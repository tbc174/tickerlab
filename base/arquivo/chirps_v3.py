"""CHIRPS v3.0 diário, sabor `rnl` (ERA5), pela cópia Zarr do Hugging Face: a chuva do mês na janela
das regiões de café (ponte da troca da v2, que o CHC deixa de produzir depois de dez/2026).

O Zarr é lido sem `xarray` nem `zarr`: só o `zarr.json`, as coordenadas e os pedaços (chunks) que
cruzam a janela e o mês, cada um um arquivo `c/tempo/lat/lon` com int16 em 0,1 mm e Zstandard. O que
vai para o acervo é um arquivo por mês (`montar_arquivo`) com a soma dos dias de cada pixel (em
0,1 mm, inteira, sem arredondar) e quantos dias tinham dado; `ler_arquivo` devolve os milímetros.

Atenção: o `rnl` (reanálise ERA5, desde 1981) **não** é o `sat` (IMERG, desde 1998) nem a v2:
são produtos diferentes e a série nunca se mistura (`FONTE_CHIRPS_V3_RNL`, normal própria).
A cópia é de uma conta pessoal (não oficial), com valores arredondados a 0,1 mm (até 0,05 mm de
diferença do GeoTIFF do CHC); a licença é a do CHC (domínio público e CC BY 4.0, DOI
10.15780/G2JQ0P). Notas de pesquisa de 28/10/2026 (`licencas-organismos-parte-4`).
"""

import calendar
import json
import logging
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

import numpy as np
import requests
import zstandard

from base.arquivo.coleta import Alvo, Cliente, Fonte, SemArquivo

log = logging.getLogger(__name__)

FONTE_CHIRPS_V3_RNL = "chirps-v3-rnl"
RAIZ_DO_ZARR = (
    "https://huggingface.co/datasets/aaguilar90/chirps-v3-daily-rnl/resolve/main/"
    "chirps-v3-daily-rnl.zarr"
)
ENDERECO_DO_MES = (
    RAIZ_DO_ZARR + "/precip?mes={ano}-{mes:02d}"
)  # só identifica o arquivo do mês
PRIMEIRO_ANO = 1991  # início da normal de 1991–2020 (OMM), como na v2
MESES_RECENTES = 3
HTTP_NAO_ENCONTRADO = 404
ESCALA_ESPERADA = 0.1  # o int16 do Zarr é em décimos de milímetro
SEM_DADO = -9999
CABECALHO = (
    b"CHIRPS3-RNL\n"  # abre o arquivo do mês; o JSON da grade vem na linha seguinte
)
PEDACOS_NA_MEMORIA = (
    24  # pedaços comprimidos (~1 MB) guardados entre um mês e o seguinte
)


@dataclass(frozen=True)
class Janela:
    """O retângulo em graus que o arquivo do mês guarda (as UFs com região de café)."""

    lat_norte: float
    lat_sul: float
    lon_oeste: float
    lon_leste: float


# de Rondônia (oeste) e da Bahia (norte e leste) ao sul do Paraná
JANELA_DO_CAFE = Janela(lat_norte=-7.0, lat_sul=-27.0, lon_oeste=-67.0, lon_leste=-37.0)


class Geometria(NamedTuple):
    """O que o `zarr.json` do `precip` diz: tamanho e pedaços."""

    dias: int
    linhas: int
    colunas: int
    pedaco: tuple[int, int, int]


class Grade(NamedTuple):
    """A grade do arquivo do mês, do jeito de `clima_regiao.Grade` (bordas, não centros)."""

    lon_oeste: float
    lat_norte: float
    passo: float
    colunas: int
    linhas: int


def _json(cliente: Cliente, caminho: str) -> dict:
    return json.loads(cliente.ler(f"{RAIZ_DO_ZARR}/{caminho}/zarr.json").conteudo)


def _descomprimir(conteudo: bytes, tamanho: int) -> bytes:
    return zstandard.ZstdDecompressor().decompress(conteudo, max_output_size=tamanho)


def _pedaco(cliente: Cliente, caminho: str, chave: str) -> bytes | None:
    """O arquivo de um pedaço; pedaço que não existe é todo sem dado (regra do Zarr)."""
    try:
        return cliente.ler(f"{RAIZ_DO_ZARR}/{caminho}/c/{chave}").conteudo
    except requests.HTTPError as erro:
        if (
            erro.response is not None
            and erro.response.status_code == HTTP_NAO_ENCONTRADO
        ):
            return None
        raise


def _geometria(meta: Mapping) -> Geometria:
    """Confere que o Zarr ainda é o que este leitor entende (int16 em 0,1 mm, bytes + zstd)."""
    codecs = [c["name"] for c in meta["codecs"]]
    escala = meta["attributes"]["scale_factor"]
    if (
        meta["data_type"] != "int16"
        or codecs != ["bytes", "zstd"]
        or meta["dimension_names"] != ["time", "lat", "lon"]
        or meta["fill_value"] != SEM_DADO
        or abs(escala - ESCALA_ESPERADA) > 1e-9
        or meta["attributes"].get("add_offset", 0.0) != 0.0
    ):
        raise ValueError("o Zarr do CHIRPS v3 mudou de formato; o leitor não vale mais")
    dias, linhas, colunas = meta["shape"]
    pedaco = tuple(meta["chunk_grid"]["configuration"]["chunk_shape"])
    return Geometria(dias, linhas, colunas, pedaco)  # type: ignore[arg-type]


def _eixo(cliente: Cliente, nome: str, dtype: str) -> tuple[np.ndarray, Mapping]:
    """Uma coordenada inteira (`time`, `lat` ou `lon`), juntando os pedaços."""
    meta = _json(cliente, nome)
    (tamanho,) = meta["shape"]
    (por_pedaco,) = meta["chunk_grid"]["configuration"]["chunk_shape"]
    partes = []
    for i in range(-(-tamanho // por_pedaco)):
        conteudo = _pedaco(cliente, nome, str(i))
        if conteudo is None:
            raise ValueError(f"falta a coordenada {nome} do Zarr do CHIRPS v3")
        bruto = _descomprimir(conteudo, por_pedaco * np.dtype(dtype).itemsize)
        partes.append(np.frombuffer(bruto, dtype=dtype))
    return np.concatenate(partes)[:tamanho], meta["attributes"]


def _dias_do_mes(tempo: np.ndarray, atributos: Mapping, ano: int, mes: int) -> range:
    """Os índices do tempo dos dias do mês; mês que a cópia ainda não cobre inteiro é `SemArquivo`."""
    unidade = str(atributos["units"])
    if not unidade.startswith("days since "):
        raise ValueError(f"unidade de tempo que não conheço: {unidade}")
    origem = date.fromisoformat(unidade.removeprefix("days since ")[:10])
    primeiro = (date(ano, mes, 1) - origem).days
    ultimo = primeiro + calendar.monthrange(ano, mes)[1] - 1
    inicio = int(np.searchsorted(tempo, primeiro))
    fim = int(np.searchsorted(tempo, ultimo, side="right"))
    if fim - inicio != ultimo - primeiro + 1 or tempo[inicio] != primeiro:
        raise SemArquivo(f"{ano}-{mes:02d}: a cópia do CHIRPS v3 ainda não cobre o mês")
    return range(inicio, fim)


def _intervalo(centros: np.ndarray, maximo: float, minimo: float) -> slice:
    """Os índices dos centros entre `minimo` e `maximo` (vale para eixo crescente ou decrescente)."""
    dentro = np.flatnonzero((centros >= minimo) & (centros <= maximo))
    if dentro.size == 0:
        raise ValueError("a janela não cruza a grade do CHIRPS v3")
    return slice(int(dentro[0]), int(dentro[-1]) + 1)


class _Pedacos:
    """Os pedaços do `precip` já baixados, os mais recentes (comprimidos), para meses vizinhos."""

    def __init__(self) -> None:
        self.guardados: OrderedDict[str, bytes | None] = OrderedDict()

    def obter(self, cliente: Cliente, chave: str) -> bytes | None:
        if chave in self.guardados:
            self.guardados.move_to_end(chave)
            return self.guardados[chave]
        conteudo = _pedaco(cliente, "precip", chave)
        self.guardados[chave] = conteudo
        while len(self.guardados) > PEDACOS_NA_MEMORIA:
            self.guardados.popitem(last=False)
        return conteudo


def _somar(
    cliente: Cliente,
    pedacos: _Pedacos,
    geometria: Geometria,
    dias: range,
    linhas: slice,
    colunas: slice,
) -> tuple[np.ndarray, np.ndarray]:
    """A soma (0,1 mm) e a contagem de dias com dado de cada pixel da janela, no mês."""
    forma = (linhas.stop - linhas.start, colunas.stop - colunas.start)
    soma = np.zeros(forma, dtype=np.int32)
    validos = np.zeros(forma, dtype=np.uint8)
    pt, pl, pc = geometria.pedaco
    tamanho = pt * pl * pc * 2
    for t in range(dias.start // pt, (dias.stop - 1) // pt + 1):
        d0, d1 = max(dias.start, t * pt) - t * pt, min(dias.stop, (t + 1) * pt) - t * pt
        for lin in range(linhas.start // pl, (linhas.stop - 1) // pl + 1):
            for col in range(colunas.start // pc, (colunas.stop - 1) // pc + 1):
                l0, l1 = max(linhas.start, lin * pl), min(linhas.stop, (lin + 1) * pl)
                c0, c1 = max(colunas.start, col * pc), min(colunas.stop, (col + 1) * pc)
                conteudo = pedacos.obter(cliente, f"{t}/{lin}/{col}")
                if conteudo is None:
                    continue  # pedaço ausente: tudo sem dado
                bloco = np.frombuffer(_descomprimir(conteudo, tamanho), dtype="<i2")
                bloco = bloco.reshape(geometria.pedaco)
                parte = bloco[
                    d0:d1, l0 - lin * pl : l1 - lin * pl, c0 - col * pc : c1 - col * pc
                ]
                com_dado = parte != SEM_DADO
                destino = (slice(l0 - linhas.start, l1 - linhas.start), slice(c0 - colunas.start, c1 - colunas.start))  # fmt: skip
                soma[destino] += np.where(com_dado, parte, 0).sum(
                    axis=0, dtype=np.int32
                )
                validos[destino] += com_dado.sum(axis=0, dtype=np.uint8)
    return soma, validos


def montar_arquivo(
    cliente: Cliente,
    ano: int,
    mes: int,
    janela: Janela = JANELA_DO_CAFE,
    pedacos: _Pedacos | None = None,
) -> bytes:
    """O arquivo do mês: cabeçalho JSON da grade e, em Zstandard, a soma (int32) e os dias com dado
    (uint8) de cada pixel da janela. Bytes iguais para o mesmo dado (o SHA-256 não muda à toa)."""
    geometria = _geometria(_json(cliente, "precip"))
    tempo, atributos_do_tempo = _eixo(cliente, "time", "<i4")
    dias = _dias_do_mes(tempo, atributos_do_tempo, ano, mes)
    lat, _ = _eixo(cliente, "lat", "<f8")
    lon, _ = _eixo(cliente, "lon", "<f8")
    linhas = _intervalo(lat, janela.lat_norte, janela.lat_sul)
    colunas = _intervalo(lon, janela.lon_leste, janela.lon_oeste)
    passo = round(abs(float(lat[1] - lat[0])), 6)
    soma, validos = _somar(
        cliente, pedacos or _Pedacos(), geometria, dias, linhas, colunas
    )
    grade = Grade(
        lon_oeste=round(float(lon[colunas.start]) - passo / 2, 6),
        lat_norte=round(float(lat[linhas.start]) + passo / 2, 6),
        passo=passo,
        colunas=soma.shape[1],
        linhas=soma.shape[0],
    )
    cabecalho = {"ano": ano, "mes": mes, "dias": len(dias), "grade": grade._asdict(), "escala": ESCALA_ESPERADA}  # fmt: skip
    corpo = soma.astype("<i4").tobytes() + validos.tobytes()
    return (
        CABECALHO
        + json.dumps(cabecalho, sort_keys=True).encode()
        + b"\n"
        + zstandard.ZstdCompressor(level=9).compress(corpo)
    )


class MesDoCHIRPS(NamedTuple):
    """O arquivo do mês, lido: grade, mês e milímetros por pixel (NaN onde faltou algum dia)."""

    ano: int
    mes: int
    grade: Grade
    chuva_mm: np.ndarray


def ler_arquivo(conteudo: bytes) -> MesDoCHIRPS:
    """Desfaz `montar_arquivo`: a chuva do mês em mm por pixel; pixel sem todos os dias vira NaN."""
    if not conteudo.startswith(CABECALHO):
        raise ValueError("não é um arquivo mensal do CHIRPS v3")
    linha, _, resto = conteudo[len(CABECALHO) :].partition(b"\n")
    cabecalho = json.loads(linha)
    grade = Grade(**cabecalho["grade"])
    pixels = grade.linhas * grade.colunas
    bruto = _descomprimir(resto, pixels * 5)
    soma = np.frombuffer(bruto[: pixels * 4], dtype="<i4").reshape(
        grade.linhas, grade.colunas
    )
    validos = np.frombuffer(bruto[pixels * 4 :], dtype=np.uint8).reshape(
        grade.linhas, grade.colunas
    )
    chuva = soma.astype(np.float32) * np.float32(cabecalho["escala"])
    chuva[validos != cabecalho["dias"]] = np.nan
    return MesDoCHIRPS(cabecalho["ano"], cabecalho["mes"], grade, chuva)


# --- a coleta (fonte do arquivo guardado) --------------------------------------------------------
def _obter_do_mes(
    ano: int, mes: int, pedacos: _Pedacos
) -> Callable[[Cliente, Path], Mapping[str, str]]:
    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        destino.write_bytes(montar_arquivo(cliente, ano, mes, pedacos=pedacos))
        return {}

    return obter


def _alvos_dos_meses(agora: datetime, atras: range) -> list[Alvo]:
    """Os meses `atras` (1 = o mês passado), do mais antigo ao mais novo."""
    hoje = agora.date()
    pedacos = _Pedacos()  # os meses vizinhos dividem os mesmos pedaços de 128 dias
    alvos = []
    for n in reversed(atras):
        ano, mes = divmod(hoje.year * 12 + hoje.month - 1 - n, 12)
        mes += 1
        alvos.append(
            Alvo(
                ENDERECO_DO_MES.format(ano=ano, mes=mes),
                ".bin",
                _obter_do_mes(ano, mes, pedacos),
            )
        )
    return alvos


def _recentes(_cliente: Cliente, agora: datetime) -> list[Alvo]:
    return _alvos_dos_meses(agora, range(1, MESES_RECENTES + 1))


def _historico(_cliente: Cliente, agora: datetime) -> list[Alvo]:
    """De janeiro de 1991 até o mês anterior aos recentes."""
    desde_1991 = (agora.year - PRIMEIRO_ANO) * 12 + agora.month - 1
    return _alvos_dos_meses(agora, range(MESES_RECENTES + 1, desde_1991 + 1))


def fontes() -> list[Fonte]:
    return [
        Fonte("chirps3-rnl-mensal", "mensal", _recentes),
        Fonte("chirps3-rnl-historico", "carga-unica", _historico),
    ]
