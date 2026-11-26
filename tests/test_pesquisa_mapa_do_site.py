"""Mapa do site pelo Firecrawl hospedado (`/v2/map`): descobrir os endereços reais de uma fonte antes de
buscar, em vez de chutar (63 das 73 recusas da linha de base de 26/11/2026 eram 404 de endereço chutado).
Mesmo porteiro, mesma trava de parâmetro cpf e mesmo teto de créditos da raspagem. Sem rede: o `post` é
dublê. A chave dos testes é inventada; o número de CPF é montado na hora e não é de ninguém."""

from pathlib import Path

import pytest

from pesquisa import agente, renderizacao
from pesquisa.pesquisador import Pesquisador
from pesquisa.renderizacao import (
    ContadorDeCreditos,
    EnvioBarrado,
    Porteiro,
    TetoDeCreditos,
)
from pesquisa.rodada import Limites
from tests.ajudantes_da_pesquisa import ClienteFalso, html_com_links

CHAVE = "chave-de-teste"
SITE = "https://dados.exemplo.gov.br"


def _cpf_inventado(base: str = "123456789") -> str:
    """Completa 9 dígitos com os dois verificadores do CPF (número de teste, de ninguém)."""
    digitos = [int(d) for d in base]
    for tamanho in (9, 10):
        soma = sum(d * (tamanho + 1 - i) for i, d in enumerate(digitos[:tamanho]))
        digitos.append((soma * 10 % 11) % 10)
    return "".join(map(str, digitos))


class _Resposta:
    def __init__(self, corpo: object, status_code: int = 200):
        self._corpo = corpo
        self.status_code = status_code

    def json(self) -> object:
        if isinstance(self._corpo, Exception):
            raise self._corpo
        return self._corpo


class _Post:
    """Dublê do `requests.post`: guarda cada pedido e devolve o corpo combinado."""

    def __init__(self, corpo: object, status_code: int = 200):
        self.corpo = corpo
        self.status_code = status_code
        self.pedidos: list[dict] = []

    def __call__(
        self, rota: str, *, json: dict, headers: dict, timeout: int
    ) -> _Resposta:
        self.pedidos.append({"rota": rota, "json": json, "headers": headers})
        return _Resposta(self.corpo, self.status_code)


def _mapa(*links: dict) -> dict:
    return {"success": True, "links": list(links)}


MAPA_PADRAO = _mapa(
    {"url": f"{SITE}/dataset/prouni", "title": "ProUni", "description": "bolsas"},
    {"url": f"{SITE}/sobre"},
)


def _mapeador(post: _Post, *, termos=(), teto: int = 10) -> tuple:
    contador = ContadorDeCreditos(teto)
    mapear = renderizacao.mapeador_hospedado(
        CHAVE, Porteiro(termos), contador, post=post
    )
    return mapear, contador


# --- a chamada --------------------------------------------------------------------------------


def test_pede_o_map_sem_proxy_sem_localizacao_e_sem_subdominio():
    post = _Post(MAPA_PADRAO)
    mapear, contador = _mapeador(post)
    links = mapear(f"{SITE}/")
    assert links == [
        {"url": f"{SITE}/dataset/prouni", "titulo": "ProUni"},
        {"url": f"{SITE}/sobre", "titulo": ""},
    ]
    (pedido,) = post.pedidos
    assert pedido["rota"] == "https://api.firecrawl.dev/v2/map"
    assert pedido["headers"] == {"Authorization": f"Bearer {CHAVE}"}
    corpo = pedido["json"]
    assert corpo["url"] == f"{SITE}/"
    assert corpo["includeSubdomains"] is False
    assert corpo["limit"] == renderizacao.LIMITE_DO_MAPA
    # `location` escolhe proxy por país; `proxy` e `threatProtection` não entram.
    assert not {"location", "proxy", "threatProtection", "search"} & corpo.keys()
    assert (contador.creditos, contador.mapas, contador.paginas) == (1, 1, 0)


@pytest.mark.parametrize(
    "corpo, status",
    [
        ({"success": False, "error": "Map timed out"}, 408),
        ({"success": False}, 200),
        (ValueError("sem JSON"), 500),
        ({"success": True, "links": "não é lista"}, 200),
    ],
)
def test_mapa_que_falhou_levanta_erro_e_conta_o_credito(corpo: object, status: int):
    mapear, contador = _mapeador(_Post(corpo, status))
    with pytest.raises(RuntimeError):
        mapear(f"{SITE}/")
    # A doc não diz se o /map com erro é cobrado: conta, para o teto nunca ser passado.
    assert contador.creditos == 1


def test_a_chave_nao_aparece_na_mensagem_de_erro():
    mapear, _ = _mapeador(_Post({"success": False, "error": "x"}, 401))
    with pytest.raises(RuntimeError) as erro:
        mapear(f"{SITE}/")
    assert CHAVE not in str(erro.value)


def test_links_fora_do_formato_sao_ignorados():
    post = _Post(
        _mapa(
            {"url": f"{SITE}/a", "title": "A" * 500},
            {"title": "sem url"},
            "não é objeto",
            {"url": 42},
        )
    )
    mapear, _ = _mapeador(post)
    (link,) = mapear(f"{SITE}/")
    assert link["url"] == f"{SITE}/a"
    assert len(link["titulo"]) <= renderizacao.TAMANHO_DO_TITULO_DO_MAPA


# --- porteiro, cpf e teto antes do envio -------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    ["https://empresa-ficticia.com.br/", f"{SITE}/busca/Empresa%20Fict%C3%ADcia"],
)
def test_termo_barrado_no_endereco_nao_vai(url: str):
    post = _Post(MAPA_PADRAO)
    mapear, contador = _mapeador(post, termos=["empresa ficticia"])
    with pytest.raises(EnvioBarrado) as erro:
        mapear(url)
    assert post.pedidos == [] and contador.creditos == 0
    assert "ficticia" not in str(erro.value).lower()


def test_parametro_cpf_no_endereco_nao_vai():
    post = _Post(MAPA_PADRAO)
    mapear, _ = _mapeador(post)
    with pytest.raises(EnvioBarrado):
        mapear(f"{SITE}/consulta?cpf={_cpf_inventado()}")
    assert post.pedidos == []


def test_provedor_com_preco_proprio_nao_vai():
    post = _Post(MAPA_PADRAO)
    mapear, _ = _mapeador(post)
    with pytest.raises(EnvioBarrado):
        mapear("https://www.linkedin.com/company/x")
    assert post.pedidos == []


def test_teto_vale_para_mapa_e_raspagem_juntos():
    contador = ContadorDeCreditos(2)
    contador.registrar(1)  # uma raspagem já feita
    post = _Post(MAPA_PADRAO)
    mapear = renderizacao.mapeador_hospedado(CHAVE, Porteiro([]), contador, post=post)
    mapear(f"{SITE}/")
    with pytest.raises(TetoDeCreditos):
        mapear(f"{SITE}/")
    assert len(post.pedidos) == 1 and contador.creditos == 2


# --- escolher pelo ambiente ---------------------------------------------------------------------


def test_sem_chave_ou_sem_arquivo_de_termos_nao_ha_mapa(tmp_path: Path):
    assert renderizacao.escolher_mapeador({}) is None
    ausente = {
        "FIRECRAWL_API_KEY": CHAVE,
        "TICKERLAB_PESQUISA_TERMOS_BARRADOS": str(tmp_path / "nao-existe.txt"),
    }
    assert renderizacao.escolher_mapeador(ausente) is None


def test_com_chave_e_termos_o_mapa_liga_com_o_teto_do_ambiente(tmp_path: Path):
    termos = tmp_path / "termos.txt"
    termos.write_text("# comentário\n", encoding="utf-8")
    contador = ContadorDeCreditos()
    mapear = renderizacao.escolher_mapeador(
        {
            "FIRECRAWL_API_KEY": CHAVE,
            "TICKERLAB_PESQUISA_TERMOS_BARRADOS": str(termos),
            "TICKERLAB_FIRECRAWL_TETO": "3",
        },
        contador=contador,
    )
    assert mapear is not None and contador.teto == 3


# --- no coletor -----------------------------------------------------------------------------------


class _MapeadorFalso:
    def __init__(self, links: list[dict[str, str]] | Exception):
        self.links = links
        self.chamadas: list[str] = []

    def __call__(self, url: str) -> list[dict[str, str]]:
        self.chamadas.append(url)
        if isinstance(self.links, Exception):
            raise self.links
        return self.links


def _pesquisador(
    tmp_path: Path,
    mapeador: _MapeadorFalso | None,
    paginas: dict | None = None,
    limites: Limites | None = None,
) -> tuple[Pesquisador, ClienteFalso]:
    falso = ClienteFalso(paginas or {})
    pesquisador = Pesquisador(tmp_path / "d", falso, mapeador=mapeador, limites=limites)
    assert pesquisador.iniciar_rodada("o ProUni publica as bolsas por ano")["ok"]
    return pesquisador, falso


def test_sem_mapeador_recusa_com_o_motivo(tmp_path: Path):
    pesquisador, _ = _pesquisador(tmp_path, None)
    resposta = pesquisador.mapear_site(f"{SITE}/")
    assert resposta["ok"] is False and "Firecrawl" in resposta["motivo"]  # type: ignore[operator]


def test_mapa_devolve_so_links_do_site_e_eles_ficam_a_um_passo(tmp_path: Path):
    mapeador = _MapeadorFalso(
        [
            {"url": f"{SITE}/dataset/prouni", "titulo": "ProUni"},
            {"url": f"{SITE}/dataset/prouni", "titulo": "repetido"},
            {"url": f"{SITE}/prouni-2024.pdf", "titulo": ""},
            {"url": f"{SITE}/sobre", "titulo": "Quem somos"},
            {"url": "https://outro.exemplo.com/x", "titulo": "fora"},
            {"url": "http://127.0.0.1/admin", "titulo": "interno"},
            {"url": "ftp://dados.exemplo.gov.br/x", "titulo": "esquema"},
        ]
    )
    pagina = html_com_links("ProUni", [])
    pesquisador, _ = _pesquisador(
        tmp_path, mapeador, {f"{SITE}/dataset/prouni": pagina}
    )
    resposta = pesquisador.mapear_site(f"{SITE}/", "prouni")
    assert resposta["ok"] is True and "aviso" in resposta
    assert [link["url"] for link in resposta["links"]] == [  # type: ignore[union-attr]
        f"{SITE}/prouni-2024.pdf",
        f"{SITE}/dataset/prouni",
    ]
    assert mapeador.chamadas == [f"{SITE}/"]
    assert pesquisador.rodada is not None
    assert pesquisador.rodada.profundidades[f"{SITE}/dataset/prouni"] == 1
    assert pesquisador.buscar_pagina(f"{SITE}/dataset/prouni")["ok"] is True


def test_mapa_corta_na_quantidade_maxima(tmp_path: Path):
    from pesquisa import coletor

    links = [{"url": f"{SITE}/p{n}", "titulo": ""} for n in range(400)]
    pesquisador, _ = _pesquisador(tmp_path, _MapeadorFalso(links))
    resposta = pesquisador.mapear_site(f"{SITE}/")
    assert len(resposta["links"]) == coletor.MAXIMO_DE_LINKS  # type: ignore[arg-type]
    assert resposta["links_cortados"] is True


def test_robots_que_proibe_o_caminho_impede_o_mapa(tmp_path: Path):
    mapeador = _MapeadorFalso([])
    pesquisador, _ = _pesquisador(tmp_path, mapeador)
    resposta = pesquisador.mapear_site(f"{SITE}/privado/")
    assert resposta["ok"] is False and mapeador.chamadas == []


def test_endereco_interno_nao_chega_ao_mapeador(tmp_path: Path):
    mapeador = _MapeadorFalso([])
    pesquisador, _ = _pesquisador(tmp_path, mapeador)
    assert pesquisador.mapear_site("http://169.254.169.254/")["ok"] is False
    assert mapeador.chamadas == []


def test_limite_de_mapas_por_rodada(tmp_path: Path):
    mapeador = _MapeadorFalso([])
    pesquisador, _ = _pesquisador(tmp_path, mapeador, limites=Limites(mapas=1))
    assert pesquisador.mapear_site(f"{SITE}/")["ok"] is True
    segunda = pesquisador.mapear_site(f"{SITE}/")
    assert "1 mapa" in segunda["limite"]  # type: ignore[operator]
    assert len(mapeador.chamadas) == 1
    assert pesquisador.estado()["mapas"] == "1/1"  # type: ignore[index]


@pytest.mark.parametrize(
    "erro, chave",
    [
        (EnvioBarrado("o endereço tem um termo da lista de barrados"), "motivo"),
        (TetoDeCreditos("teto de 10 créditos do Firecrawl atingido"), "limite"),
        (RuntimeError("Map timed out"), "motivo"),
    ],
)
def test_falha_do_mapa_vira_resposta_e_nao_derruba_nem_e_lembrada(
    tmp_path: Path, erro: Exception, chave: str
):
    pesquisador, _ = _pesquisador(tmp_path, _MapeadorFalso(erro))
    resposta = pesquisador.mapear_site(f"{SITE}/")
    assert resposta["ok"] is False and chave in resposta
    assert pesquisador.memoria.negativo_valido(f"{SITE}/") is None


def test_sem_rodada_o_mapa_pede_a_hipotese(tmp_path: Path):
    pesquisador = Pesquisador(
        tmp_path / "d", ClienteFalso({}), mapeador=_MapeadorFalso([])
    )
    assert "hipótese" in pesquisador.mapear_site(f"{SITE}/")["motivo"]  # type: ignore[operator]


# --- o agente vê a ferramenta ---------------------------------------------------------------------


def test_agente_oferece_e_executa_o_mapa(tmp_path: Path):
    nomes = {f["function"]["name"] for f in agente.FERRAMENTAS}
    assert "mapear_site" in nomes
    assert "mapear_site" in agente.INSTRUCOES
    mapeador = _MapeadorFalso([{"url": f"{SITE}/a", "titulo": "A"}])
    pesquisador, _ = _pesquisador(tmp_path, mapeador)
    resposta = agente.executar(
        agente._acoes(pesquisador),
        "mapear_site",
        '{"url": "https://dados.exemplo.gov.br/", "termo": "bolsas"}',
    )
    assert resposta["ok"] is True
    assert mapeador.chamadas == [f"{SITE}/"]


# --- achados P2 da revisão de segurança (PR 1346) -------------------------------------------------


@pytest.mark.parametrize("caminho", ["/", "/outra/pagina"])
def test_site_que_bloqueou_o_bot_nao_vai_ao_mapa(tmp_path: Path, caminho: str):
    from base.arquivo.coleta import BloqueioAntiRobo

    mapeador = _MapeadorFalso([])
    pesquisador, _ = _pesquisador(
        tmp_path, mapeador, {f"{SITE}{caminho}": BloqueioAntiRobo("desafio")}
    )
    assert pesquisador.buscar_pagina(f"{SITE}{caminho}")["ok"] is False
    resposta = pesquisador.mapear_site(f"{SITE}/", "prouni")
    assert resposta["ok"] is False and "bloque" in resposta["motivo"]  # type: ignore[operator]
    assert mapeador.chamadas == []


def test_site_com_404_lembrado_ainda_pode_ser_mapeado(tmp_path: Path):
    from tests.ajudantes_da_pesquisa import erro_http

    mapeador = _MapeadorFalso([])
    pesquisador, _ = _pesquisador(tmp_path, mapeador, {f"{SITE}/chute": erro_http(404)})
    assert pesquisador.buscar_pagina(f"{SITE}/chute")["ok"] is False
    assert pesquisador.mapear_site(f"{SITE}/")["ok"] is True
    assert len(mapeador.chamadas) == 1


def test_mapa_que_caiu_no_caminho_conta_o_credito():
    import requests

    def post_que_cai(*args: object, **kwargs: object) -> None:
        raise requests.Timeout("sem resposta")

    contador = ContadorDeCreditos(5)
    mapear = renderizacao.mapeador_hospedado(
        CHAVE, Porteiro([]), contador, post=post_que_cai
    )
    with pytest.raises(requests.Timeout):
        mapear(f"{SITE}/")
    assert (contador.creditos, contador.mapas) == (1, 1)


def test_raspagem_que_caiu_no_caminho_conta_o_credito():
    import requests

    def post_que_cai(*args: object, **kwargs: object) -> None:
        raise requests.ConnectionError("caiu")

    contador = ContadorDeCreditos(5)
    renderizar = renderizacao.renderizador_hospedado(
        CHAVE, Porteiro([]), contador, post=post_que_cai
    )
    with pytest.raises(requests.ConnectionError):
        renderizar(f"{SITE}/painel")
    assert (contador.creditos, contador.paginas) == (1, 1)


# --- revisão do Codex (PR 1346) ----------------------------------------------------------------


def test_o_termo_nunca_sai_do_pc():
    """Ao Firecrawl vai só o endereço público do site; o termo filtra aqui (P0 do Revisor)."""
    post = _Post(MAPA_PADRAO)
    mapear, _ = _mapeador(post)
    mapear(f"{SITE}/")
    assert set(post.pedidos[0]["json"]) == {
        "url",
        "includeSubdomains",
        "limit",
        "timeout",
    }


def test_termo_filtra_aqui_sem_acento_nem_caixa(tmp_path: Path):
    mapeador = _MapeadorFalso(
        [
            {"url": f"{SITE}/dados/mec-prouni", "titulo": "Bolsas concedidas"},
            {"url": f"{SITE}/dados/mec-fies", "titulo": "Bolsas do Fies"},
            {"url": f"{SITE}/dados/prouni-cursos", "titulo": "Cursos"},
        ]
    )
    pesquisador, _ = _pesquisador(tmp_path, mapeador)
    resposta = pesquisador.mapear_site(f"{SITE}/", "ProUni BOLSAS")
    assert [link["url"] for link in resposta["links"]] == [f"{SITE}/dados/mec-prouni"]  # type: ignore[union-attr]
    assert mapeador.chamadas == [f"{SITE}/"]


def test_termo_sem_achado_devolve_lista_vazia_com_dica(tmp_path: Path):
    mapeador = _MapeadorFalso([{"url": f"{SITE}/sobre", "titulo": "Quem somos"}])
    pesquisador, _ = _pesquisador(tmp_path, mapeador)
    resposta = pesquisador.mapear_site(f"{SITE}/", "prouni")
    assert resposta["ok"] is True and resposta["links"] == []
    assert resposta["no_mapa"] == 1 and "termo" in resposta["dica"]  # type: ignore[operator]


def test_mapa_respeita_o_limite_de_candidatos(tmp_path: Path):
    """O mapa conta o endereço como candidato da rodada, como a busca (P1 do Revisor)."""
    mapeador = _MapeadorFalso([])
    pesquisador, _ = _pesquisador(tmp_path, mapeador, limites=Limites(candidatos=1))
    assert pesquisador.mapear_site(f"{SITE}/")["ok"] is True
    outro = pesquisador.mapear_site("https://outro.exemplo.gov.br/")
    assert "candidatos" in outro["limite"]  # type: ignore[operator]
    assert mapeador.chamadas == [f"{SITE}/"]


# --- P2 da re-revisão de segurança (fdc8f99) -----------------------------------------------------


@pytest.mark.parametrize(
    "variante",
    [
        "http://dados.exemplo.gov.br/",
        "https://dados.exemplo.gov.br:443/",
        "https://DADOS.exemplo.gov.br/",
        "https://alguem@dados.exemplo.gov.br/",
    ],
)
def test_bloqueio_vale_para_o_host_em_qualquer_forma(tmp_path: Path, variante: str):
    from base.arquivo.coleta import BloqueioAntiRobo

    mapeador = _MapeadorFalso([])
    pesquisador, _ = _pesquisador(
        tmp_path, mapeador, {f"{SITE}/painel": BloqueioAntiRobo("desafio")}
    )
    pesquisador.buscar_pagina(f"{SITE}/painel")
    assert pesquisador.mapear_site(variante)["ok"] is False
    assert mapeador.chamadas == []


@pytest.mark.parametrize("status", [401, 403, 429, "desafio"])
def test_bloqueio_ao_ler_o_robots_impede_o_mapa_e_fica_lembrado(
    tmp_path: Path, status: object
):
    from base.arquivo.coleta import BloqueioAntiRobo, Resposta
    from tests.ajudantes_da_pesquisa import erro_http

    class _ClienteBloqueadoNoRobots(ClienteFalso):
        def ler(self, url: str) -> Resposta:
            if url.endswith("/robots.txt"):
                if status == "desafio":
                    raise BloqueioAntiRobo("cf-mitigated: challenge")
                raise erro_http(status)  # type: ignore[arg-type]
            return super().ler(url)

    mapeador = _MapeadorFalso([])
    pesquisador = Pesquisador(
        tmp_path / "d", _ClienteBloqueadoNoRobots({}), mapeador=mapeador
    )
    pesquisador.iniciar_rodada("h")
    resposta = pesquisador.mapear_site(f"{SITE}/")
    assert resposta["ok"] is False and "não se contorna" in resposta["motivo"]  # type: ignore[operator]
    assert mapeador.chamadas == []
    assert pesquisador.mapear_site(f"{SITE}/")["ok"] is False  # lembrado


def test_robots_ausente_404_ainda_deixa_mapear(tmp_path: Path):
    mapeador = _MapeadorFalso([])
    pesquisador = Pesquisador(
        tmp_path / "d", ClienteFalso({}, robots=None), mapeador=mapeador
    )
    pesquisador.iniciar_rodada("h")
    assert pesquisador.mapear_site(f"{SITE}/")["ok"] is True
