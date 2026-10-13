"""Lê a carteira exportada da Área do Investidor da B3 (investidor.b3.com.br).

A API da B3 só atende empresas credenciadas (B2B, com certificado e contrato), então o TickerLab
usa o caminho que qualquer investidor tem: baixar a planilha de posição na Área do Investidor
(Extratos → Posição → baixar em Excel) e enviar o arquivo aqui.

O arquivo tem uma aba por tipo de produto (Ações, BDR, ETF, Fundo de Investimento, Tesouro
Direto, Renda Fixa...). As colunas são achadas pelo NOME, sem depender da ordem, de acentos ou
de maiúsculas, porque a B3 muda o formato de tempos em tempos.

Privacidade: o arquivo é lido só na memória, para montar a análise e o relatório. Nada é gravado
e nada do conteúdo vai para os logs (é a carteira real de alguém).
"""

import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from io import BytesIO

import pandas as pd

TAMANHO_MAXIMO = 5 * 1024 * 1024  # 5 MB: uma posição de verdade tem poucos KB
# o .xlsx é um zip: um arquivo pequeno pode virar gigabytes ao abrir (bomba de descompressão)
TAMANHO_MAXIMO_DESCOMPRIMIDO = 20 * 1024 * 1024
MAXIMO_DE_LINHAS = 5_000  # por aba: uma carteira de verdade tem dezenas de linhas
# nomes de coluna que a B3 já usou (já sem acento e em minúsculas)
COLUNAS_DO_CODIGO = ("codigo de negociacao", "codigo", "ticker", "ativo")
COLUNAS_DO_PRODUTO = ("produto",)
COLUNAS_DA_QUANTIDADE = ("quantidade", "quantidade disponivel")
COLUNAS_DO_VALOR = (
    "valor atualizado",
    "valor atualizado (r$)",
    "valor",
    "valor liquido",
)
# aba → tipo mostrado no relatório
TIPOS_DAS_ABAS = {
    "acoes": "Ações",
    "acao": "Ações",
    "bdr": "BDR",
    "etf": "ETF",
    "fundo de investimento": "Fundos imobiliários e outros",
    "fundos imobiliarios": "Fundos imobiliários e outros",
    "fii": "Fundos imobiliários e outros",
    "tesouro direto": "Tesouro Direto",
    "renda fixa": "Renda fixa",
}
SEM_COTACAO = ("Tesouro Direto", "Renda fixa")  # sem histórico de preço no Yahoo
PADRAO_DO_CODIGO = re.compile(
    r"\b([A-Z]{4}\d{1,2}[A-Z]?)\b"
)  # PETR4, TAEE11, BOVA11, AAPL34


class ArquivoDaB3Error(ValueError):
    """O arquivo não parece a posição exportada da Área do Investidor (a mensagem explica)."""


@dataclass
class CarteiraB3:
    posicoes: pd.DataFrame  # colunas: codigo, ticker (com .SA), tipo, quantidade, valor
    sem_cotacao: pd.DataFrame  # Tesouro e renda fixa: tipo, produto, valor
    avisos: list[str] = field(default_factory=list)

    @property
    def valor_total(self) -> float:
        return float(self.posicoes["valor"].sum() + self.sem_cotacao["valor"].sum())

    def pesos(self) -> pd.Series:
        """Peso de cada ativo com cotação, pelo valor de hoje (soma 1 entre eles)."""
        valores = self.posicoes.set_index("ticker")["valor"]
        return valores / valores.sum()


def sem_acento(texto: object) -> str:
    """Minúsculas, sem acento e com um espaço só: para achar colunas e textos pelo nome."""
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(texto.lower().replace("_", " ").split())


def achar_coluna(colunas: dict[str, str], candidatos: tuple[str, ...]) -> str | None:
    """A primeira coluna da planilha cujo nome (já sem acento) está entre os candidatos."""
    for candidato in candidatos:
        if candidato in colunas:
            return colunas[candidato]
    return None


def numero_brasileiro(valor: object) -> float:
    """Aceita número ou texto brasileiro ("1.234,56", "R$ 10,00", "-")."""
    if isinstance(valor, int | float):
        return float(valor)
    texto = str(valor).replace("R$", "").replace(" ", "").strip()
    if texto in ("", "-", "nan", "None"):
        return 0.0
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def e_linha_de_total(linha: pd.Series) -> bool:
    """A planilha da B3 pode terminar com uma linha "Total" que soma as outras."""
    return any(
        sem_acento(v).startswith("total") for v in linha.dropna() if isinstance(v, str)
    )


def _tipo_da_aba(nome: str) -> str | None:
    nome = sem_acento(nome)
    for chave, tipo in TIPOS_DAS_ABAS.items():
        if nome.startswith(chave):
            return tipo
    return None


def _arquivo_invalido(planilha: str) -> str:
    return (
        f"Não consegui abrir o arquivo. Envie a planilha de {planilha} baixada da Área do "
        "Investidor da B3 (.xlsx)."
    )


def _conferir_tamanho_descomprimido(conteudo: bytes, planilha: str) -> None:
    """Recusa o .xlsx que ficaria grande demais ao abrir, antes de abri-lo.

    O tamanho de cada parte vem do índice do zip; o `zipfile` do Python não deixa uma parte
    render mais do que o índice declara, então a soma é um teto confiável.
    """
    try:
        with zipfile.ZipFile(BytesIO(conteudo)) as arquivo:
            descomprimido = sum(parte.file_size for parte in arquivo.infolist())
    except zipfile.BadZipFile as erro:
        raise ArquivoDaB3Error(_arquivo_invalido(planilha)) from erro
    if descomprimido > TAMANHO_MAXIMO_DESCOMPRIMIDO:
        raise ArquivoDaB3Error(
            f"A planilha fica grande demais ao abrir; a de {planilha} da B3 é bem menor."
        )


def _conferir_linhas(
    abas: dict[str, pd.DataFrame], planilha: str, maximo_de_linhas: int
) -> None:
    if any(len(tabela) > maximo_de_linhas for tabela in abas.values()):
        limite = f"{maximo_de_linhas:,}".replace(",", ".")  # 5.000, como no Brasil
        raise ArquivoDaB3Error(
            f"A planilha tem mais de {limite} linhas numa aba; a de {planilha} da B3 tem "
            "bem menos."
        )


def ler_abas(
    conteudo: bytes,
    nome_do_arquivo: str,
    *,
    planilha: str = "posição",
    maximo_de_linhas: int = MAXIMO_DE_LINHAS,
) -> dict[str, pd.DataFrame]:
    """Abre a planilha da Área do Investidor (.xlsx ou .csv), aba por aba, com as travas.

    Recusa arquivo grande demais, zip que explode ao abrir e aba com linhas demais, com uma
    mensagem que fala da `planilha` esperada ("posição", "movimentação").
    """
    if len(conteudo) > TAMANHO_MAXIMO:
        raise ArquivoDaB3Error(
            f"O arquivo passa de 5 MB; a planilha de {planilha} da B3 é bem menor."
        )
    # lê uma linha a mais que o limite: só para saber se passou dele, sem ler o resto
    if nome_do_arquivo.lower().endswith(".csv"):
        texto = conteudo.decode("utf-8-sig", errors="replace")
        separador = ";" if texto.count(";") > texto.count(",") else ","
        abas = {
            "acoes": pd.read_csv(
                BytesIO(conteudo), sep=separador, dtype=str, nrows=maximo_de_linhas + 1
            )
        }
    else:
        _conferir_tamanho_descomprimido(conteudo, planilha)
        try:
            abas = pd.read_excel(
                BytesIO(conteudo),
                sheet_name=None,
                dtype=object,
                nrows=maximo_de_linhas + 1,
            )
        except Exception as erro:  # arquivo corrompido ou que não é Excel
            raise ArquivoDaB3Error(_arquivo_invalido(planilha)) from erro
    _conferir_linhas(abas, planilha, maximo_de_linhas)
    return abas


def ler_carteira(conteudo: bytes, nome_do_arquivo: str) -> CarteiraB3:
    """Lê a planilha de posição da B3 e devolve as posições somadas por ativo."""
    com_cotacao, sem_cotacao, avisos = [], [], []
    for nome_da_aba, tabela in ler_abas(conteudo, nome_do_arquivo).items():
        if tabela is None or tabela.empty:
            continue
        colunas = {sem_acento(c): c for c in tabela.columns}
        tipo = _tipo_da_aba(nome_da_aba) or "Ações"
        c_codigo = achar_coluna(colunas, COLUNAS_DO_CODIGO)
        c_produto = achar_coluna(colunas, COLUNAS_DO_PRODUTO)
        c_qtd = achar_coluna(colunas, COLUNAS_DA_QUANTIDADE)
        c_valor = achar_coluna(colunas, COLUNAS_DO_VALOR)
        if c_valor is None:
            if _tipo_da_aba(nome_da_aba) is not None:
                avisos.append(
                    f"A aba {nome_da_aba} não tem a coluna de valor; ficou de fora."
                )
            continue
        for _, linha in tabela.iterrows():
            valor = numero_brasileiro(linha[c_valor])
            if valor <= 0 or e_linha_de_total(linha):
                continue  # linhas de total (contariam o dinheiro duas vezes), vazias ou zeradas
            if tipo in SEM_COTACAO:
                produto = str(linha[c_produto]) if c_produto else tipo
                sem_cotacao.append({"tipo": tipo, "produto": produto, "valor": valor})
                continue
            codigo = str(linha[c_codigo]).strip().upper() if c_codigo else ""
            if not PADRAO_DO_CODIGO.fullmatch(codigo):
                achado = PADRAO_DO_CODIGO.search(
                    str(linha[c_produto]) if c_produto else ""
                )
                codigo = achado.group(1) if achado else ""
            if not codigo:
                produto = str(linha[c_produto]) if c_produto else "sem nome"
                avisos.append(
                    f"Uma linha da aba {nome_da_aba} ({produto[:40]}) não tem código de "
                    "negociação; entrou só na composição, sem histórico de preço."
                )
                sem_cotacao.append({"tipo": tipo, "produto": produto, "valor": valor})
                continue
            quantidade = numero_brasileiro(linha[c_qtd]) if c_qtd else 0.0
            com_cotacao.append(
                {
                    "codigo": codigo,
                    "tipo": tipo,
                    "quantidade": quantidade,
                    "valor": valor,
                }
            )
    if not com_cotacao and not sem_cotacao:
        raise ArquivoDaB3Error(
            "Não achei nenhuma posição no arquivo. Ele precisa ser a planilha de POSIÇÃO da Área "
            "do Investidor, com as colunas Código de Negociação, Quantidade e Valor Atualizado."
        )
    posicoes = pd.DataFrame(
        com_cotacao, columns=["codigo", "tipo", "quantidade", "valor"]
    )
    posicoes = (
        posicoes.groupby(["codigo", "tipo"], as_index=False)[["quantidade", "valor"]]
        .sum()  # o mesmo ativo em mais de uma corretora
        .sort_values("valor", ascending=False, ignore_index=True)
    )
    posicoes.insert(1, "ticker", posicoes["codigo"] + ".SA")
    fixa = pd.DataFrame(sem_cotacao, columns=["tipo", "produto", "valor"])
    return CarteiraB3(posicoes, fixa, avisos)


def numero_efetivo_de_ativos(pesos: pd.Series) -> float:
    """1 ÷ soma dos pesos ao quadrado: quantos ativos IGUAIS dariam a mesma concentração.

    Dez ativos com 10% cada dão 10; um ativo com 90% e nove com 1,1% dão ~1,2.
    """
    return float(1 / (pesos**2).sum()) if len(pesos) else 0.0


def retorno_com_os_pesos_de_hoje(
    fechamentos: pd.DataFrame, pesos: pd.Series
) -> pd.Series:
    """Retorno diário da carteira de HOJE mantida com os mesmos pesos no passado.

    Não é o resultado real de quem investiu (as compras foram em outras datas e preços): mostra
    como esta composição teria se comportado. Ativos sem histórico no período ficam de fora e o
    peso deles é dividido entre os outros.
    """
    disponiveis = [t for t in pesos.index if t in fechamentos.columns]
    if not disponiveis:
        raise ValueError("Nenhum ativo da carteira tem histórico de preço no período.")
    retornos = fechamentos[disponiveis].pct_change().dropna(how="all").fillna(0.0)
    p = pesos[disponiveis] / pesos[disponiveis].sum()
    return retornos @ p
