"""`POST /v1/chat` (linha 903): o chat de IA do app, com o dublê do modelo (nenhuma chamada paga).

Riscos que estes testes pegam: (1) o chat responder (e gastar) com a chave `TICKERLAB_CHAT` desligada, sem a
chave do modelo ou com um modelo sem preço; (2) a conta sem organização ou a organização sem chave usar o
chat; (3) passar da cota da conta (10 por dia, 50 por mês) ou do teto do mês somando todas as contas;
(4) pessoa física chegar ao modelo, mesmo para a organização com `pessoa_na_tela`; (5) o log levar o texto da
pergunta, da resposta ou o e-mail; (6) um erro no meio deixar a pergunta em curso ou derrubar a conexão.
Todo nome aqui é inventado.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from conector_remoto.ferramentas import MENSAGEM_DE_PESSOA
from src import chat
from src.api_v1 import chat as rota
from src.banco import chaves_da_api as cb
from src.banco import membros_da_organizacao as mb
from src.banco import perguntas_do_chat as pc
from src.banco.modelo import perguntas_do_chat
from src.banco.usuarios import entrar
from src.chat import conversa as cv
from src.chat import estado as rota_estado
from src.chat.custo import custo_em_microdolares
from src.planos import LIMITES_DO_CHAT
from tests import test_api_v1_rotas as rotas
from tests.ajudantes_do_chat import (
    USO_DA_VOLTA,
    ModeloDeMentira,
    pede,
    responde,
    transporte_de_mentira,
)

chave = rotas.chave
cliente = rotas.cliente  # a Ana, logada

ROTA = "/api/v1/chat"
MOMENTO = datetime(2026, 11, 13, 15, tzinfo=UTC)
PERGUNTA = "PERGUNTA-SECRETA quais setores vocês acompanham?"
RESPOSTA = "RESPOSTA-SECRETA: Bancos."
COM_PESSOA = {"cnpj": "11111111000191", "partners": [{"name": "FULANO DE TAL"}]}


class _Fabrica:
    """Faz o modelo de cada pergunta e diz se a rota chegou a pedir um."""

    def __init__(self) -> None:
        self.voltas: list = []
        self.modelos: list[ModeloDeMentira] = []

    def __call__(self, nome: str) -> ModeloDeMentira:
        modelo = ModeloDeMentira(*self.voltas)
        self.modelos.append(modelo)
        return modelo


@pytest.fixture
def fabrica(monkeypatch):
    fabrica = _Fabrica()
    fabrica.voltas = [pede(("setores", {})), responde(RESPOSTA)]
    monkeypatch.setenv(chat.VARIAVEL_DE_LIGAR, "1")
    monkeypatch.setenv(chat.VARIAVEL_DA_CHAVE_DO_MODELO, "chave-de-teste-falsa")
    monkeypatch.delenv(chat.VARIAVEL_DO_MODELO, raising=False)
    monkeypatch.setattr(rota, "agora", lambda: MOMENTO)
    monkeypatch.setattr(rota, "modelo_para", fabrica)
    monkeypatch.setattr(
        rota, "transporte_para", lambda _contexto: transporte_de_mentira()
    )
    return fabrica


def _ana(banco):
    return rotas._id_da_ana_no(banco)


def _organizacao(banco, conta_id, *, com_chave=True, pessoa_na_tela=False):
    with banco.begin() as conexao:
        admin = entrar(conexao, "g-admin-903", "admin-903@exemplo.com")[0]
        org = cb.criar_organizacao(conexao, nome="Casa Exemplo", ator_id=admin.id)
        mb.vincular_membro(
            conexao, organizacao_id=org.id, usuario_id=conta_id, ator_id=admin.id
        )
        if com_chave:
            cb.emitir_chave(
                conexao,
                organizacao_id=org.id,
                ator_id=admin.id,
                agora=MOMENTO - timedelta(days=1),
            )
        if pessoa_na_tela:
            cb.conceder_direito(
                conexao,
                organizacao_id=org.id,
                conjunto=mb.CONJUNTO_DE_PESSOA_NA_TELA,
                finalidade=mb.FINALIDADE_DA_TELA,
                vigente_desde=MOMENTO.date() - timedelta(days=1),
                ator_id=admin.id,
            )
    return org


@pytest.fixture
def casa(banco, cliente):
    """A organização da Ana, com uma chave da API ativa."""
    return _organizacao(banco, _ana(banco))


def _perguntar(cliente, pergunta=PERGUNTA, **outros):
    return cliente.post(ROTA, json={"pergunta": pergunta, **outros})


def _linhas(resposta) -> list[dict]:
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(linha) for linha in resposta.text.splitlines() if linha]


def _perguntas(banco) -> list[sa.Row]:
    with banco.connect() as conexao:
        return list(conexao.execute(sa.select(perguntas_do_chat)))


def _gravar_perguntas(banco, conta_id, org_id, quantas, quando, custo=None):
    with banco.begin() as conexao:
        for _ in range(quantas):
            pergunta = pc.reservar(
                conexao,
                usuario_id=conta_id,
                organizacao_id=org_id,
                modelo=chat.MODELO_PADRAO,
                agora=quando,
            )
            if custo is not None:
                pc.concluir(
                    conexao,
                    pergunta,
                    estado="respondida",
                    uso=pc.UsoDaPergunta(custo_em_microdolares=custo),
                    latencia_ms=1,
                )


# ---------------------------------------------------------------- a resposta


def test_pergunta_responde_em_linhas_e_fecha_a_linha_do_banco(
    banco, cliente, casa, fabrica
):
    linhas = _linhas(_perguntar(cliente))
    assert [l["tipo"] for l in linhas] == ["ferramenta", "texto", "fim"]
    assert linhas[0]["nome"] == "setores"
    assert linhas[1]["texto"] == RESPOSTA
    fim = linhas[-1]
    assert [c["nome"] for c in fim["como_cheguei_aqui"]] == ["setores"]
    assert fim["aviso_final"] == cv.AVISO_FINAL
    (linha,) = _perguntas(banco)
    assert linha.estado == "respondida"
    assert linha.usuario_id == _ana(banco) and linha.organizacao_id == casa.id
    assert linha.chamadas_de_ferramenta == 1
    assert linha.tokens_de_entrada == 2 * USO_DA_VOLTA.entrada
    assert linha.custo_em_microdolares == custo_em_microdolares(
        chat.MODELO_PADRAO, USO_DA_VOLTA + USO_DA_VOLTA
    )
    assert linha.latencia_ms is not None


def test_o_modelo_recebe_as_instrucoes_do_arquivo_com_a_data(cliente, casa, fabrica):
    _linhas(_perguntar(cliente))
    (modelo,) = fabrica.modelos
    sistema = modelo.pedidos[0].sistema
    assert "<dados_da_ferramenta>" in sistema and "Não temos" in sistema
    assert sistema.endswith("Hoje é 13/11/2026 (horário de Brasília).")


def test_historico_vai_ao_modelo(cliente, casa, fabrica):
    historico = [{"pergunta": "antes", "resposta": "resposta de antes"}]
    _linhas(_perguntar(cliente, historico=historico))
    mensagens = fabrica.modelos[0].pedidos[0].mensagens
    assert [m["content"] for m in mensagens] == ["antes", "resposta de antes", PERGUNTA]


def test_log_so_com_ids_e_numeros(banco, cliente, casa, fabrica, caplog):
    caplog.set_level(logging.INFO)
    _linhas(_perguntar(cliente))
    assert "PERGUNTA-SECRETA" not in caplog.text
    assert "RESPOSTA-SECRETA" not in caplog.text
    assert "ana@exemplo.com" not in caplog.text
    (registro,) = [r for r in caplog.records if '"chat_pergunta"' in r.getMessage()]
    campos = json.loads(registro.getMessage())
    assert campos["usuario_id"] == str(_ana(banco))
    assert campos["organizacao_id"] == str(casa.id)
    assert campos["estado"] == "respondida" and campos["chamadas_de_ferramenta"] == 1
    assert set(campos) == {
        "evento", "pergunta_id", "usuario_id", "organizacao_id", "modelo", "estado",
        "tokens_de_entrada", "tokens_de_saida", "tokens_lidos_do_cache",
        "tokens_gravados_no_cache", "custo_em_microdolares", "chamadas_de_ferramenta",
        "latencia_ms",
    }  # fmt: skip


def test_erro_no_meio_vira_linha_de_erro_e_a_pergunta_fecha_como_erro(
    banco, cliente, casa, fabrica, caplog
):
    caplog.set_level(logging.INFO)
    fabrica.voltas = [pede(("setores", {})), [RuntimeError("detalhe-interno FULANO")]]
    linhas = _linhas(_perguntar(cliente))
    assert linhas[-1] == {"tipo": "erro", "mensagem": rota.MENSAGEM_DE_ERRO}
    (linha,) = _perguntas(banco)
    assert linha.estado == "erro"
    # a volta que parou no meio pode ter sido paga sem o uso chegar: a pergunta fica pela reserva
    assert linha.tokens_de_entrada == USO_DA_VOLTA.entrada
    assert (
        linha.custo_em_microdolares
        == LIMITES_DO_CHAT.reserva_por_pergunta_em_microdolares
    )
    assert "detalhe-interno" not in caplog.text and "FULANO" not in caplog.text


def test_volta_refeita_fica_pela_reserva(banco, cliente, casa, fabrica):
    """A tentativa que falhou foi paga e o uso dela não chega: a pergunta conta a reserva."""
    fabrica.voltas = [[cv.Recomeco(), *responde(RESPOSTA)]]
    assert _linhas(_perguntar(cliente))[-1]["tipo"] == "fim"
    (linha,) = _perguntas(banco)
    assert linha.estado == "respondida"
    assert (
        linha.custo_em_microdolares
        == LIMITES_DO_CHAT.reserva_por_pergunta_em_microdolares
    )


def test_reserva_e_conferida_de_novo_quando_a_resposta_comeca(
    banco, cliente, casa, fabrica, monkeypatch
):
    """Outro pedido passou na frente entre a conferência e a reserva: linha de erro, nada gravado."""
    _gravar_perguntas(banco, _ana(banco), casa.id, 10, MOMENTO - timedelta(hours=1))
    monkeypatch.setattr(rota, "_conferir", lambda *_: None)
    linhas = _linhas(_perguntar(cliente))
    assert linhas == [{"tipo": "erro", "mensagem": rota.MENSAGEM_COTA_DO_DIA}]
    assert fabrica.modelos[0].pedidos == []  # o modelo não foi chamado
    assert len(_perguntas(banco)) == 10


def test_pergunta_abandonada_fecha_na_proxima_reserva(banco, cliente, casa, fabrica):
    with banco.begin() as conexao:
        pc.reservar(
            conexao,
            usuario_id=_ana(banco),
            organizacao_id=casa.id,
            modelo=chat.MODELO_PADRAO,
            agora=MOMENTO - timedelta(hours=2),
        )
    _linhas(_perguntar(cliente))
    estados = sorted(l.estado for l in _perguntas(banco))
    assert estados == ["erro", "respondida"]


def test_recusa_do_modelo_fecha_como_recusada(banco, cliente, casa, fabrica):
    fabrica.voltas = [responde("", parada="refusal")]
    linhas = _linhas(_perguntar(cliente))
    assert linhas[-1]["avisos"] == [cv.AVISO_RECUSA]
    (linha,) = _perguntas(banco)
    assert linha.estado == "recusada"


# ---------------------------------------------------------------- sem pessoa


def test_pessoa_nao_chega_ao_modelo_nem_com_pessoa_na_tela(
    banco, cliente, fabrica, monkeypatch
):
    _organizacao(banco, _ana(banco), pessoa_na_tela=True)
    rotas_da_api = {
        "/companies/11111111000191/profile": httpx.Response(200, json=COM_PESSOA),
        "/companies/11111111000191": httpx.Response(200, json=COM_PESSOA),
    }
    monkeypatch.setattr(
        rota, "transporte_para", lambda _contexto: transporte_de_mentira(rotas_da_api)
    )
    fabrica.voltas = [
        pede(("ficha_da_empresa", {"cnpj": "11111111000191"})),
        responde("Não temos."),
    ]
    linhas = _linhas(_perguntar(cliente, "Quem são os sócios da ALFA?"))
    (modelo,) = fabrica.modelos
    tudo_que_o_modelo_viu = json.dumps(
        [p.mensagens for p in modelo.pedidos], ensure_ascii=False, default=str
    )
    assert "FULANO" not in tudo_que_o_modelo_viu
    assert MENSAGEM_DE_PESSOA in tudo_que_o_modelo_viu
    assert "FULANO" not in json.dumps(linhas, ensure_ascii=False)
    assert linhas[-1]["como_cheguei_aqui"][0]["ok"] is False


# ---------------------------------------------------------------- a chave desligada e a configuração


def _nada_saiu(fabrica, banco):
    assert fabrica.modelos == []
    assert _perguntas(banco) == []


def test_desligado_por_padrao(banco, cliente, casa, fabrica, monkeypatch):
    monkeypatch.delenv(chat.VARIAVEL_DE_LIGAR)
    resposta = _perguntar(cliente)
    assert resposta.status_code == 503
    assert resposta.json()["detail"] == rota.MENSAGEM_DESLIGADO
    _nada_saiu(fabrica, banco)


def test_sem_a_chave_do_modelo_nao_sobe(
    banco, cliente, casa, fabrica, monkeypatch, caplog
):
    caplog.set_level(logging.INFO)
    monkeypatch.delenv(chat.VARIAVEL_DA_CHAVE_DO_MODELO)
    resposta = _perguntar(cliente)
    assert resposta.status_code == 503
    assert resposta.json()["detail"] == rota.MENSAGEM_DESLIGADO
    assert "chat_sem_configuracao tem_chave=False" in caplog.text
    _nada_saiu(fabrica, banco)


def test_o_valor_da_chave_do_modelo_nunca_vai_ao_log(cliente, casa, fabrica, caplog):
    caplog.set_level(logging.DEBUG)
    _linhas(_perguntar(cliente))
    assert "chave-de-teste-falsa" not in caplog.text


def test_modelo_sem_preco_nao_sobe(banco, cliente, casa, fabrica, monkeypatch):
    monkeypatch.setenv(chat.VARIAVEL_DO_MODELO, "claude-modelo-inventado")
    resposta = _perguntar(cliente)
    assert resposta.status_code == 503
    _nada_saiu(fabrica, banco)


def test_modelo_da_variavel_e_o_usado(banco, cliente, casa, fabrica, monkeypatch):
    monkeypatch.setenv(chat.VARIAVEL_DO_MODELO, "claude-sonnet-5-5")
    _linhas(_perguntar(cliente))
    (linha,) = _perguntas(banco)
    assert linha.modelo == "claude-sonnet-5-5"


# ---------------------------------------------------------------- quem pode


def test_sem_login_nao_entra(banco, cliente, casa, fabrica):
    anonimo = TestClient(cliente.app)
    resposta = anonimo.post(ROTA, json={"pergunta": PERGUNTA})
    assert resposta.status_code in (401, 403)
    _nada_saiu(fabrica, banco)


def test_conta_sem_organizacao(banco, cliente, fabrica):
    resposta = _perguntar(cliente)
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == rota.MENSAGEM_SEM_ORGANIZACAO
    _nada_saiu(fabrica, banco)


def test_organizacao_sem_chave_ativa(banco, cliente, fabrica):
    _organizacao(banco, _ana(banco), com_chave=False)
    resposta = _perguntar(cliente)
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == rota.MENSAGEM_SEM_CHAVE
    _nada_saiu(fabrica, banco)


def test_ferramentas_fora_do_ar_nao_gastam_a_cota(
    banco, cliente, casa, fabrica, monkeypatch
):
    def recusar(_pedido: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "unavailable"})

    monkeypatch.setattr(
        rota, "transporte_para", lambda _contexto: httpx.MockTransport(recusar)
    )
    resposta = _perguntar(cliente)
    assert resposta.status_code == 503
    assert resposta.json()["detail"] == rota.MENSAGEM_FERRAMENTAS
    _nada_saiu(fabrica, banco)


@pytest.mark.parametrize(
    "corpo",
    [
        {"pergunta": ""},
        {"pergunta": "x" * 2_001},
        {"pergunta": "x", "historico": [{"pergunta": "a", "resposta": "b"}] * 5},
        {"pergunta": "x", "historico": [{"pergunta": "a", "resposta": "b" * 4_001}]},
    ],
)
def test_pedido_fora_do_tamanho(banco, cliente, casa, fabrica, corpo):
    assert cliente.post(ROTA, json=corpo).status_code == 422
    _nada_saiu(fabrica, banco)


# ---------------------------------------------------------------- cota e teto


def test_cota_do_dia(banco, cliente, casa, fabrica):
    _gravar_perguntas(banco, _ana(banco), casa.id, 10, MOMENTO - timedelta(hours=1))
    resposta = _perguntar(cliente)
    assert resposta.status_code == 429
    assert resposta.json()["detail"] == rota.MENSAGEM_COTA_DO_DIA
    assert fabrica.modelos == [] and len(_perguntas(banco)) == 10


def test_cota_estourada_nao_abre_o_catalogo(banco, cliente, casa, fabrica, monkeypatch):
    """Quem já estourou a cota não gasta o limite por minuto da organização com o catálogo."""
    pedidos: list[httpx.Request] = []

    def anotar(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return httpx.Response(503, json={"detail": "unavailable"})

    monkeypatch.setattr(
        rota, "transporte_para", lambda _contexto: httpx.MockTransport(anotar)
    )
    _gravar_perguntas(banco, _ana(banco), casa.id, 10, MOMENTO - timedelta(hours=1))
    assert _perguntar(cliente).status_code == 429
    assert pedidos == []


def test_cota_do_mes(banco, cliente, casa, fabrica):
    _gravar_perguntas(banco, _ana(banco), casa.id, 50, MOMENTO - timedelta(days=5))
    resposta = _perguntar(cliente)
    assert resposta.status_code == 429
    assert resposta.json()["detail"] == rota.MENSAGEM_COTA_DO_MES
    assert fabrica.modelos == []


def test_cota_e_por_conta(banco, cliente, casa, fabrica):
    with banco.begin() as conexao:
        bia = entrar(conexao, "g-bia-903", "bia-903@exemplo.com")[0]
    # respondidas (as em curso seguram a reserva do teto, e 10 delas já o encheriam)
    _gravar_perguntas(banco, bia.id, casa.id, 10, MOMENTO - timedelta(hours=1), custo=1)
    _linhas(_perguntar(cliente))


def test_teto_do_mes_pausa_o_chat_somando_todas_as_contas(
    banco, cliente, casa, fabrica
):
    with banco.begin() as conexao:
        bia = entrar(conexao, "g-bia-903", "bia-903@exemplo.com")[0]
    # outra conta já gastou US$ 49,50: a reserva de mais uma pergunta (US$ 5) passaria de US$ 50
    _gravar_perguntas(
        banco, bia.id, None, 1, MOMENTO - timedelta(days=1), custo=49_500_000
    )
    resposta = _perguntar(cliente)
    assert resposta.status_code == 503
    assert resposta.json()["detail"] == rota.MENSAGEM_PAUSADO
    assert fabrica.modelos == []


def test_teto_do_mes_anterior_nao_conta(banco, cliente, casa, fabrica):
    with banco.begin() as conexao:
        bia = entrar(conexao, "g-bia-903", "bia-903@exemplo.com")[0]
    _gravar_perguntas(
        banco, bia.id, None, 1, MOMENTO - timedelta(days=20), custo=49_500_000
    )
    _linhas(_perguntar(cliente))


# ---------------------------------------------------------------- o estado para a tela (GET /v1/chat/estado)

ROTA_DO_ESTADO = "/api/v1/chat/estado"


def _estado(cliente) -> dict:
    resposta = cliente.get(ROTA_DO_ESTADO)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def test_estado_pronto_com_a_cota_da_conta(banco, cliente, casa, fabrica):
    _gravar_perguntas(
        banco, _ana(banco), casa.id, 2, MOMENTO - timedelta(hours=1), custo=1
    )
    _gravar_perguntas(
        banco, _ana(banco), casa.id, 3, MOMENTO - timedelta(days=5), custo=1
    )
    estado = _estado(cliente)
    assert estado["situacao"] == "pronto" and estado["pode_perguntar"] is True
    assert estado["mensagem"] is None
    assert (estado["perguntas_hoje"], estado["perguntas_no_mes"]) == (2, 5)
    assert estado["perguntas_por_dia"] == LIMITES_DO_CHAT.perguntas_por_dia
    assert estado["caracteres_do_historico"] == LIMITES_DO_CHAT.caracteres_do_historico
    assert estado["exemplos"] and estado["limites"] and estado["como_funciona"]


def test_estado_nao_grava_nem_chama_o_modelo(banco, cliente, casa, fabrica):
    _estado(cliente)
    _nada_saiu(fabrica, banco)


def test_estado_nao_mostra_o_gasto(banco, cliente, casa, fabrica):
    """A tela só sabe se o teto pausou o chat; o gasto em dinheiro não sai da rota."""
    estado = _estado(cliente)
    assert not [
        campo
        for campo in estado
        if "gasto" in campo or "custo" in campo or "teto" in campo
    ]


def test_estado_desligado_por_padrao_explica_o_que_vem(
    banco, cliente, casa, fabrica, monkeypatch
):
    monkeypatch.delenv(chat.VARIAVEL_DE_LIGAR)
    estado = _estado(cliente)
    assert estado["situacao"] == "desligado" and estado["pode_perguntar"] is False
    assert estado["mensagem"] == rota_estado.MENSAGEM_AINDA_NAO_LIGADO


def test_estado_sem_a_chave_do_modelo_e_desligado(
    banco, cliente, casa, fabrica, monkeypatch
):
    monkeypatch.delenv(chat.VARIAVEL_DA_CHAVE_DO_MODELO)
    assert _estado(cliente)["situacao"] == "desligado"


def test_estado_modelo_sem_preco_e_desligado(
    banco, cliente, casa, fabrica, monkeypatch
):
    monkeypatch.setenv(chat.VARIAVEL_DO_MODELO, "claude-modelo-inventado")
    assert _estado(cliente)["situacao"] == "desligado"


def test_estado_sem_organizacao(banco, cliente, fabrica):
    estado = _estado(cliente)
    assert estado["situacao"] == "sem_organizacao"
    assert estado["mensagem"] == rota.MENSAGEM_SEM_ORGANIZACAO


def test_estado_organizacao_sem_chave(banco, cliente, fabrica):
    _organizacao(banco, _ana(banco), com_chave=False)
    estado = _estado(cliente)
    assert estado["situacao"] == "sem_chave"
    assert estado["mensagem"] == rota.MENSAGEM_SEM_CHAVE


def test_estado_cota_do_dia_e_do_mes(banco, cliente, casa, fabrica):
    _gravar_perguntas(
        banco, _ana(banco), casa.id, 10, MOMENTO - timedelta(hours=1), custo=1
    )
    assert _estado(cliente)["mensagem"] == rota.MENSAGEM_COTA_DO_DIA
    _gravar_perguntas(
        banco, _ana(banco), casa.id, 40, MOMENTO - timedelta(days=5), custo=1
    )
    assert (
        _estado(cliente)["situacao"] == "cota_do_dia"
    )  # a do dia vem primeiro, como na pergunta


def test_estado_cota_do_mes(banco, cliente, casa, fabrica):
    _gravar_perguntas(
        banco, _ana(banco), casa.id, 50, MOMENTO - timedelta(days=5), custo=1
    )
    estado = _estado(cliente)
    assert estado["situacao"] == "cota_do_mes"
    assert estado["mensagem"] == rota.MENSAGEM_COTA_DO_MES


def test_estado_pausado_pelo_teto_somando_todas_as_contas(
    banco, cliente, casa, fabrica
):
    with banco.begin() as conexao:
        bia = entrar(conexao, "g-bia-903", "bia-903@exemplo.com")[0]
    _gravar_perguntas(
        banco, bia.id, None, 1, MOMENTO - timedelta(days=1), custo=49_500_000
    )
    estado = _estado(cliente)
    assert estado["situacao"] == "pausado"
    assert estado["mensagem"] == rota.MENSAGEM_PAUSADO


def test_estado_conta_so_as_perguntas_da_propria_conta(banco, cliente, casa, fabrica):
    """Isolamento: as perguntas de outra conta (da mesma organização) não entram na cota da Ana."""
    with banco.begin() as conexao:
        bia = entrar(conexao, "g-bia-903", "bia-903@exemplo.com")[0]
    _gravar_perguntas(banco, bia.id, casa.id, 7, MOMENTO - timedelta(hours=1), custo=1)
    estado = _estado(cliente)
    assert (estado["perguntas_hoje"], estado["perguntas_no_mes"]) == (0, 0)
    assert estado["situacao"] == "pronto"


def test_estado_sem_login_nao_entra(banco, cliente, casa, fabrica):
    anonimo = TestClient(cliente.app)
    assert anonimo.get(ROTA_DO_ESTADO).status_code in (401, 403)


def test_estado_e_a_pergunta_concordam(banco, cliente, casa, fabrica):
    """O que a tela mostra antes é o que a pergunta ouve depois."""
    _gravar_perguntas(
        banco, _ana(banco), casa.id, 10, MOMENTO - timedelta(hours=1), custo=1
    )
    assert _estado(cliente)["mensagem"] == _perguntar(cliente).json()["detail"]
