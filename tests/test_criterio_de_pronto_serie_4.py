"""Critério de pronto das fontes novas da série 4 da base de ML (PR 7; ADR 0027, exigências 1, 2, 3, 8
e 9; ADR 0055, exigências 11 e 13; ADR 0074), conferido fonte por fonte, como o da série 3.

O que já tem prova em outro teste aparece pelo nome dele: se o teste sumir, este falha. Duas exigências
a mais nesta série: **nenhuma pessoa** (as fontes com administradores, contatos ou acionistas têm um
teste que prova que eles não entram) e **revisões** (a fonte que muda meses passados tem o teste de que
a revisão vira linha nova e o "como era na data" a ignora antes de ser vista).
"""

import importlib
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

from base import ofertas
from base.dicionario import TABELAS
from base.setoriais import anac, anatel, aneel, anp, ans, ons, susep
from scripts import carga_ofertas_e_conselhos
from src.banco.coletas import (
    REVENDA,
    SEM_LICENCA_CONHECIDA,
    licenca_da_fonte,
    revenda_da_fonte,
)

RAIZ = Path(__file__).resolve().parent.parent
DOMINIOS_OFICIAIS = {
    "sistemas.anac.gov.br",
    "www.gov.br",  # ANP
    "dados.ons.org.br",  # o portal do ONS (os arquivos ficam no bucket do próprio ONS)
    "dadosabertos.aneel.gov.br",
    "www.anatel.gov.br",
    "dadosabertos.ans.gov.br",
    "www2.susep.gov.br",
    "dados.cvm.gov.br",
}
SETORIAIS = "tests/test_carga_setoriais.py"
REVISOES = "tests/test_base_setoriais_revisoes.py::test_mes_revisado_vira_versao_e_como_era_ignora_a_revisao"
OFERTAS_E_CONSELHOS = "tests/test_ofertas_e_conselhos.py"
SEM_PESSOAS = (
    f"{OFERTAS_E_CONSELHOS}::test_nenhum_cpf_e_nenhuma_coluna_pessoal_proibida"
)
REPRODUTIVEL_SETORIAIS = (
    f"{SETORIAIS}::test_segunda_carga_com_os_mesmos_originais_nao_regrava"
)
LINHAGEM_SETORIAIS = (
    f"{SETORIAIS}::test_grava_cada_fonte_por_ano_com_manifesto_e_linhagem"
)
CARGA_OFERTAS_E_CONSELHOS = (
    f"{OFERTAS_E_CONSELHOS}::test_carga_grava_cada_tabela_com_manifesto_e_linhagem"
)


def _setorial(registro: str, endereco: str, tabela: str, **extra: str) -> dict:
    return {
        "fontes_no_registro": [registro],
        "enderecos": [endereco],
        "tabelas": [tabela],
        "reprodutivel": REPRODUTIVEL_SETORIAIS,
        "linhagem": LINHAGEM_SETORIAIS,
        **extra,
    }


# fonte → (registro de coletas, endereços, tabelas do dicionário, testes que provam 9, 13 e os extras)
FONTES = {
    "ANAC": _setorial(
        anac.FONTE, "base.arquivo.fontes:ESTATISTICO_DA_ANAC", "anac_estatistico"
    ),
    "ANP": _setorial(anp.FONTE, "base.arquivo.fontes:DADOS_DA_ANP", "anp_vendas"),
    "ONS": _setorial(ons.FONTE, "base.arquivo.fontes:PORTAL_DO_ONS", "ons_geracao"),
    "ANEEL SAMP": _setorial(
        aneel.FONTE,
        "base.arquivo.fontes:PORTAL_DA_ANEEL",
        "aneel_samp",
        revisoes=REVISOES,
        sem_pessoas="tests/test_base_setoriais_revisoes.py::test_samp_soma_as_linhas_de_cada_acessante_e_tira_a_media_do_percentual",
    ),
    "Anatel": _setorial(
        anatel.FONTE,
        "base.arquivo.fontes:ZIPS_DA_ANATEL",
        "anatel_acessos",
        revisoes=REVISOES,
    ),
    "ANS": _setorial(
        ans.FONTE,
        "base.setoriais.ans:URL",
        "ans_beneficiarios",
        revisoes=f"{SETORIAIS}::test_mes_revisado_pela_ans_vira_linha_nova_com_o_dia_em_que_foi_visto",
    ),
    "SUSEP": _setorial(
        susep.FONTE,
        "base.arquivo.fontes:SES_DA_SUSEP",
        "susep_seguros",
        revisoes=REVISOES,
        sem_pessoas="tests/test_base_arquivo_obter.py::test_susep_tira_do_zip_so_os_csvs_sem_pessoas",
    ),
    "CVM ofertas públicas": {
        "fontes_no_registro": [ofertas.FONTE],
        "enderecos": ["base.ofertas:URL"],
        "tabelas": ["ofertas_antigas", "ofertas_resolucao_160"],
        "reprodutivel": CARGA_OFERTAS_E_CONSELHOS,
        "linhagem": CARGA_OFERTAS_E_CONSELHOS,
        "sem_pessoas": SEM_PESSOAS,
    },
    "CVM FRE (conselhos e remuneração)": {
        "fontes_no_registro": [carga_ofertas_e_conselhos.FONTE_DO_FRE],
        "enderecos": ["https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/"],
        "tabelas": [
            "fre_conselho",
            "fre_comites",
            "fre_remuneracao",
            "fre_remuneracao_extremos",
            "fre_diversidade",
        ],
        "reprodutivel": CARGA_OFERTAS_E_CONSELHOS,
        "linhagem": CARGA_OFERTAS_E_CONSELHOS,
        "sem_pessoas": SEM_PESSOAS,
    },
}

# a coluna de "como era na data" de cada tabela (exigência 3)
COMO_ERA_NA_DATA = {
    **dict.fromkeys(
        [
            "anac_estatistico",
            "anp_vendas",
            "ons_geracao",
            "aneel_samp",
            "anatel_acessos",
            "ans_beneficiarios",
            "susep_seguros",
            "ofertas_antigas",
            "ofertas_resolucao_160",
        ],
        "disponivel_em",
    ),
    **dict.fromkeys(
        [
            "fre_conselho",
            "fre_comites",
            "fre_remuneracao",
            "fre_remuneracao_extremos",
            "fre_diversidade",
        ],
        "conhecido_em",
    ),
}
# as fontes que revisam meses passados guardam o dia em que cada valor foi visto
COM_REVISOES = {"aneel_samp", "anatel_acessos", "ans_beneficiarios", "susep_seguros"}


def _enderecos(item: str) -> list[str]:
    if ":" in item and not item.startswith("http"):
        modulo, nome = item.split(":")
        valor = getattr(importlib.import_module(modulo), nome)
        return list(valor) if isinstance(valor, tuple) else [valor]
    return [item]


def _existe(teste: str) -> bool:
    arquivo, nome = teste.split("::")
    texto = (RAIZ / arquivo).read_text(encoding="utf-8")
    return re.search(rf"^def {nome}\(", texto, re.MULTILINE) is not None


@pytest.mark.parametrize("fonte", FONTES)
def test_criterio_de_pronto_das_fontes_da_serie_4(fonte):
    dados = FONTES[fonte]
    # 1 e 11: licença conhecida e resposta sobre revenda, pela família no registro de coletas
    for registro in dados["fontes_no_registro"]:
        assert licenca_da_fonte(registro) != SEM_LICENCA_CONHECIDA, registro
        assert revenda_da_fonte(registro) in REVENDA.values(), registro
    # 2: origem segura (domínio oficial e HTTPS); o original vai para o acervo com SHA-256
    for item in dados["enderecos"]:
        for endereco in _enderecos(item):
            partes = urlparse(endereco)
            assert partes.scheme == "https", endereco
            assert partes.hostname in DOMINIOS_OFICIAIS, endereco
    for tabela in dados["tabelas"]:
        # 8: no dicionário, com as colunas
        assert TABELAS[tabela].colunas, tabela
        # 3: "como era na data" em cada tabela
        assert COMO_ERA_NA_DATA[tabela] in TABELAS[tabela].colunas, tabela
        if tabela in COM_REVISOES:
            assert "visto_em" in TABELAS[tabela].colunas, tabela
    # 9 e 13: os testes que provam continuam lá; e os das exigências desta série
    for prova in ("reprodutivel", "linhagem", "revisoes", "sem_pessoas"):
        if prova in dados:
            assert _existe(dados[prova]), dados[prova]


def test_toda_fonte_que_revisa_tem_o_teste_das_revisoes():
    for fonte, dados in FONTES.items():
        if set(dados["tabelas"]) & COM_REVISOES:
            assert "revisoes" in dados, fonte
