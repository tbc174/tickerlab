"""Tabelas pelo CNPJ das fontes novas que a conferência de 14/11/2026 confirmou (meta das 300, linha 904, PR 1).

Seis tabelas em retrato (`base/cadastros_em_retrato.py`), das fontes de `base/arquivo/lote_conferidas_14_11.py`:

| Tabela | Fonte | O que é |
|---|---|---|
| `receita_regime_tributario` | Receita, ECF | Regime de tributação do lucro declarado na ECF, por ano |
| `mte_pat` | MTE, PAT | Empresas inscritas no PAT e trabalhadores atendidos (sinal de porte) |
| `anm_tah` | ANM | Taxa Anual por Hectare paga por processo minerário |
| `anatel_pados` | Anatel | Processos sancionadores (PADOs), multa e situação do pagamento |
| `anatel_produtos_homologados` | Anatel | Produtos de telecomunicações homologados pelo solicitante |
| `anp_tancagem` | ANP | Tanques de combustível por instalação e a capacidade em m³ |

- **Só pessoa jurídica** (ADR 0075): CNPJ de 14 caracteres com o DV certo; o CPF (inteiro ou mascarado) e o CNPJ
  que não fecha o DV saem e são contados (`pessoa_fisica`, `cnpj_invalido`). Nas fontes que misturam CPF (TAH,
  PADOs, homologados), o arquivista já grava só a linha com CNPJ inteiro: o leitor confere de novo. A raiz de MEI
  ou de empresário individual é marcada por `trata_como_pessoa` na montagem, e a porta a esconde.
- **Ficam de fora** as colunas de nome (razão social, titular, empresa, grupo econômico, solicitante, fabricante):
  a Receita tem a razão social pelo CNPJ, e o nome do titular pode ser de pessoa.
- **Sem olhar o futuro:** nenhum destes arquivos diz quando foi publicado (a data de quitação da TAH, a de
  homologação e a de cadastro no PAT são do fato, não da publicação), então a linha vale desde o dia em que o
  arquivista a viu: o dia do retrato. A ECF do ano X só sai no ano X+1, e a linha vale do dia em que a vimos.
- **Mais de um endereço:** o PAT põe a data no nome da planilha e a ANP publica um CSV por mês; a montagem junta
  todos os retratos da fonte (não só os do endereço mais novo), e o registro que sai ganha `consta` falso.

Sem Streamlit; pandas só.
"""

import io
import zipfile
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
from base.arquivo import lote_conferidas_14_11 as arquivista

TABELA_DO_REGIME = "receita_regime_tributario"
TABELA_DO_PAT = "mte_pat"
TABELA_DA_TAH = "anm_tah"
TABELA_DOS_PADOS = "anatel_pados"
TABELA_DOS_HOMOLOGADOS = "anatel_produtos_homologados"
TABELA_DA_TANCAGEM = "anp_tancagem"
FONTE_DA_TAH = "anm-tah"
FONTE_DOS_PADOS = "anatel-pados"
FONTE_DOS_HOMOLOGADOS = "anatel-homologados"
FONTE_DA_TANCAGEM = "anp-tancagem"
SEPARADOR_DO_ACERVO = ";"  # o arquivista grava o CSV filtrado sempre com ";"
FORMATO_ISO = "%Y-%m-%d"
TAMANHO_DA_DATA = 10  # "AAAA-MM-DD" ou "DD/MM/AAAA", sem a hora que às vezes vem junto
CARIMBO = ("id_na_fonte", "cnpj", "cnpj_basico")


# --- leitura comum ----------------------------------------------------------------------------------------
def ler_csv(
    conteudo: bytes,
    colunas: Collection[str],
    codificacao: str,
    separador: str = SEPARADOR_DO_ACERVO,
) -> pd.DataFrame:
    """O CSV como texto, sem espaços nas pontas; coluna que a fonte tirou é erro, não coluna vazia."""
    bruta = pd.read_csv(
        io.BytesIO(conteudo),
        sep=separador,
        encoding=codificacao,
        dtype=str,
        keep_default_na=False,
    )
    bruta.columns = [c.strip() for c in bruta.columns]
    faltam = sorted(set(colunas) - set(bruta.columns))
    if faltam:
        raise KeyError(f"o arquivo deixou de trazer: {', '.join(faltam)}")
    return bruta[list(colunas)].apply(lambda serie: serie.str.strip())


def data(texto: pd.Series) -> pd.Series:
    """Data `AAAA-MM-DD` ou `DD/MM/AAAA` (com ou sem hora depois); vazio ou fora do calendário vira nulo."""
    dia = texto.str[:TAMANHO_DA_DATA]
    iso = pd.to_datetime(dia, format=FORMATO_ISO, errors="coerce")
    return iso.fillna(base.dia_br(dia))


def inteiro(texto: pd.Series) -> pd.Series:
    """Número inteiro (contagem); vazio ou texto vira nulo."""
    return pd.to_numeric(texto, errors="coerce").astype("Int64")


# --- Receita: regime tributário pela ECF -------------------------------------------------------------------
COLUNAS_DA_ECF = (
    "ano",
    "cnpj",
    "cnpj_da_scp",
    "forma_de_tributacao",
    "quantidade_de_escrituracoes",
)
SEPARADOR_DA_ECF = ","
CODIFICACAO_DA_ECF = "utf-8-sig"
COLUNAS_DO_REGIME = (
    *CARIMBO,
    "ano",
    "cnpj_da_scp",
    "forma_de_tributacao",
    "escrituracoes",
)


def _csvs_da_ecf(conteudo: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo:
        csvs = [n for n in arquivo.namelist() if n.lower().endswith(".csv")]
        if not csvs:
            raise ValueError("o ZIP da ECF não tem CSV")
        partes = [
            ler_csv(
                arquivo.read(n), COLUNAS_DA_ECF, CODIFICACAO_DA_ECF, SEPARADOR_DA_ECF
            )
            for n in csvs
        ]
    return pd.concat(partes, ignore_index=True)


def ler_regime(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """O regime de tributação de cada CNPJ e ano de um ZIP da ECF, e a contagem do que saiu.

    `cnpj_da_scp` é o CNPJ da sociedade em conta de participação quando a escrituração é dela (vazio na
    da própria empresa); fica formatado, e só quando o DV confere."""
    tabela, contagem = comum.so_pessoa_juridica(_csvs_da_ecf(conteudo), "cnpj")
    scp, _ = comum.documentos(tabela["cnpj_da_scp"])
    return base.pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(
                    tabela, ["ano", "cnpj14", "cnpj_da_scp", "forma_de_tributacao"]
                ),
                **comum.com_cnpj(tabela["cnpj14"]),
                "ano": inteiro(tabela["ano"]),
                "cnpj_da_scp": scp.map(cnpjs.formatar, na_action="ignore"),
                "forma_de_tributacao": motor.sem_vazio(tabela["forma_de_tributacao"]),
                "escrituracoes": inteiro(tabela["quantidade_de_escrituracoes"]),
            }
        ),
        contagem,
        {"ano": "Int64", "escrituracoes": "Int64"},
    )


# --- MTE: PAT ----------------------------------------------------------------------------------------------
DO_PAT = {
    "MATRIZOUFILIAL": "matriz_ou_filial",
    "MUNICIPIO": "municipio",
    "UF": "uf",
    "NOREGISTRO": "registro_no_pat",
    "SITUACAO": "situacao",
}
CONTAGENS_DO_PAT = {
    "ATE5SALARIOSMINIMOS": "trabalhadores_ate_5_salarios",
    "ACIMADE5SALARIOSMINIMOS": "trabalhadores_acima_de_5_salarios",
    "TOTALTRABALHADORESATENDIDOS": "trabalhadores_atendidos",
}
COLUNAS_DA_TABELA_DO_PAT = (
    *CARIMBO,
    *DO_PAT.values(),
    "data_do_cadastro",
    *CONTAGENS_DO_PAT.values(),
)


def ler_pat(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """As empresas de uma relação do PAT (CSV que o arquivista gravou da planilha) e a contagem do que saiu."""
    bruta = ler_csv(conteudo, arquivista.COLUNAS_DO_PAT, "utf-8")
    tabela, contagem = comum.so_pessoa_juridica(bruta, arquivista.DOCUMENTO_DO_PAT)
    return base.pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(tabela, ["cnpj14", "NOREGISTRO"]),
                **comum.com_cnpj(tabela["cnpj14"]),
                **base.renomeadas(tabela, DO_PAT),
                "data_do_cadastro": data(tabela["DATACADASTRO"]),
                **{
                    nosso: inteiro(tabela[da_fonte])
                    for da_fonte, nosso in CONTAGENS_DO_PAT.items()
                },
            }
        ),
        contagem,
        dict.fromkeys(CONTAGENS_DO_PAT.values(), "Int64"),
    )


# --- ANM: TAH ----------------------------------------------------------------------------------------------
DA_TAH = {
    "NRProcesso": "processo",
    "NRAnoProcesso": "ano_do_processo",
    "DSFaseProcesso": "fase_do_processo",
    "NMSuperintendencia": "superintendencia",
}
NUMEROS_DA_TAH = {
    "NRHectares": "hectares",
    "VLPago": "valor_pago",
    "VLTotal": "valor_total",
}
COLUNAS_DA_TABELA_DA_TAH = (
    *CARIMBO,
    *DA_TAH.values(),
    "data_da_quitacao",
    *NUMEROS_DA_TAH.values(),
)


def ler_tah(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os pagamentos da TAH de pessoa jurídica e a contagem do que saiu (uma linha por processo e quitação)."""
    bruta = ler_csv(conteudo, arquivista.COLUNAS_DA_TAH, "latin-1")
    tabela, contagem = comum.so_pessoa_juridica(bruta, "NRCpfCnpj")
    return base.pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(
                    tabela, ["NRProcesso", "NRAnoProcesso", "cnpj14", "DTQuitacao"]
                ),
                **comum.com_cnpj(tabela["cnpj14"]),
                **base.renomeadas(tabela, DA_TAH),
                "data_da_quitacao": data(tabela["DTQuitacao"]),
                **{
                    nosso: comum.numero(tabela[da_fonte])
                    for da_fonte, nosso in NUMEROS_DA_TAH.items()
                },
            }
        ),
        contagem,
        dict.fromkeys(NUMEROS_DA_TAH.values(), "float64"),
    )


# --- Anatel: PADOs -----------------------------------------------------------------------------------------
DOS_PADOS = {
    "Processo": "processo",
    "Anexação": "anexacao",
    "Tema": "tema",
    "Serviço": "servico",
    "Status do Processo": "status_do_processo",
    "Fase": "fase",
    "Situação do Pagamento": "situacao_do_pagamento",
}
COLUNAS_DA_TABELA_DOS_PADOS = (*CARIMBO, *DOS_PADOS.values(), "multa_aplicada")


def ler_pados(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os PADOs de pessoa jurídica e a contagem do que saiu (uma linha por processo, serviço e anexação).

    A multa é a do processo inteiro: quando o processo cobre mais de um serviço, ela se repete em cada linha
    (some por `processo`, não por linha)."""
    bruta = ler_csv(conteudo, arquivista.COLUNAS_DOS_PADOS, "utf-8")
    tabela, contagem = comum.so_pessoa_juridica(bruta, "CPF/CNPJ")
    return base.pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(
                    tabela, ["Processo", "cnpj14", "Serviço", "Anexação", "Tema"]
                ),
                **comum.com_cnpj(tabela["cnpj14"]),
                **base.renomeadas(tabela, DOS_PADOS),
                "multa_aplicada": comum.numero(tabela["Multa Aplicada no Processo"]),
            }
        ),
        contagem,
        {"multa_aplicada": "float64"},
    )


# --- Anatel: produtos homologados --------------------------------------------------------------------------
DOS_HOMOLOGADOS = {
    "Número de Homologação": "numero_da_homologacao",
    "Certificado de Conformidade Técnica": "certificado",
    "Situação do Certificado": "situacao_do_certificado",
    "Situação do Requerimento": "situacao_do_requerimento",
    "Modelo": "modelo",
    "Nome Comercial": "nome_comercial",
    "Categoria do Produto": "categoria",
    "Tipo do Produto": "tipo_do_produto",
    "País do Fabricante": "pais_do_fabricante",
}
DATAS_DOS_HOMOLOGADOS = {
    "Data da Homologação": "data_da_homologacao",
    "Data do Certificado de Conformidade Técnica": "data_do_certificado",
    "Data de Validade do Certificado": "validade_do_certificado",
}
COLUNAS_DA_TABELA_DOS_HOMOLOGADOS = (
    *CARIMBO,
    *DOS_HOMOLOGADOS.values(),
    *DATAS_DOS_HOMOLOGADOS.values(),
)


def ler_homologados(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os produtos homologados de solicitante pessoa jurídica e a contagem do que saiu.

    Uma linha por homologação, solicitante, modelo, nome comercial, certificado, tipo e datas (medido em
    14/11/2026: com isso só as linhas que diferem pelo nome do fabricante se repetem, e são contadas)."""
    bruta = ler_csv(conteudo, arquivista.COLUNAS_DOS_HOMOLOGADOS, "utf-8")
    tabela, contagem = comum.so_pessoa_juridica(bruta, "CNPJ do Solicitante")
    return base.pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(
                    tabela,
                    [
                        "Número de Homologação",
                        "cnpj14",
                        "Modelo",
                        "Nome Comercial",
                        "Certificado de Conformidade Técnica",
                        "Tipo do Produto",
                        "Data da Homologação",
                        "Data de Validade do Certificado",
                    ],
                ),
                **comum.com_cnpj(tabela["cnpj14"]),
                **base.renomeadas(tabela, DOS_HOMOLOGADOS),
                **{
                    nosso: data(tabela[da_fonte])
                    for da_fonte, nosso in DATAS_DOS_HOMOLOGADOS.items()
                },
            }
        ),
        contagem,
    )


# --- ANP: tancagem -----------------------------------------------------------------------------------------
# o nome da coluna sem acento (`motor.nome_da_coluna`) → o nosso; a ANP trocou o layout entre 2025 e 2026
# ("CodInstalacao" virou "CÓDIGO INSTALAÇÃO"), então cada coluna aceita os dois nomes
DA_TANCAGEM = {
    "DATA": "data_da_posicao",
    "UF": "uf",
    "MUNICIPIO": "municipio",
    "CNPJ": "cnpj14_bruto",
    "CODINSTALACAO": "codigo_da_instalacao",
    "CODIGOINSTALACAO": "codigo_da_instalacao",
    "SEGMENTO": "segmento",
    "DETALHEINSTALACAO": "detalhe_da_instalacao",
    "TAG": "tag",
    "TIPODAUNIDADE": "tipo_da_unidade",
    "GRUPODEPRODUTOS": "grupo_de_produtos",
    "TANCAGEMM3": "tancagem_m3",
}
TEXTOS_DA_TANCAGEM = (
    "uf",
    "municipio",
    "codigo_da_instalacao",
    "segmento",
    "detalhe_da_instalacao",
    "tag",
    "tipo_da_unidade",
    "grupo_de_produtos",
)
COLUNAS_DA_TABELA_DA_TANCAGEM = (
    *CARIMBO,
    *TEXTOS_DA_TANCAGEM,
    "data_da_posicao",
    "tancagem_m3",
)


def _texto_da_anp(conteudo: bytes) -> tuple[str, str]:
    """O texto e o separador: os CSVs de 2025 vêm em UTF-8 com vírgula, os de 2026 em Latin-1 com ponto e vírgula."""
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("latin-1")
    primeira = texto.split("\n", 1)[0]
    return texto, ";" if primeira.count(";") > primeira.count(",") else ","


def ler_tancagem(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os tanques de instalação de pessoa jurídica de um CSV da ANP e a contagem do que saiu."""
    texto, separador = _texto_da_anp(conteudo)
    bruta = pd.read_csv(
        io.StringIO(texto), sep=separador, dtype=str, keep_default_na=False
    )
    bruta.columns = [motor.nome_da_coluna(c) for c in bruta.columns]
    nossas = bruta[[c for c in bruta.columns if c in DA_TANCAGEM]].rename(
        columns=DA_TANCAGEM
    )
    faltam = sorted(set(DA_TANCAGEM.values()) - set(nossas.columns))
    if faltam:
        raise KeyError(f"a ANP deixou de trazer: {', '.join(faltam)}")
    nossas = nossas.apply(lambda serie: serie.str.strip())
    tabela, contagem = comum.so_pessoa_juridica(nossas, "cnpj14_bruto")
    return base.pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(
                    tabela,
                    ["cnpj14", "codigo_da_instalacao", "tag", "grupo_de_produtos"],
                ),
                **comum.com_cnpj(tabela["cnpj14"]),
                **{c: motor.sem_vazio(tabela[c]) for c in TEXTOS_DA_TANCAGEM},
                "data_da_posicao": data(tabela["data_da_posicao"]),
                "tancagem_m3": comum.numero(tabela["tancagem_m3"]),
            }
        ),
        contagem,
        {"tancagem_m3": "float64"},
    )


# --- os cadastros e a montagem -----------------------------------------------------------------------------
NOMES_DOS_REGIMES = {
    "rfb-renuncias-regime-presumido": "lucro_presumido",
    "rfb-renuncias-regime-real": "lucro_real",
    "rfb-renuncias-regime-arbitrado": "lucro_arbitrado",
    "rfb-renuncias-regime-imunes": "imunes_e_isentas",
}
NOMES_DO_PAT = {
    "mte-pat-beneficiarias": "beneficiarias",
    "mte-pat-facilitadoras": "facilitadoras",
    "mte-pat-fornecedoras": "fornecedoras",
}

CADASTROS_DO_REGIME = tuple(
    base.cadastro(TABELA_DO_REGIME, nome, fonte, ler_regime, COLUNAS_DO_REGIME)
    for fonte, nome in NOMES_DOS_REGIMES.items()
)
CADASTROS_DO_PAT = tuple(
    base.cadastro(
        TABELA_DO_PAT,
        nome,
        fonte,
        ler_pat,
        COLUNAS_DA_TABELA_DO_PAT,
        ("data_do_cadastro",),
        achar=base.todos_os_retratos(fonte),
    )
    for fonte, nome in NOMES_DO_PAT.items()
)
CADASTRO_DA_TAH = base.cadastro(
    TABELA_DA_TAH,
    "tah",
    FONTE_DA_TAH,
    ler_tah,
    COLUNAS_DA_TABELA_DA_TAH,
    ("data_da_quitacao",),
)
CADASTRO_DOS_PADOS = base.cadastro(
    TABELA_DOS_PADOS, "pados", FONTE_DOS_PADOS, ler_pados, COLUNAS_DA_TABELA_DOS_PADOS
)
CADASTRO_DOS_HOMOLOGADOS = base.cadastro(
    TABELA_DOS_HOMOLOGADOS,
    "homologados",
    FONTE_DOS_HOMOLOGADOS,
    ler_homologados,
    COLUNAS_DA_TABELA_DOS_HOMOLOGADOS,
    tuple(DATAS_DOS_HOMOLOGADOS.values()),
)
CADASTRO_DA_TANCAGEM = base.cadastro(
    TABELA_DA_TANCAGEM,
    "tancagem",
    FONTE_DA_TANCAGEM,
    ler_tancagem,
    COLUNAS_DA_TABELA_DA_TANCAGEM,
    ("data_da_posicao",),
    achar=base.todos_os_retratos(FONTE_DA_TANCAGEM),
)
CADASTROS = (
    *CADASTROS_DO_REGIME,
    *CADASTROS_DO_PAT,
    CADASTRO_DA_TAH,
    CADASTRO_DOS_PADOS,
    CADASTRO_DOS_HOMOLOGADOS,
    CADASTRO_DA_TANCAGEM,
)


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
