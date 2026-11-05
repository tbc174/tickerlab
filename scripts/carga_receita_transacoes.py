"""Coleta e carga das transações tributárias da Receita para a base: acordos individuais e adesões (linha 661).

    python -m scripts.carga_receita_transacoes --baixar <pasta nova e vazia>      (só baixa)
    python -m scripts.carga_receita_transacoes --origem <pasta baixada>           (grava no acervo)
    python -m scripts.carga_receita_transacoes --origem <pasta> --pasta /tmp/base --forcar

`--baixar` pega do portal de dados abertos da Receita (gov.br) os dois CSV e escreve `modificados.json` com a
data de "Atualizado em" da página de cada um, que vira o `disponivel_em` (o download não manda `Last-Modified`
e nenhuma das duas fontes traz a data de publicação por linha). Os arquivos baixados são dados de fora: ficam
numa pasta nova, nunca no repositório, e esta carga os lê com o Python em modo isolado (`python -I`).

`--origem` grava, com manifesto e versões (`base/parquet.py::gravar_com_versoes`):
- `receita/transacoes_individual.parquet`: os acordos, uma linha por CNPJ e processo;
- `receita/transacoes_adesao.parquet`: as adesões, uma linha por pedido (chave: `hash_linha`).
Pessoa física (CPF, mascarado ou não) nunca é gravada.

Licença a confirmar, só uso interno (ADR 0102, Emenda 2); nada é perguntado à fonte. Recusa rodar sem a
versão do código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 arquivo faltando.
"""

import argparse
import hashlib
import json
import logging
import re
from datetime import date
from pathlib import Path

import pandas as pd

from base import receita_transacoes as transacoes
from base.parquet import gravar_com_versoes
from src import acervo, rede
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_receita_transacoes")
RAIZ = "https://www.gov.br/receitafederal/dados/"
ARQUIVO_INDIVIDUAL = "transacoes-individual.csv"
ARQUIVO_ADESAO = "transacoes-adesao.csv"
ARQUIVOS = (ARQUIVO_INDIVIDUAL, ARQUIVO_ADESAO)
DICIONARIO = "transacoes-individual_metadados.pdf"
MODIFICADOS = "modificados.json"
ORDEM_DO_INDIVIDUAL = ["cnpj", "processo"]
ORDEM_DA_ADESAO = ["cnpj", "data_requerimento", "hash_linha"]
TEMPO_LIMITE = 120
TAMANHO_DO_PEDACO = 1 << 20
_ATUALIZADO_EM = re.compile(r"Atualizado em\s*(?:<[^>]*>\s*)*(\d{2})/(\d{2})/(\d{4})")


def data_de_atualizacao(pagina: str) -> date:
    """A data de "Atualizado em" da página do arquivo (`.../<arquivo>/view`)."""
    achado = _ATUALIZADO_EM.search(pagina)
    if not achado:
        raise RuntimeError("Receita: a página do arquivo não traz 'Atualizado em'")
    dia, mes, ano = (int(g) for g in achado.groups())
    return date(ano, mes, dia)


def baixar(destino: Path) -> dict[str, str]:
    """Baixa os arquivos para uma pasta nova e vazia e devolve a data de atualização (AAAA-MM-DD) de cada um."""
    if destino.exists() and any(destino.iterdir()):
        raise SystemExit(f"{destino} não está vazia: baixe numa pasta nova")
    destino.mkdir(parents=True, exist_ok=True)
    modificados: dict[str, str] = {}
    for nome in (*ARQUIVOS, DICIONARIO):
        resposta = rede.get_com_agente(
            f"{RAIZ}{nome}/@@download/file", timeout=TEMPO_LIMITE
        )
        resposta.raise_for_status()
        (destino / nome).write_bytes(resposta.content)
        pagina = rede.get_com_agente(f"{RAIZ}{nome}/view", timeout=TEMPO_LIMITE)
        pagina.raise_for_status()
        modificados[nome] = data_de_atualizacao(pagina.text).isoformat()
        log.info("baixado %s (atualizado em %s)", nome, modificados[nome])
    (destino / MODIFICADOS).write_text(
        json.dumps(modificados, indent=1), encoding="utf-8"
    )
    return modificados


def _origem(caminho: Path) -> dict[str, str]:
    resumo = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        while pedaco := arquivo.read(TAMANHO_DO_PEDACO):
            resumo.update(pedaco)
    return {"url": f"{RAIZ}{caminho.name}", "sha256": resumo.hexdigest()}


def _modificado_em(origem: Path, nome: str) -> date:
    registro = json.loads((origem / MODIFICADOS).read_text(encoding="utf-8"))
    return date.fromisoformat(registro[nome])


def _carregar(
    origem: Path, saida: Path, nome: str, destino: str, ordem: list[str], forcar: bool
) -> str:
    caminho = origem / nome
    leitor = (
        transacoes.ler_individual
        if nome == ARQUIVO_INDIVIDUAL
        else transacoes.ler_adesao
    )

    def montar() -> pd.DataFrame:
        contagem = transacoes.Contagem()
        with open(caminho, "rb") as fluxo:
            tabela = leitor(fluxo, _modificado_em(origem, nome), contagem)
        log.info("%s: %s", nome, contagem.para_manifesto())
        return tabela

    return gravar_com_versoes(
        montar,
        saida / "receita" / destino,
        [_origem(caminho)],
        ordem,
        forcar=forcar,
    )


def carregar_individual(origem: Path, saida: Path, forcar: bool = False) -> str:
    return _carregar(
        origem,
        saida,
        ARQUIVO_INDIVIDUAL,
        "transacoes_individual",
        ORDEM_DO_INDIVIDUAL,
        forcar,
    )


def carregar_adesao(origem: Path, saida: Path, forcar: bool = False) -> str:
    return _carregar(
        origem, saida, ARQUIVO_ADESAO, "transacoes_adesao", ORDEM_DA_ADESAO, forcar
    )


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--baixar", type=Path, default=None)
    argumentos.add_argument("--origem", type=Path, default=None)
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--forcar", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if opcoes.baixar:
        baixar(opcoes.baixar)
        return 0
    if not opcoes.origem:
        argumentos.error("passe --baixar <pasta nova> ou --origem <pasta baixada>")
    faltam = [n for n in (*ARQUIVOS, MODIFICADOS) if not (opcoes.origem / n).exists()]
    if faltam:
        log.error("faltam em %s: %s", opcoes.origem, ", ".join(faltam))
        return 1
    saida = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    individual = carregar_individual(opcoes.origem, saida, opcoes.forcar)
    adesao = carregar_adesao(opcoes.origem, saida, opcoes.forcar)
    log.info("Individual: %s; adesão: %s", individual, adesao)
    return 0
