"""Trava do período lacrado do modelo C-1 (pré-registro v2, seção 4; ADR 0006).

- **Desenvolvimento:** de 01/08/2018 até o último dia cujo alvo (D+1 a D+30) termina antes do
  lacrado: 12/09/2023. O alvo de um dia mais tarde usaria preço do lacrado.
- **Lacrado:** 13/10/2023 a 12/10/2026, avaliado **uma única vez**, só por uma execução aprovada no
  desenvolvimento, e só se o texto do pré-registro não mudou desde que a trava foi criada.
"""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from base.cripto.c1.alvo import DIAS_DO_ALVO
from base.cripto.c1.registro import Registro

INICIO_DO_DESENVOLVIMENTO = date(2018, 8, 1)
INICIO_DO_LACRADO = date(2023, 10, 13)
FIM_DO_LACRADO = date(2026, 10, 12)
# o último dia cujo alvo ainda termina antes do lacrado
FIM_DO_DESENVOLVIMENTO = INICIO_DO_LACRADO - timedelta(days=DIAS_DO_ALVO + 1)
ARQUIVO_DO_HASH = "pre_registro.sha256"
ARQUIVO_DA_ABERTURA = "lacrado_aberto.json"


class LacradoVazandoError(ValueError):
    """Um alvo do desenvolvimento usaria preço do período lacrado."""


class LacradoJaAbertoError(RuntimeError):
    """O lacrado já foi avaliado: não existe segunda chance."""


class CandidatoNaoAprovadoError(RuntimeError):
    """Só uma execução aprovada no desenvolvimento pode abrir o lacrado."""


class PreRegistroAlteradoError(RuntimeError):
    """O texto do pré-registro mudou depois que a trava foi criada."""


def exigir_sem_lacrado(classes: pd.Series) -> None:
    """Para com erro se algum dia com faixa conhecida tem o alvo dentro do lacrado."""
    com_classe = classes.dropna()
    if not com_classe.empty and max(com_classe.index) > FIM_DO_DESENVOLVIMENTO:
        raise LacradoVazandoError(
            f"Há alvo depois de {FIM_DO_DESENVOLVIMENTO:%d/%m/%Y}: ele usaria preço do lacrado."
        )


def cortar_desenvolvimento(
    quadro: pd.DataFrame, classes: pd.Series
) -> tuple[pd.DataFrame, pd.Series]:
    """Só os dias do desenvolvimento (as entradas já foram montadas com o passado de cada dia)."""
    dias = [
        d
        for d in quadro.index
        if INICIO_DO_DESENVOLVIMENTO <= d <= FIM_DO_DESENVOLVIMENTO
    ]
    cortadas = classes.loc[dias]
    exigir_sem_lacrado(cortadas)
    return quadro.loc[dias], cortadas


class Lacre:
    """A trava, numa pasta fora do Git: o hash do pré-registro e o registro da única abertura."""

    def __init__(self, pasta: Path, pre_registro: Path) -> None:
        self.pasta = pasta
        self.pre_registro = pre_registro
        pasta.mkdir(parents=True, exist_ok=True)
        if not (pasta / ARQUIVO_DO_HASH).exists():
            (pasta / ARQUIVO_DO_HASH).write_text(
                self._hash_do_pre_registro(), encoding="utf-8"
            )

    def abrir(self, registro: Registro, tentativa: int) -> None:
        """Abre o lacrado para a execução aprovada; só uma vez na vida do pré-registro."""
        if self._hash_do_pre_registro() != (self.pasta / ARQUIVO_DO_HASH).read_text(
            encoding="utf-8"
        ):
            raise PreRegistroAlteradoError(
                "O pré-registro mudou depois que a trava foi criada."
            )
        if not registro.aprovada(tentativa):
            raise CandidatoNaoAprovadoError(
                f"A execução {tentativa} não passou no desenvolvimento."
            )
        abertura = self.pasta / ARQUIVO_DA_ABERTURA
        if abertura.exists():
            raise LacradoJaAbertoError(
                f"O lacrado já foi aberto: {abertura.read_text(encoding='utf-8')}"
            )
        abertura.write_text(
            json.dumps(
                {"tentativa": tentativa, "aberto_em": datetime.now(UTC).isoformat()}
            ),
            encoding="utf-8",
        )

    def _hash_do_pre_registro(self) -> str:
        return hashlib.sha256(self.pre_registro.read_bytes()).hexdigest()
