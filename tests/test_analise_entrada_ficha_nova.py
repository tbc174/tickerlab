"""As seções novas da ficha da noite (PR 2 dos relatórios v2) chegam à entrada da análise escrita.

A ficha de exemplo da CPFL é anterior a elas; aqui entram a qualidade do lucro e o capital e
acionistas, montadas pelas mesmas funções da base (tabelas pequenas de `test_dossie_lucro_e_capital`),
e se confere que cada uma vira linhas citáveis, só do Pro, dentro do corte de data e do tamanho.
"""

import dataclasses
import json
from datetime import timedelta

import pytest

from base import dossie as dossie_da_base
from src import dossie
from src import relatorio_empresa as re_
from src.analise_escrita import entrada as en
from tests import test_dossie_lucro_e_capital as ficha_nova
from tests.ajudantes_da_analise import CORTE, entradas_da_cpfl

NOVAS = ("qualidade_do_lucro", "capital_e_acionistas")
LIMITE_DE_CARACTERES = (
    120_000  # folga sobre os 90 mil da CPFL: a entrada não pode crescer sem a gente ver
)


def _ficha_com_as_secoes_novas() -> dossie.Ficha:
    base = dossie.ler_ficha(dossie.FICHA_DE_EXEMPLO)
    assert base is not None
    novas = [
        ficha_nova._qualidade(
            como_era=ficha_nova._como_era(),
            releases=ficha_nova._releases(),
            trocas=ficha_nova._trocas(),
        ),
        ficha_nova._capital(
            negociacoes=ficha_nova._negociacoes(),
            eventos=ficha_nova._eventos_de_capital(),
            painel=ficha_nova._painel(),
        ),
    ]
    bruta = dossie_da_base.montar_ficha(
        base.cnpj, base.empresa, novas, base.gerado_em.isoformat()
    )
    secoes = [*base.secoes, *dossie.Ficha.model_validate(bruta).secoes]
    return base.model_copy(update={"secoes": secoes})


@pytest.fixture(scope="module")
def entrada() -> dict:
    ficha = _ficha_com_as_secoes_novas()
    entradas = dataclasses.replace(
        entradas_da_cpfl(),
        dossie=dossie.dossie_da_ficha(dossie.cortar(ficha), CORTE),
    )
    com = re_.montar(entradas, plano="pro")
    sem = re_.montar(dataclasses.replace(entradas, dossie=None), plano="pro")
    return en.entrada_da_ficha(com, CORTE, sem_dossie=sem)


@pytest.mark.parametrize("chave", NOVAS)
def test_secao_nova_aparece_na_entrada_com_linhas_so_pro(entrada, chave):
    assert chave in entrada["secoes"]
    linhas = [linha for linha in entrada["linhas"] if linha["secao"] == chave]
    assert linhas, f"{chave} sumiu das linhas da entrada"
    assert all(linha["so_pro"] for linha in linhas)
    assert any(linha.get("valor") is not None for linha in linhas)


@pytest.mark.parametrize("chave", NOVAS)
def test_secao_nova_leva_a_data_da_base_e_a_fonte(entrada, chave):
    textos = [
        linha["texto"]
        for linha in entrada["linhas"]
        if linha["secao"] == chave and linha.get("texto")
    ]
    assert any(t.startswith("Dados da base do TickerLab de 17/10/2026") for t in textos)
    assert any(t.startswith("Fonte:") for t in textos)


def test_tabelas_das_secoes_novas_viram_linhas(entrada):
    tipos = {linha["tipo"] for linha in entrada["linhas"] if linha["secao"] in NOVAS}
    assert {"numero", "linha", "paragrafo"} <= tipos


def test_entrada_com_as_secoes_novas_cabe_no_pedido(entrada):
    caracteres = len(json.dumps(entrada, ensure_ascii=False, separators=(",", ":")))
    assert caracteres < LIMITE_DE_CARACTERES


def test_secoes_novas_respeitam_o_corte_de_data():
    ficha = _ficha_com_as_secoes_novas()
    entradas = dataclasses.replace(
        entradas_da_cpfl(), dossie=dossie.dossie_da_ficha(ficha, CORTE)
    )
    com = re_.montar(entradas, plano="pro")
    with pytest.raises(en.DataDepoisDoCorteError):
        en.entrada_da_ficha(com, CORTE - timedelta(days=400))
