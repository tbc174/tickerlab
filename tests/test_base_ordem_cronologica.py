"""Ordem cronológica de pagamentos de PE e ES por CNPJ na base (linha 755 da fila; motor de risco cedente/sacado).

As tabelas `sefaz_pe_ordem_cronologica` e `es_ordem_cronologica` de `base/ordem_cronologica.py`: um Parquet por
ano de cada estado, com os retratos do ano numa série só. Só CNPJ inteiro de dígito certo; nome e CPF nunca
entram (a coleta já os tirou); toda linha vale desde o dia do arquivo (`disponivel_em`); as datas do pagamento
(`liquidado_em`, `pago_em`) contam quando aconteceu, não quando a base soube. `dias_ate_pagar` é o prazo
real do governo. Os arquivos guardados são os da coleta: ";" e UTF-8. Tudo de mentira.
"""

import json
from datetime import date

import pandas as pd
import pytest

from base import cnpj as cnpjs
from base import ordem_cronologica as oc
from base.ancoragem import parquets_sem_manifesto
from base.dicionario import TABELAS
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

PE = oc.PERNAMBUCO
ES = oc.ESPIRITO_SANTO


def _url_pe(dia: date) -> str:
    """O CSV do ano de Pernambuco: o nome leva o dia da geração e muda todo dia."""
    return (
        "https://dados.pe.gov.br/dataset/x/resource/y/download/"
        f"ordem_cronologica_pagamentos_2026_{dia:%d%m%Y}.csv"
    )


def _url_es(ano: int = 2026) -> str:
    """O CSV do ano do Espírito Santo: o nome é fixo, o conteúdo cresce."""
    return f"https://dados.es.gov.br/dataset/x/resource/y/download/ordemcronologicapagamentos-{ano}.csv"


def _pagamento_pe(
    ordem: str,
    documento: str = EMPRESA,
    empenho: str = "2026NE000001",
    liquidado: str = "2026/01/10 00:00:00.000",
    pago: str = "2026/01/25 00:00:00.000",
    valor: str = "1.500,50",
) -> dict[str, str]:
    """Uma linha como a coleta guarda: só as colunas guardadas, sem nome do credor."""
    return {
        "descicao_unidade_gestora": "SECRETARIA DE SAUDE",
        "codigo_ug": "010001",
        "cnpj": documento,
        "numero_empenho": empenho,
        "numero_documento": "5725",
        "categoria_contrato": "SERVIÇOS",
        "numero_ordem_bancaria": ordem,
        "data_liquidacao": liquidado,
        "data_ordem_bancaria": "2026/01/24 00:00:00.000",
        "data_pagamento": pago,
        "valor_documento": "52000,00",
        "valor_liquido_pagamento": valor,
    }


def _pagamento_es(
    ordem: str,
    documento: str = EMPRESA,
    empenho: str = "2026NE00001",
    liquidado: str = "10/01/2026 00:00:00",
    pago: str = "13/01/2026 00:00:00",
    valor: str = "59,6400",
) -> dict[str, str]:
    return {
        "codigoug": "450202",
        "unidadegestora": "DETRAN",
        "nomecategoriacontrato": "Locações",
        "datacronologica": "08/01/2026",
        "credor": documento,
        "codigone": empenho,
        "codigonl": "2026NL00001",
        "dataemissaonl": liquidado,
        "dataemissaoob": pago,
        "codigoob": ordem,
        "valorob": valor,
    }


def _guardar_pe(banco, dia: date, linhas: list[dict[str, str]]) -> None:
    _coletar(banco, PE.fonte, _url_pe(dia), _csv(linhas, "utf-8"), dia)


def _guardar_es(
    banco, dia: date, linhas: list[dict[str, str]], ano: int = 2026
) -> None:
    _coletar(banco, ES.fonte, _url_es(ano), _csv(linhas, "utf-8"), dia)


def _montar(banco, tmp_path, pessoas=frozenset(), **opcoes) -> dict:
    with banco.connect() as conexao:
        return oc.montar(
            conexao, tmp_path / "base", AGORA, pessoas=set(pessoas), **opcoes
        )


def _tabela(tmp_path, tabela: oc.Tabela, ano: int = 2026) -> pd.DataFrame:
    return pd.read_parquet(
        tmp_path / "base" / tabela.tabela / f"ordem-cronologica-{ano}.parquet"
    )


def test_so_cnpj_inteiro_com_datas_valores_e_prazo_de_pagamento_em_pe(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar_pe(
        banco, PRIMEIRO_DIA,
        [
            _pagamento_pe("OB1"),
            _pagamento_pe("OB2", OUTRA, pago="2026/01/10 00:00:00.000"),  # pago no mesmo dia
            _pagamento_pe("OB3", INVALIDO),
            _pagamento_pe("OB4", ""),
            _pagamento_pe("OB1"),  # repetida de verdade: fica a primeira
            _pagamento_pe("OB5", pago=""),  # ainda não pago: sem prazo
        ],
    )  # fmt: skip
    resumo = _montar(banco, tmp_path)["sefaz_pe_ordem_cronologica/2026"]
    assert resumo["cnpj_invalido"] == 2
    assert resumo["id_repetido"] == 1
    tabela = _tabela(tmp_path, PE).set_index("ordem_bancaria")
    assert len(tabela) == 3
    linha = tabela.loc["OB1"]
    assert linha["cnpj"] == cnpjs.formatar(EMPRESA)
    assert linha["cnpj_basico"] == "11222333"
    assert linha["arquivo"] == "2026"
    assert linha["unidade_gestora"] == "SECRETARIA DE SAUDE"
    assert linha["valor_pago"] == 1500.50  # vírgula decimal e ponto de milhar
    assert linha["valor_documento"] == 52000.00
    assert linha["liquidado_em"] == date(2026, 1, 10)
    assert linha["pago_em"] == date(2026, 1, 25)
    assert linha["dias_ate_pagar"] == 15
    assert tabela.loc["OB2", "dias_ate_pagar"] == 0
    assert pd.isna(tabela.loc["OB5", "pago_em"])
    assert pd.isna(tabela.loc["OB5", "dias_ate_pagar"])
    assert (
        linha["disponivel_em"] == PRIMEIRO_DIA
    )  # o pagamento é de janeiro; a base soube agora


def test_espirito_santo_le_o_formato_de_data_e_de_valor_dele(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar_es(
        banco,
        PRIMEIRO_DIA,
        [_pagamento_es("2026OB1"), _pagamento_es("2026OB2", INVALIDO)],
    )
    resumo = _montar(banco, tmp_path)["es_ordem_cronologica/2026"]
    assert resumo["cnpj_invalido"] == 1
    (linha,) = _tabela(tmp_path, ES).to_dict("records")
    assert linha["nota_de_liquidacao"] == "2026NL00001"
    assert linha["ordem_cronologica_em"] == date(2026, 1, 8)
    assert linha["liquidado_em"] == date(2026, 1, 10)
    assert linha["pago_em"] == date(2026, 1, 13)  # a emissão da ordem bancária
    assert linha["dias_ate_pagar"] == 3
    assert linha["valor_pago"] == 59.64


def test_ordens_bancarias_iguais_com_valores_diferentes_sao_pagamentos_diferentes(
    banco, tmp_path, monkeypatch
):
    """Uma ordem bancária pode pagar vários documentos do mesmo empenho: o valor entra na identidade."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar_es(
        banco, PRIMEIRO_DIA,
        [_pagamento_es("OB1", valor="10,00"), _pagamento_es("OB1", valor="20,00")],
    )  # fmt: skip
    resumo = _montar(banco, tmp_path)["es_ordem_cronologica/2026"]
    assert resumo["id_repetido"] == 0
    assert sorted(_tabela(tmp_path, ES)["valor_pago"]) == [10.0, 20.0]


def test_os_retratos_do_ano_formam_uma_serie_mesmo_com_o_nome_do_dia_diferente(
    banco, tmp_path, monkeypatch
):
    """PE troca o nome do arquivo todo dia; o ano no nome é o que junta os retratos."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar_pe(
        banco, PRIMEIRO_DIA, [_pagamento_pe("OB1"), _pagamento_pe("OB2", OUTRA)]
    )
    corrigido = _pagamento_pe("OB1", pago="2026/01/30 00:00:00.000")
    _guardar_pe(banco, SEGUNDO_DIA, [corrigido, _pagamento_pe("OB2", OUTRA)])
    resumo = _montar(banco, tmp_path)["sefaz_pe_ordem_cronologica/2026"]
    assert resumo["retratos"] == 2
    tabela = _tabela(tmp_path, PE)
    assert (
        len(tabela) == 3
    )  # a OB1 mudou de data (2 linhas); a OB2 ficou igual (1 linha)
    ob1 = tabela[tabela["ordem_bancaria"] == "OB1"].sort_values("visto_em")
    assert ob1["pago_em"].tolist() == [date(2026, 1, 25), date(2026, 1, 30)]
    assert ob1["dias_ate_pagar"].tolist() == [15, 20]
    assert ob1["disponivel_em"].tolist() == [PRIMEIRO_DIA, SEGUNDO_DIA]


def test_pagamento_que_some_do_arquivo_ganha_consta_falso_sem_apagar_o_passado(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar_pe(
        banco, PRIMEIRO_DIA, [_pagamento_pe("OB1"), _pagamento_pe("OB2", OUTRA)]
    )
    _guardar_pe(
        banco, SEGUNDO_DIA, [_pagamento_pe("OB2", OUTRA), _pagamento_pe("OB3", OUTRA)]
    )
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, PE)
    ob1 = tabela[tabela["ordem_bancaria"] == "OB1"].sort_values("visto_em")
    assert ob1["consta"].tolist() == [True, False]  # existia, e o estado tirou
    novo = tabela[tabela["ordem_bancaria"] == "OB3"]
    assert novo["disponivel_em"].tolist() == [SEGUNDO_DIA]  # só vale desde que apareceu


def test_cada_ano_e_um_parquet_e_o_ano_velho_nao_perde_linha_na_virada(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar_es(banco, PRIMEIRO_DIA, [_pagamento_es("2025OB1")], ano=2025)
    _guardar_es(banco, PRIMEIRO_DIA, [_pagamento_es("2026OB1")], ano=2026)
    _guardar_es(
        banco,
        SEGUNDO_DIA,
        [_pagamento_es("2026OB1"), _pagamento_es("2026OB2")],
        ano=2026,
    )
    resumo = _montar(banco, tmp_path)
    assert set(resumo) == {"es_ordem_cronologica/2025", "es_ordem_cronologica/2026"}
    velho = _tabela(tmp_path, ES, 2025)
    assert velho["arquivo"].tolist() == ["2025"]
    assert velho["consta"].tolist() == [
        True
    ]  # o ano velho não "perde" nada quando o novo começa
    assert len(_tabela(tmp_path, ES, 2026)) == 2


def test_nome_e_cpf_nunca_chegam_ao_parquet_e_as_colunas_batem_com_o_dicionario(
    banco, tmp_path, monkeypatch
):
    """A tabela não tem onde guardar pessoa; as colunas gravadas são as do dicionário, na mesma ordem."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar_pe(banco, PRIMEIRO_DIA, [_pagamento_pe("OB1")])
    _guardar_es(banco, PRIMEIRO_DIA, [_pagamento_es("OB1")])
    _montar(banco, tmp_path)
    for spec in oc.TABELAS:
        colunas = list(_tabela(tmp_path, spec).columns)
        assert not {"cpf", "nome", "nome_credor", "credor", "razao_social"} & set(
            colunas
        )
        assert colunas == list(TABELAS[spec.tabela].colunas)


def test_grava_com_manifesto_contrato_e_marca_de_pessoa(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar_pe(
        banco, PRIMEIRO_DIA, [_pagamento_pe("OB1"), _pagamento_pe("OB2", OUTRA)]
    )
    _montar(banco, tmp_path, pessoas={"33000167"})
    tabela = _tabela(tmp_path, PE)
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


def test_sem_arquivo_novo_e_pulado_e_refazer_le_de_novo(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar_pe(banco, PRIMEIRO_DIA, [_pagamento_pe("OB1")])
    nome = "sefaz_pe_ordem_cronologica/2026"
    _montar(banco, tmp_path)
    assert _montar(banco, tmp_path)[nome] == oc.JA_MONTADO
    assert "retratos" in _montar(banco, tmp_path, refazer=True)[nome]


def test_sem_nada_guardado_nao_monta_nada(banco, tmp_path):
    assert _montar(banco, tmp_path) == {}


def test_arquivo_sem_o_ano_no_nome_e_erro_e_nao_vira_um_ano_qualquer():
    with pytest.raises(ValueError, match="sem o ano"):
        oc._ano_no_nome("https://dados.pe.gov.br/x/download/ordem.csv")
    assert oc._ano_no_nome(_url_pe(date(2026, 11, 6))) == "2026"
    assert oc._ano_no_nome(_url_es(2025)) == "2025"


def test_comando_monta_as_tabelas_e_sai_com_1_sem_arquivo(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import carga_ordem_cronologica

    pasta = str(tmp_path / "b")
    assert carga_ordem_cronologica.main(["--pasta", pasta]) == 1
    _guardar_es(banco, PRIMEIRO_DIA, [_pagamento_es("OB1")])
    assert carga_ordem_cronologica.main(["--pasta", pasta]) == 0
    tabela = pd.read_parquet(
        tmp_path / "b" / "es_ordem_cronologica" / "ordem-cronologica-2026.parquet"
    )
    assert tabela["trata_como_pessoa"].all()  # sem a Receita guardada: o conservador


def test_o_historico_do_catalogo_comeca_no_dia_em_que_a_fonte_entrou():
    for spec in oc.TABELAS:
        assert TABELAS[spec.tabela].historico_desde == "2026-11-06"
