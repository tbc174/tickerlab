"""Dados que pertencem a cada usuário: preferências, favoritos e simulações salvas.

Regra de ouro: **toda função recebe o `usuario_id` e filtra por ele**. Quem chama passa o id da
sessão (nunca um id vindo de um campo da tela), e há testes que provam que um usuário não vê,
não reabre nem apaga o que é de outro.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa

from src.banco.modelo import favoritos, preferencias, simulacoes

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
    conexao: sa.Connection, usuario_id: uuid.UUID, tickers: list[str]
) -> None:
    """Substitui a lista de favoritos do usuário, mantendo a ordem."""
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
) -> Simulacao:
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
