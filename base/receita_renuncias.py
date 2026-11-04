"""Renúncias fiscais declaradas à Receita Federal (linha 660 da fila, rodada de fontes de 03/11/2026): o DIRBI
(benefício fiscal por regime, mensal) e a ECF (incentivos de IRPJ e CSLL, anual).

- **DIRBI:** `renuncia-por-regime-AAAA.zip`, um CSV de vírgula com campos entre aspas quando precisa, CRLF,
  10 colunas (`CNPJ, Nome, Município, UF, Cnae, Mês, Ano, Código_IN, Tributo, Valor`), valor com vírgula
  decimal. 2025 tem ~6,3 milhões de linhas e 2026 ~3,8 milhões (até jun/2026): lido em fluxo, um mês por vez.
  **Chave:** CNPJ + ano + mês + `codigo_in` + tributo (única nas duas cargas medidas).
- **ECF:** `renuncia-irpj-csll-ecf.csv`, separador `|`, 36 colunas (11 de identificação, 24 de benefício e o
  ano), 183 mil linhas, exercícios 2015 a 2025. **Chave:** CNPJ + `cod_scp` + `dt_ini` + `dt_fin` (CNPJ + ano
  NÃO é única: a empresa pode ter dois períodos no mesmo ano, por cisão ou incorporação). A linha
  inteiramente repetida é descartada; se a mesma chave vem com valores diferentes (2 casos), fica a mais
  preenchida.
- **Ler por posição, não pelo nome:** o cabeçalho do DIRBI vem com caractere corrompido. O corpo dos arquivos
  baixados em 04/11/2026 é UTF-8 (a validação da linha 637 supôs latin-1); a leitura tenta UTF-8 e cai para
  latin-1 por linha, então os dois valem.
- **CNPJ mascarado fora:** no DIRBI, o agregado de empresas com restrição judicial vem como `***...3` com o nome
  "Restrição Judicial (3)"; não é um contribuinte e é descartado (e contado). Um CNPJ que não fecha 14 dígitos
  também.
- **A instituição, não a pessoa:** só CNPJ; nome empresarial é o da pessoa jurídica. O sufixo
  "*Valores em verificação" que a Receita põe em alguns nomes vira a coluna `em_verificacao` e sai do nome.

**Sem olhar o futuro:** nenhuma das duas fontes traz a data de entrega por linha. `disponivel_em` é o
`Last-Modified` do arquivo na Receita (DIRBI 2025 e 2026: 08/09/2026; ECF: 19/09/2026), que quem chama passa.
O período de referência (`ano`, `mes`; `dt_ini`, `dt_fin`, `exercicio`) fica em colunas à parte. A
Receita regrava o arquivo inteiro: o de hoje vale a partir de hoje.

**Licença:** a confirmar, só uso interno (ADR 0102, Emenda 2); nada foi perguntado à fonte.

Sem Streamlit; pandas só.
"""

import csv
import math
import re
from array import array
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

FONTE_DIRBI = "receita-dirbi"
FONTE_ECF = "receita-ecf-renuncia"
ATRIBUICAO = "Fonte: Receita Federal do Brasil, dados abertos (DIRBI e ECF)."
AVISO = (
    "O DIRBI e a ECF mostram o que cada pessoa jurídica declarou como benefício fiscal, não o que a Receita "
    "deixou de arrecadar. Sai com cerca de 2 meses (DIRBI) a 1 ano (ECF) de atraso."
)
CODIFICACOES = ("utf-8", "latin-1")

COLUNAS_DO_DIRBI = (
    "cnpj", "nome", "municipio", "uf", "cnae", "mes", "ano", "codigo_in", "tributo", "valor",
)  # fmt: skip
CHAVE_DO_DIRBI = ["cnpj", "ano", "mes", "codigo_in", "tributo"]

COLUNAS_DE_IDENTIFICACAO_DA_ECF = (
    "cnpj", "razao_social", "cod_scp", "dt_ini", "dt_fin", "forma_trib", "forma_apur", "qualif_pj",
    "sit_especial", "cnae", "cod_nat",
)  # fmt: skip
COLUNAS_DE_BENEFICIO_DA_ECF = (
    "horario_eleitoral_deducao_lalur", "prouni_universidade_para_todos",
    "sudam_sudene_isencao_proj_ind_agric", "sudam_sudene_isencao_proj_tec_dig",
    "sudam_sudene_reducao_75_proj_setor_priorit", "sudam_sudene_red_escal_setor_prior_proj_ind_agric",
    "padis", "sudam_sudene_red_reinv", "finor", "finam", "pronac_deducao_ir", "pat_deducao_ir",
    "atividade_audiov_deducao_ir", "fundos_direitos_crianca_adolescente", "fundos_idoso",
    "incentivo_desporto", "pronon_deducao_ir", "pronas_pcd_deducao_ir", "empresa_cidada_deducao_ir",
    "rota_2030_deducao_ir", "prouni_deducao_csll", "rota_2030_deducao_csll", "perse_irpj", "perse_csll",
)  # fmt: skip
COLUNAS_DA_ECF = (
    *COLUNAS_DE_IDENTIFICACAO_DA_ECF,
    *COLUNAS_DE_BENEFICIO_DA_ECF,
    "exercicio",
)
CHAVE_DA_ECF = ["cnpj", "cod_scp", "dt_ini", "dt_fin"]

_CNPJ_FORMATADO = re.compile(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$")
_EM_VERIFICACAO = re.compile(r"\s*\*\s*Valores em verifica[cç][aã]o\s*$", re.IGNORECASE)
_MES_MAXIMO = 12


@dataclass
class Contagem:
    """O que a leitura viu e o que deixou de fora (vai para o manifesto)."""

    lidas: int = 0
    mascaradas: int = 0
    repetidas: int = 0
    conflitantes: int = 0

    def para_manifesto(self) -> dict[str, object]:
        return {
            "linhas_lidas": self.lidas,
            "linhas_com_cnpj_mascarado_descartadas": self.mascaradas,
            "linhas_repetidas_descartadas": self.repetidas,
            "chaves_repetidas_com_valores_diferentes": self.conflitantes,
        }


def decodificar(linha: bytes) -> str:
    """UTF-8 se for, senão latin-1 (que lê qualquer byte)."""
    for codificacao in CODIFICACOES:
        try:
            return linha.decode(codificacao)
        except UnicodeDecodeError:
            continue
    raise AssertionError("latin-1 lê qualquer byte")  # pragma: no cover


def _linhas_decodificadas(linhas: Iterable[bytes]) -> Iterator[str]:
    for linha in linhas:
        texto = decodificar(linha).rstrip("\r\n")
        if texto.strip():
            yield texto


def cnpj_inteiro(texto: str) -> str | None:
    """Os 14 dígitos de um CNPJ formatado (`00.000.000/0000-00`); `None` para o mascarado ou torto."""
    texto = texto.strip().lstrip("﻿")
    if not _CNPJ_FORMATADO.match(texto):
        return None
    return re.sub(r"\D", "", texto)


def valor_em_reais(texto: str) -> float | None:
    """`"32082,5"` vira 32082.5; vazio vira `None` (não declarado, diferente de zero)."""
    texto = texto.strip()
    if not texto:
        return None
    return float(texto.replace(",", "."))


def _nome_e_verificacao(nome: str) -> tuple[str, bool]:
    limpo = _EM_VERIFICACAO.sub("", nome).strip()
    return limpo, limpo != nome.strip()


_COLUNAS_CATEGORICAS_DO_DIRBI = (
    0,
    1,
    2,
    3,
    4,
    7,
    8,
)  # posições: cnpj, nome, município, uf, cnae, código, tributo


def ler_dirbi(
    linhas: Iterable[bytes],
    modificado_em: date,
    contagem: Contagem | None = None,
) -> pd.DataFrame:
    """O CSV do DIRBI inteiro em fluxo, numa tabela de memória pequena (texto repetido guardado uma vez).

    A primeira linha é o cabeçalho e é pulada: as colunas vêm pela posição. Os meses vêm misturados no
    arquivo (jan a jun de 2026 se alternam), por isso a chave é conferida no fim, com a tabela toda.
    Levanta ValueError para linha com número de campos errado, mês fora de 1 a 12 ou chave repetida."""
    contagem = contagem if contagem is not None else Contagem()
    textos = _linhas_decodificadas(linhas)
    next(textos, None)  # cabeçalho
    codigos: dict[int, dict[str, int]] = {i: {} for i in _COLUNAS_CATEGORICAS_DO_DIRBI}
    colunas_de_codigo = {i: array("i") for i in _COLUNAS_CATEGORICAS_DO_DIRBI}
    meses, anos, valores = array("h"), array("h"), array("d")
    for campos in csv.reader(textos):
        contagem.lidas += 1
        if len(campos) != len(COLUNAS_DO_DIRBI):
            raise ValueError(
                f"DIRBI: esperava {len(COLUNAS_DO_DIRBI)} campos, veio {len(campos)}"
            )
        cnpj = cnpj_inteiro(campos[0])
        if cnpj is None:
            contagem.mascaradas += 1
            continue
        campos[0] = cnpj
        mes = int(campos[5])
        if not 1 <= mes <= _MES_MAXIMO:
            raise ValueError(f"DIRBI: mês fora de 1 a 12: {mes}")
        for posicao, tabela_de_codigos in codigos.items():
            colunas_de_codigo[posicao].append(
                tabela_de_codigos.setdefault(
                    campos[posicao].strip(), len(tabela_de_codigos)
                )
            )
        meses.append(mes)
        anos.append(int(campos[6]))
        valor = valor_em_reais(campos[9])
        valores.append(math.nan if valor is None else valor)
    return _tabela_do_dirbi(
        codigos, colunas_de_codigo, meses, anos, valores, modificado_em
    )


def _categoria(codigos: dict[str, int], dos_codigos: array) -> pd.Categorical:
    return pd.Categorical.from_codes(
        np.frombuffer(dos_codigos, dtype=np.intc), categories=list(codigos)
    )


def _tabela_do_dirbi(
    codigos: dict[int, dict[str, int]],
    colunas_de_codigo: dict[int, array],
    meses: array,
    anos: array,
    valores: array,
    modificado_em: date,
) -> pd.DataFrame:
    nomes_brutos = list(codigos[1])
    limpos = [_nome_e_verificacao(nome) for nome in nomes_brutos]
    codigo_do_nome = np.frombuffer(colunas_de_codigo[1], dtype=np.intc)
    em_verificacao = np.array([flag for _, flag in limpos], dtype=bool)
    nomes = np.array([nome for nome, _ in limpos], dtype=object)
    tabela = pd.DataFrame(
        {
            "cnpj": _categoria(codigos[0], colunas_de_codigo[0]),
            "nome": pd.Categorical(nomes[codigo_do_nome]),
            "municipio": _categoria(codigos[2], colunas_de_codigo[2]),
            "uf": _categoria(codigos[3], colunas_de_codigo[3]),
            "cnae": _categoria(codigos[4], colunas_de_codigo[4]),
            "mes": np.frombuffer(meses, dtype=np.int16),
            "ano": np.frombuffer(anos, dtype=np.int16),
            "codigo_in": _categoria(codigos[7], colunas_de_codigo[7]),
            "tributo": _categoria(codigos[8], colunas_de_codigo[8]),
            "valor": pd.array(
                np.frombuffer(valores, dtype=np.float64), dtype="Float64"
            ),
            "em_verificacao": em_verificacao[codigo_do_nome],
        }
    )
    if tabela.duplicated(CHAVE_DO_DIRBI).any():
        raise ValueError("DIRBI: chave repetida (CNPJ, ano, mês, código e tributo)")
    tabela["disponivel_em"] = pd.Timestamp(modificado_em)
    return tabela


def dirbi_por_mes(
    tabela: pd.DataFrame,
) -> Iterator[tuple[tuple[int, int], pd.DataFrame]]:
    """A tabela do DIRBI repartida por `(ano, mês)`, do mais antigo ao mais novo, com texto comum
    (sem categorias) para gravar em Parquet."""
    for (ano, mes), parte in tabela.groupby(["ano", "mes"], sort=True, observed=True):
        texto = parte.astype(
            {
                c: "object"
                for c in parte.columns
                if isinstance(parte[c].dtype, pd.CategoricalDtype)
            }
        )
        yield (int(ano), int(mes)), texto.reset_index(drop=True)


def _uma_linha_por_chave_da_ecf(tabela: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Na mesma chave com valores diferentes (uma declaração completada depois da outra: medido em 04/11/2026,
    2 chaves em 183 mil), fica a linha com mais benefícios preenchidos; empate, a última do arquivo."""
    repetida = tabela.duplicated(CHAVE_DA_ECF, keep=False)
    if not repetida.any():
        return tabela, 0
    preenchidos = (tabela[list(COLUNAS_DE_BENEFICIO_DA_ECF)] != "").sum(axis=1)
    ordem = tabela.assign(_preenchidos=preenchidos, _posicao=range(len(tabela)))
    ordem = ordem.sort_values(["_preenchidos", "_posicao"])
    mantida = ordem.drop_duplicates(CHAVE_DA_ECF, keep="last")
    conflitos = int(tabela[repetida].drop_duplicates(CHAVE_DA_ECF).shape[0])
    mantida = mantida.drop(columns=["_preenchidos", "_posicao"]).sort_index()
    return mantida.reset_index(drop=True), conflitos


def _data_da_ecf(texto: str) -> pd.Timestamp:
    return pd.to_datetime(texto.strip(), format="%d/%m/%Y")


def ler_ecf(
    linhas: Iterable[bytes],
    modificado_em: date,
    contagem: Contagem | None = None,
) -> pd.DataFrame:
    """A renúncia de IRPJ e CSLL da ECF numa tabela: uma linha por CNPJ, SCP e período da escrituração.

    Cabeçalho pulado, colunas pela posição (36). Valor vazio fica `NA` (não declarado), `0,00` fica 0.
    A linha inteiramente repetida sai; a mesma chave com valores diferentes fica com a linha mais preenchida."""
    contagem = contagem if contagem is not None else Contagem()
    textos = _linhas_decodificadas(linhas)
    next(textos, None)
    linhas_lidas: list[list[str]] = []
    for campos in csv.reader(textos, delimiter="|", quoting=csv.QUOTE_NONE):
        contagem.lidas += 1
        if len(campos) != len(COLUNAS_DA_ECF):
            raise ValueError(
                f"ECF: esperava {len(COLUNAS_DA_ECF)} campos, veio {len(campos)}"
            )
        cnpj = cnpj_inteiro(campos[0])
        if cnpj is None:
            contagem.mascaradas += 1
            continue
        campos[0] = cnpj
        linhas_lidas.append(campos)
    tabela = pd.DataFrame(linhas_lidas, columns=list(COLUNAS_DA_ECF))
    inteira = len(tabela)
    tabela = tabela.drop_duplicates().reset_index(drop=True)
    contagem.repetidas = inteira - len(tabela)
    tabela, contagem.conflitantes = _uma_linha_por_chave_da_ecf(tabela)
    for coluna in ("dt_ini", "dt_fin"):
        tabela[coluna] = tabela[coluna].map(_data_da_ecf)
    for coluna in COLUNAS_DE_BENEFICIO_DA_ECF:
        tabela[coluna] = tabela[coluna].map(valor_em_reais).astype("Float64")
    tabela["exercicio"] = tabela["exercicio"].astype("int16")
    tabela["disponivel_em"] = pd.Timestamp(modificado_em)
    return tabela


def beneficios_declarados(tabela: pd.DataFrame) -> pd.DataFrame:
    """A ECF em formato longo: só os benefícios com valor diferente de zero, uma linha por benefício."""
    longa = tabela.melt(
        id_vars=[c for c in tabela.columns if c not in COLUNAS_DE_BENEFICIO_DA_ECF],
        value_vars=list(COLUNAS_DE_BENEFICIO_DA_ECF),
        var_name="beneficio",
        value_name="valor",
    )
    return longa[longa["valor"].fillna(0) != 0].reset_index(drop=True)
