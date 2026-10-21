"""Dicionário das features de crédito (B-30): nome, fórmula, fonte, frequência e defasagem de cada uma.

É o lugar só das fórmulas: `src/credito/features.py` escreve no rastro de cada feature a fórmula que
está aqui, e o teste confere que toda feature calculada tem a sua entrada (e o contrário). Mudou uma
fórmula, suba `VERSAO_DAS_FEATURES`.

A defasagem é o tempo entre o fim do período e o dia em que o número fica público; a feature vale a
partir desse dia (`disponivel_em`), nunca a partir do fim do período.
"""

from dataclasses import asdict, dataclass

VERSAO_DAS_FEATURES = "features de crédito 1"  # sobe quando uma fórmula abaixo mudar
REAIS, VEZES, FRACAO = "reais", "vezes", "fração"

_CVM = "CVM: DFP e ITR das companhias abertas (demonstrações consolidadas)"
_TRIMESTRAL = "Trimestral (ITR nos três primeiros trimestres, DFP no fim do exercício)"
_ANUAL = "Anual (DFP)"
_DEFASAGEM_DO_ITR = (
    "Até 45 dias depois do fim do trimestre (ITR) e até 3 meses depois do fim do exercício (DFP); "
    "vale a partir do dia em que a CVM recebeu o documento"
)
_DEFASAGEM_DA_DFP = "Até 3 meses depois do fim do exercício; vale a partir do dia em que a CVM recebeu a DFP"
_12M = "12 meses: último DFP + acumulado do ano no último ITR − o mesmo período do ano anterior"
_BALANCO = "balanço mais recente que a CVM já tinha recebido no dia"


@dataclass(frozen=True)
class EntradaDoDicionario:
    """Uma feature: o que é, como se calcula, de onde vem e quando fica pública."""

    chave: str
    nome: str
    unidade: str
    formula: str
    fonte: str
    frequencia: str
    defasagem: str

    def como_dict(self) -> dict:
        return asdict(self)


DICIONARIO: dict[str, EntradaDoDicionario] = {
    entrada.chave: entrada
    for entrada in (
        EntradaDoDicionario(
            "divida_liquida_sobre_ebitda",
            "Dívida líquida ÷ EBITDA (alavancagem)",
            VEZES,
            "(empréstimos e financiamentos de curto e de longo prazo − caixa e aplicações, no "
            f"{_BALANCO}) ÷ (EBIT + depreciação e amortização; {_12M}); EBITDA negativo ou zero: "
            "não observado",
            _CVM, _TRIMESTRAL, _DEFASAGEM_DO_ITR,
        ),
        EntradaDoDicionario(
            "divida_liquida_sobre_pl",
            "Dívida líquida ÷ patrimônio (alavancagem)",
            VEZES,
            "dívida líquida ÷ (patrimônio líquido − participação dos minoritários), no "
            f"{_BALANCO}; patrimônio negativo ou zero: não observado",
            _CVM, _TRIMESTRAL, _DEFASAGEM_DO_ITR,
        ),
        EntradaDoDicionario(
            "cobertura_de_juros_ebitda",
            "EBITDA ÷ despesa financeira (cobertura de juros)",
            VEZES,
            f"(EBIT + depreciação e amortização) ÷ |despesas financeiras da DRE| ({_12M}); sem "
            "despesa financeira: não observado",
            _CVM, _TRIMESTRAL, _DEFASAGEM_DO_ITR,
        ),
        EntradaDoDicionario(
            "cobertura_de_juros_ebit",
            "EBIT ÷ despesa financeira (cobertura de juros)",
            VEZES,
            f"EBIT ÷ |despesas financeiras da DRE| ({_12M}); sem despesa financeira: não observado",
            _CVM, _TRIMESTRAL, _DEFASAGEM_DO_ITR,
        ),
        EntradaDoDicionario(
            "liquidez_corrente",
            "Liquidez corrente",
            VEZES,
            f"ativo circulante ÷ passivo circulante, no {_BALANCO}; passivo circulante zero: não "
            "observado",
            _CVM, _TRIMESTRAL, _DEFASAGEM_DO_ITR,
        ),
        EntradaDoDicionario(
            "caixa_sobre_divida_de_curto_prazo",
            "Caixa ÷ dívida de curto prazo (liquidez)",
            VEZES,
            "(caixa e equivalentes + aplicações financeiras) ÷ empréstimos e financiamentos de "
            f"curto prazo, no {_BALANCO}; sem dívida de curto prazo: não observado",
            _CVM, _TRIMESTRAL, _DEFASAGEM_DO_ITR,
        ),
        EntradaDoDicionario(
            "crescimento_da_receita_1_ano",
            "Crescimento da receita em 1 ano",
            FRACAO,
            "receita do último DFP ÷ receita do DFP do ano anterior − 1; base negativa ou zero: "
            "não observado",
            _CVM, _ANUAL, _DEFASAGEM_DA_DFP,
        ),
        EntradaDoDicionario(
            "crescimento_da_receita_5_anos",
            "Crescimento da receita em 5 anos (composto, ao ano)",
            FRACAO,
            "(receita do último DFP ÷ receita do DFP de 5 anos antes) ^ (1 ÷ 5) − 1; base negativa "
            "ou zero: não observado",
            _CVM, _ANUAL, _DEFASAGEM_DA_DFP,
        ),
    )
}  # fmt: skip


def dicionario_como_lista() -> list[dict]:
    """O dicionário para a API e para a documentação, na ordem em que as features saem."""
    return [entrada.como_dict() for entrada in DICIONARIO.values()]
