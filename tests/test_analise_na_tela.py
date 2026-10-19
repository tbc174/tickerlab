"""A análise escrita no relatório (PR B do ADR 0100): a nota que abre o número, o plano de quem vê,
a ficha que mudou e o relatório sem análise. A página, o PDF e a API leem o mesmo `Relatorio.analise`."""

import dataclasses
import json
from pathlib import Path

import pytest

from src import relatorio_empresa as re_
from src.analise_escrita import entrada as en
from src.analise_escrita import saida
from src.analise_escrita.exibicao import (
    AVISO_DA_ANALISE,
    PASTA_DAS_ANALISES_PADRAO,
    com_analise,
    pasta_das_analises,
)
from src.analise_escrita.montagem import FICHA_NOVA
from tests.ajudantes_da_analise import CORTE, PAR_DA_CPFL, entradas_da_cpfl


def entrada_do_lote() -> dict:
    """A entrada como o lote a exporta do banco: sem preço da ação (o app a remonta assim)."""
    sem_preco = dataclasses.replace(entradas_da_cpfl(), preco=None, fechamentos=None)
    sem_dossie = dataclasses.replace(sem_preco, dossie=None)
    return en.entrada_da_ficha(
        re_.montar(sem_preco, "pro"), CORTE, sem_dossie=re_.montar(sem_dossie, "pro")
    )


def _gabarito() -> dict:
    return json.loads((PAR_DA_CPFL / "gabarito.json").read_text(encoding="utf-8"))[
        "analise"
    ]


def _guardar(pasta: Path, publicavel: bool = True, hash_: str | None = None) -> None:
    entrada = entrada_do_lote()
    digitos = "".join(c for c in entrada["cnpj"] if c.isdigit())
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{digitos}.json").write_text(
        json.dumps(
            {
                "cnpj": entrada["cnpj"],
                "empresa": entrada["empresa"],
                "corte": CORTE.isoformat(),
                "hash_da_entrada_atual": hash_ or en.hash_da_entrada(entrada),
                "publicavel": publicavel,
                "analise": _gabarito(),
                "linhagem": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _relatorio(plano: str, pasta: Path) -> re_.Relatorio:
    entradas = entradas_da_cpfl()
    return com_analise(re_.montar(entradas, plano), entradas, plano, pasta)


def test_sem_arquivo_o_relatorio_fica_como_hoje(tmp_path):
    entradas = entradas_da_cpfl()
    base = re_.montar(entradas, "pro")
    assert com_analise(base, entradas, "pro", tmp_path) is base
    assert base.analise is None


def test_so_texto_aprovado_na_porta_3_vai_para_a_tela(tmp_path):
    _guardar(tmp_path, publicavel=False)
    assert _relatorio("pro", tmp_path).analise is None


def test_pro_ve_as_oito_partes_com_a_origem(tmp_path):
    _guardar(tmp_path)
    analise = _relatorio("pro", tmp_path).analise
    assert analise is not None
    assert [p.chave for p in analise.partes] == list(saida.PARTES)
    assert {p.origem for p in analise.partes} == {saida.ORIGEM_MODELO}
    assert analise.aviso == AVISO_DA_ANALISE
    assert "Não é recomendação de investimento" in analise.aviso


def test_a_nota_abre_nome_valor_medido_em_fonte_e_comparacao(tmp_path):
    _guardar(tmp_path)
    analise = _relatorio("pro", tmp_path).analise
    assert analise is not None
    por_id = {li["id"]: li for li in entrada_do_lote()["linhas"]}
    nota = next(
        (
            n
            for n in analise.notas
            if por_id[n.id]["tipo"] == "numero"
            and por_id[n.id].get("comparacao")
            and por_id[n.id].get("fonte")
        ),
        None,
    )
    assert nota is not None, "o gabarito cita ao menos um número com comparação"
    linha = por_id[nota.id]
    assert nota.nome == linha["nome"]
    assert nota.texto == linha["texto"]
    assert nota.medido_em == linha["medido_em"]
    assert nota.fonte == linha["fonte"]
    assert linha["comparacao"]["contra"] in nota.comparacao


def test_notas_numeradas_de_1_sem_repetir_o_mesmo_id(tmp_path):
    _guardar(tmp_path)
    analise = _relatorio("pro", tmp_path).analise
    assert analise is not None
    assert [n.numero for n in analise.notas] == list(range(1, len(analise.notas) + 1))
    assert len({n.id for n in analise.notas}) == len(analise.notas)
    por_numero = {n.numero for n in analise.notas}
    usados = {
        n
        for parte in analise.partes
        for par in parte.paragrafos
        for frase in par.frases
        for n in frase.notas
    }
    assert usados == por_numero  # toda nota numerada aparece em alguma frase


def test_leitura_tem_rotulo_e_fato_nao(tmp_path):
    _guardar(tmp_path)
    analise = _relatorio("pro", tmp_path).analise
    assert analise is not None
    paragrafos = [par for p in analise.partes for par in p.paragrafos]
    assert {par.rotulo for par in paragrafos if par.tipo == saida.LEITURA} == {
        "Leitura"
    }
    assert {par.rotulo for par in paragrafos if par.tipo == saida.FATO} == {""}


def test_quem_nao_e_pro_nao_ve_parte_que_cita_o_dossie(tmp_path):
    _guardar(tmp_path)
    entrada = entrada_do_lote()
    dossie = {li["id"] for li in entrada["linhas"] if li["so_pro"]}
    obrigatorias = set(entrada["obrigatorias"])
    pro = _relatorio("pro", tmp_path).analise
    gratis = _relatorio("gratuito", tmp_path).analise
    assert pro is not None and gratis is not None
    assert {p.origem for p in pro.partes} == {saida.ORIGEM_MODELO}
    assert saida.ORIGEM_MOLDE in {p.origem for p in gratis.partes}
    ids_do_gratis = {n.id for n in gratis.notas}
    assert not (ids_do_gratis & (dossie - obrigatorias))


def test_ficha_nova_mostra_o_molde_e_diz_que_esta_sendo_reescrita(tmp_path):
    _guardar(tmp_path, hash_="0" * 64)
    analise = _relatorio("pro", tmp_path).analise
    assert analise is not None
    assert {p.origem for p in analise.partes} == {saida.ORIGEM_MOLDE}
    assert analise.motivo == FICHA_NOVA


def test_arquivo_ilegivel_nao_derruba_o_relatorio(tmp_path):
    _guardar(tmp_path)
    for arquivo in tmp_path.glob("*.json"):
        arquivo.write_text("{não é json", encoding="utf-8")
    assert _relatorio("pro", tmp_path).analise is None


def test_pagina_pdf_e_api_leem_a_mesma_analise(tmp_path):
    from src.api_v1 import esquemas

    _guardar(tmp_path)
    relatorio = _relatorio("pro", tmp_path)
    api = esquemas.de_relatorio_da_empresa(relatorio)
    assert api.analise is not None and relatorio.analise is not None
    assert [p.chave for p in api.analise.partes] == [
        p.chave for p in relatorio.analise.partes
    ]
    assert [n.id for n in api.analise.notas] == [n.id for n in relatorio.analise.notas]
    assert api.analise.aviso == relatorio.analise.aviso


def test_a_pasta_vem_do_ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("TICKERLAB_ANALISES", str(tmp_path))
    assert pasta_das_analises() == tmp_path
    monkeypatch.delenv("TICKERLAB_ANALISES")
    assert pasta_das_analises() == PASTA_DAS_ANALISES_PADRAO


@pytest.mark.parametrize("plano", ["pro", "gratuito"])
def test_relatorio_sem_analise_serializa_como_antes(plano):
    entradas = entradas_da_cpfl()
    assert re_.montar(entradas, plano).como_dict()["analise"] is None


def _texto_do_pdf(pdf: bytes) -> str:
    from io import BytesIO

    from pypdf import PdfReader

    return "".join(
        "".join(p.extract_text().split()) for p in PdfReader(BytesIO(pdf)).pages
    )


def test_pdf_traz_a_analise_antes_da_ficha_com_as_notas_por_parte(tmp_path):
    from src.relatorio_empresa_pdf import relatorio_da_empresa

    _guardar(tmp_path)
    relatorio = _relatorio("pro", tmp_path)
    assert relatorio.analise is not None
    texto = _texto_do_pdf(relatorio_da_empresa(relatorio))
    primeira = relatorio.analise.partes[0]
    assert "".join(primeira.titulo.split()) in texto
    assert "[1]" in texto
    nota = relatorio.analise.notas[0]
    assert "".join(nota.nome.split()) in texto
    assert texto.index("Aanálise") < texto.index("".join(re_.SECOES["limites"].split()))
    assert "Nãoérecomendaçãodeinvestimento" in texto


def test_pdf_sem_analise_fica_como_antes(tmp_path):
    from src.relatorio_empresa_pdf import relatorio_da_empresa

    entradas = entradas_da_cpfl()
    texto = _texto_do_pdf(relatorio_da_empresa(re_.montar(entradas, "pro")))
    assert "Aanálise" not in texto
    assert (
        "".join(re_.SECOES["limites"].split()) in texto
    )  # "Limites e cuidados" continua


def _tela_da_analise():
    import os
    from pathlib import Path

    from src import relatorio_empresa as re_
    from src.analise_escrita.exibicao import com_analise
    from telas.research.relatorio_empresa import _mostrar_analise
    from tests.ajudantes_da_analise import entradas_da_cpfl

    entradas = entradas_da_cpfl()
    relatorio = com_analise(
        re_.montar(entradas, "pro"), entradas, "pro", Path(os.environ["PASTA_DO_TESTE"])
    )
    assert relatorio.analise is not None
    _mostrar_analise(relatorio.analise)


def test_tela_mostra_as_partes_a_nota_numerada_e_as_notas_abertas(
    monkeypatch, tmp_path
):
    from streamlit.testing.v1 import AppTest

    _guardar(tmp_path)
    monkeypatch.setenv("PASTA_DO_TESTE", str(tmp_path))
    app = AppTest.from_function(_tela_da_analise, default_timeout=120).run()
    assert not app.exception
    assert [s.value for s in app.subheader] == [saida.TITULOS[c] for c in saida.PARTES]
    assert [h.value for h in app.header] == ["A análise", "Os dados"]
    texto = " ".join(m.value for m in app.markdown)
    assert "[1]" in texto
    assert "**Leitura:**" in texto
    assert any("Notas desta parte" in e.label for e in app.expander)
    assert AVISO_DA_ANALISE in [c.value for c in app.caption]


def test_notas_seguidas_viram_faixa_na_marca_da_frase():
    from src.analise_escrita.modelo_da_tela import FraseDaTela

    assert FraseDaTela("Texto.", (1, 2, 3, 4, 7)).com_marcas() == "Texto. [1–4, 7]"
    assert FraseDaTela("Texto.", (5, 6)).com_marcas() == "Texto. [5, 6]"
    assert FraseDaTela("Texto.", ()).com_marcas() == "Texto."
