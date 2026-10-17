"""Arquiva as fontes que só mostram o "agora" (servidor de casa; `base/arquivo/`).

    python -m scripts.arquivar_fontes --listar        (o catálogo)
    python -m scripts.arquivar_fontes diaria          (CVM, CGU, termos e catálogos; 2h)
    python -m scripts.arquivar_fontes semanal         (FIAGRO, FIDC, CRI/CRA, IBAMA, lista suja, GLEIF)
    python -m scripts.arquivar_fontes mensal          (CNPJ e PGFN, pesadas)
    python -m scripts.arquivar_fontes cvm-fiagro      (uma fonte só)
    python -m scripts.arquivar_fontes b3-negocios     (negócios do pregão da B3; também às 22h)

Cada arquivo vai para o acervo (`TICKERLAB_ACERVO`), para o registro de coletas e para o manifesto do
dia. Saída: 0 tudo certo; 1 alguma falha (o Kuma avisa); 2 nada falhou, mas um termo de uso ou um
catálogo mudou (aviso para alguém ler). Fonte desconhecida também sai com 2.

Quando algo falha, a última linha da saída padrão é `FALHAS: fonte (motivo); ...`, curta, para o
aviso do Kuma dizer o porquê (quem lê o e-mail nem sempre alcança o log do servidor).
"""

import argparse
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

from base.arquivo.cliente_http import ClienteHttp
from base.arquivo.coleta import (
    ErroDeDescoberta,
    Fonte,
    FreioDeDisco,
    Resultado,
    arquivar,
)
from base.arquivo.fontes import FONTES, GRUPOS, POR_ID
from src import acervo

log = logging.getLogger("arquivar_fontes")
esperar = time.sleep  # só este módulo espera por aqui: os testes trocam este nome, não o `time.sleep` do processo

# alguns portais bloqueiam por alguns minutos e depois liberam (o firewall do BC, 14/10/2026): uma
# nova tentativa depois de esperar, nunca um laço
ESPERA_PARA_TENTAR_DE_NOVO = 300

OK, FALHA, AVISO = 0, 1, 2
# o resumo vai na mensagem do Kuma (no endereço do push e no assunto do e-mail): curto
TAMANHO_MAXIMO_DO_RESUMO = 300


def _motivo(erro: Exception) -> str:
    return f"{type(erro).__name__}: {erro}"


def _uma_rodada(
    fonte: Fonte, cliente: ClienteHttp, temporaria: Path
) -> Resultado | str:
    """Arquiva a fonte; o motivo (texto) quando a fonte inteira falhou (descoberta, rede)."""
    try:
        return arquivar(fonte, cliente, datetime.now(UTC), temporaria)
    except (ErroDeDescoberta, requests.RequestException) as erro:
        log.error("%s: %s", fonte.id, erro)
        return _motivo(erro)


def _arquivar_com_nova_tentativa(
    fonte: Fonte, cliente: ClienteHttp, temporaria: Path
) -> Resultado | str:
    """Uma rodada; se falhou (toda ou em parte), espera e tenta mais uma vez. Freio de disco não
    tenta de novo (vira falha na hora)."""
    try:
        resultado = _uma_rodada(fonte, cliente, temporaria)
        if isinstance(resultado, Resultado) and not resultado.falhas:
            return resultado
        log.warning(
            "%s: falhou; nova tentativa em %d s", fonte.id, ESPERA_PARA_TENTAR_DE_NOVO
        )
        esperar(ESPERA_PARA_TENTAR_DE_NOVO)
        return _uma_rodada(fonte, cliente, temporaria)
    except FreioDeDisco as erro:
        log.error("%s: %s", fonte.id, erro)
        return _motivo(erro)


def resumo_das_falhas(problemas: list[str]) -> str:
    """A linha `FALHAS: ...` que vai para o aviso do Kuma, cortada em `TAMANHO_MAXIMO_DO_RESUMO`."""
    linha = "FALHAS: " + "; ".join(problemas)
    if len(linha) <= TAMANHO_MAXIMO_DO_RESUMO:
        return linha
    return linha[: TAMANHO_MAXIMO_DO_RESUMO - 3] + "..."


def escolher(alvo: str) -> list[Fonte]:
    """As fontes de um grupo ("diaria") ou a fonte pelo id ("cvm-fiagro"); vazio se não existe."""
    if alvo in GRUPOS:
        return [fonte for fonte in FONTES if fonte.grupo == alvo]
    return [POR_ID[alvo]] if alvo in POR_ID else []


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "alvo", nargs="?", help="grupo (diaria, semanal, mensal) ou id da fonte"
    )
    argumentos.add_argument(
        "--listar", action="store_true", help="mostra o catálogo e sai"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if opcoes.listar:
        for fonte in FONTES:
            marcas = ", ".join(
                m for m, s in (("pesada", fonte.pesada), ("vigia", fonte.vigia)) if s
            )
            print(f"{fonte.grupo:8} {fonte.id:28} {fonte.tipo:8} {marcas}")
        return OK
    fontes = escolher(opcoes.alvo or "")
    if not fontes:
        log.error("Fonte ou grupo desconhecido: %r (veja --listar)", opcoes.alvo)
        return AVISO

    pasta = acervo.pasta_do_acervo()
    temporaria = (pasta or Path.cwd()) / ".temporario"
    cliente = ClienteHttp()
    problemas: list[str] = []
    mudou = False
    for fonte in fontes:
        resultado = _arquivar_com_nova_tentativa(fonte, cliente, temporaria)
        if isinstance(resultado, str):
            problemas.append(f"{fonte.id} ({resultado})")
            continue
        log.info(
            "%s: %d novos, %d iguais, %d já guardados sem mudança, %d sem arquivo, %d falhas",
            fonte.id,
            resultado.novos,
            resultado.iguais,
            resultado.pulados,
            resultado.sem_arquivo,
            len(resultado.falhas),
        )
        if resultado.falhas:
            problemas.append(
                f"{fonte.id} ({len(resultado.falhas)} arquivos; 1º: {resultado.falhas[0]})"
            )
        for url in resultado.mudaram:
            log.warning("%s: o texto mudou em %s (ler de novo)", fonte.id, url)
            mudou = True
    if problemas:
        print(resumo_das_falhas(problemas))
        return FALHA
    return AVISO if mudou else OK


if __name__ == "__main__":
    sys.exit(main())
