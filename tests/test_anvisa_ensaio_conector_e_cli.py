"""Ensaio da linha 860 pelo conector e pela CLI: "fabricantes de cosméticos em SP com mais de 200 registros ativos".

A pergunta do critério de pronto, feita do jeito que o analista a faz (pela IA, no conector, e no terminal, na
CLI) contra a API de verdade em memória, com a base de mentira da Anvisa (os CNPJs são de ninguém). Os dois
caminhos têm de dar a mesma empresa, com a fonte e o dia do retrato, o aviso de que registro é sinal de porte (não
faturamento) e sem campo de pessoa. O resto da busca está em `test_api_externa_prospeccao_anvisa`.
"""

import json

import httpx
import openpyxl
import pytest
from click.testing import CliRunner
from tickerlab import comandos, configuracao

from base.porta import Porta
from src import api
from src.api_externa import VARIAVEL_DA_CHAVE, acesso, rotas
from src.api_externa.conjuntos import prospeccao
from tests import ajudantes_da_api_externa as aj
from tests import ajudantes_do_conector as conector
from tests import test_api_externa_prospeccao_anvisa as base_de_mentira

EMPRESA_ESPERADA = "11111111000191"  # a única de SP com mais de 200 cosméticos ativos
DIA_DO_RETRATO = "2026-11-09"
ARGUMENTOS_DA_PERGUNTA = {
    "uf": ["SP"],
    "cnae": ["2063"],
    "anvisa_tipo": "cosmeticos",
    "anvisa_ativos_min": 200,
}


@pytest.fixture
def cenario(banco, monkeypatch, tmp_path):
    base = tmp_path / "base"
    base_de_mentira._gravar(
        base, prospeccao.ESTABELECIMENTOS, base_de_mentira._estabelecimentos()
    )
    base_de_mentira._gravar(base, prospeccao.EMPRESAS, base_de_mentira._empresas())
    base_de_mentira._gravar(base, prospeccao.ANVISA, base_de_mentira._anvisa())
    monkeypatch.setattr(
        rotas,
        "abrir_porta",
        lambda banco_: Porta(base, banco_),
    )
    tabelas = (prospeccao.ESTABELECIMENTOS, prospeccao.EMPRESAS, prospeccao.ANVISA)
    monkeypatch.setattr(
        rotas, "regras_da_api", lambda: base_de_mentira._regras(tabelas)
    )
    monkeypatch.setattr(acesso, "agora", lambda: base_de_mentira.AGORA)
    acesso.zerar_limites()
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    aj.contrato(banco, ator, org, conjunto=prospeccao.CONJUNTO)
    return aj.chave(banco, ator, org)


def _verificar_a_empresa(corpo: dict) -> None:
    assert [e["cnpj"] for e in corpo["companies"]] == [EMPRESA_ESPERADA]
    (empresa,) = corpo["companies"]
    ativos = empresa["anvisa_registrations_active"]
    assert ativos["value"] == 260
    assert ativos["source"] == "anvisa-produtos"
    assert ativos["published_at"] == DIA_DO_RETRATO
    assert corpo["anvisa_type"] == "cosmetics"
    assert "não faturamento" in corpo["anvisa_notice"]
    assert {f["source"] for f in corpo["sources"]} == {"rfb-cnpj", "anvisa-produtos"}
    proibidas = {"partners", "cpf", "socios", "email", "phone"}
    assert not aj.chaves_de(corpo) & proibidas


def test_conector_responde_a_pergunta_com_fonte_e_dia(cenario):
    transporte = httpx.ASGITransport(app=api.criar_app({VARIAVEL_DA_CHAVE: "1"}))
    with conector.conector(transporte) as cliente:
        corpo = conector.chamar_ok(
            cliente, cenario.valor, "buscar_empresas", **ARGUMENTOS_DA_PERGUNTA
        )
    assert isinstance(corpo, dict)
    _verificar_a_empresa(corpo)


def test_cli_responde_a_pergunta_com_fonte_e_dia(cenario, monkeypatch, tmp_path):
    http = aj.cliente_da_api(monkeypatch, base_de_mentira.AGORA)
    resultado = CliRunner().invoke(
        comandos.principal,
        [
            "prospectar",
            "--uf", "SP",
            "--cnae", "2063",
            "--anvisa-tipo", "cosmeticos",
            "--anvisa-ativos-min", "200",
            "--json",
        ],
        obj=lambda _endereco: http,
        env={
            configuracao.VARIAVEL_DA_CHAVE: cenario.valor,
            configuracao.VARIAVEL_DA_PASTA: str(tmp_path / "config"),
            configuracao.VARIAVEL_DO_ENDERECO: None,
        },
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    _verificar_a_empresa(json.loads(resultado.stdout))


def test_cli_em_tabela_mostra_a_contagem_a_fonte_e_o_aviso(
    cenario, monkeypatch, tmp_path
):
    http = aj.cliente_da_api(monkeypatch, base_de_mentira.AGORA)
    resultado = CliRunner().invoke(
        comandos.principal,
        ["prospectar", "--uf", "SP", "--anvisa-ativos-min", "200",
         "--anvisa-tipo", "cosmeticos", "--cnae", "2063"],
        obj=lambda _endereco: http,
        env={
            configuracao.VARIAVEL_DA_CHAVE: cenario.valor,
            configuracao.VARIAVEL_DA_PASTA: str(tmp_path / "config"),
            configuracao.VARIAVEL_DO_ENDERECO: None,
        },
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    saida = " ".join(resultado.stdout.split())  # a tabela quebra linhas
    assert EMPRESA_ESPERADA in saida
    assert "260" in saida
    assert "anvisa-produtos" in saida
    # o aviso inteiro (sem o corte de 40 caracteres das células) e o dia do retrato da Anvisa
    assert "sinal de porte da empresa, não faturamento." in saida
    assert f"Retrato da Anvisa de {DIA_DO_RETRATO}" in saida


def test_planilha_leva_o_aviso_da_anvisa_e_o_dia_do_retrato_na_linha(
    cenario, monkeypatch, tmp_path
):
    http = aj.cliente_da_api(monkeypatch, base_de_mentira.AGORA)
    destino = tmp_path / "lista.xlsx"
    resultado = CliRunner().invoke(
        comandos.principal,
        [
            "prospectar",
            "--uf",
            "SP",
            "--cnae",
            "2063",
            "--anvisa-tipo",
            "cosmeticos",
            "--anvisa-ativos-min",
            "200",
            "--planilha",
            str(destino),
        ],
        obj=lambda _endereco: http,
        env={
            configuracao.VARIAVEL_DA_CHAVE: cenario.valor,
            configuracao.VARIAVEL_DA_PASTA: str(tmp_path / "config"),
            configuracao.VARIAVEL_DO_ENDERECO: None,
        },
    )
    assert resultado.exit_code == 0, resultado.output
    folhas = openpyxl.load_workbook(destino)
    textos = [
        str(celula)
        for folha in folhas
        for linha in folha.iter_rows(values_only=True)
        for celula in linha
        if celula is not None
    ]
    assert any("não faturamento" in texto for texto in textos)
    # a coluna "público em" traz o dia da Receita e o da Anvisa, juntos
    assert any(DIA_DO_RETRATO in texto for texto in textos)
