"""Carga das fontes setoriais (série 4, PR 4): lê os originais que o arquivista guardou (não baixa nada)
e grava um Parquet por fonte e ano, com manifesto, versões e linhagem, mais os buracos da ligação pela
B13. Sem internet: as amostras de `tests/arquivos/setoriais/` entram no acervo como coletas."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base.arquivo.fontes import SES_DA_SUSEP
from base.commodities import cftc_cot
from base.parquet import conferir_tabela, gravar_tabela
from base.setoriais import (
    anac,
    anatel,
    aneel,
    anp,
    anp_concessionarios,
    ans,
    antt_siade,
    ccee,
    comex_preco_medio,
    ons,
    ons_capacidade,
    ons_restricao,
    susep,
)
from scripts import carga_setoriais
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para

AMOSTRAS = Path(__file__).parent / "arquivos" / "setoriais"
VERSAO = "4d2b0c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7c"
ENDERECOS = {
    anac.FONTE: [("https://sistemas.anac.gov.br/dadosabertos/Dados_Estatisticos.csv", "anac/Dados_Estatisticos.csv")],
    anp.FONTE: [("https://www.gov.br/anp/arquivos/vendas-derivados/liquidos.zip", "anp/liquidos.zip")],
    ons.FONTE: [
        ("https://ons-aws-prod-opendata.s3.amazonaws.com/geracao_usina_2_ho/GERACAO_USINA-2_2010.parquet", "ons/GERACAO_USINA-2_2010.parquet"),
        ("https://ons-aws-prod-opendata.s3.amazonaws.com/geracao_usina_2_ho/GERACAO_USINA-2_2026_09.parquet", "ons/GERACAO_USINA-2_2026_09.parquet"),
    ],
    aneel.FONTE: [
        (f"https://dadosabertos.aneel.gov.br/dataset/x/resource/{ano}/download/samp-{ano}.parquet", f"aneel/samp-{ano}.parquet")
        for ano in (2010, 2024)
    ],
    anatel.FONTE: [
        (f"https://www.anatel.gov.br/dadosabertos/paineis_de_dados/acessos/{zip_}.zip#{nome}", f"anatel/{nome}")
        for zip_, nome in [
            ("acessos_banda_larga_fixa", "Acessos_Banda_Larga_Fixa_2024_Colunas.csv"),
            ("acessos_telefonia_movel", "Acessos_Telefonia_Movel_200902-2018_Modalidade_Colunas.csv"),
            ("acessos_telefonia_movel", "Acessos_Telefonia_Movel_200902-2018_Tecnologia_Colunas.csv"),
        ]
    ],
    cftc_cot.FONTE: [(cftc_cot.ENDERECO_DO_ANO.format(ano=2026), "cftc/fut_disagg_txt_2026.zip")],
    ans.FONTE: [(ans.URL, "ans/Beneficiarios_operadora_e_carteira.csv")],
    susep.FONTE: [(f"{SES_DA_SUSEP}#{susep.ARQUIVO}", "susep/Ses_seguros.csv")],
    ccee.FONTE: [
        (f"https://dadosabertos.ccee.org.br/dataset/x/resource/{nome}/download/{nome}.csv", f"ccee/{nome}.csv")
        for nome in ("hora_2021", "dia_2025", "mes_2001", "hora_2001_2020")
    ],
    ons_restricao.FONTE: [
        ("https://ons-aws-prod-opendata.s3.amazonaws.com/restricao_coff_eolica_usi/RESTRICAO_COFF_EOLICA_2026_09.parquet",
         "ons_energia/RESTRICAO_COFF_EOLICA_2026_09.parquet"),
        ("https://ons-aws-prod-opendata.s3.amazonaws.com/restricao_coff_fotovoltaica/RESTRICAO_COFF_FOTOVOLTAICA_2024_04.parquet",
         "ons_energia/RESTRICAO_COFF_FOTOVOLTAICA_2024_04.parquet"),
    ],
    ons_capacidade.FONTE: [
        ("https://ons-aws-prod-opendata.s3.amazonaws.com/capacidade_geracao/CAPACIDADE_GERACAO.parquet",
         "ons_energia/CAPACIDADE_GERACAO.parquet"),
    ],
    anp_concessionarios.FONTE: [
        ("https://www.gov.br/anp/arquivos/rc/relacao-concessionarios.csv", "anp/concessionarios.csv"),
    ],
    antt_siade.FONTE: [
        (f"https://x.gov.br/siade/producao_origem_destino_{ano}.csv", f"antt/producao_{ano}.csv")
        for ano in (2006, 2026)
    ],
    comex_preco_medio.FONTE: [
        ("https://x.gov.br/comexstat-bd/ncm/EXP_2026.csv", "comex/EXP_2026.csv"),
        ("https://x.gov.br/comexstat-bd/ncm/IMP_2026.csv", "comex/IMP_2026.csv"),
        ("https://x.gov.br/comexstat-bd/tabelas/URF.csv", "comex/URF.csv"),  # fica fora: não é de NCM
    ],
}  # fmt: skip
CNPJS_SEM_B13 = {
    "00271847000100", "02270689000108", "02873528000109", "03342704000130", "04054366000102",
    "05002889000160", "08270816000147", "08839018000193", "08926302000105", "09309027000135",
    "11210501000119", "12091809000155", "12432261000160", "15240822000117", "15596829000176",
    "16974249000138", "17186461000101", "19285411000107", "23018639000108", "25315943000134",
    "32528443000146", "33400769000156", "55372111000110",
}  # fmt: skip
ANATEL = {"Acessos_Banda_Larga_Fixa_2024_Colunas", "Acessos_Telefonia_Movel_200902-2018_Modalidade_Colunas",
          "Acessos_Telefonia_Movel_200902-2018_Tecnologia_Colunas"}  # fmt: skip


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    quando = datetime(2026, 10, 14, 17, tzinfo=UTC)
    with criar_engine(url).begin() as c:
        for fonte, enderecos in ENDERECOS.items():
            for endereco, amostra in enderecos:
                conteudo = (AMOSTRAS / amostra).read_bytes()
                caminho = acervo.guardar_original(fonte, endereco, conteudo, quando)
                registrar(c, fonte, endereco, conteudo, "ok", agora=quando,
                          caminho_do_original=caminho)  # fmt: skip
    raiz = tmp_path / "acervo" / "base"
    empresa_serie = pd.DataFrame(
        {"fonte": [anp.FONTE, anac.FONTE, aneel.FONTE, anatel.FONTE, ans.FONTE_DA_LIGACAO,
                   anp_concessionarios.FONTE, antt_siade.FONTE],
         "chave": ["RAIZEN S.A.", "GLO", "06840748000189", "02558157000162", "368253",
                   "33000167000101", "EFC"],
         "cnpj_companhia": ["33.453.598/0001-23", "06.164.253/0001-87", "06.272.793/0001-84",
                            "02.558.157/0001-62", "05.197.443/0001-38", "33.000.167/0001-01",
                            "33.592.510/0001-54"],
         "principal": [True] * 7}
    )  # fmt: skip
    gravar_tabela(
        empresa_serie, raiz / "empresa_serie" / "empresa_serie", [], ["fonte", "chave"]
    )
    return raiz


def test_grava_cada_fonte_por_ano_com_manifesto_e_linhagem(ambiente):
    from base.linhagem import linhagem_da_tabela

    assert carga_setoriais.main(["--base", str(ambiente)]) == 0
    pasta = ambiente / "setoriais"
    esperados = {
        "anac": {"2019", "2026"},
        "anp": {"2010", "2019", "2026"},
        "ons": {"2010", "2026"},
        "aneel": {"2010", "2024"},
        "anatel": ANATEL,
        "ans": {"2017", "2026"},
        "susep": {"2000", "2015", "2026"},
        "cftc": {"2026"},
        "ccee": {"2001", "2021", "2025"},
        "ons_restricao": {"eolica_2026_09", "fotovoltaica_2024_04"},
        "ons_capacidade": {"capacidade"},
        "anp_concessionarios": {"concessionarios"},
        "antt_siade": {"2006", "2026"},
        "comex_preco_medio": {"exportacao_2026", "importacao_2026"},
    }
    with criar_engine().connect() as c:
        for fonte, anos in esperados.items():
            arquivos = {p.stem for p in (pasta / fonte).glob("*.parquet")}
            assert arquivos == anos, fonte
            for ano in anos:
                arquivo = pasta / fonte / f"{ano}.parquet"
                assert conferir_tabela(arquivo), arquivo
                manifesto = json.loads(
                    arquivo.with_suffix(".json").read_text(encoding="utf-8")
                )
                assert manifesto["versao_do_codigo"] == VERSAO
                assert linhagem_da_tabela(c, arquivo).completa, arquivo
    ons_2010 = pd.read_parquet(pasta / "ons" / "2010.parquet")
    assert set(ons_2010["instante"].dt.year) == {2010}


def test_so_uma_fonte_carrega_so_ela_e_nao_mexe_nos_buracos(ambiente):
    assert (
        carga_setoriais.main(["--base", str(ambiente), "--fonte", cftc_cot.FONTE]) == 0
    )
    pasta = ambiente / "setoriais"
    assert {p.stem for p in (pasta / "cftc").glob("*.parquet")} == {"2026"}
    assert not (pasta / "anp").exists()
    assert not (pasta / "buracos").exists()


def test_buracos_da_ligacao_pela_b13(ambiente):
    carga_setoriais.main(["--base", str(ambiente)])
    buracos = pd.read_parquet(ambiente / "setoriais" / "buracos.parquet")
    por_fonte = buracos.groupby("fonte")["chave"].agg(set).to_dict()
    assert por_fonte == {
        anp.FONTE: {"VIBRA ENERGIA S.A"},
        anac.FONTE: {"AZU", "TAM"},
        aneel.FONTE: {"15139629000194"},  # a Coelba, fora da B13 do teste
        anatel.FONTE: {"02421421000111"},  # a TIM, idem
        ans.FONTE: {"005711", "326305"},
        susep.FONTE: {
            "05631",
            "05886",
            "06033",
            "06785",
        },  # a B13 não liga a SUSEP (ainda)
        ons_capacidade.FONTE: {
            "AXIA NORDESTE",
            "GEBRA",
        },  # a B13 do teste não tem energia
        ons_restricao.FONTE: {"SIMM", "VISUS ENGENHARIA", "AUREN OPERAÇÕES"},
        anp_concessionarios.FONTE: CNPJS_SEM_B13,  # só a Petrobras está na B13 do teste
        antt_siade.FONTE: {"EFPO", "EFVM"},  # só a EFC está na B13 do teste
    }


def test_buracos_mudam_com_a_fonte_mesmo_com_a_b13_igual(ambiente):
    """A B13 é a única origem anotada: com ela igual, uma revisão da fonte ainda muda os buracos."""
    carga_setoriais.main(["--base", str(ambiente)])
    arquivo = ambiente / "setoriais" / "buracos.parquet"
    antes = pd.read_parquet(arquivo).set_index(["fonte", "chave"])["valor"]
    original = (
        AMOSTRAS / "ans" / "Beneficiarios_operadora_e_carteira.csv"
    ).read_bytes()
    revisado = original.replace(b'"202606";558570', b'"202606";600000', 1)
    quando = datetime(2026, 11, 14, 17, tzinfo=UTC)
    with criar_engine().begin() as c:
        caminho = acervo.guardar_original(ans.FONTE, ans.URL, revisado, quando)
        registrar(
            c,
            ans.FONTE,
            ans.URL,
            revisado,
            "ok",
            agora=quando,
            caminho_do_original=caminho,
        )
    carga_setoriais.main(["--base", str(ambiente)])
    depois = pd.read_parquet(arquivo).set_index(["fonte", "chave"])["valor"]
    assert (
        depois[(ans.FONTE, "326305")] == antes[(ans.FONTE, "326305")] + 600000 - 558570
    )
    assert conferir_tabela(arquivo)


def test_mes_revisado_pela_ans_vira_linha_nova_com_o_dia_em_que_foi_visto(ambiente):
    """A ANS regrava o arquivo e muda um mês passado: a 2ª coleta entra como revisão (série 4, PR 5)."""
    original = (
        AMOSTRAS / "ans" / "Beneficiarios_operadora_e_carteira.csv"
    ).read_bytes()
    revisado = original.replace(b'"202606";558570', b'"202606";558571', 1)
    assert revisado != original
    quando = datetime(2026, 11, 14, 17, tzinfo=UTC)
    with criar_engine().begin() as c:
        caminho = acervo.guardar_original(ans.FONTE, ans.URL, revisado, quando)
        registrar(
            c,
            ans.FONTE,
            ans.URL,
            revisado,
            "ok",
            agora=quando,
            caminho_do_original=caminho,
        )
    assert carga_setoriais.main(["--base", str(ambiente)]) == 0
    tabela = pd.read_parquet(ambiente / "setoriais" / "ans" / "2017.parquet")
    linha = tabela[tabela["beneficiarios"].isin([558570, 558571])].sort_values(
        "visto_em"
    )
    assert linha["beneficiarios"].tolist() == [558570, 558571]
    assert linha["disponivel_em"].iloc[1] == pd.Timestamp("2026-11-14")
    manifesto = json.loads(
        (ambiente / "setoriais" / "ans" / "2017.json").read_text(encoding="utf-8")
    )
    assert len(manifesto["origens"]) == 2  # as duas baixadas


def test_segunda_carga_com_os_mesmos_originais_nao_regrava(ambiente):
    carga_setoriais.main(["--base", str(ambiente)])
    manifesto = ambiente / "setoriais" / "anac" / "2019.json"
    antes = manifesto.read_text(encoding="utf-8")
    carga_setoriais.main(["--base", str(ambiente)])
    assert manifesto.read_text(encoding="utf-8") == antes
    assert not list((ambiente / "setoriais").rglob("*.v1.parquet"))


def test_sem_a_versao_do_codigo_nao_grava(ambiente, monkeypatch):
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError):
        carga_setoriais.main(["--base", str(ambiente)])
    assert not (ambiente / "setoriais").exists()


def test_concessionarios_sem_data_valem_desde_o_dia_da_coleta(ambiente):
    carga_setoriais.main(["--base", str(ambiente)])
    tabela = pd.read_parquet(
        ambiente / "setoriais" / "anp_concessionarios" / "concessionarios.parquet"
    )
    assert set(tabela["disponivel_em"]) == {pd.Timestamp("2026-10-14")}
    assert set(tabela["visto_em"]) == {pd.Timestamp("2026-10-14")}
    assert len(tabela) == 27


def test_preco_medio_do_comex_soma_os_dois_fluxos_sem_ligar_a_empresa(ambiente):
    carga_setoriais.main(["--base", str(ambiente)])
    pasta = ambiente / "setoriais" / "comex_preco_medio"
    exportacao = pd.read_parquet(pasta / "exportacao_2026.parquet")
    assert set(exportacao["fluxo"]) == {"exportacao"}
    assert not (
        pd.read_parquet(ambiente / "setoriais" / "buracos.parquet")["fonte"]
        == comex_preco_medio.FONTE
    ).any()
