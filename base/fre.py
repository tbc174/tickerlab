"""Leitor do FRE (formulário de referência) da CVM: proventos e eventos de capital (série 2, PR 6).

O FRE aberto mudou com a Resolução CVM 59 (FRE de 2023 em diante): as tabelas de dividendos
distribuídos, desdobramentos e grupamentos, aumentos e reduções de capital e planos de recompra
**saíram**. Elas existem do FRE de 2010 ao de 2022, e é daí que vem o histórico; de 2023 em diante,
os dividendos pagos vêm do fluxo de caixa das demonstrações e as ações, da composição do capital.

- Só as tabelas de proventos e de eventos de capital são lidas: o FRE também traz nomes e dados de
  administradores, que não entram.
- De cada documento (empresa + data de referência) fica a versão mais nova do arquivo.
- O payout que a CVM informa vem em porcentagem e vira fração (50% → 0,50).
"""

import io
import re
import zipfile

import pandas as pd

CODIFICACAO_DA_CVM = "latin-1"
# o último FRE com as tabelas de eventos de capital (Resolução CVM 59): depois dele, um salto nas
# ações não tem evento para explicar (`src/fundamentalista.py`) e a carga para (`scripts/atualizar_fre.py`)
ULTIMO_ANO_COM_AS_TABELAS = 2022
DOCUMENTO = ["CNPJ_Companhia", "Data_Referencia"]
COLUNAS_DOS_PROVENTOS = (
    "cnpj", "referencia", "versao", "exercicio", "lucro_ajustado", "dividendo_total", "payout",
    "dividendos", "jcp",
)  # fmt: skip
COLUNAS_DOS_EVENTOS = (
    "cnpj", "referencia", "versao", "tipo", "data", "acoes_antes", "acoes_depois", "fator",
    "acoes_novas", "valor",
)  # fmt: skip


def _ler(conteudo_do_zip: bytes, tabela: str) -> pd.DataFrame:
    """A tabela `fre_cia_aberta_<tabela>_<ano>.csv` (vazia se o arquivo não a tem)."""
    nome = re.compile(rf"^fre_cia_aberta_{tabela}_\d{{4}}\.csv$")
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nomes = [n for n in arquivo.namelist() if nome.match(n)]
        if not nomes:
            return pd.DataFrame()
        bruto = pd.read_csv(
            arquivo.open(nomes[0]),
            sep=";",
            encoding=CODIFICACAO_DA_CVM,
            encoding_errors="replace",
            dtype=str,
            keep_default_na=False,
        )
    if bruto.empty:
        return bruto
    bruto["Versao"] = (
        pd.to_numeric(bruto["Versao"], errors="coerce").fillna(0).astype(int)
    )
    mais_nova = bruto.groupby(DOCUMENTO)["Versao"].transform("max")
    return bruto[bruto["Versao"] == mais_nova].reset_index(drop=True)


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce")


def _data(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, errors="coerce")


def _por_tipo(classes: pd.DataFrame) -> pd.DataFrame:
    """Por documento e exercício: o que foi dividendo e o que foi juros sobre capital próprio."""
    if classes.empty:
        return pd.DataFrame(
            columns=[*DOCUMENTO, "Data_Fim_Exercicio_Social", "dividendos", "jcp"]
        )
    e_jcp = classes["Dividendo_Distribuido"].str.lower().str.contains("juros")
    montante = _numero(classes["Montante"]).fillna(0)
    tabela = classes.assign(
        jcp=montante.where(e_jcp, 0), dividendos=montante.where(~e_jcp, 0)
    )
    return (
        tabela.groupby([*DOCUMENTO, "Data_Fim_Exercicio_Social"])[["dividendos", "jcp"]]
        .sum()
        .reset_index()
    )


def ler_proventos(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Proventos por exercício (FRE até 2022): lucro ajustado, total, payout, dividendos e JCP."""
    dividendos = _ler(conteudo_do_zip, "distribuicao_dividendos")
    if dividendos.empty:
        return pd.DataFrame(columns=list(COLUNAS_DOS_PROVENTOS))
    tipos = _por_tipo(_ler(conteudo_do_zip, "distribuicao_dividendos_classe_acao"))
    junto = dividendos.merge(
        tipos, on=[*DOCUMENTO, "Data_Fim_Exercicio_Social"], how="left"
    )
    return pd.DataFrame(
        {
            "cnpj": junto["CNPJ_Companhia"].str.strip(),
            "referencia": _data(junto["Data_Referencia"]),
            "versao": junto["Versao"],
            "exercicio": _data(junto["Data_Fim_Exercicio_Social"]),
            "lucro_ajustado": _numero(junto["Lucro_Liquido_Ajustado"]),
            "dividendo_total": _numero(junto["Dividendo_Distribuido_Total"]),
            "payout": _numero(junto["Dividendo_Distribuido_Lucro_Liquido_Ajustado"])
            / 100,
            "dividendos": junto["dividendos"],
            "jcp": junto["jcp"],
        },
        columns=list(COLUNAS_DOS_PROVENTOS),
    ).dropna(subset=["exercicio"])


def _desdobramentos(conteudo_do_zip: bytes) -> pd.DataFrame:
    bruto = _ler(conteudo_do_zip, "capital_social_desdobramento")
    if bruto.empty:
        return pd.DataFrame(columns=list(COLUNAS_DOS_EVENTOS))
    antes = _numero(bruto["Quantidade_Total_Acoes_Antes_Aprovacao"])
    depois = _numero(bruto["Quantidade_Total_Acoes_Depois_Aprovacao"])
    return pd.DataFrame(
        {
            "cnpj": bruto["CNPJ_Companhia"].str.strip(),
            "referencia": _data(bruto["Data_Referencia"]),
            "versao": bruto["Versao"],
            "tipo": bruto["Tipo_Evento"].str.strip().str.lower(),
            "data": _data(bruto["Data_Aprovacao"]),
            "acoes_antes": antes,
            "acoes_depois": depois,
            "fator": depois / antes.where(antes > 0),
        },
        columns=list(COLUNAS_DOS_EVENTOS),
    )


def _aumentos(conteudo_do_zip: bytes) -> pd.DataFrame:
    bruto = _ler(conteudo_do_zip, "capital_social_aumento")
    if bruto.empty:
        return pd.DataFrame(columns=list(COLUNAS_DOS_EVENTOS))
    return pd.DataFrame(
        {
            "cnpj": bruto["CNPJ_Companhia"].str.strip(),
            "referencia": _data(bruto["Data_Referencia"]),
            "versao": bruto["Versao"],
            "tipo": "aumento",
            "data": _data(bruto["Data_Deliberacao"]),
            "acoes_novas": _numero(bruto["Quantidade_Total_Acoes"]),
            "valor": _numero(bruto["Valor_Total_Emissao"]),
        },
        columns=list(COLUNAS_DOS_EVENTOS),
    )


def ler_eventos_de_capital(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Desdobramentos, grupamentos e bonificações (com o fator) e aumentos de capital (FRE até 2022)."""
    partes = [
        p
        for p in (_desdobramentos(conteudo_do_zip), _aumentos(conteudo_do_zip))
        if not p.empty
    ]
    if not partes:
        return pd.DataFrame(columns=list(COLUNAS_DOS_EVENTOS))
    return pd.concat(partes, ignore_index=True).dropna(subset=["data"])
