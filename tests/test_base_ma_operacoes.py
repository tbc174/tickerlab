"""A ligação das etapas de M&A: os documentos da mesma operação viram uma operação (a compradora e a
alvo publicam no mesmo dia; a assembleia e o fechamento vêm depois), e operações diferentes não se
juntam. Os dois primeiros casos são os da amostra de ouro com dois documentos da mesma operação."""

from datetime import date, timedelta

from base import ma_extracao as mx
from base import ma_operacoes as mo


def _doc(
    protocolo: str,
    dia: date,
    tipo: str,
    alvo: str | None,
    comprador: str | None = None,
    etapa: str | None = None,
) -> mo.DocumentoLido:
    partes = [
        mx.Parte(nome=nome, papel=papel, trecho=nome)
        for nome, papel in ((alvo, "alvo"), (comprador, "comprador"))
        if nome
    ]
    leitura = mx.LeituraDaOperacao.model_validate(
        {"tipo": tipo, "etapa": etapa, "partes": [p.model_dump() for p in partes]}
    )
    return mo.DocumentoLido(protocolo, dia, leitura)


BTG = "Banco BTG Pactual S.A."
PAN = "Banco Pan S.A."
TOTVS = "TOTVS S.A."
BEMATECH = "Bematech S.A."
DIA = date(2025, 11, 18)


def _grupos(documentos: list[mo.DocumentoLido]) -> list[set[str]]:
    ligacao = mo.ligar(documentos)
    grupos: dict[str, set[str]] = {}
    for protocolo, operacao in ligacao.items():
        grupos.setdefault(operacao, set()).add(protocolo)
    return sorted(grupos.values(), key=min)


def test_compradora_e_alvo_no_mesmo_dia_viram_uma_operacao():
    # amostra de ouro, linhas 98-99 e 5-6: a mesma incorporação de ações publicada pelas duas
    documentos = [
        _doc("btg", DIA, "INC_ACOES", PAN, BTG),
        _doc("pan", DIA, "INC_ACOES", "Banco Pan S.A. (“Pan”)", BTG),
        _doc("totvs", date(2015, 10, 6), "INC_ACOES", BEMATECH, TOTVS),
        _doc("bematech", date(2015, 10, 6), "INC_ACOES", "Bematech S/A", TOTVS, "CADE_APROVADO"),
    ]  # fmt: skip
    assert _grupos(documentos) == [{"bematech", "totvs"}, {"btg", "pan"}]


def test_assembleia_e_fechamento_ligam_pela_cadeia():
    # o fechamento está a mais de uma janela do anúncio, mas perto da assembleia
    perto = timedelta(days=mo.JANELA_EM_DIAS - 10)
    documentos = [
        _doc("anuncio", DIA, "AQ_CONTROLE", PAN, BTG),
        _doc("assembleia", DIA + perto, "AQ_CONTROLE", PAN, None, "ASSEMBLEIA"),
        _doc("fechamento", DIA + 2 * perto, "AQ_CONTROLE", PAN, BTG, "FECHAMENTO"),
    ]
    assert _grupos(documentos) == [{"anuncio", "assembleia", "fechamento"}]
    tabela, _ = mo.operacoes(documentos)
    assert tabela[["operacao", "situacao", "documentos"]].to_dict("records") == [
        {"operacao": "anuncio", "situacao": mo.CONCLUIDA, "documentos": 3}
    ]


def test_venda_de_um_lado_e_aquisicao_do_outro_sao_a_mesma():
    documentos = [
        _doc("vendedora", DIA, "VENDA_ATIVO", "Gama Logística Ltda."),
        _doc("compradora", DIA, "AQ_CONTROLE", "Gama Logística Ltda.", BTG),
    ]
    assert _grupos(documentos) == [{"compradora", "vendedora"}]


def test_operacoes_diferentes_nao_se_juntam():
    longe = timedelta(days=mo.JANELA_EM_DIAS + 1)
    documentos = [
        _doc("a", DIA, "AQ_CONTROLE", PAN, BTG),
        _doc("outro-comprador", DIA, "AQ_CONTROLE", PAN, "Caixa Participações S.A."),
        _doc("outra-familia", DIA, "OPA_CANCEL", PAN, BTG),
        _doc("outra-alvo", DIA, "AQ_CONTROLE", BEMATECH, BTG),
        _doc("depois-da-janela", DIA + longe, "AQ_CONTROLE", PAN, BTG),
        _doc("sem-alvo", DIA, "AQ_CONTROLE", None, BTG),
    ]
    assert len(_grupos(documentos)) == len(documentos)


def test_nao_e_operacao_fica_de_fora():
    documentos = [
        _doc("a", DIA, "AQ_CONTROLE", PAN, BTG),
        _doc("esclarecimento", DIA, mx.NAO_E_OPERACAO, None),
    ]
    assert mo.ligar(documentos) == {"a": "a"}


def test_ligacao_nao_depende_da_ordem_dos_documentos():
    documentos = [
        _doc("b", DIA, "INC_ACOES", PAN, BTG),
        _doc("a", DIA, "INC_ACOES", PAN, BTG),
        _doc("c", DIA + timedelta(days=30), "INC_ACOES", PAN, BTG, "ASSEMBLEIA"),
    ]
    assert mo.ligar(documentos) == mo.ligar(list(reversed(documentos)))
    assert set(mo.ligar(documentos).values()) == {"a"}  # o id é o 1º documento


def test_tabela_da_operacao():
    documentos = [
        _doc("anuncio", DIA, "AQ_MINORITARIA", PAN, BTG),
        _doc("cade", DIA + timedelta(days=90), "AQ_CONTROLE", PAN, BTG, "CADE_APROVADO"),
        _doc("assembleia", DIA + timedelta(days=120), "AQ_CONTROLE", PAN, BTG),
        _doc("cancelada", DIA, "JV", BEMATECH, TOTVS, "CANCELAMENTO"),
    ]  # fmt: skip
    tabela, ligacoes = mo.operacoes(documentos)
    assert tabela.to_dict("records") == [
        {
            "operacao": "anuncio",
            "tipo": "AQ_CONTROLE",  # o mais lido
            "familia": "controle",
            "situacao": mo.APROVADA,
            "alvo": PAN,
            "primeira_data_publica": DIA,
            "ultima_data_publica": DIA + timedelta(days=120),
            "documentos": 3,
        },
        {
            "operacao": "cancelada",
            "tipo": "JV",
            "familia": "jv",
            "situacao": mo.CANCELADA,
            "alvo": BEMATECH,
            "primeira_data_publica": DIA,
            "ultima_data_publica": DIA,
            "documentos": 1,
        },
    ]
    assert ligacoes.to_dict("records") == [
        {"protocolo": "anuncio", "operacao": "anuncio"},
        {"protocolo": "assembleia", "operacao": "anuncio"},
        {"protocolo": "cade", "operacao": "anuncio"},
        {"protocolo": "cancelada", "operacao": "cancelada"},
    ]


def test_todo_tipo_de_operacao_tem_familia():
    tipos = set(mx._enum(mx.Tipo)) - {mx.NAO_E_OPERACAO}
    assert tipos == set(mo.FAMILIA_DO_TIPO)


def test_comparar_acha_duplicadas_e_juntadas():
    gabarito = {
        "btg": "btg",
        "pan": "btg",
        "totvs": "totvs",
        "bematech": "totvs",
        "x": "x",
    }
    lida = {
        "btg": "btg",
        "pan": "pan",
        "totvs": "totvs",
        "bematech": "totvs",
        "x": "totvs",
    }
    lida["fora-do-gabarito"] = "btg"  # só conta o que os dois leram
    assert mo.comparar(lida, gabarito) == {
        "no_gabarito": [["bematech", "totvs"], ["btg", "pan"]],
        "separadas": [["btg", "pan"]],
        "juntadas": [["bematech", "x"], ["totvs", "x"]],
    }


def test_mesma_empresa_e_mais_estrita_que_a_da_medida():
    # amostra de ouro: as alvos destes pares são de operações diferentes, mas dividem uma palavra
    diferentes = [
        ("Banco BTG Pactual", "Banco Pan S.A."),
        ("UPI IPM/IOG", "UPI ClientCo"),
        ("Companhia de Saneamento Básico do Estado de São Paulo (Sabesp)", "Tubarão Saneamento S.A."),
        ("acervo cindido da Viver", "acervo cindido da REAG Investimentos S.A."),
    ]  # fmt: skip
    for a, b in diferentes:
        assert mx.nomes_batem(a, b) and not mx.mesma_empresa(a, b), (a, b)
    iguais = [
        ("Sabesp", "Companhia de Saneamento Básico do Estado de São Paulo (Sabesp)"),
        ("CEEE-D", "Companhia Estadual de Distribuição de Energia Elétrica – CEEE-D"),
        ("Banco Pan S.A. (“Pan”)", "Banco PAN"),
        ("Bematech S/A", "BEMATECH S.A."),
    ]
    for a, b in iguais:
        assert mx.mesma_empresa(a, b) and mx.mesma_empresa(b, a), (a, b)


def test_alvos_que_so_dividem_uma_palavra_nao_se_juntam():
    documentos = [
        _doc("btg-alvo", DIA, "AQ_CONTROLE", "Banco BTG Pactual S.A."),
        _doc("pan-alvo", DIA, "AQ_CONTROLE", PAN),
    ]
    assert len(_grupos(documentos)) == 2
