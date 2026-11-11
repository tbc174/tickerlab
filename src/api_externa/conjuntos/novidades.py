"""As novidades da pesquisa na API externa (linha 830): `GET /data/v1/research/news`.

As fontes que o bot conferente provou na semana, cada uma com o órgão, a data, o trecho literal e o sha256 do
original. O dado vem do `novidades.json` que o exportador do PC gera (`pesquisa/novidades.py`) e que chega ao
servidor por outro passo; a rota só lê o arquivo, não consulta o banco da base.

Não passa pelo portão de campos (D10 exige tabela do dicionário com prontidão, e isto é um arquivo de citações
conferidas, não uma tabela da base). Em troca, a leitura **repete** as regras do exportador, item a item
(`src/novidades_da_pesquisa.py`): órgão da tabela, fonte com licença e revenda liberada, hash de 64 hex,
citação curta e sem CPF nem marca de pessoa. A chave e a quota são as de sempre; cada fonte usada leva a
atribuição da licença. Arquivo ausente, ilegível ou vazio: lista vazia e `gerado_em` nulo, nunca item inventado.
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from src import acervo
from src.novidades_da_pesquisa import (
    fonte_liberada,
    orgao_da_url,
    texto_publicavel,
)

CONJUNTO = "research"
VARIAVEL_DO_ARQUIVO = "TICKERLAB_NOVIDADES"
NOME_DO_ARQUIVO = "novidades.json"
DIAS_PADRAO = 7
DIAS_MAXIMO = 30
HASH = re.compile(r"[0-9a-f]{64}")
DATA = re.compile(r"\d{4}-\d{2}-\d{2}")


class PedidoInvalido(Exception):
    """O pedido não vale; `codigo` é o que a rota devolve em 400."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


@dataclass(frozen=True)
class NovidadesServidas:
    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


def dias_do_pedido(dias: int | None) -> int:
    """Os dias pedidos (padrão 7, de 1 a 30); 400 `invalid_days` fora disso."""
    if dias is None:
        return DIAS_PADRAO
    if not 1 <= dias <= DIAS_MAXIMO:
        raise PedidoInvalido("invalid_days")
    return dias


def caminho_do_arquivo() -> Path | None:
    """O arquivo publicado: a variável `TICKERLAB_NOVIDADES`, ou `novidades.json` na pasta do acervo."""
    valor = os.environ.get(VARIAVEL_DO_ARQUIVO, "").strip()
    if valor:
        return Path(valor)
    pasta = acervo.pasta_do_acervo()
    return None if pasta is None else pasta / NOME_DO_ARQUIVO


def _ler(caminho: Path | None) -> dict:
    if caminho is None or not caminho.is_file():
        return {}
    try:
        lido = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return lido if isinstance(lido, dict) else {}


def _item_publicavel(bruto: object) -> dict[str, str] | None:
    """O item como sai, ou None se qualquer regra falha (o arquivo não é confiado às cegas)."""
    if not isinstance(bruto, dict):
        return None
    campos = {
        nome: bruto.get(nome)
        for nome in ("fonte_url", "data", "afirmacao", "trecho", "sha256", "posicao")
    }
    if not all(isinstance(valor, str) for valor in campos.values()):
        return None
    url, data, afirmacao, trecho, sha, posicao = (str(v) for v in campos.values())
    achado = orgao_da_url(url)
    if achado is None or not fonte_liberada(achado[0]):
        return None
    if not (HASH.fullmatch(sha) and DATA.fullmatch(data) and trecho):
        return None
    if not texto_publicavel(afirmacao, trecho, url, posicao):
        return None
    return {
        "orgao": achado[1],
        "fonte": achado[0],
        "fonte_url": url,
        "data": data,
        "afirmacao": afirmacao,
        "trecho": trecho,
        "sha256": sha,
        "posicao": posicao,
    }


def _gerado_em(lido: dict) -> str | None:
    valor = lido.get("gerado_em")
    return valor if isinstance(valor, str) and valor else None


def novidades(
    dias: int,
    linhas_maximas: int,
    hoje: date | None = None,
    caminho: Path | None = None,
) -> NovidadesServidas:
    """Os itens provados nos últimos `dias` (mais novos primeiro), até `linhas_maximas`."""
    lido = _ler(caminho if caminho is not None else caminho_do_arquivo())
    hoje = hoje or datetime.now(UTC).date()
    corte = (hoje - timedelta(days=dias)).isoformat()
    brutos = lido.get("itens")
    itens = [
        item
        for bruto in (brutos if isinstance(brutos, list) else [])
        if (item := _item_publicavel(bruto)) is not None and item["data"] >= corte
    ]
    itens.sort(key=lambda item: item["data"], reverse=True)
    itens = itens[:linhas_maximas]
    corpo = {
        "gerado_em": _gerado_em(lido),
        "dias": dias,
        "total_de_novidades": len(itens),
        "itens": itens,
    }
    return NovidadesServidas(
        corpo=corpo, fontes={item["fonte"] for item in itens}, linhas=len(itens)
    )
