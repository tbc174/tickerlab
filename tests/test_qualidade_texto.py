"""Textos do selo "dado em conferência" (série 1 da base de ML, PR 4): a frase que a tela mostra
ao lado do documento e a lista pública das regras."""

from datetime import date
from types import SimpleNamespace

from base.regras import VERSAO_DAS_REGRAS
from src.qualidade_texto import (
    REGRAS,
    contagem_por_documento,
    selo_do_documento,
    texto_do_selo,
)

REFEITO = (
    "A empresa refez este número no balanço seguinte, no documento entregue em 28/03/2024: Lucro "
    "do período era R$ 24,2 mi e passou a R$ -11,0 mi (de lucro para prejuízo)."
)


def _achado(regra="R6", documento="DFP", referencia=date(2022, 12, 31), porque=REFEITO):
    return SimpleNamespace(
        regra=regra, documento=documento, referencia=referencia, porque=porque
    )


def test_selo_traz_a_regra_o_documento_e_o_porque():
    texto = texto_do_selo(_achado())
    assert texto == (
        "Refeito pela empresa no balanço seguinte (DFP de 31/12/2022): " + REFEITO
    )


def test_regra_desconhecida_ainda_mostra_o_porque():
    texto = texto_do_selo(_achado(regra="R99", documento="ITR"))
    assert texto.startswith("Dado em conferência (ITR de 31/12/2022): ")
    assert texto.endswith(REFEITO)


def test_contagem_por_documento_junta_os_achados_de_cada_balanco():
    achados = [
        _achado(),
        _achado(regra="R1"),
        _achado(documento="ITR", referencia=date(2023, 3, 31)),
    ]
    contagem = contagem_por_documento(achados)
    assert contagem == {("DFP", date(2022, 12, 31)): 2, ("ITR", date(2023, 3, 31)): 1}


def test_selo_do_documento_sem_achado_fica_vazio():
    contagem = {("DFP", date(2022, 12, 31)): 2}
    assert (
        selo_do_documento(contagem, "DFP", date(2022, 12, 31)) == "Em conferência (2)"
    )
    assert selo_do_documento(contagem, "DFP", date(2023, 12, 31)) == ""


def test_toda_regra_que_roda_tem_texto_publico():
    """As regras que a tarefa diária roda (`base/rodada.py`) precisam aparecer no site."""
    from base.rodada import REGRAS_DE_UM_DOCUMENTO

    entre_documentos = ("R3", "R6", "R7", "R8")
    assert set(REGRAS) >= set(REGRAS_DE_UM_DOCUMENTO) | set(entre_documentos)
    assert all(r.titulo and r.o_que_confere for r in REGRAS.values())
    assert VERSAO_DAS_REGRAS == "1"  # mudou a versão: revise os textos públicos
