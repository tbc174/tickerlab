"""A rotulagem da fila das 21h por IA (ADR 0072), sem rede.

O que importa aqui são as proteções da ADR: o nome da empresa não chega ao modelo, a resposta só
vale dentro da lista fechada e com o trecho copiado do documento, e o custo é estimado antes.
"""

import json

import pytest

from src import rotulos_ia as ri
from src import topicos

FATO = {
    "id": "020702IPE030920240104553811-12",
    "empresa": "VIVER INCORPORADORA E CONSTRUTORA S.A",
    "setor": "Construção Civil, Mat. Constr. e Decoração",
    "entrega": "2024-09-03",
    "categoria": "Fato Relevante",
    "tipo": "",
    "especie": "",
    "assunto": "Aquisição de controle pela Viver Incorporadora",
}
AVISO = {**FATO, "categoria": "Aviso aos Acionistas", "assunto": "Bônus de Subscrição"}
TEXTO = (
    "A Viver Incorporadora e Construtora S.A. (VIVR3), inscrita no CNPJ 67.571.414/0001-41, "
    "comunica que concluiu a aquisição de 60% da Construtora Alfa por R$ 80 milhões."
)


def _resposta(**campos) -> str:
    base = {"nota": 4, "tema": "fusao", "assunto": "AQUISICAO", "confianca": "alta",
            "trecho": "concluiu a aquisição de 60% da Construtora Alfa"}  # fmt: skip
    return json.dumps({**base, **campos})


# --- anonimizar ---------------------------------------------------------------------------


def test_anonimiza_nome_codigo_e_cnpj():
    texto = ri.anonimizar(TEXTO, [FATO["empresa"]])
    assert "Viver" not in texto and "VIVER" not in texto
    assert "VIVR3" not in texto and "67.571.414/0001-41" not in texto
    assert texto.count(ri.EMPRESA) == 1
    assert ri.CODIGO in texto and ri.CNPJ in texto
    assert "Construtora Alfa" in texto  # outras empresas ficam


def test_anonimiza_sem_acento_e_em_qualquer_caixa():
    nome = "CIA DE SANEAMENTO BÁSICO DO ESTADO DE SÃO PAULO - SABESP"
    texto = "A cia de saneamento basico do estado de sao paulo - sabesp informa."
    assert ri.anonimizar(texto, [nome]) == f"A {ri.EMPRESA} informa."


def test_anonimiza_o_nome_sem_o_sufixo_da_sociedade():
    texto = "A Viver Incorporadora e Construtora informa que a Viver Incorporadora e Construtora S/A"
    assert "Viver" not in ri.anonimizar(texto, [FATO["empresa"]])


def test_codigos_de_negociacao_e_cnpj_sem_mascara():
    texto = "Ações PETR4 e PETR3 e units TAEE11; CNPJ 33000167000101."
    saida = ri.anonimizar(texto, [])
    assert (
        "PETR" not in saida and "TAEE11" not in saida and "33000167000101" not in saida
    )


def test_comeco_do_nome_tambem_e_trocado_mas_palavra_sozinha_nao():
    nome = "BANCO DO ESTADO DO RIO GRANDE DO SUL S.A."
    texto = "O Banco do Estado do Rio Grande informa. Outro banco também."
    assert (
        ri.anonimizar(texto, [nome]) == f"O {ri.EMPRESA} informa. Outro banco também."
    )


def test_nome_vazio_nao_apaga_o_texto():
    assert ri.anonimizar("Texto comum.", ["", "S.A."]) == "Texto comum."


# --- prompt v2 (17/10/2026): o que escapou na identificação da v1 -------------------------


@pytest.mark.parametrize(
    "nome, texto, esperado",
    [
        ("PETRÓLEO BRASILEIRO  S.A.  - PETROBRAS",
         "A Petrobras informa que a Petrobras Distribuidora foi vendida.",
         "A [EMPRESA] informa que a [EMPRESA] Distribuidora foi vendida."),
        ("CPFL ENERGIA S.A.", "A CPFL Paulista concluiu a obra.",
         "A [EMPRESA] Paulista concluiu a obra."),
        ("LIGHT S.A. - EM RECUPERAÇÃO JUDICIAL", "A Light comunica.", "A [EMPRESA] comunica."),
        ("COSAN S.A.", "A Cosan e a Raízen assinaram.", "A [EMPRESA] e a Raízen assinaram."),
        ("KEPLER WEBER S.A.", "A Kepler informa; a Weber também.",
         "A [EMPRESA] informa; a [EMPRESA] também."),
        ("CIA ENERG MINAS GERAIS - CEMIG", "A Cemig e a CEMIG GT.", "A [EMPRESA] e a [EMPRESA] GT."),
    ],
)  # fmt: skip
def test_palavra_que_distingue_a_empresa_sozinha_e_trocada(nome, texto, esperado):
    assert ri.anonimizar(texto, [nome]) == esperado


def test_situacao_no_cadastro_nao_apaga_o_texto():
    """O sufixo de situação é do cadastro de hoje; no texto, "em recuperação judicial" é conteúdo."""
    nome = "AMERICANAS S.A. - EM RECUPERAÇÃO JUDICIAL"
    texto = "A Americanas S.A. - Em Recuperação Judicial informa que está em recuperação judicial."
    assert ri.anonimizar(texto, [nome]) == (
        "A [EMPRESA] - Em Recuperação Judicial informa que está em recuperação judicial."
    )
    nome = "CCX CARVÃO DA COLOMBIA S.A. - EM LIQUIDAÇÃO"
    assert ri.anonimizar("A massa em liquidação.", [nome]) == "A massa em liquidação."


def test_parte_depois_do_traco_com_nome_e_trocada_inteira():
    nome = "B3 S.A. - BRASIL, BOLSA, BALCÃO"
    texto = "A B3 S.A. - Brasil, Bolsa, Balcão divulga o volume da bolsa."
    assert ri.anonimizar(texto, [nome]) == "A [EMPRESA] divulga o volume da bolsa."
    # só a parte de depois do traço, sem a de antes, também sai
    assert (
        ri.anonimizar("A Brasil, Bolsa, Balcão e a bolsa.", [nome])
        == "A [EMPRESA] e a bolsa."
    )


def test_palavra_comum_do_nome_fica():
    """Apagar "pagamento" ou "distribuidora" tiraria o sentido do texto; uma descrição com conector
    ("Instituição de Pagamento") depois do traço também fica."""
    nome = "CIELO S.A. - INSTITUIÇÃO DE PAGAMENTO"
    texto = "A Cielo, instituição de pagamento, aprovou o pagamento de dividendos."
    assert ri.anonimizar(texto, [nome]) == (
        "A [EMPRESA], instituição de pagamento, aprovou o pagamento de dividendos."
    )
    nome = "ENERGISA MINAS RIO - DISTRIBUIDORA DE ENERGIA S/A"
    texto = "A Energisa, distribuidora de energia, e a outra distribuidora."
    assert ri.anonimizar(texto, [nome]) == (
        "A [EMPRESA], distribuidora de energia, e a outra distribuidora."
    )


def test_sigla_curta_so_em_maiusculas_ou_com_inicial_maiuscula():
    """OI, BRF, B3: siglas de 2 ou 3 letras trocadas como estão no cadastro ou com a inicial
    maiúscula ("a Oi"), nunca em minúsculas, para "oi" e "de" não sumirem do texto."""
    assert ri.anonimizar(
        "A OI e a Oi informam: oi, tudo bem.", ["OI S.A. - EM RECUPERAÇÃO JUDICIAL"]
    ) == ("A [EMPRESA] e a [EMPRESA] informam: oi, tudo bem.")
    assert (
        ri.anonimizar("BRF e a Sadia de SP.", ["BRF S.A."])
        == "[EMPRESA] e a Sadia de SP."
    )


def test_sigla_so_no_comeco_de_uma_parte_do_nome():
    """Abreviações do meio do cadastro ("IND. E COM.") estão em qualquer texto em maiúsculas; a sigla
    que é nome vem no começo ("OI S.A."), depois de "BANCO" ou numa parte própria ("- NTS")."""
    nome = "AERIS IND. E COM. DE EQUIP. PARA GER. DE ENG. S.A."
    assert (
        ri.anonimizar("VENDA COM DESCONTO NA IND", [nome])
        == "VENDA COM DESCONTO NA IND"
    )
    assert (
        ri.anonimizar("O ABC e o BANCO.", ["BANCO ABC BRASIL S/A"])
        == "O [EMPRESA] e o BANCO."
    )
    nome = "NOVA TRANSPORTADORA DO SUDESTE S.A. - NTS"
    assert ri.anonimizar("A NTS informa.", [nome]) == "A [EMPRESA] informa."
    assert (
        ri.anonimizar("ITA e ITAÚ.", ["ITAÚ UNIBANCO HOLDING S.A."])
        == "ITA e [EMPRESA]."
    )


def test_marcadores_nao_sao_trocados_de_novo():
    nome = "EMAE - EMPRESA METROP.AGUAS ENERGIA S.A."
    assert (
        ri.anonimizar("A EMAE, empresa de energia.", [nome])
        == "A [EMPRESA], empresa de energia."
    )


@pytest.mark.parametrize(
    "nome, texto, vazam",
    [
        ("COSAN S.A.", "A [EMPRESA] e a Cosan Lubrificantes.", {"cosan"}),
        ("CIELO S.A. - INSTITUIÇÃO DE PAGAMENTO", "Instituição de pagamento.", set()),
        ("KEPLER WEBER S.A.", "Texto limpo.", set()),
    ],
)
def test_palavras_que_vazam(nome, texto, vazam):
    """A conferência sem custo: palavras do nome que distinguem a empresa (as que a auditoria conta
    como acerto) e que ainda estão no documento."""
    assert ri.palavras_que_vazam(texto, nome) == vazam


# --- o pedido ---------------------------------------------------------------------------


def test_pedido_sem_nome_da_empresa():
    pedido = json.dumps(ri.pedido(FATO, TEXTO), ensure_ascii=False)
    assert "Viver" not in pedido and "VIVER" not in pedido and "VIVR3" not in pedido
    assert "Construção Civil" not in pedido and "Setor" not in pedido  # v2: sem o setor


def test_pedido_usa_o_guia_v2_e_o_modelo_combinado():
    pedido = ri.pedido(FATO, TEXTO)
    assert pedido["model"] == "claude-sonnet-5-5"
    sistema = pedido["system"][0]["text"]
    assert "Na dúvida entre duas notas, fique com a menor" in sistema
    assert "Muda a tese" in sistema
    assert pedido["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_assunto_so_em_fato_relevante():
    com = ri.pedido(FATO, TEXTO)["output_config"]["format"]["schema"]
    sem = ri.pedido(AVISO, TEXTO)["output_config"]["format"]["schema"]
    assert com["properties"]["assunto"]["enum"] == list(topicos.TOPICOS)
    assert "assunto" not in sem["properties"]
    assert com["additionalProperties"] is False and sem["additionalProperties"] is False


def test_pedido_corta_o_texto_no_comeco():
    longo = "palavra " * 5_000
    conteudo = ri.pedido(AVISO, longo)["messages"][0]["content"]
    assert len(conteudo) < ri.MAX_CARACTERES_DO_TEXTO + 1_000


def test_pedido_sem_texto_avisa_o_modelo():
    conteudo = ri.pedido(AVISO, "")["messages"][0]["content"]
    assert ri.SEM_TEXTO in conteudo


# --- a resposta ---------------------------------------------------------------------------


def test_resposta_valida_vira_rotulo():
    rotulo = ri.interpretar(_resposta(), FATO, TEXTO)
    assert isinstance(rotulo, ri.RotuloDaIA)
    assert (rotulo.nota, rotulo.tema, rotulo.assunto) == (4, "fusao", "AQUISICAO")
    guardado = rotulo.para_guardar()
    assert guardado["por"] == "ia" and guardado["modelo"] == ri.MODELO
    assert (
        guardado["versao_do_prompt"] == ri.VERSAO_DO_PROMPT
        and guardado["guia"] == ri.GUIA
    )


def test_fora_do_fato_relevante_o_assunto_fica_nulo():
    resposta = json.dumps({"nota": 2, "tema": "governanca", "confianca": "media",
                           "trecho": "Bônus de Subscrição"})  # fmt: skip
    rotulo = ri.interpretar(resposta, AVISO, "")
    assert isinstance(rotulo, ri.RotuloDaIA) and rotulo.assunto is None


@pytest.mark.parametrize(
    "resposta",
    [
        "não é json",
        _resposta(nota=6),
        _resposta(nota="4"),
        _resposta(tema="outro"),
        _resposta(assunto="INVENTADO"),
        _resposta(confianca="total"),
        json.dumps({"nota": 4}),
    ],
)
def test_resposta_invalida_vira_erro(resposta):
    assert isinstance(ri.interpretar(resposta, FATO, TEXTO), ri.ErroDeRotulo)


def test_trecho_tem_de_existir_no_texto():
    erro = ri.interpretar(_resposta(trecho="comprou a empresa toda"), FATO, TEXTO)
    assert isinstance(erro, ri.ErroDeRotulo) and "trecho" in erro.motivo


def test_trecho_pode_vir_do_assunto_e_ignora_espacos():
    resposta = _resposta(trecho="Aquisição  de controle")
    assert isinstance(ri.interpretar(resposta, FATO, ""), ri.RotuloDaIA)


def test_trecho_anonimizado_tambem_vale():
    resposta = _resposta(trecho=f"A {ri.EMPRESA} ({ri.CODIGO})")
    assert isinstance(ri.interpretar(resposta, FATO, TEXTO), ri.RotuloDaIA)


def test_recusa_vira_erro():
    erro = ri.de_mensagem(
        stop_reason="refusal", texto="", evento=FATO, texto_do_documento=TEXTO
    )
    assert isinstance(erro, ri.ErroDeRotulo) and "refusal" in erro.motivo


def test_mensagem_completa_vira_rotulo():
    rotulo = ri.de_mensagem("end_turn", _resposta(), FATO, TEXTO)
    assert isinstance(rotulo, ri.RotuloDaIA)


# --- custo ---------------------------------------------------------------------------


def test_custo_em_lote_e_metade():
    normal = ri.custo_em_dolares(1_000_000, 100_000, lote=False)
    assert normal == pytest.approx(2.0 + 1.0)  # Sonnet 5.5: US$ 2 e US$ 10 por milhão
    assert ri.custo_em_dolares(1_000_000, 100_000, lote=True) == pytest.approx(
        normal / 2
    )


def test_estimativa_da_fila_inteira_fica_perto_do_plano():
    # 3.196 eventos x 4.500 tokens de entrada x 500 de saída, pela Batch: ~US$ 22 (plano de 14/10)
    estimativa = ri.custo_em_dolares(
        3_196 * 4_500, 3_196 * ri.MODELOS[ri.MODELO].saida_estimada_por_evento
    )
    assert 15 < estimativa < 30


# --- identificação ---------------------------------------------------------------------------


def test_identificacao_le_o_mesmo_documento_anonimizado():
    pedido = ri.pedido_de_identificacao(FATO, TEXTO)
    assert pedido["messages"][0]["content"] == ri.documento(FATO, TEXTO)
    assert "Viver" not in json.dumps(pedido, ensure_ascii=False)


@pytest.mark.parametrize(
    ("parada", "resposta", "esperado"),
    [
        ("end_turn", '{"empresa": "Viver"}', "Viver"),
        ("end_turn", '{"empresa": ""}', ri.NAO_SEI),
        ("end_turn", "não é json", ri.NAO_SEI),
        ("refusal", '{"empresa": "Viver"}', ri.NAO_SEI),
    ],
)
def test_palpite_da_identificacao(parada, resposta, esperado):
    assert ri.palpite_da_identificacao(parada, resposta) == esperado


def test_cliente_manda_o_workspace_quando_configurado(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-teste-sem-valor")
    monkeypatch.setenv(ri.VARIAVEL_DO_WORKSPACE, " wrkspc_teste ")
    assert ri.cliente().default_headers["anthropic-workspace-id"] == "wrkspc_teste"
    monkeypatch.delenv(ri.VARIAVEL_DO_WORKSPACE)
    assert "anthropic-workspace-id" not in ri.cliente().default_headers


def test_cnpj_com_letras_tambem_e_mascarado():
    """CNPJ novo (IN RFB 2.229/2024) não pode escapar da máscara e identificar a empresa."""
    texto = ri.anonimizar(
        "Inscrita no CNPJ 12.ABC.345/01DE-35 e no 12ABC34501DE35.", []
    )
    assert "12" not in texto and texto.count(ri.CNPJ) == 2
    # 12 letras e 2 números que não são CNPJ (o DV não confere) ficam como estão
    assert ri.anonimizar("PALAVRAGRAND12", []) == "PALAVRAGRAND12"


# --- segundo modelo às cegas (Emenda 1 da ADR 0072, 17/10/2026) ---------------------------------


def test_preco_do_opus():
    """Opus 5.5: US$ 4 e US$ 20 por milhão (o dobro do Sonnet); pela Batch API, a metade."""
    opus = ri.MODELO_CONFERENTE
    assert ri.custo_em_dolares(
        1_000_000, 100_000, lote=False, modelo=opus
    ) == pytest.approx(6.0)
    assert ri.custo_em_dolares(1_000_000, 100_000, modelo=opus) == pytest.approx(3.0)


def test_modelo_desconhecido_nao_vira_preco_de_outro():
    with pytest.raises(ValueError, match="claude-x"):
        ri.custo_em_dolares(1, 1, modelo="claude-x")
    with pytest.raises(ValueError, match="claude-x"):
        ri.pedido(FATO, TEXTO, modelo="claude-x")


def test_opus_le_exatamente_o_mesmo_pedido_que_o_sonnet():
    """Mesmo guia, mesma versão do prompt e mesmo texto anonimizado: só o modelo muda."""
    sonnet = ri.pedido(FATO, TEXTO)
    opus = ri.pedido(FATO, TEXTO, modelo=ri.MODELO_CONFERENTE)
    assert sonnet["model"] == ri.MODELO and opus["model"] == ri.MODELO_CONFERENTE
    assert {**opus, "model": ri.MODELO} == sonnet
    assert ri.hash_da_entrada(opus) != ri.hash_da_entrada(sonnet)


def test_rotulo_do_opus_guarda_o_modelo():
    rotulo = ri.RotuloDaIA("E1", 3, "fusao", "OUTROS", "trecho", "alta")
    guardado = rotulo.para_guardar(ri.MODELO_CONFERENTE)
    assert guardado["por"] == "ia" and guardado["modelo"] == ri.MODELO_CONFERENTE
    assert guardado["versao_do_prompt"] == ri.VERSAO_DO_PROMPT


def test_sem_conferir_o_trecho_a_lista_fechada_continua_valendo():
    """Só para o desvio registrado da Emenda 1 (17/10/2026): o trecho deixa de ser conferido, o resto
    da resposta continua tendo de respeitar a lista fechada."""
    rotulo = ri.interpretar(
        _resposta(trecho="comprou a empresa toda"), FATO, TEXTO, conferir_trecho=False
    )
    assert (
        isinstance(rotulo, ri.RotuloDaIA) and rotulo.trecho == "comprou a empresa toda"
    )
    erro = ri.interpretar(_resposta(nota=9), FATO, TEXTO, conferir_trecho=False)
    assert isinstance(erro, ri.ErroDeRotulo) and "nota" in erro.motivo


# --- prompt v3 (17/10/2026, ADR 0072 Emenda 2): o conteúdo também é anonimizado -----------

SABESP = "CIA SANEAMENTO BÁSICO ESTADO SÃO PAULO"


def test_versao_do_prompt_v3():
    assert ri.VERSAO_DO_PROMPT == "3" and ri.GUIA == "v2"


@pytest.mark.parametrize(
    "nome, texto, esperado",
    [
        # o cadastro abrevia (CIA, IND, COM) e tira os conectivos; o texto escreve por extenso
        (SABESP, "A Companhia de Saneamento Básico do Estado de São Paulo informa.",
         "A [EMPRESA] informa."),
        ("COMPANHIA PARANAENSE DE ENERGIA - COPEL", "A Cia. Paranaense de Energia e a Copel.",
         "A [EMPRESA] e a [EMPRESA]."),
        ("METALURGICA GERDAU S.A.", "Metalúrgica Gerdau S.A. comunica.", "[EMPRESA] comunica."),
        ("IND E COM DE ALIMENTOS ALFA S.A.", "Indústria e Comércio de Alimentos Alfa S/A informa.",
         "[EMPRESA] informa."),
    ],
)  # fmt: skip
def test_abreviacao_do_cadastro_tambem_e_trocada_por_extenso(nome, texto, esperado):
    assert ri.anonimizar(texto, [nome]) == esperado


def test_apelido_definido_depois_do_nome_e_trocado_no_texto_inteiro():
    texto = (
        'A Companhia de Saneamento Básico do Estado de São Paulo ("Sabesp" ou "Companhia") '
        "informa. A Sabesp pagou; a Companhia segue."
    )
    assert ri.anonimizar(texto, [SABESP]) == (
        'A [EMPRESA] ("[EMPRESA]" ou "Companhia") informa. A [EMPRESA] pagou; a Companhia segue.'
    )
    nome = "FERROVIA NORTE SUL S.A."
    texto = "A Ferrovia Norte Sul S.A. (“FNS”) comunica que a FNS concluiu."
    assert (
        ri.anonimizar(texto, [nome])
        == "A [EMPRESA] (“[EMPRESA]”) comunica que a [EMPRESA] concluiu."
    )


def test_enderecos_eletronicos_somem():
    texto = (
        "Mais em ri.bravaenergia.com, www.ri.alfa.com.br/docs e ri@alfa.com.br. Fim."
    )
    assert ri.anonimizar(texto, []) == (
        f"Mais em {ri.ENDERECO}, {ri.ENDERECO} e {ri.ENDERECO}. Fim."
    )


def test_codigos_de_outras_bolsas_e_numeros_de_registro():
    texto = (
        "Ações (NYSE: GOL; OTCQX: LZRFY; ADR Nível II: ABCD) e NIRE 33.300.294.597, "
        "Código CVM nº 1234, processo 1001409-24.2022.8.26.0260."
    )
    saida = ri.anonimizar(texto, [])
    for pedaco in ("GOL", "LZRFY", "ABCD", "33.300.294.597", "1234", "1001409"):
        assert pedaco not in saida
    assert saida.count(ri.CODIGO) == 3 and saida.count(ri.NUMERO) == 3


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("Caxias do Sul, 31 de julho de 2024.", "[LOCAL], 31 de julho de 2024."),
        ("A fábrica de Dias D'Ávila (BA) e a de São Luís/MA param.",
         "A fábrica de [LOCAL] e a de [LOCAL] param."),
        ("Sede na Avenida Paulista, 1000, 10º andar, CEP 01310-100, São Paulo.",
         "Sede na [LOCAL], 10º andar, CEP [LOCAL], [LOCAL]."),
        ("Com atuação em Minas Gerais e no Estado do Rio de Janeiro.",
         "Com atuação em [LOCAL] e no Estado do [LOCAL]."),
        ("A sigla RI e as Relações com Investidores (RI) ficam.",
         "A sigla RI e as Relações com Investidores (RI) ficam."),
    ],
)  # fmt: skip
def test_lugares_somem_e_a_data_fica(texto, esperado):
    assert ri.anonimizar(texto, []) == esperado


def test_outras_empresas_do_cadastro_viram_outro_marcador():
    outras = ["GOL LINHAS AEREAS INTELIGENTES S.A.", "VALE S.A.", "COSAN S.A.", SABESP]
    texto = (
        "A Gol Linhas Aéreas Inteligentes S.A. e a Cosan assinaram; vale lembrar que a Vale "
        "não participou. A Companhia de Saneamento Básico do Estado de São Paulo também não."
    )
    assert ri.anonimizar(texto, [SABESP], outras) == (
        "A [OUTRA EMPRESA] e a [OUTRA EMPRESA] assinaram; vale lembrar que a Vale "
        "não participou. A [EMPRESA] também não."
    )


def test_outras_empresas_pelo_sufixo_e_pelo_grupo():
    texto = (
        "Comprou a Metalsur Carrocerias S.R.L. e a 3R Petroleum Óleo e Gás S.A., do Grupo "
        "Carrefour Brasil, assessorada pela Moelis & Company LLC."
    )
    assert ri.anonimizar(texto, []) == (
        "Comprou a [OUTRA EMPRESA] e a [OUTRA EMPRESA], do [OUTRA EMPRESA], "
        "assessorada pela [OUTRA EMPRESA]."
    )


def test_caixa_alta_nao_escapa_do_v3():
    """Os documentos da CVM vêm muitas vezes em caixa alta: conectivos e datação também."""
    texto = (
        "BANCO DO BRASIL S.A. e a IND E COM DE ALIMENTOS BOA S.A. assinaram em "
        "DIAS D'ÁVILA, 21 DE JANEIRO DE 2025."
    )
    ri.definir_outras_empresas(["BANCO DO BRASIL S.A."])
    try:
        assert ri.anonimizar(texto, ["IND E COM DE ALIMENTOS BOA S.A."]) == (
            "[OUTRA EMPRESA] e a [EMPRESA] assinaram em [LOCAL], 21 DE JANEIRO DE 2025."
        )
    finally:
        ri.definir_outras_empresas([])


def test_apelido_vale_para_quem_o_documento_definiu():
    """ "GOL" é o apelido da Gol (outra empresa), não da Smiles (a empresa do documento); e
    "Grupo Ad Hoc" não é apelido de ninguém: não engole "um grupo ad hoc de titulares" (em
    maiúsculas vira [OUTRA EMPRESA] pela regra do "Grupo", o que só esconde mais)."""
    texto = (
        "Smiles Fidelidade S.A. (“Smiles”) informa que a Gol Linhas Aéreas Inteligentes S.A. "
        "(“GOL”) negocia com um grupo ad hoc de titulares (“Grupo Ad Hoc”). A GOL e a Smiles "
        "seguem; o Grupo Ad Hoc também."
    )
    ri.definir_outras_empresas(["GOL LINHAS AEREAS INTELIGENTES S.A."])
    try:
        assert ri.anonimizar(texto, ["SMILES FIDELIDADE S.A."]) == (
            "[EMPRESA] (“[EMPRESA]”) informa que a [OUTRA EMPRESA] (“[OUTRA EMPRESA]”) negocia "
            "com um grupo ad hoc de titulares (“[OUTRA EMPRESA]”). A [OUTRA EMPRESA] e a [EMPRESA] "
            "seguem; o [OUTRA EMPRESA] também."
        )
    finally:
        ri.definir_outras_empresas([])


def test_sobrenome_de_pessoa_nao_vira_outra_empresa():
    """A pessoa é mascarada antes das outras empresas: "José Vale Valiati" não vira
    "José [OUTRA EMPRESA] Valiati"."""
    ri.definir_outras_empresas(["VALE S.A."])
    try:
        texto = "Comunicado assinado por José Vale Valiati, Diretor de Relações com Investidores."
        assert ri.anonimizar(texto, []) == (
            "Comunicado assinado por [pessoa], Diretor de Relações com Investidores."
        )
    finally:
        ri.definir_outras_empresas([])


def test_pessoas_junto_do_cargo_viram_marcador():
    texto = "Comunicado assinado por João da Silva Santos, Diretor de Relações com Investidores."
    assert ri.anonimizar(texto, []) == (
        f"Comunicado assinado por {ri.PESSOA}, Diretor de Relações com Investidores."
    )


def test_o_que_a_nota_precisa_fica():
    texto = (
        "Em 31 de julho de 2024, nos termos da Lei 11.101/2005 e da Resolução CVM 80, "
        "a Companhia vendeu 60% por R$ 80 milhões (12,5% da receita), 3 usinas de cobre refinado."
    )
    assert ri.anonimizar(texto, [SABESP]) == texto


def test_documento_usa_o_cadastro_da_fila_como_outras_empresas(monkeypatch):
    monkeypatch.setattr(ri, "OUTRAS_EMPRESAS", ())
    ri.definir_outras_empresas(
        ["GOL LINHAS AEREAS INTELIGENTES S.A.", FATO["empresa"], ""]
    )
    assert (
        "GOL LINHAS AEREAS INTELIGENTES S.A.",
        FATO["empresa"],
    ) == ri.OUTRAS_EMPRESAS
    evento = {**FATO, "assunto": "Parceria com a Gol Linhas Aéreas Inteligentes"}
    lido = ri.documento(
        evento, "A Viver e a Gol Linhas Aéreas Inteligentes S.A. assinaram."
    )
    assert "Gol" not in lido and "Viver" not in lido
    assert lido.count(ri.OUTRA_EMPRESA) == 2 and ri.EMPRESA in lido


def test_prompts_explicam_os_marcadores_novos():
    for sistema in (ri.SISTEMA, ri.SISTEMA_DA_IDENTIFICACAO):
        for marcador in (ri.OUTRA_EMPRESA, ri.LOCAL, ri.PESSOA, ri.ENDERECO, ri.NUMERO):
            assert marcador in sistema


def test_marcadores_do_documento_sao_contados():
    texto = f"A {ri.EMPRESA} e a {ri.OUTRA_EMPRESA} em {ri.LOCAL}; {ri.OUTRA_EMPRESA}."
    assert ri.marcadores(texto) == {ri.EMPRESA: 1, ri.OUTRA_EMPRESA: 2, ri.LOCAL: 1}
