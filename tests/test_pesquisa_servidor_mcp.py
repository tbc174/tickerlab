"""O servidor MCP do bot de pesquisa responde às ferramentas (precisa do pacote `mcp` 2.x, que só
está no ambiente do bot: sem ele, estes testes são pulados)."""

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.mcpserver")

from pesquisa.pesquisador import Pesquisador
from pesquisa.servidor_mcp import criar_servidor
from tests.ajudantes_da_pesquisa import (
    ClienteFalso,
    html_com_links,
    pdf_com_texto,
    sem_docling,  # noqa: F401 (autouse)
)

SITE = "https://dados.exemplo.gov.br"
PDF = pdf_com_texto(["Parque Alfa 120 MW"])


def _servidor(tmp_path: Path):
    cliente = ClienteFalso(
        {f"{SITE}/": html_com_links("Início", [("/a.pdf", "a")]), f"{SITE}/a.pdf": PDF}
    )
    return criar_servidor(Pesquisador(tmp_path / "d", cliente))


def _chamar(servidor, nome: str, argumentos: dict) -> dict:
    resultado = asyncio.run(servidor.call_tool(nome, argumentos))
    estruturado = getattr(resultado, "structuredContent", None)
    if estruturado is None:
        import json

        estruturado = json.loads(resultado.content[0].text)
    return estruturado.get("result", estruturado)


def test_servidor_lista_as_seis_ferramentas(tmp_path: Path):
    ferramentas = asyncio.run(_servidor(tmp_path).list_tools())
    nomes = {ferramenta.name for ferramenta in ferramentas}
    assert nomes == {
        "iniciar_rodada",
        "buscar_pagina",
        "baixar_documento",
        "extrair",
        "validar_fato",
        "estado_da_rodada",
    }


def test_fluxo_completo_pelo_servidor(tmp_path: Path):
    servidor = _servidor(tmp_path)
    assert _chamar(servidor, "iniciar_rodada", {"hipotese": "Alfa tem 120 MW"})["ok"]
    pagina = _chamar(servidor, "buscar_pagina", {"url": f"{SITE}/"})
    assert pagina["titulo"] == "Início"
    baixado = _chamar(servidor, "baixar_documento", {"url": f"{SITE}/a.pdf"})
    sha = baixado["sha256"]
    texto = _chamar(servidor, "extrair", {"sha256": sha})
    assert "Parque Alfa 120 MW" in texto["blocos"][0]["texto"]
    veredito = _chamar(
        servidor,
        "validar_fato",
        {
            "afirmacao": "Alfa 120 MW",
            "valor": "120",
            "trecho": "Parque Alfa 120 MW",
            "sha256": sha,
        },
    )
    assert veredito["situacao"] == "confirmado"
    assert _chamar(servidor, "estado_da_rodada", {})["buscas"] == "1/12"
