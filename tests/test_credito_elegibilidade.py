"""As regras de elegibilidade da ficha (linha 754): um fato por regra, sem soma nem nota."""

from datetime import date

import pytest

from base.palavras_vedadas import palavras_vedadas_em
from base.receita_codigos import situacao_cadastral
from src.credito import elegibilidade as el
from src.credito import features_da_base as fb
from src.credito.dicionario import DICIONARIO
from src.credito.dossie import PEDACOS_DE_NOTA
from src.credito.features import nova_feature
from src.rastro import DocumentoUsado

DIA = date(2026, 11, 7)
DOCUMENTO = [DocumentoUsado("IPE: recuperacao_extrajudicial", date(2026, 3, 10))]


def _sinal(chave, valor, motivo=""):
    return nova_feature(chave, valor, "24 meses até 07/11/2026", DOCUMENTO, motivo)


def _resultado(resultados, chave):
    return next(r for r in resultados if r.chave == chave)


def test_toda_regra_olha_um_sinal_do_dicionario_e_vale_em_algum_papel():
    assert len({regra.chave for regra in el.REGRAS}) == len(el.REGRAS)
    for regra in el.REGRAS:
        assert regra.sinal in DICIONARIO
        assert {regra.para_o_cedente, regra.para_o_sacado} - {None} <= {
            el.INELEGIVEL,
            el.VERIFICAR,
        }
        assert regra.para_o_cedente or regra.para_o_sacado


def test_nenhuma_regra_e_nota_nem_usa_palavra_vedada():
    for regra in el.REGRAS:
        assert not PEDACOS_DE_NOTA & set(regra.chave.split("_"))
        assert not palavras_vedadas_em(regra.texto)


def test_sacado_com_re_nos_24_meses_e_inelegivel_e_o_cedente_fica_para_verificar():
    sinais = [_sinal("insolvencia_24_meses", 3)]
    sacado = _resultado(
        el.regras_de_elegibilidade(sinais, el.SACADO),
        "insolvencia_nos_ultimos_24_meses",
    )
    assert (sacado.resultado, sacado.efeito, sacado.valor) == (
        el.ACIONA,
        el.INELEGIVEL,
        3,
    )
    assert sacado.disponivel_em == date(2026, 3, 10)
    cedente = _resultado(
        el.regras_de_elegibilidade(sinais, el.CEDENTE),
        "insolvencia_nos_ultimos_24_meses",
    )
    assert (cedente.resultado, cedente.efeito) == (el.ACIONA, el.VERIFICAR)


def test_sem_insolvencia_nao_aciona():
    resultado = _resultado(
        el.regras_de_elegibilidade([_sinal("insolvencia_24_meses", 0)], el.SACADO),
        "insolvencia_nos_ultimos_24_meses",
    )
    assert resultado.resultado == el.NAO_ACIONA
    assert resultado.valor == 0


def test_sem_o_ipe_nao_da_para_saber_e_leva_o_motivo():
    sinais = [_sinal("insolvencia_24_meses", None, fb.SEM_IPE)]
    resultado = _resultado(
        el.regras_de_elegibilidade(sinais, el.SACADO),
        "insolvencia_nos_ultimos_24_meses",
    )
    assert resultado.resultado == el.NAO_DA_PARA_SABER
    assert resultado.valor is None
    assert resultado.motivo == fb.SEM_IPE


def test_sinal_que_falta_na_ficha_nao_da_para_saber():
    resultado = _resultado(
        el.regras_de_elegibilidade([], el.CEDENTE), "registro_na_lista_suja"
    )
    assert resultado.resultado == el.NAO_DA_PARA_SABER
    assert resultado.motivo == el.SEM_O_SINAL.format(chave="registros_na_lista_suja")


@pytest.mark.parametrize(
    ("valor", "resultado"),
    [(situacao_cadastral("02"), el.NAO_ACIONA), (situacao_cadastral("08"), el.ACIONA)],
)
def test_situacao_cadastral_fora_de_ativa_aciona(valor, resultado):
    assert situacao_cadastral("02") == el.ATIVA
    regra = _resultado(
        el.regras_de_elegibilidade(
            [_sinal("situacao_cadastral_na_receita", valor)], el.SACADO
        ),
        "cnpj_fora_da_situacao_ativa",
    )
    assert (regra.resultado, regra.efeito) == (resultado, el.INELEGIVEL)


@pytest.mark.parametrize(
    ("valor", "resultado"), [(fb.NENHUMA, el.NAO_ACIONA), ("falência", el.ACIONA)]
)
def test_situacao_especial_aciona_se_houver(valor, resultado):
    regra = _resultado(
        el.regras_de_elegibilidade(
            [_sinal("situacao_especial_na_receita", valor)], el.CEDENTE
        ),
        "cnpj_com_situacao_especial",
    )
    assert regra.resultado == resultado


@pytest.mark.parametrize(
    ("inadimplencia", "resultado"),
    [
        (el.LIMITE_DE_INADIMPLENCIA_DO_FUNDO, el.NAO_ACIONA),
        (0.69, el.ACIONA),
        (0.0, el.NAO_ACIONA),
    ],
)
def test_inadimplencia_do_fundo_acima_do_limite_aciona_so_para_o_cedente(
    inadimplencia, resultado
):
    sinais = [_sinal("maior_inadimplencia_dos_fundos_em_que_cede", inadimplencia)]
    regra = _resultado(
        el.regras_de_elegibilidade(sinais, el.CEDENTE),
        "fundo_do_cedente_com_inadimplencia_alta",
    )
    assert regra.resultado == resultado
    chaves_do_sacado = {r.chave for r in el.regras_de_elegibilidade(sinais, el.SACADO)}
    assert "fundo_do_cedente_com_inadimplencia_alta" not in chaves_do_sacado


def test_uma_regra_nao_mexe_na_outra():
    """Sem soma: o resultado de cada regra depende só do sinal dela."""
    sozinho = el.regras_de_elegibilidade(
        [_sinal("sancoes_vigentes_na_cgu", 2)], el.SACADO
    )
    junto = el.regras_de_elegibilidade(
        [_sinal("sancoes_vigentes_na_cgu", 2), _sinal("insolvencia_24_meses", 5),
         _sinal("registros_na_lista_suja", 1)],
        el.SACADO,
    )  # fmt: skip
    assert _resultado(sozinho, "sancao_vigente_na_cgu") == _resultado(
        junto, "sancao_vigente_na_cgu"
    )


def test_papel_desconhecido_falha():
    with pytest.raises(el.PapelDesconhecidoError):
        el.regras_de_elegibilidade([], "avalista")


def test_como_dict_tem_datas_em_texto():
    (resultado,) = [
        r for r in el.regras_de_elegibilidade([_sinal("insolvencia_24_meses", 1)], el.SACADO)
        if r.chave == "insolvencia_nos_ultimos_24_meses"
    ]  # fmt: skip
    assert resultado.como_dict()["disponivel_em"] == "2026-03-10"
