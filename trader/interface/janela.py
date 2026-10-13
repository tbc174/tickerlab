"""A janela principal: navegação lateral, telas, atalhos, barra de status e tarefas longas."""

from __future__ import annotations

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from trader.interface import tema
from trader.interface.componentes import Toast, formatar, rotulo
from trader.interface.fontes import Fontes
from trader.interface.tarefas import COMANDOS, Tarefa
from trader.interface.telas import (
    Tela,
    TelaBaselines,
    TelaDados,
    TelaInicio,
    TelaMercado,
    TelaPesquisa,
)

E = tema.ESPACO
NAVEGACAO = (  # (ícone, nome, classe da tela)
    ("⌂", "Início", TelaInicio),
    ("◎", "Pesquisa", TelaPesquisa),
    ("▤", "Baselines e ativos", TelaBaselines),
    ("⛁", "Dados", TelaDados),
    ("◔", "Mercado", TelaMercado),
)
INDICE_DADOS = 3


class Janela(QMainWindow):
    def __init__(self, fontes: Fontes | None = None) -> None:
        super().__init__()
        self.fontes = fontes or Fontes()
        self.setWindowTitle("Trader — painel de pesquisa (só leitura)")
        self.resize(1440, 900)
        self.setMinimumSize(1080, 700)
        self.tarefa: Tarefa | None = None

        # a barra de status vem antes das telas: elas avisam o estado do MT5 ao serem criadas
        barra = self.statusBar()
        barra.setSizeGripEnabled(False)
        self.s_mt5 = QLabel("● MT5 desconectado")
        self.s_dados = QLabel("")
        self.s_tentativas = QLabel("")
        self.s_holdout = QLabel("")
        self.s_tarefa = QLabel("")
        self.s_barra = QProgressBar()
        self.s_barra.setRange(0, 0)
        self.s_barra.setFixedWidth(120)
        self.s_barra.hide()
        for w in (self.s_mt5, self.s_dados, self.s_tentativas, self.s_holdout):
            barra.addWidget(w)
        barra.addPermanentWidget(self.s_tarefa)
        barra.addPermanentWidget(self.s_barra)

        fundo = QWidget()
        fundo.setObjectName("fundo")
        linha = QHBoxLayout(fundo)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(0)
        self.navegacao = QWidget()
        self.navegacao.setObjectName("navegacao")
        self.navegacao.setFixedWidth(220)
        coluna = QVBoxLayout(self.navegacao)
        coluna.setContentsMargins(E["m"], E["xl"], E["m"], E["l"])
        coluna.setSpacing(E["xs"])
        marca = rotulo("◧  Trader", "titulo_cartao")
        coluna.addWidget(marca)
        coluna.addWidget(rotulo("pesquisa · só leitura", "apagado"))
        coluna.addSpacing(E["xl"])
        self.grupo = QButtonGroup(self)
        self.grupo.setExclusive(True)
        self.pilha = QStackedWidget()
        self.telas: list[Tela] = []
        for i, (icone, nome, classe) in enumerate(NAVEGACAO):
            botao = QPushButton(f"{icone}   {nome}")
            botao.setObjectName("item_de_navegacao")
            botao.setCheckable(True)
            botao.setToolTip(f"{nome} (Ctrl+{i + 1})")
            self.grupo.addButton(botao, i)
            coluna.addWidget(botao)
            tela = classe(self.fontes, self)
            self.telas.append(tela)
            self.pilha.addWidget(tela)
        coluna.addStretch()
        coluna.addWidget(
            rotulo("Nada aqui envia ordens\nnem pontua o holdout.", "apagado")
        )
        linha.addWidget(self.navegacao)
        linha.addWidget(self.pilha, 1)
        self.setCentralWidget(fundo)
        self.grupo.idClicked.connect(self.ir_para)

        self.toast = Toast(fundo)
        for i in range(len(NAVEGACAO)):
            QShortcut(
                QKeySequence(f"Ctrl+{i + 1}"),
                self,
                activated=lambda i=i: self.ir_para(i),
            )
        QShortcut(QKeySequence("F5"), self, activated=self.atualizar_tudo)
        self._atual = 0
        self.ir_para(0)
        self.atualizar_status()

    # --- navegação ----------------------------------------------------------------------
    def ir_para(self, indice: int) -> None:
        if 0 <= self._atual < len(self.telas):
            self.telas[self._atual].ao_sair()
        self._atual = indice
        self.grupo.button(indice).setChecked(True)
        self.pilha.setCurrentIndex(indice)
        self.telas[indice].ao_entrar()

    def ir_para_dados(self) -> None:
        self.ir_para(INDICE_DADOS)

    @property
    def tela_atual(self) -> Tela:
        return self.telas[self._atual]

    def atualizar_tudo(self) -> None:
        self.tela_atual.atualizar()
        self.atualizar_status()

    # --- barra de status ----------------------------------------------------------------
    def atualizar_status(self) -> None:
        historico = self.fontes.frescor()[0]
        self.s_dados.setText(
            f"dados de {formatar(historico.atualizado_em, 'datahora')}"
            if historico.atualizado_em
            else "dados: nunca baixados"
        )
        contagem = self.fontes.contagem()
        self.s_tentativas.setText(
            f"{contagem['total']}/{contagem['orcamento']} tentativas"
        )
        h = self.fontes.holdout()
        cor, icone = tema.ESTADOS[h["estado"]]
        self.s_holdout.setText(
            f'<span style="color:{cor}">{icone}</span> holdout {h["texto"]}'
        )

    def mt5_mudou(self, conectado: bool, servidor: str = "") -> None:
        cor = tema.CORES["bom"] if conectado else tema.CORES["texto_apagado"]
        texto = f"MT5 conectado ({servidor})" if conectado else "MT5 desconectado"
        self.s_mt5.setText(f'<span style="color:{cor}">●</span> {texto}')

    # --- tarefas ------------------------------------------------------------------------
    def executar(self, chave: str) -> None:
        if self.tarefa is not None and self.tarefa.rodando:
            self.toast.mostrar(
                "Já existe uma tarefa rodando. Espere ou cancele.", "atencao"
            )
            return
        comando = COMANDOS[chave]
        self.tarefa = Tarefa(comando, self)
        self.tarefa.progresso.connect(self._progresso)
        self.tarefa.terminou.connect(self._terminou)
        self.s_tarefa.setText(f"{comando.titulo}…")
        self.s_barra.show()
        self.telas[INDICE_DADOS].tarefa_comecou(comando.titulo)
        self.tarefa.iniciar()

    def cancelar_tarefa(self) -> None:
        if self.tarefa is not None and self.tarefa.rodando:
            self.tarefa.cancelar()

    def _progresso(self, linha: str) -> None:
        self.s_tarefa.setText(linha[:60])
        self.telas[INDICE_DADOS].tarefa_progrediu(linha)

    def _terminou(self, ok: bool, resumo: str) -> None:
        self.s_barra.hide()
        self.s_tarefa.setText("")
        self.telas[INDICE_DADOS].tarefa_terminou()
        self.toast.mostrar(resumo[:160], "bom" if ok else "critico")
        self.atualizar_tudo()

    def closeEvent(self, evento: object) -> None:
        self.cancelar_tarefa()
        mercado = self.telas[4]
        if isinstance(mercado, TelaMercado) and mercado.conectado:
            mercado.desconectar()
        super().closeEvent(evento)
