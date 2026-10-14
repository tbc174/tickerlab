"""Origem do cadastro: de onde veio a pessoa, lida do cookie próprio `tl_origem`.

O Google apaga os parâmetros da URL no login (`st.login`), então o site `tickerlab.com.br` guarda
as UTMs e o `?ref=` num cookie do domínio `.tickerlab.com.br` e o app lê no primeiro login.
Nada vai para Google ou Meta (plano da campanha, PR 1; `campanha-medicao.md`).

**Formato do cookie (contrato com o site):** campos `chave=valor` separados por `|`, nesta ordem:

    s=google|m=cpc|c=testamos-ifr2|t=reel-1|r=clube-do-robo|v=2026-12-07

| chave | campo | o quê |
|---|---|---|
| `s` | `utm_source` | de onde (`google`, `instagram`, código do criador) |
| `m` | `utm_medium` | que tipo (`cpc`, `publi`, `afiliado`...) |
| `c` | `utm_campaign` | qual campanha |
| `t` | `utm_content` | qual peça |
| `r` | `ref` | código do criador do link `?ref=` |
| `v` | primeira visita | data `AAAA-MM-DD` |

Campo vazio ou ausente vale "sem informação". O valor pode vir codificado para URL
(`encodeURIComponent`). **Só passam letras minúsculas sem acento, números e hífen, até 60
caracteres:** qualquer outra coisa (um e-mail colado num `utm_*`, espaço, maiúscula) deixa o campo
vazio, para nenhum dado pessoal entrar no banco por engano. Chaves desconhecidas são ignoradas.
"""

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import unquote

NOME_DO_COOKIE = "tl_origem"
TAMANHO_MAXIMO_DO_CAMPO = 60
TAMANHO_MAXIMO_DO_COOKIE = 500  # 6 campos de até 60 caracteres cabem com folga
_CAMPO_VALIDO = re.compile(rf"[a-z0-9-]{{1,{TAMANHO_MAXIMO_DO_CAMPO}}}")
_DATA_VALIDA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_CHAVES = {"s": "source", "m": "medium", "c": "campaign", "t": "content", "r": "ref"}


@dataclass(frozen=True)
class Origem:
    source: str | None = None
    medium: str | None = None
    campaign: str | None = None
    content: str | None = None
    ref: str | None = None
    primeira_visita: date | None = None


def ler_origem(valor: str | None) -> Origem | None:
    """Lê o cookie `tl_origem`; devolve `None` se ele faltar, for grande demais ou não tiver
    nenhum campo válido."""
    if not valor or len(valor) > TAMANHO_MAXIMO_DO_COOKIE:
        return None
    campos: dict[str, str] = {}
    primeira_visita = None
    for parte in unquote(valor).split("|"):
        chave, _, texto = parte.partition("=")
        if chave in _CHAVES and _CAMPO_VALIDO.fullmatch(texto):
            campos[_CHAVES[chave]] = texto
        elif chave == "v":
            primeira_visita = _ler_data(texto)
    if not campos and primeira_visita is None:
        return None
    return Origem(**campos, primeira_visita=primeira_visita)


def _ler_data(texto: str) -> date | None:
    if not _DATA_VALIDA.fullmatch(texto):
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None
