"""Dicionário de dados da base de cripto (série 1, PR 5; exigência 8 do critério de pronto).

Para cada tabela: de onde vem, a licença, o atraso até o dado valer e, para cada coluna, o que ela
é e em que unidade. Um teste confere que toda coluna que os leitores devolvem está aqui; `em_texto()`
monta o documento que o Tiago revisa.
"""

from dataclasses import dataclass

import pandas as pd

UTC = "UTC"
SATOSHIS = "satoshis (1 BTC = 100 milhões)"


@dataclass(frozen=True)
class Tabela:
    """A descrição de uma tabela: origem, licença (família de `LICENCAS`), atraso e colunas."""

    fonte: str
    familia_da_licenca: str
    atraso: str
    colunas: dict[str, str]


_DIVULGADO = "divulgado_em: desde quando o número podia ser conhecido (UTC)"
_COLETADO = "coletado_em: quando a nossa coleta o leu (UTC)"
_PRECO = {
    "dia": "dia UTC do candle (00:00 a 24:00 UTC)",
    "abertura": "primeiro preço do dia, na moeda da tabela",
    "maxima": "maior preço do dia, na moeda da tabela",
    "minima": "menor preço do dia, na moeda da tabela",
    "fechamento": "último preço do dia, na moeda da tabela",
    "volume": "volume negociado no dia, em BTC",
    "negocios": "número de negócios no dia (só a Kraken informa)",
    "moeda": "BRL (Mercado Bitcoin) ou USD (Kraken)",
    "divulgado_em": _DIVULGADO,
}

DICIONARIO: dict[str, Tabela] = {
    "blocos": Tabela(
        "nó próprio do Bitcoin (Bitcoin Core)",
        "btc",
        "6 confirmações (cerca de 1 hora)",
        {
            "altura": "número do bloco na cadeia",
            "hash": "identificador do bloco (SHA-256 duplo do cabeçalho)",
            "hora": "hora escrita pelo minerador (UTC); pode andar para trás",
            "hora_mediana": "mediana das horas dos 11 blocos anteriores (UTC); só cresce",
            "n_transacoes": "transações no bloco, contando a coinbase",
            "taxas_total": f"taxas pagas pelas transações comuns, em {SATOSHIS}",
            "taxa_mediana_por_vbyte": "taxa típica, em satoshis por byte virtual",
            "valor_movimentado": f"soma das saídas das transações comuns (inclui troco), em {SATOSHIS}",
            "dias_moeda_destruidos": "moedas gastas vezes os dias paradas, em BTC-dias",
            "emissao": f"moedas novas permitidas no bloco, em {SATOSHIS}",
            "dificuldade": "dificuldade da mineração (1 = a de 2009)",
            "coletado_em": _COLETADO,
        },
    ),
    "rede_diaria": Tabela(
        "resumo dos blocos por dia UTC",
        "btc",
        "o dia vale quando a hora mediana passa da meia-noite e esse bloco tem 6 confirmações",
        {
            "dia": "dia UTC, pela hora dos blocos",
            "n_blocos": "blocos com hora no dia",
            "n_transacoes": "soma das transações do dia",
            "taxas_total": f"soma das taxas do dia, em {SATOSHIS}",
            "taxa_mediana_por_vbyte": "mediana das taxas típicas dos blocos do dia (sat/vB)",
            "valor_movimentado": f"soma do valor movimentado no dia, em {SATOSHIS}",
            "dias_moeda_destruidos": "soma dos dias-moeda destruídos no dia, em BTC-dias",
            "emissao": f"moedas novas do dia, em {SATOSHIS}",
            "dificuldade": "dificuldade do último bloco do dia",
            "fracao_parada_1_ano": "fração das moedas não gastas paradas há mais de 365 dias",
            "divulgado_em": _DIVULGADO,
            "coletado_em": _COLETADO,
        },
    ),
    "precos": Tabela(
        "Kraken (dólar) e Mercado Bitcoin (reais)",
        "kraken / mb",
        "o candle vale à meia-noite UTC que o fecha",
        _PRECO,
    ),
    "cftc": Tabela(
        "CFTC, Traders in Financial Futures (futuros de Bitcoin da CME)",
        "cftc",
        "relatório de terça vale na segunda seguinte, 15h30 de Nova York",
        {
            "relatorio": "terça-feira a que as posições se referem (Nova York)",
            "contrato": "bitcoin (5 BTC por contrato) ou micro_bitcoin (0,1 BTC)",
            "contratos_em_aberto": "contratos em aberto no total",
            "gestores_comprados": "contratos comprados por gestores (asset managers)",
            "gestores_vendidos": "contratos vendidos por gestores (asset managers)",
            "alavancados_comprados": "contratos comprados por fundos alavancados",
            "alavancados_vendidos": "contratos vendidos por fundos alavancados",
            "divulgado_em": _DIVULGADO,
        },
    ),
    "wikipedia": Tabela(
        "Wikimedia, acessos diários de pessoas a um artigo",
        "wiki",
        "o dia vale no fim do dia seguinte",
        {
            "dia": "dia UTC",
            "projeto": "en.wikipedia (inglês: o mundo) ou pt.wikipedia (português: o Brasil)",
            "artigo": "título do artigo",
            "acessos": "acessos de pessoas (sem robôs)",
            "divulgado_em": _DIVULGADO,
        },
    ),
    "gdelt": Tabela(
        "GDELT DOC 2.0 (notícias do mundo)",
        "gdelt",
        "o dia vale uma hora depois da meia-noite UTC",
        {
            "dia": "dia UTC",
            "noticias": "notícias que citaram o termo",
            "fracao_das_noticias": "notícias do termo divididas por todas as que o GDELT viu",
            "tom": "tom médio das notícias (negativo = pessimista), ponderado pelas notícias",
            "divulgado_em": _DIVULGADO,
        },
    ),
    "receita_totais": Tabela(
        "Receita Federal, dados abertos de criptoativos (Relatório nº 1)",
        "rfb",
        "mensal, cerca de 2 meses de atraso; vale à 0h de Brasília do dia seguinte à data do arquivo",
        {
            "mes": "primeiro dia do mês declarado",
            "exterior_pf_milhoes": "pessoas físicas com exchange no exterior, R$ milhões",
            "exterior_pj_milhoes": "pessoas jurídicas com exchange no exterior, R$ milhões",
            "exterior_milhoes": "total com exchange no exterior, R$ milhões",
            "sem_exchange_pf_milhoes": "pessoas físicas sem exchange, R$ milhões",
            "sem_exchange_pj_milhoes": "pessoas jurídicas sem exchange, R$ milhões",
            "sem_exchange_milhoes": "total sem exchange, R$ milhões",
            "exchanges_no_brasil_milhoes": "declarado pelas exchanges do Brasil, R$ milhões",
            "total_milhoes": "total geral do mês, R$ milhões",
            "divulgado_em": _DIVULGADO,
        },
    ),
    "receita_criptoativo": Tabela(
        "Receita Federal, dados abertos de criptoativos (Relatório nº 4)",
        "rfb",
        "o mesmo do Relatório nº 1",
        {
            "mes": "primeiro dia do mês declarado",
            "criptoativo": "código como a Receita agrupou: BTC, ETH, USDT, USDC ou BRZ",
            "operacoes": "número de operações declaradas",
            "valor_total_reais": "valor total das operações, em reais",
            "divulgado_em": _DIVULGADO,
        },
    ),
}


def colunas_sem_descricao(nome: str, tabela: pd.DataFrame) -> list[str]:
    """As colunas da tabela que o dicionário não descreve (deve ser vazio)."""
    descritas = DICIONARIO[nome].colunas
    return [coluna for coluna in tabela.columns if coluna not in descritas]


def em_texto() -> str:
    """O dicionário inteiro em Markdown, para revisão."""
    partes = [
        "# Dicionário de dados da base de cripto",
        "",
        f"Fuso de todas as horas: {UTC}.",
        "",
    ]
    for nome, tabela in DICIONARIO.items():
        partes += [
            f"## {nome}",
            "",
            f"- Fonte: {tabela.fonte}",
            f"- Licença: família `{tabela.familia_da_licenca}` em `src/banco/coletas.py`",
            f"- Atraso: {tabela.atraso}",
            "",
            "| Coluna | O que é |",
            "|---|---|",
            *[
                f"| `{coluna}` | {descricao} |"
                for coluna, descricao in tabela.colunas.items()
            ],
            "",
        ]
    return "\n".join(partes)
