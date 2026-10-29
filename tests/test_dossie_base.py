"""O dossiê da empresa a partir da base (plano de 17/10/2026, PR 1): a regra de mostrar, as seções e o
filtro de pessoas.

Tabelas de mentira, pequenas, já só com a empresa da ficha (o script separa por CNPJ antes).
"""

from dataclasses import replace

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import dossie
from src.banco import coletas

D = pd.Timestamp
CNPJ = "02429144000193"


# --- a regra de mostrar --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tabela",
    [
        "auditores",
        "controladas",
        "aneel_samp",
        "anatel_acessos",
        "eventos",
        # marca restrita, que desde a ADR 0102 é só informação
        "ma_negocios",  # assessorias de M&A, só fatos (a confirmar)
        "ma_datas",  # datas pelo Wayback (não comercial)
    ],
)
def test_tabela_sem_pessoa_e_fora_da_lista_proibida_pode_ser_mostrada(
    tabela: str,
) -> None:
    assert dossie.pode_mostrar(tabela)


@pytest.mark.parametrize(
    "tabela",
    [
        "pgfn_divida",  # a licença deixa, mas é crise com nome (P-44)
        "rotulos_atraso",
        "tabela_que_nao_existe",
    ],
)
def test_tabela_que_nao_pode_ser_mostrada(tabela: str) -> None:
    assert not dossie.pode_mostrar(tabela)


@pytest.mark.parametrize("tabela", ["cnpj_situacao_especial", "insolvencia"])
def test_a_d2_liberou_insolvencia_e_situacao_especial(tabela: str) -> None:
    """A ADR 0103 (D2, só fatos) tirou as duas da lista do P-44; a pgfn_divida segue fora."""
    assert dossie.pode_mostrar(tabela)


def test_a_pgfn_tem_pessoa_e_a_lgpd_segura_mesmo_com_a_licenca_liberada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Emenda 3, item 3b: dado pessoal é LGPD, não licença; a trava deixa, a tabela não sai."""
    assert coletas.pode_usar("mostrar", dossie.TABELAS["pgfn_divida"].familia_da_fonte)
    monkeypatch.setattr(dossie, "TABELAS_PROIBIDAS", frozenset())
    assert dossie.TABELAS["pgfn_divida"].pessoa
    assert not dossie.pode_mostrar("pgfn_divida")


def test_a_lista_dos_usos_sem_cobranca_nao_decide_mais(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0102: a lista só guarda a citação; tirar a fonte dela não esconde a tabela."""
    monkeypatch.setattr(coletas, "USOS_SEM_COBRANCA", ())
    assert dossie.pode_mostrar("ma_datas")
    assert dossie.pode_mostrar("ma_negocios")


def test_tabela_com_fonte_da_b3_pode_ser_mostrada_e_volta_a_barrar_se_a_lista_a_receber(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0008, Emenda 6 (22/10/2026): a B3 entrou; pôr "b3" em `FONTES_FORA_DOS_USOS` desfaz."""
    da_b3 = replace(dossie.TABELAS["ma_datas"], familia_da_fonte="b3")
    monkeypatch.setitem(dossie.TABELAS, "ma_datas", da_b3)
    assert dossie.pode_mostrar("ma_datas")
    monkeypatch.setattr(coletas, "FONTES_FORA_DOS_USOS", frozenset({"b3"}))
    assert not dossie.pode_mostrar("ma_datas")


def test_tabela_vendavel_com_pessoa_nao_pode_ser_mostrada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    com_pessoa = replace(dossie.TABELAS["auditores"], pessoa=True)
    monkeypatch.setitem(dossie.TABELAS, "auditores", com_pessoa)
    assert not dossie.pode_mostrar("auditores")


def test_registrar_tabela_proibida_da_erro() -> None:
    with pytest.raises(dossie.TabelaProibidaError, match="pgfn_divida"):
        dossie.exigir_que_pode_mostrar(["auditores", "pgfn_divida"])


def test_o_atraso_pode_ser_contado_mas_nao_mostrado() -> None:
    """O cartão do site soma quantos balanços atrasaram; a ficha de uma companhia não mostra o rótulo."""
    assert not dossie.pode_mostrar("rotulos_atraso")
    assert dossie.pode_contar("rotulos_atraso")


@pytest.mark.parametrize("tabela", ["pgfn_divida", "tabela_que_nao_existe"])
def test_o_que_nao_esta_na_lista_de_contagem_nao_conta(tabela: str) -> None:
    assert not dossie.pode_contar(tabela)


def test_o_que_pode_ser_mostrado_pode_ser_contado() -> None:
    assert dossie.pode_contar("insolvencia")


def test_contar_tabela_com_pessoa_da_erro(monkeypatch: pytest.MonkeyPatch) -> None:
    """A lista de contagem não passa por cima da LGPD nem da trava da licença."""
    com_pessoa = replace(dossie.TABELAS["rotulos_atraso"], pessoa=True)
    monkeypatch.setitem(dossie.TABELAS, "rotulos_atraso", com_pessoa)
    assert not dossie.pode_contar("rotulos_atraso")
    with pytest.raises(dossie.TabelaProibidaError, match="rotulos_atraso"):
        dossie.exigir_que_pode_contar(["insolvencia", "rotulos_atraso"])


def test_todas_as_secoes_registradas_podem_ser_mostradas() -> None:
    for secao in dossie.SECOES:
        dossie.exigir_que_pode_mostrar(secao.tabelas)
        assert dossie.fontes_das_tabelas(secao.tabelas)


def test_series_das_agencias_estao_na_secao_do_setor_regulado() -> None:
    setor = next(s for s in dossie.SECOES if s.chave == "setor_regulado")
    for serie in dossie.SERIES_DAS_AGENCIAS:
        assert serie.tabela in setor.tabelas


# --- auditor e controladas -----------------------------------------------------------------------


def _auditores() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "referencia": [D("2024-01-01"), D("2025-01-01"), D("2025-01-01")],
            "versao": [1, 2, 2],
            "auditor_id": ["rede:kpmg", "rede:kpmg", "rede:deloitte"],
            "auditor": ["KPMG", "KPMG", "Deloitte"],
            "auditor_cnpj": ["57755217000129", "57755217000129", "49928567000111"],
            "inicio": [D("2019-01-01"), D("2019-01-01"), D("2025-04-01")],
            "fim": [pd.NaT, D("2025-03-31"), pd.NaT],
        }
    )


def _controladas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "referencia": [D("2024-01-01"), D("2025-01-01"), D("2025-01-01")],
            "versao": [1, 1, 1],
            "razao_social": ["Antiga S.A.", "CPFL Paulista", "Coligada S.A."],
            "tipo": ["controlada", "controlada", "coligada"],
            "participacao": [100.0, 100.0, 30.0],
        }
    )


def _trocas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "efetiva_em": [D("2025-04-01")],
            "anterior": ["KPMG"],
            "novo": ["Deloitte"],
            "anos_com_o_anterior": [6.2],
        }
    )


def test_auditor_atual_e_o_mandato_em_curso_do_fca_mais_recente() -> None:
    secao = dossie.secao_auditor_e_controladas(
        _auditores(), _trocas(), _controladas(), pd.DataFrame(), set()
    )
    assert secao is not None
    itens = {i["chave"]: i for i in secao["itens"]}
    assert itens["auditor_atual"]["valor"] == "Deloitte"
    assert itens["auditor_desde"]["valor"] == "2025-04-01"
    assert secao["tabelas"]["trocas_de_auditor"][0]["novo"] == "Deloitte"


def test_controladas_vem_so_do_fre_mais_recente() -> None:
    secao = dossie.secao_auditor_e_controladas(
        pd.DataFrame(), pd.DataFrame(), _controladas(), pd.DataFrame(), set()
    )
    assert secao is not None
    nomes = [linha["razao_social"] for linha in secao["tabelas"]["controladas"]]
    assert nomes == ["CPFL Paulista", "Coligada S.A."]
    itens = {i["chave"]: i["valor"] for i in secao["itens"]}
    assert itens["controladas"] == 1
    assert itens["coligadas_e_outras"] == 1


def test_sem_tipo_controlada_e_quem_tem_mais_da_metade() -> None:
    controladas = _controladas().assign(
        tipo=["", " ", ""], participacao=[100.0, 100.0, 30.0]
    )
    secao = dossie.secao_auditor_e_controladas(
        pd.DataFrame(), pd.DataFrame(), controladas, pd.DataFrame(), set()
    )
    assert secao is not None
    itens = {i["chave"]: i["valor"] for i in secao["itens"]}
    assert itens == {"sociedades": 2, "controladas": 1, "coligadas_e_outras": 1}
    grupo = dossie.cnpjs_do_grupo(
        CNPJ,
        controladas.assign(cnpj=["44444444000144", "33050196000188", "55555555000155"]),
    )
    assert grupo == {CNPJ, "33050196000188"}


def test_auditor_pessoa_fisica_nao_mostra_o_nome() -> None:
    auditores = pd.DataFrame(
        {
            "referencia": [D("2025-01-01")],
            "versao": [1],
            "auditor_id": ["cvm:123"],
            "auditor": ["Fulano de Tal"],
            "auditor_cnpj": [""],
            "inicio": [D("2024-01-01")],
            "fim": [pd.NaT],
        }
    )
    secao = dossie.secao_auditor_e_controladas(
        auditores, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {"fulano de tal"}
    )
    assert secao is not None
    assert "Fulano" not in str(secao)
    assert secao["itens"][0]["valor"] == dossie.AUDITOR_PESSOA


def test_troca_com_auditor_pessoa_esconde_o_nome() -> None:
    trocas = _trocas().assign(anterior=["Fulano de Tal"])
    secao = dossie.secao_auditor_e_controladas(
        pd.DataFrame(), trocas, pd.DataFrame(), pd.DataFrame(), {"fulano de tal"}
    )
    assert secao is not None
    assert secao["tabelas"]["trocas_de_auditor"][0]["anterior"] == dossie.AUDITOR_PESSOA


def test_data_sem_hora_nas_tabelas_sai_como_texto_iso() -> None:
    trocas = _trocas().assign(efetiva_em=lambda e: e["efetiva_em"].dt.date)
    secao = dossie.secao_auditor_e_controladas(
        pd.DataFrame(), trocas, pd.DataFrame(), pd.DataFrame(), set()
    )
    assert secao is not None
    assert secao["tabelas"]["trocas_de_auditor"][0]["efetiva_em"] == "2025-04-01"


def test_empresa_sem_nada_nao_tem_a_secao() -> None:
    vazio = pd.DataFrame()
    assert dossie.secao_auditor_e_controladas(vazio, vazio, vazio, vazio, set()) is None


def test_controladoras_vem_da_rede_sem_pessoas_e_so_vigentes() -> None:
    entidades = pd.DataFrame(
        {
            "id_entidade": ["E1", "E2", "E3", "E4"],
            "nome": ["CPFL Energia", "State Grid", "Fulano", "Antigo Dono"],
            "trata_como_pessoa": [False, False, True, False],
        }
    )
    identificadores = pd.DataFrame(
        {
            "id_entidade": ["E1", "E2"],
            "sistema": ["cnpj", "cnpj"],
            "valor": [CNPJ, "33333333000133"],
            "ate": [pd.NaT, pd.NaT],
        }
    )
    ligacoes = pd.DataFrame(
        {
            "de": ["E1", "E1", "E1"],
            "para": ["E2", "E3", "E4"],
            "tipo": ["controlada_de"] * 3,
            "situacao": ["vigente", "vigente", "encerrada"],
            "fonte": ["cvm-fre"] * 3,
            "participacao": [83.7, 5.0, 50.0],
        }
    )
    tabela = dossie.controladoras(ligacoes, entidades, identificadores)
    assert tabela.to_dict("records") == [
        {
            "cnpj": CNPJ,
            "controladora": "State Grid",
            "participacao": 83.7,
            "cnpj_controladora": "33333333000133",
        }
    ]


def _controladas_das_controladoras() -> pd.DataFrame:
    """O que cada controladora lista no FRE dela: a State Grid em dia, a VBC parou em 2011, a
    Vendeu S.A. deixou de listar a empresa no FRE de 2026 e a Sócia S.A. a lista como coligada."""
    return pd.DataFrame(
        {
            "cnpj_companhia": ["33333333000133", "44444444000144"]
            + ["55555555000155"] * 2
            + ["66666666000166"],
            "referencia": [D("2026-01-01"), D("2011-01-01")]
            + [D("2025-01-01"), D("2026-01-01")]
            + [D("2026-01-01")],
            "versao": [1, 1, 1, 1, 1],
            "cnpj": ["02.429.144/0001-93", CNPJ, CNPJ, "99999999000199", CNPJ],
            "razao_social": ["CPFL Energia"] * 3 + ["Outra", "CPFL Energia"],
            "tipo": ["controlada"] * 4 + ["coligada"],
            "participacao": [83.7, 25.55, 40.0, 100.0, 5.0],
        }
    )


def test_controladora_so_aparece_se_o_fre_recente_dela_ainda_lista_a_empresa() -> None:
    controladoras = pd.DataFrame(
        {
            "cnpj": [CNPJ] * 5,
            "controladora": ["State Grid", "VBC Energia", "Vendeu S.A.", "Sem CNPJ"]
            + ["Sócia S.A."],
            "participacao": [83.7, 25.55, 40.0, 60.0, 5.0],
            "cnpj_controladora": [
                "33333333000133",
                "44444444000144",
                "55555555000155",
                None,
                "66666666000166",
            ],
        }
    )
    tabela = dossie.controladoras_em_dia(
        controladoras, _controladas_das_controladoras(), D("2026-10-17")
    )
    assert tabela.to_dict("records") == [
        {"cnpj": CNPJ, "controladora": "State Grid", "participacao": 83.7}
    ]


def test_controladoras_em_dia_sem_tabelas_fica_vazia() -> None:
    assert dossie.controladoras_em_dia(
        pd.DataFrame(), _controladas_das_controladoras(), D("2026-10-17")
    ).empty


# --- ofertas e fundos ----------------------------------------------------------------------------


def _ofertas_160() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "data_registro": [D("2024-05-10"), D("2025-02-01")],
            "data_requerimento": [D("2024-05-01"), D("2025-01-20")],
            "valor_mobiliario": ["Debêntures", "Notas Comerciais"],
            "tipo_oferta": ["Primária", "Primária"],
            "valor_total_registrado": ["1000000000", "500000000.5"],
            "status_requerimento": ["Oferta Encerrada", "Registro Concedido"],
        }
    )


def _ofertas_antigas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "data_registro_oferta": [D("2015-03-01")],
            "data_protocolo": [D("2015-02-01")],
            "tipo_ativo": ["Ações"],
            "tipo_oferta": ["Secundária"],
            "valor_total": [2_000_000_000.0],
        }
    )


def _painel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "competencia": [D("2025-08-31"), D("2025-09-30"), D("2025-09-30")],
            "tipo": ["comprado", "comprado", "vendido"],
            "fundos": [400, 412, 3],
            "valor": [9.0e9, 9.5e9, 1.0e7],
        }
    )


def test_ofertas_juntam_a_resolucao_160_e_as_antigas() -> None:
    secao = dossie.secao_ofertas_e_fundos(
        _ofertas_160(), _ofertas_antigas(), pd.DataFrame()
    )
    assert secao is not None
    ofertas = secao["tabelas"]["ofertas"]
    assert [o["data"] for o in ofertas] == ["2025-02-01", "2024-05-10", "2015-03-01"]
    assert ofertas[0]["valor_total"] == pytest.approx(500_000_000.5)
    assert ofertas[2]["regime"] == "anterior à Res. 160"
    por_ano = {linha["ano"]: linha for linha in secao["tabelas"]["ofertas_por_ano"]}
    assert por_ano[2024]["valor_total"] == pytest.approx(1e9)


def test_fundos_mostram_so_a_posicao_comprada_do_ultimo_mes() -> None:
    secao = dossie.secao_ofertas_e_fundos(pd.DataFrame(), pd.DataFrame(), _painel())
    assert secao is not None
    itens = {i["chave"]: i for i in secao["itens"]}
    assert itens["fundos_com_a_acao"]["valor"] == 412
    assert itens["fundos_com_a_acao"]["base"] == "2025-09-30"
    assert itens["valor_nos_fundos"]["valor"] == pytest.approx(9.5e9)
    assert len(secao["tabelas"]["fundos_por_mes"]) == 2


def test_grupo_e_a_companhia_e_as_controladas_do_ultimo_fre() -> None:
    controladas = _controladas().assign(
        cnpj=["44444444000144", "33.050.196/0001-88", "55555555000155"]
    )
    # a "Antiga" é de um FRE velho; a coligada não emite pelo grupo
    assert dossie.cnpjs_do_grupo(CNPJ, controladas) == {CNPJ, "33050196000188"}
    assert dossie.cnpjs_do_grupo(CNPJ, pd.DataFrame()) == {CNPJ}


def test_oferta_mostra_quem_emitiu() -> None:
    ofertas = _ofertas_160().assign(nome_emissor=["CPFL Paulista", "CPFL Energia"])
    secao = dossie.secao_ofertas_e_fundos(ofertas, pd.DataFrame(), pd.DataFrame())
    assert secao is not None
    assert secao["tabelas"]["ofertas"][0]["emissor"] == "CPFL Energia"


def _cobertura(valores: list[float]) -> pd.DataFrame:
    meses = pd.date_range("2025-01-31", periods=len(valores), freq="ME")
    return pd.DataFrame({"competencia": meses, "valor_comprado": valores})


def test_ultimo_mes_completo_do_cda_tira_o_rabo_que_ainda_esta_chegando() -> None:
    # 12 meses cheios; os 3 últimos com as carteiras ainda chegando (55%, 54%, 20% do normal)
    cobertura = _cobertura([100.0] * 12 + [55.0, 54.0, 20.0])
    assert dossie.ultimo_mes_completo(cobertura) == D("2025-12-31")


def test_queda_no_meio_da_serie_nao_corta_o_cda() -> None:
    # uma queda forte que já passou (crise de mercado) não é carteira faltando
    cobertura = _cobertura([100.0] * 7 + [50.0] + [100.0] * 6)
    assert dossie.ultimo_mes_completo(cobertura) == D("2026-02-28")


def test_cda_sem_cobertura_nao_corta() -> None:
    assert dossie.ultimo_mes_completo(pd.DataFrame()) is None


def test_fundos_param_no_ultimo_mes_completo() -> None:
    secao = dossie.secao_ofertas_e_fundos(
        pd.DataFrame(), pd.DataFrame(), _painel(), ultimo_mes_completo=D("2025-08-31")
    )
    assert secao is not None
    itens = {i["chave"]: i for i in secao["itens"]}
    assert itens["fundos_com_a_acao"]["valor"] == 400
    assert itens["fundos_com_a_acao"]["base"] == "2025-08-31"
    assert len(secao["tabelas"]["fundos_por_mes"]) == 1


def test_sem_ofertas_nem_fundos_nao_tem_a_secao() -> None:
    vazio = pd.DataFrame()
    assert dossie.secao_ofertas_e_fundos(vazio, vazio, vazio) is None


# --- setor regulado ------------------------------------------------------------------------------


def test_serie_anual_soma_o_ano_ou_pega_o_ultimo_mes() -> None:
    tabela = pd.DataFrame(
        {
            "competencia": [D("2024-11-30"), D("2024-12-31"), D("2025-03-31")],
            "chave": ["A", "A", "A"],
            "valor": [10.0, 12.0, 15.0],
        }
    )
    soma = dossie.serie_anual(tabela, dossie.SOMA_DO_ANO)
    assert soma.set_index("ano").valor.to_dict() == {2024: 22.0, 2025: 15.0}
    ultimo = dossie.serie_anual(tabela, dossie.ULTIMO_MES)
    assert ultimo.set_index("ano").valor.to_dict() == {2024: 12.0, 2025: 15.0}


def _ligacoes_b13() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fonte": ["aneel-samp", "aneel-samp", "aneel-samp"],
            "chave": ["11111111000111", "22222222000122", "33333333000133"],
            "nome": ["CPFL Paulista", "RGE", "Antiga"],
            "via": ["controlada", "controlada", "controlada"],
            "principal": [True, True, False],
            "desde": [D("2010-05-01"), D("2016-05-01"), D("2010-05-01")],
        }
    )


def _serie_aneel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ano": [2024, 2024, 2024, 2024, 2025, 2025],
            "chave": ["11111111000111", "22222222000122", "33333333000133", "99"] * 1
            + ["11111111000111", "99"],
            "valor": [5.0, 3.0, 1.0, 11.0, 6.0, 14.0],
        }
    ).merge(_PERIODOS, on="ano")


_PERIODOS = pd.DataFrame(
    {
        "ano": [2024, 2025, 2026],
        "meses": [12, 12, 8],
        "ultimo_mes": [D("2024-12-31"), D("2025-12-31"), D("2026-08-31")],
    }
)


def test_setor_regulado_soma_as_entidades_principais_e_a_participacao() -> None:
    series = {"aneel_consumidores": _serie_aneel()}
    secao = dossie.secao_setor_regulado(_ligacoes_b13(), series)
    assert secao is not None
    linhas = {r["ano"]: r for r in secao["tabelas"]["aneel_consumidores"]}
    assert linhas[2024]["valor"] == 8.0  # a "Antiga" não é a ligação principal
    assert linhas[2024]["participacao"] == pytest.approx(8 / 20)
    assert linhas[2025]["participacao"] == pytest.approx(6 / 20)
    assert secao["tabelas"]["entidades_ligadas"][0]["nome"] == "CPFL Paulista"


def _com_a_vigencia(
    ligacoes: pd.DataFrame, chave: str, ultima: str, ate: str | None
) -> pd.DataFrame:
    """A ligação da `chave` acabou: a última entrega do FRE que a mostrou é `ultima`."""
    ligacoes = ligacoes.assign(
        vigente=True,
        ultima_referencia=D("2026-01-01"),
        ate=pd.NaT,
        ate_publico_em=pd.NaT,
    )
    acabou = ligacoes["chave"] == chave
    ligacoes.loc[acabou, "vigente"] = False
    ligacoes.loc[acabou, "ultima_referencia"] = D(ultima)
    if ate:
        ligacoes.loc[acabou, "ate"] = D(ate)
        ligacoes.loc[acabou, "ate_publico_em"] = D(ate) + pd.Timedelta(days=150)
    return ligacoes


def test_setor_regulado_conta_a_entidade_so_ate_o_ano_em_que_a_ligacao_acabou() -> None:
    """A distribuidora vendida (Roraima, em 2018) não soma no ano em que já era de outro dono."""
    ligacoes = _com_a_vigencia(
        _ligacoes_b13(), "22222222000122", "2024-01-01", "2025-01-01"
    )
    com_a_rge_em_2025 = pd.concat(
        [
            _serie_aneel(),
            pd.DataFrame(
                {"ano": [2025], "chave": ["22222222000122"], "valor": [4.0]}
            ).merge(_PERIODOS, on="ano"),
        ]
    )  # a RGE tem número em 2025, mas já era de outro dono
    secao = dossie.secao_setor_regulado(
        ligacoes, {"aneel_consumidores": com_a_rge_em_2025}
    )
    assert secao is not None
    linhas = {r["ano"]: r for r in secao["tabelas"]["aneel_consumidores"]}
    assert linhas[2024]["valor"] == 8.0  # a RGE ainda era dela em 2024
    assert linhas[2025]["valor"] == 6.0  # em 2025 só a CPFL Paulista
    assert linhas[2025]["participacao"] == pytest.approx(6 / 24)


def test_setor_regulado_ligacao_de_companhia_que_parou_de_entregar_acaba_na_ultima_evidencia() -> (
    None
):
    """Eletropaulo na AES ELPA: o FRE parou em 2016 e não há entrega sem a ligação (`ate` vazio)."""
    ligacoes = _com_a_vigencia(_ligacoes_b13(), "11111111000111", "2024-01-01", None)
    secao = dossie.secao_setor_regulado(
        ligacoes, {"aneel_consumidores": _serie_aneel()}
    )
    assert secao is not None
    linhas = {r["ano"]: r for r in secao["tabelas"]["aneel_consumidores"]}
    assert linhas[2024]["valor"] == 8.0
    assert (
        2025 not in linhas
    )  # a CPFL Paulista deixou de ser da empresa; a RGE não tem número


def test_entidades_ligadas_mostram_ate_quando_a_ligacao_acabou() -> None:
    ligacoes = _com_a_vigencia(
        _ligacoes_b13(), "22222222000122", "2024-01-01", "2025-01-01"
    )
    secao = dossie.secao_setor_regulado(
        ligacoes, {"aneel_consumidores": _serie_aneel()}
    )
    assert secao is not None
    rge = next(r for r in secao["tabelas"]["entidades_ligadas"] if r["nome"] == "RGE")
    assert str(rge["ate"]).startswith("2025-01-01")
    assert str(rge["ate_publico_em"]).startswith("2025-05-31")
    cpfl = next(
        r for r in secao["tabelas"]["entidades_ligadas"] if r["nome"] == "CPFL Paulista"
    )
    assert bool(cpfl["vigente"])


def test_fontes_do_setor_sao_so_as_das_series_da_empresa() -> None:
    # regressão (18/10/2026): a seção listava as licenças de todas as agências (SUSEP, ANAC, ANP...)
    secao = dossie.secao_setor_regulado(
        _ligacoes_b13(), {"aneel_consumidores": _serie_aneel()}
    )
    assert secao is not None
    assert secao["fontes"] == dossie.fontes_das_tabelas(("empresa_serie", "aneel_samp"))
    assert not any("SUSEP" in fonte or "ANAC" in fonte for fonte in secao["fontes"])


def test_ano_sem_numero_da_empresa_fica_fora_da_serie() -> None:
    # 2026: a agência tem dado, a empresa ainda não; o item fica com 2025
    serie = pd.concat(
        [
            _serie_aneel(),
            pd.DataFrame({"ano": [2026], "chave": ["99"], "valor": [15.0]}).merge(
                _PERIODOS, on="ano"
            ),
        ]
    )
    secao = dossie.secao_setor_regulado(_ligacoes_b13(), {"aneel_consumidores": serie})
    assert secao is not None
    anos = [r["ano"] for r in secao["tabelas"]["aneel_consumidores"]]
    assert anos == [2025, 2024]
    assert secao["itens"][0]["base"] == "2025-12"  # estoque: o mês, não o ano
    assert secao["itens"][0]["valor"] == 6.0


def test_soma_do_ano_usa_o_ultimo_ano_completo_no_item() -> None:
    meses = pd.date_range("2024-01-31", "2025-03-31", freq="ME")
    mensal = pd.DataFrame({"competencia": meses, "chave": "AZUL", "valor": 10.0})
    anual = dossie.serie_anual(mensal, dossie.SOMA_DO_ANO)
    assert anual.set_index("ano")["meses"].to_dict() == {2024: 12, 2025: 3}
    ligacoes = _ligacoes_b13().assign(
        fonte="anac-estatistico", chave=["AZUL", "x", "y"]
    )
    secao = dossie.secao_setor_regulado(ligacoes, {"anac_passageiros": anual})
    assert secao is not None
    assert secao["itens"][0]["base"] == "2024"
    assert secao["itens"][0]["valor"] == 120.0
    assert (
        secao["tabelas"]["anac_passageiros"][0]["meses"] == 3
    )  # 2025 fica na tabela, marcado


def test_ultimo_mes_tem_o_mes_como_base() -> None:
    mensal = pd.DataFrame(
        {
            "competencia": [D("2025-12-31"), D("2026-08-31")],
            "chave": "11111111000111",
            "valor": [5.0, 6.0],
        }
    )
    anual = dossie.serie_anual(mensal, dossie.ULTIMO_MES)
    secao = dossie.secao_setor_regulado(_ligacoes_b13(), {"aneel_consumidores": anual})
    assert secao is not None
    assert secao["itens"][0]["base"] == "2026-08"


def test_empresa_sem_agencia_nao_tem_setor_regulado() -> None:
    assert dossie.secao_setor_regulado(pd.DataFrame(), {}) is None


def test_chave_em_digitos_casa_cnpj_formatado() -> None:
    ligacoes = _ligacoes_b13().assign(chave=["11.111.111/0001-11", "x", "y"])
    series = {"aneel_consumidores": _serie_aneel()}
    secao = dossie.secao_setor_regulado(ligacoes, series)
    assert secao is not None
    linhas = {r["ano"]: r for r in secao["tabelas"]["aneel_consumidores"]}
    assert linhas[2024]["valor"] == 5.0


# --- negócios ------------------------------------------------------------------------------------


def _eventos() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rotulo": [
                "Fato relevante",
                "Fato relevante",
                "Comunicado ao mercado",
                "Assembleia",
            ],
            "assunto": [
                "Aquisição da Enercan",
                "Resultado do 2T25",
                "Conclusão da incorporação de ações",
                "Aquisição aprovada em AGE",
            ],
            "publicado_em": [
                D("2025-03-01"),
                D("2025-08-01"),
                D("2024-06-01"),
                D("2025-04-01"),
            ],
            "link": ["l1", "l2", "l3", "l4"],
        }
    )


def test_negocios_sao_fatos_e_comunicados_com_palavras_de_negocio() -> None:
    secao = dossie.secao_negocios(_eventos())
    assert secao is not None
    assuntos = [linha["assunto"] for linha in secao["tabelas"]["negocios"]]
    assert assuntos == ["Aquisição da Enercan", "Conclusão da incorporação de ações"]


@pytest.mark.parametrize(
    "assunto",
    ["Programa de Recompra de Ações", "Aprovação do Plano de Opção de Compra de Ações"],
)
def test_recompra_e_opcao_de_compra_nao_sao_negocios(assunto: str) -> None:
    eventos = _eventos().iloc[[0]].assign(assunto=[assunto])
    assert dossie.secao_negocios(eventos) is None


def test_compra_de_participacao_e_negocio() -> None:
    eventos = _eventos().iloc[[0]].assign(assunto=["Compra de participação na Enercan"])
    assert dossie.secao_negocios(eventos) is not None


def test_negocios_aceitam_data_sem_hora_como_vem_da_base() -> None:
    eventos = _eventos().assign(publicado_em=lambda e: e["publicado_em"].dt.date)
    secao = dossie.secao_negocios(eventos)
    assert secao is not None
    assert secao["tabelas"]["negocios"][0]["publicado_em"] == "2025-03-01"
    assert secao["itens"][0]["base"] == "2025-03-01"


def test_sem_negocios_nao_tem_a_secao() -> None:
    assert dossie.secao_negocios(_eventos().iloc[[1]]) is None


# --- a ficha e o filtro de pessoas ---------------------------------------------------------------


def _ficha() -> dict:
    secao = dossie.secao_negocios(_eventos())
    return dossie.montar_ficha(CNPJ, "CPFL Energia", [secao, None], "2026-10-17")


def test_ficha_leva_o_esquema_e_as_fontes() -> None:
    ficha = _ficha()
    assert ficha["versao_do_esquema"] == dossie.VERSAO_DO_ESQUEMA
    assert ficha["cnpj"] == CNPJ
    assert [s["chave"] for s in ficha["secoes"]] == ["negocios"]
    assert "CVM" in ficha["secoes"][0]["fontes"][0]


def test_ficha_sem_pessoas_passa() -> None:
    dossie.conferir_sem_pessoas(_ficha(), {"fulano de tal"})


def test_ficha_com_cpf_da_erro() -> None:
    ficha = _ficha()
    ficha["secoes"][0]["tabelas"]["negocios"][0]["assunto"] = (
        "Venda ao Sr. 123.456.789-09"
    )
    with pytest.raises(dossie.PessoaNaFichaError, match="CPF"):
        dossie.conferir_sem_pessoas(ficha, set())


def test_ficha_com_nome_de_pessoa_da_erro() -> None:
    ficha = _ficha()
    ficha["secoes"][0]["tabelas"]["negocios"][0]["assunto"] = "FULANO DE  TÁL"
    with pytest.raises(dossie.PessoaNaFichaError, match="pessoa"):
        dossie.conferir_sem_pessoas(ficha, {"fulano de tal"})


def test_ficha_com_coluna_de_pessoa_da_erro() -> None:
    ficha = _ficha()
    ficha["secoes"][0]["tabelas"]["negocios"][0]["administrador"] = "x"
    with pytest.raises(dossie.PessoaNaFichaError, match="administrador"):
        dossie.conferir_sem_pessoas(ficha, set())


@settings(max_examples=60, deadline=None)
@given(st.text(alphabet="abcdefghij ÁÉÍÓÚáéíóú", min_size=3, max_size=30))
def test_nome_de_pessoa_e_pego_com_qualquer_caixa_e_acento(nome: str) -> None:
    normalizado = dossie.normalizar_nome(nome)
    if not normalizado:
        return
    ficha = _ficha()
    ficha["secoes"][0]["tabelas"]["negocios"][0]["assunto"] = nome.upper()
    with pytest.raises(dossie.PessoaNaFichaError):
        dossie.conferir_sem_pessoas(ficha, {normalizado})


def test_as_tabelas_do_cafe_podem_ser_mostradas():
    # PR 3 da ADR 0102: CONAB (CC BY-ND, marca "a confirmar") e FAOSTAT (CC BY) vão para tela e API
    assert dossie.pode_mostrar("conab_cafe")
    assert dossie.pode_mostrar("faostat_cafe")
    dossie.exigir_que_pode_mostrar(["conab_cafe", "faostat_cafe"])
