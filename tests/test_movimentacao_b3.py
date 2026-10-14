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
from src.dividendos_e_custo import Lancamento, custo_medio
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
            _linha("Credito", "01/02/2025", "Empréstimo", PETR, 10, "-", "-"),
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


def test_compra_no_fracionario_conta_no_mesmo_ativo():
    mov = _ler(
        [
            _linha(
                "Credito",
                "05/02/2025",
                "Transferência - Liquidação",
                PETR,
                100,
                30,
                3000,
            ),
            _linha(
                "Credito",
                "06/02/2025",
                "Transferência - Liquidação",
                "PETR4F - PETROLEO BRASILEIRO S/A PETROBRAS",
                5,
                31,
                155,
            ),
        ]
    )
    assert {x.codigo for x in mov.lancamentos} == {"PETR4"}


# --- aluguel de ações: saída sem dinheiro não é venda (13/10/2026) -----------------------------
VGIR = "VGIR11 - VALORA CRI CDI FUNDO DE INVESTIMENTO IMOBILIARIO"


def _aluguel_de(quantidade, data):
    """As 4 linhas que a B3 escreve quando a pessoa empresta as ações (copiadas da planilha real)."""
    return [
        _linha("Credito", data, "Empréstimo", VGIR, quantidade, "-", "-"),
        _linha("Credito", data, "Transferência", VGIR, quantidade, "-", "-"),
        _linha(
            "Debito", data, "Transferência - Liquidação", VGIR, quantidade, "-", "-"
        ),
        _linha("Debito", data, "Transferência", VGIR, quantidade, "-", "-"),
    ]


def test_acoes_emprestadas_nao_viram_venda():
    """Regressão (13/10/2026, planilha real do Tiago): ao emprestar 9.205 cotas, a B3 escreveu uma
    "Transferência - Liquidação" de saída sem valor; o leitor contava como venda de tudo, e o
    custo médio recomeçava na compra seguinte (1.300 cotas em vez de 10.505)."""
    mov = _ler(
        [
            _linha("Credito", "18/07/2026", "Reembolso", VGIR, 0, "-", 104),
            _linha(
                "Credito",
                "13/07/2026",
                "Transferência - Liquidação",
                VGIR,
                100,
                11,
                1100,
            ),
            *_aluguel_de(800, "03/07/2026"),
            _linha(
                "Credito",
                "04/12/2025",
                "Transferência - Liquidação",
                VGIR,
                1000,
                10,
                10000,
            ),
        ]
    )
    assert [lanc.tipo for lanc in mov.lancamentos] == ["compra", "compra", "reembolso"]
    (custo,) = custo_medio(list(mov.lancamentos))
    assert custo.completo
    assert custo.quantidade == 1100
    assert custo.custo_total == pytest.approx(11100)
    assert any(
        "VGIR11" in aviso and "não" in aviso and "venda" in aviso
        for aviso in mov.avisos
    )


def test_acoes_que_voltam_do_aluguel_nao_viram_compra():
    mov = _ler(
        [
            _linha(
                "Credito",
                "05/09/2026",
                "Transferência - Liquidação",
                VGIR,
                800,
                "-",
                "-",
            ),
            *_aluguel_de(800, "03/07/2026"),
            _linha(
                "Credito",
                "04/12/2025",
                "Transferência - Liquidação",
                VGIR,
                1000,
                10,
                10000,
            ),
        ]
    )
    (custo,) = custo_medio(list(mov.lancamentos))
    assert custo.completo and custo.quantidade == 1000
    assert custo.custo_total == pytest.approx(10000)


def test_entrada_sem_valor_que_nao_e_volta_continua_sem_custo_conhecido():
    """Ações recebidas sem valor sem uma saída antes (de outra pessoa, por exemplo): o custo
    delas não está na planilha, então o ativo fica com o custo médio incompleto."""
    mov = _ler(
        [
            _linha(
                "Credito",
                "05/09/2026",
                "Transferência - Liquidação",
                VGIR,
                300,
                "-",
                "-",
            ),
            _linha(
                "Credito",
                "04/12/2025",
                "Transferência - Liquidação",
                VGIR,
                1000,
                10,
                10000,
            ),
        ]
    )
    (custo,) = custo_medio(list(mov.lancamentos))
    assert not custo.completo


def test_taxa_do_aluguel_vira_renda_e_a_linha_so_de_quantidade_fica_de_fora():
    """A B3 escreve o aluguel de ações em duas linhas "Empréstimo" (planilha real, 13/10/2026):
    uma com a quantidade emprestada e sem valor, outra sem quantidade e com a taxa recebida."""
    mov = _ler(
        [
            _linha("Credito", "25/09/2026", "Empréstimo", VGIR, 0, "-", 7.61),
            _linha("Credito", "25/09/2026", "Empréstimo", VGIR, 800, "-", "-"),
        ]
    )
    assert mov.lancamentos == (
        Lancamento(date(2026, 9, 25), "VGIR11", "aluguel", 0, 7.61),
    )
    assert mov.fora_das_contas == 1


# ---- movimentação real de 12 meses (14/10/2026): derivativos e transferências de provento ----


def test_futuros_e_opcoes_sao_contados_a_parte_e_nao_viram_renda_fixa():
    mov = _ler(
        [
            _linha("Credito", "02/02/2025", "Compra", "Futuro - WINV26", 1, 100, 100),
            _linha("Debito", "03/02/2025", "Venda", "Futuro - WDOU26", 2, 50, 100),
            _linha(
                "Credito",
                "03/02/2025",
                "Compra",
                "Opção de Compra - BOVAE133 - BOVA11",
                1,
                1,
                1,
            ),
            _linha(
                "Debito",
                "04/02/2025",
                "Venda",
                "Opção de Venda - BOVAQ133 - BOVA11",
                1,
                1,
                1,
            ),
            _linha(
                "Credito", "04/02/2025", "Juros", "CRA - CRA123 - EMISSORA", 1, 5, 5
            ),
        ]
    )
    assert mov.lancamentos == ()
    texto = " ".join(mov.avisos)
    assert "4 linhas de futuros e opções" in texto
    assert "1 linha de Tesouro e renda fixa ficou" in texto


def test_so_derivativos_nao_gera_aviso_de_renda_fixa():
    mov = _ler([_linha("Credito", "02/02/2025", "Compra", "Futuro - WINV26", 1, 1, 1)])
    assert len(mov.avisos) == 1
    assert "futuros e opções" in mov.avisos[0]
    assert "renda fixa" not in mov.avisos[0]


def test_provento_transferido_entre_corretoras_fica_de_fora_sem_aviso():
    mov = _ler(
        [
            _linha(
                "Credito", "02/02/2025", "Dividendo - Transferido", PETR, 10, 1, 7.5
            ),
            _linha("Debito", "02/02/2025", "Dividendo - Transferido", PETR, 10, 1, 7.5),
            _linha(
                "Credito",
                "03/02/2025",
                "Juros Sobre Capital Próprio - Transferido",
                PETR,
                10,
                1,
                3.2,
            ),
            _linha(
                "Debito",
                "03/02/2025",
                "Juros Sobre Capital Próprio - Transferido",
                PETR,
                10,
                1,
                3.2,
            ),
            _linha("Credito", "04/02/2025", "Dividendo", PETR, 10, 1, 10),
        ]
    )
    assert [x.tipo for x in mov.lancamentos] == ["dividendo"]
    assert mov.fora_das_contas == 4
    assert not any("não reconhecido" in a for a in mov.avisos)


def test_amortizacao_de_fii_vira_lancamento_que_reduz_o_custo():
    mov = _ler(
        [
            _linha(
                "Credito",
                "02/02/2025",
                "Transferência - Liquidação",
                HGLG,
                10,
                100,
                1000,
            ),
            _linha("Credito", "01/03/2025", "Amortização", HGLG, 10, 10, 100),
        ]
    )
    assert [x.tipo for x in mov.lancamentos] == ["compra", "amortizacao"]
    (custo,) = custo_medio(list(mov.lancamentos))
    assert custo.custo_total == pytest.approx(900)
    assert not any("não reconhecido" in a for a in mov.avisos)


def test_atualizacao_continua_fora_das_contas_com_aviso():
    mov = _ler([_linha("Credito", "02/02/2025", "Atualização", PETR, 1900, "-", "-")])
    assert mov.lancamentos == ()
    assert any("não reconhecido" in a and "Atualização" in a for a in mov.avisos)
