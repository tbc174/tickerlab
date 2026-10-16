"""A primeira cópia de cada página de negócio no Internet Archive (base/arquivo/wayback.py; ADR 0082,
série 5 do plano de M&A, passo 4). Tudo aqui é inventado: o site e as páginas não existem."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from base.arquivo import assessorias, coleta, fontes, wayback
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from src import acervo
from src.banco import coletas

AGORA = datetime(2026, 10, 18, 6, tzinfo=UTC)
IGC = assessorias.Assessoria(
    "teste", "https://www.assessoria.com.br", r"/transactions/[^/]+"
)
PAGINA_1 = IGC.site + "/transactions/a-x-e-adquirida-pela-y"
PAGINA_2 = IGC.site + "/transactions/a-z-vendeu-participacao-a-w"
CDX_1 = (
    b'[["timestamp","original","statuscode","digest"],["20260412042937","x","200","D"]]'
)
FORA_DO_AR = (
    b"<html><head><title>Internet Archive: Temporarily Offline</title></head></html>"
)


def _nao_existe(url: str) -> requests.HTTPError:
    resposta = requests.Response()
    resposta.status_code, resposta.url = 404, url
    return requests.HTTPError("404", response=resposta)


class Arquivo:
    """O Internet Archive em memória: url -> conteúdo (ou uma lista, uma resposta por pedido)."""

    def __init__(self, respostas: dict[str, object], robots: bytes | None = None):
        self.respostas = respostas
        self.robots = robots
        self.lidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None):
        self.lidos.append(url)
        if url == wayback.ROBOTS:
            if self.robots is None:
                raise _nao_existe(url)
            return Resposta(url, self.robots, {})
        resposta = self.respostas[url]
        if isinstance(resposta, list):
            resposta = resposta.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return Resposta(url, resposta, {})

    def cabecalhos(self, url):
        return {}

    def baixar(self, url, destino: Path):
        raise AssertionError("o Wayback é lido pela consulta, nunca baixado inteiro")


def _guardar_paginas(banco, *paginas: str) -> None:
    with banco.begin() as c:
        for pagina in paginas:
            caminho = acervo.guardar_original(
                "assessoria-teste", pagina, b"<html>", AGORA
            )
            coletas.registrar(
                c, "assessoria-teste", pagina, b"<html>", "ok", agora=AGORA,
                caminho_do_original=caminho,
            )  # fmt: skip


def test_a_consulta_volta_para_a_pagina():
    consulta = wayback.consulta(PAGINA_1)
    assert consulta.startswith(wayback.CDX + "?")
    assert "output=json" in consulta
    assert wayback.pagina_da_consulta(consulta) == PAGINA_1


def test_descobrir_le_o_robots_e_pede_uma_consulta_por_pagina_guardada(banco):
    _guardar_paginas(banco, PAGINA_2, PAGINA_1)
    arquivo = Arquivo({}, robots=b"User-agent: *\nDisallow: /control/\n")
    alvos = wayback.descobrir(IGC)(arquivo, AGORA)
    assert arquivo.lidos == [wayback.ROBOTS]
    assert [a.url for a in alvos] == [
        wayback.consulta(PAGINA_1),
        wayback.consulta(PAGINA_2),
    ]
    assert all(a.extensao == ".json" for a in alvos)


def test_robots_que_nao_existe_nao_proibe(banco):
    _guardar_paginas(banco, PAGINA_1)
    assert len(wayback.descobrir(IGC)(Arquivo({}, robots=None), AGORA)) == 1


def test_robots_que_proibe_a_consulta_para_tudo(banco):
    _guardar_paginas(banco, PAGINA_1)
    arquivo = Arquivo({}, robots=b"User-agent: *\nDisallow: /cdx/\n")
    with pytest.raises(ErroDeDescoberta, match="robots"):
        wayback.descobrir(IGC)(arquivo, AGORA)


def test_sem_pagina_guardada_e_falha(banco):
    with pytest.raises(ErroDeDescoberta, match="nenhuma página"):
        wayback.descobrir(IGC)(Arquivo({}, robots=b""), AGORA)


def test_fora_do_ar_tenta_de_novo_e_guarda_a_resposta_boa(banco, tmp_path, monkeypatch):
    esperas: list[float] = []
    monkeypatch.setattr(wayback.time, "sleep", esperas.append)
    _guardar_paginas(banco, PAGINA_1)
    arquivo = Arquivo(
        {wayback.consulta(PAGINA_1): [FORA_DO_AR, requests.ConnectionError(), CDX_1]},
        robots=b"",
    )
    resultado = coleta.arquivar(
        wayback.fonte(IGC), arquivo, AGORA, tmp_path / "t", pausa=0
    )
    assert (resultado.novos, resultado.falhas) == (1, [])
    assert len(esperas) == 2
    with banco.connect() as c:
        guardada = coletas.original_mais_recente(c, wayback.consulta(PAGINA_1))
    assert guardada == CDX_1


def test_fora_do_ar_tres_vezes_e_falha_registrada(banco, tmp_path, monkeypatch):
    monkeypatch.setattr(wayback.time, "sleep", lambda s: None)
    _guardar_paginas(banco, PAGINA_1)
    consulta = wayback.consulta(PAGINA_1)
    arquivo = Arquivo({consulta: [FORA_DO_AR] * wayback.TENTATIVAS}, robots=b"")
    resultado = coleta.arquivar(
        wayback.fonte(IGC), arquivo, AGORA, tmp_path / "t", pausa=0
    )
    assert resultado.falhas == [consulta]


def test_consulta_ja_guardada_nao_e_feita_de_novo(banco, tmp_path):
    _guardar_paginas(banco, PAGINA_1)
    arquivo = Arquivo({wayback.consulta(PAGINA_1): CDX_1}, robots=b"")
    fonte = wayback.fonte(IGC)
    coleta.arquivar(fonte, arquivo, AGORA, tmp_path / "t", pausa=0)
    segunda = coleta.arquivar(fonte, arquivo, AGORA, tmp_path / "t", pausa=0)
    assert (segunda.novos, segunda.pulados) == (0, 1)


def test_wayback_no_catalogo_semanal_depois_da_assessoria():
    ids = [f.id for f in fontes.FONTES]
    assert ids.index("wayback-igc") > ids.index("assessoria-igc")
    fonte = fontes.POR_ID["wayback-igc"]
    assert (fonte.grupo, fonte.tipo) == ("semanal", "json")
    assert fonte.pausa_minima >= 3


def test_wayback_so_pesquisa_ate_o_parecer():
    assert "research" in coletas.licenca_da_fonte("wayback-igc")
    assert coletas.revenda_da_fonte("wayback-igc") == coletas.SO_USO_INTERNO
