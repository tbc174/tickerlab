"""Dívida existente por emissor e perfil de vencimentos (B-21 do dossiê da plataforma, protótipo B).

Base de mentira pela porta (`base.porta`), sem internet: as ofertas da CVM viram `DebtInstrument`, e
o perfil soma o valor emitido por ano de vencimento e indexador, cada faixa com o rastro."""

import json
from datetime import date

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base.porta import Porta
from src.divida import (
    NAO_OBSERVADO,
    instrumentos_das_ofertas,
    instrumentos_do_emissor,
    perfil_de_vencimentos,
)
from src.divida.instrumentos import indexador_por_regra

CNPJ = "11.222.333/0001-81"
OUTRO_CNPJ = "44.555.666/0001-99"
DIA = date(2024, 6, 30)


def _antiga(**campos: object) -> dict:
    padrao = {
        "numero_processo": "RJ-2020-1",
        "numero_registro_oferta": "CVM/SRE/DEB/2020/001",
        "tipo_oferta": "Primária",
        "tipo_ativo": "DEBÊNTURES SIMPLES",
        "classe_ativo": None,
        "cnpj_emissor": CNPJ,
        "nome_emissor": "EMPRESA DE MENTIRA S.A.",
        "emissao": "1",
        "serie": "1",
        "data_emissao": "2020-01-15",
        "data_vencimento": "2027-01-15",
        "valor_total": 100_000_000.0,
        "atualizacao_monetaria": "IPCA",
        "juros": "6,50% a.a.",
        "anunciada_em": "2020-01-20",
        "disponivel_em": "2020-02-20",
    }
    return {**padrao, **campos}


def _nova(**campos: object) -> dict:
    padrao = {
        "numero_requerimento": "500",
        "cnpj_emissor": CNPJ,
        "nome_emissor": "EMPRESA DE MENTIRA S.A.",
        "valor_mobiliario": "Debêntures",
        "tipo_oferta": "PRIMARIA",
        "status_requerimento": "Oferta Encerrada",
        "emissao": "3",
        "valor_total_registrado": 50_000_000.0,
        "data_registro": "2023-05-02",
        "data_encerramento": "2023-05-10",
        "anunciada_em": "2023-05-02",
        "disponivel_em": "2023-05-10",
    }
    return {**padrao, **campos}


def _tabela(linhas: list[dict]) -> pd.DataFrame:
    tabela = pd.DataFrame(linhas)
    for coluna in tabela.columns:
        if coluna.startswith("data_") or coluna in ("anunciada_em", "disponivel_em"):
            tabela[coluna] = pd.to_datetime(tabela[coluna])
    return tabela


def _porta(tmp_path, antigas: list[dict], novas: list[dict]) -> Porta:
    """A porta com as duas tabelas de ofertas (vazia, mas com as colunas, quando não há linhas)."""
    return Porta(
        tmp_path,
        arquivos={},
        conferidas={},
        extras={
            "ofertas_antigas": _tabela(antigas or [_antiga()]).iloc[: len(antigas)],
            "ofertas_resolucao_160": _tabela(novas or [_nova()]).iloc[: len(novas)],
        },
    )


# --- o indexador por regra -------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("atualizacao", "juros", "esperado"),
    [
        ("IPCA", "7,90% a.a.", "ipca"),
        ("variação acumulada do IPCA", None, "ipca"),
        ("IGP-M", "12% aa", "igpm"),
        ("IGP M", None, "igpm"),
        (None, "102% DI", "cdi"),
        (None, "100% da Taxa DI", "cdi"),
        ("Não", "DI + 2,85 aa", "cdi"),
        (None, "CDI + 1,75", "cdi"),
        (None, "TJLP + 3,63% A.A.", "tjlp"),
        ("NÃO", "9,11% a.a.", "pre"),
        ("O Valor Nominal não será atualizado", "remuneração fixa 8,25% a.a", "pre"),
        ("Não Há", "11% ao ano", "pre"),
        # taxa fixa sem dizer que não há atualização: não dá para saber se é pré
        (None, "9,11% a.a.", NAO_OBSERVADO),
        (None, None, NAO_OBSERVADO),
        ("conforme escritura", "conforme escritura", NAO_OBSERVADO),
    ],
)
def test_indexador_sai_do_texto_da_cvm_por_regra(atualizacao, juros, esperado):
    assert indexador_por_regra(atualizacao, juros) == esperado


# --- os instrumentos ----------------------------------------------------------------------------
def test_debenture_da_oferta_antiga_vira_instrumento_com_rastro():
    (instrumento,) = instrumentos_das_ofertas(_tabela([_antiga()]), _tabela([]), CNPJ)
    assert instrumento.tipo == "debenture"
    assert instrumento.emissor_cnpj == "11222333000181"
    assert instrumento.indexador == "ipca"
    assert instrumento.remuneracao == "IPCA; 6,50% a.a."
    assert instrumento.valor_emitido == 100_000_000.0
    assert instrumento.saldo is None  # a oferta não diz quanto ainda se deve
    assert instrumento.emissao == date(2020, 1, 15)
    assert instrumento.vencimento == date(2027, 1, 15)
    assert instrumento.publico_em == date(2020, 2, 20)
    assert instrumento.rastro.fonte_id == "cvm-ofertas"
    assert instrumento.rastro.o_que_falta() == []
    assert "CVM/SRE/DEB/2020/001" in instrumento.rastro.documentos[0].nome


def test_so_entra_divida_primaria_do_proprio_emissor():
    antigas = [
        _antiga(tipo_ativo="NOTAS PROMISSÓRIAS", serie="A"),
        _antiga(tipo_ativo="NOTAS COMERCIAIS", serie="B"),
        _antiga(tipo_oferta="Secundária", serie="C"),  # não é dívida nova
        _antiga(tipo_ativo="AÇÕES ORDINÁRIAS", serie="D"),
        _antiga(tipo_ativo="CERTIFICADOS DE RECEBÍVEIS IMOBILIÁRIOS - CRI", serie="E"),
        _antiga(cnpj_emissor=OUTRO_CNPJ, serie="F"),
    ]
    novas = [
        _nova(valor_mobiliario="Notas Comerciais"),
        _nova(numero_requerimento="501", valor_mobiliario="Cotas de FIDC"),
    ]
    instrumentos = instrumentos_das_ofertas(_tabela(antigas), _tabela(novas), CNPJ)
    assert sorted(i.tipo for i in instrumentos) == [
        "nota_comercial",
        "nota_comercial",
        "nota_promissoria",
    ]


def test_oferta_da_160_so_conta_encerrada_e_sem_vencimento_fica_nao_observado():
    novas = [
        _nova(),
        _nova(numero_requerimento="501", status_requerimento="Oferta Revogada"),
        _nova(numero_requerimento="502", status_requerimento="Registro Concedido"),
    ]
    (instrumento,) = instrumentos_das_ofertas(_tabela([]), _tabela(novas), CNPJ)
    assert instrumento.instrumento_id == "cvm-ofertas/160/500"
    assert instrumento.vencimento is None
    assert instrumento.indexador == NAO_OBSERVADO
    assert instrumento.remuneracao is None
    assert instrumento.valor_emitido == 50_000_000.0


def test_valor_zero_e_nao_observado_nunca_zero():
    (instrumento,) = instrumentos_das_ofertas(
        _tabela([_antiga(valor_total=0.0)]), _tabela([]), CNPJ
    )
    assert instrumento.valor_emitido is None


def test_ids_das_linhas_repetidas_nao_se_confundem():
    linhas = [_antiga(valor_total=1.0), _antiga(valor_total=2.0)]
    instrumentos = instrumentos_das_ofertas(_tabela(linhas), _tabela([]), CNPJ)
    assert len({i.instrumento_id for i in instrumentos}) == 2


def test_instrumentos_do_emissor_pela_porta_como_era_em(tmp_path):
    antigas = [
        _antiga(),
        _antiga(serie="2", disponivel_em="2024-07-01", data_emissao="2024-06-01"),
    ]
    with _porta(tmp_path, antigas, [_nova()]) as p:
        instrumentos = instrumentos_do_emissor(p, "11222333000181", DIA)
    assert [i.instrumento_id for i in instrumentos] == [
        "cvm-ofertas/antigas/CVM/SRE/DEB/2020/001/1/1",
        "cvm-ofertas/160/500",
    ]


def test_instrumentos_do_emissor_recusa_o_que_nao_e_cnpj(tmp_path):
    with (
        _porta(tmp_path, [_antiga()], [_nova()]) as p,
        pytest.raises(ValueError, match="CNPJ"),
    ):
        instrumentos_do_emissor(p, "não é cnpj", DIA)


# --- o perfil de vencimentos --------------------------------------------------------------------
def _instrumentos(antigas: list[dict], novas: list[dict] | None = None) -> list:
    return instrumentos_das_ofertas(_tabela(antigas), _tabela(novas or []), CNPJ)


def test_perfil_soma_por_ano_de_vencimento_e_indexador():
    instrumentos = _instrumentos(
        [
            _antiga(serie="1", data_vencimento="2027-01-15", valor_total=100.0),
            _antiga(serie="2", data_vencimento="2027-07-15", valor_total=50.0),
            _antiga(
                serie="3",
                data_vencimento="2027-03-01",
                valor_total=30.0,
                atualizacao_monetaria=None,
                juros="105% DI",
            ),
            _antiga(serie="4", data_vencimento="2029-01-15", valor_total=20.0),
        ]
    )
    perfil = perfil_de_vencimentos(instrumentos, DIA)
    faixas = {(f.ano, f.indexador): f.valor_emitido for f in perfil.faixas}
    assert faixas == {(2027, "cdi"): 30.0, (2027, "ipca"): 150.0, (2029, "ipca"): 20.0}
    assert {f.ano: f.valor_emitido for f in perfil.por_ano} == {2027: 180.0, 2029: 20.0}


def test_perfil_deixa_de_fora_o_que_ja_venceu_e_separa_o_sem_vencimento():
    instrumentos = _instrumentos(
        [
            _antiga(serie="1", data_vencimento="2023-01-15"),  # venceu antes de D
            _antiga(serie="2", data_vencimento="2026-01-15", valor_total=10.0),
        ],
        [_nova(valor_total_registrado=7.0)],
    )
    perfil = perfil_de_vencimentos(instrumentos, DIA)
    assert [(f.ano, f.valor_emitido) for f in perfil.por_ano] == [
        (2026, 10.0),
        (None, 7.0),
    ]
    assert perfil.ja_vencidos == 1


def test_faixa_sem_valor_observado_conta_o_instrumento_mas_nao_soma():
    instrumentos = _instrumentos(
        [_antiga(serie="1", valor_total=0.0), _antiga(serie="2", valor_total=5.0)]
    )
    (faixa,) = perfil_de_vencimentos(instrumentos, DIA).faixas
    assert faixa.valor_emitido == 5.0
    assert len(faixa.instrumentos) == 2
    assert len(faixa.sem_valor) == 1


def test_toda_faixa_tem_rastro_completo_com_os_documentos_usados():
    instrumentos = _instrumentos(
        [_antiga(serie="1"), _antiga(serie="2", disponivel_em="2021-03-01")]
    )
    perfil = perfil_de_vencimentos(instrumentos, DIA)
    for faixa in (*perfil.faixas, *perfil.por_ano):
        assert faixa.rastro.o_que_falta() == []
        assert len(faixa.rastro.documentos) == 2
        assert faixa.rastro.publicado_em == date(2021, 3, 1)


def test_perfil_ignora_instrumento_que_ainda_nao_era_publico():
    instrumentos = _instrumentos([_antiga(disponivel_em="2024-07-01")])
    assert perfil_de_vencimentos(instrumentos, DIA).faixas == ()


def test_perfil_vira_json():
    perfil = perfil_de_vencimentos(_instrumentos([_antiga()]), DIA)
    texto = json.dumps(perfil.como_dict())
    assert '"como_era_em": "2024-06-30"' in texto
    assert perfil.limites  # o que o perfil não diz vem junto


# --- sem olhar o futuro (propriedade) -----------------------------------------------------------
DIAS = st.dates(min_value=date(2015, 1, 1), max_value=date(2030, 12, 31))


@settings(max_examples=25, deadline=None)
@given(
    linhas=st.lists(
        st.tuples(DIAS, DIAS, st.integers(1, 1_000)), min_size=1, max_size=10
    ),
    dia=DIAS,
)
def test_divida_emitida_depois_de_d_nao_aparece_em_d(tmp_path_factory, linhas, dia):
    """O que ficou público depois de D não entra, e cortar o futuro não muda o perfil de D."""
    antigas = [
        _antiga(
            serie=str(i),
            disponivel_em=str(publico),
            data_emissao=str(publico),
            data_vencimento=str(vencimento),
            valor_total=float(valor),
        )
        for i, (publico, vencimento, valor) in enumerate(linhas)
    ]
    pasta = tmp_path_factory.mktemp("base")
    with _porta(pasta, antigas, []) as p:
        instrumentos = instrumentos_do_emissor(p, CNPJ, dia)
    assert all(i.publico_em <= dia for i in instrumentos)
    passado = [a for a in antigas if date.fromisoformat(a["disponivel_em"]) <= dia]
    with _porta(pasta, passado, []) as p:
        cortados = instrumentos_do_emissor(p, CNPJ, dia)
    assert cortados == instrumentos
    assert perfil_de_vencimentos(cortados, dia) == perfil_de_vencimentos(
        instrumentos, dia
    )
