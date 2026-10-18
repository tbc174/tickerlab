"""A extração de M&A medida na amostra de ouro (série 1, PR 2 do plano da base de M&A).

    python -m scripts.extrair_ma estimar --ouro CSV --textos P --saida S [--modelo M]   (sem API)
    python -m scripts.extrair_ma enviar  --ouro CSV --textos P --saida S --teto-dolares 3 [--modelo M]
    python -m scripts.extrair_ma buscar  --ouro CSV --textos P --saida S [--modelo M]
    python -m scripts.extrair_ma medir   --ouro CSV --textos P --saida S                (sem API)

`--ouro` é a amostra de ouro (`tickerlab-fontes/ma/amostra_de_ouro_candidatas.csv`); `--textos`, a
pasta com o texto de cada documento (`<protocolo>.txt`). `enviar` manda um lote da Batch API (Haiku
5.5; `--modelo claude-sonnet-5-5` para a segunda leitura) e **gasta API**: só roda com o "pode" do
Tiago para o valor, e o teto (`--teto-dolares`, obrigatório) trava o envio antes de gastar. Cada
resposta fica guardada bruta, com tokens e custo; `medir` confere tudo de novo (`base.ma_extracao`)
e compara com a amostra, por modelo, com o custo por documento e as divergências entre os dois.
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
import pandas as pd

from base import ma_extracao as mx
from scripts.rotular_com_ia import TetoPassado

log = logging.getLogger("tickerlab.extrair_ma")
FUSO = ZoneInfo("America/Sao_Paulo")
VARIAVEL_DA_CHAVE = "ANTHROPIC_API_KEY_MA"
MODELOS = (mx.MODELO, mx.CONFERENTE)


@dataclass(frozen=True)
class Documento:
    protocolo: str
    publico_em: date
    texto: str


@dataclass(frozen=True)
class Medida:
    modelo: str
    placar: pd.DataFrame
    lidos: int
    custo_por_documento: float
    leituras: dict[str, mx.LeituraDaOperacao]
    com_descarte: int
    para_revisao: int


def _ouro(arquivo: Path) -> pd.DataFrame:
    return pd.read_csv(arquivo, sep=";", encoding="utf-8-sig", dtype=str)


def documentos(ouro: Path, textos: Path) -> list[Documento]:
    """Os documentos da amostra com texto guardado (o vazio fica de fora: não há o que ler)."""
    achados = []
    for linha in _ouro(ouro).to_dict("records"):
        arquivo = textos / f"{linha['Protocolo_Entrega']}.txt"
        texto = arquivo.read_text(encoding="utf-8") if arquivo.exists() else ""
        if texto.strip():
            achados.append(
                Documento(
                    linha["Protocolo_Entrega"],
                    date.fromisoformat(linha["Data_Entrega"][:10]),
                    texto,
                )
            )
    return achados


# --- leituras e manifesto guardados --------------------------------------------------------------


def _arquivo_das_leituras(saida: Path, modelo: str) -> Path:
    return saida / f"leituras-{modelo}.jsonl"


def _arquivo_do_manifesto(saida: Path, modelo: str) -> Path:
    return saida / f"manifesto-{modelo}.json"


def ler_leituras(saida: Path, modelo: str) -> dict[str, dict]:
    arquivo = _arquivo_das_leituras(saida, modelo)
    if not arquivo.exists():
        return {}
    registros = (
        json.loads(linha) for linha in arquivo.read_text(encoding="utf-8").splitlines()
    )
    return {r["protocolo"]: r for r in registros}


def ler_manifesto(saida: Path, modelo: str) -> dict:
    arquivo = _arquivo_do_manifesto(saida, modelo)
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}


def _gravar_manifesto(saida: Path, modelo: str, manifesto: dict) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    _arquivo_do_manifesto(saida, modelo).write_text(
        json.dumps(manifesto, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _acrescentar(saida: Path, modelo: str, registros: list[dict]) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    with _arquivo_das_leituras(saida, modelo).open("a", encoding="utf-8") as arquivo:
        for registro in registros:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


def pendentes(ouro: Path, textos: Path, saida: Path, modelo: str) -> list[Documento]:
    """Os documentos sem leitura boa deste modelo (os com erro entram de novo)."""
    feitas = ler_leituras(saida, modelo)
    return [
        d
        for d in documentos(ouro, textos)
        if d.protocolo not in feitas or "erro" in feitas[d.protocolo]
    ]


def conferir_teto(manifesto: dict, estimativa: float, teto: float) -> None:
    gasto = manifesto.get("gasto_em_dolares", 0.0)
    if gasto + estimativa > teto:
        raise TetoPassado(
            f"Gasto já feito US$ {gasto:.2f} + estimativa US$ {estimativa:.2f} passa do teto US$ {teto:.2f}."
        )


def _custo(usage: anthropic.types.Usage, modelo: str) -> float:
    entrada = (
        (usage.input_tokens or 0)
        + mx.PESO_DA_ESCRITA_NO_CACHE * (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        + mx.preco(modelo).leitura_do_cache * (getattr(usage, "cache_read_input_tokens", 0) or 0)
    )  # fmt: skip
    return mx.custo_em_dolares(entrada, usage.output_tokens or 0, modelo=modelo)


# --- enviar e buscar (gastam API) ------------------------------------------------------------------


def enviar(
    cliente: anthropic.Anthropic, ouro: Path, textos: Path, saida: Path, modelo: str, teto: float
) -> str | None:  # fmt: skip
    """Manda os pendentes num lote da Batch API, se o teto permitir. Devolve o id do lote."""
    manifesto = ler_manifesto(saida, modelo)
    if any(lote["estado"] != "gravado" for lote in manifesto.get("lotes", [])):
        raise RuntimeError(
            "Há um lote enviado e ainda não gravado: rode `buscar` primeiro."
        )
    fila = pendentes(ouro, textos, saida, modelo)
    if not fila:
        log.info("Nada pendente para %s.", modelo)
        return None
    estimativa = mx.estimar_custo([d.texto for d in fila], modelo)
    conferir_teto(manifesto, estimativa, teto)
    lote = cliente.messages.batches.create(
        requests=[
            {"custom_id": d.protocolo, "params": mx.pedido(d.texto, modelo)}
            for d in fila
        ]
    )
    manifesto["lotes"] = [
        *manifesto.get("lotes", []),
        {"id": lote.id, "documentos": len(fila), "estimativa": estimativa, "estado": "enviado",
         "enviado_em": datetime.now(FUSO).isoformat(timespec="seconds")},
    ]  # fmt: skip
    _gravar_manifesto(saida, modelo, manifesto)
    log.info(
        "Lote %s: %s documentos, estimativa US$ %.2f", lote.id, len(fila), estimativa
    )
    return lote.id


def buscar(cliente: anthropic.Anthropic, saida: Path, modelo: str) -> int:
    """Grava as respostas brutas dos lotes que terminaram, com tokens e custo. Devolve quantas."""
    manifesto = ler_manifesto(saida, modelo)
    gravadas = 0
    for lote in manifesto.get("lotes", []):
        if lote["estado"] == "gravado":
            continue
        if cliente.messages.batches.retrieve(lote["id"]).processing_status != "ended":
            log.info("Lote %s ainda processando.", lote["id"])
            continue
        registros, gasto = [], 0.0
        for resultado in cliente.messages.batches.results(lote["id"]):
            base = {"protocolo": resultado.custom_id, "modelo": modelo, "lote": lote["id"],
                    "versao_do_guia": mx.VERSAO_DO_GUIA,
                    "lido_em": datetime.now(FUSO).isoformat(timespec="seconds")}  # fmt: skip
            if resultado.result.type != "succeeded":
                registros.append(base | {"erro": f"lote: {resultado.result.type}"})
                continue
            mensagem = resultado.result.message
            custo = _custo(mensagem.usage, modelo)
            gasto += custo
            bruta = next((b.text for b in mensagem.content if b.type == "text"), "")
            registro = base | {
                "resposta_bruta": bruta,
                "tokens_entrada": mensagem.usage.input_tokens,
                "tokens_saida": mensagem.usage.output_tokens,
                "custo": custo,
            }
            if mensagem.stop_reason != "end_turn":
                registro["erro"] = f"parada: {mensagem.stop_reason}"
            registros.append(registro)
        _acrescentar(saida, modelo, registros)
        lote |= {"estado": "gravado", "gasto": gasto}
        manifesto["gasto_em_dolares"] = manifesto.get("gasto_em_dolares", 0.0) + gasto
        gravadas += len(registros)
    _gravar_manifesto(saida, modelo, manifesto)
    return gravadas


# --- medida (sem API) -------------------------------------------------------------------------------


def medir_modelo(ouro: Path, textos: Path, saida: Path, modelo: str) -> Medida:
    """Confere de novo as respostas guardadas (a regra pode ter mudado; não paga de novo) e compara
    com a amostra de ouro."""
    guardadas = ler_leituras(saida, modelo)
    leituras: dict[str, mx.LeituraDaOperacao] = {}
    com_descarte = para_revisao = 0
    for documento in documentos(ouro, textos):
        registro = guardadas.get(documento.protocolo)
        if registro is None or "erro" in registro:
            continue
        try:
            lida = mx.LeituraDaOperacao.model_validate_json(registro["resposta_bruta"])
        except ValueError:
            continue
        conferida = mx.conferir(lida, documento.texto, documento.publico_em)
        leituras[documento.protocolo] = conferida.leitura
        com_descarte += bool(conferida.descartes)
        para_revisao += conferida.precisa_de_revisao
    gasto = ler_manifesto(saida, modelo).get("gasto_em_dolares", 0.0)
    return Medida(
        modelo,
        mx.medir(leituras, _ouro(ouro)),
        len(leituras),
        gasto / len(leituras) if leituras else 0.0,
        leituras,
        com_descarte,
        para_revisao,
    )


def relatorio(medidas: list[Medida]) -> str:
    """O placar por modelo, o custo por documento e onde as duas leituras discordam."""
    partes = [
        f"## {m.modelo}\n\n{m.lidos} documentos lidos; US$ {m.custo_por_documento:.5f} por "
        f"documento (lote); {m.com_descarte} com algum item descartado; {m.para_revisao} para "
        f"revisão pela coerência.\n\n{m.placar.to_string(index=False)}\n"
        for m in medidas
    ]
    if len(medidas) == 2:
        a, b = medidas
        comuns = sorted(set(a.leituras) & set(b.leituras))
        contagem: dict[str, int] = {}
        for protocolo in comuns:
            for campo in mx.divergencias(a.leituras[protocolo], b.leituras[protocolo]):
                contagem[campo] = contagem.get(campo, 0) + 1
        partes.append(
            f"## As duas leituras\n\n{len(comuns)} documentos lidos pelos dois; divergências por "
            f"campo (vão para revisão humana): {contagem or 'nenhuma'}\n"
        )
    return "\n".join(partes)


def cliente_de_ma() -> anthropic.Anthropic:
    """O cliente da API com a chave só da base de M&A (ADR 0087, regra 2: uma chave por uso). Sem a
    variável própria, o script para antes de qualquer chamada."""
    chave = os.environ.get(VARIAVEL_DA_CHAVE, "").strip()
    if not chave:
        raise SystemExit(
            f"Falta {VARIAVEL_DA_CHAVE} no ambiente (a chave da base de M&A): rode "
            "projeto-acoes/configurar-chave-anthropic-ma-casa.ps1."
        )
    return anthropic.Anthropic(api_key=chave)


def _argumentos() -> argparse.ArgumentParser:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    sub = argumentos.add_subparsers(dest="passo", required=True)
    for nome, ajuda in (
        ("estimar", "custo projetado em US$ (sem API)"),
        ("enviar", "manda o lote da Batch API (GASTA API)"),
        ("buscar", "grava os lotes que terminaram"),
        ("medir", "compara com a amostra de ouro (sem API)"),
    ):
        passo = sub.add_parser(nome, help=ajuda)
        passo.add_argument("--ouro", type=Path, required=True)
        passo.add_argument("--textos", type=Path, required=True)
        passo.add_argument("--saida", type=Path, required=True)
        passo.add_argument("--modelo", default=mx.MODELO, choices=MODELOS)
        if nome == "enviar":
            passo.add_argument("--teto-dolares", type=float, required=True)
    return argumentos


def main(argv: list[str] | None = None) -> int:
    opcoes = _argumentos().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    ouro, textos, saida, modelo = (
        opcoes.ouro,
        opcoes.textos,
        opcoes.saida,
        opcoes.modelo,
    )
    if opcoes.passo == "estimar":
        for nome in MODELOS:
            fila = pendentes(ouro, textos, saida, nome)
            custo = mx.estimar_custo([d.texto for d in fila], nome)
            print(f"{nome}: {len(fila)} documentos, estimativa US$ {custo:.2f} (lote)")
    elif opcoes.passo == "medir":
        medidas = [medir_modelo(ouro, textos, saida, nome) for nome in MODELOS]
        texto = relatorio([m for m in medidas if m.lidos])
        (saida / "medida.md").write_text(texto, encoding="utf-8")
        print(texto)
    elif opcoes.passo == "enviar":
        enviar(cliente_de_ma(), ouro, textos, saida, modelo, opcoes.teto_dolares)
    else:
        print(f"{buscar(cliente_de_ma(), saida, modelo)} respostas gravadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
