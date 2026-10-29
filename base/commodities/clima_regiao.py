"""Clima mensal por região cafeeira: tabela `clima_regiao_cafe` (plano do café, PR 8, tarefa 8.2).

Duas fontes, cada linha diz qual (`fonte`):

- **INMET** (`inmet`): as estações automáticas do BDMEP, um zip por ano com um CSV horário por
  estação (`portal.inmet.gov.br/uploads/dadoshistoricos/<ano>.zip`). `ler_inmet` vira o horário em
  diário por estação (chuva do dia, Tmín, Tmáx), `atribuir_regiao` liga a estação ao município pelo
  nome e UF (`src/commodities/cafe/regioes.py`) e `agregar` fecha o mês por região: chuva acumulada,
  Tmín média, dias com Tmín abaixo de `LIMIAR_DE_FRIO_C`, Tmáx média e `n_estacoes`.
- **CHIRPS** (`chirps`): chuva mensal por satélite e pluviômetros (UCSB, 0,05°, 1981 em diante),
  um GeoTIFF global por mês. `ler_chirps` tira a média dos pixels dentro de cada município (malha do
  IBGE) e `chirps_por_regiao` pondera pela área de café da PAM. Cobre a região que não tem estação
  e só dá chuva: temperatura fica vazia.

**Regras contra número falso** (riscos 3 e 4 do plano): a estação só conta no mês com pelo menos
`FRACAO_MINIMA_DE_DIAS` dos dias válidos (dia válido: `HORAS_MINIMAS_NO_DIA` horas com leitura); a
região só tem valor com `MINIMO_DE_ESTACOES` estações válidas, senão a linha fica com os valores
vazios (nunca zero) e `n_estacoes` diz quantas havia. A normal é a média de 1991–2020 da própria
tabela, por região, fonte e mês do ano, com pelo menos `ANOS_MINIMOS_NA_NORMAL` anos; sem isso,
normal e anomalia ficam vazias (as estações automáticas começam em 2000: a normal do INMET tem no
máximo 21 anos; a do CHIRPS, 30).

O dia da estação é o dia UTC (as 24 leituras de 00 a 23 UTC), não o dia civil de Brasília: para um
total mensal a diferença é de 3 horas numa ponta e noutra. Sem Streamlit; pandas e numpy só.
"""

import gzip
import io
import itertools
import unicodedata
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import NamedTuple

import numpy as np
import pandas as pd

from base.arquivo.chirps_v3 import FONTE_CHIRPS_V3_RNL, ler_arquivo
from src.commodities.cafe.regioes import REGIOES, Regiao

FONTE_INMET, FONTE_CHIRPS = "inmet", "chirps"
COLUNAS = (
    "regiao", "competencia", "fonte", "chuva_mm", "tmin_media_c", "dias_tmin_abaixo_de_2c",
    "tmax_media_c", "n_estacoes", "chuva_normal_mm", "chuva_anomalia_mm", "tmin_normal_c",
    "tmin_anomalia_c", "tmax_normal_c", "tmax_anomalia_c", "anos_na_normal", "disponivel_em",
)  # fmt: skip
COLUNAS_DIARIAS = (
    "estacao", "nome", "uf", "latitude", "longitude", "dia", "chuva_mm", "tmin_c", "tmax_c",
    "horas_validas",
)  # fmt: skip
CODIFICACAO_DO_INMET = "latin-1"
SEM_DADO_DO_INMET = -9999.0
LINHAS_DE_CABECALHO = (
    8  # região, UF, estação, código WMO, latitude, longitude, altitude, fundação
)
HORAS_MINIMAS_NO_DIA = 20  # das 24 leituras horárias
FRACAO_MINIMA_DE_DIAS = 0.8
MINIMO_DE_ESTACOES = 3
LIMIAR_DE_FRIO_C = (
    2.0  # Tmín no abrigo abaixo disso: dia frio na tabela (a geada é da 8.3)
)
INICIO_DA_NORMAL, FIM_DA_NORMAL = 1991, 2020  # a normal climatológica vigente da OMM
ANOS_MINIMOS_NA_NORMAL = 10
# "como era na data": não medido ainda (o arquivista passa a guardar as fontes com este PR); a folga é
# conservadora e deve ser conferida com as baixadas. O zip do ano corrente do INMET é regravado de
# tempos em tempos; o CHIRPS final do mês sai ao longo do mês seguinte
DIAS_ATE_PUBLICAR = {FONTE_INMET: 45, FONTE_CHIRPS: 60, FONTE_CHIRPS_V3_RNL: 60}
SEM_DADO_DO_CHIRPS = -9999.0
MAGICO_DO_GZIP = b"\x1f\x8b"
# o que cada coluna do CSV do INMET começa dizendo (sem acento, em minúsculas) → coluna diária
COLUNAS_DO_INMET = {
    "precipitacao total": "chuva_mm",
    "temperatura maxima na hora ant": "tmax_c",
    "temperatura minima na hora ant": "tmin_c",
}
CAMPOS_DO_CABECALHO = {
    "uf": "uf",
    "estacao": "nome",
    "codigo (wmo)": "estacao",
    "latitude": "latitude",
    "longitude": "longitude",
}


# --- INMET: do horário por estação ao mês por região --------------------------------------------
def simplificar_nome(texto: str) -> str:
    """Sem acento, minúsculo e com um espaço só: para casar nome de estação com município."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.replace("﻿", "").strip().lower().split())


def _numero(texto: str) -> float:
    texto = texto.strip().replace(",", ".")
    if not texto:
        return np.nan
    valor = float(texto)
    return np.nan if valor == SEM_DADO_DO_INMET else valor


def _cabecalho(linhas: list[str]) -> dict[str, str]:
    """As 8 linhas do topo do CSV ("CODIGO (WMO):;A509") nos campos da tabela diária."""
    campos = {}
    for linha in linhas[:LINHAS_DE_CABECALHO]:
        rotulo, _, valor = linha.partition(";")
        chave = simplificar_nome(rotulo).rstrip(":").split(" (")[0]
        if chave in CAMPOS_DO_CABECALHO:
            campos[CAMPOS_DO_CABECALHO[chave]] = valor.strip().rstrip(";")
        elif chave.startswith("codigo"):
            campos["estacao"] = valor.strip().rstrip(";")
    return campos


def _coluna_da_base(nome: str) -> str | None:
    simples = simplificar_nome(nome)
    return next(
        (
            coluna
            for inicio, coluna in COLUNAS_DO_INMET.items()
            if simples.startswith(inicio)
        ),
        None,
    )


def _ler_horario(linhas: list[str]) -> pd.DataFrame:
    """As leituras horárias de um CSV do INMET: `dia` (UTC), `chuva_mm`, `tmin_c`, `tmax_c`."""
    nomes = linhas[LINHAS_DE_CABECALHO].split(";")
    posicoes = {
        _coluna_da_base(n): i for i, n in enumerate(nomes) if _coluna_da_base(n)
    }
    registros = []
    for linha in linhas[LINHAS_DE_CABECALHO + 1 :]:
        campos = linha.split(";")
        if len(campos) <= max(posicoes.values()):
            continue
        # "2024/01/01" nos arquivos novos, "2000-09-22" nos antigos
        dia = campos[0].strip()[:10].replace("/", "-")
        registros.append(
            (
                dia,
                *(
                    _numero(campos[posicoes[c]])
                    for c in ("chuva_mm", "tmin_c", "tmax_c")
                ),
            )
        )
    horario = pd.DataFrame(registros, columns=["dia", "chuva_mm", "tmin_c", "tmax_c"])
    horario["dia"] = pd.to_datetime(horario["dia"], format="%Y-%m-%d")
    return horario


def _diario(horario: pd.DataFrame) -> pd.DataFrame:
    """Um dia por linha: chuva somada, Tmín mínima, Tmáx máxima e quantas horas tinham as três."""
    completo = horario.dropna(subset=["chuva_mm", "tmin_c", "tmax_c"])
    por_dia = completo.groupby("dia", sort=True)
    diario = por_dia.agg(
        chuva_mm=("chuva_mm", "sum"),
        tmin_c=("tmin_c", "min"),
        tmax_c=("tmax_c", "max"),
        horas_validas=("tmin_c", "size"),
    ).reset_index()
    return diario


def ler_estacao(conteudo: bytes) -> pd.DataFrame:
    """O diário de uma estação a partir do CSV horário do INMET (formato antigo ou novo)."""
    linhas = conteudo.decode(CODIFICACAO_DO_INMET).splitlines()
    campos = _cabecalho(linhas)
    diario = _diario(_ler_horario(linhas))
    for coluna in ("estacao", "nome", "uf"):
        diario[coluna] = campos.get(coluna, "")
    for coluna in ("latitude", "longitude"):
        diario[coluna] = _numero(campos.get(coluna, ""))
    return diario[list(COLUNAS_DIARIAS)]


def ler_inmet(zip_bytes: bytes) -> pd.DataFrame:
    """O diário de todas as estações de um zip anual do INMET (`COLUNAS_DIARIAS`)."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as arquivo:
        membros = [n for n in arquivo.namelist() if n.lower().endswith(".csv")]
        diarios = [ler_estacao(arquivo.read(nome)) for nome in sorted(membros)]
    if not diarios:
        return pd.DataFrame(columns=list(COLUNAS_DIARIAS))
    return pd.concat(diarios, ignore_index=True)


def _regiao_por_nome_e_uf(regioes: Iterable[Regiao]) -> dict[tuple[str, str], str]:
    return {
        (simplificar_nome(m.nome), m.uf): regiao.id
        for regiao in regioes
        for m in regiao.municipios
    }


def atribuir_regiao(
    diario: pd.DataFrame, regioes: Iterable[Regiao] = REGIOES
) -> pd.DataFrame:
    """O diário só das estações cujo nome e UF são de um município de região cafeeira, com `regiao`.

    O INMET não dá o código do município; a estação costuma ter o nome dele ("VARGINHA", MG).
    Estação com nome de distrito ou de fazenda fica de fora (limite conhecido).
    """
    por_nome = _regiao_por_nome_e_uf(regioes)
    chaves = zip(diario["nome"].map(simplificar_nome), diario["uf"], strict=True)
    com_regiao = diario.assign(regiao=[por_nome.get(chave) for chave in chaves])
    return com_regiao.dropna(subset=["regiao"]).reset_index(drop=True)


def _estacoes_validas_no_mes(diario: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por estação e mês, só as estações com dias válidos bastantes no mês."""
    validos = diario[diario["horas_validas"] >= HORAS_MINIMAS_NO_DIA].copy()
    validos["competencia"] = validos["dia"] + pd.offsets.MonthEnd(0)
    validos["frio"] = validos["tmin_c"] < LIMIAR_DE_FRIO_C
    mensal = (
        validos.groupby(["regiao", "competencia", "estacao"], sort=True)
        .agg(
            chuva_mm=("chuva_mm", "sum"),
            tmin_media_c=("tmin_c", "mean"),
            dias_tmin_abaixo_de_2c=("frio", "sum"),
            tmax_media_c=("tmax_c", "mean"),
            dias=("dia", "size"),
        )
        .reset_index()
    )
    dias_no_mes = mensal["competencia"].dt.day
    return mensal[mensal["dias"] >= FRACAO_MINIMA_DE_DIAS * dias_no_mes]


def _vazia() -> pd.DataFrame:
    return pd.DataFrame(columns=list(COLUNAS))


def agregar(diario: pd.DataFrame, regioes: Iterable[Regiao] = REGIOES) -> pd.DataFrame:
    """O mês por região a partir do diário por estação já com `regiao` (`atribuir_regiao`).

    Com menos de `MINIMO_DE_ESTACOES` estações válidas no mês os valores ficam vazios e
    `n_estacoes` diz quantas havia. Normal e anomalia vêm depois, de `com_normal`.
    """
    if diario.empty:
        return _vazia()
    ids = {r.id for r in regioes}
    por_estacao = _estacoes_validas_no_mes(diario[diario["regiao"].isin(ids)])
    valores = ["chuva_mm", "tmin_media_c", "dias_tmin_abaixo_de_2c", "tmax_media_c"]
    mensal = (
        por_estacao.groupby(["regiao", "competencia"], sort=True)
        .agg(**{v: (v, "mean") for v in valores}, n_estacoes=("estacao", "size"))
        .reset_index()
    )
    poucas = mensal["n_estacoes"] < MINIMO_DE_ESTACOES
    mensal.loc[poucas, valores] = np.nan
    mensal["fonte"] = FONTE_INMET
    return _completar(mensal)


def _completar(mensal: pd.DataFrame) -> pd.DataFrame:
    """Todas as colunas da tabela, na ordem, com `disponivel_em` pela fonte da linha."""
    for coluna in COLUNAS:
        if coluna not in mensal.columns:
            mensal[coluna] = np.nan
    atraso = mensal["fonte"].map(DIAS_ATE_PUBLICAR).astype(int)
    mensal["disponivel_em"] = mensal["competencia"] + pd.to_timedelta(atraso, unit="D")
    return mensal[list(COLUNAS)].reset_index(drop=True)


# --- CHIRPS: do GeoTIFF global à chuva por município e por região ---------------------------------
@dataclass(frozen=True)
class Grade:
    """A grade regular de um raster em graus: canto noroeste, passo e tamanho."""

    lon_oeste: float
    lat_norte: float
    passo: float
    colunas: int
    linhas: int

    def coluna(self, lon: float) -> int:
        return int((lon - self.lon_oeste) / self.passo)

    def linha(self, lat: float) -> int:
        return int((self.lat_norte - lat) / self.passo)

    def centro(
        self, linhas: np.ndarray, colunas: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """(lon, lat) do centro de cada pixel."""
        lon = self.lon_oeste + (colunas + 0.5) * self.passo
        lat = self.lat_norte - (linhas + 0.5) * self.passo
        return lon, lat


GRADE_CHIRPS = Grade(
    lon_oeste=-180.0, lat_norte=50.0, passo=0.05, colunas=7200, linhas=2000
)


class Mascara(NamedTuple):
    """Os índices (linha, coluna) dos pixels de um município na grade."""

    linhas: np.ndarray
    colunas: np.ndarray


def _dentro_do_anel(
    x: np.ndarray, y: np.ndarray, anel: list[list[float]]
) -> np.ndarray:
    """Par-ímpar (raio para a esquerda) de cada ponto contra um anel do polígono."""
    pontos = np.asarray(anel, dtype=float)
    dentro = np.zeros(x.shape, dtype=bool)
    with np.errstate(divide="ignore", invalid="ignore"):
        for (x1, y1), (x2, y2) in itertools.pairwise(pontos):
            cruza = (y1 > y) != (y2 > y)
            if not cruza.any():
                continue
            x_no_raio = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            dentro ^= cruza & (x < x_no_raio)
    return dentro


def _aneis(geometria: Mapping) -> list[list[list[float]]]:
    if geometria["type"] == "Polygon":
        return list(geometria["coordinates"])
    if geometria["type"] == "MultiPolygon":
        return [anel for poligono in geometria["coordinates"] for anel in poligono]
    raise ValueError(f"Geometria que não conheço: {geometria['type']}")


def mascara_do_municipio(geometria: Mapping, grade: Grade = GRADE_CHIRPS) -> Mascara:
    """Os pixels cujo centro cai no município (buracos descontados); município menor que um pixel
    fica com o pixel do centro da caixa dele."""
    aneis = _aneis(geometria)
    pontos = np.asarray([p for anel in aneis for p in anel], dtype=float)
    lon_min, lat_min = pontos.min(axis=0)
    lon_max, lat_max = pontos.max(axis=0)
    linhas = np.arange(
        max(grade.linha(lat_max), 0), min(grade.linha(lat_min), grade.linhas - 1) + 1
    )
    colunas = np.arange(
        max(grade.coluna(lon_min), 0), min(grade.coluna(lon_max), grade.colunas - 1) + 1
    )
    malha_l, malha_c = np.meshgrid(linhas, colunas, indexing="ij")
    lon, lat = grade.centro(malha_l, malha_c)
    dentro = np.zeros(lon.shape, dtype=bool)
    for anel in aneis:
        dentro ^= _dentro_do_anel(lon, lat, anel)
    if not dentro.any():
        centro_l = grade.linha((lat_min + lat_max) / 2)
        centro_c = grade.coluna((lon_min + lon_max) / 2)
        return Mascara(np.array([centro_l]), np.array([centro_c]))
    return Mascara(malha_l[dentro], malha_c[dentro])


def mascaras_da_malha(
    geojson: Mapping,
    codigos: Iterable[str] | None = None,
    grade: Grade = GRADE_CHIRPS,
    campo_do_codigo: str = "codarea",
) -> dict[str, Mascara]:
    """Uma máscara por município da malha (só os `codigos`, se dados), pelo campo `codarea` do IBGE."""
    quais = None if codigos is None else set(codigos)
    mascaras = {}
    for feicao in geojson["features"]:
        codigo = str(feicao["properties"][campo_do_codigo])
        if quais is None or codigo in quais:
            mascaras[codigo] = mascara_do_municipio(feicao["geometry"], grade)
    return mascaras


def ler_tif(conteudo: bytes) -> np.ndarray:
    """A matriz float32 de um GeoTIFF do CHIRPS (`.tif` ou `.tif.gz`); sem dado vira NaN."""
    from PIL import Image  # só aqui: o Pillow não está na imagem de produção

    if conteudo[:2] == MAGICO_DO_GZIP:
        conteudo = gzip.decompress(conteudo)
    Image.MAX_IMAGE_PIXELS = None  # o CHIRPS global tem 14,4 milhões de pixels
    matriz = np.asarray(Image.open(io.BytesIO(conteudo)), dtype=np.float32)
    matriz = matriz.copy()
    matriz[matriz == SEM_DADO_DO_CHIRPS] = np.nan
    return matriz


def ler_chirps(conteudo: bytes, mascaras: Mapping[str, Mascara]) -> pd.DataFrame:
    """A chuva do mês por município (`codigo`, `chuva_mm`): média dos pixels da máscara; município
    sem pixel com dado fica vazio."""
    matriz = ler_tif(conteudo)
    linhas = [
        (codigo, float(np.nanmean(valores)) if np.isfinite(valores).any() else np.nan)
        for codigo, mascara in mascaras.items()
        for valores in (matriz[mascara.linhas, mascara.colunas],)
    ]
    return pd.DataFrame(linhas, columns=["codigo", "chuva_mm"])


def ler_chirps_v3(conteudo: bytes, mascaras: Mapping[str, Mascara]) -> pd.DataFrame:
    """A chuva do mês por município (`codigo`, `chuva_mm`) do arquivo mensal do CHIRPS v3 `rnl`: média
    dos pixels da máscara (feita na grade do arquivo); pixel a que faltou algum dia não conta."""
    chuva = ler_arquivo(conteudo).chuva_mm
    linhas = []
    for codigo, mascara in mascaras.items():
        dentro = (mascara.linhas < chuva.shape[0]) & (mascara.colunas < chuva.shape[1])
        valores = chuva[mascara.linhas[dentro], mascara.colunas[dentro]]
        linhas.append((codigo, float(np.nanmean(valores)) if np.isfinite(valores).any() else np.nan))  # fmt: skip
    return pd.DataFrame(linhas, columns=["codigo", "chuva_mm"])


def chirps_por_regiao(
    por_municipio: pd.DataFrame,
    competencia: date,
    regioes: Iterable[Regiao] = REGIOES,
    fonte: str = FONTE_CHIRPS,
) -> pd.DataFrame:
    """A chuva do mês por região: média dos municípios ponderada pela área de café da PAM.

    Só chuva: temperaturas e `n_estacoes` ficam vazias (não há estação no satélite). Região sem
    nenhum município com dado fica vazia.
    """
    chuva = dict(zip(por_municipio["codigo"], por_municipio["chuva_mm"], strict=True))
    linhas = []
    for regiao in regioes:
        pesos = [(chuva.get(m.codigo), m.area_ha) for m in regiao.municipios]
        com_dado = [
            (c, a) for c, a in pesos if c is not None and np.isfinite(c) and a > 0
        ]
        media = (
            sum(c * a for c, a in com_dado) / sum(a for _, a in com_dado)
            if com_dado
            else np.nan
        )
        linhas.append(
            (regiao.id, pd.Timestamp(competencia) + pd.offsets.MonthEnd(0), media)
        )
    mensal = pd.DataFrame(linhas, columns=["regiao", "competencia", "chuva_mm"])
    mensal["fonte"] = fonte
    return _completar(mensal)


# --- normal 1991–2020 e anomalia ------------------------------------------------------------------
NORMAIS = {
    "chuva_mm": ("chuva_normal_mm", "chuva_anomalia_mm"),
    "tmin_media_c": ("tmin_normal_c", "tmin_anomalia_c"),
    "tmax_media_c": ("tmax_normal_c", "tmax_anomalia_c"),
}


def com_normal(mensal: pd.DataFrame) -> pd.DataFrame:
    """A normal de 1991–2020 (média por região, fonte e mês do ano) e a anomalia de cada valor.

    `anos_na_normal` é quantos anos entraram na normal da chuva; com menos de
    `ANOS_MINIMOS_NA_NORMAL` a normal e a anomalia ficam vazias (nunca zero).
    """
    if mensal.empty:
        return _vazia()
    tabela = _completar(mensal.copy())  # aceita a tabela sem as colunas da normal
    competencia = pd.to_datetime(tabela["competencia"])
    tabela["_mes"] = competencia.dt.month
    periodo = tabela[competencia.dt.year.between(INICIO_DA_NORMAL, FIM_DA_NORMAL)]
    chave = ["regiao", "fonte", "_mes"]
    normais = periodo.groupby(chave).agg(
        **{normal: (valor, "mean") for valor, (normal, _) in NORMAIS.items()},
        anos_na_normal=("chuva_mm", "count"),
    )
    tabela = tabela.drop(columns=list(normais.columns), errors="ignore").merge(
        normais, how="left", left_on=chave, right_index=True
    )
    poucos = ~(tabela["anos_na_normal"] >= ANOS_MINIMOS_NA_NORMAL)
    for valor, (normal, anomalia) in NORMAIS.items():
        tabela.loc[poucos, normal] = np.nan
        tabela[anomalia] = tabela[valor] - tabela[normal]
    tabela.loc[poucos, "anos_na_normal"] = np.nan
    return tabela.drop(columns="_mes")[list(COLUNAS)].reset_index(drop=True)
