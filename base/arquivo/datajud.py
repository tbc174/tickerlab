"""Cada processo das companhias abertas no DataJud, a API Pública do CNJ, **só para uso interno** (plano
de 03/11/2026 dos processos judiciais, PR 3; ADR 0121).

O termo de uso da API Pública (itens 3.3 e 3.8) veda o uso comercial e a consultoria. Por isso a família
"datajud" está em `coletas.FONTES_SO_INTERNAS`: o dado só treina e rotula, nunca sai em tela, relatório,
API nem exportação, e o original vai para `restrito/` no acervo (`src/acervo.py`).

**Só os processos que o DJEN já achou:** cada número da tabela `processos_comunicacoes` ligado a uma
companhia pelo nome (`djen.processos_da_base`). O DataJud não tem o nome das partes, então ele não acha
processo novo; ele completa o que o DJEN achou (classe, assuntos, órgão julgador, data do ajuizamento e
os movimentos). A Justiça do Trabalho fica de fora, como no DJEN (Resolução CNJ 121/2010).

**O tribunal sai do número, nunca do dado:** o índice de cada tribunal (`api_publica_tjsp`) vem do
segmento e do tribunal do número CNJ (`base/numero_cnj.py`), que tem o dígito verificador conferido, por
uma tabela fixa. O host é sempre o do DataJud.

**A chave** é a pública que o CNJ publica na wiki da API, lida do ambiente (`DATAJUD_CHAVE`), nunca do
repositório. Vai só no cabeçalho do pedido: não entra no endereço, no arquivo nem no log.

**Quando consultar de novo:** cada consulta vale para o processo até a comunicação mais recente que o DJEN
achou pelo nome. Quando o DJEN mostra comunicação nova, o processo é consultado outra vez (os movimentos
mudaram); parado, não.
"""

import json
import os
from collections.abc import Callable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from base.arquivo import djen
from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte, Obter
from base.numero_cnj import NumeroInvalido, decodificar
from src.banco import coletas
from src.banco.conexao import obter_engine

ID = "datajud-processos"
VARIAVEL_DA_CHAVE = "DATAJUD_CHAVE"
HOST = "https://api-publica.datajud.cnj.jus.br"
# sem limite escrito na wiki: um pedido por segundo, como um site pequeno (ADR 0082)
PAUSA_ENTRE_CONSULTAS_EM_SEGUNDOS = 1.0
MAXIMO_DE_PROCESSOS_POR_RODADA = 3000

# o `TR` dos segmentos com um tribunal por estado (Resolução CNJ 65/2008, anexo)
UF_DO_TRIBUNAL = {
    "01": "ac", "02": "al", "03": "ap", "04": "am", "05": "ba", "06": "ce", "07": "df",
    "08": "es", "09": "go", "10": "ma", "11": "mt", "12": "ms", "13": "mg", "14": "pa",
    "15": "pb", "16": "pr", "17": "pe", "18": "pi", "19": "rj", "20": "rn", "21": "rs",
    "22": "ro", "23": "rr", "24": "sc", "25": "se", "26": "sp", "27": "to",
}  # fmt: skip
TRIBUNAIS_REGIONAIS_FEDERAIS = 6
TRIBUNAIS_MILITARES_ESTADUAIS = ("mg", "rs", "sp")
SUPERIOR = "00"  # o `TR` dos tribunais superiores


def _apelidos_validos() -> frozenset[str]:
    """Todos os índices que a tabela fixa pode montar (o host nunca muda)."""
    federais = {f"trf{n}" for n in range(1, TRIBUNAIS_REGIONAIS_FEDERAIS + 1)}
    estaduais = {"tjdft" if uf == "df" else f"tj{uf}" for uf in UF_DO_TRIBUNAL.values()}
    eleitorais = {f"tre-{uf}" for uf in UF_DO_TRIBUNAL.values()}
    militares = {f"tjm{uf}" for uf in TRIBUNAIS_MILITARES_ESTADUAIS}
    return frozenset(
        {"stj", "tse", "stm", *federais, *estaduais, *eleitorais, *militares}
    )


APELIDOS_VALIDOS = _apelidos_validos()


def _apelido(segmento: str, tribunal: str) -> str | None:
    """O índice do tribunal no DataJud pelo `J` e o `TR` do número; None se não há (STF, CNJ, Trabalho)."""
    uf = UF_DO_TRIBUNAL.get(tribunal)
    por_segmento: dict[str, str | None] = {
        "3": "stj" if tribunal == SUPERIOR else None,
        "4": f"trf{int(tribunal)}"
        if tribunal.isdigit() and 1 <= int(tribunal) <= TRIBUNAIS_REGIONAIS_FEDERAIS
        else None,
        "6": "tse" if tribunal == SUPERIOR else (f"tre-{uf}" if uf else None),
        "7": "stm",
        "8": ("tjdft" if uf == "df" else f"tj{uf}") if uf else None,
        "9": f"tjm{uf}" if uf in TRIBUNAIS_MILITARES_ESTADUAIS else None,
    }
    apelido = por_segmento.get(segmento)
    return apelido if apelido in APELIDOS_VALIDOS else None


def _endereco(apelido: str) -> str:
    return f"{HOST}/api_publica_{apelido}/_search"


def _tribunal(numero: str) -> str | None:
    try:
        cnj = decodificar(numero)
    except NumeroInvalido:
        return None
    return _apelido(cnj.segmento, cnj.tribunal)


def endereco_do_tribunal(numero: str) -> str | None:
    """O endereço da busca no índice do tribunal do processo; None se o DataJud não tem o tribunal ou se
    o número não confere."""
    apelido = _tribunal(numero)
    return _endereco(apelido) if apelido else None


def _chave_do_alvo(endereco: str, numero: str, ate: date) -> str:
    """O endereço com o processo e a data no fragmento: um alvo por processo e por comunicação mais recente
    do DJEN. O fragmento não vai no pedido (o corpo do POST leva o número)."""
    return f"{endereco}#{urlencode({'processo': numero, 'ate': ate.isoformat()})}"


def da_chave(url: str) -> tuple[str, date]:
    """O número e a data de volta do endereço do alvo (o inverso de `_chave_do_alvo`)."""
    parametros = parse_qs(urlsplit(url).fragment)
    return parametros["processo"][0], date.fromisoformat(parametros["ate"][0])


def _chave_de_acesso() -> str:
    chave = os.environ.get(VARIAVEL_DA_CHAVE, "").strip()
    if not chave:
        raise ErroDeDescoberta(
            f"{ID}: a variável {VARIAVEL_DA_CHAVE} não está definida (a chave pública da API do "
            "DataJud vai no .env do servidor)"
        )
    return chave


def obter_processo(numero: str, apelido: str) -> Obter:
    """POST da busca pelo número no índice do tribunal; grava os processos achados (um por grau)."""
    endereco = _endereco(apelido)
    corpo = json.dumps({"query": {"match": {"numeroProcesso": numero}}}).encode()

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        resposta = cliente.ler(
            endereco,
            metodo="POST",
            cabecalhos={
                "Authorization": f"APIKey {_chave_de_acesso()}",
                "Content-Type": "application/json",
            },
            corpo=corpo,
        )
        achados = _processos_da_resposta(json.loads(resposta.conteudo))
        conteudo = {
            "consulta": {"numero": numero, "tribunal": apelido},
            "total_na_fonte": len(achados),
            "processos": achados,
        }
        destino.write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")
        return resposta.cabecalhos

    return obter


def _processos_da_resposta(corpo: Mapping[str, Any]) -> list[dict[str, Any]]:
    hits = corpo.get("hits")
    if not isinstance(hits, Mapping) or not isinstance(hits.get("hits"), list):
        raise ValueError(  # noqa: TRY004 (resposta inesperada da fonte, não erro de quem chama)
            f"a API do DataJud respondeu sem `hits`: {sorted(corpo)!r}"
        )
    return [dict(h.get("_source") or {}) for h in hits["hits"]]


def alvo(numero: str, ate: date) -> Alvo:
    """O alvo da consulta de um processo, válido até a comunicação do DJEN de `ate`."""
    apelido = _tribunal(numero)
    if apelido is None:
        raise ValueError(f"o processo {numero} não tem tribunal no DataJud")
    return Alvo(
        _chave_do_alvo(_endereco(apelido), numero, ate),
        ".json",
        obter=obter_processo(numero, apelido),
    )


def consultas_guardadas() -> frozenset[str]:
    with obter_engine().connect() as conexao:
        return frozenset(g.url for g in coletas.originais_mais_recentes(conexao, ID))


def descobrir(
    ler_processos: Callable[[], dict[str, date] | None] = djen.processos_da_base,
    ler_guardadas: Callable[[], frozenset[str]] = consultas_guardadas,
) -> Descobrir:
    """Cada processo do DJEN ainda não consultado até a comunicação mais recente dele, os que andaram mais
    recente primeiro, até `MAXIMO_DE_PROCESSOS_POR_RODADA`."""

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        _chave_de_acesso()  # sem a chave, nenhum pedido daria certo: falha já, com o nome da variável
        ultima_pelo_nome = ler_processos()
        if ultima_pelo_nome is None:
            raise ErroDeDescoberta(
                f"{ID}: a tabela processos_comunicacoes não existe "
                "(a carga dos processos ainda não rodou?)"
            )
        guardadas = ler_guardadas()
        pendentes = sorted(
            (
                (ultima, numero)
                for numero, ultima in ultima_pelo_nome.items()
                if _tribunal(numero) is not None
            ),
            reverse=True,
        )
        alvos = [alvo(numero, ultima) for ultima, numero in pendentes]
        novos = [a for a in alvos if a.url not in guardadas]
        if not novos and guardadas:
            # o arquivista trata a fonte sem alvo como falha; a consulta guardada é pulada sem pedir
            return [_alvo_guardado(min(guardadas))]
        if not novos:
            raise ErroDeDescoberta(
                f"{ID}: nenhum processo do DJEN com tribunal no DataJud"
            )
        return novos[:MAXIMO_DE_PROCESSOS_POR_RODADA]

    return _descobrir


def _alvo_guardado(url: str) -> Alvo:
    numero, ate = da_chave(url)
    return alvo(numero, ate)


def _ja_consultada(anterior: object) -> bool:
    """A consulta "ok" vale até o DJEN mostrar comunicação nova (aí o alvo é outro)."""
    return True


def fonte(
    ler_processos: Callable[[], dict[str, date] | None] = djen.processos_da_base,
    ler_guardadas: Callable[[], frozenset[str]] = consultas_guardadas,
) -> Fonte:
    return Fonte(
        ID,
        "semanal",
        descobrir(ler_processos, ler_guardadas),
        "json",
        guardado_vale=_ja_consultada,
        pausa_minima=PAUSA_ENTRE_CONSULTAS_EM_SEGUNDOS,
    )
