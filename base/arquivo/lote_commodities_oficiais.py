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
  - o ano fechado leva `versao` (ano mais ano da leitura): é lido uma vez por ano, para pegar a revisão
    tardia de um país, e não 10 MB repetidos toda semana; o ano corrente é lido toda vez e o SHA-256
    decide se há algo novo;
  - o portal responde **404 para o ano em que o produto ainda não existe**: é `SemArquivo`, nunca falha;
  - o açúcar ignora as datas e devolve sempre o retrato inteiro (170 KB): um endereço só;
  - **sem filtro de país**: a licença é da Comissão para todos os Estados-membros;
  - a carne (`meat`) dá 404 e `beef` ainda não foi pedido (nota no fim da fila), então fica fora.
"""

from datetime import datetime

from base.arquivo.coleta import Alvo, Cliente, Descobrir, Fonte
from base.arquivo.obter import arquivo_que_pode_faltar

PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS = (
    2.0  # portal público da Comissão, janelas de até 10 MB (ADR 0082)
)

# ---- DG AGRI (Agri-food data portal; © União Europeia, CC BY 4.0) --------------------------------
DG_AGRI = "https://ec.europa.eu/agrifood/api"
# primeiro ano com dado de cada produto (conferido ao vivo em 05/11/2026: antes dele o portal dá 404)
PRIMEIRO_ANO_DO_DG_AGRI = {"cereal": 2015, "oilseeds": 2021, "dairy": 1991}
PRODUTOS_SEM_JANELA_DO_DG_AGRI = ("sugar",)  # a API ignora `beginDate` e `endDate`


def endereco_do_dg_agri(produto: str, ano: int | None = None) -> str:
    """Os preços de um produto no ano (`dd/mm/aaaa`, o formato que o portal pede); sem ano, o retrato inteiro."""
    url = f"{DG_AGRI}/{produto}/prices"
    if ano is None:
        return url
    return f"{url}?beginDate=01/01/{ano}&endDate=31/12/{ano}"


def janelas_anuais_do_dg_agri(produto: str, agora: datetime) -> list[Alvo]:
    """Uma janela por ano, do primeiro com dado até o corrente; o ano que já fechou é lido uma vez por ano."""
    alvos = []
    for ano in range(PRIMEIRO_ANO_DO_DG_AGRI[produto], agora.year + 1):
        url = endereco_do_dg_agri(produto, ano)
        fechado = ano < agora.year
        alvos.append(
            Alvo(
                url,
                ".json",
                arquivo_que_pode_faltar(url),
                versao=f"{ano}-lido-em-{agora.year}" if fechado else None,
            )
        )
    return alvos


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
        pausa_minima=PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS,
    )


# aviso legal da Comissão (reuso CC BY 4.0, lido em 24/10/2026): o vigia avisa quando o texto muda
TERMOS_DOS_ORGAOS = {"termos-dgagri": "https://commission.europa.eu/legal-notice_en"}


def termos() -> dict[str, str]:
    """Os endereços de termos de uso do lote, para o `TERMOS` do arquivista."""
    return dict(TERMOS_DOS_ORGAOS)


def fontes() -> list[Fonte]:
    """Todas as fontes do lote, para o `FONTES` do arquivista."""
    produtos = (*PRIMEIRO_ANO_DO_DG_AGRI, *PRODUTOS_SEM_JANELA_DO_DG_AGRI)
    return [_fonte_do_dg_agri(produto) for produto in produtos]
