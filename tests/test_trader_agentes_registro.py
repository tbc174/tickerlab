"""Camada A3: o registro dos agentes é uma cadeia de hashes que não aceita edição nem data inventada."""

import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from trader.agentes import criterios
from trader.agentes import registro as reg

BRASILIA = ZoneInfo("America/Sao_Paulo")
NOVEMBRO = datetime(2026, 11, 3, 10, 0, tzinfo=BRASILIA)
DEZEMBRO = datetime(2026, 12, 2, 10, 0, tzinfo=BRASILIA)


def _conteudo(nota=7.5):
    return {
        "versao_dos_criterios": criterios.VERSAO,
        "hash_dos_criterios": "a" * 64,
        "modelo": "claude-sonnet-5-5",
        "avaliacoes": [{"ticker": "AAA3", "nota_final": nota}],
        "escolhidas": {"AAA3": 0.2},
    }


@pytest.fixture
def registro(tmp_path):
    return reg.RegistroDeAgentes(tmp_path / "agentes")


def test_rodadas_formam_uma_cadeia_que_confere(registro):
    primeira = registro.acrescentar(_conteudo(), agora=NOVEMBRO)
    segunda = registro.acrescentar(_conteudo(8.0), agora=DEZEMBRO)
    assert primeira["hash_anterior"] == reg.GENESE
    assert segunda["hash_anterior"] == primeira["hash"]
    assert registro.ponta() == segunda["hash"]
    assert [linha["data"] for linha in registro.linhas()] == [
        "2026-11-03",
        "2026-12-02",
    ]
    registro.verificar()


def test_a_data_vem_do_relogio_e_nao_do_conteudo(registro):
    with pytest.raises(reg.RodadaRecusadaError, match="data"):
        registro.acrescentar({**_conteudo(), "data": "2026-10-01"}, agora=NOVEMBRO)
    assert registro.linhas() == []


def test_editar_uma_nota_depois_quebra_a_conferencia(registro):
    registro.acrescentar(_conteudo(), agora=NOVEMBRO)
    registro.acrescentar(_conteudo(), agora=DEZEMBRO)
    linhas = registro.arquivo.read_text(encoding="utf-8").splitlines()
    primeira = json.loads(linhas[0])
    primeira["avaliacoes"][0]["nota_final"] = 9.9
    linhas[0] = json.dumps(primeira, ensure_ascii=False)
    registro.arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    with pytest.raises(reg.RegistroAlteradoError, match="linha 1"):
        registro.verificar()


def test_apagar_uma_rodada_quebra_a_cadeia(registro):
    for agora in (NOVEMBRO, DEZEMBRO, datetime(2027, 1, 5, 10, tzinfo=BRASILIA)):
        registro.acrescentar(_conteudo(), agora=agora)
    linhas = registro.arquivo.read_text(encoding="utf-8").splitlines()
    registro.arquivo.write_text(linhas[0] + "\n" + linhas[2] + "\n", encoding="utf-8")
    with pytest.raises(reg.RegistroAlteradoError, match="cadeia"):
        registro.verificar()


def test_segunda_rodada_no_mesmo_mes_e_recusada(registro):
    registro.acrescentar(_conteudo(), agora=NOVEMBRO)
    with pytest.raises(reg.RodadaRecusadaError, match="mês"):
        registro.acrescentar(
            _conteudo(), agora=datetime(2026, 11, 4, 10, tzinfo=BRASILIA)
        )
    assert len(registro.linhas()) == 1


def test_rodada_com_relogio_antes_da_ultima_e_recusada(registro):
    registro.acrescentar(_conteudo(), agora=DEZEMBRO)
    with pytest.raises(reg.RodadaRecusadaError, match="anterior"):
        registro.acrescentar(_conteudo(), agora=NOVEMBRO)


def test_relogio_sem_fuso_e_recusado(registro):
    with pytest.raises(ValueError, match="fuso"):
        registro.acrescentar(_conteudo(), agora=datetime(2026, 11, 3, 10))  # noqa: DTZ001 (o teste é o relógio sem fuso)


def test_dossie_e_guardado_pelo_proprio_hash(registro):
    texto = "# Dossiê da AAA3\n\nFato com fonte.\n"
    codigo = registro.guardar_dossie(texto)
    assert codigo == hashlib.sha256(texto.encode("utf-8")).hexdigest()
    assert registro.ler_dossie(codigo) == texto
    assert registro.guardar_dossie(texto) == codigo  # guardar de novo não muda nada


def test_dossie_alterado_ou_sumido_quebra_a_conferencia(registro):
    codigo = registro.guardar_dossie("original")
    conteudo = _conteudo()
    conteudo["avaliacoes"][0]["hash_do_dossie"] = codigo
    registro.acrescentar(conteudo, agora=NOVEMBRO)
    caminho = registro.pasta_dos_dossies / f"{codigo}.md"
    caminho.write_text("trocado", encoding="utf-8")
    with pytest.raises(reg.RegistroAlteradoError, match="dossiê"):
        registro.verificar()
    caminho.unlink()
    with pytest.raises(reg.RegistroAlteradoError, match="dossiê"):
        registro.verificar()


def test_registro_padrao_fica_na_pasta_fora_do_git():
    assert reg.PASTA_PADRAO.parent.name == "pesquisa_quant"
    ignorados = (reg.RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "pesquisa_quant/" in ignorados
