"""A rota `GET /companies/{cnpj}/public-procurement` (linha 980, onda 2, PR 6): só as compras públicas.

Abre só o bloco `compras_publicas` da análise (SICAF e BPS, no conjunto `public_procurement`, desligado por padrão;
ADR 0122, Emenda 2), pela mecânica de `blocos_avulsos.py`. Riscos que estes testes pegam: o bloco sair sem o conjunto
no contrato (ou com outro conjunto por contrato), vazar pelo nome ou pelo tamanho, sair para outra organização, o
BPS sair sem prontidão, a linha de pessoa ou o número do processo de compra saírem, MEI ou empresário individual,
CPF no lugar do CNPJ, a varredura de pessoa falhar calada, olhar o futuro e o consumo contar errado. Base de
mentira, sem internet; os CNPJs são de ninguém.
"""

import pytest
from sqlalchemy import select

from base.porta import Porta
from src.api_externa import rotas, tabelas_por_cnpj
from src.api_externa.conjuntos import ficha, por_tabela
from src.api_externa.pessoas import RespostaComPessoaProibida
from src.banco.modelo import consumo_da_api
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_compras_publicas as compras
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_socios_pj as socios_de_mentira
from tests.ajudantes_de_cpf import cpf_que_confere
from tests.test_api_externa_tabelas_por_cnpj import AGORA, DIA, EMPRESA, _organizacao

CONJUNTO = compras.CONJUNTO


def _pasta(tmp_path, monkeypatch, nome="base", com_dado=True, ate=None):
    pasta = socios_de_mentira.base_com_socios(tmp_path / nome)
    if com_dado:
        compras._gravar_tudo(pasta, ate=ate)
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(pasta, banco_))
    return pasta


def _pedir(
    monkeypatch, valor_da_chave, regras=compras._com_as_duas, cnpj=EMPRESA, dia=DIA
):
    monkeypatch.setattr(rotas, "regras_da_api", regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    return cliente.get(
        f"/data/v1/companies/{cnpj}/public-procurement",
        params={"known_at": dia.isoformat()},
        headers=aj.bearer(valor_da_chave),
    )


def _org(banco, nome, *conjuntos, piloto=False):
    return _organizacao(banco, aj.admin(banco), nome, *conjuntos, piloto=piloto)


def _sem_nada_de_compras(texto: str) -> None:
    for nome in compras.NOMES_DE_FORA:
        assert nome not in texto, nome


# ---------------------------------------------------------------- o que sai


def test_com_o_conjunto_o_bloco_sai_com_fonte_e_data_e_sem_o_resto_da_analise(
    tmp_path, banco, monkeypatch
):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, CONJUNTO)
    resposta = _pedir(monkeypatch, chave.valor)
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert set(corpo["blocks"]) == {"public_procurement"}
    bloco = corpo["blocks"]["public_procurement"]
    habilitado = bloco["sicaf_supplier_registration"]["items"][0]["qualified_to_bid"]
    assert (
        habilitado["value"] is True and habilitado["source"] == compras.FONTE_DO_SICAF
    )
    assert habilitado["published_at"] == "2025-06-01"
    preco = bloco["bps_health_purchases"]["items"][0]["unit_price_brl"]
    assert preco["value"] == 0.12 and preco["source"] == compras.FONTE_DO_BPS
    assert set(compras.FONTES) <= {f["source"] for f in corpo["sources"]}
    assert corpo["known_at"] == DIA.isoformat() and corpo["cnpj"] == EMPRESA
    assert corpo["requests_used"] == 1
    assert corpo["not_found"] == []
    assert corpo["limits"]
    for de_fora in ("registration", "timeline", "regulated_activities"):
        assert de_fora not in corpo  # o resto da análise não abre
    for nunca in (
        compras.DE_PESSOA,
        "OUTRA-EMPRESA",
        compras.PROCESSO,
        "purchase_process",
    ):
        assert nunca not in resposta.text


def test_sem_o_conjunto_responde_nao_disponivel_igual_com_ou_sem_o_dado(
    tmp_path, banco, monkeypatch
):
    chave = _org(banco, "Beta", ficha.CONJUNTO)
    respostas = []
    for nome, com_dado in (("com", True), ("sem", False)):
        _pasta(tmp_path, monkeypatch, nome, com_dado=com_dado)
        resposta = _pedir(monkeypatch, chave.valor)
        assert resposta.status_code == 404
        assert resposta.json()["detail"] == "not_available"
        respostas.append(resposta.content)
    assert respostas[0] == respostas[1]
    _sem_nada_de_compras(respostas[0].decode())


def test_o_conjunto_de_outra_organizacao_nao_abre_nada(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    alfa = _org(banco, "Alfa", ficha.CONJUNTO, CONJUNTO)
    beta = _org(banco, "Beta", ficha.CONJUNTO)
    assert _pedir(monkeypatch, alfa.valor).status_code == 200
    resposta = _pedir(monkeypatch, beta.valor)
    assert resposta.status_code == 404
    _sem_nada_de_compras(resposta.text)


@pytest.mark.parametrize(
    "outro", [tabelas_por_cnpj.INTEGRIDADE, tabelas_por_cnpj.SEM_TRAVA_DE_LICENCA]
)
def test_os_outros_conjuntos_por_contrato_nao_abrem_as_compras(
    tmp_path, banco, monkeypatch, outro
):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, outro)
    resposta = _pedir(monkeypatch, chave.valor)
    assert resposta.status_code == 404
    _sem_nada_de_compras(resposta.text)


def test_como_hoje_so_o_piloto_com_o_conjunto_ve_o_sicaf_e_o_bps_nunca_sai(
    tmp_path, banco, monkeypatch
):
    _pasta(tmp_path, monkeypatch)
    com_piloto = _org(banco, "Alfa", ficha.CONJUNTO, CONJUNTO, piloto=True)
    sem_piloto = _org(banco, "Beta", ficha.CONJUNTO, CONJUNTO)
    resposta = _pedir(monkeypatch, com_piloto.valor, compras._como_hoje)
    assert resposta.status_code == 200
    bloco = resposta.json()["blocks"]["public_procurement"]
    assert bloco["sicaf_supplier_registration"]["found"] is True
    assert "bps_health_purchases" not in resposta.text
    resposta = _pedir(monkeypatch, sem_piloto.valor, compras._como_hoje)
    assert resposta.status_code == 404
    _sem_nada_de_compras(resposta.text)


def test_bloco_aberto_que_nao_achou_vai_em_not_found(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch, com_dado=False)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, CONJUNTO)
    corpo = _pedir(monkeypatch, chave.valor).json()
    assert [n["block"] for n in corpo["not_found"]] == ["public_procurement"]


def test_chave_invalida_nao_ve_nada(tmp_path, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    resposta = _pedir(monkeypatch, "tl_chave_que_nao_existe")
    assert resposta.status_code == 401
    _sem_nada_de_compras(resposta.text)


# ---------------------------------------------------------------- pessoa física


@pytest.mark.parametrize(
    "cnpj",
    [
        pytest.param(empresas_de_mentira.MEI, id="mei"),
        pytest.param(
            empresas_de_mentira.EMPRESARIO_INDIVIDUAL, id="empresario_individual"
        ),
    ],
)
def test_mei_e_empresario_individual_saem_nao_disponivel(
    cnpj, tmp_path, banco, monkeypatch
):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, CONJUNTO)
    resposta = _pedir(monkeypatch, chave.valor, cnpj=cnpj)
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "not_available"


def test_cpf_no_lugar_do_cnpj_e_recusado(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, CONJUNTO)
    resposta = _pedir(monkeypatch, chave.valor, cnpj=cpf_que_confere("123456789"))
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "invalid_cnpj"


def test_varredura_de_pessoa_que_falha_derruba_a_resposta_sem_o_valor(
    tmp_path, banco, monkeypatch
):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, CONJUNTO)

    def falha(*_args: object, **_kwargs: object) -> None:
        raise RespostaComPessoaProibida(["comprasgov_sicaf.texto"])

    monkeypatch.setattr(por_tabela.LeitorPorTabela, "bloco", falha)
    resposta = _pedir(monkeypatch, chave.valor)
    assert resposta.status_code == 503
    assert "sicaf" not in resposta.text


# ---------------------------------------------------------------- sem olhar o futuro e consumo


def test_cortar_o_futuro_nao_muda_o_passado(tmp_path, banco, monkeypatch):
    chave = _org(banco, "Alfa", ficha.CONJUNTO, CONJUNTO)
    _pasta(tmp_path, monkeypatch, "inteira")
    inteira = _pedir(monkeypatch, chave.valor).json()
    _pasta(tmp_path, monkeypatch, "cortada", ate=DIA)
    assert _pedir(monkeypatch, chave.valor).json() == inteira


def test_conta_um_pedido_no_conjunto_das_compras(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Alfa", ficha.CONJUNTO, CONJUNTO)
    assert _pedir(monkeypatch, chave.valor).status_code == 200
    with banco.connect() as conexao:
        linhas = conexao.execute(
            select(consumo_da_api.c.conjunto, consumo_da_api.c.pedidos)
        ).all()  # uma organização só no teste
    assert {conjunto: pedidos for conjunto, pedidos in linhas} == {CONJUNTO: 1}


def test_sem_o_conjunto_conta_um_pedido_negado_nas_compras(
    tmp_path, banco, monkeypatch
):
    _pasta(tmp_path, monkeypatch)
    chave = _org(banco, "Beta", ficha.CONJUNTO)
    assert _pedir(monkeypatch, chave.valor).status_code == 404
    with banco.connect() as conexao:
        conjuntos = conexao.execute(select(consumo_da_api.c.conjunto)).scalars().all()
    assert conjuntos == [CONJUNTO]
