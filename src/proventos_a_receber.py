"""Lê a planilha de proventos a receber da Área do Investidor da B3 (Extratos → Eventos).

São os proventos já anunciados e ainda não pagos: dividendos, JCP, rendimentos de fundos,
reembolsos (provento de ação emprestada) e o dinheiro do leilão de frações. A tela mostra o que
cada ativo vai pagar, quando e o total.

Formato (conferido numa planilha real de 2026): uma aba "Proventos a Receber" com as colunas
Produto ("PETR4 - PETROLEO BRASILEIRO..."), Tipo (ON, PN, Fundo...), Tipo de Evento (em
maiúsculas, ou "Reembolso - DIVIDENDO"), Previsão de pagamento (texto dd/mm/aaaa, ou "-" quando
a empresa ainda não marcou a data), Instituição, Conta, Quantidade (texto, "1,5" no
fracionário), Preço unitário e Valor líquido. A última linha é o "Total líquido". O JCP vem
**líquido**, com os 15% de imposto já retidos.

Privacidade: como a posição e a movimentação, o arquivo é lido só na memória e nada do conteúdo
vai para os logs.
"""

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from src.carteira_b3 import (
    ArquivoDaB3Error,
    achar_coluna,
    e_linha_de_total,
    ler_abas,
    numero_brasileiro,
    sem_acento,
)
from src.movimentacao_b3 import FRACIONARIO, PADRAO_DO_PRODUTO

# uma carteira de verdade tem algumas dezenas de proventos anunciados
MAXIMO_DE_LINHAS_DOS_PROVENTOS = 2_000
COLUNAS_DO_PRODUTO = ("produto",)
COLUNAS_DO_EVENTO = ("tipo de evento", "evento")
COLUNAS_DA_DATA = ("previsao de pagamento", "data de pagamento", "pagamento")
COLUNAS_DA_QUANTIDADE = ("quantidade",)
COLUNAS_DO_VALOR = ("valor liquido", "valor")
# tipo de evento da B3 (sem acento) → como a tela mostra
NOMES_DOS_EVENTOS = {
    "dividendo": "Dividendo",
    "juros sobre capital proprio": "JCP (líquido)",
    "rendimento": "Rendimento",
    "leilao de fracoes": "Leilão de frações",
}
REEMBOLSO = (
    "reembolso - "  # "Reembolso - DIVIDENDO": o provento da ação que estava emprestada
)

MENSAGEM_SEM_COLUNAS = (
    "Não achei as colunas dos PROVENTOS A RECEBER (Produto, Tipo de Evento, Valor líquido). "
    "Baixe em Extratos → Eventos → Proventos a receber, na Área do Investidor da B3."
)
COMO_BAIXAR_OS_PROVENTOS = (
    "1. Na **Área do Investidor** da B3, abra **Extratos → Eventos** e escolha **Proventos a "
    "receber**.\n"
    "2. Baixe em **Excel**.\n"
    "3. Envie o arquivo aqui. Ele é lido **só na memória** e não fica guardado."
)
AVISO_DOS_PROVENTOS_DE_EXEMPLO = (
    "**Exemplo demonstrativo:** proventos a receber fictícios, não são os seus."
)
NOTA_DOS_PROVENTOS_A_RECEBER = (
    "Valores líquidos, como a B3 informa: o JCP já vem com os 15% de imposto retidos. A data é a "
    'prevista pela empresa e pode mudar; "sem data" é provento anunciado que ainda não tem dia '
    "marcado. Reembolso é o provento de uma ação que estava emprestada. Não é recomendação."
)
SEM_PROVENTOS_A_RECEBER = "A planilha não tem proventos a receber."


@dataclass(frozen=True)
class ProventoPrevisto:
    codigo: str
    tipo: str  # como a tela mostra ("Dividendo", "JCP (líquido)"...)
    data: date | None  # None: anunciado, ainda sem data de pagamento
    quantidade: float  # 0 quando a B3 não informa (leilão de frações)
    valor: float  # líquido


@dataclass(frozen=True)
class ProventosAReceber:
    itens: tuple[ProventoPrevisto, ...]  # pela data prevista; os sem data no fim
    avisos: tuple[str, ...]
    nomes: dict[str, str]  # código → nome do ativo na B3 (diz se é fundo imobiliário)

    @property
    def total(self) -> float:
        return sum(item.valor for item in self.itens)


def _data_prevista(valor: object) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    if texto in ("", "-", "nan", "None"):
        return None
    try:
        dia, mes, ano = (int(parte) for parte in texto.split("/"))
        return date(ano, mes, dia)
    except (
        ValueError
    ) as erro:  # partes que não são número, a mais, a menos ou dia inexistente
        raise ArquivoDaB3Error(
            "Um provento tem uma data de pagamento que não entendi; a B3 usa dd/mm/aaaa."
        ) from erro


def _nome_do_evento(evento: object) -> str:
    texto = sem_acento(evento)
    if texto.startswith(REEMBOLSO):
        provento = _nome_do_evento(texto.removeprefix(REEMBOLSO)).lower()
        provento = provento.replace(" (líquido)", "").replace("jcp", "JCP")
        return f"Reembolso de {provento} (ação emprestada)"
    if texto in NOMES_DOS_EVENTOS:
        return NOMES_DOS_EVENTOS[texto]
    original = " ".join(str(evento).split())  # tipo novo: o nome da B3, sem gritar
    return original[:1].upper() + original[1:].lower()


def _colunas(tabela: pd.DataFrame) -> dict[str, str] | None:
    colunas = {sem_acento(c): c for c in tabela.columns}
    achadas = {
        "produto": achar_coluna(colunas, COLUNAS_DO_PRODUTO),
        "evento": achar_coluna(colunas, COLUNAS_DO_EVENTO),
        "data": achar_coluna(colunas, COLUNAS_DA_DATA),
        "quantidade": achar_coluna(colunas, COLUNAS_DA_QUANTIDADE),
        "valor": achar_coluna(colunas, COLUNAS_DO_VALOR),
    }
    if any(achadas[nome] is None for nome in ("produto", "evento", "valor")):
        return None
    return {nome: coluna for nome, coluna in achadas.items() if coluna is not None}


def ler_proventos_a_receber(conteudo: bytes, nome_do_arquivo: str) -> ProventosAReceber:
    """Lê a planilha de proventos a receber da B3 e devolve cada provento previsto."""
    abas = ler_abas(
        conteudo,
        nome_do_arquivo,
        planilha="proventos a receber",
        maximo_de_linhas=MAXIMO_DE_LINHAS_DOS_PROVENTOS,
    )
    itens: list[ProventoPrevisto] = []
    nomes: dict[str, str] = {}
    sem_codigo = 0
    achou_colunas = False
    for tabela in abas.values():
        if tabela is None or tabela.empty:
            continue
        colunas = _colunas(tabela)
        if colunas is None:
            continue
        achou_colunas = True
        for _, linha in tabela.iterrows():
            if pd.isna(linha[colunas["produto"]]) or e_linha_de_total(linha):
                continue  # a linha "Total líquido" e linhas em branco
            produto = str(linha[colunas["produto"]])
            achado = PADRAO_DO_PRODUTO.match(produto)
            if achado is None:
                sem_codigo += 1  # Tesouro e renda fixa: sem código de negociação
                continue
            codigo = FRACIONARIO.sub("", achado.group(1))
            nomes.setdefault(codigo, produto[achado.end() :].strip())
            quantidade = (
                numero_brasileiro(linha[colunas["quantidade"]])
                if "quantidade" in colunas
                else 0.0
            )
            data = _data_prevista(linha[colunas["data"]]) if "data" in colunas else None
            itens.append(
                ProventoPrevisto(
                    codigo,
                    _nome_do_evento(linha[colunas["evento"]]),
                    data,
                    quantidade,
                    numero_brasileiro(linha[colunas["valor"]]),
                )
            )
    if not achou_colunas:
        raise ArquivoDaB3Error(MENSAGEM_SEM_COLUNAS)
    avisos = []
    if sem_codigo:
        linhas = "1 linha" if sem_codigo == 1 else f"{sem_codigo} linhas"
        avisos.append(
            f"{linhas} sem código de negociação (Tesouro e renda fixa) ficaram de fora: aqui "
            "entram só ações, FIIs, ETFs e BDRs."
        )
    itens.sort(key=lambda item: (item.data is None, item.data or date.min, item.codigo))
    return ProventosAReceber(tuple(itens), tuple(avisos), nomes)
