"""Alertas compostos do Research (etapa 6, PRD 6.2 e 7.1): regras com várias condições.

Exemplo do PRD: "média móvel semanal de alta **e** preço diário abaixo do limite configurado". Uma
regra junta até `MAXIMO_DE_CONDICOES` condições, todas ("e") ou qualquer uma ("ou"); cada condição
olha o diário ou o semanal.

Regras de honestidade (PRD 7.1 e 6.2):
- toda condição mostra **horizonte** (diário ou semanal), **atraso** (o fechamento usado; o alerta
  só vale a partir do pregão seguinte) e se havia **dados suficientes**;
- sem dados suficientes a condição fica "indisponível" e a regra não dispara (nunca vira "sim");
- semana ainda não terminada é avisada (a última barra semanal pode mudar até sexta);
- alerta é contexto, não ordem: não diz que algo vai acontecer.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from src import indicadores as ind

DIARIO, SEMANAL = "diario", "semanal"
TODAS, QUALQUER = "todas", "qualquer"
MAXIMO_DE_CONDICOES = 4
SEXTA = 4  # weekday() da sexta-feira


@dataclass(frozen=True)
class TipoDeCondicao:
    chave: str
    rotulo: str  # como aparece na lista
    janela_padrao: int | None  # None: a condição não usa janela
    limiar_padrao: float | None  # None: a condição não usa limiar
    unidade_do_limiar: str  # "preço", "%", "pontos", "×"
    explicacao: str


TIPOS = {
    t.chave: t
    for t in (
        TipoDeCondicao(
            "preco_acima_da_media",
            "Preço acima da média móvel",
            50,
            None,
            "",
            "O fechamento está acima da média simples da janela.",
        ),
        TipoDeCondicao(
            "preco_abaixo_da_media",
            "Preço abaixo da média móvel",
            50,
            None,
            "",
            "O fechamento está abaixo da média simples da janela.",
        ),
        TipoDeCondicao(
            "media_de_alta",
            "Média rápida acima da lenta (tendência de alta)",
            50,
            200.0,
            "",
            "A média da janela está acima da média do limiar (em barras).",
        ),
        TipoDeCondicao(
            "preco_abaixo_de",
            "Preço abaixo de um valor",
            None,
            30.0,
            "preço",
            "O fechamento está abaixo do valor escolhido.",
        ),
        TipoDeCondicao(
            "preco_acima_de",
            "Preço acima de um valor",
            None,
            30.0,
            "preço",
            "O fechamento está acima do valor escolhido.",
        ),
        TipoDeCondicao(
            "rsi_abaixo",
            "RSI abaixo de",
            14,
            30.0,
            "pontos",
            "RSI baixo: o preço caiu na maioria das barras recentes.",
        ),
        TipoDeCondicao(
            "rsi_acima",
            "RSI acima de",
            14,
            70.0,
            "pontos",
            "RSI alto: o preço subiu na maioria das barras recentes.",
        ),
        TipoDeCondicao(
            "adx_acima",
            "ADX acima de (há tendência)",
            14,
            25.0,
            "pontos",
            "ADX alto: há tendência (de alta ou de baixa).",
        ),
        TipoDeCondicao(
            "volume_relativo_acima",
            "Volume relativo acima de",
            20,
            2.0,
            "×",
            "Volume da barra contra a média das anteriores.",
        ),
        TipoDeCondicao(
            "queda_do_topo",
            "Queda desde o topo maior que",
            60,
            10.0,
            "%",
            "Quanto o preço está abaixo da máxima de fechamento da janela.",
        ),
        TipoDeCondicao(
            "volatilidade_acima",
            "Volatilidade anual acima de",
            20,
            40.0,
            "%",
            "Volatilidade das barras da janela, anualizada.",
        ),
    )
}


@dataclass(frozen=True)
class Condicao:
    tipo: str
    periodicidade: str = DIARIO
    janela: int | None = None
    limiar: float | None = None

    def descrever(self) -> str:
        t = TIPOS[self.tipo]
        partes = [t.rotulo]
        if self.limiar is not None and t.chave != "media_de_alta":
            unidade = {"preço": "", "pontos": "", "%": "%", "×": "×"}[
                t.unidade_do_limiar
            ]
            partes.append(f"{self.limiar:g}{unidade}".replace(".", ","))
        if self.janela is not None:
            unidade = "semanas" if self.periodicidade == SEMANAL else "pregões"
            janela = (
                f"{self.janela} e {self.limiar:g}"
                if t.chave == "media_de_alta"
                else self.janela
            )
            partes.append(f"(janela {janela} {unidade})")
        partes.append("· semanal" if self.periodicidade == SEMANAL else "· diário")
        return " ".join(partes)


@dataclass(frozen=True)
class Regra:
    nome: str
    condicoes: tuple[Condicao, ...]
    modo: str = TODAS

    def para_guardar(self) -> dict:
        return {
            "modo": self.modo,
            "condicoes": [
                {"tipo": c.tipo, "periodicidade": c.periodicidade, "janela": c.janela,
                 "limiar": c.limiar}
                for c in self.condicoes
            ],
        }  # fmt: skip

    @staticmethod
    def de_guardada(nome: str, guardada: dict) -> "Regra":
        return Regra(
            nome=nome,
            modo=guardada.get("modo", TODAS),
            condicoes=tuple(Condicao(**c) for c in guardada.get("condicoes", [])),
        )


class RegraInvalidaError(ValueError):
    """A regra não pode ser salva: falta condição, tipo desconhecido, janela ou limiar fora."""


def validar(regra: Regra) -> Regra:
    """Confere a regra e completa janela e limiar com os padrões do tipo."""
    if not regra.nome.strip():
        raise RegraInvalidaError("Dê um nome ao alerta.")
    if not 1 <= len(regra.condicoes) <= MAXIMO_DE_CONDICOES:
        raise RegraInvalidaError(
            f"Um alerta tem de 1 a {MAXIMO_DE_CONDICOES} condições."
        )
    if regra.modo not in (TODAS, QUALQUER):
        raise RegraInvalidaError("Modo desconhecido.")
    completas = []
    for c in regra.condicoes:
        if c.tipo not in TIPOS:
            raise RegraInvalidaError(f"Condição desconhecida: {c.tipo}.")
        if c.periodicidade not in (DIARIO, SEMANAL):
            raise RegraInvalidaError("Periodicidade desconhecida.")
        t = TIPOS[c.tipo]
        janela = c.janela if c.janela is not None else t.janela_padrao
        limiar = c.limiar if c.limiar is not None else t.limiar_padrao
        if janela is not None and not 2 <= int(janela) <= 500:
            raise RegraInvalidaError("A janela vai de 2 a 500.")
        if limiar is not None and not pd.notna(limiar):
            raise RegraInvalidaError("Limiar inválido.")
        completas.append(
            Condicao(
                c.tipo,
                c.periodicidade,
                None if t.janela_padrao is None else int(janela),
                None if t.limiar_padrao is None else float(limiar),
            )
        )
    return Regra(" ".join(regra.nome.split())[:80], tuple(completas), regra.modo)


# --- avaliação -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class Avaliacao:
    condicao: Condicao
    satisfeita: bool | None  # None: dados insuficientes
    valor: float | None
    barra: date | None  # a barra (fechamento) usada
    motivo: str = ""
    aviso: str = ""  # ex.: semana em andamento


@dataclass(frozen=True)
class ResultadoDaRegra:
    regra: Regra
    disparou: bool | None  # None: alguma condição necessária sem dados
    avaliacoes: tuple[Avaliacao, ...] = field(default_factory=tuple)

    @property
    def atraso(self) -> str:
        barras = [a.barra for a in self.avaliacoes if a.barra is not None]
        if not barras:
            return "Sem dados."
        return (
            f"Usa o fechamento de {max(barras):%d/%m/%Y}; um alerta só vale a partir do pregão "
            "seguinte."
        )


def _ultimo(serie: pd.Series) -> float | None:
    serie = serie.dropna()
    return None if serie.empty else float(serie.iloc[-1])


def _medida(c: Condicao, barras: pd.DataFrame) -> float | None:
    fechamento = barras["Close"]
    calculos: dict[str, Callable[[], pd.Series]] = {
        "preco_acima_da_media": lambda: (
            fechamento / ind.calcular_media_movel(fechamento, c.janela)
        ),
        "preco_abaixo_da_media": lambda: (
            fechamento / ind.calcular_media_movel(fechamento, c.janela)
        ),
        "media_de_alta": lambda: (
            ind.calcular_media_movel(fechamento, c.janela)
            / ind.calcular_media_movel(fechamento, int(c.limiar))
        ),
        "preco_abaixo_de": lambda: fechamento,
        "preco_acima_de": lambda: fechamento,
        "rsi_abaixo": lambda: ind.calcular_rsi(fechamento, c.janela),
        "rsi_acima": lambda: ind.calcular_rsi(fechamento, c.janela),
        "adx_acima": lambda: ind.calcular_adx(barras, c.janela)["adx"],
        "volume_relativo_acima": lambda: ind.calcular_volume_relativo(barras, c.janela),
        "queda_do_topo": lambda: (
            (fechamento / fechamento.rolling(c.janela).max() - 1) * -100
        ),
        "volatilidade_acima": lambda: (
            ind.calcular_volatilidade_movel(
                ind.calcular_retorno_diario(fechamento), c.janela
            )
            * 100
            / (1 if c.periodicidade == DIARIO else (ind.DIAS_POR_ANO / 52) ** 0.5)
        ),
    }
    return _ultimo(calculos[c.tipo]())


def _comparar(c: Condicao, valor: float) -> bool:
    if c.tipo in ("preco_acima_da_media", "media_de_alta"):
        return valor > 1
    if c.tipo == "preco_abaixo_da_media":
        return valor < 1
    if c.tipo in ("preco_abaixo_de", "rsi_abaixo"):
        return valor < c.limiar
    return valor > c.limiar  # acima de / queda maior que / volatilidade acima


def _semana_em_andamento(diarios: pd.DataFrame) -> str:
    ultimo = diarios.index[-1]
    if ultimo.weekday() < SEXTA:
        return f"A semana da última barra ainda não terminou (dados até {ultimo:%d/%m/%Y})."
    return ""


def _precisa(c: Condicao) -> int:
    """Quantas barras a condição precisa para ter valor."""
    janela = c.janela or 1
    if c.tipo == "media_de_alta":
        janela = max(janela, int(c.limiar))
    if c.tipo == "adx_acima":
        janela *= 2
    return janela + 1


def avaliar_condicao(c: Condicao, diarios: pd.DataFrame) -> Avaliacao:
    """A condição na última barra (diária ou semanal) dos dados, sem olhar o futuro."""
    barras = ind.para_semanal(diarios) if c.periodicidade == SEMANAL else diarios
    aviso = _semana_em_andamento(diarios) if c.periodicidade == SEMANAL else ""
    precisa = _precisa(c)
    if len(barras) < precisa:
        unidade = "semanas" if c.periodicidade == SEMANAL else "pregões"
        return Avaliacao(
            c, None, None, None,
            f"Há {len(barras)} {unidade} e a condição precisa de {precisa}.", aviso,
        )  # fmt: skip
    if c.tipo in ("adx_acima",) and not {"High", "Low"} <= set(barras.columns):
        return Avaliacao(
            c, None, None, None, "Os dados não têm máxima e mínima.", aviso
        )
    if c.tipo == "volume_relativo_acima" and "Volume" not in barras.columns:
        return Avaliacao(c, None, None, None, "Os dados não têm volume.", aviso)
    valor = _medida(c, barras)
    barra = barras.index[-1].date()
    if valor is None:
        return Avaliacao(
            c, None, None, barra, "Não há dados suficientes para calcular.", aviso
        )
    return Avaliacao(c, _comparar(c, valor), valor, barra, "", aviso)


def avaliar(regra: Regra, diarios: pd.DataFrame) -> ResultadoDaRegra:
    """A regra inteira num ativo. "Todas": dispara se todas forem satisfeitas (sem dados em uma,
    não dispara e fica indisponível). "Qualquer": dispara se uma for satisfeita."""
    avaliacoes = tuple(avaliar_condicao(c, diarios) for c in regra.condicoes)
    estados = [a.satisfeita for a in avaliacoes]
    if regra.modo == QUALQUER:
        disparou = (
            True
            if any(e is True for e in estados)
            else (None if any(e is None for e in estados) else False)
        )
    else:
        disparou = (
            False
            if any(e is False for e in estados)
            else (None if any(e is None for e in estados) else True)
        )
    return ResultadoDaRegra(regra, disparou, avaliacoes)
