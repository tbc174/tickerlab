"""Alertas de entrega de DFP e ITR fora do prazo da CVM (Research R1), sem internet."""

import io
import zipfile
from datetime import date

import pandas as pd
import sqlalchemy as sa
from hypothesis import given
from hypothesis import strategies as st

from base.dias_uteis import feriados_nacionais
from scripts import atualizar_fundamentos
from src import demonstracoes as dm
from src import prazos
from src.banco.conexao import criar_engine

INDICE = """CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC
11.111.111/0001-11;2023-12-31;1;ATRASADA S.A.;1;DFP;10;2024-05-20;http://www.rad.cvm.gov.br/x?d=10
11.111.111/0001-11;2023-12-31;2;ATRASADA S.A.;1;DFP;11;2024-06-30;http://www.rad.cvm.gov.br/x?d=11
22.222.222/0001-22;2023-12-31;2;EM DIA S.A.;2;DFP;21;2024-08-01;http://www.rad.cvm.gov.br/x?d=21
22.222.222/0001-22;2023-12-31;1;EM DIA S.A.;2;DFP;20;2024-04-01;http://www.rad.cvm.gov.br/x?d=20
"""


def _zip_do_indice() -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("dfp_cia_aberta_2023.csv", INDICE.encode("cp1252"))
    return saida.getvalue()


def test_prazos_da_cvm_com_fim_de_semana():
    assert prazos.prazo("DFP", date(2025, 12, 31)) == date(2026, 3, 31)
    # 31/03/2024 foi domingo: o prazo vai para a segunda, 01/04
    assert prazos.prazo("DFP", date(2023, 12, 31)) == date(2024, 4, 1)
    assert prazos.prazo("ITR", date(2026, 6, 30)) == date(2026, 8, 14)  # 45 dias


def test_conta_a_primeira_entrega_e_ignora_reapresentacao_tardia():
    entregas = dm.ler_primeiras_entregas(_zip_do_indice(), "DFP")
    assert len(entregas) == 2
    assert set(entregas["primeira_entrega"]) == {date(2024, 5, 20), date(2024, 4, 1)}
    assert entregas["link"].str.startswith("https://").all()
    alertas = prazos.eventos_de_atraso(entregas)
    assert list(alertas["empresa"]) == [
        "ATRASADA S.A."
    ]  # a "em dia" só reapresentou depois
    alerta = alertas.iloc[0]
    assert "49 dias depois do prazo (01/04/2024)" in alerta["assunto"]
    assert (alerta["tema"], alerta["materialidade"]) == ("risco", 80)
    assert alerta["link"].endswith("d=10")  # o documento entregue com atraso


def test_atraso_curto_pesa_menos_e_um_dia_no_singular():
    entregas = pd.DataFrame(
        {
            "cnpj": ["1"], "empresa": ["X"], "documento": ["ITR"],
            "referencia": [date(2026, 6, 30)], "primeira_entrega": [date(2026, 8, 15)],
            "link": ["https://x"],
        }
    )  # fmt: skip
    alerta = prazos.eventos_de_atraso(entregas).iloc[0]
    assert alerta["materialidade"] == 50 and ", 1 dia depois" in alerta["assunto"]


def test_arquivo_sem_indice_nao_quebra():
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("outra_coisa.csv", "a;b\n")
    entregas = dm.ler_primeiras_entregas(saida.getvalue(), "DFP")
    assert entregas.empty and prazos.eventos_de_atraso(entregas).empty


def test_coleta_dos_fundamentos_grava_os_alertas(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'p.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)

    def baixar_falso(endereco: str) -> bytes | None:
        return (
            _zip_do_indice() if endereco.endswith("dfp_cia_aberta_2023.zip") else None
        )

    monkeypatch.setattr(atualizar_fundamentos, "baixar", baixar_falso)
    assert atualizar_fundamentos.main(["--anos", "10"]) == 0
    assert atualizar_fundamentos.main(["--anos", "10"]) == 0  # de novo: nada duplica
    with criar_engine(url).connect() as c:
        linhas = c.execute(sa.text("select fonte, rotulo from eventos")).all()
    assert linhas == [(prazos.FONTE_PRAZO, "DFP entregue fora do prazo")]


def test_prazo_pula_feriado_nacional():
    # 14/11/2021 foi domingo e 15/11, feriado: o prazo do ITR de 30/09 vai para a terça, 16/11
    assert prazos.prazo("ITR", date(2021, 9, 30)) == date(2021, 11, 16)
    # exercício em 30/11/2021: a DFP vencia em 28/02/2022, segunda de Carnaval; terça também
    assert prazos.prazo("DFP", date(2021, 11, 30)) == date(2022, 3, 2)


def test_dfp_do_emissor_estrangeiro_tem_4_meses():
    assert prazos.prazo("DFP", date(2025, 12, 31), estrangeiro=True) == date(
        2026, 4, 30
    )


def test_dfp_prorrogada_na_pandemia():
    # Deliberação CVM 849/2020 (redação da 852): +2 meses para exercícios de 31/12/2019 a 31/03/2020
    assert prazos.prazo("DFP", date(2019, 12, 31)) == date(
        2020, 6, 1
    )  # 31/05 foi domingo
    assert prazos.prazo("DFP", date(2020, 3, 31)) == date(2020, 8, 31)
    assert prazos.prazo("DFP", date(2020, 12, 31)) == date(
        2021, 3, 31
    )  # já sem prorrogação
    # a prorrogação vale só para o emissor nacional
    assert prazos.prazo("DFP", date(2019, 12, 31), estrangeiro=True) == date(
        2020, 4, 30
    )


def test_itr_prorrogado_na_pandemia():
    # Deliberação 849, item IV (redação da 852): +45 dias no 1º e no 3º trimestre do exercício
    assert prazos.prazo("ITR", date(2020, 3, 31)) == date(2020, 6, 29)
    assert prazos.prazo("ITR", date(2020, 6, 30), mes_fim_do_exercicio=3) == date(
        2020, 9, 28
    )
    assert prazos.prazo("ITR", date(2020, 3, 31), mes_fim_do_exercicio=6) == date(
        2020, 6, 29
    )
    # Deliberação 862: +15 dias no ITR de 30/06/2020, só para quem fecha o exercício em dezembro
    assert prazos.prazo("ITR", date(2020, 6, 30)) == date(
        2020, 8, 31
    )  # 29/08 foi sábado
    assert prazos.prazo("ITR", date(2020, 9, 30)) == date(
        2020, 11, 16
    )  # sem prorrogação


def test_itr_prorrogado_no_rio_grande_do_sul_em_2024():
    # Resolução CVM 202/2024 (enchentes): só para quem tem sede no RS; 30/06/2024 foi domingo
    assert prazos.prazo("ITR", date(2024, 3, 31), uf="RS") == date(2024, 7, 1)
    assert prazos.prazo("ITR", date(2024, 3, 31), uf=" rs ") == date(2024, 7, 1)
    assert prazos.prazo("ITR", date(2024, 3, 31), uf="SP") == date(2024, 5, 15)
    assert prazos.prazo("ITR", date(2024, 3, 31)) == date(2024, 5, 15)
    assert prazos.prazo("ITR", date(2024, 6, 30), uf="RS") == date(2024, 8, 14)


_FINS_DE_TRIMESTRE = st.builds(
    lambda ano, mes: pd.Timestamp(ano, mes, 1) + pd.offsets.MonthEnd(0),
    st.integers(2009, 2030),
    st.sampled_from([3, 6, 9, 12]),
).map(lambda dia: dia.date())


@given(
    documento=st.sampled_from(["DFP", "ITR"]),
    referencia=_FINS_DE_TRIMESTRE,
    mes_fim=st.sampled_from([3, 6, 9, 12]),
    uf=st.sampled_from([None, "RS", "SP"]),
    estrangeiro=st.booleans(),
)
def test_prazo_cai_em_dia_util_e_nunca_antes_do_normal(
    documento, referencia, mes_fim, uf, estrangeiro
):
    limite = prazos.prazo(
        documento,
        referencia,
        mes_fim_do_exercicio=mes_fim,
        uf=uf,
        estrangeiro=estrangeiro,
    )
    assert limite.weekday() < 5 and limite not in feriados_nacionais(limite.year)
    meses = 4 if estrangeiro else 3
    normal = (
        (pd.Timestamp(referencia) + pd.DateOffset(months=meses)).date()
        if documento == "DFP"
        else referencia + pd.Timedelta(days=45)
    )
    assert normal <= limite
