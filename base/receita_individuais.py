"""Titular do empresário individual e do MEI, no cadastro da Receita, para a tela da equipe (linha 808, PR 4).

A razão social do empresário individual (natureza jurídica 213-5, da qual o MEI é um caso) é o nome da
própria pessoa, com o CPF no fim. O retrato da base nunca a guarda (`base/cnpj_historico.py` a deixa vazia);
este leitor **separado** só alimenta a pasta `acervo_pessoa/`, lida pela tela com login de organização com a
permissão `pessoa_na_tela` (ADR 0128, Emenda 1).

**O que sai:** a raiz do CNPJ e o nome do titular, sem o CPF. **O que nunca sai:** CPF (inteiro, pontuado,
mascarado, com qualquer separador entre os dígitos), qualquer outra natureza jurídica (sociedade não é
pessoa) e o nome que, sem o CPF, sobra vazio ou só com números. O arquivo não traz a idade do titular: um
titular menor emancipado não é detectável aqui (pendência de regra levada à Diretoria no PR).
"""

from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import IO, NamedTuple

import pandas as pd

from base.cnpj_historico import CAMPOS_NO_ARQUIVO_DE_EMPRESAS, EMPRESA
from base.oposicao_na_tela import Opostos
from base.pessoas.sem_cpf import tirar_cpf_da_coluna
from base.receita_contato import ONZE_DIGITOS_SEPARADOS
from base.receita_retrato import _partes

EMPRESARIO_INDIVIDUAL = "2135"
CPF_MASCARADO = r"\*{2,}[\d.\-]{4,}\*{0,}"  # ***982247** e variantes
COLUNAS = ("cnpj_basico", "titular")

NAO_E_INDIVIDUAL = "empresa_nao_individual"
TITULAR_SEM_NOME = "titular_sem_nome"
OPOSTO = (
    "titular_individual_oposto"  # linha 829: sai da tela, e o contato dessa raiz também
)
MOTIVOS = (NAO_E_INDIVIDUAL, TITULAR_SEM_NOME, OPOSTO)
CPF_NA_RAZAO = r"\*{3}\d{6}\*{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2}"  # o CPF no fim da razão social, só em memória


class ParteDosIndividuais(NamedTuple):
    """Um pedaço do `Empresas*.zip`: quem fica e quantas linhas saíram por motivo."""

    individuais: pd.DataFrame
    descartes: Counter[str]


def _individuais(
    parte: pd.DataFrame, opostos: Opostos, tiradas: set[str]
) -> ParteDosIndividuais:
    parte = parte.rename(columns=EMPRESA)
    individual = (
        parte["natureza_juridica"]
        .str.strip()
        .str.replace(r"\D", "", regex=True)
        .eq(EMPRESARIO_INDIVIDUAL)
    )
    descartes: Counter[str] = Counter({NAO_E_INDIVIDUAL: int((~individual).sum())})
    fica = parte.loc[individual].copy()
    nome = tirar_cpf_da_coluna(fica["razao_social"].str.strip())
    nome = nome.str.replace(CPF_MASCARADO, " ", regex=True)
    nome = nome.str.replace(ONZE_DIGITOS_SEPARADOS, " ", regex=True)
    nome = nome.str.replace(r"\s{2,}", " ", regex=True).str.strip()
    com_nome = nome.str.contains(r"[^\W\d_]", regex=True)  # ao menos uma letra
    descartes[TITULAR_SEM_NOME] += int((~com_nome).sum())
    saida = pd.DataFrame(
        {
            "cnpj_basico": fica["cnpj_basico"].str.strip().str.upper(),
            "titular": nome,
        }
    )
    saida = saida.loc[com_nome]
    cpf = fica.loc[com_nome, "razao_social"].str.findall(CPF_NA_RAZAO).str[-1]
    cpf = cpf.fillna("")
    oposto = opostos.marcar(cpf, saida["titular"])
    descartes[OPOSTO] += int(oposto.sum())
    tiradas.update(
        saida.loc[oposto, "cnpj_basico"]
    )  # o contato dessas raízes também sai
    return ParteDosIndividuais(saida.loc[~oposto].reset_index(drop=True), +descartes)


def ler_individuais(
    arquivo_zip: Path | IO[bytes], opostos: Opostos, tiradas: set[str]
) -> Iterator[ParteDosIndividuais]:
    """O titular dos empresários individuais de um `Empresas*.zip`, em partes, com os descartes.

    Quem tem oposição registrada (`opostos`) não entra, e a raiz dele vai para `tiradas`: o contato da raiz,
    que é o da própria pessoa, também sai (`base/receita_contato.py`).
    """
    for parte in _partes(arquivo_zip, CAMPOS_NO_ARQUIVO_DE_EMPRESAS, EMPRESA):
        yield _individuais(parte, opostos, tiradas)
