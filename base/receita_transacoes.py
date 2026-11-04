"""Transações tributárias da Receita Federal (linha 661 da fila, rodada de fontes de 03/11/2026): os acordos
individuais deferidos e as adesões às modalidades de transação (PRLF 2023, editais, Litígio Zero).

- **Individual:** `transacoes-individual.csv`, `;`, UTF-8 com BOM, CRLF, 9 colunas (`Contribuinte, CNPJ/CPF,
  Processo, Data, Dívida transacionada, Redução, Dívida com redução, Créditos PF/BCN, Saldo devedor`), valores
  em reais inteiros com ponto de milhar (`1.890.254.972`), data só `mmm/aa` (`out/23`). 46 linhas, 2 delas com
  CPF mascarado. **Chave:** CNPJ + processo (única nas 44 de CNPJ; conferida a cada leitura).
- **Adesão:** `transacoes-adesao.csv`, `;`, latin-1, 10 colunas (`CPF/CNPJ, Modalidade, Data de requerimento,
  Dívida sem redução, Redução, Crédito PF próprio, Crédito PF terceiros, Crédito BCN próprio, Crédito BCN
  terceiros, Quantidade de parcelas`), valor com vírgula decimal, data `dd/mm/aaaa`. 10.974 linhas, 67% com CPF
  mascarado. **Sem chave natural** (CNPJ + modalidade + data repete em 70 casos): cada linha ganha o `hash_linha`
  (SHA-256 do conteúdo, com o número de ordem entre as linhas idênticas, para ser único e estável). É uma
  tabela de eventos; a unicidade vem do hash, não do negócio.
- **Pessoa física nunca entra:** a linha cujo primeiro campo não é um CNPJ formatado completo (CPF mascarado,
  CPF inteiro, qualquer outra coisa) é descartada na leitura e só contada. Nem o nome do contribuinte dessas
  linhas é guardado.

**Sem olhar o futuro:** nenhum dos dois arquivos traz a data de publicação por linha, e a Receita não manda o
`Last-Modified` no cabeçalho do download. `disponivel_em` é a data de "Atualizado em" da página do arquivo
(individual: 28/07/2026; adesão: 13/10/2026), que quem chama passa. O período de referência (`data_acordo`,
`data_requerimento`) fica em coluna à parte. A Receita regrava o arquivo inteiro: o de hoje vale a partir de hoje.

**Licença:** a confirmar, só uso interno (ADR 0102, Emenda 2); nada foi perguntado à fonte.

Sem Streamlit; pandas só.
"""

import csv
import hashlib
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date

import pandas as pd

FONTE_INDIVIDUAL = "receita-transacoes-individual"
FONTE_ADESAO = "receita-transacoes-adesao"
ATRIBUICAO = "Fonte: Receita Federal do Brasil, dados abertos (transações tributárias)."
AVISO = (
    "Os acordos individuais mostram só as maiores negociações deferidas; as adesões listam o que cada "
    "contribuinte pediu, não o que foi pago. Pessoa física fica de fora."
)
CODIFICACOES = ("utf-8", "latin-1")

COLUNAS_DO_INDIVIDUAL = (
    "contribuinte", "cnpj", "processo", "data_acordo", "divida_transacionada", "reducao",
    "divida_com_reducao", "creditos_pf_bcn", "saldo_devedor",
)  # fmt: skip
CHAVE_DO_INDIVIDUAL = ["cnpj", "processo"]
COLUNAS_DE_VALOR_DO_INDIVIDUAL = COLUNAS_DO_INDIVIDUAL[4:]

COLUNAS_DA_ADESAO = (
    "cnpj", "modalidade", "data_requerimento", "divida_sem_reducao", "reducao", "credito_pf_proprio",
    "credito_pf_terceiros", "credito_bcn_proprio", "credito_bcn_terceiros", "parcelas",
)  # fmt: skip
COLUNAS_DE_VALOR_DA_ADESAO = COLUNAS_DA_ADESAO[3:9]
CHAVE_DA_ADESAO = ["hash_linha"]

_CNPJ_FORMATADO = re.compile(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$")
_MESES = {
    nome: numero
    for numero, nome in enumerate(
        ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"),
        start=1,
    )
}  # fmt: skip
_MES_E_ANO = re.compile(r"^([a-z]{3})/(\d{2})$")
_SECULO = 2000


@dataclass
class Contagem:
    """O que a leitura viu e o que deixou de fora (vai para o manifesto)."""

    lidas: int = 0
    sem_cnpj_descartadas: int = 0
    identicas_numeradas: int = 0

    def para_manifesto(self) -> dict[str, object]:
        return {
            "linhas_lidas": self.lidas,
            "linhas_sem_cnpj_descartadas": self.sem_cnpj_descartadas,
            "linhas_identicas_numeradas": self.identicas_numeradas,
        }


def decodificar(linha: bytes) -> str:
    """UTF-8 se for (tirando o BOM), senão latin-1 (que lê qualquer byte)."""
    for codificacao in CODIFICACOES:
        try:
            return linha.decode(codificacao).lstrip("﻿")
        except UnicodeDecodeError:
            continue
    raise AssertionError("latin-1 lê qualquer byte")  # pragma: no cover


def _linhas_decodificadas(linhas: Iterable[bytes]) -> Iterator[str]:
    for linha in linhas:
        texto = decodificar(linha).rstrip("\r\n")
        if texto.strip():
            yield texto


def cnpj_inteiro(texto: str) -> str | None:
    """Os 14 dígitos de um CNPJ formatado (`00.000.000/0000-00`); `None` para CPF, mascarado ou torto."""
    texto = texto.strip()
    if not _CNPJ_FORMATADO.match(texto):
        return None
    return re.sub(r"\D", "", texto)


def valor_individual(texto: str) -> float | None:
    """`"1.890.254.972"` vira 1890254972.0 (ponto é milhar); vazio vira `None`."""
    texto = texto.strip()
    if not texto:
        return None
    return float(texto.replace(".", "").replace(",", "."))


def valor_da_adesao(texto: str) -> float | None:
    """`"3057774,82"` vira 3057774.82 (vírgula decimal); vazio vira `None`."""
    texto = texto.strip()
    if not texto:
        return None
    return float(texto.replace(",", "."))


def mes_e_ano(texto: str) -> pd.Timestamp:
    """`"out/23"` vira 01/10/2023 (a fonte só dá o mês). Levanta ValueError se não for `mmm/aa`."""
    achado = _MES_E_ANO.match(texto.strip().lower())
    if not achado or achado.group(1) not in _MESES:
        raise ValueError(f"Transações: data fora do formato mmm/aa: {texto!r}")
    return pd.Timestamp(
        year=_SECULO + int(achado.group(2)), month=_MESES[achado.group(1)], day=1
    )


def _campos(
    linhas: Iterable[bytes], largura: int, nome: str, contagem: Contagem
) -> Iterator[list[str]]:
    """Os campos de cada linha de dados (o cabeçalho é pulado), conferida a largura."""
    textos = _linhas_decodificadas(linhas)
    next(textos, None)  # cabeçalho
    for campos in csv.reader(textos, delimiter=";", quoting=csv.QUOTE_NONE):
        contagem.lidas += 1
        if len(campos) != largura:
            raise ValueError(f"{nome}: esperava {largura} campos, veio {len(campos)}")
        yield campos


def ler_individual(
    linhas: Iterable[bytes],
    modificado_em: date,
    contagem: Contagem | None = None,
) -> pd.DataFrame:
    """Os acordos individuais numa tabela, uma linha por CNPJ e processo.

    Colunas pela posição. A linha cujo documento não é um CNPJ formatado sai (e o nome do contribuinte com
    ela). Levanta ValueError para linha com número de campos errado, data fora de `mmm/aa` ou chave repetida."""
    contagem = contagem if contagem is not None else Contagem()
    guardadas: list[list[object]] = []
    for campos in _campos(linhas, len(COLUNAS_DO_INDIVIDUAL), "Individual", contagem):
        cnpj = cnpj_inteiro(campos[1])
        if cnpj is None:
            contagem.sem_cnpj_descartadas += 1
            continue
        guardadas.append(
            [
                campos[0].strip(),
                cnpj,
                campos[2].strip(),
                mes_e_ano(campos[3]),
                *(valor_individual(c) for c in campos[4:]),
            ]
        )
    tabela = pd.DataFrame(guardadas, columns=list(COLUNAS_DO_INDIVIDUAL))
    tabela["data_acordo"] = pd.to_datetime(tabela["data_acordo"])
    for coluna in COLUNAS_DE_VALOR_DO_INDIVIDUAL:
        tabela[coluna] = tabela[coluna].astype("Float64")
    if tabela.duplicated(CHAVE_DO_INDIVIDUAL).any():
        raise ValueError("Individual: chave repetida (CNPJ e processo)")
    tabela["disponivel_em"] = pd.Timestamp(modificado_em)
    return tabela


def _hash_da_linha(cnpj: str, campos: list[str], ordem: int) -> str:
    """SHA-256 do conteúdo da linha, com o número de ordem entre as idênticas (0 na primeira)."""
    conteudo = "|".join([cnpj, *(c.strip() for c in campos[1:])]) + f"#{ordem}"
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


def ler_adesao(
    linhas: Iterable[bytes],
    modificado_em: date,
    contagem: Contagem | None = None,
) -> pd.DataFrame:
    """As adesões numa tabela de eventos: uma linha por pedido, com o `hash_linha` como chave.

    Colunas pela posição. A linha cujo documento não é um CNPJ formatado (os 67% de CPF mascarado) sai e só
    é contada. Linhas idênticas ficam todas, numeradas no hash. Levanta ValueError para número de campos
    errado ou data fora de `dd/mm/aaaa`."""
    contagem = contagem if contagem is not None else Contagem()
    vistas: dict[str, int] = {}
    guardadas: list[list[object]] = []
    for campos in _campos(linhas, len(COLUNAS_DA_ADESAO), "Adesão", contagem):
        cnpj = cnpj_inteiro(campos[0])
        if cnpj is None:
            contagem.sem_cnpj_descartadas += 1
            continue
        sem_ordem = _hash_da_linha(cnpj, campos, 0)
        ordem = vistas.get(sem_ordem, 0)
        vistas[sem_ordem] = ordem + 1
        contagem.identicas_numeradas += 1 if ordem else 0
        guardadas.append(
            [
                cnpj,
                campos[1].strip(),
                pd.to_datetime(campos[2].strip(), format="%d/%m/%Y"),
                *(valor_da_adesao(c) for c in campos[3:9]),
                int(campos[9]),
                _hash_da_linha(cnpj, campos, ordem),
            ]
        )
    tabela = pd.DataFrame(guardadas, columns=[*COLUNAS_DA_ADESAO, "hash_linha"])
    tabela["data_requerimento"] = pd.to_datetime(tabela["data_requerimento"])
    for coluna in COLUNAS_DE_VALOR_DA_ADESAO:
        tabela[coluna] = tabela[coluna].astype("Float64")
    tabela["parcelas"] = tabela["parcelas"].astype("int32")
    if tabela.duplicated(CHAVE_DA_ADESAO).any():
        raise ValueError("Adesão: hash repetido")  # pragma: no cover
    tabela["disponivel_em"] = pd.Timestamp(modificado_em)
    return tabela
