"""Consulta e exportação de cada tabela da base pela API aberta (virada de 5/11/2026, fase 1, PR 3).

A porta é uma base de mentira em `tmp_path/base`, com Parquets de tabelas reais do dicionário: a
`pgfn_divida` (com `cnpj`, uma linha de pessoa e uma coluna de pessoa que não existe no contrato), a
`cnpj_empresas_historico` (só `cnpj_basico`), a `curva_juros` (sem CNPJ) e a `sancoes_cgu` (tabela de
pessoa). A `insolvencia` é consultável, mas não tem arquivo nesta base.
"""

import csv
import gc
import io
import re
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from base import prontidao
from base.dicionario import TABELAS
from base.dossie import (
    COLUNAS_DE_PESSOA,
    ESPERAM_A_MARCA_DE_PESSOA,
    FECHADAS_ATE_A_PRONTIDAO,
    SO_PELA_API_EXTERNA,
    e_do_cnpj,
    exige_prontidao_na_consulta_aberta,
    pode_consultar,
    pode_consultar_aberto,
    pode_mostrar,
    servida_pela_porta,
    tem_dia_publico,
)
from base.porta import Porta
from base.porta.duckdb import ARQUIVOS
from src.api_v1 import VARIAVEL_DA_CHAVE, base_tabelas
from tests.ajudantes_da_api import cliente_do_gateway

ROTA = "/api/v1/base/tabelas"
SITE = {"Origin": "https://tickerlab.com.br"}
CPFL = "02.429.144/0001-93"
EMPRESA = "11.222.333/0001-81"
PESSOA = "12.345.678/0001-95"  # empresário individual: nunca sai (ADR 0075)
REGIAO_COM_VIRGULA = 'Região "Sul", RS'
COLETA = datetime(2025, 1, 15, 3, 0, tzinfo=UTC)


def _dividas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cnpj": [EMPRESA, EMPRESA, CPFL, PESSOA],
            "cnpj_basico": ["11222333", "11222333", "02429144", "12345678"],
            "tipo_divida": [
                "Previdenciário",
                "FGTS",
                "Previdenciário",
                "Previdenciário",
            ],
            "regiao": ["Sudeste", REGIAO_COM_VIRGULA, "Sudeste", "Norte"],
            "tipo_devedor": ["PRINCIPAL"] * 4,
            "tipo_situacao": ["Em cobrança"] * 4,
            "situacao_inscricao": ["ATIVA"] * 4,
            "ajuizado": [False, True, False, False],
            "inscricoes": [2, 1, 1, 1],
            "valor_consolidado": [1000.5, 250.0, 99.99, 10.0],
            "data_do_retrato": [date(2025, 1, 1), date(2025, 4, 1)]
            + [date(2025, 1, 1)] * 2,
            "trata_como_pessoa": [False, False, False, True],
            "disponivel_em": [date(2025, 1, 15), date(2025, 4, 10)]
            + [date(2025, 1, 15)] * 2,
            "origem_sha256": ["a" * 64] * 4,
            "origem_coletada_em": [COLETA] * 4,
            "versao_do_codigo": ["teste"] * 4,
            # coluna de pessoa que o contrato não tem: se um arquivo a trouxer, ela não sai
            "socio": ["Fulano"] * 4,
        }
    )


def _empresas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cnpj_basico": ["11222333", "02429144"],
            "mes_do_retrato": ["2025-01", "2025-01"],
            "disponivel_em": [date(2025, 2, 5)] * 2,
            "consta": [True, True],
            "natureza_juridica": ["2062", "2046"],
            "razao_social": ["EMPRESA A LTDA", "CPFL ENERGIA S.A."],
            "origem_sha256": ["b" * 64] * 2,
            "montado_em": [COLETA] * 2,
            "versao_do_codigo": ["teste"] * 2,
        }
    )


def _curva() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "data_base": [date(2025, 1, 2), date(2025, 1, 3)],
            "curva": ["pre", "pre"],
            "prazo_anos": [1.0, 1.0],
            "taxa": [0.12, 0.121],
            "titulos": [3, 3],
            "maior_prazo_anos": [10.0, 10.0],
            "disponivel_em": [date(2025, 1, 2), date(2025, 1, 3)],
            "origem_sha256": ["c" * 64] * 2,
            "origem_coletada_em": [COLETA] * 2,
            "versao_do_codigo": ["teste"] * 2,
        }
    )


def _sancoes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cadastro": ["CEIS"],
            "id_na_fonte": ["1"],
            "visto_em": [date(2025, 1, 2)],
            "nome_pessoa": ["Pessoa Privada"],
        }
    )


def _gravar(base: Path, tabela: str, linhas: pd.DataFrame) -> None:
    arquivo = base / ARQUIVOS[tabela].replace("*", "teste")
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    linhas.to_parquet(arquivo, index=False)


@pytest.fixture
def base(tmp_path) -> Path:
    pasta = tmp_path / "base"
    _gravar(pasta, "pgfn_divida", _dividas())
    _gravar(pasta, "cnpj_empresas_historico", _empresas())
    _gravar(pasta, "curva_juros", _curva())
    _gravar(pasta, "sancoes_cgu", _sancoes())
    return pasta


def _prontidao_de_todas_do_cnpj() -> dict[str, prontidao.Prontidao]:
    """Registro de mentira: toda tabela do CNPJ com as três provas de hoje (o teste, não a produção)."""
    prova = prontidao.Prova(datetime.now(UTC).date(), "conferida no teste", "teste")
    return {
        nome: prontidao.Prontidao(versao, prova, prova, prova)
        for nome, versao in prontidao.versoes_maiores().items()
        if exige_prontidao_na_consulta_aberta(nome)
    }


@pytest.fixture
def cliente(base, monkeypatch):
    """A consulta aberta com as tabelas do CNPJ prontas; a `sem_prontidao` mostra a produção de hoje."""
    monkeypatch.setattr(prontidao, "PRONTIDAO", _prontidao_de_todas_do_cnpj())
    base_tabelas.limpar_cache()
    monkeypatch.setattr(base_tabelas, "abrir_porta", lambda: Porta(base))
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    yield cliente_do_gateway({VARIAVEL_DA_CHAVE: "1"})
    base_tabelas.limpar_cache()


# --- a lista --------------------------------------------------------------------------------------
def test_lista_so_as_tabelas_consultaveis_com_colunas_fonte_e_licenca(cliente):
    r = cliente.get(ROTA, headers=SITE)
    assert r.status_code == 200, r.text
    tabelas = {t["tabela"]: t for t in r.json()["tabelas"]}
    assert set(tabelas) == {nome for nome in TABELAS if pode_consultar(nome)}
    assert {
        "pgfn_divida",
        "cnpj_empresas_historico",
        "curva_juros",
        "insolvencia",
    } <= set(tabelas)
    # pessoa, fora da porta, conferida no repositório e só interna ficam de fora
    assert {
        "sancoes_cgu",
        "cnpj_simples",
        "emissores_antigos",
        "processos_datajud",
    }.isdisjoint(tabelas)
    pgfn = tabelas["pgfn_divida"]
    assert pgfn["chaves"] == list(TABELAS["pgfn_divida"].chaves)
    assert pgfn["versao"] == TABELAS["pgfn_divida"].versao_do_contrato
    assert (
        pgfn["orgao"] == "PGFN" and pgfn["licenca"] and pgfn["fonte"] and pgfn["frase"]
    )
    assert pgfn["historico_desde"] == TABELAS["pgfn_divida"].historico_desde
    # a fonte e a licença como o site as mostra: sem decisão interna, ADR nem "perguntar"
    for t in tabelas.values():
        assert not re.search(
            r"\bADR\b|perguntar|\bML\b|`", t["licenca"] + t["fonte"]
        ), t
    nomes = [c["nome"] for c in pgfn["colunas"]]
    assert "cnpj" in nomes and "publico_em" in nomes and "aconteceu_em" in nomes
    assert all(c["tipo"] and c["descricao"] for c in pgfn["colunas"])
    # nenhuma coluna de pessoa em tabela nenhuma (a `ofertas_resolucao_160` tem `administrador`)
    assert "ofertas_resolucao_160" in tabelas
    assert not any(
        c["nome"] in COLUNAS_DE_PESSOA for t in tabelas.values() for c in t["colunas"]
    )
    assert r.json()["limite_maximo"] == base_tabelas.LIMITE_MAXIMO
    assert r.headers["cache-control"] == "public, max-age=3600"
    assert r.headers["access-control-allow-origin"] == "https://tickerlab.com.br"
    assert "set-cookie" not in r.headers


def test_lista_respeita_a_trava_de_mostrar(cliente, monkeypatch):
    monkeypatch.setattr("base.dossie.pode_mostrar", lambda _: False)
    assert cliente.get(ROTA).json()["tabelas"] == []


# --- o CNPJ só com prontidão (linha 840) ----------------------------------------------------------
@pytest.fixture
def sem_prontidao(cliente, monkeypatch):
    """Como a produção hoje: o registro de prontidão vazio."""
    monkeypatch.setattr(prontidao, "PRONTIDAO", {})
    return cliente


def _do_cnpj_consultaveis() -> set[str]:
    return {nome for nome in TABELAS if e_do_cnpj(nome) and pode_consultar(nome)}


def _fechadas_consultaveis() -> set[str]:
    return {
        nome
        for nome in TABELAS
        if nome in FECHADAS_ATE_A_PRONTIDAO and pode_consultar(nome)
    }


def test_familia_do_cnpj_inclui_as_cnpj_e_as_derivadas():
    familia = _do_cnpj_consultaveis()
    assert {
        "cnpj_empresas_pj",
        "cnpj_estabelecimentos_pj",
        "cnpj_empresas_historico",
        "cnpj_simples_historico",
        "cnpj_situacao_especial",
        "entidades",
        "identificadores",
        "ligacoes",
    } <= familia
    assert not e_do_cnpj("pgfn_divida") and not e_do_cnpj("curva_juros")


def test_sem_prontidao_a_lista_nao_anuncia_nenhuma_tabela_do_cnpj(sem_prontidao):
    nomes = {t["tabela"] for t in sem_prontidao.get(ROTA).json()["tabelas"]}
    assert nomes.isdisjoint(_do_cnpj_consultaveis())
    assert not any(n.startswith("cnpj_") for n in nomes)
    # as outras seguem como estavam
    assert nomes == {
        n
        for n in TABELAS
        if pode_consultar(n) and not exige_prontidao_na_consulta_aberta(n)
    }
    assert {"pgfn_divida", "curva_juros"} <= nomes


@pytest.mark.parametrize("nome", sorted(_do_cnpj_consultaveis()))
def test_sem_prontidao_linhas_e_csv_do_cnpj_dao_o_404_de_tabela_inexistente(
    sem_prontidao, nome
):
    inexistente = sem_prontidao.get(f"{ROTA}/nao_existe", headers=SITE)
    for rota in (f"{ROTA}/{nome}", f"{ROTA}/{nome}.csv"):
        r = sem_prontidao.get(rota, headers=SITE)
        assert r.status_code == 404 and r.json() == inexistente.json(), rota


def test_com_prontidao_a_tabela_do_cnpj_volta_sozinha(cliente, monkeypatch):
    monkeypatch.setattr(prontidao, "PRONTIDAO", {})
    assert cliente.get(f"{ROTA}/cnpj_empresas_historico").status_code == 404
    registro = _prontidao_de_todas_do_cnpj()
    monkeypatch.setattr(
        prontidao,
        "PRONTIDAO",
        {"cnpj_empresas_historico": registro["cnpj_empresas_historico"]},
    )
    r = cliente.get(f"{ROTA}/cnpj_empresas_historico", headers=SITE)
    assert r.status_code == 200 and r.json()["linhas"]
    nomes = {t["tabela"] for t in cliente.get(ROTA).json()["tabelas"]}
    assert "cnpj_empresas_historico" in nomes and "cnpj_empresas_pj" not in nomes


def test_prova_vencida_tira_a_tabela_do_cnpj_de_novo(cliente, monkeypatch):
    velha = prontidao.Prova(
        datetime.now(UTC).date() - prontidao.PRAZO_DA_PROVA - timedelta(days=1),
        "conferida no teste",
        "teste",
    )
    versao = prontidao.versoes_maiores()["cnpj_empresas_historico"]
    monkeypatch.setattr(
        prontidao,
        "PRONTIDAO",
        {"cnpj_empresas_historico": prontidao.Prontidao(versao, velha, velha, velha)},
    )
    assert not pode_consultar_aberto("cnpj_empresas_historico")
    assert cliente.get(f"{ROTA}/cnpj_empresas_historico").status_code == 404


def test_registro_de_ensaio_nao_abre_a_consulta_aberta(cliente, monkeypatch):
    """O ensaio liga o portão da API por chave (`registro_vigente`), nunca a consulta sem chave."""
    monkeypatch.setattr(prontidao, "PRONTIDAO", {})
    monkeypatch.setenv("TICKERLAB_AMBIENTE", "ensaio")
    assert not pode_consultar_aberto("cnpj_empresas_historico")


def test_o_que_ficou_em_casa_do_cnpj_nao_aparece_sem_prontidao(sem_prontidao):
    from scripts.montar_recorte_da_api import FICAM_EM_CASA

    nomes = {t["tabela"] for t in sem_prontidao.get(ROTA).json()["tabelas"]}
    assert not {n for n in FICAM_EM_CASA if e_do_cnpj(n)} & nomes


def test_api_por_chave_e_recorte_nao_mudam_com_a_trava():
    """A trava é só da consulta aberta: `pode_consultar` (recorte, vitrine do app) segue igual."""
    for nome in _do_cnpj_consultaveis():
        assert pode_consultar(nome)
    assert not pode_consultar_aberto("cnpj_empresas_pj")


# --- o 404 igual ----------------------------------------------------------------------------------
def test_tabela_inexistente_de_pessoa_barrada_ou_fora_da_porta_dao_o_mesmo_404(
    cliente, monkeypatch
):
    """Quem pergunta não descobre por que a tabela não sai: a resposta é a mesma da que não existe."""
    respostas = {}
    for caso, nome in [
        ("inexistente", "nao_existe"),
        ("pessoa", "sancoes_cgu"),  # tem arquivo nesta base, mas é tabela de pessoa
        ("fora_da_porta", "cnpj_simples"),  # pode ser mostrada, mas a porta não a serve
        ("conferida", "emissores_antigos"),  # CSV do repositório, não Parquet da base
    ]:
        r = cliente.get(f"{ROTA}/{nome}", headers=SITE)
        respostas[caso] = (
            r.status_code,
            r.json(),
            r.headers.get("access-control-allow-origin"),
        )
        assert cliente.get(f"{ROTA}/{nome}.csv").status_code == 404
    monkeypatch.setattr("base.dossie.pode_mostrar", lambda _: False)
    r = cliente.get(f"{ROTA}/pgfn_divida", headers=SITE)
    respostas["barrada"] = (
        r.status_code,
        r.json(),
        r.headers.get("access-control-allow-origin"),
    )
    assert len(set(map(str, respostas.values()))) == 1, respostas
    assert respostas["inexistente"] == (
        404,
        {"detail": "Tabela não encontrada."},
        "https://tickerlab.com.br",
    )


# --- a página -------------------------------------------------------------------------------------
def _chaves(corpo: dict) -> list[tuple[str, str]]:
    return [(linha["cnpj"], linha["tipo_divida"]) for linha in corpo["linhas"]]


def test_pagina_vem_na_ordem_das_chaves_com_total_e_origem(cliente):
    r = cliente.get(f"{ROTA}/pgfn_divida", headers=SITE)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert (corpo["tabela"], corpo["versao"]) == (
        "pgfn_divida",
        TABELAS["pgfn_divida"].versao_do_contrato,
    )
    assert corpo["orgao"] == "PGFN" and corpo["fonte"] and corpo["licenca"]
    assert (corpo["total"], corpo["limite"], corpo["deslocamento"]) == (3, 100, 0)
    # sem data, vale hoje: o que só fica público depois não sai (ver o teste do futuro, abaixo)
    assert corpo["como_era_em"] == base_tabelas.base_publica.hoje().isoformat()
    assert corpo["teto_do_csv"] == base_tabelas.TETO_DO_CSV
    assert _chaves(corpo) == [
        (CPFL, "Previdenciário"),
        (EMPRESA, "FGTS"),
        (EMPRESA, "Previdenciário"),
    ]
    assert corpo["colunas"] == list(corpo["linhas"][0])
    assert "recomendação" in corpo["aviso"]
    assert r.headers["cache-control"] == "public, max-age=3600"
    assert r.headers["access-control-allow-origin"] == "https://tickerlab.com.br"


def test_toda_linha_sai_com_a_origem_e_as_datas_em_iso(cliente):
    linha = cliente.get(f"{ROTA}/pgfn_divida", params={"cnpj": CPFL}).json()["linhas"][
        0
    ]
    assert (
        linha["publico_em"] == "2025-01-31"
    )  # o mês de `disponivel_em` vale pelo último dia
    assert linha["aconteceu_em"] == linha["data_do_retrato"] == "2025-01-01"
    assert linha["coletado_em"] == "2025-01-15"
    assert linha["origem_coletada_em"].startswith("2025-01-15T03:00:00")
    assert linha["origem_sha256"] == "a" * 64
    assert linha["ajuizado"] is False and linha["inscricoes"] == 1
    assert linha["valor_consolidado"] == 99.99


def test_pessoa_nao_sai_nem_em_linha_nem_em_coluna(cliente):
    r = cliente.get(f"{ROTA}/pgfn_divida")
    corpo = r.json()
    assert PESSOA not in r.text and "Fulano" not in r.text
    assert "socio" not in corpo["colunas"]
    assert all("socio" not in linha for linha in corpo["linhas"])
    assert corpo["total"] == 3
    csv = cliente.get(f"{ROTA}/pgfn_divida.csv").text
    assert PESSOA not in csv and "socio" not in csv and "Fulano" not in csv


def test_paginacao_com_limite_e_deslocamento(cliente):
    primeira = cliente.get(f"{ROTA}/pgfn_divida", params={"limite": 2}).json()
    segunda = cliente.get(
        f"{ROTA}/pgfn_divida", params={"limite": 2, "deslocamento": 2}
    ).json()
    fim = cliente.get(
        f"{ROTA}/pgfn_divida", params={"limite": 2, "deslocamento": 10}
    ).json()
    assert _chaves(primeira) == [(CPFL, "Previdenciário"), (EMPRESA, "FGTS")]
    assert _chaves(segunda) == [(EMPRESA, "Previdenciário")]
    assert fim["linhas"] == [] and fim["total"] == 3
    assert (primeira["total"], segunda["total"]) == (3, 3)
    assert (segunda["limite"], segunda["deslocamento"]) == (2, 2)


@pytest.mark.parametrize(
    "parametros",
    [
        {"limite": 0},
        {"limite": base_tabelas.LIMITE_MAXIMO + 1},
        {"deslocamento": -1},
        {
            "deslocamento": base_tabelas.TETO_DO_CSV + 1
        },  # o OFFSET alto ordena tudo: filtre
        {"limite": "muitos"},
        {"como_era_em": "ontem"},
        {"como_era_em": "2999-01-01"},  # o futuro não se consulta
        {"cnpj": "abc"},
        {"cnpj": "11222333000100"},  # dígitos verificadores errados
    ],
)
def test_pedido_invalido_e_422(cliente, parametros):
    r = cliente.get(f"{ROTA}/pgfn_divida", params=parametros, headers=SITE)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]


def test_entrada_invalida_leva_os_cabecalhos_do_site(cliente):
    """O navegador do site lê a mensagem da recusa, em vez de um erro de CORS."""
    r = cliente.get(f"{ROTA}/pgfn_divida", params={"cnpj": "abc"}, headers=SITE)
    assert r.status_code == 422
    assert r.headers["access-control-allow-origin"] == "https://tickerlab.com.br"
    assert "dígitos" in r.json()["detail"]


def test_como_era_em_so_enxerga_o_que_ja_era_publico(cliente):
    em_fevereiro = cliente.get(
        f"{ROTA}/pgfn_divida", params={"como_era_em": "2025-02-28"}
    ).json()
    antes = cliente.get(
        f"{ROTA}/pgfn_divida", params={"como_era_em": "2024-12-31"}
    ).json()
    assert em_fevereiro["como_era_em"] == "2025-02-28"
    assert em_fevereiro["total"] == len(em_fevereiro["linhas"]) == 2
    assert _chaves(em_fevereiro) == [
        (CPFL, "Previdenciário"),
        (EMPRESA, "Previdenciário"),
    ]
    assert all(linha["publico_em"] <= "2025-02-28" for linha in em_fevereiro["linhas"])
    assert antes["total"] == 0 and antes["linhas"] == []


@pytest.mark.parametrize("cnpj", ["11222333000181", EMPRESA])
def test_filtro_por_cnpj_nos_dois_formatos(cliente, cnpj):
    corpo = cliente.get(f"{ROTA}/pgfn_divida", params={"cnpj": cnpj}).json()
    assert corpo["total"] == 2
    assert _chaves(corpo) == [(EMPRESA, "FGTS"), (EMPRESA, "Previdenciário")]


def test_tabela_so_com_a_raiz_filtra_pela_raiz(cliente):
    corpo = cliente.get(
        f"{ROTA}/cnpj_empresas_historico", params={"cnpj": EMPRESA}
    ).json()
    assert corpo["total"] == 1
    assert corpo["linhas"][0]["cnpj_basico"] == "11222333"
    assert corpo["linhas"][0]["publico_em"] == "2025-02-28"
    assert corpo["linhas"][0]["consta"] is True


def test_tabela_sem_cnpj_recusa_o_filtro(cliente):
    sem_filtro = cliente.get(f"{ROTA}/curva_juros")
    com_filtro = cliente.get(f"{ROTA}/curva_juros", params={"cnpj": EMPRESA})
    assert sem_filtro.status_code == 200 and sem_filtro.json()["total"] == 2
    assert sem_filtro.json()["linhas"][0]["data_base"] == "2025-01-02"
    assert com_filtro.status_code == 422
    assert "não é por CNPJ" in com_filtro.json()["detail"]


# --- o CSV ----------------------------------------------------------------------------------------
def test_csv_com_bom_cabecalho_aspas_e_nome_do_arquivo(cliente):
    r = cliente.get(f"{ROTA}/pgfn_divida.csv", headers=SITE)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert r.headers["content-disposition"] == 'attachment; filename="pgfn_divida.csv"'
    assert r.headers[base_tabelas.CABECALHO_DO_TETO] == str(base_tabelas.TETO_DO_CSV)
    assert r.headers["access-control-allow-origin"] == "https://tickerlab.com.br"
    assert r.content.startswith("\ufeff".encode())
    linhas = r.content.decode("utf-8-sig").splitlines()
    cabecalho = linhas[0].split(",")
    assert cabecalho[:3] == ["cnpj", "cnpj_basico", "tipo_divida"]
    assert "publico_em" in cabecalho and "socio" not in cabecalho
    assert len(linhas) == 1 + 3  # a linha de pessoa não sai
    assert linhas[1].startswith(f"{CPFL},02429144,Previdenciário,Sudeste,")
    assert f'"{REGIAO_COM_VIRGULA.replace(chr(34), chr(34) * 2)}"' in linhas[2]
    assert ",true," in linhas[2] and ",false," in linhas[1]
    assert ",2025-01-31," in linhas[1]  # data em ISO, só o dia


def test_csv_respeita_os_filtros_e_recusa_os_invalidos(cliente):
    por_cnpj = cliente.get(f"{ROTA}/pgfn_divida.csv", params={"cnpj": "11222333000181"})
    em_fevereiro = cliente.get(
        f"{ROTA}/pgfn_divida.csv", params={"como_era_em": "2025-02-28"}
    )
    assert len(por_cnpj.content.decode("utf-8-sig").splitlines()) == 1 + 2
    assert len(em_fevereiro.content.decode("utf-8-sig").splitlines()) == 1 + 2
    assert (
        cliente.get(f"{ROTA}/pgfn_divida.csv", params={"cnpj": "abc"}).status_code
        == 422
    )
    assert (
        cliente.get(
            f"{ROTA}/pgfn_divida.csv", params={"como_era_em": "2999-01-01"}
        ).status_code
        == 422
    )
    assert (
        cliente.get(f"{ROTA}/curva_juros.csv", params={"cnpj": EMPRESA}).status_code
        == 422
    )


def _linhas_do_csv(resposta) -> list[list[str]]:
    return list(csv.reader(io.StringIO(resposta.content.decode("utf-8-sig"))))


def test_csv_que_bate_no_teto_diz_na_ultima_linha_que_cortou(cliente, monkeypatch):
    """Regressão (revisão do PR 3): o CSV parava no teto sem nada no arquivo, e o site dizia "a
    tabela inteira". Agora a última linha diz que cortou; a tabela que cabe sai sem aviso."""
    monkeypatch.setattr(base_tabelas, "TETO_DO_CSV", 3)
    inteira = _linhas_do_csv(cliente.get(f"{ROTA}/pgfn_divida.csv"))
    monkeypatch.setattr(base_tabelas, "TETO_DO_CSV", 2)
    cortado = cliente.get(f"{ROTA}/pgfn_divida.csv")
    linhas = _linhas_do_csv(cortado)
    assert len(inteira) == 1 + 3 and not inteira[-1][0].startswith("#")
    assert len(linhas) == 1 + 2 + 1
    assert linhas[1:3] == inteira[1:3]
    assert linhas[-1] == [base_tabelas.AVISO_DO_TETO.format(teto=2)]
    assert linhas[-1][0].startswith("# Arquivo cortado em 2 linhas")
    assert cortado.headers[base_tabelas.CABECALHO_DO_TETO] == "2"


def test_csv_leva_a_fonte_e_a_licenca_em_cada_linha(cliente):
    """Regressão (revisão do PR 3): o arquivo saía sem fonte nem licença, e repassado perdia a
    atribuição que a licença pede. As duas vão no fim de cada linha, iguais às do JSON."""
    origem = cliente.get(f"{ROTA}/pgfn_divida").json()
    linhas = _linhas_do_csv(cliente.get(f"{ROTA}/pgfn_divida.csv"))
    assert linhas[0][-2:] == list(base_tabelas.COLUNAS_DA_ORIGEM)
    assert all(
        linha[-2:] == [origem["fonte"], origem["licenca"]] for linha in linhas[1:]
    )
    assert origem["fonte"] and origem["licenca"]


def test_nenhuma_tabela_consultavel_tem_coluna_com_o_nome_da_origem():
    """As duas colunas da origem no CSV não podem repetir o nome de uma coluna da tabela."""
    for nome in TABELAS:
        if pode_consultar(nome):
            colunas = set(TABELAS[nome].colunas) | set(TABELAS[nome].datas)
            assert not colunas & set(base_tabelas.COLUNAS_DA_ORIGEM), nome


class _PortaQueFalhaNoMeio(Porta):
    """Lê o primeiro lote (ou a primeira página) e falha no seguinte, como o DuckDB sem memória."""

    def ler_em_lotes(self, tabela, **opcoes):
        lotes = super().ler_em_lotes(tabela, **{**opcoes, "vetores_por_lote": 1})
        yield next(lotes).head(1)
        raise duckdb.OutOfMemoryException("sem memória")

    def ler_pagina(self, tabela, **opcoes):
        if opcoes.get("deslocamento"):
            raise duckdb.OutOfMemoryException("sem memória")
        return super().ler_pagina(tabela, **opcoes)


def test_csv_que_falha_no_meio_diz_na_ultima_linha_que_esta_incompleto(
    cliente, base, monkeypatch
):
    """Regressão (revisão do PR 3): a base que falhava depois da primeira parte (o DuckDB sem
    memória no OFFSET alto) cortava o fluxo já em 200, e o arquivo parecia inteiro. Agora a última
    linha diz que está incompleto, e a porta fecha."""
    abertas: list[Porta] = []

    def abrir() -> Porta:
        abertas.append(_PortaQueFalhaNoMeio(base))
        return abertas[-1]

    monkeypatch.setattr(base_tabelas, "abrir_porta", abrir)
    monkeypatch.setattr(base_tabelas, "LINHAS_POR_PAGINA_DO_CSV", 1, raising=False)
    r = cliente.get(f"{ROTA}/pgfn_divida.csv")
    linhas = _linhas_do_csv(r)
    assert r.status_code == 200
    assert linhas[-1] == [base_tabelas.AVISO_DA_FALHA.format(linhas=1)]
    assert len(linhas) == 1 + 1 + 1
    with pytest.raises(Exception, match="closed"):
        abertas[0].con.execute("SELECT 1")


def test_csv_vazio_tem_so_o_cabecalho(cliente):
    r = cliente.get(f"{ROTA}/pgfn_divida.csv", params={"como_era_em": "2024-12-31"})
    assert r.status_code == 200
    colunas = cliente.get(f"{ROTA}/pgfn_divida").json()["colunas"]
    assert r.content.decode("utf-8-sig").splitlines() == [
        ",".join([*colunas, *base_tabelas.COLUNAS_DA_ORIGEM])
    ]


# --- limites, CORS, API desligada e base indisponível ---------------------------------------------
def test_limite_por_ip_e_429(cliente):
    for _ in range(base_tabelas.base_publica.PEDIDOS_POR_MINUTO):
        assert cliente.get(ROTA).status_code == 200
    assert cliente.get(ROTA).status_code == 429
    assert cliente.get(f"{ROTA}/pgfn_divida").status_code == 429
    assert cliente.get(f"{ROTA}/pgfn_divida.csv").status_code == 429


def test_cors_so_para_o_site(cliente):
    de_fora = cliente.get(
        f"{ROTA}/pgfn_divida", headers={"Origin": "https://outro.exemplo"}
    )
    sem_origem = cliente.get(f"{ROTA}/pgfn_divida")
    assert de_fora.status_code == sem_origem.status_code == 200
    assert "access-control-allow-origin" not in de_fora.headers
    assert "access-control-allow-origin" not in sem_origem.headers
    assert de_fora.headers["vary"] == "Origin"


def test_api_desligada_e_404(base, monkeypatch):
    monkeypatch.delenv(VARIAVEL_DA_CHAVE, raising=False)
    monkeypatch.setattr(base_tabelas, "abrir_porta", lambda: Porta(base))
    cliente = cliente_do_gateway({})
    assert cliente.get(ROTA).status_code == 404
    assert cliente.get(f"{ROTA}/pgfn_divida").status_code == 404
    assert cliente.get(f"{ROTA}/pgfn_divida.csv").status_code == 404


def test_tabela_sem_arquivo_nesta_base_e_503(cliente):
    """A `insolvencia` é consultável, mas o servidor da API não tem o acervo: 503, sem dizer onde."""
    r = cliente.get(f"{ROTA}/insolvencia", headers=SITE)
    assert r.status_code == 503, r.text
    assert "indisponível" in r.json()["detail"]
    assert r.headers["access-control-allow-origin"] == "https://tickerlab.com.br"
    assert cliente.get(f"{ROTA}/insolvencia.csv").status_code == 503


def test_porta_que_nao_abre_e_503(cliente, monkeypatch):
    def sem_acervo() -> Porta:
        raise ValueError("acervo desligado (TICKERLAB_ACERVO)")

    monkeypatch.setattr(base_tabelas, "abrir_porta", sem_acervo)
    assert cliente.get(f"{ROTA}/pgfn_divida").status_code == 503
    assert cliente.get(f"{ROTA}/pgfn_divida.csv").status_code == 503
    assert cliente.get(ROTA).status_code == 200  # a lista é do dicionário, não da base


def test_porta_fecha_depois_do_csv(cliente, base, monkeypatch):
    abertas: list[Porta] = []

    def abrir() -> Porta:
        abertas.append(Porta(base))
        return abertas[-1]

    monkeypatch.setattr(base_tabelas, "abrir_porta", abrir)
    assert cliente.get(f"{ROTA}/pgfn_divida.csv").status_code == 200
    assert cliente.get(f"{ROTA}/pgfn_divida").status_code == 200
    assert len(abertas) == 2
    for porta in abertas:
        with pytest.raises(Exception, match="closed"):
            porta.con.execute("SELECT 1")


# --- regressões da revisão cruzada do PR 3 --------------------------------------------------------
def test_sem_como_era_em_vale_hoje_e_a_linha_ainda_nao_publica_nao_sai(
    cliente, monkeypatch
):
    """Regressão: sem `como_era_em`, a porta lia sem o filtro de `publico_em`, e o JSON e o CSV
    traziam linhas que a própria base diz que só ficam públicas depois de hoje. Com "hoje" em
    28/02/2025, a dívida de FGTS (pública em 30/04/2025) não sai, nem no total, nem no CSV."""
    monkeypatch.setattr(base_tabelas.base_publica, "hoje", lambda: date(2025, 2, 28))
    corpo = cliente.get(f"{ROTA}/pgfn_divida").json()
    linhas = _linhas_do_csv(cliente.get(f"{ROTA}/pgfn_divida.csv"))
    assert corpo["como_era_em"] == "2025-02-28"
    assert corpo["total"] == len(corpo["linhas"]) == 2
    assert all(linha["publico_em"] <= "2025-02-28" for linha in corpo["linhas"])
    assert "FGTS" not in {linha["tipo_divida"] for linha in corpo["linhas"]}
    assert len(linhas) == 1 + 2 and not any("FGTS" in linha for linha in linhas)
    amanha = (date(2025, 2, 28) + timedelta(days=1)).isoformat()
    assert (
        cliente.get(f"{ROTA}/pgfn_divida", params={"como_era_em": amanha}).status_code
        == 422
    )


def test_so_e_consultavel_a_tabela_que_diz_o_dia_publico_e_separa_a_pessoa(cliente):
    """Regressão: 15 tabelas sem `publico_em` saíam sem o dia em que cada linha ficou pública (e
    `como_era_em` nelas dava 500); a situação especial e a cadastral do CNPJ, que cobrem MEI e
    empresário individual sem a marca de pessoa, saíam em lote. Agora todas dão o mesmo 404."""
    consultaveis = [nome for nome in TABELAS if pode_consultar(nome)]
    assert all(tem_dia_publico(nome) for nome in consultaveis)
    assert not set(consultaveis) & ESPERAM_A_MARCA_DE_PESSOA
    assert len(consultaveis) > 50
    for nome in ["proventos", "cadastro_de_fundos", *sorted(ESPERAM_A_MARCA_DE_PESSOA)]:
        assert not pode_consultar(nome), nome
        assert cliente.get(
            f"{ROTA}/{nome}", params={"como_era_em": "2025-01-01"}
        ).json() == {"detail": base_tabelas.NAO_ENCONTRADA}
        assert cliente.get(f"{ROTA}/{nome}.csv").status_code == 404
    assert tem_dia_publico("pgfn_divida") and not tem_dia_publico("proventos")


@pytest.mark.parametrize(
    "nome",
    [
        "entradas_de_socio_pj",
        "cnpj_situacao_cadastral",
        "controladas_pj",
        "anvisa_por_empresa",
        "receita_dirbi",
        "receita_ecf_renuncia",
        "sigsif_habilitados",
    ],
)
def test_a_que_so_a_api_externa_serve_nao_sai_na_consulta_aberta(cliente, nome):
    """Linhas 810, 841, 844 e 860 (Diretoria, 11 e 12/11/2026): as entradas de sócio PJ, a situação cadastral, a
    cópia reduzida das controladas e a contagem de registros da Anvisa vão ao VPS só para a API externa, atrás do
    portão e da prontidão; a consulta aberta dá o mesmo 404 e nem a lista as mostra."""
    assert {
        "entradas_de_socio_pj",
        "cnpj_situacao_cadastral",
        "controladas_pj",
        "anvisa_por_empresa",
        "receita_dirbi",
        "receita_ecf_renuncia",
        "sigsif_habilitados",
    } == SO_PELA_API_EXTERNA
    assert not pode_consultar(nome)
    assert cliente.get(f"{ROTA}/{nome}").json() == {
        "detail": base_tabelas.NAO_ENCONTRADA
    }
    assert cliente.get(f"{ROTA}/{nome}.csv").status_code == 404
    assert nome not in {t["tabela"] for t in cliente.get(ROTA).json()["tabelas"]}


def test_so_a_tabela_da_api_externa_muda_de_lado():
    """Nenhuma outra tabela entra nem sai da consulta aberta com a lista `SO_PELA_API_EXTERNA`."""

    def antes(nome: str) -> bool:
        return (
            pode_mostrar(nome)
            and servida_pela_porta(nome)
            and tem_dia_publico(nome)
            and nome not in ESPERAM_A_MARCA_DE_PESSOA
        )

    mudaram = {nome for nome in TABELAS if pode_consultar(nome) != antes(nome)}
    assert mudaram == SO_PELA_API_EXTERNA


def test_a_situacao_cadastral_saiu_da_espera_e_continua_fora_da_consulta_aberta(
    cliente,
):
    """Linha 841: montada só das raízes sem pessoa, deixou de esperar a marca, mas segue fora do lote."""
    assert "cnpj_situacao_cadastral" not in ESPERAM_A_MARCA_DE_PESSOA
    assert not pode_consultar("cnpj_situacao_cadastral")
    assert cliente.get(f"{ROTA}/cnpj_situacao_cadastral.csv").status_code == 404


class _PortaQueFalhaNosTipos(Porta):
    def tipos(self, tabela, versao=None):
        raise ValueError("erro que não é da base")


def test_erro_inesperado_antes_do_csv_fecha_a_porta_e_devolve_a_vaga(
    cliente, base, monkeypatch
):
    """Regressão: no CSV, só a recusa (HTTPException) fechava a porta; outro erro antes do fluxo a
    deixava aberta, com até 512MB, até o coletor de lixo passar."""
    abertas: list[Porta] = []

    def abrir() -> Porta:
        abertas.append(_PortaQueFalhaNosTipos(base))
        return abertas[-1]

    monkeypatch.setattr(base_tabelas, "abrir_porta", abrir)
    with pytest.raises(ValueError, match="não é da base"):
        cliente.get(f"{ROTA}/pgfn_divida.csv")
    with pytest.raises(Exception, match="closed"):
        abertas[0].con.execute("SELECT 1")
    vagas = base_tabelas._VAGAS
    assert all(
        vagas.acquire(blocking=False) for _ in range(base_tabelas.PORTAS_AO_MESMO_TEMPO)
    )
    for _ in range(base_tabelas.PORTAS_AO_MESMO_TEMPO):
        vagas.release()


def test_portas_ao_mesmo_tempo_tem_teto_e_a_vaga_volta(cliente, monkeypatch):
    """Regressão (negação de serviço): cada pedido abria uma porta de até 512MB, sem limite de
    pedidos ao mesmo tempo, no contêiner que serve o webhook. Sem vaga, 503 na hora (sem esperar);
    a vaga volta no fim do JSON e do CSV."""
    vagas = threading.BoundedSemaphore(1)
    monkeypatch.setattr(base_tabelas, "_VAGAS", vagas, raising=False)
    assert vagas.acquire(blocking=False)
    ocupada = cliente.get(f"{ROTA}/pgfn_divida", headers=SITE)
    assert ocupada.status_code == 503, ocupada.text
    assert ocupada.json()["detail"] == base_tabelas.OCUPADA
    assert ocupada.headers["access-control-allow-origin"] == "https://tickerlab.com.br"
    assert cliente.get(f"{ROTA}/pgfn_divida.csv").status_code == 503
    vagas.release()
    assert cliente.get(f"{ROTA}/pgfn_divida").status_code == 200
    assert cliente.get(f"{ROTA}/pgfn_divida.csv").status_code == 200
    assert vagas.acquire(blocking=False)  # as duas devolveram a vaga
    vagas.release()


def test_a_porta_da_api_abre_com_pouca_memoria_e_poucas_threads(monkeypatch):
    """O DuckDB vê os núcleos da máquina, não a cota do contêiner: sem `threads`, reserva memória
    para 16 e estoura os 512MB já na primeira página de tabela larga."""
    pedidos: list[dict] = []
    monkeypatch.setattr(
        base_tabelas.porta_da_base, "abrir", lambda **opcoes: pedidos.append(opcoes)
    )
    base_tabelas.abrir_porta()
    assert pedidos == [
        {
            "memoria": base_tabelas.MEMORIA_DA_PORTA,
            "threads": base_tabelas.THREADS_DA_PORTA,
        }
    ]


def test_csv_que_nunca_e_lido_fecha_a_porta_e_devolve_a_vaga(
    cliente, base, monkeypatch
):
    """Quem pede o CSV e desliga antes do primeiro pedaço: o servidor descarta o fluxo sem lê-lo. O
    fluxo já começou antes de responder, então descartá-lo fecha a porta e devolve a vaga (um
    gerador que nunca começou não roda o `finally`, e as vagas acabariam até reiniciar a API)."""
    abertas: list[Porta] = []

    def abrir() -> Porta:
        abertas.append(Porta(base))
        return abertas[-1]

    class _RespostaQueDescartaOFluxo(base_tabelas.StreamingResponse):
        def __init__(self, content, **opcoes):
            super().__init__(iter([b""]), **opcoes)

    monkeypatch.setattr(base_tabelas, "abrir_porta", abrir)
    monkeypatch.setattr(base_tabelas, "StreamingResponse", _RespostaQueDescartaOFluxo)
    vagas = threading.BoundedSemaphore(1)
    monkeypatch.setattr(base_tabelas, "_VAGAS", vagas, raising=False)
    assert cliente.get(f"{ROTA}/pgfn_divida.csv").status_code == 200
    gc.collect()
    with pytest.raises(Exception, match="closed"):
        abertas[0].con.execute("SELECT 1")
    assert vagas.acquire(blocking=False)
    vagas.release()


# --- as 15 da linha 842 -------------------------------------------------------------------------
# as 7 do lote 1 das 300 pelo CNPJ (linha 904): fechadas até o pode do envio ao VPS (linha 908)
LOTE_1_DA_904 = {
    "fip_informe", "fii_informe_mensal", "fii_ativos", "fii_administradores",
    "aneel_inadimplencia", "aneel_indicadores_comerciais", "ans_idss",
}  # fmt: skip


def test_as_15_da_linha_842_estao_no_dicionario():
    assert FECHADAS_ATE_A_PRONTIDAO >= LOTE_1_DA_904
    assert (
        len(FECHADAS_ATE_A_PRONTIDAO - LOTE_1_DA_904) == 19
    )  # 15 + 4 do INPI (linha 904, lote 2)
    assert set(TABELAS) >= FECHADAS_ATE_A_PRONTIDAO


def test_sem_prontidao_a_lista_nao_anuncia_as_15(sem_prontidao):
    nomes = {t["tabela"] for t in sem_prontidao.get(ROTA).json()["tabelas"]}
    assert nomes.isdisjoint(FECHADAS_ATE_A_PRONTIDAO)
    # as demais seguem como estavam
    assert {"pgfn_divida", "curva_juros"} <= nomes


@pytest.mark.parametrize("nome", sorted(_fechadas_consultaveis()))
def test_sem_prontidao_as_15_nao_servem_linhas_nem_csv(sem_prontidao, nome):
    inexistente = sem_prontidao.get(f"{ROTA}/nao_existe", headers=SITE)
    for rota in (f"{ROTA}/{nome}", f"{ROTA}/{nome}.csv"):
        r = sem_prontidao.get(rota, headers=SITE)
        assert r.status_code == 404 and r.json() == inexistente.json(), rota


def test_ma_datas_e_ma_regua_voltam_com_prontidao(cliente, monkeypatch):
    for nome in ("ma_datas", "ma_regua"):
        assert nome in FECHADAS_ATE_A_PRONTIDAO and pode_consultar(nome)
        monkeypatch.setattr(prontidao, "PRONTIDAO", {})
        assert not pode_consultar_aberto(nome)
        monkeypatch.setattr(prontidao, "PRONTIDAO", _prontidao_de_todas_do_cnpj())
        assert pode_consultar_aberto(nome)


def test_ficam_em_casa_que_a_consulta_libera_estao_fechadas():
    """Tabela nova de `FICAM_EM_CASA` que `pode_consultar` libera tem de vir para `FECHADAS_ATE_A_PRONTIDAO`
    (ou ser do CNPJ): senão a consulta aberta a anuncia sem prontidão (linha 842)."""
    from scripts.montar_recorte_da_api import FICAM_EM_CASA

    abertas = {
        n
        for n in FICAM_EM_CASA
        if n in TABELAS and pode_consultar_aberto(n) and not e_do_cnpj(n)
    }
    assert not abertas, sorted(abertas)
