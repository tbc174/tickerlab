"""Papel da v0.2: a rodada agendada grava o dia aberto, espera o dado que não saiu e registra a falta
do dia vencido. Sem internet: carregadores e séries são dublês."""

from datetime import date, datetime

import pytest

from trader import criterio_quant
from trader.papel import gravar as gv
from trader.papel import registro as rg
from trader.papel.dados import DadoAindaNaoSaiuError
from trader.papel.series import Serie

MERGE = date(2026, 11, 5)
INICIO = date(2026, 11, 6)  # sexta


def _hora(dia: date, hora: int, minuto: int = 0) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=rg.BRASILIA)


class Relogio:
    def __init__(self, agora: datetime) -> None:
        self.agora = agora

    def __call__(self) -> datetime:
        return self.agora


def _fotografar(entradas, fechamento: date, primeiro: date) -> dict:
    return {
        "fechamento": fechamento.isoformat(),
        "primeiro": primeiro.isoformat(),
        "carteira": {"patrimonio": entradas},
        "cdi_do_dia": 0.0004,
    }


def _serie(nome: str, mercado: str) -> Serie:
    return Serie(
        nome=nome,
        titulo=nome,
        mercado=mercado,
        registro=0,
        sharpe_de_referencia=0.4,
        queda_do_desenvolvimento=-0.1,
        fotografar=_fotografar,
        sharpe_do_excesso=lambda r, c: 0.0,
    )


B3 = _serie("teste_b3", "b3")
CRIPTO = _serie("teste_cripto", "cripto")


class Carregador:
    """Devolve um número como 'dados'; `saiu_ate` diz até que fechamento a fonte já publicou."""

    def __init__(self, saiu_ate: date) -> None:
        self.saiu_ate = saiu_ate
        self.pedidos: list[tuple[date, date]] = []

    def __call__(self, fechamento: date, primeiro: date) -> float:
        self.pedidos.append((fechamento, primeiro))
        if fechamento > self.saiu_ate:
            raise DadoAindaNaoSaiuError(f"sem {fechamento}")
        return 100_000.0


@pytest.fixture
def papel(tmp_path) -> rg.RegistroDoPapel:
    registro = rg.RegistroDoPapel(tmp_path)
    registro.fixar_inicio(MERGE, "abc123", _hora(MERGE, 20))
    return registro


def _rodar(papel, relogio, carregadores, series=(B3,)):
    return [str(s) for s in gv.gravar_pendentes(papel, series, carregadores, relogio)]


def test_sem_inicio_nao_grava_nada(tmp_path):
    vazio = rg.RegistroDoPapel(tmp_path)
    situacoes = _rodar(
        vazio, Relogio(_hora(INICIO, 7)), {"teste_b3": Carregador(MERGE)}
    )
    assert situacoes == ["teste_b3: - sem início"]
    assert vazio.linhas("teste_b3") == []


def test_grava_o_dia_aberto_com_o_fechamento_da_vespera_e_o_primeiro_fechamento(papel):
    carregador = Carregador(MERGE)
    situacoes = _rodar(papel, Relogio(_hora(MERGE, 19, 30)), {"teste_b3": carregador})
    assert situacoes == ["teste_b3: 2026-11-06 gravado", "teste_b3: 2026-11-09 cedo"]
    assert carregador.pedidos == [(MERGE, MERGE)]
    linha = papel.linhas("teste_b3")[0]
    assert (linha["dia"], linha["fechamento"], linha["primeiro"]) == (
        "2026-11-06",
        "2026-11-05",
        "2026-11-05",
    )


def test_rodar_de_novo_nao_regrava_nem_carrega_de_novo(papel):
    carregador = Carregador(MERGE)
    relogio = Relogio(_hora(MERGE, 19, 30))
    _rodar(papel, relogio, {"teste_b3": carregador})
    relogio.agora = _hora(INICIO, 7)
    assert _rodar(papel, relogio, {"teste_b3": carregador}) == [
        "teste_b3: 2026-11-09 cedo"
    ]
    assert len(papel.linhas("teste_b3")) == 1
    assert len(carregador.pedidos) == 1


def test_dado_que_nao_saiu_espera_e_vira_falta_depois_do_prazo(papel):
    carregador = Carregador(date(2026, 11, 4))  # o fechamento de 05/11 ainda não saiu
    relogio = Relogio(_hora(MERGE, 19, 30))
    assert _rodar(papel, relogio, {"teste_b3": carregador}) == [
        "teste_b3: 2026-11-06 esperando"
    ]
    assert papel.linhas("teste_b3") == []
    relogio.agora = _hora(INICIO, 9, 45)  # o prazo da B3
    assert _rodar(papel, relogio, {"teste_b3": carregador}) == [
        "teste_b3: 2026-11-06 falta",
        "teste_b3: 2026-11-09 cedo",
    ]
    assert papel.linhas("teste_b3")[0]["tipo"] == rg.FALTA


def test_dias_vencidos_viram_falta_e_o_dia_aberto_e_gravado(papel):
    situacoes = _rodar(
        papel,
        Relogio(_hora(date(2026, 11, 10), 19)),
        {"teste_b3": Carregador(date(2026, 11, 30))},
    )
    assert situacoes == [
        "teste_b3: 2026-11-06 falta",
        "teste_b3: 2026-11-09 falta",
        "teste_b3: 2026-11-10 falta",
        "teste_b3: 2026-11-11 gravado",
        "teste_b3: 2026-11-12 cedo",
    ]
    papel.verificar("teste_b3")


def test_cripto_grava_todo_dia_ate_a_meia_noite(papel):
    carregadores = {
        "teste_b3": Carregador(MERGE),
        "teste_cripto": Carregador(date(2026, 11, 7)),
    }
    relogio = Relogio(_hora(date(2026, 11, 7), 23, 30))  # sábado à noite
    situacoes = _rodar(papel, relogio, carregadores, series=(B3, CRIPTO))
    assert "teste_cripto: 2026-11-06 falta" in situacoes  # o prazo era 0h de 06/11
    assert "teste_cripto: 2026-11-07 falta" in situacoes
    assert "teste_cripto: 2026-11-08 gravado" in situacoes
    assert "teste_cripto: 2026-11-09 cedo" in situacoes
    primeiro = carregadores["teste_cripto"].pedidos[-1][1]
    assert primeiro == date(2026, 11, 5)  # a véspera do início, em dias corridos


def test_pre_registro_alterado_para_tudo(papel, monkeypatch):
    def recusar():
        raise criterio_quant.PreRegistroAlteradoError("mudou")

    monkeypatch.setattr(gv.criterio_quant, "conferir", recusar)
    with pytest.raises(criterio_quant.PreRegistroAlteradoError):
        _rodar(papel, Relogio(_hora(MERGE, 19, 30)), {"teste_b3": Carregador(MERGE)})
    assert papel.linhas("teste_b3") == []


def test_duas_rodadas_ao_mesmo_tempo_nao_escrevem_juntas(papel):
    relogio = Relogio(_hora(MERGE, 19, 30))
    (papel.pasta / gv.NOME_DA_TRAVA).write_text(
        _hora(MERGE, 19, 10).isoformat(), encoding="utf-8"
    )
    with pytest.raises(gv.RodadaEmAndamentoError):
        _rodar(papel, relogio, {"teste_b3": Carregador(MERGE)})
    assert papel.linhas("teste_b3") == []
    # uma trava de mais de uma hora é de uma rodada que morreu: a nova segue
    (papel.pasta / gv.NOME_DA_TRAVA).write_text(
        _hora(MERGE, 18, 0).isoformat(), encoding="utf-8"
    )
    assert (
        _rodar(papel, relogio, {"teste_b3": Carregador(MERGE)})[0]
        == "teste_b3: 2026-11-06 gravado"
    )
    assert not (papel.pasta / gv.NOME_DA_TRAVA).exists()


def test_a_linha_de_comando_fixa_o_inicio_uma_vez(tmp_path, capsys):
    assert (
        gv.main(
            ["--pasta", str(tmp_path), "--iniciar", "2026-11-05", "--commit", "abc123"]
        )
        == 0
    )
    assert "2026-11-06" in capsys.readouterr().out
    with pytest.raises(rg.RegravarRecusadoError):
        gv.main(
            ["--pasta", str(tmp_path), "--iniciar", "2026-11-09", "--commit", "def456"]
        )
    with pytest.raises(SystemExit):
        gv.main(["--pasta", str(tmp_path / "outra"), "--iniciar", "2026-11-05"])


def test_a_linha_de_comando_verifica_as_cadeias(papel, capsys):
    _rodar(papel, Relogio(_hora(MERGE, 19, 30)), {"teste_b3": Carregador(MERGE)})
    assert gv.main(["--pasta", str(papel.pasta), "--verificar"]) == 0
    assert "teste_b3: 1 linhas, cadeia confere" in capsys.readouterr().out
