"""Metodologia pública das notas, dos padrões e das fórmulas (série 2 da base de ML, PR 8; ADR 0033).

Os textos saem das mesmas constantes que os cálculos usam: mudou um limite no código, muda o texto
da página de metodologia (e o teste do site confere que a página está em dia)."""

import json

from src import metodologia_das_notas as m
from src import notas, notas_classicas, padroes, setores, valuation
from src.qualidade_texto import REGRAS


def _tudo() -> str:
    return json.dumps(m.como_dicionario(), ensure_ascii=False)


def test_padroes_citam_os_numeros_das_regras():
    texto = " ".join(m.PADROES)
    assert f"{setores.MINIMO_DE_EMPRESAS} empresas" in texto
    for regra in padroes.REGRAS_QUE_TIRAM_DO_PADRAO:
        assert REGRAS[regra].titulo.lower() in texto
    assert f"versão {padroes.VERSAO_DOS_PADROES}" in texto


def test_notas_citam_quintis_tercis_e_o_aviso_do_app():
    texto = " ".join(m.NOTAS)
    for limite in notas.LIMITES_DOS_QUINTIS:
        assert f"{limite}%" in texto
    assert f"{notas.TERCIL_BAIXO}%" in texto and f"{notas.TERCIL_ALTO}%" in texto
    assert " a ".join([notas.QUALIDADES[-1], notas.QUALIDADES[0]]) in texto
    assert f"{valuation.MINIMO_DE_ANOS} anos" in texto
    assert notas.AVISO in m.NOTAS


def test_toda_regra_de_direcao_dos_indicadores_aparece():
    nomes = {f.nome for f in m.INDICADORES_DAS_NOTAS}
    assert nomes == {nome for nome, _ in padroes.INDICADORES.values()}
    for item in m.INDICADORES_DAS_NOTAS:
        _, maior_e_melhor = next(
            v for v in padroes.INDICADORES.values() if v[0] == item.nome
        )
        assert item.direcao == (
            m.MAIOR_E_MELHOR if maior_e_melhor else m.MENOR_E_MELHOR
        )


def test_todo_grupo_de_setores_aparece():
    assert [g.nome for g in m.GRUPOS] == [nome for nome, _ in setores.GRUPOS.values()]


def test_formulas_das_notas_classicas_sao_as_do_calculo():
    conta = {f.nome: f for f in m.FORMULAS}
    assert conta["Altman Z''"].formula == notas_classicas.ALTMAN_FORMULA
    assert conta["Beneish M"].formula == notas_classicas.BENEISH_FORMULA
    assert conta["Piotroski F"].formula == notas_classicas.PIOTROSKI_FORMULA
    assert notas_classicas.ALTMAN_REFERENCIA in conta["Altman Z''"].leitura
    assert "2,6" in conta["Altman Z''"].leitura and "1,1" in conta["Altman Z''"].leitura
    assert "−1,78" in conta["Beneish M"].leitura


def test_formulas_cobrem_os_calculos_do_relatorio():
    nomes = {f.nome for f in m.FORMULAS}
    for esperado in (
        "DuPont",
        "Ciclo de caixa",
        "Caixa livre",
        "Capex / depreciação",
        "Cobertura de juros",
        "Crescimento composto",
        "P/L e P/VP",
        "DCF",
        "Valuation reverso",
    ):
        assert esperado in nomes, esperado


def test_nada_promete_nem_recomenda():
    texto = _tudo().lower()
    for proibida in (
        "compre",
        "venda a ação",
        "preço-alvo de",
        "garantid",
        "vai subir",
        "vai cair",
    ):
        assert proibida not in texto, proibida


def test_dicionario_e_json_serializavel_e_tem_a_ancora():
    dados = m.como_dicionario()
    assert dados["ancora"] == m.ANCORA_NO_SITE
    assert json.loads(_tudo()) == dados


def test_relatorio_da_empresa_aponta_para_a_secao_da_metodologia():
    from src.relatorio_empresa import _metodologia

    assert any(m.URL_NO_SITE in p for p in _metodologia().paragrafos)
