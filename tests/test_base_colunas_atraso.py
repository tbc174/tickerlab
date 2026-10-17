"""Colunas do modelo de atraso "como era na data" (modelo 8, critério de pronto, PR 3)."""

import io
import json
import zipfile
from datetime import UTC, datetime

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import fca_geral, historico
from base.modelos.atraso import colunas
from base.modelos.atraso.colunas import Fontes, colunas_como_era_na_data
from base.rotulos import EXTRAJUDICIAL, JUDICIAL, TERCEIRO
from scripts import montar_modelo_8

CIA = "11.111.111/0001-11"
FILIAL = "11.111.111/0002-00"  # a mesma companhia (mesma raiz do CNPJ)
OUTRA = "22.222.222/0001-22"
PREVISAO = pd.Timestamp("2022-03-31")
VESPERA = PREVISAO - pd.Timedelta(days=1)
DATAS = {
    "entregas": ["referencia", "prazo", "primeira_entrega"],
    "indice": ["publico_em"],
    "cadastro": ["registro", "cancelamento"],
    "fca_geral": ["referencia", "conhecido_em"],
    "valores": ["referencia", "publico_em", "fim_negociacao"],
    "auditores": ["referencia", "conhecido_em", "inicio", "fim"],
    "trocas": ["conhecido_em"],
    "insolvencia": ["conhecido_em"],
    "eventos": ["publicado_em"],
    "demonstracoes": ["inicio", "fim", "divulgado_em", "ate"],
}
COLUNAS_DAS_FONTES = {
    "entregas": ["cnpj", "documento", "referencia", "prazo", "primeira_entrega"],
    "indice": ["cnpj", "versao", "publico_em"],
    "cadastro": ["cnpj", "registro", "cancelamento"],
    "fca_geral": [
        "cnpj",
        "referencia",
        "versao",
        "conhecido_em",
        "categoria",
        "setor",
        "controle_acionario",
        "mes_fim_do_exercicio",
    ],
    "valores": [
        "cnpj",
        "referencia",
        "versao",
        "publico_em",
        "valor_mobiliario",
        "mercado",
        "segmento",
        "fim_negociacao",
    ],
    "auditores": [
        "cnpj",
        "referencia",
        "versao",
        "conhecido_em",
        "auditor_id",
        "inicio",
        "fim",
    ],
    "trocas": ["cnpj", "conhecido_em"],
    "insolvencia": ["cnpj", "rotulo", "conhecido_em"],
    "eventos": ["cnpj", "publicado_em"],
    "demonstracoes": [
        "cnpj",
        "grupo",
        "demonstracao",
        "conta",
        "descricao",
        "inicio",
        "fim",
        "valor",
        "divulgado_em",
        "ate",
    ],
}


def _tabela(nome: str, linhas: list[dict] | None = None) -> pd.DataFrame:
    tabela = pd.DataFrame(linhas or [], columns=COLUNAS_DAS_FONTES[nome])
    for coluna in DATAS[nome]:
        tabela[coluna] = pd.to_datetime(tabela[coluna])
    if nome == "demonstracoes":
        tabela = colunas.contas_do_balanco(tabela)
    return tabela


def _fontes(**linhas: list[dict]) -> Fontes:
    return Fontes(
        **{nome: _tabela(nome, linhas.get(nome)) for nome in COLUNAS_DAS_FONTES}
    )


def _exemplo(cnpj=CIA, documento="ITR", referencia=PREVISAO, prazo="2022-05-16"):
    return pd.DataFrame(
        {
            "cnpj": [cnpj],
            "documento": [documento],
            "referencia": [pd.Timestamp(referencia)],
            "data_da_previsao": [pd.Timestamp(referencia)],
            "prazo": [pd.Timestamp(prazo)],
        }
    )


def _uma(fontes: Fontes, exemplo: pd.DataFrame | None = None) -> pd.Series:
    resultado = colunas_como_era_na_data(
        _exemplo() if exemplo is None else exemplo, fontes
    )
    assert len(resultado) == 1
    return resultado.iloc[0]


def _entrega(referencia, prazo, entrega, documento="ITR", cnpj=CIA):
    return {
        "cnpj": cnpj,
        "documento": documento,
        "referencia": referencia,
        "prazo": prazo,
        "primeira_entrega": entrega,
    }


def _fca(
    conhecido_em, setor="Energia Elétrica", referencia="2021-01-01", versao=1, **mais
):
    return {
        "cnpj": CIA,
        "referencia": referencia,
        "versao": versao,
        "conhecido_em": conhecido_em,
        "categoria": "A",
        "setor": setor,
        "controle_acionario": "Privado",
        "mes_fim_do_exercicio": 12,
        **mais,
    }


def _conta(demonstracao, conta, descricao, valor, divulgado_em, ate=None, **mais):
    return {
        "cnpj": CIA,
        "grupo": "con",
        "demonstracao": demonstracao,
        "conta": conta,
        "descricao": descricao,
        "inicio": "2021-01-01",
        "fim": "2021-12-31",
        "valor": valor,
        "divulgado_em": divulgado_em,
        "ate": ate,
        **mais,
    }


def _tudo_no_dia(dia: str) -> dict[str, list[dict]]:
    """Um fato de cada fonte, todos públicos em `dia`."""
    return {
        "entregas": [_entrega("2021-12-31", dia, dia, documento="DFP")],
        "indice": [{"cnpj": CIA, "versao": 2, "publico_em": dia}],
        "fca_geral": [_fca(dia)],
        "valores": [
            {
                "cnpj": CIA,
                "referencia": "2021-01-01",
                "versao": 1,
                "publico_em": dia,
                "valor_mobiliario": "Ações Ordinárias",
                "mercado": "Bolsa",
                "segmento": "Novo Mercado",
                "fim_negociacao": None,
            }
        ],
        "auditores": [
            {
                "cnpj": CIA,
                "referencia": "2021-01-01",
                "versao": 1,
                "conhecido_em": dia,
                "auditor_id": "rede:kpmg",
                "inicio": "2015-01-01",
                "fim": None,
            }
        ],
        "trocas": [{"cnpj": CIA, "conhecido_em": dia}],
        "insolvencia": [{"cnpj": CIA, "rotulo": JUDICIAL, "conhecido_em": dia}],
        "eventos": [{"cnpj": CIA, "publicado_em": dia}],
        "demonstracoes": [
            _conta("BPA", "1", "Ativo Total", 1000.0, dia),
            _conta("BPP", "2.03", "Patrimônio Líquido Consolidado", -5.0, dia),
        ],
        "cadastro": [{"cnpj": CIA, "registro": dia, "cancelamento": None}],
    }


def test_coluna_ignora_fato_publicado_no_dia():
    """A CVM só dá o dia: o que ficou público no próprio dia da previsão não entra (vale a véspera)."""
    sem_nada = _uma(_fontes())
    no_dia = _uma(_fontes(**_tudo_no_dia(PREVISAO.date().isoformat())))
    pd.testing.assert_series_equal(no_dia, sem_nada)
    na_vespera = _uma(_fontes(**_tudo_no_dia(VESPERA.date().isoformat())))
    mudaram = [
        c
        for c in colunas.COLUNAS_PARA_PREVER
        if not _iguais(na_vespera[c], sem_nada[c])
    ]
    # tudo o que tem data pública muda quando o fato é da véspera (o calendário não tem data; o
    # exemplo não tem caixa, dívida nem DRE)
    assert set(mudaram) == set(colunas.COLUNAS_PARA_PREVER) - set(
        colunas.CALENDARIO
    ) - {
        "divida_curto_prazo_sobre_caixa",
        "prejuizo_no_ultimo_exercicio",
    }


def _iguais(a, b) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return a == b


def test_atrasou_o_anterior_nao_conta_o_proprio():
    """O próprio documento (atrasado) não é "o anterior"; o anterior entregue no prazo vale False."""
    fontes = _fontes(
        entregas=[
            _entrega("2021-09-30", "2021-11-16", "2021-11-10"),
            _entrega("2022-03-31", "2022-05-16", "2022-06-30"),  # o próprio, atrasado
        ]
    )
    linha = _uma(fontes)
    assert linha["documentos_anteriores"] == 1
    assert linha["atrasou_o_anterior"] is False or not linha["atrasou_o_anterior"]
    assert linha["atrasos_nos_ultimos_4"] == 0
    assert linha["folga_media_ultimos_4"] > 0


def test_historico_ve_o_atraso_como_era_na_vespera():
    """Um anterior com o prazo vencido e sem entrega na véspera já é atraso, contado até a previsão;
    um com o prazo ainda aberto não se sabe e fica de fora."""
    fontes = _fontes(
        entregas=[
            _entrega("2021-06-30", "2021-08-16", "2021-08-16"),  # no último dia
            # vence antes da previsão, entregue só depois: na véspera, atrasado havia 10 dias úteis
            _entrega("2021-09-30", "2022-03-17", "2022-04-20"),
            # DFP com o prazo na própria previsão, ainda sem entrega: não se sabe
            _entrega("2021-12-31", "2022-03-31", "2022-04-05", documento="DFP"),
        ]
    )
    linha = _uma(fontes)
    assert linha["documentos_anteriores"] == 2
    assert linha["atrasou_o_anterior"]
    assert linha["atrasos_nos_ultimos_4"] == 1
    assert not linha["entregou_o_anterior_no_ultimo_dia"]
    assert linha["media_dias_de_atraso_ultimos_4"] == pytest.approx((0 + 10) / 2)


def test_ultimos_4_e_8_e_reapresentacoes_em_12_meses():
    trimestres = pd.date_range("2019-03-31", "2021-12-31", freq="QE")
    entregas = [
        _entrega(
            r, r + pd.Timedelta(days=45), r + pd.Timedelta(days=50 if i % 2 else 40)
        )
        for i, r in enumerate(trimestres)
    ]
    fontes = _fontes(
        entregas=entregas,
        indice=[
            {"cnpj": CIA, "versao": 2, "publico_em": "2021-01-10"},  # mais de 12 meses
            {"cnpj": CIA, "versao": 2, "publico_em": "2021-06-10"},
            {
                "cnpj": CIA,
                "versao": 1,
                "publico_em": "2021-07-10",
            },  # 1ª versão: não é reapresentação
            {"cnpj": OUTRA, "versao": 3, "publico_em": "2021-07-10"},
        ],
    )
    linha = _uma(fontes)
    assert linha["documentos_anteriores"] == len(trimestres)
    assert linha["atrasos_nos_ultimos_4"] == 2
    assert linha["atrasos_nos_ultimos_8"] == 4
    assert linha["reapresentacoes_12_meses"] == 1


def test_sem_historico_fica_vazio():
    linha = _uma(_fontes())
    assert linha["documentos_anteriores"] == 0
    assert pd.isna(linha["atrasou_o_anterior"])
    assert pd.isna(linha["atrasos_nos_ultimos_4"])


def test_setor_vem_do_fca_vigente_na_data_e_nao_do_de_hoje():
    """O FCA mais novo (referência e versão) já público vale; o entregue depois, não; e uma reentrega
    de ano antigo não volta no tempo."""
    fontes = _fontes(
        fca_geral=[
            _fca("2020-05-31", setor="Energia Elétrica", referencia="2020-01-01"),
            _fca(
                "2021-05-31",
                setor="Saneamento",
                referencia="2021-01-01",
                mes_fim_do_exercicio=6,
            ),
            _fca("2022-01-10", setor="Bancos", referencia="2019-01-01", versao=4),
            _fca("2022-05-31", setor="Telecomunicações", referencia="2022-01-01"),
        ],
        cadastro=[
            {"cnpj": CIA, "registro": "2000-03-31", "cancelamento": "2005-01-01"},
            {"cnpj": CIA, "registro": "2012-03-30", "cancelamento": None},
            {"cnpj": CIA, "registro": "2023-01-01", "cancelamento": None},
        ],
    )
    linha = _uma(fontes)
    assert linha["setor"] == "Saneamento"
    assert linha["categoria"] == "A"
    assert linha["controle_acionario"] == "Privado"
    assert linha["exercicio_fora_de_dezembro"]
    # do último registro antes da previsão (o de 2023 ainda não existia)
    assert linha["anos_de_registro"] == pytest.approx(10.0, abs=0.01)


def test_acao_na_bolsa_e_segmento_do_fca_vigente():
    def _valor(publico_em, versao, valor="Ações Ordinárias", mercado="Bolsa", fim=None):
        return {
            "cnpj": CIA,
            "referencia": "2021-01-01",
            "versao": versao,
            "publico_em": publico_em,
            "valor_mobiliario": valor,
            "mercado": mercado,
            "segmento": "Novo Mercado",
            "fim_negociacao": fim,
        }

    fca = [_fca("2021-05-31")]
    com_acao = _uma(_fontes(fca_geral=fca, valores=[_valor("2021-05-31", 1)]))
    assert com_acao["tem_acao_na_bolsa"]
    assert com_acao["segmento_de_listagem"] == "Novo Mercado"
    so_debenture = _uma(
        _fontes(
            fca_geral=fca,
            valores=[_valor("2021-05-31", 1, "Debêntures", "Balcão Organizado")],
        )
    )
    assert not so_debenture["tem_acao_na_bolsa"]
    assert pd.isna(so_debenture["segmento_de_listagem"])
    # a versão 2 (pública antes da previsão) tira a ação da bolsa: vale ela
    deslistada = _uma(
        _fontes(
            fca_geral=fca,
            valores=[
                _valor("2021-05-31", 1),
                _valor("2021-10-01", 2, fim="2021-09-30"),
            ],
        )
    )
    assert not deslistada["tem_acao_na_bolsa"]
    assert pd.isna(_uma(_fontes())["tem_acao_na_bolsa"])


def test_auditor_grande_anos_com_ele_e_troca_anunciada():
    def _mandato(auditor_id, inicio, fim=None, conhecido_em="2021-05-31"):
        return {
            "cnpj": CIA,
            "referencia": "2021-01-01",
            "versao": 1,
            "conhecido_em": conhecido_em,
            "auditor_id": auditor_id,
            "inicio": inicio,
            "fim": fim,
        }

    fontes = _fontes(
        auditores=[
            _mandato("cvm:123", "2010-01-01", "2016-03-31"),
            _mandato("rede:kpmg", "2016-04-01"),
        ],
        trocas=[
            {"cnpj": CIA, "conhecido_em": "2016-05-31"},
            {"cnpj": CIA, "conhecido_em": "2022-04-01"},  # depois da previsão
        ],
    )
    linha = _uma(fontes)
    assert linha["auditor_rede_grande"]
    assert linha["anos_com_o_auditor"] == pytest.approx(6.0, abs=0.01)
    assert not linha["trocou_de_auditor_12_meses"]
    trocou = _uma(
        _fontes(
            auditores=[_mandato("cvm:123", "2021-04-01")],
            trocas=[{"cnpj": CIA, "conhecido_em": "2021-05-31"}],
        )
    )
    assert not trocou["auditor_rede_grande"]
    assert trocou["trocou_de_auditor_12_meses"]
    assert pd.isna(_uma(_fontes())["trocou_de_auditor_12_meses"])


def test_recuperacao_judicial_so_da_propria_companhia_pela_raiz():
    """Decisão de 17/10/2026: só a recuperação judicial da própria companhia (filiais juntas pela
    raiz do CNPJ), sem a extrajudicial e sem a exposição a outra empresa."""
    eventos = [{"cnpj": CIA, "publicado_em": "2015-01-10"}]

    def _com(*insolvencia):
        return _uma(_fontes(eventos=eventos, insolvencia=list(insolvencia)))

    assert not _com()["ja_entrou_em_recuperacao_judicial"]
    assert _com({"cnpj": FILIAL, "rotulo": JUDICIAL, "conhecido_em": "2016-06-20"})[
        "ja_entrou_em_recuperacao_judicial"
    ]
    for outra in (
        {"cnpj": OUTRA, "rotulo": JUDICIAL, "conhecido_em": "2016-06-20"},
        {"cnpj": CIA, "rotulo": EXTRAJUDICIAL, "conhecido_em": "2016-06-20"},
        {"cnpj": CIA, "rotulo": TERCEIRO, "conhecido_em": "2016-06-20"},
        {"cnpj": CIA, "rotulo": JUDICIAL, "conhecido_em": "2022-04-01"},
    ):
        assert not _com(outra)["ja_entrou_em_recuperacao_judicial"]
    # sem nenhum documento no IPE antes da previsão: não dá para dizer "nunca"
    assert pd.isna(_uma(_fontes())["ja_entrou_em_recuperacao_judicial"])


def test_reapresentacao_do_balanco_depois_da_previsao_nao_aparece():
    fontes = _fontes(
        demonstracoes=[
            _conta("BPA", "1", "Ativo Total", 1000.0, "2022-02-20", ate="2022-04-10"),
            _conta(
                "BPA", "1", "Ativo Total", 9999.0, "2022-04-10"
            ),  # reapresentado depois
            _conta("BPP", "2.03", "Patrimônio Líquido Consolidado", 50.0, "2022-02-20"),
            _conta("BPP", "2.03", "Patrimônio Líquido Consolidado", -1.0, "2022-04-10"),
        ]
    )
    linha = _uma(fontes)
    assert linha["ativo_total"] == 1000.0
    assert not linha["patrimonio_liquido_negativo"]


def test_balanco_usa_o_ultimo_consolidado_e_o_ultimo_exercicio():
    def _trimestre(fim, **mais):
        return {"fim": fim, "inicio": fim, **mais}

    fontes = _fontes(
        demonstracoes=[
            _conta(
                "BPA", "1", "Ativo Total", 1.0, "2021-11-10", **_trimestre("2021-09-30")
            ),
            _conta(
                "BPA",
                "1",
                "Ativo Total",
                7.0,
                "2021-11-10",
                grupo="ind",
                **_trimestre("2021-09-30"),
            ),
            _conta(
                "BPA",
                "1.01.01",
                "Caixa e Equivalentes de Caixa",
                20.0,
                "2021-11-10",
                **_trimestre("2021-09-30"),
            ),
            _conta(
                "BPP",
                "2.01.04",
                "Empréstimos e Financiamentos",
                50.0,
                "2021-11-10",
                **_trimestre("2021-09-30"),
            ),
            _conta(
                "BPA", "1", "Ativo Total", 2.0, "2021-08-10", **_trimestre("2021-06-30")
            ),
            # DRE de 12 meses (2020) com prejuízo; a de 9 meses (2021) com lucro não é exercício
            _conta(
                "DRE",
                "3.11",
                "Lucro/Prejuízo Consolidado do Período",
                -3.0,
                "2021-03-20",
                inicio="2020-01-01",
                fim="2020-12-31",
            ),
            _conta(
                "DRE",
                "3.09",
                "Resultado Líquido das Operações Continuadas",
                9.0,
                "2021-03-20",
                inicio="2020-01-01",
                fim="2020-12-31",
            ),
            _conta(
                "DRE",
                "3.11",
                "Lucro/Prejuízo Consolidado do Período",
                4.0,
                "2021-11-10",
                inicio="2021-01-01",
                fim="2021-09-30",
            ),
        ]
    )
    linha = _uma(fontes)
    assert linha["ativo_total"] == 1.0
    assert linha["divida_curto_prazo_sobre_caixa"] == pytest.approx(2.5)
    assert linha["prejuizo_no_ultimo_exercicio"]
    assert pd.isna(linha["patrimonio_liquido_negativo"])


def test_divida_sobre_caixa_fica_vazia_sem_caixa():
    fontes = _fontes(
        demonstracoes=[
            _conta(
                "BPA", "1.01.01", "Caixa e Equivalentes de Caixa", 0.0, "2022-02-20"
            ),
            _conta(
                "BPP", "2.01.04", "Empréstimos e Financiamentos", 50.0, "2022-02-20"
            ),
        ]
    )
    assert pd.isna(_uma(fontes)["divida_curto_prazo_sobre_caixa"])


def test_calendario_trimestre_e_prazo_perto_de_feriado():
    perto = _uma(_fontes(), _exemplo(prazo="2022-04-25"))  # Tiradentes em 21/04
    assert perto["trimestre"] == 1
    assert perto["prazo_perto_de_feriado"]
    longe = _uma(_fontes(), _exemplo(referencia="2022-06-30", prazo="2022-08-15"))
    assert longe["trimestre"] == 2
    assert not longe["prazo_perto_de_feriado"]


def test_sem_exemplos_devolve_tabela_vazia_com_as_colunas():
    vazio = _exemplo().iloc[0:0]
    resultado = colunas_como_era_na_data(vazio, _fontes())
    assert list(resultado.columns) == list(colunas.COLUNAS)
    assert resultado.empty


# ---- propriedade: cortar o futuro das fontes não muda nenhuma coluna ----

DIAS = st.dates(
    min_value=pd.Timestamp("2020-01-01").date(),
    max_value=pd.Timestamp("2023-12-31").date(),
)
EMPRESAS = st.sampled_from([CIA, FILIAL, OUTRA])


def _cortar(fontes: Fontes, dia: pd.Timestamp) -> Fontes:
    """As fontes como estavam antes de `dia`: cada fato com data pública >= `dia` sai, e as datas de
    fim e de entrega que ainda não tinham acontecido ficam vazias."""
    entregas = fontes.entregas[
        (fontes.entregas["primeira_entrega"] < dia) | (fontes.entregas["prazo"] < dia)
    ].copy()
    entregas.loc[entregas["primeira_entrega"] >= dia, "primeira_entrega"] = pd.NaT
    demonstracoes = fontes.demonstracoes[
        fontes.demonstracoes["divulgado_em"] < dia
    ].copy()
    demonstracoes.loc[demonstracoes["ate"] >= dia, "ate"] = pd.NaT
    cadastro = fontes.cadastro[fontes.cadastro["registro"] < dia].copy()
    cadastro.loc[cadastro["cancelamento"] >= dia, "cancelamento"] = pd.NaT

    def antes(tabela: pd.DataFrame, data: str) -> pd.DataFrame:
        return tabela[tabela[data] < dia]

    return Fontes(
        entregas=entregas,
        indice=antes(fontes.indice, "publico_em"),
        cadastro=cadastro,
        fca_geral=antes(fontes.fca_geral, "conhecido_em"),
        valores=antes(fontes.valores, "publico_em"),
        auditores=antes(fontes.auditores, "conhecido_em"),
        trocas=antes(fontes.trocas, "conhecido_em"),
        insolvencia=antes(fontes.insolvencia, "conhecido_em"),
        eventos=antes(fontes.eventos, "publicado_em"),
        demonstracoes=demonstracoes,
    )


@st.composite
def _fontes_ao_acaso(desenho) -> Fontes:
    def dia():
        return desenho(DIAS).isoformat()

    def talvez_dia():
        return desenho(st.one_of(st.none(), DIAS.map(lambda d: d.isoformat())))

    n = st.integers(0, 4)
    entregas = []
    for _ in range(desenho(n)):
        referencia = pd.Timestamp(desenho(DIAS)) + pd.offsets.QuarterEnd(0)
        entregas.append(
            _entrega(
                referencia.date().isoformat(),
                (referencia + pd.Timedelta(days=45)).date().isoformat(),
                talvez_dia(),
                cnpj=desenho(EMPRESAS),
            )
        )
    referencias = st.sampled_from(["2020-01-01", "2021-01-01", "2022-01-01"])
    return _fontes(
        entregas=entregas,
        indice=[
            {
                "cnpj": desenho(EMPRESAS),
                "versao": desenho(st.integers(1, 3)),
                "publico_em": dia(),
            }
            for _ in range(desenho(n))
        ],
        cadastro=[
            {"cnpj": CIA, "registro": dia(), "cancelamento": talvez_dia()}
            for _ in range(desenho(n))
        ],
        fca_geral=[
            _fca(
                dia(),
                setor=desenho(st.sampled_from(["A", "B"])),
                referencia=desenho(referencias),
                versao=desenho(st.integers(1, 2)),
                mes_fim_do_exercicio=desenho(st.sampled_from([6, 12])),
            )
            for _ in range(desenho(n))
        ],
        valores=[
            {
                "cnpj": CIA,
                "referencia": desenho(referencias),
                "versao": desenho(st.integers(1, 2)),
                "publico_em": dia(),
                "valor_mobiliario": "Ações Ordinárias",
                "mercado": "Bolsa",
                "segmento": desenho(st.sampled_from(["Novo Mercado", "Nível 1"])),
                "fim_negociacao": talvez_dia(),
            }
            for _ in range(desenho(n))
        ],
        auditores=[
            {
                "cnpj": CIA,
                "referencia": desenho(referencias),
                "versao": 1,
                "conhecido_em": dia(),
                "auditor_id": desenho(st.sampled_from(["rede:kpmg", "cvm:1"])),
                "inicio": dia(),
                "fim": talvez_dia(),
            }
            for _ in range(desenho(n))
        ],
        trocas=[{"cnpj": CIA, "conhecido_em": dia()} for _ in range(desenho(n))],
        insolvencia=[
            {
                "cnpj": desenho(EMPRESAS),
                "rotulo": desenho(st.sampled_from([JUDICIAL, EXTRAJUDICIAL])),
                "conhecido_em": dia(),
            }
            for _ in range(desenho(n))
        ],
        eventos=[
            {"cnpj": desenho(EMPRESAS), "publicado_em": dia()}
            for _ in range(desenho(n))
        ],
        demonstracoes=[
            _conta(
                "BPA",
                "1",
                "Ativo Total",
                desenho(st.floats(-10, 10, allow_nan=False)),
                dia(),
                ate=talvez_dia(),
                fim=desenho(DIAS).isoformat(),
            )
            for _ in range(desenho(n))
        ],
    )


@settings(max_examples=60, deadline=None)
@given(fontes=_fontes_ao_acaso(), previsao=DIAS)
def test_toda_coluna_usa_so_fatos_publicos_antes_da_previsao(fontes, previsao):
    """Propriedade: tirar das fontes tudo o que ficou público na previsão ou depois não muda nada."""
    previsao = pd.Timestamp(previsao)
    exemplo = _exemplo(referencia=previsao, prazo=previsao + pd.Timedelta(days=45))
    pd.testing.assert_frame_equal(
        colunas_como_era_na_data(exemplo, fontes),
        colunas_como_era_na_data(exemplo, _cortar(fontes, previsao)),
    )


# ---- leitor do FCA geral (tabela histórica `fca_geral`) ----

PRINCIPAL = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC"
)
GERAL = (
    "CNPJ_Companhia;Data_Referencia;Versao;ID_Documento;Nome_Empresarial;Data_Registro_CVM;"
    "Categoria_Registro_CVM;Situacao_Registro_CVM;Setor_Atividade;Especie_Controle_Acionario;"
    "Dia_Encerramento_Exercicio_Social;Mes_Encerramento_Exercicio_Social"
)


def _zip_do_fca(principal: list[str], geral: list[str], ano=2021) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            f"fca_cia_aberta_{ano}.csv",
            "\n".join([PRINCIPAL, *principal]).encode("latin-1"),
        )
        z.writestr(
            f"fca_cia_aberta_geral_{ano}.csv",
            "\n".join([GERAL, *geral]).encode("latin-1"),
        )
    return saida.getvalue()


def test_ler_geral_do_fca_com_a_data_de_entrega():
    conteudo = _zip_do_fca(
        [
            f"{CIA};2021-01-01;2;EMPRESA UM;001;FCA;10;2021-06-01;http://rad/10",
            f"{OUTRA};2021-01-01;1;EMPRESA DOIS;002;FCA;11;2021-05-20;http://rad/11",
            f"{OUTRA};2021-01-01;1;EMPRESA DOIS;002;FCA;12;2021-07-01;http://rad/12",
        ],
        [
            (
                f"{CIA};2021-01-01;2;10;EMPRESA UM;2001-01-01;Categoria A;Ativo;Energia Elétrica;"
                "Privado Holding;31;12"
            ),
            f"{OUTRA};2021-01-01;1;11;EMPRESA DOIS;2001-01-01;Categoria B;Ativo;;Estatal;30;6",
            # a mesma versão entregue de novo: vale a primeira entrega
            f"{OUTRA};2021-01-01;1;12;EMPRESA DOIS;2001-01-01;Categoria B;Ativo;;Estatal;30;6",
        ],
    )
    tabela = fca_geral.ler_geral_do_fca(conteudo)
    assert list(tabela.columns) == list(fca_geral.COLUNAS)
    assert len(tabela) == 2
    cia = tabela[tabela["cnpj"] == CIA].iloc[0]
    assert cia["conhecido_em"] == pd.Timestamp("2021-06-01").date()
    assert cia["categoria"] == "A"
    assert cia["setor"] == "Energia Elétrica"
    assert cia["controle_acionario"] == "Privado Holding"
    assert cia["mes_fim_do_exercicio"] == 12
    outra = tabela[tabela["cnpj"] == OUTRA].iloc[0]
    assert outra["id_documento"] == "11"
    assert outra["categoria"] == "B"
    assert pd.isna(outra["setor"])
    assert outra["mes_fim_do_exercicio"] == 6


def test_fca_geral_e_tabela_historica_com_data_publica():
    tabela = historico.TABELAS["fca_geral"]
    assert tabela.fonte == "cvm-hist-fca"
    assert tabela.data_publica == "conhecido_em"


# ---- montagem a partir da base ----


def test_montar_grava_uma_linha_por_exemplo_com_manifesto(tmp_path, monkeypatch):
    rotulos = pd.DataFrame(
        {
            "cnpj": [CIA, CIA],
            "empresa": ["EMPRESA UM", "EMPRESA UM"],
            "documento": ["ITR", "ITR"],
            "referencia": pd.to_datetime(["2021-09-30", "2022-03-31"]),
            "data_da_previsao": pd.to_datetime(["2021-09-30", "2022-03-31"]),
            "prazo": pd.to_datetime(["2021-11-16", "2022-05-16"]),
            "primeira_entrega": pd.to_datetime(["2021-11-20", "2022-05-10"]),
        }
    )
    (tmp_path / "rotulos_atraso").mkdir()
    rotulos.to_parquet(tmp_path / "rotulos_atraso" / "rotulos_atraso.parquet")
    (tmp_path / "fca_geral").mkdir()
    pd.DataFrame([_fca("2021-05-31")]).to_parquet(
        tmp_path / "fca_geral" / "2021.parquet"
    )
    indice = pd.DataFrame(
        {"cnpj": [CIA], "versao": [2], "recebido_em": pd.to_datetime(["2021-12-01"])}
    )
    cadastro = pd.DataFrame(
        {
            "cnpj": [CIA],
            "registro": pd.to_datetime(["2001-01-01"]),
            "cancelamento": [pd.NaT],
        }
    )
    monkeypatch.setattr(
        colunas.rotulo,
        "ler_indices",
        lambda _c: (indice, {}, [{"url": "i", "sha256": "1"}]),
    )
    monkeypatch.setattr(
        montar_modelo_8,
        "cadastro_do_acervo",
        lambda _c: (cadastro, {"url": "c", "sha256": "2"}),
    )
    agora = datetime(2026, 10, 17, 12, tzinfo=UTC)

    assert montar_modelo_8.montar_colunas(None, tmp_path, agora) == 2  # type: ignore[arg-type]

    gravada = pd.read_parquet(tmp_path / "colunas_atraso" / "colunas_atraso.parquet")
    assert len(gravada) == 2
    segunda = gravada.sort_values("referencia").iloc[1]
    assert segunda["atrasou_o_anterior"]
    assert segunda["reapresentacoes_12_meses"] == 1
    assert segunda["setor"] == "Energia Elétrica"
    manifesto = json.loads(
        (tmp_path / "colunas_atraso" / "colunas_atraso.json").read_text(
            encoding="utf-8"
        )
    )
    urls = {o["url"] for o in manifesto["origens"]}
    assert {
        "rotulos_atraso/rotulos_atraso.parquet",
        "fca_geral/2021.parquet",
        "i",
        "c",
    } <= urls


def test_montar_sem_rotulo_nao_grava(tmp_path, monkeypatch):
    monkeypatch.setattr(colunas.rotulo, "ler_indices", lambda _c: (None, {}, []))
    monkeypatch.setattr(montar_modelo_8, "cadastro_do_acervo", lambda _c: None)
    assert montar_modelo_8.montar_colunas(None, tmp_path, datetime.now(UTC)) == 0  # type: ignore[arg-type]
    assert not (tmp_path / "colunas_atraso").exists()
