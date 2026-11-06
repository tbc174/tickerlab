"""Posts das assessorias independentes de M&A: o original de cada página de negócio (ADR 0082).

No middle market a alvo é fechada e nada passa pela CVM: o post da assessoria ("a X foi adquirida
pela Y") costuma ser o único registro público. Aqui o arquivista só guarda a página como veio; os
fatos (partes, tipo, setor) saem dela na extração, sem texto copiado e sem pessoa física.

Regras (testes em `tests/test_base_arquivo_assessorias.py`):
- o `robots.txt` é lido **antes** do sitemap, a cada coleta; se ele proibir uma página de negócio
  ao nosso robô, ou pedir mais espera que a nossa, a coleta inteira para (falha com aviso), em vez
  de pular em silêncio;
- só as páginas em português (o site repete cada negócio em `/en/` e `/es/`);
- página já guardada não é baixada de novo: o post de um negócio fechado quase não muda, e assim a
  coleta da semana só pede o robots, o sitemap e os negócios novos;
- uma página a cada `PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS` (site pequeno de terceiros);
- a vigia (`termos-<id>-*` em `fontes.TERMOS`) avisa quando o robots ou a política do site mudam.

Site entra aqui só depois do inventário (tema 19 da trilha M&A): `robots.txt` e termos lidos.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import sqlalchemy as sa

from base.arquivo.cliente_http import AGENTE
from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte

PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS = 3.0
LOC_DO_SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"


@dataclass(frozen=True)
class Assessoria:
    id: str  # a fonte fica "assessoria-<id>"
    site: str  # "https://www.igcp.com.br", sem barra no fim
    transacao: (
        str  # caminho inteiro de uma página de negócio em português (expressão regular)
    )

    @property
    def robots(self) -> str:
        return self.site + "/robots.txt"

    @property
    def sitemap(self) -> str:
        return self.site + "/sitemap.xml"


# inventário de 16/10/2026: robots.txt só aponta o sitemap; sem termos de uso, só a política de
# privacidade; 272 negócios em português; a página dá as partes e o país, sem data nem valor
IGC = Assessoria("igc", "https://www.igcp.com.br", r"/transactions/[^/]+")
ASSESSORIAS = (IGC,)
# o que a vigia acompanha em cada site (além do robots.txt)
POLITICAS = {"igc": {"privacidade": IGC.site + "/politica-de-privacidade"}}


def paginas_de_transacao(sitemap: bytes, assessoria: Assessoria) -> list[str]:
    """As páginas de negócio em português do sitemap, sem repetição e em ordem."""
    host = urlsplit(assessoria.site).netloc
    padrao = re.compile(assessoria.transacao)
    paginas = set()
    for loc in ET.fromstring(sitemap).iter(LOC_DO_SITEMAP):
        url = (loc.text or "").strip()
        partes = urlsplit(url)
        if partes.netloc == host and padrao.fullmatch(partes.path):
            paginas.add(url)
    return sorted(paginas)


def _conferir_robots(robots: str, paginas: list[str], assessoria: Assessoria) -> None:
    leitor = RobotFileParser()
    leitor.parse(robots.splitlines())
    proibidas = [p for p in paginas if not leitor.can_fetch(AGENTE, p)]
    if proibidas:
        raise ErroDeDescoberta(
            f"assessoria-{assessoria.id}: o robots.txt proíbe {len(proibidas)} página(s) "
            f"de negócio (ex.: {proibidas[0]}); nada foi baixado"
        )
    espera = leitor.crawl_delay(AGENTE)
    if espera is not None and float(espera) > PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS:
        raise ErroDeDescoberta(
            f"assessoria-{assessoria.id}: o robots.txt pede Crawl-delay de {espera} s, "
            f"mais que os {PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS:.0f} s entre as nossas páginas"
        )


def descobrir(assessoria: Assessoria) -> Descobrir:
    """Lê o robots.txt e o sitemap; devolve as páginas de negócio, ou falha se o robots proíbe."""

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        robots = cliente.ler(assessoria.robots).conteudo.decode(
            "utf-8", errors="replace"
        )
        paginas = paginas_de_transacao(
            cliente.ler(assessoria.sitemap).conteudo, assessoria
        )
        if not paginas:
            raise ErroDeDescoberta(
                f"assessoria-{assessoria.id}: nenhuma página de negócio no sitemap"
            )
        _conferir_robots(robots, paginas, assessoria)
        return [Alvo(p, ".html") for p in paginas]

    return _descobrir


def _ja_guardada(anterior: sa.Row) -> bool:
    """Basta existir a coleta "ok" da página (o post de um negócio fechado quase não muda)."""
    return True


def fonte(assessoria: Assessoria) -> Fonte:
    return Fonte(
        f"assessoria-{assessoria.id}",
        "semanal",
        descobrir(assessoria),
        "html",
        guardado_vale=_ja_guardada,
        pausa_minima=PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS,
    )


def termos() -> dict[str, str]:
    """Os endereços que a vigia acompanha: `termos-<id>-robots` e as políticas de cada site."""
    vigiados = {f"termos-{a.id}-robots": a.robots for a in ASSESSORIAS}
    for ident, paginas in POLITICAS.items():
        vigiados |= {f"termos-{ident}-{nome}": url for nome, url in paginas.items()}
    return vigiados
