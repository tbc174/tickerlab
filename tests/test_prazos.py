"""Alertas de entrega de DFP e ITR fora do prazo da CVM (Research R1), sem internet."""

import io
import zipfile
from datetime import date

import pandas as pd
import sqlalchemy as sa

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
