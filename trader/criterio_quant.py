"""O pré-registro vigente das estratégias quant P0 e da carteira própria, e a trava do hash.

O texto aprovado pelo Tiago (03/11/2026 01h18, "Pode, como está") fica em
`docs/pre-registro-quant-p0-v0.1.md`. Mudar qualquer coisa nele gera uma versão nova, com data,
motivo e +25 tentativas no registro (seção 10 do próprio texto); o hash abaixo só muda junto com
essa versão nova. Os números do critério ficam repetidos aqui para o código não ler o texto; há
teste de que cada um aparece no texto.

A avaliação contra o critério (`Evidencia` e `avaliar`) também fica aqui: todos os Sharpes são
do **excesso sobre o CDI** (seção 3: o caixa rende o CDI), anualizados com 252; a queda máxima (F1)
é da série líquida. Convenções fixadas antes de qualquer número:
- A1: Sharpe do excesso > 0 e DSR com N = tentativas anteriores (`tentativas_anteriores`) + as do
  registro quant; a dispersão vem dos esquemas da ficha;
- A2: só onde há alternativas (PBO); a ficha diz "não se aplica" → passa com valor vazio;
- A3: cada vizinho (±20% na janela e na banda) mantém >= 70% do Sharpe do candidato;
- A4: o Sharpe líquido fica com >= 2/3 do bruto (sem custo, imposto nem impacto);
- A5: t com a correção de Lo (`avaliacao.t_estatistica_corrigida`);
- A7: contra cada régua, limite inferior de 90% do bootstrap em blocos de 21 dias da diferença de
  Sharpes dos excessos; régua sem risco (CDI) usa o bootstrap do próprio excesso;
- A8: no estresse (custos × 2, Y = 2), Sharpe do excesso > 0 e DSR >= 0,90;
- V: olhar o futuro infla (estritamente), reexecução idêntica, dados conforme e cortar o futuro
  não muda o passado. MinTRL acima da amostra → inconclusivo, como na P2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src import acaso
from trader import avaliacao
from trader.criterio import Item, Veredito
from trader.holdout import FIM_DO_DESENVOLVIMENTO, hash_do_texto
from trader.registro import RAIZ, Registro
from trader.validacao import bootstrap_diferenca_de_sharpe, bootstrap_do_sharpe

__all__ = ["FIM_DO_DESENVOLVIMENTO"]

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
# Tentativas anteriores a esta versão, contadas no DSR (seção 5, A1): M2, scalp e a Pesquisa 2.
TENTATIVAS_DA_M2 = 101  # trader/p2/preregistro.py
TENTATIVAS_DO_SCALP = 2  # docs/resultado-scalp-win-fase1b.md
REGISTRO_DA_P2 = RAIZ / "pesquisa_p2" / "registro.db"
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


def tentativas_anteriores(registro_da_p2: Path = REGISTRO_DA_P2) -> int:
    """M2 + scalp + as tentativas da Pesquisa 2 (se o registro dela está neste PC)."""
    total = TENTATIVAS_DA_M2 + TENTATIVAS_DO_SCALP
    if registro_da_p2.exists():
        registro = Registro(registro_da_p2, familias=("K", "B"), commit_fn=lambda: "")
        total += registro.total_para_o_dsr()
    return total


@dataclass
class Evidencia:
    """Tudo o que o critério precisa, medido no desenvolvimento (retornos diários líquidos)."""

    candidato: pd.Series
    cdi: pd.Series
    candidatos: pd.DataFrame  # os esquemas da ficha (custos base), para o DSR
    candidatos_estresse: pd.DataFrame  # os mesmos no estresse
    sharpe_bruto: float  # Sharpe do excesso sem custo, imposto nem impacto
    sharpes_vizinhos: dict[str, float]  # A3: Sharpe do excesso de cada vizinho
    reguas: dict[str, pd.Series]  # retornos líquidos das réguas da ficha
    p_valor_do_acaso: float
    sharpe_olhando_o_futuro: float
    reexecucao_identica: bool
    cortar_o_futuro_nao_muda: bool
    tentativas_totais: int
    nome_do_candidato: str = "risk_parity"
    pbo: float | None = None  # A2: vazio = não se aplica
    dados_conforme: bool = True
    extras: dict = field(default_factory=dict)


def _excesso(retorno: pd.Series, cdi: pd.Series) -> pd.Series:
    return (retorno - cdi.reindex(retorno.index)).dropna()


def _dsr(
    excesso: pd.Series, candidatos: pd.DataFrame, cdi: pd.Series, tentativas_totais: int
) -> float:
    excessos = candidatos.sub(cdi.reindex(candidatos.index), axis=0)
    extras = max(0, tentativas_totais - candidatos.shape[1])
    resultado = acaso.calcular_sharpe_deflacionado(
        excesso, excessos, tentativas_extras=extras
    )
    return resultado.probabilidade


def _contra_a_regua(excesso: pd.Series, regua: pd.Series, cdi: pd.Series) -> float:
    excesso_da_regua = _excesso(regua, cdi)
    if excesso_da_regua.std() == 0:
        return bootstrap_do_sharpe(excesso, bloco=BLOCO_DO_BOOTSTRAP_EM_DIAS)[
            "ic90_inferior"
        ]
    diferenca = bootstrap_diferenca_de_sharpe(
        excesso, excesso_da_regua, bloco=BLOCO_DO_BOOTSTRAP_EM_DIAS
    )
    return diferenca["ic90_inferior"]


def avaliar(e: Evidencia) -> Veredito:
    """Os itens A1 a A8, F1 e V da seção 5; todos precisam passar."""
    excesso = _excesso(e.candidato, e.cdi)
    sharpe = avaliacao.sharpe(excesso)
    itens: list[Item] = []

    dsr = _dsr(excesso, e.candidatos, e.cdi, e.tentativas_totais)
    itens.append(
        Item(
            "A1",
            f"Sharpe do excesso ({sharpe:.2f}) > 0 e DSR com {e.tentativas_totais} tentativas",
            dsr,
            f">= {DSR_MINIMO}",
            sharpe > 0 and dsr >= DSR_MINIMO,
        )
    )

    if e.pbo is None:
        itens.append(
            Item(
                "A2", "PBO (a ficha não tem alternativas)", None, "não se aplica", True
            )
        )
    else:
        itens.append(Item("A2", "PBO", e.pbo, f"<= {PBO_MAXIMO}", e.pbo <= PBO_MAXIMO))

    if sharpe > 0 and e.sharpes_vizinhos:
        fracao_do_plato = min(v / sharpe for v in e.sharpes_vizinhos.values())
    else:
        fracao_do_plato = 0.0
    itens.append(
        Item(
            "A3",
            "platô: menor Sharpe dos vizinhos ÷ Sharpe do candidato",
            fracao_do_plato,
            f">= {FRACAO_MINIMA_DO_PLATO}",
            fracao_do_plato >= FRACAO_MINIMA_DO_PLATO,
        )
    )

    comido = (
        (e.sharpe_bruto - sharpe) / e.sharpe_bruto
        if e.sharpe_bruto > 0
        else float("inf")
    )
    itens.append(
        Item(
            "A4",
            f"custo, imposto e impacto como fração do Sharpe bruto ({e.sharpe_bruto:.2f})",
            comido,
            f"<= {FRACAO_MAXIMA_DO_CUSTO:.3f}",
            comido <= FRACAO_MAXIMA_DO_CUSTO,
        )
    )

    t = avaliacao.t_estatistica_corrigida(excesso)
    itens.append(
        Item(
            "A5",
            "t-estatística do excesso com a correção de Lo",
            t,
            f">= {T_MINIMO}",
            t >= T_MINIMO,
        )
    )

    itens.append(
        Item(
            "A6",
            "contra o acaso: p-valor dos sinais deslocados",
            e.p_valor_do_acaso,
            f"<= {P_VALOR_MAXIMO_DO_ACASO}",
            e.p_valor_do_acaso <= P_VALOR_MAXIMO_DO_ACASO,
        )
    )

    limites = {
        nome: _contra_a_regua(excesso, regua, e.cdi) for nome, regua in e.reguas.items()
    }
    detalhe = ", ".join(f"{n} {v:.2f}" for n, v in limites.items())
    itens.append(
        Item(
            "A7",
            f"contra as réguas: limite inferior de 90% da diferença ({detalhe})",
            min(limites.values()) if limites else float("nan"),
            "> 0 em todas",
            bool(limites) and all(v > 0 for v in limites.values()),
        )
    )

    excesso_no_estresse = _excesso(e.candidatos_estresse[e.nome_do_candidato], e.cdi)
    sharpe_no_estresse = avaliacao.sharpe(excesso_no_estresse)
    dsr_no_estresse = _dsr(
        excesso_no_estresse, e.candidatos_estresse, e.cdi, e.tentativas_totais
    )
    itens.append(
        Item(
            "A8",
            f"estresse: Sharpe do excesso ({sharpe_no_estresse:.2f}) > 0 e DSR",
            dsr_no_estresse,
            f">= {DSR_MINIMO_NO_ESTRESSE}",
            sharpe_no_estresse > 0 and dsr_no_estresse >= DSR_MINIMO_NO_ESTRESSE,
        )
    )

    queda = avaliacao.maior_queda(e.candidato)
    itens.append(
        Item(
            "F1",
            "maior queda do pico (líquida, diária)",
            queda,
            f">= -{QUEDA_MAXIMA}",
            queda >= -QUEDA_MAXIMA,
        )
    )

    infla = e.sharpe_olhando_o_futuro > sharpe
    v_ok = (
        infla
        and e.reexecucao_identica
        and e.dados_conforme
        and e.cortar_o_futuro_nao_muda
    )
    itens.append(
        Item(
            "V",
            "verificações: futuro infla, reexecução idêntica, dados conforme, cortar o futuro",
            e.sharpe_olhando_o_futuro,
            f"futuro > {sharpe:.2f}; as outras três verdadeiras",
            v_ok,
        )
    )

    minimo = acaso.calcular_comprimento_minimo(excesso, CONFIANCA_DO_MINTRL)
    curto = not np.isfinite(minimo) or len(excesso) < minimo
    return Veredito(
        itens=itens,
        inconclusivo=curto and all(i.passou for i in itens),
        motivo_inconclusivo="amostra menor que o MinTRL" if curto else "",
    )
