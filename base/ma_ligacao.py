"""Partes dos negócios de M&A ligadas à rede de entidades, e o mesmo negócio de vários sites junto (ADR
0082, série 5 do plano de M&A, passo 3; regras da rede na ADR 0077).

**Como cada parte liga** (só regras exatas; testes em `tests/test_base_ma_ligacao.py`):
1. o nome normalizado (`normalizar`: sem acento nem caixa, sem "S.A.", "Ltda" e outras formas
   jurídicas no fim, sem "Grupo") contra os nomes das empresas e fundos da rede **e** contra a razão
   social de todas as empresas do CNPJ da Receita; as duas listas contam juntas;
2. só se nada casou: o nome fantasia dos estabelecimentos (a filial liga pela raiz);
3. um candidato só → `nome_exato` ou `nome_fantasia`; mais de um → `na_duvida` (nunca se escolhe);
   nenhum → `sem_ligacao`. O casamento aproximado fica com a prova de conceito do Splink.

**Contra homônimos** (conferência do Tiago, 16/10/2026, `ma-regua-conferencia-2026-10-16.md`: ~22 das 27
alvos que hoje são ME/EPP eram outra empresa com o mesmo nome curto):
- regra 1: nome de **uma palavra só** (ou sigla) liga só pela rede; um candidato da Receita conta para a
  dúvida, mas nunca vira a ligação ("Kawa" não é a KAWA LTDA);
- regra 4: ligação só pelo nome fantasia vale quando a razão social **tem o nome** do post; senão,
  `na_duvida` ("Estante Virtual" era o nome fantasia de um sebo);
- regra 5: razão social de empresa estrangeira registrada no Brasil (AG, BV, LLC, LTD, GmbH...) vira
  `holding_estrangeira`, sem CNPJ: é a dona de fora, não a empresa brasileira do negócio;
- regra 2: CNPJ cuja matriz abriu **depois** de o post ficar público (a primeira cópia no Wayback) nunca é
  a parte: `aberto_depois_do_negocio`, sem CNPJ.
A regra "ME/EPP fica na dúvida" foi descartada: o porte é declarado pela empresa e fica velho.

**Pessoas** (ADR 0075): empresário individual (213-5), as naturezas do grupo 4 e o MEI contam como
candidatos (para a dúvida), mas nunca viram a ligação, e nada deles sai do leitor da Receita além da
raiz. Da Receita sai só a raiz e o nome da parte, que já estava na página da assessoria: nenhuma razão
social é guardada.

**A entidade** é a da rede quando a raiz já está lá; senão, o id que a rede daria a essa raiz
(`base/rede/ids.py`), para a ligação continuar valendo quando a empresa entrar na rede.

**Duplicatas** (`negocios`): as assessorias dos dois lados postam o mesmo negócio. Duas páginas são o
mesmo negócio quando têm as mesmas partes (a entidade, quando ligada; senão o nome normalizado), vêm de
assessorias diferentes e o tipo não se contradiz (`desconhecido` não contradiz). As mesmas partes duas
vezes no mesmo site são dois posts (uma rodada e, depois, o controle): ficam separadas, e
`paginas_com_as_mesmas_partes` mostra. O id do negócio sai das partes, então não muda quando o segundo
site chega; muda se a ligação de uma parte mudar.
"""

import hashlib
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import IO

import pandas as pd

from base import ma_assessorias as ma
from base.rede import ids
from base.rede.entidades import natureza_de_pessoa

# --- nomes ------------------------------------------------------------------------------------------
GRUPO = r"(?<= )(grupo|group)(?= )"
FORMAS_JURIDICAS = (
    "s a", "sa", "ltda", "limitada", "eireli", "epp", "me", "inc", "llc", "ltd", "plc", "corp",
    "gmbh", "ag", "nv", "bv", "spa", "sarl",
)  # fmt: skip
FORMA_NO_FIM = r"( (" + "|".join(FORMAS_JURIDICAS) + r"))+ *$"


def normalizar_nomes(nomes: pd.Series) -> pd.Series:
    """Cada nome sem acento, em minúsculas, só letras e números, sem forma jurídica e sem "Grupo"."""
    texto = (
        nomes.fillna("")
        .astype(str)
        .str.normalize("NFKD")
        .str.encode("ascii", "ignore")
        .str.decode("ascii")
        .str.lower()
        .str.replace(r"[^a-z0-9]+", " ", regex=True)
    )
    texto = (
        (" " + texto + " ")
        .str.replace(GRUPO, " ", regex=True)
        .str.replace(FORMA_NO_FIM, "", regex=True)
        .str.split()
        .str.join(" ")
    )
    return texto.where(texto != "", None).astype(object)


def normalizar(nome: str | None) -> str | None:
    return normalizar_nomes(pd.Series([nome], dtype=object)).iloc[0]


# --- partes de cada página ------------------------------------------------------------------------
PAPEIS = ("alvo", "comprador", "vendedor", "outras_partes")
NA_PAGINA = ("cliente", "contraparte")
COLUNAS_DAS_PARTES = (
    "assessoria",
    "url",
    "nome",
    "papel",
    "na_pagina",
    "nome_normalizado",
    "id_entidade",
    "cnpj_raiz",
    "lei",
    "ligacao_por",
    "candidatos",
)


def _nomes(valor: object) -> list[str]:
    return [n for n in valor.split(ma.SEPARADOR) if n] if isinstance(valor, str) else []


def partes(negocios: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por empresa de cada página: o papel no negócio e o campo da página em que está."""
    linhas = []
    for negocio in negocios.to_dict("records"):
        papel = {}
        for coluna in PAPEIS:
            for nome in _nomes(negocio[coluna]):
                papel.setdefault(nome, coluna)
        na_pagina = {}
        for coluna in NA_PAGINA:
            for nome in _nomes(negocio[coluna]):
                na_pagina.setdefault(nome, coluna)
        linhas.extend(
            {
                "assessoria": negocio["assessoria"],
                "url": negocio["url"],
                "nome": nome,
                "papel": papel.get(nome),
                "na_pagina": na_pagina.get(nome),
            }
            for nome in dict.fromkeys([*papel, *na_pagina])
        )
    tabela = pd.DataFrame(
        linhas, columns=["assessoria", "url", "nome", "papel", "na_pagina"]
    ).astype(object)
    return tabela.assign(nome_normalizado=normalizar_nomes(tabela["nome"]))


# --- a rede -----------------------------------------------------------------------------------------
TIPOS_COM_NOME = (
    "empresa",
    "fundo",
)  # valor mobiliário e firma de auditoria não fazem negócio


def _vigente(identificadores: pd.DataFrame, sistema: str) -> pd.Series:
    """id_entidade → valor do sistema (o vigente primeiro)."""
    do_sistema = identificadores[identificadores["sistema"] == sistema]
    do_sistema = do_sistema.assign(_encerrado=do_sistema["ate"].notna()).sort_values(
        ["id_entidade", "_encerrado", "valor"]
    )
    return do_sistema.drop_duplicates("id_entidade").set_index("id_entidade")["valor"]


def nomes_da_rede(
    entidades: pd.DataFrame, identificadores: pd.DataFrame
) -> pd.DataFrame:
    """(nome_normalizado, id_entidade, cnpj_raiz, lei) das empresas e fundos da rede com nome.

    A rede já tira o nome de quem é pessoa (`base/rede/entidades.py`): sem nome, a entidade não casa.
    """
    com_nome = entidades[
        entidades["tipo"].isin(TIPOS_COM_NOME) & entidades["nome"].notna()
    ]
    tabela = pd.DataFrame(
        {
            "nome_normalizado": normalizar_nomes(com_nome["nome"]),
            "id_entidade": com_nome["id_entidade"],
        }
    ).dropna()
    raiz, lei = _vigente(identificadores, "cnpj_raiz"), _vigente(identificadores, "lei")
    return tabela.assign(
        cnpj_raiz=tabela["id_entidade"].map(raiz),
        lei=tabela["id_entidade"].map(lei),
    ).reset_index(drop=True)


# --- a Receita --------------------------------------------------------------------------------------
RAZAO_SOCIAL, NOME_FANTASIA = "razao_social", "nome_fantasia"
COLUNAS_DA_RECEITA = (
    "raiz",
    "nome_normalizado",
    "por",
    "pessoa",
    "abertura",  # início de atividade da matriz
    "razao_tem_o_nome",  # a razão social contém o nome do post (regra 4)
    "estrangeira",  # a razão social termina com forma jurídica de fora (regra 5)
)
CODIFICACAO = "latin-1"
TAMANHO_DA_PARTE = 1_000_000
RAZAO, NATUREZA = 1, 2  # colunas dos `Empresas*.zip`
FANTASIA, MATRIZ_OU_FILIAL, INICIO = 4, 3, 10  # colunas dos `Estabelecimentos*.zip`
MATRIZ = "1"
FORMATO_DA_DATA = "%Y%m%d"
# a forma jurídica de fora no fim da razão social ("FOXBIT LLC", "DOCK LTD"; "LTDA" é brasileira)
ESTRANGEIRA = r"\b(AG|B\.? ?V|LLC|L\.L\.C|LTD|LIMITED|GMBH|INC|PLC|N\.? ?V|CORP|CORPORATION)\.?\s*$"
MEI = 4  # coluna do `Simples.zip` (opção pelo MEI)
OPTANTE = "S"
Arquivo = Path | IO[bytes]


def partes_do_zip(arquivo_zip: Arquivo, colunas: list[int]) -> Iterator[pd.DataFrame]:
    with zipfile.ZipFile(arquivo_zip) as zipado:
        (membro,) = zipado.namelist()  # cada ZIP da Receita tem um arquivo só
        with zipado.open(membro) as texto:
            yield from pd.read_csv(
                texto, sep=";", header=None, usecols=colunas, dtype=str,
                encoding=CODIFICACAO, keep_default_na=False, chunksize=TAMANHO_DA_PARTE,
            )  # fmt: skip


def _pelo_nome(
    arquivos: Sequence[Arquivo], coluna: int, nomes: set[str]
) -> pd.DataFrame:
    """(raiz, nome_normalizado) das linhas cujo nome normalizado é um dos `nomes`."""
    achados = []
    for arquivo in arquivos:
        for parte in partes_do_zip(arquivo, [0, coluna]):
            parte = parte[parte[coluna].str.strip() != ""]
            normalizados = normalizar_nomes(parte[coluna])
            casou = normalizados.isin(nomes)
            achados.append(
                pd.DataFrame(
                    {
                        "raiz": parte.loc[casou, 0],
                        "nome_normalizado": normalizados[casou],
                    }
                )
            )
    if not achados:
        return pd.DataFrame(columns=["raiz", "nome_normalizado"])
    return pd.concat(achados, ignore_index=True).drop_duplicates(ignore_index=True)


def _das_raizes(
    arquivos: Sequence[Arquivo], colunas: list[int], raizes: set[str]
) -> pd.DataFrame:
    """raiz → valores das colunas, só das raízes pedidas (a primeira linha de cada raiz)."""
    pedacos = [
        parte[parte[0].isin(raizes)].set_index(0)[colunas]
        for arquivo in arquivos
        for parte in partes_do_zip(arquivo, [0, *colunas])
    ]
    if not pedacos:
        return pd.DataFrame(columns=colunas, dtype=object)
    valores = pd.concat(pedacos)
    return valores[~valores.index.duplicated()]


def _abertura_da_matriz(
    estabelecimentos: Sequence[Arquivo], raizes: set[str]
) -> pd.Series:
    """raiz → data de início de atividade da matriz (a filial abre depois e não conta)."""
    pedacos = [
        parte[parte[0].isin(raizes) & (parte[MATRIZ_OU_FILIAL] == MATRIZ)]
        for arquivo in estabelecimentos
        for parte in partes_do_zip(arquivo, [0, MATRIZ_OU_FILIAL, INICIO])
    ]
    if not pedacos:
        return pd.Series(dtype="datetime64[ns]")
    matrizes = pd.concat(pedacos).drop_duplicates(0).set_index(0)[INICIO]
    return pd.to_datetime(matrizes, format=FORMATO_DA_DATA, errors="coerce")


def _tem_o_nome(razoes: pd.Series, nomes: pd.Series) -> list[bool]:
    """A razão social normalizada contém o nome do post, palavra por palavra?"""
    return [
        isinstance(r, str) and isinstance(n, str) and f" {n} " in f" {r} "
        for r, n in zip(normalizar_nomes(razoes), nomes, strict=True)
    ]


def ler_receita(
    empresas: Sequence[Arquivo],
    estabelecimentos: Sequence[Arquivo],
    simples: Sequence[Arquivo],
    nomes: set[str],
) -> pd.DataFrame:
    """As raízes cujo nome (razão social ou nome fantasia) normalizado é o nome de uma parte.

    `pessoa`: empresário individual, natureza do grupo 4, MEI ou natureza que a Receita não deu (o
    conservador, como a rede). `abertura`, `razao_tem_o_nome` e `estrangeira` servem às regras contra
    homônimos. Lê os arquivos por partes; a razão social só é olhada aqui e nunca sai do leitor: sai a
    raiz, o nome da parte e os indicadores.
    """
    razao = _pelo_nome(empresas, RAZAO, nomes).assign(por=RAZAO_SOCIAL)
    fantasia = _pelo_nome(estabelecimentos, FANTASIA, nomes).assign(por=NOME_FANTASIA)
    achados = pd.concat([razao, fantasia], ignore_index=True)
    raizes = set(achados["raiz"])
    das_empresas = _das_raizes(empresas, [RAZAO, NATUREZA], raizes)
    natureza = achados["raiz"].map(das_empresas[NATUREZA])
    razao_social = achados["raiz"].map(das_empresas[RAZAO])
    mei = achados["raiz"].map(
        _das_raizes(simples, [MEI], raizes)[MEI].str.strip() == OPTANTE
    )
    pessoa = (
        natureza.isna()
        | natureza.fillna("").map(natureza_de_pessoa)
        | (mei.fillna(False).astype(bool))
    )
    estrangeira = (
        razao_social.fillna("").str.upper().str.contains(ESTRANGEIRA, regex=True)
    )
    return achados.assign(
        pessoa=pessoa.astype(bool),
        abertura=achados["raiz"].map(_abertura_da_matriz(estabelecimentos, raizes)),
        razao_tem_o_nome=_tem_o_nome(razao_social, achados["nome_normalizado"]),
        estrangeira=estrangeira.astype(bool),
    )[list(COLUNAS_DA_RECEITA)]


# --- a ligação --------------------------------------------------------------------------------------
NOME_EXATO, NA_DUVIDA, SEM_LIGACAO = "nome_exato", "na_duvida", "sem_ligacao"
HOLDING_ESTRANGEIRA, ABERTO_DEPOIS = "holding_estrangeira", "aberto_depois_do_negocio"


def _candidatos(
    rede: pd.DataFrame, receita: pd.DataFrame, fixados: dict[ids.Chave, str]
) -> pd.DataFrame:
    """Uma linha por (nome, entidade candidata, por onde casou): a rede e a Receita juntas."""
    id_da_raiz = rede.dropna(subset=["cnpj_raiz"]).drop_duplicates("cnpj_raiz")
    id_da_raiz = id_da_raiz.set_index("cnpj_raiz")["id_entidade"]
    lei = rede.drop_duplicates("id_entidade").set_index("id_entidade")["lei"]
    da_receita = receita.assign(
        id_entidade=[
            id_da_raiz.get(r)
            or fixados.get(("empresa", "cnpj_raiz", r))
            or ids.id_entidade("empresa", "cnpj_raiz", r)
            for r in receita["raiz"]
        ],
        cnpj_raiz=receita["raiz"],
    )
    da_receita = da_receita.assign(
        lei=da_receita["id_entidade"].map(lei), da_rede=False
    )
    da_rede = rede.assign(
        por=RAZAO_SOCIAL,
        pessoa=False,
        da_rede=True,
        abertura=pd.NaT,
        razao_tem_o_nome=True,
        estrangeira=False,
    )
    colunas = [
        "nome_normalizado",
        "id_entidade",
        "cnpj_raiz",
        "lei",
        "por",
        "pessoa",
        "da_rede",
        "abertura",
        "razao_tem_o_nome",
        "estrangeira",
    ]
    juntos = pd.concat(
        [da_rede[colunas], da_receita[colunas]], ignore_index=True
    ).astype(object)
    return juntos.assign(abertura=pd.to_datetime(juntos["abertura"], errors="coerce"))


def _decidir(nome: str, grupo: pd.DataFrame) -> dict[str, object]:
    exato = grupo[grupo["por"] == RAZAO_SOCIAL]
    escolhidos = exato if len(exato) else grupo  # o nome fantasia só sem nome exato
    por_entidade = escolhidos.groupby("id_entidade", sort=True).agg(
        pessoa=("pessoa", "any"),
        cnpj_raiz=("cnpj_raiz", "first"),
        lei=("lei", "first"),
        da_rede=("da_rede", "any"),
        abertura=("abertura", "min"),
        razao_tem_o_nome=("razao_tem_o_nome", "all"),
        estrangeira=("estrangeira", "any"),
    )
    vazia: dict[str, object] = dict.fromkeys(
        ("id_entidade", "cnpj_raiz", "lei", "abertura")
    )
    if len(por_entidade) > 1:
        return {**vazia, "ligacao_por": NA_DUVIDA, "candidatos": len(por_entidade)}
    unica = por_entidade.iloc[0]
    if unica["pessoa"]:
        return {**vazia, "ligacao_por": SEM_LIGACAO, "candidatos": 1}
    so_da_receita = not unica["da_rede"]
    uma_palavra = " " not in nome
    fantasia_sem_o_nome = not len(exato) and not unica["razao_tem_o_nome"]
    if so_da_receita and (uma_palavra or fantasia_sem_o_nome):  # regras 1 e 4
        return {**vazia, "ligacao_por": NA_DUVIDA, "candidatos": 1}
    if unica["estrangeira"]:  # regra 5
        return {**vazia, "ligacao_por": HOLDING_ESTRANGEIRA, "candidatos": 1}
    return {
        "id_entidade": por_entidade.index[0],
        "cnpj_raiz": unica["cnpj_raiz"] if pd.notna(unica["cnpj_raiz"]) else None,
        "lei": unica["lei"] if pd.notna(unica["lei"]) else None,
        "abertura": unica["abertura"],
        "ligacao_por": NOME_EXATO if len(exato) else NOME_FANTASIA,
        "candidatos": 1,
    }


def _aberto_depois(tabela: pd.DataFrame, publico_em: pd.Series | None) -> pd.Series:
    """Regra 2: a matriz abriu depois do dia em que o post ficou público (a primeira cópia)."""
    if publico_em is None or publico_em.empty:
        return pd.Series(False, index=tabela.index)
    dia = pd.to_datetime(publico_em, utc=True).dt.tz_localize(None).dt.normalize()
    publico = tabela["url"].map(dia)
    abertura = pd.to_datetime(tabela["abertura"], errors="coerce")
    return (abertura > publico).fillna(False).astype(bool)


def ligar(
    partes_: pd.DataFrame,
    rede: pd.DataFrame,
    receita: pd.DataFrame,
    fixados: dict[ids.Chave, str] | None = None,
    publico_em: pd.Series | None = None,
) -> pd.DataFrame:
    """As partes com `id_entidade`, `cnpj_raiz`, `lei`, `ligacao_por` e `candidatos`.

    `publico_em`: url → quando o post ficou público (a primeira cópia no Wayback), para a regra 2.
    """
    candidatos = _candidatos(rede, receita, fixados or {})
    decisoes = {
        str(nome): _decidir(str(nome), grupo)
        for nome, grupo in candidatos[
            candidatos["nome_normalizado"].isin(set(partes_["nome_normalizado"]))
        ].groupby("nome_normalizado")
    }
    sem: dict[str, object] = {
        **dict.fromkeys(("id_entidade", "cnpj_raiz", "lei", "abertura")),
        "ligacao_por": SEM_LIGACAO,
        "candidatos": 0,
    }
    decididas = pd.DataFrame(
        [decisoes.get(n, sem) for n in partes_["nome_normalizado"]],
        columns=[
            "id_entidade",
            "cnpj_raiz",
            "lei",
            "abertura",
            "ligacao_por",
            "candidatos",
        ],
        index=partes_.index,
    ).astype(object)
    tabela = pd.concat([partes_, decididas], axis=1)
    depois = _aberto_depois(tabela, publico_em)
    tabela.loc[depois, ["id_entidade", "cnpj_raiz", "lei"]] = None
    tabela.loc[depois, "ligacao_por"] = ABERTO_DEPOIS
    tabela = tabela[list(COLUNAS_DAS_PARTES)]
    return tabela.astype({"candidatos": "int64"}).sort_values(
        ["assessoria", "url", "nome"], ignore_index=True
    )


# --- duplicatas -------------------------------------------------------------------------------------
PARTES_IGUAIS = "partes_iguais"
COLUNAS_DOS_NEGOCIOS = (
    "assessoria",
    "url",
    "id_negocio",
    "paginas_do_negocio",
    "paginas_com_as_mesmas_partes",
    "duplicata_por",
)


def _id_negocio(texto: str) -> str:
    return "N" + hashlib.sha256(texto.encode()).hexdigest()[: ids.HEXADECIMAIS]


def _chave_das_partes(ligadas: pd.DataFrame) -> pd.Series:
    """(assessoria, url) → as partes da página, cada uma pela entidade ou pelo nome, em ordem."""
    parte = ligadas["id_entidade"].where(
        ligadas["id_entidade"].notna(),
        "nome:" + ligadas["nome_normalizado"].fillna(ligadas["nome"]),
    )
    return (
        ligadas.assign(_parte=parte)
        .groupby(["assessoria", "url"])["_parte"]
        .agg(lambda p: "|".join(sorted(set(p))))
    )


def _junta(grupo: pd.DataFrame) -> bool:
    """Assessorias diferentes e tipos que não se contradizem."""
    tipos = set(grupo["tipo"]) - {ma.SEM_TIPO}
    return grupo["assessoria"].is_unique and len(tipos) <= 1


def negocios(tabela: pd.DataFrame, ligadas: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por página com o `id_negocio`: o mesmo para as páginas do mesmo negócio."""
    paginas = tabela[["assessoria", "url", "tipo"]].copy()
    chaves = _chave_das_partes(ligadas)
    paginas["_partes"] = [
        chaves.get((a, u))
        for a, u in zip(paginas["assessoria"], paginas["url"], strict=True)
    ]
    com_partes = paginas["_partes"].notna()
    paginas["paginas_com_as_mesmas_partes"] = (
        paginas.groupby("_partes")["url"].transform("size").where(com_partes, 1)
    )
    juntam = {
        chave: _junta(grupo) for chave, grupo in paginas[com_partes].groupby("_partes")
    }
    paginas["id_negocio"] = [
        _id_negocio("partes|" + p)
        if isinstance(p, str) and juntam[p]
        else _id_negocio(f"pagina|{a}|{u}")
        for a, u, p in zip(
            paginas["assessoria"], paginas["url"], paginas["_partes"], strict=True
        )
    ]
    paginas["paginas_do_negocio"] = paginas.groupby("id_negocio")["url"].transform(
        "size"
    )
    paginas["duplicata_por"] = (
        pd.Series(PARTES_IGUAIS, index=paginas.index)
        .where(paginas["paginas_do_negocio"] > 1, None)
        .astype(object)
    )
    return (
        paginas[list(COLUNAS_DOS_NEGOCIOS)]
        .astype(
            {"paginas_do_negocio": "int64", "paginas_com_as_mesmas_partes": "int64"}
        )
        .sort_values(["assessoria", "url"], ignore_index=True)
    )


# --- os números da conferência ------------------------------------------------------------------
def resumo(tabela: pd.DataFrame, ligadas: pd.DataFrame, negocios_: pd.DataFrame) -> str:
    """Quantas partes ligaram, por regra; as do Brasil e as de fora; quantas duplicatas juntaram."""
    paises = tabela.set_index(["assessoria", "url"])["paises"]
    pais = pd.Series(
        [
            paises.get((a, u))
            for a, u in zip(ligadas["assessoria"], ligadas["url"], strict=True)
        ],
        index=ligadas.index,
    )
    com_cnpj = ligadas["cnpj_raiz"].notna()
    no_brasil = pais == "BR"
    de_fora = pais.notna() & ~pais.fillna("").str.contains("BR")
    por_regra = ", ".join(
        f"{r} {n}" for r, n in ligadas["ligacao_por"].value_counts().items()
    )
    juntados = negocios_.loc[negocios_["duplicata_por"].notna(), "id_negocio"]
    return (
        f"{len(ligadas)} partes; {com_cnpj.sum()} com CNPJ ({por_regra}); "
        f"negócios só no Brasil: {no_brasil.sum()} partes, {(no_brasil & com_cnpj).sum()} com CNPJ; "
        f"negócios sem BR na página: {de_fora.sum()} partes, {(de_fora & com_cnpj).sum()} com CNPJ; "
        f"{negocios_['id_negocio'].nunique()} negócios em {len(negocios_)} páginas "
        f"({juntados.nunique()} juntados de {len(juntados)} páginas)"
    )
