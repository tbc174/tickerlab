"""Régua do middle market dos negócios de M&A: a receita anual da alvo no último exercício antes do
negócio, entre R$ 30 e 500 milhões (ADR 0082, item 2; série 5 do plano de M&A, passo 5).

**`middle_market`** (testes em `tests/test_base_ma_regua.py`):
- `sim` ou `nao` pela **receita** conhecida: 30 e 500 milhões contam como `sim` (limites inclusos);
- `nao` pelo **porte** do CNPJ quando a alvo é ME ou EPP (receita até R$ 4,8 milhões por lei): é um
  limite grosso, e "demais" não decide nada;
- `desconhecido` sem nenhuma das duas. **O valor da régua nunca é estimado**: sem receita de um
  documento, `receita` fica vazia.

**Sem olhar o futuro:** só vale o que já era público **antes** do `conhecido_em` do negócio
(`ma_datas`): a receita de documento entregue no mesmo dia ou depois não existe para a régua (a CVM
não informa a hora da entrega), e o porte só vale de um arquivo da Receita baixado antes. O exercício
é o último que terminou antes do negócio: antes do `fechamento_em` quando o CNPJ o deu, senão antes do
`conhecido_em` (sem a data do negócio, o exercício pode já ser de depois dele; a ficha diz isso).

**De onde vem a receita** (cada linha diz a fonte e o documento): o exercício mais novo ganha; no mesmo
exercício, a ordem da ADR 0082:
1. `cpc15-compradora`: nota de combinação de negócios da compradora aberta (CPC 15), lida à mão;
2. `dfp-alvo`: a DRE anual da própria alvo na CVM (`demonstracoes_como_era`), quando ela tem registro;
3. `balanco-alvo`: balanço publicado da alvo fechada (jornal, Diário Oficial ou o site dela), lido à mão;
4. `cade`: a faixa de faturamento do ato de concentração, lida à mão.
As lidas à mão ficam em `base/conferidas/ma_receitas.csv`, cada linha com o documento, o dia em que
ele ficou público e o dia da conferência.
"""

from collections.abc import Sequence
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from base.amostra.demonstracoes import UM_ANO, fatos
from base.ma_datas import Guardado
from base.ma_ligacao import Arquivo, partes_do_zip

MINIMO, MAXIMO = 30_000_000.0, 500_000_000.0
SIM, NAO, DESCONHECIDO = "sim", "nao", "desconhecido"
CPC15, DFP, BALANCO, CADE = "cpc15-compradora", "dfp-alvo", "balanco-alvo", "cade"
PREFERENCIA = (CPC15, DFP, BALANCO, CADE)  # no mesmo exercício, nessa ordem
PELA_RECEITA, PELO_PORTE = "receita", "porte_me_epp"
ALVO_SEM_CNPJ, VARIAS_ALVOS, SEM_RECEITA = (
    "alvo_sem_cnpj",
    "varias_alvos",
    "sem_receita",
)
ME, EPP = (
    "01",
    "03",
)  # códigos de porte dos `Empresas*.zip` (00 não informado, 05 demais)
FUSO = ZoneInfo("America/Sao_Paulo")  # a CVM data a entrega no dia de Brasília
CONFERIDAS = Path(__file__).resolve().parent / "conferidas" / "ma_receitas.csv"
CHAVE = ["assessoria", "url"]

COLUNAS_DAS_RECEITAS = (
    "cnpj_raiz",
    "exercicio_fim",
    "receita",
    "fonte",
    "documento",
    "documento_sha256",
    "publico_em",
)
COLUNAS_DOS_PORTES = (
    "cnpj_raiz",
    "porte",
    "porte_publico_em",
    "porte_prova_url",
    "porte_prova_sha256",
)
COLUNAS = (
    "assessoria",
    "url",
    "id_negocio",
    "alvo_cnpj_raiz",
    "conhecido_em_do_negocio",
    "fechamento_em",
    "middle_market",
    "motivo",
    "receita",
    "receita_exercicio_fim",
    "receita_fonte",
    "receita_documento",
    "receita_documento_sha256",
    "receita_publico_em",
    "porte",
    "porte_publico_em",
    "porte_prova_url",
    "porte_prova_sha256",
)


# --- as fontes -------------------------------------------------------------------------------------
def receitas_da_cvm(demonstracoes: pd.DataFrame, raizes: set[str]) -> pd.DataFrame:
    """A receita anual (DRE, conta 3.01) de cada versão de cada DFP das `raizes`, consolidado antes."""
    raiz = demonstracoes["cnpj"].astype(str).str.replace(r"\D", "", regex=True).str[:8]
    todos = fatos(demonstracoes[raiz.isin(raizes)])
    anuais = todos[
        (todos["indicador"] == "receita") & ((todos["fim"] - todos["inicio"]) >= UM_ANO)
    ]
    anuais = anuais.assign(_ordem=(anuais["grupo"] != "con").astype(int)).sort_values(
        "_ordem", kind="stable"
    )
    versao = ["cnpj", "fim", "documento", "referencia", "versao", "ordem"]
    anuais = anuais.drop_duplicates(versao)
    return pd.DataFrame(
        {
            "cnpj_raiz": anuais["cnpj"].str.replace(r"\D", "", regex=True).str[:8],
            "exercicio_fim": anuais["fim"].dt.date,
            "receita": anuais["valor"].astype(float),
            "fonte": DFP,
            "documento": (
                anuais["documento"].astype(str) + " " + anuais["cnpj"].astype(str) + " "
                + pd.to_datetime(anuais["referencia"]).dt.strftime("%Y-%m-%d") + " v"
                + anuais["versao"].astype(str) + " (" + anuais["grupo"] + ")"
            ),
            "documento_sha256": None,
            "publico_em": anuais["divulgado_em"].dt.date,
        },
        columns=list(COLUNAS_DAS_RECEITAS),
    ).reset_index(drop=True)  # fmt: skip


def receitas_conferidas(arquivo: Path = CONFERIDAS) -> pd.DataFrame:
    """As receitas lidas à mão (CPC 15, balanço publicado, CADE): sem o dia do documento, recusa."""
    lidas = pd.read_csv(arquivo, sep=";", dtype=str, keep_default_na=False)
    vazias = lidas["publico_em"].str.strip() == ""
    if vazias.any():
        raise ValueError(
            f"{arquivo.name}: linha sem publico_em (o dia em que o documento ficou público)"
        )
    estranhas = set(lidas["fonte"]) - set(PREFERENCIA)
    if estranhas:
        raise ValueError(f"{arquivo.name}: fonte fora da régua: {sorted(estranhas)}")
    return pd.DataFrame(
        {
            "cnpj_raiz": lidas["cnpj_raiz"].str.zfill(8),
            "exercicio_fim": pd.to_datetime(lidas["exercicio_fim"]).dt.date,
            "receita": lidas["receita"].astype(float),
            "fonte": lidas["fonte"],
            "documento": lidas["documento"],
            "documento_sha256": None,
            "publico_em": pd.to_datetime(lidas["publico_em"]).dt.date,
        },
        columns=list(COLUNAS_DAS_RECEITAS),
    )


PORTE = 5  # coluna dos `Empresas*.zip` (0 CNPJ básico, 1 razão social, 2 natureza, ..., 5 porte)


def portes_do_cnpj(
    arquivos: Sequence[tuple[Arquivo, Guardado]], raizes: set[str]
) -> pd.DataFrame:
    """O porte das `raizes` em cada arquivo `Empresas*` guardado, com a prova (só raiz e porte são lidos)."""
    achados = []
    for arquivo, guardado in arquivos:
        for parte in partes_do_zip(arquivo, [0, PORTE]):
            parte = parte[parte[0].isin(raizes)]
            achados.append(
                pd.DataFrame(
                    {
                        "cnpj_raiz": parte[0],
                        "porte": parte[PORTE].str.strip(),
                        "porte_publico_em": guardado.baixado_em,
                        "porte_prova_url": guardado.url,
                        "porte_prova_sha256": guardado.sha256,
                    }
                )
            )
    if not achados:
        return pd.DataFrame(columns=list(COLUNAS_DOS_PORTES))
    return pd.concat(achados, ignore_index=True)[list(COLUNAS_DOS_PORTES)].astype(
        object
    )


# --- a régua ---------------------------------------------------------------------------------------
def _alvos(partes: pd.DataFrame) -> pd.DataFrame:
    """Por página: a raiz da alvo, se há exatamente uma, e o motivo quando não há."""
    alvos = partes[partes["papel"] == "alvo"]
    raizes = alvos.dropna(subset=["cnpj_raiz"]).groupby(CHAVE)["cnpj_raiz"].unique()
    return pd.DataFrame(
        {
            "alvo_cnpj_raiz": raizes.map(lambda r: r[0] if len(r) == 1 else None),
            "_motivo": raizes.map(lambda r: None if len(r) == 1 else VARIAS_ALVOS),
        }
    ).reset_index()


def _dia_do_conhecido(momento: pd.Timestamp) -> object:
    return pd.Timestamp(momento).tz_convert(FUSO).date()


def _receita(linha: pd.Series, receitas: pd.DataFrame) -> pd.Series | None:
    """A receita do último exercício antes do negócio, só de documento público antes do `conhecido_em`."""
    conhecido = _dia_do_conhecido(linha["conhecido_em_do_negocio"])
    fechamento = linha["fechamento_em"]
    negocio = pd.Timestamp(fechamento).date() if pd.notna(fechamento) else conhecido
    candidatas = receitas[
        (receitas["cnpj_raiz"] == linha["alvo_cnpj_raiz"])
        & (receitas["publico_em"] < conhecido)
        & (receitas["exercicio_fim"] < negocio)
    ]
    if candidatas.empty:
        return None
    ordem = candidatas.assign(_fonte=candidatas["fonte"].map(PREFERENCIA.index))
    ordem = ordem.sort_values(
        ["exercicio_fim", "_fonte", "publico_em"], ascending=[False, True, False]
    )
    return ordem.iloc[0]


def _porte(linha: pd.Series, portes: pd.DataFrame) -> pd.Series | None:
    """O porte do arquivo mais novo baixado antes do `conhecido_em`."""
    antes = portes[
        (portes["cnpj_raiz"] == linha["alvo_cnpj_raiz"])
        & (
            pd.to_datetime(portes["porte_publico_em"], utc=True)
            < linha["conhecido_em_do_negocio"]
        )
    ]
    if antes.empty:
        return None
    return antes.sort_values("porte_publico_em").iloc[-1]


def _medir_linha(
    linha: pd.Series, receitas: pd.DataFrame, portes: pd.DataFrame
) -> dict:
    if pd.isna(linha["alvo_cnpj_raiz"]):
        motivo = (
            linha["_motivo"] if isinstance(linha["_motivo"], str) else ALVO_SEM_CNPJ
        )
        return {"middle_market": DESCONHECIDO, "motivo": motivo}
    saida: dict[str, object] = {"middle_market": DESCONHECIDO}
    achada = _receita(linha, receitas)
    porte = _porte(linha, portes)
    if porte is not None:
        saida |= {c: porte[c] for c in COLUNAS_DOS_PORTES if c != "cnpj_raiz"}
    if achada is not None:
        dentro = MINIMO <= achada["receita"] <= MAXIMO
        return saida | {
            "middle_market": SIM if dentro else NAO,
            "motivo": PELA_RECEITA,
            "receita": achada["receita"],
            "receita_exercicio_fim": achada["exercicio_fim"],
            "receita_fonte": achada["fonte"],
            "receita_documento": achada["documento"],
            "receita_documento_sha256": achada["documento_sha256"],
            "receita_publico_em": achada["publico_em"],
        }
    if porte is not None and porte["porte"] in (ME, EPP):
        return saida | {"middle_market": NAO, "motivo": PELO_PORTE}
    return saida | {"motivo": SEM_RECEITA}


def medir(
    datas: pd.DataFrame,
    partes: pd.DataFrame,
    receitas: pd.DataFrame,
    portes: pd.DataFrame,
) -> pd.DataFrame:
    """Uma linha por página de `ma_datas`: a régua, a receita (com a fonte) e o porte usado."""
    linhas = datas[
        [*CHAVE, "id_negocio", "conhecido_em_do_negocio", "fechamento_em"]
    ].merge(_alvos(partes), on=CHAVE, how="left")
    linhas["conhecido_em_do_negocio"] = pd.to_datetime(
        linhas["conhecido_em_do_negocio"], utc=True
    )
    medidas = pd.DataFrame(
        [_medir_linha(linha, receitas, portes) for _, linha in linhas.iterrows()],
        index=linhas.index,
    )
    saida = pd.concat([linhas.drop(columns="_motivo"), medidas], axis=1)
    return (
        saida.reindex(columns=list(COLUNAS))
        .astype(
            {
                c: object
                for c in COLUNAS
                if c not in ("conhecido_em_do_negocio", "receita")
            }
        )
        .astype({"receita": float})
        .sort_values(CHAVE, ignore_index=True)
    )


def resumo(saida: pd.DataFrame) -> str:
    """Os números da conferência: quantos sim, não e desconhecido, e de onde veio cada resposta."""
    regua = saida["middle_market"].value_counts()
    motivo = saida["motivo"].value_counts()
    fontes = saida["receita_fonte"].value_counts()
    pelas = ", ".join(f"pela {f} {n}" for f, n in fontes.items()) or "nenhuma"
    return (
        f"{len(saida)} páginas; middle_market sim {regua.get(SIM, 0)}, nao {regua.get(NAO, 0)}, "
        f"desconhecido {regua.get(DESCONHECIDO, 0)}; receita {pelas}; "
        f"porte ME/EPP {motivo.get(PELO_PORTE, 0)}; desconhecido: alvo sem CNPJ "
        f"{motivo.get(ALVO_SEM_CNPJ, 0)}, sem receita antes do negócio {motivo.get(SEM_RECEITA, 0)}, "
        f"mais de uma alvo {motivo.get(VARIAS_ALVOS, 0)}"
    )
