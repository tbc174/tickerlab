"""Indicadores das distribuidoras de energia da ANEEL (meta das 300 tabelas pelo CNPJ, linha 904): a
inadimplência por indicador e mês (fonte `aneel-inadimplencia`) e os indicadores comerciais do INDGER por
município e mês (fonte `aneel-fiscalizacao`). A ANEEL publica cada arquivo inteiro a cada vez (um
retrato); `base/retratos.py` junta os retratos numa tabela que só cresce.

- **Formato** (conferido em 13/11/2026 nos arquivos guardados): `;`, tudo entre aspas, linha CRLF,
  vírgula decimal (às vezes sem zero à esquerda: `,000000000`). A inadimplência traz a data de geração
  em `DD-MM-AAAA`; o INDGER e o domínio dos indicadores, em `AAAA-MM-DD`.
- **Descrição do indicador**: do domínio (`dominio-indicadores.csv`, da mesma fonte) guardado até o dia
  do retrato, o mais novo (o de depois seria olhar o futuro). O domínio é genérico da ANEEL: sigla que não
  está nele fica sem descrição. A descrição é rótulo, não valor: não entra na comparação dos retratos.
- **Só pessoa jurídica com CNPJ de DV certo** (ADR 0075): CPF e CNPJ que não fecha o DV saem e são
  contados. Nome do agente por extenso (`NomAgente`) e a hora da carga (`DthCarga`) ficam de fora.
- **Sem olhar o futuro** (`disponivel_no_primeiro`): o primeiro retrato vale desde a data de geração do
  conjunto, nunca depois do dia do retrato. A data de geração muda a cada regeração: fica numa coluna
  auxiliar (`gerado_em`) que o `juntar` carrega sem comparar e que não é gravada; se fosse um valor,
  cada retrato semanal repetiria o milhão de linhas da inadimplência.

Sem Streamlit; pandas só.
"""

import io
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cadastros_em_retrato
from base import cnpj as cnpjs
from base import retratos as motor

FONTE_DA_INADIMPLENCIA = "aneel-inadimplencia"
FONTE_COMERCIAL = "aneel-fiscalizacao"
TABELA_DA_INADIMPLENCIA = "aneel_inadimplencia"
TABELA_COMERCIAL = "aneel_indicadores_comerciais"
ARQUIVO_DA_INADIMPLENCIA = (
    "/inadimplencia.csv"  # com a barra: a fonte guarda também `dm-inadimplencia.pdf`
)
ARQUIVO_DO_DOMINIO = "/dominio-indicadores.csv"
ARQUIVO_COMERCIAL = "/indger-dados-comerciais.csv"
SEPARADOR = ";"
CODIFICACAO = "utf-8-sig"
GERADO_NA_INADIMPLENCIA = "%d-%m-%Y"
FORMATO_DA_DATA = "%Y-%m-%d"
DIGITOS_DO_MUNICIPIO = 7
GERADO_EM = "gerado_em"  # auxiliar: só para `disponivel_no_primeiro`; não é comparado nem gravado

COLUNAS_DA_INADIMPLENCIA = (
    "id_na_fonte", "cnpj", "cnpj_basico", "sigla_do_agente", "indicador", "descricao_do_indicador",
    "referencia", "valor",
)  # fmt: skip
VALORES_DA_INADIMPLENCIA = [
    "cnpj", "sigla_do_agente", "indicador", "referencia", "valor", "consta",
]  # fmt: skip
NUMEROS_COMERCIAIS = {
    "QtdUCAtiva": "unidades_ativas",
    "QtdUCAtivaFat": "unidades_faturadas",
    "QtdFatura": "faturas",
    "QtdFaturaSemLeitura": "faturas_sem_leitura",
    "QtdRefaturamento": "refaturamentos",
    "QtdSolicRessarcimentoDano": "pedidos_de_ressarcimento_de_dano",
    "QtdRessarcIndeferido": "ressarcimentos_indeferidos",
    "VlrPagoRessarcDano": "valor_pago_de_ressarcimento",
    "QtdPostoAtendimento": "postos_de_atendimento",
    "QtdUCSuspInadimplemento": "unidades_suspensas_por_inadimplencia",
    "QtdSuspIndev": "suspensoes_indevidas",
    "VlrTotCompSuspIndevida": "valor_de_compensacao_por_suspensao_indevida",
}
COLUNAS_COMERCIAIS = (
    "id_na_fonte", "cnpj", "cnpj_basico", "sigla_do_agente", "tipo_de_outorga", "referencia",
    "municipio_ibge", *NUMEROS_COMERCIAIS.values(),
)  # fmt: skip
VALORES_COMERCIAIS = [
    "cnpj", "sigla_do_agente", "tipo_de_outorga", "referencia", "municipio_ibge",
    *NUMEROS_COMERCIAIS.values(), "consta",
]  # fmt: skip
DATAS = ("referencia",)
# tipo fixo mesmo quando a coluna vem toda vazia num retrato (sem domínio guardado, por exemplo)
TEXTOS_DA_INADIMPLENCIA = (
    "id_na_fonte",
    "cnpj",
    "cnpj_basico",
    "sigla_do_agente",
    "indicador",
    "descricao_do_indicador",
)
TEXTOS_COMERCIAIS = (
    "id_na_fonte",
    "cnpj",
    "cnpj_basico",
    "sigla_do_agente",
    "tipo_de_outorga",
    "municipio_ibge",
)


# --- leitura comum ----------------------------------------------------------------------------------
def ler_csv(conteudo: bytes) -> pd.DataFrame:
    """O CSV da ANEEL como texto, sem espaços nas pontas (nome de coluna e valor)."""
    bruta = pd.read_csv(
        io.BytesIO(conteudo),
        sep=SEPARADOR,
        encoding=CODIFICACAO,
        dtype=str,
        keep_default_na=False,
    )
    bruta.columns = [c.strip() for c in bruta.columns]
    return bruta.apply(lambda serie: serie.str.strip())


def documentos(numeros: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Para cada linha, o CNPJ de 14 caracteres (nulo se não for CNPJ de DV certo) e se é um CPF.

    Confere cada documento diferente uma vez só (são umas cem distribuidoras em um milhão de linhas)."""
    cnpj: dict[str, str] = {}
    cpf: set[str] = set()
    for numero in numeros.unique():
        completo = cnpjs.completo(numero)
        if completo and cnpjs.dv_confere(completo):
            cnpj[numero] = completo
        elif cnpjs.cpf_confere(re.sub(r"\D", "", numero)):
            cpf.add(numero)
    return numeros.map(cnpj), numeros.isin(cpf)


def so_pessoa_juridica(
    bruta: pd.DataFrame, coluna: str
) -> tuple[pd.DataFrame, dict[str, int]]:
    """As linhas com CNPJ de DV certo (o CNPJ de 14 caracteres em `cnpj14`) e quantas saíram."""
    cnpj, de_cpf = documentos(bruta[coluna])
    valido = cnpj.notna()
    contagem = {
        "linhas": len(bruta),
        "pessoa_fisica": int(de_cpf.sum()),
        "cnpj_invalido": int((~valido & ~de_cpf).sum()),
    }
    return bruta[valido].assign(cnpj14=cnpj[valido]), contagem


def numero(texto: pd.Series) -> pd.Series:
    """Vírgula decimal (`2884,00`, `,000000000`) em float; vazio vira nulo."""
    return pd.to_numeric(texto.str.replace(",", ".", regex=False), errors="coerce")


def sem_repetir(tabela: pd.DataFrame, contagem: dict[str, int]) -> pd.DataFrame:
    """Uma linha por `id_na_fonte` dentro do retrato (a primeira); as repetidas são contadas."""
    repetido = tabela["id_na_fonte"].duplicated(keep="first")
    contagem["id_repetido"] = int(repetido.sum())
    return tabela[~repetido]


def com_cnpj(cnpj14: pd.Series) -> dict[str, pd.Series]:
    """As colunas `cnpj` (formatado) e `cnpj_basico` a partir do CNPJ de 14 caracteres."""
    return {
        "cnpj": cnpj14.map(cnpjs.formatar),
        "cnpj_basico": cnpj14.str[: cnpjs.TAMANHO_DA_RAIZ],
    }


# --- inadimplência ----------------------------------------------------------------------------------
def ler_dominio(conteudo: bytes) -> dict[str, str]:
    """A descrição de cada sigla de indicador no domínio da ANEEL (a primeira, se repetir)."""
    bruta = ler_csv(conteudo)
    validas = bruta[bruta["SigIndicador"].ne("")].drop_duplicates(
        "SigIndicador", keep="first"
    )
    return dict(zip(validas["SigIndicador"], validas["DscIndicador"], strict=True))


def _referencia_do_mes(ano: pd.Series, mes: pd.Series) -> pd.Series:
    """O primeiro dia do mês (`AnoIndice`, `NumPeriodoIndice`); fora do calendário vira nulo."""
    partes = pd.DataFrame(
        {
            "year": pd.to_numeric(ano, errors="coerce"),
            "month": pd.to_numeric(mes, errors="coerce"),
            "day": 1,
        }
    )
    return pd.to_datetime(partes, errors="coerce")


def ler_inadimplencia(
    conteudo: bytes, descricoes: Mapping[str, str]
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os indicadores de inadimplência de pessoa jurídica de um retrato e a contagem do que saiu.

    `descricoes`: sigla do indicador -> descrição (`ler_dominio`); a sigla sem descrição fica vazia."""
    tabela, contagem = so_pessoa_juridica(ler_csv(conteudo), "NumCNPJ")
    referencia = _referencia_do_mes(tabela["AnoIndice"], tabela["NumPeriodoIndice"])
    valor = numero(tabela["VlrIndiceEnviado"])
    aproveitada = referencia.notna() & valor.notna()
    contagem["referencia_invalida"] = int(referencia.isna().sum())
    contagem["sem_valor"] = int((referencia.notna() & valor.isna()).sum())
    tabela = tabela[aproveitada]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": motor.chave(
                tabela, ["cnpj14", "SigIndicador", "AnoIndice", "NumPeriodoIndice"]
            ),
            **com_cnpj(tabela["cnpj14"]),
            "sigla_do_agente": motor.sem_vazio(tabela["SigAgente"]),
            "indicador": tabela["SigIndicador"],
            "descricao_do_indicador": tabela["SigIndicador"].map(dict(descricoes)),
            "referencia": referencia[aproveitada],
            "valor": valor[aproveitada],
            GERADO_EM: pd.to_datetime(
                tabela["DatGeracaoConjuntoDados"],
                format=GERADO_NA_INADIMPLENCIA,
                errors="coerce",
            ),
        }
    )
    tipos = {**dict.fromkeys(TEXTOS_DA_INADIMPLENCIA, "string"), "valor": "float64"}
    return sem_repetir(pronta, contagem).astype(tipos).reset_index(drop=True), contagem


@dataclass(frozen=True)
class RetratoComDominio(motor.Retrato):
    """Um retrato da inadimplência com o domínio dos indicadores guardado até o dia dele."""

    dominio: Path | None = None


def _dominio_ate(dominios: list[motor.Retrato], dia: date) -> Path | None:
    """O domínio mais novo guardado até `dia` (os retratos vêm do mais antigo ao mais novo)."""
    ate_o_dia = [d for d in dominios if d.dia <= dia]
    return ate_o_dia[-1].caminho if ate_o_dia else None


def achar_inadimplencia(conexao: sa.Connection) -> tuple[list[motor.Retrato], int]:
    """Os retratos da inadimplência (do endereço mais novo), cada um com o seu domínio."""
    dados, ignorados = cadastros_em_retrato._do_endereco_mais_novo(
        motor.retratos(conexao, FONTE_DA_INADIMPLENCIA, ARQUIVO_DA_INADIMPLENCIA)
    )
    dominios = motor.retratos(conexao, FONTE_DA_INADIMPLENCIA, ARQUIVO_DO_DOMINIO)
    com_dominio: list[motor.Retrato] = [
        RetratoComDominio(
            r.url, r.sha256, r.caminho, r.baixado_em, _dominio_ate(dominios, r.dia)
        )
        for r in dados
    ]
    return com_dominio, ignorados


def ler_retrato_da_inadimplencia(
    retrato: motor.Retrato,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Um retrato guardado da inadimplência, com a descrição do domínio que ele tiver."""
    dominio = retrato.dominio if isinstance(retrato, RetratoComDominio) else None
    descricoes = ler_dominio(motor.original(dominio)) if dominio else {}
    return ler_inadimplencia(motor.original(retrato.caminho), descricoes)


# --- indicadores comerciais (INDGER) ----------------------------------------------------------------
def _municipio(codigo: pd.Series) -> pd.Series:
    """O código IBGE de 7 dígitos; o resto (a fonte manda `0` em algumas linhas) fica vazio."""
    certo = codigo.str.fullmatch(rf"\d{{{DIGITOS_DO_MUNICIPIO}}}")
    return codigo.where(certo, None)


def ler_comerciais(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os indicadores comerciais de pessoa jurídica de um retrato do INDGER e a contagem do que saiu."""
    tabela, contagem = so_pessoa_juridica(ler_csv(conteudo), "NumCNPJ")
    referencia = pd.to_datetime(
        tabela["DatReferenciaInformada"], format=FORMATO_DA_DATA, errors="coerce"
    )
    contagem["referencia_invalida"] = int(referencia.isna().sum())
    tabela, referencia = tabela[referencia.notna()], referencia[referencia.notna()]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": motor.chave(
                tabela, ["cnpj14", "CodMunicipioIBGE", "DatReferenciaInformada"]
            ),
            **com_cnpj(tabela["cnpj14"]),
            "sigla_do_agente": motor.sem_vazio(tabela["SigAgente"]),
            "tipo_de_outorga": motor.sem_vazio(tabela["NomTipoOutorga"]),
            "referencia": referencia,
            "municipio_ibge": _municipio(tabela["CodMunicipioIBGE"]),
            **{
                nosso: numero(tabela[da_fonte])
                for da_fonte, nosso in NUMEROS_COMERCIAIS.items()
            },
            GERADO_EM: pd.to_datetime(
                tabela["DatGeracaoConjuntoDados"],
                format=FORMATO_DA_DATA,
                errors="coerce",
            ),
        }
    )
    tipos = {
        **dict.fromkeys(TEXTOS_COMERCIAIS, "string"),
        **dict.fromkeys(NUMEROS_COMERCIAIS.values(), "float64"),
    }
    return sem_repetir(pronta, contagem).astype(tipos).reset_index(drop=True), contagem


# --- junção dos retratos ----------------------------------------------------------------------------
def disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """A data de geração do conjunto, nunca depois do retrato; sem ela, o dia do retrato."""
    return novos[GERADO_EM].clip(upper=dia).fillna(dia)


def juntar_inadimplencia(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos da inadimplência numa tabela de valores, e quantos foram pulados."""
    return motor.juntar(lidos, VALORES_DA_INADIMPLENCIA, disponivel_no_primeiro)


def juntar_comerciais(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos do INDGER comercial numa tabela de valores, e quantos foram pulados."""
    return motor.juntar(lidos, VALORES_COMERCIAIS, disponivel_no_primeiro)


CADASTRO_DA_INADIMPLENCIA = cadastros_em_retrato.Cadastro(
    tabela=TABELA_DA_INADIMPLENCIA,
    nome="inadimplencia",
    fonte=FONTE_DA_INADIMPLENCIA,
    ler=ler_retrato_da_inadimplencia,
    juntar=juntar_inadimplencia,
    colunas=COLUNAS_DA_INADIMPLENCIA,
    datas=DATAS,
    achar=achar_inadimplencia,
)
CADASTRO_COMERCIAL = cadastros_em_retrato.Cadastro(
    tabela=TABELA_COMERCIAL,
    nome="comerciais",
    fonte=FONTE_COMERCIAL,
    ler=lambda retrato: ler_comerciais(motor.original(retrato.caminho)),
    juntar=juntar_comerciais,
    colunas=COLUNAS_COMERCIAIS,
    datas=DATAS,
    url_termina_em=ARQUIVO_COMERCIAL,
)
CADASTROS = (CADASTRO_DA_INADIMPLENCIA, CADASTRO_COMERCIAL)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/aneel_inadimplencia/inadimplencia.parquet` e
    `<pasta>/aneel_indicadores_comerciais/comerciais.parquet` (um retrato por baixada, só CNPJ)."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
