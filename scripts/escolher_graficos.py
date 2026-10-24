"""Escolhe os gráficos de cada relatório pela API do Claude, confere e guarda (plano de 23/10/2026).

    python -m scripts.escolher_graficos estimar  --entradas cpfl.json --analises PASTA_DO_TEXTO \
        --pasta P --teto-dolares 2
    python -m scripts.escolher_graficos piloto   --entradas cpfl.json --analises PASTA_DO_TEXTO \
        --pasta P --teto-dolares 2 --modelos claude-haiku-5-5,claude-sonnet-5-5,claude-opus-5-5
    python -m scripts.escolher_graficos cegas    --entradas cpfl.json --analises PASTA_DO_TEXTO \
        --pasta P --teto-dolares 2
    python -m scripts.escolher_graficos conferir --entradas cpfl.json --analises PASTA_DO_TEXTO \
        --pasta P

A escolha é um pedido à parte, depois do texto: `--analises` é a pasta do `escrever_analises`, de
onde vem o texto já montado (`analises/<chave>.json`), que tem de ser da mesma ficha (o hash da
entrada confere). `estimar` conta os tokens pela API (não gasta); `piloto` escolhe na hora com cada
modelo; `cegas` é a porta 2 (outro modelo julga cada item sem saber quem escolheu); `conferir` roda a
porta 1 e monta a escolha final (sem API): item reprovado sai, a reserva por regras completa o
mínimo, e sem a porta 2 nada do modelo vai ao ar.

**O teto vale para tudo:** nenhum passo gasta se o gasto já feito mais a estimativa passar do teto, e
a resposta guardada (mesma ficha, mesmo texto, mesmo guia) nunca é paga de novo. Em `<pasta>`:
`escolhas/` (a resposta bruta de cada modelo), `cegas/` (o veredito da porta 2), `graficos/` (a
escolha final com a linhagem, uma por modelo, para comparar na prova) e `manifesto.json` (o gasto). A
chave fica em `ANTHROPIC_API_KEY` (nunca no código).
"""

import argparse
import json
import logging
import sys
from collections.abc import Iterator, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import anthropic

from scripts import escrever_analises as ea
from scripts.rotular_com_ia import TetoPassado, conferir_teto
from src import rotulos_ia as ri
from src.analise_escrita import entrada as en
from src.analise_escrita import graficos as gr
from src.analise_escrita import pedido as pe
from src.analise_escrita import pedido_dos_graficos as pg
from src.analise_escrita import porta1_dos_graficos as p1g
from src.analise_escrita import porta2, saida, series
from src.analise_escrita import porta2_dos_graficos as p2g
from src.analise_escrita import reserva_dos_graficos as rg

log = logging.getLogger("tickerlab.analise_escrita")

__all__ = ["TetoPassado"]


def arquivo_da_escolha(pasta: Path, entrada: dict[str, Any], modelo: str) -> Path:
    return pasta / "escolhas" / f"{ea.chave(entrada)}.{modelo}.json"


def arquivo_da_cega(pasta: Path, entrada: dict[str, Any], modelo: str) -> Path:
    return pasta / "cegas" / f"{ea.chave(entrada)}.{modelo}.json"


def arquivo_dos_graficos(pasta: Path, entrada: dict[str, Any], modelo: str) -> Path:
    return pasta / "graficos" / f"{ea.chave(entrada)}.{modelo}.json"


def analise_do_texto(analises: Path, entrada: dict[str, Any]) -> saida.Analise | None:
    """O texto montado desta ficha; None se não há ou se saiu de outra ficha (outro corte, outros
    dados): gráfico e texto têm de ler a mesma ficha."""
    guardada = ea._ler(ea.arquivo_da_analise(analises, entrada))
    if guardada is None:
        return None
    if guardada.get("hash_da_entrada_atual") != en.hash_da_entrada(entrada):
        log.warning(
            "%s: o texto guardado é de outra ficha; fica de fora", ea.chave(entrada)
        )
        return None
    return saida.ler_analise(guardada["analise"], saida.partes_de(entrada))


def _hash_do_texto(analise: saida.Analise) -> str:
    return ea._sha256(
        json.dumps(analise.como_dict(), sort_keys=True, ensure_ascii=False)
    )


def ler_manifesto(pasta: Path) -> dict[str, Any]:
    return ea._ler(pasta / "manifesto.json") or {"gasto_em_dolares": 0.0}


def _pagar(pasta: Path, manifesto: dict[str, Any], custo: float) -> None:
    """Grava o gasto a cada resposta: se a próxima chamada cair, o teto já conta esta."""
    manifesto["gasto_em_dolares"] = manifesto.get("gasto_em_dolares", 0.0) + custo
    manifesto |= {"versao_do_guia": pg.VERSAO_DO_GUIA, "atualizado_em": ea._agora()}
    ea._gravar(pasta / "manifesto.json", manifesto)


def escolha_guardada(
    pasta: Path, entrada: dict[str, Any], analise: saida.Analise, modelo: str
) -> dict[str, Any] | None:
    """A resposta que vale para a ficha, o texto e o guia de hoje (mudou algum: escolhe de novo)."""
    registro = ea._ler(arquivo_da_escolha(pasta, entrada, modelo))
    if registro is None:
        return None
    mesma = (
        registro["hash_da_entrada"] == en.hash_da_entrada(entrada)
        and registro["hash_do_texto"] == _hash_do_texto(analise)
        and registro["versao_do_guia"] == pg.VERSAO_DO_GUIA
    )
    return registro if mesma else None


def _com_texto(
    entradas: list[dict[str, Any]], analises: Path
) -> Iterator[tuple[dict[str, Any], saida.Analise]]:
    """Cada ficha que tem texto, já ampliada com as séries calculadas: o texto confere com a
    entrada original; o pedido, as portas e a reserva dos gráficos leem a ampliada."""
    for entrada in entradas:
        analise = analise_do_texto(analises, entrada)
        if analise is not None:
            yield series.ampliar(entrada), analise


def _pendentes(
    entradas: list[dict[str, Any]], analises: Path, pasta: Path, modelos: Sequence[str]
) -> Iterator[tuple[dict[str, Any], saida.Analise, str]]:
    for entrada, analise in _com_texto(entradas, analises):
        for modelo in modelos:
            if escolha_guardada(pasta, entrada, analise, modelo) is None:
                yield entrada, analise, modelo


def _estimativa(
    cliente: anthropic.Anthropic,
    entrada: dict[str, Any],
    analise: saida.Analise,
    modelo: str,
) -> float:
    """A escolha e a porta 2 dela no pior caso; antes da escolha, a reserva faz as vezes dela."""
    escolha = ea._custo_estimado(cliente, pg.pedido(entrada, analise, modelo), False)
    reserva = gr.Escolha(rg.graficos_de_reserva(entrada, analise))
    cega = p2g.pedido(reserva, entrada, analise, porta2.conferente(modelo))
    return escolha + ea._custo_estimado(cliente, cega, False)


def estimar(
    cliente: anthropic.Anthropic,
    entradas: list[dict[str, Any]],
    analises: Path,
    pasta: Path,
    modelos: Sequence[str],
) -> dict[str, float]:
    """O custo projetado em US$ de cada modelo: a escolha do que falta mais a porta 2 dela."""
    custos = dict.fromkeys(modelos, 0.0)
    for entrada, analise, modelo in _pendentes(entradas, analises, pasta, modelos):
        custos[modelo] += _estimativa(cliente, entrada, analise, modelo)
    return custos


def _registro(
    entrada: dict[str, Any],
    analise: saida.Analise,
    modelo: str,
    mensagem: anthropic.types.Message,
) -> dict[str, Any]:
    tokens = ea._tokens(mensagem.usage)
    return {
        **ea.identidade(entrada),
        "modelo": modelo,
        "versao_do_guia": pg.VERSAO_DO_GUIA,
        "hash_da_entrada": en.hash_da_entrada(entrada),
        "hash_do_texto": _hash_do_texto(analise),
        "escolhido_em": ea._agora(),
        "stop_reason": mensagem.stop_reason,
        "resposta_bruta": ea._texto_da_mensagem(mensagem),
        "tokens": tokens,
        "custo_em_dolares": ea.custo_da_resposta(tokens, modelo, False),
    }


def piloto(
    cliente: anthropic.Anthropic,
    entradas: list[dict[str, Any]],
    analises: Path,
    pasta: Path,
    modelos: Sequence[str],
    teto: float,
) -> int:
    """Escolhe na hora o que ainda não tem resposta guardada. Devolve quantas escolheu."""
    pendentes = list(_pendentes(entradas, analises, pasta, modelos))
    if not pendentes:
        return 0
    manifesto = ler_manifesto(pasta)
    conferir_teto(manifesto, sum(_estimativa(cliente, *p) for p in pendentes), teto)
    for entrada, analise, modelo in pendentes:
        mensagem = ea._mensagem_completa(cliente, pg.pedido(entrada, analise, modelo))
        registro = _registro(entrada, analise, modelo, mensagem)
        ea._gravar(arquivo_da_escolha(pasta, entrada, modelo), registro)
        _pagar(pasta, manifesto, registro["custo_em_dolares"])
    log.info("Piloto dos gráficos: %s respostas", len(pendentes))
    return len(pendentes)


def _escolha_do_registro(
    registro: dict[str, Any],
) -> tuple[gr.Escolha | None, str | None]:
    try:
        return pg.ler_resposta(
            registro["stop_reason"], registro["resposta_bruta"]
        ), None
    except saida.RespostaInvalidaError as erro:
        return None, str(erro)  # fora do formato: fica a reserva, sem gastar a porta 2


def _cega_valida(
    pasta: Path, entrada: dict[str, Any], modelo: str, registro: dict[str, Any]
) -> dict[str, Any] | None:
    cega = ea._ler(arquivo_da_cega(pasta, entrada, modelo))
    hash_da_resposta = ea._sha256(registro["resposta_bruta"])
    return cega if cega and cega["hash_da_resposta"] == hash_da_resposta else None


def _a_julgar(
    entradas: list[dict[str, Any]], analises: Path, pasta: Path, modelos: Sequence[str]
) -> Iterator[tuple[dict[str, Any], saida.Analise, str, gr.Escolha, dict[str, Any]]]:
    for entrada, analise in _com_texto(entradas, analises):
        for modelo in modelos:
            registro = escolha_guardada(pasta, entrada, analise, modelo)
            if registro is None or _cega_valida(pasta, entrada, modelo, registro):
                continue
            escolha, _ = _escolha_do_registro(registro)
            if escolha is not None:
                yield entrada, analise, modelo, escolha, registro


def cegas(
    cliente: anthropic.Anthropic,
    entradas: list[dict[str, Any]],
    analises: Path,
    pasta: Path,
    modelos: Sequence[str],
    teto: float,
) -> int:
    """A porta 2 em cada escolha guardada que ainda não passou por ela. Devolve quantas julgou."""
    pendentes = list(_a_julgar(entradas, analises, pasta, modelos))
    if not pendentes:
        return 0
    manifesto = ler_manifesto(pasta)
    pedidos = [p2g.pedido(c, e, a, porta2.conferente(m)) for e, a, m, c, _ in pendentes]
    estimativa = sum(ea._custo_estimado(cliente, p, False) for p in pedidos)
    conferir_teto(manifesto, estimativa, teto)
    for (entrada, _, modelo, escolha, registro), parametros in zip(
        pendentes, pedidos, strict=True
    ):
        mensagem = ea._mensagem_completa(cliente, parametros)
        bruta = ea._texto_da_mensagem(mensagem)
        veredito = p2g.ler_veredito(mensagem.stop_reason, bruta, escolha)
        tokens = ea._tokens(mensagem.usage)
        cega = {
            "conferente": parametros["model"],
            "hash_da_resposta": ea._sha256(registro["resposta_bruta"]),
            "conferido_em": ea._agora(),
            "stop_reason": mensagem.stop_reason,
            "reprovados": sorted(veredito.reprovados),
            "motivo": veredito.motivo,
            "itens": [list(i) for i in veredito.itens],
            "tokens": tokens,
            "custo_em_dolares": ea.custo_da_resposta(
                tokens, parametros["model"], False
            ),
        }
        ea._gravar(arquivo_da_cega(pasta, entrada, modelo), cega)
        _pagar(pasta, manifesto, cega["custo_em_dolares"])
    log.info("Porta 2 dos gráficos: %s escolhas", len(pendentes))
    return len(pendentes)


def _montar(
    entrada: dict[str, Any], analise: saida.Analise, pasta: Path, modelo: str
) -> dict[str, Any]:
    registro = escolha_guardada(pasta, entrada, analise, modelo)
    escolha, motivo = (
        _escolha_do_registro(registro) if registro else (None, "sem escolha")
    )
    cega = _cega_valida(pasta, entrada, modelo, registro) if registro else None
    reprovados = (
        frozenset(cega["reprovados"]) if cega else None
    )  # nunca aprova por falta
    do_modelo = escolha or gr.Escolha(())
    finais = rg.graficos_finais(do_modelo, entrada, analise, reprovados)
    porta1_ = p1g.conferir(do_modelo, entrada, analise).reprovacoes
    return {
        **ea.identidade(entrada),
        "modelo": modelo,
        "hash_da_entrada": en.hash_da_entrada(entrada),
        "montado_em": ea._agora(),
        "escolha": finais.como_dict(),
        "linhagem": {
            "versao_do_guia": pg.VERSAO_DO_GUIA,
            "motivo": motivo or (None if cega else "sem a porta 2: só a reserva"),
            "escolha_do_modelo": escolha.como_dict() if escolha else None,
            "porta1": [asdict(r) for r in porta1_],
            "porta2": {k: v for k, v in (cega or {}).items() if k != "hash_da_resposta"}
            or None,
            "custo_em_dolares": (registro or {}).get("custo_em_dolares", 0.0)
            + (cega or {}).get("custo_em_dolares", 0.0),
        },
    }


def conferir(
    entradas: list[dict[str, Any]], analises: Path, pasta: Path, modelos: Sequence[str]
) -> int:
    """Porta 1 e montagem de cada ficha com a escolha de cada modelo; grava `graficos/`."""
    montados = 0
    for entrada, analise in _com_texto(entradas, analises):
        for modelo in modelos:
            montado = _montar(entrada, analise, pasta, modelo)
            ea._gravar(arquivo_dos_graficos(pasta, entrada, modelo), montado)
            montados += 1
    return montados


GASTAM = ("estimar", "piloto", "cegas")
PASSOS = (*GASTAM, "conferir")


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    analisador = argparse.ArgumentParser(
        description="Escolhe, confere e guarda os gráficos"
    )
    passos = analisador.add_subparsers(dest="passo", required=True)
    for nome in PASSOS:
        passo = passos.add_parser(nome)
        passo.add_argument("--pasta", type=Path, required=True)
        passo.add_argument("--analises", type=Path, required=True)
        passo.add_argument("--entradas", type=Path, nargs="+", default=[])
        passo.add_argument("--modelos", default=pe.SONNET)
        passo.add_argument("--teto-dolares", type=float, required=nome in GASTAM)
    return analisador.parse_args(argv)


def _rodar(args: argparse.Namespace, entradas: list[dict[str, Any]]) -> None:
    modelos = [m.strip() for m in args.modelos.split(",") if m.strip()]
    if args.passo == "conferir":
        print(
            f"{conferir(entradas, args.analises, args.pasta, modelos)} escolhas montadas"
        )
        return
    cliente = ri.cliente()
    if args.passo == "estimar":
        custos = estimar(cliente, entradas, args.analises, args.pasta, modelos)
        gasto = ler_manifesto(args.pasta).get("gasto_em_dolares", 0.0)
        for modelo, custo in custos.items():
            print(f"{modelo}: US$ {custo:.2f} (escolha e porta 2, no pior caso)")
        total = sum(custos.values())
        cabe = "cabe" if gasto + total <= args.teto_dolares else "PASSA"
        print(f"Total US$ {total:.2f}; já gasto US$ {gasto:.2f}; {cabe} no teto")
    elif args.passo == "piloto":
        feitas = piloto(
            cliente, entradas, args.analises, args.pasta, modelos, args.teto_dolares
        )
        print(f"{feitas} escolhas")
    else:
        feitas = cegas(
            cliente, entradas, args.analises, args.pasta, modelos, args.teto_dolares
        )
        print(f"{feitas} julgadas")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _argumentos(argv)
    for modelo in args.modelos.split(","):
        pe.modelo_conhecido(modelo.strip())
    try:
        _rodar(args, ea.ler_entradas(args.entradas))
    except TetoPassado as erro:
        print(erro, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
