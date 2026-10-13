"""Carga do FRE no banco (série 2 da base de ML, PR 6): proventos por exercício e eventos de capital,
sem duplicar quando o mesmo exercício aparece no FRE de vários anos (vale o documento mais novo), com
o original no acervo e no registro de coletas. Sem internet."""

from datetime import date

import pytest
import sqlalchemy as sa

from scripts import atualizar_fre
from src import acervo
from src.banco import fre as repo_fre
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import coletas, fre_eventos_de_capital, fre_proventos
from tests.test_base_fre import AUMENTO, DESDOBRAMENTO, DIV, DIV_CLASSE, _zip

A = "11.111.111/0001-11"


def _fre_do_ano(ano: int, total: float) -> bytes:
    ref = f"{ano}-01-01"
    return _zip(
        {
            "distribuicao_dividendos": [
                DIV,
                f"{A};{ref};1;9;EMPRESA A;2020-01-01;2020-12-31;1000.00;10.0;500.00;50.00;{total};",
            ],
            "distribuicao_dividendos_classe_acao": [DIV_CLASSE],
            "capital_social_desdobramento": [
                DESDOBRAMENTO,
                f"{A};{ref};1;9;EMPRESA A;1;2020-08-03;Desdobramento;100;0;100;1000;0;1000",
            ],
            "capital_social_aumento": [AUMENTO],
        },
        ano=ano,
    )


@pytest.fixture
def url(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'f.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    migrar_para("head", url=url)
    return url


def test_migracao_sobe_e_desce(url):
    motor = criar_engine(url)
    try:
        assert {"fre_proventos", "fre_eventos_de_capital"} <= set(
            sa.inspect(motor).get_table_names()
        )
        desfazer_ate("0028", url=url)
        assert "fre_proventos" not in sa.inspect(motor).get_table_names()
        migrar_para("head", url=url)
    finally:
        motor.dispose()


def test_o_mesmo_exercicio_em_varios_fres_fica_uma_vez_com_o_mais_novo(
    url, monkeypatch
):
    arquivos = {2021: _fre_do_ano(2021, 400.0), 2022: _fre_do_ano(2022, 500.0)}
    monkeypatch.setattr(
        atualizar_fre,
        "baixar",
        lambda endereco: arquivos.get(int(endereco.rsplit("_", 1)[-1][:4])),
    )
    assert atualizar_fre.main(["--desde", "2021", "--ate", "2022"]) == 0
    assert (
        atualizar_fre.main(["--desde", "2021", "--ate", "2022"]) == 0
    )  # de novo: nada duplica
    motor = criar_engine(url)
    try:
        with motor.connect() as c:
            proventos = c.execute(sa.select(fre_proventos)).all()
            eventos = c.execute(sa.select(fre_eventos_de_capital)).all()
            lidos = repo_fre.proventos_de(c, A)
        assert len(proventos) == 1 and proventos[0].dividendo_total == pytest.approx(
            500.0
        )
        assert proventos[0].referencia == date(2022, 1, 1)  # o FRE mais novo
        assert len(eventos) == 1 and eventos[0].fator == pytest.approx(10.0)
        assert list(lidos["exercicio"]) == [date(2020, 12, 31)]
    finally:
        motor.dispose()


def test_ano_que_nao_existe_na_cvm_e_pulado(url, monkeypatch):
    monkeypatch.setattr(atualizar_fre, "baixar", lambda endereco: None)
    assert atualizar_fre.main(["--desde", "2009", "--ate", "2009"]) == 0
    motor = criar_engine(url)
    try:
        with motor.connect() as c:
            assert (
                c.execute(
                    sa.select(sa.func.count()).select_from(fre_proventos)
                ).scalar()
                == 0
            )
    finally:
        motor.dispose()


def test_coleta_de_verdade_registra_o_original(url, monkeypatch):
    monkeypatch.setattr(
        atualizar_fre, "_baixar_da_fonte", lambda endereco: _fre_do_ano(2022, 500.0)
    )
    monkeypatch.setattr(
        atualizar_fre,
        "baixar",
        atualizar_fre.com_registro("cvm-fre", atualizar_fre._baixar_da_fonte),
    )
    assert atualizar_fre.main(["--desde", "2022", "--ate", "2022"]) == 0
    motor = criar_engine(url)
    try:
        with motor.connect() as c:
            [linha] = c.execute(sa.select(coletas)).all()
        assert linha.fonte == "cvm-fre" and linha.caminho_do_original
    finally:
        motor.dispose()
