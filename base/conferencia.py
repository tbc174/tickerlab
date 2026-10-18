"""Conferência de cada Parquet da base contra o contrato (ADR 0077 e 0078; ADR 0055).

O contrato (`base/contrato.py`) **descreve** a tabela; aqui os **valores** são conferidos contra ele,
com as regras tiradas do dicionário (`base/dicionario.py`), sem escrever nada duas vezes:

- **colunas:** as do dicionário, nem uma a menos, nem uma a mais;
- **tipo:** sai da unidade de cada coluna (`REGRA_POR_UNIDADE`: "data (dia)" é data, "ações" é
  inteiro...); um inteiro guardado como decimal porque há vazio passa, um 2024,5 não;
- **vazios:** as chaves e as `nao_nulas` da tabela não aceitam vazio;
- **faixas:** as da unidade ("0 a 100", "mês (1 a 12)", ações ≥ 0) e as `faixas` da tabela;
- **chave sem duplicata;**
- **datas:** nenhuma antes de 1900, `publico_em` e `coletado_em` nunca depois de hoje e as três datas
  em ordem (aconteceu ≤ público ≤ coletado, comparadas pelo dia; o fato anunciado antes de acontecer,
  `anuncia_o_futuro` no dicionário, pode ter `aconteceu_em` depois de `publico_em`).

Medimos o pandera antes (`projeto-acoes/relatorio-pandera-comparacao.md`, 16/10/2026): mesmo tempo, três
dependências a mais e as regras são simples; ficou o pandas puro. O resultado vai para o manifesto
(`conferencia_do_contrato`), escrito por `base/parquet.py::gravar_tabela` quando o destino fica numa
pasta que o dicionário conhece. Por enquanto é **aviso**: a montagem não para (ADR 0078; bloquear
pede o "pode" do Tiago).
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from itertools import pairwise
from pathlib import PurePath

import pandas as pd
from pandas.api import types

from base.dicionario import TABELAS, Tabela

MAXIMO_DE_PROBLEMAS = (
    20  # no manifesto: o bastante para achar o defeito, sem inchar o arquivo
)
DATA_MINIMA = pd.Timestamp("1900-01-01")
ORDEM_DAS_DATAS = ("aconteceu_em", "publico_em", "coletado_em")
SEM_FUTURO = ("publico_em", "coletado_em")


@dataclass(frozen=True)
class Regra:
    tipo: str  # texto, data, inteiro, decimal ou logico
    faixa: tuple[float | None, float | None] | None = None


_TEXTO = Regra("texto")
_DATA = Regra("data")
_INTEIRO = Regra("inteiro")
_DECIMAL = Regra("decimal")

# toda unidade do dicionário precisa estar aqui (há teste): unidade nova pede uma decisão
REGRA_POR_UNIDADE: dict[str, Regra] = {
    "texto": _TEXTO,
    "UUID": _TEXTO,
    "AAAA-MM": _TEXTO,
    "data (dia)": _DATA,
    "data e hora (UTC)": _DATA,
    "número inteiro": _INTEIRO,
    "ações": Regra("inteiro", (0, None)),
    "ano": Regra("inteiro", (1900, 2100)),
    "mês (1 a 12)": Regra("inteiro", (1, 12)),
    "0 a 100": Regra("decimal", (0, 100)),
    "verdadeiro ou falso": Regra("logico"),
    "número com decimais, na unidade da fonte": _DECIMAL,
    "reais (R$), já multiplicado pela escala informada": _DECIMAL,
    "reais (R$)": _DECIMAL,
    "reais (R$) por ação": _DECIMAL,
    "reais ou dias": _DECIMAL,
    "número": _DECIMAL,
    "fração (0,25 = 25%)": _DECIMAL,
    "pontos percentuais (66,25 = 66,25%)": _DECIMAL,
    "percentual, como a CVM informa": _DECIMAL,
    "percentual ao ano, como a CVM informa": _DECIMAL,
    "a do indicador (fração, vezes ou dias)": _DECIMAL,
    "vezes": _DECIMAL,
    "anos (base 252)": _DECIMAL,
    "anos": _DECIMAL,
    # clima por região cafeeira: a anomalia pode ser negativa; "dias" é média de estações
    "mm": _DECIMAL,
    "°C": _DECIMAL,
    "dias": Regra("decimal", (0, None)),
    # área e produção de café por município (PAM e MapBiomas)
    "hectares": Regra("decimal", (0, None)),
    "toneladas": Regra("decimal", (0, None)),
}


@dataclass(frozen=True)
class Conferencia:
    tabela: str
    versao_do_contrato: str
    regras: int  # quantas regras foram conferidas
    problemas: list[str] = field(default_factory=list)

    @property
    def aprovada(self) -> bool:
        return not self.problemas

    def para_manifesto(self) -> dict[str, object]:
        return {
            "tabela": self.tabela,
            "versao_do_contrato": self.versao_do_contrato,
            "aprovada": self.aprovada,
            "regras": self.regras,
            "problemas": self.problemas[:MAXIMO_DE_PROBLEMAS],
            **(
                {"problemas_a_mais": len(self.problemas) - MAXIMO_DE_PROBLEMAS}
                if len(self.problemas) > MAXIMO_DE_PROBLEMAS
                else {}
            ),
        }


def tabela_do_destino(destino: PurePath) -> str | None:
    """A tabela do dicionário que mora na pasta de `destino` (`.../base/<pasta>/<arquivo>`), ou None.

    Vale a pasta mais longa que casar (`fidc/informe` antes de `fidc`)."""
    partes = destino.parts
    if "base" not in partes:
        return None
    inicio = len(partes) - 1 - partes[::-1].index("base")
    pasta = "/".join(partes[inicio + 1 : -1])
    candidatas = [
        (len(t.pasta), nome)
        for nome, t in TABELAS.items()
        if t.pasta and (pasta == t.pasta or pasta.startswith(t.pasta + "/"))
    ]
    return max(candidatas)[1] if candidatas else None


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _faixa_em_texto(faixa: tuple[float | None, float | None]) -> str:
    def numero(valor: float | None, infinito: str) -> str:
        if valor is None:
            return infinito
        return str(int(valor)) if float(valor).is_integer() else str(valor)

    return f"{numero(faixa[0], '-∞')} a {numero(faixa[1], '∞')}"


def _como_data(coluna: pd.Series) -> pd.Series:
    """A coluna em dias (sem fuso), aceitando data, data e hora ou texto ISO; o que não é data vira NaT."""
    if types.is_datetime64_any_dtype(coluna):
        datas = coluna
    else:
        datas = pd.to_datetime(coluna, errors="coerce", utc=True, format="ISO8601")
    if getattr(datas.dt, "tz", None) is not None:
        datas = datas.dt.tz_convert(None)
    return datas.dt.normalize()


def _tipo_errado(coluna: pd.Series, tipo: str) -> str | None:
    """O tipo achado, se não serve para `tipo`; None se serve."""
    if tipo == "data":
        return None  # conferido valor a valor em `_problemas_de_data`
    valores = coluna.dropna()
    if valores.empty:
        return None
    achado = types.infer_dtype(valores, skipna=True)
    serve = {
        "texto": achado in ("string",),
        "logico": achado in ("boolean",),
        "decimal": achado in ("integer", "floating", "decimal", "mixed-integer-float"),
        "inteiro": achado == "integer"
        or (
            achado in ("floating", "mixed-integer-float")
            and bool((valores.astype(float) % 1 == 0).all())
        ),
    }[tipo]
    return None if serve else achado


def _problemas_de_data(nome: str, coluna: pd.Series, datas: pd.Series) -> list[str]:
    problemas = []
    nao_data = int((datas.isna() & coluna.notna()).sum())
    if nao_data:
        problemas.append(
            f"{nome}: {_plural(nao_data, 'valor que não é data', 'valores que não são data')}"
        )
    antigas = int((datas < DATA_MINIMA).sum())
    if antigas:
        problemas.append(f"{nome}: {_plural(antigas, 'data', 'datas')} antes de 1900")
    return problemas


def _datas_fora_de_ordem(tabela: Tabela, datas: dict[str, pd.Series]) -> list[str]:
    presentes = [
        (apelido, tabela.datas[apelido])
        for apelido in ORDEM_DAS_DATAS
        if tabela.datas.get(apelido) in datas
    ]
    problemas = []
    for (antes, coluna_antes), (depois, coluna_depois) in pairwise(presentes):
        if coluna_antes == coluna_depois or (
            antes == "aconteceu_em" and tabela.anuncia_o_futuro
        ):
            continue
        fora = int((datas[coluna_antes] > datas[coluna_depois]).sum())
        if fora:
            problemas.append(
                f"datas: {_plural(fora, 'linha', 'linhas')} com {antes} ({coluna_antes}) depois de "
                f"{depois} ({coluna_depois})"
            )
    return problemas


def _no_futuro(tabela: Tabela, datas: dict[str, pd.Series], hoje: date) -> list[str]:
    limite = pd.Timestamp(hoje)
    problemas = []
    for apelido in SEM_FUTURO:
        coluna = tabela.datas.get(apelido)
        if coluna in datas:
            futuras = int((datas[coluna] > limite).sum())
            if futuras:
                problemas.append(
                    f"{coluna}: {_plural(futuras, 'data', 'datas')} depois de hoje"
                )
    return problemas


def _vazios(tabela_df: pd.DataFrame, colunas: Iterable[str]) -> list[str]:
    problemas = []
    for coluna in dict.fromkeys(colunas):
        if coluna in tabela_df:
            vazios = int(tabela_df[coluna].isna().sum())
            if vazios:
                problemas.append(
                    f"{coluna}: {_plural(vazios, 'vazio', 'vazios')} (a coluna não aceita vazio)"
                )
    return problemas


def _fora_da_faixa(coluna: pd.Series, faixa: tuple[float | None, float | None]) -> int:
    numeros = pd.to_numeric(coluna, errors="coerce")
    minimo, maximo = faixa
    fora = pd.Series(False, index=coluna.index)
    if minimo is not None:
        fora |= numeros < minimo
    if maximo is not None:
        fora |= numeros > maximo
    return int(fora.sum())


def conferir(
    tabela_df: pd.DataFrame, nome: str, *, hoje: date | None = None
) -> Conferencia:
    """Confere os valores de `tabela_df` contra o contrato da tabela `nome` do dicionário."""
    tabela = TABELAS[nome]
    hoje = hoje or datetime.now(UTC).date()
    problemas: list[str] = []
    regras = 2  # colunas que faltam e colunas a mais

    faltam = [c for c in tabela.colunas if c not in tabela_df]
    sobram = [c for c in tabela_df.columns if c not in tabela.colunas]
    if faltam:
        problemas.append(f"colunas que faltam: {', '.join(faltam)}")
    if sobram:
        problemas.append(f"colunas fora do contrato: {', '.join(map(str, sobram))}")

    datas: dict[str, pd.Series] = {}
    for coluna, (_, unidade) in tabela.colunas.items():
        if coluna not in tabela_df:
            continue
        regra = REGRA_POR_UNIDADE[unidade]
        valores = tabela_df[coluna]
        regras += 1
        if regra.tipo == "data":
            datas[coluna] = _como_data(valores)
            problemas += _problemas_de_data(coluna, valores, datas[coluna])
        elif achado := _tipo_errado(valores, regra.tipo):
            problemas.append(f"{coluna}: tipo {achado}, o contrato pede {regra.tipo}")
            continue  # sem tipo certo, a faixa não faz sentido
        faixa = tabela.faixas.get(coluna, regra.faixa)
        if faixa is not None:
            regras += 1
            fora = _fora_da_faixa(valores, faixa)
            if fora:
                problemas.append(
                    f"{coluna}: {_plural(fora, 'valor', 'valores')} fora de {_faixa_em_texto(faixa)}"
                )

    regras += 1
    problemas += _vazios(tabela_df, [*tabela.chaves, *tabela.nao_nulas])

    chaves = [c for c in tabela.chaves if c in tabela_df]
    if chaves:
        regras += 1
        duplicadas = int(tabela_df.duplicated(chaves).sum())
        if duplicadas:
            problemas.append(
                f"chave duplicada: {_plural(duplicadas, 'linha', 'linhas')} ({', '.join(chaves)})"
            )

    regras += 2
    problemas += _no_futuro(tabela, datas, hoje)
    problemas += _datas_fora_de_ordem(tabela, datas)
    return Conferencia(nome, tabela.versao_do_contrato, regras, problemas)
