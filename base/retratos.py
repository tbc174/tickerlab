"""Cadastros que a fonte publica inteiros a cada vez (um **retrato**): o arquivista guarda cada arquivo
novo, e aqui os retratos viram uma tabela que só cresce, com uma linha por valor diferente de cada
registro (`base/sancoes.py`; as licenças vêm a seguir).

- O valor que muda num retrato seguinte vira linha nova, e o registro que some do arquivo ganha uma
  linha `consta=False` no dia em que sumiu (e outra `True` se voltar). `base/setoriais/revisoes.py`
  (`como_era_em`) devolve o estado num dia.
- **Sem olhar o futuro** (`disponivel_em`): o que aparece ou muda num retrato seguinte vale desde o
  dia dele; o primeiro retrato usa a regra de cada cadastro (a data que a fonte publica), nunca depois
  do dia do retrato.
- Retrato com menos da metade dos registros do anterior é arquivo cortado da fonte e é pulado.

Lê só o que o arquivista já guardou (não baixa nada).
"""

import gzip
import re
import unicodedata
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from src import acervo
from src.banco.coletas import originais_mais_recentes, versoes_guardadas

FRACAO_MINIMA = (
    0.5  # retrato com menos que isto dos registros do anterior é arquivo cortado
)
SEPARADOR_DA_CHAVE = "|"
FORA_DO_NOME = re.compile(r"[^A-Z0-9]")
# o que cada linha ganha do retrato onde foi vista (não conta para saber se o valor mudou)
CARIMBOS = ["disponivel_em", "visto_em", "origem_sha256", "origem_coletada_em"]

# a data em que cada registro do primeiro retrato passa a valer (o dia dele é o 2º argumento)
DisponivelNoPrimeiro = Callable[[pd.DataFrame, pd.Timestamp], pd.Series]


@dataclass(frozen=True)
class Retrato:
    """Um arquivo guardado do cadastro: o conteúdo de um endereço baixado pela primeira vez num dia."""

    url: str
    sha256: str
    caminho: Path
    baixado_em: datetime

    @property
    def dia(self) -> date:
        return pd.Timestamp(self.baixado_em).date()


def nome_da_coluna(coluna: str) -> str:
    """O nome da coluna sem acento, maiúsculo, só letras e números (a CGU troca travessão e espaço)."""
    sem_acento = (
        unicodedata.normalize("NFKD", coluna).encode("ascii", "ignore").decode()
    )
    return FORA_DO_NOME.sub("", sem_acento.upper())


def csv_do_zip(arquivo: zipfile.ZipFile, membro: str | None) -> str:
    """O nome do CSV dentro do ZIP: o primeiro, ou o primeiro com `membro` no nome."""
    csvs = [n for n in arquivo.namelist() if n.lower().endswith(".csv")]
    if membro is not None:
        csvs = [n for n in csvs if membro in n.lower()]
    if not csvs:
        raise ValueError(f"nenhum CSV com {membro!r} no ZIP")
    return csvs[0]


def original(caminho: Path) -> bytes:
    """O arquivo como veio da fonte: o acervo guarda em `.gz` o que não vem comprimido (o endereço da
    CGU não termina em `.zip`, então o ZIP dela fica dentro de um `.bin.gz`). Os maiores têm dezenas
    de MB: cabem na memória."""
    guardado = caminho.read_bytes()
    return gzip.decompress(guardado) if caminho.name.endswith(".gz") else guardado


def sem_vazio(texto: pd.Series) -> pd.Series:
    """O texto vazio da fonte vira nulo (o `replace("", None)` do pandas preenche com o de cima)."""
    return texto.where(texto.ne(""), None)


def chave(tabela: pd.DataFrame, colunas: Sequence[str]) -> pd.Series:
    """O identificador do registro dentro de um retrato: as colunas juntas por `|`."""
    primeira, *outras = colunas
    if not outras:
        return tabela[primeira].astype(str)
    return tabela[primeira].str.cat([tabela[c] for c in outras], sep=SEPARADOR_DA_CHAVE)


def retratos(
    conexao: sa.Connection, fonte: str, url_termina_em: str | None = None
) -> list[Retrato]:
    """Os arquivos da fonte guardados no acervo, do mais antigo ao mais novo.

    `url_termina_em`: só os endereços que terminam assim (a fonte guarda outros arquivos além deste).
    """
    pasta = acervo.pasta_do_acervo()
    if pasta is None:
        return []
    achados = [
        Retrato(original.url, versao.sha256, pasta / versao.caminho, versao.baixado_em)
        for original in originais_mais_recentes(conexao, fonte)
        if not url_termina_em or original.url.endswith(url_termina_em)
        for versao in versoes_guardadas(conexao, original.url)
        if (pasta / versao.caminho).is_file()
    ]
    return sorted(achados, key=lambda r: (pd.Timestamp(r.baixado_em), r.url))


def _assinatura(tabela: pd.DataFrame, valores: Sequence[str]) -> pd.Series:
    return pd.util.hash_pandas_object(tabela[list(valores)], index=False)


def _novos(
    atual: pd.DataFrame, ultimo: pd.DataFrame, valores: Sequence[str]
) -> pd.DataFrame:
    """O que mudou desde o último valor de cada registro, com os que saíram como `consta=False`."""
    presentes = ultimo[ultimo["consta"]]
    saidas = presentes[~presentes["id_na_fonte"].isin(atual["id_na_fonte"])].assign(
        consta=False
    )
    candidatos = pd.concat([atual, saidas[atual.columns]], ignore_index=True)
    # compara os números de 64 bits como vieram: um `map` com registro novo os passaria a decimal
    anterior = pd.Series(
        _assinatura(ultimo, valores).to_numpy(), index=ultimo["id_na_fonte"]
    )
    assinaturas = _assinatura(candidatos, valores).to_numpy()
    conhecida = candidatos["id_na_fonte"].isin(anterior.index).to_numpy()
    mudou = ~conhecida
    posicoes = np.flatnonzero(conhecida)
    mudou[posicoes] = (
        anterior.loc[candidatos["id_na_fonte"].iloc[posicoes]].to_numpy()
        != assinaturas[posicoes]
    )
    return candidatos[mudou]


def juntar(
    lidos: list[tuple[Retrato, pd.DataFrame]],
    valores: Sequence[str],
    disponivel_no_primeiro: DisponivelNoPrimeiro,
) -> tuple[pd.DataFrame, int]:
    """Os retratos lidos (do mais antigo ao mais novo) numa tabela de valores, e quantos foram pulados.

    Cada tabela lida tem `id_na_fonte` (único no retrato) e as colunas de `valores` (as que contam
    para saber se o registro mudou; `consta` entra nelas). O primeiro retrato nunca é pulado: é ele
    que dá a régua dos seguintes."""
    if not lidos:
        raise ValueError("nenhum retrato para juntar")
    eventos: list[pd.DataFrame] = []
    ultimo: pd.DataFrame | None = None
    pulados = 0
    for retrato, tabela in lidos:
        dia = pd.Timestamp(retrato.dia)
        atual = tabela.assign(consta=True)
        if ultimo is None:
            novos = atual.assign(disponivel_em=disponivel_no_primeiro(atual, dia))
        else:
            if len(atual) < FRACAO_MINIMA * int(ultimo["consta"].sum()):
                pulados += 1
                continue
            novos = _novos(atual, ultimo.drop(columns=CARIMBOS), valores).assign(
                disponivel_em=dia
            )
        novos = novos.assign(
            visto_em=dia,
            origem_sha256=retrato.sha256,
            origem_coletada_em=pd.Timestamp(retrato.baixado_em).isoformat(),
        )
        eventos.append(novos)
        ultimo = (
            novos
            if ultimo is None
            else pd.concat([ultimo, novos], ignore_index=True).drop_duplicates(
                "id_na_fonte", keep="last"
            )
        )
    return pd.concat(eventos, ignore_index=True), pulados
