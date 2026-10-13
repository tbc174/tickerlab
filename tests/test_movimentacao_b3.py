"""A planilha de movimentação da Área do Investidor da B3 (Extratos → Movimentação).

As colunas, os nomes dos tipos de movimentação e os formatos (data em texto dd/mm/aaaa, "-" no
lugar de número, "Credito"/"Debito" sem acento, Tesouro e renda fixa com tipos em maiúsculas)
foram copiados de uma planilha real de 2026; os valores aqui são inventados.
"""

from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from src.carteira_b3 import ArquivoDaB3Error
from src.dividendos_e_custo import Lancamento
from src.movimentacao_b3 import (
    MAXIMO_DE_LINHAS_DA_MOVIMENTACAO,
    ler_movimentacao,
)

COLUNAS = [
    "Entrada/Saída",
    "Data",
    "Movimentação",
    "Produto",
    "Instituição",
    "Quantidade",
    "Preço unitário",
    "Valor da Operação",
]
CORRETORA = "CORRETORA FICTICIA S/A"
EXEMPLO = Path(__file__).parent.parent / "conteudo" / "movimentacao_de_exemplo.xlsx"


def _linha(entrada, data, tipo, produto, quantidade, preco, valor):
    return [entrada, data, tipo, produto, CORRETORA, quantidade, preco, valor]


def _xlsx(linhas, aba="Movimentação"):
    arquivo = BytesIO()
    pd.DataFrame(linhas, columns=COLUNAS).to_excel(arquivo, sheet_name=aba, index=False)
    return arquivo.getvalue()


def _ler(linhas):
    return ler_movimentacao(_xlsx(linhas), "movimentacao.xlsx")


PETR = "PETR4 - PETROLEO BRASILEIRO S/A PETROBRAS"
HGLG = "HGLG11 - CGHG LOGISTICA FDO INV IMOB - FII"


def test_compra_e_venda_pela_liquidacao():
    mov = _ler(
        [
            _linha(
                "Debito", "10/03/2025", "Transferência - Liquidação", PETR, 50, 40, 2000
            ),
            _linha(
                "Credito",
                "05/02/2025",
                "Transferência - Liquidação",
                PETR,
                100,
                30,
                3000,
            ),
        ]
    )
    assert mov.lancamentos == (
        Lancamento(date(2025, 2, 5), "PETR4", "compra", 100, 3000),
        Lancamento(date(2025, 3, 10), "PETR4", "venda", 50, 2000),
    )


def test_cada_tipo_de_provento_vai_para_o_lugar_certo():
    mov = _ler(
        [
            _linha("Credito", "15/05/2025", "Dividendo", PETR, 100, 0.5, 50),
            # o JCP vem líquido: o preço é o bruto e o valor já tem os 15% de IR retidos
            _linha(
                "Credito",
                "16/05/2025",
                "Juros Sobre Capital Próprio",
                PETR,
                100,
                0.2,
                17,
            ),
            _linha("Credito", "17/05/2025", "Rendimento", HGLG, 10, 1.1, 11),
            # provento pago enquanto a ação estava emprestada
            _linha("Credito", "18/05/2025", "Reembolso", HGLG, 10, "-", 11),
        ]
    )
    assert [(x.tipo, x.valor) for x in mov.lancamentos] == [
        ("dividendo", 50),
        ("jcp", 17),
        ("rendimento", 11),
        ("reembolso", 11),
    ]


def test_eventos_que_mudam_a_quantidade():
    mov = _ler(
        [
            _linha("Credito", "02/06/2025", "Desdobro", PETR, 100, "-", "-"),
            _linha("Debito", "03/06/2025", "Grupamento", PETR, 90, "-", "-"),
            _linha("Credito", "04/06/2025", "Bonificação em Ativos", PETR, 1, "-", "-"),
            _linha("Debito", "05/06/2025", "Fração em Ativos", PETR, 0.5, "-", "-"),
        ]
    )
    assert [(x.tipo, x.quantidade) for x in mov.lancamentos] == [
        ("desdobro", 100),
        ("grupamento", 90),
        ("bonificacao", 1),
        ("venda", 0.5),  # a fração vai a leilão: sai como uma venda
    ]


def test_valor_que_falta_vem_de_quantidade_vezes_preco():
    mov = _ler([_linha("Credito", "05/02/2025", "Rendimento", HGLG, 10, 1.25, "-")])
    assert mov.lancamentos[0].valor == pytest.approx(12.5)


def test_numeros_em_texto_brasileiro():
    mov = _ler(
        [
            _linha(
                "Credito",
                "05/02/2025",
                "Transferência - Liquidação",
                PETR,
                "1.000",
                "30,5",
                "30.500,00",
            )
        ]
    )
    assert mov.lancamentos[0].quantidade == 1000
    assert mov.lancamentos[0].valor == pytest.approx(30500)


def test_tesouro_e_renda_fixa_ficam_de_fora_com_aviso():
    mov = _ler(
        [
            _linha(
                "Debito",
                "01/02/2025",
                "COMPRA / VENDA",
                "CDB - CDB123ABC - BANCO FICTICIO",
                1,
                1000,
                1000,
            ),
            _linha(
                "Credito",
                "01/02/2025",
                "Juros",
                "Tesouro IPCA+ com Juros Semestrais 2035",
                1.5,
                30,
                45,
            ),
            _linha("Credito", "05/02/2025", "Rendimento", HGLG, 10, 1, 10),
        ]
    )
    assert [x.codigo for x in mov.lancamentos] == ["HGLG11"]
    assert any("Tesouro e renda fixa" in a and "2 linhas" in a for a in mov.avisos)


def test_tipos_que_nao_mudam_custo_nem_sao_proventos_ficam_de_fora_sem_alarde():
    mov = _ler(
        [
            _linha("Debito", "01/02/2025", "Transferência", PETR, 10, "-", "-"),
            _linha("Credito", "01/02/2025", "Transferência", PETR, 10, "-", "-"),
            _linha("Credito", "01/02/2025", "Empréstimo", PETR, 10, "-", 3),
            _linha(
                "Credito",
                "01/02/2025",
                "Direito de Subscrição",
                "PETR12 - PETROBRAS DIR",
                3,
                "-",
                "-",
            ),
            _linha(
                "Debito",
                "01/02/2025",
                "Direitos de Subscrição - Não Exercido",
                "PETR12 - PETROBRAS DIR",
                3,
                "-",
                "-",
            ),
            _linha(
                "Credito",
                "01/02/2025",
                "Cessão de Direitos",
                "PETR12 - PETROBRAS DIR",
                3,
                "-",
                "-",
            ),
            _linha(
                "Debito",
                "01/02/2025",
                "Cessão de Direitos - Solicitada",
                "PETR12 - PETROBRAS DIR",
                3,
                "-",
                "-",
            ),
        ]
    )
    assert mov.lancamentos == ()
    assert mov.fora_das_contas == 7
    assert not any("não reconhecido" in a for a in mov.avisos)


def test_tipo_desconhecido_vira_aviso_e_nao_soma():
    mov = _ler(
        [
            _linha("Credito", "01/02/2025", "Incorporação", PETR, 10, "-", "-"),
            _linha("Credito", "05/02/2025", "Dividendo", PETR, 10, 1, 10),
        ]
    )
    assert [x.tipo for x in mov.lancamentos] == ["dividendo"]
    assert any("não reconhecido" in a and "Incorporação" in a for a in mov.avisos)


def test_provento_em_debito_nao_soma():
    # um estorno de provento sairia como débito: não é dinheiro recebido
    mov = _ler([_linha("Debito", "05/02/2025", "Dividendo", PETR, 10, 1, 10)])
    assert mov.lancamentos == ()
    assert any("não reconhecido" in a for a in mov.avisos)


def test_periodo_da_movimentacao():
    mov = _ler(
        [
            _linha("Credito", "05/02/2026", "Dividendo", PETR, 10, 1, 10),
            _linha("Credito", "05/02/2025", "Dividendo", PETR, 10, 1, 10),
        ]
    )
    assert (mov.primeira_data, mov.ultima_data) == (date(2025, 2, 5), date(2026, 2, 5))


def test_planilha_de_posicao_no_lugar_da_movimentacao_explica_o_erro():
    arquivo = BytesIO()
    pd.DataFrame(
        {
            "Produto": [PETR],
            "Código de Negociação": ["PETR4"],
            "Quantidade": [1],
            "Valor Atualizado": [10],
        }
    ).to_excel(arquivo, sheet_name="Acoes", index=False)
    with pytest.raises(ArquivoDaB3Error, match="MOVIMENTAÇÃO"):
        ler_movimentacao(arquivo.getvalue(), "posicao.xlsx")


def test_arquivo_que_nao_e_planilha_fala_da_movimentacao():
    with pytest.raises(ArquivoDaB3Error, match="planilha de movimentação"):
        ler_movimentacao(b"nao sou um xlsx", "movimentacao.xlsx")


def test_movimentacao_de_varios_anos_cabe_no_limite():
    linhas = [
        _linha("Credito", "05/02/2025", "Rendimento", HGLG, 10, 1, 10)
    ] * 6000  # mais que o limite da posição (5.000)
    assert len(_ler(linhas).lancamentos) == 6000
    assert MAXIMO_DE_LINHAS_DA_MOVIMENTACAO >= 20_000


def test_data_invalida_explica_o_erro():
    with pytest.raises(ArquivoDaB3Error, match="data"):
        _ler([_linha("Credito", "31/02/2025", "Dividendo", PETR, 10, 1, 10)])


def test_movimentacao_de_exemplo_e_lida_sem_avisos_de_tipo_desconhecido():
    mov = ler_movimentacao(EXEMPLO.read_bytes(), EXEMPLO.name)
    assert mov.lancamentos
    assert not any("não reconhecido" in a for a in mov.avisos)
