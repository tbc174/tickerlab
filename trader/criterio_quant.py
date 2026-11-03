"""O pré-registro vigente das estratégias quant P0 e da carteira própria, e a trava do hash.

O texto aprovado pelo Tiago (03/11/2026 01h18, "Pode, como está") fica em
`docs/pre-registro-quant-p0-v0.1.md`. Mudar qualquer coisa nele gera uma versão nova, com data,
motivo e +25 tentativas no registro (seção 10 do próprio texto); o hash abaixo só muda junto com
essa versão nova. Os números do critério ficam repetidos aqui para o código não ler o texto; há
teste de que cada um aparece no texto.

Este módulo não calcula nada: a avaliação de cada estratégia contra o critério chega com a
primeira estratégia (P0-3), lendo os limites daqui.
"""

from __future__ import annotations

from pathlib import Path

from trader.holdout import hash_do_texto

VERSAO = "0.1"
ARQUIVO = Path(__file__).resolve().parents[1] / "docs" / "pre-registro-quant-p0-v0.1.md"
# SHA-256 do texto aprovado em 03/11/2026 (quebras de linha normalizadas para \n).
HASH_DO_CRITERIO = "ea45eddf09e89f1cee5af3e7612fac2739cebf05ab1583e5270c6b3c2f403269"

# --- seção 5: critério único (medido no desenvolvimento, retornos diários líquidos) ---------------
DSR_MINIMO = 0.95  # A1
PBO_MAXIMO = 0.30  # A2
VARIACAO_DO_PLATO = 0.20  # A3: ±20% em cada parâmetro...
FRACAO_MINIMA_DO_PLATO = 0.70  # ...mantém ≥ 70% do Sharpe
FRACAO_MAXIMA_DO_CUSTO = 1 / 3  # A4: custo + imposto ≤ ⅓ do Sharpe bruto
T_MINIMO = 3.0  # A5
P_VALOR_MAXIMO_DO_ACASO = 0.05  # A6: acima do percentil 95 de 1.000 sinais deslocados
SINAIS_DESLOCADOS = 1_000  # A6
CONFIANCA_CONTRA_A_REGUA = 0.90  # A7: limite inferior de 90% do bootstrap...
BLOCO_DO_BOOTSTRAP_EM_DIAS = 21  # ...em blocos de 21 dias
DSR_MINIMO_NO_ESTRESSE = 0.90  # A8
FATOR_DE_IMPACTO_NO_ESTRESSE = 2.0  # A8: Y = 2 (Y = 1 no caso base)
QUEDA_MAXIMA = 0.35  # F1: queda máxima do pico, diária, líquida, no desenvolvimento

# --- holdout (só com decisão escrita do Tiago; uma abertura por estratégia) --------------------------
FRACAO_MINIMA_DO_SHARPE_NO_HOLDOUT = 0.50  # B1: ≥ 50% do de desenvolvimento...
SHARPE_MINIMO_NO_HOLDOUT = 0.30  # ...e ≥ 0,30
QUEDA_MAXIMA_RELATIVA_NO_HOLDOUT = 1.5  # B2
CONFIANCA_DO_MINTRL = 0.95  # C

# --- seção 6: freios da carteira própria ---------------------------------------------------------------
FREIO_GLOBAL = 0.35  # queda do pico da carteira inteira: tudo em CDI até revisão
FREIO_POR_CAMADA = 0.40  # queda do pico da própria camada: ela vai para CDI
MESES_DE_VOLTA_DO_FREIO = 12  # no backtest, a camada freada volta 12 meses depois

# --- seção 7: alavancagem do núcleo (só a camada A1, via WIN ou DI1) ---------------------------------
ALAVANCAGENS_DO_NUCLEO = (1.0, 1.3)  # as duas versões pré-registradas; nada entre elas
MARGEM_DE_AVISO = 0.30  # dias em que a margem exigida passou de 30% do patrimônio

# --- seção 8: universo dos fatores na B3 ----------------------------------------------------------------
PISO_DE_LIQUIDEZ_EM_REAIS = 5_000_000  # volume financeiro médio diário...
PREGOES_DA_LIQUIDEZ = 60  # ...nos 60 pregões anteriores ao rebalanceamento
MESES_MINIMOS_DE_PREGAO = 12

# --- seções 9 e 10: tentativas ------------------------------------------------------------------------
ORCAMENTO_POR_FICHA = {
    "F-B3": 10,
    "P0-3": 8,
    "P0-1": 10,
    "P0-2": 8,
    "P0-7": 4,
    "P0-4": 8,
    "P0-5": 6,
    "P0-6": 2,
    "P0-8": 4,
}
ORCAMENTO_DE_TENTATIVAS = 60
TENTATIVAS_POR_VERSAO_NOVA = 25
# Estudo (P0-7) e monitor (P0-6): não são candidatas a dinheiro.
FICHAS_SEM_CRITERIO = ("P0-7", "P0-6")
CANDIDATOS = {
    "P0-3": "risk parity",
    "P0-2": "BOVA11",
    "P0-1": "BTC e ETH 50/50",
}


class PreRegistroAlteradoError(RuntimeError):
    """O texto do pré-registro não é o aprovado: rodar seria mudar o critério escondido."""


def conferir(arquivo: Path = ARQUIVO, esperado: str = HASH_DO_CRITERIO) -> None:
    """Recusa seguir se o texto do pré-registro mudou desde a aprovação."""
    encontrado = hash_do_texto(arquivo)
    if encontrado != esperado:
        raise PreRegistroAlteradoError(
            f"O pré-registro em {arquivo.name} mudou (hash {encontrado[:12]}…). Uma mudança exige "
            f"versão nova aprovada pelo Tiago e +{TENTATIVAS_POR_VERSAO_NOVA} tentativas."
        )
