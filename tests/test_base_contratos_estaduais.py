"""Contratos, sanções e fornecedores do SIGA do RJ por CNPJ na base (linha 1075, lote 1 dos estados).

As tabelas `rj_contratos`, `rj_sancoes_fornecedores` e `rj_fornecedores` de `base/contratos_estaduais.py`: um
Parquet por arquivo da fonte, com os retratos diários numa série só. Só CNPJ inteiro de dígito certo; nome e CPF
nunca entram (a coleta já os tirou); **sem olhar o futuro:** toda linha vale desde o dia do arquivo em que foi
vista (`disponivel_em`), e as datas do contrato (`contratado_em`, `publicado_em`...) contam quando aconteceu,
não quando a base soube. Os arquivos guardados são os da coleta: ";", UTF-8 e o cabeçalho em minúsculas.
Tudo de mentira.
"""

import json
from datetime import date

import pandas as pd
import pytest

from base import cnpj as cnpjs
from base import contratos_estaduais as ce
from base.ancoragem import parquets_sem_manifesto
from base.dicionario import TABELAS
from base.retratos import JA_MONTADO
from tests.test_base_incentivos import (
    AGORA,
    CPF,
    EMPRESA,
    INVALIDO,
    OUTRA,
    PRIMEIRO_DIA,
    SEGUNDO_DIA,
    _coletar,
    _csv,
)

SIGA = "https://www.compras.rj.gov.br/siga/imagens"


def _contrato(
    codigo: str,
    documento: str = EMPRESA,
    pago: str = "350.000,00",
    situacao: str = "Contratado",
) -> dict[str, str]:
    """Uma linha como a coleta guarda: só as colunas guardadas, sem nome, objeto nem processo."""
    return {
        "código do contrato": codigo,
        "id processo": "5001",
        "contratação": "2026000123",
        "status contratação": situacao,
        "data contratação": "10/02/2026",
        "unidade": "SECRETARIA DE SAUDE",
        "codug": "296100",
        "tipo de aquisição": "Pregão Eletrônico",
        "critério de julgamento": "Menor Preço",
        "data início vigência": "01/03/2026",
        "data fim vigência": "28/02/2027",
        "cpf/cnpj": documento,
        "valor total contrato/valor estimado para contratação (r$)": "1.234.567,89",
        "valor total empenhado (r$)": "500.000,00",
        "valor total liquidado (r$)": "400.000,00",
        "valor total pago (r$)": pago,
        "data public deorj": "15/02/2026",
        "regimejuridico": "Lei 14.133/2021",
        "data_assinatura": "",
        "emergencial": "N",
    }


def _sancao(documento: str = EMPRESA, situacao: str = "Vigente") -> dict[str, str]:
    return {
        "cpf/cnpj": documento,
        "órgão/entidade apenadora": "SEFAZ",
        "enquadramento legal": "Art. 87 da Lei 8.666/93",
        "motivo": "Inexecução parcial",
        "contrato": "123/2025",
        "data de efetivação": "01/06/2025",
        "status da penalidade": situacao,
    }


def _fornecedor(documento: str = EMPRESA) -> dict[str, str]:
    return {
        "cpf/cnpj": documento,
        "crc": "SIM",
        "tipo empresarial": "Sociedade Limitada",
        "me/epp": "NÃO",
        "situação da empresa": "Ativo",
        "data de cadastro": "10/01/2020",
        "cidade": "Niterói",
        "uf": "RJ",
    }


def _guardar(
    banco, spec: ce.Tabela, arquivo: str, dia: date, linhas: list[dict[str, str]]
) -> None:
    _coletar(banco, spec.fonte, f"{SIGA}/{arquivo}", _csv(linhas, "utf-8"), dia)


ES = "https://dados.es.gov.br/dataset/x/resource/{}/download/{}"


def _contrato_es(
    ident: str, documento: str = EMPRESA, final: str = "1200,00"
) -> dict[str, str]:
    """Uma linha como a coleta guarda: cabeçalho em minúsculas, sem fornecedor nem objeto."""
    return {
        "id": ident,
        "idorgao": "12",
        "nomeorgao": "SECRETARIA DE SAUDE",
        "numeroprocesso": "2025-ABCDE",
        "modalidadeprocesso": "Pregão Eletrônico",
        "numeroedital": "",
        "numerodocumento": "Contrato 001/2025",
        "tipodocumento": "Contrato",
        "cnpjfornecedor": documento,
        "tipoaquisicao": "Serviço",
        "situacao": "Celebrado",
        "datacelebracao": "10/02/2025 00:00:00",
        "datainiciovigencia": "",
        "datafimvigencia": "31/12/2025 00:00:00",
        "valorinicial": "1000,50",
        "valorfinal": final,
        "eregistropreco": "N",
    }


def _empenho_es(ident: str, documento: str = EMPRESA) -> dict[str, str]:
    return {
        "id": ident,
        "numeroprocesso": "2025-ABCDE",
        "numerodocumento": "Contrato 001/2025",
        "tipodocumento": "Contrato",
        "numeroempenho": "2025NE00001",
        "valorglobal": "500,25",
        "cnpjfornecedor": documento,
    }


def _compra_direta(
    item: str, documento: str = EMPRESA, quantidade: str = "100"
) -> dict[str, str]:
    return {
        "unidade": "SES - SECRETARIA DE SAUDE",
        "id processo": "9001",
        "afastamento": "Dispensa - Pequeno valor",
        "data de aprovação": "10/03/2025",
        "valor do processo (r$)": "1.500,00",
        "cnpj_cpf": cnpjs.formatar(documento) if len(documento) == 14 else documento,
        "id item": item,
        "qtd.": quantidade,
        "unidade de medida": "UN",
        "vl. unitário (r$)": "15,00",
        "ped": "NAO",
        "regime": "Lei 14.133/2021",
        "temporalidade": "12",
    }


def _guardar_em(
    banco, spec: ce.Tabela, url: str, dia: date, linhas: list[dict[str, str]]
) -> None:
    _coletar(banco, spec.fonte, url, _csv(linhas, "utf-8"), dia)


def _montar(banco, tmp_path, pessoas=frozenset(), **opcoes) -> dict:
    with banco.connect() as conexao:
        return ce.montar(
            conexao, tmp_path / "base", AGORA, pessoas=set(pessoas), **opcoes
        )


def _tabela(tmp_path, spec: ce.Tabela, arquivo: str) -> pd.DataFrame:
    return pd.read_parquet(tmp_path / "base" / spec.tabela / f"{arquivo}.parquet")


def _texto_gravado(tmp_path) -> str:
    partes = [
        pd.read_parquet(p).astype(str).to_csv(index=False)
        for p in (tmp_path / "base").rglob("*.parquet")
    ]
    partes += [
        p.read_text(encoding="utf-8") for p in (tmp_path / "base").rglob("*.json")
    ]
    return "\n".join(partes)


def test_contratos_so_cnpj_inteiro_com_datas_e_valores(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(
        banco, ce.RJ_CONTRATOS, "CONTRATOS.CSV", PRIMEIRO_DIA,
        [
            _contrato("101"),
            _contrato("102", cnpjs.formatar(OUTRA)),  # com pontuação, como o SIGA escreve
            _contrato("103", INVALIDO),
            _contrato("104", "***.000.000-**"),
            _contrato("101"),  # repetida de verdade: fica a primeira
        ],
    )  # fmt: skip
    resumo = _montar(banco, tmp_path)["rj_contratos/contratos"]
    assert resumo["cnpj_invalido"] == 2
    assert resumo["id_repetido"] == 1
    tabela = _tabela(tmp_path, ce.RJ_CONTRATOS, "contratos").set_index(
        "codigo_contrato"
    )
    assert sorted(tabela.index) == ["101", "102"]
    linha = tabela.loc["101"]
    assert linha["cnpj"] == cnpjs.formatar(EMPRESA)
    assert linha["cnpj_basico"] == EMPRESA[:8]
    assert tabela.loc["102", "cnpj"] == cnpjs.formatar(OUTRA)
    assert linha["arquivo"] == "contratos"
    assert linha["unidade"] == "SECRETARIA DE SAUDE"
    assert linha["valor_contratado"] == 1234567.89  # vírgula decimal e ponto de milhar
    assert linha["valor_pago"] == 350000.0
    assert linha["contratado_em"] == date(2026, 2, 10)
    assert linha["publicado_em"] == date(2026, 2, 15)
    assert linha["vigencia_fim"] == date(2027, 2, 28)
    assert pd.isna(linha["assinado_em"])  # vazio na fonte fica nulo, não inventado
    # sem olhar o futuro: o contrato é de fevereiro, publicado em fevereiro; a base soube no dia do arquivo
    assert linha["disponivel_em"] == PRIMEIRO_DIA


def test_valor_pago_que_cresce_vira_versao_nova_sem_reescrever_o_passado(
    banco, tmp_path, monkeypatch
):
    """O valor pago de hoje não existia no dia da publicação: cada valor vale desde o arquivo em que apareceu."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    outro = _contrato("102", OUTRA)
    _guardar(
        banco,
        ce.RJ_CONTRATOS,
        "CONTRATOS.CSV",
        PRIMEIRO_DIA,
        [_contrato("101"), outro],
    )
    _guardar(
        banco,
        ce.RJ_CONTRATOS,
        "CONTRATOS.CSV",
        SEGUNDO_DIA,
        [_contrato("101", pago="900.000,00"), outro],
    )
    resumo = _montar(banco, tmp_path)["rj_contratos/contratos"]
    assert resumo["retratos"] == 2
    tabela = _tabela(tmp_path, ce.RJ_CONTRATOS, "contratos")
    assert len(tabela) == 3  # o 101 mudou (2 linhas); o 102 ficou igual (1 linha)
    c101 = tabela[tabela["codigo_contrato"] == "101"].sort_values("visto_em")
    assert c101["valor_pago"].tolist() == [350000.0, 900000.0]
    assert c101["disponivel_em"].tolist() == [PRIMEIRO_DIA, SEGUNDO_DIA]
    # como era no primeiro dia: só o valor de então, nada do segundo arquivo
    antes = tabela[
        pd.to_datetime(tabela["disponivel_em"]) <= pd.Timestamp(PRIMEIRO_DIA)
    ]
    assert antes["valor_pago"].tolist() == [350000.0, 350000.0]


def test_sancao_que_some_ganha_consta_falso_e_a_nova_so_vale_desde_que_apareceu(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    arquivo = "FORNECEDOR_SANCOES.CSV"
    _guardar(banco, ce.RJ_SANCOES, arquivo, PRIMEIRO_DIA, [_sancao(), _sancao(OUTRA)])
    nova = {**_sancao(OUTRA), "contrato": "77/2026", "data de efetivação": "01/11/2026"}
    _guardar(banco, ce.RJ_SANCOES, arquivo, SEGUNDO_DIA, [_sancao(OUTRA), nova])
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, ce.RJ_SANCOES, "fornecedor_sancoes")
    da_empresa = tabela[tabela["cnpj_basico"] == EMPRESA[:8]].sort_values("visto_em")
    assert da_empresa["consta"].tolist() == [True, False]  # existia, e o estado tirou
    assert da_empresa["efetivada_em"].tolist() == [date(2025, 6, 1)] * 2
    nova_linha = tabela[tabela["contrato"] == "77/2026"]
    assert nova_linha["disponivel_em"].tolist() == [SEGUNDO_DIA]
    assert nova_linha["motivo"].tolist() == ["Inexecução parcial"]


def test_sancoes_que_so_diferem_no_motivo_sao_penalidades_diferentes(
    banco, tmp_path, monkeypatch
):
    """No arquivo real, três penalidades só se distinguiam pelo motivo: nenhuma some."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    outro_motivo = {**_sancao(), "motivo": "Atraso na entrega"}
    _guardar(
        banco,
        ce.RJ_SANCOES,
        "FORNECEDOR_SANCOES.CSV",
        PRIMEIRO_DIA,
        [_sancao(), outro_motivo, _sancao()],
    )
    resumo = _montar(banco, tmp_path)["rj_sancoes_fornecedores/fornecedor_sancoes"]
    assert resumo["id_repetido"] == 1  # só a cópia idêntica
    tabela = _tabela(tmp_path, ce.RJ_SANCOES, "fornecedor_sancoes")
    assert sorted(tabela["motivo"]) == ["Atraso na entrega", "Inexecução parcial"]


def test_sancao_que_muda_de_situacao_e_versao_nova_da_mesma_penalidade(
    banco, tmp_path, monkeypatch
):
    """Vigente → Encerrada não é "o estado tirou uma e pôs outra": é a mesma penalidade, desde o dia novo."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    arquivo = "FORNECEDOR_SANCOES.CSV"
    _guardar(banco, ce.RJ_SANCOES, arquivo, PRIMEIRO_DIA, [_sancao(), _sancao(OUTRA)])
    _guardar(
        banco,
        ce.RJ_SANCOES,
        arquivo,
        SEGUNDO_DIA,
        [_sancao(situacao="Encerrada"), _sancao(OUTRA)],
    )
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, ce.RJ_SANCOES, "fornecedor_sancoes")
    da_empresa = tabela[tabela["cnpj_basico"] == EMPRESA[:8]].sort_values("visto_em")
    assert da_empresa["id_na_fonte"].nunique() == 1
    assert da_empresa["situacao"].tolist() == ["Vigente", "Encerrada"]
    assert da_empresa["consta"].tolist() == [True, True]
    assert da_empresa["disponivel_em"].tolist() == [PRIMEIRO_DIA, SEGUNDO_DIA]


def test_fornecedores_um_por_cnpj_com_mei_marcado_como_pessoa(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(
        banco,
        ce.RJ_FORNECEDORES,
        "FORNECEDORES.CSV",
        PRIMEIRO_DIA,
        [_fornecedor(), _fornecedor(OUTRA)],
    )
    _montar(banco, tmp_path, pessoas={OUTRA[:8]})
    tabela = _tabela(tmp_path, ce.RJ_FORNECEDORES, "fornecedores")
    assert dict(
        zip(tabela["cnpj_basico"], tabela["trata_como_pessoa"], strict=True)
    ) == {EMPRESA[:8]: False, OUTRA[:8]: True}
    assert tabela["cadastrado_em"].tolist() == [date(2020, 1, 10)] * 2
    assert set(tabela["cidade"]) == {"Niterói"}


def test_contratos_do_es_um_parquet_por_ano_com_datas_e_valores(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar_em(
        banco, ce.ES_CONTRATOS, ES.format("a", "contratos-2025.csv"), PRIMEIRO_DIA,
        [_contrato_es("1"), _contrato_es("2", OUTRA), _contrato_es("3", INVALIDO), _contrato_es("4", CPF)],
    )  # fmt: skip
    _guardar_em(
        banco, ce.ES_CONTRATOS, ES.format("b", "contratos-2024.csv"), PRIMEIRO_DIA,
        [_contrato_es("9")],
    )  # fmt: skip
    resumo = _montar(banco, tmp_path)
    assert {"es_contratos/contratos-2025", "es_contratos/contratos-2024"} <= set(resumo)
    assert (
        resumo["es_contratos/contratos-2025"]["cnpj_invalido"] == 2
    )  # o DV errado e o CPF
    tabela = _tabela(tmp_path, ce.ES_CONTRATOS, "contratos-2025").set_index(
        "id_contrato"
    )
    assert sorted(tabela.index) == ["1", "2"]
    linha = tabela.loc["1"]
    assert linha["cnpj"] == cnpjs.formatar(EMPRESA)
    assert linha["orgao"] == "SECRETARIA DE SAUDE"
    assert linha["celebrado_em"] == date(2025, 2, 10)  # a hora "00:00:00" não atrapalha
    assert pd.isna(linha["vigencia_inicio"])
    assert linha["vigencia_fim"] == date(2025, 12, 31)
    assert linha["valor_inicial"] == 1000.5 and linha["valor_final"] == 1200.0
    assert pd.isna(linha["edital"])  # vazio na fonte fica nulo
    assert (
        linha["disponivel_em"] == PRIMEIRO_DIA
    )  # celebrado em fevereiro; a base soube no dia do arquivo
    assert _tabela(tmp_path, ce.ES_CONTRATOS, "contratos-2024")[
        "id_contrato"
    ].tolist() == ["9"]


def test_aditivo_que_muda_o_valor_final_do_es_e_versao_nova(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    url = ES.format("a", "contratos-2025.csv")
    outro = _contrato_es("2", OUTRA)
    _guardar_em(banco, ce.ES_CONTRATOS, url, PRIMEIRO_DIA, [_contrato_es("1"), outro])
    _guardar_em(
        banco,
        ce.ES_CONTRATOS,
        url,
        SEGUNDO_DIA,
        [_contrato_es("1", final="1500,00"), outro],
    )
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, ce.ES_CONTRATOS, "contratos-2025")
    primeiro = tabela[tabela["id_contrato"] == "1"].sort_values("visto_em")
    assert primeiro["valor_final"].tolist() == [1200.0, 1500.0]
    assert primeiro["disponivel_em"].tolist() == [PRIMEIRO_DIA, SEGUNDO_DIA]


def test_empenhos_do_es_sem_data_mas_com_o_dia_do_arquivo(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar_em(
        banco, ce.ES_EMPENHOS, ES.format("c", "empenhos-2025.csv"), PRIMEIRO_DIA,
        [_empenho_es("10"), _empenho_es("11", CPF)],
    )  # fmt: skip
    _montar(banco, tmp_path)
    (linha,) = _tabela(tmp_path, ce.ES_EMPENHOS, "empenhos-2025").to_dict("records")
    assert linha["empenho"] == "2025NE00001"
    assert linha["valor_global"] == 500.25
    assert linha["disponivel_em"] == PRIMEIRO_DIA


def test_compras_diretas_do_rj_quantidade_e_preco_separam_os_itens(
    banco, tmp_path, monkeypatch
):
    """No arquivo real, processo, item e CNPJ repetem com quantidade diferente: são compras diferentes."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(
        banco, ce.RJ_COMPRAS_DIRETAS, "COMPRAS_DIRETAS.CSV", PRIMEIRO_DIA,
        [
            _compra_direta("555"),
            _compra_direta("555", quantidade="40"),
            _compra_direta("555"),  # cópia idêntica: fica uma
            _compra_direta("556", "***.000.000-**"),
        ],
    )  # fmt: skip
    resumo = _montar(banco, tmp_path)["rj_compras_diretas/compras_diretas"]
    assert resumo["id_repetido"] == 1 and resumo["cnpj_invalido"] == 1
    tabela = _tabela(tmp_path, ce.RJ_COMPRAS_DIRETAS, "compras_diretas")
    assert sorted(tabela["quantidade"]) == [40.0, 100.0]
    linha = tabela.iloc[0]
    assert linha["valor_do_processo"] == 1500.0 and linha["valor_unitario"] == 15.0
    assert linha["aprovado_em"] == date(2025, 3, 10)
    assert linha["afastamento"] == "Dispensa - Pequeno valor"


def test_nome_e_cpf_nunca_chegam_ao_parquet_e_as_colunas_batem_com_o_dicionario(
    banco, tmp_path, monkeypatch
):
    """Prova por máquina de zero pessoa: nenhum CPF em nada gravado; as colunas são as do dicionário."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(
        banco, ce.RJ_CONTRATOS, "CONTRATOS.CSV", PRIMEIRO_DIA,
        [_contrato("101"), _contrato("102", CPF)],
    )  # fmt: skip
    _guardar(
        banco,
        ce.RJ_SANCOES,
        "FORNECEDOR_SANCOES.CSV",
        PRIMEIRO_DIA,
        [_sancao(CPF), _sancao()],
    )
    _guardar(
        banco,
        ce.RJ_FORNECEDORES,
        "FORNECEDORES.CSV",
        PRIMEIRO_DIA,
        [_fornecedor(CPF), _fornecedor()],
    )
    _guardar(
        banco, ce.RJ_COMPRAS_DIRETAS, "COMPRAS_DIRETAS.CSV", PRIMEIRO_DIA,
        [_compra_direta("1", CPF), _compra_direta("2")],
    )  # fmt: skip
    _guardar_em(
        banco, ce.ES_CONTRATOS, ES.format("a", "contratos-2025.csv"), PRIMEIRO_DIA,
        [_contrato_es("1", CPF), _contrato_es("2")],
    )  # fmt: skip
    _guardar_em(
        banco, ce.ES_EMPENHOS, ES.format("b", "empenhos-2025.csv"), PRIMEIRO_DIA,
        [_empenho_es("1", CPF), _empenho_es("2")],
    )  # fmt: skip
    _montar(banco, tmp_path)
    texto = _texto_gravado(tmp_path)
    assert CPF not in texto and CPF[:9] not in texto
    arquivos = (
        (ce.RJ_CONTRATOS, "contratos"),
        (ce.RJ_SANCOES, "fornecedor_sancoes"),
        (ce.RJ_FORNECEDORES, "fornecedores"),
        (ce.RJ_COMPRAS_DIRETAS, "compras_diretas"),
        (ce.ES_CONTRATOS, "contratos-2025"),
        (ce.ES_EMPENHOS, "empenhos-2025"),
    )
    for spec, arquivo in arquivos:
        tabela = _tabela(tmp_path, spec, arquivo)
        assert len(tabela) == 1, spec.tabela  # a linha do CPF não entrou
        colunas = list(tabela.columns)
        assert not {"cpf", "nome", "fornecedor", "razao_social", "objeto"} & set(
            colunas
        )
        assert colunas == list(TABELAS[spec.tabela].colunas), spec.tabela


def test_grava_com_manifesto_e_contrato_aprovado(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(banco, ce.RJ_CONTRATOS, "CONTRATOS.CSV", PRIMEIRO_DIA, [_contrato("101")])
    _montar(banco, tmp_path)
    tabela = _tabela(tmp_path, ce.RJ_CONTRATOS, "contratos")
    assert len(tabela["origem_sha256"].iloc[0]) == 64
    assert tabela["versao_do_codigo"].iloc[0] == "0123abc"
    assert tabela["montado_em"].iloc[0] == AGORA.isoformat()
    assert parquets_sem_manifesto(tmp_path / "base") == []
    (manifesto,) = (tmp_path / "base").rglob("*.json")
    conferencia = json.loads(manifesto.read_text(encoding="utf-8"))
    assert conferencia["conferencia_do_contrato"]["aprovada"], manifesto.name


def test_sem_arquivo_novo_e_pulado_e_refazer_le_de_novo(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _guardar(banco, ce.RJ_CONTRATOS, "CONTRATOS.CSV", PRIMEIRO_DIA, [_contrato("101")])
    nome = "rj_contratos/contratos"
    _montar(banco, tmp_path)
    assert _montar(banco, tmp_path)[nome] == JA_MONTADO
    assert "retratos" in _montar(banco, tmp_path, refazer=True)[nome]


def test_sem_nada_guardado_nao_monta_nada(banco, tmp_path):
    assert _montar(banco, tmp_path) == {}


def test_coluna_que_a_fonte_tirou_e_erro_e_nao_coluna_vazia(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    sem_valor = {
        k: v for k, v in _contrato("101").items() if k != "valor total pago (r$)"
    }
    _guardar(banco, ce.RJ_CONTRATOS, "CONTRATOS.CSV", PRIMEIRO_DIA, [sem_valor])
    with pytest.raises(KeyError, match="valor total pago"):
        _montar(banco, tmp_path)


def test_o_nome_do_parquet_e_o_do_arquivo_da_fonte():
    assert ce.nome_do_arquivo(f"{SIGA}/CONTRATOS.CSV") == "contratos"
    assert ce.nome_do_arquivo(f"{SIGA}/FORNECEDOR_SANCOES.CSV") == "fornecedor_sancoes"
    assert ce.nome_do_arquivo(ES.format("a", "contratos-2025.csv")) == "contratos-2025"


def test_comando_monta_as_tabelas_e_sai_com_1_sem_arquivo(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import carga_contratos_estaduais

    pasta = str(tmp_path / "b")
    assert carga_contratos_estaduais.main(["--pasta", pasta]) == 1
    _guardar(
        banco, ce.RJ_FORNECEDORES, "FORNECEDORES.CSV", PRIMEIRO_DIA, [_fornecedor()]
    )
    assert carga_contratos_estaduais.main(["--pasta", pasta]) == 0
    tabela = pd.read_parquet(
        tmp_path / "b" / "rj_fornecedores" / "fornecedores.parquet"
    )
    assert tabela["trata_como_pessoa"].all()  # sem a Receita guardada: o conservador


def test_a_publicacao_no_diario_oficial_e_fato_e_nao_a_data_em_que_a_base_soube():
    """Quem lê o contrato não pode cortar "como era em D" pelo `publicado_em` (o valor pago é de depois)."""
    from base.tempo import sinonimos_de_tempo

    sinonimos = sinonimos_de_tempo(TABELAS["rj_contratos"], "rj_contratos")
    assert sinonimos["publicado_em"] == "aconteceu_em"
    assert sinonimos["disponivel_em"] == "publico_em"


def test_o_historico_do_catalogo_comeca_no_dia_em_que_a_fonte_entrou():
    for spec in ce.TABELAS:
        assert TABELAS[spec.tabela].historico_desde == "2026-11-25"


def test_as_formas_de_numero_das_fontes_viram_o_valor_certo():
    """As formas vistas nos arquivos de 25/11/2026: milhar com vírgula, só centavos, inteiro sem ponto, vazio."""
    valores = ce.reais(pd.Series(["1.234,50", ",5", "1000", "59,64", ""]))
    assert valores[:4].tolist() == [1234.5, 0.5, 1000.0, 59.64]
    assert pd.isna(valores[4])


def test_dois_empenhos_do_mesmo_contrato_sao_duas_linhas(banco, tmp_path, monkeypatch):
    """O `Id` do arquivo de empenhos é do empenho: o mesmo contrato com dois empenhos dá duas linhas."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    segundo = {**_empenho_es("11"), "numeroempenho": "2025NE00002"}
    _guardar_em(
        banco,
        ce.ES_EMPENHOS,
        ES.format("c", "empenhos-2025.csv"),
        PRIMEIRO_DIA,
        [_empenho_es("10"), segundo],
    )
    resumo = _montar(banco, tmp_path)["es_empenhos/empenhos-2025"]
    assert resumo["id_repetido"] == 0
    tabela = _tabela(tmp_path, ce.ES_EMPENHOS, "empenhos-2025")
    assert sorted(tabela["empenho"]) == ["2025NE00001", "2025NE00002"]
