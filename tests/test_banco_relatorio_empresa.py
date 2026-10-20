"""Leitura do relatório completo de empresa no banco (série 2 da base de ML, PR 7): pelo ticker, tudo
o que o relatório usa (demonstrações, achados, acontecimentos, FRE, padrões do corte mais recente e
pares do mesmo grupo pela receita do último ano). SQLite migrado, WEG e Petrobras das amostras."""

import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa

from src import demonstracoes as dm
from src import relatorios
from src.banco import relatorio_empresa as repo
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.demonstracoes import gravar_demonstracoes, gravar_setor
from src.banco.eventos import gravar_tickers
from src.banco.modelo import eventos, fre_proventos
from src.banco.padroes import gravar_padroes
from src.planos import LimiteDoPlanoError, conferir_relatorio

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
WEG, PETROBRAS, BB = "84.429.695/0001-11", "33.000.167/0001-01", "00.000.000/0001-91"
MAQUINAS = "Máquinas, Equipamentos, Veículos e Peças"
AGORA = datetime(2026, 10, 13, tzinfo=UTC)


@pytest.fixture
def conexao(tmp_path):
    url = f"sqlite:///{(tmp_path / 'r.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)
    contas, documentos = dm.ler_demonstracoes(
        (PASTA / "dfp_cia_aberta_2025.zip").read_bytes(), "DFP"
    )
    with motor.begin() as c:
        gravar_demonstracoes(c, contas, documentos, AGORA)
        gravar_setor(c, WEG, MAQUINAS)
        gravar_setor(c, PETROBRAS, MAQUINAS)  # de propósito: par da WEG neste teste
        gravar_setor(c, BB, "Bancos")
        gravar_tickers(
            c,
            pd.DataFrame(
                {
                    "ticker": ["WEGE3.SA", "PETR4.SA"],
                    "codigo": ["WEGE3", "PETR4"],
                    "cnpj": [WEG, PETROBRAS],
                    "empresa": ["WEG S.A.", "PETROBRAS"],
                    "valor_mobiliario": ["Ações Ordinárias", "Ações Preferenciais"],
                }
            ),
            AGORA,
        )
    with motor.connect() as c:
        yield c
    motor.dispose()


def _padroes(c, corte):
    tabela = pd.DataFrame(
        [{"grupo": "bens_de_capital", "indicador": "roe", "empresas": 9,
          "percentis": {"50": 0.15}}]
    )  # fmt: skip
    gravar_padroes(c, tabela, corte, AGORA)


def test_carrega_tudo_da_empresa_pelo_ticker(conexao):
    _padroes(conexao, date(2025, 12, 31))
    _padroes(conexao, date(2027, 1, 31))  # depois de `hoje`: não entra
    conexao.execute(
        sa.insert(fre_proventos).values(
            cnpj=WEG, exercicio=date(2021, 12, 31), referencia=date(2022, 1, 1),
            versao=1, dividendo_total=1e9, coletado_em=AGORA,
        )
    )  # fmt: skip
    conexao.execute(
        sa.insert(eventos).values(
            id=uuid.uuid4(), fonte="cvm_ipe", protocolo="1", cnpj=WEG, empresa="WEG",
            categoria="Fato Relevante", assunto="Aquisição", rotulo="Fato relevante",
            tema="eventos", materialidade=3, publicado_em=date(2026, 9, 1),
            link="https://www.rad.cvm.gov.br/x", ingerido_em=AGORA,
        )
    )  # fmt: skip
    entradas = repo.entradas_do_relatorio(
        conexao, "WEGE3.SA", preco=50.0, hoje=date(2026, 10, 13)
    )
    assert entradas is not None
    assert (entradas.cnpj, entradas.empresa, entradas.preco) == (WEG, "WEG S.A.", 50.0)
    assert not entradas.dados.contas.empty and entradas.dados.setor == MAQUINAS
    assert entradas.padroes is not None and entradas.padroes[0] == date(2025, 12, 31)
    assert len(entradas.proventos) == 1
    assert entradas.eventos is not None
    assert list(entradas.eventos["assunto"]) == ["Aquisição"]
    pares = entradas.pares
    assert pares is not None
    assert set(pares["cnpj"]) == {WEG, PETROBRAS}  # o banco é de outro grupo
    assert (pares["receita"] > 0).all() and pares["empresa"].str.len().min() > 0
    tickers = entradas.tickers
    assert tickers is not None  # só os da WEG, para a ficha técnica
    assert list(tickers["codigo"]) == ["WEGE3"]
    assert list(tickers["valor_mobiliario"]) == ["Ações Ordinárias"]
    assert pd.Timestamp(tickers["atualizado_em"].iloc[0]).date() == AGORA.date()


def test_trava_desligada_tira_o_preco_do_relatorio(conexao, monkeypatch):
    """D3 mudada em 20/10/2026: TICKERLAB_PRECO_NO_RELATORIO=0 tira o preço do Yahoo da tela, do
    PDF e da API de uma vez (todos leem por aqui), sem deploy."""
    fechamentos = pd.Series([49.0, 50.0])
    monkeypatch.setenv("TICKERLAB_PRECO_NO_RELATORIO", "0")
    desligada = repo.entradas_do_relatorio(
        conexao, "WEGE3.SA", preco=50.0, fechamentos=fechamentos
    )
    assert desligada is not None
    assert desligada.preco is None and desligada.fechamentos is None
    monkeypatch.setenv("TICKERLAB_PRECO_NO_RELATORIO", "1")
    ligada = repo.entradas_do_relatorio(
        conexao, "WEGE3.SA", preco=50.0, fechamentos=fechamentos
    )
    assert ligada is not None and ligada.preco == 50.0
    assert ligada.fechamentos is fechamentos


def test_relatorio_le_a_ficha_sem_as_secoes_do_molde_b(conexao, monkeypatch):
    """Uma ficha só com a seção da rede (molde B) não vira dossiê no relatório da empresa."""
    from src import dossie
    from tests.test_dossie_no_app import SECAO_DA_REDE, _bruta

    so_a_rede = dossie.Ficha.model_validate(_bruta() | {"secoes": [SECAO_DA_REDE]})
    monkeypatch.setattr(repo, "ficha_do", lambda _cnpj: so_a_rede)
    entradas = repo.entradas_do_relatorio(conexao, "WEGE3.SA", hoje=date(2026, 10, 13))
    assert entradas is not None
    assert entradas.dossie is None


def test_pares_leem_a_geracao_de_caixa_pela_ficha_de_cada_um(conexao):
    from src import dossie

    entradas = repo.entradas_do_relatorio(conexao, "WEGE3.SA", hoje=date(2026, 10, 13))
    assert entradas is not None
    assert entradas.caixa_do_par is dossie.caixa_do_par


def test_sem_padrao_gravado_fica_sem_padroes(conexao):
    entradas = repo.entradas_do_relatorio(conexao, "WEGE3.SA", hoje=date(2026, 10, 13))
    assert entradas is not None and entradas.padroes is None


def test_ticker_sem_empresa_na_cvm_devolve_none(conexao):
    assert repo.entradas_do_relatorio(conexao, "AAPL") is None


def test_migracao_0030_aceita_o_relatorio_da_empresa_e_volta(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.sqlite').as_posix()}"
    migrar_para("head", url=url)

    def regras() -> str:
        motor = criar_engine(url)
        try:
            return " ".join(
                c["sqltext"]
                for c in sa.inspect(motor).get_check_constraints("relatorios")
            )
        finally:
            motor.dispose()

    assert "empresa" in regras()
    desfazer_ate("0029", url=url)
    assert "empresa" not in regras() and "newsletter" in regras()
    migrar_para("head", url=url)


def test_gratuito_nao_gera_o_pdf_da_empresa_e_o_plus_gera():
    with pytest.raises(LimiteDoPlanoError):
        conferir_relatorio("gratuito", relatorios.EMPRESA, 0)
    conferir_relatorio("plus", relatorios.EMPRESA, 0)
