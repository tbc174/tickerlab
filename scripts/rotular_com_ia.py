"""Rotula a fila das 21h pela API do Claude (ADR 0072; plano `rotulagem-por-ia` de 14/10/2026).

    python -m scripts.rotular_com_ia baixar   --eventos eventos.json --pasta ACERVO/rotulos_ia/v1
    python -m scripts.rotular_com_ia estimar  --eventos eventos.json --pasta ... --teto-dolares 60
    python -m scripts.rotular_com_ia piloto   --eventos eventos.json --pasta ... --teto-dolares 60 --n 30
    python -m scripts.rotular_com_ia enviar   --eventos eventos.json --pasta ... --teto-dolares 60
    python -m scripts.rotular_com_ia buscar   --eventos eventos.json --pasta ...
    python -m scripts.rotular_com_ia identificar --eventos ... --pasta ... --teto-dolares 60 [--so-estimar]
    python -m scripts.rotular_com_ia estabilidade --eventos ... --pasta ... --teto-dolares 60 [--so-estimar]
    python -m scripts.rotular_com_ia vazamento --eventos ... --pasta ... [--texto-so-nos-fatos]  (sem API)
    python -m scripts.rotular_com_ia auditar  --eventos ... --pasta ... --humanos tiago.json
    python -m scripts.rotular_com_ia estimar  --eventos ... --pasta ... --teto-dolares 10 \
        --modelo claude-opus-5-5 --so-prova
    python -m scripts.rotular_com_ia comparar --eventos ... --pasta ...

Com `--texto-so-nos-fatos` (estimar, piloto, enviar, identificar), só os fatos relevantes vão com
texto; os outros vão só com o assunto, como o guia manda a pessoa fazer (Tiago, 14/10/2026: vale se a
CVM liberar menos de 100 documentos por dia). Cada rótulo e cada lote guardam a regra usada.

`baixar` guarda o texto de cada documento em `<pasta>/textos/` (um pedido por vez à CVM, com um minuto
de pausa, e para no primeiro sinal de limite, como o leitor; roda de novo no dia seguinte). `estimar`
conta os tokens de uma amostra pela API (não gasta) e projeta o custo da fila. `piloto` rotula poucos
eventos na hora, para conferir formato e erros. `enviar` manda o resto num lote da Batch API (metade do
preço; até 24 h) e `buscar` grava o resultado quando o lote termina.
`identificar` pergunta à IA qual é a empresa de cada evento de prova (teste de vazamento) e `auditar`
dá o veredito da ADR 0072 contra os rótulos do Tiago, em `<pasta>/auditoria.json`.

**O teto vale para tudo:** nenhum passo gasta se o gasto já feito mais a estimativa passar do teto.
Os rótulos vão para `<pasta>/rotulos.jsonl` (um por linha, com `por: "ia"`, a entrada em hash e a
resposta bruta) e o resumo para `<pasta>/manifesto.json`. Nada aqui lê ou grava na página das 21h: os
rótulos do Tiago continuam às cegas. A chave fica em `ANTHROPIC_API_KEY` (nunca no código).

**Segundo modelo às cegas (Emenda 1 da ADR 0072, 17/10/2026):** `--modelo claude-opus-5-5` faz os
mesmos passos com o Opus, no mesmo pedido, gravando em `<pasta>/rotulos.claude-opus-5-5.jsonl` e
`<pasta>/manifesto.claude-opus-5-5.json` (o gasto e o teto do Opus são contados à parte do Sonnet).
`--so-prova` limita ao conjunto de prova: os 300 primeiros da fila e o `lote-leitor-v1`. `comparar`
mede Sonnet × Opus nos 300 com os limites da emenda e lista, no lote do leitor, os eventos em que os
dois concordam no assunto (a referência de máquina do leitor), em `<pasta>/comparacao-modelos.json`.

**As outras duas conferências da Emenda 1**, só com o Sonnet e sem os rótulos do Tiago:
`identificar` pergunta qual é a empresa em todo o conjunto de prova (mais os eventos que o Tiago rotulou,
se `--humanos` vier) e grava o veredito em `<pasta>/identificacao.json` (mais de 10% reconhecidas
reprova); `estabilidade` sorteia 100 eventos com a semente fixa, grava o sorteio em
`<pasta>/estabilidade-sorteio.json` **antes de gastar**, rotula os sorteados de novo (em
`<pasta>/estabilidade.jsonl`, nunca no `rotulos.jsonl`) e publica a concordância IA × IA em
`<pasta>/estabilidade.json`. Os dois leem o mesmo pedido que o rótulo do Sonnet leu (a regra de texto
gravada nele) e, com `--so-estimar`, só contam os tokens e mostram o custo (não gastam).
"""

import argparse
import hashlib
import json
import logging
import random
import re
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

from src import auditoria_rotulos as ar
from src import leitura, rede
from src import rotulos_ia as ri

log = logging.getLogger("tickerlab.rotulos_ia")

PAUSA_ENTRE_DOWNLOADS = 60  # segundos: a CVM limita os downloads por endereço
MAX_CARACTERES_GUARDADOS = 20_000  # o texto guardado; o pedido usa só o começo
AMOSTRA_DA_ESTIMATIVA = 50
SEMENTE = 20261014
# cache: escrever custa 1,25x a entrada; ler custa uma fração que muda por modelo (`ri.MODELOS`)
PESO_DA_ESCRITA_NO_CACHE = 1.25
# mensagem mínima para contar o prefixo fixo (o guia no `system`), que o cache escreve uma vez e lê nos outros
SONDA_DO_PREFIXO = "."
_CUSTOM_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_FORA_DA_CHAVE = re.compile(r"[^A-Za-z0-9_-]")
FUSO = ZoneInfo("America/Sao_Paulo")


class TetoPassado(Exception):
    """O gasto já feito mais a estimativa passa do teto: nada é enviado."""


# --- arquivos ---------------------------------------------------------------------------------


def chave(evento_id: str) -> str:
    """O id como nome de arquivo e `custom_id` do lote: o que não for letra, número, `-` ou `_` vira `_`
    (um id do lote do leitor tem espaço). O id original continua em cada rótulo."""
    return _FORA_DA_CHAVE.sub("_", evento_id)


def ler_eventos(caminho: Path) -> list[dict]:
    """A fila da página, cada evento com a `ordem` (a posição dele na página, como nos rótulos do
    Tiago). Evento sem id ou com chave repetida fica de fora, com aviso (a fila v1 tinha um sem id, na
    posição 3.120)."""
    eventos = json.loads(caminho.read_text(encoding="utf-8"))["eventos"]
    validos, chaves = [], set()
    for posicao, evento in enumerate(eventos):
        k = chave(str(evento.get("id") or ""))
        if not _CUSTOM_ID.fullmatch(k) or k in chaves:
            log.warning(
                "Evento na posição %s sem id válido (%r): fica de fora.",
                posicao,
                evento.get("id"),
            )
            continue
        chaves.add(k)
        validos.append({"ordem": posicao, **evento})
    return validos


def ids_de_prova(eventos: list[dict]) -> list[str]:
    """Os ids do conjunto de prova: os 300 primeiros da fila e o `lote-leitor-v1`."""
    primeiros, lote = ar.conjunto_de_prova(eventos)
    return primeiros + lote


def so_prova(eventos: list[dict]) -> list[dict]:
    """Só o conjunto de prova: os 300 primeiros da fila e o `lote-leitor-v1`."""
    prova = set(ids_de_prova(eventos))
    return [e for e in eventos if e["id"] in prova]


def _sufixo(modelo: str) -> str:
    """Os arquivos do rotulador ficam com o nome de sempre; os de outro modelo levam o nome dele."""
    return "" if modelo == ri.MODELO else f".{modelo}"


def arquivo_dos_rotulos(pasta: Path, modelo: str = ri.MODELO) -> Path:
    return pasta / f"rotulos{_sufixo(modelo)}.jsonl"


def arquivo_do_manifesto(pasta: Path, modelo: str = ri.MODELO) -> Path:
    return pasta / f"manifesto{_sufixo(modelo)}.json"


def _textos(pasta: Path) -> Path:
    return pasta / "textos"


def texto_guardado(pasta: Path, evento_id: str) -> str | None:
    """O texto baixado, "" se o documento não tem texto, None se ainda não foi baixado."""
    arquivo = _textos(pasta) / f"{chave(evento_id)}.txt"
    if arquivo.exists():
        return arquivo.read_text(encoding="utf-8")
    if (_textos(pasta) / f"{chave(evento_id)}.sem_texto").exists():
        return ""
    return None


def _ler_jsonl(arquivo: Path) -> dict[str, dict]:
    """Os registros de um arquivo, pelo id do evento (o último vale)."""
    if not arquivo.exists():
        return {}
    registros = (
        json.loads(linha)
        for linha in arquivo.read_text(encoding="utf-8").splitlines()
        if linha
    )
    return {r["evento_id"]: r for r in registros}


def ler_rotulos(pasta: Path, modelo: str = ri.MODELO) -> dict[str, dict]:
    """Os registros já gravados por um modelo, pelo id do evento (o último vale)."""
    return _ler_jsonl(arquivo_dos_rotulos(pasta, modelo))


def _rotulados(pasta: Path, modelo: str = ri.MODELO) -> set[str]:
    return {i for i, r in ler_rotulos(pasta, modelo).items() if "erro" not in r}


def ler_manifesto(pasta: Path, modelo: str = ri.MODELO) -> dict:
    arquivo = arquivo_do_manifesto(pasta, modelo)
    if arquivo.exists():
        return json.loads(arquivo.read_text(encoding="utf-8"))
    return {"gasto_em_dolares": 0.0, "lotes": [], "pilotos": []}


def gravar_manifesto(
    pasta: Path, manifesto: dict, eventos: list[dict], modelo: str = ri.MODELO
) -> None:
    registros = ler_rotulos(pasta, modelo)
    jsonl = arquivo_dos_rotulos(pasta, modelo)
    manifesto |= {
        "modelo": modelo,
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
    arquivo_do_manifesto(pasta, modelo).write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _acrescentar(pasta: Path, registros: list[dict], modelo: str = ri.MODELO) -> None:
    with arquivo_dos_rotulos(pasta, modelo).open("a", encoding="utf-8") as arquivo:
        for registro in registros:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


# --- baixar ---------------------------------------------------------------------------------


def _baixar_da_cvm(url: str) -> bytes:
    resposta = rede.obter(
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
    """Baixa os textos que faltam, **fatos relevantes primeiro** (são os que mais dependem do texto;
    a CVM limita os downloads e a fila inteira pode levar semanas); para no primeiro sinal de limite.
    Devolve quantos baixou."""
    _textos(pasta).mkdir(parents=True, exist_ok=True)
    faltam = [e for e in eventos if texto_guardado(pasta, e["id"]) is None]
    faltam = sorted(faltam, key=lambda e: not ri.e_fato_relevante(e))[:maximo]
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
        nome = (
            f"{chave(evento['id'])}.txt"
            if texto
            else f"{chave(evento['id'])}.sem_texto"
        )
        (_textos(pasta) / nome).write_text(texto, encoding="utf-8")
        baixados += 1
    log.info("Textos baixados: %s; faltam %s", baixados, len(faltam) - baixados)
    return baixados


# --- estimar e conferir o teto --------------------------------------------------------------


def pendentes(eventos: list[dict], pasta: Path, modelo: str = ri.MODELO) -> list[dict]:
    """Os eventos ainda sem rótulo deste modelo (os com erro entram de novo)."""
    feitos = _rotulados(pasta, modelo)
    return [e for e in eventos if e["id"] not in feitos]


def texto_do_pedido(evento: dict, pasta: Path, so_fatos: bool = False) -> str | None:
    """O texto que vai para o modelo. Com `so_fatos` (Tiago, 14/10/2026: se a CVM liberar menos de
    100 documentos por dia), quem não é fato relevante vai só com o assunto (""), como o guia manda a
    pessoa fazer. None: o texto ainda não foi baixado."""
    if so_fatos and not ri.e_fato_relevante(evento):
        return ""
    return texto_guardado(pasta, evento["id"])


def _parametros(
    evento: dict, pasta: Path, so_fatos: bool = False, modelo: str = ri.MODELO
) -> dict:
    return ri.pedido(evento, texto_do_pedido(evento, pasta, so_fatos) or "", modelo)


def estimar(
    cliente: anthropic.Anthropic,
    eventos: list[dict],
    pasta: Path,
    so_fatos: bool = False,
    modelo: str = ri.MODELO,
) -> float:
    """O custo projetado em US$ pela Batch API: tokens de entrada contados numa amostra (a contagem
    não gasta) e a saída estimada por evento. O prefixo fixo do pedido (o guia) entra pelo preço do
    cache: escrito uma vez, lido nos outros (sem isso a estimativa saía ~6x acima do real, 15/10)."""
    if not eventos:
        return 0.0
    amostra = random.Random(SEMENTE).sample(
        eventos, min(AMOSTRA_DA_ESTIMATIVA, len(eventos))
    )
    contados = []
    for evento in amostra:
        p = _parametros(evento, pasta, so_fatos, modelo)
        contados.append(
            cliente.messages.count_tokens(
                model=p["model"], system=p["system"], messages=p["messages"]
            ).input_tokens
        )
    sonda = _parametros(amostra[0], pasta, so_fatos, modelo)
    prefixo = cliente.messages.count_tokens(
        model=sonda["model"],
        system=sonda["system"],
        messages=[{"role": "user", "content": SONDA_DO_PREFIXO}],
    ).input_tokens
    n = len(eventos)
    media = sum(contados) / len(contados)
    prefixo = min(prefixo, media)  # a sonda tem alguns tokens a mais que o prefixo puro
    preco = ri.modelo_conhecido(modelo)
    entrada = (media - prefixo) * n + prefixo * (
        PESO_DA_ESCRITA_NO_CACHE + preco.leitura_do_cache * (n - 1)
    )
    return ri.custo_em_dolares(
        round(entrada), preco.saida_estimada_por_evento * n, lote=True, modelo=modelo
    )


def custo_na_hora(
    cliente: anthropic.Anthropic, pedidos: list[dict], saida_por_evento: int
) -> float:
    """O custo em US$ de mandar `pedidos` um por um, a preço cheio e sem descontar o cache (fica um
    pouco acima do real): a entrada contada numa amostra (a contagem não gasta) e a saída estimada."""
    if not pedidos:
        return 0.0
    amostra = random.Random(SEMENTE).sample(
        pedidos, min(AMOSTRA_DA_ESTIMATIVA, len(pedidos))
    )
    media = sum(
        cliente.messages.count_tokens(
            model=p["model"], system=p["system"], messages=p["messages"]
        ).input_tokens
        for p in amostra
    ) / len(amostra)
    n = len(pedidos)
    return ri.custo_em_dolares(
        round(media * n), saida_por_evento * n, lote=False, modelo=pedidos[0]["model"]
    )


def conferir_teto(manifesto: dict, estimativa: float, teto: float) -> None:
    gasto = manifesto.get("gasto_em_dolares", 0.0)
    if gasto + estimativa > teto:
        raise TetoPassado(
            f"Gasto já feito US$ {gasto:.2f} + estimativa US$ {estimativa:.2f} passa do teto US$ {teto:.2f}."
        )


# --- rótulos a partir das respostas -----------------------------------------------------------


def _custo_da_resposta(
    usage: anthropic.types.Usage, lote: bool, modelo: str = ri.MODELO
) -> float:
    leitura = ri.modelo_conhecido(modelo).leitura_do_cache
    entrada = (
        (usage.input_tokens or 0)
        + PESO_DA_ESCRITA_NO_CACHE
        * (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        + leitura * (getattr(usage, "cache_read_input_tokens", 0) or 0)
    )
    return ri.custo_em_dolares(
        round(entrada), usage.output_tokens or 0, lote=lote, modelo=modelo
    )


def registro(
    evento: dict,
    pasta: Path,
    mensagem: anthropic.types.Message,
    origem: str,
    so_fatos: bool = False,
    modelo: str = ri.MODELO,
) -> dict:
    """O que fica guardado de uma resposta: rótulo ou erro, sempre com a entrada e a resposta bruta
    (o texto conferido é o mesmo que foi no pedido, pela mesma regra)."""
    texto_do_documento = texto_do_pedido(evento, pasta, so_fatos) or ""
    bruta = next((b.text for b in mensagem.content if b.type == "text"), "")
    resultado = ri.de_mensagem(mensagem.stop_reason, bruta, evento, texto_do_documento)
    base = {
        "evento_id": evento["id"],
        "origem": origem,
        "rotulado_em": datetime.now(FUSO).isoformat(timespec="seconds"),
        "tinha_texto": bool(texto_do_documento),
        "texto_so_nos_fatos": so_fatos,
        "hash_da_entrada": ri.hash_da_entrada(
            ri.pedido(evento, texto_do_documento, modelo)
        ),
        "resposta_bruta": bruta,
        "tokens_entrada": mensagem.usage.input_tokens,
        "tokens_saida": mensagem.usage.output_tokens,
    }
    if isinstance(resultado, ri.ErroDeRotulo):
        return base | {"erro": resultado.motivo, "por": "ia", "modelo": modelo}
    return base | resultado.para_guardar(modelo)


# --- piloto, enviar e buscar ------------------------------------------------------------------


def piloto(
    cliente: anthropic.Anthropic,
    eventos: list[dict],
    pasta: Path,
    n: int,
    teto: float,
    so_fatos: bool = False,
    modelo: str = ri.MODELO,
) -> int:
    """Rotula `n` eventos na hora (preço normal), para conferir formato, erros e custo real. Só
    entram eventos prontos pela regra de texto (o texto baixado, ou só o assunto com `so_fatos`)."""
    prontos = [
        e
        for e in pendentes(eventos, pasta, modelo)
        if texto_do_pedido(e, pasta, so_fatos) is not None
    ]
    escolhidos = prontos[:n]
    manifesto = ler_manifesto(pasta, modelo)
    conferir_teto(
        manifesto,
        estimar(cliente, escolhidos, pasta, so_fatos, modelo) / ri.DESCONTO_DO_LOTE,
        teto,
    )
    registros, gasto = [], 0.0
    for evento in escolhidos:
        mensagem = cliente.messages.create(
            **_parametros(evento, pasta, so_fatos, modelo)
        )
        registros.append(registro(evento, pasta, mensagem, "piloto", so_fatos, modelo))
        gasto += _custo_da_resposta(mensagem.usage, lote=False, modelo=modelo)
    _acrescentar(pasta, registros, modelo)
    manifesto["gasto_em_dolares"] = manifesto.get("gasto_em_dolares", 0.0) + gasto
    manifesto["pilotos"] = [
        *manifesto.get("pilotos", []),
        {"eventos": len(registros), "gasto": gasto},
    ]
    gravar_manifesto(pasta, manifesto, eventos, modelo)
    log.info("Piloto: %s eventos, US$ %.4f", len(registros), gasto)
    return len(registros)


def enviar(
    cliente: anthropic.Anthropic,
    eventos: list[dict],
    pasta: Path,
    teto: float,
    permitir_sem_texto: bool = False,
    so_fatos: bool = False,
    so_prontos: bool = False,
    modelo: str = ri.MODELO,
) -> str | None:
    """Manda os pendentes num lote da Batch API, se o teto permitir. Devolve o id do lote. Com
    `so_prontos`, vão só os que já têm o texto pela regra; os outros esperam o próximo lote (a CVM
    libera poucos textos por dia)."""
    manifesto = ler_manifesto(pasta, modelo)
    if any(lote.get("estado") != "gravado" for lote in manifesto.get("lotes", [])):
        raise RuntimeError(
            "Há um lote enviado e ainda não gravado: rode `buscar` primeiro."
        )
    faltam = pendentes(eventos, pasta, modelo)
    if not faltam:
        log.info("Nada pendente.")
        return None
    sem_baixar = [
        e["id"] for e in faltam if texto_do_pedido(e, pasta, so_fatos) is None
    ]
    if sem_baixar and so_prontos:
        faltam = [e for e in faltam if e["id"] not in set(sem_baixar)]
        log.info("%s eventos esperam o texto para o próximo lote.", len(sem_baixar))
        if not faltam:
            log.info("Nenhum evento pronto.")
            return None
    elif sem_baixar and not permitir_sem_texto:
        raise RuntimeError(
            f"{len(sem_baixar)} eventos sem o texto baixado: rode `baixar` (ou use --permitir-sem-texto)."
        )
    estimativa = estimar(cliente, faltam, pasta, so_fatos, modelo)
    conferir_teto(manifesto, estimativa, teto)
    lote = cliente.messages.batches.create(
        requests=[
            {
                "custom_id": chave(e["id"]),
                "params": _parametros(e, pasta, so_fatos, modelo),
            }
            for e in faltam
        ]
    )
    manifesto["lotes"] = [
        *manifesto.get("lotes", []),
        {"id": lote.id, "eventos": len(faltam), "estimativa": estimativa, "estado": "enviado",
         "texto_so_nos_fatos": so_fatos,
         "enviado_em": datetime.now(FUSO).isoformat(timespec="seconds")},
    ]  # fmt: skip
    gravar_manifesto(pasta, manifesto, eventos, modelo)
    log.info(
        "Lote %s enviado: %s eventos, estimativa US$ %.2f",
        lote.id,
        len(faltam),
        estimativa,
    )
    return lote.id


def buscar(
    cliente: anthropic.Anthropic,
    eventos: list[dict],
    pasta: Path,
    modelo: str = ri.MODELO,
) -> int:
    """Grava os resultados dos lotes que terminaram. Devolve quantos registros gravou."""
    manifesto = ler_manifesto(pasta, modelo)
    por_chave = {chave(e["id"]): e for e in eventos}
    gravados = 0
    for lote in manifesto.get("lotes", []):
        if lote.get("estado") == "gravado":
            continue
        if cliente.messages.batches.retrieve(lote["id"]).processing_status != "ended":
            log.info("Lote %s ainda processando.", lote["id"])
            continue
        registros, gasto = [], 0.0
        for resultado in cliente.messages.batches.results(lote["id"]):
            evento = por_chave[resultado.custom_id]
            if resultado.result.type == "succeeded":
                mensagem = resultado.result.message
                registros.append(
                    registro(
                        evento,
                        pasta,
                        mensagem,
                        f"lote {lote['id']}",
                        lote.get("texto_so_nos_fatos", False),
                        modelo,
                    )
                )
                gasto += _custo_da_resposta(mensagem.usage, lote=True, modelo=modelo)
            else:
                registros.append({"evento_id": evento["id"], "origem": f"lote {lote['id']}",
                                  "erro": f"lote: {resultado.result.type}", "por": "ia", "modelo": modelo})  # fmt: skip
        _acrescentar(pasta, registros, modelo)
        lote |= {"estado": "gravado", "gasto": gasto}
        manifesto["gasto_em_dolares"] = manifesto.get("gasto_em_dolares", 0.0) + gasto
        gravados += len(registros)
    gravar_manifesto(pasta, manifesto, eventos, modelo)
    return gravados


# --- auditoria: identificação da empresa e veredito (ADR 0072, item 3) -----------------------

# tokens de saída por pergunta, para conferir o teto antes
SAIDA_POR_IDENTIFICACAO = 200
ARQUIVO_DA_IDENTIFICACAO = "identificacao.json"


def ler_humanos(caminho: Path) -> dict[str, dict]:
    """Os rótulos do Tiago exportados da página (lista, ou {"rotulos": [...]}), pelo id do evento."""
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    rotulos = dados["rotulos"] if isinstance(dados, dict) else dados
    return {r["evento_id"]: r for r in rotulos}


def prova_dos_humanos(humanos: dict[str, dict]) -> list[str]:
    """Os eventos que o Tiago rotulou (pulados não contam)."""
    return sorted(
        i for i, h in humanos.items() if not h.get("pulado") and h.get("nota")
    )


def ler_identificacoes(pasta: Path) -> dict[str, bool] | None:
    arquivo = pasta / "identificacoes.jsonl"
    if not arquivo.exists():
        return None
    return {i: r["identificou"] for i, r in _ler_jsonl(arquivo).items()}


def _regra_do_rotulo(rotulos: dict[str, dict], evento_id: str, so_fatos: bool) -> bool:
    """A regra de texto com que o Sonnet rotulou o evento (gravada no rótulo); sem rótulo, a da
    linha de comando. Assim as conferências leem o mesmo documento que o rotulador leu."""
    return rotulos.get(evento_id, {}).get("texto_so_nos_fatos", so_fatos)


def _pedidos_de_identificacao(
    eventos: list[dict], pasta: Path, ids: list[str], so_fatos: bool
) -> list[tuple[dict, dict]]:
    """Os eventos de `ids` ainda sem palpite, cada um com o pedido de identificação."""
    por_id = {e["id"]: e for e in eventos}
    feitos = ler_identificacoes(pasta) or {}
    rotulos = ler_rotulos(pasta)
    faltam = [por_id[i] for i in ids if i in por_id and i not in feitos]
    return [
        (e, ri.pedido_de_identificacao(e, texto_do_pedido(
            e, pasta, _regra_do_rotulo(rotulos, e["id"], so_fatos)) or ""))
        for e in faltam
    ]  # fmt: skip


ARQUIVO_DO_VAZAMENTO = "vazamento.json"


def vazamento(
    eventos: list[dict], pasta: Path, ids: list[str], so_fatos: bool = False
) -> dict:
    """A conferência sem custo antes do teste de identificação (v2): em quantos eventos de `ids` o
    documento anonimizado, o mesmo que a identificação lê, ainda tem uma palavra que distingue a
    empresa (deveria ser zero) ou uma palavra comum do nome que a auditoria contaria como acerto.
    Grava em `<pasta>/vazamento.json`; não chama a API."""
    por_id = {e["id"]: e for e in eventos}
    rotulos = ler_rotulos(pasta)
    distintas: Counter[str] = Counter()
    comuns: Counter[str] = Counter()
    com_distinta, com_comum = [], []
    for i in (i for i in ids if i in por_id):
        evento = por_id[i]
        regra = _regra_do_rotulo(rotulos, i, so_fatos)
        lido = ri.documento(evento, texto_do_pedido(evento, pasta, regra) or "")
        nome = evento.get("empresa") or ""
        achadas = ri.palavras_que_vazam(lido, nome)
        ficam = ri.palavras_comuns_que_ficam(lido, nome)
        distintas.update(achadas)
        comuns.update(ficam)
        if achadas:
            com_distinta.append(i)
        if ficam:
            com_comum.append(i)
    resultado = {
        "n": sum(i in por_id for i in ids),
        "com_palavra_distinta": len(com_distinta),
        "com_palavra_comum": len(com_comum),
        "palavras_distintas": dict(distintas.most_common(30)),
        "palavras_comuns": dict(comuns.most_common(30)),
        "eventos_com_palavra_distinta": com_distinta[:100],
        "versao_do_prompt": ri.VERSAO_DO_PROMPT,
        "medido_em": datetime.now(FUSO).isoformat(timespec="seconds"),
    }
    (pasta / ARQUIVO_DO_VAZAMENTO).write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return resultado


def estimar_identificacao(
    cliente: anthropic.Anthropic,
    eventos: list[dict],
    pasta: Path,
    ids: list[str],
    so_fatos: bool = False,
) -> float:
    """O custo das perguntas que faltam (não gasta: só conta os tokens)."""
    pedidos = [p for _, p in _pedidos_de_identificacao(eventos, pasta, ids, so_fatos)]
    return custo_na_hora(cliente, pedidos, SAIDA_POR_IDENTIFICACAO)


def identificar(
    cliente: anthropic.Anthropic,
    eventos: list[dict],
    pasta: Path,
    ids: list[str],
    teto: float,
    so_fatos: bool = False,
) -> ar.Veredito:
    """Pergunta ao Sonnet qual é a empresa de cada evento de `ids` (o conjunto de prova, pela
    Emenda 1), lendo o mesmo documento anonimizado que o rotulador leu, e grava o veredito em
    `<pasta>/identificacao.json` (passe ou não, conta como tentativa)."""
    faltam = _pedidos_de_identificacao(eventos, pasta, ids, so_fatos)
    manifesto = ler_manifesto(pasta)
    conferir_teto(
        manifesto,
        custo_na_hora(cliente, [p for _, p in faltam], SAIDA_POR_IDENTIFICACAO),
        teto,
    )
    gasto = 0.0
    with (pasta / "identificacoes.jsonl").open("a", encoding="utf-8") as arquivo:
        for evento, parametros in faltam:
            mensagem = cliente.messages.create(**parametros)
            bruta = next((b.text for b in mensagem.content if b.type == "text"), "")
            palpite = ri.palpite_da_identificacao(mensagem.stop_reason, bruta)
            linha = {
                "evento_id": evento["id"],
                "palpite": palpite,
                "identificou": ar.identificou(palpite, evento.get("empresa") or ""),
            }
            arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")
            gasto += _custo_da_resposta(mensagem.usage, lote=False)
    identificacoes = ler_identificacoes(pasta) or {}
    anterior = manifesto.get("identificacao", {}).get("gasto", 0.0)
    manifesto["gasto_em_dolares"] = manifesto.get("gasto_em_dolares", 0.0) + gasto
    manifesto["identificacao"] = {
        "eventos": len(identificacoes),
        "gasto": anterior + gasto,
    }
    gravar_manifesto(pasta, manifesto, eventos)
    veredito = ar.veredito_da_identificacao(identificacoes, ids)
    (pasta / ARQUIVO_DA_IDENTIFICACAO).write_text(
        json.dumps(
            asdict(veredito) | {"passou": veredito.passou,
                                "limite": ar.LIMITES["max_identificadas"],
                                "modelo": ri.MODELO, "versao_do_prompt": ri.VERSAO_DO_PROMPT,
                                "identificado_em": datetime.now(FUSO).isoformat(timespec="seconds")},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )  # fmt: skip
    return veredito


def auditar(pasta: Path, humanos: dict[str, dict]) -> ar.Veredito:
    """O veredito da ADR 0072, gravado em `<pasta>/auditoria.json` (passe ou não, conta como tentativa)."""
    veredito = ar.auditar(humanos, ler_rotulos(pasta), ler_identificacoes(pasta))
    (pasta / "auditoria.json").write_text(
        json.dumps(
            asdict(veredito) | {"passou": veredito.passou, "limites": ar.LIMITES,
                                "modelo": ri.MODELO, "versao_do_prompt": ri.VERSAO_DO_PROMPT,
                                "auditado_em": datetime.now(FUSO).isoformat(timespec="seconds")},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )  # fmt: skip
    return veredito


def _mesma_entrada(evento: dict, pasta: Path, a: dict, b: dict) -> bool:
    """Os dois rótulos saíram do mesmo pedido, trocando só o modelo? O pedido é refeito com o texto
    de hoje, pela regra do primeiro, e tem de bater com o hash guardado em cada um (Emenda 1: "o mesmo
    texto anonimizado")."""
    texto = texto_do_pedido(evento, pasta, a.get("texto_so_nos_fatos", False)) or ""
    return all(
        r.get("hash_da_entrada")
        == ri.hash_da_entrada(ri.pedido(evento, texto, r["modelo"]))
        for r in (a, b)
    )


def _com_o_desvio_do_trecho(
    rotulos: dict[str, dict], eventos: list[dict]
) -> tuple[dict[str, dict], list[str]]:
    """Os rótulos do Sonnet com os eventos do desvio registrado (`ar.DESVIO_DO_TRECHO`) refeitos
    pela resposta bruta, sem conferir o trecho; só se o erro for o do trecho e o resto valer."""
    por_id = {e["id"]: e for e in eventos}
    refeitos, desvios = dict(rotulos), []
    for i in sorted(ar.DESVIO_DO_TRECHO):
        r = rotulos.get(i, {})
        if i not in por_id or r.get("erro") != "trecho não está no documento":
            continue
        rotulo = ri.interpretar(
            r.get("resposta_bruta", ""), por_id[i], "", conferir_trecho=False
        )
        if isinstance(rotulo, ri.RotuloDaIA):
            semerro = {k: v for k, v in r.items() if k != "erro"}
            refeitos[i] = semerro | asdict(rotulo) | {"desvio": "trecho juntado"}
            desvios.append(i)
    return refeitos, desvios


def comparar(
    pasta: Path,
    eventos: list[dict],
    modelo_a: str = ri.MODELO,
    modelo_b: str = ri.MODELO_CONFERENTE,
) -> ar.Veredito:
    """Sonnet × Opus (Emenda 1 da ADR 0072): o veredito nos 300 primeiros e a referência do leitor
    (os eventos do lote em que os dois concordam no assunto), gravados em
    `<pasta>/comparacao-modelos.json` com o SHA-256 dos dois arquivos (passe ou não, conta como
    tentativa). Só contam os pares que leram o mesmo texto: o par com entrada diferente fica de fora
    e deixa o veredito incompleto."""
    a, b = ler_rotulos(pasta, modelo_a), ler_rotulos(pasta, modelo_b)
    a, desvios = _com_o_desvio_do_trecho(a, eventos)
    primeiros, lote = ar.conjunto_de_prova(eventos)
    diferentes = [
        e["id"]
        for e in eventos
        if ar.valido(a, e["id"])
        and ar.valido(b, e["id"])
        and not _mesma_entrada(e, pasta, a[e["id"]], b[e["id"]])
    ]
    b = {i: r for i, r in b.items() if i not in set(diferentes)}
    veredito = ar.comparar_modelos(a, b, primeiros)
    if fora := [i for i in diferentes if i in set(primeiros)]:
        veredito.motivos.append(
            f"{len(fora)} eventos em que os dois modelos não leram o mesmo texto"
        )
    referencia = ar.referencia_do_leitor(a, b, lote)
    sha256 = {
        m: hashlib.sha256(arquivo_dos_rotulos(pasta, m).read_bytes()).hexdigest()
        for m in (modelo_a, modelo_b)
        if arquivo_dos_rotulos(pasta, m).exists()
    }
    (pasta / "comparacao-modelos.json").write_text(
        json.dumps(
            {"modelos": [modelo_a, modelo_b], "versao_do_prompt": ri.VERSAO_DO_PROMPT,
             "primeiros": asdict(veredito), "passou": veredito.passou,
             "limites": ar.LIMITES_DA_COMPARACAO, "entradas_diferentes": diferentes,
             "desvios": desvios,
             "lote_do_leitor": {"eventos": len(lote), "concordam_no_assunto": len(referencia),
                                "referencia": referencia},
             "sha256": sha256,
             "comparado_em": datetime.now(FUSO).isoformat(timespec="seconds")},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )  # fmt: skip
    return veredito


# --- estabilidade (Emenda 1, item 3): o Sonnet contra ele mesmo -------------------------------

ARQUIVO_DO_SORTEIO = "estabilidade-sorteio.json"
ARQUIVO_DA_ESTABILIDADE = "estabilidade.json"


def ler_estabilidade(pasta: Path) -> dict[str, dict]:
    """A segunda rodada dos sorteados, pelo id do evento."""
    return _ler_jsonl(pasta / "estabilidade.jsonl")


def _sha256(arquivo: Path) -> str | None:
    return (
        hashlib.sha256(arquivo.read_bytes()).hexdigest() if arquivo.exists() else None
    )


def sorteio_gravado(eventos: list[dict], pasta: Path) -> list[str]:
    """Os 100 da estabilidade, escritos antes de qualquer gasto e nunca refeitos: na primeira vez,
    sorteia e grava com a semente e o SHA-256 dos rótulos de onde saiu; depois, só lê."""
    arquivo = pasta / ARQUIVO_DO_SORTEIO
    if arquivo.exists():
        return json.loads(arquivo.read_text(encoding="utf-8"))["eventos"]
    sorteio = ar.sorteio_da_estabilidade(eventos, ler_rotulos(pasta))
    arquivo.write_text(
        json.dumps(
            {"semente": ar.SEMENTE_DA_ESTABILIDADE, "eventos": sorteio,
             "sha256_dos_rotulos": _sha256(arquivo_dos_rotulos(pasta)),
             "sorteado_em": datetime.now(FUSO).isoformat(timespec="seconds")},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )  # fmt: skip
    return sorteio


def _pedidos_da_estabilidade(
    eventos: list[dict], pasta: Path, sorteio: list[str]
) -> tuple[list[tuple[dict, bool, dict]], list[str]]:
    """Os sorteados ainda sem a segunda rodada, cada um com a regra de texto e o pedido da primeira,
    e os que ficam de fora porque o pedido de hoje não bate com o hash do rótulo (texto mudou)."""
    por_id = {e["id"]: e for e in eventos}
    primeira, feitos = ler_rotulos(pasta), ler_estabilidade(pasta)
    pendentes, diferentes = [], []
    for i in sorteio:
        if i in feitos:
            continue
        regra = _regra_do_rotulo(primeira, i, False)
        parametros = _parametros(por_id[i], pasta, regra)
        if ri.hash_da_entrada(parametros) != primeira.get(i, {}).get("hash_da_entrada"):
            diferentes.append(i)
            continue
        pendentes.append((por_id[i], regra, parametros))
    return pendentes, diferentes


def estimar_estabilidade(
    cliente: anthropic.Anthropic, eventos: list[dict], pasta: Path
) -> float:
    """O custo da segunda rodada que falta (não gasta; o sorteio fica gravado)."""
    pendentes, _ = _pedidos_da_estabilidade(
        eventos, pasta, sorteio_gravado(eventos, pasta)
    )
    saida = ri.MODELOS[ri.MODELO].saida_estimada_por_evento
    return custo_na_hora(cliente, [p for *_, p in pendentes], saida)


def estabilidade(
    cliente: anthropic.Anthropic, eventos: list[dict], pasta: Path, teto: float
) -> dict:
    """Rotula de novo, um por um, os sorteados, com o mesmo pedido da primeira vez, e publica a
    concordância em `<pasta>/estabilidade.json` (sem limite: a Emenda 1 só pede publicar)."""
    sorteio = sorteio_gravado(eventos, pasta)
    pendentes, diferentes = _pedidos_da_estabilidade(eventos, pasta, sorteio)
    manifesto = ler_manifesto(pasta)
    saida = ri.MODELOS[ri.MODELO].saida_estimada_por_evento
    conferir_teto(
        manifesto, custo_na_hora(cliente, [p for *_, p in pendentes], saida), teto
    )
    gasto = 0.0
    with (pasta / "estabilidade.jsonl").open("a", encoding="utf-8") as arquivo:
        for evento, regra, parametros in pendentes:
            mensagem = cliente.messages.create(**parametros)
            linha = registro(evento, pasta, mensagem, "estabilidade", regra)
            arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")
            gasto += _custo_da_resposta(mensagem.usage, lote=False)
    segunda = ler_estabilidade(pasta)
    anterior = manifesto.get("estabilidade", {}).get("gasto", 0.0)
    manifesto["gasto_em_dolares"] = manifesto.get("gasto_em_dolares", 0.0) + gasto
    manifesto["estabilidade"] = {"eventos": len(segunda), "gasto": anterior + gasto}
    gravar_manifesto(pasta, manifesto, eventos)
    medida = ar.estabilidade(ler_rotulos(pasta), segunda, sorteio) | {
        "entradas_diferentes": diferentes
    }
    (pasta / ARQUIVO_DA_ESTABILIDADE).write_text(
        json.dumps(
            medida | {"modelo": ri.MODELO, "versao_do_prompt": ri.VERSAO_DO_PROMPT,
                      "semente": ar.SEMENTE_DA_ESTABILIDADE,
                      "sha256": {"rotulos": _sha256(arquivo_dos_rotulos(pasta)),
                                 "estabilidade": _sha256(pasta / "estabilidade.jsonl")},
                      "medido_em": datetime.now(FUSO).isoformat(timespec="seconds")},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )  # fmt: skip
    return medida


def _por_cento(valor: float | None) -> str:
    return "-" if valor is None else f"{valor:.0%}"


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "passo",
        choices=(
            "baixar",
            "estimar",
            "piloto",
            "enviar",
            "buscar",
            "identificar",
            "auditar",
            "comparar",
            "estabilidade",
            "vazamento",
        ),
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
    argumentos.add_argument(
        "--humanos",
        type=Path,
        help="rótulos do Tiago exportados (auditar; em identificar, entram na prova)",
    )
    argumentos.add_argument("--n", type=int, default=30, help="eventos do piloto")
    argumentos.add_argument(
        "--permitir-sem-texto",
        action="store_true",
        help="enviar mesmo sem o texto de todos",
    )
    argumentos.add_argument(
        "--so-prontos",
        action="store_true",
        help="enviar só os que já têm o texto; os outros vão num próximo lote",
    )
    argumentos.add_argument(
        "--texto-so-nos-fatos",
        action="store_true",
        help="só os fatos relevantes vão com texto; os outros, só com o assunto",
    )
    argumentos.add_argument("--maximo", type=int, default=500, help="downloads por vez")
    argumentos.add_argument(
        "--modelo",
        choices=tuple(ri.MODELOS),
        default=ri.MODELO,
        help=f"quem rotula (padrão: {ri.MODELO}; o conferente da Emenda 1 é {ri.MODELO_CONFERENTE})",
    )
    argumentos.add_argument(
        "--so-prova",
        action="store_true",
        help="só o conjunto de prova: os 300 primeiros da fila e o lote-leitor-v1",
    )
    argumentos.add_argument(
        "--so-estimar",
        action="store_true",
        help="identificar e estabilidade: só mostra o custo (não gasta)",
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    eventos = ler_eventos(opcoes.eventos)
    opcoes.pasta.mkdir(parents=True, exist_ok=True)
    if opcoes.passo == "comparar":
        veredito = comparar(opcoes.pasta, eventos)
        print(
            "PASSOU" if veredito.passou else "NÃO PASSOU", *veredito.motivos, sep="\n- "
        )
        return 0
    if opcoes.so_prova:
        eventos = so_prova(eventos)
    if opcoes.passo == "baixar":
        baixar(eventos, opcoes.pasta, opcoes.maximo)
        return 0
    if opcoes.passo == "vazamento":
        r = vazamento(
            eventos, opcoes.pasta, ids_de_prova(eventos), opcoes.texto_so_nos_fatos
        )
        print(f"Eventos de prova: {r['n']} (prompt v{r['versao_do_prompt']})")
        print(
            f"Com palavra que distingue a empresa: {r['com_palavra_distinta']}",
            r["palavras_distintas"],
        )
        print(
            f"Com palavra comum do nome (fica de propósito): {r['com_palavra_comum']}",
            r["palavras_comuns"],
        )
        return 0
    modelo = opcoes.modelo
    if (
        opcoes.passo in ("identificar", "auditar", "estabilidade")
        and modelo != ri.MODELO
    ):
        log.error(
            "A identificação, a estabilidade e a auditoria são do rotulador (%s).",
            ri.MODELO,
        )
        return 2
    if opcoes.passo == "auditar" and opcoes.humanos is None:
        log.error("Diga o arquivo dos rótulos do Tiago com --humanos.")
        return 2
    if opcoes.passo == "auditar":
        veredito = auditar(opcoes.pasta, ler_humanos(opcoes.humanos))
        print(
            "PASSOU" if veredito.passou else "NÃO PASSOU", *veredito.motivos, sep="\n- "
        )
        return 0
    if (
        opcoes.passo in ("estimar", "piloto", "enviar", "identificar", "estabilidade")
        and opcoes.teto_dolares is None
    ):
        log.error(
            "Diga o teto com --teto-dolares (o Tiago combinou US$ 60 em 14/10/2026)."
        )
        return 2
    cliente = ri.cliente()  # chave e workspace vêm do .env
    try:
        if opcoes.passo == "estimar":
            faltam = pendentes(eventos, opcoes.pasta, modelo)
            so_fatos = opcoes.texto_so_nos_fatos
            estimativa = estimar(cliente, faltam, opcoes.pasta, so_fatos, modelo)
            gasto = ler_manifesto(opcoes.pasta, modelo).get("gasto_em_dolares", 0.0)
            sem_texto = sum(
                texto_do_pedido(e, opcoes.pasta, so_fatos) is None for e in faltam
            )
            fatos = sum(ri.e_fato_relevante(e) for e in faltam)
            print(f"Modelo: {modelo}")
            print(
                f"Pendentes: {len(faltam)} ({fatos} fatos relevantes; {sem_texto} sem texto baixado)"
            )
            print(
                f"Estimativa pela Batch API: US$ {estimativa:.2f}; já gasto: US$ {gasto:.2f}; teto: US$ {opcoes.teto_dolares:.2f}"
            )
        elif opcoes.passo in ("identificar", "estabilidade"):
            _conferencia_da_emenda(cliente, eventos, opcoes)
        elif opcoes.passo == "piloto":
            piloto(
                cliente,
                eventos,
                opcoes.pasta,
                opcoes.n,
                opcoes.teto_dolares,
                opcoes.texto_so_nos_fatos,
                modelo,
            )
        elif opcoes.passo == "enviar":
            enviar(
                cliente,
                eventos,
                opcoes.pasta,
                opcoes.teto_dolares,
                opcoes.permitir_sem_texto,
                opcoes.texto_so_nos_fatos,
                opcoes.so_prontos,
                modelo,
            )
        else:
            buscar(cliente, eventos, opcoes.pasta, modelo)
    except TetoPassado as erro:
        log.error("%s Nada foi enviado.", erro)
        return 3
    return 0


def _conferencia_da_emenda(
    cliente: anthropic.Anthropic, eventos: list[dict], opcoes: argparse.Namespace
) -> None:
    """`identificar` e `estabilidade` (ou só a estimativa delas, com `--so-estimar`)."""
    if opcoes.passo == "identificar":
        ids = ids_de_prova(eventos)
        if opcoes.humanos is not None:  # o que o Tiago rotulou a mais é prova extra
            extra = prova_dos_humanos(ler_humanos(opcoes.humanos))
            ids += [i for i in extra if i not in set(ids)]
        so_fatos = opcoes.texto_so_nos_fatos
        if opcoes.so_estimar:
            custo = estimar_identificacao(cliente, eventos, opcoes.pasta, ids, so_fatos)
            _mostrar_estimativa(len(ids), custo, opcoes.pasta, opcoes.teto_dolares)
            return
        veredito = identificar(
            cliente, eventos, opcoes.pasta, ids, opcoes.teto_dolares, so_fatos
        )
        print("PASSOU" if veredito.passou else "NÃO PASSOU",
              f"reconheceu a empresa em {_por_cento(veredito.identificadas)} de {veredito.n}",
              *veredito.motivos, sep="\n- ")  # fmt: skip
        return
    if opcoes.so_estimar:
        custo = estimar_estabilidade(cliente, eventos, opcoes.pasta)
        _mostrar_estimativa(
            ar.EVENTOS_DA_ESTABILIDADE, custo, opcoes.pasta, opcoes.teto_dolares
        )
        return
    m = estabilidade(cliente, eventos, opcoes.pasta, opcoes.teto_dolares)
    print(
        f"Pares: {m['pares']} de {m['sorteados']} (erros: {m['erros']}; "
        f"entrada diferente: {len(m['entradas_diferentes'])})"
    )
    print(f"Nota igual: {_por_cento(m.get('nota_igual'))}; a 1 ponto: "
          f"{_por_cento(m.get('perto_nota'))}; tema igual: {_por_cento(m.get('tema_igual'))}; "
          f"assunto igual: {_por_cento(m.get('assunto_igual'))}")  # fmt: skip


def _mostrar_estimativa(eventos: int, custo: float, pasta: Path, teto: float) -> None:
    gasto = ler_manifesto(pasta).get("gasto_em_dolares", 0.0)
    print(f"Modelo: {ri.MODELO}; eventos: {eventos}")
    print(f"Estimativa (um por um, preço cheio): US$ {custo:.2f}; já gasto: US$ {gasto:.2f}; "
          f"teto: US$ {teto:.2f}")  # fmt: skip


if __name__ == "__main__":
    sys.exit(main())
