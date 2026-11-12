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
from src.api_externa.conjuntos import (
    comparaveis,
    compradores,
    credito,
    empresas,
    ficha,
    prospeccao,
    setores,
    vinculos,
)
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

# "companies" entra com a rota dele (PR 4), que tira MEI e empresário individual linha a linha; "credit"
# (linha 754, PR 2) é o único de crédito; "sectors" (linha 781) é o único com agregado de mercado;
# "profiles" (linha 736, PR 2) repete o cadastro de "companies" e junta as entregas de DFP e ITR;
# "comparables" (linha 736, PR 3) junta o setor do FCA e os números do DFP dos pares; "events" (linha 736,
# PR 4) lista os documentos do IPE e as trocas de auditor; "links" (linha 736, PR 5) lê a rede de entidades;
# "buyers" (linha 810, PR 4) lista quem já se mexeu num setor, só pessoa jurídica; "assets" (linha 845) lista os
# contratos de exploração e produção da ANP da empresa
CONJUNTOS_DO_BETA = {
    "companies",
    "financials",
    "funds",
    "credit",
    "sectors",
    "profiles",
    "prospecting",
    "comparables",
    "events",
    "links",
    "buyers",
    "assets",
}
FINALIDADE_DO_CONJUNTO = {credito.CONJUNTO: Finalidade.CREDITO}
# o custo da taxa do raio-x do fundo (`base/raio_x_de_fundo.py`, `_custo`): conta nossa sobre o cadastro
CAMPOS_DO_CUSTO = {"sem_taxa", "com_taxa", "ficou_com_a_taxa", "fracao_do_resultado"}
DEPOIS_DO_COMECO = date(2026, 11, 10)
# o setor é uma conta da noite: a série da agência (1ª tabela, a da fonte) ligada às companhias abertas pela
# tabela conferida da CVM; a prontidão confere também a ligação, que não é alimentada pela fonte da série
TABELAS_DA_LIGACAO_DO_SETOR = {"empresa_serie", "cadastro_das_companhias"}
# fonte com carga própria, fora do arquivista (`DESTINOS` só tem as dele): a tabela que ela alimenta, cuja
# linhagem no dicionário cita a fonte (`scripts/carga_bcb_credito.py`, o IF.data pela API do BC)
FONTES_DE_CARGA_PROPRIA = {"bcb-ifdata": "ifdata_valores"}
# fonte com carga própria cuja tabela diz o script no `onde` (o registro de fundos da CVM 175, do FIP do `buyers`)
CARGA_PROPRIA_PELO_SCRIPT = {
    "cvm-fidc-base": ("registro_de_fundos", "scripts/carga_fidc.py")
}
# tabela montada na base a partir de outra que a fonte alimenta (as trocas de auditor saem dos auditores de
# cada FCA, `base/auditores.py`): a de origem é a que está nos destinos do arquivista
MONTADAS_DE_OUTRA_TABELA = {
    "trocas_de_auditor": "auditores",
    # as entradas de sócio PJ saem do quadro de sócios, cortado pelas raízes da lista sem pessoa (linha 810)
    "entradas_de_socio_pj": "cnpj_estabelecimentos_pj",
}
# a rede de entidades (ADR 0077, `base/rede/montar.py`) é montada de várias tabelas; a de cada fonte que sai em
# `links` é a que está nos destinos do arquivista: as controladas do FRE e os auditores do FCA
TABELAS_DA_REDE = {"ligacoes", "entidades", "identificadores"}
ORIGEM_NA_REDE = {"cvm-hist-fre": "controladas", "cvm-hist-fca": "auditores"}
# tabela montada na base histórica com os arquivos anuais da fonte (o manifesto lista cada um), fora dos
# destinos do arquivista: as entregas do perfil saem do índice das entregas da DFP e do ITR
MONTADAS_DOS_ARQUIVOS_DA_FONTE = {
    ficha.TABELA_DAS_ENTREGAS: set(ficha.FONTES_DAS_ENTREGAS.values())
}
CAMPOS_DO_SETOR = {
    *setores.COLUNAS_DA_CONCENTRACAO,
    *setores.COLUNAS_DA_PARTICIPACAO,
    *setores.COLUNAS_DOS_MEMBROS,
}


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


def test_o_beta_tem_os_sete_conjuntos():
    assert {linha.conjunto for linha in DIREITOS_DA_API_EXTERNA} == CONJUNTOS_DO_BETA


def _categoria_esperada(linha: LinhaDeDireito) -> Categoria:
    """Agregado só na concentração do mercado do setor; todo o resto é fato de empresa."""
    do_mercado = (
        linha.conjunto == setores.CONJUNTO
        and linha.fonte != setores.FONTE_DOS_MEMBROS
        and linha.campo in setores.COLUNAS_DA_CONCENTRACAO
    )
    return Categoria.AGREGADO if do_mercado else Categoria.FATO_DE_PJ


def test_toda_linha_e_fato_de_empresa_para_analise_na_api_externa():
    for linha in DIREITOS_DA_API_EXTERNA:
        assert linha.canal is Canal.API_EXTERNA, linha
        esperada = FINALIDADE_DO_CONJUNTO.get(linha.conjunto, Finalidade.ANALISE)
        assert linha.finalidade is esperada, linha
        assert linha.categoria is _categoria_esperada(linha), linha
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
        tabelas = linha.tabelas
        if linha.conjunto == setores.CONJUNTO:
            assert set(tabelas[1:]) <= TABELAS_DA_LIGACAO_DO_SETOR, linha
            tabelas = tabelas[:1]
        for tabela in tabelas:
            if tabela in MONTADAS_DOS_ARQUIVOS_DA_FONTE:
                assert linha.fonte in MONTADAS_DOS_ARQUIVOS_DA_FONTE[tabela], linha
                assert "arquivo anual da DFP e do ITR" in TABELAS[tabela].linhagem, (
                    linha
                )
            elif linha.fonte in CARGA_PROPRIA_PELO_SCRIPT:
                assert (tabela, linha.fonte) == (
                    CARGA_PROPRIA_PELO_SCRIPT[linha.fonte][0],
                    linha.fonte,
                ), linha
                assert (
                    CARGA_PROPRIA_PELO_SCRIPT[linha.fonte][1] in TABELAS[tabela].onde
                ), (linha, tabela)
            elif linha.fonte in FONTES_DE_CARGA_PROPRIA:
                assert tabela == FONTES_DE_CARGA_PROPRIA[linha.fonte], (linha, tabela)
                assert f"`{linha.fonte}`" in TABELAS[tabela].linhagem, (linha, tabela)
            else:
                assert linha.fonte in DESTINOS, linha
                origem = MONTADAS_DE_OUTRA_TABELA.get(tabela, tabela)
                if tabela in TABELAS_DA_REDE:
                    origem = ORIGEM_NA_REDE[linha.fonte]
                assert origem in DESTINOS[linha.fonte].tabelas, (linha, tabela)
            assert _da_familia(linha.fonte, TABELAS[tabela].familia_da_fonte), linha


def test_todo_campo_existe_na_tabela_ou_no_raio_x_do_cadastro_do_fundo():
    do_raio_x = set(CAMPOS_DO_CADASTRO.values()) | CAMPOS_DO_CUSTO
    for linha in DIREITOS_DA_API_EXTERNA:
        if linha.conjunto == credito.CONJUNTO:
            # fato da ficha: conta nossa sobre a tabela (`test_api_externa_credito` confere a origem)
            assert linha.tabelas == (credito.FATOS[linha.campo].tabela,), linha
            continue
        if linha.conjunto == setores.CONJUNTO:
            # coluna da ficha da noite (`test_api_externa_setores` confere que a ficha a traz)
            assert linha.campo in CAMPOS_DO_SETOR, linha
            continue
        colunas = {c for tabela in linha.tabelas for c in TABELAS[tabela].colunas}
        if linha.conjunto == ficha.CONJUNTO and linha.campo == "situacao_da_entrega":
            # conta nossa sobre as colunas booleanas da tabela (`ficha._situacao_entregue`)
            assert set(ficha.COLUNAS_DA_SITUACAO) <= colunas, linha
            continue
        if linha.conjunto == comparaveis.CONJUNTO and linha.campo not in colunas:
            # conta nossa sobre as colunas da tabela: o grupo do setor, o fim do exercício, as somas e razões
            assert set(comparaveis.ORIGEM_DAS_CONTAS[linha.campo]) <= colunas, linha
            continue
        if linha.tabelas == (CADASTRO,):
            colunas |= do_raio_x
        if (linha.tabelas, linha.campo) == (
            (empresas.LISTA_DE_EMPRESAS,),
            empresas.RETRATO_DO_CADASTRO,
        ):
            # o mês do retrato de onde saíram o nome e a natureza (linha 861): é o `mes_do_retrato` da lista PJ
            assert empresas.MES in colunas, linha
            continue
        assert linha.campo in colunas, linha


def test_do_cnpj_so_tem_direito_o_que_a_rota_que_tira_quem_e_pessoa_serve():
    # ADR 0106: MEI e empresário individual estão nas tabelas do CNPJ; o corte é por linha, na rota de
    # `companies` (`conjuntos/empresas.py`): a situação cadastral e o histórico datado (linha 686).
    servidos = {
        empresas.TABELA: empresas.CAMPOS,
        **{historico.tabela: historico.campos for historico in empresas.HISTORICOS},
        # o nome e a natureza do retrato da lista sem pessoa, com o mês (linha 861)
        empresas.LISTA_DE_EMPRESAS: (
            *empresas.CAMPOS_DO_RETRATO_PJ,
            empresas.RETRATO_DO_CADASTRO,
        ),
    }
    # a ficha de crédito tira pessoa com a mesma trava (`empresas.e_empresa`)
    da_ficha = {
        (origem.tabela, chave)
        for chave, origem in credito.FATOS.items()
        if origem.tabela.startswith("cnpj_")
    }
    do_cnpj = [
        linha
        for linha in DIREITOS_DA_API_EXTERNA
        if _da_familia(linha.fonte, "rfb")
        or any(tabela.startswith("cnpj_") for tabela in linha.tabelas)
    ]
    assert do_cnpj
    for linha in do_cnpj:
        (tabela,) = linha.tabelas
        if linha.conjunto == credito.CONJUNTO:
            assert (tabela, linha.campo) in da_ficha, linha
            continue
        if linha.conjunto == prospeccao.CONJUNTO:
            # a busca lê só as duas tabelas montadas sem pessoa (linha 584): o corte é na montagem
            assert tabela in {prospeccao.EMPRESAS, prospeccao.ESTABELECIMENTOS}, linha
            assert linha.campo in prospeccao.CAMPOS, linha
            continue
        if linha.conjunto == compradores.CONJUNTO:
            # a lista de compradores lê o setor e os nomes das duas tabelas sem pessoa (linha 584) e as entradas
            # da tabela de sócios PJ, montada só com raízes dessa lista (linha 810): o corte é na montagem
            assert tabela in {
                compradores.EMPRESAS,
                compradores.ESTABELECIMENTOS,
                compradores.ENTRADAS,
            }, linha
            continue
        if linha.conjunto == vinculos.CONJUNTO:
            # os vínculos leem só a razão social e o mês do retrato, da lista sem pessoa (linha 867), e só da
            # ponta que passou pela trava da rede (MEI e quem a rede trata como pessoa saem antes,
            # `vinculos.LeitorDeVinculos._pontas`); a natureza de pessoa também não dá nome
            assert tabela == empresas.LISTA_DE_EMPRESAS, linha
            assert linha.campo in {vinculos.NOME, empresas.RETRATO_DO_CADASTRO}, linha
            continue
        # o perfil lê o cadastro pelo mesmo leitor de `companies` (`conjuntos/ficha.py`)
        assert linha.conjunto in {empresas.CONJUNTO, ficha.CONJUNTO}, linha
        assert linha.campo in servidos[tabela], linha
    das_empresas = [linha for linha in do_cnpj if linha.conjunto == empresas.CONJUNTO]
    assert {linha.tabelas[0] for linha in das_empresas} == set(empresas.TABELAS)
    for linha in DIREITOS_DA_API_EXTERNA:
        if linha.conjunto == empresas.CONJUNTO:
            assert linha in do_cnpj, linha


def test_o_historico_do_cnpj_so_tem_direito_com_a_data_de_cada_versao():
    # sem olhar o futuro: só sai na API o histórico com `publico_em` por versão, nunca o vigente
    for historico in empresas.HISTORICOS:
        tabela = TABELAS[historico.tabela]
        assert tabela.datas.get("publico_em") == "disponivel_em", historico
        assert "mes_do_retrato" in tabela.chaves, historico


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
