"""Abre o painel do trader: `python -m trader.interface`."""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from trader.interface import tema
from trader.interface.componentes import configurar_pyqtgraph
from trader.interface.janela import Janela


def criar_aplicacao(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("Trader")
    fonte = QFont(tema.FONTE)
    fonte.setPixelSize(tema.TAMANHO["corpo"])
    app.setFont(fonte)
    app.setStyleSheet(tema.folha_de_estilo())
    configurar_pyqtgraph()
    return app


def main() -> int:
    app = criar_aplicacao()
    janela = Janela()
    janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
