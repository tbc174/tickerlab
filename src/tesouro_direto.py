"""As taxas de hoje do Tesouro Direto, para as ferramentas do site (renda fixa).

Fonte: "Taxas dos Títulos Ofertados pelo Tesouro Direto", do Tesouro Transparente (Tesouro
Nacional; licença ODbL: pode, citando a fonte). O arquivo tem o histórico inteiro desde 2002, com os
dias mais novos primeiro; por isso basta pedir o começo dele (`Range`), em vez de baixar tudo todo
dia. Se um dia o Tesouro mudar a ordem, o começo traria dias velhos e a leitura falha (o Kuma avisa)
em vez de mostrar uma taxa antiga como se fosse de hoje.

Só os títulos sem cupom e à venda (taxa de compra maior que zero): Prefixado, IPCA+ e Selic. A taxa
é a de compra da manhã, como no site do Tesouro Direto.
"""

import csv
import io
from collections.abc import Callable
from datetime import date, timedelta

import requests

from src import rede

URL_DAS_TAXAS = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/"
    "resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv"
)
FONTE = "Tesouro Nacional (Tesouro Transparente, taxas do Tesouro Direto; licença ODbL)"
BYTES_DO_COMECO = (
    65_536  # ~30 dias de taxas: o arquivo vem do dia mais novo para o mais velho
)
TITULOS = ("Tesouro Prefixado", "Tesouro IPCA+", "Tesouro Selic")
DIAS_ATE_FICAR_VELHO = (
    15  # feriado prolongado cabe; mais que isso, algo mudou no arquivo
)
TEMPO_LIMITE = 30


class TesouroIndisponivelError(Exception):
    """O arquivo do Tesouro não veio, ou veio diferente do esperado."""


def _numero(texto: str) -> float:
    return float(texto.replace(".", "").replace(",", "."))


def _dia(texto: str) -> date:
    """Lê "13/10/2026" como date(2026, 10, 13): só a data, sem hora nem fuso."""
    dia, mes, ano = texto.split("/")
    return date(int(ano), int(mes), int(dia))


def ler_taxas_do_dia(conteudo: bytes) -> dict:
    """Do começo do arquivo, as taxas do dia mais novo: {"data", "titulos": [{titulo, vencimento,
    taxa}]}, com a taxa em fração (0,1385 = 13,85% ao ano) e em ordem de título e vencimento."""
    texto = conteudo.decode("latin-1")
    if not texto.endswith("\n"):
        texto = texto[: texto.rfind("\n") + 1]  # o Range corta a última linha no meio
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=";"))
    try:
        mais_novo = max(_dia(linha["Data Base"]) for linha in linhas)
        titulos = [
            {
                "titulo": linha["Tipo Titulo"],
                "vencimento": _dia(linha["Data Vencimento"]).isoformat(),
                "taxa": _numero(linha["Taxa Compra Manha"]) / 100,
            }
            for linha in linhas
            if _dia(linha["Data Base"]) == mais_novo
            and linha["Tipo Titulo"] in TITULOS
            and _numero(linha["Taxa Compra Manha"]) > 0
        ]
    except (KeyError, ValueError) as erro:
        raise TesouroIndisponivelError(
            "Arquivo do Tesouro diferente do esperado."
        ) from erro
    if not titulos:
        raise TesouroIndisponivelError(
            "Nenhum título à venda no dia mais novo do arquivo."
        )
    titulos.sort(key=lambda t: (t["titulo"], t["vencimento"]))
    return {"data": mais_novo.isoformat(), "titulos": titulos}


Buscar = Callable[..., requests.Response]


def baixar_taxas_do_dia(hoje: date, buscar: Buscar = rede.get_com_agente) -> dict:
    """As taxas do dia mais novo, pedindo só o começo do arquivo; erro se o dia for velho demais."""
    try:
        resposta = buscar(
            URL_DAS_TAXAS,
            headers={"Range": f"bytes=0-{BYTES_DO_COMECO - 1}"},
            timeout=TEMPO_LIMITE,
        )
    except requests.RequestException as erro:
        raise TesouroIndisponivelError(
            "Não consegui consultar o Tesouro agora."
        ) from erro
    if resposta.status_code not in (
        200,
        206,
    ):  # 200: o servidor ignorou o Range e mandou tudo
        raise TesouroIndisponivelError(f"O Tesouro respondeu {resposta.status_code}.")
    taxas = ler_taxas_do_dia(resposta.content)
    if date.fromisoformat(taxas["data"]) < hoje - timedelta(days=DIAS_ATE_FICAR_VELHO):
        raise TesouroIndisponivelError(
            f"O dia mais novo do arquivo ({taxas['data']}) está velho demais: a ordem mudou?"
        )
    return taxas
