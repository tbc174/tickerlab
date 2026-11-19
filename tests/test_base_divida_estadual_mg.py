"""Dívida ativa de Minas Gerais por CNPJ na base (SEF-MG, linha 755 da fila; motor de risco cedente/sacado).

As tabelas `sef_mg_divida_ativa` (CDAs) e `sef_mg_parcelamentos` de `base/divida_estadual.py`: as duas
planilhas vêm da mesma fonte e do mesmo dia, mas cada uma é uma série (a separação é pelo fim do
endereço). Só CNPJ inteiro de dígito certo; nome e CPF nunca entram (a coleta já os tirou); toda linha vale
desde o dia da planilha (`disponivel_em`); a data da inscrição fica em `inscrito_em`. Tudo de mentira.
"""

import json
from datetime import date

import pandas as pd

from base import divida_estadual
from base.ancoragem import parquets_sem_manifesto
from base.arquivo import lote_divida_estadual as lote
from base.dicionario import TABELAS
from tests.test_base_incentivos import (
    AGORA,
    EMPRESA,
    OUTRA,
    PRIMEIRO_DIA,
    SEGUNDO_DIA,
    _coletar,
    _csv,
)

FONTE = divida_estadual.FONTE_DE_MG
CDAS = f"{lote.PASTA_DE_MG}/{lote.ARQUIVO_DAS_CDAS_DE_MG}"
PARCELAMENTOS = f"{lote.PASTA_DE_MG}/{lote.ARQUIVO_DOS_PARCELAMENTOS_DE_MG}"
INVALIDA = "11.222.333/0001-82"


def _cda(
    numero: str, cnpj: str, saldo: str = "1500.5", especie: str = "ICMS"
) -> dict[str, str]:
    """Uma linha como a coleta guarda: as 6 colunas da planilha, sem o nome do devedor."""
    return {
        "CNPJ": cnpj,
        "CDA": numero,
        "Data da inscrição": "2020-03-04",
        "Espécie": especie,
        "Saldo da CDA": saldo,
        "Saldo do núcleo": "900.25",
    }


def _parcelamento(numero: str, cnpj: str, debito: str = "12345.67") -> dict[str, str]:
    return {
        "CNPJ": cnpj,
        "Parcelamento": numero,
        "Espécie": "ICMS",
        "Data do parcelamento": "2022-01-31",
        "Parcelas": "60",
        "Débito": debito,
    }


def _guardar(banco, dia: date, cdas=(), parcelamentos=()) -> None:
    if cdas:
        _coletar(banco, FONTE, CDAS, _csv(list(cdas), "utf-8"), dia)
    if parcelamentos:
        _coletar(banco, FONTE, PARCELAMENTOS, _csv(list(parcelamentos), "utf-8"), dia)


def _montar(banco, tmp_path, pessoas=frozenset(), **opcoes) -> dict:
    with banco.connect() as conexao:
        return divida_estadual.montar(
            conexao, tmp_path / "base", AGORA, pessoas=set(pessoas), **opcoes
        )


def _cdas(tmp_path) -> pd.DataFrame:
    return pd.read_parquet(
        tmp_path / "base" / "sef_mg_divida_ativa" / "divida_ativa.parquet"
    )


def _parcelamentos(tmp_path) -> pd.DataFrame:
    return pd.read_parquet(
        tmp_path / "base" / "sef_mg_parcelamentos" / "parcelamentos.parquet"
    )


def test_le_so_as_colunas_que_a_coleta_guarda():
    """A leitura não pode depender de coluna que o filtro da coleta tira (o nome do devedor)."""
    assert set(divida_estadual._CDAS_DE_MG.values()) == set(
        lote.COLUNAS_DAS_CDAS_DE_MG.values()
    )
    assert set(divida_estadual._PARCELAMENTOS_DE_MG.values()) == set(
        lote.COLUNAS_DOS_PARCELAMENTOS_DE_MG.values()
    )


def test_cdas_so_cnpj_inteiro_com_a_data_da_inscricao_na_coluna_propria(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(
        banco,
        PRIMEIRO_DIA,
        cdas=[
            _cda("100", EMPRESA),
            _cda("200", OUTRA, "10.5", "IPVA"),
            _cda("300", INVALIDA),
            _cda("400", ""),
            _cda("100", EMPRESA),  # repetida (mesma chave): fica a primeira
        ],
    )
    resumo = _montar(banco, tmp_path)["mg_divida_ativa"]
    assert resumo["cnpj_invalido"] == 2
    assert resumo["id_repetido"] == 1
    tabela = _cdas(tmp_path).set_index("cda")
    assert len(tabela) == 2
    linha = tabela.loc["100"]
    assert linha["cnpj_basico"] == "11222333"
    assert linha["id_na_fonte"] == f"100|{EMPRESA}"
    assert linha["especie"] == "ICMS"
    assert linha["saldo_da_cda"] == 1500.5 and linha["saldo_do_nucleo"] == 900.25
    # a dívida nasceu em 2020, mas a base só soube no dia da planilha
    assert linha["inscrito_em"] == date(2020, 3, 4)
    assert linha["disponivel_em"] == PRIMEIRO_DIA


def test_parcelamentos_sao_outra_tabela_da_mesma_fonte_e_do_mesmo_dia(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(
        banco,
        PRIMEIRO_DIA,
        cdas=[_cda("100", EMPRESA)],
        parcelamentos=[_parcelamento("7", OUTRA)],
    )
    resumo = _montar(banco, tmp_path)
    assert resumo["mg_divida_ativa"]["linhas"] == 1
    assert resumo["mg_parcelamentos"]["linhas"] == 1
    assert list(_cdas(tmp_path)["cda"]) == ["100"]  # o parcelamento não entra nas CDAs
    parcelamentos = _parcelamentos(tmp_path)
    linha = parcelamentos.iloc[0]
    assert linha["parcelamento"] == "7" and linha["parcelas"] == 60
    assert linha["debito"] == 12345.67
    assert linha["parcelado_em"] == date(2022, 1, 31)
    assert linha["cnpj_basico"] == "33000167"


def test_cada_semana_e_um_retrato_valor_novo_vira_linha_nova_e_o_que_some_ganha_consta_falso(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(
        banco,
        PRIMEIRO_DIA,
        cdas=[_cda("100", EMPRESA), _cda("200", OUTRA)],
        parcelamentos=[_parcelamento("7", OUTRA)],
    )
    _guardar(
        banco,
        SEGUNDO_DIA,
        cdas=[_cda("100", EMPRESA, "1700.0"), _cda("300", OUTRA)],
        parcelamentos=[_parcelamento("7", OUTRA)],
    )
    resumo = _montar(banco, tmp_path)
    assert resumo["mg_divida_ativa"]["retratos"] == 2
    tabela = _cdas(tmp_path)
    do_100 = tabela[tabela["cda"] == "100"].sort_values("visto_em")
    assert do_100["saldo_da_cda"].tolist() == [1500.5, 1700.0]
    do_200 = tabela[tabela["cda"] == "200"].sort_values("visto_em")
    assert do_200["consta"].tolist() == [True, False]  # existia, e sumiu (paga?)
    assert do_200["disponivel_em"].tolist() == [PRIMEIRO_DIA, SEGUNDO_DIA]
    assert tabela[tabela["cda"] == "300"]["disponivel_em"].tolist() == [SEGUNDO_DIA]
    assert len(_parcelamentos(tmp_path)) == 1  # igual nos dois dias: uma linha só


def test_valor_e_data_ruins_viram_nulos_sem_derrubar_a_carga(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    ruim = _cda("100", EMPRESA, saldo="")
    ruim["Data da inscrição"] = "2026-02-31"
    _guardar(banco, PRIMEIRO_DIA, cdas=[ruim])
    _montar(banco, tmp_path)
    linha = _cdas(tmp_path).iloc[0]
    assert pd.isna(linha["saldo_da_cda"]) and pd.isna(linha["inscrito_em"])


def test_nome_e_cpf_nunca_chegam_ao_parquet(banco, tmp_path, monkeypatch):
    """O filtro da coleta tira o nome; as tabelas não têm onde guardá-lo."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(
        banco,
        PRIMEIRO_DIA,
        cdas=[_cda("100", EMPRESA)],
        parcelamentos=[_parcelamento("7", OUTRA)],
    )
    _montar(banco, tmp_path)
    proibidas = {"cpf", "nome", "razao_social", "devedor", "devedor_principal"}
    for tabela, lida in (
        ("sef_mg_divida_ativa", _cdas(tmp_path)),
        ("sef_mg_parcelamentos", _parcelamentos(tmp_path)),
    ):
        assert not proibidas & set(lida.columns)
        assert set(TABELAS[tabela].colunas) <= set(lida.columns)


def test_grava_com_manifesto_contrato_e_marca_de_pessoa(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(
        banco,
        PRIMEIRO_DIA,
        cdas=[_cda("100", EMPRESA), _cda("200", OUTRA)],
        parcelamentos=[_parcelamento("7", OUTRA)],
    )
    _montar(banco, tmp_path, pessoas={"33000167"})
    tabela = _cdas(tmp_path)
    assert dict(
        zip(tabela["cnpj_basico"], tabela["trata_como_pessoa"], strict=True)
    ) == {"11222333": False, "33000167": True}
    assert tabela["versao_do_codigo"].iloc[0] == "0123abc"
    assert tabela["montado_em"].iloc[0] == AGORA.isoformat()
    assert parquets_sem_manifesto(tmp_path / "base") == []
    manifestos = sorted((tmp_path / "base").rglob("*.json"))
    assert len(manifestos) == 2
    for manifesto in manifestos:
        conferencia = json.loads(manifesto.read_text(encoding="utf-8"))
        assert conferencia["conferencia_do_contrato"]["aprovada"], manifesto.name


def test_sem_arquivo_novo_e_pulado_e_refazer_le_de_novo(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(banco, PRIMEIRO_DIA, cdas=[_cda("100", EMPRESA)])
    _montar(banco, tmp_path)
    segunda = _montar(banco, tmp_path)
    assert segunda["mg_divida_ativa"] == divida_estadual.JA_MONTADO
    assert "retratos" in _montar(banco, tmp_path, refazer=True)["mg_divida_ativa"]


def test_so_a_planilha_que_existe_e_montada(banco, tmp_path, monkeypatch):
    """Sem parcelamento guardado, a tabela dele não aparece (nem o aviso de erro)."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(banco, PRIMEIRO_DIA, cdas=[_cda("100", EMPRESA)])
    resumo = _montar(banco, tmp_path)
    assert "mg_parcelamentos" not in resumo
    assert not (tmp_path / "base" / "sef_mg_parcelamentos").exists()


def test_o_historico_do_catalogo_comeca_no_dia_em_que_a_fonte_entrou():
    for tabela in ("sef_mg_divida_ativa", "sef_mg_parcelamentos"):
        assert TABELAS[tabela].historico_desde == "2026-11-06"
