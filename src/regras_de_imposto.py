"""Regras de imposto de renda que o TickerLab usa, num lugar só, cada uma com a fonte oficial.

Servem às ferramentas do site (DARF de ações, renda fixa com IR; exportadas para
`web/conteudo/regras_de_imposto.json`) e ao imposto simplificado do backtest (`src/imposto.py`).

Conferidas em 14/10/2026 no *Perguntas e Respostas IRPF 2026* (v1.00, Receita Federal, 23/04/2026),
que segue a legislação até dez/2025. Em 2026 nada disso mudou: a MP 1.303/2025, que trocaria a
tabela regressiva por 17,5%, caducou em 08/10/2025; a Lei 15.270/2025 mexeu em dividendos acima de
R$ 50 mil por mês e na tributação mínima de altas rendas, não no ganho líquido em bolsa.
**Ao mudar a lei, mude aqui, ponha a fonte nova e a data.** Nada disso é orientação tributária.
"""

from dataclasses import dataclass

PERGUNTAS_E_RESPOSTAS = (
    "https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/"
    "perguntas-e-respostas/dirpf/p-r-irpf-2026-v1-00-2026-04-23.pdf"
)
LEI_9430 = "https://www.planalto.gov.br/ccivil_03/leis/l9430.htm"
CONFERIDA_EM = "2026-10-14"


@dataclass(frozen=True)
class Regra:
    chave: str
    descricao: str
    valor: float | str
    fonte: str
    onde: str  # a pergunta do Perguntas e Respostas ou o artigo da lei
    conferida_em: str = CONFERIDA_EM


def _pr(chave: str, descricao: str, valor: float | str, pergunta: int) -> Regra:
    return Regra(chave, descricao, valor, PERGUNTAS_E_RESPOSTAS, f"pergunta {pergunta}")


REGRAS_DAS_ACOES: tuple[Regra, ...] = (
    _pr("aliquota_comum", "Ações, operações comuns (swing trade)", 0.15, 706),
    _pr("aliquota_day_trade", "Ações, day trade", 0.20, 706),
    _pr(
        "isencao_vendas_no_mes",
        "Isento quando o total vendido de ações no mês (mercado à vista, sem day trade) "
        "não passa de",
        20_000,
        707,
    ),
    _pr("irrf_comum", "Imposto retido na fonte nas vendas comuns", 0.00005, 706),
    _pr(
        "irrf_day_trade",
        "Imposto retido na fonte sobre o ganho do day trade",
        0.01,
        712,
    ),
    _pr("codigo_do_darf", "Código do DARF de ganhos em bolsa", "6015", 730),
    Regra(
        "darf_minimo",
        "DARF abaixo deste valor não se paga: soma ao imposto dos meses seguintes",
        10,
        LEI_9430,
        "art. 68",
    ),
)

# renda fixa (CDB, Tesouro, debêntures comuns): alíquota pelo prazo da aplicação, em dias;
# a última faixa vale para qualquer prazo maior (None)
TABELA_REGRESSIVA: tuple[tuple[int | None, float], ...] = (
    (180, 0.225),
    (360, 0.20),
    (720, 0.175),
    (None, 0.15),
)
FONTE_DA_TABELA = Regra(
    "tabela_regressiva",
    "Renda fixa: 22,5% até 180 dias, 20% até 360, 17,5% até 720, 15% acima",
    "22,5% / 20% / 17,5% / 15%",
    PERGUNTAS_E_RESPOSTAS,
    "pergunta 734",
)
ISENTOS_NA_RENDA_FIXA = Regra(
    "isentos_na_renda_fixa",
    "Isentos para pessoa física: poupança, LCI, LCA, CRI e CRA",
    "poupança, LCI, LCA, CRI, CRA",
    PERGUNTAS_E_RESPOSTAS,
    "pergunta 738",
)
TODAS: tuple[Regra, ...] = (*REGRAS_DAS_ACOES, FONTE_DA_TABELA, ISENTOS_NA_RENDA_FIXA)

_POR_CHAVE = {regra.chave: regra for regra in TODAS}


def valor(chave: str) -> float | str:
    """O valor de uma regra pela chave (erro se não existir)."""
    return _POR_CHAVE[chave].valor


def aliquota_da_renda_fixa(dias: int) -> float:
    """A alíquota da tabela regressiva para uma aplicação de `dias` dias corridos."""
    if dias < 1:
        raise ValueError("O prazo da aplicação precisa ser de pelo menos 1 dia.")
    for ate_dias, aliquota in TABELA_REGRESSIVA:
        if ate_dias is None or dias <= ate_dias:
            return aliquota
    raise AssertionError("a última faixa da tabela vale para qualquer prazo")


def para_o_site() -> dict:
    """O que vai para `web/conteudo/regras_de_imposto.json` (as mesmas regras, em JSON)."""
    return {
        "regras": [
            {
                "chave": r.chave,
                "descricao": r.descricao,
                "valor": r.valor,
                "fonte": r.fonte,
                "onde": r.onde,
                "conferida_em": r.conferida_em,
            }
            for r in TODAS
        ],
        "renda_fixa": [
            {"ate_dias": ate_dias, "aliquota": aliquota}
            for ate_dias, aliquota in TABELA_REGRESSIVA
        ],
    }
