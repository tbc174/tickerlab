"""A trava das licenças (ADR 0008, Emenda 1; ADR 0102): quatro marcas, a marca no manifesto de cada
tabela (a derivada herda a mais restrita) e, desde a ADR 0102, erro só com fonte fora dos usos (a B3):
a marca das outras fontes fica registrada e não barra treinar, rotular, exportar nem mostrar."""

import json
from pathlib import Path

import pandas as pd
import pytest

from base import licenca
from base.parquet import gravar_se_mudou, gravar_tabela, origem_de_tabela
from src.banco import coletas
from src.banco.coletas import (
    LicencaNaoPermiteError,
    Marca,
    exigir_licenca,
    fora_dos_usos,
    marca_da_fonte,
    marca_mais_restrita,
    pode_usar,
)

URL_CVM = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
URL_B3 = "https://arquivos.b3.com.br/rapinegocios/tickercsv/2026-10-15"
URL_WAYBACK = "https://web.archive.org/web/20251101000000/https://www.igcp.com.br/x"
URL_CNPJ = (
    "https://arquivos.receitafederal.gov.br/public.php/dav/files/abc/Empresas0.zip"
)
USOS = ("treinar", "rotular", "exportar", "mostrar")
FONTES_COM_MARCA_RESTRITA = (
    "yahoo-bvsp",  # não comercial, na lista dos usos sem cobrança
    "tce-rs",  # a confirmar, fora da lista
    "kraken",  # não comercial, antes só na exceção da ADR 0045
    "fonte-que-ninguem-conhece",  # sem resposta escrita: a confirmar
)


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
        (
            "rfb-cnpj",
            Marca.VENDAVEL,
        ),  # CC BY na ficha do dados.gov.br (Pode, 20/10/2026)
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


# --- o erro: só a B3 (ADR 0102) ----------------------------------------------------------------


def test_nenhuma_fonte_fica_fora_dos_usos():
    """ADR 0008, Emenda 6 (22/10/2026): a B3, a única da lista, entrou com a fonte citada."""
    assert not coletas.FONTES_FORA_DOS_USOS
    assert not fora_dos_usos("b3") and not fora_dos_usos("b3-negocios")
    assert not any(fora_dos_usos(f) for f in FONTES_COM_MARCA_RESTRITA)


@pytest.mark.parametrize("uso", USOS)
def test_b3_passa_em_todos_os_usos_com_a_marca_registrada(uso):
    """A trava antes barrava a B3; agora a marca é só informação e a fonte é citada."""
    exigir_licenca(uso, ["cvm-ipe", "b3-negocios", "b3-cotahist"], onde="teste")
    assert pode_usar(uso, "b3-negocios")
    assert marca_da_fonte("b3-negocios") == Marca.NAO_COMERCIAL


def test_a_b3_sai_com_a_fonte_citada_e_a_data():
    citacao = next(u.citacao for u in coletas.USOS_SEM_COBRANCA if u.fonte == "b3")
    assert citacao.startswith("Fonte: B3") and "data" in citacao
    assert "Emenda 6" in citacao
    assert coletas.citacoes_das_fontes(["b3-cotahist", "b3-negocios", "cvm-ipe"]) == [
        citacao
    ]


@pytest.mark.parametrize("uso", USOS)
def test_b3_volta_a_dar_erro_se_a_lista_a_receber_de_novo(uso, monkeypatch):
    """Como desfazer a Emenda 6: pôr "b3" de volta em `FONTES_FORA_DOS_USOS`."""
    monkeypatch.setattr(coletas, "FONTES_FORA_DOS_USOS", frozenset({"b3"}))
    with pytest.raises(LicencaNaoPermiteError, match="b3-negocios") as erro:
        exigir_licenca(uso, ["cvm-ipe", "b3-negocios"], onde="teste")
    assert "FONTES_FORA_DOS_USOS" in str(erro.value) and "(teste)" in str(erro.value)
    assert not pode_usar(uso, "b3-negocios")


@pytest.mark.parametrize("uso", USOS)
@pytest.mark.parametrize("fonte", FONTES_COM_MARCA_RESTRITA)
def test_marca_restrita_nao_barra_mas_fica_registrada(uso, fonte):
    """ADR 0102: "não comercial" e "a confirmar" são informação; a fonte entra, com a marca gravada."""
    exigir_licenca(uso, ["cvm-ipe", fonte])
    assert pode_usar(uso, fonte)
    assert marca_da_fonte(fonte) in {Marca.NAO_COMERCIAL, Marca.A_CONFIRMAR}


@pytest.mark.parametrize("uso", USOS)
def test_vendavel_e_uso_interno_passam(uso):
    exigir_licenca(uso, ["cvm-ipe", "sec-13f", "bcb-sgs-433"])


def test_uso_que_nao_existe_da_erro():
    with pytest.raises(ValueError, match="uso"):
        exigir_licenca("vender", ["cvm-ipe"])
    with pytest.raises(ValueError, match="uso"):
        pode_usar("vender", "cvm-ipe")


def test_kraken_e_mb_entram_em_qualquer_modelo_e_na_exportacao():
    """A exceção da ADR 0045 (só o clima de risco) perdeu o sentido: a marca não barra mais."""
    for uso in USOS:
        exigir_licenca(uso, ["kraken", "mb", "btc", "yahoo"])


def test_a_trava_segue_funcionando_para_quem_entrar_na_lista(monkeypatch):
    monkeypatch.setattr(coletas, "FONTES_FORA_DOS_USOS", frozenset({"b3", "cvm"}))
    with pytest.raises(LicencaNaoPermiteError, match="cvm-ipe"):
        exigir_licenca("treinar", ["cvm-ipe", "sec-13f"])
    assert not pode_usar("mostrar", "cvm-ipe") and pode_usar("mostrar", "sec-13f")


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
        (
            "https://pit.tce.pr.gov.br/Arquivos/2013_PIT_TodosArquivos.zip#2013_410010_Contrato.zip",
            "tce-pr",
        ),
        (
            "https://dados.tce.rs.gov.br/dados/municipal/empenhos/2024.csv.zip",
            "tce-rs-empenhos",
        ),
        ("https://dados.tce.rs.gov.br/dados/licitacon/2024.zip", "tce-rs"),
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
    assert licenca.licenca_da_tabela(amostra).marca == Marca.VENDAVEL
    assert licenca.licenca_da_tabela(amostra).fontes == {
        "cvm": Marca.VENDAVEL,
        "rfb-cnpj": Marca.VENDAVEL,
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
    licenca.exigir_licenca_das_tabelas("treinar", [kraken, cftc])  # ADR 0102: só marca


# --- o erro pelas tabelas -----------------------------------------------------------------------


@pytest.mark.parametrize("uso", USOS)
def test_tabela_da_b3_da_erro_e_diz_qual_se_ela_voltar_para_a_lista(
    uso, tmp_path, monkeypatch
):
    monkeypatch.setattr(coletas, "FONTES_FORA_DOS_USOS", frozenset({"b3"}))
    base = tmp_path / "base"
    boa = _gravar(base / "cadastro" / "cadastro", URL_CVM)
    restrita = _gravar(base / "ma_datas" / "ma_datas", URL_WAYBACK)
    da_b3 = _gravar(base / "b3_negocios" / "b3_negocios", URL_B3)
    licenca.exigir_licenca_das_tabelas(
        uso, [boa, restrita]
    )  # a marca só fica registrada
    assert _manifesto(restrita)["licenca"]["marca"] == "nao_comercial"
    with pytest.raises(LicencaNaoPermiteError, match="b3_negocios"):
        licenca.exigir_licenca_das_tabelas(uso, [boa, da_b3])


def test_origens_da_b3_dao_erro_se_ela_voltar_para_a_lista(tmp_path, monkeypatch):
    monkeypatch.setattr(coletas, "FONTES_FORA_DOS_USOS", frozenset({"b3"}))
    base = tmp_path / "base"
    restrita = _gravar(base / "ma_datas" / "ma_datas", URL_WAYBACK)
    da_b3 = _gravar(base / "b3_negocios" / "b3_negocios", URL_B3)
    origens = [
        {"url": URL_CVM, "sha256": "a" * 64},
        origem_de_tabela(restrita, base),
        origem_de_tabela(da_b3, base),
    ]
    with pytest.raises(LicencaNaoPermiteError, match="b3"):
        licenca.exigir_licenca_das_origens("treinar", origens, base / "amostra" / "x")
    licenca.exigir_licenca_das_origens("treinar", origens[:2], base / "amostra" / "x")


def test_tabela_sem_origens_fica_a_confirmar_e_passa(tmp_path):
    arquivo = gravar_tabela(_tabela(), tmp_path / "base" / "x" / "x", [], ["cnpj"])
    assert _manifesto(arquivo)["licenca"] == {
        "marca": "a_confirmar",
        "fontes": {},
        "sem_fonte": [licenca.SEM_ORIGENS],
    }
    licenca.exigir_licenca_das_tabelas("treinar", [arquivo])  # ADR 0102: informação


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


# --- Emenda 3: a lista dos usos em tela e as citações (não decide mais; ADR 0102) ---------------

FONTES_DA_EMENDA_3 = (
    "yahoo",  # múltiplos p_l e p_vp dos padrões setoriais
    "pgfn",  # dívida ativa
    "comexstat",  # B13 e rede
    "assessoria",  # negócios de M&A (só fatos, ADR 0082)
    "bcb-sgs-189",  # IGP-M da FGV
    "wayback",  # datas das cópias
    "gdelt",
)


def test_a_lista_tem_os_usos_da_emenda_3_com_onde_e_substituto():
    por_fonte = {uso.fonte: uso for uso in coletas.USOS_SEM_COBRANCA}
    assert set(FONTES_DA_EMENDA_3) <= set(por_fonte)
    for uso in coletas.USOS_SEM_COBRANCA:
        assert uso.fonte in coletas.REVENDA, uso.fonte  # fonte conhecida, com marca
        assert marca_da_fonte(uso.fonte) != Marca.VENDAVEL, uso.fonte  # senão sobra
        assert uso.onde and uso.substituto and uso.citacao, uso.fonte
    assert "b3" in por_fonte  # Emenda 6 (22/10/2026): a B3 entrou, com a citação


@pytest.mark.parametrize(
    "fonte",
    [
        "yahoo-bvsp",
        "pgfn-divida",
        "comexstat",
        "assessoria-igc",
        "bcb-sgs-189",
        "wayback-igc",
        "gdelt",
    ],
)
def test_mostrar_aceita_fonte_restrita_da_lista(fonte):
    exigir_licenca("mostrar", ["cvm-ipe", fonte], onde="relatório")
    assert coletas.pode_usar("mostrar", fonte)
    assert coletas.uso_sem_cobranca(fonte) is not None


def test_a_lista_nao_decide_mais_o_que_aparece(monkeypatch):
    """ADR 0102: tirar a fonte da lista não barra; quem bloqueia é só `FONTES_FORA_DOS_USOS`."""
    monkeypatch.setattr(coletas, "USOS_SEM_COBRANCA", ())
    exigir_licenca("mostrar", ["yahoo-bvsp", "pgfn-divida", "b3-negocios"])
    com_b3 = (coletas.UsoSemCobranca("b3", "teste", "teste", "teste"),)
    monkeypatch.setattr(coletas, "USOS_SEM_COBRANCA", com_b3)
    exigir_licenca("mostrar", ["b3-negocios"])
    monkeypatch.setattr(coletas, "FONTES_FORA_DOS_USOS", frozenset({"b3"}))
    with pytest.raises(LicencaNaoPermiteError, match="b3-negocios"):
        exigir_licenca("mostrar", ["b3-negocios"])


def test_conab_e_faostat_saem_com_a_fonte_citada():
    # PR 3 da ADR 0102: as tabelas do café vão para tela e API; a frase da fonte vem daqui
    citacao_da_conab = next(
        u.citacao for u in coletas.USOS_SEM_COBRANCA if u.fonte == "conab"
    )
    assert "CONAB" in citacao_da_conab and "CC BY-ND" in citacao_da_conab
    assert coletas.citacoes_das_fontes(["conab-cafe-safra", "faostat-cafe"]) == [
        citacao_da_conab,
        coletas.FRASE_DA_FAO,
    ]
    assert "CC BY 4.0" in coletas.FRASE_DA_FAO and "FAOSTAT" in coletas.FRASE_DA_FAO
    assert "ADR 0102" in coletas.LICENCAS["conab"]


def test_citacoes_das_fontes_restritas_e_a_frase_da_iex():
    citacao_do_yahoo = next(
        u.citacao for u in coletas.USOS_SEM_COBRANCA if u.fonte == "yahoo"
    )
    assert coletas.citacoes_das_fontes(["cvm-ipe", "yahoo-bvsp", "yahoo", "iex"]) == [
        citacao_do_yahoo,
        coletas.FRASE_DA_IEX,
    ]
    assert coletas.citacoes_das_fontes(["cvm-ipe", "bcb-sgs-433"]) == []
    assert "Data provided for free by IEX" in coletas.FRASE_DA_IEX


def test_rfb_cnpj_vendavel_com_atribuicao():
    # a ficha do conjunto no dados.gov.br declara CC BY; Tiago, "Pode", 20/10/2026 (ADR 0106, item 2)
    assert coletas.REVENDA["rfb-cnpj"] == coletas.VENDAVEL_COM_ATRIBUICAO
    assert marca_da_fonte("rfb-cnpj") == Marca.VENDAVEL
    assert (
        "CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026"
        in coletas.LICENCAS["rfb-cnpj"]
    )
    # a planilha de cripto da Receita não muda
    assert marca_da_fonte("rfb-cripto") == Marca.A_CONFIRMAR
    assert coletas.citacoes_das_fontes(["rfb-cnpj", "rfb-cnpj-estabelecimentos"]) == [
        coletas.FRASE_DA_RECEITA
    ]
    assert coletas.citacoes_das_fontes(["rfb-cripto"]) == []
    assert "Fonte: Receita Federal, dados abertos do CNPJ" in coletas.FRASE_DA_RECEITA


def test_cnpj_fora_dos_usos_sem_cobranca():
    por_fonte = {uso.fonte for uso in coletas.USOS_SEM_COBRANCA}
    assert "rfb-cnpj" not in por_fonte
    assert coletas.uso_sem_cobranca("rfb-cnpj") is None
    assert "pgfn" in por_fonte  # o da PGFN fica
    for uso in ("treinar", "rotular", "exportar", "mostrar"):
        assert coletas.pode_usar(uso, "rfb-cnpj")
