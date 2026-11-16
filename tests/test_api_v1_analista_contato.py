"""`POST /v1/analista/ficha/contato` (linha 808): o contato do estabelecimento, só para a organização que pode.

Riscos que estes testes pegam: (1) a conta de outra organização, ou sem organização, ver endereço, telefone
ou e-mail; (2) a rota dizer, pela resposta ou pelo trabalho que faz, algo sobre o CNPJ para quem não pode
ver; (3) o CNPJ ou o contato ir para a auditoria ou para o log; (4) sair coluna além do contato. Todo
endereço, telefone e e-mail aqui é inventado.
"""

import json
import logging

import pandas as pd
import pytest

from src.analista import pessoa
from src.api_v1 import analista, analista_pessoas
from src.banco.usuarios import mudar_plano
from tests import test_analista_pessoa as acervo_de_mentira
from tests import test_api_v1_analista_pessoas as dos_socios
from tests import test_api_v1_rotas as rotas

chave = rotas.chave
cliente = rotas.cliente  # a Ana, logada
dia = dos_socios.dia
casa = dos_socios.casa  # a organização da Ana, com a permissão
da_bia = dos_socios.da_bia
ROTA = "/api/v1/analista/ficha/contato"
INEXISTENTE = "/api/v1/analista/ficha/nao-existe"
EMPRESA = acervo_de_mentira.EMPRESA
CAMPOS = {
    "cnpj", "matriz", "logradouro", "bairro", "cep", "municipio", "uf", "telefones", "email",
}  # fmt: skip


@pytest.fixture(autouse=True)
def acervo(tmp_path, monkeypatch, cliente, banco):
    """O acervo de pessoa de mentira (sócios e contato) neste servidor e a Ana no Pro."""
    pasta = acervo_de_mentira._acervo(
        tmp_path / "acervo_pessoa", acervo_de_mentira.LINHAS
    )
    acervo_de_mentira._acervo_de_contato(pasta, acervo_de_mentira.CONTATOS)
    monkeypatch.setenv(pessoa.VARIAVEL, str(pasta))
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "pro")
    return pasta


def _nao_le_nada(monkeypatch) -> None:
    for nome in ("contato_da_empresa", "socios_da_empresa", "pasta_do_acervo"):
        monkeypatch.setattr(pessoa, nome, dos_socios._nao_le)
    monkeypatch.setattr(pessoa.cnpj_, "normalizar_cnpj", dos_socios._nao_le)


def _igual_a_rota_que_nao_existe(cliente, corpo) -> None:
    resposta = dos_socios._enviar(cliente, ROTA, corpo)
    inexistente = dos_socios._enviar(cliente, INEXISTENTE, corpo)
    assert resposta.status_code == inexistente.status_code == 404
    assert resposta.content == inexistente.content
    assert resposta.headers["content-type"] == inexistente.headers["content-type"]
    assert "Cache-Control" not in resposta.headers


# ---------------------------------------------------------------- quem pode


def test_membro_da_organizacao_com_a_permissao_ve_o_contato(cliente, casa):
    resposta = cliente.post(ROTA, json={"cnpj": "11.222.333/0001-81"})
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["estado"] == analista_pessoas.PRONTA
    assert [e["cnpj"] for e in dados["estabelecimentos"]] == [
        EMPRESA,
        acervo_de_mentira.FILIAL,
    ]
    assert all(set(e) == CAMPOS for e in dados["estabelecimentos"])
    assert dados["estabelecimentos"][0]["telefones"] == ["1130001000"]
    assert dados["estabelecimentos"][0]["email"] == "contato@exemplo.com.br"
    assert dados["total"] == 2
    assert dados["fonte"]["fonte"] == "rfb-cnpj" and dados["fonte"]["mes_do_retrato"]
    assert dados["limites"] == list(pessoa.LIMITES_DO_CONTATO)
    assert resposta.headers["Cache-Control"] == "no-store"


def test_empresa_sem_estabelecimento_ativo_sai_sem_contato(cliente, casa):
    dados = cliente.post(ROTA, json={"cnpj": "11000000000100"}).json()
    assert dados["estado"] == analista_pessoas.SEM_CONTATO
    assert dados["estabelecimentos"] == [] and dados["total"] == 0


@pytest.mark.parametrize("corpo", [{"cnpj": "123"}, {"cnpj": "x" * 500}, {}, b"{"])
def test_pedido_invalido_de_quem_pode_422_sem_repetir_o_que_veio(cliente, casa, corpo):
    resposta = dos_socios._enviar(cliente, ROTA, corpo)
    assert resposta.status_code == 422
    assert resposta.json() == {"detail": analista.CNPJ_INVALIDO}


def test_servidor_sem_a_tabela_de_contato_503(cliente, casa, acervo, tmp_path):
    (acervo / pessoa.CONTATO).rename(tmp_path / "fora")  # só os sócios chegaram aqui
    resposta = cliente.post(ROTA, json={"cnpj": EMPRESA})
    assert resposta.status_code == 503
    assert resposta.json()["detail"] == analista.BASE_FORA_DO_AR


# ---------------------------------------------------------------- quem não pode


@pytest.mark.parametrize("corpo", dos_socios.CORPOS)
def test_conta_sem_organizacao_recebe_o_404_da_rota_inexistente(
    cliente, monkeypatch, corpo
):
    _nao_le_nada(monkeypatch)
    _igual_a_rota_que_nao_existe(cliente, corpo)


@pytest.mark.parametrize("corpo", dos_socios.CORPOS)
def test_duas_organizacoes_uma_ve_a_outra_nao(cliente, casa, da_bia, banco, dia, corpo):
    bia, cliente_da_bia = da_bia
    dos_socios._organizacao_com(banco, dia, "Outra Exemplo", bia.id, permite=False)
    assert cliente.post(ROTA, json={"cnpj": EMPRESA}).status_code == 200
    _igual_a_rota_que_nao_existe(cliente_da_bia, corpo)


def test_quem_nao_pode_nao_faz_o_servidor_tocar_o_acervo(
    cliente, da_bia, banco, dia, monkeypatch
):
    bia, cliente_da_bia = da_bia
    dos_socios._organizacao_com(banco, dia, "Outra Exemplo", bia.id, permite=False)
    _nao_le_nada(monkeypatch)
    for corpo in dos_socios.CORPOS:
        assert dos_socios._enviar(cliente_da_bia, ROTA, corpo).status_code == 404
        assert dos_socios._enviar(cliente, ROTA, corpo).status_code == 404
    assert dos_socios._vistas(banco) == []


def test_sem_login_401_plano_sem_a_ficha_403_e_so_post(cliente, casa, banco):
    assert cliente.get(ROTA).status_code == 405
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "gratuito")
    assert cliente.post(ROTA, json={"cnpj": EMPRESA}).status_code == 403
    cliente.headers.pop("Cookie")
    assert cliente.post(ROTA, json={"cnpj": EMPRESA}).status_code == 401


# ---------------------------------------------------------------- o que fica registrado


def test_auditoria_leva_o_tipo_e_as_linhas_sem_cnpj_nem_contato(cliente, casa, banco):
    cliente.post(ROTA, json={"cnpj": EMPRESA})
    cliente.post(ROTA, json={"cnpj": "11000000000100"})
    vistas = dos_socios._vistas(banco)
    assert [v.detalhes for v in vistas] == [
        {"tipo": "contato", "linhas": 2},
        {"tipo": "contato", "linhas": 0},
    ]
    assert {v.ator_id for v in vistas} == {rotas._id_da_ana_no(banco)}
    assert {v.alvo_id for v in vistas} == {casa.id}
    tudo = str([tuple(v) for v in vistas]).lower()
    assert "11222333" not in tudo and "exemplo" not in tudo and "3000" not in tudo


def test_sem_auditoria_nada_sai(cliente, casa, monkeypatch):
    def falhar(*_argumentos, **_nomeados):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(analista_pessoas.auditoria, "registrar", falhar)
    with pytest.raises(RuntimeError):
        cliente.post(ROTA, json={"cnpj": EMPRESA})


def test_o_log_nao_leva_cnpj_nem_contato(cliente, casa, caplog):
    with caplog.at_level(logging.DEBUG):
        cliente.post(ROTA, json={"cnpj": EMPRESA})
        cliente.post(ROTA, json={"cnpj": "123"})
    texto = caplog.text.lower()
    assert "11222333" not in texto and "exemplo" not in texto
    assert "1130001000" not in texto
    assert "contato da ficha: pronta" in texto


# ------------------------------------------- individual e MEI: endereço só até município e UF (linha 859)

MEI = "33444555000181"
SEM_RUA = dict.fromkeys(
    ("tipo_logradouro", "logradouro", "numero", "complemento", "bairro", "cep")
)


def _com_mei(acervo) -> None:
    """Regrava o contato como a montagem grava: a raiz de MEI sem rua, a da empresa inteira."""
    pasta = acervo / pessoa.CONTATO
    for arquivo in pasta.glob("*.parquet"):
        arquivo.unlink()
    linhas = [*acervo_de_mentira.CONTATOS, acervo_de_mentira._contato(MEI) | SEM_RUA]
    tabela = pd.DataFrame(linhas).assign(mes_do_retrato=acervo_de_mentira.MES)
    for prefixo, parte in tabela.groupby(tabela["cnpj_basico"].str[:2]):
        parte.to_parquet(pasta / f"{prefixo}.parquet", index=False)


def test_organizacao_com_a_permissao_recebe_o_mei_sem_a_rua_e_a_empresa_inteira(
    cliente, casa, acervo
):
    _com_mei(acervo)
    do_mei = cliente.post(ROTA, json={"cnpj": MEI}).json()["estabelecimentos"][0]
    assert (
        do_mei["logradouro"] is None
        and do_mei["bairro"] is None
        and do_mei["cep"] is None
    )
    assert (
        do_mei["municipio"] and do_mei["uf"] and do_mei["telefones"] and do_mei["email"]
    )
    empresa = cliente.post(ROTA, json={"cnpj": EMPRESA}).json()["estabelecimentos"][0]
    assert empresa["logradouro"] and empresa["cep"]


def test_acervo_sem_a_marca_do_corte_e_servido_como_fora_do_ar(cliente, casa, acervo):
    (acervo / pessoa.MANIFESTO).write_text(
        json.dumps({"descartes": {}}), encoding="utf-8"
    )
    resposta = cliente.post(ROTA, json={"cnpj": EMPRESA})
    assert resposta.status_code == 503 and "DOS EXEMPLOS" not in resposta.text


def test_duas_organizacoes_so_a_com_a_permissao_recebe_o_mei(
    cliente, casa, acervo, da_bia, banco, dia
):
    bia, cliente_da_bia = da_bia
    dos_socios._organizacao_com(banco, dia, "Outra Exemplo", bia.id, permite=False)
    _com_mei(acervo)
    assert cliente.post(ROTA, json={"cnpj": MEI}).status_code == 200
    _igual_a_rota_que_nao_existe(cliente_da_bia, {"cnpj": MEI})


def test_conta_sem_organizacao_nao_ve_o_mei(cliente, acervo, monkeypatch):
    _com_mei(acervo)
    _nao_le_nada(monkeypatch)
    _igual_a_rota_que_nao_existe(cliente, {"cnpj": MEI})
