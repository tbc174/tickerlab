"""Fundamentos da CVM (Research, etapa 3): leitura das demonstrações, cálculo dos indicadores,
banco e coleta, sem internet (amostras reais de 4 empresas em `tests/arquivos/cvm/fundamentos/`)."""

from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa

from scripts import atualizar_fundamentos
from src import demonstracoes as dm
from src import fundamentos as fu
from src.banco import demonstracoes as repo
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
PETROBRAS, ITAU, BB, WEG = (
    "33.000.167/0001-01",
    "60.872.504/0001-23",
    "00.000.000/0001-91",
    "84.429.695/0001-11",
)
BILHAO = 1e9


def _ler(arquivo: str, documento: str):
    return dm.ler_demonstracoes((PASTA / arquivo).read_bytes(), documento)


@pytest.fixture(scope="module")
def banco(tmp_path_factory):
    """Um SQLite com as amostras gravadas (DFP 2024 e 2025, ITR 2026 e o cadastro)."""
    url = f"sqlite:///{(tmp_path_factory.mktemp('f') / 'f.sqlite').as_posix()}"
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
            repo.gravar_demonstracoes(c, *_ler(arquivo, documento))
    yield motor
    motor.dispose()


def _empresa(banco, cnpj):
    with banco.connect() as c:
        return repo.dados_da_empresa(c, cnpj)


# --- leitura ---------------------------------------------------------------------------------------
MIL = 1_000


def test_dfp_traz_as_contas_do_relatorio_completo():
    """Série 2 da base de ML, PR 1: as contas do relatório completo de empresa (WEG, DFP 2025,
    números do arquivo da CVM em milhares). As que a empresa divide em várias linhas são somadas."""
    contas, _ = _ler("dfp_cia_aberta_2025.zip", "DFP")
    weg = contas[contas["cnpj"] == WEG]
    saldos = weg[weg["periodo"] == dm.POSICAO].set_index("conta")["valor"]
    fluxos = weg[weg["periodo"] == dm.EXERCICIO].set_index("conta")["valor"]
    assert saldos["contas_a_receber"] == 7_837_018 * MIL
    assert saldos["estoques"] == 9_911_053 * MIL
    assert saldos["imobilizado"] == 11_511_802 * MIL
    assert saldos["intangivel"] == 2_784_989 * MIL
    assert saldos["fornecedores"] == 2_789_346 * MIL
    assert {"ativo_circulante", "passivo_circulante"} <= set(saldos.index)
    assert fluxos["custo"] == -27_122_477 * MIL
    assert fluxos["despesas_financeiras"] == -2_173_378 * MIL
    assert fluxos["depreciacao"] == 1_001_296 * MIL
    assert fluxos["capex"] == -(2_563_450 + 127_871) * MIL  # imobilizado + intangível
    assert fluxos["dividendos_pagos"] == -5_384_769 * MIL


def test_banco_nao_ganha_estoques_nem_fornecedores():
    contas, _ = _ler("dfp_cia_aberta_2025.zip", "DFP")
    do_banco = set(contas.loc[contas["cnpj"] == BB, "conta"])
    assert not {"estoques", "fornecedores", "custo"} & do_banco


def test_dfp_traz_as_contas_chave_em_reais():
    contas, documentos = _ler("dfp_cia_aberta_2025.zip", "DFP")
    petr = contas[(contas["cnpj"] == PETROBRAS) & (contas["periodo"] == dm.EXERCICIO)]
    valores = dict(zip(petr["conta"], petr["valor"], strict=True))
    assert valores["receita"] == pytest.approx(497.549 * BILHAO)
    assert valores["lucro_liquido"] == pytest.approx(110.605 * BILHAO)
    assert valores["lucro_controladores"] == pytest.approx(110.129 * BILHAO)
    assert valores["lpa_basico"] == pytest.approx(
        8.54
    )  # reais por ação: sem a escala "MIL"
    doc = documentos.set_index("cnpj").loc[PETROBRAS]
    assert doc["link"].startswith("https://www.rad.cvm.gov.br/") and doc["recebido_em"]


def test_banco_usa_outro_plano_de_contas_e_e_reconhecido():
    contas, _ = _ler("dfp_cia_aberta_2025.zip", "DFP")
    itau = set(contas.loc[contas["cnpj"] == ITAU, "conta"])
    assert (
        "ebit" not in itau
        and {"receita", "lucro_liquido", "lucro_controladores"} <= itau
    )
    setores = dm.ler_setores((PASTA / "cad_cia_aberta.csv").read_bytes()).set_index(
        "cnpj"
    )
    assert setores.loc[ITAU, "setor"] == "Bancos"
    assert dm.e_financeira("Bancos") and not dm.e_financeira(
        "Petróleo e Gás", ["receita", "ebit"]
    )
    assert dm.e_financeira(
        "", ["receita", "lucro_liquido"]
    )  # sem EBIT: plano financeiro


def test_itr_fica_com_a_versao_mais_nova_e_separa_os_acumulados():
    contas, documentos = _ler("itr_cia_aberta_2026.zip", "ITR")
    petr = contas[contas["cnpj"] == PETROBRAS]
    primeiro_tri = petr[petr["referencia"] == date(2026, 3, 31)]
    assert set(primeiro_tri["versao"]) == {2}  # havia versões 1 e 2
    assert {dm.ACUMULADO, dm.ACUMULADO_ANTERIOR, dm.POSICAO} <= set(petr["periodo"])
    assert (
        petr.loc[petr["periodo"] == dm.ACUMULADO, "inicio"] == date(2026, 1, 1)
    ).all()
    assert documentos.groupby(["cnpj", "referencia"]).size().max() == 1


# --- cálculo ---------------------------------------------------------------------------------------
def test_doze_meses_somam_o_ano_e_o_acumulado(banco):
    contas = _empresa(banco, PETROBRAS).contas
    ttm, base, usados = fu.doze_meses(contas)
    dfp = fu._contas_em(contas, "DFP", date(2025, 12, 31), dm.EXERCICIO)
    acumulado = fu._contas_em(contas, "ITR", date(2026, 6, 30), dm.ACUMULADO)
    anterior = fu._contas_em(contas, "ITR", date(2026, 6, 30), dm.ACUMULADO_ANTERIOR)
    assert ttm["receita"] == pytest.approx(
        dfp["receita"] + acumulado["receita"] - anterior["receita"]
    )
    assert base == "12 meses até 30/06/2026"
    assert usados == [("DFP", date(2025, 12, 31)), ("ITR", date(2026, 6, 30))]


def test_indicadores_da_petrobras_pelas_formulas(banco):
    f = fu.calcular(
        _empresa(banco, PETROBRAS), preco=37.5, anos=1, roic_minimo=8, pl_maximo=30
    )
    ttm, _, _ = fu.doze_meses(_empresa(banco, PETROBRAS).contas)
    assert f["margem_ebit"].valor == pytest.approx(ttm["ebit"] / ttm["receita"])
    assert f["margem_liquida"].valor == pytest.approx(
        ttm["lucro_liquido"] / ttm["receita"]
    )
    assert f["p_l"].valor == pytest.approx(37.5 / f["lpa"].valor)
    assert not f.financeira and f.notas == []  # ações conferidas com o lucro por ação
    assert (
        f["roic"].base.startswith("12 meses até")
        and "balanço de 30/06/2026" in f["roic"].base
    )
    assert any("ROIC" in frase and "filtro de 8%" in frase for frase in f.filtros)
    assert set(f.documentos["documento"]) == {"DFP", "ITR"}


def test_banco_tem_nao_se_aplica_com_motivo_e_acoes_corrigidas(banco):
    f = fu.calcular(_empresa(banco, ITAU), preco=38.0)
    assert f.financeira
    for chave in ("margem_bruta", "margem_ebit", "roic", "divida_liquida"):
        assert not f[chave].disponivel and "bancos" in f[chave].motivo
    assert f["roe"].disponivel and f["lpa"].valor == pytest.approx(4.25, rel=0.02)
    assert any(
        "milhares" in nota for nota in f.notas
    )  # a CVM traz as ações do Itaú em milhares


def test_sem_preco_e_com_prejuizo_os_multiplos_explicam(banco):
    dados = _empresa(banco, WEG)
    assert "preço" in fu.calcular(dados, preco=None)["p_l"].motivo
    contas = dados.contas.copy()
    lucro = contas["conta"].isin(["lucro_liquido", "lucro_controladores"])
    contas.loc[lucro, "valor"] = -contas.loc[lucro, "valor"].abs()
    f = fu.calcular(replace(dados, contas=contas), preco=50.0)
    assert not f["p_l"].disponivel and "Prejuízo" in f["p_l"].motivo
    assert not f["conversao_de_caixa"].disponivel


def test_crescimento_pede_anos_suficientes(banco):
    dados = _empresa(banco, WEG)
    curto = fu.calcular(dados, preco=50.0, anos=5)["crescimento_receita"]
    assert not curto.disponivel and "Só há 2 anos" in curto.motivo
    um_ano = fu.calcular(dados, preco=50.0, anos=1)["crescimento_receita"]
    tabela = fu.anuais(dados.contas)
    assert um_ano.valor == pytest.approx(
        tabela["receita"].iloc[-1] / tabela["receita"].iloc[-2] - 1
    )


def test_quantidade_de_acoes_que_nao_bate_fica_indisponivel(banco):
    dados = _empresa(banco, PETROBRAS)
    contas = dados.contas.copy()
    contas.loc[contas["conta"] == "acoes_total", "valor"] *= 37  # nem 1×, nem 1.000×
    f = fu.calcular(replace(dados, contas=contas), preco=37.5)
    assert not f["lpa"].disponivel and "não bate" in f["lpa"].motivo


# --- banco e coleta ----------------------------------------------------------------------------------
def test_gravar_de_novo_nao_muda_nada_e_versao_nova_substitui(banco):
    contas, documentos = _ler("itr_cia_aberta_2026.zip", "ITR")
    with banco.begin() as c:
        assert repo.gravar_demonstracoes(c, contas, documentos) == 0
        so_um = documentos[(documentos["cnpj"] == WEG)].head(1).assign(versao=9)
        contas_dele = contas[
            (contas["cnpj"] == WEG)
            & (contas["referencia"] == so_um["referencia"].iloc[0])
        ]
        assert repo.gravar_demonstracoes(c, contas_dele.assign(valor=1.0), so_um) == 1
        valores = (
            c.execute(
                sa.text(
                    "select distinct valor from demonstracoes where cnpj = :c and referencia = :r"
                ),
                {"c": WEG, "r": str(so_um["referencia"].iloc[0])},
            )
            .scalars()
            .all()
        )
        assert valores == [1.0]  # o documento foi trocado inteiro
        c.rollback()


def test_coleta_sem_internet_e_arquivo_que_ainda_nao_existe(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 's.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)

    def baixar_falso(endereco: str) -> bytes | None:
        if endereco.endswith("cad_cia_aberta.csv"):
            return (PASTA / "cad_cia_aberta.csv").read_bytes()
        nome = endereco.rsplit("/", 1)[-1]
        return (PASTA / nome).read_bytes() if (PASTA / nome).exists() else None  # 404

    monkeypatch.setattr(atualizar_fundamentos, "baixar", baixar_falso)
    assert atualizar_fundamentos.main(["--anos", "3"]) == 0
    with criar_engine(url).connect() as c:
        assert (
            c.execute(
                sa.text("select count(distinct cnpj) from documentos_financeiros")
            ).scalar()
            == 4
        )
        assert c.execute(sa.text("select count(*) from setores_cvm")).scalar() == 4


def test_migracao_0010_vai_e_volta(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.sqlite').as_posix()}"
    migrar_para("head", url=url)
    assert "demonstracoes" in sa.inspect(criar_engine(url)).get_table_names()
    desfazer_ate("0009", url=url)
    assert "demonstracoes" not in sa.inspect(criar_engine(url)).get_table_names()
    migrar_para("head", url=url)


@pytest.mark.parametrize(
    ("descricao", "capex"),
    [
        ("Imobilizado", True),
        ("Intangível", True),
        ("Aquisição de ativo imobilizado", True),
        ("Aquisição de bens do ativo imobilizado", True),
        ("Aquisições de bens do ativo imobilizado e intangível", True),
        ("Compras de imobilizado", True),
        ("Adições ao ativo imobilizado", True),
        ("No intangível", True),
        ("Venda de imobilizado", False),
        ("Recebimento pela venda de ativo imobilizado", False),
        ("Alienação de imobilizado e intangível", False),
        ("Baixa de imobilizado", False),
        ("Aplicação financeira de longo prazo", False),
    ],
)
def test_capex_pela_descricao_real_das_empresas(descricao, capex):
    """Descrições do DFP 2025 real: a mesma compra de imobilizado aparece escrita de vários jeitos."""
    assert dm.e_capex(pd.Series([dm._sem_acento(descricao)])).iloc[0] == capex
