"""Boletim diário da base por e-mail (`base/boletim/`): a evolução desde a última fotografia, as
tarefas que falharam, a análise do dia (rodízio) e um parágrafo de leitura pela API.
    python -m scripts.enviar_boletim_da_base             (fotografa, monta e envia)
    python -m scripts.enviar_boletim_da_base --ensaio    (monta e grava o HTML; não envia nem guarda)
    python -m scripts.enviar_boletim_da_base --sem-ia    (sem o parágrafo da API)

Feito para o servidor de casa, onde está a base, pelo `rodar-tarefa.sh` (marca `boletim-base`).
Guarda em `<acervo>/boletim/`: `fotos/AAAA-MM-DD.json` (a fotografia do dia), `AAAA-MM-DD.html` (o
e-mail) e `enviados/AAAA-MM-DD` (o id do Resend; com ele, rodar de novo no mesmo dia não reenvia, a
não ser com `--forcar`). Variáveis: `TICKERLAB_BOLETIM_PARA` (um endereço só), `RESEND_API_KEY`,
`ANTHROPIC_API_KEY` (opcional), `TICKERLAB_BOLETIM_TAREFAS` (pasta das marcas `.ok`/`.falha`) e
`TICKERLAB_BOLETIM_DIARIAS` (as tarefas diárias, separadas por espaço).
Saída 0 enviado (ou já enviado hoje); 1 com uma linha `FALHAS: ...` (vai para o Kuma).
"""

import argparse
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
import requests

from base.boletim import analises as an
from base.boletim import email as em
from base.boletim import fotografia as fo
from base.boletim import leitura_ia as li
from base.boletim import tarefas as ta
from src import acervo
from src.envio_newsletter import VARIAVEL_DA_CHAVE

log = logging.getLogger("tickerlab.boletim_da_base")
FUSO = ZoneInfo("America/Sao_Paulo")
VARIAVEL_DAS_TAREFAS = "TICKERLAB_BOLETIM_TAREFAS"
VARIAVEL_DAS_DIARIAS = "TICKERLAB_BOLETIM_DIARIAS"


def _falha(motivo: str) -> int:
    print(f"FALHAS: boletim-base: {motivo}", flush=True)
    return 1


def main(
    argv: list[str] | None = None,
    transporte: em.Transporte = requests.post,
    cliente_ia: anthropic.Anthropic | None = None,
) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--hoje", type=date.fromisoformat, default=None)
    argumentos.add_argument("--base", type=Path, default=None)
    argumentos.add_argument("--boletins", type=Path, default=None)
    argumentos.add_argument("--ensaio", action="store_true")
    argumentos.add_argument("--sem-ia", action="store_true")
    argumentos.add_argument("--forcar", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    agora = datetime.now(FUSO)
    hoje = opcoes.hoje or agora.date()
    pasta_do_acervo = acervo.pasta_do_acervo() or Path("dados_locais/acervo")
    raiz = opcoes.base or pasta_do_acervo / "base"
    boletins = opcoes.boletins or pasta_do_acervo / "boletim"
    enviado = boletins / "enviados" / hoje.isoformat()
    if not opcoes.ensaio and enviado.exists() and not opcoes.forcar:
        log.info("O boletim de %s já foi enviado (%s); nada a fazer.", hoje, enviado)
        return 0
    para = chave = ""
    if not opcoes.ensaio:
        try:
            para = em.destinatario()
        except em.DestinatarioInvalidoError as erro:
            return _falha(str(erro))
        chave = os.environ.get(VARIAVEL_DA_CHAVE) or ""
        if not chave:
            return _falha(f"sem {VARIAVEL_DA_CHAVE} no ambiente")

    foto = fo.fotografar(raiz)
    anterior = fo.ultima_antes(boletins / "fotos", hoje)
    log.info(
        "Fotografia: %s tabelas; anterior: %s",
        len(foto["tabelas"]),
        anterior and anterior[0],
    )
    tarefas = ta.ler_estado(
        Path(os.environ.get(VARIAVEL_DAS_TAREFAS) or "/estado-tarefas"),
        agora,
        (os.environ.get(VARIAVEL_DAS_DIARIAS) or "").split(),
    )
    secao = an.analise_do_dia(an.Contexto(raiz, hoje, foto))
    conteudo = em.Conteudo(
        dia=hoje,
        dia_anterior=anterior[0] if anterior else None,
        foto=foto,
        foto_anterior=anterior[1] if anterior else None,
        tarefas=tarefas,
        secao=secao,
        leitura=li.Leitura(None, "desligado nesta rodada (--sem-ia)"),
        proxima=an.titulo_do_dia(hoje + timedelta(days=1)),
    )
    if not opcoes.sem_ia:
        leitura = li.escrever_leitura(em.fatos(conteudo), cliente_ia)
        log.info("Leitura da IA: %s; tokens %s", leitura.motivo or "ok", leitura.tokens)
        conteudo = em.Conteudo(**{**conteudo.__dict__, "leitura": leitura})
    email = em.montar(conteudo)

    boletins.mkdir(parents=True, exist_ok=True)
    nome = (
        f"ensaio-{hoje.isoformat()}.html"
        if opcoes.ensaio
        else f"{hoje.isoformat()}.html"
    )
    (boletins / nome).write_text(email.html, encoding="utf-8")
    log.info("Assunto: %s; HTML em %s", email.assunto, boletins / nome)
    if opcoes.ensaio:
        return 0

    fo.guardar(foto, boletins / "fotos", hoje)
    try:
        id_da_mensagem = em.enviar(email, para, hoje, chave, transporte)
    except em.EnvioFalhouError as erro:
        return _falha(str(erro))
    enviado.parent.mkdir(parents=True, exist_ok=True)
    enviado.write_text(f"{agora.isoformat()} {id_da_mensagem}\n", encoding="utf-8")
    log.info("Boletim enviado (Resend %s).", id_da_mensagem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
