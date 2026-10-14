"""Metodologia pública das notas, dos padrões e das fórmulas (série 2 da base de ML, PR 8; ADR 0033).

Um lugar só para o que o público lê sobre como o relatório completo de empresa qualifica os números:
a página de metodologia do site (`web/src/paginas/Metodologia.tsx`, pelo `web/conteudo/notas.json`)
mostra estes textos, e o relatório (tela e PDF) aponta para eles. Os números citados vêm das
constantes que os cálculos usam (`src/padroes.py`, `src/notas.py`, `src/setores.py`,
`src/notas_classicas.py`, `src/valuation.py`), para o texto nunca dizer um limite diferente do que
o código aplica.
"""

from dataclasses import asdict, dataclass

from src import notas, notas_classicas, padroes, setores, valuation
from src.qualidade_texto import REGRAS

# a seção da página de metodologia (o selo de qualidade fica em `qualidade_texto.ANCORA_NO_SITE`)
ANCORA_NO_SITE = "padroes-notas-e-formulas"
URL_NO_SITE = f"https://tickerlab.com.br/metodologia.html#{ANCORA_NO_SITE}"
MAIOR_E_MELHOR = "quanto maior, melhor"
MENOR_E_MELHOR = "quanto menor, melhor"


def _numero(valor: float) -> str:
    """2.6 → "2,6"; −1.78 → "−1,78" (com o sinal de menos tipográfico)."""
    return f"{valor:g}".replace(".", ",").replace("-", "−")


def _lista(itens: list[str]) -> str:
    return ", ".join(itens[:-1]) + f" e {itens[-1]}" if len(itens) > 1 else itens[0]


@dataclass(frozen=True)
class Grupo:
    nome: str
    setores_da_cvm: str  # os trechos do setor informado à CVM que caem no grupo


@dataclass(frozen=True)
class IndicadorDaNota:
    nome: str
    direcao: str


@dataclass(frozen=True)
class Formula:
    nome: str
    formula: str
    leitura: str  # como ler o número e de onde vem a regra


_REGRAS_FORA = _lista(
    [REGRAS[r].titulo.lower() for r in padroes.REGRAS_QUE_TIRAM_DO_PADRAO]
)

PADROES: tuple[str, ...] = (
    (
        "Cada nota compara o número da empresa com o padrão do grupo de setores dela: os "
        "percentis do mesmo indicador entre as empresas do grupo, calculados pelo TickerLab com as "
        "demonstrações entregues à CVM (DFP e ITR) e com os mesmos cálculos da tela Fundamentos."
    ),
    (
        "Só entra o que era público na data de corte: de cada balanço vale a versão entregue à "
        "CVM até aquele dia. Uma reapresentação feita depois não muda o padrão de uma data antiga; "
        "por isso o padrão de qualquer data passada pode ser refeito e dá o mesmo resultado."
    ),
    (
        "Os cortes são o fim de cada mês; os padrões que o relatório mostra são os do corte mais "
        "recente, com o número de empresas e a data ao lado."
    ),
    (
        f"Grupo com menos de {setores.MINIMO_DE_EMPRESAS} empresas com o indicador é pequeno demais "
        "para um percentil: a empresa é comparada com o mercado inteiro (as não financeiras), e o "
        "texto avisa. O grupo financeiro nunca é comparado com as não financeiras: sem empresas "
        "suficientes, fica sem padrão."
    ),
    (
        f"Empresa com achado aberto do selo de qualidade que afeta o balanço inteiro ({_REGRAS_FORA}) "
        "fica fora do padrão daquele corte, para um número em conferência não mudar a régua dos "
        "outros."
    ),
    (
        f"Método na versão {padroes.VERSAO_DOS_PADROES}: mudou um indicador ou a regra, a versão "
        "sobe e os padrões são recalculados."
    ),
)

GRUPOS: tuple[Grupo, ...] = tuple(
    Grupo(nome, _lista(list(trechos))) for nome, trechos in setores.GRUPOS.values()
)

INDICADORES_DAS_NOTAS: tuple[IndicadorDaNota, ...] = tuple(
    IndicadorDaNota(nome, MAIOR_E_MELHOR if maior_e_melhor else MENOR_E_MELHOR)
    for nome, maior_e_melhor in padroes.INDICADORES.values()
)

_QUINTIS = _lista([f"{q}%" for q in notas.LIMITES_DOS_QUINTIS])
_FAIXA = notas.FAIXAS_FIXAS["conversao_de_caixa"]

NOTAS: tuple[str, ...] = (
    (
        f"Qualidade, de {notas.QUALIDADES[-1]} a {notas.QUALIDADES[0]}: pelos quintis do grupo "
        f"({_QUINTIS}), na direção do indicador. Numa margem, ficar acima de 80% das empresas do "
        "grupo é ótimo; na dívida e no ciclo de caixa, ótimo é ficar abaixo de 80% delas."
    ),
    (
        "Preço, barato, justo ou caro: P/L e P/VP por duas réguas. A do setor: abaixo do percentil "
        f"{notas.TERCIL_BAIXO}% do grupo é barato, acima do {notas.TERCIL_ALTO}% é caro. A do "
        "próprio histórico da empresa: os mesmos tercis, com o múltiplo de cada ano (o preço do "
        f"último pregão do ano), pedindo pelo menos {valuation.MINIMO_DE_ANOS} anos. Se as duas "
        "réguas concordam, vale a nota delas; se discordam, a nota é justo e as duas aparecem. "
        "Sem histórico, vale o setor. Com prejuízo (múltiplo negativo), não há nota."
    ),
    (
        "Toda nota aparece com o número, o padrão (onde fica a metade do meio do grupo), o grupo, "
        "a quantidade de empresas, a data do corte e a fonte. Número com selo de qualidade mostra "
        "o aviso ao lado da nota."
    ),
    (
        f"{_FAIXA.nome}: nota por faixa fixa e pública, sem comparar com o setor, porque um número "
        f"alto costuma vir de lucro pequeno, não de caixa bom. Abaixo de {_numero(_FAIXA.abaixo_de)}×, "
        f"{_FAIXA.notas[0]}; de {_numero(_FAIXA.abaixo_de)}× a {_numero(_FAIXA.ate)}×, "
        f"{_FAIXA.notas[1]}; acima de {_numero(_FAIXA.ate)}×, {_FAIXA.notas[2]}. Com prejuízo, não "
        "há nota."
    ),
    notas.AVISO,
)

_ALTMAN_LEITURA = (
    f"{notas_classicas.ALTMAN_REFERENCIA}. X1 = capital de giro / ativo; X2 = lucros retidos / "
    "ativo; X3 = EBIT / ativo; X4 = patrimônio / passivo. Faixas do artigo: acima de "
    f"{_numero(notas_classicas.ALTMAN_SEGURA)}, segura; abaixo de "
    f"{_numero(notas_classicas.ALTMAN_AFLICAO)}, de aflição; no meio, cinzenta. A faixa diz onde o "
    "número cai na amostra do artigo, não que a empresa vai quebrar."
)
_BENEISH_LEITURA = (
    f"{notas_classicas.BENEISH_REFERENCIA}. Cada índice compara o ano com o anterior (prazo de "
    "receber, margem bruta, qualidade do ativo, crescimento da receita, depreciação, despesas, "
    "accruals e alavancagem). Acima de "
    f"{_numero(notas_classicas.BENEISH_LIMITE)}, o número fica acima do limite que o artigo usou "
    "para separar as empresas da amostra: pede uma leitura atenta das demonstrações, não é "
    "acusação de manipulação."
)
_PIOTROSKI_LEITURA = (
    f"{notas_classicas.PIOTROSKI_REFERENCIA}. Os 9 critérios: ROA positivo, caixa operacional "
    "positivo, ROA subiu, caixa operacional maior que o lucro, alavancagem caiu, liquidez "
    "corrente subiu, não emitiu ações, margem bruta subiu, giro do ativo subiu. Critério sem "
    "dado não conta ponto e aparece como sem dado."
)

FORMULAS: tuple[Formula, ...] = (
    Formula(
        "DuPont",
        "ROE = margem líquida × giro do ativo × alavancagem",
        "Margem = lucro / receita; giro = receita / ativo; alavancagem = ativo / patrimônio. "
        "Fecha com o ROE da tela: lucro de 12 meses e patrimônio do balanço mais recente, os dois "
        "dos controladores.",
    ),
    Formula(
        "Ciclo de caixa",
        "dias a receber + dias de estoque − dias a pagar",
        "Receber = contas a receber / receita × 365; estoque e pagar = estoques e fornecedores / "
        "custo das vendas × 365, com o saldo médio do último ano quando houver.",
    ),
    Formula(
        "Caixa livre",
        "caixa operacional − capex",
        "Capex = compras de imobilizado e intangível na demonstração dos fluxos de caixa.",
    ),
    Formula(
        "Capex / depreciação",
        "capex / depreciação e amortização",
        "Acima de 1, a empresa investe mais do que o desgaste dos ativos.",
    ),
    Formula(
        "Cobertura de juros",
        "EBIT / despesas financeiras",
        "Sem despesa financeira no período, não se aplica.",
    ),
    Formula(
        "Crescimento composto",
        "(último ano / primeiro ano)^(1 / anos) − 1",
        "Histórico de até 10 DFPs; ano que falta aparece como falta, nunca como zero, e a "
        "variação de um ano para o outro só é calculada entre anos seguidos.",
    ),
    Formula("Piotroski F", notas_classicas.PIOTROSKI_FORMULA, _PIOTROSKI_LEITURA),
    Formula("Altman Z''", notas_classicas.ALTMAN_FORMULA, _ALTMAN_LEITURA),
    Formula("Beneish M", notas_classicas.BENEISH_FORMULA, _BENEISH_LEITURA),
    Formula(
        "P/L e P/VP",
        "preço / lucro por ação; preço / patrimônio por ação",
        "Lucro e patrimônio dos controladores, ações em circulação (sem as de tesouraria). O "
        "preço vem do Yahoo Finance e é usado só para o múltiplo.",
    ),
    Formula(
        "DCF",
        "valor por ação = (caixa livre descontado + perpetuidade descontada − dívida líquida) "
        "/ ações",
        "O caixa livre de hoje cresce à taxa escolhida pela pessoa por N anos, depois à taxa da "
        "perpetuidade, tudo trazido a valor presente pela taxa de desconto. As premissas são de "
        "quem usa; o TickerLab só faz a conta e mostra a tabela de sensibilidade. O desconto "
        "precisa ser maior que o crescimento na perpetuidade. Não é preço-alvo.",
    ),
    Formula(
        "Valuation reverso",
        "o crescimento anual que faz o DCF dar o preço de hoje",
        "Com as mesmas premissas do DCF, procura (por bissecção) o crescimento que o preço atual "
        "supõe. Sem resposta numa faixa razoável, não mostra número.",
    ),
)


def como_dicionario() -> dict[str, object]:
    """Tudo em tipos simples, para o site em React (`scripts/exportar_conteudo.py`) e a API."""
    return {
        "ancora": ANCORA_NO_SITE,
        "padroes": list(PADROES),
        "grupos": [asdict(g) for g in GRUPOS],
        "indicadores": [asdict(i) for i in INDICADORES_DAS_NOTAS],
        "notas": list(NOTAS),
        "formulas": [asdict(f) for f in FORMULAS],
    }
