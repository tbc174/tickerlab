"""Notas explicativas da DFP: o texto do PDF do pacote do ENET, por página (linha 135 da fila).

`base.enet.limpar_xml` tira o PDF do documento antes de ir para o acervo, e com ele as notas
explicativas (a dívida, as contingências, as partes relacionadas...). O FRE só traz `obrigacao` até
2022. Aqui o PDF do mesmo pacote vira **texto por página**, guardado à parte (fonte `cvm-enet-notas`,
só o texto: o PDF não é guardado) e montado em `notas_dfp`.

- **Só a DFP.** Cada versão é um documento próprio, com a própria entrega: a linha vale a partir do
  `DT_RECEB` daquela versão, ou do registro seguinte da empresa quando ela entregou fora do registro
  (`base/ponto_no_tempo.divulgacao_publica`). Nada de uma versão nova aparece numa data anterior.
- **Tamanho:** o pacote tem de 13 a 33 MB, quase tudo do PDF; o texto de uma DFP fica na casa de
  centenas de KB e vai comprimido (`.json.gz`). Página sem texto (PDF escaneado) não vira linha e
  nada é inventado no lugar: a leitura por OCR (`src.leitura.texto_por_ocr`) é de quem consome.
- **Pessoa:** o texto traz nomes (administradores, assinatura do auditor). O original vai para
  `restrito/` (`src.acervo.FONTES_COM_PESSOA`) e a tabela é marcada como tendo dado de pessoa.
- **Licença:** a da CVM (ODbL, citar a fonte), a mesma do `cvm-enet`.
"""

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base.cadastro import cadastro_do_acervo
from base.contas_cvm import ler_indice
from base.enet_antigo import FormatoNaoLido
from base.parquet import LINHAGEM, gravar_se_mudou
from base.ponto_no_tempo import divulgacao_publica
from src import acervo
from src.banco.coletas import originais_mais_recentes, registrar
from src.banco.modelo import coletas
from src.versao_do_codigo import versao_do_codigo

FONTE = "cvm-enet-notas"
FONTE_DO_INDICE = (
    "cvm-hist-dfp"  # os arquivos anuais do DFP, com a entrega de cada versão
)
TABELA = "notas_dfp"
VERSAO_DO_FORMATO = 1
ASSINATURA_DO_PDF = b"%PDF-"
COLUNAS = (
    "cnpj", "empresa", "referencia", "versao", "pagina", "texto", "disponivel_em", "link",
)  # fmt: skip


def pdf_do_pacote(pacote: bytes) -> bytes:
    """O PDF (as demonstrações e as notas) dentro do zip do ENET."""
    with zipfile.ZipFile(io.BytesIO(pacote)) as arquivo:
        nomes = [n for n in arquivo.namelist() if n.lower().endswith(".pdf")]
        if not nomes:
            raise FormatoNaoLido("o pacote do ENET não tem o PDF do documento")
        pdf = arquivo.read(nomes[0])
    if not pdf.startswith(ASSINATURA_DO_PDF):
        raise FormatoNaoLido("o arquivo .pdf do pacote do ENET não é um PDF")
    return pdf


def paginas_do_pdf(pdf: bytes) -> list[str]:
    """O texto de cada página, na ordem (vazio na página só de imagem)."""
    import pypdfium2 as pdfium  # só a coleta precisa (a imagem do app já tem)

    documento = pdfium.PdfDocument(pdf)
    try:
        return [
            documento[i].get_textpage().get_text_range().strip()
            for i in range(len(documento))
        ]
    finally:
        documento.close()


def empacotar(paginas: list[str]) -> bytes:
    """O que vai para o acervo: o mesmo texto dá sempre os mesmos bytes."""
    return json.dumps(
        {"formato": VERSAO_DO_FORMATO, "paginas": paginas},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()


def desempacotar(conteudo: bytes) -> list[str]:
    dados = json.loads(conteudo)
    if dados.get("formato") != VERSAO_DO_FORMATO:
        raise ValueError(f"formato de notas desconhecido: {dados.get('formato')!r}")
    return list(dados["paginas"])


def guardar_notas(
    conexao: sa.Connection, link: str, pacote: bytes, agora: datetime
) -> list[str]:
    """Lê o PDF do pacote, guarda o texto por página no acervo e registra a coleta."""
    paginas = paginas_do_pdf(pdf_do_pacote(pacote))
    conteudo = empacotar(paginas)
    caminho = acervo.guardar_original(FONTE, link, conteudo, agora, extensao=".json")
    registrar(
        conexao,
        FONTE,
        link,
        conteudo,
        "ok",
        detalhe=f"texto de {len(paginas)} páginas; pacote de {len(pacote)} bytes",
        agora=agora,
        caminho_do_original=caminho,
    )
    return paginas


def ja_guardadas(conexao: sa.Connection) -> set[str]:
    """Os links cujo texto já está guardado (a fila pula esses)."""
    consulta = sa.select(coletas.c.url).where(
        coletas.c.fonte == FONTE, coletas.c.situacao == "ok"
    )
    return set(conexao.execute(consulta).scalars())


def montar_tabela(
    indice: pd.DataFrame,
    textos: dict[str, list[str]],
    *,
    cadastro: pd.DataFrame,
) -> pd.DataFrame:
    """`notas_dfp`: uma linha por página com texto de cada versão de DFP que tem o texto guardado.

    `indice`: `base.contas_cvm.ler_indice`; `textos`: link → páginas; `cadastro`:
    `base.cadastro.ler_cadastro`. Versão sem texto guardado não tem linha (nunca é completada com a
    de outra versão).
    """
    dfp = indice[(indice["documento"] == "DFP") & indice["link"].isin(textos)]
    dfp = dfp.dropna(subset=["recebido_em"]).drop_duplicates("link")
    if dfp.empty:
        return pd.DataFrame(columns=list(COLUNAS))
    entrega = divulgacao_publica(dfp["cnpj"], dfp["recebido_em"], cadastro)
    linhas = [
        {
            "cnpj": documento.cnpj,
            "empresa": documento.empresa,
            "referencia": documento.referencia.date(),
            "versao": int(documento.versao),
            "pagina": numero,
            "texto": texto,
            "disponivel_em": entrega.loc[documento.Index].date(),
            "link": documento.link,
        }
        for documento in dfp.itertuples()
        for numero, texto in enumerate(textos[documento.link], start=1)
        if texto
    ]
    return pd.DataFrame(linhas, columns=list(COLUNAS))


def entregues_ate(tabela: pd.DataFrame, data: object) -> pd.DataFrame:
    """O que se sabia em `data`: cada linha só depende da própria versão, então cortar antes ou depois dá o mesmo."""
    limite = pd.Timestamp(data).date()  # type: ignore[arg-type]
    return tabela[tabela["disponivel_em"] <= limite].reset_index(drop=True)


class SemOIndice(Exception):
    """O acervo não tem o cadastro nem o índice do DFP: sem eles não há data pública."""


def _indice_do_acervo(
    conexao: sa.Connection,
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    partes, origens = [], []
    for original in originais_mais_recentes(conexao, FONTE_DO_INDICE):
        conteudo = acervo.ler_original(original.caminho_do_original)
        if conteudo is None:
            continue
        partes.append(ler_indice(conteudo, "DFP"))
        origens.append({"url": original.url, "sha256": original.sha256})
    if not partes:
        raise SemOIndice(f"{TABELA}: sem o índice do DFP no acervo")
    return pd.concat(partes, ignore_index=True), origens


def montar(conexao: sa.Connection, pasta: Path, agora: datetime) -> dict[int, int]:
    """Monta `<pasta>/notas_dfp/<ano da referência>.parquet` com o texto guardado; devolve linhas por ano."""
    cadastro = cadastro_do_acervo(conexao)
    if cadastro is None:
        raise SemOIndice(f"{TABELA}: sem o cadastro de companhias no acervo")
    indice, origens_do_indice = _indice_do_acervo(conexao)
    guardados = {o.url: o for o in originais_mais_recentes(conexao, FONTE)}
    textos = {}
    for link, original in guardados.items():
        conteudo = acervo.ler_original(original.caminho_do_original)
        if conteudo is not None:
            textos[link] = desempacotar(conteudo)
    tabela = montar_tabela(indice, textos, cadastro=cadastro[0])
    if tabela.empty:
        return {}
    tabela = tabela.assign(
        ano_do_arquivo=pd.to_datetime(tabela["referencia"]).dt.year,
        origem_sha256=tabela["link"].map(lambda l: guardados[l].sha256),
        origem_coletada_em=tabela["link"].map(
            lambda l: pd.Timestamp(guardados[l].baixado_em).isoformat()
        ),
        montado_em=agora.isoformat(),
        versao_do_codigo=versao_do_codigo(),
    )
    linhas_por_ano: dict[int, int] = {}
    for ano, do_ano in tabela.groupby("ano_do_arquivo"):
        origens = [
            *origens_do_indice,
            cadastro[1],
            *(
                {"url": l, "sha256": guardados[l].sha256}
                for l in sorted(set(do_ano["link"]))
            ),
        ]
        gravar_se_mudou(
            do_ano.reset_index(drop=True),
            pasta / TABELA / f"{int(ano)}.parquet",
            origens,
            [],
            carimbos=LINHAGEM,
        )
        linhas_por_ano[int(ano)] = len(do_ano)
    return linhas_por_ano
