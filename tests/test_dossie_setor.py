"""A seção `setor` da ficha da noite (molde D, plano de 19/10/2026, PR 1, tarefas 1.2 a 1.4).

O mercado de exemplo é a saúde suplementar: a Hapvida com duas operadoras, a Odontoprev com uma e duas
operadoras fechadas, que a base não liga a nenhuma companhia aberta.
"""

import pandas as pd
import pytest

from base import concentracao, dossie

D = pd.Timestamp
HAPVIDA, ODONTOPREV, SEM_TICKER = "05197443000138", "58119199000151", "77777777000177"
SAUDE = next(s for s in dossie.SETORES_DO_LANCAMENTO if s.chave == "saude_suplementar")
TELECOM = next(s for s in dossie.SETORES_DO_LANCAMENTO if s.chave == "telecom")
_PERIODOS = pd.DataFrame(
    {
        "ano": [2024, 2025, 2026],
        "meses": [12, 12, 8],
        "ultimo_mes": [D("2024-12-31"), D("2025-12-31"), D("2026-08-31")],
    }
)


def _empresas() -> pd.DataFrame:
    return pd.DataFrame(
        {"cnpj": [HAPVIDA, ODONTOPREV], "empresa": ["HAPVIDA S.A.", "ODONTOPREV S.A."]}
    )


def _empresa_serie() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fonte": ["ans-beneficiarios"] * 5,
            "chave": ["100", "101", "200", "300", "400"],
            "nome": ["Hapvida", "GNDI", "Odontoprev", "Antiga", "Sem ticker"],
            "cnpj_companhia": [HAPVIDA, HAPVIDA, ODONTOPREV, ODONTOPREV, SEM_TICKER],
            "via": ["propria", "controlada", "propria", "controlada", "propria"],
            "principal": [True, True, True, False, True],
            "desde": [D("2015-01-01")] * 5,
        }
    )


def _beneficiarios() -> pd.DataFrame:
    """(ano, chave, valor): 100 de mercado por ano; as fechadas 300 e 900 sem companhia aberta."""
    linhas = {
        2024: {"100": 20.0, "101": 10.0, "200": 10.0, "300": 40.0, "900": 20.0},
        2025: {"100": 25.0, "101": 15.0, "200": 10.0, "300": 30.0, "900": 20.0},
        2026: {"100": 30.0, "101": 15.0, "200": 10.0, "300": 25.0, "900": 20.0},
    }
    tabela = pd.DataFrame(
        [
            {"ano": ano, "chave": chave, "valor": valor}
            for ano, valores in linhas.items()
            for chave, valor in valores.items()
        ]
    )
    return tabela.merge(_PERIODOS, on="ano")


def _serie(nome: str) -> dossie.SerieDaAgencia:
    return next(s for s in dossie.SERIES_DAS_AGENCIAS if s.nome == nome)


def _membros() -> pd.DataFrame:
    return dossie.membros_do_setor(SAUDE, _empresas(), _empresa_serie())


def _secao() -> dict:
    secao = dossie.secao_setor(
        SAUDE, _membros(), {"ans_beneficiarios": _beneficiarios()}, _empresa_serie(), {}
    )
    assert secao is not None
    return secao


# --- quem está no setor ----------------------------------------------------------------------------


def test_setores_do_lancamento_usam_series_que_existem() -> None:
    fontes = {
        s.nome: s.fonte_b13
        for s in (*dossie.SERIES_DAS_AGENCIAS, *dossie.SERIES_DOS_BANCOS)
    }
    assert [s.chave for s in dossie.SETORES_DO_LANCAMENTO] == [
        "eletricas",
        "bancos",
        "seguros",
        "saude_suplementar",
        "telecom",
        "aviacao",
    ]
    for setor in dossie.SETORES_DO_LANCAMENTO:
        assert setor.series, setor.chave
        assert {fontes[nome] for nome in setor.series} == set(setor.fontes_b13)


def test_membro_sempre_tem_motivo() -> None:
    membros = _membros()
    assert membros.to_dict("records") == [
        {
            "cnpj": HAPVIDA,
            "empresa": "HAPVIDA S.A.",
            "motivo": "ligada à ANS por 2 entidades",
        },
        {
            "cnpj": ODONTOPREV,
            "empresa": "ODONTOPREV S.A.",
            # a "Antiga" não é a ligação principal
            "motivo": "ligada à ANS por 1 entidade",
        },
    ]


def test_companhia_sem_ticker_nao_e_membro() -> None:
    assert SEM_TICKER not in set(_membros()["cnpj"])


def test_setor_sem_membros_nao_aparece() -> None:
    sem_ninguem = dossie.membros_do_setor(TELECOM, _empresas(), _empresa_serie())
    assert sem_ninguem.empty
    assert (
        dossie.secao_setor(
            TELECOM,
            sem_ninguem,
            {"ans_beneficiarios": _beneficiarios()},
            _empresa_serie(),
            {},
        )
        is None
    )


# --- quem é um participante ------------------------------------------------------------------------


def test_entidades_da_mesma_companhia_viram_um_participante() -> None:
    participantes = dossie.participantes(
        _serie("ans_beneficiarios"), _beneficiarios(), _empresa_serie(), None
    )
    de_2025 = participantes[participantes["ano"] == 2025].set_index("participante")
    assert de_2025["valor"].to_dict() == {
        f"companhia:{HAPVIDA}": 40.0,
        f"companhia:{ODONTOPREV}": 10.0,
        "entidade:300": 30.0,  # a ligação não é a principal: fica sozinha
        "entidade:900": 20.0,
    }
    assert de_2025.loc[f"companhia:{HAPVIDA}", "por"] == "companhia"
    assert de_2025.loc["entidade:900", "por"] == "entidade"


def test_entidade_com_ligacao_encerrada_volta_a_ser_solta_nos_anos_seguintes() -> None:
    """A 101 (GNDI) foi da Hapvida até 2024: em 2025 a base não sabe de dono e ela conta sozinha."""
    ligacoes = _empresa_serie().assign(
        vigente=True,
        ultima_referencia=D("2026-01-01"),
        ate=pd.NaT,
        ate_publico_em=pd.NaT,
    )
    ligacoes.loc[ligacoes["chave"] == "101", ["vigente", "ultima_referencia"]] = [
        False,
        D("2024-01-01"),
    ]
    participantes = dossie.participantes(
        _serie("ans_beneficiarios"), _beneficiarios(), ligacoes, None
    )
    de_2024 = participantes[participantes["ano"] == 2024].set_index("participante")
    de_2025 = participantes[participantes["ano"] == 2025].set_index("participante")
    assert de_2024.loc[f"companhia:{HAPVIDA}", "valor"] == 30.0  # 100 + 101
    assert de_2025.loc[f"companhia:{HAPVIDA}", "valor"] == 25.0  # só a 100
    assert de_2025.loc["entidade:101", "valor"] == 15.0


def test_entidade_ligada_a_duas_companhias_fica_com_a_de_mais_entidades() -> None:
    # a holding e a controlada aberta: a 101 conta uma vez só, na que junta mais operadoras
    dupla = pd.concat(
        [
            _empresa_serie(),
            pd.DataFrame(
                {
                    "fonte": ["ans-beneficiarios"],
                    "chave": ["101"],
                    "nome": ["GNDI"],
                    "cnpj_companhia": [SEM_TICKER],
                    "via": ["propria"],
                    "principal": [True],
                    "desde": [D("2015-01-01")],
                }
            ),
        ]
    )
    participantes = dossie.participantes(
        _serie("ans_beneficiarios"), _beneficiarios(), dupla, None
    )
    de_2025 = participantes[participantes["ano"] == 2025]
    assert de_2025["valor"].sum() == pytest.approx(100.0)
    assert (
        de_2025.set_index("participante").loc[f"companhia:{HAPVIDA}", "valor"] == 40.0
    )


def test_grupo_da_anatel_vence_a_companhia() -> None:
    acessos = pd.DataFrame(
        {"ano": [2025] * 3, "chave": ["11", "22", "33"], "valor": [50.0, 30.0, 20.0]}
    ).merge(_PERIODOS, on="ano")
    ligacoes = pd.DataFrame(
        {
            "fonte": ["anatel-acessos"],
            "chave": ["11"],
            "nome": ["Tele"],
            "cnpj_companhia": [HAPVIDA],
            "via": ["propria"],
            "principal": [True],
            "desde": [D("2015-01-01")],
        }
    )
    grupos = pd.DataFrame(
        {
            "ano": [2025] * 3,
            "chave": ["11", "22", "33"],
            "grupo": ["Tele", "Outra", "Outra"],
        }
    )
    participantes = dossie.participantes(
        _serie("anatel_telefonia_movel"), acessos, ligacoes, grupos
    ).set_index("participante")
    assert participantes["valor"].to_dict() == {"grupo:Tele": 50.0, "grupo:Outra": 50.0}
    assert set(participantes["por"]) == {"grupo"}


# --- a seção --------------------------------------------------------------------------------------


def test_secao_setor_traz_a_concentracao_por_ano() -> None:
    secao = _secao()
    assert secao["chave"] == "setor"
    linhas = {r["ano"]: r for r in secao["tabelas"]["concentracao_ans_beneficiarios"]}
    # 2025: Hapvida 40, a 300 com 30, a 900 com 20, Odontoprev 10
    assert linhas[2025]["hhi"] == pytest.approx(40**2 + 30**2 + 20**2 + 10**2)
    assert linhas[2025]["cr4"] == pytest.approx(1.0)
    assert linhas[2025]["faixa"] == concentracao.ALTO
    assert linhas[2025]["por_entidade"] == pytest.approx(0.5)
    assert linhas[2026]["meses"] == 8


def test_itens_do_setor_vem_do_ultimo_ano_completo_da_serie() -> None:
    itens = {item["chave"]: item for item in _secao()["itens"]}
    assert itens["setor"]["valor"] == "Saúde suplementar"
    assert itens["membros"]["valor"] == 2
    # 2026 tem 8 meses: o topo da seção é do último ano inteiro, o de 2025 (o ano pela metade não
    # entra na conta, nem para um estoque como os beneficiários)
    assert itens["hhi_ans_beneficiarios"]["base"] == "2025-12"
    assert itens["hhi_ans_beneficiarios"]["valor"] == pytest.approx(
        40**2 + 30**2 + 20**2 + 10**2
    )
    assert itens["cr4_ans_beneficiarios"]["valor"] == pytest.approx(1.0)
    assert itens["mercado_ans_beneficiarios"]["valor"] == pytest.approx(100.0)


def test_ano_parcial_vira_lacuna_declarada_na_secao() -> None:
    paragrafos = _secao()["paragrafos"]
    avisos = [p for p in paragrafos if p.startswith(dossie.MARCA_DO_ANO_PARCIAL)]
    assert len(avisos) == 1
    assert "2026 tem 8 meses de dados (até ago/2026)" in avisos[0]
    assert "ano inteiro de 2025" in avisos[0]
    assert "Beneficiários de planos de saúde" in avisos[0]


def test_sem_ano_parcial_nao_ha_lacuna() -> None:
    beneficiarios = _beneficiarios()
    inteiros = beneficiarios[beneficiarios["ano"] != 2026]
    secao = dossie.secao_setor(
        SAUDE, _membros(), {"ans_beneficiarios": inteiros}, _empresa_serie(), {}
    )
    assert secao is not None
    assert not [p for p in secao["paragrafos"] if p.startswith(dossie.MARCA_DO_ANO_PARCIAL)]  # fmt: skip


def test_so_com_ano_parcial_o_topo_diz_que_nao_e_ano_inteiro() -> None:
    beneficiarios = _beneficiarios()
    so_2026 = beneficiarios[beneficiarios["ano"] == 2026]
    secao = dossie.secao_setor(
        SAUDE, _membros(), {"ans_beneficiarios": so_2026}, _empresa_serie(), {}
    )
    assert secao is not None
    itens = {item["chave"]: item for item in secao["itens"]}
    assert itens["hhi_ans_beneficiarios"]["base"] == "2026-08"
    aviso = next(p for p in secao["paragrafos"] if p.startswith(dossie.MARCA_DO_ANO_PARCIAL))  # fmt: skip
    assert "só tem 2026, com 8 meses" in aviso
    assert "não de um ano inteiro" in aviso


def test_participacao_do_setor_bate_com_a_da_ficha_da_empresa() -> None:
    do_setor = [
        linha
        for linha in _secao()["tabelas"]["participacao_dos_membros"]
        if linha["cnpj"] == HAPVIDA
    ]
    ligacoes = _empresa_serie()
    da_empresa = dossie.secao_setor_regulado(
        ligacoes[ligacoes["cnpj_companhia"] == HAPVIDA],
        {"ans_beneficiarios": _beneficiarios()},
    )
    assert da_empresa is not None
    esperado = {
        r["ano"]: r["participacao"] for r in da_empresa["tabelas"]["ans_beneficiarios"]
    }
    assert {r["ano"]: r["participacao"] for r in do_setor} == esperado
    assert {r["serie"] for r in do_setor} == {"ans_beneficiarios"}


def test_membros_vao_na_secao_com_o_motivo() -> None:
    membros = _secao()["tabelas"]["membros"]
    assert [m["cnpj"] for m in membros] == [HAPVIDA, ODONTOPREV]
    assert all(m["motivo"] for m in membros)


def test_aviso_quando_a_concentracao_e_por_entidade() -> None:
    texto = " ".join(_secao()["paragrafos"])
    assert "parecem menores" in texto


def test_sem_entidade_solta_nao_tem_aviso() -> None:
    so_abertas = _beneficiarios().query("chave in ['100', '101', '200']")
    secao = dossie.secao_setor(
        SAUDE, _membros(), {"ans_beneficiarios": so_abertas}, _empresa_serie(), {}
    )
    assert secao is not None
    assert "parecem menores" not in " ".join(secao["paragrafos"])


def test_setor_regional_avisa_o_mercado_nacional() -> None:
    assert SAUDE.mercado_regional and TELECOM.mercado_regional
    assert "mercado relevante" in " ".join(_secao()["paragrafos"])


def test_fontes_do_setor_sao_as_da_serie() -> None:
    assert _secao()["fontes"] == dossie.fontes_do_setor(["ans_beneficiarios"])


def test_secao_setor_so_com_tabelas_que_podem_ser_mostradas() -> None:
    assert frozenset({"setor"}) == dossie.SECOES_DO_MOLDE_D
    registro = next(s for s in dossie.SECOES if s.chave == "setor")
    assert all(dossie.pode_mostrar(t) for t in registro.tabelas)
    assert {"empresa_serie", "ans_beneficiarios"} <= set(registro.tabelas)


def test_setor_cortar_o_futuro_nao_muda_o_passado() -> None:
    cortada = dossie.secao_setor(
        SAUDE,
        _membros(),
        {"ans_beneficiarios": _beneficiarios().query("ano <= 2025")},
        _empresa_serie(),
        {},
    )
    assert cortada is not None
    inteira = _secao()
    for tabela in ("concentracao_ans_beneficiarios", "participacao_dos_membros"):
        ate_2025 = [r for r in inteira["tabelas"][tabela] if r["ano"] <= 2025]
        assert ate_2025 == cortada["tabelas"][tabela]
