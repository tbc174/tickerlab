"""Eventos de companhias abertas a partir dos dados abertos da CVM (Research, etapa 2a).

Duas fontes públicas e gratuitas, atualizadas pela CVM em `dados.cvm.gov.br`:

- **IPE** (Informações Periódicas e Eventuais): fatos relevantes, comunicados ao mercado, avisos
  aos acionistas, relatórios de proventos, press-releases de resultados... Cada linha tem a data de
  entrega (quando ficou público), a data de referência, o assunto e o **link para o documento
  original** no sistema da CVM: é a evidência primária de cada evento.
- **FCA** (Formulário Cadastral), tabela de valores mobiliários: liga o **código de negociação na
  B3** (PETR4) ao **CNPJ** da companhia. A empresa só reenvia o FCA quando algo muda, por isso se
  juntam vários anos e fica o registro mais recente de cada código.

Este módulo só lê e classifica (funções puras, testadas com amostras em `tests/arquivos/`). Baixar
os arquivos e gravar no banco ficam em `scripts/atualizar_eventos.py` e `src/banco/eventos.py`.

A classificação (tema e materialidade) é editorial e simples, documentada aqui; ela só ordena o
que aparece primeiro. Não é opinião sobre a empresa nem sinal de compra ou venda.
"""

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass

import pandas as pd

URL_DO_IPE = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip"
)
URL_DO_FCA = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip"
)
FONTE_IPE = "cvm_ipe"
CODIFICACAO_DA_CVM = "cp1252"  # os CSVs da CVM vêm em Windows-1252, separados por ";"


@dataclass(frozen=True)
class Classe:
    tema: str  # um dos temas de `src.parametros.TEMAS` (resultados, proventos, eventos, risco)
    materialidade: int  # 0 a 100: quanto o tipo de documento costuma importar
    rotulo: str  # nome curto mostrado na tela


IGNORAR = None  # categorias que não viram evento (muito volume, pouca informação para o leitor)

_PROVENTOS = re.compile(
    r"dividend|juros sobre (o )?capital|\bjcp\b|provento|rendimento|bonifica",
    re.IGNORECASE,
)


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").lower()


def classificar(categoria: str, tipo: str = "", assunto: str = "") -> Classe | None:
    """Tema e materialidade de um documento do IPE (None: não entra como evento)."""
    cat, tip = _sem_acento(categoria), _sem_acento(tipo)
    assunto = assunto or ""
    if cat == "fato relevante":
        return Classe("eventos", 100, "Fato relevante")
    if cat == "relatorio proventos":
        return Classe("proventos", 80, "Proventos")
    if cat == "aviso aos acionistas":
        if _PROVENTOS.search(assunto):
            return Classe("proventos", 80, "Proventos")
        return Classe("eventos", 40, "Aviso aos acionistas")
    if cat == "dados economico-financeiros":
        if "press-release" in tip or "demonstracoes financeiras" in tip:
            return Classe("resultados", 70, "Resultados")
        if "rating" in tip:
            return Classe("risco", 40, "Rating")
        return IGNORAR  # relatórios de agente fiduciário e outros, de debêntures
    if cat == "comunicado ao mercado":
        if "analistas" in tip:
            return Classe("resultados", 50, "Apresentação a analistas")
        if "participacao acionaria" in tip:
            return Classe("eventos", 50, "Participação relevante")
        return Classe("eventos", 40, "Comunicado ao mercado")
    if cat == "calendario de eventos corporativos":
        return Classe("eventos", 20, "Calendário")
    if cat == "assembleia":
        return Classe("eventos", 30, "Assembleia")
    return IGNORAR


def _ler_csv_do_zip(conteudo: bytes, contem: str) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo:
        nome = next(n for n in arquivo.namelist() if contem in n)
        return pd.read_csv(
            arquivo.open(nome),
            sep=";",
            encoding=CODIFICACAO_DA_CVM,
            encoding_errors="replace",
            dtype=str,
            keep_default_na=False,
        )


_NUMERO_NO_LINK = re.compile(r"numProtocolo=(\d+).*?numVersao=(\d+)", re.IGNORECASE)


def identificador(protocolo: str, versao: str, link: str) -> tuple[str, int] | None:
    """(protocolo, versão) da entrega. Os relatórios de proventos (e o IPE de 2003) vêm sem a coluna
    de protocolo: aí o número sai do próprio link da CVM ("rad-1477025"). O leitor de fatos
    relevantes usa a mesma regra no lote de medição (scripts.atualizar_leituras_cvm)."""
    if protocolo.strip():
        return protocolo.strip(), int(versao) if str(versao).isdigit() else 1
    achado = _NUMERO_NO_LINK.search(link or "")
    if achado is None:
        return None
    return f"rad-{achado.group(1)}", int(achado.group(2))


def ler_ipe(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os eventos de um arquivo anual do IPE, já classificados e sem versões repetidas.

    Colunas: protocolo, versao, cnpj, empresa, categoria, tipo, assunto, rotulo, tema,
    materialidade, referencia (data), publicado_em (data de entrega), link.
    """
    bruto = _ler_csv_do_zip(conteudo_do_zip, "ipe_cia_aberta")
    linhas = []
    for linha in bruto.itertuples(index=False):
        classe = classificar(linha.Categoria, linha.Tipo, linha.Assunto)
        if classe is None or not linha.Link_Download:
            continue
        chave = identificador(
            linha.Protocolo_Entrega, linha.Versao, linha.Link_Download
        )
        if chave is None:
            continue
        linhas.append(
            {
                "protocolo": chave[0],
                "versao": chave[1],
                "cnpj": linha.CNPJ_Companhia.strip(),
                "empresa": linha.Nome_Companhia.strip(),
                "categoria": linha.Categoria.strip(),
                "tipo": linha.Tipo.strip(),
                "assunto": linha.Assunto.strip(),
                "rotulo": classe.rotulo,
                "tema": classe.tema,
                "materialidade": classe.materialidade,
                "referencia": linha.Data_Referencia,
                "publicado_em": linha.Data_Entrega,
                "link": linha.Link_Download.strip(),
            }
        )
    eventos = pd.DataFrame(linhas)
    if eventos.empty:
        return eventos
    for coluna in ("referencia", "publicado_em"):
        eventos[coluna] = pd.to_datetime(eventos[coluna], errors="coerce").dt.date
    eventos = eventos.dropna(subset=["publicado_em"])
    # a mesma entrega pode vir em várias versões (reapresentações): fica a mais nova
    eventos = eventos.sort_values(["protocolo", "versao"]).drop_duplicates(
        "protocolo", keep="last"
    )
    return eventos.sort_values("publicado_em", ascending=False).reset_index(drop=True)


def ler_tickers_do_fca(conteudos_dos_zips: list[bytes]) -> pd.DataFrame:
    """Código de negociação na B3 → CNPJ e nome da companhia, juntando vários anos do FCA.

    Fica o registro mais recente de cada código (data de referência e versão maiores) e só o que
    é negociado em bolsa na B3. O código vira o símbolo do Yahoo (`PETR4` → `PETR4.SA`).
    Colunas: ticker, codigo, cnpj, empresa, valor_mobiliario.
    """
    partes = [_ler_csv_do_zip(c, "valor_mobiliario") for c in conteudos_dos_zips]
    if not partes:
        return pd.DataFrame(
            columns=["ticker", "codigo", "cnpj", "empresa", "valor_mobiliario"]
        )
    tabela = pd.concat(partes, ignore_index=True)
    tabela = tabela[
        (tabela["Sigla_Entidade_Administradora"].str.upper() == "B3")
        & (tabela["Mercado"].str.lower() == "bolsa")
        & tabela["Codigo_Negociacao"].str.fullmatch(r"[A-Z]{4}\d{1,2}")
    ].copy()
    tabela["versao_numerica"] = pd.to_numeric(tabela["Versao"], errors="coerce").fillna(
        0
    )
    tabela = tabela.sort_values(
        ["Codigo_Negociacao", "Data_Referencia", "versao_numerica"]
    )
    tabela = tabela.drop_duplicates("Codigo_Negociacao", keep="last")
    return pd.DataFrame(
        {
            "ticker": tabela["Codigo_Negociacao"] + ".SA",
            "codigo": tabela["Codigo_Negociacao"],
            "cnpj": tabela["CNPJ_Companhia"].str.strip(),
            "empresa": tabela["Nome_Empresarial"].str.strip(),
            "valor_mobiliario": tabela["Valor_Mobiliario"].str.strip(),
        }
    ).reset_index(drop=True)
