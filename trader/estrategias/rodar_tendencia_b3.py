"""Roda a ficha P0-2 (tendência na B3) contra o critério do pré-registro quant v0.1.

    python -m trader.estrategias.rodar_tendencia_b3

**Cada execução conta como tentativa** da família P0-2 no registro `pesquisa_quant/registro.db`
(orçamento de 8). O candidato é fixo (BOVA11); WIN e DI1 são as outras duas versões
pré-registradas, comparadas dentro da mesma tentativa, e a cesta das 10 maiores do Ibovespa é só
a comparação de imposto do teste do Brasil (b). Vizinhos do platô, estresse, bruto, réguas, freio
e as verificações também ficam dentro da tentativa (seção 9). Só roda se o texto do pré-registro
for o aprovado (hash) e só com dados até o fim do desenvolvimento (08/09/2023).

O DSR conta como séries testadas as três versões e os seis vizinhos de cada uma (21 colunas), além
de todas as tentativas anteriores de todas as fichas.
"""

from __future__ import annotations

import math
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trader import avaliacao, criterio_quant, freios
from trader.estrategias import dados_p0_3, rodar_alavancagem, rodar_p0_3
from trader.estrategias import dados_tendencia_b3 as dados
from trader.estrategias import tendencia_b3 as tb
from trader.holdout import exigir_sem_holdout, recortar_desenvolvimento
from trader.registro import Registro

PASTA_DA_PESQUISA = dados.PASTA_DA_PESQUISA
FICHA = "P0-2"
CANDIDATO = tb.CANDIDATO
NOME = "p0_2_tendencia_bova11"
FONTE = (
    "Yahoo Finance (BOVA11.SA, abertura e fechamento) + curva nominal do acervo (DI1) + "
    "CDI (SGS 12); cesta: " + dados.FONTE_DA_CESTA
)
REGUA = "BOVA11 comprar e segurar"
VIZINHOS: dict[str, dict] = {
    "vol_alvo_0.20": {"vol_alvo": 0.20},
    "vol_alvo_0.30": {"vol_alvo": 0.30},
    "janela_da_vol_72": {"janela_da_vol": 72},
    "janela_da_vol_108": {"janela_da_vol": 108},
    "janelas_x0.8": {"janelas": tb.escalar_janelas(tb.JANELAS, 0.8)},
    "janelas_x1.2": {"janelas": tb.escalar_janelas(tb.JANELAS, 1.2)},
}
FRACAO_DO_CORTE = rodar_p0_3.FRACAO_DO_CORTE
T_ALVO = 3.0  # a régua "anos ≈ (t/SR)²" do pré-registro usa o t do item A5
abrir_registro = rodar_p0_3.abrir_registro


def carregar_tabelas(
    pasta: Path = PASTA_DA_PESQUISA,
    pasta_do_mt5: Path = dados.PASTA_DO_MT5,
    pasta_da_curva: Path = dados.PASTA_DA_CURVA,
) -> tuple[dict[str, tb.Ativo], pd.Series]:
    """As três versões e a cesta, mais o CDI por pregão, só com o desenvolvimento."""
    barras = recortar_desenvolvimento(
        dados.so_com_negocio_desde_o_inicio(
            dados.barras_do_yahoo(pasta_do_mt5 / dados.ARQUIVO_DO_BOVA11)
        )
    )
    pregoes = pd.DatetimeIndex(barras.index)
    cdi = (
        dados_p0_3.carregar_cdi(
            pregoes.min(), pd.Timestamp(criterio_quant.FIM_DO_DESENVOLVIMENTO), pasta
        )
        .reindex(pregoes)
        .ffill()
    )
    curva = rodar_alavancagem.carregar_curva(pasta_da_curva)
    curva = curva[pd.to_datetime(curva["data_base"]) <= pregoes.max()]
    aberturas, fechamentos, volumes = dados.carregar_cesta(pregoes, pasta_do_mt5)
    for tabela in (barras, cdi, fechamentos):
        exigir_sem_holdout(tabela)
    bova11 = tb.a_vista(
        "BOVA11",
        barras["abertura"],
        barras["fechamento"],
        barras["volume"] * barras["fechamento"],
        cdi,
    )
    versoes = {
        "BOVA11": bova11,
        "WIN": tb.win_sintetico(bova11, cdi),
        "DI1": tb.di1_sintetico(curva, cdi, bova11),
        "cesta": tb.cesta(aberturas, fechamentos, volumes, cdi),
    }
    return versoes, cdi


def especificacao(versoes: dict[str, tb.Ativo], parametros: tb.Parametros) -> dict:
    bova11 = versoes["BOVA11"]
    return {
        "pesquisa": FICHA,
        "pre_registro": criterio_quant.HASH_DO_CRITERIO,
        "versao_do_codigo": tb.VERSAO,
        "fonte": FONTE,
        "cesta": list(dados.CESTA),
        "hash_dos_dados": dados.hash_da_tabela(
            pd.DataFrame({n: a.fechamento for n, a in versoes.items()})
        ),
        "inicio": bova11.datas.min().date().isoformat(),
        "fim": bova11.datas.max().date().isoformat(),
        **parametros.especificacao(),
    }


def anos_para_t(sharpe: float, t: float = T_ALVO) -> float:
    """A régua do pré-registro: anos necessários ≈ (t ÷ SR)²; infinito se o Sharpe não é positivo."""
    return (t / sharpe) ** 2 if sharpe > 0 else float("inf")


def _custo_por_lado(ativo: tb.Ativo, parametros: tb.Parametros) -> float:
    """O custo de bolsa de um real negociado, para a conta simples dos sinais deslocados (A6)."""
    if ativo.futuro:
        return (
            parametros.custos.tarifa_futuro_por_contrato / ativo.valor_do_contrato
            + parametros.spread_do_futuro_por_lado
        )
    return parametros.custos.emolumentos_no_leilao


def _resumo(r: tb.Resultado, cdi: pd.Series) -> dict:
    return {
        **avaliacao.resumir_serie(r.retorno),
        "sharpe_do_excesso": tb.sharpe_do_excesso(r.retorno, cdi),
        "exposicao_media": r.exposicao_media(),
        "giro": r.giro,
        "custos": float(r.custos.sum()),
        "rolagem": float(r.rolagem.sum()),
        "imposto": float(r.imposto.sum()),
        "imposto_por_ano": float(r.imposto.sum()) / r.anos(),
        "meses_com_imposto": r.meses_com_imposto(),
        "meses_acima_da_isencao": r.meses_acima_da_isencao(),
        "meses_simulados": len(r.ir),
        "caixa_minimo": r.caixa_minimo,
        "day_trades": r.day_trades,
    }


def _rodar_versao(
    ativo: tb.Ativo,
    cdi: pd.Series,
    parametros: tb.Parametros,
    capital: float,
) -> dict:
    """Todas as séries de uma versão: base, estresse, bruto, futuro, de novo e os vizinhos."""
    fator = criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE

    def rodar(p: tb.Parametros) -> tb.Resultado:
        return tb.simular(ativo, cdi, p, capital)

    corte = ativo.datas[int(len(ativo.datas) * FRACAO_DO_CORTE)]
    base = rodar(parametros)
    return {
        "base": base,
        "estresse": rodar(parametros.em_estresse(fator)),
        "bruto": rodar(
            tb.com(
                parametros,
                custos=tb.SEM_CUSTOS,
                fator_de_impacto=0.0,
                spread_do_futuro_por_lado=0.0,
            )
        ),
        "futuro": rodar(tb.com(parametros, olhar_o_futuro=True)),
        "de_novo": rodar(parametros),
        "vizinhos": {n: rodar(tb.com(parametros, **m)) for n, m in VIZINHOS.items()},
        "vizinhos_estresse": {
            n: rodar(tb.com(parametros, **m).em_estresse(fator))
            for n, m in VIZINHOS.items()
        },
        "cortar": tb.cortar_o_futuro_nao_muda_o_passado(
            ativo, cdi, parametros, corte, capital
        ),
        "acaso": tb.tc.p_valor_do_acaso(
            base.exposicao.to_frame(ativo.nome),
            (ativo.excesso + cdi.reindex(ativo.datas)).to_frame(ativo.nome),
            cdi,
            _custo_por_lado(ativo, parametros),
            sorteios=criterio_quant.SINAIS_DESLOCADOS,
        ),
    }


def _tabela_dos_testados(series: dict[str, dict], chave: str) -> pd.DataFrame:
    """As 21 séries testadas (3 versões × [base + 6 vizinhos]) para o DSR."""
    colunas = {}
    for nome, s in series.items():
        colunas[nome] = s[chave].retorno
        for vizinho, r in s[
            f"vizinhos{'' if chave == 'base' else '_estresse'}"
        ].items():
            colunas[f"{nome}:{vizinho}"] = r.retorno
    return pd.DataFrame(colunas)


def _veredito_da_versao(
    nome: str,
    s: dict,
    cdi: pd.Series,
    candidatos: pd.DataFrame,
    candidatos_estresse: pd.DataFrame,
    reguas: dict[str, pd.Series],
    tentativas_totais: int,
) -> criterio_quant.Veredito:
    base = s["base"]
    cdi_do_periodo = cdi.reindex(base.retorno.index)
    ordem = [nome, *(c for c in candidatos.columns if c != nome)]
    evidencia = criterio_quant.Evidencia(
        candidato=base.retorno,
        cdi=cdi_do_periodo,
        candidatos=candidatos[ordem],
        candidatos_estresse=candidatos_estresse[ordem],
        sharpe_bruto=tb.sharpe_do_excesso(s["bruto"].retorno, cdi),
        sharpes_vizinhos={
            n: tb.sharpe_do_excesso(r.retorno, cdi) for n, r in s["vizinhos"].items()
        },
        reguas=reguas,
        p_valor_do_acaso=s["acaso"]["p_valor"],
        sharpe_olhando_o_futuro=tb.sharpe_do_excesso(s["futuro"].retorno, cdi),
        reexecucao_identica=tb.hash_do_resultado(s["de_novo"])
        == tb.hash_do_resultado(base),
        cortar_o_futuro_nao_muda=s["cortar"],
        tentativas_totais=tentativas_totais,
        nome_do_candidato=nome,
    )
    return criterio_quant.avaliar(evidencia)


def _leitura_da_versao(
    s: dict, veredito: criterio_quant.Veredito, cdi: pd.Series
) -> dict:
    return {
        "veredito": veredito,
        "resumo": _resumo(s["base"], cdi),
        "estresse": _resumo(s["estresse"], cdi),
        "bruto": tb.sharpe_do_excesso(s["bruto"].retorno, cdi),
        "futuro": tb.sharpe_do_excesso(s["futuro"].retorno, cdi),
        "vizinhos": {
            n: tb.sharpe_do_excesso(r.retorno, cdi) for n, r in s["vizinhos"].items()
        },
        "acaso": s["acaso"],
    }


def _teste_do_brasil(
    versoes: dict[str, tb.Ativo],
    series: dict[str, dict],
    cdi: pd.Series,
    parametros: tb.Parametros,
    capital: float,
) -> dict:
    """(a) day trades; (b) BOVA11 × WIN × cesta no imposto; (c) custo da rolagem do WIN."""
    cesta = tb.simular(versoes["cesta"], cdi, parametros, capital)
    sem_isencao = tb.simular(
        versoes["cesta"],
        cdi,
        tb.com(
            parametros,
            custos=replace(parametros.custos, isencao_acoes_no_mes=0.0),
        ),
        capital,
    )
    win = series["WIN"]["base"]
    rolagens_no_periodo = [d for d in versoes["WIN"].rolagens if d in win.retorno.index]
    return {
        "day_trades": {n: s["base"].day_trades for n, s in series.items()},
        "imposto": {
            "BOVA11": _resumo(series["BOVA11"]["base"], cdi),
            "WIN": _resumo(win, cdi),
            "cesta": _resumo(cesta, cdi),
            "cesta_sem_isencao": _resumo(sem_isencao, cdi),
        },
        "rolagem_do_win": {
            "por_ano_do_patrimonio": win.custo_de_rolagem_por_ano(),
            "total": float(win.rolagem.sum()),
            "por_ano_em_reais": float(win.rolagem.sum()) / win.anos(),
            "rolagens_no_periodo": len(rolagens_no_periodo),
            "rolagens_com_posicao": int((win.rolagem > 0).sum()),
        },
        "rolagem_do_di1": {
            "por_ano_do_patrimonio": series["DI1"]["base"].custo_de_rolagem_por_ano(),
            "rolagens_com_posicao": int((series["DI1"]["base"].rolagem > 0).sum()),
        },
    }


def executar(
    versoes: dict[str, tb.Ativo],
    cdi: pd.Series,
    registro: Registro,
    capital: float = tb.CAPITAL_INICIAL,
) -> dict:
    """Registra a tentativa, simula tudo, avalia e guarda no registro."""
    criterio_quant.conferir()
    parametros = tb.Parametros()
    tentativa = registro.registrar(FICHA, NOME, especificacao(versoes, parametros))
    series = {
        nome: _rodar_versao(versoes[nome], cdi, parametros, capital)
        for nome in tb.VERSOES
    }
    candidatos = _tabela_dos_testados(series, "base")
    candidatos_estresse = _tabela_dos_testados(series, "estresse")
    # Esta tentativa testa 21 séries: cada uma conta no DSR (a linha do registro conta uma).
    tentativas_totais = (
        criterio_quant.tentativas_anteriores()
        + registro.total_para_o_dsr()
        - 1
        + candidatos.shape[1]
    )
    bova11 = versoes["BOVA11"]
    regua = tb.comprar_e_segurar(bova11, parametros, capital)
    inicio = series["BOVA11"]["base"].retorno.index
    reguas = {REGUA: regua, "CDI": cdi.reindex(inicio)}
    leituras = {}
    for nome in tb.VERSOES:
        veredito = _veredito_da_versao(
            nome,
            series[nome],
            cdi,
            candidatos,
            candidatos_estresse,
            reguas,
            tentativas_totais,
        )
        leituras[nome] = _leitura_da_versao(series[nome], veredito, cdi)
    base = series["BOVA11"]["base"]
    freado = freios.aplicar_freio(base.retorno, cdi)
    resumo = {
        **leituras["BOVA11"]["resumo"],
        "queda_com_freio": avaliacao.maior_queda(freado.retorno),
        "disparos_do_freio": [d.date().isoformat() for d in freado.disparos],
        "voltas_do_freio": [d.date().isoformat() for d in freado.voltas],
    }
    saida = {
        "id": tentativa,
        "candidato": CANDIDATO,
        "veredito": leituras["BOVA11"]["veredito"],
        "resumo": resumo,
        "versoes": leituras,
        "reguas": {n: avaliacao.resumir_serie(r) for n, r in reguas.items()},
        "brasil": _teste_do_brasil(versoes, series, cdi, parametros, capital),
        "tentativas_totais": tentativas_totais,
        "series_testadas": candidatos.shape[1],
        "primeiro_pregao": bova11.datas[0].date().isoformat(),
        "primeiro_dia_simulado": inicio[0].date().isoformat(),
        "anos_para_t3": anos_para_t(resumo["sharpe_do_excesso"]),
        "periodo": (
            bova11.datas.min().date().isoformat(),
            bova11.datas.max().date().isoformat(),
        ),
    }
    registro.salvar_resultado(tentativa, _para_o_registro(saida))
    return saida


def _para_o_registro(saida: dict) -> dict:
    versoes = {
        n: {**v, "veredito": v["veredito"].para_registro()}
        for n, v in saida["versoes"].items()
    }
    return {**saida, "veredito": saida["veredito"].para_registro(), "versoes": versoes}


# --- relatório -------------------------------------------------------------------------------------


def _situacao(veredito: criterio_quant.Veredito) -> str:
    situacao = "APROVADA" if veredito.aprovado else "REPROVADA"
    if veredito.reprovados:
        situacao += f" (falhou em {', '.join(veredito.reprovados)})"
    if veredito.inconclusivo:
        situacao += f"; inconclusivo: {veredito.motivo_inconclusivo}"
    return situacao


def _veredito_em_linhas(nome: str, veredito: criterio_quant.Veredito) -> list[str]:
    return [
        f"### {nome}: {_situacao(veredito)}",
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
        f"| {nome} | {r['sharpe_do_excesso']:.2f} | {r['sharpe']:.2f} | {r['retorno_anual']:.1%} | "
        f"{r['volatilidade_anual']:.1%} | {r['maior_queda']:.1%} | {r['exposicao_media']:.2f} | "
        f"{r['giro']:.1f} | {(r['custos'] + r['rolagem']) / tb.CAPITAL_INICIAL:.1%} | "
        f"{r['imposto'] / tb.CAPITAL_INICIAL:.1%} | {r['meses_com_imposto']} de {r['meses_simulados']} |"
    )


def _reais(valor: float) -> str:
    """R$ com ponto de milhar, como se escreve no Brasil (R$ 8.284)."""
    return "R$ " + f"{valor:,.0f}".replace(",", ".")


def _anos_para_t(anos: float) -> str:
    """A régua do tempo em palavras: com Sharpe do excesso ≤ 0, nenhum prazo chega a t = 3."""
    if not math.isfinite(anos):
        return "nenhum prazo bastaria (o Sharpe do excesso não é positivo)"
    return f"seriam ≈ {anos:.0f} anos"


CABECALHO = (
    "| Versão | Sharpe do excesso | Sharpe | Retorno anual | Volatilidade | Maior queda | "
    "Exposição média | Giro/ano | Custos ÷ capital | IR ÷ capital | Meses com IR |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|"
)


def escrever_relatorio(
    saida: dict, pasta: Path = PASTA_DA_PESQUISA / "relatorios"
) -> Path:
    inicio, fim = saida["periodo"]
    r = saida["resumo"]
    b = saida["brasil"]
    v = saida["versoes"]
    imposto = b["imposto"]
    rolagem = b["rolagem_do_win"]
    linhas = [
        f"# Tendência na B3 (ficha P0-2): rodada do pré-registro quant v{criterio_quant.VERSAO}",
        "",
        f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC. Dados de {inicio} a {fim} (desenvolvimento; holdout lacrado).",
        (
            f"Primeiro pregão: {saida['primeiro_pregao']}; primeiro dia simulado (depois do aquecimento de "
            f"{tb.AQUECIMENTO_EM_PREGOES} pregões): {saida['primeiro_dia_simulado']}."
        ),
        (
            f"Tentativas contadas no DSR: {saida['tentativas_totais']} (com as "
            f"{saida['series_testadas']} séries desta tentativa)."
        ),
        (
            f"Régua do tempo: anos necessários ≈ (t ÷ SR)²; com t = {T_ALVO:.0f} e o Sharpe do excesso "
            f"do BOVA11 ({r['sharpe_do_excesso']:.2f}), {_anos_para_t(saida['anos_para_t3'])}."
        ),
        "",
        "## Veredito (seção 5 do pré-registro)",
        "",
        "A candidata é o BOVA11; WIN e DI1 são comparação (a mesma régua e o mesmo DSR).",
        "",
        *(
            linha
            for nome in tb.VERSOES
            for linha in _veredito_em_linhas(nome, v[nome]["veredito"])
        ),
        "## As três versões (custos base) e o estresse",
        "",
        CABECALHO,
        *(_linha(nome, v[nome]["resumo"]) for nome in tb.VERSOES),
        *(_linha(f"{nome} estresse", v[nome]["estresse"]) for nome in tb.VERSOES),
        "",
        (
            f"BOVA11 com freio de 40%: maior queda {r['queda_com_freio']:.1%}; disparos "
            f"{r['disparos_do_freio'] or 'nenhum'}; voltas {r['voltas_do_freio'] or 'nenhuma'}. "
            f"Menor caixa ÷ patrimônio: {r['caixa_minimo']:.2f}."
        ),
        "",
        "## Teste do Brasil (ficha P0-2)",
        "",
        (
            "- (a) Saídas que viram day trade (20%): "
            + ", ".join(f"{n} {q}" for n, q in b["day_trades"].items())
            + ". Uma ordem por pregão, no leilão de "
            "abertura, e as pernas da rolagem são contratos diferentes: nenhuma compra e venda do mesmo "
            "instrumento no mesmo pregão."
        ),
        (
            "- (b) Imposto: BOVA11 (ETF, 15% sem isenção) × WIN (15% sobre o ajuste) × cesta das 10 maiores "
            "(ações, isenção de R$ 20 mil de vendas no mês):"
        ),
        "",
        "| Versão | Sharpe do excesso | IR total | IR por ano | Meses com IR | Meses acima de R$ 20 mil |",
        "|---|---|---|---|---|---|",
        *(
            f"| {n} | {x['sharpe_do_excesso']:.2f} | {_reais(x['imposto'])} | {_reais(x['imposto_por_ano'])} | "
            f"{x['meses_com_imposto']} de {x['meses_simulados']} | "
            f"{'-' if n == 'cesta_sem_isencao' else x['meses_acima_da_isencao']} |"
            for n, x in imposto.items()
        ),
        "",
        (
            f"- (c) Rolagem do WIN: {rolagem['rolagens_com_posicao']} de {rolagem['rolagens_no_periodo']} "
            f"rolagens com posição; {_reais(rolagem['total'])} no período ({_reais(rolagem['por_ano_em_reais'])} "
            f"por ano, {rolagem['por_ano_do_patrimonio']:.3%} do patrimônio médio por ano)."
        ),
        "",
        "## Réguas, platô e bruto",
        "",
        "| Régua | Sharpe | Retorno anual | Maior queda |",
        "|---|---|---|---|",
        *(
            f"| {n} | {'-' if n == 'CDI' else f'{x["sharpe"]:.2f}'} | {x['retorno_anual']:.1%} | {x['maior_queda']:.1%} |"
            for n, x in saida["reguas"].items()
        ),
        "",
        "| Vizinho (±20%) | " + " | ".join(tb.VERSOES) + " |",
        "|---|" + "---|" * len(tb.VERSOES),
        *(
            f"| {viz} | "
            + " | ".join(f"{v[n]['vizinhos'][viz]:.2f}" for n in tb.VERSOES)
            + " |"
            for viz in VIZINHOS
        ),
        "| bruto (sem custo, imposto nem impacto) | "
        + " | ".join(f"{v[n]['bruto']:.2f}" for n in tb.VERSOES)
        + " |",
        "| olhando o futuro (sem custo) | "
        + " | ".join(f"{v[n]['futuro']:.2f}" for n in tb.VERSOES)
        + " |",
        "",
        *(
            f"Contra o acaso ({n}): Sharpe real {v[n]['acaso']['sharpe_real']:.2f}, percentil 95 dos sinais "
            f"deslocados {v[n]['acaso']['percentil_95']:.2f}, p-valor {v[n]['acaso']['p_valor']:.3f}."
            for n in tb.VERSOES
        ),
        "",
        "## Limites e cuidados",
        "",
        "- Desenvolvimento só: nada aqui diz o que o holdout vai mostrar; abri-lo é decisão escrita do Tiago.",
        "- Custos v0.2 (tabelas da B3 lidas em 03/11/2026): leilão 0,032%, day trade 0,023%, WIN R$ 0,394 por contrato; a tarifa do DI1 fica a confirmar (usa a do WIN).",
        "- WIN e DI1 são sintéticos, com contratos fracionários; o DI1 executa na marcação do fechamento de D+1 (a série não tem abertura).",
        "- A cesta usa a carteira teórica de 03/11/2026 aplicada ao passado (viés de sobrevivência) e preços ajustados por proventos.",
        f"- Não negocia diferença menor que {tb.BANDA_MINIMA:.1%} do patrimônio; o custo de aquisição do IR não inclui as taxas (erra contra a estratégia).",
        "- O DARF sai do caixa mesmo que ele fique negativo (empréstimo ao CDI); o IR dos meses que não venceram é pago no último pregão.",
        "- Toda execução conta como tentativa da ficha P0-2 (orçamento 8).",
        "- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.",
    ]
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"rodada_tendencia_b3_{datetime.now(UTC):%Y%m%d_%H%M}.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def main() -> int:
    versoes, cdi = carregar_tabelas()
    saida = executar(versoes, cdi, abrir_registro())
    print(escrever_relatorio(saida).read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
