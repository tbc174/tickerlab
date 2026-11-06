"""Pacote do Painel do café: montado em casa, lido no servidor do app, o mesmo painel.

As tabelas são as do teste do painel (`tests/test_painel_do_cafe.py`), com dado divulgado depois de D
em cada fonte: o pacote de D não pode levar nenhum deles.
"""

from datetime import date

import pandas as pd
import pytest

from src.commodities.cafe import pacote_do_painel as pacote
from src.commodities.cafe import painel
from src.commodities.cafe.regioes import ARABICA, CONILON
from tests.test_painel_do_cafe import DIA, conexao, tabelas_de_exemplo  # noqa: F401

DEPOIS = date(
    2026, 5, 25
)  # o 2º levantamento da CONAB, o COT de 28/04 e o resto já saíram


def _pacote(
    dia: date = DIA, motivos: dict[str, str] | None = None
) -> pacote.PacoteDoPainel:
    tabelas = tabelas_de_exemplo()
    return pacote.montar_pacote(
        tabelas.tabelas, motivos or {}, dia, painel.MESES_DAS_EXPORTACOES
    )


def _gravado(tmp_path, monkeypatch, conteudo: pacote.PacoteDoPainel) -> None:
    caminho = tmp_path / "painel_do_cafe.json"
    pacote.gravar_pacote(conteudo, caminho)
    monkeypatch.setenv(pacote.VARIAVEL_DO_ARQUIVO, str(caminho))


def _sem_a_porta(monkeypatch) -> None:
    from src import acervo as acervo_de_arquivos

    monkeypatch.setattr(acervo_de_arquivos, "pasta_do_acervo", lambda: None)


def _blocos_da_base(p: painel.PainelDoCafe) -> dict[str, object]:
    dado = painel.em_dicionario(p)
    return {chave: dado[chave] for chave in ("fundos", "exportacoes", "balanco", "safra",
                                              "termometro", "bienalidade", "clima")}  # fmt: skip


@pytest.mark.parametrize("tipo", painel.TIPOS)
def test_o_painel_do_pacote_e_o_mesmo_das_tabelas(conexao, tmp_path, tipo):  # noqa: F811
    caminho = tmp_path / "pacote.json"
    pacote.gravar_pacote(_pacote(), caminho)
    lido = pacote.ler_pacote(caminho)
    assert lido is not None and lido.gerado_em == DIA
    do_pacote = painel.TabelasDoCafe(lido.tabelas, lido.motivos)
    esperado = painel.montar_painel(conexao, tipo, DIA, tabelas=tabelas_de_exemplo())
    obtido = painel.montar_painel(conexao, tipo, DIA, tabelas=do_pacote)
    assert painel.em_dicionario(obtido) == painel.em_dicionario(esperado)


def test_o_pacote_de_d_nao_leva_o_que_saiu_depois(conexao):  # noqa: F811
    """Aberto dias depois, o painel do pacote de D mostra D: nada divulgado depois entrou."""
    de_d = _pacote()
    depois = painel.montar_painel(
        conexao, ARABICA, DEPOIS, tabelas=painel.TabelasDoCafe(de_d.tabelas)
    )
    em_d = painel.montar_painel(conexao, ARABICA, DIA, tabelas=tabelas_de_exemplo())
    assert _blocos_da_base(depois) == _blocos_da_base(em_d)
    for nome, tabela in de_d.tabelas.items():
        divulgacao = pd.to_datetime(tabela[pacote.COLUNA_DA_DIVULGACAO[nome]])
        assert (divulgacao <= pd.Timestamp(DIA)).all(), nome


def test_o_comex_vai_so_com_os_meses_que_o_painel_mostra():
    comex = _pacote().tabelas["comex"]
    competencias = pd.to_datetime(comex["competencia"]).unique()
    assert len(competencias) == painel.MESES_DAS_EXPORTACOES
    assert max(competencias) == pd.Timestamp("2026-03-31")


def test_as_datas_voltam_como_datas(tmp_path):
    caminho = tmp_path / "pacote.json"
    pacote.gravar_pacote(_pacote(), caminho)
    lido = pacote.ler_pacote(caminho)
    assert lido is not None
    original = _pacote()
    for nome, tabela in original.tabelas.items():
        devolvida = lido.tabelas[nome]
        assert list(devolvida.columns) == list(tabela.columns), nome
        for coluna in pacote._colunas_de_data(tabela):
            assert pd.api.types.is_datetime64_any_dtype(devolvida[coluna]), (
                nome,
                coluna,
            )


def test_tabela_que_faltou_em_casa_leva_o_motivo(tmp_path, monkeypatch):
    motivo = painel.motivo_sem_tabela("usda_psd_cafe")
    tabelas = tabelas_de_exemplo().tabelas
    sem_usda = {nome: t for nome, t in tabelas.items() if nome != "usda"}
    conteudo = pacote.montar_pacote(
        sem_usda, {"usda": motivo}, DIA, painel.MESES_DAS_EXPORTACOES
    )
    _gravado(tmp_path, monkeypatch, conteudo)
    _sem_a_porta(monkeypatch)
    lidas = painel.tabelas_pela_porta()
    assert lidas.tabela("usda") is None and lidas.motivo("usda") == motivo
    assert lidas.tabela("conab") is not None


def test_sem_a_porta_o_painel_le_o_pacote(conexao, tmp_path, monkeypatch):  # noqa: F811
    _gravado(tmp_path, monkeypatch, _pacote())
    _sem_a_porta(monkeypatch)
    p = painel.montar_painel(conexao, CONILON, DIA)
    assert p.safra.conteudo is not None and p.safra.conteudo.safra == 2026
    assert p.exportacoes.conteudo is not None


def test_sem_pacote_o_painel_diz_que_a_base_nao_chega(tmp_path, monkeypatch):
    monkeypatch.setenv(pacote.VARIAVEL_DO_ARQUIVO, str(tmp_path / "nao_existe.json"))
    _sem_a_porta(monkeypatch)
    tabelas = painel.tabelas_pela_porta()
    assert not tabelas.tabelas
    assert tabelas.motivo("cftc") == painel.SEM_A_BASE


@pytest.mark.parametrize("texto", ["{nada", '{"versao": 99}', '{"versao": 1}'])
def test_pacote_que_nao_abre_nao_e_mostrado(tmp_path, texto):
    caminho = tmp_path / "pacote.json"
    caminho.write_text(texto, encoding="utf-8")
    assert pacote.ler_pacote(caminho) is None


def test_tabela_fora_do_painel_e_erro():
    with pytest.raises(ValueError, match="fora do painel"):
        pacote.montar_pacote({"bolsa": pd.DataFrame()}, {}, DIA, 12)
