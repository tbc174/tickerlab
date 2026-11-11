"""O selo dos tokens, o IP atrás do túnel e a chave do servidor na configuração (linha 570, PR 2)."""

import pytest
from starlette.requests import Request

from conector_remoto.configuracao import ler_configuracao
from conector_remoto.limite import (
    REDES_CONFIAVEIS_PADRAO,
    LimitePorIp,
    ip_do_pedido,
    redes,
)
from conector_remoto.selo import (
    TAMANHO_DO_NONCE,
    ChaveInvalida,
    Selador,
    _de_b64,
    ler_chave,
    nova_chave,
)

AGORA = 1_800_000_000.0


@pytest.fixture
def selador() -> Selador:
    return Selador(ler_chave(nova_chave()))


def test_selo_abre_so_com_o_mesmo_proposito(selador):
    selado = selador.selar("pedido", {"a": 1}, agora=AGORA)
    assert selador.abrir("pedido", selado, agora=AGORA) == {"a": 1}
    assert selador.abrir("acesso", selado, agora=AGORA) is None


def test_selo_mexido_ou_lixo_nao_abre(selador):
    selado = selador.selar("acesso", {"k": "x"}, agora=AGORA)
    mexido = selado[:-3] + ("AAA" if not selado.endswith("AAA") else "BBB")
    for texto in (mexido, "", "nao-e-base64!", "ção", "A" * 10):
        assert selador.abrir("acesso", texto, agora=AGORA) is None


def test_selo_vence(selador):
    selado = selador.selar("acesso", {}, agora=AGORA, validade_s=60)
    assert selador.abrir("acesso", selado, agora=AGORA + 59) is not None
    assert selador.abrir("acesso", selado, agora=AGORA + 60) is None


def test_cada_selo_tem_nonce_proprio(selador):
    um = selador.selar("acesso", {"k": "x"}, agora=AGORA)
    outro = selador.selar("acesso", {"k": "x"}, agora=AGORA)
    assert um != outro
    bruto_um, bruto_outro = _de_b64(um), _de_b64(outro)
    assert bruto_um and bruto_outro
    assert bruto_um[:TAMANHO_DO_NONCE] != bruto_outro[:TAMANHO_DO_NONCE]


def test_outra_chave_nao_abre_e_nao_assina_igual(selador):
    outro = Selador(ler_chave(nova_chave()))
    selado = selador.selar("acesso", {}, agora=AGORA)
    assert outro.abrir("acesso", selado, agora=AGORA) is None
    assert outro.assinar("segredo", "id") != selador.assinar("segredo", "id")
    assert selador.assinar("segredo", "id") == selador.assinar("segredo", "id")


def test_chave_do_servidor_invalida_nao_aparece_no_erro():
    curta = "Q" * 20
    with pytest.raises(ChaveInvalida) as erro:
        ler_chave(curta)
    assert curta not in str(erro.value)
    with pytest.raises(ChaveInvalida):
        ler_configuracao({"TICKERLAB_MCP_CHAVE_DOS_TOKENS": "%%%"})


def test_chave_do_servidor_nao_aparece_no_repr():
    chave = nova_chave()
    configuracao = ler_configuracao({"TICKERLAB_MCP_CHAVE_DOS_TOKENS": chave})
    bruta = ler_chave(chave)
    assert configuracao.chave_dos_tokens == bruta
    assert chave not in repr(configuracao) and repr(bruta) not in repr(configuracao)
    assert repr(Selador(bruta)) == "Selador(<chave escondida>)"


def _pedido(conexao: str, cabecalhos: dict[str, str] | None = None) -> Request:
    escopo = {
        "type": "http",
        "client": (conexao, 1234),
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (cabecalhos or {}).items()
        ],
    }
    return Request(escopo)


def test_ip_do_tunel_so_vale_vindo_de_rede_confiavel():
    confiaveis = redes(REDES_CONFIAVEIS_PADRAO)
    tunel = {"CF-Connecting-IP": "198.51.100.7"}
    assert ip_do_pedido(_pedido("127.0.0.1", tunel), confiaveis) == "198.51.100.7"
    assert ip_do_pedido(_pedido("172.18.0.1", tunel), confiaveis) == "198.51.100.7"
    assert ip_do_pedido(_pedido("203.0.113.10", tunel), confiaveis) == "203.0.113.10"
    assert (
        ip_do_pedido(_pedido("127.0.0.1", {"CF-Connecting-IP": "lixo"}), confiaveis)
        == "127.0.0.1"
    )
    assert ip_do_pedido(_pedido("127.0.0.1"), confiaveis) == "127.0.0.1"


def test_redes_confiaveis_vem_do_ambiente():
    configuracao = ler_configuracao({"TICKERLAB_MCP_PROXIES_CONFIAVEIS": "10.9.0.0/16"})
    tunel = {"CF-Connecting-IP": "198.51.100.7"}
    assert (
        ip_do_pedido(_pedido("10.9.1.2", tunel), configuracao.redes_confiaveis)
        == "198.51.100.7"
    )
    assert (
        ip_do_pedido(_pedido("127.0.0.1", tunel), configuracao.redes_confiaveis)
        == "127.0.0.1"
    )


def test_limite_conta_falhas_na_janela():
    relogio = [0.0]
    limite = LimitePorIp(3, 60, relogio=lambda: relogio[0])
    for _ in range(3):
        assert not limite.bloqueado("a")
        limite.falhou("a")
    assert limite.bloqueado("a") and not limite.bloqueado("b")
    relogio[0] = 61
    assert not limite.bloqueado("a")


def test_limite_nao_cresce_sem_fim():
    limite = LimitePorIp(5, 60, relogio=lambda: 0.0, maximo_de_ips=10)
    for i in range(50):
        limite.falhou(f"ip-{i}")
    assert len(limite._falhas) <= 10
