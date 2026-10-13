"""A planilha de posição da Área do Investidor da B3: leitura robusta e o relatório da carteira.

`tests/arquivos/posicao_b3_exemplo.xlsx` imita o formato da B3 com valores inventados: abas Acoes,
Fundo de Investimento e Tesouro Direto, a PETR4 em duas corretoras e uma linha de Total.
"""

import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
import tomllib
from pypdf import PdfReader

from src import relatorios
from src.carteira_b3 import (
    MAXIMO_DE_LINHAS,
    TAMANHO_MAXIMO,
    TAMANHO_MAXIMO_DESCOMPRIMIDO,
    ArquivoDaB3Error,
    ler_abas,
    ler_carteira,
    numero_efetivo_de_ativos,
    retorno_com_os_pesos_de_hoje,
)

EXEMPLO = Path(__file__).parent / "arquivos" / "posicao_b3_exemplo.xlsx"


def _carteira():
    return ler_carteira(EXEMPLO.read_bytes(), EXEMPLO.name)


def test_soma_o_mesmo_ativo_de_corretoras_diferentes():
    posicoes = _carteira().posicoes.set_index("codigo")
    assert posicoes.loc["PETR4", "quantidade"] == 150
    assert posicoes.loc["PETR4", "valor"] == 8400
    assert posicoes.loc["PETR4", "ticker"] == "PETR4.SA"  # pronto para o Yahoo


def test_a_linha_de_total_nao_conta_o_dinheiro_duas_vezes():
    carteira = _carteira()
    assert carteira.valor_total == 8400 + 4800 + 4200 + 1800 + 10000
    assert not carteira.avisos


def test_tesouro_entra_na_composicao_mas_sem_cotacao():
    carteira = _carteira()
    assert list(carteira.sem_cotacao["produto"]) == ["Tesouro Selic 2029"]
    assert "Tesouro Selic 2029" not in set(carteira.posicoes["codigo"])


def test_valor_em_texto_brasileiro_e_lido():
    wege = _carteira().posicoes.set_index("codigo").loc["WEGE3"]
    assert wege["valor"] == 1800  # veio como "1.800,00" na planilha


def test_colunas_sao_achadas_sem_acento_e_em_outra_ordem():
    tabela = pd.DataFrame(
        {
            "VALOR ATUALIZADO": [1000.0],
            "quantidade": [10],
            "Codigo de Negociacao": ["bbas3"],
        }
    )
    arquivo = BytesIO()
    tabela.to_excel(arquivo, sheet_name="Ações", index=False)
    carteira = ler_carteira(arquivo.getvalue(), "posicao.xlsx")
    assert list(carteira.posicoes["codigo"]) == ["BBAS3"]


def test_codigo_sai_do_nome_do_produto_quando_falta_a_coluna():
    tabela = pd.DataFrame({"Produto": ["TAEE11 - TAESA"], "Valor Atualizado": [500.0]})
    arquivo = BytesIO()
    tabela.to_excel(arquivo, sheet_name="Acoes", index=False)
    assert list(ler_carteira(arquivo.getvalue(), "p.xlsx").posicoes["codigo"]) == [
        "TAEE11"
    ]


def test_arquivo_errado_tem_mensagem_que_ajuda():
    with pytest.raises(ArquivoDaB3Error, match="Área do Investidor"):
        ler_carteira(b"isto nao e uma planilha", "posicao.xlsx")
    vazia = BytesIO()
    pd.DataFrame({"qualquer": [1]}).to_excel(vazia, index=False)
    with pytest.raises(ArquivoDaB3Error, match="POSIÇÃO"):
        ler_carteira(vazia.getvalue(), "outra.xlsx")


def test_arquivo_grande_demais_e_recusado():
    with pytest.raises(ArquivoDaB3Error, match="5 MB"):
        ler_carteira(b"0" * (5 * 1024 * 1024 + 1), "grande.xlsx")


def test_planilha_que_incha_ao_abrir_e_recusada_antes_de_ser_aberta(monkeypatch):
    # regressão do achado S-2 (Master v3): um .xlsx pequeno podia virar gigabytes na memória
    arquivo = BytesIO()
    with zipfile.ZipFile(arquivo, "w", zipfile.ZIP_DEFLATED) as zip_:
        zip_.writestr(
            "xl/worksheets/sheet1.xml", b" " * (TAMANHO_MAXIMO_DESCOMPRIMIDO + 1)
        )
    conteudo = arquivo.getvalue()
    assert len(conteudo) < 100_000  # comprimido, é pequeno

    def nao_pode_abrir(*_a, **_k):
        raise AssertionError("a planilha foi aberta antes de ser recusada")

    monkeypatch.setattr("src.carteira_b3.pd.read_excel", nao_pode_abrir)
    with pytest.raises(ArquivoDaB3Error, match="grande demais ao abrir"):
        ler_carteira(conteudo, "bomba.xlsx")


def _posicao_com_linhas(quantas):
    return pd.DataFrame(
        {
            "Código de Negociação": ["PETR4"] * quantas,
            "Valor Atualizado": [1.0] * quantas,
        }
    )


def test_planilha_com_linhas_demais_e_recusada():
    arquivo = BytesIO()
    _posicao_com_linhas(MAXIMO_DE_LINHAS + 1).to_excel(
        arquivo, sheet_name="Acoes", index=False
    )
    with pytest.raises(ArquivoDaB3Error, match="mais de 5.000 linhas"):
        ler_carteira(arquivo.getvalue(), "posicao.xlsx")


def test_planilha_no_limite_de_linhas_ainda_e_lida():
    arquivo = BytesIO()
    _posicao_com_linhas(MAXIMO_DE_LINHAS).to_excel(
        arquivo, sheet_name="Acoes", index=False
    )
    carteira = ler_carteira(arquivo.getvalue(), "posicao.xlsx")
    assert (
        carteira.posicoes.set_index("codigo").loc["PETR4", "valor"] == MAXIMO_DE_LINHAS
    )


def test_ler_abas_fala_da_planilha_esperada_e_usa_o_limite_pedido():
    with pytest.raises(ArquivoDaB3Error, match="planilha de movimentação"):
        ler_abas(b"isto nao e um xlsx", "x.xlsx", planilha="movimentação")
    arquivo = BytesIO()
    _posicao_com_linhas(11).to_excel(arquivo, sheet_name="Acoes", index=False)
    with pytest.raises(ArquivoDaB3Error, match="mais de 10 linhas"):
        ler_abas(arquivo.getvalue(), "x.xlsx", maximo_de_linhas=10)
    assert (
        len(ler_abas(arquivo.getvalue(), "x.xlsx", maximo_de_linhas=11)["Acoes"]) == 11
    )


def test_csv_com_linhas_demais_e_recusado():
    texto = _posicao_com_linhas(MAXIMO_DE_LINHAS + 1).to_csv(sep=";", index=False)
    with pytest.raises(ArquivoDaB3Error, match="mais de 5.000 linhas"):
        ler_carteira(texto.encode("utf-8"), "posicao.csv")


def test_o_app_limita_o_envio_de_arquivos_a_5_mb():
    configuracao = tomllib.loads(
        (Path(__file__).parent.parent / ".streamlit" / "config.toml").read_text("utf-8")
    )
    assert configuracao["server"]["maxUploadSize"] == TAMANHO_MAXIMO // (1024 * 1024)


def test_numero_efetivo_de_ativos():
    assert numero_efetivo_de_ativos(pd.Series([0.25] * 4)) == pytest.approx(4)
    assert numero_efetivo_de_ativos(pd.Series([0.9, 0.1])) < 1.3


def test_retorno_com_os_pesos_de_hoje_e_a_media_ponderada():
    datas = pd.bdate_range("2024-01-01", periods=3)
    fechamentos = pd.DataFrame(
        {"A.SA": [10, 11, 11], "B.SA": [10, 10, 12]}, index=datas
    )
    retorno = retorno_com_os_pesos_de_hoje(
        fechamentos, pd.Series({"A.SA": 0.75, "B.SA": 0.25})
    )
    assert retorno.iloc[0] == pytest.approx(0.75 * 0.10)
    assert retorno.iloc[1] == pytest.approx(0.25 * 0.20)


def test_relatorio_da_minha_carteira_avisa_que_nao_e_o_resultado_real():
    carteira = _carteira()
    ler = lambda t: pd.read_csv(
        f"dados_de_exemplo/{t.replace('^', '_')}.csv", index_col=0, parse_dates=True
    )["Close"]
    fechamentos = pd.DataFrame({t: ler(t) for t in carteira.posicoes["ticker"]})
    pdf = relatorios.relatorio_da_minha_carteira(carteira, fechamentos, ler("^BVSP"))
    texto = " ".join(
        " ".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages).split()
    )
    assert "Não é o seu resultado real" in texto
    assert (
        "PETR4" in texto and "43,8%" in texto
    )  # 8.400 de 19.200 em ativos com cotação
    assert "Número efetivo de ativos" in texto
