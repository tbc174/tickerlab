"""Manda ao VPS o recorte da base que a API lê (linha 739; plano `planos/2026-11-10-api-producao-com-base-739.md`).

O contêiner `tickerlab-api` de produção não tinha `<acervo>/base`: sem ela a API externa (`/data/v1`) e a
`/v1/base/tabelas` respondem 503. Este script monta, a partir da base de casa, uma cópia **só do que a API
serve**, em dois degraus (`--degrau 1`: o núcleo da API externa; `--degrau 2`: mais as tabelas da consulta
aberta da v1), e a entrega ao VPS num tar pela mesma chave dos dossiês (pedido `receber-base-api`).

Lista de permissão (Diretoria, 10/11/2026, ADR 0101 Emenda 4): só vai a tabela escrita em `DEGRAU_1` ou
`DEGRAU_2_ACRESCENTA`, e só a coluna que o dicionário (`base/dicionario.py`) conhece, menos as
`COLUNAS_DE_PESSOA`; a linha que a porta esconde como pessoa (`Tabela.linhas_de_pessoa`, vazio conta como
pessoa) não vai. O que não está na lista não vai: `cnpj/`, `restrito/`, `pessoas/`, os temporários `tmp*` e
as tabelas de pessoa nem são lidos. Arquivo sem nada a tirar segue **byte a byte** (o hash do manifesto ao lado
continua valendo para a linhagem); arquivo com coluna ou linha a tirar é regravado, e a saída é lida de novo e
conferida antes do envio: pessoa na saída é erro e nada sai.

    python -m scripts.enviar_base_ao_vps --degrau 1 --base <acervo>/base --saida /tmp/base-api
    python -m scripts.enviar_base_ao_vps --degrau 2 --base <acervo>/base --enviar

Saída 0 tudo certo; 1 falha, com a última linha `FALHAS: ...` (vai para o aviso do Kuma).

Roda: cron de casa pelo ~/bin/enviar-base-ao-vps.sh (depois da coleta da noite); manual com --saida.
"""

import argparse
import io
import logging
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

import duckdb

from base.dicionario import TABELAS
from base.dossie import COLUNAS_DE_PESSOA, pode_consultar
from base.porta.duckdb import ARQUIVOS, arquivos_da_tabela
from src import acervo

log = logging.getLogger("enviar_base_ao_vps")

# O núcleo da API externa (`src/api_externa/conjuntos/`): demonstrações, rede (empresas) e fundos.
DEGRAU_1 = (
    "demonstracoes_como_era",
    "entidades",
    "identificadores",
    "ligacoes",
    "cadastro_de_fundos",
    "carteiras_dos_fundos",
)
# Fica em casa: pesadas demais para o contêiner (linha 741 para a fidc_informe) ou com nome de parte de
# processo (pessoa possível). Só saem daqui com outra decisão.
FICAM_EM_CASA = (
    "scr_credito",
    "ons_geracao",
    "comex_preco_medio",
    "fidc_informe",
    "processos_partes",
)
# As demais que `base.dossie.pode_consultar` libera (a consulta aberta da v1). Tabela nova que a porta liberar
# não entra sozinha: o teste falha até ela ser escrita aqui ou em FICAM_EM_CASA.
DEGRAU_2_ACRESCENTA = (
    "anac_estatistico", "anatel_acessos", "aneel_samp", "anm_amb_agua_mineral",
    "anm_amb_producao_beneficiada", "anm_amb_producao_bruta", "anm_cfem_arrecadacao",
    "anm_sigbm_barragens", "anp_concessionarios", "anp_vendas", "ans_beneficiarios",
    "antt_siade", "area_cafe_municipio", "auditores", "bcb_selic_focus",
    "carteiras_bloco_8", "ccee_pld", "cda_cotas", "cftc_cot_agro", "clima_regiao_cafe",
    "cnes_competencias", "cnpj_empresas_historico", "cnpj_simples_historico",
    "codigos_invalidos", "comex_cafe", "comex_urf", "comex_via", "conab_cafe",
    "controladas", "curva_juros", "cvm_fiagro", "debentures_assembleias", "dmpl_como_era",
    "emissores", "eventos", "faostat_cafe", "fca_geral", "fre_capital_social",
    "fre_comites", "fre_conselho", "fre_distribuicao_capital", "fre_diversidade",
    "fre_empregados", "fre_remuneracao", "fre_remuneracao_extremos", "ifdata_cadastro",
    "ifdata_valores", "insolvencia", "ma_candidatos", "ma_datas", "ma_regua", "negociacoes",
    "noticias_fatos", "noticias_numeros", "ofertas_antigas", "ofertas_resolucao_160",
    "ons_capacidade", "ons_restricao", "painel_dos_fundos", "pareceres_dfp",
    "pareceres_itr", "pgfn_divida", "processos", "processos_comunicacoes",
    "processos_nas_notas", "ratings", "release_x_oficial",
    "rotulos_atraso", "securitizacao_cedente_devedor", "securitizacao_certificados",
    "sus_ambulatorial", "sus_internacoes", "susep_seguros", "tickers_no_tempo",
    "trocas_de_auditor", "usda_psd_cafe", "valores_mobiliarios",
)  # fmt: skip
# Nada daqui vai, em nenhum degrau: pastas inteiras com pessoa ou de trabalho.
PASTAS_PROIBIDAS = ("cnpj", "restrito", "pessoas")
SUFIXO_DO_MANIFESTO = ".json"
PREFIXO_DA_LINHAGEM = (
    "origem_",
)  # colunas de linhagem que o dicionário agrupa em `_ORIGEM_*`


class RecorteErro(Exception):
    """O recorte não pode sair: um pedido fora da lista ou pessoa na saída."""


@dataclass(frozen=True)
class Resultado:
    tabela: str
    arquivos: int
    copiados: int
    recortados: int
    linhas_tiradas: int
    bytes_enviados: int


def tabelas_do_degrau(degrau: int) -> tuple[str, ...]:
    """As tabelas do degrau (1 = núcleo; 2 = núcleo + consulta aberta), na ordem da lista."""
    if degrau == 1:
        return DEGRAU_1
    if degrau == 2:
        return (*DEGRAU_1, *DEGRAU_2_ACRESCENTA)
    raise RecorteErro(f"degrau {degrau} não existe (1 ou 2)")


def conferir_a_lista(tabelas: tuple[str, ...]) -> None:
    """Falha se uma tabela da lista não pode sair: sem arquivo na porta, de pessoa ou fora do que a porta mostra."""
    for nome in tabelas:
        if nome not in ARQUIVOS or nome not in TABELAS:
            raise RecorteErro(f"{nome}: a porta não serve esta tabela")
        if TABELAS[nome].pessoa:
            raise RecorteErro(f"{nome}: tabela de pessoa natural")
        if nome in FICAM_EM_CASA:
            raise RecorteErro(f"{nome}: fica em casa")
        if nome not in DEGRAU_1 and not pode_consultar(nome):
            raise RecorteErro(f"{nome}: a consulta aberta não a libera")
        if ARQUIVOS[nome].split("/")[0] in PASTAS_PROIBIDAS:
            raise RecorteErro(f"{nome}: mora em pasta proibida")


def colunas_permitidas(nome: str, colunas: list[str]) -> list[str]:
    """As colunas do arquivo que podem sair: as que o dicionário da tabela conhece, sem as de pessoa."""
    tabela = TABELAS[nome]
    conhecidas = {
        *tabela.colunas,
        *tabela.datas.values(),
        *tabela.chaves,
        *([tabela.linhas_de_pessoa] if tabela.linhas_de_pessoa else []),
    }
    return [
        c
        for c in colunas
        if c not in COLUNAS_DE_PESSOA
        and (c in conhecidas or c.startswith(PREFIXO_DA_LINHAGEM))
    ]


def _aspas(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def _colunas_do_arquivo(con: duckdb.DuckDBPyConnection, arquivo: Path) -> list[str]:
    cursor = con.execute(
        f"SELECT * FROM read_parquet({_aspas(arquivo.as_posix())}) LIMIT 0"
    )
    return [c[0] for c in cursor.description]


def _contar(con: duckdb.DuckDBPyConnection, arquivo: Path, onde: str) -> int:
    consulta = (
        f"SELECT count(*) FROM read_parquet({_aspas(arquivo.as_posix())}) WHERE {onde}"
    )
    return int(con.execute(consulta).fetchone()[0])  # type: ignore[index]


def _onde_pessoa(coluna: str) -> str:
    """Linha de pessoa: marcada ou sem marca (na dúvida é pessoa, como a porta)."""
    return f'coalesce("{coluna}", true)'


def _copiar_manifesto(origem: Path, destino: Path) -> None:
    manifesto = origem.with_suffix(SUFIXO_DO_MANIFESTO)
    if manifesto.is_file():
        shutil.copy2(manifesto, destino.with_suffix(SUFIXO_DO_MANIFESTO))


def recortar_arquivo(
    con: duckdb.DuckDBPyConnection, nome: str, origem: Path, destino: Path
) -> tuple[bool, int]:
    """Põe em `destino` o que de `origem` pode sair. Devolve (copiado byte a byte?, linhas tiradas).

    Sem coluna nem linha a tirar o arquivo vai igual. Com `linhas_de_pessoa` declarada mas ausente do arquivo
    a porta não serve linha nenhuma: aqui também nada sai (erro).
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    colunas = _colunas_do_arquivo(con, origem)
    mantidas = colunas_permitidas(nome, colunas)
    marca = TABELAS[nome].linhas_de_pessoa
    if marca and marca not in colunas:
        raise RecorteErro(
            f"{nome}: {origem.name} não tem `{marca}`: não dá para separar pessoa"
        )
    de_pessoa = _contar(con, origem, _onde_pessoa(marca)) if marca else 0
    if mantidas == colunas and de_pessoa == 0:
        shutil.copy2(origem, destino)
        _copiar_manifesto(origem, destino)
        return True, 0
    if not mantidas:
        raise RecorteErro(f"{nome}: {origem.name} ficaria sem coluna")
    selecao = ", ".join(f'"{c}"' for c in mantidas)
    onde = f"NOT {_onde_pessoa(marca)}" if marca else "true"
    con.execute(
        f"COPY (SELECT {selecao} FROM read_parquet({_aspas(origem.as_posix())}) WHERE {onde}) "
        f"TO {_aspas(destino.as_posix())} (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    _copiar_manifesto(origem, destino)
    return False, de_pessoa


def conferir_saida(con: duckdb.DuckDBPyConnection, nome: str, arquivo: Path) -> None:
    """Lê o arquivo que vai sair e falha se tiver coluna de pessoa ou linha de pessoa."""
    colunas = _colunas_do_arquivo(con, arquivo)
    proibidas = sorted(set(colunas) & COLUNAS_DE_PESSOA)
    if proibidas:
        raise RecorteErro(
            f"{nome}: {arquivo.name} saiu com coluna de pessoa {proibidas}"
        )
    marca = TABELAS[nome].linhas_de_pessoa
    if marca and (
        marca not in colunas or _contar(con, arquivo, _onde_pessoa(marca)) > 0
    ):
        raise RecorteErro(f"{nome}: {arquivo.name} saiu com linha de pessoa")


def montar(base: Path, saida: Path, tabelas: tuple[str, ...]) -> list[Resultado]:
    """Monta em `saida` (= a futura `<acervo>/base` do VPS) o recorte das tabelas; confere tudo."""
    conferir_a_lista(tabelas)
    base = base.resolve()
    resultados: list[Resultado] = []
    con = duckdb.connect()
    try:
        for nome in tabelas:
            arquivos = arquivos_da_tabela(base, ARQUIVOS[nome])
            copiados = recortados = tiradas = enviados = 0
            for origem in arquivos:
                relativo = origem.relative_to(base)
                if relativo.parts[0] in PASTAS_PROIBIDAS:
                    raise RecorteErro(f"{nome}: {relativo} está em pasta proibida")
                destino = saida / relativo
                igual, tirou = recortar_arquivo(con, nome, origem, destino)
                conferir_saida(con, nome, destino)
                copiados += igual
                recortados += not igual
                tiradas += tirou
                enviados += destino.stat().st_size
            resultados.append(
                Resultado(nome, len(arquivos), copiados, recortados, tiradas, enviados)
            )
    finally:
        con.close()
    return resultados


def empacotar(saida: Path, destino: io.BufferedIOBase) -> int:
    """Escreve o tar de `saida` (caminhos relativos, só arquivo comum). Devolve quantos arquivos."""
    total = 0
    with tarfile.open(fileobj=destino, mode="w|") as tar:  # type: ignore[call-overload]
        for arquivo in sorted(p for p in saida.rglob("*") if p.is_file()):
            info = tar.gettarinfo(
                str(arquivo), arcname=arquivo.relative_to(saida).as_posix()
            )
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with arquivo.open("rb") as f:
                tar.addfile(info, f)
            total += 1
    return total


def enviar(saida: Path, comando_ssh: list[str]) -> int:
    """Manda o tar de `saida` pela entrada padrão do ssh; devolve o código de saída do ssh."""
    with subprocess.Popen(comando_ssh, stdin=subprocess.PIPE) as processo:
        assert processo.stdin is not None
        empacotar(saida, processo.stdin)  # type: ignore[arg-type]
        processo.stdin.close()
        return processo.wait()


def comando_ssh_padrao() -> list[str]:
    return [
        "ssh", "-T", "-i", str(Path.home() / ".ssh" / "enviar_dossies"),
        "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=30",
        "tiago@tickerlab-vps.taila57363.ts.net", "receber-base-api",
    ]  # fmt: skip


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Recorte da base para o VPS (linha 739)")
    p.add_argument("--degrau", type=int, choices=(1, 2), required=True)
    p.add_argument(
        "--base", type=Path, help="<acervo>/base (padrão: o acervo do ambiente)"
    )
    p.add_argument(
        "--saida", type=Path, help="pasta onde montar o recorte (padrão: temporária)"
    )
    p.add_argument(
        "--enviar",
        action="store_true",
        help="manda o recorte ao VPS (receber-base-api)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    base = args.base
    if base is None:
        raiz = acervo.pasta_do_acervo()
        if raiz is None:
            print("FALHAS: acervo desligado (TICKERLAB_ACERVO)")
            return 1
        base = raiz / "base"
    temporaria = None
    saida = args.saida
    if saida is None:
        temporaria = tempfile.mkdtemp(prefix="base-api-")
        saida = Path(temporaria)
    try:
        resultados = montar(base, saida, tabelas_do_degrau(args.degrau))
        for r in resultados:
            log.info(
                "%s: %d arquivo(s), %d iguais, %d recortados, %d linha(s) de pessoa fora, %.1f MB",
                r.tabela, r.arquivos, r.copiados, r.recortados, r.linhas_tiradas, r.bytes_enviados / 1e6,
            )  # fmt: skip
        vazias = [
            r.tabela for r in resultados if r.arquivos == 0 and r.tabela in DEGRAU_1
        ]
        if vazias:
            print(f"FALHAS: sem arquivo na base: {', '.join(vazias)}")
            return 1
        if args.enviar:
            codigo = enviar(saida, comando_ssh_padrao())
            if codigo:
                print(f"FALHAS: o ssh saiu com {codigo}")
                return 1
        return 0
    except (RecorteErro, duckdb.Error, OSError) as erro:
        print(f"FALHAS: {erro}")
        return 1
    finally:
        if temporaria:
            shutil.rmtree(temporaria, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
