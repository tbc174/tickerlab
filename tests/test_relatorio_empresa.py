"""Relatório completo de empresa (série 2 da base de ML, PR 7; ADR 0032): a estrutura que a página,
o PDF e a futura API leem. Todas as seções, cada número com a base e a fonte, notas com o aviso, o
selo quando há achado, "o que mudou desde o balanço anterior", pares e limites. WEG real das amostras
e padrões sintéticos."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src import demonstracoes as dm
from src import relatorio_empresa as re_
from src.banco.demonstracoes import DadosDaEmpresa

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
WEG = "84.429.695/0001-11"
PERCENTIS = {str(p): p / 1000 for p in (10, 20, 25, 33, 40, 50, 60, 67, 75, 80, 90)}


@pytest.fixture(scope="module")
def dados_da_weg():
    partes, documentos = [], []
    for arquivo in ("dfp_cia_aberta_2024.zip", "dfp_cia_aberta_2025.zip"):
        contas, docs = dm.ler_demonstracoes((PASTA / arquivo).read_bytes(), "DFP")
        partes.append(contas[contas["cnpj"] == WEG])
        documentos.append(docs[docs["cnpj"] == WEG])
    return DadosDaEmpresa(
        contas=pd.concat(partes).drop(columns="cnpj"),
        documentos=pd.concat(documentos),
        setor="Máquinas, Equipamentos, Veículos e Peças",
    )


def _entradas(dados, **outros):
    padroes = pd.DataFrame(
        [
            {
                "grupo": "bens_de_capital",
                "indicador": i,
                "empresas": 27,
                "percentis": PERCENTIS,
            }
            for i in ("margem_liquida", "roe", "margem_bruta", "p_l")
        ]
    )
    campos = {
        "dados": dados,
        "cnpj": WEG,
        "empresa": "WEG S.A.",
        "ticker": "WEGE3.SA",
        "preco": 50.0,
        "padroes": (date(2025, 12, 31), padroes),
    }
    return re_.Entradas(**(campos | outros))


def test_relatorio_tem_todas_as_secoes_com_fonte_e_data(dados_da_weg):
    relatorio = re_.montar(_entradas(dados_da_weg))
    chaves = [s.chave for s in relatorio.secoes]
    assert chaves == list(re_.SECOES)
    resultado = relatorio.secao("resultado")
    receita = next(i for i in resultado.itens if i.chave == "receita")
    assert receita.texto.startswith("R$ ") and receita.base  # de quando é o número
    assert relatorio.fontes and any("CVM" in f for f in relatorio.fontes)
    assert relatorio.secao("limites").paragrafos  # a seção obrigatória


def test_nota_ao_lado_do_numero_e_o_aviso(dados_da_weg):
    relatorio = re_.montar(_entradas(dados_da_weg))
    margem = next(
        i for i in relatorio.secao("resultado").itens if i.chave == "margem_liquida"
    )
    assert margem.nota in {"ótimo", "bom", "médio", "ruim", "péssimo"}
    assert "Padrão" in margem.nota_texto
    assert relatorio.aviso_das_notas in " ".join(
        relatorio.secao("padroes_e_notas").paragrafos
    )


def test_numero_com_achado_aberto_ganha_o_selo(dados_da_weg):
    achado = SimpleNamespace(
        regra="R6", documento="DFP", referencia=date(2024, 12, 31),
        porque="A empresa refez o lucro no balanço seguinte.", conta="3.11",
    )  # fmt: skip
    relatorio = re_.montar(_entradas(dados_da_weg, achados=[achado]))
    qualidade = relatorio.secao("qualidade")
    assert any("refez o lucro" in p for p in qualidade.paragrafos)
    assert relatorio.em_conferencia


def test_o_que_mudou_desde_o_balanco_anterior(dados_da_weg):
    mudou = re_.montar(_entradas(dados_da_weg)).secao("o_que_mudou")
    linhas = mudou.tabelas["indicadores"]
    assert linhas and {"indicador", "antes", "agora"} <= set(linhas[0])
    assert any("2024" in p and "2025" in p for p in mudou.paragrafos)


def test_pares_do_mesmo_grupo_pela_receita(dados_da_weg):
    pares = pd.DataFrame(
        {
            "cnpj": ["1", "2", "3", WEG],
            "empresa": ["Perto", "Longe", "Médio", "WEG S.A."],
            "receita": [40e9, 1e9, 20e9, 41e9],
        }
    )
    tabela = (
        re_.montar(_entradas(dados_da_weg, pares=pares)).secao("pares").tabelas["pares"]
    )
    assert [p["empresa"] for p in tabela][:2] == [
        "Perto",
        "Médio",
    ]  # a própria WEG não entra
    assert "WEG S.A." not in [p["empresa"] for p in tabela]


def test_valuation_com_premissas_padrao_e_sensibilidade(dados_da_weg):
    valuation = re_.montar(_entradas(dados_da_weg)).secao("valuation")
    assert "sensibilidade" in valuation.tabelas
    assert any("premissas" in p.lower() for p in valuation.paragrafos)


def test_relatorio_e_json_serializavel(dados_da_weg):
    texto = json.dumps(
        re_.montar(_entradas(dados_da_weg)).como_dict(), ensure_ascii=False
    )
    assert "WEG S.A." in texto


def test_banco_mostra_nao_se_aplica(dados_da_weg):
    banco = DadosDaEmpresa(dados_da_weg.contas, dados_da_weg.documentos, "Bancos")
    caixa = re_.montar(_entradas(banco)).secao("caixa")
    assert any("Não se aplica" in i.motivo for i in caixa.itens)


def test_cascata_do_lucro_fecha():
    ano = {"receita": 1000.0, "resultado_bruto": 400.0, "despesas_com_vendas": -80.0,
           "despesas_administrativas": -50.0, "ebit": 230.0, "lucro_liquido": 150.0}  # fmt: skip
    passos = re_.cascata_do_lucro(ano)
    assert passos[0] == ("Receita", 1000.0)
    assert passos[-1] == ("Lucro consolidado", 150.0)  # com a parte dos minoritários
    assert sum(v for _, v in passos[:-1]) == pytest.approx(150.0)  # a cascata fecha
    assert ("Custo", -600.0) in passos
    assert ("Outras operacionais", -40.0) in passos  # 400 − 80 − 50 − 230


def test_cascata_sem_receita_ou_lucro_fica_vazia():
    assert re_.cascata_do_lucro({"receita": 10.0}) == []


def test_ponte_da_divida_fecha():
    anterior = {"divida_liquida": 500.0}
    atual = {"divida_liquida": 420.0, "fco": 300.0, "capex": -120.0,
             "dividendos_pagos": -60.0}  # fmt: skip
    passos = re_.ponte_da_divida(anterior, atual)
    assert passos[0] == ("Dívida líquida no começo", 500.0)
    assert passos[-1] == ("Dívida líquida no fim", 420.0)
    assert sum(v for _, v in passos[:-1]) == pytest.approx(420.0)
    assert ("Caixa operacional", -300.0) in passos  # caixa gerado reduz a dívida
    assert ("Capex", 120.0) in passos and ("Dividendos pagos", 60.0) in passos


def test_relatorio_traz_cascata_e_ponte(dados_da_weg):
    relatorio = re_.montar(_entradas(dados_da_weg))
    assert relatorio.secao("resultado").tabelas["cascata"]
    assert "ponte" in relatorio.secao("endividamento").tabelas


def test_frases_do_valuation_terminam_com_ponto(dados_da_weg):
    valuation = re_.montar(_entradas(dados_da_weg)).secao("valuation")
    assert all(p.endswith(".") for p in valuation.paragrafos)


def test_premissas_escolhidas_aparecem_no_texto(dados_da_weg):
    premissas = re_.Premissas(
        desconto=0.15, perpetuidade=0.02, anos=10, crescimento=0.04
    )
    valuation = re_.montar(_entradas(dados_da_weg, premissas=premissas)).secao(
        "valuation"
    )
    texto = " ".join(valuation.paragrafos)
    assert "escolhidas por você" in texto and "15,0%" in texto
