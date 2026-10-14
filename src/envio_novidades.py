"""Novidades e ofertas do TickerLab por e-mail (migração 0037): o consentimento, a campanha e o e-mail.

- **Opt-in próprio:** o e-mail do login serve só para a conta (política de privacidade). Só recebe
  quem marcou a caixa abaixo, que começa desmarcada, no primeiro acesso ou em Meus dados. Cada
  e-mail traz um link para sair que funciona sem login (`/novidades/sair` na API) e o cabeçalho de
  saída em um clique.
- **Campanha:** um arquivo Markdown simples. A 1ª linha `# ...` é o assunto; depois, parágrafos,
  itens com `- ` e linhas só com um endereço (viram link). O nome do arquivo é o id da campanha.
- **Honestidade:** o texto não pode prometer rentabilidade (`EXPRESSOES_PROIBIDAS`) e todo e-mail
  diz que nada é recomendação de investimento.
- Nenhum dado da pessoa vai para os registros (logs).
"""

import html
import os
import re
from dataclasses import dataclass
from pathlib import Path

from src import marca
from src.envio_newsletter import URL_DA_API_PADRAO, VARIAVEL_DA_API, Email

VERSAO_DO_CONSENTIMENTO = "2026-10-14"
TEXTO_DO_CONSENTIMENTO = (
    "Quero receber por e-mail novidades e ofertas do TickerLab (lançamentos, recursos novos e "
    "promoções dos planos). Posso sair a qualquer momento pelo link em cada e-mail ou em Meus dados."
)
VARIAVEL_DO_REMETENTE = "TICKERLAB_NOVIDADES_REMETENTE"
REMETENTE_PADRAO = "TickerLab <novidades@tickerlab.com.br>"
AVISO = "Este e-mail não é recomendação de investimento. Rentabilidade passada não garante resultado futuro."
RODAPE = (
    "Você recebe este e-mail porque pediu novidades e ofertas do TickerLab. "
    "Para não receber mais:"
)
# o CLAUDE.md: "nunca prometer rentabilidade". Conferido em minúsculas, no assunto e no corpo.
EXPRESSOES_PROIBIDAS = (
    "garantid",  # rentabilidade garantida, retorno garantido, lucro garantido...
    "lucro certo",
    "sem risco",
    "risco zero",
    "dinheiro fácil",
    "fique rico",
)
_ID_VALIDO = re.compile(r"[a-z0-9-]{1,80}")
_ENDERECO = re.compile(r"https://\S+")


class CampanhaInvalidaError(ValueError):
    """O arquivo da campanha não segue o formato ou promete o que não pode."""


@dataclass(frozen=True)
class Campanha:
    id: str  # o nome do arquivo, sem a extensão
    assunto: str
    blocos: tuple[tuple[str, ...], ...]  # parágrafos; cada um, uma ou mais linhas


def remetente() -> str:
    return os.environ.get(VARIAVEL_DO_REMETENTE) or REMETENTE_PADRAO


def link_para_sair(codigo: str) -> str:
    base = (os.environ.get(VARIAVEL_DA_API) or URL_DA_API_PADRAO).rstrip("/")
    return f"{base}/novidades/sair?codigo={codigo}"


def _conferir_promessas(texto: str) -> None:
    minusculo = texto.lower()
    achadas = [e for e in EXPRESSOES_PROIBIDAS if e in minusculo]
    if achadas:
        raise CampanhaInvalidaError(
            f"O texto promete o que não pode ({', '.join(achadas)}): reescreva sem isso."
        )


def ler_campanha(id_da_campanha: str, texto: str) -> Campanha:
    """Lê o Markdown da campanha. Recusa id fora do padrão, falta de assunto ou de corpo, e
    qualquer promessa de rentabilidade."""
    if not _ID_VALIDO.fullmatch(id_da_campanha):
        raise CampanhaInvalidaError(
            "O nome do arquivo vira o id: só letras minúsculas sem acento, números e hífen."
        )
    linhas = texto.strip().splitlines()
    if not linhas or not linhas[0].startswith("# ") or not linhas[0][2:].strip():
        raise CampanhaInvalidaError("A 1ª linha precisa ser o assunto: '# Assunto'.")
    assunto = linhas[0][2:].strip()
    blocos, atual = [], []
    for linha in linhas[1:]:
        if linha.strip():
            atual.append(linha.strip())
        elif atual:
            blocos.append(tuple(atual))
            atual = []
    if atual:
        blocos.append(tuple(atual))
    if not blocos:
        raise CampanhaInvalidaError("A campanha não tem texto depois do assunto.")
    _conferir_promessas(texto)
    return Campanha(id_da_campanha, assunto, tuple(blocos))


def ler_arquivo_da_campanha(caminho: Path) -> Campanha:
    return ler_campanha(caminho.stem, caminho.read_text(encoding="utf-8"))


def _e(texto: str) -> str:
    return html.escape(texto, quote=True)


def _bloco_em_html(bloco: tuple[str, ...]) -> str:
    if all(linha.startswith("- ") for linha in bloco):
        itens = "".join(f"<li>{_e(linha[2:])}</li>" for linha in bloco)
        return f"<ul>{itens}</ul>"
    if len(bloco) == 1 and _ENDERECO.fullmatch(bloco[0]):
        return f'<p><a href="{_e(bloco[0])}" style="color:{marca.AZUL}">{_e(bloco[0])}</a></p>'
    return f'<p style="margin:0 0 12px">{"<br>".join(_e(l) for l in bloco)}</p>'


def montar_email(campanha: Campanha, link_de_saida: str) -> Email:
    """O e-mail da campanha, em HTML e em texto puro (os dois com o aviso e o link para sair)."""
    assunto = f"TickerLab · {campanha.assunto}"
    corpo_html = "".join(_bloco_em_html(bloco) for bloco in campanha.blocos)
    html_final = (
        f'<div style="font-family:{marca.FONTE},Arial,sans-serif;color:{marca.PAPEL_TEXTO};'
        f'max-width:640px;margin:0 auto;padding:16px">'
        f'<p style="margin:0 0 16px;font-size:22px;font-weight:800;color:{marca.MARINHO}">'
        f'Ticker<span style="color:{marca.AZUL}">Lab</span></p>'
        f'<h1 style="font-size:20px;margin:0 0 16px">{_e(campanha.assunto)}</h1>'
        f"{corpo_html}"
        f'<p style="font-size:12px;color:{marca.PAPEL_SUTIL};margin-top:32px">{_e(AVISO)}</p>'
        f'<p style="font-size:12px;color:{marca.PAPEL_SUTIL}">{_e(RODAPE)} '
        f'<a href="{_e(link_de_saida)}" style="color:{marca.AZUL}">sair das novidades</a>.</p>'
        "</div>"
    )
    texto_final = "\n\n".join(
        [
            campanha.assunto,
            *("\n".join(bloco) for bloco in campanha.blocos),
            AVISO,
            f"{RODAPE} {link_de_saida}",
        ]
    )
    return Email(assunto, html_final, texto_final)
