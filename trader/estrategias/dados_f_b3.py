"""Dados da ficha F-B3: COTAHIST anual da B3, FCA (cadastro) e balanços ponto no tempo do acervo.

De onde vem cada tabela de `fatores_b3.Dados`:

| Tabela | Fonte | Situação em 03/11/2026 |
|---|---|---|
| fechamento, abertura, volume | COTAHIST anual (`COTAHIST_A<ano>.ZIP`, mercado à vista) de 2009 a 2023, na pasta da ficha | **falta**: o acervo só tem o COTAHIST diário desde 09/2026 e o lote anual de 1986 a 2009 |
| preços ajustados | `precos_ajustados.parquet` (fechamento ajustado por desdobramentos e proventos, mesmas datas e tickers) | **falta**: não há base de preços ajustados; `eventos_de_capital` e `proventos` do acervo vão até 2023 e permitem construí-la |
| cadastro | ISIN do COTAHIST (posições 3 a 6 = emissor) → `fca/emissores.parquet` e, para quem saiu antes de 2018, `emissores_antigos.csv` (ligação pelo nome, conferida por dois modelos); classe pela especificação; datas do FCA quando houver | pronto (emissores do FCA desde 2018 e 77 antigos) |
| fundamentos | `demonstracoes/<ano>.parquet` do acervo, consolidado, com `divulgado_em` e `ate` | pronto (2010 em diante) |
| acoes | `acoes_em_circulacao.parquet` (CNPJ, quantidade, data em que ficou pública) | **falta**: o acervo não tem quantidade de ações |
| cdi, ibovespa | SGS 12 (cache da pesquisa) e BOVA11 do export do MT5 | pronto |

`conferir_base` lista o que falta; com faltas, a rodada da ficha para antes de registrar qualquer
tentativa (pré-registro v0.1, seção 2: sem as deslistadas não há resultado honesto). Nada aqui
baixa nada da internet. `carregar_tabelas` monta tudo quando a base existir e ainda não foi
exercitada com dados reais (limitação declarada no relatório).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

from trader.estrategias import dados_p0_3
from trader.estrategias.fatores_b3 import (
    CLASSES_DE_ACAO,
    COLUNAS_DAS_ACOES,
    COLUNAS_DO_CADASTRO,
    COLUNAS_DOS_FUNDAMENTOS,
    CONTAS_USADAS,
    Dados,
)
from trader.holdout import exigir_sem_holdout, recortar_desenvolvimento

PASTA_DA_PESQUISA = dados_p0_3.PASTA_DA_PESQUISA
PASTA_DA_FICHA = PASTA_DA_PESQUISA / "f_b3"
PASTA_DO_ACERVO = (
    dados_p0_3.PASTA_DA_CURVA.parent
)  # a cópia local do acervo (`acervo/base`)
PRIMEIRO_ANO = (
    2009  # 12 meses de pregão e de balanço antes da primeira decisão, em 2010
)
ULTIMO_ANO = 2023  # o desenvolvimento acaba em 08/09/2023
ARQUIVO_DE_PRECOS_AJUSTADOS = "precos_ajustados.parquet"
ARQUIVO_DE_ACOES = "acoes_em_circulacao.parquet"
TIPO_DE_REGISTRO = "01"
MERCADO_A_VISTA = "010"
CENTAVOS = 100
GRUPO_CONSOLIDADO = "con"
POSICOES_DO_EMISSOR_NO_ISIN = slice(2, 6)
# Posições do layout COTAHIST (registro 01, 245 posições), as mesmas de base/intradiario_b3.py.
CAMPOS = {
    "tipo": (0, 2),
    "data": (2, 10),
    "ticker": (12, 24),
    "mercado": (24, 27),
    "especificacao": (39, 49),
    "abertura": (56, 69),
    "fechamento": (108, 121),
    "volume": (170, 188),
    "fator_de_cotacao": (210, 217),
    "isin": (230, 242),
    "distribuicao": (242, 245),  # DISMES: muda no dia ex de desdobramento e de provento
}
# Emissores que saíram antes de 2018 (o FCA do acervo só liga ticker a CNPJ desde então): o CNPJ
# pelo nome de pregão, escolhido às cegas por dois modelos nos nomes da CVM do acervo; quem
# discordou ou não achou fica sem CNPJ (conferência automática, sem o Tiago).
ARQUIVO_DOS_EMISSORES_ANTIGOS = Path(__file__).with_name("emissores_antigos.csv")
COLUNAS_DOS_EMISSORES_ANTIGOS = (
    "emissor",
    "cnpj",
    "nome_no_pregao",
    "empresa_na_cvm",
    "conferencia",
)


def nome_do_cotahist(ano: int) -> str:
    return f"COTAHIST_A{ano}.ZIP"


def conferir_base(pasta: Path = PASTA_DA_FICHA, *, com_acoes: bool = True) -> list[str]:
    """Os arquivos que faltam para a ficha rodar; lista vazia quando dá para rodar.

    `com_acoes=False` serve às fichas que não usam a quantidade de ações (P0-4, pares).
    """
    esperados = [nome_do_cotahist(ano) for ano in range(PRIMEIRO_ANO, ULTIMO_ANO + 1)]
    esperados.append(ARQUIVO_DE_PRECOS_AJUSTADOS)
    if com_acoes:
        esperados.append(ARQUIVO_DE_ACOES)
    return [nome for nome in esperados if not (pasta / nome).exists()]


def ler_cotahist_anual(caminho: Path) -> pd.DataFrame:
    """Um ZIP anual da B3 em formato longo: data, ticker, isin, especificação, preços e volume.

    Só o mercado à vista em lote padrão (010); preços e volume vêm em centavos no arquivo. Até
    2023 há papéis cotados por lote de mil (fator de cotação 1000): o preço é dividido pelo fator
    para ficar por ação (o volume já vem em reais). Campo vazio vale 1.
    """
    with zipfile.ZipFile(caminho) as pacote:
        nome = next(n for n in pacote.namelist() if n.upper().endswith(".TXT"))
        with pacote.open(nome) as bruto:
            tabela = pd.read_fwf(
                io.TextIOWrapper(bruto, encoding="latin-1"),
                colspecs=list(CAMPOS.values()),
                names=list(CAMPOS),
                dtype=str,
                header=None,
            )
    cotacoes = tabela[
        (tabela["tipo"] == TIPO_DE_REGISTRO) & (tabela["mercado"] == MERCADO_A_VISTA)
    ]
    divisor = CENTAVOS * pd.to_numeric(cotacoes["fator_de_cotacao"]).fillna(1.0)
    return pd.DataFrame(
        {
            "data": pd.to_datetime(cotacoes["data"], format="%Y%m%d"),
            "ticker": cotacoes["ticker"].str.strip(),
            "isin": cotacoes["isin"].str.strip(),
            "especificacao": cotacoes["especificacao"].str.strip(),
            "abertura": cotacoes["abertura"].astype(float) / divisor,
            "fechamento": cotacoes["fechamento"].astype(float) / divisor,
            "volume": cotacoes["volume"].astype(float) / CENTAVOS,
            "distribuicao": cotacoes["distribuicao"].str.strip(),
        }
    ).reset_index(drop=True)


def paineis(longo: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fechamento, abertura e volume em tabelas largas (data × ticker), NaN sem pregão."""

    def painel(coluna: str) -> pd.DataFrame:
        return longo.pivot_table(
            index="data", columns="ticker", values=coluna, aggfunc="last"
        ).sort_index()

    fechamento = painel("fechamento")
    return (
        fechamento,
        painel("abertura").reindex_like(fechamento),
        painel("volume").reindex_like(fechamento),
    )


def trocas_de_distribuicao(longo: pd.DataFrame) -> pd.DataFrame:
    """Tabela larga (data × ticker): verdadeiro no pregão em que o número de distribuição mudou.

    O primeiro pregão de cada papel não conta como troca; dia sem pregão é falso.
    """
    ordenado = longo.sort_values(["ticker", "data"], kind="stable")
    anterior = ordenado.groupby("ticker")["distribuicao"].shift()
    troca = anterior.notna() & (ordenado["distribuicao"] != anterior)
    largo = ordenado.assign(troca=troca).pivot_table(
        index="data", columns="ticker", values="troca", aggfunc="max"
    )
    return largo.sort_index().eq(True)


def emissores_com_antigos(
    emissores: pd.DataFrame, antigos: pd.DataFrame
) -> pd.DataFrame:
    """Os emissores do FCA mais os antigos com CNPJ; no mesmo emissor vale o FCA."""
    com_cnpj = antigos.loc[antigos["cnpj"].notna(), ["emissor", "cnpj"]]
    juntos = pd.concat([emissores[["emissor", "cnpj"]], com_cnpj], ignore_index=True)
    return juntos.drop_duplicates("emissor", keep="first").reset_index(drop=True)


def ler_emissores(pasta_do_acervo: Path) -> pd.DataFrame:
    """`fca/emissores.parquet` do acervo completado por `emissores_antigos.csv`."""
    return emissores_com_antigos(
        pd.read_parquet(pasta_do_acervo / "fca" / "emissores.parquet"),
        pd.read_csv(ARQUIVO_DOS_EMISSORES_ANTIGOS, dtype=str),
    )


def classe_da_especificacao(especificacao: str) -> str:
    """ON, PN ou UNT pela especificação do papel ("PN N2", "UNT N2"); o resto é "outro"."""
    for classe in CLASSES_DE_ACAO:
        if especificacao.upper().startswith(classe):
            return classe
    return "outro"


def cadastro_dos_tickers(
    longo: pd.DataFrame,
    emissores: pd.DataFrame,
    tickers_do_fca: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Cadastro por ticker: CNPJ pelo emissor do ISIN, classe, primeiro e último pregão.

    O último pregão fica vazio para quem ainda negociava no último dia dos dados. O primeiro é
    o do COTAHIST ou, se o FCA souber de uma data anterior, a do FCA.
    """
    ultimo_dia = longo["data"].max()
    por_ticker = longo.sort_values("data", kind="stable").groupby("ticker")
    tabela = por_ticker.agg(
        isin=("isin", "last"),
        especificacao=("especificacao", "last"),
        inicio_negociacao=("data", "min"),
        ultimo=("data", "max"),
    )
    cnpj_do_emissor = emissores.drop_duplicates("emissor").set_index("emissor")["cnpj"]
    tabela["cnpj"] = (
        tabela["isin"].str[POSICOES_DO_EMISSOR_NO_ISIN].map(cnpj_do_emissor)
    )
    tabela["classe"] = tabela["especificacao"].map(classe_da_especificacao)
    tabela["fim_negociacao"] = tabela["ultimo"].where(tabela["ultimo"] < ultimo_dia)
    if tickers_do_fca is not None:
        do_fca = pd.to_datetime(
            tickers_do_fca.drop_duplicates("codigo").set_index("codigo")[
                "inicio_negociacao"
            ]
        ).reindex(tabela.index)
        tabela["inicio_negociacao"] = tabela["inicio_negociacao"].where(
            do_fca.isna() | (do_fca > tabela["inicio_negociacao"]), do_fca
        )
    return tabela[list(COLUNAS_DO_CADASTRO)]


def fundamentos_do_acervo(demonstracoes: pd.DataFrame) -> pd.DataFrame:
    """Da tabela `demonstracoes/<ano>.parquet` para o formato da ficha.

    Só o consolidado e as contas usadas; as versões ficam em ordem para a última vencer.
    Empresa que só publica o individual fica sem fundamentos (limitação declarada).
    """
    linhas = demonstracoes[
        (demonstracoes["grupo"] == GRUPO_CONSOLIDADO)
        & demonstracoes["conta"].isin(CONTAS_USADAS)
    ]
    linhas = linhas.sort_values(["cnpj", "conta", "fim", "versao"], kind="stable")
    return linhas[list(COLUNAS_DOS_FUNDAMENTOS)].reset_index(drop=True)


def carregar_tabelas(
    pasta: Path = PASTA_DA_FICHA,
    pasta_do_acervo: Path = PASTA_DO_ACERVO,
    *,
    com_acoes: bool = True,
) -> Dados:
    """Monta `Dados` da ficha só com o desenvolvimento; falha listando o que falta.

    Com `com_acoes=False`, `acoes` vem vazia (com as colunas certas).
    """
    faltas = conferir_base(pasta, com_acoes=com_acoes)
    if faltas:
        raise FileNotFoundError(f"faltam na base da ficha F-B3: {', '.join(faltas)}")
    anos = range(PRIMEIRO_ANO, ULTIMO_ANO + 1)
    longo = pd.concat(
        [ler_cotahist_anual(pasta / nome_do_cotahist(ano)) for ano in anos],
        ignore_index=True,
    )
    bruto, abertura_bruta, volume = paineis(longo)
    ajustado = pd.read_parquet(pasta / ARQUIVO_DE_PRECOS_AJUSTADOS).reindex_like(bruto)
    fator = ajustado / bruto
    fechamento = recortar_desenvolvimento(ajustado)
    datas = pd.DatetimeIndex(fechamento.index)
    emissores = ler_emissores(pasta_do_acervo)
    tickers_do_fca = pd.read_parquet(pasta_do_acervo / "fca" / "tickers.parquet")
    fundamentos = pd.concat(
        [
            fundamentos_do_acervo(
                pd.read_parquet(pasta_do_acervo / "demonstracoes" / f"{ano}.parquet")
            )
            for ano in anos
            if (pasta_do_acervo / "demonstracoes" / f"{ano}.parquet").exists()
        ],
        ignore_index=True,
    )
    bova11 = dados_p0_3.fechamento_do_mt5(
        dados_p0_3.PASTA_DO_MT5 / dados_p0_3.ARQUIVOS_DO_MT5["BOVA11"],
        so_com_negocio=True,
    )
    ibovespa = bova11.reindex(datas).ffill().pct_change(fill_method=None).fillna(0.0)
    cdi = dados_p0_3.carregar_cdi(datas.min(), datas.max()).reindex(datas).ffill()
    dados = Dados(
        fechamento=fechamento,
        abertura=(abertura_bruta * fator).reindex(datas),
        volume=volume.reindex(datas),
        cadastro=cadastro_dos_tickers(longo, emissores, tickers_do_fca),
        fundamentos=fundamentos,
        acoes=(
            pd.read_parquet(pasta / ARQUIVO_DE_ACOES)[list(COLUNAS_DAS_ACOES)]
            if com_acoes
            else pd.DataFrame(columns=list(COLUNAS_DAS_ACOES))
        ),
        cdi=cdi,
        ibovespa=ibovespa,
    )
    for tabela in (dados.fechamento, dados.abertura, dados.volume, dados.cdi):
        exigir_sem_holdout(tabela)
    return dados
