"""Catálogo do arquivista (base/arquivo/fontes.py): como cada fonte acha os seus arquivos."""

import json
from datetime import UTC, datetime

import pytest

from base.arquivo import fontes
from base.arquivo.coleta import ErroDeDescoberta, Resposta

AGORA = datetime(2026, 10, 14, 5, tzinfo=UTC)  # 2h em Brasília


class Paginas:
    """Responde `ler` com páginas fixas; guarda os pedidos (método e cabeçalhos)."""

    def __init__(self, paginas: dict[str, bytes], finais: dict[str, str] | None = None):
        self.paginas = paginas
        self.finais = finais or {}
        self.pedidos: list[tuple[str, str, dict]] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None):
        self.pedidos.append((metodo, url, dict(cabecalhos or {})))
        return Resposta(self.finais.get(url, url), self.paginas[url], {})


def _ckan(urls):
    return json.dumps(
        {"success": True, "result": {"resources": [{"url": u} for u in urls]}}
    ).encode()


def test_ckan_devolve_os_recursos_do_pacote():
    portal = "https://dados.cvm.gov.br"
    pedido = f"{portal}/api/3/action/package_show?id=processo-sancionador"
    cliente = Paginas(
        {
            pedido: _ckan(
                ["https://dados.cvm.gov.br/a.zip", "https://dados.cvm.gov.br/meta.zip"]
            )
        }
    )
    alvos = fontes.descobrir_ckan(cliente, portal, "processo-sancionador")
    assert [a.url for a in alvos] == [
        "https://dados.cvm.gov.br/a.zip",
        "https://dados.cvm.gov.br/meta.zip",
    ]


def test_ckan_sem_recurso_e_falha():
    portal = "https://dados.cvm.gov.br"
    cliente = Paginas({f"{portal}/api/3/action/package_show?id=x": _ckan([])})
    with pytest.raises(ErroDeDescoberta):
        fontes.descobrir_ckan(cliente, portal, "x")


def test_cgu_pega_a_data_mais_recente_publicada_na_pagina():
    pagina = (
        b'arquivos.push({"ano" : "2026", "mes" : "10", "dia" : "08", "origem" :  "CEPIM"});'
        b'arquivos.push({"ano" : "2026", "mes" : "10", "dia" : "09", "origem" :  "CEPIM"});'
        b'arquivos.push({"ano" : "2026", "mes" : "09", "dia" : "30", "origem" :  "CEPIM"});'
    )
    cliente = Paginas(
        {"https://portaldatransparencia.gov.br/download-de-dados/cepim": pagina}
    )
    alvos = fontes.descobrir_cgu("cepim")(cliente, AGORA)
    assert [a.url for a in alvos] == [
        "https://portaldatransparencia.gov.br/download-de-dados/cepim/20261009"
    ]
    assert alvos[0].extensao == ".zip"


def test_cgu_sem_data_na_pagina_e_falha():
    cliente = Paginas(
        {
            "https://portaldatransparencia.gov.br/download-de-dados/ceis": b"<html></html>"
        }
    )
    with pytest.raises(ErroDeDescoberta):
        fontes.descobrir_cgu("ceis")(cliente, AGORA)


def test_lista_suja_acha_csv_e_pdf_na_pagina():
    pagina = (
        b'<a href="https://www.gov.br/trabalho-e-emprego/x/cadastro_de_empregadores.csv">csv</a>'
        b'<a href="https://www.gov.br/trabalho-e-emprego/x/cadastro_de_empregadores.pdf">pdf</a>'
        b'<a href="https://www.gov.br/trabalho-e-emprego/x/outra-coisa.pdf">outra</a>'
    )
    cliente = Paginas({fontes.PAGINA_DA_LISTA_SUJA: pagina})
    urls = [a.url for a in fontes.descobrir_lista_suja(cliente, AGORA)]
    assert urls == [
        "https://www.gov.br/trabalho-e-emprego/x/cadastro_de_empregadores.csv",
        "https://www.gov.br/trabalho-e-emprego/x/cadastro_de_empregadores.pdf",
    ]


def test_gleif_pagina_ate_a_ultima():
    def pagina(n):
        return json.dumps(
            {"meta": {"pagination": {"currentPage": n, "lastPage": 3}}}
        ).encode()

    cliente = Paginas({fontes.endereco_gleif(n): pagina(n) for n in (1, 2, 3)})
    alvos = fontes.descobrir_gleif(cliente, AGORA)
    assert [a.url for a in alvos] == [fontes.endereco_gleif(n) for n in (1, 2, 3)]
    assert all(a.extensao == ".json" for a in alvos)


def test_pgfn_pega_o_trimestre_mais_recente():
    raiz = b'<a href="2025_trimestre_04/">x</a><a href="2026_trimestre_02/">y</a><a href="2026_trimestre_01/">z</a>'
    pasta = b'<a href="/">..</a><a href="Dados_abertos_FGTS.zip">a</a><a href="Dados_abertos_Previdenciario.zip">b</a>'
    cliente = Paginas(
        {fontes.RAIZ_DA_PGFN: raiz, fontes.RAIZ_DA_PGFN + "2026_trimestre_02/": pasta}
    )
    urls = [a.url for a in fontes.descobrir_pgfn(cliente, AGORA)]
    assert urls == [
        "https://dadosabertos.pgfn.gov.br/2026_trimestre_02/Dados_abertos_FGTS.zip",
        "https://dadosabertos.pgfn.gov.br/2026_trimestre_02/Dados_abertos_Previdenciario.zip",
    ]


def _propfind(caminhos):
    respostas = "".join(
        f"<d:response><d:href>{c}</d:href></d:response>" for c in caminhos
    )
    return f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">{respostas}</d:multistatus>'.encode()


def test_cnpj_acha_o_mes_mais_recente_pelo_compartilhamento_da_receita():
    base = fontes.RAIZ_DO_CNPJ
    webdav = fontes.WEBDAV_DA_RECEITA
    cliente = Paginas(
        {
            base: b"<html></html>",
            webdav + fontes.PASTA_DO_CNPJ + "/": _propfind(
                [
                    f"/public.php/webdav/{fontes.PASTA_DO_CNPJ}/",
                    f"/public.php/webdav/{fontes.PASTA_DO_CNPJ}/2026-08/",
                    f"/public.php/webdav/{fontes.PASTA_DO_CNPJ}/2026-09/",
                    f"/public.php/webdav/{fontes.PASTA_DO_CNPJ}/LEIAME.pdf",
                ]
            ),
            webdav + fontes.PASTA_DO_CNPJ + "/2026-09/": _propfind(
                [
                    f"/public.php/webdav/{fontes.PASTA_DO_CNPJ}/2026-09/",
                    f"/public.php/webdav/{fontes.PASTA_DO_CNPJ}/2026-09/Empresas0.zip",
                    f"/public.php/webdav/{fontes.PASTA_DO_CNPJ}/2026-09/Socios0.zip",
                ]
            ),
        },
        finais={base: "https://arquivos.receitafederal.gov.br/index.php/s/AbC123xyz"},
    )
    urls = [a.url for a in fontes.descobrir_cnpj(cliente, AGORA)]
    assert urls == [
        f"https://arquivos.receitafederal.gov.br/public.php/dav/files/AbC123xyz/{fontes.PASTA_DO_CNPJ}/2026-09/Empresas0.zip",
        f"https://arquivos.receitafederal.gov.br/public.php/dav/files/AbC123xyz/{fontes.PASTA_DO_CNPJ}/2026-09/Socios0.zip",
    ]
    [propfind_raiz] = [p for p in cliente.pedidos if p[0] == "PROPFIND"][:1]
    assert propfind_raiz[2]["Depth"] == "1"
    assert propfind_raiz[2]["Authorization"].startswith("Basic ")


def test_cnpj_sem_token_e_falha():
    cliente = Paginas(
        {fontes.RAIZ_DO_CNPJ: b""},
        finais={fontes.RAIZ_DO_CNPJ: "https://arquivos.receitafederal.gov.br/"},
    )
    with pytest.raises(ErroDeDescoberta):
        fontes.descobrir_cnpj(cliente, AGORA)


def test_catalogo_tem_ids_unicos_e_grupos_conhecidos():
    ids = [f.id for f in fontes.FONTES]
    assert len(ids) == len(set(ids))
    assert {f.grupo for f in fontes.FONTES} <= {"diaria", "semanal", "mensal"}
    pesadas = {f.id for f in fontes.FONTES if f.pesada}
    assert {"rfb-cnpj", "pgfn-divida"} <= pesadas
    vigias = {f.id for f in fontes.FONTES if f.vigia}
    assert vigias and all(i.startswith(("termos-", "catalogo-")) for i in vigias)
    assert "cvm-fiagro" in ids
