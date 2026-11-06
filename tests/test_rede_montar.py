"""Montagem de `entidades` e `identificadores` das tabelas que a base já tem (plano, tarefa 2.6).

Uma mini-base de mentira: a Petrobras (cadastro da CVM, tickers e emissor do FCA, LEI do GLEIF), a
Ipiranga (controlada da Ultrapar, com código da ANP pela empresa ↔ série), um FIDC com administrador e
auditor, um banco do IF.data, um conglomerado (não vira entidade) e um MEI auditor (pessoa).
"""

import pandas as pd

from base.rede import ids, montar, resolucao

D = pd.Timestamp
PETROBRAS, ULTRAPAR = "33.000.167/0001-01", "33.256.439/0001-39"
FUNDO, ADMIN, BANCO = "11.222.333/0001-81", "60.746.948/0001-12", "00416968"


def _entradas() -> montar.Entradas:
    return montar.Entradas(
        cadastro=pd.DataFrame(
            {
                "cnpj": [PETROBRAS, ULTRAPAR],
                "empresa": [
                    "PETROLEO BRASILEIRO S.A. PETROBRAS",
                    "ULTRAPAR PARTICIPACOES S.A.",
                ],
                "registro": [D("1977-07-20"), D("1999-01-01")],
                "cancelamento": [pd.NaT, pd.NaT],
            }
        ),
        tickers=pd.DataFrame(
            {
                "codigo": ["PETR4", "PETR3", "UGPA3"],
                "cnpj": [PETROBRAS, PETROBRAS, ULTRAPAR],
                "primeiro_visto": [D("2018-05-31"), D("2018-05-31"), D("2018-06-10")],
                "valido_ate": [pd.NaT, pd.NaT, pd.NaT],
                "inicio_negociacao": [
                    D("1977-08-01"),
                    D("1977-08-01"),
                    D("1999-10-01"),
                ],
                "origem": ["fca", "fca", "códigos conferidos"],
            }
        ),
        emissores=pd.DataFrame(
            {
                "emissor": ["PETR", "UGPA", "XPTO"],
                "cnpj": [PETROBRAS, ULTRAPAR, ULTRAPAR],
                "primeiro_recebido_em": [
                    D("2010-05-31"),
                    D("2010-06-01"),
                    D("2011-01-01"),
                ],
                "conflito": [
                    False,
                    False,
                    True,
                ],  # XPTO com dois CNPJs no FCA: não liga
                "origem": ["fca", "fca", "fca"],
            }
        ),
        controladas=pd.DataFrame(
            {
                "cnpj_companhia": ["33256439000139"],
                "companhia": ["ULTRAPAR PARTICIPAÇÕES"],
                "cnpj": ["33337122000127"],
                "razao_social": ["Ipiranga Produtos de Petróleo S.A."],
                "referencia": [D("2009-12-31")],
                "conhecido_em": [D("2010-06-10").date()],
                "tipo": ["controlada"],
                "participacao": [100.0],
            }
        ),
        empresa_serie=pd.DataFrame(
            {
                "fonte": ["anp-vendas", "comexstat", "antt-siade"],
                "chave": ["IPIRANGA", "27101921", "EFC"],
                "nome": ["IPIRANGA", "OLEO DIESEL", "Estrada de Ferro Carajás"],
                "raiz": ["33337122", None, "33592510"],
                "via": ["controlada", "produto", "propria"],
                "por": ["cnpj", "cnpj", "tabela"],
                "cnpj_companhia": [ULTRAPAR, ULTRAPAR, "33592510000154"],
                "desde": [D("2010-06-10")] * 3,
                "principal": [True, False, True],
                "participacao": [100.0, None, None],
                "montado_em": [D("2026-10-14 18:55", tz="UTC")] * 3,
            }
        ),
        fundos=pd.DataFrame(
            {
                "TP_FUNDO": ["FIDC"],
                "CNPJ_FUNDO": [FUNDO],
                "DENOM_SOCIAL": ["FIDC DE MENTIRA"],
                "DT_REG": ["2015-03-02"],
                "CD_CVM": ["12345"],
                "CNPJ_ADMIN": [ADMIN],
                "ADMIN": ["BANCO ADMINISTRADOR S.A."],
                "PF_PJ_GESTOR": ["PF"],
                "CPF_CNPJ_GESTOR": [None],
                "GESTOR": [None],
                "CNPJ_AUDITOR": ["44.555.666/0001-81"],
                "AUDITOR": ["MEI AUDITOR 52998224725"],
            }
        ),
        ifdata=pd.DataFrame(
            {
                "data_base": [D("2025-06-30"), D("2025-06-30")],
                "cod_inst": [BANCO, "C0080075"],
                "instituicao": ["BANCO INTER", "CONGLOMERADO X"],
            }
        ),
        gleif=pd.DataFrame(
            {
                "lei": ["5493000J2N45DDNE4Y28"],
                "cnpj": ["33000167000101"],
                "nome": ["PETROLEO BRASILEIRO SA"],
                "autoridade": ["RA000681"],
                "categoria": ["GENERAL"],
                "situacao_do_lei": ["ISSUED"],
                "publico_em": [D("2026-10-13")],
                "conflito": [False],
            }
        ),
    )


def _rede(entradas: montar.Entradas | None = None):
    obs = montar.observacoes(entradas or _entradas())
    naturezas = pd.DataFrame(
        {"cnpj_basico": ["33000167", "44555666"], "natureza_juridica": ["2038", "2062"]}
    )
    meis = pd.DataFrame({"cnpj_basico": ["44555666"], "mei": [True]})
    return montar.montar_rede(obs, naturezas, meis, {})


def _id(raiz: str) -> str:
    return ids.id_entidade("empresa", "cnpj_raiz", raiz)


def _de(identificadores: pd.DataFrame, raiz: str) -> pd.DataFrame:
    return identificadores[identificadores["id_entidade"] == _id(raiz)]


def test_cada_fonte_vira_entidade():
    entidades, _, _ = _rede()
    esperado = {
        _id("33000167"), _id("33256439"), _id("33337122"), _id("33592510"), _id(BANCO),
        _id("60746948"), _id("44555666"), ids.id_entidade("fundo", "cnpj", "11222333000181"),
    }  # fmt: skip
    assert set(entidades["id_entidade"]) == esperado
    assert not entidades["id_entidade"].duplicated().any()


def test_conglomerado_produto_e_gestor_pessoa_fisica_nao_viram_entidade():
    entidades, identificadores, _ = _rede()
    texto = pd.concat([entidades, identificadores]).astype(str).to_string()
    assert "C0080075" not in texto and "CONGLOMERADO" not in texto
    assert "27101921" not in texto and "OLEO DIESEL" not in texto


def test_identificadores_da_petrobras():
    _, identificadores, _ = _rede()
    petrobras = _de(identificadores, "33000167")
    por_sistema = {s: sorted(g["valor"]) for s, g in petrobras.groupby("sistema")}
    assert por_sistema == {
        "cnpj": ["33000167000101"],
        "cnpj_raiz": ["33000167"],
        "emissor": ["PETR"],
        "lei": ["5493000J2N45DDNE4Y28"],
        "ticker": ["PETR3", "PETR4"],
    }
    lei = petrobras[petrobras["sistema"] == "lei"].iloc[0]
    assert (lei["regra"], lei["publico_em"]) == (3, D("2026-10-13"))


def test_ticker_so_vale_depois_do_fca():
    """O ticker vale (e é público) da entrega do FCA, não do início da negociação que ele informa."""
    _, identificadores, _ = _rede()
    petr4 = identificadores[identificadores["valor"] == "PETR4"].iloc[0]
    assert petr4["desde"] == D("2018-05-31") and petr4["publico_em"] == D("2018-05-31")
    ugpa3 = identificadores[identificadores["valor"] == "UGPA3"].iloc[0]
    assert (ugpa3["regra"], ugpa3["conferido_por"]) == (7, resolucao.PELA_TABELA)


def test_emissor_em_conflito_no_fca_nao_liga():
    _, identificadores, _ = _rede()
    assert "XPTO" not in set(identificadores["valor"])


def test_codigo_do_regulador_e_tabela_conferida():
    _, identificadores, _ = _rede()
    anp = identificadores[identificadores["sistema"] == "codigo_anp-vendas"].iloc[0]
    assert (anp["id_entidade"], anp["valor"], anp["regra"]) == (
        _id("33337122"),
        "IPIRANGA",
        5,
    )
    efc = identificadores[identificadores["sistema"] == "codigo_antt-siade"].iloc[0]
    assert (efc["regra"], efc["conferido_por"]) == (7, resolucao.PELA_TABELA)


def test_fundo_banco_e_participantes():
    entidades, identificadores, _ = _rede()
    por_id = entidades.set_index("id_entidade")
    fundo = por_id.loc[ids.id_entidade("fundo", "cnpj", "11222333000181")]
    assert (fundo["tipo"], fundo["nome"], fundo["natureza_juridica"]) == (
        "fundo", "FIDC DE MENTIRA", "2224",
    )  # fmt: skip
    assert por_id.loc[_id(BANCO), "nome"] == "BANCO INTER"
    banco = _de(identificadores, BANCO)
    assert set(banco["sistema"]) == {"cnpj_raiz", "codigo_bcb_ifdata"}
    assert banco["publico_em"].min() == D("2025-10-28")  # data-base + 120 dias
    assert por_id.loc[_id("60746948"), "nome"] == "BANCO ADMINISTRADOR S.A."


def test_natureza_pela_receita_e_mei_sem_nome():
    entidades, _, _ = _rede()
    por_id = entidades.set_index("id_entidade")
    assert por_id.loc[_id("33000167"), "natureza_juridica"] == "2038"
    assert por_id.loc[_id("33256439"), ["natureza_juridica", "natureza_fonte"]].tolist() == [
        "2046", "fonte",
    ]  # fmt: skip
    mei = por_id.loc[_id("44555666")]
    assert mei["mei"] and mei["trata_como_pessoa"] and pd.isna(mei["nome"])
    assert "52998224725" not in entidades.astype(str).to_string()


def test_nome_da_fonte_de_maior_prioridade():
    entidades, _, _ = _rede()
    assert (
        entidades.set_index("id_entidade").loc[_id("33000167"), "nome"]
        == "PETROLEO BRASILEIRO S.A. PETROBRAS"
    )


def test_raizes_para_a_receita():
    assert montar.raizes(montar.observacoes(_entradas())) >= {
        "33000167",
        "11222333",
        "44555666",
    }


def test_ordem_das_entradas_nao_muda_o_resultado():
    entradas = _entradas()
    embaralhadas = montar.Entradas(
        **{nome: t.iloc[::-1] for nome, t in vars(entradas).items()}
    )
    for antes, depois in zip(_rede(entradas), _rede(embaralhadas), strict=True):
        pd.testing.assert_frame_equal(antes, depois)


def test_entrada_que_falta_fica_vazia():
    so_o_cadastro = montar.Entradas(cadastro=_entradas().cadastro)
    entidades, identificadores, _ = _rede(so_o_cadastro)
    assert len(entidades) == 2 and set(identificadores["sistema"]) == {
        "cnpj",
        "cnpj_raiz",
    }


def test_colunas_iguais_as_do_dicionario():
    from base.dicionario import TABELAS

    entidades, identificadores, _ = _rede()
    assert list(entidades.columns) == list(TABELAS["entidades"].colunas)
    assert list(identificadores.columns) == list(TABELAS["identificadores"].colunas)
    assert TABELAS["entidades"].modulo == TABELAS["identificadores"].modulo == "rede"


def test_codigo_cvm_do_fundo_leva_o_tipo():
    """A CVM reaproveita o código em tipos diferentes de fundo (FI 19 e FIF 19 são outros fundos)."""
    fundos = pd.DataFrame(
        {
            "TP_FUNDO": ["FI", "FIF"],
            "CNPJ_FUNDO": ["11.222.333/0001-81", "60.746.948/0001-12"],
            "DENOM_SOCIAL": ["FUNDO A", "FUNDO B"],
            "DT_REG": ["2005-01-01", "2003-01-01"],
            "CD_CVM": ["19", "19"],
        }
    )
    _, identificadores, conflitos = _rede(montar.Entradas(fundos=fundos))
    codigos = identificadores[identificadores["valor"] == "19"]
    assert sorted(codigos["sistema"]) == ["codigo_cvm_FI", "codigo_cvm_FIF"]
    assert conflitos.empty


def test_cnpj_de_fundo_e_sempre_o_fundo():
    """O fundo que aparece como controlada no FRE ou como empresa no GLEIF é o mesmo fundo."""
    entradas = _entradas()
    controladas = pd.concat(
        [
            entradas.controladas,
            entradas.controladas.assign(
                cnpj="11222333000181", razao_social="FIDC DE MENTIRA (no FRE)"
            ),
        ],
        ignore_index=True,
    )
    gleif = entradas.gleif.assign(cnpj="11222333000181", categoria="GENERAL")
    entidades, identificadores, conflitos = _rede(
        montar.Entradas(
            **{**vars(entradas), "controladas": controladas, "gleif": gleif}
        )
    )
    assert conflitos.empty
    fundo = ids.id_entidade("fundo", "cnpj", "11222333000181")
    assert _id("11222333") not in set(entidades["id_entidade"])
    lei = identificadores[identificadores["sistema"] == "lei"].iloc[0]
    assert lei["id_entidade"] == fundo
