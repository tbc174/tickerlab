"""O pedido da ficha guardado junto com o backtest salvo (onda 3, PR E2).

O Pulse recalcula a ficha das estratégias salvas com os dados de hoje: o pedido precisa ir e voltar
do banco sem mudar o veredito, e o que volta do banco é dado não confiável.
"""

import json
from dataclasses import replace

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src import ficha
from src.cdi import calcular_taxa_anual_do_cdi
from src.estrategias import ESTRATEGIAS
from src.protecoes import Protecoes
from tests.test_ficha import _pedido, _tendencias_longas

DADOS = _tendencias_longas(n=800)


def _pela_base(guardado):
    """Como o banco devolve: passou por JSON."""
    return json.loads(json.dumps(guardado))


def _completo(**extras):
    return _pedido(
        DADOS,
        protecoes=Protecoes(stop_loss=0.08, janela_atr=10, dias_de_espera=3),
        livres=("curta", "longa"),
        taxa_livre_de_risco=0.1,
        tolerancia_de_queda=0.25,
        tentativas_da_pessoa=4,
        **extras,
    )


def _sem_dados(pedido):
    return replace(pedido, dados=None, cdi_diario=None)


def test_ida_e_volta_devolve_o_mesmo_pedido():
    original = _completo()
    volta = ficha.pedido_guardado(
        _pela_base(ficha.pedido_para_guardar(original)), DADOS
    )
    assert _sem_dados(volta) == _sem_dados(original)
    assert volta.dados is DADOS


def test_pedido_guardado_da_o_mesmo_veredito():
    original = _completo()
    volta = ficha.pedido_guardado(
        _pela_base(ficha.pedido_para_guardar(original)), DADOS
    )
    assert ficha.montar_ficha(volta) == ficha.montar_ficha(original)


def test_pedido_com_cdi_recalcula_a_taxa_com_o_cdi_de_hoje():
    cdi = pd.Series(0.0004, index=DADOS.index)
    guardado = _pela_base(ficha.pedido_para_guardar(_completo(cdi_diario=cdi)))
    assert guardado["usa_cdi"] is True
    volta = ficha.pedido_guardado(guardado, DADOS, cdi)
    assert volta.cdi_diario is cdi
    assert volta.taxa_livre_de_risco == pytest.approx(
        calcular_taxa_anual_do_cdi(cdi, DADOS.index)
    )
    with pytest.raises(ValueError, match="CDI"):
        ficha.pedido_guardado(guardado, DADOS)


def test_estrategia_sem_numeros_e_sem_protecoes_vai_e_volta():
    original = _pedido(DADOS, "Comprar e segurar")
    volta = ficha.pedido_guardado(
        _pela_base(ficha.pedido_para_guardar(original)), DADOS
    )
    assert _sem_dados(volta) == _sem_dados(original)


def _estragar(**mudancas):
    guardado = _pela_base(ficha.pedido_para_guardar(_completo()))
    for chave, valor in mudancas.items():
        if valor is _APAGAR:
            del guardado[chave]
        else:
            guardado[chave] = valor
    return guardado


_APAGAR = object()


@pytest.mark.parametrize(
    "guardado",
    [
        None,
        "texto",
        [1, 2],
        _estragar(versao=2),
        _estragar(versao=_APAGAR),
        _estragar(estrategia="Estratégia que não existe"),
        _estragar(estrategia=["Cruzamento de médias"]),
        _estragar(parametros={"curta": 20, "longa": 50, "inventado": 1}),
        _estragar(parametros={"curta": 5000}),
        _estragar(parametros={"curta": True}),
        _estragar(parametros={"curta": "20"}),
        _estragar(parametros={"tipo": "Outro"}),
        _estragar(parametros="curta=20"),
        _estragar(custo_por_operacao=-0.01),
        _estragar(custo_por_operacao=float("nan")),
        _estragar(custo_por_operacao="0.001"),
        _estragar(capital_inicial=0),
        _estragar(capital_inicial=1e20),
        _estragar(protecoes={"stop_loss": 0.08, "invasor": 1}),
        _estragar(protecoes={"stop_loss": -0.08}),
        _estragar(protecoes={"janela_atr": 2.5}),
        _estragar(protecoes={"janela_atr": None}),
        _estragar(protecoes={"janela_volatilidade": 0}),
        _estragar(protecoes={"dias_de_espera": 10**9}),
        _estragar(protecoes="stop"),
        _estragar(livres=["curta", "inventado"]),
        _estragar(livres=["tipo"]),
        _estragar(livres=["curta", "longa", "curta"]),
        _estragar(livres="curta"),
        _estragar(taxa_livre_de_risco=50.0),
        _estragar(usa_cdi="sim"),
        _estragar(tolerancia_de_queda=0.99),
        _estragar(tentativas_da_pessoa=0),
        _estragar(tentativas_da_pessoa=2.5),
        _estragar(tentativas_da_pessoa=True),
    ],
)
def test_pedido_guardado_hostil_e_recusado(guardado):
    with pytest.raises(ValueError):
        ficha.pedido_guardado(guardado, DADOS)


def _escolhas(estrategia):
    """Valores válidos para cada parâmetro da estratégia (números dentro da faixa)."""
    campos = {}
    for p in ESTRATEGIAS[estrategia].parametros:
        if p.opcoes:
            campos[p.nome] = st.sampled_from(p.opcoes)
        elif isinstance(p.padrao, int):
            campos[p.nome] = st.integers(p.minimo, p.maximo)
        else:
            campos[p.nome] = st.floats(p.minimo, p.maximo, allow_nan=False)
    return st.fixed_dictionaries(campos)


@st.composite
def _pedidos(draw):
    estrategia = draw(st.sampled_from(list(ESTRATEGIAS)))
    numericos = [p.nome for p in ESTRATEGIAS[estrategia].parametros if not p.opcoes]
    protecoes = draw(
        st.none()
        | st.builds(
            Protecoes,
            stop_loss=st.none() | st.floats(0.01, 0.5),
            stop_movel=st.none() | st.floats(0.01, 0.5),
            janela_atr=st.integers(2, 100),
            dias_de_espera=st.none() | st.integers(0, 60),
        )
    )
    return ficha.PedidoDaFicha(
        dados=DADOS,
        estrategia=estrategia,
        parametros=draw(_escolhas(estrategia)),
        custo_por_operacao=draw(st.floats(0, 0.05)),
        capital_inicial=draw(st.floats(1, 1e9)),
        protecoes=protecoes,
        livres=tuple(
            draw(st.lists(st.sampled_from(numericos), max_size=2, unique=True))
        )
        if numericos
        else (),
        taxa_livre_de_risco=draw(st.floats(-0.05, 0.5)),
        tolerancia_de_queda=draw(
            st.floats(ficha.TOLERANCIA_MINIMA, ficha.TOLERANCIA_MAXIMA)
        ),
        tentativas_da_pessoa=draw(st.integers(1, 1000)),
    )


@settings(max_examples=200)
@given(_pedidos())
def test_qualquer_pedido_valido_vai_e_volta(original):
    volta = ficha.pedido_guardado(
        _pela_base(ficha.pedido_para_guardar(original)), DADOS
    )
    assert _sem_dados(volta) == _sem_dados(original)
