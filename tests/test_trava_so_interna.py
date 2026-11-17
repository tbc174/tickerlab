"""Trava das fontes só internas (plano dos processos de 03/11/2026, PR 3; ADR 0121).

O DataJud (API Pública do CNJ) entra na base só para uso interno: treinar e rotular. Os termos de uso
(itens 3.3 e 3.8) vedam o uso comercial e a consultoria, então o dado nunca sai em tela, relatório, PDF,
API (do app ou externa) nem exportação. A trava fica num lugar só, `coletas.pode_usar`, por onde passam a
vitrine, o dossiê, a busca por CNPJ, o relatório, a exportação do acervo e o portão da API externa.
"""

from datetime import date

import pytest

from src import portao_externo as portao
from src.banco import coletas
from src.banco.coletas import (
    FONTES_SO_INTERNAS,
    MOSTRAR,
    USOS_INTERNOS,
    LicencaNaoPermiteError,
    exigir_licenca,
    pode_usar,
    so_interna,
)
from src.portao_externo import Canal, Decisao, Finalidade, Pedido, decidir

DATAJUD = ("datajud", "datajud-processos")
HOJE = date(2026, 11, 5)


def test_o_datajud_e_a_unica_fonte_so_interna():
    assert frozenset({"datajud"}) == FONTES_SO_INTERNAS
    assert USOS_INTERNOS == ("treinar", "rotular")
    assert set(USOS_INTERNOS) < set(coletas.USOS)


@pytest.mark.parametrize("fonte", DATAJUD)
@pytest.mark.parametrize("uso", ["treinar", "rotular"])
def test_datajud_entra_nos_usos_internos(fonte, uso):
    assert pode_usar(uso, fonte) is True
    exigir_licenca(uso, [fonte, "cvm-ipe"], onde="teste")


@pytest.mark.parametrize("fonte", DATAJUD)
@pytest.mark.parametrize("uso", ["exportar", MOSTRAR])
def test_datajud_nunca_sai(fonte, uso):
    assert pode_usar(uso, fonte) is False
    with pytest.raises(LicencaNaoPermiteError, match="só uso interno"):
        exigir_licenca(uso, ["cvm-ipe", fonte], onde="ficha")


def test_so_interna_olha_a_familia_e_nao_o_comeco_do_nome():
    assert so_interna("datajud") and so_interna("datajud-processos")
    assert not so_interna("djen") and not so_interna("djen-processos")
    assert not so_interna("datajudx") and not so_interna("termos-datajud")


def test_o_djen_continua_saindo_em_todos_os_usos():
    for uso in coletas.USOS:
        assert pode_usar(uso, "djen-processos") is True


def test_o_datajud_esta_registrado_como_as_outras_fontes():
    assert "uso interno" in coletas.LICENCAS["datajud"]
    assert coletas.REVENDA["datajud"] == coletas.SO_USO_INTERNO
    assert "datajud" in coletas.COLETA_E_GUARDA


def test_o_endereco_do_datajud_tem_familia_na_base():
    from base.licenca import FAMILIA_DO_ENDERECO

    familias = {
        familia
        for endereco, familia in FAMILIA_DO_ENDERECO.items()
        if "api-publica.datajud.cnj.jus.br" in endereco
    }
    assert familias == {"datajud"}


def _pedido(canal: str, finalidade: Finalidade) -> Pedido:
    return Pedido(
        fonte="datajud-processos",
        conjunto="processos_datajud",
        campo="classe",
        canal=canal,
        finalidade=finalidade,
    )


def test_a_api_externa_nega_o_datajud_desde_o_primeiro_dia():
    assert "datajud" in portao.NEGADAS_DESDE_O_PRIMEIRO_DIA
    for finalidade in Finalidade:
        pedido = _pedido(Canal.API_EXTERNA, finalidade)
        assert decidir(pedido, HOJE).libera is False


@pytest.mark.parametrize("canal", sorted(portao.CANAIS_DO_APP))
def test_nos_canais_do_app_o_datajud_so_treina(canal):
    mostrar = decidir(_pedido(canal, Finalidade.ANALISE), HOJE)
    treinar = decidir(_pedido(canal, Finalidade.TREINO), HOJE)
    assert mostrar == Decisao(False, portao.Motivo.REGRA_DO_APP)
    assert treinar == Decisao(True, portao.Motivo.REGRA_DO_APP)


# --- o site público -------------------------------------------------------------------------------

TABELAS_DO_DATAJUD = ("processos_datajud", "processos_datajud_movimentos")


def test_o_catalogo_publico_tira_as_tabelas_so_internas():
    from base import vitrine
    from base.contrato import catalogo

    completo = catalogo()
    publico = vitrine.catalogo_publico(
        completo, montadas=frozenset(completo["tabelas"])
    )
    assert set(TABELAS_DO_DATAJUD) <= set(completo["tabelas"])
    assert not set(TABELAS_DO_DATAJUD) & set(publico["tabelas"])
    assert "processos_comunicacoes" in publico["tabelas"]  # o DJEN continua


def test_a_pagina_dados_nao_mostra_o_datajud():
    """Nem o nome da tabela: o site não anuncia dado que não pode sair."""
    import json

    from scripts import exportar_conteudo as exp

    pagina = exp.conteudo()["catalogo"]
    for parte in ("tabelas", "modulos", "fontes", "ligado_pelo_cnpj"):
        texto = json.dumps(pagina[parte], ensure_ascii=False)
        assert "processos_datajud" not in texto, parte
        assert coletas.licenca_da_fonte("datajud") not in texto, parte


# --- o Ficha Clara e a vista do CNPJ --------------------------------------------------------------


def test_o_ficha_clara_e_a_vista_do_cnpj_nao_leem_tabela_so_interna():
    """As duas saídas por CNPJ leem listas fixas de tabelas: nenhuma pode ser de fonte só interna."""
    from base.conferencias_por_cnpj import FONTES
    from base.dicionario import TABELAS
    from base.porta import vista_do_cnpj

    lidas = {tabela for fonte in FONTES for tabela in fonte.lidas}
    assert {
        "processos",
        "processos_partes",
        "processos_comunicacoes",
    } <= lidas  # o DJEN sai
    lidas |= set(vista_do_cnpj.MUDANCAS)
    lidas.add(vista_do_cnpj.PARTICIPACOES)
    internas = {
        nome
        for nome in lidas
        if nome in TABELAS and so_interna(TABELAS[nome].familia_da_fonte)
    }
    assert not internas
    assert not set(TABELAS_DO_DATAJUD) & lidas
