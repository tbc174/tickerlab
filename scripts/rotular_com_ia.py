"""Rotula a fila das 21h pela API do Claude (ADR 0072; plano `rotulagem-por-ia` de 14/10/2026).

    python -m scripts.rotular_com_ia baixar   --eventos eventos.json --pasta ACERVO/rotulos_ia/v1
    python -m scripts.rotular_com_ia estimar  --eventos eventos.json --pasta ... --teto-dolares 60
    python -m scripts.rotular_com_ia piloto   --eventos eventos.json --pasta ... --teto-dolares 60 --n 30
    python -m scripts.rotular_com_ia enviar   --eventos eventos.json --pasta ... --teto-dolares 60
    python -m scripts.rotular_com_ia buscar   --eventos eventos.json --pasta ...

`baixar` guarda o texto de cada documento em `<pasta>/textos/` (um pedido por vez à CVM, com um minuto
de pausa, e para no primeiro sinal de limite, como o leitor; roda de novo no dia seguinte). `estimar`
conta os tokens de uma amostra pela API (não gasta) e projeta o custo da fila. `piloto` rotula poucos
eventos na hora, para conferir formato e erros. `enviar` manda o resto num lote da Batch API (metade do
preço; até 24 h) e `buscar` grava o resultado quando o lote termina.

**O teto vale para tudo:** nenhum passo gasta se o gasto já feito mais a estimativa passar do teto.
Os rótulos vão para `<pasta>/rotulos.jsonl` (um por linha, com `por: "ia"`, a entrada em hash e a
resposta bruta) e o resumo para `<pasta>/manifesto.json`. Nada aqui lê ou grava na página das 21h: os
rótulos do Tiago continuam às cegas. A chave fica em `ANTHROPIC_API_KEY` (nunca no código).
"""

import argparse
import hashlib
import json
import logging
import random
import re
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
import requests

from src import leitura
from src import rotulos_ia as ri

log = logging.getLogger("tickerlab.rotulos_ia")

PAUSA_ENTRE_DOWNLOADS = 60  # segundos: a CVM limita os downloads por endereço
MAX_CARACTERES_GUARDADOS = 20_000  # o texto guardado; o pedido usa só o começo
AMOSTRA_DA_ESTIMATIVA = 50
SEMENTE = 20261014
# cache: escrever custa 1,25x a entrada; ler custa 0,1x
PESO_DA_ESCRITA_NO_CACHE, PESO_DA_LEITURA_DO_CACHE = 1.25, 0.1
_CUSTOM_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
FUSO = ZoneInfo("America/Sao_Paulo")


class TetoPassado(Exception):
    """O gasto já feito mais a estimativa passa do teto: nada é enviado."""


# --- arquivos ---------------------------------------------------------------------------------


def ler_eventos(caminho: Path) -> list[dict]:
    return json.loads(caminho.read_text(encoding="utf-8"))["eventos"]


def _textos(pasta: Path) -> Path:
    return pasta / "textos"


def texto_guardado(pasta: Path, evento_id: str) -> str | None:
    """O texto baixado, "" se o documento não tem texto, None se ainda não foi baixado."""
    arquivo = _textos(pasta) / f"{evento_id}.txt"
    if arquivo.exists():
        return arquivo.read_text(encoding="utf-8")
    if (_textos(pasta) / f"{evento_id}.sem_texto").exists():
        return ""
    return None


def ler_rotulos(pasta: Path) -> dict[str, dict]:
    """Os registros já gravados, pelo id do evento (o último vale)."""
    arquivo = pasta / "rotulos.jsonl"
    if not arquivo.exists():
        return {}
    registros = (
        json.loads(linha)
        for linha in arquivo.read_text(encoding="utf-8").splitlines()
        if linha
    )
    return {r["evento_id"]: r for r in registros}


def _rotulados(pasta: Path) -> set[str]:
    return {i for i, r in ler_rotulos(pasta).items() if "erro" not in r}


def ler_manifesto(pasta: Path) -> dict:
    arquivo = pasta / "manifesto.json"
    if arquivo.exists():
        return json.loads(arquivo.read_text(encoding="utf-8"))
    return {"gasto_em_dolares": 0.0, "lotes": [], "pilotos": []}


def gravar_manifesto(pasta: Path, manifesto: dict, eventos: list[dict]) -> None:
    registros = ler_rotulos(pasta)
    jsonl = pasta / "rotulos.jsonl"
    manifesto |= {
        "modelo": ri.MODELO,
        "versao_do_prompt": ri.VERSAO_DO_PROMPT,
        "guia": ri.GUIA,
        "eventos_na_fila": len(eventos),
        "rotulados": sum("erro" not in r for r in registros.values()),
        "erros": sum("erro" in r for r in registros.values()),
        "sha256_do_jsonl": hashlib.sha256(jsonl.read_bytes()).hexdigest()
        if jsonl.exists()
        else None,
        "atualizado_em": datetime.now(FUSO).isoformat(timespec="seconds"),
    }
    (pasta / "manifesto.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _acrescentar(pasta: Path, registros: list[dict]) -> None:
    with (pasta / "rotulos.jsonl").open("a", encoding="utf-8") as arquivo:
        for registro in registros:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


# --- baixar ---------------------------------------------------------------------------------


def _baixar_da_cvm(url: str) -> bytes:
    resposta = requests.get(
        url, timeout=120, headers={"User-Agent": "TickerLab (tickerlab.com.br)"}
    )
    resposta.raise_for_status()
    return resposta.content


def texto_do_conteudo(conteudo: bytes, evento: dict) -> str:
    """O texto do PDF ("" se for só imagem ou ilegível), sem cabeçalho e assinatura nos fatos."""
    try:
        texto = leitura.texto_do_pdf(conteudo)
    except Exception:  # noqa: BLE001 (PDF malformado: fica sem texto e o modelo julga pelo assunto)
        return ""
    if len(texto.split()) < leitura.MIN_PALAVRAS_POR_FRASE:
        return ""
    if ri.e_fato_relevante(evento):
        texto = leitura.sem_cabecalho_e_assinatura(texto)
    return " ".join(texto.split())[:MAX_CARACTERES_GUARDADOS]


def baixar(
    eventos: list[dict],
    pasta: Path,
    maximo: int,
    obter: Callable[[str], bytes] = _baixar_da_cvm,
    pausa: float = PAUSA_ENTRE_DOWNLOADS,
) -> int:
    """Baixa os textos que faltam; para no primeiro sinal de limite da CVM. Devolve quantos baixou."""
    _textos(pasta).mkdir(parents=True, exist_ok=True)
    faltam = [e for e in eventos if texto_guardado(pasta, e["id"]) is None][:maximo]
    baixados = 0
    for i, evento in enumerate(faltam):
        if i:
            time.sleep(pausa)
        conteudo = obter(evento["link"])
        if not leitura.e_pdf(conteudo):
            log.warning(
                "A CVM devolveu uma página no lugar do PDF (limite): para e continua depois."
            )
            break
        texto = texto_do_conteudo(conteudo, evento)
        nome = f"{evento['id']}.txt" if texto else f"{evento['id']}.sem_texto"
        (_textos(pasta) / nome).write_text(texto, encoding="utf-8")
        baixados += 1
    log.info("Textos baixados: %s; faltam %s", baixados, len(faltam) - baixados)
    return baixados


# --- estimar e conferir o teto --------------------------------------------------------------


def pendentes(eventos: list[dict], pasta: Path) -> list[dict]:
    """Os eventos ainda sem rótulo (os com erro entram de novo)."""
    feitos = _rotulados(pasta)
    return [e for e in eventos if e["id"] not in feitos]


def _parametros(evento: dict, pasta: Path) -> dict:
    return ri.pedido(evento, texto_guardado(pasta, evento["id"]) or "")


def estimar(cliente: anthropic.Anthropic, eventos: list[dict], pasta: Path) -> float:
    """O custo projetado em US$ pela Batch API: tokens de entrada contados numa amostra (a contagem
    não gasta) e a saída estimada por evento."""
    if not eventos:
        return 0.0
    amostra = random.Random(SEMENTE).sample(
        eventos, min(AMOSTRA_DA_ESTIMATIVA, len(eventos))
    )
    contados = []
    for evento in amostra:
        p = _parametros(evento, pasta)
        contados.append(
            cliente.messages.count_tokens(
                model=p["model"], system=p["system"], messages=p["messages"]
            ).input_tokens
        )
    entrada = sum(contados) / len(contados) * len(eventos)
    return ri.custo_em_dolares(
        round(entrada), ri.SAIDA_ESTIMADA_POR_EVENTO * len(eventos), lote=True
    )


def conferir_teto(manifesto: dict, estimativa: float, teto: float) -> None:
    gasto = manifesto.get("gasto_em_dolares", 0.0)
    if gasto + estimativa > teto:
        raise TetoPassado(
            f"Gasto já feito US$ {gasto:.2f} + estimativa US$ {estimativa:.2f} passa do teto US$ {teto:.2f}."
        )


# --- rótulos a partir das respostas -----------------------------------------------------------


def _custo_da_resposta(usage: anthropic.types.Usage, lote: bool) -> float:
    entrada = (
        (usage.input_tokens or 0)
        + PESO_DA_ESCRITA_NO_CACHE
        * (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        + PESO_DA_LEITURA_DO_CACHE * (getattr(usage, "cache_read_input_tokens", 0) or 0)
    )
    return ri.custo_em_dolares(round(entrada), usage.output_tokens or 0, lote=lote)


def registro(
    evento: dict, pasta: Path, mensagem: anthropic.types.Message, origem: str
) -> dict:
    """O que fica guardado de uma resposta: rótulo ou erro, sempre com a entrada e a resposta bruta."""
    texto_do_documento = texto_guardado(pasta, evento["id"]) or ""
    bruta = next((b.text for b in mensagem.content if b.type == "text"), "")
    resultado = ri.de_mensagem(mensagem.stop_reason, bruta, evento, texto_do_documento)
    base = {
        "evento_id": evento["id"],
        "origem": origem,
        "rotulado_em": datetime.now(FUSO).isoformat(timespec="seconds"),
        "tinha_texto": bool(texto_do_documento),
        "hash_da_entrada": ri.hash_da_entrada(ri.pedido(evento, texto_do_documento)),
        "resposta_bruta": bruta,
        "tokens_entrada": mensagem.usage.input_tokens,
        "tokens_saida": mensagem.usage.output_tokens,
    }
    if isinstance(resultado, ri.ErroDeRotulo):
        return base | {"erro": resultado.motivo, "por": "ia", "modelo": ri.MODELO}
    return base | resultado.para_guardar()


# --- piloto, enviar e buscar ------------------------------------------------------------------


def piloto(
    cliente: anthropic.Anthropic, eventos: list[dict], pasta: Path, n: int, teto: float
) -> int:
    """Rotula `n` eventos na hora (preço normal), para conferir formato, erros e custo real."""
    escolhidos = pendentes(eventos, pasta)[:n]
    manifesto = ler_manifesto(pasta)
    conferir_teto(
        manifesto, estimar(cliente, escolhidos, pasta) / ri.DESCONTO_DO_LOTE, teto
    )
    registros, gasto = [], 0.0
    for evento in escolhidos:
        mensagem = cliente.messages.create(**_parametros(evento, pasta))
        registros.append(registro(evento, pasta, mensagem, "piloto"))
        gasto += _custo_da_resposta(mensagem.usage, lote=False)
    _acrescentar(pasta, registros)
    manifesto["gasto_em_dolares"] = manifesto.get("gasto_em_dolares", 0.0) + gasto
    manifesto["pilotos"] = [
        *manifesto.get("pilotos", []),
        {"eventos": len(registros), "gasto": gasto},
    ]
    gravar_manifesto(pasta, manifesto, eventos)
    log.info("Piloto: %s eventos, US$ %.4f", len(registros), gasto)
    return len(registros)


def enviar(
    cliente: anthropic.Anthropic,
    eventos: list[dict],
    pasta: Path,
    teto: float,
    permitir_sem_texto: bool = False,
) -> str | None:
    """Manda os pendentes num lote da Batch API, se o teto permitir. Devolve o id do lote."""
    manifesto = ler_manifesto(pasta)
    if any(lote.get("estado") != "gravado" for lote in manifesto.get("lotes", [])):
        raise RuntimeError(
            "Há um lote enviado e ainda não gravado: rode `buscar` primeiro."
        )
    faltam = pendentes(eventos, pasta)
    if not faltam:
        log.info("Nada pendente.")
        return None
    sem_baixar = [e["id"] for e in faltam if texto_guardado(pasta, e["id"]) is None]
    if sem_baixar and not permitir_sem_texto:
        raise RuntimeError(
            f"{len(sem_baixar)} eventos sem o texto baixado: rode `baixar` (ou use --permitir-sem-texto)."
        )
    estimativa = estimar(cliente, faltam, pasta)
    conferir_teto(manifesto, estimativa, teto)
    for evento in faltam:
        if not _CUSTOM_ID.fullmatch(evento["id"]):
            raise ValueError(f"Id fora do formato da Batch API: {evento['id']!r}")
    lote = cliente.messages.batches.create(
        requests=[
            {"custom_id": e["id"], "params": _parametros(e, pasta)} for e in faltam
        ]
    )
    manifesto["lotes"] = [
        *manifesto.get("lotes", []),
        {"id": lote.id, "eventos": len(faltam), "estimativa": estimativa, "estado": "enviado",
         "enviado_em": datetime.now(FUSO).isoformat(timespec="seconds")},
    ]  # fmt: skip
    gravar_manifesto(pasta, manifesto, eventos)
    log.info(
        "Lote %s enviado: %s eventos, estimativa US$ %.2f",
        lote.id,
        len(faltam),
        estimativa,
    )
    return lote.id


def buscar(cliente: anthropic.Anthropic, eventos: list[dict], pasta: Path) -> int:
    """Grava os resultados dos lotes que terminaram. Devolve quantos registros gravou."""
    manifesto = ler_manifesto(pasta)
    por_id = {e["id"]: e for e in eventos}
    gravados = 0
    for lote in manifesto.get("lotes", []):
        if lote.get("estado") == "gravado":
            continue
        if cliente.messages.batches.retrieve(lote["id"]).processing_status != "ended":
            log.info("Lote %s ainda processando.", lote["id"])
            continue
        registros, gasto = [], 0.0
        for resultado in cliente.messages.batches.results(lote["id"]):
            evento = por_id[resultado.custom_id]
            if resultado.result.type == "succeeded":
                mensagem = resultado.result.message
                registros.append(
                    registro(evento, pasta, mensagem, f"lote {lote['id']}")
                )
                gasto += _custo_da_resposta(mensagem.usage, lote=True)
            else:
                registros.append({"evento_id": evento["id"], "origem": f"lote {lote['id']}",
                                  "erro": f"lote: {resultado.result.type}", "por": "ia", "modelo": ri.MODELO})  # fmt: skip
        _acrescentar(pasta, registros)
        lote |= {"estado": "gravado", "gasto": gasto}
        manifesto["gasto_em_dolares"] = manifesto.get("gasto_em_dolares", 0.0) + gasto
        gravados += len(registros)
    gravar_manifesto(pasta, manifesto, eventos)
    return gravados


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "passo", choices=("baixar", "estimar", "piloto", "enviar", "buscar")
    )
    argumentos.add_argument(
        "--eventos", type=Path, required=True, help="eventos.json da página"
    )
    argumentos.add_argument(
        "--pasta", type=Path, required=True, help="pasta no acervo (rotulos_ia/v1)"
    )
    argumentos.add_argument(
        "--teto-dolares", type=float, help="obrigatório em estimar, piloto e enviar"
    )
    argumentos.add_argument("--n", type=int, default=30, help="eventos do piloto")
    argumentos.add_argument(
        "--permitir-sem-texto",
        action="store_true",
        help="enviar mesmo sem o texto de todos",
    )
    argumentos.add_argument("--maximo", type=int, default=500, help="downloads por vez")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    eventos = ler_eventos(opcoes.eventos)
    opcoes.pasta.mkdir(parents=True, exist_ok=True)
    if opcoes.passo == "baixar":
        baixar(eventos, opcoes.pasta, opcoes.maximo)
        return 0
    if opcoes.passo in ("estimar", "piloto", "enviar") and opcoes.teto_dolares is None:
        log.error(
            "Diga o teto com --teto-dolares (o Tiago combinou US$ 60 em 14/10/2026)."
        )
        return 2
    cliente = anthropic.Anthropic()  # a chave vem de ANTHROPIC_API_KEY
    try:
        if opcoes.passo == "estimar":
            faltam = pendentes(eventos, opcoes.pasta)
            estimativa = estimar(cliente, faltam, opcoes.pasta)
            gasto = ler_manifesto(opcoes.pasta).get("gasto_em_dolares", 0.0)
            sem_texto = sum(
                texto_guardado(opcoes.pasta, e["id"]) is None for e in faltam
            )
            print(f"Pendentes: {len(faltam)} ({sem_texto} sem texto baixado)")
            print(
                f"Estimativa pela Batch API: US$ {estimativa:.2f}; já gasto: US$ {gasto:.2f}; teto: US$ {opcoes.teto_dolares:.2f}"
            )
        elif opcoes.passo == "piloto":
            piloto(cliente, eventos, opcoes.pasta, opcoes.n, opcoes.teto_dolares)
        elif opcoes.passo == "enviar":
            enviar(
                cliente,
                eventos,
                opcoes.pasta,
                opcoes.teto_dolares,
                opcoes.permitir_sem_texto,
            )
        else:
            buscar(cliente, eventos, opcoes.pasta)
    except TetoPassado as erro:
        log.error("%s Nada foi enviado.", erro)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
