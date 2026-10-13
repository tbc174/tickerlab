"""Leitura do nó do Bitcoin em Parquet, retomável e com reorganização (base de cripto, PR 2).

Lê bloco a bloco, da altura seguinte à última gravada até o último bloco com `CONFIRMACOES`
confirmações (o topo da cadeia ainda pode ser trocado pela rede). Grava, na `pasta`:

- `blocos/AAAA/AAAA-MM.parquet`: uma linha por bloco (as métricas de `blocos.py` e `coletado_em`),
  separadas pelo mês da hora do bloco, em UTC;
- `parado/AAAA.parquet`: por dia UTC, a fração das moedas paradas há mais de um ano no fim do dia;
- `pontos/ponto-<altura>.npz`: o estado da leitura (histograma de idade, horas por altura), para
  recomeçar de onde parou; os `PONTOS_GUARDADOS` mais novos ficam;
- `reorganizacoes/<quando>.parquet`: blocos que a rede trocou por outros, com o motivo. Nada que já
  foi gravado some sem deixar registro (ADR 0024).

**Quando o dia "fecha":** a hora que o minerador põe no bloco pode andar para trás, mas a hora
mediana (das 11 anteriores) só cresce, e um bloco novo precisa ter hora maior que ela. Então, quando
a hora mediana passa da meia-noite UTC, nenhum bloco futuro pode cair no dia anterior: é aí que a
fração parada do dia é calculada.

**O nó é podado** (ADR 0031): depois de gravar, o leitor diz ao nó até onde ele pode apagar os
blocos (`liberar_ate`), sempre deixando os que um ponto guardado ainda precisaria para refazer a
leitura depois de uma reorganização.
"""

import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from base.cripto.arquivos import (
    acrescentar,
    arquivos_da_tabela,
    gravar_parquet,
    ler_tabela,
)
from base.cripto.blocos import (
    FOLGA_DO_HISTOGRAMA,
    atualizar_histograma,
    metricas_do_bloco,
)

CONFIRMACOES = 6
BLOCOS_POR_PONTO = 1_000
PONTOS_GUARDADOS = 24
# o Bitcoin Core nunca apaga os 288 blocos mais novos (cerca de 2 dias)
BLOCOS_QUE_O_NO_GUARDA = 288
DIAS_PARA_ESTAR_PARADO = 365
SEGUNDOS_POR_DIA = 86_400
MOTIVO_DA_REORGANIZACAO = "reorganização da cadeia: a rede trocou este bloco por outro"

PASTA_DOS_BLOCOS = "blocos"
PASTA_DO_PARADO = "parado"
PASTA_DOS_PONTOS = "pontos"
PASTA_DAS_REORGANIZACOES = "reorganizacoes"


class FonteDeBlocos(Protocol):
    """O que a leitura precisa do nó (o `ClienteRPC` e o nó falso dos testes)."""

    def altura_do_topo(self) -> int: ...
    def hash_na_altura(self, altura: int) -> str: ...
    def bloco(self, hash_do_bloco: str) -> dict: ...
    def liberar_ate(self, altura: int) -> None: ...
    def total_nao_gasto(self, altura: int) -> int: ...


class CadeiaInconsistente(RuntimeError):
    """A cadeia do nó não continua a que já foi lida, e não há ponto conhecido para voltar."""


@dataclass
class Estado:
    """Onde a leitura parou: a última altura lida e o que é preciso para continuar dela."""

    altura: int = -1
    hash: str = ""
    histograma: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    horas: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    dia_aberto: date | None = None  # o primeiro dia ainda sem a fração parada


@dataclass
class _Lote:
    blocos: list[dict] = field(default_factory=list)
    parado: list[dict] = field(default_factory=list)


def ler_ate_o_topo(
    no: FonteDeBlocos,
    pasta: Path,
    agora: datetime,
    *,
    confirmacoes: int = CONFIRMACOES,
    blocos_por_ponto: int = BLOCOS_POR_PONTO,
) -> int:
    """Lê do último ponto gravado até o último bloco com `confirmacoes`; devolve quantos leu."""
    estado = _estado_valido(no, pasta, agora)
    limite = no.altura_do_topo() - confirmacoes + 1
    lote = _Lote()
    lidos = 0
    while estado.altura < limite:
        _aplicar_bloco(estado, _proximo_bloco(no, estado), lote, agora)
        lidos += 1
        if len(lote.blocos) >= blocos_por_ponto or estado.altura == limite:
            _gravar(pasta, lote, estado, no)
            lote = _Lote()
    return lidos


def ler_blocos(pasta: Path) -> pd.DataFrame:
    """Todas as linhas de blocos gravadas, em ordem de altura."""
    return ler_tabela(pasta / PASTA_DOS_BLOCOS, "altura")


def ler_parado(pasta: Path) -> pd.DataFrame:
    """A fração parada há mais de um ano, por dia UTC, em ordem de dia."""
    return ler_tabela(pasta / PASTA_DO_PARADO, "dia")


def ler_reorganizacoes(pasta: Path) -> pd.DataFrame:
    """Os blocos que a rede trocou, como estavam gravados, com `desfeito_em` e `motivo`."""
    return ler_tabela(pasta / PASTA_DAS_REORGANIZACOES, "altura")


def conferir_com_o_no(pasta: Path, no: FonteDeBlocos) -> int:
    """Soma do histograma menos o total não gasto que o nó informa, em satoshis (0 = bate)."""
    estado = _carregar_ponto(_listar_pontos(pasta)[-1])
    return int(estado.histograma.sum()) - no.total_nao_gasto(estado.altura)


def _proximo_bloco(no: FonteDeBlocos, estado: Estado) -> dict:
    altura = estado.altura + 1
    bloco = no.bloco(no.hash_na_altura(altura))
    if altura > 0 and bloco.get("previousblockhash") != estado.hash:
        raise CadeiaInconsistente(
            f"O bloco da altura {altura} não continua o bloco lido antes dele."
        )
    return bloco


def _aplicar_bloco(estado: Estado, bloco: dict, lote: _Lote, agora: datetime) -> None:
    altura = bloco["height"]
    estado.horas = _com_tamanho(estado.horas, altura)
    estado.horas[altura] = bloco["time"]
    estado.histograma = _com_tamanho(estado.histograma, altura)
    # o dia fecha com o estado de antes deste bloco
    _fechar_dias(estado, bloco, lote, agora)
    metricas = metricas_do_bloco(bloco, lambda origem: int(estado.horas[origem]))
    estado.histograma = atualizar_histograma(estado.histograma, bloco)
    estado.altura, estado.hash = altura, bloco["hash"]
    lote.blocos.append({**asdict(metricas), "coletado_em": agora})


def _fechar_dias(estado: Estado, bloco: dict, lote: _Lote, agora: datetime) -> None:
    if estado.dia_aberto is None:
        estado.dia_aberto = datetime.fromtimestamp(bloco["time"], tz=UTC).date()
    while _fim_do_dia(estado.dia_aberto) <= bloco["mediantime"]:
        lote.parado.append(
            {
                "dia": estado.dia_aberto,
                "altura": estado.altura,
                "fracao_parada_1_ano": _fracao_parada(
                    estado, _fim_do_dia(estado.dia_aberto)
                ),
                "coletado_em": agora,
            }
        )
        estado.dia_aberto += timedelta(days=1)


def _fim_do_dia(dia: date) -> int:
    """Meia-noite UTC que encerra o dia, em segundos Unix."""
    return (
        int(datetime(dia.year, dia.month, dia.day, tzinfo=UTC).timestamp())
        + SEGUNDOS_POR_DIA
    )


def _fracao_parada(estado: Estado, fim_do_dia: int) -> float | None:
    quantas = estado.altura + 1
    nao_gasto = estado.histograma[:quantas]
    total = int(nao_gasto.sum())
    if total == 0:
        return None
    corte = fim_do_dia - DIAS_PARA_ESTAR_PARADO * SEGUNDOS_POR_DIA
    return float(nao_gasto[estado.horas[:quantas] < corte].sum() / total)


def _com_tamanho(valores: np.ndarray, altura: int) -> np.ndarray:
    if altura < len(valores):
        return valores
    return np.concatenate(
        [valores, np.zeros(altura - len(valores) + FOLGA_DO_HISTOGRAMA, np.int64)]
    )


# --- gravação ---------------------------------------------------------------------------------


def _gravar(pasta: Path, lote: _Lote, estado: Estado, no: FonteDeBlocos) -> None:
    """Linhas primeiro, ponto depois: se cair no meio, a leitura refaz do ponto anterior e as
    linhas repetidas são trocadas (chave única por altura e por dia)."""
    blocos = pd.DataFrame(lote.blocos)
    acrescentar(
        pasta / PASTA_DOS_BLOCOS,
        blocos,
        blocos["hora"].dt.strftime("%Y/%Y-%m"),
        "altura",
    )
    if lote.parado:
        parado = pd.DataFrame(lote.parado)
        acrescentar(
            pasta / PASTA_DO_PARADO,
            parado,
            parado["dia"].map(lambda d: f"{d.year}"),
            "dia",
        )
    _salvar_ponto(pasta, estado)
    pontos = _listar_pontos(pasta)
    for velho in pontos[:-PONTOS_GUARDADOS]:
        velho.unlink()
    _liberar_no_no(no, pasta, estado)


def _liberar_no_no(no: FonteDeBlocos, pasta: Path, estado: Estado) -> None:
    mais_antigo = _altura_do_ponto(_listar_pontos(pasta)[0])
    ate = min(mais_antigo, estado.altura - BLOCOS_QUE_O_NO_GUARDA)
    if ate > 0:
        no.liberar_ate(ate)


# --- pontos e reorganização -------------------------------------------------------------------


def _salvar_ponto(pasta: Path, estado: Estado) -> None:
    quantas = estado.altura + 1
    arquivo = pasta / PASTA_DOS_PONTOS / f"ponto-{estado.altura:09d}.npz"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    provisorio = arquivo.with_name(arquivo.stem + ".provisorio.npz")
    np.savez_compressed(
        provisorio,
        altura=estado.altura,
        hash=estado.hash,
        histograma=estado.histograma[:quantas],
        horas=estado.horas[:quantas],
        dia_aberto=estado.dia_aberto.isoformat() if estado.dia_aberto else "",
    )
    os.replace(provisorio, arquivo)


def _carregar_ponto(arquivo: Path) -> Estado:
    with np.load(arquivo, allow_pickle=False) as ponto:
        dia_aberto = str(ponto["dia_aberto"])
        return Estado(
            altura=int(ponto["altura"]),
            hash=str(ponto["hash"]),
            histograma=ponto["histograma"].copy(),
            horas=ponto["horas"].copy(),
            dia_aberto=date.fromisoformat(dia_aberto) if dia_aberto else None,
        )


def _listar_pontos(pasta: Path) -> list[Path]:
    """Os pontos gravados, do mais velho ao mais novo (o nome tem a altura com zeros à esquerda)."""
    pasta_dos_pontos = pasta / PASTA_DOS_PONTOS
    if not pasta_dos_pontos.exists():
        return []
    return sorted(
        p for p in pasta_dos_pontos.glob("ponto-*.npz") if "provisorio" not in p.name
    )


def _altura_do_ponto(arquivo: Path) -> int:
    return int(arquivo.stem.removeprefix("ponto-"))


def _estado_valido(no: FonteDeBlocos, pasta: Path, agora: datetime) -> Estado:
    """O ponto mais novo que a cadeia do nó ainda tem. Se não for o último gravado, a rede trocou
    blocos: o que foi lido depois dele vai para `reorganizacoes/`."""
    pontos = _listar_pontos(pasta)
    if not pontos:
        return Estado()
    for posicao in range(len(pontos) - 1, -1, -1):
        estado = _carregar_ponto(pontos[posicao])
        if _no_ainda_tem(no, estado):
            if posicao < len(pontos) - 1:
                _desfazer_acima(pasta, estado.altura, agora)
                for descartado in pontos[posicao + 1 :]:
                    descartado.unlink()
            return estado
    raise CadeiaInconsistente(
        "A cadeia do nó não tem nenhum ponto já lido: a leitura não sabe de onde continuar."
    )


def _no_ainda_tem(no: FonteDeBlocos, estado: Estado) -> bool:
    return (
        estado.altura <= no.altura_do_topo()
        and no.hash_na_altura(estado.altura) == estado.hash
    )


def _desfazer_acima(pasta: Path, corte: int, agora: datetime) -> None:
    """Tira dos arquivos o que está acima do `corte`: os blocos vão para `reorganizacoes/` (com o
    motivo); a fração parada é recalculada na leitura seguinte."""
    desfeitos = [
        _tirar_acima(arquivo, corte)
        for arquivo in arquivos_da_tabela(pasta / PASTA_DOS_BLOCOS)
    ]
    for arquivo in arquivos_da_tabela(pasta / PASTA_DO_PARADO):
        _tirar_acima(arquivo, corte)
    desfeitos = [tabela for tabela in desfeitos if not tabela.empty]
    if desfeitos:
        tabela = pd.concat(desfeitos).assign(
            desfeito_em=agora, motivo=MOTIVO_DA_REORGANIZACAO
        )
        nome = f"{agora:%Y%m%dT%H%M%S}.parquet"
        gravar_parquet(pasta / PASTA_DAS_REORGANIZACOES / nome, tabela)


def _tirar_acima(arquivo: Path, corte: int) -> pd.DataFrame:
    """Regrava o arquivo sem as linhas acima do `corte` e devolve as que saíram."""
    tabela = pd.read_parquet(arquivo)
    acima = tabela["altura"] > corte
    if acima.any():
        gravar_parquet(arquivo, tabela[~acima])
    return tabela[acima]
