"""Dicionário de dados da base de ML (série 1, PR 8; ADR 0027, exigência 8): toda coluna de toda
tabela tem descrição e unidade, e toda tabela tem fonte, licença, frequência e atraso de
divulgação. O documento para o Tiago revisar é gerado daqui e precisa estar em dia."""

from pathlib import Path

from base.cadastro import COLUNAS_DOS_TICKERS, ler_cadastro
from base.dicionario import ARQUIVO_DO_DOCUMENTO, TABELAS, documento_em_markdown
from base.ponto_no_tempo import COLUNAS_DA_BASE
from src.banco.coletas import SEM_LICENCA_CONHECIDA, licenca_da_fonte
from src.banco.modelo import achados_de_qualidade

RAIZ = Path(__file__).resolve().parent.parent


def _colunas_de_verdade() -> dict[str, list[str]]:
    cadastro = ler_cadastro(b"CNPJ_CIA;DENOM_SOCIAL;SIT\n1;A;ATIVO\n")
    return {
        "demonstracoes_como_era": list(COLUNAS_DA_BASE),
        "achados_de_qualidade": [c.name for c in achados_de_qualidade.columns],
        "cadastro_das_companhias": list(cadastro.columns),
        "tickers_no_tempo": list(COLUNAS_DOS_TICKERS),
    }


def test_dicionario_cobre_toda_coluna_da_base():
    for tabela, colunas in _colunas_de_verdade().items():
        assert tabela in TABELAS, tabela
        assert set(TABELAS[tabela].colunas) == set(colunas), tabela


def test_toda_tabela_tem_fonte_licenca_frequencia_e_atraso():
    for nome, tabela in TABELAS.items():
        for campo in ("descricao", "fonte", "frequencia", "atraso", "onde"):
            assert getattr(tabela, campo), f"{nome}: falta {campo}"
        assert licenca_da_fonte(tabela.familia_da_fonte) != SEM_LICENCA_CONHECIDA, nome
        for coluna, (descricao, unidade) in tabela.colunas.items():
            assert descricao and unidade, f"{nome}.{coluna}"


def test_documento_do_dicionario_esta_em_dia():
    """Mudou o dicionário? Rode `python -m base.dicionario`."""
    atual = (RAIZ / ARQUIVO_DO_DOCUMENTO).read_text(encoding="utf-8")
    assert atual == documento_em_markdown()
