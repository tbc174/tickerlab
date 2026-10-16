"""Empresa ↔ série da prévia do balanço (série B13): quem cada regulador enxerga e de que ação é.

Os reguladores falam de quem opera (a operadora de saúde, a distribuidora de energia, o banco no Pix),
e quem opera muitas vezes é uma controlada da companhia listada. A ligação usa as controladas do FRE
(`base/controladas.py`), na ordem de segurança:

1. **CNPJ** (raiz de 8 dígitos) da entidade igual ao da companhia (`propria`) ou ao de uma controlada
   ou coligada informada no FRE (`controlada`, `coligada`): ANS (também pelo cadastro das operadoras,
   ativas e canceladas), SAMP da ANEEL, Pix (o ISPB é a raiz do CNPJ), Anatel e SUSEP (pelo cadastro
   das entidades autorizadas: o código FIP do SES ganha o CNPJ);
2. **nome** igual, depois de normalizar (sem acento, pontuação nem "S.A."/"LTDA" no fim), ao nome da
   companhia ou à razão social de uma sociedade dela: ANP e ONS, que só trazem o nome. Nada de semelhança
   aproximada: um nome parecido não liga (ligar errado é pior que não ligar);
3. **tabela conferida** (`base/conferidas/empresa_serie.csv`, `por` = `tabela`): as siglas sem CNPJ nem
   razão social (ferrovias da ANTT, companhias aéreas da ANAC) ganham o CNPJ de quem opera, conferido no
   FRE e no CNPJ da Receita, e daí ligam pelo FRE como no item 1 (as datas vêm da CVM, não da tabela).
   Uma sigla pode ter mais de um CNPJ: a concessionária e a dona dela (a FCA e a VLI);
4. **produtos do Comex Stat** (`via` = `produto`): o Comex não diz quem exportou, então a tabela liga o
   capítulo do NCM (4 dígitos: 2601, minério de ferro) às companhias expostas a ele. É exposição, não
   posse: sem participação e nunca `principal`.

Uma entidade pode ligar a várias companhias (o FRE guarda ligações antigas e participações sem tipo
informado, `sem_tipo`): `principal` marca a que usar (`_principal`). Toda entidade aparece no resultado,
com ou sem ligação, para a revisão ver o que faltou. `desde` = primeira entrega à CVM de um FRE que
informava a ligação: ela não vale antes disso (sem olhar o futuro). `origem_sha256` leva ao arquivo de
onde a entidade saiu (no Comex, à versão da tabela conferida).
"""

import hashlib
import io
import json
import re
import unicodedata
import zipfile
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import IO

import pandas as pd
import sqlalchemy as sa

from base import fca
from base.controladas import cnpj14
from base.parquet import (
    LINHAGEM,
    arquivos_atuais,
    gravar_se_mudou,
    origem_de_tabela,
)
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.versao_do_codigo import versao_do_codigo

TABELA = "empresa_serie"
TABELA_CONFERIDA = Path(__file__).resolve().parent / "conferidas" / "empresa_serie.csv"
COLUNAS_DAS_ENTIDADES = ("fonte", "chave", "nome", "raiz")
COLUNAS = (
    "fonte", "chave", "nome", "raiz", "cnpj_companhia", "companhia", "via", "por",
    "participacao", "desde", "ultima_referencia", "principal", "tickers", "origem_sha256",
)  # fmt: skip
ORDEM_DAS_VIAS = {"propria": 0, "controlada": 1, "coligada": 2, "sem_tipo": 3}
PRODUTO = "produto"  # via do Comex: exposição ao produto, não posse
PELA_TABELA = "tabela"
COMEX = "comexstat"
SUFIXOS = {"S", "A", "SA", "LTDA", "EIRELI", "ME", "EPP"}
NAO_ALFANUMERICO = re.compile(r"[^A-Z0-9]+")
ANO = re.compile(r"(?<!\d)(\d{4})(?!\d)")
PERIODO = re.compile(r"\d{4}[_-]?\d{0,2}")
TAMANHO_DO_PEDACO = 500_000


def nome_normalizado(nome: object) -> str | None:
    """'Ipiranga Produtos de Petróleo S.A.' -> 'IPIRANGA PRODUTOS DE PETROLEO'."""
    if nome is None or (isinstance(nome, float) and pd.isna(nome)):
        return None
    sem_acento = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore")
    palavras = NAO_ALFANUMERICO.sub(" ", sem_acento.decode().upper()).split()
    while palavras and palavras[-1] in SUFIXOS:
        palavras.pop()
    return " ".join(palavras) or None


def _raiz(cnpj: object) -> str | None:
    completo = cnpj14(cnpj)
    return completo[:8] if completo else None


def _entidades(
    fonte: str, chaves: Iterable, nomes: Iterable, raizes: Iterable
) -> pd.DataFrame:
    tabela = pd.DataFrame(
        {"chave": list(chaves), "nome": list(nomes), "raiz": list(raizes)}
    )
    tabela = tabela.dropna(subset=["chave"])
    tabela["chave"] = tabela["chave"].astype(str).str.strip()
    tabela["nome"] = tabela["nome"].astype(str).str.strip()
    tabela = tabela.drop_duplicates(subset=["chave"]).assign(fonte=fonte)
    return pd.DataFrame(tabela[list(COLUNAS_DAS_ENTIDADES)]).reset_index(drop=True)


def _csv_em_pedacos(
    arquivo: IO[bytes], colunas: list[str], codificacao: str
) -> pd.DataFrame:
    """Só as colunas pedidas, sem repetir, lendo o CSV em pedaços (arquivos de centenas de MB)."""
    partes = [
        pedaco.drop_duplicates()
        for pedaco in pd.read_csv(
            arquivo,
            sep=";",
            usecols=colunas,
            dtype=str,
            encoding=codificacao,
            encoding_errors="replace",
            chunksize=TAMANHO_DO_PEDACO,
        )
    ]
    if not partes:
        return pd.DataFrame(columns=colunas)
    return pd.concat(partes, ignore_index=True).drop_duplicates()


def entidades_ans(conteudo: bytes) -> pd.DataFrame:
    """Operadoras de saúde (registro ANS, razão social, CNPJ) de um ZIP de beneficiários."""
    colunas = ["CD_OPERADORA", "NM_RAZAO_SOCIAL", "NR_CNPJ"]
    with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo:
        tabela = _csv_em_pedacos(arquivo.open(arquivo.namelist()[0]), colunas, "utf-8")
    return _entidades(
        "ans-beneficiarios", tabela["CD_OPERADORA"], tabela["NM_RAZAO_SOCIAL"],
        tabela["NR_CNPJ"].map(_raiz),
    )  # fmt: skip


def entidades_samp(conteudo: bytes) -> pd.DataFrame:
    """Distribuidoras de energia do SAMP (guardado já sem as colunas pessoais)."""
    tabela = pd.read_parquet(
        io.BytesIO(conteudo),
        columns=["NumCNPJAgenteDistribuidora", "NomAgenteDistribuidora"],
    ).drop_duplicates()
    cnpj = tabela["NumCNPJAgenteDistribuidora"].map(cnpj14)
    return _entidades(
        "aneel-samp", cnpj, tabela["NomAgenteDistribuidora"], cnpj.str[:8]
    )


def entidades_pix(conteudo: bytes) -> pd.DataFrame:
    """Participantes do Pix: o ISPB é a raiz do CNPJ da instituição."""
    linhas = json.loads(conteudo)["value"]
    ispb = [linha["ISPB"] for linha in linhas]
    return _entidades("bcb-pix-chaves", ispb, [lin["Nome"] for lin in linhas], ispb)


def entidades_anatel(conteudo: bytes) -> pd.DataFrame:
    """Prestadoras de um CSV "_Colunas" da Anatel (o grupo econômico vai junto no nome)."""
    tabela = _csv_em_pedacos(
        io.BytesIO(conteudo), ["CNPJ", "Empresa", "Grupo Econômico"], "utf-8-sig"
    )
    cnpj = tabela["CNPJ"].map(cnpj14)
    nome = tabela["Empresa"] + " (" + tabela["Grupo Econômico"].fillna("") + ")"
    return _entidades("anatel-acessos", cnpj, nome, cnpj.str[:8])


def entidades_anp(conteudo: bytes) -> pd.DataFrame:
    """Distribuidores dos arquivos de vendas da ANP (só o nome; nos líquidos, "Agente Regulado")."""
    nomes: list[str] = []
    with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo:
        for membro in (m for m in arquivo.namelist() if "Vendas" in m):
            cabecalho = pd.read_csv(
                arquivo.open(membro), sep=";", encoding="latin-1", nrows=0
            )
            coluna = next(
                (c for c in ("Agente Regulado", "Distribuidor") if c in cabecalho),
                None,
            )
            if coluna:
                tabela = _csv_em_pedacos(arquivo.open(membro), [coluna], "latin-1")
                nomes += tabela[coluna].dropna().tolist()
    return _entidades("anp-vendas-distribuidora", nomes, nomes, [None] * len(nomes))


def entidades_ons(conteudo: bytes) -> pd.DataFrame:
    """Agentes proprietários das usinas (capacidade instalada do ONS; só o nome)."""
    tabela = pd.read_parquet(io.BytesIO(conteudo), columns=["nom_agenteproprietario"])
    nomes = tabela["nom_agenteproprietario"].dropna().str.strip().unique().tolist()
    return _entidades("ons-capacidade-geracao", nomes, nomes, [None] * len(nomes))


def entidades_antt(conteudo: bytes) -> pd.DataFrame:
    """Ferrovias de um CSV anual de produção do SIADE da ANTT (só a sigla: EFC, MRS, RMS...)."""
    tabela = _csv_em_pedacos(io.BytesIO(conteudo), ["Ferrovia"], "latin-1")
    siglas = tabela["Ferrovia"].dropna().str.strip().tolist()
    return _entidades("antt-siade", siglas, siglas, [None] * len(siglas))


def entidades_anac(conteudo: bytes) -> pd.DataFrame:
    """Companhias aéreas brasileiras do arquivo estatístico da ANAC (sigla e nome; sem CNPJ).

    A 1ª linha é "Atualizado em: ..." (pulada). A mesma sigla já foi de mais de uma empresa (ABJ): os
    nomes vão juntos, separados por " / ".
    """
    arquivo = io.BytesIO(conteudo)
    arquivo.readline()
    colunas = ["EMPRESA_SIGLA", "EMPRESA_NOME", "EMPRESA_NACIONALIDADE"]
    tabela = _csv_em_pedacos(arquivo, colunas, "utf-8")
    brasileiras = tabela[tabela["EMPRESA_NACIONALIDADE"] == "BRASILEIRA"]
    nomes = (
        brasileiras.dropna(subset=["EMPRESA_SIGLA", "EMPRESA_NOME"])
        .groupby("EMPRESA_SIGLA")["EMPRESA_NOME"]
        .agg(lambda serie: " / ".join(sorted(set(serie.str.strip()))))
    )
    return _entidades(
        "anac-estatistico", nomes.index, nomes.tolist(), [None] * len(nomes)
    )


def entidades_cadastro_ans(conteudo: bytes) -> pd.DataFrame:
    """Operadoras do cadastro da ANS (ativas ou canceladas): registro, razão social e CNPJ. A chave é
    o registro da operadora, a mesma das informações de beneficiários (`ans-beneficiarios`)."""
    tabela = pd.read_csv(
        io.BytesIO(conteudo), sep=";", dtype=str, encoding="utf-8", keep_default_na=False,
        usecols=["REGISTRO_OPERADORA", "CNPJ", "RAZAO_SOCIAL"],
    )  # fmt: skip
    return _entidades(
        "ans-beneficiarios", tabela["REGISTRO_OPERADORA"], tabela["RAZAO_SOCIAL"],
        tabela["CNPJ"].map(_raiz),
    )  # fmt: skip


def entidades_cadastro_susep(conteudo: bytes) -> pd.DataFrame:
    """Entidades autorizadas pela SUSEP: o código FIP (o `coenti` do SES, 5 dígitos) e o CNPJ."""
    itens = json.loads(conteudo)["value"]
    codigos = [str(item["entcodigofip"]).strip().zfill(5) for item in itens]
    return _entidades(
        "susep-ses", codigos, [item["entnome"] for item in itens],
        [_raiz(item["entcgc"]) for item in itens],
    )  # fmt: skip


def _periodo(url: str) -> str:
    return max(PERIODO.findall(url.rsplit("/", 1)[-1]), default="")


# fontes lidas em todos os períodos: quem já saiu (a TIM Celular, incorporada em 2018; a distribuidora
# vendida) também liga, senão a história das fontes setoriais ficava sem empresa (série 4, 16/10/2026)
TODOS_OS_PERIODOS = {
    "anp-vendas-distribuidora", "antt-siade", "anatel-acessos", "aneel-samp", "ans-operadoras",
}  # fmt: skip


def escolher(fonte: str, urls: list[str]) -> set[str]:
    """Que arquivos ler: todos os períodos das fontes da história (`TODOS_OS_PERIODOS`: os ZIPs da
    ANP, os anos da ANTT e do SAMP, todos os "_Colunas" da Anatel, as operadoras ativas e as
    canceladas da ANS) e, nas outras, os de maior período no nome (ano, ano-mês ou data)."""
    if fonte in TODOS_OS_PERIODOS:
        return set(urls)
    maior = max((_periodo(u) for u in urls), default="")
    return {u for u in urls if _periodo(u) == maior}


# fonte do arquivista -> (que arquivos servem, leitor)
LEITORES: dict[str, tuple[Callable[[str], bool], Callable[[bytes], pd.DataFrame]]] = {
    "ans-beneficiarios": (lambda url: url.endswith(".zip"), entidades_ans),
    "aneel-samp": (lambda url: url.endswith(".parquet"), entidades_samp),
    "bcb-pix-chaves": (lambda url: "ChavesPix" in url, entidades_pix),
    "anatel-acessos": (lambda url: url.endswith("_Colunas.csv"), entidades_anatel),
    "anp-vendas-distribuidora": (lambda url: url.endswith(".zip"), entidades_anp),
    "ons-capacidade-geracao": (lambda url: url.endswith(".parquet"), entidades_ons),
    "antt-siade": (lambda url: url.endswith(".csv"), entidades_antt),
    "anac-estatistico": (lambda url: url.endswith(".csv"), entidades_anac),
    "ans-operadoras": (lambda url: url.endswith(".csv"), entidades_cadastro_ans),
    "susep-cadastro": (lambda url: "DadosCadastrais" in url, entidades_cadastro_susep),
}


def entidades_das_fontes(conexao: sa.Connection) -> pd.DataFrame:
    """As entidades de cada fonte guardada no acervo (a história ou a safra mais recente, `escolher`)."""
    partes = []
    for fonte, (serve, ler) in LEITORES.items():
        originais = [o for o in originais_mais_recentes(conexao, fonte) if serve(o.url)]
        urls = escolher(fonte, [o.url for o in originais])
        for original in (o for o in originais if o.url in urls):
            conteudo = acervo.ler_original(original.caminho_do_original)
            if conteudo is not None:
                partes.append(ler(conteudo).assign(origem_sha256=original.sha256))
    if not partes:
        return pd.DataFrame(columns=[*COLUNAS_DAS_ENTIDADES, "origem_sha256"])
    juntas = pd.concat(partes, ignore_index=True)
    return juntas.drop_duplicates(subset=["fonte", "chave"]).reset_index(drop=True)


def tabela_conferida(caminho: Path = TABELA_CONFERIDA) -> pd.DataFrame:
    """Siglas e produtos ligados à mão a um CNPJ, linha a linha, com observação e conferência."""
    return pd.read_csv(
        caminho, sep=";", dtype=str, keep_default_na=False, encoding="utf-8"
    )


def com_a_tabela_conferida(
    entidades: pd.DataFrame, conferida: pd.DataFrame
) -> pd.DataFrame:
    """As entidades sem CNPJ que estão na tabela ganham a raiz (uma linha por CNPJ) e o nome dela;
    `raiz_conferida` marca essas linhas, para `ligar` dizer `por` = `tabela`."""
    siglas = conferida.loc[
        conferida["fonte"] != COMEX, ["fonte", "chave", "nome_na_fonte", "cnpj"]
    ]
    juntas = entidades.merge(siglas, on=["fonte", "chave"], how="left")
    achou = juntas["raiz"].isna() & (juntas["cnpj"].fillna("") != "")
    juntas["raiz"] = juntas["raiz"].where(~achou, juntas["cnpj"].map(_raiz))
    juntas["nome"] = juntas["nome"].where(~achou, juntas["nome_na_fonte"])
    juntas["raiz_conferida"] = achou
    return juntas.drop(columns=["nome_na_fonte", "cnpj"])


def ligacoes_de_produto(
    conferida: pd.DataFrame, caminho: Path = TABELA_CONFERIDA
) -> pd.DataFrame:
    """Capítulo do NCM → companhias expostas a ele (`via` = `produto`), direto da tabela conferida.

    `origem_sha256` é o da tabela conferida: diz que versão dela fez a ligação.
    """
    produtos = conferida[conferida["fonte"] == COMEX]
    tabela = pd.DataFrame(
        {
            "fonte": COMEX,
            "chave": produtos["chave"],
            "nome": produtos["nome_na_fonte"],
            "cnpj_companhia": produtos["cnpj"].map(cnpj14),
            "companhia": produtos["razao_social"],
            "via": PRODUTO,
            "por": PELA_TABELA,
            "participacao": float("nan"),
            "principal": False,
            "origem_sha256": hashlib.sha256(caminho.read_bytes()).hexdigest(),
        }
    )
    return tabela.reindex(columns=list(COLUNAS)).reset_index(drop=True)


def _donos(controladas: pd.DataFrame) -> pd.DataFrame:
    """Raiz de CNPJ e nome normalizado de cada companhia e de cada sociedade ligada a ela."""
    propria = (
        controladas[["cnpj_companhia", "companhia", "referencia", "conhecido_em"]]
        .drop_duplicates()
        .assign(via="propria", participacao=100.0)
    )
    propria["cnpj"] = propria["cnpj_companhia"]
    propria["nome"] = propria["companhia"]
    ligadas = controladas.assign(
        nome=controladas["razao_social"],
        via=controladas["tipo"].where(
            controladas["tipo"].isin(["controlada", "coligada"]), "sem_tipo"
        ),
    )
    todos = pd.concat([propria, ligadas], ignore_index=True)
    todos["raiz"] = todos["cnpj"].map(_raiz)
    todos["nome_normalizado"] = todos["nome"].map(nome_normalizado)
    chave = ["raiz", "nome_normalizado", "cnpj_companhia", "via"]
    return (
        todos.dropna(subset=["cnpj_companhia"])
        .groupby(chave, dropna=False)
        .agg(
            companhia=("companhia", "last"),
            participacao=("participacao", "last"),
            desde=("conhecido_em", "min"),
            ultima_referencia=("referencia", "max"),
        )
        .reset_index()
    )


def ligar(entidades: pd.DataFrame, controladas: pd.DataFrame) -> pd.DataFrame:
    """Cada entidade com as companhias a que pertence (pelo CNPJ ou, sem CNPJ, pelo nome exato)."""
    donos = _donos(controladas)
    campos = [
        "cnpj_companhia",
        "companhia",
        "via",
        "participacao",
        "desde",
        "ultima_referencia",
    ]
    com_raiz = donos.dropna(subset=["raiz"])[["raiz", *campos]].drop_duplicates()
    por_cnpj = entidades.dropna(subset=["raiz"]).merge(com_raiz, on="raiz")
    pela_tabela = (
        por_cnpj["raiz_conferida"].fillna(False).astype(bool)
        if "raiz_conferida" in por_cnpj
        else pd.Series(False, index=por_cnpj.index)
    )
    por_cnpj["por"] = pela_tabela.map({True: PELA_TABELA, False: "cnpj"})
    sem_cnpj = entidades[entidades["raiz"].isna()].copy()
    sem_cnpj["nome_normalizado"] = sem_cnpj["nome"].map(nome_normalizado)
    com_nome = donos.dropna(subset=["nome_normalizado"])
    por_nome = sem_cnpj.merge(
        com_nome[["nome_normalizado", *campos]].drop_duplicates(), on="nome_normalizado"
    ).drop(columns="nome_normalizado")
    por_nome["por"] = "nome"
    ligadas = pd.concat([por_cnpj, por_nome], ignore_index=True)
    chaves_ligadas = set(zip(ligadas["fonte"], ligadas["chave"], strict=True))
    sem_ligacao = [
        (f, c) not in chaves_ligadas
        for f, c in zip(entidades["fonte"], entidades["chave"], strict=True)
    ]
    # uma sigla com dois CNPJs na tabela e nenhum ligado fica numa linha só
    sobra = entidades.loc[sem_ligacao].drop_duplicates(subset=["fonte", "chave"])
    tudo = pd.concat([ligadas, sobra], ignore_index=True)
    tudo["principal"] = _principal(tudo)
    tudo = tudo.reindex(columns=list(COLUNAS))
    return tudo.sort_values(
        ["fonte", "chave", "principal"], ascending=[True, True, False]
    ).reset_index(drop=True)


def _principal(ligacoes: pd.DataFrame) -> pd.Series:
    """A ligação a usar de cada entidade: uma companhia com ticker hoje (quando os tickers já vieram
    do FCA; o Banco Inter S.A. saiu da bolsa e a Inter & Co ficou); depois a própria companhia;
    senão a do FRE mais recente, com
    controlada antes de coligada e, no empate, a maior participação. As outras ficam como histórico
    (uma distribuidora que já foi coligada da Eletrobras continua aparecendo, mas não é a principal)."""
    tickers = (
        ligacoes["tickers"]
        if "tickers" in ligacoes
        else pd.Series(None, index=ligacoes.index, dtype=object)
    )
    ordem = ligacoes.assign(
        _sem_ticker=tickers.isna().astype(int),
        _propria=(ligacoes["via"] != "propria").astype(int),
        _recente=pd.to_datetime(ligacoes["ultima_referencia"], errors="coerce"),
        _via=ligacoes["via"].map(ORDEM_DAS_VIAS).fillna(len(ORDEM_DAS_VIAS)),
    ).sort_values(
        [
            "fonte",
            "chave",
            "_sem_ticker",
            "_propria",
            "_recente",
            "_via",
            "participacao",
        ],
        ascending=[True, True, True, True, False, True, False],
        na_position="last",
    )
    primeira = ~ordem.duplicated(subset=["fonte", "chave"])
    valida = ordem["cnpj_companhia"].notna() & (ordem["via"] != PRODUTO)
    return (primeira & valida).reindex(ligacoes.index)


def tickers_por_cnpj(conteudo_do_fca: bytes) -> dict[str, str]:
    """CNPJ da companhia -> tickers informados no FCA (de 2018 em diante o FCA traz o código)."""
    valores = fca.ler_valores_mobiliarios(conteudo_do_fca).dropna(subset=["ticker"])
    valores["cnpj"] = valores["cnpj"].map(cnpj14)
    return (
        valores.dropna(subset=["cnpj"])
        .groupby("cnpj")["ticker"]
        .agg(lambda serie: " ".join(sorted(set(serie))))
        .to_dict()
    )


def _tickers_do_fca_mais_recente(conexao: sa.Connection) -> dict[str, str]:
    fcas = [
        o for o in originais_mais_recentes(conexao, "cvm-hist-fca") if ANO.search(o.url)
    ]
    if not fcas:
        return {}
    recente = max(fcas, key=lambda o: int(ANO.findall(o.url)[-1]))
    conteudo = acervo.ler_original(recente.caminho_do_original)
    return tickers_por_cnpj(conteudo) if conteudo is not None else {}


def montar(conexao: sa.Connection, pasta: Path, agora: datetime) -> int:
    """`<pasta>/empresa_serie/empresa_serie.parquet` (precisa de `<pasta>/controladas/`).

    Devolve quantas linhas ligaram a uma companhia, sem contar a exposição a produto do Comex (0 e
    nada gravado sem controladas ou entidades).
    """
    anos = arquivos_atuais(pasta / "controladas")
    entidades = entidades_das_fontes(conexao)
    if not anos or entidades.empty:
        return 0
    controladas = pd.concat([pd.read_parquet(a) for a in anos], ignore_index=True)
    conferida = tabela_conferida()
    tabela = pd.concat(
        [
            ligar(com_a_tabela_conferida(entidades, conferida), controladas),
            ligacoes_de_produto(conferida),
        ],
        ignore_index=True,
    )
    tabela["tickers"] = tabela["cnpj_companhia"].map(
        _tickers_do_fca_mais_recente(conexao)
    )
    tabela["principal"] = _principal(tabela)
    tabela["montado_em"] = agora.isoformat()
    tabela["versao_do_codigo"] = versao_do_codigo()
    for coluna in ("desde", "ultima_referencia"):
        tabela[coluna] = tabela[coluna].astype("string")
    conferida_em_bytes = TABELA_CONFERIDA.read_bytes()
    gravar_se_mudou(
        tabela,
        pasta / TABELA / f"{TABELA}.parquet",
        [
            *(origem_de_tabela(ano, pasta) for ano in anos),
            {
                "url": f"base/conferidas/{TABELA_CONFERIDA.name}",
                "sha256": hashlib.sha256(conferida_em_bytes).hexdigest(),
            },
        ],
        ["fonte", "chave"],
        carimbos=LINHAGEM,
    )
    return int((tabela["cnpj_companhia"].notna() & (tabela["via"] != PRODUTO)).sum())
