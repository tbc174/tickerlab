"""Configuração dos logs: texto legível no desenvolvimento, uma linha de JSON por registro em produção.

Em produção (`TICKERLAB_LOG_FORMATO=json`) cada linha é um JSON com hora, nível, origem e
mensagem, o que facilita filtrar com `docker logs ... | jq`. Nunca registre e-mail, nome, senhas
ou chaves: o que passa por aqui vai para o disco do servidor. Pelo mesmo motivo, o log de acesso
do uvicorn sai sem a query string (o link de descadastro leva um código que vale como senha).
"""

import json
import logging
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime

VARIAVEL_DO_FORMATO = "TICKERLAB_LOG_FORMATO"
VARIAVEL_DO_NIVEL = "TICKERLAB_LOG_NIVEL"
TAMANHO_MAXIMO_DO_ERRO = 4000  # caracteres do rastreio de uma exceção
LOGGERS_DO_UVICORN = ("uvicorn", "uvicorn.error", "uvicorn.access")
FORMATO_DE_TEXTO = "%(asctime)s %(levelname)s %(name)s: %(message)s"
# no uvicorn.access, args = (cliente, método, caminho, versão do HTTP, status)
POSICAO_DO_CAMINHO = 2


class SemQueryString(logging.Filter):
    """Tira a query string do caminho no log de acesso do uvicorn.

    `GET /newsletter/sair?codigo=...` levava ao disco o código que descadastra sem login (achado
    6a do Codex, ADR 0091). Nenhuma rota precisa da query no log, então ela sai de todas.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) > POSICAO_DO_CAMINHO:
            caminho = args[POSICAO_DO_CAMINHO]
            if isinstance(caminho, str) and "?" in caminho:
                novos = list(args)
                novos[POSICAO_DO_CAMINHO] = caminho.split("?", 1)[0]
                record.args = tuple(novos)
        return True


class FormatadorJson(logging.Formatter):
    """Um registro por linha, em JSON, com campos em português."""

    def format(self, record: logging.LogRecord) -> str:
        linha = {
            "hora": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "nivel": record.levelname,
            "origem": record.name,
            "mensagem": record.getMessage(),
        }
        if record.exc_info:
            linha["erro"] = self.formatException(record.exc_info)[
                :TAMANHO_MAXIMO_DO_ERRO
            ]
        return json.dumps(linha, ensure_ascii=False)


def _nivel(texto: str | None) -> int:
    nivel = logging.getLevelName((texto or "INFO").upper())
    return nivel if isinstance(nivel, int) else logging.INFO


def configurar_logs(ambiente: Mapping[str, str] | None = None) -> logging.Handler:
    """Liga os logs do processo. Pode ser chamada várias vezes (o Streamlit reexecuta o script)."""
    ambiente = os.environ if ambiente is None else ambiente
    em_json = (ambiente.get(VARIAVEL_DO_FORMATO) or "").lower() == "json"
    raiz = logging.getLogger()
    for antigo in [h for h in raiz.handlers if getattr(h, "_do_tickerlab", False)]:
        raiz.removeHandler(antigo)
    handler = logging.StreamHandler(sys.stderr)
    handler._do_tickerlab = True  # type: ignore[attr-defined]
    handler.setFormatter(
        FormatadorJson() if em_json else logging.Formatter(FORMATO_DE_TEXTO)
    )
    raiz.addHandler(handler)
    raiz.setLevel(_nivel(ambiente.get(VARIAVEL_DO_NIVEL)))
    acesso = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, SemQueryString) for f in acesso.filters):
        acesso.addFilter(SemQueryString())
    if em_json:
        # o uvicorn tem logs próprios; manda tudo pelo mesmo formato
        for nome in LOGGERS_DO_UVICORN:
            logger = logging.getLogger(nome)
            logger.handlers = [handler]
            logger.propagate = False
    return handler
