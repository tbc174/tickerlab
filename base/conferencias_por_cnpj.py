"""As conferências por CNPJ que a ficha do Ficha Clara mostra (linha 525 da fila; Ficha Clara, etapa 6).

Um arquivo SQLite só de leitura, montado em casa a partir das tabelas da base, para o portal abrir sem DuckDB
nem Parquet (o mesmo jeito dos contratos do PNCP). Uma seção por tema na ficha, e cada fonte diz o que é:
- **consta**: a raiz tem linhas vigentes na fonte (`registros`, até `LINHAS_POR_FONTE`, as mais novas antes);
- **não consta**: a fonte está no arquivo (`meta.estado`, com a data até onde foi conferida) e a raiz não;
- **não conferido**: a fonte não está no arquivo. A ficha nunca confunde isso com "não consta".

**Vigente.** Nas tabelas de retratos (sanções, licenças, incentivos e financiamentos), o valor mais novo de cada registro já
público no dia da montagem (`como_era_em`) e só se ainda consta na fonte. Na dívida ativa, o retrato mais novo
já público de cada tipo de dívida. Nada do futuro: a linha que ainda não era pública fica de fora.

**Financiamentos.** O histórico de contratações do BNDES e da Finep (linha 469): cada operação com o valor
contratado e o desembolsado como a fonte divulga, em texto exato ("250.04"), nunca somados nem tomados por
saldo; a liquidada continua (é o histórico), com a situação ao lado. Uma fonte por banco, cada uma com a sua
licença (`licenca` no estado: a do BNDES é ODbL e pede a atribuição).

**Preços da CMED.** As duas listas de preços máximos (`cmed_precos`), cada uma uma fonte: `consumidor` (PF e
PMC) e `governo` (PF e PMVG). Uma linha por apresentação com o CNPJ inteiro (a filial não se mistura dentro da
raiz), os preços sem impostos e com ICMS de 0% em texto exato (os de cada alíquota ficam na base), as marcas e as
datas; `total` conta as apresentações. É teto regulatório, não preço praticado nem faturamento; e "vigente na
lista" não quer dizer "registro ativo na Anvisa": a situação sanitária não é conferida aqui. A licença própria
das listas está a confirmar (é a do `licenca` da fonte).

**Sem pessoa física.** A linha marcada `trata_como_pessoa` (empresário individual e MEI, ADR 0075) não entra,
nem coluna de texto livre que possa levar nome (assunto, origem da informação, complemento). A ficha também não
mostra estas seções para empresário individual e MEI, para não dizer nada da pessoa nem pela ausência.

**Grupo.** As ligações por sócia pessoa jurídica do QSA vigente da vista do CNPJ (`base/rede/grupo_do_qsa.py`),
para o portal andar o grupo do mesmo jeito; sem pessoa física, sem pseudônimo e sem nome.

**Processos judiciais** (plano dos processos de 03/11/2026, PR 4; ADR 0121). Só o DJEN do CNJ (`base/processos.py`),
nunca o DataJud (só uso interno). Duas fontes: `processos` (cada processo em que a companhia é parte, com
tribunal, órgão, classe, ramo, o polo e o dia da primeira comunicação que a liga a ele, o dia da comunicação mais
nova e a certidão oficial dela no DJEN) e `processos_por_ano` (as contagens de `processos.contagens`: por ano da
ligação, polo e ramo). Sem o nome das partes, sem advogados e sem o link do tribunal. `conferido_ate` é o dia da
comunicação mais nova vista: a ficha diz "não encontrado até" esse dia, nunca que a empresa não tem processos (ADR
0103). Com o cadastro da CVM (`montar(cadastro=...)`), cada companhia com registro ativo no dia sem processo ganha
total 0 ("não encontrado até"); a empresa fora do cadastro fica sem linha (a ficha diz "não conferido"), e o
estado traz quantas foram `buscadas`. Limites: só companhias abertas, ligadas pelo nome; só o que saiu no DJEN
desde 2025; sem segredo de justiça, sem STF e sem a Justiça do Trabalho.
"""

import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pandas as pd

from base import processos, tpu
from base.dicionario import TABELAS
from base.parquet import gravar_atomico
from base.porta import Porta, vista_do_cnpj
from base.porta.duckdb import nome_da_view
from base.porta.rede import views
from base.rede import grupo_do_qsa
from src.banco.coletas import licenca_da_fonte

ESQUEMA = "1"  # o portal recusa outro: campo novo só entra com o contrato da integração
LINHAS_POR_FONTE = 50  # por raiz e fonte; `total` diz quantas há
TEMAS = {
    "sinais": "Sanções, penalidades e dívida ativa",
    "licencas": "Licenças e registros",
    "incentivos": "Incentivos e benefícios",
    "financiamentos": "Financiamentos do BNDES e da Finep",
    "precos": "Preços máximos de medicamentos (CMED)",
    "processos": "Processos judiciais publicados no DJEN",
}
RAIZ_DA_FONTE = "raiz"  # a fonte só traz a raiz do CNPJ (o RDE-IED)
# a certidão de cada comunicação (o PDF oficial do DJEN): `<endereço>/<hash>/certidao`
CERTIDAO_DO_DJEN = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
_HASH_DO_DJEN = re.compile(r"[A-Za-z0-9]+")

_SANCOES = (
    "cadastro", "cnpj", "categoria", "situacao", "orgao", "uf_do_orgao", "esfera_do_orgao",
    "fundamentacao_legal", "abrangencia", "processo", "inicio", "fim", "publicado_em",
    "transito_em_julgado", "valor_multa",
)  # fmt: skip
_LICENCAS = (
    "cadastro", "cnpj", "registro", "categoria", "descricao", "situacao", "uf", "municipio",
    "concedido_em", "vence_em", "cancelado_em",
)  # fmt: skip
_FINANCIAMENTOS = (
    "cnpj", "modalidade", "contrato", "convenio_do_agente", "contratado_em", "valor_contratado",
    "valor_desembolsado", "contrapartida", "financiador", "forma_de_apoio", "produto",
    "custo_financeiro", "juros", "carencia_meses", "amortizacao_meses", "situacao", "situacao_classe",
    "uf",
)  # fmt: skip


def _cmed(maximo: str) -> tuple[str, ...]:
    """As colunas de uma lista da CMED na ficha: o PF e o preço máximo dela (`pmc` ou `pmvg`)."""
    return (
        "cnpj", "ggrem", "registro", "produto", "apresentacao", "substancia", "tipo_de_produto",
        "regime_de_preco", "pf_sem_impostos", "pf_0", f"{maximo}_sem_impostos", f"{maximo}_0",
        "precos_com_asterisco", "restricao_hospitalar", "cap", "confaz_87", "lista_publicada_em",
        "publico_desde",
    )  # fmt: skip


@dataclass(frozen=True)
class Fonte:
    """Uma tabela da base na ficha: o que mostrar dela e de onde ela vem."""

    tabela: str
    tema: str  # uma chave de `TEMAS`
    nome: str  # o que a ficha escreve
    orgao: str
    endereco: str  # a página pública da fonte, para conferir
    colunas: tuple[str, ...]  # só estas vão para o arquivo
    ordem: str  # a linha mais nova (ou maior) primeiro
    chave: str = "cnpj"  # "cnpj" (a raiz sai do CNPJ inteiro) ou `RAIZ_DA_FONTE`
    # só as linhas desta `lista` da tabela (a CMED: uma fonte por lista)
    lista: str = ""
    # a coluna que decide entre linhas de `ordem` igual (a ordem fica estável)
    desempate: str = ""
    # as outras tabelas que a fonte lê: sem alguma delas, a fonte fica "não conferida"
    outras: tuple[str, ...] = ()
    # o nome em `registros` quando não é o da tabela (duas fontes da mesma tabela)
    arquivo: str = ""
    # a montagem própria das linhas (raiz, colunas, em ordem) e do dia conferido; sem ela, as vigentes
    linhas: "Callable[[duckdb.DuckDBPyConnection, Fonte, date], tuple[pd.DataFrame, str | None]] | None" = None
    # a busca da fonte cobre as companhias com registro ativo na CVM (o DJEN busca pelo nome delas):
    # com o cadastro, a buscada sem linha ganha total 0; a de fora fica sem linha ("não conferido")
    so_companhias_abertas: bool = False

    @property
    def nome_no_arquivo(self) -> str:
        """Como a fonte aparece em `registros` e no estado: a tabela, e a lista quando há."""
        if self.arquivo:
            return self.arquivo
        return f"{self.tabela}_{self.lista}" if self.lista else self.tabela

    @property
    def lidas(self) -> tuple[str, ...]:
        """Todas as tabelas da base que a fonte lê."""
        return (self.tabela, *self.outras)


_PROCESSOS = (
    "cnpj", "numero_processo", "tribunal", "orgao", "classe", "ramo", "polo", "ligado_em",
    "ultima_comunicacao", "certidao",
)  # fmt: skip
_POR_ANO = (
    "ano",
    "processos",
    "como_autora",
    "como_re",
    *sorted(set(tpu.RAMOS.values())),
    "sem_ramo",
)


def certidao_do_djen(id_na_fonte: object) -> str | None:
    """A certidão da comunicação no DJEN (o PDF oficial) pelo hash dela; None sem hash: a comunicação
    guardada só com o id numérico não tem certidão por esse endereço, e o texto vem de fora (não vira
    caminho nem parâmetro). Só texto é hash: o vazio do merge (NaN) viraria "nan"."""
    texto = id_na_fonte if isinstance(id_na_fonte, str) else ""
    if not _HASH_DO_DJEN.fullmatch(texto) or texto.isdigit():
        return None
    return f"{CERTIDAO_DO_DJEN}/{texto}/certidao"


def _raiz(cnpj: pd.Series) -> pd.Series:
    return (
        cnpj.astype(str).str.upper().str.replace(r"[^0-9A-Z]", "", regex=True).str[:8]
    )


def _partes_das_companhias(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """As partes que são companhia (com CNPJ), na ordem em que ficaram públicas: a primeira ligação
    de cada processo sai de `processos.ligacoes`, a mesma regra das contagens."""
    return con.execute(
        "SELECT numero_processo, polo, tipo_parte, cnpj, CAST(disponivel_em AS DATE) AS disponivel_em "
        f"FROM {_view(processos.TABELA_DAS_PARTES)} "
        f"WHERE tipo_parte = '{processos.COMPANHIA}' AND cnpj IS NOT NULL "
        "ORDER BY disponivel_em, id_na_fonte"
    ).df()


def _processos_publicos(con: duckdb.DuckDBPyConnection, dia: str) -> pd.DataFrame:
    """Um processo por linha, já ligado a uma companhia no dia; a classe pela TPU, ou como o DJEN escreve."""
    return con.execute(
        "SELECT numero_processo, tribunal, orgao, coalesce(classe_tpu, classe) AS classe, ramo "
        f"FROM {_view(processos.TABELA_DOS_PROCESSOS)} WHERE CAST(disponivel_em AS DATE) <= {dia}"
    ).df()


def _ultimas_comunicacoes(con: duckdb.DuckDBPyConnection, dia: str) -> pd.DataFrame:
    """A comunicação mais nova de cada processo já pública no dia; a cancelada só se não há outra."""
    return con.execute(
        f"""
        SELECT numero_processo, id_na_fonte, CAST(disponivel_em AS DATE) AS ultima_comunicacao FROM (
            SELECT *, row_number() OVER (
                PARTITION BY numero_processo
                ORDER BY coalesce(CAST(cancelada_em AS DATE) <= {dia}, false),
                         disponivel_em DESC, visto_em DESC, id_na_fonte DESC
            ) AS n
            FROM {_view(processos.TABELA_DAS_COMUNICACOES)} WHERE CAST(disponivel_em AS DATE) <= {dia}
        ) WHERE n = 1
        """
    ).df()


def _conferido_no_djen(con: duckdb.DuckDBPyConnection, dia: str) -> str | None:
    """O dia da comunicação mais nova vista (a data da busca que a ficha mostra)."""
    linha = con.execute(
        f"SELECT max(CAST(visto_em AS DATE)) FROM {_view(processos.TABELA_DAS_COMUNICACOES)} "
        f"WHERE CAST(disponivel_em AS DATE) <= {dia}"
    ).fetchone()
    return linha[0].isoformat() if linha and linha[0] else None


def _linhas_dos_processos(
    con: duckdb.DuckDBPyConnection, fonte: "Fonte", hoje: date
) -> tuple[pd.DataFrame, str | None]:
    """Cada processo de cada raiz, com a comunicação mais nova primeiro."""
    dia = f"DATE '{hoje.isoformat()}'"
    ligadas = processos.ligacoes(_partes_das_companhias(con), hoje)
    ligadas = ligadas.assign(raiz=_raiz(ligadas["cnpj"])).drop_duplicates(
        ["raiz", "numero_processo"]
    )
    tabela = (
        ligadas.rename(columns={"disponivel_em": "ligado_em"})
        .merge(_processos_publicos(con, dia), on="numero_processo", how="left")
        .merge(_ultimas_comunicacoes(con, dia), on="numero_processo", how="left")
    )
    tabela = tabela.assign(certidao=tabela["id_na_fonte"].map(certidao_do_djen))
    tabela = tabela.sort_values(
        ["raiz", "ultima_comunicacao", "numero_processo"],
        ascending=[True, False, False],
        na_position="last",
        kind="stable",
    )
    return tabela[["raiz", *fonte.colunas]], _conferido_no_djen(con, dia)


def _linhas_por_ano(
    con: duckdb.DuckDBPyConnection, fonte: "Fonte", hoje: date
) -> tuple[pd.DataFrame, str | None]:
    """As contagens de `processos.contagens` por raiz e ano (o mais novo primeiro), sem as citações
    nas notas da DFP (outra fonte, que a ficha ainda não mostra)."""
    dia = f"DATE '{hoje.isoformat()}'"
    sem_citacoes = pd.DataFrame(columns=["cnpj", "numero_processo", "disponivel_em"])
    contagem = processos.contagens(
        _partes_das_companhias(con), _processos_publicos(con, dia), sem_citacoes, hoje
    )
    contados = [c for c in fonte.colunas if c != "ano"]
    tabela = (
        contagem.assign(raiz=_raiz(contagem["cnpj"]))
        .groupby(["raiz", "ano"], as_index=False)[contados]
        .sum()
        .sort_values(["raiz", "ano"], ascending=[True, False], kind="stable")
    )
    return tabela[["raiz", *fonte.colunas]], _conferido_no_djen(con, dia)


def companhias_buscadas(cadastro: pd.DataFrame | None, hoje: date) -> set[str] | None:
    """As raízes das companhias com registro ativo na CVM no dia (`base.cadastro.ler_cadastro`): as que a
    busca do DJEN cobre (`base/arquivo/djen.py`). None sem o cadastro: não se sabe quem foi buscado."""
    if cadastro is None:
        return None
    ativas = cadastro[
        cadastro["cancelamento"].isna()
        & (pd.to_datetime(cadastro["registro"]) <= pd.Timestamp(hoje))
    ]
    raizes = (
        ativas["cnpj"].astype(str).str.upper().str.replace(r"[^0-9A-Z]", "", regex=True)
    )
    return set(raizes[raizes.str.len() == 14].str[:8])


FONTES = (
    Fonte("sancoes_cgu", "sinais", "Sanções do CEIS, CNEP, CEPIM e acordos de leniência", "CGU",
          "https://portaldatransparencia.gov.br/download-de-dados", _SANCOES, "inicio"),
    Fonte("ans_penalidades", "sinais", "Penalidades a operadoras de planos de saúde", "ANS",
          "https://dadosabertos.ans.gov.br/", _SANCOES, "inicio"),
    Fonte("pgfn_divida", "sinais", "Dívida ativa da União, da Previdência e do FGTS", "PGFN",
          "https://dadosabertos.pgfn.gov.br/",
          ("cnpj", "tipo_divida", "tipo_situacao", "situacao_inscricao", "ajuizado", "inscricoes",
           "valor_consolidado", "primeira_inscricao", "ultima_inscricao", "data_do_retrato"),
          "valor_consolidado"),
    Fonte("anvisa_registros", "licencas", "Autorizações de funcionamento e registros de produtos", "Anvisa",
          "https://dados.anvisa.gov.br/dados/", _LICENCAS, "concedido_em"),
    Fonte("antt_rntrc", "licencas", "Registro de transportador rodoviário de cargas (RNTRC)", "ANTT",
          "https://dados.antt.gov.br", _LICENCAS, "concedido_em"),
    Fonte("mapa_sipeagro", "licencas", "Registros de estabelecimentos agropecuários (SIPEAGRO)", "MAPA",
          "https://dados.agricultura.gov.br", _LICENCAS, "concedido_em"),
    Fonte("anatel_outorgas", "licencas", "Outorgas de serviços de telecomunicações", "Anatel",
          "https://www.anatel.gov.br/dadosabertos/", _LICENCAS, "concedido_em"),
    Fonte("anm_titulos", "licencas", "Títulos minerários (Cadastro Mineiro)", "ANM",
          "https://dadosabertos.anm.gov.br/", _LICENCAS, "concedido_em"),
    Fonte("ancine_agentes", "licencas", "Registro de agente econômico do audiovisual", "Ancine",
          "https://dados.ancine.gov.br/dados-abertos/", _LICENCAS, "concedido_em"),
    Fonte("mme_reidi", "incentivos", "Projetos de energia enquadrados no REIDI", "MME",
          "https://dadosabertos.mme.gov.br",
          ("cnpj", "projeto", "nome_do_projeto", "portaria", "uf", "municipio", "portaria_em",
           "execucao_desde", "execucao_ate", "valor_do_beneficio"),
          "portaria_em"),
    Fonte("aneel_cde", "incentivos", "Descontos tarifários pagos pela CDE", "ANEEL",
          "https://dadosabertos.aneel.gov.br",
          ("cnpj", "arquivo", "mes", "distribuidora", "classe", "grupo_tarifario", "tipo_de_desconto",
           "valor_do_desconto"),
          "mes"),
    Fonte("bcb_rde_ied", "incentivos", "Registros de investimento estrangeiro direto (RDE-IED)",
          "Banco Central", "https://dadosabertos.bcb.gov.br",
          ("codigo_rde", "uf", "pais", "ocorrencia", "mes"), "mes", RAIZ_DA_FONTE),
    Fonte("financiamentos_bndes", "financiamentos", "Operações de crédito não automáticas do BNDES",
          "BNDES", "https://dadosabertos.bndes.gov.br/", _FINANCIAMENTOS, "contratado_em"),
    Fonte("financiamentos_finep", "financiamentos", "Crédito direto e descentralizado da Finep", "Finep",
          "https://www.finep.gov.br/", _FINANCIAMENTOS, "contratado_em"),
    Fonte("cmed_precos", "precos", "Preço Fábrica e Preço Máximo ao Consumidor (PF e PMC)",
          "CMED (Anvisa)", "https://dados.anvisa.gov.br/dados/", _cmed("pmc"), "pf_0",
          lista="consumidor", desempate="id_na_fonte"),
    Fonte("cmed_precos", "precos", "Preço Fábrica e Preço Máximo de Venda ao Governo (PF e PMVG)",
          "CMED (Anvisa)", "https://dados.anvisa.gov.br/dados/", _cmed("pmvg"), "pf_0",
          lista="governo", desempate="id_na_fonte"),
    Fonte("processos", "processos", "Processos em que a companhia é parte, a comunicação mais nova primeiro",
          "CNJ (DJEN)", "https://comunica.pje.jus.br/", _PROCESSOS, "ultima_comunicacao",
          outras=(processos.TABELA_DAS_PARTES, processos.TABELA_DAS_COMUNICACOES),
          linhas=_linhas_dos_processos, so_companhias_abertas=True),
    Fonte("processos", "processos", "Processos por ano da ligação, polo e ramo", "CNJ (DJEN)",
          "https://comunica.pje.jus.br/", _POR_ANO, "ano",
          outras=(processos.TABELA_DAS_PARTES, processos.TABELA_DAS_COMUNICACOES),
          arquivo="processos_por_ano", linhas=_linhas_por_ano),
)  # fmt: skip

_CNPJ_LIMPO = "regexp_replace(upper(CAST(cnpj AS VARCHAR)), '[^0-9A-Z]', '', 'g')"


def _view(tabela: str) -> str:
    return '"' + nome_da_view(tabela).replace('"', '""') + '"'


def _da_lista(fonte: Fonte) -> str:
    """O filtro da `lista` da fonte (vazio sem lista); o nome vem de `FONTES`, nunca de fora."""
    return f"AND lista = '{fonte.lista}'" if fonte.lista else ""


def _vigentes_sql(fonte: Fonte, hoje: date) -> str:
    """As linhas vigentes da fonte no dia `hoje`, com a `raiz`, sem pessoa e já públicas."""
    dia = f"DATE '{hoje.isoformat()}'"
    raiz = (
        "upper(CAST(cnpj_basico AS VARCHAR))"
        if fonte.chave == RAIZ_DA_FONTE
        else f"left({_CNPJ_LIMPO}, 8)"
    )
    filtro_cnpj = (
        "" if fonte.chave == RAIZ_DA_FONTE else f"AND length({_CNPJ_LIMPO}) = 14"
    )
    if fonte.tabela == "pgfn_divida":
        janela = "rank() OVER (PARTITION BY tipo_divida ORDER BY data_do_retrato DESC)"
        condicao = "n = 1"
    else:
        chaves = ", ".join(c for c in TABELAS[fonte.tabela].chaves if c != "visto_em")
        janela = f"row_number() OVER (PARTITION BY {chaves} ORDER BY disponivel_em DESC, visto_em DESC)"
        condicao = "n = 1 AND consta"
    return f"""
        SELECT {raiz} AS raiz, *, CAST(disponivel_em AS DATE) AS publico_desde FROM (
            SELECT *, {janela} AS n FROM {_view(fonte.tabela)}
            WHERE CAST(disponivel_em AS DATE) <= {dia} {_da_lista(fonte)}
        )
        WHERE {condicao} AND NOT coalesce(trata_como_pessoa, false) {filtro_cnpj}
    """


def _valor(valor: object) -> object:
    """Um valor de célula em tipo de JSON: data em ISO, vazio em None, `Decimal` em texto exato."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):  # type: ignore[arg-type]
        return None
    if isinstance(valor, pd.Timestamp | datetime | date):
        return valor.isoformat()[:10]
    if isinstance(valor, bool | int | float | str):
        return valor
    return str(valor)


def _linhas_da_fonte(
    con: duckdb.DuckDBPyConnection, fonte: Fonte, hoje: date
) -> tuple[pd.DataFrame, str | None]:
    """As linhas vigentes (só as colunas da ficha e a raiz) e o dia mais novo conferido na fonte."""
    con.execute(f"CREATE OR REPLACE TEMP VIEW vigentes AS {_vigentes_sql(fonte, hoje)}")
    tipos = {
        linha[0]: linha[1] for linha in con.execute("DESCRIBE vigentes").fetchall()
    }
    colunas = [c for c in fonte.colunas if c in tipos]
    # o decimal sai em texto ("250.04"): o DataFrame do DuckDB o faria float e perderia o valor exato
    selecao = ", ".join(
        [
            "raiz",
            *(
                f"CAST({c} AS VARCHAR) AS {c}" if tipos[c].startswith("DECIMAL") else c
                for c in colunas
            ),
        ]
    )
    # a ordem é a da coluna da view (o número), não a do texto da seleção ("99.00" > "1000.00")
    desempate = f", vigentes.{fonte.desempate}" if fonte.desempate else ""
    tabela = con.execute(
        f"SELECT {selecao} FROM vigentes "
        f"ORDER BY raiz, vigentes.{fonte.ordem} DESC NULLS LAST{desempate}"
    ).df()
    dia = "data_do_retrato" if fonte.tabela == "pgfn_divida" else "visto_em"
    conferido = con.execute(
        f"SELECT max(CAST({dia} AS DATE)) FROM {_view(fonte.tabela)} "
        f"WHERE CAST(disponivel_em AS DATE) <= DATE '{hoje.isoformat()}' {_da_lista(fonte)}"
    ).fetchone()
    ultimo = conferido[0] if conferido else None
    return tabela, (ultimo.isoformat() if ultimo else None)


def _por_raiz(tabela: pd.DataFrame) -> Iterator[tuple[str, int, str]]:
    """(raiz, total, linhas em JSON) por raiz; as linhas já vêm em ordem."""
    colunas = [c for c in tabela.columns if c != "raiz"]
    for raiz, grupo in tabela.groupby("raiz", sort=True):
        linhas = [
            {c: _valor(v) for c, v in zip(colunas, linha, strict=True)}
            for linha in grupo[colunas].head(LINHAS_POR_FONTE).itertuples(index=False)
        ]
        yield str(raiz), len(grupo), json.dumps(linhas, ensure_ascii=False)


def _criar(banco: sqlite3.Connection) -> None:
    banco.executescript(
        """
        CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
        CREATE TABLE registros (
            raiz TEXT NOT NULL, tabela TEXT NOT NULL, total INTEGER NOT NULL, linhas TEXT NOT NULL,
            PRIMARY KEY (raiz, tabela)
        ) WITHOUT ROWID;
        CREATE TABLE ligacoes (socia TEXT NOT NULL, empresa TEXT NOT NULL, qualificacao TEXT, entrada_em TEXT);
        """
    )


def _gravar_ligacoes(banco: sqlite3.Connection, vista: Path) -> dict | None:
    """As ligações do QSA vigente da vista; None se a vista não chegou."""
    manifesto = vista_do_cnpj.manifesto(vista)
    if manifesto is None:
        return None
    total = 0
    for parte in vista_do_cnpj.participacoes(vista):
        linhas = grupo_do_qsa.ligacoes(parte)
        banco.executemany(
            "INSERT INTO ligacoes VALUES (?, ?, ?, ?)",
            [(v.socia, v.empresa, v.qualificacao, v.entrada_em) for v in linhas],
        )
        total += len(linhas)
    banco.execute("CREATE INDEX ligacoes_da_socia ON ligacoes (socia)")
    banco.execute("CREATE INDEX ligacoes_da_empresa ON ligacoes (empresa)")
    return {
        "retrato": manifesto.get("mes"),
        "disponivel_em": manifesto.get("disponivel_em"),
        "ligacoes": total,
    }


def _gravar_fonte(
    banco: sqlite3.Connection,
    con: duckdb.DuckDBPyConnection,
    fonte: Fonte,
    hoje: date,
    abertas: set[str] | None,
) -> dict | None:
    """Grava as linhas da fonte em `registros` e devolve o estado dela; None se ela fica "não
    conferida" (a lista da CMED ainda não montada nunca vira zero). `abertas`: as raízes que a busca
    cobre, para a fonte `so_companhias_abertas`."""
    montagem = fonte.linhas or _linhas_da_fonte
    tabela, conferido = montagem(con, fonte, hoje)
    if fonte.lista and conferido is None:
        return None
    linhas = list(_por_raiz(tabela))
    # Sem a data da busca não há como dizer "não encontrado até": ninguém ganha o total 0.
    buscadas = (
        abertas if fonte.so_companhias_abertas and conferido is not None else None
    )
    com_linhas = {raiz for raiz, _, _ in linhas}
    sem_linhas = sorted((buscadas or set()) - com_linhas)
    banco.executemany(
        "INSERT INTO registros VALUES (?, ?, ?, ?)",
        [(raiz, fonte.nome_no_arquivo, total, js) for raiz, total, js in linhas]
        + [(raiz, fonte.nome_no_arquivo, 0, "[]") for raiz in sem_linhas],
    )
    estado = {
        "tabela": fonte.nome_no_arquivo, "tema": fonte.tema, "nome": fonte.nome,
        "orgao": fonte.orgao, "endereco": fonte.endereco,
        "licenca": licenca_da_fonte(TABELAS[fonte.tabela].familia_da_fonte),
        "conferido_ate": conferido, "empresas": len(linhas), "registros": len(tabela),
    }  # fmt: skip
    if fonte.so_companhias_abertas:
        estado["buscadas"] = None if buscadas is None else len(buscadas)
    return estado


def montar(
    base: Path,
    destino: Path,
    vista: Path | None = None,
    agora: datetime | None = None,
    cadastro: pd.DataFrame | None = None,
) -> dict:
    """Grava o arquivo das conferências em `destino` (troca no fim) e devolve o estado gravado.

    Só entra a fonte que tem arquivo na `base` (e, com `lista`, linha dessa lista já pública): a
    que falta fica "não conferida" na ficha.
    """
    agora = agora or datetime.now(UTC)
    hoje = agora.date()
    abertas = companhias_buscadas(cadastro, hoje)
    estado: dict = {
        "esquema": ESQUEMA,
        "gerado_em": agora.isoformat(),
        "temas": TEMAS,
        "fontes": [],
    }

    def gravar(caminho: Path) -> None:
        caminho.unlink(missing_ok=True)
        banco = sqlite3.connect(caminho)
        try:
            _criar(banco)
            with Porta(base) as porta:
                existem = views(porta.con)
                for fonte in FONTES:
                    if any(nome_da_view(t) not in existem for t in fonte.lidas):
                        continue
                    gravada = _gravar_fonte(banco, porta.con, fonte, hoje, abertas)
                    if gravada is not None:
                        estado["fontes"].append(gravada)
            estado["grupo"] = _gravar_ligacoes(banco, vista) if vista else None
            banco.executemany(
                "INSERT INTO meta VALUES (?, ?)",
                [
                    ("schema", ESQUEMA),
                    ("estado", json.dumps(estado, ensure_ascii=False)),
                ],
            )
            banco.commit()
        finally:
            banco.close()

    destino.parent.mkdir(parents=True, exist_ok=True)
    gravar_atomico(destino, gravar)
    return estado
