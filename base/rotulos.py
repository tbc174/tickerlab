"""Rótulos de insolvência (série B2): recuperação judicial ou extrajudicial, falência e liquidação.

Fonte: o IPE da CVM desde 2003 (guardado pelo arquivista como `cvm-hist-ipe`). Dois tipos de
evidência, cada uma com a data em que ficou pública (`conhecido_em` = data de entrega à CVM):
- `categoria_ipe`: documentos das categorias próprias da CVM ("Informações de Companhias em
  Recuperação Judicial ou Extrajudicial", "em Falência", "em Liquidação", "Pedidos de falência");
- `fato_relevante`: fato relevante ou comunicado cujo assunto anuncia o pedido. Costuma ser o primeiro
  sinal público, mas pode ser um esclarecimento de notícia: quem montar o modelo decide se usa.

`primeira_ocorrencia` dá a primeira data de cada rótulo por empresa: é o rótulo "entrou em
recuperação judicial em tal data" do catálogo de modelos (ADR 0030).
"""

import io
import re
import unicodedata
import zipfile

import pandas as pd

COLUNAS = (
    "cnpj",
    "empresa",
    "rotulo",
    "evidencia",
    "categoria",
    "tipo",
    "assunto",
    "conhecido_em",
    "referencia",
    "protocolo",
    "versao",
    "link",
)
# categoria (sem acento, minúsculas) da CVM → rótulo; o tipo decide judicial ou extrajudicial
CATEGORIAS = (
    ("recuperacao judicial ou extrajudicial", "recuperacao"),
    ("pedidos de falencia", "pedido_de_falencia"),
    ("em falencia", "falencia"),
    ("sentenca de falencia", "falencia"),
    ("em liquidacao", "liquidacao"),
)
CATEGORIAS_DE_ANUNCIO = ("fato relevante", "comunicado ao mercado")
# assunto do fato relevante → rótulo (a primeira que casar vale)
ASSUNTOS = (
    (re.compile(r"recuperacao extrajudicial"), "recuperacao_extrajudicial"),
    (re.compile(r"recuperacao judicial"), "recuperacao_judicial"),
    (re.compile(r"(pedido|requerimento)s? de (auto)?falencia"), "pedido_de_falencia"),
    (
        re.compile(
            r"(decreta\w*|sentenca|convola\w*|decreto)( \w+){0,3} (de )?falencia"
            r"|autofalencia|falencia (da|de) (companhia|empresa|sociedade)"
        ),
        "falencia",
    ),
    (
        re.compile(r"liquidacao extrajudicial|em liquidacao|liquidacao da companhia"),
        "liquidacao",
    ),
)
# nomes de órgãos e de leis que só mencionam a palavra (Oi, 2016: "Tribunal de Falências")
MENCOES_SEM_EVENTO = re.compile(
    r"(tribunal|vara|lei|juizo) (empresarial )?de falencias?"
)


def _simples(texto: object) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode(
        "ascii", "ignore"
    )
    return sem_acento.decode().lower().strip()


def _ler_ipe_bruto(conteudo_do_zip: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nome = next(n for n in arquivo.namelist() if "ipe_cia_aberta" in n)
        with arquivo.open(nome) as csv:
            return pd.read_csv(csv, sep=";", encoding="latin-1", dtype=str).fillna("")


def _texto(linha: pd.Series, coluna: str) -> str:
    return str(linha[coluna]).strip()


def _rotulo_da_categoria(categoria: str, tipo: str) -> str | None:
    for trecho, rotulo in CATEGORIAS:
        if trecho in categoria:
            if rotulo == "recuperacao":
                return (
                    "recuperacao_extrajudicial"
                    if "extrajudicial" in tipo
                    else "recuperacao_judicial"
                )
            return rotulo
    return None


def _rotulo_do_assunto(assunto: str) -> str | None:
    assunto = MENCOES_SEM_EVENTO.sub(" ", assunto)
    return next((rotulo for padrao, rotulo in ASSUNTOS if padrao.search(assunto)), None)


def _classificar(linha: pd.Series) -> tuple[str, str] | None:
    """(rótulo, evidência) do documento, ou None se não fala de insolvência."""
    categoria, tipo = _simples(linha["Categoria"]), _simples(linha["Tipo"])
    rotulo = _rotulo_da_categoria(categoria, tipo)
    if rotulo:
        return rotulo, "categoria_ipe"
    if categoria in CATEGORIAS_DE_ANUNCIO:
        rotulo = _rotulo_do_assunto(_simples(linha["Assunto"]))
        if rotulo:
            return rotulo, "fato_relevante"
    return None


def ler_insolvencia_do_ipe(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os documentos de um arquivo anual do IPE que indicam insolvência, um por entrega."""
    bruto = _ler_ipe_bruto(conteudo_do_zip)
    linhas = []
    for _, linha in bruto.iterrows():
        classe = _classificar(linha)
        if classe is None:
            continue
        linhas.append(
            {
                "cnpj": _texto(linha, "CNPJ_Companhia"),
                "empresa": _texto(linha, "Nome_Companhia"),
                "rotulo": classe[0],
                "evidencia": classe[1],
                "categoria": _texto(linha, "Categoria"),
                "tipo": _texto(linha, "Tipo"),
                "assunto": _texto(linha, "Assunto"),
                "conhecido_em": linha["Data_Entrega"],
                "referencia": linha["Data_Referencia"],
                "protocolo": _texto(linha, "Protocolo_Entrega"),
                "versao": pd.to_numeric(linha["Versao"], errors="coerce"),
                "link": _texto(linha, "Link_Download"),
            }
        )
    tabela = pd.DataFrame(linhas, columns=list(COLUNAS))
    if tabela.empty:
        return tabela
    for coluna in ("conhecido_em", "referencia"):
        tabela[coluna] = pd.to_datetime(tabela[coluna], errors="coerce").dt.date
    tabela = tabela.dropna(subset=["conhecido_em"])
    # reapresentações da mesma entrega: fica a versão mais nova
    tabela = tabela.sort_values(["protocolo", "versao"]).drop_duplicates(
        "protocolo", keep="last"
    )
    return tabela.sort_values(["conhecido_em", "cnpj"]).reset_index(drop=True)


def primeira_ocorrencia(tabela: pd.DataFrame) -> pd.DataFrame:
    """A primeira data pública de cada rótulo por empresa (com a evidência daquele dia)."""
    if tabela.empty:
        return tabela
    ordenada = tabela.sort_values(["conhecido_em", "protocolo"])
    return ordenada.drop_duplicates(["cnpj", "rotulo"], keep="first").reset_index(
        drop=True
    )
