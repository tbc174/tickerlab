"""LGPD: aceite dos termos, exportação dos meus dados e exclusão da conta."""

import json
import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
import stripe

from src import auditoria, conformidade
from src.banco import dados_do_usuario as repo
from src.banco import tentativas
from src.banco.modelo import assinaturas, metadata
from src.banco.usuarios import buscar_por_id, entrar
from src.cobranca import Assinatura, encerrar_cobranca


@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


@pytest.fixture
def ana(conexao):
    return entrar(
        conexao, "ana", "ana@exemplo.com", "Ana", "https://exemplo.com/f.png"
    )[0]


@pytest.fixture
def bia(conexao):
    return entrar(conexao, "bia", "bia@exemplo.com", "Bia")[0]


# --- aceite dos termos ---
def test_usuario_novo_precisa_aceitar(ana):
    assert conformidade.precisa_aceitar_os_termos(ana)


def test_aceitar_grava_versao_data_e_auditoria(conexao, ana):
    conformidade.registrar_aceite(conexao, ana.id)
    depois = buscar_por_id(conexao, ana.id)
    assert depois.termos_versao == conformidade.VERSAO_DOS_TERMOS
    assert depois.termos_aceitos_em is not None
    assert not conformidade.precisa_aceitar_os_termos(depois)
    registro = auditoria.listar_recentes(conexao)[0]
    assert registro.acao == auditoria.ACAO_TERMOS_ACEITOS
    assert registro.detalhes == {"versao": conformidade.VERSAO_DOS_TERMOS}


def test_nova_versao_dos_termos_pede_novo_aceite(conexao, ana, monkeypatch):
    conformidade.registrar_aceite(conexao, ana.id)
    monkeypatch.setattr(conformidade, "VERSAO_DOS_TERMOS", "2099-01-01")
    assert conformidade.precisa_aceitar_os_termos(buscar_por_id(conexao, ana.id))


def test_o_aceite_continua_depois_de_novo_login(conexao, ana):
    conformidade.registrar_aceite(conexao, ana.id)
    de_novo = entrar(conexao, "ana", "ana@exemplo.com", "Ana Souza")[0]
    assert not conformidade.precisa_aceitar_os_termos(de_novo)


# --- textos ---
@pytest.mark.parametrize("nome", ["termos", "privacidade"])
def test_textos_legais_existem_e_citam_o_essencial(nome):
    texto = conformidade.carregar_texto(nome)
    assert len(texto) > 800
    # o que o TickerLab é: plataforma de inteligência financeira, por assinatura
    assert "inteligência financeira" in texto.lower()


def test_termos_dizem_que_nada_e_recomendacao_de_investimento():
    termos = conformidade.carregar_texto("termos").lower()
    assert "nada aqui é recomendação de investimento" in termos
    assert "projeto educacional" not in termos  # produto comercial desde 13/10/2026


def test_texto_desconhecido():
    with pytest.raises(ValueError):
        conformidade.carregar_texto("../app")


def test_politica_de_privacidade_cobre_os_dados_e_os_direitos():
    texto = conformidade.carregar_texto("privacidade").lower()
    for termo in ("google", "stripe", "e-mail", "exportar", "apagar", "lgpd", "cookie"):
        assert termo in texto, termo


# --- exportar ---
def test_exportar_traz_tudo_da_pessoa_e_so_dela(conexao, ana, bia):
    repo.salvar_preferencias(conexao, ana.id, {"periodo": "5y"})
    repo.salvar_favoritos(conexao, ana.id, ["AAPL", "PETR4.SA"])
    repo.salvar_simulacao(
        conexao, ana.id, "backtest", "Minha", {"a": 1}, {"numeros": {"x": "1"}}
    )
    repo.salvar_favoritos(conexao, bia.id, ["VALE3.SA"])
    repo.salvar_simulacao(conexao, bia.id, "backtest", "Da Bia", {}, {})
    tentativas.registrar_tentativa(conexao, ana.id, "PETR4.SA", "a" * 64)
    tentativas.registrar_tentativa(conexao, bia.id, "VALE3.SA", "b" * 64)
    dados = conformidade.exportar_meus_dados(conexao, ana.id)
    assert dados["tentativas_por_ativo"] == {"PETR4.SA": 1}
    assert dados["perfil"]["email"] == "ana@exemplo.com"
    assert dados["preferencias"] == {"periodo": "5y"}
    assert dados["favoritos"] == ["AAPL", "PETR4.SA"]
    assert [s["nome"] for s in dados["simulacoes"]] == ["Minha"]
    texto = json.dumps(dados)
    assert (
        "bia@exemplo.com" not in texto
        and "Da Bia" not in texto
        and "VALE3" not in texto
    )


def test_politica_de_privacidade_cita_as_tentativas_do_backtest():
    texto = conformidade.carregar_texto("privacidade")
    assert "tentativas" in texto and "SHA-256" in texto


def test_exportar_vira_json_e_registra_na_auditoria(conexao, ana):
    dados = conformidade.exportar_meus_dados(conexao, ana.id)
    json.dumps(dados)  # não pode ter nada que o JSON não aceite (datas, UUIDs)
    assert auditoria.listar_recentes(conexao)[0].acao == auditoria.ACAO_DADOS_EXPORTADOS


def test_exportar_nao_vaza_ids_do_stripe(conexao, ana):
    conexao.execute(
        sa.insert(assinaturas).values(
            usuario_id=ana.id,
            stripe_customer_id="cus_SECRETO",
            stripe_subscription_id="sub_SECRETO",
            status="active",
            cancela_no_fim=False,
            evento_em=1,
        )
    )
    dados = conformidade.exportar_meus_dados(conexao, ana.id)
    assert dados["assinatura"]["status"] == "active"
    assert "SECRETO" not in json.dumps(dados)


def test_exportar_de_quem_nao_existe(conexao):
    with pytest.raises(LookupError):
        conformidade.exportar_meus_dados(conexao, uuid.uuid4())


# --- apagar a conta ---
def test_apagar_conta_remove_tudo_da_pessoa_e_so_dela(conexao, ana, bia):
    repo.salvar_favoritos(conexao, ana.id, ["AAPL"])
    repo.salvar_preferencias(conexao, ana.id, {"periodo": "5y"})
    repo.salvar_simulacao(conexao, ana.id, "backtest", "Minha", {}, {})
    repo.salvar_simulacao(conexao, bia.id, "backtest", "Da Bia", {}, {})
    assert conformidade.apagar_conta(conexao, ana.id) is True
    assert buscar_por_id(conexao, ana.id) is None
    assert repo.listar_simulacoes(conexao, ana.id) == []
    assert repo.listar_favoritos(conexao, ana.id) == []
    assert repo.carregar_preferencias(conexao, ana.id) == {}
    assert len(repo.listar_simulacoes(conexao, bia.id)) == 1  # a da Bia continua


def test_apagar_deixa_so_um_registro_sem_dado_pessoal(conexao, ana):
    conformidade.registrar_aceite(conexao, ana.id)  # a auditoria dela aponta para ela
    conformidade.apagar_conta(conexao, ana.id)
    registros = auditoria.listar_recentes(conexao)
    assert registros[0].acao == auditoria.ACAO_CONTA_APAGADA
    assert registros[0].alvo_id == ana.id and registros[0].ator_id is None
    assert all(r.ator_id is None for r in registros)  # os do aceite perderam o vínculo
    texto = str([(r.detalhes, r.acao) for r in registros])
    assert "ana@exemplo.com" not in texto


def test_apagar_quem_nao_existe(conexao):
    assert conformidade.apagar_conta(conexao, uuid.uuid4()) is False
    assert auditoria.listar_recentes(conexao) == []


# --- encerrar a cobrança no Stripe ---
class StripeFalso:
    def __init__(self, falha_ao_cancelar=False, falha_ao_apagar=False):
        self.chamadas = []

        def cancelar(id_):
            self.chamadas.append(("cancelar", id_))
            if falha_ao_cancelar:
                raise stripe.InvalidRequestError("já cancelada", "id")

        def apagar(id_):
            self.chamadas.append(("apagar", id_))
            if falha_ao_apagar:
                raise stripe.InvalidRequestError("não existe", "id")

        self.v1 = SimpleNamespace(
            subscriptions=SimpleNamespace(cancel=cancelar),
            customers=SimpleNamespace(delete=apagar),
        )


def _assinatura(status="active"):
    return Assinatura(uuid.uuid4(), "cus_1", "sub_1", status, None, False)


def test_encerrar_cancela_a_assinatura_e_apaga_o_cliente():
    stripe_falso = StripeFalso()
    encerrar_cobranca(_assinatura(), cliente=stripe_falso)
    assert stripe_falso.chamadas == [("cancelar", "sub_1"), ("apagar", "cus_1")]


def test_encerrar_nao_cancela_de_novo_o_que_ja_esta_cancelado():
    stripe_falso = StripeFalso()
    encerrar_cobranca(_assinatura("canceled"), cliente=stripe_falso)
    assert stripe_falso.chamadas == [("apagar", "cus_1")]


def test_encerrar_tolera_o_que_ja_nao_existe_no_stripe():
    stripe_falso = StripeFalso(falha_ao_cancelar=True, falha_ao_apagar=True)
    encerrar_cobranca(_assinatura(), cliente=stripe_falso)  # não levanta erro


def test_encerrar_sem_assinatura_nao_faz_nada():
    stripe_falso = StripeFalso()
    encerrar_cobranca(None, cliente=stripe_falso)
    assert stripe_falso.chamadas == []
