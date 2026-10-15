"""Critério de pronto das fontes novas da série 3 da base de ML (PR 8; ADR 0027, exigências 1, 2, 3, 8
e 9; ADR 0055, exigências 11 e 13), conferido fonte por fonte.

O que já tem prova em outro teste aparece pelo nome dele: se o teste sumir, este falha. O que ainda
falta fica em `PENDENCIAS`, com o motivo. A única (o FCA sem a data de entrega) foi resolvida na série
4, PR 1: as tabelas do FCA valem pelo `DT_RECEB`.
"""

import importlib
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

from base.dicionario import TABELAS
from scripts import carga_bcb_credito, carga_cda, carga_fca, carga_fidc
from src.banco.coletas import (
    REVENDA,
    SEM_LICENCA_CONHECIDA,
    licenca_da_fonte,
    revenda_da_fonte,
)

RAIZ = Path(__file__).resolve().parent.parent
DOMINIOS_OFICIAIS = {"dados.cvm.gov.br", "olinda.bcb.gov.br", "www.bcb.gov.br"}

# fonte → (registro de coletas, endereços, tabelas do dicionário, testes que provam 9 e 13)
FONTES = {
    "CVM CDA": {
        "fontes_no_registro": [carga_cda.FONTE],
        "enderecos": [carga_cda.PASTA_DA_CVM],
        "tabelas": ["carteiras_dos_fundos", "carteiras_bloco_8"],
        "reprodutivel": "tests/test_carga_cda.py::test_ano_igual_ao_que_ja_tem_e_pulado",
        "linhagem": "tests/test_carga_cda.py::test_linhagem_do_ano_e_completa",
    },
    "CVM FCA": {
        "fontes_no_registro": [carga_fca.FONTE],
        "enderecos": [carga_fca.URL_DO_FCA],
        "tabelas": [
            "valores_mobiliarios",
            "emissores",
            "tickers_no_tempo",
            "codigos_invalidos",
        ],
        "reprodutivel": "tests/test_carga_fca.py::test_segunda_carga_le_do_acervo_sem_baixar_de_novo",
        "linhagem": "tests/test_carga_fca.py::test_linhagem_de_cada_tabela_e_completa",
    },
    "CVM FIDC e cadastro de fundos": {
        "fontes_no_registro": [carga_fidc.FONTE],
        "enderecos": [carga_fidc.PASTA_DO_INFORME, carga_fidc.PASTA_DO_CADASTRO],
        "tabelas": ["fidc_informe", "cadastro_de_fundos"],
        "reprodutivel": "tests/test_carga_fidc.py::test_carga_repetida_da_o_mesmo_resultado",
        "linhagem": "tests/test_carga_fidc.py::test_linhagem_do_informe_e_do_cadastro_e_completa",
    },
    "BC IF.data": {
        "fontes_no_registro": [carga_bcb_credito.FONTE_IFDATA],
        "enderecos": ["base.bcb_ifdata:API"],
        "tabelas": ["ifdata_valores", "ifdata_cadastro", "ligacao_dos_bancos"],
        "reprodutivel": "tests/test_carga_bcb_credito.py::test_revisao_do_bc_vira_versao",
        "linhagem": "tests/test_carga_bcb_credito.py::test_linhagem_do_ifdata_e_do_scr_e_completa",
    },
    "BC SCR.data": {
        "fontes_no_registro": [carga_bcb_credito.FONTE_SCR],
        "enderecos": ["base.bcb_scr:ENDERECO"],
        "tabelas": ["scr_credito"],
        "reprodutivel": "tests/test_carga_bcb_credito.py::test_scr_repetido_da_o_mesmo_resultado",
        "linhagem": "tests/test_carga_bcb_credito.py::test_linhagem_do_ifdata_e_do_scr_e_completa",
    },
}

# tabelas cuja data de "como era na data" é a própria coluna de tempo da fonte (exigência 3)
COMO_ERA_NA_DATA = {
    "valores_mobiliarios": "recebido_em",
    "tickers_no_tempo": "primeiro_visto",
    "emissores": "primeiro_recebido_em",
    "codigos_invalidos": "recebido_em",
    "carteiras_dos_fundos": "disponivel_em",
    "carteiras_bloco_8": "disponivel_em",
    "fidc_informe": "disponivel_em",
    "ifdata_valores": "disponivel_em",
    "scr_credito": "disponivel_em",
}
# retratos do cadastro na data da coleta: cada carga que muda algo vira versão `<nome>.v<N>`
RETRATOS = {"cadastro_de_fundos", "ifdata_cadastro", "ligacao_dos_bancos"}
PENDENCIAS: dict[tuple[str, int], str] = {}


def _endereco(item: str) -> str:
    if ":" in item and not item.startswith("http"):
        modulo, nome = item.split(":")
        return getattr(importlib.import_module(modulo), nome)
    return item


def _existe(teste: str) -> bool:
    arquivo, nome = teste.split("::")
    return (
        re.search(
            rf"^def {nome}\(",
            (RAIZ / arquivo).read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        is not None
    )


@pytest.mark.parametrize("fonte", FONTES)
def test_criterio_de_pronto_das_fontes_novas(fonte):
    dados = FONTES[fonte]
    # 1 e 11: licença conhecida e resposta sobre revenda, pela família no registro de coletas
    for registro in dados["fontes_no_registro"]:
        assert licenca_da_fonte(registro) != SEM_LICENCA_CONHECIDA, registro
        assert revenda_da_fonte(registro) in REVENDA.values(), registro
    # 2: origem segura (domínio oficial e HTTPS); o original vai para o acervo com SHA-256
    for item in dados["enderecos"]:
        endereco = urlparse(_endereco(item))
        assert endereco.scheme == "https" and endereco.hostname in DOMINIOS_OFICIAIS, (
            item
        )
    # 8: no dicionário, com as colunas
    for tabela in dados["tabelas"]:
        assert TABELAS[tabela].colunas, tabela
    # 3: "como era na data" em cada tabela (coluna de tempo, retrato com versões ou pendência)
    for tabela in dados["tabelas"]:
        if tabela in COMO_ERA_NA_DATA:
            assert COMO_ERA_NA_DATA[tabela] in TABELAS[tabela].colunas, tabela
        elif tabela not in RETRATOS:
            assert (fonte, 3) in PENDENCIAS, f"{fonte}: {tabela} sem como era na data"
    # 9 e 13: os testes que provam continuam lá
    assert _existe(dados["reprodutivel"]), dados["reprodutivel"]
    assert _existe(dados["linhagem"]), dados["linhagem"]
