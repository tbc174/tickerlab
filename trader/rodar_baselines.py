"""Roda as baselines B0, B1 e B2 e a análise de viabilidade, SÓ no desenvolvimento (até 08/09/2023).

    python -m trader.rodar_baselines

Cada baseline entra no registro de tentativas (família H0) e o relatório vai para
`pesquisa_m2/relatorios/`. Custos no caso base (×1) e no estresse (×2), como manda o critério.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trader import armazem, avaliacao, baselines, juros, viabilidade
from trader.backtest import executar_backtest
from trader.custos import MARGEM_DO_SWAP, VERSAO_DA_TABELA, custos_do_ativo
from trader.holdout import (
    FIM_DO_DESENVOLVIMENTO,
    INICIO_DA_AVALIACAO,
    carregar_desenvolvimento,
)
from trader.posicao import (
    ALVO_PADRAO,
    LARGURA_DO_BUFFER,
    LIMITE_DE_ERRO_DE_AJUSTE,
    TETO_PADRAO,
    dimensionar,
    retornos_seguros,
    zerar_erros_de_ajuste,
)
from trader.registro import ORCAMENTO_DE_TENTATIVAS, PASTA_DA_PESQUISA, Registro
from trader.universo import UNIVERSO, Ativo

PASTA_DOS_RELATORIOS = PASTA_DA_PESQUISA / "relatorios"
MULTIPLICADORES = (1.0, 2.0)


CLASSES_COM_LIMPEZA_DE_AJUSTE = {"acoes_b3"}


@dataclass(frozen=True)
class SerieDoAtivo:
    ativo: Ativo
    retorno: (
        pd.Series
    )  # retornos seguros (e limpos, nas ações da B3) do desenvolvimento
    dias_zerados: int = 0

    @property
    def dias_por_ano(self) -> int:
        return 365 if self.ativo.classe == "cripto" else 252


def carregar_series(ativos: list[Ativo] | None = None) -> list[SerieDoAtivo]:
    lista = [a for a in (ativos or UNIVERSO) if a.papel == "operar"]
    series = []
    for ativo in lista:
        candles = carregar_desenvolvimento(ativo.arquivo)
        if len(candles) < 2:
            continue
        retorno = retornos_seguros(candles["Close"])
        zerados = 0
        if ativo.classe in CLASSES_COM_LIMPEZA_DE_AJUSTE:
            retorno, zerados = zerar_erros_de_ajuste(retorno)
        series.append(SerieDoAtivo(ativo, retorno, zerados))
    return series


def sinal(nome: str, serie: SerieDoAtivo) -> pd.Series:
    if nome == "B0":
        return baselines.sinal_b0(serie.ativo, serie.retorno.index)
    if nome == "B1":
        return baselines.sinal_b1(serie.retorno)
    if nome == "B2":
        return baselines.sinal_b2(serie.retorno)
    raise ValueError(f"Baseline desconhecida: {nome}")


def rodar_baseline(
    nome: str, series: list[SerieDoAtivo], taxas: pd.DataFrame | None = None
) -> dict:
    """Backtest de cada ativo com custos ×1 e ×2; devolve resumo da carteira e por ativo."""
    por_multiplicador: dict[str, dict] = {}
    por_ativo: list[dict] = []
    series_da_carteira: dict[str, pd.Series] = {}
    for mult in MULTIPLICADORES:
        retornos: dict[str, pd.Series] = {}
        for serie in series:
            s = sinal(nome, serie)
            posicao = dimensionar(s, serie.retorno, dias_por_ano=serie.dias_por_ano)
            if not (posicao != 0).any():
                continue  # ex.: B0 em forex fica fora da carteira
            resultado = executar_backtest(
                baselines.preco_sintetico(serie.retorno),
                posicao,
                custos_do_ativo(serie.ativo, mult, taxas, serie.retorno.index),
                limite=TETO_PADRAO,
                retorno_do_ativo=serie.retorno,
            )
            janela = resultado.retorno.index >= INICIO_DA_AVALIACAO
            retorno = resultado.retorno[janela]
            if retorno.empty:
                continue
            retornos[serie.ativo.simbolo] = retorno
            if mult == 1.0:
                anos = max(len(retorno) / serie.dias_por_ano, 1e-9)
                resumo = avaliacao.resumir_serie(retorno, serie.dias_por_ano)
                custos_por_ano = float(resultado.custos[janela].sum() / anos)
                vol = resumo["volatilidade_anual"]
                por_ativo.append(
                    {
                        "baseline": nome,
                        "simbolo": serie.ativo.simbolo,
                        "classe": serie.ativo.classe,
                        "proxy_de": serie.ativo.proxy_de,
                        **resumo,
                        "custos_por_ano": custos_por_ano,
                        "swap_por_ano": float(resultado.swap[janela].sum() / anos),
                        "giro_por_ano": float(
                            resultado.posicao[janela].diff().abs().sum() / anos
                        ),
                        "custo_anual_em_sharpe": (
                            custos_por_ano / vol if vol and vol > 0 else float("nan")
                        ),
                    }
                )
        por_multiplicador[f"x{mult:g}"] = avaliacao.resumir_carteira(retornos)
        series_da_carteira[f"x{mult:g}"] = avaliacao.retorno_da_carteira(
            avaliacao.montar_carteira(retornos)
        )
    return {
        "carteira": por_multiplicador,
        "por_ativo": por_ativo,
        "series": series_da_carteira,
    }


def especificacao(nome: str, series: list[SerieDoAtivo]) -> dict:
    return {
        "tipo": "baseline",
        "baseline": nome,
        "parametros": (
            {"velocidades": [list(v) for v in baselines.VELOCIDADES], "teto": 20}
            if nome == "B1"
            else {}
        ),
        "posicao": {
            "alvo": ALVO_PADRAO,
            "teto": TETO_PADRAO,
            "buffer": LARGURA_DO_BUFFER,
            "volatilidade": "mista 35d + 30% da lenta de 10 anos",
        },
        "custos": {
            "tabela": VERSAO_DA_TABELA,
            "swap": "carry pelas taxas basicas do BIS (dia anterior) +/- margem",
            "margem_do_swap": MARGEM_DO_SWAP,
        },
        "dados": {
            "inicio_da_avaliacao": INICIO_DA_AVALIACAO.date().isoformat(),
            "fim_do_desenvolvimento": FIM_DO_DESENVOLVIMENTO.date().isoformat(),
            "futuros_do_yahoo": "so atributo",
            "erros_de_ajuste": {
                "classes": sorted(CLASSES_COM_LIMPEZA_DE_AJUSTE),
                "limite": LIMITE_DE_ERRO_DE_AJUSTE,
            },
        },
        "universo": sorted(s.ativo.simbolo for s in series),
    }


def rodar_viabilidade(series: list[SerieDoAtivo]) -> tuple[pd.DataFrame, dict]:
    linhas = []
    for serie in series:
        custo = (
            custos_do_ativo(serie.ativo).custo_por_lado(serie.retorno.index[:1]).iloc[0]
        )
        linhas.append(
            {
                "simbolo": serie.ativo.simbolo,
                "classe": serie.ativo.classe,
                **viabilidade.linha_de_viabilidade(
                    serie.retorno.loc[INICIO_DA_AVALIACAO:], 2 * custo
                ),
            }
        )
    semanais = viabilidade.retornos_semanais(
        {s.ativo.simbolo: s.retorno.loc[INICIO_DA_AVALIACAO:] for s in series}
    )
    return pd.DataFrame(linhas), viabilidade.apostas_independentes(semanais)


def _fmt(valor: object, casas: int = 2, pct: bool = False) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "-"
    if pct:
        return f"{float(valor) * 100:.{casas - 1 if casas > 1 else 0}f}%"
    return f"{float(valor):.{casas}f}"


def escrever_relatorio(
    resultados: dict[str, dict],
    tentativas: dict[str, int],
    viab: pd.DataFrame,
    apostas: dict,
    pasta: Path,
    registro: Registro,
    series: list[SerieDoAtivo] | None = None,
) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    com_zeros = [s for s in (series or []) if s.dias_zerados]
    zerados = sum(s.dias_zerados for s in com_zeros)
    detalhe_zerados = ", ".join(
        f"{s.ativo.simbolo} {s.dias_zerados}" for s in com_zeros
    )
    agora = datetime.now(UTC)
    caminho = pasta / f"baselines_{agora:%Y%m%d_%H%M}.md"
    linhas = [
        (
            f"# Baselines e viabilidade (de {INICIO_DA_AVALIACAO:%d/%m/%Y} a "
            f"{FIM_DO_DESENVOLVIMENTO:%d/%m/%Y}, só desenvolvimento)"
        ),
        "",
        (
            f"Gerado em {agora:%d/%m/%Y %H:%M} UTC. Tentativas registradas no desenvolvimento: "
            f"{registro.total_para_o_dsr()} de {ORCAMENTO_DE_TENTATIVAS} (orçamento)."
        ),
        "",
        "## Carteira (risco igual entre ativos, custos ×1 e ×2)",
        "",
        (
            "| Baseline | Tentativa | Ativos | Sharpe ×1 | Sharpe ×2 | t ×1 | Retorno/ano |"
            " Vol/ano | Maior queda | Anos positivos | Ativos positivos | Maior participação |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for nome, r in resultados.items():
        a, b = r["carteira"]["x1"], r["carteira"]["x2"]
        linhas.append(
            f"| {nome} | #{tentativas[nome]} | {a['ativos']} | {_fmt(a['sharpe'])} | "
            f"{_fmt(b['sharpe'])} | {_fmt(a['t'])} | {_fmt(a['retorno_anual'], 2, True)} | "
            f"{_fmt(a['volatilidade_anual'], 2, True)} | {_fmt(a['maior_queda'], 2, True)} | "
            f"{_fmt(a['anos_positivos'], 2, True)} | {_fmt(a['fracao_de_ativos_positivos'], 2, True)} | "
            f"{_fmt(a['maior_participacao'], 2, True)} ({a['ativo_de_maior_participacao'] or '-'}) |"
        )
    linhas += [
        "",
        (
            "Referência do critério (seção 5A): t ≥ 3,0; ≥ 60% dos ativos e ≥ 65% dos anos"
            " positivos; nenhum ativo com mais de 25%; custos ×2 ainda positivos. As baselines"
            " **não** precisam passar: elas são a régua que o candidato de ML precisa vencer"
            " (principalmente a B1)."
        ),
        "",
        "## B1 (tendência simples) por ativo, custos ×1",
        "",
        "| Ativo | Classe | Sharpe | t | Retorno/ano | Maior queda | Giro/ano | Custo/ano em Sharpe | Proxy de |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    b1 = sorted(
        resultados["B1"]["por_ativo"],
        key=lambda x: -x["sharpe"] if not pd.isna(x["sharpe"]) else 0,
    )
    for x in b1:
        linhas.append(
            f"| {x['simbolo']} | {x['classe']} | {_fmt(x['sharpe'])} | {_fmt(x['t'])} | "
            f"{_fmt(x['retorno_anual'], 2, True)} | {_fmt(x['maior_queda'], 2, True)} | "
            f"{_fmt(x['giro_por_ano'], 1)} | {_fmt(x['custo_anual_em_sharpe'], 3)} | "
            f"{x['proxy_de'].split(':')[0] if x['proxy_de'] else ''} |"
        )
    linhas += [
        "",
        "## Viabilidade",
        "",
        (
            f"- **Apostas independentes:** {_fmt(apostas['apostas_independentes'], 1)} de "
            f"{apostas['ativos']} ativos (correlação média semanal "
            f"{_fmt(apostas['correlacao_media'])}; pares sem 2 anos em comum: "
            f"{apostas['pares_sem_dados_em_comum']})."
        ),
        "",
        (
            "| Ativo | Classe | Dias | Custo ida e volta (pb) | Mov. > custo 1d | 5d | 21d |"
            " Autocorr. 1d | Autocorr. semanal |"
        ),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for _, x in viab.sort_values("movimento_maior_que_custo_1d").iterrows():
        linhas.append(
            f"| {x['simbolo']} | {x['classe']} | {int(x['dias'])} | {_fmt(x['custo_ida_e_volta_pb'], 1)} | "
            f"{_fmt(x['movimento_maior_que_custo_1d'], 2, True)} | "
            f"{_fmt(x['movimento_maior_que_custo_5d'], 2, True)} | "
            f"{_fmt(x['movimento_maior_que_custo_21d'], 2, True)} | "
            f"{_fmt(x['autocorrelacao_1d'], 3)} | {_fmt(x['autocorrelacao_semanal'], 3)} |"
        )
    linhas += [
        "",
        "## Limitações destes números",
        "",
        "- Só desenvolvimento (03/01/2000 a 08/09/2023); nada do holdout foi lido.",
        "- Futuros contínuos do Yahoo (=F) ficaram fora: são só atributo (saltos de rolagem).",
        (
            "- Ações da B3: retornos diários acima de 40% em módulo foram zerados como erro de"
            f" ajuste do Yahoo ({zerados} dias no total: {detalhe_zerados or 'nenhum'})."
        ),
        (
            "- Swap = carry pelas taxas básicas dos bancos centrais (BIS) ± 0,5% ao ano de margem;"
            " o swap real de cada corretora é diferente. Resultados são acima do juro da moeda"
            " (ações da B3 e Ibovespa: acima da Selic)."
        ),
        (
            "- Ações da B3 com viés de sobrevivência; futuros contínuos sem ajuste de rolagem;"
            " proxies no lugar de WIN, WDO, ICF e BGI; sem imposto."
        ),
    ]
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def main() -> int:
    registro = Registro()
    taxas = juros.carregar()
    print("Carregando o desenvolvimento...")
    series = carregar_series()
    print(f"{len(series)} ativos para operar.")
    resultados: dict[str, dict] = {}
    tentativas: dict[str, int] = {}
    for nome in ("B0", "B1", "B2"):
        print(f"Rodando {nome}...")
        tentativa = registro.registrar(
            "H0", f"baseline_{nome}", especificacao(nome, series)
        )
        resultados[nome] = rodar_baseline(nome, series, taxas)
        registro.salvar_resultado(tentativa, {"carteira": resultados[nome]["carteira"]})
        armazem.salvar(
            registro.obter(tentativa)["hash"],
            resultados[nome]["series"]["x1"],
            resultados[nome]["series"]["x2"],
            apelido=f"baseline_{nome}",
        )
        tentativas[nome] = tentativa
    print("Viabilidade...")
    viab, apostas = rodar_viabilidade(series)
    PASTA_DOS_RELATORIOS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [linha for r in resultados.values() for linha in r["por_ativo"]]
    ).to_csv(PASTA_DOS_RELATORIOS / "baselines_por_ativo.csv", index=False)
    viab.to_csv(PASTA_DOS_RELATORIOS / "viabilidade.csv", index=False)
    (PASTA_DOS_RELATORIOS / "viabilidade_resumo.json").write_text(
        json.dumps(apostas, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    caminho = escrever_relatorio(
        resultados, tentativas, viab, apostas, PASTA_DOS_RELATORIOS, registro, series
    )
    for nome, r in resultados.items():
        a, b = r["carteira"]["x1"], r["carteira"]["x2"]
        print(
            f"{nome}: Sharpe {a['sharpe']:.2f} (custos ×2: {b['sharpe']:.2f}), t {a['t']:.2f}, "
            f"{a['ativos']} ativos, {a['fracao_de_ativos_positivos']:.0%} positivos"
        )
    print(
        f"Apostas independentes: {apostas['apostas_independentes']:.1f} de {apostas['ativos']}"
    )
    print(f"Relatório: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
