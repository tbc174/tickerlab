"""Um fundo na tela (linha 664, d): o raio-x da API externa, com o portão do app.

Base de mentira (a mesma do teste da API); os CNPJs são de ninguém. Riscos: olhar o futuro (a carteira
"como era" em `hoje`), mostrar fonte fora dos usos e dizer "não existe" quando a base não está aqui.
"""

import hashlib
from datetime import UTC, date, datetime

import pytest
from streamlit.testing.v1 import AppTest

from base import porta as porta_da_base
from base.parquet import gravar_tabela
from base.porta import Porta
from src import fundo_no_app as modulo
from src import portao_externo as portao
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.fundo_no_app import FundoIndisponivelError, fundo_na_tela
from tests.ajudantes_da_conta import ir_para
from tests.test_api_externa_fundos import (
    FUNDO,
    ORIGINAL,
    SEM_CADASTRO,
    URL_DO_CADASTRO,
    _cadastro,
    _carteira,
)

BAIXADO_EM = datetime(2026, 11, 5, 3, tzinfo=UTC)
HOJE = date(2026, 11, 10)


@pytest.fixture
def base(tmp_path, banco, monkeypatch):
    monkeypatch.setenv(vc.VARIAVEL, "7ddaf09c1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b")
    with banco.begin() as conexao:
        registrar(
            conexao, "cvm-cadastros", URL_DO_CADASTRO, ORIGINAL, "ok", agora=BAIXADO_EM
        )
    pasta = tmp_path / "base"
    origem = {"url": URL_DO_CADASTRO, "sha256": hashlib.sha256(ORIGINAL).hexdigest()}
    gravar_tabela(_cadastro(), pasta / "fidc/cadastro/cad_fi", [origem], ["CNPJ_FUNDO"])
    for ano in (2024, 2026):
        arquivo = pasta / "cda" / f"{ano}.parquet"
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        _carteira()[lambda d, a=ano: d.competencia.dt.year == a].to_parquet(
            arquivo, index=False
        )
    monkeypatch.setattr(
        porta_da_base, "abrir", lambda banco=None, **_: Porta(pasta, banco)
    )
    monkeypatch.setattr(modulo, "obter_engine", lambda: banco)
    return pasta


def test_fundo_traz_cadastro_e_carteira_mais_nova(base):
    fundo = fundo_na_tela(FUNDO, HOJE)
    assert fundo is not None
    assert fundo.cadastro["nome"] == "FUNDO UM"
    assert fundo.cadastro["taxa_administracao_pct_ao_ano"] == 2.0
    assert fundo.cadastro_publico_em == date(2026, 11, 5)
    assert [p["codigo"] for p in fundo.carteira] == ["ITUB4", "WEGE3"]
    assert fundo.custo_da_taxa == []  # sem retorno suposto não há conta


def test_custo_da_taxa_so_com_o_retorno_que_a_pessoa_supoe(base):
    fundo = fundo_na_tela(FUNDO, HOJE, retorno_suposto=0.10)
    assert fundo is not None
    assert [c["anos"] for c in fundo.custo_da_taxa] == [5, 20]
    primeiro = fundo.custo_da_taxa[0]
    assert primeiro["com_taxa"] < primeiro["sem_taxa"]
    assert fundo.retorno_suposto == 0.10


def test_carteira_como_era_no_dia_nao_olha_o_futuro(base):
    # a carteira de fev/2026 só ficou pública em 29/05/2026; antes disso vale a de 2024
    antes = fundo_na_tela(FUNDO, date(2026, 5, 28))
    assert antes is not None
    assert [p["codigo"] for p in antes.carteira] == ["PETR4"]
    # cadastro baixado em 05/11: antes disso ele não era público
    assert antes.cadastro == {}


def test_fundo_que_nao_esta_na_base_e_none(base):
    assert fundo_na_tela(SEM_CADASTRO, HOJE) is None


def test_cnpj_invalido_e_erro_de_quem_digitou(base):
    with pytest.raises(ValueError, match="CNPJ inválido"):
        fundo_na_tela("123", HOJE)


def test_base_fora_deste_servidor_nao_diz_que_o_fundo_nao_existe(monkeypatch):
    def sem_acervo(**_):
        raise ValueError("acervo desligado (TICKERLAB_ACERVO)")

    monkeypatch.setattr(porta_da_base, "abrir", sem_acervo)
    with pytest.raises(FundoIndisponivelError):
        fundo_na_tela(FUNDO, HOJE)


def test_fonte_sem_licenca_para_mostrar_nao_sai(base, monkeypatch):
    monkeypatch.setattr(
        portao, "pode_usar", lambda uso, fonte: fonte != "cvm-cadastros"
    )
    fundo = fundo_na_tela(FUNDO, HOJE)
    assert fundo is not None
    assert fundo.cadastro == {}
    assert fundo.carteira  # a CDA continua liberada


# ---------------------------------------------------------------- a aba "Um fundo"


def _aba() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    return ir_para(app, "donos")


def test_aba_mostra_taxas_e_carteira_do_fundo(base):
    app = _aba().text_input(key="fundo_cnpj").input(FUNDO).run()
    assert not app.exception
    rotulos = {m.label: m.value for m in app.metric}
    assert rotulos["Classe"] == "Ações"
    assert rotulos["Taxa de administração"] == "2,00%"
    codigos = [linha for df in app.dataframe for linha in df.value.get("Código", [])]
    assert codigos == ["ITUB4", "WEGE3"]
    assert any("ODbL" in c.value for c in app.caption)


def test_aba_so_calcula_o_custo_com_o_retorno_que_a_pessoa_da(base):
    app = _aba().text_input(key="fundo_cnpj").input(FUNDO).run()
    assert not any("Quanto a taxa" in m.value for m in app.markdown)
    app.checkbox(key="fundo_com_retorno").check().run()
    assert any("retorno de 10,0% ao ano" in m.value for m in app.markdown)


def test_aba_cnpj_invalido_e_fundo_ausente(base):
    app = _aba().text_input(key="fundo_cnpj").input("123").run()
    assert any("não é válido" in w.value for w in app.warning)
    app.text_input(key="fundo_cnpj").input(SEM_CADASTRO).run()
    assert any("Não achamos esse fundo" in i.value for i in app.info)


def test_aba_sem_a_base_nao_diz_que_o_fundo_nao_existe(monkeypatch):
    def sem_acervo(**_):
        raise ValueError("acervo desligado")

    monkeypatch.setattr(porta_da_base, "abrir", sem_acervo)
    app = _aba().text_input(key="fundo_cnpj").input(FUNDO).run()
    assert any("não está disponível" in i.value for i in app.info)
    assert not any("Não achamos" in i.value for i in app.info)
