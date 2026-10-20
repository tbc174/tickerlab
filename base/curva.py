"""Curva de juros própria (série B12): nominal, real e inflação implícita, sem B3 nem ANBIMA.

Fonte: as taxas diárias do Tesouro Direto desde 2004 (Tesouro Transparente, ODbL), guardadas pelo
arquivista como `tesouro-br-direto`. Versão 1, de propósito simples e auditável:

- só os títulos **sem cupom**, cuja taxa já é a taxa "zero" do prazo: Tesouro Prefixado (LTN) para a
  curva nominal e Tesouro IPCA+ (NTN-B Principal) para a real;
- prazo em dias úteis (base 252) da **liquidação** (dia útil seguinte à cotação) até o vencimento, com
  o calendário que se conhecia na data (`base/dias_uteis.py`): é a conta que reproduz o preço publicado
  pelo Tesouro em 99% das linhas;
- entre dois títulos, interpolação **flat-forward** (padrão do mercado brasileiro); **sem extrapolar**:
  se o título mais longo do dia vence em 7 anos, o vértice de 10 anos não sai;
- inflação implícita = (1 + nominal) / (1 + real) − 1 no mesmo prazo.

Cuidados: a taxa do Tesouro Direto tem um spread do Tesouro sobre o mercado secundário (medir contra
os leilões, `tesouro-br-leiloes`). Usa a taxa de compra; quando o título só está à venda para resgate,
a de venda (`lado`). Nada de olhar o futuro: a curva de um dia só usa as taxas daquele dia, e
`disponivel_em` é o dia útil seguinte (o arquivo do Tesouro sai na manhã seguinte).

Versão 2 (B-24): além da flat-forward, o método `nss` ajusta aos títulos do dia uma curva
Nelson-Siegel-Svensson (`ajustar_nss`, `taxa_nss`). A flat-forward **continua sendo a padrão**. A NSS:

- é ajustada ao logaritmo de (1 + taxa), por grade nos dois prazos de decaimento (tau1, tau2) e
  mínimos quadrados lineares nos quatro betas, só com numpy (nada de scipy) e sem sorteio: a mesma
  entrada dá sempre o mesmo ajuste;
- usa Svensson com 6 ou mais títulos no dia, Nelson-Siegel (sem o segundo corcunda) com 4 ou 5, e
  não dá curva com menos de 4 (haveria menos pontos que parâmetros);
- **passa perto dos títulos, não exatamente por eles**: o erro máximo nos vértices observados vem em
  `erro_max_bp` (com 6 ou 7 títulos e 6 parâmetros o ajuste é quase exato por construção; o que diz
  se a curva presta fora dos vértices é outra conta, que esta versão não faz);
- **extrapola**: dá taxa também além do título mais longo. Isso é **hipótese do modelo, não dado do
  Tesouro**: a coluna `maior_prazo_anos` diz até onde há título, e todo vértice com prazo maior que
  ela é extrapolado.

A fórmula é a de Svensson (1994), a mesma que o QuantLib (`NelsonSiegelFitting`, `SvenssonFitting`)
e os bancos centrais usam; o QuantLib é só referência, não é instalado nem importado.
Versão 3 (depois): os títulos com cupom (NTN-F e NTN-B).
"""

import io
import math
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base.dias_uteis import DIAS_POR_ANO, dias_uteis, proximo_dia_util
from base.parquet import LINHAGEM, gravar_se_mudou
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.versao_do_codigo import versao_do_codigo

FONTE = "tesouro-br-direto"
TITULOS_DAS_CURVAS = {"nominal": "Tesouro Prefixado", "real": "Tesouro IPCA+"}
VERTICES_ANOS = (0.5, 1, 2, 3, 5, 10, 20)
TABELA = "curva_juros"
METODOS = ("flat_forward", "nss")
TITULOS_MINIMOS_NSS = 6  # Svensson tem 6 parâmetros (4 betas e 2 taus)
TITULOS_MINIMOS_NS = 4  # Nelson-Siegel tem 4 (3 betas e 1 tau)
TAU1_ANOS = (0.25, 8.0)  # faixa de busca do primeiro prazo de decaimento
TAU2_ANOS = (1.0, 30.0)  # e do segundo
TAU2_SOBRE_TAU1 = (
    1.5  # tau2 bem maior que tau1, para os dois corcundas não trocarem de lugar
)
PASSOS_DA_GRADE = 24
RODADAS_DE_REFINO = 3
PENALIDADE_DOS_BETAS = (
    1e-6  # peso do encolhimento de beta1 a beta3 (ver `_betas_e_erros`)
)
PONTOS_BASE_POR_UNIDADE = 1e4
COLUNAS_DO_CSV = {
    "Tipo Titulo": "titulo",
    "Data Vencimento": "vencimento",
    "Data Base": "data_base",
    "Taxa Compra Manha": "taxa_compra",
    "Taxa Venda Manha": "taxa_venda",
}


def ler_tesouro_direto(conteudo: bytes) -> pd.DataFrame:
    """Uma linha por título e dia: taxa (decimal), lado da taxa e prazo em dias úteis e em anos."""
    bruto = pd.read_csv(io.BytesIO(conteudo), sep=";", decimal=",", encoding="latin-1")
    tabela = pd.DataFrame(
        bruto.rename(columns=COLUNAS_DO_CSV).loc[:, list(COLUNAS_DO_CSV.values())]
    )
    for coluna in ("data_base", "vencimento"):
        tabela[coluna] = pd.to_datetime(tabela[coluna], dayfirst=True)
    compra = pd.Series(tabela["taxa_compra"]).fillna(0) > 0
    venda = pd.Series(tabela["taxa_venda"]).fillna(0) > 0
    tabela = tabela.loc[compra | venda].copy()
    compra = compra.loc[tabela.index]
    tabela["taxa"] = (
        pd.Series(tabela["taxa_compra"]).where(compra, tabela["taxa_venda"]) / 100
    )
    tabela["lado"] = np.where(compra, "compra", "venda")
    tabela["liquidacao"] = proximo_dia_util(pd.Series(tabela["data_base"]))
    tabela["dias_uteis"] = dias_uteis(
        pd.Series(tabela["liquidacao"]), pd.Series(tabela["vencimento"])
    )
    tabela = tabela.loc[tabela["dias_uteis"] > 0].copy()
    tabela["prazo_anos"] = tabela["dias_uteis"] / DIAS_POR_ANO
    colunas = [
        "data_base",
        "titulo",
        "vencimento",
        "taxa",
        "lado",
        "dias_uteis",
        "prazo_anos",
    ]
    ordenada = tabela.loc[:, colunas].sort_values(["data_base", "titulo", "vencimento"])
    return ordenada.reset_index(drop=True)


def flat_forward(prazos: np.ndarray, taxas: np.ndarray, alvo: float) -> float:
    """Taxa no prazo `alvo` (anos) entre os títulos do dia; NaN fora do intervalo (sem extrapolar).

    Flat-forward: o logaritmo do fator (1 + taxa) ^ prazo varia em linha reta entre dois vencimentos,
    ou seja, a taxa a termo entre eles é constante.
    """
    if len(prazos) == 0 or alvo < prazos[0] or alvo > prazos[-1]:
        return math.nan
    fatores = prazos * np.log1p(taxas)
    return math.expm1(float(np.interp(alvo, prazos, fatores)) / alvo)


def _cargas(
    prazos: np.ndarray, tau1: np.ndarray, tau2: np.ndarray | None
) -> np.ndarray:
    """Cargas (..., prazos, betas) da NSS para cada par de taus; sem `tau2` é Nelson-Siegel (3 betas)."""
    x1 = prazos / tau1[..., None]
    carga1 = -np.expm1(-x1) / x1
    colunas = [np.ones_like(carga1), carga1, carga1 - np.exp(-x1)]
    if tau2 is not None:
        x2 = prazos / tau2[..., None]
        colunas.append(-np.expm1(-x2) / x2 - np.exp(-x2))
    return np.stack(colunas, axis=-1)


def _betas_e_erros(
    y: np.ndarray, prazos: np.ndarray, tau1: np.ndarray, tau2: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray]:
    """Mínimos quadrados lineares nos betas para cada par de taus: (betas, soma dos quadrados).

    Com 6 ou 7 títulos e 6 parâmetros o ajuste puro é quase uma interpolação e pode pôr betas enormes
    que se anulam entre os vértices e explodem além deles (numa amostra de teste foi a 24% aos 20 anos,
    com o último título a 13%). Por isso beta1 a beta3 levam uma penalidade pequena
    (`PENALIDADE_DOS_BETAS`, regressão em crista): o erro nos vértices sobe menos de 0,1 bp e a
    extrapolação fica comportada. O beta0 (o nível de longo prazo) não é penalizado.
    """
    cargas = _cargas(prazos, tau1, tau2)
    colunas = cargas.shape[-1]
    crista = np.sqrt(PENALIDADE_DOS_BETAS) * np.eye(colunas)[1:]
    crista = np.broadcast_to(crista, (*cargas.shape[:-2], *crista.shape))
    sistema = np.concatenate([cargas, crista], axis=-2)
    alvo = np.concatenate([y, np.zeros(colunas - 1)])
    betas = np.linalg.pinv(sistema) @ alvo
    resto = np.einsum("...pb,...b->...p", sistema, betas) - alvo
    return betas, np.sum(resto**2, axis=-1)


def _grade_em_volta(
    centro: float, passo: float, faixa: tuple[float, float]
) -> np.ndarray:
    """Grade de `PASSOS_DA_GRADE` pontos de um passo abaixo a um acima do centro, dentro da faixa."""
    return np.geomspace(
        max(centro / passo, faixa[0]), min(centro * passo, faixa[1]), PASSOS_DA_GRADE
    )


def _pares_validos(
    grade1: np.ndarray, grade2: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray | None]:
    if grade2 is None:
        return grade1, None
    par1, par2 = (a.ravel() for a in np.meshgrid(grade1, grade2, indexing="ij"))
    valido = par2 >= TAU2_SOBRE_TAU1 * par1
    return par1[valido], par2[valido]


def _melhores_taus(
    y: np.ndarray, prazos: np.ndarray, com_tau2: bool
) -> tuple[float, float | None]:
    """Grade nos prazos de decaimento, cada rodada mais fina em volta do melhor par; sem sorteio."""
    grade1 = np.geomspace(*TAU1_ANOS, PASSOS_DA_GRADE)
    grade2 = np.geomspace(*TAU2_ANOS, PASSOS_DA_GRADE) if com_tau2 else None
    for rodada in range(RODADAS_DE_REFINO + 1):
        par1, par2 = _pares_validos(grade1, grade2)
        _, erros = _betas_e_erros(y, prazos, par1, par2)
        melhor = int(np.argmin(erros))
        tau1, tau2 = float(par1[melhor]), None if par2 is None else float(par2[melhor])
        if rodada < RODADAS_DE_REFINO:
            grade1 = _grade_em_volta(tau1, float(grade1[1] / grade1[0]), TAU1_ANOS)
            if grade2 is not None and tau2 is not None:
                grade2 = _grade_em_volta(tau2, float(grade2[1] / grade2[0]), TAU2_ANOS)
    return tau1, tau2


def ajustar_nss(
    prazos: np.ndarray, taxas: np.ndarray
) -> dict[str, float | int | str] | None:
    """Ajusta Nelson-Siegel-Svensson aos títulos de um dia; `None` com menos de 4 títulos.

    `prazos` em anos (dias úteis / 252) e `taxas` em decimal ao ano, de títulos sem cupom do mesmo dia.
    Devolve só tipos simples: `modelo` ("nss" com 6 ou mais títulos, "ns" com 4 ou 5), `beta0` a `beta3`,
    `tau1`, `tau2` (NaN no "ns"), `titulos`, `maior_prazo_anos` e `erro_max_bp`, o maior erro, em
    pontos-base, entre a curva e as taxas dos títulos. Passar perto dos títulos não prova a curva fora
    deles; o que ela diz além de `maior_prazo_anos` é hipótese do modelo, não dado.
    """
    prazos, taxas = np.asarray(prazos, dtype=float), np.asarray(taxas, dtype=float)
    if len(prazos) < TITULOS_MINIMOS_NS:
        return None
    com_tau2 = len(prazos) >= TITULOS_MINIMOS_NSS
    tau1, tau2 = _melhores_taus(np.log1p(taxas), prazos, com_tau2)
    betas, _ = _betas_e_erros(
        np.log1p(taxas),
        prazos,
        np.array(tau1),
        None if tau2 is None else np.array(tau2),
    )
    ajuste: dict[str, float | int | str] = {
        "modelo": "nss" if com_tau2 else "ns",
        "beta0": float(betas[0]),
        "beta1": float(betas[1]),
        "beta2": float(betas[2]),
        "beta3": float(betas[3]) if com_tau2 else 0.0,
        "tau1": tau1,
        "tau2": math.nan if tau2 is None else tau2,
        "titulos": len(prazos),
        "maior_prazo_anos": float(prazos.max()),
    }
    previstas = np.array([taxa_nss(ajuste, float(p)) for p in prazos])
    ajuste["erro_max_bp"] = float(
        np.max(np.abs(previstas - taxas)) * PONTOS_BASE_POR_UNIDADE
    )
    return ajuste


def taxa_nss(parametros: Mapping[str, float | int | str], prazo: float) -> float:
    """Taxa ao ano (decimal) da curva NSS no `prazo` em anos; NaN se o prazo não for positivo."""
    if prazo <= 0:
        return math.nan
    tau2 = float(parametros["tau2"])
    cargas = _cargas(
        np.array([prazo]),
        np.array(float(parametros["tau1"])),
        None if math.isnan(tau2) else np.array(tau2),
    )[0]
    betas = np.array([float(parametros[f"beta{i}"]) for i in range(cargas.shape[-1])])
    return math.expm1(float(cargas @ betas))


def _pontos(dia: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    pontos = dia.groupby("prazo_anos")["taxa"].mean().sort_index()
    return pontos.index.to_numpy(dtype=float), pontos.to_numpy(dtype=float)


def _vertices(dia: pd.DataFrame, metodo: str) -> list[tuple[float, float]]:
    prazos, taxas = _pontos(dia)
    if metodo == "nss":
        ajuste = ajustar_nss(prazos, taxas)
        if ajuste is None:
            return []
        return [(v, taxa_nss(ajuste, v)) for v in VERTICES_ANOS]
    return [(v, flat_forward(prazos, taxas, v)) for v in VERTICES_ANOS]


def montar_curvas(taxas: pd.DataFrame, metodo: str = "flat_forward") -> pd.DataFrame:
    """Vértices de cada dia (nominal, real e implícita).

    `flat_forward` (padrão): só onde há títulos dos dois lados do prazo. `nss`: também além do título
    mais longo; esses vértices são extrapolados (hipótese do modelo, não dado): os de `prazo_anos`
    maior que `maior_prazo_anos`.
    """
    if metodo not in METODOS:
        raise ValueError(f"metodo deve ser um de {METODOS}, não {metodo!r}")
    linhas = []
    for curva, titulo in TITULOS_DAS_CURVAS.items():
        do_titulo = taxas[taxas["titulo"] == titulo]
        for data_base, dia in do_titulo.groupby("data_base"):
            maior = float(dia["prazo_anos"].max())
            for prazo, taxa in _vertices(dia, metodo):
                if math.isfinite(taxa) and taxa > -1:
                    linhas.append((data_base, curva, prazo, taxa, len(dia), maior))
    curvas = pd.DataFrame(
        linhas,
        columns=[
            "data_base",
            "curva",
            "prazo_anos",
            "taxa",
            "titulos",
            "maior_prazo_anos",
        ],
    )
    chave = ["data_base", "prazo_anos"]
    nominal = curvas[curvas["curva"] == "nominal"].set_index(chave)
    real = curvas[curvas["curva"] == "real"].set_index(chave)
    juntos = nominal.join(real, how="inner", lsuffix="_n", rsuffix="_r")
    implicita = pd.DataFrame(
        {
            "curva": "implicita",
            "taxa": (1 + juntos["taxa_n"]) / (1 + juntos["taxa_r"]) - 1,
            "titulos": juntos["titulos_n"] + juntos["titulos_r"],
            "maior_prazo_anos": juntos[
                ["maior_prazo_anos_n", "maior_prazo_anos_r"]
            ].min(axis=1),
        }
    ).reset_index()
    curvas = pd.concat([curvas, implicita], ignore_index=True)
    curvas["disponivel_em"] = proximo_dia_util(curvas["data_base"])
    return curvas.sort_values(["data_base", "curva", "prazo_anos"]).reset_index(
        drop=True
    )


def montar(conexao: sa.Connection, pasta: Path, agora: datetime) -> dict[int, int]:
    """`<pasta>/curva_juros/<ano>.parquet` a partir do CSV do Tesouro Direto mais recente."""
    for original in originais_mais_recentes(conexao, FONTE):
        if not original.url.lower().endswith(".csv"):
            continue  # o pacote também tem o PDF de metadados
        conteudo = acervo.ler_original(original.caminho_do_original)
        if conteudo is None:
            continue
        curvas = montar_curvas(ler_tesouro_direto(conteudo)).assign(
            origem_sha256=original.sha256,
            origem_coletada_em=pd.Timestamp(original.baixado_em).isoformat(),
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )
        linhas: dict[int, int] = {}
        for ano, do_ano in curvas.groupby(curvas["data_base"].dt.year):
            gravar_se_mudou(
                do_ano,
                pasta / TABELA / f"{ano}.parquet",
                [{"url": original.url, "sha256": original.sha256}],
                ["data_base", "curva", "prazo_anos"],
                carimbos=LINHAGEM,
            )
            linhas[int(ano)] = len(do_ano)
        return linhas
    return {}
