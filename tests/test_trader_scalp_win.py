"""Fase 1 do scalp no mini índice (docs/pre-registro-scalp-win-fase1.md), com negócios inventados."""

import hashlib
import zipfile

import numpy as np
import pandas as pd
import pytest

from trader import scalp_win as sw

PREGAO = pd.Timestamp("2026-10-05")
FUSO = "America/Sao_Paulo"


def _instante(hora: str) -> pd.Timestamp:
    return pd.Timestamp(f"2026-10-05 {hora}").tz_localize(FUSO)


def _negocios(linhas: list[tuple]) -> pd.DataFrame:
    """Linhas (hora, preço) ou (hora, preço, campos que mudam, num dicionário)."""
    registros = []
    for numero, linha in enumerate(linhas, start=1):
        hora, preco, *extra = linha
        registro = {
            "instante": _instante(hora),
            "pregao": PREGAO,
            "simbolo": "WINV26",
            "preco": float(preco),
            "quantidade": 1,
            "sessao": 1,
            "cancelado": False,
            "identificador": numero * 10,
        }
        registro.update(extra[0] if extra else {})
        registros.append(registro)
    return pd.DataFrame(registros)


# --- contrato do dia ---
def _selo(linhas: list[tuple[str, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(linhas, columns=["simbolo", "volume_no_boletim", "selo"])


def test_o_contrato_principal_e_o_win_de_maior_volume_no_boletim():
    selo = _selo(
        [
            ("WINV26", 9e9, "completo"),
            ("WINZ26", 1e9, "incompleto"),
            ("WDOV26", 9e12, "completo"),
            ("WINV26C210000", 9e12, "completo"),  # opção: não é o futuro
        ]
    )
    assert sw.contrato_principal(selo) == ("WINV26", "completo")


def test_sem_win_no_selo_vira_erro_claro():
    with pytest.raises(ValueError, match="WIN"):
        sw.contrato_principal(_selo([("WDOV26", 1.0, "completo")]))


# --- limpeza dos negócios ---
def test_limpeza_tira_cancelado_inserido_after_outro_simbolo_e_outro_pregao():
    negocios = _negocios(
        [
            ("10:00:00", 100),
            ("10:00:01", 105),  # identificador 20: cancelado na linha de baixo
            ("10:00:02", 110, {"identificador": 31}),  # inserido depois
            ("10:00:03", 115, {"sessao": 6}),
            ("10:00:04", 120, {"simbolo": "WINZ26"}),
            ("10:00:05", 125, {"pregao": pd.Timestamp("2026-10-02")}),
            ("10:00:06", 105, {"identificador": 20, "cancelado": True}),
            ("10:00:07", 130),
        ]
    )
    limpos = sw.limpar_negocios(negocios, "WINV26", PREGAO)
    assert limpos["preco"].tolist() == [100.0, 130.0]


def test_limpeza_ordena_por_instante_e_identificador():
    negocios = _negocios(
        [("10:00:01", 200), ("10:00:00", 100, {"identificador": 50}), ("10:00:00", 150)]
    )
    limpos = sw.limpar_negocios(negocios, "WINV26", PREGAO)
    assert limpos["preco"].tolist() == [150.0, 100.0, 200.0]


# --- M1: custo do spread ---
def test_roll_recupera_o_spread_do_vai_e_vem_entre_compra_e_venda():
    gerador = np.random.default_rng(1)
    lado = gerador.choice([-1.0, 1.0], size=200_000)
    precos = 100_000 + lado * 5 / 2  # meio do mercado parado, spread de 1 tick
    assert sw.spread_de_roll(precos) == pytest.approx(5.0, rel=0.02)


def test_roll_e_zero_quando_a_covariancia_nao_e_negativa():
    assert sw.spread_de_roll(np.arange(0, 1000, 5, dtype=float)) == 0.0
    assert sw.spread_de_roll(np.array([100.0])) == 0.0


def test_fracao_de_um_tick_conta_so_mudancas_diferentes_de_zero():
    precos = np.array([100, 105, 105, 100, 110, 110], dtype=float)
    assert sw.fracao_de_um_tick(precos) == pytest.approx(2 / 3)
    assert np.isnan(sw.fracao_de_um_tick(np.array([100.0, 100.0])))


def test_empate_tem_piso_de_10_pontos():
    assert sw.empate(0.0) == 10.0
    assert sw.empate(5.0) == 10.0
    assert sw.empate(8.0) == 13.0


# --- grade de preços por minuto ---
def test_a_grade_vai_das_9h15_as_17h45_minuto_a_minuto():
    grade = sw.grade_de_precos(_negocios([("09:10:00", 100)]), PREGAO)
    assert grade.index[0] == _instante("09:15:00")
    assert grade.index[-1] == _instante("17:45:00")
    assert len(grade) == 8 * 60 + 30 + 1


def test_a_grade_usa_so_negocios_de_antes_do_minuto_e_herda_o_anterior():
    negocios = _negocios([("09:14:59", 100), ("10:00:00", 200), ("10:00:30", 300)])
    grade = sw.grade_de_precos(negocios, PREGAO)
    assert grade[_instante("09:15:00")] == 100.0
    assert (
        grade[_instante("10:00:00")] == 100.0
    )  # o negócio das 10h00 ainda não aconteceu
    assert grade[_instante("10:01:00")] == 300.0
    assert grade[_instante("17:45:00")] == 300.0


def test_sem_negocio_antes_o_preco_fica_vazio():
    grade = sw.grade_de_precos(_negocios([("10:00:00", 100)]), PREGAO)
    assert np.isnan(grade[_instante("09:15:00")])


def test_cortar_o_futuro_nao_muda_a_grade_do_passado():
    gerador = np.random.default_rng(7)
    segundos = np.sort(gerador.integers(9 * 3600, 18 * 3600, size=3000))
    horas = [f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}" for s in segundos]
    precos = 100_000 + 5 * np.cumsum(gerador.choice([-1, 0, 1], size=len(horas)))
    negocios = _negocios(list(zip(horas, precos, strict=True)))
    inteira = sw.grade_de_precos(negocios, PREGAO)
    corte = _instante("13:00:00")
    cortada = sw.grade_de_precos(negocios[negocios["instante"] < corte], PREGAO)
    ate_o_corte = inteira.index <= corte
    pd.testing.assert_series_equal(inteira[ate_o_corte], cortada[ate_o_corte])


# --- M3: as regras de scalp ---
def _grade(precos: list[float]) -> pd.Series:
    indice = pd.date_range(_instante("09:15:00"), periods=len(precos), freq="min")
    return pd.Series(precos, index=indice, dtype=float)


def test_momento_compra_depois_de_subir_e_vende_depois_de_cair():
    grade = _grade([100, 105, 115, 110, 110, 120])
    # h=1, decisões nos minutos 1 a 4: sinais +5, +10, -5 e 0 (sem operação)
    ganhos = sw.ganhos_da_regra(grade, h=1, direcao="momento")
    assert ganhos.tolist() == [10.0, -5.0, 0.0]


def test_reversao_e_o_espelho_do_momento():
    grade = _grade([100, 105, 115, 110, 110, 120])
    assert sw.ganhos_da_regra(grade, h=1, direcao="reversao").tolist() == [
        -10.0,
        5.0,
        0.0,
    ]


def test_regra_sem_sobreposicao_e_a_ultima_saida_ate_o_fim_da_grade():
    grade = _grade([100, 110, 120, 125, 130, 120, 140])
    # h=2: decisões nos minutos 2 (sinal +20) e 4 (sinal +10); saídas nos minutos 4 e 6
    assert sw.ganhos_da_regra(grade, h=2, direcao="momento").tolist() == [10.0, 10.0]


def test_regra_pula_decisao_sem_preco():
    grade = _grade([np.nan, 100, 105, 110])
    assert sw.ganhos_da_regra(grade, h=1, direcao="momento").tolist() == [5.0]


def test_direcao_desconhecida_vira_erro():
    with pytest.raises(ValueError, match="direção"):
        sw.ganhos_da_regra(_grade([100, 105]), h=1, direcao="aleatoria")


def test_ha_exatamente_oito_variantes_pre_registradas():
    assert len(sw.VARIANTES) == 8
    assert {v.h for v in sw.VARIANTES} == {1, 2, 5, 10}
    assert {v.direcao for v in sw.VARIANTES} == {"momento", "reversao"}


# --- M2: movimento por horário ---
def test_variacoes_por_faixa_de_30_minutos_pelo_inicio():
    grade = _grade([100.0] * 30 + [110.0] * 31)  # 09h15 a 10h15
    variacoes = sw.variacoes(grade, h=1)
    assert set(variacoes["faixa"]) == {"09:00", "09:30", "10:00"}
    resumo = sw.resumo_por_faixa(variacoes)
    linha = resumo.set_index("faixa").loc["09:30"]
    assert linha["media_abs"] == pytest.approx(10 / 30)


# --- critério ---
def test_media_por_operacao_junta_os_dias():
    dias = [np.array([10.0, 20.0]), np.array([]), np.array([30.0])]
    assert sw.media_por_operacao(dias) == pytest.approx(20.0)
    assert np.isnan(sw.media_por_operacao([np.array([])]))


def test_bootstrap_de_ganho_constante_e_um_ponto_e_repete_com_a_semente():
    dias = [np.full(5, 12.0) for _ in range(12)]
    assert sw.intervalo_bootstrap(dias) == pytest.approx((12.0, 12.0))
    variados = [np.array([float(i), -float(i)]) + i for i in range(12)]
    assert sw.intervalo_bootstrap(variados) == sw.intervalo_bootstrap(variados)
    inferior, superior = sw.intervalo_bootstrap(variados)
    assert inferior < sw.media_por_operacao(variados) < superior


def _ganhos(medias_dev: dict[str, float], ganho_val: float) -> dict:
    por_variante = {}
    for variante in sw.VARIANTES:
        media = medias_dev.get(variante.nome, 0.0)
        por_variante[variante.nome] = {
            "desenvolvimento": [np.full(3, media) for _ in range(11)],
            "validacao": [np.full(3, ganho_val) for _ in range(12)],
        }
    return por_variante


def test_veredito_escolhe_no_desenvolvimento_e_decide_na_validacao():
    ganhos = _ganhos({"reversao_1min": 4.0, "momento_5min": 3.0}, ganho_val=15.0)
    veredito = sw.veredito(ganhos, empate_em_pontos=10.0)
    assert veredito["escolhida"] == "reversao_1min"
    assert veredito["decisao"] == "APROVA"


def test_veredito_reprova_quando_o_limite_inferior_nao_passa_do_empate():
    ganhos = _ganhos({"momento_2min": 4.0}, ganho_val=10.0)  # empata, não passa
    assert sw.veredito(ganhos, empate_em_pontos=10.0)["decisao"] == "REPROVA"


def test_a_validacao_nao_muda_a_escolha():
    ganhos = _ganhos({"momento_10min": 4.0}, ganho_val=-50.0)
    ganhos["reversao_2min"]["validacao"] = [np.full(3, 99.0) for _ in range(12)]
    veredito = sw.veredito(ganhos, empate_em_pontos=10.0)
    assert veredito["escolhida"] == "momento_10min"
    assert veredito["decisao"] == "REPROVA"


def test_divisao_cronologica_onze_e_doze():
    desenvolvimento, validacao = sw.dividir([dia.pregao for dia in sw.DIAS_QUE_ENTRAM])
    assert len(desenvolvimento) == 11 and len(validacao) == 12
    assert max(desenvolvimento) < min(validacao)


# --- os dados fechados no pré-registro ---
def test_a_tabela_tem_23_dias_que_entram_e_4_fora():
    assert len(sw.DIAS) == 27
    assert len(sw.DIAS_QUE_ENTRAM) == 23
    fora = [dia.pregao for dia in sw.DIAS if dia.selo != "completo"]
    assert fora == ["2026-09-22", "2026-09-25", "2026-09-29", "2026-10-09"]


def test_o_pre_registro_nao_mudou_desde_a_medida():
    assert sw.sha256_do_pre_registro() == sw.SHA256_DO_PRE_REGISTRO


def test_arquivo_com_hash_diferente_para_a_rodada(tmp_path):
    caminho = tmp_path / "x.zip"
    with zipfile.ZipFile(caminho, "w") as arquivo:
        arquivo.writestr("05-10-2026_NEGOCIOSAVISTA.txt", "x")
    with pytest.raises(sw.ArquivoDiferenteError, match="2026-10-05"):
        sw.conferir_arquivo(caminho, "2026-10-05", "0" * 64)
    certo = hashlib.sha256(caminho.read_bytes()).hexdigest()
    sw.conferir_arquivo(caminho, "2026-10-05", certo)  # não levanta
