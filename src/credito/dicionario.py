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


# --- os sinais da ficha de crédito (linha 754: `src/credito/sinais.py`) ---------------------------
_RETRATO_DA_PGFN = (
    "no retrato mais novo que já era público no dia, só como devedor principal, somando todos os "
    "estabelecimentos da raiz do CNPJ; fora do retrato: zero; empresário individual ou MEI: não "
    "observado (ADR 0075)"
)
_VIGENTE = (
    "na versão mais nova de cada registro vista até o dia, que ainda constava da lista (`consta`), "
    "da raiz do CNPJ; o registro de pessoa natural não entra (ADR 0075); nenhum: zero"
)
_MENSAL_DO_GOVERNO = "Mensal (a base olha a lista e grava o que mudou)"
_DEFASAGEM_DO_MES = (
    "Vale a partir do último dia do mês em que a base viu a mudança pela primeira vez (a fonte não "
    "diz quando publica)"
)
_DIARIA_DO_GOVERNO = "Diária (a base olha a lista e grava o que mudou)"
_DEFASAGEM_DO_DIA = "Vale a partir do dia em que a base viu a linha pela primeira vez"
_12_MESES_DE_PAGAMENTO = (
    "nos 365 dias até o dia, pela data do pagamento, com a raiz do CNPJ como credora do Estado; a "
    "versão mais nova de cada pagamento vista até o dia"
)
_FIDC = "CVM: informe mensal de FIDC, quadro I (tabela `fidc_informe` da base)"
_MENSAL_DO_FIDC = "Mensal (um informe por fundo e competência)"
_DEFASAGEM_DO_FIDC = (
    "O fundo entrega em até 15 dias; a base conta competência + 45 dias, ou o dia em que o informe "
    "apareceu na CVM, se for depois"
)
_COMO_CEDENTE = (
    "nos fundos que listam o CNPJ entre os maiores cedentes (quadro I) na competência mais nova em "
    "que ele aparece, entre os informes públicos no dia e dos 12 meses até o dia"
)
_RATINGS = "CVM: ratings lidos dos documentos do IPE (tabela `ratings` da base)"
_DO_RATING = (
    "do documento mais novo entregue à CVM até o dia com rating extraído (documento sem rating "
    "legível não entra); nenhum: não observado"
)
_PE = "Sefaz de Pernambuco: ordem cronológica de pagamentos (tabela `sefaz_pe_ordem_cronologica` da base)"
_ES = "Governo do Espírito Santo: ordem cronológica de pagamentos (tabela `es_ordem_cronologica` da base)"
_SEFA_PR = "Secretaria da Fazenda do Paraná: lista de devedores (tabela `sefa_pr_divida_ativa` da base)"


def _da_ordem_cronologica(uf: str, fonte: str) -> tuple[EntradaDoDicionario, ...]:
    estado = f"do Estado ({uf.upper()})"
    return (
        EntradaDoDicionario(
            f"pagamentos_recebidos_de_{uf}_12_meses",
            f"Pagamentos recebidos {estado} em 12 meses",
            QUANTIDADE, f"quantidade de pagamentos, {_12_MESES_DE_PAGAMENTO}; nenhum: zero",
            fonte, _DIARIA_DO_GOVERNO, _DEFASAGEM_DO_DIA,
        ),
        EntradaDoDicionario(
            f"valor_recebido_de_{uf}_12_meses",
            f"Valor recebido {estado} em 12 meses",
            REAIS, f"soma do valor pago, {_12_MESES_DE_PAGAMENTO}; nenhum: zero",
            fonte, _DIARIA_DO_GOVERNO, _DEFASAGEM_DO_DIA,
        ),
        EntradaDoDicionario(
            f"mediana_de_dias_ate_receber_de_{uf}",
            f"Dias até o Estado ({uf.upper()}) pagar, depois da liquidação (mediana)",
            QUANTIDADE,
            f"mediana dos dias entre a liquidação e o pagamento, {_12_MESES_DE_PAGAMENTO}; nenhum "
            "pagamento: não observado",
            fonte, _DIARIA_DO_GOVERNO, _DEFASAGEM_DO_DIA,
        ),
    )  # fmt: skip


def _da_pgfn(chave: str, nome: str, situacao: str) -> EntradaDoDicionario:
    return EntradaDoDicionario(
        chave, nome, REAIS,
        f"soma do valor consolidado das inscrições na situação \"{situacao}\", {_RETRATO_DA_PGFN}",
        _PGFN, _TRIMESTRAL_DA_PGFN, _DEFASAGEM_DA_PGFN,
    )  # fmt: skip


_DA_FICHA = (
    _da_pgfn("divida_ativa_em_cobranca", "Dívida ativa da União em cobrança (valor)", "Em cobrança"),
    _da_pgfn(
        "divida_ativa_com_beneficio_fiscal",
        "Dívida ativa da União com benefício fiscal: parcelamento ou transação (valor)",
        "Benefício Fiscal",
    ),
    _da_pgfn("divida_ativa_em_garantia", "Dívida ativa da União garantida (valor)", "Garantia"),
    _da_pgfn(
        "divida_ativa_suspensa_pela_justica",
        "Dívida ativa da União suspensa por decisão judicial (valor)",
        "Suspenso por decisão judicial",
    ),
    _da_pgfn("divida_ativa_em_negociacao", "Dívida ativa da União em negociação (valor)", "Em negociação"),
    EntradaDoDicionario(
        "situacao_cadastral_na_receita",
        "Situação cadastral do CNPJ",
        TEXTO,
        "situação cadastral (Ativa, Suspensa, Inapta, Baixada, Nula) no retrato mais novo, público no "
        "dia, em que a raiz do CNPJ aparece, da matriz ou, sem ela, de um estabelecimento da raiz; a "
        "raiz em nenhum retrato público no dia: não observado",
        "Receita Federal: dados abertos do CNPJ (tabela `cnpj_situacao_cadastral` da base)",
        "Mensal (um retrato por mês)",
        "Vale a partir do fim do mês do retrato ou do dia em que foi baixado, o que vier depois",
    ),
    EntradaDoDicionario(
        "sancoes_vigentes_na_cgu",
        "Sanções vigentes na CGU (CEIS, CNEP, CEPIM, acordos de leniência)",
        QUANTIDADE,
        f"quantidade de registros, {_VIGENTE}",
        "CGU: Portal da Transparência (tabela `sancoes_cgu` da base)",
        _MENSAL_DO_GOVERNO, _DEFASAGEM_DO_MES,
    ),
    EntradaDoDicionario(
        "registros_na_lista_suja",
        "Registros no cadastro de empregadores do trabalho análogo ao de escravo",
        QUANTIDADE,
        f"quantidade de registros, {_VIGENTE}",
        "Ministério do Trabalho: cadastro de empregadores (tabela `mte_lista_suja` da base)",
        _MENSAL_DO_GOVERNO, _DEFASAGEM_DO_MES,
    ),
    EntradaDoDicionario(
        "embargos_vigentes_no_ibama",
        "Áreas embargadas pelo IBAMA, ainda sem desembargo",
        QUANTIDADE,
        f"quantidade de termos de embargo não cancelados nem desembargados, {_VIGENTE}",
        "IBAMA: termos de embargo (tabela `ibama_embargos` da base)",
        _MENSAL_DO_GOVERNO, _DEFASAGEM_DO_MES,
    ),
    EntradaDoDicionario(
        "divida_ativa_no_parana",
        "Dívida ativa no Paraná (valor)",
        REAIS,
        f"soma do valor total dos débitos, {_VIGENTE}",
        _SEFA_PR, _DIARIA_DO_GOVERNO, _DEFASAGEM_DO_DIA,
    ),
    EntradaDoDicionario(
        "divida_ativa_no_parana_sem_parcelamento_nem_suspensao",
        "Dívida ativa no Paraná sem parcelamento ativo, suspensão nem garantia (valor)",
        REAIS,
        "soma do valor total dos débitos sem parcelamento ativo, sem suspensão e sem garantia, "
        f"{_VIGENTE}",
        _SEFA_PR, _DIARIA_DO_GOVERNO, _DEFASAGEM_DO_DIA,
    ),
    EntradaDoDicionario(
        "divida_ativa_em_minas_gerais",
        "Dívida ativa em Minas Gerais (saldo)",
        REAIS,
        f"soma do saldo das certidões de dívida ativa, {_VIGENTE}",
        "Secretaria de Fazenda de Minas Gerais: dívida ativa (tabela `sef_mg_divida_ativa` da base)",
        _DIARIA_DO_GOVERNO, _DEFASAGEM_DO_DIA,
    ),
    EntradaDoDicionario(
        "parcelamentos_em_minas_gerais",
        "Débitos parcelados em Minas Gerais (valor)",
        REAIS,
        f"soma do débito dos parcelamentos, {_VIGENTE}",
        "Secretaria de Fazenda de Minas Gerais: parcelamentos (tabela `sef_mg_parcelamentos` da base)",
        _DIARIA_DO_GOVERNO, _DEFASAGEM_DO_DIA,
    ),
    *_da_ordem_cronologica("pe", _PE),
    *_da_ordem_cronologica("es", _ES),
    EntradaDoDicionario(
        "fundos_em_que_cede",
        "FIDCs em que a empresa está entre os maiores cedentes",
        QUANTIDADE,
        f"quantidade de fundos, {_COMO_CEDENTE}; nenhum: zero",
        _FIDC, _MENSAL_DO_FIDC, _DEFASAGEM_DO_FIDC,
    ),
    EntradaDoDicionario(
        "maior_participacao_como_cedente",
        "Maior participação da empresa na carteira de um FIDC",
        FRACAO,
        f"o maior percentual informado para o CNPJ ÷ 100, {_COMO_CEDENTE}; nenhum fundo: não observado",
        _FIDC, _MENSAL_DO_FIDC, _DEFASAGEM_DO_FIDC,
    ),
    EntradaDoDicionario(
        "carteira_dos_fundos_em_que_cede",
        "Carteira dos FIDCs em que a empresa cede (valor)",
        REAIS,
        f"soma da carteira de direitos creditórios (`TAB_I2_VL_CARTEIRA`) dos fundos, {_COMO_CEDENTE}; "
        "nenhum fundo: zero",
        _FIDC, _MENSAL_DO_FIDC, _DEFASAGEM_DO_FIDC,
    ),
    EntradaDoDicionario(
        "maior_inadimplencia_dos_fundos_em_que_cede",
        "Maior inadimplência entre os FIDCs em que a empresa cede",
        FRACAO,
        "o maior quociente direitos creditórios inadimplentes (`TAB_I2A3_VL_CRED_INAD`) ÷ carteira "
        f"(`TAB_I2_VL_CARTEIRA`) entre os fundos, {_COMO_CEDENTE}; a carteira do fundo é de todos os "
        "cedentes, não só da empresa; nenhum fundo com carteira: não observado",
        _FIDC, _MENSAL_DO_FIDC, _DEFASAGEM_DO_FIDC,
    ),
    EntradaDoDicionario(
        "rating_mais_recente",
        "Rating de crédito mais recente na CVM",
        TEXTO,
        f"\"<rating> (<agência>, escala <escala>)\" {_DO_RATING}",
        _RATINGS, _DIARIA, _DEFASAGEM_DO_IPE,
    ),
    EntradaDoDicionario(
        "perspectiva_do_rating",
        "Perspectiva do rating mais recente",
        TEXTO,
        f"a perspectiva (estável, positiva, negativa, em observação) {_DO_RATING}; documento sem "
        "perspectiva: \"não informada\"",
        _RATINGS, _DIARIA, _DEFASAGEM_DO_IPE,
    ),
    EntradaDoDicionario(
        "dias_desde_o_rating",
        "Dias desde o rating mais recente",
        QUANTIDADE,
        f"dias entre a entrega do documento e o dia da análise, {_DO_RATING}",
        _RATINGS, _DIARIA, _DEFASAGEM_DO_IPE,
    ),
    EntradaDoDicionario(
        "insolvencia_24_meses",
        "Documentos de insolvência da própria companhia em 24 meses",
        QUANTIDADE,
        "quantidade de entregas (protocolos) do IPE nos 730 dias até o dia com rótulo de recuperação, "
        f"pedido de falência, falência ou liquidação da própria companhia; {_SEM_IPE}",
        _IPE, _DIARIA, _DEFASAGEM_DO_IPE,
    ),
    EntradaDoDicionario(
        "ultima_insolvencia_24_meses",
        "Último evento de insolvência da própria companhia em 24 meses",
        TEXTO,
        "\"<rótulo> em <dia>\" da entrega mais recente do IPE nos 730 dias até o dia sobre "
        f"insolvência da própria companhia; sem nenhuma: \"nenhum\"; {_SEM_IPE}",
        _IPE, _DIARIA, _DEFASAGEM_DO_IPE,
    ),
    EntradaDoDicionario(
        "atrasos_de_entrega_na_cvm",
        "Atrasos na entrega das demonstrações à CVM (últimas 8)",
        QUANTIDADE,
        "quantidade de DFP e ITR entregues depois do prazo entre as 8 mais novas já entregues até o "
        "dia (a que ainda não foi entregue no dia não aparece); nenhuma entregue: não observado",
        "CVM: prazos e primeira entrega das DFP e ITR (tabela `rotulos_atraso` da base)",
        "Trimestral (cada ITR e DFP)",
        "Vale a partir do dia da primeira entrega do documento",
    ),
)  # fmt: skip

DICIONARIO.update({entrada.chave: entrada for entrada in _DA_FICHA})

# as features de cada origem, na ordem em que saem
DAS_DEMONSTRACOES = tuple(k for k, e in DICIONARIO.items() if e.fonte == _CVM)
DA_FICHA = tuple(entrada.chave for entrada in _DA_FICHA)
DA_BASE = tuple(
    k for k in DICIONARIO if k not in DAS_DEMONSTRACOES and k not in DA_FICHA
)


def dicionario_como_lista() -> list[dict]:
    """O dicionário para a API e para a documentação, na ordem em que as features saem."""
    return [entrada.como_dict() for entrada in DICIONARIO.values()]
