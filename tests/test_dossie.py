"""A ficha do dossiê no app: ler, validar, cortar o ruído e virar seções do relatório (plano do
relatório-modelo, 17/10/2026, PR 1, tarefas 1 e 2).

Usa a ficha de exemplo da CPFL guardada em `dados_de_exemplo/dossie/` e cópias alteradas dela.
"""

import json
from pathlib import Path

import pytest

from src import dossie

EXEMPLO = dossie.FICHA_DE_EXEMPLO


def _gravar(tmp_path: Path, conteudo: object) -> Path:
    caminho = tmp_path / "ficha.json"
    caminho.write_text(
        conteudo if isinstance(conteudo, str) else json.dumps(conteudo),
        encoding="utf-8",
    )
    return caminho


def _bruta() -> dict:
    return json.loads(EXEMPLO.read_text(encoding="utf-8"))


# --- ler e validar -------------------------------------------------------------------------------


def test_le_a_ficha_de_exemplo() -> None:
    ficha = dossie.ler_ficha(EXEMPLO)
    assert ficha is not None
    assert ficha.cnpj == "02429144000193"
    assert ficha.empresa == "CPFL ENERGIA S.A."
    assert [s.chave for s in ficha.secoes] == [
        "auditor_e_controladas",
        "ofertas_e_fundos",
        "setor_regulado",
        "negocios",
    ]


def test_versao_de_esquema_desconhecida_nao_e_lida(tmp_path: Path) -> None:
    bruta = _bruta() | {"versao_do_esquema": 99}
    assert dossie.ler_ficha(_gravar(tmp_path, bruta)) is None


@pytest.mark.parametrize("conteudo", ["{nao é json", {"cnpj": "1"}, []])
def test_ficha_fora_do_esquema_nao_e_lida(tmp_path: Path, conteudo: object) -> None:
    assert dossie.ler_ficha(_gravar(tmp_path, conteudo)) is None


def test_ficha_que_nao_existe_nao_e_lida(tmp_path: Path) -> None:
    assert dossie.ler_ficha(tmp_path / "nao-existe.json") is None


# --- cortes de qualidade ---------------------------------------------------------------------------


def test_serie_de_agencia_sem_peso_sai_da_ficha() -> None:
    # 113 acessos de banda larga da CPFL Telecom em 2016 (0,0004% da Anatel): ruído, não setor
    ficha = dossie.cortar(dossie.ler_ficha(EXEMPLO))
    setor = next(s for s in ficha.secoes if s.chave == "setor_regulado")
    assert "anatel_banda_larga_fixa" not in setor.tabelas
    assert [i.chave for i in setor.itens] == ["aneel_consumidores"]
    assert "aneel_consumidores" in setor.tabelas


def test_entidades_ligadas_ficam_so_as_das_series_que_sobraram() -> None:
    ficha = dossie.cortar(dossie.ler_ficha(EXEMPLO))
    setor = next(s for s in ficha.secoes if s.chave == "setor_regulado")
    fontes = {linha["fonte"] for linha in setor.tabelas["entidades_ligadas"]}
    assert fontes == {"aneel-samp"}


def test_setor_sem_nenhuma_serie_com_peso_some(tmp_path: Path) -> None:
    bruta = _bruta()
    setor = next(s for s in bruta["secoes"] if s["chave"] == "setor_regulado")
    for linha in setor["tabelas"]["aneel_consumidores"]:
        linha["participacao"] = 0.00001
    ficha = dossie.cortar(dossie.ler_ficha(_gravar(tmp_path, bruta)))
    assert "setor_regulado" not in [s.chave for s in ficha.secoes]


# --- seções do relatório ---------------------------------------------------------------------------


def _secoes() -> dict:
    ficha = dossie.cortar(dossie.ler_ficha(EXEMPLO))
    return {s.chave: s for s in dossie.secoes_da_ficha(ficha)}


def test_secoes_tem_titulo_itens_escritos_e_a_fonte() -> None:
    secoes = _secoes()
    fundos = secoes["ofertas_e_fundos"]
    assert fundos.titulo == "Ofertas e fundos"
    itens = {i.chave: i for i in fundos.itens}
    assert itens["fundos_com_a_acao"].texto == "370"
    assert itens["fundos_com_a_acao"].base == "31/03/2026"
    assert itens["valor_nos_fundos"].texto == "R$ 495,2 mi"
    assert any(p.startswith("Fonte: ODbL") for p in fundos.paragrafos)


def test_numero_grande_que_nao_e_dinheiro_nao_vira_reais() -> None:
    setor = _secoes()["setor_regulado"]
    item = setor.itens[0]
    assert item.texto == "9.743.641"
    assert item.base == "dez/2025"
    linha = setor.tabelas["aneel_consumidores"][0]
    assert linha["Consumidores"] == "9.743.641"
    assert linha["Parte do total"] == "11,1%"


def test_data_do_fre_no_futuro_vira_ano_de_referencia() -> None:
    # o FRE de 2026 tem a data de referência 31/12/2026, depois do dia da ficha
    itens = {i.chave: i for i in _secoes()["auditor_e_controladas"].itens}
    assert itens["controladas"].base == "FRE de 2026"
    assert itens["auditor_desde"].texto == "01/01/2022"


def test_tabelas_saem_escritas_com_rotulos() -> None:
    secoes = _secoes()
    oferta = secoes["ofertas_e_fundos"].tabelas["ofertas"][0]
    assert oferta["Data"] == "09/09/2026"
    assert oferta["Valor registrado"] == "R$ 1,7 bi"
    mes = secoes["ofertas_e_fundos"].tabelas["fundos_por_mes"][-1]
    assert mes == {
        "Mês": "mar/2026",
        "Fundos": "370",
        "Valor nas carteiras": "R$ 495,2 mi",
    }
    troca = secoes["auditor_e_controladas"].tabelas["trocas_de_auditor"][0]
    assert troca["Anos com o anterior"] == "4,8"
    controlada = secoes["auditor_e_controladas"].tabelas["controladas"][-1]
    assert controlada["Participação"] == "30%"
    assert controlada["Controlada"] == "não"


def test_negocios_guardam_o_link_do_documento_na_cvm() -> None:
    negocios = _secoes()["negocios"]
    assert "link" not in negocios.tabelas["negocios"][0]
    ficha = dossie.cortar(dossie.ler_ficha(EXEMPLO))
    links = dossie.links_da_tabela(ficha, "negocios", "negocios")
    assert links[0].startswith("https://www.rad.cvm.gov.br/")
    assert len(links) == len(negocios.tabelas["negocios"])


def test_titulo_de_cada_tabela() -> None:
    assert (
        dossie.titulo_da_tabela("fundos_por_mes") == "Fundos com a empresa, mês a mês"
    )
    assert (
        dossie.titulo_da_tabela("aneel_consumidores")
        == "Consumidores atendidos pelas distribuidoras (ANEEL)"
    )
