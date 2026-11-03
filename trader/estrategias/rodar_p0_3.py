"""Roda a ficha P0-3 inteira contra o critério do pré-registro quant v0.1.

    python -m trader.estrategias.rodar_p0_3

**Cada execução conta como tentativa** no registro `pesquisa_quant/registro.db`: 4 por rodada (os
três esquemas no modo vender e o candidato no modo aporte). Os vizinhos do platô (A3), as réguas,
o estresse, o bruto e as verificações ficam gravados dentro da tentativa do candidato: são
leituras do mesmo candidato, não configurações concorrendo a dinheiro (seção 9 do pré-registro).
Só roda se o texto do pré-registro for o aprovado (hash) e só com dados até o fim do
desenvolvimento (o holdout continua lacrado).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trader import avaliacao, criterio_quant
from trader.estrategias import carteira_rp, dados_p0_3
from trader.holdout import exigir_sem_holdout, recortar_desenvolvimento
from trader.registro import Registro

PASTA_DA_PESQUISA = dados_p0_3.PASTA_DA_PESQUISA
FICHA = "P0-3"
ESQUEMAS = ("risk_parity", "inverso_vol", "min_var")
CANDIDATO = carteira_rp.CANDIDATO
VIZINHOS = {
    "janela_202": {"janela": 202},
    "janela_302": {"janela": 302},
    "banda_0.16": {"banda": 0.16},
    "banda_0.24": {"banda": 0.24},
}
FRACAO_DO_CORTE = 0.7  # V (4): corta o futuro em 70% dos dias
NOMES = {
    "risk_parity": "risk parity",
    "inverso_vol": "inverso da volatilidade",
    "min_var": "mínima variância",
}


def abrir_registro(caminho: Path = PASTA_DA_PESQUISA / "registro.db") -> Registro:
    return Registro(
        caminho,
        familias=tuple(criterio_quant.ORCAMENTO_POR_FICHA),
        orcamento=criterio_quant.ORCAMENTO_DE_TENTATIVAS,
    )


def carregar_tabelas(
    pasta: Path = PASTA_DA_PESQUISA,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Preços em reais, CDI e volumes, só com dados do desenvolvimento."""
    mt5 = {
        nome: dados_p0_3.fechamento_do_mt5(dados_p0_3.PASTA_DO_MT5 / arquivo)
        for nome, arquivo in dados_p0_3.ARQUIVOS_DO_MT5.items()
    }
    curva = dados_p0_3.carregar_curva_real()
    inicio, fim = curva.index.min(), pd.Timestamp(criterio_quant.FIM_DO_DESENVOLVIMENTO)
    ipca = dados_p0_3.carregar_ipca(inicio - pd.DateOffset(months=1), fim, pasta)
    ntnb = dados_p0_3.indice_sintetico_da_ntnb(recortar_desenvolvimento(curva), ipca)
    precos = recortar_desenvolvimento(
        dados_p0_3.montar_precos(
            bova11=mt5["BOVA11"],
            ntnb=ntnb,
            ouro_usd=mt5["OURO"],
            sp500_usd=mt5["SP500"],
            brl=mt5["BRL"],
        )
    )
    cdi = (
        dados_p0_3.carregar_cdi(precos.index.min(), fim, pasta)
        .reindex(precos.index)
        .ffill()
    )
    volumes = pd.Series(dados_p0_3.VOLUME_MEDIO_EM_REAIS)
    exigir_sem_holdout(precos)
    exigir_sem_holdout(cdi)
    return precos, cdi, volumes


def _excesso(retorno: pd.Series, cdi: pd.Series) -> pd.Series:
    return retorno - cdi.reindex(retorno.index)


def executar(
    precos: pd.DataFrame, cdi: pd.Series, volumes: pd.Series, registro: Registro
) -> dict:
    """Registra as 4 tentativas, simula tudo, avalia o candidato e guarda no registro."""
    criterio_quant.conferir()
    comum = {
        "pesquisa": FICHA,
        "pre_registro": criterio_quant.HASH_DO_CRITERIO,
        "versao_do_codigo": carteira_rp.VERSAO,
        "inicio": precos.index.min().date().isoformat(),
        "fim": precos.index.max().date().isoformat(),
    }
    configuracoes = {
        esquema: carteira_rp.Parametros(esquema=esquema) for esquema in ESQUEMAS
    }
    configuracoes[f"{CANDIDATO}_aporte"] = carteira_rp.Parametros(
        esquema=CANDIDATO, modo="aporte"
    )
    ids = {
        nome: registro.registrar(
            FICHA, f"p0_3_{nome}", {**comum, **parametros.especificacao()}
        )
        for nome, parametros in configuracoes.items()
    }

    def rodar(parametros: carteira_rp.Parametros) -> carteira_rp.Resultado:
        return carteira_rp.simular(precos, cdi, volumes, parametros)

    def sharpe_do_excesso(resultado: carteira_rp.Resultado) -> float:
        return avaliacao.sharpe(_excesso(resultado.retorno, cdi))

    base = {esquema: rodar(configuracoes[esquema]) for esquema in ESQUEMAS}
    estresse = {
        esquema: rodar(
            carteira_rp.com(
                configuracoes[esquema],
                custos=configuracoes[esquema].custos.em_estresse(
                    criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE
                ),
                fator_de_impacto=criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE,
            )
        )
        for esquema in ESQUEMAS
    }
    candidato = base[CANDIDATO]
    parametros = configuracoes[CANDIDATO]
    aporte = rodar(configuracoes[f"{CANDIDATO}_aporte"])
    bruto = rodar(
        carteira_rp.com(parametros, custos=carteira_rp.SEM_CUSTOS, fator_de_impacto=0.0)
    )
    futuro = rodar(carteira_rp.com(parametros, olhar_o_futuro=True))
    de_novo = rodar(parametros)
    vizinhos = {
        nome: rodar(carteira_rp.com(parametros, **mudanca))
        for nome, mudanca in VIZINHOS.items()
    }
    reguas = {
        "60/40": rodar(carteira_rp.REGUA_60_40).retorno,
        "CDI": cdi.reindex(precos.index),
    }
    corte = precos.index[int(len(precos) * FRACAO_DO_CORTE)]
    cortar = carteira_rp.cortar_o_futuro_nao_muda_o_passado(
        precos, cdi, volumes, parametros, corte
    )
    acaso = carteira_rp.p_valor_do_acaso(
        candidato.pesos,
        precos.pct_change().fillna(0.0),
        cdi,
        parametros.custos.emolumentos_a_vista,
        sorteios=criterio_quant.SINAIS_DESLOCADOS,
    )
    tentativas_totais = (
        criterio_quant.tentativas_anteriores() + registro.total_para_o_dsr()
    )

    evidencia = criterio_quant.Evidencia(
        candidato=candidato.retorno,
        cdi=cdi.reindex(precos.index),
        candidatos=pd.DataFrame({e: r.retorno for e, r in base.items()}),
        candidatos_estresse=pd.DataFrame({e: r.retorno for e, r in estresse.items()}),
        sharpe_bruto=sharpe_do_excesso(bruto),
        sharpes_vizinhos={nome: sharpe_do_excesso(r) for nome, r in vizinhos.items()},
        reguas=reguas,
        p_valor_do_acaso=acaso["p_valor"],
        sharpe_olhando_o_futuro=sharpe_do_excesso(futuro),
        reexecucao_identica=carteira_rp.hash_do_resultado(de_novo)
        == carteira_rp.hash_do_resultado(candidato),
        cortar_o_futuro_nao_muda=cortar,
        tentativas_totais=tentativas_totais,
        nome_do_candidato=CANDIDATO,
    )
    veredito = criterio_quant.avaliar(evidencia)

    def resumo(resultado: carteira_rp.Resultado) -> dict:
        return {
            **avaliacao.resumir_serie(resultado.retorno),
            "sharpe_do_excesso": sharpe_do_excesso(resultado),
            "giro": resultado.giro,
            "custos": float(resultado.custos.sum()),
            "imposto": float(resultado.imposto.sum()),
        }

    resumos = {esquema: resumo(r) for esquema, r in base.items()}
    brasil = {"vender": resumos[CANDIDATO], "aporte": resumo(aporte)}
    resumo_das_reguas = {nome: avaliacao.resumir_serie(r) for nome, r in reguas.items()}
    vizinhos_resumo = {nome: resumo(r) for nome, r in vizinhos.items()}
    for nome, tentativa in ids.items():
        if nome == f"{CANDIDATO}_aporte":
            resultado = {"resumo": brasil["aporte"]}
        else:
            resultado = {"resumo": resumos[nome], "estresse": resumo(estresse[nome])}
        if nome == CANDIDATO:
            resultado |= {
                "veredito": veredito.para_registro(),
                "acaso": acaso,
                "vizinhos": vizinhos_resumo,
                "reguas": resumo_das_reguas,
                "bruto": resumo(bruto),
                "tentativas_totais": tentativas_totais,
            }
        registro.salvar_resultado(tentativa, resultado)
    return {
        "ids": ids,
        "veredito": veredito,
        "resumos": resumos,
        "estresse": {e: resumo(r) for e, r in estresse.items()},
        "brasil": brasil,
        "reguas": resumo_das_reguas,
        "vizinhos": vizinhos_resumo,
        "bruto": resumo(bruto),
        "acaso": acaso,
        "tentativas_totais": tentativas_totais,
        "inicio_das_series": {
            c: precos[c].first_valid_index().date().isoformat() for c in precos.columns
        },
        "periodo": (comum["inicio"], comum["fim"]),
    }


def _linha(nome: str, r: dict) -> str:
    return (
        f"| {nome} | {r.get('sharpe_do_excesso', float('nan')):.2f} | {r.get('sharpe', float('nan')):.2f} | "
        f"{r.get('retorno_anual', float('nan')):.1%} | {r.get('volatilidade_anual', float('nan')):.1%} | "
        f"{r.get('maior_queda', float('nan')):.1%} | {r.get('giro', float('nan')):.2f} |"
    )


def escrever_relatorio(
    saida: dict, pasta: Path = PASTA_DA_PESQUISA / "relatorios"
) -> Path:
    veredito = saida["veredito"]
    cabecalho = "| Esquema | Sharpe do excesso | Sharpe | Retorno anual | Volatilidade | Maior queda | Giro |\n|---|---|---|---|---|---|---|"
    inicio, fim = saida["periodo"]
    linhas = [
        f"# Ficha P0-3: rodada do pré-registro quant v{criterio_quant.VERSAO}",
        "",
        f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC. Dados de {inicio} a {fim} (desenvolvimento; holdout lacrado).",
        f"Tentativas contadas no DSR: {saida['tentativas_totais']}.",
        "",
        f"**Veredito do {NOMES[CANDIDATO]}: {'APROVADO' if veredito.aprovado else 'REPROVADO'}**"
        + (
            f" (falhou em {', '.join(veredito.reprovados)})"
            if veredito.reprovados
            else ""
        )
        + (
            f"; inconclusivo: {veredito.motivo_inconclusivo}"
            if veredito.inconclusivo
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
        "## Os três esquemas (custos base, modo vender)",
        "",
        cabecalho,
        *(_linha(NOMES[e], r) for e, r in saida["resumos"].items()),
        "",
        "## Estresse (custos × 2, impacto Y = 2)",
        "",
        cabecalho,
        *(_linha(NOMES[e], r) for e, r in saida["estresse"].items()),
        "",
        "## O teste do Brasil: vender para rebalancear ou só aportar 1% ao mês",
        "",
        cabecalho,
        *(_linha(modo, r) for modo, r in saida["brasil"].items()),
        "",
        "## Réguas e platô",
        "",
        "| Régua | Sharpe | Retorno anual | Maior queda |",
        "|---|---|---|---|",
        *(
            f"| {n} | {r['sharpe']:.2f} | {r['retorno_anual']:.1%} | {r['maior_queda']:.1%} |"
            for n, r in saida["reguas"].items()
        ),
        "",
        "| Vizinho | Sharpe do excesso |",
        "|---|---|",
        *(
            f"| {n} | {r['sharpe_do_excesso']:.2f} |"
            for n, r in saida["vizinhos"].items()
        ),
        f"| bruto (sem custo, imposto nem impacto) | {saida['bruto']['sharpe_do_excesso']:.2f} |",
        "",
        "## Primeiro dia de cada série",
        "",
        *(f"- {ativo}: {dia}" for ativo, dia in saida["inicio_das_series"].items()),
        "",
        "## Limites e cuidados",
        "",
        "- Desenvolvimento só: nada aqui diz o que o holdout vai mostrar; abri-lo é decisão escrita do Tiago.",
        "- A NTN-B é um índice sintético de prazo constante (curva de 5 anos + IPCA pro rata), não o B5P211.",
        "- Ouro e S&P 500 em reais sem hedge; feriado lá fora usa o último preço em dólar.",
        "- Quantidades fracionárias: os índices não têm cota, o lote de 100 não foi aplicado.",
        "- Volumes para o impacto são estimativas conservadoras fixadas antes dos números.",
        "- O DARF é pago no último pregão do mês seguinte, vendendo se o caixa não cobre.",
        "- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.",
    ]
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"rodada_p0_3_{datetime.now(UTC):%Y%m%d_%H%M}.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def main() -> int:
    precos, cdi, volumes = carregar_tabelas()
    saida = executar(precos, cdi, volumes, abrir_registro())
    print(escrever_relatorio(saida).read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
