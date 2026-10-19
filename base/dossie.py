"""O dossiê da empresa: o que a base de ML diz de cada companhia, para o app (plano de 17/10/2026).

O "Relatório da empresa" do app (ADR 0032) ganha seções que vêm da base. Elas são calculadas toda noite
no servidor de casa (`scripts/gerar_dossies.py`), uma ficha JSON por CNPJ, e só o assinante Pro as vê.
É o primeiro uso da base como produto (ADR 0076: o TickerLab é o primeiro cliente).

**Só entra o que pode ser mostrado a quem paga** (`pode_mostrar`):

- a tabela está no dicionário da base e **não guarda pessoa** (ADR 0075: nomes esperam a LGPD);
- a fonte pode ser **mostrada** pela trava das licenças (`coletas.pode_usar("mostrar", ...)`): toda
  fonte, com a marca registrada e a fonte citada (ADR 0102), menos a B3 (ADR 0019);
- não é uma tabela de crise ou de risco com o nome da empresa (insolvência, atraso, situação especial,
  dívida com a União: esperam o parecer, P-44), nem das assessorias de M&A (licença a confirmar).

Uma fonte que passar a ser vendável entra sozinha: basta a tabela estar numa seção. Para pôr uma série
nova de agência (as das séries 5 e 6 da base, quando chegarem), é uma linha em `SERIES_DAS_AGENCIAS`.

Por último, `conferir_sem_pessoas` passa pela ficha inteira: nenhum CPF, nenhum nome de entidade tratada
como pessoa e nenhuma coluna de pessoa. Os textos livres (o assunto de um fato relevante) só são
conferidos contra os nomes que a rede conhece: é um limite, escrito na seção.

Funções puras: as tabelas chegam já só com a empresa da ficha; ler e gravar fica no script.
"""

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, NamedTuple

import pandas as pd

from base.cnpj import formatar, raiz
from base.dicionario import TABELAS
from base.rede.ligacoes_das_fontes import (
    AUDITA,
    COLIGADA_DE,
    CONTROLADA_DE,
    DO_CONGLOMERADO_DE,
    EMITE,
    PARTICIPADA_DE,
)
from base.rede.vistas import vista_publicada
from src.banco.coletas import MOSTRAR, licenca_da_fonte, pode_usar

VERSAO_DO_ESQUEMA = 1  # muda quando o app precisa ler a ficha de outro jeito
# fora do app até o parecer (crise ou risco com o nome da empresa, P-44), mesmo que a licença deixe
# (a Emenda 3 da ADR 0008 liberou a da PGFN e a da situação especial; o P-44 ainda as segura)
TABELAS_PROIBIDAS = frozenset(
    {"insolvencia", "rotulos_atraso", "cnpj_situacao_especial", "pgfn_divida"}
)
LINHAS_NAS_LISTAS = (
    20  # últimas ofertas, últimos negócios: o resto fica na contagem por ano
)
MESES_DOS_FUNDOS = 24
ANOS_NAS_SERIES = 10
MESES_NO_ANO = 12
PARTICIPACAO_DE_CONTROLE = (
    50.0  # sem o tipo no FRE, mais da metade do capital é controle
)
ANOS_DO_FRE_EM_DIA = 2  # FRE da controladora mais velho que isso: ela parou de entregar
# mês do CDA com menos que isso do valor normal (mediana dos 12 anteriores): carteiras ainda chegando
FRACAO_DO_MES_COMPLETO = 0.6
MESES_PARA_A_MEDIANA = 12
MESES_MINIMOS_NA_MEDIANA = 6
AUDITOR_PESSOA = "Auditor pessoa física (nome não mostrado)"
DIGITOS_DO_CNPJ = 14
SOMA_DO_ANO, ULTIMO_MES = "soma do ano", "último mês do ano"
CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
COLUNAS_DE_PESSOA = frozenset(
    {"cpf", "administrador", "conselheiro", "diretor", "nome_pessoa", "socio"}
)
# palavras do assunto que indicam compra, venda, fusão ou reorganização (escolha editorial, sem acento)
PALAVRAS_DE_NEGOCIO = re.compile(
    r"aquisi|incorpora|fusao|cisao|aliena|desinvestimento|combinacao de negocio"
    r"|\bvenda de (?:participa|ativo|controle)|\bcompra de (?:participa|ativo|controle)"
    r"|oferta publica de aquisi|\bopa\b|reorganizacao societaria|joint venture"
    r"|transferencia de controle|memorando de entendimento"
)
ROTULOS_DE_NEGOCIO = ("Fato relevante", "Comunicado ao mercado")


class TabelaProibidaError(ValueError):
    """Uma seção do dossiê usaria uma tabela que não pode ser mostrada a quem assina."""


class PessoaNaFichaError(ValueError):
    """A ficha montada tem CPF, nome de pessoa ou coluna de pessoa: não sai do servidor de casa."""


# --- a regra de mostrar --------------------------------------------------------------------------


def pode_mostrar(nome_da_tabela: str) -> bool:
    """A tabela pode aparecer no app? (a trava deixa mostrar, sem pessoa e fora da lista proibida)"""
    tabela = TABELAS.get(nome_da_tabela)
    if tabela is None or tabela.pessoa or nome_da_tabela in TABELAS_PROIBIDAS:
        return False
    return pode_usar(MOSTRAR, tabela.familia_da_fonte)


def exigir_que_pode_mostrar(tabelas: Iterable[str]) -> None:
    """Levanta `TabelaProibidaError` com as tabelas que não podem ser mostradas."""
    proibidas = [nome for nome in tabelas if not pode_mostrar(nome)]
    if proibidas:
        raise TabelaProibidaError(f"não podem ser mostradas: {', '.join(proibidas)}")


def fontes_das_tabelas(tabelas: Iterable[str]) -> list[str]:
    """As licenças das fontes das tabelas, sem repetir: vão na seção (a atribuição que a licença pede)."""
    return sorted(
        {licenca_da_fonte(TABELAS[nome].familia_da_fonte) for nome in tabelas}
    )


@dataclass(frozen=True)
class SerieDaAgencia:
    """Uma medida de agência por entidade e mês, ligada à companhia pela tabela empresa ↔ série (B13)."""

    nome: str  # chave da série na ficha
    fonte_b13: str  # a `fonte` em `empresa_serie`
    tabela: str  # no dicionário da base (lida pela porta)
    chave: str  # a coluna que a B13 usa como `chave`
    valor: str
    modo: str  # SOMA_DO_ANO ou ULTIMO_MES
    medida: str  # o que o número é, escrito para a tela
    unidade: str
    # filtros de igualdade da porta: `(coluna, valor)` ou `(coluna, (valores aceitos))`
    filtros: tuple[tuple[str, str | tuple[str, ...]], ...] = ()
    chave_em_digitos: bool = False  # CNPJ: casa formatado ou não


SERIES_DAS_AGENCIAS = (
    SerieDaAgencia(
        "aneel_consumidores",
        "aneel-samp",
        "aneel_samp",
        "cnpj",
        "valor",
        ULTIMO_MES,
        "Consumidores atendidos pelas distribuidoras (ANEEL)",
        "consumidores",
        (
            ("detalhe_do_mercado", "Número de consumidores"),
            ("tipo_de_mercado", "Regular"),
        ),
        chave_em_digitos=True,
    ),
    *(
        SerieDaAgencia(
            f"anatel_{servico}",
            "anatel-acessos",
            "anatel_acessos",
            "cnpj",
            "acessos",
            ULTIMO_MES,
            f"Acessos em serviço, {texto} (Anatel)",
            "acessos",
            # a móvel vem por modalidade e por tecnologia (o mesmo acesso duas vezes): só a 1ª
            (("servico", servico), ("recorte", ("completo", "modalidade"))),
            chave_em_digitos=True,
        )
        for servico, texto in (
            ("telefonia_movel", "telefonia móvel"),
            ("banda_larga_fixa", "banda larga fixa"),
            ("tv_por_assinatura", "TV por assinatura"),
        )
    ),
    SerieDaAgencia(
        "ans_beneficiarios",
        "ans-beneficiarios",
        "ans_beneficiarios",
        "cd_operadora",
        "beneficiarios",
        ULTIMO_MES,
        "Beneficiários de planos de saúde (ANS)",
        "beneficiários",
    ),
    SerieDaAgencia(
        "anac_passageiros",
        "anac-estatistico",
        "anac_estatistico",
        "empresa_sigla",
        "passageiros_pagos",
        SOMA_DO_ANO,
        "Passageiros pagos transportados (ANAC)",
        "passageiros",
    ),
    SerieDaAgencia(
        "susep_premio_ganho",
        "susep-ses",
        "susep_seguros",
        "coenti",
        "premio_ganho",
        SOMA_DO_ANO,
        "Prêmio ganho das seguradoras (SUSEP)",
        "R$",
    ),
    SerieDaAgencia(
        "anp_vendas",
        "anp-vendas-distribuidora",
        "anp_vendas",
        "agente",
        "quantidade",
        SOMA_DO_ANO,
        "Vendas das distribuidoras de combustíveis líquidos (ANP)",
        "mil m³",
        (("unidade", "mil m³"),),
    ),
)


def fontes_do_setor(nomes_das_series: Iterable[str]) -> list[str]:
    """As licenças do setor regulado: a ligação empresa ↔ série e só as agências das séries dadas."""
    nomes = set(nomes_das_series)
    tabelas = [serie.tabela for serie in SERIES_DAS_AGENCIAS if serie.nome in nomes]
    return fontes_das_tabelas(("empresa_serie", *tabelas))


@dataclass(frozen=True)
class SecaoDaBase:
    chave: str
    titulo: str
    tabelas: tuple[str, ...]


SECOES = (
    SecaoDaBase(
        "auditor_e_controladas",
        "Auditor e controladas",
        (
            "auditores",
            "trocas_de_auditor",
            "controladas",
            "ligacoes",
            "entidades",
            "identificadores",
        ),
    ),
    SecaoDaBase(
        "ofertas_e_fundos",
        "Ofertas e fundos",
        ("ofertas_resolucao_160", "ofertas_antigas", "painel_dos_fundos"),
    ),
    SecaoDaBase(
        "setor_regulado",
        "Setor regulado",
        ("empresa_serie", *dict.fromkeys(s.tabela for s in SERIES_DAS_AGENCIAS)),
    ),
    SecaoDaBase("negocios", "Negócios (M&A pela CVM)", ("eventos",)),
    SecaoDaBase(
        "rede", "Ligações na rede", ("ligacoes", "entidades", "identificadores")
    ),
)
_SECAO_POR_CHAVE = {secao.chave: secao for secao in SECOES}

LIMITES = {
    "auditor_e_controladas": (
        "Controladas e coligadas vêm do Formulário de Referência (FRE) mais recente entregue à CVM. "
        "Quando o FRE não informa o tipo, conta como controlada a sociedade com mais da metade do "
        "capital. A controladora aparece só quando ela também entrega o FRE, com o dos últimos 2 anos ainda listando a "
        "companhia. Auditor pessoa física "
        "não tem o nome mostrado."
    ),
    "ofertas_e_fundos": (
        "Ofertas registradas na CVM (Resolução 160 e as anteriores) da companhia e das controladas do "
        "FRE mais recente (o grupo costuma emitir pelas controladas), pelo valor registrado, não o "
        "colocado. Fundos: a posição comprada somada das carteiras entregues à CVM (CDA), que saem "
        "com até 90 dias de atraso: os meses em que as carteiras ainda estão chegando ficam de fora."
    ),
    "setor_regulado": (
        "Soma das entidades ligadas à companhia pela tabela empresa ↔ série da base (própria ou "
        "controlada, pelo FRE). A participação é sobre o total da agência no ano."
    ),
    "negocios": (
        "Fatos relevantes e comunicados cujo assunto fala de compra, venda, fusão, incorporação ou "
        "reorganização. A escolha é pelas palavras do assunto: pode deixar escapar ou incluir algum. "
        "O assunto é escrito pela empresa."
    ),
    "rede": (
        "Ligações da rede de entidades do TickerLab, montada com o Formulário de Referência (FRE), o "
        "Formulário Cadastral e as carteiras dos fundos entregues à CVM e com o IF.data do Banco "
        "Central. Uma ligação do FRE só aparece quando o FRE mais recente da companhia que a informa é "
        "dos últimos 2 anos e ainda a lista. A data é a do primeiro documento que mostrou a ligação. "
        "Pessoas (sócios, administradores) e sinais negativos (sanções, dívidas) não aparecem."
    ),
}


# --- peças comuns ---------------------------------------------------------------------------------


def normalizar_nome(texto: str) -> str:
    """Sem acento, em minúsculas e com um espaço só: para comparar nomes."""
    sem_acento = unicodedata.normalize("NFD", str(texto))
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    return " ".join(sem_acento.casefold().split())


def digitos(valores: pd.Series) -> pd.Series:
    """Só os dígitos de cada valor (CNPJ formatado ou não)."""
    return valores.astype(str).str.replace(r"\D", "", regex=True)


def _data(valor: object) -> str | None:
    return None if pd.isna(valor) else pd.Timestamp(valor).strftime("%Y-%m-%d")


def _registros(tabela: pd.DataFrame) -> list[dict[str, Any]]:
    """As linhas em tipos simples (datas ISO, faltando → None), como vão no JSON."""
    copia = tabela.copy()
    for coluna in copia.columns:
        if pd.api.types.is_datetime64_any_dtype(copia[coluna]):
            copia[coluna] = copia[coluna].dt.strftime("%Y-%m-%d")
        elif copia[coluna].map(lambda v: isinstance(v, date)).any():
            # a base guarda algumas datas sem hora (`datetime.date`): o JSON as escreveria em milissegundos
            copia[coluna] = copia[coluna].map(_data)
    return json.loads(copia.to_json(orient="records", force_ascii=False))


def _item(
    chave: str, nome: str, valor: str | float | None, unidade: str, base: str | None
) -> dict[str, Any]:
    return {
        "chave": chave,
        "nome": nome,
        "valor": valor,
        "unidade": unidade,
        "base": base,
    }


def _secao(
    chave: str,
    itens: list[dict[str, Any]],
    tabelas: Mapping[str, pd.DataFrame],
    paragrafos: list[str] | None = None,
    fontes: list[str] | None = None,
) -> dict[str, Any]:
    registro = _SECAO_POR_CHAVE[chave]
    return {
        "chave": chave,
        "titulo": registro.titulo,
        "itens": itens,
        "tabelas": {nome: _registros(t) for nome, t in tabelas.items() if not t.empty},
        "paragrafos": [*(paragrafos or []), LIMITES[chave]],
        "fontes": fontes_das_tabelas(registro.tabelas) if fontes is None else fontes,
    }


def _mais_recente(tabela: pd.DataFrame) -> pd.DataFrame:
    """As linhas do documento mais recente (maior referência e, nela, a maior versão)."""
    if tabela.empty:
        return tabela
    ultima = tabela["referencia"].max()
    do_ultimo = tabela[tabela["referencia"] == ultima]
    return do_ultimo[do_ultimo["versao"] == do_ultimo["versao"].max()]


# --- auditor e controladas -----------------------------------------------------------------------


def _e_pessoa(nome: object, pessoas: set[str]) -> bool:
    return normalizar_nome(nome) in pessoas


def _nome_do_auditor(linha: pd.Series, pessoas: set[str]) -> str:
    """O nome da firma; o de um auditor pessoa física não aparece (sem CNPJ de firma ou nome de pessoa)."""
    cnpj = re.sub(r"\D", "", str(linha.get("auditor_cnpj") or ""))
    firma = len(cnpj) == DIGITOS_DO_CNPJ or str(linha.get("auditor_id", "")).startswith(
        "rede:"
    )
    if not firma or _e_pessoa(linha["auditor"], pessoas):
        return AUDITOR_PESSOA
    return str(linha["auditor"])


def _itens_do_auditor(
    auditores: pd.DataFrame, pessoas: set[str]
) -> list[dict[str, Any]]:
    if auditores.empty:
        return []
    em_curso = _mais_recente(auditores)
    em_curso = em_curso[em_curso["fim"].isna()].sort_values("inicio")
    if em_curso.empty:
        return []
    atual = em_curso.iloc[-1]
    base = _data(atual["referencia"])
    return [
        _item(
            "auditor_atual",
            "Auditor atual",
            _nome_do_auditor(atual, pessoas),
            "texto",
            base,
        ),
        _item("auditor_desde", "Auditor desde", _data(atual["inicio"]), "data", base),
    ]


def _trocas_sem_pessoas(trocas: pd.DataFrame, pessoas: set[str]) -> pd.DataFrame:
    if trocas.empty:
        return trocas
    tabela = trocas[["efetiva_em", "anterior", "novo", "anos_com_o_anterior"]].copy()
    for coluna in ("anterior", "novo"):
        tabela[coluna] = tabela[coluna].map(
            lambda nome: AUDITOR_PESSOA if _e_pessoa(nome, pessoas) else nome
        )
    return tabela.sort_values("efetiva_em", ascending=False)


def _e_controlada(sociedades: pd.DataFrame) -> pd.Series:
    """Controlada pelo tipo do FRE ou, quando o tipo vem vazio (os FREs recentes), por mais da metade."""
    tipo = sociedades["tipo"].fillna("").astype(str).str.strip().str.lower()
    participacao = pd.to_numeric(sociedades["participacao"], errors="coerce")
    return (tipo == "controlada") | (
        (tipo == "") & (participacao > PARTICIPACAO_DE_CONTROLE)
    )


def cnpjs_do_grupo(cnpj: str, controladas: pd.DataFrame) -> set[str]:
    """A companhia e as controladas do FRE mais recente (só dígitos): quem emite pelo grupo."""
    ultimas = _mais_recente(controladas)
    if ultimas.empty:
        return {cnpj}
    das_controladas = digitos(ultimas.loc[_e_controlada(ultimas), "cnpj"].dropna())
    return {cnpj, *(c for c in das_controladas if len(c) == DIGITOS_DO_CNPJ)}


def _controladas_do_ultimo_fre(
    controladas: pd.DataFrame,
) -> tuple[pd.DataFrame, str | None]:
    ultimas = _mais_recente(controladas)
    if ultimas.empty:
        return ultimas, None
    tabela = (
        ultimas[["razao_social", "tipo", "participacao"]]
        .assign(controlada=_e_controlada(ultimas))
        .sort_values("participacao", ascending=False)
    )
    return tabela, _data(ultimas["referencia"].iloc[0])


def secao_auditor_e_controladas(
    auditores: pd.DataFrame,
    trocas: pd.DataFrame,
    controladas: pd.DataFrame,
    controladoras_da_empresa: pd.DataFrame,
    pessoas: set[str],
) -> dict[str, Any] | None:
    """Quem audita, as trocas de auditor, as controladas e coligadas e quem controla (None: nada)."""
    itens = _itens_do_auditor(auditores, pessoas)
    tabela_de_controladas, base = _controladas_do_ultimo_fre(controladas)
    if not tabela_de_controladas.empty:
        sao_controladas = int(tabela_de_controladas["controlada"].sum())
        total = len(tabela_de_controladas)
        itens += [
            _item("sociedades", "Sociedades no FRE", total, "empresas", base),
            _item("controladas", "Controladas", sao_controladas, "empresas", base),
            _item(
                "coligadas_e_outras",
                "Coligadas e outras participações",
                total - sao_controladas,
                "empresas",
                base,
            ),
        ]
    tabelas = {
        "trocas_de_auditor": _trocas_sem_pessoas(trocas, pessoas),
        "controladas": tabela_de_controladas,
        "controladoras": controladoras_da_empresa.drop(columns="cnpj", errors="ignore"),
    }
    if not itens and all(t.empty for t in tabelas.values()):
        return None
    return _secao("auditor_e_controladas", itens, tabelas)


def controladoras(
    ligacoes: pd.DataFrame, entidades: pd.DataFrame, identificadores: pd.DataFrame
) -> pd.DataFrame:
    """Quem controla cada companhia hoje pela rede (FRE da controladora): cnpj, controladora, participação.

    Só ligações vigentes; nenhuma entidade tratada como pessoa. Sem datas de fim: o `ate` da rede ainda
    pode olhar o futuro (achado na Ultrapar), e aqui só importa a situação de hoje.
    """
    cnpjs = identificadores[
        (identificadores["sistema"] == "cnpj") & identificadores["ate"].isna()
    ][["id_entidade", "valor"]].rename(columns={"id_entidade": "de", "valor": "cnpj"})
    cnpjs_das_controladoras = cnpjs.rename(
        columns={"de": "para", "cnpj": "cnpj_controladora"}
    )
    vigentes = ligacoes[
        (ligacoes["tipo"] == "controlada_de")
        & (ligacoes["situacao"] == "vigente")
        & (ligacoes["fonte"] == "cvm-fre")
    ]
    nomes = entidades[~entidades["trata_como_pessoa"].fillna(True).astype(bool)][
        ["id_entidade", "nome"]
    ].rename(columns={"id_entidade": "para", "nome": "controladora"})
    tabela = (
        vigentes.merge(cnpjs, on="de")
        .merge(nomes, on="para")
        .merge(cnpjs_das_controladoras, on="para", how="left")
    )
    return tabela[
        ["cnpj", "controladora", "participacao", "cnpj_controladora"]
    ].reset_index(drop=True)


def controladoras_em_dia(
    controladoras: pd.DataFrame, controladas: pd.DataFrame, hoje: pd.Timestamp
) -> pd.DataFrame:
    """Só as controladoras cujo FRE mais recente é dos últimos anos e ainda lista a empresa como controlada.

    A rede guarda a ligação como vigente enquanto ninguém a encerra: a controladora que parou de
    entregar o FRE (a VBC Energia, que deixou a CPFL em 2011) continuaria aparecendo como dona hoje.
    """
    if controladoras.empty or controladas.empty:
        return pd.DataFrame(columns=["cnpj", "controladora", "participacao"])
    limite = hoje.tz_localize(None) - pd.DateOffset(years=ANOS_DO_FRE_EM_DIA)
    listadas = set()
    for cnpj_controladora, fres in controladas.groupby(
        digitos(controladas["cnpj_companhia"])
    ):
        ultimo = _mais_recente(fres)
        if ultimo.empty or pd.Timestamp(ultimo["referencia"].iloc[0]) < limite:
            continue
        como_controlada = ultimo[_e_controlada(ultimo)]
        listadas |= {
            (str(cnpj_controladora), c)
            for c in digitos(como_controlada["cnpj"].dropna())
        }
    pares = zip(
        controladoras["cnpj_controladora"], digitos(controladoras["cnpj"]), strict=True
    )
    em_dia = [
        isinstance(dona, str) and (re.sub(r"\D", "", dona), empresa) in listadas
        for dona, empresa in pares
    ]
    return controladoras.loc[
        em_dia, ["cnpj", "controladora", "participacao"]
    ].reset_index(drop=True)


# --- ofertas e fundos ----------------------------------------------------------------------------


def _numero(valores: pd.Series) -> pd.Series:
    return pd.to_numeric(valores, errors="coerce")


def _ofertas(ofertas_160: pd.DataFrame, ofertas_antigas: pd.DataFrame) -> pd.DataFrame:
    """As ofertas das duas tabelas da CVM numa só, da mais nova para a mais velha."""
    partes = []
    if not ofertas_160.empty:
        partes.append(
            pd.DataFrame(
                {
                    "data": ofertas_160["data_registro"].fillna(
                        ofertas_160["data_requerimento"]
                    ),
                    "regime": "Res. 160",
                    "emissor": ofertas_160.get("nome_emissor"),
                    "valor_mobiliario": ofertas_160["valor_mobiliario"],
                    "tipo_oferta": ofertas_160["tipo_oferta"],
                    "valor_total": _numero(ofertas_160["valor_total_registrado"]),
                    "situacao": ofertas_160["status_requerimento"],
                }
            )
        )
    if not ofertas_antigas.empty:
        partes.append(
            pd.DataFrame(
                {
                    "data": ofertas_antigas["data_registro_oferta"].fillna(
                        ofertas_antigas["data_protocolo"]
                    ),
                    "regime": "anterior à Res. 160",
                    "emissor": ofertas_antigas.get("nome_emissor"),
                    "valor_mobiliario": ofertas_antigas["tipo_ativo"],
                    "tipo_oferta": ofertas_antigas["tipo_oferta"],
                    "valor_total": _numero(ofertas_antigas["valor_total"]),
                    "situacao": None,
                }
            )
        )
    if not partes:
        return pd.DataFrame()
    juntas = pd.concat(partes, ignore_index=True)
    juntas["data"] = pd.to_datetime(juntas["data"])
    return juntas.sort_values("data", ascending=False, ignore_index=True)


def _ofertas_por_ano(ofertas: pd.DataFrame) -> pd.DataFrame:
    if ofertas.empty:
        return ofertas
    por_ano = ofertas.groupby(ofertas["data"].dt.year.rename("ano")).agg(
        ofertas=("regime", "size"), valor_total=("valor_total", "sum")
    )
    return (
        por_ano.reset_index().sort_values("ano", ascending=False).head(ANOS_NAS_SERIES)
    )


def ultimo_mes_completo(cobertura: pd.DataFrame) -> pd.Timestamp | None:
    """O último mês do CDA com as carteiras já entregues (None: sem a tabela de cobertura).

    Os fundos entregam a carteira com até 90 dias de atraso, então os meses mais novos ainda crescem.
    Só o rabo da série é cortado: do fim para trás, sai cada mês com menos de 60% da mediana dos 12
    anteriores. Uma queda no meio da série (crise de mercado) não é carteira faltando.
    """
    if cobertura.empty:
        return None
    serie = cobertura.sort_values("competencia").reset_index(drop=True)
    valores = pd.to_numeric(serie["valor_comprado"], errors="coerce")
    for posicao in range(len(serie) - 1, -1, -1):
        anteriores = valores.iloc[
            max(0, posicao - MESES_PARA_A_MEDIANA) : posicao
        ].dropna()
        if len(anteriores) < MESES_MINIMOS_NA_MEDIANA:
            return pd.Timestamp(serie["competencia"].iloc[posicao])
        if valores.iloc[posicao] >= FRACAO_DO_MES_COMPLETO * anteriores.median():
            return pd.Timestamp(serie["competencia"].iloc[posicao])
    return None


def _fundos(
    painel: pd.DataFrame, ultimo_mes: pd.Timestamp | None = None
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Quantos fundos têm a ação e quanto, no último mês completo, e a série dos últimos meses."""
    if painel.empty:
        return [], painel
    if ultimo_mes is not None:
        painel = painel[pd.to_datetime(painel["competencia"]) <= ultimo_mes]
    comprado = painel[painel["tipo"] == "comprado"].sort_values("competencia")
    if comprado.empty:
        return [], comprado
    ultimo = comprado.iloc[-1]
    base = _data(ultimo["competencia"])
    itens = [
        _item(
            "fundos_com_a_acao",
            "Fundos com a empresa na carteira",
            int(ultimo["fundos"]),
            "fundos",
            base,
        ),
        _item(
            "valor_nos_fundos",
            "Valor nas carteiras dos fundos",
            float(ultimo["valor"]),
            "R$",
            base,
        ),
    ]
    serie = comprado[["competencia", "fundos", "valor"]].tail(MESES_DOS_FUNDOS)
    return itens, serie


def secao_ofertas_e_fundos(
    ofertas_160: pd.DataFrame,
    ofertas_antigas: pd.DataFrame,
    painel: pd.DataFrame,
    ultimo_mes_completo: pd.Timestamp | None = None,
) -> dict[str, Any] | None:
    """As ofertas registradas na CVM e os fundos que têm a empresa na carteira (None: nada)."""
    ofertas = _ofertas(ofertas_160, ofertas_antigas)
    itens, fundos_por_mes = _fundos(painel, ultimo_mes_completo)
    if ofertas.empty and not itens:
        return None
    if not ofertas.empty:
        itens.insert(
            0,
            _item(
                "ofertas",
                "Ofertas registradas na CVM",
                len(ofertas),
                "ofertas",
                _data(ofertas["data"].max()),
            ),
        )
    tabelas = {
        "ofertas": ofertas.head(LINHAS_NAS_LISTAS),
        "ofertas_por_ano": _ofertas_por_ano(ofertas),
        "fundos_por_mes": fundos_por_mes,
    }
    return _secao("ofertas_e_fundos", itens, tabelas)


# --- setor regulado ------------------------------------------------------------------------------


def serie_anual(tabela: pd.DataFrame, modo: str) -> pd.DataFrame:
    """De (competencia, chave, valor) por mês para (ano, chave, valor) por ano.

    `SOMA_DO_ANO` soma os meses (passageiros, prêmios); `ULTIMO_MES` fica com o último mês que a fonte
    tem em cada ano (consumidores, acessos: um estoque, que não se soma).
    """
    ano = tabela["competencia"].dt.year
    # quantos meses a fonte tem em cada ano e qual o último: o ano corrente ainda está pela metade
    meses = tabela.groupby(ano)["competencia"].agg(meses="nunique", ultimo_mes="max")
    if modo == ULTIMO_MES:
        ultimo = tabela.groupby(ano)["competencia"].transform("max")
        tabela, ano = (
            tabela[tabela["competencia"] == ultimo],
            ano[tabela["competencia"] == ultimo],
        )
    somada = tabela.groupby([ano.rename("ano"), "chave"])["valor"].sum().reset_index()
    return somada.merge(meses.rename_axis("ano").reset_index(), on="ano")


def _chaves(ligacoes: pd.DataFrame, serie: SerieDaAgencia) -> set[str]:
    principais = ligacoes[
        (ligacoes["fonte"] == serie.fonte_b13) & ligacoes["principal"]
    ]
    valores = principais["chave"].astype(str).str.strip()
    return set(digitos(valores) if serie.chave_em_digitos else valores)


def _participacao_por_ano(dados: pd.DataFrame, chaves: set[str]) -> pd.DataFrame:
    dados = dados.assign(chave=dados["chave"].astype(str).str.strip())
    total = dados.groupby("ano")["valor"].sum()
    da_empresa = dados[dados["chave"].isin(chaves)].groupby("ano")["valor"].sum()
    # só os anos em que a empresa tem número: a divisão alinharia com todos os anos do mercado
    tabela = pd.DataFrame(
        {"valor": da_empresa, "participacao": da_empresa / total}
    ).dropna(subset=["valor"])
    periodo = dados.groupby("ano")[["meses", "ultimo_mes"]].first()
    tabela = tabela.join(periodo)
    return (
        tabela.reset_index().sort_values("ano", ascending=False).head(ANOS_NAS_SERIES)
    )


def _entidades_ligadas(ligacoes: pd.DataFrame) -> pd.DataFrame:
    principais = ligacoes[ligacoes["principal"]]
    return principais[["fonte", "nome", "via", "desde"]].sort_values(["fonte", "nome"])


def _item_da_serie(serie: SerieDaAgencia, tabela: pd.DataFrame) -> dict[str, Any]:
    """O número do item: o último mês (estoque) ou o último ano completo (soma; o corrente engana)."""
    if serie.modo == ULTIMO_MES:
        linha = tabela.iloc[0]
        base = pd.Timestamp(linha["ultimo_mes"]).strftime("%Y-%m")
    else:
        completos = tabela[tabela["meses"] == MESES_NO_ANO]
        linha = completos.iloc[0] if not completos.empty else tabela.iloc[0]
        base = str(int(linha["ano"]))
    return _item(serie.nome, serie.medida, float(linha["valor"]), serie.unidade, base)


def secao_setor_regulado(
    ligacoes_b13: pd.DataFrame, series: Mapping[str, pd.DataFrame]
) -> dict[str, Any] | None:
    """Os números da agência que regula a empresa, somadas as entidades dela (None: sem agência).

    `ligacoes_b13` são as linhas de `empresa_serie` da companhia; `series`, por `SerieDaAgencia.nome`,
    (ano, chave, valor) de todo o mercado, para a participação.
    """
    if ligacoes_b13.empty:
        return None
    itens, tabelas = [], {}
    for serie in SERIES_DAS_AGENCIAS:
        chaves = _chaves(ligacoes_b13, serie)
        dados = series.get(serie.nome)
        if not chaves or dados is None or dados.empty:
            continue
        tabela = _participacao_por_ano(dados, chaves)
        if tabela.empty:
            continue
        tabelas[serie.nome] = tabela
        itens.append(_item_da_serie(serie, tabela))
    if not tabelas:
        return None
    tabelas["entidades_ligadas"] = _entidades_ligadas(ligacoes_b13)
    return _secao(
        "setor_regulado", itens, tabelas, fontes=fontes_do_setor(tabelas.keys())
    )


# --- negócios ------------------------------------------------------------------------------------


def secao_negocios(eventos: pd.DataFrame) -> dict[str, Any] | None:
    """Fatos relevantes e comunicados de compra, venda, fusão ou reorganização (None: nenhum)."""
    if eventos.empty:
        return None
    # a base guarda a data sem hora (`datetime.date`): vira data do pandas para ordenar e agrupar
    eventos = eventos.assign(publicado_em=pd.to_datetime(eventos["publicado_em"]))
    assunto = eventos["assunto"].fillna("").map(normalizar_nome)
    negocios = eventos[
        eventos["rotulo"].isin(ROTULOS_DE_NEGOCIO)
        & assunto.str.contains(PALAVRAS_DE_NEGOCIO)
    ].sort_values("publicado_em", ascending=False)
    if negocios.empty:
        return None
    por_ano = (
        negocios.groupby(negocios["publicado_em"].dt.year.rename("ano"))
        .size()
        .rename("documentos")
        .reset_index()
        .sort_values("ano", ascending=False)
        .head(ANOS_NAS_SERIES)
    )
    base = _data(negocios["publicado_em"].iloc[0])
    itens = [
        _item(
            "negocios",
            "Documentos de negócios na CVM",
            len(negocios),
            "documentos",
            base,
        )
    ]
    tabelas = {
        "negocios": negocios[["publicado_em", "rotulo", "assunto", "link"]].head(
            LINHAS_NAS_LISTAS
        ),
        "negocios_por_ano": por_ano,
    }
    return _secao("negocios", itens, tabelas)


# --- ligações na rede (molde B: a busca por CNPJ, plano de 19/10/2026) ---------------------------


class Relacao(NamedTuple):
    """O que a outra ponta de uma ligação é para a empresa da ficha."""

    chave: str  # do item com a contagem
    tipo: str
    empresa_em_de: bool  # a empresa da ficha é a ponta `de` da ligação
    nome: str


RELACOES = (
    Relacao("controladas", CONTROLADA_DE, False, "Controlada"),
    Relacao("controladoras", CONTROLADA_DE, True, "Controladora"),
    Relacao("coligadas", COLIGADA_DE, False, "Coligada"),
    Relacao("coligada_de", COLIGADA_DE, True, "Tem a companhia como coligada"),
    Relacao("participacoes", PARTICIPADA_DE, False, "Participação da companhia"),
    Relacao("participam", PARTICIPADA_DE, True, "Tem participação na companhia"),
    Relacao("auditor", AUDITA, False, "Auditor"),
    Relacao(
        "instituicoes_do_conglomerado",
        DO_CONGLOMERADO_DE,
        False,
        "Instituição do conglomerado",
    ),
    Relacao("lider_do_conglomerado", DO_CONGLOMERADO_DE, True, "Líder do conglomerado"),
)
_RELACAO = {(r.tipo, r.empresa_em_de): r for r in RELACOES}
TIPOS_DO_FRE = frozenset({CONTROLADA_DE, COLIGADA_DE, PARTICIPADA_DE})
# só estes tipos saem (nenhum de pessoa nem negativo); `emite` entra só como contagem
TIPOS_DA_REDE = frozenset({*(r.tipo for r in RELACOES), EMITE})
# a família da licença e o documento de cada fonte de ligação; fonte fora daqui não sai (`opera_para`
# já está no setor regulado; uma fonte nova só entra quando alguém a põe aqui)
FONTES_DA_REDE = {
    "cvm-fre": ("cvm", "Formulário de Referência (CVM)"),
    "cvm-fca": ("cvm", "Formulário Cadastral (CVM)"),
    "cvm-cda": ("cvm", "Carteiras dos fundos (CVM)"),
    "bcb-ifdata": ("bcb", "IF.data (Banco Central)"),
}
# os identificadores públicos da empresa que saem: a família da licença e o nome na tela
IDENTIFICADORES_DA_EMPRESA = {
    "cnpj": ("cvm", "CNPJ"),
    "ticker": ("cvm", "Ticker"),
    "emissor": ("cvm", "Código do emissor"),
    "lei": ("gleif", "LEI (GLEIF)"),
    "codigo_bcb_ifdata": ("bcb", "Código no IF.data (Banco Central)"),
}
SISTEMAS_DA_REDE = (*IDENTIFICADORES_DA_EMPRESA, "cnpj_raiz")  # o que a noite lê
SECOES_DO_MOLDE_B = frozenset(
    {"rede"}
)  # o relatório da empresa (molde A) não as mostra


@dataclass(frozen=True)
class RedeDaNoite:
    """A rede pronta para as fichas: só o que pode sair, já separado por entidade."""

    centros: dict[str, str]  # raiz do CNPJ → id_entidade
    ligacoes: dict[str, pd.DataFrame]  # id_entidade → as ligações dele que podem sair
    identificadores: dict[
        str, pd.DataFrame
    ]  # id_entidade → os identificadores que saem
    nomes: dict[str, str]
    cnpjs: dict[str, str]


def _sem_fuso(quando: pd.Timestamp) -> pd.Timestamp:
    return quando.tz_localize(None) if quando.tzinfo else quando


def _pode_mostrar_a_familia(familia: object) -> bool:
    return isinstance(familia, str) and pode_usar(MOSTRAR, familia)  # sem família: NaN


def raizes_do_fre_em_dia(
    controladas: pd.DataFrame, hoje: pd.Timestamp
) -> set[tuple[str, str]]:
    """(raiz da companhia, raiz da sociedade) de cada FRE mais recente dos últimos anos, público hoje.

    A rede guarda a ligação do FRE como vigente enquanto ninguém a encerra: a companhia que parou de
    entregar (a VBC Energia, que deixou a CPFL em 2011) continuaria dona hoje.
    """
    if controladas.empty or "conhecido_em" not in controladas.columns:
        return set()  # sem a data de entrega não dá para saber o que já era público
    hoje = _sem_fuso(hoje)
    publicos = controladas[pd.to_datetime(controladas["conhecido_em"]) <= hoje]
    limite = hoje - pd.DateOffset(years=ANOS_DO_FRE_EM_DIA)
    pares: set[tuple[str, str]] = set()
    for companhia, fres in publicos.groupby(publicos["cnpj_companhia"].map(raiz)):
        ultimo = _mais_recente(fres)
        if ultimo.empty or pd.Timestamp(ultimo["referencia"].iloc[0]) < limite:
            continue
        pares |= {(str(companhia), r) for r in ultimo["cnpj"].dropna().map(raiz) if r}
    return pares


def _raizes(identificadores: pd.DataFrame) -> pd.Series:
    """A raiz do CNPJ de cada entidade (pela raiz da rede ou pelo CNPJ inteiro)."""
    pela_raiz = identificadores[identificadores["sistema"] == "cnpj_raiz"]
    pelo_cnpj = identificadores[identificadores["sistema"] == "cnpj"]
    juntas = pd.concat(
        [
            pela_raiz.assign(raiz=pela_raiz["valor"]),
            pelo_cnpj.assign(raiz=pelo_cnpj["valor"].map(raiz)),
        ]
    ).dropna(subset=["raiz"])
    return juntas.drop_duplicates("id_entidade").set_index("id_entidade")["raiz"]


def _centros(identificadores: pd.DataFrame) -> dict[str, str]:
    """Raiz → entidade, só quando a raiz aponta para uma entidade só."""
    raizes = identificadores[identificadores["sistema"] == "cnpj_raiz"]
    unicas = raizes.drop_duplicates(["valor", "id_entidade"])
    unicas = unicas[~unicas["valor"].duplicated(keep=False)]
    return dict(zip(unicas["valor"], unicas["id_entidade"], strict=True))


def _ligacoes_que_podem_sair(
    ligacoes: pd.DataFrame, empresas: set[str]
) -> pd.DataFrame:
    """Os tipos da rede, de fonte conhecida que pode ser mostrada, entre empresas (nunca pessoas)."""
    familias = ligacoes["fonte"].map(lambda f: FONTES_DA_REDE.get(f, (None, ""))[0])
    entre_empresas = ligacoes["de"].isin(empresas) & (
        ligacoes["para"].isin(empresas) | (ligacoes["tipo"] == EMITE)
    )
    return ligacoes[
        ligacoes["tipo"].isin(TIPOS_DA_REDE)
        & familias.map(_pode_mostrar_a_familia).astype(bool)
        & entre_empresas
    ]


def _do_fre_em_dia(
    ligacoes: pd.DataFrame, raizes: pd.Series, pares: set[tuple[str, str]]
) -> pd.Series:
    """A ligação não é do FRE, ou o FRE em dia da companhia (`para`) ainda lista a sociedade (`de`)."""
    par = zip(ligacoes["para"].map(raizes), ligacoes["de"].map(raizes), strict=True)
    listada = pd.Series([p in pares for p in par], index=ligacoes.index, dtype=bool)
    return ~ligacoes["tipo"].isin(TIPOS_DO_FRE) | listada


def _por_entidade(ligacoes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """As ligações de cada entidade, como `de` ou como `para`."""
    por_de = {str(e): g for e, g in ligacoes.groupby("de")}
    por_para = {str(e): g for e, g in ligacoes.groupby("para")}
    vazia = ligacoes.iloc[0:0]
    return {
        e: pd.concat([por_de.get(e, vazia), por_para.get(e, vazia)])
        for e in por_de.keys() | por_para.keys()
    }


def _identificadores_que_saem(
    identificadores: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    familias = identificadores["sistema"].map(
        lambda s: IDENTIFICADORES_DA_EMPRESA.get(s, (None, ""))[0]
    )
    saem = identificadores[familias.map(_pode_mostrar_a_familia).astype(bool)]
    return {str(e): g for e, g in saem.groupby("id_entidade")}


def preparar_rede(
    ligacoes: pd.DataFrame,
    entidades: pd.DataFrame,
    identificadores: pd.DataFrame,
    controladas: pd.DataFrame,
    hoje: pd.Timestamp,
) -> RedeDaNoite:
    """A rede como era em `hoje` (a porta já cortou o futuro), sem pessoa nem tipo negativo.

    Montada uma vez por noite. Entidade fora da rede conta como pessoa (o conservador); a ligação do
    FRE só fica se o FRE em dia ainda a mostra (`raizes_do_fre_em_dia`).
    """
    if ligacoes.empty or entidades.empty or identificadores.empty:
        return RedeDaNoite(
            {}, {}, {}, {}, {}
        )  # a rede ainda não foi montada nesta base
    publicadas, _ = vista_publicada(ligacoes, entidades)
    empresas = entidades[~entidades["trata_como_pessoa"].fillna(True).astype(bool)]
    nomes = {
        str(e): str(n)
        for e, n in zip(empresas["id_entidade"], empresas["nome"], strict=True)
    }
    podem = _ligacoes_que_podem_sair(publicadas, set(nomes))
    pares = raizes_do_fre_em_dia(controladas, hoje)
    podem = podem[_do_fre_em_dia(podem, _raizes(identificadores), pares)]
    cnpjs = identificadores[identificadores["sistema"] == "cnpj"].drop_duplicates(
        "id_entidade"
    )
    return RedeDaNoite(
        centros=_centros(identificadores),
        ligacoes=_por_entidade(podem),
        identificadores=_identificadores_que_saem(identificadores),
        nomes=nomes,
        cnpjs=dict(zip(cnpjs["id_entidade"], cnpjs["valor"], strict=True)),
    )


def _cnpj_formatado(cnpj: str | None) -> str | None:
    return formatar(cnpj) if cnpj and len(cnpj) == DIGITOS_DO_CNPJ else None


_COLUNAS_DAS_LIGACOES = (
    "ordem",
    "chave",
    "relacao",
    "entidade",
    "cnpj",
    "participacao",
    "desde",
    "documento",
    "familia",
)
_COLUNAS_DOS_IDENTIFICADORES = ("identificador", "valor", "desde", "familia")


def _linhas_da_rede(
    centro: str, ligacoes: pd.DataFrame, rede: RedeDaNoite
) -> pd.DataFrame:
    """Uma linha por ligação: o que a outra ponta é para a empresa, com o documento que a mostra."""
    linhas = []
    for ligacao in ligacoes.itertuples(index=False):
        em_de = ligacao.de == centro
        relacao = _RELACAO.get((str(ligacao.tipo), em_de))
        outra = str(ligacao.para if em_de else ligacao.de)
        if relacao is None or outra == centro:
            continue
        familia, documento = FONTES_DA_REDE[str(ligacao.fonte)]
        linhas.append(
            {
                "ordem": RELACOES.index(relacao),
                "chave": relacao.chave,
                "relacao": relacao.nome,
                "entidade": rede.nomes[outra],
                "cnpj": _cnpj_formatado(rede.cnpjs.get(outra)),
                "participacao": ligacao.participacao,
                "desde": ligacao.aconteceu_em,
                "documento": documento,
                "familia": familia,
            }
        )
    return pd.DataFrame(linhas, columns=list(_COLUNAS_DAS_LIGACOES))


def _mostradas(linhas: pd.DataFrame) -> pd.DataFrame:
    """Até `LINHAS_NAS_LISTAS` por relação, as de maior participação primeiro."""
    if linhas.empty:
        return linhas
    ordenadas = linhas.sort_values(
        ["ordem", "participacao", "entidade"],
        ascending=[True, False, True],
        na_position="last",
    )
    return (
        ordenadas.groupby("chave", sort=False)
        .head(LINHAS_NAS_LISTAS)
        .drop(columns=["ordem", "chave", "familia"])
    )


def _tabela_dos_identificadores(identificadores: pd.DataFrame | None) -> pd.DataFrame:
    if identificadores is None:
        return pd.DataFrame(columns=list(_COLUNAS_DOS_IDENTIFICADORES))
    ordem = list(IDENTIFICADORES_DA_EMPRESA)
    tabela = identificadores.assign(
        ordem=identificadores["sistema"].map(ordem.index)
    ).sort_values(["ordem", "valor"])
    return pd.DataFrame(
        {
            "identificador": tabela["sistema"].map(
                lambda s: IDENTIFICADORES_DA_EMPRESA[s][1]
            ),
            "valor": [
                _cnpj_formatado(v) if s == "cnpj" else v
                for s, v in zip(tabela["sistema"], tabela["valor"], strict=True)
            ],
            "desde": tabela["desde"],
            "familia": tabela["sistema"].map(
                lambda s: IDENTIFICADORES_DA_EMPRESA[s][0]
            ),
        }
    )


def _itens_da_rede(linhas: pd.DataFrame, emitidos: int) -> list[dict[str, Any]]:
    itens = [_item("ligacoes", "Ligações na rede", len(linhas), "empresas", None)]
    contagem = linhas["chave"].value_counts() if not linhas.empty else pd.Series()
    itens += [
        _item(r.chave, r.nome, int(contagem[r.chave]), "empresas", None)
        for r in RELACOES
        if r.chave in contagem
    ]
    if emitidos:
        itens.append(
            _item(
                "valores_mobiliarios",
                "Valores mobiliários nas carteiras dos fundos",
                emitidos,
                "valores mobiliários",
                None,
            )
        )
    return itens


def secao_rede(cnpj: str, rede: RedeDaNoite) -> dict[str, Any] | None:
    """O que a companhia é na rede: controladas, donas, coligadas, auditor e conglomerado (None: nada).

    Cada relação mostra até `LINHAS_NAS_LISTAS` entidades; a contagem é toda. Os valores mobiliários
    entram só como contagem.
    """
    centro = rede.centros.get(raiz(cnpj) or "")
    if centro is None or centro not in rede.ligacoes:
        return None
    ligacoes = rede.ligacoes[centro]
    emite = (ligacoes["tipo"] == EMITE) & (ligacoes["de"] == centro)
    emitidos = int(ligacoes.loc[emite, "para"].nunique())
    linhas = _linhas_da_rede(centro, ligacoes[ligacoes["tipo"] != EMITE], rede)
    if linhas.empty and not emitidos:
        return None
    identificadores = _tabela_dos_identificadores(rede.identificadores.get(centro))
    familias = {*linhas["familia"], *identificadores["familia"]}
    if emitidos:
        familias.add(FONTES_DA_REDE["cvm-cda"][0])
    tabelas = {
        "ligacoes_da_rede": _mostradas(linhas),
        "identificadores_da_empresa": identificadores.drop(
            columns="familia", errors="ignore"
        ),
    }
    fontes = sorted({licenca_da_fonte(f) for f in familias})
    return _secao("rede", _itens_da_rede(linhas, emitidos), tabelas, fontes=fontes)


# --- a ficha e o filtro de pessoas ---------------------------------------------------------------


def montar_ficha(
    cnpj: str, empresa: str, secoes: Iterable[dict[str, Any] | None], gerado_em: str
) -> dict[str, Any]:
    """A ficha de uma companhia: o esquema, quem é e as seções que existem, na ordem de `SECOES`."""
    return {
        "versao_do_esquema": VERSAO_DO_ESQUEMA,
        "cnpj": cnpj,
        "empresa": empresa,
        "gerado_em": gerado_em,
        "secoes": [secao for secao in secoes if secao is not None],
    }


def _textos_e_chaves(valor: object) -> Iterable[tuple[str, str]]:
    """Cada texto da ficha, com o tipo ("texto" ou "coluna"), percorrendo listas e dicionários."""
    if isinstance(valor, dict):
        for chave, dentro in valor.items():
            yield "coluna", str(chave)
            yield from _textos_e_chaves(dentro)
    elif isinstance(valor, list):
        for dentro in valor:
            yield from _textos_e_chaves(dentro)
    elif isinstance(valor, str):
        yield "texto", valor


def conferir_sem_pessoas(ficha: Mapping[str, Any], pessoas: set[str]) -> None:
    """Levanta `PessoaNaFichaError` se a ficha tem CPF, nome de pessoa (já normalizado) ou coluna de pessoa."""
    for tipo, texto in _textos_e_chaves(ficha):
        if tipo == "coluna":
            if texto in COLUNAS_DE_PESSOA:
                raise PessoaNaFichaError(f"coluna de pessoa na ficha: {texto}")
        elif CPF.search(texto):
            raise PessoaNaFichaError("CPF na ficha")
        elif normalizar_nome(texto) in pessoas:
            raise PessoaNaFichaError("nome de pessoa na ficha")
