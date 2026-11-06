"""Exportação em CSV: tabelas prontas para abrir no Excel (separador ";" e vírgula decimal).

As datas saem como AAAA-MM-DD, que não deixa dúvida entre dia e mês. O arquivo leva a marca
UTF-8 (BOM), para o Excel mostrar os acentos certos.
"""

import pandas as pd

# O Excel lê como fórmula o texto que começa com um destes caracteres (injeção de CSV).
INICIOS_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _proteger_texto_de_formula(tabela: pd.DataFrame) -> pd.DataFrame:
    """Cópia da tabela com um apóstrofo na frente do texto que viraria fórmula no Excel.

    Só as colunas de texto: número (inclusive negativo) continua número.
    """
    protegida = tabela.copy()
    for coluna in protegida.columns:
        if not (
            pd.api.types.is_object_dtype(protegida[coluna])
            or pd.api.types.is_string_dtype(protegida[coluna])
        ):
            continue
        protegida[coluna] = protegida[coluna].map(
            lambda valor: (
                "'" + valor
                if isinstance(valor, str) and valor.startswith(INICIOS_DE_FORMULA)
                else valor
            )
        )
    return protegida


def converter_para_csv(tabela: pd.DataFrame, formato_brasileiro: bool = True) -> bytes:
    """Texto CSV da tabela (com o índice). Brasileiro: ";" entre colunas e "," nos decimais."""
    if tabela.empty:
        raise ValueError("Não há dados para exportar.")
    separador, decimal = (";", ",") if formato_brasileiro else (",", ".")
    texto = _proteger_texto_de_formula(tabela).to_csv(
        sep=separador,
        decimal=decimal,
        date_format="%Y-%m-%d",
        index_label=tabela.index.name or "Data",
    )
    return texto.encode("utf-8-sig")


def montar_tabela_de_precos(dados: pd.DataFrame) -> pd.DataFrame:
    """Os preços e o volume que o app baixou, com o retorno diário do fechamento."""
    tabela = dados.copy()
    tabela["Retorno diário"] = tabela["Close"].pct_change()
    tabela.index.name = "Data"
    return tabela


def montar_tabela_de_curvas(
    curvas: dict[str, pd.Series], capital_inicial: float
) -> pd.DataFrame:
    """Quanto o capital inicial viraria dia a dia em cada simulação."""
    if not curvas:
        raise ValueError("Não há curvas para exportar.")
    tabela = pd.DataFrame(
        {nome: curva * capital_inicial for nome, curva in curvas.items()}
    )
    tabela.index.name = "Data"
    return tabela


def montar_tabela_de_operacoes(operacoes: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por operação, com nomes de coluna em português."""
    tabela = operacoes.rename(
        columns={
            "entrada": "Primeiro dia",
            "saida": "Último dia",
            "dias": "Dias",
            "retorno": "Retorno",
            "aberta": "Em aberto",
        }
    ).reset_index(drop=True)
    tabela.index = tabela.index + 1
    tabela.index.name = "Operação"
    return tabela
