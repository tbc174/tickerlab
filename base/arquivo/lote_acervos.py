"""Lote acervos históricos do arquivista (rodada 4 da pesquisa de dados escondidos, 24/10/2026, linha 292
da fila; ADR 0102: licença lida vira marca, coleta com ritmo, uso citando a fonte).

Até onde dá para voltar no tempo (cotações, juros, câmbio, inflação, contas nacionais). Cada fonte guarda o
arquivo como o provedor o publica; a carga em tabela é uma linha própria da fila.

O que o lote **não** repete, porque os lotes anteriores já cobrem (conferido em `origin/main` em 24/10/2026):
- **CVM** DFP, ITR, FRE, FCA (e IPE, VLMO, CDA): as fontes `cvm-hist-*` de `fontes.py` listam a pasta
  inteira e pegam todos os anos (DFP e FCA e FRE desde 2010, ITR desde 2011); o `lote_cvm` acrescentou os
  conjuntos de fundos, FII e securitizadoras;
- **Tesouro** estoque, emissões e resgates da dívida federal, leilões, Tesouro Direto e CAPAG
  (`tesouro-br-*` de `fontes.py` e do `lote_tesouro`). Daqui entram só os pacotes de dívida que ficaram de
  fora;
- **B3 do dia** (`b3-cotahist-dia`, `b3-negocios`, `b3-boletim-pr`): o lote traz o COTAHIST **anual**;
- **BCB** Olinda, COSIF e SICONFI (`lote_bcb`) e as séries do SGS que o app lê (`src/bcb.py`): o lote
  guarda o SGS **antes de 2000**, em arquivo, que o app não lê.

Cinco famílias (a família decide a licença e a marca em `src/banco/coletas.py`):
- **B3 COTAHIST anual 1986 a 2009** (`b3-cotahist-anual`, `a_confirmar` como o resto da B3: ADR 0008, Emenda 6,
  "usar no produto com a fonte citada, risco assumido"; revenda a confirmar). Um ZIP por ano, nome a nome
  (a listagem da pasta dá 403; o `COTAHIST_A1985.ZIP` não existe). O proxy do Ibovespa de 1995 tem valores
  implausíveis: guarda-se como veio, sem tratar como série limpa;
- **BCB** (`bcb-relatorio-anual`, `bcb-sgs-pre-2000`; ODbL, vendável citando o BC): o relatório anual em PDF de
  1997 a 2011 (1990 a 1996 não estão no ar) e o SGS de antes de 2000 em janelas de até 10 anos (o SGS devolve 406
  acima disso): dólar venda desde 28/11/1984, Selic diária desde 04/06/1986, CDI diário desde 06/03/1986 e
  IPCA mensal desde 01/1980;
- **IBGE FTP por HTTP** (`ibge-precos-ftp`, `ibge-contas-nacionais-ftp`; "todos os arquivos aqui disponíveis são
  públicos", vendável com a atribuição ao IBGE): INPC e IPCA desde 1978 e as Contas Nacionais de 2005 a 2023;
- **Tesouro** (`tesouro-br-divida-*`; ODbL): os pacotes de dívida que o portal tem e as fontes anteriores não
  pegavam (execução e dotação da dívida federal, emissões diretas e soberanas, dívida e serviço da dívida dos
  estados). Ficam de fora `contratos-divida` (PDFs de contratos, sem licença escrita) e
  `relatorios-da-divida-contratual-da-uniao` (sem licença escrita);
- **IPEADATA OData** (`ipea-odata-*`; sem termos, `a_confirmar`: séries de terceiros herdam a fonte): o catálogo
  de metadados e seis séries longas, com o `SERCODIGO` de origem e a fonte original dentro do próprio arquivo.

Regras (testes em `tests/test_base_arquivo_lote_acervos.py`):
- **LGPD (ADR 0088): nenhuma destas fontes traz pessoa física.** O FRE da CVM (diretores e administradores),
  que traria, é o `cvm-hist-fre` que já existe e não é tocado aqui; nada deste lote lê pessoa;
- **ritmo pelo calendário da fonte:** o que nunca mais muda (COTAHIST de anos fechados, relatórios anuais, SGS
  antigo) é `carga-unica` e só roda pelo id; o que o provedor atualiza (preços do IBGE, Contas Nacionais, IPEADATA,
  pacotes do Tesouro) roda `mensal`. As grandes são `pesada` (só baixa o que mudou);
- **listagem do FTP do IBGE:** só pastas de dados e só as extensões de dado (`.zip`, `.xls`, `.xlsx`, `.ods`,
  `.csv`, `.txt`, `.pdf`); página `.html` é recusada pela coleta e fica de fora. Pasta que sumiu falha com o
  nome dela (nunca "ok" com zero arquivos).
"""

import re
from datetime import date, datetime
from urllib.parse import urljoin

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte
from base.arquivo.lote_brasil2 import descobrir_ckan

MENSAL = "mensal"
CARGA_UNICA = "carga-unica"

# ---------- B3: COTAHIST anual ----------

COTAHIST_ANUAL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ano}.ZIP"
PRIMEIRO_ANO_DO_COTAHIST = 1986  # o A1985 responde 404
ULTIMO_ANO_DO_COTAHIST_DESTE_LOTE = (
    2009  # de 2010 em diante é do que a B3 já publica no dia a dia
)


def descobrir_cotahist_anual(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Um ZIP por ano de 1986 a 2009, nome a nome (a listagem da pasta responde 403)."""
    return [
        Alvo(COTAHIST_ANUAL.format(ano=ano))
        for ano in range(
            PRIMEIRO_ANO_DO_COTAHIST, ULTIMO_ANO_DO_COTAHIST_DESTE_LOTE + 1
        )
    ]


# ---------- BCB: relatórios anuais e SGS antigo ----------

PASTA_DO_RELATORIO = "https://www.bcb.gov.br/pec/boletim/"
# 1997 tem um PDF só (nome curto); 1998 e 1999 só têm uma página com um PDF por capítulo
RELATORIO_DE_1997 = PASTA_DO_RELATORIO + "banual97/rel97-p.pdf"
PAGINAS_DOS_RELATORIOS_EM_CAPITULOS = (
    PASTA_DO_RELATORIO + "banual98/banual.asp?frame=1",
    PASTA_DO_RELATORIO + "banual99/banual.asp?frame=1",
)
PRIMEIRO_ANO_DO_RELATORIO_EM_UM_PDF = 2000
ULTIMO_ANO_DO_RELATORIO = 2011
PDF_DO_CAPITULO = re.compile(rb'href="(rel\d{4}[^"/]*\.pdf)"', re.IGNORECASE)


def descobrir_relatorios_anuais(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os relatórios anuais do Banco Central de 1997 a 2011, em PDF."""
    alvos = [Alvo(RELATORIO_DE_1997)]
    for pagina in PAGINAS_DOS_RELATORIOS_EM_CAPITULOS:
        capitulos = dict.fromkeys(
            m.decode() for m in PDF_DO_CAPITULO.findall(cliente.ler(pagina).conteudo)
        )
        if not capitulos:
            raise ErroDeDescoberta(f"nenhum capítulo em PDF em {pagina}")
        alvos += [Alvo(urljoin(pagina, c)) for c in capitulos]
    alvos += [
        Alvo(f"{PASTA_DO_RELATORIO}banual{ano}/rel{ano}p.pdf")
        for ano in range(
            PRIMEIRO_ANO_DO_RELATORIO_EM_UM_PDF, ULTIMO_ANO_DO_RELATORIO + 1
        )
    ]
    return alvos


SGS = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
    "?formato=json&dataInicial={inicio:%d/%m/%Y}&dataFinal={fim:%d/%m/%Y}"
)
ANOS_POR_PEDIDO_DO_SGS = 10  # acima disso o SGS responde 406
FIM_DO_SGS_ANTIGO = date(1999, 12, 31)  # de 2000 em diante é o que `src/bcb.py` já lê
# código do SGS -> primeiro dia que a série tem (medido em 24/10/2026)
SERIES_DO_SGS_ANTIGO = {
    1: date(1984, 11, 28),  # dólar americano (venda), diário
    11: date(1986, 6, 4),  # taxa Selic, diária
    12: date(1986, 3, 6),  # CDI, diário
    433: date(1980, 1, 1),  # IPCA, variação mensal
}


def _mais_anos(dia: date, anos: int) -> date:
    try:
        return dia.replace(year=dia.year + anos)
    except ValueError:  # 29/02
        return dia.replace(year=dia.year + anos, day=28)


def janelas(inicio: date, fim: date) -> list[tuple[date, date]]:
    """Janelas de até 10 anos, sem buraco nem sobreposição, de `inicio` a `fim` (inclusive)."""
    achadas: list[tuple[date, date]] = []
    comeco = inicio
    while comeco <= fim:
        ultimo = min(
            _mais_anos(comeco, ANOS_POR_PEDIDO_DO_SGS).toordinal() - 1, fim.toordinal()
        )
        achadas.append((comeco, date.fromordinal(ultimo)))
        comeco = date.fromordinal(ultimo + 1)
    return achadas


def descobrir_sgs_antigo(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Um pedido por série e por janela de 10 anos, de cada começo de série até 31/12/1999."""
    return [
        Alvo(SGS.format(codigo=codigo, inicio=inicio, fim=fim), ".json")
        for codigo, primeiro_dia in SERIES_DO_SGS_ANTIGO.items()
        for inicio, fim in janelas(primeiro_dia, FIM_DO_SGS_ANTIGO)
    ]


# ---------- IBGE: FTP por HTTP ----------

RAIZ_DO_IBGE = "https://ftp.ibge.gov.br/"
PRECOS_DO_IBGE = RAIZ_DO_IBGE + "Precos_Indices_de_Precos_ao_Consumidor/"
CONTAS_DO_IBGE = RAIZ_DO_IBGE + "Contas_Nacionais/Sistema_de_Contas_Nacionais/"
# (pasta, quantos níveis de subpasta descer): índices de preços desde 1978 (INPC e IPCA)
PASTAS_DE_PRECOS_DO_IBGE = (
    (PRECOS_DO_IBGE + "INPC/Serie_Historica/", 0),
    (PRECOS_DO_IBGE + "IPCA/Serie_Historica/", 0),
    (PRECOS_DO_IBGE + "INPC/", 0),
    (PRECOS_DO_IBGE + "Numeros_Indices/Numind_INPC_IPCA/", 0),
)
NIVEIS_DAS_CONTAS_NACIONAIS = 3  # ano -> tabelas_xls -> sinoticas -> arquivo
EXTENSOES_DO_IBGE = (".zip", ".xls", ".xlsx", ".ods", ".csv", ".txt", ".pdf")
LINK_NA_LISTAGEM = re.compile(rb'href="([^"?#:/][^"?#:]*)"', re.IGNORECASE)
ANO_NA_LISTAGEM = re.compile(r"\d{4}/")


def _links_da_pasta(cliente: Cliente, pasta: str) -> list[str]:
    """Os links relativos de uma listagem de pasta (sem o "voltar", sem endereço de fora)."""
    achados = dict.fromkeys(
        m.decode() for m in LINK_NA_LISTAGEM.findall(cliente.ler(pasta).conteudo)
    )
    return [link for link in achados if not link.startswith("..")]


def arquivos_da_pasta(cliente: Cliente, pasta: str, niveis: int) -> list[Alvo]:
    """Os arquivos de dado de uma pasta do FTP do IBGE, descendo até `niveis` subpastas."""
    alvos: list[Alvo] = []
    for link in _links_da_pasta(cliente, pasta):
        endereco = urljoin(pasta, link)
        if link.endswith("/"):
            if niveis > 0:
                alvos += arquivos_da_pasta(cliente, endereco, niveis - 1)
        elif link.lower().endswith(EXTENSOES_DO_IBGE):
            alvos.append(Alvo(endereco))
    return alvos


def descobrir_precos_do_ibge(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """INPC e IPCA desde 1978: séries históricas e números-índices."""
    alvos: list[Alvo] = []
    for pasta, niveis in PASTAS_DE_PRECOS_DO_IBGE:
        achados = arquivos_da_pasta(cliente, pasta, niveis)
        if not achados:
            raise ErroDeDescoberta(f"nenhum arquivo de dado em {pasta}")
        alvos += achados
    return alvos


def descobrir_contas_nacionais_do_ibge(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """As Contas Nacionais por edição (2005 a 2023): as pastas de ano, sem notas nem seminários."""
    anos = [
        a
        for a in _links_da_pasta(cliente, CONTAS_DO_IBGE)
        if ANO_NA_LISTAGEM.fullmatch(a)
    ]
    if not anos:
        raise ErroDeDescoberta(f"nenhuma pasta de ano em {CONTAS_DO_IBGE}")
    alvos: list[Alvo] = []
    for ano in anos:
        alvos += arquivos_da_pasta(
            cliente, CONTAS_DO_IBGE + ano, NIVEIS_DAS_CONTAS_NACIONAIS
        )
    if not alvos:
        raise ErroDeDescoberta(f"nenhum arquivo de dado em {CONTAS_DO_IBGE}")
    return alvos


# ---------- Tesouro: pacotes de dívida que faltavam ----------

PORTAL_DO_TESOURO = "https://www.tesourotransparente.gov.br/ckan"
CSV = ("csv",)
CSV_E_XLSX = ("csv", "xlsx")
# id da fonte -> (pacote do CKAN, formatos): ODbL; só a dívida e o serviço da dívida (nada por pessoa)
PACOTES_DE_DIVIDA: dict[str, tuple[str, tuple[str, ...]]] = {
    "tesouro-br-divida-execucao-por-fonte": (
        "execucao-orcamentaria-e-financeira-da-divida-publica-federal-por-fonte",
        CSV,
    ),
    "tesouro-br-divida-execucao-por-nd": (
        "execucao-orcamentaria-e-financeira-da-divida-publica-federal-por-nd",
        CSV,
    ),
    "tesouro-br-divida-dotacao": (
        "dotacao-orcamentaria-e-credito-empenhado-da-divida-publica-federal-por-fonte-de-recursos",
        CSV,
    ),
    "tesouro-br-divida-emissoes-diretas": ("ds018", CSV),
    "tesouro-br-divida-emissoes-soberanas": ("ds012", ("xlsx",)),
    "tesouro-br-divida-estados-estoque": (
        "estoque-da-divida-de-estados-e-do-distrito-federal",
        CSV,
    ),
    "tesouro-br-divida-estados-servico": (
        "servico-da-divida-de-estados-e-do-distrito-federal",
        CSV,
    ),
    "tesouro-br-divida-consolidada-liquida": (
        "limites-da-lrf-para-a-uniao-divida-consolidada-liquida-da-uniao",
        CSV,
    ),
}
NAO_COLETADOS_DO_TESOURO = {
    "contratos-divida",  # PDFs de contratos, sem licença escrita no pacote
    "relatorios-da-divida-contratual-da-uniao",  # sem licença escrita no pacote
}


def _pacote_do_tesouro(pacote: str, formatos: tuple[str, ...]) -> Descobrir:
    return lambda cliente, agora: descobrir_ckan(
        cliente, PORTAL_DO_TESOURO, pacote, formatos=formatos
    )


# ---------- IPEADATA: OData sem chave ----------

RAIZ_DO_IPEADATA = "http://www.ipeadata.gov.br/api/odata4/"
METADADOS_DO_IPEADATA = RAIZ_DO_IPEADATA + "Metadados"
SERIE_DO_IPEADATA = RAIZ_DO_IPEADATA + "ValoresSerie(SERCODIGO='{codigo}')"
# SERCODIGO -> o que é (a fonte original vem dentro do arquivo, em `Metadados`)
SERIES_DO_IPEADATA = {
    "GM366_IBVSP366": "Ibovespa, fechamento diário desde 27/04/1993 (BM&FBovespa; 1995 com valores implausíveis)",
    "GM366_IBVSPV366": "Ibovespa, volatilidade diária desde 1985 (calculada pelo Ipea)",
    "BM12_TJOVER12": "Selic over, mensal desde 1974 (Bacen)",
    "BM12_ERV12": "Câmbio R$/US$ comercial venda, média mensal desde 1930 (Bacen)",
    "PRECOS12_IPCA12": "IPCA geral, índice mensal desde 12/1979 (IBGE)",
    "PRECOS12_INPC12": "INPC geral, índice mensal desde 03/1979 (IBGE)",
}


def descobrir_metadados_do_ipeadata(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [Alvo(METADADOS_DO_IPEADATA, ".json")]


def descobrir_series_do_ipeadata(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [
        Alvo(SERIE_DO_IPEADATA.format(codigo=codigo), ".json")
        for codigo in SERIES_DO_IPEADATA
    ]


def fontes() -> list[Fonte]:
    """Todas as fontes do lote, para o `FONTES` do arquivista."""
    return [
        Fonte(
            "b3-cotahist-anual",
            CARGA_UNICA,
            descobrir_cotahist_anual,
            "zip",
            pesada=True,
        ),
        Fonte(
            "bcb-relatorio-anual",
            CARGA_UNICA,
            descobrir_relatorios_anuais,
            "pdf",
            pesada=True,
        ),
        Fonte("bcb-sgs-pre-2000", CARGA_UNICA, descobrir_sgs_antigo, "json"),
        Fonte(
            "ibge-precos-ftp",
            MENSAL,
            descobrir_precos_do_ibge,
            pesada=True,
        ),
        Fonte(
            "ibge-contas-nacionais-ftp",
            MENSAL,
            descobrir_contas_nacionais_do_ibge,
            pesada=True,
        ),
        *(
            Fonte(id_, MENSAL, _pacote_do_tesouro(pacote, formatos))
            for id_, (pacote, formatos) in PACOTES_DE_DIVIDA.items()
        ),
        Fonte(
            "ipea-odata-metadados",
            MENSAL,
            descobrir_metadados_do_ipeadata,
            "json",
            pesada=True,
        ),
        Fonte("ipea-odata-series", MENSAL, descobrir_series_do_ipeadata, "json"),
    ]
