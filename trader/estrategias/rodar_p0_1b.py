"""Roda a ficha P0-1b (tendência em cripto no par em reais) contra o critério do pré-registro quant v0.2.

    python -I -m trader.estrategias.rodar_p0_1b

**Cada execução conta como tentativa** da família P0-1b no registro único (orçamento de 2; uma
terceira execução é recusada antes de registrar). O candidato é fixo ("BTCBRL e ETHBRL 50/50");
vizinhos do platô (os seis da P0-1 e a banda ±20%), estresse, bruto, réguas, freio, o teste do
Brasil e as verificações ficam dentro da mesma tentativa. Só roda se o texto do pré-registro for o
aprovado (hash) e só com dados até o fim do desenvolvimento (08/09/2023).

O teste do Brasil (c) roda a P0-1 sem mudança, na série dela (BTCUSDT e ETHUSDT × PTAX da
véspera), e corta o resultado nos dias simulados da P0-1b: é uma comparação dentro desta tentativa,
não uma tentativa nova da P0-1 (a regra e a série dela não mudam).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trader import avaliacao, criterio_quant, freios
from trader.estrategias import dados_cripto_brl as dados
from trader.estrategias import dados_tendencia_cripto as dados_p0_1
from trader.estrategias import rodar_tendencia_cripto as rodar_p0_1
from trader.estrategias import tendencia_cripto as tc
from trader.estrategias import tendencia_cripto_brl as brl
from trader.holdout import exigir_sem_holdout, recortar_desenvolvimento
from trader.registro import Registro

PASTA_DA_PESQUISA = dados.PASTA_DA_PESQUISA
FICHA = brl.FICHA
CANDIDATO = brl.CANDIDATO
NOME = "p0_1b_tendencia_btcbrl_ethbrl"
FONTE = "Binance Vision (BTCBRL, ETHBRL), em reais, sem câmbio"
VIZINHOS: dict[str, dict] = {
    **rodar_p0_1.VIZINHOS,
    "banda_0.16": {
        "banda": round(brl.BANDA * criterio_quant.FATOR_DO_PLATO_ABAIXO, 10)
    },
    "banda_0.24": {"banda": round(brl.BANDA * criterio_quant.FATOR_DO_PLATO_ACIMA, 10)},
}
FRACAO_DO_CORTE = rodar_p0_1.FRACAO_DO_CORTE
T_ALVO = rodar_p0_1.T_ALVO
anos_para_t = rodar_p0_1.anos_para_t
abrir_registro = rodar_p0_1.abrir_registro

Tabelas = tuple[pd.DataFrame, pd.Series, pd.DataFrame]


class OrcamentoDaFichaEsgotadoError(RuntimeError):
    """A ficha já usou as tentativas que o pré-registro deu a ela."""


def carregar_tabelas(
    pasta: Path = PASTA_DA_PESQUISA, pasta_brl: Path = dados.PASTA_DA_BINANCE_BRL
) -> tuple[Tabelas, dict[str, str]]:
    """Preços e volumes em reais, retorno do caixa (só o desenvolvimento) e o 1º candle de cada par."""
    tabelas = dados.carregar_pares(pasta_brl)
    precos, volumes = dados.montar_precos(tabelas)
    precos = recortar_desenvolvimento(precos)
    volumes = dados_p0_1.volume_medio_conhecido(recortar_desenvolvimento(volumes))
    cdi = dados_p0_1.carregar_cdi_corrido(pd.DatetimeIndex(precos.index), pasta)
    for tabela in (precos, volumes, cdi):
        exigir_sem_holdout(tabela)
    return (precos, cdi, volumes), dados.primeiro_candle(tabelas)


def execucoes_da_ficha(registro: Registro) -> int:
    return sum(
        int(t["execucoes"])
        for t in registro.listar("desenvolvimento")
        if t["familia"] == FICHA
    )


def exigir_orcamento_da_ficha(registro: Registro) -> None:
    usadas = execucoes_da_ficha(registro)
    if usadas >= brl.ORCAMENTO:
        raise OrcamentoDaFichaEsgotadoError(
            f"a ficha {FICHA} já usou {usadas} de {brl.ORCAMENTO} tentativas"
        )


def especificacao(
    precos: pd.DataFrame,
    parametros: brl.Parametros,
    primeiro_candle: dict[str, str],
    precos_p0_1: pd.DataFrame,
) -> dict:
    return {
        "pesquisa": FICHA,
        "candidato": CANDIDATO,
        "pre_registro": criterio_quant.HASH_DO_CRITERIO,
        "versao_do_codigo": tc.VERSAO,
        "fonte": FONTE,
        "hash_dos_dados": dados_p0_1.hash_da_tabela(precos),
        "primeiro_candle": primeiro_candle,
        "inicio": precos.index.min().date().isoformat(),
        "fim": precos.index.max().date().isoformat(),
        "comparacao_p0_1": {
            "fonte": rodar_p0_1.FONTE,
            "hash_dos_dados": dados_p0_1.hash_da_tabela(precos_p0_1),
        },
        **parametros.especificacao(),
    }


def comparar_com_a_p0_1(p0_1: Tabelas, dias: pd.DatetimeIndex) -> dict:
    """Teste (c): a P0-1 sem mudança, na série dela, cortada nos dias simulados da P0-1b."""
    precos, cdi, volumes = p0_1
    com_cambio = tc.simular(precos, cdi, volumes, tc.Parametros())
    sem_cambio = tc.simular(
        precos, cdi, volumes, tc.com(tc.Parametros(), com_cambio=False)
    )
    if not dias.isin(com_cambio.retorno.index).all():
        raise ValueError("a série da P0-1 não cobre os dias simulados da P0-1b")

    def no_periodo(serie: pd.Series) -> pd.Series:
        return serie.reindex(dias)

    return {
        "sharpe_do_excesso": tc.sharpe_do_excesso(no_periodo(com_cambio.retorno), cdi),
        "sharpe_do_excesso_sem_cambio": tc.sharpe_do_excesso(
            no_periodo(sem_cambio.retorno), cdi
        ),
        "cambio_no_periodo": float(no_periodo(com_cambio.cambio).sum()),
        "custos_no_periodo": float(no_periodo(com_cambio.custos).sum()),
        "giro_no_periodo": float(
            no_periodo(com_cambio.negociado.abs().sum(axis=1)).sum()
            / (len(dias) / tc.DIAS_POR_ANO)
            / float(no_periodo(com_cambio.patrimonio).mean())
        ),
    }


def executar(
    precos: pd.DataFrame,
    cdi: pd.Series,
    volumes: pd.DataFrame,
    registro: Registro,
    p0_1: Tabelas,
    primeiro_candle: dict[str, str] | None = None,
    capital: float = tc.CAPITAL_INICIAL,
) -> dict:
    """Confere o texto e o orçamento, registra a tentativa, simula tudo, avalia e guarda."""
    criterio_quant.conferir()
    exigir_orcamento_da_ficha(registro)
    parametros = brl.Parametros()
    primeiro_candle = primeiro_candle or {
        a: precos[a].first_valid_index().date().isoformat() for a in tc.ATIVOS
    }
    tentativa = registro.registrar(
        FICHA, NOME, especificacao(precos, parametros, primeiro_candle, p0_1[0])
    )
    fator = criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE

    def rodar(p: brl.Parametros, caixa: pd.Series = cdi) -> brl.Resultado:
        return brl.simular(precos, caixa, volumes, p, capital)

    def sharpe_do_excesso(retorno: pd.Series) -> float:
        return tc.sharpe_do_excesso(retorno, cdi)

    base = rodar(parametros)
    estresse = rodar(parametros.em_estresse(fator))
    bruto = rodar(
        brl.com(
            parametros, custos=tc.SEM_CUSTOS, fator_de_impacto=0.0, spread_por_lado=0.0
        )
    )
    futuro = rodar(brl.com(parametros, olhar_o_futuro=True))
    de_novo = rodar(parametros)
    vizinhos = {n: rodar(brl.com(parametros, **m)) for n, m in VIZINHOS.items()}
    vizinhos_estresse = {
        n: rodar(brl.com(parametros, **m).em_estresse(fator))
        for n, m in VIZINHOS.items()
    }
    caixa_a_zero = rodar(parametros, pd.Series(0.0, index=precos.index))
    sem_banda = rodar(brl.com(parametros, banda=None))
    spread_de_leitura = rodar(
        brl.com(parametros, spread_por_lado=brl.SPREAD_DE_LEITURA)
    )
    regua_btc = brl.comprar_e_segurar(
        precos["BTC"], volumes["BTC"], parametros, capital
    )
    cdi_do_periodo = cdi.reindex(base.retorno.index)
    corte = precos.index[int(len(precos) * FRACAO_DO_CORTE)]
    cortar = brl.cortar_o_futuro_nao_muda_o_passado(
        precos, cdi, volumes, parametros, corte, capital
    )
    acaso = tc.p_valor_do_acaso(
        base.exposicao,
        precos.pct_change().fillna(0.0),
        cdi,
        parametros.custos.taxa_cripto_por_lado + parametros.spread_por_lado,
        sorteios=criterio_quant.SINAIS_DESLOCADOS,
    )
    comparacao = comparar_com_a_p0_1(p0_1, pd.DatetimeIndex(base.retorno.index))
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
    reguas = {
        "BTCBRL comprar e segurar": uteis(regua_btc),
        "CDI": uteis(cdi_do_periodo),
    }
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

    def resumo(r: brl.Resultado) -> dict:
        return {
            **avaliacao.resumir_serie(uteis(r.retorno)),
            "sharpe_365": avaliacao.sharpe(r.retorno, tc.DIAS_POR_ANO),
            "sharpe_do_excesso": sharpe_do_excesso(r.retorno),
            "exposicao_media": r.exposicao_media(),
            "giro": r.giro,
            "custos": float(r.custos.sum()),
            "spread": float(r.spread.sum()),
            "imposto": float(r.imposto.sum()),
            "meses_acima_da_isencao": r.meses_acima_da_isencao(),
            "ordens": int((r.negociado != 0).to_numpy().sum()),
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
        "p0_1_no_periodo": comparacao,
        "sem_banda": resumo(sem_banda),
    }
    saida = {
        "id": tentativa,
        "execucoes_da_ficha": execucoes_da_ficha(registro),
        "veredito": veredito,
        "resumo": resumo_base,
        "estresse": resumo(estresse),
        "spread_de_leitura": resumo(spread_de_leitura),
        "bruto": sharpe_bruto,
        "vizinhos": sharpes_vizinhos,
        "reguas": {n: avaliacao.resumir_serie(r) for n, r in reguas.items()},
        "acaso": acaso,
        "brasil": brasil,
        "tentativas_totais": tentativas_totais,
        "primeiro_candle": primeiro_candle,
        "primeiro_dia_simulado": base.retorno.index[0].date().isoformat(),
        "anos_simulados": anos,
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
        f"{r['exposicao_media']:.2f} | {r['giro']:.1f} | {r['ordens']} | "
        f"{r['custos'] / tc.CAPITAL_INICIAL:.1%} | {r['spread'] / tc.CAPITAL_INICIAL:.1%} | "
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
        "Maior queda | Exposição média | Giro/ano | Ordens | Custos ÷ capital | Spread ÷ capital | "
        "IR ÷ capital | Meses com IR |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    inicio, fim = saida["periodo"]
    r = saida["resumo"]
    b = saida["brasil"]
    c = b["p0_1_no_periodo"]
    acaso = saida["acaso"]
    linhas = [
        f"# Tendência em cripto no par em reais (ficha P0-1b): rodada do pré-registro quant v{criterio_quant.VERSAO}",
        "",
        f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC. Dados de {inicio} a {fim} (desenvolvimento; holdout lacrado).",
        (
            f"Primeiro candle de cada par: {saida['primeiro_candle']}; primeiro dia simulado (depois do "
            f"aquecimento de {tc.AQUECIMENTO_EM_DIAS} dias): {saida['primeiro_dia_simulado']} "
            f"({saida['anos_simulados']:.1f} anos simulados)."
        ),
        (
            f"Registro: linha {saida['id']}, execução {saida['execucoes_da_ficha']} de {brl.ORCAMENTO} da ficha. "
            f"Tentativas contadas no DSR: {saida['tentativas_totais']}."
        ),
        (
            f"Régua do tempo: anos necessários ≈ (t ÷ SR)²; com t = {T_ALVO:.0f} e o Sharpe do excesso "
            f"medido ({r['sharpe_do_excesso']:.2f}) seriam {saida['anos_para_t3']:.0f} anos."
        ),
        "",
        "## Veredito (seção 5 do pré-registro)",
        "",
        *_veredito_em_linhas(saida["veredito"]),
        "## O candidato (spread de 0,3% por lado) e o estresse",
        "",
        cabecalho,
        _linha("base", r),
        _linha("estresse (taxa × 2, Y = 2, spread do livro × 2)", saida["estresse"]),
        _linha("leitura: spread de 0,1% por lado", saida["spread_de_leitura"]),
        "",
        (
            f"Com freio de 40%: maior queda {r['queda_com_freio']:.1%}; disparos "
            f"{r['disparos_do_freio'] or 'nenhum'}; voltas {r['voltas_do_freio'] or 'nenhuma'}. "
            f"Menor caixa ÷ patrimônio: {r['caixa_minimo']:.2f}."
        ),
        "",
        "## Teste do Brasil (ficha P0-1b)",
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
            f"- (c) A P0-1 no mesmo período (BTCUSDT e ETHUSDT × PTAX): Sharpe do excesso {c['sharpe_do_excesso']:.2f} "
            f"com câmbio e {c['sharpe_do_excesso_sem_cambio']:.2f} sem; câmbio R$ {c['cambio_no_periodo']:,.0f} "
            f"no período; giro {c['giro_no_periodo']:.1f} por ano. A P0-1b: {r['sharpe_do_excesso']:.2f}."
        ),
        (
            f"- (d) Com e sem a banda: Sharpe do excesso {r['sharpe_do_excesso']:.2f} contra "
            f"{b['sem_banda']['sharpe_do_excesso']:.2f}; giro {r['giro']:.1f} contra {b['sem_banda']['giro']:.1f} "
            f"por ano; {r['ordens']} contra {b['sem_banda']['ordens']} ordens."
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
        f"| bruto (sem taxa, imposto, impacto nem spread) | {saida['bruto']:.2f} |",
        "",
        (
            f"Contra o acaso: Sharpe real {acaso['sharpe_real']:.2f}, percentil 95 dos sinais "
            f"deslocados {acaso['percentil_95']:.2f}, p-valor {acaso['p_valor']:.3f}."
        ),
        "",
        "## Limites e cuidados",
        "",
        "- **Esta ficha foi escolhida depois de ver o resultado da P0-1** (o câmbio era o maior custo); o DSR conta todas as tentativas anteriores, mas o viés de escolha não some.",
        "- Desenvolvimento só: nada aqui diz o que o holdout vai mostrar; abri-lo é decisão escrita do Tiago (e gasta o lacre da C-1 junto).",
        "- Poucos anos: os pares em reais começaram em outubro de 2020; com o aquecimento de 365 dias sobram menos de dois anos simulados.",
        "- Dados do Binance Vision (uso interno), já em reais; o livro em reais não tem histórico de spread: o critério usa 0,3% por lado, 0,1% é só leitura.",
        f"- A banda vem por cima da regra da P0-1: ordem menor que {tc.BANDA_MINIMA:.1%} do patrimônio continua sem sair; o custo de aquisição do IR não inclui as taxas (erra contra a estratégia).",
        "- O DARF sai do caixa mesmo que ele fique negativo (empréstimo ao CDI); o IR dos meses que não venceram é pago no último dia dos dados.",
        "- O DSR conta o candidato e os oito vizinhos como séries testadas; o critério anualiza com 252 (fim de semana composto na segunda).",
        "- O teste (c) roda a P0-1 sem mudança e corta o resultado; não é tentativa nova da P0-1.",
        f"- Toda execução conta como tentativa da ficha P0-1b (orçamento {brl.ORCAMENTO}).",
        "- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.",
    ]
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"rodada_p0_1b_{datetime.now(UTC):%Y%m%d_%H%M}.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def main() -> int:
    (precos, cdi, volumes), primeiro_candle = carregar_tabelas()
    p0_1 = rodar_p0_1.carregar_tabelas()
    saida = executar(precos, cdi, volumes, abrir_registro(), p0_1, primeiro_candle)
    relatorio = escrever_relatorio(saida)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(relatorio.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
