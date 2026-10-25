"""Dicionário das features de crédito (B-30): nome, fórmula, fonte, frequência e defasagem de cada uma.

É o lugar só das fórmulas: `src/credito/features.py` escreve no rastro de cada feature a fórmula que
está aqui, e o teste confere que toda feature calculada tem a sua entrada (e o contrário). Mudou uma
fórmula, suba `VERSAO_DAS_FEATURES`.

A defasagem é o tempo entre o fim do período e o dia em que o número fica público; a feature vale a
partir desse dia (`disponivel_em`), nunca a partir do fim do período.
"""

from dataclasses import asdict, dataclass

VERSAO_DAS_FEATURES = "features de crédito 1"  # sobe quando uma fórmula abaixo mudar
REAIS, VEZES, FRACAO, QUANTIDADE, TEXTO = (
    "reais",
    "vezes",
    "fração",
    "quantidade",
    "texto",
)

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
_PGFN = "PGFN: dados abertos da dívida ativa da União (tabela `pgfn_divida` da base)"
_TRIMESTRAL_DA_PGFN = "Trimestral (um retrato por trimestre)"
_DEFASAGEM_DA_PGFN = (
    "Semanas depois do fim do trimestre; vale a partir do último dia do mês em que o arquivo foi "
    "visto pela primeira vez (a PGFN não diz quando publica; histórico desde 14/10/2026)"
)
_DO_PRINCIPAL = (
    "no retrato mais novo que já era público no dia, só como devedor principal (sem corresponsável "
    "nem solidário), somando todos os estabelecimentos da raiz do CNPJ; a empresa fora do retrato "
    "tem zero; empresário individual ou MEI: não observado (ADR 0075)"
)
_IPE = "CVM: documentos do IPE (tabelas `eventos` e `insolvencia` da base)"
_DIARIA = "Diária (cada entrega à CVM)"
_DEFASAGEM_DO_IPE = (
    "Nenhuma além da entrega: vale a partir do dia em que a CVM recebeu o documento"
)
_SCR = "Banco Central: SCR.data, carteira de crédito (tabela `scr_credito` da base)"
_MENSAL_DO_SCR = "Mensal (uma data-base por mês, fim do mês)"
_DEFASAGEM_DO_SCR = (
    "O BC publica cerca de 30 dias depois do fim do mês; a base conta 60 dias (vale a partir da "
    "data-base + 60 dias). O BC regrava meses antigos e a base guarda só a regravação mais nova"
)
_SEM_IPE = "sem nenhum documento do IPE até o dia (a companhia não entregava à CVM): não observado"


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
        EntradaDoDicionario(
            "divida_ativa_da_uniao",
            "Dívida ativa da União (valor)",
            REAIS,
            f"soma do valor consolidado das inscrições, {_DO_PRINCIPAL}",
            _PGFN, _TRIMESTRAL_DA_PGFN, _DEFASAGEM_DA_PGFN,
        ),
        EntradaDoDicionario(
            "divida_ativa_ajuizada",
            "Dívida ativa da União já na Justiça (valor)",
            REAIS,
            f"soma do valor consolidado das inscrições ajuizadas, {_DO_PRINCIPAL}",
            _PGFN, _TRIMESTRAL_DA_PGFN, _DEFASAGEM_DA_PGFN,
        ),
        EntradaDoDicionario(
            "inscricoes_em_divida_ativa",
            "Inscrições em dívida ativa da União",
            QUANTIDADE,
            f"quantidade de inscrições, {_DO_PRINCIPAL}",
            _PGFN, _TRIMESTRAL_DA_PGFN, _DEFASAGEM_DA_PGFN,
        ),
        EntradaDoDicionario(
            "situacao_especial_na_receita",
            "Situação especial no CNPJ",
            TEXTO,
            "rótulo da situação especial (falência, recuperação, liquidação, intervenção) no "
            "retrato mais novo que já era público no dia, da matriz ou, sem ela, de um "
            "estabelecimento da raiz; fora do retrato: \"nenhuma\"; sem retrato guardado no dia: "
            "não observado",
            "Receita Federal: dados abertos do CNPJ (tabela `cnpj_situacao_especial` da base)",
            "Mensal (um retrato por mês)",
            "Por volta do dia 10 a 15 do mês seguinte; vale a partir do fim do mês do retrato ou do "
            "dia em que foi baixado, o que vier depois",
        ),
        EntradaDoDicionario(
            "eventos_de_insolvencia",
            "Documentos de insolvência da própria companhia",
            QUANTIDADE,
            "quantidade de entregas (protocolos) do IPE até o dia com rótulo de recuperação, "
            "pedido de falência, falência ou liquidação da própria companhia (sem a exposição a "
            f"terceiro); {_SEM_IPE}",
            _IPE, _DIARIA, _DEFASAGEM_DO_IPE,
        ),
        EntradaDoDicionario(
            "ultimo_evento_de_insolvencia",
            "Último evento de insolvência da própria companhia",
            TEXTO,
            "rótulo da entrega mais recente do IPE até o dia sobre insolvência da própria "
            f"companhia; sem nenhuma: \"nenhum\"; {_SEM_IPE}",
            _IPE, _DIARIA, _DEFASAGEM_DO_IPE,
        ),
        EntradaDoDicionario(
            "fatos_relevantes_12_meses",
            "Fatos relevantes em 12 meses",
            QUANTIDADE,
            f"quantidade de fatos relevantes entregues nos 365 dias até o dia; {_SEM_IPE}",
            _IPE, _DIARIA, _DEFASAGEM_DO_IPE,
        ),
        EntradaDoDicionario(
            "ratings_12_meses",
            "Documentos de rating em 12 meses",
            QUANTIDADE,
            "quantidade de documentos de rating (tema risco do IPE) entregues nos 365 dias até o "
            f"dia; {_SEM_IPE}",
            _IPE, _DIARIA, _DEFASAGEM_DO_IPE,
        ),
        EntradaDoDicionario(
            "inadimplencia_do_setor_no_scr",
            "Inadimplência do setor da empresa no SCR",
            FRACAO,
            "carteira em inadimplência (atraso acima de 90 dias) ÷ carteira ativa, das pessoas "
            "jurídicas da seção do CNAE da empresa, somadas todas as UF, segmentos, portes e "
            "modalidades, na data-base mais nova que já era pública no dia; seção da empresa "
            "desconhecida, ou nenhuma data-base pública no dia: não observado",
            _SCR, _MENSAL_DO_SCR, _DEFASAGEM_DO_SCR,
        ),
        EntradaDoDicionario(
            "carteira_do_setor_no_scr",
            "Carteira de crédito do setor da empresa no SCR",
            REAIS,
            "carteira ativa das pessoas jurídicas da seção do CNAE da empresa, somadas todas as UF, "
            "segmentos, portes e modalidades, na data-base mais nova que já era pública no dia; "
            "seção da empresa desconhecida, ou nenhuma data-base pública no dia: não observado",
            _SCR, _MENSAL_DO_SCR, _DEFASAGEM_DO_SCR,
        ),
    )
}  # fmt: skip


# as features de cada origem, na ordem em que saem
DAS_DEMONSTRACOES = tuple(k for k, e in DICIONARIO.items() if e.fonte == _CVM)
DA_BASE = tuple(k for k in DICIONARIO if k not in DAS_DEMONSTRACOES)


def dicionario_como_lista() -> list[dict]:
    """O dicionário para a API e para a documentação, na ordem em que as features saem."""
    return [entrada.como_dict() for entrada in DICIONARIO.values()]
