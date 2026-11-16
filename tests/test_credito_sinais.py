"""Os sinais da ficha de crédito (linha 754), pela porta: PGFN por situação, Receita, listas do governo,
dívida estadual, o Estado como pagador, FIDC como cedente, rating, insolvência e entrega à CVM.

Tabelas de mentira (`extras` da porta) com os números reais do exemplo da Mundial (06/11/2026): a
Mundial como cedente, a Raia Drogasil como sacado forte e o GPA, em recuperação extrajudicial, como
sacado fraco. O que conta é o dia em que cada linha ficou pública. Por propriedade: tirar da base as
linhas publicadas depois de um corte não muda os sinais de nenhum dia antes dele."""

import random
from datetime import date, timedelta

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import cnpj as cnpj_
from base.porta import Porta
from base.rede import ids
from src.credito import features as fc
from src.credito import features_da_base as fb
from src.credito import sinais as si
from src.credito.dicionario import DA_FICHA, DICIONARIO

MUNDIAL, RD, GPA, MEI, NOVA, OUTRA = (
    "88610191000154",
    "61585865000151",
    "47508411000156",
    "44555666000199",
    "11222333000181",
    "33000167000101",
)
DIA = date(2026, 11, 7)
EGM, MARFIM = "13.416.131/0001-04", "30.178.001/0001-91"


def _f(cnpj: str) -> str:
    return cnpj_.formatar(cnpj)


def _ts(dia: str | None) -> pd.Timestamp | None:
    return pd.Timestamp(dia) if dia else None


# --- as linhas de cada tabela ---------------------------------------------------------------------
def _pgfn(cnpj, situacao, valor, retrato="2026-06-30", visto="2026-10-14", devedor="principal",
          pessoa=False) -> dict:  # fmt: skip
    return {"cnpj": _f(cnpj), "cnpj_basico": cnpj[:8], "tipo_divida": "nao_previdenciaria",
            "regiao": "1", "tipo_devedor": devedor, "tipo_situacao": situacao,
            "situacao_inscricao": "ATIVA", "ajuizado": False, "inscricoes": 1,
            "valor_consolidado": valor, "data_do_retrato": _ts(retrato), "trata_como_pessoa": pessoa,
            "disponivel_em": _ts(visto)}  # fmt: skip


def _cadastral(cnpj, mes, visto, codigo, matriz=True, consta=True) -> dict:
    """Uma versão de um estabelecimento (linha 841): nasce no mês em que algum campo mudou."""
    return {"cnpj": _f(cnpj), "cnpj_basico": cnpj[:8], "matriz": matriz,
            "situacao_cadastral": codigo, "data_situacao_cadastral": _ts("2005-11-03"),
            "motivo_situacao": "00", "mes_do_retrato": mes, "disponivel_em": _ts(visto),
            "consta": consta}  # fmt: skip


def _mudanca(cnpj, id_na_fonte, visto, consta=True, pessoa=False, **outras) -> dict:
    """Uma linha de tabela que grava o que mudou (`visto_em`: a versão)."""
    return {"id_na_fonte": id_na_fonte, "cnpj": _f(cnpj), "cnpj_basico": cnpj[:8],
            "consta": consta, "trata_como_pessoa": pessoa, "visto_em": _ts(visto),
            "disponivel_em": _ts(visto), **outras}  # fmt: skip


def _pagamento(
    cnpj, id_na_fonte, pago_em, valor, dias, visto=None, consta=True
) -> dict:
    return _mudanca(cnpj, id_na_fonte, visto or pago_em, consta, arquivo="ano", pago_em=_ts(pago_em),
                    valor_pago=valor, dias_ate_pagar=dias)  # fmt: skip


def _fidc(fundo, competencia, publico, cedentes, carteira, inadimplente) -> dict:
    """Um informe; `cedentes` = [(coluna do quadro, posição, CNPJ, percentual em texto)]. A CVM
    guarda os números em texto com ponto."""
    linha = {"competencia": _ts(competencia), "cnpj_fundo": fundo, "TAB_I2_VL_CARTEIRA": carteira,
             "TAB_I2A3_VL_CRED_INAD": inadimplente,              "disponivel_em": _ts(publico)}  # fmt: skip
    for quadro in ("TAB_I2A12", "TAB_I2B1", "TAB_I2B12"):
        for n in (1, 2):
            linha[f"{quadro}_CPF_CNPJ_CEDENTE_{n}"] = None
            linha[f"{quadro}_PR_CEDENTE_{n}"] = None
    for quadro, n, cnpj, percentual in cedentes:
        linha[f"{quadro}_CPF_CNPJ_CEDENTE_{n}"] = cnpj
        linha[f"{quadro}_PR_CEDENTE_{n}"] = percentual
    return linha


def _rating(cnpj, protocolo, publico, nota, perspectiva, escala="nacional",
            situacao="extraido") -> dict:  # fmt: skip
    return {"cnpj": _f(cnpj), "empresa": "X", "codigo_cvm": "1", "agencia": "fitch",
            "escala": escala, "nota": nota, "nivel": None, "nota_original": nota,
            "perspectiva": perspectiva, "acao": "afirmacao", "data_acao": _ts(publico),
            "outras_notas": None, "publico_em": _ts(publico), "protocolo": protocolo, "versao": 1,
            "link": f"https://cvm/{protocolo}", "evidencia": "", "situacao_extracao": situacao,
            "documentos": 1}  # fmt: skip


def _insolvencia(cnpj, protocolo, rotulo, conhecido_em, versao=1) -> dict:
    return {"cnpj": _f(cnpj), "empresa": "X", "rotulo": rotulo, "evento": rotulo,
            "regra": "categoria_ipe", "evidencia": "categoria_ipe", "categoria": "c", "tipo": "",
            "assunto": "", "conhecido_em": _ts(conhecido_em), "referencia": _ts(conhecido_em),
            "protocolo": protocolo, "versao": versao, "link": f"https://cvm/{protocolo}"}  # fmt: skip


def _evento(cnpj, protocolo, publicado_em) -> dict:
    return {"protocolo": protocolo, "versao": 1, "cnpj": _f(cnpj), "empresa": "X",
            "categoria": "Comunicado ao mercado", "tipo": "", "assunto": "",
            "rotulo": "Comunicado ao mercado", "tema": "eventos", "materialidade": 50,
            "referencia": _ts(publicado_em), "publicado_em": _ts(publicado_em),
            "link": f"https://cvm/{protocolo}"}  # fmt: skip


def _entrega(cnpj, documento, referencia, prazo, entrega) -> dict:
    atrasou = _ts(entrega) > _ts(prazo)
    return {"cnpj": _f(cnpj), "empresa": "X", "documento": documento,
            "referencia": _ts(referencia), "data_da_previsao": _ts(prazo), "prazo": _ts(prazo),
            "primeira_entrega": _ts(entrega), "dias_uteis_de_atraso": 5 if atrasou else 0,
            "atrasou": atrasou, "atraso_grave": False, "zona_cinzenta": False, "uf": "RS",
            "mes_fim_do_exercicio": 12}  # fmt: skip


def _entregas(cnpj, atrasada: tuple[int, ...] = ()) -> list[dict]:
    """Dez trimestres até jun/2026, cada um entregue 45 dias depois do fim; os de `atrasada`
    (0 = o mais novo) chegam 10 dias depois do prazo."""
    linhas = []
    for i, fim in enumerate(
        pd.date_range(end="2026-06-30", periods=10, freq="QE")[::-1]
    ):
        prazo = fim + pd.Timedelta(days=45)
        entrega = prazo + pd.Timedelta(days=10 if i in atrasada else -1)
        documento = "DFP" if fim.month == 12 else "ITR"
        linhas.append(
            _entrega(
                cnpj, documento, str(fim.date()), str(prazo.date()), str(entrega.date())
            )
        )
    return linhas


def _entidade(cnpj, pessoa) -> tuple[dict, dict]:
    id_entidade = ids.id_entidade("empresa", "cnpj_raiz", cnpj[:8])
    publico = pd.Timestamp("2010-12-31")
    return (
        {"id_entidade": id_entidade, "tipo": "empresa", "nome": "X",
         "natureza_juridica": "2135" if pessoa else "2046", "natureza_fonte": "receita",
         "mei": pessoa, "trata_como_pessoa": pessoa, "publico_em": publico},
        {"id_entidade": id_entidade, "sistema": "cnpj_raiz", "valor": cnpj[:8], "desde": publico,
         "publico_em": publico},
    )  # fmt: skip


# --- a base de mentira ----------------------------------------------------------------------------
BF, GA, SU, EC = (
    "Benefício Fiscal",
    "Garantia",
    "Suspenso por decisão judicial",
    "Em cobrança",
)
PGFN = [
    _pgfn(MUNDIAL, BF, 1_374_333_000.0),
    _pgfn(MUNDIAL, GA, 186_020_800.0),
    _pgfn(MUNDIAL, SU, 193_458_200.0),
    _pgfn(MUNDIAL, EC, 9_999.0, devedor="corresponsavel"),  # corresponsável não entra
    _pgfn(
        MUNDIAL, EC, 5_000.0, retrato="2026-03-31", visto="2026-05-12"
    ),  # retrato antigo
    _pgfn(RD, GA, 16_467_753.29),
    _pgfn(RD, SU, 1_375_810.43),
    _pgfn(GPA, BF, 181_264_900.0),
    _pgfn(GPA, GA, 2_652_363_000.0),
    _pgfn(GPA, SU, 101_207_100.0),
    _pgfn(MEI, EC, 70.0, pessoa=True),
]
FILIAL_DA_OUTRA = OUTRA[:8] + "000282"
CADASTRAL = [
    _cadastral(cnpj, "2024-05", "2024-06-10", "02") for cnpj in (MUNDIAL, RD, GPA)
] + [  # a versão de 2024 ainda vale em 2026: nada mudou desde então
    _cadastral(OUTRA, "2026-08", "2026-09-10", "02"),
    _cadastral(
        OUTRA, "2026-09", "2026-10-10", "8"
    ),  # sem o zero à esquerda, como em alguns meses
    _cadastral(FILIAL_DA_OUTRA, "2026-08", "2026-09-10", "02", matriz=False),
]
_PRAZO = {"inicio": _ts("2026-05-01"), "fim": _ts("2028-05-01")}
CGU = [
    _mudanca(OUTRA, "S1", "2026-05-10", cadastro="CEIS", **_PRAZO),
    _mudanca(
        OUTRA, "S1", "2026-09-03", consta=False, cadastro="CEIS", **_PRAZO
    ),  # saiu da lista
    _mudanca(
        OUTRA, "S2", "2026-05-10", cadastro="CNEP", inicio=_ts("2026-05-01"), fim=None
    ),
    _mudanca(MEI, "S3", "2026-05-10", pessoa=True, cadastro="CEIS", **_PRAZO),
    # ainda na lista, mas o prazo acabou antes do dia: não é vigente
    _mudanca(
        OUTRA,
        "S4",
        "2026-05-10",
        cadastro="CEIS",
        inicio=_ts("2025-01-01"),
        fim=_ts("2026-07-20"),
    ),
    # publicada com início depois do dia: ainda não vale
    _mudanca(
        OUTRA, "S5", "2026-05-10", cadastro="CEIS", inicio=_ts("2027-01-01"), fim=None
    ),
]
LISTA_SUJA = [
    _mudanca(OUTRA, "L1", "2026-04-05"),
    _mudanca(OUTRA, "L2", "2026-04-05", pessoa=None),  # na dúvida, é pessoa: não entra
]
IBAMA = [
    # as marcas são texto, como o IBAMA escreve (SIT_CANCELADO e SIT_DESEMBARGO)
    _mudanca(OUTRA, "T1", "2026-03-01", cancelado="N", desembargado=None),
    _mudanca(OUTRA, "T2", "2026-03-01", cancelado="N", desembargado="S"),
    _mudanca(OUTRA, "T3", "2026-03-01", cancelado="S", desembargado=None),
    _mudanca(OUTRA, "T4", "2026-03-01", cancelado=None, desembargado=" s "),
]
SEFA_PR = [
    _mudanca(GPA, "P1", "2026-09-01", valor_total=100.0, suspensao=None, com_garantia=False,
             com_parcelamento_ativo=True),
    _mudanca(GPA, "P2", "2026-09-01", valor_total=200.0, suspensao=None, com_garantia=True,
             com_parcelamento_ativo=False),
    _mudanca(GPA, "P3", "2026-09-01", valor_total=300.0, suspensao="Liminar", com_garantia=False,
             com_parcelamento_ativo=False),
    _mudanca(GPA, "P4", "2026-09-01", valor_total=400.0, suspensao=None, com_garantia=False,
             com_parcelamento_ativo=False),
    _mudanca(GPA, "P4", "2026-12-01", valor_total=900.0, suspensao=None, com_garantia=False,
             com_parcelamento_ativo=False),  # versão de depois do dia
]  # fmt: skip
SEF_MG = [
    _mudanca(RD, f"C{i}", "2026-08-20", saldo_da_cda=10.0 * i) for i in (1, 2, 3, 4)
]
SEF_MG_PARCELAMENTOS = [_mudanca(RD, "M1", "2026-08-20", debito=55.0)]
PE = [
    _pagamento(MUNDIAL, "1", "2026-03-10", 1000.0, 30),
    _pagamento(MUNDIAL, "2", "2026-08-01", 2000.0, 10),
    _pagamento(MUNDIAL, "3", "2025-10-01", 7000.0, 90),  # mais de 365 dias antes do dia
    _pagamento(MUNDIAL, "4", "2026-11-20", 8000.0, 1),  # pagamento de depois do dia
    _pagamento(MUNDIAL, "5", "2026-06-01", 500.0, 3),
    _pagamento(
        MUNDIAL, "5", "2026-06-15", 500.0, 3, visto="2026-06-15", consta=False
    ),  # corrigido
]
ES = [_pagamento(OUTRA, "1", "2026-05-05", 50.0, 4)]
FIDC = [
    _fidc(EGM, "2026-08-31", "2026-10-15", [("TAB_I2B12", 1, _f(MUNDIAL), "35.45")],
          "68100000.00", "0"),
    _fidc(MARFIM, "2026-08-31", "2026-10-15", [("TAB_I2A12", 2, _f(MUNDIAL), "0.32")],
          "6340000.00", "4395000.00"),
    _fidc(EGM, "2026-09-30", "2026-11-14", [("TAB_I2B12", 1, _f(MUNDIAL), "33.88")],
          "68970000.00", "0"),
    _fidc(MARFIM, "2026-09-30", "2026-11-14", [("TAB_I2A12", 2, _f(MUNDIAL), "0.42")],
          "5500000.00", "0"),
    _fidc(EGM, "2026-05-31", "2026-07-15", [("TAB_I2B1", 1, _f(OUTRA), "12.5")], "1000", "0"),
]  # fmt: skip
RATINGS = [
    _rating(RD, "R1", "2019-02-05", "AAA", "estavel"),
    _rating(RD, "R2", "2019-02-19", "AAA", "estavel"),
    _rating(RD, "R3", "2026-12-01", "AA+", "negativa"),  # de depois do dia
    _rating(GPA, "G1", "2026-03-02", "A", "em_observacao_negativa", escala="global"),
    _rating(
        GPA, "G2", "2026-10-01", None, None, situacao="nao_extraido"
    ),  # sem rating legível
]
INSOLVENCIA = [
    _insolvencia(GPA, "I0", "recuperacao_judicial", "2018-05-02"),  # fora dos 24 meses
    _insolvencia(GPA, "I1", "recuperacao_extrajudicial", "2026-03-10"),
    _insolvencia(GPA, "I1", "recuperacao_extrajudicial", "2026-03-12", versao=2),
    _insolvencia(GPA, "I2", "recuperacao_extrajudicial", "2026-03-11"),
    _insolvencia(GPA, "I3", "recuperacao_extrajudicial", "2026-10-07"),
    _insolvencia(
        GPA, "I4", "exposicao_a_terceiro", "2026-10-20"
    ),  # de terceiro: não conta
    _insolvencia(RD, "I5", "exposicao_a_terceiro", "2026-01-15"),
]
EVENTOS = [_evento(MUNDIAL, "E1", "2026-08-14"), _evento(RD, "E2", "2026-08-14")]
ATRASO = _entregas(MUNDIAL, atrasada=(9,)) + _entregas(RD, atrasada=(2,))
REDE = [_entidade(MUNDIAL, False), _entidade(MEI, True)]
TABELAS = {
    "pgfn_divida": PGFN,
    "cnpj_situacao_cadastral": CADASTRAL,
    "sancoes_cgu": CGU,
    "mte_lista_suja": LISTA_SUJA,
    "ibama_embargos": IBAMA,
    "sefa_pr_divida_ativa": SEFA_PR,
    "sef_mg_divida_ativa": SEF_MG,
    "sef_mg_parcelamentos": SEF_MG_PARCELAMENTOS,
    "sefaz_pe_ordem_cronologica": PE,
    "es_ordem_cronologica": ES,
    "fidc_informe": FIDC,
    "ratings": RATINGS,
    "insolvencia": INSOLVENCIA,
    "eventos": EVENTOS,
    "rotulos_atraso": ATRASO,
    "entidades": [entidade for entidade, _ in REDE],
    "identificadores": [identificador for _, identificador in REDE],
}


def _fim_do_mes(coluna: str):
    return lambda linha: linha[coluna] + pd.offsets.MonthEnd(0)


def _no_dia(coluna: str):
    return lambda linha: linha[coluna]


# o dia em que cada linha fica pública (as tabelas mensais valem pelo último dia do mês)
PUBLICO_EM = {
    "pgfn_divida": _fim_do_mes("disponivel_em"),
    "cnpj_situacao_cadastral": _fim_do_mes("disponivel_em"),
    "sancoes_cgu": _fim_do_mes("disponivel_em"),
    "mte_lista_suja": _fim_do_mes("disponivel_em"),
    "ibama_embargos": _fim_do_mes("disponivel_em"),
    "sefa_pr_divida_ativa": _no_dia("disponivel_em"),
    "sef_mg_divida_ativa": _no_dia("disponivel_em"),
    "sef_mg_parcelamentos": _no_dia("disponivel_em"),
    "sefaz_pe_ordem_cronologica": _no_dia("disponivel_em"),
    "es_ordem_cronologica": _no_dia("disponivel_em"),
    "fidc_informe": _no_dia("disponivel_em"),
    "ratings": _no_dia("publico_em"),
    "insolvencia": _no_dia("conhecido_em"),
    "eventos": _no_dia("publicado_em"),
    "rotulos_atraso": _no_dia("primeira_entrega"),
    "entidades": _no_dia("publico_em"),
    "identificadores": _no_dia("publico_em"),
}


def _porta(
    pasta,
    corte: date | None = None,
    sem: tuple[str, ...] = (),
    trocas: dict[str, list[dict]] | None = None,
) -> Porta:
    extras = {}
    for nome, linhas in {**TABELAS, **(trocas or {})}.items():
        if nome in sem:
            continue
        tabela = pd.DataFrame(linhas)
        if corte is not None:
            tabela = tabela[
                [PUBLICO_EM[nome](x).date() <= corte for _, x in tabela.iterrows()]
            ]
        extras[nome] = tabela
    return Porta(pasta, arquivos={}, conferidas={}, extras=extras)


@pytest.fixture
def porta(tmp_path):
    with _porta(tmp_path) as p:
        yield p


def _sinais(porta, cnpj, dia=DIA) -> dict[str, fc.Feature]:
    return {f.chave: f for f in si.sinais_da_ficha(porta, cnpj, dia)}


# --- forma ----------------------------------------------------------------------------------------
def test_os_sinais_saem_na_ordem_do_dicionario_com_a_formula_dele(porta):
    sinais = si.sinais_da_ficha(porta, MUNDIAL, DIA)
    assert [f.chave for f in sinais] == list(DA_FICHA)
    for f in sinais:
        assert f.rastro.formula == DICIONARIO[f.chave].formula


def test_cnpj_invalido_e_recusado(porta):
    with pytest.raises(ValueError):
        si.sinais_da_ficha(porta, "123", DIA)


# --- PGFN por situação ----------------------------------------------------------------------------
def test_pgfn_soma_por_situacao_no_retrato_mais_novo(porta):
    f = _sinais(porta, MUNDIAL)
    assert f["divida_ativa_com_beneficio_fiscal"].valor == pytest.approx(
        1_374_333_000.0
    )
    assert f["divida_ativa_em_garantia"].valor == pytest.approx(186_020_800.0)
    assert f["divida_ativa_suspensa_pela_justica"].valor == pytest.approx(193_458_200.0)
    assert f["divida_ativa_em_cobranca"].valor == 0.0  # o corresponsável não entra
    assert f["divida_ativa_em_negociacao"].valor == 0.0
    assert f["divida_ativa_em_cobranca"].disponivel_em == date(2026, 10, 31)
    assert "30/06/2026" in f["divida_ativa_em_cobranca"].periodo


def test_pgfn_antes_do_retrato_novo_usa_o_antigo(porta):
    f = _sinais(porta, MUNDIAL, date(2026, 8, 1))
    assert f["divida_ativa_em_cobranca"].valor == 5_000.0
    assert f["divida_ativa_com_beneficio_fiscal"].valor == 0.0


def test_pgfn_da_rd_e_do_gpa_batem_com_o_exemplo(porta):
    rd, gpa = _sinais(porta, RD), _sinais(porta, GPA)
    assert rd["divida_ativa_em_garantia"].valor == pytest.approx(16_467_753.29)
    assert rd["divida_ativa_suspensa_pela_justica"].valor == pytest.approx(1_375_810.43)
    assert gpa["divida_ativa_em_garantia"].valor == pytest.approx(2_652_363_000.0)


def test_pgfn_sem_retrato_publico_fica_nao_observada(porta):
    f = _sinais(porta, MUNDIAL, date(2026, 5, 1))
    assert f["divida_ativa_em_cobranca"].valor is None
    assert f["divida_ativa_em_cobranca"].motivo == fb.SEM_RETRATO.format(fonte="PGFN")


# --- Receita: situação cadastral ------------------------------------------------------------------
def test_situacao_cadastral_do_retrato_mais_novo_da_matriz(porta):
    assert _sinais(porta, MUNDIAL)["situacao_cadastral_na_receita"].valor == "Ativa"
    outra = _sinais(porta, OUTRA)["situacao_cadastral_na_receita"]
    assert outra.valor == "Baixada" and outra.disponivel_em == date(2026, 10, 31)
    antes = _sinais(porta, OUTRA, date(2026, 10, 15))["situacao_cadastral_na_receita"]
    assert antes.valor == "Ativa"


def test_situacao_cadastral_de_quem_saiu_do_arquivo_nao_conta(tmp_path):
    """A matriz saiu do arquivo da Receita em 2026-10: vale a filial; sem nenhum, não observada."""
    saiu = _cadastral(OUTRA, "2026-10", "2026-10-12", None, matriz=None, consta=False)
    with _porta(tmp_path, trocas={"cnpj_situacao_cadastral": [*CADASTRAL, saiu]}) as p:
        assert _sinais(p, OUTRA)["situacao_cadastral_na_receita"].valor == "Ativa"
    sem_filial = [linha for linha in CADASTRAL if linha["cnpj"] != _f(FILIAL_DA_OUTRA)]
    (tmp_path / "2").mkdir()
    trocas = {"cnpj_situacao_cadastral": [*sem_filial, saiu]}
    with _porta(tmp_path / "2", trocas=trocas) as p:
        f = _sinais(p, OUTRA)["situacao_cadastral_na_receita"]
    assert f.valor is None and f.motivo == si.SEM_O_CNPJ.format(fonte="Receita")


def test_situacao_cadastral_sem_o_cnpj_fica_nao_observada(porta):
    f = _sinais(porta, NOVA)["situacao_cadastral_na_receita"]
    assert f.valor is None and f.motivo == si.SEM_O_CNPJ.format(fonte="Receita")


# --- listas do governo ----------------------------------------------------------------------------
def test_sancao_conta_so_a_versao_mais_nova_que_ainda_consta(porta):
    assert _sinais(porta, OUTRA, date(2026, 8, 1))["sancoes_vigentes_na_cgu"].valor == 2
    depois = _sinais(porta, OUTRA, date(2026, 10, 1))["sancoes_vigentes_na_cgu"]
    assert depois.valor == 1  # a S1 saiu da lista em setembro


def test_sancao_com_prazo_acabado_ou_ainda_por_comecar_nao_e_vigente(porta):
    # a S4 ainda consta, mas conta só até acabar em 20/07; a S5 só começa em 2027 e não conta
    assert (
        _sinais(porta, OUTRA, date(2026, 7, 15))["sancoes_vigentes_na_cgu"].valor == 3
    )
    assert (
        _sinais(porta, OUTRA, date(2026, 7, 25))["sancoes_vigentes_na_cgu"].valor == 2
    )


def test_lista_vazia_para_o_cnpj_e_zero_com_a_data_da_lista(porta):
    f = _sinais(porta, MUNDIAL)["sancoes_vigentes_na_cgu"]
    assert f.valor == 0 and f.motivo == ""
    assert f.disponivel_em == date(
        2026, 9, 30
    )  # a versão mais nova da lista pública no dia


def test_lista_que_a_base_ainda_nao_olhava_fica_nao_observada(porta):
    f = _sinais(porta, MUNDIAL, date(2026, 1, 1))["sancoes_vigentes_na_cgu"]
    assert f.valor is None and f.motivo == si.SEM_LISTA.format(tabela="sancoes_cgu")


def test_registro_que_pode_ser_de_pessoa_nao_conta(porta):
    assert _sinais(porta, OUTRA)["registros_na_lista_suja"].valor == 1


def test_embargo_marcado_s_de_cancelado_ou_desembargado_nao_conta(porta):
    # só o T1 (N e vazio) segue vigente; "S", com espaço ou minúsculo, tira o termo
    assert _sinais(porta, OUTRA)["embargos_vigentes_no_ibama"].valor == 1


# --- dívida estadual ------------------------------------------------------------------------------
def test_divida_do_parana_total_e_sem_parcelamento_nem_suspensao(porta):
    f = _sinais(porta, GPA)
    assert f["divida_ativa_no_parana"].valor == pytest.approx(1000.0)
    assert f[
        "divida_ativa_no_parana_sem_parcelamento_nem_suspensao"
    ].valor == pytest.approx(400.0)


def test_divida_de_minas_e_parcelamentos(porta):
    f = _sinais(porta, RD)
    assert f["divida_ativa_em_minas_gerais"].valor == pytest.approx(100.0)
    assert f["parcelamentos_em_minas_gerais"].valor == pytest.approx(55.0)
    assert _sinais(porta, MUNDIAL)["divida_ativa_em_minas_gerais"].valor == 0.0


# --- o Estado como pagador ------------------------------------------------------------------------
def test_pagamentos_de_pe_nos_12_meses(porta):
    f = _sinais(porta, MUNDIAL)
    assert f["pagamentos_recebidos_de_pe_12_meses"].valor == 2
    assert f["valor_recebido_de_pe_12_meses"].valor == pytest.approx(3000.0)
    assert f["mediana_de_dias_ate_receber_de_pe"].valor == pytest.approx(20.0)
    assert f["mediana_de_dias_ate_receber_de_pe"].disponivel_em == date(2026, 8, 1)


def test_sem_pagamento_do_es_e_zero_e_a_mediana_nao_observada(porta):
    f = _sinais(porta, MUNDIAL)
    assert f["pagamentos_recebidos_de_es_12_meses"].valor == 0
    assert f["valor_recebido_de_es_12_meses"].valor == 0.0
    mediana = f["mediana_de_dias_ate_receber_de_es"]
    assert mediana.valor is None and mediana.motivo == si.SEM_PAGAMENTO


# --- FIDC como cedente ----------------------------------------------------------------------------
def test_fidc_da_mundial_na_competencia_publica_no_dia(porta):
    f = _sinais(porta, MUNDIAL)  # set/2026 só fica pública em 14/11
    assert f["fundos_em_que_cede"].valor == 2
    assert f["maior_participacao_como_cedente"].valor == pytest.approx(0.3545)
    assert f["carteira_dos_fundos_em_que_cede"].valor == pytest.approx(74_440_000.0)
    assert f["maior_inadimplencia_dos_fundos_em_que_cede"].valor == pytest.approx(
        4395 / 6340
    )
    assert f["fundos_em_que_cede"].disponivel_em == date(2026, 10, 15)
    assert "08/2026" in f["fundos_em_que_cede"].periodo


def test_fidc_a_competencia_nova_vale_quando_fica_publica(porta):
    f = _sinais(porta, MUNDIAL, date(2026, 11, 14))
    assert f["maior_participacao_como_cedente"].valor == pytest.approx(0.3388)
    assert f["carteira_dos_fundos_em_que_cede"].valor == pytest.approx(74_470_000.0)
    assert f["maior_inadimplencia_dos_fundos_em_que_cede"].valor == 0.0


def test_fidc_sem_fundo_e_zero_e_o_resto_nao_observado(porta):
    f = _sinais(porta, RD)
    assert f["fundos_em_que_cede"].valor == 0
    assert f["carteira_dos_fundos_em_que_cede"].valor == 0.0
    for chave in (
        "maior_participacao_como_cedente",
        "maior_inadimplencia_dos_fundos_em_que_cede",
    ):
        assert f[chave].valor is None and f[chave].motivo == si.SEM_FUNDO


def test_fidc_sem_as_colunas_do_cedente_fica_nao_observado(tmp_path):
    extras = {nome: pd.DataFrame(linhas) for nome, linhas in TABELAS.items()}
    fidc = extras["fidc_informe"]
    extras["fidc_informe"] = fidc[[c for c in fidc.columns if "_CEDENTE_" not in c]]
    with Porta(tmp_path, arquivos={}, conferidas={}, extras=extras) as p:
        f = _sinais(p, MUNDIAL)
    for chave in si.DO_FIDC:
        assert f[chave].valor is None and f[chave].motivo == si.SEM_COLUNA_DO_CEDENTE


# --- rating ---------------------------------------------------------------------------------------
def test_rating_mais_novo_publico_no_dia(porta):
    f = _sinais(porta, RD)
    assert f["rating_mais_recente"].valor == "AAA (Fitch, escala nacional)"
    assert f["perspectiva_do_rating"].valor == "estável"
    assert f["dias_desde_o_rating"].valor == (DIA - date(2019, 2, 19)).days
    assert f["rating_mais_recente"].disponivel_em == date(2019, 2, 19)


def test_rating_ignora_documento_sem_rating_legivel(porta):
    f = _sinais(porta, GPA)
    assert f["rating_mais_recente"].valor == "A (Fitch, escala global)"
    assert f["perspectiva_do_rating"].valor == "em observação negativa"


def test_sem_rating_fica_nao_observado(porta):
    f = _sinais(porta, MUNDIAL)["rating_mais_recente"]
    assert f.valor is None and f.motivo == si.SEM_RATING


# --- insolvência em 24 meses ----------------------------------------------------------------------
def test_insolvencia_do_gpa_em_24_meses(porta):
    f = _sinais(porta, GPA)
    assert (
        f["insolvencia_24_meses"].valor == 3
    )  # protocolos, sem a de 2018 nem a de terceiro
    assert (
        f["ultima_insolvencia_24_meses"].valor
        == "recuperacao_extrajudicial em 07/10/2026"
    )


def test_insolvencia_so_de_terceiro_e_zero(porta):
    f = _sinais(porta, RD)
    assert f["insolvencia_24_meses"].valor == 0
    assert f["ultima_insolvencia_24_meses"].valor == fb.NENHUM


def test_insolvencia_sem_ipe_nao_da_para_saber(porta):
    f = _sinais(porta, NOVA)["insolvencia_24_meses"]
    assert f.valor is None and f.motivo == fb.SEM_IPE


# --- entrega à CVM --------------------------------------------------------------------------------
def test_atrasos_nas_ultimas_8_entregas(porta):
    assert (
        _sinais(porta, MUNDIAL)["atrasos_de_entrega_na_cvm"].valor == 0
    )  # o atraso é o 10º
    rd = _sinais(porta, RD)["atrasos_de_entrega_na_cvm"]
    assert rd.valor == 1 and rd.disponivel_em == date(2026, 8, 13)


def test_entrega_de_depois_do_dia_nao_aparece(porta):
    # em 01/04/2026 a mais nova entregue é a DFP de 2025, a que atrasou, e ela já conta
    f = _sinais(porta, RD, date(2026, 4, 1))["atrasos_de_entrega_na_cvm"]
    assert f.valor == 1 and f.disponivel_em == date(2026, 2, 24)


def test_sem_entrega_nao_da_para_saber(porta):
    f = _sinais(porta, GPA)["atrasos_de_entrega_na_cvm"]
    assert f.valor is None and f.motivo == si.SEM_ENTREGA


# --- tabela fora da base e pessoa -----------------------------------------------------------------
@pytest.mark.parametrize(
    ("tabela", "chave"),
    [
        ("sancoes_cgu", "sancoes_vigentes_na_cgu"),
        ("mte_lista_suja", "registros_na_lista_suja"),
        ("ibama_embargos", "embargos_vigentes_no_ibama"),
        ("sefa_pr_divida_ativa", "divida_ativa_no_parana"),
        ("sef_mg_divida_ativa", "divida_ativa_em_minas_gerais"),
        ("sef_mg_parcelamentos", "parcelamentos_em_minas_gerais"),
        ("sefaz_pe_ordem_cronologica", "valor_recebido_de_pe_12_meses"),
        ("es_ordem_cronologica", "valor_recebido_de_es_12_meses"),
        ("fidc_informe", "fundos_em_que_cede"),
        ("ratings", "rating_mais_recente"),
        ("rotulos_atraso", "atrasos_de_entrega_na_cvm"),
        ("cnpj_situacao_cadastral", "situacao_cadastral_na_receita"),
        ("pgfn_divida", "divida_ativa_em_cobranca"),
    ],
)
def test_tabela_fora_da_base_nao_vira_nao_consta(tmp_path, tabela, chave):
    with _porta(tmp_path, sem=(tabela,)) as p:
        f = _sinais(p, MUNDIAL)[chave]
    assert f.valor is None and f.motivo == fb.SEM_A_TABELA.format(tabela=tabela)


def test_sem_ipe_nem_insolvencia_na_base(tmp_path):
    with _porta(tmp_path, sem=("insolvencia", "eventos")) as p:
        f = _sinais(p, GPA)["insolvencia_24_meses"]
    assert f.valor is None and f.motivo == fb.SEM_A_TABELA.format(tabela="insolvencia")


def test_mei_nao_tem_sinal_nenhum(porta):
    for f in si.sinais_da_ficha(porta, MEI, DIA):
        assert f.valor is None and f.motivo == fb.COMO_PESSOA


# --- sem olhar o futuro ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def pasta(tmp_path_factory):
    return tmp_path_factory.mktemp("sinais")


@settings(max_examples=40, deadline=None)
@given(
    st.dates(date(2025, 6, 1), date(2027, 3, 31)),
    st.integers(0, 500),
    st.sampled_from([MUNDIAL, RD, GPA, MEI, NOVA, OUTRA]),
)
def test_cortar_o_futuro_nao_muda_o_passado(pasta, dia, dias_a_mais, cnpj):
    with (
        _porta(pasta) as completa,
        _porta(pasta, dia + timedelta(days=dias_a_mais)) as cortada,
    ):
        sinais = si.sinais_da_ficha(completa, cnpj, dia)
        assert si.sinais_da_ficha(cortada, cnpj, dia) == sinais
    fc.conferir_ponto_no_tempo(sinais, dia)


def test_a_ordem_das_linhas_nao_muda_os_sinais(tmp_path):
    embaralhadas = {
        nome: random.Random(7).sample(linhas, len(linhas))
        for nome, linhas in TABELAS.items()
    }
    extras = {nome: pd.DataFrame(linhas) for nome, linhas in embaralhadas.items()}
    with (
        Porta(tmp_path, arquivos={}, conferidas={}, extras=extras) as p,
        _porta(tmp_path) as q,
    ):
        for cnpj in (MUNDIAL, RD, GPA):
            assert si.sinais_da_ficha(p, cnpj, DIA) == si.sinais_da_ficha(q, cnpj, DIA)
