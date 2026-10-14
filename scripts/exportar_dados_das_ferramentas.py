"""Grava os dados do Banco Central que as ferramentas do site usam: `ferramentas.json`.

    python -m scripts.exportar_dados_das_ferramentas --destino /caminho/ferramentas.json

Roda no VPS uma vez por dia, depois do fechamento da PTAX (~13h), e o nginx do site serve o arquivo
em `tickerlab.com.br/dados/ferramentas.json`. O navegador faz as contas (conversor, renda fixa,
juro real, correção pela inflação) com esses números.

**Só dados do Banco Central** (dados abertos, licença ODbL: pode, citando a fonte). Preço do Yahoo
ou de corretora não entra aqui (ADR 0008; a ferramenta "Quanto daria?" usa a API, só o resultado).

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

import requests

from src import bcb
from src.cdi import SERIE_DO_CDI

FONTE = "Banco Central do Brasil (dados abertos: PTAX e SGS; licença ODbL)"
PARTES = ("moedas", "cdi", "selic_meta", "poupanca", "ipca")
DIAS_PARA_TRAS = 15  # cobre feriados e o fim de semana sem cotação
INICIO_DO_IPCA = date(1994, 7, 1)  # o Plano Real: antes disso, outra moeda
POUPANCA = bcb.Serie(
    195, "Poupança: rentabilidade no mês (depósitos desde 04/05/2012)", "% no mês"
)
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
    inicio = hoje - timedelta(days=DIAS_PARA_TRAS)
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


COLETORES: dict[str, Coletor] = {
    "moedas": _moedas,
    "cdi": _cdi,
    "selic_meta": _selic_meta,
    "poupanca": _poupanca,
    "ipca": _ipca,
}


def coletar(hoje: date, buscar: Buscar = requests.get) -> tuple[dict, list[str]]:
    """As partes que o BC devolveu e a lista das que falharam ("parte (motivo)")."""
    dados: dict = {}
    falhas: list[str] = []
    for parte, coletor in COLETORES.items():
        try:
            dados[parte] = coletor(hoje, buscar)
        except bcb.BcbIndisponivelError as erro:
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
        description="Dados do Banco Central para as ferramentas do site."
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
