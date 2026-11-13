"""Carga do IF.data dos bancos (desde 2000) e do SCR.data do crédito por setor (desde 2012) para a base
(série 3 da base de ML, PR 7; `base/bcb_ifdata.py` e `base/bcb_scr.py`).

    python -m scripts.carga_bcb_credito                     (tudo, até hoje)
    python -m scripts.carga_bcb_credito --so ifdata --desde 2024
    python -m scripts.carga_bcb_credito --so scr --pasta <acervo>/base/bcb
    python -m scripts.carga_bcb_credito --data-base 202509 --forcar   (só manual)

Grava, com manifesto e versões (`base/parquet.py::gravar_com_versoes`):
- `ifdata/valores/tipo_<t>/<AAAAMM>.parquet`: os 15 relatórios de uma data-base e um tipo de
  instituição, no formato longo da fonte, com `disponivel_em`;
- `ifdata/cadastro/<AAAAMM>.parquet`: o cadastro da data-base (com a raiz do CNPJ);
- `ifdata/ligacao_dos_bancos.parquet`: instituição → CNPJ → tickers (com as tabelas da `carga_fca`);
- `scr/<ano>.parquet`: os meses do SCR.data versão 2 do ano, com `disponivel_em`.

As 8 datas-base mais novas do IF.data e os 2 anos mais novos do SCR são baixados de novo a cada carga
(o BC revisa os números; cada revisão vira versão). O resto vem do acervo se já estiver lá. Um pedido
por vez, com pausa; se o firewall do BC bloquear, espera 5 minutos e tenta mais uma vez. Recusa rodar
sem a versão do código (exigência 13 da ADR 0055).

`--data-base AAAAMM` refaz só os valores dessa data-base pelas respostas já guardadas no acervo, sem
baixar do BC e sem tocar no cadastro, na ligação, no SCR nem nas outras datas-base; se faltar uma
resposta guardada, para e diz qual. `--forcar` (só junto com `--data-base`) remonta mesmo com as mesmas
respostas, quando o leitor mudou (linha 877: a 2025-09 gravada com linhas repetidas antes do #1101).

Roda: cron de casa pelo carga-serie3.sh (todo mês, dia 12, às 9h15), sem `--data-base`; com
`--data-base` e `--forcar`, só manual, nunca agendado; citado em dicionario.py.
"""

import argparse
import calendar
import hashlib
import logging
import re
import sys
import time
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import sqlalchemy as sa

from base import bcb_ifdata, bcb_scr, cnpj_pela_ponte
from base.parquet import GRAVADO, IGUAL, gravar_com_versoes, gravar_tabela
from base.publicacao import dia_da_coleta
from scripts import carga_ponte
from src import acervo, rede
from src.banco.coletas import (
    coletas_guardadas,
    com_registro,
    original_mais_recente,
)
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_bcb_credito")
FONTE_IFDATA = "bcb-ifdata"
FONTE_SCR = "bcb-scr-base"  # o arquivista guarda os mesmos arquivos como `bcb-scr`
SUBPASTA = Path("base") / "bcb"
SUBPASTA_DO_FCA = Path("base") / "fca"
DATAS_RECENTES = 8  # do IF.data: dois anos de trimestres
ANOS_RECENTES = 2  # do SCR
PAUSA_IFDATA, PAUSA_SCR = 1.0, 30.0  # segundos entre pedidos
ESPERA_DEPOIS_DO_BLOQUEIO = 300.0
NAO_ENCONTRADO = 404
ORDEM_DOS_VALORES = ["cod_inst", "relatorio", "conta", "grupo", "coluna"]
ORDEM_DO_CADASTRO = ["cod_inst"]
VAZIO = "vazio"  # o BC não mandou linha nenhuma do tipo na data-base


class RespostaGuardadaFaltandoError(LookupError):
    """`--data-base` só relê o que está guardado: falta a resposta destes endereços."""

    def __init__(self, enderecos: list[str]) -> None:
        super().__init__("; ".join(enderecos))
        self.enderecos = enderecos


def _baixar_da_fonte(url: str) -> bytes | None:
    for tentativa in (1, 2):
        try:
            resposta = rede.get_com_agente(url, timeout=900)
            if resposta.status_code == NAO_ENCONTRADO:
                return None
            resposta.raise_for_status()
            return resposta.content
        except requests.RequestException:
            if tentativa == 2:
                raise
            log.warning("o BC não respondeu %s: tento de novo em 5 minutos", url)
            time.sleep(ESPERA_DEPOIS_DO_BLOQUEIO)
    return None


baixar_ifdata = com_registro(FONTE_IFDATA, _baixar_da_fonte)
baixar_scr = com_registro(FONTE_SCR, _baixar_da_fonte)


def _origem(url: str, conteudo: bytes) -> dict[str, str]:
    return {"url": url, "sha256": hashlib.sha256(conteudo).hexdigest()}


def _obter(
    conexao: sa.Connection,
    url: str,
    baixar: Callable[[str], bytes | None],
    de_novo: bool,
    pausa: float,
) -> bytes | None:
    if not de_novo and (guardado := original_mais_recente(conexao, url)) is not None:
        return guardado
    conteudo = baixar(url)
    time.sleep(pausa)
    return conteudo


def _data_da_base(data_base: int) -> date:
    ano, mes = divmod(data_base, 100)
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def _coletas_do_relatorio(
    conexao: sa.Connection, url: str, lido: bytes
) -> list[tuple[pd.Timestamp, bytes]]:
    """Cada resposta guardada do relatório (o dia da baixada e o conteúdo). Sem nenhuma guardada
    (acervo desligado), só a que foi lida agora, sem dia."""
    guardadas = coletas_guardadas(conexao, url)
    if not guardadas:
        return [(pd.NaT, lido)]
    return [(dia_da_coleta(baixado_em), c) for baixado_em, _, c in guardadas]


def _valores_do_tipo(
    coletas: dict[str, list[tuple[pd.Timestamp, bytes]]],
) -> pd.DataFrame:
    """Os relatórios de um tipo, cada um com as revisões do BC (uma coleta por baixada)."""
    partes = []
    for guardadas in coletas.values():
        lidas = [(dia, bcb_ifdata.ler_valores(c)) for dia, c in guardadas]
        lidas = [(dia, t) for dia, t in lidas if not t.empty]
        if lidas:
            partes.append(bcb_ifdata.valores_com_revisoes(lidas))
    return pd.concat(partes, ignore_index=True)


def _valores_com_raiz(
    coletas: dict[str, list[tuple[pd.Timestamp, bytes]]],
    ponte: pd.DataFrame | None,
) -> pd.DataFrame:
    """Os valores do tipo com `cnpj_basico`, a raiz do CNPJ que o cadastro do IF.data dá ao código da
    instituição (linha 904, lote 4; `base/cnpj_pela_ponte.py`). Sem cadastro gravado, a coluna sai vazia."""
    valores = _valores_do_tipo(coletas)
    if ponte is not None and not ponte.empty:
        # a instituição individual tem a raiz do próprio código; o líder só vale para os códigos de conglomerado
        propria = (
            ponte["cod_inst"]
            .astype("string")
            .where(ponte["cod_inst"].astype("string").str.fullmatch(r"\d{8}"))
        )
        ponte = ponte.assign(cnpj_raiz=propria.fillna(ponte["cnpj_raiz"]))
    com_raiz, contagem = cnpj_pela_ponte.com_cnpj_da_ponte(
        valores,
        "cod_inst",
        ponte,
        cnpj_pela_ponte.SO_A_RAIZ,
        chave_da_ponte="cod_inst",
    )
    log.info("ifdata_valores: raiz pelo cadastro %s", contagem)
    return com_raiz


def _gravar_valores_do_tipo(
    conexao: sa.Connection,
    destino: Path,
    lidos: list[tuple[str, bytes]],
    forcar: bool = False,
    pasta: Path | None = None,
) -> str:
    """Os relatórios de um tipo de instituição numa data-base (`VAZIO` se o BC não mandou linha).
    `pasta` é a da base: dela vem o cadastro que dá a raiz do CNPJ."""
    coletas = {u: _coletas_do_relatorio(conexao, u, c) for u, c in lidos}
    origens = [_origem(u, c) for u, guardadas in coletas.items() for _, c in guardadas]
    if all(bcb_ifdata.ler_valores(c).empty for _, c in lidos):
        return VAZIO
    ponte, origens_da_ponte = (
        carga_ponte.ler_ponte(pasta / "ifdata" / "cadastro", pasta)
        if pasta
        else (None, [])
    )
    return gravar_com_versoes(
        lambda: _valores_com_raiz(coletas, ponte),
        destino,
        [*origens, *origens_da_ponte],
        ORDEM_DOS_VALORES,
        forcar=forcar,
    )


def _destino_dos_valores(pasta: Path, tipo: int, data_base: int) -> Path:
    return pasta / "ifdata" / "valores" / f"tipo_{tipo}" / str(data_base)


def carregar_ifdata_data(
    conexao: sa.Connection, data_base: int, pasta: Path, de_novo: bool
) -> str:
    """Os 15 relatórios de cada tipo de instituição e o cadastro de uma data-base. O cadastro é gravado antes
    dos valores: dele vem a raiz do CNPJ de cada instituição (`cnpj_basico`, linha 904)."""
    lidos_por_tipo: dict[int, list[tuple[str, bytes]]] = {}
    for tipo in bcb_ifdata.tipos_da_data(data_base):
        lidos = []
        for relatorio in bcb_ifdata.RELATORIOS:
            url = bcb_ifdata.endereco_dos_valores(data_base, tipo, relatorio)
            conteudo = _obter(conexao, url, baixar_ifdata, de_novo, PAUSA_IFDATA)
            if conteudo is not None:
                lidos.append((url, conteudo))
        lidos_por_tipo[tipo] = lidos
    sem_valores = all(
        bcb_ifdata.ler_valores(c).empty
        for lidos in lidos_por_tipo.values()
        for _, c in lidos
    )
    if sem_valores:
        return "sem dados (ainda não publicada?)"
    resultados = []
    url = bcb_ifdata.endereco_do_cadastro(data_base)
    conteudo = _obter(conexao, url, baixar_ifdata, de_novo, PAUSA_IFDATA)
    if conteudo is not None:
        guardadas = _coletas_do_relatorio(conexao, url, conteudo)
        resultados.append(
            gravar_com_versoes(
                lambda: bcb_ifdata.cadastro_com_revisoes(
                    [(dia, bcb_ifdata.ler_cadastro(c)) for dia, c in guardadas]
                ),
                pasta / "ifdata" / "cadastro" / str(data_base),
                [_origem(url, c) for _, c in guardadas],
                ORDEM_DO_CADASTRO,
            )
        )
    for tipo, lidos in lidos_por_tipo.items():
        destino = _destino_dos_valores(pasta, tipo, data_base)
        resultados.append(_gravar_valores_do_tipo(conexao, destino, lidos, pasta=pasta))
    return f"{resultados.count(GRAVADO)} gravadas, {resultados.count(IGUAL)} iguais"


def refazer_valores_da_data(
    conexao: sa.Connection, data_base: int, pasta: Path, forcar: bool
) -> str:
    """Remonta só os valores de uma data-base pelas respostas do BC já guardadas no acervo, sem baixar
    nada (linha 877: o leitor mudou e as mesmas respostas não regravam). O cadastro, a ligação dos
    bancos, o SCR e as outras datas-base ficam como estão. Se faltar alguma resposta guardada, para
    antes de gravar qualquer tipo (`RespostaGuardadaFaltandoError`)."""
    lidos_por_tipo: dict[int, list[tuple[str, bytes]]] = {}
    faltando = []
    for tipo in bcb_ifdata.tipos_da_data(data_base):
        lidos_por_tipo[tipo] = []
        for relatorio in bcb_ifdata.RELATORIOS:
            url = bcb_ifdata.endereco_dos_valores(data_base, tipo, relatorio)
            guardada = original_mais_recente(conexao, url)
            if guardada is None:
                faltando.append(url)
            else:
                lidos_por_tipo[tipo].append((url, guardada))
    if faltando:
        raise RespostaGuardadaFaltandoError(faltando)
    resultados = [
        _gravar_valores_do_tipo(
            conexao,
            _destino_dos_valores(pasta, tipo, data_base),
            lidos,
            forcar,
            pasta,
        )
        for tipo, lidos in lidos_por_tipo.items()
    ]
    return (
        f"{resultados.count(GRAVADO)} gravadas, {resultados.count(IGUAL)} iguais, "
        f"{resultados.count(VAZIO)} vazias"
    )


def montar_ligacao(pasta: Path, pasta_do_fca: Path) -> int:
    """A ligação instituição → CNPJ → tickers, de todos os cadastros já gravados."""
    # só o cadastro atual de cada data-base (`202506`), nunca as versões anteriores (`202506.v1`)
    arquivos = sorted(
        a
        for a in (pasta / "ifdata" / "cadastro").glob("*.parquet")
        if re.fullmatch(r"\d{6}", a.stem)
    )
    if not arquivos:
        return 0
    cadastro = bcb_ifdata.cadastro_mais_novo(
        pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)
    )
    entradas = [pasta_do_fca / "emissores.parquet", pasta_do_fca / "tickers.parquet"]
    emissores, tickers = (pd.read_parquet(a) for a in entradas)
    ligacao = bcb_ifdata.ligacao_dos_bancos(cadastro, emissores, tickers)
    origens = [
        {
            "url": a.relative_to(a.parents[2]).as_posix(),
            "sha256": hashlib.sha256(a.read_bytes()).hexdigest(),
        }
        for a in [*arquivos, *entradas]
    ]
    gravar_tabela(
        ligacao,
        pasta / "ifdata" / "ligacao_dos_bancos",
        origens,
        ["data_base", "cod_inst"],
    )
    return len(ligacao)


def carregar_scr_ano(
    conexao: sa.Connection, ano: int, pasta: Path, de_novo: bool
) -> str:
    url = bcb_scr.endereco_do_ano(ano)
    conteudo = _obter(conexao, url, baixar_scr, de_novo, PAUSA_SCR)
    if conteudo is None:
        return "sem arquivo"
    guardadas = _coletas_do_relatorio(conexao, url, conteudo)
    return gravar_com_versoes(
        lambda: bcb_scr.ano_com_revisoes(
            [(dia, bcb_scr.ler_ano(c)) for dia, c in guardadas]
        ),
        pasta / "scr" / str(ano),
        [_origem(url, c) for _, c in guardadas],
        list(bcb_scr.COLUNAS_DE_TEXTO),
    )


def _conferir_opcoes(
    argumentos: argparse.ArgumentParser, opcoes: argparse.Namespace
) -> None:
    """`--forcar` só com `--data-base` (nunca num intervalo de anos); `--data-base` sozinha."""
    if opcoes.forcar and opcoes.data_base is None:
        argumentos.error("--forcar só vale junto com --data-base")
    if opcoes.data_base is None:
        return
    if any(o is not None for o in (opcoes.so, opcoes.desde, opcoes.ate)):
        argumentos.error("--data-base não se mistura com --so, --desde nem --ate")
    ano = opcoes.data_base // 100
    if ano < bcb_ifdata.PRIMEIRO_ANO or opcoes.data_base not in bcb_ifdata.datas_base(
        ano, ano
    ):
        argumentos.error(
            f"--data-base {opcoes.data_base}: não é uma data-base do IF.data (AAAAMM de fim de trimestre)"
        )


def _refazer(conexao: sa.Connection, data_base: int, pasta: Path, forcar: bool) -> int:
    try:
        resultado = refazer_valores_da_data(conexao, data_base, pasta, forcar)
    except RespostaGuardadaFaltandoError as erro:
        log.error(
            "IF.data %s: faltam %d respostas guardadas; nada foi baixado nem gravado: %s",
            data_base,
            len(erro.enderecos),
            erro,
        )
        return 1
    log.info("IF.data %s refeita pelas respostas guardadas: %s", data_base, resultado)
    return 0


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    argumentos.add_argument("--so", choices=("ifdata", "scr"), default=None)
    argumentos.add_argument("--desde", type=int, default=None)
    argumentos.add_argument("--ate", type=int, default=None, help="padrão: este ano")
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--fca", type=Path, default=None, help="pasta da carga_fca")
    argumentos.add_argument(
        "--data-base",
        type=int,
        default=None,
        help="AAAAMM: refaz só os valores dessa data-base pelas respostas guardadas, sem baixar",
    )
    argumentos.add_argument(
        "--forcar",
        action="store_true",
        help="só com --data-base: remonta mesmo com as mesmas respostas (o leitor mudou)",
    )
    opcoes = argumentos.parse_args(argv)
    _conferir_opcoes(argumentos, opcoes)
    ate = opcoes.ate or hoje.year
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    raiz = acervo.pasta_do_acervo()
    pasta = opcoes.pasta or (None if raiz is None else raiz / SUBPASTA)
    pasta_do_fca = opcoes.fca or (None if raiz is None else raiz / SUBPASTA_DO_FCA)
    if pasta is None:
        argumentos.error("acervo desligado: informe --pasta")
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            if opcoes.data_base is not None:
                return _refazer(conexao, opcoes.data_base, pasta, opcoes.forcar)
            if opcoes.so in (None, "ifdata"):
                desde = opcoes.desde or bcb_ifdata.PRIMEIRO_ANO
                datas = [
                    d
                    for d in bcb_ifdata.datas_base(desde, ate)
                    if _data_da_base(d) < hoje
                ]
                todas = [
                    d
                    for d in bcb_ifdata.datas_base(bcb_ifdata.PRIMEIRO_ANO, hoje.year)
                    if _data_da_base(d) < hoje
                ]
                recentes = set(todas[-DATAS_RECENTES:])
                for data_base in datas:
                    resultado = carregar_ifdata_data(
                        conexao, data_base, pasta, data_base in recentes
                    )
                    log.info("IF.data %s: %s", data_base, resultado)
                if (
                    pasta_do_fca is not None
                    and (pasta_do_fca / "tickers.parquet").exists()
                ):
                    log.info(
                        "ligação dos bancos: %s linhas",
                        montar_ligacao(pasta, pasta_do_fca),
                    )
                else:
                    log.warning(
                        "sem as tabelas da carga_fca: ligação dos bancos não montada"
                    )
            if opcoes.so in (None, "scr"):
                desde = opcoes.desde or bcb_scr.PRIMEIRO_ANO
                for ano in range(max(desde, bcb_scr.PRIMEIRO_ANO), ate + 1):
                    resultado = carregar_scr_ano(
                        conexao, ano, pasta, ano > hoje.year - ANOS_RECENTES
                    )
                    log.info("SCR %s: %s", ano, resultado)
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
