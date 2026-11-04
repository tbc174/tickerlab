"""P0-8: a rodada trava sem estratégia aprovada e nunca registra tentativa."""

import pytest

from trader import criterio_quant
from trader.estrategias import rodar_regime as rodar


def _registro_com(tmp_path, *tentativas):
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    for familia, nome, resultado in tentativas:
        id_ = registro.registrar(familia, nome, {"nome": nome})
        if resultado is not None:
            registro.salvar_resultado(id_, resultado)
    return registro


APROVADA = {"veredito": {"aprovado": True}}
REPROVADA = {"veredito": {"aprovado": False}}
RECONSTRUIDA = {"reconstruido": True, "resumo": "REPROVADO"}


def test_sem_aprovada_a_ficha_nao_tem_objeto(tmp_path, capsys):
    registro = _registro_com(
        tmp_path,
        ("P0-1", "tendencia", RECONSTRUIDA),
        ("P0-5", "pead", REPROVADA),
        ("P0-3", "sem_resultado", None),
    )
    antes = registro.total_para_o_dsr()
    assert rodar.main(registro) == rodar.SAIDA_SEM_OBJETO
    assert capsys.readouterr().out.startswith("SEM OBJETO")
    assert registro.total_para_o_dsr() == antes


def test_estudo_monitor_e_a_propria_p0_8_nao_contam(tmp_path):
    registro = _registro_com(
        tmp_path,
        ("P0-6", "monitor", APROVADA),
        ("P0-7", "simulador", APROVADA),
        ("P0-8", "regime", APROVADA),
    )
    assert rodar.aprovadas(registro) == []


def test_com_aprovada_lista_e_nao_registra(tmp_path, capsys):
    registro = _registro_com(
        tmp_path, ("P0-1", "tendencia", APROVADA), ("P0-2", "bova", REPROVADA)
    )
    antes = registro.total_para_o_dsr()
    assert rodar.main(registro) == rodar.SAIDA_FALTA_A_COMPARACAO
    assert "P0-1 tendencia" in capsys.readouterr().out
    assert registro.total_para_o_dsr() == antes


def test_pre_registro_alterado_para_antes_de_ler(tmp_path, monkeypatch):
    def recusar(*_, **__):
        raise criterio_quant.PreRegistroAlteradoError("mudou")

    monkeypatch.setattr(rodar.criterio_quant, "conferir", recusar)

    def nao_ler(*_, **__):
        raise AssertionError("o registro não pode ser lido com o texto alterado")

    monkeypatch.setattr(rodar, "aprovadas", nao_ler)
    with pytest.raises(criterio_quant.PreRegistroAlteradoError):
        rodar.main(_registro_com(tmp_path))


def test_orcamento_da_ficha_continua_intacto():
    assert criterio_quant.ORCAMENTO_POR_FICHA[rodar.FICHA] == 4
