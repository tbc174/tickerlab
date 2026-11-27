"""Confere a saúde pública e o frescor da base, sem credenciais.

Roda: CI (GitHub Actions, vigia-externo.yml), a cada 30 minutos ou manual.
"""

import json
import math
import os
from datetime import UTC, datetime
from http.client import HTTPException, HTTPSConnection

ROTAS = (
    ("app", "app.tickerlab.com.br", "/classico/_stcore/health"),
    ("API", "api.tickerlab.com.br", "/saude"),
    ("conector", "mcp.tickerlab.com.br", "/saude"),
    ("base", "api.tickerlab.com.br", "/saude/frescor"),
)
TEMPO_LIMITE_S = 20
MAXIMO_DO_CORPO = 8192
FRESCOR_PADRAO_HORAS = "72"


def consultar(host: str, caminho: str, *, ler_corpo: bool) -> tuple[int, bytes]:
    """Faz um GET HTTPS limitado, sem credencial e sem seguir redirecionamento."""
    conexao = HTTPSConnection(host, timeout=TEMPO_LIMITE_S)
    try:
        conexao.request("GET", caminho, headers={"Cache-Control": "no-cache"})
        resposta = conexao.getresponse()
        corpo = resposta.read(MAXIMO_DO_CORPO + 1) if ler_corpo else b""
        return resposta.status, corpo
    finally:
        conexao.close()


def frescor_em_dia(corpo: bytes, maximo_horas: float) -> bool:
    """Exige data ISO com fuso, não futura e dentro do prazo; corpo inválido falha."""
    if len(corpo) > MAXIMO_DO_CORPO:
        return False
    try:
        dados = json.loads(corpo)
        if not isinstance(dados, dict) or not isinstance(
            dados.get("base_atualizada_em"), str
        ):
            return False
        data = datetime.fromisoformat(dados["base_atualizada_em"])
        if data.tzinfo is None:
            return False
        idade_horas = (datetime.now(UTC) - data).total_seconds() / 3600
    except (ValueError, UnicodeError):
        return False
    return 0 <= idade_horas <= maximo_horas


def main() -> int:
    """Devolve 1 se alguma checagem falhar; 0 se todas passarem."""
    if os.environ.get("FORCAR_FALHA") == "true":
        print("::error::Falha forçada para conferir a notificação do GitHub.")
        return 1
    try:
        maximo = float(os.environ.get("FRESCOR_MAX_HORAS", FRESCOR_PADRAO_HORAS))
        if not math.isfinite(maximo) or maximo <= 0:
            raise ValueError
    except ValueError:
        print("::error::FRESCOR_MAX_HORAS deve ser um número positivo e finito.")
        return 1
    falhou = False
    for nome, host, caminho in ROTAS:
        try:
            codigo, corpo = consultar(host, caminho, ler_corpo=nome == "base")
        except (OSError, HTTPException):
            print(f"::error::{nome}: falha de conexão ou resposta HTTP inválida.")
            falhou = True
            continue
        if codigo != 200:
            print(f"::error::{nome}: HTTP {codigo}; esperado 200.")
            falhou = True
        elif nome == "base" and not frescor_em_dia(corpo, maximo):
            print("::error::base: frescor vencido, futuro ou inválido.")
            falhou = True
        else:
            print(f"{nome}: ok")
    return int(falhou)


if __name__ == "__main__":
    raise SystemExit(main())
