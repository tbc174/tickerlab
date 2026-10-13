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
