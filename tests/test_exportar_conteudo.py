"""O conteúdo que o site em React lê (web/conteudo/*.json) vem do Python e não pode ficar velho."""

import json
import re

from base.contrato import PASTA
from scripts import exportar_conteudo as exp
from src import marca, modulos, planos


def test_o_conteudo_do_site_esta_em_dia():
    """Mudou um módulo, um plano, uma página ou a marca? Rode `python -m scripts.exportar_conteudo`."""
    for nome, dados in exp.conteudo().items():
        arquivo = exp.DESTINO / f"{nome}.json"
        assert arquivo.exists(), f"falta {arquivo.name}"
        assert json.loads(arquivo.read_text(encoding="utf-8")) == json.loads(
            exp.em_json(dados)
        ), f"{arquivo.name} está velho"


def test_modulos_levam_o_que_o_site_mostra():
    exportados = exp.conteudo()["modulos"]
    assert [m["chave"] for m in exportados] == [m.chave for m in modulos.MODULOS]
    primeira = exportados[0]["funcionalidades"][0]
    original = modulos.MODULOS[0].funcionalidades[0]
    assert primeira == {
        "nome": original.nome,
        "descricao": original.descricao,
        "pagina_do_app": original.pagina_do_app,
        "pagina_do_site": original.pagina_do_site,
        "ticker": original.ticker,
        "disponivel": original.disponivel,
    }


def test_marca_leva_as_duas_paletas_e_o_simbolo():
    m = exp.conteudo()["marca"]
    assert m["paleta_clara"]["fundo"] == marca.PALETA_CLARA.fundo
    assert m["paleta_escura"]["texto"] == marca.PALETA_ESCURA.texto
    assert m["simbolo_svg"] == marca.simbolo_svg(topo="currentColor")
    assert m["fonte"] == marca.FONTE


def test_planos_levam_a_tabela_e_quem_ja_cobra():
    p = exp.conteudo()["planos"]
    assert p["tabela"] == planos.tabela_de_planos()
    assert p["com_cobranca"] == list(planos.COM_COBRANCA)


def test_json_estavel_para_o_diff_ficar_limpo():
    """Mesma entrada, mesmo texto: chaves em ordem fixa e acentos legíveis."""
    texto = exp.em_json({"b": "ação", "a": 1})
    assert texto == '{\n  "a": 1,\n  "b": "ação"\n}\n'


def test_marca_leva_as_cores_do_site_nos_dois_temas():
    m = exp.conteudo()["marca"]
    assert m["site_claro"] == [list(par) for par in marca.SITE_CLARO.items()]
    assert m["site_escuro"] == [list(par) for par in marca.SITE_ESCURO.items()]
    assert m["site_faixa_marinha"] == [
        list(par) for par in marca.SITE_FAIXA_MARINHA.items()
    ]


def test_site_leva_os_estilos_do_relatorio_e_os_exemplos():
    from src import catalogo
    from src.estilos_pdf import ESTILOS

    site = exp.conteudo()["site"]
    assert [e["chave"] for e in site["estilos_do_relatorio"]] == list(ESTILOS)
    assert site["estilos_do_relatorio"][0]["nome"] == next(iter(ESTILOS.values())).nome
    assert [e["simbolo"] for e in site["exemplos"]] == list(catalogo.EXEMPLOS)
    assert site["exemplos"][0]["rotulo"] == catalogo.rotulo("PETR4.SA").split(" · ")[0]


def test_planos_levam_os_nomes_para_a_tabela_e_a_cobranca():
    p = exp.conteudo()["planos"]
    assert p["nomes"] == [planos.limites_do(x).nome for x in planos.PLANOS]
    assert p["nomes_com_cobranca"] == [
        planos.limites_do(x).nome for x in planos.COM_COBRANCA
    ]
    assert p["nomes_em_breve"] == [
        planos.limites_do(x).nome
        for x in planos.PLANOS
        if x != "gratuito" and x not in planos.COM_COBRANCA
    ]


def test_textos_legais_vao_em_html_sem_o_titulo_do_arquivo():
    from scripts.markdown_simples import markdown_para_html

    legais = exp.conteudo()["legal"]
    assert set(legais) == {"termos", "privacidade"}
    bruto = (exp.RAIZ / "conteudo" / "termos.md").read_text(encoding="utf-8")
    sem_titulo = bruto.split("\n", 1)[1]  # o título do arquivo vira o h1 da página
    assert legais["termos"] == markdown_para_html(sem_titulo)


def test_qualidade_leva_os_mesmos_textos_do_app():
    from src import qualidade_texto as q

    exportado = exp.conteudo()["qualidade"]
    assert exportado["titulo_do_selo"] == q.TITULO_DO_SELO
    assert exportado["ancora"] == q.ANCORA_NO_SITE
    assert exportado["explicacao"] == q.EXPLICACAO_DO_SELO
    assert exportado["regras"] == [
        {"titulo": r.titulo, "o_que_confere": r.o_que_confere}
        for r in q.REGRAS.values()
    ]


def test_paginas_levam_o_contrato_para_a_tela_nova():
    """O app em React monta as rotas e os campos a partir do contrato de cada página."""
    from src.paginas import POR_CHAVE

    paginas_em_json = json.loads(exp.em_json(exp.conteudo()["paginas"]))
    exportadas = {p["chave"]: p for p in paginas_em_json}
    visao = exportadas["visao_geral"]["contrato"]
    original = POR_CHAVE["visao_geral"].contrato
    assert original is not None
    assert visao["rota"] == original.rota and visao["metodo"] == original.metodo
    assert visao["resposta"] == original.resposta
    assert [e["nome"] for e in visao["entradas"]] == [e.nome for e in original.entradas]
    assert visao["entradas"][1]["opcoes"] == list(original.entradas[1].opcoes)
    assert exportadas["inicio"]["contrato"] is None


def test_paginas_e_areas_levam_a_area_para_o_menu_do_app_novo():
    """O menu por áreas do React (ADR 0096) lê a área de cada página e a ordem de cada área daqui."""
    from src.paginas import AREAS, POR_CHAVE, paginas_da_area

    exportadas = {
        p["chave"]: p for p in json.loads(exp.em_json(exp.conteudo()["paginas"]))
    }
    for chave, p in exportadas.items():
        assert p["area"] == POR_CHAVE[chave].area
    areas = json.loads(exp.em_json(exp.conteudo()["app"]))["areas"]
    assert [a["chave"] for a in areas] == list(AREAS)
    ativo = next(a for a in areas if a["chave"] == "ativo")
    assert (
        ativo["rotulo"] == AREAS["ativo"].rotulo
        and ativo["frase"] == AREAS["ativo"].frase
    )
    assert ativo["paginas"] == [p.chave for p in paginas_da_area("ativo")]
    conta = next(a for a in areas if a["chave"] == "conta")
    assert (
        "admin" not in conta["paginas"]
    )  # o catálogo da administração fica fora do bundle


def test_paginas_de_admin_ficam_fora_do_bundle_publico():
    """O catálogo da administração não vai no JavaScript público (a tela é só do Streamlit)."""
    from src.paginas import PAGINAS

    assert any(p.somente_admin for p in PAGINAS)  # o teste só vale enquanto existir uma
    texto = exp.em_json(exp.conteudo()["paginas"])
    assert '"somente_admin": true' not in texto
    assert "registro de ações de administrador" not in texto


def test_app_leva_o_painel_e_as_ajudas_sem_markdown():
    """A visão geral em React: os itens do painel, na ordem da tela, e o "?" de cada um em partes."""
    from src import analises

    app = json.loads(exp.em_json(exp.conteudo()["app"]))
    assert [i["campo"] for i in app["painel"]["itens"]] == [
        i.campo for i in analises.ITENS_DO_PAINEL
    ]
    ajuda = app["glossario"]["Drawdown"]
    assert ajuda[0]["rotulo"] == "O que é"
    assert ajuda[0]["texto"].startswith("a queda desde o ponto mais alto")
    assert "drawdown máximo" in ajuda[0]["texto"]  # *itálico* sem os asteriscos
    textos = json.dumps(app["glossario"], ensure_ascii=False)
    assert "*" not in textos
    assert {i.termo for i in analises.ITENS_DO_PAINEL} <= set(app["glossario"])


def test_app_leva_risco_retorno_mensal_e_comparacao():
    from src import analises, comparacao
    from src import indicadores as ind

    app = json.loads(exp.em_json(exp.conteudo()["app"]))
    assert app["retorno_mensal"]["meses"] == list(ind.NOMES_DOS_MESES)
    assert app["retorno_mensal"]["legenda"] == analises.LEGENDA_DO_MAPA_MENSAL
    atalhos = {a["nome"]: a["ticker"] for a in app["comparacao"]["atalhos"]}
    assert atalhos == comparacao.ATALHOS
    assert app["comparacao"]["max_ativos"] == comparacao.MAX_ATIVOS
    assert {"Volatilidade móvel", "Sazonalidade", "Base 100"} <= set(app["glossario"])


def test_app_leva_as_estrategias_e_os_formatos_das_metricas():
    from src import formatos
    from src.estrategias import ESTRATEGIAS

    app = json.loads(exp.em_json(exp.conteudo()["app"]))
    estrategias = app["backtest"]["estrategias"]
    assert [e["nome"] for e in estrategias] == list(ESTRATEGIAS)
    medias = next(e for e in estrategias if e["nome"] == "Cruzamento de médias")
    curta = medias["parametros"][0]
    assert (curta["nome"], curta["padrao"], curta["minimo"], curta["maximo"]) == (
        "curta",
        20,
        5,
        100,
    )
    por_formato = app["backtest"]["metricas_por_formato"]
    assert set(por_formato["inteiro"]) == formatos.METRICAS_INTEIRAS


def test_formatacao_leva_os_casos_do_python():
    from src import formatos

    assert exp.conteudo()["formatacao"] == formatos.casos_de_formatacao()


def test_app_leva_os_textos_de_juros_e_da_linha_do_tempo():
    from src import juros_e_inflacao as ji
    from src import linha_do_tempo as ldt

    app = json.loads(exp.em_json(exp.conteudo()["app"]))
    assert app["juros"]["termos"] == ji.TERMO_DO_GLOSSARIO
    assert app["juros"]["nota_do_focus"] == ji.NOTA_DO_FOCUS
    assert set(ji.TERMO_DO_GLOSSARIO.values()) | {"Boletim Focus"} <= set(
        app["glossario"]
    )
    assert app["linha_do_tempo"]["relevancias"] == [
        {"nome": n, "valor": v} for n, v in ldt.RELEVANCIAS.items()
    ]
    assert app["linha_do_tempo"]["padrao"] == ldt.MATERIALIDADE_PADRAO


def _pagina_do_pdf_de_exemplo(numero: int) -> str:
    """O texto de uma página do PDF de exemplo que o site oferece (site/relatorio/)."""
    import pypdfium2

    from scripts import gerar_site as gs

    caminho = gs.DESTINO / "relatorio" / f"exemplo-{gs.TICKER_DO_EXEMPLO}.pdf"
    documento = pypdfium2.PdfDocument(caminho.read_bytes())
    try:
        return (
            documento[numero - 1].get_textpage().get_text_range().replace("\r\n", "\n")
        )
    finally:
        documento.close()


def test_painel_do_site_tem_os_mesmos_numeros_do_pdf_de_exemplo():
    """ADR 0065, item 4: o número do hero sai do mesmo cálculo do relatório, nunca escrito à mão."""
    painel = exp.painel_de_exemplo()
    numeros_chave = _pagina_do_pdf_de_exemplo(2)
    rotulos_no_pdf = {
        "retorno_total": "Retorno total",
        "retorno_ao_ano": "Retorno anualizado",
        "volatilidade": "Volatilidade anual",
        "maior_queda": "Maior queda",
        "sharpe": "Índice de Sharpe",
    }
    for chave, rotulo in rotulos_no_pdf.items():
        assert f"{rotulo}\n{painel[chave]['texto']}\n" in numeros_chave, chave
    assert painel["retorno_total"]["texto"].startswith("▲")  # a seta vai junto da cor
    assert painel["maior_queda"]["valor"] < 0


def test_painel_do_site_leva_o_periodo_e_a_serie_em_base_100():
    from scripts import gerar_site as gs

    painel = exp.painel_de_exemplo()
    dados = gs.dados_de_exemplo(gs.TICKER_DO_EXEMPLO)
    assert painel["ticker"] == gs.TICKER_DO_EXEMPLO
    assert painel["inicio"] == f"{dados.index[0]:%Y-%m-%d}"
    assert painel["fim"] == f"{dados.index[-1]:%Y-%m-%d}"
    serie = painel["serie"]
    assert len(serie) == 64
    assert serie[0] == 100
    # o último ponto é o retorno total: 100 × (1 + retorno)
    assert abs(serie[-1] - 100 * (1 + painel["retorno_total"]["valor"])) < 0.1


def test_painel_vai_para_o_site_no_exemplo_json():
    assert exp.conteudo()["exemplo"] == exp.painel_de_exemplo()


def test_site_leva_a_fita_e_o_total_de_ativos_da_busca():
    """A fita da página inicial: código do catálogo e um nome curto, nenhum preço (ADR 0065)."""
    from src import catalogo

    site = exp.conteudo()["site"]
    tabela = catalogo.carregar()
    assert site["total_de_ativos"] == len(tabela)
    assert len(site["fita"]) >= 10
    for item in site["fita"]:
        assert set(item) == {"simbolo", "codigo", "nome"}
        assert item["codigo"] == tabela.loc[item["simbolo"], "codigo"]


def test_catalogo_do_site_vem_do_contrato():
    """A página Dados conta as tabelas e as fontes do `catalogo.json`; nada é digitado à mão."""
    contrato = json.loads((PASTA / "catalogo.json").read_text(encoding="utf-8"))[
        "tabelas"
    ]
    catalogo = exp.conteudo()["catalogo"]

    assert catalogo["totais"]["tabelas"] == len(contrato) == len(catalogo["tabelas"])
    assert catalogo["totais"]["fontes"] == len(
        {t["licenca"] for t in contrato.values()}
    )
    assert catalogo["totais"]["fontes"] == len(catalogo["fontes"])
    assert catalogo["totais"]["modulos"] == len(catalogo["modulos"])
    assert sum(m["tabelas"] for m in catalogo["modulos"]) == len(contrato)
    assert catalogo["totais"]["fontes_em_consulta"] == sum(
        f["situacao"] == "em consulta" for f in catalogo["fontes"]
    )
    for linha in catalogo["tabelas"]:
        assert linha["modulo"] and linha["frase"] and linha["orgao"]
        assert linha["frequencia"] and linha["historico_desde"]
        assert linha["situacao"] in ("licenciada", "em consulta")


def test_catalogo_do_site_nao_leva_conversa_interna():
    """Servidor, ADR, código e passo de PR ficam no repositório; o site aberto lê só o resultado."""
    catalogo = exp.conteudo()["catalogo"]
    for t in catalogo["tabelas"]:
        for texto in (t["frase"], t["atraso"] or "", t["frequencia"]):
            assert not re.search(r"servidor|VPS|arquivista|`|bADRb|\w+/\w+\.py", texto), (
                texto
            )
        assert t["frase"].endswith((".", "…"))
        assert t["frase"].count("(") == t["frase"].count(")"), t["frase"]
