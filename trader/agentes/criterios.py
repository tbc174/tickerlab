"""Os critérios dos agentes analistas (camada A3) e a trava do hash.

O texto fica em `docs/criterios-agentes-analistas-v0.1.md`. Ele é do Tiago (nível 1): enquanto
`HASH_APROVADO` for `None`, o texto é um rascunho e nenhuma rodada é preparada ou registrada. Com o
"pode" dele, o hash do texto entra aqui num PR próprio; mudar o texto depois disso é a versão 0.2.
Os números ficam repetidos aqui para o código não ler o texto; há teste de que cada um aparece nele.
"""

from __future__ import annotations

from pathlib import Path

from trader import criterio_quant
from trader.holdout import hash_do_texto

VERSAO = "0.1"
ARQUIVO = (
    Path(__file__).resolve().parents[2] / "docs" / "criterios-agentes-analistas-v0.1.md"
)
# SHA-256 do texto aprovado (quebras de linha normalizadas). None seria rascunho, sem o "pode".
# "Pode" do Tiago em 03/11/2026 22h03 ("Aprovar como está"), na conversa da carteira própria.
HASH_APROVADO: str | None = (
    "ed1fe75c8812df8921cfb343b0aa09cef3b29708454f8b635e2ac6f3ad6628dc"
)

# --- seção 2: universo ----------------------------------------------------------------------------
PISO_DE_LIQUIDEZ = criterio_quant.PISO_DE_LIQUIDEZ_EM_REAIS  # o mesmo dos fatores na B3
PREGOES_MINIMOS = (
    criterio_quant.PREGOES_DA_LIQUIDEZ
)  # a média da liquidez precisa deles
MAXIMO_DE_CANDIDATAS = 30  # ADR 0118: até 30 empresas por rodada

# --- seção 3: a rodada ----------------------------------------------------------------------------
PREGOES_DA_JANELA = 5  # do 1º ao 5º pregão do mês

# --- seção 4: a nota -------------------------------------------------------------------------------
PESOS = {"C1": 20, "C2": 15, "C3": 15, "C4": 15, "C5": 20, "C6": 15}
VETOS = ("V1", "V2", "V3", "V4", "V5")
NOTA_MINIMA = 0
NOTA_MAXIMA = 10
NOTA_MAXIMA_SEM_FONTE = 5

# --- seção 5: a regra ------------------------------------------------------------------------------
NOTA_DE_CORTE = 7.0
MAXIMO_NA_CARTEIRA = 5
PESO_POR_EMPRESA = 1 / MAXIMO_NA_CARTEIRA
FREIO = criterio_quant.FREIO_POR_CAMADA

# --- seção 7: comparação ---------------------------------------------------------------------------
MESES_DA_COMPARACAO = 12


class CriteriosNaoAprovadosError(RuntimeError):
    """O texto ainda é rascunho, ou mudou depois de aprovado."""


def texto() -> str:
    return ARQUIVO.read_text(encoding="utf-8")


def hash_atual() -> str:
    return hash_do_texto(ARQUIVO)


def conferir() -> str:
    """Devolve o hash aprovado se o texto for o aprovado; senão, recusa."""
    if HASH_APROVADO is None:
        raise CriteriosNaoAprovadosError(
            f"Os critérios {VERSAO} ainda são rascunho: falta o 'pode' do Tiago "
            "e o hash dele em trader/agentes/criterios.py."
        )
    if hash_atual() != HASH_APROVADO:
        raise CriteriosNaoAprovadosError(
            f"O texto dos critérios mudou depois de aprovado ({ARQUIVO.name}): "
            "mudança é versão nova, com data e motivo."
        )
    return HASH_APROVADO
