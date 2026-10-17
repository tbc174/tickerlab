"""Critério de pronto das fontes e tabelas do modelo 8 (atraso na entrega da DFP/ITR; ADR 0060).

ADR 0027, Emenda 1 (16/10/2026): um modelo só é testado com dado real quando **cada fonte e cada
tabela que ele usa** passam nas exigências 1 a 9, 11 e 13 (a 12 é da base inteira; a 10, o período
lacrado, vai no pré-registro). Este é o teste que o pré-registro do modelo 8 aponta. Cada exigência de
cada fonte fica num de três lugares:

- **provada:** pela conferência automática (1, 2, 3, 8 e 11, como nas séries 3 e 4) e pelos testes
  de `PROVAS`, que precisam continuar existindo (se um sumir, este falha);
- **não se aplica:** em `NAO_SE_APLICA`, com o motivo;
- **pendente:** em `PENDENCIAS`, com o motivo e o PR que resolve (A a D do placar da mesa Dados, ou
  o PR do plano do modelo 8).

Diferente das séries 3 e 4, aqui as exigências 4 (sobrevivência), 5 (eventos), 6 (conferência
cruzada) e 7 (qualidade automática) também precisam de prova. A Fase 1 só começa com `PENDENCIAS`
vazio: `test_modelo_8_pronto_para_a_fase_1` falha de propósito até lá.
"""

import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

from base import historico
from base.arquivo.fontes import PASTAS_DA_CVM
from base.cadastro import FONTE_DO_CADASTRO
from base.dicionario import TABELAS
from base.modelos.atraso import rotulo
from scripts import montar_base_como_era
from src import demonstracoes
from src.banco.coletas import (
    PODEM_ENTRAR,
    REVENDA,
    SEM_LICENCA_CONHECIDA,
    licenca_da_fonte,
    marca_da_fonte,
    revenda_da_fonte,
)

RAIZ = Path(__file__).resolve().parent.parent
DOMINIOS_OFICIAIS = {"dados.cvm.gov.br"}
EXIGENCIAS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 13)

DFP_ITR = "CVM DFP e ITR"
CADASTRO = "CVM cadastro de companhias"
FCA = "CVM FCA (auditores)"
IPE = "CVM IPE"
PRAZOS = "Prazos da CVM (normas)"

# fonte → registro de coletas, endereços e tabelas do dicionário com a coluna de "como era na data"
FONTES = {
    DFP_ITR: {
        "fontes_no_registro": [
            *rotulo.FONTES_DO_INDICE.values(),
            montar_base_como_era.FONTE,
        ],
        "enderecos": [demonstracoes.URL_DO_DFP, demonstracoes.URL_DO_ITR],
        "tabelas": {
            "rotulos_atraso": "primeira_entrega",
            "demonstracoes_como_era": "divulgado_em",
        },
    },
    CADASTRO: {
        "fontes_no_registro": [FONTE_DO_CADASTRO],
        "enderecos": [demonstracoes.URL_DO_CADASTRO],
        "tabelas": {"cadastro_das_companhias": "registro"},
    },
    FCA: {
        "fontes_no_registro": [historico.TABELAS["auditores"].fonte],
        "enderecos": [f"{PASTAS_DA_CVM}CIA_ABERTA/DOC/FCA/DADOS/"],
        "tabelas": {"auditores": "conhecido_em", "trocas_de_auditor": "conhecido_em"},
    },
    IPE: {
        "fontes_no_registro": [
            historico.TABELAS["insolvencia"].fonte,
            historico.TABELAS["eventos"].fonte,
        ],
        "enderecos": [f"{PASTAS_DA_CVM}CIA_ABERTA/DOC/IPE/DADOS/"],
        "tabelas": {"insolvencia": "conhecido_em", "eventos": "publicado_em"},
    },
    # não é dado coletado: o prazo legal sai de `src/prazos.py` e `base/dias_uteis.py`
    PRAZOS: {"fontes_no_registro": [], "enderecos": [], "tabelas": {}},
}

# fora da v1 do modelo 8 (entrar depois = pré-registro novo, Emenda 1, item 4)
FORA_DA_V1 = {
    "achados_de_qualidade": (
        "selo R1 a R11: a R8 repete o histórico de entregas e a tabela fica no banco do app, sem "
        "versão do código por linha (decisão do Tiago, 16/10/2026)"
    ),
}

PONTO = "tests/test_base_ponto_no_tempo.py"
COMO_ERA = "tests/test_montar_base_como_era.py"
ROTULO = "tests/test_base_rotulo_atraso.py"
ROTULO_ACERVO = "tests/test_base_rotulo_atraso_acervo.py"
CADASTRO_T = "tests/test_base_cadastro.py"
AUDITORES = "tests/test_base_auditores.py"
ROTULOS_IPE = "tests/test_base_rotulos.py"
HISTORICO = "tests/test_base_historico.py"
LINHAGEM = "tests/test_linhagem.py"
PRAZOS_T = "tests/test_prazos.py"
CANCELADAS = "tests/test_conferir_canceladas.py"
MONTAGEM = "tests/test_montar_modelo_8.py"
QUALIDADE = "tests/test_qualidade_da_montagem.py"
# montagem semanal no servidor de casa com relatório de qualidade e aviso no Kuma (PR D)
MONTAGEM_COM_ALERTA = [
    f"{MONTAGEM}::test_ano_que_some_ou_escala_que_muda_faz_a_montagem_falhar",
    f"{MONTAGEM}::test_tabela_sem_arquivo_faz_a_montagem_falhar",
    f"{MONTAGEM}::test_monta_na_ordem_e_falha_quando_um_original_nao_abre",
    f"{QUALIDADE}::test_primeira_montagem_so_confere_o_que_nao_depende_da_anterior",
]
CRUZADA = "tests/test_conferencia_cruzada_modelo_8.py"  # tolerâncias em docs/conferencia-cruzada-modelo-8.md
# conferência medida das canceladas (rodada no servidor de casa em 16/10/2026: 0 perdidas)
CONFERENCIA_DAS_CANCELADAS = [
    f"{CADASTRO_T}::test_conferencia_separa_falta_da_fonte_de_empresa_perdida_na_montagem",
    f"{CANCELADAS}::test_cancelada_que_a_fonte_tem_e_a_base_nao_faz_a_conferencia_falhar",
    f"{CANCELADAS}::test_cada_falta_explicada_a_mao_tem_motivo_e_data",
]

PROVAS: dict[tuple[str, int], list[str]] = {
    (DFP_ITR, 3): [
        f"{PONTO}::test_como_era_em_31_12_2020_nao_tem_nada_divulgado_depois",
        f"{PONTO}::test_entrega_fora_do_registro_vale_a_partir_do_registro_seguinte",
        f"{ROTULO}::test_entrega_depois_de_hoje_ainda_nao_existia",
        f"{ROTULO}::test_documento_com_prazo_antes_do_registro_nao_e_exemplo",
        # só é exemplo o que a empresa devia (conferência da data de entrega, 15 e 16/10)
        f"{ROTULO}::test_documento_com_prazo_entre_dois_registros_nao_e_exemplo",
        f"{ROTULO}::test_documento_com_prazo_depois_do_cancelamento_nao_e_exemplo",
        f"{ROTULO}::test_empresa_fora_do_cadastro_nao_e_exemplo",
    ],
    (DFP_ITR, 4): [
        f"{ROTULO}::test_empresa_cancelada_continua_nos_anos_ativos",
        *CONFERENCIA_DAS_CANCELADAS,
    ],
    # contas da base "como era" e rótulo contra o ENET, com as tolerâncias escritas antes (PR C)
    (DFP_ITR, 6): [
        f"{CRUZADA}::test_contas_da_base_como_era_conferem_com_o_documento_no_enet",
        f"{CRUZADA}::test_rotulo_confere_com_o_envio_no_enet",
    ],
    (DFP_ITR, 7): MONTAGEM_COM_ALERTA,
    (DFP_ITR, 9): [
        f"{PONTO}::test_refazer_a_base_dos_originais_da_os_mesmos_hashes",
        f"{COMO_ERA}::test_montar_de_novo_da_o_mesmo_hash_e_conferir_confirma",
        f"{ROTULO_ACERVO}::test_mesmos_originais_e_mesmo_dia_dao_o_mesmo_hash",
    ],
    (DFP_ITR, 13): [
        f"{COMO_ERA}::test_manifesto_leva_a_versao_do_codigo",
        f"{ROTULO_ACERVO}::test_monta_o_rotulo_dos_originais_com_manifesto",
        f"{LINHAGEM}::test_linha_sorteada_volta_ao_original",
    ],
    (CADASTRO, 3): [f"{ROTULO}::test_registrada_depois_do_prazo_nao_deve_o_documento"],
    (CADASTRO, 4): [
        f"{CADASTRO_T}::test_canceladas_com_data_e_motivo",
        f"{CADASTRO_T}::test_cobertura_das_canceladas_mostra_quem_saiu_e_falta_na_base",
    ],
    # o cadastro não é gravado sozinho: entra nas origens do manifesto de quem o usa
    (CADASTRO, 6): [
        f"{CRUZADA}::test_registro_e_cancelamento_conferem_com_a_consulta_da_cvm"
    ],
    # sem o cadastro no acervo, o rótulo não é montado e a montagem falha (o arquivista coleta todo dia)
    (CADASTRO, 7): [
        *MONTAGEM_COM_ALERTA,
        f"{ROTULO_ACERVO}::test_sem_originais_nada_e_gravado",
    ],
    (CADASTRO, 9): [
        f"{COMO_ERA}::test_montar_de_novo_da_o_mesmo_hash_e_conferir_confirma"
    ],
    (CADASTRO, 13): [
        f"{ROTULO_ACERVO}::test_monta_o_rotulo_dos_originais_com_manifesto",
        f"{COMO_ERA}::test_manifesto_leva_a_versao_do_codigo",
    ],
    (FCA, 3): [
        f"{AUDITORES}::test_mandato_leva_a_data_em_que_a_cvm_recebeu_o_documento",
        f"{AUDITORES}::test_trocas_conhecidas_ate_uma_data_nao_dependem_do_futuro",
        f"{AUDITORES}::test_fca_antigo_reapresentado_depois_do_novo_nao_desfaz_a_troca",
        # o FCA do pedido de registro vale a partir do registro (60 páginas do ENET, 16/10)
        f"{AUDITORES}::test_fca_do_pedido_de_registro_vale_a_partir_do_registro",
        f"{AUDITORES}::test_no_fca_do_pedido_de_registro_o_registro_seguinte_nunca_e_cedo_demais",
    ],
    (FCA, 4): CONFERENCIA_DAS_CANCELADAS,
    (FCA, 6): [f"{CRUZADA}::test_auditor_da_tabela_e_quem_assina_o_relatorio_da_dfp"],
    (FCA, 7): MONTAGEM_COM_ALERTA,
    (FCA, 9): [
        f"{HISTORICO}::test_remontar_com_o_mesmo_dado_nao_regrava_nem_cria_versao",
        f"{AUDITORES}::test_trocas_saem_dos_anos_de_auditores_gravados_na_base",
    ],
    (FCA, 13): [
        f"{AUDITORES}::test_auditores_entram_na_base_historica",
        f"{LINHAGEM}::test_linha_sorteada_volta_ao_original",
    ],
    (IPE, 3): [
        f"{ROTULOS_IPE}::test_primeira_data_por_empresa_e_rotulo",
        f"{HISTORICO}::test_eventos_do_ipe_saem_num_parquet_por_ano_com_a_origem",
    ],
    (IPE, 4): CONFERENCIA_DAS_CANCELADAS,
    (IPE, 7): MONTAGEM_COM_ALERTA,
    (IPE, 9): [
        f"{HISTORICO}::test_remontar_com_o_mesmo_dado_nao_regrava_nem_cria_versao"
    ],
    (IPE, 13): [
        f"{HISTORICO}::test_eventos_do_ipe_saem_num_parquet_por_ano_com_a_origem",
        f"{ROTULOS_IPE}::test_rotulos_entram_na_base_historica",
    ],
    (PRAZOS, 3): [
        f"{PRAZOS_T}::test_prazo_cai_em_dia_util_e_nunca_antes_do_normal",
        f"{PRAZOS_T}::test_dfp_prorrogada_na_pandemia",
    ],
    # normas lidas nos PDFs oficiais e conferidas com datas conhecidas de entrega
    (PRAZOS, 6): [
        f"{PRAZOS_T}::test_prazo_pula_feriado_nacional",
        f"{PRAZOS_T}::test_itr_prorrogado_na_pandemia",
        f"{PRAZOS_T}::test_itr_prorrogado_no_rio_grande_do_sul_em_2024",
        f"{PRAZOS_T}::test_dfp_do_emissor_estrangeiro_tem_4_meses",
        f"{CRUZADA}::test_prorrogacoes_de_2022_a_2026_estao_no_codigo_e_nas_entregas",
    ],
    (PRAZOS, 9): [f"{PRAZOS_T}::test_prazo_cai_em_dia_util_e_nunca_antes_do_normal"],
    # a versão do código que calculou o prazo vai no manifesto do rótulo
    (PRAZOS, 13): [f"{ROTULO_ACERVO}::test_monta_o_rotulo_dos_originais_com_manifesto"],
}

SEM_PRECO = (
    "o modelo 8 não usa preço nem quantidade de ações: desdobramentos, dividendos e trocas de "
    "ticker não mexem em nada dele; empresa que muda de CNPJ começa sem histórico de entregas, "
    "como a CVM a trata (limite declarado no pré-registro)"
)
NAO_SE_APLICA: dict[tuple[str, int], str] = {
    **{(fonte, 5): SEM_PRECO for fonte in FONTES},
    (PRAZOS, 1): "atos oficiais não têm proteção autoral (Lei 9.610/98, art. 8º, IV)",
    (PRAZOS, 11): "atos oficiais não têm proteção autoral (Lei 9.610/98, art. 8º, IV)",
    (
        PRAZOS,
        2,
    ): "não é dado coletado: cada prorrogação está em `src/prazos.py` com a norma citada",
    (PRAZOS, 4): "é regra, não lista de empresas",
    (
        PRAZOS,
        7,
    ): "código determinístico, sem coleta: os testes de `tests/test_prazos.py` o conferem",
    (PRAZOS, 8): (
        "é regra, não tabela: o prazo de cada exemplo está na ficha `rotulos_atraso` "
        "(`test_o_prazo_esta_na_ficha_do_rotulo`)"
    ),
}

PENDENCIAS: dict[tuple[str, int], str] = {
    (DFP_ITR, 8): (
        "a ficha `rotulos_atraso` entrou depois da revisão do dicionário de 14/10 (e mudou no "
        "PR B: quem é exemplo): falta o Tiago ler. PR B"
    ),
    (CADASTRO, 3): (
        "é o retrato de hoje: serve para quem devia o documento e para a UF, não para colunas "
        "(setor e categoria virão do FCA pela data de entrega). Regra e teste no PR 3 do plano"
    ),
    (IPE, 6): (
        "conferência cruzada com a Receita abaixo da tolerância (76% e 55% contra 90%; a recuperação "
        "judicial bate 25 de 25): o rótulo do IPE marca eventos de outras empresas do grupo e a "
        "recuperação extrajudicial, e a Receita não marca casos conhecidos. Proposta para o Tiago "
        "decidir: usar do IPE só a recuperação judicial da própria companhia, corrigida, no PR 3"
    ),
}


def _existe(teste: str) -> bool:
    arquivo, nome = teste.split("::")
    texto = (RAIZ / arquivo).read_text(encoding="utf-8")
    return re.search(rf"^def {nome}\(", texto, re.MULTILINE) is not None


def _conferencia_automatica(fonte: str, exigencia: int) -> bool:
    """Confere o que o código já diz da fonte; devolve se houve o que conferir."""
    dados = FONTES[fonte]
    if exigencia in (1, 11) and dados["fontes_no_registro"]:
        # licença conhecida e resposta sobre revenda, pela família no registro de coletas
        for registro in dados["fontes_no_registro"]:
            assert licenca_da_fonte(registro) != SEM_LICENCA_CONHECIDA, registro
            assert revenda_da_fonte(registro) in REVENDA.values(), registro
            # ADR 0008, Emenda 1: só "vendável" e "só uso interno" entram em modelo
            assert marca_da_fonte(registro) in PODEM_ENTRAR, registro
        return True
    if exigencia == 2 and dados["enderecos"]:
        # domínio oficial e HTTPS; o original vai para o acervo com SHA-256
        for endereco in dados["enderecos"]:
            partes = urlparse(endereco)
            assert partes.scheme == "https", endereco
            assert partes.hostname in DOMINIOS_OFICIAIS, endereco
        return True
    if exigencia == 3 and dados["tabelas"]:
        for tabela, coluna in dados["tabelas"].items():
            assert coluna in TABELAS[tabela].colunas, tabela
        return True
    if exigencia == 8 and dados["tabelas"]:
        for tabela in dados["tabelas"]:
            assert TABELAS[tabela].colunas, tabela
        return True
    return False


@pytest.mark.parametrize(
    ("fonte", "exigencia"), [(f, e) for f in FONTES for e in EXIGENCIAS]
)
def test_criterio_de_pronto_das_fontes_do_modelo_8(fonte, exigencia):
    chave = (fonte, exigencia)
    if chave in NAO_SE_APLICA:
        assert chave not in PROVAS and chave not in PENDENCIAS, chave
        return
    automatica = _conferencia_automatica(fonte, exigencia)
    for prova in PROVAS.get(chave, []):
        assert _existe(prova), prova
    assert automatica or chave in PROVAS or chave in PENDENCIAS, (
        f"{fonte}, exigência {exigencia}: sem prova, sem pendência e sem motivo para não se aplicar"
    )


def test_listas_so_falam_de_fontes_e_exigencias_do_modelo():
    for fonte, exigencia in [*PROVAS, *NAO_SE_APLICA, *PENDENCIAS]:
        assert fonte in FONTES and exigencia in EXIGENCIAS, (fonte, exigencia)


def test_toda_pendencia_diz_o_pr_que_a_resolve():
    for chave, motivo in PENDENCIAS.items():
        assert re.search(r"\bPR (?:[A-D]|\d)\b", motivo), chave


def test_o_que_ficou_fora_da_v1_nao_entra_pelas_fontes():
    tabelas = {t for dados in FONTES.values() for t in dados["tabelas"]}
    assert not tabelas & set(FORA_DA_V1)


def test_o_prazo_esta_na_ficha_do_rotulo():
    colunas = TABELAS["rotulos_atraso"].colunas
    assert {"prazo", "dias_uteis_de_atraso", "zona_cinzenta"} <= set(colunas)


@pytest.mark.xfail(
    strict=True,
    reason="ADR 0027, Emenda 1: o modelo 8 só começa a Fase 1 sem pendências (PRs B a D)",
)
def test_modelo_8_pronto_para_a_fase_1():
    assert not PENDENCIAS
