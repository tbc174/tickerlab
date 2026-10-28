"""O relatório do setor (molde D, plano de 19/10/2026, PR 3, tarefas 3.0 a 3.4).

A noite grava a seção `setor` na ficha de um membro e aponta para ela no manifesto; o app junta os
membros pelo setor da CVM e os indicadores de cada um. Os testes usam uma noite pequena (elétricas,
2 companhias abertas, 2024 e 2025) montada pelas mesmas funções da base.
"""

import json
import re
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import dossie as dossie_da_base
from src import cruzamentos, dossie, fundamentos
from src import relatorio_setor as rs
from src.analise_escrita import porta1
from src.dossie import Ficha, SecaoDaFicha
from src.relatorio_empresa import escrever
from tests.test_dossie_no_app import CPFL, _bruta, _pasta
from tests.test_setores import SETORES_REAIS

OUTRA = (
    "11222333000181"  # uma distribuidora inventada, a 2ª companhia aberta do exemplo
)
HOJE = date(2026, 10, 20)


def _ligacoes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fonte": ["aneel-samp", "aneel-samp"],
            "chave": ["33050196000188", "44555666000177"],
            "nome": ["CPFL Paulista", "Outra Distribuidora"],
            "cnpj_companhia": [CPFL, OUTRA],
            "via": ["controlada", "controlada"],
            "principal": [True, True],
            "desde": [pd.Timestamp("2010-05-01")] * 2,
        }
    )


def _consumidores() -> pd.DataFrame:
    chaves = ["33050196000188", "44555666000177", "99999999000199"]
    return pd.DataFrame(
        {
            "ano": [2024] * 3 + [2025] * 3,
            "chave": chaves * 2,
            "valor": [100.0, 300.0, 600.0, 110.0, 280.0, 610.0],
            "meses": [12] * 6,
            "ultimo_mes": [pd.Timestamp("2024-12-31")] * 3
            + [pd.Timestamp("2025-12-31")] * 3,
        }
    )


def _consumidores_com_2026_pela_metade() -> pd.DataFrame:
    """2024 e 2025 inteiros e 2026 com 8 meses: poucos participantes, a CPFL e a outra sozinhas."""
    parcial = pd.DataFrame(
        {
            "ano": [2026] * 2,
            "chave": ["33050196000188", "44555666000177"],
            "valor": [5.0, 7.0],
            "meses": [8] * 2,
            "ultimo_mes": [pd.Timestamp("2026-08-31")] * 2,
        }
    )
    return pd.concat([_consumidores(), parcial], ignore_index=True)


def secao_da_noite(consumidores: pd.DataFrame | None = None) -> dict:
    """A seção `setor` das elétricas como a noite a grava (molde D, PR 1)."""
    setor = rs.setor_do_relatorio("eletricas")
    membros = dossie_da_base.membros_do_setor(
        setor,
        pd.DataFrame(
            {
                "cnpj": [CPFL, OUTRA],
                "empresa": ["CPFL ENERGIA S.A.", "OUTRA ENERGIA S.A."],
            }
        ),
        _ligacoes(),
    )
    secao = dossie_da_base.secao_setor(
        setor,
        membros,
        {
            "aneel_consumidores": _consumidores()
            if consumidores is None
            else consumidores
        },
        _ligacoes(),
        {},
    )
    assert secao is not None
    return json.loads(json.dumps(secao, allow_nan=False))


def gravar_noite(
    pasta: Path, secao: dict | None = None, setor: str = "eletricas"
) -> Path:
    """A ficha da CPFL com a seção do setor e o manifesto que aponta para ela."""
    bruta = _bruta()
    bruta["secoes"].append(secao or secao_da_noite())
    _pasta(pasta, bruta)
    manifesto = {"setores": {setor: {"ficha": CPFL, "membros": [CPFL, OUTRA]}}}
    (pasta / "atual" / dossie.NOME_DO_MANIFESTO).write_text(
        json.dumps(manifesto), encoding="utf-8"
    )
    return pasta


@pytest.fixture
def noite(tmp_path: Path) -> dossie.SecaoDoSetor:
    secao = dossie.secao_do_setor("eletricas", gravar_noite(tmp_path))
    assert secao is not None
    return secao


TICKERS = {CPFL: ["CPFE3"], OUTRA: ["OUTR3"]}


def _membros(noite: dossie.SecaoDoSetor, da_cvm: dict | None = None) -> list[rs.Membro]:
    return rs.juntar_membros(noite.secao.tabelas["membros"], da_cvm or {}, TICKERS)


def _indicador(
    chave: str, valor: float, unidade: str = fundamentos.REAIS
) -> fundamentos.Indicador:
    return fundamentos.Indicador(
        chave, chave, valor, unidade, "12 meses até 30/06/2026"
    )


def _entradas(noite, indicadores=None, caixas=None) -> rs.EntradasDoSetor:
    return rs.EntradasDoSetor(
        rs.setor_do_relatorio("eletricas"),
        _membros(noite),
        noite,
        indicadores or {},
        caixas or {},
    )


# --- 3.0: os setores da CVM -----------------------------------------------------------------------


def test_setores_da_cvm_existem_no_cadastro() -> None:
    nomes = {nome for nomes in rs.SETORES_DA_CVM.values() for nome in nomes}
    assert nomes <= set(SETORES_REAIS)


def test_setores_da_cvm_sao_do_relatorio() -> None:
    assert set(rs.SETORES_DA_CVM) <= set(rs.POR_CHAVE)


def test_aviacao_fica_na_reserva() -> None:
    with pytest.raises(rs.SetorDesconhecidoError):
        rs.setor_do_relatorio("aviacao")
    with pytest.raises(rs.SetorDesconhecidoError):
        rs.setor_do_relatorio("../eletricas")
    assert [s.chave for s in rs.SETORES_DO_RELATORIO] == [
        "eletricas",
        "bancos",
        "seguros",
        "saude_suplementar",
        "telecom",
    ]


def test_membro_entra_pela_noite_e_pela_cvm_com_os_dois_motivos(noite) -> None:
    da_cvm = {CPFL: ("CPFL ENERGIA S.A.", "Energia Elétrica")}
    cpfl = next(m for m in _membros(noite, da_cvm) if m.cnpj == CPFL)
    assert (
        cpfl.motivo == "ligada à ANEEL por 1 entidade; setor da CVM: Energia Elétrica"
    )
    assert cpfl.tickers == ["CPFE3"]


def test_membro_sem_ticker_fica_de_fora(noite) -> None:
    membros = rs.juntar_membros(
        noite.secao.tabelas["membros"],
        {"99888777000166": ("FECHADA", "Energia Elétrica")},
        TICKERS,
    )
    assert [m.cnpj for m in membros] == [
        CPFL,
        OUTRA,
    ]  # em ordem de nome, não de tamanho


# --- 3.1: a matriz KPI × setor --------------------------------------------------------------------


def test_todo_kpi_que_falta_tem_fonte() -> None:
    faltam = [k for k in rs.KPIS_DO_SETOR if k.situacao == rs.FALTA]
    assert faltam
    assert all(k.fonte and k.tabela is None and k.no_relatorio is None for k in faltam)


def test_kpi_tem_so_com_tabela_que_pode_mostrar() -> None:
    for kpi in rs.KPIS_DO_SETOR:
        if kpi.situacao == rs.FALTA:
            continue
        assert kpi.tabela == rs.DO_BANCO_DO_APP or dossie_da_base.pode_mostrar(
            kpi.tabela or ""
        ), kpi.id


def test_kpi_parcial_diz_o_que_falta() -> None:
    parciais = [k for k in rs.KPIS_DO_SETOR if k.situacao == rs.PARCIAL]
    assert parciais and all(k.o_que_falta for k in parciais)


def test_kpi_proprio_que_sai_no_relatorio_e_serie_do_setor() -> None:
    series = set(dossie.SERIES_DO_SETOR)
    proprios = [k for k in rs.KPIS_DO_SETOR if rs.TODOS not in k.setores]
    assert all(k.no_relatorio in series for k in proprios if k.no_relatorio), proprios


def test_ids_dos_kpis_sao_unicos() -> None:
    ids = [k.id for k in rs.KPIS_DO_SETOR]
    assert len(ids) == len(set(ids))


def test_cada_setor_do_relatorio_tem_kpis_proprios() -> None:
    for setor in rs.SETORES_DO_RELATORIO:
        assert any(setor.chave in k.setores for k in rs.KPIS_DO_SETOR), setor.chave


# --- 3.2: lado a lado -----------------------------------------------------------------------------


def _lado_a_lado(noite, indicadores=None, caixas=None) -> list[dict[str, str]]:
    return rs.lado_a_lado(
        rs.setor_do_relatorio("eletricas"),
        _membros(noite),
        indicadores or {},
        caixas or {},
        noite.secao.tabelas["participacao_dos_membros"],
    )


def test_ebitda_sem_a_t1_e_ainda_sem_dado(noite) -> None:
    linhas = _lado_a_lado(noite)
    assert {l["Margem EBITDA (último exercício)"] for l in linhas} == {
        rs.AINDA_SEM_DADO
    }


def test_ebitda_com_a_t1_aparece(noite) -> None:
    caixas = {CPFL: {"exercicio": 2025, "margem_ebitda": 0.25, "fcf": 1.0}}
    cpfl = next(
        l for l in _lado_a_lado(noite, caixas=caixas) if l["Tickers"] == "CPFE3"
    )
    assert cpfl["Margem EBITDA (último exercício)"] == "25,0%"
    assert "EBITDA: exercício 2025" in cpfl["De quando"]


def test_lado_a_lado_com_data_e_fonte(noite) -> None:
    indicadores = {CPFL: {"receita": _indicador("receita", 4.5e10)}}
    linhas = _lado_a_lado(noite, indicadores)
    cpfl = next(l for l in linhas if l["Tickers"] == "CPFE3")
    assert cpfl["Receita (12 meses)"] == escrever(4.5e10, fundamentos.REAIS)
    assert (
        cpfl["Parte do mercado: Consumidores atendidos pelas distribuidoras (ANEEL)"]
        == "11,0%"
    )
    assert "12 meses até 30/06/2026" in cpfl["De quando"]
    assert "dez/2025" in cpfl["De quando"]
    outra = next(l for l in linhas if l["Tickers"] == "OUTR3")
    assert outra["Receita (12 meses)"] == rs.AINDA_SEM_DADO  # sem DFP no banco do app
    relatorio = rs.montar_relatorio_do_setor(_entradas(noite, indicadores), "pro", HOJE)
    secao = next(s for s in relatorio.secoes if s.chave == "lado_a_lado")
    assert any(p.startswith("Fonte: DFP e ITR") for p in secao.paragrafos)
    assert secao.paragrafos[0].startswith("Dados da base do TickerLab de")


def test_lado_a_lado_nao_ordena_pelo_numero(noite) -> None:
    indicadores = {
        CPFL: {"receita": _indicador("receita", 1.0)},
        OUTRA: {"receita": _indicador("receita", 9.0)},
    }
    linhas = _lado_a_lado(noite, indicadores)
    assert [l["Companhia"] for l in linhas] == [
        "CPFL ENERGIA S.A.",
        "OUTRA ENERGIA S.A.",
    ]


# --- 3.3: as frases por regra ---------------------------------------------------------------------


def _ids_que_existem(noite: dossie.SecaoDoSetor) -> set[str]:
    ids = {"membros", *noite.itens}
    for chave, linhas in noite.secao.tabelas.items():
        for linha in linhas:
            if chave == "participacao_dos_membros":
                ids.add(f"{chave}/{linha['cnpj']}/{linha['serie']}/{linha['ano']}")
            elif "ano" in linha:
                ids.add(f"{chave}/{linha['ano']}")
    return ids


def test_frase_sempre_com_id_do_numero(noite) -> None:
    frases = rs.frases_por_regra(rs.setor_do_relatorio("eletricas"), noite.secao)
    assert rs.MINIMO_DE_FRASES <= len(frases) <= rs.MAXIMO_DE_FRASES
    existem = _ids_que_existem(noite)
    for frase in frases:
        assert frase.ids and set(frase.ids) <= existem, frase


def test_frase_traz_os_numeros_da_noite(noite) -> None:
    textos = " ".join(
        f.texto
        for f in rs.frases_por_regra(rs.setor_do_relatorio("eletricas"), noite.secao)
    )
    assert "na faixa" in textos and "Guia H do CADE" in textos
    assert "de 2024 para 2025" in textos.lower()
    # a CPFL subiu de 10,0% para 11,0%; a outra caiu de 30,0% para 28,0% (a maior variação)
    assert (
        "a da OUTRA ENERGIA S.A.: caiu 2,0 pontos percentuais, de 30,0% para 28,0%"
        in textos
    )


def test_frase_sem_previsao_nem_ordem_por_juizo(noite) -> None:
    textos = [
        f.texto
        for f in rs.frases_por_regra(rs.setor_do_relatorio("eletricas"), noite.secao)
    ]
    juizo = re.compile(
        r"\b(?:melhor|pior|lider\w*|domina\w*|vencedor\w*|perdedor\w*|destaque)\b"
    )
    for texto in [*textos, rs.SOBRE_AS_FRASES, rs.SOBRE_O_LADO_A_LADO]:
        normal = porta1.normalizar(texto)
        assert not porta1._PROIBIDAS.search(normal), texto
        assert not porta1._PREVISAO.search(normal), texto
        assert not juizo.search(normal), texto


@pytest.fixture
def noite_com_2026_pela_metade(tmp_path: Path) -> dossie.SecaoDoSetor:
    secao = secao_da_noite(_consumidores_com_2026_pela_metade())
    noite = dossie.secao_do_setor("eletricas", gravar_noite(tmp_path, secao))
    assert noite is not None
    return noite


def test_frases_usam_o_ultimo_ano_completo_e_nao_o_parcial(
    noite_com_2026_pela_metade,
) -> None:
    """2026 tem 8 meses e 2 participantes: as frases do ano (HHI, CR4, soma, maior parte) são de 2025."""
    secao = noite_com_2026_pela_metade.secao
    frases = rs.frases_por_regra(rs.setor_do_relatorio("eletricas"), secao)
    por_id = {f.ids[0]: f.texto for f in frases}
    assert por_id["hhi_aneel_consumidores"].startswith("Em 2025, o HHI")
    assert "em 2025, entre 3 participantes" in por_id["cr4_aneel_consumidores"]
    assert all("2026" not in f.texto for f in frases), [f.texto for f in frases]
    assert any(f.texto.startswith("Em 2025, as 2 companhias abertas") for f in frases)


def test_sem_ano_completo_a_frase_diz_os_meses(tmp_path: Path) -> None:
    so_parcial = _consumidores_com_2026_pela_metade().query("ano == 2026")
    secao = secao_da_noite(so_parcial.reset_index(drop=True))
    noite = dossie.secao_do_setor("eletricas", gravar_noite(tmp_path, secao))
    assert noite is not None
    frases = rs.frases_por_regra(rs.setor_do_relatorio("eletricas"), noite.secao)
    assert frases
    for frase in frases:
        assert "2026 (só 8 meses, até ago/2026)" in frase.texto, frase.texto


def test_tamanho_e_concentracao_declaram_o_ano_parcial(
    noite_com_2026_pela_metade,
) -> None:
    relatorio = rs.montar_relatorio_do_setor(
        _entradas(noite_com_2026_pela_metade), "pro", HOJE
    )
    por_chave = {s.chave: s for s in relatorio.secoes}
    for chave in ("tamanho", "concentracao"):
        avisos = [p for p in por_chave[chave].paragrafos if "2026 tem 8 meses" in p]
        assert len(avisos) == 1, chave
        assert "ano inteiro de 2025" in avisos[0]
    itens = {i.chave: i for s in relatorio.secoes for i in s.itens}
    assert itens["hhi_aneel_consumidores"].base == "dez/2025"
    assert itens["mercado_aneel_consumidores"].valor == pytest.approx(1000.0)


def test_sem_numeros_bastantes_nao_ha_frase() -> None:
    secao = dossie.SecaoDaFicha(chave="setor", titulo="Setor")
    assert rs.frases_por_regra(rs.setor_do_relatorio("eletricas"), secao) == []


# --- 3.4: o relatório -----------------------------------------------------------------------------


def test_relatorio_do_setor_ordem_das_secoes(noite) -> None:
    relatorio = rs.montar_relatorio_do_setor(_entradas(noite), "pro", HOJE)
    assert [s.chave for s in relatorio.secoes] == list(rs.ORDEM_DAS_SECOES)
    assert relatorio.como_era_em == noite.dia
    assert relatorio.frases and relatorio.fontes and not relatorio.avisos
    assert next(s for s in relatorio.secoes if s.chave == "metodologia").recolhida


def test_secoes_trazem_as_tabelas_da_noite(noite) -> None:
    relatorio = rs.montar_relatorio_do_setor(_entradas(noite), "pro", HOJE)
    por_chave = {s.chave: s for s in relatorio.secoes}
    assert "concentracao_aneel_consumidores" in por_chave["concentracao"].tabelas
    assert "participacao_aneel_consumidores" in por_chave["participacao"].tabelas
    assert "tamanho_aneel_consumidores" in por_chave["tamanho"].tabelas
    assert [i.chave for i in por_chave["concentracao"].itens] == [
        "hhi_aneel_consumidores",
        "cr4_aneel_consumidores",
    ]
    membros = por_chave["membros"].tabelas["membros"]
    assert membros[0]["CNPJ"] == "02.429.144/0001-93"


def test_sem_o_plano_vem_trancado(noite) -> None:
    relatorio = rs.montar_relatorio_do_setor(_entradas(noite), "gratuito", HOJE)
    trancadas = [s for s in relatorio.secoes if s.trancada]
    assert {s.chave for s in trancadas} == rs.DA_BASE
    assert all(not s.itens and not s.tabelas and s.paragrafos for s in trancadas)
    assert relatorio.frases == []
    assert not any(
        "ODbL" in f for f in relatorio.fontes
    )  # nenhuma fonte da base sem o número
    abertas = {s.chave for s in relatorio.secoes if not s.trancada}
    assert abertas == {"membros", "nao_temos", "metodologia"}


@pytest.mark.parametrize("plano", ["gratuito", "pro"])
def test_nao_temos_sempre_presente(noite, plano) -> None:
    for entradas in (
        _entradas(noite),
        rs.EntradasDoSetor(rs.setor_do_relatorio("bancos"), [], None, {}, {}),
    ):
        relatorio = rs.montar_relatorio_do_setor(entradas, plano, HOJE)
        secao = next(s for s in relatorio.secoes if s.chave == "nao_temos")
        assert not secao.trancada and secao.tabelas["nao_temos"]
        assert relatorio.nao_temos
        assert all(f.motivo and f.fonte for f in relatorio.nao_temos)


def test_nao_temos_diz_o_parcial_e_o_que_a_base_ja_tem() -> None:
    faltas = {f.kpi: f for f in rs.nao_temos("eletricas")}
    assert faltas["Perdas de energia"].motivo.startswith("Parcial:")
    assert faltas["Geração por usina"].fonte == "base do TickerLab (tabela ons_geracao)"
    assert faltas["PLD e CMO"].fonte == "série T6 da mesa Dados"
    assert "Consumidores atendidos" not in faltas  # esse sai no relatório


def test_setor_sem_a_noite_traz_os_membros_e_o_aviso() -> None:
    membros = [
        rs.Membro(
            "00000000000191", "BANCO DO BRASIL S.A.", ["BBAS3"], "setor da CVM: Bancos"
        )
    ]
    entradas = rs.EntradasDoSetor(
        rs.setor_do_relatorio("bancos"), membros, None, {}, {}
    )
    relatorio = rs.montar_relatorio_do_setor(entradas, "pro", HOJE)
    assert relatorio.como_era_em is None and relatorio.avisos == [rs.SEM_A_NOITE]
    assert [s.chave for s in relatorio.secoes] == [
        "membros",
        "lado_a_lado",
        "cruzamentos",
        "o_que_os_dados_mostram",
        "nao_temos",
        "metodologia",
    ]
    lado = next(s for s in relatorio.secoes if s.chave == "lado_a_lado")
    assert lado.tabelas["lado_a_lado"][0]["Companhia"] == "BANCO DO BRASIL S.A."


def _ficha_com_fundos_entrando() -> Ficha:
    janelas = [
        {"janela": "atual", "compras": 900.0, "vendas": 100.0, "ate": "2026-09-30"},
        {"janela": "anterior", "compras": 500.0, "vendas": 400.0, "ate": "2026-06-30"},
    ]
    capital = SecaoDaFicha(
        chave="capital_e_acionistas",
        titulo="Capital e acionistas",
        tabelas={"fundos_janelas": janelas},
        fontes=["CVM, tabela de teste"],
    )
    return Ficha(
        versao_do_esquema=1,
        cnpj="02429144000193",
        empresa="Alfa",
        gerado_em=datetime(2026, 10, 17, 6, 0, tzinfo=UTC),
        secoes=[capital],
    )


def test_cruzamentos_do_setor_dizem_k_de_n_com_quem_e_a_fonte(noite) -> None:
    entradas = replace(_entradas(noite), fichas={"Alfa": _ficha_com_fundos_entrando()})
    relatorio = rs.montar_relatorio_do_setor(entradas, "pro", HOJE)
    secao = next(s for s in relatorio.secoes if s.chave == "cruzamentos")
    fundos = next(p for p in secao.paragrafos if p.startswith("Fundos entrando"))
    assert "1 de 1 companhias do setor com dado têm achado" in fundos
    assert "Com achado: Alfa." in fundos and "Fonte: CVM, tabela de teste." in fundos
    assert secao.paragrafos[-1] == cruzamentos.LIMITE_DOS_CRUZAMENTOS


def test_cruzamentos_sem_nenhuma_ficha_dizem_que_nao_ha_o_que_cruzar(noite) -> None:
    relatorio = rs.montar_relatorio_do_setor(_entradas(noite), "pro", HOJE)
    secao = next(s for s in relatorio.secoes if s.chave == "cruzamentos")
    assert rs.SEM_FICHAS_PARA_CRUZAR in secao.paragrafos
    assert not secao.trancada


def test_cruzamentos_ficam_trancados_sem_o_dossie_da_base(noite) -> None:
    relatorio = rs.montar_relatorio_do_setor(_entradas(noite), "gratuito", HOJE)
    secao = next(s for s in relatorio.secoes if s.chave == "cruzamentos")
    assert secao.trancada and "Com achado" not in " ".join(secao.paragrafos)


def test_relatorio_vira_json(noite) -> None:
    dados = rs.montar_relatorio_do_setor(_entradas(noite), "pro", HOJE).como_dict()
    json.dumps(dados, allow_nan=False)
    assert dados["como_era_em"] == noite.dia.isoformat()
    assert dados["frases"][0]["ids"]


# --- com o banco do app ---------------------------------------------------------------------------


def test_entradas_do_setor_com_o_banco(banco, tmp_path) -> None:
    from tests.test_fundamentos_no_app import _coletar

    _coletar(banco)
    with banco.connect() as conexao:
        entradas = rs.entradas_do_setor(conexao, "bancos", tmp_path)
        disponiveis = rs.setores_disponiveis(conexao, tmp_path)
    nomes = [m.empresa for m in entradas.membros]
    # o Itaú tem ticker no FCA de exemplo; o Banco do Brasil de exemplo não, e fica de fora
    assert nomes == ["ITAU UNIBANCO HOLDING S.A."]
    assert entradas.membros[0].tickers == ["ITUB4"]
    assert all(
        m.tickers and m.motivo.startswith("setor da CVM") for m in entradas.membros
    )
    assert entradas.da_noite is None
    assert set(entradas.indicadores) == {m.cnpj for m in entradas.membros}
    bancos = next(s for s in disponiveis if s.chave == "bancos")
    assert bancos.empresas == len(entradas.membros) and bancos.como_era_em is None
