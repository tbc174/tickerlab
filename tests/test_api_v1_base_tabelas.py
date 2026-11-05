"""Consulta e exportação de cada tabela da base pela API aberta (virada de 5/11/2026, fase 1, PR 3).

A porta é uma base de mentira em `tmp_path/base`, com Parquets de tabelas reais do dicionário: a
`pgfn_divida` (com `cnpj`, uma linha de pessoa e uma coluna de pessoa que não existe no contrato), a
`cnpj_empresas_historico` (só `cnpj_basico`), a `curva_juros` (sem CNPJ) e a `sancoes_cgu` (tabela de
pessoa). A `insolvencia` é consultável, mas não tem arquivo nesta base.
"""

import re
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from base.dicionario import TABELAS
from base.dossie import COLUNAS_DE_PESSOA, pode_consultar
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


@pytest.fixture
def cliente(base, monkeypatch):
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
    assert corpo["como_era_em"] is None
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
    assert r.content.startswith("﻿".encode())
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


def test_csv_sai_pagina_a_pagina_ate_o_teto(cliente, monkeypatch):
    """Páginas de uma linha: o CSV junta todas até o fim; com o teto em duas, para nelas e avisa."""
    monkeypatch.setattr(base_tabelas, "LINHAS_POR_PAGINA_DO_CSV", 1)
    tudo = cliente.get(f"{ROTA}/pgfn_divida.csv")
    monkeypatch.setattr(base_tabelas, "TETO_DO_CSV", 2)
    cortado = cliente.get(f"{ROTA}/pgfn_divida.csv")
    assert len(tudo.content.decode("utf-8-sig").splitlines()) == 1 + 3
    assert len(cortado.content.decode("utf-8-sig").splitlines()) == 1 + 2
    assert cortado.headers[base_tabelas.CABECALHO_DO_TETO] == "2"


def test_csv_vazio_tem_so_o_cabecalho(cliente):
    r = cliente.get(f"{ROTA}/pgfn_divida.csv", params={"como_era_em": "2024-12-31"})
    assert r.status_code == 200
    assert r.content.decode("utf-8-sig").splitlines() == [
        ",".join(cliente.get(f"{ROTA}/pgfn_divida").json()["colunas"])
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
