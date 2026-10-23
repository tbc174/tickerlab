"""O direito de resposta (ADR 0103, ponto 9): a frase aprovada pelo Tiago sai ao pé de toda ficha pública
(tela, PDF e deck); a ficha que sair sem ela falha aqui."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src import apresentacao as ap
from src import busca_por_cnpj as busca
from src import dossie
from src import relatorio_empresa as re_
from src import relatorio_setor as rs
from src.apresentacao_pdf import apresentacao_em_pdf
from src.apresentacao_pptx import apresentacao_em_pptx
from src.contestacao import FRASE_DE_CONTESTACAO, com_a_contestacao
from src.relatorio_do_cnpj_pdf import relatorio_do_cnpj
from src.relatorio_empresa_pdf import relatorio_da_empresa
from tests.test_apresentacao import _sem_espacos, _texto_do_pdf, _texto_do_pptx
from tests.test_busca_por_cnpj import HOJE as HOJE_DA_BUSCA
from tests.test_busca_por_cnpj import PETROBRAS, _gravar_ficha
from tests.test_relatorio_empresa import _entradas as entradas_da_empresa
from tests.test_relatorio_empresa import dados_da_weg  # noqa: F401
from tests.test_relatorio_setor import HOJE, gravar_noite
from tests.test_relatorio_setor import _entradas as entradas_do_setor

# o texto aprovado em 19/10/2026 ("pode com esse texto"), palavra por palavra, sem prazo e sem ajuste
TEXTO_APROVADO = (
    "Representa esta empresa e viu um fato errado? Escreva para contato@tickerlab.com.br com o CNPJ e o "
    "fato. A contestação aparece ao lado do fato até a conferência."
)
GERADO_EM = datetime(2026, 10, 22, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
FRASE = _sem_espacos(FRASE_DE_CONTESTACAO)


def test_a_frase_e_exatamente_a_aprovada():
    assert FRASE_DE_CONTESTACAO == TEXTO_APROVADO


def test_a_frase_vai_no_fim_uma_vez_so():
    limites = com_a_contestacao(["a", FRASE_DE_CONTESTACAO, "b"])
    assert limites == ["a", "b", FRASE_DE_CONTESTACAO]


@pytest.mark.parametrize("plano", [None, "gratuito", "pro"])
def test_ficha_da_empresa_termina_com_a_frase_em_qualquer_plano(
    dados_da_weg,  # noqa: F811
    plano,
):
    relatorio = re_.montar(entradas_da_empresa(dados_da_weg), plano)
    assert relatorio.secoes[-1].chave == "limites"
    assert relatorio.secao("limites").paragrafos[-1] == FRASE_DE_CONTESTACAO


def test_ficha_da_empresa_no_pdf_e_no_deck_traz_a_frase(dados_da_weg):  # noqa: F811
    relatorio = re_.montar(entradas_da_empresa(dados_da_weg))
    deck = ap.da_ficha(relatorio, GERADO_EM)
    assert FRASE in _sem_espacos(_texto_do_pdf(apresentacao_em_pdf(deck, GERADO_EM)))
    assert FRASE in _sem_espacos(_texto_do_pptx(apresentacao_em_pptx(deck, GERADO_EM)))
    pdf = relatorio_da_empresa(relatorio, GERADO_EM)
    assert FRASE in _sem_espacos(_texto_do_pdf(pdf))


def test_relatorio_do_setor_traz_a_frase_na_tela_e_no_deck(tmp_path):
    secao = dossie.secao_do_setor("eletricas", gravar_noite(tmp_path))
    assert secao is not None
    relatorio = rs.montar_relatorio_do_setor(entradas_do_setor(secao), "pro", HOJE)
    assert relatorio.limites[-1] == FRASE_DE_CONTESTACAO
    deck = ap.do_setor(relatorio, GERADO_EM)
    assert FRASE in _sem_espacos(_texto_do_pdf(apresentacao_em_pdf(deck, GERADO_EM)))


def test_relatorio_do_cnpj_traz_a_frase_com_ficha_e_sem_ficha(banco, tmp_path):
    from tests.test_fundamentos_no_app import _coletar

    _coletar(banco)
    pasta = _gravar_ficha(tmp_path)
    with banco.connect() as conexao:
        com_ficha = busca.buscar_por_cnpj(
            conexao, PETROBRAS, "pro", HOJE_DA_BUSCA, pasta
        )
        sem_ficha = busca.buscar_por_cnpj(
            conexao, "00.000.000/0001-91", "pro", HOJE_DA_BUSCA, pasta
        )
    for relatorio in (com_ficha, sem_ficha):
        assert relatorio.limites[-1] == FRASE_DE_CONTESTACAO
        pdf = relatorio_do_cnpj(relatorio, GERADO_EM)
        assert FRASE in _sem_espacos(_texto_do_pdf(pdf))
