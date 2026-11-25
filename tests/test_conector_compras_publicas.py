"""A ferramenta `compras_publicas` do conector (linha 980, onda 2, PR 6).

Um pedido à rota `GET /companies/{cnpj}/public-procurement` (testada em `test_api_externa_compras.py`), cortado no
teto da conversa como a análise completa. A ferramenta nasce desligada: só aparece para a chave com o conjunto
`public_procurement` no contrato, que nenhuma organização tem por padrão (ligar é só do Tiago). Riscos que estes
testes pegam: a ferramenta aparecer sem o conjunto (ou com o perfil, o conjunto ampliado ou a integridade); pedir
outra rota ou perder o dia; o corte esconder que cortou; pessoa física passar pela tranca de saída; CPF no lugar do
CNPJ chegar à API. Todo valor aqui é inventado.
"""

import json

import httpx
import pytest

from conector_remoto import ferramentas
from tests import ajudantes_do_conector as aj
from tests.ajudantes_de_cpf import cpf_que_confere, formatado

NOME = "compras_publicas"
CONJUNTO = "public_procurement"
CNPJ = "11111111000191"  # de mentira, com os dígitos verificadores certos
UM_DIA = "2026-03-31"
ROTA = f"/companies/{CNPJ}/public-procurement"


def _campo(valor: object, fonte: str = "bps") -> dict:
    return {"value": valor, "source": fonte, "published_at": "2026-02-10"}


def _compras(itens_do_bps: int = 3, texto: str = "HOSPITAL X") -> dict:
    return {
        "cnpj": CNPJ,
        "known_at": UM_DIA,
        "blocks": {
            "public_procurement": {
                "sicaf_supplier_registration": {
                    "found": True,
                    "sources": ["comprasgov-sicaf"],
                    "coverage": "Cadastro de fornecedores do governo federal.",
                    "items": [{"qualified_to_bid": _campo(True, "comprasgov-sicaf")}],
                    "truncated": False,
                },
                "bps_health_purchases": {
                    "found": True,
                    "sources": ["bps"],
                    "coverage": "Banco de Preços em Saúde.",
                    "items": [
                        {
                            "institution": _campo(texto),
                            "unit_price_brl": _campo(0.1 + i),
                        }
                        for i in range(itens_do_bps)
                    ],
                    "truncated": False,
                },
            }
        },
        "not_found": [],
        "requests_used": 1,
        "limits": ["Só as compras públicas que a sua chave vê."],
        "sources": [{"source": "comprasgov-sicaf"}, {"source": "bps"}],
    }


def _chamar(corpo: dict | None = None, conjuntos=(CONJUNTO,), **argumentos):
    pedidos: list[httpx.Request] = []
    rotas = {} if corpo is None else {ROTA: httpx.Response(200, json=corpo)}
    transporte = aj.api_de_mentira(rotas, conjuntos=conjuntos, pedidos=pedidos)
    with aj.conector(transporte) as cliente:
        erro, texto = aj.chamar(cliente, aj.CHAVE_DE_MENTIRA, NOME, **argumentos)
    return erro, texto, [p for p in pedidos if p.url.path != "/data/v1/catalog"]


# ---------------------------------------------------------------- nasce desligada


def test_a_ferramenta_esta_registrada_so_com_o_conjunto_de_compras():
    assert ferramentas.CONJUNTOS_DA_FERRAMENTA[NOME] == frozenset({CONJUNTO})
    assert ferramentas.TITULOS_DAS_FERRAMENTAS[NOME]


@pytest.mark.parametrize(
    ("conjuntos", "aparece"),
    [
        (frozenset(), False),
        (frozenset({"profiles"}), False),
        (frozenset({"extended_sources"}), False),
        (frozenset({"integrity"}), False),
        (frozenset({"profiles", "extended_sources", "integrity", "credit"}), False),
        (frozenset({CONJUNTO}), True),
        (frozenset({"profiles", CONJUNTO}), True),
    ],
)
def test_o_portao_so_libera_com_o_conjunto_de_compras(conjuntos, aparece):
    assert ferramentas.ferramenta_liberada(NOME, conjuntos) is aparece


def test_aparece_so_para_quem_tem_o_conjunto_no_contrato():
    for conjuntos, aparece in (
        ((CONJUNTO,), True),
        (("profiles", "extended_sources", "integrity"), False),
    ):
        transporte = aj.api_de_mentira({}, conjuntos=conjuntos)
        with aj.conector(transporte) as cliente:
            nomes = aj.nomes_das_ferramentas(cliente, aj.CHAVE_DE_MENTIRA)
        assert (NOME in nomes) is aparece, conjuntos


# ---------------------------------------------------------------- o pedido e a resposta


def test_pede_a_rota_das_compras_com_o_dia():
    erro, texto, pedidos = _chamar(
        _compras(), cnpj="11.111.111/0001-91", como_era_em=UM_DIA
    )
    assert not erro, texto
    (pedido,) = pedidos
    assert pedido.url.path == f"/data/v1{ROTA}"
    assert pedido.url.params["known_at"] == UM_DIA
    corpo = json.loads(texto)
    item = corpo["blocks"]["public_procurement"]["bps_health_purchases"]["items"][0]
    assert item["unit_price_brl"]["source"] == "bps"
    assert item["unit_price_brl"]["published_at"] == "2026-02-10"
    assert corpo["requests_used"] == 1


def test_sem_o_dia_pede_o_de_hoje():
    _erro, _texto, pedidos = _chamar(_compras(), cnpj=CNPJ)
    (pedido,) = pedidos
    assert "known_at" not in pedido.url.params


def test_limite_corta_a_lista_e_diz_que_cortou():
    erro, texto, _ = _chamar(_compras(itens_do_bps=8), cnpj=CNPJ, limite=2)
    assert not erro, texto
    corpo = json.loads(texto)
    itens = corpo["blocks"]["public_procurement"]["bps_health_purchases"]["items"]
    assert len(itens) == 2
    assert "2 de 8" in json.dumps(corpo["limits"], ensure_ascii=False)


def test_a_resposta_grande_cabe_na_conversa_com_o_aviso_de_corte():
    erro, texto, _ = _chamar(_compras(itens_do_bps=3000), cnpj=CNPJ)
    assert not erro, texto
    corpo = json.loads(texto)
    itens = corpo["blocks"]["public_procurement"]["bps_health_purchases"]["items"]
    assert len(itens) < 3000
    assert "cortada" in json.dumps(corpo["limits"], ensure_ascii=False)


def test_sem_o_conjunto_a_api_responde_nao_disponivel_com_frase_clara():
    erro, texto, _ = _chamar(None, cnpj=CNPJ)
    assert erro
    assert "Não disponível" in texto and "o_que_posso_ver" in texto


# ---------------------------------------------------------------- pessoa física


def test_cpf_no_lugar_do_cnpj_e_recusado_sem_chamar_a_api():
    erro, texto, pedidos = _chamar(
        _compras(), cnpj=formatado(cpf_que_confere("888654321"))
    )
    assert erro and not pedidos
    assert "888654321" not in texto


def test_resposta_com_pessoa_e_recusada_inteira_sem_repetir_o_valor():
    cpf = formatado(cpf_que_confere("888654321"))
    erro, texto, _ = _chamar(_compras(texto=f"HOSPITAL {cpf}"), cnpj=CNPJ)
    assert erro and ferramentas.MENSAGEM_DE_PESSOA in texto
    assert cpf not in texto and "888654321" not in texto


def test_a_tranca_de_pessoa_le_tambem_o_item_que_o_limite_corta():
    # a trava roda antes do corte: o CPF só no último item, que `limite=1` tiraria, ainda recusa a resposta
    cpf = formatado(cpf_que_confere("888654321"))
    corpo = _compras(itens_do_bps=3)
    itens = corpo["blocks"]["public_procurement"]["bps_health_purchases"]["items"]
    itens[-1]["institution"] = _campo(f"HOSPITAL {cpf}")
    erro, texto, _ = _chamar(corpo, cnpj=CNPJ, limite=1)
    assert erro and ferramentas.MENSAGEM_DE_PESSOA in texto
    assert cpf not in texto and "888654321" not in texto
