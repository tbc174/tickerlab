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
DECRETO_6306 = (
    "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2007/decreto/d6306.htm"
)
LEI_14754 = "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/lei/l14754.htm"
TARIFAS_DO_TESOURO_DIRETO = (
    "https://www.b3.com.br/pt_br/produtos-e-servicos/tarifas/tarifas-de-tesouro-direto/"
)
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
# IOF nos resgates de renda fixa antes de 30 dias (Decreto 6.306/2007, art. 32 e anexo, conferido em
# 15/10/2026 no texto compilado): a fração do rendimento do 1º ao 29º dia; zero a partir do 30º. A
# LCA tem alíquota zero (art. 32, § 2º, V); a LCI não está na lista.
TABELA_DO_IOF: tuple[float, ...] = (
    0.96, 0.93, 0.90, 0.86, 0.83, 0.80, 0.76, 0.73, 0.70, 0.66,
    0.63, 0.60, 0.56, 0.53, 0.50, 0.46, 0.43, 0.40, 0.36, 0.33,
    0.30, 0.26, 0.23, 0.20, 0.16, 0.13, 0.10, 0.06, 0.03,
)  # fmt: skip
IOF_DA_RENDA_FIXA = Regra(
    "iof_resgate_antes_de_30_dias",
    "IOF sobre o rendimento no resgate antes de 30 dias (CDB, Tesouro, LCI); LCA tem alíquota zero",
    "96% no 1º dia ... 3% no 29º; 0 a partir do 30º",
    DECRETO_6306,
    "art. 32 e anexo; LCA: art. 32, § 2º, V",
    conferida_em="2026-10-15",
)
# a custódia do Tesouro Direto é tarifa da B3 (página de tarifas, conferida em 15/10/2026): 0,2% ao
# ano sobre o valor dos títulos, provisionada todo dia e cobrada no resgate, no vencimento ou nos
# juros; no Tesouro Selic, isenta até R$ 10 mil por CPF (cobra só sobre o excedente)
CUSTODIA_DO_TESOURO = Regra(
    "custodia_do_tesouro",
    "Taxa de custódia do Tesouro Direto (B3), ao ano sobre o valor dos títulos",
    0.002,
    TARIFAS_DO_TESOURO_DIRETO,
    "Tarifas de Tesouro Direto",
    conferida_em="2026-10-15",
)
CUSTODIA_ISENTA_NO_SELIC = Regra(
    "custodia_isenta_no_selic_ate",
    "No Tesouro Selic, sem custódia até este valor por CPF (cobra só sobre o que passar)",
    10_000,
    TARIFAS_DO_TESOURO_DIRETO,
    "Tarifas de Tesouro Direto",
    conferida_em="2026-10-15",
)
# fundos de investimento (Lei 14.754/2023, art. 17, conferido em 15/10/2026 no texto compilado): o
# IR é retido no último dia útil de maio e de novembro (o "come-cotas") ou no resgate, se antes;
# 15% na regra geral (longo prazo) e 20% nos fundos de curto prazo (art. 6º da Lei 11.053/2004);
# no resgate, o complemento até a tabela (P&R IRPF 2026, pergunta 736)
COME_COTAS_LONGO = Regra(
    "come_cotas_longo_prazo",
    "Fundos de longo prazo: IR retido em maio e novembro (come-cotas)",
    0.15,
    LEI_14754,
    "art. 17, § 1º, I, a",
    conferida_em="2026-10-15",
)
COME_COTAS_CURTO = Regra(
    "come_cotas_curto_prazo",
    "Fundos de curto prazo: IR retido em maio e novembro (come-cotas)",
    0.20,
    LEI_14754,
    "art. 17, § 1º, II, a",
    conferida_em="2026-10-15",
)
FUNDOS_DE_CURTO_PRAZO = Regra(
    "tabela_dos_fundos_de_curto_prazo",
    "Fundos de curto prazo no resgate: 22,5% até 180 dias, 20% depois",
    "22,5% / 20%",
    PERGUNTAS_E_RESPOSTAS,
    "pergunta 736",
    conferida_em="2026-10-15",
)
TODAS: tuple[Regra, ...] = (
    *REGRAS_DAS_ACOES,
    FONTE_DA_TABELA,
    ISENTOS_NA_RENDA_FIXA,
    IOF_DA_RENDA_FIXA,
    CUSTODIA_DO_TESOURO,
    CUSTODIA_ISENTA_NO_SELIC,
    COME_COTAS_LONGO,
    COME_COTAS_CURTO,
    FUNDOS_DE_CURTO_PRAZO,
)
DIAS_DO_CURTO_PRAZO = 180
ALIQUOTAS_DO_CURTO_PRAZO = (0.225, 0.20)  # até 180 dias, depois

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


def aliquota_do_iof(dias: int) -> float:
    """A fração do rendimento que o IOF leva num resgate depois de `dias` dias corridos."""
    if dias < 1:
        raise ValueError("O prazo da aplicação precisa ser de pelo menos 1 dia.")
    return TABELA_DO_IOF[dias - 1] if dias <= len(TABELA_DO_IOF) else 0.0


def aliquota_do_fundo(dias: int, longo_prazo: bool) -> float:
    """A alíquota total do IR no resgate de um fundo: a tabela regressiva (longo prazo) ou 22,5%
    até 180 dias e 20% depois (curto prazo)."""
    if longo_prazo:
        return aliquota_da_renda_fixa(dias)
    if dias < 1:
        raise ValueError("O prazo da aplicação precisa ser de pelo menos 1 dia.")
    ate_180, depois = ALIQUOTAS_DO_CURTO_PRAZO
    return ate_180 if dias <= DIAS_DO_CURTO_PRAZO else depois


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
        "iof": list(TABELA_DO_IOF),
        "fundos": {
            "come_cotas_longo": COME_COTAS_LONGO.valor,
            "come_cotas_curto": COME_COTAS_CURTO.valor,
            "curto_prazo": {
                "ate_dias": DIAS_DO_CURTO_PRAZO,
                "aliquotas": list(ALIQUOTAS_DO_CURTO_PRAZO),
            },
        },
        "custodia_do_tesouro": {
            "taxa": CUSTODIA_DO_TESOURO.valor,
            "isento_no_selic_ate": CUSTODIA_ISENTA_NO_SELIC.valor,
        },
    }
