"""Preços mensais de referência de commodities: Pink Sheet do Banco Mundial e FMI (PCPS).

São preços **mensais** e grátis (a média do mês), para o café (arábica e robusta), os
fertilizantes (ureia, cloreto de potássio, DAP) e alguns grãos e fibras. O preço diário de bolsa
(ICE, B3, CEPEA, ICO) é pago e não entra aqui (ADR 0094, Emenda 1).

As duas fontes entram no acervo de séries (ADR 0024, "como era na data") como `bm-pink-<item>` e
`fmi-<item>`, na mesma unidade (US$ por kg ou por tonelada). Ambas ficam `uso_interno`: o Pink
Sheet é CC BY 4.0, mas cita fontes de terceiros (Bloomberg, S&P Global, ICO) que não podem ser
repassadas sem o consentimento delas, e o FMI pede autorização para uso comercial
(licencas-por-fonte.md do autor, lido em 18/10/2026).

Fica sem Streamlit: entradas e saídas em tipos simples.
"""

import io
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import openpyxl
import pandas as pd
import requests
import sqlalchemy as sa

from base.arquivo.cliente_http import AGENTE
from src.banco.series import SerieDoAcervo, garantir_serie, gravar

log = logging.getLogger(__name__)

URL_DA_PAGINA_DO_PINK = "https://www.worldbank.org/en/research/commodity-markets"
URL_DO_FMI = "https://api.imf.org/external/sdmx/2.1/data/PCPS/G001.{indicadores}.USD.M"
CABECALHO_CSV_DO_FMI = "application/vnd.sdmx.data+csv;version=1.0.0"
TEMPO_LIMITE = 60
USER_AGENT = {"User-Agent": AGENTE}

ABA_MENSAL = "Monthly Prices"
LINHA_DOS_NOMES = 5  # na aba mensal: nomes na linha 5 e unidades na 6 (a contar de 1)
LINHA_DAS_UNIDADES = 6
LIBRA_EM_KG = (
    0.45359237  # o FMI dá café, açúcar e algodão em centavos de dólar por libra-peso
)
CENTAVOS_POR_LIBRA_EM_DOLARES_POR_KG = 1 / (100 * LIBRA_EM_KG)
FAMILIA_BM = "bm-pink"
FAMILIA_FMI = "fmi-pcps"
# o Pink Sheet sai nos primeiros dias úteis do mês e o FMI perto do dia 10 (janela de coleta)
SERIE_TESTEMUNHA = {FAMILIA_BM: "bm-pink-cafe-arabica", FAMILIA_FMI: "fmi-cafe-arabica"}
JANELA_DE_COLETA = {FAMILIA_BM: range(2, 8), FAMILIA_FMI: range(8, 15)}


class PrecosIndisponiveisError(Exception):
    """A fonte não respondeu ou a resposta não é a esperada."""


@dataclass(frozen=True)
class ItemDeReferencia:
    chave: str  # "cafe-arabica": vira o fim do id da série
    nome: str
    unidade: str  # a do catálogo: "US$/kg" ou "US$/t"
    nome_no_pink: str  # cabeçalho da planilha, sem os asteriscos de nota
    unidade_no_pink: str  # a que a planilha traz; se mudar, o item é ignorado com aviso
    codigo_no_fmi: str
    fator_do_fmi: float  # FMI → unidade do catálogo


_CENTAVOS_LIBRA = CENTAVOS_POR_LIBRA_EM_DOLARES_POR_KG
ITENS = (
    ItemDeReferencia("cafe-arabica", "Café arábica (indicador ICO, outros suaves)", "US$/kg", "Coffee, Arabica", "($/kg)", "PCOFFOTM", _CENTAVOS_LIBRA),
    ItemDeReferencia("cafe-robusta", "Café robusta (indicador ICO)", "US$/kg", "Coffee, Robusta", "($/kg)", "PCOFFROB", _CENTAVOS_LIBRA),
    ItemDeReferencia("ureia", "Ureia", "US$/t", "Urea", "($/mt)", "PUREA", 1.0),
    ItemDeReferencia("cloreto-de-potassio", "Cloreto de potássio", "US$/t", "Potassium chloride", "($/mt)", "PPOTASH", 1.0),
    ItemDeReferencia("dap", "Fosfato diamônico (DAP)", "US$/t", "DAP", "($/mt)", "PDAP", 1.0),
    ItemDeReferencia("soja", "Soja", "US$/t", "Soybeans", "($/mt)", "PSOYB", 1.0),
    ItemDeReferencia("milho", "Milho", "US$/t", "Maize", "($/mt)", "PMAIZMT", 1.0),
    ItemDeReferencia("acucar", "Açúcar (mercado mundial)", "US$/kg", "Sugar, world", "($/kg)", "PSUGAISA", _CENTAVOS_LIBRA),
    ItemDeReferencia("algodao", "Algodão (Índice A)", "US$/kg", "Cotton, A Index", "($/kg)", "PCOTTIND", _CENTAVOS_LIBRA),
)  # fmt: skip
# Onde as duas fontes medem o mesmo indicador (ICO e Índice A), valem a conferência de 1%. Nos
# demais o FMI usa outro mercado ou outra especificação (ureia, DAP e potássio chegam a divergir
# mais de 10%): ele só complementa, não confere.
COMPARAVEIS = ("cafe-arabica", "cafe-robusta", "algodao")

_ITEM_PELA_CHAVE = {item.chave: item for item in ITENS}
_ITEM_PELO_NOME_NO_PINK = {item.nome_no_pink: item for item in ITENS}
_ITEM_PELO_CODIGO_DO_FMI = {item.codigo_no_fmi: item for item in ITENS}
_MES_DO_PINK = re.compile(r"^(\d{4})M(\d{2})$")
_MES_DO_FMI = re.compile(r"^(\d{4})-M(\d{2})$")
_ENDERECO_DO_PINK = re.compile(
    r"https://thedocs\.worldbank\.org/[^\"'\s<>]*CMO-Historical-Data-Monthly\.xlsx"
)


@dataclass(frozen=True)
class ValorMensal:
    id: str  # "bm-pink-cafe-arabica"
    mes: date  # sempre o dia 1
    valor: float | None  # None: a fonte não tem o valor (célula vazia), nunca zero


def serie_do_acervo(codigo: str) -> SerieDoAcervo:
    """A série do acervo de `bm-pink-<item>` ou `fmi-<item>` (sempre só uso interno)."""
    familia = "bm-pink" if codigo.startswith("bm-pink-") else "fmi"
    chave = codigo.removeprefix(f"{familia}-")
    item = _ITEM_PELA_CHAVE[chave]
    fonte = "Pink Sheet do Banco Mundial" if familia == "bm-pink" else "FMI (PCPS)"
    return SerieDoAcervo(
        codigo,
        f"{item.nome} ({fonte}, média mensal)",
        item.unidade,
        "mensal",
        uso_interno=True,
    )


def _numero(celula: object) -> float | None:
    """O número da célula; vazio, ".." ou texto viram None."""
    if isinstance(celula, bool) or not isinstance(celula, (int, float)):
        return None
    return float(celula) if pd.notna(celula) else None


def ler_pink_sheet(conteudo: bytes) -> list[ValorMensal]:
    """Os itens de `ITENS` da aba mensal do Pink Sheet (XLSX), um valor por mês.

    Item que sumiu da planilha, ou cuja unidade mudou, é ignorado com aviso: melhor faltar o dado
    do que guardar um número na unidade errada."""
    pasta = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    try:
        linhas = list(pasta[ABA_MENSAL].iter_rows(values_only=True))
    except KeyError as erro:
        raise PrecosIndisponiveisError("O Pink Sheet veio sem a aba mensal.") from erro
    finally:
        pasta.close()
    nomes, unidades = linhas[LINHA_DOS_NOMES - 1], linhas[LINHA_DAS_UNIDADES - 1]
    colunas: dict[int, ItemDeReferencia] = {}
    for posicao, nome in enumerate(nomes):
        item = _ITEM_PELO_NOME_NO_PINK.get(str(nome or "").replace("*", "").strip())
        if item is None:
            continue
        if str(unidades[posicao]).strip() != item.unidade_no_pink:
            log.warning(
                "Pink Sheet: a unidade de %s mudou para %s; item ignorado.",
                item.nome_no_pink,
                unidades[posicao],
            )
            continue
        colunas[posicao] = item
    for item in ITENS:
        if item not in colunas.values():
            log.warning("Pink Sheet: sem %s nesta planilha.", item.nome_no_pink)
    valores = []
    for linha in linhas[LINHA_DAS_UNIDADES:]:
        mes = _MES_DO_PINK.match(str(linha[0] or ""))
        if not mes:
            continue
        dia = date(int(mes[1]), int(mes[2]), 1)
        valores += [
            ValorMensal(f"bm-pink-{item.chave}", dia, _numero(linha[posicao]))
            for posicao, item in colunas.items()
        ]
    return valores


def ler_fmi(conteudo: bytes) -> list[ValorMensal]:
    """Os valores mensais, em dólares, do CSV do FMI (SDMX), na unidade do catálogo.

    Linhas de metadados, índices, variações e trimestres são ignoradas; um indicador que não está
    em `ITENS` é ignorado com aviso."""
    tabela = pd.read_csv(io.BytesIO(conteudo), dtype=str, keep_default_na=False)
    tabela = tabela[
        (tabela["DATA_TRANSFORMATION"] == "USD") & (tabela["FREQUENCY"] == "M")
    ]
    desconhecidos: set[str] = set()
    valores = []
    for indicador, periodo, observacao in zip(
        tabela["INDICATOR"], tabela["TIME_PERIOD"], tabela["OBS_VALUE"], strict=True
    ):
        item = _ITEM_PELO_CODIGO_DO_FMI.get(indicador)
        mes = _MES_DO_FMI.match(periodo)
        if item is None:
            desconhecidos.add(indicador)
        elif mes:
            numero = pd.to_numeric(observacao, errors="coerce")
            valor = None if pd.isna(numero) else float(numero) * item.fator_do_fmi
            valores.append(
                ValorMensal(
                    f"fmi-{item.chave}", date(int(mes[1]), int(mes[2]), 1), valor
                )
            )
    for indicador in sorted(desconhecidos):
        log.warning("FMI: indicador %s fora da lista; ignorado.", indicador)
    return valores


def gravar_precos(
    conexao: sa.Connection, valores: list[ValorMensal], divulgado_em: date
) -> int:
    """Guarda os valores no acervo na safra `divulgado_em` (cadastra a série se for nova).
    Devolve quantas linhas entraram; valor igual ao já conhecido não grava nada, valor revisto vira
    safra nova sem apagar a anterior, e vazio (None) não é gravado."""
    por_serie: dict[str, dict[date, float]] = {}
    for v in valores:
        por_serie.setdefault(v.id, {})
        if v.valor is not None:
            por_serie[v.id][v.mes] = v.valor
    novas = 0
    for codigo, meses in por_serie.items():
        garantir_serie(conexao, serie_do_acervo(codigo))
        novas += gravar(conexao, codigo, pd.Series(meses, dtype=float), divulgado_em)
    return novas


def achar_endereco_do_pink(html: str) -> str:
    """O link do XLSX mensal na página do Banco Mundial (o endereço muda a cada edição)."""
    achado = _ENDERECO_DO_PINK.search(html)
    if achado is None:
        raise PrecosIndisponiveisError(
            "Não achei o Pink Sheet na página do Banco Mundial."
        )
    return achado.group(0)


def _pedir(
    buscar: Callable[..., requests.Response], url: str, **extra: object
) -> requests.Response:
    try:
        resposta = buscar(url, timeout=TEMPO_LIMITE, **extra)
        resposta.raise_for_status()
    except requests.RequestException as erro:
        log.warning("Falha ao consultar %s: %s", url, erro)
        raise PrecosIndisponiveisError(f"Não consegui consultar {url} agora.") from erro
    return resposta


def baixar_pink_sheet(buscar: Callable[..., requests.Response] = requests.get) -> bytes:
    pagina = _pedir(buscar, URL_DA_PAGINA_DO_PINK, headers=USER_AGENT)
    return _pedir(
        buscar, achar_endereco_do_pink(pagina.text), headers=USER_AGENT
    ).content


def baixar_fmi(
    desde: date, buscar: Callable[..., requests.Response] = requests.get
) -> bytes:
    """O CSV do FMI com os itens de `ITENS`, de `desde` até o último mês publicado."""
    indicadores = "+".join(item.codigo_no_fmi for item in ITENS)
    return _pedir(
        buscar,
        URL_DO_FMI.format(indicadores=indicadores),
        params={"startPeriod": desde.strftime("%Y-%m")},
        headers={**USER_AGENT, "Accept": CABECALHO_CSV_DO_FMI},
    ).content


def deve_coletar(familia: str, hoje: date, tem_dados: bool) -> bool:
    """Coleta mensal: sem dados ainda, hoje mesmo; depois, só na janela em que a fonte publica."""
    return not tem_dados or hoje.day in JANELA_DE_COLETA[familia]
