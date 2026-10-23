"""Registro de fontes (B-01 do backlog da plataforma modular): uma linha legível por fonte do
arquivista, com licença, marca, ritmo e a data em que alguém leu os termos.

Tudo sai de `base/arquivo/fontes.py` (a lista de fontes) e de `src/banco/coletas.py` (licença e
marca de cada família): nada é digitado duas vezes. Só `TERMOS_LIDOS_EM` é dado novo, porque a data
da leitura dos termos só existia em comentário. Fonte sem data aparece como "não registrada", sem
inventar. Autenticação, custo e SLA por fonte ainda não estão em nenhum lugar estruturado; ficam fora
até alguém registrá-los (não são deduzidos do código).
"""

import re
from dataclasses import dataclass
from datetime import date

from base.arquivo.fontes import FONTES
from base.vitrine import licenca_do_site
from src.banco.coletas import licenca_da_fonte, marca_da_fonte, revenda_da_fonte

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
    "bis": date(2026, 10, 22),
    "nasa": date(2026, 10, 22),
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
# lote setoriais Brasil (licencas-por-fonte.md): as licenças lidas na rodada 3 (ANS, ANAC), na
# rodada 1 (EPE, INEP, Senatran, INPI, ANEEL e Comex Stat); Anatel e ANP seguem o balanço prévio de
# 14/10/2026 (licença declarada no conjunto do dados.gov.br)
TERMOS_LIDOS_EM |= dict.fromkeys(
    ("epe", "inep", "senatran", "inpi", "aneel", "ans", "anac", "comexstat"),
    date(2026, 10, 22),
)
TERMOS_LIDOS_EM |= dict.fromkeys(("anatel", "anp"), date(2026, 10, 14))
# lote licitações e contratos (licencas-por-fonte.md, rodada 4, lido em 22/10/2026)
TERMOS_LIDOS_EM |= dict.fromkeys(
    ("seges", "comprasgov", "transferegov", "pncp", "tcu", "govmg", "govsc"),
    date(2026, 10, 22),
)
# lote cadastros globais (licencas-por-fonte.md, rodada 4): Wikidata, OFAC, UE e OFSI; o GLEIF e a SEC
# já têm a data da auditoria de 21/10/2026
TERMOS_LIDOS_EM |= dict.fromkeys(
    ("wikidata", "ofac", "eufsf", "ofsi"), date(2026, 10, 22)
)

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
