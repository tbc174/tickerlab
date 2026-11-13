"""Cadastros do Banco Central pelo CNPJ (meta das 300 tabelas, lote 3, linha 904): as entidades supervisionadas e
as cooperativas de crédito (posição de um dia), os correspondentes no País, as filiais de administradoras de
consórcio e os regimes especiais (liquidação extrajudicial e afins). Fontes `bcb-*` do arquivista
(`base/arquivo/lote_cadastros_bcb_antt.py`); a licença é a ODbL do Banco Central (família `bcb`).

- **Formato** (conferido em 13/11/2026 no serviço Olinda): JSON `{"value": [...]}`, UTF-8, tudo como texto; datas
  `AAAA-MM-DD` (filiais de consórcio) ou `DD/MM/AAAA` (regimes especiais). O Olinda responde `value: []` para o
  que ainda não saiu: o arquivista trata como "sem arquivo", então o leitor nunca vê lista vazia (se ver, falha).
- **Só pessoa jurídica** (ADR 0075): `entidades supervisionadas`, `cooperativas` e `regimes especiais` trazem o CNPJ
  de 14 caracteres (CPF e DV errado saem e são contados); `correspondentes` e `filiais de consórcio` trazem só a
  raiz de 8 dígitos. Raiz de MEI ou de empresário individual é marcada por `trata_como_pessoa` na montagem. A
  linha sem CNPJ (a entidade que só tem código do BC) fica de fora e é contada em `sem_cnpj`.
- **Ficam de fora** os nomes (da entidade, do contratante e do correspondente: texto livre, e a Receita tem a
  razão social), o endereço, o CEP, o e-mail, o telefone e o `Responsavel` do regime especial (um liquidante
  pessoa física). Ficam o código de município do IBGE e a UF.
- **Sem olhar o futuro:** os arquivos não trazem a data em que foram publicados (o `database` das entidades é a
  posição pedida, não a publicação), então a linha vale desde o dia em que o arquivista a viu: o dia do retrato.
  O BcBase guarda um endereço por dia de coleta; a montagem junta todos (não só o mais novo), e a entidade que
  sai da lista ganha a linha com `consta` falso.

Sem Streamlit; pandas só.
"""

import hashlib
import json
from collections.abc import Callable, Collection
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import aneel_indicadores as comum
from base import cadastros_em_retrato
from base import retratos as motor

FONTE_DAS_SUPERVISIONADAS = "bcb-supervisionadas"
FONTE_DAS_COOPERATIVAS = "bcb-cooperativas"
FONTE_DOS_CORRESPONDENTES = "bcb-correspondentes"
FONTE_DAS_FILIAIS = "bcb-filiais-de-consorcio"
FONTE_DOS_REGIMES = "bcb-regimes-especiais"
TABELA_DAS_SUPERVISIONADAS = "bcb_supervisionadas"
TABELA_DAS_COOPERATIVAS = "bcb_cooperativas"
TABELA_DOS_CORRESPONDENTES = "bcb_correspondentes"
TABELA_DAS_FILIAIS = "bcb_filiais_de_consorcio"
TABELA_DOS_REGIMES = "bcb_regimes_especiais"
FORMATO_DO_DIA_BR = "%d/%m/%Y"
DIGITOS_DA_RAIZ = 8
TAMANHO_DO_SELO_DO_ENDERECO = 10
IDENTIFICADOR_DO_BACEN = "codigoIdentificadorBacen"
CNPJ14_DO_BACEN = "codigoCNPJ14"

# --- o que as duas listas do BcBase têm em comum --------------------------------------------------------
DO_BACEN = {
    "codigoSisbacen": "codigo_sisbacen",
    "nomeDaUnidadeFederativa": "uf",
    "codigoDoMunicipioNoIBGE": "municipio_ibge",
    "siglaDaPessoaJuridica": "sigla",
    "codigoTipoSituacaoPessoaJuridica": "situacao_codigo",
    "descricaoTipoSituacaoPessoaJuridica": "situacao",
}
DAS_SUPERVISIONADAS = {
    **DO_BACEN,
    "codigoTipoEntidadeSupervisionada": "tipo_codigo",
    "descricaoTipoEntidadeSupervisionada": "tipo",
    "codigoNaturezaJuridica": "natureza_codigo",
    "descricaoNaturezaJuridica": "natureza",
    "indicadorEsferaPublica": "esfera_publica",
}
DAS_COOPERATIVAS = {
    **DO_BACEN,
    "codigoClasseCooperativa": "classe_codigo",
    "descricaoClasseCooperativa": "classe",
    "codigoTipoCooperativa": "tipo_da_cooperativa_codigo",
    "descricaoTipoCooperativa": "tipo_da_cooperativa",
    "codigoCategoriaCooperativa": "categoria_codigo",
    "descricaoCategoriaCooperativa": "categoria",
}
CARIMBO = ("id_na_fonte", "cnpj", "cnpj_basico")


# --- leitura comum ----------------------------------------------------------------------------------
def ler_olinda(conteudo: bytes, colunas: Collection[str]) -> pd.DataFrame:
    """O `value` do Olinda como texto (nulo vira vazio, sem espaços nas pontas).

    Lista vazia ou coluna que sumiu é erro, nunca "nada a ler": sem isto, uma coluna renomeada pelo
    Banco Central viraria uma coluna vazia sem ninguém ver."""
    valores = json.loads(conteudo).get("value") or []
    if not valores:
        raise ValueError("o arquivo do Olinda não tem registros")
    bruta = pd.DataFrame(valores, dtype=str).fillna("")
    faltam = sorted(set(colunas) - set(bruta.columns))
    if faltam:
        raise KeyError(f"o Olinda deixou de trazer: {', '.join(faltam)}")
    return bruta.apply(lambda serie: serie.str.strip())


def renomeadas(tabela: pd.DataFrame, colunas: dict[str, str]) -> dict[str, pd.Series]:
    """As colunas de texto da fonte com o nosso nome; vazio vira nulo."""
    return {
        nosso: motor.sem_vazio(tabela[da_fonte]) for da_fonte, nosso in colunas.items()
    }


def dia_br(texto: pd.Series, formato: str = FORMATO_DO_DIA_BR) -> pd.Series:
    """Data em `formato`; vazio ou fora do calendário vira nulo."""
    return pd.to_datetime(texto, format=formato, errors="coerce")


def so_raizes(
    bruta: pd.DataFrame, colunas: tuple[str, ...]
) -> tuple[pd.DataFrame, dict[str, int]]:
    """As linhas em que todas as `colunas` são uma raiz de CNPJ (8 dígitos) e a contagem das que saíram."""
    valida = pd.Series(True, index=bruta.index)
    for coluna in colunas:
        valida &= bruta[coluna].str.fullmatch(rf"\d{{{DIGITOS_DA_RAIZ}}}")
    return bruta[valida], {
        "linhas": len(bruta),
        "raiz_invalida": int((~valida).sum()),
    }


def so_pessoa_juridica_com_cnpj(
    bruta: pd.DataFrame, coluna: str
) -> tuple[pd.DataFrame, dict[str, int]]:
    """As linhas com CNPJ de DV certo em `cnpj14`; as sem CNPJ saem à parte (`sem_cnpj`), sem contar como erro."""
    sem_cnpj = bruta[coluna].eq("")
    tabela, contagem = comum.so_pessoa_juridica(bruta[~sem_cnpj], coluna)
    return tabela, {**contagem, "linhas": len(bruta), "sem_cnpj": int(sem_cnpj.sum())}


def pronta(
    tabela: pd.DataFrame, contagem: dict[str, int], tipos: dict[str, str] | None = None
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Uma linha por `id_na_fonte`; o que não é data nem tem tipo próprio vira texto (`string`)."""
    tipos = tipos or {}
    textos = {
        c: "string"
        for c in tabela.columns
        if c not in tipos and not pd.api.types.is_datetime64_any_dtype(tabela[c])
    }
    sem_repetidas = comum.sem_repetir(tabela, contagem)
    return sem_repetidas.astype({**textos, **tipos}).reset_index(drop=True), contagem


def disponivel_no_dia_do_retrato(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """Estes arquivos não dizem quando foram publicados: a linha vale desde o dia em que a vimos."""
    return pd.Series(dia, index=novos.index)


def cadastro(
    tabela: str, nome: str, fonte: str, ler: Callable[[bytes], tuple[pd.DataFrame, dict[str, int]]],
    colunas: tuple[str, ...], datas: tuple[str, ...] = (),
    achar: cadastros_em_retrato.Achador | None = None,
    raizes_de_pessoa: tuple[str, ...] = ("cnpj_basico",),
) -> cadastros_em_retrato.Cadastro:  # fmt: skip
    """O cadastro em retrato de uma tabela do lote: todas as colunas contam para saber se a linha mudou."""
    valores = [c for c in colunas if c != "id_na_fonte"] + ["consta"]
    return cadastros_em_retrato.Cadastro(
        tabela=tabela,
        nome=nome,
        fonte=fonte,
        ler=lambda retrato: ler(motor.original(retrato.caminho)),
        juntar=lambda lidos: motor.juntar(lidos, valores, disponivel_no_dia_do_retrato),
        colunas=colunas,
        datas=datas,
        achar=achar,
        raizes_de_pessoa=raizes_de_pessoa,
    )


def todos_os_retratos(fonte: str) -> cadastros_em_retrato.Achador:
    """Para a fonte que guarda um endereço por dia de coleta: todos os retratos, não só os do endereço mais novo."""
    return lambda conexao: (motor.retratos(conexao, fonte), 0)


# --- entidades supervisionadas e cooperativas -------------------------------------------------------------
def _ler_do_bacen(
    conteudo: bytes, colunas: dict[str, str]
) -> tuple[pd.DataFrame, dict[str, int]]:
    bruta = ler_olinda(conteudo, [IDENTIFICADOR_DO_BACEN, CNPJ14_DO_BACEN, *colunas])
    tabela, contagem = so_pessoa_juridica_com_cnpj(bruta, CNPJ14_DO_BACEN)
    return pronta(
        pd.DataFrame(
            {
                "id_na_fonte": tabela[IDENTIFICADOR_DO_BACEN],
                **comum.com_cnpj(tabela["cnpj14"]),
                **renomeadas(tabela, colunas),
            }
        ),
        contagem,
    )


def ler_supervisionadas(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """As entidades supervisionadas com CNPJ de uma posição do BcBase, e a contagem do que saiu."""
    return _ler_do_bacen(conteudo, DAS_SUPERVISIONADAS)


def ler_cooperativas(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """As cooperativas de crédito com CNPJ de uma posição do BcBase, e a contagem do que saiu."""
    return _ler_do_bacen(conteudo, DAS_COOPERATIVAS)


# --- correspondentes ------------------------------------------------------------------------------------
DOS_CORRESPONDENTES = {
    "Tipo": "tipo",
    "Ordem": "ordem",
    "MunicipioIBGE": "municipio_ibge",
    "UF": "uf",
    "ServicosCorrespondentes": "servicos",
}
COLUNAS_DOS_CORRESPONDENTES = (
    "id_na_fonte", "cnpj_basico", "cnpj_basico_contratante", *DOS_CORRESPONDENTES.values(),
)  # fmt: skip


def ler_correspondentes(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os correspondentes (raiz do CNPJ) e a instituição contratante de um retrato.

    O nome do correspondente e o do contratante ficam de fora. A chave é contratante, correspondente e a
    ordem que a fonte numera (a fonte tinha 24 repetições exatas em 13/11/2026: a primeira fica)."""
    bruta = ler_olinda(
        conteudo, ["CnpjContratante", "CnpjCorrespondente", *DOS_CORRESPONDENTES]
    )
    tabela, contagem = so_raizes(bruta, ("CnpjContratante", "CnpjCorrespondente"))
    return pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(
                    tabela, ["CnpjContratante", "CnpjCorrespondente", "Ordem"]
                ),
                "cnpj_basico": tabela["CnpjCorrespondente"],
                "cnpj_basico_contratante": tabela["CnpjContratante"],
                **renomeadas(tabela, DOS_CORRESPONDENTES),
            }
        ),
        contagem,
    )


# --- filiais de administradoras de consórcio --------------------------------------------------------------
DAS_FILIAIS = {"MunicipioIbge": "municipio_ibge", "UF": "uf"}
ENDERECO_DA_FILIAL = ("Endereco", "Numero", "Complemento", "Bairro", "CEP")
COLUNAS_DAS_FILIAIS = (
    "id_na_fonte", "cnpj_basico", *DAS_FILIAIS.values(), "inicio_em",
)  # fmt: skip


def _selo_do_endereco(tabela: pd.DataFrame) -> pd.Series:
    """Um selo curto do endereço, para distinguir duas filiais do mesmo município sem guardar o endereço."""
    juntos = tabela[list(ENDERECO_DA_FILIAL)].agg("|".join, axis=1)
    return juntos.map(
        lambda texto: hashlib.sha256(texto.encode()).hexdigest()[
            :TAMANHO_DO_SELO_DO_ENDERECO
        ]
    )


def ler_filiais(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """As filiais das administradoras de consórcio (raiz do CNPJ, município e dia de início) de um retrato.

    O endereço, o CEP e o telefone ficam de fora; o selo do endereço só separa filiais do mesmo município."""
    bruta = ler_olinda(
        conteudo, ["CNPJ", "DataInicio", *DAS_FILIAIS, *ENDERECO_DA_FILIAL]
    )
    tabela, contagem = so_raizes(bruta, ("CNPJ",))
    return pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(tabela, ["CNPJ", "MunicipioIbge"])
                + "|"
                + _selo_do_endereco(tabela),
                "cnpj_basico": tabela["CNPJ"],
                **renomeadas(tabela, DAS_FILIAIS),
                "inicio_em": dia_br(tabela["DataInicio"], comum.FORMATO_DA_DATA),
            }
        ),
        contagem,
    )


# --- regimes especiais ----------------------------------------------------------------------------------
DOS_REGIMES = {"Tipo": "tipo", "UF": "uf"}
COLUNAS_DOS_REGIMES = (*CARIMBO, *DOS_REGIMES.values(), "inicio_em")


def ler_regimes(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os regimes especiais (liquidação extrajudicial e afins) das instituições com CNPJ de um retrato.

    O nome, o endereço, o e-mail, o telefone e o `Responsavel` (o liquidante) ficam de fora."""
    bruta = ler_olinda(conteudo, ["CnpjInstituicao", "Inicio", *DOS_REGIMES])
    tabela, contagem = so_pessoa_juridica_com_cnpj(bruta, "CnpjInstituicao")
    return pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(tabela, ["cnpj14", "Inicio", "Tipo"]),
                **comum.com_cnpj(tabela["cnpj14"]),
                **renomeadas(tabela, DOS_REGIMES),
                "inicio_em": dia_br(tabela["Inicio"]),
            }
        ),
        contagem,
    )


# --- montagem -------------------------------------------------------------------------------------------
CADASTRO_DAS_SUPERVISIONADAS = cadastro(
    TABELA_DAS_SUPERVISIONADAS, "supervisionadas", FONTE_DAS_SUPERVISIONADAS, ler_supervisionadas,
    (*CARIMBO, *DAS_SUPERVISIONADAS.values()), achar=todos_os_retratos(FONTE_DAS_SUPERVISIONADAS),
)  # fmt: skip
CADASTRO_DAS_COOPERATIVAS = cadastro(
    TABELA_DAS_COOPERATIVAS, "cooperativas", FONTE_DAS_COOPERATIVAS, ler_cooperativas,
    (*CARIMBO, *DAS_COOPERATIVAS.values()), achar=todos_os_retratos(FONTE_DAS_COOPERATIVAS),
)  # fmt: skip
CADASTRO_DOS_CORRESPONDENTES = cadastro(
    TABELA_DOS_CORRESPONDENTES, "correspondentes", FONTE_DOS_CORRESPONDENTES, ler_correspondentes,
    COLUNAS_DOS_CORRESPONDENTES, raizes_de_pessoa=("cnpj_basico", "cnpj_basico_contratante"),
)  # fmt: skip
CADASTRO_DAS_FILIAIS = cadastro(
    TABELA_DAS_FILIAIS, "filiais", FONTE_DAS_FILIAIS, ler_filiais, COLUNAS_DAS_FILIAIS, ("inicio_em",),
)  # fmt: skip
CADASTRO_DOS_REGIMES = cadastro(
    TABELA_DOS_REGIMES, "regimes", FONTE_DOS_REGIMES, ler_regimes, COLUNAS_DOS_REGIMES, ("inicio_em",),
)  # fmt: skip
CADASTROS = (
    CADASTRO_DAS_SUPERVISIONADAS,
    CADASTRO_DAS_COOPERATIVAS,
    CADASTRO_DOS_CORRESPONDENTES,
    CADASTRO_DAS_FILIAIS,
    CADASTRO_DOS_REGIMES,
)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/bcb_<tabela>/<cadastro>.parquet` para cada cadastro com arquivo guardado (só CNPJ)."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
