"""Dados que pertencem a cada usuário: preferências, favoritos e simulações salvas.

Regra de ouro: **toda função recebe o `usuario_id` e filtra por ele**. Quem chama passa o id da
sessão (nunca um id vindo de um campo da tela), e há testes que provam que um usuário não vê,
não reabre nem apaga o que é de outro.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from src import auditoria
from src.alertas import Regra, RegraInvalidaError, validar
from src.banco.modelo import (
    TIPOS_DE_RELATORIO,
    alertas,
    carteiras_do_research,
    favoritos,
    pdfs_originais,
    preferencias,
    presets,
    relatorios,
    simulacoes,
    watchlists,
)
from src.carteira_research import VERSAO_DO_CONSENTIMENTO, Fotografia
from src.planos import (
    conferir_alerta,
    conferir_carteira,
    conferir_favoritos,
    conferir_parametros_por_ativo,
    conferir_relatorio,
    conferir_simulacoes,
    conferir_watchlist,
)
from src.research import NOMES_RESERVADOS

TIPOS_DE_SIMULACAO = ("backtest", "carteira", "pares")
TAMANHO_MAXIMO_DO_NOME = 120
TAMANHO_MAXIMO_DOS_DADOS = 20_000  # bytes de JSON por campo (parâmetros ou resultado)
MAX_SIMULACOES_POR_USUARIO = 500  # trava de segurança; os limites dos planos vêm na S4
MAX_FAVORITOS_NO_BANCO = 50


class DadosInvalidosError(ValueError):
    """Algo que o usuário (ou a tela) mandou não pode ser guardado."""


@dataclass(frozen=True)
class Simulacao:
    id: uuid.UUID
    tipo: str
    nome: str
    parametros: dict
    resultado: dict
    criada_em: datetime


def _agora() -> datetime:
    return datetime.now(UTC)


# --- preferências -------------------------------------------------------------------------
def carregar_preferencias(conexao: sa.Connection, usuario_id: uuid.UUID) -> dict:
    linha = conexao.execute(
        sa.select(preferencias.c.dados).where(preferencias.c.usuario_id == usuario_id)
    ).first()
    return dict(linha.dados) if linha else {}


def salvar_preferencias(
    conexao: sa.Connection, usuario_id: uuid.UUID, dados: dict
) -> None:
    """Grava (substituindo) as preferências do usuário."""
    _conferir_tamanho(dados, "As preferências")
    existe = conexao.execute(
        sa.select(preferencias.c.usuario_id).where(
            preferencias.c.usuario_id == usuario_id
        )
    ).first()
    if existe:
        conexao.execute(
            sa.update(preferencias)
            .where(preferencias.c.usuario_id == usuario_id)
            .values(dados=dados, atualizado_em=_agora())
        )
    else:
        conexao.execute(
            sa.insert(preferencias).values(
                usuario_id=usuario_id, dados=dados, atualizado_em=_agora()
            )
        )


# --- favoritos ----------------------------------------------------------------------------
def listar_favoritos(conexao: sa.Connection, usuario_id: uuid.UUID) -> list[str]:
    linhas = conexao.execute(
        sa.select(favoritos.c.ticker)
        .where(favoritos.c.usuario_id == usuario_id)
        .order_by(favoritos.c.ordem, favoritos.c.ticker)
    )
    return [linha.ticker for linha in linhas]


def salvar_favoritos(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    tickers: list[str],
    plano: str | None = None,
) -> None:
    """Substitui a lista de favoritos do usuário, mantendo a ordem.

    Com `plano`, recusa uma lista que cresça além do limite dele (`LimiteDoPlanoError`).
    """
    limpos: list[str] = []
    for ticker in tickers:
        ticker = (ticker or "").strip().upper()
        if not ticker or len(ticker) > 20:
            raise DadosInvalidosError(f"Ticker inválido: {ticker!r}.")
        if ticker not in limpos:
            limpos.append(ticker)
    if len(limpos) > MAX_FAVORITOS_NO_BANCO:
        raise DadosInvalidosError(
            f"No máximo {MAX_FAVORITOS_NO_BANCO} favoritos por conta."
        )
    if plano is not None:
        conferir_favoritos(
            plano, len(listar_favoritos(conexao, usuario_id)), len(limpos)
        )
    conexao.execute(sa.delete(favoritos).where(favoritos.c.usuario_id == usuario_id))
    if limpos:
        conexao.execute(
            sa.insert(favoritos),
            [
                {
                    "usuario_id": usuario_id,
                    "ticker": ticker,
                    "ordem": posicao,
                    "criado_em": _agora(),
                }
                for posicao, ticker in enumerate(limpos)
            ],
        )


# --- simulações ---------------------------------------------------------------------------
def _conferir_tamanho(valor: dict, o_que: str) -> None:
    if not isinstance(valor, dict):
        raise DadosInvalidosError(f"{o_que} precisam ser um dicionário.")
    try:
        texto = json.dumps(valor)
    except (TypeError, ValueError) as erro:
        raise DadosInvalidosError(f"{o_que} não são JSON válido.") from erro
    if len(texto.encode("utf-8")) > TAMANHO_MAXIMO_DOS_DADOS:
        raise DadosInvalidosError(f"{o_que} são grandes demais para guardar.")


def _de_linha(linha: sa.Row) -> Simulacao:
    return Simulacao(
        id=linha.id,
        tipo=linha.tipo,
        nome=linha.nome,
        parametros=dict(linha.parametros),
        resultado=dict(linha.resultado),
        criada_em=linha.criada_em,
    )


def contar_simulacoes(conexao: sa.Connection, usuario_id: uuid.UUID) -> int:
    return conexao.execute(
        sa.select(sa.func.count())
        .select_from(simulacoes)
        .where(simulacoes.c.usuario_id == usuario_id)
    ).scalar_one()


def salvar_simulacao(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    tipo: str,
    nome: str,
    parametros: dict,
    resultado: dict,
    plano: str | None = None,
) -> Simulacao:
    """Guarda a simulação. Com `plano`, recusa se o usuário já está no limite dele."""
    if tipo not in TIPOS_DE_SIMULACAO:
        raise DadosInvalidosError(
            f"Tipo de simulação desconhecido: {tipo}. Use um destes: {TIPOS_DE_SIMULACAO}."
        )
    nome = " ".join((nome or "").split())
    if not nome:
        raise DadosInvalidosError("Dê um nome para a simulação.")
    if len(nome) > TAMANHO_MAXIMO_DO_NOME:
        raise DadosInvalidosError(
            f"O nome pode ter até {TAMANHO_MAXIMO_DO_NOME} caracteres."
        )
    _conferir_tamanho(parametros, "Os parâmetros")
    _conferir_tamanho(resultado, "O resultado")
    if plano is not None:
        conferir_simulacoes(plano, contar_simulacoes(conexao, usuario_id))
    if contar_simulacoes(conexao, usuario_id) >= MAX_SIMULACOES_POR_USUARIO:
        raise DadosInvalidosError(
            f"Você chegou ao máximo de {MAX_SIMULACOES_POR_USUARIO} simulações salvas."
        )
    nova = uuid.uuid4()
    conexao.execute(
        sa.insert(simulacoes).values(
            id=nova,
            usuario_id=usuario_id,
            tipo=tipo,
            nome=nome,
            parametros=parametros,
            resultado=resultado,
            criada_em=_agora(),
        )
    )
    return buscar_simulacao(conexao, usuario_id, nova)


def listar_simulacoes(
    conexao: sa.Connection, usuario_id: uuid.UUID, tipo: str | None = None
) -> list[Simulacao]:
    """As simulações do usuário, da mais nova para a mais antiga."""
    consulta = sa.select(simulacoes).where(simulacoes.c.usuario_id == usuario_id)
    if tipo is not None:
        consulta = consulta.where(simulacoes.c.tipo == tipo)
    consulta = consulta.order_by(simulacoes.c.criada_em.desc(), simulacoes.c.nome)
    return [_de_linha(linha) for linha in conexao.execute(consulta)]


def buscar_simulacao(
    conexao: sa.Connection, usuario_id: uuid.UUID, simulacao_id: uuid.UUID
) -> Simulacao | None:
    """A simulação, se for deste usuário (a de outro usuário não existe para ele)."""
    linha = conexao.execute(
        sa.select(simulacoes).where(
            simulacoes.c.id == simulacao_id, simulacoes.c.usuario_id == usuario_id
        )
    ).first()
    return _de_linha(linha) if linha else None


def apagar_simulacao(
    conexao: sa.Connection, usuario_id: uuid.UUID, simulacao_id: uuid.UUID
) -> bool:
    """Apaga a simulação se for deste usuário. Devolve se havia o que apagar."""
    resultado = conexao.execute(
        sa.delete(simulacoes).where(
            simulacoes.c.id == simulacao_id, simulacoes.c.usuario_id == usuario_id
        )
    )
    return resultado.rowcount > 0


# --- relatórios em PDF (só o tipo e a hora, para o limite do plano) --------------------------
JANELA_DO_LIMITE_DE_RELATORIOS = timedelta(hours=24)


def contar_relatorios_recentes(
    conexao: sa.Connection, usuario_id: uuid.UUID, agora: datetime | None = None
) -> int:
    """Quantos relatórios o usuário gerou nas últimas 24 horas."""
    desde = (agora or _agora()) - JANELA_DO_LIMITE_DE_RELATORIOS
    return conexao.execute(
        sa.select(sa.func.count())
        .select_from(relatorios)
        .where(relatorios.c.usuario_id == usuario_id, relatorios.c.criado_em > desde)
    ).scalar_one()


@dataclass(frozen=True)
class RelatorioGerado:
    id: uuid.UUID
    tipo: str
    titulo: str
    parametros: dict
    criado_em: datetime


TAMANHO_MAXIMO_DO_TITULO = 200


def registrar_relatorio(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    tipo: str,
    plano: str | None = None,
    agora: datetime | None = None,
    titulo: str | None = None,
    parametros: dict | None = None,
) -> uuid.UUID:
    """Anota um relatório gerado e devolve o id. Com `plano`, recusa (antes de anotar) o que
    passa do limite. `titulo` e `parametros` alimentam a biblioteca (reabrir e gerar de novo)."""
    if tipo not in TIPOS_DE_RELATORIO:
        raise DadosInvalidosError(
            f"Tipo de relatório desconhecido: {tipo}. Use um destes: {TIPOS_DE_RELATORIO}."
        )
    if parametros is not None:
        _conferir_tamanho(parametros, "parâmetros do relatório")
    agora = agora or _agora()
    if plano is not None:
        conferir_relatorio(
            plano, tipo, contar_relatorios_recentes(conexao, usuario_id, agora)
        )
    novo = uuid.uuid4()
    conexao.execute(
        sa.insert(relatorios).values(
            id=novo,
            usuario_id=usuario_id,
            tipo=tipo,
            criado_em=agora,
            titulo=(titulo or "")[:TAMANHO_MAXIMO_DO_TITULO] or None,
            parametros=parametros,
        )
    )
    return novo


def listar_relatorios(conexao: sa.Connection, usuario_id: uuid.UUID) -> list[dict]:
    """Os relatórios que o usuário gerou (tipo e hora), do mais novo para o mais antigo.

    Inclui os excluídos da biblioteca: é o registro usado pelo limite do plano e pela exportação.
    """
    return [
        {"tipo": l.tipo, "criado_em": l.criado_em.isoformat()}
        for l in conexao.execute(
            sa.select(relatorios.c.tipo, relatorios.c.criado_em)
            .where(relatorios.c.usuario_id == usuario_id)
            .order_by(relatorios.c.criado_em.desc())
        )
    ]


def biblioteca_de_relatorios(
    conexao: sa.Connection, usuario_id: uuid.UUID, limite: int = 200
) -> list[RelatorioGerado]:
    """A biblioteca: os relatórios não excluídos, do mais novo para o mais antigo."""
    return [
        RelatorioGerado(
            id=l.id,
            tipo=l.tipo,
            titulo=l.titulo or "",
            parametros=dict(l.parametros or {}),
            criado_em=l.criado_em,
        )
        for l in conexao.execute(
            sa.select(relatorios)
            .where(
                relatorios.c.usuario_id == usuario_id,
                relatorios.c.apagado_em.is_(None),
            )
            .order_by(relatorios.c.criado_em.desc())
            .limit(limite)
        )
    ]


def excluir_relatorio(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    relatorio_id: uuid.UUID,
    agora: datetime | None = None,
) -> bool:
    """Tira o relatório da biblioteca: apaga o título, os parâmetros e o PDF original guardado. A
    linha (tipo e hora) fica, para o limite do plano continuar valendo. Só mexe nos relatórios
    do próprio usuário."""
    conexao.execute(
        sa.delete(pdfs_originais).where(
            pdfs_originais.c.relatorio_id == relatorio_id,
            pdfs_originais.c.usuario_id == usuario_id,
        )
    )
    resultado = conexao.execute(
        sa.update(relatorios)
        .where(
            relatorios.c.id == relatorio_id,
            relatorios.c.usuario_id == usuario_id,
            relatorios.c.apagado_em.is_(None),
        )
        .values(titulo=None, parametros=None, apagado_em=agora or _agora())
    )
    return resultado.rowcount == 1


# --- presets do Research (versões; nada é sobrescrito) -----------------------------------------
MAX_VERSOES_POR_PRESET = 500  # trava de segurança contra cliques sem fim


@dataclass(frozen=True)
class VersaoDePreset:
    versao: int
    parametros: dict
    motivo: str
    criado_em: datetime


def _ultima_versao(conexao, usuario_id, escopo, alvo):  # noqa: ANN001, ANN202
    return conexao.execute(
        sa.select(presets)
        .where(
            presets.c.usuario_id == usuario_id,
            presets.c.escopo == escopo,
            presets.c.alvo == alvo,
        )
        .order_by(presets.c.versao.desc())
        .limit(1)
    ).first()


def presets_atuais(conexao: sa.Connection, usuario_id: uuid.UUID) -> list:
    """A versão mais nova de cada preset do usuário, pronta para `src.presets.resolver`.

    Um preset cuja versão mais nova está vazia (tudo restaurado) não entra.
    """
    from src.presets import Preset  # evita importar o Pydantic só para abrir o banco

    ultimas = (
        sa.select(
            presets.c.escopo,
            presets.c.alvo,
            sa.func.max(presets.c.versao).label("versao"),
        )
        .where(presets.c.usuario_id == usuario_id)
        .group_by(presets.c.escopo, presets.c.alvo)
        .subquery()
    )
    linhas = conexao.execute(
        sa.select(presets)
        .join(
            ultimas,
            (presets.c.escopo == ultimas.c.escopo)
            & (presets.c.alvo == ultimas.c.alvo)
            & (presets.c.versao == ultimas.c.versao),
        )
        .where(presets.c.usuario_id == usuario_id)
    ).all()
    return [
        Preset(
            escopo=l.escopo,
            alvo=l.alvo or None,
            nome=l.nome,
            versao=l.versao,
            parametros=dict(l.parametros),
        )
        for l in linhas
        if l.parametros
    ]


def salvar_preset(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    escopo: str,
    alvo: str | None,
    parametros: dict,
    plano: str | None = None,
    nome: str = "",
    motivo: str = "",
    agora: datetime | None = None,
) -> int | None:
    """Grava os parâmetros como a versão seguinte e devolve o número dela.

    Valida tudo de novo aqui (não confia na tela). Se nada mudou, não cria versão (devolve None).
    Com `plano`, aplica o limite de ativos com parâmetros próprios. `parametros` vazio = restaurar
    tudo neste escopo (também vira uma versão, para o histórico).
    """
    import pydantic

    from src.presets import Preset, conferir_ao_salvar

    try:
        preset = Preset(
            escopo=escopo, alvo=alvo or None, nome=nome, parametros=parametros
        )
    except pydantic.ValidationError as erro:
        mensagens = "; ".join(
            e["msg"].removeprefix("Value error, ") for e in erro.errors()
        )
        raise DadosInvalidosError(mensagens) from erro
    alvo_salvo = preset.alvo or ""
    # as regras entre parâmetros valem no conjunto final (este escopo e os que herdam dele)
    try:
        conferir_ao_salvar(presets_atuais(conexao, usuario_id), preset)
    except ValueError as erro:
        raise DadosInvalidosError(str(erro)) from erro
    valores = {
        k: list(v) if isinstance(v, tuple) else v for k, v in preset.parametros.items()
    }
    anterior = _ultima_versao(conexao, usuario_id, escopo, alvo_salvo)
    if anterior is not None and dict(anterior.parametros) == valores:
        return None
    if anterior is None and not valores:
        return None  # restaurar o que nunca foi mudado
    if plano is not None and escopo == "ativo" and valores:
        conferir_parametros_por_ativo(
            plano,
            len(
                [p for p in presets_atuais(conexao, usuario_id) if p.escopo == "ativo"]
            ),
            ja_tem_este=anterior is not None and bool(anterior.parametros),
        )
    versao = (anterior.versao + 1) if anterior is not None else 1
    if versao > MAX_VERSOES_POR_PRESET:
        raise DadosInvalidosError("Este preset já tem versões demais.")
    conexao.execute(
        sa.insert(presets).values(
            id=uuid.uuid4(),
            usuario_id=usuario_id,
            escopo=escopo,
            alvo=alvo_salvo,
            versao=versao,
            nome=(nome or "")[:80],
            parametros=valores,
            motivo=(motivo or "")[:200],
            criado_em=agora or _agora(),
        )
    )
    return versao


def historico_do_preset(
    conexao: sa.Connection, usuario_id: uuid.UUID, escopo: str, alvo: str | None
) -> list[VersaoDePreset]:
    """Todas as versões de um preset, da mais nova para a mais antiga."""
    alvo_salvo = alvo or ""
    if escopo == "ativo" and alvo:
        from src.dados import normalizar_ticker

        alvo_salvo = normalizar_ticker(alvo)
    return [
        VersaoDePreset(l.versao, dict(l.parametros), l.motivo, l.criado_em)
        for l in conexao.execute(
            sa.select(presets)
            .where(
                presets.c.usuario_id == usuario_id,
                presets.c.escopo == escopo,
                presets.c.alvo == alvo_salvo,
            )
            .order_by(presets.c.versao.desc())
        )
    ]


# --- watchlists do Research ----------------------------------------------------------------------
TAMANHO_MAXIMO_DO_NOME_DA_LISTA = 60


@dataclass(frozen=True)
class Watchlist:
    id: uuid.UUID
    nome: str
    tickers: list[str]


def _limpar_tickers(tickers: list[str]) -> list[str]:
    from src.dados import normalizar_ticker
    from src.link import ticker_valido

    limpos = []
    for ticker in tickers:
        simbolo = normalizar_ticker(ticker)
        if not ticker_valido(simbolo):
            raise DadosInvalidosError(f"Código de ativo inválido: {ticker}.")
        if simbolo not in limpos:
            limpos.append(simbolo)
    return limpos


def _limpar_nome(nome: str) -> str:
    nome = " ".join((nome or "").split())
    if not nome:
        raise DadosInvalidosError("Dê um nome à lista.")
    if len(nome) > TAMANHO_MAXIMO_DO_NOME_DA_LISTA:
        raise DadosInvalidosError(
            f"O nome da lista tem até {TAMANHO_MAXIMO_DO_NOME_DA_LISTA} letras."
        )
    if nome.casefold() in {n.casefold() for n in NOMES_RESERVADOS}:
        raise DadosInvalidosError(
            f'"{nome}" é o nome de uma lista do app; escolha outro.'
        )
    return nome


def listar_watchlists(conexao: sa.Connection, usuario_id: uuid.UUID) -> list[Watchlist]:
    return [
        Watchlist(l.id, l.nome, list(l.tickers))
        for l in conexao.execute(
            sa.select(watchlists)
            .where(watchlists.c.usuario_id == usuario_id)
            .order_by(watchlists.c.criado_em, watchlists.c.nome)
        )
    ]


def salvar_watchlist(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    nome: str,
    tickers: list[str],
    plano: str | None = None,
    watchlist_id: uuid.UUID | None = None,
    agora: datetime | None = None,
) -> uuid.UUID:
    """Cria a lista (sem `watchlist_id`) ou troca o nome e os ativos de uma lista sua."""
    nome, tickers = _limpar_nome(nome), _limpar_tickers(tickers)
    agora = agora or _agora()
    existentes = listar_watchlists(conexao, usuario_id)
    if plano is not None:
        conferir_watchlist(
            plano, len(existentes), len(tickers), e_nova=watchlist_id is None
        )
    repetido = [
        w for w in existentes if w.nome.lower() == nome.lower() and w.id != watchlist_id
    ]
    if repetido:
        raise DadosInvalidosError(f'Você já tem uma lista chamada "{nome}".')
    if watchlist_id is None:
        novo = uuid.uuid4()
        conexao.execute(
            sa.insert(watchlists).values(
                id=novo,
                usuario_id=usuario_id,
                nome=nome,
                tickers=tickers,
                criado_em=agora,
                atualizado_em=agora,
            )
        )
        return novo
    alterou = conexao.execute(
        sa.update(watchlists)
        .where(watchlists.c.id == watchlist_id, watchlists.c.usuario_id == usuario_id)
        .values(nome=nome, tickers=tickers, atualizado_em=agora)
    ).rowcount
    if alterou != 1:
        raise DadosInvalidosError("Lista não encontrada.")
    return watchlist_id


def apagar_watchlist(
    conexao: sa.Connection, usuario_id: uuid.UUID, watchlist_id: uuid.UUID
) -> bool:
    return (
        conexao.execute(
            sa.delete(watchlists).where(
                watchlists.c.id == watchlist_id, watchlists.c.usuario_id == usuario_id
            )
        ).rowcount
        == 1
    )


# --- alertas compostos do Research (etapa 6) -----------------------------------------------------
@dataclass(frozen=True)
class AlertaSalvo:
    id: uuid.UUID
    regra: Regra


def listar_alertas(conexao: sa.Connection, usuario_id: uuid.UUID) -> list[AlertaSalvo]:
    return [
        AlertaSalvo(l.id, Regra.de_guardada(l.nome, dict(l.regra)))
        for l in conexao.execute(
            sa.select(alertas)
            .where(alertas.c.usuario_id == usuario_id)
            .order_by(alertas.c.criado_em, alertas.c.nome)
        )
    ]


def salvar_alerta(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    regra: Regra,
    plano: str | None = None,
    alerta_id: uuid.UUID | None = None,
    agora: datetime | None = None,
) -> uuid.UUID:
    """Cria o alerta (sem `alerta_id`) ou troca um alerta seu. Confere a regra e o plano."""
    try:
        regra = validar(regra)
    except RegraInvalidaError as erro:
        raise DadosInvalidosError(str(erro)) from erro
    agora = agora or _agora()
    existentes = listar_alertas(conexao, usuario_id)
    if plano is not None and alerta_id is None:
        conferir_alerta(plano, len(existentes))
    if any(
        a.regra.nome.lower() == regra.nome.lower() and a.id != alerta_id
        for a in existentes
    ):
        raise DadosInvalidosError(f'Você já tem um alerta chamado "{regra.nome}".')
    valores = {
        "nome": regra.nome,
        "regra": regra.para_guardar(),
        "atualizado_em": agora,
    }
    if alerta_id is None:
        novo = uuid.uuid4()
        conexao.execute(
            sa.insert(alertas).values(
                id=novo, usuario_id=usuario_id, criado_em=agora, **valores
            )
        )
        return novo
    alterou = conexao.execute(
        sa.update(alertas)
        .where(alertas.c.id == alerta_id, alertas.c.usuario_id == usuario_id)
        .values(**valores)
    ).rowcount
    if alterou != 1:
        raise DadosInvalidosError("Alerta não encontrado.")
    return alerta_id


def apagar_alerta(
    conexao: sa.Connection, usuario_id: uuid.UUID, alerta_id: uuid.UUID
) -> bool:
    return (
        conexao.execute(
            sa.delete(alertas).where(
                alertas.c.id == alerta_id, alertas.c.usuario_id == usuario_id
            )
        ).rowcount
        == 1
    )


# --- carteira do Research (etapa 5, decisão 0020) ----------------------------------------------
def carregar_carteira(
    conexao: sa.Connection, usuario_id: uuid.UUID
) -> Fotografia | None:
    """A fotografia guardada (só pesos), ou None se não há carteira ou o consentimento foi revogado."""
    linha = conexao.execute(
        sa.select(carteiras_do_research).where(
            carteiras_do_research.c.usuario_id == usuario_id
        )
    ).first()
    if linha is None:
        return None
    return Fotografia(
        {str(t): float(p) for t, p in dict(linha.pesos).items()}, linha.enviada_em
    )


def salvar_carteira(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    foto: Fotografia,
    plano: str | None = None,
    agora: datetime | None = None,
) -> None:
    """Guarda (ou troca) a fotografia, com o consentimento da versão atual.

    Só chame depois de a pessoa marcar o consentimento na tela: a versão e a hora ficam na linha
    e na auditoria (só ids, para provar o consentimento mesmo depois de revogado).
    """
    if plano is not None:
        conferir_carteira(plano)
    if not foto.pesos:
        raise DadosInvalidosError("A carteira não tem ativos com peso.")
    _conferir_tamanho(foto.pesos, "A carteira")
    agora = agora or _agora()
    conexao.execute(
        sa.delete(carteiras_do_research).where(
            carteiras_do_research.c.usuario_id == usuario_id
        )
    )
    conexao.execute(
        sa.insert(carteiras_do_research).values(
            usuario_id=usuario_id,
            pesos=foto.pesos,
            enviada_em=foto.enviada_em,
            versao_do_consentimento=VERSAO_DO_CONSENTIMENTO,
            consentido_em=agora,
        )
    )
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_CARTEIRA_CONSENTIDA,
        usuario_id,
        {"versao": VERSAO_DO_CONSENTIMENTO},
    )


def revogar_carteira(conexao: sa.Connection, usuario_id: uuid.UUID) -> bool:
    """Revoga o consentimento: apaga a fotografia na hora. Devolve False se não havia carteira."""
    apagou = (
        conexao.execute(
            sa.delete(carteiras_do_research).where(
                carteiras_do_research.c.usuario_id == usuario_id
            )
        ).rowcount
        == 1
    )
    if apagou:
        auditoria.registrar(
            conexao, usuario_id, auditoria.ACAO_CARTEIRA_REVOGADA, usuario_id
        )
    return apagou
