"""A ferramenta `registros_nas_agencias` do conector (linha 980, onda 2, PR 5).

Um pedido à rota `GET /companies/{cnpj}/registrations` (testada em `test_api_externa_registros.py`), cortado no
teto da conversa como a análise completa. Riscos que estes testes pegam: a ferramenta aparecer para a chave que
não vê nenhum dos conjuntos; pedir outra rota ou perder o dia; o corte esconder que cortou; pessoa física passar
pela tranca de saída; CPF no lugar do CNPJ chegar à API. Todo valor aqui é inventado.
"""

import json

import httpx

from conector_remoto import ferramentas
from tests import ajudantes_do_conector as aj
from tests.ajudantes_de_cpf import cpf_que_confere, formatado

NOME = "registros_nas_agencias"
CNPJ = "11111111000191"  # de mentira, com os dígitos verificadores certos
UM_DIA = "2026-03-31"
ROTA = f"/companies/{CNPJ}/registrations"


def _campo(valor: object, fonte: str = "aneel-fiscalizacao") -> dict:
    return {"value": valor, "source": fonte, "published_at": "2026-02-10"}


def _registros(itens_da_aneel: int = 3, texto: str = "AGENTE X") -> dict:
    return {
        "cnpj": CNPJ,
        "known_at": UM_DIA,
        "blocks": {
            "regulated_activities": {
                "aneel_commercial_indicators": {
                    "found": True,
                    "sources": ["aneel-fiscalizacao"],
                    "coverage": "Indicadores comerciais das distribuidoras.",
                    "items": [
                        {
                            "agent_acronym": _campo(texto),
                            "active_consumer_units": _campo(100 + i),
                        }
                        for i in range(itens_da_aneel)
                    ],
                    "truncated": False,
                }
            },
            "additional_records": {
                "anp_storage_capacity": {
                    "found": True,
                    "sources": ["anp-tancagem"],
                    "coverage": "Tancagem autorizada pela ANP.",
                    "items": [{"storage_capacity_m3": _campo(1500.0, "anp-tancagem")}],
                    "truncated": False,
                }
            },
        },
        "not_found": [],
        "requests_used": 2,
        "limits": ["Só os registros da empresa nas agências que a sua chave vê."],
        "sources": [{"source": "aneel-fiscalizacao"}, {"source": "anp-tancagem"}],
    }


def _chamar(
    corpo: dict | None = None, conjuntos=("profiles", "extended_sources"), **argumentos
):
    pedidos: list[httpx.Request] = []
    rotas = {} if corpo is None else {ROTA: httpx.Response(200, json=corpo)}
    transporte = aj.api_de_mentira(rotas, conjuntos=conjuntos, pedidos=pedidos)
    with aj.conector(transporte) as cliente:
        erro, texto = aj.chamar(cliente, aj.CHAVE_DE_MENTIRA, NOME, **argumentos)
    return erro, texto, [p for p in pedidos if p.url.path != "/data/v1/catalog"]


# ---------------------------------------------------------------- quem vê a ferramenta


def test_a_ferramenta_esta_registrada_com_os_dois_conjuntos():
    assert ferramentas.CONJUNTOS_DA_FERRAMENTA[NOME] == frozenset(
        {"profiles", "extended_sources"}
    )
    assert ferramentas.TITULOS_DAS_FERRAMENTAS[NOME]


def test_aparece_para_quem_ve_um_dos_conjuntos_e_some_para_quem_nao_ve_nenhum():
    for conjuntos, aparece in (
        (("profiles",), True),
        (("extended_sources",), True),
        (("credit", "companies"), False),
    ):
        transporte = aj.api_de_mentira({}, conjuntos=conjuntos)
        with aj.conector(transporte) as cliente:
            nomes = aj.nomes_das_ferramentas(cliente, aj.CHAVE_DE_MENTIRA)
        assert (NOME in nomes) is aparece, conjuntos


# ---------------------------------------------------------------- o pedido e a resposta


def test_pede_a_rota_dos_registros_com_o_dia():
    erro, texto, pedidos = _chamar(
        _registros(), cnpj="11.111.111/0001-91", como_era_em=UM_DIA
    )
    assert not erro, texto
    (pedido,) = pedidos
    assert pedido.url.path == f"/data/v1{ROTA}"
    assert pedido.url.params["known_at"] == UM_DIA
    corpo = json.loads(texto)
    item = corpo["blocks"]["regulated_activities"]["aneel_commercial_indicators"][
        "items"
    ][0]
    assert item["active_consumer_units"]["source"] == "aneel-fiscalizacao"
    assert item["active_consumer_units"]["published_at"] == "2026-02-10"
    assert corpo["requests_used"] == 2


def test_sem_o_dia_pede_o_de_hoje():
    _erro, _texto, pedidos = _chamar(_registros(), cnpj=CNPJ)
    (pedido,) = pedidos
    assert "known_at" not in pedido.url.params


def test_blocos_traz_so_o_bloco_pedido():
    erro, texto, _ = _chamar(_registros(), cnpj=CNPJ, blocos=["additional_records"])
    assert not erro, texto
    assert set(json.loads(texto)["blocks"]) == {"additional_records"}


def test_limite_corta_a_lista_e_diz_que_cortou():
    erro, texto, _ = _chamar(_registros(itens_da_aneel=8), cnpj=CNPJ, limite=2)
    assert not erro, texto
    corpo = json.loads(texto)
    itens = corpo["blocks"]["regulated_activities"]["aneel_commercial_indicators"][
        "items"
    ]
    assert len(itens) == 2
    assert "2 de 8" in json.dumps(corpo["limits"], ensure_ascii=False)


def test_a_resposta_grande_cabe_na_conversa_com_o_aviso_de_corte():
    erro, texto, _ = _chamar(_registros(itens_da_aneel=3000), cnpj=CNPJ)
    assert not erro, texto
    corpo = json.loads(texto)
    assert (
        len(
            corpo["blocks"]["regulated_activities"]["aneel_commercial_indicators"][
                "items"
            ]
        )
        < 3000
    )
    assert "cortada" in json.dumps(corpo["limits"], ensure_ascii=False)


def test_sem_nenhum_dos_conjuntos_a_api_responde_nao_disponivel_com_frase_clara():
    erro, texto, _ = _chamar(None, cnpj=CNPJ)
    assert erro
    assert "Não disponível" in texto and "o_que_posso_ver" in texto


# ---------------------------------------------------------------- pessoa física


def test_cpf_no_lugar_do_cnpj_e_recusado_sem_chamar_a_api():
    erro, texto, pedidos = _chamar(
        _registros(), cnpj=formatado(cpf_que_confere("888654321"))
    )
    assert erro and not pedidos
    assert "888654321" not in texto


def test_resposta_com_pessoa_e_recusada_inteira_sem_repetir_o_valor():
    cpf = formatado(cpf_que_confere("888654321"))
    erro, texto, _ = _chamar(_registros(texto=f"AGENTE {cpf}"), cnpj=CNPJ)
    assert erro and ferramentas.MENSAGEM_DE_PESSOA in texto
    assert cpf not in texto and "888654321" not in texto
