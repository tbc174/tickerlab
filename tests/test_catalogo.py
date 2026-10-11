"""O catálogo da busca: tem os ativos certos e nunca troca o ativo em silêncio."""

import pandas as pd

from src import catalogo


def test_tem_os_ativos_mais_buscados_com_nome_e_bolsa():
    for simbolo in ("PETR4.SA", "VALE3.SA", "BOVA11.SA", "AAPL", "^BVSP", "BTC-USD"):
        assert catalogo.esta_no_catalogo(simbolo), simbolo
    assert catalogo.rotulo("PETR4.SA").startswith(
        "PETR4 · "
    ) and "B3" in catalogo.rotulo("PETR4.SA")
    assert catalogo.rotulo("AAPL").endswith("EUA · Ação")


def test_sem_simbolos_repetidos_e_sem_campos_vazios():
    tabela = catalogo.carregar()
    assert tabela.index.is_unique
    assert not tabela[["codigo", "nome", "bolsa", "tipo"]].isna().any().any()


def test_codigo_digitado_vira_o_simbolo_do_catalogo():
    assert catalogo.resolver("vale3") == "VALE3.SA"  # sem saber do .SA
    assert catalogo.resolver(" PETR4 ") == "PETR4.SA"
    assert catalogo.resolver("usd/brl") == "BRL=X"
    assert catalogo.resolver("BRK-B") == "BRK-B"


def test_o_que_foi_escolhido_na_lista_vale_como_esta():
    assert (
        catalogo.resolver("AAPL34.SA") == "AAPL34.SA"
    )  # o BDR não vira a ação americana
    assert catalogo.resolver("AAPL") == "AAPL"  # e a ação americana não vira o BDR


def test_fora_do_catalogo_segue_a_regra_antiga_sem_inventar():
    assert catalogo.resolver("ABCD3") == "ABCD3.SA"  # formato da B3: só ganha o sufixo
    assert catalogo.resolver("XYZW") == "XYZW"  # não troca por um parecido
    assert catalogo.resolver("") is None


def test_ativo_atual_fora_do_catalogo_continua_nas_opcoes():
    assert catalogo.opcoes("ABCD3.SA")[0] == "ABCD3.SA"
    assert catalogo.rotulo("ABCD3.SA") == "ABCD3.SA · fora do catálogo"


def test_cabecalho_do_arquivo_diz_de_onde_veio():
    primeira = catalogo.ARQUIVO.read_text(encoding="utf-8").splitlines()[0]
    assert primeira.startswith("# catálogo de ativos") and "gerar_catalogo" in primeira
    assert isinstance(catalogo.carregar(), pd.DataFrame)


def test_busca_de_ativos_tem_lupa_no_lugar_da_seta():
    from src import estilo

    for campo in ("ticker", "ativo_do_inicio"):
        assert f'.st-key-{campo} [aria-label="Open"] svg' in estilo.CSS_DO_APP
    assert "%3Csvg" in estilo.CSS_DO_APP and "<svg" not in estilo.CSS_DO_APP
