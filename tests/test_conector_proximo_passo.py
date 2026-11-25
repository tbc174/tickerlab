"""O próximo passo no fim da resposta das ferramentas de lista (linha 984, item 2).

Riscos que estes testes pegam: (1) o texto citar ferramenta ou parâmetro que não existe, e a IA chamar
no vazio; (2) o rodapé trazer preço, promessa, recomendação, concorrente, pessoa ou o nome de quem usa o
conector; (3) o rodapé sumir ou se repetir; (4) ele passar a mudar o que a API entregou; (5) o erro de "não
disponível" deixar a IA sem saber o que fazer. Todo valor aqui é inventado.
"""

import inspect
import json
import re

import httpx
import pytest

from conector_remoto import ferramentas
from conector_remoto.pessoa import PALAVRAS_DE_PESSOA, exigir_sem_pessoa
from conector_remoto.proximo_passo import (
    CHAVE_DO_PROXIMO_PASSO,
    LISTA_DA_FERRAMENTA,
    PROXIMO_PASSO,
    QUANDO_VAZIA,
    SEM_CONSULTA,
    com_proximo_passo,
)
from tests import ajudantes_do_conector as aj

CHAVE = aj.CHAVE_DE_MENTIRA
CNPJ = "11111111000191"  # de mentira, com os dígitos verificadores certos
ITEM = {"cnpj": {"value": CNPJ}}
# a rota de cada ferramenta de lista e os argumentos mínimos do pedido
PEDIDOS = {
    "buscar_empresas": ("/companies", {}),
    "compradores_do_setor": ("/buyers", {"cnae": "6201500"}),
    "comparaveis": (f"/companies/{CNPJ}/comparables", {"cnpj": CNPJ}),
    "eventos": (f"/companies/{CNPJ}/events", {"cnpj": CNPJ}),
    "vinculos": (f"/companies/{CNPJ}/links", {"cnpj": CNPJ}),
    "setores": ("/sectors", {}),
}
PALAVRAS_PROIBIDAS = (
    "recomend",
    "garant",
    "promet",
    "r$",
    "preço",
    "preco",
    "gratuit",
    "melhor",
)


def _textos() -> list[tuple[str, str]]:
    return (
        [(f"proximo:{n}", t) for n, t in PROXIMO_PASSO.items()]
        + [(f"vazia:{n}", t) for n, t in QUANDO_VAZIA.items()]
        + [("vazia:eventos", SEM_CONSULTA)]
    )


def _chamar(ferramenta: str, corpo: dict) -> dict:
    caminho, argumentos = PEDIDOS[ferramenta]
    transporte = aj.api_de_mentira({caminho: httpx.Response(200, json=corpo)})
    with aj.conector(transporte) as cliente:
        return aj.chamar_ok(cliente, CHAVE, ferramenta, **argumentos)


def _parametros(cliente, ferramenta: str) -> set[str]:
    lista = aj.rpc(cliente, CHAVE, "tools/list").json()["result"]["tools"]
    (ferramenta_pedida,) = [f for f in lista if f["name"] == ferramenta]
    return set(ferramenta_pedida["inputSchema"].get("properties", {}))


# ---------------------------------------------------------------- o que cada ferramenta de lista faz


@pytest.mark.parametrize("ferramenta", sorted(LISTA_DA_FERRAMENTA))
def test_lista_com_itens_traz_o_proximo_passo_da_ferramenta(ferramenta):
    chave_da_lista = LISTA_DA_FERRAMENTA[ferramenta]
    saida = _chamar(ferramenta, {chave_da_lista: [ITEM], "limits": []})
    assert saida[CHAVE_DO_PROXIMO_PASSO] == PROXIMO_PASSO[ferramenta]
    assert saida[chave_da_lista] == [ITEM]  # o que a API entregou fica como veio


@pytest.mark.parametrize("ferramenta", sorted(LISTA_DA_FERRAMENTA))
def test_lista_vazia_diz_o_que_ficou_de_fora_do_pedido(ferramenta):
    chave_da_lista = LISTA_DA_FERRAMENTA[ferramenta]
    saida = _chamar(ferramenta, {chave_da_lista: []})
    assert saida[CHAVE_DO_PROXIMO_PASSO] == QUANDO_VAZIA[ferramenta]
    assert "não estime" in saida[CHAVE_DO_PROXIMO_PASSO]


def test_todo_texto_tem_o_par_de_vazio_ou_de_lista_cheia():
    assert set(PROXIMO_PASSO) == set(QUANDO_VAZIA) == set(LISTA_DA_FERRAMENTA)


def test_o_rodape_aparece_uma_vez_so_e_nao_se_sobrepoe_ao_da_api():
    corpo = {"companies": [ITEM], CHAVE_DO_PROXIMO_PASSO: "da API"}
    assert com_proximo_passo("buscar_empresas", corpo) == corpo
    saida = com_proximo_passo("buscar_empresas", {"companies": [ITEM]})
    assert json.dumps(saida).count(CHAVE_DO_PROXIMO_PASSO) == 1


@pytest.mark.parametrize(
    "corpo", [[ITEM], "texto", None, {"outra_chave": [ITEM]}, {"companies": "texto"}]
)
def test_corpo_de_outra_forma_passa_como_veio(corpo):
    assert com_proximo_passo("buscar_empresas", corpo) == corpo


def test_ferramenta_que_nao_e_de_lista_nao_ganha_rodape():
    corpo = {"companies": [ITEM]}
    assert com_proximo_passo("ficha_da_empresa", corpo) == corpo
    saida = _chamar_ficha()
    assert CHAVE_DO_PROXIMO_PASSO not in saida


def _chamar_ficha() -> dict:
    transporte = aj.api_de_mentira(
        {f"/companies/{CNPJ}": httpx.Response(200, json={"companies": [ITEM]})}
    )
    with aj.conector(transporte) as cliente:
        return aj.chamar_ok(cliente, CHAVE, "ficha_da_empresa", cnpj=CNPJ)


# ---------------------------------------------------------------- o que o texto pode dizer


@pytest.mark.parametrize(("nome", "texto"), _textos())
def test_texto_nao_tem_preco_promessa_recomendacao_nem_concorrente(nome, texto):
    baixo = texto.lower()
    assert not [p for p in PALAVRAS_PROIBIDAS if p in baixo], nome


@pytest.mark.parametrize(("nome", "texto"), _textos())
def test_texto_nao_fala_de_pessoa_e_passa_pela_tranca(nome, texto):
    palavras = set(re.findall(r"[a-zà-ú_]+", texto.lower()))
    assert not palavras & PALAVRAS_DE_PESSOA, nome
    exigir_sem_pessoa({"next_step": texto})
    assert "cpf" not in texto.lower() and "@" not in texto


@pytest.mark.parametrize(("nome", "texto"), _textos())
def test_texto_cita_so_ferramenta_e_parametro_que_existem(nome, texto):
    citados = set(re.findall(r"`([a-z_]+)`", texto))
    assert citados, nome
    ferramenta = nome.split(":")[1]
    transporte = aj.api_de_mentira({})
    with aj.conector(transporte) as cliente:
        da_ferramenta = _parametros(cliente, ferramenta)
        das_citadas = set()
        for citado in citados & set(ferramentas.CONJUNTOS_DA_FERRAMENTA):
            das_citadas |= _parametros(cliente, citado)
    nomes = set(ferramentas.CONJUNTOS_DA_FERRAMENTA)
    inexistentes = citados - nomes - da_ferramenta - das_citadas
    assert not inexistentes, (nome, inexistentes)


def test_toda_ferramenta_de_lista_existe_e_fala_de_uma_lista():
    assert set(LISTA_DA_FERRAMENTA) <= set(ferramentas.CONJUNTOS_DA_FERRAMENTA)


# ---------------------------------------------------------------- a tranca e o teto continuam valendo


def test_resposta_com_pessoa_continua_recusada_com_o_rodape_no_lugar():
    corpo = {"companies": [{"cnpj": CNPJ, "partners": [{"name": "x"}]}]}
    transporte = aj.api_de_mentira({"/companies": httpx.Response(200, json=corpo)})
    with aj.conector(transporte) as cliente:
        erro, texto = aj.chamar(cliente, CHAVE, "buscar_empresas")
    assert erro and CHAVE_DO_PROXIMO_PASSO not in texto


# ---------------------------------------------------------------- o erro que explica o que fazer


def test_nao_disponivel_aponta_o_que_posso_ver_e_pede_para_nao_estimar():
    transporte = aj.api_de_mentira({})
    with aj.conector(transporte) as cliente:
        erro, texto = aj.chamar(cliente, CHAVE, "ficha_da_empresa", cnpj=CNPJ)
    assert erro
    assert "o_que_posso_ver" in texto and "não estime" in texto
    assert "o_que_posso_ver" in ferramentas.CONJUNTOS_DA_FERRAMENTA


def test_o_chat_do_app_nao_ganha_o_rodape_porque_nao_tem_todas_as_ferramentas_citadas():
    padrao = (
        inspect.signature(ferramentas.registrar_ferramentas)
        .parameters["com_proximo_passo"]
        .default
    )
    assert padrao is False
    assert (
        inspect.signature(ferramentas.Pedidos).parameters["com_proximo_passo"].default
        is False
    )


@pytest.mark.parametrize(
    ("ferramenta", "campo"),
    [
        ("eventos", "unavailable_event_types"),
        ("vinculos", "unavailable_link_types"),
        ("compradores_do_setor", "unavailable_signals"),
        # linha 980, item (e): par vazio com número que a chave não vê (observação da revisão cruzada do #1253)
        ("comparaveis", "unavailable_figures"),
    ],
)
def test_lista_vazia_com_tipo_nao_consultado_nao_diz_que_a_base_nao_tem(
    ferramenta, campo
):
    saida = _chamar(
        ferramenta, {LISTA_DA_FERRAMENTA[ferramenta]: [], campo: ["auditor_change"]}
    )
    assert saida[CHAVE_DO_PROXIMO_PASSO] == SEM_CONSULTA
    assert "a base não tem" in SEM_CONSULTA and "não quer dizer" in SEM_CONSULTA
    assert "Nenhum" not in saida[CHAVE_DO_PROXIMO_PASSO]


def test_lista_com_itens_mantem_o_proximo_passo_mesmo_com_tipo_nao_consultado():
    saida = _chamar(
        "eventos", {"events": [ITEM], "unavailable_event_types": ["auditor_change"]}
    )
    assert saida[CHAVE_DO_PROXIMO_PASSO] == PROXIMO_PASSO["eventos"]


def test_aviso_de_nao_consultado_vazio_nao_conta():
    saida = _chamar("eventos", {"events": [], "unavailable_event_types": []})
    assert saida[CHAVE_DO_PROXIMO_PASSO] == QUANDO_VAZIA["eventos"]


def test_o_rodape_nao_faz_a_resposta_passar_do_teto(monkeypatch):
    corpo = {"companies": [{"texto": "x" * 200}]}
    monkeypatch.setattr(
        "conector_remoto.ferramentas.TETO_DE_CARACTERES",
        saida_tamanho(corpo) + 10,  # cabe sem o rodapé, não cabe com ele
    )
    transporte = aj.api_de_mentira({"/companies": httpx.Response(200, json=corpo)})
    with aj.conector(transporte) as cliente:
        erro, texto = aj.chamar(cliente, CHAVE, "buscar_empresas")
    assert erro and "grande demais" in texto


def saida_tamanho(corpo: dict) -> int:
    return len(json.dumps(corpo, ensure_ascii=False, separators=(",", ":")))
