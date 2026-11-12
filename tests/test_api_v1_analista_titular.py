"""`POST /v1/analista/ficha/titular` (linha 808): o titular do empresário individual e do MEI, só para a
organização que pode.

Riscos que estes testes pegam: (1) a conta de outra organização, ou sem organização, ver o titular; (2) a
rota dizer, pela resposta ou pelo trabalho que faz, algo sobre o CNPJ para quem não pode ver; (3) o CNPJ ou o
nome ir para a auditoria ou para o log; (4) sair coluna além do nome (CPF, pseudônimo); (5) mostrar quem se
opôs; (6) a API por chave, a CLI ou o conector terem a rota. Todo nome aqui é inventado.
"""

import logging
from pathlib import Path

import pytest

from src.analista import pessoa
from src.api_v1 import analista, analista_pessoas
from src.banco.usuarios import mudar_plano
from tests import test_api_v1_analista_pessoas as dos_socios
from tests import test_api_v1_rotas as rotas
from tests import test_montar_acervo_pessoa as montar_de_mentira

chave = rotas.chave
cliente = rotas.cliente  # a Ana, logada
dia = dos_socios.dia
casa = dos_socios.casa  # a organização da Ana, com a permissão
da_bia = dos_socios.da_bia
ROTA = "/api/v1/analista/ficha/titular"
INEXISTENTE = "/api/v1/analista/ficha/nao-existe"
INDIVIDUAL = "22333444000181"  # a raiz do empresário individual do acervo de mentira
SOCIEDADE = "11222333000181"


@pytest.fixture(autouse=True)
def acervo(tmp_path, monkeypatch, cliente, banco):
    """O acervo de pessoa montado de mentira (sócios, titular e contato) e a Ana no Pro."""
    cnpj, bruto = montar_de_mentira._acervo(tmp_path / "origem")
    destino = tmp_path / "fora" / "acervo_pessoa"
    montar_de_mentira.montar.carregar(
        cnpj, bruto, destino, montar_de_mentira.AGORA, montar_de_mentira.SEM_OPOSTOS
    )
    monkeypatch.setenv(pessoa.VARIAVEL, str(destino))
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "pro")
    return destino


def _nao_le_nada(monkeypatch) -> None:
    for nome in ("titular_da_empresa", "pasta_do_acervo"):
        monkeypatch.setattr(pessoa, nome, dos_socios._nao_le)
    monkeypatch.setattr(pessoa.cnpj_, "normalizar_cnpj", dos_socios._nao_le)


def _igual_a_rota_que_nao_existe(cliente, corpo) -> None:
    resposta = dos_socios._enviar(cliente, ROTA, corpo)
    inexistente = dos_socios._enviar(cliente, INEXISTENTE, corpo)
    assert resposta.status_code == inexistente.status_code == 404
    assert resposta.content == inexistente.content
    assert resposta.headers["content-type"] == inexistente.headers["content-type"]
    assert "Cache-Control" not in resposta.headers


CORPOS = [{"cnpj": INDIVIDUAL}, *dos_socios.CORPOS]

# ---------------------------------------------------------------- quem pode


def test_membro_da_organizacao_com_a_permissao_ve_o_titular(cliente, casa):
    resposta = cliente.post(ROTA, json={"cnpj": "22.333.444/0001-81"})
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["estado"] == analista_pessoas.PRONTA
    assert dados["titulares"] == [{"nome": "BELTRANO EXEMPLO"}]
    assert dados["total"] == 1
    assert "id_pessoa" not in resposta.text and "88800000127" not in resposta.text
    assert dados["fonte"]["fonte"] == "rfb-cnpj" and dados["fonte"]["mes_do_retrato"]
    assert dados["limites"] == list(pessoa.LIMITES_DO_TITULAR)
    assert resposta.headers["Cache-Control"] == "no-store"


def test_sociedade_nao_tem_titular(cliente, casa):
    dados = cliente.post(ROTA, json={"cnpj": SOCIEDADE}).json()
    assert dados["estado"] == analista_pessoas.SEM_TITULAR
    assert dados["titulares"] == [] and dados["total"] == 0


@pytest.mark.parametrize("corpo", [{"cnpj": "123"}, {"cnpj": "x" * 500}, {}, b"{"])
def test_pedido_invalido_de_quem_pode_422_sem_repetir_o_que_veio(cliente, casa, corpo):
    resposta = dos_socios._enviar(cliente, ROTA, corpo)
    assert resposta.status_code == 422
    assert resposta.json() == {"detail": analista.CNPJ_INVALIDO}


def test_servidor_sem_a_tabela_de_individuais_503(cliente, casa, acervo, tmp_path):
    (acervo / pessoa.INDIVIDUAIS).rename(tmp_path / "sem_individuais")
    resposta = cliente.post(ROTA, json={"cnpj": INDIVIDUAL})
    assert resposta.status_code == 503
    assert resposta.json()["detail"] == analista.BASE_FORA_DO_AR


# ---------------------------------------------------------------- quem não pode


@pytest.mark.parametrize("corpo", CORPOS)
def test_conta_sem_organizacao_recebe_o_404_da_rota_inexistente(
    cliente, monkeypatch, corpo
):
    _nao_le_nada(monkeypatch)
    _igual_a_rota_que_nao_existe(cliente, corpo)


@pytest.mark.parametrize("corpo", CORPOS)
def test_duas_organizacoes_uma_ve_a_outra_nao(cliente, casa, da_bia, banco, dia, corpo):
    bia, cliente_da_bia = da_bia
    dos_socios._organizacao_com(banco, dia, "Outra Exemplo", bia.id, permite=False)
    assert cliente.post(ROTA, json={"cnpj": INDIVIDUAL}).status_code == 200
    _igual_a_rota_que_nao_existe(cliente_da_bia, corpo)


def test_quem_nao_pode_nao_faz_o_servidor_tocar_o_acervo(
    cliente, da_bia, banco, dia, monkeypatch
):
    bia, cliente_da_bia = da_bia
    dos_socios._organizacao_com(banco, dia, "Outra Exemplo", bia.id, permite=False)
    _nao_le_nada(monkeypatch)
    for corpo in CORPOS:
        assert dos_socios._enviar(cliente_da_bia, ROTA, corpo).status_code == 404
        assert dos_socios._enviar(cliente, ROTA, corpo).status_code == 404
    assert dos_socios._vistas(banco) == []


def test_permissao_suspensa_ou_desvinculada_404(cliente, banco, dia):
    ana = rotas._id_da_ana_no(banco)
    organizacao, admin = dos_socios._organizacao_com(banco, dia, "Casa Exemplo", ana)
    assert cliente.post(ROTA, json={"cnpj": INDIVIDUAL}).status_code == 200
    with banco.begin() as conexao:
        dos_socios.mb.desvincular_membro(
            conexao, organizacao_id=organizacao.id, usuario_id=ana, ator_id=admin.id
        )
    assert cliente.post(ROTA, json={"cnpj": INDIVIDUAL}).status_code == 404


def test_sem_login_401_plano_sem_a_ficha_403_e_so_post(cliente, casa, banco):
    assert cliente.get(ROTA).status_code == 405
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "gratuito")
    assert cliente.post(ROTA, json={"cnpj": INDIVIDUAL}).status_code == 403
    cliente.headers.pop("Cookie")
    assert cliente.post(ROTA, json={"cnpj": INDIVIDUAL}).status_code == 401


# ---------------------------------------------------------------- o que fica registrado


def test_auditoria_leva_o_tipo_e_as_linhas_sem_cnpj_nem_nome(cliente, casa, banco):
    cliente.post(ROTA, json={"cnpj": INDIVIDUAL})
    cliente.post(ROTA, json={"cnpj": SOCIEDADE})
    vistas = dos_socios._vistas(banco)
    assert [v.detalhes for v in vistas] == [
        {"tipo": "titular", "linhas": 1},
        {"tipo": "titular", "linhas": 0},
    ]
    assert {v.ator_id for v in vistas} == {rotas._id_da_ana_no(banco)}
    assert {v.alvo_id for v in vistas} == {casa.id}
    tudo = str([tuple(v) for v in vistas]).lower()
    assert "22333444" not in tudo and "beltrano" not in tudo


def test_sem_auditoria_nada_sai(cliente, casa, monkeypatch):
    def falhar(*_argumentos, **_nomeados):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(analista_pessoas.auditoria, "registrar", falhar)
    with pytest.raises(RuntimeError):
        cliente.post(ROTA, json={"cnpj": INDIVIDUAL})


def test_o_log_nao_leva_cnpj_nem_nome(cliente, casa, caplog):
    with caplog.at_level(logging.DEBUG):
        cliente.post(ROTA, json={"cnpj": INDIVIDUAL})
        cliente.post(ROTA, json={"cnpj": "123"})
    texto = caplog.text.lower()
    assert "22333444" not in texto and "beltrano" not in texto
    assert "titular da ficha: pronta" in texto


# ------------------------------------------- oposição do titular (linha 829)


def test_titular_que_se_opos_nao_aparece_para_a_organizacao_com_a_permissao(
    cliente, casa, tmp_path, monkeypatch
):
    cnpj, bruto = montar_de_mentira._acervo(tmp_path / "origem2")
    destino = tmp_path / "fora2" / "acervo_pessoa"
    opostos = montar_de_mentira._opostos(("88800000127", "BELTRANO EXEMPLO"))
    montar_de_mentira.montar.carregar(
        cnpj, bruto, destino, montar_de_mentira.AGORA, opostos
    )
    monkeypatch.setenv(pessoa.VARIAVEL, str(destino))
    dados = cliente.post(ROTA, json={"cnpj": INDIVIDUAL}).json()
    assert dados["estado"] == analista_pessoas.SEM_TITULAR and dados["titulares"] == []


# ------------------------------------------- só a tela com login (API por chave, CLI e conector)


def test_so_a_rota_da_tela_com_login_le_o_acervo_de_pessoa():
    """A API por chave, a CLI, o site e o conector não leem o acervo de pessoa: fora `src/api_v1/analista_pessoas.py`
    (que confere a permissão) e o registro das rotas, nenhum arquivo de `src/`, `scripts/` ou `cli/` o importa."""
    raiz = Path(__file__).resolve().parent.parent
    permitidos = {
        raiz / "src" / "analista" / "pessoa.py",
        raiz / "src" / "api_v1" / "analista_pessoas.py",
        raiz / "src" / "api_v1" / "acesso.py",
        raiz / "src" / "api.py",
    }
    donos = set()
    for pasta in ("src", "scripts", "cli"):
        for arquivo in (raiz / pasta).rglob("*.py"):
            texto = arquivo.read_text(encoding="utf-8", errors="ignore")
            if "analista.pessoa" in texto or "analista import pessoa" in texto:
                donos.add(arquivo)
    assert donos <= permitidos, sorted(str(d) for d in donos - permitidos)
