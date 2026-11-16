"""A CLI `tickerlab` (linha 772; ADR 0127) contra a API externa de verdade, montada em memória.

Cada teste roda o comando pelo `CliRunner` do click, com o cliente HTTP trocado pelo `TestClient` do app de
verdade (`src.api.criar_app`, API externa ligada, banco SQLite novo, uma organização e uma chave de teste).
As demonstrações leem uma base de verdade gravada no `tmp_path`; a empresa e o fundo trocam só a leitura da
base por uma resposta pronta, para a chave, a quota, o consumo, o envelope e a tradução serem os de verdade.

Riscos que estes testes pegam: a chave aparecer numa saída ou num log; a tabela perder a fonte ou a data; o
`--json` não ser o envelope da API; um erro da API virar um traceback ou um código de saída errado.
"""

import contextlib
import json
import logging
import os
import re
import stat
from datetime import date
from typing import ClassVar

import httpx
import openpyxl
import pytest
from click.testing import CliRunner
from fastapi import HTTPException
from fastapi.testclient import TestClient
from tickerlab import cliente, comandos, configuracao, formato, planilha
from tickerlab.cliente import Saida

from base.porta import Porta
from src import api
from src.api_externa import acesso, rotas
from src.api_externa.conjuntos import (
    comparaveis,
    empresas,
    eventos,
    ficha,
    fundos,
    prospeccao,
    setores,
    vinculos,
)
from src.api_externa.envelope import campo
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_por_cnpj_comparaveis as comparaveis_de_mentira
from tests import test_api_externa_por_cnpj_comparaveis_rota as rota_dos_comparaveis
from tests import test_api_externa_por_cnpj_eventos as eventos_de_mentira
from tests import test_api_externa_por_cnpj_eventos_rota as rota_dos_eventos
from tests import test_api_externa_por_cnpj_ficha as ficha_de_mentira
from tests import test_api_externa_por_cnpj_vinculos as vinculos_de_mentira
from tests import test_api_externa_por_cnpj_vinculos_rota as rota_dos_vinculos
from tests import test_api_externa_prospeccao as busca_de_mentira
from tests.test_api_externa_demonstracoes import (
    AGORA,
    EMPRESA,
    SEM_DEMONSTRACOES,
    _base,
    _regras_das_demonstracoes,
)
from tests.test_api_externa_por_cnpj_perfil import _regras as _regras_do_perfil
from tests.test_api_externa_setores import DIA_DA_NOITE
from tests.test_api_externa_setores import _regras as _regras_do_setor
from tests.test_relatorio_setor import CPFL, OUTRA, gravar_noite

PUBLICO_EM = date(2026, 10, 31)


# ---------------------------------------------------------------- a API em memória


class _Empresas:
    """A leitura da Receita trocada por uma resposta pronta; guarda o que a rota pediu."""

    pedidos: ClassVar[list[tuple[str, date]]] = []

    def empresa(self, cnpj: str, dia: date) -> empresas.EmpresaServida:
        self.pedidos.append((cnpj, dia))
        corpo = {
            "cnpj": cnpj,
            "como_era_em": dia.isoformat(),
            "situacao_cadastral": _campo("ATIVA", "rfb-cnpj"),
            "razao_social": _campo("ALFA ENERGIA S.A.", "rfb-cnpj"),
            "matriz": _campo(True, "rfb-cnpj"),
        }
        return empresas.EmpresaServida(corpo, {"rfb-cnpj"}, 1)


class _Fundos:
    pedidos: ClassVar[list[tuple[str, date, float | None]]] = []

    def fundo(self, cnpj: str, dia: date, retorno: float | None) -> fundos.FundoServido:
        self.pedidos.append((cnpj, dia, retorno))
        cadastro = "cvm-cadastros"
        corpo = {
            "cnpj": cnpj,
            "como_era_em": dia.isoformat(),
            "cadastro": {
                "nome": _campo("ALFA FIC FIM", cadastro),
                "taxa_administracao_pct_ao_ano": _campo(1.5, cadastro),
            },
            "custo_da_taxa": {
                "hipotese": {"capital_inicial": 100000, "retorno_suposto": retorno},
                "prazos": [
                    {"anos": 1, "ficou_com_a_taxa": _campo(1612.5, cadastro)},
                    {"anos": 5, "ficou_com_a_taxa": _campo(8932.25, cadastro)},
                ],
            },
            "carteira": {
                "posicoes": [
                    {
                        "codigo": _campo("PETR4", "cvm-hist-cda"),
                        "valor": _campo(2500000.0, "cvm-hist-cda"),
                    }
                ],
                "cortada": True,
            },
        }
        return fundos.FundoServido(corpo, {cadastro, "cvm-hist-cda"}, 2)


def _campo(valor: object, fonte: str) -> dict:
    return campo(valor, fonte=fonte, publico_em=PUBLICO_EM, visto_em=None)


@pytest.fixture
def base_das_demonstracoes(tmp_path, monkeypatch):
    base = tmp_path / "base"
    arquivo = base / "demonstracoes" / "2025.parquet"
    arquivo.parent.mkdir(parents=True)
    _base().to_parquet(arquivo, index=False)
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    monkeypatch.setattr(rotas, "regras_da_api", _regras_das_demonstracoes)


@pytest.fixture
def leituras_prontas(monkeypatch):
    """A empresa e o fundo sem a base: só a leitura troca, a rota é a de verdade."""
    _Empresas.pedidos, _Fundos.pedidos = [], []
    monkeypatch.setattr(rotas, "abrir_porta", lambda _banco: contextlib.nullcontext())
    monkeypatch.setattr(rotas, "_leitor_de_empresas", lambda *_a: _Empresas())
    monkeypatch.setattr(rotas, "_leitor", lambda *_a: _Fundos())


@pytest.fixture
def cenario(banco):
    """Uma organização com chave e contrato dos três conjuntos de dado."""
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    for conjunto in ("companies", "financials", "funds"):
        aj.contrato(banco, ator, org, conjunto=conjunto)
    return ator, org, chave


@pytest.fixture
def chave(cenario) -> str:
    return cenario[2].valor


@pytest.fixture
def api_em_memoria(monkeypatch, banco) -> TestClient:
    return aj.cliente_da_api(monkeypatch, AGORA)


@pytest.fixture
def rodar(api_em_memoria, tmp_path):
    """Roda `tickerlab ...` contra a API em memória, com a pasta de configuração só do teste."""

    def rodar_(*argumentos: str, http=api_em_memoria, entrada=None, **ambiente):
        env = {
            configuracao.VARIAVEL_DA_PASTA: str(tmp_path / "config"),
            configuracao.VARIAVEL_DA_CHAVE: None,
            configuracao.VARIAVEL_DO_ENDERECO: None,
        } | ambiente
        return CliRunner().invoke(
            comandos.principal,
            list(argumentos),
            obj=lambda _endereco: http,
            env=env,
            input=entrada,
        )

    return rodar_


def _com_chave(chave: str) -> dict[str, str]:
    return {configuracao.VARIAVEL_DA_CHAVE: chave}


# ---------------------------------------------------------------- empresa


@pytest.mark.usefixtures("leituras_prontas")
def test_empresa_em_tabela_tem_fonte_data_e_aviso(rodar, chave):
    resultado = rodar(
        "empresa", "--so-cadastro", "11.111.111/0001-91", **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    saida = resultado.stdout
    assert "CNPJ: 11111111000191" in saida
    assert "Como era em: 2026-11-10" in saida
    linha = next(l for l in saida.splitlines() if l.startswith("registration_status"))
    assert "ATIVA" in linha and "rfb-cnpj" in linha and "2026-10-31" in linha
    assert "head_office" in saida and "sim" in saida
    assert "Fontes (cite ao usar estes números):\n- rfb-cnpj:" in saida
    assert saida.rstrip().endswith(formato.AVISO)


@pytest.mark.usefixtures("leituras_prontas")
def test_empresa_aceita_cnpj_com_ou_sem_pontuacao(rodar, chave):
    for escrito in ("11.111.111/0001-91", "11111111000191", " 11111111/0001-91 "):
        assert (
            rodar("empresa", "--so-cadastro", escrito, **_com_chave(chave)).exit_code
            == 0
        )
    assert {cnpj for cnpj, _dia in _Empresas.pedidos} == {"11111111000191"}


@pytest.mark.usefixtures("leituras_prontas")
def test_empresa_em_json_e_o_envelope_da_api(rodar, chave, api_em_memoria):
    resultado = rodar(
        "empresa", "--so-cadastro", "11111111000191", "--json", **_com_chave(chave)
    )
    assert resultado.exit_code == 0
    corpo = json.loads(resultado.stdout)
    direto = api_em_memoria.get(
        "/data/v1/companies/11111111000191", headers=aj.bearer(chave)
    ).json()
    assert corpo == direto
    assert corpo["registration_status"] == {
        "value": "ATIVA",
        "source": "rfb-cnpj",
        "published_at": "2026-10-31",
        "observed_at": None,
    }
    assert corpo["sources"][0]["source"] == "rfb-cnpj"


@pytest.mark.usefixtures("leituras_prontas")
def test_como_era_vai_para_a_api(rodar, chave):
    resultado = rodar(
        "empresa",
        "--so-cadastro",
        "11111111000191",
        "--como-era",
        "2025-06-30",
        **_com_chave(chave),
    )
    assert resultado.exit_code == 0
    assert _Empresas.pedidos == [("11111111000191", date(2025, 6, 30))]


# ---------------------------------------------------------------- empresa: o perfil (cadastro e entregas à CVM)


@pytest.fixture
def perfil_pronto(banco, cenario, monkeypatch, tmp_path):
    """A base de mentira do perfil (Receita e entregas), as tabelas prontas e o contrato de `profiles`."""
    base = ficha_de_mentira._base(tmp_path, ficha_de_mentira._rotulos())
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    monkeypatch.setattr(rotas, "regras_da_api", _regras_do_perfil)
    ator, org, _chave = cenario
    aj.contrato(banco, ator, org, conjunto=ficha.CONJUNTO)


@pytest.mark.usefixtures("perfil_pronto")
def test_empresa_e_o_perfil_com_cadastro_e_entregas(rodar, chave):
    resultado = rodar("empresa", EMPRESA, **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    saida = resultado.stdout
    assert "## registration" in saida and "rfb-cnpj" in saida
    entregas = saida.split("## periodic_filings", 1)[1]
    dfp_2023 = next(l for l in entregas.splitlines() if "2023-12-31" in l)
    assert "DFP" in dfp_2023 and ficha.NO_PRAZO in dfp_2023 and "2024-03-20" in dfp_2023
    assert "cvm-hist-dfp" in dfp_2023
    assert "- cvm-hist-dfp:" in saida and "- rfb-cnpj:" in saida
    assert saida.rstrip().endswith(formato.AVISO)


@pytest.mark.usefixtures("perfil_pronto")
def test_empresa_em_json_e_o_envelope_do_perfil(rodar, chave, api_em_memoria):
    resultado = rodar("empresa", EMPRESA, "--json", **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    direto = api_em_memoria.get(
        f"/data/v1/companies/{EMPRESA}/profile", headers=aj.bearer(chave)
    ).json()
    assert json.loads(resultado.stdout) == direto
    assert direto["periodic_filings"][0]["filing_status"]["source"].startswith("cvm-")


@pytest.mark.usefixtures("perfil_pronto")
def test_empresa_como_era_nao_mostra_a_entrega_que_veio_depois(rodar, chave):
    resultado = rodar(
        "empresa", EMPRESA, "--como-era", "2025-06-30", "--json", **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    corpo = json.loads(resultado.stdout)
    dfp_2024 = next(
        linha
        for linha in corpo["periodic_filings"]
        if linha["reference_period"]["value"] == "2024-12-31"
    )
    assert dfp_2024["filing_status"]["value"] == ficha.NAO_ENTREGUE


@pytest.mark.usefixtures("perfil_pronto")
def test_empresa_em_planilha_tem_a_aba_das_entregas(rodar, chave, tmp_path):
    arquivo = tmp_path / "alfa.xlsx"
    resultado = rodar(
        "empresa", EMPRESA, "--planilha", str(arquivo), **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    abas = _abrir_xlsx(arquivo)
    assert list(abas) == ["campos", "periodic_filings", "limits", "fontes"]
    entregas = _linhas_com_cabecalho(abas["periodic_filings"])
    assert {e["filing_status"] for e in entregas} >= {ficha.NO_PRAZO}
    campos = {linha[0]: linha for linha in abas["campos"][1:]}
    assert campos["registration › legal_name"][2] == "rfb-cnpj"


def test_chave_sem_o_perfil_usa_so_o_cadastro(rodar, chave, tmp_path, monkeypatch):
    """A chave com só `companies` no contrato: o perfil é sem dado (código 5), o cadastro sai."""
    base = ficha_de_mentira._base(tmp_path, ficha_de_mentira._rotulos())
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    monkeypatch.setattr(rotas, "regras_da_api", _regras_do_perfil)
    perfil = rodar("empresa", EMPRESA, **_com_chave(chave))
    assert perfil.exit_code == Saida.SEM_DADO
    assert "tickerlab catalogo" in perfil.output
    cadastro = rodar("empresa", "--so-cadastro", EMPRESA, "--json", **_com_chave(chave))
    assert cadastro.exit_code == 0, cadastro.output
    corpo = json.loads(cadastro.stdout)
    assert corpo["legal_name"]["source"] == "rfb-cnpj"
    assert "periodic_filings" not in corpo


# ---------------------------------------------------------------- demonstrações (base de verdade)


@pytest.mark.usefixtures("base_das_demonstracoes")
def test_demonstracoes_em_tabela(rodar, chave):
    resultado = rodar("demonstracoes", EMPRESA, **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    linhas = resultado.stdout.splitlines()
    cabecalho = next(l for l in linhas if l.startswith("statement"))
    assert cabecalho.split()[-3:] == ["fonte", "público", "em"]
    receita_de_2025 = next(
        l for l in linhas if "2025-01-01" in l and "2025-12-31" in l and "3.01" in l
    )
    assert "200" in receita_de_2025
    assert "cvm-hist-dfp" in receita_de_2025 and "2026-03-15" in receita_de_2025
    assert (
        "- cvm-hist-dfp:" in resultado.stdout and "- cvm-hist-itr:" in resultado.stdout
    )


@pytest.mark.usefixtures("base_das_demonstracoes")
def test_demonstracoes_como_eram_e_por_periodo(rodar, chave):
    resultado = rodar(
        "demonstracoes", EMPRESA, "--como-era", "2025-04-01", "--periodo",
        "2024-12-31", "--json", **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    corpo = json.loads(resultado.stdout)
    assert corpo["known_at"] == "2025-04-01"
    (linha,) = corpo["rows"]
    assert linha["value"]["value"] == 100.0  # a versão 1, antes da reapresentação
    assert linha["revision"]["value"] == 1


@pytest.mark.usefixtures("base_das_demonstracoes")
def test_demonstracoes_cortadas_avisam(rodar, chave, monkeypatch):
    monkeypatch.setattr(acesso, "linhas_por_resposta", lambda _contexto: 2)
    resultado = rodar("demonstracoes", EMPRESA, **_com_chave(chave))
    assert resultado.exit_code == 0
    assert formato.AVISO_DE_CORTE in resultado.stdout


@pytest.mark.usefixtures("base_das_demonstracoes")
def test_cnpj_sem_demonstracoes_sai_com_codigo_de_sem_dado(rodar, chave):
    resultado = rodar("demonstracoes", SEM_DEMONSTRACOES, **_com_chave(chave))
    assert resultado.exit_code == Saida.SEM_DADO
    assert resultado.stdout == ""
    assert "Faturamento de empresa fechada a base não tem" in resultado.stderr
    assert "não estima" in resultado.stderr


def test_sem_demonstracao_diz_a_mesma_frase_do_conector():
    from conector_remoto.ferramentas import MENSAGEM_SEM_DEMONSTRACAO

    assert cliente.SEM_DEMONSTRACAO == MENSAGEM_SEM_DEMONSTRACAO


@pytest.mark.usefixtures("base_das_demonstracoes")
def test_conjunto_fora_do_contrato_tambem_e_sem_dado(rodar, banco):
    ator = aj.admin(banco)
    beta = aj.organizacao(banco, ator, nome="Beta Wealth")
    chave_da_beta = aj.chave(banco, ator, beta).valor  # sem contrato nenhum
    resultado = rodar("demonstracoes", EMPRESA, **_com_chave(chave_da_beta))
    assert resultado.exit_code == Saida.SEM_DADO


# ---------------------------------------------------------------- fundo


@pytest.mark.usefixtures("leituras_prontas")
def test_fundo_em_tabela_tem_cada_bloco_com_fonte(rodar, chave):
    resultado = rodar(
        "fundo", "11111111000191", "--retorno-suposto", "0.12", **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    saida = resultado.stdout
    assert _Fundos.pedidos[0][2] == 0.12
    assert "## profile" in saida and "## fee_cost › horizons" in saida
    assert "## holdings › positions" in saida
    taxa = next(l for l in saida.splitlines() if l.startswith("management_fee"))
    assert "1,50" in taxa and "cvm-cadastros" in taxa
    assert "1.612,50" in saida  # número no jeito brasileiro
    assert "2.500.000" in saida
    assert "initial_amount: 100.000" in saida
    assert formato.AVISO_DE_CORTE in saida
    assert "- cvm-cadastros:" in saida and "- cvm-hist-cda:" in saida


@pytest.mark.usefixtures("leituras_prontas")
def test_fundo_sem_retorno_suposto_nao_manda_o_parametro(rodar, chave):
    assert rodar("fundo", "11111111000191", **_com_chave(chave)).exit_code == 0
    assert _Fundos.pedidos[0][2] is None


@pytest.mark.usefixtures("leituras_prontas")
def test_retorno_suposto_fora_do_plausivel_e_pedido_invalido(rodar, chave):
    resultado = rodar(
        "fundo", "11111111000191", "--retorno-suposto", "5", **_com_chave(chave)
    )
    assert resultado.exit_code == Saida.PEDIDO_INVALIDO
    assert "--retorno-suposto" in resultado.stderr


# ---------------------------------------------------------------- setor (molde D, a ficha da noite)


@pytest.fixture
def setor_pronto(banco, cenario, monkeypatch, tmp_path):
    """A noite das elétricas gravada, o contrato de `sectors` e as tabelas do setor prontas."""
    _noite_das_eletricas(tmp_path, monkeypatch)
    ator, org, _chave = cenario
    aj.contrato(banco, ator, org, conjunto=setores.CONJUNTO)


def _noite_das_eletricas(tmp_path, monkeypatch) -> None:
    """A ficha da noite com as elétricas, a pasta das fichas apontando para ela e as regras do setor."""
    pasta = tmp_path / "noite"
    pasta.mkdir()
    gravar_noite(pasta)
    monkeypatch.setenv("TICKERLAB_DOSSIES", str(pasta))
    monkeypatch.setattr(rotas, "regras_da_api", _regras_do_setor)


def _pedidos_do_mes(banco, cenario) -> int:
    with banco.connect() as conexao:
        return cb.consumo_do_mes(conexao, cenario[1].id, AGORA.date()).pedidos


@pytest.mark.usefixtures("setor_pronto")
def test_setor_sem_chave_lista_os_setores_sem_gastar_a_quota(
    rodar, chave, banco, cenario
):
    resultado = rodar("setor", **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    linha = next(l for l in resultado.stdout.splitlines() if l.startswith("eletricas"))
    assert "Elétricas" in linha and DIA_DA_NOITE in linha
    assert "tickerlab setor eletricas" in resultado.stdout
    corpo = json.loads(rodar("setor", "--json", **_com_chave(chave)).stdout)
    assert corpo == {
        "sectors": [
            {"sector": "eletricas", "name": "Elétricas", "known_at": DIA_DA_NOITE}
        ]
    }
    assert _pedidos_do_mes(banco, cenario) == 0


@pytest.mark.usefixtures("setor_pronto")
def test_setor_em_tabela_tem_cada_serie_com_fonte_e_data(rodar, chave):
    resultado = rodar("setor", "eletricas", **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    saida = resultado.stdout
    assert "Setor: eletricas" in saida and f"Como era em: {DIA_DA_NOITE}" in saida
    assert "## by_series › aneel_consumidores › concentration" in saida
    assert "## by_series › aneel_consumidores › member_shares" in saida
    hhi = next(l for l in saida.splitlines() if l.startswith("2025") and "4.626" in l)
    assert "aneel-samp" in hhi and DIA_DA_NOITE in hhi
    membros = saida.split("## members", 1)[1]
    assert CPFL in membros and OUTRA in membros and "cvm-cadastros" in membros
    assert "- aneel-samp:" in saida and "- cvm-cadastros:" in saida
    assert saida.rstrip().endswith(formato.AVISO)


@pytest.mark.usefixtures("setor_pronto")
def test_setor_em_json_e_o_envelope_da_api(
    rodar, chave, api_em_memoria, banco, cenario
):
    resultado = rodar("setor", "eletricas", "--json", **_com_chave(chave))
    assert resultado.exit_code == 0
    direto = api_em_memoria.get(
        "/data/v1/sectors/eletricas", headers=aj.bearer(chave)
    ).json()
    assert json.loads(resultado.stdout) == direto
    assert direto["by_series"][0]["concentration"][0]["hhi"]["source"] == "aneel-samp"
    assert _pedidos_do_mes(banco, cenario) == 2  # o setor gasta a quota; a lista, não


@pytest.mark.usefixtures("setor_pronto")
def test_setor_como_era_antes_da_noite_e_sem_dado(rodar, chave):
    resultado = rodar(
        "setor", "eletricas", "--como-era", "2026-10-01", **_com_chave(chave)
    )
    assert resultado.exit_code == Saida.SEM_DADO
    assert resultado.stdout == ""
    assert "Não há dado disponível" in resultado.stderr
    assert (
        rodar(
            "setor", "eletricas", "--como-era", DIA_DA_NOITE, **_com_chave(chave)
        ).exit_code
        == 0
    )


@pytest.mark.usefixtures("setor_pronto")
def test_setor_desconhecido_e_sem_dado_e_chave_mal_escrita_nem_chega_a_api(
    rodar, chave, banco, cenario
):
    assert rodar("setor", "petroleo", **_com_chave(chave)).exit_code == Saida.SEM_DADO
    antes = _pedidos_do_mes(banco, cenario)
    for mal_escrita in (
        "../catalog",
        "Elétricas",
        "bancos?known_at=2020-01-01",
        "x" * 41,
    ):
        resultado = rodar("setor", mal_escrita, **_com_chave(chave))
        assert resultado.exit_code == Saida.USO, mal_escrita
        assert "tickerlab setor" in resultado.output
    assert _pedidos_do_mes(banco, cenario) == antes


@pytest.mark.usefixtures("setor_pronto")
def test_setor_cortado_avisa(rodar, chave, monkeypatch):
    monkeypatch.setattr(acesso, "linhas_por_resposta", lambda _contexto: 2)
    resultado = rodar("setor", "eletricas", **_com_chave(chave))
    assert resultado.exit_code == 0
    assert formato.AVISO_DE_CORTE in resultado.stdout


def test_setor_fora_do_contrato_e_sem_dado(rodar, chave, tmp_path, monkeypatch):
    _noite_das_eletricas(
        tmp_path, monkeypatch
    )  # a chave tem contrato, mas não de `sectors`
    assert rodar("setor", "eletricas", **_com_chave(chave)).exit_code == Saida.SEM_DADO


# ---------------------------------------------------------------- planilha (CSV e XLSX, para o Excel)


def _abrir_xlsx(arquivo) -> dict[str, list[tuple]]:
    """As abas do XLSX como o Excel as leria (openpyxl só nos testes; o pacote não depende dele)."""
    pasta = openpyxl.load_workbook(arquivo)
    return {
        aba.title: list(aba.iter_rows(values_only=True)) for aba in pasta.worksheets
    }


def _linhas_com_cabecalho(linhas: list[tuple]) -> list[dict]:
    cabecalho, *resto = linhas
    return [dict(zip(cabecalho, linha, strict=True)) for linha in resto]


@pytest.mark.usefixtures("base_das_demonstracoes")
def test_demonstracoes_em_xlsx_tem_numero_fonte_e_data_em_cada_linha(
    rodar, chave, tmp_path
):
    arquivo = tmp_path / "alfa.xlsx"
    resultado = rodar(
        "demonstracoes", EMPRESA, "--planilha", str(arquivo), **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    assert "Planilha gravada" in resultado.stdout and str(arquivo) in resultado.stdout
    assert "- cvm-hist-dfp:" in resultado.stdout
    assert resultado.stdout.rstrip().endswith(formato.AVISO)
    abas = _abrir_xlsx(arquivo)
    assert list(abas) == ["campos", "rows", "fontes"]
    linhas = _linhas_com_cabecalho(abas["rows"])
    receita = next(
        l for l in linhas
        if l["account"] == "3.01" and str(l["end"]).startswith("2025-12-31")
        and str(l["start"]).startswith("2025-01-01")
    )  # fmt: skip
    assert receita["value"] == 200  # número, não texto formatado
    assert (
        receita["fonte"] == "cvm-hist-dfp" and receita["publicado_em"] == "2026-03-15"
    )
    campos = {linha[0]: linha[1] for linha in abas["campos"][1:]}
    assert campos["cnpj"] == EMPRESA
    fontes = {linha[0]: linha[1] for linha in abas["fontes"][1:]}
    assert "cvm-hist-dfp" in fontes and fontes["aviso"] == formato.AVISO


@pytest.mark.usefixtures("setor_pronto")
def test_setor_em_xlsx_tem_uma_aba_por_tabela(rodar, chave, tmp_path):
    arquivo = tmp_path / "eletricas.xlsx"
    resultado = rodar(
        "setor", "eletricas", "--planilha", str(arquivo), **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    abas = _abrir_xlsx(arquivo)
    assert all(len(nome) <= planilha.LIMITE_DO_NOME_DA_ABA for nome in abas)
    concentracao = next(nome for nome in abas if nome.endswith(".concentration"))
    assert concentracao.startswith("aneel_consumidor")  # a série que distingue as abas
    hhi = next(
        l for l in _linhas_com_cabecalho(abas[concentracao]) if l["year"] == 2025
    )
    assert hhi["hhi"] == pytest.approx(4626, abs=1)
    assert hhi["fonte"] == "aneel-samp" and hhi["publicado_em"] == DIA_DA_NOITE
    membros = [l["cnpj"] for l in _linhas_com_cabecalho(abas["members"])]
    assert CPFL in membros and OUTRA in membros
    assert abas["fontes"][-1] == ("aviso", formato.AVISO, None)


@pytest.mark.usefixtures("setor_pronto")
def test_lista_de_setores_em_csv_para_o_excel(rodar, chave, tmp_path):
    arquivo = tmp_path / "setores.csv"
    resultado = rodar("setor", "--planilha", str(arquivo), **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    conteudo = arquivo.read_bytes()
    assert conteudo.startswith(b"\xef\xbb\xbf")  # o Excel só lê o acento com o BOM
    assert conteudo.decode("utf-8-sig").splitlines() == [
        "sector;name;known_at",
        f"eletricas;Elétricas;{DIA_DA_NOITE}",
    ]


@pytest.mark.usefixtures("leituras_prontas")
def test_fundo_em_csv_e_um_arquivo_por_tabela_com_virgula_decimal(
    rodar, chave, tmp_path
):
    arquivo = tmp_path / "fundo.csv"
    resultado = rodar(
        "fundo", "11111111000191", "--planilha", str(arquivo), **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    gravados = sorted(p.name for p in tmp_path.glob("fundo-*.csv"))
    assert gravados == [
        "fundo-campos.csv",
        "fundo-fee_cost_horizons.csv",
        "fundo-holdings_positions.csv",
    ]
    assert not arquivo.exists()
    for nome in gravados:
        assert nome in resultado.stdout
    campos = (tmp_path / "fundo-campos.csv").read_text(encoding="utf-8-sig")
    assert (
        "profile › management_fee_pct_per_year;1,5;cvm-cadastros;2026-10-31" in campos
    )
    prazos = (tmp_path / "fundo-fee_cost_horizons.csv").read_text(encoding="utf-8-sig")
    assert prazos.splitlines()[1] == "1;1612,5;cvm-cadastros;2026-10-31"


@pytest.mark.usefixtures("leituras_prontas")
def test_planilha_com_json_grava_e_imprime_o_envelope(rodar, chave, tmp_path):
    arquivo = tmp_path / "alfa.xlsx"
    resultado = rodar(
        "empresa",
        "--so-cadastro",
        EMPRESA,
        "--planilha",
        str(arquivo),
        "--json",
        **_com_chave(chave),
    )
    assert resultado.exit_code == 0, resultado.output
    assert json.loads(resultado.stdout)["legal_name"]["value"] == "ALFA ENERGIA S.A."
    campos = {l[0]: l for l in _abrir_xlsx(arquivo)["campos"][1:]}
    assert campos["legal_name"][1:3] == ("ALFA ENERGIA S.A.", "rfb-cnpj")
    assert campos["head_office"][1] is True


def test_planilha_de_extensao_desconhecida_nem_chega_a_api(rodar, chave, tmp_path):
    resultado = rodar(
        "empresa", "--so-cadastro", EMPRESA, "--planilha", str(tmp_path / "alfa.ods"), http=None,
        **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == Saida.USO
    assert ".xlsx" in resultado.output and ".csv" in resultado.output


@pytest.mark.usefixtures("leituras_prontas")
def test_planilha_em_pasta_que_nao_existe_e_erro_claro(rodar, chave, tmp_path):
    destino = tmp_path / "nao-existe" / "alfa.xlsx"
    resultado = rodar(
        "empresa",
        "--so-cadastro",
        EMPRESA,
        "--planilha",
        str(destino),
        **_com_chave(chave),
    )
    assert resultado.exit_code == Saida.ERRO
    assert "não consegui gravar a planilha" in resultado.output


@pytest.mark.parametrize("texto", ["=HYPERLINK(1)", "+1", "-1", "@SOMA(1)", "\t=1"])
def test_texto_que_parece_formula_nao_vira_formula(texto, tmp_path):
    tabela = planilha.Tabela("t", ["nome"], [[texto]])
    assert planilha.texto_do_csv(tabela).splitlines()[1].strip('"') == "'" + texto
    arquivo = tmp_path / "t.xlsx"
    arquivo.write_bytes(planilha.conteudo_do_xlsx([tabela]))
    celula = openpyxl.load_workbook(arquivo).active["A2"]  # type: ignore[index]
    assert celula.data_type == "s"  # texto, nunca fórmula


def test_numero_negativo_continua_numero_no_csv():
    tabela = planilha.Tabela("t", ["valor"], [[-1.5], [-2]])
    assert planilha.texto_do_csv(tabela).splitlines()[1:] == ["-1,5", "-2"]


def test_nomes_das_abas_que_o_excel_aceita():
    tabelas = [
        planilha.Tabela("a › b:c/d", []),
        planilha.Tabela("by_series › aneel_consumidores › concentration", []),
        planilha.Tabela("by_series › aneel_consumidores_outra › concentration", []),
        planilha.Tabela("CAMPOS", []),
        planilha.Tabela("campos", []),
    ]
    nomes = planilha.nomes_das_abas(tabelas)
    assert nomes[0] == "a.b_c_d"
    assert nomes[1] == "aneel_consumidore.concentration"
    assert len({n.lower() for n in nomes}) == len(nomes)
    assert all(len(n) <= planilha.LIMITE_DO_NOME_DA_ABA for n in nomes)
    assert nomes[4] == "campos~2"


def test_a_mesma_resposta_da_o_mesmo_xlsx():
    tabela = planilha.Tabela("t", ["a"], [[1], ["x & <y>"], [None], [True]])
    assert planilha.conteudo_do_xlsx([tabela]) == planilha.conteudo_do_xlsx([tabela])


# ---------------------------------------------------------------- catálogo e consumo


def test_catalogo_em_tabela_e_json(rodar, banco, monkeypatch):
    ator = aj.admin(banco)
    alfa = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, alfa).valor
    aj.contrato(banco, ator, alfa)  # dfp
    monkeypatch.setattr(rotas, "regras_da_api", lambda: aj.portao_liberando())
    tabela = rodar("catalogo", **_com_chave(chave))
    assert tabela.exit_code == 0, tabela.output
    linha = next(l for l in tabela.stdout.splitlines() if l.startswith("dfp"))
    assert linha.split() == ["dfp", "analysis", "value", "cvm-dfp"]
    assert "- cvm-dfp: Fonte: " in tabela.stdout
    corpo = json.loads(rodar("catalogo", "--json", **_com_chave(chave)).stdout)
    assert corpo["datasets"][0]["dataset"] == "dfp"


def test_catalogo_vazio_diz_o_que_fazer(rodar, chave):
    resultado = rodar("catalogo", **_com_chave(chave))
    assert resultado.exit_code == 0
    assert "ainda não tem nenhum conjunto liberado" in resultado.stdout
    assert "Fontes: nenhuma fonte nesta resposta." in resultado.stdout


@pytest.mark.usefixtures("leituras_prontas")
def test_consumo_mostra_o_mes_e_os_limites(rodar, chave):
    rodar("empresa", "--so-cadastro", EMPRESA, **_com_chave(chave))
    resultado = rodar("consumo", **_com_chave(chave))
    assert resultado.exit_code == 0
    pedidos = next(
        l for l in resultado.stdout.splitlines() if l.startswith("pedidos no mês")
    )
    assert pedidos.split()[-1] == "1"
    assert (
        "Fonte: TickerLab, consumo da sua organização no mês 2026-11"
        in resultado.stdout
    )
    corpo = json.loads(rodar("consumo", "--json", **_com_chave(chave)).stdout)
    assert corpo["requests"] == 1 and corpo["month"] == "2026-11"


# ---------------------------------------------------------------- erros e códigos de saída


def test_sem_chave_sai_com_codigo_da_chave(rodar):
    resultado = rodar("consumo")
    assert resultado.exit_code == Saida.CHAVE
    assert "tickerlab login" in resultado.stderr


def test_chave_recusada(rodar, cenario):
    resultado = rodar("consumo", **_com_chave("tld_aaaaaaaa_" + "x" * 43))
    assert resultado.exit_code == Saida.CHAVE
    assert "recusou a chave" in resultado.stderr


@pytest.mark.usefixtures("leituras_prontas")
def test_quota_do_mes_e_limite_do_minuto(rodar, chave, monkeypatch):
    def sem_quota(*_a, **_k):
        raise HTTPException(429, detail=acesso.CODIGO_DA_QUOTA_DO_MES)

    monkeypatch.setattr(acesso, "exigir_quota", sem_quota)
    resultado = rodar("empresa", "--so-cadastro", EMPRESA, **_com_chave(chave))
    assert resultado.exit_code == Saida.LIMITE
    assert "quota de pedidos do mês acabou" in resultado.stderr

    def sem_minuto(*_a, **_k):
        raise HTTPException(
            429, detail=acesso.CODIGO_DO_LIMITE_DO_MINUTO, headers={"Retry-After": "60"}
        )

    monkeypatch.setattr(acesso, "_conferir_minuto", sem_minuto)
    esperas: list[float] = []
    monkeypatch.setattr(cliente, "esperar", esperas.append)
    resultado = rodar("catalogo", **_com_chave(chave))
    assert resultado.exit_code == Saida.LIMITE
    assert "tente de novo em 60 segundos" in resultado.stderr
    assert esperas == [60]  # esperou uma vez, e o limite continuou


def _limite_do_minuto_e_depois(corpo: dict, retry_after: str):
    """Um servidor que recusa o 1º pedido pelo limite do minuto e responde `corpo` nos seguintes."""
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        if len(pedidos) == 1:
            return httpx.Response(
                429,
                json={"detail": acesso.CODIGO_DO_LIMITE_DO_MINUTO},
                headers={"Retry-After": retry_after},
            )
        return httpx.Response(200, json=corpo)

    return _http_falso(responder), pedidos


def test_limite_do_minuto_espera_e_tenta_de_novo_sozinho(rodar, chave, monkeypatch):
    esperas: list[float] = []
    monkeypatch.setattr(cliente, "esperar", esperas.append)
    http, pedidos = _limite_do_minuto_e_depois({"datasets": []}, "7")
    resultado = rodar("catalogo", "--json", http=http, **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    assert esperas == [7] and len(pedidos) == 2
    assert "esperando 7 segundos" in resultado.stderr
    assert json.loads(resultado.stdout) == {"datasets": []}


@pytest.mark.parametrize("retry_after", ["3600", "Wed, 21 Oct 2026 07:28:00 GMT"])
def test_espera_longa_ou_ilegivel_nao_prende_o_terminal(
    rodar, chave, monkeypatch, retry_after
):
    esperas: list[float] = []
    monkeypatch.setattr(cliente, "esperar", esperas.append)
    http, pedidos = _limite_do_minuto_e_depois({}, retry_after)
    resultado = rodar("catalogo", http=http, **_com_chave(chave))
    assert resultado.exit_code == Saida.LIMITE
    assert esperas == [] and len(pedidos) == 1


@pytest.mark.usefixtures("leituras_prontas")
def test_quota_do_mes_nao_espera(rodar, chave, monkeypatch):
    def sem_quota(*_a, **_k):
        raise HTTPException(429, detail=acesso.CODIGO_DA_QUOTA_DO_MES)

    monkeypatch.setattr(acesso, "exigir_quota", sem_quota)
    esperas: list[float] = []
    monkeypatch.setattr(cliente, "esperar", esperas.append)
    resultado = rodar("empresa", "--so-cadastro", EMPRESA, **_com_chave(chave))
    assert resultado.exit_code == Saida.LIMITE and esperas == []


@pytest.mark.usefixtures("leituras_prontas")
def test_digito_errado_e_pedido_invalido(rodar, chave):
    resultado = rodar("empresa", "--so-cadastro", "11111111000100", **_com_chave(chave))
    assert resultado.exit_code == Saida.PEDIDO_INVALIDO
    assert "dígito verificador" in resultado.stderr


def test_cnpj_mal_escrito_nem_chega_a_api(rodar, chave):
    # http=None: se a CLI tentasse falar com a API, o comando quebraria (código 1)
    resultado = rodar("empresa", "--so-cadastro", "123", http=None, **_com_chave(chave))
    assert resultado.exit_code == Saida.USO
    assert "14 caracteres" in resultado.output


@pytest.mark.usefixtures("leituras_prontas")
def test_data_no_futuro_e_pedido_invalido(rodar, chave):
    resultado = rodar(
        "empresa",
        "--so-cadastro",
        EMPRESA,
        "--como-era",
        "2030-01-01",
        **_com_chave(chave),
    )
    assert resultado.exit_code == Saida.PEDIDO_INVALIDO
    assert "futuro" in resultado.stderr


def test_base_fora_do_ar(rodar, chave, monkeypatch):
    def sem_base(_banco):
        raise OSError("sem disco")

    monkeypatch.setattr(rotas, "abrir_porta", sem_base)
    resultado = rodar("empresa", "--so-cadastro", EMPRESA, **_com_chave(chave))
    assert resultado.exit_code == Saida.FORA_DO_AR
    assert "fora do ar" in resultado.stderr


def test_api_externa_desligada_no_endereco(rodar, chave, banco):
    desligada = TestClient(api.criar_app({}))
    resultado = rodar("consumo", http=desligada, **_com_chave(chave))
    assert resultado.exit_code == Saida.FORA_DO_AR
    assert "TICKERLAB_API_URL" in resultado.stderr


def _http_falso(responder) -> httpx.Client:
    return httpx.Client(
        base_url="https://api.exemplo.test", transport=httpx.MockTransport(responder)
    )


def test_sem_internet(rodar, chave):
    def cai(pedido: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem rede", request=pedido)

    resultado = rodar("consumo", http=_http_falso(cai), **_com_chave(chave))
    assert resultado.exit_code == Saida.FORA_DO_AR
    assert "Não consegui falar com a API" in resultado.stderr


def test_resposta_que_nao_e_json(rodar, chave):
    resultado = rodar(
        "consumo",
        http=_http_falso(lambda _p: httpx.Response(200, text="<html>")),
        **_com_chave(chave),
    )
    assert resultado.exit_code == Saida.FORA_DO_AR


def test_a_chave_vai_so_no_cabecalho(rodar, chave):
    vistos: list[httpx.Request] = []

    def guardar(pedido: httpx.Request) -> httpx.Response:
        vistos.append(pedido)
        return httpx.Response(200, json={"month": "2026-11"})

    rodar("consumo", http=_http_falso(guardar), **_com_chave(chave))
    (pedido,) = vistos
    assert pedido.headers["Authorization"] == f"Bearer {chave}"
    assert chave not in str(pedido.url)


def test_endereco_sem_https_e_recusado(rodar, chave):
    resultado = rodar(
        "consumo",
        http=None,
        **_com_chave(chave),
        **{configuracao.VARIAVEL_DO_ENDERECO: "http://api.exemplo.com"},
    )
    assert resultado.exit_code == Saida.USO
    assert "https://" in resultado.stderr


@pytest.mark.parametrize(
    ("endereco", "esperado"),
    [
        (None, "https://api.tickerlab.com.br"),
        ("https://api.exemplo.com/", "https://api.exemplo.com"),
        ("http://localhost:8000", "http://localhost:8000"),
        ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
        ("http://api.tickerlab.localhost", "http://api.tickerlab.localhost"),
    ],
)
def test_enderecos_aceitos(endereco, esperado):
    ambiente = {} if endereco is None else {configuracao.VARIAVEL_DO_ENDERECO: endereco}
    assert configuracao.endereco_da_api(ambiente) == esperado


# ---------------------------------------------------------------- a chave nunca aparece


@pytest.mark.usefixtures("leituras_prontas", "base_das_demonstracoes")
def test_a_chave_nao_aparece_em_saida_nem_log(rodar, chave, caplog):
    caplog.set_level(logging.DEBUG)
    resultados = [
        rodar(*comando, **_com_chave(chave))
        for comando in (
            ("empresa", "--so-cadastro", EMPRESA),
            ("empresa", "--so-cadastro", EMPRESA, "--json"),
            ("demonstracoes", SEM_DEMONSTRACOES),  # erro
            ("empresa", "--so-cadastro", "11111111000100"),  # erro
            ("catalogo", "--json"),
            ("consumo",),
        )
    ]
    resultados.append(rodar("login", entrada=f"{chave}\n"))
    resultados.append(rodar("consumo", **_com_chave("tld_aaaaaaaa_" + "x" * 43)))
    for resultado in resultados:
        assert chave not in resultado.output
        assert chave not in resultado.stderr
    assert chave not in caplog.text
    assert "tld_aaaaaaaa_" not in caplog.text


# ---------------------------------------------------------------- login e logout


def test_login_confere_grava_so_para_o_dono_e_vale_sem_a_variavel(
    rodar, chave, tmp_path
):
    resultado = rodar("login", entrada=f"{chave}\n")
    assert resultado.exit_code == 0, resultado.output
    arquivo = tmp_path / "config" / configuracao.NOME_DO_ARQUIVO
    assert json.loads(arquivo.read_text(encoding="utf-8")) == {"api_key": chave}
    if os.name != "nt":  # no Windows, a pasta do usuário já é só da conta
        assert stat.S_IMODE(arquivo.stat().st_mode) == configuracao.SO_O_DONO_LE
    assert rodar("consumo").exit_code == 0  # sem TICKERLAB_API_KEY: lê o arquivo


def test_login_com_chave_recusada_nao_grava(rodar, cenario, tmp_path):
    resultado = rodar("login", entrada="tld_aaaaaaaa_" + "x" * 43 + "\n")
    assert resultado.exit_code == Saida.CHAVE
    assert not (tmp_path / "config" / configuracao.NOME_DO_ARQUIVO).exists()


def test_login_sem_conferir_e_logout(rodar, tmp_path):
    resultado = rodar("login", "--sem-conferir", entrada="tld_qualquer\n", http=None)
    assert resultado.exit_code == 0
    arquivo = tmp_path / "config" / configuracao.NOME_DO_ARQUIVO
    assert arquivo.exists()
    assert "Chave apagada" in rodar("logout").stdout
    assert not arquivo.exists()
    assert "Não havia chave" in rodar("logout").stdout


def test_login_com_espaco_no_meio_e_recusado(rodar, tmp_path):
    resultado = rodar("login", "--sem-conferir", entrada="tld_abc def\n")
    assert resultado.exit_code == Saida.USO
    assert not (tmp_path / "config" / configuracao.NOME_DO_ARQUIVO).exists()


def test_variavel_vale_mais_que_o_arquivo(tmp_path):
    ambiente = {configuracao.VARIAVEL_DA_PASTA: str(tmp_path)}
    configuracao.gravar_chave("tld_do_arquivo", ambiente)
    assert configuracao.chave_da_api(ambiente) == "tld_do_arquivo"
    com_variavel = ambiente | {configuracao.VARIAVEL_DA_CHAVE: " tld_da_variavel "}
    assert configuracao.chave_da_api(com_variavel) == "tld_da_variavel"


def test_arquivo_estragado_pede_login_de_novo(tmp_path):
    ambiente = {configuracao.VARIAVEL_DA_PASTA: str(tmp_path)}
    configuracao.arquivo_da_chave(ambiente).write_text("{", encoding="utf-8")
    with pytest.raises(configuracao.ConfiguracaoInvalidaError, match="login"):
        configuracao.chave_da_api(ambiente)


def test_pasta_da_configuracao_por_sistema():
    assert configuracao.pasta_da_configuracao(
        {configuracao.VARIAVEL_DA_PASTA: "/x"}
    ) == configuracao.Path("/x")
    # sem APPDATA (Linux, macOS), a pasta segue o XDG
    assert configuracao.pasta_da_configuracao(
        {"XDG_CONFIG_HOME": "/home/a/.config"}
    ) == configuracao.Path("/home/a/.config/tickerlab")


# ---------------------------------------------------------------- instruções e pacote


def test_instrucoes_do_agente(rodar):
    agentes = rodar("instrucoes")
    assert agentes.exit_code == 0
    assert "Nada é recomendação de investimento" in agentes.stdout
    assert "Não invente número que a CLI não devolveu" in agentes.stdout
    for comando in (
        "empresa",
        "demonstracoes",
        "fundo",
        "setor",
        "prospectar",
        "comparaveis",
        "eventos",
        "dossie",
        "compradores",
        "ativos",
        "vinculos",
        "novidades",
        "catalogo",
        "consumo",
        "deck",
    ):
        assert f"tickerlab {comando}" in agentes.stdout
        assert f"tickerlab {comando}" in rodar("instrucoes", "skill").stdout
    skill = rodar("instrucoes", "skill").stdout
    assert "--planilha" in agentes.stdout and "--planilha" in skill
    assert skill.startswith("---\nname: tickerlab\ndescription: ")


def test_codigos_de_saida_documentados_batem():
    """Os códigos das instruções do agente são os da `Saida`."""
    texto = (
        configuracao.Path(comandos.__file__).parent / "instrucoes" / "AGENTS.md"
    ).read_text(encoding="utf-8")
    for codigo in Saida:
        assert f"| {int(codigo)} |" in texto


def test_versao_e_ajuda(rodar):
    assert "tickerlab, version 0.1.0" in rodar("--version").stdout
    ajuda = rodar("--help").stdout
    assert "recomendação de investimento" in ajuda
    assert rodar("empresa", "--help").exit_code == 0


def test_o_pacote_so_depende_de_click_e_httpx():
    """O cliente não pode levar o `src/` (nem o resto do repositório) para o PC de quem o instala."""
    import tomllib

    pacote = configuracao.Path(comandos.__file__).parents[1]
    projeto = tomllib.loads((pacote / "pyproject.toml").read_text(encoding="utf-8"))
    assert [d.split(">")[0] for d in projeto["project"]["dependencies"]] == [
        "click",
        "httpx",
    ]
    assert projeto["project"]["scripts"] == {
        "tickerlab": "tickerlab.comandos:principal"
    }
    for arquivo in (pacote / "tickerlab").glob("*.py"):
        codigo = arquivo.read_text(encoding="utf-8")
        for proibido in (
            "from src",
            "import src",
            "from base",
            "import base",
            "streamlit",
        ):
            assert proibido not in codigo, (arquivo.name, proibido)


# ---------------------------------------------------------------- formato


@pytest.mark.parametrize(
    ("valor", "texto"),
    [
        (1234567.891, "1.234.567,89"),
        (1000.0, "1.000"),
        (-5, "-5"),
        (0.12, "0,12"),
        (True, "sim"),
        (False, "não"),
        (None, "—"),
        ("", "—"),
        ({"value": 2.5, "source": "x"}, "2,50"),
        ("a" * 50, "a" * 39 + "…"),
    ],
)
def test_celula(valor, texto):
    assert formato.celula(valor) == texto


def test_ano_sai_sem_milhar():
    assert formato.celula({"value": 2025, "source": "x"}, "year") == "2025"
    assert formato.celula(2025, "value") == "2.025"
    assert formato.celula(2025.5, "year") == "2.025,50"  # só o inteiro é ano


def test_tabela_alinha_as_colunas():
    texto = formato.tabela(("a", "bb"), [("ccc", "d"), ("e", "ffff")])
    assert texto.splitlines() == ["a    bb", "---  ----", "ccc  d", "e    ffff"]


def test_mensagem_de_status_desconhecido():
    resposta = httpx.Response(418, json={"detail": "teapot"})
    erro = cliente.erro_da_resposta(resposta, "https://api.exemplo.com")
    assert erro.exit_code == Saida.ERRO
    validacao = cliente.erro_da_resposta(
        httpx.Response(422, json={"detail": [{"msg": "x"}]}), "https://x"
    )
    assert validacao.exit_code == Saida.PEDIDO_INVALIDO


@pytest.mark.usefixtures("leituras_prontas")
def test_o_consumo_da_cli_e_o_do_banco(rodar, chave, cenario, banco):
    _ator, org, _chave = cenario
    rodar("empresa", "--so-cadastro", EMPRESA, **_com_chave(chave))
    rodar("catalogo", **_com_chave(chave))  # não conta
    with banco.connect() as conexao:
        assert cb.consumo_do_mes(conexao, org.id, AGORA.date()).pedidos == 1


def test_o_cliente_http_de_verdade_nao_leva_a_chave():
    """O cliente que a CLI abre fora dos testes: endereço, tempo máximo e nenhum cabeçalho com a chave."""
    with cliente.abrir_http("https://api.exemplo.com") as http:
        assert str(http.base_url) == "https://api.exemplo.com"
        assert http.timeout.read == cliente.TEMPO_MAXIMO
        assert http.headers["User-Agent"].startswith("tickerlab-cli/")
        assert "Authorization" not in http.headers


# ---------------------------------------------------------------- prospectar (busca de empresas, rota 794)
# Contra um servidor falso que segue a rota da 584 (PR #973); o teste contra a API em memória entra
# quando a rota estiver na main.

DIA_DO_CADASTRO = "2026-10-12"


def _env(valor, fonte: str = "rfb-cnpj") -> dict:
    return {
        "value": valor,
        "source": fonte,
        "published_at": DIA_DO_CADASTRO,
        "observed_at": None,
    }


def _linha_da_busca(cnpj: str, nome: str) -> dict:
    return {
        "cnpj": cnpj,  # a chave da linha sai sem envelope, como na rota
        "legal_name": _env(nome),
        "cnae_code": _env("3511501"),
        "state_code": _env("SP"),
        "size": _env("other"),
    }


FONTE_DA_RECEITA = {
    "source": "rfb-cnpj",
    "attribution": "Receita Federal, CNPJ",
    "license": "dados abertos",
}


def _busca_falsa(paginas: list[list[dict]]):
    """Um servidor da busca que serve `paginas` em sequência pelo cursor, e guarda os pedidos."""
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        assert pedido.url.path == "/data/v1/companies"
        indice = int(pedido.url.params.get("cursor", "0"))
        seguinte = str(indice + 1) if indice + 1 < len(paginas) else None
        return httpx.Response(
            200,
            json={
                "companies": paginas[indice],
                "truncated": False,
                "next_cursor": seguinte,
                "sources": [FONTE_DA_RECEITA],
            },
        )

    return _http_falso(responder), pedidos


PAGINAS_DA_BUSCA = [
    [_linha_da_busca("11111111000191", "ALFA ENERGIA S.A.")],
    [_linha_da_busca("22222222000191", "BETA ENERGIA S.A.")],
    [_linha_da_busca("33333333000191", "GAMA ENERGIA LTDA")],
]


def test_prospectar_traduz_os_filtros_para_a_api(rodar, chave):
    http, pedidos = _busca_falsa(PAGINAS_DA_BUSCA[:1])
    resultado = rodar(
        "prospectar", "--cnae", "35.11-5/01", "--cnae", "3512", "--uf", "sp", "--uf", "RJ",
        "--municipio", "7107", "--municipio", "Campinas", "--porte", "demais", "--porte", "pequena",
        "--natureza", "205-4", "--situacao", "ativa", "--situacao", "suspensa",
        "--aberta-antes", "2016-11-10", "--aberta-depois", "1990-01-01",
        "--so-matriz", "--por-pagina", "100", "--como-era", "2026-11-01",
        http=http, **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    (pedido,) = pedidos
    listas = {
        nome: pedido.url.params.get_list(nome)
        for nome in ("cnae", "state", "municipality", "size", "registration_status")
    }
    assert listas == {
        "cnae": ["3511501", "3512"],
        "state": ["SP", "RJ"],
        "municipality": ["7107", "Campinas"],
        "size": ["other", "small"],
        "registration_status": ["ativa", "suspensa"],
    }
    assert {n: v for n, v in pedido.url.params.items() if n not in listas} == {
        "legal_nature": "2054",
        "opened_before": "2016-11-10",
        "opened_after": "1990-01-01",
        "head_office": "true",
        "limit": "100",
        "known_at": "2026-11-01",
    }
    assert pedido.headers["Authorization"] == f"Bearer {chave}"


def test_prospectar_traduz_os_registros_da_anvisa_para_a_api(rodar, chave):
    """Linha 860: tipo, mínimos e ordem da Anvisa seguem com os nomes da API; a ordem decresce (mais registros
    primeiro)."""
    http, pedidos = _busca_falsa(PAGINAS_DA_BUSCA[:1])
    resultado = rodar(
        "prospectar", "--uf", "SP", "--anvisa-tipo", "produtos_saude", "--anvisa-ativos-min", "200",
        "--anvisa-total-min", "250", "--ordenar-por", "anvisa",
        http=http, **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    (pedido,) = pedidos
    assert {n: v for n, v in pedido.url.params.items()} == {
        "state": "SP",
        "anvisa_type": "health_products",
        "anvisa_active_min": "200",
        "anvisa_total_min": "250",
        "sort": "-anvisa",
    }


def test_prospectar_so_com_o_minimo_da_anvisa_conta_como_filtro(rodar, chave):
    http, pedidos = _busca_falsa(PAGINAS_DA_BUSCA[:1])
    resultado = rodar(
        "prospectar", "--anvisa-ativos-min", "50", http=http, **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    (pedido,) = pedidos
    assert dict(pedido.url.params.items()) == {
        "anvisa_active_min": "50"
    }  # o tipo padrão é da API


def test_prospectar_so_ordenar_nao_conta_como_filtro(rodar, chave):
    """A ordem não filtra: sem outro filtro a CLI recusa antes de gastar um pedido da quota."""
    http, pedidos = _busca_falsa(PAGINAS_DA_BUSCA[:1])
    resultado = rodar(
        "prospectar", "--ordenar-por", "anvisa", http=http, **_com_chave(chave)
    )
    assert resultado.exit_code == Saida.USO
    assert "pelo menos um filtro" in resultado.output
    assert pedidos == []


def test_prospectar_so_o_tipo_da_anvisa_nao_conta_como_filtro(rodar, chave):
    """O tipo só escolhe a contagem: a API também o recusa sozinho, então a CLI recusa antes de gastar a quota."""
    http, pedidos = _busca_falsa(PAGINAS_DA_BUSCA[:1])
    resultado = rodar(
        "prospectar", "--anvisa-tipo", "cosmeticos", http=http, **_com_chave(chave)
    )
    assert resultado.exit_code == Saida.USO
    assert "pelo menos um filtro" in resultado.output
    assert pedidos == []


@pytest.mark.parametrize("opcao", ["--anvisa-ativos-min", "--anvisa-total-min"])
@pytest.mark.parametrize("valor", ["0", "-3", "10000001", "muitos"])
def test_prospectar_recusa_minimo_da_anvisa_fora_da_faixa(rodar, chave, opcao, valor):
    http, pedidos = _busca_falsa(PAGINAS_DA_BUSCA[:1])
    resultado = rodar(
        "prospectar", "--uf", "SP", opcao, valor, http=http, **_com_chave(chave)
    )
    assert resultado.exit_code == Saida.USO
    assert pedidos == []


@pytest.mark.parametrize(
    "tipo", ["medicamentos", "alimentos", "afe", "cbpf", "cosmetics"]
)
def test_prospectar_recusa_tipo_da_anvisa_que_a_api_nao_serve(rodar, chave, tipo):
    """Medicamentos, alimentos, AFE e CBPF esperam a licença de cada ficha; o tipo em inglês não vale na CLI."""
    http, pedidos = _busca_falsa(PAGINAS_DA_BUSCA[:1])
    resultado = rodar(
        "prospectar",
        "--uf",
        "SP",
        "--anvisa-tipo",
        tipo,
        http=http,
        **_com_chave(chave),
    )
    assert resultado.exit_code == Saida.USO
    assert pedidos == []


def test_prospectar_mostra_a_pagina_com_fonte_e_avisa_que_ha_mais(rodar, chave):
    http, pedidos = _busca_falsa(PAGINAS_DA_BUSCA)
    resultado = rodar("prospectar", "--cnae", "35", http=http, **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    assert len(pedidos) == 1
    saida = resultado.stdout
    assert saida.startswith(
        "1 empresas nesta resposta. Há mais: rode de novo com --todas"
    )
    alfa = next(linha for linha in saida.splitlines() if "ALFA ENERGIA" in linha)
    assert "rfb-cnpj" in alfa and DIA_DO_CADASTRO in alfa
    assert "BETA" not in saida and "next_cursor" not in saida
    assert "- rfb-cnpj: Receita Federal, CNPJ" in saida
    assert saida.rstrip().endswith(formato.AVISO)


def test_prospectar_todas_segue_o_cursor_e_junta_as_paginas(rodar, chave):
    http, pedidos = _busca_falsa(PAGINAS_DA_BUSCA)
    resultado = rodar(
        "prospectar", "--uf", "SP", "--todas", "--json", http=http, **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    assert [p.url.params.get("cursor") for p in pedidos] == [None, "1", "2"]
    assert all(
        p.url.params.get("state") == "SP" for p in pedidos
    )  # o filtro vai em toda página
    corpo = json.loads(resultado.stdout)
    assert [e["cnpj"] for e in corpo["companies"]] == [
        "11111111000191", "22222222000191", "33333333000191",
    ]  # fmt: skip
    assert corpo["next_cursor"] is None and corpo["sources"] == [FONTE_DA_RECEITA]
    assert "buscando a página 3" in resultado.stderr


def test_prospectar_todas_para_no_maximo_de_paginas(rodar, chave, monkeypatch):
    monkeypatch.setattr(cliente, "PAGINAS_MAXIMAS", 2)
    http, pedidos = _busca_falsa(PAGINAS_DA_BUSCA)
    resultado = rodar(
        "prospectar", "--uf", "SP", "--todas", http=http, **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    assert len(pedidos) == 2
    assert resultado.stdout.startswith("2 empresas nesta resposta. Há mais")


def test_prospectar_em_planilha_tem_uma_linha_por_empresa(rodar, chave, tmp_path):
    http, _pedidos = _busca_falsa(PAGINAS_DA_BUSCA)
    arquivo = tmp_path / "energia.xlsx"
    resultado = rodar(
        "prospectar", "--cnae", "35", "--todas", "--planilha", str(arquivo),
        http=http, **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    abas = _abrir_xlsx(arquivo)
    empresas = _linhas_com_cabecalho(abas["companies"])
    assert [e["legal_name"] for e in empresas] == [
        "ALFA ENERGIA S.A.", "BETA ENERGIA S.A.", "GAMA ENERGIA LTDA",
    ]  # fmt: skip
    assert {(e["fonte"], e["publicado_em"]) for e in empresas} == {
        ("rfb-cnpj", DIA_DO_CADASTRO)
    }


def test_prospectar_sem_resultado_diz_o_que_fazer(rodar, chave):
    http, _pedidos = _busca_falsa([[]])
    resultado = rodar("prospectar", "--cnae", "35", http=http, **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    assert resultado.stdout.startswith("Nenhuma empresa com estes filtros")


@pytest.mark.parametrize(
    "argumentos",
    [
        (),  # sem filtro: a base inteira não sai
        ("--como-era", "2026-11-01"),  # a data sozinha não é filtro
        ("--situacao", "baixada"),  # a situação sozinha também não
        ("--cnae", "3"),
        ("--cnae", "35115010"),
        ("--uf", "S"),
        ("--municipio", "3550308"),  # o código do IBGE não é o da Receita
        ("--municipio", " "),
        ("--natureza", "20545"),
        ("--porte", "grande"),
        ("--situacao", "ATIVA_X", "--uf", "SP"),
        tuple(arg for _ in range(51) for arg in ("--uf", "SP")),
        ("--uf", "SP", "--por-pagina", "101"),
    ],
)
def test_prospectar_filtro_mal_escrito_nem_chega_a_api(rodar, chave, argumentos):
    resultado = rodar("prospectar", *argumentos, http=None, **_com_chave(chave))
    assert resultado.exit_code == Saida.USO, resultado.output


@pytest.mark.parametrize(
    ("codigo", "saida", "trecho"),
    [
        ("invalid_filter", Saida.PEDIDO_INVALIDO, "recusou um dos filtros"),
        ("filter_required", Saida.USO, "pelo menos um filtro"),
    ],
)
def test_prospectar_recusa_da_api_em_portugues(rodar, chave, codigo, saida, trecho):
    http = _http_falso(lambda _p: httpx.Response(400, json={"detail": codigo}))
    resultado = rodar("prospectar", "--uf", "SP", http=http, **_com_chave(chave))
    assert resultado.exit_code == saida
    assert trecho in resultado.stderr


# ---------------------------------------------------------------- prospectar contra a API em memória (rota 794)


@pytest.fixture
def busca_pronta(banco, cenario, monkeypatch, tmp_path):
    """A base de mentira da busca (as duas tabelas sem pessoa), as tabelas prontas e o contrato."""
    base = tmp_path / "base"
    busca_de_mentira._gravar(
        base, prospeccao.ESTABELECIMENTOS, busca_de_mentira._estabelecimentos()
    )
    busca_de_mentira._gravar(base, prospeccao.EMPRESAS, busca_de_mentira._empresas())
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    monkeypatch.setattr(rotas, "regras_da_api", busca_de_mentira._regras_da_busca)
    ator, org, _chave = cenario
    aj.contrato(banco, ator, org, conjunto=prospeccao.CONJUNTO)


@pytest.mark.usefixtures("busca_pronta")
def test_prospectar_em_json_e_o_envelope_da_rota(rodar, chave, api_em_memoria):
    resultado = rodar(
        "prospectar", "--cnae", "4711302", "--uf", "SP", "--municipio", "7107", "--json",
        **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    direto = api_em_memoria.get(
        "/data/v1/companies",
        params={
            "cnae": "4711302",
            "state": "SP",
            "municipality": "7107",
            "registration_status": "ativa",
        },
        headers=aj.bearer(chave),
    ).json()
    assert json.loads(resultado.stdout) == direto
    assert direto["companies"], "a base de mentira tem empresa nesse filtro"
    assert direto["companies"][0]["legal_name"]["source"] == "rfb-cnpj"


@pytest.mark.usefixtures("busca_pronta")
def test_prospectar_todas_percorre_as_paginas_da_rota(rodar, chave, api_em_memoria):
    resultado = rodar(
        "prospectar", "--uf", "SP", "--uf", "MG", "--situacao", "ativa", "--situacao", "baixada",
        "--por-pagina", "1", "--todas", "--json", **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    juntas = [e["cnpj"] for e in json.loads(resultado.stdout)["companies"]]
    de_uma_vez = api_em_memoria.get(
        "/data/v1/companies",
        params={
            "state": ["SP", "MG"],
            "registration_status": ["ativa", "baixada"],
            "limit": "100",
        },
        headers=aj.bearer(chave),
    ).json()
    assert juntas == [e["cnpj"] for e in de_uma_vez["companies"]]
    assert len(juntas) > 1 and len(set(juntas)) == len(juntas)


@pytest.mark.usefixtures("busca_pronta")
def test_prospectar_em_tabela_tem_fonte_e_aviso(rodar, chave):
    resultado = rodar("prospectar", "--cnae", "62", **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    assert "empresas nesta resposta" in resultado.stdout
    assert "rfb-cnpj" in resultado.stdout
    assert resultado.stdout.rstrip().endswith(formato.AVISO)


def test_prospectar_sem_o_conjunto_no_contrato_e_sem_dado(
    rodar, chave, tmp_path, monkeypatch
):
    base = tmp_path / "base"
    busca_de_mentira._gravar(
        base, prospeccao.ESTABELECIMENTOS, busca_de_mentira._estabelecimentos()
    )
    busca_de_mentira._gravar(base, prospeccao.EMPRESAS, busca_de_mentira._empresas())
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    monkeypatch.setattr(rotas, "regras_da_api", busca_de_mentira._regras_da_busca)
    resultado = rodar("prospectar", "--cnae", "62", **_com_chave(chave))
    assert resultado.exit_code == Saida.SEM_DADO, resultado.output


# ---------------------------------------------------------------- comparaveis (rota da linha 736, PR 3)

DIA_DOS_PARES = comparaveis_de_mentira.DIA.isoformat()


@pytest.fixture
def comparaveis_prontos(banco, cenario, monkeypatch, tmp_path):
    """A base de mentira dos comparáveis, as tabelas prontas e o contrato de `comparables`."""
    base = comparaveis_de_mentira.gravar_base(tmp_path / "base")
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    monkeypatch.setattr(rotas, "regras_da_api", rota_dos_comparaveis._regras)
    ator, org, _chave = cenario
    aj.contrato(banco, ator, org, conjunto=comparaveis.CONJUNTO)


@pytest.mark.usefixtures("comparaveis_prontos")
def test_comparaveis_em_tabela_tem_a_empresa_os_pares_e_as_medianas(rodar, chave):
    resultado = rodar(
        "comparaveis", comparaveis_de_mentira.ALFA, "--como-era", DIA_DOS_PARES,
        **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    saida = resultado.stdout
    empresa_ = saida.split("## subject_company", 1)[1].split("## ", 1)[0]
    receita = next(linha for linha in empresa_.splitlines() if "revenue" in linha)
    assert "cvm-hist-dfp" in receita and "2025-03-20" in receita
    assert "## peers" in saida and "## peer_medians" in saida and "## limits" in saida
    assert "- cvm-hist-dfp:" in saida and "- cvm-hist-fca:" in saida
    assert saida.rstrip().endswith(formato.AVISO)


@pytest.mark.usefixtures("comparaveis_prontos")
def test_comparaveis_em_json_e_o_envelope_da_rota(rodar, chave, api_em_memoria):
    alfa = comparaveis_de_mentira.ALFA
    resultado = rodar(
        "comparaveis", alfa, "--como-era", DIA_DOS_PARES, "--json", **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    direto = api_em_memoria.get(
        f"/data/v1/companies/{alfa}/comparables",
        params={"known_at": DIA_DOS_PARES},
        headers=aj.bearer(chave),
    ).json()
    assert json.loads(resultado.stdout) == direto
    assert len(direto["peers"]) == len(comparaveis_de_mentira.PARES)


@pytest.mark.usefixtures("comparaveis_prontos")
def test_comparaveis_sem_como_era_sao_os_de_hoje(rodar, chave):
    """Hoje a ALFA informou outro setor no FCA: os pares de energia não são mais dela."""
    resultado = rodar(
        "comparaveis", comparaveis_de_mentira.ALFA, "--json", **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    corpo = json.loads(resultado.stdout)
    assert corpo["sector_group"]["value"] == "trade" and corpo["peers"] == []


@pytest.mark.usefixtures("comparaveis_prontos")
def test_comparaveis_em_planilha_tem_uma_linha_por_par(rodar, chave, tmp_path):
    arquivo = tmp_path / "pares.xlsx"
    resultado = rodar(
        "comparaveis", comparaveis_de_mentira.ALFA, "--como-era", DIA_DOS_PARES,
        "--planilha", str(arquivo), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    abas = _abrir_xlsx(arquivo)
    assert {"peers", "fontes"} <= set(abas)
    pares = _linhas_com_cabecalho(abas["peers"])
    assert len(pares) == len(comparaveis_de_mentira.PARES)
    # o nome vem do FCA e os números do DFP: a linha do par cita as duas fontes
    assert all(
        set(p["fonte"].split(", ")) == {"cvm-hist-fca", "cvm-hist-dfp"} for p in pares
    )
    assert all(isinstance(p["revenue"], float) for p in pares)


def test_comparaveis_fora_do_contrato_e_sem_dado(rodar, chave, tmp_path, monkeypatch):
    base = comparaveis_de_mentira.gravar_base(tmp_path / "base")
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    monkeypatch.setattr(rotas, "regras_da_api", rota_dos_comparaveis._regras)
    resultado = rodar("comparaveis", comparaveis_de_mentira.ALFA, **_com_chave(chave))
    assert resultado.exit_code == Saida.SEM_DADO, resultado.output


# ---------------------------------------------------------------- eventos (rota da linha 736, PR 4)

DIA_DOS_EVENTOS = eventos_de_mentira.DIA.isoformat()


@pytest.fixture
def eventos_prontos(banco, cenario, monkeypatch, tmp_path):
    """A base de mentira dos eventos, as tabelas prontas e o contrato de `events`."""
    base = eventos_de_mentira.gravar_base(tmp_path / "base")
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    monkeypatch.setattr(rotas, "regras_da_api", rota_dos_eventos._regras)
    ator, org, _chave = cenario
    aj.contrato(banco, ator, org, conjunto=eventos.CONJUNTO)


@pytest.mark.usefixtures("eventos_prontos")
def test_eventos_em_tabela_tem_cada_evento_com_fonte_e_data(rodar, chave):
    resultado = rodar(
        "eventos", eventos_de_mentira.ALFA, "--como-era", DIA_DOS_EVENTOS,
        **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    saida = resultado.stdout
    assert saida.startswith(
        f"{rota_dos_eventos.EVENTOS_NO_DIA} eventos nesta resposta."
    )
    assert "Há mais" not in saida
    troca = next(linha for linha in saida.splitlines() if "AUDITORA DOIS" in linha)
    assert "cvm-hist-fca" in troca and "2025-05-31" in troca
    documento = next(linha for linha in saida.splitlines() if "Fato Relevante" in linha)
    assert "cvm-hist-ipe" in documento
    assert "## limits" in saida and "- cvm-hist-ipe:" in saida
    assert saida.rstrip().endswith(formato.AVISO)


@pytest.mark.usefixtures("eventos_prontos")
def test_eventos_em_json_e_o_envelope_da_rota(rodar, chave, api_em_memoria):
    alfa = eventos_de_mentira.ALFA
    resultado = rodar(
        "eventos", alfa, "--como-era", DIA_DOS_EVENTOS, "--json", **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    direto = api_em_memoria.get(
        f"/data/v1/companies/{alfa}/events",
        params={"known_at": DIA_DOS_EVENTOS},
        headers=aj.bearer(chave),
    ).json()
    assert json.loads(resultado.stdout) == direto
    assert len(direto["events"]) == rota_dos_eventos.EVENTOS_NO_DIA


@pytest.mark.usefixtures("eventos_prontos")
def test_eventos_tipo_auditor_traz_so_a_troca(rodar, chave):
    resultado = rodar(
        "eventos", eventos_de_mentira.ALFA, "--como-era", DIA_DOS_EVENTOS,
        "--tipo", "auditor", "--json", **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    corpo = json.loads(resultado.stdout)
    assert [e["event_type"] for e in corpo["events"]] == ["auditor_change"]
    assert {f["source"] for f in corpo["sources"]} == {"cvm-hist-fca"}


@pytest.mark.usefixtures("eventos_prontos")
def test_eventos_sem_como_era_trazem_o_que_veio_depois(rodar, chave):
    resultado = rodar("eventos", eventos_de_mentira.ALFA, "--json", **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    corpo = json.loads(resultado.stdout)
    assert "P4" in {
        e["filing_id"]["value"] for e in corpo["events"] if "filing_id" in e
    }


@pytest.mark.usefixtures("eventos_prontos")
def test_eventos_pagina_avisa_que_ha_mais_e_todas_junta_tudo(rodar, chave, monkeypatch):
    monkeypatch.setattr(acesso, "linhas_por_resposta", lambda _contexto: 3)
    argumentos = ("eventos", eventos_de_mentira.ALFA, "--como-era", DIA_DOS_EVENTOS)
    uma = rodar(*argumentos, **_com_chave(chave))
    assert uma.exit_code == 0, uma.output
    assert uma.stdout.startswith(
        "3 eventos nesta resposta. Há mais: rode de novo com --todas"
    )
    todas = rodar(*argumentos, "--todas", "--json", **_com_chave(chave))
    assert todas.exit_code == 0, todas.output
    corpo = json.loads(todas.stdout)
    assert len(corpo["events"]) == rota_dos_eventos.EVENTOS_NO_DIA
    assert corpo["next_cursor"] is None and corpo["truncated"] is False
    assert {f["source"] for f in corpo["sources"]} == {"cvm-hist-ipe", "cvm-hist-fca"}
    assert "buscando a página 2" in todas.stderr


@pytest.mark.usefixtures("eventos_prontos")
def test_eventos_em_planilha_tem_uma_linha_por_evento(rodar, chave, tmp_path):
    arquivo = tmp_path / "eventos.xlsx"
    resultado = rodar(
        "eventos", eventos_de_mentira.ALFA, "--como-era", DIA_DOS_EVENTOS,
        "--planilha", str(arquivo), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    abas = _abrir_xlsx(arquivo)
    assert {"events", "fontes"} <= set(abas)
    linhas = _linhas_com_cabecalho(abas["events"])
    assert len(linhas) == rota_dos_eventos.EVENTOS_NO_DIA
    assert {linha["fonte"] for linha in linhas} == {"cvm-hist-ipe", "cvm-hist-fca"}


def test_eventos_fora_do_contrato_e_sem_dado(rodar, chave, tmp_path, monkeypatch):
    base = eventos_de_mentira.gravar_base(tmp_path / "base")
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    monkeypatch.setattr(rotas, "regras_da_api", rota_dos_eventos._regras)
    resultado = rodar("eventos", eventos_de_mentira.ALFA, **_com_chave(chave))
    assert resultado.exit_code == Saida.SEM_DADO, resultado.output


def test_eventos_tipo_desconhecido_nem_chega_a_api(rodar, chave):
    resultado = rodar(
        "eventos",
        eventos_de_mentira.ALFA,
        "--tipo",
        "fusao",
        http=None,
        **_com_chave(chave),
    )
    assert resultado.exit_code == Saida.USO, resultado.output


@pytest.mark.parametrize(
    ("codigo", "trecho"),
    [("invalid_event_type", "Tipo de evento"), ("invalid_cursor", "página pedida")],
)
def test_eventos_recusa_da_api_em_portugues(rodar, chave, codigo, trecho):
    http = _http_falso(lambda _p: httpx.Response(400, json={"detail": codigo}))
    resultado = rodar(
        "eventos", eventos_de_mentira.ALFA, http=http, **_com_chave(chave)
    )
    assert resultado.exit_code == Saida.PEDIDO_INVALIDO
    assert trecho in resultado.stderr


CORPO_DE_COMPRADORES = {
    "buyers": [
        {
            "entity_id": "pj:99999999",
            "legal_name": {
                "value": "COMPRADORA EXEMPLO S.A.",
                "source": "rfb-cnpj",
                "published_at": "2026-10-01",
                "observed_at": "2026-10-02",
            },
            "signals": {
                "value": ["entrou_como_socio"],
                "source": "rfb-cnpj",
                "published_at": "2026-10-01",
                "observed_at": "2026-10-02",
            },
        }
    ],
    "limits": [
        {"source": "rfb-cnpj", "text": "Movimento passado não é intenção de compra."}
    ],
}


def _pedir_compradores(rodar, chave, *argumentos):
    vistos: list[httpx.Request] = []

    def guardar(pedido: httpx.Request) -> httpx.Response:
        vistos.append(pedido)
        return httpx.Response(200, json=CORPO_DE_COMPRADORES)

    resultado = rodar(
        "compradores", *argumentos, http=_http_falso(guardar), **_com_chave(chave)
    )
    return resultado, vistos


def test_compradores_pede_a_rota_com_os_filtros(rodar, chave):
    resultado, vistos = _pedir_compradores(
        rodar, chave, "--cnae", "3511-5/01", "--uf", "sp", "--anos", "5",
        "--limite", "10", "--como-era", "2026-03-31",
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    (pedido,) = vistos
    assert pedido.url.path == "/data/v1/buyers"
    assert dict(pedido.url.params) == {
        "cnae": "3511501",
        "state": "SP",
        "years": "5",
        "limit": "10",
        "known_at": "2026-03-31",
    }
    assert "COMPRADORA EXEMPLO S.A." in resultado.stdout
    assert "## limits" in resultado.stdout
    assert resultado.stdout.rstrip().endswith(formato.AVISO)


def test_compradores_padrao_de_anos_e_limite(rodar, chave):
    resultado, vistos = _pedir_compradores(rodar, chave, "--cnae", "35115")
    assert resultado.exit_code == 0, resultado.output
    parametros = dict(vistos[0].url.params)
    assert parametros["years"] == "3" and parametros["limit"] == "20"
    assert "state" not in parametros


def test_compradores_em_json_e_o_envelope_da_rota(rodar, chave):
    resultado, _ = _pedir_compradores(rodar, chave, "--cnae", "35115", "--json")
    assert resultado.exit_code == 0, resultado.output
    assert json.loads(resultado.stdout) == CORPO_DE_COMPRADORES


# ---------------------------------------------------------------- vinculos (rota da linha 736, PR 5)

DIA_DOS_VINCULOS = vinculos_de_mentira.DIA.isoformat()


@pytest.fixture
def vinculos_prontos(banco, cenario, monkeypatch, tmp_path):
    """A base de mentira dos vínculos, as tabelas prontas e o contrato de `links`."""
    base = vinculos_de_mentira.gravar_base(tmp_path / "base")
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    monkeypatch.setattr(rotas, "regras_da_api", rota_dos_vinculos._regras)
    ator, org, _chave = cenario
    aj.contrato(banco, ator, org, conjunto=vinculos.CONJUNTO)


@pytest.mark.usefixtures("vinculos_prontos")
def test_vinculos_em_tabela_tem_as_pontas_com_nome_fonte_e_data(rodar, chave):
    resultado = rodar(
        "vinculos", vinculos_de_mentira.ALFA, "--como-era", DIA_DOS_VINCULOS,
        **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    saida = resultado.stdout
    mae = next(
        linha for linha in saida.splitlines() if "60" in linha and "ALFA LTDA" in linha
    )
    assert "(11111111)" in mae and "cvm-hist-fre" in mae and "2019-05-31" in mae
    assert "{" not in saida  # as pontas não saem como dicionário
    assert "## limits" in saida and "- rfb-cnpj:" in saida
    assert saida.rstrip().endswith(formato.AVISO)


@pytest.mark.usefixtures("vinculos_prontos")
def test_vinculos_em_json_e_o_envelope_da_rota(rodar, chave, api_em_memoria):
    alfa = vinculos_de_mentira.ALFA
    resultado = rodar(
        "vinculos", alfa, "--como-era", DIA_DOS_VINCULOS, "--json", **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    direto = api_em_memoria.get(
        f"/data/v1/companies/{alfa}/links",
        params={"known_at": DIA_DOS_VINCULOS, "depth": "1"},
        headers=aj.bearer(chave),
    ).json()
    assert json.loads(resultado.stdout) == direto
    assert len(direto["links"]) == rota_dos_vinculos.VINCULOS_NO_DIA


@pytest.mark.usefixtures("vinculos_prontos")
def test_vinculos_profundidade_e_tipo_vao_para_a_api(rodar, chave):
    resultado = rodar(
        "vinculos", vinculos_de_mentira.ALFA, "--como-era", DIA_DOS_VINCULOS,
        "--profundidade", "3", "--tipo", "controlada", "--json", **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    corpo = json.loads(resultado.stdout)
    assert corpo["depth"] == 3
    assert {v["kind"]["value"] for v in corpo["links"]} == {"subsidiary_of"}
    assert max(v["hops"] for v in corpo["links"]) == 3


@pytest.mark.usefixtures("vinculos_prontos")
def test_vinculos_em_planilha_tem_uma_linha_por_vinculo(rodar, chave, tmp_path):
    arquivo = tmp_path / "vinculos.xlsx"
    resultado = rodar(
        "vinculos", vinculos_de_mentira.ALFA, "--como-era", DIA_DOS_VINCULOS,
        "--planilha", str(arquivo), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    abas = _abrir_xlsx(arquivo)
    assert {"links", "fontes"} <= set(abas)
    linhas = _linhas_com_cabecalho(abas["links"])
    assert len(linhas) == rota_dos_vinculos.VINCULOS_NO_DIA
    assert all(linha["de"] and linha["para"] and linha["fonte"] for linha in linhas)


def test_vinculos_fora_do_contrato_e_sem_dado(rodar, chave, tmp_path, monkeypatch):
    base = vinculos_de_mentira.gravar_base(tmp_path / "base")
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    monkeypatch.setattr(rotas, "regras_da_api", rota_dos_vinculos._regras)
    resultado = rodar("vinculos", vinculos_de_mentira.ALFA, **_com_chave(chave))
    assert resultado.exit_code == Saida.SEM_DADO, resultado.output


@pytest.mark.parametrize(
    "argumentos",
    [
        ("--cnae", "351"),
        ("--cnae", "35115", "--uf", "SAO"),
        ("--cnae", "35115", "--anos", "11"),
        ("--cnae", "35115", "--limite", "51"),
        (),
    ],
)
def test_compradores_pedido_ruim_nem_chega_a_api(rodar, chave, argumentos):
    resultado, vistos = _pedir_compradores(rodar, chave, *argumentos)
    assert resultado.exit_code == Saida.USO
    assert vistos == []


def test_compradores_recusa_da_api_vira_mensagem_clara(rodar, chave):
    def recusa(_p: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "invalid_cnae"})

    resultado = rodar(
        "compradores", "--cnae", "35115", http=_http_falso(recusa), **_com_chave(chave)
    )
    assert resultado.exit_code == Saida.PEDIDO_INVALIDO
    assert "5 ou 7 dígitos" in resultado.stderr


@pytest.mark.parametrize(
    "argumentos",
    [("--profundidade", "4"), ("--profundidade", "0"), ("--tipo", "fusao")],
)
def test_vinculos_pedido_mal_escrito_nem_chega_a_api(rodar, chave, argumentos):
    resultado = rodar(
        "vinculos",
        vinculos_de_mentira.ALFA,
        *argumentos,
        http=None,
        **_com_chave(chave),
    )
    assert resultado.exit_code == Saida.USO, resultado.output


@pytest.mark.parametrize(
    ("codigo", "saida", "trecho"),
    [
        ("invalid_depth", Saida.USO, "1 a 3 saltos"),
        ("invalid_link_type", Saida.PEDIDO_INVALIDO, "Tipo de vínculo"),
    ],
)
def test_vinculos_recusa_da_api_em_portugues(rodar, chave, codigo, saida, trecho):
    http = _http_falso(lambda _p: httpx.Response(400, json={"detail": codigo}))
    resultado = rodar(
        "vinculos", vinculos_de_mentira.ALFA, http=http, **_com_chave(chave)
    )
    assert resultado.exit_code == saida
    assert trecho in resultado.stderr


# ---------------------------------------------------------------- novidades (fontes provadas pela pesquisa, linha 830)

CORPO_DE_NOVIDADES = {
    "generated_at": "2026-11-11T12:00:00+00:00",
    "days": 7,
    "total_news": 1,
    "items": [
        {
            "agency": "CVM",
            "source": "cvm",
            "source_url": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/exemplo.csv",
            "date": "2026-11-10",
            "excerpt": "Parque Exemplo Eólico: 120 MW, vigência 2035",
            "original_sha256": "a" * 64,
            "position": "linha 3",
        }
    ],
}


def _pedir_novidades(rodar, chave, corpo, *argumentos):
    vistos: list[httpx.Request] = []

    def guardar(pedido: httpx.Request) -> httpx.Response:
        vistos.append(pedido)
        return httpx.Response(200, json=corpo)

    resultado = rodar(
        "novidades", *argumentos, http=_http_falso(guardar), **_com_chave(chave)
    )
    return resultado, vistos


def test_novidades_pede_a_rota_e_mostra_orgao_trecho_e_hash(rodar, chave):
    resultado, vistos = _pedir_novidades(
        rodar, chave, CORPO_DE_NOVIDADES, "--dias", "14"
    )
    assert resultado.exit_code == 0
    assert vistos[0].url.path.endswith("/research/news")
    assert vistos[0].url.params["days"] == "14"
    assert "CVM · 2026-11-10" in resultado.stdout
    assert "Parque Exemplo Eólico: 120 MW" in resultado.stdout
    assert "a" * 64 in resultado.stdout


def test_novidades_marca_o_recorte_fora_das_aspas(rodar, chave):
    item = CORPO_DE_NOVIDADES["items"][0] | {"excerpt_cut": "ambos"}
    corpo = CORPO_DE_NOVIDADES | {"items": [item]}
    resultado, _ = _pedir_novidades(rodar, chave, corpo)
    assert "vigência 2035”  [recorte: o original continua antes e depois]" in (
        resultado.stdout
    )


def test_novidades_sem_nada_diz_que_nao_ha(rodar, chave):
    vazio = {"generated_at": None, "days": 7, "total_news": 0, "items": []}
    resultado, _ = _pedir_novidades(rodar, chave, vazio)
    assert resultado.exit_code == 0
    assert "Nenhuma fonte nova provada na semana" in resultado.stdout


def test_novidades_dias_fora_da_faixa_nem_chega_a_api(rodar, chave):
    resultado = rodar("novidades", "--dias", "31", http=None, **_com_chave(chave))
    assert resultado.exit_code != 0


def _env(valor):
    return {
        "value": valor,
        "source": "rfb-cnpj",
        "published_at": "2026-10-01",
        "observed_at": "2026-10-02",
    }


def _secoes_do_dossie(faltando: dict[str, int] | None = None):
    faltando = faltando or {}
    corpos = {
        "/profile": {
            "cnpj": {"razao": _env("EMPRESA EXEMPLO S.A.")},
            "sources": [{"source": "rfb-cnpj"}],
        },
        "/events": {
            "events": [],
            "sources": [{"source": "rfb-cnpj"}, {"source": "cvm"}],
        },
        "/links": {
            "links": [],
            "limits": [{"source": "x", "text": "limite dos vínculos"}],
        },
        "/comparables": {"comparables": [], "sources": [{"source": "cvm"}]},
    }
    vistos: list[str] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        sufixo = "/" + pedido.url.path.rsplit("/", 1)[1]
        vistos.append(sufixo)
        if sufixo in faltando:
            codigo = {403: "dataset_not_in_contract", 404: "not_available"}[
                faltando[sufixo]
            ]
            return httpx.Response(faltando[sufixo], json={"detail": codigo})
        return httpx.Response(200, json=dict(corpos[sufixo]))

    return responder, vistos


def test_dossie_junta_as_quatro_secoes_sem_repetir_fonte(rodar, chave):
    responder, vistos = _secoes_do_dossie()
    resultado = rodar(
        "dossie",
        "11111111000191",
        "--json",
        http=_http_falso(responder),
        **_com_chave(chave),
    )
    assert resultado.exit_code == 0, resultado.output
    assert vistos == ["/profile", "/events", "/links", "/comparables"]
    corpo = json.loads(resultado.stdout)
    assert corpo["requests_used"] == 4 and corpo["gaps"] == []
    assert [f["source"] for f in corpo["sources"]] == ["rfb-cnpj", "cvm"]
    assert corpo["limits"] == [{"source": "x", "text": "limite dos vínculos"}]
    assert "sources" not in corpo["events"]


def test_dossie_secao_sem_dado_vira_lacuna_dita(rodar, chave):
    responder, _ = _secoes_do_dossie({"/links": 404})
    resultado = rodar(
        "dossie", "11111111000191", http=_http_falso(responder), **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    assert "Ficou de fora: links" in resultado.stdout
    assert "## comparables" in resultado.stdout


def test_dossie_sem_perfil_e_erro(rodar, chave):
    responder, _ = _secoes_do_dossie({"/profile": 404})
    resultado = rodar(
        "dossie", "11111111000191", http=_http_falso(responder), **_com_chave(chave)
    )
    assert resultado.exit_code == Saida.SEM_DADO


def test_dossie_em_planilha_tem_aba_das_fontes(rodar, chave, tmp_path):
    responder, _ = _secoes_do_dossie()
    arquivo = tmp_path / "dossie.xlsx"
    resultado = rodar(
        "dossie", "11111111000191", "--planilha", str(arquivo),
        http=_http_falso(responder), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    abas = _abrir_xlsx(arquivo)
    assert any("fonte" in aba.lower() for aba in abas)


def test_dossie_exportado_so_chama_rotas_de_pj_e_nao_leva_cpf(rodar, chave, tmp_path):
    responder, vistos = _secoes_do_dossie({"/links": 404})
    arquivo = tmp_path / "dossie.xlsx"
    resultado = rodar(
        "dossie", "11111111000191", "--planilha", str(arquivo),
        http=_http_falso(responder), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    assert vistos == ["/profile", "/events", "/links", "/comparables"]
    celulas = " ".join(
        str(c) for linhas in _abrir_xlsx(arquivo).values() for l in linhas for c in l
    )
    assert not re.search(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", celulas)
    assert "não achado:" in celulas


def test_eventos_pede_50_por_pagina_e_com_todas_deixa_o_plano_decidir(monkeypatch):
    """Sem --todas a CLI pede a primeira página de 50 (uma companhia grande passa de mil eventos)."""
    pedidos: list[dict] = []

    def pedir(self, caminho, parametros=None):
        pedidos.append(dict(parametros or {}))
        return {"events": [], "next_cursor": None}

    monkeypatch.setattr(cliente.ApiDoTickerlab, "pedir", pedir)
    api_de_mentira = cliente.ApiDoTickerlab(httpx.Client(), "chave", "http://x")
    api_de_mentira.eventos("33000167000101", None, [], False)
    api_de_mentira.eventos("33000167000101", None, [], True)
    assert pedidos[0]["limit"] == "50"
    assert "limit" not in pedidos[1]


# ------------------------------------------------ aviso de piloto (865, D11)
# A frase vem da API (base/prontidao.AVISO_DE_PILOTO); a CLI só mostra a que veio. Estes testes usam uma
# frase qualquer: o que se confere é que a que chegou aparece na saída, não o texto fixo.

FRASE_DE_PILOTO = (
    "FRASE-QUALQUER-DO-PILOTO: dado de piloto, ainda sem a conferência cheia."
)
CNPJ_PILOTO = "11111111000191"


def _piloto(valor: object, fonte: str = "fonte-x") -> dict:
    return {
        "value": valor,
        "source": fonte,
        "published_at": "2026-01-02",
        "pilot": True,
        "pilot_notice": FRASE_DE_PILOTO,
    }


def _resposta_fixa(corpo: dict):
    return _http_falso(lambda _p: httpx.Response(200, json=corpo))


def _perfil_de_piloto() -> dict:
    return {
        "pilot_notice": FRASE_DE_PILOTO,
        "cnpj": {"razao": _piloto("EMPRESA EXEMPLO S.A."), "porte": _env("grande")},
        "sources": [{"source": "fonte-x"}],
    }


def test_piloto_na_tela_mostra_a_frase_e_marca_o_campo(rodar, chave):
    resultado = rodar(
        "empresa", CNPJ_PILOTO, http=_resposta_fixa(_perfil_de_piloto()),
        **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    assert FRASE_DE_PILOTO in resultado.stdout  # inteira, sem truncar
    assert (
        "piloto" in resultado.stdout.splitlines()[0]
        or "Aviso de piloto" in resultado.stdout
    )
    assert any(
        linha.startswith("razao") and linha.rstrip().endswith("sim")
        for linha in resultado.stdout.splitlines()
    )


def test_piloto_em_linhas_de_lista_marca_a_linha_e_traz_a_frase(rodar, chave):
    corpo = {
        "pilot_notice": FRASE_DE_PILOTO,
        "events": [
            {"kind": _piloto("capital"), "year": _env(2025)},
            {"kind": _env("x")},
        ],
        "sources": [],
    }
    resultado = rodar(
        "eventos", CNPJ_PILOTO, http=_resposta_fixa(corpo), **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    assert resultado.stdout.count(FRASE_DE_PILOTO) >= 1
    assert "piloto" in resultado.stdout


def test_piloto_no_json_passa_inteiro(rodar, chave):
    corpo = _perfil_de_piloto()
    resultado = rodar(
        "empresa",
        CNPJ_PILOTO,
        "--json",
        http=_resposta_fixa(corpo),
        **_com_chave(chave),
    )
    saida = json.loads(resultado.stdout)
    assert saida["pilot_notice"] == FRASE_DE_PILOTO
    assert saida["cnpj"]["razao"]["pilot"] is True
    assert saida["cnpj"]["razao"]["pilot_notice"] == FRASE_DE_PILOTO


def test_piloto_na_planilha_xlsx_leva_a_marca_e_a_frase(rodar, chave, tmp_path):
    arquivo = tmp_path / "piloto.xlsx"
    resultado = rodar(
        "empresa", CNPJ_PILOTO, "--planilha", str(arquivo),
        http=_resposta_fixa(_perfil_de_piloto()), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    assert FRASE_DE_PILOTO in resultado.stdout  # a confirmação também avisa
    abas = _abrir_xlsx(arquivo)
    texto = json.dumps(abas, ensure_ascii=False)
    assert FRASE_DE_PILOTO in texto
    assert "piloto" in texto


def test_piloto_na_planilha_csv_leva_a_marca_e_a_frase(rodar, chave, tmp_path):
    arquivo = tmp_path / "piloto.csv"
    resultado = rodar(
        "empresa", CNPJ_PILOTO, "--planilha", str(arquivo),
        http=_resposta_fixa(_perfil_de_piloto()), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    texto = arquivo.read_text(encoding="utf-8-sig")
    assert FRASE_DE_PILOTO in texto
    assert texto.splitlines()[0].split(";")[-1] == "piloto"


def test_piloto_marcado_sem_frase_nunca_passa_calado(rodar, chave):
    corpo = {"cnpj": {"razao": {**_env("X"), "pilot": True}}, "sources": []}
    resultado = rodar(
        "empresa", CNPJ_PILOTO, http=_resposta_fixa(corpo), **_com_chave(chave)
    )
    assert "Aviso de piloto" in resultado.stdout


def test_sem_piloto_a_saida_nao_ganha_nada(rodar, chave):
    corpo = {"cnpj": {"razao": _env("X")}, "sources": [{"source": "fonte-x"}]}
    resultado = rodar(
        "empresa", CNPJ_PILOTO, http=_resposta_fixa(corpo), **_com_chave(chave)
    )
    assert "piloto" not in resultado.stdout.lower()


def test_piloto_no_dossie_aparece_na_tela(rodar, chave):
    responder, _ = _secoes_do_dossie()

    def com_piloto(pedido: httpx.Request) -> httpx.Response:
        resposta = responder(pedido)
        corpo = json.loads(resposta.content)
        if pedido.url.path.endswith("/comparables"):
            corpo["pilot_notice"] = FRASE_DE_PILOTO
            corpo["comparables"] = [{"cnpj": _piloto("22222222000191")}]
        return httpx.Response(200, json=corpo)

    resultado = rodar(
        "dossie", CNPJ_PILOTO, http=_http_falso(com_piloto), **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    assert FRASE_DE_PILOTO in resultado.stdout


def test_piloto_no_catalogo_aparece_na_tela(rodar, chave):
    corpo = {
        "pilot_notice": FRASE_DE_PILOTO,
        "datasets": [
            {
                "dataset": "d",
                "purpose": "p",
                "fields": [{"field": "f", "source": "s", "pilot": True}],
            }
        ],
        "sources": [],
    }
    resultado = rodar("catalogo", http=_resposta_fixa(corpo), **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    assert FRASE_DE_PILOTO in resultado.stdout


def test_piloto_no_csv_da_lista_a_frase_vai_na_propria_coluna(rodar, chave, tmp_path):
    corpo = {
        "events": [{"kind": _piloto("capital")}, {"kind": _env("x")}],
        "sources": [],
    }
    arquivo = tmp_path / "ev.csv"
    resultado = rodar(
        "eventos", CNPJ_PILOTO, "--planilha", str(arquivo),
        http=_resposta_fixa(corpo), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    linhas = arquivo.read_text(encoding="utf-8-sig").splitlines()
    assert linhas[0].split(";")[-1] == "piloto"
    assert linhas[1].split(";")[-1] == FRASE_DE_PILOTO  # a linha marcada leva a frase
    assert linhas[2].split(";")[-1] == ""  # a que não é de piloto, não


def test_piloto_dentro_da_serie_do_setor_marca_a_linha_certa():
    corpo = {
        "market": {"hhi": _env(1)},
        "series": [{"name": "aneel", "points": [], "total": _piloto(5)}],
        "sources": [],
    }
    campos = planilha.tabelas_da_resposta(corpo)[0]
    assert campos.cabecalho[-1] == "piloto"
    por_nome = {linha[0]: linha[-1] for linha in campos.linhas}
    assert por_nome["series › aneel › total"] == FRASE_DE_PILOTO
    assert por_nome["market › hhi"] is None


def test_piloto_no_nome_da_ponta_do_vinculo_marca_a_linha(rodar, chave):
    ponta = {"cnpj_root": "11111111", "legal_name": _piloto("EMPRESA A")}
    outra = {"cnpj_root": "22222222", "legal_name": _env("EMPRESA B")}
    corpo = {
        "links": [
            {"hops": 1, "kind": "socio", "from": ponta, "to": outra, "share": _env(10)},
            {"hops": 1, "kind": "socio", "from": outra, "to": outra, "share": _env(20)},
        ],
        "sources": [],
    }
    resultado = rodar(
        "vinculos", CNPJ_PILOTO, http=_resposta_fixa(corpo), **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    linhas = [l for l in resultado.stdout.splitlines() if l.startswith("1")]
    assert linhas[0].rstrip().endswith("sim")
    assert not linhas[1].rstrip().endswith("sim")
    assert FRASE_DE_PILOTO in resultado.stdout


def test_piloto_de_uma_pagina_sobrevive_ao_juntar_paginas():
    primeira = {"companies": [1], "pilot_notice": FRASE_DE_PILOTO, "sources": []}
    ultima = {"companies": [2], "sources": []}
    assert cliente.juntar_paginas(primeira, ultima)["pilot_notice"] == FRASE_DE_PILOTO


# ---------------------------------------------------------------- deck


def _pptx_falso() -> bytes:
    return b"PK\x03\x04" + b"conteudo-do-deck"


def _deck_que_responde(vistos: list, nome: str | None = None, status: int = 200):
    def responder(pedido: httpx.Request) -> httpx.Response:
        vistos.append(pedido)
        if status != 200:
            return httpx.Response(status, json={"detail": "not_available"})
        cabecalhos = (
            {"Content-Disposition": f'attachment; filename="{nome}"'} if nome else {}
        )
        return httpx.Response(200, content=_pptx_falso(), headers=cabecalhos)

    return _http_falso(responder)


def test_deck_da_empresa_grava_com_o_nome_da_api(rodar, chave, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vistos: list = []
    http = _deck_que_responde(vistos, "tickerlab-empresa-11111111000191.pptx")
    resultado = rodar("deck", "11111111000191", http=http, **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    assert vistos[0].url.path == "/data/v1/companies/11111111000191/deck"
    assert (
        tmp_path / "tickerlab-empresa-11111111000191.pptx"
    ).read_bytes() == _pptx_falso()
    assert "Deck gravado" in resultado.stdout


def test_deck_do_setor_com_saida_e_como_era(rodar, chave, tmp_path):
    vistos: list = []
    alvo = tmp_path / "setor.pptx"
    resultado = rodar(
        "deck", "--setor", "eletricas", "--como-era", "2026-03-31", "--saida", str(alvo),
        http=_deck_que_responde(vistos), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    assert vistos[0].url.path == "/data/v1/sectors/eletricas/deck"
    assert vistos[0].url.params["known_at"] == "2026-03-31"
    assert alvo.read_bytes() == _pptx_falso()


def test_deck_nome_estranho_da_api_nao_vira_caminho(
    rodar, chave, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    http = _deck_que_responde([], "../../fora.pptx")
    resultado = rodar("deck", "11111111000191", http=http, **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    assert (tmp_path / "tickerlab-empresa-11111111000191.pptx").exists()
    assert not (tmp_path.parent.parent / "fora.pptx").exists()


def test_deck_nao_troca_arquivo_existente_sem_substituir(rodar, chave, tmp_path):
    alvo = tmp_path / "d.pptx"
    alvo.write_bytes(b"antigo")
    http = _deck_que_responde([])
    recusa = rodar(
        "deck", "11111111000191", "--saida", str(alvo), http=http, **_com_chave(chave)
    )
    assert recusa.exit_code == Saida.PEDIDO_INVALIDO and alvo.read_bytes() == b"antigo"
    troca = rodar(
        "deck", "11111111000191", "--saida", str(alvo), "--substituir",
        http=http, **_com_chave(chave),
    )  # fmt: skip
    assert troca.exit_code == 0 and alvo.read_bytes() == _pptx_falso()


@pytest.mark.parametrize(
    "argumentos",
    [
        (),
        ("11111111000191", "--setor", "eletricas"),
        ("123",),
        ("--setor", "Ruim Aqui"),
    ],
)
def test_deck_pedido_mal_feito_nem_chega_a_api(rodar, chave, argumentos):
    vistos: list = []
    resultado = rodar(
        "deck", *argumentos, http=_deck_que_responde(vistos), **_com_chave(chave)
    )
    assert resultado.exit_code != 0 and vistos == []


def test_deck_sem_dado_e_chave_recusada_usam_os_codigos_dos_outros(
    rodar, chave, tmp_path
):
    sem_dado = rodar(
        "deck", "11111111000191", "--saida", str(tmp_path / "a.pptx"),
        http=_deck_que_responde([], status=404), **_com_chave(chave),
    )  # fmt: skip
    assert sem_dado.exit_code == Saida.SEM_DADO
    assert not (tmp_path / "a.pptx").exists()
    sem_chave = rodar("deck", "11111111000191", http=_deck_que_responde([]))
    assert sem_chave.exit_code == Saida.CHAVE


def test_deck_resposta_que_nao_e_arquivo_e_fora_do_ar(rodar, chave, tmp_path):
    http = _http_falso(lambda _p: httpx.Response(200, text="<html>"))
    resultado = rodar(
        "deck",
        "11111111000191",
        "--saida",
        str(tmp_path / "a.pptx"),
        http=http,
        **_com_chave(chave),
    )
    assert resultado.exit_code == Saida.FORA_DO_AR


# ---- tipo de evento não disponível para a organização (linha 883) ----------------------------------------


def _eventos_com_tipo_barrado(linhas: list[dict]) -> dict:
    return {
        "events": linhas,
        "unavailable_event_types": ["auditor_change"],
        "limits": [{"source": "cvm", "text": "só o que foi servido"}],
        "sources": [{"source": "cvm"}],
    }


def test_eventos_vazios_com_tipo_barrado_nao_dizem_que_nao_tem(rodar, chave):
    resultado = rodar(
        "eventos", "11111111000191",
        http=_resposta_fixa(_eventos_com_tipo_barrado([])), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    primeira = resultado.stdout.splitlines()[0]
    assert "não está disponível" in primeira and "auditor_change" in primeira
    assert "Nenhum evento da empresa até o dia" not in resultado.stdout


def test_eventos_com_linhas_e_tipo_barrado_avisam_na_primeira_linha(rodar, chave):
    linhas = [{"kind": _env("ipe_filing"), "year": _env(2025)}]
    resultado = rodar(
        "eventos", "11111111000191",
        http=_resposta_fixa(_eventos_com_tipo_barrado(linhas)), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    primeira = resultado.stdout.splitlines()[0]
    assert "auditor_change" in primeira and "1 eventos nesta resposta" in primeira


def test_eventos_sem_tipo_barrado_seguem_como_antes(rodar, chave):
    corpo = {"events": [], "unavailable_event_types": [], "sources": []}
    resultado = rodar(
        "eventos", "11111111000191", http=_resposta_fixa(corpo), **_com_chave(chave)
    )
    assert "Nenhum evento da empresa até o dia" in resultado.stdout
    assert "não está disponível" not in resultado.stdout


def test_eventos_em_json_passam_o_campo_inteiro(rodar, chave):
    corpo = _eventos_com_tipo_barrado([])
    resultado = rodar(
        "eventos", "11111111000191", "--json",
        http=_resposta_fixa(corpo), **_com_chave(chave),
    )  # fmt: skip
    assert json.loads(resultado.stdout) == corpo


def test_dossie_poe_o_tipo_barrado_em_gaps(rodar, chave):
    interno, _ = _secoes_do_dossie()

    def responder(pedido):
        resposta = interno(pedido)
        if pedido.url.path.endswith("/events"):
            return httpx.Response(200, json=_eventos_com_tipo_barrado([]))
        return resposta

    resultado = rodar(
        "dossie", "11111111000191", "--json",
        http=_http_falso(responder), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    lacunas = json.loads(resultado.stdout)["gaps"]
    assert [g["section"] for g in lacunas] == ["events"]
    assert "auditor_change" in lacunas[0]["reason"]
    tela = rodar(
        "dossie", "11111111000191",
        http=_http_falso(responder), **_com_chave(chave),
    )  # fmt: skip
    assert "Ficou de fora: events" in tela.stdout


def test_planilha_de_eventos_leva_o_aviso_de_nao_disponivel(rodar, chave, tmp_path):
    arquivo = tmp_path / "eventos.xlsx"
    resultado = rodar(
        "eventos", "11111111000191", "--planilha", str(arquivo),
        http=_resposta_fixa(_eventos_com_tipo_barrado([])), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    assert "auditor_change" in resultado.stdout
    celulas = " ".join(
        str(c) for linhas in _abrir_xlsx(arquivo).values() for l in linhas for c in l
    )
    assert "auditor_change" in celulas


def test_campo_unavailable_de_outra_rota_sai_pelo_proprio_nome(rodar, chave):
    corpo = {"links": [], "unavailable_link_types": ["auditor"], "sources": []}
    resultado = rodar(
        "vinculos", "11111111000191", http=_resposta_fixa(corpo), **_com_chave(chave)
    )
    assert resultado.exit_code == 0, resultado.output
    assert "tipos de vínculo: auditor" in resultado.stdout


def _ativos_da_anp() -> dict:
    return {
        "cnpj": "11111111000191",
        "assets": {
            "oil_gas_contracts": {
                "found": True,
                "source": "ANP",
                "latest_published_at": "2025-06-30",
                "coverage": "contratos de E&P vigentes",
                "items": [{"contract": "BM-X-1", "share": _env(0.3)}],
                "truncated": False,
            }
        },
        "not_covered": ["mining_rights"],
        "limits": ["Não achado não quer dizer que a empresa não tem o ativo."],
        "sources": [{"source": "ANP"}],
    }


def test_ativos_pede_a_rota_e_mostra_o_bloco(rodar, chave):
    pedidos: list[str] = []

    def responder(pedido):
        pedidos.append(pedido.url.path)
        return httpx.Response(200, json=_ativos_da_anp())

    resultado = rodar(
        "ativos", "11111111000191", "--como-era", "2025-07-01",
        http=_http_falso(responder), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    assert pedidos == ["/data/v1/companies/11111111000191/assets"]
    assert "oil_gas_contracts" in resultado.stdout
    assert "BM-X-1" in resultado.stdout
    assert "mining_rights" in resultado.stdout


def test_ativos_em_json_passa_inteiro(rodar, chave):
    resultado = rodar(
        "ativos", "11111111000191", "--json",
        http=_resposta_fixa(_ativos_da_anp()), **_com_chave(chave),
    )  # fmt: skip
    assert resultado.exit_code == 0, resultado.output
    assert json.loads(resultado.stdout) == _ativos_da_anp()


def test_ativos_sem_chave_sai_com_o_codigo_de_chave(rodar):
    resultado = rodar("ativos", "11111111000191")
    assert resultado.exit_code == 3


@pytest.mark.parametrize(
    ("comando", "campo", "valor", "rotulo"),
    [
        ("compradores", "unavailable_signals", "fund_partner", "sinais de comprador"),
        ("empresa", "unavailable_filings", "ITR", "entregas à CVM"),
        ("comparaveis", "unavailable_figures", "ebitda", "números dos comparáveis"),
        (
            "empresa",
            "unavailable_registration_fields",
            "simples_nacional",
            "campos do cadastro na Receita",
        ),
    ],
)
def test_rotulos_dos_campos_nao_disponiveis(
    rodar, chave, comando, campo, valor, rotulo
):
    corpo = {campo: [valor], "sources": []}
    args = ["--cnae", "47113"] if comando == "compradores" else ["11111111000191"]
    resultado = rodar(comando, *args, http=_resposta_fixa(corpo), **_com_chave(chave))
    assert resultado.exit_code == 0, resultado.output
    assert f"{rotulo}: {valor}" in resultado.stdout
