"""Os press-releases de resultado das companhias abertas (vitrine, ideia 2; plano de 17/10/2026).

    python -m scripts.ler_releases medir [--base PASTA] [--desde 2024]       (sem API)
    python -m scripts.ler_releases baixar  --pasta P [--amostra N] [--maximo N]   (CVM, 60 s entre PDFs)
    python -m scripts.ler_releases conferir --pasta P [--modelo M]            (sem API)
    python -m scripts.ler_releases estimar --pasta P --teto-dolares 5 [--modelo M]
    python -m scripts.ler_releases piloto  --pasta P --teto-dolares 5 --n 20 [--modelo M]
    python -m scripts.ler_releases enviar  --pasta P --teto-dolares 5 [--modelo M]
    python -m scripts.ler_releases buscar  --pasta P [--modelo M]

`medir` conta os press-releases do IPE guardado no acervo por ano de entrega e quantos têm ITR ou
DFP do mesmo período em `demonstracoes_como_era` (lê a base pela `base.porta`). Os outros passos
leem os releases: o modelo só copia número e trecho, o código confere (`base.leitor_release`) e
tudo fica guardado com a linhagem. `estimar`, `piloto` e `enviar` gastam API (Haiku 5.5; `--modelo
claude-sonnet-5-5` para a leitura às cegas): só rodam com o "pode" do Tiago para o valor, e o teto
(`--teto-dolares`, obrigatório) trava o envio antes de gastar.
"""

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import anthropic
import pandas as pd

from base import leitor_release as lr
from base import porta, releases
from base.porta.duckdb import nome_da_view
from base.ratings import FONTE_DO_IPE, ler_ipe_bruto
from scripts.rotular_com_ia import PAUSA_ENTRE_DOWNLOADS, TetoPassado, _baixar_da_cvm
from src import acervo, leitura
from src import rotulos_ia as ri
from src.banco.coletas import originais_mais_recentes
from src.banco.conexao import criar_engine
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.ler_releases")
PRIMEIRO_ANO = 2024
FUSO = ZoneInfo("America/Sao_Paulo")
MAX_CARACTERES_GUARDADOS = 60_000  # um release tem 10 a 30 páginas; cabe inteiro
AMOSTRA_DA_ESTIMATIVA = 50
SEMENTE = 20261017
PESO_DA_ESCRITA_NO_CACHE = 1.25
SONDA_DO_PREFIXO = "."
DOMINIO_DA_CVM = "cvm.gov.br"  # o link vem do índice; só baixa daqui, por https
_FORA_DA_CHAVE = re.compile(r"[^A-Za-z0-9_-]")


def _so_digitos(cnpj: pd.Series) -> pd.Series:
    return cnpj.astype(str).str.replace(r"\D", "", regex=True)


def medir(achados: pd.DataFrame, demonstracoes: pd.DataFrame) -> pd.DataFrame:
    """Por ano de entrega: releases, empresas e quantos têm ITR/DFP do mesmo período (CNPJ e data)."""
    entregues = set(
        zip(
            _so_digitos(demonstracoes["cnpj"]),
            pd.to_datetime(demonstracoes["referencia"]),
            strict=True,
        )
    )
    chaves = zip(_so_digitos(achados["cnpj"]), achados["referencia"], strict=True)
    tem = pd.Series([c in entregues for c in chaves], index=achados.index, dtype=bool)
    por_ano = achados.assign(
        com_itr_dfp=tem, ano=achados["data_entrega"].dt.year
    ).groupby("ano")
    medida = por_ano.agg(
        releases=("protocolo", "size"),
        empresas=("cnpj", "nunique"),
        com_itr_dfp=("com_itr_dfp", "sum"),
    ).reset_index()
    medida["percentual_com_itr_dfp"] = (
        100 * medida["com_itr_dfp"] / medida["releases"]
    ).round(1)
    return medida


def _releases_do_acervo(desde: int) -> pd.DataFrame:
    motor = criar_engine(url_do_banco())
    try:
        with motor.connect() as conexao:
            anuais = [
                o
                for o in originais_mais_recentes(conexao, FONTE_DO_IPE)
                if "ipe_cia_aberta_" in o.url
            ]
    finally:
        motor.dispose()
    partes = []
    for original in anuais:
        conteudo = acervo.ler_original(original.caminho_do_original)
        if conteudo:
            partes.append(releases.releases_de_resultado(ler_ipe_bruto(conteudo)))
    if not partes:
        return pd.DataFrame(columns=list(releases.COLUNAS))
    todos = pd.concat(partes, ignore_index=True).drop_duplicates("protocolo")
    return todos[todos["data_entrega"].dt.year >= desde].reset_index(drop=True)


def _demonstracoes(pasta_da_base: Path) -> pd.DataFrame:
    """Só os pares (CNPJ, período) entregues: a base é lida pela porta, sem trazer as contas."""
    with porta.abrir(pasta_da_base) as p:
        visao = nome_da_view("demonstracoes_como_era")
        return p.con.execute(f'SELECT DISTINCT cnpj, referencia FROM "{visao}"').df()


# --- os arquivos de trabalho -----------------------------------------------------------------


def _chave(protocolo: str) -> str:
    """O id do pedido na Batch API (letras, números, _ e -; até 64)."""
    return _FORA_DA_CHAVE.sub("_", str(protocolo))[:64]


def _textos(pasta: Path) -> Path:
    return pasta / "textos"


def _sufixo(modelo: str) -> str:
    return _FORA_DA_CHAVE.sub("-", modelo)


def _arquivo_das_leituras(pasta: Path, modelo: str) -> Path:
    return pasta / f"leituras-{_sufixo(modelo)}.jsonl"


def _arquivo_do_manifesto(pasta: Path, modelo: str) -> Path:
    return pasta / f"manifesto-{_sufixo(modelo)}.json"


def guardar_texto(
    pasta: Path, protocolo: str, texto: str, sha256: str, link: str = ""
) -> None:
    """Guarda o texto do release (`.sem_texto` se o PDF é só imagem: vai para a revisão) e a
    impressão digital do PDF original."""
    _textos(pasta).mkdir(parents=True, exist_ok=True)
    nome = _chave(protocolo)
    for velho in (".txt", ".sem_texto"):
        (_textos(pasta) / f"{nome}{velho}").unlink(missing_ok=True)
    sufixo = ".txt" if texto else ".sem_texto"
    (_textos(pasta) / f"{nome}{sufixo}").write_text(texto, encoding="utf-8")
    meta = {"sha256_do_documento": sha256, "link": link}
    (_textos(pasta) / f"{nome}.json").write_text(json.dumps(meta), encoding="utf-8")


def texto_guardado(pasta: Path, protocolo: str) -> str | None:
    """O texto guardado; "" se o PDF não tinha texto; None se ainda não foi baixado."""
    nome = _chave(protocolo)
    if (_textos(pasta) / f"{nome}.sem_texto").exists():
        return ""
    arquivo = _textos(pasta) / f"{nome}.txt"
    return arquivo.read_text(encoding="utf-8") if arquivo.exists() else None


def _meta(pasta: Path, protocolo: str) -> dict:
    arquivo = _textos(pasta) / f"{_chave(protocolo)}.json"
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}


def ler_leituras(pasta: Path, modelo: str = lr.MODELO) -> dict[str, dict]:
    """As leituras gravadas, pelo protocolo (a última de cada uma)."""
    arquivo = _arquivo_das_leituras(pasta, modelo)
    if not arquivo.exists():
        return {}
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    return {r["protocolo"]: r for r in map(json.loads, filter(None, linhas))}


def _acrescentar(pasta: Path, registros: list[dict], modelo: str) -> None:
    with _arquivo_das_leituras(pasta, modelo).open("a", encoding="utf-8") as arquivo:
        for registro in registros:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


def _ler_manifesto(pasta: Path, modelo: str) -> dict:
    arquivo = _arquivo_do_manifesto(pasta, modelo)
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}


def _gravar_manifesto(pasta: Path, manifesto: dict, modelo: str) -> None:
    manifesto |= {
        "modelo": modelo,
        "versao_do_guia": lr.VERSAO_DO_GUIA,
        "atualizado_em": datetime.now(FUSO).isoformat(timespec="seconds"),
    }
    _arquivo_do_manifesto(pasta, modelo).write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def escolher(achados: pd.DataFrame, amostra: int | None) -> pd.DataFrame:
    """Todos os releases, ou uma amostra sorteada com semente fixa (a prova e o piloto)."""
    if not amostra or amostra >= len(achados):
        return achados
    protocolos = sorted(achados["protocolo"].astype(str))
    sorteados = set(random.Random(SEMENTE).sample(protocolos, amostra))
    return achados[achados["protocolo"].astype(str).isin(sorteados)]


PROVA_DE = pd.Timestamp("2024-01-01")
PROVA_ATE = pd.Timestamp("2026-03-31")
MAXIMO_POR_EMPRESA_NA_PROVA = 2


def amostra_da_prova(achados: pd.DataFrame, tamanho: int = 200) -> pd.DataFrame:
    """A amostra da prova (plano de 17/10/2026): de 01/2024 a 03/2026, no máximo 2 por empresa, os
    quatro trimestres do ano em partes iguais, sorteio com semente fixa (a mesma lista dá sempre os
    mesmos releases, na ordem que vier)."""
    janela = achados[
        (achados["referencia"] >= PROVA_DE) & (achados["referencia"] <= PROVA_ATE)
    ]
    sorteio = random.Random(SEMENTE)
    protocolos = sorted(janela["protocolo"].astype(str))
    sorteio.shuffle(protocolos)
    ordem = {p: i for i, p in enumerate(protocolos)}
    janela = janela.assign(
        _ordem=janela["protocolo"].astype(str).map(ordem)
    ).sort_values("_ordem")
    janela = janela.groupby("cnpj").head(MAXIMO_POR_EMPRESA_NA_PROVA)
    por_trimestre = [janela[janela["referencia"].dt.quarter == q] for q in (1, 2, 3, 4)]
    cota = tamanho // len(por_trimestre)
    escolhidos = pd.concat([grupo.head(cota) for grupo in por_trimestre])
    faltam = tamanho - len(escolhidos)
    if (
        faltam > 0
    ):  # um trimestre com menos releases que a cota: completa com os que sobraram
        resto = janela[~janela["protocolo"].isin(escolhidos["protocolo"])]
        escolhidos = pd.concat([escolhidos, resto.head(faltam)])
    return (
        escolhidos.drop(columns="_ordem")
        .sort_values("protocolo")
        .reset_index(drop=True)
    )


# --- baixar ----------------------------------------------------------------------------------


def link_da_cvm(link: str) -> bool:
    """O link é https e de um endereço da CVM? (nada que o índice traga leva o servidor a outro lugar)."""
    partes = urlsplit(link)
    host = partes.hostname or ""
    return partes.scheme == "https" and (
        host == DOMINIO_DA_CVM or host.endswith("." + DOMINIO_DA_CVM)
    )


def baixar(
    achados: pd.DataFrame,
    pasta: Path,
    maximo: int,
    obter: Callable[[str], bytes] = _baixar_da_cvm,
    pausa: float = PAUSA_ENTRE_DOWNLOADS,
) -> int:
    """Baixa os PDFs que faltam, os mais novos primeiro; para no primeiro sinal de limite da CVM
    (uma página no lugar do PDF). Devolve quantos baixou."""
    faltam = achados[
        [texto_guardado(pasta, str(p)) is None for p in achados["protocolo"]]
    ].sort_values("data_entrega", ascending=False)
    baixados = 0
    for i, (_, release) in enumerate(faltam.head(maximo).iterrows()):
        if i:
            time.sleep(pausa)
        if not link_da_cvm(release["link"]):
            log.warning("Link fora da CVM ignorado: %s", release["protocolo"])
            continue
        conteudo = obter(release["link"])
        if not leitura.e_pdf(conteudo):
            log.warning(
                "A CVM devolveu uma página no lugar do PDF (limite): para e continua depois."
            )
            break
        try:
            texto = " ".join(leitura.texto_do_pdf(conteudo).split())
        except Exception:  # noqa: BLE001 (PDF malformado: fila de revisão)
            texto = ""
        guardar_texto(
            pasta, str(release["protocolo"]), texto[:MAX_CARACTERES_GUARDADOS],
            lr.sha256_do_documento(conteudo), release["link"],
        )  # fmt: skip
        baixados += 1
    log.info("PDFs baixados: %s; faltam %s", baixados, max(len(faltam) - baixados, 0))
    return baixados


def fila_de_revisao(achados: pd.DataFrame, pasta: Path) -> list[str]:
    """Os releases cujo PDF não tem texto legível: não vão à API, esperam um humano."""
    protocolos = (str(p) for p in achados["protocolo"])
    return [p for p in protocolos if texto_guardado(pasta, p) == ""]


# --- leituras: registro, reuso, estimativa e teto --------------------------------------------


def _prontos(achados: pd.DataFrame, pasta: Path) -> list[tuple[pd.Series, str]]:
    """Os releases com texto legível baixado."""
    prontos = []
    for _, release in achados.iterrows():
        texto = texto_guardado(pasta, str(release["protocolo"]))
        if texto:
            prontos.append((release, texto))
    return prontos


def _registro(
    release: pd.Series, texto: str, pasta: Path, bruta: str, parada: str | None,
    tokens: tuple[int, int], origem: str, modelo: str,
) -> dict:  # fmt: skip
    """O que fica guardado de uma resposta: sempre com a linhagem inteira (documento, modelo, guia,
    data, entrada e resposta bruta), mais as linhas que o código provou no texto e os descartes."""
    protocolo = str(release["protocolo"])
    base = {
        "protocolo": protocolo,
        "link": release["link"],
        "sha256_do_documento": _meta(pasta, protocolo).get("sha256_do_documento", ""),
        "modelo": modelo,
        "versao_do_guia": lr.VERSAO_DO_GUIA,
        "lido_em": datetime.now(FUSO).isoformat(timespec="seconds"),
        "origem": origem,
        "hash_da_entrada": lr.chave_da_entrada(texto, modelo),
        "resposta_bruta": bruta,
        "tokens_entrada": tokens[0],
        "tokens_saida": tokens[1],
    }
    if parada != "end_turn":
        return base | {"erro": f"parada: {parada}"}
    try:
        lida = lr.LeituraDoRelease.model_validate_json(bruta)
    except ValueError:
        return base | {"erro": "resposta fora do formato"}
    conferida = lr.conferir(lida, texto)
    return base | {
        "linhas": [linha.model_dump() for linha in conferida.linhas],
        "ajustes": [ajuste.model_dump() for ajuste in conferida.ajustes],
        "descartes": [asdict(d) for d in conferida.descartes],
    }


def _por_entrada(leituras: dict[str, dict]) -> dict[str, dict]:
    return {r["hash_da_entrada"]: r for r in leituras.values() if "erro" not in r}


def _reusar(achados: pd.DataFrame, pasta: Path, modelo: str) -> int:
    """Quem tem a mesma entrada (texto + guia + modelo) de uma leitura guardada reaproveita a
    resposta, sem chamar a API (0087, regra 4). Devolve quantos reaproveitou."""
    leituras = ler_leituras(pasta, modelo)
    guardadas = _por_entrada(leituras)
    novos = []
    for release, texto in _prontos(achados, pasta):
        protocolo = str(release["protocolo"])
        antiga = guardadas.get(lr.chave_da_entrada(texto, modelo))
        if protocolo in leituras or antiga is None:
            continue
        novos.append(
            _registro(release, texto, pasta, antiga["resposta_bruta"], "end_turn",
                      (0, 0), f"reuso de {antiga['protocolo']}", modelo)
        )  # fmt: skip
    _acrescentar(pasta, novos, modelo)
    return len(novos)


def pendentes(
    achados: pd.DataFrame, pasta: Path, modelo: str = lr.MODELO
) -> list[tuple[pd.Series, str]]:
    """Os releases prontos sem leitura (os com erro entram de novo), sem repetir a mesma entrada."""
    feitos = ler_leituras(pasta, modelo)
    vistos: set[str] = set()
    fila = []
    for release, texto in _prontos(achados, pasta):
        feita = feitos.get(str(release["protocolo"]))
        chave = lr.chave_da_entrada(texto, modelo)
        if (feita and "erro" not in feita) or chave in vistos:
            continue
        vistos.add(chave)
        fila.append((release, texto))
    return fila


def estimar(
    cliente: anthropic.Anthropic,
    fila: list[tuple[pd.Series, str]],
    modelo: str = lr.MODELO,
) -> float:
    """O custo projetado em US$ pela Batch API: tokens de entrada contados numa amostra (a contagem
    não gasta) e a saída estimada. O guia (prefixo fixo) entra pelo preço do cache: escrito uma vez,
    lido nos outros."""
    if not fila:
        return 0.0
    amostra = random.Random(SEMENTE).sample(fila, min(AMOSTRA_DA_ESTIMATIVA, len(fila)))
    contados = []
    for _, texto in amostra:
        p = lr.pedido(texto, modelo)
        contados.append(
            cliente.messages.count_tokens(
                model=p["model"], system=p["system"], messages=p["messages"]
            ).input_tokens
        )
    sonda = lr.pedido(amostra[0][1], modelo)
    prefixo = cliente.messages.count_tokens(
        model=modelo, system=sonda["system"],
        messages=[{"role": "user", "content": SONDA_DO_PREFIXO}],
    ).input_tokens  # fmt: skip
    n, media = len(fila), sum(contados) / len(contados)
    prefixo = min(prefixo, media)
    leitura_do_cache = lr.preco(modelo).leitura_do_cache
    entrada = (media - prefixo) * n + prefixo * (
        PESO_DA_ESCRITA_NO_CACHE + leitura_do_cache * (n - 1)
    )
    return lr.custo_em_dolares(
        entrada, lr.SAIDA_ESTIMADA_POR_RELEASE * n, lote=True, modelo=modelo
    )


def conferir_teto(manifesto: dict, estimativa: float, teto: float) -> None:
    gasto = manifesto.get("gasto_em_dolares", 0.0)
    if gasto + estimativa > teto:
        raise TetoPassado(
            f"Gasto já feito US$ {gasto:.2f} + estimativa US$ {estimativa:.2f} passa do teto US$ {teto:.2f}."
        )


def _custo_da_resposta(usage: anthropic.types.Usage, lote: bool, modelo: str) -> float:
    leitura_do_cache = lr.preco(modelo).leitura_do_cache
    entrada = (
        (usage.input_tokens or 0)
        + PESO_DA_ESCRITA_NO_CACHE * (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        + leitura_do_cache * (getattr(usage, "cache_read_input_tokens", 0) or 0)
    )  # fmt: skip
    return lr.custo_em_dolares(
        entrada, usage.output_tokens or 0, lote=lote, modelo=modelo
    )


def _da_mensagem(
    mensagem: anthropic.types.Message,
) -> tuple[str, str | None, tuple[int, int]]:
    bruta = next((b.text for b in mensagem.content if b.type == "text"), "")
    tokens = (mensagem.usage.input_tokens, mensagem.usage.output_tokens)
    return bruta, mensagem.stop_reason, tokens


# --- piloto, enviar e buscar -----------------------------------------------------------------


def piloto(
    cliente: anthropic.Anthropic, achados: pd.DataFrame, pasta: Path, n: int, teto: float,
    modelo: str = lr.MODELO,
) -> int:  # fmt: skip
    """Lê `n` releases na hora (preço normal) para conferir formato, erros e custo real."""
    _reusar(achados, pasta, modelo)
    escolhidos = pendentes(achados, pasta, modelo)[:n]
    manifesto = _ler_manifesto(pasta, modelo)
    conferir_teto(
        manifesto, estimar(cliente, escolhidos, modelo) / ri.DESCONTO_DO_LOTE, teto
    )
    registros, gasto = [], 0.0
    for release, texto in escolhidos:
        mensagem = cliente.messages.create(**lr.pedido(texto, modelo))
        bruta, parada, tokens = _da_mensagem(mensagem)
        registros.append(
            _registro(release, texto, pasta, bruta, parada, tokens, "piloto", modelo)
        )
        gasto += _custo_da_resposta(mensagem.usage, lote=False, modelo=modelo)
    _acrescentar(pasta, registros, modelo)
    manifesto["gasto_em_dolares"] = manifesto.get("gasto_em_dolares", 0.0) + gasto
    manifesto["pilotos"] = [
        *manifesto.get("pilotos", []),
        {"releases": len(registros), "gasto": gasto},
    ]
    _gravar_manifesto(pasta, manifesto, modelo)
    _reusar(achados, pasta, modelo)
    log.info("Piloto: %s releases, US$ %.4f", len(registros), gasto)
    return len(registros)


def enviar(
    cliente: anthropic.Anthropic,
    achados: pd.DataFrame,
    pasta: Path,
    teto: float,
    modelo: str = lr.MODELO,
) -> str | None:
    """Manda os pendentes num lote da Batch API, se o teto permitir. Devolve o id do lote."""
    manifesto = _ler_manifesto(pasta, modelo)
    if any(lote.get("estado") != "gravado" for lote in manifesto.get("lotes", [])):
        raise RuntimeError(
            "Há um lote enviado e ainda não gravado: rode `buscar` primeiro."
        )
    _reusar(achados, pasta, modelo)
    fila = pendentes(achados, pasta, modelo)
    if not fila:
        log.info("Nada pendente.")
        return None
    estimativa = estimar(cliente, fila, modelo)
    conferir_teto(manifesto, estimativa, teto)
    lote = cliente.messages.batches.create(
        requests=[
            {
                "custom_id": _chave(str(r["protocolo"])),
                "params": lr.pedido(texto, modelo),
            }
            for r, texto in fila
        ]
    )
    manifesto["lotes"] = [
        *manifesto.get("lotes", []),
        {"id": lote.id, "releases": len(fila), "estimativa": estimativa, "estado": "enviado",
         "enviado_em": datetime.now(FUSO).isoformat(timespec="seconds")},
    ]  # fmt: skip
    _gravar_manifesto(pasta, manifesto, modelo)
    log.info(
        "Lote %s enviado: %s releases, estimativa US$ %.2f",
        lote.id,
        len(fila),
        estimativa,
    )
    return lote.id


def buscar(
    cliente: anthropic.Anthropic,
    achados: pd.DataFrame,
    pasta: Path,
    modelo: str = lr.MODELO,
) -> int:
    """Grava os resultados dos lotes que terminaram. Devolve quantos registros gravou."""
    manifesto = _ler_manifesto(pasta, modelo)
    por_chave = {
        _chave(str(r["protocolo"])): (r, texto) for r, texto in _prontos(achados, pasta)
    }
    gravados = 0
    for lote in manifesto.get("lotes", []):
        if lote.get("estado") == "gravado":
            continue
        if cliente.messages.batches.retrieve(lote["id"]).processing_status != "ended":
            log.info("Lote %s ainda processando.", lote["id"])
            continue
        registros, gasto = [], 0.0
        for resultado in cliente.messages.batches.results(lote["id"]):
            release, texto = por_chave[resultado.custom_id]
            origem = f"lote {lote['id']}"
            if resultado.result.type == "succeeded":
                mensagem = resultado.result.message
                bruta, parada, tokens = _da_mensagem(mensagem)
                registros.append(
                    _registro(
                        release, texto, pasta, bruta, parada, tokens, origem, modelo
                    )
                )
                gasto += _custo_da_resposta(mensagem.usage, lote=True, modelo=modelo)
            else:
                registros.append({"protocolo": str(release["protocolo"]), "origem": origem,
                                  "erro": f"lote: {resultado.result.type}", "modelo": modelo})  # fmt: skip
        _acrescentar(pasta, registros, modelo)
        lote |= {"estado": "gravado", "gasto": gasto}
        manifesto["gasto_em_dolares"] = manifesto.get("gasto_em_dolares", 0.0) + gasto
        gravados += len(registros)
    _gravar_manifesto(pasta, manifesto, modelo)
    _reusar(achados, pasta, modelo)
    return gravados


def conferir_gravadas(
    achados: pd.DataFrame, pasta: Path, modelo: str = lr.MODELO
) -> dict:
    """Refaz a conferência do trecho sobre as respostas brutas guardadas (sem API): se a regra mudar,
    os números mudam sem pagar de novo."""
    leituras = ler_leituras(pasta, modelo)
    contagem = {
        "lidas": 0,
        "com_erro": 0,
        "linhas": 0,
        "ajustes": 0,
        "descartes": 0,
        "sem_linha": 0,
    }
    for release, texto in _prontos(achados, pasta):
        antiga = leituras.get(str(release["protocolo"]))
        if antiga is None:
            continue
        contagem["lidas"] += 1
        novo = _registro(
            release,
            texto,
            pasta,
            antiga["resposta_bruta"],
            "end_turn",
            (0, 0),
            "conferir",
            modelo,
        )
        if "erro" in novo:
            contagem["com_erro"] += 1
            continue
        contagem["linhas"] += len(novo["linhas"])
        contagem["ajustes"] += len(novo["ajustes"])
        contagem["descartes"] += len(novo["descartes"])
        contagem["sem_linha"] += not novo["linhas"]
    return contagem


def _argumentos() -> argparse.ArgumentParser:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    sub = argumentos.add_subparsers(dest="passo", required=True)
    medir_ = sub.add_parser(
        "medir", help="conta os releases e os que têm ITR/DFP (sem API)"
    )
    medir_.add_argument("--base", type=Path, default=None)
    medir_.add_argument("--desde", type=int, default=PRIMEIRO_ANO)
    for nome, ajuda in (
        ("baixar", "baixa os PDFs da CVM (60 s entre um e outro)"),
        ("conferir", "refaz a conferência do trecho nas respostas guardadas (sem API)"),
        ("estimar", "custo projetado em US$ (a contagem de tokens não gasta)"),
        ("piloto", "lê N releases na hora, a preço normal (GASTA API)"),
        ("enviar", "manda o lote da Batch API (GASTA API)"),
        ("buscar", "grava os lotes que terminaram"),
    ):
        passo = sub.add_parser(nome, help=ajuda)
        passo.add_argument("--pasta", type=Path, required=True)
        passo.add_argument("--desde", type=int, default=PRIMEIRO_ANO)
        passo.add_argument(
            "--amostra", type=int, default=None, help="sorteio com semente fixa"
        )
        passo.add_argument(
            "--prova",
            action="store_true",
            help="a amostra da prova do plano (200 releases, 01/2024 a 03/2026)",
        )
        passo.add_argument("--modelo", default=lr.MODELO)
        if nome == "baixar":
            passo.add_argument("--maximo", type=int, default=200)
        if nome in ("estimar", "piloto", "enviar"):
            passo.add_argument("--teto-dolares", type=float, required=True)
        if nome == "piloto":
            passo.add_argument("--n", type=int, default=20)
    return argumentos


def _passo_com_releases(opcoes: argparse.Namespace) -> int:
    todos = _releases_do_acervo(opcoes.desde)
    achados = (
        amostra_da_prova(todos) if opcoes.prova else escolher(todos, opcoes.amostra)
    )
    pasta, modelo = opcoes.pasta, opcoes.modelo
    pasta.mkdir(parents=True, exist_ok=True)
    if opcoes.passo == "baixar":
        baixar(achados, pasta, opcoes.maximo)
    elif opcoes.passo == "conferir":
        print(json.dumps(conferir_gravadas(achados, pasta, modelo), indent=2))
    else:
        cliente = cliente_da_vitrine()
        if opcoes.passo == "estimar":
            fila = pendentes(achados, pasta, modelo)
            custo = estimar(cliente, fila, modelo)
            print(
                f"{len(fila)} releases, estimativa US$ {custo:.2f} (teto US$ {opcoes.teto_dolares:.2f})"
            )
            conferir_teto(_ler_manifesto(pasta, modelo), custo, opcoes.teto_dolares)
        elif opcoes.passo == "piloto":
            piloto(cliente, achados, pasta, opcoes.n, opcoes.teto_dolares, modelo)
        elif opcoes.passo == "enviar":
            enviar(cliente, achados, pasta, opcoes.teto_dolares, modelo)
        else:
            buscar(cliente, achados, pasta, modelo)
    return 0


VARIAVEL_DA_CHAVE = "ANTHROPIC_API_KEY_VITRINE"


def cliente_da_vitrine() -> anthropic.Anthropic:
    """O cliente da API com a chave só da vitrine (uma chave por uso, ADR 0087, regra 2).

    Não cai na `ANTHROPIC_API_KEY`: ela é a da rotulagem, e misturar as duas esconde de que uso veio o
    gasto. Sem a variável própria, o script para antes de qualquer chamada.
    """
    chave = os.environ.get(VARIAVEL_DA_CHAVE, "").strip()
    if not chave:
        raise SystemExit(
            f"Falta {VARIAVEL_DA_CHAVE} no ambiente (a chave da vitrine, separada da dos rótulos): "
            "rode projeto-acoes/configurar-chave-anthropic-vitrine-casa.ps1."
        )
    return anthropic.Anthropic(api_key=chave)


def main(argv: list[str] | None = None) -> int:
    opcoes = _argumentos().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if opcoes.passo != "medir":
        return _passo_com_releases(opcoes)
    base = (
        opcoes.base
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    print(
        medir(_releases_do_acervo(opcoes.desde), _demonstracoes(base)).to_string(
            index=False
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
