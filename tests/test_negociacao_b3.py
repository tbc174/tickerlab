"""A planilha de negociação da Área do Investidor da B3 (Extratos → Negociação).

As colunas e os formatos (data em texto dd/mm/aaaa, "Compra"/"Venda", nomes dos mercados, "-" no
vencimento do mercado à vista, código fracionário com F, e o Valor dos futuros já com o
multiplicador do contrato) foram copiados de uma planilha real de 2026; os valores aqui são
inventados.
"""

from datetime import date
from io import BytesIO

import pandas as pd
import pytest

from src.carteira_b3 import ArquivoDaB3Error
from src.negociacao_b3 import MAXIMO_DE_LINHAS_DA_NEGOCIACAO, ler_negociacao

COLUNAS = [
    "Data do Negócio",
    "Tipo de Movimentação",
    "Mercado",
    "Prazo/Vencimento",
    "Instituição",
    "Código de Negociação",
    "Quantidade",
    "Preço",
    "Valor",
]
CORRETORA = "CORRETORA FICTICIA S/A"
A_VISTA = "Mercado à Vista"


def _linha(data, lado, mercado, codigo, quantidade, preco, valor, prazo="-"):
    return [data, lado, mercado, prazo, CORRETORA, codigo, quantidade, preco, valor]


def _xlsx(linhas, aba="Negociação"):
    arquivo = BytesIO()
    pd.DataFrame(linhas, columns=COLUNAS).to_excel(arquivo, sheet_name=aba, index=False)
    return arquivo.getvalue()


def _ler(linhas, nomes=None):
    return ler_negociacao(_xlsx(linhas), "negociacao.xlsx", nomes)


def test_le_compra_e_venda_pelo_nome_das_colunas():
    neg = _ler(
        [
            _linha("12/03/2026", "Venda", A_VISTA, "PETR4", 50, 40.0, 2000.0),
            _linha("10/03/2026", "Compra", A_VISTA, "PETR4", 100, 30.0, 3000.0),
        ]
    )
    compra, venda = neg.negocios  # em ordem de data (a B3 manda do mais novo)
    assert (compra.data, compra.codigo, compra.compra) == (
        date(2026, 3, 10),
        "PETR4",
        True,
    )
    assert (compra.quantidade, compra.valor, compra.classe) == (100, 3000.0, "acao")
    assert venda.compra is False and venda.valor == 2000.0
    assert (neg.primeira_data, neg.ultima_data) == (
        date(2026, 3, 10),
        date(2026, 3, 12),
    )


def test_fracionario_junta_com_o_lote_padrao():
    neg = _ler(
        [
            _linha(
                "10/03/2026", "Compra", "Mercado Fracionário", "PETR4F", 7, 30.0, 210.0
            )
        ]
    )
    assert neg.negocios[0].codigo == "PETR4"
    assert neg.negocios[0].classe == "acao"


def test_futuro_usa_o_valor_com_o_multiplicador():
    neg = _ler(
        [
            _linha(
                "10/03/2026",
                "Compra",
                "Futuro",
                "WINJ26",
                2,
                130000,
                52000.0,
                "15/04/2026",
            )
        ]
    )
    (negocio,) = neg.negocios
    assert negocio.classe == "futuro"
    assert negocio.codigo == "WINJ26"
    assert negocio.valor == 52000.0  # 2 × 130.000 pontos × R$ 0,20


def test_fii_reconhecido_pelo_nome():
    neg = _ler(
        [_linha("10/03/2026", "Compra", A_VISTA, "HGLG11", 10, 160.0, 1600.0)],
        nomes={"HGLG11": "CGHG LOGISTICA FDO INV IMOB - FII"},
    )
    assert neg.negocios[0].classe == "fii"


def test_fiagro_conta_como_fii():
    neg = _ler(
        [_linha("10/03/2026", "Compra", A_VISTA, "RZAG11", 10, 10.0, 100.0)],
        nomes={"RZAG11": "FDO INV CADEIAS PROD AGRO RIZA AGRO FIAGRO IMOB"},
    )
    assert neg.negocios[0].classe == "fii"


def test_unit_com_nome_de_empresa_conta_como_acao():
    neg = _ler(
        [_linha("10/03/2026", "Compra", A_VISTA, "KLBN11", 10, 20.0, 200.0)],
        nomes={"KLBN11": "KLABIN S/A"},
    )
    assert neg.negocios[0].classe == "acao"


def test_codigo_11_sem_nome_vai_para_outros_com_aviso():
    neg = _ler([_linha("10/03/2026", "Compra", A_VISTA, "KNCR11", 10, 100.0, 1000.0)])
    assert neg.negocios[0].classe == "outros"
    assert any("KNCR11" in aviso and "movimentação" in aviso for aviso in neg.avisos)


def test_etf_pelo_nome_vai_para_outros():
    neg = _ler(
        [_linha("10/03/2026", "Compra", A_VISTA, "BOVA11", 10, 120.0, 1200.0)],
        nomes={"BOVA11": "ISHARES BOVA FDO INDICE"},
    )
    assert neg.negocios[0].classe == "outros"


def test_opcoes_renda_fixa_e_bdr_ficam_de_fora_com_aviso():
    neg = _ler(
        [
            _linha(
                "10/03/2026",
                "Compra",
                "Opção de Compra sobre Ações",
                "BOVAE133",
                100,
                1.0,
                100.0,
                "20/05/2026",
            ),
            _linha(
                "10/03/2026", "Compra", "Renda Fixa", "CRA0000001", 1, 1000.0, 1000.0
            ),
            _linha("10/03/2026", "Compra", A_VISTA, "AAPL34", 10, 50.0, 500.0),
            _linha("10/03/2026", "Compra", A_VISTA, "PETR4", 10, 30.0, 300.0),
        ]
    )
    assert [n.codigo for n in neg.negocios] == ["PETR4"]
    assert neg.fora == 3
    texto = " ".join(neg.avisos)
    assert "opções" in texto and "BDR" in texto and "renda fixa" in texto


def test_mercado_desconhecido_fica_de_fora_com_o_nome():
    neg = _ler([_linha("10/03/2026", "Compra", "Termo", "PETR4T", 10, 30.0, 300.0)])
    assert neg.negocios == ()
    assert any("Termo" in aviso for aviso in neg.avisos)


def test_sem_valor_usa_quantidade_vezes_preco_no_a_vista():
    neg = _ler([_linha("10/03/2026", "Compra", A_VISTA, "PETR4", 10, 30.0, "-")])
    assert neg.negocios[0].valor == pytest.approx(300.0)


def test_data_que_nao_entendo_da_erro_claro():
    with pytest.raises(ArquivoDaB3Error, match="dd/mm/aaaa"):
        _ler([_linha("10-03-2026x", "Compra", A_VISTA, "PETR4", 10, 30.0, 300.0)])


def test_arquivo_sem_as_colunas_da_erro_claro():
    arquivo = BytesIO()
    pd.DataFrame({"Produto": ["PETR4"], "Quantidade": [100]}).to_excel(
        arquivo, index=False
    )
    with pytest.raises(ArquivoDaB3Error, match="NEGOCIAÇÃO"):
        ler_negociacao(arquivo.getvalue(), "outra.xlsx")


def test_recusa_planilha_com_linhas_demais():
    linhas = [_linha("10/03/2026", "Compra", A_VISTA, "PETR4", 1, 1.0, 1.0)] * (
        MAXIMO_DE_LINHAS_DA_NEGOCIACAO + 1
    )
    with pytest.raises(ArquivoDaB3Error, match="linhas"):
        _ler(linhas)
