"""Lê a planilha de movimentação da Área do Investidor da B3 (Extratos → Movimentação).

Cada linha é um acontecimento na custódia: compra ou venda liquidada, provento, desdobro,
transferência entre corretoras, aluguel de ações, Tesouro... O leitor transforma as linhas que
importam para o custo médio e para os proventos em `Lancamento` (`src/dividendos_e_custo.py`) e
conta as outras, sem esconder nada: o que ele não conhece vira aviso, nunca número.

Formato (conferido numa planilha real de 2026): uma aba "Movimentação" com as colunas
Entrada/Saída ("Credito"/"Debito"), Data (texto dd/mm/aaaa), Movimentação, Produto ("PETR4 -
PETROLEO BRASILEIRO..."), Instituição, Quantidade, Preço unitário e Valor da Operação ("-" quando
não há). O JCP vem **líquido**: o valor já tem os 15% de imposto retidos na fonte.

Privacidade: como a planilha de posição, o arquivo é lido só na memória e nada do conteúdo vai
para os logs.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from src.carteira_b3 import (
    ArquivoDaB3Error,
    achar_coluna,
    ler_abas,
    numero_brasileiro,
    sem_acento,
)
from src.dividendos_e_custo import Lancamento

# uma movimentação de vários anos tem centenas ou poucos milhares de linhas
MAXIMO_DE_LINHAS_DA_MOVIMENTACAO = 20_000
COLUNAS_DA_ENTRADA = ("entrada/saida",)
COLUNAS_DA_DATA = ("data",)
COLUNAS_DO_TIPO = ("movimentacao",)
COLUNAS_DO_PRODUTO = ("produto",)
COLUNAS_DA_QUANTIDADE = ("quantidade",)
COLUNAS_DO_PRECO = ("preco unitario", "preco")
COLUNAS_DO_VALOR = ("valor da operacao", "valor")

LIQUIDACAO = "transferencia - liquidacao"
_QUASE_ZERO = 1e-9
# (tipo da B3 sem acento, entrada ou saída) → tipo do lançamento. Liquidação SEM dinheiro não é
# compra nem venda (ver `_movimentos_sem_dinheiro`)
TIPOS = {
    ("transferencia - liquidacao", "credito"): "compra",
    ("transferencia - liquidacao", "debito"): "venda",
    ("dividendo", "credito"): "dividendo",
    ("juros sobre capital proprio", "credito"): "jcp",
    ("rendimento", "credito"): "rendimento",
    ("reembolso", "credito"): "reembolso",  # provento de ação emprestada
    # a taxa do aluguel; a linha só com a quantidade emprestada vem sem valor e fica de fora
    ("emprestimo", "credito"): "aluguel",
    # devolução de capital de FII: reduz o custo médio (não é provento)
    ("amortizacao", "credito"): "amortizacao",
    ("desdobro", "credito"): "desdobro",
    ("grupamento", "debito"): "grupamento",
    ("bonificacao em ativos", "credito"): "bonificacao",
    ("fracao em ativos", "debito"): "venda",  # a fração vai a leilão
}
# não mudam o custo médio nem são proventos: ficam fora das contas, sem aviso
FORA_DAS_CONTAS = {
    "transferencia",  # entre corretoras: sai de uma e entra na outra
    "emprestimo",  # aluguel de ações sem valor: a ação continua sendo da pessoa
    "leilao de fracao",  # o dinheiro da fração já saiu como venda
    "direito de subscricao",
    "direitos de subscricao - nao exercido",
    "cessao de direitos",
    "cessao de direitos - solicitada",
    # o provento que passou de uma corretora para outra: vem em par Crédito + Débito, mesma data,
    # produto e valor (conferido numa movimentação real de 12 meses), e o par soma zero
    "dividendo - transferido",
    "juros sobre capital proprio - transferido",
}
# futuros e opções: o Produto vem como "Futuro - WINV26" ou "Opção de Compra - BOVAE133 - ..."
DERIVATIVO = re.compile(
    r"^\s*(Futuro|Op[cç][aã]o de (Compra|Venda))\s+-\s", re.IGNORECASE
)
PADRAO_DO_PRODUTO = re.compile(r"^\s*([A-Z]{4}\d{1,2}[A-Z]?)\s+-\s")
# PETR4F é a PETR4 comprada no mercado fracionário: o mesmo ativo, o mesmo custo médio
FRACIONARIO = re.compile(r"(?<=\d)F$")

MENSAGEM_SEM_COLUNAS = (
    "Não achei as colunas da MOVIMENTAÇÃO (Entrada/Saída, Data, Movimentação, Produto, "
    "Quantidade). Baixe em Extratos → Movimentação, na Área do Investidor da B3. A planilha de "
    "posição vai no outro campo."
)


@dataclass(frozen=True)
class MovimentacaoB3:
    lancamentos: tuple[Lancamento, ...]  # em ordem de data
    fora_das_contas: int  # linhas conhecidas que não entram nas contas
    avisos: tuple[str, ...]
    primeira_data: date | None
    ultima_data: date | None
    nomes: dict[str, str] = field(default_factory=dict)  # código → nome (diz se é FII)


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
            "Uma linha da movimentação tem uma data que não entendi; a B3 usa dd/mm/aaaa."
        ) from erro


def _colunas(tabela: pd.DataFrame) -> dict[str, str] | None:
    colunas = {sem_acento(c): c for c in tabela.columns}
    achadas = {
        "entrada": achar_coluna(colunas, COLUNAS_DA_ENTRADA),
        "data": achar_coluna(colunas, COLUNAS_DA_DATA),
        "tipo": achar_coluna(colunas, COLUNAS_DO_TIPO),
        "produto": achar_coluna(colunas, COLUNAS_DO_PRODUTO),
        "quantidade": achar_coluna(colunas, COLUNAS_DA_QUANTIDADE),
        "preco": achar_coluna(colunas, COLUNAS_DO_PRECO),
        "valor": achar_coluna(colunas, COLUNAS_DO_VALOR),
    }
    obrigatorias = ("entrada", "data", "tipo", "produto", "quantidade")
    if any(achadas[nome] is None for nome in obrigatorias):
        return None
    return {nome: coluna for nome, coluna in achadas.items() if coluna is not None}


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _valor_da_linha(
    linha: pd.Series, colunas: dict[str, str], quantidade: float
) -> float:
    """O dinheiro da linha: o "Valor da Operação" ou, sem ele, quantidade × preço (0 se não há)."""
    valor = numero_brasileiro(linha[colunas["valor"]]) if "valor" in colunas else 0.0
    if valor <= 0 and "preco" in colunas:
        valor = quantidade * numero_brasileiro(linha[colunas["preco"]])
    return valor


def _quantidade(valor: float) -> str:
    """9205 → "9.205"; 0,5 → "0,5" (até 2 casas, sem zeros à direita)."""
    texto = f"{valor:,.2f}".rstrip("0").rstrip(".")
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


@dataclass(frozen=True)
class _SemDinheiro:
    """Uma liquidação sem valor: ações que saíram ou entraram sem dinheiro."""

    data: date
    codigo: str
    saida: bool
    quantidade: float


def _movimentos_sem_dinheiro(
    movimentos: list[_SemDinheiro],
) -> tuple[list[Lancamento], list[_SemDinheiro]]:
    """Separa as liquidações sem valor em (entradas que viram compra sem valor, saídas).

    Toda venda traz dinheiro: uma saída sem valor não é venda (no aluguel de ações a B3 escreve
    assim a ida das ações para quem tomou emprestado, e elas continuam sendo da pessoa). Uma
    entrada sem valor é a volta de uma saída anterior do mesmo ativo; sem saída antes, são ações
    recebidas sem custo conhecido e continuam como compra sem valor (custo médio incompleto).
    """
    fora_de_casa: dict[str, float] = defaultdict(float)
    compras: list[Lancamento] = []
    saidas: list[_SemDinheiro] = []
    # no mesmo dia, a saída vem antes da volta
    for mov in sorted(movimentos, key=lambda m: (m.data, not m.saida)):
        if mov.saida:
            fora_de_casa[mov.codigo] += mov.quantidade
            saidas.append(mov)
        elif fora_de_casa[mov.codigo] >= mov.quantidade - _QUASE_ZERO:
            fora_de_casa[mov.codigo] -= mov.quantidade
        else:
            compras.append(
                Lancamento(mov.data, mov.codigo, "compra", mov.quantidade, 0.0)
            )
    return compras, saidas


def _aviso_das_saidas(saidas: list[_SemDinheiro]) -> str:
    lista = "; ".join(
        f"{s.codigo} ({_quantidade(s.quantidade)} em {s.data:%d/%m/%Y})" for s in saidas
    )
    return (
        "Saídas de ações sem dinheiro (aluguel de ações ou transferência) não contam como "
        f"venda: {lista}. Essas ações continuam no custo médio."
    )


def _avisos_do_que_ficou_de_fora(
    renda_fixa: int, derivativos: int, desconhecidos: dict[str, int]
) -> list[str]:
    avisos: list[str] = []
    if derivativos:
        avisos.append(
            f"{_plural(derivativos, 'linha', 'linhas')} de futuros e opções "
            f"{'ficou' if derivativos == 1 else 'ficaram'} de fora: aqui entram só ativos com "
            "código de negociação em custódia (ações, FIIs, ETFs, BDRs)."
        )
    if renda_fixa:
        ficou = "ficou" if renda_fixa == 1 else "ficaram"
        avisos.append(
            f"{_plural(renda_fixa, 'linha', 'linhas')} de Tesouro e renda fixa {ficou} de "
            "fora: aqui entram só ativos com código de negociação (ações, FIIs, ETFs, BDRs)."
        )
    if desconhecidos:
        lista = "; ".join(
            f"{rotulo}: {_plural(n, 'linha', 'linhas')}"
            for rotulo, n in desconhecidos.items()
        )
        avisos.append(
            f"Tipos de movimentação não reconhecidos ficaram de fora das contas ({lista}). "
            "Se algum muda a quantidade de ações, o custo médio desse ativo pode não bater."
        )
    return avisos


def ler_movimentacao(conteudo: bytes, nome_do_arquivo: str) -> MovimentacaoB3:
    """Lê a movimentação da B3 e devolve os lançamentos que entram nas contas."""
    abas = ler_abas(
        conteudo,
        nome_do_arquivo,
        planilha="movimentação",
        maximo_de_linhas=MAXIMO_DE_LINHAS_DA_MOVIMENTACAO,
    )
    lancamentos: list[Lancamento] = []
    sem_dinheiro: list[_SemDinheiro] = []
    datas: list[date] = []
    fora = renda_fixa = derivativos = 0
    desconhecidos: dict[str, int] = {}
    nomes: dict[str, str] = {}
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
            nome_do_tipo = str(linha[colunas["tipo"]]).strip()
            tipo_da_b3 = sem_acento(nome_do_tipo)
            entrada = sem_acento(linha[colunas["entrada"]])
            produto = str(linha[colunas["produto"]])
            achado = PADRAO_DO_PRODUTO.match(produto)
            if achado is None:
                if DERIVATIVO.match(produto):
                    derivativos += (
                        1  # contrato, não ativo em custódia: não tem custo médio
                    )
                    continue
                renda_fixa += 1  # Tesouro, CDB, debênture: não têm código de negociação
                continue
            nomes.setdefault(
                FRACIONARIO.sub("", achado.group(1)), produto[achado.end() :].strip()
            )
            tipo = TIPOS.get((tipo_da_b3, entrada))
            if tipo is None:
                if tipo_da_b3 in FORA_DAS_CONTAS:
                    fora += 1
                else:
                    rotulo = f"{nome_do_tipo} ({linha[colunas['entrada']]})"
                    desconhecidos[rotulo] = desconhecidos.get(rotulo, 0) + 1
                continue
            quantidade = numero_brasileiro(linha[colunas["quantidade"]])
            valor = _valor_da_linha(linha, colunas, quantidade)
            codigo = FRACIONARIO.sub("", achado.group(1))
            if tipo == "aluguel" and valor <= 0:
                fora += 1  # só a quantidade emprestada: não é renda nem muda o custo
                continue
            if tipo_da_b3 == LIQUIDACAO and valor <= 0:
                saida = entrada == "debito"
                sem_dinheiro.append(_SemDinheiro(dia, codigo, saida, quantidade))
                continue
            lancamentos.append(Lancamento(dia, codigo, tipo, quantidade, valor))
    if not achou_colunas:
        raise ArquivoDaB3Error(MENSAGEM_SEM_COLUNAS)
    compras_sem_valor, saidas_sem_valor = _movimentos_sem_dinheiro(sem_dinheiro)
    lancamentos += compras_sem_valor
    fora += len(sem_dinheiro) - len(compras_sem_valor)
    avisos = []
    if saidas_sem_valor:
        avisos.append(_aviso_das_saidas(saidas_sem_valor))
    avisos += _avisos_do_que_ficou_de_fora(renda_fixa, derivativos, desconhecidos)
    lancamentos.sort(
        key=lambda lanc: lanc.data
    )  # a B3 manda do mais novo ao mais velho
    return MovimentacaoB3(
        tuple(lancamentos),
        fora,
        tuple(avisos),
        min(datas) if datas else None,
        max(datas) if datas else None,
        nomes,
    )
