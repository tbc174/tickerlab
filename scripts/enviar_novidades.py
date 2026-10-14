"""Envia uma campanha de Novidades e ofertas a quem marcou o consentimento (migração 0037).

    python -m scripts.enviar_novidades campanhas/2026-11-lancamento.md          (prévia: só admins)
    python -m scripts.enviar_novidades campanhas/2026-11-lancamento.md --todos  (todos os inscritos)

Sem `--todos`, só os e-mails de `TICKERLAB_ADMINS` recebem: confira o e-mail na sua caixa antes de
mandar para todo mundo. Cada pessoa recebe a mesma campanha uma vez só (o registro do envio e a
chave de idempotência do Resend); rodar de novo só tenta quem falhou. Sem `RESEND_API_KEY`, nada
sai. Nenhum e-mail aparece nos registros (logs): só o id da conta.
"""

import argparse
import logging
import os
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

import sqlalchemy as sa

from src import envio_newsletter
from src import envio_novidades as envio
from src.autenticacao import emails_de_admin
from src.banco import novidades_por_email as repo
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.novidades")
Enviar = Callable[..., str]


def _e_admin(email: str, admins: Iterable[str]) -> bool:
    return email.strip().lower() in {a.lower() for a in admins}


def processar(
    conexao: sa.Connection,
    destinatario: repo.Destinatario,
    campanha: envio.Campanha,
    chave: str,
    so_admins: tuple[str, ...] | None,
    enviar: Enviar = envio_newsletter.enviar_pelo_resend,
) -> str | None:
    """Envia a campanha a esta pessoa. Devolve a situação, ou None se nada a fazer.

    `so_admins`: na prévia, a lista de quem pode receber; None manda para todos os inscritos.
    """
    uid = destinatario.inscricao.usuario_id
    if repo.situacao_do_envio(conexao, uid, campanha.id) == "enviado":
        return None
    if so_admins is not None and not _e_admin(destinatario.email, so_admins):
        return None  # fica para o envio com --todos
    link = envio.link_para_sair(destinatario.inscricao.codigo_para_sair)
    mensagem = envio.montar_email(campanha, link)
    try:
        enviar(destinatario.email, mensagem, link, f"novidades-{uid}-{campanha.id}",
               chave, remetente=envio.remetente())  # fmt: skip
    except envio_newsletter.EnvioFalhouError as erro:
        repo.registrar_envio(conexao, uid, campanha.id, "falhou", str(erro))
        return "falhou"
    repo.registrar_envio(conexao, uid, campanha.id, "enviado")
    return "enviado"


def main(argv: list[str] | None = None, enviar: Enviar | None = None) -> int:
    leitor = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    leitor.add_argument("campanha", type=Path, help="o arquivo .md da campanha")
    leitor.add_argument(
        "--todos",
        action="store_true",
        help="manda para todos os inscritos (sem isso: prévia)",
    )
    argumentos = leitor.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        campanha = envio.ler_arquivo_da_campanha(argumentos.campanha)
    except (OSError, envio.CampanhaInvalidaError) as erro:
        log.error("Campanha recusada: %s", erro)
        return 1
    chave = os.environ.get(envio_newsletter.VARIAVEL_DA_CHAVE)
    if not chave:
        log.warning("Sem RESEND_API_KEY: nada foi enviado.")
        return 0
    so_admins = None if argumentos.todos else emails_de_admin()
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    contagem: dict[str, int] = {}
    try:
        with motor.connect() as conexao:
            todos = repo.destinatarios(conexao)
        for destinatario in todos:
            with motor.begin() as conexao:  # uma transação por pessoa
                situacao = processar(conexao, destinatario, campanha, chave, so_admins,
                                     enviar or envio_newsletter.enviar_pelo_resend)  # fmt: skip
            if situacao:
                contagem[situacao] = contagem.get(situacao, 0) + 1
                log.info("Conta %s: %s", destinatario.inscricao.usuario_id, situacao)
        log.info(
            "Novidades %s (%s): %s inscrições; %s",
            campanha.id,
            "todos" if argumentos.todos else "prévia só para admins",
            len(todos),
            contagem or "nada a enviar",
        )
    except sa.exc.SQLAlchemyError as erro:
        log.error("Envio interrompido: %s", erro.__class__.__name__)
        return 1
    finally:
        motor.dispose()
    return 1 if contagem.get("falhou") else 0


if __name__ == "__main__":
    sys.exit(main())
