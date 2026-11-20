"""`ativos` e `o_que_mudou` de uma companhia grande cabem na conversa (ensaio de 20/11/2026, ordem da Diretoria).

Dois defeitos achados pelo conector de produção: `ativos` de uma petroleira grande dava "grande demais" (475 mil
caracteres: centenas de contratos, ~2,6 mil caracteres cada, com fonte, dia e a frase de piloto em cada valor) e
`o_que_mudou` de uma companhia aberta dava 138 mil, sem parâmetro nenhum para pedir menos. Os testes rodam o
conector de verdade com uma API de mentira (`httpx.MockTransport`) que responde do tamanho de uma companhia
grande; todo CNPJ e todo valor é inventado. Riscos: a ferramenta falhar de novo; cortar sem dizer o que cortou;
perder a frase de piloto do que entrega (D11.3); a trava de pessoa deixar de olhar a resposta crua.
"""

import json

import httpx
import pytest

from base.prontidao import AVISO_DE_PILOTO
from conector_remoto import enxugar, ferramentas
from conector_remoto.saida import TETO_DE_CARACTERES, tamanho_em_caracteres
from tests import ajudantes_do_conector as aj
from tests.ajudantes_de_cpf import cpf_que_confere, formatado

CHAVE = aj.CHAVE_DE_MENTIRA
EMPRESA = "11222333000181"
DESDE = "2026-08-01"
HOJE = "2026-11-10"
CONTRATOS = 180  # uma petroleira grande: centenas de contratos
ENTREGAS = 64  # as entregas de DFP e ITR de uma companhia aberta antiga


def _env(valor: object, fonte: str, dia: str = "2026-10-01") -> dict:
    """Um valor como a API o entrega a uma organização do piloto: a fonte, o dia e a frase de piloto."""
    return {
        "value": valor,
        "source": fonte,
        "published_at": dia,
        "observed_at": None,
        "pilot": True,
        "pilot_notice": AVISO_DE_PILOTO,
    }


def _contrato(n: int) -> dict:
    anp = "anp-concessionarios"
    return {
        "contract_number": _env(f"ANP-{n:04d}", anp),
        "bid_round": _env("Rodada 11", anp),
        "phase": _env("Produção" if n % 2 else "Exploração", anp),
        "field_or_block_name": _env(f"CAMPO FICTICIO {n}", anp),
        "basin": _env("Santos", anp),
        "onshore_offshore": _env("Mar", anp),
        "contract_share_pct": _env(30.0, anp),
        "is_operator": _env(n % 3 == 0, anp),
    }


def _barragem(n: int, uf: str) -> dict:
    anm = "anm-sigbm-barragens"
    return {
        "dam_id": _env(f"B{n:05d}", anm),
        "name": _env(f"BARRAGEM FICTICIA {n}", anm),
        "mine_name": _env(f"MINA FICTICIA {n}", anm),
        "state_code": _env(uf, anm),
        "municipality": _env("MUNICIPIO FICTICIO", anm),
        "risk_category": _env("Baixo", anm),
        "height_m": _env(12.5, anm),
    }


def _bloco(itens: list[dict], fonte: str) -> dict:
    return {
        "found": bool(itens),
        "source": fonte,
        "latest_published_at": "2026-10-30",
        "coverage": "Cobertura de mentira para o teste.",
        "items": itens,
        "truncated": False,
    }


def _ativos(contratos: int = CONTRATOS, barragens: int = 0) -> dict:
    corpo: dict = {
        "cnpj": EMPRESA,
        "known_at": HOJE,
        "oil_gas_contracts": _bloco(
            [_contrato(n) for n in range(1, contratos + 1)], "anp-concessionarios"
        ),
        "not_covered": ["Imóveis, terras e matrículas."],
        "limits": ["Nada aqui é recomendação de investimento."],
    }
    if barragens:
        ufs = ("MG", "PA")
        corpo["mining_dams"] = _bloco(
            [_barragem(n, ufs[n % 2]) for n in range(1, barragens + 1)],
            "anm-sigbm-barragens",
        )
    return corpo


def _api(
    rotas: dict[str, object],
    conjuntos: tuple[str, ...],
    pedidos: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    """A API de mentira de uma organização: o catálogo dela e, por caminho, o corpo que devolve."""

    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedidos is not None:
            pedidos.append(pedido)
        if pedido.url.path == "/data/v1/catalog":
            return httpx.Response(
                200,
                json={"datasets": [{"dataset": c} for c in conjuntos], "sources": []},
            )
        caminho = pedido.url.path.removeprefix("/data/v1")
        corpo = rotas.get(caminho)
        if corpo is None:
            return httpx.Response(404, json={"detail": "not_available"})
        if callable(corpo):
            corpo = corpo(pedido)
        return httpx.Response(200, json=corpo)

    return httpx.MockTransport(responder)


def _chamar(rotas, conjuntos, ferramenta: str, **argumentos) -> tuple[bool, str]:
    with aj.conector(_api(rotas, conjuntos)) as cliente:
        return aj.chamar(cliente, CHAVE, ferramenta, **argumentos)


def _ativos_pedidos(corpo: dict, **argumentos) -> dict:
    erro, texto = _chamar(
        {f"/companies/{EMPRESA}/assets": corpo},
        ("assets",),
        "ativos",
        cnpj=EMPRESA,
        **argumentos,
    )
    assert not erro, texto
    assert len(texto) <= TETO_DE_CARACTERES
    return json.loads(texto)


def _contratos_entregues(corpo: dict) -> list[str]:
    return [c["contract_number"]["value"] for c in corpo["oil_gas_contracts"]["items"]]


# ================================================================ ativos


def test_a_resposta_de_teste_tem_o_tamanho_do_defeito():
    # sem o conserto, a petroleira de mentira daria a mesma mensagem de "grande demais" da produção
    assert len(json.dumps(_ativos(), ensure_ascii=False)) > 3 * TETO_DE_CARACTERES


def test_ativos_de_petroleira_grande_cabe_e_diz_o_que_cortou():
    corpo = _ativos_pedidos(_ativos())
    entregues = _contratos_entregues(corpo)
    assert 0 < len(entregues) < CONTRATOS
    assert entregues == [
        f"ANP-{n:04d}" for n in range(1, len(entregues) + 1)
    ]  # o começo, na ordem da API
    assert corpo["truncated"] is True
    assert corpo["oil_gas_contracts"]["truncated"] is True
    avisos = " ".join(corpo["limits"])
    assert f"{len(entregues)} de {CONTRATOS}" in avisos
    assert (
        "Nada aqui é recomendação de investimento." in corpo["limits"]
    )  # os da API ficam
    for parametro in ("tipo_de_ativo", "uf", "somente_operador"):
        assert f"`{parametro}`" in avisos


def test_ativos_que_cabe_inteiro_passa_sem_corte_nem_aviso():
    corpo = _ativos_pedidos(_ativos(contratos=5))
    assert len(_contratos_entregues(corpo)) == 5
    assert "truncated" not in corpo
    assert corpo["oil_gas_contracts"]["truncated"] is False
    assert corpo["limits"] == ["Nada aqui é recomendação de investimento."]


def test_ativos_cortado_leva_a_frase_de_piloto_em_cada_valor_entregue():
    corpo = _ativos_pedidos(_ativos())
    for contrato in corpo["oil_gas_contracts"]["items"]:
        for envelope in contrato.values():
            assert envelope["pilot"] is True
            assert envelope["pilot_notice"] == AVISO_DE_PILOTO


def test_limite_traz_so_os_primeiros_itens_de_cada_bloco():
    corpo = _ativos_pedidos(_ativos(contratos=40, barragens=30), limite=7)
    assert len(corpo["oil_gas_contracts"]["items"]) == 7
    assert len(corpo["mining_dams"]["items"]) == 7
    assert corpo["truncated"] is True
    assert "7 de 40" in " ".join(corpo["limits"])


def test_somente_operador_traz_so_os_contratos_em_que_a_empresa_opera():
    corpo = _ativos_pedidos(_ativos(contratos=30), somente_operador=True)
    operadores = [
        c["is_operator"]["value"] for c in corpo["oil_gas_contracts"]["items"]
    ]
    assert operadores == [True] * 10
    assert "opera" in " ".join(corpo["limits"])


def test_uf_filtra_as_barragens_e_diz_que_nao_filtra_o_petroleo():
    corpo = _ativos_pedidos(_ativos(contratos=5, barragens=20), uf="mg")
    ufs = {b["state_code"]["value"] for b in corpo["mining_dams"]["items"]}
    assert ufs == {"MG"}
    assert len(corpo["oil_gas_contracts"]["items"]) == 5  # o contrato da ANP não tem UF
    assert "não filtra" in " ".join(corpo["limits"])


def test_uf_que_so_explica_o_filtro_nao_marca_truncated():
    # revisão cruzada: `truncated` quer dizer que faltou algo; só filtro que não tirou nada não diz isso
    corpo = _ativos_pedidos(_ativos(contratos=5), uf="mg")
    assert len(corpo["oil_gas_contracts"]["items"]) == 5
    assert "não filtra" in " ".join(corpo["limits"])
    assert "truncated" not in corpo


def test_tipo_de_ativo_traz_so_o_bloco_pedido_e_diz_o_que_ficou_de_fora():
    corpo = _ativos_pedidos(
        _ativos(contratos=5, barragens=3), tipo_de_ativo="barragens"
    )
    assert "oil_gas_contracts" not in corpo
    assert len(corpo["mining_dams"]["items"]) == 3
    assert "contratos de petróleo e gás" in " ".join(corpo["limits"])


def test_tipo_de_ativo_que_a_chave_nao_ve_diz_que_o_bloco_nao_veio():
    corpo = _ativos_pedidos(_ativos(contratos=5), tipo_de_ativo="royalties")
    assert "mining_royalties" not in corpo
    assert "não veio" in " ".join(corpo["limits"])


def test_nenhum_bloco_leva_todo_o_orcamento_os_blocos_dividem_o_espaco():
    corpo = _ativos_pedidos(_ativos(contratos=CONTRATOS, barragens=CONTRATOS))
    contratos = len(corpo["oil_gas_contracts"]["items"])
    barragens = len(corpo["mining_dams"]["items"])
    assert contratos > 0 and barragens > 0
    assert (
        abs(contratos - barragens) <= 1 or barragens > contratos
    )  # a barragem é mais leve: cabem mais


@pytest.mark.parametrize(
    "argumentos",
    [
        {"uf": "Minas"},
        {"uf": "M"},
        {"limite": 0},
        {"limite": 501},
        {"tipo_de_ativo": "terras"},
    ],
)
def test_parametro_invalido_de_ativos_e_recusado_sem_chamar_a_api(argumentos):
    pedidos: list[httpx.Request] = []
    with aj.conector(_api({}, ("assets",), pedidos)) as cliente:
        erro, _ = aj.chamar(cliente, CHAVE, "ativos", cnpj=EMPRESA, **argumentos)
    assert erro
    assert not any("/assets" in p.url.path for p in pedidos)


def test_ativos_nao_manda_filtro_nenhum_a_api_so_a_data():
    pedidos: list[httpx.Request] = []
    rotas = {f"/companies/{EMPRESA}/assets": _ativos(contratos=3)}
    with aj.conector(_api(rotas, ("assets",), pedidos)) as cliente:
        aj.chamar_ok(
            cliente,
            CHAVE,
            "ativos",
            cnpj=EMPRESA,
            uf="MG",
            limite=2,
            como_era_em="2026-01-01",
        )
    (pedido,) = [p for p in pedidos if "/assets" in p.url.path]
    assert dict(pedido.url.params) == {"known_at": "2026-01-01"}


def test_ativos_com_pessoa_na_resposta_crua_continua_recusado_depois_do_corte():
    corpo = _ativos(contratos=CONTRATOS)
    corpo["oil_gas_contracts"]["items"][0]["cpf"] = formatado(
        cpf_que_confere("123456789")
    )
    erro, texto = _chamar(
        {f"/companies/{EMPRESA}/assets": corpo},
        ("assets",),
        "ativos",
        cnpj=EMPRESA,
        limite=1,
    )
    assert erro
    assert ferramentas.MENSAGEM_DE_PESSOA in texto or "dado" in texto
    assert formatado(cpf_que_confere("123456789")) not in texto


def test_erro_da_api_em_ativos_passa_como_antes():
    erro, texto = _chamar({}, ("assets",), "ativos", cnpj=EMPRESA, limite=3)
    assert erro
    assert "grande demais" not in texto


def test_as_dicas_citam_so_parametros_que_a_ferramenta_tem():
    with aj.conector(
        _api({}, ("assets", "profiles", "companies", "links", "events"))
    ) as cliente:
        resposta = aj.rpc(cliente, CHAVE, "tools/list")
    ferramentas_ = {f["name"]: f for f in resposta.json()["result"]["tools"]}
    for nome in ("ativos", "o_que_mudou"):
        propriedades = set(ferramentas_[nome]["inputSchema"]["properties"])
        citados = set(
            __import__("re").findall(
                r"`(\w+)`", ferramentas.DICAS_DE_RESPOSTA_GRANDE[nome]
            )
        )
        assert citados <= propriedades | {"cadastro", "vinculos", "eventos"}, nome


# ================================================================ o_que_mudou

CAMINHO_DA_FICHA = f"/companies/{EMPRESA}/profile"
CAMINHO_DOS_VINCULOS = f"/companies/{EMPRESA}/links"
CAMINHO_DOS_EVENTOS = f"/companies/{EMPRESA}/events"
TODOS = ("profiles", "links", "events")


def _entrega(n: int, atraso: int) -> dict:
    """Uma entrega de DFP/ITR: o documento e o período a identificam, o atraso muda com o dia."""
    cvm = "cvm-dfp-itr"
    return {
        "document": _env("DFP" if n % 4 == 0 else "ITR", cvm, "2026-04-02"),
        "reference_period": _env(
            f"20{10 + n // 4:02d}-{(n % 4) * 3 + 3:02d}-30", cvm, "2026-04-02"
        ),
        "status": _env("Entregue", cvm, "2026-04-02"),
        "delay_days": _env(atraso, cvm, "2026-04-02"),
        "due_date": _env("2026-03-31", cvm, "2026-04-02"),
        "delivered_at": _env("2026-04-02", cvm, "2026-04-02"),
        "version": _env(1, cvm, "2026-04-02"),
    }


def _ficha(
    atraso: int, entregas: int = ENTREGAS, nome: str = "ALFA ENERGIA S.A."
) -> dict:
    return {
        "cnpj": EMPRESA,
        "known_at": HOJE,
        "registration": {"legal_name": _env(nome, "rfb-cnpj", "2025-01-01")},
        "periodic_filings": [_entrega(n, atraso) for n in range(entregas)],
        "limits": [{"code": "so_pj", "text": "Só pessoa jurídica."}],
        "sources": [{"source": "cvm-dfp-itr", "license": "CC BY"}],
    }


def _evento(n: int) -> dict:
    return {
        "event_type": "ipe_filing",
        "filing_id": _env(f"P{n:04d}", "cvm-hist-ipe", "2026-10-02"),
        "category": _env("Fato Relevante", "cvm-hist-ipe", "2026-10-02"),
    }


def _vinculo(n: int) -> dict:
    cvm = "cvm-fre"
    ponta = lambda raiz: {
        "entity_id": f"E{raiz}",
        "cnpj_root": raiz,
        "legal_name": _env(f"EMPRESA FICTICIA {raiz}", "rfb-cnpj", "2025-12-31"),
    }
    return {
        "hops": 1,
        "kind": _env("subsidiary_of", cvm, "2025-05-31"),
        "from": ponta("11222333"),
        "to": ponta(f"{n:08d}"),
        "ownership_pct": _env(60.0, cvm, "2025-05-31"),
        "valid_from": _env("2018-12-31", cvm, "2025-05-31"),
    }


def _api_da_companhia(
    atraso_hoje: int = 5,
    atraso_antes: int = 1,
    vinculos: int = 0,
    eventos: int = 0,
    pedidos: list[httpx.Request] | None = None,
    ficha_hoje: dict | None = None,
    entregas: int = ENTREGAS,
) -> httpx.MockTransport:
    """A API com memória: com `known_at` responde como era em `DESDE`, sem ele responde como é hoje."""
    hoje = {
        CAMINHO_DA_FICHA: ficha_hoje or _ficha(atraso_hoje, entregas),
        CAMINHO_DOS_VINCULOS: {
            "known_at": HOJE,
            "links": [_vinculo(n) for n in range(vinculos)],
        },
        CAMINHO_DOS_EVENTOS: {
            "known_at": HOJE,
            "events": [_evento(n) for n in range(eventos)],
            "truncated": False,
        },
    }
    era = {
        CAMINHO_DA_FICHA: _ficha(atraso_antes, entregas),
        CAMINHO_DOS_VINCULOS: {
            "known_at": DESDE,
            "links": [_vinculo(n) for n in range(vinculos)],
        },
        CAMINHO_DOS_EVENTOS: {"known_at": DESDE, "events": [], "truncated": False},
    }

    def por_dia(caminho: str):
        return lambda pedido: (era if "known_at" in pedido.url.params else hoje)[
            caminho
        ]

    return _api({c: por_dia(c) for c in hoje}, TODOS, pedidos)


def _o_que_mudou(transporte, **argumentos) -> dict:
    with aj.conector(transporte) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE, "o_que_mudou", cnpj=EMPRESA, desde=DESDE, **argumentos
        )
    assert not erro, texto
    assert len(texto) <= TETO_DE_CARACTERES
    return json.loads(texto)


def test_a_diferenca_de_teste_tem_o_tamanho_do_defeito():
    # cada entrega que mudou leva o antes e o depois: 64 entregas passam do teto sozinhas
    um = {"before": _entrega(1, 1), "after": _entrega(1, 5)}
    assert len(json.dumps(um, ensure_ascii=False)) * ENTREGAS > TETO_DE_CARACTERES


def test_o_que_mudou_de_companhia_aberta_cabe_e_diz_o_que_cortou():
    corpo = _o_que_mudou(_api_da_companhia(atraso_hoje=5, atraso_antes=1))
    assert corpo["changes_found"] == ENTREGAS  # a contagem é a inteira
    mudadas = corpo["registration"]["changed"]
    assert 0 < len(mudadas) < ENTREGAS
    assert corpo["changes_shown"] == len(mudadas)
    assert corpo["truncated"] is True
    assert corpo["registration"]["truncated"] is True
    avisos = json.dumps(corpo["limits"], ensure_ascii=False)
    assert f"{len(mudadas)} de {ENTREGAS}" in avisos
    assert "`blocos`" in avisos and "`limite`" in avisos


def test_o_que_mudou_cortado_mantem_a_frase_de_piloto_do_que_entrega():
    corpo = _o_que_mudou(_api_da_companhia(atraso_hoje=5, atraso_antes=1))
    for mudanca in corpo["registration"]["changed"]:
        for lado in (mudanca["before"], mudanca["after"]):
            for envelope in lado.values():
                assert envelope["pilot_notice"] == AVISO_DE_PILOTO


def test_o_que_mudou_que_cabe_inteiro_passa_sem_corte():
    corpo = _o_que_mudou(
        _api_da_companhia(atraso_hoje=5, atraso_antes=1, entregas=3),
        limite=200,
    )
    assert "truncated" not in corpo
    assert "changes_shown" not in corpo


def test_limite_corta_cada_lista_e_a_contagem_continua_inteira():
    corpo = _o_que_mudou(_api_da_companhia(atraso_hoje=5, atraso_antes=1), limite=3)
    assert len(corpo["registration"]["changed"]) == 3
    assert corpo["changes_found"] == ENTREGAS
    assert corpo["changes_shown"] == 3
    assert f"3 de {ENTREGAS}" in json.dumps(corpo["limits"], ensure_ascii=False)


def test_blocos_pede_so_o_que_o_analista_quer_e_nao_consulta_o_resto():
    pedidos: list[httpx.Request] = []
    corpo = _o_que_mudou(
        _api_da_companhia(eventos=10, pedidos=pedidos), blocos=["eventos"]
    )
    assert "registration" not in corpo and "links" not in corpo
    assert len(corpo["events"]["added"]) == 10
    caminhos = {p.url.path for p in pedidos}
    assert not any(c.endswith(("/profile", "/links")) for c in caminhos)
    por_bloco = {n["block"]: n["reason"] for n in corpo["not_consulted"]}
    assert por_bloco == {"registration": "not_requested", "links": "not_requested"}


def test_um_bloco_por_vez_da_a_cada_um_o_espaco_inteiro():
    juntos = _o_que_mudou(_api_da_companhia(atraso_hoje=5, atraso_antes=1, eventos=100))
    so_cadastro = _o_que_mudou(
        _api_da_companhia(atraso_hoje=5, atraso_antes=1, eventos=100),
        blocos=["cadastro"],
    )
    assert len(so_cadastro["registration"]["changed"]) > len(
        juntos["registration"]["changed"]
    )


def test_os_blocos_dividem_o_espaco_nenhum_leva_tudo():
    corpo = _o_que_mudou(
        _api_da_companhia(atraso_hoje=5, atraso_antes=1, eventos=100, vinculos=0)
    )
    assert len(corpo["registration"]["changed"]) > 0
    assert len(corpo["events"]["added"]) > 0


def test_ficha_crua_grande_nao_derruba_o_que_mudou_so_porque_passou_do_teto():
    # a ficha de mentira tem ~96 mil caracteres por dia; com 30 mil de eventos a mais, a crua passava do teto
    # na tranca antiga (que olhava cada resposta crua com o teto). O que vai à IA é só a diferença.
    ficha = _ficha(1, entregas=ENTREGAS)
    tamanho = len(json.dumps(ficha, ensure_ascii=False))
    assert tamanho > 40_000
    corpo = _o_que_mudou(
        _api_da_companhia(atraso_hoje=1, atraso_antes=1, ficha_hoje=ficha)
    )
    assert corpo["changes_found"] == 0


def test_resposta_crua_acima_do_teto_mas_sem_mudanca_entrega_a_frase_de_nada_mudou():
    grande = _ficha(1, entregas=ENTREGAS * 3)
    assert len(json.dumps(grande, ensure_ascii=False)) > TETO_DE_CARACTERES
    corpo = _o_que_mudou(
        _api_da_companhia(atraso_hoje=1, atraso_antes=1, ficha_hoje=grande),
    )
    assert corpo["registration"][
        "added"
    ]  # as entregas que o dia antigo não tinha: mudança de verdade
    assert tamanho_em_caracteres(corpo) <= TETO_DE_CARACTERES


def test_pessoa_na_resposta_crua_continua_recusada_mesmo_sem_o_teto():
    ficha = _ficha(5)
    ficha["registration"]["partners_cpf"] = _env(
        formatado(cpf_que_confere("987654321")), "rfb-cnpj"
    )
    transporte = _api_da_companhia(ficha_hoje=ficha)
    with aj.conector(transporte) as cliente:
        erro, texto = aj.chamar(
            cliente, CHAVE, "o_que_mudou", cnpj=EMPRESA, desde=DESDE
        )
    assert erro
    assert ferramentas.MENSAGEM_DE_PESSOA in texto or "dado" in texto
    assert formatado(cpf_que_confere("987654321")) not in texto


@pytest.mark.parametrize(
    "argumentos",
    [{"limite": 0}, {"limite": 201}, {"blocos": ["socios"]}, {"blocos": "eventos"}],
)
def test_parametro_invalido_de_o_que_mudou_e_recusado_sem_chamar_a_api(argumentos):
    pedidos: list[httpx.Request] = []
    with aj.conector(_api_da_companhia(pedidos=pedidos)) as cliente:
        erro, _ = aj.chamar(
            cliente, CHAVE, "o_que_mudou", cnpj=EMPRESA, desde=DESDE, **argumentos
        )
    assert erro
    assert not any("/companies/" in p.url.path for p in pedidos)


# ================================================================ o corte em si (sem rede)


def test_o_corte_nao_mexe_no_que_nao_e_lista_nem_perde_a_ordem():
    corpo = enxugar.enxugar_o_que_mudou(
        {
            "changes_found": 4,
            "registration": {
                "changed": [],
                "added": [{"n": i} for i in range(4)],
                "removed": [],
            },
            "limits": [],
        },
        limite=2,
    )
    assert isinstance(corpo, dict)
    assert corpo["registration"]["added"] == [{"n": 0}, {"n": 1}]
    assert corpo["changes_found"] == 4


@pytest.mark.parametrize("entrada", [None, [], "texto", 3, {}])
def test_corpo_que_nao_tem_o_formato_passa_como_veio(entrada):
    assert enxugar.enxugar_o_que_mudou(entrada, limite=1) == entrada
    assert enxugar.enxugar_ativos(entrada, limite=1) == entrada


def test_o_orcamento_so_conta_os_itens_que_cabem():
    pesados = [{"x": "a" * 50_000} for _ in range(5)]
    leves = [{"x": "b"} for _ in range(5)]
    ficam = enxugar._quantos_cabem({}, {"pesados": pesados, "leves": leves})
    assert ficam["leves"] == 5
    assert 0 < ficam["pesados"] < 5
