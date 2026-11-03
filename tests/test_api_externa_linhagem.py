"""Os direitos dos campos do beta da API externa (B-32a, PR 2; ADR 0108, D2.2, D3 e D10).

Cada linha de `DIREITOS_DA_API_EXTERNA` diz que um campo, de uma fonte e de uma tabela do dicionário, sai
para quem integra. Estes testes conferem a linhagem de cada linha (a fonte alimenta a tabela, o campo
existe nela, a prova pode ir para o catálogo público) e que nenhuma abre dado de pessoa. Também travam o
efeito de hoje: sem a prontidão das tabelas (D10), nenhum campo sai ainda.
"""

import dataclasses
from datetime import date

from base import prontidao
from base.arquivo.destinos import DESTINOS
from base.dicionario import TABELAS
from base.dossie import COLUNAS_DE_PESSOA
from base.prontidao import Prontidao, Prova, prova_publicavel
from base.raio_x_de_fundo import CADASTRO, CAMPOS_DO_CADASTRO
from src import portao_externo as portao
from src.banco.coletas import Marca, marca_da_fonte
from src.portao_externo import (
    DIREITOS_DA_API_EXTERNA,
    NUNCA_SAEM,
    PALAVRAS_QUE_NUNCA_SAEM,
    Canal,
    Categoria,
    Finalidade,
    LinhaDeDireito,
    Motivo,
    Pedido,
)

# "companies" entra com a rota dele (PR 4), que tira MEI e empresário individual linha a linha
CONJUNTOS_DO_BETA = {"financials", "funds"}
# o custo da taxa do raio-x do fundo (`base/raio_x_de_fundo.py`, `_custo`): conta nossa sobre o cadastro
CAMPOS_DO_CUSTO = {"sem_taxa", "com_taxa", "ficou_com_a_taxa", "fracao_do_resultado"}
DEPOIS_DO_COMECO = date(2026, 11, 10)


def _pedido(linha: LinhaDeDireito) -> Pedido:
    return Pedido(
        linha.fonte, linha.conjunto, linha.campo, linha.canal, linha.finalidade
    )


def _regras_prontas(dia: date) -> portao.Regras:
    """As regras de hoje, só com cada tabela do beta pronta no `dia`."""
    prova = Prova(dia, "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    tabelas = {tabela for linha in DIREITOS_DA_API_EXTERNA for tabela in linha.tabelas}
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


def _da_familia(fonte: str, familia: str) -> bool:
    return fonte == familia or fonte.startswith(f"{familia}-")


def test_o_beta_tem_os_tres_conjuntos():
    assert {linha.conjunto for linha in DIREITOS_DA_API_EXTERNA} == CONJUNTOS_DO_BETA


def test_toda_linha_e_fato_de_empresa_para_analise_na_api_externa():
    for linha in DIREITOS_DA_API_EXTERNA:
        assert linha.canal is Canal.API_EXTERNA, linha
        assert linha.finalidade is Finalidade.ANALISE, linha
        assert linha.categoria is Categoria.FATO_DE_PJ, linha
        assert linha.categoria not in NUNCA_SAEM, linha
        assert linha.vigente_ate is None, linha


def test_toda_prova_pode_ir_para_o_catalogo_publico():
    for linha in DIREITOS_DA_API_EXTERNA:
        assert prova_publicavel(linha.prova), linha


def test_nenhuma_linha_se_repete():
    chaves = [linha[:5] for linha in DIREITOS_DA_API_EXTERNA]
    assert len(chaves) == len(set(chaves))


def test_toda_tabela_existe_e_nao_guarda_dado_de_pessoa():
    for linha in DIREITOS_DA_API_EXTERNA:
        assert linha.tabelas, linha
        for tabela in linha.tabelas:
            assert tabela in TABELAS, (linha, tabela)
            assert not TABELAS[tabela].pessoa, (linha, tabela)


def test_a_fonte_e_o_arquivo_do_acervo_que_alimenta_a_tabela():
    for linha in DIREITOS_DA_API_EXTERNA:
        assert linha.fonte in DESTINOS, linha
        for tabela in linha.tabelas:
            assert tabela in DESTINOS[linha.fonte].tabelas, (linha, tabela)
            assert _da_familia(linha.fonte, TABELAS[tabela].familia_da_fonte), linha


def test_todo_campo_existe_na_tabela_ou_no_raio_x_do_cadastro_do_fundo():
    do_raio_x = set(CAMPOS_DO_CADASTRO.values()) | CAMPOS_DO_CUSTO
    for linha in DIREITOS_DA_API_EXTERNA:
        colunas = {c for tabela in linha.tabelas for c in TABELAS[tabela].colunas}
        if linha.tabelas == (CADASTRO,):
            colunas |= do_raio_x
        assert linha.campo in colunas, linha


def test_nenhuma_tabela_do_cnpj_tem_direito_sem_a_rota_que_tira_quem_e_pessoa():
    # ADR 0106: MEI e empresário individual estão nas tabelas do CNPJ; o corte é por linha, na rota
    for linha in DIREITOS_DA_API_EXTERNA:
        assert not _da_familia(linha.fonte, "rfb"), linha
        assert not any(tabela.startswith("cnpj_") for tabela in linha.tabelas), linha


def test_nenhum_campo_de_pessoa_tem_direito():
    for linha in DIREITOS_DA_API_EXTERNA:
        partes = set(linha.campo.lower().split("_"))
        assert not partes & PALAVRAS_QUE_NUNCA_SAEM, linha
        assert not partes & COLUNAS_DE_PESSOA, linha
        assert linha.campo not in COLUNAS_DE_PESSOA, linha


def test_toda_fonte_do_beta_e_vendavel():
    for fonte in {linha.fonte for linha in DIREITOS_DA_API_EXTERNA}:
        assert marca_da_fonte(fonte) is Marca.VENDAVEL, fonte


def test_hoje_nenhum_campo_sai_sem_a_prontidao_das_tabelas():
    # D10: as linhas existem, mas a tabela só sai com as provas 6, 7 e 8 em `base/prontidao.py`
    for linha in DIREITOS_DA_API_EXTERNA:
        decisao = portao.decidir(_pedido(linha), DEPOIS_DO_COMECO)
        assert decisao.motivo is Motivo.SEM_PRONTIDAO, linha
        assert portao.codigo_publico(decisao) == "not_available"


def test_com_as_tabelas_prontas_todo_campo_do_beta_sai():
    regras = _regras_prontas(DEPOIS_DO_COMECO)
    for linha in DIREITOS_DA_API_EXTERNA:
        decisao = portao.decidir(_pedido(linha), DEPOIS_DO_COMECO, regras)
        assert decisao.libera, (linha, decisao.motivo)


def test_prova_de_prontidao_vencida_nega_com_o_codigo_de_sempre():
    vencida = date(2026, 7, 1)  # mais de 90 dias antes da consulta
    regras = _regras_prontas(vencida)
    for linha in DIREITOS_DA_API_EXTERNA:
        decisao = portao.decidir(_pedido(linha), DEPOIS_DO_COMECO, regras)
        assert decisao.motivo is Motivo.PRONTIDAO_VENCIDA, linha
        assert portao.codigo_publico(decisao) == "not_available"
