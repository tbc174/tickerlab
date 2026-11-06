"""Seção do CNAE da companhia, no nome que o SCR do Banco Central usa."""

import pytest

from base import bcb_scr
from base.cnae import SECOES, secao_do_cnae
from tests.test_base_bcb import _scr


@pytest.mark.parametrize(
    ("codigo", "secao"),
    [
        ("0111301", "Agricultura, pecuária, produção florestal, pesca e aquicultura"),
        ("0600001", "Indústrias extrativas"),
        ("1011201", "Indústrias de transformação"),
        ("3511501", "Eletricidade e gás"),
        ("3600601", "Água, esgoto, atividades de gestão de resíduos e descontaminação"),
        ("4120400", "Construção"),
        ("4711301", "Comércio; reparação de veículos automotores e motocicletas"),
        ("6422100", "Atividades financeiras, de seguros e serviços relacionados"),
        ("6810202", "Atividades imobiliárias"),
        ("8411600", "Administração pública, defesa e seguridade social"),
        ("9700500", "Serviços domésticos"),
        (
            "9900800",
            "Organismos internacionais e outras instituições extraterritoriais",
        ),
    ],
)
def test_secao_pela_divisao_do_cnae(codigo, secao):
    assert secao_do_cnae(codigo) == secao


@pytest.mark.parametrize("codigo", ["4120400", "41.20-4-00", " 4120400 ", 4120400])
def test_aceita_o_codigo_com_pontuacao_ou_numero(codigo):
    assert secao_do_cnae(codigo) == "Construção"


@pytest.mark.parametrize("codigo", [None, "", "abc", "12", "0000000", "0400000"])
def test_codigo_sem_divisao_do_cnae_nao_tem_secao(codigo):
    assert secao_do_cnae(codigo) is None


def test_toda_secao_do_scr_pj_e_uma_das_nossas():
    """Os nomes não são de cabeça: são os do arquivo do BC (menos o 'Não informados')."""
    for nome in ("scrdata_2012.zip", "scrdata_2026.zip"):
        pj = bcb_scr.ler_ano(_scr(nome)).query("cliente == 'PJ'")["cnae_ocupacao"]
        nomes = set(pj.astype(str)) - {"Não informados"}
        assert nomes <= set(SECOES.values()), nomes - set(SECOES.values())
