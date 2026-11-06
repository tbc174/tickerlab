"""Os dados da rodada dos agentes: pregões da B3 e cadastro, balanços e insolvência do acervo.

De onde vem cada tabela de `fatores_b3.Dados` (critérios, seção 2: o universo é mecânico):

| Tabela | Fonte |
|---|---|
| fechamento, abertura, volume | COTAHIST anual da B3 (`COTAHIST_A<ano>.ZIP`, do ano da rodada e do anterior) posto em `PASTA_DOS_ANUAIS`, e o COTAHIST do dia guardado pelo arquivista em `bruto/b3-cotahist-dia/<ano>/`; no mesmo pregão vale o do dia |
| cadastro | ISIN do COTAHIST → emissores do FCA; início da negociação pelo FCA quando ele sabe de antes |
| fundamentos | `demonstracoes/<ano>.parquet` do acervo (consolidado), do ano da rodada e do anterior |
| recuperacao_judicial | `insolvencia/<ano>.parquet` do acervo (documentos que a CVM recebeu) |
| acoes, cdi | vazios: o universo e a liquidez não usam; a comparação de 12 meses carrega os dela |

Preços sem ajuste por proventos: a rodada só usa o volume e se houve negócio no dia. Os diários
sozinhos não bastam (o arquivista guarda o COTAHIST do dia desde 15/09/2026 e a média da
liquidez pede 60 pregões), então o anual do ano entra antes da rodada. Nada aqui baixa nada da
internet: falta de pregão para a rodada e diz qual arquivo pôr onde.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from trader import calendario
from trader.agentes import criterios
from trader.estrategias import dados_f_b3
from trader.estrategias.fatores_b3 import (
    COLUNAS_DAS_ACOES,
    COLUNAS_DOS_FUNDAMENTOS,
    Dados,
)

PASTA_DO_ACERVO = dados_f_b3.PASTA_DO_ACERVO  # `acervo/base` da cópia local
PASTA_DOS_DIARIOS = PASTA_DO_ACERVO.parent / "bruto" / "b3-cotahist-dia"
PASTA_DOS_ANUAIS = dados_f_b3.PASTA_DA_PESQUISA / "cotahist"  # fora do Git
ENDERECO_DO_ANUAL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/{nome}"
COLUNAS_DO_COTAHIST = (
    "data",
    "ticker",
    "isin",
    "especificacao",
    "abertura",
    "fechamento",
    "volume",
)
# Insolvência em curso ou pedida (critérios, seção 2 e veto V1); `exposicao_a_terceiro` é a
# empresa que tem a receber de quem quebrou, não a que quebrou.
ROTULOS_DE_INSOLVENCIA = (
    "recuperacao_judicial",
    "recuperacao_extrajudicial",
    "recuperacao_judicial_ou_extrajudicial",
    "pedido_de_falencia",
    "falencia",
    "liquidacao",
)
# A CVM não tem um evento de "encerrada": quem está em recuperação manda documento todo mês
# (relatório do administrador judicial), então 12 meses sem documento novo contam como fim.
MESES_SEM_DOCUMENTO = 12
DIAS_CORRIDOS_POR_PREGAO = 2  # folga para achar os N últimos pregões no calendário


class FaltamPregoesError(FileNotFoundError):
    """A base não tem todos os pregões que a liquidez da rodada pede."""


def _juntar(tabelas: Iterable[pd.DataFrame], colunas: Iterable[str]) -> pd.DataFrame:
    lista = list(tabelas)
    if not lista:
        return pd.DataFrame(columns=list(colunas))
    return pd.concat(lista, ignore_index=True)


def ler_pregoes(anuais: Iterable[Path], diarios: Iterable[Path]) -> pd.DataFrame:
    """Os COTAHIST em formato longo; um pregão que veio no diário sai inteiro do diário.

    O diário tem o mesmo leiaute do anual (registro 01, mercado à vista), lido pela mesma função.
    """
    do_dia = _juntar(map(dados_f_b3.ler_cotahist_anual, diarios), COLUNAS_DO_COTAHIST)
    do_ano = _juntar(map(dados_f_b3.ler_cotahist_anual, anuais), COLUNAS_DO_COTAHIST)
    do_ano = do_ano[~do_ano["data"].isin(do_dia["data"].unique())]
    longo = _juntar([do_ano, do_dia], COLUNAS_DO_COTAHIST)
    longo = longo.drop_duplicates(["data", "ticker"], keep="last")
    return longo.sort_values(["data", "ticker"], kind="stable").reset_index(drop=True)


def pregoes_que_faltam(datas: Iterable[date], ate: date, quantos: int) -> list[date]:
    """Dos `quantos` últimos pregões do calendário até `ate` (inclusive), os que não estão nos dados."""
    inicio = ate - timedelta(days=DIAS_CORRIDOS_POR_PREGAO * quantos)
    esperados = calendario.pregoes(inicio, ate)[-quantos:]
    presentes = set(datas)
    return [dia for dia in esperados if dia not in presentes]


def recuperacao_judicial(insolvencia: pd.DataFrame, ate: date) -> pd.DataFrame:
    """Uma linha por CNPJ: do primeiro documento de insolvência até 12 meses depois do último.

    Só o que a CVM recebeu até `ate` (sem olhar o futuro).
    """
    insolvencia = insolvencia.reset_index(drop=True)  # anos juntados repetem o índice
    conhecido = pd.to_datetime(insolvencia["conhecido_em"])
    linhas = insolvencia[
        insolvencia["rotulo"].isin(ROTULOS_DE_INSOLVENCIA)
        & (conhecido <= pd.Timestamp(ate))
    ].assign(conhecido_em=conhecido)
    por_cnpj = linhas.groupby("cnpj", sort=True)["conhecido_em"]
    tabela = pd.DataFrame(
        {
            "inicio": por_cnpj.min(),
            "fim": por_cnpj.max() + pd.DateOffset(months=MESES_SEM_DOCUMENTO),
        }
    )
    return tabela.reset_index()[["cnpj", "inicio", "fim"]]


def _anos(dia: date) -> tuple[int, int]:
    return dia.year - 1, dia.year


def _parquets_dos_anos(pasta: Path, anos: Iterable[int]) -> list[pd.DataFrame]:
    caminhos = (pasta / f"{ano}.parquet" for ano in anos)
    return [pd.read_parquet(caminho) for caminho in caminhos if caminho.exists()]


def _erro_de_pregoes(faltas: list[date], pasta_dos_anuais: Path) -> FaltamPregoesError:
    nomes = sorted({dados_f_b3.nome_do_cotahist(dia.year) for dia in faltas})
    arquivos = ", ".join(
        f"{nome} ({ENDERECO_DO_ANUAL.format(nome=nome)})" for nome in nomes
    )
    return FaltamPregoesError(
        f"faltam {len(faltas)} pregões para a liquidez da rodada "
        f"({', '.join(dia.isoformat() for dia in faltas)}); "
        f"ponha {arquivos} em {pasta_dos_anuais}"
    )


def carregar(
    dia_dos_dados: date,
    pasta_do_acervo: Path = PASTA_DO_ACERVO,
    pasta_dos_anuais: Path = PASTA_DOS_ANUAIS,
    pasta_dos_diarios: Path = PASTA_DOS_DIARIOS,
) -> Dados:
    """`Dados` com os pregões até `dia_dos_dados` (inclusive); falha se falta algum dos 61 últimos."""
    anos = _anos(dia_dos_dados)
    anuais = [
        pasta_dos_anuais / dados_f_b3.nome_do_cotahist(ano)
        for ano in anos
        if (pasta_dos_anuais / dados_f_b3.nome_do_cotahist(ano)).exists()
    ]
    diarios = [
        caminho
        for ano in anos
        for caminho in sorted((pasta_dos_diarios / str(ano)).glob("*.zip"))
    ]
    longo = ler_pregoes(anuais, diarios)
    longo = longo[longo["data"] <= pd.Timestamp(dia_dos_dados)]
    datas = {dia.date() for dia in pd.DatetimeIndex(longo["data"].unique())}
    faltas = pregoes_que_faltam(
        datas, dia_dos_dados, criterios.PREGOES_MINIMOS + 1
    )  # os 60 da média e o próprio dia
    if faltas:
        raise _erro_de_pregoes(faltas, pasta_dos_anuais)
    fechamento, abertura, volume = dados_f_b3.paineis(longo)
    fundamentos = _juntar(
        map(
            dados_f_b3.fundamentos_do_acervo,
            _parquets_dos_anos(pasta_do_acervo / "demonstracoes", anos),
        ),
        COLUNAS_DOS_FUNDAMENTOS,
    )
    fundamentos = fundamentos[
        pd.to_datetime(fundamentos["divulgado_em"]) <= pd.Timestamp(dia_dos_dados)
    ]
    insolvencia = _juntar(
        _parquets_dos_anos(pasta_do_acervo / "insolvencia", anos),
        ("cnpj", "rotulo", "conhecido_em"),
    )
    return Dados(
        fechamento=fechamento,
        abertura=abertura,
        volume=volume,
        cadastro=dados_f_b3.cadastro_dos_tickers(
            longo,
            pd.read_parquet(pasta_do_acervo / "fca" / "emissores.parquet"),
            pd.read_parquet(pasta_do_acervo / "fca" / "tickers.parquet"),
        ),
        fundamentos=fundamentos.reset_index(drop=True),
        acoes=pd.DataFrame(columns=list(COLUNAS_DAS_ACOES)),
        cdi=pd.Series(float("nan"), index=fechamento.index, name="cdi"),
        recuperacao_judicial=recuperacao_judicial(insolvencia, dia_dos_dados),
    )
