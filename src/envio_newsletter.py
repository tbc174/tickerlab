"""Newsletter por e-mail (Research, etapa 5c; decisão 0020): quando, para quem e o quê.

- **Opt-in:** só recebe quem se inscreveu numa lista, com consentimento próprio (texto e versão
  aqui). Cada e-mail traz um link para sair que funciona sem login (`/newsletter/sair` na API).
- **Trava até o parecer jurídico:** `SO_PARA_ADMINS`. Enquanto valer, a edição de quem não é
  administrador fica "retida" e não sai (o PRD condiciona o envio a parecer; liberar exige uma
  decisão nova).
- **Uma edição por período:** a diária uma vez por dia; a semanal às segundas, com a semana
  anterior. O registro do envio (usuário + período) e a chave de idempotência do Resend impedem
  mandar duas vezes, mesmo se a coleta rodar de novo.
- **Conteúdo:** a mesma edição da página e do PDF (`src.newsletter`), com fonte e link de cada
  item e a seção de limites. Nenhum dado da pessoa vai para os registros (logs).
"""

import html
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

import requests

from src import marca
from src.newsletter import TITULO_DOS_TRECHOS, Edicao, Item

VERSAO_DO_CONSENTIMENTO = "2026-10-12"
TEXTO_DO_CONSENTIMENTO = (
    "Quero receber a Newsletter desta lista por e-mail, na frequência escolhida. Sei que é um "
    "resumo de documentos públicos, não uma recomendação, e que posso sair a qualquer momento "
    "pelo link em cada e-mail ou aqui."
)
SO_PARA_ADMINS = True  # decisão 0020: até o parecer jurídico, só a equipe recebe
JANELA_DA_CADENCIA = {"diaria": 1, "semanal": 7}
NOMES_DAS_CADENCIAS = {"diaria": "Diária", "semanal": "Semanal (às segundas)"}
SEGUNDA = 0
VARIAVEL_DA_CHAVE = "RESEND_API_KEY"  # segredo: só no .env do servidor
VARIAVEL_DO_REMETENTE = "TICKERLAB_NEWSLETTER_REMETENTE"
REMETENTE_PADRAO = "TickerLab <newsletter@tickerlab.com.br>"
VARIAVEL_DA_API = "TICKERLAB_URL_DA_API"
URL_DA_API_PADRAO = "https://api.tickerlab.com.br"
URL_DO_RESEND = "https://api.resend.com/emails"
TEMPO_MAXIMO = 30  # segundos por envio


def periodo_da_edicao(cadencia: str, hoje: date) -> str | None:
    """A chave do período (uma edição por chave), ou None se hoje não é dia de enviar."""
    if cadencia == "diaria":
        return hoje.isoformat()
    if hoje.weekday() != SEGUNDA:
        return None
    ano, semana, _ = hoje.isocalendar()
    return f"{ano}-W{semana:02d}"


def pode_receber(email: str, admins: Iterable[str]) -> bool:
    """A trava da decisão 0020: até o parecer, só os e-mails de `TICKERLAB_ADMINS`."""
    return not SO_PARA_ADMINS or email.strip().lower() in {a.lower() for a in admins}


def link_para_sair(codigo: str) -> str:
    base = (os.environ.get(VARIAVEL_DA_API) or URL_DA_API_PADRAO).rstrip("/")
    return f"{base}/newsletter/sair?codigo={codigo}"


@dataclass(frozen=True)
class Email:
    assunto: str
    html: str
    texto: str


def _e(texto: str) -> str:
    return html.escape(texto, quote=True)


def _item_em_html(item: Item) -> str:
    partes = [
        f'<p style="margin:16px 0 4px"><strong>{_e(item.titulo)}</strong></p>',
        f'<p style="margin:0 0 4px">{_e(item.texto)}</p>',
    ]
    if item.trechos:
        citacoes = " ".join(f"“{_e(t)}”" for t in item.trechos)
        partes.append(
            f'<p style="margin:0 0 4px;color:{marca.PAPEL_SUTIL};font-size:13px">'
            f"{_e(TITULO_DOS_TRECHOS)}: {citacoes}</p>"
        )
    if item.link:
        partes.append(
            f'<p style="margin:0"><a href="{_e(item.link)}" style="color:{marca.AZUL}">'
            f"Abrir o documento original na {_e(item.sigla_da_fonte or 'fonte')}</a></p>"
        )
    return "".join(partes)


def _item_em_texto(item: Item) -> str:
    linhas = [item.titulo, item.texto]
    if item.trechos:
        linhas.append(
            f"{TITULO_DOS_TRECHOS}: " + " ".join(f"“{t}”" for t in item.trechos)
        )
    if item.link:
        linhas.append(item.link)
    return "\n".join(linhas)


def montar_email(edicao: Edicao, link_de_saida: str) -> Email:
    """O e-mail da edição, em HTML e em texto puro (os dois com os mesmos itens e limites)."""
    assunto = f"TickerLab · Newsletter {edicao.lista}: {edicao.inicio:%d/%m} a {edicao.fim:%d/%m}"
    corpo_html, corpo_texto = [], []
    for secao in edicao.secoes:
        corpo_html.append(
            f'<h2 style="font-size:17px;margin:28px 0 0">{_e(secao.titulo)}</h2>'
        )
        corpo_texto.append(f"\n== {secao.titulo} ==")
        if not secao.itens:
            corpo_html.append(
                f'<p style="color:{marca.PAPEL_SUTIL}">{_e(secao.vazio)}</p>'
            )
            corpo_texto.append(secao.vazio)
        for item in secao.itens:
            corpo_html.append(_item_em_html(item))
            corpo_texto.append(_item_em_texto(item))
    limites_html = "".join(f"<li>{_e(limite)}</li>" for limite in edicao.limites)
    rodape = (
        "Você recebe este e-mail porque se inscreveu na Newsletter do TickerLab. "
        "Para não receber mais:"
    )
    html_final = (
        f'<div style="font-family:{marca.FONTE},Arial,sans-serif;color:{marca.PAPEL_TEXTO};'
        f'max-width:640px;margin:0 auto;padding:16px">'
        f'<p style="margin:0 0 4px;font-size:22px;font-weight:800;color:{marca.MARINHO}">'
        f'Ticker<span style="color:{marca.AZUL}">Lab</span></p>'
        f'<p style="font-size:13px;color:{marca.PAPEL_SUTIL}">{_e(assunto)}</p>'
        + "".join(corpo_html)
        + '<h2 style="font-size:17px;margin:28px 0 0">Limites</h2>'
        f"<ul>{limites_html}</ul>"
        f'<p style="font-size:12px;color:{marca.PAPEL_SUTIL};margin-top:32px">{_e(rodape)} '
        f'<a href="{_e(link_de_saida)}" style="color:{marca.AZUL}">sair da Newsletter</a>.</p>'
        "</div>"
    )
    texto_final = "\n".join(
        [
            assunto,
            *corpo_texto,
            "\n== Limites ==",
            *(f"- {limite}" for limite in edicao.limites),
            f"\n{rodape} {link_de_saida}",
        ]
    )
    return Email(assunto, html_final, texto_final)


class EnvioFalhouError(RuntimeError):
    """O Resend recusou ou não respondeu (a mensagem não tem o e-mail da pessoa)."""


Transporte = Callable[..., requests.Response]


def enviar_pelo_resend(
    para: str,
    email: Email,
    link_de_saida: str | None,
    idempotencia: str,
    chave: str,
    transporte: Transporte = requests.post,
    remetente: str | None = None,
) -> str:
    """Envia pelo Resend e devolve o id da mensagem. A chave de idempotência evita duplicar.

    Sem `remetente`, vale o da Newsletter (as Novidades passam o delas). Sem `link_de_saida` (o
    boletim interno da base, que só vai para o autor), o e-mail sai sem o cabeçalho de saída."""
    remetente = remetente or os.environ.get(VARIAVEL_DO_REMETENTE) or REMETENTE_PADRAO
    try:
        resposta = transporte(
            URL_DO_RESEND,
            timeout=TEMPO_MAXIMO,
            headers={
                "Authorization": f"Bearer {chave}",
                "Idempotency-Key": idempotencia,
            },
            json={
                "from": remetente,
                "to": [para],
                "subject": email.assunto,
                "html": email.html,
                "text": email.texto,
                **(
                    {
                        "headers": {
                            "List-Unsubscribe": f"<{link_de_saida}>",
                            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                        }
                    }
                    if link_de_saida
                    else {}
                ),
            },
        )
    except requests.RequestException as erro:
        raise EnvioFalhouError(
            f"sem resposta do Resend ({erro.__class__.__name__})"
        ) from None
    if not resposta.ok:
        raise EnvioFalhouError(f"o Resend recusou (HTTP {resposta.status_code})")
    return str(resposta.json().get("id", ""))
