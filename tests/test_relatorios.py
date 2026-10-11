"""Relatórios em PDF: abrem, batem com os números do site, trazem o aviso e respeitam o plano."""

import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pandas as pd
import pytest
from pypdf import PdfReader

from src import graficos_pdf as gp
from src import indicadores as ind
from src import relatorios
from src.banco import dados_do_usuario as repo
from src.banco import usuarios as contas
from src.carteiras import ESTRATEGIAS_DE_CARTEIRA
from src.comparacao import alinhar_fechamentos
from src.conformidade import apagar_conta, exportar_meus_dados
from src.planos import LimiteDoPlanoError, conferir_relatorio

AGORA = datetime(2026, 10, 11, 15, 0, tzinfo=UTC)


def _dados(ticker):
    return pd.read_csv(f"dados_de_exemplo/{ticker}.csv", index_col=0, parse_dates=True)


def _texto(pdf: bytes) -> str:
    assert pdf.startswith(b"%PDF")
    leitor = PdfReader(BytesIO(pdf))
    texto = " ".join(pagina.extract_text() for pagina in leitor.pages)
    return " ".join(texto.split())  # as frases quebram de linha no PDF


def _paginas(pdf: bytes) -> int:
    return len(PdfReader(BytesIO(pdf)).pages)


# --- os PDFs --------------------------------------------------------------------------------
def test_relatorio_do_ativo_bate_com_os_numeros_do_site():
    dados = _dados("PETR4.SA")
    pdf = relatorios.relatorio_do_ativo("PETR4.SA", dados, 0.0, "5 anos", exemplo=True)
    texto = _texto(pdf)
    retorno = ind.calcular_retorno_diario(dados["Close"].dropna())
    total = ind.calcular_retorno_acumulado(retorno).iloc[-1]
    assert gp.pct_br(total, 1, sinal=True) in texto  # o mesmo número da Visão geral
    assert "▲" in texto or "▼" in texto  # alta e queda sempre com seta
    assert "nada aqui é recomendação de investimento" in texto
    assert "Glossário" in texto and "Índice de Sharpe" in texto
    assert "de exemplo" in texto  # avisa que os dados são de exemplo
    assert "**" not in texto  # o Markdown do site não vaza para o PDF
    assert _paginas(pdf) >= 2


def test_relatorio_de_comparacao_tem_todos_os_ativos():
    alinhado, _ = alinhar_fechamentos(
        {t: _dados(t)["Close"] for t in ("PETR4.SA", "VALE3.SA", "_BVSP")}
    )
    texto = _texto(relatorios.relatorio_de_comparacao(alinhado))
    for ticker in ("PETR4.SA", "VALE3.SA", "_BVSP"):
        assert ticker in texto
    assert "Base 100" in texto  # o termo do glossário (o título do gráfico é imagem)


def test_relatorio_de_backtest_compara_com_comprar_e_segurar_e_avisa_da_sorte():
    texto = _texto(
        relatorios.relatorio_de_backtest(
            "PETR4.SA", _dados("PETR4.SA"), "Cruzamento de médias"
        )
    )
    assert "Comprar e segurar" in texto and "Cruzamento de médias" in texto
    assert "pode ser sorte" in texto


def test_relatorio_de_carteira_mostra_o_giro_legivel():
    fechamentos = pd.DataFrame(
        {t: _dados(t)["Close"] for t in ("PETR4.SA", "VALE3.SA", "ITUB4.SA")}
    ).dropna()
    nome = list(ESTRATEGIAS_DE_CARTEIRA)[1]
    texto = _texto(relatorios.relatorio_de_carteira(fechamentos, nome))
    assert "× o capital" in texto and "Cada ativo sozinho" in texto


def test_cada_relatorio_tem_um_nome():
    assert set(relatorios.NOMES_DOS_RELATORIOS) == set(repo.TIPOS_DE_RELATORIO)


# --- limites do plano -----------------------------------------------------------------------
def test_gratuito_gera_so_o_do_ativo_e_ate_3_por_dia():
    conferir_relatorio("gratuito", "ativo", 2)
    with pytest.raises(LimiteDoPlanoError, match="3 relatórios"):
        conferir_relatorio("gratuito", "ativo", 3)
    with pytest.raises(LimiteDoPlanoError, match="plano Pro"):
        conferir_relatorio("gratuito", "backtest", 0)


def test_pro_gera_todos_sem_limite():
    for tipo in repo.TIPOS_DE_RELATORIO:
        conferir_relatorio("pro", tipo, 10_000)


# --- banco: contagem, isolamento e LGPD -----------------------------------------------------
def _usuario(conexao, sub):
    usuario, _ = contas.entrar(conexao, sub, f"{sub}@exemplo.com")
    return usuario.id


def test_contagem_e_das_ultimas_24_horas_e_de_cada_usuario(banco):
    with banco.begin() as conexao:
        ana, bia = _usuario(conexao, "ana"), _usuario(conexao, "bia")
        repo.registrar_relatorio(
            conexao, ana, "ativo", agora=AGORA - timedelta(hours=30)
        )
        repo.registrar_relatorio(
            conexao, ana, "ativo", agora=AGORA - timedelta(hours=2)
        )
        repo.registrar_relatorio(
            conexao, bia, "ativo", agora=AGORA - timedelta(hours=1)
        )
        assert (
            repo.contar_relatorios_recentes(conexao, ana, AGORA) == 1
        )  # o de 30 h não conta
        assert repo.contar_relatorios_recentes(conexao, bia, AGORA) == 1


def test_o_limite_e_conferido_antes_de_registrar(banco):
    with banco.begin() as conexao:
        ana = _usuario(conexao, "ana")
        for _ in range(3):
            repo.registrar_relatorio(
                conexao, ana, "ativo", plano="gratuito", agora=AGORA
            )
        with pytest.raises(LimiteDoPlanoError):
            repo.registrar_relatorio(
                conexao, ana, "ativo", plano="gratuito", agora=AGORA
            )
        assert (
            repo.contar_relatorios_recentes(conexao, ana, AGORA) == 3
        )  # o recusado não entrou


def test_tipo_desconhecido_e_recusado(banco):
    with banco.begin() as conexao, pytest.raises(repo.DadosInvalidosError):
        repo.registrar_relatorio(conexao, _usuario(conexao, "ana"), "qualquer")


def test_relatorios_entram_na_exportacao_e_somem_com_a_conta(banco):
    with banco.begin() as conexao:
        ana = _usuario(conexao, "ana")
        repo.registrar_relatorio(conexao, ana, "ativo", agora=AGORA)
        exportado = exportar_meus_dados(conexao, ana)
        assert [r["tipo"] for r in exportado["relatorios_em_pdf"]] == ["ativo"]
        assert apagar_conta(conexao, ana)
        assert repo.listar_relatorios(conexao, ana) == []
        assert repo.contar_relatorios_recentes(conexao, uuid.uuid4(), AGORA) == 0
