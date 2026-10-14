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

import csv
import io
import re
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from src import acervo
from src.banco.coletas import originais_mais_recentes

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
                # de 2003 a 2014 o protocolo vem vazio: o link identifica o documento
                "protocolo": _texto(linha, "Protocolo_Entrega")
                or _texto(linha, "Link_Download"),
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


# --- parte 2: "situação especial" do CNPJ (Receita, arquivos de estabelecimentos) ----------------
# o arquivo não tem cabeçalho: 30 colunas; 0-2 CNPJ (básico, ordem, dígito), 3 matriz (1) ou filial
# (2), 28 situação especial, 29 data da situação especial (layout da Receita, conferido em 14/10/2026)
POSICAO_DA_SITUACAO = 28
POSICAO_DA_DATA = 29
SITUACOES = {
    "FALIDO": "falencia",
    "RECUPERACAO JUDICIAL": "recuperacao_judicial",
    "RECUPERACAO EXTRAJUDICIAL": "recuperacao_extrajudicial",
    "LIQUIDACAO EXTRA-JUDICIAL": "liquidacao_extrajudicial",
    "EM LIQUID.EXTRA-JUDICIAL": "liquidacao_extrajudicial",
    "LIQUIDACAO JUDICIAL": "liquidacao_judicial",
    "EM LIQUIDACAO": "liquidacao",
    "INTERVENCAO": "intervencao",
}
MES_NA_PASTA = re.compile(r"/(\d{4}-\d{2})/Estabelecimentos\d*\.zip$", re.IGNORECASE)


def ler_situacao_especial_do_cnpj(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os estabelecimentos com "situação especial" num arquivo de estabelecimentos do CNPJ.

    Lê em fluxo (o arquivo tem milhões de linhas) e guarda só CNPJ, matriz ou filial, situação e data:
    nome fantasia, endereço, telefone e e-mail nunca saem (LGPD).
    """
    linhas = []
    with (
        zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo,
        arquivo.open(arquivo.namelist()[0]) as bruto,
    ):
        leitor = csv.reader(io.TextIOWrapper(bruto, encoding="latin-1"), delimiter=";")
        for campos in leitor:
            if len(campos) <= POSICAO_DA_DATA:
                continue
            situacao = campos[POSICAO_DA_SITUACAO].strip()
            if not situacao:
                continue
            basico, ordem, digito = (campos[i].strip() for i in range(3))
            linhas.append(
                {
                    "cnpj": f"{basico[:2]}.{basico[2:5]}.{basico[5:8]}/{ordem}-{digito}",
                    "cnpj_basico": basico,
                    "matriz": campos[3].strip() == "1",
                    "situacao_especial": situacao,
                    "rotulo": SITUACOES.get(situacao),
                    "data_situacao_especial": campos[POSICAO_DA_DATA].strip(),
                }
            )
    tabela = pd.DataFrame(
        linhas,
        columns=[
            "cnpj",
            "cnpj_basico",
            "matriz",
            "situacao_especial",
            "rotulo",
            "data_situacao_especial",
        ],
    )
    tabela["data_situacao_especial"] = pd.to_datetime(
        tabela["data_situacao_especial"], format="%Y%m%d", errors="coerce"
    ).dt.date
    tabela["rotulo"] = (
        tabela["rotulo"].astype(object).where(tabela["rotulo"].notna(), None)
    )
    return tabela


def montar_situacao_especial(
    conexao: sa.Connection, pasta: Path, agora: datetime
) -> dict[str, int]:
    """`<pasta>/cnpj_situacao_especial/<AAAA-MM>.parquet` para cada mês do CNPJ guardado.

    O CNPJ só mostra o retrato do mês: cada mês guardado vira um retrato, e o histórico "como era na
    data" nasce da sequência deles (`mes_do_retrato`, mais `data_situacao_especial` da Receita).
    """
    por_mes: dict[str, list[pd.DataFrame]] = {}
    for original in originais_mais_recentes(conexao, "rfb-cnpj"):
        achado = MES_NA_PASTA.search(original.url)
        conteudo = acervo.ler_original(original.caminho_do_original)
        if achado is None or conteudo is None:
            continue
        tabela = ler_situacao_especial_do_cnpj(conteudo).assign(
            mes_do_retrato=achado.group(1),
            origem_sha256=original.sha256,
            origem_coletada_em=pd.Timestamp(original.baixado_em).isoformat(),
            montado_em=agora.isoformat(),
        )
        por_mes.setdefault(achado.group(1), []).append(tabela)
    linhas: dict[str, int] = {}
    for mes, partes in por_mes.items():
        tabela = pd.concat(partes, ignore_index=True)
        destino = pasta / "cnpj_situacao_especial" / f"{mes}.parquet"
        destino.parent.mkdir(parents=True, exist_ok=True)
        parcial = destino.with_name(destino.name + ".parcial")
        tabela.to_parquet(parcial, index=False)
        parcial.replace(destino)
        linhas[mes] = len(tabela)
    return linhas
