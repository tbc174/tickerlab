"""Números no estilo brasileiro (vírgula decimal; traço quando não há número).

A tela do Streamlit (`telas/comum.py`) e o app em React (`web/src/app/formatar.ts`) mostram os números
com estas regras. O React tem a própria cópia em TypeScript, conferida contra `casos_de_formatacao()`
(exportados para `web/conteudo/formatacao.json`), inclusive nos empates de arredondamento: o Python
arredonda o empate exato para o par (12,125 → 12,12) e o `toFixed` do JavaScript, para cima.
"""

import math

SEM_NUMERO = "—"
CASAS = 2


def _sem_numero(valor: float | None) -> bool:
    return valor is None or math.isnan(valor) or math.isinf(valor)


def formatar_pct(valor: float | None, com_sinal: bool = False) -> str:
    """Fração em porcentagem: 0.1234 → "12,34%" (ou "+12,34%"); vazio vira um traço."""
    if valor is None or _sem_numero(valor):
        return SEM_NUMERO
    texto = f"{valor:+.{CASAS}%}" if com_sinal else f"{valor:.{CASAS}%}"
    return texto.replace(".", ",")


def formatar_decimal(valor: float | None) -> str:
    """Número com duas casas: 1.2345 → "1,23" (o Sharpe); vazio vira um traço."""
    if valor is None or _sem_numero(valor):
        return SEM_NUMERO
    return f"{valor:.{CASAS}f}".replace(".", ",")


# valores que pegam os casos difíceis: empates exatos (0.12125 * 100 = 12.125), negativos, zero,
# milhares (sem separador, como na tela), muito pequenos e vazios
_VALORES_DE_TESTE = (
    0.1234, -0.0567, 0.0, -0.0, 0.12125, 0.12375, -0.12125, 0.00125, 0.10625, 0.02375,
    12.5, 1.125, 2.675, -1.125, 0.125, 1e-9, -1e-9, 123.456789, None,
)  # fmt: skip
FORMATOS = ("pct", "pct_com_sinal", "decimal", "inteiro")

# o formato de cada métrica do backtest (o resto sai com duas casas: Sharpe, Sortino, Calmar...)
METRICAS_EM_PORCENTAGEM_COM_SINAL = {
    "Retorno total",
    "Retorno anualizado",
    "Expectativa por operação",
}
METRICAS_EM_PORCENTAGEM = {
    "Chance de não ser sorte",
    "Volatilidade anual",
    "Maior queda",
    "Exposição média",
    "Taxa de acerto",
}
METRICAS_INTEIRAS = {"Dias debaixo d'água (máx.)", "Operações"}


def formato_da_metrica(nome: str) -> str:
    """ "pct_com_sinal", "pct", "inteiro" ou "decimal", conforme a métrica."""
    if nome in METRICAS_EM_PORCENTAGEM_COM_SINAL:
        return "pct_com_sinal"
    if nome in METRICAS_EM_PORCENTAGEM:
        return "pct"
    if nome in METRICAS_INTEIRAS:
        return "inteiro"
    return "decimal"


def formatar(valor: float | None, formato: str) -> str:
    """O número num formato: "pct", "pct_com_sinal", "decimal" ou "inteiro" (parte inteira)."""
    if formato == "decimal":
        return formatar_decimal(valor)
    if formato == "inteiro":
        return SEM_NUMERO if valor is None or _sem_numero(valor) else f"{int(valor)}"
    return formatar_pct(valor, com_sinal=formato == "pct_com_sinal")


def casos_de_formatacao() -> list[dict[str, float | str | None]]:
    """Cada valor de teste em cada formato, com o texto que o Python mostra (para o teste do React)."""
    return [
        {"valor": valor, "formato": formato, "texto": formatar(valor, formato)}
        for valor in _VALORES_DE_TESTE
        for formato in FORMATOS
    ]
