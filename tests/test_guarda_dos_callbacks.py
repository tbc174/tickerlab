"""Todo callback da versão clássica que grava na conta confere a conta no próprio clique (linha 306;
revisões cruzadas do Codex no #659).

O Streamlit roda o callback antes do corpo do app, onde a sessão relê a conta. Uma aba aberta antes
do bloqueio ainda apagaria, trocaria ou revogaria dados com um clique. Aqui cada callback roda com a
conta já bloqueada no banco: ele não pode chegar ao banco da tela (o `obter_engine` do módulo) e
pede a releitura da conta já nesta execução (`usuario_em = 0`).
"""

import contextlib
import types
import uuid
from pathlib import Path

import pytest
import streamlit as st

from src import relatorios
from src.banco.usuarios import entrar
from telas import dados_da_conta
from telas.compartilhar import _revogar
from telas.conta import entrada, meus_dados
from telas.estrategias import ficha
from telas.relatorios import biblioteca, estudio
from telas.research import (
    alertas,
    diario_de_teses,
    minha_carteira,
    newsletter,
    parametros,
)
from tests.ajudantes_da_conta import bloquear_pelo_admin

PLANILHA = Path(__file__).parent.parent / "conteudo" / "carteira_de_exemplo.xlsx"


class _ArquivoEnviado:
    """O que o `st.file_uploader` deixa na sessão: só o nome e os bytes interessam aqui."""

    name = PLANILHA.name

    def getvalue(self) -> bytes:
        return PLANILHA.read_bytes()


def _versao_antiga():
    return types.SimpleNamespace(versao=1, parametros={})


# (módulo cujo banco não pode ser tocado, callback, argumentos depois do usuário ou None, estado)
CALLBACKS = {
    "atualizar a fotografia da carteira": (
        minha_carteira,
        minha_carteira._guardar_da_tela,
        (),
        {"minha_carteira_arquivo": _ArquivoEnviado()},
    ),
    "revogar a carteira": (
        minha_carteira,
        minha_carteira._revogar_da_tela,
        (),
        {},
    ),
    "apagar um alerta": (alertas, alertas._apagar_alerta, (uuid.uuid4(), "regra"), {}),
    "apagar uma tese": (diario_de_teses, diario_de_teses._apagar, (uuid.uuid4(),), {}),
    "guardar uma tese": (diario_de_teses, diario_de_teses._guardar, (), {}),
    "excluir um PDF": (biblioteca, biblioteca._excluir, (uuid.uuid4(),), {}),
    "cancelar a Newsletter": (newsletter, newsletter._cancelar_a_newsletter, (), {}),
    "inscrever na Newsletter": (
        newsletter,
        newsletter._inscrever_na_newsletter,
        (),
        {"newsletter_email_lista": "favoritos", "newsletter_email_cadencia": "semanal"},
    ),
    "sair das Novidades": (meus_dados, meus_dados._mudar_novidades, (False,), {}),
    "guardar o tema": (meus_dados, meus_dados._guardar_tema, (), {}),
    "voltar a uma versão dos parâmetros": (
        parametros,
        parametros._voltar_versao,
        ("geral", "", _versao_antiga()),
        {},
    ),
    "salvar a configuração do estúdio": (
        estudio,
        estudio._salvar_configuracao,
        (next(iter(relatorios.SECOES)),),
        {},
    ),
    "aceitar os termos": (entrada, entrada._registrar_aceite, (), {}),
    "salvar uma simulação": (
        dados_da_conta,
        dados_da_conta._salvar_simulacao,
        ("backtest", "Simulação", {}),
        {},
    ),
}


@pytest.fixture
def ana_bloqueada(banco):
    with banco.begin() as conexao:
        ana = entrar(conexao, "g-ana-da-guarda", "ana-guarda@exemplo.com", "Ana")[0]
    bloquear_pelo_admin(banco, ana.id)
    return ana  # o objeto é o que a aba guardou antes do bloqueio


def _sem_banco_da_tela(monkeypatch, modulo):
    tocou = []

    def anotar():
        tocou.append(modulo.__name__)
        raise RuntimeError("o callback chegou ao banco")

    monkeypatch.setattr(modulo, "obter_engine", anotar)
    return tocou


@pytest.mark.parametrize("acao", list(CALLBACKS))
def test_callback_da_aba_aberta_nao_grava_na_conta_bloqueada(
    acao, ana_bloqueada, monkeypatch
):
    modulo, callback, argumentos, estado = CALLBACKS[acao]
    sessao = {"usuario": ana_bloqueada, "usuario_em": 123.0, **estado}
    monkeypatch.setattr(st, "session_state", sessao)
    tocou = _sem_banco_da_tela(monkeypatch, modulo)
    with contextlib.suppress(RuntimeError):  # sem a guarda, o callback para no banco
        callback(ana_bloqueada, *argumentos)
    assert tocou == []
    assert sessao["usuario_em"] == 0


def test_revogar_um_link_da_aba_aberta_nao_chega_ao_banco(ana_bloqueada, monkeypatch):
    from telas import compartilhar

    sessao = {"usuario": ana_bloqueada, "usuario_em": 123.0}
    monkeypatch.setattr(st, "session_state", sessao)
    tocou = _sem_banco_da_tela(monkeypatch, compartilhar)
    with contextlib.suppress(RuntimeError):
        _revogar(ana_bloqueada.id, uuid.uuid4())
    assert tocou == [] and sessao["usuario_em"] == 0


def test_tolerancia_da_aba_aberta_nao_grava_na_conta_bloqueada(
    ana_bloqueada, monkeypatch
):
    sessao = {
        "usuario": ana_bloqueada,
        "usuario_em": 123.0,
        ficha.CHAVE_DA_TOLERANCIA: 20,
    }
    monkeypatch.setattr(st, "session_state", sessao)
    tocou = _sem_banco_da_tela(monkeypatch, ficha)
    with contextlib.suppress(RuntimeError):
        ficha._guardar_tolerancia()
    assert tocou == [] and sessao["usuario_em"] == 0


def test_sem_login_o_alerta_local_ainda_se_apaga(monkeypatch):
    """No modo local não há conta para bloquear: o alerta guardado só na sessão sai."""
    regra = types.SimpleNamespace(nome="regra")
    sessao = {"usuario": None, "alertas_locais": [regra]}
    monkeypatch.setattr(st, "session_state", sessao)
    alertas._apagar_alerta(None, None, "regra")
    assert sessao["alertas_locais"] == []
