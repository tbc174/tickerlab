"""O cruzamento de raízes com a `cnpj_empresas_pj` (linha 789): pega a raiz que não é de PJ."""

import pandas as pd
import pytest

from base.dicionario import TABELAS
from base.porta import Porta
from base.porta.duckdb import ARQUIVOS
from base.sem_pessoa_por_raiz import SEM_PESSOA_PELA_RAIZ, TABELA_PJ, cruzar

RAIZ_PJ, PESSOA_FICTICIA = "11111111", "99999999"


def _caminho(padrao: str) -> str:
    return padrao.replace("*", "x")


def _gravar(pasta, nome, tabela):
    arquivo = pasta / _caminho(ARQUIVOS[nome])
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(arquivo, index=False)


def _acervo(pasta, raizes, coluna="cnpj"):
    colunas_pj = {c: ["x"] * 2 for c in TABELAS[TABELA_PJ].colunas}
    colunas_pj["cnpj_basico"] = [RAIZ_PJ, "22222222"]
    colunas_pj[TABELAS[TABELA_PJ].datas["publico_em"]] = ["2024-07-31"] * 2
    _gravar(pasta, TABELA_PJ, pd.DataFrame(colunas_pj))
    tabela = {c: ["x"] * len(raizes) for c in TABELAS["eventos"].colunas}
    tabela[coluna] = [f"{r}000100" for r in raizes]
    tabela[TABELAS["eventos"].datas["publico_em"]] = ["2024-07-31"] * len(raizes)
    _gravar(pasta, "eventos", pd.DataFrame(tabela))


def test_so_raiz_de_pj_passa(tmp_path):
    _acervo(tmp_path, [RAIZ_PJ, RAIZ_PJ, "22222222"])
    with Porta(tmp_path) as porta:
        c = cruzar(porta, "eventos", "cnpj")
    assert (c.raizes, c.fora_da_pj, c.sem_pessoa) == (2, 0, True)


def test_raiz_fora_da_pj_reprova_sem_dizer_qual(tmp_path):
    _acervo(tmp_path, [RAIZ_PJ, PESSOA_FICTICIA])
    with Porta(tmp_path) as porta:
        c = cruzar(porta, "eventos", "cnpj")
    assert (c.raizes, c.fora_da_pj, c.sem_pessoa) == (2, 1, False)
    assert PESSOA_FICTICIA not in repr(c)


def test_cnpj_com_pontuacao_e_zero_a_esquerda_cruza_certo(tmp_path):
    _acervo(tmp_path, [RAIZ_PJ])
    arquivo = tmp_path / _caminho(ARQUIVOS["eventos"])
    tabela = pd.read_parquet(arquivo)
    tabela["cnpj"] = ["11.111.111/0001-00"]
    tabela.to_parquet(arquivo, index=False)
    with Porta(tmp_path) as porta:
        assert cruzar(porta, "eventos", "cnpj").sem_pessoa


def test_cnpj_sem_os_quatorze_digitos_conta_como_fora(tmp_path):
    _acervo(tmp_path, [RAIZ_PJ])
    arquivo = tmp_path / _caminho(ARQUIVOS["eventos"])
    tabela = pd.read_parquet(arquivo)
    tabela["cnpj"] = ["1111111100010"]  # perdeu um zero à esquerda: a raiz andaria
    tabela.to_parquet(arquivo, index=False)
    with Porta(tmp_path) as porta:
        c = cruzar(porta, "eventos", "cnpj")
    assert (c.raizes, c.fora_da_pj) == (1, 1)


def test_tabela_vazia_nao_conta_como_sem_pessoa(tmp_path):
    _acervo(tmp_path, [])
    with Porta(tmp_path) as porta:
        assert not cruzar(porta, "eventos", "cnpj").sem_pessoa


@pytest.mark.parametrize("nome,coluna", SEM_PESSOA_PELA_RAIZ.items())
def test_a_coluna_existe_no_dicionario(nome, coluna):
    assert coluna in TABELAS[nome].colunas
