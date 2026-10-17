"""Régua do middle market dos negócios de M&A: receita anual da alvo entre R$ 30 e 500 milhões no
último ano antes do negócio (base/ma_regua.py; ADR 0082, série 5 do plano de M&A, passo 5).

Tudo aqui é inventado: empresas, raízes de CNPJ, receitas e arquivos da Receita.
"""

import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base import ma_datas as datas
from base import ma_regua as regua
from base.dicionario import TABELAS
from base.parquet import conferir_tabela, gravar_tabela, ler_tabela
from scripts import carga_ma_assessorias as carga
from tests.test_base_ma_ligacao import (
    RAIZ_ALFA,
    RAIZ_BETA,
    RAIZ_DELTA,
    RECEITA,
    _zip,
    ambiente,  # noqa: F401 (fixture)
)

CONHECIDO = datetime(2025, 11, 18, 10, tzinfo=UTC)
CNPJ_DA_ALFA = "11.111.111/0001-91"


def _datas(**campos) -> pd.DataFrame:
    linha = {
        "assessoria": "igc",
        "url": "u1",
        "id_negocio": "N1",
        "conhecido_em_do_negocio": CONHECIDO,
        "fechamento_em": None,
    }
    linha.update(campos)
    return pd.DataFrame([linha])


def _partes(*alvos: str | None, url: str = "u1") -> pd.DataFrame:
    linhas = [
        {"assessoria": "igc", "url": url, "papel": "alvo", "cnpj_raiz": raiz}
        for raiz in alvos
    ]
    linhas.append(
        {"assessoria": "igc", "url": url, "papel": "comprador", "cnpj_raiz": RAIZ_DELTA}
    )
    return pd.DataFrame(linhas)


def _receita(
    receita: float,
    exercicio_fim: date = date(2024, 12, 31),
    publico_em: date = date(2025, 3, 28),
    fonte: str = regua.DFP,
    raiz: str = RAIZ_ALFA,
) -> dict:
    return {
        "cnpj_raiz": raiz,
        "exercicio_fim": exercicio_fim,
        "receita": receita,
        "fonte": fonte,
        "documento": f"DFP {exercicio_fim} v1",
        "documento_sha256": None,
        "publico_em": publico_em,
    }


def _receitas(*linhas: dict) -> pd.DataFrame:
    return pd.DataFrame(list(linhas), columns=list(regua.COLUNAS_DAS_RECEITAS))


def _portes(*linhas: tuple[str, str, datetime]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cnpj_raiz": raiz,
                "porte": porte,
                "porte_publico_em": quando,
                "porte_prova_url": RECEITA + "Empresas0.zip",
                "porte_prova_sha256": "e" * 64,
            }
            for raiz, porte, quando in linhas
        ],
        columns=list(regua.COLUNAS_DOS_PORTES),
    )


SEM_PORTE = _portes()


def _medir(receitas: pd.DataFrame, portes: pd.DataFrame = SEM_PORTE, **campos):
    return regua.medir(_datas(**campos), _partes(RAIZ_ALFA), receitas, portes).iloc[0]


# --- a régua ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "receita, esperado",
    [
        (29_999_999.99, "nao"),
        (30_000_000.0, "sim"),
        (120_000_000.0, "sim"),
        (500_000_000.0, "sim"),
        (500_000_000.01, "nao"),
    ],
)
def test_regua_nos_limites_de_30_e_500_milhoes(receita, esperado):
    linha = _medir(_receitas(_receita(receita)))
    assert linha["middle_market"] == esperado
    assert linha["receita"] == receita
    assert linha["receita_fonte"] == regua.DFP
    assert linha["motivo"] == regua.PELA_RECEITA


def test_receita_de_documento_entregue_depois_do_negocio_nunca_entra():
    """Sem olhar o futuro: a DFP entregue depois do `conhecido_em` não existe para a régua."""
    depois = _receita(80_000_000.0, publico_em=date(2025, 11, 19))
    linha = _medir(_receitas(depois))
    assert linha["middle_market"] == regua.DESCONHECIDO
    assert pd.isna(linha["receita"])
    assert linha["motivo"] == regua.SEM_RECEITA


def test_documento_entregue_no_mesmo_dia_tambem_nao_entra():
    """A CVM não diz a hora da entrega: no mesmo dia do `conhecido_em`, não se sabe qual veio antes."""
    linha = _medir(_receitas(_receita(80_000_000.0, publico_em=date(2025, 11, 18))))
    assert linha["middle_market"] == regua.DESCONHECIDO


def test_cortar_o_futuro_nao_muda_a_regua():
    antes = _receita(
        80_000_000.0, exercicio_fim=date(2023, 12, 31), publico_em=date(2024, 3, 1)
    )
    depois = _receita(900_000_000.0, publico_em=date(2026, 3, 1))
    so_o_passado = _medir(_receitas(antes))
    com_o_futuro = _medir(_receitas(antes, depois))
    assert so_o_passado.equals(com_o_futuro)
    assert com_o_futuro["middle_market"] == regua.SIM


def test_vale_o_ultimo_exercicio_antes_do_negocio():
    linha = _medir(
        _receitas(
            _receita(
                20_000_000.0,
                exercicio_fim=date(2023, 12, 31),
                publico_em=date(2024, 3, 1),
            ),
            _receita(
                40_000_000.0,
                exercicio_fim=date(2024, 12, 31),
                publico_em=date(2025, 3, 1),
            ),
        )
    )
    assert linha["receita"] == 40_000_000.0
    assert linha["receita_exercicio_fim"] == date(2024, 12, 31)


def test_com_a_data_do_fechamento_vale_o_exercicio_antes_dele():
    """Fechado em 2024: a receita de 2024 (entregue em 2025, antes do `conhecido_em`) já é de depois."""
    linha = _medir(
        _receitas(
            _receita(
                20_000_000.0,
                exercicio_fim=date(2023, 12, 31),
                publico_em=date(2024, 3, 1),
            ),
            _receita(
                40_000_000.0,
                exercicio_fim=date(2024, 12, 31),
                publico_em=date(2025, 3, 1),
            ),
        ),
        fechamento_em=date(2024, 6, 3),
    )
    assert linha["receita"] == 20_000_000.0
    assert linha["middle_market"] == regua.NAO


def test_reapresentacao_entregue_antes_vale_a_mais_nova():
    linha = _medir(
        _receitas(
            _receita(25_000_000.0, publico_em=date(2025, 3, 1)),
            _receita(35_000_000.0, publico_em=date(2025, 6, 1)),  # versão 2, refeita
        )
    )
    assert linha["receita"] == 35_000_000.0
    assert linha["receita_publico_em"] == date(2025, 6, 1)


def test_no_mesmo_exercicio_a_ordem_das_fontes_decide():
    linha = _medir(
        _receitas(
            _receita(25_000_000.0, fonte=regua.CADE),
            _receita(35_000_000.0, fonte=regua.CPC15),
        )
    )
    assert linha["receita_fonte"] == regua.CPC15


def test_porte_me_ou_epp_vira_nao():
    for porte in ("01", "03"):
        linha = _medir(
            _receitas(), _portes((RAIZ_ALFA, porte, datetime(2025, 10, 14, tzinfo=UTC)))
        )
        assert linha["middle_market"] == regua.NAO
        assert linha["motivo"] == regua.PELO_PORTE
        assert pd.isna(linha["receita"])  # o valor da régua nunca é estimado
        assert linha["porte"] == porte


def test_porte_demais_nao_decide():
    linha = _medir(
        _receitas(), _portes((RAIZ_ALFA, "05", datetime(2025, 10, 14, tzinfo=UTC)))
    )
    assert linha["middle_market"] == regua.DESCONHECIDO
    assert linha["porte"] == "05"


def test_porte_de_arquivo_baixado_depois_do_negocio_nao_vale():
    linha = _medir(
        _receitas(), _portes((RAIZ_ALFA, "01", datetime(2026, 10, 14, tzinfo=UTC)))
    )
    assert linha["middle_market"] == regua.DESCONHECIDO
    assert pd.isna(linha["porte"])


def test_receita_conhecida_vem_antes_do_porte():
    linha = _medir(
        _receitas(_receita(60_000_000.0)),
        _portes((RAIZ_ALFA, "03", datetime(2025, 10, 14, tzinfo=UTC))),
    )
    assert linha["middle_market"] == regua.SIM


def test_sem_fonte_vira_desconhecido():
    linha = _medir(_receitas())
    assert linha["middle_market"] == regua.DESCONHECIDO
    assert linha["motivo"] == regua.SEM_RECEITA


def test_alvo_sem_cnpj_ou_mais_de_uma_alvo_fica_desconhecido():
    receitas = _receitas(_receita(60_000_000.0), _receita(70_000_000.0, raiz=RAIZ_BETA))
    sem = regua.medir(_datas(), _partes(None), receitas, SEM_PORTE).iloc[0]
    assert (sem["middle_market"], sem["motivo"]) == (
        regua.DESCONHECIDO,
        regua.ALVO_SEM_CNPJ,
    )
    duas = regua.medir(
        _datas(), _partes(RAIZ_ALFA, RAIZ_BETA), receitas, SEM_PORTE
    ).iloc[0]
    assert (duas["middle_market"], duas["motivo"]) == (
        regua.DESCONHECIDO,
        regua.VARIAS_ALVOS,
    )


def test_pagina_sem_alvo_nenhuma_tambem_sai():
    partes = pd.DataFrame(columns=["assessoria", "url", "papel", "cnpj_raiz"])
    saida = regua.medir(_datas(), partes, _receitas(), SEM_PORTE)
    assert list(saida["motivo"]) == [regua.ALVO_SEM_CNPJ]


# --- as fontes ---------------------------------------------------------------------------------------
def _demonstracoes(*linhas: tuple) -> pd.DataFrame:
    colunas = ["cnpj", "grupo", "demonstracao", "conta", "descricao", "inicio", "fim", "valor",
               "documento", "referencia", "versao", "ordem", "divulgado_em"]  # fmt: skip
    return pd.DataFrame(list(linhas), columns=colunas)


def test_receita_da_cvm_e_a_anual_da_dre_com_o_consolidado_antes():
    receitas = regua.receitas_da_cvm(
        _demonstracoes(
            (CNPJ_DA_ALFA, "con", "DRE", "3.01", "Receita de Venda de Bens e/ou Serviços",
             "2024-01-01", "2024-12-31", 90e6, "DFP", "2024-12-31", 1, "ultimo", "2025-03-28"),
            (CNPJ_DA_ALFA, "ind", "DRE", "3.01", "Receita de Venda de Bens e/ou Serviços",
             "2024-01-01", "2024-12-31", 70e6, "DFP", "2024-12-31", 1, "ultimo", "2025-03-28"),
            (CNPJ_DA_ALFA, "con", "DRE", "3.01", "Receita de Venda de Bens e/ou Serviços",
             "2024-07-01", "2024-09-30", 20e6, "ITR", "2024-09-30", 1, "ultimo", "2024-11-10"),
        ),
        {RAIZ_ALFA},
    )  # fmt: skip
    assert len(receitas) == 1  # o trimestre do ITR não é um ano
    linha = receitas.iloc[0]
    assert linha["cnpj_raiz"] == RAIZ_ALFA
    assert linha["receita"] == 90e6
    assert linha["fonte"] == regua.DFP
    assert linha["exercicio_fim"] == date(2024, 12, 31)
    assert linha["publico_em"] == date(2025, 3, 28)


def test_receita_da_cvm_so_das_raizes_pedidas():
    receitas = regua.receitas_da_cvm(
        _demonstracoes(
            (CNPJ_DA_ALFA, "con", "DRE", "3.01", "Receita de Venda", "2024-01-01",
             "2024-12-31", 90e6, "DFP", "2024-12-31", 1, "ultimo", "2025-03-28"),
        ),
        {RAIZ_BETA},
    )  # fmt: skip
    assert receitas.empty


def test_portes_saem_do_cnpj_com_a_prova():
    arquivo = _zip(
        [
            [RAIZ_ALFA, "ALFA OLEOS S.A.", "2054", "10", "1000,00", "03", ""],
            [RAIZ_BETA, "BETA LTDA", "2062", "49", "10,00", "05", ""],
        ]
    )
    guardado = datas.Guardado(RECEITA + "Empresas0.zip", "e" * 64, CONHECIDO)
    portes = regua.portes_do_cnpj([(arquivo, guardado)], {RAIZ_ALFA})
    assert list(portes.columns) == list(regua.COLUNAS_DOS_PORTES)
    assert portes.to_dict("records") == [
        {
            "cnpj_raiz": RAIZ_ALFA,
            "porte": "03",
            "porte_publico_em": CONHECIDO,
            "porte_prova_url": RECEITA + "Empresas0.zip",
            "porte_prova_sha256": "e" * 64,
        }
    ]


def test_receitas_conferidas_exigem_a_data_do_documento(tmp_path):
    arquivo = tmp_path / "ma_receitas.csv"
    arquivo.write_text(
        "cnpj_raiz;exercicio_fim;receita;fonte;documento;publico_em;conferido_em;observacao\n"
        f"{RAIZ_ALFA};2024-12-31;45000000;cpc15-compradora;https://exemplo/dfp;;2026-10-16;\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="publico_em"):
        regua.receitas_conferidas(arquivo)


def test_receitas_conferidas_recusam_fonte_desconhecida(tmp_path):
    arquivo = tmp_path / "ma_receitas.csv"
    arquivo.write_text(
        "cnpj_raiz;exercicio_fim;receita;fonte;documento;publico_em;conferido_em;observacao\n"
        f"{RAIZ_ALFA};2024-12-31;45000000;noticia;https://exemplo;2025-01-01;2026-10-16;\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fonte"):
        regua.receitas_conferidas(arquivo)


def test_tabela_conferida_do_repositorio_le_sem_erro():
    receitas = regua.receitas_conferidas()
    assert list(receitas.columns) == list(regua.COLUNAS_DAS_RECEITAS)


# --- contrato e resumo -------------------------------------------------------------------------------
def test_tabela_tem_as_colunas_do_dicionario():
    assert set(TABELAS["ma_regua"].colunas) == set(regua.COLUNAS)


def test_resumo_conta_cada_resposta_e_de_onde_veio():
    saida = pd.DataFrame(
        {
            "middle_market": ["sim", "nao", "nao", "desconhecido", "desconhecido"],
            "motivo": [
                regua.PELA_RECEITA,
                regua.PELA_RECEITA,
                regua.PELO_PORTE,
                regua.ALVO_SEM_CNPJ,
                regua.SEM_RECEITA,
            ],
            "receita_fonte": [regua.DFP, regua.CPC15, None, None, None],
        }
    )
    assert regua.resumo(saida) == (
        "5 páginas; middle_market sim 1, nao 2, desconhecido 2; receita pela dfp-alvo 1, "
        "pela cpc15-compradora 1; porte ME/EPP 1; desconhecido: alvo sem CNPJ 1, "
        "sem receita antes do negócio 1, mais de uma alvo 0"
    )


# --- carga -------------------------------------------------------------------------------------------
def test_carga_grava_a_regua_com_manifesto(ambiente, capsys):  # noqa: F811
    gravar_tabela(
        _demonstracoes(
            (CNPJ_DA_ALFA, "con", "DRE", "3.01", "Receita de Venda", "2024-01-01",
             "2024-12-31", 90e6, "DFP", "2024-12-31", 1, "ultimo", "2025-03-28"),
        ).assign(
            inicio=lambda t: pd.to_datetime(t["inicio"]).dt.date,
            fim=lambda t: pd.to_datetime(t["fim"]).dt.date,
            referencia=lambda t: pd.to_datetime(t["referencia"]).dt.date,
            divulgado_em=lambda t: pd.to_datetime(t["divulgado_em"]).dt.date,
        ),
        ambiente / "demonstracoes" / "2024",
        [{"url": "teste", "sha256": "0" * 64}],
        ["cnpj"],
    )  # fmt: skip
    assert carga.main(["--base", str(ambiente)]) == 0
    arquivo = ambiente / "ma" / "regua" / "negocios.parquet"
    assert conferir_tabela(arquivo)
    manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    urls = {o["url"] for o in manifesto["origens"]}
    assert "ma/datas/negocios.parquet" in urls
    assert "demonstracoes/2024.parquet" in urls
    assert RECEITA + "Empresas0.zip" in urls
    saida = ler_tabela(arquivo).set_index("url")
    alfa = "https://www.igcp.com.br/transactions/a-alfa-oleos-foi-adquirida-pela-delta"
    # sem cópia no Wayback, o `conhecido_em` é a coleta (2026): a DFP de 2024 já era pública
    assert saida.loc[alfa, "middle_market"] == "sim"
    assert saida.loc[alfa, "receita_fonte"] == "dfp-alvo"
    assert "middle_market sim 1" in capsys.readouterr().out
