"""Guardar e reabrir simulações: captura as escolhas da tela e as devolve com segurança.

Uma simulação salva é um "retrato" dos campos que o usuário preencheu (o `session_state` do
Streamlit) mais um resumo dos números. Reabrir é colocar o retrato de volta nos campos; o app
recalcula tudo com os dados de hoje. O retrato vem do banco, então é tratado como não confiável:
só entram chaves conhecidas e valores simples, e o ticker, o período e a taxa passam pela mesma
validação do link compartilhável.
"""

import math
from collections.abc import Callable, Mapping
from urllib.parse import urlencode

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


# --- as simulações salvas pelo app novo (ADR 0062, tela 3) -----------------------------------
# O app novo não tem session_state: o retrato dele guarda os campos do contrato do backtest
# (src/paginas.py) com esta marca de origem. O app atual reabre só o ticker e o período desse
# retrato (as outras chaves não têm o prefixo de nenhuma aba e ficam de fora no restaurar).
ORIGEM_DO_APP_NOVO = "app-novo"
CAMPOS_DO_BACKTEST_NO_APP_NOVO = (
    "ticker",
    "periodo",
    "estrategia",
    "custo_por_operacao",
    "taxa",
    "capital_inicial",
    "tolerancia_de_queda",
)
PREFIXO_DO_PARAMETRO = (
    "p."  # como web/src/app/Formulario.tsx põe os parâmetros no endereço
)
MAX_LIVRES = 2
MAX_PARAMETROS = 10


def retrato_do_app_novo(
    ticker: str,
    periodo: str,
    estrategia: str,
    parametros: Mapping[str, int | float | str],
    custo_por_operacao: float,
    capital_inicial: float,
    tolerancia_de_queda: float,
    livres: tuple[str, ...],
    taxa: float | None,
) -> dict:
    """O que o app novo guarda como `parametros` de um backtest: as escolhas da tela, nos nomes
    do contrato (frações, como a API). Sem `taxa`, a tela usou o CDI e a reabertura também usa."""
    retrato = {
        "origem": ORIGEM_DO_APP_NOVO,
        "ticker": ticker,
        "periodo": periodo,
        "estrategia": estrategia,
        "parametros": dict(parametros),
        "custo_por_operacao": float(custo_por_operacao),
        "capital_inicial": float(capital_inicial),
        "tolerancia_de_queda": float(tolerancia_de_queda),
        "livres": list(livres),
    }
    if taxa is not None:
        retrato["taxa"] = float(taxa)
    return retrato


def endereco_no_app_novo(tipo: str, retrato: object) -> str | None:
    """A tela do app novo que reabre a simulação com as mesmas escolhas ("/backtest?...").

    None quando ela só reabre no app atual: outro tipo de simulação ou retrato do Streamlit.
    O retrato vem do banco (não confiável): só os campos conhecidos, com valores simples.
    """
    if (
        tipo != "backtest"
        or not isinstance(retrato, Mapping)
        or retrato.get("origem") != ORIGEM_DO_APP_NOVO
    ):
        return None
    pares: list[tuple[str, str]] = []
    for campo in CAMPOS_DO_BACKTEST_NO_APP_NOVO:
        valor = retrato.get(campo)
        if valor is not None and _valor_simples(valor) and not isinstance(valor, bool):
            pares.append((campo, str(valor)))
    livres = retrato.get("livres")
    if isinstance(livres, list):
        pares += [
            ("livres", nome) for nome in livres[:MAX_LIVRES] if isinstance(nome, str)
        ]
    parametros = retrato.get("parametros")
    if isinstance(parametros, Mapping):
        pares += [
            (f"{PREFIXO_DO_PARAMETRO}{nome}", str(valor))
            for nome, valor in list(parametros.items())[:MAX_PARAMETROS]
            if isinstance(nome, str) and _valor_simples(valor)
        ]
    return f"/backtest?{urlencode(pares)}"
