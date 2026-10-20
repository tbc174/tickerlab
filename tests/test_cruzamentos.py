"""Os cruzamentos do bloco comum (item 5): regra, fonte, data, "sem achado" e sem olhar o futuro."""

import copy
import inspect
from datetime import UTC, date, datetime

import pytest

from src import cruzamentos
from src.cruzamentos import (
    AUDITOR,
    FUNDOS,
    INSIDERS,
    REFEITO,
    cruzamentos_da_ficha,
    cruzamentos_do_setor,
)
from src.dossie import Ficha, SecaoDaFicha

HOJE = date(2026, 10, 19)
FONTE = "CVM, tabela de teste"


def _ficha(*secoes: SecaoDaFicha) -> Ficha:
    return Ficha(
        versao_do_esquema=1,
        cnpj="02429144000193",
        empresa="Empresa Teste",
        gerado_em=datetime(2026, 10, 19, 6, 0, tzinfo=UTC),
        secoes=list(secoes),
    )


def _capital(fundos=None, insiders=None) -> SecaoDaFicha:
    return SecaoDaFicha(
        chave="capital_e_acionistas",
        titulo="Capital e acionistas",
        tabelas={"fundos_janelas": fundos or [], "insiders_janelas": insiders or []},
        fontes=[FONTE],
    )


def _janelas(compras, vendas, compras_antes, vendas_antes, ate="2026-09-30"):
    return [
        {"janela": "últimos 12 meses", "ate": ate, "compras": compras, "vendas": vendas},
        {"janela": "12 meses anteriores", "ate": "2025-09-30", "compras": compras_antes, "vendas": vendas_antes},
    ]  # fmt: skip


def _qualidade(refeitos=(), olhados=10, diferentes=0) -> SecaoDaFicha:
    return SecaoDaFicha(
        chave="qualidade_do_lucro",
        titulo="Qualidade do lucro",
        itens=[
            {
                "chave": "exercicios_olhados",
                "nome": "olhados",
                "valor": olhados,
                "unidade": "exercícios",
                "base": "2026-03-20",
            },
            {
                "chave": "releases_diferentes",
                "nome": "diferentes",
                "valor": diferentes,
                "unidade": "valores",
                "base": "2026-08-14",
            },
        ],
        tabelas={"reapresentacoes": list(refeitos)},
        fontes=[FONTE],
    )


def _troca(efetiva_em: str) -> dict:
    return {
        "efetiva_em": efetiva_em,
        "anterior": "Firma A",
        "novo": "Firma B",
        "anos_com_o_anterior": 8.0,
    }


def _auditor(*trocas) -> SecaoDaFicha:
    return SecaoDaFicha(
        chave="auditor_e_controladas",
        titulo="Auditor",
        tabelas={"trocas_de_auditor": list(trocas)},
        fontes=[FONTE],
    )


def _achar(ficha: Ficha, chave: str, hoje: date = HOJE):
    return {c.chave: c for c in cruzamentos_da_ficha(ficha, hoje)}[chave]


# --- fundos ---------------------------------------------------------------------------------------


def test_fundos_entrando_quando_o_saldo_passa_de_25_por_cento_do_volume():
    ficha = _ficha(_capital(fundos=_janelas(900.0, 100.0, 500.0, 400.0)))
    achado = _achar(ficha, FUNDOS)
    assert achado.achado
    assert achado.frase.startswith("Fundos entrando.")
    assert achado.medido_em == "2026-09-30" and achado.fontes == (FONTE,)
    assert "30/09/2026" in achado.frase


def test_fundos_saindo_e_virada_de_saldo():
    saindo = _achar(
        _ficha(_capital(fundos=_janelas(100.0, 900.0, 400.0, 500.0))), FUNDOS
    )
    assert saindo.frase.startswith("Fundos saindo.")
    virada = _achar(
        _ficha(_capital(fundos=_janelas(480.0, 520.0, 700.0, 300.0))), FUNDOS
    )
    assert virada.achado and virada.frase.startswith("Fundos viraram o saldo.")


def test_fundos_equilibrados_dizem_sem_achado_com_os_numeros():
    achado = _achar(
        _ficha(_capital(fundos=_janelas(520.0, 480.0, 510.0, 490.0))), FUNDOS
    )
    assert not achado.achado and achado.frase.startswith("Sem achado.")


def test_fundos_sem_as_duas_janelas_nao_inventa():
    achado = _achar(_ficha(_capital(fundos=_janelas(1.0, 1.0, 1.0, 1.0)[:1])), FUNDOS)
    assert not achado.achado and achado.medido_em is None


# --- número refeito -------------------------------------------------------------------------------


def test_refeito_conta_exercicios_e_datas():
    refeitos = [
        {"exercicio": 2023, "linha": "Lucro do período", "trocado_em": "2024-05-10"},
        {"exercicio": 2023, "linha": "Receita", "trocado_em": "2024-05-10"},
        {"exercicio": 2024, "linha": "Receita", "trocado_em": "2025-04-02"},
    ]
    achado = _achar(_ficha(_qualidade(refeitos)), REFEITO)
    assert achado.achado
    assert "2 de 10 exercícios" in achado.frase and "02/04/2025" in achado.frase
    assert achado.numeros["exercicios_refeitos"] == 2


def test_refeito_com_release_diferente_tambem_e_achado():
    achado = _achar(_ficha(_qualidade(diferentes=3)), REFEITO)
    assert achado.achado and "3 valores do release" in achado.frase


def test_refeito_limpo_diz_quantos_olhou():
    achado = _achar(_ficha(_qualidade()), REFEITO)
    assert not achado.achado and "Nenhum dos 10 exercícios" in achado.frase


# --- troca de auditor -----------------------------------------------------------------------------


def test_troca_recente_de_auditor_e_achado_e_antiga_nao():
    recente = _achar(_ficha(_auditor(_troca("2025-06-30"))), AUDITOR)
    assert recente.achado and "Firma A para Firma B" in recente.frase
    antiga = _achar(_ficha(_auditor(_troca("2019-06-30"))), AUDITOR)
    assert not antiga.achado and "há mais de 3 anos" in antiga.frase


def test_sem_troca_nenhuma_diz_sem_achado():
    assert not _achar(_ficha(_auditor()), AUDITOR).achado


# --- insiders -------------------------------------------------------------------------------------


def _insiders(compras, vendas, negociacoes=7) -> SecaoDaFicha:
    return _capital(
        insiders=[{"janela": "últimos 12 meses", "ate": "2026-10-19", "compras": compras, "vendas": vendas, "negociacoes": negociacoes}]
    )  # fmt: skip


def test_insiders_predominam_vendas_ou_compras_so_no_agregado():
    vendas = _achar(_ficha(_insiders(100.0, 900.0)), INSIDERS)
    assert vendas.achado and vendas.frase.startswith("Predominam as vendas.")
    assert "sem nomes" in vendas.frase and "7 negociações" in vendas.frase
    compras = _achar(_ficha(_insiders(900.0, 100.0)), INSIDERS)
    assert compras.frase.startswith("Predominam as compras.")


def test_insiders_equilibrados_ou_sem_volume_nao_sao_achado():
    assert not _achar(_ficha(_insiders(500.0, 500.0)), INSIDERS).achado
    assert not _achar(_ficha(_insiders(0.0, 0.0, 0)), INSIDERS).achado


# --- sem olhar o futuro ---------------------------------------------------------------------------


def test_linhas_do_futuro_nao_mudam_o_passado():
    """Cortar o futuro não muda o passado: o que tem data depois de `hoje` é ignorado."""
    passado = [_troca("2025-06-30")]
    futuro = [*passado, {**_troca("2027-01-01"), "novo": "Firma Futura"}]
    refeitos = [{"exercicio": 2023, "linha": "Receita", "trocado_em": "2024-05-10"}]
    com_futuro = [
        *refeitos,
        {"exercicio": 2025, "linha": "Receita", "trocado_em": "2027-02-01"},
    ]
    janelas = _janelas(900.0, 100.0, 500.0, 400.0)
    com_janela_futura = [
        {"janela": "x", "ate": "2027-09-30", "compras": 1.0, "vendas": 9e9},
        *janelas,
    ]
    insiders = [
        {
            "janela": "x",
            "ate": "2030-01-01",
            "compras": 9e9,
            "vendas": 0.0,
            "negociacoes": 1,
        }
    ]
    sem = _ficha(_capital(janelas), _qualidade(refeitos), _auditor(*passado))
    com = _ficha(
        _capital(com_janela_futura, insiders),
        _qualidade(com_futuro),
        _auditor(*futuro),
    )
    assert cruzamentos_da_ficha(sem, HOJE)[:3] == cruzamentos_da_ficha(com, HOJE)[:3]
    assert not _achar(com, INSIDERS).achado


# --- dívida ativa e pessoas -----------------------------------------------------------------------


def test_o_bloco_nao_le_a_divida_ativa_nem_nomes_de_pessoas():
    """ADR 0103: `pgfn_divida` bloqueada até o ponto 9; insiders só agregados."""
    codigo = inspect.getsource(cruzamentos).replace(cruzamentos.__doc__ or "", "")
    assert "pgfn" not in codigo.lower()
    for coluna in ("nome", "cpf", "pessoa"):
        assert f'["{coluna}"]' not in codigo


def test_os_quatro_cruzamentos_sempre_na_mesma_ordem():
    chaves = [c.chave for c in cruzamentos_da_ficha(_ficha(), HOJE)]
    assert chaves == [FUNDOS, REFEITO, AUDITOR, INSIDERS]
    assert all(not c.achado and c.frase for c in cruzamentos_da_ficha(_ficha(), HOJE))


# --- o setor --------------------------------------------------------------------------------------


def test_setor_soma_quem_tem_achado_e_nao_conta_quem_nao_tinha_dado():
    entra = _ficha(_capital(fundos=_janelas(900.0, 100.0, 500.0, 400.0)))
    equilibrada = _ficha(_capital(fundos=_janelas(520.0, 480.0, 510.0, 490.0)))
    sem_dado = _ficha()
    setor = {c.chave: c for c in cruzamentos_do_setor(
        {"Alfa": entra, "Beta": equilibrada, "Gama": sem_dado}, HOJE
    )}  # fmt: skip
    fundos = setor[FUNDOS]
    assert (fundos.com_achado, fundos.avaliadas) == (1, 2)
    assert fundos.empresas == ("Alfa",) and fundos.fontes == (FONTE,)
    assert (
        fundos.frase
        == "Fundos entrando e saindo: 1 de 2 companhias do setor com dado têm achado."
    )
    assert setor[AUDITOR].avaliadas == 0
    assert "nenhuma companhia" in setor[AUDITOR].frase


def test_cruzamentos_nao_mudam_a_ficha_recebida():
    ficha = _ficha(_capital(fundos=_janelas(900.0, 100.0, 500.0, 400.0)))
    antes = copy.deepcopy(ficha)
    cruzamentos_da_ficha(ficha, HOJE)
    assert ficha == antes


@pytest.mark.parametrize("regra", cruzamentos.REGRAS)
def test_cada_regra_aceita_ficha_vazia(regra):
    assert not regra(_ficha(), HOJE).achado
