"""Montagem da amostra integrada (PR 1): lê as tabelas da base e o cadastro do acervo, grava o painel por
ano com manifesto e as origens, e uma segunda montagem com a mesma base não regrava nada."""

import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from base.parquet import conferir_tabela, gravar_tabela
from scripts import montar_amostra
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para

VERSAO = "7b2b0c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7c"
URL_DO_CADASTRO = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
)
CADASTRO = (
    "CNPJ_CIA;DENOM_SOCIAL;DT_REG;DT_CANCEL;MOTIVO_CANCEL;SIT;SETOR_ATIV;UF\n"
    "11.111.111/0001-11;ATIVA FICTICIA SA;2005-03-01;;;ATIVO;Energia;SP\n"
    "22.222.222/0001-22;CANCELADA FICTICIA SA;2012-02-10;2015-07-20;Voluntário;CANCELADA;Varejo;RJ\n"
)

# as entradas vêm da CVM (a trava das licenças barra a amostra de treino sem fonte conhecida)
DA_CVM = [
    {
        "url": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/x.zip",
        "sha256": "a" * 64,
    }
]


@pytest.fixture
def base(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    conteudo = CADASTRO.encode("latin-1")
    quando = datetime(2026, 10, 15, 5, tzinfo=UTC)
    with criar_engine(url).begin() as c:
        caminho = acervo.guardar_original(
            "cvm-cadastros", URL_DO_CADASTRO, conteudo, quando
        )
        registrar(c, "cvm-cadastros", URL_DO_CADASTRO, conteudo, "ok", agora=quando,
                  caminho_do_original=caminho)  # fmt: skip
    raiz = tmp_path / "acervo" / "base"
    entregas = pd.DataFrame(
        {
            "cnpj": ["11.111.111/0001-11", "22.222.222/0001-22"],
            "primeira_entrega": pd.to_datetime(["2009-03-30", "2012-05-15"]),
        }
    )
    gravar_tabela(
        entregas, raiz / "rotulos_atraso" / "rotulos_atraso", DA_CVM, ["cnpj"]
    )
    tickers = pd.DataFrame(
        {
            "codigo": ["ATVA3"], "cnpj": ["11.111.111/0001-11"],
            "primeiro_visto": pd.to_datetime(["2011-05-31"]), "valido_ate": pd.to_datetime([None]),
        }
    )  # fmt: skip
    gravar_tabela(tickers, raiz / "fca" / "tickers", DA_CVM, ["codigo"])
    return raiz


def test_grava_o_painel_por_ano_com_as_origens(base):
    assert montar_amostra.main(["--base", str(base), "--fim", "2016-12-31"]) == 0
    pasta = base / montar_amostra.PASTA
    assert {p.stem for p in pasta.glob("*.parquet")} == {
        str(a) for a in range(2010, 2017)
    }
    for arquivo in pasta.glob("*.parquet"):
        assert conferir_tabela(arquivo), arquivo
    manifesto = json.loads((pasta / "2015.json").read_text(encoding="utf-8"))
    assert [o["url"] for o in manifesto["origens"]] == [
        URL_DO_CADASTRO, "rotulos_atraso/rotulos_atraso.parquet", "fca/tickers.parquet",
    ]  # fmt: skip
    painel = pd.read_parquet(pasta / "2015.parquet")
    cancelada = painel[painel["cnpj"] == "22.222.222/0001-22"]
    assert cancelada["data"].max() == pd.Timestamp(
        "2015-06-30"
    )  # cancelada em 20/07/2015


def test_segunda_montagem_com_a_mesma_base_nao_regrava(base):
    montar_amostra.main(["--base", str(base), "--fim", "2016-12-31"])
    manifesto = base / montar_amostra.PASTA / "2012.json"
    antes = manifesto.read_text(encoding="utf-8")
    montar_amostra.main(["--base", str(base), "--fim", "2016-12-31"])
    assert manifesto.read_text(encoding="utf-8") == antes
    assert not list((base / montar_amostra.PASTA).glob("*.v1.parquet"))


def test_ultimo_mes_fechado():
    assert montar_amostra.ultimo_mes_fechado(
        pd.Timestamp("2026-10-01")
    ) == pd.Timestamp("2026-09-30")
    assert montar_amostra.ultimo_mes_fechado(
        pd.Timestamp("2026-10-31 23:00")
    ) == pd.Timestamp("2026-09-30")


def test_sem_a_versao_do_codigo_nao_grava(base, monkeypatch):
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError):
        montar_amostra.main(["--base", str(base), "--fim", "2016-12-31"])
    assert not (base / "amostra").exists()


def test_painel_traz_as_demonstracoes_como_eram(base):
    linha = {
        "cnpj": "11.111.111/0001-11", "empresa": "ATIVA", "grupo": "con", "demonstracao": "BPA",
        "conta": "1", "descricao": "Ativo Total", "inicio": pd.NaT, "fim": pd.Timestamp("2014-12-31"),
        "valor": 1000.0, "documento": "DFP", "referencia": pd.Timestamp("2014-12-31"), "versao": 1,
        "ordem": "ultimo", "origem": "dados_abertos", "divulgado_em": pd.Timestamp("2015-03-20"),
        "ate": pd.NaT,
    }  # fmt: skip
    gravar_tabela(
        pd.DataFrame([linha]), base / "demonstracoes" / "2014", DA_CVM, ["cnpj"]
    )
    montar_amostra.main(["--base", str(base), "--fim", "2016-12-31"])
    painel = pd.read_parquet(base / montar_amostra.PASTA / "2015.parquet")
    ativa = painel[painel["cnpj"] == "11.111.111/0001-11"].set_index("data")
    assert pd.isna(
        ativa.loc[pd.Timestamp("2015-02-28"), "ativo_total"]
    )  # entregue em 20/03
    assert ativa.loc[pd.Timestamp("2015-03-31"), "ativo_total"] == 1000.0
    manifesto = json.loads(
        (base / montar_amostra.PASTA / "2015.json").read_text(encoding="utf-8")
    )
    assert "demonstracoes/2014.parquet" in [o["url"] for o in manifesto["origens"]]


def _trocar_a_origem_dos_tickers(base, url: str) -> None:
    tickers = pd.read_parquet(base / "fca" / "tickers.parquet")
    origem = [{"url": url, "sha256": "b" * 64}]
    gravar_tabela(tickers, base / "fca" / "tickers", origem, ["codigo"])


def test_amostra_com_entrada_da_b3_da_erro_e_nao_grava(base, monkeypatch):
    """A trava das licenças: a amostra é a entrada do treino; uma tabela com fonte fora dos usos
    (`FONTES_FORA_DOS_USOS`, vazia desde a Emenda 6 da ADR 0008) barra a montagem inteira."""
    from src.banco import coletas
    from src.banco.coletas import LicencaNaoPermiteError

    monkeypatch.setattr(coletas, "FONTES_FORA_DOS_USOS", frozenset({"b3"}))

    _trocar_a_origem_dos_tickers(
        base, "https://arquivos.b3.com.br/rapinegocios/tickercsv/2016-12-30"
    )
    with pytest.raises(LicencaNaoPermiteError, match="b3"):
        montar_amostra.main(["--base", str(base), "--fim", "2016-12-31"])
    assert not (base / montar_amostra.PASTA).exists()


def test_amostra_com_entrada_nao_comercial_grava_e_herda_a_marca(base):
    """ADR 0102: fonte "não comercial" (datas do Wayback) entra; o painel herda a marca."""
    _trocar_a_origem_dos_tickers(base, "https://web.archive.org/web/2025/x")
    assert montar_amostra.main(["--base", str(base), "--fim", "2016-12-31"]) == 0
    manifesto = json.loads(
        (base / montar_amostra.PASTA / "2015.json").read_text(encoding="utf-8")
    )
    assert manifesto["licenca"]["marca"] == "nao_comercial"
    assert manifesto["licenca"]["fontes"]["wayback"] == "nao_comercial"
