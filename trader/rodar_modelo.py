"""Roda UMA configuração de modelo de ponta a ponta, só no desenvolvimento, e julga pelo critério.

    python -m trader.rodar_modelo --modelo logistica
    python -m trader.rodar_modelo --modelo lightgbm --nome lgbm_v1

1. registra a tentativa (antes de rodar: o que é tentado conta, mesmo que dê erro);
2. CPCV com 45 divisões → 9 caminhos (custos ×1 e ×2);
3. verificações de vazamento (normal duas vezes, futuro, embaralhado);
4. teste contra o acaso da carteira;
5. avaliador A1–A10 e C; o veredito vai para o registro (`aprovado_em_A`) e para um relatório.
Precisa das baselines já rodadas (a B1 é a régua do A5).
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime

import pandas as pd

from trader import armazem, atributos, avaliacao, criterio, juros, pipeline, vazamento
from trader.holdout import FIM_DO_DESENVOLVIMENTO, INICIO_DA_AVALIACAO
from trader.registro import Registro
from trader.rodar_baselines import PASTA_DOS_RELATORIOS, carregar_series


def preparar() -> tuple[list, pd.DataFrame, pd.DataFrame]:
    taxas = juros.carregar()
    series = carregar_series()
    painel = atributos.montar_painel(
        series,
        taxas,
        atributos.carregar_macro(),
        INICIO_DA_AVALIACAO,
        FIM_DO_DESENVOLVIMENTO,
    )
    return series, taxas, painel


def escrever_relatorio(
    config: pipeline.Configuracao,
    tentativa: int,
    res: pipeline.ResultadoDoPipeline,
    veredito: criterio.Veredito,
    vaz_det: dict,
    acaso: dict,
) -> str:
    sharpes = [avaliacao.sharpe(c) for c in res.caminhos]
    sharpes_x2 = [avaliacao.sharpe(c) for c in res.caminhos_x2]
    agora = datetime.now(UTC)
    linhas = [
        f"# {config.nome} ({config.modelo}, família {config.familia}) — tentativa #{tentativa}",
        "",
        (
            f"Gerado em {agora:%d/%m/%Y %H:%M} UTC. Só desenvolvimento "
            f"({INICIO_DA_AVALIACAO:%d/%m/%Y} a {FIM_DO_DESENVOLVIMENTO:%d/%m/%Y})."
        ),
        "",
        f"**Veredito: {'APROVADO em A' if veredito.aprovado else 'REPROVADO'}**"
        + (
            f" (inconclusivo: {veredito.motivo_inconclusivo})"
            if veredito.inconclusivo
            else ""
        )
        + (
            f" — falhou em {', '.join(veredito.reprovados)}"
            if veredito.reprovados
            else ""
        ),
        "",
        "| Item | O quê | Valor | Limite | Passou |",
        "|---|---|---|---|---|",
    ]
    for i in veredito.itens:
        valor = "-" if i.valor is None else f"{i.valor:.3f}"
        linhas.append(
            f"| {i.codigo} | {i.descricao} | {valor} | {i.limite} | {'sim' if i.passou else 'NÃO'} |"
        )
    linhas += [
        "",
        "## Os 9 caminhos",
        "",
        "Sharpe ×1: " + ", ".join(f"{x:.2f}" for x in sharpes),
        "",
        "Sharpe ×2: " + ", ".join(f"{x:.2f}" for x in sharpes_x2),
        "",
        "## Vazamento e acaso",
        "",
        (
            f"- Sharpe normal {vaz_det['sharpe_normal']:.2f}; olhando o futuro "
            f"{vaz_det['sharpe_futuro']:.2f}; rótulos embaralhados "
            f"{vaz_det['sharpe_embaralhado']:.2f} "
            f"(limite ±{vaz_det['limite_do_embaralhado']:.2f})."
        ),
        (
            f"- Contra o acaso: Sharpe real {acaso['sharpe_real']:.2f}, percentil 95 dos "
            f"sorteios {acaso['percentil_95']:.2f}, p-valor {acaso['p_valor']:.3f}."
        ),
    ]
    PASTA_DOS_RELATORIOS.mkdir(parents=True, exist_ok=True)
    caminho = PASTA_DOS_RELATORIOS / f"modelo_{config.nome}_{agora:%Y%m%d_%H%M}.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return str(caminho)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--modelo", choices=["logistica", "floresta", "lightgbm"], required=True
    )
    parser.add_argument("--nome", default=None)
    args = parser.parse_args()
    config = pipeline.Configuracao(
        nome=args.nome or f"{args.modelo}_v1", modelo=args.modelo
    )
    inicio = time.time()
    registro = Registro()
    b1 = armazem.carregar("baseline_B1")["x1"]
    print("Montando o painel de atributos...", flush=True)
    series, taxas, painel = preparar()
    print(f"{len(painel):,} linhas, {painel['simbolo'].nunique()} ativos.", flush=True)

    tentativa = registro.registrar(config.familia, config.nome, config.especificacao())
    print(
        f"Tentativa #{tentativa} registrada. Rodando o CPCV (45 divisões)...",
        flush=True,
    )
    res = pipeline.rodar(config, painel, series, taxas, progresso=True)
    m = criterio.indice_do_caminho_mediano(res.caminhos)

    print(
        "Verificações de vazamento (normal de novo, futuro, embaralhado)...", flush=True
    )
    primeira = {"usada": False}

    def rodar_variante(variante: str) -> pd.Series:
        if variante == "normal" and not primeira["usada"]:
            primeira["usada"] = True
            return res.caminhos[m]
        outro = pipeline.rodar(config, painel, series, taxas, variante=variante)
        return outro.caminhos[m]

    vaz, vaz_det = vazamento.verificar(rodar_variante)

    print("Teste contra o acaso...", flush=True)
    acaso = criterio.p_valor_do_acaso_da_carteira(
        res.posicoes[m], res.retornos_dos_ativos, res.custo_por_lado
    )
    hash_ = registro.obter(tentativa)["hash"]
    armazem.salvar(hash_, res.caminhos[m], res.caminhos_x2[m])
    indice = res.caminhos[m].index
    evidencia = criterio.EvidenciaDoDesenvolvimento(
        caminhos=res.caminhos,
        caminhos_x2=res.caminhos_x2,
        por_ativo=res.por_ativo[m],
        b1=b1,
        candidatos=armazem.candidatos(indice, "x1"),
        candidatos_x2=armazem.candidatos(indice, "x2"),
        tentativas_totais=registro.total_para_o_dsr(),
        p_valor_do_acaso=acaso["p_valor"],
        vazamento=vaz,
    )
    veredito = criterio.avaliar_desenvolvimento(evidencia)
    registro.salvar_resultado(
        tentativa,
        {
            **veredito.para_registro(),
            "aprovado_em_A": veredito.aprovado,
            "sharpes_dos_caminhos": [avaliacao.sharpe(c) for c in res.caminhos],
            "vazamento": vaz_det,
            "acaso": acaso,
        },
    )
    relatorio = escrever_relatorio(config, tentativa, res, veredito, vaz_det, acaso)
    print(
        f"\nVeredito: {'APROVADO em A' if veredito.aprovado else 'REPROVADO'}"
        + (
            f" (falhou em {', '.join(veredito.reprovados)})"
            if veredito.reprovados
            else ""
        )
    )
    for i in veredito.itens:
        valor = "-" if i.valor is None else f"{i.valor:.3f}"
        print(
            f"  {i.codigo:>3} {'ok ' if i.passou else 'NÃO'} {valor:>8}  {i.descricao}"
        )
    print(f"Tentativas registradas: {registro.total_para_o_dsr()} de 300.")
    print(f"Relatório: {relatorio}  ({(time.time() - inicio) / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
