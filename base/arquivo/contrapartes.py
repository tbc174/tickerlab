"""As páginas dos fatos da ficha das contrapartes do café, guardadas como prova (PR 12 do plano do café).

A ficha (`base/contrapartes/cafe.py`) diz o fato com as nossas palavras e o link; a cópia guardada aqui
é só prova interna de que a página dizia aquilo naquela data (nunca vai para tela, API ou exportação).
Fato de recuperação judicial ou fechamento só entra na ficha com a página guardada.

Ligada com o "pode" do Tiago de 18/10/2026 (cópia interna, só dos quatro sites de `SITES_COM_COPIA`).
`paginas_guardadas` diz à ficha quais páginas já estão no acervo; até a primeira coleta, a notícia
fica em "o que não sabemos", com o veículo, a data e o link. Para desligar: tirar `fonte()` de
`base/arquivo/fontes.py::FONTES` e o destino de `base/arquivo/destinos.py`.

Regras (testes em `tests/test_base_contrapartes_cafe.py`):
- só os sites cujos termos não proíbem cópia nem robô (`SITES_COM_COPIA`, termos lidos em 18–19/10/2026
  e registrados em `licencas-por-fonte.md`); AgFeed e Brazil Journal proíbem, a Compre Rural veda
  reprodução: ficam de fora;
- o `robots.txt` de cada site é lido antes, a cada coleta; se ele proibir uma página ao nosso robô ou
  pedir mais espera que a nossa, a coleta inteira para (falha com aviso);
- página já guardada não é baixada de novo (notícia publicada quase não muda);
- uma página a cada `PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS`.
"""

from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import pandas as pd
import sqlalchemy as sa

from base.arquivo import robots
from base.arquivo.cliente_http import AGENTE
from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte
from base.contrapartes import cafe
from src.banco import coletas

ID = "contrapartes-cafe"
PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS = 3.0
SITES_COM_COPIA = (
    "www.almg.gov.br",  # termos: reprodução livre citando fonte e autor
    "www.bloomberglinea.com.br",  # termos da assinatura: uso pessoal e interno
    "revistacultivar.com.br",  # sem termos publicados
    "www.noticiasagricolas.com.br",  # sem termos publicados
)


def paginas_a_guardar(fatos: pd.DataFrame) -> list[str]:
    """Os endereços da coluna `fonte` nos sites com cópia, sem repetição e na ordem da tabela."""
    enderecos = dict.fromkeys(str(f) for f in fatos["fonte"].dropna())
    return [e for e in enderecos if urlsplit(e).netloc in SITES_COM_COPIA]


def _conferir_robots(site: str, texto: str, paginas: list[str]) -> None:
    proibidas = [
        p for p in paginas if not robots.pode_buscar(texto, urlsplit(p).path or "/")
    ]
    if proibidas:
        raise ErroDeDescoberta(
            f"contrapartes-cafe: o robots.txt de {site} proíbe {len(proibidas)} página(s) "
            f"(ex.: {proibidas[0]}); nada foi baixado"
        )
    leitor = RobotFileParser()
    leitor.parse(texto.splitlines())
    espera = leitor.crawl_delay(AGENTE)
    if espera is not None and float(espera) > PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS:
        raise ErroDeDescoberta(
            f"contrapartes-cafe: o robots.txt de {site} pede Crawl-delay de {espera} s, "
            f"mais que os {PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS:.0f} s entre as nossas páginas"
        )


def descobrir(ler_fatos: Callable[[], pd.DataFrame] = cafe.ler) -> Descobrir:
    """Lê o robots.txt de cada site e devolve as páginas dos fatos, ou falha se algum proíbe."""

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        paginas = paginas_a_guardar(ler_fatos())
        por_site: dict[str, list[str]] = {}
        for pagina in paginas:
            por_site.setdefault(urlsplit(pagina).netloc, []).append(pagina)
        for site, do_site in por_site.items():
            texto = cliente.ler(f"https://{site}/robots.txt").conteudo
            _conferir_robots(site, texto.decode("utf-8", errors="replace"), do_site)
        return [Alvo(p, ".html") for p in paginas]

    return _descobrir


def _ja_guardada(anterior: sa.Row) -> bool:
    """Basta existir a coleta "ok" da página."""
    return True


def paginas_guardadas(conexao: sa.Connection) -> frozenset[str]:
    """Os endereços que o arquivista já guardou no acervo (o `guardadas` de `cafe.montar_ficha`)."""
    return frozenset(
        linha.url for linha in coletas.originais_mais_recentes(conexao, ID)
    )


def fonte(ler_fatos: Callable[[], pd.DataFrame] = cafe.ler) -> Fonte:
    return Fonte(
        ID,
        "semanal",
        descobrir(ler_fatos),
        "html",
        guardado_vale=_ja_guardada,
        pausa_minima=PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS,
    )
