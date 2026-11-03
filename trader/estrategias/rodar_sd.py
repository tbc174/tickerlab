"""Roda o estudo da ficha P0-7 (Synthetic Dividend e rebalanceamento) do pré-registro quant v0.1.

    python -m trader.estrategias.rodar_sd

**Cada execução conta como tentativa** da família P0-7 no registro `pesquisa_quant/registro.db`
(orçamento de 4). É estudo, não candidata: não passa pelo critério da seção 5 e nada aqui vira
dinheiro. Só roda se o texto do pré-registro for o aprovado (hash). O histórico usa só o
desenvolvimento (até 08/09/2023).

O que a rodada mede, tudo numa tentativa só:
1. **Monte Carlo** (GBM, 2.000 caminhos, 3 anos): os quatro cenários da tabela 4.4 do relatório, com
   caixa a CDI de 14%, custos e IR do Brasil e execução no fechamento do dia seguinte;
2. **a versão do relatório** (10 bps por lado, sem IR, caixa negativo livre, execução no próprio
   fechamento), para comparar com os números publicados;
3. **o histórico:** janelas de 3 anos começando em cada mês, no BTC em reais e no BOVA11;
4. **os testes do Brasil:** (a) caixa a CDI contra caixa a 0%: o CDI aumenta a vantagem do
   constant-mix? (b) o teto de vendas da isenção muda o resultado? (c) com ordens limitadas no dia,
   o bloqueio de day trade muda o resultado? (d) o mesmo índice como ETF (sem isenção) e como
   ações (com a isenção de R$ 20 mil).
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trader import criterio_quant
from trader.custos_br import CustosBR
from trader.estrategias import dados_p0_3, rodar_p0_3, rodar_tendencia_cripto
from trader.estrategias import dados_tendencia_b3 as dados_b3
from trader.estrategias import sd_simulador as sd
from trader.estrategias.sd_simulador import Cenario, Parametros
from trader.holdout import exigir_sem_holdout, recortar_desenvolvimento
from trader.registro import Registro

PASTA_DA_PESQUISA = dados_p0_3.PASTA_DA_PESQUISA
FICHA = "P0-7"
NOME = "p0_7_simulador_sd"
CDI_DO_ESTUDO = 0.14  # o do relatório (seção 4.4)
CENARIOS = (
    Cenario("BTC μ 50%, σ 70%", 0.50, 0.70, "cripto", 365),
    Cenario("BTC μ 20%, σ 70%", 0.20, 0.70, "cripto", 365),
    Cenario("Ibovespa μ 17%, σ 25%", 0.17, 0.25, "etf", 252),
    Cenario("Ação μ 16%, σ 15%", 0.16, 0.15, "acoes", 252),
)
# A versão do relatório: o caixa de cada linha da tabela 4.4 e as medianas publicadas
# (comprar e segurar, SD8), com erro de Monte Carlo de ~±0,03×.
CAIXA_DO_RELATORIO = {
    "BTC μ 50%, σ 70%": 0.04,
    "BTC μ 20%, σ 70%": 0.04,
    "Ibovespa μ 17%, σ 25%": 0.14,
    "Ação μ 16%, σ 15%": 0.14,
}
MEDIANAS_DO_RELATORIO = {
    "BTC μ 50%, σ 70%": (2.14, 2.35),
    "BTC μ 20%, σ 70%": (0.87, 1.11),
    "Ibovespa μ 17%, σ 25%": (1.52, 1.57),
    "Ação μ 16%, σ 15%": (1.56, 1.57),
}
CUSTOS_DO_RELATORIO = CustosBR(
    emolumentos_a_vista=0.001, emolumentos_no_leilao=0.001, taxa_cripto_por_lado=0.001
)
CENARIOS_DO_DAY_TRADE = ("Ibovespa μ 17%, σ 25%", "Ação μ 16%, σ 15%")
REGRAS_COM_VENDA = ("full", "constant_mix")
NOMES_DAS_REGRAS = {
    "comprar_e_segurar": "Comprar e segurar",
    "full": "SD Full (sd8, s = 50%)",
    "ath": "SD ATH-only",
    "constant_mix": "Constant-mix 50% (banda σ/√F)",
}
REGUA = "comprar_e_segurar"
abrir_registro = rodar_p0_3.abrir_registro


# --- dados -----------------------------------------------------------------------------------------------


def carregar_historico(
    pasta: Path = PASTA_DA_PESQUISA,
    pasta_da_binance: Path = rodar_tendencia_cripto.PASTA_DA_BINANCE,
    pasta_do_mt5: Path = dados_b3.PASTA_DO_MT5,
) -> dict[str, tuple[pd.Series, pd.Series, str, int]]:
    """BTC em reais (dias corridos) e BOVA11 (pregões), cada um com o caixa a CDI, só o desenvolvimento."""
    precos, cdi, _ = rodar_tendencia_cripto.carregar_tabelas(pasta, pasta_da_binance)
    btc = precos["BTC"].dropna()
    barras = recortar_desenvolvimento(
        dados_b3.so_com_negocio_desde_o_inicio(
            dados_b3.barras_do_yahoo(pasta_do_mt5 / dados_b3.ARQUIVO_DO_BOVA11)
        )
    )
    pregoes = pd.DatetimeIndex(barras.index)
    cdi_b3 = (
        dados_p0_3.carregar_cdi(
            pregoes.min(), pd.Timestamp(criterio_quant.FIM_DO_DESENVOLVIMENTO), pasta
        )
        .reindex(pregoes)
        .ffill()
        .fillna(0.0)
    )
    historico = {
        "BTC em reais": (btc, cdi.reindex(btc.index).fillna(0.0), "cripto", 365),
        "BOVA11": (barras["fechamento"], cdi_b3, "etf", 252),
    }
    for fechamento, caixa, _, _ in historico.values():
        exigir_sem_holdout(fechamento)
        exigir_sem_holdout(caixa)
    return historico


# --- as simulações ---------------------------------------------------------------------------------------


def parametros_de(
    classe: str, dias_por_ano: int, regra: str, **mudancas: object
) -> Parametros:
    base = Parametros(
        regra=regra,
        classe=classe,
        dias_por_ano=dias_por_ano,
        execucoes_desejadas=sd.EXECUCOES_DESEJADAS[classe],
    )
    return sd.com(base, **mudancas)


def rodar_regras(
    caminhos: sd.Caminhos,
    classe: str,
    dias_por_ano: int,
    regras: tuple[str, ...] = sd.REGRAS,
    **mudancas: object,
) -> dict[str, dict]:
    """Cada regra nos mesmos caminhos, com a régua (comprar e segurar) de cada caminho ao lado."""

    def simular(regra: str) -> sd.Resultado:
        return sd.simular(
            caminhos, parametros_de(classe, dias_por_ano, regra, **mudancas)
        )

    regua = simular(REGUA)
    return {
        regra: sd.resumir(regua if regra == REGUA else simular(regra), regua)
        for regra in (REGUA, *(r for r in regras if r != REGUA))
    }


def _tem_isencao(classe: str) -> bool:
    return CustosBR().isencao_no_mes(classe, day_trade=False) > 0


def monte_carlo(caminhos: int = sd.CAMINHOS, anos: int = sd.ANOS) -> dict[str, dict]:
    """Os quatro cenários: base, caixa a zero, teto, versão do relatório e, no ETF, como ações."""
    saida = {}
    for c in CENARIOS:
        args = (c.classe, c.dias_por_ano)
        com_cdi = sd.caminhos_gbm(c, CDI_DO_ESTUDO, caminhos=caminhos, anos=anos)
        sem_cdi = sd.caminhos_gbm(c, 0.0, caminhos=caminhos, anos=anos)
        do_relatorio = sd.caminhos_gbm(
            c, CAIXA_DO_RELATORIO[c.nome], caminhos=caminhos, anos=anos
        )
        cenario = {
            "base": rodar_regras(com_cdi, *args),
            "caixa_a_zero": rodar_regras(sem_cdi, *args),
            "relatorio": rodar_regras(
                do_relatorio,
                *args,
                regras=(REGUA, "full"),
                custos=CUSTOS_DO_RELATORIO,
                com_imposto=False,
                caixa_negativo=True,
                execucao="limitada",
            ),
        }
        if _tem_isencao(c.classe):
            cenario["teto"] = rodar_regras(
                com_cdi, *args, regras=REGRAS_COM_VENDA, teto_de_vendas=True
            )
        if c.classe == "etf":
            cenario["como_acoes"] = rodar_regras(com_cdi, "acoes", c.dias_por_ano)
        saida[c.nome] = cenario
    return saida


def day_trade(caminhos: int = sd.CAMINHOS, anos: int = sd.ANOS) -> dict[str, dict]:
    """Ordens limitadas no dia (8 preços por dia), com e sem o bloqueio de day trade."""
    saida = {}
    for c in CENARIOS:
        if c.nome not in CENARIOS_DO_DAY_TRADE:
            continue
        precos = sd.caminhos_gbm(
            c,
            CDI_DO_ESTUDO,
            caminhos=caminhos,
            anos=anos,
            passos_por_dia=sd.PASSOS_NO_DIA,
        )
        args = (c.classe, c.dias_por_ano)
        saida[c.nome] = {
            "livre": rodar_regras(
                precos, *args, regras=REGRAS_COM_VENDA, execucao="limitada"
            ),
            "bloqueado": rodar_regras(
                precos,
                *args,
                regras=REGRAS_COM_VENDA,
                execucao="limitada",
                bloquear_day_trade=True,
            ),
        }
    return saida


def historico(
    series: dict[str, tuple[pd.Series, pd.Series, str, int]],
    anos: int = sd.ANOS,
) -> dict[str, dict]:
    """Janelas de `anos` anos a partir de cada mês: base, caixa a zero e as variações do Brasil."""
    saida = {}
    for nome, (fechamento, caixa, classe, dias_por_ano) in series.items():
        tamanho = {"dias": anos * dias_por_ano + 1, "aquecimento": dias_por_ano}
        com_cdi, comecos = sd.janelas_do_historico(fechamento, caixa, **tamanho)
        sem_cdi, _ = sd.janelas_do_historico(
            fechamento, pd.Series(0.0, index=caixa.index), **tamanho
        )
        args = (classe, dias_por_ano)
        serie = {
            "janelas": len(comecos),
            "primeiro_comeco": comecos[0].date().isoformat(),
            "ultimo_comeco": comecos[-1].date().isoformat(),
            "primeiro_preco": fechamento.index[0].date().isoformat(),
            "ultimo_preco": fechamento.index[-1].date().isoformat(),
            "base": rodar_regras(com_cdi, *args),
            "caixa_a_zero": rodar_regras(sem_cdi, *args),
        }
        if _tem_isencao(classe):
            serie["teto"] = rodar_regras(
                com_cdi, *args, regras=REGRAS_COM_VENDA, teto_de_vendas=True
            )
        if classe == "cripto":
            serie["com_cambio"] = rodar_regras(com_cdi, *args, com_cambio=True)
        if classe == "etf":
            serie["como_acoes"] = rodar_regras(com_cdi, "acoes", dias_por_ano)
        saida[nome] = serie
    return saida


def reexecucao_identica(caminhos: int = sd.CAMINHOS, anos: int = sd.ANOS) -> bool:
    """A mesma semente dá o mesmo resultado, caminho a caminho."""
    c = CENARIOS[0]

    def rodar() -> str:
        precos = sd.caminhos_gbm(c, CDI_DO_ESTUDO, caminhos=caminhos, anos=anos)
        return sd.hash_do_resultado(
            sd.simular(precos, parametros_de(c.classe, c.dias_por_ano, "full"))
        )

    return rodar() == rodar()


def especificacao(
    series: dict[str, tuple[pd.Series, pd.Series, str, int]], caminhos: int, anos: int
) -> dict:
    return {
        "pesquisa": FICHA,
        "pre_registro": criterio_quant.HASH_DO_CRITERIO,
        "versao_do_codigo": sd.VERSAO,
        "cenarios": [asdict(c) for c in CENARIOS],
        "cdi_do_estudo": CDI_DO_ESTUDO,
        "caminhos": caminhos,
        "anos": anos,
        "semente": sd.SEMENTE,
        "passos_no_dia": sd.PASSOS_NO_DIA,
        "capital": sd.CAPITAL_INICIAL,
        "parametros": Parametros().especificacao(),
        "historico": {
            nome: {
                "classe": classe,
                "inicio": f.index[0].date().isoformat(),
                "fim": f.index[-1].date().isoformat(),
                "hash": dados_b3.hash_da_tabela(f),
            }
            for nome, (f, _, classe, _) in series.items()
        },
    }


def executar(
    series: dict[str, tuple[pd.Series, pd.Series, str, int]],
    registro: Registro,
    caminhos: int = sd.CAMINHOS,
    anos: int = sd.ANOS,
) -> dict:
    """Registra a tentativa antes de qualquer número, simula tudo e guarda no registro."""
    criterio_quant.conferir()
    tentativa = registro.registrar(FICHA, NOME, especificacao(series, caminhos, anos))
    saida = {
        "id": tentativa,
        "caminhos": caminhos,
        "anos": anos,
        "monte_carlo": monte_carlo(caminhos, anos),
        "day_trade": day_trade(caminhos, anos),
        "historico": historico(series, anos),
        "reexecucao_identica": reexecucao_identica(min(caminhos, 200), anos),
    }
    registro.salvar_resultado(tentativa, saida)
    return saida


# --- o relatório -----------------------------------------------------------------------------------------


CABECALHO = (
    "| Regra | Mediana | p5 | p95 | Média | Vence comprar e segurar | Execuções/ano | "
    "IR ÷ capital | Maior queda (mediana) |\n|---|---|---|---|---|---|---|---|---|"
)


def _linha(regra: str, r: dict) -> str:
    vence = "-" if regra == REGUA else f"{r['vence_a_regua']:.0%}"
    return (
        f"| {NOMES_DAS_REGRAS[regra]} | {r['mediana']:.2f}× | {r['p5']:.2f}× | {r['p95']:.2f}× | "
        f"{r['media']:.2f}× | {vence} | {r['execucoes_por_ano']:.1f} | {r['imposto']:.1%} | "
        f"{r['maior_queda']:.0%} |"
    )


def _tabela(regras: dict[str, dict]) -> list[str]:
    return [CABECALHO, *(_linha(regra, r) for regra, r in regras.items()), ""]


def vantagem(regras: dict[str, dict], regra: str) -> float:
    """Mediana da regra − mediana de comprar e segurar (em múltiplos do capital)."""
    return regras[regra]["mediana"] - regras[REGUA]["mediana"]


def _brasil(nome: str, cenario: dict) -> list[str]:
    linhas = [
        (
            f"- **{nome}.** (a) Constant-mix − comprar e segurar (mediana): "
            f"{vantagem(cenario['base'], 'constant_mix'):+.2f}× com caixa a CDI e "
            f"{vantagem(cenario['caixa_a_zero'], 'constant_mix'):+.2f}× com caixa a 0%; vence em "
            f"{cenario['base']['constant_mix']['vence_a_regua']:.0%} e "
            f"{cenario['caixa_a_zero']['constant_mix']['vence_a_regua']:.0%} dos caminhos."
        )
    ]
    if "teto" in cenario:
        partes = [
            f"{NOMES_DAS_REGRAS[r]} {cenario['teto'][r]['mediana'] - cenario['base'][r]['mediana']:+.3f}× "
            f"({cenario['teto'][r]['vendas_travadas']:.1f} vendas travadas por caminho)"
            for r in REGRAS_COM_VENDA
        ]
        linhas.append(f"  (b) Teto de vendas da isenção: {'; '.join(partes)}.")
    if "como_acoes" in cenario:
        partes = [
            f"{NOMES_DAS_REGRAS[r]} {cenario['base'][r]['mediana']:.2f}× como ETF e "
            f"{cenario['como_acoes'][r]['mediana']:.2f}× como ações"
            for r in REGRAS_COM_VENDA
        ]
        linhas.append(f"  (d) Sem e com a isenção de R$ 20 mil: {'; '.join(partes)}.")
    return linhas


def escrever_relatorio(
    saida: dict, pasta: Path = PASTA_DA_PESQUISA / "relatorios"
) -> Path:
    linhas = [
        f"# Synthetic Dividend e rebalanceamento (ficha P0-7): rodada do pré-registro quant v{criterio_quant.VERSAO}",
        "",
        (
            f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC. Tentativa {saida['id']} da família "
            "P0-7. Estudo, não candidata: não passa pelo critério da seção 5."
        ),
        (
            f"Monte Carlo: GBM, {saida['caminhos']} caminhos, {saida['anos']} anos, semente {sd.SEMENTE}; capital "
            f"R$ {sd.CAPITAL_INICIAL:,.0f}; múltiplo = patrimônio liquidado no último dia (com custo e IR "
            "dessa venda) ÷ capital."
        ),
        f"Reexecução idêntica: {'sim' if saida['reexecucao_identica'] else 'NÃO'}.",
        "",
        f"## 1. Monte Carlo com caixa a CDI de {CDI_DO_ESTUDO:.0%}, custos e IR do Brasil, ordem no fechamento de D+1",
        "",
    ]
    for nome, cenario in saida["monte_carlo"].items():
        linhas += [f"### {nome}", "", *_tabela(cenario["base"])]
    linhas += [
        "## 2. A versão do relatório (10 bps por lado, sem IR, caixa negativo livre, ordem no próprio fechamento)",
        "",
        "| Cenário | Comprar e segurar (aqui; relatório) | SD8 (aqui; relatório) | SD8 vence |",
        "|---|---|---|---|",
    ]
    for nome, cenario in saida["monte_carlo"].items():
        r = cenario["relatorio"]
        bh, sd8 = MEDIANAS_DO_RELATORIO[nome]
        linhas.append(
            f"| {nome} | {r[REGUA]['mediana']:.2f}×; {bh:.2f}× | {r['full']['mediana']:.2f}×; {sd8:.2f}× | "
            f"{r['full']['vence_a_regua']:.0%} |"
        )
    linhas += [
        "",
        f"## 3. Histórico (janelas de {saida['anos']} anos começando em cada mês, desenvolvimento)",
        "",
    ]
    for nome, serie in saida["historico"].items():
        linhas += [
            f"### {nome}",
            "",
            (
                f"Preços de {serie['primeiro_preco']} a {serie['ultimo_preco']}; {serie['janelas']} janelas, "
                f"começando de {serie['primeiro_comeco']} a {serie['ultimo_comeco']} (sobrepostas: os "
                "percentis não são independentes)."
            ),
            "",
            *_tabela(serie["base"]),
        ]
        if "com_cambio" in serie:
            linhas += [
                "Com IOF e spread de câmbio em toda ordem:",
                "",
                *_tabela(serie["com_cambio"]),
            ]
    linhas += ["## 4. Testes do Brasil", ""]
    for nome, cenario in {**saida["monte_carlo"], **saida["historico"]}.items():
        linhas += _brasil(nome, cenario)
    linhas += [
        "",
        "(c) Ordens limitadas no dia (8 preços por dia), sem e com o bloqueio de day trade:",
        "",
    ]
    for nome, cenario in saida["day_trade"].items():
        for regra in REGRAS_COM_VENDA:
            livre, bloqueado = cenario["livre"][regra], cenario["bloqueado"][regra]
            linhas.append(
                f"- {nome}, {NOMES_DAS_REGRAS[regra]}: mediana {livre['mediana']:.3f}× livre e "
                f"{bloqueado['mediana']:.3f}× bloqueado; {livre['dias_de_day_trade']:.1f} dias com day trade "
                f"por caminho sem o bloqueio; vence comprar e segurar em {livre['vence_a_regua']:.0%} e "
                f"{bloqueado['vence_a_regua']:.0%}."
            )
    linhas += [
        "",
        "## Limites e cuidados",
        "",
        "- Estudo: não é candidata a dinheiro e não passa pelo critério (pré-registro, ficha P0-7).",
        "- GBM tem volatilidade constante e sem saltos; o histórico é um caminho só, em janelas sobrepostas.",
        "- O Monte Carlo usa um calendário sintético; só os meses (IR e DARF) dependem dele.",
        "- Sem impacto de mercado; o custo de aquisição do IR não inclui as taxas (erra contra quem vende).",
        "- Sem caixa negativo (salvo na versão do relatório): a recompra do SD fica limitada ao caixa.",
        "- O teto e a isenção dependem do capital (R$ 200 mil); com mais capital o teto pesa mais.",
        "- Day trade em cripto segue a tabela de `custos_br` (20%); o teste (c) roda só na B3.",
        "- Toda execução conta como tentativa da ficha P0-7 (orçamento 4).",
        "- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.",
    ]
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"rodada_sd_{datetime.now(UTC):%Y%m%d_%H%M}.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def main() -> int:
    saida = executar(carregar_historico(), abrir_registro())
    print(escrever_relatorio(saida).read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
