"""A ferramenta `de_onde_vem` do conector (linha 980, onda 1, item 4).

Ela explica um conjunto ou um campo a partir do catálogo que a chave já lê (`/catalog`), sem pedir dado de
empresa. Riscos que estes testes pegam: (1) pedir ou entregar dado de empresa; (2) mostrar conjunto ou campo
que a chave não vê (duas organizações com catálogos diferentes); (3) erro da API sair sem frase clara ou
travar o conector; (4) o aviso de piloto repetido por campo, ou sumir; (5) pessoa física, CPF ou contato
passarem pela tranca de saída. Todo valor aqui é inventado.
"""

import json
import time

import httpx
import pytest

from conector_remoto import ferramentas, ferramentas_do_analista, saida
from conector_remoto.configuracao import TEMPO_LIMITE_DA_API_S
from conector_remoto.ferramentas_do_analista import MAXIMO_DE_ACHADOS
from tests import ajudantes_do_conector as aj
from tests.ajudantes_de_cpf import cpf_que_confere, formatado

CHAVE_A = aj.CHAVE_DE_MENTIRA
CHAVE_B = "tld_bcdefghi_" + "B" * 43
AVISO_DE_PILOTO = "Parte destes dados vem de piloto: confira antes de citar."


def _catalogo_da_a() -> dict:
    return {
        "datasets": [
            {
                "dataset": "profiles",
                "purpose": "analysis",
                "fields": [
                    {"field": "legal_name", "source": "rfb-cnpj"},
                    {"field": "size", "source": "rfb-cnpj"},
                ],
            },
            {
                "dataset": "credit",
                "purpose": "credit",
                "fields": [
                    {"field": "fidcs_as_assignor", "source": "cvm-fidc"},
                    {"field": "legal_name", "source": "rfb-cnpj", "pilot": True},
                    {
                        "field": "largest_delinquency",
                        "source": "cvm-fidc",
                        "pilot": True,
                    },
                ],
            },
        ],
        "sources": [
            {
                "source": "rfb-cnpj",
                "license": "dados abertos da Receita Federal",
                "attribution": "Fonte: Receita Federal.",
            },
            {
                "source": "cvm-fidc",
                "license": "dados abertos da CVM",
                "attribution": "Fonte: CVM.",
            },
        ],
        "pilot_notice": AVISO_DE_PILOTO,
    }


def _catalogo_da_b() -> dict:
    return {
        "datasets": [
            {
                "dataset": "profiles",
                "purpose": "analysis",
                "fields": [{"field": "size", "source": "rfb-cnpj"}],
            }
        ],
        "sources": [
            {
                "source": "rfb-cnpj",
                "license": "dados abertos da Receita Federal",
                "attribution": "Fonte: Receita Federal.",
            }
        ],
    }


def _api(
    catalogos: dict[str, dict] | None = None,
    pedidos: list[httpx.Request] | None = None,
    depois_da_porta: httpx.Response | None = None,
) -> httpx.MockTransport:
    """Um dublê da API com um catálogo por chave. `depois_da_porta` responde o 2º `/catalog` em diante (o 1º é o
    da porta do conector, que confere a chave)."""
    catalogos = catalogos or {CHAVE_A: _catalogo_da_a()}
    chamadas = {"catalogo": 0}

    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedidos is not None:
            pedidos.append(pedido)
        chave = pedido.headers.get("authorization", "").removeprefix("Bearer ")
        if chave not in catalogos:
            return httpx.Response(401, json={"detail": "invalid_api_key"})
        if pedido.url.path == "/data/v1/catalog":
            chamadas["catalogo"] += 1
            if depois_da_porta is not None and chamadas["catalogo"] > 1:
                return depois_da_porta
            return httpx.Response(200, json=catalogos[chave])
        return httpx.Response(404, json={"detail": "not_available"})

    return httpx.MockTransport(responder)


def _perguntar(transporte: httpx.MockTransport, chave: str, sobre: str):
    with aj.conector(transporte) as cliente:
        return aj.chamar(cliente, chave, "de_onde_vem", sobre=sobre)


def _explicar(sobre: str, chave: str = CHAVE_A, **api) -> dict:
    with aj.conector(_api(**api)) as cliente:
        return aj.chamar_ok(cliente, chave, "de_onde_vem", sobre=sobre)


# ---------------------------------------------------------------- a ligação com ferramentas.py


def test_a_ferramenta_vale_para_toda_chave_como_o_que_posso_ver():
    assert ferramentas.CONJUNTOS_DA_FERRAMENTA["de_onde_vem"] == frozenset()
    assert ferramentas.TITULOS_DAS_FERRAMENTAS["de_onde_vem"]
    assert hasattr(ferramentas_do_analista, "registrar")


def test_a_ferramenta_aparece_para_chave_de_qualquer_organizacao():
    transporte = _api({CHAVE_A: _catalogo_da_a(), CHAVE_B: _catalogo_da_b()})
    with aj.conector(transporte) as cliente:
        assert "de_onde_vem" in aj.nomes_das_ferramentas(cliente, CHAVE_A)
        assert "de_onde_vem" in aj.nomes_das_ferramentas(cliente, CHAVE_B)


# ---------------------------------------------------------------- o que ela explica


def test_conjunto_traz_campos_fontes_licenca_e_finalidade():
    corpo = _explicar("credit")
    assert corpo["kind"] == "dataset"
    (achado,) = corpo["matches"]
    assert achado["dataset"] == "credit" and achado["purpose"] == "credit"
    assert [c["field"] for c in achado["fields"]] == [
        "fidcs_as_assignor",
        "legal_name",
        "largest_delinquency",
    ]
    assert {c["source"] for c in achado["fields"]} == {"cvm-fidc", "rfb-cnpj"}
    licencas = {f["source"]: f for f in corpo["sources"]}
    assert licencas["cvm-fidc"]["license"] == "dados abertos da CVM"
    assert licencas["rfb-cnpj"]["attribution"] == "Fonte: Receita Federal."


def test_campo_traz_cada_conjunto_em_que_aparece_e_a_fonte_de_cada():
    corpo = _explicar("legal_name")
    assert corpo["kind"] == "field"
    achados = {(m["dataset"], m["source"]) for m in corpo["matches"]}
    assert achados == {("profiles", "rfb-cnpj"), ("credit", "rfb-cnpj")}


def test_a_pergunta_ignora_maiuscula_e_espaco_nas_pontas():
    assert _explicar("  CREDIT ")["matches"][0]["dataset"] == "credit"


def test_so_as_fontes_do_achado_vao_na_resposta():
    corpo = _explicar("size")
    assert [f["source"] for f in corpo["sources"]] == ["rfb-cnpj"]


def test_o_aviso_de_piloto_vem_uma_vez_com_a_lista_dos_campos_de_piloto():
    corpo = _explicar("credit")
    texto = json.dumps(corpo, ensure_ascii=False)
    assert texto.count(AVISO_DE_PILOTO) == 1
    assert corpo["pilot_fields"] == ["credit.largest_delinquency", "credit.legal_name"]
    marcados = [c["field"] for c in corpo["matches"][0]["fields"] if c.get("pilot")]
    assert marcados == ["legal_name", "largest_delinquency"]


def test_sem_campo_de_piloto_nao_ha_aviso_nem_lista():
    corpo = _explicar("profiles")
    assert "pilot_notice" not in corpo and "pilot_fields" not in corpo


def test_a_resposta_diz_o_que_o_catalogo_nao_traz():
    corpo = _explicar("profiles")
    assert any("significado" in limite for limite in corpo["limits"])


# ---------------------------------------------------------------- não pede dado de empresa


def test_so_o_catalogo_e_consultado_nunca_uma_rota_de_empresa():
    pedidos: list[httpx.Request] = []
    _explicar("credit", pedidos=pedidos)
    assert {p.url.path for p in pedidos} == {"/data/v1/catalog"}


# ---------------------------------------------------------------- nada que a chave não vê


def test_duas_organizacoes_nao_veem_o_catalogo_uma_da_outra():
    transporte = _api({CHAVE_A: _catalogo_da_a(), CHAVE_B: _catalogo_da_b()})
    with aj.conector(transporte) as cliente:
        da_a = aj.chamar_ok(cliente, CHAVE_A, "de_onde_vem", sobre="credit")
        erro, texto = aj.chamar(cliente, CHAVE_B, "de_onde_vem", sobre="credit")
        erro_campo, texto_campo = aj.chamar(
            cliente, CHAVE_B, "de_onde_vem", sobre="legal_name"
        )
    assert da_a["matches"][0]["dataset"] == "credit"
    assert erro and "cvm-fidc" not in texto and "fidcs_as_assignor" not in texto
    assert erro_campo and "rfb-cnpj" not in texto_campo


def test_pergunta_sem_achado_diz_que_a_chave_nao_ve_e_aponta_o_o_que_posso_ver():
    erro, texto = _perguntar(_api(), CHAVE_A, "nao_existe")
    assert erro and "o_que_posso_ver" in texto and "sua chave" in texto


def test_o_erro_de_pergunta_sem_achado_nao_lista_conjuntos_nem_campos():
    _, texto = _perguntar(_api(), CHAVE_A, "nao_existe")
    assert "credit" not in texto and "legal_name" not in texto


@pytest.mark.parametrize("sobre", ["", "   ", "a b", "credit;", "x" * 81, "../credit"])
def test_pergunta_que_nao_e_nome_de_conjunto_ou_campo_e_recusada(sobre):
    erro, texto = _perguntar(_api(), CHAVE_A, sobre)
    assert erro and "Traceback" not in texto


# ---------------------------------------------------------------- erros da API


@pytest.mark.parametrize(
    ("resposta", "frase"),
    [
        (
            httpx.Response(
                429, json={"detail": "rate_limited"}, headers={"Retry-After": "17"}
            ),
            "tente de novo em 17 s",
        ),
        (
            httpx.Response(429, json={"detail": "monthly_quota"}),
            "quota de pedidos do mês",
        ),
        (httpx.Response(401, json={"detail": "invalid_api_key"}), "chave foi recusada"),
        (httpx.Response(503, json={"detail": "unavailable"}), "fora do ar"),
        (httpx.Response(500, json={"detail": "boom"}), "erro inesperado (status 500)"),
    ],
)
def test_erro_da_api_vira_frase_clara_em_portugues(resposta, frase):
    erro, texto = _perguntar(_api(depois_da_porta=resposta), CHAVE_A, "credit")
    assert erro and frase in texto
    assert CHAVE_A not in texto and "Traceback" not in texto


def test_api_lenta_nao_trava_o_conector_e_devolve_a_frase_de_sempre():
    chamadas = {"n": 0}

    def lenta(pedido: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            return httpx.Response(200, json=_catalogo_da_a())
        raise httpx.ReadTimeout("a API demorou", request=pedido)

    inicio = time.perf_counter()
    erro, texto = _perguntar(httpx.MockTransport(lenta), CHAVE_A, "credit")
    assert erro and "não respondeu" in texto
    assert time.perf_counter() - inicio < TEMPO_LIMITE_DA_API_S


# ---------------------------------------------------------------- a tranca de saída


@pytest.mark.parametrize(
    "sujo",
    [
        {"cpf": "x"},
        {"partners": [{"name": "FULANA EXEMPLO"}]},
        {"attribution_extra": f"titular {formatado(cpf_que_confere('888654321'))}"},
        {"contact": "fulana@exemplo.invalid"},
    ],
    ids=["chave de CPF", "sócio", "CPF no texto", "e-mail"],
)
def test_catalogo_com_pessoa_e_recusado_inteiro_sem_repetir_o_valor(sujo):
    catalogo = _catalogo_da_a()
    catalogo["sources"][0] = catalogo["sources"][0] | sujo
    erro, texto = _perguntar(_api({CHAVE_A: catalogo}), CHAVE_A, "profiles")
    assert erro
    assert "FULANA" not in texto and "exemplo.invalid" not in texto
    assert "888654321" not in texto


def test_a_descricao_segue_o_molde_e_nao_promete_nada():
    transporte = _api()
    with aj.conector(transporte) as cliente:
        corpo = aj.rpc(cliente, CHAVE_A, "tools/list").json()
    ferramenta = next(f for f in corpo["result"]["tools"] if f["name"] == "de_onde_vem")
    texto = ferramenta["description"]
    for marca in ("Serve para", "Fonte:", "Não traz:"):
        assert texto.count(marca) == 1
    for proibido in ("recomend", "garant", "promet", "R$"):
        assert proibido not in texto


# ---------------------------------------------------------------- o teto da resposta


def test_campo_em_muitos_conjuntos_vem_cortado_e_cabe_no_teto():
    catalogo = _catalogo_da_a()
    catalogo["datasets"] = [
        {
            "dataset": f"conjunto_{n}",
            "purpose": "analysis",
            "fields": [{"field": "size", "source": "rfb-cnpj"}],
        }
        for n in range(200)
    ]
    corpo = _explicar("size", pedidos=None, catalogos={CHAVE_A: catalogo})
    assert len(corpo["matches"]) == MAXIMO_DE_ACHADOS and corpo["truncated"] is True
    assert len(json.dumps(corpo)) < saida.TETO_DE_CARACTERES
