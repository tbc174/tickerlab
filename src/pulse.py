"""O Pulse: o que mudou nos ativos da pessoa desde a última vez que ela o abriu (onda 3, PR E).

Junta, numa janela "desde a última visita", o que outras partes do app já calculam:
- os **acontecimentos** coletados depois da visita (CVM e SEC), na mesma ordem de relevância do
  Research e da Newsletter (`research.ordenar`);
- a **variação** do preço de cada ativo, do último fechamento conhecido na hora da visita até o
  último fechamento de hoje (sem olhar o futuro: um preço que ainda não existia na hora da visita
  nunca vira a base).

Nas estratégias salvas (backtests salvos com o pedido da ficha, PR E2), mostra o **veredito da
ficha "Foi sorte?" que mudou** com os dados de hoje.

Os ativos da pessoa são tudo o que ela guardou: favoritos, a carteira do Research (Pro), as listas
e os ativos das estratégias salvas. Tudo aqui é função pura em tipos simples (ADR 0044): a tela só
lê do banco, chama e mostra. Nada é recomendação.
"""

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from src import diario_de_teses, ficha, research
from src.banco.eventos import Evento
from src.cdi import CDIIndisponivelError
from src.dados import DadosIndisponiveisError, normalizar_ticker
from src.ficha import Resultado
from src.simulacoes import restaurar_estado

FUSO = ZoneInfo("America/Sao_Paulo")
JANELA_DA_PRIMEIRA_VISITA = timedelta(days=7)
# o app novo reenvia, no F5, o início da janela que a aba mostrava: nunca antes disto
JANELA_MAXIMA_DA_ABA = timedelta(days=30)
# um documento entregue um pouco antes da visita pode ser coletado depois dela; mais velho que
# isso é carga antiga (não é novidade para a pessoa)
PUBLICADOS_ATE_ANTES_DA_VISITA = timedelta(days=30)
# a partir desta hora (São Paulo) o fechamento do dia já existe (B3 fecha às 17h, EUA às 17h)
HORA_DO_FECHAMENTO = 18
TAMANHO_MAXIMO_DO_TICKER = 20  # o mesmo das tabelas do banco
# cada ativo é um download de preços: a página não pode ficar lenta
MAXIMO_DE_ATIVOS = 30
NOME_DOS_FAVORITOS = "favoritos"
NOME_DA_CARTEIRA = research.NOME_DA_CARTEIRA
NOME_DAS_ESTRATEGIAS = "estratégias salvas"
LIMITES = (
    (
        "Os acontecimentos vêm de documentos públicos entregues à CVM e à SEC, coletados uma "
        "vez por dia; um documento pode chegar com atraso ou ser corrigido depois."
    ),
    (
        "A variação usa o fechamento do Yahoo Finance, que pode ter atraso ou erros, e não "
        "inclui proventos."
    ),
    (
        'O veredito das estratégias salvas é a ficha "Foi sorte?" refeita com os preços de '
        "hoje, como no Backtest; a cada visita, só as 10 salvas mais recentemente são conferidas."
    ),
    "O Pulse mostra o que mudou, não o que fazer: nada aqui é recomendação de investimento.",
)


log = logging.getLogger(__name__)


def _codigo(ticker: str) -> str:
    return ticker.removesuffix(".SA")


# --- janela ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Janela:
    desde: datetime  # a última visita (ou 7 dias atrás, na primeira)
    ate: datetime  # agora, na hora em que a página foi aberta
    primeira_vez: bool
    guardada_na_aba: bool = (
        False  # o app novo voltou ao início que a aba já mostrava (F5)
    )

    @property
    def publicados_desde(self) -> date:
        return (self.desde - PUBLICADOS_ATE_ANTES_DA_VISITA).astimezone(FUSO).date()


def janela(ultima_visita: datetime | None, agora: datetime) -> Janela:
    """A janela do Pulse: da última visita até agora (na primeira vez, os últimos 7 dias)."""
    if agora.tzinfo is None or (
        ultima_visita is not None and ultima_visita.tzinfo is None
    ):
        raise ValueError("As horas do Pulse precisam ter fuso.")
    if ultima_visita is None:
        return Janela(agora - JANELA_DA_PRIMEIRA_VISITA, agora, primeira_vez=True)
    return Janela(min(ultima_visita, agora), agora, primeira_vez=False)


def janela_da_aba(
    ultima_visita: datetime | None, agora: datetime, desde: datetime | None
) -> Janela:
    """A janela do app novo, que não guarda sessão no servidor: abrir o Pulse marca a visita, e
    o F5 da mesma aba reenvia o início que ela mostrava (`desde`), para a janela não zerar.

    `desde` só amplia a janela (nunca a encurta) e nunca volta mais de 30 dias.
    """
    j = janela(ultima_visita, agora)
    if desde is None:
        return j
    if desde.tzinfo is None:
        raise ValueError("As horas do Pulse precisam ter fuso.")
    inicio = max(desde, agora - JANELA_MAXIMA_DA_ABA)
    if inicio >= j.desde:
        return j
    return Janela(inicio, agora, primeira_vez=False, guardada_na_aba=True)


def texto_da_janela(j: Janela) -> str:
    if j.guardada_na_aba:
        desde = j.desde.astimezone(FUSO)
        return (
            f"O que mudou desde {desde:%d/%m/%Y} às {desde:%Hh%M} "
            "(a janela que esta aba já mostrava)."
        )
    if j.primeira_vez:
        return (
            "Primeira visita: o que aconteceu nos últimos "
            f"{JANELA_DA_PRIMEIRA_VISITA.days} dias."
        )
    desde = j.desde.astimezone(FUSO)
    return f"Desde a sua última visita, em {desde:%d/%m/%Y} às {desde:%Hh%M}."


# --- ativos da pessoa -----------------------------------------------------------------------


@dataclass(frozen=True)
class AtivoDaPessoa:
    ticker: str
    origens: tuple[
        str, ...
    ]  # "favoritos", "Minha carteira", "lista X", "estratégias salvas"


def ativos_da_pessoa(
    favoritos: Iterable[str],
    carteira: Iterable[str],
    listas: Iterable[tuple[str, Iterable[str]]],
    estrategias: Iterable[object],
    maximo: int = MAXIMO_DE_ATIVOS,
) -> tuple[tuple[AtivoDaPessoa, ...], int]:
    """Os ativos guardados pela pessoa, sem repetir, e quantos ficaram além do `maximo`.

    A ordem é a de quem ela escolheu primeiro: favoritos, carteira, listas, estratégias.
    """
    fontes: list[tuple[str, Iterable[object]]] = [
        (NOME_DOS_FAVORITOS, favoritos),
        (NOME_DA_CARTEIRA, carteira),
        *((f"lista {nome}", tickers) for nome, tickers in listas),
        (NOME_DAS_ESTRATEGIAS, estrategias),
    ]
    origens: dict[str, list[str]] = {}
    for origem, tickers in fontes:
        for bruto in tickers:
            if (
                not isinstance(bruto, str)
                or len(bruto.strip()) > TAMANHO_MAXIMO_DO_TICKER
            ):
                continue  # o retrato de uma simulação salva vem do banco: não confiável
            ticker = normalizar_ticker(bruto)
            if ticker and origem not in origens.setdefault(ticker, []):
                origens[ticker].append(origem)
    todos = [AtivoDaPessoa(t, tuple(o)) for t, o in origens.items()]
    return tuple(todos[:maximo]), max(len(todos) - maximo, 0)


SEM_ATIVOS = (
    "Ainda não há nenhum ativo guardado. O Pulse acompanha os seus favoritos, as listas do "
    "Research, a carteira guardada (Pro) e os ativos das estratégias salvas."
)


def aviso_dos_ativos_de_fora(fora: int) -> str:
    return (
        f"O Pulse acompanha até {MAXIMO_DE_ATIVOS} ativos; {fora} ficaram de fora "
        "(valem os favoritos, depois a carteira, as listas e as estratégias)."
    )


# --- variação -------------------------------------------------------------------------------

NOTA_DA_VARIACAO = (
    "Do último fechamento que já existia na hora da sua visita até o último fechamento de "
    "hoje, na moeda do ativo e sem os proventos."
)


@dataclass(frozen=True)
class Variacao:
    ticker: str
    de: date
    preco_de: float
    ate: date
    preco_ate: float

    @property
    def retorno(self) -> float:
        return self.preco_ate / self.preco_de - 1


def _ultimo_dia_fechado(visita: datetime) -> date:
    """O último dia cujo fechamento já existia na hora da visita."""
    local = visita.astimezone(FUSO)
    if local.hour >= HORA_DO_FECHAMENTO:
        return local.date()
    return local.date() - timedelta(days=1)


def variacao(ticker: str, fechamentos: pd.Series, visita: datetime) -> Variacao | None:
    """Do último fechamento conhecido na hora da visita ao último fechamento da série.

    None quando não há preço antes da visita ou nenhum pregão novo depois dela.
    """
    serie = pd.Series(fechamentos, dtype=float).dropna().sort_index()
    serie = serie[serie > 0]
    dias = [pd.Timestamp(rotulo).date() for rotulo in serie.index]
    corte = _ultimo_dia_fechado(visita)
    fechados = [i for i, dia in enumerate(dias) if dia <= corte]
    if not fechados or dias[-1] <= dias[fechados[-1]]:
        return None
    base = fechados[-1]
    return Variacao(
        ticker, dias[base], float(serie.iloc[base]), dias[-1], float(serie.iloc[-1])
    )


# períodos aceitos pelo leitor de preços e quantos dias cada um cobre com folga (feriados)
PERIODOS_DE_PRECOS = (("6mo", 170), ("1y", 350), ("2y", 715))


def periodo_de_precos(j: Janela) -> str:
    """O menor histórico de preços que ainda tem o fechamento de antes da visita."""
    dias = (j.ate - j.desde).days
    return next((p for p, cobre in PERIODOS_DE_PRECOS if dias <= cobre), "5y")


def ordenar_variacoes(variacoes: Iterable[Variacao]) -> list[Variacao]:
    """A maior mudança (para cima ou para baixo) primeiro."""
    return sorted(variacoes, key=lambda v: abs(v.retorno), reverse=True)


def texto_da_variacao(v: Variacao) -> str:
    numero = f"{v.retorno * 100:+.1f}".replace(".", ",")
    return f"{_codigo(v.ticker)}: {numero}% (de {v.de:%d/%m} a {v.ate:%d/%m})"


# --- acontecimentos -------------------------------------------------------------------------


def acontecimentos(
    eventos: Iterable[Evento],
    ativos: Iterable[AtivoDaPessoa],
    j: Janela,
    pesos: Mapping[str, float],
    temas: Iterable[str],
) -> list[research.ItemDoResearch]:
    """Os eventos novos por relevância, todos (é o que mudou), com a origem de cada ativo."""
    hoje = j.ate.astimezone(FUSO).date()
    itens = research.ordenar(
        eventos,
        pesos,
        temas,
        hoje,
        max((hoje - j.publicados_desde).days, 1),
        "Pulse",
        maximo_por_ativo=None,
    )
    origens = {a.ticker: a.origens for a in ativos}
    return [_com_a_origem(item, origens.get(item.evento.ticker, ())) for item in itens]


def _com_a_origem(
    item: research.ItemDoResearch, origens: tuple[str, ...]
) -> research.ItemDoResearch:
    codigo = _codigo(item.evento.ticker)
    razao = (
        f"Você acompanha {codigo} em: {', '.join(origens)}."
        if origens
        else (f"Você acompanha {codigo}.")
    )
    return replace(item, razoes=[razao, *item.razoes[1:]])


# --- vereditos das estratégias salvas (PR E2) -----------------------------------------------

# cada ficha recalcula a validação inteira: a página não pode ficar lenta
MAXIMO_DE_FICHAS = 10
VEREDITOS = frozenset(r.value for r in Resultado)


@dataclass(frozen=True)
class EstrategiaSalva:
    id: str
    nome: str
    retrato: Mapping  # os campos da tela guardados (ticker, período, em reais...)
    pedido: object  # o pedido da ficha guardado: validado só na hora de usar
    veredito_ao_salvar: str | None


def _ficha_guardada(resultado: object) -> Mapping | None:
    if not isinstance(resultado, Mapping):
        return None
    guardada = resultado.get("ficha")
    if not isinstance(guardada, Mapping) or "pedido" not in guardada:
        return None
    return guardada


def _veredito(valor: object) -> str | None:
    return valor if isinstance(valor, str) and valor in VEREDITOS else None


def estrategias_salvas(
    simulacoes: Iterable, maximo: int = MAXIMO_DE_FICHAS
) -> tuple[tuple[EstrategiaSalva, ...], int, int]:
    """Os backtests salvos com a ficha (os mais novos primeiro, até `maximo`).

    Devolve também quantos foram salvos antes do Pulse guardar a ficha e quantos passaram do
    limite. As simulações vêm na ordem do banco (a mais nova primeiro).
    """
    salvas, sem_ficha = [], 0
    for simulacao in simulacoes:
        if simulacao.tipo != "backtest":
            continue
        guardada = _ficha_guardada(simulacao.resultado)
        if guardada is None:
            sem_ficha += 1
            continue
        retrato = simulacao.parametros
        salvas.append(
            EstrategiaSalva(
                str(simulacao.id),
                simulacao.nome,
                retrato if isinstance(retrato, Mapping) else {},
                guardada["pedido"],
                _veredito(guardada.get("veredito")),
            )
        )
    return tuple(salvas[:maximo]), sem_ficha, max(len(salvas) - maximo, 0)


def precisa_do_cdi(pedido: object) -> bool:
    return isinstance(pedido, Mapping) and pedido.get("usa_cdi") is True


@dataclass(frozen=True)
class VereditoDaEstrategia:
    estrategia: EstrategiaSalva
    antes: str | None  # o visto no último Pulse (ou o da hora de salvar)
    agora: str | None  # None: não deu para conferir agora

    @property
    def mudou(self) -> bool:
        return None not in (self.antes, self.agora) and self.antes != self.agora


def comparar(
    estrategia: EstrategiaSalva, vistos: Mapping[str, str], agora: str | None
) -> VereditoDaEstrategia:
    antes = _veredito(vistos.get(estrategia.id)) or estrategia.veredito_ao_salvar
    return VereditoDaEstrategia(estrategia, antes, _veredito(agora))


def vereditos_para_guardar(
    vistos: Mapping[str, str],
    conferidos: Iterable[VereditoDaEstrategia],
    ids_salvos: set[str],
) -> dict[str, str]:
    """Os vistos de agora; o que não deu para conferir fica com o visto antes (se ainda existe)."""
    novos = {i: v for i, v in vistos.items() if i in ids_salvos and _veredito(v)}
    for conferido in conferidos:
        if conferido.agora is not None:
            novos[conferido.estrategia.id] = conferido.agora
    return novos


def veredito_de_hoje(
    estrategia: EstrategiaSalva,
    carregar: Callable[[str, str, bool], pd.DataFrame],
    cdi: Callable[[pd.Timestamp, pd.Timestamp], pd.Series],
    montar: Callable[[ficha.PedidoDaFicha], ficha.Ficha] = ficha.montar_ficha,
) -> str | None:
    """O veredito da ficha "Foi sorte?" com os preços de hoje; None se não deu para conferir.

    Quem chama passa o seu jeito de baixar preços e CDI (o Streamlit usa os caches dele, a API
    os dela): o cálculo é um só, e os números são os mesmos nas duas telas.
    """
    campos = restaurar_estado(estrategia.retrato, "backtest")
    if "ticker" not in campos or "periodo" not in campos:
        return None
    try:
        dados = carregar(
            campos["ticker"], campos["periodo"], campos.get("em_reais", False)
        )
        if dados.attrs.get("cambio_falhou"):
            return None  # em dólar, o veredito mudaria pelo câmbio que faltou
        cdi_diario = None
        if precisa_do_cdi(estrategia.pedido):
            cdi_diario = cdi(dados.index[0], dados.index[-1])
        pedido = ficha.pedido_guardado(estrategia.pedido, dados, cdi_diario)
        return montar(pedido).veredito.resultado.value
    except (DadosIndisponiveisError, CDIIndisponivelError, ValueError, KeyError):
        return None
    except Exception:
        log.exception("Falha ao conferir a ficha de uma estratégia salva no Pulse")
        return None


# --- o selo da mudança no app novo (Workspace) ----------------------------------------------
# A visita marcada já guarda o veredito novo como "visto": no F5 da aba, "antes" e "agora" seriam
# iguais e o selo sumiria. A mudança vista (de, para e quando) fica guardada junto dos vistos até
# sair de qualquer janela possível (30 dias) e aparece enquanto estiver dentro da janela da aba.
TAMANHO_MAXIMO_DO_ID = 64  # o mesmo limite dos vistos em src/banco/pulse.py


@dataclass(frozen=True)
class Mudanca:
    antes: str
    agora: str
    em: datetime  # a visita em que a mudança foi vista


@dataclass(frozen=True)
class EstrategiaAcompanhada:
    estrategia: EstrategiaSalva
    antes: str | None
    agora: str | None  # None: não deu para conferir agora
    mudou: bool
    conferido_em: datetime | None  # a visita em que o veredito de agora foi visto


def acompanhar(
    conferidos: Iterable[VereditoDaEstrategia],
    mudancas: Mapping[str, Mudanca],
    j: Janela,
) -> tuple[list[EstrategiaAcompanhada], dict[str, Mudanca]]:
    """As estratégias na ordem do cartão (as que mudaram, as iguais, as não conferidas) e as
    mudanças que continuam guardadas."""
    mudaram, iguais, sem_conferir = [], [], []
    guardar: dict[str, Mudanca] = {}
    for v in conferidos:
        sid = v.estrategia.id
        anterior = mudancas.get(sid)
        if anterior is not None and anterior.em < j.ate - JANELA_MAXIMA_DA_ABA:
            anterior = None  # velha: fora de qualquer janela
        if v.agora is None:
            if anterior is not None:
                guardar[sid] = anterior  # fica para quando der para conferir
            sem_conferir.append(
                EstrategiaAcompanhada(v.estrategia, v.antes, None, False, None)
            )
        elif v.mudou and v.antes is not None:
            guardar[sid] = Mudanca(v.antes, v.agora, j.ate)
            mudaram.append(
                EstrategiaAcompanhada(v.estrategia, v.antes, v.agora, True, j.ate)
            )
        elif anterior is not None and anterior.agora == v.agora:
            guardar[sid] = anterior
            if (
                anterior.em > j.desde
            ):  # vista depois da visita que abre a janela: o selo fica
                mudaram.append(
                    EstrategiaAcompanhada(
                        v.estrategia, anterior.antes, v.agora, True, anterior.em
                    )
                )
            else:
                iguais.append(
                    EstrategiaAcompanhada(v.estrategia, v.antes, v.agora, False, j.ate)
                )
        else:  # sem mudança guardada, ou a guardada se desfez
            iguais.append(
                EstrategiaAcompanhada(v.estrategia, v.antes, v.agora, False, j.ate)
            )
    return [*mudaram, *iguais, *sem_conferir], guardar


def mudancas_para_guardar(mudancas: Mapping[str, Mudanca]) -> dict[str, dict[str, str]]:
    return {
        sid: {"antes": m.antes, "agora": m.agora, "em": m.em.isoformat()}
        for sid, m in mudancas.items()
    }


def _mudanca(guardada: object) -> Mudanca | None:
    if not isinstance(guardada, Mapping):
        return None
    antes, depois = _veredito(guardada.get("antes")), _veredito(guardada.get("agora"))
    em = guardada.get("em")
    if antes is None or depois is None or antes == depois or not isinstance(em, str):
        return None
    try:
        quando = datetime.fromisoformat(em)
    except ValueError:
        return None
    return None if quando.tzinfo is None else Mudanca(antes, depois, quando)


def ler_mudancas(guardadas: object) -> dict[str, Mudanca]:
    """As mudanças guardadas. Vêm do banco (não confiável): o estranho fica de fora."""
    if not isinstance(guardadas, Mapping):
        return {}
    lidas = {}
    for sid, guardada in guardadas.items():
        mudanca = _mudanca(guardada)
        if isinstance(sid, str) and len(sid) <= TAMANHO_MAXIMO_DO_ID and mudanca:
            lidas[sid] = mudanca
    return lidas


def texto_do_veredito(v: VereditoDaEstrategia) -> str:
    return (
        f'**{v.estrategia.nome}**: o veredito da ficha "Foi sorte?" mudou de **{v.antes}** para '
        f"**{v.agora}** com os dados de hoje."
    )


def teses_por_estrategia(
    anotacoes: Iterable[diario_de_teses.Anotacao],
) -> dict[str, diario_de_teses.Anotacao]:
    """Para cada backtest salvo (id em texto), a anotação mais nova do Diário ligada a ele."""
    ligadas: dict[str, diario_de_teses.Anotacao] = {}
    for anotacao in sorted(anotacoes, key=lambda a: a.criada_em):
        for simulacao_id in anotacao.estrategias:
            ligadas[str(simulacao_id)] = anotacao  # a mais nova sobrescreve
    return ligadas


def texto_da_tese_ligada(anotacao: diario_de_teses.Anotacao) -> str:
    """Uma linha com a data e o começo da tese (texto da pessoa: mostrar como texto puro)."""
    return (
        f"Sua tese sobre {_codigo(anotacao.ticker)} em "
        f"{diario_de_teses.texto_da_data(anotacao.criada_em)}: "
        f"“{diario_de_teses.trecho(anotacao.texto)}”"
    )


def agora() -> datetime:
    return datetime.now(UTC)
