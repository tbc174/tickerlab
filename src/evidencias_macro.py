"""Evidências macro (etapa 2 do desenho em `docs/desenho-achados-e-porques.md`): juros, inflação,
dólar e o que o mercado espera, cada número com a data em que ficou público.

Os números saem do mesmo painel da tela de Juros e inflação (`src/juros_e_inflacao.py`), lido do
acervo do Banco Central "como era conhecido" no dia pedido: um valor revisto ou uma decisão do Copom
divulgados depois desse dia não aparecem (sem olhar o futuro).

Dois tipos de evidência:
- **fato:** o nível do número (a meta da Selic é 15,00% ao ano), com a mesma frase da tela;
- **padrão:** a tendência em 12 meses por uma regra fixa e pública (subiu, caiu ou ficou estável),
  e a expectativa do Focus contra a Selic de hoje. Os limites das regras estão no topo do módulo e
  sobem de versão (`VERSAO_DAS_REGRAS`) quando mudarem.

Série que falta no acervo vira evidência "indisponível com motivo", e o resto continua.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import sqlalchemy as sa

from src import juros_e_inflacao as ji
from src.evidencias import FATO, MACRO, PADRAO, Evidencia

VERSAO_DAS_REGRAS = "1"  # sobe quando um limite ou um rótulo das regras abaixo mudar
LIMIAR_DOS_JUROS = 0.5  # pontos percentuais: menos que isso em 12 meses é "estável"
LIMIAR_DA_INFLACAO = 1.0  # pontos percentuais do IPCA em 12 meses
LIMIAR_DO_DOLAR = 0.10  # 10% em 12 meses
DIAS_NO_ANO = 365
SUBIU, CAIU, ESTAVEL = "subiu", "caiu", "estavel"
ESPERA_CORTE, ESPERA_ALTA, ESPERA_ESTABILIDADE = (
    "espera-corte",
    "espera-alta",
    "espera-estabilidade",
)
INDISPONIVEL = "indisponivel"
PONTOS = "pontos percentuais em 12 meses"
VARIACAO = "variação em 12 meses (fração)"
LIMITE_DO_PADRAO = (
    "A regra é fixa e pública: diz o que aconteceu com o número, não o que vai acontecer. "
    "Não é recomendação de compra ou venda."
)


@dataclass(frozen=True)
class _Tendencia:
    chave: str  # "selic", "ipca_12m", "dolar"
    nome: str
    antes: float
    agora: float
    rotulo: str
    variacao: float  # em pontos (juros e inflação) ou em fração (dólar)
    unidade: str
    limite: str  # a regra escrita, para os limites da evidência


def _regra(chave: str) -> str:
    return f"macro/{chave}@{VERSAO_DAS_REGRAS}"


def _indisponivel(chave: str, dia: date, motivo: str, fonte: str) -> Evidencia:
    """A evidência que falta, com o motivo na frase (sem número e sem data de divulgação)."""
    return Evidencia(
        id=f"macro.{chave}.{INDISPONIVEL}",
        tipo=MACRO,
        ativo=None,
        frase=motivo,
        valor=None,
        unidade="",
        data_de_corte=dia,
        divulgado_em=None,
        fonte=fonte,
        regra=_regra(chave),
        forca=FATO,
    )


def _rotulo(variacao: float, limiar: float) -> str:
    if variacao >= limiar:
        return SUBIU
    return CAIU if variacao <= -limiar else ESTAVEL


def _decimal(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")


# --- fatos: o nível, com a frase da tela -----------------------------------------------------------
def _nivel(numero: ji.Numero, chave: str, dia: date) -> Evidencia:
    if numero.valor is None or numero.divulgado_em is None:
        return _indisponivel(
            f"{chave}_nivel",
            dia,
            f"{numero.nome}: sem dado no acervo nesta data.",
            numero.fonte,
        )
    return Evidencia(
        id=f"macro.{chave}.nivel",
        tipo=MACRO,
        ativo=None,
        frase=f"{numero.nome}: {ji.formatar_valor(numero)} ({ji.legenda(numero)}).",
        valor=numero.valor,
        unidade=numero.unidade,
        data_de_corte=dia,
        divulgado_em=numero.divulgado_em,
        fonte=numero.fonte,
        regra=_regra(f"{chave}_nivel"),
        forca=FATO,
    )


def _numero(painel: ji.PainelDeJuros, nome: str) -> ji.Numero:
    return next(n for n in painel.numeros if n.nome == nome)


# --- padrões: a tendência em 12 meses --------------------------------------------------------------
def _um_ano_antes(serie: pd.Series) -> float | None:
    """O valor vigente um ano antes da última referência, ou None sem histórico suficiente."""
    alvo = serie.index[-1] - timedelta(days=DIAS_NO_ANO)
    if serie.index[0] > alvo:
        return None
    return float(serie.asof(alvo))


def _evidencia_da_tendencia(
    t: _Tendencia, divulgado_em: date, fonte: str, dia: date
) -> Evidencia:
    verbo = {SUBIU: "subiu", CAIU: "caiu", ESTAVEL: "ficou estável"}[t.rotulo]
    if t.unidade == PONTOS:
        mudanca = f"{_decimal(abs(t.variacao))} ponto(s)"
        de_para = f"de {_decimal(t.antes)}% para {_decimal(t.agora)}%"
    else:
        mudanca = f"{_decimal(abs(t.variacao) * 100)}%"
        de_para = f"de R$ {_decimal(t.antes)} para R$ {_decimal(t.agora)}"
    frase = (
        f"{t.nome} {verbo} em 12 meses ({mudanca}): {de_para}."
        if t.rotulo != ESTAVEL
        else f"{t.nome} {verbo} em 12 meses: {de_para}."
    )
    return Evidencia(
        id=f"macro.{t.chave}.{t.rotulo}",
        tipo=MACRO,
        ativo=None,
        frase=frase,
        valor=t.variacao,
        unidade=t.unidade,
        data_de_corte=dia,
        divulgado_em=divulgado_em,
        fonte=fonte,
        regra=_regra(f"{t.chave}_tendencia"),
        forca=PADRAO,
        limites=(t.limite, LIMITE_DO_PADRAO),
    )


def _tendencia_da_selic(lidas: dict[str, ji.SerieLida], dia: date) -> Evidencia:
    fonte = ji.FONTE_SGS.format(432)
    lida = lidas.get(ji.SELIC_META)
    antes = None if lida is None else _um_ano_antes(lida.valores)
    if lida is None or antes is None or lida.divulgado_em is None:
        return _indisponivel(
            "selic",
            dia,
            "Meta da Selic: menos de 12 meses de histórico nesta data.",
            fonte,
        )
    agora = float(lida.valores.iloc[-1])
    limite = f"Subida ou queda: {_decimal(LIMIAR_DOS_JUROS)} ponto ou mais em 12 meses."
    tendencia = _Tendencia(
        "selic", ji.NOME_SELIC, antes, agora,
        _rotulo(agora - antes, LIMIAR_DOS_JUROS), agora - antes, PONTOS, limite,
    )  # fmt: skip
    return _evidencia_da_tendencia(tendencia, lida.divulgado_em, fonte, dia)


def _tendencia_do_ipca(
    painel: ji.PainelDeJuros, lidas: dict[str, ji.SerieLida], dia: date
) -> Evidencia:
    fonte = ji.FONTE_SGS.format(433)
    acumulado = pd.Series(
        {pd.Timestamp(p.mes): p.ipca_12_meses for p in painel.historico}, dtype=float
    ).dropna()
    lida = lidas.get(ji.IPCA)
    antes = None if acumulado.empty else _um_ano_antes(acumulado)
    if lida is None or antes is None or lida.divulgado_em is None:
        return _indisponivel(
            "ipca_12m",
            dia,
            "IPCA em 12 meses: menos de 2 anos de IPCA nesta data.",
            fonte,
        )
    agora = float(acumulado.iloc[-1])
    limite = (
        f"Subida ou queda: {_decimal(LIMIAR_DA_INFLACAO)} ponto ou mais em 12 meses."
    )
    tendencia = _Tendencia(
        "ipca_12m", ji.NOME_IPCA_12M, antes, agora,
        _rotulo(agora - antes, LIMIAR_DA_INFLACAO), agora - antes, PONTOS, limite,
    )  # fmt: skip
    return _evidencia_da_tendencia(tendencia, lida.divulgado_em, fonte, dia)


def _tendencia_do_dolar(lidas: dict[str, ji.SerieLida], dia: date) -> Evidencia:
    fonte = ji.FONTE_SGS.format(1)
    lida = lidas.get(ji.DOLAR)
    antes = None if lida is None else _um_ano_antes(lida.valores)
    if lida is None or not antes or lida.divulgado_em is None:
        return _indisponivel(
            "dolar",
            dia,
            "Dólar comercial: menos de 12 meses de histórico nesta data.",
            fonte,
        )
    agora = float(lida.valores.iloc[-1])
    variacao = agora / antes - 1
    limite = f"Subida ou queda: {_decimal(LIMIAR_DO_DOLAR * 100)}% ou mais em 12 meses."
    tendencia = _Tendencia(
        "dolar", ji.NOME_DOLAR, antes, agora,
        _rotulo(variacao, LIMIAR_DO_DOLAR), variacao, VARIACAO, limite,
    )  # fmt: skip
    return _evidencia_da_tendencia(tendencia, lida.divulgado_em, fonte, dia)


# --- padrão: o que o Focus espera para a Selic no fim do ano ---------------------------------------
def _rotulo_do_focus(diferenca: float) -> str:
    if diferenca <= -LIMIAR_DOS_JUROS:
        return ESPERA_CORTE
    return ESPERA_ALTA if diferenca >= LIMIAR_DOS_JUROS else ESPERA_ESTABILIDADE


def _focus_da_selic(painel: ji.PainelDeJuros, dia: date) -> Evidencia:
    selic = _numero(painel, ji.NOME_SELIC)
    esperada = next(
        (
            e
            for e in painel.expectativas
            if e.indicador == "Selic" and e.ano == dia.year
        ),
        None,
    )
    if esperada is None or esperada.pesquisa is None or selic.valor is None:
        return _indisponivel(
            "focus_selic", dia, "Focus: sem a expectativa da Selic para este ano nesta data.",
            ji.FONTE_FOCUS,
        )  # fmt: skip
    diferenca = esperada.mediana - selic.valor
    frase = (
        f"O mercado espera a Selic em {_decimal(esperada.mediana)}% no fim de {esperada.ano} "
        f"(Focus de {esperada.pesquisa:%d/%m/%Y}), contra {_decimal(selic.valor)}% hoje."
    )
    return Evidencia(
        id=f"macro.focus_selic.{_rotulo_do_focus(diferenca)}",
        tipo=MACRO,
        ativo=None,
        frase=frase,
        valor=diferenca,
        unidade="pontos percentuais (esperada − atual)",
        data_de_corte=dia,
        divulgado_em=esperada.pesquisa,
        fonte=ji.FONTE_FOCUS,
        regra=_regra("focus_selic"),
        forca=PADRAO,
        limites=(
            ji.NOTA_DO_FOCUS,
            f"Corte ou alta esperados: {_decimal(LIMIAR_DOS_JUROS)} ponto ou mais.",
            LIMITE_DO_PADRAO,
        ),
    )


# --- entrada -------------------------------------------------------------------------------------
def evidencias_macro(lidas: dict[str, ji.SerieLida], dia: date) -> list[Evidencia]:
    """As evidências macro a partir das séries lidas "como eram conhecidas" em `dia`."""
    painel = ji.montar_painel(lidas, None, dia)
    construtores: tuple[Callable[[], Evidencia], ...] = (
        lambda: _nivel(_numero(painel, ji.NOME_SELIC), "selic", dia),
        lambda: _tendencia_da_selic(lidas, dia),
        lambda: _nivel(_numero(painel, ji.NOME_IPCA_12M), "ipca_12m", dia),
        lambda: _tendencia_do_ipca(painel, lidas, dia),
        lambda: _tendencia_do_dolar(lidas, dia),
        lambda: _focus_da_selic(painel, dia),
    )
    return [construir() for construir in construtores]


def evidencias_macro_em(conexao: sa.Connection, dia: date) -> list[Evidencia]:
    """As evidências macro só com o que o acervo do Banco Central conhecia no fim de `dia`."""
    return evidencias_macro(ji.ler_series(conexao, dia), dia)
