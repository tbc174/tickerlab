"""Os pares com a geração de caixa (série T1): a margem EBITDA e o FCF de cada par saem da ficha da noite
dele; par sem a seção mostra "ainda sem dado", nunca um número inventado.
"""

import json
from pathlib import Path

import pandas as pd

from base import dossie as dossie_da_base
from src import dossie
from src import relatorio_empresa as re_
from tests.test_dossie_geracao_de_caixa import HOJE, _como_era
from tests.test_relatorio_empresa import WEG, _entradas, dados_da_weg  # noqa: F401

PERTO, SEM_FICHA = "02429144000193", "33000167000101"


def _gravar_ficha(pasta: Path, cnpj: str) -> None:
    bruta = dossie_da_base.montar_ficha(
        cnpj,
        "Perto S.A.",
        [dossie_da_base.secao_geracao_de_caixa(_como_era(), HOJE)],
        "2026-10-17T07:00:00-03:00",
    )
    destino = pasta / "atual" / f"{cnpj}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(bruta), encoding="utf-8")


def test_caixa_do_par_le_o_ultimo_exercicio_da_ficha(tmp_path: Path) -> None:
    _gravar_ficha(tmp_path, PERTO)
    assert dossie.caixa_do_par(PERTO, tmp_path) == {
        "exercicio": 2025,
        "margem_ebitda": 0.25,
        "fcf": 1_300e6,
    }
    assert dossie.caixa_do_par(SEM_FICHA, tmp_path) is None


def _pares_com_caixa(dados, caixa_do_par) -> list[dict]:
    pares = pd.DataFrame(
        {
            "cnpj": [PERTO, SEM_FICHA, WEG],
            "empresa": ["Perto", "Sem ficha", "WEG S.A."],
            "receita": [40e9, 20e9, 41e9],
        }
    )
    entradas = _entradas(dados, pares=pares, caixa_do_par=caixa_do_par)
    return re_.montar(entradas).secao("pares").tabelas["pares"]


def test_pares_mostram_margem_ebitda_e_fcf_ou_ainda_sem_dado(
    dados_da_weg,  # noqa: F811
    tmp_path: Path,
) -> None:
    _gravar_ficha(tmp_path, PERTO)
    perto, sem_ficha = _pares_com_caixa(
        dados_da_weg, lambda cnpj: dossie.caixa_do_par(cnpj, tmp_path)
    )
    assert perto["margem_ebitda"] == "25,0%"
    assert perto["fcf"] == "R$ 1,3 bi"
    assert perto["exercicio_do_caixa"] == "2025"
    assert sem_ficha["margem_ebitda"] == re_.AINDA_SEM_DADO
    assert sem_ficha["fcf"] == re_.AINDA_SEM_DADO


def test_sem_leitor_de_fichas_os_pares_ficam_so_com_a_receita(
    dados_da_weg,  # noqa: F811
) -> None:
    linhas = _pares_com_caixa(dados_da_weg, None)
    assert set(linhas[0]) == {"empresa", "receita"}


def test_pares_explicam_de_onde_vem_o_caixa(dados_da_weg) -> None:  # noqa: F811
    pares = pd.DataFrame({"cnpj": [PERTO], "empresa": ["Perto"], "receita": [40e9]})
    com = re_.montar(_entradas(dados_da_weg, pares=pares, caixa_do_par=lambda _: None))
    sem = re_.montar(_entradas(dados_da_weg, pares=pares))
    assert re_.SOBRE_O_CAIXA_DOS_PARES in com.secao("pares").paragrafos
    assert re_.SOBRE_O_CAIXA_DOS_PARES not in sem.secao("pares").paragrafos


def test_cabecalhos_dos_pares_com_siglas_e_acento() -> None:
    assert re_.rotulo_da_coluna("margem_ebitda") == "Margem EBITDA"
    assert re_.rotulo_da_coluna("fcf") == "FCF"
    assert re_.rotulo_da_coluna("exercicio_do_caixa") == "Exercício da margem e do FCF"
    assert re_.rotulo_da_coluna("dividendo_total") == "Dividendo total"
