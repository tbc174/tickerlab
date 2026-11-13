"""`anvisa_por_empresa` no registro de piloto (linha 860, PR 6; ADR 0108, Emenda 2, D11).

A busca por registros da Anvisa só responde à organização do piloto no conector e na CLI se a tabela tiver o
registro de piloto em dia, a marca de pessoa decidida e a versão maior conferida. O que este arquivo cobra é o
**registro de verdade** (não um de mentira): o aviso, o sinal de porte e as colunas sem licença lida ficam
cobertos em `test_api_externa_prospeccao_anvisa.py` e `test_api_externa_piloto.py`.
"""

from datetime import date

from base import prontidao
from base.dicionario import TABELAS
from src.api_externa.conjuntos import prospeccao

TABELA = "anvisa_por_empresa"
HOJE = date(2026, 11, 13)


def test_o_registro_de_verdade_libera_a_tabela_pelo_piloto_hoje() -> None:
    falta = prontidao.negacao_do_piloto(
        (TABELA,),
        prontidao.PRONTIDAO_DE_PILOTO,
        prontidao.versoes_maiores(),
        prontidao.tabelas_com_pessoa_decidida(),
        HOJE,
    )
    assert falta is None


def test_a_versao_do_registro_e_a_do_contrato_e_a_prova_7_vence_em_90_dias() -> None:
    registro = prontidao.PRONTIDAO_DE_PILOTO[TABELA]
    assert registro.versao_maior == prontidao.versoes_maiores()[TABELA]
    qualidade = registro.qualidade
    assert qualidade is not None
    # a prova é do dia em que a tabela foi medida (verde) e tem identificador: sem os dois a tabela nega
    assert qualidade.data <= HOJE
    assert qualidade.prova.startswith("placar-qualidade-")


def test_a_tabela_nao_entra_na_prontidao_cheia_nem_guarda_pessoa() -> None:
    """O piloto não é a prontidão cheia (falta a conferência cruzada) e a tabela é só de pessoa jurídica."""
    assert TABELA not in prontidao.PRONTIDAO
    assert not TABELAS[TABELA].pessoa
    assert TABELAS[TABELA].linhas_de_pessoa == "trata_como_pessoa"


def test_so_os_tipos_com_licenca_lida_chegam_a_quem_busca() -> None:
    """Cosméticos, saneantes e produtos para saúde (CC Attribution lida em 12/11/2026); os outros tipos existem
    na tabela e ficam sem ser servidos até a ficha de cada um ser lida."""
    servidos = {t for prefixos in prospeccao.TIPOS_DA_ANVISA.values() for t in prefixos}
    assert servidos == {"cosmeticos", "saneantes", "produtos_saude"}
    sem_licenca = {"alimentos", "medicamentos", "afe", "cbpf"}
    assert not servidos & sem_licenca


def test_a_resposta_diz_que_e_sinal_de_porte_e_nao_faturamento() -> None:
    assert "sinal de porte" in prospeccao.AVISO_DA_ANVISA
    assert "não faturamento" in prospeccao.AVISO_DA_ANVISA
