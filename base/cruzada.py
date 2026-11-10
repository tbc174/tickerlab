"""Conferência cruzada: o mesmo número lido em duas fontes (exigência 6 da ADR 0027; plano do placar, PR 1).

Cada `Par` diz o que se compara, por qual chave, com que tolerância e **quão independentes são as duas
fontes**: `MESMO_DOCUMENTO` pega erro **nosso** de leitura, `OUTRO_ORGAO` pega erro **da fonte**. O placar soma
as independências separadas (uma conferência contra a própria fonte não prova o que uma de outro órgão prova).

Só regra: as tabelas chegam em DataFrames (quem lê a base pela porta é `scripts/conferir_cruzado.py`) e o resultado
sai em tipos simples. Divergência sem explicação deixa o relatório vermelho; a explicada por uma pessoa fica em
`conferidas/divergencias_explicadas.csv` (par, chave, explicação, data), como as canceladas explicadas.
"""

import csv
import io
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

MESMO_DOCUMENTO = "mesmo documento, outro canal"
MESMA_FONTE_OUTRO_DOCUMENTO = "mesma fonte, outro documento"
OUTRO_ORGAO = "outro órgão"
INDEPENDENCIAS = (MESMO_DOCUMENTO, MESMA_FONTE_OUTRO_DOCUMENTO, OUTRO_ORGAO)

CAMINHO_EXPLICADAS = (
    Path(__file__).parent / "conferidas" / "divergencias_explicadas.csv"
)
MAXIMO_DE_DIVERGENCIAS_NO_JSON = (
    50  # o bastante para achar o defeito, sem inchar o arquivo do dia
)
ARREDONDAMENTO = (
    1e-9  # só absorve o erro de ponto flutuante; a tolerância de verdade fica no `Par`
)

Preparar = Callable[[Mapping[str, pd.DataFrame]], tuple[pd.DataFrame, pd.DataFrame]]


@dataclass(frozen=True)
class Tolerancia:
    """Diferença aceita: o maior entre `absoluta` (unidades da fonte) e `relativa` (fração do maior valor)."""

    absoluta: float = 0.0
    relativa: float = 0.0

    def aceita(self, a: float, b: float) -> bool:
        folga = max(self.absoluta, self.relativa * max(abs(a), abs(b)))
        return abs(a - b) <= folga + ARREDONDAMENTO


@dataclass(frozen=True)
class Par:
    nome: str
    descricao: str
    chave: tuple[str, ...]
    tolerancia: Tolerancia
    independencia: str
    # tabelas lidas da base → (lado A, lado B), cada um com as colunas da chave e `valor`
    preparar: Preparar | None = None
    # as tabelas do dicionário para as quais o par é prova (a prontidão da API é por tabela)
    tabelas: tuple[str, ...] = ()
    # Regra: o par só conta para a exigência 6 quando os dois lados medem o mesmo perímetro. Par cujos
    # lados medem perímetros diferentes fica visível, rebaixado, com a causa escrita aqui: nunca
    # prova uma tabela, nunca deixa o placar vermelho.
    informativo: str = ""


@dataclass(frozen=True)
class Divergencia:
    chave: str
    a: float
    b: float
    diferenca: float
    diferenca_pct: float
    explicada: bool


@dataclass(frozen=True)
class Relatorio:
    par: str
    independencia: str
    comparadas: int
    iguais: int
    pela_tolerancia: int
    diferentes: int
    so_em_a: int
    so_em_b: int
    divergencias: list[Divergencia] = field(default_factory=list)
    tabelas: tuple[str, ...] = ()
    sem_dados: str = ""  # por que o par não rodou (tabela ausente); vazio quando rodou
    informativo: str = ""  # a causa de o par não valer para a exigência 6 (vazio: vale)

    @property
    def sem_explicacao(self) -> int:
        return sum(not d.explicada for d in self.divergencias)

    @property
    def vermelho(self) -> bool:
        return self.sem_explicacao > 0 and not self.informativo

    def como_dict(self) -> dict[str, object]:
        return {
            "nome": self.par,
            "independencia": self.independencia,
            "comparadas": self.comparadas,
            "iguais": self.iguais,
            "pela_tolerancia": self.pela_tolerancia,
            "diferentes": self.diferentes,
            "so_em_a": self.so_em_a,
            "so_em_b": self.so_em_b,
            "sem_explicacao": self.sem_explicacao,
            "vermelho": self.vermelho,
            "tabelas": list(self.tabelas),
            "sem_dados": self.sem_dados,
            "informativo": self.informativo,
            "divergencias": [
                vars(d) for d in self.divergencias[:MAXIMO_DE_DIVERGENCIAS_NO_JSON]
            ],
        }


def ler_explicadas(texto: str) -> set[tuple[str, str]]:
    """As divergências já conferidas por uma pessoa: pares (par, chave)."""
    leitor = csv.DictReader(io.StringIO(texto), delimiter=";")
    return {(linha["par"], linha["chave"]) for linha in leitor if linha.get("par")}


def _texto_da_coluna(coluna: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(coluna):
        return coluna.dt.strftime("%Y-%m-%d")
    return coluna.astype(str)


def _lado(frame: pd.DataFrame, chave: tuple[str, ...]) -> pd.Series:
    """Valor por chave; vazio não se compara e chave repetida fica com a última linha."""
    com_valor = frame.dropna(subset=["valor"])
    partes = [_texto_da_coluna(com_valor[coluna]) for coluna in chave]
    indice = ["|".join(textos) for textos in zip(*partes, strict=True)]
    serie = pd.Series(com_valor["valor"].to_numpy(dtype=float), index=indice)
    return serie[~serie.index.duplicated(keep="last")]


def par_sem_dados(par: Par, motivo: str) -> Relatorio:
    """Par que não rodou: não prova nada (zero comparações) e não finge que passou."""
    return Relatorio(
        par.nome,
        par.independencia,
        0,
        0,
        0,
        0,
        0,
        0,
        tabelas=par.tabelas,
        sem_dados=motivo,
        informativo=par.informativo,
    )


def comparar(
    par: Par,
    a: pd.DataFrame,
    b: pd.DataFrame,
    explicadas: set[tuple[str, str]],
) -> Relatorio:
    lado_a, lado_b = _lado(a, par.chave), _lado(b, par.chave)
    comuns = lado_a.index.intersection(lado_b.index)
    iguais = pela_tolerancia = 0
    divergencias: list[Divergencia] = []
    for chave in sorted(comuns):
        va, vb = float(lado_a[chave]), float(lado_b[chave])
        if va == vb:
            iguais += 1
        elif par.tolerancia.aceita(va, vb):
            pela_tolerancia += 1
        else:
            maior = max(abs(va), abs(vb))
            divergencias.append(
                Divergencia(
                    chave=chave,
                    a=va,
                    b=vb,
                    diferenca=abs(va - vb),
                    diferenca_pct=abs(va - vb) / maior * 100,
                    explicada=(par.nome, chave) in explicadas,
                )
            )
    return Relatorio(
        par=par.nome,
        independencia=par.independencia,
        comparadas=len(comuns),
        iguais=iguais,
        pela_tolerancia=pela_tolerancia,
        diferentes=len(divergencias),
        so_em_a=len(lado_a.index.difference(lado_b.index)),
        so_em_b=len(lado_b.index.difference(lado_a.index)),
        divergencias=divergencias,
        tabelas=par.tabelas,
        informativo=par.informativo,
    )


def montar_relatorio_do_dia(
    dia: str, relatorios: Iterable[Relatorio]
) -> dict[str, object]:
    """O JSON do dia (`<acervo>/placar/<dia>/cruzada.json`): por par e somado por independência."""
    relatorios = list(relatorios)
    por_independencia: dict[str, dict[str, int]] = defaultdict(
        lambda: {"comparadas": 0, "diferentes": 0, "sem_explicacao": 0}
    )
    for r in relatorios:
        if r.informativo:  # não conta para a exigência 6
            continue
        soma = por_independencia[r.independencia]
        soma["comparadas"] += r.comparadas
        soma["diferentes"] += r.diferentes
        soma["sem_explicacao"] += r.sem_explicacao
    return {
        "dia": dia,
        "pares": [r.como_dict() for r in relatorios],
        "por_independencia": dict(por_independencia),
        "vermelho": any(r.vermelho for r in relatorios),
    }


# ---- os pares ----------------------------------------------------------------------------------

SGS_META = "bcb-sgs-432"


def _preparar_selic(
    tabelas: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A meta do SGS 432 que valia no dia seguinte a cada reunião, contra a meta escrita no comunicado."""
    selic = tabelas["bcb_selic_focus"]
    sgs = (
        selic[selic["serie"] == SGS_META]
        .sort_values("divulgado_em")
        .drop_duplicates("referencia", keep="last")
        .sort_values("referencia")
    )
    copom = tabelas["copom_reunioes"].copy()
    copom["data"] = pd.to_datetime(copom["data"])
    copom["meta_selic"] = pd.to_numeric(copom["meta_selic"])
    copom["vale_desde"] = copom["data"] + pd.Timedelta(days=1)
    casado = pd.merge_asof(
        copom.sort_values("vale_desde"),
        sgs[["referencia", "valor"]].rename(columns={"valor": "valor_sgs"}),
        left_on="vale_desde",
        right_on="referencia",
        direction="backward",
    )
    a = casado[["data"]].assign(valor=casado["valor_sgs"])
    b = casado[["data"]].assign(valor=casado["meta_selic"])
    return a, b


def _total_do_ifdata(
    ifdata: pd.DataFrame, ligacao: pd.DataFrame, coluna: str
) -> pd.DataFrame:
    """Um valor por banco e data-base: o conglomerado financeiro (tipo 2); sem ele, o prudencial (tipo 1)."""
    linhas = ifdata[
        (ifdata["relatorio"] == 1)
        & (ifdata["coluna"] == coluna)
        & ifdata["tipo_instituicao"].isin([1, 2])
    ]
    com_cnpj = linhas.merge(
        ligacao[["data_base", "cod_inst", "cnpj"]], on=["data_base", "cod_inst"]
    )
    preferidos = com_cnpj.sort_values(
        "tipo_instituicao", ascending=False
    ).drop_duplicates(["cnpj", "data_base"], keep="last")
    return preferidos[["cnpj", "data_base"]].assign(valor=preferidos["saldo"])


def _dfp_consolidada(dfp: pd.DataFrame, bancos: pd.Series) -> pd.DataFrame:
    base = dfp[
        (dfp["grupo"] == "con")
        & (dfp["documento"] == "DFP")
        & (dfp["ordem"] == "ultimo")
        & dfp["cnpj"].isin(bancos)
    ]
    return base.rename(columns={"referencia": "data_base"})


def _ativo_total_da_dfp(dfp: pd.DataFrame) -> pd.DataFrame:
    return dfp[(dfp["demonstracao"] == "BPA") & (dfp["conta"] == "1")]


def _patrimonio_da_dfp(dfp: pd.DataFrame) -> pd.DataFrame:
    # o plano dos bancos põe o patrimônio líquido em 2.07 e o das demais empresas em 2.03: acha pelo nome
    return dfp[
        (dfp["demonstracao"] == "BPP")
        & dfp["conta"].str.fullmatch(r"2\.\d\d")
        & dfp["descricao"].str.startswith("Patrimônio Líquido")
    ]


def _preparar_banco(
    tabelas: Mapping[str, pd.DataFrame],
    coluna_do_ifdata: str,
    linhas_da_dfp: Callable[[pd.DataFrame], pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ligacao = tabelas["ligacao_dos_bancos"].dropna(subset=["cnpj"])
    a = _total_do_ifdata(tabelas["ifdata_valores"], ligacao, coluna_do_ifdata)
    dfp = linhas_da_dfp(
        _dfp_consolidada(tabelas["demonstracoes_como_era"], ligacao["cnpj"])
    )
    return a, dfp[["cnpj", "data_base", "valor"]]


def _preparar_ativo(
    tabelas: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _preparar_banco(tabelas, "Ativo Total", _ativo_total_da_dfp)


def _preparar_patrimonio(
    tabelas: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _preparar_banco(tabelas, "Patrimônio Líquido", _patrimonio_da_dfp)


# O IF.data fecha o perímetro do conglomerado do Banco Central e a DFP o da CVM; 2% absorve a diferença de
# perímetro e o arredondamento sem esconder um erro de escala (mil vezes) ou de conta.
TOLERANCIA_DOS_BANCOS = Tolerancia(relativa=0.02)
# a meta vem em % ao ano com duas casas; meio ponto-base de folga só para o ponto flutuante
TOLERANCIA_DA_SELIC = Tolerancia(absoluta=0.005)

_PERIMETRO_DOS_BANCOS = (
    "perímetros diferentes: o IF.data mede o balanço do conglomerado (perímetro do Banco Central) e a DFP "
    "é o consolidado da CVM; em 10/11/2026 a diferença mediana era de ~7%, de 2010 a 2025, nunca dentro "
    "dos 2%. Não prova nem reprova a tabela"
)

PARES: tuple[Par, ...] = (
    Par(
        nome="selic_meta_sgs_x_copom",
        descricao="Meta da Selic no SGS 432 no dia seguinte a cada reunião × meta no comunicado do Copom",
        chave=("data",),
        tolerancia=TOLERANCIA_DA_SELIC,
        independencia=MESMA_FONTE_OUTRO_DOCUMENTO,
        preparar=_preparar_selic,
        tabelas=("bcb_selic_focus",),
    ),
    Par(
        nome="banco_ativo_total_ifdata_x_dfp",
        descricao="Ativo total do banco: IF.data (Banco Central) × DFP consolidada (CVM)",
        chave=("cnpj", "data_base"),
        tolerancia=TOLERANCIA_DOS_BANCOS,
        independencia=OUTRO_ORGAO,
        informativo=_PERIMETRO_DOS_BANCOS,
        preparar=_preparar_ativo,
        tabelas=("ifdata_valores", "demonstracoes_como_era"),
    ),
    Par(
        nome="banco_patrimonio_liquido_ifdata_x_dfp",
        descricao="Patrimônio líquido do banco: IF.data (Banco Central) × DFP consolidada (CVM)",
        chave=("cnpj", "data_base"),
        tolerancia=TOLERANCIA_DOS_BANCOS,
        independencia=OUTRO_ORGAO,
        informativo=_PERIMETRO_DOS_BANCOS,
        preparar=_preparar_patrimonio,
        tabelas=("ifdata_valores", "demonstracoes_como_era"),
    ),
)
