"""As duas seções da virada de 5/11/2026 (fase 1, PR 2): dívida ativa com a União (PGFN) e entrega das
demonstrações no prazo (`rotulos_atraso`), na ficha como fato datado.

A PGFN e a CVM dizem; a ficha copia com a data do fato, o dia em que ficou público, o veículo e o link,
e mostra a regra que deu o rótulo. Não avalia, não dá nota, não olha o futuro, não cita pessoa. Sem
linha, diz "sem inscrição" (ou "sem documento devido") com o dia; sem a tabela na base, não há seção.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from base import dossie
from base.contrapartes import cafe
from src import amostra_do_relatorio
from src import dossie as dossie_do_app
from src import relatorio_empresa_markdown as markdown
from src.prazos import ATRASO_GRAVE, DIAS_DO_ITR, MESES_DO_DFP, ZONA_CINZENTA
from src.relatorio_empresa import ORDEM_DAS_SECOES

D = pd.Timestamp
HOJE = D("2026-10-17")
CNPJ = "02429144000193"
SHA = "a" * 64
MONTADA_EM = "2026-10-21T00:00:00-03:00"  # o dia em que a tabela de rótulos foi montada
VEDADAS = cafe.VEDADAS_DA_ADR_0103
JULGAMENTOS = ("avaliamos", "classificamos", "nota ", "risco", "sinal")
ENDERECO_DAS_ENTREGAS = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/"

# linhas da PGFN além da linha-base de `_pgfn` (o retrato de 30/09/2026, público em 10/10/2026)
FGTS = {"tipo_divida": "fgts", "inscricoes": 1, "valor_consolidado": 300_000.0}
RETRATO_ANTIGO = {
    "data_do_retrato": D("2026-06-30"),
    "disponivel_em": D("2026-07-10"),
    "inscricoes": 9,
    "valor_consolidado": 9_000_000.0,
}
RETRATO_FUTURO = {
    "data_do_retrato": D("2026-12-31"),
    "disponivel_em": D("2027-01-10"),
    "valor_consolidado": 7_777_777.0,
}

# linhas de `rotulos_atraso` além da linha-base de `_rotulos` (a DFP de 2025, no prazo)
ZONA = {
    "documento": "ITR",
    "referencia": D("2026-03-31"),
    "prazo": D("2026-05-15"),
    "primeira_entrega": D("2026-05-18"),
    "dias_uteis_de_atraso": 1,
    "atrasou": True,
    "zona_cinzenta": True,
}
GRAVE = {
    "documento": "DFP",
    "referencia": D("2024-12-31"),
    "prazo": D("2025-03-31"),
    "primeira_entrega": D("2025-05-30"),
    "dias_uteis_de_atraso": 41,
    "atrasou": True,
    "atraso_grave": True,
}
ATRASADA = {
    "documento": "ITR",
    "referencia": D("2025-09-30"),
    "prazo": D("2025-11-14"),
    "primeira_entrega": D("2025-11-21"),
    "dias_uteis_de_atraso": 4,
    "atrasou": True,
}
ENTREGUE_DEPOIS_DE_HOJE = {  # o ITR do 2T26, entregue em 20/10: a ficha de 17/10 não pode saber
    "documento": "ITR",
    "referencia": D("2026-06-30"),
    "prazo": D("2026-08-14"),
    "primeira_entrega": D("2026-10-20"),
    "dias_uteis_de_atraso": 45,
    "atrasou": True,
    "atraso_grave": True,
}
VENCIDA_SEM_ENTREGA = {  # a mesma linha, como a tabela a via antes da entrega
    **ENTREGUE_DEPOIS_DE_HOJE,
    "primeira_entrega": pd.NaT,
    "dias_uteis_de_atraso": 44,
}
PRAZO_NO_FUTURO = {
    "documento": "ITR",
    "referencia": D("2026-09-30"),
    "prazo": D("2026-11-16"),
    "primeira_entrega": pd.NaT,
    "dias_uteis_de_atraso": 0,
    "atrasou": True,
    "atraso_grave": True,
}
DIAS_UTEIS_ATE_HOJE = (
    44  # de 14/08/2026 (conta) a 17/10/2026 (não conta), sem 7/9 e 12/10
)


def _pgfn(*linhas: dict) -> pd.DataFrame:
    base = {
        "cnpj_basico": CNPJ[:8],
        "tipo_divida": "nao_previdenciaria",
        "regiao": "SP",
        "tipo_devedor": "principal",
        "tipo_situacao": "Em cobrança",
        "situacao_inscricao": "ATIVA EM COBRANCA",
        "ajuizado": True,
        "inscricoes": 3,
        "valor_consolidado": 1_200_000.0,
        "data_do_retrato": D("2026-09-30"),
        "disponivel_em": D("2026-10-10"),
        "origem_sha256": SHA,
    }
    return pd.DataFrame([{**base, **linha} for linha in linhas or ({},)])


def _rotulos(*linhas: dict) -> pd.DataFrame:
    base = {
        "cnpj": "02.429.144/0001-93",
        "empresa": "CPFL ENERGIA S.A.",
        "documento": "DFP",
        "referencia": D("2025-12-31"),
        "prazo": D("2026-03-31"),
        "primeira_entrega": D("2026-03-27"),
        "dias_uteis_de_atraso": 0,
        "atrasou": False,
        "atraso_grave": False,
        "zona_cinzenta": False,
        "montado_em": MONTADA_EM,
    }
    return pd.DataFrame([{**base, **linha} for linha in linhas or ({},)])


def _divida(pgfn: pd.DataFrame, hoje: pd.Timestamp = HOJE) -> dict:
    secao = dossie.secao_divida_com_a_uniao(pgfn, hoje)
    assert secao is not None
    return secao


def _entregas(rotulos: pd.DataFrame, hoje: pd.Timestamp = HOJE) -> dict:
    secao = dossie.secao_entrega_das_demonstracoes(rotulos, hoje)
    assert secao is not None
    return secao


def _inscricoes(secao: dict) -> list[dict]:
    return secao["tabelas"].get("inscricoes_na_divida_ativa", [])


def _linhas(secao: dict) -> list[dict]:
    return secao["tabelas"].get("entregas_de_dfp_e_itr", [])


def _as_duas_secoes() -> list[dict]:
    return [
        _divida(_pgfn({}, FGTS, RETRATO_ANTIGO)),
        _entregas(_rotulos({}, ZONA, GRAVE, ENTREGUE_DEPOIS_DE_HOJE)),
    ]


# --- o registro das seções e das colunas ----------------------------------------------------------


@pytest.mark.parametrize(
    ("chave", "titulo", "tabela"),
    [
        ("divida_com_a_uniao", "Dívida ativa com a União (PGFN)", "pgfn_divida"),
        (
            "entrega_das_demonstracoes",
            "Entrega das demonstrações no prazo",
            "rotulos_atraso",
        ),
    ],
)
def test_a_secao_esta_registrada_com_a_tabela_e_os_limites(
    chave: str, titulo: str, tabela: str
) -> None:
    registrada = next(s for s in dossie.SECOES if s.chave == chave)
    assert (registrada.titulo, registrada.tabelas) == (titulo, (tabela,))
    dossie.exigir_que_pode_mostrar(registrada.tabelas)
    assert dossie.fontes_das_tabelas(registrada.tabelas)
    limites = dossie.LIMITES[chave]
    assert "recomendação" in limites and "Pessoas" in limites
    assert "contestar" in limites  # o direito de resposta, pelo contato do TickerLab


def test_as_secoes_entram_depois_da_insolvencia_no_molde_a() -> None:
    ordem = list(ORDEM_DAS_SECOES)
    assert ordem.index("divida_com_a_uniao") == ordem.index("insolvencia") + 1
    assert (
        ordem.index("entrega_das_demonstracoes")
        == ordem.index("divida_com_a_uniao") + 1
    )
    assert ordem.index("entrega_das_demonstracoes") < ordem.index("notas_classicas")


def test_toda_coluna_produzida_esta_declarada_com_rotulo_e_titulo() -> None:
    tabelas = {
        "inscricoes_na_divida_ativa": _inscricoes(_divida(_pgfn())),
        "entregas_de_dfp_e_itr": _linhas(_entregas(_rotulos())),
    }
    for tabela, linhas in tabelas.items():
        declaradas = dossie_do_app.colunas_da_tabela(tabela)
        assert declaradas is not None
        assert dossie_do_app.titulo_da_tabela(tabela)
        assert {c for c, _, _ in declaradas} == set(linhas[0])
        rotulos = {c: r for c, r, _ in declaradas}
        assert rotulos["link"] == dossie_do_app.ROTULO_DO_LINK
        assert rotulos["publico_em"] == "Público desde"


@pytest.mark.parametrize(
    "tabela",
    ["ratings", "assembleias_recentes", "negocios", "registros_de_insolvencia"],
)
def test_a_fonte_original_entrou_nas_tabelas_que_ja_carregam_o_link(
    tabela: str,
) -> None:
    colunas = dossie_do_app.colunas_da_tabela(tabela)
    assert colunas is not None
    assert [r for c, r, _ in colunas if c == "link"] == [dossie_do_app.ROTULO_DO_LINK]


# --- dívida ativa com a União ---------------------------------------------------------------------


def test_sem_a_tabela_na_base_nao_ha_secao() -> None:
    assert dossie.secao_divida_com_a_uniao(None, HOJE) is None
    assert dossie.secao_entrega_das_demonstracoes(None, HOJE) is None


def test_sem_inscricao_diz_o_dia_da_consulta_e_o_que_nao_sabe() -> None:
    secao = _divida(_pgfn().iloc[0:0])
    assert secao["tabelas"] == {}
    assert secao["paragrafos"] == [
        "Sem inscrição em dívida ativa da União nos retratos públicos da PGFN até 17/10/2026.",
        dossie.O_QUE_NAO_SABEMOS_DA_DIVIDA,
        dossie.LIMITES["divida_com_a_uniao"],
    ]
    assert _divida(pd.DataFrame())["tabelas"] == {}  # a empresa sem linha na tabela


def test_cada_inscricao_e_um_fato_datado_com_fonte_link_e_original() -> None:
    assert _inscricoes(_divida(_pgfn())) == [
        {
            "tipo_divida": "nao_previdenciaria",
            "tipo_situacao": "Em cobrança",
            "situacao_inscricao": "ATIVA EM COBRANCA",
            "ajuizado": True,
            "inscricoes": 3,
            "valor_consolidado": 1_200_000.0,
            "regiao": "SP",
            "tipo_devedor": "principal",
            "aconteceu_em": "2026-09-30",
            "publico_em": "2026-10-10",
            "veiculo": "PGFN (dados abertos da dívida ativa)",
            "link": "https://dadosabertos.pgfn.gov.br/",
            "origem": SHA,
        }
    ]


def test_os_retratos_saem_do_mais_novo_ao_mais_antigo_e_por_tipo() -> None:
    pgfn = _pgfn(RETRATO_ANTIGO, {"tipo_divida": "previdenciaria"}, FGTS)
    linhas = _inscricoes(_divida(pgfn))
    assert [(l["aconteceu_em"], l["tipo_divida"]) for l in linhas] == [
        ("2026-09-30", "fgts"),
        ("2026-09-30", "previdenciaria"),
        ("2026-06-30", "nao_previdenciaria"),
    ]


def test_o_retrato_que_ainda_nao_era_publico_fica_fora_e_o_do_dia_entra() -> None:
    no_dia = {**FGTS, "disponivel_em": HOJE}
    secao = _divida(_pgfn({}, RETRATO_FUTURO, no_dia))
    assert [(l["tipo_divida"], l["publico_em"]) for l in _inscricoes(secao)] == [
        ("fgts", "2026-10-17"),
        ("nao_previdenciaria", "2026-10-10"),
    ]
    texto = json.dumps(secao, ensure_ascii=False)
    assert "7777777" not in texto and "2027-01-10" not in texto


def test_o_resumo_conta_so_o_retrato_mais_novo_no_total_e_por_tipo() -> None:
    secao = _divida(_pgfn({}, FGTS, RETRATO_ANTIGO))
    assert secao["paragrafos"][0] == (
        "Retrato mais novo da PGFN, de 30/09/2026 (público desde 10/10/2026): 4 inscrições em "
        "dívida ativa da União, R$ 1,5 mi de valor consolidado na data do retrato; por tipo: FGTS: "
        "1 inscrição, R$ 300,0 mil; não previdenciária: 3 inscrições, R$ 1,2 mi."
    )  # as 9 inscrições do retrato antigo ficam na tabela, não no resumo


def test_o_resumo_diz_quando_a_fonte_nao_conta_nem_valora() -> None:
    sem_numeros = {"inscricoes": float("nan"), "valor_consolidado": float("nan")}
    secao = _divida(_pgfn(sem_numeros))
    assert (
        "inscrições sem contagem na fonte em dívida ativa da União, valor não informado"
        in secao["paragrafos"][0]
    )
    (linha,) = _inscricoes(secao)
    assert (linha["inscricoes"], linha["valor_consolidado"]) == (None, None)


def test_cortar_o_futuro_nao_muda_o_passado_na_divida() -> None:
    inteira = _pgfn({}, FGTS, RETRATO_FUTURO)
    so_o_passado = inteira[inteira["disponivel_em"] <= HOJE]
    assert len(so_o_passado) == len(inteira) - 1
    assert _divida(inteira) == _divida(so_o_passado)


# --- entrega das demonstrações --------------------------------------------------------------------


def test_sem_documento_devido_diz_o_dia_e_a_regra() -> None:
    secao = _entregas(_rotulos(PRAZO_NO_FUTURO))
    assert secao["tabelas"] == {}
    assert secao["paragrafos"] == [
        (
            "Sem DFP ou ITR com prazo de entrega até 17/10/2026 nos dados abertos da CVM "
            "lidos pela base."
        ),
        dossie.REGRA_DO_ATRASO,
        dossie.LIMITES["entrega_das_demonstracoes"],
    ]
    assert _entregas(pd.DataFrame())["tabelas"] == {}  # a empresa sem linha na tabela


def test_cada_entrega_leva_prazo_rotulo_regra_e_fonte() -> None:
    assert _linhas(_entregas(_rotulos())) == [
        {
            "documento": "DFP",
            "referencia": "2025-12-31",
            "prazo": "2026-03-31",
            "primeira_entrega": "2026-03-27",
            "publico_em": "2026-03-27",
            "dias_uteis_de_atraso": 0,
            "rotulo": "no prazo",
            "regra": "no prazo: a primeira entrega não passou do dia do prazo",
            "veiculo": "CVM (dados abertos: entregas de DFP e ITR)",
            "link": f"{ENDERECO_DAS_ENTREGAS}DFP/",
        }
    ]


@pytest.mark.parametrize(
    ("linha", "rotulo", "regra"),
    [
        (
            ZONA,
            "zona cinzenta",
            (
                "zona cinzenta: entregou 1 dia útil depois do prazo (até 2 dias úteis; um "
                "feriado local pode explicar)"
            ),
        ),
        (
            GRAVE,
            "atraso grave",
            (
                "atraso grave: entregou 41 dias úteis depois do prazo, mais de 30 dias "
                "corridos depois dele"
            ),
        ),
        (ATRASADA, "atrasou", "atrasou: entregou 4 dias úteis depois do prazo"),
    ],
)
def test_o_rotulo_vem_da_tabela_com_a_regra_que_o_deu(
    linha: dict, rotulo: str, regra: str
) -> None:
    (entrega,) = _linhas(_entregas(_rotulos(linha)))
    assert (entrega["rotulo"], entrega["regra"]) == (rotulo, regra)
    assert (
        entrega["dias_uteis_de_atraso"] == linha["dias_uteis_de_atraso"]
    )  # não recalcula
    assert entrega["link"] == f"{ENDERECO_DAS_ENTREGAS}{linha['documento']}/"


def test_a_regra_em_palavras_usa_os_numeros_do_codigo() -> None:
    for trecho in (
        f"{MESES_DO_DFP} meses",
        f"{DIAS_DO_ITR} dias",
        f"mais de {ATRASO_GRAVE} dias corridos",
        f"até {ZONA_CINZENTA} dias úteis",
    ):
        assert trecho in dossie.REGRA_DO_ATRASO


def test_a_entrega_depois_de_hoje_nao_aparece_so_o_fato_de_nao_ter_entregado() -> None:
    secao = _entregas(_rotulos(ENTREGUE_DEPOIS_DE_HOJE))
    assert _linhas(secao) == [
        {
            "documento": "ITR",
            "referencia": "2026-06-30",
            "prazo": "2026-08-14",
            "primeira_entrega": None,
            "publico_em": None,
            "dias_uteis_de_atraso": DIAS_UTEIS_ATE_HOJE,
            "rotulo": "não entregue até 17/10/2026",
            "regra": "não entregue até 17/10/2026: 44 dias úteis desde o prazo",
            "veiculo": "CVM (dados abertos: entregas de DFP e ITR)",
            "link": f"{ENDERECO_DAS_ENTREGAS}ITR/",
        }
    ]
    assert "2026-10-20" not in json.dumps(secao)


def test_o_documento_com_prazo_depois_de_hoje_fica_fora() -> None:
    com_o_futuro = _linhas(_entregas(_rotulos(PRAZO_NO_FUTURO, {})))
    assert com_o_futuro == _linhas(_entregas(_rotulos()))
    assert len(com_o_futuro) == 1


def test_o_documento_sem_entrega_so_aparece_enquanto_a_tabela_sabia_dele() -> None:
    rotulos = _rotulos(VENCIDA_SEM_ENTREGA)  # montada em 21/10
    no_dia_da_montagem = _linhas(_entregas(rotulos, D("2026-10-21")))
    assert [l["rotulo"] for l in no_dia_da_montagem] == ["não entregue até 21/10/2026"]
    assert _linhas(_entregas(rotulos, D("2026-10-22"))) == []  # a tabela já não sabe
    assert _linhas(_entregas(rotulos.assign(montado_em=None))) == []


def test_as_entregas_saem_do_prazo_mais_novo_ao_mais_antigo() -> None:
    linhas = _linhas(_entregas(_rotulos(GRAVE, {}, ZONA)))
    assert [(l["documento"], l["prazo"]) for l in linhas] == [
        ("ITR", "2026-05-15"),
        ("DFP", "2026-03-31"),
        ("DFP", "2025-03-31"),
    ]


def test_cortar_o_futuro_nao_muda_o_passado_na_entrega() -> None:
    """A tabela montada depois da entrega (com ela) e a montada em HOJE, antes dela (sem ela), dão a
    mesma ficha de HOJE."""
    depois = _rotulos({}, ENTREGUE_DEPOIS_DE_HOJE, PRAZO_NO_FUTURO)
    antes = _rotulos({}, VENCIDA_SEM_ENTREGA, PRAZO_NO_FUTURO).assign(
        montado_em=f"{HOJE:%Y-%m-%d}T00:00:00-03:00"
    )
    assert _entregas(depois) == _entregas(antes)
    assert len(_linhas(_entregas(depois))) == 2


# --- o que vale para as duas ----------------------------------------------------------------------


def test_toda_linha_exposta_tem_veiculo_dia_publico_e_link() -> None:
    linhas = [l for s in _as_duas_secoes() for t in s["tabelas"].values() for l in t]
    assert len(linhas) == 7
    for linha in linhas:
        assert linha["veiculo"] and linha["link"].startswith("https://")
        assert linha["publico_em"] or linha.get("rotulo", "").startswith(
            "não entregue até"
        )


def test_as_secoes_nao_julgam_nem_citam_pessoa() -> None:
    secoes = _as_duas_secoes()
    texto = json.dumps(secoes, ensure_ascii=False).lower()
    for palavra in (*VEDADAS, *JULGAMENTOS):
        assert palavra not in texto, palavra
    ficha = dossie.montar_ficha(CNPJ, "CPFL", secoes, "2026-10-17T07:00:00-03:00")
    dossie.conferir_sem_pessoas(ficha, {"fulano de tal"})


def test_o_markdown_escreve_o_link_da_fonte_como_endereco() -> None:
    colunas = dossie_do_app.colunas_da_tabela("entregas_de_dfp_e_itr")
    assert colunas is not None
    escritas = dossie_do_app.escrever_linhas(colunas, _linhas(_entregas(_rotulos())))
    texto = "\n".join(markdown._tabela("entregas_de_dfp_e_itr", escritas))
    assert (
        f"Fonte original: {ENDERECO_DAS_ENTREGAS}DFP/" in texto
    )  # endereço, sem escape
    assert "CIA\\_ABERTA" not in texto
    assert "Prazo de entrega: 31/03/2026" in texto


def test_o_site_nao_leva_a_coluna_da_fonte_original() -> None:
    linhas = [{"Data": "30/09/2026", dossie_do_app.ROTULO_DO_LINK: "https://x.gov.br/"}]
    assert amostra_do_relatorio._colunas_do_site(linhas) == ["Data"]


# --- a tela ---------------------------------------------------------------------------------------


def _tela_das_secoes(caminho: str) -> None:
    from pathlib import Path

    from src import dossie as dossie_da_tela
    from telas.research.relatorio_empresa import _mostrar_secao

    ficha = dossie_da_tela.ler_ficha(Path(caminho))
    assert ficha is not None
    for secao in dossie_da_tela.secoes_da_ficha(ficha):
        _mostrar_secao(secao)


def test_a_tela_mostra_as_duas_secoes_com_a_fonte_original_clicavel(
    tmp_path: Path,
) -> None:
    from streamlit.testing.v1 import AppTest

    secoes = [_divida(_pgfn()), _entregas(_rotulos({}, ENTREGUE_DEPOIS_DE_HOJE))]
    ficha = dossie.montar_ficha(CNPJ, "CPFL", secoes, "2026-10-17T07:00:00-03:00")
    caminho = tmp_path / f"{CNPJ}.json"
    caminho.write_text(json.dumps(ficha), encoding="utf-8")

    app = AppTest.from_function(_tela_das_secoes, args=(str(caminho),)).run()

    assert not app.exception
    assert [s.value for s in app.subheader] == [
        "Dívida ativa com a União (PGFN)",
        "Entrega das demonstrações no prazo",
    ]
    textos = " ".join(m.value for m in app.markdown)
    assert "Retrato mais novo da PGFN, de 30/09/2026" in textos
    assert "Regra do TickerLab sobre o índice público da CVM" in textos
    divida, entregas = app.dataframe[0].value, app.dataframe[1].value
    assert list(divida["Fonte original"]) == ["https://dadosabertos.pgfn.gov.br/"]
    assert list(divida["Original no acervo"]) == [SHA[:12]]
    assert list(divida["Público desde"]) == ["10/10/2026"]
    assert list(entregas["Rótulo"]) == ["não entregue até 17/10/2026", "no prazo"]
    assert list(entregas["Primeira entrega"]) == ["—", "27/03/2026"]
    assert list(entregas["Regra que deu o rótulo"]) == [
        "não entregue até 17/10/2026: 44 dias úteis desde o prazo",
        "no prazo: a primeira entrega não passou do dia do prazo",
    ]
    for (
        elemento
    ) in app.dataframe:  # a coluna da fonte original é um link, nos dois quadros
        colunas = json.loads(elemento.proto.columns)
        assert colunas["Fonte original"]["type_config"]["type"] == "link"
