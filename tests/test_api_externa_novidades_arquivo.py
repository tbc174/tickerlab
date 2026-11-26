"""Escolha do arquivo de novidades: configuração explícita, acervo e leitura local."""

import json
from datetime import date

import pytest

from src import acervo
from src.api_externa.conjuntos import novidades

HOJE = date(2026, 11, 26)
GERADO_EM = "2026-11-26T09:00:00+00:00"


@pytest.fixture(autouse=True)
def configuracao_isolada(monkeypatch, tmp_path):
    monkeypatch.delenv(novidades.VARIAVEL_DO_ARQUIVO, raising=False)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))


@pytest.mark.parametrize("valor", [None, "", " \t "])
def test_sem_arquivo_configurado_usa_novidades_na_pasta_do_acervo(
    monkeypatch, tmp_path, valor
):
    if valor is not None:
        monkeypatch.setenv(novidades.VARIAVEL_DO_ARQUIVO, valor)

    assert novidades.caminho_do_arquivo() == tmp_path / "acervo" / "novidades.json"


@pytest.mark.parametrize("acervo_desligado", [False, True])
def test_arquivo_explicito_tem_prioridade_e_remove_espacos_externos(
    monkeypatch, tmp_path, acervo_desligado
):
    arquivo = tmp_path / "pesquisa publicada" / "outras-novidades.json"
    monkeypatch.setenv(novidades.VARIAVEL_DO_ARQUIVO, f" \t{arquivo} \t")
    if acervo_desligado:
        monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, acervo.DESLIGADO)

    assert novidades.caminho_do_arquivo() == arquivo


def test_sem_configuracao_usa_a_pasta_padrao_do_acervo(monkeypatch, tmp_path):
    pasta_padrao = tmp_path / "acervo-padrao"
    monkeypatch.delenv(acervo.VARIAVEL_DA_PASTA)
    monkeypatch.setattr(acervo, "PASTA_PADRAO", pasta_padrao)

    assert novidades.caminho_do_arquivo() == pasta_padrao / "novidades.json"


def test_acervo_desligado_sem_arquivo_explicito_devolve_resposta_vazia(monkeypatch):
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, acervo.DESLIGADO)

    assert novidades.caminho_do_arquivo() is None
    servido = novidades.novidades(dias=7, linhas_maximas=10, hoje=HOJE)

    assert servido.corpo == {
        "gerado_em": None,
        "dias": 7,
        "total_de_novidades": 0,
        "itens": [],
    }
    assert servido.fontes == set()
    assert servido.linhas == 0


@pytest.mark.parametrize("origem", ["acervo", "ambiente", "argumento"])
def test_leitura_respeita_a_prioridade_argumento_ambiente_acervo(
    monkeypatch, tmp_path, origem
):
    arquivos = {
        "acervo": tmp_path / "acervo" / "novidades.json",
        "ambiente": tmp_path / "publicado.json",
        "argumento": tmp_path / "escolhido.json",
    }
    # Datas distintas permitem conferir qual arquivo foi lido sem dados de pessoas.
    datas = {
        "acervo": "2026-11-24T09:00:00+00:00",
        "ambiente": "2026-11-25T09:00:00+00:00",
        "argumento": GERADO_EM,
    }
    for nome, arquivo in arquivos.items():
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(
            json.dumps({"gerado_em": datas[nome], "itens": []}), encoding="utf-8"
        )
    if origem != "acervo":
        monkeypatch.setenv(novidades.VARIAVEL_DO_ARQUIVO, str(arquivos["ambiente"]))
    caminho = arquivos["argumento"] if origem == "argumento" else None

    servido = novidades.novidades(7, 10, hoje=HOJE, caminho=caminho)

    assert servido.corpo["gerado_em"] == datas[origem]
    assert servido.corpo["itens"] == []


def test_arquivo_explicito_ausente_nao_recorre_ao_acervo(monkeypatch, tmp_path):
    arquivo_do_acervo = tmp_path / "acervo" / "novidades.json"
    arquivo_do_acervo.parent.mkdir()
    arquivo_do_acervo.write_text(
        json.dumps({"gerado_em": GERADO_EM, "itens": []}), encoding="utf-8"
    )
    monkeypatch.setenv(
        novidades.VARIAVEL_DO_ARQUIVO, str(tmp_path / "nao-publicado.json")
    )

    servido = novidades.novidades(7, 10, hoje=HOJE)

    assert servido.corpo["gerado_em"] is None
    assert servido.corpo["total_de_novidades"] == 0
    assert servido.corpo["itens"] == []
