"""As comunicações processuais do DJEN (Diário de Justiça Eletrônico Nacional, do CNJ) em que cada
companhia aberta é parte (plano de 03/11/2026 dos processos judiciais, PR 1; ADR 0121).

A API pública (`comunicaapi.pje.jus.br`) busca pelo nome da parte. Para cada companhia ativa do cadastro
da CVM, uma consulta pela razão social:

- toda semana, a última semana fechada (segunda a domingo);
- e, aos poucos, os meses fechados desde `HISTORICO_DESDE` ainda não consultados (até
  `MAXIMO_DO_HISTORICO_POR_RODADA` por rodada, do mais novo ao mais antigo).

O que fica de fora antes de guardar (o acervo guarda o JSON já limpo, em `restrito/`):
- **a Justiça do Trabalho inteira**: a Resolução CNJ 121/2010 (art. 4º, § 1º, II, na redação da
  Resolução 143/2011) proíbe a consulta pública dela pelo nome da parte;
- **o nome dos advogados**: guardamos só quantos são.

O texto da comunicação fica no acervo para a leitura do teor (PR 2 do plano); a tabela nunca guarda
nome de pessoa física (`base/processos.py`).
"""

import json
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import pandas as pd

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte, Obter
from base.cadastro import cadastro_do_acervo
from src.banco import coletas
from src.banco.conexao import obter_engine

ID = "djen-partes"
API = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
HISTORICO_DESDE = date(2025, 1, 1)
ITENS_POR_PAGINA = 100  # o máximo que a API aceita
# 20 páginas = 2.000 comunicações de uma companhia numa semana ou num mês: mais que isso é nome
# genérico demais (a consulta fica marcada como `cortada`)
MAXIMO_DE_PAGINAS = 20
MAXIMO_DO_HISTORICO_POR_RODADA = 1500
PAUSA_ENTRE_CONSULTAS_EM_SEGUNDOS = 2.0
DIAS_DA_SEMANA = 7
SEGMENTO_DO_TRABALHO = "5"  # o `J` do número CNJ (`base/numero_cnj.py`)
SIGLAS_DO_TRABALHO = ("TRT", "TST")

Periodo = tuple[date, date]


def consulta(nome: str, inicio: date, fim: date, pagina: int = 1) -> str:
    """O endereço da busca pelo nome da parte entre `inicio` e `fim` (inclusive)."""
    parametros = {
        "nomeParte": nome,
        "dataDisponibilizacaoInicio": inicio.isoformat(),
        "dataDisponibilizacaoFim": fim.isoformat(),
        "itensPorPagina": ITENS_POR_PAGINA,
        "pagina": pagina,
    }
    return f"{API}?{urlencode(parametros)}"


def da_consulta(endereco: str) -> tuple[str, date, date]:
    """O nome e o período de volta do endereço (o inverso de `consulta`)."""
    parametros = parse_qs(urlsplit(endereco).query)
    return (
        parametros["nomeParte"][0],
        date.fromisoformat(parametros["dataDisponibilizacaoInicio"][0]),
        date.fromisoformat(parametros["dataDisponibilizacaoFim"][0]),
    )


def ultima_semana_fechada(hoje: date) -> Periodo:
    """De segunda a domingo, a semana inteira mais recente antes de `hoje`."""
    domingo = hoje - timedelta(
        days=hoje.isoweekday() % DIAS_DA_SEMANA or DIAS_DA_SEMANA
    )
    return domingo - timedelta(days=DIAS_DA_SEMANA - 1), domingo


def meses_fechados(hoje: date, desde: date = HISTORICO_DESDE) -> list[Periodo]:
    """Cada mês inteiro de `desde` até o mês antes de `hoje`, do mais novo ao mais antigo."""
    meses: list[Periodo] = []
    inicio = date(desde.year, desde.month, 1)
    while True:
        proximo = (inicio + timedelta(days=32)).replace(day=1)
        if proximo > hoje.replace(day=1):
            break
        meses.append((inicio, proximo - timedelta(days=1)))
        inicio = proximo
    return meses[::-1]


def empresas_ativas() -> list[str]:
    """A razão social de cada companhia com registro ativo no cadastro da CVM guardado no acervo."""
    with obter_engine().connect() as conexao:
        achado = cadastro_do_acervo(conexao)
    if achado is None:
        return []
    cadastro, _ = achado
    ativas = cadastro[cadastro["cancelamento"].isna()]
    return sorted(set(ativas["empresa"].dropna().str.strip()) - {""})


def consultas_guardadas() -> frozenset[str]:
    with obter_engine().connect() as conexao:
        return frozenset(g.url for g in coletas.originais_mais_recentes(conexao, ID))


def da_justica_do_trabalho(item: Mapping[str, Any]) -> bool:
    """A comunicação é de um TRT ou do TST (pela sigla ou pelo segmento do número)?"""
    sigla = str(item.get("siglaTribunal") or "").upper()
    numero = "".join(c for c in str(item.get("numero_processo") or "") if c.isdigit())
    return sigla.startswith(SIGLAS_DO_TRABALHO) or (
        len(numero) == 20 and numero[13] == SEGMENTO_DO_TRABALHO
    )


def sem_advogados(item: Mapping[str, Any]) -> dict[str, Any]:
    """A comunicação sem a lista dos advogados, só com quantos são."""
    limpo = {k: v for k, v in item.items() if k != "destinatarioadvogados"}
    limpo["quantidade_de_advogados"] = len(item.get("destinatarioadvogados") or [])
    return limpo


def _pagina(
    cliente: Cliente, endereco: str
) -> tuple[dict[str, Any], Mapping[str, str]]:
    resposta = cliente.ler(endereco)
    corpo = json.loads(resposta.conteudo)
    if str(corpo.get("status", "")).lower() != "success" or "items" not in corpo:
        raise ValueError(
            f"a API do DJEN respondeu {corpo.get('status')!r}: {corpo.get('message')!r}"
        )
    return corpo, resposta.cabecalhos


def obter_consulta(endereco: str) -> Obter:
    """Lê todas as páginas da busca (até `MAXIMO_DE_PAGINAS`) e grava o JSON limpo."""
    nome, inicio, fim = da_consulta(endereco)

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        corpo, cabecalhos = _pagina(cliente, endereco)
        total = int(corpo.get("count") or 0)
        itens = list(corpo["items"])
        pagina = 1
        while len(itens) < total and corpo["items"] and pagina < MAXIMO_DE_PAGINAS:
            pagina += 1
            corpo, _ = _pagina(cliente, consulta(nome, inicio, fim, pagina))
            itens.extend(corpo["items"])
        guardados = [sem_advogados(i) for i in itens if not da_justica_do_trabalho(i)]
        conteudo = {
            "consulta": {
                "nome": nome,
                "inicio": inicio.isoformat(),
                "fim": fim.isoformat(),
            },
            "total_na_fonte": total,
            "lidas": len(itens),
            "fora_por_ser_do_trabalho": len(itens) - len(guardados),
            "cortada": len(itens) < total,
            "items": guardados,
        }
        destino.write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")
        return cabecalhos

    return obter


def _alvo(nome: str, periodo: Periodo) -> Alvo:
    endereco = consulta(nome, *periodo)
    return Alvo(endereco, ".json", obter=obter_consulta(endereco))


def descobrir(
    ler_empresas: Callable[[], list[str]] = empresas_ativas,
    ler_guardadas: Callable[[], frozenset[str]] = consultas_guardadas,
) -> Descobrir:
    """A última semana de cada companhia e um pedaço do histórico ainda não consultado.

    O histórico já guardado sai aqui, e não no arquivista: assim ele não espera a pausa por consulta
    que nem vai ser feita."""

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        empresas = ler_empresas()
        if not empresas:
            raise ErroDeDescoberta(
                "djen-partes: nenhuma companhia ativa no cadastro da CVM do acervo "
                "(o arquivista ainda não o guardou?)"
            )
        hoje = pd.Timestamp(agora).date()
        semana = ultima_semana_fechada(hoje)
        guardadas = ler_guardadas()
        historico = [
            consulta(nome, *mes) for mes in meses_fechados(hoje) for nome in empresas
        ]
        faltam = [c for c in historico if c not in guardadas]
        da_semana = [_alvo(nome, semana) for nome in empresas]
        do_historico = [
            Alvo(c, ".json", obter=obter_consulta(c))
            for c in faltam[:MAXIMO_DO_HISTORICO_POR_RODADA]
        ]
        return [*da_semana, *do_historico]

    return _descobrir


def _ja_consultada(anterior: object) -> bool:
    """Período fechado não muda: a consulta "ok" vale para sempre (a semana repetida no mesmo
    domingo, numa segunda rodada, não pede de novo)."""
    return True


def fonte(
    ler_empresas: Callable[[], list[str]] = empresas_ativas,
    ler_guardadas: Callable[[], frozenset[str]] = consultas_guardadas,
) -> Fonte:
    return Fonte(
        ID,
        "semanal",
        descobrir(ler_empresas, ler_guardadas),
        "json",
        guardado_vale=_ja_consultada,
        pausa_minima=PAUSA_ENTRE_CONSULTAS_EM_SEGUNDOS,
    )
