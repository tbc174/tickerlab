"""Assunto (tópico) de cada fato relevante pelo título que a empresa dá no IPE (leitor v2, ADR 0069).

Os títulos abaixo são reais (IPE da CVM, dados abertos). As armadilhas são as falhas do leitor v1, que
contava palavras soltas.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src import topicos

CASOS = [
    # operações (os códigos são os do dicionário da base de M&A, ADR 0063)
    ("Ecorodovias conclui aquisição da MGO", "AQUISICAO"),
    ("Aquisição de Ativos - Buscopan e Buscofem", "AQUISICAO"),
    ("Acionista Controlador adquire Fundo de Investimento", "AQUISICAO"),
    ("Acordo vinculante para venda da The Body Shop", "VENDA_ATIVO"),
    (
        "Petrobras assina contrato para venda de campos em produção na Bacia Potiguar",
        "VENDA_ATIVO",
    ),
    ("Alienação Relevante de Ativos Industriais", "VENDA_ATIVO"),
    ("Cessão de Carteira - Segmento Empresarial", "VENDA_ATIVO"),
    ("Venda de UPI no âmbito da recuperação judicial", "VENDA_ATIVO"),
    ("Conclusão da Venda da Moy Park", "VENDA_ATIVO"),
    ("Incorporação de ações", "FUSAO_INCORPORACAO"),
    ("Incorporação Videomar", "FUSAO_INCORPORACAO"),
    ("Aprovação ANTAQ fusão Rumo e ALL", "FUSAO_INCORPORACAO"),
    ("Cisão parcial de sua controlada MOVIDA LOCAÇÃO DE VEÍCULOS S.A.", "CISAO"),
    ("Mudança de Controle da Companhia", "ALIEN_CONTROLE"),
    ("Assinatura de contrato de joint venture com a Mitsui", "JV"),
    ("Oferta pública de aquisição de ações para aumento de participação", "OPA"),
    ("Cancelamento de Registro de Companhia Aberta", "FECHAMENTO_CAPITAL"),
    ("OPA para cancelamento de registro", "FECHAMENTO_CAPITAL"),
    ("Reorganização societária do grupo", "REORG"),
    # outros assuntos
    ("JCP 2T23", "DIVIDENDOS"),
    ("Declaração de dividendos intercalares", "DIVIDENDOS"),
    ("Encerramento do Programa de Recompra de Ações", "RECOMPRA"),
    ("Aquisição de ações de própria emissão", "RECOMPRA"),
    ("5ª emissão de debêntures simples", "DIVIDA"),
    ("Petrobras sobre precificação de títulos globais", "DIVIDA"),
    ("Acordo com Bondholders", "DIVIDA"),
    ("Negociação de dívidas do Sistema Eletrobras", "DIVIDA"),
    ("Aumento de capital social", "OFERTA_ACOES"),
    ("Oferta pública de distribuição primária de ações", "OFERTA_ACOES"),
    ("Deferimento Petição de Recuperação Judicial", "RJ_INSOLVENCIA"),
    ("Suspensão de Decisão que Decretou Falência de Subsidiária", "RJ_INSOLVENCIA"),
    (
        "Enauta anuncia Carlos Mastrangelo como novo Diretor de Produção",
        "ADMINISTRACAO",
    ),
    ("Formação do Conselho Consultivo e alteração de CEO", "ADMINISTRACAO"),
    ("Divulgação de Resultados 2T25", "RESULTADOS_PROJECOES"),
    ("Revisão do guidance para o ano de 2025", "RESULTADOS_PROJECOES"),
    (
        "Adiamento de Divulgação das Demonstrações Financeiras 2T25",
        "RESULTADOS_PROJECOES",
    ),
    ("Relatório de Produção e Vendas 3T24", "RESULTADOS_PROJECOES"),
    ("Decisão Tribunal do CADE", "PROCESSOS"),
    (
        "Decisão Colegiado CVM - não refazimento de demonstrações financeiras",
        "PROCESSOS",
    ),
    # achados da medição provisória (amostra de M&A e da rotulagem, 14/10)
    (
        "Cisão Total da Parati, com incorporação do acervo cindido pela RME e pela Lepsa",
        "CISAO",
    ),
    ("Incorporação e Deslistagem da Companhia", "FUSAO_INCORPORACAO"),
    (
        "Deliberações do CDPED sobre a modelagem de desestatização da Companhia",
        "ALIEN_CONTROLE",
    ),
    ("Distribuição de dvidendos", "DIVIDENDOS"),
    ("Possível Oferta Primária de Ações", "OFERTA_ACOES"),
    ("Desdobramento de ações", "OFERTA_ACOES"),
    ("Suspensão da Assembleia Geral dos Credores", "RJ_INSOLVENCIA"),
    ("Fato Relevante Tutela Cautelar", "PROCESSOS"),
    ("Sale &amp Leaseback 3ª Tranche", "VENDA_ATIVO"),
    # títulos genéricos ficam para o texto ou o modelo
    ("Fato Relevante", "OUTROS"),
    ("Comunicado", "OUTROS"),
    ("Celebração ou Extinção de Contrato", "OUTROS"),
    ("", "OUTROS"),
]


@pytest.mark.parametrize(("titulo", "esperado"), CASOS)
def test_topico_pelo_titulo(titulo, esperado):
    assert topicos.topico_do_titulo(titulo).principal == esperado


def test_armadilhas_do_leitor_v1():
    # "Incorporadora" no nome da empresa não é incorporação
    assert (
        topicos.topico_do_titulo("VIVER INCORPORADORA E CONSTRUTORA S.A").principal
        == "OUTROS"
    )
    # recompra não é aquisição, mesmo com "aquisição" no título
    assert topicos.topico_do_titulo(
        "Programa de aquisição de ações de emissão própria"
    ).principal == ("RECOMPRA")
    # notícia negada não é operação
    assert topicos.topico_do_titulo(
        "Esclarecimento: não há negociação para aquisição"
    ).principal == ("OUTROS")
    # alienação fiduciária é garantia de dívida, não venda
    assert (
        topicos.topico_do_titulo("Alienação fiduciária de ações em garantia").principal
        == "DIVIDA"
    )


def test_titulo_com_varios_assuntos_guarda_os_secundarios():
    leitura = topicos.topico_do_titulo(
        "Celebração, Alteração ou Rescisão de Acordo de Acionistas||Mudança de Controle da "
        "Companhia||Renúncia de Diretor Financeiro"
    )
    assert leitura.principal == "ALIEN_CONTROLE"
    assert leitura.secundarios == ("ADMINISTRACAO",)
    assert leitura.trecho == "Mudança de Controle da Companhia"


def test_resultado_diz_como_foi_decidido():
    leitura = topicos.topico_do_titulo("Ecorodovias conclui aquisição da MGO")
    assert leitura.metodo == "regra_titulo"
    assert leitura.versao == topicos.VERSAO
    assert leitura.trecho == "Ecorodovias conclui aquisição da MGO"
    assert topicos.topico_do_titulo("Fato Relevante").trecho == ""


def test_taxonomia():
    assert len(topicos.TOPICOS) == 18
    assert "OUTROS" in topicos.TOPICOS
    # os de operação são os candidatos da base de M&A
    assert {
        "AQUISICAO", "VENDA_ATIVO", "FUSAO_INCORPORACAO", "CISAO", "JV", "ALIEN_CONTROLE",
        "OPA", "FECHAMENTO_CAPITAL", "REORG",
    } == topicos.OPERACOES  # fmt: skip
    assert set(topicos.TOPICOS) > topicos.OPERACOES
    for codigo, nome in topicos.TOPICOS.items():
        assert codigo.isupper() and nome[0].isupper(), codigo
    assert topicos.TOPICOS["OPA"] == "OPA"
    assert topicos.TOPICOS["AQUISICAO"] == "Aquisição"


@given(st.text())
def test_qualquer_titulo_da_um_topico_da_lista(titulo):
    leitura = topicos.topico_do_titulo(titulo)
    assert leitura.principal in topicos.TOPICOS
    assert set(leitura.secundarios) <= set(topicos.TOPICOS)
    assert leitura.principal not in leitura.secundarios
    assert len(leitura.secundarios) <= 2
    assert leitura.trecho in titulo


# --- camada 2: o texto do fato relevante (quando o PDF foi lido) ---------------------------------

FATO_DE_AQUISICAO = """
COMPANHIA EXEMPLO S.A.
CNPJ nº 00.000.000/0001-00
FATO RELEVANTE
A Companhia Exemplo S.A., em atendimento ao disposto na Resolução CVM nº 44, comunica aos seus
acionistas e ao mercado em geral o que segue. O Conselho de Administração aprovou hoje a aquisição
de 100% da Fábrica Modelo Ltda. por R$ 1,2 bilhão, pagos em dinheiro na data do fechamento. A
operação será paga com caixa próprio e com a emissão de debêntures no valor de R$ 500 milhões. A
Companhia manterá o mercado informado sobre o andamento da operação, nos termos da regulamentação.
São Paulo, 12 de outubro de 2026.
Maria Exemplo
Diretora Financeira e de Relações com Investidores
"""


def test_topico_pelo_texto_com_a_frase_que_decidiu():
    leitura = topicos.topico_do_texto(FATO_DE_AQUISICAO)
    assert (
        leitura.principal == "AQUISICAO"
    )  # não "Mudança na administração" (o Conselho aprovou)
    assert leitura.secundarios == ("DIVIDA",)  # as debêntures da frase seguinte
    assert leitura.trecho.startswith(
        "O Conselho de Administração aprovou hoje a aquisição"
    )
    assert leitura.trecho in FATO_DE_AQUISICAO.replace("\n", " ")
    assert leitura.metodo == "regra_texto"


def test_texto_ignora_o_cabecalho_e_a_assinatura():
    # "Diretora Financeira" na assinatura não é mudança na administração
    so_juridiques = (
        "FATO RELEVANTE\nA Companhia, em atendimento ao disposto na Resolução CVM nº 44, comunica aos "
        "seus acionistas e ao mercado em geral que recebeu correspondência de um acionista.\n"
        "São Paulo, 1 de outubro de 2026.\nJoão Exemplo\nDiretor de Relações com Investidores\n"
    )
    assert topicos.topico_do_texto(so_juridiques).principal == "OUTROS"


def test_o_assunto_esta_no_comeco_do_documento():
    """O que vem no fim (as ressalvas e o histórico) não decide o assunto."""
    frases = [
        "A Companhia comunica que o Conselho aprovou o pagamento de dividendos de R$ 1,00."
    ]
    frases += [
        "Esta frase de enchimento tem palavras suficientes para contar aqui."
    ] * 12
    frases += [
        "No passado, a Companhia concluiu a aquisição da Empresa Antiga em 2010."
    ]
    leitura = topicos.topico_do_texto(" ".join(frases))
    assert leitura.principal == "DIVIDENDOS"
    assert "AQUISICAO" not in leitura.secundarios


def test_documento_junta_titulo_e_texto():
    # título genérico: decide o texto
    leitura = topicos.topico_do_documento("Fato Relevante", FATO_DE_AQUISICAO)
    assert (leitura.principal, leitura.metodo) == ("AQUISICAO", "regra_texto")
    # título claro: vale o título (o texto não muda o assunto)
    leitura = topicos.topico_do_documento("JCP 2T23", FATO_DE_AQUISICAO)
    assert (leitura.principal, leitura.metodo) == ("DIVIDENDOS", "regra_titulo")
    # sem texto (PDF escaneado): fica o título
    assert topicos.topico_do_documento("Fato Relevante", "").principal == "OUTROS"


@given(st.text())
def test_qualquer_texto_da_um_topico_da_lista(texto):
    leitura = topicos.topico_do_texto(texto)
    assert leitura.principal in topicos.TOPICOS
    assert leitura.principal not in leitura.secundarios
    assert len(leitura.secundarios) <= 2


# --- achados da primeira rodada em produção (14/10/2026) ---------------------------------------


def test_sigla_do_estado_do_rio_nao_e_recuperacao_judicial():
    """O endereço no cabeçalho ("Rio de Janeiro – RJ") virava recuperação judicial."""
    texto = (
        "AXIA Energia S.A. CNPJ 00.001.180/0001-26 Avenida Graça Aranha, 26, Centro, Rio de "
        "Janeiro, RJ. A Companhia comunica a quinta operação de conversão das ações preferenciais "
        "classe C em ações ordinárias, conforme aprovado pelos acionistas."
    )
    assert topicos.topico_do_texto(texto).principal != "RJ_INSOLVENCIA"
    assert topicos.topico_do_titulo("Unidade RJ").principal == "OUTROS"
    assert (
        topicos.topico_do_titulo("Pedido de recuperação judicial").principal
        == "RJ_INSOLVENCIA"
    )


def test_frase_de_encerramento_nao_decide_o_assunto():
    """ "A Companhia manterá o mercado informado" vem em quase todo fato e não diz o assunto."""
    texto = (
        "A Companhia recebeu de acionistas um pedido de convocação de assembleia geral "
        "extraordinária para deliberar sobre a eleição de membros do conselho. A Companhia "
        "manterá seus acionistas e o mercado em geral devidamente informados sobre o aumento de "
        "capital e demais assuntos."
    )
    leitura = topicos.topico_do_texto(texto)
    assert (
        leitura.principal == "ADMINISTRACAO"
    )  # a eleição de conselheiros, não o aumento de capital
    assert "OFERTA_ACOES" not in leitura.secundarios


def test_mudou_a_regra_mudou_a_versao():
    assert topicos.VERSAO == "2"
