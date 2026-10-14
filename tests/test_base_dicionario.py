"""Dicionário de dados da base de ML (série 1, PR 8; ADR 0027, exigência 8): toda coluna de toda
tabela tem descrição e unidade, e toda tabela tem fonte, licença, frequência e atraso de
divulgação. O documento para o Tiago revisar é gerado daqui e precisa estar em dia."""

from pathlib import Path

import pandas as pd

from base import cda, fca, ligacoes
from base.cadastro import ler_cadastro, tickers_no_tempo
from base.dicionario import ARQUIVO_DO_DOCUMENTO, TABELAS, documento_em_markdown
from base.ponto_no_tempo import COLUNAS_DA_BASE
from src.banco.coletas import (
    LICENCAS,
    REVENDA,
    SEM_LICENCA_CONHECIDA,
    SO_USO_INTERNO,
    licenca_da_fonte,
    revenda_da_fonte,
)
from src.banco.modelo import (
    achados_de_qualidade,
    fre_eventos_de_capital,
    fre_proventos,
    padroes_setoriais,
)
from src.padroes import MULTIPLOS

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DO_FCA = RAIZ / "tests" / "arquivos" / "cvm" / "fca"
# as tabelas da série 3 da base de ML (fundos e crédito), com a função ou a carga que as grava
SERIE_3 = (
    "valores_mobiliarios", "emissores", "tickers_no_tempo", "codigos_invalidos",
    "codigos_fora_do_fca", "emissores_antigos", "carteiras_dos_fundos", "painel_dos_fundos",
    "cobertura_dos_fundos", "buracos_dos_fundos", "fidc_informe", "cadastro_de_fundos",
    "ifdata_valores", "ifdata_cadastro", "ligacao_dos_bancos", "scr_credito",
)  # fmt: skip


def _tickers_e_emissores_da_carga() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Como a `carga_fca` grava (série 3, PR 8: com a tabela de códigos conferidos e a origem)."""
    zips = [p.read_bytes() for p in sorted(PASTA_DO_FCA.glob("*.zip"))]
    valores = pd.concat(
        [fca.ler_valores_mobiliarios(z) for z in zips], ignore_index=True
    )
    return fca.com_codigos_conferidos(
        tickers_no_tempo(zips), fca.emissores(valores), fca.codigos_conferidos()
    )


def _colunas_de_verdade() -> dict[str, list[str]]:
    cadastro = ler_cadastro(b"CNPJ_CIA;DENOM_SOCIAL;SIT\n1;A;ATIVO\n")
    tickers, emissores = _tickers_e_emissores_da_carga()
    return {
        "demonstracoes_como_era": list(COLUNAS_DA_BASE),
        "achados_de_qualidade": [c.name for c in achados_de_qualidade.columns],
        "cadastro_das_companhias": list(cadastro.columns),
        "tickers_no_tempo": list(tickers.columns),
        "valores_mobiliarios": list(fca.COLUNAS),
        "carteiras_dos_fundos": [*cda.COLUNAS, "disponivel_em"],
        "emissores": list(emissores.columns),
        "codigos_fora_do_fca": list(fca.codigos_conferidos().columns),
        "emissores_antigos": list(ligacoes.tabela_conferida().columns),
        "codigos_invalidos": [
            "cnpj",
            "empresa",
            "referencia",
            "valor_mobiliario",
            "codigo_informado",
        ],
        **{
            t.name: [c.name for c in t.columns]
            for t in (padroes_setoriais, fre_proventos, fre_eventos_de_capital)
        },
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


def test_dicionario_cobre_padroes_e_fre():
    """Série 2 da base de ML, PR 8: as tabelas novas entram com todas as colunas."""
    for nome in ("padroes_setoriais", "fre_proventos", "fre_eventos_de_capital"):
        assert nome in TABELAS, nome


def test_toda_tabela_diz_se_pode_ser_revendida_e_a_linhagem():
    """ADR 0055, exigências 11 (revenda) e 13 (linhagem até o original)."""
    for nome, tabela in TABELAS.items():
        assert revenda_da_fonte(tabela.familia_da_fonte) in REVENDA.values(), nome
        assert tabela.linhagem, f"{nome}: falta a linhagem"
        assert f"**Revenda:** {revenda_da_fonte(tabela.familia_da_fonte)}" in (
            documento_em_markdown()
        )


def test_toda_fonte_com_licenca_tem_resposta_sobre_revenda():
    assert set(REVENDA) == set(LICENCAS)


def test_fonte_sem_licenca_de_dados_nunca_e_vendavel():
    """Yahoo e corretoras de cripto sem termo de dados (ADRs 0008 e 0045): só uso interno."""
    for familia in ("yahoo", "kraken", "mb"):
        assert revenda_da_fonte(familia) == SO_USO_INTERNO
    assert revenda_da_fonte("desconhecida") == SO_USO_INTERNO


def test_padroes_avisam_que_os_multiplos_usam_o_preco_do_yahoo():
    """Os múltiplos dos padrões levam o preço do Yahoo: só uso interno, nunca vender (plano da
    série 2, nota da ADR 0055)."""
    ressalva = TABELAS["padroes_setoriais"].ressalva_de_revenda
    assert SO_USO_INTERNO in ressalva
    for multiplo in MULTIPLOS:
        assert f"`{multiplo}`" in ressalva


def test_documento_do_dicionario_esta_em_dia():
    """Mudou o dicionário? Rode `python -m base.dicionario`."""
    atual = (RAIZ / ARQUIVO_DO_DOCUMENTO).read_text(encoding="utf-8")
    assert atual == documento_em_markdown()


def test_base_como_era_na_data_guarda_a_versao_do_codigo():
    """Exigência 13 da ADR 0055: a linhagem da base diz qual commit a montou."""
    linhagem = TABELAS["demonstracoes_como_era"].linhagem
    assert "versao_do_codigo" in linhagem and "ainda não é guardada" not in linhagem


def test_fidc_e_cadastro_de_fundos_dizem_o_que_fica_fora_por_lgpd():
    """Série 3, PR 6: as tabelas do Capital dizem, no dicionário, o dado pessoal que não entra."""
    assert "CPF vira vazio" in TABELAS["fidc_informe"].descricao
    assert "diretor" in TABELAS["cadastro_de_fundos"].descricao


def test_painel_dos_fundos_cobre_as_colunas_dos_dois_paineis():
    """Série 3, PR 5: as colunas do painel por emissor e por empresa estão no dicionário."""
    from base import ligacoes
    from tests.test_base_ligacoes import _ligacao, _posicoes

    colunas = set(ligacoes.painel_por_emissor(_posicoes()).columns) | set(
        ligacoes.painel_por_empresa(_posicoes(), _ligacao()).columns
    )
    assert colunas == set(TABELAS["painel_dos_fundos"].colunas)


def test_tabelas_do_banco_central_cobrem_as_colunas_dos_leitores():
    """Série 3, PR 7: IF.data, ligação dos bancos e SCR.data, conferidos com as amostras reais."""
    from base import bcb_ifdata, bcb_scr
    from tests.test_base_bcb import _empresas_e_tickers, _ifdata, _scr

    cadastro = bcb_ifdata.ler_cadastro(_ifdata("cadastro_202506.json"))
    colunas = {
        "ifdata_valores": [
            *bcb_ifdata.ler_valores(_ifdata("valores_202506_t1_r1.json")).columns,
            "disponivel_em",
        ],
        "ifdata_cadastro": list(cadastro.columns),
        "ligacao_dos_bancos": list(
            bcb_ifdata.ligacao_dos_bancos(cadastro, *_empresas_e_tickers()).columns
        ),
        "scr_credito": [
            *bcb_scr.ler_ano(_scr("scrdata_2012.zip")).columns,
            "disponivel_em",
        ],
    }
    for tabela, esperadas in colunas.items():
        assert set(TABELAS[tabela].colunas) == set(esperadas), tabela


def test_dicionario_cobre_as_tabelas_da_serie_3():
    """Série 3, PR 8 (ADR 0027, exigência 8; ADR 0055, 11 e 13): cada tabela nova tem colunas com
    unidade, frequência, atraso, fonte, licença, revenda e a linhagem com a versão do código."""
    documento = documento_em_markdown()
    for nome in SERIE_3:
        tabela = TABELAS[nome]
        assert tabela.colunas, f"{nome}: sem colunas"
        for coluna, (descricao, unidade) in tabela.colunas.items():
            assert descricao and unidade, f"{nome}.{coluna}"
        for campo in ("descricao", "fonte", "frequencia", "atraso", "onde", "linhagem"):
            assert getattr(tabela, campo), f"{nome}: falta {campo}"
        assert licenca_da_fonte(tabela.familia_da_fonte) != SEM_LICENCA_CONHECIDA, nome
        assert revenda_da_fonte(tabela.familia_da_fonte) in REVENDA.values(), nome
        assert "ainda não é guardada" not in tabela.linhagem, nome
        assert "versão do código" in tabela.linhagem or "SHA-256" in tabela.linhagem, (
            nome
        )
        assert f"## `{nome}`" in documento, nome


def test_cobertura_e_buracos_dos_fundos_cobrem_as_colunas():
    from tests.test_base_ligacoes import _ligacao, _posicoes

    assert set(ligacoes.cobertura(_posicoes(), _ligacao()).columns) == set(
        TABELAS["cobertura_dos_fundos"].colunas
    )
    assert set(ligacoes.buracos(_posicoes(), _ligacao()).columns) == set(
        TABELAS["buracos_dos_fundos"].colunas
    )


def test_cadastro_de_fundos_diz_como_fica_o_gestor_pessoa_fisica():
    """LGPD: o dicionário diz que o documento e o nome do gestor PF ficam vazios."""
    colunas = TABELAS["cadastro_de_fundos"].colunas
    assert "pessoa física" in colunas["CPF_CNPJ_GESTOR"][0]
    assert "pessoa física" in colunas["GESTOR"][0]
    assert "DIRETOR" not in colunas


def test_tabelas_da_serie_b_cobrem_as_colunas_gravadas():
    """B13, parte 2: as tabelas da base histórica (servidor de casa) entram no dicionário. Onde o
    código não tem a lista de colunas numa constante, a lista é a das tabelas reais montadas em
    14/10/2026 (esquema lido dos Parquets)."""
    from base import auditores, controladas, empresa_serie, fre, rotulos
    from src.negociacoes import COLUNAS as COLUNAS_DAS_NEGOCIACOES

    origem = ["origem_sha256", "origem_coletada_em", "montado_em", "versao_do_codigo"]
    da_historica = ["ano_do_arquivo", *origem]
    eventos = [
        "protocolo", "versao", "cnpj", "empresa", "categoria", "tipo", "assunto", "rotulo",
        "tema", "materialidade", "referencia", "publicado_em", "link",
    ]  # fmt: skip
    situacao = [
        "cnpj", "cnpj_basico", "matriz", "situacao_especial", "rotulo",
        "data_situacao_especial", "mes_do_retrato",
    ]  # fmt: skip
    curva = [
        "data_base", "curva", "prazo_anos", "taxa", "titulos", "maior_prazo_anos",
        "disponivel_em",
    ]  # fmt: skip
    esperadas = {
        "eventos": [*eventos, *da_historica],
        "negociacoes": [*COLUNAS_DAS_NEGOCIACOES, *da_historica],
        "proventos": [*fre.COLUNAS_DOS_PROVENTOS, *da_historica],
        "eventos_de_capital": [*fre.COLUNAS_DOS_EVENTOS, *da_historica],
        "insolvencia": [*rotulos.COLUNAS, *da_historica],
        "cnpj_situacao_especial": [*situacao, *origem],
        "auditores": [*auditores.COLUNAS, *da_historica],
        "trocas_de_auditor": [
            *auditores.COLUNAS_DAS_TROCAS,
            "montado_em",
            "versao_do_codigo",
        ],
        "curva_juros": [*curva, *origem],
        "controladas": [*controladas.COLUNAS, *da_historica],
        "empresa_serie": [*empresa_serie.COLUNAS, "montado_em", "versao_do_codigo"],
    }
    for tabela, colunas in esperadas.items():
        assert set(TABELAS[tabela].colunas) == set(colunas), tabela
        # exigência 13 da ADR 0055: toda linha da série B diz o commit que a montou
        assert "versao_do_codigo" in TABELAS[tabela].linhagem, tabela
        assert "ainda não é guardada" not in TABELAS[tabela].linhagem, tabela
    assert "Comex Stat a confirmar" in TABELAS["empresa_serie"].ressalva_de_revenda
