"""Fonte, data e atribuição em cada campo da API externa (B-32a; cliente-norte, Emenda 2).

Quem integra precisa saber, campo a campo, de onde veio o número e desde quando ele era público.
"""

from datetime import UTC, date, datetime

import pytest

from src.api_externa import envelope
from src.api_externa.nomes import traduzir_chaves
from src.banco.coletas import SEM_LICENCA_CONHECIDA


def test_campo_tem_fonte_e_as_duas_datas():
    campo = envelope.campo(
        1.5,
        fonte="cvm-dfp",
        publico_em=date(2025, 3, 28),
        visto_em=datetime(2025, 3, 29, 6, 15, tzinfo=UTC),
    )
    assert traduzir_chaves(campo) == {
        "value": 1.5,
        "source": "cvm-dfp",
        "published_at": "2025-03-28",
        "observed_at": "2025-03-29T06:15:00+00:00",
    }


def test_campo_sem_visto_em_sai_com_nulo():
    campo = envelope.campo(
        "ATIVA", fonte="rfb-cnpj", publico_em=date(2026, 10, 12), visto_em=None
    )
    assert campo["visto_em"] is None


def test_campo_sem_data_de_publicacao_nao_sai():
    # sem o publico_em não há como cortar pelo known_at (D6): melhor não servir
    with pytest.raises(ValueError):
        envelope.campo(1, fonte="cvm", publico_em=None, visto_em=None)


@pytest.mark.parametrize("fonte", ["cvm", "cvm-dfp", "cvm-fundos", "rfb-cnpj"])
def test_toda_fonte_do_beta_tem_licenca_e_atribuicao(fonte):
    (linha,) = envelope.fontes_da_resposta([fonte])
    assert linha["fonte"] == fonte
    assert linha["licenca"] != SEM_LICENCA_CONHECIDA
    assert linha["atribuicao"].startswith("Fonte: ")


def test_fonte_sem_atribuicao_conhecida_nao_sai():
    with pytest.raises(ValueError):
        envelope.fontes_da_resposta(["fonte-que-nao-existe"])


def test_fontes_da_resposta_sem_repetir_e_em_ordem():
    linhas = envelope.fontes_da_resposta(["rfb-cnpj", "cvm-dfp", "rfb-cnpj"])
    assert [linha["fonte"] for linha in linhas] == ["cvm-dfp", "rfb-cnpj"]
