"""A primeira cópia de cada página de negócio no Internet Archive (Wayback Machine; ADR 0082, série 5
do plano de M&A, passo 4).

A página da assessoria não diz quando o negócio ficou público, e a nossa primeira coleta é de 16/10/2026.
A cópia mais antiga no Wayback é a prova de que a página já estava no ar naquele momento: o
`conhecido_em` do negócio pode ser essa data (`base/ma_datas.py`), nunca uma data contada no texto.

Regras (testes em `tests/test_base_arquivo_wayback.py`):
- um pedido à API CDX por página de negócio já guardada no acervo (a lista vem do registro de
  coletas, não do site), com pausa e o nosso robô identificado; a resposta (JSON pequeno com as
  datas das cópias) é o original guardado, com SHA-256, e é ela a prova;
- o `robots.txt` do `web.archive.org` é lido antes, a cada coleta: se proibir a consulta, nada é
  pedido; se não existir (hoje responde 404), não proíbe;
- o Internet Archive sai do ar às vezes ("Temporarily Offline", uma página HTML no lugar do JSON):
  cada consulta é tentada até `TENTATIVAS` vezes, com espera crescente; depois fica como falha e
  volta na semana seguinte;
- consulta já guardada não é refeita: a cópia mais antiga não muda.

Termos de uso lidos em 16/10/2026 (archive.org/about/terms): acesso "for scholarship and research
purposes only" e nada de guardar dado pessoal. Por isso só a data das cópias entra na base, e a
licença fica "só uso interno" até o parecer (`src/banco/coletas.py`).
"""

import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit
from urllib.robotparser import RobotFileParser

from base.arquivo.assessorias import Assessoria
from base.arquivo.cliente_http import AGENTE
from base.arquivo.coleta import (
    COMECO_DE_HTML,
    Alvo,
    Cliente,
    Descobrir,
    ErroDeDescoberta,
    Fonte,
    Obter,
)
from src.banco.coletas import originais_mais_recentes
from src.banco.conexao import obter_engine

esperar = time.sleep  # só este módulo espera por aqui: os testes trocam este nome, não o `time.sleep` do processo
CDX = "https://web.archive.org/cdx/search/cdx"
ROBOTS = "https://web.archive.org/robots.txt"
CAMPOS = "timestamp,original,statuscode,digest"
PAUSA_ENTRE_CONSULTAS_EM_SEGUNDOS = 4.0
TENTATIVAS = 3
ESPERA_ENTRE_AS_TENTATIVAS_EM_SEGUNDOS = 30.0
HTTP_NAO_ENCONTRADO = 404


def consulta(pagina: str) -> str:
    """O endereço da consulta à API CDX com todas as cópias da página (o original guardado)."""
    return f"{CDX}?url={quote(pagina, safe='')}&output=json&fl={CAMPOS}"


def pagina_da_consulta(endereco: str) -> str:
    return parse_qs(urlsplit(endereco).query)["url"][0]


def _robots(cliente: Cliente) -> str:
    """O `robots.txt` do Wayback; vazio quando ele não existe (404 não proíbe nada)."""
    try:
        return cliente.ler(ROBOTS).conteudo.decode("utf-8", errors="replace")
    except Exception as erro:
        resposta = getattr(erro, "response", None)
        if getattr(resposta, "status_code", None) == HTTP_NAO_ENCONTRADO:
            return ""
        raise


def _obter(endereco: str) -> Obter:
    """Lê a consulta e grava o JSON; tenta de novo quando o Internet Archive está fora do ar."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        motivo = ""
        for tentativa in range(TENTATIVAS):
            if tentativa:
                esperar(ESPERA_ENTRE_AS_TENTATIVAS_EM_SEGUNDOS * tentativa)
            try:
                resposta = cliente.ler(endereco)
            except Exception as erro:  # noqa: BLE001 (conexão que cai ou erro 5xx: tenta de novo)
                motivo = f"{type(erro).__name__}: {erro}"
                continue
            if COMECO_DE_HTML.match(resposta.conteudo):
                motivo = "o Internet Archive respondeu uma página HTML (fora do ar)"
                continue
            destino.write_bytes(resposta.conteudo)
            return resposta.cabecalhos
        raise ValueError(f"{TENTATIVAS} tentativas sem resposta: {motivo}")

    return obter


def descobrir(assessoria: Assessoria) -> Descobrir:
    """Lê o `robots.txt` e devolve uma consulta por página de negócio já guardada no acervo."""

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        leitor = RobotFileParser()
        leitor.parse(_robots(cliente).splitlines())
        with obter_engine().connect() as conexao:
            guardadas = originais_mais_recentes(conexao, f"assessoria-{assessoria.id}")
        paginas = sorted(g.url for g in guardadas)
        if not paginas:
            raise ErroDeDescoberta(
                f"wayback-{assessoria.id}: nenhuma página da assessoria guardada"
            )
        consultas = [consulta(p) for p in paginas]
        if not leitor.can_fetch(AGENTE, consultas[0]):
            raise ErroDeDescoberta(
                f"wayback-{assessoria.id}: o robots.txt do Wayback proíbe a consulta CDX; "
                "nada foi pedido"
            )
        return [Alvo(c, ".json", obter=_obter(c)) for c in consultas]

    return _descobrir


def fonte(assessoria: Assessoria) -> Fonte:
    return Fonte(
        f"wayback-{assessoria.id}",
        "semanal",
        descobrir(assessoria),
        "json",
        guardado_vale=lambda anterior: True,  # a cópia mais antiga não muda
        pausa_minima=PAUSA_ENTRE_CONSULTAS_EM_SEGUNDOS,
    )
