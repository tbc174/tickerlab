"""Catálogo de fatores candidatos: cada um com fórmula, referência e dado; nenhum medido."""

import importlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base.ponto_no_tempo import montar_base
from trader.base_local import DadoAusenteError
from trader.fatores import balanco as fb
from trader.fatores import catalogo as cat
from trader.fatores import preco as fp

RAIZ = Path(__file__).resolve().parents[1]
A = "11.111.111/0001-11"


# ---- catálogo ----


def test_todo_fator_tem_referencia_com_o_ano():
    for f in cat.FATORES:
        assert f.referencia and f.formula and f.familia, f.nome
        assert str(f.ano) in f.referencia, f.nome


def test_nomes_unicos_e_busca_por_nome():
    nomes = [f.nome for f in cat.FATORES]
    assert len(nomes) == len(set(nomes))
    assert cat.fator("accruals").ano == 1996
    with pytest.raises(ValueError, match="catálogo"):
        cat.fator("astrologia")


def test_dados_existem_no_mapa_de_fontes_e_as_fontes_existem():
    for f in cat.FATORES:
        assert f.dados and set(f.dados) <= set(cat.FONTES), f.nome
    for caminho in cat.FONTES.values():
        assert (RAIZ / caminho).is_file(), caminho


def test_funcao_declarada_existe_e_e_chamavel():
    for f in cat.FATORES:
        if f.funcao is None:
            continue
        modulo, nome = f.funcao.rsplit(".", 1)
        assert callable(getattr(importlib.import_module(modulo), nome)), f.funcao


def test_situacao_na_base_coerente_com_a_funcao():
    for f in cat.FATORES:
        assert f.na_base in cat.SITUACOES_NA_BASE, f.nome
        assert f.direcao in (cat.COMPRA_OS_MAIORES, cat.COMPRA_OS_MENORES), f.nome
        if f.na_base == "sim":
            assert f.funcao is not None, f.nome
        else:
            assert f.nota_da_base, f.nome


def test_nenhum_fator_foi_medido():
    """Medir um fator é tentativa da pesquisa: só depois do pré-registro, nunca marcado aqui à mão."""
    assert not any(f.medido for f in cat.FATORES)


def test_markdown_avisa_que_nada_foi_medido():
    texto = cat.catalogo_em_markdown()
    # o cabeçalho e uma linha por fator
    linhas = [linha for linha in texto.splitlines() if linha.startswith("| ")]
    assert len(linhas) == len(cat.FATORES) + 1
    assert "Nenhum fator foi medido" in texto


# ---- fatores de preço ----


def _precos(valores, inicio="2020-01-01"):
    return pd.Series(
        valores, index=pd.bdate_range(inicio, periods=len(valores)), dtype=float
    )


def test_momento_e_reversao_com_contas_a_mao():
    p = _precos(np.arange(1, fp.ANO + 2))  # P(t) = t + 1
    t = fp.ANO
    assert fp.momento_12_1(p).iloc[t] == pytest.approx((t - fp.MES + 1) / 1 - 1)
    assert fp.retorno_de_1_mes(p).iloc[t] == pytest.approx(
        (t + 1) / (t - fp.MES + 1) - 1
    )
    assert fp.momento_12_1(p).iloc[: fp.ANO].isna().all()


def test_volatilidade_de_serie_que_alterna():
    retornos = np.tile([0.01, -0.01], fp.ANO)
    p = _precos(100 * np.cumprod(1 + retornos))
    vol = fp.volatilidade_de_12_meses(p)
    esperado = pd.Series(retornos).iloc[-fp.ANO :].std() * np.sqrt(fp.ANO)
    assert vol.iloc[-1] == pytest.approx(esperado)
    assert vol.iloc[: fp.MINIMO_NA_JANELA].isna().all()


def test_beta_de_quem_anda_em_dobro_e_dois():
    rng = np.random.default_rng(3)
    m = rng.normal(0, 0.01, fp.ANO + 10)
    mercado = _precos(100 * np.cumprod(1 + m))
    ativo = _precos(100 * np.cumprod(1 + 2 * m))
    assert fp.beta_de_mercado(ativo, mercado).iloc[-1] == pytest.approx(2.0)


def test_beta_ignora_dia_sem_mercado_sem_preencher():
    rng = np.random.default_rng(4)
    m = rng.normal(0, 0.01, fp.ANO + 10)
    mercado = _precos(100 * np.cumprod(1 + m))
    ativo = _precos(100 * np.cumprod(1 + 2 * m))
    beta = fp.beta_de_mercado(ativo, mercado.drop(mercado.index[100]))
    assert beta.iloc[-1] == pytest.approx(2.0, rel=0.05)


def test_distancia_da_maxima():
    p = _precos(list(range(100, 100 + fp.ANO)) + [200.0])
    d = fp.distancia_da_maxima_de_52_semanas(p)
    assert d.iloc[-2] == 0.0  # na máxima
    assert d.iloc[-1] == pytest.approx(200 / (100 + fp.ANO - 1) - 1)


FATORES_DE_PRECO = [
    fp.momento_12_1,
    fp.retorno_de_1_mes,
    fp.volatilidade_de_12_meses,
    fp.distancia_da_maxima_de_52_semanas,
]


@settings(max_examples=25, deadline=None)
@given(
    semente=st.integers(0, 10_000),
    corte=st.integers(fp.ANO // 2, 2 * fp.ANO),
    indice_do_fator=st.integers(0, len(FATORES_DE_PRECO)),
)
def test_preco_cortar_o_futuro_nao_muda_o_passado(semente, corte, indice_do_fator):
    rng = np.random.default_rng(semente)
    p = _precos(100 * np.cumprod(1 + rng.normal(0, 0.02, 2 * fp.ANO + 50)))
    if indice_do_fator == len(FATORES_DE_PRECO):
        mercado = _precos(100 * np.cumprod(1 + rng.normal(0, 0.01, len(p))))

        def calcular(serie):
            return fp.beta_de_mercado(serie, mercado)
    else:
        calcular = FATORES_DE_PRECO[indice_do_fator]
    inteira = calcular(p).iloc[:corte]
    cortada = calcular(p.iloc[:corte])
    pd.testing.assert_series_equal(inteira, cortada, check_freq=False)


# ---- fatores de balanço ----


def _fato(conta, valor, divulgado_em, fim="2022-12-31", versao=1, saldo=False):
    fim = pd.Timestamp(fim)
    inicio = pd.NaT if saldo else fim - pd.DateOffset(years=1) + pd.Timedelta(days=1)
    return {
        "cnpj": A,
        "empresa": "EMPRESA",
        "grupo": "con",
        "demonstracao": "BPA" if saldo else ("DFC_MI" if conta == "6.01" else "DRE"),
        "conta": conta,
        "descricao": conta,
        "inicio": inicio,
        "fim": fim,
        "valor": valor,
        "documento": "DFP",
        "referencia": pd.Timestamp("2022-12-31"),
        "versao": versao,
        "ordem": "ultimo",
        "origem": "dados_abertos",
        "divulgado_em": pd.Timestamp(divulgado_em),
    }


def _dfp(divulgado_em="2023-03-17", ativo=1000.0, ativo_antes=800.0, versao=1):
    """Uma DFP de 2022: ativo de 2022 e de 2021 (o 'penúltimo'), resultado bruto, lucro e caixa."""
    return [
        _fato("1", ativo, divulgado_em, versao=versao, saldo=True),
        _fato(
            "1", ativo_antes, divulgado_em, fim="2021-12-31", versao=versao, saldo=True
        ),
        _fato("3.03", 300.0, divulgado_em, versao=versao),
        _fato("3.11", 120.0, divulgado_em, versao=versao),
        _fato("6.01", 70.0, divulgado_em, versao=versao),
    ]


def _base(linhas):
    return montar_base(pd.DataFrame(linhas))


def test_fatores_de_balanco_com_contas_a_mao():
    base = _base(_dfp())
    datas = pd.to_datetime(["2023-04-03"])
    assert fb.rentabilidade_bruta(base, datas, A).iloc[0] == pytest.approx(0.3)
    assert fb.accruals(base, datas, A).iloc[0] == pytest.approx((120 - 70) / 1000)
    assert fb.crescimento_do_ativo(base, datas, A).iloc[0] == pytest.approx(0.25)


def test_balanco_so_vale_no_dia_seguinte_a_entrega():
    base = _base(_dfp("2023-03-17"))
    datas = pd.to_datetime(["2023-03-17", "2023-03-18"])
    for calcular in (fb.rentabilidade_bruta, fb.accruals, fb.crescimento_do_ativo):
        serie = calcular(base, datas, A, aceitar_vazio=True)
        assert serie.isna().tolist() == [True, False], calcular.__name__
        with pytest.raises(DadoAusenteError):
            calcular(base, datas, A)


def test_crescimento_usa_o_ano_anterior_reapresentado_ja_publico():
    base = _base(_dfp("2023-03-17") + _dfp("2023-05-02", ativo_antes=500.0, versao=2))
    datas = pd.to_datetime(["2023-04-03", "2023-05-03"])
    assert fb.crescimento_do_ativo(base, datas, A).tolist() == pytest.approx(
        [0.25, 1.0]
    )


def test_crescimento_sem_o_ano_anterior_fica_vazio_declarado():
    base = _base([_fato("1", 1000.0, "2023-03-17", saldo=True)])
    datas = pd.to_datetime(["2023-04-03"])
    with pytest.raises(DadoAusenteError, match="dois anos"):
        fb.crescimento_do_ativo(base, datas, A)
    assert fb.crescimento_do_ativo(base, datas, A, aceitar_vazio=True).isna().all()


PRIMEIRO_DIA = pd.Timestamp("2023-03-01")


@settings(max_examples=40, deadline=None)
@given(
    entregas=st.lists(
        st.tuples(st.integers(0, 40), st.sampled_from([500.0, 800.0, 900.0])),
        min_size=1,
        max_size=4,
    ),
    dias=st.integers(0, 42),
)
def test_balanco_cortar_o_futuro_nao_muda_o_passado(entregas, dias):
    linhas = []
    for versao, (atraso, ativo_antes) in enumerate(entregas, start=1):
        dia = PRIMEIRO_DIA + pd.Timedelta(days=atraso)
        linhas += _dfp(dia, ativo_antes=ativo_antes, versao=versao)
    publicadas = pd.DataFrame(linhas)
    corte = PRIMEIRO_DIA + pd.Timedelta(days=dias)
    datas = pd.date_range(PRIMEIRO_DIA, corte + pd.Timedelta(days=1))
    passado = publicadas[publicadas["divulgado_em"] <= corte]
    for calcular in (fb.rentabilidade_bruta, fb.accruals, fb.crescimento_do_ativo):
        inteira = calcular(montar_base(publicadas), datas, A, aceitar_vazio=True)
        if passado.empty:
            assert inteira.isna().all()
            continue
        cortada = calcular(montar_base(passado), datas, A, aceitar_vazio=True)
        pd.testing.assert_series_equal(inteira, cortada)
