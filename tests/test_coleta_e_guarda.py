"""Coleta e guarda de cada família do `LICENCAS` (linha 159 da fila; ADR 0108, D3 e D5.3).

As respostas vêm da auditoria N0 de 21/10/2026; o que ela não respondeu fica `nao_lida` / `nao_diz`.
"""

from datetime import date

import pytest

from src import portao_externo
from src.banco import coletas
from src.banco.coletas import Coleta, Guarda

HOJE = date(2026, 10, 26)

# Famílias que passam as marcas do portão externo (revenda, guarda, coleta, leitura dos termos).
# Ficam de fora, de propósito: `bm`, `cgu` e `cftc` (revenda só uso interno); `rfb-cnpj` (coleta
# `robots_fecha` com as duas condições, mas `TERMOS_LIDOS_EM` ainda não tem a data da leitura)
PASSAM_AS_MARCAS = {
    "antt",
    "bcb",
    "ccee",
    "chirps",
    "cvm",
    "tce-rs-empenhos",
    "aneel",
    "tesouro",
    "gleif",
    "tce-pr",
    "tce-pr-pit",
    "tce-pr-despesa",
    "tesouro-br",
    "tesouro-br-divida",
    "tesouro-br-direto",
    "tesouro-br-leiloes",
    "anp",
    "anac",
    "ans",
    "anatel",
    "susep",
    "usda",
    "faostat",
}


def test_toda_familia_do_licencas_tem_coleta_e_guarda() -> None:
    sem_resposta = set(coletas.LICENCAS) - set(coletas.COLETA_E_GUARDA)
    assert not sem_resposta, f"família sem coleta e guarda: {sorted(sem_resposta)}"


@pytest.mark.parametrize("familia", sorted(coletas.COLETA_E_GUARDA))
def test_as_respostas_de_cada_familia_fecham(familia: str) -> None:
    resposta = coletas.COLETA_E_GUARDA[familia]
    assert isinstance(resposta.coleta, Coleta)
    assert isinstance(resposta.guarda, Guarda)
    if resposta.guarda is Guarda.COM_PRAZO:
        assert resposta.dias_de_guarda and resposta.dias_de_guarda > 0
    else:
        assert resposta.dias_de_guarda is None
    if resposta.coleta is not Coleta.ROBOTS_FECHA:
        # as condições (a) e (b) do D5.3 só têm sentido quando o robots.txt fecha
        assert not resposta.licenca_permite_reuso_comercial
        assert not resposta.respeita_ritmo_e_se_identifica


def test_o_que_a_auditoria_vedou_nao_sai() -> None:
    """Yahoo, Kraken, FNC e FMI: o termo veda; a guarda do Yahoo, da Kraken e da FNC também."""
    for familia in ("yahoo", "kraken", "fnc", "fmi", "b3", "contrapartes"):
        assert coletas.COLETA_E_GUARDA[familia].coleta is Coleta.TERMO_VEDA, familia
    for familia in ("yahoo", "kraken", "fnc"):
        assert coletas.COLETA_E_GUARDA[familia].guarda is Guarda.NAO_GUARDAR, familia


def test_familia_que_a_auditoria_nao_leu_continua_negada() -> None:
    for familia in ("mb", "ibge", "inmet", "pgfn", "comexstat", "bis", "ebc"):
        resposta = coletas.COLETA_E_GUARDA[familia]
        assert resposta.coleta is Coleta.NAO_LIDA, familia
        assert resposta.guarda is Guarda.NAO_DIZ, familia


def test_familias_que_passam_o_portao_externo_pelas_marcas() -> None:
    regras = portao_externo.regras_vigentes()
    passam = {
        familia
        for familia in coletas.LICENCAS
        if portao_externo._negacao_das_marcas(familia, HOJE, regras) is None
    }
    assert passam == PASSAM_AS_MARCAS


def test_nenhuma_marca_de_revenda_mudou() -> None:
    """A linha 159 só preenche coleta e guarda; a revenda é da linha 125."""
    assert coletas.marca_da_fonte("mapbiomas") is coletas.Marca.VENDAVEL
    assert coletas.marca_da_fonte("kraken") is coletas.Marca.NAO_COMERCIAL
    assert coletas.marca_da_fonte("gdelt") is coletas.Marca.A_CONFIRMAR
    assert coletas.marca_da_fonte("cftc") is coletas.Marca.USO_INTERNO
