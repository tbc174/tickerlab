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

from src.banco.modelo import (
    TIPOS_DE_RELATORIO,
    favoritos,
    preferencias,
    presets,
    relatorios,
    simulacoes,
)
from src.planos import (
    conferir_favoritos,
    conferir_parametros_por_ativo,
    conferir_relatorio,
    conferir_simulacoes,
)

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
    """Tira o relatório da biblioteca: apaga o título e os parâmetros. A linha (tipo e hora)
    fica, para o limite do plano continuar valendo. Só mexe nos relatórios do próprio usuário."""
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
