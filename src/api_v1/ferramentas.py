"""A rota pública da ferramenta "Quanto daria? Foi sorte?" do site (ADR 0070).

`GET /v1/ferramentas/quanto-daria?desde=AAAA-MM-DD&valor=1000`, **sem login**:

- Só **números soltos** por ativo (valor final, retorno, valor em poder de compra e o resumo das
  janelas): nenhuma lista de números, nunca a série (há teste que percorre o esquema).
- **Limite por IP** (o da Cloudflare), como o do link compartilhado: 30 pedidos por minuto.
- **Cache do dia:** a mesma data (o mesmo mês) no mesmo dia não recalcula; o valor só multiplica.
- **CORS só para `https://tickerlab.com.br`** (a página do site chama daqui, de outro domínio).
- **Desligável sem deploy:** `TICKERLAB_PONTE_COM_YAHOO=0` no `.env` tira o Ibovespa e o bitcoin
  (ADR 0070, item 5).
- A data vale pelo mês dela; de pelo menos 30 dias atrás; valor de R$ 1 a R$ 10 milhões.

Fora do `rotas.py` (e do contrato `openapi-v1.json`) de propósito, como o link compartilhado: as
rotas de lá exigem conta e servem ao app; esta serve ao site aberto.
"""

import os
import threading
from datetime import date, datetime
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from src.api_v1.acesso import LimiteDePedidos, agora, exigir_api_ligada
from src.api_v1.compartilhados import ip_de_quem_pede
from src.bcb import FUSO
from src.ferramentas import ponte, ponte_dados

PEDIDOS_POR_MINUTO_POR_IP = 30
ORIGEM_DO_SITE = "https://tickerlab.com.br"
VARIAVEL_DO_YAHOO = "TICKERLAB_PONTE_COM_YAHOO"
# o navegador e a Cloudflare podem guardar a resposta por 1 hora
SEGUNDOS_DE_CACHE = 3600
FONTE_FORA_DO_AR = "Fonte fora do ar agora."
AVISO = (
    "Simulação com dados do passado: não é recomendação de investimento nem promessa de "
    "resultado. Antes de imposto e taxas. As janelas se sobrepõem: não são sorteios independentes."
)

LIMITE_POR_IP = LimiteDePedidos(PEDIDOS_POR_MINUTO_POR_IP)
CALCULADOS: dict[
    tuple[str, date], tuple[list[ponte.ResultadoDoAtivo], list["IndisponivelV1"]]
] = {}
_TRAVA = threading.Lock()


def hoje() -> date:
    return datetime.now(FUSO).date()


def ponte_com_yahoo() -> bool:
    return os.environ.get(VARIAVEL_DO_YAHOO, "1") != "0"


def _cors(request: Request) -> dict[str, str]:
    """Os cabeçalhos de CORS (só para o site), também nos erros: sem eles, o navegador bloqueia a
    resposta e a página não consegue mostrar a mensagem (só vê "falhou")."""
    cabecalhos = {"Vary": "Origin"}
    if request.headers.get("origin") == ORIGEM_DO_SITE:
        cabecalhos["Access-Control-Allow-Origin"] = ORIGEM_DO_SITE
    return cabecalhos


def _recusa(request: Request, status: int, detalhe: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detalhe, headers=_cors(request))


def conferir_o_pedido(request: Request) -> None:
    if not LIMITE_POR_IP.permitir(f"ip:{ip_de_quem_pede(request)}", agora()):
        raise _recusa(request, 429, "Muitos pedidos: espere um minuto.")


router = APIRouter(
    prefix="/v1/ferramentas",
    dependencies=[Depends(exigir_api_ligada), Depends(conferir_o_pedido)],
)


class JanelasV1(BaseModel):
    quantas: int
    pior: float
    mediana: float
    melhor: float
    abaixo_da_sua: float  # fração das janelas que dariam menos que a data escolhida


class AtivoV1(BaseModel):
    ativo: str
    nome: str
    fonte: str
    inicio: date
    fim: date
    valor_final: float
    retorno: float
    valor_real: float  # em poder de compra do mês inicial (descontado o IPCA)
    janelas: JanelasV1 | None


class IndisponivelV1(BaseModel):
    nome: str
    motivo: str


class QuantoDariaV1(BaseModel):
    desde: date  # o 1º dia do mês pedido
    valor: float
    ativos: list[AtivoV1]
    indisponiveis: list[IndisponivelV1]
    aviso: str
    calculado_em: date


Curva = pd.Series | ponte_dados.CurvaIndisponivelError


def _curvas(dia: date) -> tuple[dict, dict[str, Curva]]:
    """O arquivo de dados e as curvas de cada ativo (ou o erro de cada um)."""
    arquivo = ponte_dados.obter_arquivo(dia)
    curvas: dict[str, Curva] = dict(ponte_dados.curvas_do_banco_central(arquivo))
    dolar = curvas.get("dolar")
    if not isinstance(dolar, pd.Series):
        # o arquivo ainda sem o dólar mês a mês: ele e o bitcoin ficam de fora, o resto segue
        dolar = ponte_dados.CurvaIndisponivelError("Ainda sem o dólar mês a mês.")
        curvas["dolar"] = dolar
    if ponte_com_yahoo():
        for ativo in ponte.ATIVOS_DO_YAHOO:
            if ativo == "bitcoin" and not isinstance(dolar, pd.Series):
                curvas[ativo] = dolar
                continue
            try:
                curvas[ativo] = ponte_dados.obter_curva_do_yahoo(
                    ativo,
                    dia,
                    dolar if isinstance(dolar, pd.Series) else pd.Series(dtype=float),
                )
            except ponte_dados.CurvaIndisponivelError as erro:
                curvas[ativo] = erro
    return arquivo, curvas


def _calcular(
    desde: date, dia: date
) -> tuple[list[ponte.ResultadoDoAtivo], list[IndisponivelV1]]:
    """Os resultados para R$ 1 (o valor só multiplica) e os ativos que ficaram de fora."""
    arquivo, curvas = _curvas(dia)
    fator = ponte_dados.fator_do_ipca(desde, arquivo["ipca"]["meses"])
    resultados: list[ponte.ResultadoDoAtivo] = []
    fora: list[IndisponivelV1] = []
    for ativo in ponte.ATIVOS:
        curva = curvas.get(ativo)
        if curva is None:
            continue  # desligado pelo .env
        if isinstance(curva, ponte_dados.CurvaIndisponivelError):
            fora.append(
                IndisponivelV1(nome=ponte.NOMES[ativo], motivo=FONTE_FORA_DO_AR)
            )
            continue
        try:
            resultados.append(ponte.resultado_do_ativo(ativo, curva, desde, 1.0, fator))
        except ValueError as erro:
            fora.append(IndisponivelV1(nome=ponte.NOMES[ativo], motivo=str(erro)))
    return resultados, fora


def _do_cache(
    desde: date, dia: date
) -> tuple[list[ponte.ResultadoDoAtivo], list[IndisponivelV1]]:
    chave = (f"{desde:%Y-%m}", dia)
    with _TRAVA:
        if chave in CALCULADOS:
            return CALCULADOS[chave]
        # dias anteriores não servem mais
        for velha in [c for c in CALCULADOS if c[1] != dia]:
            del CALCULADOS[velha]
    calculado = _calcular(desde, dia)
    # uma fonte fora do ar agora não fica guardada até amanhã: o próximo pedido tenta de novo
    if not any(i.motivo == FONTE_FORA_DO_AR for i in calculado[1]):
        with _TRAVA:
            CALCULADOS[chave] = calculado
    return calculado


def _ativo_v1(r: ponte.ResultadoDoAtivo, valor: float) -> AtivoV1:
    j = r.janelas
    return AtivoV1(
        ativo=r.ativo,
        nome=r.nome,
        fonte=r.fonte,
        inicio=r.inicio,
        fim=r.fim,
        valor_final=r.valor_final * valor,
        retorno=r.retorno,
        valor_real=r.valor_real * valor,
        janelas=None
        if j is None
        else JanelasV1(
            quantas=j.quantas,
            pior=j.pior * valor,
            mediana=j.mediana * valor,
            melhor=j.melhor * valor,
            abaixo_da_sua=j.abaixo_da_sua,
        ),
    )


def _ler_pedido(request: Request, desde: str, valor: str) -> tuple[date, float]:
    try:
        data = date.fromisoformat(desde)
        quantia = float(valor)
    except ValueError as erro:
        raise _recusa(
            request, 422, "Use a data como AAAA-MM-DD e o valor em números."
        ) from erro
    try:
        ponte.conferir_pedido(data, quantia, hoje())
    except ValueError as erro:
        raise _recusa(request, 422, str(erro)) from erro
    return data, quantia


@router.get("/quanto-daria", response_model=QuantoDariaV1)
def quanto_daria(
    request: Request,
    response: Response,
    desde: Annotated[str, Query(max_length=10)],
    valor: Annotated[str, Query(max_length=20)] = "1000",
) -> QuantoDariaV1:
    dia = hoje()
    data, quantia = _ler_pedido(request, desde, valor)
    mes = data.replace(day=1)  # a data vale pelo mês dela
    try:
        resultados, fora = _do_cache(mes, dia)
    except ponte_dados.CurvaIndisponivelError as erro:
        raise _recusa(
            request, 503, "Os dados das ferramentas estão indisponíveis agora."
        ) from erro
    response.headers.update(_cors(request))
    response.headers["Cache-Control"] = f"public, max-age={SEGUNDOS_DE_CACHE}"
    return QuantoDariaV1(
        desde=mes,
        valor=quantia,
        ativos=[_ativo_v1(r, quantia) for r in resultados],
        indisponiveis=fora,
        aviso=AVISO,
        calculado_em=dia,
    )
