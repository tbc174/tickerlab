"""Escreve as análises das fichas pela API do Claude, confere e guarda (ADR 0100; plano de 18/10/2026).

    python -m scripts.escrever_analises estimar  --entradas cpfl.json --pasta P --teto-dolares 3
    python -m scripts.escrever_analises piloto   --entradas cpfl.json --pasta P --teto-dolares 3 \
        --modelos claude-haiku-5-5,claude-sonnet-5-5,claude-opus-5-5
    python -m scripts.escrever_analises enviar   --entradas *.json --pasta P --teto-dolares 50 \
        --modelos claude-sonnet-5-5
    python -m scripts.escrever_analises buscar   --entradas *.json --pasta P
    python -m scripts.escrever_analises cegas    --entradas *.json --pasta P --teto-dolares 3
    python -m scripts.escrever_analises conferir --entradas *.json --pasta P --modelo claude-sonnet-5-5
    python -m scripts.escrever_analises revisar  --entradas *.json --pasta P --notas PASTA_DO_OBSIDIAN
    python -m scripts.escrever_analises aprovar  --pasta P --notas PASTA_DO_OBSIDIAN

Cada entrada é a ficha já serializada (`entrada.entrada_da_ficha`, em JSON). `estimar` conta os
tokens pela API (não gasta) e mostra o custo da escrita e da porta 2 por modelo. `piloto` escreve na
hora (preço cheio); `enviar` e `buscar` fazem o mesmo pela Batch API (metade do preço; até 24 h).
`cegas` é a porta 2: outro modelo confere cada frase sem saber quem escreveu. `conferir` roda a
porta 1 e monta a análise (sem API): parte reprovada vira molde, e sem a porta 2 nada do modelo vai
ao ar. `revisar` escreve a nota da porta 3 no Obsidian e `aprovar` lê o veredito do Tiago e conta o
critério de saída da 0100.

**O teto vale para tudo:** nenhum passo gasta se o gasto já feito mais a estimativa passar do teto.
Resposta guardada (mesma entrada, mesmo guia) nunca é paga de novo. Em `<pasta>`: `respostas/` (a
resposta bruta de cada escritor), `cegas/` (o veredito da porta 2), `analises/` (o texto montado com
a linhagem inteira, o que vai para o VPS) e `manifesto.json` (gasto, pilotos, lotes e os vereditos da
porta 3 em ordem). A chave fica em `ANTHROPIC_API_KEY` (nunca no código).
"""

import argparse
import hashlib
import json
import logging
import re
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic

from scripts.rotular_com_ia import (
    FUSO,
    PESO_DA_ESCRITA_NO_CACHE,
    TetoPassado,
    conferir_teto,
)
from src import rotulos_ia as ri
from src.analise_escrita import entrada as en
from src.analise_escrita import montagem, porta2, porta3, saida
from src.analise_escrita import pedido as pe
from src.analise_escrita.molde import VERSAO_DO_MOLDE, molde

log = logging.getLogger("tickerlab.analise_escrita")

__all__ = ["TetoPassado"]

# tokens de saída da porta 2, só para a estimativa: ~200 frases com rótulo, veredito e motivo curto
LOTE_TERMINADO = "ended"
SEM_A_PORTA_2 = "a porta 2 não conferiu esta resposta"
_FORA_DO_NOME = re.compile(r"[^\w .()-]")


# --- arquivos -------------------------------------------------------------------------------------
def _algarismos(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


def chave(entrada: dict[str, Any]) -> str:
    """O CNPJ só com os algarismos: nome de arquivo e `custom_id` do lote."""
    return _algarismos(entrada["cnpj"])


def arquivo_da_resposta(pasta: Path, entrada: dict[str, Any], modelo: str) -> Path:
    return pasta / "respostas" / f"{chave(entrada)}.{modelo}.json"


def arquivo_da_cega(pasta: Path, entrada: dict[str, Any], modelo: str) -> Path:
    return pasta / "cegas" / f"{chave(entrada)}.{modelo}.json"


def arquivo_da_analise(pasta: Path, entrada: dict[str, Any]) -> Path:
    return pasta / "analises" / f"{chave(entrada)}.json"


def _ler(arquivo: Path) -> dict[str, Any] | None:
    if not arquivo.exists():
        return None
    return json.loads(arquivo.read_text(encoding="utf-8"))


def _gravar(arquivo: Path, dado: dict[str, Any]) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(dado, ensure_ascii=False, indent=2), encoding="utf-8")


def _agora() -> str:
    return datetime.now(FUSO).isoformat(timespec="seconds")


def ler_entradas(caminhos: Sequence[Path]) -> list[dict[str, Any]]:
    """Lê as entradas e barra, antes de qualquer envio à API, a que traz nome de pessoa (D4)."""
    entradas = [json.loads(c.read_text(encoding="utf-8")) for c in caminhos]
    for caminho, entrada in zip(caminhos, entradas, strict=True):
        try:
            en.conferir_sem_nome_com_cargo(entrada)
        except en.PessoaNaEntradaError as erro:
            raise ValueError(f"{caminho.name}: {erro}") from erro
    return entradas


def ler_manifesto(pasta: Path) -> dict[str, Any]:
    return _ler(pasta / "manifesto.json") or {
        "gasto_em_dolares": 0.0,
        "pilotos": [],
        "lotes": [],
        "porta3": [],
    }


def gravar_manifesto(pasta: Path, manifesto: dict[str, Any]) -> None:
    manifesto |= {
        "versao_do_guia": pe.VERSAO_DO_GUIA,
        "versao_do_molde": VERSAO_DO_MOLDE,
        "atualizado_em": _agora(),
    }
    _gravar(pasta / "manifesto.json", manifesto)


def _somar_gasto(manifesto: dict[str, Any], gasto: float) -> None:
    manifesto["gasto_em_dolares"] = manifesto.get("gasto_em_dolares", 0.0) + gasto


def _pagar(pasta: Path, manifesto: dict[str, Any], custo: float) -> None:
    """Grava o gasto a cada resposta: se a próxima chamada cair, o teto já conta esta."""
    _somar_gasto(manifesto, custo)
    gravar_manifesto(pasta, manifesto)


def _mensagem_completa(
    cliente: anthropic.Anthropic, parametros: dict[str, Any]
) -> anthropic.types.Message:
    """A resposta inteira por streaming: com o `max_tokens` da análise, a SDK recusa o `create`
    (o pedido poderia passar de 10 minutos)."""
    with cliente.messages.stream(**parametros) as fluxo:
        return fluxo.get_final_message()


def resposta_guardada(
    pasta: Path, entrada: dict[str, Any], modelo: str
) -> dict[str, Any] | None:
    """A resposta que vale para a entrada de hoje e o guia de hoje (outra entrada: escreve de novo)."""
    registro = _ler(arquivo_da_resposta(pasta, entrada, modelo))
    if registro is None or "erro" in registro:
        return None
    if registro["hash_da_entrada"] != en.hash_da_entrada(entrada):
        return None
    if registro["versao_do_guia"] != pe.VERSAO_DO_GUIA:
        return None
    if _cortada_com_limite_menor(registro):
        return None
    return registro


def _cortada_com_limite_menor(registro: dict[str, Any]) -> bool:
    """Resposta cortada no limite vale de novo só se o limite subiu (com o mesmo, cortaria igual)."""
    limite = registro.get("max_tokens", 0)
    return registro["stop_reason"] == pe.CORTADA and limite < pe.MAX_TOKENS_DA_RESPOSTA


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# --- custo ----------------------------------------------------------------------------------------
def _tokens(usage: anthropic.types.Usage) -> dict[str, int]:
    return {
        "entrada": usage.input_tokens or 0,
        "saida": usage.output_tokens or 0,
        "cache_escrito": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        "cache_lido": getattr(usage, "cache_read_input_tokens", 0) or 0,
    }


def custo_da_resposta(tokens: dict[str, int], modelo: str, lote: bool) -> float:
    leitura = pe.modelo_conhecido(modelo).leitura_do_cache
    entrada = (
        tokens["entrada"]
        + PESO_DA_ESCRITA_NO_CACHE * tokens["cache_escrito"]
        + leitura * tokens["cache_lido"]
    )
    return pe.custo_em_dolares(round(entrada), tokens["saida"], modelo, lote)


def _custo_estimado(
    cliente: anthropic.Anthropic, parametros: dict[str, Any], lote: bool
) -> float:
    """O pior caso, para o teto nunca furar: a entrada contada pela API (não gasta), toda pelo preço
    de escrever no cache, e a saída do `max_tokens` inteiro (o raciocínio conta nela e não aparece
    no texto)."""
    contados = cliente.messages.count_tokens(
        model=parametros["model"],
        system=parametros["system"],
        messages=parametros["messages"],
    ).input_tokens
    entrada = round(contados * PESO_DA_ESCRITA_NO_CACHE)
    return pe.custo_em_dolares(
        entrada, parametros["max_tokens"], parametros["model"], lote
    )


def _tamanho_do_texto(modelo: str) -> int:
    """Os tokens do texto que o escritor deve entregar (só o texto, sem o raciocínio)."""
    return pe.modelo_conhecido(modelo).saida_estimada_por_evento


def _estimativa_da_escrita(
    cliente: anthropic.Anthropic,
    pares: list[tuple[dict[str, Any], str]],
    lote: bool,
) -> float:
    return sum(_custo_estimado(cliente, pe.pedido(e, m), lote) for e, m in pares)


def _estimativa_da_cega(
    cliente: anthropic.Anthropic,
    entrada: dict[str, Any],
    analise: saida.Analise,
    escritor: str,
    texto_a_mais: int = 0,
) -> float:
    """`texto_a_mais`: antes da escrita, o texto ainda não existe; o molde faz as vezes dele e a
    saída estimada do escritor entra por cima (de novo, acima do real)."""
    parametros = porta2.pedido(analise, entrada, porta2.conferente(escritor))
    custo = _custo_estimado(cliente, parametros, False)
    preco = pe.modelo_conhecido(parametros["model"])
    return custo + texto_a_mais * PESO_DA_ESCRITA_NO_CACHE * preco.entrada / 1_000_000


def estimar(
    cliente: anthropic.Anthropic,
    entradas: list[dict[str, Any]],
    pasta: Path,
    modelos: Sequence[str],
    lote: bool = False,
) -> dict[str, float]:
    """O custo projetado em US$ de cada escritor: a escrita do que falta mais a porta 2 dela."""
    custos = {}
    for modelo in modelos:
        pares = _a_escrever(entradas, pasta, [modelo])
        cegas_ = sum(
            _estimativa_da_cega(cliente, e, molde(e), modelo, _tamanho_do_texto(modelo))
            for e, _ in pares
        )
        custos[modelo] = _estimativa_da_escrita(cliente, pares, lote) + cegas_
    return custos


# --- escrever: piloto, enviar e buscar ------------------------------------------------------------
def _a_escrever(
    entradas: list[dict[str, Any]], pasta: Path, modelos: Sequence[str]
) -> list[tuple[dict[str, Any], str]]:
    return [
        (e, m)
        for e in entradas
        for m in modelos
        if resposta_guardada(pasta, e, m) is None
    ]


def _texto_da_mensagem(mensagem: anthropic.types.Message) -> str:
    return next((b.text for b in mensagem.content if b.type == "text"), "")


def _registro_da_resposta(
    entrada: dict[str, Any],
    modelo: str,
    mensagem: anthropic.types.Message,
    origem: str,
    lote: bool,
    hash_da_entrada: str | None = None,
) -> dict[str, Any]:
    """A linhagem da resposta (0100, item 10): de que entrada, por qual modelo e guia, a que custo."""
    tokens = _tokens(mensagem.usage)
    return {
        "cnpj": entrada["cnpj"],
        "empresa": entrada["empresa"],
        "modelo": modelo,
        "versao_do_guia": pe.VERSAO_DO_GUIA,
        "versao_do_molde": VERSAO_DO_MOLDE,
        "hash_da_entrada": hash_da_entrada or en.hash_da_entrada(entrada),
        "origem": origem,
        "escrito_em": _agora(),
        "stop_reason": mensagem.stop_reason,
        "resposta_bruta": _texto_da_mensagem(mensagem),
        "max_tokens": pe.MAX_TOKENS_DA_RESPOSTA,
        "blocos": dict(Counter(bloco.type for bloco in mensagem.content)),
        "tokens": tokens,
        "custo_em_dolares": custo_da_resposta(tokens, modelo, lote),
    }


def piloto(
    cliente: anthropic.Anthropic,
    entradas: list[dict[str, Any]],
    pasta: Path,
    modelos: Sequence[str],
    teto: float,
) -> int:
    """Escreve na hora (preço cheio) o que ainda não tem resposta guardada. Devolve quantas escreveu."""
    pares = _a_escrever(entradas, pasta, modelos)
    if not pares:
        return 0
    manifesto = ler_manifesto(pasta)
    conferir_teto(manifesto, _estimativa_da_escrita(cliente, pares, False), teto)
    gasto = 0.0
    for entrada, modelo in pares:
        mensagem = _mensagem_completa(cliente, pe.pedido(entrada, modelo))
        registro = _registro_da_resposta(entrada, modelo, mensagem, "piloto", False)
        _gravar(arquivo_da_resposta(pasta, entrada, modelo), registro)
        _pagar(pasta, manifesto, registro["custo_em_dolares"])
        gasto += registro["custo_em_dolares"]
    manifesto["pilotos"] = [
        *manifesto.get("pilotos", []),
        {"respostas": len(pares), "gasto": gasto, "em": _agora()},
    ]
    gravar_manifesto(pasta, manifesto)
    log.info("Piloto: %s respostas, US$ %.4f", len(pares), gasto)
    return len(pares)


def enviar(
    cliente: anthropic.Anthropic,
    entradas: list[dict[str, Any]],
    pasta: Path,
    modelo: str,
    teto: float,
) -> str | None:
    """Manda o que falta num lote da Batch API, se o teto permitir. Devolve o id do lote."""
    manifesto = ler_manifesto(pasta)
    if any(lote.get("estado") != "gravado" for lote in manifesto.get("lotes", [])):
        raise RuntimeError(
            "Há um lote enviado e ainda não gravado: rode `buscar` primeiro."
        )
    pares = _a_escrever(entradas, pasta, [modelo])
    if not pares:
        log.info("Nada pendente.")
        return None
    estimativa = _estimativa_da_escrita(cliente, pares, True)
    conferir_teto(manifesto, estimativa, teto)
    lote = cliente.messages.batches.create(
        requests=[
            {"custom_id": chave(e), "params": pe.pedido(e, modelo)} for e, _ in pares
        ]
    )
    manifesto["lotes"] = [
        *manifesto.get("lotes", []),
        {"id": lote.id, "modelo": modelo, "estimativa": estimativa, "estado": "enviado",
         "hashes": {chave(e): en.hash_da_entrada(e) for e, _ in pares},
         "enviado_em": _agora()},
    ]  # fmt: skip
    gravar_manifesto(pasta, manifesto)
    log.info("Lote %s enviado: %s fichas, US$ %.2f", lote.id, len(pares), estimativa)
    return lote.id


def _gravar_resultado(
    resultado: anthropic.types.messages.MessageBatchIndividualResponse,
    lote: dict[str, Any],
    por_chave: dict[str, dict[str, Any]],
    pasta: Path,
) -> float:
    entrada, modelo = por_chave[resultado.custom_id], lote["modelo"]
    destino = arquivo_da_resposta(pasta, entrada, modelo)
    if resultado.result.type != "succeeded":
        _gravar(destino, {"erro": f"lote: {resultado.result.type}", "lote": lote["id"]})
        return 0.0
    hash_ = lote["hashes"][resultado.custom_id]
    registro = _registro_da_resposta(
        entrada, modelo, resultado.result.message, f"lote {lote['id']}", True, hash_
    )
    _gravar(destino, registro)
    return registro["custo_em_dolares"]


def buscar(
    cliente: anthropic.Anthropic, entradas: list[dict[str, Any]], pasta: Path
) -> int:
    """Grava as respostas dos lotes que terminaram. Devolve quantas gravou."""
    manifesto = ler_manifesto(pasta)
    por_chave = {chave(e): e for e in entradas}
    gravadas = 0
    for lote in manifesto.get("lotes", []):
        if lote.get("estado") == "gravado":
            continue
        if (
            cliente.messages.batches.retrieve(lote["id"]).processing_status
            != LOTE_TERMINADO
        ):
            log.info("Lote %s ainda processando.", lote["id"])
            continue
        gasto = 0.0
        for resultado in cliente.messages.batches.results(lote["id"]):
            gasto += _gravar_resultado(resultado, lote, por_chave, pasta)
            gravadas += 1
        lote |= {"estado": "gravado", "gasto": gasto}
        _somar_gasto(manifesto, gasto)
    gravar_manifesto(pasta, manifesto)
    return gravadas


# --- porta 2: às cegas ----------------------------------------------------------------------------
def _analise_da_resposta(registro: dict[str, Any]) -> saida.Analise | None:
    try:
        dados = pe.ler_resposta(registro["stop_reason"], registro["resposta_bruta"])
        return saida.ler_analise(dados)
    except saida.RespostaInvalidaError:
        return None  # fora do formato: vira molde na conferência, sem gastar a porta 2


def _cega_valida(
    pasta: Path, entrada: dict[str, Any], modelo: str, registro: dict[str, Any]
) -> dict[str, Any] | None:
    cega = _ler(arquivo_da_cega(pasta, entrada, modelo))
    if cega and cega["hash_da_resposta"] == _sha256(registro["resposta_bruta"]):
        return cega
    return None


def _a_conferir(
    entradas: list[dict[str, Any]], pasta: Path, modelos: Sequence[str]
) -> Iterator[tuple[dict[str, Any], str, saida.Analise, dict[str, Any]]]:
    for entrada in entradas:
        for modelo in modelos:
            registro = resposta_guardada(pasta, entrada, modelo)
            if registro is None or _cega_valida(pasta, entrada, modelo, registro):
                continue
            analise = _analise_da_resposta(registro)
            if analise is not None:
                yield entrada, modelo, analise, registro


def _registro_da_cega(
    analise: saida.Analise,
    escritor: str,
    registro: dict[str, Any],
    mensagem: anthropic.types.Message,
) -> dict[str, Any]:
    conferente = porta2.conferente(escritor)
    bruta = _texto_da_mensagem(mensagem)
    veredito = porta2.ler_veredito(mensagem.stop_reason, bruta, analise)
    tokens = _tokens(mensagem.usage)
    return {
        "escritor": escritor,
        "conferente": conferente,
        "hash_da_resposta": _sha256(registro["resposta_bruta"]),
        "conferido_em": _agora(),
        "stop_reason": mensagem.stop_reason,
        "resposta_bruta": bruta,
        "reprovadas": sorted(veredito.reprovadas),
        "motivo": veredito.motivo,
        "frases": [list(f) for f in veredito.frases],
        "tokens": tokens,
        "custo_em_dolares": custo_da_resposta(tokens, conferente, False),
    }


def cegas(
    cliente: anthropic.Anthropic,
    entradas: list[dict[str, Any]],
    pasta: Path,
    modelos: Sequence[str],
    teto: float,
) -> int:
    """A porta 2 em cada resposta guardada que ainda não passou por ela. Devolve quantas conferiu."""
    pendentes = list(_a_conferir(entradas, pasta, modelos))
    if not pendentes:
        return 0
    manifesto = ler_manifesto(pasta)
    estimativa = sum(_estimativa_da_cega(cliente, e, a, m) for e, m, a, _ in pendentes)
    conferir_teto(manifesto, estimativa, teto)
    gasto = 0.0
    for entrada, modelo, analise, registro in pendentes:
        parametros = porta2.pedido(analise, entrada, porta2.conferente(modelo))
        mensagem = _mensagem_completa(cliente, parametros)
        cega = _registro_da_cega(analise, modelo, registro, mensagem)
        _gravar(arquivo_da_cega(pasta, entrada, modelo), cega)
        _pagar(pasta, manifesto, cega["custo_em_dolares"])
        gasto += cega["custo_em_dolares"]
    gravar_manifesto(pasta, manifesto)
    log.info("Porta 2: %s respostas, US$ %.4f", len(pendentes), gasto)
    return len(pendentes)


# --- conferir e montar (sem API) ------------------------------------------------------------------
def _porta2_da_linhagem(cega: dict[str, Any] | None) -> dict[str, Any] | None:
    if cega is None:
        return None
    campos = (
        "conferente",
        "reprovadas",
        "motivo",
        "frases",
        "tokens",
        "custo_em_dolares",
    )
    return {c: cega[c] for c in campos}


def _porta3_mantida(
    anterior: dict[str, Any] | None, registro: dict[str, Any]
) -> dict[str, Any] | None:
    """O veredito da porta 3 só continua valendo para a mesma resposta da mesma entrada."""
    if anterior is None:
        return None
    linhagem = anterior["linhagem"]
    mesma = linhagem.get("resposta_bruta") == registro["resposta_bruta"]
    return linhagem.get("porta3") if mesma else None


def _montar(
    entrada: dict[str, Any], pasta: Path, modelo: str
) -> tuple[montagem.Montagem, dict[str, Any] | None, dict[str, Any] | None]:
    registro = _ler(arquivo_da_resposta(pasta, entrada, modelo))
    if registro is None or "erro" in registro:
        return montagem.analise_final(None, entrada, None), None, None
    cega = _cega_valida(pasta, entrada, modelo, registro)
    reprovadas = cega["reprovadas"] if cega else saida.PARTES  # nunca aprova por falta
    m = montagem.da_resposta_bruta(
        registro["stop_reason"],
        registro["resposta_bruta"],
        entrada,
        registro["hash_da_entrada"],
        reprovadas,
    )
    return m, registro, cega


def _linhagem(
    m: montagem.Montagem,
    registro: dict[str, Any] | None,
    cega: dict[str, Any] | None,
    porta3_: dict[str, Any] | None,
) -> dict[str, Any]:
    da_resposta = {
        k: v for k, v in (registro or {}).items() if k not in ("cnpj", "empresa")
    }
    porta1 = [asdict(r) for r in m.conferencia.reprovacoes] if m.conferencia else None
    motivo = m.motivo or (SEM_A_PORTA_2 if registro and cega is None else None)
    return da_resposta | {
        "versao_do_molde": VERSAO_DO_MOLDE,
        "motivo": motivo,
        "porta1": porta1,
        "porta2": _porta2_da_linhagem(cega),
        "porta3": porta3_,
    }


def conferir(entradas: list[dict[str, Any]], pasta: Path, modelo: str) -> int:
    """Porta 1 e montagem de cada entrada com o texto do `modelo`; grava `analises/`."""
    for entrada in entradas:
        m, registro, cega = _montar(entrada, pasta, modelo)
        destino = arquivo_da_analise(pasta, entrada)
        porta3_ = _porta3_mantida(_ler(destino), registro) if registro else None
        analise = {
            "cnpj": entrada["cnpj"],
            "empresa": entrada["empresa"],
            "corte": entrada[
                "corte"
            ],  # o app remonta a ficha neste corte para conferir o hash
            "hash_da_entrada_atual": en.hash_da_entrada(entrada),
            "montada_em": _agora(),
            "publicavel": bool(porta3_ and porta3_["veredito"] == porta3.APROVADO),
            "analise": m.analise.como_dict(),
            "linhagem": _linhagem(m, registro, cega, porta3_),
        }
        _gravar(destino, analise)
    return len(entradas)


# --- porta 3: revisar e aprovar -------------------------------------------------------------------
def _arquivo_da_nota(notas: Path, entrada: dict[str, Any]) -> Path:
    nome = _FORA_DO_NOME.sub("", entrada["empresa"]).strip()
    return notas / f"{nome} {chave(entrada)}.md"


def _nota(guardada: dict[str, Any], entrada: dict[str, Any]) -> str:
    """A nota mostra o texto que iria ao ar, ligado à entrada de hoje (o veredito vale só para ela)."""
    linhagem = guardada["linhagem"] | {
        "hash_da_entrada": guardada["hash_da_entrada_atual"]
    }
    return porta3.nota(saida.ler_analise(guardada["analise"]), entrada, linhagem)


def revisar(entradas: list[dict[str, Any]], pasta: Path, notas: Path) -> list[Path]:
    """Uma nota por análise ainda sem veredito; nota que já existe nunca é sobrescrita."""
    escritas = []
    for entrada in entradas:
        guardada = _ler(arquivo_da_analise(pasta, entrada))
        destino = _arquivo_da_nota(notas, entrada)
        if guardada is None or guardada["linhagem"]["porta3"] or destino.exists():
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(_nota(guardada, entrada), encoding="utf-8")
        escritas.append(destino)
    return escritas


def _registrar_veredito(
    pasta: Path, revisao: porta3.Revisao, manifesto: dict[str, Any]
) -> None:
    arquivo = pasta / "analises" / f"{_algarismos(revisao.cnpj)}.json"
    guardada = _ler(arquivo)
    if guardada is None or guardada["hash_da_entrada_atual"] != revisao.hash_da_entrada:
        log.warning("Veredito de %s sem a análise de mesma entrada.", revisao.cnpj)
        return
    vistos = {(v["cnpj"], v["hash_da_entrada"]) for v in manifesto["porta3"]}
    if (revisao.cnpj, revisao.hash_da_entrada) in vistos:
        return
    veredito = {"veredito": revisao.veredito, "motivo": revisao.motivo, "em": _agora()}
    guardada["linhagem"]["porta3"] = veredito
    guardada["publicavel"] = revisao.veredito == porta3.APROVADO
    _gravar(arquivo, guardada)
    manifesto["porta3"].append(
        {"cnpj": revisao.cnpj, "hash_da_entrada": revisao.hash_da_entrada} | veredito
    )


def aprovar(pasta: Path, notas: Path) -> porta3.Saida:
    """Lê os vereditos das notas, grava na linhagem e conta o critério de saída da 0100."""
    manifesto = ler_manifesto(pasta)
    manifesto.setdefault("porta3", [])
    for arquivo in sorted(notas.glob("*.md")):
        revisao = porta3.ler_revisao(arquivo.read_text(encoding="utf-8"))
        if revisao is not None:
            _registrar_veredito(pasta, revisao, manifesto)
    gravar_manifesto(pasta, manifesto)
    return porta3.criterio_de_saida([v["veredito"] for v in manifesto["porta3"]])


# --- linha de comando -----------------------------------------------------------------------------
GASTAM = ("estimar", "piloto", "enviar", "cegas")
PASSOS = (*GASTAM, "buscar", "conferir", "revisar", "aprovar")


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    analisador = argparse.ArgumentParser(
        description="Escreve, confere e guarda as análises"
    )
    passos = analisador.add_subparsers(dest="passo", required=True)
    for nome in PASSOS:
        passo = passos.add_parser(nome)
        passo.add_argument("--pasta", type=Path, required=True)
        passo.add_argument("--entradas", type=Path, nargs="+", default=[])
        passo.add_argument("--modelos", default=",".join(pe.ESCRITORES))
        passo.add_argument("--modelo", default=pe.SONNET)
        passo.add_argument("--notas", type=Path)
        passo.add_argument("--teto-dolares", type=float, required=nome in GASTAM)
    return analisador.parse_args(argv)


def _mostrar_estimativa(custos: dict[str, float], teto: float, gasto: float) -> None:
    for modelo, custo in custos.items():
        print(f"{modelo}: US$ {custo:.2f} (escrita e porta 2)")
    total = sum(custos.values())
    situacao = "cabe" if gasto + total <= teto else "PASSA"
    print(
        f"Total US$ {total:.2f}; já gasto US$ {gasto:.2f}; {situacao} no teto de US$ {teto:.2f}"
    )


def _rodar(args: argparse.Namespace, entradas: list[dict[str, Any]]) -> None:
    modelos = [m.strip() for m in args.modelos.split(",") if m.strip()]
    if args.passo == "conferir":
        conferir(entradas, args.pasta, args.modelo)
        return
    if args.passo in ("revisar", "aprovar"):
        if args.notas is None:
            raise SystemExit("--notas é obrigatório em revisar e aprovar")
        if args.passo == "revisar":
            print(f"{len(revisar(entradas, args.pasta, args.notas))} notas escritas")
        else:
            print(aprovar(args.pasta, args.notas))
        return
    cliente = ri.cliente()
    if args.passo == "estimar":
        gasto = ler_manifesto(args.pasta).get("gasto_em_dolares", 0.0)
        custos = estimar(cliente, entradas, args.pasta, modelos)
        _mostrar_estimativa(custos, args.teto_dolares, gasto)
    elif args.passo == "piloto":
        print(
            f"{piloto(cliente, entradas, args.pasta, modelos, args.teto_dolares)} respostas"
        )
    elif args.passo == "enviar":
        print(enviar(cliente, entradas, args.pasta, args.modelo, args.teto_dolares))
    elif args.passo == "buscar":
        print(f"{buscar(cliente, entradas, args.pasta)} respostas gravadas")
    else:
        print(
            f"{cegas(cliente, entradas, args.pasta, modelos, args.teto_dolares)} conferidas"
        )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _argumentos(argv)
    for modelo in args.modelos.split(","):
        pe.modelo_conhecido(modelo.strip())
    try:
        _rodar(args, ler_entradas(args.entradas))
    except TetoPassado as erro:
        print(erro, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
