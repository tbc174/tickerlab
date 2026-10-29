"""Monta as fichas do dossiê da empresa a partir da base (plano de 17/10/2026, PRs 1 e 1b).

    python -m scripts.gerar_dossies                   (a base do acervo; grava em <acervo>/dossies)
    python -m scripts.gerar_dossies --pasta <base>    (outra pasta da base)
    python -m scripts.gerar_dossies --saida <pasta>   (ensaio: grava fora do acervo)

Lê só o que a base já tem (nenhuma coleta nova), e só pela porta (`base.porta`, ADR 0077): o nome não é
`montar_*` porque não grava a base, então o `test_porta_unica` vigia. Grava `<saida>/<AAAA-MM-DD>/<cnpj>.json`, uma ficha
por companhia com ticker que vale hoje e tem alguma seção, e o `manifesto.json`: a versão do esquema e do
código, o hash de cada tabela lida (ADR 0078: dá para refazer e conferir) e as tabelas que faltaram. A
pasta do dia é montada ao lado e só troca de nome no fim: quem lê nunca vê uma pasta pela metade. As
regras do que pode entrar ficam em `base/dossie.py`.

Uma seção que quebra numa empresa não derruba as outras nem a noite; uma ficha com pessoa não é gravada.
Roda toda noite no servidor de casa, depois da rede: saída 0 tudo certo; 1 alguma falha, com a última
linha `FALHAS: ...` (vai para o aviso do Kuma), como `scripts/montar_rede.py`.
"""

import argparse
import json
import logging
import shutil
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from base import contestacoes as contestacoes_da_base
from base import dossie
from base import indicadores_de_caixa as t1
from base.dicionario import TABELAS
from base.porta import Porta
from src import acervo
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger(__name__)
FUSO = ZoneInfo("America/Sao_Paulo")  # o dia da pasta é o do Brasil, não o do servidor
TAMANHO_MAXIMO_DO_RESUMO = 300  # o resumo vai no endereço do push do Kuma
VAZIA = pd.DataFrame()
RAIZ_DO_CNPJ = 8  # os 8 primeiros dígitos: a empresa, sem a filial
Filtros = dict[str, object]


@dataclass
class Leitor:
    """Lê as tabelas pela porta e anota o hash de cada arquivo lido e as tabelas que faltaram (vão no
    manifesto: dá para refazer a noite e conferir, ADR 0078)."""

    porta: Porta
    tabelas: dict[str, str | None] = field(default_factory=dict)
    faltando: list[str] = field(default_factory=list)

    def _existe(self, tabela: str) -> bool:
        """A tabela tem arquivo nesta base (uma que nem existe no dicionário é erro de código)."""
        if tabela not in self.porta.tabelas:
            raise KeyError(f"tabela `{tabela}` não existe no dicionário da base")
        try:
            self.tabelas.update(self.porta.hashes(tabela))
        except KeyError:
            self.faltando.append(tabela)
            return False
        return True

    def ler(
        self,
        tabela: str,
        colunas: list[str] | None = None,
        filtros: Filtros | None = None,
        como_era_em: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """A tabela inteira, ou só as `colunas` que ela tem (vazia e anotada, se não há arquivo)."""
        if not self._existe(tabela):
            return VAZIA
        existentes = self.porta.colunas(tabela)
        escolhidas = (
            None if colunas is None else [c for c in colunas if c in existentes]
        )
        return self.porta.ler(
            tabela, como_era_em=como_era_em, filtros=filtros, colunas=escolhidas
        )

    def somar(
        self,
        tabela: str,
        por: list[str],
        valor: str,
        filtros: Filtros,
        como_era_em: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """A soma de `valor` por `por`, feita na porta (série de milhões de linhas)."""
        if not self._existe(tabela):
            return VAZIA
        return self.porta.somar(tabela, por, valor, filtros, como_era_em=como_era_em)

    def tem_coluna(self, tabela: str, coluna: str) -> bool:
        """A tabela existe nesta base e tem a coluna (a da Anatel antiga não tem o grupo)."""
        return self._existe(tabela) and coluna in self.porta.colunas(tabela)


@dataclass(frozen=True)
class Entradas:
    """As tabelas da base que o dossiê usa, de todas as empresas."""

    empresas: pd.DataFrame  # cnpj (só dígitos), empresa
    auditores: pd.DataFrame
    trocas: pd.DataFrame
    controladas: pd.DataFrame
    controladoras: pd.DataFrame
    ofertas_160: pd.DataFrame
    ofertas_antigas: pd.DataFrame
    painel: pd.DataFrame
    ultimo_mes_do_cda: pd.Timestamp | None
    empresa_serie: pd.DataFrame
    eventos: pd.DataFrame
    como_era: pd.DataFrame  # a DRE anual da DFP, todas as versões (as reapresentações)
    caixa: pd.DataFrame  # a DFC e a DVA anuais da DFP, todas as versões (a série T1)
    releases: pd.DataFrame
    negociacoes: pd.DataFrame
    eventos_de_capital: pd.DataFrame
    fre: dict[str, pd.DataFrame]  # as tabelas fre_* da governança, pelo nome
    ratings: pd.DataFrame
    assembleias: pd.DataFrame  # debentures_assembleias
    series: dict[str, pd.DataFrame]
    # a ligação dos bancos (IF.data) no formato da empresa_serie: só o setor dos bancos a usa
    bancos: pd.DataFrame
    grupos: dict[
        str, pd.DataFrame
    ]  # (ano, chave, grupo) das séries cuja agência informa o grupo
    pessoas: set[str]
    rede: dossie.RedeDaNoite
    hoje: pd.Timestamp  # o dia da ficha, sem fuso, para comparar com as datas da base
    # o M&A das assessorias de cada empresa (raiz do CNPJ), como era conhecido em `hoje`
    negocios_de_ma: dict[str, pd.DataFrame] = field(default_factory=dict)
    # insolvência (CVM) e situação especial (Receita) por raiz de CNPJ; None: a base não tem a tabela
    # (a ficha diz "não consultamos"). As contestações vêm do CSV conferido à mão, por raiz.
    insolvencia: dict[str, pd.DataFrame] | None = None
    situacao_especial: dict[str, pd.DataFrame] | None = None
    contestacoes: pd.DataFrame = field(default_factory=contestacoes_da_base.vazia)
    # o relatório do auditor sobre a DFP (`pareceres_dfp`); vazio: a base ainda não tem a tabela
    pareceres: pd.DataFrame = field(default_factory=pd.DataFrame)
    # o lucro ajustado e o dividendo de cada exercício (`proventos`, do FRE), já com a entrega do FRE
    proventos: pd.DataFrame = field(default_factory=pd.DataFrame)


# só as colunas que as seções de qualidade do lucro, de geração de caixa e de capital usam (a DRE de
# todo o mercado é grande)
COLUNAS_DA_DRE = (
    "cnpj",
    "grupo",
    "demonstracao",
    "documento",
    "conta",
    "descricao",
    "inicio",
    "fim",
    "valor",
    "divulgado_em",
)
COLUNAS_DO_RELEASE = (
    "cnpj",
    "versao",
    "periodo",
    "referencia",
    "data_entrega",
    "link",
    "linha",
    "periodo_lido",
    "leitura",
    "valor_release_reais",
    "valor_oficial_reais",
    "diferenca_pct",
    "classe",
    "publico_em",
)
COLUNAS_DAS_NEGOCIACOES = ("cnpj", "cargo", "operacao", "data", "entregue_em", "valor")
COLUNAS_DOS_EVENTOS = (
    "cnpj", "referencia", "versao", "tipo", "data", "fator", "acoes_novas", "valor",
)  # fmt: skip
_DO_FRE = ("cnpj", "referencia", "versao", "conhecido_em")
COLUNAS_DA_GOVERNANCA = {  # tabela do FRE → as colunas que a seção usa (nunca nomes)
    "fre_conselho": (*_DO_FRE, "orgao", "membros", "independentes", "eleitos_por_minoritarios"),
    "fre_comites": (*_DO_FRE, "tipo_de_comite", "membros"),
    "fre_remuneracao": (
        *_DO_FRE, "fim_do_exercicio", "orgao", "membros_remunerados", "total_remuneracao",
        "total_do_orgao",
    ),
    "fre_remuneracao_extremos": (*_DO_FRE, "fim_do_exercicio", "orgao", "maior", "media", "menor"),
    "fre_diversidade": (*_DO_FRE, "orgao", "genero_feminino"),
}  # fmt: skip
COLUNAS_DA_INSOLVENCIA = (
    "cnpj", "rotulo", "evento", "protocolo", "versao", "referencia", "conhecido_em", "link",
)  # fmt: skip
COLUNAS_DOS_PARECERES = (
    "cnpj", "referencia", "versao", "disponivel_em", "opiniao", "enfase", "continuidade_operacional",
)  # fmt: skip
COLUNAS_DA_SITUACAO_ESPECIAL = (
    "cnpj", "cnpj_basico", "matriz", "situacao_especial", "rotulo", "data_situacao_especial",
    "mes_do_retrato", "disponivel_em",
)  # fmt: skip
COLUNAS_DOS_RATINGS = (
    "cnpj", "agencia", "escala", "nota", "nota_original", "nivel", "perspectiva", "acao",
    "data_acao", "publico_em", "protocolo", "link", "situacao_extracao",
)  # fmt: skip
# `estresse` é um rótulo nosso: a ficha o usa só para escolher as assembleias de aperto e não o mostra
COLUNAS_DAS_ASSEMBLEIAS = (
    "cnpj", "documento", "especie", "assunto", "publico_em", "protocolo", "versao", "link",
    dossie.APERTO, *(f"tema_{tema}" for tema in dossie.TEMAS_DAS_ASSEMBLEIAS),
)  # fmt: skip
COLUNAS_DOS_PROVENTOS = (
    "cnpj", "referencia", "versao", "exercicio", "lucro_ajustado", "dividendo_total", "payout",
)  # fmt: skip


def _empresas(tickers: pd.DataFrame) -> pd.DataFrame:
    """As companhias com algum ticker que vale hoje (o FCA mais recente ainda o mostra)."""
    if tickers.empty:
        return pd.DataFrame(columns=["cnpj", "empresa"])
    valendo = tickers[tickers["valido_ate"].isna()]
    tabela = pd.DataFrame(
        {"cnpj": dossie.digitos(valendo["cnpj"]), "empresa": valendo["empresa"]}
    )
    return tabela.drop_duplicates("cnpj").reset_index(drop=True)


def _pessoas(entidades: pd.DataFrame) -> set[str]:
    if entidades.empty:
        return set()
    pessoas = entidades[entidades["trata_como_pessoa"].fillna(False).astype(bool)]
    return {n for n in pessoas["nome"].dropna().map(dossie.normalizar_nome) if n}


def ler_serie(
    leitor: Leitor, serie: dossie.SerieDaAgencia, hoje: pd.Timestamp | None = None
) -> pd.DataFrame:
    """(ano, chave, valor) de todo o mercado de uma agência, já no modo da série (mais a `abertura`,
    quando a série tem uma).

    A porta soma por data e chave como a fonte escreve; aqui a chave é limpa (o mesmo CNPJ formatado e
    em dígitos vira um só) e somada de novo, o que dá o mesmo que limpar antes de somar. A série
    `como_era` (o IF.data) é lida como era em `hoje`: a data-base ainda não pública fica de fora.
    A soma também abre pela coluna de publicação da tabela (quando ela tem uma), para o rastro dizer
    quando cada mês ficou público; abrir por mais uma coluna não muda a soma.
    """
    abertura = [serie.abertura] if serie.abertura else []
    publicacao = _coluna_de_publicacao(leitor, serie.tabela)
    somada = leitor.somar(
        serie.tabela,
        [serie.data, serie.chave, *abertura, *publicacao],
        serie.valor,
        {coluna: valor for coluna, valor in serie.filtros},
        como_era_em=hoje if serie.como_era else None,
    )
    if somada.empty:
        return VAZIA
    chave = somada[serie.chave].astype(str).str.strip()
    mensais = pd.DataFrame(
        {
            "competencia": pd.to_datetime(somada[serie.data]),
            "chave": dossie.digitos(chave) if serie.chave_em_digitos else chave,
            **({"abertura": somada[serie.abertura]} if serie.abertura else {}),
            "valor": somada[serie.valor],
        }
    )
    por = ["competencia", "chave", *(["abertura"] if serie.abertura else [])]
    publicado = (
        pd.to_datetime(somada[publicacao[0]]).groupby(mensais["competencia"]).max()
        if publicacao
        else None
    )
    mensais = mensais.groupby(por, as_index=False)["valor"].sum()
    if publicado is not None:
        mensais["publicado_em"] = mensais["competencia"].map(publicado)
    return dossie.serie_anual(mensais, serie.modo, serie.meses_por_periodo)


def _coluna_de_publicacao(leitor: Leitor, tabela: str) -> list[str]:
    """A coluna de quando a linha ficou pública, se a tabela tem uma (lista vazia: não tem)."""
    coluna = TABELAS[tabela].datas.get("publico_em")
    return [coluna] if coluna and leitor.tem_coluna(tabela, coluna) else []


def ler_grupos(leitor: Leitor, serie: dossie.SerieDaAgencia) -> pd.DataFrame:
    """(ano, chave, grupo) do grupo econômico que a agência informa (vazia: a série não tem grupo)."""
    if serie.grupo is None or not leitor.tem_coluna(serie.tabela, serie.grupo):
        return VAZIA
    somada = leitor.somar(
        serie.tabela,
        ["competencia", serie.chave, serie.grupo],
        serie.valor,
        {coluna: valor for coluna, valor in serie.filtros},
    )
    if somada.empty:
        return VAZIA
    chave = somada[serie.chave].astype(str).str.strip()
    mensais = pd.DataFrame(
        {
            "competencia": pd.to_datetime(somada["competencia"]),
            "chave": dossie.digitos(chave) if serie.chave_em_digitos else chave,
            "grupo": somada[serie.grupo],
            "valor": somada[serie.valor],
        }
    )
    mensais = mensais.groupby(
        ["competencia", "chave", "grupo"], as_index=False, dropna=False
    )["valor"].sum()
    return dossie.grupos_por_ano(mensais)


def _controladoras(
    leitor: Leitor, hoje: pd.Timestamp, entidades: pd.DataFrame
) -> pd.DataFrame:
    """Quem controla cada companhia hoje (a rede como era hoje)."""
    ligacoes = leitor.ler(
        "ligacoes",
        ["de", "para", "tipo", "situacao", "fonte", "participacao"],
        filtros={"tipo": "controlada_de", "fonte": "cvm-fre"},
        como_era_em=hoje,
    )
    identificadores = leitor.ler(
        "identificadores",
        ["id_entidade", "sistema", "valor", "ate"],
        filtros={"sistema": "cnpj"},
        como_era_em=hoje,
    )
    if ligacoes.empty or entidades.empty or identificadores.empty:
        return VAZIA
    return dossie.controladoras(ligacoes, entidades, identificadores)


def _rede(
    leitor: Leitor,
    hoje: pd.Timestamp,
    entidades: pd.DataFrame,
    controladas: pd.DataFrame,
) -> dossie.RedeDaNoite:
    """A rede como era hoje, só com os tipos e os identificadores que a seção da rede mostra."""
    ligacoes = leitor.ler(
        "ligacoes", filtros={"tipo": sorted(dossie.TIPOS_DA_REDE)}, como_era_em=hoje
    )
    identificadores = leitor.ler(
        "identificadores",
        ["id_entidade", "sistema", "valor", "desde", "ate"],
        filtros={"sistema": list(dossie.SISTEMAS_DA_REDE)},
        como_era_em=hoje,
    )
    return dossie.preparar_rede(ligacoes, entidades, identificadores, controladas, hoje)


COLUNAS_DA_LIGACAO_DOS_BANCOS = (
    "data_base",
    "cod_inst",
    "instituicao",
    "cnpj",
    "ligado_por",
)


def _bancos(
    leitor: Leitor, series: dict[str, pd.DataFrame], dia: pd.Timestamp
) -> pd.DataFrame:
    """A ligação dos conglomerados das séries dos bancos às companhias, como era no dia."""
    chaves = {
        str(chave)
        for s in dossie.SERIES_DOS_BANCOS
        if not series[s.nome].empty
        for chave in series[s.nome]["chave"]
    }
    ligacao = leitor.ler("ligacao_dos_bancos", [*COLUNAS_DA_LIGACAO_DOS_BANCOS])
    return dossie.ligacoes_dos_bancos(ligacao, chaves, dia)


def _dia(agora: pd.Timestamp) -> pd.Timestamp:
    """O dia de `agora`, sem fuso: as datas da base (entrega, publicação) não têm fuso."""
    return (agora.tz_localize(None) if agora.tzinfo else agora).normalize()


def ler_entradas(leitor: Leitor, hoje: pd.Timestamp) -> Entradas:
    """Tudo o que o dossiê lê da base, uma vez, para todas as empresas.

    As pessoas vêm de todas as entidades, sem data: o filtro de pessoas da ficha erra para o lado
    de tirar demais.
    """
    entidades = leitor.ler("entidades", ["id_entidade", "nome", "trata_como_pessoa"])
    controladoras = _controladoras(leitor, hoje, entidades)
    controladas = leitor.ler("controladas")
    series = {
        s.nome: ler_serie(leitor, s, hoje)
        for s in (*dossie.SERIES_DAS_AGENCIAS, *dossie.SERIES_DOS_BANCOS)
    }
    fre = {
        tabela: leitor.ler(tabela, [*colunas])
        for tabela, colunas in COLUNAS_DA_GOVERNANCA.items()
    }
    return Entradas(
        empresas=_empresas(
            leitor.ler("tickers_no_tempo", ["cnpj", "empresa", "valido_ate"])
        ),
        auditores=leitor.ler("auditores"),
        trocas=leitor.ler("trocas_de_auditor"),
        controladas=controladas,
        controladoras=dossie.controladoras_em_dia(controladoras, controladas, hoje),
        ofertas_160=leitor.ler("ofertas_resolucao_160"),
        ofertas_antigas=leitor.ler("ofertas_antigas"),
        # a tabela tem os dois painéis: o por empresa é o que não tem emissor
        painel=leitor.ler("painel_dos_fundos", filtros={"emissor": None}),
        ultimo_mes_do_cda=dossie.ultimo_mes_completo(
            leitor.ler("cobertura_dos_fundos", ["competencia", "valor_comprado"])
        ),
        empresa_serie=leitor.ler("empresa_serie"),
        eventos=leitor.ler(
            "eventos", ["cnpj", "rotulo", "assunto", "publicado_em", "link"]
        ),
        como_era=leitor.ler(
            "demonstracoes_como_era",
            [*COLUNAS_DA_DRE],
            filtros={
                "demonstracao": "DRE",
                "documento": "DFP",
                # o EBIT (3.05) é da geração de caixa; a qualidade do lucro não o lê
                "conta": [*dossie.CONTAS_DA_DRE, t1.EBIT],
            },
        ),
        caixa=leitor.ler(
            "demonstracoes_como_era",
            [*COLUNAS_DA_DRE],
            filtros={"documento": "DFP", "demonstracao": [*t1.DFC, t1.DVA]},
        ),
        releases=leitor.ler("release_x_oficial", [*COLUNAS_DO_RELEASE]),
        negociacoes=leitor.ler("negociacoes", [*COLUNAS_DAS_NEGOCIACOES]),
        eventos_de_capital=leitor.ler("eventos_de_capital", [*COLUNAS_DOS_EVENTOS]),
        fre=fre,
        ratings=leitor.ler("ratings", [*COLUNAS_DOS_RATINGS]),
        assembleias=leitor.ler("debentures_assembleias", [*COLUNAS_DAS_ASSEMBLEIAS]),
        series=series,
        bancos=_bancos(leitor, series, _dia(hoje)),
        grupos={
            s.nome: ler_grupos(leitor, s) for s in dossie.SERIES_DAS_AGENCIAS if s.grupo
        },
        pessoas=_pessoas(entidades),
        rede=_rede(leitor, hoje, entidades, controladas),
        hoje=_dia(hoje),
        negocios_de_ma=_negocios_de_ma(leitor, _dia(hoje)),
        insolvencia=_por_raiz(
            _ler_se_existe(leitor, "insolvencia", COLUNAS_DA_INSOLVENCIA), "cnpj"
        ),
        situacao_especial=_por_raiz(
            _ler_se_existe(
                leitor, "cnpj_situacao_especial", COLUNAS_DA_SITUACAO_ESPECIAL
            ),
            "cnpj_basico",
        ),
        contestacoes=contestacoes_da_base.ler(),
        pareceres=_pareceres(leitor),
        proventos=_proventos(leitor, fre["fre_remuneracao"]),
    )


def _proventos(leitor: Leitor, fre_remuneracao: pd.DataFrame) -> pd.DataFrame:
    """Os proventos de cada exercício com a data em que o FRE que os informou foi entregue.

    A tabela `proventos` só tem a data da coleta: para cortar o futuro, a ficha precisa do dia em que o
    FRE ficou público, que vem de `fre_remuneracao` pela mesma chave (cnpj, referencia, versao). Linha
    de FRE que a base não conhece fica de fora. Vazio quando a base não tem a tabela.
    """
    proventos = _ler_se_existe(leitor, "proventos", COLUNAS_DOS_PROVENTOS)
    if proventos is None or proventos.empty:
        return VAZIA
    return com_a_entrega_do_fre(proventos, fre_remuneracao)


def com_a_entrega_do_fre(proventos: pd.DataFrame, do_fre: pd.DataFrame) -> pd.DataFrame:
    """`proventos` com a coluna `conhecido_em` de `do_fre` (uma tabela fre_*), pela chave do FRE."""
    chave = ["cnpj", "referencia", "versao"]
    if do_fre.empty or not set(chave) <= set(do_fre.columns):
        return proventos.iloc[0:0]
    entregas = do_fre[[*chave, "conhecido_em"]].drop_duplicates(chave)
    juntos = proventos.assign(
        cnpj=dossie.digitos(proventos["cnpj"]),
        referencia=pd.to_datetime(proventos["referencia"]),
    ).merge(
        entregas.assign(
            cnpj=dossie.digitos(entregas["cnpj"]),
            referencia=pd.to_datetime(entregas["referencia"]),
        ),
        on=chave,
        how="inner",
    )
    return juntos.reset_index(drop=True)


def _pareceres(leitor: Leitor) -> pd.DataFrame:
    """Os pareceres do auditor (todas as versões, com o dia em que ficaram públicos); vazio sem a tabela."""
    pareceres = _ler_se_existe(leitor, "pareceres_dfp", COLUNAS_DOS_PARECERES)
    return VAZIA if pareceres is None else pareceres


def _ler_se_existe(
    leitor: Leitor, tabela: str, colunas: tuple[str, ...]
) -> pd.DataFrame | None:
    """A tabela lida, ou None quando a base não a tem (a ficha diz que não consultou a fonte)."""
    if not leitor.tem_coluna(tabela, colunas[0]):
        return None
    return leitor.ler(tabela, [*colunas])


def _por_raiz(
    tabela: pd.DataFrame | None, coluna: str
) -> dict[str, pd.DataFrame] | None:
    """A tabela separada pela raiz do CNPJ (a filial e a matriz são a mesma empresa); None fica None."""
    if tabela is None:
        return None
    if tabela.empty:
        return {}
    raizes = dossie.digitos(tabela[coluna]).str[:RAIZ_DO_CNPJ]
    return {str(r): g for r, g in tabela.groupby(raizes)}


def _negocios_de_ma(leitor: Leitor, hoje: pd.Timestamp) -> dict[str, pd.DataFrame]:
    """O M&A das assessorias por raiz de CNPJ (vazio: a base ainda não tem as tabelas)."""
    chave = ["assessoria", "url"]
    return dossie.negocios_de_ma_por_empresa(
        leitor.ler("ma_partes", [*chave, "papel", "cnpj_raiz", "ligacao_por"]),
        leitor.ler("ma_negocios", [*chave, "id_negocio"]),
        leitor.ler("ma_datas", [*chave, "conhecido_em_do_negocio", "confirmado_por"]),
        leitor.ler("ma_assessorias", [*chave, "tipo"]),
        hoje.strftime("%Y-%m-%d"),
    )


def _por_cnpj(tabela: pd.DataFrame, coluna: str) -> dict[str, pd.DataFrame]:
    """A tabela separada por CNPJ (só dígitos), para cada empresa ler só as linhas dela."""
    if tabela.empty or coluna not in tabela.columns:
        return {}
    return {str(c): g for c, g in tabela.groupby(dossie.digitos(tabela[coluna]))}


def _do_grupo(tabelas: dict[str, pd.DataFrame], cnpjs: set[str]) -> pd.DataFrame:
    """As linhas de todos os CNPJs do grupo juntas (vazia se nenhum aparece)."""
    partes = [tabelas[c] for c in sorted(cnpjs) if c in tabelas]
    return pd.concat(partes, ignore_index=True) if partes else VAZIA


Secao = Callable[[str], dict | None]


def _da_raiz(tabelas: dict[str, pd.DataFrame] | None, cnpj: str) -> pd.DataFrame | None:
    """As linhas da empresa (raiz do CNPJ); None: a base não tem a tabela; vazia: sem linha dela."""
    return None if tabelas is None else tabelas.get(cnpj[:RAIZ_DO_CNPJ], VAZIA)


def _secoes(entradas: Entradas, setores: Mapping[str, dict]) -> dict[str, Secao]:
    """Cada seção como uma função do CNPJ, com as tabelas já separadas por empresa.

    `setores`: a seção do setor de cada CNPJ que a leva (`distribuir_setores`), já pronta.
    """
    auditores = _por_cnpj(entradas.auditores, "cnpj")
    trocas = _por_cnpj(entradas.trocas, "cnpj")
    pareceres = _por_cnpj(entradas.pareceres, "cnpj")
    controladas = _por_cnpj(entradas.controladas, "cnpj_companhia")
    controladoras = _por_cnpj(entradas.controladoras, "cnpj")
    ofertas_160 = _por_cnpj(entradas.ofertas_160, "cnpj_emissor")
    ofertas_antigas = _por_cnpj(entradas.ofertas_antigas, "cnpj_emissor")
    painel = _por_cnpj(entradas.painel, "cnpj")
    empresa_serie = _por_cnpj(entradas.empresa_serie, "cnpj_companhia")
    eventos = _por_cnpj(entradas.eventos, "cnpj")
    como_era = _por_cnpj(entradas.como_era, "cnpj")
    caixa = _por_cnpj(entradas.caixa, "cnpj")
    releases = _por_cnpj(entradas.releases, "cnpj")
    negociacoes = _por_cnpj(entradas.negociacoes, "cnpj")
    eventos_de_capital = _por_cnpj(entradas.eventos_de_capital, "cnpj")
    fre = {nome: _por_cnpj(tabela, "cnpj") for nome, tabela in entradas.fre.items()}
    ratings = _por_cnpj(entradas.ratings, "cnpj")
    assembleias = _por_cnpj(entradas.assembleias, "cnpj")
    proventos = _por_cnpj(entradas.proventos, "cnpj")
    hoje = entradas.hoje
    de_ma = entradas.negocios_de_ma

    def governanca(cnpj: str) -> dict | None:
        do_fre = {nome: fre[nome].get(cnpj, VAZIA) for nome in COLUNAS_DA_GOVERNANCA}
        return dossie.secao_governanca(
            do_fre["fre_conselho"],
            do_fre["fre_comites"],
            do_fre["fre_remuneracao"],
            do_fre["fre_remuneracao_extremos"],
            do_fre["fre_diversidade"],
            hoje,
        )

    def ofertas_e_fundos(cnpj: str) -> dict | None:
        grupo = dossie.cnpjs_do_grupo(cnpj, controladas.get(cnpj, VAZIA))
        return dossie.secao_ofertas_e_fundos(
            _do_grupo(ofertas_160, grupo),
            _do_grupo(ofertas_antigas, grupo),
            painel.get(cnpj, VAZIA),
            entradas.ultimo_mes_do_cda,
        )

    return {
        "auditor_e_controladas": lambda c: dossie.secao_auditor_e_controladas(
            auditores.get(c, VAZIA),
            trocas.get(c, VAZIA),
            controladas.get(c, VAZIA),
            controladoras.get(c, VAZIA),
            entradas.pessoas,
            pareceres.get(c, VAZIA),
            hoje,
        ),
        "qualidade_do_lucro": lambda c: dossie.secao_qualidade_do_lucro(
            como_era.get(c, VAZIA), releases.get(c, VAZIA), trocas.get(c, VAZIA), hoje
        ),
        "geracao_de_caixa": lambda c: dossie.secao_geracao_de_caixa(
            pd.concat([como_era.get(c, VAZIA), caixa.get(c, VAZIA)]), hoje
        ),
        "ofertas_e_fundos": ofertas_e_fundos,
        "capital_e_acionistas": lambda c: dossie.secao_capital_e_acionistas(
            negociacoes.get(c, VAZIA),
            eventos_de_capital.get(c, VAZIA),
            painel.get(c, VAZIA),
            hoje,
            entradas.ultimo_mes_do_cda,
            proventos=proventos.get(c, VAZIA),
        ),
        "governanca": governanca,
        "credito": lambda c: dossie.secao_credito(
            ratings.get(c, VAZIA), assembleias.get(c, VAZIA), hoje
        ),
        "setor_regulado": lambda c: dossie.secao_setor_regulado(
            empresa_serie.get(c, VAZIA), entradas.series
        ),
        "setor": setores.get,
        "negocios": lambda c: dossie.secao_negocios(
            eventos.get(c, VAZIA), de_ma.get(c[:RAIZ_DO_CNPJ])
        ),
        "insolvencia": lambda c: dossie.secao_insolvencia(
            _da_raiz(entradas.insolvencia, c),
            _da_raiz(entradas.situacao_especial, c),
            contestacoes_da_base.da_empresa(entradas.contestacoes, c[:RAIZ_DO_CNPJ]),
            hoje,
        ),
        "rede": lambda c: dossie.secao_rede(c, entradas.rede),
    }


@dataclass
class Resumo:
    empresas: int = 0
    fichas: int = 0
    falhas: list[str] = field(default_factory=list)
    # setor → a ficha que leva a seção e os membros (vai no manifesto: o app acha o setor por ele)
    setores: dict[str, dict] = field(default_factory=dict)


SetorMontado = tuple[str, list[str], dict]  # chave do setor, CNPJs dos membros, a seção


def _ligacoes_dos_setores(entradas: Entradas) -> pd.DataFrame:
    """A empresa_serie mais a ligação dos bancos: as entidades de todas as agências dos setores."""
    partes = [t for t in (entradas.empresa_serie, entradas.bancos) if not t.empty]
    if len(partes) < 2:
        return partes[0] if partes else entradas.empresa_serie
    return pd.concat(partes, ignore_index=True)


def montar_setores(entradas: Entradas) -> tuple[list[SetorMontado], list[str]]:
    """A seção de cada setor do lançamento, uma vez para todo o mercado; um setor que quebra fica de
    fora e vai nas falhas, sem derrubar os outros nem a noite."""
    montados, falhas = [], []
    ligacoes = _ligacoes_dos_setores(entradas)
    for setor in dossie.SETORES_DO_LANCAMENTO:
        try:
            membros = dossie.membros_do_setor(setor, entradas.empresas, ligacoes)
            if membros.empty:  # nenhuma companhia da base no setor: nada a montar
                continue
            secao = dossie.secao_setor(
                setor, membros, entradas.series, ligacoes, entradas.grupos
            )
        except Exception as erro:  # noqa: BLE001 (um setor não derruba a noite)
            falhas.append(f"setor {setor.chave}: {type(erro).__name__}: {erro}")
            continue
        if secao is not None:
            montados.append((setor.chave, membros["cnpj"].tolist(), secao))
    return montados, falhas


def distribuir_setores(
    montados: list[SetorMontado],
) -> tuple[dict[str, tuple[str, dict]], list[str]]:
    """CNPJ → (setor, seção): cada setor vai na ficha do 1º membro que ainda não leva outro.

    O recebedor do servidor só aceita a ficha de um CNPJ e o manifesto: o setor viaja dentro da ficha
    de um membro, e uma ficha tem uma seção de cada chave. Quem está em dois setores (seguros e
    saúde) leva o primeiro e passa o segundo para outro membro.
    """
    fichas: dict[str, tuple[str, dict]] = {}
    falhas = []
    for chave, membros, secao in montados:
        livre = next((cnpj for cnpj in membros if cnpj not in fichas), None)
        if livre is None:
            falhas.append(f"setor {chave}: todos os membros já levam outro setor")
            continue
        fichas[livre] = (chave, secao)
    return fichas, falhas


def _ficha(
    cnpj: str, empresa: str, secoes: dict[str, Secao], gerado_em: str, quebras: Counter
) -> dict | None:
    """A ficha de uma empresa (None: nenhuma seção); a seção que quebra fica de fora e é contada."""
    feitas = []
    for chave, montar_secao in secoes.items():
        try:
            feitas.append(montar_secao(cnpj))
        except Exception as erro:  # noqa: BLE001 (uma seção não derruba a ficha nem a noite)
            quebras[f"{chave}: {type(erro).__name__}: {erro}"] += 1
    ficha = dossie.montar_ficha(cnpj, empresa, feitas, gerado_em)
    return ficha if ficha["secoes"] else None


def _gravar_json(destino: Path, conteudo: dict) -> None:
    destino.write_text(
        json.dumps(conteudo, ensure_ascii=False, allow_nan=False, indent=None),
        encoding="utf-8",
    )


def _gravar_fichas(
    entradas: Entradas, pasta: Path, gerado_em: str, resumo: Resumo
) -> None:
    montados, falhas_dos_setores = montar_setores(entradas)
    setores, sem_ficha = distribuir_setores(montados)
    membros = {chave: cnpjs for chave, cnpjs, _ in montados}
    secoes = _secoes(entradas, {cnpj: secao for cnpj, (_, secao) in setores.items()})
    quebras: Counter = Counter()
    for linha in entradas.empresas.itertuples(index=False):
        ficha = _ficha(str(linha.cnpj), str(linha.empresa), secoes, gerado_em, quebras)
        if ficha is None:
            continue
        try:
            dossie.conferir_sem_pessoas(ficha, entradas.pessoas)
            _gravar_json(pasta / f"{linha.cnpj}.json", ficha)
        except (dossie.PessoaNaFichaError, ValueError) as erro:
            resumo.falhas.append(f"{linha.cnpj}: {type(erro).__name__}")
            continue
        resumo.fichas += 1
        if linha.cnpj in setores:
            chave = setores[linha.cnpj][0]
            resumo.setores[chave] = {"ficha": linha.cnpj, "membros": membros[chave]}
    resumo.falhas += [
        *falhas_dos_setores,
        *sem_ficha,
        *(f"{quebra} ({n} empresas)" for quebra, n in quebras.items()),
    ]


def _trocar_pasta(montando: Path, destino: Path) -> None:
    """A pasta do dia aparece inteira de uma vez; a de antes, do mesmo dia, sai."""
    if destino.exists():
        shutil.rmtree(destino)
    montando.rename(destino)


def montar(
    pasta: Path, saida: Path, agora: pd.Timestamp, versao_do_codigo: str
) -> Resumo:
    """Grava as fichas e o manifesto em `<saida>/<dia>`; devolve quantas e o que falhou."""
    with Porta(pasta) as porta:
        leitor = Leitor(porta)
        entradas = ler_entradas(leitor, agora)
    resumo = Resumo(empresas=len(entradas.empresas))
    if entradas.empresas.empty:
        resumo.falhas.append("tickers_no_tempo: sem o universo das empresas")
        return resumo
    dia = agora.strftime("%Y-%m-%d")
    montando = saida / f".{dia}.montando"
    shutil.rmtree(montando, ignore_errors=True)
    montando.mkdir(parents=True)
    _gravar_fichas(entradas, montando, agora.isoformat(), resumo)
    _gravar_json(
        montando / "manifesto.json",
        {
            "versao_do_esquema": dossie.VERSAO_DO_ESQUEMA,
            "gerado_em": agora.isoformat(),
            "versao_do_codigo": versao_do_codigo,
            "empresas": resumo.empresas,
            "fichas": resumo.fichas,
            "tabelas": dict(sorted(leitor.tabelas.items())),
            "faltando": sorted(set(leitor.faltando)),
            "falhas": resumo.falhas,
            "setores": dict(sorted(resumo.setores.items())),
        },
    )
    _trocar_pasta(montando, saida / dia)
    return resumo


def _avisar(problemas: list[str]) -> int:
    linha = "FALHAS: dossiês: " + "; ".join(problemas)
    print(linha[:TAMANHO_MAXIMO_DO_RESUMO])
    return 1


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--pasta", type=Path, default=None, help="pasta da base")
    argumentos.add_argument(
        "--saida", type=Path, default=None, help="onde gravar as fichas"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    raiz = acervo.pasta_do_acervo() or Path("dados_locais/acervo")
    pasta = opcoes.pasta or raiz / "base"
    saida = opcoes.saida or raiz / "dossies"
    versao = exigir_versao_do_codigo()
    log.info("Versão do código: %s", versao)
    try:
        resumo = montar(pasta, saida, pd.Timestamp(datetime.now(FUSO)), versao)
    except Exception as erro:  # a noite não para em silêncio: o Kuma recebe o motivo
        log.exception("a montagem dos dossiês falhou")
        return _avisar([f"{type(erro).__name__}: {erro}"])
    log.info("dossiês: %d fichas de %d empresas", resumo.fichas, resumo.empresas)
    return _avisar(resumo.falhas) if resumo.falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
