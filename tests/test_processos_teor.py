"""O teor da comunicação do DJEN lido por regra (plano de 03/11/2026, PR 2, grupo 4): tipo de ato,
resultado e o maior valor em reais. Os textos são inventados no formato dos tribunais."""

import pytest

from base import processos_teor as pt

SENTENCA_PARCIAL = (
    "<p>Processo 1000001-00.2025.8.26.0100 - Procedimento Comum Cível - FULANO DE TAL - "
    "COMPANHIA EXEMPLO S.A. - SENTENÇA Ante o exposto, JULGO PARCIALMENTE PROCEDENTES os "
    "pedidos formulados nesta ação para condenar a ré ao pagamento de R$ 5.000,00 (cinco mil "
    "reais). Por consequência, EXTINGO o processo com resolução do mérito, nos termos do art. "
    "487, I, do CPC. Valor da causa: R$ 12.345,67. - ADV: BELTRANO (OAB SP000001)</p>"
)


@pytest.mark.parametrize(
    ("tipo_documento", "esperado"),
    [
        ("Sentença", "sentenca"),
        ("Acórdão", "acordao"),
        ("EMENTA / ACORDÃO", "acordao"),
        ("Intimação de acórdão", "acordao"),
        ("Decisão", "decisao"),
        ("Despacho", "despacho"),
        ("Despacho_Intimação_Intimação (Outros)", "despacho"),
        ("DESPACHO/DECISÃO", "despacho_ou_decisao"),
        ("Ato ordinatório", "ato_ordinatorio"),
        ("Ata de sessão de julgamento", "ata_de_julgamento"),
        ("Ata de sesso", "ata_de_julgamento"),
        ("PAUTA DE JULGAMENTOS", "pauta"),
        ("Próximos Julgados", "pauta"),
        ("ATA DE DISTRIBUIÇÃO", "distribuicao"),
        ("Edital", "edital"),
        ("Certidão", "certidao"),
    ],
)
def test_tipo_de_ato_pelo_tipo_do_documento(tipo_documento, esperado):
    assert pt.tipo_de_ato(tipo_documento, "texto qualquer") == esperado


def test_tipo_generico_vira_sentenca_so_com_dispositivo_de_sentenca():
    assert pt.tipo_de_ato("Intimação", SENTENCA_PARCIAL) == "sentenca"
    assert pt.tipo_de_ato("Outros", "Manifeste-se a parte autora em 15 dias.") is None
    # recurso julgado em texto genérico pode ser acórdão ou decisão do relator: sem tipo
    assert (
        pt.tipo_de_ato("Intimação", "Ante o exposto, NEGO PROVIMENTO ao recurso.")
        is None
    )


@pytest.mark.parametrize(
    ("texto", "resultado", "trecho"),
    [
        (
            SENTENCA_PARCIAL,
            "parcialmente_procedente",
            "JULGO PARCIALMENTE PROCEDENTES",
        ),
        (
            "Posto isso, JULGO IMPROCEDENTE o pedido formulado por FULANO.",
            "improcedente",
            "JULGO IMPROCEDENTE",
        ),
        (
            "Isso posto, JULGO PROCEDENTE o pedido e extingo o feito com resolução do mérito.",
            "procedente",
            "JULGO PROCEDENTE",
        ),
        (
            "JULGO PROCEDENTE EM PARTE a ação.",
            "parcialmente_procedente",
            "JULGO PROCEDENTE EM PARTE",
        ),
        (
            "HOMOLOGO, por sentença, o ACORDO celebrado entre as partes e julgo extinto o processo.",
            "acordo_homologado",
            "HOMOLOGO ... ACORDO",
        ),
        (
            "Diante do adimplemento do débito, EXTINGO O PROCESSO nos termos do art. 924, II, do CPC.",
            "extinto",
            "EXTINGO O PROCESSO",
        ),
        (
            "Homologo a desistência e JULGO EXTINTO O FEITO sem resolução do mérito.",
            "extinto",
            "JULGO EXTINTO O FEITO",
        ),
        (
            "A Turma decidiu, por unanimidade, NEGAR PROVIMENTO ao recurso.",
            "recurso_nao_provido",
            "NEGAR PROVIMENTO",
        ),
        (
            "Por maioria, DERAM PARCIAL PROVIMENTO ao apelo.",
            "recurso_parcialmente_provido",
            "DERAM PARCIAL PROVIMENTO",
        ),
        (
            "Ante o exposto, DOU PROVIMENTO ao agravo.",
            "recurso_provido",
            "DOU PROVIMENTO",
        ),
        (
            "DAR PROVIMENTO PARCIAL ao recurso.",
            "recurso_parcialmente_provido",
            "DAR PROVIMENTO PARCIAL",
        ),
    ],
)
def test_resultado_pelo_dispositivo(texto, resultado, trecho):
    assert pt.resultado(pt.texto_limpo(texto)) == (resultado, trecho)


@pytest.mark.parametrize(
    "texto",
    [
        "Manifeste-se a parte autora sobre a contestação.",
        # dois dispositivos que se contradizem: sem resultado
        "JULGO IMPROCEDENTE a reconvenção. JULGO PROCEDENTE a ação principal.",
        # a sentença de antes, contada no passado, não é o resultado desta comunicação
        "A sentença julgou improcedente o pedido; o recurso foi recebido. Às contrarrazões.",
        "Não comparecendo as partes, o processo será extinto, na forma do art. 51.",
        "Providencie o interessado o preenchimento, conforme o Provimento CGJ nº 05/2019.",
        "Homologo os quesitos apresentados pelas partes.",
        "Rejeito os embargos de declaração.",
        # a ementa é igual à do precedente citado: não diz o que esta comunicação decidiu
        "RECURSO NÃO PROVIDO. Acórdão vistos e relatados.",
        'Conforme julgado a seguir: "RECURSO ESPECIAL. MORA. RECURSO PROVIDO." Intime-se.',
        # o provimento narrado é o de antes
        "Ao negar provimento ao recurso, a decisão fixou honorários de 20%. Acolho os embargos.",
    ],
)
def test_sem_resultado_quando_nao_ha_dispositivo_claro(texto):
    assert pt.resultado(pt.texto_limpo(texto)) is None


def test_trecho_nao_leva_texto_livre_do_meio():
    """O trecho guardado é só a fórmula do dispositivo: entre o verbo e a palavra-chave pode estar o
    nome de uma pessoa, e ele não entra."""
    texto = pt.texto_limpo("JULGO o pedido de FULANO DE TAL IMPROCEDENTE.")
    assert pt.resultado(texto) == ("improcedente", "JULGO ... IMPROCEDENTE")


@pytest.mark.parametrize(
    ("texto", "valor"),
    [
        (SENTENCA_PARCIAL, 12345.67),
        (
            "Condeno ao pagamento de R$ 1.234.567,89 e honorários de R$ 500,00.",
            1234567.89,
        ),
        ("Multa diária de R$500.", 500.0),
        ("Sem valor nenhum.", None),
        ("Custas de R$ 0,00.", None),
    ],
)
def test_maior_valor_em_reais(texto, valor):
    assert pt.maior_valor(pt.texto_limpo(texto)) == valor


def test_texto_limpo_tira_html_acento_e_espacos():
    assert (
        pt.texto_limpo("<p>Sentença&nbsp;  de   <b>mérito</b></p>")
        == "SENTENCA DE MERITO"
    )


def test_ler_junta_tudo_e_nao_le_lista_de_muitos_processos():
    item = {"tipoDocumento": "Intimação", "texto": SENTENCA_PARCIAL}
    assert pt.ler(item) == pt.Leitura(
        "sentenca",
        "parcialmente_procedente",
        "JULGO PARCIALMENTE PROCEDENTES",
        12345.67,
    )
    pauta = {
        "tipoDocumento": "Pauta de Julgamento",
        "texto": "NEGAR PROVIMENTO R$ 10,00",
    }
    assert pt.ler(pauta) == pt.Leitura("pauta", None, None, None)
    longo = {"tipoDocumento": "Sentença", "texto": SENTENCA_PARCIAL * 200}
    assert pt.ler(longo) == pt.Leitura("sentenca", None, None, None)
    # tipo genérico num texto longo: o dispositivo pode ser de outro processo da lista
    assert pt.ler({**longo, "tipoDocumento": "Intimação"}) == pt.Leitura(
        None, None, None, None
    )
    assert pt.ler({"tipoDocumento": None, "texto": None}) == pt.Leitura(
        None, None, None, None
    )
