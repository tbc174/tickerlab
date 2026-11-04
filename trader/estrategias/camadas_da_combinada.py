"""As camadas da ficha C-1 (pré-registro quant v0.2, seção 9), rodadas de novo com o código da main.

Cada camada é a configuração de uma linha do registro, com o mesmo carregador e a mesma simulação do
rodador dela, mas **sem registrar nada**: quem conta a tentativa é a C-1 (`rodar_c1`). Para cada
camada saem três séries, como o rodador dela faz: a base (custos da seção 3), o estresse (custos × 2
e impacto Y = 2) e o bruto (sem custo, imposto nem impacto).

Convenção fixada aqui, antes de qualquer número da C-1: a série de cada camada é **a série que o
registro avaliou** (o período do Sharpe do excesso gravado). Na P0-5 isso começa no primeiro pregão
com posição (`rodar_pead.periodo_de_avaliacao`); nas outras, no primeiro retorno da simulação. O
Sharpe do excesso de cada camada sai pela definição do rodador dela (a P0-1, por exemplo, compõe os
dias corridos em dias úteis), e a C-1 confere que ele reproduz o número gravado.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from trader import avaliacao, criterio_quant
from trader.estrategias import (
    carteira_rp,
    dados_f_b3,
    dados_pares,
    dados_pead,
    pares,
    pead,
    rodar_p0_3,
    rodar_pead,
    rodar_tendencia_b3,
    rodar_tendencia_cripto,
)
from trader.estrategias import fatores_b3 as fb
from trader.estrategias import tendencia_b3 as tb
from trader.estrategias import tendencia_cripto as tc
from trader.holdout import exigir_sem_holdout

FATOR = criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE
# As linhas 5, 11, 12 e 14 do registro foram refeitas dos relatórios (o original se perdeu em
# 03/11/2026) e guardam o Sharpe do excesso com duas casas: reproduzir é cair no mesmo arredondamento.
ARREDONDADO_EM_DUAS_CASAS = 0.005
EXATO = 1e-9


@dataclass(frozen=True)
class Registrado:
    """O Sharpe do excesso que a linha do registro gravou para a camada."""

    linha: int
    sharpe: float
    tolerancia: float


REGISTRADO = {
    "P0-3": Registrado(5, 0.41, ARREDONDADO_EM_DUAS_CASAS),
    "F-B3": Registrado(17, -0.030656850019758854, EXATO),
    "P0-1": Registrado(11, 0.68, ARREDONDADO_EM_DUAS_CASAS),
    "P0-2 BOVA11": Registrado(12, -0.16, ARREDONDADO_EM_DUAS_CASAS),
    "P0-2 DI1": Registrado(12, 0.44, ARREDONDADO_EM_DUAS_CASAS),
    "P0-4": Registrado(14, 0.05, ARREDONDADO_EM_DUAS_CASAS),
    "P0-5": Registrado(16, 0.0788694656791887, EXATO),
}


@dataclass(frozen=True)
class Camada:
    """As três séries de uma camada, líquidas e sem freio, no calendário dela."""

    nome: str
    base: pd.Series
    estresse: pd.Series
    bruto: pd.Series
    cdi: pd.Series  # o caixa da camada, no calendário dela
    sharpe: float  # Sharpe do excesso pela definição do rodador da camada
    conforme: bool = (
        True  # dados sem viés de sobrevivência (as camadas de ações da B3 conferem)
    )


@dataclass(frozen=True)
class Camadas:
    camadas: dict[str, Camada]
    regua_60_40: pd.Series  # a régua da ficha, como a P0-3 a roda


def reproduz(camada: Camada) -> bool:
    """O Sharpe do excesso da reexecução bate com o gravado no registro?"""
    gravado = REGISTRADO[camada.nome]
    return abs(camada.sharpe - gravado.sharpe) <= gravado.tolerancia + EXATO


def hash_da_serie(camada: Camada) -> str:
    """Impressão digital da série base: a rodada seguinte confere se os dados da camada mudaram."""
    base = camada.base.dropna().round(12)
    conteudo = base.index.asi8.tobytes() + base.to_numpy().tobytes()
    return hashlib.sha256(conteudo).hexdigest()


def _excesso(retorno: pd.Series, cdi: pd.Series) -> pd.Series:
    return retorno - cdi.reindex(retorno.index)


def _no_periodo(retorno: pd.Series, periodo: pd.Index, cdi: pd.Series) -> pd.Series:
    """Leituras que começam noutro dia ficam no período da base, com CDI antes (como nos rodadores)."""
    return retorno.reindex(periodo).fillna(cdi.reindex(periodo))


def _conferir(*tabelas: pd.DataFrame | pd.Series) -> None:
    for tabela in tabelas:
        exigir_sem_holdout(tabela)


def camada_p0_3() -> tuple[Camada, pd.Series]:
    """P0-3, risk parity a 1,0x (linha 5), e a régua 60/40 da mesma rodada."""
    precos, cdi, volumes = rodar_p0_3.carregar_tabelas()
    parametros = carteira_rp.Parametros(esquema=rodar_p0_3.CANDIDATO)

    def rodar(p: carteira_rp.Parametros) -> pd.Series:
        return carteira_rp.simular(precos, cdi, volumes, p).retorno

    base = rodar(parametros)
    camada = Camada(
        nome="P0-3",
        base=base,
        estresse=rodar(
            carteira_rp.com(
                parametros,
                custos=parametros.custos.em_estresse(FATOR),
                fator_de_impacto=FATOR,
            )
        ),
        bruto=rodar(
            carteira_rp.com(
                parametros, custos=carteira_rp.SEM_CUSTOS, fator_de_impacto=0.0
            )
        ),
        cdi=cdi,
        sharpe=avaliacao.sharpe(_excesso(base, cdi)),
    )
    return camada, rodar(carteira_rp.REGUA_60_40)


def camada_f_b3() -> Camada:
    """F-B3, fatores na B3 (linha 17)."""
    dados = dados_f_b3.carregar_tabelas()
    parametros = fb.Parametros()

    def rodar(p: fb.Parametros) -> pd.Series:
        return fb.simular(dados, p).retorno

    base = rodar(parametros)
    return Camada(
        nome="F-B3",
        base=base,
        estresse=rodar(
            fb.com(
                parametros,
                custos=parametros.custos.em_estresse(FATOR),
                fator_de_impacto=FATOR,
            )
        ),
        bruto=rodar(fb.com(parametros, custos=fb.SEM_CUSTOS, fator_de_impacto=0.0)),
        cdi=dados.cdi,
        sharpe=avaliacao.sharpe(_excesso(base, dados.cdi)),
        conforme=not fb.conferir_sobrevivencia(dados).vies,
    )


def camada_p0_1() -> Camada:
    """P0-1, tendência em BTC e ETH em USDT × PTAX (linha 11), em dias corridos."""
    precos, cdi, volumes = rodar_tendencia_cripto.carregar_tabelas()
    parametros = tc.Parametros()

    def rodar(p: tc.Parametros) -> pd.Series:
        return tc.simular(precos, cdi, volumes, p, tc.CAPITAL_INICIAL).retorno

    base = rodar(parametros)
    return Camada(
        nome="P0-1",
        base=base,
        estresse=rodar(parametros.em_estresse(FATOR)),
        bruto=rodar(
            tc.com(
                parametros,
                custos=tc.SEM_CUSTOS,
                fator_de_impacto=0.0,
                com_cambio=False,
            )
        ),
        cdi=cdi,
        sharpe=tc.sharpe_do_excesso(base, cdi),
    )


def camadas_p0_2() -> dict[str, Camada]:
    """P0-2 (linha 12): a versão BOVA11 (candidata) e a DI1 (comparação)."""
    versoes, cdi = rodar_tendencia_b3.carregar_tabelas()
    parametros = tb.Parametros()
    camadas = {}
    for versao in ("BOVA11", "DI1"):

        def rodar(p: tb.Parametros, ativo: tb.Ativo = versoes[versao]) -> pd.Series:
            return tb.simular(ativo, cdi, p, tb.CAPITAL_INICIAL).retorno

        base = rodar(parametros)
        nome = f"P0-2 {versao}"
        camadas[nome] = Camada(
            nome=nome,
            base=base,
            estresse=rodar(parametros.em_estresse(FATOR)),
            bruto=rodar(
                tb.com(
                    parametros,
                    custos=tb.SEM_CUSTOS,
                    fator_de_impacto=0.0,
                    spread_do_futuro_por_lado=0.0,
                )
            ),
            cdi=cdi,
            sharpe=tb.sharpe_do_excesso(base, cdi),
        )
    return camadas


def camada_p0_4() -> Camada:
    """P0-4, pares na B3 (linha 14)."""
    dados = dados_pares.carregar_tabelas(dados_pares.PASTA_DA_FICHA)
    parametros = pares.Parametros()
    cache: dict = {}

    def rodar(p: pares.Parametros) -> pd.Series:
        return pares.simular(dados, p, cache).retorno

    base = rodar(parametros)
    periodo = base.index
    return Camada(
        nome="P0-4",
        base=base,
        estresse=_no_periodo(
            rodar(
                pares.com(
                    parametros,
                    custos=parametros.custos.em_estresse(FATOR),
                    fator_de_impacto=FATOR,
                )
            ),
            periodo,
            dados.cdi,
        ),
        bruto=_no_periodo(
            rodar(
                pares.com(
                    parametros,
                    custos=pares.SEM_CUSTOS,
                    fator_de_impacto=0.0,
                    taxa_do_aluguel=0.0,
                )
            ),
            periodo,
            dados.cdi,
        ),
        cdi=dados.cdi,
        sharpe=avaliacao.sharpe(_excesso(base, dados.cdi)),
        conforme=not fb.conferir_sobrevivencia(dados).vies,
    )


def camada_p0_5() -> Camada:
    """P0-5, PEAD na B3 (linha 16), do primeiro pregão com posição em diante."""
    dados = dados_pead.carregar_tabelas(
        dados_pead.PASTA_DA_FICHA, dados_pead.PASTA_DO_ACERVO
    )
    parametros = pead.Parametros()
    eventos = pead.eventos_de_lucro(pead._so_o_lucro(dados), parametros)

    def rodar(p: pead.Parametros) -> pead.Resultado:
        return pead.simular(dados, p, *eventos)

    candidato = rodar(parametros)
    periodo = rodar_pead.periodo_de_avaliacao(candidato)

    def serie(p: pead.Parametros) -> pd.Series:
        return rodar(p).retorno.reindex(periodo)

    base = candidato.retorno.reindex(periodo)
    return Camada(
        nome="P0-5",
        base=base,
        estresse=serie(
            pead.com(
                parametros,
                custos=parametros.custos.em_estresse(FATOR),
                fator_de_impacto=FATOR,
            )
        ),
        bruto=serie(pead.com(parametros, custos=pead.SEM_CUSTOS, fator_de_impacto=0.0)),
        cdi=dados.cdi,
        sharpe=avaliacao.sharpe(_excesso(base, dados.cdi)),
        conforme=not fb.conferir_sobrevivencia(dados).vies,
    )


def montar(avisar: Callable[[str], None] = print) -> Camadas:
    """Roda as sete séries (seis da candidata e o DI1 da comparação), só com o desenvolvimento."""
    p0_3, regua = camada_p0_3()
    avisar("P0-3 pronta")
    camadas = {"P0-3": p0_3}
    for montar_camada in (camada_p0_1, camada_f_b3, camada_p0_4, camada_p0_5):
        camada = montar_camada()
        camadas[camada.nome] = camada
        avisar(f"{camada.nome} pronta")
    camadas.update(camadas_p0_2())
    avisar("P0-2 pronta")
    for camada in camadas.values():
        _conferir(camada.base, camada.estresse, camada.bruto)
    _conferir(regua)
    return Camadas(camadas=camadas, regua_60_40=regua)
