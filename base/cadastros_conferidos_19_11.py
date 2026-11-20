"""Tabelas pelo CNPJ das fontes que a conferência de 19/11/2026 confirmou (meta das 300, PR 2): SICAF e BPS.

Duas tabelas em retrato (`base/cadastros_em_retrato.py`), das fontes de `base/arquivo/lote_conferidas_19_11.py`:

| Tabela | Fonte | O que é |
|---|---|---|
| `comprasgov_sicaf` | Compras.gov.br, SICAF | Fornecedores do governo federal: ativo, habilitado a licitar, CNAE, natureza e porte |
| `bps_compras` | Ministério da Saúde, Banco de Preços em Saúde | Compras públicas de medicamentos e produtos de saúde: item, quantidade e preço |

- **Só pessoa jurídica** (ADR 0075): CNPJ de 14 caracteres com o DV certo; o CPF (inteiro ou mascarado) e o CNPJ
  que não fecha o DV saem e são contados (`pessoa_fisica`, `cnpj_invalido`). O arquivista já grava só o item com
  CNPJ inteiro e sem o campo `cpf`: o leitor confere de novo. A raiz de MEI ou de empresário individual é marcada
  por `trata_como_pessoa` na montagem (no BPS, a do fornecedor e a do fabricante), e a porta a esconde.
- **Ficam de fora** a razão social do SICAF e os nomes do fornecedor e do fabricante do BPS (o arquivista nem os
  grava): a Receita tem a razão social pelo CNPJ, e o nome pode ser de pessoa.
- **Sem olhar o futuro:** o SICAF não diz quando cada cadastro mudou, e a data de inserção no BPS é a do sistema
  do Ministério, não a da publicação do arquivo; a linha vale desde o dia em que o arquivista a viu.
- **Um arquivo por ano no BPS:** cada ZIP anual é uma série própria de retratos (a compra de 2021 não "sai" por
  não estar no ZIP de 2022); a montagem junta os retratos de cada endereço à parte e empilha os anos.

Sem Streamlit; pandas só.
"""

import json
from collections.abc import Collection
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import aneel_indicadores as comum
from base import bcb_cadastros as base
from base import cadastros_em_retrato
from base import cnpj as cnpjs
from base import retratos as motor
from base.arquivo import lote_conferidas_19_11 as arquivista
from base.cadastros_conferidos import data, inteiro, ler_csv

TABELA_DO_SICAF = "comprasgov_sicaf"
TABELA_DO_BPS = "bps_compras"
FONTE_DO_BPS = "bps"
CARIMBO = ("id_na_fonte", "cnpj", "cnpj_basico")
DIGITOS_DO_CNAE = 7  # a API manda o código como número: o zero da frente some
VERDADES = {"true": True, "false": False}


# --- Compras.gov.br: SICAF ---------------------------------------------------------------------------------
DO_SICAF = {
    "nomeCnae": "descricao_do_cnae",
    "naturezaJuridicaId": "natureza_juridica",
    "naturezaJuridicaNome": "descricao_da_natureza_juridica",
    "porteEmpresaId": "porte",
    "porteEmpresaNome": "descricao_do_porte",
    "nomeMunicipio": "municipio",
    "ufSigla": "uf",
}
SIM_OU_NAO_DO_SICAF = {"ativo": "ativo", "habilitadoLicitar": "habilitado_a_licitar"}
COLUNAS_DO_SICAF = (
    *CARIMBO,
    *SIM_OU_NAO_DO_SICAF.values(),
    "cnae",
    *DO_SICAF.values(),
)


def _texto(valor: object) -> str:
    """O valor do JSON como o texto do CSV: nulo vira vazio e o booleano, `true`/`false`."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    return str(valor).strip()


def _sim_ou_nao(texto: pd.Series) -> pd.Series:
    """`true`/`false` em booleano; outro valor vira nulo."""
    return texto.map(VERDADES).astype("boolean")


def _cnae(texto: pd.Series) -> pd.Series:
    """O código CNAE com 7 dígitos (a API o manda como número); vazio vira nulo."""
    return motor.sem_vazio(texto).str.zfill(DIGITOS_DO_CNAE)


def ler_sicaf(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os fornecedores pessoa jurídica de uma lista do SICAF (o JSONL do arquivista) e a contagem do que saiu."""
    itens = [
        json.loads(linha) for linha in conteudo.decode("utf-8").splitlines() if linha
    ]
    bruta = pd.DataFrame(
        [
            {c: _texto(item.get(c)) for c in arquivista.CAMPOS_DO_SICAF}
            for item in itens
        ],
        columns=list(arquivista.CAMPOS_DO_SICAF),
        dtype="object",
    )
    tabela, contagem = comum.so_pessoa_juridica(
        bruta, arquivista.CAMPO_DO_CNPJ_DO_SICAF
    )
    return base.pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(tabela, ["cnpj14"]),
                **comum.com_cnpj(tabela["cnpj14"]),
                **{
                    nosso: _sim_ou_nao(tabela[da_fonte])
                    for da_fonte, nosso in SIM_OU_NAO_DO_SICAF.items()
                },
                "cnae": _cnae(tabela["codigoCnae"]),
                **{
                    nosso: motor.sem_vazio(tabela[da_fonte])
                    for da_fonte, nosso in DO_SICAF.items()
                },
            }
        ),
        contagem,
        dict.fromkeys(SIM_OU_NAO_DO_SICAF.values(), "boolean"),
    )


# --- Ministério da Saúde: Banco de Preços em Saúde ---------------------------------------------------------
DO_BPS = {
    "no_instituicao": "instituicao",
    "sg_uf": "uf",
    "no_municipio": "municipio",
    "ds_esfera": "esfera",
    "validade_compra": "validade_da_compra",
    "co_catmat": "catmat",
    "ds_item": "item",
    "co_pdm": "pdm",
    "no_pdm": "descricao_do_pdm",
    "co_classe": "classe",
    "no_classe": "descricao_da_classe",
    "fg_generico": "generico",
    "registro_anvisa": "registro_na_anvisa",
    "tp_compra": "tipo_de_compra",
    "modalidade": "modalidade",
    "nu_processo_compra": "processo_de_compra",
    "nu_ata": "ata",
    "sg_unidade_medida": "unidade_de_medida",
    "un_fornecimento": "unidade_de_fornecimento",
    "un_medida_capacidade": "unidade_da_capacidade",
}
DATAS_DO_BPS = {"dt_compra": "data_da_compra", "dt_insercao": "data_de_insercao"}
NUMEROS_DO_BPS = {
    "vl_capacidade": "capacidade",
    "qt_medicamento": "quantidade",
    "vl_preco_unitario": "preco_unitario",
    "vl_preco_total": "preco_total",
}
COLUNAS_DO_BPS = (
    *CARIMBO,
    "cnpj_do_fabricante",
    "cnpj_basico_do_fabricante",
    "cnpj_da_instituicao",
    "ano_da_compra",
    *DATAS_DO_BPS.values(),
    *DO_BPS.values(),
    *NUMEROS_DO_BPS.values(),
)
RAIZES_DE_PESSOA_DO_BPS = ("cnpj_basico", "cnpj_basico_do_fabricante")


def ler_bps(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """As compras de fornecedor pessoa jurídica de um ano do BPS e a contagem do que saiu.

    O CNPJ do fabricante e o da instituição compradora ficam formatados, e só quando o DV confere."""
    bruta = ler_csv(conteudo, arquivista.COLUNAS_DO_BPS, "utf-8")
    tabela, contagem = comum.so_pessoa_juridica(
        bruta, arquivista.COLUNA_DO_FORNECEDOR_DO_BPS
    )
    fabricante, _ = comum.documentos(tabela["cnpj_fabricante"])
    instituicao, _ = comum.documentos(tabela["cnpj_instituicao"])
    return base.pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(tabela, ["co_seq_bps"]),
                **comum.com_cnpj(tabela["cnpj14"]),
                "cnpj_do_fabricante": fabricante.map(
                    cnpjs.formatar, na_action="ignore"
                ),
                # `map`, e não `.str`: no ano sem nenhum fabricante a coluna inteira é nula (float)
                "cnpj_basico_do_fabricante": fabricante.map(
                    lambda cnpj: cnpj[: cnpjs.TAMANHO_DA_RAIZ], na_action="ignore"
                ),
                "cnpj_da_instituicao": instituicao.map(
                    cnpjs.formatar, na_action="ignore"
                ),
                "ano_da_compra": inteiro(tabela["ano_compra"]),
                **{
                    nosso: data(tabela[da_fonte])
                    for da_fonte, nosso in DATAS_DO_BPS.items()
                },
                **{
                    nosso: motor.sem_vazio(tabela[da_fonte])
                    for da_fonte, nosso in DO_BPS.items()
                },
                **{
                    nosso: comum.numero(tabela[da_fonte])
                    for da_fonte, nosso in NUMEROS_DO_BPS.items()
                },
            }
        ),
        contagem,
        {"ano_da_compra": "Int64", **dict.fromkeys(NUMEROS_DO_BPS.values(), "float64")},
    )


def _juntar_cada_ano(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos de cada ZIP anual juntados à parte (uma série por endereço) e empilhados."""
    valores = [c for c in COLUNAS_DO_BPS if c != "id_na_fonte"] + ["consta"]
    por_endereco: dict[str, list[tuple[motor.Retrato, pd.DataFrame]]] = {}
    for retrato, tabela in lidos:
        por_endereco.setdefault(retrato.url, []).append((retrato, tabela))
    juntados = [
        motor.juntar(serie, valores, base.disponivel_no_dia_do_retrato)
        for serie in por_endereco.values()
    ]
    return (
        pd.concat([tabela for tabela, _ in juntados], ignore_index=True),
        sum(pulados for _, pulados in juntados),
    )


# --- os cadastros e a montagem -----------------------------------------------------------------------------
NOMES_DO_SICAF = {
    "comprasgov-sicaf-ativos": "ativos",
    "comprasgov-sicaf-inativos": "inativos",
}
CADASTROS_DO_SICAF = tuple(
    base.cadastro(TABELA_DO_SICAF, nome, fonte, ler_sicaf, COLUNAS_DO_SICAF)
    for fonte, nome in NOMES_DO_SICAF.items()
)
CADASTRO_DO_BPS = cadastros_em_retrato.Cadastro(
    tabela=TABELA_DO_BPS,
    nome="compras",
    fonte=FONTE_DO_BPS,
    ler=lambda retrato: ler_bps(motor.original(retrato.caminho)),
    juntar=_juntar_cada_ano,
    colunas=COLUNAS_DO_BPS,
    datas=tuple(DATAS_DO_BPS.values()),
    achar=base.todos_os_retratos(FONTE_DO_BPS),
    raizes_de_pessoa=RAIZES_DE_PESSOA_DO_BPS,
)
CADASTROS = (*CADASTROS_DO_SICAF, CADASTRO_DO_BPS)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/<tabela>/<cadastro>.parquet` de cada cadastro com arquivo guardado (`cadastros_em_retrato`)."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
