"""Features de crédito ponto-no-tempo (B-30 do dossiê da plataforma, protótipo C, parte 1).

As contas com as demonstrações reais de 4 empresas (`tests/arquivos/cvm/fundamentos/`); o princípio
"cortar o futuro não muda o passado" por propriedade (Hypothesis), sobre demonstrações sintéticas com
datas de entrega sorteadas; e a conferência que derruba qualquer feature com `disponivel_em` depois
do dia da análise."""

import json
import random
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src import demonstracoes as dm
from src import fundamentos as fu
from src.banco import demonstracoes as repo
from src.banco.conexao import criar_engine, migrar_para
from src.banco.demonstracoes import DadosDaEmpresa
from src.credito import features as fc
from src.credito.dicionario import (
    DAS_DEMONSTRACOES,
    DICIONARIO,
    VERSAO_DAS_FEATURES,
    dicionario_como_lista,
)
from src.divida import capacidade as ca
from src.rastro import DocumentoUsado, Rastro

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
PETROBRAS, ITAU, WEG = "33.000.167/0001-01", "60.872.504/0001-23", "84.429.695/0001-11"
DIA = date(2026, 9, 30)


@pytest.fixture(scope="module")
def banco(tmp_path_factory):
    """Um SQLite com as amostras gravadas (DFP 2024 e 2025, ITR 2026 e o cadastro)."""
    url = f"sqlite:///{(tmp_path_factory.mktemp('c') / 'c.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)
    with motor.begin() as c:
        repo.gravar_setores(
            c, dm.ler_setores((PASTA / "cad_cia_aberta.csv").read_bytes())
        )
        for arquivo, documento in (
            ("dfp_cia_aberta_2024.zip", "DFP"),
            ("dfp_cia_aberta_2025.zip", "DFP"),
            ("itr_cia_aberta_2026.zip", "ITR"),
        ):
            repo.gravar_demonstracoes(
                c, *dm.ler_demonstracoes((PASTA / arquivo).read_bytes(), documento)
            )
    yield motor
    motor.dispose()


def _dados(banco, cnpj: str) -> DadosDaEmpresa:
    with banco.connect() as c:
        return repo.dados_da_empresa(c, cnpj)


# --- as contas, com demonstrações reais -----------------------------------------------------------
def test_as_features_reusam_os_numeros_da_ficha(banco):
    dados = _dados(banco, WEG)
    f = fc.features_das_demonstracoes(dados, DIA)
    insumos = ca.insumos_das_demonstracoes(dados, DIA)
    ttm, _, _ = fu.doze_meses(dados.contas)
    saldo, _, _ = fu.balanco_mais_recente(dados.contas)
    ficha = fu.calcular(dados, preco=None)
    ebitda, liquida = insumos.ebitda.valor, insumos.divida_liquida.valor
    assert ebitda and liquida is not None
    assert f["divida_liquida_sobre_ebitda"].valor == pytest.approx(liquida / ebitda)
    assert f["divida_liquida_sobre_pl"].valor == ficha["divida_sobre_pl"].valor
    despesa = abs(ttm["despesas_financeiras"])
    assert f["cobertura_de_juros_ebitda"].valor == pytest.approx(ebitda / despesa)
    assert f["cobertura_de_juros_ebit"].valor == pytest.approx(ttm["ebit"] / despesa)
    assert f["liquidez_corrente"].valor == pytest.approx(
        saldo["ativo_circulante"] / saldo["passivo_circulante"]
    )
    assert f["caixa_sobre_divida_de_curto_prazo"].valor == pytest.approx(
        insumos.caixa.valor / saldo["divida_cp"]  # type: ignore[operator]
    )
    receita = fu.anuais(dados.contas)["receita"]
    assert f["crescimento_da_receita_1_ano"].valor == pytest.approx(
        receita.loc[2025] / receita.loc[2024] - 1
    )


def test_toda_feature_tem_rastro_completo_e_a_formula_do_dicionario(banco):
    f = fc.features_das_demonstracoes(_dados(banco, WEG), DIA)
    assert [x.chave for x in f.features] == list(DAS_DEMONSTRACOES)
    for feature in f.features:
        assert feature.rastro.formula == DICIONARIO[feature.chave].formula
        assert feature.rastro.versao_do_calculo == VERSAO_DAS_FEATURES
        assert feature.disponivel_em == feature.rastro.publicado_em
        if feature.valor is not None:
            assert feature.rastro.o_que_falta() == [], feature.chave
            assert feature.disponivel_em <= DIA  # type: ignore[operator]
    assert {d.nome for d in f["divida_liquida_sobre_ebitda"].rastro.documentos} == {
        "DFP de 31/12/2025, versão 1",
        "ITR de 30/06/2026, versão 1",
    }
    assert [d.nome for d in f["liquidez_corrente"].rastro.documentos] == [
        "ITR de 30/06/2026, versão 1"
    ]
    assert f["divida_liquida_sobre_ebitda"].periodo == (
        "12 meses até 30/06/2026; balanço de 30/06/2026"
    )


def test_como_era_no_dia_usa_so_o_que_a_cvm_tinha_recebido(banco):
    """WEG em 01/05/2026: o ITR de junho ainda não existia; vale o de março."""
    f = fc.features_das_demonstracoes(_dados(banco, WEG), date(2026, 5, 1))
    assert f["cobertura_de_juros_ebit"].periodo == "12 meses até 31/03/2026"
    fc.conferir_ponto_no_tempo(f.features, date(2026, 5, 1))


def test_reapresentado_depois_do_dia_fica_nao_observado(banco):
    """Petrobras: o ITR de março tem a versão 2, recebida em 11/05/2026; a 1ª não está guardada."""
    f = fc.features_das_demonstracoes(_dados(banco, PETROBRAS), date(2026, 5, 1))
    for chave in ("divida_liquida_sobre_ebitda", "liquidez_corrente"):
        assert f[chave].valor is None and "ITR de 31/03/2026" in f[chave].motivo


def test_antes_de_qualquer_documento_nada_e_observado(banco):
    f = fc.features_das_demonstracoes(_dados(banco, WEG), date(2025, 1, 1))
    assert all(x.valor is None and x.motivo for x in f.features)
    assert all(x.disponivel_em is None for x in f.features)


def test_banco_nao_tem_alavancagem_nem_liquidez_por_estas_contas(banco):
    f = fc.features_das_demonstracoes(_dados(banco, ITAU), DIA)
    for chave in ("divida_liquida_sobre_ebitda", "liquidez_corrente"):
        assert f[chave].valor is None
        assert f[chave].motivo == fu.NAO_SE_APLICA_A_FINANCEIRAS


def test_crescimento_de_5_anos_sem_historia_fica_nao_observado(banco):
    f = fc.features_das_demonstracoes(_dados(banco, WEG), DIA)
    assert f["crescimento_da_receita_5_anos"].valor is None
    assert "horizonte" in f["crescimento_da_receita_5_anos"].motivo


def test_features_do_emissor_pelo_banco(banco):
    with banco.connect() as c:
        f = fc.features_do_emissor(c, "84429695000111", DIA)
    assert f.cnpj == "84429695000111" and f.data_da_analise == DIA
    assert f["liquidez_corrente"].valor is not None
    with banco.connect() as c, pytest.raises(ValueError):
        fc.features_do_emissor(c, "123", DIA)


def test_features_e_dicionario_viram_json(banco):
    f = fc.features_das_demonstracoes(_dados(banco, WEG), DIA, cnpj="84429695000111")
    texto = json.dumps(f.como_dict())
    lido = json.loads(texto)
    assert lido["data_da_analise"] == "2026-09-30"
    assert lido["features"][0]["disponivel_em"] <= "2026-09-30"
    assert set(f.valores()) == set(DAS_DEMONSTRACOES)
    assert json.loads(json.dumps(dicionario_como_lista()))[0]["chave"] == (
        "divida_liquida_sobre_ebitda"
    )


def test_limites_dizem_que_nao_e_score_nem_recomendacao(banco):
    f = fc.features_das_demonstracoes(_dados(banco, WEG), DIA)
    texto = " ".join(f.limites).lower()
    assert "score" in texto and "recomendação" in texto


# --- a conferência "sem olhar o futuro" -----------------------------------------------------------
def _feature(disponivel_em: date | None, valor: float | None = 1.0) -> fc.Feature:
    documentos = [] if disponivel_em is None else [DocumentoUsado("DFP", disponivel_em)]
    rastro = Rastro.dos_documentos("x", VERSAO_DAS_FEATURES, "cvm", documentos)
    return fc.Feature("x", valor, "", rastro, disponivel_em=rastro.publicado_em)


def test_feature_publicada_depois_do_dia_derruba_a_conferencia():
    fc.conferir_ponto_no_tempo([_feature(DIA)], DIA)
    with pytest.raises(fc.OlhouOFuturoError, match="x"):
        fc.conferir_ponto_no_tempo([_feature(DIA + timedelta(days=1))], DIA)


def test_documento_do_futuro_no_rastro_derruba_mesmo_com_a_data_da_feature_certa():
    feature = _feature(DIA)
    futuro = DocumentoUsado("ITR do futuro", DIA + timedelta(days=1))
    feature = replace(
        feature,
        rastro=replace(feature.rastro, documentos=(*feature.rastro.documentos, futuro)),
    )
    with pytest.raises(fc.OlhouOFuturoError):
        fc.conferir_ponto_no_tempo([feature], DIA)


def test_numero_observado_sem_data_nao_passa_e_nao_observado_sem_data_passa():
    fc.conferir_ponto_no_tempo([_feature(None, valor=None)], DIA)
    with pytest.raises(fc.OlhouOFuturoError):
        fc.conferir_ponto_no_tempo([_feature(None, valor=1.0)], DIA)


def test_calcular_com_o_futuro_e_pego_pela_conferencia(banco):
    """O erro que a conferência existe para pegar: calcular num dia e usar em outro, anterior."""
    f = fc.features_das_demonstracoes(_dados(banco, WEG), DIA)
    with pytest.raises(fc.OlhouOFuturoError):
        fc.conferir_ponto_no_tempo(f.features, date(2026, 5, 1))


# --- por propriedade: cortar o futuro não muda o passado ------------------------------------------
ANOS = range(2017, 2027)
TRIMESTRES = ((3, 31), (6, 30), (9, 30))
FLUXOS = ("receita", "ebit", "depreciacao", "despesas_financeiras", "lucro_liquido")
SALDOS = (
    "caixa",
    "aplicacoes",
    "divida_cp",
    "divida_lp",
    "ativo_circulante",
    "passivo_circulante",
    "patrimonio_liquido",
)


def _valores(sorte: random.Random, contas: tuple[str, ...]) -> dict[str, float]:
    valores = {conta: sorte.uniform(-2e9, 1e10) for conta in contas}
    if "despesas_financeiras" in valores:
        valores["despesas_financeiras"] = -abs(valores["despesas_financeiras"])
    return valores


def _linhas(documento, referencia, periodo, valores) -> list[dict]:
    return [
        {"documento": documento, "referencia": referencia, "versao": 1,
         "periodo": periodo, "inicio": None, "fim": referencia, "conta": conta, "valor": valor}
        for conta, valor in valores.items()
    ]  # fmt: skip


def _demonstracoes_sinteticas(sorte: random.Random) -> DadosDaEmpresa:
    """DFPs e ITRs de 2017 a 2026, com a entrega sorteada (ITR: 20 a 50 dias; DFP: 30 a 100)."""
    contas, documentos = [], []

    def entregar(documento: str, referencia: date, dias: tuple[int, int]) -> None:
        documentos.append(
            {"documento": documento, "referencia": referencia, "versao": 1, "empresa": "X",
             "recebido_em": referencia + timedelta(days=sorte.randint(*dias)), "link": ""}
        )  # fmt: skip

    for ano in ANOS:
        for mes, dia in TRIMESTRES:
            referencia = date(ano, mes, dia)
            contas += _linhas("ITR", referencia, dm.ACUMULADO, _valores(sorte, FLUXOS))
            contas += _linhas(
                "ITR", referencia, dm.ACUMULADO_ANTERIOR, _valores(sorte, FLUXOS)
            )
            contas += _linhas("ITR", referencia, dm.POSICAO, _valores(sorte, SALDOS))
            entregar("ITR", referencia, (20, 50))
        referencia = date(ano, 12, 31)
        contas += _linhas("DFP", referencia, dm.EXERCICIO, _valores(sorte, FLUXOS))
        contas += _linhas("DFP", referencia, dm.POSICAO, _valores(sorte, SALDOS))
        entregar("DFP", referencia, (30, 100))
    return DadosDaEmpresa(pd.DataFrame(contas), pd.DataFrame(documentos), "Máquinas")


dias = st.dates(date(2016, 6, 1), date(2028, 6, 1))


@settings(max_examples=60, deadline=None)
@given(st.integers(0, 2**32 - 1), dias, st.integers(0, 900))
def test_cortar_o_futuro_nao_muda_o_passado(semente, dia, dias_a_mais):
    # a semente sorteia valores e entregas (com `st.randoms` o exemplo fica grande demais)
    dados = _demonstracoes_sinteticas(random.Random(semente))
    corte = dia + timedelta(days=dias_a_mais)
    cortadas = ca.demonstracoes_como_eram(dados, corte).dados
    completas = fc.features_das_demonstracoes(dados, dia)
    assert fc.features_das_demonstracoes(cortadas, dia) == completas
    fc.conferir_ponto_no_tempo(completas.features, dia)
