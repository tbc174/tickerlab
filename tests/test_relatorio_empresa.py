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
    qualidade = relatorio.secao("qualidade_do_lucro")
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


def test_caixa_operacional_tem_nota_por_faixa_fora_das_notas_contra_o_setor(
    dados_da_weg,
):
    """Série 3, PR 2: a nota do caixa operacional / lucro é por faixa fixa, mesmo sem padrões, e não
    aparece entre as "notas contra o setor"."""
    relatorio = re_.montar(_entradas(dados_da_weg, padroes=None))
    item = next(
        i for i in relatorio.secao("caixa").itens if i.chave == "conversao_de_caixa"
    )
    assert item.nota in {"atenção", "saudável", "conferir o lucro"}
    assert "não compara com o setor" in item.nota_texto
    contra_o_setor = " ".join(
        re_.montar(_entradas(dados_da_weg)).secao("padroes_e_notas").paragrafos
    )
    assert "Caixa operacional" not in contra_o_setor


def test_margens_liquidas_tem_nomes_e_bases_diferentes(dados_da_weg):
    """Fim da série 2: a WEG mostrava "Margem líquida" 16,6% e 15,6% na mesma página."""
    relatorio = re_.montar(_entradas(dados_da_weg))
    resultado = {i.chave: i.nome for i in relatorio.secao("resultado").itens}
    retorno = {i.chave: i.nome for i in relatorio.secao("retorno").itens}
    assert resultado["margem_liquida"] == "Margem líquida (lucro consolidado)"
    assert retorno["dupont_margem"] == "Margem líquida dos acionistas (DuPont)"


# --- a fonte restrita citada (ADR 0008, Emenda 3) --------------------------------------------------


def test_relatorio_cita_o_yahoo_pela_lista_dos_usos_sem_cobranca(dados_da_weg):
    from src.banco import coletas

    relatorio = re_.montar(_entradas(dados_da_weg))
    citacao = next(u.citacao for u in coletas.USOS_SEM_COBRANCA if u.fonte == "yahoo")
    assert re_.fontes_do_relatorio(_entradas(dados_da_weg)) == ("cvm", "yahoo")
    assert citacao in relatorio.fontes
    assert "Yahoo" in citacao
    assert relatorio.fontes.index(citacao) > 0  # a CVM vem primeiro


def test_relatorio_barra_fonte_fora_dos_usos(dados_da_weg, monkeypatch):
    """A trava segue no relatório: se o preço viesse da B3, ele não seria montado (ADR 0102)."""
    from src.banco import coletas

    monkeypatch.setattr(re_, "FONTE_DO_PRECO", "b3")
    with pytest.raises(coletas.LicencaNaoPermiteError, match="b3"):
        re_.montar(_entradas(dados_da_weg))


def test_relatorio_monta_mesmo_sem_a_lista_dos_usos_sem_cobranca(
    dados_da_weg, monkeypatch
):
    """ADR 0102: a lista só guarda a citação; sem ela o relatório sai, sem a frase do Yahoo."""
    from src.banco import coletas

    monkeypatch.setattr(coletas, "USOS_SEM_COBRANCA", ())
    relatorio = re_.montar(_entradas(dados_da_weg))
    assert not any("Yahoo" in f for f in relatorio.fontes)


def test_relatorio_sem_preco_nem_padroes_nao_usa_o_yahoo(dados_da_weg):
    entradas = _entradas(dados_da_weg, preco=None, padroes=None)
    assert re_.fontes_do_relatorio(entradas) == ("cvm",)
    relatorio = re_.montar(entradas)
    assert not any("Yahoo" in f for f in relatorio.fontes)


# --- DY e múltiplos de mercado (D3 mudada em 20/10/2026) -------------------------------------------


def test_dividendos_abrem_com_o_dy_citando_o_preco(dados_da_weg):
    dividendos = re_.montar(_entradas(dados_da_weg)).secao("dividendos")
    dy = dividendos.itens[0]
    assert dy.chave == "dividend_yield" and dy.valor and dy.valor > 0
    assert dy.texto.endswith("%") and dy.fonte == re_.FONTE_DOS_MULTIPLOS
    assert any("minoritários" in p for p in dividendos.paragrafos)


def test_valuation_traz_valor_de_mercado_ev_e_multiplos(dados_da_weg):
    valuation = re_.montar(_entradas(dados_da_weg)).secao("valuation")
    itens = {i.chave: i for i in valuation.itens}
    for chave in ("p_l", "p_vp", *re_.MULTIPLOS_DE_MERCADO):
        assert itens[chave].valor is not None, chave
        assert itens[chave].fonte == re_.FONTE_DOS_MULTIPLOS
    assert itens["valor_de_mercado"].texto.startswith("R$ ")
    assert itens["ev_ebitda"].texto.endswith("×")


def test_sem_preco_dy_e_multiplos_ficam_com_o_motivo(dados_da_weg):
    relatorio = re_.montar(_entradas(dados_da_weg, preco=None))
    dy = relatorio.secao("dividendos").itens[0]
    assert dy.valor is None and "preço" in dy.motivo
    for item in relatorio.secao("valuation").itens:
        assert item.valor is None and "preço" in item.motivo


def test_anexo_de_anos_tem_contas_nas_linhas_e_anos_nas_colunas():
    contas = pd.DataFrame(
        {"receita": [100.0, 120.0, None], "lpa_basico": [1.5, 2.0, 2.5]},
        index=pd.Index([2023, 2024, 2025], name="ano"),
    )
    linhas = re_.anexo_de_anos(contas)
    assert [linha["conta"] for linha in linhas] == ["Receita", "LPA básico"]
    assert list(linhas[0]) == ["conta", "unidade", "2023", "2024", "2025"]
    assert linhas[0]["unidade"] == "R$" and linhas[1]["unidade"] == "R$ por ação"
    assert (
        linhas[0]["2024"] == 120.0 and linhas[0]["2025"] is None
    )  # ano sem a conta: vazio
    assert re_.anexo_de_anos(pd.DataFrame()) == []


def test_historico_traz_o_anexo_com_fonte_e_sem_ano_alem_do_publicado(dados_da_weg):
    secao = re_.montar(_entradas(dados_da_weg)).secao("historico")
    anexo = secao.tabelas["anexo_de_anos"]
    anos = [c for c in anexo[0] if c.isdigit()]
    assert anos == sorted(anos) and int(anos[-1]) <= 2025
    # o anexo toma o lugar da tabela de anos nas linhas na página, no PDF e na API; ela fica na
    # seção porque a análise escrita cita as linhas dela
    assert "contas" in secao.tabelas
    assert list(secao.tabelas_a_mostrar()) == ["anexo_de_anos", "vertical"]
    assert any("DFP" in p and "CVM" in p for p in secao.paragrafos)
