"""Lê a planilha de negociação da Área do Investidor da B3 (Extratos → Negociação).

Cada linha é um negócio: uma compra ou uma venda num dia, com quantidade, preço e valor. É daqui
que sai o resultado realizado de cada mês (`src/resultado_por_mes.py`), com o day trade separado,
porque a movimentação só mostra a liquidação, dois dias depois, sem dizer o que foi day trade.

Formato (conferido numa planilha real de 2026): uma aba "Negociação" com as colunas Data do
Negócio (texto dd/mm/aaaa), Tipo de Movimentação ("Compra"/"Venda"), Mercado ("Mercado à Vista",
"Mercado Fracionário", "Futuro", "Opção de Compra sobre Ações"...), Prazo/Vencimento ("-" no à
vista), Instituição, Código de Negociação, Quantidade, Preço e Valor. Nos futuros o Valor já vem
multiplicado pelo tamanho do contrato (R$ 0,20 por ponto no WIN, R$ 10 no WDO), então o resultado
sai do Valor, sem tabela de multiplicadores.

A planilha só traz o código. Um código terminado em 11 pode ser FII, ETF ou unit de empresa: quem
diz é o nome do ativo, que vem da movimentação ou dos proventos a receber (`nomes`). Sem o nome,
o ativo fica em "outros", com aviso.

Privacidade: como as outras planilhas da B3, o arquivo é lido só na memória e nada do conteúdo vai
para os logs.
"""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from src.carteira_b3 import (
    ArquivoDaB3Error,
    achar_coluna,
    ler_abas,
    numero_brasileiro,
    sem_acento,
)
from src.movimentacao_b3 import FRACIONARIO

# um ano de day trade em minicontratos passa de 2 mil negócios
MAXIMO_DE_LINHAS_DA_NEGOCIACAO = 20_000
COLUNAS_DA_DATA = ("data do negocio", "data")
COLUNAS_DO_LADO = ("tipo de movimentacao", "compra/venda", "c/v")
COLUNAS_DO_MERCADO = ("mercado",)
COLUNAS_DO_CODIGO = ("codigo de negociacao", "codigo")
COLUNAS_DA_QUANTIDADE = ("quantidade",)
COLUNAS_DO_PRECO = ("preco",)
COLUNAS_DO_VALOR = ("valor",)

A_VISTA = ("mercado a vista", "mercado fracionario")
FUTURO = "futuro"
# mercados conhecidos que ficam fora do resultado → como o aviso os chama
FORA_DO_RESULTADO = {
    "opcao de compra sobre acoes": "opções",
    "opcao de venda sobre acoes": "opções",
    "exercicio de opcao de compra": "opções",
    "exercicio de opcao de venda": "opções",
    "renda fixa": "renda fixa",
}
PADRAO_DO_CODIGO = re.compile(r"^([A-Z]{4})(\d{1,2})$")
FINAIS_DE_ACAO = {"3", "4", "5", "6", "7", "8"}
# começos de palavra do nome do ativo na B3 (sem acento, minúsculas): "imob" pega "IMOB",
# "IMOBILIÁRIO" e "IMOBILIARIOS", que aparecem nos nomes reais
PALAVRAS_DE_FII = ("fii", "imob", "fiagro")
PALAVRAS_DE_OUTROS_FUNDOS = ("fdo", "fundo", "etf", "indice", "ishares")

MENSAGEM_SEM_COLUNAS = (
    "Não achei as colunas da NEGOCIAÇÃO (Data do Negócio, Tipo de Movimentação, Mercado, Código "
    "de Negociação, Quantidade). Baixe em Extratos → Negociação, na Área do Investidor da B3."
)


@dataclass(frozen=True)
class Negocio:
    data: date
    codigo: str  # sem o F do fracionário
    classe: (
        str  # "acao", "fii", "futuro" ou "outros" (ETF, fundo ou código 11 sem nome)
    )
    compra: bool  # False: venda
    quantidade: float
    preco: float
    valor: float  # o dinheiro do negócio (nos futuros, já com o multiplicador)


@dataclass(frozen=True)
class NegociacaoB3:
    negocios: tuple[Negocio, ...]  # em ordem de data
    fora: int  # negócios que não entram no resultado (opções, renda fixa, BDR...)
    avisos: tuple[str, ...]
    primeira_data: date | None
    ultima_data: date | None


def _data(valor: object) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        dia, mes, ano = (int(parte) for parte in str(valor).strip().split("/"))
        return date(ano, mes, dia)
    except (
        ValueError
    ) as erro:  # partes que não são número, a mais, a menos ou dia inexistente
        raise ArquivoDaB3Error(
            "Um negócio tem uma data que não entendi; a B3 usa dd/mm/aaaa."
        ) from erro


def _colunas(tabela: pd.DataFrame) -> dict[str, str] | None:
    colunas = {sem_acento(c): c for c in tabela.columns}
    achadas = {
        "data": achar_coluna(colunas, COLUNAS_DA_DATA),
        "lado": achar_coluna(colunas, COLUNAS_DO_LADO),
        "mercado": achar_coluna(colunas, COLUNAS_DO_MERCADO),
        "codigo": achar_coluna(colunas, COLUNAS_DO_CODIGO),
        "quantidade": achar_coluna(colunas, COLUNAS_DA_QUANTIDADE),
        "preco": achar_coluna(colunas, COLUNAS_DO_PRECO),
        "valor": achar_coluna(colunas, COLUNAS_DO_VALOR),
    }
    obrigatorias = ("data", "lado", "mercado", "codigo", "quantidade")
    if any(achadas[nome] is None for nome in obrigatorias):
        return None
    return {nome: coluna for nome, coluna in achadas.items() if coluna is not None}


def _classe_no_a_vista(codigo: str, nomes: dict[str, str]) -> str | None:
    """ "acao", "fii" ou "outros"; None para BDR e códigos que não são de ativo da bolsa."""
    achado = PADRAO_DO_CODIGO.match(codigo)
    if achado is None:
        return None
    final = achado.group(2)
    if final in FINAIS_DE_ACAO:
        return "acao"
    if final != "11":
        return None  # BDR (34, 35...) e outros finais
    nome = sem_acento(nomes.get(codigo, ""))
    if not nome:
        return "outros"
    palavras = re.split(r"[^a-z0-9]+", nome)
    if any(p.startswith(PALAVRAS_DE_FII) for p in palavras):
        return "fii"
    if any(p.startswith(PALAVRAS_DE_OUTROS_FUNDOS) for p in palavras):
        return "outros"
    return "acao"  # unit de empresa (KLBN11, TAEE11): ações juntas num código só


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _avisos(fora: Counter[str], sem_nome: set[str]) -> list[str]:
    avisos = []
    if fora:
        lista = ", ".join(
            f"{tipo}: {_plural(n, 'negócio', 'negócios')}" for tipo, n in fora.items()
        )
        avisos.append(
            f"Ficaram de fora do resultado ({lista}). Opções têm exercício e vencimento que "
            "não vêm na planilha; BDR e renda fixa têm regras próprias."
        )
    if sem_nome:
        avisos.append(
            f"Não deu para saber se {', '.join(sorted(sem_nome))} é FII, ETF ou unit: ficou em "
            '"Outros". Envie também a movimentação ou os proventos a receber, que trazem o '
            "nome do ativo."
        )
    return avisos


def ler_negociacao(
    conteudo: bytes, nome_do_arquivo: str, nomes: dict[str, str] | None = None
) -> NegociacaoB3:
    """Lê a negociação da B3 e devolve os negócios que entram no resultado, em ordem de data.

    `nomes` (código → nome do ativo na B3) diz se um código terminado em 11 é FII.
    """
    nomes = nomes or {}
    abas = ler_abas(
        conteudo,
        nome_do_arquivo,
        planilha="negociação",
        maximo_de_linhas=MAXIMO_DE_LINHAS_DA_NEGOCIACAO,
    )
    negocios: list[Negocio] = []
    datas: list[date] = []
    fora: Counter[str] = Counter()
    sem_nome: set[str] = set()
    achou_colunas = False
    for tabela in abas.values():
        if tabela is None or tabela.empty:
            continue
        colunas = _colunas(tabela)
        if colunas is None:
            continue
        achou_colunas = True
        for _, linha in tabela.iterrows():
            if pd.isna(linha[colunas["data"]]):
                continue  # linha em branco no fim da planilha
            dia = _data(linha[colunas["data"]])
            datas.append(dia)
            mercado = sem_acento(linha[colunas["mercado"]])
            codigo = FRACIONARIO.sub("", str(linha[colunas["codigo"]]).strip().upper())
            if mercado == FUTURO:
                classe: str | None = "futuro"
            elif mercado in A_VISTA:
                classe = _classe_no_a_vista(codigo, nomes)
                if classe is None:
                    fora["BDR e outros códigos"] += 1
                    continue
                if classe == "outros" and codigo not in nomes:
                    sem_nome.add(codigo)
            else:
                original = " ".join(str(linha[colunas["mercado"]]).split())
                fora[FORA_DO_RESULTADO.get(mercado, original)] += 1
                continue
            quantidade = numero_brasileiro(linha[colunas["quantidade"]])
            preco = (
                numero_brasileiro(linha[colunas["preco"]])
                if "preco" in colunas
                else 0.0
            )
            valor = (
                numero_brasileiro(linha[colunas["valor"]])
                if "valor" in colunas
                else 0.0
            )
            if valor <= 0 and classe != "futuro":
                valor = quantidade * preco
            negocios.append(
                Negocio(
                    dia,
                    codigo,
                    classe,
                    sem_acento(linha[colunas["lado"]]).startswith("c"),
                    quantidade,
                    preco,
                    valor,
                )
            )
    if not achou_colunas:
        raise ArquivoDaB3Error(MENSAGEM_SEM_COLUNAS)
    negocios.sort(key=lambda negocio: negocio.data)  # estável: mantém a ordem no dia
    return NegociacaoB3(
        tuple(negocios),
        sum(fora.values()),
        tuple(_avisos(fora, sem_nome)),
        min(datas) if datas else None,
        max(datas) if datas else None,
    )
