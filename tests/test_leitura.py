"""Leitura dos documentos (Research R5): o algoritmo próprio, sem IA, com textos de exemplo."""

from fpdf import FPDF

from src import leitura

FATO = """
COMPANHIA EXEMPLO S.A.
CNPJ nº 00.000.000/0001-00
FATO RELEVANTE
A Companhia Exemplo S.A., em atendimento ao disposto na Resolução CVM nº 44, comunica aos seus
acionistas e ao mercado em geral o que segue. O Conselho de Administração aprovou hoje a aquisição
de 100% da Fábrica Modelo Ltda. por R$ 1,2 bilhão, pagos em dinheiro na data do fechamento. A
aquisição dobra a capacidade de produção da Companhia e deve ser concluída em até seis meses, depois
da aprovação do CADE. A operação será paga com caixa próprio e com a emissão de debêntures no valor
de R$ 500 milhões. A Companhia manterá o mercado informado sobre o andamento da operação, nos termos
da regulamentação aplicável.
São Paulo, 12 de outubro de 2026.
Maria Exemplo
Diretora Financeira e de Relações com Investidores
"""


def test_frases_nao_quebram_nas_abreviacoes():
    texto = "A Companhia Exemplo S.A. aprovou o art. 5 do estatuto hoje cedo. Outra frase com seis palavras aqui."
    assert leitura.dividir_em_frases(texto) == [
        "A Companhia Exemplo S.A. aprovou o art. 5 do estatuto hoje cedo.",
        "Outra frase com seis palavras aqui.",
    ]


def test_abreviacao_so_vale_como_palavra_inteira():
    """ "start." termina em "art.", mas é fim de frase."""
    texto = "The project had a very slow start. Then revenue grew much faster than expected."
    assert len(leitura.dividir_em_frases(texto)) == 2


def test_frases_curtas_ficam_de_fora():
    assert leitura.dividir_em_frases(
        "Curta demais. Esta aqui tem palavras suficientes para contar."
    ) == ["Esta aqui tem palavras suficientes para contar."]


def test_resumo_traz_o_fato_e_nao_o_juridiques():
    resumo = leitura.resumir_fato_relevante(FATO)
    assert len(resumo.frases) == leitura.FRASES_DO_RESUMO
    assert any("aquisição de 100%" in f for f in resumo.frases)
    assert not any("em atendimento ao disposto" in f for f in resumo.frases)
    assert not any("manterá o mercado" in f for f in resumo.frases)


def test_resumo_mantem_a_ordem_original_e_nao_reescreve():
    resumo = leitura.resumir_fato_relevante(FATO)
    corpo = " ".join(FATO.split())
    posicoes = [
        corpo.index(frase) for frase in resumo.frases
    ]  # cada frase existe igual no texto
    assert posicoes == sorted(posicoes)


def test_resumo_tira_cabecalho_e_assinatura():
    resumo = leitura.resumir_fato_relevante(FATO)
    assert not any("CNPJ" in f or "Maria Exemplo" in f for f in resumo.frases)


def test_numeros_e_assuntos():
    resumo = leitura.resumir_fato_relevante(FATO)
    assert "R$ 1,2 bilhão" in resumo.numeros
    assert "R$ 500 milhões" in resumo.numeros
    assert "100%" in resumo.numeros
    assert resumo.assuntos[0] == "Aquisição, venda ou fusão"
    assert "Dívida e captação" in resumo.assuntos


def test_resumo_guarda_a_versao_do_algoritmo():
    guardado = leitura.resumir_fato_relevante(FATO).para_guardar()
    assert guardado["versao"] == leitura.VERSAO
    assert set(guardado) == {"frases", "numeros", "assuntos", "palavras", "versao"}


def test_frase_longa_e_cortada():
    frase = " ".join(["palavra"] * (leitura.MAX_PALAVRAS_POR_FRASE + 10))
    cortada = leitura._cortar(frase)
    assert cortada.endswith("(...)")
    assert len(cortada.split()) == leitura.MAX_PALAVRAS_POR_FRASE + 1


# --- 10-K ---------------------------------------------------------------------------------------
RISCOS_ANTES = [
    f"Our business depends on demand for consumer electronics in market number {i}, which may "
    f"decline because of economic conditions, competition and pricing pressure in region {i}."
    for i in range(30)
]


def _10k(riscos: list[str]) -> str:
    """Um 10-K mínimo: sumário (com o título curto), a seção 1A e o item seguinte."""
    paragrafos = "".join(f"<p>{frase}</p>" for frase in riscos)
    return (
        "<html><body><ix:header><p>Item 1A. Risk Factors dado oculto</p></ix:header>"
        "<table><tr><td>Item 1A. Risk Factors</td><td>12</td></tr>"
        "<tr><td>Item 1B. Unresolved Staff Comments</td><td>20</td></tr></table>"
        "<script>var x = 'Item 1A. Risk Factors';</script>"
        f"<h2>Item 1A. Risk Factors</h2>{paragrafos}"
        "<h2>Item 1B. Unresolved Staff Comments</h2><p>None.</p>"
        "<h2>Item 2. Properties</h2><p>Offices.</p></body></html>"
    )


def test_acha_a_secao_de_riscos_e_nao_o_sumario():
    secao = leitura.fatores_de_risco(_10k(RISCOS_ANTES))
    assert secao is not None
    assert secao.startswith("Item 1A. Risk Factors Our business depends")
    assert "Unresolved" not in secao and "var x" not in secao


def test_secao_curta_ou_ausente_vira_none():
    assert leitura.fatores_de_risco(_10k(RISCOS_ANTES[:2])) is None
    assert leitura.fatores_de_risco("<html><p>Sem a seção.</p></html>") is None


def test_textos_iguais():
    secao = leitura.fatores_de_risco(_10k(RISCOS_ANTES))
    mudanca = leitura.comparar_riscos(secao, secao)
    assert mudanca.semelhanca == 1.0
    assert mudanca.frases_novas == () and mudanca.novas_no_total == 0
    assert mudanca.palavras_em_alta == ()


def test_risco_novo_aparece():
    novo = (
        "Tariffs imposed on imported semiconductors could materially increase our tariffs costs, "
        "and further tariffs and export restrictions may disrupt our tariffs exposed supply chain."
    )
    antes = leitura.fatores_de_risco(_10k(RISCOS_ANTES))
    agora = leitura.fatores_de_risco(_10k([*RISCOS_ANTES, novo]))
    mudanca = leitura.comparar_riscos(antes, agora)
    assert 0.8 < mudanca.semelhanca < 1.0
    assert mudanca.novas_no_total == 1
    assert mudanca.frases_novas == (novo,)
    assert mudanca.palavras_agora > mudanca.palavras_antes
    palavra, vezes_antes, vezes_agora = mudanca.palavras_em_alta[0]
    assert (palavra, vezes_antes, vezes_agora) == ("tariffs", 0, 4)


def test_frase_pouco_editada_nao_conta_como_nova():
    antes = leitura.fatores_de_risco(_10k(RISCOS_ANTES))
    editados = [*RISCOS_ANTES]
    editados[0] = editados[0].replace("may decline", "could decline")
    agora = leitura.fatores_de_risco(_10k(editados))
    assert leitura.comparar_riscos(antes, agora).novas_no_total == 0


def test_comparacao_guarda_listas():
    secao = leitura.fatores_de_risco(_10k(RISCOS_ANTES))
    guardado = leitura.comparar_riscos(secao, secao).para_guardar()
    assert guardado["versao"] == leitura.VERSAO
    assert isinstance(guardado["palavras_em_alta"], list)


# --- PDF ----------------------------------------------------------------------------------------
def _pdf(texto: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=11)
    pdf.multi_cell(0, 6, texto)
    return bytes(pdf.output())


def test_texto_do_pdf():
    conteudo = _pdf("Fato relevante: a Companhia aprovou a recompra de ações.")
    assert leitura.e_pdf(conteudo)
    assert "recompra de ações" in leitura.texto_do_pdf(conteudo)


def test_pagina_de_aviso_nao_e_pdf():
    assert not leitura.e_pdf(b"<html>Limite de downloads atingido</html>")
    assert not leitura.e_pdf(_pdf("cortado")[:200])  # PDF pela metade
