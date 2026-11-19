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
    # linha 980, onda 1: os três fluxos novos do analista
    "preparar_reuniao": {"cnpj": "11.111.111/0001-91", "como_era_em": "2025-06-30"},
    "perfil_sem_nome": {"cnpj": CNPJ},
    "lista_longa_de_compradores": {"cnae": "6201-5", "uf": "mg", "anos": "5"},
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


def test_lista_os_oito_fluxos_com_titulo_e_argumentos():
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
        "preparar_reuniao": ["cnpj"],
        "perfil_sem_nome": ["cnpj"],
        "lista_longa_de_compradores": ["cnae"],
    }


@pytest.mark.parametrize("nome", sorted(PROMPTS))
def test_cada_fluxo_cita_so_ferramentas_que_existem_e_fecha_com_as_travas(nome):
    with _conector() as cliente:
        texto = _texto(cliente, nome, PROMPTS[nome])
    citadas = set(re.findall(r"`([a-z_]+)`", texto))
    usadas = citadas & set(ferramentas.CONJUNTOS_DA_FERRAMENTA)
    assert usadas, texto
    parametros = {
        "como_era_em",
        "aberta_antes_de",
        "next_cursor",
        "limits",
        "anos",
        "limite",
    }
    assert citadas <= set(ferramentas.CONJUNTOS_DA_FERRAMENTA) | parametros
    if nome == "perfil_sem_nome":
        # o perfil anônimo não pode liberar nem o nome de sócio: o fecho dele é outro
        assert texto.endswith(prompts.FECHO_ANONIMO)
        assert "Não consulte nem escreva nome de pessoa física" in texto
        return
    assert texto.endswith(prompts.FECHO)
    assert (
        "De pessoa física, só o que `socios_e_donos`" in texto
        and "sem CPF nem contato" in texto
    )


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
        # os três novos conferem os argumentos como os outros
        ("preparar_reuniao", {"cnpj": formatado(CPF_DE_TESTE)}),
        ("preparar_reuniao", {"cnpj": CNPJ, "como_era_em": "ontem"}),
        ("perfil_sem_nome", {"cnpj": "../companies"}),
        ("perfil_sem_nome", {"cnpj": CNPJ, "como_era_em": "31/12/2025"}),
        ("lista_longa_de_compradores", {"cnae": "62"}),
        ("lista_longa_de_compradores", {"cnae": "62015", "uf": "São Paulo"}),
        ("lista_longa_de_compradores", {"cnae": "62015", "anos": "50"}),
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


NOVOS = ("preparar_reuniao", "perfil_sem_nome", "lista_longa_de_compradores")


@pytest.mark.parametrize("nome", NOVOS)
def test_os_novos_nao_pedem_estimativa_nem_recomendacao(nome):
    with _conector() as cliente:
        texto = _texto(cliente, nome, PROMPTS[nome]).lower()
    # palavra inteira: "estime" não pode pegar "investimento"
    for pedido_vedado in (
        "estime",
        "estimar",
        "faturamento",
        "recomende",
        "indique",
        "invista",
        "compre",
        "venda",
    ):
        assert not re.search(rf"\b{pedido_vedado}\b", texto), (nome, pedido_vedado)


def test_preparar_reuniao_monta_a_pagina_com_perguntas_ligadas_a_fatos():
    with _conector() as cliente:
        texto = _texto(cliente, "preparar_reuniao", PROMPTS["preparar_reuniao"])
    assert CNPJ in texto and "`como_era_em` = 2025-06-30" in texto
    for ferramenta in ("ficha_da_empresa", "eventos", "vinculos", "comparaveis"):
        assert f"`{ferramenta}`" in texto
    assert "perguntas" in texto and "fato" in texto


def test_perfil_sem_nome_so_consulta_a_ficha_e_proibe_o_que_identifica():
    with _conector() as cliente:
        texto = _texto(cliente, "perfil_sem_nome", PROMPTS["perfil_sem_nome"])
    citadas = set(re.findall(r"`([a-z_]+)`", texto))
    # eventos e vínculos trazem nomes de terceiros e fatos que identificam a empresa
    assert citadas & set(ferramentas.CONJUNTOS_DA_FERRAMENTA) == {"ficha_da_empresa"}
    for identificador in (
        "razão social",
        "nome fantasia",
        "CNPJ",
        "município",
        "UF",
        "endereço",
        "nome de sócio",
    ):
        assert identificador in texto, identificador
    assert "região" in texto and "faixa" in texto
    assert "releia" in texto


def test_perfil_sem_nome_nao_repete_o_cnpj_alem_do_pedido_da_ficha():
    with _conector() as cliente:
        texto = _texto(cliente, "perfil_sem_nome", PROMPTS["perfil_sem_nome"])
    assert texto.count(CNPJ) == 1


def test_lista_longa_pede_o_maximo_e_nao_corta_nem_prioriza():
    with _conector() as cliente:
        texto = _texto(
            cliente,
            "lista_longa_de_compradores",
            PROMPTS["lista_longa_de_compradores"],
        )
    assert "`compradores_do_setor`" in texto
    assert f"`limite` {ferramentas.LIMITE_MAXIMO_DOS_COMPRADORES}" in texto
    assert "CNAE 62015 na UF MG nos últimos 5 anos" in texto
    assert "movimento passado" in texto and "intenção de compra" in texto
