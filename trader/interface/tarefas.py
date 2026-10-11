"""Tarefas longas do painel (baixar dados, rodar baselines) em processos separados.

Cada tarefa é um dos comandos que já existem (`python -m trader.baixar_historico` etc.), rodado
por `QProcess`: a janela não congela, a última linha impressa vira o texto de progresso e dá
para cancelar. Uma tarefa por vez (botões ficam desabilitados enquanto uma roda).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from trader.interface.fontes import RAIZ


@dataclass(frozen=True)
class Comando:
    chave: str
    titulo: str
    modulo: str
    argumentos: tuple[str, ...] = ()
    descricao: str = ""


COMANDOS = {
    c.chave: c
    for c in (
        Comando(
            "historico",
            "Baixar histórico",
            "trader.baixar_historico",
            descricao="MT5 (forex e metais) e yfinance (B3, commodities, cripto, índices). "
            "O MetaTrader 5 precisa estar aberto numa conta demo para a parte do MT5.",
        ),
        Comando(
            "historico_yf",
            "Baixar só yfinance",
            "trader.baixar_historico",
            ("--so", "yfinance"),
            descricao="Só as séries do yfinance (não precisa do MetaTrader 5).",
        ),
        Comando(
            "b3",
            "Atualizar boletim da B3",
            "trader.atualizar_b3",
            descricao="Futuros da B3 (boi, café, mini índice, mini dólar...). A B3 só guarda "
            "~3 semanas: rode todo dia útil.",
        ),
        Comando(
            "juros",
            "Atualizar juros",
            "trader.atualizar_juros",
            descricao="Taxas básicas dos bancos centrais (BIS).",
        ),
        Comando(
            "baselines",
            "Rodar baselines",
            "trader.rodar_baselines",
            descricao="B0, B1 e B2 no desenvolvimento. Mesma especificação não conta como tentativa nova.",
        ),
    )
}


class Tarefa(QObject):
    progresso = Signal(str)  # última linha impressa
    terminou = Signal(bool, str)  # (deu certo, resumo)

    def __init__(self, comando: Comando, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.comando = comando
        self.processo = QProcess(self)
        self.processo.setWorkingDirectory(str(RAIZ))
        ambiente = QProcessEnvironment.systemEnvironment()
        ambiente.insert("PYTHONPATH", str(RAIZ))
        ambiente.insert("PYTHONUNBUFFERED", "1")
        ambiente.insert("PYTHONIOENCODING", "utf-8")
        self.processo.setProcessEnvironment(ambiente)
        self.processo.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.processo.readyReadStandardOutput.connect(self._ler)
        self.processo.finished.connect(self._fim)
        self.processo.errorOccurred.connect(self._erro)
        self.linhas: list[str] = []
        self.cancelada = False

    def iniciar(self) -> None:
        self.processo.start(
            sys.executable, ["-m", self.comando.modulo, *self.comando.argumentos]
        )

    def cancelar(self) -> None:
        self.cancelada = True
        self.processo.kill()

    @property
    def rodando(self) -> bool:
        return self.processo.state() != QProcess.ProcessState.NotRunning

    def _ler(self) -> None:
        texto = bytes(self.processo.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        novas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
        if novas:
            self.linhas.extend(novas)
            self.progresso.emit(novas[-1])

    def _fim(self, codigo: int, _status: object) -> None:
        if self.cancelada:
            self.terminou.emit(False, f"{self.comando.titulo}: cancelado.")
            return
        ultima = self.linhas[-1] if self.linhas else ""
        if codigo == 0:
            self.terminou.emit(True, f"{self.comando.titulo}: concluído. {ultima}")
        else:
            self.terminou.emit(False, f"{self.comando.titulo} falhou. {ultima}")

    def _erro(self, _erro: object) -> None:
        if (
            not self.cancelada
            and self.processo.state() == QProcess.ProcessState.NotRunning
        ):
            self.terminou.emit(
                False,
                f"{self.comando.titulo}: não consegui iniciar ({os.path.basename(sys.executable)}).",
            )
