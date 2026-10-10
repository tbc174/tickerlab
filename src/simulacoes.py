"""Guardar e reabrir simulações: captura as escolhas da tela e as devolve com segurança.

Uma simulação salva é um "retrato" dos campos que o usuário preencheu (o `session_state` do
Streamlit) mais um resumo dos números. Reabrir é colocar o retrato de volta nos campos; o app
recalcula tudo com os dados de hoje. O retrato vem do banco, então é tratado como não confiável:
só entram chaves conhecidas e valores simples, e o ticker, o período e a taxa passam pela mesma
validação do link compartilhável.
"""

import math
from collections.abc import Callable, Mapping

from src.link import ler_parametros

NOMES_DOS_TIPOS = {"backtest": "Backtest", "carteira": "Carteira", "pares": "Pares"}
CAMPOS_DO_TOPO = ("ticker", "periodo", "taxa", "em_reais", "usar_exemplo")
PREFIXOS_DOS_CAMPOS = {
    "backtest": (
        "backtest_",
        "parametro_",
        "custo_",
        "liga_",
        "valor_",
        "espera_depois_do_stop",
    ),
    "carteira": ("carteira_",),
    "pares": ("pares_",),
}
# dependem dos dados do momento (opções que mudam): não voltam, para não quebrar o campo
CAMPOS_QUE_NAO_VOLTAM = {"carteira_ativos_no_grafico", "pares_escolhido"}
MAX_CAMPOS = 80
TAMANHO_MAXIMO_DO_TEXTO = 300


def _valor_simples(valor: object) -> bool:
    if isinstance(valor, int):  # inclui bool
        return True
    if isinstance(valor, float):
        return math.isfinite(valor)
    return isinstance(valor, str) and len(valor) <= TAMANHO_MAXIMO_DO_TEXTO


def _chave_do_tipo(chave: str, tipo: str) -> bool:
    return chave not in CAMPOS_QUE_NAO_VOLTAM and chave.startswith(
        PREFIXOS_DOS_CAMPOS[tipo]
    )


def capturar_estado(estado: Mapping, tipo: str) -> dict:
    """Os campos da tela (topo + os da aba do tipo) que valem a pena guardar."""
    if tipo not in PREFIXOS_DOS_CAMPOS:
        raise ValueError(f"Tipo de simulação desconhecido: {tipo}.")
    retrato = {}
    for chave, valor in estado.items():
        if not isinstance(chave, str) or not _valor_simples(valor):
            continue
        if chave in CAMPOS_DO_TOPO or _chave_do_tipo(chave, tipo):
            retrato[chave] = valor
    return retrato


def _campos_do_topo_validos(retrato: Mapping) -> dict:
    """Valida ticker, período e taxa como a URL: o que for inválido é ignorado."""
    como_url = {
        "ticker": str(retrato.get("ticker", "")),
        "periodo": str(retrato.get("periodo", "")),
        "taxa": str(retrato.get("taxa", "")),
    }
    for chave_url, chave in (("reais", "em_reais"), ("exemplo", "usar_exemplo")):
        if retrato.get(chave) is True:
            como_url[chave_url] = "1"
    lidos = ler_parametros(como_url)
    validos = {c: lidos[c] for c in ("ticker", "periodo", "taxa") if c in lidos}
    for chave in ("em_reais", "usar_exemplo"):
        if chave in retrato:
            validos[chave] = retrato[chave] is True
    return validos


def restaurar_estado(
    retrato: Mapping,
    tipo: str,
    campo_ainda_vale: Callable[[str, object], bool] | None = None,
) -> dict:
    """Os campos que podem voltar para a tela. O que não for conhecido ou válido fica de fora.

    `campo_ainda_vale(chave, valor)` deixa o app recusar valores que a tela de hoje não aceita
    mais (por exemplo, uma estratégia que deixou de existir).
    """
    if tipo not in PREFIXOS_DOS_CAMPOS:
        raise ValueError(f"Tipo de simulação desconhecido: {tipo}.")
    if not isinstance(retrato, Mapping):
        return {}
    candidatos = {
        c: v
        for c, v in list(retrato.items())[:MAX_CAMPOS]
        if isinstance(c, str) and _chave_do_tipo(c, tipo) and _valor_simples(v)
    }
    if campo_ainda_vale is not None:
        candidatos = {c: v for c, v in candidatos.items() if campo_ainda_vale(c, v)}
    return {**_campos_do_topo_validos(retrato), **candidatos}
