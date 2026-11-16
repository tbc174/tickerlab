"""O free float na seção de governança do dossiê (linha 403 da fila): o percentual de ações em
circulação que a companhia declara no item 15.7 do FRE, com a data de entrega, sem olhar o futuro e
sem afirmar o que o preenchimento não sustenta (zero e mais de 100% ficam de fora)."""

import pandas as pd

from base import dossie

D = pd.Timestamp
HOJE = D("2026-10-17")
CNPJ = "02.429.144/0001-93"
FRE_2025 = ("2025-01-01", 1, "2025-05-31")
FRE_2026_V1 = ("2026-01-01", 1, "2026-05-29")
FRE_2026_V2 = ("2026-01-01", 2, "2026-07-10")
FRE_2027 = ("2027-01-01", 1, "2026-11-30")


def _linha(fre: tuple[str, int, str], percentual: float, **extra: object) -> dict:
    referencia, versao, entregue_em = fre
    return {
        "cnpj": CNPJ,
        "referencia": D(referencia),
        "versao": versao,
        "conhecido_em": D(entregue_em),
        "acionistas_pf": 1_000,
        "acionistas_pj": 50,
        "acionistas_institucionais": 20,
        "circulacao_total": 3_000_000.0,
        "percentual_total": percentual,
        "ultima_assembleia_em": D("2026-04-25"),
        **extra,
    }


def _governanca(distribuicao: pd.DataFrame | None, hoje: pd.Timestamp = HOJE):
    vazia = pd.DataFrame()
    return dossie.secao_governanca(
        vazia, vazia, vazia, vazia, vazia, hoje, None, None, distribuicao
    )


def _free_float(secao: dict | None) -> dict:
    assert secao is not None
    return next(i for i in secao["itens"] if i["chave"] == "free_float")


def test_free_float_e_o_percentual_do_fre_mais_novo_ja_entregue_como_fracao() -> None:
    distribuicao = pd.DataFrame(
        [
            _linha(FRE_2025, 30.0),
            _linha(FRE_2026_V1, 35.0),
            _linha(FRE_2026_V2, 38.8),
            _linha(FRE_2027, 90.0),  # só é entregue depois de hoje
        ]
    )
    secao = _governanca(distribuicao)
    item = _free_float(secao)
    assert item["valor"] == 0.388  # a versão 2 vale; a 1 foi reapresentada
    assert item["unidade"] == "fração"
    assert item["base"] == "2026-07-10"
    assert item["rastro"]["publicado_em"] == "2026-07-10"


def test_cortar_o_futuro_nao_muda_o_passado() -> None:
    distribuicao = pd.DataFrame([_linha(FRE_2025, 30.0), _linha(FRE_2026_V2, 38.8)])
    antes_da_entrega = _free_float(_governanca(distribuicao, D("2026-06-30")))
    so_o_passado = _free_float(_governanca(distribuicao.iloc[:1], D("2026-06-30")))
    assert antes_da_entrega == so_o_passado
    assert antes_da_entrega["valor"] == 0.30


def test_tabela_anual_traz_o_fre_anterior_para_comparar() -> None:
    distribuicao = pd.DataFrame([_linha(FRE_2025, 30.0), _linha(FRE_2026_V2, 38.8)])
    secao = _governanca(distribuicao)
    assert secao is not None
    tabela = secao["tabelas"]["free_float_por_ano"]
    assert [linha["ano"] for linha in tabela] == [2026, 2025]
    assert [linha["free_float"] for linha in tabela] == [0.388, 0.30]
    assert tabela[0]["acionistas_pf"] == 1_000
    assert tabela[0]["entregue_em"] == "2026-07-10"


def test_fre_mais_novo_sem_percentual_com_sentido_nao_recua_para_um_mais_velho() -> (
    None
):
    """O FRE atual diz 0% (ou mais de 100%): o item some, em vez de mostrar o número de anos atrás."""
    for sem_sentido in (0.0, 114.137):
        distribuicao = pd.DataFrame(
            [_linha(FRE_2025, 30.0), _linha(FRE_2026_V2, sem_sentido)]
        )
        secao = _governanca(distribuicao)
        assert secao is None  # sem o item, a seção de governança nem aparece
    zerado = pd.DataFrame([_linha(FRE_2026_V2, 0.0)])
    assert _governanca(zerado) is None


def test_fre_sem_percentual_com_sentido_fica_vazio_e_manda_no_item() -> None:
    distribuicao = pd.DataFrame([_linha(FRE_2025, 30.0), _linha(FRE_2026_V2, 0.0)])
    por_ano = dossie._free_float_por_ano(distribuicao)
    assert list(por_ano["ano"]) == [2026, 2025]  # o mais novo vem primeiro, mesmo vazio
    assert pd.isna(por_ano.loc[0, "free_float"])
    assert por_ano.loc[1, "free_float"] == 0.30
    assert dossie._item_do_free_float(por_ano) == []


def test_cem_por_cento_e_um_free_float_valido() -> None:
    """100% é possível (sem controlador, administradores nem tesouraria com ações): não é recuo."""
    distribuicao = pd.DataFrame([_linha(FRE_2025, 30.0), _linha(FRE_2026_V2, 100.0)])
    item = _free_float(_governanca(distribuicao))
    assert item["valor"] == 1.0
    assert item["base"] == "2026-07-10"


def test_percentual_minusculo_nao_arredonda_para_zero() -> None:
    distribuicao = pd.DataFrame([_linha(FRE_2026_V2, 0.000018)])
    item = _free_float(_governanca(distribuicao))
    assert item["valor"] == 0.00000018


def test_dois_documentos_na_mesma_versao_valem_o_entregue_por_ultimo() -> None:
    distribuicao = pd.DataFrame(
        [
            _linha(FRE_2026_V2, 38.8),
            _linha(("2026-01-01", 2, "2026-07-20"), 41.0),
        ]
    )
    assert _free_float(_governanca(distribuicao))["valor"] == 0.41


def test_sem_a_tabela_a_secao_nao_inventa_free_float() -> None:
    assert _governanca(None) is None
    assert _governanca(pd.DataFrame()) is None
