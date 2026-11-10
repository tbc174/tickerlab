"""O leitor do `acervo_pessoa/` para a tela da equipe (ADR 0128, Emenda 1; linha 808).

É o único lugar do app que lê pessoa física. A pasta fica **fora da base** (`TICKERLAB_ACERVO_PESSOA`), não
passa pela Porta nem pelo portão da API por chave, e é montada em casa por `scripts/montar_acervo_pessoa.py`
(sem CPF e sem menor de idade). Quem decide se a conta pode ver é a rota, antes de chamar este módulo
(`src/banco/membros_da_organizacao.py`): aqui não há permissão, só leitura.

Do arquivo saem **só** o nome do sócio, a qualificação e a data de entrada: as colunas são escolhidas pelo
nome, então uma coluna a mais no arquivo nunca chega à tela.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from base import cnpj as cnpj_
from base import receita_codigos

VARIAVEL = "TICKERLAB_ACERVO_PESSOA"
SOCIOS = "socios_pf"
TAMANHO_DA_RAIZ = 8
PREFIXO = (
    2  # o arquivo de cada raiz é o dos 2 primeiros caracteres (como o montador reparte)
)
MAXIMO_DE_SOCIOS = 100  # a tela mostra até aqui e diz que há mais
COLUNAS = ["cnpj_basico", "nome_socio", "qualificacao", "data_entrada", "mes_do_retrato"]  # fmt: skip
FONTE = "rfb-cnpj"
ATRIBUICAO = (
    "Receita Federal, dados abertos do CNPJ (quadro de sócios e administradores)"
)
LIMITES = (
    "Sócios pessoa física do quadro da Receita Federal no mês do retrato: mudança posterior não aparece.",
    "Só adultos: menor de idade, incapaz, quem tem representante legal e sócio do exterior ficam de fora.",
    "Sem CPF. Sócio que é empresa está no cadastro da ficha, não nesta lista.",
    "Nome igual não prova que é a mesma pessoa em duas empresas.",
)


class AcervoIndisponivelError(RuntimeError):
    """O acervo de pessoa não está neste servidor (sem a variável, sem a pasta) ou não pôde ser lido."""


class CnpjInvalidoError(ValueError):
    """O texto pedido não tem a forma de um CNPJ."""


@dataclass(frozen=True)
class Socios:
    """Os sócios pessoa física de uma empresa, em tipos simples, e de que mês é o retrato."""

    socios: list[dict[str, str | None]]
    total: int
    mes_do_retrato: str | None


def pasta_do_acervo() -> Path:
    """A pasta do acervo de pessoa neste servidor; `AcervoIndisponivelError` se não há."""
    caminho = os.environ.get(VARIAVEL, "").strip()
    if not caminho or not (Path(caminho) / SOCIOS).is_dir():
        raise AcervoIndisponivelError("acervo de pessoa fora deste servidor")
    return Path(caminho)


def _linha(linha: dict) -> dict[str, str | None]:
    codigo = linha["qualificacao"]
    entrada = linha["data_entrada"]
    return {
        "nome": linha["nome_socio"],
        "qualificacao": receita_codigos.qualificacao(codigo) or codigo,
        "entrou_em": None if entrada is None else entrada.date().isoformat(),
    }


def socios_da_empresa(pasta: Path, cnpj: str) -> Socios:
    """Os sócios pessoa física adultos da empresa do CNPJ, do mais antigo ao mais novo.

    `CnpjInvalidoError` se o CNPJ é inválido; `AcervoIndisponivelError` se o arquivo não pôde ser lido.
    Empresa sem sócio pessoa física no acervo: lista vazia.
    """
    normalizado = cnpj_.normalizar_cnpj(cnpj)
    if not normalizado:
        raise CnpjInvalidoError("CNPJ inválido")
    raiz = normalizado[:TAMANHO_DA_RAIZ]
    arquivo = pasta / SOCIOS / f"{raiz[:PREFIXO]}.parquet"
    if not arquivo.is_file():
        return Socios([], 0, None)
    try:
        tabela = pq.read_table(
            arquivo, columns=COLUNAS, filters=[("cnpj_basico", "=", raiz)]
        )
    except (pa.ArrowException, OSError) as erro:
        raise AcervoIndisponivelError("acervo de pessoa ilegível") from erro
    linhas = [linha for linha in tabela.to_pylist() if linha["nome_socio"]]
    linhas.sort(
        key=lambda s: (
            s["data_entrada"] is None,
            s["data_entrada"] or 0,
            s["nome_socio"],
        )
    )
    mes = linhas[0]["mes_do_retrato"] if linhas else None
    return Socios(
        [_linha(linha) for linha in linhas[:MAXIMO_DE_SOCIOS]], len(linhas), mes
    )
