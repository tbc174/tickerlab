"""As vizinhas do mesmo ramo (`conjuntos/vizinhas.py`, linha 1038): o bloco da análise completa.

Empresas ativas com a mesma atividade principal no município e, fora dele, na mesma UF, no retrato da Receita do
dia. Base de mentira, sem internet; os CNPJs são de ninguém. Riscos: pessoa (só as duas listas sem pessoa; razão
social com cara de CPF sai), olhar o futuro (o retrato só vale desde que ficou público), filtro por campo que o
portão nega (viraria oráculo) e uma UF grande demais para montar a lista dentro do prazo.
"""

import dataclasses
import re
from datetime import date

import pandas as pd
import pytest
import sqlalchemy as sa

from base import prontidao
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from conector_remoto import enxugar
from src import portao_externo as portao
from src.analista import analise as analise_da_tela
from src.api_externa import acesso, rotas
from src.api_externa.conjuntos import analise, empresas, vizinhas
from src.banco.modelo import consumo_da_api
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_empresas as empresas_de_mentira

ALVO = "11111111000191"
CNAE, OUTRO_CNAE = "2121103", "4711302"
CIDADE, OUTRA_CIDADE = "6291", "7107"  # Campinas e São Paulo no código da Receita
DIA = date(2026, 10, 15)
CARIMBOS = {
    "origem_sha256": "0" * 64,
    "montado_em": pd.Timestamp("2026-11-05", tz="UTC"),
    "versao_do_codigo": "teste",
}
# fmt: off
ESTABELECIMENTOS = [
    # cnpj, matriz, situação, abertura, cnae, uf, município, mês, disponível em
    (ALVO, True, "02", "2000-01-01", CNAE, "SP", CIDADE),
    ("11111111000272", False, "02", "2015-01-01", CNAE, "SP", CIDADE),  # filial da própria empresa
    ("22222222000191", True, "02", "2001-02-03", CNAE, "SP", CIDADE),
    ("33333333000191", True, "02", "2002-02-03", CNAE, "SP", CIDADE),
    ("44444444000191", True, "02", "2003-02-03", CNAE, "SP", OUTRA_CIDADE),  # matriz em outra cidade...
    ("44444444000272", False, "02", "2004-02-03", CNAE, "SP", CIDADE),  # ...e filial na cidade
    ("55555555000191", True, "02", "2005-02-03", CNAE, "SP", OUTRA_CIDADE),
    ("66666666000191", True, "02", "2006-02-03", CNAE, "MG", "4123"),  # outra UF
    ("77777777000191", True, "08", "2007-02-03", CNAE, "SP", CIDADE),  # baixada
    ("88888888000191", True, "02", "2008-02-03", OUTRO_CNAE, "SP", CIDADE),  # outro ramo
    ("99999999000191", True, "02", "2009-02-03", CNAE, "SP", CIDADE),  # razão social com cara de CPF
]
EMPRESAS = [
    # raiz, razão, natureza, porte, capital, estabelecimentos
    ("11111111", "ALVO FARMA S.A.", "2054", "demais", 9_000_000.0, 2),
    ("22222222", "BETA LABORATORIO LTDA", "2062", "pequeno", 100_000.0, 1),
    ("33333333", "GAMA REMEDIOS S.A.", "2054", "demais", 7_000_000.0, 3),
    ("44444444", "DELTA FARMA LTDA", "2062", "demais", 500_000.0, 2),
    ("55555555", "EPSILON SA", "2054", "demais", 50_000_000.0, 1),
    ("66666666", "ZETA SA", "2054", "demais", 80_000_000.0, 1),
    ("77777777", "BAIXADA LTDA", "2062", "micro", 1.0, 0),
    ("88888888", "OUTRO RAMO LTDA", "2062", "micro", 1.0, 1),
    ("99999999", "EMPRESA 123.456.789-09 LTDA", "2062", "micro", 99_000_000.0, 1),
]
# fmt: on
MESES = (("2026-09", "2026-09-30"),)


def _estabelecimentos(linhas=ESTABELECIMENTOS, meses=MESES) -> pd.DataFrame:
    colunas = [
        "cnpj", "matriz", "situacao_cadastral", "data_inicio_atividade", "cnae_principal", "uf", "municipio",
    ]  # fmt: skip
    partes = []
    for mes, disponivel in meses:
        tabela = pd.DataFrame(linhas, columns=colunas)
        tabela["data_inicio_atividade"] = pd.to_datetime(
            tabela["data_inicio_atividade"]
        )
        tabela["cnpj_basico"] = tabela["cnpj"].str[:8]
        tabela["mes_do_retrato"] = mes
        tabela["disponivel_em"] = date.fromisoformat(disponivel)
        partes.append(tabela)
    return pd.concat(partes, ignore_index=True).assign(**CARIMBOS)


def _empresas(linhas=EMPRESAS, meses=MESES) -> pd.DataFrame:
    colunas = [
        "cnpj_basico", "razao_social", "natureza_juridica", "porte", "capital_social", "n_estabelecimentos",
    ]  # fmt: skip
    partes = []
    for mes, disponivel in meses:
        tabela = pd.DataFrame(linhas, columns=colunas)
        tabela["mes_do_retrato"] = mes
        tabela["disponivel_em"] = date.fromisoformat(disponivel)
        partes.append(tabela)
    return pd.concat(partes, ignore_index=True).assign(**CARIMBOS)


def gravar(base, estabelecimentos: pd.DataFrame, empresas: pd.DataFrame) -> None:
    for nome, tabela in (
        (vizinhas.ESTABELECIMENTOS, estabelecimentos),
        (vizinhas.EMPRESAS, empresas),
    ):
        (base / nome).mkdir(parents=True, exist_ok=True)
        tabela.to_parquet(base / nome / "00.parquet", index=False)


def _gravar_a_rede(base, raiz_tratada_como_pessoa: str) -> None:
    """A rede com uma entidade que ela manda tratar como pessoa."""
    (base / "rede").mkdir()
    chave = "E" + "1" * 20
    pd.DataFrame(
        [(chave, "empresa", False, True)],
        columns=["id_entidade", "tipo", "mei", "trata_como_pessoa"],
    ).assign(
        nome=None,
        natureza_juridica="2062",
        natureza_fonte="receita",
        fontes="cvm-cadastro",
        publico_em=date(2020, 1, 1),
    ).to_parquet(base / "rede" / "entidades.parquet", index=False)
    pd.DataFrame(
        [(chave, "cnpj_raiz", raiz_tratada_como_pessoa)],
        columns=["id_entidade", "sistema", "valor"],
    ).assign(
        desde=None,
        ate=None,
        publico_em=date(2020, 1, 1),
        regra=2,
        conferido_por="regra",
        fontes="cvm-cadastro",
    ).to_parquet(base / "rede" / "identificadores.parquet", index=False)


@pytest.fixture
def pasta(tmp_path):
    base = tmp_path / "base"
    gravar(base, _estabelecimentos(), _empresas())
    return base


def _tudo(_fonte: str, _campo: str, _derivado: bool) -> bool:
    return True


def _sem(*campos: str):
    return lambda _fonte, campo, _derivado: campo not in campos


def _ler(pasta, cnpj=ALVO, dia=DIA, permitido=_tudo, linhas=10):
    with Porta(pasta) as porta:
        return vizinhas.LeitorDeVizinhas(porta, permitido, linhas).vizinhas(cnpj, dia)


def _cnpjs(itens: list[dict]) -> list[str]:
    return [item["cnpj"] for item in itens]


# ---------------------------------------------------------------- o que sai


def test_lista_as_do_mesmo_ramo_no_municipio_da_maior_para_a_menor_pelo_capital(pasta):
    corpo = _ler(pasta).corpo
    # a própria empresa (e a filial dela), a baixada, a de outro ramo, a de outra UF e a com CPF ficam fora
    assert _cnpjs(corpo["no_municipio"]) == [
        "33333333000191",
        "44444444000272",
        "22222222000191",
    ]
    assert _cnpjs(corpo["na_uf"]) == ["55555555000191"]


def test_cada_valor_traz_a_fonte_e_o_dia_em_que_ficou_publico(pasta):
    corpo = _ler(pasta).corpo
    primeira = corpo["no_municipio"][0]
    assert primeira["razao_social"] == {
        "valor": "GAMA REMEDIOS S.A.",
        "fonte": "rfb-cnpj",
        "publico_em": "2026-09-30",
        "visto_em": None,
    }
    assert primeira["capital_social"]["valor"] == 7_000_000.0
    assert primeira["n_estabelecimentos"]["valor"] == 3
    assert primeira["porte"]["valor"] == "other"
    assert primeira["data_inicio_atividade"]["valor"] == "2002-02-03"
    assert primeira["matriz"]["valor"] is True
    assert corpo["cnae_principal"]["valor"] == CNAE
    assert corpo["uf"]["valor"] == "SP"
    assert corpo["municipio_texto"]["valor"] == "CAMPINAS"
    assert corpo["mes_do_retrato"]["valor"] == "2026-09"
    assert _ler(pasta).fontes == {"rfb-cnpj"}


def test_empresa_com_filial_na_cidade_conta_uma_vez_e_diz_que_nao_e_a_matriz(pasta):
    corpo = _ler(pasta).corpo
    delta = next(i for i in corpo["no_municipio"] if i["cnpj"] == "44444444000272")
    assert delta["matriz"]["valor"] is False
    assert not [i for i in corpo["na_uf"] if i["cnpj"].startswith("44444444")]


def test_teto_proprio_de_vizinhas_por_recorte_mesmo_com_plano_que_da_mais(tmp_path):
    """A análise custa o mesmo com ou sem as vizinhas: o teto limita o que sai de graça (Diretoria, 26/11)."""
    muitas = [
        (f"{10_000_000 + n}000191", True, "02", "2010-01-01", CNAE, "SP", cidade)
        for n, cidade in enumerate([CIDADE] * 15 + [OUTRA_CIDADE] * 15)
    ]
    empresas_ = [
        (cnpj[:8], f"EMPRESA {cnpj[:8]} LTDA", "2062", "micro", 1000.0, 1)
        for cnpj, *_ in muitas
    ]
    gravar(
        tmp_path / "base",
        _estabelecimentos([ESTABELECIMENTOS[0], *muitas]),
        _empresas([EMPRESAS[0], *empresas_]),
    )
    corpo = _ler(tmp_path / "base", linhas=500).corpo
    assert vizinhas.TETO_DE_VIZINHAS == 10
    assert len(corpo["no_municipio"]) == len(corpo["na_uf"]) == 10
    assert corpo["total_no_municipio"] == 15 and corpo["total_na_uf"] == 30
    assert corpo["cortada"] is True
    assert "no máximo 10" in " ".join(corpo["limites"])


def test_empresario_individual_e_quem_a_rede_trata_como_pessoa_nao_sao_listados(
    tmp_path,
):
    """As listas da Receita já nascem sem MEI e empresário individual; a trava das outras leituras confirma."""
    individual = ("12121212000191", True, "02", "2012-01-01", CNAE, "SP", CIDADE)
    pessoa_da_rede = ("13131313000191", True, "02", "2013-01-01", CNAE, "SP", CIDADE)
    base = tmp_path / "base"
    gravar(
        base,
        _estabelecimentos([*ESTABELECIMENTOS, individual, pessoa_da_rede]),
        _empresas(
            [
                *EMPRESAS,
                ("12121212", "FULANO DE MENTIRA", "2135", "micro", 9e7, 1),
                ("13131313", "BELTRANO DE MENTIRA", "2062", "micro", 8e7, 1),
            ]
        ),
    )
    _gravar_a_rede(base, "13131313")
    corpo = _ler(base).corpo
    assert _cnpjs(corpo["no_municipio"]) == [
        "33333333000191",
        "44444444000272",
        "22222222000191",
    ]
    assert "DE MENTIRA" not in str(corpo)


def test_conta_o_ramo_no_municipio_e_na_uf_e_diz_quando_a_lista_foi_cortada(pasta):
    corpo = _ler(pasta, linhas=1).corpo
    assert _cnpjs(corpo["no_municipio"]) == ["33333333000191"]
    # a com CPF conta no total (é empresa do ramo), mas não é listada
    assert corpo["total_no_municipio"] == 4
    assert corpo["total_na_uf"] == 5
    assert corpo["cortada"] is True


def test_na_uf_traz_o_nome_do_municipio_de_cada_uma(pasta):
    (fora,) = _ler(pasta).corpo["na_uf"]
    assert fora["municipio_texto"]["valor"] == "SAO PAULO"


def test_os_limites_dizem_o_que_a_lista_e_e_o_que_nao_e(pasta):
    texto = " ".join(_ler(pasta).corpo["limites"])
    assert "capital social" in texto and "faturamento" in texto
    assert "empresário individual" in texto
    assert "dono" in texto and "risco" in texto


def test_uf_grande_demais_nao_monta_a_lista_de_fora_mas_diz_quantas_sao(
    pasta, monkeypatch
):
    monkeypatch.setattr(vizinhas, "TETO_NA_UF", 2)
    corpo = _ler(pasta).corpo
    assert corpo["na_uf"] == []
    assert corpo["total_na_uf"] == 5
    assert len(corpo["no_municipio"]) == 3
    assert vizinhas.LIMITE_DA_UF_GRANDE in corpo["limites"]


def test_ramo_sem_vizinha_sai_com_listas_vazias_e_total_zero(pasta):
    corpo = _ler(pasta, cnpj="88888888000191").corpo
    assert corpo["no_municipio"] == [] and corpo["na_uf"] == []
    assert corpo["total_no_municipio"] == 0 and corpo["total_na_uf"] == 0
    assert corpo["cortada"] is False


# ---------------------------------------------------------------- o portão


@pytest.mark.parametrize(
    "campo", ["razao_social", "cnae_principal", "uf", "municipio", "situacao_cadastral"]
)
def test_sem_um_campo_que_filtra_ou_nomeia_o_bloco_nao_sai(pasta, campo):
    assert _ler(pasta, permitido=_sem(campo)) is None


def test_sem_o_capital_a_ordem_e_pelo_cnpj_e_o_capital_nao_sai(pasta):
    corpo = _ler(pasta, permitido=_sem("capital_social")).corpo
    assert _cnpjs(corpo["no_municipio"]) == [
        "22222222000191",
        "33333333000191",
        "44444444000272",
    ]
    assert all("capital_social" not in item for item in corpo["no_municipio"])


# ---------------------------------------------------------------- quem pede


def test_cnpj_que_nao_e_empresa_ou_nao_esta_no_retrato_nao_tem_bloco(pasta):
    assert _ler(pasta, cnpj="00000000000191") is None


def test_cnpj_invalido_e_erro(pasta):
    with pytest.raises(ValueError):
        _ler(pasta, cnpj="123")


def test_antes_do_primeiro_retrato_publico_nao_ha_bloco(pasta):
    assert _ler(pasta, dia=date(2026, 9, 1)) is None


def test_cortar_o_futuro_nao_muda_o_passado(tmp_path):
    """O retrato de outubro (público em 31/10) não existe para quem pergunta em 15/10."""
    meses = (("2026-09", "2026-09-30"), ("2026-10", "2026-10-31"))
    futuro = [
        (cnpj, matriz, "08", abertura, cnae, uf, municipio)
        for cnpj, matriz, _, abertura, cnae, uf, municipio in ESTABELECIMENTOS
        if cnpj != ALVO
    ]
    estab = pd.concat(
        [
            _estabelecimentos(meses=meses[:1]),
            _estabelecimentos(futuro, meses=meses[1:]),
            _estabelecimentos([ESTABELECIMENTOS[0]], meses=meses[1:]),
        ],
        ignore_index=True,
    )
    gravar(tmp_path / "com", estab, _empresas(meses=meses))
    gravar(tmp_path / "sem", _estabelecimentos(), _empresas())
    assert _ler(tmp_path / "com").corpo == _ler(tmp_path / "sem").corpo
    depois = _ler(tmp_path / "com", dia=date(2026, 11, 5)).corpo
    assert (
        depois["no_municipio"] == []
    )  # no retrato novo todas as outras foram baixadas


# ---------------------------------------------------------------- na análise


def test_o_bloco_esta_registrado_na_analise_com_as_listas_dele():
    (bloco,) = [b for b in analise.BLOCOS if b.nome == vizinhas.BLOCO]
    assert bloco.conjunto == vizinhas.CONJUNTO
    assert bloco.finalidade == analise.ANALISE
    assert bloco.exige == vizinhas.EXIGE
    assert bloco.listas == ("no_municipio", "na_uf")
    # "não achado" é ramo sem vizinha, não lista vazia: a UF grande ou a trava podem esvaziar a lista
    vazias = {"no_municipio": [], "na_uf": []}
    assert bloco.vazio is not None
    assert bloco.vazio(vazias | {"total_na_uf": 0}) is True
    assert bloco.vazio(vazias | {"total_na_uf": 3}) is False
    assert bloco.aviso_se_fechado == vizinhas.NAO_HABILITADO
    # a análise custa o mesmo com ou sem as vizinhas; os outros blocos contam como antes
    assert [b.nome for b in analise.BLOCOS if not b.conta_pedido] == [vizinhas.BLOCO]
    nomes = [b.nome for b in analise.BLOCOS]
    assert nomes.index(vizinhas.BLOCO) == nomes.index("comparaveis") + 1


def test_a_tela_do_analista_ainda_nao_traz_o_bloco_e_diz_isso():
    """A tela não fala de chave nem de conjunto: diz que as vizinhas não estão disponíveis nela."""
    assert vizinhas.CONJUNTO in analise_da_tela.CONJUNTOS_AINDA_SEM_TELA
    assert vizinhas.BLOCO in analise_da_tela.TITULOS
    corpo = analise_da_tela.corpo_da_tela(
        {
            "cnpj": ALVO,
            "como_era_em": DIA.isoformat(),
            "frase": {"texto": "ALVO."},
            "blocos": {
                analise.CADASTRO: {},
                vizinhas.BLOCO: {"nao_habilitado": vizinhas.NAO_HABILITADO},
            },
            "linha_do_tempo": [],
            "leituras": [],
            "nao_encontrado": [],
            "nao_respondeu_a_tempo": [],
            "ainda_nao_traz": [],
            "limites": [],
        }
    )
    assert [b["nome"] for b in corpo["blocos"]] == [analise.CADASTRO]
    assert analise_da_tela.VIZINHAS_NAO_DISPONIVEIS in corpo["ainda_nao_traz"]


# ---------------------------------------------------------------- pela rota, com o contrato de cada organização

AGORA = empresas_de_mentira.AGORA
ROTA = f"/data/v1/companies/{ALVO}/analysis"
UM_CPF = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}|(?<!\d)\d{11}(?!\d)")


def _regras_das_vizinhas() -> portao.Regras:
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    tabelas = (*empresas.TABELAS, vizinhas.ESTABELECIMENTOS, vizinhas.EMPRESAS)
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    base = tmp_path / "rota"
    empresas_de_mentira._gravar_base(
        base,
        empresas_de_mentira._retratos(),
        com_rede=False,
        historicos=False,
    )
    gravar(base, _estabelecimentos(), _empresas())
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    monkeypatch.setattr(rotas, "regras_da_api", _regras_das_vizinhas)
    return aj.cliente_da_api(monkeypatch, AGORA)


def _organizacao_com(banco, ator, nome: str, *conjuntos: str):
    org = aj.organizacao(banco, ator, nome)
    chave = aj.chave(banco, ator, org)
    for conjunto in conjuntos:
        aj.contrato(banco, ator, org, conjunto=conjunto)
    return org, chave


def _por_conjunto(banco, org) -> dict[str, int]:
    """Os pedidos do mês, por conjunto."""
    with banco.connect() as conexao:
        linhas = conexao.execute(
            sa.select(consumo_da_api.c.conjunto, sa.func.sum(consumo_da_api.c.pedidos))
            .where(consumo_da_api.c.organizacao_id == org.id)
            .group_by(consumo_da_api.c.conjunto)
        ).all()
    return {conjunto: int(pedidos) for conjunto, pedidos in linhas}


def test_so_a_organizacao_com_a_busca_no_contrato_ve_as_vizinhas(banco, cliente):
    ator = aj.admin(banco)
    org_com, com = _organizacao_com(banco, ator, "Alfa", "companies", vizinhas.CONJUNTO)
    org_sem, sem = _organizacao_com(banco, ator, "Beta", "companies")
    parametros = {"known_at": DIA.isoformat()}
    resposta = cliente.get(ROTA, params=parametros, headers=aj.bearer(com.valor))
    assert resposta.status_code == 200
    bloco = resposta.json()["blocks"]["same_industry_neighbors"]
    assert [i["cnpj"] for i in bloco["in_municipality"]] == [
        "33333333000191",
        "44444444000272",
        "22222222000191",
    ]
    assert bloco["in_municipality"][0]["legal_name"]["source"] == "rfb-cnpj"
    assert bloco["in_municipality"][0]["legal_name"]["published_at"] == "2026-09-30"
    assert bloco["total_in_state"] == 5
    assert "rfb-cnpj" in {f["source"] for f in resposta.json()["sources"]}
    assert not UM_CPF.search(resposta.text)

    outra = cliente.get(ROTA, params=parametros, headers=aj.bearer(sem.valor))
    assert outra.status_code == 200
    # não some em silêncio: o bloco diz que o conjunto não está habilitado, sem nada da base
    assert outra.json()["blocks"]["same_industry_neighbors"] == {
        "not_enabled": vizinhas.NAO_HABILITADO
    }
    assert "LABORATORIO" not in outra.text and "prospecting" in outra.text

    # as vizinhas não somam pedido: as duas organizações gastam o mesmo, só o do cadastro
    assert resposta.json()["requests_used"] == outra.json()["requests_used"] == 1
    assert (
        _por_conjunto(banco, org_com)
        == _por_conjunto(banco, org_sem)
        == {"companies": 1}
    )


def test_os_limites_da_resposta_dizem_que_as_vizinhas_nao_contam_pedido(pasta):
    assert "as vizinhas não contam pedido" in " ".join(_ler(pasta).corpo["limites"])


def test_com_ou_sem_o_bloco_a_analise_custa_o_mesmo_na_quota_e_no_consumo(
    banco, cliente, monkeypatch
):
    """A exceção à regra de um pedido por conjunto lido: com uma quota em que só cabe a análise de antes, quem tem
    a busca de empresas não toma 429, e o consumo por conjunto é o mesmo de uma análise sem o bloco."""
    ator = aj.admin(banco)
    org_com, com = _organizacao_com(banco, ator, "Alfa", "companies", vizinhas.CONJUNTO)
    org_antes, antes = _organizacao_com(
        banco, ator, "Gama", "companies", vizinhas.CONJUNTO
    )
    limites = acesso.limites_da_api
    monkeypatch.setattr(
        acesso,
        "limites_da_api",
        lambda plano: dataclasses.replace(limites(plano), pedidos_por_mes=1),
    )
    parametros = {"known_at": DIA.isoformat()}
    agora_ = cliente.get(ROTA, params=parametros, headers=aj.bearer(com.valor))
    assert agora_.status_code == 200
    assert "in_municipality" in agora_.json()["blocks"]["same_industry_neighbors"]

    # a mesma análise como era antes do bloco existir
    monkeypatch.setattr(
        analise,
        "BLOCOS",
        tuple(b for b in analise.BLOCOS if b.nome != vizinhas.BLOCO),
    )
    antiga = cliente.get(ROTA, params=parametros, headers=aj.bearer(antes.valor))
    assert antiga.status_code == 200
    assert "same_industry_neighbors" not in antiga.text
    assert agora_.json()["requests_used"] == antiga.json()["requests_used"] == 1
    assert _por_conjunto(banco, org_com) == _por_conjunto(banco, org_antes)
    assert _por_conjunto(banco, org_com) == {"companies": 1}


def test_sem_a_busca_no_contrato_nada_das_vizinhas_e_lido(banco, cliente, monkeypatch):
    def ler(*_):
        raise AssertionError("o leitor das vizinhas não pode rodar sem o conjunto")

    monkeypatch.setattr(vizinhas.LeitorDeVizinhas, "vizinhas", ler)
    _org, sem = _organizacao_com(banco, aj.admin(banco), "Beta", "companies")
    resposta = cliente.get(
        ROTA, params={"known_at": DIA.isoformat()}, headers=aj.bearer(sem.valor)
    )
    assert resposta.status_code == 200
    assert resposta.json()["blocks"]["same_industry_neighbors"] == {
        "not_enabled": vizinhas.NAO_HABILITADO
    }
    assert resposta.json()["timed_out"] == []


# ---------------------------------------------------------------- no conector


def test_o_conector_corta_as_listas_do_bloco_e_diz_de_onde_pedir_o_resto():
    corpo = {
        "blocks": {
            "same_industry_neighbors": {
                "in_municipality": [{"cnpj": f"{n:014d}"} for n in range(5)],
                "elsewhere_in_state": [{"cnpj": f"{n:014d}"} for n in range(5)],
            }
        },
        "limits": [],
        "timed_out": [],
    }
    curto = enxugar.enxugar_analise(corpo, limite=2)
    bloco = curto["blocks"]["same_industry_neighbors"]
    assert len(bloco["in_municipality"]) == 2 and len(bloco["elsewhere_in_state"]) == 2
    assert bloco["truncated"] is True
    # atrasado, o aviso diz a ferramenta que traz a lista sozinha
    corpo["timed_out"] = [{"block": "same_industry_neighbors"}]
    atrasada = enxugar.enxugar_analise(corpo)
    assert "`buscar_empresas`" in " ".join(atrasada["limits"])
