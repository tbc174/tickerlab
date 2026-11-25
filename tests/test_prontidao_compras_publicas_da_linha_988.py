"""As compras públicas no registro de piloto (linha 988; ADR 0108, Emenda 3, D11).

`comprasgov_sicaf` (o cadastro de fornecedores do SICAF) tem CNPJ inteiro em toda linha e a marca `trata_como_pessoa`
por linha. Só conta como pronta porque o servidor da API guarda apenas a cópia reduzida só-PJ de
`base/recorte_dos_cadastros.py` (degrau 9), que também tira a linha que o próprio SICAF chama de empresário individual
ou de pessoa física. O `bps_compras` tem a mesma cópia reduzida, mas fica fora do registro: o placar acusa a queda de
linhas de 2022 para 2023 e a causa ainda não foi conferida.
"""

from datetime import date

from base import prontidao, recorte_dos_cadastros
from base.dicionario import TABELAS
from base.qualidade_automatica import REGRAS

HOJE = date(2026, 11, 25)
SICAF, BPS = recorte_dos_cadastros.SICAF, recorte_dos_cadastros.BPS


def test_as_duas_tem_a_marca_por_linha_e_contam_como_decididas() -> None:
    for tabela in (SICAF, BPS):
        contrato = TABELAS[tabela]
        assert contrato.linhas_de_pessoa == "trata_como_pessoa"
        assert contrato.linhas_de_pessoa in contrato.colunas
        assert tabela in prontidao.tabelas_com_pessoa_decidida()
        assert tabela in recorte_dos_cadastros.COMPRAS_PUBLICAS
        assert tabela in REGRAS


def test_sem_o_registro_de_piloto_o_sicaf_nao_sai() -> None:
    falta = prontidao.negacao_do_piloto(
        (SICAF,), {}, prontidao.versoes_maiores(), frozenset({SICAF}), HOJE
    )
    assert falta is prontidao.Falta.SEM_PRONTIDAO


def test_o_registro_de_verdade_libera_o_sicaf_pelo_piloto() -> None:
    falta = prontidao.negacao_do_piloto(
        (SICAF,),
        prontidao.PRONTIDAO_DE_PILOTO,
        prontidao.versoes_maiores(),
        prontidao.tabelas_com_pessoa_decidida(),
        HOJE,
    )
    assert falta is None


def test_a_versao_e_as_duas_provas_do_sicaf_sao_as_do_piloto() -> None:
    registro = prontidao.PRONTIDAO_DE_PILOTO[SICAF]
    assert registro.versao_maior == prontidao.versoes_maiores()[SICAF]
    assert registro.qualidade is not None and registro.dicionario is not None
    assert registro.qualidade.data == HOJE
    assert prontidao.prova_publicavel(registro.qualidade.prova)
    assert prontidao.prova_publicavel(registro.dicionario.prova)
    assert SICAF not in prontidao.PRONTIDAO


def test_o_bps_fica_fora_do_registro_ate_a_causa_da_queda_de_2023() -> None:
    assert BPS not in prontidao.PRONTIDAO_DE_PILOTO
    assert BPS not in prontidao.PRONTIDAO
    falta = prontidao.negacao_do_piloto(
        (BPS,),
        prontidao.PRONTIDAO_DE_PILOTO,
        prontidao.versoes_maiores(),
        prontidao.tabelas_com_pessoa_decidida(),
        HOJE,
    )
    assert falta is prontidao.Falta.SEM_PRONTIDAO
