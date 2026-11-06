"""Os dados do mapa do café, em tipos simples.

Por município: produção e área da PAM (do tipo pedido: arábica, conilon ou total), a área de café do
MapBiomas, a região produtora e a anomalia de chuva da região no mês. Tudo sai em `dict`, `list`,
`str`, `int`, `float` e `None` (`DadosDoMapa.em_dicionario`), pronto para a tela de hoje e para a
rota da API de amanhã.

A malha vai simplificada (`simplificar_malha`): só os municípios com café e os contornos afinados
pelo algoritmo de Douglas–Peucker até caber em `LIMITE_DA_MALHA_BYTES` (risco 6 do plano do café: a
malha municipal inteira do IBGE tem dezenas de MB e travaria o navegador).
"""

import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date

import pandas as pd

from base.commodities.clima_regiao import FONTE_CHIRPS
from src.commodities.cafe.regioes import REGIOES, Regiao

TIPOS = ("arabica", "conilon", "total")
LIMITE_DA_MALHA_BYTES = 2 * 1024 * 1024
CASAS_DAS_COORDENADAS = 4  # ~11 m: de sobra para um mapa de municípios
TOLERANCIA_INICIAL_GRAUS = 0.001  # ~110 m
FATOR_DA_TOLERANCIA = 2.0
TOLERANCIA_MAXIMA_GRAUS = 1.0  # além disso o contorno virou um borrão: melhor falhar
PONTOS_MINIMOS_DO_ANEL = 4  # triângulo fechado (o primeiro ponto repetido no fim)
PROPRIEDADE_DO_CODIGO = "codarea"  # como a malha do IBGE chama o código do município
Ponto = list[float]
Anel = list[Ponto]


@dataclass(frozen=True)
class MunicipioNoMapa:
    codigo: str
    nome: str
    uf: str
    regiao: str | None  # id em `src/commodities/cafe/regioes.py`; None fora das regiões
    producao_t: float | None
    area_pam_ha: float | None
    area_mapbiomas_ha: float | None
    anomalia_de_chuva_mm: float | None  # da região, no mês dos dados de clima


@dataclass(frozen=True)
class DadosDoMapa:
    ano: int
    tipo: str
    competencia: str | None  # mês do clima (AAAA-MM); None quando não há clima
    municipios: tuple[MunicipioNoMapa, ...]

    def em_dicionario(self) -> dict[str, object]:
        return {
            "ano": self.ano,
            "tipo": self.tipo,
            "competencia": self.competencia,
            "municipios": [asdict(m) for m in self.municipios],
        }


def _numero(valor: object) -> float | None:
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return None
    return float(valor)  # type: ignore[arg-type]


def _anomalia_por_regiao(
    clima: pd.DataFrame, competencia: date | None, fonte: str
) -> tuple[str | None, dict[str, float | None]]:
    """A anomalia de chuva de cada região no mês pedido (ou no último mês com dado da fonte)."""
    if clima.empty:
        return None, {}
    da_fonte = clima[(clima["fonte"] == fonte) & clima["chuva_anomalia_mm"].notna()]
    if da_fonte.empty:
        return None, {}
    mes = pd.Timestamp(competencia) if competencia else da_fonte["competencia"].max()
    do_mes = da_fonte[da_fonte["competencia"] == mes]
    anomalias = {
        str(regiao): _numero(valor)
        for regiao, valor in zip(
            do_mes["regiao"], do_mes["chuva_anomalia_mm"], strict=True
        )
    }
    return mes.strftime("%Y-%m"), anomalias


def _ano_mais_recente(pam: pd.DataFrame, area: pd.DataFrame) -> int:
    anos = [int(t["ano"].max()) for t in (pam, area) if not t.empty]
    if not anos:
        raise ValueError("sem dados de área ou produção para o mapa")
    return max(anos)


def montar_dados_do_mapa(
    pam: pd.DataFrame,
    area: pd.DataFrame,
    clima: pd.DataFrame,
    regioes: Sequence[Regiao] = REGIOES,
    tipo: str = "total",
    ano: int | None = None,
    competencia: date | None = None,
    fonte_do_clima: str = FONTE_CHIRPS,
) -> DadosDoMapa:
    """Junta, para o `ano` (padrão: o mais recente), a PAM (`ler_pam`), o MapBiomas
    (`ler_mapbiomas`) e o clima mensal por região (`clima_regiao_cafe`) numa lista de municípios.
    Município que só uma fonte tem entra com a outra coluna vazia; nome e UF vêm da PAM ou do
    cadastro das regiões."""
    if tipo not in TIPOS:
        raise ValueError(f"tipo {tipo!r}: use um de {TIPOS}")
    ano = ano or _ano_mais_recente(pam, area)
    juntos = pam[pam["ano"] == ano].merge(
        area[area["ano"] == ano], on="codigo", how="outer"
    )
    regiao_por_codigo = {m.codigo: r.id for r in regioes for m in r.municipios}
    municipio_por_codigo = {m.codigo: m for r in regioes for m in r.municipios}
    mes, anomalias = _anomalia_por_regiao(clima, competencia, fonte_do_clima)
    municipios = []
    for linha in juntos.sort_values("codigo").itertuples(index=False):
        codigo = str(linha.codigo)
        cadastrado = municipio_por_codigo.get(codigo)
        regiao = regiao_por_codigo.get(codigo)
        nome = getattr(linha, "nome", None)
        uf = getattr(linha, "uf", None)
        municipios.append(
            MunicipioNoMapa(
                codigo=codigo,
                nome=str(nome)
                if isinstance(nome, str)
                else (cadastrado.nome if cadastrado else ""),
                uf=str(uf)
                if isinstance(uf, str)
                else (cadastrado.uf if cadastrado else ""),
                regiao=regiao,
                producao_t=_numero(getattr(linha, f"producao_{tipo}_t", None)),
                area_pam_ha=_numero(getattr(linha, f"area_{tipo}_ha", None)),
                area_mapbiomas_ha=_numero(getattr(linha, "area_mapbiomas_ha", None)),
                anomalia_de_chuva_mm=anomalias.get(regiao) if regiao else None,
            )
        )
    return DadosDoMapa(
        ano=ano, tipo=tipo, competencia=mes, municipios=tuple(municipios)
    )


# --- malha -------------------------------------------------------------------------------------------
def tamanho_em_bytes(geojson: dict) -> int:
    """O tamanho do GeoJSON como vai para o navegador (JSON compacto, UTF-8)."""
    return len(
        json.dumps(geojson, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )


def _distancia_ao_segmento(ponto: Ponto, inicio: Ponto, fim: Ponto) -> float:
    """Distância perpendicular (no plano das coordenadas) de `ponto` ao segmento `inicio`–`fim`."""
    (x, y), (x0, y0), (x1, y1) = ponto, inicio, fim
    dx, dy = x1 - x0, y1 - y0
    if dx == 0 and dy == 0:
        return math.hypot(x - x0, y - y0)
    t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x0 + t * dx), y - (y0 + t * dy))


def douglas_peucker(pontos: Anel, tolerancia: float) -> Anel:
    """Tira os pontos que ficam a menos de `tolerancia` da reta entre os vizinhos mantidos (versão
    iterativa, sem recursão, do algoritmo clássico). Os extremos ficam sempre."""
    if tolerancia <= 0 or len(pontos) < 3:
        return list(pontos)
    manter = [False] * len(pontos)
    manter[0] = manter[-1] = True
    pilha = [(0, len(pontos) - 1)]
    while pilha:
        inicio, fim = pilha.pop()
        maior, indice = 0.0, None
        for i in range(inicio + 1, fim):
            distancia = _distancia_ao_segmento(pontos[i], pontos[inicio], pontos[fim])
            if distancia > maior:
                maior, indice = distancia, i
        if indice is not None and maior > tolerancia:
            manter[indice] = True
            pilha.extend([(inicio, indice), (indice, fim)])
    return [p for p, fica in zip(pontos, manter, strict=True) if fica]


def _anel_minimo(anel: Anel) -> Anel:
    """O menor contorno que ainda lembra o município: os pontos extremos do anel (mais a oeste, ao
    norte, a leste e ao sul), na ordem em que aparecem, fechado."""
    extremos = {
        min(range(len(anel)), key=lambda i: anel[i][0]),
        max(range(len(anel)), key=lambda i: anel[i][1]),
        max(range(len(anel)), key=lambda i: anel[i][0]),
        min(range(len(anel)), key=lambda i: anel[i][1]),
    }
    pontos = [list(anel[i]) for i in sorted(extremos)]
    pontos.append(list(pontos[0]))
    return pontos


def _anel_simplificado(anel: Anel, tolerancia: float) -> Anel:
    """Coordenadas arredondadas e o contorno afinado; um anel que ficaria pequeno demais (menos de um
    triângulo fechado) vira o contorno mínimo dos seus pontos extremos, para que uma tolerância
    maior nunca devolva uma malha maior."""
    arredondado = [[round(c, CASAS_DAS_COORDENADAS) for c in ponto] for ponto in anel]
    afinado = douglas_peucker(arredondado, tolerancia)
    if afinado[0] != afinado[-1]:
        afinado.append(list(afinado[0]))
    if len(afinado) >= PONTOS_MINIMOS_DO_ANEL:
        return afinado
    return _anel_minimo(
        arredondado[:-1] if arredondado[0] == arredondado[-1] else arredondado
    )


def _geometria_simplificada(geometria: dict, tolerancia: float) -> dict:
    if geometria["type"] == "Polygon":
        aneis = [_anel_simplificado(a, tolerancia) for a in geometria["coordinates"]]
        return {"type": "Polygon", "coordinates": aneis}
    if geometria["type"] == "MultiPolygon":
        poligonos = [
            [_anel_simplificado(a, tolerancia) for a in poligono]
            for poligono in geometria["coordinates"]
        ]
        return {"type": "MultiPolygon", "coordinates": poligonos}
    raise ValueError(
        f"geometria {geometria['type']!r} na malha: esperava Polygon ou MultiPolygon"
    )


def _feicao_simplificada(feicao: dict, tolerancia: float) -> dict:
    return {
        "type": "Feature",
        "properties": {
            PROPRIEDADE_DO_CODIGO: feicao["properties"][PROPRIEDADE_DO_CODIGO]
        },
        "geometry": _geometria_simplificada(feicao["geometry"], tolerancia),
    }


def simplificar_malha(
    malha: dict, codigos: Iterable[str], limite_bytes: int = LIMITE_DA_MALHA_BYTES
) -> dict:
    """Só os municípios de `codigos` (a propriedade `codarea` da malha do IBGE), com as coordenadas
    arredondadas e, enquanto o GeoJSON passar de `limite_bytes`, os contornos afinados por
    Douglas–Peucker com tolerância que dobra a cada volta. Devolve um FeatureCollection novo (o de
    entrada não muda) e falha se nem a tolerância máxima bastar."""
    quero = set(codigos)
    feicoes = [
        f
        for f in malha["features"]
        if f["properties"].get(PROPRIEDADE_DO_CODIGO) in quero
    ]
    tolerancia = 0.0
    while True:
        simplificada = {
            "type": "FeatureCollection",
            "features": [_feicao_simplificada(f, tolerancia) for f in feicoes],
        }
        if tamanho_em_bytes(simplificada) <= limite_bytes:
            return simplificada
        tolerancia = (
            TOLERANCIA_INICIAL_GRAUS
            if tolerancia == 0
            else tolerancia * FATOR_DA_TOLERANCIA
        )
        if tolerancia > TOLERANCIA_MAXIMA_GRAUS:
            raise ValueError(
                f"a malha de {len(feicoes)} municípios não cabe em {limite_bytes} bytes nem com a "
                f"tolerância máxima de {TOLERANCIA_MAXIMA_GRAUS}°"
            )
