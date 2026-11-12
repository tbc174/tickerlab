"""O leitor do `acervo_pessoa/` para a tela da equipe (ADR 0128, Emenda 1; linha 808).

É o único lugar do app que lê pessoa física. A pasta fica **fora da base** (`TICKERLAB_ACERVO_PESSOA`), não
passa pela Porta nem pelo portão da API por chave, e é montada em casa por `scripts/montar_acervo_pessoa.py`
(sem CPF e sem menor de idade). Quem decide se a conta pode ver é a rota, antes de chamar este módulo
(`src/banco/membros_da_organizacao.py`): aqui não há permissão, só leitura.

Do arquivo de sócios saem **só** o nome do sócio, a qualificação e a data de entrada; do arquivo de contato,
**só** o endereço, os telefones e o e-mail de cada estabelecimento ativo. As colunas são escolhidas pelo
nome, então uma coluna a mais no arquivo nunca chega à tela.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from base import cnpj as cnpj_
from base import receita_codigos, receita_contato

VARIAVEL = "TICKERLAB_ACERVO_PESSOA"
SOCIOS = "socios_pf"
CONTATO = "contato"
MANIFESTO = "manifesto.json"
TAMANHO_DA_RAIZ = 8
PREFIXO = (
    2  # o arquivo de cada raiz é o dos 2 primeiros caracteres (como o montador reparte)
)
MAXIMO_DE_SOCIOS = 100  # a tela mostra até aqui e diz que há mais
MAXIMO_DE_ESTABELECIMENTOS = 20  # o pedido, a matriz e as primeiras filiais
COLUNAS_DO_CONTATO = [
    "cnpj_basico", "cnpj", "matriz", "tipo_logradouro", "logradouro", "numero", "complemento",
    "bairro", "cep", "municipio", "uf", "telefone_1", "telefone_2", "email", "mes_do_retrato",
]  # fmt: skip
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
ATRIBUICAO_DO_CONTATO = (
    "Receita Federal, dados abertos do CNPJ (cadastro dos estabelecimentos)"
)
LIMITES_DO_CONTATO = (
    "Endereço, telefone e e-mail como a empresa declarou à Receita no mês do retrato: podem ter mudado.",
    "Só estabelecimentos ativos. Sem nome fantasia e sem fax.",
    "No MEI e no empresário individual o endereço aparece só até o município e a UF; o telefone costuma ser o da própria pessoa.",
    "Use só para o contato profissional com a empresa.",
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


@dataclass(frozen=True)
class Contato:
    """O contato dos estabelecimentos ativos de uma empresa, em tipos simples, e o mês do retrato."""

    estabelecimentos: list[dict[str, str | bool | list[str] | None]]
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


def _cnpj(cnpj: str) -> str:
    normalizado = cnpj_.normalizar_cnpj(cnpj)
    if not normalizado:
        raise CnpjInvalidoError("CNPJ inválido")
    return normalizado


def _linhas_da_raiz(pasta: Path, tabela: str, raiz: str, colunas: list[str]) -> list:
    """As linhas da raiz na tabela, só com as colunas pedidas; sem o arquivo do prefixo, nenhuma."""
    if not (pasta / tabela).is_dir():
        raise AcervoIndisponivelError("tabela do acervo de pessoa fora deste servidor")
    arquivo = pasta / tabela / f"{raiz[:PREFIXO]}.parquet"
    if not arquivo.is_file():
        return []
    try:
        lida = pq.read_table(
            arquivo, columns=colunas, filters=[("cnpj_basico", "=", raiz)]
        )
    except (pa.ArrowException, OSError) as erro:
        raise AcervoIndisponivelError("acervo de pessoa ilegível") from erro
    return lida.to_pylist()


def socios_da_empresa(pasta: Path, cnpj: str) -> Socios:
    """Os sócios pessoa física adultos da empresa do CNPJ, do mais antigo ao mais novo.

    `CnpjInvalidoError` se o CNPJ é inválido; `AcervoIndisponivelError` se o arquivo não pôde ser lido.
    Empresa sem sócio pessoa física no acervo: lista vazia.
    """
    raiz = _cnpj(cnpj)[:TAMANHO_DA_RAIZ]
    linhas = [
        linha
        for linha in _linhas_da_raiz(pasta, SOCIOS, raiz, COLUNAS)
        if linha["nome_socio"]
    ]
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


def _logradouro(linha: dict) -> str | None:
    rua = " ".join(p for p in (linha["tipo_logradouro"], linha["logradouro"]) if p)
    partes = [p for p in (rua, linha["numero"], linha["complemento"]) if p]
    return ", ".join(partes) or None


def _estabelecimento(linha: dict) -> dict[str, str | bool | list[str] | None]:
    codigo = linha["municipio"]
    return {
        "cnpj": linha["cnpj"],
        "matriz": bool(linha["matriz"]),
        "logradouro": _logradouro(linha),
        "bairro": linha["bairro"],
        "cep": linha["cep"],
        "municipio": receita_codigos.municipio(codigo) or codigo,
        "uf": linha["uf"],
        "telefones": [t for t in (linha["telefone_1"], linha["telefone_2"]) if t],
        "email": linha["email"],
    }


def _exigir_corte_do_endereco(pasta: Path) -> None:
    """Só serve contato de um acervo montado com o corte do endereço de MEI e de empresário individual
    (linha 859): o manifesto da montagem conta o motivo `endereco_de_individual_cortado`. Acervo anterior
    ainda teria a rua de toda pessoa; o servidor o trata como fora do ar até a montagem nova."""
    try:
        manifesto = json.loads((pasta / MANIFESTO).read_text(encoding="utf-8"))
        marcado = receita_contato.ENDERECO_CORTADO in manifesto["descartes"]
    except (OSError, ValueError, KeyError, TypeError) as erro:
        raise AcervoIndisponivelError(
            "manifesto do acervo de pessoa ilegível"
        ) from erro
    if not marcado:
        raise AcervoIndisponivelError(
            "acervo de pessoa sem o corte do endereço de individual"
        )


def contato_da_empresa(pasta: Path, cnpj: str) -> Contato:
    """O contato dos estabelecimentos ativos da empresa do CNPJ: o pedido primeiro, depois a matriz e as
    filiais, pela ordem do CNPJ.

    `CnpjInvalidoError` se o CNPJ é inválido; `AcervoIndisponivelError` se a tabela não está neste servidor
    ou não pôde ser lida. Empresa sem estabelecimento ativo no acervo: lista vazia.
    """
    pedido = _cnpj(cnpj)
    _exigir_corte_do_endereco(pasta)
    linhas = _linhas_da_raiz(
        pasta, CONTATO, pedido[:TAMANHO_DA_RAIZ], COLUNAS_DO_CONTATO
    )
    linhas.sort(key=lambda e: (e["cnpj"] != pedido, not e["matriz"], e["cnpj"]))
    mes = linhas[0]["mes_do_retrato"] if linhas else None
    mostrados = linhas[:MAXIMO_DE_ESTABELECIMENTOS]
    return Contato([_estabelecimento(linha) for linha in mostrados], len(linhas), mes)
