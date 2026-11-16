"""O cruzamento de raízes com a `cnpj_empresas_pj` (linha 789): pega a raiz que não é de PJ."""

import pandas as pd
import pytest

from base.dicionario import TABELAS
from base.porta import Porta
from base.porta.duckdb import ARQUIVOS
from base.sem_pessoa_por_raiz import (
    OUTRA_COLUNA,
    SEM_PESSOA_PELA_RAIZ,
    SO_A_RAIZ,
    TABELA_PJ,
    cruzar,
)

RAIZ_PJ, PESSOA_FICTICIA = "11111111", "99999999"


def _caminho(padrao: str) -> str:
    return padrao.replace("*", "x")


def _gravar(pasta, nome, tabela):
    arquivo = pasta / _caminho(ARQUIVOS[nome])
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(arquivo, index=False)


def _acervo(pasta, raizes, coluna="cnpj", pj_extra=()):
    raizes_pj = [RAIZ_PJ, "22222222", *pj_extra]
    colunas_pj = {c: ["x"] * len(raizes_pj) for c in TABELAS[TABELA_PJ].colunas}
    colunas_pj["cnpj_basico"] = raizes_pj
    colunas_pj[TABELAS[TABELA_PJ].datas["publico_em"]] = ["2024-07-31"] * len(raizes_pj)
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


def test_cnpj_alfanumerico_cruza_pela_raiz_sem_cortar_as_letras(tmp_path):
    """As letras do CNPJ novo ficam nas posições 9 a 12 (a ordem): a raiz de 8 continua numérica e é a da PJ."""
    _acervo(tmp_path, [RAIZ_PJ])
    arquivo = tmp_path / _caminho(ARQUIVOS["eventos"])
    tabela = pd.read_parquet(arquivo)
    tabela["cnpj"] = ["11.111.111/00AB-35"]
    tabela.to_parquet(arquivo, index=False)
    with Porta(tmp_path) as porta:
        c = cruzar(porta, "eventos", "cnpj")
    assert (c.raizes, c.fora_da_pj, c.sem_pessoa) == (1, 0, True)


def test_cnpj_com_letra_na_raiz_cruza_pela_raiz_inteira(tmp_path):
    # a raiz com letra está na lista de PJ: só passa se as letras ficarem na raiz
    _acervo(tmp_path, ["A1B2C3D4"], pj_extra=["A1B2C3D4"])
    with Porta(tmp_path) as porta:
        c = cruzar(porta, "eventos", "cnpj")
    assert (c.raizes, c.fora_da_pj) == (1, 0)


def test_raiz_do_texto_diferente_da_coluna_de_raiz_reprova(tmp_path, monkeypatch):
    from base import sem_pessoa_por_raiz as modulo

    _acervo(tmp_path, [RAIZ_PJ])
    arquivo = tmp_path / _caminho(ARQUIVOS["eventos"])
    tabela = pd.read_parquet(arquivo)
    tabela["cnpj"] = ["11.111.111/00AB-35"]
    tabela["protocolo"] = "11111111"
    tabela.to_parquet(arquivo, index=False)
    monkeypatch.setitem(modulo.RAIZ_SEPARADA, "eventos", "protocolo")
    with Porta(tmp_path) as porta:
        assert cruzar(porta, "eventos", "cnpj").sem_pessoa
        tabela["protocolo"] = "22222222"
        tabela.to_parquet(arquivo, index=False)
    with Porta(tmp_path) as porta:
        c = cruzar(porta, "eventos", "cnpj")
    assert (c.fora_da_pj, c.raiz_diferente, c.sem_pessoa) == (0, 1, False)


def test_tabela_vazia_nao_conta_como_sem_pessoa(tmp_path):
    _acervo(tmp_path, [])
    with Porta(tmp_path) as porta:
        assert not cruzar(porta, "eventos", "cnpj").sem_pessoa


@pytest.mark.parametrize("nome,coluna", SEM_PESSOA_PELA_RAIZ.items())
def test_a_coluna_existe_no_dicionario(nome, coluna):
    assert coluna in TABELAS[nome].colunas


def test_cruzar_todas_pula_a_copia_que_so_existe_no_envio(tmp_path, monkeypatch):
    """`fips_registrados` só é montada no envio ao VPS: sem arquivo em casa, não derruba a conferência das outras."""
    from base import sem_pessoa_por_raiz as modulo

    _acervo(tmp_path, [RAIZ_PJ])
    monkeypatch.setattr(
        modulo,
        "SEM_PESSOA_PELA_RAIZ",
        {"eventos": "cnpj", "fips_registrados": "CNPJ_Fundo"},
    )
    assert "fips_registrados" in modulo.SO_NA_COPIA_DO_ENVIO
    with Porta(tmp_path) as porta:
        assert [c.tabela for c in modulo.cruzar_todas(porta)] == ["eventos"]


# linha 957: a `empresa_serie` guarda só a raiz da entidade (8 posições, "quando há") e o CNPJ da companhia


def _empresa_serie(pasta, raizes, companhias, pj_extra=()):
    _acervo(pasta, [], pj_extra=pj_extra)
    tabela = {c: ["x"] * len(raizes) for c in TABELAS["empresa_serie"].colunas}
    tabela["raiz"] = list(raizes)
    tabela["cnpj_companhia"] = list(companhias)
    tabela["desde"] = ["2024-07-31"] * len(raizes)
    tabela["montado_em"] = ["2024-07-31T12:00:00"] * len(raizes)
    _gravar(pasta, "empresa_serie", pd.DataFrame(tabela))


def test_coluna_que_ja_e_a_raiz_cruza_com_a_outra_coluna(tmp_path):
    _empresa_serie(tmp_path, [RAIZ_PJ, None], [f"{RAIZ_PJ}000100", "22222222000100"])
    with Porta(tmp_path) as porta:
        c = cruzar(porta, "empresa_serie", "raiz")
    assert (c.raizes, c.fora_da_pj, c.sem_documento, c.sem_pessoa) == (2, 0, 0, True)


def test_raiz_de_fora_na_coluna_de_raiz_reprova_sem_dizer_qual(tmp_path):
    _empresa_serie(tmp_path, [PESSOA_FICTICIA], [f"{RAIZ_PJ}000100"])
    with Porta(tmp_path) as porta:
        c = cruzar(porta, "empresa_serie", "raiz")
    assert (c.raizes, c.fora_da_pj, c.sem_pessoa) == (2, 1, False)
    assert PESSOA_FICTICIA not in repr(c)


def test_companhia_de_fora_reprova(tmp_path):
    _empresa_serie(tmp_path, [RAIZ_PJ], [f"{PESSOA_FICTICIA}000100"])
    with Porta(tmp_path) as porta:
        assert not cruzar(porta, "empresa_serie", "raiz").sem_pessoa


def test_raiz_fora_da_forma_de_oito_conta_como_fora(tmp_path):
    # zero à esquerda perdido (7 posições) ou o CNPJ inteiro no lugar da raiz: não é a raiz, conta como fora
    _empresa_serie(
        tmp_path, ["1111111", f"{RAIZ_PJ}000100"], [None, None], pj_extra=["01111111"]
    )
    with Porta(tmp_path) as porta:
        c = cruzar(porta, "empresa_serie", "raiz")
    assert (c.raizes, c.fora_da_pj, c.sem_pessoa) == (1, 1, False)


def test_raiz_com_letra_e_minuscula_cruza_pela_raiz_inteira(tmp_path):
    _empresa_serie(tmp_path, ["a1b2c3d4"], [None], pj_extra=["A1B2C3D4"])
    with Porta(tmp_path) as porta:
        c = cruzar(porta, "empresa_serie", "raiz")
    assert (c.raizes, c.fora_da_pj, c.sem_pessoa) == (1, 0, True)


def test_linha_sem_raiz_nem_companhia_nao_tem_prova(tmp_path):
    """Entidade só pelo nome e sem ligação: nada prova que é pessoa jurídica. Na dúvida, reprova."""
    _empresa_serie(tmp_path, [RAIZ_PJ, None, ""], [None, None, "  "])
    with Porta(tmp_path) as porta:
        c = cruzar(porta, "empresa_serie", "raiz")
    assert (c.raizes, c.fora_da_pj, c.sem_documento, c.sem_pessoa) == (1, 0, 2, False)


@pytest.mark.parametrize("nome,coluna", OUTRA_COLUNA.items())
def test_a_outra_coluna_existe_no_dicionario(nome, coluna):
    assert coluna in TABELAS[nome].colunas
    assert nome in SO_A_RAIZ


@pytest.mark.parametrize("nome,coluna", SO_A_RAIZ.items())
def test_a_coluna_de_raiz_e_a_de_oito_posicoes_e_a_mesma_da_lista(nome, coluna):
    assert "8" in TABELAS[nome].colunas[coluna][0]
    assert SEM_PESSOA_PELA_RAIZ.get(nome, coluna) == coluna


def test_empresa_serie_reprovada_nao_esta_na_lista():
    """Medida em 16/11/2026: raiz fora da lista de PJ e linha sem documento. Só volta pela linha 960, medida de novo."""
    assert "empresa_serie" not in SEM_PESSOA_PELA_RAIZ
