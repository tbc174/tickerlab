"""A trava das licenças (ADR 0008, Emenda 1): quatro marcas, a marca no manifesto de cada tabela (a
derivada herda a mais restrita) e erro ao treinar, rotular ou exportar com fonte "não comercial" ou
"a confirmar"."""

import json
from pathlib import Path

import pandas as pd
import pytest

from base import licenca
from base.parquet import gravar_se_mudou, gravar_tabela, origem_de_tabela
from src.banco import coletas
from src.banco.coletas import (
    MODELO_CLIMA_DE_RISCO,
    LicencaNaoPermiteError,
    Marca,
    exigir_licenca,
    marca_da_fonte,
    marca_mais_restrita,
)

URL_CVM = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
URL_WAYBACK = "https://web.archive.org/web/20251101000000/https://www.igcp.com.br/x"
URL_CNPJ = (
    "https://arquivos.receitafederal.gov.br/public.php/dav/files/abc/Empresas0.zip"
)
USOS = ("treinar", "rotular", "exportar")


def _tabela() -> pd.DataFrame:
    return pd.DataFrame({"cnpj": ["1", "2"], "valor": [1.0, 2.0]})


def _gravar(destino: Path, *urls: str, origens: list | None = None) -> Path:
    todas = [{"url": u, "sha256": "a" * 64} for u in urls] + (origens or [])
    return gravar_tabela(_tabela(), destino, todas, ["cnpj"])


def _manifesto(arquivo: Path) -> dict:
    return json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))


# --- as quatro marcas -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fonte", "marca"),
    [
        ("cvm-ipe", Marca.VENDAVEL),
        ("bcb-sgs-433", Marca.VENDAVEL),
        (
            "sec-13f",
            Marca.USO_INTERNO,
        ),  # a SEC permite ML por escrito; revenda a confirmar
        ("yahoo", Marca.NAO_COMERCIAL),  # termos do Yahoo: uso pessoal
        ("yahoo-bvsp", Marca.NAO_COMERCIAL),
        ("b3-negocios", Marca.NAO_COMERCIAL),  # só pesquisa até a B3 autorizar
        ("bcb-sgs-189", Marca.NAO_COMERCIAL),  # IGP-M da FGV, mesmo repassado pelo BC
        (
            "wayback-igc",
            Marca.NAO_COMERCIAL,
        ),  # "for scholarship and research purposes only"
        ("kraken", Marca.NAO_COMERCIAL),  # fora da exceção da ADR 0045
        ("mb", Marca.NAO_COMERCIAL),
        ("rfb-cnpj", Marca.A_CONFIRMAR),  # perguntar a licença do conjunto
        ("pgfn-divida", Marca.A_CONFIRMAR),
        (
            "fonte-que-ninguem-conhece",
            Marca.A_CONFIRMAR,
        ),  # fonte nova sem resposta escrita
    ],
)
def test_cada_fonte_tem_uma_das_quatro_marcas(fonte, marca):
    assert marca_da_fonte(fonte) == marca


def test_toda_resposta_de_revenda_tem_marca():
    assert {marca_da_fonte(f) for f in coletas.REVENDA} <= set(Marca)
    assert set(coletas.MARCA_DA_REVENDA) == set(coletas.REVENDA.values())


def test_a_mais_restrita_vence():
    assert marca_mais_restrita([Marca.VENDAVEL, Marca.USO_INTERNO]) == Marca.USO_INTERNO
    assert marca_mais_restrita([Marca.A_CONFIRMAR, Marca.VENDAVEL]) == Marca.A_CONFIRMAR
    assert (
        marca_mais_restrita([Marca.A_CONFIRMAR, Marca.NAO_COMERCIAL])
        == Marca.NAO_COMERCIAL
    )
    assert marca_mais_restrita([]) == Marca.A_CONFIRMAR  # sem fonte conhecida


# --- o erro -------------------------------------------------------------------------------------


@pytest.mark.parametrize("uso", USOS)
@pytest.mark.parametrize("fonte", ["yahoo-bvsp", "rfb-cnpj", "b3-negocios"])
def test_fonte_nao_comercial_ou_a_confirmar_da_erro(uso, fonte):
    with pytest.raises(LicencaNaoPermiteError, match=fonte):
        exigir_licenca(uso, ["cvm-ipe", fonte])


@pytest.mark.parametrize("uso", USOS)
def test_vendavel_e_uso_interno_passam(uso):
    exigir_licenca(uso, ["cvm-ipe", "sec-13f", "bcb-sgs-433"])


def test_uso_que_nao_existe_da_erro():
    with pytest.raises(ValueError, match="uso"):
        exigir_licenca("vender", ["cvm-ipe"])


def test_excecao_da_adr_0045_so_no_clima_de_risco_e_nunca_na_exportacao():
    exigir_licenca("treinar", ["kraken", "mb", "btc"], modelo=MODELO_CLIMA_DE_RISCO)
    exigir_licenca("rotular", ["kraken"], modelo=MODELO_CLIMA_DE_RISCO)
    with pytest.raises(LicencaNaoPermiteError):
        exigir_licenca("treinar", ["kraken"])
    with pytest.raises(LicencaNaoPermiteError):
        exigir_licenca("treinar", ["kraken"], modelo="outro-modelo")
    with pytest.raises(LicencaNaoPermiteError):
        exigir_licenca("exportar", ["kraken"], modelo=MODELO_CLIMA_DE_RISCO)
    with pytest.raises(LicencaNaoPermiteError):  # a exceção não cobre o Yahoo
        exigir_licenca("treinar", ["yahoo"], modelo=MODELO_CLIMA_DE_RISCO)


# --- a marca no manifesto -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "familia"),
    [
        (URL_CVM, "cvm"),
        ("https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?x=1", "cvm"),
        ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados", "bcb"),
        ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.189/dados", "bcb-sgs-189"),
        (URL_WAYBACK, "wayback"),
        (URL_CNPJ, "rfb-cnpj"),
        ("https://www.gov.br/receitafederal/pt-br/assuntos/x.xlsx", "rfb"),
        ("https://www.igcp.com.br/negocio-1", "assessoria"),
        ("https://arquivos.b3.com.br/rapinegocios/tickercsv/2026-10-15", "b3"),
        ("https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D01.ZIP", "b3"),
        (
            "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/x.csv",
            "anp",
        ),
        ("https://sem-fonte.example/x.csv", None),
        ("base/conferidas/empresas.csv", None),  # conferida à mão: não traz fonte nova
    ],
)
def test_familia_pelo_endereco_do_original(url, familia):
    assert licenca.familia_do_endereco(url) == familia


def test_manifesto_grava_a_marca_e_as_fontes(tmp_path):
    arquivo = _gravar(tmp_path / "base" / "cadastro" / "cadastro", URL_CVM)
    assert _manifesto(arquivo)["licenca"] == {
        "marca": "vendavel",
        "fontes": {"cvm": "vendavel"},
    }


def test_tabela_sem_fonte_conhecida_fica_a_confirmar(tmp_path):
    arquivo = _gravar(tmp_path / "base" / "x" / "x", "https://sem-fonte.example/x.csv")
    assert _manifesto(arquivo)["licenca"]["marca"] == "a_confirmar"
    assert _manifesto(arquivo)["licenca"]["sem_fonte"] == [
        "https://sem-fonte.example/x.csv"
    ]


def test_derivada_herda_a_marca_mais_restrita_das_entradas(tmp_path):
    base = tmp_path / "base"
    datas = _gravar(base / "ma_datas" / "ma_datas", URL_WAYBACK)
    cadastro = _gravar(base / "cadastro" / "cadastro", URL_CVM)
    derivada = _gravar(
        base / "ma_regua" / "ma_regua",
        origens=[origem_de_tabela(datas, base), origem_de_tabela(cadastro, base)],
    )
    assert _manifesto(derivada)["licenca"] == {
        "marca": "nao_comercial",
        "fontes": {"cvm": "vendavel", "wayback": "nao_comercial"},
    }


def test_derivada_de_derivada_herda_ate_o_original(tmp_path):
    base = tmp_path / "base"
    cnpj = _gravar(base / "cnpj" / "cnpj", URL_CNPJ)
    rede = _gravar(base / "rede" / "entidades", origens=[origem_de_tabela(cnpj, base)])
    amostra = _gravar(
        base / "amostra" / "painel", URL_CVM, origens=[origem_de_tabela(rede, base)]
    )
    assert licenca.licenca_da_tabela(amostra).marca == Marca.A_CONFIRMAR
    assert licenca.licenca_da_tabela(amostra).fontes == {
        "cvm": Marca.VENDAVEL,
        "rfb-cnpj": Marca.A_CONFIRMAR,
    }


def test_manifesto_antigo_sem_a_marca_e_calculado_pelas_origens(tmp_path):
    arquivo = _gravar(tmp_path / "base" / "ma" / "ma", URL_WAYBACK)
    manifesto = _manifesto(arquivo)
    del manifesto["licenca"]
    arquivo.with_suffix(".json").write_text(json.dumps(manifesto), encoding="utf-8")
    assert licenca.licenca_da_tabela(arquivo).marca == Marca.NAO_COMERCIAL


def test_entrada_que_sumiu_deixa_a_derivada_a_confirmar(tmp_path):
    base = tmp_path / "base"
    derivada = _gravar(
        base / "d" / "d", URL_CVM, origens=[{"url": "sumiu/x.parquet", "sha256": "b"}]
    )
    assert licenca.licenca_da_tabela(derivada).marca == Marca.A_CONFIRMAR


def test_cripto_sem_origens_tem_a_fonte_pela_pasta(tmp_path):
    """A base de cripto grava sem origens (a linhagem fica nas colunas): a pasta diz a fonte."""
    cripto = tmp_path / "cripto"
    kraken = cripto / "precos" / "kraken" / "2024.parquet"
    cftc = cripto / "cftc" / "2024.parquet"
    for arquivo in (kraken, cftc):
        gravar_se_mudou(_tabela(), arquivo, [], [], versoes=False)
    assert _manifesto(kraken)["licenca"]["fontes"] == {"kraken": "nao_comercial"}
    assert _manifesto(cftc)["licenca"]["fontes"] == {"cftc": "uso_interno"}
    licenca.exigir_licenca_das_tabelas(
        "treinar", [kraken, cftc], modelo=MODELO_CLIMA_DE_RISCO
    )
    with pytest.raises(LicencaNaoPermiteError, match="kraken"):
        licenca.exigir_licenca_das_tabelas("treinar", [kraken, cftc])


# --- o erro pelas tabelas -----------------------------------------------------------------------


@pytest.mark.parametrize("uso", USOS)
def test_tabela_nao_comercial_da_erro_e_diz_qual(uso, tmp_path):
    base = tmp_path / "base"
    boa = _gravar(base / "cadastro" / "cadastro", URL_CVM)
    ruim = _gravar(base / "ma_datas" / "ma_datas", URL_WAYBACK)
    licenca.exigir_licenca_das_tabelas(uso, [boa])
    with pytest.raises(LicencaNaoPermiteError, match="ma_datas"):
        licenca.exigir_licenca_das_tabelas(uso, [boa, ruim])


def test_origens_nao_comerciais_dao_erro_antes_de_gravar(tmp_path):
    base = tmp_path / "base"
    ruim = _gravar(base / "ma_datas" / "ma_datas", URL_WAYBACK)
    origens = [
        {"url": URL_CVM, "sha256": "a" * 64},
        origem_de_tabela(ruim, base),
    ]
    with pytest.raises(LicencaNaoPermiteError, match="wayback"):
        licenca.exigir_licenca_das_origens("treinar", origens, base / "amostra" / "x")
    licenca.exigir_licenca_das_origens("treinar", origens[:1], base / "amostra" / "x")


def test_tabela_sem_origens_fica_a_confirmar_e_da_erro(tmp_path):
    arquivo = gravar_tabela(_tabela(), tmp_path / "base" / "x" / "x", [], ["cnpj"])
    assert _manifesto(arquivo)["licenca"] == {
        "marca": "a_confirmar",
        "fontes": {},
        "sem_fonte": [licenca.SEM_ORIGENS],
    }
    with pytest.raises(LicencaNaoPermiteError, match="sem origens"):
        licenca.exigir_licenca_das_tabelas("treinar", [arquivo])


def test_conferida_com_a_fonte_de_cada_linha_traz_a_marca_dela(tmp_path, monkeypatch):
    """`base/conferidas/empresa_serie.csv` diz a fonte do arquivista em cada linha (o Comex Stat está
    a confirmar); texto livre na coluna `fonte` (as outras conferidas) não vira fonte."""
    conferidas = tmp_path / "repo" / "base" / "conferidas"
    conferidas.mkdir(parents=True)
    (conferidas / "empresa_serie.csv").write_text(
        "fonte;chave;cnpj\nans-beneficiarios;1;x\ncomexstat;2;y\n", encoding="utf-8"
    )
    (conferidas / "emissores.csv").write_text(
        "emissor;fonte\nABNB;cadastro de companhias da CVM (cad_cia_aberta.csv)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(licenca, "RAIZ_DO_REPOSITORIO", tmp_path / "repo")
    serie = _gravar(
        tmp_path / "base" / "empresa_serie" / "empresa_serie",
        URL_CVM,
        origens=[{"url": "base/conferidas/empresa_serie.csv", "sha256": "c"}],
    )
    emissores = _gravar(
        tmp_path / "base" / "fca" / "emissores",
        URL_CVM,
        origens=[{"url": "base/conferidas/emissores.csv", "sha256": "d"}],
    )
    assert _manifesto(serie)["licenca"] == {
        "marca": "a_confirmar",
        "fontes": {"ans": "vendavel", "comexstat": "a_confirmar", "cvm": "vendavel"},
    }
    assert _manifesto(emissores)["licenca"]["fontes"] == {"cvm": "vendavel"}
