"""Componentes do painel: cartões, avisos, tabela formatada, gráficos (linhas, barras, velas) e toast.

Seguem o documento de design: grade de 8 px, cores por papel (`tema.CORES`), números à direita
com algarismos de largura fixa, ganho/perda com sinal e seta, estado com ícone e texto, legenda
sempre que houver 2+ séries e rótulo direto quando forem até 4, mira (crosshair) com valores.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPointF,
    QRectF,
    QSortFilterProxyModel,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPicture
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from trader.interface import tema

C, E = tema.CORES, tema.ESPACO


def configurar_pyqtgraph() -> None:
    pg.setConfigOptions(
        antialias=True, background=C["superficie"], foreground=C["texto_apagado"]
    )


def rotulo(texto: str = "", papel: str | None = None, quebra: bool = False) -> QLabel:
    r = QLabel(texto)
    if papel:
        r.setProperty("papel", papel)
    r.setWordWrap(quebra)
    return r


def fonte_tabular(tamanho: int = tema.TAMANHO["corpo"], negrito: bool = False) -> QFont:
    """Fonte com algarismos de largura fixa (as colunas de números alinham)."""
    f = QFont(tema.FONTE, tamanho)
    f.setPixelSize(tamanho)
    if negrito:
        f.setWeight(QFont.Weight.DemiBold)
    try:
        f.setFeature(QFont.Tag("tnum"), 1)
    except AttributeError:  # Qt antigo: Segoe UI já usa algarismos tabulares por padrão
        pass
    return f


# --- cartões e avisos ------------------------------------------------------------------------


class Cartao(QFrame):
    """Superfície de nível 1 com título (e "(i)" de ajuda opcional) e um corpo."""

    def __init__(
        self, titulo: str = "", ajuda: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cartao")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(E["l"], E["l"], E["l"], E["l"])
        self.layout_.setSpacing(E["s"])
        if titulo:
            linha = QHBoxLayout()
            linha.setSpacing(E["s"])
            self.titulo = rotulo(titulo, "titulo_cartao")
            linha.addWidget(self.titulo)
            if ajuda:
                info = rotulo("ⓘ", "info")
                info.setToolTip(ajuda)
                info.setCursor(Qt.CursorShape.WhatsThisCursor)
                linha.addWidget(info)
            linha.addStretch()
            self.layout_.addLayout(linha)

    def adicionar(self, widget: QWidget, esticar: int = 0) -> QWidget:
        self.layout_.addWidget(widget, esticar)
        return widget


class CartaoResumo(Cartao):
    """Número de destaque com legenda (ex.: tentativas 15 de 300)."""

    def __init__(
        self, titulo: str, ajuda: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(titulo, ajuda, parent)
        self.valor = self.adicionar(rotulo("—", "destaque"))
        self.legenda = self.adicionar(rotulo("", "secundario", quebra=True))
        self.layout_.addStretch()
        self.setMinimumWidth(200)

    def atualizar(
        self, valor: str, legenda: str = "", estado: str | None = None
    ) -> None:
        if estado:
            cor, icone = tema.ESTADOS[estado]
            self.valor.setText(f"{icone} {valor}")
            self.valor.setStyleSheet(f"color: {cor};")
        else:
            self.valor.setText(valor)
            self.valor.setStyleSheet("")
        self.legenda.setText(legenda)


class Aviso(QFrame):
    """Estado vazio ou de erro: ícone, explicação e (opcional) a ação que resolve."""

    def __init__(
        self,
        texto: str,
        estado: str | None = None,
        acao: str = "",
        ao_clicar: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("aviso")
        linha = QHBoxLayout(self)
        linha.setContentsMargins(E["l"], E["m"], E["l"], E["m"])
        linha.setSpacing(E["m"])
        if estado:
            cor, icone = tema.ESTADOS[estado]
            marca = rotulo(icone)
            marca.setStyleSheet(f"color: {cor}; font-size: 18px;")
            linha.addWidget(marca)
        self.texto = rotulo(texto, quebra=True)
        linha.addWidget(self.texto, 1)
        self.botao = None
        if acao:
            self.botao = QPushButton(acao)
            if ao_clicar:
                self.botao.clicked.connect(ao_clicar)
            linha.addWidget(self.botao)


# --- tabela ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Coluna:
    chave: str
    titulo: str
    formato: str = "texto"  # texto, int, num2, num3, pct, data, datahora, veredito, situacao, variacao


NUMERICOS = {"int", "num2", "num3", "pct", "variacao"}
VEREDITOS = {
    "aprovado": ("bom", "aprovado"),
    "reprovado": ("critico", "reprovado"),
    "régua": (None, "régua (baseline)"),
    "sem resultado": ("atencao", "sem resultado"),
}
SITUACOES = {
    "ok": ("bom", "ok"),
    "reparada": ("bom", "reparada"),
    "ok com aviso": ("atencao", "ok com aviso"),
}


def formatar(valor: object, formato: str) -> str:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "—"
    if formato == "int":
        return f"{int(valor):,}".replace(",", ".")
    if formato == "num2":
        return (
            f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
    if formato == "num3":
        return f"{float(valor):.3f}".replace(".", ",")
    if formato == "pct":
        return f"{float(valor) * 100:.1f}%".replace(".", ",")
    if formato == "variacao":
        v = float(valor)
        return f"{tema.seta(v)} {v * 100:+.2f}%".replace(".", ",")
    if formato == "data":
        return f"{pd.Timestamp(valor):%d/%m/%Y}"
    if formato == "datahora":
        return f"{pd.Timestamp(valor):%d/%m/%Y %H:%M}"
    if formato == "veredito":
        estado, texto = VEREDITOS.get(str(valor), (None, str(valor)))
        return f"{tema.ESTADOS[estado][1]} {texto}" if estado else texto
    if formato == "situacao":
        estado, texto = SITUACOES.get(str(valor), ("critico", str(valor)))
        return f"{tema.ESTADOS[estado][1]} {texto}"
    return str(valor)


def _cor(valor: object, formato: str) -> QColor | None:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return QColor(C["texto_apagado"])
    if formato == "variacao":
        return QColor(tema.cor_da_variacao(float(valor)))
    if formato == "veredito":
        estado = VEREDITOS.get(str(valor), (None, ""))[0]
        return (
            QColor(tema.ESTADOS[estado][0]) if estado else QColor(C["texto_secundario"])
        )
    if formato == "situacao":
        estado = SITUACOES.get(str(valor), ("critico", ""))[0]
        return QColor(tema.ESTADOS[estado][0])
    return None


class ModeloDeTabela(QAbstractTableModel):
    def __init__(
        self, colunas: Sequence[Coluna], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.colunas = list(colunas)
        self.dados = pd.DataFrame(columns=[c.chave for c in colunas])
        self._fonte = fonte_tabular()

    def definir(self, dados: pd.DataFrame) -> None:
        self.beginResetModel()
        self.dados = dados.reset_index(drop=True)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.dados)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.colunas)

    def valor(self, linha: int, chave: str) -> object:
        return self.dados.iloc[linha][chave] if chave in self.dados.columns else None

    def data(
        self, indice: QModelIndex, papel: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not indice.isValid():
            return None
        coluna = self.colunas[indice.column()]
        valor = self.valor(indice.row(), coluna.chave)
        if papel == Qt.ItemDataRole.DisplayRole:
            return formatar(valor, coluna.formato)
        if papel == Qt.ItemDataRole.UserRole:  # para ordenar pelo valor, não pelo texto
            # o Qt só compara tipos comuns do Python: nada de np.int64 ou Timestamp
            if isinstance(valor, pd.Timestamp):
                return float(valor.value)
            if isinstance(valor, (int, float, np.integer, np.floating)):
                numero = float(valor)
                return -np.inf if np.isnan(numero) else numero
            return "" if valor is None else str(valor)
        if papel == Qt.ItemDataRole.TextAlignmentRole:
            if coluna.formato in NUMERICOS:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if papel == Qt.ItemDataRole.ForegroundRole:
            return _cor(valor, coluna.formato)
        if papel == Qt.ItemDataRole.FontRole and coluna.formato in NUMERICOS:
            return self._fonte
        return None

    def headerData(
        self,
        secao: int,
        orientacao: Qt.Orientation,
        papel: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if orientacao != Qt.Orientation.Horizontal:
            return None
        coluna = self.colunas[secao]
        if papel == Qt.ItemDataRole.DisplayRole:
            return coluna.titulo
        if papel == Qt.ItemDataRole.TextAlignmentRole:
            if coluna.formato in NUMERICOS:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None


class Tabela(QTableView):
    """Tabela ordenável e filtrável por texto, sem linhas de grade pesadas."""

    def __init__(
        self, colunas: Sequence[Coluna], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.modelo = ModeloDeTabela(colunas, self)
        self.filtro = QSortFilterProxyModel(self)
        self.filtro.setSourceModel(self.modelo)
        self.filtro.setSortRole(Qt.ItemDataRole.UserRole)
        self.filtro.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.filtro.setFilterKeyColumn(-1)
        self.setModel(self.filtro)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(tema.ALTURA_DO_BOTAO)
        cabecalho = self.horizontalHeader()
        cabecalho.setHighlightSections(False)
        cabecalho.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        cabecalho.setStretchLastSection(True)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    def definir(self, dados: pd.DataFrame) -> None:
        self.modelo.definir(dados)

    def filtrar(self, texto: str) -> None:
        self.filtro.setFilterFixedString(texto)

    def linha_selecionada(self) -> int | None:
        selecao = self.selectionModel().selectedRows()
        if not selecao:
            return None
        return self.filtro.mapToSource(selecao[0]).row()


# --- gráficos --------------------------------------------------------------------------------


def _segundos(indice: pd.DatetimeIndex) -> np.ndarray:
    return pd.DatetimeIndex(indice).as_unit("s").asi8.astype(float)


def _caneta(cor: str, largura: float = 2, tracejada: bool = False) -> object:
    estilo = Qt.PenStyle.DashLine if tracejada else Qt.PenStyle.SolidLine
    return pg.mkPen(QColor(cor), width=largura, style=estilo)


def _preparar_eixos(grafico: pg.PlotWidget) -> None:
    grafico.showGrid(x=False, y=True, alpha=0.15)
    for nome in ("left", "bottom"):
        eixo = grafico.getAxis(nome)
        eixo.setPen(pg.mkPen(C["eixo"]))
        eixo.setTextPen(pg.mkPen(C["texto_apagado"]))
        eixo.setStyle(tickFont=fonte_tabular(tema.TAMANHO["rotulo"]))
    grafico.setMenuEnabled(False)


class GraficoDeLinhas(pg.PlotWidget):
    """Séries no tempo (mesma escala), com legenda, rótulo no fim e mira com os valores."""

    def __init__(
        self,
        formato_y: str = "num2",
        linha_base: float | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent, axisItems={"bottom": pg.DateAxisItem()})
        _preparar_eixos(self)
        self.formato_y = formato_y
        self.linha_base = linha_base
        self.series: dict[str, pd.Series] = {}
        self._legenda = None
        self._mira = pg.InfiniteLine(angle=90, movable=False, pen=_caneta(C["eixo"], 1))
        self._texto = pg.TextItem(
            color=C["texto"], anchor=(0, 1), fill=pg.mkBrush(C["elevado"])
        )
        self._proxy = pg.SignalProxy(
            self.scene().sigMouseMoved, rateLimit=60, slot=self._mover
        )

    def definir(
        self, series: dict[str, pd.Series], cores: dict[str, str] | None = None
    ) -> None:
        self.clear()
        self.series = {k: v.dropna() for k, v in series.items() if len(v.dropna())}
        cores = cores or {}
        if self._legenda is not None:
            self._legenda.scene() and self._legenda.scene().removeItem(self._legenda)
            self._legenda = None
        if len(self.series) >= 2:
            self._legenda = self.addLegend(
                offset=(E["s"], E["s"]), labelTextColor=C["texto_secundario"]
            )
        if self.linha_base is not None:
            self.addItem(
                pg.InfiniteLine(pos=self.linha_base, angle=0, pen=_caneta(C["eixo"], 1))
            )
        for i, (nome, serie) in enumerate(self.series.items()):
            cor = cores.get(nome, tema.SERIES[i % len(tema.SERIES)])
            self.plot(
                _segundos(serie.index),
                serie.to_numpy(dtype=float),
                pen=_caneta(cor),
                name=nome,
            )
            if len(self.series) <= 4:  # rótulo direto no fim da linha
                fim = pg.TextItem(nome, color=cor, anchor=(0, 0.5))
                fim.setPos(_segundos(serie.index[-1:])[0], float(serie.iloc[-1]))
                self.addItem(fim)
        self.addItem(self._mira, ignoreBounds=True)
        self.addItem(self._texto, ignoreBounds=True)
        self._mira.hide()
        self._texto.hide()
        self.enableAutoRange()

    def _mover(self, evento: tuple) -> None:
        if not self.series:
            return
        posicao = evento[0]
        if not self.sceneBoundingRect().contains(posicao):
            self._mira.hide()
            self._texto.hide()
            return
        ponto = self.getPlotItem().vb.mapSceneToView(posicao)
        x = ponto.x()
        linhas = []
        for nome, serie in self.series.items():
            xs = _segundos(serie.index)
            i = int(np.clip(np.searchsorted(xs, x), 0, len(xs) - 1))
            linhas.append(f"{nome}: {formatar(serie.iloc[i], self.formato_y)}")
            data = serie.index[i]
        self._mira.setPos(x)
        self._texto.setText(f"{pd.Timestamp(data):%d/%m/%Y}\n" + "\n".join(linhas))
        self._texto.setPos(x, ponto.y())
        self._mira.show()
        self._texto.show()


class GraficoDeBarras(pg.PlotWidget):
    """Barras de categorias (ex.: Sharpe de cada caminho) com uma linha de referência."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        _preparar_eixos(self)

    def definir(
        self,
        rotulos: Sequence[str],
        valores: Sequence[float],
        referencia: float | None = None,
        nome_da_referencia: str = "",
    ) -> None:
        self.clear()
        x = np.arange(len(valores))
        cores = [QColor(tema.cor_da_variacao(v)) for v in valores]
        self.addItem(
            pg.BarGraphItem(
                x=x,
                height=list(valores),
                width=0.6,
                brushes=cores,
                pens=[pg.mkPen(None)] * len(x),
            )
        )
        self.addItem(pg.InfiniteLine(pos=0, angle=0, pen=_caneta(C["eixo"], 1)))
        if referencia is not None:
            self.addItem(
                pg.InfiniteLine(
                    pos=referencia, angle=0, pen=_caneta(C["texto_secundario"], 1, True)
                )
            )
            marca = pg.TextItem(
                f"{nome_da_referencia} {referencia:.2f}".replace(".", ","),
                color=C["texto_secundario"],
                anchor=(1, 1),
            )
            marca.setPos(len(valores) - 0.5, referencia)
            self.addItem(marca)
        self.getAxis("bottom").setTicks([list(zip(x, rotulos, strict=True))])


class Velas(pg.GraphicsObject):
    """Velas: alta = contorno vazado azul, baixa = cheia vermelha (forma + cor, nunca só cor)."""

    def __init__(self) -> None:
        super().__init__()
        self._figura = QPicture()

    def definir(self, candles: pd.DataFrame) -> None:
        self._figura = QPicture()
        pintor = QPainter(self._figura)
        if len(candles) > 1:
            xs = _segundos(candles.index)
            largura = np.median(np.diff(xs)) * 0.35
            for x, (_, linha) in zip(xs, candles.iterrows(), strict=True):
                alta = linha["Close"] >= linha["Open"]
                cor = QColor(C["ganho"] if alta else C["perda"])
                pintor.setPen(pg.mkPen(cor, width=1))
                pintor.drawLine(QPointF(x, linha["Low"]), QPointF(x, linha["High"]))
                pintor.setBrush(pg.mkBrush(C["superficie"] if alta else cor))
                topo, base = (
                    max(linha["Open"], linha["Close"]),
                    min(linha["Open"], linha["Close"]),
                )
                pintor.drawRect(
                    QRectF(x - largura, base, 2 * largura, max(topo - base, 1e-12))
                )
        pintor.end()
        self.prepareGeometryChange()
        self.update()

    def paint(self, pintor: QPainter, *_: object) -> None:
        pintor.drawPicture(0, 0, self._figura)

    def boundingRect(self) -> QRectF:
        return QRectF(self._figura.boundingRect())


class GraficoDeVelas(pg.PlotWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent, axisItems={"bottom": pg.DateAxisItem()})
        _preparar_eixos(self)
        self.velas = Velas()
        self.addItem(self.velas)

    def definir(self, candles: pd.DataFrame) -> None:
        self.velas.definir(candles)
        self.enableAutoRange()


# --- aviso flutuante (sucesso) ---------------------------------------------------------------


class Toast(QLabel):
    """Aviso curto no canto inferior direito; some sozinho em 4 s."""

    DURACAO_MS = 4000

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("aviso")
        self.setStyleSheet(
            f"background: {C['elevado']}; border: 1px solid {C['borda']};"
            f" border-radius: {tema.RAIO['cartao']}px; padding: {E['m']}px {E['l']}px;"
        )
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def mostrar(self, texto: str, estado: str = "bom") -> None:
        cor, icone = tema.ESTADOS[estado]
        self.setText(f'<span style="color:{cor}">{icone}</span>&nbsp;&nbsp;{texto}')
        self.adjustSize()
        pai = self.parentWidget()
        self.move(
            pai.width() - self.width() - E["xl"],
            pai.height() - self.height() - E["xxxl"],
        )
        self.raise_()
        self.show()
        self._timer.start(self.DURACAO_MS)
