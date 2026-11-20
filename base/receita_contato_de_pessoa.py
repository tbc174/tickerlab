"""Empresas cujo contato é o da própria pessoa, para o corte do `acervo_pessoa/contato` (ADR 0128, Emenda 4).

A regra (`AGENTS.md`, "Exceção") diz que o titular do MEI e do empresário individual sai **só com o nome**, sem
endereço e sem contato, e que a mesma regra vale para a sociedade de um sócio pessoa física só (unipessoal): o
endereço, o telefone e o e-mail do estabelecimento costumam ser os da casa e os da pessoa. A natureza 213-5
(empresário individual, da qual o MEI é um caso) já é juntada por `base/receita_individuais.py`; este módulo
junta o que faltava:

- **MEI pelo Simples:** a opção atual pelo MEI no `Simples.zip` (o optante com natureza de empresa conta também);
- **EIRELI:** as naturezas 230-5 e 231-3 da antiga empresa individual de responsabilidade limitada, que era de
  uma pessoa só;
- **quadro de um sócio só:** a raiz cujo quadro, somado em todos os `Socios*.zip` do mês, tem uma única linha
  distinta, e ela é de pessoa física (tipo 2) ou do exterior (tipo 3, que pode ser pessoa).

Leitura mais estreita (Diretoria, 18/11/2026 15h51, com o `AGENTS.md`, "Diante de dúvida, a leitura mais
estreita"): na dúvida a empresa entra no corte. Por isso a linha repetida conta uma vez e o sócio do exterior
entra. Só a raiz sai daqui, em números de 64 bits (`base/cnpj.py`); nome e documento do sócio só servem, em
memória, para saber se duas linhas são a mesma.
"""

from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd

from base import cnpj
from base.cnpj_historico import CAMPOS_NO_ARQUIVO_DE_EMPRESAS
from base.receita_natureza import COLUNA_DA_NATUREZA, COLUNA_DO_MEI, OPTANTE
from base.receita_retrato import CAMPOS_DO_SIMPLES, CAMPOS_DO_SOCIO, _partes

NATUREZAS_DA_EIRELI = frozenset({"2305", "2313"})
TIPOS_QUE_PODEM_SER_PESSOA = frozenset(
    {"2", "3"}
)  # 2: pessoa física; 3: do exterior (pessoa ou empresa)
COLUNA_DO_TIPO = 1
COLUNAS_QUE_DIZEM_QUEM_E = (
    2,
    3,
)  # nome e documento: só para reconhecer a linha repetida
VAZIO = np.array([], dtype=np.int64)


def _raizes(parte: pd.DataFrame) -> np.ndarray:
    return cnpj.raizes_em_numeros(parte[0].str.strip().str.upper())


def raizes_do_mei(arquivo_zip: Path | IO[bytes]) -> np.ndarray:
    """As raízes com a opção atual pelo MEI de um `Simples.zip`, como no `base/receita_natureza.ler_mei`, mas
    de todas as empresas (o `ler_mei` só devolve as raízes pedidas)."""
    pedacos = [
        _raizes(parte.loc[parte[COLUNA_DO_MEI].str.strip() == OPTANTE])
        for parte in _partes(arquivo_zip, CAMPOS_DO_SIMPLES, (0, COLUNA_DO_MEI))
    ]
    return np.concatenate(pedacos) if pedacos else VAZIO


def raizes_de_eireli(arquivo_zip: Path | IO[bytes]) -> np.ndarray:
    """As raízes com a natureza da antiga EIRELI de um `Empresas*.zip`."""
    pedacos = []
    for parte in _partes(
        arquivo_zip, CAMPOS_NO_ARQUIVO_DE_EMPRESAS, (0, COLUNA_DA_NATUREZA)
    ):
        natureza = parte[COLUNA_DA_NATUREZA].str.replace(r"\D", "", regex=True)
        pedacos.append(_raizes(parte.loc[natureza.isin(NATUREZAS_DA_EIRELI)]))
    return np.concatenate(pedacos) if pedacos else VAZIO


class QuadrosDeSocios:
    """Quantas linhas distintas cada raiz tem no quadro de sócios do mês, somados todos os `Socios*.zip`.

    Guarda, por linha distinta, só a raiz (número), um resumo de 64 bits da linha e se o tipo pode ser pessoa.
    """

    def __init__(self) -> None:
        self._partes: list[pd.DataFrame] = []

    def anotar(self, arquivo_zip: Path | IO[bytes]) -> None:
        posicoes = (0, COLUNA_DO_TIPO, *COLUNAS_QUE_DIZEM_QUEM_E)
        for parte in _partes(arquivo_zip, CAMPOS_DO_SOCIO, posicoes):
            tipo = parte[COLUNA_DO_TIPO].str.strip()
            linhas = pd.DataFrame(
                {
                    "raiz": _raizes(parte),
                    "linha": pd.util.hash_pandas_object(
                        parte[[COLUNA_DO_TIPO, *COLUNAS_QUE_DIZEM_QUEM_E]].apply(
                            lambda c: c.str.strip()
                        ),
                        index=False,
                    ).to_numpy(),
                    "pessoa": tipo.isin(TIPOS_QUE_PODEM_SER_PESSOA).to_numpy(),
                }
            )
            self._partes.append(linhas.drop_duplicates(["raiz", "linha"]))

    def unipessoais(self) -> np.ndarray:
        """As raízes com uma única linha distinta no quadro, e ela de quem pode ser pessoa."""
        if not self._partes:
            return VAZIO
        linhas = pd.concat(self._partes, ignore_index=True).drop_duplicates(
            ["raiz", "linha"]
        )
        por_raiz = linhas.groupby("raiz", sort=False)["pessoa"].agg(["size", "all"])
        return por_raiz.index[(por_raiz["size"] == 1) & por_raiz["all"]].to_numpy(
            dtype=np.int64
        )
