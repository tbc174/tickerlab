"""Contrato de dados com versão e catálogo da base (ADR 0077, PR 1)."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from base import contrato
from base.dicionario import TABELAS, Tabela

CAMPOS_DA_P6 = {
    "tabela", "modulo", "dono", "versao", "colunas", "chaves", "datas", "historico_desde",
    "granularidade_do_publico_em", "licenca", "revenda", "pessoa", "frequencia", "atraso",
    "sinonimos_de_tempo",
}  # fmt: skip


def _tabela(**mudancas) -> Tabela:
    base = Tabela(
        descricao="d",
        fonte="f",
        familia_da_fonte="cvm",
        frequencia="diária",
        atraso="1 dia",
        onde="o",
        linhagem="l",
        colunas={"cnpj": ("CNPJ", "texto"), "valor": ("Valor", "reais")},
        modulo="mercado_e_empresas",
        chaves=("cnpj",),
        historico_desde="2010-01-01",
        granularidade_do_publico_em="dia",
    )
    return replace(base, **mudancas)


def _congelar(pasta: Path, tabelas: dict[str, Tabela]) -> None:
    contrato.gravar(tabelas, pasta, pasta / "CHANGELOG.md")


# --- 1.2: gerar contrato e catálogo ---
def test_catalogo_publicado_esta_em_dia():
    """Mudou o dicionário? Rode `python -m base.contrato` e revise o diff."""
    publicado = json.loads(
        (contrato.PASTA / "catalogo.json").read_text(encoding="utf-8")
    )
    assert publicado == contrato.catalogo(), "base/contratos/catalogo.json está velho"


def test_catalogo_tem_os_campos_da_p6():
    catalogo = contrato.catalogo()
    assert set(catalogo["tabelas"]) == set(TABELAS)
    for nome, entrada in catalogo["tabelas"].items():
        assert set(entrada) == CAMPOS_DA_P6, nome
        assert entrada["tabela"] == nome
        assert entrada["dono"] == "Dados"
        assert entrada["colunas"], nome


def test_contrato_guarda_unidade_de_cada_coluna():
    entrada = contrato.contrato_da_tabela("t", _tabela())
    assert entrada["colunas"]["valor"] == {"descricao": "Valor", "unidade": "reais"}
    assert entrada["versao"] == "1.0.0"


def test_gerador_cria_um_arquivo_por_tabela_na_versao_maior(tmp_path):
    _congelar(tmp_path, {"t": _tabela()})
    assert (tmp_path / "v1" / "t.json").exists()
    assert (tmp_path / "catalogo.json").exists()


# --- 1.3: a regra da versão maior ---
def test_gerador_nunca_regrava_contrato_congelado(tmp_path):
    _congelar(tmp_path, {"t": _tabela()})
    antes = (tmp_path / "v1" / "t.json").read_text(encoding="utf-8")
    _congelar(tmp_path, {"t": _tabela(colunas={"cnpj": ("CNPJ", "texto")})})
    assert (tmp_path / "v1" / "t.json").read_text(encoding="utf-8") == antes


def test_sem_mudanca_nao_ha_erro(tmp_path):
    tabelas = {"t": _tabela()}
    _congelar(tmp_path, tabelas)
    assert contrato.conferir_versoes(tabelas, tmp_path) == []


def test_coluna_que_some_exige_versao_maior(tmp_path):
    _congelar(tmp_path, {"t": _tabela()})
    sem_valor = {"t": _tabela(colunas={"cnpj": ("CNPJ", "texto")})}
    erros = contrato.conferir_versoes(sem_valor, tmp_path)
    assert len(erros) == 1 and "t" in erros[0] and "valor" in erros[0]
    com_maior = {**sem_valor, "t": replace(sem_valor["t"], versao_do_contrato="2.0.0")}
    assert contrato.conferir_versoes(com_maior, tmp_path) == []


def test_mudanca_de_unidade_ou_de_chave_exige_maior(tmp_path):
    _congelar(tmp_path, {"t": _tabela()})
    outra_unidade = {
        "t": _tabela(colunas={"cnpj": ("CNPJ", "texto"), "valor": ("Valor", "dólares")})
    }
    outra_chave = {"t": _tabela(chaves=("cnpj", "valor"))}
    for mudada in (outra_unidade, outra_chave):
        erros = contrato.conferir_versoes(mudada, tmp_path)
        assert len(erros) == 1, mudada
        subida = {"t": replace(mudada["t"], versao_do_contrato="2.0.0")}
        assert contrato.conferir_versoes(subida, tmp_path) == []


def test_coluna_nova_exige_menor(tmp_path):
    _congelar(tmp_path, {"t": _tabela()})
    colunas = {
        "cnpj": ("CNPJ", "texto"),
        "valor": ("Valor", "reais"),
        "novo": ("Novo", "texto"),
    }
    nova = {"t": _tabela(colunas=colunas)}
    erros = contrato.conferir_versoes(nova, tmp_path)
    assert len(erros) == 1 and "novo" in erros[0]
    com_menor = {"t": replace(nova["t"], versao_do_contrato="1.1.0")}
    assert contrato.conferir_versoes(com_menor, tmp_path) == []


def test_tabela_que_some_do_dicionario_e_erro(tmp_path):
    _congelar(tmp_path, {"t": _tabela()})
    erros = contrato.conferir_versoes({}, tmp_path)
    assert len(erros) == 1 and "t" in erros[0]


def test_tabela_nova_nao_e_erro(tmp_path):
    _congelar(tmp_path, {"t": _tabela()})
    assert contrato.conferir_versoes({"t": _tabela(), "u": _tabela()}, tmp_path) == []


def test_depois_da_maior_o_novo_contrato_vira_a_base_da_conferencia(tmp_path):
    _congelar(tmp_path, {"t": _tabela()})
    v2 = {"t": _tabela(colunas={"cnpj": ("CNPJ", "texto")}, versao_do_contrato="2.0.0")}
    _congelar(tmp_path, v2)
    assert (tmp_path / "v2" / "t.json").exists()
    assert contrato.conferir_versoes(v2, tmp_path) == []
    # voltar atrás agora é uma coluna nova em relação à v2, e pede a menor
    assert contrato.conferir_versoes(
        {"t": _tabela(versao_do_contrato="2.0.0")}, tmp_path
    )


def test_contratos_de_hoje_conferem():
    assert contrato.conferir_versoes(TABELAS, contrato.PASTA) == []


def test_changelog_publicado_esta_em_dia():
    publicado = contrato.ARQUIVO_DO_CHANGELOG.read_text(encoding="utf-8")
    assert publicado == contrato.changelog(TABELAS, contrato.PASTA)


def test_changelog_lista_a_coluna_nova(tmp_path):
    _congelar(tmp_path, {"t": _tabela()})
    colunas = {
        "cnpj": ("CNPJ", "texto"),
        "valor": ("Valor", "reais"),
        "novo": ("Novo", "texto"),
    }
    texto = contrato.changelog(
        {"t": _tabela(colunas=colunas, versao_do_contrato="1.1.0")}, tmp_path
    )
    assert "`t`" in texto and "1.1.0" in texto and "novo" in texto


def test_versao_invalida_e_recusada():
    with pytest.raises(ValueError):
        contrato.versao_em_numeros("1.0")
