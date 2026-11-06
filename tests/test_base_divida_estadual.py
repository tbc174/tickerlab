"""Dívida ativa do Paraná por CNPJ na base (Sefa-PR, linha 755 da fila; motor de risco cedente/sacado).

A tabela `sefa_pr_divida_ativa` de `base/divida_estadual.py`: um ZIP por dia, todos numa série só.
Só CNPJ inteiro de dígito certo; nome e CPF nunca entram (a coleta já os tirou); toda linha vale desde o
dia do arquivo (`disponivel_em`); a data da inscrição fica em `inscrito_em`, que conta quando o débito
nasceu, não quando a base soube. Os arquivos guardados são os da coleta: ";" e UTF-8. Tudo de mentira.
"""

import json
from datetime import date

import pandas as pd

from base import cnpj as cnpjs
from base import divida_estadual
from base.ancoragem import parquets_sem_manifesto
from base.arquivo import lote_divida_estadual as lote
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
)

FONTE = divida_estadual.FONTE_DO_PR


def _url(dia: date) -> str:
    """O endereço do ZIP do dia: muda de nome todo dia."""
    return f"{lote.PORTAL_DO_PR}/portal-devedor/download/csv/lista-devedores-pr_{dia:%d-%m-%Y}_04_00.zip"


def _debito(
    numero: str,
    documento: str,
    total: str = "1793.01",
    tipo: str = "ICMS",
    suspensao: str = "Não",
    garantia: str = "Não",
    parcelamento: str = "Não",
    atualizado: str = "01/11/2026",
) -> dict[str, str]:
    """Uma linha como a coleta guarda: as 12 colunas da fonte, sem CPF nem nome."""
    return {
        "Dívida ativa": numero,
        "Data da inscrição do débito": "18/06/1973",
        "Data da atualização": atualizado,
        "Valor do imposto": "1787.10",
        "Valor da multa": "5.91",
        "Valor dos juros": "0.00",
        "Valor total": total,
        "Tipo do crédito": tipo,
        "CNPJ": documento,
        "Suspensão de exigibilidade": suspensao,
        "Indicativo de garantia": garantia,
        "Indicativo de parcelamento ativo": parcelamento,
    }


def _guardar(banco, dia: date, linhas: list[dict[str, str]]) -> None:
    _coletar(banco, FONTE, _url(dia), _csv(linhas, "utf-8"), dia)


def _montar(banco, tmp_path, pessoas=frozenset(), **opcoes) -> dict:
    with banco.connect() as conexao:
        return divida_estadual.montar(
            conexao, tmp_path / "base", AGORA, pessoas=set(pessoas), **opcoes
        )


def _tabela(tmp_path) -> pd.DataFrame:
    return pd.read_parquet(
        tmp_path / "base" / "sefa_pr_divida_ativa" / "divida_ativa.parquet"
    )


def test_le_so_as_colunas_que_a_coleta_guarda():
    """A leitura não pode depender de coluna que o filtro da coleta tira (CPF, nome)."""
    assert set(divida_estadual._PR.values()) <= set(lote.COLUNAS_GUARDADAS_NO_PR)
    for tirada in lote.COLUNAS_DE_PESSOA_NO_PR:
        assert tirada not in divida_estadual._PR.values()


def test_so_cnpj_inteiro_com_a_data_da_inscricao_na_coluna_propria(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    linhas = [
        _debito("100", EMPRESA, suspensao="DEPOSITO JUDICIAL", garantia="Sim"),
        _debito("200", OUTRA, "10.50", "IPVA", parcelamento="Sim"),
        _debito("300", INVALIDO),
        _debito("400", ""),
        _debito("100", EMPRESA),  # repetida (mesma chave): fica a primeira
    ]
    _guardar(banco, PRIMEIRO_DIA, linhas)
    resumo = _montar(banco, tmp_path)["divida_ativa"]
    assert resumo["cnpj_invalido"] == 2
    assert resumo["id_repetido"] == 1
    tabela = _tabela(tmp_path).set_index("divida_ativa")
    assert len(tabela) == 2
    linha = tabela.loc["100"]
    assert linha["cnpj"] == cnpjs.formatar(EMPRESA)
    assert linha["cnpj_basico"] == "11222333"
    assert linha["tipo_do_credito"] == "ICMS"
    assert linha["id_na_fonte"] == f"100|{EMPRESA}|ICMS"
    assert linha["valor_total"] == 1793.01
    assert linha["valor_do_imposto"] == 1787.10
    assert linha["suspensao"] == "DEPOSITO JUDICIAL"
    assert bool(linha["com_garantia"]) and not bool(linha["com_parcelamento_ativo"])
    assert linha["atualizado_em"] == date(2026, 11, 1)
    # a dívida nasceu em 1973, mas a base só soube no dia do arquivo
    assert linha["inscrito_em"] == date(1973, 6, 18)
    assert linha["disponivel_em"] == PRIMEIRO_DIA
    outra = tabela.loc["200"]
    assert pd.isna(outra["suspensao"])  # "Não" é a ausência de suspensão
    assert bool(outra["com_parcelamento_ativo"]) and not bool(outra["com_garantia"])


def test_mesmo_numero_em_tipos_diferentes_sao_debitos_diferentes(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(
        banco, PRIMEIRO_DIA,
        [_debito("100", EMPRESA, tipo="ICMS"), _debito("100", EMPRESA, tipo="IPVA")],
    )  # fmt: skip
    _montar(banco, tmp_path)
    assert sorted(_tabela(tmp_path)["tipo_do_credito"]) == ["ICMS", "IPVA"]


def test_data_e_valor_ruins_viram_nulos_sem_derrubar_a_carga(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    ruim = _debito("100", EMPRESA, total="", atualizado="31/02/2026")
    _guardar(banco, PRIMEIRO_DIA, [ruim])
    _montar(banco, tmp_path)
    linha = _tabela(tmp_path).iloc[0]
    assert pd.isna(linha["valor_total"])
    assert pd.isna(linha["atualizado_em"])


def test_cada_dia_e_um_retrato_da_mesma_serie_valor_novo_vira_linha_nova(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(banco, PRIMEIRO_DIA, [_debito("100", EMPRESA), _debito("200", OUTRA)])
    atualizado = _debito("100", EMPRESA, total="1900.00", atualizado="29/11/2026")
    _guardar(banco, SEGUNDO_DIA, [atualizado, _debito("200", OUTRA)])
    resumo = _montar(banco, tmp_path)["divida_ativa"]
    assert resumo["retratos"] == 2
    tabela = _tabela(tmp_path)
    assert len(tabela) == 3  # o 100 mudou (2 linhas); o 200 ficou igual (1 linha)
    datas = tabela.assign(
        disponivel_em=pd.to_datetime(tabela["disponivel_em"]),
        visto_em=pd.to_datetime(tabela["visto_em"]),
    )
    chave = ["id_na_fonte"]
    antes = como_era_em(datas, PRIMEIRO_DIA, chave).set_index("divida_ativa")
    depois = como_era_em(datas, SEGUNDO_DIA, chave).set_index("divida_ativa")
    assert antes.loc["100", "valor_total"] == 1793.01
    assert depois.loc["100", "valor_total"] == 1900.00


def test_debito_que_some_do_arquivo_ganha_consta_falso_sem_apagar_o_passado(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(banco, PRIMEIRO_DIA, [_debito("100", EMPRESA), _debito("200", OUTRA)])
    _guardar(banco, SEGUNDO_DIA, [_debito("200", OUTRA), _debito("300", OUTRA)])
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path)
    do_100 = tabela[tabela["divida_ativa"] == "100"].sort_values("visto_em")
    assert do_100["consta"].tolist() == [True, False]  # existia, e sumiu (quitado?)
    assert do_100["disponivel_em"].tolist() == [PRIMEIRO_DIA, SEGUNDO_DIA]
    novo = tabela[tabela["divida_ativa"] == "300"]
    assert novo["disponivel_em"].tolist() == [
        SEGUNDO_DIA
    ]  # só vale desde o dia em que apareceu


def test_nome_e_cpf_nunca_chegam_ao_parquet(banco, tmp_path, monkeypatch):
    """O filtro da coleta tira as colunas de pessoa; a tabela não tem onde guardá-las."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(banco, PRIMEIRO_DIA, [_debito("100", EMPRESA)])
    _montar(banco, tmp_path)
    colunas = set(_tabela(tmp_path).columns)
    assert not {"cpf", "nome", "razao_social", "nome_razao_social"} & colunas
    assert set(TABELAS["sefa_pr_divida_ativa"].colunas) <= colunas


def test_grava_com_manifesto_contrato_e_marca_de_pessoa(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(banco, PRIMEIRO_DIA, [_debito("100", EMPRESA), _debito("200", OUTRA)])
    _montar(banco, tmp_path, pessoas={"33000167"})
    tabela = _tabela(tmp_path)
    assert dict(
        zip(tabela["cnpj_basico"], tabela["trata_como_pessoa"], strict=True)
    ) == {"11222333": False, "33000167": True}
    assert len(tabela["origem_sha256"].iloc[0]) == 64
    assert tabela["versao_do_codigo"].iloc[0] == "0123abc"
    assert tabela["montado_em"].iloc[0] == AGORA.isoformat()
    assert parquets_sem_manifesto(tmp_path / "base") == []
    (manifesto,) = (tmp_path / "base").rglob("*.json")
    conferencia = json.loads(manifesto.read_text(encoding="utf-8"))
    assert conferencia["conferencia_do_contrato"]["aprovada"], manifesto.name


def test_sem_arquivo_novo_e_pulado_e_refazer_le_de_novo(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(banco, PRIMEIRO_DIA, [_debito("100", EMPRESA)])
    _montar(banco, tmp_path)
    assert _montar(banco, tmp_path)["divida_ativa"] == divida_estadual.JA_MONTADO
    assert "retratos" in _montar(banco, tmp_path, refazer=True)["divida_ativa"]


def test_sem_nada_guardado_nao_monta_nada(banco, tmp_path):
    assert _montar(banco, tmp_path) == {}


def test_comando_monta_a_tabela_e_sai_com_1_sem_arquivo(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import carga_divida_estadual

    pasta = str(tmp_path / "b")
    assert carga_divida_estadual.main(["--pasta", pasta]) == 1
    _guardar(banco, PRIMEIRO_DIA, [_debito("100", EMPRESA)])
    assert carga_divida_estadual.main(["--pasta", pasta]) == 0
    tabela = pd.read_parquet(
        tmp_path / "b" / "sefa_pr_divida_ativa" / "divida_ativa.parquet"
    )
    assert tabela["trata_como_pessoa"].all()  # sem a Receita guardada: o conservador


def test_o_historico_do_catalogo_comeca_no_dia_em_que_a_fonte_entrou():
    assert TABELAS["sefa_pr_divida_ativa"].historico_desde == "2026-11-06"
