"""Pré-lançamento (emenda à ADR 0029): toda conta usa o Pro, e a tabela continua mostrando os planos."""

import pytest

from src import planos
from src.banco.modelo import PLANOS
from src.paginas import motivo_da_pagina


@pytest.fixture
def tudo_liberado(monkeypatch):
    monkeypatch.setattr(planos, "TUDO_LIBERADO_NO_PRE_LANCAMENTO", True)


@pytest.mark.usefixtures("tudo_liberado")
@pytest.mark.parametrize("plano", [*PLANOS, None, "", "desconhecido"])
def test_toda_conta_usa_os_limites_do_pro(plano):
    assert planos.limites_do(plano) is planos.LIMITES_DOS_PLANOS["pro"]
    for recurso in planos.NOMES_DOS_RECURSOS:
        assert planos.motivo_sem_acesso(plano, recurso) is None


@pytest.mark.usefixtures("tudo_liberado")
def test_o_gratuito_passa_das_travas_de_antes():
    planos.conferir_simulacoes("gratuito", ja_salvas=500)
    planos.conferir_relatorio("gratuito", "carteira", gerados_em_24h=500)
    assert motivo_da_pagina("gratuito", "pares") is None


@pytest.mark.usefixtures("tudo_liberado")
def test_a_tabela_mostra_o_que_cada_plano_vai_incluir():
    simulacoes = planos.tabela_de_planos()[0]
    assert simulacoes["Recurso"] == "Simulações salvas"
    assert (simulacoes["Gratuito"], simulacoes["Pro"]) == ("5", "Ilimitadas")


@pytest.mark.usefixtures("tudo_liberado")
def test_a_pagina_de_planos_avisa_do_pre_lancamento():
    aviso = planos.aviso_da_pagina_de_planos()
    assert aviso.startswith(planos.AVISO_DO_PRE_LANCAMENTO)
    assert planos.AVISO_DO_MODO_DE_TESTE in aviso


def test_depois_do_lancamento_volta_cada_plano_com_o_seu_limite():
    # o conftest desliga o pré-lançamento em todos os testes
    assert planos.limites_do("gratuito").simulacoes == 5
    assert planos.aviso_da_pagina_de_planos() == planos.AVISO_DO_MODO_DE_TESTE
