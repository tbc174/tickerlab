"""Roda a Pesquisa 2 inteira: K1, K2, B0 e B1, com o critério do pré-registro (fase P6).

    python -m trader.p2.rodar

**Cada execução conta como tentativa** no registro `pesquisa_p2/registro.db` (4 por rodada) e o
Sharpe deflacionado soma as 101 tentativas da M2. Só roda se o texto do pré-registro for o aprovado
(hash) e só com dados até o fim do desenvolvimento (o holdout continua lacrado).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trader import avaliacao
from trader.holdout import exigir_sem_holdout, recortar_desenvolvimento
from trader.p2 import carteira, criterio, preregistro, regras, retornos
from trader.p2.baixar import ARQUIVO_DE_SHILLER, ARQUIVO_DO_BIS
from trader.p2.dividendos import rendimento_de_dividendos
from trader.p2.fontes import PASTA_PADRAO, carregar_serie
from trader.p2.juros import juro_da_moeda
from trader.p2.mercados import JUROS_CURTOS, MERCADOS, Mercado
from trader.registro import RAIZ, Registro

PASTA_DA_PESQUISA = RAIZ / "pesquisa_p2"
FAMILIAS = ("K", "B")
FAMILIA_DA_CONFIGURACAO = {"K1": "K", "K2": "K", "B0": "B", "B1": "B"}
CANDIDATO = "K2"


def abrir_registro(caminho: Path = PASTA_DA_PESQUISA / "registro.db") -> Registro:
    return Registro(
        caminho, familias=FAMILIAS, orcamento=preregistro.ORCAMENTO_DE_TENTATIVAS
    )


def carregar_tabelas(
    pasta: Path = PASTA_PADRAO,
) -> tuple[dict[str, Mercado], dict[str, pd.DataFrame]]:
    """Retornos de CFD de todos os mercados, só com dados do desenvolvimento."""
    ocde = {
        moeda: carregar_serie("fred", serie, pasta)
        for moeda, serie in JUROS_CURTOS.items()
    }
    ocde = {moeda: serie for moeda, serie in ocde.items() if serie is not None}
    bis = pd.read_parquet(pasta / ARQUIVO_DO_BIS)
    shiller = pd.read_parquet(pasta / ARQUIVO_DE_SHILLER)["valor"]

    def juro(moeda: str, indice: pd.DatetimeIndex) -> pd.Series:
        return juro_da_moeda(moeda, indice, ocde, bis)

    def dividendo(codigo: str, indice: pd.DatetimeIndex) -> pd.Series:
        return rendimento_de_dividendos(codigo, indice, shiller)

    mercados, tabelas = {}, {}
    for mercado in MERCADOS:
        serie = carregar_serie(mercado.fonte, mercado.serie, pasta)
        if serie is None:
            raise FileNotFoundError(
                f"Falta a série de {mercado.codigo}: rode python -m trader.p2.baixar"
            )
        tabela = retornos.montar(
            mercado, recortar_desenvolvimento(serie), juro, dividendo
        )
        tabela = tabela.dropna(subset=["total"])
        exigir_sem_holdout(tabela)
        mercados[mercado.codigo], tabelas[mercado.codigo] = mercado, tabela
    return mercados, tabelas


def _previsoes(
    configuracao: str, mercados: dict[str, Mercado], tabelas: dict[str, pd.DataFrame]
) -> dict[str, pd.Series]:
    return {
        c: regras.previsao(configuracao, m, tabelas[c]) for c, m in mercados.items()
    }


def executar(
    mercados: dict[str, Mercado], tabelas: dict[str, pd.DataFrame], registro: Registro
) -> dict:
    """Registra as 4 configurações, simula, avalia o K2 e guarda tudo no registro."""
    preregistro.conferir()
    especificacao_comum = {
        "pesquisa": "P2",
        "pre_registro": preregistro.HASH_DO_CRITERIO,
        "mercados": sorted(mercados),
    }
    ids = {
        cfg: registro.registrar(
            FAMILIA_DA_CONFIGURACAO[cfg],
            f"p2_{cfg.lower()}",
            {**especificacao_comum, "configuracao": cfg},
        )
        for cfg in regras.CONFIGURACOES
    }
    previsoes = {
        cfg: _previsoes(cfg, mercados, tabelas) for cfg in regras.CONFIGURACOES
    }

    def carteira_de(cfg: str, custos: carteira.Custos) -> carteira.Resultado:
        return carteira.simular(mercados, tabelas, previsoes[cfg], custos)

    base = {cfg: carteira_de(cfg, carteira.CUSTOS_BASE) for cfg in regras.CONFIGURACOES}
    estresse_a = {
        cfg: carteira_de(cfg, carteira.ESTRESSE_A).retorno
        for cfg in regras.CONFIGURACOES
    }
    estresse_b = {
        cfg: carteira_de(cfg, carteira.ESTRESSE_B).retorno
        for cfg in regras.CONFIGURACOES
    }
    recorte = criterio.recortar_avaliacao

    k2 = base[CANDIDATO]
    futuro = carteira.simular(
        mercados, tabelas, previsoes[CANDIDATO], olhar_o_futuro=True
    )
    de_novo = carteira.simular(
        mercados, tabelas, _previsoes(CANDIDATO, mercados, tabelas)
    )
    datas = recorte(k2.retorno).index
    dias = pd.Series(datas.to_series().diff().dt.days.fillna(1).to_numpy(), index=datas)
    acaso = criterio.p_valor_do_acaso(
        k2.posicao.reindex(datas),
        pd.DataFrame({c: t["total"] for c, t in tabelas.items()}).reindex(datas),
        pd.Series({c: carteira.CUSTOS_BASE.por_lado(m) for c, m in mercados.items()}),
        pd.Series({c: carteira.CUSTOS_BASE.margem(m) for c, m in mercados.items()}),
        dias,
    )

    def tabela(series: dict[str, pd.Series]) -> pd.DataFrame:
        return pd.DataFrame({c: recorte(r) for c, r in series.items()})

    evidencia = criterio.Evidencia(
        candidato=recorte(k2.retorno),
        por_mercado=recorte(k2.contribuicao),
        grupo_do_mercado={c: m.grupo for c, m in mercados.items()},
        b1=recorte(base["B1"].retorno),
        candidatos=tabela({c: r.retorno for c, r in base.items()}),
        candidatos_a=tabela(estresse_a),
        candidatos_b=tabela(estresse_b),
        tentativas_totais=preregistro.TENTATIVAS_DA_M2 + registro.total_para_o_dsr(),
        p_valor_do_acaso=acaso["p_valor"],
        sharpe_olhando_o_futuro=avaliacao.sharpe(recorte(futuro.retorno)),
        reexecucao_identica=bool(de_novo.retorno.equals(k2.retorno)),
    )
    veredito = criterio.avaliar(evidencia)
    resumos = {
        cfg: avaliacao.resumir_serie(recorte(r.retorno)) for cfg, r in base.items()
    }
    for cfg, tentativa in ids.items():
        resultado = {"resumo": resumos[cfg]}
        if cfg == CANDIDATO:
            resultado |= {"veredito": veredito.para_registro(), "acaso": acaso}
        registro.salvar_resultado(tentativa, resultado)
    return {"ids": ids, "veredito": veredito, "resumos": resumos, "acaso": acaso}


def escrever_relatorio(
    saida: dict, pasta: Path = PASTA_DA_PESQUISA / "relatorios"
) -> Path:
    veredito = saida["veredito"]
    linhas = [
        "# Pesquisa 2: rodada do pré-registro v0.1",
        "",
        f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC. Avaliação de 01/01/1980 a 08/09/2023.",
        "",
        f"**Veredito do K2: {'APROVADO' if veredito.aprovado else 'REPROVADO'}**"
        + (
            f" (falhou em {', '.join(veredito.reprovados)})"
            if veredito.reprovados
            else ""
        ),
        "",
        "| Item | O quê | Valor | Limite | Passou |",
        "|---|---|---|---|---|",
        *(
            f"| {i.codigo} | {i.descricao} | {'-' if i.valor is None else f'{i.valor:.3f}'} | {i.limite} | {'sim' if i.passou else 'NÃO'} |"
            for i in veredito.itens
        ),
        "",
        "## As quatro configurações (custos base)",
        "",
        "| Configuração | Sharpe | Retorno anual | Volatilidade | Maior queda |",
        "|---|---|---|---|---|",
        *(
            f"| {cfg} | {r.get('sharpe', float('nan')):.2f} | {r.get('retorno_anual', float('nan')):.1%} | "
            f"{r.get('volatilidade_anual', float('nan')):.1%} | {r.get('maior_queda', float('nan')):.1%} |"
            for cfg, r in saida["resumos"].items()
        ),
    ]
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"rodada_p2_{datetime.now(UTC):%Y%m%d_%H%M}.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def main() -> int:
    mercados, tabelas = carregar_tabelas()
    saida = executar(mercados, tabelas, abrir_registro())
    print(escrever_relatorio(saida).read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
