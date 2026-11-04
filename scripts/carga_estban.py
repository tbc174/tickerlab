"""Carga do ESTBAN do Banco Central para a base: balancete mensal por agência e município (linha 659).

    python -m scripts.carga_estban                                   (grava no acervo: o que falta e as 6 mais novas)
    python -m scripts.carga_estban --competencia 202602 --pasta /tmp/base --forcar

Baixa o ZIP de cada competência (`base/estban.py`, endereço `AAAAMM_ESTBAN_AG.csv.zip`) e grava, com manifesto
e versões (`base/parquet.py::gravar_com_versoes`), `estban_agencias/<AAAAMM>.parquet`: a tabela larga, uma
linha por agência e município, uma coluna por verbete, com `gerado_em` e `disponivel_em`.

O BC regrava as 6 competências mais novas **publicadas** todo mês (não os 6 últimos meses do calendário: o
dado sai com ~7 meses de atraso). Elas são baixadas de novo a cada carga; cada baixada é guardada no acervo
(o original, com o SHA-256) e a data de modificação do arquivo no servidor (`Last-Modified`) entra no
`detalhe` do registro de coletas e no `disponivel_em`. Sem o cabeçalho, vale o dia da coleta (o mais tarde,
nunca o mais cedo). As competências mais antigas só são baixadas se ainda não estiverem gravadas.

**Sem olhar o futuro:** se a competência baixada de novo traz os mesmos números (só mudou a data de geração
do arquivo), nada se regrava e o `disponivel_em` continua o da primeira vez; se os números mudaram, é versão
nova e a data nova vale.

`PRIMEIRA_COMPETENCIA` (200301) é uma suposição: o primeiro endereço que existir vale, e 404 é "não
publicada". Ritmo mensal; o app não depende dela. Licença do BCB a confirmar, só uso interno (ADR 0102,
Emenda 2); nada é perguntado à fonte. Recusa rodar sem a versão do código (exigência 13 da ADR 0055). Saída 0
tudo certo; 1 se alguma competência falhou.
"""

import argparse
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from base import estban
from base.parquet import GRAVADO, IGUAL, gravar_com_versoes, ler_tabela
from src import acervo, rede
from src.banco.coletas import (
    HTTP_NAO_ENCONTRADO,
    _guardar_sem_atrapalhar,
    registrar,
)
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_estban")
TEMPO_LIMITE = 600
PRIMEIRA_COMPETENCIA = 200301
COMPETENCIAS_REGRAVADAS = 6
PAUSA_ENTRE_PEDIDOS = 2.0  # segundos
DESTINO = "estban_agencias"
ORDEM = list(estban.CHAVE)
CARIMBOS = ("gerado_em", "disponivel_em")
NAO_PUBLICADA, PULADA, FALHOU = "nao_publicada", "pulada", "falhou"


@dataclass(frozen=True)
class Baixada:
    """O ZIP de uma competência e o dia em que o servidor o modificou pela última vez."""

    conteudo: bytes
    modificado_em: date


def data_de_modificacao(cabecalho: str | None, hoje: date) -> date:
    """O `Last-Modified` do servidor como data; sem ele (ou ilegível), `hoje`: o mais tarde possível."""
    if not cabecalho:
        return hoje
    try:
        return parsedate_to_datetime(cabecalho).astimezone(UTC).date()
    except (TypeError, ValueError):
        return hoje


def _registrar(
    url: str, conteudo: bytes | None, situacao: str, detalhe: str, agora: datetime
) -> None:
    caminho = None
    if conteudo is not None:
        caminho = _guardar_sem_atrapalhar(estban.FONTE, url, conteudo, agora)
    try:
        with obter_engine().begin() as conexao:
            registrar(
                conexao, estban.FONTE, url, conteudo, situacao, detalhe, agora, caminho
            )
    except Exception:  # o registro é para auditoria; a carga segue sem ele
        log.exception("Falha ao registrar a coleta do ESTBAN %s", url)


def baixar(url: str, hoje: date) -> Baixada | None:
    """O ZIP da competência, guardado no acervo e registrado; `None` se o BC ainda não o publicou (404)."""
    resposta = rede.get_com_agente(url, timeout=TEMPO_LIMITE)
    agora = datetime.now(UTC)
    if resposta.status_code == HTTP_NAO_ENCONTRADO:
        _registrar(url, None, "nao_encontrado", "HTTP 404", agora)
        return None
    resposta.raise_for_status()
    modificado_em = data_de_modificacao(resposta.headers.get("Last-Modified"), hoje)
    detalhe = f"modificado no servidor em {modificado_em.isoformat()}"
    _registrar(url, resposta.content, "ok", detalhe, agora)
    return Baixada(resposta.content, modificado_em)


def competencias_ate(hoje: date, primeira: int = PRIMEIRA_COMPETENCIA) -> list[int]:
    """As competências (AAAAMM) de `primeira` até o mês anterior ao de `hoje`, da mais nova à mais antiga."""
    ultima = hoje.year * 12 + hoje.month - 2  # o mês anterior, em meses desde o ano 0
    inicio = (primeira // 100) * 12 + primeira % 100 - 1
    return [(m // 12) * 100 + m % 12 + 1 for m in range(ultima, inicio - 1, -1)]


def mesma_tabela(anterior: pd.DataFrame, nova: pd.DataFrame) -> bool:
    """Os mesmos números, sem contar as datas de geração e de disponibilidade."""
    sem_datas = [c for c in nova.columns if c not in CARIMBOS]
    return anterior[sem_datas].reset_index(drop=True).equals(
        nova[sem_datas].reset_index(drop=True)
    )  # fmt: skip


def carregar(
    competencia: int, baixada: Baixada, saida: Path, forcar: bool = False
) -> str:
    """Lê o ZIP e grava a competência; `IGUAL` se os números não mudaram desde a última gravação."""
    tabela = estban.ler_competencia(baixada.conteudo, baixada.modificado_em)
    destino = saida / DESTINO / str(competencia)
    arquivo = destino.with_suffix(".parquet")
    if arquivo.exists() and not forcar and mesma_tabela(ler_tabela(arquivo), tabela):
        return IGUAL
    origem = {
        "url": estban.endereco_da_competencia(competencia),
        "sha256": hashlib.sha256(baixada.conteudo).hexdigest(),
    }
    return gravar_com_versoes(lambda: tabela, destino, [origem], ORDEM, forcar=True)


def rodar(
    competencias: list[int] | None,
    saida: Path,
    hoje: date,
    baixar_zip: Callable[[str, date], Baixada | None] = baixar,
    forcar: bool = False,
    pausa: float = PAUSA_ENTRE_PEDIDOS,
) -> dict[int, str]:
    """A rodada: sem `competencias`, as que faltam e as `COMPETENCIAS_REGRAVADAS` mais novas publicadas.

    Devolve o que aconteceu com cada competência (`gravado`, `igual`, `nao_publicada`, `pulada` ou `falhou`)."""
    pedidas = competencias or competencias_ate(hoje)
    resultado: dict[int, str] = {}
    publicadas = 0
    for competencia in pedidas:
        gravada = (saida / DESTINO / f"{competencia}.parquet").exists()
        if gravada and competencias is None and publicadas >= COMPETENCIAS_REGRAVADAS:
            resultado[competencia] = PULADA
            continue
        try:
            baixada = baixar_zip(estban.endereco_da_competencia(competencia), hoje)
            time.sleep(pausa)
            if baixada is None:
                resultado[competencia] = NAO_PUBLICADA
                continue
            publicadas += 1
            resultado[competencia] = carregar(competencia, baixada, saida, forcar)
        except (requests.RequestException, ValueError, OSError) as erro:
            log.error("ESTBAN %s falhou: %s", competencia, erro)
            resultado[competencia] = FALHOU
    return resultado


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--competencia", type=int, action="append", default=None)
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--forcar", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    saida = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    resultado = rodar(opcoes.competencia, saida, hoje, forcar=opcoes.forcar)
    contagem = list(resultado.values())
    log.info(
        "ESTBAN: %d gravadas, %d iguais, %d ainda não publicadas, %d falharam",
        contagem.count(GRAVADO),
        contagem.count(IGUAL),
        contagem.count(NAO_PUBLICADA),
        contagem.count(FALHOU),
    )
    return 1 if FALHOU in contagem else 0


if __name__ == "__main__":
    raise SystemExit(main())
