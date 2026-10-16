"""Carga das fontes setoriais (série 4, PR 4): lê os originais que o arquivista guardou (não baixa nada)
e grava um Parquet por fonte e ano, com manifesto, versões e linhagem, mais os buracos da ligação pela
B13. Sem internet: as amostras de `tests/arquivos/setoriais/` entram no acervo como coletas."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base.arquivo.fontes import SES_DA_SUSEP
from base.parquet import conferir_tabela, gravar_tabela
from base.setoriais import anac, anatel, aneel, anp, ans, ons, susep
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
    ans.FONTE: [(ans.URL, "ans/Beneficiarios_operadora_e_carteira.csv")],
    susep.FONTE: [(f"{SES_DA_SUSEP}#{susep.ARQUIVO}", "susep/Ses_seguros.csv")],
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
        {"fonte": [anp.FONTE, anac.FONTE, aneel.FONTE, anatel.FONTE, ans.FONTE_DA_LIGACAO],
         "chave": ["RAIZEN S.A.", "GLO", "06840748000189", "02558157000162", "368253"],
         "cnpj_companhia": ["33.453.598/0001-23", "06.164.253/0001-87", "06.272.793/0001-84",
                            "02.558.157/0001-62", "05.197.443/0001-38"],
         "principal": [True] * 5}
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
    }


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
