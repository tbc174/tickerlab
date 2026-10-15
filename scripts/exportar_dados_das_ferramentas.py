"""Grava os dados abertos que as ferramentas do site usam: `ferramentas.json`.

    python -m scripts.exportar_dados_das_ferramentas --destino /caminho/ferramentas.json

Roda no VPS uma vez por dia, depois do fechamento da PTAX (~13h), e o nginx do site serve o arquivo
em `tickerlab.com.br/dados/ferramentas.json`. O navegador faz as contas (conversor, renda fixa,
juro real, correção pela inflação) com esses números.

**Só dados abertos do Banco Central e do Tesouro Nacional** (licença ODbL: pode, citando a fonte).
Preço do Yahoo, da B3 ou de corretora não entra aqui (ADR 0008; a ferramenta "Quanto daria?" usa a
API, só o resultado). Desde as ferramentas v2 (PR 3): o Focus (IPCA e Selic esperados), o CDI e a
poupança mês a mês, os últimos 12 meses da PTAX de cada moeda e as taxas do Tesouro Direto.

Cada parte leva a data a que se refere: se o BC falhar numa parte, fica a do arquivo anterior, com a
data dela (a página avisa quando o dado está velho), e a última linha da saída é `FALHAS: ...` para
o aviso do Kuma (saída 1).
"""

import argparse
import json
import logging
import os
import sys
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from src import bcb, tesouro_direto
from src.cdi import SERIE_DO_CDI

FONTE = (
    "Banco Central do Brasil (dados abertos: PTAX, SGS e Focus) e Tesouro Nacional (Tesouro "
    "Transparente: taxas do Tesouro Direto); licença ODbL"
)
PARTES = (
    "moedas",
    "cdi",
    "selic_meta",
    "poupanca",
    "ipca",
    "focus",
    "cdi_mensal",
    "poupanca_mensal",
    "tesouro",
)
DIAS_PARA_TRAS = 15  # cobre feriados e o fim de semana sem cotação
DIAS_DE_HISTORICO_DA_PTAX = 366  # o gráfico de 12 meses do conversor
INICIO_DO_IPCA = date(1994, 7, 1)  # o Plano Real: antes disso, outra moeda
POUPANCA = bcb.Serie(
    195, "Poupança: rentabilidade no mês (depósitos desde 04/05/2012)", "% no mês"
)
# a regra antiga da poupança (depósitos até 03/05/2012): a série mês a mês usa esta até mai/2012
POUPANCA_ANTIGA = bcb.Serie(
    25, "Poupança: rentabilidade no mês (depósitos até 03/05/2012)", "% no mês"
)
COMECO_DA_REGRA_NOVA = "2012-06"  # o 1º aniversário de dia 1 depois de 04/05/2012
CDI_NO_MES = bcb.Serie(4391, "CDI acumulado no mês", "% no mês")
DIAS_DE_FOCUS = 21  # o Focus sai às segundas: três semanas cobrem um feriado
ANOS_DE_FOCUS = 4  # o ano corrente e os 3 seguintes
INDICADORES_DO_FOCUS = {"ipca": "IPCA", "selic": "Selic"}
DIAS_UTEIS_POR_ANO = 252  # o CDI é ao dia útil
TAMANHO_MAXIMO_DO_RESUMO = 300

log = logging.getLogger(__name__)
Buscar = bcb.Buscar
Coletor = Callable[[date, Buscar], object]


def _dia(momento: object) -> str:
    return str(momento)[:10]


def _ultimo(serie_sgs: bcb.Serie, hoje: date, buscar: Buscar) -> tuple[float, str]:
    serie = bcb.baixar_sgs(
        serie_sgs, hoje - timedelta(days=DIAS_PARA_TRAS), hoje, hoje, buscar
    )
    if serie.empty:
        raise bcb.BcbIndisponivelError(f"Sem dado recente de {serie_sgs.nome}.")
    return float(serie.iloc[-1]), _dia(serie.index[-1])


def _moedas(hoje: date, buscar: Buscar) -> list[dict]:
    """A PTAX de hoje de cada moeda e, para o gráfico do conversor, a de venda dos últimos 12 meses."""
    inicio = hoje - timedelta(days=DIAS_DE_HISTORICO_DA_PTAX)
    linhas = []
    for moeda in bcb.baixar_moedas(buscar):
        ptax = bcb.baixar_ptax_da_moeda(moeda.codigo, inicio, hoje, hoje, buscar)
        linhas.append(
            {
                "codigo": moeda.codigo,
                "nome": moeda.nome,
                "compra": float(ptax["compra"].iloc[-1]),
                "venda": float(ptax["venda"].iloc[-1]),
                "data": _dia(ptax.index[-1]),
                "historico": [
                    [_dia(dia), float(venda)] for dia, venda in ptax["venda"].items()
                ],
            }
        )
    return linhas


def _cdi(hoje: date, buscar: Buscar) -> dict:
    ao_dia, data = _ultimo(SERIE_DO_CDI, hoje, buscar)
    return {"ao_ano": (1 + ao_dia / 100) ** DIAS_UTEIS_POR_ANO - 1, "data": data}


def _selic_meta(hoje: date, buscar: Buscar) -> dict:
    ao_ano, data = _ultimo(bcb.SERIES["selic_meta"], hoje, buscar)
    return {"ao_ano": ao_ano / 100, "data": data}


def _poupanca(hoje: date, buscar: Buscar) -> dict:
    ao_mes, data = _ultimo(POUPANCA, hoje, buscar)
    return {"ao_mes": ao_mes / 100, "data": data}


def _ipca(hoje: date, buscar: Buscar) -> dict:
    serie = bcb.baixar_sgs(bcb.SERIES["ipca"], INICIO_DO_IPCA, hoje, hoje, buscar)
    meses = [
        [f"{momento:%Y-%m}", float(valor) / 100] for momento, valor in serie.items()
    ]
    return {"meses": meses, "ultimo": meses[-1][0]}


def _meses_fechados(serie: pd.Series, hoje: date) -> list[list]:
    """[["AAAA-MM", fração], ...] do aniversário (ou do mês) que cai no dia 1, sem o mês corrente
    (que ainda não acabou: o CDI dele é parcial, e a poupança só credita no mês seguinte)."""
    corrente = f"{hoje:%Y-%m}"
    return [
        [f"{momento:%Y-%m}", float(valor) / 100]
        for momento, valor in serie.items()
        if momento.day == 1 and f"{momento:%Y-%m}" < corrente
    ]


def _mensal(meses: list[list]) -> dict:
    if not meses:
        raise bcb.BcbIndisponivelError("Série mensal vazia.")
    return {"meses": meses, "ultimo": meses[-1][0]}


def _cdi_mensal(hoje: date, buscar: Buscar) -> dict:
    serie = bcb.baixar_sgs(CDI_NO_MES, INICIO_DO_IPCA, hoje, hoje, buscar)
    return _mensal(_meses_fechados(serie, hoje))


def _poupanca_mensal(hoje: date, buscar: Buscar) -> dict:
    """O rendimento de quem depositou no dia 1: regra antiga até mai/2012, regra nova depois."""
    antiga = bcb.baixar_sgs(
        POUPANCA_ANTIGA, INICIO_DO_IPCA, date(2012, 5, 31), hoje, buscar
    )
    nova = bcb.baixar_sgs(POUPANCA, date(2012, 6, 1), hoje, hoje, buscar)
    meses = [m for m in _meses_fechados(antiga, hoje) if m[0] < COMECO_DA_REGRA_NOVA]
    meses += [m for m in _meses_fechados(nova, hoje) if m[0] >= COMECO_DA_REGRA_NOVA]
    return _mensal(meses)


def _focus(hoje: date, buscar: Buscar) -> dict:
    """A mediana da pesquisa Focus mais nova, do ano corrente aos 3 seguintes, em fração."""
    resultado = {}
    for chave, indicador in INDICADORES_DO_FOCUS.items():
        tabela = bcb.baixar_focus(
            indicador, hoje - timedelta(days=DIAS_DE_FOCUS), buscar, base_de_calculo=0
        )
        if tabela.empty:
            raise bcb.BcbIndisponivelError(
                f"Sem pesquisa Focus recente de {indicador}."
            )
        mais_nova = tabela[tabela["data"] == tabela["data"].max()]
        anos = range(hoje.year, hoje.year + ANOS_DE_FOCUS)
        resultado[chave] = {
            "data": _dia(mais_nova["data"].iloc[0]),
            "anos": {
                str(linha.ano): float(linha.mediana) / 100
                for linha in mais_nova.itertuples()
                if linha.ano in anos
            },
        }
    return resultado


def _tesouro(hoje: date, buscar: Buscar) -> dict:
    return tesouro_direto.baixar_taxas_do_dia(hoje, buscar)


COLETORES: dict[str, Coletor] = {
    "moedas": _moedas,
    "cdi": _cdi,
    "selic_meta": _selic_meta,
    "poupanca": _poupanca,
    "ipca": _ipca,
    "focus": _focus,
    "cdi_mensal": _cdi_mensal,
    "poupanca_mensal": _poupanca_mensal,
    "tesouro": _tesouro,
}


def coletar(hoje: date, buscar: Buscar = requests.get) -> tuple[dict, list[str]]:
    """As partes que vieram e a lista das que falharam ("parte (motivo)")."""
    dados: dict = {}
    falhas: list[str] = []
    for parte, coletor in COLETORES.items():
        try:
            dados[parte] = coletor(hoje, buscar)
        except (
            bcb.BcbIndisponivelError,
            tesouro_direto.TesouroIndisponivelError,
        ) as erro:
            log.error("%s: %s", parte, erro)
            falhas.append(f"{parte} ({erro})")
    return dados, falhas


def montar(dados: dict, anterior: dict, agora: datetime) -> dict:
    """O arquivo novo: as partes coletadas agora e, das que falharam, as do arquivo anterior."""
    arquivo: dict = {"gerado_em": agora.isoformat(timespec="seconds"), "fonte": FONTE}
    for parte in PARTES:
        if parte in dados:
            arquivo[parte] = dados[parte]
        elif parte in anterior:
            arquivo[parte] = anterior[parte]
    return arquivo


def gravar(destino: Path, conteudo: dict) -> None:
    """Grava num temporário ao lado e troca de uma vez: o nginx nunca serve um arquivo pela metade."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".json.tmp")
    temporario.write_text(
        json.dumps(conteudo, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporario, destino)


def _anterior(destino: Path) -> dict:
    try:
        return json.loads(destino.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _agora() -> datetime:
    return datetime.now(bcb.FUSO)


def resumo_das_falhas(falhas: list[str]) -> str:
    """A linha `FALHAS: ...` do aviso do Kuma, curta."""
    linha = "FALHAS: " + "; ".join(falhas)
    if len(linha) <= TAMANHO_MAXIMO_DO_RESUMO:
        return linha
    return linha[: TAMANHO_MAXIMO_DO_RESUMO - 3] + "..."


def main(argv: Sequence[str] | None = None, buscar: Buscar = requests.get) -> int:
    parser = argparse.ArgumentParser(
        description="Dados do Banco Central e do Tesouro para as ferramentas do site."
    )
    parser.add_argument("--destino", type=Path, required=True)
    args = parser.parse_args(argv)
    agora = _agora()
    dados, falhas = coletar(agora.date(), buscar)
    gravar(args.destino, montar(dados, _anterior(args.destino), agora))
    print(f"{len(dados)} de {len(PARTES)} partes atualizadas em {args.destino}")
    if falhas:
        print(resumo_das_falhas(falhas))
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main())
