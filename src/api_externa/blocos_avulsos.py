"""Alguns blocos da análise completa, sem abrir o resto (linha 980, onda 2): a mecânica das rotas que servem só uma
parte da análise (`registros.py`, `compras.py`).

Cada bloco é o mesmo da análise completa (`conjuntos/analise.py`): o mesmo leitor, o mesmo portão do conjunto dele e
a mesma varredura de pessoa. A diferença é não abrir o resto da análise e, por isso, gastar um pedido por conjunto
aberto, não um por bloco da análise. Bloco que a chave não vê não aparece, nem pelo nome (a resposta de quem não o
vê é a mesma com ou sem o dado na base). Sem nenhum dos blocos, ou para CNPJ que não é de empresa (MEI, empresário
individual), `not_available`.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

import sqlalchemy as sa
from fastapi import HTTPException

from base.porta import Porta
from src.api_externa import acesso, pessoas, piloto, rotas
from src.api_externa.catalogo import linhas_liberadas
from src.api_externa.conjuntos import Servido, analise, empresas, por_tabela
from src.api_externa.envelope import fontes_da_resposta
from src.api_externa.nomes import para_fora, traduzir_chaves
from src.api_externa.rotas import (
    FINALIDADE,
    NAO_DISPONIVEL,
    _fora_do_ar,
    _porta,
    _portao,
)
from src.api_externa.tabelas_por_cnpj import do_bloco
from src.banco.chaves_da_api import registrar_consumo
from src.banco.conexao import obter_engine
from src.chaves_da_api import ContextoDaChave

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Avulsos:
    """Os blocos de uma rota, na ordem da resposta, e as frases de `limits` dela; `rotulo` só vai ao log."""

    blocos: tuple[str, ...]
    limites: tuple[str, ...]
    rotulo: str

    @property
    def conjunto_do_negado(self) -> str:
        """Sem nenhum bloco aberto, o pedido conta como negado no conjunto do primeiro bloco da rota."""
        return do_bloco(self.blocos[0])[0].conjunto


def _abertos(
    avulsos: Avulsos, liberadas: Iterable[analise.Liberada]
) -> tuple[analise.Bloco, ...]:
    """Os blocos da rota que o portão abre hoje para a chave (não depende do CNPJ)."""
    _, abertos = analise.blocos_abertos(liberadas)
    return tuple(b for b in abertos if b.nome in avulsos.blocos)


def _ler(
    avulsos: Avulsos,
    blocos: tuple[analise.Bloco, ...],
    conexao: sa.Connection,
    porta: Porta,
    contexto: ContextoDaChave,
    cnpj: str,
    dia: date,
) -> dict[str, Servido | None]:
    """O que cada bloco serviu (None: nenhum campo liberado). Nada se o CNPJ não é de empresa."""
    if not empresas.e_empresa(porta, cnpj):
        return dict.fromkeys((b.nome for b in blocos), None)
    linhas = acesso.linhas_por_resposta(contexto)
    try:
        return {
            b.nome: b.ler(
                porta,
                _portao(conexao, contexto, b.conjunto, b.finalidade),
                linhas,
                cnpj,
                dia,
            )
            for b in blocos
        }
    except pessoas.RespostaComPessoaProibida as erro:
        # a varredura achou CPF ou e-mail num texto da fonte: a resposta inteira cai, nunca um "não achou" falso
        log.error(
            "%s: varredura de pessoa falhou em %d lugar(es)",
            avulsos.rotulo,
            len(erro.caminhos),
        )
        raise _fora_do_ar() from erro


def _contar(
    conexao: sa.Connection,
    contexto: ContextoDaChave,
    blocos: tuple[analise.Bloco, ...],
    lidos: dict[str, Servido | None],
) -> None:
    """Um pedido por conjunto aberto; dois blocos do mesmo conjunto somam as linhas, e o conjunto só conta como
    negado se nenhum deles saiu (a mesma conta da análise)."""
    por_conjunto: dict[tuple[str, str], tuple[int, bool]] = {}
    for bloco in blocos:
        servido = lidos.get(bloco.nome)
        linhas, negado = por_conjunto.get((bloco.conjunto, bloco.finalidade), (0, True))
        por_conjunto[(bloco.conjunto, bloco.finalidade)] = (
            linhas + (0 if servido is None else servido.linhas),
            negado and servido is None,
        )
    for (conjunto, finalidade), (linhas, negado) in por_conjunto.items():
        registrar_consumo(
            conexao, contexto, conjunto=conjunto, finalidade=finalidade,
            linhas=linhas, negado=negado, agora=acesso.agora(),
        )  # fmt: skip


def _corpo(
    avulsos: Avulsos,
    cnpj: str,
    dia: date,
    blocos: tuple[analise.Bloco, ...],
    lidos: dict[str, Servido | None],
) -> tuple[dict, set[str]]:
    """O corpo da resposta (com as chaves em português, que `traduzir_chaves` passa para o inglês) e as fontes."""
    servidos = {nome: lido for nome, lido in lidos.items() if lido is not None}
    fontes = {fonte for lido in servidos.values() for fonte in lido.fontes}
    corpo = {
        "cnpj": cnpj,
        "como_era_em": dia.isoformat(),
        "blocos": {nome: lido.corpo for nome, lido in servidos.items()},
        "nao_encontrado": [
            {"bloco": para_fora(nome), "por_que": analise.NAO_ACHADO}
            for nome, lido in servidos.items()
            if por_tabela.vazio(lido.corpo)
        ],
        "pedidos_usados": len({(b.conjunto, b.finalidade) for b in blocos}),
        "limites": list(avulsos.limites),
    }
    return corpo, fontes


def _lidos_e_contados(
    avulsos: Avulsos, contexto: ContextoDaChave, cnpj: str, dia: date
) -> tuple[dict, set[str]]:
    """Os blocos lidos e contados; 404 se a chave não vê nenhum ou se nada sai."""
    with obter_engine().begin() as conexao:
        liberadas = linhas_liberadas(
            conexao, contexto, acesso.agora().date(), rotas.regras_da_api()
        )
        blocos = _abertos(avulsos, liberadas)
        if not blocos:
            lidos: dict[str, Servido | None] = {}
            registrar_consumo(
                conexao, contexto, conjunto=avulsos.conjunto_do_negado, finalidade=FINALIDADE,
                linhas=0, negado=True, agora=acesso.agora(),
            )  # fmt: skip
        else:
            conjuntos = {(b.conjunto, b.finalidade) for b in blocos}
            acesso.exigir_quota(conexao, contexto, len(conjuntos), acesso.agora())
            with _porta(conexao) as porta:
                lidos = _ler(avulsos, blocos, conexao, porta, contexto, cnpj, dia)
            _contar(conexao, contexto, blocos, lidos)
    if not any(lido is not None for lido in lidos.values()):
        raise HTTPException(status_code=404, detail=NAO_DISPONIVEL)
    return _corpo(avulsos, cnpj, dia, blocos, lidos)


def servir(avulsos: Avulsos, contexto: ContextoDaChave, cnpj: str, dia: date) -> object:
    """A resposta da rota, já com o aviso de piloto, as fontes e as chaves em inglês."""
    with piloto.anotar() as liberados:
        corpo, fontes = _lidos_e_contados(avulsos, contexto, cnpj, dia)
    corpo = piloto.marcar(corpo, liberados)
    return traduzir_chaves(corpo | {"fontes": fontes_da_resposta(fontes)})
