"""O contrato do dossiê de crédito de PJ (C-PR01 do Plano Mestre v3.1; N4, linha 113 da fila).

O contrato se defende sozinho: dossiê que olha o futuro, que deixa uma seção vazia sem lacuna, que traz pessoa
física (id de pessoa, CPF inteiro ou mascarado) ou que dá nota não é montado. E sai em JSON de tipos simples.
"""

import json
from dataclasses import replace
from datetime import date

import pytest

from src.credito import dossie as dc
from src.credito.features import OlhouOFuturoError
from src.rastro import DocumentoUsado, Rastro

CNPJ = "02429144000193"
DIA = date(2025, 6, 30)
ANTES = date(2025, 4, 10)
DEPOIS = date(2025, 7, 15)
DFP = DocumentoUsado(
    "DFP de 31/12/2024, versão 1", ANTES, "https://www.rad.cvm.gov.br/x"
)


def _rastro(publicado_em: date = ANTES) -> Rastro:
    documento = replace(DFP, publicado_em=publicado_em)
    return Rastro.dos_documentos(
        "lido como entregue", "dossie_credito 1", "cvm", [documento]
    )


def _fato(
    chave: str = "razao_social",
    valor: object = "CPFL Energia S.A.",
    publico_em: date = ANTES,
):
    return dc.Fato(chave, valor, _rastro(publico_em), publico_em)


def _parte(id_entidade: str = "E" + "a" * 20) -> dc.ParteJuridica:
    return dc.ParteJuridica(
        id_entidade, "empresa", "CPFL Geração de Energia S.A.", "03953509000147"
    )


def _vinculo(**mudar) -> dc.Vinculo:
    vinculo = dc.Vinculo(
        tipo="controlada_de",
        sentido=dc.PARA_A_EMPRESA,
        outra_parte=_parte(),
        grau=dc.DOCUMENTO_OFICIAL,
        rastro=_rastro(),
        publico_em=ANTES,
        desde=date(2010, 1, 1),
        participacao=100.0,
    )
    return replace(vinculo, **mudar)


def _documento(publico_em: date = ANTES) -> dc.Documento:
    return dc.Documento(
        "DFP", date(2024, 12, 31), publico_em, _rastro(publico_em), url=DFP.url
    )


def _operacao() -> dc.Operacao:
    return dc.Operacao("emissor", "debenture", "BRCPFEDBS0X1", _rastro(), ANTES)


def _lacuna(secao: str, tipo: str = dc.NAO_OBSERVAVEL) -> dc.Lacuna:
    return dc.Lacuna(secao, "o que falta", tipo, "por que falta")


def _dossie(**mudar) -> dc.DossieCredito:
    campos = {
        "cnpj": CNPJ,
        "data_de_referencia": DIA,
        "identificacao": (_fato(),),
        "situacao": (_fato("situacao_cadastral", "ativa"),),
        "documentos": (_documento(),),
        "fundamentos": (_fato("alavancagem", 2.1),),
        "vinculos": (_vinculo(),),
        "operacoes_publicas": (_operacao(),),
        "lacunas": (),
    } | mudar
    return dc.DossieCredito(**campos)


def test_dossie_completo_sai_em_json_com_datas_em_texto():
    dossie = _dossie()
    texto = json.dumps(dossie.como_dict(), ensure_ascii=False)
    lido = json.loads(texto)
    assert lido["data_de_referencia"] == "2025-06-30"
    assert lido["vinculos"][0]["grau"] == dc.DOCUMENTO_OFICIAL
    assert lido["identificacao"][0]["rastro"]["publicado_em"] == "2025-04-10"
    assert lido["versao_do_contrato"] == dc.VERSAO_DO_CONTRATO


def test_cnpj_invalido_nao_monta():
    with pytest.raises(ValueError, match="CNPJ"):
        _dossie(cnpj="123")


@pytest.mark.parametrize(
    "mudar",
    [
        {"identificacao": (_fato(publico_em=DEPOIS),)},
        {"documentos": (_documento(DEPOIS),)},
        {"vinculos": (_vinculo(publico_em=DEPOIS),)},
        {
            "vinculos": (_vinculo(rastro=_rastro(DEPOIS)),)
        },  # o documento do rastro é do futuro
        {"operacoes_publicas": (replace(_operacao(), publico_em=DEPOIS),)},
    ],
)
def test_qualquer_coisa_publicada_depois_do_dia_derruba_o_dossie(mudar):
    with pytest.raises(OlhouOFuturoError):
        _dossie(**mudar)


def test_publicado_no_proprio_dia_entra():
    assert (
        _dossie(identificacao=(_fato(publico_em=DIA),)).identificacao[0].publico_em
        == DIA
    )


def test_fim_do_vinculo_so_entra_se_ja_era_publico():
    """O `ate` é a data do fato; quem diz que o fim já se sabia no dia é o `ate_publico_em` (D5)."""
    with pytest.raises(OlhouOFuturoError):
        _dossie(vinculos=(_vinculo(ate=date(2025, 1, 1), ate_publico_em=DEPOIS),))
    with pytest.raises(ValueError, match="ate_publico_em"):
        _dossie(vinculos=(_vinculo(ate=date(2025, 1, 1)),))
    encerrado = _vinculo(ate=date(2025, 1, 1), ate_publico_em=ANTES)
    assert _dossie(vinculos=(encerrado,)).vinculos[0].ate == date(2025, 1, 1)


@pytest.mark.parametrize("secao", dc.SECOES)
def test_secao_vazia_sem_lacuna_nao_monta(secao):
    with pytest.raises(dc.SecaoSemLacunaError, match=secao):
        _dossie(**{secao: ()})


@pytest.mark.parametrize("secao", dc.SECOES)
def test_secao_vazia_com_lacuna_escrita_monta(secao):
    dossie = _dossie(**{secao: ()}, lacunas=(_lacuna(secao),))
    assert dossie.lacunas_da(secao) == (_lacuna(secao),)


def test_lacuna_de_secao_ou_tipo_desconhecido_nao_monta():
    with pytest.raises(ValueError, match="seção"):
        _dossie(lacunas=(_lacuna("score"),))
    with pytest.raises(ValueError, match="tipo"):
        _dossie(lacunas=(_lacuna("vinculos", "talvez"),))


def test_lacuna_sem_motivo_nao_monta():
    with pytest.raises(ValueError, match="motivo"):
        _dossie(lacunas=(dc.Lacuna("vinculos", "sócios", dc.BLOQUEADA, " "),))


def test_rastro_incompleto_nao_monta():
    sem_formula = replace(_rastro(), formula="")
    with pytest.raises(ValueError, match="rastro"):
        _dossie(identificacao=(replace(_fato(), rastro=sem_formula),))


def test_fato_sem_valor_e_lacuna_nao_fato():
    with pytest.raises(ValueError, match="lacuna"):
        _dossie(identificacao=(_fato(valor=None),))
    with pytest.raises(ValueError, match="lacuna"):
        _dossie(identificacao=(_fato(valor="  "),))


def test_grau_desconhecido_nao_monta():
    with pytest.raises(ValueError, match="grau"):
        _dossie(vinculos=(_vinculo(grau="quase certo"),))


def test_sentido_desconhecido_nao_monta():
    with pytest.raises(ValueError, match="sentido"):
        _dossie(vinculos=(_vinculo(sentido="lado"),))


def test_pessoa_fisica_como_parte_nao_monta():
    with pytest.raises(dc.PessoaNoDossieError):
        _dossie(vinculos=(_vinculo(outra_parte=_parte("P" + "b" * 20)),))
    with pytest.raises(dc.PessoaNoDossieError):
        _dossie(vinculos=(_vinculo(outra_parte=_parte("qualquer")),))


@pytest.mark.parametrize(
    "texto",
    [
        "123.456.789-09",
        "12345678909",
        "***456789**",
        "***.456.789-**",
        "sócio 529.982.247-25 entrou",
    ],
)
def test_cpf_em_qualquer_texto_nao_monta(texto):
    with pytest.raises(dc.PessoaNoDossieError):
        _dossie(identificacao=(_fato("nome_fantasia", texto),))
    with pytest.raises(dc.PessoaNoDossieError):
        _dossie(
            fundamentos=(),
            lacunas=(dc.Lacuna("fundamentos", "x", dc.SEM_REGISTRO, texto),),
        )


def test_cnpj_nao_e_confundido_com_cpf():
    """CNPJ (14 dígitos, com ou sem pontuação) e ISIN não são CPF."""
    dossie = _dossie(
        identificacao=(
            _fato("cnpj", "02.429.144/0001-93"),
            _fato("cnpj_sem_pontos", CNPJ),
        ),
        operacoes_publicas=(_operacao(),),
    )
    assert len(dossie.identificacao) == 2


@pytest.mark.parametrize(
    "chave", ["score", "nota_de_credito", "semaforo_do_risco", "selo"]
)
def test_chave_de_nota_ou_score_nao_monta(chave):
    with pytest.raises(dc.NotaNoDossieError):
        _dossie(fundamentos=(_fato(chave, 7.0),))


@pytest.mark.parametrize(
    "texto", ["empresa confiável", "evite esta empresa", "recomendamos"]
)
def test_palavra_vedada_em_texto_nao_monta(texto):
    with pytest.raises(dc.NotaNoDossieError):
        _dossie(identificacao=(_fato("nome_fantasia", texto),))


def test_ratings_publicados_contados_nao_sao_nota():
    """Contar ratings que a companhia publicou no IPE é fato; "rating" sozinho não é palavra vedada."""
    assert (
        _dossie(fundamentos=(_fato("ratings_12_meses", 2),)).fundamentos[0].valor == 2
    )


def test_lacunas_saem_em_ordem_de_secao():
    lacunas = (_lacuna("vinculos"), _lacuna("identificacao", dc.FONTE_INDISPONIVEL))
    dossie = _dossie(lacunas=lacunas)
    assert [lacuna.secao for lacuna in dossie.lacunas] == ["identificacao", "vinculos"]
