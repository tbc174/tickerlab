"""Roda a ficha P0-4 (pares cointegrados na B3) inteira contra o critério do pré-registro quant v0.1.

    python -m trader.estrategias.rodar_pares

**Cada execução conta como uma tentativa** no registro `pesquisa_quant/registro.db` (orçamento da
ficha: 8). Os vizinhos do platô (A3, ±20% em cada parâmetro), o estresse, o bruto, a régua (CDI), as
verificações e os testes do Brasil (aluguel a 2, 5 e 10% a.a.; lote de 100 contra ações inteiras;
pares de setor e ON/PN contra todos; com e sem as deslistadas) ficam gravados dentro da tentativa do
candidato: são leituras do mesmo candidato, não configurações concorrendo a dinheiro (seção 9).

Antes de registrar qualquer tentativa, `main` confere a base (`dados_pares.conferir_base`): sem o
COTAHIST anual com as deslistadas e os preços ajustados, a rodada é INCONCLUSIVA por dados e nada é
gravado (seção 2). Só roda se o texto do pré-registro for o aprovado (hash) e só com dados até o fim
do desenvolvimento.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trader import avaliacao, criterio_quant
from trader.criterio import Item, Veredito
from trader.estrategias import dados_pares, pares
from trader.estrategias import fatores_b3 as fb
from trader.estrategias.carteira_rp import p_valor_do_acaso
from trader.registro import Registro

PASTA_DA_PESQUISA = dados_pares.dados_f_b3.PASTA_DA_PESQUISA
FICHA = "P0-4"
CANDIDATO = "pares_b3"
NOME_DO_CANDIDATO = "pares cointegrados na B3"
VIZINHOS = {
    "z_entrada_1.6": {"z_entrada": 1.6},
    "z_entrada_2.4": {"z_entrada": 2.4},
    "z_saida_0.4": {"z_saida": 0.4},
    "z_saida_0.6": {"z_saida": 0.6},
    "z_stop_3.2": {"z_stop": 3.2},
    "z_stop_4.8": {"z_stop": 4.8},
    "meia_vida_x2.4": {"multiplo_da_meia_vida": 2.4},
    "meia_vida_x3.6": {"multiplo_da_meia_vida": 3.6},
    "pares_8": {"max_pares": 8},
    "pares_12": {"max_pares": 12},
    "formacao_10": {"meses_de_formacao": 10},
    "formacao_14": {"meses_de_formacao": 14},
}
TAXAS_DO_ALUGUEL = {"2% a.a.": 0.02, "5% a.a.": 0.05, "10% a.a.": 0.10}
CONJUNTOS = {
    "todos os pares": "todos",
    "só pares do mesmo setor": "setor",
    "só ON/PN da mesma empresa": "on_pn",
}
FRACAO_DO_CORTE = 0.7  # V (4): corta o futuro em 70% dos dias
MENSAGEM_SEM_BASE = (
    "INCONCLUSIVA: sem universo histórico com as deslistadas, a ficha P0-4 não roda e nenhuma "
    "tentativa foi registrada (pré-registro v0.1, seção 2). Falta em {pasta}: {faltas}."
)
SAIDA_SEM_BASE = 2
# Sem nenhum par escolhido em nenhuma janela, a carteira fica toda no CDI: o excesso é zero todo
# dia, o Sharpe não existe e o DSR não tem o que deflacionar. A regra rodou com a base inteira e não
# produziu nada, então reprova no A1 (não é falta de dado; não vira inconclusiva).
VEREDITO_SEM_OPERACAO = Veredito(
    [
        Item(
            "A1",
            "a regra não escolheu nenhum par em nenhuma janela: a carteira ficou no CDI",
            None,
            "> 0 operações",
            False,
        )
    ]
)


abrir_registro = criterio_quant.abrir_registro


def _no_periodo(retorno: pd.Series, indice: pd.Index, cdi: pd.Series) -> pd.Series:
    """A série no período do candidato; antes da 1ª janela o dinheiro está no caixa, rendendo o CDI.

    Os vizinhos de formação (10 e 14 meses) começam em outro dia: sem isso, as colunas do DSR e do
    platô não teriam as mesmas datas.
    """
    return retorno.reindex(indice).fillna(cdi.reindex(indice))


def _acaso(
    candidato: pares.Resultado, dados: pares.Dados, parametros: pares.Parametros
) -> dict:
    """A6 (sinais deslocados no tempo); sem nenhuma posição não há o que deslocar, e o p-valor é 1."""
    if not candidato.pesos.abs().to_numpy().any():
        return {"sharpe_real": None, "percentil_95": None, "p_valor": 1.0}
    return p_valor_do_acaso(
        candidato.pesos,
        dados.fechamento.ffill().pct_change(fill_method=None).fillna(0.0),
        dados.cdi,
        parametros.custos.emolumentos_no_leilao,
        sorteios=criterio_quant.SINAIS_DESLOCADOS,
    )


def executar(
    dados: pares.Dados,
    registro: Registro,
    parametros: pares.Parametros | None = None,
) -> dict:
    """Registra a tentativa, simula tudo, avalia o candidato e guarda no registro.

    `parametros` fica no padrão da ficha; outro valor só serve aos testes (dados sintéticos curtos,
    em que 12 meses de formação quase nunca bastam para o teste de cointegração).
    """
    criterio_quant.conferir()
    conformidade = fb.conferir_sobrevivencia(dados)
    parametros = parametros or pares.Parametros()
    datas = dados.fechamento.index
    comum = {
        "pesquisa": FICHA,
        "pre_registro": criterio_quant.HASH_DO_CRITERIO,
        "versao_do_codigo": pares.VERSAO,
        "inicio": datas.min().date().isoformat(),
        "fim": datas.max().date().isoformat(),
    }
    tentativa = registro.registrar(
        FICHA, CANDIDATO, {**comum, **parametros.especificacao()}
    )
    cache: dict = {}  # a formação de cada janela é a mesma em quase todas as leituras

    def rodar(p: pares.Parametros) -> pares.Resultado:
        return pares.simular(dados, p, cache)

    candidato = rodar(parametros)
    periodo = candidato.retorno.index
    cdi = dados.cdi.reindex(periodo)

    def serie(resultado: pares.Resultado) -> pd.Series:
        return _no_periodo(resultado.retorno, periodo, dados.cdi)

    def sharpe_do_excesso(resultado: pares.Resultado) -> float:
        return avaliacao.sharpe(serie(resultado) - cdi)

    def em_estresse(p: pares.Parametros) -> pares.Parametros:
        return pares.com(
            p,
            custos=p.custos.em_estresse(criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE),
            fator_de_impacto=criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE,
        )

    vizinhos = {
        nome: rodar(pares.com(parametros, **mudanca))
        for nome, mudanca in VIZINHOS.items()
    }
    # O DSR precisa de mais de uma série: o candidato e os vizinhos do platô, que são
    # leituras dele (não concorrem a dinheiro), entram juntos.
    base = {CANDIDATO: candidato, **vizinhos}
    estresse = {
        nome: rodar(em_estresse(pares.com(parametros, **VIZINHOS.get(nome, {}))))
        for nome in base
    }
    bruto = rodar(
        pares.com(
            parametros,
            custos=pares.SEM_CUSTOS,
            fator_de_impacto=0.0,
            taxa_do_aluguel=0.0,
        )
    )
    no_sinal = rodar(pares.com(parametros, executar_no_sinal=True))
    de_novo = pares.simular(dados, parametros)  # sem o cache: reexecução de verdade
    alugueis = {
        nome: candidato
        if taxa == parametros.taxa_do_aluguel
        else rodar(pares.com(parametros, taxa_do_aluguel=taxa))
        for nome, taxa in TAXAS_DO_ALUGUEL.items()
    }
    lote_padrao = rodar(pares.com(parametros, fracionario=False))
    conjuntos = {
        nome: candidato
        if conjunto == parametros.conjunto
        else rodar(pares.com(parametros, conjunto=conjunto))
        for nome, conjunto in CONJUNTOS.items()
    }
    sem_deslistadas = rodar(pares.com(parametros, com_deslistadas=False))
    reguas = {"CDI": cdi}
    corte = datas[int(len(datas) * FRACAO_DO_CORTE)]
    cortar = pares.cortar_o_futuro_nao_muda_o_passado(dados, parametros, corte)
    acaso = _acaso(candidato, dados, parametros)
    tentativas_totais = (
        criterio_quant.tentativas_anteriores() + registro.total_para_o_dsr()
    )

    evidencia = criterio_quant.Evidencia(
        candidato=candidato.retorno,
        cdi=cdi,
        candidatos=pd.DataFrame({n: serie(r) for n, r in base.items()}),
        candidatos_estresse=pd.DataFrame({n: serie(r) for n, r in estresse.items()}),
        sharpe_bruto=sharpe_do_excesso(bruto),
        sharpes_vizinhos={n: sharpe_do_excesso(r) for n, r in vizinhos.items()},
        reguas=reguas,
        p_valor_do_acaso=acaso["p_valor"],
        sharpe_olhando_o_futuro=sharpe_do_excesso(no_sinal),
        reexecucao_identica=pares.hash_do_resultado(de_novo)
        == pares.hash_do_resultado(candidato),
        cortar_o_futuro_nao_muda=cortar,
        tentativas_totais=tentativas_totais,
        nome_do_candidato=CANDIDATO,
        dados_conforme=not conformidade.vies,
    )
    veredito = (
        criterio_quant.avaliar(evidencia)
        if len(candidato.operacoes)
        else VEREDITO_SEM_OPERACAO
    )

    def resumo(resultado: pares.Resultado) -> dict:
        operacoes = resultado.operacoes
        return {
            **avaliacao.resumir_serie(serie(resultado)),
            "sharpe_do_excesso": sharpe_do_excesso(resultado),
            "giro": resultado.giro,
            "custos": float(resultado.custos.sum()),
            "aluguel": float(resultado.aluguel.sum()),
            "imposto": float(resultado.imposto.sum()),
            "operacoes": len(operacoes),
            "pares_selecionados": sum(len(j["pares"]) for j in resultado.janelas),
            "dias_de_day_trade": resultado.dias_de_day_trade,
            "fechadas_no_dia_da_entrada": resultado.fechadas_no_dia_da_entrada,
            "quebrados_por_deslistagem": resultado.quebrados_por_deslistagem,
        }

    saida = {
        "id": tentativa,
        "veredito": veredito,
        "resumo": resumo(candidato),
        "estresse": resumo(estresse[CANDIDATO]),
        "bruto": resumo(bruto),
        "vizinhos": {n: resumo(r) for n, r in vizinhos.items()},
        "reguas": {n: avaliacao.resumir_serie(r) for n, r in reguas.items()},
        "brasil": {
            "aluguel": {n: resumo(r) for n, r in alugueis.items()},
            "lote": {
                "ações inteiras (candidato)": resumo(candidato),
                "lote de 100": resumo(lote_padrao),
            },
            "conjuntos": {n: resumo(r) for n, r in conjuntos.items()},
            "deslistadas": {
                "com as deslistadas": resumo(candidato),
                "só sobreviventes": resumo(sem_deslistadas),
            },
        },
        "janelas": candidato.janelas,
        "sobrevivencia": asdict(conformidade),
        "acaso": acaso,
        "tentativas_totais": tentativas_totais,
        "universo": {"tickers": int(dados.fechamento.shape[1])},
        "periodo": (
            periodo.min().date().isoformat() if len(periodo) else comum["inicio"],
            comum["fim"],
        ),
    }
    registro.salvar_resultado(
        tentativa,
        {
            chave: (valor.para_registro() if chave == "veredito" else valor)
            for chave, valor in saida.items()
            if chave not in ("id", "periodo")
        },
    )
    return saida


def _linha(nome: str, r: dict) -> str:
    nan = float("nan")
    return (
        f"| {nome} | {r.get('sharpe_do_excesso', nan):.2f} | {r.get('retorno_anual', nan):.1%} | "
        f"{r.get('maior_queda', nan):.1%} | {r.get('operacoes', 0)} | "
        f"{r.get('custos', nan):,.0f} | {r.get('aluguel', nan):,.0f} | {r.get('imposto', nan):,.0f} |"
    )


def escrever_relatorio(
    saida: dict, pasta: Path = PASTA_DA_PESQUISA / "relatorios"
) -> Path:
    veredito = saida["veredito"]
    cabecalho = (
        "| Leitura | Sharpe do excesso | Retorno anual | Maior queda | Operações | Custos (R$) "
        "| Aluguel (R$) | IR (R$) |\n|---|---|---|---|---|---|---|---|"
    )
    inicio, fim = saida["periodo"]
    brasil = saida["brasil"]
    lote = brasil["lote"]["lote de 100"]
    candidato = saida["resumo"]
    janelas = saida["janelas"]
    linhas = [
        f"# Ficha P0-4: rodada do pré-registro quant v{criterio_quant.VERSAO}",
        "",
        f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC. Dados de {inicio} a {fim} (desenvolvimento; holdout lacrado).",
        (
            f"Tentativas contadas no DSR: {saida['tentativas_totais']}. "
            f"Universo: {saida['universo']['tickers']} tickers; {len(janelas)} janelas de operação."
        ),
        "",
        f"**Veredito dos {NOME_DO_CANDIDATO}: {'APROVADO' if veredito.aprovado else 'REPROVADO'}**"
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
        f"**Sobrevivência:** {saida['sobrevivencia']['aviso']}",
        "",
        "| Item | O quê | Valor | Limite | Passou |",
        "|---|---|---|---|---|",
        *(
            f"| {i.codigo} | {i.descricao} | {'-' if i.valor is None else f'{i.valor:.3f}'} | {i.limite} | {'sim' if i.passou else 'NÃO'} |"
            for i in veredito.itens
        ),
        "",
        "## As janelas (formação de 12 meses, operação nos 6 seguintes)",
        "",
        "| Operação | Pares testados | Cointegrados (BH) | Com meia-vida de 5 a 30 | Escolhidos |",
        "|---|---|---|---|---|",
        *(
            f"| {j['inicio']} a {j['fim']} | {j['testados']} | {j['cointegrados']} | {j['candidatos']} | "
            + (", ".join(f"{p['y']}/{p['x']}" for p in j["pares"]) or "nenhum")
            + " |"
            for j in janelas
        ),
        "",
        "## O candidato (custos base), o estresse e o bruto",
        "",
        cabecalho,
        _linha("candidato", candidato),
        _linha("estresse (custos × 2, impacto Y = 2)", saida["estresse"]),
        _linha("bruto (sem custo, aluguel, imposto nem impacto)", saida["bruto"]),
        "",
        "## O teste do Brasil",
        "",
        "### (a) Aluguel da perna vendida (mínimo de R$ 10 por operação)",
        "",
        cabecalho,
        *(_linha(n, r) for n, r in brasil["aluguel"].items()),
        "",
        "### (b) Lote de 100 e holding de pelo menos 1 pregão",
        "",
        cabecalho,
        *(_linha(n, r) for n, r in brasil["lote"].items()),
        "",
        (
            f"Dias com compra e venda do mesmo ticker (day trade, entre pares diferentes): "
            f"{candidato['dias_de_day_trade']} no candidato e {lote['dias_de_day_trade']} no lote de 100. "
            f"Pares fechados no mesmo dia da entrada: {candidato['fechadas_no_dia_da_entrada']} "
            "(a regra nunca fecha no pregão em que abriu)."
        ),
        "",
        "### (c) Pares ON/PN e pares do mesmo setor contra todos os pares",
        "",
        cabecalho,
        *(_linha(n, r) for n, r in brasil["conjuntos"].items()),
        "",
        "### (d) OPA e deslistagem",
        "",
        cabecalho,
        *(_linha(n, r) for n, r in brasil["deslistadas"].items()),
        "",
        f"Pares quebrados por deslistagem no candidato: {candidato['quebrados_por_deslistagem']}.",
        "",
        "## Régua e platô",
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
        "",
        "## Limites e cuidados",
        "",
        "- Desenvolvimento só: nada aqui diz o que o holdout vai mostrar; abri-lo é decisão escrita do Tiago.",
        "- Sem nenhuma deslistada na base o resultado tem viés de sobrevivência e não autoriza dinheiro.",
        "- OPA e deslistagem entram pelo fim da negociação no cadastro: o par fecha no pregão seguinte ao último preço; o preço da OPA em si não é modelado.",
        "- O aluguel é uma taxa fixa por leitura (2, 5 ou 10% a.a.); a taxa real de cada ação muda e algumas nem têm doador.",
        "- Com 12 meses de formação, o teste de Engle-Granger com a correção de Benjamini-Hochberg tem pouco poder: em muitas janelas nenhum par passa, e o dinheiro fica no CDI.",
        "- A régua é o CDI: a carteira é neutra (comprada e vendida), então o Ibovespa não é a comparação certa.",
        "- O DARF é pago no último pregão do mês seguinte; o IR é o do swing, também no day trade entre pares.",
        "- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.",
    ]
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"rodada_pares_{datetime.now(UTC):%Y%m%d_%H%M}.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def main(pasta: Path = dados_pares.PASTA_DA_FICHA) -> int:
    faltas = dados_pares.conferir_base(pasta)
    if faltas:
        print(MENSAGEM_SEM_BASE.format(pasta=pasta, faltas=", ".join(faltas)))
        return SAIDA_SEM_BASE
    dados = dados_pares.carregar_tabelas(pasta)
    saida = executar(dados, abrir_registro())
    print(escrever_relatorio(saida).read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
