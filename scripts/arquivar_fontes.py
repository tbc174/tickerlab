"""Arquiva as fontes que só mostram o "agora" (servidor de casa; `base/arquivo/`).

    python -m scripts.arquivar_fontes --listar        (o catálogo)
    python -m scripts.arquivar_fontes diaria          (CVM, CGU, termos e catálogos; 2h)
    python -m scripts.arquivar_fontes semanal         (FIAGRO, FIDC, CRI/CRA, IBAMA, lista suja, GLEIF)
    python -m scripts.arquivar_fontes mensal          (CNPJ e PGFN, pesadas)
    python -m scripts.arquivar_fontes cvm-fiagro      (uma fonte só)
    python -m scripts.arquivar_fontes b3-negocios     (negócios do pregão da B3; também às 22h)

Cada arquivo vai para o acervo (`TICKERLAB_ACERVO`), para o registro de coletas e para o manifesto do
dia. Saída: 0 tudo certo; 1 alguma falha de dado (o Kuma avisa); 2 nada falhou, mas um termo de uso ou um
catálogo mudou, ou uma página vigiada caiu no desafio anti-robô do site, ou uma página de termos de uso
não responde há 7 dias ou mais (linha `FICHA:` para uma pessoa; antes disso é só a linha `AVISO:` com a
data desde quando não responde, e a coleta do dado não fica vermelha por isso). Fonte desconhecida
também sai com 2.

Quando um dado falha, a última linha da saída padrão é `FALHAS: fonte (motivo); ...`, com a lista completa
(o `rodar-tarefa.sh` corta o que vai ao Kuma; o log guarda tudo). Cada fonte que falha espera para tentar de
novo (5 minutos; 30 segundos nas páginas de termos), dentro de um orçamento de 30 minutos por rodada.

Roda: cron de casa pelo arquivar-fontes.sh (todo dia às 2h00 e 22h00; todo domingo às 3h00 e 4h00) e
por outros scripts do servidor; citado em fontes.py.
"""

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

from base.arquivo.cliente_http import ClienteHttp
from base.arquivo.coleta import (
    ErroDeDescoberta,
    Fonte,
    FreioDeDisco,
    Resultado,
    arquivar,
    ultima_ok_em,
)
from base.arquivo.fontes import FONTES, GRUPOS, POR_ID
from src import acervo

log = logging.getLogger("arquivar_fontes")
esperar = time.sleep  # só este módulo espera por aqui: os testes trocam este nome, não o `time.sleep` do processo

# alguns portais bloqueiam por alguns minutos e depois liberam (o firewall do BC, 14/10/2026): uma
# nova tentativa depois de esperar, nunca um laço
ESPERA_PARA_TENTAR_DE_NOVO = 300

OK, FALHA, AVISO = 0, 1, 2

# página de termos de uso (licença): vigiar a licença é trava nossa, mas a página fora do ar não é falha
# da coleta do dado. Fora há menos de 7 dias é só aviso; a partir daí vira ficha para uma pessoa
# (saída 2). 17/11/2026: três páginas de termos mantiveram vermelha, por semanas, a coleta inteira.
PREFIXO_DOS_TERMOS = "termos-"
DIAS_ATE_VIRAR_FICHA = 7
# a página de termos tenta de novo logo (30 s), não depois de 5 minutos; e a rodada toda gasta no
# máximo 30 minutos esperando (a rodada de 17/11/2026 durou 14 h de esperas por fonte)
ESPERA_DOS_TERMOS = 30
ORCAMENTO_DE_ESPERA = 1800


def agora() -> datetime:
    return datetime.now(UTC)


def _eh_termo(fonte: Fonte) -> bool:
    return fonte.id.startswith(PREFIXO_DOS_TERMOS)


@dataclass
class _Orcamento:
    """Quanto a rodada ainda pode esperar por fontes que falharam."""

    restante: float = ORCAMENTO_DE_ESPERA

    def gastar(self, segundos: float) -> bool:
        """Reserva a espera; False (sem esperar) quando o orçamento da rodada acabou."""
        if segundos > self.restante:
            return False
        self.restante -= segundos
        return True


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
    fonte: Fonte, cliente: ClienteHttp, temporaria: Path, orcamento: _Orcamento
) -> Resultado | str:
    """Uma rodada; se falhou (toda ou em parte), espera e tenta mais uma vez. Freio de disco não
    tenta de novo (vira falha na hora). Sem orçamento de espera na rodada, não tenta de novo."""
    try:
        resultado = _uma_rodada(fonte, cliente, temporaria)
        if isinstance(resultado, Resultado) and not resultado.falhas:
            return resultado
        espera = ESPERA_DOS_TERMOS if _eh_termo(fonte) else ESPERA_PARA_TENTAR_DE_NOVO
        if not orcamento.gastar(espera):
            log.warning(
                "%s: falhou; sem nova tentativa (o orçamento de espera da rodada acabou)",
                fonte.id,
            )
            return resultado
        log.warning("%s: falhou; nova tentativa em %d s", fonte.id, espera)
        esperar(espera)
        return _uma_rodada(fonte, cliente, temporaria)
    except FreioDeDisco as erro:
        log.error("%s: %s", fonte.id, erro)
        return _motivo(erro)


def resumo_das_falhas(problemas: list[str]) -> str:
    """A linha `FALHAS: ...` com a lista completa (o `rodar-tarefa.sh` corta o que vai ao Kuma; o log
    guarda tudo). Só falha de dado: página de termos fora do ar tem a linha própria."""
    return "FALHAS: " + "; ".join(problemas)


def _situacao_do_termo(fonte_id: str, url: str | None) -> tuple[str, bool]:
    """(frase, vira_ficha): desde quando a página de termos não responde. Nunca respondeu, ou 7 dias
    ou mais, vira ficha para uma pessoa."""
    desde = ultima_ok_em(url) if url else None
    if desde is None:
        return f"{fonte_id} nunca respondeu", True
    if desde.tzinfo is None:
        desde = desde.replace(tzinfo=UTC)
    fora_ha = agora() - desde
    frase = f"{fonte_id} sem resposta desde {desde.date().isoformat()}"
    return frase, fora_ha >= timedelta(days=DIAS_ATE_VIRAR_FICHA)


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
    termos_fora: list[tuple[str, str | None]] = []  # (fonte, endereço que falhou)
    orcamento = _Orcamento()
    mudou = False
    for fonte in fontes:
        resultado = _arquivar_com_nova_tentativa(fonte, cliente, temporaria, orcamento)
        if isinstance(resultado, str):
            if _eh_termo(fonte):
                termos_fora.append((fonte.id, None))
            else:
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
        if resultado.falhas and _eh_termo(fonte):
            termos_fora.append((fonte.id, resultado.falhas[0]))
        elif resultado.falhas:
            problemas.append(
                f"{fonte.id} ({len(resultado.falhas)} arquivos; 1º: {resultado.falhas[0]})"
            )
        for url in resultado.bloqueadas:
            log.warning(
                "%s: desafio anti-robô em %s (sem cópia; ver com uma pessoa)",
                fonte.id,
                url,
            )
            mudou = True
        for url in resultado.mudaram:
            log.warning("%s: o texto mudou em %s (ler de novo)", fonte.id, url)
            mudou = True
    ficha = False
    for fonte_id, url in termos_fora:
        frase, vira_ficha = _situacao_do_termo(fonte_id, url)
        print(f"{'FICHA' if vira_ficha else 'AVISO'}: {frase}")
        ficha = ficha or vira_ficha
    if problemas:
        print(
            resumo_das_falhas(problemas)
        )  # por último: é a linha que o rodar-tarefa.sh lê
        return FALHA
    return AVISO if mudou or ficha else OK


if __name__ == "__main__":
    sys.exit(main())
