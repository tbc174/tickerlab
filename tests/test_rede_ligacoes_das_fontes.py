"""As ligações que a base já tem viram linhas da rede (plano, tarefa 3.2).

Usa a mini-base de `tests/test_rede_montar.py` (Petrobras, Ultrapar e Ipiranga, um FIDC, um banco) com
o que cada fonte de ligação acrescenta: as carteiras do CDA (valores mobiliários), os auditores do FCA,
o conglomerado do IF.data e as controladas em vários FREs.
"""

import pandas as pd

from base.rede import ids, ligacoes, ligacoes_das_fontes, montar
from tests.test_rede_montar import FUNDO, PETROBRAS, ULTRAPAR, _entradas

D = pd.Timestamp
IPIRANGA, OXITENO = "33337122000127", "62545686000153"
PETR4, PETR3 = "BRPETRACNPR6", "BRPETRACNOR9"
KPMG = "00418"


def _id(raiz: str) -> str:
    return ids.id_entidade("empresa", "cnpj_raiz", raiz)


def _isin(isin: str) -> str:
    return ids.id_entidade("valor_mobiliario", "isin", isin)


ID_FUNDO = ids.id_entidade("fundo", "cnpj", "11222333000181")
ID_KPMG = ids.id_entidade("auditor", "codigo_cvm_auditor", KPMG)


def _controladas() -> pd.DataFrame:
    """Três FREs da Ultrapar: a Oxiteno some no de 2022 e o tipo some no de 2021 (fica o de antes)."""
    linhas = [
        ("2019-12-31", "2020-05-29", IPIRANGA, "controlada", 100.0),
        ("2019-12-31", "2020-05-29", OXITENO, "controlada", 100.0),
        ("2020-12-31", "2021-05-31", IPIRANGA, "", 100.0),
        ("2020-12-31", "2021-05-31", OXITENO, "", 100.0),
        ("2021-12-31", "2022-05-31", IPIRANGA, "", 100.0),
        (
            "2019-12-31",
            "2020-05-29",
            None,
            "controlada",
            100.0,
        ),  # estrangeira: sem CNPJ
    ]
    return pd.DataFrame(
        {
            "cnpj_companhia": "33256439000139",
            "companhia": "ULTRAPAR",
            "referencia": [D(r) for r, *_ in linhas],
            "conhecido_em": [D(c).date() for _, c, *_ in linhas],
            "cnpj": [c for _, _, c, _, _ in linhas],
            "razao_social": [
                "IPIRANGA",
                "OXITENO",
                "IPIRANGA",
                "OXITENO",
                "IPIRANGA",
                "X",
            ],
            "tipo": [t for *_, t, _ in linhas],
            "participacao": [p for *_, p in linhas],
            "origem_sha256": "aa" * 32,
        }
    )


def _auditores() -> pd.DataFrame:
    """KPMG audita a Petrobras; uma linha traz o código da KPMG com outra firma (conflito) e uma é de
    auditor pessoa física (sem CNPJ: nunca vira entidade)."""
    return pd.DataFrame(
        {
            "cnpj": [PETROBRAS, PETROBRAS, ULTRAPAR, ULTRAPAR],
            "referencia": [
                D("2021-01-01"),
                D("2022-01-01"),
                D("2022-01-01"),
                D("2022-01-01"),
            ],
            "conhecido_em": [
                D("2021-05-31"),
                D("2022-05-31"),
                D("2022-05-30"),
                D("2022-05-30"),
            ],
            "auditor_id": ["rede:kpmg", "rede:kpmg", "rede:deloitte", "cvm:99999"],
            "auditor": ["KPMG AUDITORES", "KPMG AUDITORES", "DELOITTE", None],
            "auditor_cnpj": [
                "57755217000129",
                "57755217000129",
                "49928567000111",
                None,
            ],
            "codigo_cvm_auditor": [KPMG, KPMG, KPMG, "99999"],
            "inicio": [
                D("2017-01-01"),
                D("2017-01-01"),
                D("2020-01-01"),
                D("2019-01-01"),
            ],
            "fim": [pd.NaT, D("2021-12-31"), pd.NaT, pd.NaT],
            "origem_sha256": ["a1" * 32, "a2" * 32, "a3" * 32, "a4" * 32],
        }
    )


def _posicoes() -> pd.DataFrame:
    """O FIDC de mentira com PETR4 de jan a mar/2021, sem abril, e de novo em maio; PETR3 só em jan."""
    meses = ["2021-01-31", "2021-02-28", "2021-03-31", "2021-05-31", "2021-01-31"]
    return pd.DataFrame(
        {
            "competencia": [D(m) for m in meses],
            "cnpj_fundo": FUNDO,
            "fundo": "FIDC DE MENTIRA (no CDA)",
            "tipo_do_fundo": "FIDC",
            "tipo": "comprado",
            "isin": [PETR4] * 4 + [PETR3],
            "emissor": "PETR",
            "disponivel_em": [D(m) + pd.Timedelta(days=90) for m in meses],
            "origem_sha256": "cd" * 32,
        }
    )


def _empresa_serie() -> pd.DataFrame:
    """A Ipiranga por duas fontes (ANP e ANEEL), um produto do Comex e uma própria (a mesma empresa)."""
    linhas = [
        ("anp-vendas", "IPIRANGA", "33337122", ULTRAPAR, "controlada", "cnpj", True),
        ("aneel-samp", IPIRANGA, "33337122", ULTRAPAR, "controlada", "tabela", False),
        ("comexstat", "27101921", None, ULTRAPAR, "produto", "cnpj", False),
        ("antt-siade", "EFC", "33592510", "33592510000154", "propria", "tabela", True),
    ]
    return pd.DataFrame(
        {
            "fonte": [f for f, *_ in linhas],
            "chave": [c for _, c, *_ in linhas],
            "nome": ["IPIRANGA", "IPIRANGA", "OLEO DIESEL", "Estrada de Ferro Carajás"],
            "raiz": [r for _, _, r, *_ in linhas],
            "cnpj_companhia": [c for _, _, _, c, *_ in linhas],
            "via": [v for *_, v, _, _ in linhas],
            "por": [p for *_, p, _ in linhas],
            "principal": [p for *_, p in linhas],
            "participacao": [100.0, 100.0, None, None],
            "desde": [D("2010-06-10")] * 4,
            "origem_sha256": ["b1" * 32, "b2" * 32, "b3" * 32, "b4" * 32],
            "montado_em": [D("2026-10-14 18:55", tz="UTC")] * 4,
        }
    )


def _entradas_com_tudo() -> montar.Entradas:
    entradas = _entradas()
    return montar.Entradas(
        **{
            **vars(entradas),
            "controladas": _controladas(),
            "auditores": _auditores(),
            "isins": ligacoes_das_fontes.isins_das_posicoes(_posicoes()),
            "empresa_serie": _empresa_serie(),
            "ifdata": pd.DataFrame(
                {
                    "data_base": [D("2025-03-31"), D("2025-06-30"), D("2025-06-30")],
                    "cod_inst": ["00416968", "00416968", "60746948"],
                    "instituicao": ["BANCO INTER", "BANCO INTER", "BANCO ADMIN"],
                    "cnpj_lider": ["60746948", "60746948", "60746948"],
                    "origem_sha256": "ee" * 32,
                }
            ),
        }
    )


def _identificadores(entradas: montar.Entradas) -> pd.DataFrame:
    obs = montar.observacoes(entradas)
    vazia = pd.DataFrame(columns=["cnpj_basico", "natureza_juridica"])
    _, identificadores, _ = montar.montar_rede(
        obs, vazia, pd.DataFrame(columns=["cnpj_basico", "mei"]), {}
    )
    return identificadores


def _ligacoes() -> pd.DataFrame:
    entradas = _entradas_com_tudo()
    identificadores = _identificadores(entradas)
    periodos = ligacoes_das_fontes.periodos_das_posicoes(_posicoes())
    return montar.montar_ligacoes(
        entradas, identificadores, periodos, ultimo_mes=periodos["fim"].max()
    )


def _do_tipo(tabela: pd.DataFrame, tipo: str) -> pd.DataFrame:
    return tabela[tabela["tipo"] == tipo].reset_index(drop=True)


def test_valores_mobiliarios_e_auditores_viram_entidades():
    entidades, _, _ = montar.montar_rede(
        montar.observacoes(_entradas_com_tudo()),
        pd.DataFrame(columns=["cnpj_basico", "natureza_juridica"]),
        pd.DataFrame(columns=["cnpj_basico", "mei"]),
        {},
    )
    por_id = entidades.set_index("id_entidade")
    assert por_id.loc[_isin(PETR4), "tipo"] == "valor_mobiliario"
    assert por_id.loc[_isin(PETR4), "natureza_juridica"] == "nao_se_aplica"
    assert not por_id.loc[_isin(PETR4), "trata_como_pessoa"]
    assert por_id.loc[ID_KPMG, ["tipo", "nome"]].tolist() == [
        "auditor",
        "KPMG AUDITORES",
    ]
    # o auditor pessoa física (só o código) nunca vira entidade
    assert ids.id_entidade("auditor", "codigo_cvm_auditor", "99999") not in por_id.index


def _rede_com_naturezas(
    auditores: pd.DataFrame, naturezas: dict[str, str]
) -> pd.DataFrame:
    entradas = montar.Entradas(**{**vars(_entradas_com_tudo()), "auditores": auditores})
    entidades, _, _ = montar.montar_rede(
        montar.observacoes(entradas),
        pd.DataFrame(
            {
                "cnpj_basico": list(naturezas),
                "natureza_juridica": list(naturezas.values()),
            }
        ),
        pd.DataFrame(columns=["cnpj_basico", "mei"]),
        {},
    )
    return entidades.set_index("id_entidade")


def test_firma_de_auditoria_tem_a_natureza_da_receita_pela_raiz_do_cnpj():
    """A CVM não diz a natureza do auditor: ela vem da Receita pela raiz do CNPJ da firma (D8 só
    quando a Receita não acha a raiz)."""
    assert "57755217" in montar.raizes(montar.observacoes(_entradas_com_tudo()))
    kpmg = _rede_com_naturezas(_auditores(), {"57755217": "2232"}).loc[ID_KPMG]
    assert kpmg[["natureza_juridica", "natureza_fonte"]].tolist() == ["2232", "receita"]
    assert not kpmg["trata_como_pessoa"] and kpmg["nome"] == "KPMG AUDITORES"


def test_firma_de_auditoria_sem_natureza_na_receita_segue_como_pessoa():
    kpmg = _rede_com_naturezas(_auditores(), {}).loc[ID_KPMG]
    assert kpmg["natureza_juridica"] == "nao_informada" and kpmg["trata_como_pessoa"]


def test_auditor_empresario_individual_e_pessoa_sem_nome():
    kpmg = _rede_com_naturezas(_auditores(), {"57755217": "2135"}).loc[ID_KPMG]
    assert kpmg["trata_como_pessoa"] and pd.isna(kpmg["nome"])


def test_auditor_com_natureza_fora_das_sociedades_segue_como_pessoa():
    """Firma de auditoria registrada na CVM é sociedade (grupo 2 da Receita). Outra natureza (ex.: o
    CNPJ do FCA cai num cartório, 303-4) diz que o documento não é da firma: fica a D8."""
    kpmg = _rede_com_naturezas(_auditores(), {"57755217": "3034"}).loc[ID_KPMG]
    assert kpmg[["natureza_juridica", "natureza_fonte"]].tolist() == [
        "nao_informada",
        "nao_informada",
    ]
    assert kpmg["trata_como_pessoa"]


def test_codigo_com_duas_raizes_fica_com_a_mais_frequente():
    """Parte das linhas do FCA traz o CNPJ errado: vale a raiz da maioria dos mandatos do código."""
    auditores = _auditores()
    # 1 linha com o CNPJ errado e 2 com o certo
    auditores.loc[0, "auditor_cnpj"] = "11222333000181"
    auditores = pd.concat([auditores, auditores.iloc[[1]]], ignore_index=True)
    naturezas = {"11222333": "2135", "57755217": "2232"}
    kpmg = _rede_com_naturezas(auditores, naturezas).loc[ID_KPMG]
    assert kpmg["natureza_juridica"] == "2232"


def test_controladas_viram_controlada_de():
    controladas = _do_tipo(_ligacoes(), "controlada_de")
    ipiranga = controladas[controladas["de"] == _id("33337122")].iloc[0]
    assert ipiranga["para"] == _id("33256439")
    assert ipiranga["aconteceu_em"] == D("2019-12-31")
    assert ipiranga["publico_em"] == D("2020-05-29")  # o `conhecido_em` do 1º FRE
    assert pd.isna(ipiranga["ate"]) and ipiranga["situacao"] == "vigente"
    assert ipiranga["participacao"] == 100.0 and ipiranga["fonte"] == "cvm-fre"
    # a Oxiteno sumiu no FRE de 2022: a fonte encerrou na referência dele
    oxiteno = controladas[controladas["de"] == _id("62545686")].iloc[0]
    assert (oxiteno["ate"], oxiteno["encerrada_por"]) == (D("2021-12-31"), "fonte")
    # o fim só ficou público com o FRE que já não a mostra (entregue em 31/05/2022)
    assert oxiteno["ate_publico_em"] == D("2022-05-31")
    assert (
        len(controladas) == 2
    )  # o tipo em branco nos FREs seguintes não abre outra ligação


def test_detem_comprime_meses_seguidos():
    detem = _do_tipo(_ligacoes(), "detem")
    petr4 = detem[detem["para"] == _isin(PETR4)].sort_values("aconteceu_em")
    assert petr4["de"].unique().tolist() == [ID_FUNDO]
    pd.testing.assert_frame_equal(
        petr4[["aconteceu_em", "ate"]].reset_index(drop=True),
        pd.DataFrame(
            {
                # jan a mar (em abril já não tinha); maio é o último mês da base: continua
                "aconteceu_em": [D("2021-01-31"), D("2021-05-31")],
                "ate": [D("2021-04-30"), pd.NaT],
            }
        ).astype("datetime64[ns]"),
    )
    assert petr4["publico_em"].iloc[0] == D("2021-01-31") + pd.Timedelta(days=90)
    assert set(petr4["papel"]) == {"comprado"}
    petr3 = detem[detem["para"] == _isin(PETR3)].iloc[0]
    assert petr3["ate"] == D("2021-02-28")
    # a carteira sem a posição só fica pública 90 dias depois do mês
    assert petr3["ate_publico_em"] == D("2021-02-28") + pd.Timedelta(days=90)
    assert petr4["ate_publico_em"].iloc[0] == D("2021-04-30") + pd.Timedelta(days=90)


def test_emite_pelo_emissor_do_isin():
    emite = _do_tipo(_ligacoes(), "emite")
    assert set(emite["para"]) == {_isin(PETR4), _isin(PETR3)}
    assert set(emite["de"]) == {_id("33000167")}
    linha = emite[emite["para"] == _isin(PETR4)].iloc[0]
    assert linha["aconteceu_em"] == D("2021-01-31")
    # público quando os dois eram públicos: o ISIN (CDA) e o emissor (FCA de 2010)
    assert linha["publico_em"] == D("2021-01-31") + pd.Timedelta(days=90)


def test_emissor_de_duas_empresas_no_periodo_nao_liga():
    posicoes = _posicoes().assign(emissor="UGPA", isin="BRUGPAACNOR8")
    entradas = montar.Entradas(
        **{
            **vars(_entradas_com_tudo()),
            "isins": ligacoes_das_fontes.isins_das_posicoes(posicoes),
        }
    )
    identificadores = _identificadores(entradas)
    dobrado = identificadores[identificadores["valor"] == "UGPA"].assign(
        id_entidade=_id("33000167")
    )
    emite = ligacoes_das_fontes.emite(
        entradas.isins, pd.concat([identificadores, dobrado], ignore_index=True)
    )
    assert emite.empty


def test_audita_pelo_codigo_da_cvm():
    audita = _do_tipo(_ligacoes(), "audita")
    assert (
        len(audita) == 1
    )  # a linha com o código da KPMG e o nome da Deloitte é conflito
    linha = audita.iloc[0]
    assert (linha["de"], linha["para"]) == (ID_KPMG, _id("33000167"))
    assert linha["aconteceu_em"] == D("2017-01-01")
    assert linha["publico_em"] == D("2021-05-31")  # o FCA que primeiro mostrou
    assert linha["ate"] == D("2021-12-31")  # o fim, do FCA mais novo
    assert linha["ate_publico_em"] == D("2022-05-31")  # o 1º FCA que mostrou o fim
    assert linha["origem_sha256"] == "a1" * 32


def test_opera_para_pela_empresa_serie():
    opera = _do_tipo(_ligacoes(), "opera_para")
    assert (
        len(opera) == 1
    )  # as duas fontes dizem a mesma ligação; produto e própria não ligam
    linha = opera.iloc[0]
    assert (linha["de"], linha["para"]) == (_id("33337122"), _id("33256439"))
    assert linha["papel"] == "controlada;principal"
    # a fonte de governo é conhecida desde que foi guardada
    assert linha["publico_em"] == D("2026-10-14")
    assert linha["aconteceu_em"] == D("2010-06-10")
    assert linha["conferido_por"] == "regra"  # uma das fontes ligou pela regra


def test_banco_do_conglomerado():
    conglomerado = _do_tipo(_ligacoes(), "do_conglomerado_de")
    assert len(conglomerado) == 1  # o líder não liga a ele mesmo
    linha = conglomerado.iloc[0]
    assert (linha["de"], linha["para"]) == (_id("00416968"), _id("60746948"))
    assert linha["aconteceu_em"] == D("2025-03-31")
    assert linha["publico_em"] == D("2025-03-31") + pd.Timedelta(days=120)
    assert pd.isna(linha["ate"])


PWC = "00287"
ID_PWC = ids.id_entidade("auditor", "codigo_cvm_auditor", PWC)


def _ligacoes_com(**trocas: pd.DataFrame) -> pd.DataFrame:
    entradas = montar.Entradas(**{**vars(_entradas_com_tudo()), **trocas})
    identificadores = _identificadores(entradas)
    periodos = ligacoes_das_fontes.periodos_das_posicoes(_posicoes())
    return montar.montar_ligacoes(
        entradas, identificadores, periodos, ultimo_mes=periodos["fim"].max()
    )


def _petrobras_troca_kpmg_por_pwc() -> pd.DataFrame:
    """FCA de 2021: KPMG desde 2017, sem fim. FCA de 2022: só a PwC, desde 01/01/2022; a KPMG some
    sem que nenhum FCA diga o fim dela (o caso da KPMG de 2006 "vigente" em 2020)."""
    return pd.DataFrame(
        {
            "cnpj": [PETROBRAS, PETROBRAS],
            "referencia": [D("2021-01-01"), D("2022-01-01")],
            "conhecido_em": [D("2021-05-31"), D("2022-05-31")],
            "auditor_id": ["rede:kpmg", "rede:pwc"],
            "auditor": ["KPMG AUDITORES", "PRICEWATERHOUSECOOPERS"],
            "auditor_cnpj": ["57755217000129", "61562112000120"],
            "codigo_cvm_auditor": [KPMG, PWC],
            "inicio": [D("2017-01-01"), D("2022-01-01")],
            "fim": [pd.NaT, pd.NaT],
            "origem_sha256": ["a1" * 32, "a2" * 32],
        }
    )


def test_mandato_sem_fim_que_some_do_fca_fecha():
    audita = _do_tipo(
        _ligacoes_com(auditores=_petrobras_troca_kpmg_por_pwc()), "audita"
    )
    por_firma = audita.set_index("de")
    kpmg, pwc = por_firma.loc[ID_KPMG], por_firma.loc[ID_PWC]
    # fecha no início do mandato que entrou, público com o FCA que já não a lista
    assert (kpmg["ate"], kpmg["ate_publico_em"]) == (D("2022-01-01"), D("2022-05-31"))
    assert (kpmg["situacao"], kpmg["encerrada_por"]) == ("encerrada", "fonte")
    assert pd.isna(pwc["ate"]) and pwc["situacao"] == "vigente"


def test_mandato_que_some_sem_outro_entrar_fecha_na_entrega():
    """O FCA seguinte lista só um mandato já encerrado: a KPMG sumiu sem ninguém no lugar. O fim é a
    entrega desse FCA (o mais tarde que pode ter sido), público no mesmo dia."""
    auditores = _petrobras_troca_kpmg_por_pwc().assign(
        inicio=[D("2017-01-01"), D("2012-01-01")],
        fim=[pd.NaT, D("2016-12-31")],
    )
    audita = _do_tipo(_ligacoes_com(auditores=auditores), "audita").set_index("de")
    kpmg = audita.loc[ID_KPMG]
    assert (kpmg["ate"], kpmg["ate_publico_em"]) == (D("2022-05-31"), D("2022-05-31"))


def test_mandato_listado_no_fca_mais_novo_continua():
    auditores = _petrobras_troca_kpmg_por_pwc()
    de_novo = auditores.head(1).assign(
        referencia=D("2022-01-01"), conhecido_em=D("2022-05-31")
    )
    auditores = pd.concat([auditores, de_novo], ignore_index=True)
    audita = _do_tipo(_ligacoes_com(auditores=auditores), "audita").set_index("de")
    assert pd.isna(audita.loc[ID_KPMG, "ate"])  # auditoria conjunta: as duas seguem


def test_banco_que_sai_do_conglomerado_fecha_com_o_if_data_seguinte():
    """O Inter some do conglomerado na data-base de set/2025: o fim é essa data-base, pública 120
    dias depois (quando o IF.data dela sai)."""
    ifdata = pd.DataFrame(
        {
            "data_base": [D("2025-03-31"), D("2025-06-30"), D("2025-09-30")],
            "cod_inst": ["00416968", "00416968", "60746948"],
            "instituicao": ["BANCO INTER", "BANCO INTER", "BANCO ADMIN"],
            "cnpj_lider": ["60746948", "60746948", "60746948"],
            "origem_sha256": "ee" * 32,
        }
    )
    linha = _do_tipo(_ligacoes_com(ifdata=ifdata), "do_conglomerado_de").iloc[0]
    assert linha["ate"] == D("2025-09-30")
    assert linha["ate_publico_em"] == D("2025-09-30") + pd.Timedelta(days=120)


def test_toda_ligacao_tem_as_duas_pontas_e_chave_unica():
    tabela = _ligacoes()
    assert tabela["de"].notna().all() and tabela["para"].notna().all()
    assert list(tabela.columns) == list(ligacoes.COLUNAS)
    assert not tabela.duplicated(ligacoes.CHAVE).any()
    assert set(tabela["conferido_por"]) <= {"regra", "tabela"}


def test_ordem_das_entradas_nao_muda_as_ligacoes():
    entradas = _entradas_com_tudo()
    identificadores = _identificadores(entradas)
    periodos = ligacoes_das_fontes.periodos_das_posicoes(_posicoes())
    antes = montar.montar_ligacoes(entradas, identificadores, periodos, 0)
    embaralhadas = montar.Entradas(
        **{n: t.iloc[::-1] for n, t in vars(entradas).items()}
    )
    depois = montar.montar_ligacoes(
        embaralhadas, identificadores.iloc[::-1], periodos.iloc[::-1], 0
    )
    pd.testing.assert_frame_equal(antes, depois)


def test_duas_filiais_no_mesmo_fre_ficam_uma_ligacao():
    controladas = pd.concat(
        [
            _controladas(),
            _controladas().head(1).assign(cnpj="33337122000208", participacao=40.0),
        ],
        ignore_index=True,
    )
    r = ligacoes_das_fontes.Resolvedor(_identificadores(_entradas_com_tudo()))
    tabela = ligacoes.normalizar(ligacoes_das_fontes.das_controladas(controladas, r))
    ipiranga = tabela[tabela["de"] == _id("33337122")]
    assert ipiranga["participacao"].tolist() == [100.0]


def _ipiranga_listada_duas_vezes(primeira: tuple, segunda: tuple) -> pd.DataFrame:
    """O FRE de 2019 da Ultrapar lista a Ipiranga duas vezes: (tipo, participação) de cada linha."""
    base = _controladas().head(1)
    return pd.concat(
        [
            base.assign(tipo=primeira[0], participacao=primeira[1]),
            base.assign(tipo=segunda[0], participacao=segunda[1]),
        ],
        ignore_index=True,
    )


def _ligacao_da_ipiranga(controladas: pd.DataFrame) -> pd.DataFrame:
    r = ligacoes_das_fontes.Resolvedor(_identificadores(_entradas_com_tudo()))
    tabela = ligacoes.normalizar(ligacoes_das_fontes.das_controladas(controladas, r))
    return tabela[tabela["de"] == _id("33337122")]


def test_controlada_vence_a_coligada_do_mesmo_fre_mesmo_com_menos_participacao():
    # achado da B-03: a linha de coligada (maior %) levava a vaga e a controlada perdia a controladora
    for ordem in (
        [("coligada", 60.0), ("controlada", 30.0)],
        [("controlada", 30.0), ("coligada", 60.0)],
    ):
        ipiranga = _ligacao_da_ipiranga(_ipiranga_listada_duas_vezes(*ordem))
        assert ipiranga["tipo"].tolist() == [ligacoes_das_fontes.CONTROLADA_DE]
        assert ipiranga["participacao"].tolist() == [30.0]


def test_so_coligada_no_mesmo_fre_segue_a_maior_participacao():
    ipiranga = _ligacao_da_ipiranga(
        _ipiranga_listada_duas_vezes(("coligada", 20.0), ("coligada", 25.0))
    )
    assert ipiranga["tipo"].tolist() == [ligacoes_das_fontes.COLIGADA_DE]
    assert ipiranga["participacao"].tolist() == [25.0]


def test_controlada_do_mesmo_fre_mantem_a_data_do_fre():
    # sem olhar o futuro: a ligação nasce na entrega do FRE, não numa linha de outro
    ipiranga = _ligacao_da_ipiranga(
        _ipiranga_listada_duas_vezes(("coligada", 60.0), ("controlada", 30.0))
    )
    assert ipiranga["publico_em"].dt.date.tolist() == [D("2020-05-29").date()]


def test_fundo_que_so_esta_nas_carteiras_vira_entidade_e_detem():
    """Metade das linhas do CDA é de fundo fora do cadastro (classes da CVM 175): o CDA traz o CNPJ,
    o tipo e o nome, e o fundo vira entidade; o nome do cadastro, quando há, continua valendo."""
    posicoes = pd.concat(
        [
            _posicoes(),
            _posicoes()
            .head(1)
            .assign(cnpj_fundo="11.444.777/0001-61", fundo="CLASSE X"),
        ],
        ignore_index=True,
    )
    entradas = montar.Entradas(
        **{
            **vars(_entradas_com_tudo()),
            "isins": ligacoes_das_fontes.isins_das_posicoes(posicoes),
            "fundos_das_carteiras": ligacoes_das_fontes.juntar_fundos(
                [ligacoes_das_fontes.fundos_das_posicoes(posicoes)]
            ),
        }
    )
    obs = montar.observacoes(entradas)
    vazia = pd.DataFrame(columns=["cnpj_basico", "natureza_juridica"])
    entidades, identificadores, _ = montar.montar_rede(
        obs, vazia, pd.DataFrame(columns=["cnpj_basico", "mei"]), {}
    )
    por_id = entidades.set_index("id_entidade")
    classe = ids.id_entidade("fundo", "cnpj", "11444777000161")
    assert por_id.loc[classe, ["tipo", "nome", "natureza_juridica"]].tolist() == [
        "fundo", "CLASSE X", "2224",
    ]  # fmt: skip
    assert por_id.loc[ID_FUNDO, "nome"] == "FIDC DE MENTIRA"  # o do cadastro ganha
    periodos = ligacoes_das_fontes.periodos_das_posicoes(posicoes)
    tabela = montar.montar_ligacoes(
        entradas, identificadores, periodos, periodos["fim"].max()
    )
    detem = tabela[tabela["tipo"] == "detem"]
    assert classe in set(detem["de"])
