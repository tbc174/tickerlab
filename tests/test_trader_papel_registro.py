"""Papel da v0.2 (seção 5 do pré-registro quant): a cadeia que grava um dia por série, sem regravar."""

import json
from datetime import date, datetime

import pytest

from trader.papel import registro as rg

B3 = "b3"
CRIPTO = "cripto"


def _agora(dia: date, hora: int = 7, minuto: int = 0) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=rg.BRASILIA)


def _foto(fechamento: str, patrimonio: float = 100_000.0) -> dict:
    return {
        "fechamento": fechamento,
        "sinal": {"BOVA11": 0.5},
        "carteira": {"patrimonio": patrimonio},
    }


def _registro(tmp_path) -> rg.RegistroDoPapel:
    return rg.RegistroDoPapel(tmp_path)


# --- prazo de cada mercado ------------------------------------------------------------------------


def test_prazo_da_b3_e_o_inicio_da_pre_abertura_do_pregao_em_que_vale():
    assert rg.prazo(date(2026, 11, 10), B3) == _agora(date(2026, 11, 10), 9, 45)


def test_prazo_da_cripto_e_a_meia_noite_de_brasilia_do_dia_em_que_vale():
    assert rg.prazo(date(2026, 11, 10), CRIPTO) == _agora(date(2026, 11, 10), 0)


def test_so_se_grava_depois_do_fechamento_da_vespera():
    # B3: 18h do pregão anterior (o fechamento das 17h já saiu); cripto: 21h de Brasília (0h UTC).
    assert rg.abre_em(date(2026, 11, 10), B3) == _agora(date(2026, 11, 9), 18)
    assert rg.abre_em(date(2026, 11, 10), CRIPTO) == _agora(date(2026, 11, 9), 21)
    # segunda-feira: a véspera da B3 é a sexta
    assert rg.abre_em(date(2026, 11, 9), B3) == _agora(date(2026, 11, 6), 18)


# --- gravar ---------------------------------------------------------------------------------------


def test_grava_com_data_do_relogio_hash_e_prazo(tmp_path):
    papel = _registro(tmp_path)
    linha = papel.gravar(
        "p0_3", B3, date(2026, 11, 10), _foto("2026-11-09"), _agora(date(2026, 11, 10))
    )
    assert linha["tipo"] == "gravacao"
    assert linha["dia"] == "2026-11-10"
    assert linha["registrado_em"] == "2026-11-10T07:00:00-03:00"
    assert linha["prazo"] == "2026-11-10T09:45:00-03:00"
    assert linha["hash_anterior"] == rg.GENESE
    assert linha["hash"] == rg.hash_da_linha(linha)
    assert papel.linhas("p0_3") == [linha]
    papel.verificar("p0_3")


def test_gravar_duas_vezes_o_mesmo_dia_falha(tmp_path):
    papel = _registro(tmp_path)
    dia = date(2026, 11, 10)
    papel.gravar("p0_3", B3, dia, _foto("2026-11-09"), _agora(dia, 7))
    with pytest.raises(rg.RegravarRecusadoError, match="já gravado"):
        papel.gravar("p0_3", B3, dia, _foto("2026-11-09", 1.0), _agora(dia, 8))
    assert len(papel.linhas("p0_3")) == 1


def test_dia_anterior_ao_ultimo_gravado_falha(tmp_path):
    papel = _registro(tmp_path)
    papel.gravar(
        "p0_3", B3, date(2026, 11, 11), _foto("2026-11-10"), _agora(date(2026, 11, 11))
    )
    with pytest.raises(rg.RegravarRecusadoError):
        papel.gravar(
            "p0_3",
            B3,
            date(2026, 11, 10),
            _foto("2026-11-09"),
            _agora(date(2026, 11, 11), 8),
        )


def test_depois_do_prazo_nao_grava(tmp_path):
    papel = _registro(tmp_path)
    dia = date(2026, 11, 10)
    with pytest.raises(rg.PrazoVencidoError):
        papel.gravar("p0_3", B3, dia, _foto("2026-11-09"), _agora(dia, 9, 45))
    assert papel.linhas("p0_3") == []


def test_antes_do_fechamento_da_vespera_nao_grava(tmp_path):
    papel = _registro(tmp_path)
    with pytest.raises(rg.CedoDemaisError):
        papel.gravar(
            "p0_3",
            B3,
            date(2026, 11, 10),
            _foto("2026-11-09"),
            _agora(date(2026, 11, 9), 14),
        )


def test_fechamento_tem_que_ser_a_vespera_do_dia(tmp_path):
    papel = _registro(tmp_path)
    with pytest.raises(rg.GravacaoRecusadaError, match="véspera"):
        papel.gravar(
            "p0_3",
            B3,
            date(2026, 11, 10),
            _foto("2026-11-06"),
            _agora(date(2026, 11, 10)),
        )


def test_campos_do_registro_nao_vem_do_conteudo(tmp_path):
    papel = _registro(tmp_path)
    foto = {**_foto("2026-11-09"), "registrado_em": "2020-01-01T00:00:00-03:00"}
    with pytest.raises(rg.GravacaoRecusadaError, match="registrado_em"):
        papel.gravar("p0_3", B3, date(2026, 11, 10), foto, _agora(date(2026, 11, 10)))


def test_relogio_para_tras_falha(tmp_path):
    papel = _registro(tmp_path)
    papel.gravar(
        "p0_1",
        CRIPTO,
        date(2026, 11, 11),
        _foto("2026-11-10"),
        _agora(date(2026, 11, 10), 23),
    )
    with pytest.raises(rg.GravacaoRecusadaError, match="relógio"):
        papel.gravar(
            "p0_1",
            CRIPTO,
            date(2026, 11, 12),
            _foto("2026-11-11"),
            _agora(date(2026, 11, 10), 22),
        )


def test_relogio_sem_fuso_falha(tmp_path):
    with pytest.raises(ValueError, match="fuso"):
        _registro(tmp_path).gravar(
            "p0_3",
            B3,
            date(2026, 11, 10),
            _foto("2026-11-09"),
            datetime(2026, 11, 10, 7),  # noqa: DTZ001 (o teste é justamente sem fuso)
        )


# --- faltas ---------------------------------------------------------------------------------------


def test_dia_pulado_vira_falta_e_nunca_e_preenchido(tmp_path):
    papel = _registro(tmp_path)
    papel.gravar(
        "p0_3", B3, date(2026, 11, 9), _foto("2026-11-06"), _agora(date(2026, 11, 9))
    )
    # 10/11 e 11/11 passaram sem gravação; a de 12/11 grava as duas faltas antes
    papel.gravar(
        "p0_3", B3, date(2026, 11, 12), _foto("2026-11-11"), _agora(date(2026, 11, 12))
    )
    tipos = [(linha["dia"], linha["tipo"]) for linha in papel.linhas("p0_3")]
    assert tipos == [
        ("2026-11-09", "gravacao"),
        ("2026-11-10", "falta"),
        ("2026-11-11", "falta"),
        ("2026-11-12", "gravacao"),
    ]
    with pytest.raises(rg.RegravarRecusadoError):
        papel.gravar(
            "p0_3",
            B3,
            date(2026, 11, 11),
            _foto("2026-11-10"),
            _agora(date(2026, 11, 12), 8),
        )
    papel.verificar("p0_3")


def test_falta_so_entra_depois_do_prazo(tmp_path):
    papel = _registro(tmp_path)
    dia = date(2026, 11, 10)
    with pytest.raises(rg.GravacaoRecusadaError, match="prazo"):
        papel.registrar_falta("p0_3", B3, dia, "sem dados", _agora(dia, 9))
    linha = papel.registrar_falta("p0_3", B3, dia, "sem dados", _agora(dia, 10))
    assert linha["tipo"] == "falta" and linha["motivo"] == "sem dados"


def test_cripto_conta_todo_dia_corrido(tmp_path):
    papel = _registro(tmp_path)
    papel.gravar(
        "p0_1",
        CRIPTO,
        date(2026, 11, 6),
        _foto("2026-11-05"),
        _agora(date(2026, 11, 5), 23),
    )
    papel.gravar(
        "p0_1",
        CRIPTO,
        date(2026, 11, 9),
        _foto("2026-11-08"),
        _agora(date(2026, 11, 8), 23),
    )
    faltas = [
        linha["dia"] for linha in papel.linhas("p0_1") if linha["tipo"] == "falta"
    ]
    assert faltas == ["2026-11-07", "2026-11-08"]


def test_feriado_da_b3_nao_e_falta(tmp_path):
    papel = _registro(tmp_path)
    # 20/11/2026 (Consciência Negra) é feriado nacional: depois de 19/11 vem 23/11
    papel.gravar(
        "p0_3", B3, date(2026, 11, 19), _foto("2026-11-18"), _agora(date(2026, 11, 19))
    )
    papel.gravar(
        "p0_3", B3, date(2026, 11, 23), _foto("2026-11-19"), _agora(date(2026, 11, 23))
    )
    assert [linha["tipo"] for linha in papel.linhas("p0_3")] == ["gravacao", "gravacao"]


def test_dia_que_nao_e_pregao_e_recusado(tmp_path):
    papel = _registro(tmp_path)
    with pytest.raises(rg.GravacaoRecusadaError, match="não negocia"):
        papel.gravar(
            "p0_3",
            B3,
            date(2026, 11, 8),
            _foto("2026-11-06"),
            _agora(date(2026, 11, 8)),
        )


# --- a cadeia -------------------------------------------------------------------------------------


def test_alterar_uma_linha_quebra_a_cadeia(tmp_path):
    papel = _registro(tmp_path)
    papel.gravar(
        "p0_3", B3, date(2026, 11, 10), _foto("2026-11-09"), _agora(date(2026, 11, 10))
    )
    papel.gravar(
        "p0_3", B3, date(2026, 11, 11), _foto("2026-11-10"), _agora(date(2026, 11, 11))
    )
    arquivo = papel.arquivo("p0_3")
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    primeira = json.loads(linhas[0])
    primeira["carteira"]["patrimonio"] = 999_999.0
    linhas[0] = json.dumps(primeira, ensure_ascii=False, sort_keys=True)
    arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    with pytest.raises(rg.RegistroAlteradoError, match="linha 1"):
        papel.verificar("p0_3")
    with pytest.raises(rg.RegistroAlteradoError):
        papel.gravar(
            "p0_3",
            B3,
            date(2026, 11, 12),
            _foto("2026-11-11"),
            _agora(date(2026, 11, 12)),
        )


def test_apagar_uma_linha_quebra_a_cadeia(tmp_path):
    papel = _registro(tmp_path)
    for dia in (10, 11, 12):
        papel.gravar(
            "p0_3",
            B3,
            date(2026, 11, dia),
            _foto(f"2026-11-{dia - 1:02d}"),
            _agora(date(2026, 11, dia)),
        )
    arquivo = papel.arquivo("p0_3")
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    arquivo.write_text("\n".join([linhas[0], linhas[2]]) + "\n", encoding="utf-8")
    with pytest.raises(rg.RegistroAlteradoError, match="linha 2"):
        papel.verificar("p0_3")


def test_cada_serie_tem_a_propria_cadeia(tmp_path):
    papel = _registro(tmp_path)
    dia = date(2026, 11, 10)
    papel.gravar("p0_3", B3, dia, _foto("2026-11-09"), _agora(dia, 7))
    papel.gravar("di1", B3, dia, _foto("2026-11-09"), _agora(dia, 7, 1))
    assert papel.ponta("p0_3") != papel.ponta("di1")
    assert papel.series() == ["di1", "p0_3"]


def test_nome_de_serie_estranho_e_recusado(tmp_path):
    with pytest.raises(ValueError, match="nome"):
        _registro(tmp_path).linhas("../fora")


# --- o início -------------------------------------------------------------------------------------


def test_inicio_e_o_primeiro_pregao_depois_do_merge_e_nao_muda(tmp_path):
    papel = _registro(tmp_path)
    # merge numa sexta à tarde: o papel começa na segunda
    inicio = papel.fixar_inicio(
        date(2026, 11, 6), "abc1234", _agora(date(2026, 11, 6), 15)
    )
    assert inicio["inicio"] == "2026-11-09"
    assert papel.inicio() == date(2026, 11, 9)
    with pytest.raises(rg.RegravarRecusadoError, match="início"):
        papel.fixar_inicio(date(2026, 11, 9), "def5678", _agora(date(2026, 11, 9), 15))
    assert papel.inicio() == date(2026, 11, 9)


def test_sem_inicio_fixado_nao_ha_inicio(tmp_path):
    assert _registro(tmp_path).inicio() is None


def test_inicio_alterado_e_detectado(tmp_path):
    papel = _registro(tmp_path)
    papel.fixar_inicio(date(2026, 11, 6), "abc1234", _agora(date(2026, 11, 6), 15))
    dados = json.loads(papel.arquivo_do_inicio.read_text(encoding="utf-8"))
    dados["inicio"] = "2026-11-02"
    papel.arquivo_do_inicio.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(rg.RegistroAlteradoError, match="início"):
        papel.inicio()


def test_nada_antes_do_inicio(tmp_path):
    papel = _registro(tmp_path)
    papel.fixar_inicio(date(2026, 11, 6), "abc1234", _agora(date(2026, 11, 6), 15))
    with pytest.raises(rg.GravacaoRecusadaError, match="antes do início"):
        papel.gravar(
            "p0_1",
            CRIPTO,
            date(2026, 11, 8),
            _foto("2026-11-07"),
            _agora(date(2026, 11, 7), 23),
        )


def test_primeiro_dia_depois_do_inicio_pulado_vira_falta(tmp_path):
    papel = _registro(tmp_path)
    papel.fixar_inicio(date(2026, 11, 6), "abc1234", _agora(date(2026, 11, 6), 15))
    papel.gravar(
        "p0_3", B3, date(2026, 11, 10), _foto("2026-11-09"), _agora(date(2026, 11, 10))
    )
    assert [(x["dia"], x["tipo"]) for x in papel.linhas("p0_3")] == [
        ("2026-11-09", "falta"),
        ("2026-11-10", "gravacao"),
    ]


def test_proximo_dia_a_gravar(tmp_path):
    papel = _registro(tmp_path)
    papel.fixar_inicio(date(2026, 11, 6), "abc1234", _agora(date(2026, 11, 6), 15))
    assert papel.proximo_dia("p0_3", B3) == date(2026, 11, 9)
    assert papel.proximo_dia("p0_1", CRIPTO) == date(2026, 11, 9)
    papel.gravar(
        "p0_1",
        CRIPTO,
        date(2026, 11, 9),
        _foto("2026-11-08"),
        _agora(date(2026, 11, 8), 23),
    )
    assert papel.proximo_dia("p0_1", CRIPTO) == date(2026, 11, 10)
