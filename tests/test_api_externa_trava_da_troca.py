"""A trava da troca da base (linha 1099, parte b, decidida pela Diretoria em 25/11 como trava provisória).

As views do DuckDB leem os Parquets pelo caminho, e o recebedor do VPS troca a `base/` no mesmo lugar que a API lê. Um
pedido que cruza a troca pode juntar arquivos de antes e de depois numa resposta só (o P1 do Revisor no #1329). A
trava não impede a troca: no fim do pedido, só na porta do pedido, a impressão da base (caminho, data e tamanho de
cada arquivo) é tirada de novo e comparada com a da abertura da porta dona. Se mudou, a resposta não sai: a API
responde 503 `base_updating` com `Retry-After`, e o conector mostra uma frase, nunca a exceção. A rota não conta o
pedido no consumo.

O que a trava NÃO pega fica escrito num teste próprio: a troca que preserva a data e o tamanho de todo arquivo. O
conserto de raiz é a pasta versionada (parte a da 1099), que não é deste PR. Base de mentira, sem internet.
"""

import os

import duckdb
import httpx
import pytest
from fastapi import HTTPException

from base.porta import Porta
from src.api_externa import porta_compartilhada as compartilhada
from src.api_externa import rotas
from src.api_externa.conjuntos import analise, empresas
from tests import ajudantes_do_conector as conector
from tests import test_api_externa_analise as rota_da_analise
from tests import test_api_externa_e_empresa as listas_de_mentira
from tests import test_api_externa_retrato_guardado as guardado
from tests import test_api_externa_socios_pj as socios_de_mentira

NOVA = "11222222000191"  # só entra no retrato novo, no mesmo arquivo (prefixo 11) da EMPRESA das listas


def _base_de_producao(monkeypatch, pasta) -> None:
    """A porta do pedido de produção (cursor da porta dona, memória dividida, impressão da abertura) sobre
    `pasta`."""
    compartilhada.zerar()
    monkeypatch.setattr(compartilhada, "abrir_a_base", lambda: Porta(pasta))
    monkeypatch.setattr(compartilhada, "_pasta_da_base", lambda: pasta)
    monkeypatch.setattr(rotas, "abrir_porta", compartilhada.porta_do_pedido)


@pytest.fixture
def listas(tmp_path, monkeypatch):
    pasta = tmp_path / "base"
    guardado._gravar_listas(pasta)
    _base_de_producao(monkeypatch, pasta)
    yield pasta
    compartilhada.zerar()


def _retrato_novo_com_a_nova(pasta) -> None:
    """O recebedor regrava as duas listas no mesmo caminho, com o retrato de 2026-11 e a NOVA dentro dele."""
    guardado._acrescentar_no_mesmo_arquivo(
        pasta,
        empresas.LISTA_DE_EMPRESAS,
        guardado._no_mes(
            listas_de_mentira._empresas([(NOVA[:8], "2062", guardado.NOVISSIMO)])
        ),
    )
    guardado._acrescentar_no_mesmo_arquivo(
        pasta,
        empresas.LISTA_DE_ESTABELECIMENTOS,
        guardado._no_mes(
            listas_de_mentira._estabelecimentos([(NOVA, guardado.NOVISSIMO)])
        ),
    )


def _base_em_atualizacao(erro: pytest.ExceptionInfo[HTTPException]) -> None:
    assert erro.value.status_code == 503
    assert erro.value.detail == "base_updating"
    assert erro.value.headers == {"Retry-After": str(rotas.ESPERA_DA_TROCA_S)}


# ---------------------------------------------------------------- o cenário do Revisor (aceite da 1099)


def test_o_pedido_que_cruza_a_troca_responde_503_e_nao_a_resposta_misturada(
    listas, monkeypatch
):
    """O cenário do Revisor no #1329: a carga cai logo depois de achar o mês das duas listas, antes da consulta
    que o usa. Sem a trava, o pedido respondia "não é empresa" para a NOVA, que uma porta aberta depois da troca
    aceita. Com a trava, esse pedido não responde nada de dado; o seguinte responde certo."""
    achar_o_mes = empresas._retrato_das_duas_listas
    trocou: list[str] = []

    def achar_e_trocar(porta):
        mes = achar_o_mes(porta)
        if not trocou:
            _retrato_novo_com_a_nova(listas)
            trocou.append(mes)
        return mes

    monkeypatch.setattr(empresas, "_retrato_das_duas_listas", achar_e_trocar)
    no_meio: list[bool] = []
    with pytest.raises(HTTPException) as erro, rotas._porta(None) as porta:
        no_meio.append(empresas.e_empresa(porta, NOVA))
    _base_em_atualizacao(erro)
    assert trocou == [guardado.NOVO]
    assert no_meio == [
        False
    ]  # a resposta misturada existiu dentro do pedido; não saiu dele
    with rotas._porta(None) as porta:
        assert empresas.e_empresa(porta, NOVA)  # o pedido seguinte, na base nova


def test_sem_troca_o_pedido_responde_e_a_memoria_continua(listas):
    with rotas._porta(None) as porta:
        assert empresas.e_empresa(porta, listas_de_mentira.EMPRESA)
    with rotas._porta(None) as porta:
        assert empresas.CHAVE_DO_RETRATO_DAS_DUAS_LISTAS in porta.memoria_da_base
        assert empresas.e_empresa(porta, listas_de_mentira.EMPRESA)


def _arquivo_novo(pasta) -> None:
    """Um Parquet a mais na pasta de uma lista (o recebedor entrega um prefixo que não havia)."""
    pasta_da_lista = pasta / empresas.LISTA_DE_EMPRESAS
    origem = next(pasta_da_lista.glob("*.parquet"))
    (pasta_da_lista / "99.parquet").write_bytes(origem.read_bytes())


def _arquivo_apagado(pasta) -> None:
    next((pasta / empresas.LISTA_DE_EMPRESAS).glob("*.parquet")).unlink()


@pytest.mark.parametrize(
    "trocar",
    [
        pytest.param(_retrato_novo_com_a_nova, id="arquivo regravado"),
        pytest.param(_arquivo_novo, id="arquivo novo"),
        pytest.param(_arquivo_apagado, id="arquivo apagado"),
    ],
)
def test_toda_troca_de_arquivo_no_meio_do_pedido_vira_503(listas, trocar):
    with pytest.raises(HTTPException) as erro, rotas._porta(None) as porta:
        empresas.e_empresa(porta, listas_de_mentira.EMPRESA)
        trocar(listas)
    _base_em_atualizacao(erro)


@pytest.mark.parametrize(
    "erro_no_meio",
    [duckdb.IOException("arquivo cortado"), HTTPException(404, "not_available")],
)
def test_erro_no_meio_de_um_pedido_que_cruzou_a_troca_tambem_vira_base_em_atualizacao(
    listas, erro_no_meio
):
    """O arquivo lido pela metade (erro do DuckDB) e o 404 decidido sobre a base misturada são respostas
    misturadas também: com a base trocada, o que sai é o 503 da troca."""
    with pytest.raises(HTTPException) as erro, rotas._porta(None):
        _retrato_novo_com_a_nova(listas)
        raise erro_no_meio
    _base_em_atualizacao(erro)


@pytest.mark.parametrize(
    ("erro_no_meio", "esperado"),
    [
        (duckdb.IOException("arquivo cortado"), (503, "service_unavailable")),
        (HTTPException(404, "not_available"), (404, "not_available")),
    ],
)
def test_erro_no_meio_sem_troca_continua_o_de_antes(listas, erro_no_meio, esperado):
    with pytest.raises(HTTPException) as erro, rotas._porta(None):
        raise erro_no_meio
    assert (erro.value.status_code, erro.value.detail) == esperado


def test_a_porta_aberta_durante_a_troca_tambem_e_conferida(listas, monkeypatch):
    """A porta dona aberta no meio da troca guarda a impressão de ANTES da abertura: o pedido que a abriu vê a
    troca no fim e responde 503 (as views podem ter listado arquivos dos dois lados)."""
    abrir = compartilhada.abrir_a_base

    def abrir_durante_a_troca():
        porta = abrir()
        _retrato_novo_com_a_nova(listas)
        return porta

    monkeypatch.setattr(compartilhada, "abrir_a_base", abrir_durante_a_troca)
    with pytest.raises(HTTPException) as erro, rotas._porta(None) as porta:
        empresas.e_empresa(porta, NOVA)
    _base_em_atualizacao(erro)


# ---------------------------------------------------------------- o limite (o que a trava não pega)


def test_limite_a_troca_que_preserva_data_e_tamanho_nao_e_vista(listas):
    """Escrito para ninguém ler a trava como conserto de raiz: um arquivo regravado com o mesmo tamanho e a
    mesma data de antes tem a mesma impressão, e o pedido responde. Só a pasta versionada (1099, parte a) fecha
    isto. Aqui o conteúdo muda de propósito (um byte do meio) e a data volta à de antes."""
    arquivo = next((listas / empresas.LISTA_DE_EMPRESAS).glob("*.parquet"))
    antes = arquivo.stat()
    with rotas._porta(None) as porta:
        empresas.e_empresa(porta, listas_de_mentira.EMPRESA)
        conteudo = bytearray(arquivo.read_bytes())
        conteudo[len(conteudo) // 2] ^= 0xFF
        arquivo.write_bytes(bytes(conteudo))
        os.utime(arquivo, ns=(antes.st_atime_ns, antes.st_mtime_ns))
    assert arquivo.stat().st_size == antes.st_size


# ---------------------------------------------------------------- pela rota e pelo conector


@pytest.fixture
def analise_de_producao(tmp_path, monkeypatch):
    pasta = socios_de_mentira.base_com_socios(tmp_path)
    _base_de_producao(monkeypatch, pasta)
    monkeypatch.setattr(rotas, "regras_da_api", rota_da_analise._regras)
    yield pasta
    compartilhada.zerar()


def _tocar_a_base(pasta) -> None:
    """A carga regrava todo Parquet da base no mesmo caminho (a data muda)."""
    for arquivo in pasta.rglob("*.parquet"):
        os.utime(arquivo, ns=(1, 1))


def test_na_rota_a_analise_que_cruza_a_troca_da_503_com_retry_after_e_nao_conta(
    analise_de_producao, monkeypatch, banco
):
    montar = analise.montar_analise

    def montar_e_trocar(*args, **kwargs):
        servida = montar(*args, **kwargs)
        _tocar_a_base(analise_de_producao)
        return servida

    cliente = rota_da_analise.aj.cliente_da_api(monkeypatch, rota_da_analise.AGORA)
    ator = rota_da_analise.aj.admin(banco)
    org, chave = rota_da_analise._organizacao(
        banco,
        ator,
        "Alfa",
        rota_da_analise.ficha.CONJUNTO,
        rota_da_analise.compradores.CONJUNTO,
    )
    assert rota_da_analise._get(cliente, chave).status_code == 200
    contado = rota_da_analise._por_conjunto(banco, org)
    monkeypatch.setattr(analise, "montar_analise", montar_e_trocar)
    resposta = rota_da_analise._get(cliente, chave)
    assert resposta.status_code == 503
    assert resposta.json() == {"detail": "base_updating"}
    assert resposta.headers["Retry-After"] == str(rotas.ESPERA_DA_TROCA_S)
    assert rota_da_analise._por_conjunto(banco, org) == contado  # o 503 não conta
    monkeypatch.setattr(analise, "montar_analise", montar)
    assert (
        rota_da_analise._get(cliente, chave).status_code == 200
    )  # o seguinte, na base nova


def test_no_conector_o_503_da_troca_chega_como_frase_e_nao_como_excecao():
    empresa = "11222333000181"
    resposta = httpx.Response(
        503,
        json={"detail": "base_updating"},
        headers={"Retry-After": str(rotas.ESPERA_DA_TROCA_S)},
    )
    with conector.conector(
        conector.api_de_mentira(
            {f"/companies/{empresa}/analysis": resposta}, conjuntos=("profiles",)
        )
    ) as cliente:
        erro, texto = conector.chamar(
            cliente, conector.CHAVE_DE_MENTIRA, "analise_completa", cnpj=empresa
        )
    assert erro
    assert "tente de novo" in texto
    assert "Traceback" not in texto and "base_updating" not in texto
