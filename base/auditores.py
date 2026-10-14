"""Auditor por empresa e data e o rótulo "trocou de auditor" (série B3).

Fonte: o FCA da CVM desde 2010 (guardado pelo arquivista como `cvm-hist-fca`). Cada arquivo anual traz,
na tabela `fca_cia_aberta_auditor`, os mandatos de auditor (firma, início e fim) da **última versão**
do formulário de cada empresa; a data em que a CVM recebeu essa versão vem do arquivo principal
(`DT_RECEB`, ligado pelo `ID_DOC`) e é o `conhecido_em`. Como o acervo só tem a última versão, essa data
pode ser mais tarde que a da primeira notícia, nunca mais cedo.

LGPD: o sócio responsável técnico (nome e CPF) nunca entra, e o auditor pessoa física (CPF no lugar do
CNPJ, raro) fica só com o código da CVM.

A firma é identificada pela raiz do CNPJ (as filiais da KPMG mudam o final; o código da CVM às vezes vem
vazio); sem CNPJ, pelo código da CVM; sem os dois (firma estrangeira), pelo nome.
"""

import io
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

CODIFICACAO_DA_CVM = "latin-1"
COLUNAS = (
    "cnpj", "empresa", "referencia", "versao", "id_documento", "conhecido_em", "auditor_id",
    "auditor", "auditor_cnpj", "codigo_cvm_auditor", "origem", "inicio", "fim",
)  # fmt: skip
COLUNAS_DAS_TROCAS = (
    "cnpj", "empresa", "conhecido_em", "efetiva_em", "anterior_id", "anterior", "novo_id",
    "novo", "anos_com_o_anterior", "id_documento",
)  # fmt: skip
# no primeiro FCA guardado de uma empresa, só um mandato encerrado há menos que isto antes do ano de
# referência indica a troca (um encerrado há anos é história antiga, não notícia daquele ano)
ENCERRADO_HA_POUCO = timedelta(days=366)
DIAS_POR_ANO = 365.25
SO_DIGITOS = re.compile(r"\D")


def _texto(serie: pd.Series) -> pd.Series:
    return serie.str.strip().replace("", None)


def _data(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, errors="coerce").dt.date


def _ler(arquivo: zipfile.ZipFile, trecho: str) -> pd.DataFrame:
    nome = next(n for n in arquivo.namelist() if trecho in n)
    return pd.read_csv(
        arquivo.open(nome), sep=";", encoding=CODIFICACAO_DA_CVM, dtype=str,
        keep_default_na=False,
    )  # fmt: skip


def _identidade(cnpj_da_firma: object, codigo: object, nome: object) -> str:
    if isinstance(cnpj_da_firma, str) and cnpj_da_firma:
        return f"cnpj:{cnpj_da_firma[:8]}"
    if isinstance(codigo, str) and codigo:
        return f"cvm:{codigo}"
    return f"nome:{nome.strip().lower() if isinstance(nome, str) else ''}"


def ler_auditores_do_fca(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os mandatos de auditor de um arquivo anual do FCA, com a data de entrega do documento."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        bruto = _ler(arquivo, "_auditor_")
        principal = _ler(arquivo, "fca_cia_aberta_2")
    recebido = dict(
        zip(principal["ID_DOC"].str.strip(), principal["DT_RECEB"], strict=True)
    )
    documento = bruto["CPF_CNPJ_Auditor"].str.replace(SO_DIGITOS, "", regex=True)
    pessoa_juridica = documento.str.len() == 14
    codigo = _texto(bruto["Codigo_CVM_Auditor"])
    nome = _texto(bruto["Auditor"]).where(pessoa_juridica | (documento == ""), None)
    auditor_cnpj = documento.where(pessoa_juridica, None)
    tabela = pd.DataFrame(
        {
            "cnpj": bruto["CNPJ_Companhia"].str.strip(),
            "empresa": bruto["Nome_Empresarial"].str.strip(),
            "referencia": _data(bruto["Data_Referencia"]),
            "versao": pd.to_numeric(bruto["Versao"], errors="coerce"),
            "id_documento": bruto["ID_Documento"].str.strip(),
            "conhecido_em": _data(bruto["ID_Documento"].str.strip().map(recebido)),
            "auditor_id": [
                _identidade(c, k, n)
                for c, k, n in zip(auditor_cnpj, codigo, nome, strict=True)
            ],
            "auditor": nome,
            "auditor_cnpj": auditor_cnpj,
            "codigo_cvm_auditor": codigo,
            "origem": _texto(bruto["Origem_Auditor"]),
            "inicio": _data(bruto["Data_Inicio_Atuacao_Auditor"]),
            "fim": _data(bruto["Data_Fim_Atuacao_Auditor"]),
        }
    )
    tabela = tabela.astype(object).where(tabela.notna(), None)
    # sem o responsável técnico, o mesmo mandato repetido (um por sócio) vira uma linha só
    tabela = tabela.dropna(subset=["conhecido_em"]).drop_duplicates(
        ["id_documento", "auditor_id", "inicio", "fim"]
    )
    return tabela[list(COLUNAS)].reset_index(drop=True)


@dataclass
class _Empresa:
    """O que já se sabia da empresa: o FCA mais novo lido e os auditores vigentes desde quando."""

    referencia: date | None = None
    vigentes: dict[str, date] = field(default_factory=dict)  # auditor_id → desde
    nomes: dict[str, str | None] = field(default_factory=dict)


def _vigentes(documento: pd.DataFrame, recebido: date) -> dict[str, date]:
    """auditor_id → início, dos mandatos sem fim ou que acabam depois da entrega."""
    ativos = documento[documento["fim"].isna() | (documento["fim"] >= recebido)]
    return ativos.groupby("auditor_id")["inicio"].min().to_dict()


def _anteriores_no_primeiro_fca(
    documento: pd.DataFrame, vigentes: dict[str, date]
) -> dict[str, date]:
    """No primeiro FCA guardado, os auditores cujo mandato acabou pouco antes do ano de referência."""
    referencia = documento["referencia"].iloc[0]
    encerrados = documento[
        documento["fim"].notna()
        & (documento["fim"] >= referencia - ENCERRADO_HA_POUCO)
        & ~documento["auditor_id"].isin(vigentes)
    ]
    if encerrados.empty:
        return dict(vigentes)
    return encerrados.groupby("auditor_id")["inicio"].min().to_dict()


def _nome(nomes: dict[str, str | None], ids: Iterable[str]) -> str | None:
    partes = [nomes.get(i) for i in sorted(ids)]
    return " + ".join(p for p in partes if p) or None


def _mais_cedo(datas: Iterable[object]) -> date | None:
    """A data mais antiga; None se nenhuma foi informada (há mandato sem data de início no FCA)."""
    informadas = [d for d in datas if isinstance(d, date)]
    return min(informadas) if informadas else None


def _troca(
    estado: _Empresa,
    documento: pd.DataFrame,
    saidas: set[str],
    entradas: set[str],
    recebido: date,
) -> dict:
    efetiva = _mais_cedo(
        documento.loc[documento["auditor_id"].isin(entradas), "inicio"]
    )
    desde = _mais_cedo(estado.vigentes[i] for i in saidas)
    anos = (
        round((efetiva - desde).days / DIAS_POR_ANO, 1) if efetiva and desde else None
    )
    return {
        "cnpj": documento["cnpj"].iloc[0],
        "empresa": documento["empresa"].iloc[-1],
        "conhecido_em": recebido,
        "efetiva_em": efetiva,
        "anterior_id": " + ".join(sorted(saidas)),
        "anterior": _nome(estado.nomes, saidas),
        "novo_id": " + ".join(sorted(entradas)),
        "novo": _nome(estado.nomes, entradas),
        "anos_com_o_anterior": anos,
        "id_documento": documento["id_documento"].iloc[0],
    }


def trocas_de_auditor(auditores: pd.DataFrame) -> pd.DataFrame:
    """As trocas de auditor, cada uma na data em que o FCA que a mostra foi entregue à CVM.

    Lê os documentos na ordem de entrega e nunca reescreve uma troca já dada: montar só com os FCAs
    entregues até uma data dá as mesmas trocas que montar com tudo e cortar naquela data. Entrada de
    uma segunda firma (auditoria conjunta) ou saída de uma delas não é troca; troca é sair uma firma e
    entrar outra. Um FCA de um ano mais velho entregue depois de um mais novo (reapresentação) é
    correção do passado e não gera troca.
    """
    linhas: list[dict] = []
    estados: dict[str, _Empresa] = {}
    if auditores.empty:
        return pd.DataFrame(columns=list(COLUNAS_DAS_TROCAS))
    ordem = auditores.sort_values(["conhecido_em", "id_documento"], kind="stable")
    for _, documento in ordem.groupby(["conhecido_em", "id_documento"], sort=False):
        cnpj, referencia = documento["cnpj"].iloc[0], documento["referencia"].iloc[0]
        recebido = documento["conhecido_em"].iloc[0]
        estado = estados.setdefault(cnpj, _Empresa())
        if estado.referencia is not None and referencia <= estado.referencia:
            continue
        primeiro = estado.referencia is None
        estado.referencia = referencia
        estado.nomes.update(
            documento.drop_duplicates("auditor_id", keep="last")
            .set_index("auditor_id")["auditor"]
            .to_dict()
        )
        vigentes = _vigentes(documento, recebido)
        if not vigentes:  # todos os mandatos encerrados: espera o próximo FCA
            continue
        if primeiro:
            estado.vigentes = _anteriores_no_primeiro_fca(documento, vigentes)
        saidas = set(estado.vigentes) - set(vigentes)
        entradas = set(vigentes) - set(estado.vigentes)
        if saidas and entradas:
            linhas.append(_troca(estado, documento, saidas, entradas, recebido))
        # quem continua mantém o "desde" antigo; quem entra começa no início do mandato
        estado.vigentes = {
            auditor: estado.vigentes.get(auditor, inicio)
            for auditor, inicio in vigentes.items()
        }
    return pd.DataFrame(linhas, columns=list(COLUNAS_DAS_TROCAS))


DATAS = ("referencia", "conhecido_em", "inicio", "fim")


def montar_trocas(pasta: Path, agora: datetime) -> int:
    """`<pasta>/trocas_de_auditor/trocas.parquet` a partir de todos os anos de `<pasta>/auditores/`.

    Roda depois de `historico.montar("auditores", ...)`; devolve quantas trocas gravou (0 e nada
    gravado quando ainda não há ano de auditores na base).
    """
    anos = sorted((pasta / "auditores").glob("*.parquet"))
    if not anos:
        return 0
    todos = pd.concat([pd.read_parquet(ano) for ano in anos], ignore_index=True)
    for coluna in DATAS:
        todos[coluna] = pd.to_datetime(todos[coluna], errors="coerce").dt.date
    todos = todos.astype(object).where(todos.notna(), None)
    trocas = trocas_de_auditor(todos).assign(montado_em=agora.isoformat())
    destino = pasta / "trocas_de_auditor" / "trocas.parquet"
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    trocas.to_parquet(parcial, index=False)
    parcial.replace(destino)
    return len(trocas)
