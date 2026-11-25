"""A ferramenta `acompanhar_empresas` do conector (linha 980, onda 2, PR 1): o que mudou em 2 a 5 empresas desde
um dia, numa chamada.

É o `o_que_mudou` repetido por empresa, sem rota nova e com os mesmos conjuntos; a API do outro lado é um dublê
com memória (com `known_at` responde o passado, sem ele responde hoje). Nenhum dado de pessoa real: os CNPJs são
de mentira, com os dígitos verificadores certos.
"""

import json

import httpx
import pytest

from conector_remoto import consultas_das_portas, ferramentas, saida, servidor
from tests import ajudantes_do_conector as aj
from tests.ajudantes_de_cpf import cpf_que_confere, formatado

ALFA = "11222333000181"
BETA = "99888777000100"
GAMA = "11444777000161"
CHAVE = aj.CHAVE_DE_MENTIRA
OUTRA_CHAVE = "tld_bcdefghi_" + "B" * 43
DESDE = "2026-01-01"
HOJE = "2026-11-10"
TODOS = ("profiles", "companies", "links", "events")


def _fato(valor: object, fonte: str, publico_em: str) -> dict:
    return {"value": valor, "source": fonte, "published_at": publico_em}


def _ficha(cnpj: str, nome: str, dia_do_nome: str) -> dict:
    return {
        "cnpj": cnpj,
        "known_at": HOJE,
        "registration": {
            "legal_name": _fato(nome, "rfb-cnpj", dia_do_nome),
            "registration_status": _fato("ativa", "rfb-cnpj", "2025-12-01"),
        },
        "periodic_filings": [],
        "limits": [{"code": "so_pj", "text": "Só pessoa jurídica."}],
        "sources": [{"source": "rfb-cnpj", "license": "CC BY"}],
    }


def _evento(protocolo: str, dia: str) -> dict:
    return {
        "event_type": "ipe_filing",
        "filing_id": _fato(protocolo, "cvm-hist-ipe", dia),
        "category": _fato("Fato Relevante", "cvm-hist-ipe", dia),
    }


def _eventos(*itens: dict) -> dict:
    return {
        "known_at": HOJE,
        "events": list(itens),
        "truncated": False,
        "sources": [{"source": "cvm-hist-ipe", "license": "CC BY"}],
    }


def _vinculos() -> dict:
    return {
        "known_at": HOJE,
        "links": [],
        "sources": [{"source": "cvm-fre", "license": "CC BY"}],
    }


def _hoje() -> dict[str, dict]:
    """ALFA mudou de nome e teve um fato relevante novo; BETA ficou igual; GAMA a base não serve."""
    return {
        f"/companies/{ALFA}/profile": _ficha(ALFA, "ALFA S.A. NOVA", "2026-08-01"),
        f"/companies/{ALFA}/links": _vinculos(),
        f"/companies/{ALFA}/events": _eventos(
            _evento("P2", "2026-03-15"), _evento("P1", "2025-12-20")
        ),
        f"/companies/{BETA}/profile": _ficha(BETA, "BETA LTDA", "2024-02-01"),
        f"/companies/{BETA}/links": _vinculos(),
        f"/companies/{BETA}/events": _eventos(_evento("B1", "2025-06-01")),
    }


def _era() -> dict[str, dict]:
    return {
        f"/companies/{ALFA}/profile": _ficha(ALFA, "ALFA S.A.", "2025-03-10"),
        f"/companies/{ALFA}/links": _vinculos(),
        f"/companies/{ALFA}/events": _eventos(_evento("P1", "2025-12-20")),
        f"/companies/{BETA}/profile": _ficha(BETA, "BETA LTDA", "2024-02-01"),
        f"/companies/{BETA}/links": _vinculos(),
        f"/companies/{BETA}/events": _eventos(_evento("B1", "2025-06-01")),
    }


def _api(
    catalogos: dict[str, tuple[str, ...]] | None = None,
    pedidos: list[httpx.Request] | None = None,
    hoje: dict[str, dict] | None = None,
    respostas_fixas: dict[str, httpx.Response] | None = None,
) -> httpx.MockTransport:
    catalogos = {CHAVE: TODOS} if catalogos is None else catalogos
    hoje = _hoje() if hoje is None else hoje
    era = _era()

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
        if respostas_fixas and caminho in respostas_fixas:
            return respostas_fixas[caminho]
        corpo = (era if "known_at" in pedido.url.params else hoje).get(caminho)
        if corpo is None:
            return httpx.Response(404, json={"detail": "not_available"})
        return httpx.Response(200, json=corpo)

    return httpx.MockTransport(responder)


def _acompanhar(cliente, cnpjs, chave=CHAVE, **argumentos):
    return aj.chamar_ok(
        cliente, chave, "acompanhar_empresas", cnpjs=cnpjs, desde=DESDE, **argumentos
    )


def _da_empresa(corpo: dict, cnpj: str) -> dict:
    (empresa,) = [e for e in corpo["companies"] if e["cnpj"] == cnpj]
    return empresa


# ---------------------------------------------------------------- a ligação com a lista única


def test_a_ferramenta_esta_na_lista_unica_com_os_conjuntos_do_o_que_mudou():
    assert ferramentas.CONJUNTOS_DA_FERRAMENTA["acompanhar_empresas"] == frozenset(
        TODOS
    )
    assert ferramentas.TITULOS_DAS_FERRAMENTAS["acompanhar_empresas"]
    assert ferramentas.DICAS_DE_RESPOSTA_GRANDE["acompanhar_empresas"]


def test_a_consulta_diz_por_que_a_cli_e_a_api_nao_tem():
    (consulta,) = [
        c
        for c in consultas_das_portas.CONSULTAS
        if any(f.nome == "acompanhar_empresas" for f in c.ferramentas)
    ]
    assert not consulta.comandos and not consulta.rotas
    assert set(consulta.fora_de_uma_porta) == {"cli", "api"}


def test_as_instrucoes_do_servidor_dizem_quando_usar_a_ferramenta():
    assert "`acompanhar_empresas`" in servidor.INSTRUCOES


def test_a_descricao_diz_o_que_devolve_e_o_que_nao_traz_sem_preco_nem_promessa():
    descricao = consultas_das_portas.ferramenta("acompanhar_empresas").descricao
    assert "Fonte:" in descricao and "Não traz:" in descricao
    minusculas = descricao.lower()
    for palavra in ("recomend", "oportunidade", "r$", "garant", "melhor"):
        assert palavra not in minusculas, palavra


# ---------------------------------------------------------------- quem vê a ferramenta


def test_sem_nenhum_dos_conjuntos_a_ferramenta_nao_aparece_nem_chama_a_api():
    pedidos: list[httpx.Request] = []
    transporte = _api(catalogos={CHAVE: ("credit",)}, pedidos=pedidos)
    with aj.conector(transporte) as cliente:
        assert "acompanhar_empresas" not in aj.nomes_das_ferramentas(cliente, CHAVE)
        erro, texto = aj.chamar(
            cliente, CHAVE, "acompanhar_empresas", cnpjs=[ALFA, BETA], desde=DESDE
        )
    assert erro and texto == ferramentas.MENSAGEM_NAO_LIBERADA
    assert not [p for p in pedidos if "/companies/" in p.url.path]


def test_com_so_os_eventos_consulta_so_os_eventos_de_cada_empresa():
    pedidos: list[httpx.Request] = []
    transporte = _api(catalogos={CHAVE: ("events",)}, pedidos=pedidos)
    with aj.conector(transporte) as cliente:
        corpo = _acompanhar(cliente, [ALFA, BETA])
    consultados = {
        p.url.path.removeprefix("/data/v1")
        for p in pedidos
        if "/companies/" in p.url.path
    }
    assert consultados == {f"/companies/{ALFA}/events", f"/companies/{BETA}/events"}
    assert {b["block"] for b in corpo["not_consulted"]} == {"registration", "links"}


def test_duas_organizacoes_cada_uma_ve_so_o_que_o_catalogo_da_sua_chave_libera():
    transporte = _api(catalogos={CHAVE: TODOS, OUTRA_CHAVE: ("events",)})
    with aj.conector(transporte) as cliente:
        completa = _acompanhar(cliente, [ALFA, BETA])
        so_eventos = _acompanhar(cliente, [ALFA, BETA], chave=OUTRA_CHAVE)
    assert "registration" in _da_empresa(completa, ALFA)
    assert "registration" not in _da_empresa(so_eventos, ALFA)


# ---------------------------------------------------------------- o que a ferramenta entrega


def test_cada_empresa_traz_so_o_que_mudou_com_a_fonte_e_o_dia():
    with aj.conector(_api()) as cliente:
        corpo = _acompanhar(cliente, [ALFA, BETA])
    assert corpo["since"] == DESDE and corpo["until"] == HOJE
    alfa = _da_empresa(corpo, ALFA)
    assert alfa["changes_found"] == 2
    (nome,) = alfa["registration"]["changed"]
    assert nome["field"] == "legal_name"
    assert nome["before"] == _fato("ALFA S.A.", "rfb-cnpj", "2025-03-10")
    assert nome["after"] == _fato("ALFA S.A. NOVA", "rfb-cnpj", "2026-08-01")
    (novo,) = alfa["events"]["added"]
    assert novo["item"]["filing_id"] == _fato("P2", "cvm-hist-ipe", "2026-03-15")


def test_a_empresa_sem_mudanca_vem_numa_linha_so_e_a_contagem_no_topo():
    with aj.conector(_api()) as cliente:
        corpo = _acompanhar(cliente, [ALFA, BETA])
    assert _da_empresa(corpo, BETA) == {"cnpj": BETA, "changes_found": 0}
    assert corpo["companies_with_changes"] == 1


def test_as_empresas_saem_na_ordem_pedida_sem_nota_nem_ordenacao():
    with aj.conector(_api()) as cliente:
        corpo = _acompanhar(cliente, [BETA, ALFA])
    assert [e["cnpj"] for e in corpo["companies"]] == [BETA, ALFA]
    texto = json.dumps(corpo, ensure_ascii=False).lower()
    for palavra in ("score", "rating", "nota", "rank"):
        assert f'"{palavra}' not in texto, palavra


def test_a_empresa_que_a_base_nao_serve_vai_para_not_available_e_as_outras_seguem():
    with aj.conector(_api()) as cliente:
        corpo = _acompanhar(cliente, [ALFA, GAMA])
    assert corpo["not_available"] == [GAMA]
    assert [e["cnpj"] for e in corpo["companies"]] == [ALFA]


def test_fontes_e_avisos_vem_uma_vez_so_no_topo():
    with aj.conector(_api()) as cliente:
        corpo = _acompanhar(cliente, [ALFA, BETA])
    fontes = [f["source"] for f in corpo["sources"]]
    assert (
        sorted(fontes) == sorted(set(fontes)) == ["cvm-fre", "cvm-hist-ipe", "rfb-cnpj"]
    )
    codigos = [aviso.get("code") for aviso in corpo["limits"]]
    assert codigos.count("so_pj") == 1
    assert "acompanhar_empresas" in codigos and "o_que_mudou" in codigos
    for empresa in corpo["companies"]:
        assert not {"sources", "limits", "since", "until"} & set(empresa)


def test_o_limite_corta_cada_lista_e_diz_quantas_mudancas_foram_mostradas():
    hoje = _hoje()
    hoje[f"/companies/{ALFA}/events"] = _eventos(
        *(_evento(f"N{i}", "2026-04-01") for i in range(6)),
        _evento("P1", "2025-12-20"),
    )
    with aj.conector(_api(hoje=hoje)) as cliente:
        corpo = _acompanhar(cliente, [ALFA, BETA], limite=2)
    alfa = _da_empresa(corpo, ALFA)
    assert len(alfa["events"]["added"]) == 2
    assert alfa["changes_found"] == 7 and alfa["changes_shown"] == 3


def test_o_lado_antigo_pede_known_at_e_o_de_hoje_nao():
    pedidos: list[httpx.Request] = []
    with aj.conector(_api(pedidos=pedidos)) as cliente:
        _acompanhar(cliente, [ALFA, BETA])
    das_empresas = [p for p in pedidos if "/companies/" in p.url.path]
    assert len(das_empresas) == 12  # 2 empresas x 3 blocos x 2 dias
    com_dia = [p for p in das_empresas if "known_at" in p.url.params]
    assert len(com_dia) == 6
    assert {p.url.params["known_at"] for p in com_dia} == {DESDE}


# ---------------------------------------------------------------- o que a ferramenta recusa


@pytest.mark.parametrize("quantos", [0, 1, 6])
def test_menos_de_2_ou_mais_de_5_empresas_e_recusado_sem_chamar_a_api(quantos):
    pedidos: list[httpx.Request] = []
    cnpjs = [ALFA, BETA, GAMA, "11111111000191", "22222222000191", "33333333000191"]
    with aj.conector(_api(pedidos=pedidos)) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE, "acompanhar_empresas", cnpjs=cnpjs[:quantos], desde=DESDE
        )
    assert erro and "2 a 5" in texto
    assert not [p for p in pedidos if "/companies/" in p.url.path]


def test_cnpj_repetido_e_recusado():
    with aj.conector(_api()) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE, "acompanhar_empresas", cnpjs=[ALFA, ALFA], desde=DESDE
        )
    assert erro and "repetido" in texto


def test_cpf_no_lugar_do_cnpj_e_recusado_sem_chamar_a_api():
    pedidos: list[httpx.Request] = []
    with aj.conector(_api(pedidos=pedidos)) as cliente:
        erro, texto = aj.chamar(
            cliente,
            CHAVE,
            "acompanhar_empresas",
            cnpjs=[ALFA, formatado(cpf_que_confere("888654321"))],
            desde=DESDE,
        )
    assert erro and "CPF" in texto
    assert not [p for p in pedidos if "/companies/" in p.url.path]


def test_desde_hoje_ou_depois_nao_tem_o_que_comparar():
    with aj.conector(_api()) as cliente:
        erro, texto = aj.chamar(
            cliente,
            CHAVE,
            "acompanhar_empresas",
            cnpjs=[ALFA, BETA],
            desde="2999-01-01",
        )
    assert erro and "anterior a hoje" in texto


def test_limite_da_api_para_tudo_em_vez_de_esconder_a_empresa():
    fixas = {
        f"/companies/{BETA}/events": httpx.Response(
            429, headers={"Retry-After": "30"}, json={"detail": "rate_limited"}
        )
    }
    with aj.conector(_api(respostas_fixas=fixas)) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE, "acompanhar_empresas", cnpjs=[ALFA, BETA], desde=DESDE
        )
    assert erro and "minuto" in texto.lower()


def test_resposta_com_pessoa_e_recusada_inteira_sem_repetir_o_valor():
    cpf = formatado(cpf_que_confere("888654321"))
    hoje = _hoje()
    hoje[f"/companies/{BETA}/profile"]["registration"]["legal_name"] = _fato(
        f"BETA {cpf}", "rfb-cnpj", "2026-02-01"
    )
    with aj.conector(_api(hoje=hoje)) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE, "acompanhar_empresas", cnpjs=[ALFA, BETA], desde=DESDE
        )
    assert erro and ferramentas.MENSAGEM_DE_PESSOA in texto
    assert cpf not in texto and "888654321" not in texto


def test_sem_mudanca_mas_com_bloco_que_a_base_nao_serviu_diz_qual_bloco():
    fixas = {
        f"/companies/{BETA}/links": httpx.Response(
            404, json={"detail": "not_available"}
        )
    }
    with aj.conector(_api(respostas_fixas=fixas)) as cliente:
        corpo = _acompanhar(cliente, [ALFA, BETA])
    beta = _da_empresa(corpo, BETA)
    assert beta["changes_found"] == 0
    assert beta["not_available_blocks"] == [
        {"block": "links", "reason": "not_available"}
    ]
    assert "links" not in {b["block"] for b in corpo["not_consulted"]}


def _hoje_com_muitos_eventos(cnpjs: list[str], quantos: int) -> dict[str, dict]:
    """Cada empresa com o nome trocado e `quantos` eventos novos: o pior caso de uma lista cheia."""
    hoje = _hoje()
    for cnpj in cnpjs:
        hoje[f"/companies/{cnpj}/profile"] = _ficha(cnpj, f"NOVA {cnpj}", "2026-08-01")
        hoje[f"/companies/{cnpj}/links"] = _vinculos()
        hoje[f"/companies/{cnpj}/events"] = _eventos(
            *(_evento(f"{cnpj}-{i}", "2026-04-01") for i in range(quantos))
        )
    return hoje


def test_cinco_empresas_com_a_pagina_cheia_de_eventos_cabem_no_teto():
    cinco = [ALFA, BETA, GAMA, "11111111000191", "22222222000191"]
    hoje = _hoje_com_muitos_eventos(cinco, 100)
    with aj.conector(_api(hoje=hoje)) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE, "acompanhar_empresas", cnpjs=cinco, desde=DESDE
        )
    assert not erro, texto
    assert len(texto) < saida.TETO_DE_CARACTERES
    corpo = json.loads(texto)
    assert all(e["changes_shown"] < e["changes_found"] for e in corpo["companies"])


def test_so_blocos_que_a_chave_nao_ve_diz_isso_em_vez_de_dizer_que_a_base_nao_tem():
    """Achado P2 da revisão de segurança do PR 1: antes, as duas empresas iam para `not_available` (a base não as
    serve), quando era a chave que não via o bloco pedido."""
    pedidos: list[httpx.Request] = []
    transporte = _api(catalogos={CHAVE: ("events",)}, pedidos=pedidos)
    with aj.conector(transporte) as cliente:
        erro, texto = aj.chamar(
            cliente,
            CHAVE,
            "acompanhar_empresas",
            cnpjs=[ALFA, BETA],
            desde=DESDE,
            blocos=["cadastro"],
        )
    assert erro and "cadastro" in texto and "chave" in texto
    assert not [p for p in pedidos if "/companies/" in p.url.path]
