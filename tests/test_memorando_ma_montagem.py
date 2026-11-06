"""Memorando de M&A (B-26), PR 2: a montagem das seções, o gabarito da CPFL e o "sem olhar o futuro".

O gabarito usa a ficha de exemplo da CPFL (`dados_de_exemplo/dossie/`), uma tabela de comps e premissas
de LBO e de DCF feitas para dar números que se conferem à mão.
"""

import json
import shutil
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src import comps_por_transacao as ct
from src import dossie
from src.busca_por_cnpj import RelatorioDoCnpj, montar_relatorio_do_cnpj
from src.lbo import DISTRIBUI, PremissasDoLbo, lbo
from src.memorando_ma import conferencia as co
from src.memorando_ma import evidencia as ev
from src.memorando_ma import montagem as mt
from src.memorando_ma.formato import SECOES, Memorando
from src.rastro import Rastro
from src.relatorio_empresa import Item, Secao

CPFL = "02429144000193"
EXEMPLO = Path("dados_de_exemplo/dossie") / f"{CPFL}.json"
ENERGIA = "Energia Elétrica"
DIA_DA_FICHA = date(2026, 10, 17)
ANTES = date(2025, 6, 30)
RASTRO = Rastro("valor do dia", "teste 1", "cvm", date(2025, 3, 31))


@pytest.fixture(scope="module")
def ficha(tmp_path_factory) -> dossie.Ficha:
    pasta = tmp_path_factory.mktemp("dossies")
    (pasta / "atual").mkdir()
    shutil.copy(EXEMPLO, pasta / "atual")
    lida = dossie.ficha_do(CPFL, pasta)
    assert lida is not None
    return lida


@pytest.fixture(scope="module")
def relatorio(ficha) -> RelatorioDoCnpj:
    return montar_relatorio_do_cnpj(ficha, None, "pro", DIA_DA_FICHA)


def _precedente(n: int, multiplo: float, anuncio: date) -> dict:
    return {
        "operacao": f"op{n}",
        "alvo": f"Alvo {n} S.A.",
        "alvo_cnpj": f"{n:02d}.111.111/0001-11",
        "anuncio": anuncio,
        "valor_protocolo": f"protocolo-{n}",
        "valor_publico_em": anuncio,
        "base_12m": "exercício encerrado em 31/12/2022",
        "entregue_ate": anuncio - timedelta(days=30),
        "ev_ebitda": multiplo,
        "ev_receita": None,
        "ev_ebit": None,
    }


# 6, 8 e 10 até a data (quartis inclusivos, à mão: 7, 8 e 9); 50 só depois de 17/10/2026
TABELA = pd.DataFrame(
    [
        _precedente(1, 6.0, date(2023, 3, 1)),
        _precedente(2, 8.0, date(2024, 3, 1)),
        _precedente(3, 10.0, date(2025, 3, 1)),
        _precedente(4, 50.0, date(2026, 11, 1)),
    ]
)


def _comps(cnpj: str, dia: date, tabela: pd.DataFrame = TABELA) -> ct.CompsPorTransacao:
    setores = {c: ENERGIA for c in tabela["alvo_cnpj"]} | {cnpj: ENERGIA}
    return ct.comps_por_transacao(tabela, setores, cnpj, dia)


# LBO à mão: preço 100 × 8 = 800, todo do acionista (sem dívida nem imposto); recebe 100 no ano 1 e
# 100 + 800 da venda no ano 2. TIR: −800 + 100/1,125 + 900/1,125² = 0 → 12,5%; MOIC 1.000/800 = 1,25
PREMISSAS_DO_LBO = PremissasDoLbo(
    100.0,
    8.0,
    8.0,
    (100.0, 100.0),
    (0.0, 0.0),
    (0.0, 0.0),
    (0.0, 0.0),
    0.0,
    politica=DISTRIBUI,
)
# DCF à mão: 1 ano, desconto 10%, perpetuidade 0: valor = F/1,1 + (F/0,1)/1,1 = 10 × F. Preço 1.100
# → F = 110 = 100 × (1 + g) → g = 10%
DCF = mt.PremissasDoDcfReverso(1100.0, 100.0, 1.0, 0.0, 1, 0.10, 0.0, RASTRO, RASTRO)
PARES = mt.IndicadorContraOsPares(
    "margem_ebitda",
    "Margem EBITDA",
    mt.FRACAO,
    0.25,
    0.20,
    9,
    "Energia elétrica",
    RASTRO,
    RASTRO,
)
MULTIPLO = mt.MultiploContraOHistorico("p_l", "P/L", 8.0, 10.0, 5, RASTRO, RASTRO)


def _entrada(relatorio, ficha, dia: date, **outros) -> mt.EntradaDoMemorando:
    campos = {
        "relatorio": relatorio,
        "ficha": ficha,
        "pares": (PARES,),
        "dcf_reverso": DCF,
        "multiplos": (MULTIPLO,),
        "comps": _comps(relatorio.cnpj, dia),
        "lbo": lbo(PREMISSAS_DO_LBO, dia),
    }
    return mt.EntradaDoMemorando(**(campos | outros))


def _frases(memorando: Memorando, chave: str) -> list[str]:
    secao = next(s for s in memorando.secoes if s.chave == chave)
    return [f.texto for f in secao.frases]


def test_gabarito_da_cpfl_conferido_a_mao(relatorio, ficha):
    memorando = mt.montar_memorando(
        _entrada(relatorio, ficha, DIA_DA_FICHA), DIA_DA_FICHA
    )
    assert [s.chave for s in memorando.secoes] == list(SECOES)
    assert (memorando.cnpj, memorando.empresa) == (
        "02.429.144/0001-93",
        "CPFL ENERGIA S.A.",
    )
    assert _frases(memorando, "perfil")[:2] == [
        "Auditor atual: PRICEWATERHOUSECOOPERS AUDITORES INDEPENDENTES LTDA.",
        "Auditor desde: 01/01/2022.",
    ]
    assert _frases(memorando, "pares") == [
        "Margem EBITDA de 25,0%, acima da mediana de 20,0% das 9 empresas do grupo Energia elétrica."
    ]
    assert _frases(memorando, "dcf_e_multiplos") == [
        (
            "Com desconto de 10,0% ao ano, perpetuidade de 0,0% ao ano e 1 ano de fluxo explícito "
            "(premissas declaradas), o preço do dia supõe um crescimento de 10,0% ao ano no caixa livre."
        ),
        (
            "O P/L do dia é de 8,00 vezes, abaixo da mediana de 10,00 vezes dos 5 anos do próprio "
            "histórico."
        ),
    ]
    comps = _frases(memorando, "comps_por_transacao")
    assert comps[0] == (
        f"A mediana do EV/EBITDA pago em 3 precedentes do grupo {_comps(relatorio.cnpj, DIA_DA_FICHA).nome_do_grupo} "
        "foi de 8,00 vezes, com o primeiro quartil em 7,00 vezes e o terceiro em 9,00 vezes."
    )  # fmt: skip
    assert "menos de 3 precedentes" in comps[1]
    assert _frases(memorando, "lbo") == [
        (
            "As premissas declaradas do LBO são compra a 8,00 vezes o EBITDA de entrada, venda a 8,00 "
            "vezes o EBITDA do último ano e 2 anos até a saída."
        ),
        "Com elas, o acionista põe R$ 800 na compra.",
        "A TIR do acionista é de 12,5% ao ano e o MOIC, de 1,25 vezes.",
    ]
    red_flags = _frases(memorando, "red_flags")
    assert (
        "Troca de auditor. Sem achado. A última troca de auditor foi em 01/01/2022, há mais de 3 "
        "anos." in red_flags
    )
    assert red_flags[-1].startswith("Dívida com a União e atrasos de pagamento")


def test_toda_frase_cita_evidencia_completa(relatorio, ficha):
    memorando = mt.montar_memorando(
        _entrada(relatorio, ficha, DIA_DA_FICHA), DIA_DA_FICHA
    )
    assert co.conferir(memorando).aprovada
    for secao in memorando.secoes:
        for frase in secao.frases:
            assert frase.notas
            for nota in frase.notas:
                evidencia = memorando.evidencia(nota)
                assert evidencia is not None and not evidencia.o_que_falta()


def test_o_lbo_cita_os_rastros_do_calculo(relatorio, ficha):
    memorando = mt.montar_memorando(
        _entrada(relatorio, ficha, DIA_DA_FICHA), DIA_DA_FICHA
    )
    tir = memorando.evidencia("lbo.tir")
    assert tir is not None and tir.valor == pytest.approx(0.125)
    assert tir.rastro is not None and "valor presente" in tir.rastro.formula


def _relatorio_com_item(relatorio: RelatorioDoCnpj, base: str) -> RelatorioDoCnpj:
    item = Item(
        "ligadas",
        "Empresas ligadas",
        "4",
        4.0,
        "empresas",
        base,
        fonte="FRE entregue à CVM",
    )
    return replace(relatorio, secoes=[*relatorio.secoes, Secao("rede", "Rede", [item])])


@pytest.mark.parametrize("dia", [date(2023, 6, 30), ANTES, date(2026, 1, 15)])
def test_sem_olhar_o_futuro(relatorio, ficha, dia):
    """Cortar o futuro (precedentes, itens da rede e o LBO de depois) não muda o memorando do dia."""
    com_futuro = _entrada(
        _relatorio_com_item(relatorio, "FRE entregue em 01/11/2026"),
        ficha,
        dia,
        comps=_comps(relatorio.cnpj, dia),
        lbo=lbo(PREMISSAS_DO_LBO, date(2026, 11, 1)),
    )
    publicos = TABELA[TABELA["anuncio"] <= dia]
    cortado = _entrada(
        relatorio, ficha, dia, comps=_comps(relatorio.cnpj, dia, publicos), lbo=None
    )
    assert (
        mt.montar_memorando(com_futuro, dia).como_dict()
        == mt.montar_memorando(cortado, dia).como_dict()
    )


def test_item_de_antes_da_data_entra_e_o_de_depois_nao(relatorio, ficha):
    entrada = _entrada(
        _relatorio_com_item(relatorio, "FRE entregue em 31/03/2025"), ficha, ANTES
    )
    assert "Empresas ligadas: 4." in _frases(
        mt.montar_memorando(entrada, ANTES), "perfil"
    )
    entrada = _entrada(
        _relatorio_com_item(relatorio, "FRE entregue em 01/07/2025"), ficha, ANTES
    )
    assert "Empresas ligadas: 4." not in _frases(
        mt.montar_memorando(entrada, ANTES), "perfil"
    )


def test_secao_sem_dado_diz_o_que_falta(relatorio):
    entrada = mt.EntradaDoMemorando(relatorio)
    memorando = mt.montar_memorando(entrada, ANTES)
    assert _frases(memorando, "pares") == [
        "Pares do mesmo setor: sem dado público até 30/06/2025."
    ]
    assert _frases(memorando, "lbo") == [
        "LBO com as premissas declaradas: sem dado público até 30/06/2025."
    ]
    lacuna = memorando.evidencia("pares.sem_dado")
    assert lacuna is not None and lacuna.tipo == ev.LACUNA


def test_secao_trancada_fica_de_fora(relatorio):
    trancado = replace(
        relatorio, secoes=[replace(s, trancada=True) for s in relatorio.secoes]
    )
    memorando = mt.montar_memorando(mt.EntradaDoMemorando(trancado), DIA_DA_FICHA)
    assert _frases(memorando, "perfil") == [
        "Perfil: a companhia, o grupo e a rede: sem dado público até 17/10/2026."
    ]


def test_dcf_sem_crescimento_na_faixa_vira_lacuna(relatorio):
    sem_solucao = replace(DCF, caixa_livre=-10.0)
    memorando = mt.montar_memorando(
        mt.EntradaDoMemorando(relatorio, dcf_reverso=sem_solucao), DIA_DA_FICHA
    )
    frase = _frases(memorando, "dcf_e_multiplos")[0]
    assert frase.startswith(
        "Nenhum crescimento entre -50,0% e 100,0% ao ano faz o DCF dar o preço"
    )


def test_comps_sem_setor_vira_lacuna(relatorio):
    sem_setor = ct.comps_por_transacao(TABELA, {}, relatorio.cnpj, DIA_DA_FICHA)
    memorando = mt.montar_memorando(
        mt.EntradaDoMemorando(relatorio, comps=sem_setor), DIA_DA_FICHA
    )
    assert _frases(memorando, "comps_por_transacao") == [
        f"Comps por transação: {ct.SEM_SETOR}."
    ]


def test_nunca_escreve_o_valor_por_acao_nem_o_valor_da_saida(relatorio, ficha):
    texto = mt.montar_memorando(
        _entrada(relatorio, ficha, DIA_DA_FICHA), DIA_DA_FICHA
    ).como_texto()
    assert (
        "1.100" not in texto and "R$ 1,1 mil" not in texto
    )  # o preço e o valor por ação do DCF
    assert "vale" not in co.porta1.normalizar(texto).split()


def test_como_dict_vira_json(relatorio, ficha):
    memorando = mt.montar_memorando(
        _entrada(relatorio, ficha, DIA_DA_FICHA), DIA_DA_FICHA
    )
    dado = json.loads(json.dumps(memorando.como_dict(), ensure_ascii=False))
    assert [s["chave"] for s in dado["secoes"]] == list(SECOES)
    assert any("Nada aqui é recomendação" in limite for limite in dado["limites"])


@pytest.mark.parametrize(
    ("valor", "unidade", "esperado"),
    [
        (8.1, mt.VEZES, "8,10 vezes"),
        (0.2312, mt.FRACAO, "23,1%"),
        (495_194_775.44, mt.REAIS, "R$ 495,2 mi"),
    ],
)
def test_numero_escrito(valor, unidade, esperado):
    assert mt.escrito(valor, unidade) == esperado
