"""O critério de aprovação da M2 em código (pré-registro v0.1, `docs/pre-registro-m2-v0.1.md`).

Escrito ANTES de qualquer resultado de ML, para que a régua não possa ser ajustada ao que aparecer.
Cada item devolve o valor medido, o limite e se passou. Os limiares abaixo são os do texto
aprovado; há teste que confere cada um.

Convenções (o texto aprovado não detalha; fixadas aqui, antes de ver resultado):
- os números de carteira usam retornos diários líquidos, em dias úteis, anualizados com 252;
- **caminho mediano** = o caminho do CPCV com o Sharpe do meio (o 5º de 9). A1, A5, A6, A7, A8,
  A9 e C usam esse caminho; A3 usa a mediana das t-estatísticas dos 9 caminhos; A4 conta os 9;
- teste contra o acaso da carteira (A10): a posição de todos os ativos é deslocada no tempo pelo
  mesmo número de dias (a exposição e o giro ficam iguais, a relação com o preço some).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from src import acaso
from trader import avaliacao
from trader.validacao import bootstrap_diferenca_de_sharpe

# --- limiares aprovados (v0.1) -------------------------------------------------------------
DSR_MINIMO = 0.95  # A1
PBO_MAXIMO = 0.25  # A2
T_MINIMO = 3.0  # A3
CAMINHOS_POSITIVOS_MINIMOS = 8  # A4 (de 9)
FRACAO_DE_ATIVOS_POSITIVOS_MINIMA = 0.60  # A6
PARTICIPACAO_MAXIMA = 0.25  # A7
FRACAO_DE_ANOS_POSITIVOS_MINIMA = 0.65  # A8
DSR_MINIMO_NO_ESTRESSE = 0.90  # A9
P_VALOR_MAXIMO_DO_ACASO = 0.05  # A10: acima do percentil 95
SHARPE_MINIMO_NO_HOLDOUT = 0.30  # B1
DESCONTO_DE_DECAIMENTO = 0.50  # B1
QUEDA_MAXIMA_RELATIVA = 1.5  # B2
CONFIANCA_DO_MINTRL = 0.95  # C
DIAS_POR_ANO = 252


@dataclass(frozen=True)
class Item:
    codigo: str
    descricao: str
    valor: float | None
    limite: str
    passou: bool


@dataclass(frozen=True)
class Veredito:
    itens: list[Item]
    inconclusivo: bool = False
    motivo_inconclusivo: str = ""

    @property
    def aprovado(self) -> bool:
        return all(i.passou for i in self.itens) and not self.inconclusivo

    @property
    def reprovados(self) -> list[str]:
        return [i.codigo for i in self.itens if not i.passou]

    def para_registro(self) -> dict:
        """O que vai para o registro de tentativas (`aprovado_em_A` destrava o holdout)."""
        return {
            "aprovado": self.aprovado,
            "inconclusivo": self.inconclusivo,
            "motivo_inconclusivo": self.motivo_inconclusivo,
            "reprovados": self.reprovados,
            "itens": [asdict(i) for i in self.itens],
        }


@dataclass
class EvidenciaDoDesenvolvimento:
    """Tudo o que a seção 5A precisa, vindo do CPCV do candidato."""

    caminhos: list[pd.Series]  # 9 carteiras fora da amostra, custos ×1
    caminhos_x2: list[pd.Series]  # os mesmos, custos ×2
    por_ativo: dict[str, pd.Series]  # retornos por ativo no caminho mediano (×1)
    b1: pd.Series  # carteira da baseline B1 nas mesmas datas (×1)
    candidatos: (
        pd.DataFrame
    )  # carteiras das configurações comparadas (inclui o candidato)
    candidatos_x2: pd.DataFrame  # as mesmas, custos ×2
    tentativas_totais: int  # `Registro.total_para_o_dsr()`
    p_valor_do_acaso: float  # teste contra o acaso da carteira
    vazamento: dict[str, bool] = field(default_factory=dict)  # seção 8: todas True


def _sharpe(r: pd.Series) -> float:
    return avaliacao.sharpe(r, DIAS_POR_ANO)


def indice_do_caminho_mediano(caminhos: list[pd.Series]) -> int:
    sharpes = np.array([_sharpe(c) for c in caminhos])
    ordem = np.argsort(np.where(np.isnan(sharpes), -np.inf, sharpes))
    return int(ordem[len(ordem) // 2])


def _dsr(retorno: pd.Series, candidatos: pd.DataFrame, tentativas_totais: int) -> float:
    extras = max(0, tentativas_totais - candidatos.shape[1])
    return acaso.calcular_sharpe_deflacionado(
        retorno, candidatos, tentativas_extras=extras
    ).probabilidade


def avaliar_desenvolvimento(e: EvidenciaDoDesenvolvimento) -> Veredito:
    """Critérios A1 a A10 e C, no desenvolvimento. Todos precisam passar."""
    if len(e.caminhos) != 9 or len(e.caminhos_x2) != 9:
        raise ValueError("O critério pede os 9 caminhos do CPCV (custos ×1 e ×2).")
    m = indice_do_caminho_mediano(e.caminhos)
    mediano, mediano_x2 = e.caminhos[m].dropna(), e.caminhos_x2[m].dropna()
    itens: list[Item] = []

    dsr = _dsr(mediano, e.candidatos, e.tentativas_totais)
    itens.append(
        Item(
            "A1",
            "Sharpe deflacionado (todas as tentativas)",
            dsr,
            f">= {DSR_MINIMO}",
            bool(dsr >= DSR_MINIMO),
        )
    )
    pbo = acaso.calcular_pbo(e.candidatos).probabilidade
    itens.append(Item("A2", "PBO", pbo, f"<= {PBO_MAXIMO}", bool(pbo <= PBO_MAXIMO)))
    t = float(np.nanmedian([avaliacao.t_estatistica(c) for c in e.caminhos]))
    itens.append(
        Item(
            "A3",
            "t-estatística (mediana dos 9 caminhos)",
            t,
            f">= {T_MINIMO}",
            bool(t >= T_MINIMO),
        )
    )
    positivos = int(sum(_sharpe(c) > 0 for c in e.caminhos))
    itens.append(
        Item(
            "A4",
            "caminhos com Sharpe > 0",
            float(positivos),
            f">= {CAMINHOS_POSITIVOS_MINIMOS} de 9",
            positivos >= CAMINHOS_POSITIVOS_MINIMOS,
        )
    )
    boot = bootstrap_diferenca_de_sharpe(mediano, e.b1)
    itens.append(
        Item(
            "A5",
            "contra a B1: limite inferior de 90% da diferença de Sharpe",
            boot["ic90_inferior"],
            "> 0",
            bool(boot["ic90_inferior"] > 0),
        )
    )
    sharpes_por_ativo = pd.Series({k: _sharpe(v) for k, v in e.por_ativo.items()})
    fracao = float((sharpes_por_ativo > 0).mean()) if len(sharpes_por_ativo) else 0.0
    itens.append(
        Item(
            "A6",
            "fração dos ativos com Sharpe > 0",
            fracao,
            f">= {FRACAO_DE_ATIVOS_POSITIVOS_MINIMA}",
            fracao >= FRACAO_DE_ATIVOS_POSITIVOS_MINIMA,
        )
    )
    participacao = avaliacao.participacao_por_ativo(
        avaliacao.montar_carteira(e.por_ativo)
    )
    maior = float(participacao.max()) if participacao.notna().any() else float("nan")
    itens.append(
        Item(
            "A7",
            "maior participação de um ativo no resultado",
            maior,
            f"<= {PARTICIPACAO_MAXIMA}",
            bool(maior <= PARTICIPACAO_MAXIMA),
        )
    )
    anos = avaliacao.fracao_de_anos_positivos(mediano)
    itens.append(
        Item(
            "A8",
            "anos civis com retorno > 0",
            anos,
            f">= {FRACAO_DE_ANOS_POSITIVOS_MINIMA}",
            bool(anos >= FRACAO_DE_ANOS_POSITIVOS_MINIMA),
        )
    )
    sharpe_x2 = _sharpe(mediano_x2)
    dsr_x2 = _dsr(mediano_x2, e.candidatos_x2, e.tentativas_totais)
    itens.append(
        Item(
            "A9",
            "custos ×2: Sharpe e DSR",
            sharpe_x2,
            f"Sharpe > 0 e DSR >= {DSR_MINIMO_NO_ESTRESSE} (DSR = {dsr_x2:.3f})",
            bool(sharpe_x2 > 0 and dsr_x2 >= DSR_MINIMO_NO_ESTRESSE),
        )
    )
    itens.append(
        Item(
            "A10",
            "contra o acaso: p-valor",
            e.p_valor_do_acaso,
            f"<= {P_VALOR_MAXIMO_DO_ACASO}",
            bool(e.p_valor_do_acaso <= P_VALOR_MAXIMO_DO_ACASO),
        )
    )
    vazamento_ok = bool(e.vazamento) and all(e.vazamento.values())
    itens.append(
        Item(
            "V",
            "verificações de vazamento da seção 8",
            None,
            "todas presentes e aprovadas",
            vazamento_ok,
        )
    )

    minimo = acaso.calcular_comprimento_minimo(mediano, CONFIANCA_DO_MINTRL)
    curto = not np.isfinite(minimo) or minimo > len(mediano)
    motivo = (
        f"MinTRL de {minimo:.0f} dias e só há {len(mediano)}"
        if curto and np.isfinite(minimo)
        else ("Sharpe não positivo: MinTRL infinito" if curto else "")
    )
    # Sharpe negativo já reprova em A1/A3/A4; "inconclusivo" só quando tudo o resto passou
    inconclusivo = curto and all(i.passou for i in itens)
    return Veredito(itens, inconclusivo, motivo if inconclusivo else "")


def avaliar_holdout(
    holdout: pd.Series,
    holdout_x2: pd.Series,
    b1_no_holdout: pd.Series,
    sharpe_do_desenvolvimento: float,
    queda_mediana_do_desenvolvimento: float,
) -> Veredito:
    """Critérios B1 a B4, no holdout (pontuado uma vez, via `trader.holdout.pontuar`)."""
    sharpe = _sharpe(holdout)
    piso = max(
        SHARPE_MINIMO_NO_HOLDOUT, DESCONTO_DE_DECAIMENTO * sharpe_do_desenvolvimento
    )
    queda = avaliacao.maior_queda(holdout)
    limite_da_queda = QUEDA_MAXIMA_RELATIVA * abs(queda_mediana_do_desenvolvimento)
    sharpe_b1 = _sharpe(b1_no_holdout)
    sharpe_x2 = _sharpe(holdout_x2)
    itens = [
        Item(
            "B1",
            "Sharpe líquido no holdout",
            sharpe,
            f">= {piso:.3f}",
            bool(sharpe >= piso),
        ),
        Item(
            "B2",
            "queda máxima no holdout",
            queda,
            f">= -{limite_da_queda:.3f}",
            bool(abs(queda) <= limite_da_queda),
        ),
        Item(
            "B3",
            "Sharpe acima da B1 no holdout",
            sharpe - sharpe_b1,
            "> 0",
            bool(sharpe > sharpe_b1),
        ),
        Item(
            "B4", "custos ×2: Sharpe no holdout", sharpe_x2, "> 0", bool(sharpe_x2 > 0)
        ),
    ]
    return Veredito(itens)


def p_valor_do_acaso_da_carteira(
    posicoes: pd.DataFrame,
    retornos: pd.DataFrame,
    custo_por_lado: pd.Series,
    sorteios: int = 1000,
    semente: int = 42,
) -> dict:
    """A10: desloca no tempo as posições de todos os ativos juntas e refaz a carteira.

    `posicoes` (decididas no fim do dia) e `retornos` dos ativos: mesmas datas e colunas; vazio =
    ativo sem dado no dia. Usa a conta simples (posição de ontem × retorno − custo do giro), a mesma
    para o real e para os sorteios. Devolve o Sharpe real, o percentil 95 dos sorteios e o p-valor.
    """
    if not posicoes.index.equals(retornos.index) or list(posicoes.columns) != list(
        retornos.columns
    ):
        raise ValueError("Posições e retornos precisam das mesmas datas e colunas.")
    disponivel = retornos.notna().to_numpy()
    r = retornos.fillna(0.0).to_numpy(dtype=float)
    p = posicoes.fillna(0.0).to_numpy(dtype=float)
    custo = custo_por_lado.reindex(posicoes.columns).fillna(0.0).to_numpy(dtype=float)
    n = len(p)

    def sharpe_da_carteira(desejada: np.ndarray) -> float:
        posicao = np.vstack([np.zeros((1, desejada.shape[1])), desejada[:-1]])
        giro = np.abs(np.diff(posicao, axis=0, prepend=0.0))
        diario = np.where(disponivel, posicao * r - giro * custo, np.nan)
        com_dado = disponivel.any(axis=1)
        carteira = np.nanmean(diario[com_dado], axis=1)
        desvio = carteira.std(ddof=1)
        return (
            float(carteira.mean() / desvio * np.sqrt(DIAS_POR_ANO))
            if desvio > 0
            else np.nan
        )

    real = sharpe_da_carteira(p)
    folga = max(21, n // 10)
    if n - 2 * folga < 1:
        raise ValueError("Poucos dados para o teste contra o acaso.")
    deslocamentos = np.random.default_rng(semente).integers(
        folga, n - folga, size=sorteios
    )
    sorteados = np.array(
        [sharpe_da_carteira(np.roll(p, int(k), axis=0)) for k in deslocamentos]
    )
    sorteados = sorteados[~np.isnan(sorteados)]
    return {
        "sharpe_real": real,
        "percentil_95": float(np.percentile(sorteados, 95)),
        "p_valor": float((1 + (sorteados >= real).sum()) / (1 + len(sorteados))),
    }
