"""As ferramentas do analista que só compõem o que a API já devolve (linha 980, onda 1).

Riscos que estes testes pegam: (1) a ferramenta aparecer, ou responder, para a chave que não vê o conjunto
dela; (2) uma organização receber o que é de outra (a chave de cada uma vai à API, e a API é quem decide);
(3) erro da API (404, 429, 5xx, API lenta) sair sem frase clara ou travar o conector; (4) pessoa física,
CPF, contato ou endereço passar pela tranca de saída; (5) descrição de ferramenta com preço, promessa ou
instrução. Todo CNPJ e todo valor aqui é inventado.
"""

import json
import time

import httpx
import pytest

from conector_remoto import ferramentas, ferramentas_do_analista, saida
from conector_remoto.configuracao import TEMPO_LIMITE_DA_API_S
from src.api_externa.conjuntos import credito
from tests import ajudantes_do_conector as aj
from tests.ajudantes_de_cpf import cpf_que_confere, formatado

EMPRESA = "11222333000181"
OUTRA_EMPRESA = "99888777000100"
CHAVE_A = aj.CHAVE_DE_MENTIRA
CHAVE_B = "tld_bcdefghi_" + "B" * 43
# os conjuntos de uma organização que só olha o cadastro, e a de uma que também vê o crédito
SEM_CREDITO = ("profiles", "companies", "events")
COM_CREDITO = (*SEM_CREDITO, credito.CONJUNTO)


def _fato(valor: object, fonte: str, publico_em: str) -> dict:
    return {
        "value": valor,
        "source": fonte,
        "published_at": publico_em,
        "observed_at": None,
    }


def _corpo_do_credito(**extra) -> dict:
    return {
        "cnpj": EMPRESA,
        "known_at": "2026-11-10",
        "rfb_registration_status": _fato("Ativa", "rfb-cnpj", "2026-10-01"),
        "fidcs_as_assignor": _fato(2, "cvm-fidc", "2026-10-15"),
        "limits": list(credito.LIMITES),
    } | extra


def _api(
    rotas: dict[str, httpx.Response],
    catalogos: dict[str, tuple[str, ...]],
    pedidos: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    """Um dublê da API com uma chave por organização: cada uma tem o catálogo dela e as rotas dela."""

    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedidos is not None:
            pedidos.append(pedido)
        chave = pedido.headers.get("authorization", "").removeprefix("Bearer ")
        if chave not in catalogos:
            return httpx.Response(401, json={"detail": "invalid_api_key"})
        if pedido.url.path == "/data/v1/catalog":
            conjuntos = [{"dataset": c} for c in catalogos[chave]]
            return httpx.Response(200, json={"datasets": conjuntos, "sources": []})
        caminho = pedido.url.path.removeprefix("/data/v1")
        return rotas.get(
            f"{chave}:{caminho}", httpx.Response(404, json={"detail": "not_available"})
        )

    return httpx.MockTransport(responder)


def _api_do_credito(
    corpo: object = None, status: int = 200, pedidos=None, **cabecalhos
) -> httpx.MockTransport:
    """A API de uma organização só (a chave A) que vê o crédito e responde `corpo` na rota `/credit`."""
    resposta = httpx.Response(
        status, json=_corpo_do_credito() if corpo is None else corpo, headers=cabecalhos
    )
    return _api(
        {f"{CHAVE_A}:/credit/{EMPRESA}": resposta},
        {CHAVE_A: COM_CREDITO},
        pedidos,
    )


def _pediu_o_credito(pedidos: list[httpx.Request]) -> bool:
    return any("/credit/" in p.url.path for p in pedidos)


# ---------------------------------------------------------------- a ligação com ferramentas.py


def test_o_conjunto_da_ferramenta_e_o_da_rota_de_credito():
    assert ferramentas.CONJUNTOS_DA_FERRAMENTA["credito_da_empresa"] == frozenset(
        {credito.CONJUNTO}
    )


def test_a_ferramenta_tem_titulo_no_lugar_de_todos():
    assert ferramentas.TITULOS_DAS_FERRAMENTAS["credito_da_empresa"]
    assert hasattr(ferramentas_do_analista, "registrar")


# ---------------------------------------------------------------- quem vê a ferramenta


def test_sem_o_conjunto_credit_a_ferramenta_nao_aparece_nem_responde():
    pedidos: list[httpx.Request] = []
    transporte = _api(
        {f"{CHAVE_A}:/credit/{EMPRESA}": httpx.Response(200, json=_corpo_do_credito())},
        {CHAVE_A: SEM_CREDITO},
        pedidos,
    )
    with aj.conector(transporte) as cliente:
        assert "credito_da_empresa" not in aj.nomes_das_ferramentas(cliente, CHAVE_A)
        erro, texto = aj.chamar(cliente, CHAVE_A, "credito_da_empresa", cnpj=EMPRESA)
    assert erro and texto == ferramentas.MENSAGEM_NAO_LIBERADA
    assert not _pediu_o_credito(pedidos)


def test_com_o_conjunto_credit_a_ferramenta_entrega_os_fatos_com_fonte_e_data():
    pedidos: list[httpx.Request] = []
    with aj.conector(_api_do_credito(pedidos=pedidos)) as cliente:
        assert "credito_da_empresa" in aj.nomes_das_ferramentas(cliente, CHAVE_A)
        corpo = aj.chamar_ok(
            cliente, CHAVE_A, "credito_da_empresa", cnpj="11.222.333/0001-81"
        )
    assert corpo == _corpo_do_credito()
    assert corpo["fidcs_as_assignor"]["source"] == "cvm-fidc"
    assert corpo["fidcs_as_assignor"]["published_at"] == "2026-10-15"
    (pedido,) = [p for p in pedidos if "/credit/" in p.url.path]
    assert pedido.url.path == f"/data/v1/credit/{EMPRESA}"
    assert "known_at" not in pedido.url.params


def test_como_era_em_vai_para_a_api_como_known_at():
    pedidos: list[httpx.Request] = []
    with aj.conector(_api_do_credito(pedidos=pedidos)) as cliente:
        aj.chamar_ok(
            cliente,
            CHAVE_A,
            "credito_da_empresa",
            cnpj=EMPRESA,
            como_era_em="2026-06-30",
        )
    (pedido,) = [p for p in pedidos if "/credit/" in p.url.path]
    assert pedido.url.params["known_at"] == "2026-06-30"


def test_a_ferramenta_so_pede_cnpj_e_nao_chama_a_api_com_cpf():
    pedidos: list[httpx.Request] = []
    with aj.conector(_api_do_credito(pedidos=pedidos)) as cliente:
        erro, texto = aj.chamar(
            cliente,
            CHAVE_A,
            "credito_da_empresa",
            cnpj=formatado(cpf_que_confere("888654321")),
        )
    assert erro and "nunca CPF" in texto
    assert not _pediu_o_credito(pedidos)


# ---------------------------------------------------------------- duas organizações


def test_duas_organizacoes_nao_veem_o_que_e_da_outra():
    """A é a única com o conjunto e com a rota; a chave de B nunca recebe o que a de A recebe."""
    pedidos: list[httpx.Request] = []
    transporte = _api(
        {f"{CHAVE_A}:/credit/{EMPRESA}": httpx.Response(200, json=_corpo_do_credito())},
        {CHAVE_A: COM_CREDITO, CHAVE_B: SEM_CREDITO},
        pedidos,
    )
    with aj.conector(transporte) as cliente:
        da_a = aj.chamar_ok(cliente, CHAVE_A, "credito_da_empresa", cnpj=EMPRESA)
        nomes_de_b = aj.nomes_das_ferramentas(cliente, CHAVE_B)
        erro, texto = aj.chamar(cliente, CHAVE_B, "credito_da_empresa", cnpj=EMPRESA)
    assert da_a == _corpo_do_credito()
    assert "credito_da_empresa" not in nomes_de_b
    assert erro and "cvm-fidc" not in texto and "Ativa" not in texto
    # o pedido de cada uma levou a chave dela, e a de B nunca chegou à rota de crédito
    de_b = [p for p in pedidos if p.headers["authorization"] == f"Bearer {CHAVE_B}"]
    assert not _pediu_o_credito(de_b)


def test_a_organizacao_com_o_conjunto_mas_sem_o_dado_recebe_o_nao_disponivel():
    """A API nega com o mesmo 404 o dado que não existe e o que a organização não pode ver."""
    transporte = _api({}, {CHAVE_A: COM_CREDITO})
    with aj.conector(transporte) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE_A, "credito_da_empresa", cnpj=OUTRA_EMPRESA
        )
    assert erro and "Não disponível" in texto


# ---------------------------------------------------------------- erros da API


@pytest.mark.parametrize(
    ("status", "cabecalhos", "corpo", "frase"),
    [
        (404, {}, {"detail": "not_available"}, "Não disponível"),
        (
            429,
            {"Retry-After": "17"},
            {"detail": "rate_limited"},
            "tente de novo em 17 s",
        ),
        (429, {}, {"detail": "monthly_quota"}, "quota de pedidos do mês"),
        (401, {}, {"detail": "invalid_api_key"}, "chave foi recusada"),
        (422, {}, {"detail": "invalid"}, "formato errado"),
        (503, {}, {"detail": "unavailable"}, "fora do ar"),
        (500, {}, {"detail": "boom"}, "erro inesperado (status 500)"),
    ],
)
def test_erro_da_api_vira_frase_clara_em_portugues(status, cabecalhos, corpo, frase):
    with aj.conector(_api_do_credito(corpo, status, **cabecalhos)) as cliente:
        erro, texto = aj.chamar(cliente, CHAVE_A, "credito_da_empresa", cnpj=EMPRESA)
    assert erro and frase in texto
    assert CHAVE_A not in texto and "Traceback" not in texto


def test_api_lenta_nao_trava_o_conector_e_devolve_a_frase_de_sempre():
    """O cliente da API para no limite do conector: ao estourá-lo, a IA recebe a frase, não um silêncio."""

    def lenta(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path.endswith("/catalog"):
            return httpx.Response(
                200, json={"datasets": [{"dataset": c} for c in COM_CREDITO]}
            )
        raise httpx.ReadTimeout("a API demorou", request=pedido)

    inicio = time.perf_counter()
    with aj.conector(httpx.MockTransport(lenta)) as cliente:
        erro, texto = aj.chamar(cliente, CHAVE_A, "credito_da_empresa", cnpj=EMPRESA)
    assert erro and "não respondeu" in texto
    assert time.perf_counter() - inicio < TEMPO_LIMITE_DA_API_S


# ---------------------------------------------------------------- a tranca de saída


@pytest.mark.parametrize(
    "sujo",
    [
        _corpo_do_credito(cpf="x"),
        _corpo_do_credito(partners=[{"name": "FULANA EXEMPLO"}]),
        _corpo_do_credito(
            limits=[f"titular {formatado(cpf_que_confere('888654321'))}"]
        ),
        _corpo_do_credito(contact="fulana@exemplo.invalid"),
    ],
    ids=["chave de CPF", "sócio", "CPF no texto", "e-mail"],
)
def test_resposta_com_pessoa_e_recusada_inteira_sem_repetir_o_valor(sujo):
    with aj.conector(_api_do_credito(sujo)) as cliente:
        erro, texto = aj.chamar(cliente, CHAVE_A, "credito_da_empresa", cnpj=EMPRESA)
    assert erro and ferramentas.MENSAGEM_DE_PESSOA in texto
    assert "FULANA" not in texto and "exemplo.invalid" not in texto
    assert "888654321" not in texto


def test_o_que_a_ferramenta_entrega_nao_tem_pessoa_nem_nota_de_credito():
    with aj.conector(_api_do_credito()) as cliente:
        texto = json.dumps(
            aj.chamar_ok(cliente, CHAVE_A, "credito_da_empresa", cnpj=EMPRESA)
        )
    for proibida in ("rating", "score", "eligib", "partners", "cpf"):
        assert proibida not in texto.lower()


def test_resposta_acima_do_teto_vira_frase_clara_e_nao_corta_o_dado_no_meio():
    gigante = _corpo_do_credito(limits=["x" * (saida.TETO_DE_CARACTERES + 1)])
    with aj.conector(_api_do_credito(gigante)) as cliente:
        erro, texto = aj.chamar(cliente, CHAVE_A, "credito_da_empresa", cnpj=EMPRESA)
    assert erro and "grande demais" in texto
    assert len(texto) < 1_000


# ---------------------------------------------------------------- o texto que o analista lê


def _descricoes_das_ferramentas_novas() -> dict[str, str]:
    novas = {"credito_da_empresa"}
    with aj.conector(_api_do_credito()) as cliente:
        lista = aj.rpc(cliente, CHAVE_A, "tools/list").json()["result"]["tools"]
    return {f["name"]: f["description"] for f in lista if f["name"] in novas}


def test_descricao_diz_o_que_devolve_e_o_que_nao_traz_sem_preco_nem_promessa():
    descricoes = _descricoes_das_ferramentas_novas()
    assert descricoes
    for nome, descricao in descricoes.items():
        for parte in ("Serve para", "Fonte:", "Não traz:"):
            assert descricao.count(parte) == 1, (nome, parte)
        for vedada in ("recomend", "preço", "garant", "promet", "R$"):
            assert vedada not in descricao.lower(), (nome, vedada)


def test_a_descricao_do_credito_diz_o_que_a_rota_nao_traz():
    descricao = _descricoes_das_ferramentas_novas()["credito_da_empresa"]
    nao_traz = descricao.split("Não traz:")[1]
    for ausente in ("rating", "elegibilidade", "SCR"):
        assert ausente in nao_traz
