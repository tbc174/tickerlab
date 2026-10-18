"""Release × documento oficial: a comparação do que a empresa disse com o que entregou à CVM."""

import pandas as pd
import pytest

from base import release_x_oficial as rxo

CNPJ = "11.111.111/0001-11"


def _leitura(
    valor, unidade="milhoes", periodo="trimestre", linha="receita_liquida", **extra
):
    base = {
        "cnpj": CNPJ, "protocolo": "P1", "versao": 1, "periodo": "3T25",
        "referencia": pd.Timestamp("2025-09-30"), "data_entrega": pd.Timestamp("2025-11-05"),
        "link": "https://www.rad.cvm.gov.br/x.pdf",
        "linha": linha, "valor": valor, "unidade": unidade, "periodo_lido": periodo,
        "modelo": "claude-haiku-5-5", "versao_do_guia": "v1", "sha256_do_documento": "ab",
    }  # fmt: skip
    return base | extra


def _oficial(valor, inicio="2025-07-01", fim="2025-09-30", conta="3.01", grupo="con",
             divulgado_em="2025-11-05", ate=None, documento="ITR", versao=1,
             descricao="Receita de Venda de Bens e/ou Serviços"):  # fmt: skip
    return {
        "cnpj": CNPJ, "grupo": grupo, "demonstracao": "DRE", "conta": conta,
        "descricao": descricao, "inicio": pd.Timestamp(inicio), "fim": pd.Timestamp(fim),
        "valor": float(valor), "documento": documento, "versao": versao, "ordem": "ultimo",
        "divulgado_em": pd.Timestamp(divulgado_em),
        "ate": pd.Timestamp(ate) if ate else pd.NaT,
    }  # fmt: skip


def _comparar(leituras, oficiais):
    return rxo.comparar(pd.DataFrame(leituras), pd.DataFrame(oficiais))


def test_normaliza_milhoes_e_mil():
    # R$ 1.234,5 milhões × 1.234.512 mil: a diferença cabe na meia casa que o release mostra
    r = _comparar([_leitura(1234.5)], [_oficial(1_234_512_000)]).iloc[0]
    assert r["classe"] == rxo.IGUAL_ARREDONDADO
    assert r["valor_release_reais"] == pytest.approx(1_234_500_000)
    assert r["diferenca_reais"] == pytest.approx(-12_000)


def test_igual_exato_e_diferente_com_a_diferenca():
    igual = _comparar([_leitura(1234.5)], [_oficial(1_234_500_000)]).iloc[0]
    assert igual["classe"] == rxo.IGUAL
    r = _comparar([_leitura(1300.0)], [_oficial(1_234_500_000)]).iloc[0]
    assert r["classe"] == rxo.DIFERENTE
    assert r["diferenca_reais"] == pytest.approx(65_500_000)
    assert r["diferenca_pct"] == pytest.approx(65.5 / 1234.5 * 100)


def test_unidade_sem_casas_tem_uma_unidade_de_tolerancia():
    # "R$ 1.235 milhões": o release soma parcelas arredondadas, então até 1 milhão de diferença é arredondamento
    r = _comparar([_leitura(1235.0)], [_oficial(1_234_200_000)]).iloc[0]
    assert r["classe"] == rxo.IGUAL_ARREDONDADO
    longe = _comparar([_leitura(1235.0)], [_oficial(1_236_500_000)]).iloc[0]
    assert longe["classe"] == rxo.DIFERENTE


def test_quarto_trimestre_e_o_ano_da_dfp_menos_os_nove_meses_do_itr():
    oficiais = [
        _oficial(1_000_000_000, inicio="2025-01-01", fim="2025-12-31", documento="DFP",
                 divulgado_em="2026-03-10"),
        _oficial(700_000_000, inicio="2025-01-01", fim="2025-09-30", divulgado_em="2025-11-05"),
    ]  # fmt: skip
    release = _leitura(
        300.0, referencia=pd.Timestamp("2025-12-31"),
        data_entrega=pd.Timestamp("2026-03-12"),
    )  # fmt: skip
    r = _comparar([release], oficiais).iloc[0]
    assert r["classe"] == rxo.IGUAL
    assert r["valor_oficial_reais"] == pytest.approx(300_000_000)
    assert r["documento"] == "DFP-ITR"


def test_quarto_trimestre_sem_o_itr_dos_nove_meses_fica_sem_itr():
    oficiais = [
        _oficial(1_000_000_000, inicio="2025-01-01", fim="2025-12-31", documento="DFP",
                 divulgado_em="2026-03-10"),
    ]  # fmt: skip
    release = _leitura(
        300.0, referencia=pd.Timestamp("2025-12-31"),
        data_entrega=pd.Timestamp("2026-03-12"),
    )  # fmt: skip
    assert _comparar([release], oficiais).iloc[0]["classe"] == rxo.SEM_ITR


def test_trimestre_contra_3_meses_e_acumulado_contra_9_meses():
    oficiais = [
        _oficial(100_000_000),  # 3 meses
        _oficial(900_000_000, inicio="2025-01-01"),  # 9 meses
    ]
    resultado = _comparar(
        [_leitura(100.0), _leitura(900.0, periodo="acumulado_no_ano")], oficiais
    ).set_index("periodo_lido")
    assert resultado.loc["trimestre", "classe"] == rxo.IGUAL
    assert resultado.loc["acumulado_no_ano", "classe"] == rxo.IGUAL


def test_ano_contra_o_exercicio_da_dfp():
    referencia = pd.Timestamp("2025-12-31")
    oficial = _oficial(
        5_000_000_000, inicio="2025-01-01", fim="2025-12-31", documento="DFP"
    )
    leitura = _leitura(
        5.0, unidade="bilhoes", periodo="ano", referencia=referencia, periodo_lido="ano"
    )
    r = _comparar([leitura], [oficial]).iloc[0]
    assert r["classe"] == rxo.IGUAL
    assert r["documento"] == "DFP"


def test_usa_consolidado_e_cai_no_individual():
    com_consolidado = _comparar(
        [_leitura(100.0)], [_oficial(100_000_000), _oficial(40_000_000, grupo="ind")]
    ).iloc[0]
    assert com_consolidado["grupo"] == "con"
    assert com_consolidado["classe"] == rxo.IGUAL
    so_individual = _comparar(
        [_leitura(40.0)], [_oficial(40_000_000, grupo="ind")]
    ).iloc[0]
    assert so_individual["grupo"] == "ind"
    assert so_individual["classe"] == rxo.IGUAL


def test_compara_com_a_versao_da_data_do_release():
    # a v1 valia no dia do release; a reapresentação veio depois e não pode mudar a conta
    oficiais = [
        _oficial(100_000_000, ate="2026-03-01"),
        _oficial(90_000_000, versao=2, divulgado_em="2026-03-01"),
    ]
    r = _comparar([_leitura(100.0)], oficiais).iloc[0]
    assert r["classe"] == rxo.IGUAL
    assert r["documento_versao"] == 1


def test_itr_entregue_depois_do_release_vale_e_a_tabela_so_fica_pronta_nele():
    oficial = _oficial(100_000_000, divulgado_em="2025-11-10")
    r = _comparar([_leitura(100.0)], [oficial]).iloc[0]
    assert r["classe"] == rxo.IGUAL
    assert r["disponivel_em"] == pd.Timestamp("2025-11-10")


def test_disponivel_em_e_a_data_mais_nova_entre_release_e_itr():
    r = _comparar(
        [_leitura(100.0)], [_oficial(100_000_000, divulgado_em="2025-11-03")]
    ).iloc[0]
    assert r["disponivel_em"] == pd.Timestamp("2025-11-05")


def test_classes_sem_itr_e_release_nao_mostra():
    leituras = [_leitura(100.0), _leitura(10.0, linha="lucro_liquido_controladores")]
    oficiais = [
        _oficial(100_000_000),
        # o release não traz o resultado operacional, mas o ITR traz
        _oficial(
            7_000_000,
            conta="3.05",
            descricao="Resultado Antes do Resultado Financeiro e dos Tributos",
        ),
    ]
    resultado = _comparar(leituras, oficiais).set_index("linha")["classe"].to_dict()
    assert resultado["receita_liquida"] == rxo.IGUAL
    assert resultado["lucro_liquido_controladores"] == rxo.SEM_ITR
    assert resultado["resultado_operacional"] == rxo.RELEASE_NAO_MOSTRA


def test_empresa_sem_nada_no_itr_fica_sem_itr():
    outra = _oficial(1_000, fim="2024-09-30", inicio="2024-07-01")
    r = _comparar([_leitura(100.0)], [outra]).iloc[0]
    assert r["classe"] == rxo.SEM_ITR
    assert pd.isna(r["valor_oficial_reais"])


def test_so_a_conta_certa_vale():
    # 3.01 de banco ("Receitas da Intermediação...") vale; outra conta 3.01 qualquer não
    errada = _oficial(100_000_000, descricao="Outra coisa")
    r = _comparar([_leitura(100.0)], [errada]).iloc[0]
    assert r["classe"] == rxo.SEM_ITR


def test_so_ultimo_vale_e_o_ano_anterior_refeito_nao():
    refeito = _oficial(50_000_000) | {"ordem": "penultimo"}
    r = _comparar([_leitura(50.0)], [refeito]).iloc[0]
    assert r["classe"] == rxo.SEM_ITR


def test_tabela_tem_colunas_do_contrato_e_sem_texto_de_modelo():
    tabela = rxo.montar(
        pd.DataFrame([_leitura(100.0)]),
        pd.DataFrame([_oficial(100_000_000)]),
        agora=pd.Timestamp("2026-10-17", tz="UTC"),
    )
    assert list(tabela.columns) == list(rxo.COLUNAS)
    assert "trecho" not in tabela.columns
    assert tabela.iloc[0]["modelo"] == "claude-haiku-5-5"
    assert tabela.iloc[0]["disponivel_em"] == tabela.iloc[0]["publico_em"]


def test_gravar_cria_parquet_com_manifesto(tmp_path):
    n = rxo.gravar(
        pd.DataFrame([_leitura(100.0)]),
        pd.DataFrame([_oficial(100_000_000)]),
        tmp_path,
        pd.Timestamp("2026-10-17", tz="UTC"),
    )
    assert n == 1
    pasta = tmp_path / "release_x_oficial"
    assert (pasta / "release_x_oficial.parquet").exists()
    assert (pasta / "release_x_oficial.json").exists()


def test_dicionario_e_contrato_dizem_as_mesmas_colunas():
    from base.dicionario import TABELAS

    tabela = TABELAS["release_x_oficial"]
    assert tuple(tabela.colunas) == rxo.COLUNAS
    assert tabela.chaves == tuple(rxo.CHAVE)
    assert tabela.datas["publico_em"] == "publico_em"
    assert tabela.familia_da_fonte == "cvm"


def test_manifesto_tem_um_original_por_pdf_com_o_sha256(tmp_path):
    import json

    leituras = [_leitura(100.0), _leitura(10.0, linha="resultado_operacional")]
    rxo.gravar(
        pd.DataFrame(leituras),
        pd.DataFrame([_oficial(100_000_000)]),
        tmp_path,
        pd.Timestamp("2026-10-17", tz="UTC"),
    )
    manifesto = json.loads(
        (tmp_path / "release_x_oficial" / "release_x_oficial.json").read_text("utf-8")
    )
    assert [o["sha256"] for o in manifesto["origens"]] == ["ab"]
