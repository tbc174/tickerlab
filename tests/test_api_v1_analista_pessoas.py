"""`POST /v1/analista/ficha/pessoas` (linha 808): os sócios pessoa física, só para a organização que pode.

Riscos que estes testes pegam: (1) a conta de outra organização, ou sem organização, ver pessoa; (2) a rota
dizer, pela resposta ou pelo trabalho que faz, se o CNPJ tem sócio para quem não pode ver; (3) a permissão
valer depois de suspensa ou vencida; (4) o CNPJ ou um nome ir para a auditoria ou para o log; (5) sair coluna
além de nome, qualificação e data de entrada. Todo nome aqui é inventado.
"""

import logging
from datetime import timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from src import auditoria
from src.analista import pessoa
from src.api_v1 import analista, analista_pessoas
from src.banco import chaves_da_api as cb
from src.banco import membros_da_organizacao as mb
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.banco.usuarios import entrar, mudar_plano
from src.conformidade import registrar_aceite
from tests import test_analista_pessoa as acervo_de_mentira
from tests import test_api_v1_rotas as rotas
from tests.ajudantes_da_api import da_sessao

chave = rotas.chave
cliente = rotas.cliente  # a Ana, logada
ROTA = "/api/v1/analista/ficha/pessoas"
INEXISTENTE = "/api/v1/analista/ficha/nao-existe"
EMPRESA = acervo_de_mentira.EMPRESA


@pytest.fixture(autouse=True)
def acervo(tmp_path, monkeypatch, cliente, banco):
    """O acervo de pessoa de mentira neste servidor, o dia fixo e a Ana no Pro."""
    pasta = acervo_de_mentira._acervo(
        tmp_path / "acervo_pessoa", acervo_de_mentira.LINHAS
    )
    monkeypatch.setenv(pessoa.VARIAVEL, str(pasta))
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "pro")
    return pasta


@pytest.fixture
def dia():
    return analista.hoje()


def _organizacao_com(banco, dia, nome, conta_id, *, permite=True, ate=None):
    """Uma organização com a conta de membro e, se `permite`, a permissão vigente desde ontem."""
    with banco.begin() as conexao:
        admin = entrar(conexao, "g-admin-808", "admin-808@exemplo.com")[0]
        organizacao = cb.criar_organizacao(conexao, nome=nome, ator_id=admin.id)
        mb.vincular_membro(
            conexao,
            organizacao_id=organizacao.id,
            usuario_id=conta_id,
            ator_id=admin.id,
        )
        if permite:
            cb.conceder_direito(
                conexao,
                organizacao_id=organizacao.id,
                conjunto=mb.CONJUNTO_DE_PESSOA_NA_TELA,
                finalidade=mb.FINALIDADE_DA_TELA,
                vigente_desde=dia - timedelta(days=1),
                vigente_ate=ate,
                ator_id=admin.id,
            )
    return organizacao, admin


@pytest.fixture
def casa(banco, dia):
    """A organização da Ana, com a permissão."""
    return _organizacao_com(banco, dia, "Casa Exemplo", rotas._id_da_ana_no(banco))[0]


@pytest.fixture
def da_bia(cliente, banco):
    """Outra conta logada no Pro, com os termos aceitos (a Bia)."""
    with banco.begin() as conexao:
        bia = entrar(conexao, "g-bia-808", "bia-808@exemplo.com")[0]
        registrar_aceite(conexao, bia.id)
        mudar_plano(conexao, bia.id, "pro")
    return bia, TestClient(cliente.app, headers=da_sessao(banco, bia))


def _nao_le(*_argumentos, **_nomeados):
    raise AssertionError(
        "o acervo de pessoa não pode ser tocado para quem não pode ver"
    )


def _vistas(banco) -> list[sa.Row]:
    tabela = tabela_da_auditoria
    with banco.connect() as conexao:
        return list(
            conexao.execute(
                sa.select(tabela).where(tabela.c.acao == auditoria.ACAO_PESSOA_VISTA)
            )
        )


# ---------------------------------------------------------------- quem pode


def test_membro_da_organizacao_com_a_permissao_ve_os_socios(cliente, casa):
    resposta = cliente.post(ROTA, json={"cnpj": "11.222.333/0001-81"})
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["estado"] == analista_pessoas.PRONTA
    assert [s["nome"] for s in dados["socios"]] == [
        "BELTRANO EXEMPLO",
        "FULANA EXEMPLO",
    ]
    assert all(set(s) == {"nome", "qualificacao", "entrou_em"} for s in dados["socios"])
    assert dados["total"] == 2
    assert dados["fonte"]["fonte"] == "rfb-cnpj" and dados["fonte"]["mes_do_retrato"]
    assert dados["limites"] == list(pessoa.LIMITES)
    assert resposta.headers["Cache-Control"] == "no-store"


def test_empresa_sem_socio_pessoa_fisica_sai_sem_socios(cliente, casa):
    dados = cliente.post(ROTA, json={"cnpj": "11000000000100"}).json()
    assert dados["estado"] == analista_pessoas.SEM_SOCIOS
    assert dados["socios"] == [] and dados["total"] == 0


def test_cnpj_invalido_422_sem_repetir_o_texto(cliente, casa):
    for cnpj in ("123", "x" * 500, "../../etc/passwd"):
        resposta = cliente.post(ROTA, json={"cnpj": cnpj})
        assert resposta.status_code == 422
        assert resposta.json()["detail"] == analista.CNPJ_INVALIDO


@pytest.mark.parametrize("corpo", [{}, {"cnpj": 12}, ["lista"], b"{", b""])
def test_corpo_invalido_de_quem_pode_422_sem_repetir_o_que_veio(cliente, casa, corpo):
    resposta = _enviar(cliente, ROTA, corpo)
    assert resposta.status_code == 422
    assert resposta.json() == {"detail": analista.CNPJ_INVALIDO}


def test_acervo_fora_deste_servidor_503(cliente, casa, monkeypatch):
    monkeypatch.delenv(pessoa.VARIAVEL)
    resposta = cliente.post(ROTA, json={"cnpj": EMPRESA})
    assert resposta.status_code == 503
    assert resposta.json()["detail"] == analista.BASE_FORA_DO_AR


# ---------------------------------------------------------------- quem não pode


JSON = {"content-type": "application/json"}


def _enviar(cliente, rota, corpo):
    """`corpo` em bytes vai cru (JSON malformado); o resto vai como JSON."""
    if isinstance(corpo, bytes):
        return cliente.post(rota, content=corpo, headers=JSON)
    return cliente.post(rota, json=corpo)


def _igual_a_rota_que_nao_existe(cliente, corpo) -> None:
    resposta = _enviar(cliente, ROTA, corpo)
    inexistente = _enviar(cliente, INEXISTENTE, corpo)
    assert resposta.status_code == inexistente.status_code == 404
    assert resposta.content == inexistente.content
    assert resposta.headers["content-type"] == inexistente.headers["content-type"]
    assert "Cache-Control" not in resposta.headers


CORPOS = [
    {"cnpj": EMPRESA},  # tem sócio no acervo
    {"cnpj": "99000000000100"},  # não tem
    {"cnpj": "isto não é um CNPJ"},
    {"cnpj": "x" * 500},
    {},  # sem o campo
    {"cnpj": 12},
    ["lista"],
    b"{",  # JSON malformado
    b"",
]


@pytest.mark.parametrize("corpo", CORPOS)
def test_conta_sem_organizacao_recebe_o_404_da_rota_inexistente(
    cliente, monkeypatch, corpo
):
    monkeypatch.setattr(pessoa, "socios_da_empresa", _nao_le)
    monkeypatch.setattr(pessoa, "pasta_do_acervo", _nao_le)
    _igual_a_rota_que_nao_existe(cliente, corpo)


@pytest.mark.parametrize("corpo", CORPOS)
def test_duas_organizacoes_uma_ve_a_outra_nao(cliente, casa, da_bia, banco, dia, corpo):
    bia, cliente_da_bia = da_bia
    _organizacao_com(banco, dia, "Outra Exemplo", bia.id, permite=False)
    assert cliente.post(ROTA, json={"cnpj": EMPRESA}).status_code == 200
    _igual_a_rota_que_nao_existe(cliente_da_bia, corpo)


def test_quem_nao_pode_nao_faz_o_servidor_tocar_o_acervo(
    cliente, da_bia, banco, dia, monkeypatch
):
    """O tempo não denuncia: sem a permissão, o trabalho do servidor é o mesmo para qualquer CNPJ (nenhum
    arquivo aberto, nenhum CNPJ validado), e nada vai para a auditoria."""
    bia, cliente_da_bia = da_bia
    _organizacao_com(banco, dia, "Outra Exemplo", bia.id, permite=False)
    monkeypatch.setattr(pessoa, "socios_da_empresa", _nao_le)
    monkeypatch.setattr(pessoa, "pasta_do_acervo", _nao_le)
    monkeypatch.setattr(pessoa.cnpj_, "normalizar_cnpj", _nao_le)
    for corpo in CORPOS:
        assert _enviar(cliente_da_bia, ROTA, corpo).status_code == 404
        assert _enviar(cliente, ROTA, corpo).status_code == 404  # sem organização
    assert _vistas(banco) == []


def test_permissao_vencida_suspensa_ou_organizacao_suspensa_404(
    cliente, banco, dia, monkeypatch
):
    ana = rotas._id_da_ana_no(banco)
    organizacao, admin = _organizacao_com(banco, dia, "Casa Exemplo", ana)
    assert cliente.post(ROTA, json={"cnpj": EMPRESA}).status_code == 200
    with banco.begin() as conexao:
        cb.suspender_organizacao(
            conexao, organizacao_id=organizacao.id, motivo="contrato", ator_id=admin.id
        )
    assert cliente.post(ROTA, json={"cnpj": EMPRESA}).status_code == 404
    with banco.begin() as conexao:
        cb.reativar_organizacao(
            conexao, organizacao_id=organizacao.id, ator_id=admin.id
        )
    assert cliente.post(ROTA, json={"cnpj": EMPRESA}).status_code == 200
    monkeypatch.setattr(analista, "hoje", lambda: dia - timedelta(days=30))
    assert (
        cliente.post(ROTA, json={"cnpj": EMPRESA}).status_code == 404
    )  # antes da vigência


def test_desvinculada_a_conta_deixa_de_ver(cliente, banco, dia):
    ana = rotas._id_da_ana_no(banco)
    organizacao, admin = _organizacao_com(banco, dia, "Casa Exemplo", ana)
    assert cliente.post(ROTA, json={"cnpj": EMPRESA}).status_code == 200
    with banco.begin() as conexao:
        mb.desvincular_membro(
            conexao, organizacao_id=organizacao.id, usuario_id=ana, ator_id=admin.id
        )
    assert cliente.post(ROTA, json={"cnpj": EMPRESA}).status_code == 404


def test_sem_login_401_e_plano_sem_a_ficha_403(cliente, casa, banco, monkeypatch):
    monkeypatch.setattr(pessoa, "socios_da_empresa", _nao_le)
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "gratuito")
    assert cliente.post(ROTA, json={"cnpj": EMPRESA}).status_code == 403
    cliente.headers.pop("Cookie")
    assert cliente.post(ROTA, json={"cnpj": EMPRESA}).status_code == 401


def test_so_post(cliente, casa):
    assert cliente.get(ROTA).status_code == 405


# ---------------------------------------------------------------- o que fica registrado


def test_auditoria_leva_conta_organizacao_tipo_e_linhas_sem_cnpj_nem_nome(
    cliente, casa, banco
):
    cliente.post(ROTA, json={"cnpj": EMPRESA})
    cliente.post(ROTA, json={"cnpj": "11000000000100"})
    vistas = _vistas(banco)
    assert [v.detalhes for v in vistas] == [
        {"tipo": "socios", "linhas": 2},
        {"tipo": "socios", "linhas": 0},
    ]
    assert {v.ator_id for v in vistas} == {rotas._id_da_ana_no(banco)}
    assert {v.alvo_id for v in vistas} == {casa.id}
    tudo = str([tuple(v) for v in vistas])
    assert "11222333" not in tudo and "EXEMPLO" not in tudo


def test_sem_auditoria_nada_sai(cliente, casa, monkeypatch):
    def falhar(*_argumentos, **_nomeados):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(analista_pessoas.auditoria, "registrar", falhar)
    with pytest.raises(RuntimeError):
        cliente.post(ROTA, json={"cnpj": EMPRESA})


def test_o_log_nao_leva_cnpj_nem_nome(cliente, casa, caplog):
    with caplog.at_level(logging.DEBUG):
        cliente.post(ROTA, json={"cnpj": EMPRESA})
        cliente.post(ROTA, json={"cnpj": "123"})
    assert "11222333" not in caplog.text and "EXEMPLO" not in caplog.text
    assert "sócios da ficha: pronta" in caplog.text
