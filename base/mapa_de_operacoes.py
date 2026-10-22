"""Mapa de operações de FIDC, CRI e CRA por CNPJ (N6 do mapa do Plano Mestre v3.1; C-PR04; item 12
da lista do lançamento).

`mapa_de_operacoes(porta, cnpj, como_era_em)` devolve, para um CNPJ, cada vínculo dele com uma
operação, **só com o que a CVM publica**, e diz o que não dá para observar (`Mapa.lacunas`):

- **FIDC** (`fidc_informe`, quadro I, mês a mês, e `cadastro_de_fundos`): o fundo (`emissor` das
  cotas), o `administrador` e os `cedente`s (só CNPJ válido) de cada mês, com o primeiro e o último
  mês em que apareceram e o dia em que o primeiro ficou público; o `gestor` vem do cadastro.
- **CRI e CRA** (`ofertas_antigas` e `ofertas_resolucao_160`): a `securitizadora`, que na CVM é o
  emissor do certificado, por oferta. CRI e CRA não têm administrador nem gestor.

Um vínculo é uma linha de `COLUNAS`. `referencia_desde` e `referencia_ate` são o primeiro e o último
mês (ou dia da oferta) em que a CVM mostrou o vínculo: não são a data em que ele começou nem acabou.
`publico_em` é o dia em que a primeira dessas linhas ficou pública. Com `como_era_em=D`, só entra o
que já era público em D (o futuro não muda o passado; há teste). O cadastro de fundos é um retrato
do dia da coleta, sem data pública por linha: com `como_era_em`, o gestor sai do mapa e a lacuna
diz isso. Cedente e devedor de CRI e CRA só existem no informe mensal dos certificados, que ainda
não está na porta (série 6, PR 1): ficam como "não observável". A ANBIMA fica de fora (termos).

A busca é pelo CNPJ em qualquer papel que a fonte permita achar sem varrer a base: o próprio fundo,
o administrador, o gestor e a securitizadora. O inverso do cedente (em quais fundos um CNPJ cede)
não é feito.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from base import cnpj as cnpj_
from base.porta import Porta

FIDC, CRI, CRA = "FIDC", "CRI", "CRA"
COLUNAS = (
    "tipo",  # FIDC, CRI ou CRA
    "operacao",  # o CNPJ do fundo, ou a oferta do certificado (origem:número/emissão)
    "cnpj_operacao",  # o CNPJ do fundo, ou o da securitizadora que emitiu
    "nome_operacao",
    "papel",  # emissor, securitizadora, administrador, gestor ou cedente
    "cnpj_papel",
    "nome_papel",  # vazio onde a fonte só dá o CNPJ (o cedente)
    "referencia_desde",  # primeiro mês (ou dia da oferta) em que a CVM mostrou o vínculo
    "referencia_ate",  # o último (não é o fim do vínculo)
    "publico_em",  # o dia em que a primeira linha ficou pública (vazio no cadastro)
    "fonte",  # a tabela da base
    "campo",  # a coluna da CVM de onde veio
)
INFORME = "fidc_informe"
CADASTRO = "cadastro_de_fundos"
OFERTAS = {"ofertas_antigas": "antigas", "ofertas_resolucao_160": "160"}
CEDENTE = re.compile(r"CPF_CNPJ_CEDENTE_(\d+)$")
E_CRI = re.compile(r"receb\w*\s+imobili|\bcri\b", re.IGNORECASE)
E_CRA = re.compile(r"receb\w*\s+do\s+agro|\bcra\b", re.IGNORECASE)

LACUNAS_FIXAS = (
    (
        "CRI e CRA: cedente e devedor só saem do informe mensal dos certificados da CVM, que ainda "
        "não está na porta (série 6, PR 1): não observável por aqui"
    ),
    "CRI e CRA: não têm administrador nem gestor; o emissor na CVM é a securitizadora",
    "ANBIMA fora do mapa: os termos dela proíbem o uso sem autorização escrita",
)


@dataclass(frozen=True)
class Mapa:
    vinculos: pd.DataFrame  # as colunas de `COLUNAS`
    lacunas: list[str]  # o que não dá para observar, em português


def _vazio() -> pd.DataFrame:
    return pd.DataFrame(columns=list(COLUNAS))


def _formatado(valor: object) -> str | None:
    """O CNPJ no formato que a base guarda (com pontos), ou None se não for um CNPJ."""
    normal = cnpj_.normalizar_cnpj(valor)
    return cnpj_.formatar(normal) if normal else None


def _agrupar(linhas: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    """Um vínculo por chave: o primeiro e o último mês e o 1º dia público; o nome mais recente."""
    ordenadas = linhas.sort_values("referencia")
    return (
        ordenadas.groupby(chaves, dropna=False)
        .agg(
            nome_operacao=("nome_operacao", "last"),
            referencia_desde=("referencia", "min"),
            referencia_ate=("referencia", "max"),
            publico_em=("publico_em", "min"),
        )
        .reset_index()
    )


def _ler(
    porta: Porta,
    tabela: str,
    filtros: dict[str, object],
    colunas: Sequence[str],
    dia: object,
) -> pd.DataFrame | None:
    """A tabela filtrada só com as `colunas` que ela tem; None se a base não tem a tabela."""
    try:
        existentes = set(porta.colunas(tabela))
    except KeyError:
        return None
    usadas = [c for c in colunas if c in existentes]
    return porta.ler(tabela, como_era_em=dia, filtros=filtros, colunas=usadas)


def _vinculos_do_informe(
    porta: Porta, filtro: dict, dia: object
) -> pd.DataFrame | None:
    """Administrador e cedentes de cada mês do informe, para o filtro (o fundo ou o administrador)."""
    colunas_do_informe = porta.colunas(INFORME) if _tem(porta, INFORME) else []
    cedentes = [c for c in colunas_do_informe if CEDENTE.search(c)]
    base = ["cnpj_fundo", "competencia", "publico_em", "DENOM_SOCIAL"]
    linhas = _ler(
        porta, INFORME, filtro, [*base, "CNPJ_ADMIN", "ADMIN", *cedentes], dia
    )
    if linhas is None:
        return None
    linhas = linhas.assign(referencia=pd.to_datetime(linhas["competencia"]))
    linhas = linhas.rename(columns={"DENOM_SOCIAL": "nome_operacao"})
    return pd.concat(
        [_administradores(linhas), _cedentes(linhas, cedentes)], ignore_index=True
    )


def _tem(porta: Porta, tabela: str) -> bool:
    try:
        porta.colunas(tabela)
    except KeyError:
        return False
    return True


def _do_fidc(linhas: pd.DataFrame, papel: str, campo: str) -> pd.DataFrame:
    """Dá a forma de `COLUNAS` às linhas já agrupadas por fundo e papel."""
    return linhas.assign(
        tipo=FIDC,
        operacao=linhas["cnpj_fundo"],
        cnpj_operacao=linhas["cnpj_fundo"],
        papel=papel,
        fonte=INFORME,
        campo=campo,
    )


def _administradores(linhas: pd.DataFrame) -> pd.DataFrame:
    if "CNPJ_ADMIN" not in linhas:
        return _vazio()
    admin = linhas.assign(cnpj_papel=linhas["CNPJ_ADMIN"].map(_formatado))
    admin = admin[admin["cnpj_papel"].notna()].assign(nome_papel=lambda t: t["ADMIN"])
    if admin.empty:
        return _vazio()
    agrupado = _agrupar(admin, ["cnpj_fundo", "cnpj_papel", "nome_papel"])
    return _do_fidc(agrupado, "administrador", "CNPJ_ADMIN")


def _cedentes(linhas: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    """Um cedente por CNPJ e fundo; a CVM só dá o CNPJ, o nome fica vazio."""
    partes = [
        linhas.assign(cnpj_papel=linhas[c].map(_formatado), nome_papel=None)
        for c in colunas
    ]
    if not partes:
        return _vazio()
    todos = pd.concat(partes, ignore_index=True)
    todos = todos[todos["cnpj_papel"].notna()]
    if todos.empty:
        return _vazio()
    agrupado = _agrupar(todos, ["cnpj_fundo", "cnpj_papel", "nome_papel"])
    return _do_fidc(agrupado, "cedente", "CPF_CNPJ_CEDENTE")


def _fidc_do_informe(porta: Porta, cnpj: str, dia: object) -> pd.DataFrame | None:
    """O CNPJ como fundo (administrador e cedentes) e como administrador de outros fundos."""
    como_fundo = _vinculos_do_informe(porta, {"cnpj_fundo": cnpj}, dia)
    como_admin = _vinculos_do_informe(porta, {"CNPJ_ADMIN": cnpj}, dia)
    if como_fundo is None or como_admin is None:
        return None
    como_admin = como_admin[como_admin["papel"] == "administrador"]
    return pd.concat([como_fundo, como_admin], ignore_index=True)


def _gestores(porta: Porta, cnpj: str) -> tuple[pd.DataFrame, list[str]]:
    """O gestor do cadastro (retrato da coleta, sem data pública) do fundo e do gestor `cnpj`."""
    avisos: list[str] = []
    colunas = ["CNPJ_FUNDO", "DENOM_SOCIAL", "TP_FUNDO", "PF_PJ_GESTOR"]
    colunas += ["CPF_CNPJ_GESTOR", "GESTOR"]
    achados = [
        _ler(porta, CADASTRO, {filtro: cnpj}, colunas, None)
        for filtro in ("CNPJ_FUNDO", "CPF_CNPJ_GESTOR")
    ]
    if any(a is None for a in achados):
        return _vazio(), ["gestor: a base não tem o cadastro de fundos"]
    cadastro = pd.concat([a for a in achados if a is not None]).drop_duplicates()
    cadastro = cadastro[cadastro["TP_FUNDO"].fillna("").str.startswith(FIDC)]
    pessoa_fisica = cadastro["CPF_CNPJ_GESTOR"].isna()
    if pessoa_fisica.any():
        avisos.append(
            "gestor: em "
            f"{int(pessoa_fisica.sum())} FIDC o gestor é pessoa física e a base não guarda o nome"
        )
    gestores = cadastro[~pessoa_fisica]
    vinculos = pd.DataFrame(
        {
            "tipo": FIDC,
            "operacao": gestores["CNPJ_FUNDO"],
            "cnpj_operacao": gestores["CNPJ_FUNDO"],
            "nome_operacao": gestores["DENOM_SOCIAL"],
            "papel": "gestor",
            "cnpj_papel": gestores["CPF_CNPJ_GESTOR"],
            "nome_papel": gestores["GESTOR"],
            "referencia_desde": pd.NaT,
            "referencia_ate": pd.NaT,
            "publico_em": pd.NaT,
            "fonte": CADASTRO,
            "campo": "CPF_CNPJ_GESTOR",
        }
    )
    return vinculos, avisos


def _tipo_do_certificado(texto: object) -> str | None:
    if not isinstance(texto, str):
        return None
    if E_CRI.search(texto):
        return CRI
    return CRA if E_CRA.search(texto) else None


def _ofertas_de_certificados(
    porta: Porta, cnpj: str, dia: object
) -> list[pd.DataFrame]:
    """As ofertas de CRI e CRA do emissor `cnpj`, uma tabela da base por vez."""
    quando = ["anunciada_em", "publico_em", "nome_emissor", "emissao"]
    desenhos = {
        "ofertas_antigas": (
            ["tipo_ativo", "numero_registro_oferta", "numero_processo"],
            "tipo_ativo",
        ),
        "ofertas_resolucao_160": (
            ["valor_mobiliario", "numero_requerimento"],
            "valor_mobiliario",
        ),
    }
    saida = []
    for tabela, (colunas, campo) in desenhos.items():
        ofertas = _ler(porta, tabela, {"cnpj_emissor": cnpj}, [*quando, *colunas], dia)
        if ofertas is None or ofertas.empty:
            continue
        ofertas = ofertas.assign(tipo=ofertas[campo].map(_tipo_do_certificado))
        saida.append(_da_oferta(ofertas[ofertas["tipo"].notna()], tabela, campo, cnpj))
    return saida


def _numero_da_oferta(ofertas: pd.DataFrame) -> pd.Series:
    """O número da oferta: registro, processo (as antigas) ou requerimento (a 160), o 1º que existe."""
    numeros = [
        ofertas[c]
        for c in ("numero_registro_oferta", "numero_processo", "numero_requerimento")
        if c in ofertas
    ]
    return pd.concat(numeros, axis=1).bfill(axis=1).iloc[:, 0].fillna("")


def _da_oferta(
    ofertas: pd.DataFrame, tabela: str, campo: str, cnpj: str
) -> pd.DataFrame:
    if ofertas.empty:
        return _vazio()
    origem = OFERTAS[tabela]
    numero = _numero_da_oferta(ofertas).astype(str)
    emissao = ofertas["emissao"].fillna("").astype(str)
    linhas = ofertas.assign(
        operacao=origem + ":" + numero + "/" + emissao,
        nome_papel=ofertas["nome_emissor"],
        nome_operacao=ofertas["nome_emissor"] + " (emissão " + emissao + ")",
        referencia=pd.to_datetime(ofertas["anunciada_em"]),
    )
    agrupado = _agrupar(linhas, ["tipo", "operacao", "nome_papel"])
    return agrupado.assign(
        cnpj_operacao=cnpj,
        papel="securitizadora",
        cnpj_papel=cnpj,
        fonte=tabela,
        campo=campo,
    )


def _lacuna_do_gestor(dia: object) -> list[str]:
    if dia is None:
        return [
            "gestor: o cadastro da CVM é o retrato do dia da coleta, sem data de entrada do gestor"
        ]
    return [
        (
            f"gestor em {dia}: o cadastro da CVM é um retrato sem data pública por linha; "
            "o gestor de uma data passada não é observável e fica fora do mapa"
        )
    ]


def mapa_de_operacoes(porta: Porta, cnpj: str, como_era_em: object = None) -> Mapa:
    """Os vínculos do CNPJ com operações de FIDC, CRI e CRA, e as lacunas.

    `como_era_em` (dia): só o que já era público nesse dia. Erro (`ValueError`) se `cnpj` não for um CNPJ.
    """
    formatado = _formatado(cnpj)
    if formatado is None:
        raise ValueError(f"CNPJ inválido: {cnpj!r}")
    lacunas = [*LACUNAS_FIXAS]
    partes: list[pd.DataFrame] = []
    informe = _fidc_do_informe(porta, formatado, como_era_em)
    if informe is None:
        lacunas.append(
            "FIDC: a base não tem o informe mensal (administrador e cedentes)"
        )
    else:
        partes.append(informe)
    if como_era_em is None:
        gestores, avisos = _gestores(porta, formatado)
        partes.append(gestores)
        lacunas += avisos
    lacunas += _lacuna_do_gestor(como_era_em)
    partes += _ofertas_de_certificados(porta, formatado, como_era_em)
    return Mapa(_juntar(partes), lacunas)


def _juntar(partes: list[pd.DataFrame]) -> pd.DataFrame:
    com_linhas = [p for p in partes if not p.empty]
    if not com_linhas:
        return _vazio()
    todos = pd.concat(com_linhas, ignore_index=True)[list(COLUNAS)]
    return todos.sort_values(["tipo", "operacao", "papel", "cnpj_papel"]).reset_index(
        drop=True
    )
