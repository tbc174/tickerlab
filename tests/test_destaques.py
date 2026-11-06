"""Os destaques "O que a base mostra" (plano do relatório-modelo, 17/10/2026, PR 1, tarefa 3).

Cada destaque é um molde fixo com os números da ficha encaixados (ADR 0028, item 5: nenhuma frase de
modelo de linguagem). Os testes usam a ficha de exemplo da CPFL e cópias alteradas dela.
"""

import json
import re
from pathlib import Path

import pytest

from src import destaques, dossie
from tests.ajudantes_da_ficha import FICHA_DE_17_10


def _ficha(alterar=None, tmp_path: Path | None = None) -> dossie.Ficha:
    if alterar is None:
        ficha = dossie.ler_ficha(FICHA_DE_17_10)
    else:
        assert tmp_path is not None
        bruta = json.loads(FICHA_DE_17_10.read_text(encoding="utf-8"))
        alterar(bruta)
        caminho = tmp_path / "ficha.json"
        caminho.write_text(json.dumps(bruta), encoding="utf-8")
        ficha = dossie.ler_ficha(caminho)
    assert ficha is not None
    return dossie.cortar(ficha)


def _por_chave(ficha: dossie.Ficha) -> dict[str, destaques.Destaque]:
    return {d.chave: d for d in destaques.destaques_da_ficha(ficha)}


def test_fundos_no_ultimo_mes_completo_e_doze_meses_antes() -> None:
    fundos = _por_chave(_ficha())["fundos"]
    assert fundos.texto == (
        "370 fundos tinham papéis da empresa nas carteiras de mar/2026, o último mês com as "
        "carteiras completas na CVM, somando R$ 495,2 mi. Doze meses antes eram 455 fundos, "
        "com R$ 611,6 mi."
    )
    assert fundos.secao == "ofertas_e_fundos"
    assert fundos.data == "mar/2026"
    assert fundos.fonte.startswith("ODbL")


def test_ofertas_do_ultimo_ano_completo_e_quantas_empresas_do_grupo_emitiram() -> None:
    ofertas = _por_chave(_ficha())["ofertas"]
    assert ofertas.texto == (
        "Em 2025, o grupo registrou 14 ofertas na CVM, somando R$ 9,8 bi pelo valor registrado, "
        "emitidas por 6 empresas do grupo."
    )
    assert ofertas.data == "2025"


def test_ofertas_sem_a_lista_inteira_do_ano_nao_contam_os_emissores(
    tmp_path: Path,
) -> None:
    def tirar_uma(bruta: dict) -> None:
        secao = next(s for s in bruta["secoes"] if s["chave"] == "ofertas_e_fundos")
        secao["tabelas"]["ofertas"] = secao["tabelas"]["ofertas"][:-6]

    ofertas = _por_chave(_ficha(tirar_uma, tmp_path))["ofertas"]
    assert ofertas.texto.endswith("pelo valor registrado.")


def test_auditor_atual_o_anterior_e_quantas_trocas() -> None:
    auditor = _por_chave(_ficha())["auditor"]
    assert auditor.texto == (
        "PRICEWATERHOUSECOOPERS AUDITORES INDEPENDENTES audita a companhia desde 2022. Antes, "
        "KPMG Auditores Independentes ficou 4,8 anos. Foram 3 trocas de auditor desde 2012."
    )


def test_setor_regulado_com_a_parte_do_total() -> None:
    setor = _por_chave(_ficha())["setor"]
    assert setor.texto == (
        "Consumidores atendidos pelas distribuidoras (ANEEL): 9.743.641 em dez/2025, 11,1% do "
        "total da agência."
    )
    assert (
        setor.fonte
        == "ODbL (dados abertos da ANEEL; citar). SAMP sem CPF e nome do consumidor"
    )


def test_negocios_citam_o_assunto_como_a_empresa_escreveu() -> None:
    negocios = _por_chave(_ficha())["negocios"]
    assert negocios.texto == (
        "A base acha 89 fatos relevantes e comunicados da companhia sobre aquisições, "
        "alienações, fusões ou reorganizações. O último, em 02/02/2026: “Reorganização Societária - Incorporação, Cisão "
        "ou Fusão da Companhia”."
    )
    assert negocios.link.startswith("https://www.rad.cvm.gov.br/")


def test_controladas_do_fre() -> None:
    controladas = _por_chave(_ficha())["controladas"]
    assert (
        controladas.texto
        == "O FRE de 2026 lista 18 controladas e 1 coligada ou outra participação."
    )


def test_ordem_dos_destaques() -> None:
    assert [d.chave for d in destaques.destaques_da_ficha(_ficha())] == [
        "fundos",
        "ofertas",
        "setor",
        "auditor",
        "controladas",
        "negocios",
    ]


def test_sem_a_secao_o_destaque_nao_aparece(tmp_path: Path) -> None:
    def sem_fundos(bruta: dict) -> None:
        bruta["secoes"] = [
            s for s in bruta["secoes"] if s["chave"] != "ofertas_e_fundos"
        ]

    chaves = set(_por_chave(_ficha(sem_fundos, tmp_path)))
    assert "fundos" not in chaves and "ofertas" not in chaves
    assert "auditor" in chaves


def test_fundos_sem_o_mesmo_mes_do_ano_anterior_nao_comparam(tmp_path: Path) -> None:
    def poucos_meses(bruta: dict) -> None:
        secao = next(s for s in bruta["secoes"] if s["chave"] == "ofertas_e_fundos")
        secao["tabelas"]["fundos_por_mes"] = secao["tabelas"]["fundos_por_mes"][-5:]

    fundos = _por_chave(_ficha(poucos_meses, tmp_path))["fundos"]
    assert "Doze meses antes" not in fundos.texto


def test_fundos_com_um_mes_faltando_comparam_com_o_mesmo_mes(tmp_path: Path) -> None:
    def sem_um_mes(bruta: dict) -> None:
        secao = next(s for s in bruta["secoes"] if s["chave"] == "ofertas_e_fundos")
        del secao["tabelas"]["fundos_por_mes"][15]  # jul/2025

    fundos = _por_chave(_ficha(sem_um_mes, tmp_path))["fundos"]
    assert fundos.texto.endswith("Doze meses antes eram 455 fundos, com R$ 611,6 mi.")


PALAVRAS_PROIBIDAS = re.compile(
    r"compr[ae]\b|vend[ae]\b|recomend|fraude|risco alto|barat|caro\b|oportunidade|garant",
    re.IGNORECASE,
)


@pytest.mark.parametrize("molde", sorted(destaques.MOLDES.values()))
def test_moldes_sem_palavras_de_recomendacao_ou_acusacao(molde: str) -> None:
    assert not PALAVRAS_PROIBIDAS.search(molde), molde
