"""Registro de tentativas da M2: contagem honesta para o Sharpe deflacionado."""

from datetime import UTC, datetime

import pytest

from trader import registro as reg
from trader.registro import OrcamentoEstouradoError, Registro


@pytest.fixture
def r(tmp_path):
    return Registro(
        tmp_path / "registro.db",
        commit_fn=lambda: "abc1234",
        agora_fn=lambda: datetime(2026, 10, 11, 12, 0, tzinfo=UTC),
    )


SPEC = {
    "modelo": "logistica",
    "rotulo": "fwd_ret_1d",
    "c": 1.0,
    "atributos": ["r1", "r5"],
}


def test_hash_nao_depende_da_ordem_das_chaves():
    a = {"x": 1, "y": [1, 2], "z": {"b": 2, "a": 1}}
    b = {"z": {"a": 1, "b": 2}, "y": [1, 2], "x": 1}
    assert reg.hash_da_especificacao(a) == reg.hash_da_especificacao(b)
    assert reg.hash_da_especificacao(a) != reg.hash_da_especificacao({**a, "x": 2})


def test_especificacao_que_nao_e_json_e_recusada():
    with pytest.raises(TypeError):
        reg.hash_da_especificacao({"funcao": lambda x: x})


def test_registrar_conta_uma_tentativa_e_guarda_tudo(r):
    i = r.registrar("H1", "logistica_v1", SPEC)
    dados = r.obter(i)
    assert dados["familia"] == "H1" and dados["nome"] == "logistica_v1"
    assert dados["spec"] == SPEC and dados["commit_do_codigo"] == "abc1234"
    assert dados["fase"] == "desenvolvimento" and dados["resultado"] is None
    assert r.contar() == 1 and r.total_para_o_dsr() == 1


def test_mesma_configuracao_nao_e_tentativa_nova_mas_conta_a_execucao(r):
    """Toda execução conta no DSR e no orçamento (pré-registro v0.1, seção 9), mas é a mesma linha."""
    a = r.registrar("H1", "logistica_v1", SPEC)
    b = r.registrar("H1", "outro nome, mesma spec", dict(reversed(list(SPEC.items()))))
    assert a == b and r.contar() == 1
    assert r.obter(a)["execucoes"] == 2
    assert r.total_para_o_dsr() == 2
    assert r.orcamento_restante() == r.orcamento - 2


def test_mudar_um_valor_e_tentativa_nova(r):
    r.registrar("H1", "a", SPEC)
    r.registrar("H1", "b", {**SPEC, "c": 0.5})
    r.registrar("H2", "c", {**SPEC, "modelo": "lightgbm"})
    assert r.contar() == 3


def test_holdout_nao_entra_na_contagem_do_dsr(r):
    r.registrar("H1", "a", SPEC)
    r.registrar("H1", "a", SPEC, fase="holdout")
    assert r.contar("desenvolvimento") == 1 and r.contar("holdout") == 1
    assert r.total_para_o_dsr() == 1


def test_familia_fase_e_nome_invalidos_sao_recusados(r):
    with pytest.raises(ValueError, match="Família"):
        r.registrar("X9", "a", SPEC)
    with pytest.raises(ValueError, match="Fase"):
        r.registrar("H1", "a", SPEC, fase="teste")
    with pytest.raises(ValueError, match="nome"):
        r.registrar("H1", "  ", SPEC)


def test_ajuste_do_criterio_soma_25_tentativas(r):
    r.registrar("H1", "a", SPEC)
    r.registrar_ajuste_do_criterio("0.2", "mudei o PBO máximo")
    assert r.tentativas_extras() == 25 and r.total_para_o_dsr() == 26
    r.registrar_ajuste_do_criterio("0.3", "outro ajuste")
    assert r.total_para_o_dsr() == 51


def test_orcamento_de_300_avisa_e_pode_parar(r):
    assert r.orcamento_restante() == 300
    for i in range(300):
        r.registrar("H1", f"t{i}", {"i": i})
    assert r.orcamento_restante() == 0
    r.exigir_orcamento()  # exatamente no limite ainda passa
    r.registrar("H1", "301", {"i": 301})
    assert r.orcamento_restante() == -1 and r.total_para_o_dsr() == 301
    with pytest.raises(OrcamentoEstouradoError):
        r.exigir_orcamento()


def test_salvar_resultado_e_ler_de_volta(r):
    i = r.registrar("H2", "lgbm", SPEC)
    r.salvar_resultado(i, {"sharpe": 0.8, "aprovado_em_A": False})
    assert r.obter(i)["resultado"] == {"sharpe": 0.8, "aprovado_em_A": False}
    with pytest.raises(KeyError):
        r.salvar_resultado(999, {})
    with pytest.raises(KeyError):
        r.obter(999)


def test_dados_persistem_entre_aberturas_do_banco(tmp_path):
    caminho = tmp_path / "x" / "registro.db"
    Registro(caminho, commit_fn=lambda: "c1").registrar("H1", "a", SPEC)
    reaberto = Registro(caminho, commit_fn=lambda: "c2")
    assert reaberto.contar() == 1
    reaberto.registrar("H1", "b", {**SPEC, "c": 9})
    assert Registro(caminho).contar() == 2


def test_listar_filtra_por_fase(r):
    r.registrar("H1", "a", SPEC)
    r.registrar("H1", "a", SPEC, fase="holdout")
    assert len(r.listar()) == 2 and len(r.listar("holdout")) == 1


def test_commit_atual_devolve_texto_mesmo_sem_git(monkeypatch):
    import subprocess

    def quebra(*args, **kwargs):
        raise OSError("sem git")

    monkeypatch.setattr(subprocess, "run", quebra)
    assert reg.commit_atual() == "desconhecido"


# --- proveniência: quem escreveu cada tentativa (ideia 11 do Vibe-Trading) -------------------


def test_proveniencia_nao_muda_o_hash_nem_a_contagem(r):
    sem = r.registrar("H1", "logistica_v1", SPEC)
    r.registrar_proveniencia(sem, autor="Tiago", modelo="claude-opus-5-5")
    de_novo = r.registrar("H1", "logistica_v1", SPEC)
    assert de_novo == sem
    assert r.obter(sem)["hash"] == reg.hash_da_especificacao(SPEC)
    assert r.contar() == 1


def test_proveniencia_guarda_autor_modelo_e_commit(r):
    tid = r.registrar("H1", "logistica_v1", SPEC)
    r.registrar_proveniencia(tid, autor="Tiago", modelo="claude-opus-5-5")
    assert r.obter_proveniencia(tid) == {
        "autor": "Tiago",
        "modelo": "claude-opus-5-5",
        "commit_do_codigo": "abc1234",
        "registrada_em": "2026-10-11T12:00:00+00:00",
    }


def test_hipotese_escrita_por_pessoa_fica_sem_modelo(r):
    tid = r.registrar("H1", "logistica_v1", SPEC)
    r.registrar_proveniencia(tid, autor="Tiago")
    assert r.obter_proveniencia(tid)["modelo"] is None


def test_proveniencia_ausente_e_none_e_nunca_inventada(r):
    tid = r.registrar("H1", "logistica_v1", SPEC)
    assert r.obter_proveniencia(tid) is None


def test_proveniencia_exige_autor_e_tentativa_existente(r):
    tid = r.registrar("H1", "logistica_v1", SPEC)
    with pytest.raises(ValueError):
        r.registrar_proveniencia(tid, autor="  ")
    with pytest.raises(KeyError):
        r.registrar_proveniencia(999, autor="Tiago")


def test_proveniencia_nao_se_reescreve(r):
    """Quem escreveu é um fato do passado: a segunda anotação diferente é recusada."""
    tid = r.registrar("H1", "logistica_v1", SPEC)
    r.registrar_proveniencia(tid, autor="Tiago")
    r.registrar_proveniencia(tid, autor="Tiago")  # a mesma de novo não é erro
    with pytest.raises(ValueError):
        r.registrar_proveniencia(tid, autor="Outra pessoa")


def test_banco_antigo_ganha_a_tabela_de_proveniencia(tmp_path):
    import sqlite3

    caminho = tmp_path / "antigo.db"
    with sqlite3.connect(caminho) as c:
        c.executescript(reg.ESQUEMA)  # o esquema de antes, sem a tabela nova
    velho = Registro(caminho, commit_fn=lambda: "abc1234")
    tid = velho.registrar("H1", "logistica_v1", SPEC)
    assert velho.obter_proveniencia(tid) is None


# --- pesquisa P0 fora das cópias do repositório, com cópia de segurança -----------------------------


def test_registro_com_copias_guarda_o_banco_a_cada_escrita(tmp_path):
    copias = tmp_path / "copias"
    r = Registro(tmp_path / "registro.db", commit_fn=lambda: "c1", copias=copias)
    tentativa = r.registrar("H1", "a", SPEC)
    r.salvar_resultado(tentativa, {"sharpe": 0.1})
    r.registrar_ajuste_do_criterio("v0.2", "teste")
    guardadas = sorted(copias.glob("registro_*.db"))
    assert len(guardadas) == 3
    ultima = Registro(guardadas[-1], commit_fn=lambda: "c1")
    assert ultima.contar() == 1
    assert ultima.obter(tentativa)["resultado"] == {"sharpe": 0.1}
    assert ultima.tentativas_extras() == reg.TENTATIVAS_POR_AJUSTE


def test_copias_ficam_nas_mais_recentes(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "MAXIMO_DE_COPIAS", 2)
    copias = tmp_path / "copias"
    r = Registro(tmp_path / "registro.db", commit_fn=lambda: "c1", copias=copias)
    for numero in range(4):
        r.registrar("H1", f"t{numero}", {**SPEC, "c": numero})
    guardadas = sorted(copias.glob("registro_*.db"))
    assert len(guardadas) == 2
    assert Registro(guardadas[-1], commit_fn=lambda: "c1").contar() == 4


def test_registro_sem_copias_nao_cria_pasta(tmp_path):
    Registro(tmp_path / "registro.db", commit_fn=lambda: "c1").registrar(
        "H1", "a", SPEC
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["registro.db"]


def test_pesquisa_quant_fica_fora_das_copias_do_repositorio(monkeypatch):
    monkeypatch.delenv(reg.VARIAVEL_DA_PESQUISA_QUANT, raising=False)
    pasta = reg.pasta_da_pesquisa_quant()
    assert pasta.name == "pesquisa_quant"
    assert not pasta.is_relative_to(reg.RAIZ)


def test_variaveis_trocam_os_lugares_da_pesquisa(tmp_path, monkeypatch):
    monkeypatch.setenv(reg.VARIAVEL_DA_PESQUISA_QUANT, str(tmp_path / "pesquisa"))
    monkeypatch.setenv(reg.VARIAVEL_DAS_COPIAS, str(tmp_path / "copias"))
    assert reg.pasta_da_pesquisa_quant() == tmp_path / "pesquisa"
    assert reg.pasta_das_copias() == tmp_path / "copias"


@pytest.mark.parametrize("tem_onedrive", [True, False])
def test_copias_vao_para_o_onedrive_quando_ele_existe(
    tmp_path, monkeypatch, tem_onedrive
):
    monkeypatch.delenv(reg.VARIAVEL_DA_PESQUISA_QUANT, raising=False)
    monkeypatch.delenv(reg.VARIAVEL_DAS_COPIAS, raising=False)
    monkeypatch.setattr(reg.Path, "home", classmethod(lambda cls: tmp_path))
    if tem_onedrive:
        (tmp_path / "OneDrive").mkdir()
        assert (
            reg.pasta_das_copias()
            == tmp_path / "OneDrive" / "TickerLab-Pesquisa" / "copias"
        )
    else:
        assert reg.pasta_das_copias() == reg.pasta_da_pesquisa_quant() / "copias"
