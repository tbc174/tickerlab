"""Partes dos negócios de M&A ligadas à rede de entidades, e o mesmo negócio de vários sites junto (ADR
0082, série 5 do plano de M&A, passo 3; regras da rede na ADR 0077).

**Como cada parte liga** (só regras exatas; testes em `tests/test_base_ma_ligacao.py`):
1. o nome normalizado (`normalizar`: sem acento nem caixa, sem "S.A.", "Ltda" e outras formas
   jurídicas no fim, sem "Grupo") contra os nomes das empresas e fundos da rede **e** contra a razão
   social de todas as empresas do CNPJ da Receita; as duas listas contam juntas;
2. só se nada casou: o nome fantasia dos estabelecimentos (a filial liga pela raiz);
3. um candidato só → `nome_exato` ou `nome_fantasia`; mais de um → `na_duvida` (nunca se escolhe);
   nenhum → `sem_ligacao`. O casamento aproximado fica com a prova de conceito do Splink.

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
COLUNAS_DA_RECEITA = ("raiz", "nome_normalizado", "por", "pessoa")
CODIFICACAO = "latin-1"
TAMANHO_DA_PARTE = 1_000_000
RAZAO, NATUREZA = 1, 2  # colunas dos `Empresas*.zip`
FANTASIA = 4  # coluna dos `Estabelecimentos*.zip`
MEI = 4  # coluna do `Simples.zip` (opção pelo MEI)
OPTANTE = "S"
Arquivo = Path | IO[bytes]


def _partes(arquivo_zip: Arquivo, colunas: list[int]) -> Iterator[pd.DataFrame]:
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
        for parte in _partes(arquivo, [0, coluna]):
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
    arquivos: Sequence[Arquivo], coluna: int, raizes: set[str]
) -> pd.Series:
    """raiz → valor da coluna, só das raízes pedidas."""
    pedacos = [
        parte[parte[0].isin(raizes)].set_index(0)[coluna]
        for arquivo in arquivos
        for parte in _partes(arquivo, [0, coluna])
    ]
    if not pedacos:
        return pd.Series(dtype=object)
    valores = pd.concat(pedacos)
    return valores[~valores.index.duplicated()]


def ler_receita(
    empresas: Sequence[Arquivo],
    estabelecimentos: Sequence[Arquivo],
    simples: Sequence[Arquivo],
    nomes: set[str],
) -> pd.DataFrame:
    """As raízes cujo nome (razão social ou nome fantasia) normalizado é o nome de uma parte.

    `pessoa`: empresário individual, natureza do grupo 4, MEI ou natureza que a Receita não deu (o
    conservador, como a rede). Lê os arquivos por partes; guarda só raiz e o nome da parte.
    """
    razao = _pelo_nome(empresas, RAZAO, nomes).assign(por=RAZAO_SOCIAL)
    fantasia = _pelo_nome(estabelecimentos, FANTASIA, nomes).assign(por=NOME_FANTASIA)
    achados = pd.concat([razao, fantasia], ignore_index=True)
    raizes = set(achados["raiz"])
    natureza = achados["raiz"].map(_das_raizes(empresas, NATUREZA, raizes))
    mei = achados["raiz"].map(_das_raizes(simples, MEI, raizes).str.strip() == OPTANTE)
    pessoa = (
        natureza.isna()
        | natureza.fillna("").map(natureza_de_pessoa)
        | (mei.fillna(False).astype(bool))
    )
    return achados.assign(pessoa=pessoa.astype(bool))[list(COLUNAS_DA_RECEITA)]


# --- a ligação --------------------------------------------------------------------------------------
NOME_EXATO, NA_DUVIDA, SEM_LIGACAO = "nome_exato", "na_duvida", "sem_ligacao"


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
    da_receita = da_receita.assign(lei=da_receita["id_entidade"].map(lei))
    da_rede = rede.assign(por=RAZAO_SOCIAL, pessoa=False)
    colunas = ["nome_normalizado", "id_entidade", "cnpj_raiz", "lei", "por", "pessoa"]
    return pd.concat([da_rede[colunas], da_receita[colunas]], ignore_index=True).astype(
        object
    )


def _decidir(grupo: pd.DataFrame) -> dict[str, object]:
    exato = grupo[grupo["por"] == RAZAO_SOCIAL]
    escolhidos = exato if len(exato) else grupo  # o nome fantasia só sem nome exato
    por_entidade = escolhidos.groupby("id_entidade", sort=True).agg(
        pessoa=("pessoa", "any"),
        cnpj_raiz=("cnpj_raiz", "first"),
        lei=("lei", "first"),
    )
    vazia: dict[str, object] = dict.fromkeys(("id_entidade", "cnpj_raiz", "lei"))
    if len(por_entidade) > 1:
        return {**vazia, "ligacao_por": NA_DUVIDA, "candidatos": len(por_entidade)}
    unica = por_entidade.iloc[0]
    if unica["pessoa"]:
        return {**vazia, "ligacao_por": SEM_LIGACAO, "candidatos": 1}
    return {
        "id_entidade": por_entidade.index[0],
        "cnpj_raiz": unica["cnpj_raiz"] if pd.notna(unica["cnpj_raiz"]) else None,
        "lei": unica["lei"] if pd.notna(unica["lei"]) else None,
        "ligacao_por": NOME_EXATO if len(exato) else NOME_FANTASIA,
        "candidatos": 1,
    }


def ligar(
    partes_: pd.DataFrame,
    rede: pd.DataFrame,
    receita: pd.DataFrame,
    fixados: dict[ids.Chave, str] | None = None,
) -> pd.DataFrame:
    """As partes com `id_entidade`, `cnpj_raiz`, `lei`, `ligacao_por` e `candidatos`."""
    candidatos = _candidatos(rede, receita, fixados or {})
    decisoes = {
        nome: _decidir(grupo)
        for nome, grupo in candidatos[
            candidatos["nome_normalizado"].isin(set(partes_["nome_normalizado"]))
        ].groupby("nome_normalizado")
    }
    sem: dict[str, object] = {
        **dict.fromkeys(("id_entidade", "cnpj_raiz", "lei")),
        "ligacao_por": SEM_LIGACAO,
        "candidatos": 0,
    }
    decididas = pd.DataFrame(
        [decisoes.get(n, sem) for n in partes_["nome_normalizado"]],
        columns=["id_entidade", "cnpj_raiz", "lei", "ligacao_por", "candidatos"],
        index=partes_.index,
    ).astype(object)
    tabela = pd.concat([partes_, decididas], axis=1)[list(COLUNAS_DAS_PARTES)]
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
