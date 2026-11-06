"""Benefícios fiscais de Pernambuco por CNPJ na base (SEFAZ-PE, linha 578 da fila; Ficha Clara, etapa 4b).

A quarta fonte de `base/incentivos.py`: um Parquet por ano da SEFAZ-PE (`beneficios_fiscais_2025_.csv`).
Só CNPJ inteiro de dígito certo; razão social nunca entra (a coleta já a tirou); toda linha vale desde o
dia do arquivo (`disponivel_em`), e o prazo do benefício (`termo_inicial`, `termo_final`) fica nas colunas
`vigencia_inicio` e `vigencia_fim`, que contam o que o benefício cobre, não quando a base soube.
Os arquivos guardados são os da coleta: ";" e UTF-8, datas "2010/08/04 00:00:00.000". Tudo de mentira.
"""

import json
from datetime import date

import pandas as pd
import pytest

from base import cnpj as cnpjs
from base import incentivos
from base.ancoragem import parquets_sem_manifesto
from base.arquivo import lote_sefaz_pe
from base.dicionario import TABELAS
from base.setoriais.revisoes import como_era_em
from tests.test_base_incentivos import (
    AGORA,
    EMPRESA,
    INVALIDO,
    OUTRA,
    PRIMEIRO_DIA,
    SEGUNDO_DIA,
    _coletar,
    _csv,
    _montar,
    _texto_gravado,
)

FONTE = "sefazpe-beneficios"
URL_2025 = (
    f"{lote_sefaz_pe.PORTAL}/dataset/x/resource/y/download/beneficios_fiscais_2025_.csv"
)
URL_2008 = (
    f"{lote_sefaz_pe.PORTAL}/dataset/x/resource/z/download/beneficios_fiscais_2008_.csv"
)
CPF = "12345678909"


def _beneficio(
    documento: str,
    programa: str = "PEAP",
    cacepe: str = "117135429",
    inicio: str = "2024/07/04 00:00:00.000",
    fim: str = "2025/07/03 00:00:00.000",
) -> dict[str, str]:
    return {
        "programa": programa,
        "cnpj": documento,
        "cacepe": cacepe,
        "termo_inicial": inicio,
        "termo_final": fim,
    }


def _tabela(tmp_path, arquivo: str = "beneficios-fiscais-2025") -> pd.DataFrame:
    return pd.read_parquet(
        tmp_path / "base" / "sefaz_pe_beneficios" / f"{arquivo}.parquet"
    )


def test_le_so_as_colunas_que_a_coleta_guarda():
    """A leitura não pode depender de coluna que o filtro da coleta tira (a razão social)."""
    assert set(incentivos._PE.values()) <= set(lote_sefaz_pe.COLUNAS_GUARDADAS)
    assert "empresa" not in incentivos._PE.values()


def test_so_cnpj_inteiro_com_a_vigencia_nas_colunas_proprias(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    linhas = [
        _beneficio(EMPRESA),
        _beneficio(OUTRA, "MAQUINAS PESADAS", "27695905", "2010/08/04 00:00:00.000"),
        _beneficio(CPF),
        _beneficio(INVALIDO),
        _beneficio(EMPRESA),  # repetida (mesma chave): fica a primeira
    ]
    _coletar(banco, FONTE, URL_2025, _csv(linhas, "utf-8"), PRIMEIRO_DIA)
    resumo = _montar(banco, tmp_path)
    assert resumo["beneficios-fiscais-2025"]["cnpj_invalido"] == 2
    assert resumo["beneficios-fiscais-2025"]["id_repetido"] == 1
    tabela = _tabela(tmp_path).set_index("cnpj")
    assert len(tabela) == 2
    linha = tabela.loc[cnpjs.formatar(EMPRESA)]
    assert linha["cnpj_basico"] == "11222333"
    assert linha["programa"] == "PEAP"
    assert linha["cacepe"] == "117135429"
    assert linha["vigencia_inicio"] == date(2024, 7, 4)
    assert linha["vigencia_fim"] == date(2025, 7, 3)
    assert linha["arquivo"] == "2025"
    assert linha["id_na_fonte"] == f"PEAP|{EMPRESA}|117135429|2024-07-04"
    antigo = tabela.loc[cnpjs.formatar(OUTRA)]
    # o benefício começou em 2010, mas a base só soube no dia do arquivo
    assert antigo["vigencia_inicio"] == date(2010, 8, 4)
    assert set(tabela["disponivel_em"]) == {PRIMEIRO_DIA}
    assert CPF not in _texto_gravado(tmp_path)


def test_data_ruim_vira_nula_sem_derrubar_a_carga(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    linhas = [_beneficio(EMPRESA, fim=""), _beneficio(OUTRA, inicio="31/02/2025")]
    _coletar(banco, FONTE, URL_2025, _csv(linhas, "utf-8"), PRIMEIRO_DIA)
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path).set_index("cnpj")
    assert pd.isna(tabela.loc[cnpjs.formatar(EMPRESA), "vigencia_fim"])
    assert pd.isna(tabela.loc[cnpjs.formatar(OUTRA), "vigencia_inicio"])


def test_cada_ano_e_um_arquivo_e_um_parquet(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _coletar(banco, FONTE, URL_2025, _csv([_beneficio(EMPRESA)], "utf-8"), PRIMEIRO_DIA)
    _coletar(
        banco, FONTE, URL_2008,
        _csv([_beneficio(EMPRESA, "PRODEPE", "23626003", "2001/06/01 00:00:00.000", "2008/12/31 00:00:00.000")], "utf-8"),
        PRIMEIRO_DIA,
    )  # fmt: skip
    resumo = _montar(banco, tmp_path)
    assert set(resumo) == {"beneficios-fiscais-2025", "beneficios-fiscais-2008"}
    assert _tabela(tmp_path, "beneficios-fiscais-2008")["programa"].tolist() == [
        "PRODEPE"
    ]
    assert _tabela(tmp_path)["arquivo"].tolist() == ["2025"]


def test_prazo_prorrogado_vira_linha_nova_sem_mudar_o_passado(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _coletar(banco, FONTE, URL_2025, _csv([_beneficio(EMPRESA)], "utf-8"), PRIMEIRO_DIA)
    prorrogado = _beneficio(EMPRESA, fim="2026/07/03 00:00:00.000")
    _coletar(banco, FONTE, URL_2025, _csv([prorrogado], "utf-8"), SEGUNDO_DIA)
    resumo = _montar(banco, tmp_path)
    assert resumo["beneficios-fiscais-2025"]["retratos"] == 2
    tabela = _tabela(tmp_path)
    assert len(tabela) == 2
    datas = tabela.assign(
        disponivel_em=pd.to_datetime(tabela["disponivel_em"]),
        visto_em=pd.to_datetime(tabela["visto_em"]),
    )
    antes = como_era_em(datas, PRIMEIRO_DIA, ["id_na_fonte"]).iloc[0]
    depois = como_era_em(datas, SEGUNDO_DIA, ["id_na_fonte"]).iloc[0]
    assert antes["vigencia_fim"] == date(2025, 7, 3)
    assert depois["vigencia_fim"] == date(2026, 7, 3)


def test_grava_com_manifesto_contrato_e_marca_de_pessoa(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _coletar(
        banco, FONTE, URL_2025,
        _csv([_beneficio(EMPRESA), _beneficio(OUTRA)], "utf-8"), PRIMEIRO_DIA,
    )  # fmt: skip
    _montar(banco, tmp_path, pessoas={"33000167"})
    tabela = _tabela(tmp_path)
    assert dict(
        zip(tabela["cnpj_basico"], tabela["trata_como_pessoa"], strict=True)
    ) == {
        "11222333": False,
        "33000167": True,
    }
    assert len(tabela["origem_sha256"].iloc[0]) == 64
    assert tabela["versao_do_codigo"].iloc[0] == "0123abc"
    assert tabela["montado_em"].iloc[0] == AGORA.isoformat()
    assert parquets_sem_manifesto(tmp_path / "base") == []
    (manifesto,) = (tmp_path / "base").rglob("*.json")
    conferencia = json.loads(manifesto.read_text(encoding="utf-8"))
    assert conferencia["conferencia_do_contrato"]["aprovada"], manifesto.name


def test_sem_arquivo_novo_e_pulado(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _coletar(banco, FONTE, URL_2025, _csv([_beneficio(EMPRESA)], "utf-8"), PRIMEIRO_DIA)
    _montar(banco, tmp_path)
    assert _montar(banco, tmp_path)["beneficios-fiscais-2025"] == incentivos.JA_MONTADO


def test_o_nome_do_parquet_e_o_ano_da_url():
    assert incentivos.nome_do_arquivo(URL_2025) == "beneficios-fiscais-2025"
    assert incentivos.ano_da_pe(URL_2008) == "2008"
    with pytest.raises(ValueError, match="ano"):
        incentivos.ano_da_pe("https://x/outra_coisa.csv")


def test_comando_monta_tambem_a_sefaz_pe(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import carga_incentivos

    _coletar(banco, FONTE, URL_2025, _csv([_beneficio(EMPRESA)], "utf-8"), PRIMEIRO_DIA)
    assert carga_incentivos.main(["--pasta", str(tmp_path / "b")]) == 0
    tabela = pd.read_parquet(
        tmp_path / "b" / "sefaz_pe_beneficios" / "beneficios-fiscais-2025.parquet"
    )
    assert tabela["trata_como_pessoa"].all()  # sem a Receita guardada: o conservador


def test_o_historico_do_catalogo_nao_comeca_antes_de_a_fonte_entrar():
    """A SEFAZ-PE entrou no arquivista em 05/11/2026 (termos lidos nesse dia): o catálogo público
    não pode prometer histórico de 29/10, o dia dos outros três incentivos."""
    assert TABELAS["sefaz_pe_beneficios"].historico_desde == "2026-11-05"
    assert TABELAS["mme_reidi"].historico_desde == "2026-10-29"
