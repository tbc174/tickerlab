"""Negócios e eventos na ficha: o M&A das assessorias (séries 5 da base) ao lado dos documentos da CVM.

Tabelas de mentira, pequenas. Só agregados (nenhuma outra parte, nenhum valor, nenhuma pessoa) e cada
número com a data em que o negócio ficou conhecido, sem olhar o futuro.
"""

import json

import pandas as pd

from base import dossie
from src import dossie as dossie_do_app

RAIZ = "02429144"
HOJE = "2026-10-17"


def _partes() -> pd.DataFrame:
    linhas = [
        # (url, papel, raiz, ligação)
        ("a", "comprador", RAIZ, "nome_exato"),
        ("b", "vendedor", RAIZ, "nome_exato"),
        ("c", "alvo", RAIZ, "nome_fantasia"),
        ("d", "alvo", RAIZ, "na_duvida"),  # nome em dúvida: fora
        ("e", "comprador", "99999999", "nome_exato"),  # outra empresa
        ("f", "alvo", RAIZ, "nome_exato"),  # a mesma venda que "c", noutro site
        ("g", "alvo", RAIZ, "nome_exato"),  # fusão: a alvo não foi "comprada"
        ("h", "alvo", RAIZ, "nome_exato"),  # só vira conhecido depois de hoje
    ]
    return pd.DataFrame(
        [
            {
                "assessoria": "igc",
                "url": u,
                "papel": p,
                "cnpj_raiz": r,
                "ligacao_por": lig,
            }
            for u, p, r, lig in linhas
        ]
    )


def _negocios() -> pd.DataFrame:
    ids = {
        "a": "N1",
        "b": "N2",
        "c": "N3",
        "d": "N4",
        "e": "N5",
        "f": "N3",
        "g": "N6",
        "h": "N7",
    }
    return pd.DataFrame(
        [{"assessoria": "igc", "url": u, "id_negocio": i} for u, i in ids.items()]
    )


def _datas() -> pd.DataFrame:
    dias = {
        "a": "2024-03-01", "b": "2025-06-10", "c": "2025-08-01", "d": "2025-09-01",
        "e": "2025-09-02", "f": "2025-08-05", "g": "2026-01-15", "h": "2026-12-01",
    }  # fmt: skip
    return pd.DataFrame(
        [
            {
                "assessoria": "igc",
                "url": u,
                "conhecido_em_do_negocio": pd.Timestamp(d),
                "confirmado_por": "cade" if u == "b" else None,
            }
            for u, d in dias.items()
        ]
    )


def _assessorias() -> pd.DataFrame:
    tipos = {
        "a": "AQ_CONTROLE", "b": "VENDA_ATIVO", "c": "AQ_MINORITARIA", "d": "AQ_CONTROLE",
        "e": "AQ_CONTROLE", "f": "AQ_MINORITARIA", "g": "FUSAO", "h": "AQ_CONTROLE",
    }  # fmt: skip
    return pd.DataFrame(
        [{"assessoria": "igc", "url": u, "tipo": t} for u, t in tipos.items()]
    )


def _por_empresa(
    hoje: str = HOJE, *, datas: pd.DataFrame | None = None
) -> dict[str, pd.DataFrame]:
    return dossie.negocios_de_ma_por_empresa(
        _partes(),
        _negocios(),
        _datas() if datas is None else datas,
        _assessorias(),
        hoje,
    )


def _itens(secao: dict) -> dict[str, dict]:
    return {item["chave"]: item for item in secao["itens"]}


def test_conta_o_papel_da_empresa_em_cada_negocio_uma_vez():
    ma = _por_empresa()[RAIZ]
    assert dict(ma["papel"].value_counts()) == {
        "comprou": 1,
        "vendeu": 1,
        "foi_comprada": 1,  # N3, contado uma vez mesmo em dois sites
        "outro": 1,  # a fusão
    }


def test_nome_em_duvida_e_outra_empresa_ficam_fora():
    por_empresa = _por_empresa()
    assert "N4" not in set(por_empresa[RAIZ]["id_negocio"])
    assert "N5" not in set(por_empresa[RAIZ]["id_negocio"])
    assert set(por_empresa) == {RAIZ, "99999999"}


def test_sem_olhar_o_futuro_cortar_o_futuro_nao_muda_o_passado():
    completo = _por_empresa(HOJE)[RAIZ]
    cortada = _datas()
    cortada = cortada[
        pd.to_datetime(cortada["conhecido_em_do_negocio"]) <= pd.Timestamp(HOJE)
    ]
    sem_futuro = _por_empresa(HOJE, datas=cortada)[RAIZ]
    pd.testing.assert_frame_equal(
        completo.reset_index(drop=True), sem_futuro.reset_index(drop=True)
    )
    assert "N7" not in set(completo["id_negocio"])
    # um dia depois da prova, o negócio entra
    assert "N7" in set(_por_empresa("2026-12-01")[RAIZ]["id_negocio"])


def test_secao_traz_os_tres_numeros_com_data_e_a_fonte():
    secao = dossie.secao_negocios(pd.DataFrame(), _por_empresa()[RAIZ])
    assert secao is not None
    assert secao["titulo"] == "Negócios e eventos"
    itens = _itens(secao)
    assert {
        k: itens[k]["valor"] for k in ("ma_comprou", "ma_vendeu", "ma_foi_comprada")
    } == {
        "ma_comprou": 1,
        "ma_vendeu": 1,
        "ma_foi_comprada": 1,
    }
    rastro = itens["ma_comprou"]["rastro"]
    assert rastro["fonte_id"] == "assessoria"
    assert rastro["publicado_em"] == "2026-01-15"  # o negócio mais novo já conhecido
    assert (
        "Cobre as assessorias" in secao["paragrafos"][-1]
    )  # os limites vão com a seção


def test_secao_so_com_agregados_sem_a_outra_parte_nem_valor():
    secao = dossie.secao_negocios(pd.DataFrame(), _por_empresa()[RAIZ])
    assert secao is not None
    colunas = {c for t in secao["tabelas"].values() for linha in t for c in linha}
    assert colunas <= {
        "ano", "comprou", "vendeu", "foi_comprada", "outro",
        "conhecido_em", "papel", "tipo", "confirmado",
    }  # fmt: skip
    dossie.conferir_sem_pessoas({"secoes": [secao]}, set())


def test_sem_negocios_de_ma_a_secao_da_cvm_fica_como_era():
    eventos = pd.DataFrame(
        [
            {
                "publicado_em": pd.Timestamp("2026-05-01").date(),
                "rotulo": "Fato relevante",
                "assunto": "Aquisição de controle da Beta",
                "link": "x",
            }
        ]
    )
    secao = dossie.secao_negocios(eventos, pd.DataFrame())
    assert secao is not None
    assert [i["chave"] for i in secao["itens"]] == ["negocios"]
    assert dossie.secao_negocios(pd.DataFrame(), pd.DataFrame()) is None
    assert dossie.secao_negocios(pd.DataFrame(), None) is None


def test_tabela_ausente_nao_quebra():
    vazia = pd.DataFrame()
    assert dossie.negocios_de_ma_por_empresa(vazia, vazia, vazia, vazia, HOJE) == {}


def test_o_app_escreve_papel_e_tipo_em_portugues():
    assert (
        dossie_do_app._papel_no_ma("foi_comprada")
        == "Foi comprada ou recebeu investimento"
    )
    assert dossie_do_app._tipo_de_ma("AQ_CONTROLE") == "Compra de controle"
    assert dossie_do_app._tipo_de_ma("desconhecido") == "Tipo não identificado"


def test_a_secao_chega_ao_app_com_titulo_data_fonte_e_sem_comparacao(tmp_path):
    secao = dossie.secao_negocios(pd.DataFrame(), _por_empresa()[RAIZ])
    ficha = dossie.montar_ficha(
        "02429144000193", "Empresa", [secao], "2026-10-17T03:00:00-03:00"
    )
    caminho = tmp_path / "02429144000193.json"
    caminho.write_text(json.dumps(ficha), encoding="utf-8")
    lida = dossie_do_app.ler_ficha(caminho)
    assert lida is not None
    (do_app,) = dossie_do_app.secoes_da_ficha(dossie_do_app.cortar(lida))
    assert do_app.titulo == "Negócios e eventos"
    assert set(do_app.tabelas) == {"ma_por_ano", "ma_recentes"}
    for tabela in do_app.tabelas:
        assert tabela in dossie_do_app.TITULOS_DAS_TABELAS
    for item in do_app.itens:
        assert item.numero.o_que_falta() == [], item.chave
        assert item.fonte in dossie_do_app.FONTES_DOS_ITENS.values()
    recentes = do_app.tabelas["ma_recentes"]
    assert {linha["Papel da empresa"] for linha in recentes} >= {"Vendeu"}
