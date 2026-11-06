"""F-B3: a base que faltava (ações pelo FRE, DFP e ITR; episódios de recuperação judicial; preço
por ação para o valor de mercado), em ZIPs e tabelas sintéticos, sem internet."""

import io
import zipfile
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from tests.ajudantes_f_b3 import CNPJS, dados_sinteticos
from trader.estrategias import dados_f_b3
from trader.estrategias import fatores_b3 as fb
from trader.holdout import FIM_DO_DESENVOLVIMENTO

CNPJ = "11.111.111/0001-11"
OUTRO = "22.222.222/0001-22"
D = pd.Timestamp("2018-03-01")  # o dia do teste do valor em test_trader_fatores_b3.py
INDICE = "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC"
CAPITAL_DO_FRE = (
    "CNPJ_Companhia;Data_Referencia;Versao;ID_Documento;Nome_Companhia;ID_Capital_Social;"
    "Tipo_Capital;Data_Autorizacao_Aprovacao;Valor_Capital;Prazo_Integralizacao;"
    "Quantidade_Acoes_Ordinarias;Quantidade_Acoes_Preferenciais;Quantidade_Total_Acoes"
)
COMPOSICAO = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;QT_ACAO_ORDIN_CAP_INTEGR;QT_ACAO_PREF_CAP_INTEGR;"
    "QT_ACAO_TOTAL_CAP_INTEGR;QT_ACAO_ORDIN_TESOURO;QT_ACAO_PREF_TESOURO;QT_ACAO_TOTAL_TESOURO"
)


def _zip(arquivos: dict[str, list[str]]) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as pacote:
        for nome, linhas in arquivos.items():
            pacote.writestr(nome, "\n".join(linhas).encode("latin-1"))
    return saida.getvalue()


def _fre(ano: int, capital: list[str], indice: list[str]) -> bytes:
    return _zip(
        {
            f"fre_cia_aberta_{ano}.csv": [INDICE, *indice],
            f"fre_cia_aberta_capital_social_{ano}.csv": [CAPITAL_DO_FRE, *capital],
            f"fre_cia_aberta_capital_social_aumento_{ano}.csv": ["x;y", "1;2"],
        }
    )


def _itr(ano: int, composicao: list[str], indice: list[str]) -> bytes:
    return _zip(
        {
            f"itr_cia_aberta_{ano}.csv": [INDICE, *indice],
            f"itr_cia_aberta_composicao_capital_{ano}.csv": [COMPOSICAO, *composicao],
        }
    )


def _linha_do_indice(cnpj, versao, id_doc, recebido, referencia="2015-01-01"):
    return f"{cnpj};{referencia};{versao};EMPRESA;1;FRE;{id_doc};{recebido};link"


def _linha_do_capital(cnpj, id_doc, tipo, aprovado, total):
    return f"{cnpj};2015-01-01;3;{id_doc};EMPRESA;9;{tipo};{aprovado};1.00;;{total};0;{total}"


# --- ações ---------------------------------------------------------------------------------------------


def test_fre_usa_o_capital_integralizado_e_o_dia_em_que_a_cvm_recebeu_a_versao():
    conteudo = _fre(
        2015,
        capital=[
            _linha_do_capital(CNPJ, "30", "Capital Autorizado", "2015-06-01", 999),
            _linha_do_capital(CNPJ, "30", "Capital Integralizado", "2015-02-01", 100),
            _linha_do_capital(CNPJ, "30", "Capital Integralizado", "2015-06-01", 150),
        ],
        indice=[
            _linha_do_indice(CNPJ, 1, "10", "2015-05-29"),
            _linha_do_indice(CNPJ, 3, "30", "2015-11-20"),
        ],
    )
    tabela = dados_f_b3.acoes_do_fre(conteudo)
    assert tabela.to_dict("records") == [
        {
            "cnpj": CNPJ,
            "quantidade": 150.0,
            "disponivel_em": pd.Timestamp("2015-11-20"),
        }
    ]


def test_itr_liga_cada_versao_ao_dia_em_que_foi_recebida():
    conteudo = _itr(
        2021,
        composicao=[
            f"{CNPJ};2021-03-31;1;EMPRESA;60;40;100;0;0;5",
            f"{CNPJ};2021-06-30;2;EMPRESA;60;60;120;0;0;5",
        ],
        indice=[
            _linha_do_indice(CNPJ, 1, "1", "2021-05-14", "2021-03-31"),
            _linha_do_indice(CNPJ, 1, "2", "2021-08-13", "2021-06-30"),
            _linha_do_indice(CNPJ, 2, "3", "2021-09-01", "2021-06-30"),
        ],
    )
    tabela = dados_f_b3.acoes_da_dfp_ou_itr(conteudo)
    assert tabela["quantidade"].tolist() == [100.0, 120.0]  # sem descontar a tesouraria
    assert tabela["disponivel_em"].tolist() == [
        pd.Timestamp("2021-05-14"),
        pd.Timestamp("2021-09-01"),  # a versão 2, não a 1
    ]


def test_arquivo_sem_composicao_do_capital_nao_traz_acoes():
    antigo = _zip(
        {
            "itr_cia_aberta_2015.csv": [
                INDICE,
                _linha_do_indice(CNPJ, 1, "1", "2015-05-14"),
            ]
        }
    )
    tabela = dados_f_b3.acoes_da_dfp_ou_itr(antigo)
    assert tabela.empty
    assert list(tabela.columns) == list(fb.COLUNAS_DAS_ACOES)


def test_montar_acoes_corta_o_holdout_tira_zeros_e_a_dfp_vence_o_fre_no_mesmo_dia():
    depois = (FIM_DO_DESENVOLVIMENTO + pd.Timedelta(days=1)).date().isoformat()
    fre = _fre(
        2021,
        capital=[
            _linha_do_capital(CNPJ, "1", "Capital Integralizado", "2021-01-01", 100),
            _linha_do_capital(OUTRO, "2", "Capital Integralizado", "2021-01-01", 0),
        ],
        indice=[
            _linha_do_indice(CNPJ, 1, "1", "2021-05-14"),
            _linha_do_indice(OUTRO, 1, "2", "2021-05-14"),
        ],
    )
    itr = _itr(
        2021,
        composicao=[
            f"{CNPJ};2021-03-31;1;EMPRESA;0;0;130;0;0;0",
            f"{CNPJ};2023-06-30;1;EMPRESA;0;0;140;0;0;0",
        ],
        indice=[
            _linha_do_indice(CNPJ, 1, "7", "2021-05-14", "2021-03-31"),
            _linha_do_indice(CNPJ, 1, "8", depois, "2023-06-30"),
        ],
    )
    tabela = dados_f_b3.montar_acoes([fre], [itr])
    assert tabela.to_dict("records") == [
        {
            "cnpj": CNPJ,
            "quantidade": 130.0,
            "disponivel_em": pd.Timestamp("2021-05-14"),
        }
    ]


def test_gravar_acoes_le_as_duas_pastas(tmp_path):
    pasta_do_fre, pasta_da_cvm = tmp_path / "fre" / "2026", tmp_path / "cvm"
    pasta_do_fre.mkdir(parents=True)
    pasta_da_cvm.mkdir()
    (pasta_do_fre / "abc.zip").write_bytes(
        _fre(
            2012,
            [_linha_do_capital(CNPJ, "1", "Capital Integralizado", "2012-01-01", 10)],
            [_linha_do_indice(CNPJ, 1, "1", "2012-05-30")],
        )
    )
    (pasta_da_cvm / "itr_cia_aberta_2020.zip").write_bytes(
        _itr(
            2020,
            [f"{CNPJ};2020-03-31;1;EMPRESA;0;0;20;0;0;0"],
            [_linha_do_indice(CNPJ, 1, "2", "2020-05-15", "2020-03-31")],
        )
    )
    destino = dados_f_b3.gravar_acoes(
        tmp_path / "fre", pasta_da_cvm, tmp_path / "acoes.parquet"
    )
    assert pd.read_parquet(destino)["quantidade"].tolist() == [10.0, 20.0]


# --- recuperação judicial ------------------------------------------------------------------------------


def _insolvencia(linhas):
    return pd.DataFrame(linhas, columns=["cnpj", "rotulo", "conhecido_em"])


def test_doze_meses_sem_documento_fecham_o_episodio():
    tabela = dados_f_b3.episodios_de_recuperacao_judicial(
        _insolvencia(
            [
                (CNPJ, "recuperacao_judicial", "2014-10-15"),
                (CNPJ, "recuperacao_judicial", "2015-09-23"),
                (CNPJ, "recuperacao_judicial", "2017-03-01"),  # 17 meses depois: outro
                (OUTRO, "recuperacao_judicial_ou_extrajudicial", "2016-01-04"),
                (OUTRO, "recuperacao_extrajudicial", "2012-01-04"),
                (OUTRO, "exposicao_a_terceiro", "2011-01-04"),
                (OUTRO, "falencia", "2013-01-04"),
            ]
        )
    )
    assert tabela.to_dict("records") == [
        {
            "cnpj": CNPJ,
            "inicio": pd.Timestamp("2014-10-15"),
            "fim": pd.Timestamp("2016-09-23"),
        },
        {
            "cnpj": CNPJ,
            "inicio": pd.Timestamp("2017-03-01"),
            "fim": pd.Timestamp("2018-03-01"),
        },
        {
            "cnpj": OUTRO,
            "inicio": pd.Timestamp("2016-01-04"),
            "fim": pd.Timestamp("2017-01-04"),
        },
    ]


def test_documento_depois_do_desenvolvimento_nao_entra():
    depois = FIM_DO_DESENVOLVIMENTO + pd.Timedelta(days=1)
    tabela = dados_f_b3.episodios_de_recuperacao_judicial(
        _insolvencia([(CNPJ, "recuperacao_judicial", depois)])
    )
    assert tabela.empty
    assert list(tabela.columns) == list(dados_f_b3.COLUNAS_DA_RECUPERACAO)


def _em_recuperacao(tabela: pd.DataFrame, dia: pd.Timestamp) -> bool:
    dados = replace(dados_sinteticos(), recuperacao_judicial=tabela)
    return CNPJ in fb._em_recuperacao_judicial(dados, dia)


@pytest.mark.parametrize("semente", range(5))
def test_cortar_o_futuro_nao_muda_quem_esta_em_recuperacao(semente):
    """No dia D, a tabela com tudo e a tabela só com o que a CVM recebeu até D dizem o mesmo."""
    gerador = np.random.default_rng(semente)
    dias = pd.Timestamp("2012-01-02") + pd.to_timedelta(
        np.sort(gerador.integers(0, 3000, size=25)), unit="D"
    )
    insolvencia = _insolvencia([(CNPJ, "recuperacao_judicial", d) for d in dias])
    inteira = dados_f_b3.episodios_de_recuperacao_judicial(insolvencia)
    for dia in pd.date_range("2012-01-02", "2020-12-31", freq="17D"):
        ate_o_dia = dados_f_b3.episodios_de_recuperacao_judicial(insolvencia, ate=dia)
        recente = ((dias <= dia) & (dias > dia - pd.DateOffset(months=12))).any()
        assert (
            _em_recuperacao(inteira, dia) == _em_recuperacao(ate_o_dia, dia) == recente
        )


def test_ler_insolvencia_junta_os_anos_ate_o_ultimo(tmp_path):
    pasta = tmp_path / "insolvencia"
    pasta.mkdir()
    for ano in (2008, 2023, 2024):
        _insolvencia([(CNPJ, "recuperacao_judicial", f"{ano}-05-01")]).to_parquet(
            pasta / f"{ano}.parquet"
        )
    _insolvencia([(CNPJ, "recuperacao_judicial", "2010-05-01")]).to_parquet(
        pasta / "2010.v1.parquet"  # a versão anterior da base não entra
    )
    tabela = dados_f_b3.ler_insolvencia(tmp_path)
    assert sorted(tabela["conhecido_em"]) == ["2008-05-01", "2023-05-01"]


# --- preço por ação e valor da firma -------------------------------------------------------------------


def _longo():
    dias = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
    linhas = [
        (dias[0], "XXXX3", 10.0, 1e6),
        (dias[0], "XXXX4", 11.0, 5e6),
        (dias[0], "XXXX11", 32.0, 9e7),  # a unit, a mais líquida, não entra
        (dias[1], "XXXX3", 10.5, 2e6),  # sem negócio na PN: vale a ON do dia
        (dias[0], "YYYY3", 7.0, 1e5),
    ]
    longo = pd.DataFrame(linhas, columns=["data", "ticker", "fechamento", "volume"])
    cadastro = pd.DataFrame(
        {
            "cnpj": [CNPJ, CNPJ, CNPJ, OUTRO],
            "classe": ["ON", "PN", "UNT", "ON"],
        },
        index=["XXXX3", "XXXX4", "XXXX11", "YYYY3"],
    )
    return longo, cadastro, pd.DatetimeIndex(dias)


def test_preco_por_acao_e_o_da_on_ou_pn_mais_negociada_e_nunca_o_da_unit():
    longo, cadastro, dias = _longo()
    preco = dados_f_b3.preco_por_acao(longo, cadastro, dias)
    assert preco[CNPJ].tolist() == [11.0, 10.5, 10.5]  # o último dia repete o anterior
    assert preco[OUTRO].tolist() == [7.0, 7.0, 7.0]


def test_preco_por_acao_nao_olha_o_futuro():
    longo, cadastro, dias = _longo()
    inteiro = dados_f_b3.preco_por_acao(longo, cadastro, dias)
    cortado = dados_f_b3.preco_por_acao(
        longo[longo["data"] <= dias[1]], cadastro, dias[:2]
    )
    pd.testing.assert_frame_equal(inteiro.iloc[:2], cortado)


def test_valor_da_firma_usa_o_preco_bruto_de_uma_acao_quando_existe():
    dados = dados_sinteticos()
    bruto = pd.DataFrame(
        {cnpj: 2.0 * dados.fechamento[t] for t, cnpj in CNPJS.items()},
        index=dados.fechamento.index,
    )
    com_bruto = replace(dados, preco_por_acao=bruto)
    fatores = fb.fatores_em(D, com_bruto, ["AAA3"])
    valor_da_firma = 1e7 * bruto.loc[D, CNPJS["AAA3"]] + 1e8 - 2e7
    assert fatores.loc["AAA3", "valor"] == pytest.approx(1e8 / valor_da_firma)


def test_preco_por_acao_precisa_das_datas_do_fechamento():
    dados = dados_sinteticos()
    curto = pd.DataFrame({CNPJS["AAA3"]: 1.0}, index=dados.fechamento.index[:-1])
    with pytest.raises(ValueError, match="preco_por_acao"):
        fb._conferir_entradas(replace(dados, preco_por_acao=curto))


def test_cortar_corta_o_preco_por_acao():
    dados = dados_sinteticos()
    bruto = pd.DataFrame({CNPJS["AAA3"]: 1.0}, index=dados.fechamento.index)
    cortado = fb.cortar(replace(dados, preco_por_acao=bruto), D)
    assert cortado.preco_por_acao is not None
    assert cortado.preco_por_acao.index.max() == D


# --- correção da unidade da quantidade -----------------------------------------------------------------

DIAS = pd.bdate_range("2021-01-04", periods=60)


def _documentos(*linhas):
    return pd.DataFrame(
        [(CNPJ, q, DIAS[i]) for i, q in linhas], columns=list(fb.COLUNAS_DAS_ACOES)
    )


def _painel(valores):
    return pd.DataFrame({CNPJ: valores}, index=DIAS)


SEM_VOLUME = pd.DataFrame(index=DIAS)


def _corrigir(documentos, preco, negociado=SEM_VOLUME):
    tabela = dados_f_b3.corrigir_quantidade(documentos, preco, negociado)
    return tabela["quantidade"].tolist()


def test_balanco_em_milhares_volta_para_a_escala_do_anterior():
    preco = _painel(10.0)
    assert _corrigir(_documentos((0, 1e9), (20, 1e6), (40, 1.1e9)), preco) == [
        1e9,
        1e9,
        1.1e9,
    ]


def test_desdobramento_de_verdade_fica_como_veio():
    preco = _painel([20.0] * 30 + [2.0] * 30)  # o preço cai dez vezes no dia 30
    assert _corrigir(_documentos((0, 1e8), (35, 1e9)), preco) == [1e8, 1e9]


def test_sem_preco_o_salto_de_potencia_de_dez_e_unidade():
    assert _corrigir(_documentos((0, 5e8), (20, 5e5)), pd.DataFrame(index=DIAS)) == [
        5e8,
        5e8,
    ]


def test_mudanca_que_nao_e_potencia_de_dez_fica():
    assert _corrigir(_documentos((0, 1e8), (20, 1.3e8)), _painel(10.0)) == [1e8, 1.3e8]


def test_giro_impossivel_poe_a_serie_em_unidades_desde_o_primeiro_documento():
    # 100 mil ações a R$ 10 = R$ 1 milhão, negociando R$ 10 milhões por dia: veio em milhares
    negociado = _painel(1e7)
    assert _corrigir(
        _documentos((0, 1e5), (20, 1.02e8), (40, 1.03e5)), _painel(10.0), negociado
    ) == [1e8, 1.02e8, 1.03e8]


def test_valor_de_mercado_acima_de_dois_trilhoes_esta_em_milesimos():
    assert _corrigir(_documentos((0, 1e12)), _painel(10.0)) == [1e9]


@pytest.mark.parametrize("corte", [10, 25, 45])
def test_corrigir_nao_olha_o_futuro(corte):
    documentos = _documentos((0, 1e5), (15, 1e8), (30, 1e11), (50, 2e8))
    preco = _painel(np.linspace(10, 30, len(DIAS)))
    negociado = _painel(1e7)
    inteira = dados_f_b3.corrigir_quantidade(documentos, preco, negociado)
    dia = DIAS[corte]
    cortada = dados_f_b3.corrigir_quantidade(
        documentos[documentos["disponivel_em"] <= dia], preco[:dia], negociado[:dia]
    )
    pd.testing.assert_frame_equal(
        inteira[inteira["disponivel_em"] <= dia].reset_index(drop=True), cortada
    )


def test_volume_por_empresa_soma_os_tickers_do_cnpj_na_janela():
    volume = pd.DataFrame({"XXXX3": 1.0, "XXXX4": 2.0, "YYYY3": np.nan}, index=DIAS)
    cadastro = pd.DataFrame(
        {"cnpj": [CNPJ, CNPJ, OUTRO]}, index=["XXXX3", "XXXX4", "YYYY3"]
    )
    medio = dados_f_b3.volume_por_empresa(volume, cadastro)
    janela = fb.PREGOES_DA_LIQUIDEZ
    assert medio[CNPJ].iloc[janela - 1 :].eq(3.0).all()
    assert medio[CNPJ].iloc[0] == pytest.approx(3.0 / janela)
    assert medio[OUTRO].eq(0.0).all()
