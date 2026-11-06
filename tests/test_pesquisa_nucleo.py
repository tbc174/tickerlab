"""Rodada, memória, leitores e evidência do bot de pesquisa (`pesquisa/`), sem internet."""

from datetime import timedelta
from pathlib import Path

import pytest

from pesquisa import evidencia, leitores, memoria
from pesquisa.rodada import MEGABYTE, LimiteExcedido, Limites, Rodada
from tests.ajudantes_da_pesquisa import (
    html_com_links,
    pdf_com_texto,
    sem_docling,  # noqa: F401 (autouse)
    xlsx_com_linhas,
)

# --- rodada ------------------------------------------------------------------------------


def test_limites_padrao_sao_os_da_fila():
    limites = Limites()
    assert (limites.buscas, limites.candidatos, limites.profundidade) == (12, 30, 2)
    assert limites.bytes_maximos == 250 * MEGABYTE
    assert limites.segundos == 30 * 60


def test_rodada_para_na_13a_busca():
    rodada = Rodada("h")
    for _ in range(12):
        rodada.gastar_busca()
    with pytest.raises(LimiteExcedido, match="12 buscas"):
        rodada.gastar_busca()


def test_rodada_conta_candidato_distinto_uma_vez_e_para_no_31():
    rodada = Rodada("h")
    for numero in range(30):
        rodada.examinar(f"https://x.gov.br/{numero}")
    rodada.examinar("https://x.gov.br/0")  # repetido: não conta de novo
    with pytest.raises(LimiteExcedido, match="30 candidatos"):
        rodada.examinar("https://x.gov.br/novo")


def test_documento_pode_ficar_um_passo_alem_do_limite_das_paginas():
    rodada = Rodada("h")
    rodada.anotar_links("https://a", ["https://b"])
    rodada.anotar_links("https://b", ["https://c"])
    rodada.anotar_links("https://c", ["https://planilha.xlsx"])
    with pytest.raises(LimiteExcedido, match="limite 2"):
        rodada.examinar("https://planilha.xlsx")
    rodada.examinar("https://planilha.xlsx", folha=True)
    rodada.anotar_links("https://planilha.xlsx", ["https://longe.xlsx"])
    with pytest.raises(LimiteExcedido, match="limite 3"):
        rodada.examinar("https://longe.xlsx", folha=True)


def test_rodada_recusa_profundidade_acima_de_2_e_guarda_o_caminho_mais_curto():
    rodada = Rodada("h")
    rodada.anotar_links("https://a", ["https://b"])
    rodada.anotar_links("https://b", ["https://c"])
    rodada.anotar_links("https://c", ["https://d"])
    assert rodada.profundidades["https://c"] == 2
    rodada.examinar("https://c")
    with pytest.raises(LimiteExcedido, match="links do ponto de partida"):
        rodada.examinar("https://d")
    rodada.anotar_links("https://a", ["https://d"])  # atalho: agora d está a 1 link
    rodada.examinar("https://d")


def test_rodada_para_depois_de_30_minutos():
    agora = [0.0]
    rodada = Rodada("h", relogio=lambda: agora[0])
    rodada.gastar_busca()
    agora[0] = 30 * 60 + 1
    with pytest.raises(LimiteExcedido, match="30 minutos"):
        rodada.gastar_busca()


def test_rodada_conta_bytes_e_diz_o_saldo():
    rodada = Rodada("h", Limites(bytes_maximos=10 * MEGABYTE))
    rodada.gastar_bytes(4 * MEGABYTE)
    assert rodada.bytes_restantes() == 6 * MEGABYTE
    rodada.gastar_bytes(20 * MEGABYTE)
    assert rodada.bytes_restantes() == 0
    assert rodada.resumo()["buscas"] == "0/12"


# --- memória -----------------------------------------------------------------------------


def _visto(url: str = "https://x.gov.br/a.pdf") -> memoria.Visto:
    return memoria.Visto(url, url, "a" * 64, "pdf", 10, None, "2026-11-05", "r1")


def test_memoria_lembra_o_visto_e_apaga_o_negativo(tmp_path: Path):
    banco = memoria.Memoria(tmp_path / "m.sqlite")
    banco.anotar_negativo("https://x.gov.br/a.pdf", "HTTP 403", 403, "r0")
    assert banco.negativo_valido("https://x.gov.br/a.pdf") is not None
    banco.lembrar(_visto())
    assert banco.negativo_valido("https://x.gov.br/a.pdf") is None
    visto = banco.ja_visto("https://x.gov.br/a.pdf")
    assert visto is not None and visto.sha256 == "a" * 64


def test_negativo_vence_em_7_dias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    banco = memoria.Memoria(tmp_path / "m.sqlite")
    banco.anotar_negativo("https://x", "HTTP 403", 403, "r0")
    depois = memoria.agora() + timedelta(days=memoria.VALIDADE_DO_NEGATIVO_DIAS + 1)
    monkeypatch.setattr(memoria, "agora", lambda: depois)
    assert banco.negativo_valido("https://x") is None


def test_memoria_registra_fato_e_conta(tmp_path: Path):
    banco = memoria.Memoria(tmp_path / "m.sqlite")
    banco.registrar_fato("r1", "h", {"valor": "120"}, "confirmado", [])
    assert banco.contagens() == {"visto": 0, "negativo": 0, "fato": 1}


def test_memoria_persiste_entre_aberturas(tmp_path: Path):
    memoria.Memoria(tmp_path / "m.sqlite").lembrar(_visto())
    assert memoria.Memoria(tmp_path / "m.sqlite").ja_visto("https://x.gov.br/a.pdf")


# --- leitores ----------------------------------------------------------------------------


def _gravar(tmp_path: Path, nome: str, conteudo: bytes) -> Path:
    caminho = tmp_path / nome
    caminho.write_bytes(conteudo)
    return caminho


def test_descobrir_tipo_pelo_conteudo_e_nao_pelo_nome(tmp_path: Path):
    assert (
        leitores.descobrir_tipo(_gravar(tmp_path, "a.xlsx", pdf_com_texto(["oi"])))
        == "pdf"
    )
    assert (
        leitores.descobrir_tipo(_gravar(tmp_path, "b.pdf", xlsx_com_linhas([[1]])))
        == "xlsx"
    )
    assert (
        leitores.descobrir_tipo(
            _gravar(tmp_path, "c.pdf", b"<html><body>x</body></html>")
        )
        == "html"
    )
    assert leitores.descobrir_tipo(_gravar(tmp_path, "d.csv", b"a;b\n1;2\n")) == "csv"
    assert (
        leitores.descobrir_tipo(_gravar(tmp_path, "e.bin", b"\x00\x01"))
        == "desconhecido"
    )


def test_pdf_devolve_o_texto_com_a_pagina(tmp_path: Path):
    arquivo = _gravar(
        tmp_path, "a.pdf", pdf_com_texto(["Parque Alfa 120 MW", "Parque Beta 80 MW"])
    )
    extracao = leitores.extrair(arquivo, motor="auto")
    assert extracao.tipo == "pdf"
    assert [bloco.posicao for bloco in extracao.blocos][:2] == ["pagina 1", "pagina 2"]
    assert "Parque Beta 80 MW" in extracao.blocos[1].texto


def test_pdf_pede_so_a_faixa_de_paginas(tmp_path: Path):
    arquivo = _gravar(tmp_path, "a.pdf", pdf_com_texto(["um", "dois", "tres"]))
    extracao = leitores.extrair(arquivo, motor="auto", pagina_inicial=2, pagina_final=2)
    assert [bloco.posicao for bloco in extracao.blocos] == ["pagina 2"]
    assert any("lidas de 2 a 2" in aviso for aviso in extracao.avisos)


def test_xlsx_devolve_linhas_com_o_numero_e_corta_no_limite(tmp_path: Path):
    arquivo = _gravar(
        tmp_path, "a.xlsx", xlsx_com_linhas([[f"linha {n}", n] for n in range(1, 11)])
    )
    extracao = leitores.extrair(arquivo, maximo_de_linhas=4, linha_inicial=3)
    assert extracao.truncado
    assert extracao.tabelas[0].primeira_linha == 3
    posicoes = [posicao for posicao, _ in extracao.trechos()]
    assert posicoes[0] == "Dados linha 3" and posicoes[-1] == "Dados linha 6"


def test_xlsx_pula_linhas_vazias_corta_celulas_do_fim_e_guarda_o_numero_real(
    tmp_path: Path,
):
    linhas = [
        [None],
        [None, None],
        ["Usina", "MW", None, None],
        [None],
        ["Alfa", 120, None, None],
    ]
    arquivo = _gravar(tmp_path, "a.xlsx", xlsx_com_linhas(linhas))
    extracao = leitores.extrair(arquivo)
    assert extracao.tabelas[0].linhas == [["Usina", "MW"], ["Alfa", "120"]]
    assert [posicao for posicao, _ in extracao.trechos()] == [
        "Dados linha 3",
        "Dados linha 5",
    ]


def test_xlsx_pede_uma_aba_e_lista_os_nomes(tmp_path: Path):
    from openpyxl import Workbook

    pasta = Workbook()
    primeira = pasta.active
    assert primeira is not None
    primeira.title = "Leia-me"
    primeira.append(["texto de capa"])
    pasta.create_sheet("Resultado").append(["Alfa", 120])
    arquivo = tmp_path / "a.xlsx"
    pasta.save(arquivo)
    todas = leitores.extrair(arquivo)
    uma = leitores.extrair(arquivo, planilha="Resultado")
    assert todas.planilhas == ["Leia-me", "Resultado"] and len(todas.tabelas) == 2
    assert [t.posicao for t in uma.tabelas] == ["Resultado"]
    erro = leitores.extrair(arquivo, planilha="Nao existe")
    assert not erro.tabelas and "não há a planilha" in erro.avisos[0]


def test_xlsx_contem_acha_a_linha_no_meio_de_milhares_antes_do_corte(tmp_path: Path):
    linhas = [["Usina", "CEG"]] + [
        [f"Parque {n}", f"EOL.CV.{n}"] for n in range(1, 501)
    ]
    arquivo = _gravar(tmp_path, "a.xlsx", xlsx_com_linhas(linhas))
    cega = leitores.extrair(arquivo, maximo_de_linhas=10)
    achada = leitores.extrair(arquivo, maximo_de_linhas=10, contem=("eol.cv.450",))
    assert cega.truncado and not achada.truncado
    assert achada.tabelas[0].linhas == [["Parque 450", "EOL.CV.450"]]
    assert [posicao for posicao, _ in achada.trechos()] == ["Dados linha 451"]


def test_contem_exige_todos_os_termos_e_ignora_caixa(tmp_path: Path):
    arquivo = _gravar(
        tmp_path, "a.csv", b"usina;ano\nAlfa;2019\nAlfa;2021\nBeta;2021\n"
    )
    extracao = leitores.extrair(arquivo, contem=("ALFA", "2021"))
    assert extracao.tabelas[0].linhas == [["Alfa", "2021"]]
    assert [posicao for posicao, _ in extracao.trechos()] == ["csv linha 3"]


def test_contem_filtra_paginas_de_pdf(tmp_path: Path):
    arquivo = _gravar(tmp_path, "a.pdf", pdf_com_texto(["um", "dois", "tres"]))
    extracao = leitores.extrair(arquivo, motor="auto", contem=("dois",))
    assert [bloco.posicao for bloco in extracao.blocos] == ["pagina 2"]


def test_csv_acha_o_delimitador_e_a_codificacao(tmp_path: Path):
    conteudo = "usina;potência\nAlfa;120\n".encode("cp1252")
    extracao = leitores.extrair(_gravar(tmp_path, "a.csv", conteudo))
    assert extracao.tabelas[0].linhas[1] == ["Alfa", "120"]
    assert extracao.tabelas[0].linhas[0] == ["usina", "potência"]


def test_html_tira_script_e_le_tabela():
    html = b"<html><body><script>x=1</script><p>Texto   do\n parque</p><table><tr><td>A</td><td>1</td></tr></table></body></html>"
    extracao = leitores.ler_html(html)
    assert (
        extracao.blocos[0].texto == "A 1 Texto do parque"
        or "Texto do parque" in extracao.blocos[0].texto
    )
    assert "x=1" not in extracao.blocos[0].texto
    assert extracao.tabelas[0].linhas == [["A", "1"]]


def test_texto_longo_e_cortado_e_marcado():
    html = html_com_links("t", [], texto="palavra " * 100)
    extracao = leitores.ler_html(html, maximo=50)
    assert extracao.truncado and len(extracao.blocos[0].texto) == 50


def test_tipo_nao_suportado_avisa_em_vez_de_fingir(tmp_path: Path):
    extracao = leitores.extrair(_gravar(tmp_path, "a.bin", b"\x00\x01\x02"))
    assert extracao.avisos and not extracao.blocos and not extracao.tabelas


def test_pdf_sem_texto_avisa_que_pode_ser_escaneado(tmp_path: Path):
    arquivo = _gravar(tmp_path, "a.pdf", pdf_com_texto([""]))
    assert any("escaneado" in aviso for aviso in leitores.extrair(arquivo).avisos)


# --- evidência ---------------------------------------------------------------------------


def _fato(sha: str, **mudancas: object) -> evidencia.Fato:
    base: dict[str, object] = {
        "afirmacao": "Alfa tem 120 MW",
        "valor": "120",
        "trecho": "Parque Alfa 120 MW",
        "sha256": sha,
    }
    base.update(mudancas)
    return evidencia.Fato(**base)  # type: ignore[arg-type]


def _pdf_guardado(tmp_path: Path, textos: list[str]) -> tuple[Path, str]:
    from pesquisa.coletor import _sha256_do_arquivo

    arquivo = _gravar(tmp_path, "original.pdf", pdf_com_texto(textos))
    return arquivo, _sha256_do_arquivo(arquivo)


def test_fato_com_trecho_literal_e_confirmado_e_diz_onde(tmp_path: Path):
    arquivo, sha = _pdf_guardado(tmp_path, ["Capa", "Parque Alfa 120 MW em Sobral"])
    veredito = evidencia.validar(_fato(sha), arquivo)
    assert veredito.situacao == evidencia.CONFIRMADO
    assert veredito.onde == "pagina 2"


def test_linha_de_planilha_vale_com_barra_ou_espaco_e_posicao_com_virgula(
    tmp_path: Path,
):
    from pesquisa.coletor import _sha256_do_arquivo

    arquivo = _gravar(
        tmp_path,
        "a.xlsx",
        xlsx_com_linhas([["Usina", "CEG"], ["Alfa Eólica", "EOL.CV.RN.1"]]),
    )
    sha = _sha256_do_arquivo(arquivo)
    for trecho in ("Alfa Eólica | EOL.CV.RN.1", "Alfa Eólica EOL.CV.RN.1"):
        fato = _fato(
            sha,
            trecho=trecho,
            valor="EOL.CV.RN.1",
            posicao="Dados, linha 2",
        )
        veredito = evidencia.validar(fato, arquivo)
        assert veredito.situacao == evidencia.CONFIRMADO, veredito.motivos
        assert veredito.onde == "Dados linha 2"


def test_trecho_inventado_fica_pendente(tmp_path: Path):
    arquivo, sha = _pdf_guardado(tmp_path, ["Parque Alfa 120 MW"])
    veredito = evidencia.validar(
        _fato(sha, trecho="Parque Alfa 999 MW sem fonte"), arquivo
    )
    assert veredito.situacao == evidencia.PENDENTE
    assert "não está literalmente" in veredito.motivos[0]


def test_valor_fora_do_trecho_fica_pendente(tmp_path: Path):
    arquivo, sha = _pdf_guardado(tmp_path, ["Parque Alfa 120 MW"])
    veredito = evidencia.validar(_fato(sha, valor="150"), arquivo)
    assert veredito.situacao == evidencia.PENDENTE
    assert "valor" in veredito.motivos[0]


def test_exigir_no_trecho_cobra_cnpj_e_ano(tmp_path: Path):
    arquivo, sha = _pdf_guardado(
        tmp_path, ["Parque Alfa 120 MW CNPJ 12.345.678/0001-90"]
    )
    trecho = "Parque Alfa 120 MW CNPJ 12.345.678/0001-90"
    certo = evidencia.validar(
        _fato(sha, trecho=trecho, exigir_no_trecho=("12345678000190",)), arquivo
    )
    errado = evidencia.validar(
        _fato(sha, trecho=trecho, exigir_no_trecho=("2035",)), arquivo
    )
    assert certo.situacao == evidencia.CONFIRMADO
    assert errado.situacao == evidencia.PENDENTE and "2035" in errado.motivos[0]


def test_hash_diferente_do_arquivo_fica_pendente(tmp_path: Path):
    arquivo, _ = _pdf_guardado(tmp_path, ["Parque Alfa 120 MW"])
    veredito = evidencia.validar(_fato("0" * 64), arquivo)
    assert veredito.situacao == evidencia.PENDENTE and "sha256" in veredito.motivos[0]


def test_sem_original_e_trecho_curto_ficam_pendentes(tmp_path: Path):
    assert evidencia.validar(_fato("0" * 64), None).situacao == evidencia.PENDENTE
    arquivo, sha = _pdf_guardado(tmp_path, ["R$ 5 e mais coisas"])
    curto = evidencia.validar(_fato(sha, valor="5", trecho="R$ 5"), arquivo)
    assert curto.situacao == evidencia.PENDENTE and "curto" in curto.motivos[0]


def test_posicao_dada_restringe_a_busca(tmp_path: Path):
    arquivo, sha = _pdf_guardado(
        tmp_path, ["Parque Alfa 120 MW", "outra coisa qualquer aqui"]
    )
    assert (
        evidencia.validar(_fato(sha, posicao="pagina 2"), arquivo).situacao
        == evidencia.PENDENTE
    )
    assert (
        evidencia.validar(_fato(sha, posicao="pagina 1"), arquivo).situacao
        == evidencia.CONFIRMADO
    )


def test_confere_linha_de_planilha(tmp_path: Path):
    from pesquisa.coletor import _sha256_do_arquivo

    arquivo = _gravar(
        tmp_path, "p.xlsx", xlsx_com_linhas([["Usina", "MW"], ["Alfa Eolica", 120]])
    )
    fato = _fato(_sha256_do_arquivo(arquivo), trecho="Alfa Eolica | 120")
    veredito = evidencia.validar(fato, arquivo)
    assert (
        veredito.situacao == evidencia.CONFIRMADO and veredito.onde == "Dados linha 2"
    )


# --- Docling (dublê: o de verdade baixa modelos e é medido na rodada real) ----------------


def _docling_falso(monkeypatch: pytest.MonkeyPatch):
    import sys
    import types

    import pandas

    class Item:
        def __init__(self, texto: str, pagina: int) -> None:
            self.text = texto
            self.prov = [types.SimpleNamespace(page_no=pagina)]

    class TabelaFalsa:
        def __init__(self) -> None:
            self.prov = [types.SimpleNamespace(page_no=2)]

        def export_to_dataframe(self, _documento: object) -> pandas.DataFrame:
            return pandas.DataFrame({"Usina": ["Alfa", "Beta"], "MW": [120, 80]})

    documento = types.SimpleNamespace(
        texts=[Item("Parque Alfa", 1), Item("120 MW", 1), Item("Parque Beta", 2)],
        tables=[TabelaFalsa()],
    )

    class Conversor:
        def convert(self, _caminho: str):
            return types.SimpleNamespace(document=documento)

    modulo = types.ModuleType("docling.document_converter")
    modulo.DocumentConverter = Conversor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))
    monkeypatch.setitem(sys.modules, "docling.document_converter", modulo)


def test_docling_devolve_texto_por_pagina_e_tabela_com_pagina(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pytest.importorskip("pandas")
    _docling_falso(monkeypatch)
    arquivo = _gravar(tmp_path, "a.pdf", pdf_com_texto(["x"]))
    extracao = leitores.extrair(arquivo, motor="docling")
    assert extracao.motor == "docling"
    assert [(b.posicao, b.texto) for b in extracao.blocos] == [
        ("pagina 1", "Parque Alfa 120 MW"),
        ("pagina 2", "Parque Beta"),
    ]
    assert extracao.tabelas[0].posicao == "pagina 2 tabela 1"
    assert extracao.tabelas[0].linhas[1] == ["Alfa", "120"]


def test_docling_respeita_a_faixa_de_paginas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pytest.importorskip("pandas")
    _docling_falso(monkeypatch)
    arquivo = _gravar(tmp_path, "a.pdf", pdf_com_texto(["x"]))
    extracao = leitores.extrair(
        arquivo, motor="docling", pagina_inicial=2, pagina_final=2
    )
    assert [b.posicao for b in extracao.blocos] == ["pagina 2"]
