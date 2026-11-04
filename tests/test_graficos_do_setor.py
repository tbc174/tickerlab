"""Os gráficos escolhidos pela IA no relatório do setor (plano de 23/10/2026, PR 4).

O mesmo cardápio do relatório da empresa, com as tabelas do setor (tamanho, concentração, lado a
lado). O setor não mostra o texto da análise: o gráfico entra no fim da seção da tabela dele, com o
achado embaixo. O ano que a agência ainda não fechou fica fora do desenho (não se compara com os
anos inteiros). A prova é o setor elétrico de 21/10/2026, com o relatório guardado como saiu.
"""

import copy
import json
from datetime import date

import pytest

from src.analise_escrita import entrada as en
from src.analise_escrita import graficos as gr
from src.analise_escrita import molde as molde_
from src.analise_escrita import porta1_dos_graficos as p1g
from src.analise_escrita import reserva_dos_graficos as rg
from src.analise_escrita.exibicao_do_setor import CAMPO_DOS_GRAFICOS, graficos_do_setor
from src.analise_escrita.modelo_da_tela import GraficoDaTela
from tests.ajudantes_da_analise_do_setor import (
    CORTE,
    PAR_DO_SETOR,
    entrada_do_setor,
    gabarito,
    ler_do_par,
)

ESCOLHA_DA_SESSAO = PAR_DO_SETOR / "prova" / "graficos_sessao.json"
CONCENTRACAO = "concentracao.concentracao_aneel_consumidores"


@pytest.fixture(name="relatorio")
def _relatorio() -> dict:
    return ler_do_par("relatorio.json")


def _por_tabela(graficos: tuple[GraficoDaTela, ...]) -> dict[str, GraficoDaTela]:
    return {g.pontos.ids[0].rsplit(".", 1)[0]: g for g in graficos}


def test_ano_parcial_nao_entra_na_tabela_do_grafico(relatorio: dict) -> None:
    entrada = entrada_do_setor(relatorio)
    linhas = gr.tabelas_da_entrada(entrada)[CONCENTRACAO]
    anos = [linha.celulas["Ano"] for linha in linhas]
    assert "2026" not in anos
    assert anos[0] == "2025"


def test_reserva_do_setor_desenha_concentracao_tamanho_e_lado_a_lado(
    relatorio: dict,
) -> None:
    entrada = entrada_do_setor(relatorio)
    reserva = rg.graficos_de_reserva(entrada, molde_.molde(entrada))
    assert {g.tabela.split(".")[0] for g in reserva} == {
        "concentracao",
        "tamanho",
        "lado_a_lado",
    }
    assert {g.origem for g in reserva} == {rg.ORIGEM_REGRAS}
    assert p1g.conferir(gr.Escolha(reserva), entrada, molde_.molde(entrada)).aprovada


def test_graficos_do_setor_saem_so_da_ficha(relatorio: dict) -> None:
    graficos = graficos_do_setor(relatorio, CORTE)
    hhi = _por_tabela(graficos)[CONCENTRACAO]
    assert hhi.secao == "concentracao"
    assert hhi.pontos.rotulos[-1] == "2025"
    assert hhi.pontos.valores[0][-1] == 1015.0
    assert len(hhi.pontos.rotulos) == 9  # 2017 a 2025, sem 2026 (8 meses)


def test_troca_de_valor_na_ficha_muda_o_ponto(relatorio: dict) -> None:
    outro = copy.deepcopy(relatorio)
    concentracao = next(s for s in outro["secoes"] if s["chave"] == "concentracao")
    linhas = next(iter(concentracao["tabelas"].values()))
    linha_2025 = next(li for li in linhas if li["Ano"] == "2025")
    linha_2025["HHI (pontos)"] = "1.234"
    hhi = _por_tabela(graficos_do_setor(outro, CORTE))[CONCENTRACAO]
    assert hhi.pontos.valores[0][-1] == 1234.0


def test_setor_trancado_nao_tem_grafico(relatorio: dict) -> None:
    trancado = copy.deepcopy(relatorio)
    for secao in trancado["secoes"]:
        if secao["chave"] in {"tamanho", "concentracao", "lado_a_lado"}:
            secao["trancada"] = True
    assert graficos_do_setor(trancado, CORTE) == ()


def test_grafico_do_setor_respeita_o_corte(relatorio: dict) -> None:
    antes = graficos_do_setor(relatorio, date(2026, 10, 21))
    cortado = json.loads(json.dumps(relatorio))
    for secao in cortado["secoes"]:
        for linhas in secao["tabelas"].values():
            linhas[:] = [li for li in linhas if li.get("Ano") != "2025"]
    depois = _por_tabela(graficos_do_setor(cortado, CORTE))[CONCENTRACAO]
    assert depois.pontos.rotulos == _por_tabela(antes)[CONCENTRACAO].pontos.rotulos[:-1]


def _lote(relatorio: dict, escolha: dict, **mudancas: object) -> dict:
    """O arquivo do lote do setor, como o `escrever_analises` o grava, com a escolha publicada."""
    entrada = entrada_do_setor(relatorio)
    analise = gabarito()
    registro = {
        "hash_da_entrada": en.hash_da_entrada(entrada),
        "hash_do_texto": gr.hash_do_texto(analise),
        "escolha": escolha,
    }
    lote = {
        "publicavel": True,
        "cnpj": "setor-eletricas",
        "analise": analise.como_dict(),
        "corte": CORTE.isoformat(),
        "hash_da_entrada_atual": en.hash_da_entrada(entrada),
        CAMPO_DOS_GRAFICOS: registro,
    }
    return {**lote, **mudancas}


def _grava(pasta, lote: dict) -> None:
    (pasta / "setor-eletricas.json").write_text(json.dumps(lote), encoding="utf-8")


def test_prova_do_setor_eletrico_a_escolha_da_sessao_passa_na_porta_1(
    relatorio: dict,
) -> None:
    """A escolha feita pela sessão (US$ 0) para o setor elétrico passa na porta 1 contra o texto
    aprovado e traz ao menos um gráfico que a reserva não tem."""
    entrada = entrada_do_setor(relatorio)
    escolha = gr.ler_escolha(json.loads(ESCOLHA_DA_SESSAO.read_text(encoding="utf-8")))
    conferencia = p1g.conferir(escolha, entrada, gabarito())
    assert conferencia.aprovada, conferencia.reprovacoes
    reserva = {g.chave for g in rg.graficos_de_reserva(entrada, gabarito())}
    assert any(g.chave not in reserva for g in escolha.graficos)


def test_escolha_publicada_do_setor_vai_ao_relatorio(relatorio: dict, tmp_path) -> None:
    bruta = json.loads(ESCOLHA_DA_SESSAO.read_text(encoding="utf-8"))
    _grava(tmp_path, _lote(relatorio, bruta))
    graficos = graficos_do_setor(relatorio, CORTE, pasta=tmp_path)
    assert {g.origem for g in graficos} >= {"modelo"}
    assert all(g.secao for g in graficos)
    assert all(g.por_que.texto for g in graficos)


def test_ficha_que_mudou_volta_a_reserva(relatorio: dict, tmp_path) -> None:
    bruta = json.loads(ESCOLHA_DA_SESSAO.read_text(encoding="utf-8"))
    lote = _lote(relatorio, bruta)
    lote[CAMPO_DOS_GRAFICOS]["hash_da_entrada"] = "outra-ficha"
    _grava(tmp_path, lote)
    graficos = graficos_do_setor(relatorio, CORTE, pasta=tmp_path)
    assert graficos
    assert {g.origem for g in graficos} == {rg.ORIGEM_REGRAS}


def test_lote_nao_publicavel_fica_so_com_a_reserva(relatorio: dict, tmp_path) -> None:
    bruta = json.loads(ESCOLHA_DA_SESSAO.read_text(encoding="utf-8"))
    _grava(tmp_path, _lote(relatorio, bruta, publicavel=False))
    graficos = graficos_do_setor(relatorio, CORTE, pasta=tmp_path)
    assert {g.origem for g in graficos} == {rg.ORIGEM_REGRAS}


def test_relatorio_do_setor_traz_os_graficos_na_api_e_no_pdf(relatorio: dict) -> None:
    from datetime import UTC, datetime

    from src import relatorio_do_setor_pdf as pdf_do_setor
    from src.api_v1 import esquemas
    from src.relatorio_setor import RelatorioDoSetor

    graficos = graficos_do_setor(relatorio, CORTE)
    montado = RelatorioDoSetor(
        setor=relatorio["setor"],
        nome=relatorio["nome"],
        como_era_em=CORTE,
        membros=[],
        secoes=[],
        frases=[],
        nao_temos=[],
        fontes=relatorio["fontes"],
        limites=relatorio["limites"],
        graficos=graficos,
    )
    api = esquemas.de_relatorio_do_setor(montado)
    assert [g.secao for g in api.graficos] == [g.secao for g in graficos]
    assert api.graficos[0].pontos.ids == list(graficos[0].pontos.ids)
    sem = pdf_do_setor.relatorio_do_setor(
        RelatorioDoSetor(**{**montado.__dict__, "graficos": ()}),
        datetime(2026, 10, 21, tzinfo=UTC),
    )
    com = pdf_do_setor.relatorio_do_setor(montado, datetime(2026, 10, 21, tzinfo=UTC))
    assert com.count(b"/Subtype /Image") > sem.count(b"/Subtype /Image")


def test_contagem_de_milhoes_vai_em_milhoes_no_eixo(relatorio: dict) -> None:
    """87.543.053 consumidores não cabem no eixo do PDF: o gráfico fala em milhões."""
    tamanho = next(
        g for g in graficos_do_setor(relatorio, CORTE) if g.secao == "tamanho"
    )
    assert tamanho.escala.medida == "milhões"
    assert tamanho.escala.divisor == 1e6
