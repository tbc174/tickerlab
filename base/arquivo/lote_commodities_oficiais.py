"""Lote "commodities oficiais": preços de commodities de órgãos públicos com licença aberta (linha 396 da fila;
licenças lidas em 24/10 e 26/10/2026, ADR 0102). O arquivista guarda cada resposta como veio: ler os preços
(o DG AGRI manda "€229,29" como texto) e tratar é tarefa da extração, não daqui.

Regras (testes em `tests/test_base_arquivo_lote_commodities_oficiais.py`), uma fonte por PR:

- **DG AGRI** (portal de dados agroalimentares da Comissão Europeia, CC BY 4.0 com crédito à Comissão e
  indicação de mudanças; o que for de terceiros fica fora da licença). Um endereço por produto (`cereal`,
  `oilseeds`, `dairy` e `sugar`), id "dgagri-produto":
  - cereais, oleaginosas e laticínios viram **uma janela por ano**, do primeiro ano com dado até o ano da
    coleta: o histórico inteiro de cereais passa de 60 MB e estoura o tempo do pedido, e uma janela fechada
    muda pouco;
  - o portal só devolve a semana que cabe **inteira** na janela: a que atravessa a virada (29/12 a 04/01)
    sumiria de todas. Por isso a janela de cada ano vai até 10/01 do ano seguinte (a semana de virada fica
    inteira na do ano que fecha, e a primeira semana do ano novo repete na janela dele);
  - a janela do ano que já fechou, baixada depois de 31/01 do ano seguinte, vale para sempre (`guardado_vale`,
    pela data da última coleta "ok": a que foi baixada antes é relida uma vez, para pegar a revisão tardia de
    um país); o ano corrente é lido toda vez e o SHA-256 decide se há algo novo. O `Alvo.versao` não serve
    aqui: o arquivista só grava os cabeçalhos HTTP como versão;
  - o portal responde **404 para o ano em que o produto ainda não existe**: é `SemArquivo`, nunca falha;
  - o açúcar ignora as datas e devolve sempre o retrato inteiro (170 KB): um endereço só;
  - **sem filtro de país**: a licença é da Comissão para todos os Estados-membros;
  - a carne (`meat`) dá 404 e `beef` ainda não foi pedido (nota no fim da fila), então fica fora.
- **Bank of Canada, índice de preços de commodities (BCPI)** pela API Valet, sem chave. Termos lidos de novo em
  05/11/2026: uso, cópia e distribuição livres citando o Banco como fonte e indicando as mudanças; quem
  vende o conteúdo avisa o comprador de que ele é grátis no site; é **proibido burlar o limite de pedidos da
  Valet**. Uma fonte por grupo de séries (`boc-bcpi-semanal`, `-mensal`, `-anual` e `-pesos`), cada uma com
  dois endereços: as observações do grupo (de 31 KB a 1,5 MB) e a descrição das séries (nome, unidade). São
  8 pedidos por rodada, com pausa de 2 s. O mensal traz o total (`M.BCPI`) e os subíndices de energia
  (`M.ENER`), metais (`M.MTLS`) e não energia (`M.BCNE`); o semanal traz `W.BCPI`.
- **Eurostat**, dois conjuntos da família `eurostat` (CC BY 4.0, só os países da UE: a lista é a de
  `lote_organismos.FILTRO_DE_PAIS_DO_EUROSTAT`, um lugar só): `eurostat-precos-agricolas` (`apri_ap_crpouta`,
  preços de produtos agrícolas, 193 KB) e `eurostat-preco-do-gas` (`nrg_pc_202`, gás para consumidores
  domésticos, 262 KB). Um pedido cada, mensal (os dois saem por ano ou semestre).
- **SSB** (Statistics Norway, CC BY 4.0 citando o SSB, com o link da licença e a indicação de mudanças; lido em
  06/11/2026): a tabela 03024, exportação semanal de salmão de cativeiro (peso e preço por quilo, fresco e
  congelado, desde 2000). Um pedido GET à API nova (`pxwebapi/v2`), que sem `valueCodes` devolve só a última
  semana; com todos os valores de cada dimensão vêm as 1.400 semanas em 80 KB. Fonte `ssb-salmao-semanal`.
- **Weekly Oil Bulletin** (DG ENER, família `dgener`; reprodução autorizada citando a fonte, no aviso legal da
  Comissão e na nota dentro das planilhas; lido em 06/11/2026): as quatro planilhas da página do boletim (preços
  semanais com e sem imposto, histórico de 4,5 MB e impostos), descobertas pelos links da página porque o
  endereço do preço semanal muda toda semana. Fonte `dgener-oil-bulletin`.
"""

import re
from datetime import UTC, date, datetime

import sqlalchemy as sa

from base.arquivo.coleta import Alvo, Cliente, Descobrir, Fonte
from base.arquivo.lote_organismos import EUROSTAT, FILTRO_DE_PAIS_DO_EUROSTAT
from base.arquivo.obter import arquivo_que_pode_faltar

PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS = (
    2.0  # portal público da Comissão, janelas de até 10 MB (ADR 0082)
)

# ---- DG AGRI (Agri-food data portal; © União Europeia, CC BY 4.0) --------------------------------
DG_AGRI = "https://ec.europa.eu/agrifood/api"
# primeiro ano com dado de cada produto (conferido ao vivo em 05/11/2026: antes dele o portal dá 404)
PRIMEIRO_ANO_DO_DG_AGRI = {"cereal": 2015, "oilseeds": 2021, "dairy": 1991}
PRODUTOS_SEM_JANELA_DO_DG_AGRI = ("sugar",)  # a API ignora `beginDate` e `endDate`
# a semana mais longa da virada termina em 6/1; 10/1 dá folga (conferido ao vivo em 05/11/2026)
FIM_DA_JANELA_NO_ANO_SEGUINTE = "10/01"
# depois deste dia a janela do ano que fechou já tem as últimas semanas e as correções de janeiro
PRIMEIRO_DIA_DA_JANELA_FECHADA = (2, 1)
_ANO_DA_JANELA = re.compile(r"beginDate=01/01/(\d{4})&")


def endereco_do_dg_agri(produto: str, ano: int | None = None) -> str:
    """Os preços de um produto no ano (`dd/mm/aaaa`, o formato que o portal pede); sem ano, o retrato inteiro."""
    url = f"{DG_AGRI}/{produto}/prices"
    if ano is None:
        return url
    return (
        f"{url}?beginDate=01/01/{ano}&endDate={FIM_DA_JANELA_NO_ANO_SEGUINTE}/{ano + 1}"
    )


def janelas_anuais_do_dg_agri(produto: str, agora: datetime) -> list[Alvo]:
    """Uma janela por ano, do primeiro com dado até o corrente; o 404 de ano sem dado não é falha."""
    anos = range(PRIMEIRO_ANO_DO_DG_AGRI[produto], agora.year + 1)
    return [
        Alvo(url, ".json", arquivo_que_pode_faltar(url))
        for url in (endereco_do_dg_agri(produto, ano) for ano in anos)
    ]


def janela_fechada_ja_guardada(anterior: sa.Row) -> bool:
    """A última coleta "ok" da janela foi depois de fechado o ano e de janeiro? Então não muda mais."""
    ano = _ANO_DA_JANELA.search(anterior.url)
    if ano is None:  # o açúcar não tem janela: lido toda vez
        return False
    baixado = anterior.baixado_em
    if baixado.tzinfo is None:  # o SQLite dos testes devolve sem fuso
        baixado = baixado.replace(tzinfo=UTC)
    mes, dia = PRIMEIRO_DIA_DA_JANELA_FECHADA
    return baixado.date() >= date(int(ano.group(1)) + 1, mes, dia)


def descobrir_dg_agri(produto: str) -> Descobrir:
    """Janelas anuais (cereais, oleaginosas, laticínios) ou o retrato único (açúcar)."""

    def _descobrir(_cliente: Cliente, agora: datetime) -> list[Alvo]:
        if produto in PRODUTOS_SEM_JANELA_DO_DG_AGRI:
            return [Alvo(endereco_do_dg_agri(produto), ".json")]
        return janelas_anuais_do_dg_agri(produto, agora)

    return _descobrir


def _fonte_do_dg_agri(produto: str) -> Fonte:
    return Fonte(
        f"dgagri-{produto}",
        "semanal",  # o portal publica toda semana (açúcar, por mês); o SHA-256 decide o que é novo
        descobrir_dg_agri(produto),
        "json",
        guardado_vale=janela_fechada_ja_guardada,
        pausa_minima=PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS,
    )


# ---- Bank of Canada, BCPI (API Valet; termos de uso do Banco) -------------------------------------
VALET = "https://www.bankofcanada.ca/valet"
# id da fonte -> (grupo da Valet, quando roda); a Valet limita os pedidos, então são poucos e com pausa
GRUPOS_DO_BCPI = {
    "boc-bcpi-semanal": ("BCPI_WEEKLY", "semanal"),
    "boc-bcpi-mensal": ("BCPI_MONTHLY", "mensal"),
    "boc-bcpi-anual": ("BCPI_ANNUAL", "mensal"),
    "boc-bcpi-pesos": ("BCPI_WEIGHTS", "mensal"),
}


def alvos_do_bcpi(grupo: str) -> list[Alvo]:
    """As observações do grupo e a descrição das séries (nome e unidade de cada uma)."""
    return [
        Alvo(f"{VALET}/observations/group/{grupo}/json", ".json"),
        Alvo(f"{VALET}/groups/{grupo}/json", ".json"),
    ]


def _fonte_do_bcpi(id_: str) -> Fonte:
    grupo, quando = GRUPOS_DO_BCPI[id_]
    return Fonte(
        id_,
        quando,
        lambda _cliente, _agora: alvos_do_bcpi(grupo),
        "json",
        pausa_minima=PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS,
    )


# ---- Eurostat: preços agrícolas e de energia (família `eurostat`, só a UE) -------------------------
CONJUNTOS_DO_EUROSTAT = {
    "eurostat-precos-agricolas": "apri_ap_crpouta",
    "eurostat-preco-do-gas": "nrg_pc_202",
}


def endereco_do_eurostat(conjunto: str) -> str:
    """O conjunto só com os países da UE que a licença cobre (o mesmo filtro das outras séries do Eurostat)."""
    return f"{EUROSTAT}/{conjunto}?{FILTRO_DE_PAIS_DO_EUROSTAT}&lang=EN"


def _fonte_do_eurostat(id_: str) -> Fonte:
    url = endereco_do_eurostat(CONJUNTOS_DO_EUROSTAT[id_])
    return Fonte(
        id_,
        "mensal",  # os dois conjuntos saem por ano ou semestre; o SHA-256 decide o que é novo
        lambda _cliente, _agora: [Alvo(url, ".json")],
        "json",
        pausa_minima=PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS,
    )


# ---- SSB: exportação semanal de salmão (tabela 03024; CC BY 4.0) -----------------------------------
SSB_SALMAO = (
    "https://data.ssb.no/api/pxwebapi/v2/tables/03024/data?lang=en&outputFormat=json-stat2"
    "&valueCodes%5BVareGrupper2%5D=*&valueCodes%5BContentsCode%5D=*&valueCodes%5BTid%5D=*"
)


def _fonte_do_ssb() -> Fonte:
    return Fonte(
        "ssb-salmao-semanal",
        "semanal",  # o SSB publica toda semana; o SHA-256 decide o que é novo
        lambda _cliente, _agora: [Alvo(SSB_SALMAO, ".json")],
        "json",
        pausa_minima=PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS,
    )


# ---- Weekly Oil Bulletin (DG ENER; família `dgener`; reprodução autorizada citando a fonte) ---------
PAGINA_DO_WOB = "https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en"
SITE_DA_COMISSAO_DE_ENERGIA = "https://energy.ec.europa.eu"
# só as planilhas (preços semanais com e sem imposto, histórico e impostos); PDFs de mapa e de notas ficam fora
PLANILHA_DO_WOB = re.compile(
    rb'href="(/document/download/[0-9a-f-]+_en)\?filename=[^"]*\.xlsx"', re.IGNORECASE
)


def descobrir_wob(cliente: Cliente, _agora: datetime) -> list[Alvo]:
    """As planilhas que a página do boletim publica hoje, sem repetir.

    O endereço do preço semanal muda toda semana (nome com a data), e o do histórico "adivinhado" redireciona
    para a home: só valem os links da página. Sem planilha na página, nenhum alvo (nada é inventado)."""
    pagina = cliente.ler(PAGINA_DO_WOB).conteudo
    caminhos = dict.fromkeys(m.decode("ascii") for m in PLANILHA_DO_WOB.findall(pagina))
    return [
        Alvo(f"{SITE_DA_COMISSAO_DE_ENERGIA}{caminho}", ".xlsx") for caminho in caminhos
    ]


def _fonte_do_wob() -> Fonte:
    return Fonte(
        "dgener-oil-bulletin",
        "semanal",  # o boletim sai toda semana; o SHA-256 decide o que é novo
        descobrir_wob,
        "zip",  # XLSX é um zip
        pausa_minima=PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS,
    )


# avisos legais lidos: o vigia avisa quando o texto muda (Comissão em 24/10/2026, Bank of Canada em 05/11/2026)
TERMOS_DOS_ORGAOS = {
    "termos-dgagri": "https://commission.europa.eu/legal-notice_en",
    "termos-boc": "https://www.bankofcanada.ca/terms/",
    "termos-ssb": "https://www.ssb.no/en/diverse/lisens",
    # a Comissão publica o boletim sob o mesmo aviso legal do DG AGRI; a família é outra (DG ENER)
    "termos-dgener": "https://commission.europa.eu/legal-notice_en",
}


def termos() -> dict[str, str]:
    """Os endereços de termos de uso do lote, para o `TERMOS` do arquivista."""
    return dict(TERMOS_DOS_ORGAOS)


def fontes() -> list[Fonte]:
    """Todas as fontes do lote, para o `FONTES` do arquivista."""
    produtos = (*PRIMEIRO_ANO_DO_DG_AGRI, *PRODUTOS_SEM_JANELA_DO_DG_AGRI)
    return [
        *(_fonte_do_dg_agri(produto) for produto in produtos),
        *(_fonte_do_bcpi(id_) for id_ in GRUPOS_DO_BCPI),
        *(_fonte_do_eurostat(id_) for id_ in CONJUNTOS_DO_EUROSTAT),
        _fonte_do_ssb(),
        _fonte_do_wob(),
    ]
