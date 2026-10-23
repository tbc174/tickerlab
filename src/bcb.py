"""Dados do Banco Central: séries do SGS, dólar PTAX e expectativas do Focus.

Primeira parte da proposta de dados novos (macro do Brasil). Aqui só se **busca e lê**: guardar
com histórico de versões é outro passo (o desenho do armazenamento ainda vai ser feito).

Fontes, todas públicas e sem login (dados abertos do Banco Central; citar a fonte):

- **SGS** (Sistema Gerenciador de Séries Temporais): `api.bcb.gov.br/dados/serie/bcdata.sgs.N`;
- **PTAX** (dólar oficial do dia) e **Focus** (expectativas do mercado): API Olinda,
  `olinda.bcb.gov.br`.

Sem olhar o futuro: algumas séries trazem datas à frente (a meta da Selic é repetida até a
próxima reunião do Copom). Tudo depois de `hoje` é cortado.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from src import rede

URL_DO_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
URL_DA_PTAX = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)
URL_DA_PTAX_DA_MOEDA = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)
URL_DAS_MOEDAS = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/Moedas"
BOLETIM_DE_FECHAMENTO = "Fechamento"  # a PTAX do dia; os outros boletins são parciais
URL_DO_FOCUS = (
    "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
    "ExpectativasMercadoAnuais"
)
# o SGS aceita até 10 anos por consulta, mas sem cache uma janela longa passa dos ~30 s do
# servidor do BC, que devolve uma página "Requisição inválida!" com status 200 (13/10/2026).
# Com 3 anos isso fica raro, mas ainda acontece com o cache frio: a página conta como passageira
ANOS_POR_CONSULTA = 3
TEMPO_LIMITE = 60  # segundos: sem cache, o SGS leva até ~30 s numa janela de 9 anos
# um 502, um timeout ou a página de erro do BC somem em segundos (13/10/2026): tenta mais 2 vezes
ESPERAS_ENTRE_TENTATIVAS = (5, 15)  # segundos
HTTP_ERRO_DO_SERVIDOR = 500
esperar = time.sleep  # os testes trocam
FUSO = ZoneInfo("America/Sao_Paulo")  # "hoje" é o do Brasil, não o do servidor (UTC)

log = logging.getLogger(__name__)

Buscar = Callable[..., requests.Response]


@dataclass(frozen=True)
class Serie:
    codigo: int
    nome: str
    unidade: str


# conferidas na API em 12/10/2026
SERIES = {
    "selic_meta": Serie(432, "Meta da Selic", "% ao ano"),
    "selic_diaria": Serie(11, "Selic diária", "% ao dia"),
    "ipca": Serie(433, "IPCA (variação no mês)", "% no mês"),
    "igpm": Serie(189, "IGP-M (variação no mês)", "% no mês"),
    "ibc_br": Serie(24363, "IBC-Br (prévia do PIB)", "índice"),
    "dolar": Serie(1, "Dólar comercial (venda)", "R$ por US$"),
    "euro": Serie(21619, "Euro (venda)", "R$ por €"),
    # IC-Br (índice de commodities do BC, em reais, mensal): conferidos na API em 18/10/2026 pelas
    # variações de novembro de 2024 divulgadas pelo BC (geral +3,90%; agropecuária +5,46%)
    "icbr": Serie(27574, "IC-Br (índice de commodities, geral)", "índice"),
    "icbr_agro": Serie(27575, "IC-Br agropecuária", "índice"),
}

COLUNAS_DO_FOCUS = {
    "Indicador": "indicador",
    "Data": "data",
    "DataReferencia": "ano",
    "Mediana": "mediana",
    "Media": "media",
    "Minimo": "minimo",
    "Maximo": "maximo",
    "numeroRespondentes": "respondentes",
}


class BcbIndisponivelError(Exception):
    """O Banco Central não respondeu ou respondeu algo inesperado."""


def _passageiro(erro: Exception) -> bool:
    """Erro que costuma sumir sozinho: o BC demorou, caiu a conexão ou respondeu 5xx.

    Resposta que não é JSON também: é a página "Requisição inválida!" que o servidor do BC devolve,
    com status 200, quando a consulta passa do tempo dele; repetida, já vem do cache.
    """
    if isinstance(erro, (requests.Timeout, requests.ConnectionError, ValueError)):
        return True
    resposta = getattr(erro, "response", None)
    return (
        isinstance(erro, requests.HTTPError)
        and resposta is not None
        and (resposta.status_code >= HTTP_ERRO_DO_SERVIDOR)
    )


def _pedir(buscar: Buscar, url: str, params: dict | None) -> object:
    for tentativa, espera in enumerate([*ESPERAS_ENTRE_TENTATIVAS, None], start=1):
        try:
            resposta = buscar(url, params=params, timeout=TEMPO_LIMITE)
            resposta.raise_for_status()
            return resposta.json()
        except (requests.RequestException, ValueError) as erro:
            log.warning(
                "Falha ao consultar o Banco Central (tentativa %s): %s", tentativa, erro
            )
            if espera is None or not _passageiro(erro):
                raise BcbIndisponivelError(
                    "Não consegui consultar o Banco Central agora."
                ) from erro
            esperar(espera)
    raise AssertionError("inalcançável")  # o laço sempre devolve ou levanta


def _hoje() -> date:
    return datetime.now(FUSO).date()


def _cortar_futuro(serie: pd.Series, hoje: date) -> pd.Series:
    return serie[serie.index <= pd.Timestamp(hoje)]


# --- SGS ----------------------------------------------------------------------------------------
def montar_serie_sgs(registros: list[dict], nome: str, hoje: date) -> pd.Series:
    """A resposta do SGS (data dd/mm/aaaa e valor como texto) numa série por data, até `hoje`."""
    if not registros:
        raise BcbIndisponivelError(f"O Banco Central não devolveu dados de {nome}.")
    tabela = pd.DataFrame(registros)
    try:
        datas = pd.to_datetime(tabela["data"], format="%d/%m/%Y")
        valores = pd.to_numeric(tabela["valor"])
    except (KeyError, ValueError) as erro:
        raise BcbIndisponivelError(f"Resposta inesperada do SGS para {nome}.") from erro
    serie = pd.Series(valores.to_numpy(), index=datas, name=nome)
    serie = serie[~serie.index.duplicated(keep="last")].sort_index()
    return _cortar_futuro(serie, hoje)


def baixar_serie_sgs(
    chave: str,
    inicio: date,
    fim: date,
    hoje: date | None = None,
    buscar: Buscar = rede.get_com_agente,
) -> pd.Series:
    """A série `chave` de `SERIES` entre `inicio` e `fim` (ver `baixar_sgs`)."""
    return baixar_sgs(SERIES[chave], inicio, fim, hoje, buscar)


def baixar_sgs(
    serie: Serie,
    inicio: date,
    fim: date,
    hoje: date | None = None,
    buscar: Buscar = rede.get_com_agente,
) -> pd.Series:
    """Uma série do SGS entre `inicio` e `fim`, em consultas de até `ANOS_POR_CONSULTA` anos.

    Serve também para séries fora de `SERIES` (o CDI do backtest), que a coleta do acervo não
    percorre.
    """
    hoje = hoje or _hoje()
    comeco, final = pd.Timestamp(inicio), pd.Timestamp(fim)
    if final < comeco:
        raise ValueError("A data final deve vir depois da inicial.")
    registros: list[dict] = []
    while comeco <= final:
        termino = min(comeco + pd.DateOffset(years=ANOS_POR_CONSULTA), final)
        params = {
            "formato": "json",
            "dataInicial": comeco.strftime("%d/%m/%Y"),
            "dataFinal": termino.strftime("%d/%m/%Y"),
        }
        resposta = _pedir(buscar, URL_DO_SGS.format(codigo=serie.codigo), params)
        if not isinstance(resposta, list):
            raise BcbIndisponivelError(f"Resposta inesperada do SGS para {serie.nome}.")
        registros += resposta
        comeco = termino + pd.Timedelta(days=1)
    return montar_serie_sgs(registros, serie.nome, hoje)


# --- PTAX ---------------------------------------------------------------------------------------
def montar_ptax(resposta: object, hoje: date) -> pd.DataFrame:
    """Compra e venda da PTAX por dia (a cotação de fechamento, a última do dia)."""
    if not isinstance(resposta, dict) or not resposta.get("value"):
        raise BcbIndisponivelError("O Banco Central não devolveu a PTAX deste período.")
    tabela = pd.DataFrame(resposta["value"])
    try:
        momentos = pd.to_datetime(tabela["dataHoraCotacao"])
        ptax = pd.DataFrame(
            {
                "compra": pd.to_numeric(tabela["cotacaoCompra"]).to_numpy(),
                "venda": pd.to_numeric(tabela["cotacaoVenda"]).to_numpy(),
                "momento": momentos.to_numpy(),
            },
            index=momentos.dt.normalize(),
        )
    except (KeyError, ValueError) as erro:
        raise BcbIndisponivelError("Resposta inesperada da PTAX.") from erro
    ptax = ptax.sort_values("momento")
    ptax = ptax[~ptax.index.duplicated(keep="last")].drop(columns="momento")
    return ptax[ptax.index <= pd.Timestamp(hoje)]


def baixar_ptax(
    inicio: date,
    fim: date,
    hoje: date | None = None,
    buscar: Buscar = rede.get_com_agente,
) -> pd.DataFrame:
    """A PTAX do dólar (compra e venda) entre `inicio` e `fim`."""
    params = {
        "@dataInicial": f"'{inicio:%m-%d-%Y}'",
        "@dataFinalCotacao": f"'{fim:%m-%d-%Y}'",
        "$format": "json",
    }
    return montar_ptax(_pedir(buscar, URL_DA_PTAX, params), hoje or _hoje())


@dataclass(frozen=True)
class Moeda:
    codigo: str  # "EUR"
    nome: str  # "Euro"


def montar_moedas(resposta: object) -> list[Moeda]:
    """As moedas que têm PTAX (em 14/10/2026 eram 10, do dólar à coroa sueca)."""
    if not isinstance(resposta, dict) or not resposta.get("value"):
        raise BcbIndisponivelError(
            "O Banco Central não devolveu a lista de moedas da PTAX."
        )
    try:
        return [Moeda(m["simbolo"], m["nomeFormatado"]) for m in resposta["value"]]
    except (KeyError, TypeError) as erro:
        raise BcbIndisponivelError("Resposta inesperada da lista de moedas.") from erro


def baixar_moedas(buscar: Buscar = rede.get_com_agente) -> list[Moeda]:
    """A lista de moedas da PTAX."""
    return montar_moedas(_pedir(buscar, URL_DAS_MOEDAS, {"$format": "json"}))


def montar_ptax_da_moeda(resposta: object, hoje: date) -> pd.DataFrame:
    """Compra e venda (em reais) por dia, só do boletim de fechamento: a PTAX daquele dia."""
    if not isinstance(resposta, dict) or not isinstance(resposta.get("value"), list):
        raise BcbIndisponivelError("Resposta inesperada da PTAX.")
    fechamentos = [
        cotacao
        for cotacao in resposta["value"]
        if cotacao.get("tipoBoletim") == BOLETIM_DE_FECHAMENTO
    ]
    return montar_ptax({"value": fechamentos}, hoje)


def baixar_ptax_da_moeda(
    moeda: str,
    inicio: date,
    fim: date,
    hoje: date | None = None,
    buscar: Buscar = rede.get_com_agente,
) -> pd.DataFrame:
    """A PTAX de `moeda` ("EUR", "GBP"...) entre `inicio` e `fim`, em reais."""
    params = {
        "@moeda": f"'{moeda}'",
        "@dataInicial": f"'{inicio:%m-%d-%Y}'",
        "@dataFinalCotacao": f"'{fim:%m-%d-%Y}'",
        "$format": "json",
    }
    resposta = _pedir(buscar, URL_DA_PTAX_DA_MOEDA, params)
    return montar_ptax_da_moeda(resposta, hoje or _hoje())


# --- Focus --------------------------------------------------------------------------------------
def montar_focus(resposta: object) -> pd.DataFrame:
    """As expectativas anuais do Focus: uma linha por data da pesquisa e ano de referência."""
    if not isinstance(resposta, dict) or "value" not in resposta:
        raise BcbIndisponivelError("Resposta inesperada do Focus.")
    tabela = pd.DataFrame(resposta["value"])
    if tabela.empty:
        return pd.DataFrame(columns=list(COLUNAS_DO_FOCUS.values()))
    try:
        tabela = tabela[list(COLUNAS_DO_FOCUS)].rename(columns=COLUNAS_DO_FOCUS)
        tabela["data"] = pd.to_datetime(tabela["data"])
        tabela["ano"] = pd.to_numeric(tabela["ano"]).astype(int)
    except (KeyError, ValueError) as erro:
        raise BcbIndisponivelError("Resposta inesperada do Focus.") from erro
    return tabela.sort_values(["data", "ano"]).reset_index(drop=True)


def baixar_focus(
    indicador: str,
    desde: date,
    buscar: Buscar = rede.get_com_agente,
    base_de_calculo: int | None = None,
) -> pd.DataFrame:
    """O que o mercado espera para `indicador` ("IPCA", "Selic", "Câmbio", "PIB Total"...)
    em cada ano, nas pesquisas publicadas desde `desde`.

    O Focus publica duas contas por pesquisa: `base_de_calculo` 0 (respostas dos últimos 30 dias,
    a divulgada no boletim) e 1 (só dos últimos 4 dias úteis). None traz as duas."""
    if "'" in indicador:
        raise ValueError("Indicador inválido.")
    filtro = f"Indicador eq '{indicador}' and Data ge '{desde:%Y-%m-%d}'"
    if base_de_calculo is not None:
        filtro += f" and baseCalculo eq {int(base_de_calculo)}"
    params = {
        "$filter": filtro,
        "$orderby": "Data desc",
        "$format": "json",
    }
    # a API Olinda recusa (erro 400) o "+" que o requests põe no lugar dos espaços: só aceita %20
    consulta = urlencode(params, quote_via=quote, safe="$'")
    return montar_focus(_pedir(buscar, f"{URL_DO_FOCUS}?{consulta}", None))
