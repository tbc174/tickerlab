"""DMPL "como era na data" (série T1): a mutação do patrimônio líquido tem uma coluna a mais
(`COLUNA_DF`: capital social, reservas, lucros acumulados...), por isso é uma tabela própria, com a
coluna no fato. As regras de data são as mesmas das outras demonstrações."""

import io
import zipfile

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base.contas_cvm import COLUNAS
from base.dmpl import (
    COLUNAS_DA_DMPL,
    FORMATO_DMPL,
    coluna_canonica,
    ler_dmpl,
    publicadas_do_enet,
)
from base.ponto_no_tempo import (
    com_divulgacao,
    como_era_em,
    conferir_pasta,
    gravar_parquet,
    ler_parquet,
    montar_base,
)

A = "11.111.111/0001-11"
SEM_CADASTRO = pd.DataFrame(columns=["cnpj", "registro", "cancelamento"])
CABECALHO = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;"
    "DT_INI_EXERC;DT_FIM_EXERC;COLUNA_DF;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA"
)


def _linha_csv(coluna, valor="100.0000000000", conta="5.01", ordem="ÚLTIMO"):
    return (
        f"{A};2023-12-31;1;EMPRESA A;012345;DF Consolidado - Demonstração das Mutações do "
        f"Patrimônio Líquido;REAL;MIL;{ordem};2023-01-01;2023-12-31;{coluna};{conta};"
        f"Saldos Iniciais;{valor};S"
    )


def _zip(arquivos):
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        for nome, linhas in arquivos.items():
            z.writestr(nome, "\n".join(linhas).encode("latin-1"))
    return saida.getvalue()


# --- coluna canônica --------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("texto", "canonica"),
    [
        ("Capital Social Integralizado", "capital_social"),
        ("Capital Social", "capital_social"),
        (
            "Reservas de Capital, Opções Outorgadas e Ações em Tesouraria",
            "reservas_de_capital",
        ),
        (
            "Reservas de Capital, Outorgadas em Ações em Tesouraria",
            "reservas_de_capital",
        ),
        ("Reservas de Lucro", "reservas_de_lucro"),
        ("Lucros ou Prejuízos Acumulados", "lucros_acumulados"),
        ("Lucros/Prejuízos Acumulados", "lucros_acumulados"),
        ("Lucro / Prejuízo Acumulado", "lucros_acumulados"),
        ("Outros Resultados Abrangentes", "outros_resultados_abrangentes"),
        ("Ajustes Avaliação Patrimonial", "ajustes_de_avaliacao_patrimonial"),
        ("Ajustes de Avaliação Patrimonial", "ajustes_de_avaliacao_patrimonial"),
        ("Reservas de Reavaliação", "reservas_de_reavaliacao"),
        ("Patrimônio Líquido", "patrimonio_liquido"),
        ("Total do Patrimônio Líquido", "patrimonio_liquido"),
        ("Patrimônio Líquido - Acionistas Controladores", "patrimonio_liquido"),
        ("Participação dos Não Controladores", "nao_controladores"),
        ("Patrimônio Líquido - Acionistas Não Controladores", "nao_controladores"),
        ("Patrimônio Líquido Consolidado", "patrimonio_liquido_consolidado"),
        ("Total do Patrimônio Líquido Consolidado", "patrimonio_liquido_consolidado"),
        ("", "sem_coluna"),
        ("Ações em Tesouraria (nova)", "acoes_em_tesouraria_nova"),
    ],
)
def test_coluna_canonica(texto, canonica):
    assert coluna_canonica(texto) == canonica


# --- leitura dos dados abertos ------------------------------------------------------------------------
def test_le_a_dmpl_com_a_coluna_e_o_valor_em_reais():
    zip_bytes = _zip(
        {
            "dfp_cia_aberta_DMPL_con_2023.csv": [
                CABECALHO,
                _linha_csv("Capital Social Integralizado"),
                _linha_csv("Patrimônio Líquido", "250.0000000000"),
                _linha_csv("Patrimônio Líquido", "250.0000000000"),  # repetida idêntica
            ],
            # outras demonstrações não entram aqui
            "dfp_cia_aberta_DRE_con_2023.csv": ["CNPJ_CIA;DT_REFER"],
        }
    )
    dmpl = ler_dmpl(zip_bytes, "DFP")
    assert list(dmpl.columns) == list(COLUNAS_DA_DMPL) == [*COLUNAS, "coluna"]
    assert dmpl.set_index("coluna")["valor"].to_dict() == {
        "capital_social": 100_000.0,
        "patrimonio_liquido": 250_000.0,
    }
    assert set(dmpl["demonstracao"]) == {"DMPL"} and set(dmpl["grupo"]) == {"con"}
    assert set(dmpl["inicio"]) == {pd.Timestamp("2023-01-01")}


def test_zip_sem_dmpl_devolve_tabela_vazia_com_as_colunas():
    dmpl = ler_dmpl(_zip({"dfp_cia_aberta_2023.csv": ["CNPJ_CIA"]}), "DFP")
    assert dmpl.empty and list(dmpl.columns) == list(COLUNAS_DA_DMPL)


# --- como era na data -----------------------------------------------------------------------------------
def _dmpl(valor, divulgado_em, coluna="patrimonio_liquido", versao=1, documento="DFP"):
    referencia = pd.Timestamp("2023-12-31" if documento == "DFP" else "2023-06-30")
    return {
        "cnpj": A,
        "empresa": "EMPRESA A",
        "documento": documento,
        "referencia": referencia,
        "versao": versao,
        "demonstracao": "DMPL",
        "grupo": "con",
        "ordem": "ultimo",
        "inicio": pd.Timestamp("2023-01-01"),
        "fim": referencia,
        "conta": "5.07",
        "descricao": "Saldos Finais",
        "conta_fixa": True,
        "valor": valor,
        "coluna": coluna,
        "divulgado_em": pd.Timestamp(divulgado_em),
        "origem": "dados_abertos",
    }


def test_cada_coluna_e_um_fato():
    base = montar_base(
        pd.DataFrame(
            [
                _dmpl(800.0, "2024-03-01"),
                _dmpl(1000.0, "2024-03-01", coluna="capital_social"),
            ]
        ),
        formato=FORMATO_DMPL,
    )
    assert len(base) == 2
    assert list(base.columns) == list(FORMATO_DMPL.colunas_da_base)
    assert base["ate"].isna().all()


def test_itr_versao_2_so_vale_a_partir_da_propria_divulgacao():
    base = montar_base(
        pd.DataFrame(
            [
                _dmpl(800.0, "2023-08-10", documento="ITR"),
                _dmpl(780.0, "2023-09-20", versao=2, documento="ITR"),
            ]
        ),
        formato=FORMATO_DMPL,
    )
    assert como_era_em(base, "2023-09-19")["valor"].tolist() == [800.0]
    assert como_era_em(base, "2023-09-20")["valor"].tolist() == [780.0]


def test_com_divulgacao_guarda_a_coluna():
    contas = pd.DataFrame([_dmpl(800.0, "2024-03-01")]).drop(
        columns=["divulgado_em", "origem"]
    )
    indice = pd.DataFrame(
        {
            "cnpj": [A],
            "referencia": [pd.Timestamp("2023-12-31")],
            "versao": [1],
            "recebido_em": [pd.Timestamp("2024-03-01")],
        }
    )
    publicadas = com_divulgacao(
        contas, indice, "dados_abertos", cadastro=SEM_CADASTRO, formato=FORMATO_DMPL
    )
    assert publicadas["coluna"].tolist() == ["patrimonio_liquido"]
    assert publicadas["divulgado_em"].tolist() == [pd.Timestamp("2024-03-01")]


def test_publicadas_do_enet_trazem_a_dmpl_com_a_data_da_versao():
    from base.enet import ler_xml_enet
    from tests.test_base_enet import _dfp
    from tests.test_base_ponto_no_tempo import _indice_do_brb

    publicadas = publicadas_do_enet(
        [ler_xml_enet(_dfp(versao=1))], _indice_do_brb(), cadastro=SEM_CADASTRO
    )
    assert set(publicadas["origem"]) == {"enet"}
    assert "patrimonio_liquido" in set(publicadas["coluna"])
    assert set(publicadas["divulgado_em"]) == {pd.Timestamp("2023-03-10")}


def test_parquet_da_dmpl_volta_igual_e_confere(tmp_path):
    base = montar_base(
        pd.DataFrame(
            [_dmpl(800.0, "2024-03-01"), _dmpl(810.0, "2024-04-01", versao=2)]
        ),
        formato=FORMATO_DMPL,
    )
    gravar_parquet(base, tmp_path, formato=FORMATO_DMPL)
    de_volta = ler_parquet(tmp_path, formato=FORMATO_DMPL)
    pd.testing.assert_frame_equal(
        de_volta.sort_values("divulgado_em").reset_index(drop=True),
        base.sort_values("divulgado_em").reset_index(drop=True),
        check_dtype=False,
    )
    assert conferir_pasta(tmp_path, formato=FORMATO_DMPL) == {"2023": True}


# --- sem olhar o futuro (propriedade) --------------------------------------------------------------------
PRIMEIRO_DIA = pd.Timestamp("2024-01-02")


@st.composite
def _publicacoes(desenho):
    quantas = desenho(st.integers(min_value=1, max_value=8))
    linhas = []
    for versao in range(1, quantas + 1):
        coluna = desenho(st.sampled_from(["capital_social", "patrimonio_liquido"]))
        valor = desenho(st.sampled_from([1.0, 2.0, float("nan")]))
        dia = PRIMEIRO_DIA + pd.Timedelta(days=desenho(st.integers(0, 20)))
        linhas.append(_dmpl(valor, dia, coluna=coluna, versao=versao))
    return pd.DataFrame(linhas)


@settings(max_examples=60, deadline=None)
@given(publicadas=_publicacoes(), dias=st.integers(0, 22))
def test_cortar_o_futuro_nao_muda_o_passado(publicadas, dias):
    dia = PRIMEIRO_DIA + pd.Timedelta(days=dias)
    inteira = como_era_em(montar_base(publicadas, formato=FORMATO_DMPL), dia)
    so_o_passado = publicadas[publicadas["divulgado_em"] <= dia]
    if so_o_passado.empty:
        assert inteira.empty
        return
    cortada = como_era_em(montar_base(so_o_passado, formato=FORMATO_DMPL), dia)

    def sem_ate(foto):
        return foto.drop(columns="ate").sort_values("coluna").reset_index(drop=True)

    pd.testing.assert_frame_equal(sem_ate(inteira), sem_ate(cortada))
