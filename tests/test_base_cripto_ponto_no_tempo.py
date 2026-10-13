""" "Como era na data", reprodutibilidade e dicionário da base de cripto (série 1, PR 5).

Usa as amostras dos testes de cada leitor, para conferir as tabelas como elas saem de verdade.
"""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base.cripto.atencao import juntar_gdelt, ler_gdelt, ler_wikipedia
from base.cripto.cftc import ler_tff
from base.cripto.diario import resumo_diario
from base.cripto.dicionario import DICIONARIO, colunas_sem_descricao, em_texto
from base.cripto.leitura import ler_ate_o_topo, ler_blocos, ler_parado
from base.cripto.ponto_no_tempo import como_era_em, hash_do_conteudo
from base.cripto.precos import ler_kraken_rest, ler_mercado_bitcoin
from base.cripto.receita import ler_por_criptoativo, ler_totais
from tests.test_base_cripto_atencao import TOM, VOLUME, WIKIPEDIA
from tests.test_base_cripto_cftc import _zip_da_amostra
from tests.test_base_cripto_leitura import NoFalso, _cadeia
from tests.test_base_cripto_precos import KRAKEN_REST, MERCADO_BITCOIN
from tests.test_base_cripto_receita import PUBLICADO, _relatorio_1, _relatorio_4

AGORA = datetime(2026, 10, 13, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def tabelas(tmp_path_factory) -> dict[str, pd.DataFrame]:
    """Cada tabela da base, como os leitores a devolvem."""
    pasta = tmp_path_factory.mktemp("no")
    ler_ate_o_topo(NoFalso(_cadeia(30)), pasta, AGORA, blocos_por_ponto=7)
    return {
        "blocos": ler_blocos(pasta),
        "rede_diaria": resumo_diario(ler_blocos(pasta), ler_parado(pasta)),
        "precos": pd.concat(
            [
                ler_mercado_bitcoin(MERCADO_BITCOIN, AGORA),
                ler_kraken_rest(KRAKEN_REST, AGORA),
            ]
        ),
        "cftc": ler_tff(_zip_da_amostra()),
        "wikipedia": ler_wikipedia(WIKIPEDIA),
        "gdelt": juntar_gdelt(ler_gdelt(VOLUME), ler_gdelt(TOM)),
        "receita_totais": ler_totais(_relatorio_1(), PUBLICADO),
        "receita_criptoativo": ler_por_criptoativo(_relatorio_4(), PUBLICADO, "BTC"),
    }


def test_toda_tabela_esta_no_dicionario(tabelas):
    assert set(tabelas) == set(DICIONARIO)


@pytest.mark.parametrize("nome", list(DICIONARIO))
def test_toda_coluna_esta_descrita(tabelas, nome):
    assert colunas_sem_descricao(nome, tabelas[nome]) == []


@pytest.mark.parametrize("nome", [n for n in DICIONARIO if n != "blocos"])
def test_base_em_31_12_2020_nao_acha_nada_divulgado_depois(tabelas, nome):
    # a tabela de blocos não tem divulgado_em: o dia passa a valer no resumo diário
    corte = datetime(2020, 12, 31, 23, 59, 59, tzinfo=UTC)

    na_data = como_era_em(tabelas[nome], corte)

    assert (na_data["divulgado_em"] <= pd.Timestamp(corte)).all()
    assert pd.api.types.is_datetime64_any_dtype(tabelas[nome]["divulgado_em"])
    assert str(tabelas[nome]["divulgado_em"].dt.tz) == "UTC"


def test_versao_mais_nova_ate_a_data():
    receita = pd.DataFrame(
        {
            "mes": [date(2026, 1, 1), date(2026, 1, 1)],
            "total_milhoes": [100.0, 120.0],  # a Receita refez janeiro
            "divulgado_em": pd.to_datetime(["2026-04-01", "2026-06-01"], utc=True),
        }
    )

    em_maio = como_era_em(receita, datetime(2026, 5, 1, tzinfo=UTC), chave=["mes"])
    em_julho = como_era_em(receita, datetime(2026, 7, 1, tzinfo=UTC), chave=["mes"])

    assert em_maio["total_milhoes"].tolist() == [100.0]
    assert em_julho["total_milhoes"].tolist() == [120.0]


def test_refazer_a_leitura_da_o_mesmo_hash(tmp_path):
    em_partes, de_uma_vez = tmp_path / "partes", tmp_path / "uma"
    no = NoFalso(_cadeia(20))
    ler_ate_o_topo(no, em_partes, AGORA, blocos_por_ponto=4)
    no.blocos = _cadeia(40, base=no.blocos)
    ler_ate_o_topo(
        no, em_partes, datetime(2026, 10, 14, tzinfo=UTC), blocos_por_ponto=4
    )
    ler_ate_o_topo(NoFalso(_cadeia(40)), de_uma_vez, AGORA, blocos_por_ponto=100)

    for ler, chave in ((ler_blocos, ["altura"]), (ler_parado, ["dia"])):
        assert hash_do_conteudo(ler(em_partes), chave) == hash_do_conteudo(
            ler(de_uma_vez), chave
        )


def test_hash_muda_se_um_numero_muda():
    tabela = pd.DataFrame({"dia": [1, 2], "valor": [0.1, 0.2]})
    mudada = tabela.assign(valor=[0.1, 0.2000000001])

    assert hash_do_conteudo(tabela, ["dia"]) != hash_do_conteudo(mudada, ["dia"])


def test_dicionario_em_texto_tem_cada_tabela():
    texto = em_texto()

    for nome in DICIONARIO:
        assert f"## {nome}" in texto
