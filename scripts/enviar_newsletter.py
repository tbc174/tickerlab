"""Envia a Newsletter por e-mail a quem se inscreveu (Research, etapa 5c; decisão 0020).

    python -m scripts.enviar_newsletter         (no VPS: todo dia, depois das coletas)

Para cada inscrição: hoje é dia dessa frequência? A edição deste período ainda não saiu? A
pessoa pode receber? (trava `SO_PARA_ADMINS` até o parecer jurídico.) Então monta a mesma edição
da página, com os parâmetros dela, e envia pelo Resend.

Sem `RESEND_API_KEY`, nada sai: a edição é montada e registrada como "retida" (dá para testar no
servidor antes de criar a conta). Uma falha de envio fica registrada e é tentada de novo na
próxima vez. Nenhum e-mail aparece nos registros (logs): só o id da conta.
"""

import argparse
import logging
import os
import sys
import uuid
from collections.abc import Callable
from datetime import datetime

import sqlalchemy as sa

from src import edicao, research
from src import envio_newsletter as envio
from src import presets as research_presets
from src.autenticacao import emails_de_admin
from src.banco import newsletter_por_email as repo
from src.banco.conexao import criar_engine, migrar_para
from src.banco.dados_do_usuario import (
    carregar_carteira,
    listar_favoritos,
    listar_watchlists,
    presets_atuais,
)
from src.carteira_research import Fotografia
from src.configuracao import url_do_banco
from src.dados import normalizar_ticker
from src.planos import CARTEIRA_NO_RESEARCH, pode_usar
from src.relatorios import agora

log = logging.getLogger("tickerlab.newsletter")
Enviar = Callable[..., str]


def tickers_da_lista(
    conexao: sa.Connection, usuario_id: uuid.UUID, plano: str, lista: str
) -> tuple[list[str], Fotografia | None] | None:
    """(tickers, carteira) da lista inscrita, ou None se ela não existe mais."""
    if lista == research.NOME_DA_DEMONSTRACAO:
        return list(research.DEMONSTRACAO), None
    if lista == research.NOME_DOS_FAVORITOS:
        favoritos = [
            normalizar_ticker(t) for t in listar_favoritos(conexao, usuario_id)
        ]
        return (favoritos, None) if favoritos else None
    if lista == research.NOME_DA_CARTEIRA:
        carteira = (
            carregar_carteira(conexao, usuario_id)
            if pode_usar(plano, CARTEIRA_NO_RESEARCH)
            else None
        )
        return (list(carteira.pesos), carteira) if carteira else None
    for watchlist in listar_watchlists(conexao, usuario_id):
        if watchlist.nome == lista:
            return list(watchlist.tickers), None
    return None


def _parametros(
    conexao: sa.Connection, usuario_id: uuid.UUID
) -> research_presets.Resolucao:
    try:
        return research_presets.resolver(presets_atuais(conexao, usuario_id))
    except (
        ValueError
    ):  # guardados que não combinam mais: os padrões (como a página faz)
        return research_presets.resolver([])


def processar(
    conexao: sa.Connection,
    destinatario: repo.Destinatario,
    momento: datetime,
    chave: str | None,
    admins: tuple[str, ...],
    enviar: Enviar = envio.enviar_pelo_resend,
) -> str | None:
    """Envia (ou retém) a edição desta pessoa. Devolve a situação, ou None se nada a fazer."""
    inscricao = destinatario.inscricao
    uid = inscricao.usuario_id
    periodo = envio.periodo_da_edicao(inscricao.cadencia, momento.date())
    if periodo is None or repo.situacao_do_envio(conexao, uid, periodo) in (
        "enviado",
        "retido",
    ):
        return None
    if not envio.pode_receber(destinatario.email, admins):
        repo.registrar_envio(
            conexao, uid, periodo, "retido", "aguardando o parecer jurídico"
        )
        return "retido"
    achada = tickers_da_lista(conexao, uid, destinatario.plano, inscricao.lista)
    if achada is None:
        repo.registrar_envio(conexao, uid, periodo, "retido", "a lista não existe mais")
        return "retido"
    tickers, carteira = achada
    janela = envio.JANELA_DA_CADENCIA[inscricao.cadencia]
    a_edicao = edicao.montar_edicao(
        conexao,
        inscricao.lista,
        tickers,
        janela,
        _parametros(conexao, uid),
        momento,
        carteira,
    )
    link = envio.link_para_sair(inscricao.codigo_para_sair)
    mensagem = envio.montar_email(a_edicao, link)
    if not chave:
        repo.registrar_envio(conexao, uid, periodo, "retido", "sem RESEND_API_KEY")
        return "retido"
    try:
        enviar(destinatario.email, mensagem, link, f"newsletter-{uid}-{periodo}", chave)
    except envio.EnvioFalhouError as erro:
        repo.registrar_envio(conexao, uid, periodo, "falhou", str(erro))
        return "falhou"
    repo.registrar_envio(conexao, uid, periodo, "enviado")
    return "enviado"


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    chave = os.environ.get(envio.VARIAVEL_DA_CHAVE)
    momento, admins = agora(), emails_de_admin()
    contagem: dict[str, int] = {}
    try:
        with motor.connect() as conexao:
            todos = repo.destinatarios(conexao)
        for destinatario in todos:
            with (
                motor.begin() as conexao
            ):  # uma transação por pessoa: um erro não trava os outros
                situacao = processar(conexao, destinatario, momento, chave, admins)
            if situacao:
                contagem[situacao] = contagem.get(situacao, 0) + 1
                log.info("Conta %s: %s", destinatario.inscricao.usuario_id, situacao)
        log.info(
            "Newsletter: %s inscrições; %s",
            len(todos),
            contagem or "nada a enviar hoje",
        )
    except sa.exc.SQLAlchemyError as erro:
        log.error("Envio interrompido: %s", erro.__class__.__name__)
        return 1
    finally:
        motor.dispose()
    return 1 if contagem.get("falhou") else 0


if __name__ == "__main__":
    sys.exit(main())
