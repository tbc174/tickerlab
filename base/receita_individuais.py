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

import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import IO, NamedTuple

import pandas as pd

from base.cnpj_historico import CAMPOS_NO_ARQUIVO_DE_EMPRESAS, EMPRESA
from base.oposicao_na_tela import Opostos
from base.pessoas.sem_cpf import CPF_COM_SEPARADOR_LARGO, tirar_cpf_da_coluna
from base.receita_contato import ONZE_DIGITOS_SEPARADOS, RaizesDeIndividual
from base.receita_retrato import _partes

EMPRESARIO_INDIVIDUAL = "2135"
CPF_MASCARADO = r"\*{2,}[\d.\-]{4,}\*{0,}"  # ***982247** e variantes
COLUNAS = ("cnpj_basico", "titular", "id_pessoa")

NAO_E_INDIVIDUAL = "empresa_nao_individual"
TITULAR_SEM_NOME = "titular_sem_nome"
OPOSTO = (
    "titular_individual_oposto"  # linha 829: sai da tela, e o contato dessa raiz também
)
MOTIVOS = (NAO_E_INDIVIDUAL, TITULAR_SEM_NOME, OPOSTO)
SEPARADOR = r"[\s.\-/]?"
CPF_MASCARADO_LARGO = (
    re.compile(  # ***982247**, ***.982.247-** e parecidos: o miolo basta para o id
        rf"\*{{3}}{SEPARADOR}(\d{{3}}){SEPARADOR}(\d{{3}}){SEPARADOR}-?\*{{2}}"
    )
)


class ParteDosIndividuais(NamedTuple):
    """Um pedaço do `Empresas*.zip`: quem fica e quantas linhas saíram por motivo."""

    individuais: pd.DataFrame
    descartes: Counter[str]


def _cpf_da_razao(razao: str) -> str:
    """O último CPF escrito na razão social (mascarado ou não, em qualquer separador), só em memória."""
    mascarados = CPF_MASCARADO_LARGO.findall(razao)
    if mascarados:
        return "***" + "".join(mascarados[-1]) + "**"
    inteiros = [m.group() for m in CPF_COM_SEPARADOR_LARGO.finditer(razao)]
    digitos = re.sub(r"\D", "", inteiros[-1]) if inteiros else ""
    return digitos if len(digitos) == 11 else ""


def _individuais(
    parte: pd.DataFrame,
    opostos: Opostos,
    tiradas: set[str],
    raizes: RaizesDeIndividual | None = None,
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
    if (
        raizes is not None
    ):  # toda raiz de individual, com ou sem nome: o endereço dela é da pessoa
        raizes.juntar(fica["cnpj_basico"].str.strip().str.upper())
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
    cpf = fica.loc[com_nome, "razao_social"].map(_cpf_da_razao)
    ids = opostos.ids_de(cpf, saida["titular"])
    sem_cpf = (
        ids == ""
    )  # razão sem CPF: o id vem da raiz, para a oposição achar a linha
    ids[sem_cpf] = opostos.ids_da_raiz(saida.loc[sem_cpf, "cnpj_basico"])
    saida["id_pessoa"] = ids
    oposto = opostos.marcar(saida["id_pessoa"])
    descartes[OPOSTO] += int(oposto.sum())
    tiradas.update(
        saida.loc[oposto, "cnpj_basico"]
    )  # o contato dessas raízes também sai
    return ParteDosIndividuais(saida.loc[~oposto].reset_index(drop=True), +descartes)


def ler_individuais(
    arquivo_zip: Path | IO[bytes],
    opostos: Opostos,
    tiradas: set[str],
    raizes: RaizesDeIndividual | None = None,
) -> Iterator[ParteDosIndividuais]:
    """O titular dos empresários individuais de um `Empresas*.zip`, em partes, com os descartes.

    Quem tem oposição registrada (`opostos`) não entra, e a raiz dele vai para `tiradas`: o contato da raiz,
    que é o da própria pessoa, também sai (`base/receita_contato.py`). `raizes` recebe toda raiz de empresário
    individual e MEI, até a sem nome: o contato dela só vai até o município e a UF (linha 859).
    """
    for parte in _partes(arquivo_zip, CAMPOS_NO_ARQUIVO_DE_EMPRESAS, EMPRESA):
        yield _individuais(parte, opostos, tiradas, raizes)
