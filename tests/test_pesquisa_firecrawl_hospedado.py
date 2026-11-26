"""Firecrawl hospedado no bot de pesquisa: porteiro, teto de créditos, cascata e a chamada (sem rede: o
`post` é dublê). A chave dos testes é inventada; nenhum CPF aqui é de alguém: o número é montado na hora."""

from pathlib import Path

import pytest

from pesquisa import renderizacao
from pesquisa.renderizacao import (
    ContadorDeCreditos,
    EnvioBarrado,
    Porteiro,
    TetoDeCreditos,
)

CHAVE = "chave-de-teste"
PAGINA = "https://dados.exemplo.gov.br/painel"


def _cpf_inventado(base: str = "123456789") -> str:
    """Completa 9 dígitos com os dois verificadores do CPF (número de teste, de ninguém)."""
    digitos = [int(d) for d in base]
    for tamanho in (9, 10):
        soma = sum(d * (tamanho + 1 - i) for i, d in enumerate(digitos[:tamanho]))
        digitos.append((soma * 10 % 11) % 10)
    return "".join(map(str, digitos))


class _Resposta:
    def __init__(self, corpo: dict, status_code: int = 200):
        self._corpo = corpo
        self.status_code = status_code

    def json(self) -> dict:
        return self._corpo


class _Post:
    """Dublê do `requests.post`: guarda cada pedido e devolve o corpo combinado."""

    def __init__(self, corpo: dict, status_code: int = 200):
        self.corpo = corpo
        self.status_code = status_code
        self.pedidos: list[dict] = []

    def __call__(
        self, rota: str, *, json: dict, headers: dict, timeout: int
    ) -> _Resposta:
        self.pedidos.append({"rota": rota, "json": json, "headers": headers})
        return _Resposta(self.corpo, self.status_code)


def _ok(creditos: int | None = None, status: int = 200) -> dict:
    metadados: dict = {"url": PAGINA + "/", "statusCode": status}
    if creditos is not None:
        metadados["creditsUsed"] = creditos
    return {
        "success": True,
        "data": {"rawHtml": "<p>painel</p>", "metadata": metadados},
    }


def _hospedado(post: _Post, *, termos=(), teto: int = 10) -> tuple:
    contador = ContadorDeCreditos(teto)
    renderizar = renderizacao.renderizador_hospedado(
        CHAVE, Porteiro(termos), contador, post=post
    )
    return renderizar, contador


# --- a chamada --------------------------------------------------------------------------------


def test_hospedado_pede_so_o_html_sem_proxy_anti_robo_e_sem_guardar_no_indice():
    post = _Post(_ok())
    renderizar, _ = _hospedado(post)
    assert renderizar(PAGINA) == (PAGINA + "/", b"<p>painel</p>")
    (pedido,) = post.pedidos
    assert pedido["rota"] == "https://api.firecrawl.dev/v2/scrape"
    assert pedido["headers"] == {"Authorization": f"Bearer {CHAVE}"}
    # Formato travado: qualquer opção nova (formato com LLM, PDF por página, ZDR, PII...) muda o custo
    # máximo de uma chamada e tem de passar por CUSTO_MAXIMO_POR_CHAMADA.
    assert pedido["json"] == {
        "url": PAGINA,
        "formats": ["rawHtml"],
        "onlyMainContent": False,
        "proxy": "basic",
        "storeInCache": False,
        "timeout": renderizacao.TEMPO_DO_SERVICO_EM_MS,
        "parsers": [],
    }
    assert renderizacao.CUSTO_MAXIMO_POR_CHAMADA == 1


@pytest.mark.parametrize(
    ("corpo", "status_code"),
    [
        ({"success": False, "error": "tempo esgotado"}, 200),
        ({"success": True, "data": {}}, 200),
        (_ok(status=404), 200),
        (_ok(status=403), 200),
        ({"success": False, "error": "Payment required"}, 402),
    ],
)
def test_hospedado_sem_pagina_boa_levanta_erro(corpo: dict, status_code: int):
    renderizar, _ = _hospedado(_Post(corpo, status_code))
    with pytest.raises(RuntimeError):
        renderizar(PAGINA)


def test_a_chave_nao_aparece_na_mensagem_de_erro():
    renderizar, _ = _hospedado(_Post({"success": False, "error": "falhou"}))
    with pytest.raises(RuntimeError) as erro:
        renderizar(PAGINA)
    assert CHAVE not in str(erro.value)


# --- porteiro ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "molde",
    ["{d}", "{p}", "q={d}&x=1", "a/{d}/b", "x{d}y"],
)
def test_porteiro_recusa_endereco_com_cpf_valido(molde: str):
    digitos = _cpf_inventado()
    pontuado = f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    url = f"{PAGINA}?" + molde.format(d=digitos, p=pontuado)
    if molde == "x{d}y":
        url = f"{PAGINA}/x{digitos}y"
    post = _Post(_ok())
    renderizar, _ = _hospedado(post)
    with pytest.raises(EnvioBarrado) as erro:
        renderizar(url)
    assert digitos not in str(erro.value)
    assert post.pedidos == []


def test_porteiro_deixa_passar_onze_digitos_que_nao_sao_cpf():
    digitos = _cpf_inventado()
    errado = digitos[:-1] + str((int(digitos[-1]) + 1) % 10)
    Porteiro(()).conferir(f"{PAGINA}?id={errado}")
    Porteiro(()).conferir(
        f"{PAGINA}?cnpj=00000000000191&id=1{digitos}"
    )  # 12 dígitos seguidos


@pytest.mark.parametrize(
    "url",
    [
        "https://busca.exemplo.com/?q=Empresa+Fict%C3%ADcia+Alfa",
        "https://busca.exemplo.com/empresa-ficticia-alfa",
        "https://busca.exemplo.com/EMPRESA%20FICTICIA%20ALFA/x",
    ],
)
def test_porteiro_recusa_termo_barrado_sem_acento_nem_caixa(url: str):
    post = _Post(_ok())
    renderizar, _ = _hospedado(post, termos=["Empresa Fictícia Alfa"])
    with pytest.raises(EnvioBarrado) as erro:
        renderizar(url)
    assert "alfa" not in str(erro.value).lower()
    assert post.pedidos == []


def test_porteiro_le_os_termos_do_arquivo_fora_do_repositorio(tmp_path: Path):
    arquivo = tmp_path / "termos.txt"
    arquivo.write_text(
        "# comentário\n\nEmpresa Fictícia Alfa\n  Beta Ficta  \n", encoding="utf-8"
    )
    porteiro = renderizacao.porteiro_do_ambiente(
        {renderizacao.VARIAVEL_DOS_TERMOS_BARRADOS: str(arquivo)}
    )
    porteiro.conferir(
        "https://x.gov.br/comentario"
    )  # linha de comentário não vira termo
    with pytest.raises(EnvioBarrado):
        porteiro.conferir("https://x.gov.br/beta-ficta")


def test_arquivo_de_termos_dentro_do_repositorio_ou_ausente_e_recusado(tmp_path: Path):
    variavel = renderizacao.VARIAVEL_DOS_TERMOS_BARRADOS
    dentro = Path(renderizacao.__file__).resolve().parent / "README.md"
    with pytest.raises(ValueError, match="fora do repositório"):
        renderizacao.porteiro_do_ambiente({variavel: str(dentro)})
    with pytest.raises(ValueError, match="não existe"):
        renderizacao.porteiro_do_ambiente({variavel: str(tmp_path / "nao-ha.txt")})


# --- teto de créditos -------------------------------------------------------------------------


def test_contador_soma_o_que_a_resposta_diz_e_um_por_pagina_sem_a_informacao():
    renderizar, contador = _hospedado(_Post(_ok(creditos=3)))
    renderizar(PAGINA)
    assert (contador.paginas, contador.creditos) == (1, 3)
    renderizar2, contador2 = _hospedado(_Post(_ok()))
    renderizar2(PAGINA)
    assert (contador2.paginas, contador2.creditos) == (1, 1)


def test_no_teto_recusa_sem_chamar_o_servico():
    post = _Post(_ok(creditos=1))
    renderizar, contador = _hospedado(post, teto=3)
    for _ in range(3):
        renderizar(PAGINA)
    with pytest.raises(TetoDeCreditos):
        renderizar(PAGINA)
    assert len(post.pedidos) == 3
    assert contador.creditos == 3


@pytest.mark.parametrize("teto", range(8))
@pytest.mark.parametrize("pagina_com_erro", [False, True])
def test_gasto_do_processo_nunca_passa_do_teto(teto: int, pagina_com_erro: bool):
    """Com cada chamada custando até o máximo conhecido, o gasto nunca passa do teto, nem com
    página que volta com erro (que também é cobrada)."""
    corpo = _ok(
        creditos=renderizacao.CUSTO_MAXIMO_POR_CHAMADA,
        status=404 if pagina_com_erro else 200,
    )
    post = _Post(corpo)
    renderizar, contador = _hospedado(post, teto=teto)
    for _ in range(teto + 5):
        try:
            renderizar(PAGINA)
        except TetoDeCreditos:
            break
        except RuntimeError:
            continue
    assert contador.creditos <= teto
    assert len(post.pedidos) * renderizacao.CUSTO_MAXIMO_POR_CHAMADA <= teto


@pytest.mark.parametrize(
    "url",
    [
        "https://x.com/alguem",
        "https://www.linkedin.com/company/y",
        "https://mobile.twitter.com/z",
    ],
)
def test_endereco_de_provedor_com_preco_proprio_nao_vai(url: str):
    post = _Post(_ok())
    renderizar, _ = _hospedado(post)
    with pytest.raises(EnvioBarrado):
        renderizar(url)
    assert post.pedidos == []


def test_lista_de_termos_vazia_liga_com_aviso(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    monkeypatch.setattr(renderizacao, "crawl4ai_instalado", lambda: False)
    escolhido = renderizacao.escolher_renderizador(
        {renderizacao.VARIAVEL_DA_CHAVE: CHAVE}
    )
    assert escolhido is not None
    assert "vazia" in capsys.readouterr().err


# --- escolha e cascata ------------------------------------------------------------------------


def _sem_crawl4ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(renderizacao, "crawl4ai_instalado", lambda: False)


def test_sem_chave_nao_ha_hospedado(monkeypatch: pytest.MonkeyPatch):
    _sem_crawl4ai(monkeypatch)
    assert renderizacao.escolher_renderizador({}) is None


def test_com_chave_e_sem_crawl4ai_o_hospedado_e_o_unico(
    monkeypatch: pytest.MonkeyPatch,
):
    _sem_crawl4ai(monkeypatch)
    escolhido = renderizacao.escolher_renderizador(
        {renderizacao.VARIAVEL_DA_CHAVE: CHAVE}
    )
    assert (
        escolhido is not None
        and escolhido.__name__ == "renderizar_pelo_firecrawl_hospedado"
    )


def test_firecrawl_local_tem_preferencia_sobre_o_hospedado():
    ambiente = {
        renderizacao.VARIAVEL_DA_CHAVE: CHAVE,
        renderizacao.VARIAVEL_DO_FIRECRAWL: "http://127.0.0.1:3002",
    }
    escolhido = renderizacao.escolher_renderizador(ambiente)
    assert escolhido is not None and escolhido.__name__ == "renderizar_pelo_firecrawl"


def test_teto_vem_da_variavel(monkeypatch: pytest.MonkeyPatch):
    _sem_crawl4ai(monkeypatch)
    contador = ContadorDeCreditos(0)
    renderizacao.escolher_renderizador(
        {renderizacao.VARIAVEL_DA_CHAVE: CHAVE, renderizacao.VARIAVEL_DO_TETO: "7"},
        contador=contador,
    )
    assert contador.teto == 7
    with pytest.raises(ValueError, match="inteiro"):
        renderizacao.escolher_renderizador(
            {
                renderizacao.VARIAVEL_DA_CHAVE: CHAVE,
                renderizacao.VARIAVEL_DO_TETO: "muito",
            }
        )


def test_cascata_so_chama_o_firecrawl_quando_o_crawl4ai_falha(
    monkeypatch: pytest.MonkeyPatch,
):
    chamados: list[str] = []

    def crawl4ai_bom(url: str) -> tuple[str, bytes]:
        chamados.append("crawl4ai")
        return url, b"<p>crawl4ai</p>"

    def crawl4ai_ruim(url: str) -> tuple[str, bytes]:
        chamados.append("crawl4ai")
        raise RuntimeError("navegador não abriu")

    def firecrawl(url: str) -> tuple[str, bytes]:
        chamados.append("firecrawl")
        return url, b"<p>firecrawl</p>"

    assert (
        renderizacao.em_cascata(crawl4ai_bom, firecrawl)(PAGINA)[1]
        == b"<p>crawl4ai</p>"
    )
    assert chamados == ["crawl4ai"]
    chamados.clear()
    assert (
        renderizacao.em_cascata(crawl4ai_ruim, firecrawl)(PAGINA)[1]
        == b"<p>firecrawl</p>"
    )
    assert chamados == ["crawl4ai", "firecrawl"]


def test_cascata_devolve_o_ultimo_erro_quando_todos_falham():
    def ruim(url: str) -> tuple[str, bytes]:
        raise RuntimeError("primeiro")

    def barrado(url: str) -> tuple[str, bytes]:
        raise EnvioBarrado("barrado")

    with pytest.raises(EnvioBarrado):
        renderizacao.em_cascata(ruim, barrado)(PAGINA)


def test_com_chave_e_crawl4ai_a_ordem_e_crawl4ai_depois_firecrawl(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(renderizacao, "crawl4ai_instalado", lambda: True)
    monkeypatch.setattr(renderizacao, "renderizar", lambda url: (url, b"<p>local</p>"))
    escolhido = renderizacao.escolher_renderizador(
        {renderizacao.VARIAVEL_DA_CHAVE: CHAVE}
    )
    assert escolhido is not None and escolhido.__name__ == "renderizar_em_cascata"
    assert escolhido(PAGINA) == (PAGINA, b"<p>local</p>")


# --- correções da revisão de segurança (#1343) ------------------------------------------------


@pytest.fixture(autouse=True)
def _termos_padrao_vazio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """O arquivo padrão de termos (na pasta do bot) existe e está vazio, sem depender do PC."""
    arquivo = tmp_path / "termos-padrao.txt"
    arquivo.write_text("", encoding="utf-8")
    monkeypatch.setattr(renderizacao, "TERMOS_BARRADOS_PADRAO", arquivo)
    return arquivo


def _formas_do_cpf(d: str) -> list[str]:
    return [
        f"/edital/fulano-{d[:3]}-{d[3:6]}-{d[6:9]}-{d[9:]}",
        f"?q={d[:3]}+{d[3:6]}+{d[6:9]}+{d[9:]}",
        f"?q={d[:3]}%20{d[3:6]}%20{d[6:9]}%20{d[9:]}",
        f"?q={d[:3]}%252E{d[3:6]}%252E{d[6:9]}-{d[9:]}",
        f"?q={d[:3]},{d[3:6]},{d[6:9]},{d[9:]}",
        f"/{d[:3]}/{d[3:6]}/{d[6:9]}/{d[9:]}",
    ]


@pytest.mark.parametrize("indice", range(6))
def test_porteiro_acha_cpf_com_qualquer_separador_e_codificacao(indice: int):
    trecho = _formas_do_cpf(_cpf_inventado())[indice]
    with pytest.raises(EnvioBarrado):
        Porteiro(()).conferir("https://x.gov.br" + trecho)


@pytest.mark.parametrize(
    "url",
    [
        "https://x.gov.br/consulta.asp?razao=EMPRESA+FICT%CDCIA+ALFA",  # Latin-1
        "https://x.gov.br/ir?url=https%3A%2F%2Fy%2Fb%3Fq%3DEmpresa%2520Fict%25C3%25ADcia%2520Alfa",
        "https://x.gov.br/ir?u=Empresa%252BFict%2525C3%2525ADcia%252BAlfa",  # três vezes
    ],
)
def test_porteiro_acha_termo_em_latin1_e_em_codificacao_repetida(url: str):
    with pytest.raises(EnvioBarrado):
        Porteiro(["Empresa Fictícia Alfa"]).conferir(url)


def test_com_chave_mas_sem_arquivo_de_termos_o_hospedado_nao_liga(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    _sem_crawl4ai(monkeypatch)
    monkeypatch.setattr(renderizacao, "TERMOS_BARRADOS_PADRAO", tmp_path / "nao-ha.txt")
    assert (
        renderizacao.escolher_renderizador({renderizacao.VARIAVEL_DA_CHAVE: CHAVE})
        is None
    )
    assert "desligado" in capsys.readouterr().err
    dentro = Path(renderizacao.__file__).resolve()
    ambiente = {
        renderizacao.VARIAVEL_DA_CHAVE: CHAVE,
        renderizacao.VARIAVEL_DOS_TERMOS_BARRADOS: str(dentro),
    }
    assert renderizacao.escolher_renderizador(ambiente) is None


@pytest.mark.parametrize(
    ("corpo", "status_code"),
    [(_ok(creditos=1, status=404), 200), ({"success": False}, 500), ({}, 429)],
)
def test_resposta_com_erro_tambem_conta_credito(corpo: dict, status_code: int):
    renderizar, contador = _hospedado(_Post(corpo, status_code), teto=2)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            renderizar(PAGINA)
    assert contador.creditos == 2
    with pytest.raises(TetoDeCreditos):
        renderizar(PAGINA)


@pytest.mark.parametrize("status", [401, 403, 429])
def test_pagina_bloqueada_no_firecrawl_e_bloqueio(status: int):
    renderizar, _ = _hospedado(_Post(_ok(status=status)))
    with pytest.raises(renderizacao.BloqueioNaRenderizacao):
        renderizar(PAGINA)


def test_bloqueio_no_crawl4ai_nao_passa_ao_firecrawl():
    chamados: list[str] = []

    def crawl4ai_bloqueado(url: str) -> tuple[str, bytes]:
        chamados.append("crawl4ai")
        raise renderizacao.BloqueioNaRenderizacao("a página respondeu HTTP 403")

    def firecrawl(url: str) -> tuple[str, bytes]:
        chamados.append("firecrawl")
        return url, b"<p>contornado</p>"

    with pytest.raises(renderizacao.BloqueioNaRenderizacao):
        renderizacao.em_cascata(crawl4ai_bloqueado, firecrawl)(PAGINA)
    assert chamados == ["crawl4ai"]
