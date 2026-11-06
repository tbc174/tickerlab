"""Os press-releases de resultado no índice do IPE (vitrine, PR 1; plano de 17/10/2026)."""

from datetime import date

import pandas as pd

from base import releases

COLUNAS = [
    "CNPJ_Companhia", "Nome_Companhia", "Codigo_CVM", "Data_Referencia", "Categoria", "Tipo",
    "Assunto", "Data_Entrega", "Protocolo_Entrega", "Versao", "Link_Download",
]  # fmt: skip
CNPJ = "33.000.167/0001-01"


def _linha(
    categoria="Dados Econômico-Financeiros",
    tipo="Press-release",
    referencia="2025-09-30",
    entrega="2025-11-06",
    protocolo="P1",
    versao="1",
    cnpj=CNPJ,
):
    return [
        cnpj, "EMPRESA", "9512", referencia, categoria, tipo, "", entrega, protocolo, versao,
        f"https://rad/numProtocolo={protocolo}&numVersao={versao}",
    ]  # fmt: skip


def _ipe(*linhas):
    return pd.DataFrame(list(linhas), columns=COLUNAS)


def test_so_press_release_de_resultado():
    ipe = _ipe(
        _linha(protocolo="A"),
        _linha(tipo="Demonstrações Financeiras Anuais Completas", protocolo="B"),
        _linha(tipo="Relatório do Agente Fiduciário", protocolo="C"),
        _linha(tipo="Rating", protocolo="D"),
        _linha(categoria="Comunicado ao Mercado", tipo="", protocolo="E"),
        _linha(categoria="Fato Relevante", tipo="", protocolo="F"),
    )
    achados = releases.releases_de_resultado(ipe)
    assert list(achados["protocolo"]) == ["A"]
    assert list(achados.columns) == list(releases.COLUNAS)


def test_periodo_do_release():
    assert releases.periodo_do_trimestre(date(2025, 9, 30)) == "3T25"
    assert releases.periodo_do_trimestre(date(2025, 12, 31)) == "4T25"
    assert releases.periodo_do_trimestre(date(2026, 3, 31)) == "1T26"
    assert releases.periodo_do_trimestre(date(2024, 6, 30)) == "2T24"
    ipe = _ipe(_linha(referencia="2025-12-31", protocolo="X"))
    assert releases.releases_de_resultado(ipe)["periodo"].iloc[0] == "4T25"


def test_fica_a_versao_mais_nova_entregue_ate_a_data():
    ipe = _ipe(
        _linha(protocolo="P", versao="1", entrega="2025-11-06"),
        _linha(protocolo="P", versao="2", entrega="2025-11-20"),
    )
    assert releases.releases_de_resultado(ipe)["versao"].iloc[0] == 2
    # em 10/11 só a versão 1 existia: a reapresentação é do futuro
    no_dia = releases.releases_de_resultado(ipe, ate=date(2025, 11, 10))
    assert list(no_dia["versao"]) == [1]
    assert releases.releases_de_resultado(ipe, ate=date(2025, 11, 1)).empty


def test_sem_link_ou_sem_data_nao_entra():
    ipe = _ipe(_linha(protocolo="A"), _linha(protocolo="B", entrega=""))
    ipe.loc[0, "Link_Download"] = ""
    assert releases.releases_de_resultado(ipe).empty


def test_vazio_devolve_as_colunas():
    achados = releases.releases_de_resultado(_ipe())
    assert achados.empty and list(achados.columns) == list(releases.COLUNAS)
