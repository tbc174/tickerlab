"""Roda a ficha P0-1 (tendência em cripto em reais) contra o critério do pré-registro quant v0.1.

    python -m trader.estrategias.rodar_tendencia_cripto

**Cada execução conta como tentativa** da família P0-1 no registro `pesquisa_quant/registro.db`
(orçamento de 10). O candidato é fixo ("BTC e ETH 50/50"); vizinhos do platô, estresse, bruto,
réguas, freio, os testes do Brasil e as verificações ficam dentro da mesma tentativa (seção 9).
Só roda se o texto do pré-registro for o aprovado (hash) e só com dados até o fim do
desenvolvimento (08/09/2023).

O critério anualiza com 252: toda série diária (em dias corridos) entra na evidência composta em
dias úteis (sábado e domingo somados à segunda, `avaliacao.para_dias_uteis`). O DSR conta o
candidato e os seis vizinhos como as séries testadas (não há alternativas pré-registradas).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trader import avaliacao, criterio_quant, freios
from trader.estrategias import dados_tendencia_cripto as dados
from trader.estrategias import rodar_p0_3
from trader.estrategias import tendencia_cripto as tc
from trader.holdout import exigir_sem_holdout, recortar_desenvolvimento
from trader.registro import Registro

PASTA_DA_PESQUISA = dados.PASTA_DA_PESQUISA
PASTA_DA_BINANCE = dados.PASTA_DA_BINANCE
FICHA = "P0-1"
CANDIDATO = tc.CANDIDATO
NOME = "p0_1_tendencia_btc_eth"
FONTE = "Binance Vision (BTCUSDT, ETHUSDT) × dólar PTAX da véspera (SGS 1)"
VIZINHOS: dict[str, dict] = {
    "vol_alvo_0.20": {"vol_alvo": 0.20},
    "vol_alvo_0.30": {"vol_alvo": 0.30},
    "janela_da_vol_72": {"janela_da_vol": 72},
    "janela_da_vol_108": {"janela_da_vol": 108},
    "janelas_x0.8": {
        "janelas": tc.escalar_janelas(tc.JANELAS, criterio_quant.FATOR_DO_PLATO_ABAIXO)
    },
    "janelas_x1.2": {
        "janelas": tc.escalar_janelas(tc.JANELAS, criterio_quant.FATOR_DO_PLATO_ACIMA)
    },
}
FRACAO_DO_CORTE = rodar_p0_3.FRACAO_DO_CORTE
T_ALVO = 3.0  # a régua "anos ≈ (t/SR)²" do pré-registro usa o t do item A5
abrir_registro = rodar_p0_3.abrir_registro


def carregar_tabelas(
    pasta: Path = PASTA_DA_PESQUISA, pasta_da_binance: Path = PASTA_DA_BINANCE
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Preços em reais, retorno do caixa e volume conhecido, em dias corridos, só o desenvolvimento."""
    tabelas = {
        ativo: dados.carregar_par(par, pasta_da_binance)
        for ativo, par in dados.PARES.items()
    }
    dolar = dados.carregar_dolar(pasta=pasta)
    precos, volumes = dados.montar_precos(tabelas, dolar)
    precos = recortar_desenvolvimento(precos)
    volumes = dados.volume_medio_conhecido(recortar_desenvolvimento(volumes))
    cdi = dados.carregar_cdi_corrido(pd.DatetimeIndex(precos.index), pasta)
    for tabela in (precos, volumes, cdi):
        exigir_sem_holdout(tabela)
    return precos, cdi, volumes


def especificacao(precos: pd.DataFrame, parametros: tc.Parametros) -> dict:
    return {
        "pesquisa": FICHA,
        "candidato": CANDIDATO,
        "pre_registro": criterio_quant.HASH_DO_CRITERIO,
        "versao_do_codigo": tc.VERSAO,
        "fonte": FONTE,
        "hash_dos_dados": dados.hash_da_tabela(precos),
        "inicio": precos.index.min().date().isoformat(),
        "fim": precos.index.max().date().isoformat(),
        **parametros.especificacao(),
    }


def anos_para_t(sharpe: float, t: float = T_ALVO) -> float:
    """A régua do pré-registro: anos necessários ≈ (t ÷ SR)²; infinito se o Sharpe não é positivo."""
    return (t / sharpe) ** 2 if sharpe > 0 else float("inf")


def executar(
    precos: pd.DataFrame,
    cdi: pd.Series,
    volumes: pd.DataFrame,
    registro: Registro,
    capital: float = tc.CAPITAL_INICIAL,
) -> dict:
    """Registra a tentativa, simula tudo, avalia e guarda no registro."""
    criterio_quant.conferir()
    parametros = tc.Parametros()
    tentativa = registro.registrar(FICHA, NOME, especificacao(precos, parametros))
    fator = criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE

    def rodar(p: tc.Parametros, caixa: pd.Series = cdi) -> tc.Resultado:
        return tc.simular(precos, caixa, volumes, p, capital)

    def sharpe_do_excesso(retorno: pd.Series) -> float:
        return tc.sharpe_do_excesso(retorno, cdi)

    base = rodar(parametros)
    estresse = rodar(parametros.em_estresse(fator))
    bruto = rodar(
        tc.com(parametros, custos=tc.SEM_CUSTOS, fator_de_impacto=0.0, com_cambio=False)
    )
    futuro = rodar(tc.com(parametros, olhar_o_futuro=True))
    de_novo = rodar(parametros)
    vizinhos = {n: rodar(tc.com(parametros, **m)) for n, m in VIZINHOS.items()}
    vizinhos_estresse = {
        n: rodar(tc.com(parametros, **m).em_estresse(fator))
        for n, m in VIZINHOS.items()
    }
    caixa_a_zero = rodar(parametros, pd.Series(0.0, index=precos.index))
    sem_cambio = rodar(tc.com(parametros, com_cambio=False))
    regua_btc = tc.comprar_e_segurar(precos["BTC"], volumes["BTC"], parametros, capital)
    cdi_do_periodo = cdi.reindex(base.retorno.index)
    corte = precos.index[int(len(precos) * FRACAO_DO_CORTE)]
    cortar = tc.cortar_o_futuro_nao_muda_o_passado(
        precos, cdi, volumes, parametros, corte, capital
    )
    acaso = tc.p_valor_do_acaso(
        base.exposicao,
        precos.pct_change().fillna(0.0),
        cdi,
        parametros.custos.taxa_cripto_por_lado,
        sorteios=criterio_quant.SINAIS_DESLOCADOS,
    )
    tentativas_totais = (
        criterio_quant.tentativas_anteriores() + registro.total_para_o_dsr()
    )

    uteis = tc.em_dias_uteis
    candidatos = pd.DataFrame(
        {
            CANDIDATO: uteis(base.retorno),
            **{n: uteis(r.retorno) for n, r in vizinhos.items()},
        }
    )
    candidatos_estresse = pd.DataFrame(
        {
            CANDIDATO: uteis(estresse.retorno),
            **{n: uteis(r.retorno) for n, r in vizinhos_estresse.items()},
        }
    )
    sharpes_vizinhos = {n: sharpe_do_excesso(r.retorno) for n, r in vizinhos.items()}
    sharpe_bruto = sharpe_do_excesso(bruto.retorno)
    reguas = {"BTC comprar e segurar": uteis(regua_btc), "CDI": uteis(cdi_do_periodo)}
    evidencia = criterio_quant.Evidencia(
        candidato=uteis(base.retorno),
        cdi=uteis(cdi_do_periodo),
        candidatos=candidatos,
        candidatos_estresse=candidatos_estresse,
        sharpe_bruto=sharpe_bruto,
        sharpes_vizinhos=sharpes_vizinhos,
        reguas=reguas,
        p_valor_do_acaso=acaso["p_valor"],
        sharpe_olhando_o_futuro=sharpe_do_excesso(futuro.retorno),
        reexecucao_identica=tc.hash_do_resultado(de_novo) == tc.hash_do_resultado(base),
        cortar_o_futuro_nao_muda=cortar,
        tentativas_totais=tentativas_totais,
        nome_do_candidato=CANDIDATO,
    )
    veredito = criterio_quant.avaliar(evidencia)
    freado = freios.aplicar_freio(base.retorno, cdi)

    def resumo(r: tc.Resultado) -> dict:
        return {
            **avaliacao.resumir_serie(uteis(r.retorno)),
            "sharpe_365": avaliacao.sharpe(r.retorno, tc.DIAS_POR_ANO),
            "sharpe_do_excesso": sharpe_do_excesso(r.retorno),
            "exposicao_media": r.exposicao_media(),
            "giro": r.giro,
            "custos": float(r.custos.sum()),
            "cambio": float(r.cambio.sum()),
            "imposto": float(r.imposto.sum()),
            "meses_acima_da_isencao": r.meses_acima_da_isencao(),
            "caixa_minimo": r.caixa_minimo,
        }

    resumo_base = {
        **resumo(base),
        "queda_com_freio": avaliacao.maior_queda(freado.retorno),
        "disparos_do_freio": [d.date().isoformat() for d in freado.disparos],
        "voltas_do_freio": [d.date().isoformat() for d in freado.voltas],
    }
    anos = len(base.retorno) / tc.DIAS_POR_ANO
    brasil = {
        "retorno_anual_caixa_a_cdi": resumo_base["retorno_anual"],
        "retorno_anual_caixa_a_zero": avaliacao.resumir_serie(
            uteis(caixa_a_zero.retorno)
        )["retorno_anual"],
        "sharpe_caixa_a_zero": avaliacao.sharpe(uteis(caixa_a_zero.retorno)),
        "meses_acima_da_isencao": resumo_base["meses_acima_da_isencao"],
        "meses_simulados": len(base.ir),
        "imposto_total": resumo_base["imposto"],
        "imposto_por_ano": resumo_base["imposto"] / anos,
        "cambio_total": resumo_base["cambio"],
        "sharpe_do_excesso_sem_cambio": sharpe_do_excesso(sem_cambio.retorno),
    }
    inicio_das_series = {
        ativo: precos[ativo].first_valid_index().date().isoformat()
        for ativo in tc.ATIVOS
    }
    saida = {
        "id": tentativa,
        "veredito": veredito,
        "resumo": resumo_base,
        "estresse": resumo(estresse),
        "bruto": sharpe_bruto,
        "vizinhos": sharpes_vizinhos,
        "reguas": {n: avaliacao.resumir_serie(r) for n, r in reguas.items()},
        "acaso": acaso,
        "brasil": brasil,
        "tentativas_totais": tentativas_totais,
        "inicio_das_series": inicio_das_series,
        "primeiro_dia_simulado": base.retorno.index[0].date().isoformat(),
        "anos_para_t3": anos_para_t(resumo_base["sharpe_do_excesso"]),
        "periodo": (
            precos.index.min().date().isoformat(),
            precos.index.max().date().isoformat(),
        ),
    }
    registro.salvar_resultado(
        tentativa, {**saida, "veredito": veredito.para_registro()}
    )
    return saida


def _veredito_em_linhas(veredito: criterio_quant.Veredito) -> list[str]:
    situacao = "APROVADA" if veredito.aprovado else "REPROVADA"
    if veredito.reprovados:
        situacao += f" (falhou em {', '.join(veredito.reprovados)})"
    if veredito.inconclusivo:
        situacao += f"; inconclusivo: {veredito.motivo_inconclusivo}"
    return [
        f"### {CANDIDATO}: {situacao}",
        "",
        "| Item | O quê | Valor | Limite | Passou |",
        "|---|---|---|---|---|",
        *(
            f"| {i.codigo} | {i.descricao} | {'-' if i.valor is None else f'{i.valor:.3f}'} | {i.limite} | {'sim' if i.passou else 'NÃO'} |"
            for i in veredito.itens
        ),
        "",
    ]


def _linha(nome: str, r: dict) -> str:
    return (
        f"| {nome} | {r['sharpe_do_excesso']:.2f} | {r['sharpe']:.2f} | {r['sharpe_365']:.2f} | "
        f"{r['retorno_anual']:.1%} | {r['volatilidade_anual']:.1%} | {r['maior_queda']:.1%} | "
        f"{r['exposicao_media']:.2f} | {r['giro']:.1f} | {r['custos'] / tc.CAPITAL_INICIAL:.1%} | "
        f"{r['imposto'] / tc.CAPITAL_INICIAL:.1%} | {r['meses_acima_da_isencao']} |"
    )


def _regua_em_linha(nome: str, r: dict) -> str:
    sharpe = "-" if nome == "CDI" else f"{r['sharpe']:.2f}"
    return f"| {nome} | {sharpe} | {r['retorno_anual']:.1%} | {r['maior_queda']:.1%} |"


def escrever_relatorio(
    saida: dict, pasta: Path = PASTA_DA_PESQUISA / "relatorios"
) -> Path:
    cabecalho = (
        "| Versão | Sharpe do excesso | Sharpe (252) | Sharpe (365) | Retorno anual | Volatilidade | "
        "Maior queda | Exposição média | Giro/ano | Custos ÷ capital | IR ÷ capital | Meses com IR |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    inicio, fim = saida["periodo"]
    r = saida["resumo"]
    b = saida["brasil"]
    acaso = saida["acaso"]
    linhas = [
        f"# Tendência em cripto em reais (ficha P0-1): rodada do pré-registro quant v{criterio_quant.VERSAO}",
        "",
        f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC. Dados de {inicio} a {fim} (desenvolvimento; holdout lacrado).",
        (
            f"Primeiro preço de cada série: {saida['inicio_das_series']}; primeiro dia simulado (depois do "
            f"aquecimento de {tc.AQUECIMENTO_EM_DIAS} dias): {saida['primeiro_dia_simulado']}."
        ),
        f"Tentativas contadas no DSR: {saida['tentativas_totais']}.",
        (
            f"Régua do tempo: anos necessários ≈ (t ÷ SR)²; com t = {T_ALVO:.0f} e o Sharpe do excesso "
            f"medido ({r['sharpe_do_excesso']:.2f}) seriam {saida['anos_para_t3']:.0f} anos."
        ),
        "",
        "## Veredito (seção 5 do pré-registro)",
        "",
        *_veredito_em_linhas(saida["veredito"]),
        "## O candidato (custos base) e o estresse",
        "",
        cabecalho,
        _linha("base", r),
        _linha("estresse (custos × 2, Y = 2, spread × 2)", saida["estresse"]),
        "",
        (
            f"Com freio de 40%: maior queda {r['queda_com_freio']:.1%}; disparos "
            f"{r['disparos_do_freio'] or 'nenhum'}; voltas {r['voltas_do_freio'] or 'nenhuma'}. "
            f"Menor caixa ÷ patrimônio: {r['caixa_minimo']:.2f}."
        ),
        "",
        "## Teste do Brasil (ficha P0-1)",
        "",
        (
            f"- (a) Caixa a CDI contra caixa a 0%: retorno anual {b['retorno_anual_caixa_a_cdi']:.1%} contra "
            f"{b['retorno_anual_caixa_a_zero']:.1%}; Sharpe {r['sharpe']:.2f} contra {b['sharpe_caixa_a_zero']:.2f}."
        ),
        (
            f"- (b) Meses acima do teto de R$ 35 mil de vendas: {b['meses_acima_da_isencao']} de "
            f"{b['meses_simulados']}; imposto total R$ {b['imposto_total']:,.0f} "
            f"(R$ {b['imposto_por_ano']:,.0f} por ano)."
        ),
        (
            f"- (c) IOF e spread de câmbio: R$ {b['cambio_total']:,.0f} no período; Sharpe do excesso sem o "
            f"câmbio (a série em USDT) {b['sharpe_do_excesso_sem_cambio']:.2f} contra {r['sharpe_do_excesso']:.2f}."
        ),
        "",
        "## Réguas, platô e bruto",
        "",
        "| Régua | Sharpe | Retorno anual | Maior queda |",
        "|---|---|---|---|",
        *(_regua_em_linha(n, x) for n, x in saida["reguas"].items()),
        "",
        "| Vizinho | Sharpe do excesso |",
        "|---|---|",
        *(f"| {v} | {s:.2f} |" for v, s in saida["vizinhos"].items()),
        f"| bruto (sem custo, imposto, impacto nem câmbio) | {saida['bruto']:.2f} |",
        "",
        (
            f"Contra o acaso: Sharpe real {acaso['sharpe_real']:.2f}, percentil 95 dos sinais "
            f"deslocados {acaso['percentil_95']:.2f}, p-valor {acaso['p_valor']:.3f}."
        ),
        "",
        "## Limites e cuidados",
        "",
        "- Desenvolvimento só: nada aqui diz o que o holdout vai mostrar; abri-lo é decisão escrita do Tiago.",
        "- Dados do Binance Vision (uso interno) em USDT, convertidos pelo dólar PTAX da véspera; a série é a mesma do começo ao fim.",
        f"- Não negocia diferença menor que {tc.BANDA_MINIMA:.1%} do patrimônio; o custo de aquisição do IR não inclui as taxas (erra contra a estratégia).",
        "- O DARF sai do caixa mesmo que ele fique negativo (empréstimo ao CDI); o IR dos meses que não venceram é pago no último dia dos dados.",
        "- O DSR conta o candidato e os seis vizinhos como séries testadas; o critério anualiza com 252 (fim de semana composto na segunda).",
        "- Toda execução conta como tentativa da ficha P0-1 (orçamento 10).",
        "- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.",
    ]
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"rodada_tendencia_cripto_{datetime.now(UTC):%Y%m%d_%H%M}.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def main() -> int:
    precos, cdi, volumes = carregar_tabelas()
    saida = executar(precos, cdi, volumes, abrir_registro())
    print(escrever_relatorio(saida).read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
