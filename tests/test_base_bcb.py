"""IF.data dos bancos e SCR.data do crédito por setor (série 3 da base de ML, PR 7). Sem internet.

Amostras reais recortadas (`tests/arquivos/bcb/`), do inventário de 14/10/2026:
- IF.data (API Olinda): o resumo de jun/2025 dos conglomerados prudenciais de Itaú, BB, Bradesco,
  Santander, BTG e Caixa; o ativo de dez/2000 do conglomerado financeiro Bradesco, com 3 das 34 linhas
  de total sem código de instituição; o cadastro dessas datas. Saldos em reais.
- SCR.data versão 2 (`scrdata_<ano>.zip`): 240 linhas de nov e dez/2012 e de ago/2026, metade PF e
  metade PJ, com a BOM, as aspas e os CNAEs com ";" no nome, como vêm do BC.
"""

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from base import bcb_ifdata, bcb_scr

PASTA = Path(__file__).parent / "arquivos" / "bcb"
ITAU, BB, BRADESCO, SANTANDER, BTG, CAIXA = (
    "C0080099",
    "C0080329",
    "C0080075",
    "C0080185",
    "C0080336",
    "C0080738",
)


def _ifdata(nome: str) -> bytes:
    return (PASTA / "ifdata" / nome).read_bytes()


def _scr(nome: str) -> bytes:
    return (PASTA / "scr" / nome).read_bytes()


# ---------------------------------------------------------------------------- IF.data


def test_ifdata_le_balanco_e_carteira_por_instituicao():
    valores = bcb_ifdata.ler_valores(_ifdata("valores_202506_t1_r1.json"))
    assert len(valores) == 60  # 6 conglomerados x 10 linhas do resumo
    assert set(valores.columns) >= {
        "data_base",
        "tipo_instituicao",
        "cod_inst",
        "relatorio",
        "conta",
        "coluna",
        "saldo",
    }
    assert (valores["data_base"] == pd.Timestamp("2025-06-30")).all()
    ativo = valores[
        (valores["cod_inst"] == ITAU) & (valores["coluna"] == "Ativo Total")
    ]
    assert ativo["saldo"].iloc[0] == pytest.approx(2_565_430_000_000, rel=1e-3)
    # o BC quebra a linha antes da letra da nota ("... RWA \n(e)"): vira um espaço só
    assert not valores["coluna"].str.contains("\n").any()
    assert "Patrimônio de Referência para Comparação com o RWA (e)" in set(
        valores["coluna"]
    )


def test_ifdata_linhas_de_total_sem_instituicao_ficam_fora():
    bruto = json.loads(_ifdata("valores_200012_t2_r2.json"))["value"]
    valores = bcb_ifdata.ler_valores(_ifdata("valores_200012_t2_r2.json"))
    assert len(valores) == len(bruto) - 3
    assert valores["cod_inst"].notna().all()
    assert (valores["data_base"] == pd.Timestamp("2000-12-31")).all()


def test_ifdata_resposta_vazia_vira_tabela_vazia():
    vazio = json.dumps({"@odata.context": "x", "value": []}).encode()
    assert bcb_ifdata.ler_valores(vazio).empty


def test_ifdata_datas_base_e_tipos_de_instituicao():
    datas = bcb_ifdata.datas_base(2000, 2001)
    assert datas == [200003, 200006, 200009, 200012, 200103, 200106, 200109, 200112]
    # o conglomerado prudencial só existe desde mar/2014
    assert bcb_ifdata.tipos_da_data(201312) == (2, 3)
    assert bcb_ifdata.tipos_da_data(201403) == (1, 2, 3)
    assert 15 not in bcb_ifdata.RELATORIOS  # câmbio fica fora


def test_ifdata_so_entra_como_era_na_data_depois_da_publicacao():
    valores = bcb_ifdata.ler_valores(_ifdata("valores_202506_t1_r1.json"))
    disponivel = bcb_ifdata.disponivel_em(valores)
    assert (disponivel == pd.Timestamp("2025-06-30") + pd.Timedelta(days=120)).all()


def _empresas_e_tickers() -> tuple[pd.DataFrame, pd.DataFrame]:
    empresas = pd.DataFrame(
        {
            "emissor": ["ITUB", "BBAS", "BBDC", "SANB", "BPAC"],
            "cnpj": [
                "60.872.504/0001-23",
                "00.000.000/0001-91",
                "60.746.948/0001-12",
                "90.400.888/0001-42",
                "30.306.294/0001-45",
            ],
            "conflito": [False] * 5,
        }
    )
    data = pd.Timestamp
    # como a `tickers_no_tempo`: da entrega do FCA que trouxe o código até a do que veio sem ele
    tickers = pd.DataFrame(
        {
            "codigo": [
                "ITUB4",
                "ITUB3",
                "BBAS3",
                "BBDC4",
                "SANB11",
                "BPAC11",
                "BBTG11",
            ],
            "cnpj": [
                "60.872.504/0001-23",
                "60.872.504/0001-23",
                "00.000.000/0001-91",
                "60.746.948/0001-12",
                "90.400.888/0001-42",
                "30.306.294/0001-45",
                "30.306.294/0001-45",
            ],
            "primeiro_visto": [data("2010-05-31")] * 6 + [data("2012-05-31")],
            "ultimo_visto": [data("2026-05-31")] * 6 + [data("2017-05-31")],
            "valido_ate": [pd.NaT] * 6 + [data("2018-05-31")],  # BBTG11 saiu
        }
    )
    return empresas, tickers


def test_banco_da_bolsa_liga_ao_cnpj_e_a_acao():
    cadastro = bcb_ifdata.ler_cadastro(_ifdata("cadastro_202506.json"))
    empresas, tickers = _empresas_e_tickers()
    ligacao = bcb_ifdata.ligacao_dos_bancos(cadastro, empresas, tickers).set_index(
        "cod_inst"
    )
    esperado = {
        ITAU: ("60.872.504/0001-23", "ITUB3,ITUB4"),
        BB: ("00.000.000/0001-91", "BBAS3"),
        BRADESCO: ("60.746.948/0001-12", "BBDC4"),
        SANTANDER: ("90.400.888/0001-42", "SANB11"),
        BTG: ("30.306.294/0001-45", "BPAC11"),  # o BBTG11 não valia mais em 2025
    }
    for codigo, (cnpj, codigos) in esperado.items():
        assert ligacao.loc[codigo, "cnpj"] == cnpj, codigo
        assert ligacao.loc[codigo, "tickers"] == codigos, codigo
    # a Caixa não tem ação; o Bradesco Cartões não tem líder, e o próprio CodInst é a raiz do CNPJ
    assert pd.isna(ligacao.loc[CAIXA, "cnpj"])
    assert ligacao.loc["59438325", "cnpj_raiz"] == "59438325"
    assert (ligacao["data_base"] == pd.Timestamp("2025-06-30")).all()


def test_instituicao_listada_liga_pelo_proprio_cnpj_e_nao_pelo_do_lider():
    """Série 3, PR 8: o Banco PAN está no conglomerado do BTG (o líder é o BTG), mas tem ação própria
    (BPAN4): a instituição individual liga pelo próprio CNPJ; o resto do conglomerado, pelo líder."""
    cadastro = pd.DataFrame(
        {
            "data_base": [pd.Timestamp("2025-06-30")] * 3,
            "cod_inst": ["59285411", "30306294", BTG],
            "instituicao": [
                "BANCO PAN S.A.",
                "BANCO BTG PACTUAL S.A.",
                "BTG PACTUAL - PRUDENCIAL",
            ],
            "cnpj_raiz": ["30306294"] * 3,  # o IF.data dá o CNPJ do líder a todos
        }
    )
    empresas, tickers = _empresas_e_tickers()
    pan = "59.285.411/0001-13"
    empresas = pd.concat(
        [
            empresas,
            pd.DataFrame({"emissor": ["BPAN"], "cnpj": [pan], "conflito": [False]}),
        ],
        ignore_index=True,
    )
    tickers = pd.concat(
        [
            tickers,
            pd.DataFrame(
                {
                    "codigo": ["BPAN4"],
                    "cnpj": [pan],
                    "primeiro_visto": [pd.Timestamp("2019-05-31")],
                    "ultimo_visto": [pd.Timestamp("2026-05-31")],
                    "valido_ate": [pd.NaT],
                }
            ),
        ],
        ignore_index=True,
    )
    ligacao = bcb_ifdata.ligacao_dos_bancos(cadastro, empresas, tickers).set_index(
        "cod_inst"
    )
    assert ligacao.loc["59285411", ["cnpj", "tickers", "ligado_por"]].tolist() == [
        pan,
        "BPAN4",
        bcb_ifdata.PELO_PROPRIO_CNPJ,
    ]
    assert ligacao.loc["30306294", "ligado_por"] == bcb_ifdata.PELO_PROPRIO_CNPJ
    assert ligacao.loc[BTG, ["cnpj", "tickers", "ligado_por"]].tolist() == [
        "30.306.294/0001-45",
        "BPAC11",
        bcb_ifdata.PELO_LIDER,
    ]


def test_ligacao_antes_do_fca_chega_ao_cnpj_mas_nao_a_acao():
    cadastro = bcb_ifdata.ler_cadastro(_ifdata("cadastro_200012.json"))
    empresas, tickers = _empresas_e_tickers()
    ligacao = bcb_ifdata.ligacao_dos_bancos(cadastro, empresas, tickers).set_index(
        "cod_inst"
    )
    assert ligacao.loc["C0010045", "cnpj"] == "60.746.948/0001-12"
    assert pd.isna(ligacao.loc["C0010045", "tickers"])  # o FCA começa em 2010


def test_ticker_so_entra_na_data_base_depois_da_entrega_do_fca():
    """Série 4, PR 1: o ticker vale da entrega do FCA, não do ano dele. Com o FCA que trouxe o
    BPAC11 entregue em 15/07/2025, o cadastro de 30/06/2025 ainda não tem o código; o de 30/09, sim."""
    cadastro = pd.DataFrame(
        {
            "data_base": [pd.Timestamp("2025-06-30"), pd.Timestamp("2025-09-30")],
            "cod_inst": [BTG, BTG],
            "instituicao": ["BTG PACTUAL - PRUDENCIAL"] * 2,
            "cnpj_raiz": ["30306294"] * 2,
        }
    )
    empresas, tickers = _empresas_e_tickers()
    tickers.loc[tickers["codigo"] == "BPAC11", "primeiro_visto"] = pd.Timestamp(
        "2025-07-15"
    )
    ligacao = bcb_ifdata.ligacao_dos_bancos(cadastro, empresas, tickers)
    assert pd.isna(ligacao["tickers"].iloc[0])
    assert ligacao["tickers"].iloc[1] == "BPAC11"


# ---------------------------------------------------------------------------- SCR.data


def _somar_texto(conteudo_do_zip: bytes, coluna: str) -> float:
    total = 0.0
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        for nome in arquivo.namelist():
            bruto = pd.read_csv(
                arquivo.open(nome), sep=";", dtype=str, encoding="utf-8-sig"
            )
            total += bruto[coluna].str.replace(",", ".").astype(float).sum()
    return total


@pytest.mark.parametrize("nome", ["scrdata_2012.zip", "scrdata_2026.zip"])
def test_scr_le_carteira_e_atraso_por_cnae_e_porte(nome):
    scr = bcb_scr.ler_ano(_scr(nome))
    assert list(scr.columns[: len(bcb_scr.COLUNAS_DE_TEXTO)]) == list(
        bcb_scr.COLUNAS_DE_TEXTO
    )
    assert scr["cliente"].isin(["PF", "PJ"]).all()
    for coluna in ("carteira_ativa", "carteira_vencida", "carteira_inadimplencia"):
        assert scr[coluna].dtype == "float64"
        assert scr[coluna].sum() == pytest.approx(_somar_texto(_scr(nome), coluna))
    # acentos certos (o arquivo é UTF-8 com BOM)
    assert "Médio" in set(scr["porte"]) or "Mais de 5 a 10 salários mínimos" in set(
        scr["porte"]
    )
    # o CNAE com ";" dentro das aspas continua inteiro
    pj = scr[scr["cliente"] == "PJ"]["cnae_ocupacao"]
    assert pj.str.contains("; ", regex=False).any()
    # -1 é o jeito do BC dizer "sem número de operações"
    assert (scr["numero_de_operacoes"].dropna() >= 0).all()
    assert scr["numero_de_operacoes"].isna().any()


def test_scr_meses_do_arquivo_e_publicacao():
    scr = bcb_scr.ler_ano(_scr("scrdata_2012.zip"))
    assert sorted(scr["data_base"].unique()) == [
        pd.Timestamp("2012-11-30"),
        pd.Timestamp("2012-12-31"),
    ]
    disponivel = bcb_scr.disponivel_em(scr)
    assert (disponivel == scr["data_base"] + pd.Timedelta(days=60)).all()
    assert (
        bcb_scr.endereco_do_ano(2026)
        == "https://www.bcb.gov.br/pda/desig/scrdata_2026.zip"
    )
    assert bcb_scr.PRIMEIRO_ANO == 2012
