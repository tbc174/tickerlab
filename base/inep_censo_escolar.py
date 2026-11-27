"""Microdados 2022–2025: escolas privadas por CNPJ e matrículas agregadas.

Lista fechada de colunas em CADASTRO e MATRICULAS; nenhuma seleção por prefixo.
2022–2024: CSV único. 2025 v2: somente Escola e Matricula, por ano/código INEP.
O MD5 publicado DENTRO do ZIP é dos CSVs, não do ZIP: confere os dois membros
usados antes de interpretá-los. As outras quatro tabelas não são abertas.
"""

import hashlib
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from base.cnpj import dv_confere

ANOS = (2022, 2023, 2024, 2025)
FONTE = "INEP / Censo Escolar da Educação Básica"
TABELA = "inep_censo_escolar"
CHAVE = ("co_entidade", "ano_censo")
LINHAS_POR_BLOCO = 20_000
BYTES_POR_BLOCO = 1024 * 1024
MAX_MANIFESTO = 64 * 1024
CADASTRO = {
    "CO_ENTIDADE": "co_entidade",
    "NU_ANO_CENSO": "ano_censo",
    "TP_DEPENDENCIA": "dependencia",
    "TP_SITUACAO_FUNCIONAMENTO": "situacao_funcionamento",
    "NU_CNPJ_ESCOLA_PRIVADA": "cnpj_escola",
    "NU_CNPJ_MANTENEDORA": "cnpj_mantenedora",
    "SG_UF": "uf",
    "CO_MUNICIPIO": "codigo_municipio",
    "NO_MUNICIPIO": "municipio",
}
MATRICULAS = {
    "QT_MAT_BAS": "Total da educação básica (não somar os recortes)",
    "QT_MAT_INF": "Educação infantil",
    "QT_MAT_INF_CRE": "Creche",
    "QT_MAT_INF_PRE": "Pré-escola",
    "QT_MAT_FUND": "Ensino fundamental",
    "QT_MAT_FUND_AI": "Ensino fundamental, anos iniciais",
    "QT_MAT_FUND_AF": "Ensino fundamental, anos finais",
    "QT_MAT_MED": "Ensino médio",
    "QT_MAT_PROF": "Educação profissional",
    "QT_MAT_PROF_TEC": "Educação profissional técnica",
    "QT_MAT_EJA": "Educação de jovens e adultos",
    "QT_MAT_ESP": "Educação especial (incluída nos totais, nunca somar ao total)",
    "QT_MAT_BAS_INT": "Tempo integral, educação básica (coluna de 2025)",
    "QT_MAT_INF_INT": "Tempo integral, educação infantil",
    "QT_MAT_INF_CRE_INT": "Tempo integral, creche",
    "QT_MAT_INF_PRE_INT": "Tempo integral, pré-escola",
    "QT_MAT_FUND_INT": "Tempo integral, ensino fundamental",
    "QT_MAT_FUND_AI_INT": "Tempo integral, anos iniciais",
    "QT_MAT_FUND_AF_INT": "Tempo integral, anos finais",
    "QT_MAT_MED_INT": "Tempo integral, ensino médio",
}
# O total integral não existe nas edições antigas. Ausência é nulo, nunca zero
# nem soma estimada de etapas que podem se sobrepor.
MATRICULAS_OBRIGATORIAS = tuple(c for c in MATRICULAS if not c.endswith("_INT"))
CHAVE_ORIGINAL = ("NU_ANO_CENSO", "CO_ENTIDADE")
CNPJ_NUMERICO = re.compile(r"[0-9]{14}\Z")
MD5 = re.compile(r"^([a-fA-F0-9]{32})\s+\*?(.+?)\s*$")


def url_da_edicao(ano: int) -> str:
    """Endereço fixo das quatro edições conferidas; 2025 usa o ZIP v2."""
    if ano not in ANOS:
        raise ValueError("Censo Escolar: edição fora de 2022 a 2025")
    sufixo = "_" if ano == 2025 else ""
    return f"https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_{ano}{sufixo}.zip"


def data_da_edicao(ano: int) -> date:
    """Referência do censo: última quarta-feira de maio, não a publicação."""
    ultimo = date(ano, 5, 31)
    return ultimo - timedelta(days=(ultimo.weekday() - 2) % 7)


def _membro(pacote: zipfile.ZipFile, nome: str) -> zipfile.ZipInfo:
    achados = [
        m
        for m in pacote.infolist()
        if m.filename.rsplit("/", 1)[-1].casefold() == nome.casefold()
    ]
    if len(achados) != 1:
        raise ValueError(f"Censo Escolar: membro ausente ou duplicado: {nome}")
    return achados[0]


def _somas_publicadas(pacote: zipfile.ZipFile, ano: int) -> dict[str, str]:
    try:
        membro = _membro(pacote, f"md5_microdados_ed_basica_{ano}.txt")
    except ValueError as erro:
        raise ValueError("Censo Escolar: manifesto MD5 ausente ou duplicado") from erro
    if membro.file_size > MAX_MANIFESTO:
        raise ValueError("Censo Escolar: manifesto MD5 acima do tamanho permitido")
    texto = pacote.read(membro).decode("utf-8-sig")
    somas = {}
    for linha in texto.splitlines():
        if not linha.strip():
            continue
        achado = MD5.fullmatch(linha.strip())
        if not achado:
            raise ValueError("Censo Escolar: formato de manifesto MD5 não reconhecido")
        soma, nome = achado.groups()
        chave = nome.replace("\\", "/").rsplit("/", 1)[-1].casefold()
        if chave in somas:
            raise ValueError("Censo Escolar: entrada duplicada no manifesto MD5")
        somas[chave] = soma.lower()
    return somas


def _conferir_md5(
    pacote: zipfile.ZipFile, membro: zipfile.ZipInfo, somas: dict[str, str]
) -> None:
    esperado = somas.get(membro.filename.rsplit("/", 1)[-1].casefold())
    if esperado is None:
        raise ValueError("Censo Escolar: CSV sem MD5 publicado")
    soma = hashlib.md5(usedforsecurity=False)
    with pacote.open(membro) as entrada:
        while bloco := entrada.read(BYTES_POR_BLOCO):
            soma.update(bloco)
    if soma.hexdigest() != esperado:
        raise ValueError("Censo Escolar: MD5 divergente; edição recusada")


def _cnpj_estrito(valor: str) -> str | None:
    # Não completar zeros, limpar pontuação, truncar ou converter float.
    return valor if CNPJ_NUMERICO.fullmatch(valor) and dv_confere(valor) else None


def _cadastro_privado(tabela: pd.DataFrame) -> pd.DataFrame:
    tabela = tabela.loc[tabela.TP_DEPENDENCIA == "4"].copy()
    documentos = ["NU_CNPJ_ESCOLA_PRIVADA", "NU_CNPJ_MANTENEDORA"]
    for coluna in documentos:
        tabela[coluna] = tabela[coluna].map(_cnpj_estrito).astype("string")
    return tabela.loc[tabela[documentos].notna().any(axis=1)]


def _ler_csv(
    pacote: zipfile.ZipFile,
    membro: zipfile.ZipInfo,
    *,
    cadastro: bool,
    matriculas: bool,
) -> pd.DataFrame:
    permitidas = (
        set(CHAVE_ORIGINAL)
        | (set(CADASTRO) if cadastro else set())
        | (set(MATRICULAS) if matriculas else set())
    )
    obrigatorias = (
        set(CHAVE_ORIGINAL)
        | (set(CADASTRO) if cadastro else set())
        | (set(MATRICULAS_OBRIGATORIAS) if matriculas else set())
    )
    partes = []
    with (
        pacote.open(membro) as entrada,
        pd.read_csv(
            entrada,
            sep=";",
            encoding="latin-1",
            dtype="string",
            keep_default_na=False,
            usecols=lambda coluna: coluna in permitidas,
            chunksize=LINHAS_POR_BLOCO,
        ) as leitor,
    ):
        for bloco in leitor:
            if not obrigatorias.issubset(bloco.columns):
                raise ValueError(
                    "Censo Escolar: faltam colunas obrigatórias; layout mudou"
                )
            partes.append(_cadastro_privado(bloco) if cadastro else bloco)
    if not partes:
        raise ValueError("Censo Escolar: CSV vazio")
    return pd.concat(partes, ignore_index=True)


def _conferir_chaves(tabela: pd.DataFrame, ano: int) -> None:
    if not tabela.NU_ANO_CENSO.eq(str(ano)).all():
        raise ValueError("Censo Escolar: ano do CSV difere da edição")
    if (
        not tabela.CO_ENTIDADE.str.fullmatch(r"[0-9]{8}").all()
        or tabela.duplicated(list(CHAVE_ORIGINAL)).any()
    ):
        raise ValueError("Censo Escolar: código INEP inválido ou duplicado")


def _numeros(tabela: pd.DataFrame, colunas: list[str]) -> None:
    for coluna in colunas:
        texto = tabela[coluna].fillna("")
        if not (texto.eq("") | texto.str.fullmatch(r"[0-9]+")).all():
            raise ValueError("Censo Escolar: contagem ou código numérico inválido")
        tabela[coluna] = pd.to_numeric(texto.replace("", pd.NA), errors="raise").astype(
            "Int64"
        )


def ler_edicao(caminho: Path, ano: int) -> pd.DataFrame:
    """Valida MD5 e lê só cadastro privado e matrículas, sem campos pessoais."""
    url_da_edicao(ano)
    with zipfile.ZipFile(caminho) as pacote:
        nomes = (
            [f"Tabela_Escola_{ano}_v2.csv", f"Tabela_Matricula_{ano}_v2.csv"]
            if ano == 2025
            else [f"microdados_ed_basica_{ano}.csv"]
        )
        membros = [_membro(pacote, nome) for nome in nomes]
        somas = _somas_publicadas(pacote, ano)
        for membro in membros:
            _conferir_md5(pacote, membro, somas)
        tabela = _ler_csv(pacote, membros[0], cadastro=True, matriculas=ano != 2025)
        _conferir_chaves(tabela, ano)
        if ano == 2025:
            matriculas = _ler_csv(pacote, membros[1], cadastro=False, matriculas=True)
            _conferir_chaves(matriculas, ano)
            # Falhar se a fonte perdeu uma escola: não transformar ausência em zero
            # nem eliminar silenciosamente uma escola privada no INNER JOIN.
            if not set(tabela.CO_ENTIDADE).issubset(set(matriculas.CO_ENTIDADE)):
                raise ValueError(
                    "Censo Escolar: escola privada sem linha de matrículas"
                )
            tabela = tabela.merge(
                matriculas, on=list(CHAVE_ORIGINAL), validate="one_to_one"
            )
    tabela = tabela.reindex(columns=[*CADASTRO, *MATRICULAS], fill_value="")
    _numeros(
        tabela,
        ["NU_ANO_CENSO", "TP_DEPENDENCIA", "TP_SITUACAO_FUNCIONAMENTO", *MATRICULAS],
    )
    tabela = tabela.rename(columns={**CADASTRO, **{c: c.lower() for c in MATRICULAS}})
    tabela["fonte"] = FONTE
    tabela["data_edicao"] = data_da_edicao(ano)
    return tabela.sort_values(list(CHAVE)).reset_index(drop=True)
