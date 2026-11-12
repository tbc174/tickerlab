"""As rotas da tela do analista (linha 798): `POST /v1/analista/ficha` e `/v1/analista/ficha/planilha`.

A leitura tem os testes dela em `test_analista_leitura.py`; aqui fica o que é da rota: login, termos e plano
(a página `ficha_da_empresa`), o CNPJ só no corpo (nunca no endereço, no log nem no nome do arquivo), a base
fora do ar (503), os três estados e a planilha. A porta e as regras do portão são as da API externa
(`src/api_externa/rotas.py`): os testes trocam as mesmas funções que os testes de lá.
"""

import dataclasses
import io
import logging
import shutil

import openpyxl
import pytest

from base.porta import Porta
from src import paginas
from src.analista import leitura
from src.api_externa import rotas as rotas_da_api_externa
from src.api_externa.conjuntos import empresas, ficha
from src.api_v1 import analista
from src.banco.usuarios import mudar_plano
from tests import test_analista_leitura as leitura_de_mentira
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_por_cnpj_ficha as ficha_de_mentira
from tests import test_api_v1_rotas as rotas

chave = rotas.chave  # as fixtures da conta logada, as mesmas dos outros testes da API
ROTA = "/api/v1/analista/ficha"
PLANILHA = "/api/v1/analista/ficha/planilha"
EMPRESA = empresas_de_mentira.EMPRESA
FORMATADO = empresas_de_mentira._formatado(EMPRESA)


cliente = rotas.cliente


@pytest.fixture(autouse=True)
def base(tmp_path, monkeypatch, cliente, banco):
    """A base de mentira pela porta da API externa, as tabelas da ficha prontas e a conta no Pro."""
    _mudar_plano(banco, "pro")
    pasta = ficha_de_mentira._base(tmp_path, ficha_de_mentira._rotulos())
    monkeypatch.setattr(
        rotas_da_api_externa, "abrir_porta", lambda banco_: Porta(pasta, banco_)
    )
    monkeypatch.setattr(
        rotas_da_api_externa, "regras_da_api", leitura_de_mentira._regras
    )
    monkeypatch.setattr(analista, "hoje", lambda: leitura_de_mentira.HOJE)
    return pasta


def _mudar_plano(banco, plano: str) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), plano)


# ---------------------------------------------------------------- o que sai


def test_ficha_pronta_com_fonte_data_e_limites(cliente):
    resposta = cliente.post(ROTA, json={"cnpj": FORMATADO})
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["estado"] == leitura.PRONTA
    assert dados["ficha"]["cnpj"] == EMPRESA
    razao = dados["ficha"]["cadastro_na_receita"]["razao_social"]
    assert razao["fonte"] == "rfb-cnpj" and razao["publico_em"]
    assert dados["ficha"]["entregas"]
    assert {f["fonte"] for f in dados["fontes"]} == {
        "rfb-cnpj",
        "cvm-hist-dfp",
        "cvm-hist-itr",
    }
    assert all(f["atribuicao"] and f["licenca"] for f in dados["fontes"])
    assert dados["limites"] == list(leitura.LIMITES)


def test_a_rota_devolve_o_mesmo_corpo_da_leitura(cliente, base):
    """Risco 3: a rota não muda o que a leitura (o leitor da API externa) devolve."""
    dados = cliente.post(ROTA, json={"cnpj": EMPRESA}).json()
    with Porta(base) as porta:
        esperado = leitura.ficha(
            porta,
            EMPRESA,
            hoje=leitura_de_mentira.HOJE,
            regras=leitura_de_mentira._regras(),
        )
    corpo = {k: v for k, v in esperado.corpo.items() if k != "limites"}
    assert dados["ficha"] == corpo


@pytest.mark.parametrize(
    "cnpj",
    [
        empresas_de_mentira.MEI,
        empresas_de_mentira.EMPRESARIO_INDIVIDUAL,
        empresas_de_mentira.INEXISTENTE,
    ],
)
def test_pessoa_e_cnpj_que_nao_existe_dao_a_mesma_resposta(cliente, cnpj):
    resposta = cliente.post(ROTA, json={"cnpj": cnpj})
    assert resposta.status_code == 200
    assert resposta.json() == {
        "estado": leitura.NAO_DISPONIVEL,
        "ficha": None,
        "fontes": [],
        "limites": list(leitura.LIMITES),
        "o_que_vem": leitura.blocos_como_lista(),
    }


def test_sem_prontidao_e_estado_da_tela_nao_erro(cliente, monkeypatch):
    monkeypatch.setattr(
        rotas_da_api_externa, "regras_da_api", leitura_de_mentira._sem_prontidao
    )
    resposta = cliente.post(ROTA, json={"cnpj": EMPRESA})
    assert resposta.status_code == 200
    assert resposta.json()["estado"] == leitura.NAO_LIBERADA
    assert resposta.json()["ficha"] is None


def test_entregas_sem_prontidao_saem_sem_o_bloco(cliente, monkeypatch):
    monkeypatch.setattr(
        rotas_da_api_externa,
        "regras_da_api",
        lambda: leitura_de_mentira._regras(empresas.TABELAS),
    )
    dados = cliente.post(ROTA, json={"cnpj": EMPRESA}).json()
    assert dados["estado"] == leitura.PRONTA
    assert dados["ficha"]["entregas"] is None
    # linha 897: o bloco não consultado é dito, não some em silêncio
    assert dados["ficha"]["entregas_nao_disponiveis"] == ["DFP", "ITR"]
    assert leitura.LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL in dados["limites"]
    assert not any(
        frase in dados["limites"] for frase in ficha.LIMITES_DO_DOCUMENTO["DFP"]
    )


def _sem_a_fonte(fonte: str):
    """As regras da tela sem nenhuma linha de direito da fonte no perfil (o documento barrado para a tela)."""
    regras = leitura_de_mentira._regras()
    linhas = tuple(
        linha
        for linha in regras.linhas
        if not (linha.conjunto == ficha.CONJUNTO and linha.fonte == fonte)
    )
    return dataclasses.replace(regras, linhas=linhas)


def test_itr_barrado_vem_listado_e_os_limites_dizem_que_nao_foi_consultado(
    cliente, monkeypatch
):
    """Linha 897: a tela trocava os limites por um texto fixo que falava dos dois documentos; com o ITR
    barrado, a lista só com DFP lia como "a companhia não entregou ITR"."""
    regras = _sem_a_fonte(ficha.FONTES_DAS_ENTREGAS["ITR"])
    monkeypatch.setattr(rotas_da_api_externa, "regras_da_api", lambda: regras)
    dados = cliente.post(ROTA, json={"cnpj": EMPRESA}).json()
    assert dados["estado"] == leitura.PRONTA
    assert dados["ficha"]["entregas_nao_disponiveis"] == ["ITR"]
    assert dados["ficha"]["entregas"]
    assert {e["documento"]["valor"] for e in dados["ficha"]["entregas"]} == {"DFP"}
    assert leitura.LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL in dados["limites"]
    assert dados["limites"] != list(leitura.LIMITES)
    assert not any("unavailable_" in l or "known_at" in l for l in dados["limites"])


def test_os_dois_documentos_servidos_nada_fica_de_fora(cliente):
    dados = cliente.post(ROTA, json={"cnpj": EMPRESA}).json()
    assert dados["ficha"]["entregas_nao_disponiveis"] == []
    assert dados["limites"] == list(leitura.LIMITES)
    assert leitura.LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL not in dados["limites"]


# ---------------------------------------------------------------- pedido, acesso e base


@pytest.mark.parametrize("cnpj", ["123", "abc", "", "1" * 400])
def test_cnpj_invalido_422_sem_repetir_o_texto(cliente, cnpj):
    resposta = cliente.post(ROTA, json={"cnpj": cnpj})
    assert resposta.status_code == 422
    assert "1" * 20 not in resposta.text


def test_sem_login_401(cliente):
    cliente.headers.pop("Cookie")
    assert cliente.post(ROTA, json={"cnpj": EMPRESA}).status_code == 401


def test_plano_sem_o_dossie_da_base_403_sem_ler_a_base(cliente, banco, monkeypatch):
    _mudar_plano(banco, "gratuito")

    def nao_abre(_banco):
        raise AssertionError("a base não pode ser aberta para quem o plano recusa")

    monkeypatch.setattr(rotas_da_api_externa, "abrir_porta", nao_abre)
    resposta = cliente.post(ROTA, json={"cnpj": EMPRESA})
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == paginas.motivo_da_pagina(
        "gratuito", analista.PAGINA
    )
    assert cliente.post(PLANILHA, json={"cnpj": EMPRESA}).status_code == 403


def test_base_fora_do_ar_503_sem_dizer_onde(cliente, monkeypatch):
    def falha(_banco):
        raise OSError("C:/caminho/da/base")

    monkeypatch.setattr(rotas_da_api_externa, "abrir_porta", falha)
    resposta = cliente.post(ROTA, json={"cnpj": EMPRESA})
    assert resposta.status_code == 503
    assert "caminho" not in resposta.text


@pytest.mark.parametrize("rota", [ROTA, PLANILHA])
def test_tabela_que_falta_na_base_e_503_nao_500(cliente, base, rota):
    # o portão diz "pronta", mas a base deste servidor não tem o arquivo da tabela (achado na prévia,
    # com o acervo do PC, que não tem a situação cadastral): a tela mostra "base fora do ar", não um
    # erro sem mensagem, e a resposta não diz o caminho nem o nome da tabela
    shutil.rmtree(base / "cnpj_situacao_cadastral")
    resposta = cliente.post(rota, json={"cnpj": EMPRESA})
    assert resposta.status_code == 503
    assert resposta.json() == {"detail": analista.BASE_FORA_DO_AR}


def test_cnpj_nao_vai_para_o_log(cliente, caplog):
    with caplog.at_level(logging.DEBUG):
        cliente.post(ROTA, json={"cnpj": EMPRESA})
        cliente.post(PLANILHA, json={"cnpj": EMPRESA})
    assert EMPRESA not in caplog.text and EMPRESA[:8] not in caplog.text


# ---------------------------------------------------------------- planilha


def test_planilha_da_ficha_sem_o_cnpj_no_nome_do_arquivo(cliente):
    resposta = cliente.post(PLANILHA, json={"cnpj": EMPRESA})
    assert resposta.status_code == 200, resposta.text
    disposicao = resposta.headers["content-disposition"]
    assert disposicao == f'attachment; filename="{analista.NOME_DA_PLANILHA}"'
    assert EMPRESA not in disposicao and EMPRESA[:8] not in disposicao
    assert resposta.headers["cache-control"] == "no-store"
    pasta = openpyxl.load_workbook(io.BytesIO(resposta.content))
    assert pasta.sheetnames == ["campos", "entregas", "limites", "fontes"]


def test_planilha_de_ficha_que_nao_sai_404_igual_para_todos(cliente, monkeypatch):
    mei = cliente.post(PLANILHA, json={"cnpj": empresas_de_mentira.MEI})
    inexistente = cliente.post(PLANILHA, json={"cnpj": empresas_de_mentira.INEXISTENTE})
    assert mei.status_code == inexistente.status_code == 404
    assert mei.json() == inexistente.json()
    monkeypatch.setattr(
        rotas_da_api_externa, "regras_da_api", leitura_de_mentira._sem_prontidao
    )
    assert cliente.post(PLANILHA, json={"cnpj": EMPRESA}).json() == mei.json()


def test_toda_resposta_diz_o_que_a_ficha_traz(cliente, monkeypatch):
    """Sem prontidão a tela mostra o que vem (os blocos e a fonte de cada um); o corpo é sempre o mesmo."""
    monkeypatch.setattr(
        rotas_da_api_externa, "regras_da_api", leitura_de_mentira._sem_prontidao
    )
    sem_prontidao = cliente.post(ROTA, json={"cnpj": EMPRESA}).json()
    assert sem_prontidao["o_que_vem"] == leitura.blocos_como_lista()
