"""Anatel, ANM (TAH), ANP (tancagem) e o PAT do MTE na análise completa, só no conjunto sem trava de licença
(ADR 0122, Emenda 2, 19/11/2026).

Base de mentira, sem internet; os CNPJs são de ninguém. O leitor (`conjuntos/por_tabela.py`) com a porta de verdade,
e a rota da análise com o portão e as linhas de direito de verdade. Riscos: a licença deixar de travar fora do
conjunto (no `profiles`, no site, para outra organização), linha de pessoa física saindo ou contando, bloco fechado
vazando pelo nome ou pelo tamanho (duas organizações, resposta idêntica com e sem o dado) e olhar o futuro.
"""

import dataclasses
from datetime import date

import pandas as pd
import pytest

from base import prontidao
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.api_externa import rotas, tabelas_por_cnpj
from src.api_externa.conjuntos import analise, ficha
from src.banco import coletas
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_analise as analise_de_mentira
from tests import test_api_externa_socios_pj as socios_de_mentira
from tests.test_api_externa_tabelas_por_cnpj import (
    AGORA,
    DIA,
    EMPRESA,
    OUTRA_RAIZ,
    RAIZ,
    _ler,
    _organizacao,
    gravar,
)

PADOS = "anatel_pados"
HOMOLOGADOS = "anatel_produtos_homologados"
TAH = "anm_tah"
TANCAGEM = "anp_tancagem"
PAT = "mte_pat"
TABELAS = (PADOS, HOMOLOGADOS, TAH, TANCAGEM, PAT)
FONTES = ("anatel-pados", "anatel-homologados", "anm-tah", "anp-tancagem", "mte-pat")
BLOCO = tabelas_por_cnpj.REGISTROS_ADICIONAIS
CONJUNTO = tabelas_por_cnpj.SEM_TRAVA_DE_LICENCA
DE_PESSOA = "LINHA-DE-PESSOA"  # marca do texto que só a linha de pessoa tem
NOMES_DE_FORA = (
    "additional_records",
    "anatel_enforcement_proceedings",
    "anatel_certified_products",
    "anm_annual_hectare_fee",
    "anp_storage_capacity",
    "mte_worker_meal_program",
    *FONTES,
)


def _comum(tabela: pd.DataFrame) -> pd.DataFrame:
    """As colunas de toda tabela ligada pelo CNPJ: a raiz, o id, a origem, as datas e a linha de empresa (a de
    pessoa vem marcada em cada fixture)."""
    for coluna in ("disponivel_em", "visto_em"):
        tabela[coluna] = pd.to_datetime(tabela[coluna]).dt.date
    return tabela.assign(
        cnpj_basico=tabela["cnpj"].str[:8],
        id_na_fonte=[f"id-{i}" for i in range(len(tabela))],
        origem_sha256="0" * 64,
    )


def _linhas(colunas: list[str], linhas: list[tuple]) -> pd.DataFrame:
    tabela = pd.DataFrame(
        linhas, columns=[*colunas, "disponivel_em", "consta", "trata_como_pessoa"]
    )
    tabela["visto_em"] = tabela["disponivel_em"]
    return _comum(tabela)


def _pados() -> pd.DataFrame:
    # fmt: off
    return _linhas(
        ["cnpj", "processo", "tema", "multa_aplicada"],
        [
            (EMPRESA, "PADO-1", "Qualidade", 5000.0, "2024-03-01", True, False),
            (EMPRESA, "PADO-SAIU", "SAIU-DO-ARQUIVO", 1.0, "2024-03-01", False, False),
            (RAIZ + "000270", "PADO-PESSOA", DE_PESSOA, 9.0, "2024-03-01", True, True),
            (RAIZ + "000351", "PADO-VAZIA", DE_PESSOA, 9.0, "2024-03-01", True, None),
            (OUTRA_RAIZ + "000100", "PADO-OUTRA", "OUTRA-EMPRESA", 9.0, "2024-03-01", True, False),
        ],
    )
    # fmt: on


def _homologados() -> pd.DataFrame:
    tabela = _linhas(
        ["cnpj", "numero_da_homologacao", "modelo", "data_da_homologacao"],
        [
            (EMPRESA, "H-1", "ROTEADOR X", "2023-05-02", "2023-05-10", True, False),
            (
                EMPRESA,
                "H-SAIU",
                "SAIU-DO-ARQUIVO",
                "2023-05-02",
                "2023-05-10",
                False,
                False,
            ),
            (
                RAIZ + "000270",
                "H-PESSOA",
                DE_PESSOA,
                "2023-05-02",
                "2023-05-10",
                True,
                True,
            ),
        ],
    )
    tabela["data_da_homologacao"] = pd.to_datetime(
        tabela["data_da_homologacao"]
    ).dt.date
    return tabela


def _tah() -> pd.DataFrame:
    tabela = _linhas(
        ["cnpj", "processo", "hectares", "valor_pago", "data_da_quitacao"],
        [
            (
                EMPRESA,
                "800.001/2020",
                120.5,
                800.0,
                "2025-01-31",
                "2025-02-05",
                True,
                False,
            ),
            (
                RAIZ + "000270",
                "TAH-PESSOA",
                5.0,
                9.0,
                "2025-01-31",
                "2025-02-05",
                True,
                True,
            ),
            (
                EMPRESA,
                "TAH-SAIU",
                5.0,
                9.0,
                "2025-01-31",
                "2025-02-05",
                False,
                False,
            ),
            (
                EMPRESA,
                "800.002/2020",
                10.0,
                90.0,
                "2025-12-31",
                "2026-01-05",
                True,
                False,
            ),
        ],
    )
    tabela["data_da_quitacao"] = pd.to_datetime(tabela["data_da_quitacao"]).dt.date
    return tabela


def _tancagem() -> pd.DataFrame:
    """A mesma instalação em duas posições: só a mais nova já pública no dia sai. A posição de pessoa, mais nova,
    não conta para escolher a data."""
    tabela = _linhas(
        [
            "cnpj",
            "codigo_da_instalacao",
            "grupo_de_produtos",
            "tancagem_m3",
            "data_da_posicao",
        ],
        [
            (
                EMPRESA,
                "INST-1",
                "Diesel",
                1000.0,
                "2024-01-01",
                "2024-01-15",
                True,
                False,
            ),
            (
                EMPRESA,
                "INST-1",
                "Diesel",
                1500.0,
                "2025-01-01",
                "2025-01-15",
                True,
                False,
            ),
            (
                EMPRESA,
                "INST-PESSOA",
                DE_PESSOA,
                9.0,
                "2025-03-01",
                "2025-03-10",
                True,
                True,
            ),
        ],
    )
    tabela["data_da_posicao"] = pd.to_datetime(tabela["data_da_posicao"]).dt.date
    return tabela


def _pat() -> pd.DataFrame:
    tabela = _linhas(
        [
            "cnpj",
            "registro_no_pat",
            "situacao",
            "trabalhadores_atendidos",
            "data_do_cadastro",
        ],
        [
            (EMPRESA, "PAT-1", "Ativa", 230, "2022-08-01", "2024-07-01", True, False),
            (
                EMPRESA,
                "PAT-SAIU",
                "SAIU-DO-ARQUIVO",
                1,
                "2022-08-01",
                "2024-07-01",
                False,
                False,
            ),
            (
                RAIZ + "000270",
                "PAT-PESSOA",
                DE_PESSOA,
                1,
                "2022-08-01",
                "2024-07-01",
                True,
                True,
            ),
        ],
    )
    tabela["data_do_cadastro"] = pd.to_datetime(tabela["data_do_cadastro"]).dt.date
    return tabela


def _gravar_tudo(pasta) -> None:
    for tabela, linhas in (
        (PADOS, _pados()),
        (HOMOLOGADOS, _homologados()),
        (TAH, _tah()),
        (TANCAGEM, _tancagem()),
        (PAT, _pat()),
    ):
        gravar(pasta, tabela, linhas)


@pytest.fixture
def base(tmp_path):
    pasta = tmp_path / "base"
    _gravar_tudo(pasta)
    return pasta


def _corpo(pasta, dia=DIA) -> dict:
    lido = _ler(pasta, BLOCO, dia=dia)
    assert lido is not None
    return lido.corpo


# ---------------------------------------------------------------- o registro e as marcas


def test_as_cinco_tabelas_estao_so_no_conjunto_sem_trava_com_a_marca_de_pessoa():
    entradas = {
        e.tabela: e for e in tabelas_por_cnpj.REGISTRO if e.conjunto == CONJUNTO
    }
    assert set(entradas) == set(TABELAS)
    assert {f for e in entradas.values() for f in e.fontes} == set(FONTES)
    for entrada in entradas.values():
        assert entrada.bloco == BLOCO and entrada.onde_sai == tabelas_por_cnpj.ANALISE
        assert entrada.marca_de_pessoa == tabelas_por_cnpj.TRATA_COMO_PESSOA
        assert set(entrada.campos).isdisjoint({"nome", "cnpj", "razao_social"})


def test_a_licenca_deixa_de_travar_so_no_conjunto_sem_trava():
    for fonte in (*FONTES, "anm-tah-2024", "mte-pat-beneficiarias"):
        assert coletas.sai_sem_trava_de_licenca(fonte, CONJUNTO), fonte
        for outro in ("profiles", "assets", coletas.CONJUNTO_DE_INTEGRIDADE):
            assert not coletas.sai_sem_trava_de_licenca(fonte, outro), (fonte, outro)
    # a família inteira não entra: só as fontes do lote, pelo prefixo
    for fora in (
        "anatel-acessos",
        "anm-cfem",
        "anp-concessionarios",
        "mte-lista-suja",
        "anatelx-pados",
    ):
        assert not coletas.sai_sem_trava_de_licenca(fora, CONJUNTO), fora


def test_fora_do_conjunto_o_portao_segue_negando_pela_marca():
    hoje = AGORA.date()
    regras = portao.regras_vigentes()
    for fonte in FONTES:
        assert portao._negacao_das_marcas(fonte, CONJUNTO, hoje, regras) is None
        assert portao._negacao_das_marcas(fonte, "profiles", hoje, regras) is not None


def test_o_portao_de_verdade_libera_so_no_conjunto():
    """O pedido inteiro, pela `decidir`: no conjunto (com a prontidão do teste) libera; no `profiles`, no
    `assets` e no de integridade, nega."""
    regras = _regras()
    campos = {
        "anatel-pados": "multa_aplicada",
        "anatel-homologados": "modelo",
        "anm-tah": "valor_pago",
        "anp-tancagem": "tancagem_m3",
        "mte-pat": "trabalhadores_atendidos",
    }
    for fonte, campo in campos.items():
        for conjunto in (
            CONJUNTO,
            "profiles",
            "assets",
            coletas.CONJUNTO_DE_INTEGRIDADE,
        ):
            pedido = portao.Pedido(
                fonte,
                conjunto,
                campo,
                portao.Canal.API_EXTERNA,
                portao.Finalidade.ANALISE,
            )
            decisao = portao.decidir(pedido, AGORA.date(), regras)
            assert decisao.libera is (conjunto == CONJUNTO), (fonte, conjunto, decisao)


def test_o_pat_segue_de_uso_interno_fora_do_conjunto():
    assert coletas.marca_da_fonte("mte-pat") is coletas.Marca.USO_INTERNO
    assert not coletas.sai_no_conjunto_de_integridade(
        "mte-pat", coletas.CONJUNTO_DE_INTEGRIDADE
    )


def test_as_cinco_fontes_saem_so_como_publicadas():
    """Rodapé CC BY-ND 3.0 ou licença a confirmar: nenhuma conta nossa sobre o registro, mesmo no conjunto."""
    for fonte in FONTES:
        pedido = portao.Pedido(
            fonte,
            CONJUNTO,
            "qualquer_campo",
            portao.Canal.API_EXTERNA,
            portao.Finalidade.ANALISE,
            derivado=True,
        )
        decisao = portao.decidir(pedido, AGORA.date(), _regras())
        assert decisao.motivo is portao.Motivo.SO_COMO_PUBLICADO, fonte


def test_toda_fonte_do_lote_tem_atribuicao():
    from src.api_externa.envelope import ATRIBUICOES_DA_API

    for fonte in FONTES:
        assert ATRIBUICOES_DA_API[fonte]


def test_o_bloco_nao_entra_na_lista_do_que_a_analise_nao_consulta():
    """Para a chave sem o conjunto, o bloco nem é citado: não vaza pelo nome."""
    assert analise.ainda_nao_traz(()) == list(analise.AINDA_NAO_TRAZ)
    assert not any(
        "Anatel" in frase or "ANM" in frase for frase in analise.AINDA_NAO_TRAZ
    )


# ---------------------------------------------------------------- o leitor


def test_so_a_linha_de_empresa_que_consta_sai(base):
    corpo = _corpo(base)
    pados = corpo["processos_sancionadores_da_anatel"]
    assert [i["processo"]["valor"] for i in pados["itens"]] == ["PADO-1"]
    assert pados["itens"][0]["multa_aplicada"]["fonte"] == "anatel-pados"
    texto = str(corpo)
    for fora in (
        DE_PESSOA,
        "PADO-PESSOA",
        "PADO-VAZIA",
        "SAIU-DO-ARQUIVO",
        "OUTRA-EMPRESA",
    ):
        assert fora not in texto


def test_em_toda_tabela_so_a_linha_de_empresa_que_consta_sai(base):
    corpo = _corpo(base)
    esperado = {
        "processos_sancionadores_da_anatel": ("processo", ["PADO-1"]),
        "produtos_homologados_na_anatel": ("numero_da_homologacao", ["H-1"]),
        "taxa_anual_por_hectare_da_anm": ("processo", ["800.001/2020"]),
        "tancagem_na_anp": ("codigo_da_instalacao", ["INST-1"]),
        "pat_do_mte": ("registro_no_pat", ["PAT-1"]),
    }
    for chave, (campo, valores) in esperado.items():
        itens = corpo[chave]["itens"]
        assert [i[campo]["valor"] for i in itens] == valores, chave
        assert DE_PESSOA not in str(itens) and "SAIU-DO-ARQUIVO" not in str(itens), (
            chave
        )


def test_cada_tabela_sai_na_chave_dela_com_a_fonte(base):
    corpo = _corpo(base)
    esperado = {
        "produtos_homologados_na_anatel": (
            "modelo",
            "ROTEADOR X",
            "anatel-homologados",
        ),
        "taxa_anual_por_hectare_da_anm": ("processo", "800.001/2020", "anm-tah"),
        "pat_do_mte": ("registro_no_pat", "PAT-1", "mte-pat"),
    }
    for chave, (campo, valor, fonte) in esperado.items():
        item = corpo[chave]["itens"][0]
        assert item[campo]["valor"] == valor, chave
        assert item[campo]["fonte"] == fonte, chave


def test_a_tancagem_traz_so_a_posicao_mais_nova_ja_publica(base):
    itens = _corpo(base)["tancagem_na_anp"]["itens"]
    assert [i["tancagem_m3"]["valor"] for i in itens] == [1500.0]
    antes = _corpo(base, dia=date(2024, 6, 30))["tancagem_na_anp"]["itens"]
    assert [i["tancagem_m3"]["valor"] for i in antes] == [1000.0]


def test_cortar_o_futuro_nao_muda_o_passado(tmp_path, base):
    sem_futuro = tmp_path / "sem"
    for tabela, linhas in (
        (PADOS, _pados()),
        (HOMOLOGADOS, _homologados()),
        (TAH, _tah()),
        (TANCAGEM, _tancagem()),
        (PAT, _pat()),
    ):
        gravar(sem_futuro, tabela, linhas[linhas["disponivel_em"] <= DIA])
    assert _corpo(sem_futuro) == _corpo(base)
    # o pagamento de dezembro de 2025 ainda não era público em junho
    assert "800.002/2020" not in str(_corpo(base))


# ---------------------------------------------------------------- a análise, com o portão de verdade


def _regras() -> portao.Regras:
    """As regras de verdade com o perfil e as cinco tabelas com a prontidão cheia (a prova com a data do teste):
    hoje a produção nega só pela prontidão, que é da faixa da mesa Dados (`base/prontidao.py`)."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    cheias = (*analise_de_mentira.DO_PERFIL, *TABELAS)
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in cheias},
    )


def _analise(monkeypatch, valor_da_chave, regras=_regras):
    monkeypatch.setattr(rotas, "regras_da_api", regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    return cliente.get(
        f"/data/v1/companies/{EMPRESA}/analysis",
        params={"known_at": DIA.isoformat()},
        headers=aj.bearer(valor_da_chave),
    )


def _pasta(tmp_path, monkeypatch, nome="base", com_dado=True):
    pasta = socios_de_mentira.base_com_socios(tmp_path / nome)
    if com_dado:
        _gravar_tudo(pasta)
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(pasta, banco_))
    return pasta


def test_com_o_conjunto_o_bloco_sai_com_fonte_e_data(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    chave = _organizacao(banco, aj.admin(banco), "Alfa", ficha.CONJUNTO, CONJUNTO)
    resposta = _analise(monkeypatch, chave.valor)
    assert resposta.status_code == 200
    bloco = resposta.json()["blocks"]["additional_records"]
    pados = bloco["anatel_enforcement_proceedings"]
    assert pados["found"] is True
    multa = pados["items"][0]["fine_imposed_brl"]
    assert multa["value"] == 5000.0 and multa["source"] == "anatel-pados"
    assert multa["published_at"] == "2024-03-01"
    assert (
        bloco["anp_storage_capacity"]["items"][0]["storage_capacity_m3"]["value"]
        == 1500.0
    )
    assert (
        bloco["mte_worker_meal_program"]["items"][0]["workers_served"]["value"] == 230
    )
    fontes = {f["source"] for f in resposta.json()["sources"]}
    assert set(FONTES) <= fontes
    for nunca in (DE_PESSOA, "PADO-PESSOA", "OUTRA-EMPRESA"):
        assert nunca not in resposta.text


def test_sem_o_conjunto_nada_aparece_nem_pelo_nome_nem_pelo_tamanho(
    tmp_path, banco, monkeypatch
):
    chave = _organizacao(banco, aj.admin(banco), "Beta", ficha.CONJUNTO)
    respostas = []
    for nome, com_dado in (("com", True), ("sem", False)):
        _pasta(tmp_path, monkeypatch, nome, com_dado=com_dado)
        resposta = _analise(monkeypatch, chave.valor)
        assert resposta.status_code == 200
        respostas.append(resposta.content)
    assert respostas[0] == respostas[1]
    for nome in NOMES_DE_FORA:
        assert nome not in respostas[0].decode()


def test_o_conjunto_de_outra_organizacao_nao_abre_nada(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    ator = aj.admin(banco)
    _organizacao(banco, ator, "Alfa", ficha.CONJUNTO, CONJUNTO)
    beta = _organizacao(banco, ator, "Beta", ficha.CONJUNTO)
    texto = _analise(monkeypatch, beta.valor).text
    for nome in NOMES_DE_FORA:
        assert nome not in texto


def test_o_conjunto_de_integridade_nao_abre_o_lote(tmp_path, banco, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    chave = _organizacao(
        banco, aj.admin(banco), "Alfa", ficha.CONJUNTO, tabelas_por_cnpj.INTEGRIDADE
    )
    texto = _analise(monkeypatch, chave.valor).text
    for nome in NOMES_DE_FORA:
        assert nome not in texto


def test_chave_invalida_nao_ve_nada(tmp_path, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    resposta = _analise(monkeypatch, "tl_chave_que_nao_existe")
    assert resposta.status_code == 401
    for nome in NOMES_DE_FORA:
        assert nome not in resposta.text


def test_sem_a_prontidao_o_conjunto_nao_libera_como_hoje_em_producao(
    tmp_path, banco, monkeypatch
):
    _pasta(tmp_path, monkeypatch)
    chave = _organizacao(banco, aj.admin(banco), "Alfa", ficha.CONJUNTO, CONJUNTO)
    so_o_perfil = lambda: dataclasses.replace(
        _regras(),
        prontidao={t: p for t, p in _regras().prontidao.items() if t not in TABELAS},
    )
    texto = _analise(monkeypatch, chave.valor, regras=so_o_perfil).text
    for nome in NOMES_DE_FORA:
        assert nome not in texto
