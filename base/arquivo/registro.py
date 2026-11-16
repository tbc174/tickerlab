"""Registro de fontes (B-01 do backlog da plataforma modular): uma linha legível por fonte do
arquivista, com licença, marca, ritmo e a data em que alguém leu os termos.

Tudo sai de `base/arquivo/fontes.py` (a lista de fontes) e de `src/banco/coletas.py` (licença e
marca de cada família): nada é digitado duas vezes. Só `TERMOS_LIDOS_EM` é dado novo, porque a data
da leitura dos termos só existia em comentário. Fonte sem data aparece como "não registrada", sem
inventar. Autenticação, custo e SLA por fonte ainda não estão em nenhum lugar estruturado; ficam fora
até alguém registrá-los (não são deduzidos do código).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from base.arquivo.fontes import FONTES
from base.arquivo.orgaos import NAO_SAO_FONTE, ORGAO_DA_FAMILIA
from base.vitrine import licenca_do_site
from src.banco.coletas import (
    USOS_SEM_COBRANCA,
    licenca_da_fonte,
    marca_da_fonte,
    marca_mais_restrita,
    revenda_da_fonte,
)

# família da fonte (o começo do id) → dia em que os termos foram lidos (licencas-por-fonte.md e
# comentários de `LICENCAS`); família que não está aqui ainda não tem a data anotada
TERMOS_LIDOS_EM: dict[str, date] = {
    "cvm": date(2026, 10, 12),
    "susep": date(2026, 10, 15),
    "wayback": date(2026, 10, 16),
    "tce": date(2026, 10, 16),
    "inmet": date(2026, 10, 18),
    "ibge": date(2026, 10, 18),
    "b3": date(2026, 10, 18),
    "conab": date(2026, 10, 18),
    "usda": date(2026, 10, 18),
    "faostat": date(2026, 10, 18),
    "ico": date(2026, 10, 18),
    "cecafe": date(2026, 10, 18),
    "fnc": date(2026, 10, 18),
    "contrapartes": date(2026, 10, 18),
    # lote organismos: rodadas 1 e 4 da pesquisa de dados escondidos
    "bce": date(2026, 10, 22),
    "ocde": date(2026, 10, 22),
    "eurostat": date(2026, 10, 22),
    "worldbank": date(2026, 10, 22),
    "bis": date(
        2026, 11, 3
    ),  # relido em 03/11 (linha 639): data.bis.org/help/legal e robots.txt
    "nasa": date(2026, 10, 22),
    "dgagri": date(
        2026, 10, 24
    ),  # aviso legal da Comissão, lido na rodada de 24/10 (linha 396)
    "dgener": date(
        2026, 11, 6
    ),  # aviso na planilha: reprodução autorizada citando a fonte (linha 396)
    "ssb": date(2026, 11, 6),  # CC BY 4.0, página de licença lida na hora (linha 396)
    "boc": date(2026, 11, 5),  # termos do Banco relidos na hora (linha 396)
    # bancos centrais nórdicos (linha 511; termos lidos na rodada recorrente de 29/10/2026)
    "riksbank": date(2026, 10, 29),
    "norges": date(2026, 10, 29),
    "dst": date(2026, 10, 29),
    "scb": date(2026, 10, 29),
    "statfi": date(2026, 10, 29),
    "statice": date(2026, 10, 29),
    "noaa": date(2026, 10, 22),
    # lote EUA (rodada 1 da pesquisa de dados escondidos)
    "treasury": date(2026, 10, 22),
    "fed": date(2026, 10, 22),
    "bls": date(2026, 10, 22),
    "eia": date(2026, 10, 22),
    "ofr": date(2026, 10, 22),
    "nyfed": date(2026, 10, 22),
    "tic": date(2026, 10, 22),
    "census": date(2026, 10, 22),
    # CHIRPS v3 `rnl` pela cópia Zarr do Hugging Face (pesquisa de 28/10/2026, partes 4 a 6)
    "chirps3": date(2026, 10, 28),
}
# releituras e primeiras leituras da auditoria N0 (21/10/2026; `auditoria-licitude-da-coleta-2026-10-21.md`);
# vale o dia mais novo. Família que a auditoria não conseguiu abrir ou não releu fica com a data antiga
TERMOS_LIDOS_EM |= dict.fromkeys(
    (
        "cvm",
        "sec",
        "bcb",
        "chirps",
        "mapbiomas",
        "bm",
        "fmi",
        "tesouro",
        "iex",
        "yahoo",
        "gdelt",
        "kraken",
        "gleif",
        "ccee",
        "antt",
        "ons",
        "cgu",
        "pgfn",
        "faostat",
        "ico",
        "inmet",
        "fnc",
        "b3",
        "conab",
    ),
    date(2026, 10, 21),
)
# rodada 1 da pesquisa de dados escondidos (licencas-por-fonte.md): BCB e Tesouro Transparente
# relidos em 22/10/2026, depois da auditoria; vale o dia mais novo
TERMOS_LIDOS_EM |= dict.fromkeys(("bcb", "tesouro"), date(2026, 10, 22))
# fontes pouco visíveis (ADR 0124): rodapés do gov.br da Sudeco e da Sudam lidos em 04/11/2026; a
# família "divida" fica sem data porque os termos dos sites dos PDFs não foram lidos um a um
TERMOS_LIDOS_EM |= dict.fromkeys(("sudeco", "sudam"), date(2026, 11, 4))
# lote setoriais Brasil (licencas-por-fonte.md): as licenças lidas na rodada 3 (ANS, ANAC), na
# rodada 1 (EPE, INEP, Senatran, INPI, ANEEL e Comex Stat); Anatel e ANP seguem o balanço prévio de
# 14/10/2026 (licença declarada no conjunto do dados.gov.br)
TERMOS_LIDOS_EM |= dict.fromkeys(
    ("epe", "inep", "senatran", "inpi", "aneel", "ans", "anac", "comexstat"),
    date(2026, 10, 22),
)
TERMOS_LIDOS_EM |= dict.fromkeys(("anatel", "anp"), date(2026, 10, 14))
# Ficha Clara, licenças e registros: a licença declarada no conjunto do dados.gov.br (CC BY), como a
# da Anatel; robots.txt e termos dos portais ainda não lidos (`COLETA_E_GUARDA`: não lida)
TERMOS_LIDOS_EM |= dict.fromkeys(("mapa", "anm", "ancine"), date(2026, 10, 29))
# linha 860: Anvisa lida de novo em 12/11/2026 (ficha CC Attribution no dados.gov.br, sem robots.txt, página de
# dados abertos do gov.br: "livremente usá-los, reutilizá-los e redistribuí-los", no máximo creditar a autoria)
TERMOS_LIDOS_EM["anvisa"] = date(2026, 11, 12)
# Ficha Clara, incentivos: a licença dita no portal do MME ("Outra (Aberta)", sem nome)
TERMOS_LIDOS_EM["mme"] = date(2026, 10, 29)
# linhas 658 e 688: robots.txt e licença dos CKAN de GO (CC BY), MS (CC BY no conjunto; uso a confirmar) e
# SP capital (CC0) lidos em 05/11/2026; GO e MS: Disallow /api/ e Crawl-Delay 10; SP: Disallow /
TERMOS_LIDOS_EM |= dict.fromkeys(("goias", "msestado", "spcapital"), date(2026, 11, 5))
# linha 578: benefícios fiscais da SEFAZ-PE; licença CC BY lida em 03/11/2026, robots.txt (Disallow /api/,
# Crawl-Delay 10) em 05/11/2026
TERMOS_LIDOS_EM["sefazpe"] = date(2026, 11, 5)
# linha 755: dívida ativa da Sefa-PR; o portal não tem robots.txt (404) nem termos de uso da lista, lido em 06/11/2026
TERMOS_LIDOS_EM["sefapr"] = date(2026, 11, 6)
TERMOS_LIDOS_EM["esdados"] = date(2026, 11, 6)  # CC BY no CKAN do ES (linha 755)
# linha 755: dívida ativa da SEF-MG; sem robots.txt (404) nem termos de uso da lista, só a base legal (CTN 198 §3º II), lido em 06/11/2026
TERMOS_LIDOS_EM["sefmg"] = date(2026, 11, 6)
# lote licitações e contratos (licencas-por-fonte.md, rodada 4, lido em 22/10/2026)
TERMOS_LIDOS_EM |= dict.fromkeys(
    ("seges", "comprasgov", "transferegov", "pncp", "tcu", "govmg", "govsc"),
    date(2026, 10, 22),
)
# lote Brasil, segunda camada (licencas-por-fonte.md): Portal da Transparência, BNDES e INSS lidos
# na rodada 3 da pesquisa (licença no CKAN/no portal)
TERMOS_LIDOS_EM |= dict.fromkeys(("transparencia", "bndes", "inss"), date(2026, 10, 22))
# lote cadastros globais (licencas-por-fonte.md, rodada 4): Wikidata, OFAC, UE e OFSI; o GLEIF e a SEC
# já têm a data da auditoria de 21/10/2026
TERMOS_LIDOS_EM |= dict.fromkeys(
    ("wikidata", "ofac", "eufsf", "ofsi"), date(2026, 10, 22)
)

# lote atenção e texto (licencas-por-fonte.md, rodada 4): Wikimedia, Querido Diário, Crossref, OpenAlex e
# as três agências; o GDELT já tem a data da auditoria de 21/10/2026
TERMOS_LIDOS_EM |= dict.fromkeys(
    ("wiki", "querido", "crossref", "openalex", "ebc", "senado", "camara"),
    date(2026, 10, 22),
)

# lote clima e fogo (licencas-por-fonte.md, rodada 4): termos lidos em 23/10/2026; o INMET, o MapBiomas,
# o NOAA e o ONS já têm data anterior
TERMOS_LIDOS_EM |= dict.fromkeys(
    (
        "inpe",
        "firms",
        "terrabrasilis",
        "ecmwf",
        "climatetrace",
        "edgar",
        "carbonmonitor",
    ),
    date(2026, 10, 23),
)

# lote patentes e marcas (licencas-por-fonte.md, rodada 4): EPO e WIPO lidos em 22/10/2026; o INPI já
# tem a data da rodada 1
TERMOS_LIDOS_EM |= dict.fromkeys(("epo", "wipo"), date(2026, 10, 22))
# lote Europa e RBA (linha 512): licenças lidas na fonte primária em 29/10/2026 (pesquisa recorrente, tema 2);
# o SNB só ganha a marca não comercial (aviso do site), sem coleta
TERMOS_LIDOS_EM |= dict.fromkeys(
    ("statat", "statbel", "cbs", "cso", "ines", "istat", "rba", "snb"),
    date(2026, 10, 29),
)
# lote acervos históricos (rodada 4, linha 292): IPEADATA sem termos publicados, lido em 22/10/2026
TERMOS_LIDOS_EM |= dict.fromkeys(("ipea",), date(2026, 10, 22))
# base de CNPJ (família "rfb", fonte `rfb-cnpj`): ficha do conjunto lida em 20/10/2026 e rodapé em
# 21/10/2026 na auditoria N0; vale a leitura completa. O portão olha a família (o id até o 1º hífen)
TERMOS_LIDOS_EM["rfb"] = date(2026, 10, 21)

# parêntese que cita decisão interna ("(ADRs 0019 e 0073)"): fica fora do site aberto
_DECISAO_INTERNA = re.compile(r"\s*\([^)]*\bADRs?\b[^)]*\)")


def _licenca_publica(licenca: str) -> str:
    return _DECISAO_INTERNA.sub("", licenca_do_site(licenca))


@dataclass(frozen=True)
class RegistroDeFonte:
    id: str
    familia: str
    licenca: str
    marca: str  # "vendavel", "uso_interno", "nao_comercial" ou "a_confirmar"
    revenda: str  # a frase da marca, em português
    ritmo: str  # o grupo em que o arquivista a coleta: diaria, semanal, mensal ou carga-unica
    tipo: str
    pesada: bool
    pausa_entre_pedidos_s: float
    termos_vigiados: bool  # o arquivista avisa quando o texto dos termos muda
    termos_lidos_em: date | None


def registro_de_fontes() -> list[RegistroDeFonte]:
    """Uma linha por fonte de `FONTES`, na mesma ordem."""
    return [
        RegistroDeFonte(
            id=f.id,
            familia=f.id.split("-", 1)[0],
            licenca=licenca_da_fonte(f.id),
            marca=marca_da_fonte(f.id).value,
            revenda=revenda_da_fonte(f.id),
            ritmo=f.grupo,
            tipo=f.tipo,
            pesada=f.pesada,
            pausa_entre_pedidos_s=f.pausa_minima,
            termos_vigiados=f.vigia,
            termos_lidos_em=TERMOS_LIDOS_EM.get(f.id.split("-", 1)[0]),
        )
        for f in FONTES
    ]


def para_o_site() -> list[dict]:
    """As linhas como o site aberto mostra: tipos simples, licença sem a decisão interna."""
    return [
        {
            "id": r.id,
            "licenca": _licenca_publica(r.licenca),
            "marca": r.marca,
            "ritmo": r.ritmo,
            "termos_lidos_em": r.termos_lidos_em.isoformat()
            if r.termos_lidos_em
            else None,
        }
        for r in registro_de_fontes()
    ]


# --- a lista por família, para a página Dados (linha 592 da fila) ---

# famílias que o app ou os scripts leem sem passar pelo arquivista (preços, café, cripto); têm licença
# em `LICENCAS`, mas nenhuma coleta em `FONTES`
FONTES_DE_FORA_DO_ARQUIVISTA = (
    "yahoo",
    "iex",
    "bm",
    "cecafe",
    "fnc",
    "kraken",
    "mb",
    "btc",
    "ms",  # CNES: carga mensal por `scripts/carga_cnes.py`, fora do arquivista (linha 654)
    "estban",  # ESTBAN do BCB: carga mensal por `scripts/carga_estban.py`, fora do arquivista (linha 659)
    # linha 658: carga por `scripts/carga_go_ms_sp.py`, fora do arquivista
    "goias",
    "msestado",
    "spcapital",
)
RITMO_DE_FORA = "lida pelo app"

# família que chega a uma tela, ao relatório ou à API sem ter tabela no catálogo de contratos: o módulo
# de `src/` que a lê e uma palavra do texto dele (um teste confere que os dois existem)
FONTES_LIDAS_PELO_APP: dict[str, tuple[str, str]] = {
    "yahoo": ("src/dados.py", "Yahoo"),  # todo preço do app
    "sec": ("src/coleta_sec.py", "sec.gov"),  # busca na SEC, no Research
    "b3": ("src/carteira_b3.py", "B3"),  # carteira exportada da B3
    "ibge": ("src/ibge_sidra.py", "IBGE"),  # mapa e calendário do café (API)
    "chirps": (
        "src/commodities/cafe/indices_de_clima.py",
        "CHIRPS",
    ),  # chuva do painel do café
    "bm": ("src/commodities/painel_de_precos.py", "Pink Sheet"),  # preços de referência
    "fmi": ("src/commodities/painel_de_precos.py", "FMI"),  # preços de referência
}

# tabela do catálogo que nenhuma tela, relatório ou rota da API lê ainda (ela existe na base e na porta
# de dados, mas não chega ao usuário): não conta para o selo "em uso" da página Dados (linha 663). Quem
# ligar uma tela a ela tira o nome daqui; um teste procura o nome em `src/`, `telas/` e `web/src/`.
TABELAS_SEM_LEITOR: frozenset[str] = frozenset(
    {
        "faostat_cafe",  # FAOSTAT: café
        "processos",  # DJEN: carga e conferência no servidor, sem tela
        "processos_comunicacoes",
        "processos_partes",
        "processos_nas_notas",
        # DataJud: só uso interno (`coletas.FONTES_SO_INTERNAS`); nenhuma tela pode ler, nunca
        "processos_datajud",
        "processos_datajud_movimentos",
    }
)

Uso = Literal["em_uso", "guardada"]


def _familia(fonte: str) -> str:
    return fonte.split("-", 1)[0]


def familias_publicas() -> list[str]:
    """As famílias da lista pública: as do arquivista, na ordem de `FONTES`, e depois as de fora."""
    vistas = dict.fromkeys(_familia(f.id) for f in FONTES)
    vistas |= dict.fromkeys(FONTES_DE_FORA_DO_ARQUIVISTA)
    return [f for f in vistas if f not in NAO_SAO_FONTE]


def _fontes_da_familia(familia: str) -> list[str]:
    """Os ids das coletas da família; família de fora do arquivista vale por ela mesma."""
    ids = [f.id for f in FONTES if _familia(f.id) == familia]
    return ids or [familia]


def _licencas_do_catalogo(catalogo: dict) -> set[str]:
    return {
        t["licenca"]
        for nome, t in catalogo["tabelas"].items()
        if nome not in TABELAS_SEM_LEITOR
    }


def uso_da_familia(familia: str, catalogo: dict) -> Uso:
    """ "em_uso" se algum número do TickerLab sai da família: tabela do catálogo que alguma tela lê
    (`TABELAS_SEM_LEITOR` fica de fora) com a licença de uma coleta dela, uso citado sem cobrança (`USOS_SEM_COBRANCA`) ou módulo do app que a lê."""
    no_catalogo = _licencas_do_catalogo(catalogo)
    if any(licenca_da_fonte(f) in no_catalogo for f in _fontes_da_familia(familia)):
        return "em_uso"
    if familia in {_familia(u.fonte) for u in USOS_SEM_COBRANCA}:
        return "em_uso"
    return "em_uso" if familia in FONTES_LIDAS_PELO_APP else "guardada"


def _sem_repetir(textos: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(textos))


def familias_para_o_site(catalogo: dict) -> list[dict]:
    """Uma linha por família, como a página Dados mostra: órgão, link, uso, a marca mais restrita das
    coletas, as licenças sem a decisão interna, os ids das coletas e a leitura mais nova dos termos.

    Família sem órgão em `base/arquivo/orgaos.py` dá erro aqui (e no build), em vez de aparecer crua.
    """
    linhas = []
    for familia in familias_publicas():
        orgao = ORGAO_DA_FAMILIA[familia]
        fontes = _fontes_da_familia(familia)
        lida_pelo_app = familia in FONTES_DE_FORA_DO_ARQUIVISTA
        termos = TERMOS_LIDOS_EM.get(familia)
        linhas.append(
            {
                "familia": familia,
                "orgao": orgao.nome,
                "link": orgao.link,
                "uso": uso_da_familia(familia, catalogo),
                "marca": marca_mais_restrita(marca_da_fonte(f) for f in fontes).value,
                "licencas": _sem_repetir(
                    _licenca_publica(licenca_da_fonte(f)) for f in fontes
                ),
                "coletas": [] if lida_pelo_app else fontes,
                "ritmo": RITMO_DE_FORA if lida_pelo_app else None,
                "termos_lidos_em": termos.isoformat() if termos else None,
            }
        )
    return linhas
