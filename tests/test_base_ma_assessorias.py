"""Fatos dos posts das assessorias de M&A (base/ma_assessorias.py, ADR 0082, série 5 do plano de M&A).

As páginas daqui são inventadas, no formato das da IGC (listas do Webflow: empresa assessorada,
contraparte, país e equipe), com nomes de empresas e pessoas que não existem.
"""

import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from base import ma_assessorias as ma
from base.dicionario import TABELAS
from base.parquet import conferir_tabela, ler_tabela
from scripts import carga_ma_assessorias as carga
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para

SITE = "https://www.assessoria.com.br/transactions/"
QUANDO = datetime(2026, 10, 16, 9, tzinfo=UTC)
VERSAO = "6a2b0c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7c"
EQUIPE = ["Fulana Exemplar", "Beltrano Fictício"]


def _lista(instancia: str, empresas: list[tuple[str, str]]) -> str:
    if not empresas:
        return (
            f'<div fs-list-instance="{instancia}" fs-list-element="wrapper" class="w-dyn-list">'
            '<div class="hide w-dyn-empty"><div>No items found.</div></div></div>'
        )
    itens = "".join(
        '<div role="listitem" class="w-dyn-item">'
        f'<a href="/transaction-company/{chave}" class="fs-template-link"></a>'
        f'<div class="card"><h3 class="transaction-card-company-title">{nome} </h3></div>'
        f'<div class="card vertical"><h3 class="transaction-card-company-title">{nome}</h3></div>'
        "</div>"
        for chave, nome in empresas
    )
    return (
        f'<div fs-list-instance="{instancia}" fs-list-element="wrapper" class="w-dyn-list">'
        f'<div role="list" class="w-dyn-items">{itens}</div></div>'
    )


def pagina(
    clientes: list[tuple[str, str]],
    contrapartes: list[tuple[str, str]] = (),  # type: ignore[assignment]
    paises: list[str] = ("Brazil",),  # type: ignore[assignment]
    equipe: list[str] = (),  # type: ignore[assignment]
) -> bytes:
    bandeiras = "".join(
        '<div role="listitem" class="w-dyn-item"><a href="/transactions-country/x"></a>'
        f'<div fs-list-field="country" class="hide">{p}</div></div>'
        for p in paises
    )
    pessoas = "".join(
        '<div role="listitem" class="w-dyn-item"><a href="/team/x"></a>'
        f"<h3>{nome}</h3></div>"
        for nome in equipe
    )
    return (
        "<!DOCTYPE html><html><head><title>Assessoria</title></head><body>"
        '<div class="global-embed"><!-- Sectors --></div>'
        '<div fs-list-instance="countries" fs-list-element="wrapper" class="w-dyn-list">'
        f'<div role="list" class="transaction-flags w-dyn-items">{bandeiras}</div></div>'
        '<div fs-list-instance="team" fs-list-element="wrapper" class="w-dyn-list">'
        f'<div role="list" class="w-dyn-items">{pessoas}</div></div>'
        + _lista("keywords", [])
        + _lista("advised-company", clientes)
        + _lista("advised-company-compact", clientes)
        + _lista("target-company", list(contrapartes))
        + _lista("target-company-compact", list(contrapartes))
        + "</body></html>"
    ).encode()


def extrair(slug: str, html: bytes) -> dict:
    return ma.extrair(html, SITE + slug, "a" * 64, QUANDO, "teste")


# --- regras do título -------------------------------------------------------------------------------
def test_foi_adquirida_pela():
    linha = extrair(
        "a-alfa-foi-adquirida-pela-beta",
        pagina([("alfa", "Alfa")], [("beta-x7k2p", "Beta")]),
    )
    assert linha["tipo"] == "AQ_CONTROLE"
    assert (linha["alvo"], linha["comprador"], linha["vendedor"]) == (
        "Alfa",
        "Beta",
        None,
    )
    assert linha["lado_da_assessoria"] == "venda"
    assert linha["papeis_por"] == "titulo"
    assert linha["conferencia"] == "assessoria"
    assert linha["coletado_em"] == QUANDO
    assert linha["url"] == SITE + "a-alfa-foi-adquirida-pela-beta"


def test_was_acquired_by_em_ingles():
    linha = extrair(
        "gama-was-acquired-by-delta-group",
        pagina([("gama", "Gama")], [("delta", "Delta Group")]),
    )
    assert (linha["tipo"], linha["alvo"], linha["comprador"]) == (
        "AQ_CONTROLE",
        "Gama",
        "Delta Group",
    )


@pytest.mark.parametrize(
    ("slug", "tipo"),
    [
        ("alfa-vendeu-participacao-minoritaria-para-a-beta", "AQ_MINORITARIA"),
        ("alfa-sold-a-minority-stake-to-beta", "AQ_MINORITARIA"),
        ("alfa-vendeu-participacao-majoritaria-para-o-beta", "AQ_CONTROLE"),
        ("alfa-secures-majority-investment-from-beta", "AQ_CONTROLE"),
        ("alfa-sold-an-equity-stake-to-beta", "desconhecido"),  # sem dizer quanto
        ("alfa-recebeu-investimento-da-beta", "PE_VC"),
        ("alfa-completed-its-series-a-round-led-by-beta", "PE_VC"),
    ],
)
def test_venda_de_participacao_e_investimento(slug, tipo):
    linha = extrair(slug, pagina([("alfa", "Alfa")], [("beta", "Beta")]))
    assert linha["tipo"] == tipo
    assert (linha["alvo"], linha["comprador"]) == ("Alfa", "Beta")
    assert linha["lado_da_assessoria"] == "venda"


def test_quem_compra_vem_antes_do_verbo():
    linha = extrair(
        "beta-adquiriu-participacao-minoritaria-na-alfa",
        pagina([("alfa", "Alfa")], [("beta", "Beta")]),
    )
    assert (linha["tipo"], linha["alvo"], linha["comprador"]) == (
        "AQ_MINORITARIA",
        "Alfa",
        "Beta",
    )


def test_assessoria_do_lado_de_quem_compra():
    linha = extrair(
        "beta-acquired-alfa", pagina([("beta", "Beta")], [("alfa", "Alfa")])
    )
    assert (linha["alvo"], linha["comprador"]) == ("Alfa", "Beta")
    assert linha["lado_da_assessoria"] == "compra"


def test_controladora_citada_vira_vendedor_ou_outra_parte():
    linha = extrair(
        "a-alfa-subsidiaria-da-omega-foi-adquirida-pela-beta-empresa-do-grupo-sigma",
        pagina(
            [("alfa", "Alfa"), ("omega", "Ômega")],
            [("beta", "Beta"), ("sigma", "Sigma")],
        ),
    )
    assert linha["alvo"] == "Alfa"
    assert linha["vendedor"] == "Ômega"
    assert linha["comprador"] == "Beta"
    assert linha["outras_partes"] == "Sigma"


def test_quem_vende_uma_empresa_que_nao_e_ela_mesma():
    linha = extrair(
        "grupo-omega-vendeu-alfa-para-beta",
        pagina([("alfa", "Alfa"), ("omega", "Grupo Ômega")], [("beta", "Beta")]),
    )
    assert (linha["alvo"], linha["vendedor"], linha["comprador"]) == (
        "Alfa",
        "Grupo Ômega",
        "Beta",
    )


def test_contraparte_fora_do_titulo_fica_em_outras_partes():
    linha = extrair(
        "alfa-was-acquired-by-beta",
        pagina([("alfa", "Alfa")], [("beta", "Beta"), ("fundo-kappa", "Fundo Kappa")]),
    )
    assert linha["comprador"] == "Beta"
    assert linha["outras_partes"] == "Fundo Kappa"


def test_nome_que_nao_aparece_no_titulo_usa_os_campos_da_pagina():
    """A página diz quem a assessoria assessorou e quem foi a contraparte; o título só diz o
    sentido. Sem casar nenhum nome, os papéis vêm da página, e a linha diz isso."""
    linha = extrair(
        "alfa-was-acquired-by-beta",
        pagina([("zeta-z9q1w", "Zeta")], [("eta", "Eta")]),
    )
    assert (linha["alvo"], linha["comprador"]) == ("Zeta", "Eta")
    assert linha["papeis_por"] == "pagina"


def test_comprou_100_por_cento_de_alguem_nao_e_controladora():
    linha = extrair(
        "beta-of-sigma-group-acquired-100-of-alfa-embalagens",
        pagina([("alfa", "Alfa")], [("beta", "Beta"), ("sigma", "Sigma")]),
    )
    assert (linha["alvo"], linha["comprador"], linha["vendedor"]) == (
        "Alfa",
        "Beta",
        None,
    )
    assert (
        linha["outras_partes"] == "Sigma"
    )  # "beta of sigma group": a controladora de quem compra


def test_equity_no_nome_do_investidor_nao_e_participacao():
    linha = extrair(
        "alfa-recebeu-investimento-do-one-equity-partners",
        pagina([("alfa", "Alfa")], [("one-equity-partners", "One Equity Partners")]),
    )
    assert linha["tipo"] == "PE_VC"


def test_venda_de_ativo():
    linha = extrair(
        "alfa-sold-its-switch-platform-to-beta",
        pagina([("alfa", "Alfa")], [("beta", "Beta")]),
    )
    assert linha["tipo"] == "VENDA_ATIVO"
    assert (linha["alvo"], linha["vendedor"], linha["comprador"]) == (
        None,
        "Alfa",
        "Beta",
    )
    assert linha["lado_da_assessoria"] == "venda"


def test_ativo_comprado_de_alguem():
    linha = extrair(
        "beta-acquired-the-x1-complex-from-laboratorio-alfa",
        pagina([("alfa", "Alfa")], [("beta", "Beta")]),
    )
    assert linha["tipo"] == "VENDA_ATIVO"
    assert (linha["vendedor"], linha["comprador"]) == ("Alfa", "Beta")


@pytest.mark.parametrize(
    ("slug", "tipo"),
    [
        ("alfa-e-beta-uniram-suas-operacoes", "FUSAO"),
        ("alfa-and-beta-merged-their-operations", "FUSAO"),
        ("alfa-e-beta-formaram-uma-joint-venture", "JV"),
        ("alfa-e-beta-firmaram-uma-alianca-estrategica", "JV"),
    ],
)
def test_fusao_e_joint_venture_nao_tem_alvo_nem_comprador(slug, tipo):
    linha = extrair(slug, pagina([("alfa", "Alfa")], [("beta", "Beta")]))
    assert linha["tipo"] == tipo
    assert (linha["alvo"], linha["comprador"]) == (None, None)
    assert (linha["cliente"], linha["contraparte"]) == ("Alfa", "Beta")
    assert linha["lado_da_assessoria"] == "parte"


@pytest.mark.parametrize(
    ("slug", "valor", "moeda"),
    [
        ("a-alfa-concluiu-a-emissao-de-um-cri-de-r-70-000-000-00", 70_000_000.0, "BRL"),
        (
            "alfa-concluiu-a-emissao-de-notas-comerciais-de-r-64-milhoes",
            64_000_000.0,
            "BRL",
        ),
        (
            "alfa-concluiu-emissao-de-debenture-no-valor-de-r-100-000-000",
            100_000_000.0,
            "BRL",
        ),
        ("alfa-conclui-estruturacao-de-fidc-proprio", None, None),
        (
            "alfa-concluiu-a-emissao-de-nota-comercial-de-r-50-000-000-00",
            50_000_000.0,
            "BRL",
        ),
    ],
)
def test_emissao_de_divida(slug, valor, moeda):
    linha = extrair(slug, pagina([("alfa", "Alfa")]))
    assert linha["tipo"] == "DCM"
    assert linha["lado_da_assessoria"] == "captacao"
    assert (linha["alvo"], linha["comprador"]) == (None, None)
    assert linha["cliente"] == "Alfa"
    assert linha["valor"] == valor
    assert linha["moeda"] == moeda


def test_emprestimo_nao_e_oferta_de_divida():
    linha = extrair(
        "alfa-captou-us-10-000-000-00-com-a-beta-em-linha-de-longo-prazo",
        pagina([("alfa", "Alfa")]),
    )
    assert linha["tipo"] == "desconhecido"
    assert (linha["valor"], linha["moeda"]) == (10_000_000.0, "USD")
    assert linha["lado_da_assessoria"] == "captacao"


def test_titulo_sem_verbo_fica_desconhecido_e_sem_papeis():
    linha = extrair("alfa", pagina([("alfa", "Alfa")], [("beta", "Beta")]))
    assert linha["tipo"] == "desconhecido"
    assert linha["regra"] is None
    assert (linha["alvo"], linha["comprador"], linha["lado_da_assessoria"]) == (
        None,
        None,
        None,
    )
    assert (linha["cliente"], linha["contraparte"]) == ("Alfa", "Beta")


# --- página, país e o que nunca entra -----------------------------------------------------------------
def test_paises_viram_codigos_e_o_desconhecido_fica_como_veio():
    linha = extrair(
        "alfa-foi-adquirida-pela-beta",
        pagina(
            [("alfa", "Alfa")],
            [("beta", "Beta")],
            ["Brazil", "United States", "Atlântida"],
        ),
    )
    assert linha["paises"] == "BR;US;Atlântida"


def test_pagina_sem_informacao_fica_vazia():
    linha = extrair("alfa-foi-adquirida-pela-beta", b"<html><body></body></html>")
    for coluna in (
        "alvo",
        "comprador",
        "vendedor",
        "cliente",
        "contraparte",
        "paises",
        "setor",
    ):
        assert linha[coluna] is None, coluna
    assert linha["tipo"] == "AQ_CONTROLE"  # o título diz; os nomes, não
    assert linha["papeis_por"] is None


def test_nenhuma_pessoa_fisica_entra():
    """A equipe da assessoria (lista `team`) nunca é lida, e o nome de uma pessoa citado só no
    título não vai para nenhuma coluna além do próprio endereço da página."""
    html = pagina(
        [("alfa", "Alfa")],
        [("beta", "Beta")],
        equipe=EQUIPE,
    )
    linha = extrair(
        "alfa-vende-seus-ativos-para-a-beta-e-fulano-de-tal-acionista", html
    )
    textos = [str(v) for k, v in linha.items() if k != "url" and v is not None]
    for nome in [*EQUIPE, "fulano", "Fulano"]:
        assert not any(nome in t for t in textos), nome


def test_nenhum_texto_longo_na_saida():
    longo = "Empresa " + "muito " * 80
    linha = extrair(
        "alfa-foi-adquirida-pela-beta", pagina([("alfa", longo)], [("beta", "Beta")])
    )
    assert all(
        len(str(v)) <= ma.LIMITE_DO_TEXTO for v in linha.values() if v is not None
    )


def test_tabela_tem_as_colunas_do_dicionario():
    linhas = [extrair("alfa-foi-adquirida-pela-beta", pagina([("alfa", "Alfa")]))]
    tabela = ma.tabela(linhas)
    assert list(tabela.columns) == list(ma.COLUNAS)
    assert set(TABELAS["ma_assessorias"].colunas) == set(ma.COLUNAS)
    assert ma.tabela([]).empty


# --- carga ------------------------------------------------------------------------------------------
PAGINAS = {
    "https://www.igcp.com.br/transactions/a-alfa-foi-adquirida-pela-beta": pagina(
        [("alfa", "Alfa")], [("beta", "Beta")], equipe=EQUIPE
    ),
    "https://www.igcp.com.br/transactions/gama-concluiu-a-emissao-de-um-cra-de-r-20-000-000-00": pagina(
        [("gama", "Gama")]
    ),
}


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    with criar_engine(url).begin() as c:
        for endereco, conteudo in PAGINAS.items():
            caminho = acervo.guardar_original(
                "assessoria-igc", endereco, conteudo, QUANDO
            )
            registrar(
                c,
                "assessoria-igc",
                endereco,
                conteudo,
                "ok",
                agora=QUANDO,
                caminho_do_original=caminho,
            )
    return tmp_path / "acervo" / "base"


def test_carga_grava_uma_linha_por_pagina_com_manifesto_e_linhagem(ambiente, capsys):
    from base.linhagem import linhagem_da_tabela

    assert carga.main(["--base", str(ambiente)]) == 0
    arquivo = ambiente / "ma" / "assessorias" / "igc.parquet"
    assert conferir_tabela(arquivo)
    manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    assert manifesto["versao_do_codigo"] == VERSAO
    with criar_engine().connect() as c:
        assert linhagem_da_tabela(c, arquivo).completa
    tabela = ler_tabela(arquivo)
    assert len(tabela) == 2
    assert set(tabela["tipo"]) == {"AQ_CONTROLE", "DCM"}
    assert (tabela["assessoria"] == "igc").all()
    assert pd.Timestamp(tabela["coletado_em"].iloc[0]) == pd.Timestamp(QUANDO)
    resumo = capsys.readouterr().out
    assert "2 negócios" in resumo
    antes = arquivo.with_suffix(".json").read_text(encoding="utf-8")
    carga.main(["--base", str(ambiente)])  # as mesmas páginas: nada muda
    assert arquivo.with_suffix(".json").read_text(encoding="utf-8") == antes


def test_carga_recusa_rodar_sem_a_versao_do_codigo(ambiente, monkeypatch):
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError):
        carga.main(["--base", str(ambiente)])
    assert not (ambiente / "ma").exists()
