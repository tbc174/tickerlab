"""Os prompts do conector (linha 901): os fluxos da casa de M&A, sem dado e sem pessoa.

Riscos: um prompt citar ferramenta que não existe (o modelo inventa a resposta), pedir dado de pessoa física,
levar ao pedido um argumento que não foi conferido (CPF no lugar do CNPJ) ou aparecer sem a chave.
"""

import re

import pytest
from mcp.types import INVALID_PARAMS

from conector_remoto import ferramentas, prompts, servidor
from tests import ajudantes_do_conector as aj
from tests.ajudantes_de_cpf import CPF_DE_TESTE, formatado

CNPJ = "11111111000191"
PROMPTS = {
    "triagem_de_cnpj": {"cnpj": "11.111.111/0001-91"},
    "alvos_no_setor": {"cnae": "3511-5", "uf": "sp", "anos_de_abertura": "5"},
    "compradores_no_setor": {"cnae": "6201-5", "uf": "MG", "anos": "3"},
    "comparaveis_da_empresa": {"cnpj": CNPJ, "como_era_em": "2025-06-30"},
    "dossie_da_empresa": {"cnpj": CNPJ},
}


def _conector():
    return aj.conector(aj.api_de_mentira({}))


def _pedir(cliente, nome: str, argumentos: dict[str, str]):
    return aj.rpc(
        cliente,
        aj.CHAVE_DE_MENTIRA,
        "prompts/get",
        {"name": nome, "arguments": argumentos},
    )


def _texto(cliente, nome: str, argumentos: dict[str, str]) -> str:
    resposta = _pedir(cliente, nome, argumentos)
    assert resposta.status_code == 200, resposta.text
    (mensagem,) = resposta.json()["result"]["messages"]
    assert mensagem["role"] == "user"
    return mensagem["content"]["text"]


def test_lista_os_cinco_fluxos_com_titulo_e_argumentos():
    with _conector() as cliente:
        resposta = aj.rpc(cliente, aj.CHAVE_DE_MENTIRA, "prompts/list")
    assert resposta.status_code == 200, resposta.text
    lista = {p["name"]: p for p in resposta.json()["result"]["prompts"]}
    assert set(lista) == set(PROMPTS)
    for prompt in lista.values():
        assert prompt["title"] and prompt["description"]
        for argumento in prompt["arguments"]:
            assert argumento["description"]
    obrigatorios = {
        nome: sorted(a["name"] for a in p["arguments"] if a["required"])
        for nome, p in lista.items()
    }
    assert obrigatorios == {
        "triagem_de_cnpj": ["cnpj"],
        "alvos_no_setor": ["cnae", "uf"],
        "compradores_no_setor": ["cnae"],
        "comparaveis_da_empresa": ["cnpj"],
        "dossie_da_empresa": ["cnpj"],
    }


@pytest.mark.parametrize("nome", sorted(PROMPTS))
def test_cada_fluxo_cita_so_ferramentas_que_existem_e_fecha_com_as_travas(nome):
    with _conector() as cliente:
        texto = _texto(cliente, nome, PROMPTS[nome])
    citadas = set(re.findall(r"`([a-z_]+)`", texto))
    usadas = citadas & set(ferramentas.CONJUNTOS_DA_FERRAMENTA)
    assert usadas, texto
    parametros = {"como_era_em", "aberta_antes_de", "next_cursor", "limits", "anos"}
    assert citadas <= set(ferramentas.CONJUNTOS_DA_FERRAMENTA) | parametros
    assert texto.endswith(prompts.FECHO)
    assert "Não traga dado de pessoa física" in texto


def test_argumentos_saem_conferidos_e_limpos():
    with _conector() as cliente:
        triagem = _texto(cliente, "triagem_de_cnpj", PROMPTS["triagem_de_cnpj"])
        alvos = _texto(cliente, "alvos_no_setor", PROMPTS["alvos_no_setor"])
        comparaveis = _texto(
            cliente, "comparaveis_da_empresa", PROMPTS["comparaveis_da_empresa"]
        )
        compradores = _texto(
            cliente, "compradores_no_setor", PROMPTS["compradores_no_setor"]
        )
    assert CNPJ in triagem
    assert "CNAE 62015 na UF MG nos últimos 3 anos" in compradores
    assert "CNAE 35115 na UF SP" in alvos and "há mais de 5 anos" in alvos
    assert "`como_era_em` = 2025-06-30" in comparaveis


def test_dossie_usa_a_mesma_orientacao_das_instrucoes():
    with _conector() as cliente:
        texto = _texto(cliente, "dossie_da_empresa", PROMPTS["dossie_da_empresa"])
    assert servidor.ORIENTACAO_DO_DOSSIE in texto


@pytest.mark.parametrize(
    ("nome", "argumentos"),
    [
        (
            "triagem_de_cnpj",
            {"cnpj": formatado(CPF_DE_TESTE)},
        ),  # forma de CPF, de ninguém
        ("dossie_da_empresa", {"cnpj": "../companies"}),
        ("comparaveis_da_empresa", {"cnpj": CNPJ, "como_era_em": "ontem"}),
        ("alvos_no_setor", {"cnae": "energia", "uf": "SP"}),
        ("alvos_no_setor", {"cnae": "35", "uf": "São Paulo"}),
        ("alvos_no_setor", {"cnae": "35", "uf": "SP", "anos_de_abertura": "-1"}),
        ("compradores_no_setor", {"cnae": "62015", "anos": "mil"}),
        # a ferramenta de compradores só aceita classe ou subclasse, e até 10 anos
        ("compradores_no_setor", {"cnae": "62"}),
        ("compradores_no_setor", {"cnae": "62015", "anos": "50"}),
        # só ASCII: dígito sobrescrito, dígito arábico e a letra que o upper dobra
        ("alvos_no_setor", {"cnae": "35", "uf": "SP", "anos_de_abertura": "²"}),
        ("alvos_no_setor", {"cnae": "٦٢", "uf": "SP"}),
        ("alvos_no_setor", {"cnae": "35", "uf": "ß"}),
    ],
)
def test_argumento_fora_da_forma_e_recusado_sem_montar_o_pedido(nome, argumentos):
    with _conector() as cliente:
        resposta = _pedir(cliente, nome, argumentos)
    corpo = resposta.json()
    assert "result" not in corpo
    erro = corpo["error"]
    assert erro["code"] == INVALID_PARAMS
    # a frase é nossa, em português, e não repete o que foi digitado
    assert "Error rendering" not in erro["message"]
    assert all(valor not in erro["message"] for valor in argumentos.values())


def test_sem_chave_nao_ha_prompt():
    with _conector() as cliente:
        resposta = aj.rpc(cliente, None, "prompts/list")
    assert resposta.status_code == 401
