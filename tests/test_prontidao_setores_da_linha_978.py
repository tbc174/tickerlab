"""Os setores (`empresa_serie` e `anatel_acessos`) no registro de piloto (linha 978; ADR 0108, Emenda 2, D11).

As duas tabelas têm coluna de CNPJ ou raiz e nenhuma marca de pessoa por linha: a tabela inteira, de casa, tem raiz fora da
`cnpj_empresas_pj` e linha sem documento. Só contam como decididas porque o servidor da API guarda apenas a cópia reduzida
de `base/recorte_dos_setores.py` (degrau 7), conferida por máquina a cada montagem. O placar de 19/11/2026 deu verde com o
motivo de cada vazio e de cada salto escrito na regra. A linha de companhia dos setores segue fechada: o
`cadastro_das_companhias` ainda não existe em Parquet nem tem prontidão.
"""

from datetime import date

import pytest

from base import prontidao, recorte_dos_setores
from base.dicionario import TABELAS
from base.qualidade_automatica import REGRAS
from src import portao_externo as portao

HOJE = date(2026, 11, 19)
DOS_SETORES = ("empresa_serie", "anatel_acessos")


def _decidir(fonte: str, campo: str, *, piloto: bool, conjunto: str = "sectors"):
    pedido = portao.Pedido(
        fonte,
        conjunto,
        campo,
        portao.Canal.API_EXTERNA,
        portao.Finalidade.ANALISE,
        False,
        piloto,
    )
    return portao.decidir(pedido, HOJE)


def test_a_lista_decidida_e_a_que_o_recorte_dos_setores_reduz() -> None:
    assert frozenset(DOS_SETORES) == prontidao.COPIA_REDUZIDA_PELA_RAIZ
    assert set(recorte_dos_setores.SETORES) == set(DOS_SETORES)


@pytest.mark.parametrize("tabela", DOS_SETORES)
def test_a_tabela_inteira_nao_e_de_pessoa_mas_so_conta_como_decidida_pela_copia(
    tabela: str,
) -> None:
    assert not TABELAS[tabela].pessoa
    assert tabela in prontidao.tabelas_com_pessoa_decidida()
    # fora da lista, uma tabela com coluna de CNPJ e sem marca por linha continua sem a decisão
    assert not prontidao.pessoa_decidida(
        "tabela_qualquer", pessoa=False, colunas=("cnpj",), linhas_de_pessoa=""
    )


@pytest.mark.parametrize("tabela", DOS_SETORES)
def test_sem_o_registro_de_piloto_a_tabela_nao_sai(tabela: str) -> None:
    falta = prontidao.negacao_do_piloto(
        (tabela,), {}, prontidao.versoes_maiores(), frozenset({tabela}), HOJE
    )
    assert falta is prontidao.Falta.SEM_PRONTIDAO


@pytest.mark.parametrize("tabela", DOS_SETORES)
def test_o_registro_de_verdade_libera_a_tabela_pelo_piloto(tabela: str) -> None:
    falta = prontidao.negacao_do_piloto(
        (tabela,),
        prontidao.PRONTIDAO_DE_PILOTO,
        prontidao.versoes_maiores(),
        prontidao.tabelas_com_pessoa_decidida(),
        HOJE,
    )
    assert falta is None


@pytest.mark.parametrize("tabela", DOS_SETORES)
def test_a_versao_e_as_duas_provas_sao_as_do_piloto(tabela: str) -> None:
    registro = prontidao.PRONTIDAO_DE_PILOTO[tabela]
    assert registro.versao_maior == prontidao.versoes_maiores()[tabela]
    assert registro.qualidade is not None and registro.dicionario is not None
    assert registro.qualidade.data == HOJE
    assert prontidao.prova_publicavel(registro.qualidade.prova)
    assert prontidao.prova_publicavel(registro.dicionario.prova)


@pytest.mark.parametrize("tabela", DOS_SETORES)
def test_a_tabela_tem_regra_de_qualidade_com_o_motivo_dos_vazios_e_nao_vira_prontidao_cheia(
    tabela: str,
) -> None:
    assert tabela in REGRAS
    assert tabela not in prontidao.PRONTIDAO
    assert all(REGRAS[tabela].opcionais.values())  # cada vazio aceito diz o porquê
    assert all(REGRAS[tabela].saltos_explicados.values())


def test_a_linha_agregada_do_setor_abre_so_para_o_piloto() -> None:
    aberta = _decidir("anatel-acessos", "hhi", piloto=True)
    assert aberta.libera and aberta.motivo == portao.Motivo.LIBERADO_PELO_PILOTO
    assert aberta.piloto  # o bloco leva o aviso "Dado de piloto"
    fechada = _decidir("anatel-acessos", "hhi", piloto=False)
    assert not fechada.libera


@pytest.mark.parametrize("fonte", [fonte for fonte, _ in portao._SERIES_DOS_SETORES])
def test_a_linha_agregada_abre_em_toda_serie_de_agencia_pronta_e_so_para_o_piloto(
    fonte: str,
) -> None:
    """A `empresa_serie` pronta também abre a linha agregada das outras séries (aneel, ifdata, susep, ans): era a única
    tabela delas sem prontidão. O campo é agregado (índice de concentração), nunca empresa nem pessoa."""
    assert _decidir(fonte, "hhi", piloto=True).libera
    assert not _decidir(fonte, "hhi", piloto=False).libera


@pytest.mark.parametrize("campo", ["cnpj", "empresa", "valor", "participacao"])
def test_a_linha_de_companhia_dos_setores_segue_fechada_sem_o_cadastro_em_parquet(
    campo: str,
) -> None:
    """Depende do `cadastro_das_companhias`, que não tem Parquet nem prontidão: nada abre por tabela vizinha."""
    assert "cadastro_das_companhias" not in prontidao.PRONTIDAO_DE_PILOTO
    assert not _decidir("anatel-acessos", campo, piloto=True).libera
    assert not _decidir("cvm-cadastros", campo, piloto=True).libera
