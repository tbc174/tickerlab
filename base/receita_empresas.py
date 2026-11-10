"""Leitor da tabela `Empresas` da Receita e a vista de estabelecimentos sem pessoa (linha 584 da fila).

Serve a rota `/companies` da API externa e o comando de empresa da CLI: razão social, natureza jurídica e
porte de **toda pessoa jurídica**, e uma vista dos estabelecimentos dela com atividade (CNAE), abertura,
município e UF. Desenho no plano da API externa, "Achado para a fila".

**Pessoa física fica fora (LGPD, ADR 0106):**
- a linha de empresário individual (natureza 213-5) e do grupo 4 nem sai do leitor, porque a razão social
  deles é o nome e o CPF da pessoa;
- a vista deixa de fora o MEI (opção pelo MEI no Simples), mesmo com natureza de empresa, e a raiz que não
  está na tabela de empresas (na dúvida, é pessoa);
- na razão social das outras, um CPF escrito no texto sai (`base.pessoas.sem_cpf`); também sai qualquer
  sequência de 11 ou 12 dígitos soltos, ou escrita como CPF com separadores fora do padrão (CPF colado a hífen ou com dígito a mais, achado na carga de 10/11/2026;
  CNPJ tem 14 e fica);
- a vista só tem o CNPJ, a situação, a abertura, a atividade, o município e a UF: sem logradouro, CEP,
  contato nem nome fantasia.

Layout do `Empresas*.zip` (conferido em 15/10/2026): sem cabeçalho, `;`, aspas, latin-1; básico; razão
social; natureza; qualificação; capital; porte; ente federativo. Capital, qualificação do responsável e
ente federativo não são lidos.
"""

import re
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import IO

import pandas as pd

from base.pessoas.sem_cpf import tirar_cpf_da_coluna
from base.receita_retrato import CODIFICACAO, TAMANHO_DA_PARTE, _conferir_campos
from base.rede.entidades import natureza_de_pessoa

CAMPOS_NO_ARQUIVO_DE_EMPRESAS = 7
EMPRESA = {0: "cnpj_basico", 1: "razao_social", 2: "natureza_juridica", 5: "porte"}
PORTES = {"00": "nao_informado", "01": "micro", "03": "pequeno", "05": "demais"}
COLUNAS_DA_VISTA = (
    "cnpj", "cnpj_basico", "matriz", "situacao_cadastral", "data_inicio_atividade",
    "cnae_principal", "uf", "municipio",
)  # fmt: skip


NUMERO_COMPRIDO_DE_PESSOA = re.compile(
    r"-?(?<!\d)(?:\d{11,12}|\d{3}[.\s]?\d{3}[.\s]?\d{3}[-./\s]?\d{2})(?!\d)"
)
ESPACOS = re.compile(r"\s{2,}")


def _sem_numero_de_pessoa(razao: pd.Series) -> pd.Series:
    """Tira 11 ou 12 dígitos soltos da razão social (CPF mal escrito); CNPJ (14) não é tocado."""
    limpo = razao.str.replace(NUMERO_COMPRIDO_DE_PESSOA, "", regex=True)
    return limpo.str.replace(ESPACOS, " ", regex=True).str.strip(" -")


def _empresas_pj(parte: pd.DataFrame) -> pd.DataFrame:
    natureza = parte["natureza_juridica"].str.strip()
    juridica = ~natureza.map(natureza_de_pessoa).astype(bool)
    saida = pd.DataFrame(
        {
            "cnpj_basico": parte["cnpj_basico"].str.strip(),
            "razao_social": _sem_numero_de_pessoa(
                tirar_cpf_da_coluna(parte["razao_social"].str.strip())
            ),
            "natureza_juridica": natureza,
            "porte": parte["porte"].str.strip().map(PORTES).fillna("nao_informado"),
        }
    )
    return saida[juridica].reset_index(drop=True)


def ler_empresas_pj(arquivo_zip: Path | IO[bytes]) -> Iterator[pd.DataFrame]:
    """(cnpj_basico, razao_social, natureza_juridica, porte) das pessoas jurídicas de um `Empresas*.zip`.

    Empresário individual e grupo 4 são descartados antes de qualquer coisa ser guardada. `porte` sai como
    `nao_informado`, `micro`, `pequeno` ou `demais`.
    """
    with zipfile.ZipFile(arquivo_zip) as zipado:
        (membro,) = zipado.namelist()  # cada ZIP da Receita tem um arquivo só
        _conferir_campos(zipado, membro, CAMPOS_NO_ARQUIVO_DE_EMPRESAS)
        with zipado.open(membro) as texto:
            leitor = pd.read_csv(
                texto, sep=";", header=None, dtype=str, encoding=CODIFICACAO,
                keep_default_na=False, na_values=[], chunksize=TAMANHO_DA_PARTE,
                usecols=sorted(EMPRESA),
            )  # fmt: skip
            for parte in leitor:
                yield _empresas_pj(parte.rename(columns=EMPRESA))


def estabelecimentos_sem_pessoa(
    estabelecimentos: pd.DataFrame, empresas_pj: pd.DataFrame, simples: pd.DataFrame
) -> pd.DataFrame:
    """A vista: os estabelecimentos das pessoas jurídicas que não são MEI, sem endereço fino.

    `estabelecimentos` é o retrato vigente (`base.receita_retrato.ler_estabelecimentos`), `empresas_pj` a
    saída de `ler_empresas_pj` e `simples` a de `ler_simples`. Fica só a raiz que está em `empresas_pj` (a
    que a tabela de empresas não conhece, ou é de pessoa, sai) e que não optou pelo MEI.
    """
    # prefixo sem nenhum registro no Simples (ex.: raízes 99...) chega vazio, sem colunas: ninguém é MEI
    # lá, porque todo MEI tem registro no Simples
    mei = (
        set(simples.loc[simples["optante_mei"].astype(bool), "cnpj_basico"])
        if "optante_mei" in simples.columns
        else set()
    )
    vista = estabelecimentos[
        estabelecimentos["cnpj_basico"].isin(set(empresas_pj["cnpj_basico"]))
        & ~estabelecimentos["cnpj_basico"].isin(mei)
    ]
    return vista[list(COLUNAS_DA_VISTA)].reset_index(drop=True)
