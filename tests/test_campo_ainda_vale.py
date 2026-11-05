"""`_campo_ainda_vale`: o que uma simulação guardada pode devolver às telas de hoje."""

import pytest

from src.carteiras import ESTRATEGIAS_DE_CARTEIRA
from src.estrategias import ESTRATEGIAS
from telas.dados_da_conta import ESPERAS_DEPOIS_DO_STOP, _campo_ainda_vale


def _primeiro_parametro(registro, com_opcoes):
    """Um parâmetro real do catálogo (numérico ou de escolha), para o teste não inventar limites."""
    for nome, estrategia in registro.items():
        for p in estrategia.parametros:
            if bool(getattr(p, "opcoes", None)) == com_opcoes:
                return nome, p
    return None


def test_estrategia_conhecida_vale_e_desconhecida_nao():
    assert _campo_ainda_vale("backtest_estrategia", next(iter(ESTRATEGIAS)))
    assert not _campo_ainda_vale("backtest_estrategia", "Extinta")
    assert _campo_ainda_vale("carteira_estrategia", next(iter(ESTRATEGIAS_DE_CARTEIRA)))
    assert not _campo_ainda_vale("carteira_estrategia", "Extinta")


def test_espera_depois_do_stop_so_aceita_as_opcoes_da_tela():
    assert _campo_ainda_vale(
        "espera_depois_do_stop", next(iter(ESPERAS_DEPOIS_DO_STOP))
    )
    assert not _campo_ainda_vale("espera_depois_do_stop", "Esperar 7 dias úteis")


def test_modo_de_custos_so_aceita_os_dois_modos():
    assert _campo_ainda_vale("backtest_modo_custos", "Um número só")
    assert _campo_ainda_vale("backtest_modo_custos", "Detalhados")
    assert not _campo_ainda_vale("backtest_modo_custos", "Outro")


def test_parametro_numerico_respeita_a_faixa_e_recusa_bool():
    achado = _primeiro_parametro(ESTRATEGIAS, com_opcoes=False)
    assert achado is not None
    nome, p = achado
    chave = f"parametro_{nome}_{p.nome}"
    assert _campo_ainda_vale(chave, p.minimo)
    assert _campo_ainda_vale(chave, p.maximo)
    assert not _campo_ainda_vale(chave, p.maximo + 1)
    assert not _campo_ainda_vale(chave, p.minimo - 1)
    assert not _campo_ainda_vale(chave, "5")
    assert not _campo_ainda_vale(
        chave, True
    )  # bool é int no Python, mas não é número aqui


def test_parametro_de_carteira_usa_o_prefixo_proprio():
    achado = _primeiro_parametro(ESTRATEGIAS_DE_CARTEIRA, com_opcoes=False)
    if achado is None:
        pytest.skip("nenhuma carteira com parâmetro numérico")
    nome, p = achado
    chave = f"carteira_{nome}_{p.nome}"
    assert _campo_ainda_vale(chave, p.minimo)
    assert not _campo_ainda_vale(chave, p.maximo + 1)


def test_parametro_com_opcoes_so_aceita_as_opcoes():
    achado = _primeiro_parametro(ESTRATEGIAS, com_opcoes=True)
    if achado is None:
        pytest.skip("nenhuma estratégia com parâmetro de escolha")
    nome, p = achado
    chave = f"parametro_{nome}_{p.nome}"
    assert _campo_ainda_vale(chave, p.opcoes[0])
    assert not _campo_ainda_vale(chave, "opção que não existe")


def test_parametro_desconhecido_nao_volta_mas_chave_comum_volta():
    assert not _campo_ainda_vale("parametro_Extinta_janela", 10)
    assert _campo_ainda_vale("backtest_capital", 5000.0)
