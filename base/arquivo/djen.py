"""As comunicações processuais do DJEN (Diário de Justiça Eletrônico Nacional, do CNJ) em que cada
companhia aberta é parte (plano de 03/11/2026 dos processos judiciais, PR 1; ADR 0121).

A API pública (`comunicaapi.pje.jus.br`) busca pelo nome da parte. Para cada companhia ativa do cadastro
da CVM, uma consulta pela razão social:

- toda semana, a última semana fechada (segunda a domingo);
- e, aos poucos, os meses fechados desde `HISTORICO_DESDE` ainda não consultados (até
  `MAXIMO_DO_HISTORICO_POR_RODADA` por rodada, do mais novo ao mais antigo).

O que fica de fora antes de guardar:
- **a Justiça do Trabalho inteira**: a Resolução CNJ 121/2010 (art. 4º, § 1º, II, na redação da
  Resolução 143/2011) proíbe a consulta pública dela pelo nome da parte;
- **a lista dos advogados** (`destinatarioadvogados`): guardamos só quantos são.

**O que continua com pessoa física:** a lista das partes (`destinatarios`) e o texto da comunicação, que
costuma trazer o nome dos advogados e das partes (às vezes o CPF). Por isso a fonte está em
`FONTES_COM_PESSOA` e o JSON vai para `restrito/` no acervo, pasta que nenhum pacote nem exportação
leva (`src/acervo.py`). O texto fica para a leitura do teor (PR 2 do plano); a tabela nunca guarda nome
de pessoa física (`base/processos.py`).

**Só as companhias ativas hoje, pela razão social de hoje:** a companhia que saiu da CVM não é
consultada, e a comunicação que escreve o nome antigo de quem mudou de razão social não é achada.

**O segundo passo, pelo número do processo (`djen-processos`, PR 1b):** a busca pelo nome só acha a
comunicação que intima a companhia; a do mesmo processo dirigida só à outra parte (a sentença
publicada para o autor, por exemplo) não vem. Cada processo que a tabela `processos_comunicacoes` já
ligou a uma companhia pelo nome é consultado pelo número (a API ignora o filtro por CNPJ, mas o
`numeroProcesso` funciona), de `HISTORICO_DESDE` até o último mês fechado; depois, só quando a busca
pelo nome mostra comunicação nova depois do fim da última consulta, e só o pedaço que falta. Processo
parado pelo nome não é consultado de novo: a comunicação nova que só intima a outra parte fica de fora
até a companhia ser intimada outra vez.
"""

import json
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import pandas as pd

from base import porta
from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte, Obter
from base.cadastro import cadastro_do_acervo
from src import acervo
from src.banco import coletas
from src.banco.conexao import obter_engine

ID = "djen-partes"
ID_DOS_PROCESSOS = "djen-processos"
API = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
HISTORICO_DESDE = date(2025, 1, 1)
ITENS_POR_PAGINA = 100  # o máximo que a API aceita
# 20 páginas = 2.000 comunicações de uma companhia numa semana ou num mês: mais que isso é nome
# genérico demais (a consulta fica marcada como `cortada`)
MAXIMO_DE_PAGINAS = 20
MAXIMO_DO_HISTORICO_POR_RODADA = 1500
# uma consulta por processo; a Petrobras sozinha tem milhares de processos, então o primeiro passo
# pelo número leva várias rodadas (os que andaram mais recente pelo nome primeiro)
MAXIMO_DE_PROCESSOS_POR_RODADA = 3000
TABELA_DAS_COMUNICACOES = "processos_comunicacoes"
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


def consulta_do_processo(numero: str, inicio: date, fim: date, pagina: int = 1) -> str:
    """O endereço da busca pelo número do processo (só os algarismos) entre `inicio` e `fim`."""
    parametros = {
        "numeroProcesso": _algarismos(numero),
        "dataDisponibilizacaoInicio": inicio.isoformat(),
        "dataDisponibilizacaoFim": fim.isoformat(),
        "itensPorPagina": ITENS_POR_PAGINA,
        "pagina": pagina,
    }
    return f"{API}?{urlencode(parametros)}"


def da_consulta_do_processo(endereco: str) -> tuple[str, date, date]:
    """O número e o período de volta do endereço (o inverso de `consulta_do_processo`)."""
    parametros = parse_qs(urlsplit(endereco).query)
    return (
        parametros["numeroProcesso"][0],
        date.fromisoformat(parametros["dataDisponibilizacaoInicio"][0]),
        date.fromisoformat(parametros["dataDisponibilizacaoFim"][0]),
    )


def _algarismos(numero: str) -> str:
    return "".join(c for c in numero if c.isdigit())


def _na_pagina(endereco: str, pagina: int) -> str:
    """O mesmo endereço em outra página."""
    partes = urlsplit(endereco)
    parametros = {k: v[0] for k, v in parse_qs(partes.query).items()}
    return partes._replace(query=urlencode({**parametros, "pagina": pagina})).geturl()


def _o_que_foi_consultado(endereco: str) -> dict[str, str]:
    """O nome ou o número, e o período, para gravar junto com as comunicações."""
    parametros = parse_qs(urlsplit(endereco).query)
    pedido = {"nome": "nomeParte", "numero": "numeroProcesso"}
    return {
        **{chave: parametros[p][0] for chave, p in pedido.items() if p in parametros},
        "inicio": parametros["dataDisponibilizacaoInicio"][0],
        "fim": parametros["dataDisponibilizacaoFim"][0],
    }


def ultima_semana_fechada(hoje: date) -> Periodo:
    """De segunda a domingo, a semana inteira mais recente antes de `hoje`."""
    domingo = hoje - timedelta(
        days=hoje.isoweekday() % DIAS_DA_SEMANA or DIAS_DA_SEMANA
    )
    return domingo - timedelta(days=DIAS_DA_SEMANA - 1), domingo


def ultimo_mes_fechado(hoje: date) -> date:
    """O último dia do mês antes do de `hoje`."""
    return hoje.replace(day=1) - timedelta(days=1)


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
    """Lê todas as páginas da busca, pelo nome ou pelo número (até `MAXIMO_DE_PAGINAS`), e grava o
    JSON limpo."""
    consultado = _o_que_foi_consultado(endereco)

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        corpo, cabecalhos = _pagina(cliente, endereco)
        total = int(corpo.get("count") or 0)
        itens = list(corpo["items"])
        pagina = 1
        while len(itens) < total and corpo["items"] and pagina < MAXIMO_DE_PAGINAS:
            pagina += 1
            corpo, _ = _pagina(cliente, _na_pagina(endereco, pagina))
            itens.extend(corpo["items"])
        guardados = [sem_advogados(i) for i in itens if not da_justica_do_trabalho(i)]
        conteudo = {
            "consulta": consultado,
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


# --- o segundo passo, pelo número do processo -----------------------------------------------------


def processos_da_base(pasta: Path | None = None) -> dict[str, date] | None:
    """Cada processo da tabela `processos_comunicacoes` (só os algarismos) -> o dia da comunicação mais
    recente achada pelo nome; None se a carga ainda não montou a tabela.

    Só a achada pelo nome conta: a achada pelo número é consequência desta consulta, e contar com ela
    faria o processo ser consultado de novo toda semana."""
    if pasta is None:
        pasta = (acervo.pasta_do_acervo() or acervo.PASTA_PADRAO) / "base"
    if not (pasta / TABELA_DAS_COMUNICACOES / "djen.parquet").exists():
        return None
    with porta.abrir(pasta) as base:
        pelo_nome = base.ler(
            TABELA_DAS_COMUNICACOES,
            filtros={"achada_por": "nome"},
            colunas=["numero_processo", "disponivel_em"],
        )
    ultima = pelo_nome.groupby("numero_processo")["disponivel_em"].max()
    return {_algarismos(str(n)): pd.Timestamp(d).date() for n, d in ultima.items()}


def consultas_dos_processos_guardadas() -> frozenset[str]:
    with obter_engine().connect() as conexao:
        return frozenset(
            g.url for g in coletas.originais_mais_recentes(conexao, ID_DOS_PROCESSOS)
        )


def _ate_onde_foi(guardadas: frozenset[str]) -> dict[str, date]:
    """Cada processo já consultado -> o fim da consulta guardada mais longa."""
    fins: dict[str, date] = {}
    for endereco in guardadas:
        numero, _, fim = da_consulta_do_processo(endereco)
        fins[numero] = max(fim, fins.get(numero, fim))
    return fins


def descobrir_processos(
    ler_processos: Callable[[], dict[str, date] | None] = processos_da_base,
    ler_guardadas: Callable[[], frozenset[str]] = consultas_dos_processos_guardadas,
) -> Descobrir:
    """Cada processo novo, de `HISTORICO_DESDE` até o último mês fechado; cada processo que andou pelo
    nome depois da última consulta, só o pedaço que falta. Os que andaram mais recente vão primeiro,
    até `MAXIMO_DE_PROCESSOS_POR_RODADA`."""

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        ultima_pelo_nome = ler_processos()
        if ultima_pelo_nome is None:
            raise ErroDeDescoberta(
                f"{ID_DOS_PROCESSOS}: a tabela processos_comunicacoes não existe "
                "(a carga dos processos ainda não rodou?)"
            )
        fim = ultimo_mes_fechado(pd.Timestamp(agora).date())
        guardadas = ler_guardadas()
        ate_onde_foi = _ate_onde_foi(guardadas)
        pendentes: list[tuple[date, str]] = []
        for numero, ultima in ultima_pelo_nome.items():
            ja_foi = ate_onde_foi.get(numero)
            if ja_foi is None:
                pendentes.append(
                    (ultima, consulta_do_processo(numero, HISTORICO_DESDE, fim))
                )
            elif ultima > ja_foi and fim > ja_foi:
                inicio = ja_foi + timedelta(days=1)
                pendentes.append((ultima, consulta_do_processo(numero, inicio, fim)))
        pendentes.sort(key=lambda p: p[0], reverse=True)
        enderecos = [e for _, e in pendentes[:MAXIMO_DE_PROCESSOS_POR_RODADA]]
        if not enderecos and guardadas:
            # o arquivista trata a fonte sem alvo como falha; a consulta guardada é pulada sem pedir
            enderecos = [min(guardadas)]
        if not enderecos:
            raise ErroDeDescoberta(
                f"{ID_DOS_PROCESSOS}: nenhum processo ligado a uma companhia na base"
            )
        return [Alvo(e, ".json", obter=obter_consulta(e)) for e in enderecos]

    return _descobrir


def fonte_dos_processos(
    ler_processos: Callable[[], dict[str, date] | None] = processos_da_base,
    ler_guardadas: Callable[[], frozenset[str]] = consultas_dos_processos_guardadas,
) -> Fonte:
    return Fonte(
        ID_DOS_PROCESSOS,
        "semanal",
        descobrir_processos(ler_processos, ler_guardadas),
        "json",
        guardado_vale=_ja_consultada,
        pausa_minima=PAUSA_ENTRE_CONSULTAS_EM_SEGUNDOS,
    )
