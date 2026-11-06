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
# Ficam de fora, de propósito: `bm`, `cgu` e `cftc` (revenda só uso interno). `rfb-cnpj` passa desde
# que `TERMOS_LIDOS_EM` ganhou a data da leitura (coleta `robots_fecha` com as duas condições).
PASSAM_AS_MARCAS = {
    "antt",
    "conab",  # vendável por risco assumido (ADR 0122, 05/11/2026)
    "bcb",
    "ccee",
    "chirps",
    "chirps3",
    "gdelt",
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
    "bis",
    "dgagri",  # CC BY 4.0 da Comissão Europeia, lido em 24/10/2026 (linha 396)
    "boc",  # Bank of Canada: livre citando o Banco, termos relidos em 05/11/2026 (linha 396)
    "riksbank",  # reuso livre citando a fonte, termos lidos em 29/10/2026 (linha 511)
    "rfb-cnpj",
    "goias",  # CC BY, termos relidos em 05/11/2026 (linha 688)
    "spcapital",  # CC0, termos relidos em 05/11/2026 (linha 688)
    "msestado",  # CC BY, "pode" do Tiago em 05/11/2026 (linha 688)
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
    for familia in ("mb", "ibge", "inmet", "pgfn", "comexstat", "ebc"):
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
    """A linha 159 só preenche coleta e guarda; a revenda é da Emenda 5 (linha 161)."""
    # a ADR 0122 (05/11/2026) mudou o MapBiomas para vendável por risco assumido; o Kraken não mudou
    assert coletas.revenda_da_fonte("mapbiomas") == coletas.VENDAVEL_RISCO_ASSUMIDO
    assert coletas.marca_da_fonte("kraken") is coletas.Marca.NAO_COMERCIAL
    assert coletas.marca_da_fonte("gdelt") is coletas.Marca.VENDAVEL
    assert coletas.marca_da_fonte("cftc") is coletas.Marca.VENDAVEL


def test_bis_foi_lido_em_03_11_e_coleta_aberta_sem_prazo() -> None:
    """Linha 639: `data.bis.org/help/legal` libera o uso e o robots.txt não fecha a API (ADR 0121)."""
    from base.arquivo.registro import TERMOS_LIDOS_EM

    resposta = coletas.COLETA_E_GUARDA["bis"]
    assert resposta.coleta is Coleta.ABERTA
    assert resposta.guarda is Guarda.SEM_PRAZO
    assert TERMOS_LIDOS_EM["bis"] == date(2026, 11, 3)
    assert coletas.marca_da_fonte("bis") is coletas.Marca.VENDAVEL
