"""Monta `receita_dirbi`, `receita_ecf_renuncia` e `sigsif_habilitados` (linha 904, lote 3 das 300 tabelas pelo CNPJ).

    python -m scripts.montar_tabelas_lote_3 --baixar-sigsif <pasta nova e vazia>            (só baixa os 2 CSVs)
    python -m scripts.montar_tabelas_lote_3 --sigsif <pasta baixada>                        (grava no acervo)
    python -m scripts.montar_tabelas_lote_3 --receita <pasta de carga_receita_renuncias --baixar>
    python -m scripts.montar_tabelas_lote_3 --sigsif <pasta> --receita <pasta> --pasta /tmp/base

O download da Receita é o de `scripts/carga_receita_renuncias.py --baixar` (mesma pasta, mesmo `modificados.json`).
O do SIGSIF vem do CKAN do MAPA (CC BY) e também escreve `modificados.json` com o `Last-Modified` de cada CSV, que
vira o `disponivel_em`. Os arquivos baixados são dados de fora: ficam numa pasta nova, nunca no repositório, e esta
carga os lê com o Python em modo isolado (`python -I`).

Grava, só de pessoa jurídica (`base/derivadas_do_lote_3.py`: quem é pessoa sai da tabela inteira, e nenhum nome é
gravado), com manifesto e versões (`base/parquet.py::gravar_com_versoes`):
- `receita_dirbi/<ano>.parquet`: um por ano do DIRBI;
- `receita_ecf_renuncia/receita_ecf_renuncia.parquet`;
- `sigsif_habilitados/sigsif_habilitados.parquet`.

Pergunta à Receita guardada (`base/pgfn.py::pessoas_pela_receita`) quais raízes são de pessoa; sem ela, nada entra.
O resumo no log diz, por tabela, as linhas lidas, as que saíram (CNPJ inválido, pessoa ou fora da Receita) e as que
ficaram: é a prova de zero pessoa que a carga no servidor pede. Recusa rodar sem a versão do código (exigência 13
da ADR 0055). Saída 0 tudo certo; 1 arquivo faltando ou tabela vazia.

Roda: manual (python -m scripts.montar_tabelas_lote_3), no servidor de casa, depois de baixar; sem uso registrado em
13/11/2026 (a carga pede o "pode" da Diretoria).
"""

import argparse
import hashlib
import json
import logging
import sys
import zipfile
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy.engine import Connection

from base import derivadas_do_lote_3 as derivadas
from base import receita_renuncias as renuncias
from base import sigsif
from base.parquet import GRAVADO, gravar_com_versoes
from base.pgfn import pessoas_pela_receita
from scripts import carga_receita_renuncias as carga
from src import acervo, rede
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.montar_tabelas_lote_3")

MODIFICADOS = "modificados.json"
ARQUIVOS_DO_SIGSIF = {
    "registrados.csv": "97277e92-264a-4dc0-9aea-f87b8ea93798/download/sigsifestabelecimentosregistradosnosif.csv",
    "habilitados.csv": "fcb7f87d-0092-4a52-a44b-b3550747b4c2/download/sigsifestabelecimentosnacionais.csv",
}
ENDERECO_DO_SIGSIF = "https://dados.agricultura.gov.br/dataset/062166e3-b515-4274-8e7d-68aadd64b820/resource/"
TEMPO_LIMITE = 300
TAMANHO_DO_PEDACO = 1 << 20
ORDEM_DO_DIRBI = list(derivadas.CHAVE_DO_DIRBI)
ORDEM_DA_ECF = list(derivadas.CHAVE_DA_ECF)
ORDEM_DOS_HABILITADOS = list(derivadas.CHAVE_DOS_HABILITADOS)


def baixar_sigsif(destino: Path) -> dict[str, str]:
    """Baixa os dois CSVs do SIGSIF para uma pasta nova e vazia e devolve o `Last-Modified` (AAAA-MM-DD) de cada."""
    if destino.exists() and any(destino.iterdir()):
        raise SystemExit(f"{destino} não está vazia: baixe numa pasta nova")
    destino.mkdir(parents=True, exist_ok=True)
    modificados: dict[str, str] = {}
    for nome, fim in ARQUIVOS_DO_SIGSIF.items():
        with rede.get_com_agente(
            ENDERECO_DO_SIGSIF + fim, stream=True, timeout=TEMPO_LIMITE
        ) as resposta:
            resposta.raise_for_status()
            with open(destino / nome, "wb") as saida:
                saida.writelines(resposta.iter_content(TAMANHO_DO_PEDACO))
            modificado = parsedate_to_datetime(resposta.headers["Last-Modified"])
            modificados[nome] = modificado.date().isoformat()
        log.info("baixado %s (modificado em %s)", nome, modificados[nome])
    (destino / MODIFICADOS).write_text(
        json.dumps(modificados, indent=1), encoding="utf-8"
    )
    return modificados


def _sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        while pedaco := arquivo.read(TAMANHO_DO_PEDACO):
            resumo.update(pedaco)
    return resumo.hexdigest()


def _modificado_em(pasta: Path, nome: str) -> date:
    registro = json.loads((pasta / MODIFICADOS).read_text(encoding="utf-8"))
    return date.fromisoformat(registro[nome])


def _baixado_em(caminho: Path) -> pd.Timestamp:
    """Quando o arquivo foi gravado no disco (o horário em que foi baixado), em UTC."""
    return pd.Timestamp(caminho.stat().st_mtime, unit="s", tz="UTC")


def _origem(caminho: Path, url: str) -> list[dict[str, str]]:
    return [{"url": url, "sha256": _sha256(caminho)}]


def _dirbi_do_zip(
    caminho: Path,
    modificado: date,
    descobrir: derivadas.DescobrirPessoas,
    carimbos: tuple[pd.Timestamp, str],
    dados: dict[str, object],
) -> pd.DataFrame:
    """Lê um ZIP do DIRBI e devolve só as pessoas jurídicas; a contagem vai para `dados`."""
    lida = renuncias.Contagem()
    with zipfile.ZipFile(caminho) as zip_, zip_.open(zip_.namelist()[0]) as fluxo:
        lido = renuncias.ler_dirbi(fluxo, modificado, lida)
    tabela, contagem = derivadas.dirbi_para_a_base(lido, descobrir)
    dados.update({**lida.para_manifesto(), **contagem})
    agora, versao = carimbos
    return derivadas.com_linhagem(
        tabela, modificado, _sha256(caminho), _baixado_em(caminho), agora, versao
    )


def montar_dirbi(
    origem: Path,
    saida: Path,
    descobrir: derivadas.DescobrirPessoas,
    agora: pd.Timestamp,
    versao: str,
    forcar: bool = False,
) -> dict[str, dict[str, object]]:
    """Um Parquet por ZIP do DIRBI (por ano); devolve, por ano, o resultado da gravação e a contagem."""
    resumo: dict[str, dict[str, object]] = {}
    for nome in carga.ARQUIVOS_DO_DIRBI:
        caminho = origem / nome
        ano = nome.removesuffix(".zip").rsplit("-", 1)[-1]
        dados: dict[str, object] = {}
        montar = partial(
            _dirbi_do_zip,
            caminho,
            _modificado_em(origem, nome),
            descobrir,
            (agora, versao),
            dados,
        )
        dados["gravou"] = gravar_com_versoes(
            montar,
            saida / derivadas.TABELA_DIRBI / ano,
            _origem(caminho, f"{carga.ENDERECO_PUBLICO}DIRBI/{nome}"),
            ORDEM_DO_DIRBI,
            forcar=forcar,
        )
        resumo[ano] = dados
    return resumo


def montar_ecf(
    origem: Path,
    saida: Path,
    descobrir: derivadas.DescobrirPessoas,
    agora: pd.Timestamp,
    versao: str,
    forcar: bool = False,
) -> dict[str, object]:
    caminho = origem / carga.ARQUIVO_DA_ECF
    dados: dict[str, object] = {}

    def montar() -> pd.DataFrame:
        lida = renuncias.Contagem()
        data = _modificado_em(origem, caminho.name)
        with open(caminho, "rb") as fluxo:
            lido = renuncias.ler_ecf(fluxo, data, lida)
        tabela, contagem = derivadas.ecf_para_a_base(lido, descobrir)
        dados.update({**lida.para_manifesto(), **contagem})
        return derivadas.com_linhagem(
            tabela, data, _sha256(caminho), _baixado_em(caminho), agora, versao
        )

    dados["gravou"] = gravar_com_versoes(
        montar,
        saida / derivadas.TABELA_ECF / derivadas.TABELA_ECF,
        _origem(caminho, f"{carga.ENDERECO_PUBLICO}ECF/{caminho.name}"),
        ORDEM_DA_ECF,
        forcar=forcar,
    )
    return dados


def montar_habilitados(
    origem: Path,
    saida: Path,
    descobrir: derivadas.DescobrirPessoas,
    agora: pd.Timestamp,
    versao: str,
    forcar: bool = False,
) -> dict[str, object]:
    registrados = origem / "registrados.csv"
    habilitados = origem / "habilitados.csv"
    dados: dict[str, object] = {}

    def montar() -> pd.DataFrame:
        cadastro = sigsif.ler_estabelecimentos(
            registrados.read_bytes(), _modificado_em(origem, registrados.name)
        )
        dados["registrados_sem_cnpj_descartados"] = cadastro.attrs[
            "descartadas_sem_cnpj"
        ]
        # o CNPJ vem do cadastro e a habilitação do outro arquivo: a linha vale desde o mais novo dos dois
        data = max(
            _modificado_em(origem, habilitados.name),
            _modificado_em(origem, registrados.name),
        )
        # SIF que também aparece numa linha sem CNPJ (CPF) não tem dono único: fica sem CNPJ e sai da tabela
        ambiguos = cadastro.attrs["sifs_sem_cnpj"]
        cadastro = cadastro[~cadastro["nr_sif"].isin(ambiguos)]
        lido = sigsif.ler_habilitados(habilitados.read_bytes(), cadastro, data)
        tabela, contagem = derivadas.habilitados_para_a_base(lido, descobrir)
        dados.update(contagem)
        return derivadas.com_linhagem(
            tabela,
            data,
            _sha256(habilitados),
            _baixado_em(habilitados),
            agora,
            versao,
        )

    origens = [
        {
            "url": ENDERECO_DO_SIGSIF + ARQUIVOS_DO_SIGSIF[nome],
            "sha256": _sha256(origem / nome),
        }
        for nome in ("registrados.csv", "habilitados.csv")
    ]
    dados["gravou"] = gravar_com_versoes(
        montar,
        saida / derivadas.TABELA_HABILITADOS / derivadas.TABELA_HABILITADOS,
        origens,
        ORDEM_DOS_HABILITADOS,
        forcar=forcar,
    )
    return dados


def _pessoas_pela_receita(conexao: Connection) -> derivadas.DescobrirPessoas:
    def descobrir(raizes: np.ndarray) -> np.ndarray:
        return pessoas_pela_receita(conexao, raizes)

    return descobrir


def _vazia(dados: dict[str, object]) -> bool:
    """Montou e ficou sem linha. Quando a versão guardada é igual, a montagem nem roda e não há contagem."""
    return "linhas_na_tabela" in dados and not dados["linhas_na_tabela"]


def _faltam(pasta: Path, nomes: list[str]) -> list[str]:
    return [n for n in nomes if not (pasta / n).exists()]


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--baixar-sigsif", type=Path, default=None)
    argumentos.add_argument("--sigsif", type=Path, default=None)
    argumentos.add_argument("--receita", type=Path, default=None)
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--forcar", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if opcoes.baixar_sigsif:
        baixar_sigsif(opcoes.baixar_sigsif)
        return 0
    if not (opcoes.sigsif or opcoes.receita):
        argumentos.error("passe --baixar-sigsif <pasta nova>, --sigsif ou --receita")
    faltam: list[str] = []
    if opcoes.sigsif:
        faltam += _faltam(opcoes.sigsif, [*ARQUIVOS_DO_SIGSIF, MODIFICADOS])
    if opcoes.receita:
        faltam += _faltam(
            opcoes.receita,
            [*carga.ARQUIVOS_DO_DIRBI, carga.ARQUIVO_DA_ECF, MODIFICADOS],
        )
    if faltam:
        log.error("faltam: %s", ", ".join(faltam))
        return 1
    saida = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    versao = exigir_versao_do_codigo()
    log.info("Versão do código: %s", versao)
    agora = pd.Timestamp(datetime.now(UTC))
    vazias: list[str] = []
    with obter_engine().connect() as conexao:
        descobrir = _pessoas_pela_receita(conexao)
        if opcoes.receita:
            dirbi = montar_dirbi(
                opcoes.receita, saida, descobrir, agora, versao, opcoes.forcar
            )
            ecf = montar_ecf(
                opcoes.receita, saida, descobrir, agora, versao, opcoes.forcar
            )
            for ano, dados in dirbi.items():
                log.info("%s %s: %s", derivadas.TABELA_DIRBI, ano, dados)
            log.info("%s: %s", derivadas.TABELA_ECF, ecf)
            vazias += [f"DIRBI {a}" for a, d in dirbi.items() if _vazia(d)]
            vazias += ["ECF"] if _vazia(ecf) else []
        if opcoes.sigsif:
            hab = montar_habilitados(
                opcoes.sigsif, saida, descobrir, agora, versao, opcoes.forcar
            )
            log.info("%s: %s", derivadas.TABELA_HABILITADOS, hab)
            vazias += ["habilitados"] if _vazia(hab) else []
    if vazias:
        log.error(
            "tabela vazia (sem a Receita guardada toda raiz conta como pessoa): %s",
            ", ".join(vazias),
        )
        return 1
    log.info("gravado: %s", GRAVADO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
