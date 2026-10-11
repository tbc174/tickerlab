"""Painel do trader (PySide6), sem abrir janela de verdade (Qt "offscreen").

Só roda no Windows: o trader inteiro é do Windows, e no Linux do CI o Qt precisaria de
bibliotecas gráficas extras. Os testes conferem comportamento; a conferência visual é do Tiago.
"""

import os
import sys

import pytest

if sys.platform != "win32":
    pytest.skip("Interface do trader: só no Windows.", allow_module_level=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import numpy as np
import pandas as pd

from tests.test_trader_mt5 import CANDLES, MT5Falso, _rates
from trader import armazem
from trader.interface import tema
from trader.interface.__main__ import criar_aplicacao
from trader.interface.componentes import formatar
from trader.interface.fontes import Fontes
from trader.interface.janela import Janela
from trader.interface.tarefas import Comando, Tarefa
from trader.interface.telas import TelaMercado, TelaPesquisa
from trader.mt5 import ConexaoMT5
from trader.registro import Registro


@pytest.fixture(scope="module")
def app():
    return criar_aplicacao([])


def _serie(n=600, media=0.0003, seed=1):
    rng = np.random.default_rng(seed)
    return pd.Series(
        rng.normal(media, 0.01, n), index=pd.bdate_range("2000-01-03", periods=n)
    )


@pytest.fixture
def raiz(tmp_path):
    """Uma pasta de repositório falsa com tudo o que as telas leem."""
    (tmp_path / "dados_mt5").mkdir()
    pd.DataFrame(
        {
            "arquivo": ["EURUSD", "PETR4.SA"],
            "simbolo": ["EURUSD", "PETR4.SA"],
            "fonte": ["mt5", "yfinance"],
            "classe": ["forex", "acoes_b3"],
            "papel": ["operar", "operar"],
            "situacao": ["ok", "reparada"],
            "linhas": [6000, 6700],
            "inicio": ["2001-10-18", "2000-01-03"],
            "fim": ["2026-10-09", "2026-10-09"],
            "reparados": [0, 92],
            "saltos_suspeitos": [3, 40],
            "proxy_de": ["", ""],
        }
    ).to_csv(tmp_path / "dados_mt5" / "relatorio_de_qualidade.csv", index=False)
    b3 = tmp_path / "dados_b3" / "futuros"
    b3.mkdir(parents=True)
    pd.DataFrame({"x": [1]}).to_parquet(b3 / "2026-10-09.parquet")
    (tmp_path / "dados_juros").mkdir()
    pd.DataFrame(
        {"BRL": [13.75, 13.75], "USD": [3.875, 3.875]},
        index=pd.to_datetime(["2026-10-05", "2026-10-06"]),
    ).to_parquet(tmp_path / "dados_juros" / "taxas_basicas.parquet")

    pesquisa = tmp_path / "pesquisa_m2"
    registro = Registro(pesquisa / "registro.db", commit_fn=lambda: "abc1234")
    series = pesquisa / "series"
    for i, nome in enumerate(("B0", "B1", "B2")):
        t = registro.registrar("H0", f"baseline_{nome}", {"baseline": nome})
        s = _serie(seed=i)
        registro.salvar_resultado(
            t,
            {
                "carteira": {
                    "x1": {"sharpe": 0.1 * i, "t": 0.5},
                    "x2": {"sharpe": 0.0, "t": 0.0},
                }
            },
        )
        armazem.salvar(
            registro.obter(t)["hash"], s, s - 0.0001, series, apelido=f"baseline_{nome}"
        )
    modelo = registro.registrar("H1", "logistica_v1", {"modelo": "logistica"})
    itens = [
        {
            "codigo": "A1",
            "descricao": "DSR",
            "valor": 0.0,
            "limite": ">= 0.95",
            "passou": False,
        },
        {
            "codigo": "A3",
            "descricao": "t",
            "valor": 0.34,
            "limite": ">= 3.0",
            "passou": False,
        },
        {
            "codigo": "V",
            "descricao": "vazamento",
            "valor": None,
            "limite": "todas",
            "passou": True,
        },
    ]
    registro.salvar_resultado(
        modelo,
        {
            "aprovado": False,
            "reprovados": ["A1", "A3"],
            "itens": itens,
            "sharpes_dos_caminhos": [
                0.07,
                0.07,
                0.08,
                0.02,
                0.10,
                0.07,
                -0.01,
                -0.13,
                0.11,
            ],
            "vazamento": {
                "sharpe_normal": 0.07,
                "sharpe_futuro": 22.8,
                "sharpe_embaralhado": 0.41,
                "limite_do_embaralhado": 0.42,
            },
            "acaso": {"p_valor": 0.302},
        },
    )
    armazem.salvar(
        registro.obter(modelo)["hash"], _serie(seed=9), _serie(seed=9), series
    )
    relatorios = pesquisa / "relatorios"
    relatorios.mkdir(parents=True)
    pd.DataFrame(
        {
            "baseline": ["B1", "B1"],
            "simbolo": ["EURUSD", "PETR4.SA"],
            "classe": ["forex", "acoes_b3"],
            "sharpe": [0.13, 0.18],
            "t": [0.6, 0.9],
            "retorno_anual": [0.007, 0.009],
            "maior_queda": [-0.25, -0.18],
            "giro_por_ano": [12.0, 2.2],
            "custo_anual_em_sharpe": [0.02, 0.02],
            "swap_por_ano": [-0.002, -0.006],
        }
    ).to_csv(relatorios / "baselines_por_ativo.csv", index=False)
    pd.DataFrame(
        {
            "simbolo": ["EURUSD"],
            "classe": ["forex"],
            "movimento_maior_que_custo_1d": [0.96],
        }
    ).to_csv(relatorios / "viabilidade.csv", index=False)
    (relatorios / "viabilidade_resumo.json").write_text(
        '{"ativos": 56, "apostas_independentes": 9.3, "correlacao_media": 0.15}',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def janela(app, qtbot, raiz):
    j = Janela(Fontes(raiz, agora=pd.Timestamp("2026-10-11 12:00")))
    qtbot.addWidget(j)
    return j


# --- tema e formatação -----------------------------------------------------------------------


def test_folha_de_estilo_usa_os_tokens():
    estilo = tema.folha_de_estilo()
    for cor in ("#121212", "#1a1a19", "#3987e5", "#ececea"):
        assert cor in estilo
    assert tema.FONTE in estilo


def test_manrope_vem_do_repositorio_e_alinha_os_numeros(app):
    from PySide6.QtGui import QFontInfo, QFontMetrics

    from trader.interface.componentes import fonte_tabular

    assert tema.ARQUIVO_DA_FONTE.exists()
    assert (tema.ARQUIVO_DA_FONTE.parent / "OFL.txt").exists()  # a licença vai junto
    assert QFontInfo(app.font()).family() == "Manrope"
    medida = QFontMetrics(fonte_tabular())
    assert medida.horizontalAdvance("1") == medida.horizontalAdvance("8")


def test_ganho_e_perda_nunca_so_pela_cor():
    assert formatar(0.012, "variacao") == "▲ +1,20%"
    assert formatar(-0.008, "variacao") == "▼ -0,80%"
    assert tema.cor_da_variacao(0.01) == tema.CORES["ganho"]
    assert tema.cor_da_variacao(-0.01) == tema.CORES["perda"]
    assert formatar("reprovado", "veredito").startswith("✕")
    assert formatar("aprovado", "veredito").startswith("✓")
    assert formatar(np.nan, "num2") == "—"
    assert formatar(1234.5, "num2") == "1.234,50"


# --- janela e telas --------------------------------------------------------------------------


def test_janela_abre_e_navega_por_todas_as_telas(janela, qtbot):
    janela.show()
    for i in range(len(janela.telas)):
        janela.ir_para(i)
        assert janela.pilha.currentIndex() == i
        assert janela.grupo.button(i).isChecked()
    assert "4/300 tentativas" in janela.s_tentativas.text()
    assert "intacto" in janela.s_holdout.text()


def test_inicio_mostra_resumo_e_avisos(janela):
    inicio = janela.telas[0]
    inicio.atualizar()
    assert inicio.c_tentativas.valor.text() == "4"
    assert "restam 296" in inicio.c_tentativas.legenda.text()
    assert "logistica_v1" in inicio.c_melhor.legenda.text()
    assert inicio.t_frescor.modelo.rowCount() == 3


def test_pesquisa_filtra_e_mostra_o_veredito_item_a_item(janela, qtbot):
    pesquisa: TelaPesquisa = janela.telas[1]
    janela.ir_para(1)
    assert pesquisa.tabela.modelo.rowCount() == 4
    primeira = pesquisa.tabela.filtro.index(0, 0)
    assert pesquisa.tabela.filtro.data(primeira) == "4"  # a mais recente primeiro
    pesquisa.f_familia.setCurrentIndex(2)  # H1
    assert pesquisa.tabela.modelo.rowCount() == 1
    pesquisa.tabela.selectRow(0)
    assert "REPROVADO" in pesquisa.d_titulo.text() and "A1" in pesquisa.d_titulo.text()
    assert pesquisa.d_itens.modelo.rowCount() == 3
    assert "22,80" in pesquisa.d_notas.text()
    pesquisa.f_familia.setCurrentIndex(0)
    pesquisa.f_busca.setText("baseline_B1")
    assert pesquisa.tabela.modelo.rowCount() == 1


def test_filtro_tem_todas_as_familias_do_registro(janela):
    from trader.registro import FAMILIAS

    pesquisa: TelaPesquisa = janela.telas[1]
    no_filtro = {
        pesquisa.f_familia.itemText(i).split()[0]
        for i in range(1, pesquisa.f_familia.count())
    }
    assert no_filtro == set(FAMILIAS)


def test_texto_do_embaralhado_segue_a_regra_de_cada_versao():
    from trader.interface.telas import _texto_do_embaralhado

    novo = _texto_do_embaralhado(
        {
            "sharpe_embaralhado": -0.16,
            "sharpe_proporcao": 0.23,
            "sharpe_da_diferenca": -0.74,
            "limite_da_diferenca": 0.46,
        }
    )
    assert "proporção 0,23" in novo and "acima de +0,46" in novo
    antigo = _texto_do_embaralhado(
        {"sharpe_embaralhado": 0.41, "limite_do_embaralhado": 0.42}
    )
    assert "v0.1" in antigo and "±0,42" in antigo


def test_baselines_mostram_resumo_ativos_e_apostas(janela):
    janela.ir_para(2)
    tela = janela.telas[2]
    assert tela.t_resumo.modelo.rowCount() == 3
    assert tela.t_ativos.modelo.rowCount() == 2
    assert tela.c_apostas.valor.text() == "9,3"
    tela.f_classe.setCurrentText("forex")
    assert tela.t_ativos.modelo.rowCount() == 1


def test_baselines_sem_dados_mostra_estado_vazio(app, qtbot, tmp_path):
    j = Janela(Fontes(tmp_path))
    qtbot.addWidget(j)
    j.ir_para(2)
    assert not j.telas[2].vazio.isHidden()
    assert j.telas[2].c_resumo.isHidden()


def test_dados_mostra_qualidade_e_juros(janela):
    janela.ir_para(3)
    tela = janela.telas[3]
    assert tela.t_qualidade.modelo.rowCount() == 2
    tela.f_busca.setText("PETR4")
    assert tela.t_qualidade.filtro.rowCount() == 1
    assert set(tela.g_juros.series) == {"BRL", "USD"}


# --- mercado (MT5 falso) ---------------------------------------------------------------------


class MT5ComCotacao(MT5Falso):
    def symbol_info_tick(self, simbolo):
        return SimpleNamespace(bid=1.1000, ask=1.1002, time=1_700_000_000)


def test_mercado_conecta_lista_cotacoes_e_desenha_velas(app, qtbot, raiz):
    j = Janela(Fontes(raiz))
    qtbot.addWidget(j)
    mercado: TelaMercado = j.telas[4]
    mercado._abrir_conexao = lambda: ConexaoMT5(
        MT5ComCotacao(
            rates=_rates(CANDLES),
            simbolos=tuple(
                __import__("trader.interface.telas", fromlist=["x"]).SIMBOLOS_DO_MT5
            ),
        )
    )
    j.ir_para(4)
    mercado.conectar()
    assert mercado.conectado and mercado.aviso.isHidden()
    assert "conectado" in j.s_mt5.text()
    assert mercado.t_cotacoes.modelo.rowCount() > 0
    mercado.t_cotacoes.selectRow(0)
    assert "Gráfico diário —" in mercado.c_grafico.titulo.text()
    assert not mercado.g_velas.velas.boundingRect().isEmpty()
    mercado.desconectar()
    assert not mercado.conectado and "desconectado" in j.s_mt5.text()


def test_mercado_recusa_conta_real_com_mensagem_clara(app, qtbot, raiz):
    j = Janela(Fontes(raiz))
    qtbot.addWidget(j)
    mercado: TelaMercado = j.telas[4]
    mercado._abrir_conexao = lambda: ConexaoMT5(
        MT5ComCotacao(modo=2, rates=_rates(CANDLES))
    )
    mercado.conectar()
    assert not mercado.conectado
    assert "DEMO" in mercado.aviso.texto.text()


def test_mercado_sem_terminal_fica_desconectado(app, qtbot, raiz):
    j = Janela(Fontes(raiz))
    qtbot.addWidget(j)
    mercado: TelaMercado = j.telas[4]
    mercado._abrir_conexao = lambda: ConexaoMT5(MT5Falso(inicializa=False))
    mercado.conectar()
    assert not mercado.conectado
    assert "Não conectou" in mercado.aviso.texto.text()


# --- tarefas ---------------------------------------------------------------------------------


def test_tarefa_roda_um_comando_e_avisa_o_fim(app, qtbot):
    tarefa = Tarefa(Comando("teste", "Teste", "platform"))
    linhas = []
    tarefa.progresso.connect(linhas.append)
    with qtbot.waitSignal(tarefa.terminou, timeout=30000) as sinal:
        tarefa.iniciar()
    ok, resumo = sinal.args
    assert ok and "Teste: concluído" in resumo and linhas


def test_tarefa_cancelada_avisa(app, qtbot):
    tarefa = Tarefa(Comando("lenta", "Lenta", "http.server", ("0",)))
    with qtbot.waitSignal(tarefa.terminou, timeout=30000) as sinal:
        tarefa.iniciar()
        qtbot.waitUntil(lambda: tarefa.rodando, timeout=10000)
        tarefa.cancelar()
    ok, resumo = sinal.args
    assert not ok and "cancelado" in resumo


def test_janela_nao_deixa_duas_tarefas_ao_mesmo_tempo(janela, qtbot, monkeypatch):
    from trader.interface import tarefas

    monkeypatch.setitem(
        tarefas.COMANDOS, "lenta", Comando("lenta", "Lenta", "http.server", ("0",))
    )
    janela.executar("lenta")
    qtbot.waitUntil(lambda: janela.tarefa.rodando, timeout=10000)
    assert all(not b.isEnabled() for b in janela.telas[3].botoes.values())
    janela.executar("lenta")  # a segunda é recusada com aviso
    assert "Já existe uma tarefa" in janela.toast.text()
    with qtbot.waitSignal(janela.tarefa.terminou, timeout=30000):
        janela.cancelar_tarefa()
    assert all(b.isEnabled() for b in janela.telas[3].botoes.values())


def test_dados_aceita_relatorio_antigo_sem_proxy_de(app, qtbot, raiz):
    caminho = raiz / "dados_mt5" / "relatorio_de_qualidade.csv"
    pd.read_csv(caminho).drop(columns=["proxy_de"]).to_csv(caminho, index=False)
    j = Janela(Fontes(raiz))
    qtbot.addWidget(j)
    j.ir_para(3)
    assert j.telas[3].t_qualidade.modelo.rowCount() == 2
