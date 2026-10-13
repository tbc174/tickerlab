"""O conteúdo que o site em React lê (web/conteudo/*.json) vem do Python e não pode ficar velho."""

import json

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
