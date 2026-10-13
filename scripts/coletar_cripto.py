"""Coleta da base de cripto no servidor de casa (série 1 de cripto; `base/cripto/coleta.py`).

    python -m scripts.coletar_cripto mb          (Mercado Bitcoin: só os dias que faltam)
    python -m scripts.coletar_cripto kraken      (Kraken: os últimos 720 dias)
    python -m scripts.coletar_cripto cftc        (posições nos futuros de Bitcoin da CME)
    python -m scripts.coletar_cripto wikipedia   (acessos ao artigo "Bitcoin")
    python -m scripts.coletar_cripto gdelt       (notícias; um dia por vez, 6 s entre pedidos)
    python -m scripts.coletar_cripto receita     (planilha de criptoativos da Receita)
    python -m scripts.coletar_cripto no          (nó do Bitcoin; cookie em BITCOIN_COOKIE)
    python -m scripts.coletar_cripto kraken-arquivo XBTUSD_1440.csv   (carga única do histórico)
    python -m scripts.coletar_cripto qualidade   (regras C1 a C8 sobre a base; achados em qualidade/)
    python -m scripts.coletar_cripto verificar   (refaz dos originais, "como era na data" e eventos)

A base fica em `<TICKERLAB_ACERVO>/base/cripto/`. Cada arquivo baixado vai para o acervo do
original e para o registro de coletas (`com_registro`). Qualquer falha devolve 1 (o Kuma avisa) e
nada é tratado como dado ausente: a rodada seguinte pede de novo desde o último dia guardado.
"""

import argparse
import json
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import asdict, fields
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import requests
import sqlalchemy as sa

from base.cripto import coleta
from base.cripto.arquivos import gravar_parquet, ler_tabela
from base.cripto.eventos import dias_que_nao_batem, saltos_nos_eventos
from base.cripto.leitura import CadeiaInconsistente, ler_blocos
from base.cripto.no_bitcoin import ClienteRPC, ErroDoNo
from base.cripto.qualidade import VERSAO_DAS_REGRAS, AchadoCripto, rodar
from base.cripto.reprodutivel import CHAVES, Original, comparar, nada_depois_de, refazer
from src import acervo
from src.banco.coletas import com_registro
from src.banco.conexao import obter_engine
from src.banco.modelo import coletas
from src.bcb import baixar_ptax

log = logging.getLogger("coletar_cripto")

AGENTE = "TickerLab (tickerlab.com.br; contato@tickerlab.com.br)"
TEMPO_LIMITE_EM_SEGUNDOS = 120
VARIAVEL_DO_COOKIE = "BITCOIN_COOKIE"
# fonte da linha de comando: (nome no registro de coletas, função de coleta)
COLETAS: dict[str, tuple[str, Callable[[Path, datetime, coleta.Baixar], int]]] = {
    "mb": ("mb-candles", coleta.coletar_mercado_bitcoin),
    "kraken": ("kraken-ohlc", coleta.coletar_kraken),
    "cftc": ("cftc-tff", coleta.coletar_cftc),
    "wikipedia": ("wiki-acessos", coleta.coletar_wikipedia),
    "gdelt": ("gdelt-cripto", coleta.coletar_gdelt),
    "receita": ("rfb-cripto", coleta.coletar_receita),
}
# a carga única do histórico: o CSV diário que vem dentro do zip oficial da Kraken
ARQUIVO_DA_KRAKEN = "https://assets.kraken.com/marketing/institutions/Kraken_OHLCVT_Full.zip/XBTUSD_1440.csv"
INICIO_DA_PTAX = date(2014, 1, 1)
# a base montada "nesta data" não pode trazer nada divulgado depois (exigência 3)
CORTE_DO_COMO_ERA = datetime(2020, 12, 31, 23, 59, 59, tzinfo=UTC)
FONTES_REFAZIVEIS = (
    "kraken-ohlc",
    "kraken-arquivo",
    "mb-candles",
    "cftc-tff",
    "wiki-acessos",
    "gdelt-cripto",
    "rfb-cripto",
)
FALHAS_ESPERADAS = (
    requests.RequestException,
    ValueError,
    KeyError,
    ErroDoNo,
    CadeiaInconsistente,
)


def pasta_da_base() -> Path:
    """`<acervo>/base/cripto`, ao lado das outras bases (combinado com a sessão da base de ML)."""
    return (acervo.pasta_do_acervo() or acervo.PASTA_PADRAO) / "base" / "cripto"


def _baixar_da_fonte(url: str) -> bytes:
    resposta = requests.get(
        url, timeout=TEMPO_LIMITE_EM_SEGUNDOS, headers={"User-Agent": AGENTE}
    )
    resposta.raise_for_status()
    return resposta.content


def _ptax() -> pd.DataFrame | None:
    """A PTAX de venda por dia, do Banco Central (para a conferência Kraken x Mercado Bitcoin)."""
    tabela = baixar_ptax(INICIO_DA_PTAX, datetime.now(UTC).date())
    return pd.DataFrame({"dia": tabela.index.date, "ptax": tabela["venda"].to_numpy()})


def _rodar_qualidade(pasta: Path, agora: datetime) -> int:
    """Roda as regras sobre a base e grava os achados do dia em `qualidade/AAAA-MM-DD.parquet`."""
    precos = {
        nome: tabela
        for nome in ("kraken", "mb")
        if not (tabela := ler_tabela(pasta / "precos" / nome, "dia")).empty
    }
    cot = ler_tabela(pasta / "cftc", ["relatorio", "contrato"])
    rodada = rodar(precos=precos, ptax=_ptax(), cot=None if cot.empty else cot)
    colunas = [campo.name for campo in fields(AchadoCripto)]
    achados = pd.DataFrame(
        [asdict(achado) for achado in rodada.achados], columns=colunas
    )
    achados = achados.assign(versao_das_regras=VERSAO_DAS_REGRAS, rodado_em=agora)
    gravar_parquet(pasta / "qualidade" / f"{agora:%Y-%m-%d}.parquet", achados)
    if rodada.falhas:
        raise ValueError(f"Regras de qualidade quebradas: {', '.join(rodada.falhas)}")
    return len(achados)


def _originais_do_registro() -> list[Original]:
    """Os originais de cripto do acervo, na ordem do download, com o que o registro diz deles."""
    consulta = (
        sa.select(coletas)
        .where(
            coletas.c.fonte.in_(FONTES_REFAZIVEIS),
            coletas.c.situacao == "ok",
            coletas.c.caminho_do_original.is_not(None),
        )
        .order_by(coletas.c.baixado_em)
    )
    with obter_engine().connect() as conexao:
        linhas = conexao.execute(consulta).all()
    originais = []
    for linha in linhas:
        conteudo = acervo.ler_original(linha.caminho_do_original)
        if conteudo is None:
            raise ValueError(f"O original sumiu do acervo: {linha.caminho_do_original}")
        quando = (
            linha.baixado_em
            if linha.baixado_em.tzinfo
            else linha.baixado_em.replace(tzinfo=UTC)
        )
        originais.append(Original(linha.fonte, linha.url, quando, conteudo))
    return originais


def _verificar(pasta: Path, agora: datetime) -> int:
    """Exigências 3, 5 e 9: refaz dos originais e compara, corta no tempo, confere os eventos."""
    originais = _originais_do_registro()
    iguais = comparar(refazer(originais), pasta)
    guardadas = {
        nome: ler_tabela(pasta / nome, chave) for nome, chave in CHAVES.items()
    }
    guardadas["rede_diaria"] = ler_tabela(pasta / "rede_diaria", "dia")
    com_dado = {nome: tabela for nome, tabela in guardadas.items() if not tabela.empty}
    sem_futuro = nada_depois_de(com_dado, CORTE_DO_COMO_ERA)
    blocos = ler_blocos(pasta / "no")
    eventos_errados = dias_que_nao_batem(blocos) if not blocos.empty else []
    rede = guardadas["rede_diaria"]
    saltos = saltos_nos_eventos(rede) if not rede.empty else pd.DataFrame()
    relatorio = {
        "feito_em": agora.isoformat(),
        "originais": len(originais),
        "iguais": iguais,
        "nada_depois_do_corte": sem_futuro,
        "eventos_que_nao_batem": eventos_errados,
        "saltos_nos_eventos": saltos.to_dict("records"),
    }
    destino = pasta / "verificacao" / f"{agora:%Y-%m-%d}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    # as duas conferências usam o nome da tabela como chave: juntar num dicionário só apagaria uma
    problemas = (
        [f"{nome} não se refaz dos originais" for nome, ok in iguais.items() if not ok]
        + [
            f"{nome} traz dado de depois do corte"
            for nome, ok in sem_futuro.items()
            if not ok
        ]
        + eventos_errados
    )
    if problemas:
        raise ValueError(f"Verificação da base de cripto falhou: {problemas}")
    return len(originais)


def _coletar(fonte: str, pasta: Path, agora: datetime, caminho: str | None) -> int:
    if fonte == "qualidade":
        return _rodar_qualidade(pasta, agora)
    if fonte == "verificar":
        return _verificar(pasta, agora)
    if fonte == "kraken-arquivo":
        if not caminho:
            raise ValueError(
                "Informe o caminho do XBTUSD_1440.csv extraído do arquivo da Kraken."
            )
        ler = com_registro("kraken-arquivo", lambda _url: Path(caminho).read_bytes())
        return coleta.carregar_arquivo_kraken(pasta, agora, ler(ARQUIVO_DA_KRAKEN))
    if fonte == "no":
        cliente = ClienteRPC(Path(os.environ[VARIAVEL_DO_COOKIE]))
        return coleta.coletar_no(pasta, agora, cliente)
    nome_no_registro, coletar = COLETAS[fonte]
    return coletar(pasta, agora, com_registro(nome_no_registro, _baixar_da_fonte))


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "fonte", choices=[*COLETAS, "no", "kraken-arquivo", "qualidade", "verificar"]
    )
    argumentos.add_argument(
        "caminho", nargs="?", help="só para kraken-arquivo: o CSV diário"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        novas = _coletar(
            opcoes.fonte, pasta_da_base(), datetime.now(UTC), opcoes.caminho
        )
    except FALHAS_ESPERADAS as erro:
        log.error("Coleta de cripto (%s) falhou: %r", opcoes.fonte, erro)
        return 1
    log.info("Coleta de cripto (%s): %d linhas novas.", opcoes.fonte, novas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
