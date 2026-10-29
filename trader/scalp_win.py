"""Fase 1 do scalp no mini índice (WIN): mede se regras simples passam do custo. Só leitura.

Implementa o `docs/pre-registro-scalp-win-fase1.md` (versão 1.0, escrita antes da medida): lê o
arquivo grátis de negócios da B3, mede o custo do spread (Roll), o movimento por horário e as 8
regras de scalp pré-registradas, e decide APROVA ou REPROVA pelo critério da seção 4. Nada aqui
fala com corretora ou plataforma. Pesquisa à parte da M2: não grava no registro dela.

Uso (uma vez; toda execução é uma tentativa):

    python -m trader.scalp_win --negocios <pasta dos zips> --selo <pasta dos selos> --saida <pasta>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from base.intradiario_b3 import PASSO_DO_IDENTIFICADOR, ler_negocios
from src.barras_intradiarias import FUSO_DA_B3, SESSAO_REGULAR, remover_cancelados

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_DO_PRE_REGISTRO = RAIZ / "docs" / "pre-registro-scalp-win-fase1.md"
# SHA-256 do texto vigente (quebras de linha normalizadas para \n), versão 1.0 de 29/10/2026.
SHA256_DO_PRE_REGISTRO = (
    "5c4e4bb853618a5471efc8d154c6ee425ecf1f904eb4c1b8cafe5a9cbd6428e2"
)

PADRAO_DO_FUTURO_WIN = re.compile(r"^WIN[FGHJKMNQUVXZ]\d\d$")
SELO_QUE_ENTRA = "completo"

INICIO_DA_JANELA = pd.Timedelta(hours=9, minutes=15)
FIM_DA_JANELA = pd.Timedelta(hours=17, minutes=45)
FAIXA_DO_HORARIO = "30min"

PONTOS_POR_TICK = 5.0
TARIFA_DE_IDA_E_VOLTA_EM_PONTOS = (
    2.5  # cerca de R$ 0,50 por contrato; 1 ponto = R$ 0,20
)
DERRAPAGEM_MEDIA_EM_PONTOS = PONTOS_POR_TICK / 2
PISO_DO_EMPATE_EM_PONTOS = 10.0  # cenário C do relatório da pesquisa

HORIZONTES_EM_MINUTOS = (1, 2, 5, 10)
DIRECOES = ("momento", "reversao")
SINAL_DA_DIRECAO = {"momento": 1.0, "reversao": -1.0}

REAMOSTRAS = 10_000
SEMENTE = 20261029
PERCENTIS_DO_INTERVALO = (2.5, 97.5)


@dataclass(frozen=True)
class Dia:
    """Um pregão da tabela fechada no pré-registro (seção 2)."""

    pregao: str
    simbolo: str
    selo: str
    sha256: str


@dataclass(frozen=True)
class Variante:
    """Uma das 8 regras de scalp pré-registradas (seção 3, M3)."""

    h: int
    direcao: str

    @property
    def nome(self) -> str:
        return f"{self.direcao}_{self.h}min"


class ArquivoDiferenteError(RuntimeError):
    """O arquivo do pregão não é o que o pré-registro fechou (hash diferente)."""


DIAS: tuple[Dia, ...] = tuple(
    Dia(*linha)
    for linha in [
        (
            "2026-09-15",
            "WINV26",
            "completo",
            "1b544fed0dc4c1d365c7c671232eeaf776bf3048875fac542ee5b70f79fbb072",
        ),
        (
            "2026-09-16",
            "WINV26",
            "completo",
            "63c96cdf4c8d743b800ed76e8bfe80ee7a3f9e062cf1d773400171e2caa5d2b1",
        ),
        (
            "2026-09-17",
            "WINV26",
            "completo",
            "f186080ae01b193bd153c310b5c124dd5feeae8a21f7dbb7b0cafca11f48a6f3",
        ),
        (
            "2026-09-18",
            "WINV26",
            "completo",
            "d99f509eefb5c33ad6de6641fff4e14ce43c412dc937eb5c51bd2ef4998efd89",
        ),
        (
            "2026-09-21",
            "WINV26",
            "completo",
            "63f5de9f59dbc1a90e8e8361b2f1d45c55551bec4ae0e02c9cf194f7fc14f588",
        ),
        (
            "2026-09-22",
            "WINV26",
            "incompleto",
            "b5f481cb7060203695ec7a74fdc3c71c83366bc5cc4b876bbe15670a2fc84c07",
        ),
        (
            "2026-09-23",
            "WINV26",
            "completo",
            "df0b40253a12b0efe8c65959da65f8095a5097f847c7593a02a267311c43b271",
        ),
        (
            "2026-09-24",
            "WINV26",
            "completo",
            "86db531abe795b3ddd4ffcd62da2a32d9285e450c01e75b1e2b1779e5dd9b04f",
        ),
        (
            "2026-09-25",
            "WINV26",
            "incompleto",
            "955d799aabbc5c348cc55be789b80ca438f6c839a98691397127f9b7eb3416bc",
        ),
        (
            "2026-09-28",
            "WINV26",
            "completo",
            "e45d6ca309e52f8e0b9b68169f38e6e325c20aabae163c1f36bed8dcd0cb9aaa",
        ),
        (
            "2026-09-29",
            "WINV26",
            "incompleto",
            "1a7c580380ec8c5e148884dbf1655f5f2d9a96a9982b02422267f4becb42b085",
        ),
        (
            "2026-09-30",
            "WINV26",
            "completo",
            "7f004e6abe5d25187fea3e0d27a46e0cfa90dfb51af2da27267709b44428f322",
        ),
        (
            "2026-10-01",
            "WINV26",
            "completo",
            "29f7c5804ae8ed0d541dc303f44e5a8046b10f7355bafea09ac62dd567c7067a",
        ),
        (
            "2026-10-02",
            "WINV26",
            "completo",
            "d7d0a32e539d8b1bbaec16540c7f04df3e7529330648125494473e1285365e0d",
        ),
        (
            "2026-10-05",
            "WINV26",
            "completo",
            "3cae4cb5314fbf88787d0f66fb48d0d18614e23475bcf4b16f3306947d278a9b",
        ),
        (
            "2026-10-06",
            "WINV26",
            "completo",
            "8e397b0dcb38551afcf82969aa77f56edeed8d05acf9d739c4afbbeca6538884",
        ),
        (
            "2026-10-07",
            "WINV26",
            "completo",
            "1436aff7e664229549d965442abb68aa4b3a5f7cf8192d4e0dfa5c6d51d2a7b7",
        ),
        (
            "2026-10-08",
            "WINV26",
            "completo",
            "692a94a7c2199fea578f2724cd8d8565f2f3978625885e031f44dba9195e6400",
        ),
        (
            "2026-10-09",
            "WINV26",
            "incompleto",
            "799bcf06be7da994d61538ce7a2c9d22ed0fd220e88cc664e206cea4a4298029",
        ),
        (
            "2026-10-13",
            "WINV26",
            "completo",
            "3bfbe976a4e9415fe18af31b755cbbd2c46904f76bddbe8618d71df0058e5c91",
        ),
        (
            "2026-10-14",
            "WINZ26",
            "completo",
            "0d0af93ec3d827e4a94cdb8589be18beaab951ff7ca5dad4cd5102a399d416d8",
        ),
        (
            "2026-10-15",
            "WINZ26",
            "completo",
            "3488103acb44cf40f3c35372cfbc23d0a00776577952e433a45f496f3d00832f",
        ),
        (
            "2026-10-16",
            "WINZ26",
            "completo",
            "4cd327d297d742779f06b242ffa291f2147321ee7aecafaabfee3e66c575a64e",
        ),
        (
            "2026-10-19",
            "WINZ26",
            "completo",
            "81bee21c2eec77c99fb36587dc17b13611692f703276be83b6af13cbf1100317",
        ),
        (
            "2026-10-20",
            "WINZ26",
            "completo",
            "55fc7791271f9d6ab3cda974bd166fb81e7bbd50f20180a5b7bf3bdf7c70a5b6",
        ),
        (
            "2026-10-21",
            "WINZ26",
            "completo",
            "aae19a5d4a32e151a20a0692688ae3dd74dc822b49bdd3132d819088bd312840",
        ),
        (
            "2026-10-22",
            "WINZ26",
            "completo",
            "ce24e1ce54266d37fca9c774dbec4eb28fb43e9f411e36b4a0e6d1791cda084e",
        ),
    ]
)
DIAS_QUE_ENTRAM: tuple[Dia, ...] = tuple(
    dia for dia in DIAS if dia.selo == SELO_QUE_ENTRA
)
VARIANTES: tuple[Variante, ...] = tuple(
    Variante(h, direcao) for h in HORIZONTES_EM_MINUTOS for direcao in DIRECOES
)


# --- conferências ---
def sha256_do_pre_registro(caminho: Path = CAMINHO_DO_PRE_REGISTRO) -> str:
    """SHA-256 do pré-registro, ignorando diferença de quebra de linha (Windows x Linux)."""
    return hashlib.sha256(caminho.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def conferir_arquivo(caminho: Path, pregao: str, esperado: str) -> None:
    """Para a rodada se o arquivo do pregão não for o que o pré-registro fechou."""
    achado = hashlib.sha256(caminho.read_bytes()).hexdigest()
    if achado != esperado:
        raise ArquivoDiferenteError(
            f"{pregao}: o arquivo tem SHA-256 {achado}, o pré-registro fechou {esperado}"
        )


def contrato_principal(selo: pd.DataFrame) -> tuple[str, str]:
    """O futuro do WIN de maior volume no boletim do dia e o selo dele."""
    futuros = selo[selo["simbolo"].astype(str).str.match(PADRAO_DO_FUTURO_WIN)]
    if futuros.empty:
        raise ValueError("o selo do dia não tem nenhum futuro do WIN")
    linha = futuros.sort_values(
        "volume_no_boletim", ascending=False, kind="stable"
    ).iloc[0]
    return str(linha["simbolo"]), str(linha["selo"])


# --- negócios ---
def limpar_negocios(
    negocios: pd.DataFrame, simbolo: str, pregao: pd.Timestamp
) -> pd.DataFrame:
    """Os negócios do contrato no pregão, como a seção 2 manda, na ordem instante e identificador.

    Tira as linhas de cancelamento e os negócios cancelados, os inseridos depois (identificador que
    não é múltiplo de 10), o after e os negócios de outro pregão.
    """
    do_contrato = remover_cancelados(negocios[negocios["simbolo"] == simbolo])
    mantidos = (
        (do_contrato["identificador"] % PASSO_DO_IDENTIFICADOR == 0)
        & (do_contrato["sessao"] == SESSAO_REGULAR)
        & (do_contrato["pregao"] == pregao)
    )
    return do_contrato[mantidos].sort_values(
        ["instante", "identificador"], kind="stable"
    )


def _horario(pregao: pd.Timestamp, deslocamento: pd.Timedelta) -> pd.Timestamp:
    return (pregao.normalize() + deslocamento).tz_localize(FUSO_DA_B3)


def na_janela(negocios: pd.DataFrame, pregao: pd.Timestamp) -> pd.DataFrame:
    """Os negócios das 09h15 (inclusive) às 17h45 (exclusive)."""
    inicio = _horario(pregao, INICIO_DA_JANELA)
    fim = _horario(pregao, FIM_DA_JANELA)
    return negocios[(negocios["instante"] >= inicio) & (negocios["instante"] < fim)]


# --- M1: custo do spread ---
def spread_de_roll(precos: np.ndarray) -> float:
    """Medida de Roll: 2·√(−cov(Δpₜ, Δpₜ₋₁)), em pontos; 0 quando a covariância não é negativa."""
    mudancas = np.diff(np.asarray(precos, dtype=float))
    if len(mudancas) < 3:
        return 0.0
    covariancia = float(np.cov(mudancas[1:], mudancas[:-1])[0, 1])
    return 2.0 * float(np.sqrt(-covariancia)) if covariancia < 0 else 0.0


def fracao_de_um_tick(precos: np.ndarray) -> float:
    """Das mudanças de preço diferentes de zero, a fração que é de um tick."""
    mudancas = np.abs(np.diff(np.asarray(precos, dtype=float)))
    mudancas = mudancas[mudancas > 0]
    if len(mudancas) == 0:
        return float("nan")
    return float(np.mean(np.isclose(mudancas, PONTOS_POR_TICK)))


def empate(spread_em_pontos: float) -> float:
    """Ganho bruto por operação que só empata: tarifa + spread + derrapagem, com o piso de 10."""
    custo = (
        TARIFA_DE_IDA_E_VOLTA_EM_PONTOS + spread_em_pontos + DERRAPAGEM_MEDIA_EM_PONTOS
    )
    return max(PISO_DO_EMPATE_EM_PONTOS, custo)


# --- grade de preços ---
def _em_nanossegundos(instantes: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    indice = pd.DatetimeIndex(instantes).tz_convert("UTC").as_unit("ns")
    return indice.asi8


def grade_de_precos(negocios: pd.DataFrame, pregao: pd.Timestamp) -> pd.Series:
    """Preço em cada minuto das 09h15 às 17h45: o do último negócio antes daquele minuto.

    Minuto sem negócio herda o anterior; antes do primeiro negócio, vazio. Só olha negócios de antes
    de cada minuto (sem olhar o futuro).
    """
    ordenados = negocios.sort_values(["instante", "identificador"], kind="stable")
    grade = pd.date_range(
        _horario(pregao, INICIO_DA_JANELA), _horario(pregao, FIM_DA_JANELA), freq="min"
    )
    posicao = (
        np.searchsorted(
            _em_nanossegundos(ordenados["instante"]),
            _em_nanossegundos(grade),
            side="left",
        )
        - 1
    )
    # um preço vazio na frente: posição -1 (nenhum negócio antes do minuto) cai nele
    precos = np.concatenate([[np.nan], ordenados["preco"].to_numpy(dtype=float)])
    return pd.Series(precos[posicao + 1], index=grade, dtype=float)


# --- M3: as regras ---
def ganhos_do_sinal(
    grade: pd.Series, sinal: np.ndarray, h: int, direcao: str
) -> np.ndarray:
    """Ganho bruto (pontos) de cada operação: decide a cada h minutos pelo sinal, sai h minutos depois.

    `sinal` tem um valor por minuto da grade, calculado só com o que veio antes daquele minuto.
    Decisões nos minutos h, 2h, ... da grade, enquanto a saída cabe nela. Sinal zero ou vazio, ou
    preço vazio: não opera. Momento segue o sinal; reversão vai contra.
    """
    if direcao not in SINAL_DA_DIRECAO:
        raise ValueError(
            f"direção desconhecida: {direcao!r} (use {', '.join(DIRECOES)})"
        )
    precos = grade.to_numpy(dtype=float)
    decisoes = np.arange(h, len(precos) - h, h)
    lado = np.sign(np.asarray(sinal, dtype=float)[decisoes])
    resultado = precos[decisoes + h] - precos[decisoes]
    opera = np.isfinite(lado) & np.isfinite(resultado) & (lado != 0)
    return SINAL_DA_DIRECAO[direcao] * lado[opera] * resultado[opera]


def ganhos_da_regra(grade: pd.Series, h: int, direcao: str) -> np.ndarray:
    """As regras da fase 1: o sinal é a variação do preço nos h minutos de antes da decisão."""
    precos = grade.to_numpy(dtype=float)
    variacao_de_antes = np.full(len(precos), np.nan)
    variacao_de_antes[h:] = precos[h:] - precos[:-h]
    return ganhos_do_sinal(grade, variacao_de_antes, h, direcao)


# --- M2: movimento por horário ---
def variacoes(grade: pd.Series, h: int) -> pd.DataFrame:
    """Variação de h minutos começando em cada minuto da grade, com a faixa de 30 min do começo."""
    precos = grade.to_numpy(dtype=float)
    inicio = grade.index[: len(precos) - h]
    variacao = precos[h:] - precos[:-h]
    tabela = pd.DataFrame(
        {
            "h": h,
            "faixa": inicio.floor(FAIXA_DO_HORARIO).strftime("%H:%M"),
            "variacao": variacao,
        }
    )
    return tabela[np.isfinite(tabela["variacao"])]


def resumo_por_faixa(tabela: pd.DataFrame) -> pd.DataFrame:
    """Desvio padrão e média do valor absoluto das variações, por horizonte e faixa."""
    return (
        tabela.assign(absoluta=tabela["variacao"].abs())
        .groupby(["h", "faixa"], as_index=False)
        .agg(
            desvio=("variacao", "std"),
            media_abs=("absoluta", "mean"),
            n=("variacao", "size"),
        )
    )


# --- critério ---
def media_por_operacao(dias: Sequence[np.ndarray]) -> float:
    """Ganho médio por operação juntando as operações de todos os dias."""
    quantidade = sum(len(ganhos) for ganhos in dias)
    if quantidade == 0:
        return float("nan")
    return float(sum(float(np.sum(ganhos)) for ganhos in dias) / quantidade)


def intervalo_bootstrap(
    dias: Sequence[np.ndarray], reamostras: int = REAMOSTRAS, semente: int = SEMENTE
) -> tuple[float, float]:
    """Intervalo de 95% do ganho médio por operação, reamostrando dias inteiros com reposição."""
    somas = np.array([float(np.sum(ganhos)) for ganhos in dias])
    quantidades = np.array([len(ganhos) for ganhos in dias], dtype=float)
    sorteio = np.random.default_rng(semente).integers(
        0, len(dias), size=(reamostras, len(dias))
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        medias = somas[sorteio].sum(axis=1) / quantidades[sorteio].sum(axis=1)
    inferior, superior = np.nanpercentile(medias, PERCENTIS_DO_INTERVALO)
    return float(inferior), float(superior)


def dividir(pregoes: Sequence[str]) -> tuple[list[str], list[str]]:
    """Desenvolvimento (a primeira metade, arredondada para baixo) e validação, em ordem de data."""
    ordenados = sorted(pregoes)
    metade = len(ordenados) // 2
    return ordenados[:metade], ordenados[metade:]


def veredito(
    ganhos: dict[str, dict[str, list[np.ndarray]]],
    empate_em_pontos: float,
    ordem: Sequence[str] | None = None,
) -> dict[str, object]:
    """Escolhe no desenvolvimento a variante de maior ganho médio e decide só com ela na validação.

    `ordem` é a lista pré-registrada das variantes, que desempata; sem ela, as 8 da fase 1.
    """
    medias = {
        nome: {metade: media_por_operacao(dias) for metade, dias in por_metade.items()}
        for nome, por_metade in ganhos.items()
    }
    if ordem is None:
        ordem = [variante.nome for variante in VARIANTES]

    def chave(nome: str) -> float:
        media = medias[nome]["desenvolvimento"]
        return media if np.isfinite(media) else -np.inf

    escolhida = max(ordem, key=chave)  # empate: a primeira da lista
    inferior, superior = intervalo_bootstrap(ganhos[escolhida]["validacao"])
    return {
        "escolhida": escolhida,
        "media_na_validacao": medias[escolhida]["validacao"],
        "intervalo_95": [inferior, superior],
        "empate_em_pontos": empate_em_pontos,
        "decisao": "APROVA" if inferior > empate_em_pontos else "REPROVA",
        "medias": medias,
    }


# --- a rodada ---
def _negocios_do_dia(caminho_zip: Path, dia: Dia) -> pd.DataFrame:
    pedacos = [
        pedaco[pedaco["simbolo"] == dia.simbolo] for pedaco in ler_negocios(caminho_zip)
    ]
    return limpar_negocios(
        pd.concat(pedacos, ignore_index=True), dia.simbolo, pd.Timestamp(dia.pregao)
    )


def _conferir_selos(pasta_do_selo: Path) -> None:
    for dia in DIAS:
        simbolo, selo = contrato_principal(
            pd.read_parquet(pasta_do_selo / f"{dia.pregao}.parquet")
        )
        if (simbolo, selo) != (dia.simbolo, dia.selo):
            raise ArquivoDiferenteError(
                f"{dia.pregao}: o selo diz {simbolo} {selo}; o pré-registro fechou {dia.simbolo} {dia.selo}"
            )


def medir(pasta_dos_negocios: Path, pasta_do_selo: Path) -> dict[str, object]:
    """A tentativa inteira: confere tudo, mede M1, M2 e M3 e aplica o critério."""
    if sha256_do_pre_registro() != SHA256_DO_PRE_REGISTRO:
        raise ArquivoDiferenteError(
            "o pré-registro mudou depois de fechado: a rodada não mede"
        )
    _conferir_selos(pasta_do_selo)
    por_dia: dict[str, dict[str, object]] = {}
    ganhos_por_dia: dict[str, dict[str, np.ndarray]] = {}
    tabelas_de_variacao = []
    for dia in DIAS_QUE_ENTRAM:
        caminho = pasta_dos_negocios / f"{dia.sha256}.zip"
        conferir_arquivo(caminho, dia.pregao, dia.sha256)
        negocios = _negocios_do_dia(caminho, dia)
        pregao = pd.Timestamp(dia.pregao)
        precos_da_janela = na_janela(negocios, pregao)["preco"].to_numpy(dtype=float)
        grade = grade_de_precos(negocios, pregao)
        por_dia[dia.pregao] = {
            "simbolo": dia.simbolo,
            "negocios_na_janela": len(precos_da_janela),
            "spread_de_roll": spread_de_roll(precos_da_janela),
            "fracao_de_um_tick": fracao_de_um_tick(precos_da_janela),
        }
        ganhos_por_dia[dia.pregao] = {
            variante.nome: ganhos_da_regra(grade, variante.h, variante.direcao)
            for variante in VARIANTES
        }
        tabelas_de_variacao += [variacoes(grade, h) for h in HORIZONTES_EM_MINUTOS]
        print(f"{dia.pregao}: {len(precos_da_janela)} negócios na janela", flush=True)
    spread = float(np.median([float(d["spread_de_roll"]) for d in por_dia.values()]))  # type: ignore[arg-type]
    limite = empate(spread)
    desenvolvimento, validacao = dividir(list(ganhos_por_dia))
    ganhos = {
        variante.nome: {
            "desenvolvimento": [
                ganhos_por_dia[p][variante.nome] for p in desenvolvimento
            ],
            "validacao": [ganhos_por_dia[p][variante.nome] for p in validacao],
        }
        for variante in VARIANTES
    }
    todas = pd.concat(tabelas_de_variacao, ignore_index=True)
    teto = (
        todas.assign(absoluta=todas["variacao"].abs()).groupby("h")["absoluta"].mean()
    )
    return {
        "tentativa": 1,
        "sha256_do_pre_registro": SHA256_DO_PRE_REGISTRO,
        "dias": por_dia,
        "desenvolvimento": desenvolvimento,
        "validacao": validacao,
        "spread_mediano_em_pontos": spread,
        "operacoes": {
            nome: {
                metade: int(sum(len(g) for g in dias))
                for metade, dias in por_metade.items()
            }
            for nome, por_metade in ganhos.items()
        },
        "veredito": veredito(ganhos, limite),
        "teto_media_abs_por_h": {int(h): float(v) for h, v in teto.items()},
        "movimento_por_faixa": resumo_por_faixa(todas).to_dict(orient="records"),
    }


def _ler_argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    leitor = argparse.ArgumentParser(
        description="Fase 1 do scalp no mini índice: mede se regras simples passam do custo."
    )
    leitor.add_argument(
        "--negocios", type=Path, required=True, help="pasta com os zips <sha256>.zip"
    )
    leitor.add_argument(
        "--selo", type=Path, required=True, help="pasta com os selos <dia>.parquet"
    )
    leitor.add_argument(
        "--saida", type=Path, required=True, help="pasta do resultado (fora do Git)"
    )
    return leitor.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    argumentos = _ler_argumentos(argv)
    resultado = medir(argumentos.negocios, argumentos.selo)
    argumentos.saida.mkdir(parents=True, exist_ok=True)
    caminho = argumentos.saida / "tentativa-1.json"
    caminho.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, default=float),
        encoding="utf-8",
    )
    decisao = resultado["veredito"]
    print(
        json.dumps(
            {k: v for k, v in decisao.items() if k != "medias"}, ensure_ascii=False
        )
    )  # type: ignore[union-attr]
    print(f"resultado em {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
