"""Dicionário de dados da base de ML (série 1, PR 8; ADR 0027, exigência 8): toda coluna de toda
tabela tem descrição e unidade, e toda tabela tem fonte, licença, frequência e atraso de
divulgação. O documento para o Tiago revisar é gerado daqui e precisa estar em dia."""

from pathlib import Path

from base import cda, fca
from base.cadastro import COLUNAS_DOS_TICKERS, ler_cadastro
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


def _colunas_de_verdade() -> dict[str, list[str]]:
    cadastro = ler_cadastro(b"CNPJ_CIA;DENOM_SOCIAL;SIT\n1;A;ATIVO\n")
    return {
        "demonstracoes_como_era": list(COLUNAS_DA_BASE),
        "achados_de_qualidade": [c.name for c in achados_de_qualidade.columns],
        "cadastro_das_companhias": list(cadastro.columns),
        "tickers_no_tempo": list(COLUNAS_DOS_TICKERS),
        "valores_mobiliarios": list(fca.COLUNAS),
        "carteiras_dos_fundos": [*cda.COLUNAS, "disponivel_em"],
        "emissores": [
            "emissor",
            "cnpj",
            "empresa",
            "primeiro_ano",
            "ultimo_ano",
            "conflito",
        ],
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
