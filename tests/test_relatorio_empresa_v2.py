"""Relatórios v2, PR 1 (plano de 17/10/2026): a ficha da empresa ganha leitura.

A ficha inteira da CPFL Energia, montada com dados reais: as demonstrações recortadas dos dados abertos
da CVM (DFP de 2024 e 2025, ITR de 2026), os padrões do setor de energia calculados com as mesmas
demonstrações de todas as companhias (corte de 31/08/2026) e a ficha do dossiê de exemplo.
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src import demonstracoes as dm
from src import dossie
from src import relatorio_empresa as re_
from src.banco.demonstracoes import DadosDaEmpresa

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "cpfl"
CPFL = "02.429.144/0001-93"
SETOR = "Emp. Adm. Part. - Energia Elétrica"
ARQUIVOS = (
    ("dfp_cia_aberta_2024.zip", "DFP"),
    ("dfp_cia_aberta_2025.zip", "DFP"),
    ("itr_cia_aberta_2026.zip", "ITR"),
)
PRECO = 35.0  # um preço fixo, só para os múltiplos saírem
DIA_DA_FICHA = date(2026, 10, 17)
# as seções feitas das demonstrações: todo número delas compara com algo (nunca "sem comparação")
SECOES_DAS_DEMONSTRACOES = (
    "resultado",
    "retorno",
    "endividamento",
    "caixa",
    "notas_classicas",
    "valuation",
)


def _dados() -> DadosDaEmpresa:
    contas, documentos = [], []
    for arquivo, tipo in ARQUIVOS:
        c, d = dm.ler_demonstracoes((PASTA / arquivo).read_bytes(), tipo)
        contas.append(c[c["cnpj"] == CPFL])
        documentos.append(d[d["cnpj"] == CPFL])
    return DadosDaEmpresa(
        pd.concat(contas).drop(columns="cnpj"), pd.concat(documentos), SETOR
    )


def _padroes() -> tuple[date, pd.DataFrame]:
    bruto = json.loads((PASTA / "padroes_energia.json").read_text(encoding="utf-8"))
    return date.fromisoformat(bruto["corte"]), pd.DataFrame(bruto["padroes"])


@pytest.fixture(scope="module")
def entradas_da_cpfl() -> re_.Entradas:
    ficha = dossie.ler_ficha(dossie.FICHA_DE_EXEMPLO)
    assert ficha is not None
    return re_.Entradas(
        dados=_dados(),
        cnpj=CPFL,
        empresa="CPFL ENERGIA S.A.",
        ticker="CPFE3.SA",
        preco=PRECO,
        padroes=_padroes(),
        dossie=dossie.dossie_da_ficha(dossie.cortar(ficha), DIA_DA_FICHA),
    )


@pytest.fixture(scope="module")
def ficha_da_cpfl(entradas_da_cpfl) -> re_.Relatorio:
    return re_.montar(entradas_da_cpfl, plano="pro")


def _faltas(relatorio: re_.Relatorio) -> list[str]:
    faltas = []
    for secao in relatorio.secoes:
        for item in secao.itens:
            onde = f"{secao.chave}.{item.chave}"
            if item.texto == "—":  # sem número: tem de dizer por quê
                if not item.motivo:
                    faltas.append(f"{onde}: sem número e sem o motivo")
                continue
            falta = item.numero.o_que_falta()
            if falta:
                faltas.append(f"{onde} ({item.texto}): falta {', '.join(falta)}")
    return faltas


def test_todo_numero_tem_data_fonte_e_comparacao(ficha_da_cpfl):
    """O contrato do número: valor, de quando é, de onde veio e contra o quê comparar."""
    assert sum(len(s.itens) for s in ficha_da_cpfl.secoes) > 40
    assert _faltas(ficha_da_cpfl) == []


def test_numeros_das_demonstracoes_sempre_comparam(ficha_da_cpfl):
    """ "Sem comparação" é só para o que não tem par (uma contagem do FRE), nunca para um número
    das demonstrações: esses comparam com o setor, uma faixa, o artigo ou o balanço anterior."""
    for chave in SECOES_DAS_DEMONSTRACOES:
        for item in ficha_da_cpfl.secao(chave).itens:
            if item.texto != "—":
                assert item.comparacao is not None, f"{chave}.{item.chave}"
                assert item.comparacao.contra and item.comparacao.texto


def test_nota_contra_o_setor_compara_com_a_mediana(ficha_da_cpfl):
    roe = next(i for i in ficha_da_cpfl.secao("retorno").itens if i.chave == "roe")
    assert roe.comparacao is not None
    assert "energia" in roe.comparacao.contra.lower()
    assert "31/08/2026" in roe.comparacao.contra
    assert "mediana" in roe.comparacao.texto


def test_sem_plano_pro_o_contrato_vale_igual(entradas_da_cpfl):
    assert _faltas(re_.montar(entradas_da_cpfl)) == []


def test_numero_do_dossie_compara_com_o_ano_ou_o_mes_anterior(ficha_da_cpfl):
    ofertas = ficha_da_cpfl.secao("ofertas_e_fundos")
    fundos = next(i for i in ofertas.itens if i.chave == "fundos_com_a_acao")
    assert fundos.comparacao is not None and "mar/2025" in fundos.comparacao.texto
    assert "CDA" in fundos.fonte
