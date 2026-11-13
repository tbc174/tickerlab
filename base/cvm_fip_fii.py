"""Informes dos FIP e dos FII e o cadastro dos administradores de FII, da CVM (linha 904 da fila, lote 1
da meta de 300 tabelas pelo CNPJ). Quatro tabelas, todas pelo CNPJ do fundo (ou do administrador):

- **`fip_informe`** (fontes `cvm-fip-trimestral`, de 2021 a 2023, e `cvm-fip-quadrimestral`, de 2024 em
  diante): o mesmo informe dos Fundos de Investimento em Participações antes e depois da Resolução CVM
  175, numa tabela só. Patrimônio, cotistas, capital comprometido, subscrito e integralizado.
- **`fii_informe_mensal`** (fonte `cvm-fii-mensal`): o informe mensal dos FII, a parte geral (segmento,
  mandato, gestão, ISIN, administrador pelo CNPJ) junto do complemento (cotistas, ativo, patrimônio, cota,
  taxas, rentabilidade e dividend yield do mês).
- **`fii_ativos`** (fonte `cvm-fii-trimestral`, arquivo `ativo`): os títulos e valores mobiliários que cada
  FII declara ter, com o CNPJ do emissor. Liga uma empresa aos FII que carregam os papéis dela.
- **`fii_administradores`** (fonte `cvm-fii-administradores`): quem a CVM registrou para administrar FII,
  com a situação e as datas do registro e do cancelamento.

Formato conferido em 13/11/2026 nos arquivos guardados: `;`, Latin-1, um arquivo (ou ZIP) por ano, que a
CVM republica inteiro. Cada arquivo do ano vira um Parquet (`<pasta>/<tabela>/<arquivo>.parquet`), montado
como cadastro em retrato (`base/cadastros_em_retrato.py`): o valor que muda entre uma baixada e outra vira
linha nova, e o registro que some ganha `consta` falso.

- **Sem pessoa** (ADR 0075): só CNPJ de DV certo; contato, endereço e nome do administrador ficam de fora
  (o administrador entra pelo CNPJ). `trata_como_pessoa` marca o empresário individual e o MEI pela Receita;
  em `fii_ativos`, a linha também é marcada quando o emissor é pessoa, e o nome do emissor só entra quando o
  CNPJ dele fecha o DV.
- **Sem olhar o futuro**: nos FII, `disponivel_em` é a `Data_Entrega` do informe (o dia em que chegou à
  CVM), nunca depois do arquivo; o informe dos FIP e o cadastro não dizem quando cada linha saiu, então vale o
  dia em que o arquivista viu o arquivo (a leitura mais estreita).

Sem Streamlit; pandas só.
"""

import io
import zipfile
from collections.abc import Callable, Collection
from datetime import datetime
from pathlib import Path, PurePosixPath

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cadastros_em_retrato
from base import cnpj as cnpjs
from base import retratos as motor

SEPARADOR = ";"
CODIFICACAO = "latin-1"
FORMATO_DA_DATA = "%Y-%m-%d"
PASTA_DOS_DADOS = (
    "/DADOS/"  # a CVM guarda o dicionário em `/META/`, com o mesmo final de nome
)

Leitor = Callable[[bytes, pd.Timestamp], tuple[pd.DataFrame, dict[str, int]]]


def cnpj_ou_vazio(serie: pd.Series) -> pd.Series:
    """Os 14 caracteres do CNPJ que fecha o DV; o resto (CPF, vazio, DV errado) vira nulo."""
    completos = serie.map(cnpjs.completo)
    certos = completos.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c))
    return completos.where(certos.astype(bool), None)


def formatado(serie: pd.Series) -> pd.Series:
    """O CNPJ de DV certo, formatado (`12.345.678/0001-90`); o resto, nulo."""
    return cnpj_ou_vazio(serie).map(
        lambda c: cnpjs.formatar(c) if isinstance(c, str) else None
    )


def _ler_csv(conteudo: bytes, colunas: Collection[str]) -> pd.DataFrame:
    """O CSV da CVM só com as `colunas` (a que faltar vem vazia), tudo como texto sem espaço nas pontas."""
    bruta = pd.read_csv(
        io.BytesIO(conteudo),
        sep=SEPARADOR,
        encoding=CODIFICACAO,
        dtype=str,
        keep_default_na=False,
        usecols=lambda c: c.strip() in colunas,
    )
    bruta = bruta.rename(columns=str.strip)
    for coluna in colunas:
        if coluna not in bruta:
            bruta[coluna] = ""  # coluna que a CVM não mandou naquele arquivo
    return bruta.apply(lambda serie: serie.str.strip())


def _membro(zip_: zipfile.ZipFile, trecho: str) -> bytes | None:
    """O CSV do ZIP anual com `trecho` no nome (`_geral_`, `_complemento_`, `_ativo_`...)."""
    nome = next(
        (n for n in zip_.namelist() if trecho in n and n.endswith(".csv")), None
    )
    return None if nome is None else zip_.read(nome)


def _numeros(tabela: pd.DataFrame, nomes: dict[str, str]) -> dict[str, pd.Series]:
    return {
        nova: pd.to_numeric(tabela[velha].str.replace(",", "."), errors="coerce")
        for velha, nova in nomes.items()
    }


def _textos(tabela: pd.DataFrame, nomes: dict[str, str]) -> dict[str, pd.Series]:
    return {nova: motor.sem_vazio(tabela[velha]) for velha, nova in nomes.items()}


def _datas(tabela: pd.DataFrame, nomes: dict[str, str]) -> dict[str, pd.Series]:
    return {
        nova: pd.to_datetime(tabela[velha], format=FORMATO_DA_DATA, errors="coerce")
        for velha, nova in nomes.items()
    }


def _inteiro(coluna: str) -> bool:
    return coluna == "versao" or coluna.startswith("cotistas")


def _com_tipos(tabela: pd.DataFrame, colunas: tuple[str, ...]) -> pd.DataFrame:
    """As `colunas`, nesta ordem e com tipo fixo (texto, inteiro, decimal ou data): os Parquets de cada
    ano são lidos juntos pela porta, e um ano sem nenhum valor numa coluna não pode mudar o tipo dela."""
    pronta = tabela[list(colunas)].reset_index(drop=True)
    for coluna in pronta.columns:
        serie = pronta[coluna]
        if pd.api.types.is_datetime64_any_dtype(serie):
            continue
        if _inteiro(coluna):
            pronta[coluna] = pd.to_numeric(serie).round().astype("Int64")
        elif pd.api.types.is_numeric_dtype(serie):
            pronta[coluna] = serie.astype("float64")
        else:
            pronta[coluna] = serie.astype("string")
    return pronta


def _do_fundo(cnpj: pd.Series) -> dict[str, pd.Series]:
    return {
        "cnpj": cnpj.map(cnpjs.formatar),
        "cnpj_basico": cnpj.str[: cnpjs.TAMANHO_DA_RAIZ],
    }


def _entregue_ate_o_dia(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """A `Data_Entrega` do informe, nunca depois do arquivo; sem ela, o dia do arquivo."""
    entrega = pd.to_datetime(novos["entregue_em"])
    return entrega.where(entrega <= dia, dia).fillna(dia)


def _no_dia_do_arquivo(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """O arquivo não diz quando cada linha saiu: vale o dia em que foi visto."""
    return pd.Series(dia, index=novos.index)


# --- FIP ---------------------------------------------------------------------------------------------

TABELA_DOS_FIP = "fip_informe"
FONTES_DOS_FIP = {
    "cvm-fip-trimestral": "trimestral",
    "cvm-fip-quadrimestral": "quadrimestral",
}
CNPJ_DO_FIP = ("CNPJ_FUNDO", "CNPJ_FUNDO_CLASSE")  # antes e depois da Resolução CVM 175
TEXTOS_DO_FIP = {
    "TP_FUNDO_CLASSE": "tipo_fundo_classe",
    "DENOM_SOCIAL": "nome_do_fundo",
    "ENTID_INVEST": "entidade_de_investimento",
    "PUBLICO_ALVO": "publico_alvo",
}
NUMEROS_DO_FIP = {
    "VL_PATRIM_LIQ": "patrimonio_liquido",
    "QT_COTA": "cotas",
    "VL_PATRIM_COTA": "valor_patrimonial_da_cota",
    "NR_COTST": "cotistas",
    "VL_CAP_COMPROM": "capital_comprometido",
    "VL_CAP_SUBSCR": "capital_subscrito",
    "VL_CAP_INTEGR": "capital_integralizado",
    "VL_INVEST_FIP_COTA": "investido_em_cotas_de_fip",
    "NR_COTST_SUBSCR_PF": "cotistas_pessoa_fisica",
    "NR_COTST_SUBSCR_PJ_NAO_FINANC": "cotistas_empresa_nao_financeira",
    "NR_COTST_SUBSCR_INVNR": "cotistas_nao_residentes",
    "NR_COTST_SUBSCR_EFPC": "cotistas_previdencia_fechada",
    "NR_COTST_SUBSCR_RPPS": "cotistas_regime_proprio",
}
DATAS_DO_FIP = {"DT_COMPTC": "competencia"}
COLUNAS_DO_FIP = (
    "id_na_fonte", "cnpj", "cnpj_basico", "competencia", "periodicidade",
    *TEXTOS_DO_FIP.values(), *NUMEROS_DO_FIP.values(),
)  # fmt: skip


def ler_fip(conteudo: bytes, periodicidade: str) -> tuple[pd.DataFrame, dict[str, int]]:
    """Um arquivo anual do informe dos FIP e a contagem do que ficou de fora."""
    bruta = _ler_csv(
        conteudo, [*CNPJ_DO_FIP, *TEXTOS_DO_FIP, *NUMEROS_DO_FIP, *DATAS_DO_FIP]
    )
    cnpj = cnpj_ou_vazio(
        bruta["CNPJ_FUNDO"].where(
            bruta["CNPJ_FUNDO"].ne(""), bruta["CNPJ_FUNDO_CLASSE"]
        )
    )
    valido = cnpj.notna()
    tabela = bruta[valido].assign(_cnpj=cnpj[valido])
    pronta = pd.DataFrame(
        {
            **_do_fundo(tabela["_cnpj"]),
            **_datas(tabela, DATAS_DO_FIP),
            "periodicidade": periodicidade,
            **_textos(tabela, TEXTOS_DO_FIP),
            **_numeros(tabela, NUMEROS_DO_FIP),
        }
    )
    pronta = pronta.assign(
        id_na_fonte=pronta["cnpj"]
        + "|"
        + pronta["competencia"].dt.strftime(FORMATO_DA_DATA).fillna("")
    )
    repetido = pronta["id_na_fonte"].duplicated(keep="last")
    contagem = {
        "linhas": len(bruta),
        "cnpj_invalido": int((~valido).sum()),
        "repetido_no_arquivo": int(repetido.sum()),
    }
    return _com_tipos(pronta[~repetido], COLUNAS_DO_FIP), contagem


# --- FII: informe mensal --------------------------------------------------------------------------

TABELA_DO_MENSAL = "fii_informe_mensal"
FONTE_DO_MENSAL = "cvm-fii-mensal"
CHAVE_DO_INFORME = ["CNPJ_Fundo_Classe", "Data_Referencia", "Versao"]
TEXTOS_DO_MENSAL = {
    "Tipo_Fundo_Classe": "tipo_fundo_classe",
    "Nome_Fundo_Classe": "nome_do_fundo",
    "Publico_Alvo": "publico_alvo",
    "Codigo_ISIN": "codigo_isin",
    "Fundo_Exclusivo": "fundo_exclusivo",
    "Mandato": "mandato",
    "Segmento_Atuacao": "segmento_de_atuacao",
    "Tipo_Gestao": "tipo_de_gestao",
    "Prazo_Duracao": "prazo_de_duracao",
    "Mercado_Negociacao_Bolsa": "negocia_em_bolsa",
}
DATAS_DO_MENSAL = {
    "Data_Referencia": "referencia",
    "Data_Entrega": "entregue_em",
    "Data_Funcionamento": "funciona_desde",
}
NUMEROS_DO_MENSAL = {
    "Total_Numero_Cotistas": "cotistas",
    "Numero_Cotistas_Pessoa_Fisica": "cotistas_pessoa_fisica",
    "Valor_Ativo": "valor_do_ativo",
    "Patrimonio_Liquido": "patrimonio_liquido",
    "Cotas_Emitidas": "cotas_emitidas",
    "Valor_Patrimonial_Cotas": "valor_patrimonial_da_cota",
    "Percentual_Despesas_Taxa_Administracao": "taxa_de_administracao_pct",
    "Percentual_Rentabilidade_Efetiva_Mes": "rentabilidade_efetiva_no_mes",
    "Percentual_Rentabilidade_Patrimonial_Mes": "rentabilidade_patrimonial_no_mes",
    "Percentual_Dividend_Yield_Mes": "dividend_yield_no_mes",
}
COLUNAS_DO_MENSAL = (
    "id_na_fonte", "cnpj", "cnpj_basico", "referencia", "versao", "entregue_em",
    *TEXTOS_DO_MENSAL.values(), "funciona_desde", "cnpj_administrador",
    *NUMEROS_DO_MENSAL.values(),
)  # fmt: skip


def _id_do_informe(tabela: pd.DataFrame) -> pd.Series:
    return (
        tabela["cnpj"]
        + "|"
        + tabela["referencia"].dt.strftime(FORMATO_DA_DATA).fillna("")
        + "|"
        + tabela["versao"].astype(str)
    )


def _versao(tabela: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(tabela["Versao"], errors="coerce").astype("Int64")


def ler_mensal(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """O ZIP anual do informe mensal dos FII (geral + complemento) e a contagem do que ficou de fora."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zip_:
        geral, complemento = _membro(zip_, "_geral_"), _membro(zip_, "_complemento_")
    if geral is None:
        return pd.DataFrame(columns=list(COLUNAS_DO_MENSAL)), {"linhas": 0}
    bruta = _ler_csv(
        geral,
        [
            *CHAVE_DO_INFORME,
            *TEXTOS_DO_MENSAL,
            "Data_Entrega",
            "Data_Funcionamento",
            "CNPJ_Administrador",
        ],
    )
    numeros = (
        _ler_csv(complemento or b"", [*CHAVE_DO_INFORME, *NUMEROS_DO_MENSAL])
        if complemento
        else None
    )
    if numeros is not None:
        numeros = numeros.drop_duplicates(CHAVE_DO_INFORME, keep="last")
        bruta = bruta.merge(numeros, on=CHAVE_DO_INFORME, how="left").fillna("")
    else:
        bruta = bruta.assign(**dict.fromkeys(NUMEROS_DO_MENSAL, ""))
    cnpj = cnpj_ou_vazio(bruta["CNPJ_Fundo_Classe"])
    valido = cnpj.notna()
    tabela = bruta[valido].assign(_cnpj=cnpj[valido])
    pronta = pd.DataFrame(
        {
            **_do_fundo(tabela["_cnpj"]),
            "versao": _versao(tabela),
            **_datas(tabela, DATAS_DO_MENSAL),
            **_textos(tabela, TEXTOS_DO_MENSAL),
            "cnpj_administrador": formatado(tabela["CNPJ_Administrador"]),
            **_numeros(tabela, NUMEROS_DO_MENSAL),
        }
    )
    pronta = pronta.assign(id_na_fonte=_id_do_informe(pronta))
    repetido = pronta["id_na_fonte"].duplicated(keep="last")
    contagem = {
        "linhas": len(bruta),
        "cnpj_invalido": int((~valido).sum()),
        "repetido_no_arquivo": int(repetido.sum()),
    }
    return _com_tipos(pronta[~repetido], COLUNAS_DO_MENSAL), contagem


# --- FII: ativos do informe trimestral ------------------------------------------------------------

TABELA_DOS_ATIVOS = "fii_ativos"
FONTE_DO_TRIMESTRAL = "cvm-fii-trimestral"
TEXTOS_DO_ATIVO = {
    "Tipo": "tipo_do_ativo",
    "Emissao": "emissao",
    "Serie": "serie",
    "Codigo_Acao": "codigo",
    "Nome_Ativo": "nome_do_ativo",
}
NUMEROS_DO_ATIVO = {"Quantidade": "quantidade", "Valor": "valor"}
COLUNAS_DOS_ATIVOS = (
    "id_na_fonte", "cnpj", "cnpj_basico", "referencia", "versao", "entregue_em",
    "cnpj_emissor", "cnpj_basico_emissor", "emissor", *TEXTOS_DO_ATIVO.values(), "vencimento",
    *NUMEROS_DO_ATIVO.values(),
)  # fmt: skip
# a linha é de pessoa se o fundo ou o emissor for empresário individual ou MEI
RAIZES_DE_PESSOA_DOS_ATIVOS = ("cnpj_basico", "cnpj_basico_emissor")


def _entregas(geral: bytes | None) -> pd.DataFrame:
    """A `Data_Entrega` de cada informe trimestral (só a chave e a data; o resto do arquivo não entra)."""
    if geral is None:
        return pd.DataFrame(columns=[*CHAVE_DO_INFORME, "Data_Entrega"])
    return _ler_csv(geral, [*CHAVE_DO_INFORME, "Data_Entrega"]).drop_duplicates(
        CHAVE_DO_INFORME, keep="last"
    )


def _id_do_ativo(tabela: pd.DataFrame) -> pd.Series:
    """Fundo, mês e versão do informe, o ativo e, se o mesmo ativo aparece duas vezes, a ordem dele."""
    descricao = motor.chave(
        tabela.fillna(""),
        [
            "cnpj_emissor",
            "tipo_do_ativo",
            "emissao",
            "serie",
            "codigo",
            "nome_do_ativo",
        ],
    )
    base = _id_do_informe(tabela) + "|" + descricao
    return base + "|" + base.groupby(base).cumcount().astype(str)


def ler_ativos(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os ativos do ZIP anual do informe trimestral dos FII e a contagem do que ficou de fora."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zip_:
        ativos, geral = _membro(zip_, "_ativo_2"), _membro(zip_, "_geral_")
    if ativos is None:
        return pd.DataFrame(columns=list(COLUNAS_DOS_ATIVOS)), {"linhas": 0}
    bruta = (
        _ler_csv(
            ativos,
            [
                *CHAVE_DO_INFORME,
                "Emissor",
                "CNPJ_Emissor",
                "Data_Vencimento",
                *TEXTOS_DO_ATIVO,
                *NUMEROS_DO_ATIVO,
            ],
        )
        .merge(_entregas(geral), on=CHAVE_DO_INFORME, how="left")
        .fillna("")
    )
    cnpj = cnpj_ou_vazio(bruta["CNPJ_Fundo_Classe"])
    valido = cnpj.notna()
    tabela = bruta[valido].assign(_cnpj=cnpj[valido])
    emissor = cnpj_ou_vazio(tabela["CNPJ_Emissor"])
    pronta = pd.DataFrame(
        {
            **_do_fundo(tabela["_cnpj"]),
            "versao": _versao(tabela),
            **_datas(
                tabela, {"Data_Referencia": "referencia", "Data_Entrega": "entregue_em"}
            ),
            "cnpj_emissor": emissor.map(
                lambda c: cnpjs.formatar(c) if isinstance(c, str) else None
            ),
            "cnpj_basico_emissor": emissor.str[: cnpjs.TAMANHO_DA_RAIZ],
            # o nome só com o CNPJ do emissor de DV certo: sem ele, o nome pode ser de qualquer um
            "emissor": motor.sem_vazio(tabela["Emissor"]).where(emissor.notna(), None),
            **_textos(tabela, TEXTOS_DO_ATIVO),
            **_datas(tabela, {"Data_Vencimento": "vencimento"}),
            **_numeros(tabela, NUMEROS_DO_ATIVO),
        }
    )
    pronta = pronta.assign(id_na_fonte=_id_do_ativo(pronta))
    contagem = {
        "linhas": len(bruta),
        "cnpj_invalido": int((~valido).sum()),
        "emissor_sem_cnpj": int(emissor.isna().sum()),
    }
    return _com_tipos(pronta, COLUNAS_DOS_ATIVOS), contagem


# --- FII: administradores ---------------------------------------------------------------------------

TABELA_DOS_ADMINISTRADORES = "fii_administradores"
FONTE_DOS_ADMINISTRADORES = "cvm-fii-administradores"
ARQUIVO_DOS_ADMINISTRADORES = "/cad_adm_fii.csv"
TEXTOS_DO_ADMINISTRADOR = {
    "DENOM_SOCIAL": "razao_social",
    "DENOM_COMERC": "nome_comercial",
    "MOTIVO_CANCEL": "motivo_do_cancelamento",
    "SIT": "situacao",
    "UF": "uf",
}
DATAS_DO_ADMINISTRADOR = {
    "DT_REG": "registrado_em",
    "DT_CANCEL": "cancelado_em",
    "DT_INI_SIT": "situacao_desde",
}
COLUNAS_DOS_ADMINISTRADORES = (
    "id_na_fonte", "cnpj", "cnpj_basico", *TEXTOS_DO_ADMINISTRADOR.values(),
    *DATAS_DO_ADMINISTRADOR.values(),
)  # fmt: skip


def ler_administradores(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """O cadastro dos administradores de FII (sem endereço nem contato) e a contagem do que ficou de fora."""
    bruta = _ler_csv(
        conteudo, ["CNPJ", *TEXTOS_DO_ADMINISTRADOR, *DATAS_DO_ADMINISTRADOR]
    )
    cnpj = cnpj_ou_vazio(bruta["CNPJ"])
    valido = cnpj.notna()
    tabela = bruta[valido].assign(_cnpj=cnpj[valido])
    pronta = pd.DataFrame(
        {
            **_do_fundo(tabela["_cnpj"]),
            **_textos(tabela, TEXTOS_DO_ADMINISTRADOR),
            **_datas(tabela, DATAS_DO_ADMINISTRADOR),
        }
    )
    pronta = pronta.assign(id_na_fonte=pronta["cnpj"])
    repetido = pronta["id_na_fonte"].duplicated(keep="first")
    contagem = {
        "linhas": len(bruta),
        "cnpj_invalido": int((~valido).sum()),
        "repetido_no_arquivo": int(repetido.sum()),
    }
    return _com_tipos(pronta[~repetido], COLUNAS_DOS_ADMINISTRADORES), contagem


# --- montagem ---------------------------------------------------------------------------------------


def _juntador(
    colunas: tuple[str, ...], disponivel: motor.DisponivelNoPrimeiro
) -> cadastros_em_retrato.Juntador:
    """A junção dos retratos comparando todas as colunas menos o `id_na_fonte`, e o `consta`: sem ele,
    o registro que sai do arquivo não ganharia a linha `consta` falso (`base/retratos.py`)."""
    valores = (*colunas[1:], "consta")

    def juntar(
        lidos: list[tuple[motor.Retrato, pd.DataFrame]],
    ) -> tuple[pd.DataFrame, int]:
        return motor.juntar(lidos, valores, disponivel)

    return juntar


def _do_endereco(fonte: str, url: str) -> cadastros_em_retrato.Achador:
    def achar(conexao: sa.Connection) -> tuple[list[motor.Retrato], int]:
        return [r for r in motor.retratos(conexao, fonte) if r.url == url], 0

    return achar


def _enderecos(conexao: sa.Connection, fonte: str, final: str) -> list[str]:
    """Os endereços de dados da fonte (um por ano) que terminam em `final`, sem o dicionário da CVM."""
    return sorted(
        {
            r.url
            for r in motor.retratos(conexao, fonte, final)
            if PASTA_DOS_DADOS in r.url
        }
    )


def _por_arquivo(
    conexao: sa.Connection,
    tabela: str,
    fonte: str,
    final: str,
    ler: Callable[[bytes], tuple[pd.DataFrame, dict[str, int]]],
    colunas: tuple[str, ...],
    datas: tuple[str, ...],
    disponivel: motor.DisponivelNoPrimeiro,
    raizes_de_pessoa: tuple[str, ...] = ("cnpj_basico",),
) -> list[cadastros_em_retrato.Cadastro]:
    """Um cadastro por arquivo anual (`inf_mensal_fii_2024`...): cada ano é um retrato à parte."""
    return [
        cadastros_em_retrato.Cadastro(
            tabela=tabela,
            nome=PurePosixPath(url).stem,
            fonte=fonte,
            ler=lambda retrato: ler(motor.original(retrato.caminho)),
            juntar=_juntador(colunas, disponivel),
            colunas=colunas,
            datas=datas,
            achar=_do_endereco(fonte, url),
            raizes_de_pessoa=raizes_de_pessoa,
        )
        for url in _enderecos(conexao, fonte, final)
    ]


def cadastros(conexao: sa.Connection) -> tuple[cadastros_em_retrato.Cadastro, ...]:
    """Os cadastros das quatro tabelas, pelos arquivos que o arquivista guardou."""
    fip = [
        cadastro
        for fonte, periodicidade in FONTES_DOS_FIP.items()
        for cadastro in _por_arquivo(
            conexao,
            TABELA_DOS_FIP,
            fonte,
            ".csv",
            lambda conteudo, p=periodicidade: ler_fip(conteudo, p),
            COLUNAS_DO_FIP,
            ("competencia",),
            _no_dia_do_arquivo,
        )
    ]
    mensal = _por_arquivo(
        conexao, TABELA_DO_MENSAL, FONTE_DO_MENSAL, ".zip", ler_mensal,
        COLUNAS_DO_MENSAL, ("referencia", "entregue_em", "funciona_desde"), _entregue_ate_o_dia,
    )  # fmt: skip
    ativos = _por_arquivo(
        conexao, TABELA_DOS_ATIVOS, FONTE_DO_TRIMESTRAL, ".zip", ler_ativos,
        COLUNAS_DOS_ATIVOS, ("referencia", "entregue_em", "vencimento"), _entregue_ate_o_dia,
        RAIZES_DE_PESSOA_DOS_ATIVOS,
    )  # fmt: skip
    administradores = cadastros_em_retrato.Cadastro(
        tabela=TABELA_DOS_ADMINISTRADORES,
        nome="administradores",
        fonte=FONTE_DOS_ADMINISTRADORES,
        ler=lambda retrato: ler_administradores(motor.original(retrato.caminho)),
        juntar=_juntador(COLUNAS_DOS_ADMINISTRADORES, _no_dia_do_arquivo),
        colunas=COLUNAS_DOS_ADMINISTRADORES,
        datas=tuple(DATAS_DO_ADMINISTRADOR.values()),
        url_termina_em=ARQUIVO_DOS_ADMINISTRADORES,
    )
    return (*fip, *mensal, *ativos, administradores)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/<tabela>/<arquivo>.parquet` das quatro tabelas; arquivo sem baixada nova é pulado."""
    return cadastros_em_retrato.montar(
        cadastros(conexao), conexao, pasta, agora, pessoas, refazer
    )
