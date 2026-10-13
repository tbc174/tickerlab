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
