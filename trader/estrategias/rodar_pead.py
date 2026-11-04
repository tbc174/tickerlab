"""Roda a ficha P0-5 (eventos do IPE e PEAD na B3) inteira contra o critério do pré-registro quant v0.1.

    python -m trader.estrategias.rodar_pead

**Cada execução conta como uma tentativa** no registro `pesquisa_quant/registro.db` (orçamento da
ficha: 6). Os vizinhos do platô (A3, ±20% em cada parâmetro), o estresse, o bruto, as réguas (CDI e
Ibovespa total líquido), as verificações, o teste do Brasil (dia zero = D+1 contra dia zero = D,
otimista e proibido no resultado final), a leitura sem as deslistadas e o estudo dos eventos (CAR
por tipo de documento) ficam gravados dentro da tentativa do candidato: são leituras do mesmo
candidato, não configurações concorrendo a dinheiro (seção 9).

**Período de avaliação** (fixado antes da rodada): do primeiro pregão em que o candidato tem
posição até o fim do desenvolvimento. Antes disso a regra não pode operar (a SUE pede 12 trimestres
de lucro, e os balanços do acervo começam em 2010 com os comparativos de 2009): o dinheiro fica no
CDI e o excesso seria zero por construção. Todas as leituras usam as mesmas datas.

Antes de registrar qualquer tentativa, `main` confere a base (`dados_pead.conferir_base`): sem o
COTAHIST anual com as deslistadas, os preços ajustados e o IPE, a rodada é INCONCLUSIVA por dados e
nada é gravado (seção 2). Só roda se o texto do pré-registro for o aprovado (hash) e só com dados
até o fim do desenvolvimento.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trader import avaliacao, criterio_quant
from trader.criterio import Item, Veredito
from trader.estrategias import dados_pead, pead
from trader.estrategias import fatores_b3 as fb
from trader.estrategias.carteira_rp import p_valor_do_acaso
from trader.registro import Registro

PASTA_DA_PESQUISA = dados_pead.dados_f_b3.PASTA_DA_PESQUISA
FICHA = "P0-5"
CANDIDATO = "pead_b3"
NOME_DO_CANDIDATO = "PEAD (surpresa de lucro) na B3"
REGUA_DO_IBOVESPA = "Ibovespa total líquido (BOVA11)"
VIZINHOS = {
    "trimestres_6": {"trimestres_do_desvio": 6},
    "trimestres_10": {"trimestres_do_desvio": 10},
    "fracao_0.267": {"fracao_de_cima": 0.8 / 3},
    "fracao_0.4": {"fracao_de_cima": 0.4},
    "pregoes_48": {"pregoes_na_posicao": 48},
    "pregoes_72": {"pregoes_na_posicao": 72},
    "posicoes_24": {"posicoes": 24},
    "posicoes_36": {"posicoes": 36},
}
FRACAO_DO_CORTE = 0.7  # V (4): corta o futuro em 70% dos dias
EVENTOS_MINIMOS_NO_RELATORIO = (
    30  # tipo de documento com menos eventos não vai para a tabela
)
MENSAGEM_SEM_BASE = (
    "INCONCLUSIVA: sem universo histórico com as deslistadas e o IPE, a ficha P0-5 não roda e "
    "nenhuma tentativa foi registrada (pré-registro v0.1, seção 2). Falta em {pasta}: {faltas}."
)
SAIDA_SEM_BASE = 2
# Sem nenhuma posição, a carteira fica toda no CDI: o excesso é zero todo dia e o Sharpe não existe.
# A regra rodou com a base inteira e não produziu nada, então reprova no A1 (não é falta de dado).
VEREDITO_SEM_OPERACAO = Veredito(
    [
        Item(
            "A1",
            "a regra não abriu nenhuma posição: a carteira ficou no CDI",
            None,
            "> 0 posições",
            False,
        )
    ]
)

abrir_registro = criterio_quant.abrir_registro


def periodo_de_avaliacao(resultado: pead.Resultado) -> pd.DatetimeIndex:
    """Do primeiro pregão com posição ao fim (vazio quando a regra nunca operou)."""
    com_posicao = resultado.pesos.sum(axis=1) > 0
    if not com_posicao.any():
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(resultado.retorno.index[com_posicao.to_numpy().argmax() :])


def _acaso(
    candidato: pead.Resultado,
    dados: pead.Dados,
    parametros: pead.Parametros,
    periodo: pd.DatetimeIndex,
) -> dict:
    """A6 (sinais deslocados no tempo); sem nenhuma posição não há o que deslocar, e o p-valor é 1."""
    pesos = candidato.pesos.reindex(periodo)
    if not len(periodo) or not pesos.abs().to_numpy().any():
        return {"sharpe_real": None, "percentil_95": None, "p_valor": 1.0}
    return p_valor_do_acaso(
        pesos,
        dados.fechamento.ffill().pct_change(fill_method=None).fillna(0.0),
        dados.cdi,
        parametros.custos.emolumentos_no_leilao,
        sorteios=criterio_quant.SINAIS_DESLOCADOS,
    )


def executar(
    dados: pead.Dados,
    registro: Registro,
    escolhidos: pead.Parametros | None = None,
) -> dict:
    """Registra a tentativa, simula tudo, avalia o candidato e guarda no registro."""
    criterio_quant.conferir()
    conformidade = fb.conferir_sobrevivencia(dados)
    parametros: pead.Parametros = escolhidos or pead.Parametros()
    datas = dados.fechamento.index
    comum = {
        "pesquisa": FICHA,
        "pre_registro": criterio_quant.HASH_DO_CRITERIO,
        "versao_do_codigo": pead.VERSAO,
        "inicio": datas.min().date().isoformat(),
        "fim": datas.max().date().isoformat(),
    }
    tentativa = registro.registrar(
        FICHA, CANDIDATO, {**comum, **parametros.especificacao()}
    )
    so_o_lucro = pead._so_o_lucro(dados)
    eventos: dict[tuple[int, bool], tuple[pd.DataFrame, dict]] = {}

    def eventos_de(p: pead.Parametros) -> tuple[pd.DataFrame, dict]:
        """Os eventos só mudam com os trimestres do desvio e com as deslistadas."""
        chave = (p.trimestres_do_desvio, p.com_deslistadas)
        if chave not in eventos:
            eventos[chave] = pead.eventos_de_lucro(so_o_lucro, p)
        return eventos[chave]

    def rodar(p: pead.Parametros) -> pead.Resultado:
        return pead.simular(dados, p, *eventos_de(p))

    def em_estresse(p: pead.Parametros) -> pead.Parametros:
        return pead.com(
            p,
            custos=p.custos.em_estresse(criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE),
            fator_de_impacto=criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE,
        )

    candidato = rodar(parametros)
    periodo = periodo_de_avaliacao(candidato)
    cdi = dados.cdi.reindex(periodo)

    def serie(resultado: pead.Resultado) -> pd.Series:
        return resultado.retorno.reindex(periodo)

    def sharpe_do_excesso(resultado: pead.Resultado) -> float:
        return avaliacao.sharpe(serie(resultado) - cdi)

    vizinhos = {
        nome: rodar(pead.com(parametros, **mudanca))
        for nome, mudanca in VIZINHOS.items()
    }
    # O DSR precisa de mais de uma série: o candidato e os vizinhos do platô, que são
    # leituras dele (não concorrem a dinheiro), entram juntos.
    base = {CANDIDATO: candidato, **vizinhos}
    estresse = {
        nome: rodar(em_estresse(pead.com(parametros, **VIZINHOS.get(nome, {}))))
        for nome in base
    }
    bruto = rodar(pead.com(parametros, custos=pead.SEM_CUSTOS, fator_de_impacto=0.0))
    no_sinal = rodar(pead.com(parametros, executar_no_sinal=True))
    otimista = rodar(pead.com(parametros, dia_zero_em_d=True))
    sem_deslistadas = rodar(pead.com(parametros, com_deslistadas=False))
    de_novo = pead.simular(
        dados, parametros
    )  # sem os eventos guardados: reexecução de verdade
    reguas = {"CDI": cdi}
    if dados.ibovespa is not None:
        reguas[REGUA_DO_IBOVESPA] = dados.ibovespa.reindex(periodo)
    corte = datas[int(len(datas) * FRACAO_DO_CORTE)]
    cortar = pead.cortar_o_futuro_nao_muda_o_passado(dados, parametros, corte)
    acaso = _acaso(candidato, dados, parametros, periodo)
    estudo = pead.estudo_dos_eventos(dados, parametros, eventos_de(parametros)[0])
    tentativas_totais = (
        criterio_quant.tentativas_anteriores() + registro.total_para_o_dsr()
    )
    operou = bool(len(candidato.posicoes)) and len(periodo) > 1

    evidencia = criterio_quant.Evidencia(
        candidato=serie(candidato),
        cdi=cdi,
        candidatos=pd.DataFrame({n: serie(r) for n, r in base.items()}),
        candidatos_estresse=pd.DataFrame({n: serie(r) for n, r in estresse.items()}),
        sharpe_bruto=sharpe_do_excesso(bruto),
        sharpes_vizinhos={n: sharpe_do_excesso(r) for n, r in vizinhos.items()},
        reguas=reguas,
        p_valor_do_acaso=acaso["p_valor"],
        sharpe_olhando_o_futuro=sharpe_do_excesso(no_sinal),
        reexecucao_identica=pead.hash_do_resultado(de_novo)
        == pead.hash_do_resultado(candidato),
        cortar_o_futuro_nao_muda=cortar,
        tentativas_totais=tentativas_totais,
        nome_do_candidato=CANDIDATO,
        dados_conforme=not conformidade.vies,
    )
    veredito = criterio_quant.avaliar(evidencia) if operou else VEREDITO_SEM_OPERACAO

    def resumo(resultado: pead.Resultado) -> dict:
        posicoes = resultado.posicoes
        return {
            **avaliacao.resumir_serie(serie(resultado)),
            "sharpe_do_excesso": sharpe_do_excesso(resultado),
            "giro": resultado.giro,
            "custos": float(resultado.custos.sum()),
            "imposto": float(resultado.imposto.sum()),
            "posicoes": len(posicoes),
            "retorno_medio_da_posicao": float(posicoes["retorno"].mean())
            if len(posicoes)
            else None,
            "acerto": float((posicoes["retorno"] > 0).mean())
            if len(posicoes)
            else None,
            "motivos": posicoes["motivo"].value_counts().to_dict()
            if len(posicoes)
            else {},
            "exposicao_media": float(
                resultado.pesos.reindex(periodo).sum(axis=1).mean()
            )
            if len(periodo)
            else 0.0,
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
            "dia zero = D+1 (candidato)": resumo(candidato),
            "dia zero = D (otimista, proibido)": resumo(otimista),
        },
        "no_sinal": resumo(no_sinal),
        "deslistadas": {
            "com as deslistadas": resumo(candidato),
            "só sobreviventes": resumo(sem_deslistadas),
        },
        "contagem": candidato.contagem,
        "estudo": estudo,
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
            if chave != "id"
        },
    )
    return saida


# --- o relatório --------------------------------------------------------------------------------------


def _pct(valor: float | None, casas: int = 1) -> str:
    return "-" if valor is None else f"{valor:.{casas}%}"


def _linha(nome: str, r: dict) -> str:
    nan = float("nan")
    return (
        f"| {nome} | {r.get('sharpe_do_excesso', nan):.2f} | {r.get('retorno_anual', nan):.1%} | "
        f"{r.get('maior_queda', nan):.1%} | {r.get('posicoes', 0)} | "
        f"{_pct(r.get('retorno_medio_da_posicao'), 2)} | {_pct(r.get('acerto'))} | "
        f"{_pct(r.get('exposicao_media'), 0)} | {r.get('custos', nan):,.0f} | {r.get('imposto', nan):,.0f} |"
    )


def _tabela_do_car(resumos: dict, minimo: int) -> list[str]:
    linhas = [
        "| Grupo | Eventos | CAR médio | CAR mediano | t | Positivos |",
        "|---|---|---|---|---|---|",
    ]
    for nome, r in sorted(resumos.items(), key=lambda item: -item[1]["n"]):
        if r["n"] < minimo:
            continue
        linhas.append(
            f"| {nome} | {r['n']} | {_pct(r['media'], 2)} | {_pct(r['mediana'], 2)} | "
            f"{r['t']:.2f} | {_pct(r['positivos'], 0)} |"
        )
    return linhas


def escrever_relatorio(
    saida: dict, pasta: Path = PASTA_DA_PESQUISA / "relatorios"
) -> Path:
    veredito = saida["veredito"]
    cabecalho = (
        "| Leitura | Sharpe do excesso | Retorno anual | Maior queda | Posições | Retorno médio "
        "da posição | Acerto | Exposição média | Custos (R$) | IR (R$) |\n"
        "|---|---|---|---|---|---|---|---|---|---|"
    )
    inicio, fim = saida["periodo"]
    contagem = saida["contagem"]
    estudo = saida["estudo"]
    pequenos = sum(
        1 for r in estudo["por_tipo"].values() if r["n"] < EVENTOS_MINIMOS_NO_RELATORIO
    )
    linhas = [
        f"# Ficha P0-5: rodada do pré-registro quant v{criterio_quant.VERSAO}",
        "",
        (
            f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC. Período de avaliação de {inicio} a {fim} "
            "(desenvolvimento; holdout lacrado)."
        ),
        (
            f"Tentativas contadas no DSR: {saida['tentativas_totais']}. "
            f"Universo: {saida['universo']['tickers']} tickers."
        ),
        "",
        "Nada aqui é recomendação de investimento.",
        "",
        f"**Veredito do {NOME_DO_CANDIDATO}: {'APROVADO' if veredito.aprovado else 'REPROVADO'}**"
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
        "## Os anúncios de lucro (do trimestre ao sinal)",
        "",
        "| Etapa | Trimestres |",
        "|---|---|",
        *(f"| {nome} | {valor} |" for nome, valor in contagem.items()),
        "",
        "## O candidato (custos base), o estresse e o bruto",
        "",
        cabecalho,
        _linha("candidato", saida["resumo"]),
        _linha("estresse (custos × 2, impacto Y = 2)", saida["estresse"]),
        _linha("bruto (sem custo, imposto nem impacto)", saida["bruto"]),
        _linha("V (1): entrada no dia D (antes do documento)", saida["no_sinal"]),
        "",
        "## O teste do Brasil: o IPE não tem hora",
        "",
        cabecalho,
        *(_linha(n, r) for n, r in saida["brasil"].items()),
        "",
        "## Deslistagens",
        "",
        cabecalho,
        *(_linha(n, r) for n, r in saida["deslistadas"].items()),
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
        "## Estudo dos eventos: CAR (+1, +60) pelo modelo de mercado",
        "",
        (
            f"{estudo['documentos']} documentos do IPE de empresas do universo, um por empresa, tipo e "
            f"dia zero. Tipos com menos de {EVENTOS_MINIMOS_NO_RELATORIO} eventos ficam de fora da "
            f"tabela ({pequenos})."
        ),
        "",
        *_tabela_do_car(estudo["por_tipo"], EVENTOS_MINIMOS_NO_RELATORIO),
        "",
        "### Por tercil da SUE (os anúncios de lucro)",
        "",
        *_tabela_do_car(estudo["por_tercil_da_sue"], 1),
        "",
        "## Limites e cuidados",
        "",
        "- Desenvolvimento só: nada aqui diz o que o holdout vai mostrar; abri-lo é decisão escrita do Tiago.",
        "- O IPE não tem hora: o dia zero é D+1 e a entrada é na abertura de D+2. Dia zero = D é a leitura otimista, proibida no resultado final.",
        "- O lucro vem da conta 3.11 do consolidado; empresa que só publica o individual fica de fora.",
        "- Anúncio cujo ITR ou DFP só aparece na base no dia da entrada ou depois fica de fora (o número poderia ser de uma reapresentação).",
        "- Os CARs se sobrepõem no tempo e entre empresas (mesmo dia, mesmo setor): o t supõe eventos independentes e exagera a confiança.",
        "- O mercado do modelo é o BOVA11 (desde 2009); o β é estimado em 252 pregões e muda com o tempo.",
        "- A recuperação judicial não é filtrada: o acervo não tem a tabela (limitação declarada da seção 8).",
        "- A régua do Ibovespa é o BOVA11 comprado e mantido, sem o IR da venda final.",
        "- O DARF é pago no último pregão do mês seguinte; o IR é o do swing (15%, isenção de R$ 20 mil).",
        "- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.",
    ]
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"rodada_pead_{datetime.now(UTC):%Y%m%d_%H%M}.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def imprimir(texto: str) -> None:
    """Imprime sem quebrar num terminal sem UTF-8 (o `python -I` ignora o PYTHONIOENCODING)."""
    codificacao = sys.stdout.encoding or "utf-8"
    print(texto.encode(codificacao, errors="replace").decode(codificacao))


def main(
    pasta: Path = dados_pead.PASTA_DA_FICHA,
    pasta_do_acervo: Path = dados_pead.PASTA_DO_ACERVO,
) -> int:
    faltas = dados_pead.conferir_base(pasta, pasta_do_acervo)
    if faltas:
        print(MENSAGEM_SEM_BASE.format(pasta=pasta, faltas=", ".join(faltas)))
        return SAIDA_SEM_BASE
    dados = dados_pead.carregar_tabelas(pasta, pasta_do_acervo)
    saida = executar(dados, abrir_registro())
    imprimir(escrever_relatorio(saida).read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
