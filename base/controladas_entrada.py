"""Quando cada controlada entrou no FRE da companhia: a primeira vez que o par aparece (linha 1045).

`controladas` (`base/controladas.py`) guarda uma linha por companhia, FRE e sociedade, de 2010 em diante. Quem
pergunta "essa companhia já tinha essa controlada antes do negócio?" não pode usar a `referencia` dessa tabela:
ela é o fim do exercício e, no FRE de 2026 entregue em junho, é 2026-12-31 (futura). Esta tabela guarda, por par
**companhia ↔ controlada**, a primeira entrega em que o par apareceu:

- **A chave do par é a raiz de 8 dígitos do CNPJ da controlada**, não o CNPJ inteiro: a Dasa informou a Ímpar com
  um CNPJ de filial em 2023 e 2024 e com outro em 2025 (mesma raiz). Pelo CNPJ inteiro seriam dois pares, e o
  segundo pareceria uma entrada nova em 2025. `cnpj` é o CNPJ informado na primeira entrega.
- **`conhecido_em` é o recebimento do documento na CVM** (`DT_RECEB`), o dia em que o par ficou público; é a data
  que serve a "sem olhar o futuro". `primeira_referencia` e `primeiro_ano_no_fre` saem da mesma entrega (a que
  tornou o par público primeiro), nunca de uma reentrega posterior de um FRE mais velho.
- **`entrada_observada`**: verdadeiro quando a companhia já tinha entregado, antes dessa data, um FRE de referência
  mais antiga **sem** o par. Falso quer dizer que o par já estava no primeiro FRE que a base vê da companhia: a
  ligação existe "não depois de" `primeiro_ano_no_fre`, e a entrada de fato pode ser anterior (a Cantu entrou na
  CVM em 2022; a CPX estava no primeiro FRE dela). Isto não é a data do negócio nem a da compra: é o FRE.
- **A CVM só publica a versão mais nova de cada FRE**, então uma ligação informada na versão 1 e mantida na 3 só
  aparece na 3: `conhecido_em` pode ser **depois** da data real em que a companhia a informou, nunca antes.
- Só pessoa jurídica com CNPJ: sociedade sem CNPJ (de fora do país) fica de fora, "não conferido", e nunca se liga
  pelo nome; CNPJ que não confere e CPF completado com zeros também (`base/recorte_dos_compradores.py`). A tabela
  não leva razão social, nome nem CPF.

Sem Streamlit; pandas só. Roda no servidor de casa, depois de `controladas` (`scripts/montar_base_historica.py`).
"""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from base.cnpj import normalizar_cnpj
from base.parquet import (
    LINHAGEM,
    arquivos_atuais,
    gravar_se_mudou,
    origem_de_tabela,
)
from base.recorte_dos_compradores import cnpj_de_empresa, cnpj_que_confere
from src.versao_do_codigo import versao_do_codigo

TABELA = "controladas_entrada"
TABELA_DE_ORIGEM = "controladas"
CHAVE = ("cnpj_companhia", "raiz_da_controlada")
COLUNAS = (
    "cnpj_companhia", "raiz_da_controlada", "cnpj", "primeiro_ano_no_fre",
    "primeira_referencia", "conhecido_em", "tipo_na_entrada", "entrada_observada",
)  # fmt: skip
LEITURA = ("cnpj_companhia", "referencia", "conhecido_em", "cnpj", "tipo")
TAMANHO_DA_RAIZ = 8


@dataclass(frozen=True)
class Resultado:
    """A tabela e o que ficou de fora, contado por linha de `controladas` (nunca com o CNPJ, que vai ao log)."""

    tabela: pd.DataFrame
    sem_data: int  # sem o recebimento na CVM: não há como dizer quando ficou público
    sem_cnpj: int  # sociedade sem CNPJ (de fora do país): não conferido
    nao_confere: int  # CNPJ de 14 caracteres que não confere, CPF completado com zeros ou companhia sem CNPJ certo


def _dias(coluna: pd.Series) -> pd.Series:
    return pd.to_datetime(coluna, errors="coerce")


def _entregas_da_companhia(controladas: pd.DataFrame) -> pd.DataFrame:
    """Cada FRE (companhia, referência) com o 1º recebimento, tenha ele sociedade com CNPJ ou não."""
    return (
        controladas.groupby(["cnpj_companhia", "referencia"], as_index=False)[
            "conhecido_em"
        ].min()
    ).rename(
        columns={"referencia": "referencia_anterior", "conhecido_em": "recebido_em"}
    )


def _entrada_observada(primeiras: pd.DataFrame, entregas: pd.DataFrame) -> pd.Series:
    """A companhia já tinha entregue, antes do dia da entrada, um FRE mais velho sem o par."""
    antes = primeiras[
        ["cnpj_companhia", "raiz_da_controlada", "primeira", "recebido"]
    ].merge(entregas, on="cnpj_companhia")
    antes = antes[
        (antes["referencia_anterior"] < antes["primeira"])
        & (antes["recebido_em"] <= antes["recebido"])
    ]
    com_anterior = set(
        zip(antes["cnpj_companhia"], antes["raiz_da_controlada"], strict=True)
    )
    return pd.Series(
        [
            (c, r) in com_anterior
            for c, r in zip(
                primeiras["cnpj_companhia"],
                primeiras["raiz_da_controlada"],
                strict=True,
            )
        ],
        index=primeiras.index,
    )


def primeira_entrada(controladas: pd.DataFrame) -> Resultado:
    """A primeira entrega do FRE em que cada par companhia ↔ controlada aparece.

    `controladas` é a tabela da base (precisa de `LEITURA`); cada linha é uma sociedade de um FRE entregue.
    """
    base = pd.DataFrame(controladas[list(LEITURA)]).copy()
    base["referencia"] = _dias(base["referencia"])
    base["conhecido_em"] = _dias(base["conhecido_em"])
    com_data = base[base["referencia"].notna() & base["conhecido_em"].notna()]
    sem_data = len(base) - len(com_data)
    entregas = _entregas_da_companhia(com_data)

    com_cnpj = com_data[com_data["cnpj"].notna()]
    sem_cnpj = len(com_data) - len(com_cnpj)
    certas = com_cnpj["cnpj"].map(cnpj_de_empresa) & com_cnpj["cnpj_companhia"].map(
        cnpj_que_confere
    )
    nao_confere = int((~certas).sum())
    pares = com_cnpj[certas].assign(
        raiz_da_controlada=lambda q: q["cnpj"].str[:TAMANHO_DA_RAIZ],
        tipo=lambda q: q["tipo"].replace("", None),
    )
    primeiras = (
        pares.sort_values(
            [*CHAVE, "conhecido_em", "referencia", "cnpj", "tipo"], na_position="last"
        )
        .drop_duplicates(list(CHAVE))
        .rename(columns={"referencia": "primeira", "conhecido_em": "recebido"})
        .reset_index(drop=True)
    )
    tabela = pd.DataFrame(
        {
            "cnpj_companhia": primeiras["cnpj_companhia"],
            "raiz_da_controlada": primeiras["raiz_da_controlada"],
            "cnpj": primeiras["cnpj"],
            "primeiro_ano_no_fre": primeiras["primeira"].dt.year.astype("int64"),
            "primeira_referencia": primeiras["primeira"].dt.date,
            "conhecido_em": primeiras["recebido"].dt.date,
            "tipo_na_entrada": primeiras["tipo"],
            "entrada_observada": _entrada_observada(primeiras, entregas).astype(bool)
            if len(primeiras)
            else pd.Series([], dtype=bool),
        }
    )
    return Resultado(
        pd.DataFrame(tabela[list(COLUNAS)]).reset_index(drop=True),
        sem_data=sem_data,
        sem_cnpj=sem_cnpj,
        nao_confere=nao_confere,
    )


def _dia(valor: object) -> str | None:
    return (
        None
        if valor is None or pd.isna(valor)
        else pd.Timestamp(valor).date().isoformat()
    )  # type: ignore[arg-type]


def _raizes(cnpjs: list[str]) -> set[str]:
    raizes = set()
    for texto in cnpjs:
        completo = normalizar_cnpj(texto)
        if completo:
            raizes.add(completo[:TAMANHO_DA_RAIZ])
    return raizes


def entradas_ate(
    tabela: pd.DataFrame,
    dia: date,
    *,
    companhias: list[str] | None = None,
    controladas: list[str] | None = None,
) -> list[dict[str, object]]:
    """As entradas já públicas em `dia` (`conhecido_em <= dia`), em tipos simples (texto, inteiro, booleano).

    `companhias`: CNPJs de quem informou o FRE; `controladas`: CNPJs (inteiros ou só a raiz) das sociedades.
    Sem filtro, tudo o que já era público. Cada item tem as colunas de `COLUNAS`, com as datas em ISO.
    """
    achadas = tabela[_dias(tabela["conhecido_em"]) <= pd.Timestamp(dia)]
    if companhias is not None:
        achadas = achadas[
            achadas["cnpj_companhia"].isin(
                [c for c in map(normalizar_cnpj, companhias) if c]
            )
        ]
    if controladas is not None:
        achadas = achadas[achadas["raiz_da_controlada"].isin(_raizes(controladas))]
    achadas = achadas.sort_values(list(CHAVE))
    return [
        {
            "cnpj_companhia": str(linha["cnpj_companhia"]),
            "raiz_da_controlada": str(linha["raiz_da_controlada"]),
            "cnpj": str(linha["cnpj"]),
            "primeiro_ano_no_fre": int(linha["primeiro_ano_no_fre"]),
            "primeira_referencia": _dia(linha["primeira_referencia"]),
            "conhecido_em": _dia(linha["conhecido_em"]),
            "tipo_na_entrada": None
            if pd.isna(linha["tipo_na_entrada"])
            else str(linha["tipo_na_entrada"]),
            "entrada_observada": bool(linha["entrada_observada"]),
        }
        for _, linha in achadas.iterrows()
    ]


def montar(pasta: Path, agora: datetime) -> int:
    """`<pasta>/controladas_entrada/controladas_entrada.parquet`, a partir de `<pasta>/controladas/*.parquet`.

    Devolve quantos pares gravou (0, e nada gravado, sem `controladas`). Não regrava o que não mudou.
    """
    anos = arquivos_atuais(pasta / TABELA_DE_ORIGEM)
    if not anos:
        return 0
    lidas = pd.concat(
        [pd.read_parquet(ano, columns=list(LEITURA)) for ano in anos],
        ignore_index=True,
    )
    resultado = primeira_entrada(lidas)
    tabela = resultado.tabela.assign(
        montado_em=agora.isoformat(), versao_do_codigo=versao_do_codigo()
    )
    gravar_se_mudou(
        tabela,
        pasta / TABELA / f"{TABELA}.parquet",
        [origem_de_tabela(ano, pasta) for ano in anos],
        list(CHAVE),
        carimbos=LINHAGEM,
    )
    return len(tabela)
