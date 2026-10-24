"""As escolhas de gráficos da prova de 23/10/2026 na CPFL, congeladas: nada vai à rede.

Cada arquivo `graficos_<modelo>.json` guarda a resposta do modelo (guia v1) e o veredito cego da
porta 2. O que importa: a resposta é desta ficha; a porta 1 de hoje barra o que barrava na prova
(o ano no título) e o que só a porta 2 pegava (ofertas por ano com o ano aberto e anos faltando); e
a montagem leva só o que passou nas duas.

O guia v1 pedia um porquê neutro ("Mostra, passo a passo, como..."); o Tiago achou os gráficos pouco
interessantes, e desde a emenda 1 do plano o porquê do modelo é o achado, com número. A porta 1 de
hoje reprova esses porquês neutros (`achado_sem_numero`), e a reserva toma o lugar deles.
"""

import hashlib
import json

import pytest

from src.analise_escrita import entrada as en
from src.analise_escrita import graficos as gr
from src.analise_escrita import pedido_dos_graficos as pg
from src.analise_escrita import porta1, saida
from src.analise_escrita import porta1_dos_graficos as p1g
from src.analise_escrita import reserva_dos_graficos as rg
from tests.ajudantes_da_analise import PAR_DA_CPFL

ENTRADA = json.loads((PAR_DA_CPFL / "entrada.json").read_text(encoding="utf-8"))
ANALISE = saida.ler_analise(
    json.loads((PAR_DA_CPFL / "gabarito.json").read_text(encoding="utf-8"))["analise"]
)
MODELOS = ("haiku", "sonnet", "opus")
TEMPO = {p1g.PERIODO_ABERTO, p1g.PERIODO_FALTANDO}

SEM_NUMERO = p1g.ACHADO_SEM_NUMERO
DO_MODELO, DA_RESERVA = saida.ORIGEM_MODELO, rg.ORIGEM_REGRAS

# (índice, regra) que a porta 1 reprova; a origem dos gráficos e quantos destaques vão ao ar
ESPERADO = {
    "haiku": (
        {(i, SEM_NUMERO) for i in range(5)}
        | {(3, p1g.PERIODO_ABERTO), (3, p1g.PERIODO_FALTANDO)},
        [DA_RESERVA, DA_RESERVA],
        1,
    ),
    "sonnet": (
        {(i, SEM_NUMERO) for i in range(4)}
        | {(3, p1g.PERIODO_ABERTO), (3, p1g.PERIODO_FALTANDO)},
        [DA_RESERVA, DA_RESERVA],
        2,
    ),
    "opus": (  # o único que já escrevia o achado com número em quase todos
        {
            (0, SEM_NUMERO),
            (1, porta1.DATA),
            (2, p1g.PERIODO_ABERTO),
            (2, p1g.PERIODO_FALTANDO),
        },
        [DO_MODELO, DA_RESERVA],
        2,
    ),
}


def _congelado(modelo: str) -> dict:
    arquivo = PAR_DA_CPFL / f"graficos_{modelo}.json"
    return json.loads(arquivo.read_text(encoding="utf-8"))


def _escolha(modelo: str) -> gr.Escolha:
    registro = _congelado(modelo)["escolha"]
    return pg.ler_resposta(registro["stop_reason"], registro["resposta_bruta"])


@pytest.mark.parametrize("modelo", MODELOS)
def test_resposta_congelada_e_desta_ficha(modelo):
    congelado = _congelado(modelo)
    escolha, cega = congelado["escolha"], congelado["cega"]
    assert escolha["hash_da_entrada"] == en.hash_da_entrada(ENTRADA)
    resposta = escolha["resposta_bruta"].encode("utf-8")
    assert cega["hash_da_resposta"] == hashlib.sha256(resposta).hexdigest()
    assert cega["conferente"] != escolha["modelo"]  # ninguém julga a si


@pytest.mark.parametrize("modelo", MODELOS)
def test_porta1_barra_o_que_a_prova_ensinou(modelo):
    reprovacoes = p1g.conferir(_escolha(modelo), ENTRADA, ANALISE).reprovacoes
    assert {(r.indice, r.regra) for r in reprovacoes} == ESPERADO[modelo][0]


@pytest.mark.parametrize("modelo", MODELOS)
def test_porta1_pega_de_graca_o_que_a_porta2_pegou(modelo):
    """O gráfico de período quebrado que a porta 2 reprovou na prova agora sai antes dela."""
    reprovacoes = p1g.conferir(_escolha(modelo), ENTRADA, ANALISE).reprovacoes
    do_tempo = {p1g.rotulo(r.item, r.indice) for r in reprovacoes if r.regra in TEMPO}
    assert do_tempo
    assert do_tempo <= set(_congelado(modelo)["cega"]["reprovados"])


@pytest.mark.parametrize("modelo", MODELOS)
def test_montagem_leva_so_o_que_passou_nas_duas_portas(modelo):
    reprovados = frozenset(_congelado(modelo)["cega"]["reprovados"])
    finais = rg.graficos_finais(_escolha(modelo), ENTRADA, ANALISE, reprovados)
    _, origens, destaques = ESPERADO[modelo]
    assert [g.origem for g in finais.graficos] == origens
    assert len(finais.destaques) == destaques
    assert not p1g.conferir(finais, ENTRADA, ANALISE).reprovacoes
