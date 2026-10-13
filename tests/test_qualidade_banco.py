"""Achados das regras de qualidade no banco (série 1 da base de ML, PR 3): gravar de novo não
duplica, achado que sumiu é fechado (nunca apagado) e "como era na data" não olha o futuro."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest
import sqlalchemy as sa

from base.regras import Achado
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import achados_de_qualidade
from src.banco.qualidade import achados_de, gravar_achados

ENTREGA = datetime(2024, 3, 28, 18, tzinfo=UTC)
PRIMEIRA_RODADA = datetime(2026, 10, 13, 7, tzinfo=UTC)
SEGUNDA_RODADA = PRIMEIRA_RODADA + timedelta(days=1)
DFP_2023 = pd.Timestamp("2023-12-31")
CNPJ = "00.000.000/0001-91"


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{(tmp_path / 'q.sqlite').as_posix()}"


@pytest.fixture
def motor(url):
    migrar_para("head", url=url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()


def _achado(
    regra="R1", conta="1", valor=100.0, porque="Ativo diferente do passivo.", **outros
):
    campos = {
        "regra": regra,
        "cnpj": CNPJ,
        "documento": "DFP",
        "referencia": DFP_2023,
        "grupo": "con",
        "conta": conta,
        "valor": valor,
        "valor_esperado": 90.0,
        "porque": porque,
        "valido_desde": ENTREGA,
    }
    return Achado(**(campos | outros))


def _gravar(conexao, achados, agora, regras=("R1", "R4")):
    return gravar_achados(
        conexao,
        achados,
        regras=regras,
        documento="DFP",
        referencias=[DFP_2023],
        agora=agora,
    )


def _todas(conexao):
    return list(conexao.execute(sa.select(achados_de_qualidade)))


def test_migracao_0026_sobe_e_desce(url):
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        assert "achados_de_qualidade" in sa.inspect(motor).get_table_names()
        desfazer_ate("0025", url=url)
        assert "achados_de_qualidade" not in sa.inspect(motor).get_table_names()
        migrar_para("head", url=url)
        assert "achados_de_qualidade" in sa.inspect(motor).get_table_names()
    finally:
        motor.dispose()


def test_gravar_de_novo_o_mesmo_achado_nao_duplica(motor):
    with motor.begin() as c:
        resumo = _gravar(c, [_achado()], PRIMEIRA_RODADA)
        assert (resumo.novos, resumo.fechados) == (1, 0)
    with motor.begin() as c:
        resumo = _gravar(c, [_achado(porque="Texto revisado.")], SEGUNDA_RODADA)
        assert (resumo.novos, resumo.atualizados, resumo.fechados) == (0, 1, 0)
        linhas = _todas(c)
    assert len(linhas) == 1
    assert linhas[0].porque == "Texto revisado."
    assert (
        linhas[0].valido_desde.replace(tzinfo=UTC) == ENTREGA
    )  # a data de origem não muda


def test_achado_que_sumiu_e_fechado_e_nao_apagado(motor):
    with motor.begin() as c:
        _gravar(
            c,
            [_achado(), _achado(regra="R4", conta="1.01.01", valor=-5.0)],
            PRIMEIRA_RODADA,
        )
    with motor.begin() as c:
        resumo = _gravar(c, [_achado()], SEGUNDA_RODADA)
        linhas = {linha.regra: linha for linha in _todas(c)}
    assert resumo.fechados == 1
    assert linhas["R4"].fechado_em.replace(tzinfo=UTC) == SEGUNDA_RODADA
    assert linhas["R1"].fechado_em is None


def test_regra_que_nao_rodou_nao_fecha_os_achados_dela(motor):
    with motor.begin() as c:
        _gravar(
            c,
            [_achado(regra="R8", grupo="", conta="")],
            PRIMEIRA_RODADA,
            regras=("R8",),
        )
    with motor.begin() as c:
        _gravar(c, [_achado()], SEGUNDA_RODADA, regras=("R1",))
        abertos = [linha.regra for linha in _todas(c) if linha.fechado_em is None]
    assert sorted(abertos) == ["R1", "R8"]


def test_achado_que_volta_depois_de_fechado_abre_uma_linha_nova(motor):
    with motor.begin() as c:
        _gravar(c, [_achado()], PRIMEIRA_RODADA)
    with motor.begin() as c:
        _gravar(c, [], SEGUNDA_RODADA)
    with motor.begin() as c:
        _gravar(c, [_achado()], SEGUNDA_RODADA + timedelta(days=1))
        linhas = _todas(c)
    assert len(linhas) == 2
    assert sum(linha.fechado_em is None for linha in linhas) == 1


def test_achado_sem_data_de_origem_e_recusado(motor):
    with motor.begin() as c, pytest.raises(ValueError, match="valido_desde"):
        _gravar(c, [_achado(valido_desde=None)], PRIMEIRA_RODADA)


def test_achado_fora_do_documento_rodado_e_recusado(motor):
    with motor.begin() as c, pytest.raises(ValueError, match="fora"):
        _gravar(c, [_achado(referencia=pd.Timestamp("2022-12-31"))], PRIMEIRA_RODADA)


def test_valor_vazio_vira_nulo(motor):
    with motor.begin() as c:
        _gravar(c, [_achado(valor=float("nan"))], PRIMEIRA_RODADA)
        assert _todas(c)[0].valor is None


def test_achados_de_le_os_abertos_e_como_era_na_data(motor):
    with motor.begin() as c:
        _gravar(c, [_achado()], PRIMEIRA_RODADA)
    with motor.begin() as c:
        _gravar(c, [], SEGUNDA_RODADA)
    with motor.connect() as c:
        assert achados_de(c, CNPJ) == []
        antes_da_entrega = achados_de(c, CNPJ, em=ENTREGA - timedelta(days=1))
        entre_as_rodadas = achados_de(c, CNPJ, em=PRIMEIRA_RODADA + timedelta(hours=1))
        assert achados_de(c, "11.111.111/0001-11", em=PRIMEIRA_RODADA) == []
    assert antes_da_entrega == []  # o achado não existia antes da DFP ser entregue
    assert [a.regra for a in entre_as_rodadas] == ["R1"]
    assert entre_as_rodadas[0].referencia == date(2023, 12, 31)
