"""Fase 1b do scalp no mini índice (WIN): o fluxo dos últimos minutos prevê o preço? Só leitura.

Implementa o `docs/pre-registro-scalp-win-fase1b.md` (versão 1.0, escrita antes da medida): os mesmos
23 pregões, a mesma limpeza e a mesma grade de preços da fase 1 (`trader.scalp_win`), com dois sinais
novos tirados do mesmo arquivo grátis da B3: o fluxo do agressor pela regra do tick (F) e a compra
líquida das corretoras de lote pequeno (C). Decide APROVA ou REPROVA pelo critério da seção 4. Nada
aqui fala com corretora ou plataforma.

Uso (uma vez; toda execução é uma tentativa):

    python -m trader.scalp_win_1b --negocios <pasta dos zips> --selo <pasta dos selos> --saida <pasta>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# A leitura em pedaços e a montagem das colunas são as da base; aqui só se acrescentam as corretoras.
from base.intradiario_b3 import (
    COLUNAS_LIDAS,
    LINHAS_POR_PEDACO,
    _ler_em_pedacos,
    _negocios_do_pedaco,
)
from trader import scalp_win as sw
from trader.scalp_win import ganhos_do_sinal

CAMINHO_DO_PRE_REGISTRO = sw.RAIZ / "docs" / "pre-registro-scalp-win-fase1b.md"
# SHA-256 do texto vigente (quebras de linha normalizadas para \n), versão 1.0 de 29/10/2026.
SHA256_DO_PRE_REGISTRO = (
    "d71a7c7c6a88a11e44bc07a58370a4af00e496911d7e281414bb264dd0e23d87"
)
TENTATIVA = 2

EMPATE_EM_PONTOS = (
    sw.PISO_DO_EMPATE_EM_PONTOS
)  # fixo (seção 4): a fase 1 mediu 7,6, abaixo do piso
COLUNAS_DAS_CORRETORAS = {
    "CodigoParticipanteComprador": "str",
    "CodigoParticipanteVendedor": "str",
}
PARTICIPACAO_MINIMA = (
    0.01  # do volume do WIN, para a corretora contar na escolha do grupo
)
UM_MINUTO = pd.Timedelta(minutes=1)
MINUTOS_NA_JANELA = int((sw.FIM_DA_JANELA - sw.INICIO_DA_JANELA) / UM_MINUTO)

AGRESSOR = "F"
LOTE_PEQUENO = "C"
SINAIS = (AGRESSOR, LOTE_PEQUENO)


@dataclass(frozen=True)
class Variante:
    """Uma das 16 regras pré-registradas (seção 3): sinal, horizonte e direção."""

    sinal: str
    h: int
    direcao: str

    @property
    def nome(self) -> str:
        return f"{self.sinal}_{self.direcao}_{self.h}min"


# a ordem da lista desempata (seção 4): F antes de C, h crescente, momento antes de reversão
VARIANTES: tuple[Variante, ...] = tuple(
    Variante(sinal, h, direcao)
    for sinal in SINAIS
    for h in sw.HORIZONTES_EM_MINUTOS
    for direcao in sw.DIRECOES
)


@dataclass(frozen=True)
class Fluxo:
    """O fluxo de um pregão, minuto a minuto da janela (minuto m = [09h15 + m, 09h15 + m + 1))."""

    agressor: np.ndarray  # soma de (sinal do tick × quantidade)
    corretoras: (
        pd.DataFrame
    )  # compra líquida: linhas são os minutos, colunas as corretoras
    lotes: (
        pd.DataFrame
    )  # por corretora: volume (comprado + vendido) e lados (negócios em que entrou)


# --- leitura ---
def ler_negocios_com_corretoras(
    caminho_zip: Path, linhas_por_pedaco: int = LINHAS_POR_PEDACO
) -> Iterator[pd.DataFrame]:
    """Os negócios do arquivo da B3, como `base.intradiario_b3.ler_negocios`, mais comprador e vendedor.

    Os códigos das corretoras vêm como texto, do jeito que estão no arquivo.
    """
    colunas = {**COLUNAS_LIDAS, **COLUNAS_DAS_CORRETORAS}
    for pedaco in _ler_em_pedacos(caminho_zip, colunas, linhas_por_pedaco):
        yield _negocios_do_pedaco(pedaco).assign(
            comprador=pedaco["CodigoParticipanteComprador"],
            vendedor=pedaco["CodigoParticipanteVendedor"],
        )


# --- sinais ---
def sinais_do_tick(precos: np.ndarray) -> np.ndarray:
    """Regra do tick: +1 se o negócio subiu o preço, −1 se desceu; sem mudança, herda o anterior.

    O primeiro negócio do dia, e os que vêm antes de qualquer mudança, ficam com 0.
    """
    mudanca = np.sign(np.diff(np.asarray(precos, dtype=float), prepend=np.nan))
    herdado = pd.Series(mudanca).replace(0.0, np.nan).ffill().fillna(0.0)
    return herdado.to_numpy(dtype=int)


def fluxo_por_minuto(negocios: pd.DataFrame, pregao: pd.Timestamp) -> Fluxo:
    """Fluxo do agressor, compra líquida e lotes das corretoras, minuto a minuto da janela.

    O sinal do tick usa todos os negócios do pregão (os de antes das 09h15 só servem de referência);
    as somas usam só os da janela.
    """
    ordenados = negocios.sort_values(["instante", "identificador"], kind="stable")
    sinal = sinais_do_tick(ordenados["preco"].to_numpy(dtype=float))
    inicio = sw._horario(pregao, sw.INICIO_DA_JANELA)
    fim = sw._horario(pregao, sw.FIM_DA_JANELA)
    dentro = (
        (ordenados["instante"] >= inicio) & (ordenados["instante"] < fim)
    ).to_numpy()
    janela = ordenados[dentro]
    minuto = ((janela["instante"] - inicio) // UM_MINUTO).to_numpy(dtype=int)
    quantidade = janela["quantidade"].to_numpy(dtype=float)
    agressor = np.bincount(
        minuto, weights=sinal[dentro] * quantidade, minlength=MINUTOS_NA_JANELA
    )
    lados = pd.DataFrame(
        {
            "minuto": np.concatenate([minuto, minuto]),
            "corretora": np.concatenate(
                [janela["comprador"].to_numpy(), janela["vendedor"].to_numpy()]
            ),
            "liquido": np.concatenate([quantidade, -quantidade]),
            "volume": np.concatenate([quantidade, quantidade]),
        }
    )
    corretoras = (
        lados.pivot_table(
            index="minuto", columns="corretora", values="liquido", aggfunc="sum"
        )
        .reindex(range(MINUTOS_NA_JANELA))
        .fillna(0.0)
    )
    lotes = lados.groupby("corretora", as_index=False).agg(
        volume=("volume", "sum"), lados=("volume", "size")
    )
    return Fluxo(agressor=agressor, corretoras=corretoras, lotes=lotes)


def fluxo_do_grupo(fluxo: Fluxo, grupo: set[str]) -> np.ndarray:
    """Compra líquida do grupo por minuto; negócio entre duas corretoras do grupo se anula."""
    colunas = [
        corretora for corretora in fluxo.corretoras.columns if corretora in grupo
    ]
    if not colunas:
        return np.zeros(len(fluxo.corretoras))
    return fluxo.corretoras[colunas].sum(axis=1).to_numpy(dtype=float)


def grupo_de_lote_pequeno(lotes_do_desenvolvimento: Sequence[pd.DataFrame]) -> set[str]:
    """As corretoras com ao menos 1% do volume e lote médio até a mediana delas (seção 3, C).

    Recebe os lotes só dos pregões do desenvolvimento, somados antes de calcular.
    """
    soma = (
        pd.concat(lotes_do_desenvolvimento, ignore_index=True)
        .groupby("corretora")[["volume", "lados"]]
        .sum()
    )
    # somando comprado e vendido de todas, cada negócio conta duas vezes: é o 2 × volume da seção 3
    participacao = soma["volume"] / soma["volume"].sum()
    grandes = soma[participacao >= PARTICIPACAO_MINIMA]
    lote_medio = grandes["volume"] / grandes["lados"]
    return set(lote_medio[lote_medio <= lote_medio.median()].index)


def soma_da_janela(por_minuto: np.ndarray, h: int) -> np.ndarray:
    """Para cada minuto k da grade (0 a 510), a soma dos minutos [k − h, k); vazio quando k < h."""
    acumulado = np.concatenate([[0.0], np.cumsum(np.asarray(por_minuto, dtype=float))])
    janela = np.full(len(acumulado), np.nan)
    janela[h:] = acumulado[h:] - acumulado[:-h]
    return janela


def ganhos_do_dia(
    grade: pd.Series, fluxo: Fluxo, grupo: set[str]
) -> dict[str, np.ndarray]:
    """O ganho de cada operação das 16 variantes num pregão."""
    por_minuto = {
        AGRESSOR: fluxo.agressor,
        LOTE_PEQUENO: fluxo_do_grupo(fluxo, grupo),
    }
    return {
        variante.nome: ganhos_do_sinal(
            grade,
            soma_da_janela(por_minuto[variante.sinal], variante.h),
            variante.h,
            variante.direcao,
        )
        for variante in VARIANTES
    }


# --- a rodada ---
def _negocios_do_dia(caminho_zip: Path, dia: sw.Dia) -> pd.DataFrame:
    pedacos = [
        pedaco[pedaco["simbolo"] == dia.simbolo]
        for pedaco in ler_negocios_com_corretoras(caminho_zip)
    ]
    return sw.limpar_negocios(
        pd.concat(pedacos, ignore_index=True), dia.simbolo, pd.Timestamp(dia.pregao)
    )


def _conferir_pre_registros() -> None:
    if sw.sha256_do_pre_registro(CAMINHO_DO_PRE_REGISTRO) != SHA256_DO_PRE_REGISTRO:
        raise sw.ArquivoDiferenteError(
            "o pré-registro da 1b mudou depois de fechado: a rodada não mede"
        )
    # os dias, os hashes e os selos vêm da tabela da fase 1
    if sw.sha256_do_pre_registro() != sw.SHA256_DO_PRE_REGISTRO:
        raise sw.ArquivoDiferenteError(
            "o pré-registro da fase 1 mudou depois de fechado: a rodada não mede"
        )


def medir(pasta_dos_negocios: Path, pasta_do_selo: Path) -> dict[str, object]:
    """A tentativa inteira: confere tudo, monta o fluxo, escolhe o grupo e aplica o critério."""
    _conferir_pre_registros()
    sw._conferir_selos(pasta_do_selo)
    grades: dict[str, pd.Series] = {}
    fluxos: dict[str, Fluxo] = {}
    por_dia: dict[str, dict[str, object]] = {}
    for dia in sw.DIAS_QUE_ENTRAM:
        caminho = pasta_dos_negocios / f"{dia.sha256}.zip"
        sw.conferir_arquivo(caminho, dia.pregao, dia.sha256)
        negocios = _negocios_do_dia(caminho, dia)
        pregao = pd.Timestamp(dia.pregao)
        grades[dia.pregao] = sw.grade_de_precos(negocios, pregao)
        fluxos[dia.pregao] = fluxo_por_minuto(negocios, pregao)
        janela = sw.na_janela(negocios, pregao)
        por_dia[dia.pregao] = {
            "negocios_na_janela": len(janela),
            "sem_codigo_de_corretora": int(
                (janela["comprador"].isna() | janela["vendedor"].isna()).sum()
            ),
        }
        print(f"{dia.pregao}: {len(janela)} negócios na janela", flush=True)
    desenvolvimento, validacao = sw.dividir(list(grades))
    grupo = grupo_de_lote_pequeno([fluxos[p].lotes for p in desenvolvimento])
    ganhos_por_dia = {
        pregao: ganhos_do_dia(grades[pregao], fluxos[pregao], grupo)
        for pregao in grades
    }
    ganhos = {
        variante.nome: {
            "desenvolvimento": [
                ganhos_por_dia[p][variante.nome] for p in desenvolvimento
            ],
            "validacao": [ganhos_por_dia[p][variante.nome] for p in validacao],
        }
        for variante in VARIANTES
    }
    volume_do_desenvolvimento = (
        pd.concat([fluxos[p].lotes for p in desenvolvimento], ignore_index=True)
        .groupby("corretora")["volume"]
        .sum()
    )
    return {
        "tentativa": TENTATIVA,
        "sha256_do_pre_registro": SHA256_DO_PRE_REGISTRO,
        "sha256_do_pre_registro_da_fase1": sw.SHA256_DO_PRE_REGISTRO,
        "dias": por_dia,
        "desenvolvimento": desenvolvimento,
        "validacao": validacao,
        "grupo_de_lote_pequeno": {
            "corretoras": sorted(grupo),
            "participacao_no_volume_do_desenvolvimento": float(
                volume_do_desenvolvimento[sorted(grupo)].sum()
                / volume_do_desenvolvimento.sum()
            ),
            "corretoras_no_desenvolvimento": len(volume_do_desenvolvimento),
        },
        "operacoes": {
            nome: {
                metade: int(sum(len(g) for g in dias))
                for metade, dias in por_metade.items()
            }
            for nome, por_metade in ganhos.items()
        },
        "veredito": sw.veredito(
            ganhos, EMPATE_EM_PONTOS, ordem=[variante.nome for variante in VARIANTES]
        ),
    }


def _ler_argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    leitor = argparse.ArgumentParser(
        description="Fase 1b do scalp no mini índice: o fluxo prevê o preço?"
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
    caminho = argumentos.saida / f"tentativa-{TENTATIVA}.json"
    caminho.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, default=float),
        encoding="utf-8",
    )
    decisao: dict[str, object] = resultado["veredito"]  # type: ignore[assignment]
    print(
        json.dumps(
            {k: v for k, v in decisao.items() if k != "medias"}, ensure_ascii=False
        )
    )
    print(f"resultado em {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
