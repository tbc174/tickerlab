"""Ligação das partes dos negócios de M&A com a rede e duplicatas (base/ma_ligacao.py; ADR 0082, série 5
do plano de M&A, passo 3).

Tudo aqui é inventado: empresas, raízes de CNPJ e páginas de duas assessorias que não existem.
"""

import io
import json
import zipfile

import pandas as pd
import pytest

from base import ma_assessorias as ma
from base import ma_ligacao as lig
from base.dicionario import TABELAS
from base.parquet import conferir_tabela, gravar_tabela, ler_tabela
from base.rede import ids
from scripts import carga_ma_assessorias as carga
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para
from tests.test_base_ma_assessorias import QUANDO, VERSAO, pagina

RAIZ_ALFA, RAIZ_BETA, RAIZ_GAMA, RAIZ_DELTA = (
    "11111111",
    "22222222",
    "33333333",
    "44444444",
)
ID_ALFA = ids.id_entidade("empresa", "cnpj_raiz", RAIZ_ALFA)


# --- nomes ------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "nome, esperado",
    [
        ("Alfa Óleos S.A.", "alfa oleos"),
        ("ALFA OLEOS S/A", "alfa oleos"),
        ("Grupo Beta Ltda.", "beta"),
        ("Beta Group", "beta"),
        ("Gama Comércio Ltda - ME", "gama comercio"),
        ("Delta Inc.", "delta"),
        ("Visa", "visa"),  # "sa" só sai como palavra no fim, nunca dentro do nome
        ("Ltda.", None),
        ("", None),
        (None, None),
    ],
)
def test_nome_normalizado(nome, esperado):
    assert lig.normalizar(nome) == esperado
    assert lig.normalizar_nomes(pd.Series([nome], dtype=object)).iloc[0] == esperado


# --- partes de cada página ------------------------------------------------------------------------
def _negocio(**campos) -> dict:
    linha = dict.fromkeys(ma.COLUNAS)
    linha.update({"assessoria": "igc", "url": "u1", "tipo": "AQ_CONTROLE"}, **campos)
    return linha


def test_uma_parte_por_empresa_com_papel_e_lado():
    negocios = ma.tabela(
        [
            _negocio(
                alvo="Alfa",
                comprador="Beta",
                outras_partes="Gama",
                cliente="Alfa",
                contraparte="Beta; Gama",
            )
        ]
    )
    partes = lig.partes(negocios).set_index("nome")
    assert list(partes.index) == ["Alfa", "Beta", "Gama"]
    assert partes.loc["Alfa", "papel"] == "alvo"
    assert partes.loc["Alfa", "na_pagina"] == "cliente"
    assert partes.loc["Beta", "papel"] == "comprador"
    assert partes.loc["Gama", "papel"] == "outras_partes"
    assert partes.loc["Gama", "na_pagina"] == "contraparte"


def test_divida_so_tem_quem_captou():
    negocios = ma.tabela([_negocio(tipo="DCM", cliente="Alfa")])
    partes = lig.partes(negocios)
    assert partes[["nome", "papel", "na_pagina"]].to_dict("records") == [
        {"nome": "Alfa", "papel": None, "na_pagina": "cliente"}
    ]


# --- ligação --------------------------------------------------------------------------------------
def _rede(*entidades: tuple[str, str, str | None, str | None]) -> pd.DataFrame:
    """(id, nome, raiz, lei) → o que `nomes_da_rede` devolve."""
    return lig.nomes_da_rede(
        pd.DataFrame(
            {
                "id_entidade": [e[0] for e in entidades],
                "tipo": "empresa",
                "nome": [e[1] for e in entidades],
                "trata_como_pessoa": False,
            }
        ),
        pd.DataFrame(
            [
                {"id_entidade": e[0], "sistema": s, "valor": v, "ate": None}
                for e in entidades
                for s, v in (("cnpj_raiz", e[2]), ("lei", e[3]))
                if v
            ],
            columns=["id_entidade", "sistema", "valor", "ate"],
        ),
    )


PADRAO_DA_RECEITA = (
    None,
    True,
    False,
    False,
    False,
)  # abertura, tem o nome, estrangeira, pequena, sem fins lucrativos


def _receita(*linhas: tuple) -> pd.DataFrame:
    """(raiz, nome normalizado, por, pessoa[, abertura, tem o nome, estrangeira, pequena, sem fins
    lucrativos])."""
    completas = [tuple(linha) + PADRAO_DA_RECEITA[len(linha) - 4 :] for linha in linhas]
    return pd.DataFrame(completas, columns=list(lig.COLUNAS_DA_RECEITA))


def _ligar(nome: str, rede=None, receita=None, publico_em=None) -> dict:
    partes = lig.partes(ma.tabela([_negocio(cliente=nome, alvo=nome)]))
    ligadas = lig.ligar(
        partes,
        rede if rede is not None else _rede(),
        receita if receita is not None else _receita(),
        publico_em=publico_em,
    )
    assert len(ligadas) == 1
    return ligadas.iloc[0].to_dict()


def test_nome_exato_de_uma_entidade_da_rede():
    rede = _rede((ID_ALFA, "ALFA ÓLEOS S.A.", RAIZ_ALFA, "LEI00000000000000001"))
    parte = _ligar("Alfa Óleos", rede)
    assert parte["ligacao_por"] == "nome_exato"
    assert parte["id_entidade"] == ID_ALFA
    assert parte["cnpj_raiz"] == RAIZ_ALFA
    assert parte["lei"] == "LEI00000000000000001"
    assert parte["candidatos"] == 1


def test_nome_de_duas_entidades_fica_na_duvida():
    rede = _rede(
        (ID_ALFA, "Alfa S.A.", RAIZ_ALFA, None),
        ("E2", "ALFA LTDA", RAIZ_BETA, None),
    )
    parte = _ligar("Alfa", rede)
    assert parte["ligacao_por"] == "na_duvida"
    assert parte["candidatos"] == 2
    assert parte["id_entidade"] is None and parte["cnpj_raiz"] is None


def test_rede_e_razao_social_de_outra_raiz_ficam_na_duvida():
    rede = _rede((ID_ALFA, "Alfa S.A.", RAIZ_ALFA, None))
    receita = _receita((RAIZ_BETA, "alfa", lig.RAZAO_SOCIAL, False))
    assert _ligar("Alfa", rede, receita)["ligacao_por"] == "na_duvida"


def test_a_mesma_empresa_pela_rede_e_pela_receita_e_uma_so():
    rede = _rede((ID_ALFA, "Alfa S.A.", RAIZ_ALFA, None))
    receita = _receita((RAIZ_ALFA, "alfa", lig.RAZAO_SOCIAL, False))
    parte = _ligar("Alfa", rede, receita)
    assert parte["ligacao_por"] == "nome_exato"
    assert parte["id_entidade"] == ID_ALFA


def test_razao_social_de_fechada_fora_da_rede_ganha_o_id_que_a_rede_daria():
    receita = _receita((RAIZ_GAMA, "gama comercio", lig.RAZAO_SOCIAL, False))
    parte = _ligar("Gama Comércio", receita=receita)
    assert parte["ligacao_por"] == "nome_exato"
    assert parte["cnpj_raiz"] == RAIZ_GAMA
    assert parte["id_entidade"] == ids.id_entidade("empresa", "cnpj_raiz", RAIZ_GAMA)


def test_nome_fantasia_so_quando_o_nome_nao_casou():
    receita = _receita((RAIZ_DELTA, "delta adubos", lig.NOME_FANTASIA, False))
    parte = _ligar("Delta Adubos", receita=receita)
    assert parte["ligacao_por"] == "nome_fantasia"
    assert parte["cnpj_raiz"] == RAIZ_DELTA
    # com a razão social de outra raiz, o nome fantasia nem é olhado
    receita = _receita(
        (RAIZ_DELTA, "delta adubos", lig.NOME_FANTASIA, False),
        (RAIZ_GAMA, "delta adubos", lig.RAZAO_SOCIAL, False),
    )
    assert _ligar("Delta Adubos", receita=receita)["cnpj_raiz"] == RAIZ_GAMA


def test_nome_fantasia_de_duas_raizes_fica_na_duvida():
    receita = _receita(
        (RAIZ_DELTA, "delta", lig.NOME_FANTASIA, False),
        (RAIZ_GAMA, "delta", lig.NOME_FANTASIA, False),
    )
    parte = _ligar("Delta", receita=receita)
    assert parte["ligacao_por"] == "na_duvida"
    assert parte["candidatos"] == 2


def test_pessoa_com_cnpj_nunca_e_ligada():
    """Empresário individual e MEI são pessoas (ADR 0075): contam para a dúvida, nunca viram a ligação."""
    sozinha = _receita((RAIZ_GAMA, "gama", lig.RAZAO_SOCIAL, True))
    parte = _ligar("Gama", receita=sozinha)
    assert parte["ligacao_por"] == "sem_ligacao"
    assert parte["id_entidade"] is None and parte["cnpj_raiz"] is None
    com_empresa = _receita(
        (RAIZ_GAMA, "gama", lig.RAZAO_SOCIAL, True),
        (RAIZ_DELTA, "gama", lig.RAZAO_SOCIAL, False),
    )
    assert _ligar("Gama", receita=com_empresa)["ligacao_por"] == "na_duvida"


def test_sem_nada_fica_sem_ligacao():
    parte = _ligar("Ômega Internacional")
    assert parte["ligacao_por"] == "sem_ligacao"
    assert parte["candidatos"] == 0


# --- regras contra homônimos (conferência do Tiago, 16/10: `ma-regua-conferencia-2026-10-16.md`) ----
def test_nome_de_uma_palavra_so_de_microempresa_nao_liga_pela_receita():
    """Regra 1: "Kawa" casava com a KAWA LTDA, uma microempresa sem relação com o negócio."""
    receita = _receita(
        (RAIZ_GAMA, "kawa", lig.RAZAO_SOCIAL, False, None, True, False, True)
    )
    parte = _ligar("Kawa", receita=receita)
    assert parte["ligacao_por"] == "na_duvida"
    assert parte["candidatos"] == 1
    assert parte["id_entidade"] is None and parte["cnpj_raiz"] is None
    fantasia = _receita(
        (RAIZ_GAMA, "kawa", lig.NOME_FANTASIA, False, None, True, False, True)
    )
    assert _ligar("Kawa", receita=fantasia)["ligacao_por"] == "na_duvida"


def test_marca_de_uma_palavra_de_porte_maior_liga_pela_receita():
    """A 1ª versão da regra 1 derrubou SANKHYA S.A., SUNO S.A. e outras marcas certas."""
    receita = _receita((RAIZ_GAMA, "sankhya", lig.RAZAO_SOCIAL, False))
    parte = _ligar("Sankhya", receita=receita)
    assert parte["ligacao_por"] == "nome_exato"
    assert parte["cnpj_raiz"] == RAIZ_GAMA


def test_nome_de_uma_palavra_so_liga_pela_rede():
    rede = _rede((ID_ALFA, "KAWA S.A.", RAIZ_ALFA, None))
    parte = _ligar("Kawa", rede)
    assert parte["ligacao_por"] == "nome_exato"
    assert parte["cnpj_raiz"] == RAIZ_ALFA
    # a mesma empresa também pela Receita continua uma só
    receita = _receita((RAIZ_ALFA, "kawa", lig.RAZAO_SOCIAL, False))
    assert _ligar("Kawa", rede, receita)["cnpj_raiz"] == RAIZ_ALFA


def test_nome_fantasia_sem_o_nome_na_razao_social_fica_na_duvida():
    """Regra 4: "Estante Virtual" era o nome fantasia de um sebo com outra razão social."""
    sem = _receita(
        (RAIZ_DELTA, "estante virtual", lig.NOME_FANTASIA, False, None, False)
    )
    parte = _ligar("Estante Virtual", receita=sem)
    assert parte["ligacao_por"] == "na_duvida"
    assert parte["cnpj_raiz"] is None
    com = _receita(
        (RAIZ_DELTA, "estante virtual", lig.NOME_FANTASIA, False, None, True)
    )
    assert _ligar("Estante Virtual", receita=com)["ligacao_por"] == "nome_fantasia"


def test_regra_4_vale_so_para_a_alvo():
    """Na compradora, o nome fantasia liga mesmo sem o nome na razão social ("Hypermarcas" é hoje a
    HYPERA S.A.; "ClearSale", a CLEAR SALE S.A.): o homônimo que a regra pega é o da alvo."""
    receita = _receita(
        (RAIZ_DELTA, "hypermarcas", lig.NOME_FANTASIA, False, None, False)
    )
    partes = lig.partes(
        ma.tabela(
            [
                _negocio(url="u1", alvo="Alfa Óleos", comprador="Hypermarcas"),
                _negocio(url="u2", alvo="Hypermarcas", comprador="Beta"),
            ]
        )
    )
    ligadas = lig.ligar(partes, _rede(), receita).set_index(["url", "nome"])
    compradora = ligadas.loc[("u1", "Hypermarcas")]
    assert compradora["ligacao_por"] == "nome_fantasia"
    assert compradora["cnpj_raiz"] == RAIZ_DELTA
    alvo = ligadas.loc[("u2", "Hypermarcas")]
    assert alvo["ligacao_por"] == "na_duvida"
    assert alvo["cnpj_raiz"] is None and alvo["id_entidade"] is None
    assert alvo["candidatos"] == 1


def test_nome_fantasia_de_entidade_sem_fins_lucrativos_nunca_liga():
    """Regra 6: "Urgo" (a compradora francesa) casou com o nome fantasia de um sindicato. Sindicato,
    associação e fundação (grupo 3 da Receita) não ligam pelo nome fantasia em nenhum papel."""
    receita = _receita(
        (RAIZ_GAMA, "urgo", lig.NOME_FANTASIA, False, None, False, False, False, True)
    )
    partes = lig.partes(ma.tabela([_negocio(alvo="Alfa Óleos", comprador="Urgo")]))
    urgo = lig.ligar(partes, _rede(), receita).set_index("nome").loc["Urgo"]
    assert urgo["ligacao_por"] == "na_duvida"
    assert urgo["cnpj_raiz"] is None and urgo["candidatos"] == 1
    # pela razão social, liga: a fundação de previdência compra e vende participações
    exata = _receita(
        (RAIZ_GAMA, "urgo", lig.RAZAO_SOCIAL, False, None, True, False, False, True)
    )
    assert (
        lig.ligar(partes, _rede(), exata).set_index("nome").loc["Urgo", "cnpj_raiz"]
        == RAIZ_GAMA
    )


def test_cnpj_de_empresa_estrangeira_vira_holding_e_nao_a_alvo():
    """Regra 5: a FOXBIT LLC registrada no Brasil é a holding de fora, não a empresa brasileira."""
    receita = _receita(
        (RAIZ_GAMA, "foxbit brasil", lig.RAZAO_SOCIAL, False, None, True, True)
    )
    parte = _ligar("Foxbit Brasil", receita=receita)  # `_ligar` põe o nome como alvo
    assert parte["ligacao_por"] == "holding_estrangeira"
    assert parte["candidatos"] == 1
    assert parte["id_entidade"] is None and parte["cnpj_raiz"] is None


def test_compradora_estrangeira_liga_a_dona_de_fora():
    """Na compradora, a empresa de fora registrada no Brasil é a própria parte."""
    receita = _receita(
        (RAIZ_GAMA, "one equity partners", lig.RAZAO_SOCIAL, False, None, True, True)
    )
    partes = lig.partes(
        ma.tabela([_negocio(alvo="Alfa Óleos", comprador="One Equity Partners")])
    )
    ligadas = lig.ligar(partes, _rede(), receita).set_index("nome")
    assert ligadas.loc["One Equity Partners", "ligacao_por"] == "nome_exato"
    assert ligadas.loc["One Equity Partners", "cnpj_raiz"] == RAIZ_GAMA


def test_cnpj_aberto_depois_do_post_nunca_e_a_parte():
    """Regra 2: a CDF LTDA abriu em 02/2026, três meses depois da primeira cópia do post."""
    receita = _receita(
        (
            RAIZ_GAMA,
            "cdf tecnologia",
            lig.RAZAO_SOCIAL,
            False,
            pd.Timestamp("2026-02-04"),
        )
    )
    publico = pd.Series({"u1": pd.Timestamp("2025-11-18 13:08", tz="UTC")})
    parte = _ligar("CDF Tecnologia", receita=receita, publico_em=publico)
    assert parte["ligacao_por"] == "aberto_depois_do_negocio"
    assert parte["id_entidade"] is None and parte["cnpj_raiz"] is None
    antes = pd.Series({"u1": pd.Timestamp("2026-03-01", tz="UTC")})
    depois_do_cnpj = _ligar("CDF Tecnologia", receita=receita, publico_em=antes)
    assert depois_do_cnpj["cnpj_raiz"] == RAIZ_GAMA
    # sem a data do post, a regra não tem como valer: liga
    sem_data = _ligar("CDF Tecnologia", receita=receita)
    assert sem_data["cnpj_raiz"] == RAIZ_GAMA
    assert "abertura" not in sem_data


# --- duplicatas -------------------------------------------------------------------------------------
SITE_1 = "https://www.assessoria-um.com.br/transactions/"
SITE_2 = "https://www.assessoria-dois.com.br/transactions/"


def _do_site(assessoria: str, url: str, html: bytes) -> dict:
    return ma.extrair(html, url, "a" * 64, QUANDO, assessoria)


def _negocios(linhas: list[dict], rede=None) -> pd.DataFrame:
    tabela = ma.tabela(linhas)
    ligadas = lig.ligar(
        lig.partes(tabela), rede if rede is not None else _rede(), _receita()
    )
    return lig.negocios(tabela, ligadas).set_index("url")


def test_o_mesmo_negocio_de_dois_sites_vira_um_so():
    """A assessoria de quem vendeu e a de quem comprou postam o mesmo negócio, cada uma do seu jeito."""
    vendedor = _do_site(
        "um",
        SITE_1 + "a-alfa-oleos-foi-adquirida-pela-beta",
        pagina([("alfa-oleos", "Alfa Óleos")], [("beta", "Beta")]),
    )
    comprador = _do_site(
        "dois",
        SITE_2 + "beta-s-a-adquiriu-a-alfa-oleos-s-a",
        pagina([("beta-sa", "Beta S.A.")], [("alfa-oleos-sa", "Alfa Óleos S.A.")]),
    )
    sozinho = _do_site(
        "um",
        SITE_1 + "gama-foi-adquirida-pela-delta",
        pagina([("gama", "Gama")], [("delta", "Delta")]),
    )
    negocios = _negocios([vendedor, comprador, sozinho])
    assert len(negocios) == 3  # uma linha por página; o id junta
    assert negocios["id_negocio"].nunique() == 2
    assert (
        negocios.loc[vendedor["url"], "id_negocio"]
        == negocios.loc[comprador["url"], "id_negocio"]
    )
    assert negocios.loc[vendedor["url"], "paginas_do_negocio"] == 2
    assert negocios.loc[vendedor["url"], "duplicata_por"] == "partes_iguais"
    assert negocios.loc[sozinho["url"], "paginas_do_negocio"] == 1
    assert pd.isna(negocios.loc[sozinho["url"], "duplicata_por"])


def test_nomes_diferentes_da_mesma_entidade_tambem_juntam():
    rede = _rede((ID_ALFA, "Alfa Óleos S.A.", RAIZ_ALFA, None))
    rede = pd.concat(
        [rede, rede.assign(nome_normalizado="alfa oleos industria")], ignore_index=True
    )
    um = _do_site(
        "um",
        SITE_1 + "alfa-oleos-foi-adquirida-pela-beta",
        pagina([("alfa-oleos", "Alfa Óleos")], [("beta", "Beta")]),
    )
    dois = _do_site(
        "dois",
        SITE_2 + "beta-adquiriu-a-alfa-oleos-industria",
        pagina([("beta", "Beta")], [("alfa", "Alfa Óleos Indústria")]),
    )
    negocios = _negocios([um, dois], rede)
    assert negocios["id_negocio"].nunique() == 1


def test_as_mesmas_partes_na_mesma_assessoria_sao_negocios_diferentes():
    """Duas páginas do mesmo site são dois posts: uma rodada e, anos depois, a compra do controle."""
    rodada = _do_site(
        "um",
        SITE_1 + "alfa-recebeu-investimento-da-beta",
        pagina([("alfa", "Alfa")], [("beta", "Beta")]),
    )
    controle = _do_site(
        "um",
        SITE_1 + "alfa-foi-adquirida-pela-beta",
        pagina([("alfa", "Alfa")], [("beta", "Beta")]),
    )
    negocios = _negocios([rodada, controle])
    assert negocios["id_negocio"].nunique() == 2
    assert (negocios["paginas_com_as_mesmas_partes"] == 2).all()
    assert negocios["duplicata_por"].isna().all()


def test_tipos_diferentes_nao_juntam():
    um = _do_site(
        "um",
        SITE_1 + "alfa-recebeu-investimento-da-beta",
        pagina([("alfa", "Alfa")], [("beta", "Beta")]),
    )
    dois = _do_site(
        "dois",
        SITE_2 + "beta-adquiriu-a-alfa",
        pagina([("beta", "Beta")], [("alfa", "Alfa")]),
    )
    assert _negocios([um, dois])["id_negocio"].nunique() == 2


def test_id_do_negocio_nao_muda_quando_chega_o_segundo_site():
    um = _do_site(
        "um",
        SITE_1 + "alfa-foi-adquirida-pela-beta",
        pagina([("alfa", "Alfa")], [("beta", "Beta")]),
    )
    dois = _do_site(
        "dois",
        SITE_2 + "beta-adquiriu-a-alfa",
        pagina([("beta", "Beta")], [("alfa", "Alfa")]),
    )
    antes = _negocios([um]).loc[um["url"], "id_negocio"]
    depois = _negocios([um, dois]).loc[um["url"], "id_negocio"]
    assert antes == depois


# --- Receita ----------------------------------------------------------------------------------------
def _zip(linhas: list[list[str]]) -> io.BytesIO:
    texto = "\n".join(";".join(f'"{c}"' for c in linha) for linha in linhas) + "\n"
    arquivo = io.BytesIO()
    with zipfile.ZipFile(arquivo, "w") as z:
        z.writestr("K3241.K03200Y0.D61010.CSV", texto.encode("latin-1"))
    arquivo.seek(0)
    return arquivo


def _empresas() -> io.BytesIO:
    # básico; razão social; natureza; qualificação; capital; porte; ente
    return _zip(
        [
            [RAIZ_ALFA, "ALFA OLEOS S.A.", "2054", "10", "1000,00", "05", ""],
            [RAIZ_BETA, "FULANO EXEMPLAR 12345678909", "2135", "50", "0,00", "01", ""],
            [RAIZ_GAMA, "GAMA COMERCIO LTDA", "2062", "49", "10,00", "03", ""],
            [RAIZ_DELTA, "DELTA HOLDING LTDA", "2062", "49", "10,00", "03", ""],
            ["55555555", "OUTRA COISA LTDA", "2062", "49", "10,00", "03", ""],
            ["66666666", "OMEGA PAGAMENTOS LLC", "2062", "49", "10,00", "05", ""],
            ["77777777", "SINDICATO DOS EXEMPLOS", "3131", "16", "0,00", "05", ""],
        ]
    )


def _estabelecimentos() -> io.BytesIO:
    # básico; ordem; dv; matriz/filial; nome fantasia; situação; data; motivo; cidade; país; início
    def linha(
        raiz: str, ordem: str, matriz: str, fantasia: str, inicio: str
    ) -> list[str]:
        return [raiz, ordem, "00", matriz, fantasia, "02", "", "", "", "", inicio]

    return _zip(
        [
            linha(RAIZ_DELTA, "0001", "1", "DELTA", "19940613"),
            linha(
                RAIZ_DELTA, "0002", "2", "DELTA", "20240101"
            ),  # filial: liga pela raiz
            linha(RAIZ_BETA, "0001", "1", "FULANO", "20100101"),
            linha("55555555", "0001", "1", "", "20000101"),
            linha("66666666", "0001", "1", "", "20180725"),
            linha(RAIZ_ALFA, "0001", "1", "", "19660908"),
            linha("77777777", "0001", "1", "URGO", "19900101"),
        ]
    )


def _simples(mei: str = RAIZ_GAMA) -> io.BytesIO:
    return _zip([[mei, "S", "20200101", "", "S", "20200101", ""]])


def test_receita_devolve_so_raiz_e_o_nome_ja_normalizado():
    nomes = {
        "alfa oleos",
        "delta",
        "fulano",
        "gama comercio",
        "fulano exemplar 12345678909",
        "omega pagamentos",
        "urgo",
    }
    achados = lig.ler_receita([_empresas()], [_estabelecimentos()], [_simples()], nomes)
    assert list(achados.columns) == list(lig.COLUNAS_DA_RECEITA)
    por = {(a.raiz, a.por): a for a in achados.itertuples(index=False)}
    assert (RAIZ_ALFA, lig.RAZAO_SOCIAL) in por
    assert not por[(RAIZ_ALFA, lig.RAZAO_SOCIAL)].pessoa
    assert (RAIZ_DELTA, lig.NOME_FANTASIA) in por
    assert len(achados[achados["raiz"] == RAIZ_DELTA]) == 1  # matriz e filial: uma raiz
    assert por[(RAIZ_GAMA, lig.RAZAO_SOCIAL)].pessoa  # MEI
    assert por[(RAIZ_BETA, lig.NOME_FANTASIA)].pessoa  # empresário individual
    assert por[(RAIZ_BETA, lig.RAZAO_SOCIAL)].pessoa
    # nenhuma razão social sai do leitor: só o nome da parte, que já estava na página
    assert set(achados["nome_normalizado"]) <= nomes
    # a abertura é a da matriz (a filial de 2024 não conta)
    assert por[(RAIZ_DELTA, lig.NOME_FANTASIA)].abertura == pd.Timestamp("1994-06-13")
    assert por[(RAIZ_ALFA, lig.RAZAO_SOCIAL)].abertura == pd.Timestamp("1966-09-08")
    # nome fantasia "DELTA" e razão social "DELTA HOLDING": a razão social tem o nome
    assert por[(RAIZ_DELTA, lig.NOME_FANTASIA)].razao_tem_o_nome
    assert por[("66666666", lig.RAZAO_SOCIAL)].estrangeira
    assert not por[(RAIZ_ALFA, lig.RAZAO_SOCIAL)].estrangeira
    # porte 03 (EPP) é pequena; 05 (demais) não
    assert por[(RAIZ_DELTA, lig.NOME_FANTASIA)].pequena
    assert not por[(RAIZ_ALFA, lig.RAZAO_SOCIAL)].pequena
    # natureza do grupo 3 (3131, entidade sindical) é sem fins lucrativos; 2054 (S.A.) não
    assert por[("77777777", lig.NOME_FANTASIA)].sem_fins_lucrativos
    assert not por[(RAIZ_ALFA, lig.RAZAO_SOCIAL)].sem_fins_lucrativos


# --- contrato ---------------------------------------------------------------------------------------
def test_tabelas_tem_as_colunas_do_dicionario():
    assert set(TABELAS["ma_partes"].colunas) == set(lig.COLUNAS_DAS_PARTES)
    assert set(TABELAS["ma_negocios"].colunas) == set(lig.COLUNAS_DOS_NEGOCIOS)


# --- carga ------------------------------------------------------------------------------------------
PAGINAS = {
    "https://www.igcp.com.br/transactions/a-alfa-oleos-foi-adquirida-pela-delta": pagina(
        [("alfa-oleos", "Alfa Óleos")], [("delta-holding", "Delta Holding")]
    ),
    "https://www.igcp.com.br/transactions/omega-concluiu-a-emissao-de-um-cra": pagina(
        [("omega", "Ômega")]
    ),
}
RECEITA = (
    "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/2026-10/"
)


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    arquivos = {
        "assessoria-igc": PAGINAS,
        "rfb-cnpj": {
            RECEITA + "Empresas0.zip": _empresas().getvalue(),
            RECEITA + "Estabelecimentos0.zip": _estabelecimentos().getvalue(),
            RECEITA + "Simples.zip": _simples().getvalue(),
        },
    }
    with criar_engine(url).begin() as c:
        for fonte, conteudos in arquivos.items():
            for endereco, conteudo in conteudos.items():
                caminho = acervo.guardar_original(fonte, endereco, conteudo, QUANDO)
                registrar(
                    c, fonte, endereco, conteudo, "ok", agora=QUANDO,
                    caminho_do_original=caminho,
                )  # fmt: skip
    base = tmp_path / "acervo" / "base"
    gravar_tabela(
        pd.DataFrame(
            {
                "id_entidade": [ID_ALFA],
                "tipo": ["empresa"],
                "nome": ["ALFA OLEOS S.A."],
                "trata_como_pessoa": [False],
            }
        ),
        base / "rede" / "entidades",
        [{"url": "teste", "sha256": "0" * 64}],
        ["id_entidade"],
    )
    gravar_tabela(
        pd.DataFrame(
            {
                "id_entidade": [ID_ALFA],
                "sistema": ["cnpj_raiz"],
                "valor": [RAIZ_ALFA],
                "ate": [None],
            }
        ),
        base / "rede" / "identificadores",
        [{"url": "teste", "sha256": "0" * 64}],
        ["id_entidade"],
    )
    return base


def test_carga_liga_as_partes_e_grava_com_manifesto(ambiente, capsys):
    assert carga.main(["--base", str(ambiente)]) == 0
    arquivo = ambiente / "ma" / "ligacao" / "partes.parquet"
    assert conferir_tabela(arquivo)
    manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    assert manifesto["versao_do_codigo"] == VERSAO
    urls = {o["url"] for o in manifesto["origens"]}
    assert "ma/assessorias/igc.parquet" in urls
    assert "rede/entidades.parquet" in urls
    assert RECEITA + "Estabelecimentos0.zip" in urls
    partes = ler_tabela(arquivo).set_index("nome")
    assert partes.loc["Alfa Óleos", "id_entidade"] == ID_ALFA
    assert partes.loc["Delta Holding", "ligacao_por"] == "nome_exato"
    assert partes.loc["Ômega", "ligacao_por"] == "sem_ligacao"
    negocios = ler_tabela(ambiente / "ma" / "ligacao" / "negocios.parquet")
    assert len(negocios) == 2
    assert "2 com CNPJ" in capsys.readouterr().out
    antes = arquivo.with_suffix(".json").read_text(encoding="utf-8")
    carga.main(["--base", str(ambiente)])  # nada mudou: nada é lido de novo
    assert arquivo.with_suffix(".json").read_text(encoding="utf-8") == antes


def test_forcar_refaz_com_as_mesmas_entradas(ambiente, monkeypatch):
    """Só o código mudou (a regra da ligação): sem `--forcar` nada é refeito; com ele, sim."""
    assert carga.main(["--base", str(ambiente)]) == 0
    arquivo = ambiente / "ma" / "ligacao" / "partes.parquet"
    ligar = lig.ligar

    def ligar_diferente(*args, **kwargs):
        return ligar(*args, **kwargs).assign(ligacao_por=lig.NA_DUVIDA)

    monkeypatch.setattr(carga.ma_ligacao, "ligar", ligar_diferente)
    carga.main(["--base", str(ambiente)])
    assert set(ler_tabela(arquivo)["ligacao_por"]) != {lig.NA_DUVIDA}
    assert carga.main(["--base", str(ambiente), "--forcar"]) == 0
    assert set(ler_tabela(arquivo)["ligacao_por"]) == {lig.NA_DUVIDA}


def test_carga_sem_a_rede_nao_liga(ambiente, capsys):
    for arquivo in (ambiente / "rede").iterdir():
        arquivo.unlink()
    assert carga.main(["--base", str(ambiente)]) == 0
    assert not (ambiente / "ma" / "ligacao").exists()
    assert (ambiente / "ma" / "assessorias" / "igc.parquet").exists()


def test_resumo_conta_as_partes_do_brasil_e_de_fora():
    tabela = ma.tabela(
        [
            _negocio(url="u1", cliente="Alfa", paises="BR"),
            _negocio(url="u2", cliente="Beta", paises="US"),
        ]
    )
    rede = _rede((ID_ALFA, "Alfa", RAIZ_ALFA, None))
    ligadas = lig.ligar(lig.partes(tabela), rede, _receita())
    texto = lig.resumo(tabela, ligadas, lig.negocios(tabela, ligadas))
    assert "negócios só no Brasil: 1 partes, 1 com CNPJ" in texto
    assert "negócios sem BR na página: 1 partes" in texto
