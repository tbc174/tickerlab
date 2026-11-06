"""A conta da cobertura das garantias de uma exposição (B-17), sem banco e sem relógio escondido.

Só aritmética e alertas: nada aqui diz se uma garantia é boa ou ruim, e nada converte moeda. A fórmula
vai junto da resposta, com a parcela de cada garantia e o que ficou de fora (e por quê), para a pessoa
conferir a conta à mão. Entra `Decimal`, sai texto: o resultado vira JSON sem perder casa decimal.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

FORMULA = (
    "valor protegido = max(0, valor avaliado × (1 − haircut) − ônus anteriores); "
    "cobertura = soma do valor protegido das garantias vigentes, na moeda da exposição ÷ exposição"
)
DIAS_DO_AVISO_DE_VALIDADE = 30

SEM_VALIDADE = "sem_validade"
VIGENTE = "vigente"
VENCE_EM_30_DIAS = "vence_em_30_dias"
VENCIDA = "vencida"

MOTIVO_MOEDA_DIFERENTE = "moeda_diferente"
MOTIVO_VENCIDA = "vencida"

ZERO = Decimal(0)


@dataclass(frozen=True)
class GarantiaParaAConta:
    """O que a conta precisa de uma garantia; ids em texto, valores em `Decimal`."""

    id: str
    valor_avaliado: Decimal
    haircut: Decimal
    onus_anteriores: Decimal
    moeda: str
    valido_ate: date | None


def valor_protegido(
    valor_avaliado: Decimal, haircut: Decimal, onus_anteriores: Decimal = ZERO
) -> Decimal:
    """O que a garantia protege depois do desconto e dos ônus que pesam antes dela; nunca negativo."""
    protegido = valor_avaliado * (1 - haircut) - onus_anteriores
    return max(ZERO, protegido)


def situacao_da_validade(valido_ate: date | None, hoje: date) -> str:
    """`sem_validade`, `vigente`, `vence_em_30_dias` ou `vencida`; vale até o fim do dia `valido_ate`."""
    if valido_ate is None:
        return SEM_VALIDADE
    if valido_ate < hoje:
        return VENCIDA
    if valido_ate <= hoje + timedelta(days=DIAS_DO_AVISO_DE_VALIDADE):
        return VENCE_EM_30_DIAS
    return VIGENTE


def _razao(soma: Decimal, exposicao: Decimal | None) -> Decimal | None:
    if exposicao is None or exposicao <= ZERO:
        return None  # sem dívida a cobrir não há cobertura: nunca divisão por zero
    return soma / exposicao


def _texto(valor: Decimal | None) -> str | None:
    return None if valor is None else format(valor, "f")


def calcular_cobertura(
    *,
    exposicao: Decimal | None,
    moeda: str,
    garantias: list[GarantiaParaAConta],
    hoje: date,
) -> dict:
    """Cobertura da exposição pelas garantias, com a fórmula, as parcelas e o que ficou de fora."""
    parcelas = []
    fora = []
    vigentes = ZERO
    todas = ZERO
    for garantia in garantias:
        situacao = situacao_da_validade(garantia.valido_ate, hoje)
        if garantia.moeda != moeda:
            fora.append({"garantia_id": garantia.id, "motivo": MOTIVO_MOEDA_DIFERENTE})
            continue
        protegido = valor_protegido(
            garantia.valor_avaliado, garantia.haircut, garantia.onus_anteriores
        )
        todas += protegido
        if situacao == VENCIDA:
            fora.append({"garantia_id": garantia.id, "motivo": MOTIVO_VENCIDA})
        else:
            vigentes += protegido
        parcelas.append(
            {
                "garantia_id": garantia.id,
                "valor_protegido": _texto(protegido),
                "validade": situacao,
            }
        )
    return {
        "formula": FORMULA,
        "moeda": moeda,
        "exposicao": _texto(exposicao),
        "valor_protegido_vigente": _texto(vigentes),
        "cobertura": _texto(_razao(vigentes, exposicao)),
        "cobertura_contando_as_vencidas": _texto(_razao(todas, exposicao)),
        "parcelas": parcelas,
        "fora_da_conta": fora,
    }
