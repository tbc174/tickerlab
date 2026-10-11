"""Holdout lacrado da M2: o trecho final do histórico que só pode ser pontuado UMA vez.

Implementa a seção 2 e a seção 7 do critério aprovado (`docs/pre-registro-m2-v0.1.md`):

    desenvolvimento : até 08/09/2023        (tudo o que se projeta e se escolhe usa só isto)
    expurgo         : 09/09/2023 a 09/10/2023 (~21 pregões; descartado, para os rótulos não vazarem)
    holdout         : 10/10/2023 a 09/10/2026 (pontuado uma vez, por um único candidato)

Regras que o código faz cumprir:
- `recortar_desenvolvimento` é o único jeito de pegar dados para pesquisar; calcule rótulos DEPOIS
  de recortar, para nenhum rótulo olhar além de 08/09/2023;
- `pontuar` confere que o texto do critério não foi alterado, que o candidato passou nos critérios
  A1 a A10 no desenvolvimento, **cria o lacre antes de avaliar** (uma falha no meio também queima o
  holdout, de propósito) e recusa qualquer segunda pontuação;
- `destrancar` existe, mas exige uma frase de confirmação e **invalida** o holdout: depois disso o
  resultado final só vale com dados novos (M3).

Ensaie a função de avaliação com dados de desenvolvimento antes de chamar `pontuar`.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trader import dados as dados_do_trader
from trader.registro import PASTA_DA_PESQUISA, RAIZ, Registro

FIM_DO_DESENVOLVIMENTO = pd.Timestamp("2023-09-08")
# Decisão do Tiago (11/10/2026), depois das primeiras baselines: a avaliação começa em 03/01/2000
# para todos. Antes disso quase só há índices à vista (S&P desde 1927, Nasdaq desde 1971), que
# dominavam a carteira e têm autocorrelação falsa por preço defasado; nem eram negociáveis (não
# havia futuro de índice antes de 1982). Os sinais podem usar o histórico anterior para aquecer.
INICIO_DA_AVALIACAO = pd.Timestamp("2000-01-03")
INICIO_DO_HOLDOUT = pd.Timestamp("2023-10-10")
FIM_DO_HOLDOUT = pd.Timestamp("2026-10-09")
CAMINHO_DO_CRITERIO = RAIZ / "docs" / "pre-registro-m2-v0.1.md"
# SHA-256 do texto aprovado pelo Tiago em 11/10/2026 (com quebras de linha normalizadas para \n)
HASH_DO_CRITERIO = "b8074c37ae92cb4542965d1c2285f3d31f9751f5f3cb6758497d7baa07f32e98"
FRASE_DE_CONFIRMACAO = "INVALIDAR HOLDOUT"
NOME_DO_LACRE = "holdout.lock"
NOME_DA_INVALIDACAO = "holdout.invalidado.json"


class HoldoutVazandoError(ValueError):
    """Dados do holdout (ou do expurgo) apareceram onde só cabe desenvolvimento."""


class HoldoutJaUsadoError(RuntimeError):
    """O holdout já foi pontuado (ou queimado por uma falha). Só um humano pode destrancar."""


class CriterioAlteradoError(RuntimeError):
    """O texto do critério não é o que o Tiago aprovou."""


class CandidatoNaoAprovadoError(RuntimeError):
    """O candidato não passou em A1 a A10 no desenvolvimento, então não pode ir ao holdout."""


def recortar_desenvolvimento[T: (pd.DataFrame, pd.Series)](dados: T) -> T:
    """Só a parte de desenvolvimento (até 08/09/2023). Use SEMPRE antes de pesquisar."""
    if not isinstance(dados.index, pd.DatetimeIndex):
        raise TypeError("Os dados precisam ter índice de datas.")
    return dados.loc[dados.index <= FIM_DO_DESENVOLVIMENTO]


def carregar_desenvolvimento(
    arquivo: str, pasta: Path = dados_do_trader.PASTA_PADRAO
) -> pd.DataFrame:
    """O caminho padrão para pesquisar: carrega a série do disco já recortada até 08/09/2023.

    `arquivo` é o nome do Parquet sem o `_D1` (o campo `arquivo` de `trader/universo.py`).
    Falha se a série não foi baixada.
    """
    candles = dados_do_trader.carregar(arquivo, "D1", pasta)
    if candles is None:
        raise FileNotFoundError(f"A série {arquivo} ainda não foi baixada.")
    return recortar_desenvolvimento(candles)


def exigir_sem_holdout(dados: pd.DataFrame | pd.Series) -> None:
    """Levanta erro se houver qualquer data depois do fim do desenvolvimento."""
    if len(dados) and dados.index.max() > FIM_DO_DESENVOLVIMENTO:
        raise HoldoutVazandoError(
            f"Há dados de {dados.index.max():%d/%m/%Y}, depois do fim do desenvolvimento "
            f"({FIM_DO_DESENVOLVIMENTO:%d/%m/%Y}). Use recortar_desenvolvimento()."
        )


def hash_do_texto(caminho: Path) -> str:
    """SHA-256 do arquivo, ignorando diferença de quebra de linha (Windows x Linux)."""
    texto = caminho.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(texto).hexdigest()


def _conferir_criterio(caminho: Path, esperado: str) -> None:
    if not caminho.exists():
        raise CriterioAlteradoError(f"Não achei o critério aprovado em {caminho}.")
    if hash_do_texto(caminho) != esperado:
        raise CriterioAlteradoError(
            "O texto do critério mudou depois da aprovação. Mudar é permitido, mas vira a "
            "v0.2 (com data e +25 tentativas); o holdout não pode ser pontuado com ele alterado."
        )


def holdout_valido(pasta: Path = PASTA_DA_PESQUISA) -> bool:
    """False depois que alguém destrancou o holdout."""
    return not (pasta / NOME_DA_INVALIDACAO).exists()


def pontuar(
    registro: Registro,
    tentativa_id: int,
    dados: dict[str, pd.DataFrame],
    avaliar: Callable[[dict[str, pd.DataFrame]], dict],
    pasta: Path = PASTA_DA_PESQUISA,
    criterio: Path = CAMINHO_DO_CRITERIO,
    hash_esperado: str = HASH_DO_CRITERIO,
) -> dict:
    """Pontua o candidato no holdout. Só funciona uma vez. Devolve o que `avaliar` devolver."""
    _conferir_criterio(criterio, hash_esperado)
    tentativa = registro.obter(tentativa_id)
    if tentativa["fase"] != "desenvolvimento":
        raise CandidatoNaoAprovadoError(
            "Só candidatos do desenvolvimento vão ao holdout."
        )
    if not (tentativa["resultado"] or {}).get("aprovado_em_A"):
        raise CandidatoNaoAprovadoError(
            f"A tentativa {tentativa_id} não tem `aprovado_em_A` verdadeiro no registro."
        )

    lacre = pasta / NOME_DO_LACRE
    pasta.mkdir(parents=True, exist_ok=True)
    conteudo = {
        "tentativa_id": tentativa_id,
        "hash_da_especificacao": tentativa["hash"],
        "familia": tentativa["familia"],
        "nome": tentativa["nome"],
        "commit_do_codigo": tentativa["commit_do_codigo"],
        "hash_do_criterio": hash_esperado,
        "lacrado_em": datetime.now(UTC).isoformat(),
    }
    try:
        # modo exclusivo: se dois processos tentarem, só um cria o arquivo
        descritor = os.open(lacre, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise HoldoutJaUsadoError(
            f"O holdout já foi usado ({lacre.read_text(encoding='utf-8')[:300]})."
        ) from None
    with os.fdopen(descritor, "w", encoding="utf-8") as f:
        json.dump(conteudo, f, ensure_ascii=False, indent=2)

    recortados = {
        nome: tabela.loc[
            (tabela.index >= INICIO_DO_HOLDOUT) & (tabela.index <= FIM_DO_HOLDOUT)
        ]
        for nome, tabela in dados.items()
    }
    recortados = {nome: t for nome, t in recortados.items() if len(t)}
    try:
        resultado = avaliar(recortados)
    except Exception as erro:
        conteudo["avaliacao_falhou"] = f"{type(erro).__name__}: {erro}"
        lacre.write_text(
            json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        raise

    resultado = {**resultado, "valido": holdout_valido(pasta)}
    id_holdout = registro.registrar(
        tentativa["familia"], tentativa["nome"], tentativa["spec"], fase="holdout"
    )
    registro.salvar_resultado(id_holdout, resultado)
    conteudo["concluido_em"] = datetime.now(UTC).isoformat()
    lacre.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return resultado


def destrancar(motivo: str, confirmacao: str, pasta: Path = PASTA_DA_PESQUISA) -> Path:
    """Libera o lacre para uma nova pontuação e **invalida** o holdout. Só para uso humano.

    Depois disto o resultado do holdout não vale como prova; o teste final passa a ser o paper
    trading em dados novos (M3). Exige a frase `INVALIDAR HOLDOUT` e um motivo escrito.
    """
    if confirmacao != FRASE_DE_CONFIRMACAO:
        raise PermissionError(
            f"Para destrancar, confirme com a frase {FRASE_DE_CONFIRMACAO!r}."
        )
    if not motivo.strip():
        raise ValueError("Escreva o motivo.")
    lacre = pasta / NOME_DO_LACRE
    if not lacre.exists():
        raise FileNotFoundError("O holdout não está lacrado.")
    momento = datetime.now(UTC)
    arquivado = pasta / f"{NOME_DO_LACRE}.invalidado-{momento:%Y%m%dT%H%M%S}"
    lacre.rename(arquivado)
    (pasta / NOME_DA_INVALIDACAO).write_text(
        json.dumps(
            {
                "motivo": motivo,
                "invalidado_em": momento.isoformat(),
                "lacre": arquivado.name,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return arquivado
