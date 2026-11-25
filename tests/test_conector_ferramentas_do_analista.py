"""As ferramentas do analista que só compõem o que a API já devolve (linha 980, onda 1).

Riscos que estes testes pegam: (1) a ferramenta aparecer, ou responder, para a chave que não vê o conjunto
dela; (2) uma organização receber o que é de outra (a chave de cada uma vai à API, e a API é quem decide);
(3) erro da API (404, 429, 5xx, API lenta) sair sem frase clara ou travar o conector; (4) pessoa física,
CPF, contato ou endereço passar pela tranca de saída; (5) descrição de ferramenta com preço, promessa ou
instrução. Todo CNPJ e todo valor aqui é inventado.
"""

import asyncio
import json
import time
from datetime import UTC, datetime

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
    novas = {"credito_da_empresa", "o_que_mudou", "comparar_empresas"}
    catalogo = {CHAVE_A: (*TODOS_OS_BLOCOS, credito.CONJUNTO)}
    with aj.conector(_api_do_historico(catalogos=catalogo)) as cliente:
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


# ================================================================ o_que_mudou
#
# Compara o que a API devolvia com `known_at = desde` e o que devolve hoje, nos três blocos que a chave vê
# (cadastro, vínculos e eventos), e lista só a diferença, cada item com a fonte e o dia em que ficou público.

DESDE = "2026-01-01"
HOJE = "2026-11-10"
TODOS_OS_BLOCOS = ("profiles", "companies", "links", "events")
CAMINHO_DA_FICHA = f"/companies/{EMPRESA}/profile"
CAMINHO_DOS_VINCULOS = f"/companies/{EMPRESA}/links"
CAMINHO_DOS_EVENTOS = f"/companies/{EMPRESA}/events"


def _ficha(nome: str, dia_do_nome: str, **extra) -> dict:
    return {
        "cnpj": EMPRESA,
        "known_at": HOJE,
        "registration": {
            "legal_name": _fato(nome, "rfb-cnpj", dia_do_nome),
            # igual nos dois dias, mas republicado: o dia muda e o valor não, então não é mudança
            "registration_status": _fato(
                "ativa", "rfb-cnpj", extra.pop("dia", "2025-12-01")
            ),
        },
        "periodic_filings": extra.pop("entregas", []),
        "limits": [{"code": "so_pj", "text": "Só pessoa jurídica."}],
        "sources": [{"source": "rfb-cnpj", "license": "CC BY"}],
    }


def _ponta(raiz: str, retrato: str = "2025-12") -> dict:
    """Uma ponta do vínculo como a API a devolve: o nome e o mês do retrato da Receita, cada um com o seu envelope."""
    return {
        "entity_id": f"E{raiz}",
        "cnpj_root": raiz,
        "legal_name": _fato(f"EMPRESA {raiz}", "rfb-cnpj", "2025-12-31"),
        "registry_snapshot_month": _fato(retrato, "rfb-cnpj", "2025-12-31"),
    }


def _vinculo(
    raiz: str, participacao: float, dia: str, retrato: str = "2025-12"
) -> dict:
    """Um vínculo no formato real da rota `/links`: `kind` e `valid_from` com envelope do FRE."""
    return {
        "hops": 1,
        "kind": _fato("subsidiary_of", "cvm-hist-fre", dia),
        "from": _ponta("11222333", retrato),
        "to": _ponta(raiz, retrato),
        "ownership_pct": _fato(participacao, "cvm-hist-fre", dia),
        "valid_from": _fato("2018-12-31", "cvm-hist-fre", dia),
    }


def _evento(protocolo: str, dia: str) -> dict:
    return {
        "event_type": "ipe_filing",
        "filing_id": _fato(protocolo, "cvm-hist-ipe", dia),
        "category": _fato("Fato Relevante", "cvm-hist-ipe", dia),
    }


def _vinculos(*itens: dict) -> dict:
    return {
        "known_at": HOJE,
        "links": list(itens),
        "limits": [
            {"code": "so_companhia_aberta", "text": "Controle: só companhia aberta."}
        ],
        "sources": [{"source": "cvm-fre", "license": "CC BY"}],
    }


def _eventos(*itens: dict, truncado: bool = False) -> dict:
    return {
        "known_at": HOJE,
        "events": list(itens),
        "truncated": truncado,
        "sources": [{"source": "cvm-hist-ipe", "license": "CC BY"}],
    }


def _como_hoje() -> dict[str, dict]:
    return {
        CAMINHO_DA_FICHA: _ficha("ALFA S.A. NOVA", "2026-08-01"),
        CAMINHO_DOS_VINCULOS: _vinculos(
            _vinculo("55555555", 60.0, "2026-05-31"),
            _vinculo("77777777", 25.0, "2026-06-30"),
        ),
        CAMINHO_DOS_EVENTOS: _eventos(
            _evento("P3", "2026-10-02"),
            _evento("P2", "2026-03-15"),
            _evento("P1", "2025-12-20"),
        ),
    }


def _como_era() -> dict[str, dict]:
    """O que a base sabia em `DESDE`: a mesma empresa, com o nome antigo, uma participação menor e um evento."""
    return {
        CAMINHO_DA_FICHA: _ficha("ALFA S.A.", "2025-03-10"),
        CAMINHO_DOS_VINCULOS: _vinculos(_vinculo("55555555", 40.0, "2025-05-31")),
        CAMINHO_DOS_EVENTOS: _eventos(_evento("P1", "2025-12-20")),
    }


def _api_do_historico(
    hoje: dict[str, dict] | None = None,
    era: dict[str, dict] | None = None,
    catalogos: dict[str, tuple[str, ...]] | None = None,
    pedidos: list[httpx.Request] | None = None,
    vaza: bool = False,
) -> httpx.MockTransport:
    """A API de mentira com memória: com `known_at` responde `era`, sem ele responde `hoje`. Com `vaza`, ignora
    o `known_at` (a falha que o conector não pode deixar passar: dado do futuro no retrato do passado)."""
    hoje = _como_hoje() if hoje is None else hoje
    era = _como_era() if era is None else era
    catalogos = {CHAVE_A: TODOS_OS_BLOCOS} if catalogos is None else catalogos

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
        no_passado = "known_at" in pedido.url.params and not vaza
        corpo = (era if no_passado else hoje).get(caminho)
        if corpo is None:
            return httpx.Response(404, json={"detail": "not_available"})
        return httpx.Response(200, json=corpo)

    return httpx.MockTransport(responder)


def _o_que_mudou(cliente, chave=CHAVE_A, **argumentos):
    return aj.chamar_ok(
        cliente, chave, "o_que_mudou", cnpj=EMPRESA, desde=DESDE, **argumentos
    )


def _campos(entradas: list[dict]) -> set[str]:
    return {e["field"] for e in entradas}


def _protocolos(entradas: list[dict]) -> set[str]:
    return {e["item"]["filing_id"]["value"] for e in entradas}


# ---------------------------------------------------------------- a ligação com ferramentas.py


def test_o_que_mudou_aparece_para_quem_ve_o_cadastro_os_vinculos_ou_os_eventos():
    assert ferramentas.CONJUNTOS_DA_FERRAMENTA["o_que_mudou"] == frozenset(
        TODOS_OS_BLOCOS
    )
    assert ferramentas.TITULOS_DAS_FERRAMENTAS["o_que_mudou"]


# ---------------------------------------------------------------- quem vê a ferramenta


def test_sem_nenhum_dos_conjuntos_a_ferramenta_nao_aparece_nem_responde():
    pedidos: list[httpx.Request] = []
    transporte = _api_do_historico(
        catalogos={CHAVE_A: ("credit", "buyers")}, pedidos=pedidos
    )
    with aj.conector(transporte) as cliente:
        assert "o_que_mudou" not in aj.nomes_das_ferramentas(cliente, CHAVE_A)
        erro, texto = aj.chamar(
            cliente, CHAVE_A, "o_que_mudou", cnpj=EMPRESA, desde=DESDE
        )
    assert erro and texto == ferramentas.MENSAGEM_NAO_LIBERADA
    assert not [p for p in pedidos if "/companies/" in p.url.path]


def test_com_so_um_dos_conjuntos_consulta_so_aquele_bloco_e_diz_o_que_nao_viu():
    pedidos: list[httpx.Request] = []
    transporte = _api_do_historico(catalogos={CHAVE_A: ("events",)}, pedidos=pedidos)
    with aj.conector(transporte) as cliente:
        corpo = _o_que_mudou(cliente)
    consultados = {
        p.url.path.removeprefix("/data/v1")
        for p in pedidos
        if "/companies/" in p.url.path
    }
    assert consultados == {CAMINHO_DOS_EVENTOS}
    assert _protocolos(corpo["events"]["added"]) == {"P2", "P3"}
    assert {b["block"] for b in corpo["not_consulted"]} == {"registration", "links"}
    assert "registration" not in corpo and "links" not in corpo


# ---------------------------------------------------------------- o que a ferramenta entrega


def test_lista_so_o_que_mudou_com_o_antes_o_depois_a_fonte_e_o_dia():
    with aj.conector(_api_do_historico()) as cliente:
        corpo = _o_que_mudou(cliente)
    assert corpo["cnpj"] == EMPRESA
    assert corpo["since"] == DESDE and corpo["until"] == HOJE
    cadastro = corpo["registration"]
    # o nome mudou; a situação foi republicada com o mesmo valor, então fica de fora
    assert _campos(cadastro["changed"]) == {"legal_name"}
    (nome,) = cadastro["changed"]
    assert nome["before"] == _fato("ALFA S.A.", "rfb-cnpj", "2025-03-10")
    assert nome["after"] == _fato("ALFA S.A. NOVA", "rfb-cnpj", "2026-08-01")
    assert cadastro["added"] == [] and cadastro["removed"] == []


def test_vinculo_novo_e_vinculo_que_mudou_de_participacao_aparecem_cada_um_no_seu_lugar():
    with aj.conector(_api_do_historico()) as cliente:
        corpo = _o_que_mudou(cliente)
    vinculos = corpo["links"]
    (novo,) = vinculos["added"]
    assert novo["item"]["to"]["cnpj_root"] == "77777777"
    assert novo["item"]["ownership_pct"]["published_at"] == "2026-06-30"
    (mudou,) = vinculos["changed"]
    assert mudou["before"]["ownership_pct"]["value"] == 40.0
    assert mudou["after"]["ownership_pct"]["value"] == 60.0
    assert vinculos["removed"] == []


def test_evento_que_ja_era_conhecido_nao_aparece_so_os_novos_com_o_dia_em_que_ficaram_publicos():
    with aj.conector(_api_do_historico()) as cliente:
        corpo = _o_que_mudou(cliente)
    eventos = corpo["events"]
    assert _protocolos(eventos["added"]) == {"P2", "P3"}
    assert {e["item"]["filing_id"]["published_at"] for e in eventos["added"]} == {
        "2026-03-15",
        "2026-10-02",
    }
    assert eventos["removed"] == [] and eventos["changed"] == []


def test_o_que_saiu_da_base_aparece_em_removed():
    hoje = _como_hoje() | {CAMINHO_DOS_VINCULOS: _vinculos()}
    with aj.conector(_api_do_historico(hoje=hoje)) as cliente:
        corpo = _o_que_mudou(cliente)
    (saiu,) = corpo["links"]["removed"]
    assert saiu["item"]["to"]["cnpj_root"] == "55555555"


def test_quando_nada_mudou_diz_isso_em_vez_de_devolver_listas_vazias_soltas():
    with aj.conector(_api_do_historico(hoje=_como_era())) as cliente:
        corpo = _o_que_mudou(cliente)
    assert corpo["changes_found"] == 0
    for bloco in ("registration", "links", "events"):
        assert corpo[bloco] == {"changed": [], "added": [], "removed": []}


def test_conta_as_mudancas_achadas_e_repete_as_fontes_e_os_avisos_da_api():
    with aj.conector(_api_do_historico()) as cliente:
        corpo = _o_que_mudou(cliente)
    assert (
        corpo["changes_found"] == 1 + 2 + 2
    )  # nome; vínculo novo e vínculo alterado; dois eventos
    assert {f["source"] for f in corpo["sources"]} == {
        "rfb-cnpj",
        "cvm-fre",
        "cvm-hist-ipe",
    }
    textos = {limite["code"] for limite in corpo["limits"]}
    assert {"so_pj", "so_companhia_aberta", "o_que_mudou"} <= textos


def test_a_empresa_que_ainda_nao_existia_na_base_no_dia_tem_tudo_como_novo_e_o_aviso():
    era = {
        CAMINHO_DOS_EVENTOS: _eventos()
    }  # sem cadastro nem vínculos em `DESDE`: 404 do lado antigo
    with aj.conector(_api_do_historico(era=era)) as cliente:
        corpo = _o_que_mudou(cliente)
    assert corpo["registration"]["before_not_available"] is True
    assert _campos(corpo["registration"]["added"]) == {
        "legal_name",
        "registration_status",
    }
    assert corpo["links"]["before_not_available"] is True
    assert "before_not_available" not in corpo["events"]


def test_a_pagina_cheia_de_eventos_vem_marcada_como_parcial():
    hoje = _como_hoje() | {
        CAMINHO_DOS_EVENTOS: _eventos(_evento("P9", "2026-10-02"), truncado=True)
    }
    with aj.conector(_api_do_historico(hoje=hoje)) as cliente:
        corpo = _o_que_mudou(cliente)
    assert corpo["events"]["partial"] is True
    assert "partial" not in corpo["links"]


# ---------------------------------------------------------------- o que vai à API


def test_o_lado_antigo_pede_known_at_e_o_de_hoje_nao_e_o_cnpj_vai_sem_pontuacao():
    pedidos: list[httpx.Request] = []
    with aj.conector(_api_do_historico(pedidos=pedidos)) as cliente:
        aj.chamar_ok(
            cliente, CHAVE_A, "o_que_mudou", cnpj="11.222.333/0001-81", desde=DESDE
        )
    do_cnpj = [p for p in pedidos if f"/companies/{EMPRESA}" in p.url.path]
    assert len(do_cnpj) == 6  # três blocos, cada um nos dois dias
    antigos = [p for p in do_cnpj if "known_at" in p.url.params]
    atuais = [p for p in do_cnpj if "known_at" not in p.url.params]
    assert len(antigos) == len(atuais) == 3
    assert {p.url.params["known_at"] for p in antigos} == {DESDE}
    eventos = [p for p in do_cnpj if p.url.path.endswith("/events")]
    assert {p.url.params["limit"] for p in eventos} == {"100"}


@pytest.mark.parametrize("desde", ["2099-01-01", "hoje", "01/01/2026"])
def test_data_invalida_ou_futura_e_recusada_sem_chamar_a_api(desde):
    pedidos: list[httpx.Request] = []
    with aj.conector(_api_do_historico(pedidos=pedidos)) as cliente:
        erro, _ = aj.chamar(cliente, CHAVE_A, "o_que_mudou", cnpj=EMPRESA, desde=desde)
    assert erro
    assert not [p for p in pedidos if "/companies/" in p.url.path]


def test_desde_hoje_ou_depois_nao_tem_o_que_comparar_e_diz_isso():
    hoje = datetime.now(UTC).date().isoformat()
    with aj.conector(_api_do_historico()) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE_A, "o_que_mudou", cnpj=EMPRESA, desde=hoje
        )
    assert erro and "anterior a hoje" in texto


def test_o_que_mudou_so_pede_cnpj_e_nao_chama_a_api_com_cpf():
    pedidos: list[httpx.Request] = []
    with aj.conector(_api_do_historico(pedidos=pedidos)) as cliente:
        erro, texto = aj.chamar(
            cliente,
            CHAVE_A,
            "o_que_mudou",
            cnpj=formatado(cpf_que_confere("888654321")),
            desde=DESDE,
        )
    assert erro and "nunca CPF" in texto
    assert not [p for p in pedidos if "/companies/" in p.url.path]


# ---------------------------------------------------------------- sem olhar o futuro


def _datas_publicas(no: object) -> list[str]:
    if isinstance(no, dict):
        achadas = (
            [no["published_at"]] if isinstance(no.get("published_at"), str) else []
        )
        return achadas + [d for filho in no.values() for d in _datas_publicas(filho)]
    if isinstance(no, list):
        return [d for filho in no for d in _datas_publicas(filho)]
    return []


def _o_lado_antigo(corpo: dict) -> list[object]:
    """Tudo o que a resposta põe como `before` ou como `removed`: o que a base sabia em `desde`."""
    antigos: list[object] = []
    for bloco in ("registration", "links", "events"):
        antigos.extend(entrada["before"] for entrada in corpo[bloco]["changed"])
        antigos.extend(
            entrada.get("before", entrada.get("item"))
            for entrada in corpo[bloco]["removed"]
        )
    return antigos


def test_o_lado_antigo_nao_traz_nada_publicado_depois_de_desde():
    with aj.conector(_api_do_historico()) as cliente:
        corpo = _o_que_mudou(cliente)
    assert _o_lado_antigo(corpo)
    assert max(_datas_publicas(_o_lado_antigo(corpo))) <= DESDE


def test_mesmo_se_a_api_vazasse_o_futuro_a_ferramenta_corta_o_lado_antigo_no_dia_pedido():
    """A API de mentira ignora o `known_at` e devolve o de hoje dos dois lados. O lado antigo só pode ficar
    com o que já era público em `desde`: o resto é novo, nunca 'o que já havia'."""
    with aj.conector(_api_do_historico(vaza=True)) as cliente:
        corpo = _o_que_mudou(cliente)
    antigos = _o_lado_antigo(corpo)
    assert max([*_datas_publicas(antigos), "0000-00-00"]) <= DESDE
    # o que só ficou público depois de `desde` entra como novo, não some nem vira 'já havia'
    assert _protocolos(corpo["events"]["added"]) == {"P2", "P3"}
    assert corpo["events"]["removed"] == []
    assert "to" in corpo["links"]["added"][0]["item"]


def test_o_cadastro_republicado_depois_de_desde_nao_conta_como_valor_antigo():
    """O nome que só ficou público em 2026-08 não pode ser o `before` de ninguém."""
    with aj.conector(_api_do_historico(vaza=True)) as cliente:
        corpo = _o_que_mudou(cliente)
    assert corpo["registration"]["changed"] == []
    assert _campos(corpo["registration"]["added"]) == {"legal_name"}


# ---------------------------------------------------------------- duas organizações


def test_duas_organizacoes_cada_uma_ve_so_os_blocos_do_catalogo_da_sua_chave():
    pedidos: list[httpx.Request] = []
    catalogos = {CHAVE_A: TODOS_OS_BLOCOS, CHAVE_B: ("credit",)}
    with aj.conector(
        _api_do_historico(catalogos=catalogos, pedidos=pedidos)
    ) as cliente:
        da_a = _o_que_mudou(cliente, CHAVE_A)
        nomes_de_b = aj.nomes_das_ferramentas(cliente, CHAVE_B)
        erro, texto = aj.chamar(
            cliente, CHAVE_B, "o_que_mudou", cnpj=EMPRESA, desde=DESDE
        )
    assert da_a["changes_found"] == 5
    assert "o_que_mudou" not in nomes_de_b
    assert erro and "ALFA" not in texto and "P3" not in texto
    de_b = [p for p in pedidos if p.headers["authorization"] == f"Bearer {CHAVE_B}"]
    assert not [p for p in de_b if "/companies/" in p.url.path]


def test_a_chave_que_ve_so_o_cadastro_nao_recebe_vinculos_nem_eventos():
    with aj.conector(_api_do_historico(catalogos={CHAVE_B: ("profiles",)})) as cliente:
        corpo = _o_que_mudou(cliente, CHAVE_B)
    assert "links" not in corpo and "events" not in corpo
    assert {b["block"] for b in corpo["not_consulted"]} == {"links", "events"}


# ---------------------------------------------------------------- erros da API


def test_bloco_que_a_api_nao_serve_vai_para_not_consulted_e_os_outros_seguem():
    hoje, era = _como_hoje(), _como_era()
    del hoje[CAMINHO_DOS_EVENTOS], era[CAMINHO_DOS_EVENTOS]
    with aj.conector(_api_do_historico(hoje=hoje, era=era)) as cliente:
        corpo = _o_que_mudou(cliente)
    assert "events" not in corpo
    (evento,) = [b for b in corpo["not_consulted"] if b["block"] == "events"]
    assert evento["reason"] == "not_available"
    assert corpo["registration"]["changed"]


def test_bloco_que_a_base_servia_em_desde_e_hoje_nao_serve_tem_tudo_em_removed_e_o_aviso():
    hoje = _como_hoje()
    del hoje[CAMINHO_DOS_VINCULOS]
    with aj.conector(_api_do_historico(hoje=hoje)) as cliente:
        corpo = _o_que_mudou(cliente)
    assert corpo["links"]["after_not_available"] is True
    assert len(corpo["links"]["removed"]) == 1 and corpo["links"]["added"] == []


def test_cadastro_que_so_existe_no_conjunto_companies_entra_pelo_caminho_de_reserva():
    """Sem `profiles` a ficha vem de `/companies/{cnpj}`, e o cadastro plano é comparado do mesmo jeito."""

    def plano(nome: str) -> dict:
        return {
            "cnpj": EMPRESA,
            "known_at": HOJE,
            "legal_name": _fato(nome, "rfb-cnpj", "2025-03-10"),
        }

    hoje = {f"/companies/{EMPRESA}": plano("ALFA S.A. NOVA")}
    era = {f"/companies/{EMPRESA}": plano("ALFA S.A.")}
    transporte = _api_do_historico(
        hoje=hoje, era=era, catalogos={CHAVE_A: ("companies",)}
    )
    with aj.conector(transporte) as cliente:
        corpo = _o_que_mudou(cliente)
    assert _campos(corpo["registration"]["changed"]) == {"legal_name"}


def test_empresa_que_nenhum_bloco_serve_recebe_o_nao_disponivel_de_sempre():
    with aj.conector(_api_do_historico(hoje={}, era={})) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE_A, "o_que_mudou", cnpj=OUTRA_EMPRESA, desde=DESDE
        )
    assert erro and "Não disponível" in texto


def _api_que_so_responde(status: int, corpo: dict, **cabecalhos) -> httpx.MockTransport:
    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path == "/data/v1/catalog":
            conjuntos = [{"dataset": c} for c in TODOS_OS_BLOCOS]
            return httpx.Response(200, json={"datasets": conjuntos, "sources": []})
        return httpx.Response(status, json=corpo, headers=cabecalhos)

    return httpx.MockTransport(responder)


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
def test_erro_da_api_do_o_que_mudou_vira_frase_clara_em_portugues(
    status, cabecalhos, corpo, frase
):
    with aj.conector(_api_que_so_responde(status, corpo, **cabecalhos)) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE_A, "o_que_mudou", cnpj=EMPRESA, desde=DESDE
        )
    assert erro and frase in texto
    assert CHAVE_A not in texto and "Traceback" not in texto


def test_erro_de_um_bloco_que_nao_e_404_derruba_a_resposta_inteira_em_vez_de_entregar_pela_metade():
    """Cadastro e eventos respondem; os vínculos dão 429. Entregar 'o que mudou' sem esse bloco, calado,
    seria dizer que os vínculos não mudaram: a ferramenta para e diz o motivo."""

    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path == "/data/v1/catalog":
            conjuntos = [{"dataset": c} for c in TODOS_OS_BLOCOS]
            return httpx.Response(200, json={"datasets": conjuntos, "sources": []})
        if pedido.url.path.endswith("/links"):
            return httpx.Response(
                429, json={"detail": "rate_limited"}, headers={"Retry-After": "9"}
            )
        no_passado = "known_at" in pedido.url.params
        corpos = _como_era() if no_passado else _como_hoje()
        return httpx.Response(
            200, json=corpos[pedido.url.path.removeprefix("/data/v1")]
        )

    with aj.conector(httpx.MockTransport(responder)) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE_A, "o_que_mudou", cnpj=EMPRESA, desde=DESDE
        )
    assert erro and "tente de novo em 9 s" in texto


def test_api_lenta_nao_trava_o_conector_e_os_pedidos_correm_juntos():
    """Seis pedidos a uma API que demora e estoura o tempo: em fila, a ferramenta levaria seis vezes a espera de
    um pedido. Correm juntos, e a IA recebe a frase de sempre dentro do limite do conector."""
    espera = 0.3

    async def lenta(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path.endswith("/catalog"):
            return httpx.Response(
                200, json={"datasets": [{"dataset": c} for c in TODOS_OS_BLOCOS]}
            )
        await asyncio.sleep(espera)
        raise httpx.ReadTimeout("a API demorou", request=pedido)

    inicio = time.perf_counter()
    with aj.conector(httpx.MockTransport(lenta)) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE_A, "o_que_mudou", cnpj=EMPRESA, desde=DESDE
        )
    gasto = time.perf_counter() - inicio
    assert erro and "não respondeu" in texto
    assert gasto < TEMPO_LIMITE_DA_API_S
    assert gasto < 4 * espera  # seis pedidos em fila custariam 6 * espera


# ---------------------------------------------------------------- a tranca de saída


@pytest.mark.parametrize(
    "sujar",
    [
        lambda corpo: corpo[CAMINHO_DA_FICHA]["registration"].update(
            partners=[{"name": "FULANA EXEMPLO"}]
        ),
        lambda corpo: corpo[CAMINHO_DOS_VINCULOS]["links"][0].update(cpf="x"),
        lambda corpo: corpo[CAMINHO_DOS_EVENTOS]["events"][0].update(
            contact="fulana@exemplo.invalid"
        ),
    ],
    ids=["sócio no cadastro", "chave de CPF no vínculo", "e-mail no evento"],
)
def test_pessoa_na_resposta_da_api_recusa_a_resposta_inteira_sem_repetir_o_valor(sujar):
    hoje = _como_hoje()
    sujar(hoje)
    with aj.conector(_api_do_historico(hoje=hoje)) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE_A, "o_que_mudou", cnpj=EMPRESA, desde=DESDE
        )
    assert erro and ferramentas.MENSAGEM_DE_PESSOA in texto
    assert "FULANA" not in texto and "exemplo.invalid" not in texto


def test_pessoa_so_no_lado_antigo_tambem_e_recusada():
    """O que a ferramenta compara passa pela tranca antes de sair: o sócio do retrato velho não vaza pelo 'before'."""
    era = _como_era()
    era[CAMINHO_DA_FICHA]["registration"]["legal_name"] = _fato(
        "FULANA EXEMPLO", "rfb-cnpj", "2025-03-10"
    )
    era[CAMINHO_DA_FICHA]["registration"]["partners"] = [{"name": "FULANA EXEMPLO"}]
    with aj.conector(_api_do_historico(era=era)) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE_A, "o_que_mudou", cnpj=EMPRESA, desde=DESDE
        )
    assert erro and "FULANA" not in texto


def test_o_que_a_ferramenta_entrega_nao_tem_pessoa_nem_contato():
    with aj.conector(_api_do_historico()) as cliente:
        texto = json.dumps(_o_que_mudou(cliente))
    for proibida in ("partners", "cpf", "contact", "email", "address"):
        assert proibida not in texto.lower()


def test_resposta_acima_do_teto_do_o_que_mudou_vira_frase_clara_e_nao_corta_o_dado_no_meio():
    hoje = _como_hoje()
    hoje[CAMINHO_DA_FICHA]["limits"] = ["x" * (saida.TETO_DE_CARACTERES + 1)]
    with aj.conector(_api_do_historico(hoje=hoje)) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE_A, "o_que_mudou", cnpj=EMPRESA, desde=DESDE
        )
    assert erro and "grande demais" in texto
    assert len(texto) < 1_000


# ---------------------------------------------------------------- o texto que o analista lê


def test_a_descricao_do_o_que_mudou_diz_o_que_nao_traz():
    descricao = _descricoes_das_ferramentas_novas()["o_que_mudou"]
    nao_traz = descricao.split("Não traz:")[1]
    for ausente in ("sócio pessoa física", "não foi publicada", "faturamento"):
        assert ausente in nao_traz


# ---------------------------------------------------------------- achados da revisão cruzada


def test_o_vinculo_que_so_trocou_o_mes_do_retrato_da_ponta_nao_vira_removido_e_novo():
    hoje = _como_hoje() | {
        CAMINHO_DOS_VINCULOS: _vinculos(
            _vinculo("55555555", 40.0, "2025-05-31", retrato="2026-10")
        )
    }
    with aj.conector(_api_do_historico(hoje=hoje)) as cliente:
        corpo = _o_que_mudou(cliente)
    vinculos = corpo["links"]
    assert vinculos["added"] == [] and vinculos["removed"] == []
    assert vinculos["changed"] == []


def test_o_mes_do_retrato_da_receita_no_cadastro_nao_conta_como_mudanca():
    def com_retrato(mes: str) -> dict:
        ficha = _ficha("ALFA S.A.", "2025-03-10")
        ficha["registration"]["snapshot_month"] = _fato(mes, "rfb-cnpj", "2026-10-31")
        ficha["registration"]["registry_snapshot_month"] = _fato(
            mes, "rfb-cnpj", "2026-10-31"
        )
        return ficha

    hoje = _como_era() | {CAMINHO_DA_FICHA: com_retrato("2026-10")}
    era = _como_era() | {CAMINHO_DA_FICHA: com_retrato("2025-12")}
    with aj.conector(_api_do_historico(hoje=hoje, era=era)) as cliente:
        corpo = _o_que_mudou(cliente)
    assert corpo["changes_found"] == 0


def _entrega(situacao: str, atraso: int, entregue_em: str | None) -> dict:
    return {
        "document": _fato("ITR", "cvm-hist-itr", "2025-11-14"),
        "reference_period": _fato("2025-09-30", "cvm-hist-itr", "2025-11-14"),
        "due_date": _fato("2025-11-14", "cvm-hist-itr", "2025-11-14"),
        "first_filed_on": _fato(entregue_em, "cvm-hist-itr", "2025-11-14"),
        "business_days_late": _fato(atraso, "cvm-hist-itr", "2025-11-14"),
        "filing_status": _fato(situacao, "cvm-hist-itr", "2025-11-14"),
    }


def test_entrega_que_mudou_de_situacao_e_uma_mudanca_nao_um_documento_que_sumiu_e_outro_que_entrou():
    era = _como_era() | {
        CAMINHO_DA_FICHA: _ficha(
            "ALFA S.A.", "2025-03-10", entregas=[_entrega("not_filed", 4, None)]
        )
    }
    hoje = _como_era() | {
        CAMINHO_DA_FICHA: _ficha(
            "ALFA S.A.", "2025-03-10", entregas=[_entrega("late", 7, "2025-11-25")]
        )
    }
    with aj.conector(_api_do_historico(hoje=hoje, era=era)) as cliente:
        corpo = _o_que_mudou(cliente)
    cadastro = corpo["registration"]
    assert cadastro["added"] == [] and cadastro["removed"] == []
    (mudou,) = cadastro["changed"]
    assert mudou["before"]["filing_status"]["value"] == "not_filed"
    assert mudou["after"]["filing_status"]["value"] == "late"


def test_pagina_cheia_nao_diz_que_saiu_o_que_so_ficou_fora_da_pagina():
    """Hoje a página traz só os 2 eventos mais novos; o P1, mais velho, não saiu da base: ficou fora dela."""
    era = _como_era() | {
        CAMINHO_DOS_EVENTOS: _eventos(_evento("P1", "2025-12-20"), truncado=True)
    }
    hoje = _como_hoje() | {
        CAMINHO_DOS_EVENTOS: _eventos(
            _evento("P3", "2026-10-02"), _evento("P2", "2026-03-15"), truncado=True
        )
    }
    with aj.conector(_api_do_historico(hoje=hoje, era=era)) as cliente:
        corpo = _o_que_mudou(cliente)
    eventos = corpo["events"]
    assert eventos["partial"] is True
    assert eventos["removed"] == []
    assert _protocolos(eventos["added"]) == {"P2", "P3"}


def test_se_a_api_vazar_um_vinculo_do_futuro_o_item_inteiro_sai_do_lado_antigo():
    """O vínculo novo tem o `kind` público depois de `desde`, mas as pontas trazem datas antigas (Receita): a
    casca das pontas não pode ficar no lado antigo como 'havia vínculo com X em `desde`'."""
    pedidos: list[httpx.Request] = []
    with aj.conector(_api_do_historico(pedidos=pedidos, vaza=True)) as cliente:
        corpo = _o_que_mudou(cliente)
    antigos = [e.get("before", e.get("item")) for e in corpo["links"]["removed"]] + [
        e["before"] for e in corpo["links"]["changed"]
    ]
    assert "77777777" not in json.dumps(antigos)
    # os dois vínculos de hoje têm o `kind` público depois de `desde`: são novos, não "o que já havia"
    assert {e["item"]["to"]["cnpj_root"] for e in corpo["links"]["added"]} == {
        "55555555",
        "77777777",
    }


# ================================================================ comparar_empresas
#
# A ficha de 2 a 5 empresas lado a lado: uma linha por campo, uma coluna por empresa (a chave é o CNPJ).

TERCEIRA_EMPRESA = "55444333000122"
SO_O_CADASTRO = ("profiles", "companies")


def _ficha_de(cnpj: str, nome: str, **extra) -> dict:
    """A ficha de uma empresa, do jeito da API; `extra` põe campos a mais no cadastro."""
    ficha = _ficha(nome, "2025-03-10")
    ficha["cnpj"] = cnpj
    ficha["registration"] |= extra
    return ficha


def _fichas(por_cnpj: dict[str, dict | None]) -> dict[str, dict]:
    """As rotas de ficha de cada empresa (`None` = a base não a tem)."""
    return {
        f"/companies/{cnpj}/profile": ficha
        for cnpj, ficha in por_cnpj.items()
        if ficha is not None
    }


def _tres_fichas() -> dict[str, dict]:
    return _fichas(
        {
            EMPRESA: _ficha_de(
                EMPRESA, "ALFA S.A.", size=_fato("grande", "rfb-cnpj", "2025-12-01")
            ),
            OUTRA_EMPRESA: _ficha_de(OUTRA_EMPRESA, "BETA LTDA"),
            TERCEIRA_EMPRESA: _ficha_de(
                TERCEIRA_EMPRESA,
                "GAMA S.A.",
                size=_fato("pequeno", "rfb-cnpj", "2025-12-01"),
            ),
        }
    )


def _comparar(cliente, *cnpjs: str, chave: str = CHAVE_A):
    return aj.chamar_ok(cliente, chave, "comparar_empresas", cnpjs=list(cnpjs))


def _linha(corpo: dict, campo: str) -> dict:
    (linha,) = [f for f in corpo["fields"] if f["field"] == campo]
    return linha["values"]


def test_comparar_empresas_so_aparece_para_quem_ve_o_cadastro():
    catalogos = {CHAVE_A: SO_O_CADASTRO, CHAVE_B: ("credit", "links", "events")}
    with aj.conector(_api_do_historico(catalogos=catalogos)) as cliente:
        com = aj.nomes_das_ferramentas(cliente, CHAVE_A)
        sem = aj.nomes_das_ferramentas(cliente, CHAVE_B)
        erro, _ = aj.chamar(
            cliente,
            CHAVE_B,
            "comparar_empresas",
            cnpjs=[EMPRESA, OUTRA_EMPRESA],
        )
    assert "comparar_empresas" in com
    assert "comparar_empresas" not in sem
    assert erro


def test_comparar_poe_cada_empresa_numa_coluna_com_fonte_e_dia_em_cada_valor():
    with aj.conector(_api_do_historico(hoje=_tres_fichas())) as cliente:
        corpo = _comparar(cliente, EMPRESA, OUTRA_EMPRESA, TERCEIRA_EMPRESA)
    assert corpo["cnpjs"] == [EMPRESA, OUTRA_EMPRESA, TERCEIRA_EMPRESA]
    nomes = _linha(corpo, "legal_name")
    assert nomes[EMPRESA] == _fato("ALFA S.A.", "rfb-cnpj", "2025-03-10")
    assert nomes[OUTRA_EMPRESA]["value"] == "BETA LTDA"
    assert nomes[TERCEIRA_EMPRESA]["value"] == "GAMA S.A."
    assert corpo["not_available"] == []
    assert {f["source"] for f in corpo["sources"]} == {"rfb-cnpj"}


def test_campo_que_a_empresa_nao_tem_vem_como_nao_disponivel_e_nunca_como_zero():
    with aj.conector(_api_do_historico(hoje=_tres_fichas())) as cliente:
        corpo = _comparar(cliente, EMPRESA, OUTRA_EMPRESA, TERCEIRA_EMPRESA)
    porte = _linha(corpo, "size")
    assert porte[EMPRESA]["value"] == "grande"
    assert porte[OUTRA_EMPRESA] == "não disponível"
    assert porte[TERCEIRA_EMPRESA]["value"] == "pequeno"
    assert any(limite["code"] == "comparar_empresas" for limite in corpo["limits"])


def test_as_entregas_de_dfp_e_itr_vem_por_empresa():
    alfa = _ficha_de(EMPRESA, "ALFA S.A.")
    alfa["periodic_filings"] = [_entrega("late", 7, "2025-11-25")]
    fichas = _fichas(
        {EMPRESA: alfa, OUTRA_EMPRESA: _ficha_de(OUTRA_EMPRESA, "BETA LTDA")}
    )
    with aj.conector(_api_do_historico(hoje=fichas)) as cliente:
        corpo = _comparar(cliente, EMPRESA, OUTRA_EMPRESA)
    entregas = corpo["periodic_filings"]
    assert entregas[EMPRESA][0]["filing_status"]["value"] == "late"
    assert entregas[OUTRA_EMPRESA] == []


def test_empresa_que_a_base_nao_tem_vira_coluna_nao_disponivel_e_as_outras_seguem():
    fichas = _fichas(
        {
            EMPRESA: _ficha_de(EMPRESA, "ALFA S.A."),
            OUTRA_EMPRESA: None,
        }
    )
    with aj.conector(_api_do_historico(hoje=fichas)) as cliente:
        corpo = _comparar(cliente, EMPRESA, OUTRA_EMPRESA)
    assert corpo["not_available"] == [OUTRA_EMPRESA]
    nomes = _linha(corpo, "legal_name")
    assert nomes[EMPRESA]["value"] == "ALFA S.A."
    assert nomes[OUTRA_EMPRESA] == "não disponível"
    assert corpo["periodic_filings"][OUTRA_EMPRESA] == "não disponível"


def test_nenhuma_empresa_na_base_devolve_o_nao_disponivel_de_sempre():
    with aj.conector(_api_do_historico(hoje={})) as cliente:
        erro, texto = aj.chamar(
            cliente,
            CHAVE_A,
            "comparar_empresas",
            cnpjs=[EMPRESA, OUTRA_EMPRESA],
        )
    assert erro and "Não disponível" in texto


@pytest.mark.parametrize("quantas", [6, 7, 25])
def test_mais_de_cinco_empresas_e_erro_claro_e_nao_chama_a_api(quantas):
    pedidos: list[httpx.Request] = []
    cnpjs = [f"{n:014d}" for n in range(1, quantas + 1)]
    with aj.conector(_api_do_historico(pedidos=pedidos)) as cliente:
        erro, texto = aj.chamar(cliente, CHAVE_A, "comparar_empresas", cnpjs=cnpjs)
    assert erro and "2 a 5 empresas" in texto and f"vieram {quantas}" in texto
    assert not [p for p in pedidos if "/companies/" in p.url.path]


def test_cinco_empresas_e_o_maximo_aceito():
    cnpjs = [f"{n:014d}" for n in range(1, 6)]
    fichas = _fichas({c: _ficha_de(c, f"EMPRESA {c}") for c in cnpjs})
    with aj.conector(_api_do_historico(hoje=fichas)) as cliente:
        corpo = _comparar(cliente, *cnpjs)
    assert corpo["cnpjs"] == cnpjs


def test_uma_empresa_so_nao_e_comparacao():
    with aj.conector(_api_do_historico(hoje=_tres_fichas())) as cliente:
        erro, texto = aj.chamar(cliente, CHAVE_A, "comparar_empresas", cnpjs=[EMPRESA])
    assert erro and "2 a 5 empresas" in texto


def test_cnpj_repetido_e_cpf_sao_recusados_sem_chamar_a_api():
    pedidos: list[httpx.Request] = []
    with aj.conector(_api_do_historico(pedidos=pedidos)) as cliente:
        repetido = aj.chamar(
            cliente,
            CHAVE_A,
            "comparar_empresas",
            cnpjs=[EMPRESA, "11.222.333/0001-81"],
        )
        cpf = aj.chamar(
            cliente,
            CHAVE_A,
            "comparar_empresas",
            cnpjs=[EMPRESA, formatado(cpf_que_confere("888654321"))],
        )
    assert repetido[0] and "repetido" in repetido[1]
    assert cpf[0] and "nunca CPF" in cpf[1]
    assert not [p for p in pedidos if "/companies/" in p.url.path]


def test_cada_empresa_vai_a_api_so_com_o_cnpj_sem_pontuacao_e_sem_known_at():
    pedidos: list[httpx.Request] = []
    with aj.conector(
        _api_do_historico(hoje=_tres_fichas(), pedidos=pedidos)
    ) as cliente:
        _comparar(cliente, "11.222.333/0001-81", OUTRA_EMPRESA)
    fichas = [p for p in pedidos if "/companies/" in p.url.path]
    assert sorted(p.url.path for p in fichas) == sorted(
        f"/data/v1/companies/{c}/profile" for c in (EMPRESA, OUTRA_EMPRESA)
    )
    assert all("known_at" not in p.url.params for p in fichas)


def test_chave_so_com_companies_usa_o_cadastro_plano_de_reserva():
    plano = {
        f"/companies/{c}": {
            "cnpj": c,
            "known_at": HOJE,
            "legal_name": _fato(f"EMPRESA {c}", "rfb-cnpj", "2025-03-10"),
        }
        for c in (EMPRESA, OUTRA_EMPRESA)
    }
    transporte = _api_do_historico(hoje=plano, catalogos={CHAVE_A: ("companies",)})
    with aj.conector(transporte) as cliente:
        corpo = _comparar(cliente, EMPRESA, OUTRA_EMPRESA)
    assert set(_linha(corpo, "legal_name")) == {EMPRESA, OUTRA_EMPRESA}


def test_duas_organizacoes_cada_uma_ve_so_o_que_a_chave_dela_libera():
    pedidos: list[httpx.Request] = []
    catalogos = {CHAVE_A: SO_O_CADASTRO, CHAVE_B: ("credit",)}
    with aj.conector(
        _api_do_historico(hoje=_tres_fichas(), catalogos=catalogos, pedidos=pedidos)
    ) as cliente:
        da_a = _comparar(cliente, EMPRESA, OUTRA_EMPRESA)
        erro, texto = aj.chamar(
            cliente,
            CHAVE_B,
            "comparar_empresas",
            cnpjs=[EMPRESA, OUTRA_EMPRESA],
        )
    assert _linha(da_a, "legal_name")[EMPRESA]["value"] == "ALFA S.A."
    assert erro and "ALFA" not in texto and "BETA" not in texto
    de_b = [p for p in pedidos if p.headers["authorization"] == f"Bearer {CHAVE_B}"]
    assert not [p for p in de_b if "/companies/" in p.url.path]


@pytest.mark.parametrize(
    ("status", "cabecalhos", "corpo", "frase"),
    [
        (
            429,
            {"Retry-After": "17"},
            {"detail": "rate_limited"},
            "tente de novo em 17 s",
        ),
        (401, {}, {"detail": "invalid_api_key"}, "chave foi recusada"),
        (422, {}, {"detail": "invalid"}, "formato errado"),
        (503, {}, {"detail": "unavailable"}, "fora do ar"),
        (500, {}, {"detail": "boom"}, "erro inesperado (status 500)"),
    ],
)
def test_erro_da_api_na_comparacao_vira_frase_clara_em_portugues(
    status, cabecalhos, corpo, frase
):
    with aj.conector(_api_que_so_responde(status, corpo, **cabecalhos)) as cliente:
        erro, texto = aj.chamar(
            cliente,
            CHAVE_A,
            "comparar_empresas",
            cnpjs=[EMPRESA, OUTRA_EMPRESA],
        )
    assert erro and frase in texto
    assert CHAVE_A not in texto and "Traceback" not in texto


def test_erro_de_uma_empresa_que_nao_e_404_derruba_a_comparacao_inteira():
    """Uma coluna a menos, calada, pareceria 'não disponível': a ferramenta para e diz o motivo."""

    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path == "/data/v1/catalog":
            conjuntos = [{"dataset": c} for c in SO_O_CADASTRO]
            return httpx.Response(200, json={"datasets": conjuntos, "sources": []})
        if OUTRA_EMPRESA in pedido.url.path:
            return httpx.Response(
                429, json={"detail": "rate_limited"}, headers={"Retry-After": "9"}
            )
        return httpx.Response(200, json=_ficha_de(EMPRESA, "ALFA S.A."))

    with aj.conector(httpx.MockTransport(responder)) as cliente:
        erro, texto = aj.chamar(
            cliente,
            CHAVE_A,
            "comparar_empresas",
            cnpjs=[EMPRESA, OUTRA_EMPRESA],
        )
    assert erro and "tente de novo em 9 s" in texto and "ALFA" not in texto


def test_api_lenta_nao_trava_o_conector_e_as_fichas_correm_juntas():
    espera = 0.3

    async def lenta(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path.endswith("/catalog"):
            return httpx.Response(
                200, json={"datasets": [{"dataset": c} for c in SO_O_CADASTRO]}
            )
        await asyncio.sleep(espera)
        raise httpx.ReadTimeout("a API demorou", request=pedido)

    cnpjs = [f"{n:014d}" for n in range(1, 6)]
    inicio = time.perf_counter()
    with aj.conector(httpx.MockTransport(lenta)) as cliente:
        erro, texto = aj.chamar(cliente, CHAVE_A, "comparar_empresas", cnpjs=cnpjs)
    gasto = time.perf_counter() - inicio
    assert erro and "não respondeu" in texto
    assert gasto < TEMPO_LIMITE_DA_API_S
    assert gasto < 3 * espera  # cinco fichas em fila custariam 5 * espera


@pytest.mark.parametrize(
    "sujar",
    [
        lambda ficha: ficha["registration"].update(
            partners=[{"name": "FULANA EXEMPLO"}]
        ),
        lambda ficha: ficha.update(contact="fulana@exemplo.invalid"),
        lambda ficha: ficha.update(cpf="x"),
    ],
    ids=["sócio no cadastro", "e-mail na ficha", "chave de CPF"],
)
def test_pessoa_na_ficha_de_qualquer_empresa_recusa_a_comparacao_sem_repetir_o_valor(
    sujar,
):
    fichas = _tres_fichas()
    sujar(fichas[f"/companies/{OUTRA_EMPRESA}/profile"])
    with aj.conector(_api_do_historico(hoje=fichas)) as cliente:
        erro, texto = aj.chamar(
            cliente,
            CHAVE_A,
            "comparar_empresas",
            cnpjs=[EMPRESA, OUTRA_EMPRESA],
        )
    assert erro and ferramentas.MENSAGEM_DE_PESSOA in texto
    assert "FULANA" not in texto and "exemplo.invalid" not in texto


def test_a_descricao_do_comparar_empresas_diz_o_que_nao_traz():
    descricao = _descricoes_das_ferramentas_novas()["comparar_empresas"]
    nao_traz = descricao.split("Não traz:")[1]
    for ausente in ("pessoa física", "faturamento", "opinião"):
        assert ausente in nao_traz
    assert "2 a 5" in descricao


# ---------------------------------------------------------------- revisão cruzada de comparar_empresas


def test_entregas_nao_consultadas_nao_viram_lista_vazia():
    """Sem `periodic_filings` a API diz que a lista não foi consultada: vazia seria 'nenhuma entrega'."""
    sem_entregas = _ficha_de(EMPRESA, "ALFA S.A.")
    del sem_entregas["periodic_filings"]
    sem_entregas["unavailable_filings"] = ["ITR"]
    fichas = _fichas(
        {EMPRESA: sem_entregas, OUTRA_EMPRESA: _ficha_de(OUTRA_EMPRESA, "BETA LTDA")}
    )
    with aj.conector(_api_do_historico(hoje=fichas)) as cliente:
        corpo = _comparar(cliente, EMPRESA, OUTRA_EMPRESA)
    assert corpo["periodic_filings"][EMPRESA] == "não disponível"
    assert corpo["periodic_filings"][OUTRA_EMPRESA] == []
    assert corpo["unavailable_filings"] == {EMPRESA: ["ITR"]}


def test_documento_nao_consultado_de_uma_empresa_vai_para_a_saida_e_nao_para_as_outras():
    parcial = _ficha_de(EMPRESA, "ALFA S.A.")
    parcial["unavailable_filings"] = ["ITR"]
    parcial["unavailable_registration_fields"] = ["simples"]
    fichas = _fichas(
        {EMPRESA: parcial, OUTRA_EMPRESA: _ficha_de(OUTRA_EMPRESA, "BETA LTDA")}
    )
    with aj.conector(_api_do_historico(hoje=fichas)) as cliente:
        corpo = _comparar(cliente, EMPRESA, OUTRA_EMPRESA)
    assert corpo["unavailable_filings"] == {EMPRESA: ["ITR"]}
    assert corpo["unavailable_registration_fields"] == {EMPRESA: ["simples"]}


def test_sem_documento_nao_consultado_as_chaves_nao_aparecem():
    fichas = _fichas(
        {
            EMPRESA: _ficha_de(EMPRESA, "ALFA S.A."),
            OUTRA_EMPRESA: _ficha_de(OUTRA_EMPRESA, "BETA LTDA"),
        }
    )
    with aj.conector(_api_do_historico(hoje=fichas)) as cliente:
        corpo = _comparar(cliente, EMPRESA, OUTRA_EMPRESA)
    assert "unavailable_filings" not in corpo
    assert "unavailable_registration_fields" not in corpo


def _entregas_de(n: int) -> list[dict]:
    """`n` entregas de ITR, uma por trimestre, da mais antiga à mais nova, com texto pesado."""
    entregas = []
    for i in range(n):
        entrega = _entrega("filed", 0, "2025-11-14")
        entrega["reference_period"] = _fato(
            f"{2000 + i // 4}-{(i % 4) * 3 + 3:02d}-28", "cvm-hist-itr", "2025-11-14"
        )
        entregas.append(entrega)
    return entregas


def test_cinco_companhias_com_historico_longo_cabem_no_teto_com_as_entregas_mais_novas():
    fichas = {}
    for numero, cnpj in enumerate(
        [EMPRESA, OUTRA_EMPRESA, TERCEIRA_EMPRESA, "22333444000155", "33444555000166"]
    ):
        ficha = _ficha_de(cnpj, f"EMPRESA {numero}")
        ficha["periodic_filings"] = _entregas_de(64)
        fichas[f"/companies/{cnpj}/profile"] = ficha
    cnpjs = [c.split("/")[2] for c in fichas]
    with aj.conector(_api_do_historico(hoje=fichas)) as cliente:
        corpo = _comparar(cliente, *cnpjs)
    for cnpj in cnpjs:
        entregas = corpo["periodic_filings"][cnpj]
        assert len(entregas) == ferramentas_do_analista.MAXIMO_DE_ENTREGAS
        periodos = [e["reference_period"]["value"] for e in entregas]
        assert periodos == sorted(periodos, reverse=True)
        assert periodos[0] == "2015-12-28"  # a mais nova das 64 (16 anos)
        assert corpo["filings_cut"][cnpj] == 64
    assert len(json.dumps(corpo)) < saida.TETO_DE_CARACTERES


def test_a_frase_de_resposta_grande_manda_comparar_menos_empresas():
    frase = ferramentas.mensagem_de_resposta_grande("comparar_empresas", 200_000)
    assert "cnpjs" in frase and "não tem como pedir menos" not in frase


def test_a_descricao_nao_promete_porte_nem_cita_fonte_que_nao_serve():
    descricao = _descricoes_das_ferramentas_novas()["comparar_empresas"]
    assert "porte" not in descricao.split("Não traz:")[0]
    assert "FRE" not in descricao and "IPE" not in descricao
    assert "DFP e ITR" in descricao


def test_cnpj_de_tamanho_absurdo_e_recusado_pelo_esquema_antes_de_qualquer_pedido():
    pedidos: list[httpx.Request] = []
    with aj.conector(
        _api_do_historico(hoje=_tres_fichas(), pedidos=pedidos)
    ) as cliente:
        n = len(pedidos)
        erro, _ = aj.chamar(
            cliente, CHAVE_A, "comparar_empresas", cnpjs=[EMPRESA, "9" * 5000]
        )
    assert erro
    assert not [p for p in pedidos[n:] if "/companies/" in p.url.path]


# ---------------------------------------------------------------- o retrato de cada lado (linha 980, item d)


def _com_retrato(ficha: dict, mes: str, publico_em: str) -> dict:
    ficha["registration"]["snapshot_month"] = _fato(mes, "rfb-cnpj", publico_em)
    return ficha


def test_o_cadastro_diz_de_que_retrato_da_receita_vem_cada_lado():
    hoje = _como_hoje()
    era = _como_era()
    _com_retrato(hoje[CAMINHO_DA_FICHA], "2026-10", "2026-10-20")
    _com_retrato(era[CAMINHO_DA_FICHA], "2025-12", "2025-12-20")
    with aj.conector(_api_do_historico(hoje=hoje, era=era)) as cliente:
        corpo = _o_que_mudou(cliente)
    assert corpo["registration"]["snapshot_month"] == {
        "before": _fato("2025-12", "rfb-cnpj", "2025-12-20"),
        "after": _fato("2026-10", "rfb-cnpj", "2026-10-20"),
    }
    # o mês do retrato diz qual retrato a base leu, não o que mudou: não conta como mudança
    assert "snapshot_month" not in _campos(corpo["registration"]["changed"])


def test_o_retrato_do_lado_antigo_publicado_depois_de_desde_nao_aparece():
    hoje = _como_hoje()
    era = _como_era()
    _com_retrato(hoje[CAMINHO_DA_FICHA], "2026-10", "2026-10-20")
    _com_retrato(era[CAMINHO_DA_FICHA], "2026-02", "2026-02-20")  # a API vazou o futuro
    with aj.conector(_api_do_historico(hoje=hoje, era=era)) as cliente:
        corpo = _o_que_mudou(cliente)
    assert corpo["registration"]["snapshot_month"] == {
        "before": None,
        "after": _fato("2026-10", "rfb-cnpj", "2026-10-20"),
    }


def test_sem_o_mes_do_retrato_na_api_o_campo_nao_aparece():
    with aj.conector(_api_do_historico()) as cliente:
        corpo = _o_que_mudou(cliente)
    assert "snapshot_month" not in corpo["registration"]
