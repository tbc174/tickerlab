"""Custo das taxas e da queda: duas contas que parecem pequenas e não são.

Taxa: uma taxa anual sobre o patrimônio (a de administração de um fundo, por exemplo) é cobrada todo
ano sobre tudo, inclusive sobre o que ela já deixou de render; em 20 anos, 1% ao ano leva quase um
quinto do patrimônio. Aqui a taxa é cobrada no fim de cada ano: valor × (1 + retorno) × (1 − taxa).

Queda: depois de cair 50%, é preciso subir 100% para voltar ao valor de antes.
"""

from dataclasses import dataclass

ANOS_MAXIMOS = 100


@dataclass(frozen=True)
class CustoDaTaxa:
    sem_taxa: float
    com_taxa: float
    ficou_com_a_taxa: (
        float  # o que a taxa levou, contando o que esse dinheiro teria rendido
    )
    fracao_do_resultado: (
        float  # o que a taxa levou, como fração do valor final sem taxa
    )


@dataclass(frozen=True)
class LinhaDaTaxa:
    ano: int
    sem_taxa: float
    com_taxa: float


def _conferir(capital: float, retorno: float, taxa: float, anos: int) -> None:
    if capital < 0:
        raise ValueError("O capital não pode ser negativo.")
    if retorno <= -1:
        raise ValueError("O retorno precisa ser maior que -100% ao ano.")
    if taxa < 0 or taxa >= 1:
        raise ValueError("A taxa precisa estar entre 0% e 100% ao ano.")
    if anos < 0 or anos > ANOS_MAXIMOS:
        raise ValueError(f"O prazo precisa estar entre 0 e {ANOS_MAXIMOS} anos.")


def custo_da_taxa(
    capital: float, retorno: float, taxa: float, anos: int
) -> CustoDaTaxa:
    """Quanto o patrimônio fica com e sem a taxa anual depois de `anos` anos."""
    _conferir(capital, retorno, taxa, anos)
    sem = capital * (1 + retorno) ** anos
    com = capital * ((1 + retorno) * (1 - taxa)) ** anos
    return CustoDaTaxa(
        sem_taxa=sem,
        com_taxa=com,
        ficou_com_a_taxa=sem - com,
        fracao_do_resultado=(sem - com) / sem if sem > 0 else 0.0,
    )


def evolucao_da_taxa(
    capital: float, retorno: float, taxa: float, anos: int
) -> list[LinhaDaTaxa]:
    """Ano a ano, do 0 ao último, o patrimônio sem e com a taxa."""
    _conferir(capital, retorno, taxa, anos)
    return [
        LinhaDaTaxa(
            ano=ano,
            sem_taxa=capital * (1 + retorno) ** ano,
            com_taxa=capital * ((1 + retorno) * (1 - taxa)) ** ano,
        )
        for ano in range(anos + 1)
    ]


def alta_para_recuperar(queda: float) -> float:
    """A alta que volta ao valor de antes de uma `queda` (-0,5 → 1,0: cair 50% pede +100%)."""
    if queda <= -1 or queda > 0:
        raise ValueError("A queda precisa estar entre 0% e -100% (sem chegar a -100%).")
    return 1 / (1 + queda) - 1
