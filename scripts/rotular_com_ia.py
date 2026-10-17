"""Rotula a fila das 21h pela API do Claude (ADR 0072; plano `rotulagem-por-ia` de 14/10/2026).

    python -m scripts.rotular_com_ia baixar   --eventos eventos.json --pasta ACERVO/rotulos_ia/v1
    python -m scripts.rotular_com_ia estimar  --eventos eventos.json --pasta ... --teto-dolares 60
    python -m scripts.rotular_com_ia piloto   --eventos eventos.json --pasta ... --teto-dolares 60 --n 30
    python -m scripts.rotular_com_ia enviar   --eventos eventos.json --pasta ... --teto-dolares 60
    python -m scripts.rotular_com_ia buscar   --eventos eventos.json --pasta ...
    python -m scripts.rotular_com_ia identificar --eventos ... --pasta ... --humanos tiago.json --teto-dolares 60
    python -m scripts.rotular_com_ia auditar  --eventos ... --pasta ... --humanos tiago.json

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
# cache: escrever custa 1,25x a entrada; ler custa 0,1x
PESO_DA_ESCRITA_NO_CACHE, PESO_DA_LEITURA_DO_CACHE = 1.25, 0.1
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
    """A fila da página. Evento sem id ou com chave repetida fica de fora, com aviso (a fila v1 tem um
    sem id, na posição 3.120)."""
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
        validos.append(evento)
    return validos


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


def pendentes(eventos: list[dict], pasta: Path) -> list[dict]:
    """Os eventos ainda sem rótulo (os com erro entram de novo)."""
    feitos = _rotulados(pasta)
    return [e for e in eventos if e["id"] not in feitos]


def texto_do_pedido(evento: dict, pasta: Path, so_fatos: bool = False) -> str | None:
    """O texto que vai para o modelo. Com `so_fatos` (Tiago, 14/10/2026: se a CVM liberar menos de
    100 documentos por dia), quem não é fato relevante vai só com o assunto (""), como o guia manda a
    pessoa fazer. None: o texto ainda não foi baixado."""
    if so_fatos and not ri.e_fato_relevante(evento):
        return ""
    return texto_guardado(pasta, evento["id"])


def _parametros(evento: dict, pasta: Path, so_fatos: bool = False) -> dict:
    return ri.pedido(evento, texto_do_pedido(evento, pasta, so_fatos) or "")


def estimar(
    cliente: anthropic.Anthropic,
    eventos: list[dict],
    pasta: Path,
    so_fatos: bool = False,
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
        p = _parametros(evento, pasta, so_fatos)
        contados.append(
            cliente.messages.count_tokens(
                model=p["model"], system=p["system"], messages=p["messages"]
            ).input_tokens
        )
    sonda = _parametros(amostra[0], pasta, so_fatos)
    prefixo = cliente.messages.count_tokens(
        model=sonda["model"],
        system=sonda["system"],
        messages=[{"role": "user", "content": SONDA_DO_PREFIXO}],
    ).input_tokens
    n = len(eventos)
    media = sum(contados) / len(contados)
    prefixo = min(prefixo, media)  # a sonda tem alguns tokens a mais que o prefixo puro
    entrada = (media - prefixo) * n + prefixo * (
        PESO_DA_ESCRITA_NO_CACHE + PESO_DA_LEITURA_DO_CACHE * (n - 1)
    )
    return ri.custo_em_dolares(
        round(entrada), ri.SAIDA_ESTIMADA_POR_EVENTO * n, lote=True
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
    evento: dict,
    pasta: Path,
    mensagem: anthropic.types.Message,
    origem: str,
    so_fatos: bool = False,
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
    cliente: anthropic.Anthropic,
    eventos: list[dict],
    pasta: Path,
    n: int,
    teto: float,
    so_fatos: bool = False,
) -> int:
    """Rotula `n` eventos na hora (preço normal), para conferir formato, erros e custo real. Só
    entram eventos prontos pela regra de texto (o texto baixado, ou só o assunto com `so_fatos`)."""
    prontos = [
        e
        for e in pendentes(eventos, pasta)
        if texto_do_pedido(e, pasta, so_fatos) is not None
    ]
    escolhidos = prontos[:n]
    manifesto = ler_manifesto(pasta)
    conferir_teto(
        manifesto,
        estimar(cliente, escolhidos, pasta, so_fatos) / ri.DESCONTO_DO_LOTE,
        teto,
    )
    registros, gasto = [], 0.0
    for evento in escolhidos:
        mensagem = cliente.messages.create(**_parametros(evento, pasta, so_fatos))
        registros.append(registro(evento, pasta, mensagem, "piloto", so_fatos))
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
    so_fatos: bool = False,
    so_prontos: bool = False,
) -> str | None:
    """Manda os pendentes num lote da Batch API, se o teto permitir. Devolve o id do lote. Com
    `so_prontos`, vão só os que já têm o texto pela regra; os outros esperam o próximo lote (a CVM
    libera poucos textos por dia)."""
    manifesto = ler_manifesto(pasta)
    if any(lote.get("estado") != "gravado" for lote in manifesto.get("lotes", [])):
        raise RuntimeError(
            "Há um lote enviado e ainda não gravado: rode `buscar` primeiro."
        )
    faltam = pendentes(eventos, pasta)
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
    estimativa = estimar(cliente, faltam, pasta, so_fatos)
    conferir_teto(manifesto, estimativa, teto)
    lote = cliente.messages.batches.create(
        requests=[
            {"custom_id": chave(e["id"]), "params": _parametros(e, pasta, so_fatos)}
            for e in faltam
        ]
    )
    manifesto["lotes"] = [
        *manifesto.get("lotes", []),
        {"id": lote.id, "eventos": len(faltam), "estimativa": estimativa, "estado": "enviado",
         "texto_so_nos_fatos": so_fatos,
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
                    )
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


# --- auditoria: identificação da empresa e veredito (ADR 0072, item 3) -----------------------

TOKENS_POR_IDENTIFICACAO = (4_500, 200)  # entrada e saída, para conferir o teto antes


def ler_humanos(caminho: Path) -> dict[str, dict]:
    """Os rótulos do Tiago exportados da página (lista, ou {"rotulos": [...]}), pelo id do evento."""
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    rotulos = dados["rotulos"] if isinstance(dados, dict) else dados
    return {r["evento_id"]: r for r in rotulos}


def _prova(humanos: dict[str, dict]) -> list[str]:
    return sorted(
        i for i, h in humanos.items() if not h.get("pulado") and h.get("nota")
    )


def ler_identificacoes(pasta: Path) -> dict[str, bool] | None:
    arquivo = pasta / "identificacoes.jsonl"
    if not arquivo.exists():
        return None
    linhas = (
        json.loads(linha)
        for linha in arquivo.read_text(encoding="utf-8").splitlines()
        if linha
    )
    return {r["evento_id"]: r["identificou"] for r in linhas}


def identificar(
    cliente: anthropic.Anthropic,
    eventos: list[dict],
    pasta: Path,
    humanos: dict[str, dict],
    teto: float,
    so_fatos: bool = False,
) -> int:
    """Pergunta à IA qual é a empresa de cada evento de prova, lendo o mesmo documento anonimizado
    que o rotulador leu (use a mesma regra de texto do lote)."""
    por_id = {e["id"]: e for e in eventos}
    feitos = ler_identificacoes(pasta) or {}
    faltam = [por_id[i] for i in _prova(humanos) if i in por_id and i not in feitos]
    manifesto = ler_manifesto(pasta)
    entrada, saida = TOKENS_POR_IDENTIFICACAO
    conferir_teto(
        manifesto,
        ri.custo_em_dolares(entrada * len(faltam), saida * len(faltam), lote=False),
        teto,
    )
    gasto = 0.0
    with (pasta / "identificacoes.jsonl").open("a", encoding="utf-8") as arquivo:
        for evento in faltam:
            mensagem = cliente.messages.create(
                **ri.pedido_de_identificacao(
                    evento, texto_do_pedido(evento, pasta, so_fatos) or ""
                )
            )
            bruta = next((b.text for b in mensagem.content if b.type == "text"), "")
            palpite = ri.palpite_da_identificacao(mensagem.stop_reason, bruta)
            linha = {
                "evento_id": evento["id"],
                "palpite": palpite,
                "identificou": ar.identificou(palpite, evento.get("empresa") or ""),
            }
            arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")
            gasto += _custo_da_resposta(mensagem.usage, lote=False)
    manifesto["gasto_em_dolares"] = manifesto.get("gasto_em_dolares", 0.0) + gasto
    manifesto["identificacao"] = {"eventos": len(faltam) + len(feitos), "gasto": gasto}
    gravar_manifesto(pasta, manifesto, eventos)
    return len(faltam)


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
        help="rótulos do Tiago exportados (identificar e auditar)",
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
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    eventos = ler_eventos(opcoes.eventos)
    opcoes.pasta.mkdir(parents=True, exist_ok=True)
    if opcoes.passo == "baixar":
        baixar(eventos, opcoes.pasta, opcoes.maximo)
        return 0
    if opcoes.passo in ("identificar", "auditar") and opcoes.humanos is None:
        log.error("Diga o arquivo dos rótulos do Tiago com --humanos.")
        return 2
    if opcoes.passo == "auditar":
        veredito = auditar(opcoes.pasta, ler_humanos(opcoes.humanos))
        print(
            "PASSOU" if veredito.passou else "NÃO PASSOU", *veredito.motivos, sep="\n- "
        )
        return 0
    if (
        opcoes.passo in ("estimar", "piloto", "enviar", "identificar")
        and opcoes.teto_dolares is None
    ):
        log.error(
            "Diga o teto com --teto-dolares (o Tiago combinou US$ 60 em 14/10/2026)."
        )
        return 2
    cliente = ri.cliente()  # chave e workspace vêm do .env
    try:
        if opcoes.passo == "estimar":
            faltam = pendentes(eventos, opcoes.pasta)
            so_fatos = opcoes.texto_so_nos_fatos
            estimativa = estimar(cliente, faltam, opcoes.pasta, so_fatos)
            gasto = ler_manifesto(opcoes.pasta).get("gasto_em_dolares", 0.0)
            sem_texto = sum(
                texto_do_pedido(e, opcoes.pasta, so_fatos) is None for e in faltam
            )
            print(f"Pendentes: {len(faltam)} ({sem_texto} sem texto baixado)")
            print(
                f"Estimativa pela Batch API: US$ {estimativa:.2f}; já gasto: US$ {gasto:.2f}; teto: US$ {opcoes.teto_dolares:.2f}"
            )
        elif opcoes.passo == "identificar":
            identificar(
                cliente,
                eventos,
                opcoes.pasta,
                ler_humanos(opcoes.humanos),
                opcoes.teto_dolares,
                opcoes.texto_so_nos_fatos,
            )
        elif opcoes.passo == "piloto":
            piloto(
                cliente,
                eventos,
                opcoes.pasta,
                opcoes.n,
                opcoes.teto_dolares,
                opcoes.texto_so_nos_fatos,
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
            )
        else:
            buscar(cliente, eventos, opcoes.pasta)
    except TetoPassado as erro:
        log.error("%s Nada foi enviado.", erro)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
