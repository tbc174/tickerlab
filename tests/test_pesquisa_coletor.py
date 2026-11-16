"""Coletor e Pesquisador do bot de pesquisa (`pesquisa/`): rede falsa, sem internet."""

import json
from pathlib import Path

import pytest
import requests

from base.arquivo.coleta import BloqueioAntiRobo
from pesquisa import coletor
from pesquisa.pesquisador import Pesquisador
from pesquisa.rodada import MEGABYTE, Limites
from tests.ajudantes_da_pesquisa import (
    ClienteFalso,
    erro_http,
    html_com_links,
    pdf_com_texto,
    sem_docling,  # noqa: F401 (autouse)
    xlsx_com_linhas,
)

SITE = "https://dados.exemplo.gov.br"
PDF = pdf_com_texto(["Parque Alfa 120 MW CNPJ 12.345.678/0001-90"])
XLSX = xlsx_com_linhas([["Usina", "MW"], ["Alfa Eolica", 120]])


def _pesquisador(
    tmp_path: Path,
    paginas: dict[str, object],
    limites: Limites | None = None,
    **cliente: object,
) -> tuple[Pesquisador, ClienteFalso]:
    falso = ClienteFalso(paginas, **cliente)  # type: ignore[arg-type]
    pesquisador = Pesquisador(tmp_path / "dados", falso, limites=limites)
    assert pesquisador.iniciar_rodada("a potência de Alfa é 120 MW")["ok"]
    return pesquisador, falso


# --- endereços ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://x.gov.br/a",
        "http://localhost:8000/x",
        "http://127.0.0.1/x",
        "http://10.0.0.5/x",
        "http://192.168.0.1/x",
        "http://169.254.169.254/latest",
        "http://[::1]/x",
        "http://servidor.local/x",
        "sem-esquema",
    ],
)
def test_endereco_interno_ou_de_outro_esquema_e_recusado(url: str):
    with pytest.raises(coletor.Recusa):
        coletor.normalizar_url(url)


def test_normalizar_tira_o_fragmento_e_aceita_ip_publico():
    assert coletor.normalizar_url(f"{SITE}/a#parte") == f"{SITE}/a"
    assert coletor.normalizar_url("http://8.8.8.8/x") == "http://8.8.8.8/x"


def test_tipo_do_link_pela_extensao():
    assert coletor.tipo_do_link(f"{SITE}/a.PDF?x=1") == "pdf"
    assert coletor.tipo_do_link(f"{SITE}/a.xlsx") == "xlsx"
    assert coletor.tipo_do_link(f"{SITE}/pagina") == "pagina"


# --- buscar página -----------------------------------------------------------------------


def test_buscar_pagina_devolve_titulo_texto_links_e_documentos_primeiro(tmp_path: Path):
    html = html_com_links(
        "Leilões",
        [("/sobre", "Sobre"), ("/anexo.pdf", "Resultado"), ("mailto:a@b", "e-mail")],
        texto="Resultados dos leilões",
    )
    pesquisador, _ = _pesquisador(tmp_path, {f"{SITE}/": html})
    resposta = pesquisador.buscar_pagina(f"{SITE}/")
    assert resposta["ok"] and resposta["titulo"] == "Leilões"
    assert "Resultados dos leilões" in resposta["texto"]  # type: ignore[operator]
    links = resposta["links"]
    assert [link["url"] for link in links] == [f"{SITE}/anexo.pdf", f"{SITE}/sobre"]  # type: ignore[index]
    assert "dado" in resposta["aviso"] and len(resposta["sha256"]) == 64  # type: ignore[arg-type]


def test_pagina_ja_vista_volta_da_memoria_sem_novo_pedido_nem_gasto(tmp_path: Path):
    pesquisador, falso = _pesquisador(tmp_path, {f"{SITE}/": html_com_links("A", [])})
    pesquisador.buscar_pagina(f"{SITE}/")
    segunda = pesquisador.buscar_pagina(f"{SITE}/")
    assert segunda["ja_visto"] is True
    assert falso.pedidos == [f"{SITE}/"]
    assert pesquisador.rodada.buscas_feitas == 1  # type: ignore[union-attr]


def test_robots_disallow_e_respeitado_e_lembrado(tmp_path: Path):
    pesquisador, falso = _pesquisador(tmp_path, {f"{SITE}/privado/a": b"segredo"})
    resposta = pesquisador.buscar_pagina(f"{SITE}/privado/a")
    assert not resposta["ok"] and "robots.txt" in resposta["motivo"]  # type: ignore[operator]
    assert falso.pedidos == []
    assert pesquisador.buscar_pagina(f"{SITE}/privado/a")["ja_tentado"] is True


def test_sem_robots_vale_a_regra_de_quem_nao_tem(tmp_path: Path):
    pesquisador, _ = _pesquisador(
        tmp_path, {f"{SITE}/privado/a": html_com_links("A", [])}, robots=None
    )
    assert pesquisador.buscar_pagina(f"{SITE}/privado/a")["ok"]


def test_http_403_vira_negativo_lembrado_e_forcar_tenta_de_novo(tmp_path: Path):
    paginas = {f"{SITE}/a.xlsx": erro_http(403)}
    pesquisador, falso = _pesquisador(tmp_path, paginas)
    primeira = pesquisador.baixar_documento(f"{SITE}/a.xlsx")
    assert primeira["status_http"] == 403 and primeira["ok"] is False
    segunda = pesquisador.baixar_documento(f"{SITE}/a.xlsx")
    assert segunda["ja_tentado"] is True and falso.pedidos == [f"{SITE}/a.xlsx"]
    falso.paginas[f"{SITE}/a.xlsx"] = XLSX
    assert pesquisador.baixar_documento(f"{SITE}/a.xlsx", forcar=True)["ok"]


def test_falha_de_conexao_nao_vira_negativo(tmp_path: Path):
    paginas = {f"{SITE}/a": requests.ConnectionError("caiu")}
    pesquisador, falso = _pesquisador(tmp_path, paginas)
    assert pesquisador.buscar_pagina(f"{SITE}/a")["ok"] is False
    falso.paginas[f"{SITE}/a"] = html_com_links("A", [])
    assert pesquisador.buscar_pagina(f"{SITE}/a")["ok"] is True


def test_bloqueio_anti_robo_e_registrado_e_nao_se_contorna(tmp_path: Path):
    pesquisador, falso = _pesquisador(
        tmp_path, {f"{SITE}/a": BloqueioAntiRobo("desafio")}
    )
    resposta = pesquisador.buscar_pagina(f"{SITE}/a")
    assert "anti-robô" in resposta["motivo"]  # type: ignore[operator]
    assert pesquisador.buscar_pagina(f"{SITE}/a")["ja_tentado"] is True
    assert falso.pedidos == [f"{SITE}/a"]


def test_renderizar_sem_crawl4ai_recusa_com_o_motivo(tmp_path: Path):
    pesquisador, _ = _pesquisador(tmp_path, {f"{SITE}/a": html_com_links("A", [])})
    resposta = pesquisador.buscar_pagina(f"{SITE}/a", renderizar=True)
    assert "Crawl4AI" in resposta["motivo"]  # type: ignore[operator]


def test_renderizador_injetado_e_usado_e_respeita_robots(tmp_path: Path):
    chamadas: list[str] = []

    def renderizador(url: str) -> tuple[str, bytes]:
        chamadas.append(url)
        return url, html_com_links("Montada por JS", [], texto="conteúdo dinâmico")

    falso = ClienteFalso({})
    pesquisador = Pesquisador(tmp_path / "d", falso, renderizador=renderizador)
    pesquisador.iniciar_rodada("h")
    resposta = pesquisador.buscar_pagina(f"{SITE}/app", renderizar=True)
    assert resposta["titulo"] == "Montada por JS" and chamadas == [f"{SITE}/app"]
    bloqueada = pesquisador.buscar_pagina(f"{SITE}/privado/x", renderizar=True)
    assert not bloqueada["ok"] and chamadas == [f"{SITE}/app"]


def test_navegador_que_falha_vira_recusa_e_nao_derruba_a_ferramenta(tmp_path: Path):
    def renderizador(url: str) -> tuple[str, bytes]:
        raise RuntimeError("Executable doesn't exist")

    pesquisador = Pesquisador(
        tmp_path / "d", ClienteFalso({}), renderizador=renderizador
    )
    pesquisador.iniciar_rodada("h")
    resposta = pesquisador.buscar_pagina(f"{SITE}/app", renderizar=True)
    assert resposta["ok"] is False and "renderização falhou" in resposta["motivo"]  # type: ignore[operator]
    assert (
        pesquisador.memoria.negativo_valido(f"{SITE}/app") is None
    )  # falha do ambiente


def test_endereco_interno_nao_chega_a_rede(tmp_path: Path):
    pesquisador, falso = _pesquisador(tmp_path, {})
    assert pesquisador.buscar_pagina("http://127.0.0.1:8080/admin")["ok"] is False
    assert pesquisador.baixar_documento("http://169.254.169.254/x")["ok"] is False
    assert falso.pedidos == []


# --- limites da rodada -------------------------------------------------------------------


def test_13a_busca_devolve_limite_e_nao_pede(tmp_path: Path):
    paginas = {f"{SITE}/{n}": html_com_links(str(n), []) for n in range(14)}
    pesquisador, falso = _pesquisador(tmp_path, paginas)
    respostas = [pesquisador.buscar_pagina(f"{SITE}/{n}") for n in range(13)]
    assert all(r["ok"] for r in respostas[:12])
    assert "12 buscas" in respostas[12]["limite"]  # type: ignore[operator]
    assert len(falso.pedidos) == 12


def test_profundidade_3_e_recusada(tmp_path: Path):
    paginas = {
        f"{SITE}/a": html_com_links("a", [("/b", "b")]),
        f"{SITE}/b": html_com_links("b", [("/c", "c")]),
        f"{SITE}/c": html_com_links("c", [("/d", "d")]),
        f"{SITE}/d": html_com_links("d", []),
    }
    pesquisador, _ = _pesquisador(tmp_path, paginas)
    for letra in "abc":
        assert pesquisador.buscar_pagina(f"{SITE}/{letra}")["ok"]
    assert (
        "links do ponto de partida" in pesquisador.buscar_pagina(f"{SITE}/d")["limite"]
    )  # type: ignore[operator]


def test_arquivo_maior_que_o_saldo_nao_e_baixado(tmp_path: Path):
    limites = Limites(bytes_maximos=1 * MEGABYTE)
    pesquisador, falso = _pesquisador(
        tmp_path,
        {f"{SITE}/grande.pdf": PDF},
        limites,
        cabecalhos={"Content-Length": str(500 * MEGABYTE)},
    )
    resposta = pesquisador.baixar_documento(f"{SITE}/grande.pdf")
    assert "saldo" in resposta["limite"]  # type: ignore[operator]
    assert falso.pedidos == []


def test_estado_mostra_o_gasto_e_a_memoria(tmp_path: Path):
    pesquisador, _ = _pesquisador(tmp_path, {f"{SITE}/": html_com_links("A", [])})
    pesquisador.buscar_pagina(f"{SITE}/")
    estado = pesquisador.estado()
    assert estado["buscas"] == "1/12" and estado["memoria"]["visto"] == 1  # type: ignore[index]


def test_sem_rodada_aberta_as_ferramentas_pedem_a_hipotese(tmp_path: Path):
    pesquisador = Pesquisador(tmp_path / "d", ClienteFalso({}))
    assert "iniciar_rodada" in pesquisador.buscar_pagina(f"{SITE}/")["motivo"]  # type: ignore[operator]
    assert pesquisador.iniciar_rodada("   ")["ok"] is False


# --- baixar documento, extrair, validar --------------------------------------------------


def test_baixar_documento_guarda_original_proveniencia_e_sha(tmp_path: Path):
    pesquisador, _ = _pesquisador(tmp_path, {f"{SITE}/a.pdf": PDF})
    resposta = pesquisador.baixar_documento(f"{SITE}/a.pdf")
    assert (
        resposta["ok"] and resposta["tipo"] == "pdf" and len(resposta["sha256"]) == 64
    )  # type: ignore[arg-type]
    sha = str(resposta["sha256"])
    assert Path(str(resposta["caminho"])).read_bytes() == PDF
    proveniencia = json.loads(
        (tmp_path / "dados" / "documentos" / f"{sha}.json").read_text("utf-8")
    )
    assert proveniencia["url"] == f"{SITE}/a.pdf" and proveniencia[
        "hipotese"
    ].startswith("a potência")
    assert pesquisador.baixar_documento(f"{SITE}/a.pdf")["ja_visto"] is True


def test_documento_que_vem_como_html_e_recusado(tmp_path: Path):
    pesquisador, _ = _pesquisador(
        tmp_path, {f"{SITE}/a.pdf": b"<html><body>Acesso negado</body></html>"}
    )
    resposta = pesquisador.baixar_documento(f"{SITE}/a.pdf")
    assert not resposta["ok"] and "HTML" in resposta["motivo"]  # type: ignore[operator]
    assert not list((tmp_path / "dados" / "documentos").glob("*.pdf"))


def test_extrair_le_pdf_e_xlsx_baixados(tmp_path: Path):
    pesquisador, _ = _pesquisador(
        tmp_path, {f"{SITE}/a.pdf": PDF, f"{SITE}/b.xlsx": XLSX}
    )
    sha_pdf = str(pesquisador.baixar_documento(f"{SITE}/a.pdf")["sha256"])
    sha_xlsx = str(pesquisador.baixar_documento(f"{SITE}/b.xlsx")["sha256"])
    pdf = pesquisador.extrair(sha_pdf)
    assert pdf["ok"] and "Parque Alfa 120 MW" in pdf["blocos"][0]["texto"]  # type: ignore[index]
    planilha = pesquisador.extrair(sha_xlsx)
    assert planilha["tabelas"][0]["linhas"][1] == ["Alfa Eolica", "120"]  # type: ignore[index]
    assert "dado" in planilha["aviso"]  # type: ignore[operator]


CSV_DA_CVM = (
    "CNPJ_CIA;DENOM_SOCIAL;SIT\n"
    "33.000.167/0001-01;PETRÓLEO BRASILEIRO S.A. - PETROBRAS;ATIVO\n"
).encode("latin-1")


def test_csv_baixado_e_lido_e_o_fato_confirmado(tmp_path: Path):
    """Regressão: o tipo era descoberto no temporário `.tmp`, e todo CSV virava "desconhecido"
    (rodada real no cadastro da CVM em 10/11/2026: nada se lia, nenhum fato se confirmava)."""
    url = f"{SITE}/dados/cad_cia_aberta.csv"
    pesquisador, _ = _pesquisador(tmp_path, {url: CSV_DA_CVM})
    baixado = pesquisador.baixar_documento(url)
    assert baixado["ok"] and baixado["tipo"] == "csv"
    sha = str(baixado["sha256"])
    extracao = pesquisador.extrair(sha, contem=["PETROBRAS"])
    assert extracao["ok"] and extracao["tabelas"]  # type: ignore[index]
    fato = pesquisador.validar_fato(
        "CNPJ da Petrobras no cadastro da CVM",
        "33.000.167/0001-01",
        "33.000.167/0001-01 | PETRÓLEO BRASILEIRO S.A. - PETROBRAS",
        sha,
    )
    assert fato["situacao"] == "confirmado", fato


@pytest.mark.parametrize("sha", ["../../etc/passwd", "abc", "z" * 64, "0" * 64])
def test_extrair_recusa_hash_invalido_ou_desconhecido(tmp_path: Path, sha: str):
    pesquisador, _ = _pesquisador(tmp_path, {})
    assert pesquisador.extrair(sha)["ok"] is False


def test_extrair_com_docling_recusa_quando_nao_instalado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from pesquisa import leitores

    monkeypatch.setattr(leitores, "docling_instalado", lambda: False)
    pesquisador, _ = _pesquisador(tmp_path, {f"{SITE}/a.pdf": PDF})
    sha = str(pesquisador.baixar_documento(f"{SITE}/a.pdf")["sha256"])
    assert "Docling" in pesquisador.extrair(sha, motor="docling")["motivo"]  # type: ignore[operator]
    assert pesquisador.extrair(sha, motor="outro")["ok"] is False


def test_validar_fato_confirma_trecho_real_e_pendencia_para_inventado(tmp_path: Path):
    pesquisador, _ = _pesquisador(tmp_path, {f"{SITE}/a.pdf": PDF})
    sha = str(pesquisador.baixar_documento(f"{SITE}/a.pdf")["sha256"])
    certo = pesquisador.validar_fato(
        "Alfa tem 120 MW",
        "120",
        "Parque Alfa 120 MW CNPJ 12.345.678/0001-90",
        sha,
        exigir_no_trecho=["12345678000190"],
    )
    inventado = pesquisador.validar_fato(
        "Alfa tem 300 MW", "300", "Parque Alfa 300 MW em Sobral", sha
    )
    assert certo["situacao"] == "confirmado" and certo["onde"] == "pagina 1"
    assert inventado["situacao"] == "pendente"
    assert pesquisador.estado()["memoria"]["fato"] == 2  # type: ignore[index]


def test_validar_fato_de_arquivo_desconhecido_responde_erro(tmp_path: Path):
    pesquisador, _ = _pesquisador(tmp_path, {})
    assert (
        pesquisador.validar_fato("a", "1", "trecho qualquer longo", "0" * 64)["ok"]
        is False
    )
