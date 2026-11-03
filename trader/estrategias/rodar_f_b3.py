"""Roda a ficha F-B3 (fatores na B3) inteira contra o critério do pré-registro quant v0.1.

    python -m trader.estrategias.rodar_f_b3

**Cada execução conta como uma tentativa** no registro `pesquisa_quant/registro.db` (orçamento da
ficha: 10). Os vizinhos do platô (A3), o estresse, o bruto, as réguas, as verificações e os testes
do Brasil (com e sem deslistadas, três tamanhos de carteira, balanço pela data de divulgação contra
a data do balanço) ficam gravados dentro da tentativa do candidato: são leituras do mesmo candidato,
não configurações concorrendo a dinheiro (seção 9 do pré-registro).

Antes de registrar qualquer tentativa, `main` confere a base (`dados_f_b3.conferir_base`): sem o
COTAHIST anual com as deslistadas, a rodada é INCONCLUSIVA por dados e nada é gravado (seção 2: só
com as sobreviventes o resultado teria viés de sobrevivência e não autoriza dinheiro). Só roda se o
texto do pré-registro for o aprovado (hash) e só com dados até o fim do desenvolvimento.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trader import avaliacao, criterio_quant
from trader.estrategias import dados_f_b3
from trader.estrategias import fatores_b3 as fb
from trader.registro import Registro

PASTA_DA_PESQUISA = dados_f_b3.PASTA_DA_PESQUISA
FICHA = "F-B3"
CANDIDATO = "fatores_b3"
NOME_DO_CANDIDATO = "fatores na B3"
VIZINHOS = {
    "quintil_0.15": {"quintil": 0.15},
    "quintil_0.25": {"quintil": 0.25},
    "banda_0.16": {"banda": 0.16},
    "banda_0.24": {"banda": 0.24},
}
CARTEIRAS_DO_BRASIL = {
    "R$ 100 mil": 100_000.0,
    "R$ 500 mil": 500_000.0,
    "R$ 2 milhões": 2_000_000.0,
}
FRACAO_DO_CORTE = 0.7  # V (4): corta o futuro em 70% dos dias
MENSAGEM_SEM_BASE = (
    "INCONCLUSIVA: sem universo histórico com as deslistadas, a ficha F-B3 não roda e nenhuma "
    "tentativa foi registrada (pré-registro v0.1, seção 2). Falta em {pasta}: {faltas}."
)
SAIDA_SEM_BASE = 2


def abrir_registro(caminho: Path = PASTA_DA_PESQUISA / "registro.db") -> Registro:
    return Registro(
        caminho,
        familias=tuple(criterio_quant.ORCAMENTO_POR_FICHA),
        orcamento=criterio_quant.ORCAMENTO_DE_TENTATIVAS,
    )


def _excesso(retorno: pd.Series, cdi: pd.Series) -> pd.Series:
    return retorno - cdi.reindex(retorno.index)


def executar(dados: fb.Dados, registro: Registro) -> dict:
    """Registra a tentativa, simula tudo, avalia o candidato e guarda no registro."""
    criterio_quant.conferir()
    conformidade = fb.conferir_sobrevivencia(dados)
    parametros = fb.Parametros()
    datas = dados.fechamento.index
    comum = {
        "pesquisa": FICHA,
        "pre_registro": criterio_quant.HASH_DO_CRITERIO,
        "versao_do_codigo": fb.VERSAO,
        "inicio": datas.min().date().isoformat(),
        "fim": datas.max().date().isoformat(),
    }
    tentativa = registro.registrar(
        FICHA, CANDIDATO, {**comum, **parametros.especificacao()}
    )

    def rodar(p: fb.Parametros) -> fb.Resultado:
        return fb.simular(dados, p)

    def sharpe_do_excesso(resultado: fb.Resultado) -> float:
        return avaliacao.sharpe(_excesso(resultado.retorno, dados.cdi))

    def em_estresse(p: fb.Parametros) -> fb.Parametros:
        return fb.com(
            p,
            custos=p.custos.em_estresse(criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE),
            fator_de_impacto=criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE,
        )

    candidato = rodar(parametros)
    vizinhos = {
        nome: rodar(fb.com(parametros, **mudanca)) for nome, mudanca in VIZINHOS.items()
    }
    # O DSR precisa de mais de uma série: o candidato e os vizinhos do platô, que são
    # leituras dele (não concorrem a dinheiro), entram juntos.
    base = {CANDIDATO: candidato, **vizinhos}
    estresse = {
        nome: rodar(em_estresse(fb.com(parametros, **VIZINHOS.get(nome, {}))))
        for nome in base
    }
    bruto = rodar(fb.com(parametros, custos=fb.SEM_CUSTOS, fator_de_impacto=0.0))
    futuro = rodar(fb.com(parametros, olhar_o_futuro=True))
    de_novo = rodar(parametros)
    sem_deslistadas = rodar(fb.com(parametros, com_deslistadas=False))
    carteiras = {
        nome: candidato
        if capital == parametros.capital_inicial
        else rodar(fb.com(parametros, capital_inicial=capital))
        for nome, capital in CARTEIRAS_DO_BRASIL.items()
    }
    reguas = {"CDI": dados.cdi.reindex(datas)}
    if dados.ibovespa is not None:
        reguas["Ibovespa total líquido (BOVA11)"] = dados.ibovespa.reindex(datas)
    corte = datas[int(len(datas) * FRACAO_DO_CORTE)]
    cortar = fb.cortar_o_futuro_nao_muda_o_passado(dados, parametros, corte)
    acaso = fb.p_valor_do_acaso(
        candidato.pesos,
        dados.fechamento.ffill().pct_change(fill_method=None).fillna(0.0),
        dados.cdi,
        parametros.custos.emolumentos_a_vista,
        sorteios=criterio_quant.SINAIS_DESLOCADOS,
    )
    tentativas_totais = (
        criterio_quant.tentativas_anteriores() + registro.total_para_o_dsr()
    )

    evidencia = criterio_quant.Evidencia(
        candidato=candidato.retorno,
        cdi=dados.cdi.reindex(datas),
        candidatos=pd.DataFrame({n: r.retorno for n, r in base.items()}),
        candidatos_estresse=pd.DataFrame({n: r.retorno for n, r in estresse.items()}),
        sharpe_bruto=sharpe_do_excesso(bruto),
        sharpes_vizinhos={n: sharpe_do_excesso(r) for n, r in vizinhos.items()},
        reguas=reguas,
        p_valor_do_acaso=acaso["p_valor"],
        sharpe_olhando_o_futuro=sharpe_do_excesso(futuro),
        reexecucao_identica=fb.hash_do_resultado(de_novo)
        == fb.hash_do_resultado(candidato),
        cortar_o_futuro_nao_muda=cortar,
        tentativas_totais=tentativas_totais,
        nome_do_candidato=CANDIDATO,
        dados_conforme=not conformidade.vies,
    )
    veredito = criterio_quant.avaliar(evidencia)

    def resumo(resultado: fb.Resultado) -> dict:
        return {
            **avaliacao.resumir_serie(resultado.retorno),
            "sharpe_do_excesso": sharpe_do_excesso(resultado),
            "giro": resultado.giro,
            "custos": float(resultado.custos.sum()),
            "imposto": float(resultado.imposto.sum()),
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
            "deslistadas": {
                "com as deslistadas": resumo(candidato),
                "só sobreviventes": resumo(sem_deslistadas),
            },
            "carteiras": {n: resumo(r) for n, r in carteiras.items()},
            "balanco": {
                "pela data de divulgação": resumo(candidato),
                "pela data do balanço (olha o futuro)": resumo(futuro),
            },
        },
        "sobrevivencia": asdict(conformidade),
        "acaso": acaso,
        "tentativas_totais": tentativas_totais,
        "universo": {
            "tickers": int(dados.fechamento.shape[1]),
            "meses_com_alvo": len(candidato.alvos),
        },
        "periodo": (comum["inicio"], comum["fim"]),
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
    return (
        f"| {nome} | {r.get('sharpe_do_excesso', float('nan')):.2f} | {r.get('sharpe', float('nan')):.2f} | "
        f"{r.get('retorno_anual', float('nan')):.1%} | {r.get('volatilidade_anual', float('nan')):.1%} | "
        f"{r.get('maior_queda', float('nan')):.1%} | {r.get('giro', float('nan')):.2f} |"
    )


def escrever_relatorio(
    saida: dict, pasta: Path = PASTA_DA_PESQUISA / "relatorios"
) -> Path:
    veredito = saida["veredito"]
    cabecalho = "| Carteira | Sharpe do excesso | Sharpe | Retorno anual | Volatilidade | Maior queda | Giro |\n|---|---|---|---|---|---|---|"
    inicio, fim = saida["periodo"]
    brasil = saida["brasil"]
    linhas = [
        f"# Ficha F-B3: rodada do pré-registro quant v{criterio_quant.VERSAO}",
        "",
        f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC. Dados de {inicio} a {fim} (desenvolvimento; holdout lacrado).",
        (
            f"Tentativas contadas no DSR: {saida['tentativas_totais']}. "
            f"Universo: {saida['universo']['tickers']} tickers, "
            f"{saida['universo']['meses_com_alvo']} meses com carteira-alvo."
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
        "## O candidato (custos base), o estresse e o bruto",
        "",
        cabecalho,
        _linha("candidato", saida["resumo"]),
        _linha("estresse (custos × 2, impacto Y = 2)", saida["estresse"]),
        _linha("bruto (sem custo, imposto nem impacto)", saida["bruto"]),
        "",
        "## O teste do Brasil",
        "",
        "### (a) Com as deslistadas ou só com as sobreviventes",
        "",
        cabecalho,
        *(_linha(n, r) for n, r in brasil["deslistadas"].items()),
        "",
        "### (b) Tamanho da carteira e a isenção de R$ 20 mil",
        "",
        cabecalho,
        *(_linha(n, r) for n, r in brasil["carteiras"].items()),
        "",
        "### (c) Balanço pela data de divulgação ou pela data do balanço",
        "",
        cabecalho,
        *(_linha(n, r) for n, r in brasil["balanco"].items()),
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
        "",
        "## Limites e cuidados",
        "",
        "- Desenvolvimento só: nada aqui diz o que o holdout vai mostrar; abri-lo é decisão escrita do Tiago.",
        "- Sem nenhuma deslistada na base o resultado tem viés de sobrevivência e não autoriza dinheiro.",
        "- Bancos e seguradoras ficam sem o fator valor (plano de contas próprio) e entram com 3 fatores.",
        "- A régua do Ibovespa é o BOVA11 comprado e mantido, sem o IR da venda final.",
        "- Preço ajustado para momento e volatilidade; a execução usa a abertura ajustada pelo mesmo fator.",
        "- A recuperação judicial só é filtrada quando a tabela existe; sem ela, a ficha declara a falta.",
        "- O DARF é pago no último pregão do mês seguinte, vendendo se o caixa não cobre.",
        "- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.",
    ]
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"rodada_f_b3_{datetime.now(UTC):%Y%m%d_%H%M}.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def main(pasta: Path = dados_f_b3.PASTA_DA_FICHA) -> int:
    faltas = dados_f_b3.conferir_base(pasta)
    if faltas:
        print(MENSAGEM_SEM_BASE.format(pasta=pasta, faltas=", ".join(faltas)))
        return SAIDA_SEM_BASE
    dados = dados_f_b3.carregar_tabelas(pasta)
    saida = executar(dados, abrir_registro())
    print(escrever_relatorio(saida).read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
