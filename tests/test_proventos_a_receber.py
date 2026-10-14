"""A planilha de proventos a receber da Área do Investidor da B3 (Extratos → Eventos).

As colunas e os formatos (data em texto dd/mm/aaaa ou "-" quando ainda não há data, quantidade em
texto com vírgula, tipos de evento em maiúsculas, "Reembolso - ..." para ação emprestada e a
última linha "Total líquido") foram copiados de uma planilha real de 2026; os valores aqui são
inventados.
"""

from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from src.carteira_b3 import ArquivoDaB3Error
from src.proventos_a_receber import (
    MAXIMO_DE_LINHAS_DOS_PROVENTOS,
    ler_proventos_a_receber,
)

COLUNAS = [
    "Produto",
    "Tipo",
    "Tipo de Evento",
    "Previsão de pagamento",
    "Instituição",
    "Conta",
    "Quantidade",
    "Preço unitário",
    "Valor líquido",
]
CORRETORA = "CORRETORA FICTICIA S/A"
EXEMPLO = (
    Path(__file__).parent.parent / "conteudo" / "proventos_a_receber_de_exemplo.xlsx"
)
PETR = "PETR4 - PETROLEO BRASILEIRO S.A. PETROBRAS"
HGLG = "HGLG11 - CGHG LOGISTICA FDO INV IMOB - FII"


def _linha(produto, evento, data, quantidade, preco, valor, tipo="PN"):
    return [produto, tipo, evento, data, CORRETORA, 1234567, quantidade, preco, valor]


def _total(valor):
    return [None] * 7 + ["Total líquido", valor]


def _xlsx(linhas, aba="Proventos a Receber"):
    arquivo = BytesIO()
    pd.DataFrame(linhas, columns=COLUNAS).to_excel(arquivo, sheet_name=aba, index=False)
    return arquivo.getvalue()


def _ler(linhas):
    return ler_proventos_a_receber(_xlsx(linhas), "eventos.xlsx")


def test_le_os_proventos_pelo_nome_das_colunas():
    proventos = _ler(
        [
            _linha(PETR, "DIVIDENDO", "20/11/2026", "100", 1.13, 113.0),
            _total(113.0),
        ]
    )
    (item,) = proventos.itens
    assert item.codigo == "PETR4"
    assert item.tipo == "Dividendo"
    assert item.data == date(2026, 11, 20)
    assert item.quantidade == 100
    assert item.valor == pytest.approx(113.0)
    assert proventos.total == pytest.approx(113.0)


def test_a_linha_do_total_fica_de_fora():
    proventos = _ler(
        [
            _linha(PETR, "DIVIDENDO", "20/11/2026", "100", 1.0, 100.0),
            _linha(HGLG, "RENDIMENTO", "14/11/2026", "10", 1.1, 11.0, tipo="Fundo"),
            _total(111.0),
        ]
    )
    assert len(proventos.itens) == 2
    assert proventos.total == pytest.approx(111.0)


def test_sem_data_prevista_fica_sem_data_e_vai_para_o_fim():
    proventos = _ler(
        [
            _linha(PETR, "JUROS SOBRE CAPITAL PRÓPRIO", "-", "100", 0.3, 25.5),
            _linha(HGLG, "RENDIMENTO", "14/11/2026", "10", 1.1, 11.0, tipo="Fundo"),
        ]
    )
    assert [i.codigo for i in proventos.itens] == ["HGLG11", "PETR4"]
    assert proventos.itens[-1].data is None
    assert proventos.itens[-1].tipo == "JCP (líquido)"


def test_ordena_pela_data_prevista():
    proventos = _ler(
        [
            _linha(PETR, "DIVIDENDO", "20/12/2026", "100", 1.0, 100.0),
            _linha(HGLG, "RENDIMENTO", "14/11/2026", "10", 1.1, 11.0, tipo="Fundo"),
        ]
    )
    assert [i.data for i in proventos.itens] == [date(2026, 11, 14), date(2026, 12, 20)]


def test_reembolso_e_provento_de_acao_emprestada():
    proventos = _ler(
        [_linha(PETR, "Reembolso - DIVIDENDO", "20/11/2026", "50", 1.0, 50.0)]
    )
    assert proventos.itens[0].tipo == "Reembolso de dividendo (ação emprestada)"


def test_leilao_de_fracoes_entra_como_dinheiro_a_receber():
    proventos = _ler([_linha(PETR, "LEILÃO DE FRAÇÕES", "05/11/2026", "-", 31.2, 31.2)])
    (item,) = proventos.itens
    assert item.tipo == "Leilão de frações"
    assert item.quantidade == 0
    assert item.valor == pytest.approx(31.2)


def test_tipo_desconhecido_aparece_com_o_nome_da_b3():
    proventos = _ler(
        [_linha(PETR, "RESTITUIÇÃO DE CAPITAL", "05/11/2026", "100", 0.5, 50.0)]
    )
    assert proventos.itens[0].tipo == "Restituição de capital"


def test_quantidade_com_virgula_e_fracionario():
    proventos = _ler(
        [
            _linha(
                "PETR4F - PETROLEO BRASILEIRO", "DIVIDENDO", "20/11/2026", "1,5", 1, 1.5
            )
        ]
    )
    (item,) = proventos.itens
    assert item.codigo == "PETR4"
    assert item.quantidade == pytest.approx(1.5)


def test_guarda_o_nome_de_cada_ativo():
    proventos = _ler(
        [_linha(HGLG, "RENDIMENTO", "14/11/2026", "10", 1.1, 11.0, tipo="Fundo")]
    )
    assert proventos.nomes == {"HGLG11": "CGHG LOGISTICA FDO INV IMOB - FII"}


def test_linha_sem_codigo_de_negociacao_fica_de_fora_com_aviso():
    proventos = _ler(
        [
            _linha(
                "Tesouro Selic 2029", "PAGAMENTO DE JUROS", "01/01/2027", "1", 10, 10.0
            ),
            _linha(PETR, "DIVIDENDO", "20/11/2026", "100", 1.0, 100.0),
        ]
    )
    assert [i.codigo for i in proventos.itens] == ["PETR4"]
    assert any("1 linha" in aviso for aviso in proventos.avisos)


def test_planilha_vazia_nao_tem_proventos():
    proventos = _ler([_total(0.0)])
    assert proventos.itens == ()
    assert proventos.total == 0


def test_data_que_nao_entendo_da_erro_claro():
    with pytest.raises(ArquivoDaB3Error, match="dd/mm/aaaa"):
        _ler([_linha(PETR, "DIVIDENDO", "2026-11-20x", "100", 1.0, 100.0)])


def test_arquivo_sem_as_colunas_da_erro_claro():
    arquivo = BytesIO()
    pd.DataFrame({"Código": ["PETR4"], "Quantidade": [100]}).to_excel(
        arquivo, index=False
    )
    with pytest.raises(ArquivoDaB3Error, match="PROVENTOS A RECEBER"):
        ler_proventos_a_receber(arquivo.getvalue(), "outra.xlsx")


def test_recusa_planilha_com_linhas_demais():
    linhas = [_linha(PETR, "DIVIDENDO", "20/11/2026", "1", 1.0, 1.0)] * (
        MAXIMO_DE_LINHAS_DOS_PROVENTOS + 1
    )
    with pytest.raises(ArquivoDaB3Error, match="linhas"):
        _ler(linhas)


def test_o_exemplo_da_pasta_conteudo_le_sem_aviso():
    proventos = ler_proventos_a_receber(EXEMPLO.read_bytes(), EXEMPLO.name)
    assert proventos.itens and not proventos.avisos
    assert proventos.total == pytest.approx(sum(i.valor for i in proventos.itens))
