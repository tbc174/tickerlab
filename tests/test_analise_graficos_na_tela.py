"""Os gráficos escolhidos pela IA no relatório (plano de 23/10/2026, PR 3).

A escolha do modelo é publicada junto do texto (`graficos` no arquivo da análise) e só vale para a
mesma ficha e o mesmo texto; fora disso, ou reprovada na porta 1, entra a reserva por regras. Quem
não é Pro não vê gráfico nem destaque do dossiê. A página, o PDF e a API leem o mesmo
`Relatorio.analise`.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from src import relatorio_empresa as re_
from src.analise_escrita import entrada as en
from src.analise_escrita import graficos as gr
from src.analise_escrita import reserva_dos_graficos as rg
from src.analise_escrita import saida, series
from src.analise_escrita.exibicao import CAMPO_DOS_GRAFICOS, com_analise
from src.analise_escrita.modelo_da_tela import AnaliseDaTela
from tests.ajudantes_da_analise import CORTE, PAR_DA_CPFL, entradas_da_cpfl
from tests.test_analise_na_tela import entrada_do_lote

PARTE = "o_que_os_numeros_mostram"
MARGEM = {
    "tipo": "barras_no_tempo",
    "tabela": "series.margens",
    "eixo": "Ano",
    "colunas": ["Margem líquida"],
    "titulo": "Margem líquida por ano",
    "parte": PARTE,
    "paragrafo": 1,
    "por_que": {
        "texto": "A margem líquida foi de 13,5% em 2024 e de 12,9% em 2025.",
        "notas": ["series.margens.0", "series.margens.1"],
    },
}
CONSUMIDORES = {  # tabela do dossiê: só o Pro vê
    "tipo": "linha_no_tempo",
    "tabela": "setor_regulado.aneel_consumidores",
    "eixo": "Ano",
    "colunas": ["Consumidores"],
    "titulo": "Consumidores das distribuidoras",
    "parte": "o_que_e",
    "paragrafo": 1,
    "por_que": {
        "texto": "Os consumidores foram de 9.095.518 em 2016 para 9.743.641 em 2025.",
        "notas": [
            "setor_regulado.aneel_consumidores.9",
            "setor_regulado.aneel_consumidores.0",
        ],
    },
}
DIVIDENDOS = {
    "secao": "dividendos",
    "parte": "dinheiro",
    "por_que": {
        "texto": "A seção traz os dividendos pagos e o lucro de cada ano.",
        "notas": ["dividendos.historico.0"],
    },
}


def _texto() -> saida.Analise:
    gabarito = json.loads((PAR_DA_CPFL / "gabarito.json").read_text(encoding="utf-8"))
    return saida.ler_analise(gabarito["analise"])


def _publicada(
    graficos: list[dict], destaques: list[dict] = (), **trocas: str
) -> dict[str, Any]:
    """A escolha como o passo `publicar` a grava no arquivo da análise."""
    return {
        "modelo": "claude-opus-5-5",
        "hash_da_entrada": en.hash_da_entrada(series.ampliar(entrada_do_lote())),
        "hash_do_texto": gr.hash_do_texto(_texto()),
        "escolha": {"graficos": graficos, "destaques": list(destaques)},
        **trocas,
    }


def _guardar(pasta: Path, graficos: dict[str, Any] | None = None) -> None:
    entrada = entrada_do_lote()
    digitos = "".join(c for c in entrada["cnpj"] if c.isdigit())
    guardada = {
        "cnpj": entrada["cnpj"],
        "empresa": entrada["empresa"],
        "corte": CORTE.isoformat(),
        "hash_da_entrada_atual": en.hash_da_entrada(entrada),
        "publicavel": True,
        "analise": _texto().como_dict(),
        "linhagem": {},
    }
    if graficos is not None:
        guardada[CAMPO_DOS_GRAFICOS] = graficos
    (pasta / f"{digitos}.json").write_text(
        json.dumps(guardada, ensure_ascii=False), encoding="utf-8"
    )


def _analise(pasta: Path, plano: str = "pro") -> AnaliseDaTela:
    entradas = entradas_da_cpfl()
    analise = com_analise(re_.montar(entradas, plano), entradas, plano, pasta).analise
    assert analise is not None
    return analise


def test_sem_escolha_publicada_a_reserva_vai_para_a_tela(tmp_path):
    _guardar(tmp_path)
    analise = _analise(tmp_path)
    assert len(analise.graficos) >= gr.MINIMO_DE_GRAFICOS
    assert {g.origem for g in analise.graficos} == {rg.ORIGEM_REGRAS}
    assert analise.destaques == ()


def test_escolha_do_modelo_vai_para_a_tela_com_os_pontos_da_ficha(tmp_path):
    _guardar(tmp_path, _publicada([MARGEM, CONSUMIDORES], [DIVIDENDOS]))
    analise = _analise(tmp_path)
    margem = next(g for g in analise.graficos if g.titulo == MARGEM["titulo"])
    assert margem.origem == saida.ORIGEM_MODELO
    assert (margem.parte, margem.paragrafo) == (PARTE, 1)
    assert margem.pontos.rotulos == ("2024", "2025")
    assert margem.pontos.valores == (pytest.approx((0.135, 0.129)),)
    assert margem.escala.medida == "%"
    assert margem.por_que.texto == MARGEM["por_que"]["texto"]
    citadas = {n.numero: n.id for n in analise.notas}
    assert [citadas[n] for n in margem.por_que.notas] == MARGEM["por_que"]["notas"]
    (destaque,) = analise.destaques
    assert (destaque.secao, destaque.titulo) == ("dividendos", "Dividendos e diluição")


def test_notas_seguem_a_ordem_de_leitura_e_cada_parte_lista_as_suas(tmp_path):
    _guardar(tmp_path, _publicada([MARGEM], [DIVIDENDOS]))
    analise = _analise(tmp_path)
    assert [n.numero for n in analise.notas] == list(range(1, len(analise.notas) + 1))
    indice = next(i for i, p in enumerate(analise.partes) if p.chave == PARTE)
    parte = analise.partes[indice]
    margem = next(g for g in analise.graficos if g.titulo == MARGEM["titulo"])
    lidas = [  # o que vem antes do gráfico na leitura: as partes de antes e os parágrafos 0 e 1
        *(f for p in analise.partes[:indice] for pa in p.paragrafos for f in pa.frases),
        *(f for pa in parte.paragrafos[:2] for f in pa.frases),
        *(g.por_que for g in analise.graficos_do_paragrafo(PARTE, 0)),
    ]
    ultima = max(n for f in lidas for n in f.notas)
    assert margem.por_que.notas == (ultima + 1, ultima + 2)
    novas = {n for f in parte.paragrafos[2].frases for n in f.notas if n > ultima}
    assert all(n > ultima + 2 for n in novas)
    da_parte = {n.numero for n in analise.notas_da_parte(parte)}
    assert set(margem.por_que.notas) <= da_parte
    assert analise.graficos_do_paragrafo(PARTE, 1) == (margem,)


def test_escolha_de_outro_texto_ou_outra_ficha_volta_a_reserva(tmp_path):
    for trocas in ({"hash_do_texto": "0" * 64}, {"hash_da_entrada": "0" * 64}):
        _guardar(tmp_path, _publicada([MARGEM], [DIVIDENDOS], **trocas))
        analise = _analise(tmp_path)
        assert {g.origem for g in analise.graficos} == {rg.ORIGEM_REGRAS}
        assert analise.destaques == ()


def test_grafico_reprovado_na_porta1_sai_e_a_reserva_completa(tmp_path):
    sem_numero = {**MARGEM, "por_que": {**MARGEM["por_que"], "texto": "A margem."}}
    _guardar(tmp_path, _publicada([sem_numero]))
    analise = _analise(tmp_path)
    assert MARGEM["titulo"] not in {g.titulo for g in analise.graficos}
    assert len(analise.graficos) >= gr.MINIMO_DE_GRAFICOS


def test_escolha_fora_do_formato_nao_derruba_o_texto(tmp_path):
    _guardar(tmp_path, {"escolha": "não é escolha"})
    analise = _analise(tmp_path)
    assert {p.origem for p in analise.partes} == {saida.ORIGEM_MODELO}
    assert {g.origem for g in analise.graficos} == {rg.ORIGEM_REGRAS}


def test_quem_nao_e_pro_nao_ve_grafico_nem_nota_do_dossie(tmp_path):
    _guardar(tmp_path, _publicada([MARGEM, CONSUMIDORES], [DIVIDENDOS]))
    dossie = {li["id"] for li in entrada_do_lote()["linhas"] if li["so_pro"]}
    pro, gratis = _analise(tmp_path), _analise(tmp_path, "gratuito")
    assert CONSUMIDORES["titulo"] in {g.titulo for g in pro.graficos}
    assert CONSUMIDORES["titulo"] not in {g.titulo for g in gratis.graficos}
    assert not {i for g in gratis.graficos for i in g.pontos.ids} & dossie
    obrigatorias = set(entrada_do_lote()["obrigatorias"])
    assert not ({n.id for n in gratis.notas} & (dossie - obrigatorias))


def test_ficha_nova_so_mostra_a_reserva(tmp_path):
    _guardar(tmp_path, _publicada([MARGEM]))
    arquivo = next(tmp_path.glob("*.json"))
    guardada = json.loads(arquivo.read_text(encoding="utf-8"))
    guardada["hash_da_entrada_atual"] = "0" * 64
    arquivo.write_text(json.dumps(guardada, ensure_ascii=False), encoding="utf-8")
    analise = _analise(tmp_path)
    assert {p.origem for p in analise.partes} == {saida.ORIGEM_MOLDE}
    assert {g.origem for g in analise.graficos} == {rg.ORIGEM_REGRAS}


def test_api_traz_os_graficos_com_os_pontos_e_os_destaques(tmp_path):
    from src.api_v1 import esquemas

    _guardar(tmp_path, _publicada([MARGEM], [DIVIDENDOS]))
    entradas = entradas_da_cpfl()
    relatorio = com_analise(re_.montar(entradas, "pro"), entradas, "pro", tmp_path)
    api = esquemas.de_relatorio_da_empresa(relatorio)
    assert api.analise is not None
    margem = next(g for g in api.analise.graficos if g.titulo == MARGEM["titulo"])
    assert margem.pontos.rotulos == ["2024", "2025"]
    assert margem.escala.medida == "%"
    assert margem.por_que.texto == MARGEM["por_que"]["texto"]
    assert [d.secao for d in api.analise.destaques] == ["dividendos"]


def test_pdf_traz_o_achado_do_grafico_e_o_destaque(tmp_path):
    from src.relatorio_empresa_pdf import relatorio_da_empresa
    from tests.test_analise_na_tela import _texto_do_pdf

    _guardar(tmp_path, _publicada([MARGEM], [DIVIDENDOS]))
    entradas = entradas_da_cpfl()
    relatorio = com_analise(re_.montar(entradas, "pro"), entradas, "pro", tmp_path)
    texto = _texto_do_pdf(relatorio_da_empresa(relatorio))
    assert "".join(MARGEM["por_que"]["texto"].split()) in texto
    assert "".join(DIVIDENDOS["por_que"]["texto"].split()) in texto


def test_tela_desenha_o_grafico_depois_do_paragrafo_com_o_achado(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    from tests.test_analise_na_tela import _tela_da_analise

    _guardar(tmp_path, _publicada([MARGEM], [DIVIDENDOS]))
    monkeypatch.setenv("PASTA_DO_TESTE", str(tmp_path))
    app = AppTest.from_function(_tela_da_analise, default_timeout=120).run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == len(_analise(tmp_path).graficos)
    legendas = " ".join(c.value for c in app.caption)
    assert MARGEM["por_que"]["texto"].replace(".", "") in legendas
    (destaque,) = app.info
    assert "Dividendos e diluição" in destaque.value
