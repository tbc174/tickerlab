"""Holdout lacrado: recorte de datas, lacre de uso único e critério protegido."""

import json

import numpy as np
import pandas as pd
import pytest

from trader import holdout as h
from trader.registro import Registro

TEXTO = "critério aprovado\nlinha 2\n"


@pytest.fixture
def ambiente(tmp_path):
    criterio = tmp_path / "criterio.md"
    criterio.write_text(TEXTO, encoding="utf-8", newline="\n")
    registro = Registro(tmp_path / "pesquisa" / "registro.db", commit_fn=lambda: "abc")
    return {
        "pasta": tmp_path / "pesquisa",
        "criterio": criterio,
        "hash": h.hash_do_texto(criterio),
        "registro": registro,
    }


def _candidato(ambiente, aprovado=True):
    i = ambiente["registro"].registrar("H2", "lgbm_v1", {"modelo": "lgbm"})
    ambiente["registro"].salvar_resultado(i, {"aprovado_em_A": aprovado})
    return i


def _dados():
    indice = pd.bdate_range("2023-01-02", "2026-10-30")
    return {
        "EURUSD": pd.DataFrame(
            {"Close": np.arange(len(indice), dtype=float)}, index=indice
        ),
        "VAZIO": pd.DataFrame({"Close": [1.0]}, index=[pd.Timestamp("2020-01-01")]),
    }


def _pontuar(ambiente, i, avaliar):
    return h.pontuar(
        ambiente["registro"],
        i,
        _dados(),
        avaliar,
        pasta=ambiente["pasta"],
        criterio=ambiente["criterio"],
        hash_esperado=ambiente["hash"],
    )


# --- recorte -------------------------------------------------------------------------------


def test_datas_do_criterio_aprovado():
    assert h.FIM_DO_DESENVOLVIMENTO == pd.Timestamp("2023-09-08")
    assert h.INICIO_DO_HOLDOUT == pd.Timestamp("2023-10-10")
    assert h.FIM_DO_HOLDOUT == pd.Timestamp("2026-10-09")
    expurgo = pd.bdate_range("2023-09-09", "2023-10-09")
    assert 20 <= len(expurgo) <= 22  # ~21 pregões descartados


def test_recortar_desenvolvimento_corta_no_ultimo_dia_permitido():
    d = _dados()["EURUSD"]
    dev = h.recortar_desenvolvimento(d)
    assert dev.index.max() == pd.Timestamp("2023-09-08")
    serie = h.recortar_desenvolvimento(d["Close"])
    assert serie.index.max() == pd.Timestamp("2023-09-08")
    h.exigir_sem_holdout(dev)


def test_exigir_sem_holdout_pega_vazamento():
    d = _dados()["EURUSD"]
    with pytest.raises(h.HoldoutVazandoError, match="depois do fim"):
        h.exigir_sem_holdout(d)
    h.exigir_sem_holdout(d.iloc[0:0])  # vazio não vaza


def test_recortar_exige_indice_de_datas():
    with pytest.raises(TypeError):
        h.recortar_desenvolvimento(pd.DataFrame({"a": [1, 2]}))


# --- critério protegido --------------------------------------------------------------------


def test_o_criterio_aprovado_no_repositorio_tem_o_hash_registrado():
    assert h.CAMINHO_DO_CRITERIO.exists()
    assert h.hash_do_texto(h.CAMINHO_DO_CRITERIO) == h.HASH_DO_CRITERIO


def test_hash_ignora_quebra_de_linha_do_windows(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_bytes(b"x\ny\n")
    b.write_bytes(b"x\r\ny\r\n")
    assert h.hash_do_texto(a) == h.hash_do_texto(b)


def test_criterio_alterado_impede_pontuar(ambiente):
    i = _candidato(ambiente)
    ambiente["criterio"].write_text(TEXTO + "mudei um limite\n", encoding="utf-8")
    with pytest.raises(h.CriterioAlteradoError, match="v0.2"):
        _pontuar(ambiente, i, lambda d: {})
    assert not (ambiente["pasta"] / h.NOME_DO_LACRE).exists()  # nada queimado


def test_criterio_sumido_impede_pontuar(ambiente):
    i = _candidato(ambiente)
    ambiente["criterio"].unlink()
    with pytest.raises(h.CriterioAlteradoError, match="Não achei"):
        _pontuar(ambiente, i, lambda d: {})


# --- pontuar uma vez -----------------------------------------------------------------------


def test_so_pontua_candidato_aprovado_no_desenvolvimento(ambiente):
    i = _candidato(ambiente, aprovado=False)
    with pytest.raises(h.CandidatoNaoAprovadoError):
        _pontuar(ambiente, i, lambda d: {})
    sem_resultado = ambiente["registro"].registrar("H1", "sem resultado", {"a": 1})
    with pytest.raises(h.CandidatoNaoAprovadoError):
        _pontuar(ambiente, sem_resultado, lambda d: {})
    assert not (ambiente["pasta"] / h.NOME_DO_LACRE).exists()


def test_avaliar_recebe_so_o_trecho_do_holdout(ambiente):
    i = _candidato(ambiente)
    vistos = {}

    def avaliar(dados):
        vistos.update(dados)
        return {"sharpe": 0.9}

    resultado = _pontuar(ambiente, i, avaliar)
    assert set(vistos) == {"EURUSD"}  # a série sem dados no período sai
    assert vistos["EURUSD"].index.min() >= h.INICIO_DO_HOLDOUT
    assert vistos["EURUSD"].index.max() <= h.FIM_DO_HOLDOUT
    assert resultado == {"sharpe": 0.9, "valido": True}


def test_pontuar_registra_e_lacra(ambiente):
    i = _candidato(ambiente)
    _pontuar(ambiente, i, lambda d: {"sharpe": 0.9})
    texto = (ambiente["pasta"] / h.NOME_DO_LACRE).read_text(encoding="utf-8")
    lacre = json.loads(texto)
    assert lacre["tentativa_id"] == i and lacre["hash_do_criterio"] == ambiente["hash"]
    assert "concluido_em" in lacre
    reg = ambiente["registro"]
    assert reg.contar("holdout") == 1
    assert reg.listar("holdout")[0]["nome"] == "lgbm_v1"
    assert (
        reg.total_para_o_dsr() == 1
    )  # o holdout não infla a contagem do desenvolvimento


def test_segunda_pontuacao_e_recusada(ambiente):
    i = _candidato(ambiente)
    _pontuar(ambiente, i, lambda d: {"sharpe": 0.9})
    chamadas = []

    def avaliar(dados):
        chamadas.append(1)
        return {}

    with pytest.raises(h.HoldoutJaUsadoError):
        _pontuar(ambiente, i, avaliar)
    assert chamadas == []  # nem chega a olhar os dados de novo


def test_outro_candidato_tambem_nao_pode_depois_do_primeiro(ambiente):
    primeiro = _candidato(ambiente)
    _pontuar(ambiente, primeiro, lambda d: {"sharpe": 0.9})
    segundo = ambiente["registro"].registrar("H3", "meta_v1", {"modelo": "meta"})
    ambiente["registro"].salvar_resultado(segundo, {"aprovado_em_A": True})
    with pytest.raises(h.HoldoutJaUsadoError):
        _pontuar(ambiente, segundo, lambda d: {})


def test_falha_na_avaliacao_queima_o_holdout(ambiente):
    i = _candidato(ambiente)

    def quebra(dados):
        raise ZeroDivisionError("bug no avaliador")

    with pytest.raises(ZeroDivisionError):
        _pontuar(ambiente, i, quebra)
    texto = (ambiente["pasta"] / h.NOME_DO_LACRE).read_text(encoding="utf-8")
    assert "ZeroDivisionError" in json.loads(texto)["avaliacao_falhou"]
    with pytest.raises(h.HoldoutJaUsadoError):
        _pontuar(ambiente, i, lambda d: {"sharpe": 1})


# --- destrancar ----------------------------------------------------------------------------


def test_destrancar_exige_frase_e_motivo(ambiente):
    i = _candidato(ambiente)
    _pontuar(ambiente, i, lambda d: {"sharpe": 0.9})
    with pytest.raises(PermissionError):
        h.destrancar("quero tentar de novo", "sim", pasta=ambiente["pasta"])
    with pytest.raises(ValueError, match="motivo"):
        h.destrancar("  ", h.FRASE_DE_CONFIRMACAO, pasta=ambiente["pasta"])
    assert (ambiente["pasta"] / h.NOME_DO_LACRE).exists()


def test_destrancar_invalida_o_holdout_e_marca_os_resultados(ambiente):
    i = _candidato(ambiente)
    _pontuar(ambiente, i, lambda d: {"sharpe": 0.9})
    assert h.holdout_valido(ambiente["pasta"])
    arquivado = h.destrancar(
        "bug no avaliador", h.FRASE_DE_CONFIRMACAO, pasta=ambiente["pasta"]
    )
    assert arquivado.exists()
    assert not (ambiente["pasta"] / h.NOME_DO_LACRE).exists()
    assert not h.holdout_valido(ambiente["pasta"])
    texto = (ambiente["pasta"] / h.NOME_DA_INVALIDACAO).read_text(encoding="utf-8")
    assert json.loads(texto)["motivo"] == "bug no avaliador"
    novo = _pontuar(ambiente, i, lambda d: {"sharpe": 1.5})
    assert novo["valido"] is False  # o resultado nunca mais vale como prova


def test_destrancar_sem_lacre_da_erro(ambiente):
    with pytest.raises(FileNotFoundError):
        h.destrancar("x", h.FRASE_DE_CONFIRMACAO, pasta=ambiente["pasta"])


def test_carregar_desenvolvimento_nunca_devolve_dado_do_holdout(tmp_path):
    from trader.dados import salvar

    salvar(_dados()["EURUSD"], "EURUSD", "D1", tmp_path)
    dev = h.carregar_desenvolvimento("EURUSD", tmp_path)
    assert dev.index.max() == h.FIM_DO_DESENVOLVIMENTO
    h.exigir_sem_holdout(dev)
    with pytest.raises(FileNotFoundError, match="não foi baixada"):
        h.carregar_desenvolvimento("NAOEXISTE", tmp_path)
