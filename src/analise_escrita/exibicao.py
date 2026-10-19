"""A análise escrita no relatório da empresa: o que a página, o PDF e a API mostram (ADR 0100).

O lote (`scripts/escrever_analises.py`) deixa `analises/<cnpj>.json` na pasta das análises, que chega
ao app como as fichas do dossiê. Aqui a análise guardada vira `Relatorio.analise`, com cada nota
resolvida na linha da ficha de agora. Três travas, todas para nunca mostrar texto errado:

- só o texto aprovado na porta 3 (`publicavel`) vai ao ar;
- a ficha mudou desde que o texto foi escrito (o hash da entrada não bate): sai o molde, com o
  aviso de que a análise está sendo reescrita, nunca texto com número velho;
- quem não é Pro (D4) não vê a parte que cita o dossiê: ela sai do molde montado sem o dossiê.

Sem arquivo, ilegível ou fora do formato, o relatório fica como estava: sem análise e sem erro.
"""

import dataclasses
import json
import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from src.analise_escrita import entrada as en
from src.analise_escrita import montagem, saida
from src.analise_escrita.modelo_da_tela import (
    AnaliseDaTela,
    FraseDaTela,
    NotaDaTela,
    ParagrafoDaTela,
    ParteDaTela,
)
from src.analise_escrita.molde import molde
from src.configuracao import PASTA_RAIZ
from src.planos import DOSSIE_DA_BASE, pode_usar
from src.relatorio_empresa import (
    Entradas,
    Premissas,
    Relatorio,
    escrever_celula,
    montar,
    rotulo_da_coluna,
)

log = logging.getLogger(__name__)

PASTA_DAS_ANALISES_PADRAO = PASTA_RAIZ / "dados_locais" / "analises"
TAMANHO_MAXIMO = 5_000_000  # bytes: uma análise tem algumas dezenas de KB
PLANO_COMPLETO = (
    "pro"  # a entrada é sempre a da ficha inteira (o grátis fica marcado em `so_pro`)
)
ROTULO_DA_LEITURA = "Leitura"
NOME_DA_LACUNA = "O que a base não tem"
CAMPOS_DO_LOTE = ("publicavel", "analise", "corte", "hash_da_entrada_atual")
AVISO_DA_ANALISE = (
    "Análise escrita por modelo de linguagem a partir de dados públicos, com cada afirmação "
    "conferida por código contra a fonte. Não é recomendação de investimento. Partes dos dados "
    "estão sob a Open Database License (ODbL 1.0): cite a fonte."
)


def pasta_das_analises() -> Path:
    return Path(os.environ.get("TICKERLAB_ANALISES") or PASTA_DAS_ANALISES_PADRAO)


def _ler_guardada(cnpj: str, pasta: Path) -> dict[str, Any] | None:
    """O arquivo do lote do CNPJ, ou None se não há, é grande demais ou está fora do formato."""
    caminho = pasta / f"{re.sub(r'\D', '', cnpj)}.json"
    try:
        if caminho.stat().st_size > TAMANHO_MAXIMO:
            log.warning("análise grande demais: %s", caminho)
            return None
        guardada = json.loads(caminho.read_text(encoding="utf-8"))
    except OSError:
        return None  # a empresa não tem análise (ou a pasta ainda não chegou)
    except ValueError:
        log.warning("análise ilegível: %s", caminho)
        return None
    if not isinstance(guardada, dict) or any(c not in guardada for c in CAMPOS_DO_LOTE):
        log.warning("análise fora do formato do lote: %s", caminho)
        return None
    return guardada


def _entrada_de_hoje(entradas: Entradas, corte: date) -> dict[str, Any] | None:
    """A entrada da ficha de agora, montada como o lote a montou (sem preço, no corte do texto)."""
    sem_preco = dataclasses.replace(
        entradas, preco=None, fechamentos=None, premissas=Premissas()
    )
    com = montar(sem_preco, PLANO_COMPLETO)
    sem = montar(dataclasses.replace(sem_preco, dossie=None), PLANO_COMPLETO)
    try:
        return en.entrada_da_ficha(com, corte, sem_dossie=sem)
    except (en.DataDepoisDoCorteError, en.PessoaNaEntradaError):
        return None


def _nota(numero: int, linha: dict[str, Any], entrada: dict[str, Any]) -> NotaDaTela:
    """A linha da entrada como a pessoa lê: nome, valor escrito, de quando, de onde, comparação."""
    secao = entrada["secoes"].get(linha.get("secao"), "")
    fonte = ""
    match linha["tipo"]:
        case "numero":
            nome = linha["nome"]
            texto = linha.get("texto") or linha.get("motivo", "")
            fonte = linha.get("fonte", "")
        case "linha":
            nome = f"{secao}: {linha['tabela']}"
            texto = "; ".join(
                f"{rotulo_da_coluna(k)} {escrever_celula(v)}"
                for k, v in linha["celulas"].items()
            )
        case "ponto":
            nome, texto, fonte = secao, linha["texto"], linha.get("tabela", "")
        case "lacuna":
            nome, texto = NOME_DA_LACUNA, linha["texto"]
        case _:
            nome, texto = secao, linha["texto"]
    comparacao = linha.get("comparacao")
    return NotaDaTela(
        numero=numero,
        id=linha["id"],
        nome=nome,
        texto=texto,
        medido_em=linha.get("medido_em", ""),
        fonte=fonte,
        comparacao=(
            f"Contra {comparacao['contra']}: {comparacao['texto']}"
            if comparacao
            else ""
        ),
    )


def _paragrafo(
    paragrafo: saida.Paragrafo, linhas: dict[str, Any], numeros: dict[str, int]
) -> ParagrafoDaTela:
    frases = []
    for frase in paragrafo.frases:
        ids = [i for i in dict.fromkeys(frase.notas) if i in linhas]
        for id_ in ids:
            numeros.setdefault(id_, len(numeros) + 1)
        frases.append(FraseDaTela(frase.texto, tuple(numeros[i] for i in ids)))
    rotulo = ROTULO_DA_LEITURA if paragrafo.tipo == saida.LEITURA else ""
    return ParagrafoDaTela(paragrafo.tipo, rotulo, tuple(frases))


def _para_a_tela(
    analise: saida.Analise, entrada: dict[str, Any], motivo: str | None
) -> AnaliseDaTela:
    """Numera as notas na ordem em que aparecem (o mesmo id leva o mesmo número) e as resolve."""
    linhas = {linha["id"]: linha for linha in entrada["linhas"]}
    numeros: dict[str, int] = {}
    partes = tuple(
        ParteDaTela(
            parte.chave,
            saida.TITULOS[parte.chave],
            parte.origem,
            tuple(_paragrafo(p, linhas, numeros) for p in parte.paragrafos),
        )
        for parte in analise.partes
    )
    notas = tuple(_nota(n, linhas[i], entrada) for i, n in numeros.items())
    return AnaliseDaTela(partes, notas, AVISO_DA_ANALISE, motivo)


def _analise_a_mostrar(
    guardada: dict[str, Any], entrada: dict[str, Any], e_pro: bool
) -> tuple[saida.Analise, str | None]:
    """O texto do modelo, o molde (ficha nova) ou o texto sem as partes do dossiê (quem não é Pro)."""
    if guardada["hash_da_entrada_atual"] != en.hash_da_entrada(entrada):
        return molde(entrada, e_pro), montagem.FICHA_NOVA
    analise = saida.ler_analise(guardada["analise"])
    if not e_pro:
        analise = montagem.sem_o_dossie(analise, entrada)
    return analise, None


def com_analise(
    relatorio: Relatorio,
    entradas: Entradas,
    plano: str | None,
    pasta: Path | None = None,
) -> Relatorio:
    """O relatório com a análise escrita, se há texto aprovado; senão, o mesmo relatório.

    `entradas` são as do relatório (para montar a ficha de agora e conferir o hash); `plano`, o de
    quem vê. A página, o PDF e a API chamam esta função e leem `relatorio.analise`.
    """
    guardada = _ler_guardada(relatorio.cnpj, pasta or pasta_das_analises())
    if guardada is None or guardada["publicavel"] is not True:
        return relatorio  # enquanto a porta 3 for total, só texto aprovado vai ao ar
    try:
        entrada = _entrada_de_hoje(entradas, date.fromisoformat(guardada["corte"]))
        if entrada is None:
            return relatorio
        analise, motivo = _analise_a_mostrar(
            guardada, entrada, pode_usar(plano, DOSSIE_DA_BASE)
        )
    except (saida.RespostaInvalidaError, ValueError, KeyError, TypeError):
        log.warning("análise de %s fora do formato", relatorio.cnpj)
        return relatorio
    return dataclasses.replace(
        relatorio, analise=_para_a_tela(analise, entrada, motivo)
    )
