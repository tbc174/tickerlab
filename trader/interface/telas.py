"""As cinco telas do painel. Cada uma responde a UMA pergunta principal; o resto fica sob demanda.

Início ("está tudo em ordem?"), Pesquisa ("como está a pesquisa?"), Baselines ("qual é a régua?"),
Dados ("os dados estão em dia?") e Mercado ("o que o mercado está fazendo?", só leitura).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from trader import avaliacao
from trader.interface import tema
from trader.interface.componentes import (
    Aviso,
    Cartao,
    CartaoResumo,
    Coluna,
    GraficoDeBarras,
    GraficoDeLinhas,
    GraficoDeVelas,
    Tabela,
    formatar,
    rotulo,
)
from trader.interface.fontes import Fontes
from trader.interface.tarefas import COMANDOS
from trader.universo import UNIVERSO

if TYPE_CHECKING:
    from trader.interface.janela import Janela

E = tema.ESPACO


class Tela(QWidget):
    titulo = ""
    pergunta = ""

    def __init__(self, fontes: Fontes, janela: Janela | None = None) -> None:
        super().__init__()
        self.fontes = fontes
        self.janela = janela
        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        externo.addWidget(rolagem)
        conteudo = QWidget()
        conteudo.setObjectName("fundo")
        rolagem.setWidget(conteudo)
        self.corpo = QVBoxLayout(conteudo)
        self.corpo.setContentsMargins(E["xxl"], E["xl"], E["xxl"], E["xl"])
        self.corpo.setSpacing(E["xl"])
        cabecalho = QHBoxLayout()
        textos = QVBoxLayout()
        textos.setSpacing(E["xs"])
        textos.addWidget(rotulo(self.titulo, "titulo_tela"))
        textos.addWidget(rotulo(self.pergunta, "subtitulo_tela"))
        cabecalho.addLayout(textos)
        cabecalho.addStretch()
        self.acoes = QHBoxLayout()
        self.acoes.setSpacing(E["s"])
        cabecalho.addLayout(self.acoes)
        self.corpo.addLayout(cabecalho)

    def botao(
        self, texto: str, ao_clicar: object, primario: bool = False, dica: str = ""
    ) -> QPushButton:
        b = QPushButton(texto)
        if primario:
            b.setProperty("papel", "primario")
        if dica:
            b.setToolTip(dica)
        b.clicked.connect(ao_clicar)
        return b

    def atualizar(self) -> None:  # cada tela relê o que mostra
        pass

    def ao_entrar(self) -> None:
        self.atualizar()

    def ao_sair(self) -> None:
        pass


def _texto_do_embaralhado(vaz: dict) -> str:
    """Contra a referência da proporção (desde a v0.2) ou, nas tentativas antigas, a regra da v0.1."""
    emb = formatar(vaz.get("sharpe_embaralhado"), "num2")
    if "sharpe_da_diferenca" in vaz:
        return (
            f"rótulos embaralhados {emb} contra a proporção "
            f"{formatar(vaz.get('sharpe_proporcao'), 'num2')} (diferença "
            f"{formatar(vaz.get('sharpe_da_diferenca'), 'num2')}; desde a v0.4 só reprova acima de "
            f"+{formatar(vaz.get('limite_da_diferenca'), 'num2')})"
        )
    return (
        f"rótulos embaralhados {emb} "
        f"(limite ±{formatar(vaz.get('limite_do_embaralhado'), 'num2')}, regra da v0.1)"
    )


def _limpar(layout: QVBoxLayout | QHBoxLayout | QGridLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


# --- Início ----------------------------------------------------------------------------------


class TelaInicio(Tela):
    titulo = "Início"
    pergunta = "Está tudo em ordem?"

    def __init__(self, fontes: Fontes, janela: Janela | None = None) -> None:
        super().__init__(fontes, janela)
        linha = QHBoxLayout()
        linha.setSpacing(E["l"])
        self.c_tentativas = CartaoResumo(
            "Tentativas",
            "Configurações testadas no desenvolvimento. O Sharpe deflacionado usa este total; o orçamento aprovado é de 300.",
        )
        self.c_holdout = CartaoResumo(
            "Holdout",
            "Os 3 anos finais (10/10/2023 a 09/10/2026), pontuados uma única vez por um candidato aprovado em A1–A10. A interface não pontua o holdout.",
        )
        self.c_regua = CartaoResumo(
            "Régua (B1)",
            "Sharpe da tendência simples no desenvolvimento. Um modelo de ML só conta se vencer esta régua com folga (critério A5).",
        )
        self.c_melhor = CartaoResumo(
            "Melhor modelo",
            "O modelo de ML com maior Sharpe mediano nos 9 caminhos do CPCV, e o veredito dele.",
        )
        for c in (self.c_tentativas, self.c_holdout, self.c_regua, self.c_melhor):
            linha.addWidget(c, 1)
        self.corpo.addLayout(linha)
        self.c_agora = Cartao(
            "O que fazer agora",
            "Avisos sobre dados velhos, rodadas interrompidas e passos que faltam.",
        )
        self.lista = QVBoxLayout()
        self.lista.setSpacing(E["s"])
        self.c_agora.layout_.addLayout(self.lista)
        self.corpo.addWidget(self.c_agora)
        self.c_frescor = Cartao("Atualização dos dados")
        self.t_frescor = Tabela(
            [
                Coluna("fonte", "Fonte"),
                Coluna("atualizado_em", "Atualizado em", "datahora"),
                Coluna("detalhe", "Detalhe"),
                Coluna("situacao", "Situação", "situacao"),
            ]
        )
        self.t_frescor.setMinimumHeight(4 * tema.ALTURA_DO_BOTAO + 16)
        self.c_frescor.adicionar(self.t_frescor)
        self.corpo.addWidget(self.c_frescor)
        self.corpo.addStretch()
        self.acoes.addWidget(
            self.botao("Atualizar", self.atualizar, dica="Reler tudo (F5)")
        )

    def atualizar(self) -> None:
        contagem = self.fontes.contagem()
        self.c_tentativas.atualizar(
            f"{contagem['total']}",
            f"de {contagem['orcamento']} no orçamento · restam {contagem['restante']}",
        )
        h = self.fontes.holdout()
        self.c_holdout.atualizar(
            h["texto"].split(" (")[0], f"{h['periodo']}", h["estado"]
        )
        resumo = self.fontes.resumo_das_baselines()
        b1 = resumo.query("baseline == 'B1'")
        if len(b1):
            self.c_regua.atualizar(
                formatar(b1["sharpe"].iloc[0], "num2"),
                "Sharpe da tendência simples (custos ×1)",
            )
        else:
            self.c_regua.atualizar("—", "Rode as baselines na tela Dados.")
        tentativas = self.fontes.tentativas()
        modelos = tentativas[tentativas["veredito"].isin(["aprovado", "reprovado"])]
        if len(modelos):
            melhor = modelos.loc[modelos["sharpe"].idxmax()]
            estado = "bom" if melhor["veredito"] == "aprovado" else "critico"
            self.c_melhor.atualizar(
                formatar(melhor["sharpe"], "num2"),
                f"{melhor['nome']} (#{melhor['id']}) · {melhor['veredito']}",
                estado,
            )
        else:
            self.c_melhor.atualizar("—", "Nenhum modelo julgado ainda.")
        _limpar(self.lista)
        alertas = self.fontes.alertas()
        if not alertas:
            self.lista.addWidget(
                Aviso(
                    "Tudo em dia: dados atualizados e nenhuma rodada pendente.", "bom"
                )
            )
        for a in alertas:
            ir = (
                self.janela.ir_para_dados if self.janela and "Dados" in a.acao else None
            )
            self.lista.addWidget(
                Aviso(f"{a.texto} {a.acao}", a.nivel, "Abrir Dados" if ir else "", ir)
            )
        linhas = [
            {
                "fonte": f.fonte,
                "atualizado_em": f.atualizado_em,
                "detalhe": f.detalhe,
                "situacao": "ok" if not f.velho else "desatualizado",
            }
            for f in self.fontes.frescor()
        ]
        self.t_frescor.definir(pd.DataFrame(linhas))


# --- Pesquisa --------------------------------------------------------------------------------


class TelaPesquisa(Tela):
    titulo = "Pesquisa"
    pergunta = "Como está a pesquisa? O que passou, o que reprovou e por quê."

    def __init__(self, fontes: Fontes, janela: Janela | None = None) -> None:
        super().__init__(fontes, janela)
        filtros = QHBoxLayout()
        filtros.setSpacing(E["s"])
        self.f_familia = QComboBox()
        self.f_familia.addItems(
            [
                "Todas as famílias",
                "H0 baselines",
                "H1 linear",
                "H2 árvores",
                "H3 meta-rotulagem",
                "H4 deep learning",
                "H5 séries temporais",
            ]
        )
        self.f_veredito = QComboBox()
        self.f_veredito.addItems(
            ["Todos os vereditos", "aprovado", "reprovado", "régua", "sem resultado"]
        )
        self.f_busca = QLineEdit()
        self.f_busca.setPlaceholderText("Buscar pelo nome…")
        for w in (self.f_familia, self.f_veredito):
            w.currentIndexChanged.connect(self._filtrar)
            filtros.addWidget(w)
        self.f_busca.textChanged.connect(self._filtrar)
        filtros.addWidget(self.f_busca, 1)
        self.corpo.addLayout(filtros)

        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.setChildrenCollapsible(False)
        self.c_lista = Cartao("Tentativas")
        self.tabela = Tabela(
            [
                Coluna("id", "#", "int"),
                Coluna("familia", "Família"),
                Coluna("nome", "Nome"),
                Coluna("veredito", "Veredito", "veredito"),
                Coluna("sharpe", "Sharpe", "num2"),
                Coluna("t", "t", "num2"),
                Coluna("criada_em", "Criada em", "datahora"),
            ]
        )
        self.tabela.setMinimumHeight(420)
        self.tabela.sortByColumn(
            0, Qt.SortOrder.DescendingOrder
        )  # mais recentes primeiro
        self.tabela.selectionModel().selectionChanged.connect(self._mostrar_detalhe)
        self.c_lista.adicionar(self.tabela, 1)
        self.c_detalhe = Cartao(
            "Detalhe", "Clique numa tentativa para ver o veredito item a item."
        )
        self.d_titulo = self.c_detalhe.adicionar(
            rotulo("Selecione uma tentativa na tabela.", "secundario", quebra=True)
        )
        self.d_itens = Tabela(
            [
                Coluna("codigo", "Item"),
                Coluna("descricao", "O quê"),
                Coluna("valor", "Valor", "num3"),
                Coluna("limite", "Limite"),
                Coluna("passou_txt", "Passou", "situacao"),
            ]
        )
        self.d_itens.setMinimumHeight(12 * tema.ALTURA_DO_BOTAO)
        self.c_detalhe.adicionar(self.d_itens)
        self.d_caminhos_titulo = self.c_detalhe.adicionar(
            rotulo("Sharpe dos 9 caminhos do CPCV (linha tracejada: B1)", "apagado")
        )
        self.d_caminhos = GraficoDeBarras()
        self.d_caminhos.setMinimumHeight(180)
        self.c_detalhe.adicionar(self.d_caminhos)
        self.d_curva_titulo = self.c_detalhe.adicionar(
            rotulo("Capital do caminho mediano contra a B1 (começa em 1)", "apagado")
        )
        self.d_curva = GraficoDeLinhas(linha_base=1.0)
        self.d_curva.setMinimumHeight(220)
        self.c_detalhe.adicionar(self.d_curva)
        self.d_notas = self.c_detalhe.adicionar(rotulo("", "secundario", quebra=True))
        divisor.addWidget(self.c_lista)
        divisor.addWidget(self.c_detalhe)
        divisor.setSizes([520, 680])
        self.corpo.addWidget(divisor, 1)
        self.acoes.addWidget(
            self.botao("Atualizar", self.atualizar, dica="Reler o registro (F5)")
        )
        self._dados = pd.DataFrame()
        self._detalhe_visivel(False)

    def _detalhe_visivel(self, visivel: bool) -> None:
        for w in (
            self.d_itens,
            self.d_caminhos_titulo,
            self.d_caminhos,
            self.d_curva_titulo,
            self.d_curva,
            self.d_notas,
        ):
            w.setVisible(visivel)

    def atualizar(self) -> None:
        self._dados = self.fontes.tentativas()
        self._filtrar()

    def _filtrar(self) -> None:
        dados = self._dados
        if dados.empty:
            self.tabela.definir(dados)
            return
        if self.f_familia.currentIndex() > 0:
            dados = dados[dados["familia"] == self.f_familia.currentText().split()[0]]
        if self.f_veredito.currentIndex() > 0:
            dados = dados[dados["veredito"] == self.f_veredito.currentText()]
        busca = self.f_busca.text().strip().lower()
        if busca:
            dados = dados[dados["nome"].str.lower().str.contains(busca, regex=False)]
        self.tabela.definir(dados)

    def _mostrar_detalhe(self) -> None:
        linha = self.tabela.linha_selecionada()
        if linha is None:
            return
        tentativa_id = int(self.tabela.modelo.valor(linha, "id"))
        d = self.fontes.detalhe_da_tentativa(tentativa_id)
        resultado = d["resultado"] or {}
        self._detalhe_visivel(True)
        b1 = self.fontes.baseline("B1")
        sharpe_b1 = avaliacao.sharpe(b1["x1"]) if b1 is not None else None
        if "itens" in resultado:
            veredito = (
                "APROVADO em A1–A10" if resultado.get("aprovado") else "REPROVADO"
            )
            reprov = ", ".join(resultado.get("reprovados", []))
            self.d_titulo.setText(
                f"#{tentativa_id} · {d['nome']} ({d['familia']}) · {veredito}"
                + (f" — falhou em {reprov}" if reprov else "")
            )
            itens = pd.DataFrame(resultado["itens"])
            itens["passou_txt"] = np.where(itens["passou"], "ok", "não passou")
            self.d_itens.definir(itens)
            sharpes = resultado.get("sharpes_dos_caminhos") or []
            self.d_caminhos.definir(
                [str(i + 1) for i in range(len(sharpes))], sharpes, sharpe_b1, "B1"
            )
            vaz = resultado.get("vazamento", {})
            acaso = resultado.get("acaso", {})
            self.d_notas.setText(
                f"Vazamento — normal {formatar(vaz.get('sharpe_normal'), 'num2')}, olhando o futuro "
                f"{formatar(vaz.get('sharpe_futuro'), 'num2')}, {_texto_do_embaralhado(vaz)}. "
                f"Contra o acaso — p-valor {formatar(acaso.get('p_valor'), 'num3')}."
            )
            self.d_itens.setVisible(True)
            self.d_caminhos.setVisible(bool(sharpes))
            self.d_caminhos_titulo.setVisible(bool(sharpes))
        else:
            texto = (
                "régua (baseline): não é julgada pelo critério"
                if "carteira" in resultado
                else "sem resultado (rodada interrompida?)"
            )
            self.d_titulo.setText(
                f"#{tentativa_id} · {d['nome']} ({d['familia']}) · {texto}"
            )
            for w in (self.d_itens, self.d_caminhos, self.d_caminhos_titulo):
                w.setVisible(False)
            self.d_notas.setText(
                f"Commit do código: {d['commit_do_codigo']} · execuções: {d['execucoes']}"
            )
        series = {}
        if d["serie"] is not None:
            series[d["nome"]] = (1 + d["serie"]["x1"].fillna(0)).cumprod()
        if b1 is not None and d["nome"] != "baseline_B1":
            series["B1"] = (1 + b1["x1"].fillna(0)).cumprod()
        self.d_curva.definir(series, {d["nome"]: tema.SERIES[0], "B1": tema.SERIES[1]})
        self.d_curva.setVisible(bool(series))
        self.d_curva_titulo.setVisible(bool(series))


# --- Baselines e ativos ----------------------------------------------------------------------


class TelaBaselines(Tela):
    titulo = "Baselines e ativos"
    pergunta = "Qual é a régua que o ML precisa vencer, e onde ela funciona?"

    CORES: ClassVar[dict[str, str]] = {
        "B0": tema.SERIES[0],
        "B1": tema.SERIES[1],
        "B2": tema.SERIES[2],
    }

    def __init__(self, fontes: Fontes, janela: Janela | None = None) -> None:
        super().__init__(fontes, janela)
        self.vazio = Aviso(
            "As baselines ainda não foram rodadas.",
            "atencao",
            "Abrir Dados",
            janela.ir_para_dados if janela else None,
        )
        self.corpo.addWidget(self.vazio)
        self.c_resumo = Cartao(
            "Carteira (risco igual, desenvolvimento desde 2000)",
            "B0 comprar e segurar · B1 tendência simples (a régua) · B2 previsão ingênua. Resultado acima do juro da moeda (carry).",
        )
        self.t_resumo = Tabela(
            [
                Coluna("baseline", "Baseline"),
                Coluna("sharpe", "Sharpe ×1", "num2"),
                Coluna("sharpe_x2", "Sharpe ×2", "num2"),
                Coluna("t", "t", "num2"),
                Coluna("retorno_anual", "Retorno/ano", "pct"),
                Coluna("volatilidade_anual", "Vol/ano", "pct"),
                Coluna("maior_queda", "Maior queda", "pct"),
                Coluna("anos_positivos", "Anos positivos", "pct"),
            ]
        )
        self.t_resumo.setMinimumHeight(4 * tema.ALTURA_DO_BOTAO + 16)
        self.c_resumo.adicionar(self.t_resumo)
        self.g_curvas = GraficoDeLinhas(linha_base=1.0)
        self.g_curvas.setMinimumHeight(280)
        self.c_resumo.adicionar(self.g_curvas)
        self.corpo.addWidget(self.c_resumo)

        linha = QHBoxLayout()
        linha.setSpacing(E["l"])
        self.c_apostas = CartaoResumo(
            "Apostas independentes",
            "Quantas apostas de fato existem entre os ativos, pela correlação dos retornos semanais. Ativos parecidos contam menos.",
        )
        linha.addWidget(self.c_apostas, 1)
        self.c_movimento = CartaoResumo(
            "Movimento maior que o custo",
            "Fração média dos dias em que o preço anda mais do que custa entrar e sair. Perto de 100% = custo não é o gargalo.",
        )
        linha.addWidget(self.c_movimento, 1)
        self.corpo.addLayout(linha)

        self.c_ativos = Cartao("Por ativo")
        filtros = QHBoxLayout()
        self.f_baseline = QComboBox()
        self.f_baseline.addItems(["B1", "B0", "B2"])
        self.f_classe = QComboBox()
        self.f_classe.addItem("Todas as classes")
        self.f_classe.addItems(
            sorted({a.classe for a in UNIVERSO if a.papel == "operar"})
        )
        for w in (self.f_baseline, self.f_classe):
            w.currentIndexChanged.connect(self._filtrar)
            filtros.addWidget(w)
        filtros.addStretch()
        self.c_ativos.layout_.addLayout(filtros)
        self.t_ativos = Tabela(
            [
                Coluna("simbolo", "Ativo"),
                Coluna("classe", "Classe"),
                Coluna("sharpe", "Sharpe", "num2"),
                Coluna("t", "t", "num2"),
                Coluna("retorno_anual", "Retorno/ano", "pct"),
                Coluna("maior_queda", "Maior queda", "pct"),
                Coluna("giro_por_ano", "Giro/ano", "num2"),
                Coluna("custo_anual_em_sharpe", "Custo/ano em Sharpe", "num3"),
                Coluna("swap_por_ano", "Swap/ano", "pct"),
            ]
        )
        self.t_ativos.setMinimumHeight(420)
        self.c_ativos.adicionar(self.t_ativos)
        self.corpo.addWidget(self.c_ativos)
        self.acoes.addWidget(
            self.botao("Atualizar", self.atualizar, dica="Reler os resultados (F5)")
        )
        self._por_ativo = pd.DataFrame()

    def atualizar(self) -> None:
        resumo = self.fontes.resumo_das_baselines()
        tem = not resumo.empty
        self.vazio.setVisible(not tem)
        for w in (self.c_resumo, self.c_ativos, self.c_apostas, self.c_movimento):
            w.setVisible(tem)
        if not tem:
            return
        self.t_resumo.definir(resumo)
        self.g_curvas.definir(self.fontes.curvas_das_baselines(), self.CORES)
        viab, apostas = self.fontes.viabilidade()
        if apostas:
            self.c_apostas.atualizar(
                f"{apostas.get('apostas_independentes', float('nan')):.1f}".replace(
                    ".", ","
                ),
                f"de {apostas.get('ativos')} ativos · correlação semanal média "
                f"{formatar(apostas.get('correlacao_media'), 'num2')}",
            )
        else:
            self.c_apostas.atualizar("—", "Rode as baselines de novo para calcular.")
        if len(viab):
            self.c_movimento.atualizar(
                formatar(viab["movimento_maior_que_custo_1d"].mean(), "pct"),
                "dos dias, na média dos ativos (custo de ida e volta)",
            )
        self._por_ativo = self.fontes.baselines_por_ativo()
        self._filtrar()

    def _filtrar(self) -> None:
        dados = self._por_ativo
        if dados.empty:
            self.t_ativos.definir(dados)
            return
        dados = dados[dados["baseline"] == self.f_baseline.currentText()]
        if self.f_classe.currentIndex() > 0:
            dados = dados[dados["classe"] == self.f_classe.currentText()]
        self.t_ativos.definir(dados.sort_values("sharpe", ascending=False))


# --- Dados -----------------------------------------------------------------------------------


class TelaDados(Tela):
    titulo = "Dados"
    pergunta = "Os dados estão em dia e confiáveis?"

    def __init__(self, fontes: Fontes, janela: Janela | None = None) -> None:
        super().__init__(fontes, janela)
        self.c_tarefas = Cartao(
            "Atualizar",
            "Cada botão roda um comando do trader num processo separado; dá para cancelar.",
        )
        grade = QGridLayout()
        grade.setHorizontalSpacing(E["s"])
        grade.setVerticalSpacing(E["s"])
        self.botoes: dict[str, QPushButton] = {}
        for i, comando in enumerate(COMANDOS.values()):
            b = self.botao(
                comando.titulo,
                lambda _=False, c=comando.chave: self._executar(c),
                i == 0,
                comando.descricao,
            )
            self.botoes[comando.chave] = b
            grade.addWidget(b, 0, i)
        self.c_tarefas.layout_.addLayout(grade)
        self.p_linha = QHBoxLayout()
        self.p_barra = QProgressBar()
        self.p_barra.setRange(
            0, 0
        )  # indeterminada: os comandos não dizem a porcentagem
        self.p_texto = rotulo("", "secundario")
        self.p_cancelar = QPushButton("Cancelar")
        self.p_cancelar.clicked.connect(self._cancelar)
        self.p_linha.addWidget(self.p_barra, 1)
        self.p_linha.addWidget(self.p_texto, 2)
        self.p_linha.addWidget(self.p_cancelar)
        self.c_tarefas.layout_.addLayout(self.p_linha)
        self.corpo.addWidget(self.c_tarefas)

        self.c_qualidade = Cartao(
            "Qualidade das séries",
            "Situação depois do reparo: ok, reparada (máxima/mínima corrigidas, fechamento intacto) ou com aviso (defeito real conhecido).",
        )
        self.f_busca = QLineEdit()
        self.f_busca.setPlaceholderText("Filtrar por ativo, classe, situação…")
        self.c_qualidade.adicionar(self.f_busca)
        self.t_qualidade = Tabela(
            [
                Coluna("simbolo", "Ativo"),
                Coluna("fonte", "Fonte"),
                Coluna("classe", "Classe"),
                Coluna("papel", "Papel"),
                Coluna("situacao", "Situação", "situacao"),
                Coluna("linhas", "Linhas", "int"),
                Coluna("inicio", "Início"),
                Coluna("fim", "Fim"),
                Coluna("reparados", "Reparados", "int"),
                Coluna("saltos_suspeitos", "Saltos suspeitos", "int"),
                Coluna("proxy_de", "Proxy de"),
            ]
        )
        self.t_qualidade.setMinimumHeight(440)
        self.f_busca.textChanged.connect(self.t_qualidade.filtrar)
        self.c_qualidade.adicionar(self.t_qualidade)
        self.corpo.addWidget(self.c_qualidade)
        self.c_juros = Cartao(
            "Taxas básicas de juro (% ao ano)",
            "Bancos centrais (BIS). Entram no carry: o custo ou ganho de manter a posição.",
        )
        self.g_juros = GraficoDeLinhas(formato_y="num2")
        self.g_juros.setMinimumHeight(260)
        self.c_juros.adicionar(self.g_juros)
        self.corpo.addWidget(self.c_juros)
        self._tarefa_visivel(False)

    def _tarefa_visivel(self, visivel: bool) -> None:
        for w in (self.p_barra, self.p_texto, self.p_cancelar):
            w.setVisible(visivel)
        for b in self.botoes.values():
            b.setEnabled(not visivel)

    def _executar(self, chave: str) -> None:
        if self.janela is not None:
            self.janela.executar(chave)

    def _cancelar(self) -> None:
        if self.janela is not None:
            self.janela.cancelar_tarefa()

    def tarefa_comecou(self, titulo: str) -> None:
        self._tarefa_visivel(True)
        self.p_texto.setText(f"{titulo}…")

    def tarefa_progrediu(self, linha: str) -> None:
        self.p_texto.setText(linha[:140])

    def tarefa_terminou(self) -> None:
        self._tarefa_visivel(False)
        self.atualizar()

    def atualizar(self) -> None:
        qualidade = self.fontes.qualidade()
        if len(qualidade):
            # relatórios antigos não têm a coluna proxy_de; mostra só o nome do futuro
            proxy = (
                qualidade["proxy_de"]
                if "proxy_de" in qualidade
                else pd.Series("", index=qualidade.index)
            )
            qualidade = qualidade.assign(
                proxy_de=proxy.fillna("").astype(str).str.split(":").str[0]
            )
        self.t_qualidade.definir(qualidade)
        taxas = self.fontes.taxas_de_juro()
        self.g_juros.definir(
            {c: taxas[c] for c in taxas.columns},
            {c: tema.SERIES[i] for i, c in enumerate(taxas.columns)},
        )


# --- Mercado (MT5, só leitura) ---------------------------------------------------------------


SIMBOLOS_DO_MT5 = [a.simbolo for a in UNIVERSO if a.fonte == "mt5"]


class TelaMercado(Tela):
    titulo = "Mercado"
    pergunta = (
        "O que o mercado está fazendo agora? (MetaTrader 5, conta demo, só leitura)"
    )
    INTERVALO_MS = 3000

    def __init__(
        self, fontes: Fontes, janela: Janela | None = None, abrir_conexao: object = None
    ) -> None:
        super().__init__(fontes, janela)
        self._abrir_conexao = abrir_conexao
        self._conexao = None
        self._fechamentos: dict[str, float] = {}
        self.aviso = Aviso(
            "Desconectado. Abra o MetaTrader 5, entre numa conta DEMO e clique em Conectar. "
            "(Conta real é recusada; nenhuma ordem é enviada por aqui.)",
            "atencao",
        )
        self.corpo.addWidget(self.aviso)
        divisor = QSplitter(Qt.Orientation.Horizontal)
        self.c_lista = Cartao("Lista de observação")
        self.t_cotacoes = Tabela(
            [
                Coluna("simbolo", "Ativo"),
                Coluna("compra", "Compra", "num3"),
                Coluna("venda", "Venda", "num3"),
                Coluna("spread", "Spread", "num3"),
                Coluna("variacao", "Hoje", "variacao"),
                Coluna("hora", "Hora", "datahora"),
            ]
        )
        self.t_cotacoes.setMinimumHeight(520)
        self.t_cotacoes.selectionModel().selectionChanged.connect(self._mostrar_grafico)
        self.c_lista.adicionar(self.t_cotacoes, 1)
        self.c_grafico = Cartao(
            "Gráfico diário",
            "Velas: alta com contorno vazado, baixa cheia. Roda do mouse = zoom.",
        )
        self.g_velas = GraficoDeVelas()
        self.g_velas.setMinimumHeight(480)
        self.c_grafico.adicionar(self.g_velas, 1)
        divisor.addWidget(self.c_lista)
        divisor.addWidget(self.c_grafico)
        divisor.setSizes([520, 760])
        self.corpo.addWidget(divisor, 1)
        self.b_conectar = self.botao(
            "Conectar",
            self.conectar,
            primario=True,
            dica="Liga ao MetaTrader 5 aberto (conta demo)",
        )
        self.b_desconectar = self.botao("Desconectar", self.desconectar)
        self.acoes.addWidget(self.b_conectar)
        self.acoes.addWidget(self.b_desconectar)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._atualizar_cotacoes)
        self._estado(False)

    @property
    def conectado(self) -> bool:
        return self._conexao is not None

    def _estado(self, conectado: bool, mensagem: str = "") -> None:
        self.aviso.setVisible(not conectado)
        if mensagem:
            self.aviso.texto.setText(mensagem)
        self.b_conectar.setVisible(not conectado)
        self.b_desconectar.setVisible(conectado)
        self.c_lista.setEnabled(conectado)
        self.c_grafico.setEnabled(conectado)
        if self.janela is not None:
            self.janela.mt5_mudou(
                conectado, self._conexao.conta.servidor if conectado else ""
            )

    def conectar(self) -> None:
        from trader.mt5 import ConexaoMT5, ContaRealRecusadaError, MT5IndisponivelError

        try:
            conexao = (self._abrir_conexao or ConexaoMT5)()
            conexao.__enter__()
        except (MT5IndisponivelError, ContaRealRecusadaError, RuntimeError) as erro:
            self._estado(False, f"Não conectou: {erro}")
            return
        self._conexao = conexao
        self._fechamentos = {}
        for s in SIMBOLOS_DO_MT5:  # fechamento de ontem, para a variação do dia
            try:
                d = conexao.candles(
                    s,
                    "D1",
                    pd.Timestamp.now(tz="UTC").to_pydatetime() - pd.Timedelta(days=10),
                )
                self._fechamentos[s] = (
                    float(d["Close"].iloc[-2]) if len(d) > 1 else np.nan
                )
            except Exception:  # noqa: BLE001 (um símbolo ruim não derruba a lista)
                self._fechamentos[s] = np.nan
        self._estado(True)
        self._atualizar_cotacoes()
        self.timer.start(self.INTERVALO_MS)

    def desconectar(self) -> None:
        self.timer.stop()
        if self._conexao is not None:
            self._conexao.__exit__(None, None, None)
        self._conexao = None
        self._estado(False)

    def ao_sair(self) -> None:
        self.timer.stop()

    def ao_entrar(self) -> None:
        if self.conectado:
            self.timer.start(self.INTERVALO_MS)

    def _atualizar_cotacoes(self) -> None:
        if self._conexao is None:
            return
        linhas, sem_cotacao = [], []
        for s in SIMBOLOS_DO_MT5:
            try:
                c = self._conexao.cotacao(s)
            except Exception as erro:  # noqa: BLE001 (um símbolo ruim não derruba a lista)
                sem_cotacao.append(f"{s}: {erro}")
                c = None
            if c is None:
                continue
            anterior = self._fechamentos.get(s, np.nan)
            linhas.append(
                {
                    **c,
                    "spread": c["venda"] - c["compra"],
                    "variacao": c["compra"] / anterior - 1
                    if anterior and np.isfinite(anterior)
                    else np.nan,
                }
            )
        self.c_lista.titulo.setText(
            "Lista de observação"
            + (f" — {len(sem_cotacao)} sem cotação" if sem_cotacao else "")
        )
        self.c_lista.titulo.setToolTip("\n".join(sem_cotacao))
        selecionada = self.t_cotacoes.linha_selecionada()
        simbolo = (
            self.t_cotacoes.modelo.valor(selecionada, "simbolo")
            if selecionada is not None
            else None
        )
        self.t_cotacoes.definir(pd.DataFrame(linhas))
        if simbolo is not None:  # mantém a seleção depois de atualizar
            for i in range(self.t_cotacoes.filtro.rowCount()):
                indice = self.t_cotacoes.filtro.index(i, 0)
                if self.t_cotacoes.filtro.data(indice) == simbolo:
                    self.t_cotacoes.blockSignals(True)
                    self.t_cotacoes.selectRow(i)
                    self.t_cotacoes.blockSignals(False)
                    break

    def _mostrar_grafico(self) -> None:
        linha = self.t_cotacoes.linha_selecionada()
        if linha is None or self._conexao is None:
            return
        simbolo = self.t_cotacoes.modelo.valor(linha, "simbolo")
        try:
            candles = self._conexao.candles(
                simbolo,
                "D1",
                pd.Timestamp.now(tz="UTC").to_pydatetime() - pd.Timedelta(days=365),
            )
        except Exception as erro:  # noqa: BLE001
            self.c_grafico.titulo.setText(f"Gráfico diário — sem dados ({erro})")
            return
        self.c_grafico.titulo.setText(f"Gráfico diário — {simbolo}")
        self.g_velas.definir(candles)
