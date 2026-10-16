"""Conferência de cada Parquet da base contra o contrato (ADR 0077 e 0078): tipo de cada coluna,
nulos, faixas, chave sem duplicata e as três datas em ordem. As regras saem do dicionário; um Parquet
quebrado de propósito precisa reprovar em cada uma delas."""

import json
from datetime import date

import pandas as pd
import pytest

from base.conferencia import (
    REGRA_POR_UNIDADE,
    conferir,
    tabela_do_destino,
)
from base.dicionario import TABELAS
from base.parquet import gravar_tabela
from src import versao_do_codigo as vc

HOJE = date(2026, 10, 16)
VERSAO = "587cb6c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7"


def _eventos(linhas: int = 3) -> pd.DataFrame:
    """Uma tabela `eventos` certa, com as colunas do dicionário e os tipos do Parquet do servidor."""
    return pd.DataFrame(
        {
            "protocolo": [f"P{i}" for i in range(linhas)],
            "versao": [1] * linhas,
            "cnpj": ["33.000.167/0001-01"] * linhas,
            "empresa": ["Petrobras"] * linhas,
            "categoria": ["Fato Relevante"] * linhas,
            "tipo": [None] * linhas,
            "assunto": ["Assunto"] * linhas,
            "rotulo": ["fato relevante"] * linhas,
            "tema": ["eventos"] * linhas,
            "materialidade": [80] * linhas,
            "referencia": [date(2024, 3, 1)] * linhas,
            "publicado_em": [date(2024, 3, 2)] * linhas,
            "link": ["https://www.rad.cvm.gov.br/x"] * linhas,
            "ano_do_arquivo": [2024] * linhas,
            "origem_sha256": ["ab" * 32] * linhas,
            "origem_coletada_em": ["2026-10-14T03:00:00+00:00"] * linhas,
            "montado_em": ["2026-10-15T22:30:00+00:00"] * linhas,
            "versao_do_codigo": [VERSAO] * linhas,
        }
    )


def _problemas(tabela: pd.DataFrame, nome: str = "eventos") -> list[str]:
    return conferir(tabela, nome, hoje=HOJE).problemas


def test_tabela_certa_passa():
    resultado = conferir(_eventos(), "eventos", hoje=HOJE)
    assert resultado.problemas == []
    assert resultado.aprovada
    assert resultado.regras > 0


def test_toda_unidade_do_dicionario_tem_regra():
    unidades = {u for t in TABELAS.values() for (_, u) in t.colunas.values()}
    assert unidades - set(REGRA_POR_UNIDADE) == set()


def test_faixas_e_nao_nulas_do_dicionario_existem_na_tabela():
    for nome, tabela in TABELAS.items():
        for coluna in [*tabela.faixas, *tabela.nao_nulas]:
            assert coluna in tabela.colunas, f"{nome}: `{coluna}` não está nas colunas"


def test_tipo_errado_reprova():
    tabela = _eventos()
    tabela["materialidade"] = ["alta", "baixa", "alta"]
    tabela["publicado_em"] = ["ontem", "2024-03-02", None]
    problemas = _problemas(tabela)
    assert any(p.startswith("materialidade: tipo") for p in problemas)
    assert any(p.startswith("publicado_em: 1 valor que não é data") for p in problemas)


def test_inteiro_guardado_como_decimal_por_causa_de_vazio_passa():
    tabela = _eventos()
    tabela["versao"] = [1.0, 2.0, None]
    tabela["protocolo"] = ["P0", "P1", "P2"]
    assert not any(p.startswith("versao: tipo") for p in _problemas(tabela))


def test_decimal_em_coluna_de_inteiro_reprova():
    tabela = _eventos()
    tabela["ano_do_arquivo"] = [2024.5, 2024.0, 2024.0]
    assert any(p.startswith("ano_do_arquivo: tipo") for p in _problemas(tabela))


def test_nulo_na_chave_reprova():
    tabela = _eventos()
    tabela.loc[1, "protocolo"] = None
    assert "protocolo: 1 vazio (a coluna não aceita vazio)" in _problemas(tabela)


def test_chave_duplicada_reprova():
    tabela = _eventos()
    tabela.loc[2, "protocolo"] = "P0"
    assert "chave duplicada: 1 linha (protocolo, versao)" in _problemas(tabela)


def test_fora_da_faixa_reprova():
    tabela = _eventos()
    tabela.loc[0, "materialidade"] = 150
    assert "materialidade: 1 valor fora de 0 a 100" in _problemas(tabela)


def _curva() -> pd.DataFrame:
    """Uma tabela `curva_juros` certa (nela o fato nunca vem depois de ficar público)."""
    return pd.DataFrame(
        {
            "data_base": pd.to_datetime(["2024-01-02"]),
            "curva": ["nominal"],
            "prazo_anos": [0.5],
            "taxa": [0.11],
            "titulos": [12],
            "maior_prazo_anos": [20.0],
            "disponivel_em": pd.to_datetime(["2024-01-03"]),
            "origem_sha256": ["ab" * 32],
            "origem_coletada_em": ["2026-10-14T03:00:00+00:00"],
            "montado_em": ["2026-10-15T22:30:00+00:00"],
            "versao_do_codigo": [VERSAO],
        }
    )


def test_faixa_escrita_no_dicionario_reprova():
    tabela = _curva()
    tabela.loc[0, "prazo_anos"] = -0.5
    assert "prazo_anos: 1 valor fora de 0 a ∞" in _problemas(tabela, "curva_juros")


def test_datas_fora_de_ordem_reprovam():
    curva = _curva()
    curva.loc[0, "data_base"] = pd.Timestamp(
        "2024-01-05"
    )  # aconteceu depois de ficar público
    assert (
        "datas: 1 linha com aconteceu_em (data_base) depois de publico_em (disponivel_em)"
        in _problemas(curva, "curva_juros")
    )
    eventos = _eventos()
    eventos.loc[1, "publicado_em"] = date(
        2026, 10, 20
    )  # público depois de coletado, e no futuro
    problemas = _problemas(eventos)
    assert (
        "datas: 1 linha com publico_em (publicado_em) depois de coletado_em (origem_coletada_em)"
        in problemas
    )
    assert "publicado_em: 1 data depois de hoje" in problemas


def test_fato_anunciado_antes_de_acontecer_passa_onde_o_dicionario_permite():
    # uma assembleia é publicada antes de acontecer: em `eventos`, aconteceu_em pode vir depois
    tabela = _eventos()
    tabela.loc[0, "referencia"] = date(2024, 4, 30)
    assert TABELAS["eventos"].anuncia_o_futuro
    assert _problemas(tabela) == []


def test_data_antes_de_1900_reprova():
    tabela = _eventos()
    tabela.loc[0, "referencia"] = date(1024, 3, 1)
    assert "referencia: 1 data antes de 1900" in _problemas(tabela)


def test_colunas_que_faltam_e_que_sobram_reprovam():
    tabela = _eventos().drop(columns=["link"]).assign(extra=1)
    problemas = _problemas(tabela)
    assert "colunas que faltam: link" in problemas
    assert "colunas fora do contrato: extra" in problemas


def test_tabela_vazia_passa():
    assert _problemas(_eventos().iloc[0:0]) == []


@pytest.mark.parametrize(
    ("caminho", "esperado"),
    [
        ("/mnt/acervo/base/eventos/2024", "eventos"),
        ("/mnt/acervo/base/amostra/v1/painel/2020", "amostra_painel"),
        ("/mnt/acervo/base/curva_juros/2010", "curva_juros"),
        ("/mnt/acervo/base/pasta_sem_contrato/2010", None),
        ("/tmp/eventos/2024", None),  # fora de uma pasta `base`
    ],
)
def test_tabela_do_destino(caminho, esperado):
    from pathlib import PurePosixPath

    assert tabela_do_destino(PurePosixPath(caminho)) == esperado


def test_montagem_grava_a_conferencia_no_manifesto_sem_bloquear(tmp_path, monkeypatch):
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    quebrada = _eventos()
    quebrada.loc[0, "materialidade"] = 150
    destino = tmp_path / "base" / "eventos" / "2024"

    arquivo = gravar_tabela(quebrada, destino, [], ["protocolo", "versao"])

    assert arquivo.exists()  # aviso: a montagem não para
    manifesto = json.loads(destino.with_suffix(".json").read_text(encoding="utf-8"))
    conferencia = manifesto["conferencia_do_contrato"]
    assert conferencia["tabela"] == "eventos"
    assert conferencia["versao_do_contrato"] == TABELAS["eventos"].versao_do_contrato
    assert conferencia["aprovada"] is False
    assert "materialidade: 1 valor fora de 0 a 100" in conferencia["problemas"]


def test_tabela_sem_contrato_nao_leva_conferencia(tmp_path, monkeypatch):
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    destino = tmp_path / "qualquer" / "2024"
    gravar_tabela(_eventos(), destino, [], ["protocolo"])
    manifesto = json.loads(destino.with_suffix(".json").read_text(encoding="utf-8"))
    assert "conferencia_do_contrato" not in manifesto


def test_conferencia_que_falha_nao_para_a_montagem(tmp_path, monkeypatch):
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)

    def quebrada(*_args, **_kwargs):
        raise RuntimeError("defeito no conferidor")

    monkeypatch.setattr("base.conferencia.conferir", quebrada)
    destino = tmp_path / "base" / "eventos" / "2024"
    assert gravar_tabela(_eventos(), destino, [], ["protocolo"]).exists()
    manifesto = json.loads(destino.with_suffix(".json").read_text(encoding="utf-8"))
    assert manifesto["conferencia_do_contrato"] == {
        "tabela": "eventos",
        "aprovada": False,
        "erro": "RuntimeError: defeito no conferidor",
    }
