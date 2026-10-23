"""Registro de fontes (B-01): cada fonte do arquivista com licença, marca, ritmo e data da leitura dos termos."""

from datetime import date

import pytest

from base.arquivo import registro
from base.arquivo.fontes import FONTES
from src.banco.coletas import LICENCAS, REVENDA


def _tem_entrada(tabela: dict, fonte: str) -> bool:
    """A fonte (ou a família dela) tem linha própria: o padrão "a confirmar" não conta."""
    return fonte in tabela or fonte.split("-", 1)[0] in tabela


@pytest.mark.parametrize("fonte", [f.id for f in FONTES])
def test_toda_fonte_tem_marca_e_licenca_escritas(fonte):
    """Fonte nova sem marca nem licença registradas quebra aqui, em vez de cair no padrão calado."""
    assert _tem_entrada(REVENDA, fonte), (
        f"{fonte}: sem marca em REVENDA (src/banco/coletas.py)"
    )
    assert _tem_entrada(LICENCAS, fonte), (
        f"{fonte}: sem licença em LICENCAS (src/banco/coletas.py)"
    )


def test_o_registro_tem_uma_linha_por_fonte_na_ordem_do_catalogo():
    linhas = registro.registro_de_fontes()
    assert [r.id for r in linhas] == [f.id for f in FONTES]


def test_cada_linha_traz_licenca_marca_e_ritmo():
    for linha in registro.registro_de_fontes():
        assert linha.licenca and linha.marca and linha.ritmo, linha.id
        assert linha.marca in {
            "vendavel",
            "uso_interno",
            "nao_comercial",
            "a_confirmar",
        }
        assert linha.ritmo in {"diaria", "semanal", "mensal", "carga-unica"}


def test_marca_e_licenca_batem_com_as_funcoes_da_coleta():
    por_id = {r.id: r for r in registro.registro_de_fontes()}
    assert por_id["cvm-fidc"].marca == "vendavel"
    assert "ODbL" in por_id["cvm-fidc"].licenca
    assert por_id["rfb-cnpj"].marca == "vendavel"


def test_a_data_da_leitura_dos_termos_e_uma_data_ou_nada():
    por_id = {r.id: r for r in registro.registro_de_fontes()}
    assert por_id["inmet-bdmep"].termos_lidos_em == date(2026, 10, 21)
    assert por_id["cvm-fidc"].termos_lidos_em == date(2026, 10, 21)
    assert por_id["ibama-autos"].termos_lidos_em is None
    assert por_id["gleif-br"].termos_lidos_em == date(2026, 10, 21)


def test_toda_data_de_leitura_aponta_para_uma_familia_que_existe():
    # família coletada pelo arquivista ou com licença registrada (Kraken, Yahoo e outras vêm de outro coletor)
    familias = {f.id.split("-", 1)[0] for f in FONTES} | set(LICENCAS)
    assert set(registro.TERMOS_LIDOS_EM) <= familias


def test_a_exportacao_para_o_site_nao_leva_conversa_interna():
    for linha in registro.para_o_site():
        texto = " ".join(str(v) for v in linha.values())
        assert "ADR" not in texto and "src/" not in texto, linha["id"]
    assert registro.para_o_site()[0].keys() >= {
        "id",
        "licenca",
        "marca",
        "ritmo",
        "termos_lidos_em",
    }
