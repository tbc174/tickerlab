"""ABS-EE da SEC em tape (src/securitizacao/abs_ee.py) e o validador da B-10 num arquivo real.

Aceite da B-14: o validador roda num ABS-EE real sem alterar código. A amostra é um recorte, sem edição,
do arquivo de ativos do CarMax Select Receivables Trust 2026-C (ver `dados_de_exemplo/securitizacao/LEIAME.md`).
"""

import io
from pathlib import Path

import pytest

from scripts.validar_abs_ee import main, resumo
from src.securitizacao.abs_ee import ESQUEMA_AUTO, tape_de_abs_ee
from src.securitizacao.tape import CEDENTE_INVALIDO, SACADO_INVALIDO, validar_tape

AMOSTRA = Path("dados_de_exemplo/securitizacao/abs_ee_carmax_2026c_amostra.xml")


def _xml(*ativos: str, esquema: str = ESQUEMA_AUTO) -> io.BytesIO:
    corpo = "".join(f"<assets>{a}</assets>" for a in ativos)
    return io.BytesIO(f'<assetData xmlns="{esquema}">{corpo}</assetData>'.encode())


def _ativo(**mudancas: str) -> str:
    campos = {
        "assetNumber": "abc==",
        "reportingPeriodEndingDate": "09-30-2026",
        "originatorName": "CBS",
        "originationDate": "10/2020",
        "originalLoanAmount": "23046.74",
        "loanMaturityDate": "02/2027",
        "reportingPeriodActualEndBalanceAmount": "2324.34",
    }
    campos.update(mudancas)
    return "".join(f"<{k}>{v}</{k}>" for k, v in campos.items())


def test_amostra_real_passa_pelo_validador_sem_mexer_nele():
    with AMOSTRA.open("rb") as arquivo:
        tape = tape_de_abs_ee(arquivo)
    achados = validar_tape(tape)
    assert tape["data_de_corte"] == "2026-09-30"
    assert len(tape["recebiveis"]) == 30
    # o ABS-EE não tem CNPJ: só T07 e T08, uma vez por linha; nenhuma outra regra acusa
    assert {a.regra for a in achados} == {CEDENTE_INVALIDO, SACADO_INVALIDO}
    assert len(achados) == 60


def test_campos_viram_centavos_e_ultimo_dia_do_mes():
    (r,) = tape_de_abs_ee(_xml(_ativo()))["recebiveis"]
    assert r["valor_face"] == 2304674
    assert r["saldo"] == 232434
    assert r["valor_pago"] == 2304674 - 232434
    assert (r["emissao"], r["vencimento"]) == ("2020-10-31", "2027-02-28")
    assert r["recebivel_id"] == r["sacado_cnpj"] == "abc=="
    assert r["cedente_cnpj"] == "CBS"


def test_saldo_maior_que_a_face_aparece_como_erro_de_esquema():
    tape = tape_de_abs_ee(
        _xml(_ativo(reportingPeriodActualEndBalanceAmount="30000.00"))
    )
    assert any(a.regra == "T01" and a.campo == "valor_pago" for a in validar_tape(tape))


def test_data_ilegivel_vira_achado_e_nao_excecao():
    tape = tape_de_abs_ee(_xml(_ativo(originationDate="13/2020")))
    assert tape["recebiveis"][0]["emissao"] is None
    assert any(a.regra == "T01" and a.campo == "emissao" for a in validar_tape(tape))


def test_limite_corta_nos_primeiros_ativos():
    arquivo = _xml(
        _ativo(assetNumber="a"), _ativo(assetNumber="b"), _ativo(assetNumber="c")
    )
    assert len(tape_de_abs_ee(arquivo, limite=2)["recebiveis"]) == 2


def test_esquema_de_outro_tipo_de_abs_nao_e_lido_em_silencio():
    outro = "http://www.sec.gov/edgar/document/absee/cmbs/assetdata"
    with pytest.raises(ValueError, match="não suportado"):
        tape_de_abs_ee(_xml(_ativo(), esquema=outro))


def test_arquivo_sem_ativos_e_erro():
    with pytest.raises(ValueError, match="nenhum ativo"):
        tape_de_abs_ee(_xml())


def test_corte_diferente_entre_ativos_e_erro():
    arquivo = _xml(_ativo(), _ativo(reportingPeriodEndingDate="08-31-2026"))
    with pytest.raises(ValueError, match="data de corte"):
        tape_de_abs_ee(arquivo)


def test_script_resume_achados_por_regra(capsys):
    assert main([str(AMOSTRA), "--limite", "5"]) == 0
    saida = capsys.readouterr().out
    assert "5 ativos" in saida
    assert "T07: 5" in saida and "T08: 5" in saida
    assert "fora T07/T08 (CNPJ que o ABS-EE não tem): 0" in saida


def test_resumo_devolve_linhas():
    assert resumo(AMOSTRA, 3)[0].startswith("data de corte 2026-09-30 · 3 ativos")
