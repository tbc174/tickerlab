"""A entrada em empresa baixada diz quando e por que a empresa baixou (linha 1042, campos da baixa).

Sem isto a prova mostra uma empresa "do setor" que a Receita já baixou, sem dizer que é uma baixada. Os três campos
(`situacao_da_empresa`, `baixada_em`, `motivo_da_baixa`) saem da versão mais nova já pública da situação cadastral, com fonte e
data como a razão social. Riscos: olhar o futuro (versão ainda não pública), dar o campo a empresa ativa, quebrar a
lista quando a base não tem o histórico e confundir a data de uma filial com a da empresa.
"""
# ruff: noqa: F811  (a fixture `pasta` vem do arquivo do buyers e se repete nos argumentos)

from datetime import date

import pandas as pd
import pytest

from base.porta import Porta
from src.api_externa.conjuntos import compradores
from tests.test_api_externa_compradores import (
    ALVO_SP,
    BAIXADA,
    CARIMBOS,
    COMPRADORA,
    NOMES,
    SETOR,
    _gravar,
    pasta,  # noqa: F401  (fixture reaproveitada)
)

HOJE = date(2026, 11, 10)
TABELA = "cnpj_situacao_cadastral"
COLUNAS = [
    "cnpj",
    "situacao_cadastral",
    "data_situacao_cadastral",
    "motivo_situacao",
    "mes_do_retrato",
    "disponivel_em",
]
# fmt: off
VERSOES = [
    # estabelecimento, situação, desde, motivo, mês do retrato, disponível em
    (BAIXADA + "000100", "08", "2025-08-15", "01", "2025-09", "2025-09-21"),
    (BAIXADA + "000200", "08", "2025-11-30", "02", "2025-12", "2025-12-21"),  # a filial que baixou por último
    (BAIXADA + "000300", "08", "2024-01-10", "01", "2024-02", "2024-02-21"),
    (ALVO_SP + "000100", "02", "2010-01-01", "00", "2026-09", "2026-09-21"),
    # a versão de novembro ainda não era pública em 10/11: a baixa de outra data não pode valer
    (BAIXADA + "000200", "08", "2026-11-05", "09", "2026-11", "2026-11-21"),
]
# fmt: on


@pytest.fixture(autouse=True)
def _cache_limpo():
    compradores.zerar_o_cache()
    yield
    compradores.zerar_o_cache()


def _gravar_a_situacao(pasta, versoes=VERSOES) -> None:
    tabela = pd.DataFrame(list(versoes), columns=COLUNAS)
    tabela["cnpj_basico"] = tabela["cnpj"].str[:8]
    tabela["matriz"] = True
    tabela["consta"] = True
    tabela["data_situacao_cadastral"] = pd.to_datetime(
        tabela["data_situacao_cadastral"]
    ).dt.date
    tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"]).dt.date
    tabela["origem_coletada_em"] = CARIMBOS["montado_em"]
    _gravar(pasta / TABELA / "parte.parquet", tabela.assign(**CARIMBOS))


def _exemplos(pasta, cnae=SETOR):
    leitor = compradores.LeitorDeCompradores(Porta(pasta), lambda *_: True, 50)
    servido = leitor.compradores(
        compradores.PedidoDeCompradores(cnae, None, 3, 50), HOJE
    )
    assert servido is not None
    (comprador,) = [
        c for c in servido.corpo["compradores"] if c["raiz_do_cnpj"] == COMPRADORA
    ]
    return {
        e["empresa_do_setor"]["raiz_do_cnpj"]: e["empresa_do_setor"]
        for e in comprador["provas"][compradores.ENTROU]["exemplos"]
    }


def test_a_empresa_baixada_diz_a_situacao_a_data_e_o_motivo(pasta):
    _gravar_a_situacao(pasta)
    baixada = _exemplos(pasta)[BAIXADA]
    assert baixada["situacao_da_empresa"]["valor"] == "baixada"
    # a baixa da empresa é a da última filial a baixar entre as públicas no dia: 30/11/2025, motivo 02
    assert baixada["baixada_em"]["valor"] == "2025-11-30"
    assert baixada["motivo_da_baixa"]["valor"] == "02"
    assert baixada["razao_social"]["valor"] == NOMES[BAIXADA]


def test_os_campos_da_baixa_trazem_fonte_e_dia_em_que_ficaram_publicos(pasta):
    _gravar_a_situacao(pasta)
    baixada = _exemplos(pasta)[BAIXADA]
    for nome in ("situacao_da_empresa", "baixada_em", "motivo_da_baixa"):
        assert baixada[nome]["fonte"] == compradores.RECEITA
        assert baixada[nome]["publico_em"] == "2025-12-31"  # o mês vale pelo último dia


def test_versao_ainda_nao_publica_no_dia_nao_vale(pasta):
    _gravar_a_situacao(pasta)
    baixada = _exemplos(pasta)[BAIXADA]
    assert baixada["baixada_em"]["valor"] != "2026-11-05"
    assert baixada["motivo_da_baixa"]["valor"] != "09"


def test_empresa_ativa_nao_ganha_os_campos(pasta):
    _gravar_a_situacao(pasta)
    ativa = _exemplos(pasta)[ALVO_SP]
    assert set(ativa) == {"raiz_do_cnpj", "razao_social"}


def test_sem_o_historico_na_base_a_lista_sai_sem_os_campos(pasta):
    baixada = _exemplos(pasta)[BAIXADA]
    assert set(baixada) == {"raiz_do_cnpj", "razao_social"}


def test_baixada_sem_linha_no_historico_sai_sem_os_campos(pasta):
    _gravar_a_situacao(pasta, [v for v in VERSOES if v[0].startswith(ALVO_SP)])
    baixada = _exemplos(pasta)[BAIXADA]
    assert set(baixada) == {"raiz_do_cnpj", "razao_social"}


def test_o_campo_nao_leva_o_motivo_traduzido(pasta):
    """O código vai como a Receita publica: a tradução (incorporação, por exemplo) não foi conferida em fonte real."""
    _gravar_a_situacao(pasta)
    assert _exemplos(pasta)[BAIXADA]["motivo_da_baixa"]["valor"].isdigit()


def test_sem_a_liberacao_do_portao_os_campos_nao_saem_e_a_lista_segue(pasta):
    """Organização sem a linha da situação cadastral no `buyers`: a empresa baixada sai como antes, sem os três campos."""
    _gravar_a_situacao(pasta)

    def sem_o_motivo(_fonte, nome, _padrao):
        return nome != "motivo_situacao"

    leitor = compradores.LeitorDeCompradores(Porta(pasta), sem_o_motivo, 50)
    servido = leitor.compradores(
        compradores.PedidoDeCompradores(SETOR, None, 3, 50), HOJE
    )
    assert servido is not None
    (comprador,) = [
        c for c in servido.corpo["compradores"] if c["raiz_do_cnpj"] == COMPRADORA
    ]
    alvos = {
        e["empresa_do_setor"]["raiz_do_cnpj"]: e["empresa_do_setor"]
        for e in comprador["provas"][compradores.ENTROU]["exemplos"]
    }
    assert set(alvos[BAIXADA]) == {"raiz_do_cnpj", "razao_social"}
