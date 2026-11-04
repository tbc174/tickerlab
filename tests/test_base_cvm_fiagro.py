"""Informe mensal dos Fiagro: só classe com CNPJ de DV certo, a maior versão vale, o informe vale desde a
entrega (nunca desde o mês de referência) e nenhum contato entra.

O ZIP daqui é de mentira, no formato conferido em 04/11/2026 nos guardados pelo arquivista."""

import io
import zipfile

import pandas as pd

from base import cnpj as cnpjs
from base import cvm_fiagro


def _cnpj(raiz: str) -> str:
    for dv in range(100):
        bruto = f"{raiz}0001{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


FUNDO = _cnpj("11222333")
OUTRO = _cnpj("33000167")
INVALIDO = FUNDO[:-1] + str((int(FUNDO[-1]) + 1) % 10)
CABECALHO = (
    "CNPJ_Classe;Nome_Classe;Data_Referencia;Data_Entrega;Versao;Publico_Alvo;Codigo_ISIN;"
    "Mercado_Negociacao;CNPJ_Administrador;Email_Administrador;Site;CNPJ_Gestor;Numero_Cotistas;"
    "Valor_Ativo;Patrimonio_Liquido;Cotas_Emitidas;Valor_Patrimonial_Cotas;CRA"
)


def _linha(
    cnpj: str, versao: str = "1", entrega: str = "2026-07-03", cotistas: str = "10"
) -> str:
    return (
        f"{cnpj};FIAGRO DE MENTIRA;2026-06-01;{entrega};{versao};INVESTIDOR QUALIFICADO;;BALCAO;"
        f"{FUNDO};contato@exemplo.invalid;www.exemplo.invalid;{OUTRO};{cotistas};100.5;90.25;1000;0.09;5.5"
    )


def _zip(*linhas: str) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            "inf_mensal_fiagro_202606.csv",
            "\n".join([CABECALHO, *linhas]).encode("latin-1"),
        )
        z.writestr(
            "inf_mensal_fiagro_subclasse_202606.csv", b"CNPJ_Classe;Nome_Subclasse\n"
        )
    return saida.getvalue()


def test_so_classe_de_cnpj_certo_e_a_maior_versao_vale():
    conteudo = _zip(
        _linha(FUNDO, "1", cotistas="10"),
        _linha(FUNDO, "2", entrega="2026-07-20", cotistas="12"),
        _linha(INVALIDO),
    )
    tabela, contagem = cvm_fiagro.ler_mes(conteudo)
    assert len(tabela) == 1
    linha = tabela.iloc[0]
    assert linha["cnpj"] == cnpjs.formatar(FUNDO)
    assert linha["versao"] == 2
    assert linha["cotistas"] == 12
    assert linha["patrimonio_liquido"] == 90.25
    assert linha["cnpj_gestor"] == cnpjs.formatar(OUTRO)
    assert contagem == {"linhas": 3, "cnpj_invalido": 1, "versao_antiga": 1}


def test_disponivel_na_entrega_e_nao_na_referencia():
    tabela, _ = cvm_fiagro.ler_mes(_zip(_linha(FUNDO)))
    assert tabela["referencia"].iloc[0] == pd.Timestamp("2026-06-01")
    assert tabela["disponivel_em"].iloc[0] == pd.Timestamp("2026-07-03")


def test_contato_do_administrador_nao_entra():
    tabela, _ = cvm_fiagro.ler_mes(_zip(_linha(FUNDO)))
    assert "exemplo.invalid" not in tabela.astype(str).to_csv()
    assert "email_administrador" not in tabela.columns


def test_zip_sem_informe_da_classe_devolve_tabela_vazia():
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("meta_inf_mensal_fiagro.txt", b"x")
    tabela, contagem = cvm_fiagro.ler_mes(saida.getvalue())
    assert list(tabela.columns) == cvm_fiagro.COLUNAS
    assert contagem["linhas"] == 0
