"""OAuth do conector remoto (linha 570, PR 2): o Claude e o ChatGPT entram com a chave de cada analista.

Cada teste cobre uma das condições do aceite da Diretoria (10/11/2026): uma chave por pessoa (1), código
de uso único na memória e registro sem estado (2), página `/autorizar` protegida (3), limite por IP atrás
do túnel (4), troca da chave do servidor derruba todos e nada vaza para o log (5). Sem dado de pessoa nem
CNPJ real: as chaves são de mentira e a API é um dublê.
"""

import logging
import time
from urllib.parse import quote

import pytest

from conector_remoto import oauth
from conector_remoto.selo import nova_chave
from conector_remoto.servidor import METADADOS_DO_SERVIDOR
from tests import ajudantes_do_conector as aj
from tests import ajudantes_do_oauth as ao


@pytest.fixture
def api() -> ao.ApiComChaves:
    return ao.ApiComChaves()


def _ferramentas(cliente, token: str) -> list[str]:
    return aj.nomes_das_ferramentas(cliente, token)


# ------------------------------------------------------------------ metadados


def test_metadados_anunciam_cliente_publico_pkce_e_o_mesmo_issuer(api):
    with aj.conector(api.transporte) as cliente:
        servidor = cliente.get(METADADOS_DO_SERVIDOR).json()
        recurso = cliente.get("/.well-known/oauth-protected-resource/mcp").json()
    assert recurso["authorization_servers"] == [servidor["issuer"]]
    assert recurso["resource"] == ao.RECURSO
    assert "none" in servidor["token_endpoint_auth_methods_supported"]
    assert servidor["code_challenge_methods_supported"] == ["S256"]
    assert servidor["registration_endpoint"] == f"{aj.URL_PUBLICA}/register"
    assert "revocation_endpoint" not in servidor


def test_sem_token_o_mcp_responde_401_com_o_ponteiro_dos_metadados(api):
    with aj.conector(api.transporte) as cliente:
        resposta = aj.rpc(cliente, None, "tools/list")
    assert resposta.status_code == 401
    assert (
        "/.well-known/oauth-protected-resource/mcp"
        in resposta.headers["www-authenticate"]
    )


# ------------------------------------------------------------------ registro (DCR)


@pytest.mark.parametrize(
    "volta", [ao.VOLTA_DO_CLAUDE, ao.VOLTA_DO_CHATGPT, ao.VOLTA_DO_CHATGPT_POR_ID]
)
def test_registro_aceita_o_claude_e_o_chatgpt_como_cliente_publico(api, volta):
    with aj.conector(api.transporte) as cliente:
        registrado = ao.registrar_ok(cliente, volta)
    assert registrado["redirect_uris"] == [volta]
    assert registrado["token_endpoint_auth_method"] == "none"
    assert registrado.get("client_secret") is None


@pytest.mark.parametrize(
    "enderecos",
    [
        ("https://atacante.example/callback",),
        (ao.VOLTA_DO_CLAUDE, "https://atacante.example/callback"),
        ("http://localhost:33418/callback",),
        ("https://claude.ai/api/mcp/auth_callback/../outra",),
        ("https://chatgpt.com/connector/oauth/../../x",),
        ("https://chatgpt.com.atacante.example/connector_platform_oauth_redirect",),
    ],
)
def test_registro_recusa_endereco_de_volta_fora_da_lista(api, enderecos):
    with aj.conector(api.transporte) as cliente:
        resposta = ao.registrar(cliente, *enderecos)
    assert resposta.status_code == 400
    assert resposta.json()["error"] == "invalid_redirect_uri"


def test_registro_nao_grava_nada_e_sobrevive_a_outro_processo_com_a_mesma_chave(api):
    ambiente = {"TICKERLAB_MCP_CHAVE_DOS_TOKENS": nova_chave()}
    with aj.conector(api.transporte, ambiente) as cliente:
        registrado = ao.registrar_ok(cliente)
    _, desafio = ao.pkce()
    with aj.conector(api.transporte, ambiente) as outro_processo:
        resposta = ao.autorizar(outro_processo, registrado["client_id"], desafio)
    assert resposta.status_code == 302


def test_client_id_mexido_nao_abre(api):
    with aj.conector(api.transporte) as cliente:
        registrado = ao.registrar_ok(cliente)
        mexido = registrado["client_id"][:-2] + (
            "AA" if not registrado["client_id"].endswith("AA") else "BB"
        )
        resposta = ao.autorizar(cliente, mexido, ao.pkce()[1])
    assert resposta.status_code == 400


def test_cliente_confidencial_tem_segredo_derivado_e_o_token_confere(api):
    with aj.conector(api.transporte) as cliente:
        registrado, codigo, verificador = ao.codigo_para(
            cliente, ao.CHAVE_A, metodo="client_secret_post"
        )
        assert registrado["client_secret"]
        errado = dict(registrado, client_secret="x" * 64)
        recusado = ao.trocar_codigo(cliente, errado, codigo, verificador)
        assert recusado.status_code == 401
        registrado2, codigo2, verificador2 = ao.codigo_para(
            cliente, ao.CHAVE_A, metodo="client_secret_post"
        )
        aceito = ao.trocar_codigo(cliente, registrado2, codigo2, verificador2)
    assert aceito.status_code == 200, aceito.text


# ------------------------------------------------------------------ /authorize


def test_authorize_sem_pkce_e_recusado(api):
    with aj.conector(api.transporte) as cliente:
        registrado = ao.registrar_ok(cliente)
        resposta = ao.autorizar(cliente, registrado["client_id"], None)
    assert (
        "error=invalid_request" in resposta.headers.get("location", "")
        or resposta.status_code == 400
    )


def test_authorize_para_outro_recurso_e_recusado(api):
    with aj.conector(api.transporte) as cliente:
        registrado = ao.registrar_ok(cliente)
        resposta = ao.autorizar(
            cliente,
            registrado["client_id"],
            ao.pkce()[1],
            recurso="https://outro.example/mcp",
        )
    assert resposta.status_code == 302
    assert "error=invalid_target" in resposta.headers["location"]


def test_authorize_com_volta_nao_registrada_e_recusado(api):
    with aj.conector(api.transporte) as cliente:
        registrado = ao.registrar_ok(cliente, ao.VOLTA_DO_CLAUDE)
        resposta = ao.autorizar(
            cliente, registrado["client_id"], ao.pkce()[1], volta=ao.VOLTA_DO_CHATGPT
        )
    assert resposta.status_code == 400


# ------------------------------------------------------------------ a página /autorizar


@pytest.mark.parametrize(
    ("volta", "ia", "host"),
    [
        (ao.VOLTA_DO_CLAUDE, "Claude", "claude.ai"),
        (ao.VOLTA_DO_CHATGPT_POR_ID, "ChatGPT", "chatgpt.com"),
    ],
)
def test_pagina_diz_qual_ia_pede_e_o_aviso(api, volta, ia, host):
    with aj.conector(api.transporte) as cliente:
        registrado = ao.registrar_ok(cliente, volta)
        endereco = ao.endereco_da_pagina(
            cliente, registrado["client_id"], ao.pkce()[1], volta=volta
        )
        resposta, _, _ = ao.abrir_pagina(cliente, endereco)
    assert f"Ligar o {ia} ao TickerLab" in resposta.text
    assert f"<code>{host}</code>" in resposta.text
    assert "Só continue se foi você que começou esta ligação agora" in resposta.text
    assert "sua</strong> chave pessoal" in resposta.text


def test_pagina_nao_abre_em_moldura_nem_fica_em_cache(api):
    with aj.conector(api.transporte) as cliente:
        registrado = ao.registrar_ok(cliente)
        endereco = ao.endereco_da_pagina(cliente, registrado["client_id"], ao.pkce()[1])
        resposta, _, _ = ao.abrir_pagina(cliente, endereco)
    politica = resposta.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in politica
    assert "default-src 'none'" in politica
    assert resposta.headers["x-frame-options"] == "DENY"
    assert resposta.headers["cache-control"] == "no-store"
    assert resposta.headers["referrer-policy"] == "no-referrer"
    cookie = resposta.headers["set-cookie"]
    for atributo in (
        "__Host-tickerlab-csrf=",
        "HttpOnly",
        "Secure",
        "SameSite=strict",
        "Path=/",
    ):
        assert atributo in cookie


def test_pagina_a_chave_vai_no_corpo_nunca_na_url(api):
    with aj.conector(api.transporte) as cliente:
        registrado = ao.registrar_ok(cliente)
        endereco = ao.endereco_da_pagina(cliente, registrado["client_id"], ao.pkce()[1])
        resposta, _, _ = ao.abrir_pagina(cliente, endereco)
    assert '<form method="post" action="/autorizar">' in resposta.text
    assert 'type="password" id="chave" name="chave"' in resposta.text


def test_pedido_mexido_ou_vazio_mostra_erro(api):
    with aj.conector(api.transporte) as cliente:
        vazio = cliente.get("/autorizar")
        mexido = cliente.get("/autorizar?pedido=" + quote("A" * 80))
    assert vazio.status_code == mexido.status_code == 400
    assert "venceu ou não é válido" in mexido.text


def test_post_sem_o_csrf_certo_e_recusado(api):
    with aj.conector(api.transporte) as cliente:
        registrado = ao.registrar_ok(cliente)
        endereco = ao.endereco_da_pagina(cliente, registrado["client_id"], ao.pkce()[1])
        _, pedido, _ = ao.abrir_pagina(cliente, endereco)
        outro_csrf = ao.enviar_chave(
            cliente, pedido, "csrf-de-outra-pagina", ao.CHAVE_A
        )
        cliente.cookies.clear()
        sem_cookie = ao.enviar_chave(cliente, pedido, "qualquer", ao.CHAVE_A)
    assert outro_csrf.status_code == sem_cookie.status_code == 403
    assert "location" not in outro_csrf.headers


def test_chave_errada_mostra_o_mesmo_erro_e_nao_ecoa_a_chave(api):
    tentativa = "tld_zzzzzzzz_" + "Z" * 43
    with aj.conector(api.transporte) as cliente:
        registrado = ao.registrar_ok(cliente)
        endereco = ao.endereco_da_pagina(cliente, registrado["client_id"], ao.pkce()[1])
        _, pedido, csrf = ao.abrir_pagina(cliente, endereco)
        formato_errado = ao.enviar_chave(cliente, pedido, csrf, "nao-e-chave")
        revogada = ao.enviar_chave(cliente, pedido, csrf, tentativa)
    assert formato_errado.status_code == revogada.status_code == 401
    assert "A chave não foi aceita" in revogada.text
    assert tentativa not in revogada.text and "nao-e-chave" not in formato_errado.text


def test_api_fora_do_ar_na_pagina_diz_que_nao_respondeu(api):
    with aj.conector(api.transporte) as cliente:
        registrado = ao.registrar_ok(cliente)
        endereco = ao.endereco_da_pagina(cliente, registrado["client_id"], ao.pkce()[1])
        _, pedido, csrf = ao.abrir_pagina(cliente, endereco)
        api.fora_do_ar = True
        resposta = ao.enviar_chave(cliente, pedido, csrf, ao.CHAVE_A)
    assert resposta.status_code == 503
    assert "não respondeu" in resposta.text


def test_cancelar_volta_para_a_ia_com_access_denied(api):
    with aj.conector(api.transporte) as cliente:
        registrado = ao.registrar_ok(cliente)
        endereco = ao.endereco_da_pagina(cliente, registrado["client_id"], ao.pkce()[1])
        _, pedido, csrf = ao.abrir_pagina(cliente, endereco)
        resposta = ao.enviar_chave(cliente, pedido, csrf, "", acao="cancelar")
    assert resposta.status_code == 303
    volta = ao.parametros_da_volta(resposta.headers["location"])
    assert volta == {"error": "access_denied", "state": "estado-1"}


# ------------------------------------------------------------------ código de uso único e tokens


def test_caminho_inteiro_da_um_token_que_abre_as_ferramentas_da_chave(api):
    with aj.conector(api.transporte) as cliente:
        _, tokens = ao.tokens_para(cliente, ao.CHAVE_A)
        ferramentas = _ferramentas(cliente, tokens["access_token"])
    assert tokens["token_type"].lower() == "bearer"
    assert tokens["expires_in"] == oauth.VALIDADE_DO_ACESSO_S
    assert ferramentas == _ferramentas_com_chave_direta(api, ao.CHAVE_A)
    for token in (tokens["access_token"], tokens["refresh_token"]):
        assert ao.CHAVE_A not in token
        assert "tld_" not in token


def _ferramentas_com_chave_direta(api, chave: str) -> list[str]:
    with aj.conector(api.transporte) as cliente:
        return _ferramentas(cliente, chave)


def test_cada_analista_ve_so_o_que_a_chave_dele_libera(api):
    with aj.conector(api.transporte) as cliente:
        _, tokens_a = ao.tokens_para(cliente, ao.CHAVE_A)
        _, tokens_b = ao.tokens_para(cliente, ao.CHAVE_B)
        de_a = _ferramentas(cliente, tokens_a["access_token"])
        de_b = _ferramentas(cliente, tokens_b["access_token"])
    assert de_a == ["demonstracoes", "ficha_da_empresa", "o_que_posso_ver"]
    assert de_b == ["o_que_posso_ver", "setor", "setores"]


def test_codigo_reusado_e_recusado(api):
    with aj.conector(api.transporte) as cliente:
        registrado, codigo, verificador = ao.codigo_para(cliente, ao.CHAVE_A)
        primeira = ao.trocar_codigo(cliente, registrado, codigo, verificador)
        segunda = ao.trocar_codigo(cliente, registrado, codigo, verificador)
    assert primeira.status_code == 200
    assert segunda.status_code == 400
    assert segunda.json()["error"] == "invalid_grant"


def test_verificador_pkce_errado_e_recusado_e_gasta_o_codigo(api):
    with aj.conector(api.transporte) as cliente:
        registrado, codigo, verificador = ao.codigo_para(cliente, ao.CHAVE_A)
        errado = ao.trocar_codigo(cliente, registrado, codigo, "x" * 50)
        depois = ao.trocar_codigo(cliente, registrado, codigo, verificador)
    assert errado.json()["error"] == "invalid_grant"
    assert depois.json()["error"] == "invalid_grant"


def test_codigo_de_outro_cliente_e_recusado(api):
    with aj.conector(api.transporte) as cliente:
        _, codigo, verificador = ao.codigo_para(cliente, ao.CHAVE_A)
        intruso = ao.registrar_ok(cliente)
        resposta = ao.trocar_codigo(cliente, intruso, codigo, verificador)
    assert resposta.json()["error"] == "invalid_grant"


def test_codigo_vence_em_60_segundos(api, monkeypatch):
    with aj.conector(api.transporte) as cliente:
        registrado, codigo, verificador = ao.codigo_para(cliente, ao.CHAVE_A)
        agora = time.time()
        monkeypatch.setattr(
            oauth.time, "time", lambda: agora + oauth.VALIDADE_DO_CODIGO_S + 1
        )
        resposta = ao.trocar_codigo(cliente, registrado, codigo, verificador)
    assert resposta.json()["error"] == "invalid_grant"


def test_token_mexido_ou_de_outro_proposito_nao_entra(api):
    with aj.conector(api.transporte) as cliente:
        _, tokens = ao.tokens_para(cliente, ao.CHAVE_A)
        acesso = tokens["access_token"]
        mexido = acesso[:10] + ("A" if acesso[10] != "A" else "B") + acesso[11:]
        com_mexido = aj.rpc(cliente, mexido, "tools/list")
        com_renovacao = aj.rpc(cliente, tokens["refresh_token"], "tools/list")
    assert com_mexido.status_code == com_renovacao.status_code == 401


def test_token_de_acesso_vence(api, monkeypatch):
    with aj.conector(api.transporte) as cliente:
        _, tokens = ao.tokens_para(cliente, ao.CHAVE_A)
        agora = time.time()
        monkeypatch.setattr(
            oauth.time, "time", lambda: agora + oauth.VALIDADE_DO_ACESSO_S + 1
        )
        resposta = aj.rpc(cliente, tokens["access_token"], "tools/list")
    assert resposta.status_code == 401


# ------------------------------------------------------------------ renovação


def test_renovacao_troca_os_tokens_e_o_velho_nao_serve_de_novo(api):
    with aj.conector(api.transporte) as cliente:
        registrado, tokens = ao.tokens_para(cliente, ao.CHAVE_A)
        nova = ao.renovar(cliente, registrado, tokens["refresh_token"])
        de_novo = ao.renovar(cliente, registrado, tokens["refresh_token"])
        assert nova.status_code == 200, nova.text
        ferramentas = _ferramentas(cliente, nova.json()["access_token"])
    assert nova.json()["refresh_token"] != tokens["refresh_token"]
    assert ferramentas
    assert de_novo.status_code == 400
    assert de_novo.json()["error"] == "invalid_grant"


def test_renovacao_de_outro_cliente_e_recusada(api):
    with aj.conector(api.transporte) as cliente:
        _, tokens = ao.tokens_para(cliente, ao.CHAVE_A)
        intruso = ao.registrar_ok(cliente)
        resposta = ao.renovar(cliente, intruso, tokens["refresh_token"])
    assert resposta.json()["error"] == "invalid_grant"


def test_chave_revogada_nao_renova_e_nao_consulta(api):
    with aj.conector(api.transporte) as cliente:
        registrado, tokens = ao.tokens_para(cliente, ao.CHAVE_A)
        api.revogar(ao.CHAVE_A)
        erro, _ = aj.chamar(
            cliente, tokens["access_token"], "ficha_da_empresa", cnpj="11111111000191"
        )
        renovacao = ao.renovar(cliente, registrado, tokens["refresh_token"])
        # a renovação recusada apaga a chave da memória: o token de acesso cai na hora
        depois = aj.rpc(cliente, tokens["access_token"], "tools/list")
    assert erro
    assert renovacao.status_code == 400
    assert renovacao.json()["error"] == "invalid_grant"
    assert depois.status_code == 401


def test_api_fora_do_ar_na_renovacao_nao_gasta_o_token(api):
    with aj.conector(api.transporte) as cliente:
        registrado, tokens = ao.tokens_para(cliente, ao.CHAVE_A)
        api.fora_do_ar = True
        falhou = ao.renovar(cliente, registrado, tokens["refresh_token"])
        api.fora_do_ar = False
        depois = ao.renovar(cliente, registrado, tokens["refresh_token"])
    assert falhou.status_code == 400
    assert falhou.json()["error"] == "invalid_request"
    assert depois.status_code == 200, depois.text


# ------------------------------------------------------------------ chave do servidor (incidente)


def test_trocar_a_chave_do_servidor_derruba_todos_os_tokens(api):
    with aj.conector(
        api.transporte, {"TICKERLAB_MCP_CHAVE_DOS_TOKENS": nova_chave()}
    ) as antes:
        registrado, tokens = ao.tokens_para(antes, ao.CHAVE_A)
    with aj.conector(
        api.transporte, {"TICKERLAB_MCP_CHAVE_DOS_TOKENS": nova_chave()}
    ) as depois:
        acesso = aj.rpc(depois, tokens["access_token"], "tools/list")
        renovacao = ao.renovar(depois, registrado, tokens["refresh_token"])
        direta = aj.rpc(depois, ao.CHAVE_A, "tools/list")
    assert acesso.status_code == 401
    assert renovacao.status_code in {400, 401}
    assert direta.status_code == 200


def test_nem_a_chave_do_analista_nem_os_tokens_nem_a_do_servidor_vao_para_o_log(
    api, caplog
):
    chave_do_servidor = nova_chave()
    caplog.set_level(logging.DEBUG)
    with aj.conector(
        api.transporte, {"TICKERLAB_MCP_CHAVE_DOS_TOKENS": chave_do_servidor}
    ) as cliente:
        registrado, tokens = ao.tokens_para(cliente, ao.CHAVE_A)
        ao.renovar(cliente, registrado, tokens["refresh_token"])
        _ferramentas(cliente, tokens["access_token"])
    texto = caplog.text
    for segredo in (
        ao.CHAVE_A,
        tokens["access_token"],
        tokens["refresh_token"],
        chave_do_servidor,
    ):
        assert segredo not in texto


# ------------------------------------------------------------------ limite por IP atrás do túnel


def _falhar(cliente, vezes: int, cabecalhos: dict[str, str] | None = None) -> list[int]:
    registrado = ao.registrar_ok(cliente)
    endereco = ao.endereco_da_pagina(cliente, registrado["client_id"], ao.pkce()[1])
    _, pedido, csrf = ao.abrir_pagina(cliente, endereco)
    return [
        ao.enviar_chave(
            cliente, pedido, csrf, "errada", cabecalhos=cabecalhos
        ).status_code
        for _ in range(vezes)
    ]


def _chave_certa(cliente, cabecalhos: dict[str, str] | None = None) -> int:
    registrado = ao.registrar_ok(cliente)
    endereco = ao.endereco_da_pagina(cliente, registrado["client_id"], ao.pkce()[1])
    _, pedido, csrf = ao.abrir_pagina(cliente, endereco)
    return ao.enviar_chave(
        cliente, pedido, csrf, ao.CHAVE_A, cabecalhos=cabecalhos
    ).status_code


def test_passou_de_20_falhas_o_ip_recebe_429_mesmo_com_a_chave_certa(api):
    with aj.conector(api.transporte) as cliente:
        assert set(_falhar(cliente, 20)) == {401}
        assert _chave_certa(cliente) == 429


def test_cabecalho_do_tunel_forjado_de_fora_e_ignorado(api):
    with aj.conector(api.transporte, ip="203.0.113.10") as cliente:
        for i in range(20):
            _falhar(cliente, 1, {"CF-Connecting-IP": f"198.51.100.{i}"})
        assert _chave_certa(cliente, {"CF-Connecting-IP": "198.51.100.200"}) == 429


def test_atras_do_tunel_o_limite_e_por_quem_chamou(api):
    with aj.conector(api.transporte, ip="127.0.0.1") as cliente:
        _falhar(cliente, 20, {"CF-Connecting-IP": "198.51.100.7"})
        assert _chave_certa(cliente, {"CF-Connecting-IP": "198.51.100.7"}) == 429
        assert _chave_certa(cliente, {"CF-Connecting-IP": "198.51.100.8"}) == 303


def test_acerto_nao_conta_no_limite(api):
    with aj.conector(api.transporte) as cliente:
        resultados = [_chave_certa(cliente) for _ in range(25)]
    assert set(resultados) == {303}
