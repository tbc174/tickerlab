"""Oposição do titular na tela da equipe (LGPD, art. 18, § 2º; linha 829; ADR 0128, Emenda 1).

A política de privacidade promete que quem se opôs sai também da tela da organização em 15 dias. A oposição
(`base/pessoas/oposicoes.py`) guarda só o `id_pessoa`: o HMAC do meio do CPF e do primeiro e do último nome.
A montagem do `acervo_pessoa` calcula esse mesmo id de cada sócio (do CPF mascarado do `Socios*.zip`) e de
cada titular de empresário individual (do CPF no fim da razão social), **só na memória**: o CPF nunca é
gravado nem sai daqui. Quem tem id com oposição, atendida ou não, fica fora do acervo.

Falha fechada: sem a pasta restrita ou sem a chave, nada é montado (`SemOposicoesError`, `ErroSemChave`).
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from base.parquet import gravar_atomico
from base.pessoas import chave as chaves
from base.pessoas import oposicoes
from base.porta import pessoas as porta

log = logging.getLogger(__name__)


class SemOposicoesError(RuntimeError):
    """A pasta restrita, onde estão as oposições, não existe neste servidor."""


class SemAcervoError(RuntimeError):
    """O `--acervo-pessoa` não aponta para um acervo montado com os ids."""


@dataclass(frozen=True)
class Opostos:
    """Os ids com oposição registrada e a chave para calcular o id de quem entra no acervo."""

    ids: frozenset[str]
    chave: bytes = field(repr=False)  # nunca no log nem no texto de erro

    def _id(self, documento: str, nome: str) -> str:
        try:
            primeiro, ultimo = chaves.primeiro_e_ultimo(nome)
            return chaves.id_pessoa(documento, primeiro, ultimo, self.chave)
        except (
            ValueError
        ):  # CPF malformado ou nome vazio: sem id, a pessoa não tem como se opor
            return ""

    def ids_de(self, documentos: pd.Series, nomes: pd.Series) -> pd.Series:
        """O `id_pessoa` de cada linha (vazio quando não dá para calcular). Fica no acervo para a
        oposição de amanhã valer sem refazer a montagem (`oposicoes.aplicar_no_acervo`)."""
        ids = [self._id(d, n) for d, n in zip(documentos, nomes, strict=True)]
        return pd.Series(ids, index=documentos.index, dtype=object)

    def ids_da_raiz(self, raizes: pd.Series) -> pd.Series:
        """O id de quem não tem CPF na razão social: sai da raiz do CNPJ (`chaves.id_da_raiz`)."""
        return raizes.map(lambda raiz: chaves.id_da_raiz(raiz, self.chave)).astype(
            object
        )

    def marcar(self, ids: pd.Series) -> pd.Series:
        """Verdadeiro para quem tem oposição registrada."""
        return ids.isin(self.ids) & (ids != "")


def carregar(restrita: Path) -> Opostos:
    """As oposições da pasta restrita e a chave do pseudônimo; recusa pasta ou chave ausentes."""
    if not (restrita / porta.PASTA_DAS_PESSOAS).is_dir():  # a pasta-mãe errada não vale
        raise SemOposicoesError("pasta restrita de pessoas ausente")
    return Opostos(frozenset(oposicoes.ids_opostos(restrita)), chaves.ler_chave())


# ------------------------------------------------------------------ oposição de depois da montagem

SOCIOS = (
    "socios_pf"  # as pastas do `acervo_pessoa/` (a montagem usa estes mesmos nomes)
)
INDIVIDUAIS = "individuais"
CONTATO = "contato"


def _regravar(arquivo: Path, tabela: pd.DataFrame) -> None:
    gravar_atomico(arquivo, lambda caminho: tabela.to_parquet(caminho, index=False))


def aplicar_no_acervo(acervo_pessoa: Path, ids: set[str]) -> int:
    """Tira do `acervo_pessoa/` já montado quem tem oposição (idempotente): o sócio, o titular do
    individual e o contato da raiz dele. Faz a oposição valer no dia, sem esperar a montagem do mês
    seguinte (prazo de 15 dias da política). Devolve quantas linhas saíram; só contagem."""
    exigir_acervo(acervo_pessoa)
    if not ids:
        return 0
    tiradas = 0
    raizes: set[str] = (
        set()
    )  # lidas antes de regravar qualquer coisa: queda no meio não as perde
    for arquivo in sorted((acervo_pessoa / INDIVIDUAIS).glob("*.parquet")):
        linhas = pd.read_parquet(arquivo, columns=["cnpj_basico", "id_pessoa"])
        raizes.update(linhas.loc[linhas["id_pessoa"].isin(ids), "cnpj_basico"])
    for arquivo in sorted(
        (acervo_pessoa / CONTATO).glob("*.parquet")
    ):  # contato primeiro
        linhas = pd.read_parquet(arquivo)
        do_oposto = linhas["cnpj_basico"].isin(raizes)
        if do_oposto.any():
            _regravar(arquivo, linhas.loc[~do_oposto].reset_index(drop=True))
            tiradas += int(do_oposto.sum())
    for tabela in (INDIVIDUAIS, SOCIOS):
        for arquivo in sorted((acervo_pessoa / tabela).glob("*.parquet")):
            linhas = pd.read_parquet(arquivo)
            oposto = linhas["id_pessoa"].isin(ids)
            if oposto.any():
                _regravar(arquivo, linhas.loc[~oposto].reset_index(drop=True))
                tiradas += int(oposto.sum())
    log.info("oposição no acervo de pessoa: %d linha(s) tirada(s)", tiradas)
    return tiradas


def exigir_acervo(acervo_pessoa: Path) -> None:
    """Recusa um `--acervo-pessoa` que não é um `acervo_pessoa/` montado com os ids (caminho errado
    ou montagem antiga): sem isto a oposição pareceria aplicada e a pessoa continuaria na tela."""
    pasta = acervo_pessoa / SOCIOS
    if not pasta.is_dir() or not any(pasta.glob("*.parquet")):
        raise SemAcervoError("acervo_pessoa ausente ou vazio: confira o caminho")
    amostra = pd.read_parquet(next(iter(sorted(pasta.glob("*.parquet")))))
    if "id_pessoa" not in amostra.columns:
        raise SemAcervoError(
            "acervo_pessoa montado antes da coluna id_pessoa: monte de novo"
        )


def restantes(acervo_pessoa: Path, ids: set[str]) -> int:
    """Quantas linhas de quem tem oposição ainda estão no acervo (sócio, titular do individual e o contato
    da raiz dele). Deve ser zero depois do `aplicar_no_acervo`; só contagem, nunca o conteúdo."""
    exigir_acervo(acervo_pessoa)
    if not ids:
        return 0
    total = 0
    raizes: set[str] = set()
    for tabela in (INDIVIDUAIS, SOCIOS):
        for arquivo in sorted((acervo_pessoa / tabela).glob("*.parquet")):
            linhas = pd.read_parquet(arquivo)
            oposto = linhas["id_pessoa"].isin(ids)
            total += int(oposto.sum())
            if tabela == INDIVIDUAIS:
                raizes.update(linhas.loc[oposto, "cnpj_basico"])
    for arquivo in sorted((acervo_pessoa / CONTATO).glob("*.parquet")):
        total += int(pd.read_parquet(arquivo)["cnpj_basico"].isin(raizes).sum())
    return total


def tem_na_tela(acervo_pessoa: Path, cnpj: str, ids: list[str]) -> tuple[int, int]:
    """Quantas linhas de titular de individual e de contato a base guarda desta raiz para estes ids
    (direito de acesso, LGPD art. 18, I e II). Só contagem."""
    exigir_acervo(acervo_pessoa)
    raiz = oposicoes.raiz_do_cnpj(cnpj)
    titular = contato = 0
    for arquivo in sorted((acervo_pessoa / INDIVIDUAIS).glob("*.parquet")):
        linhas = pd.read_parquet(arquivo, filters=[("cnpj_basico", "=", raiz)])
        titular += int(linhas["id_pessoa"].isin(ids).sum())
    if titular:
        for arquivo in sorted((acervo_pessoa / CONTATO).glob("*.parquet")):
            linhas = pd.read_parquet(arquivo, filters=[("cnpj_basico", "=", raiz)])
            contato += len(linhas)
    return titular, contato


def achar_titular_individual(acervo_pessoa: Path, cnpj: str, nome: str) -> list[str]:
    """Os `id_pessoa` do titular de um empresário individual ou MEI (que não está no quadro de sócios),
    achado na tabela `individuais` pela raiz do CNPJ e pelo nome como a Receita publica."""
    exigir_acervo(acervo_pessoa)
    raiz = oposicoes.raiz_do_cnpj(cnpj)
    alvo = chaves.normalizar_nome(nome)
    ids: set[str] = set()
    for arquivo in sorted((acervo_pessoa / INDIVIDUAIS).glob("*.parquet")):
        linhas = pd.read_parquet(arquivo, filters=[("cnpj_basico", "=", raiz)])
        achados = linhas[linhas["titular"].map(chaves.normalizar_nome) == alvo]
        ids.update(i for i in achados["id_pessoa"] if i)
    return sorted(ids)
