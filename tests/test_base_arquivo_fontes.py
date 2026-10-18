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


def test_pasta_da_cvm_lista_os_arquivos_de_todos_os_anos():
    pasta = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/"
    pagina = (
        b'<a href="../">../</a><a href="ipe_cia_aberta_2003.zip">x</a>'
        b'<a href="ipe_cia_aberta_2026.zip">y</a><a href="?C=M;O=A">ordem</a>'
    )
    cliente = Paginas({pasta: pagina})
    urls = [a.url for a in fontes.descobrir_pasta(cliente, pasta)]
    assert urls == [
        pasta + "ipe_cia_aberta_2003.zip",
        pasta + "ipe_cia_aberta_2026.zip",
    ]


def test_pasta_vazia_e_falha():
    pasta = "https://dados.cvm.gov.br/dados/X/"
    with pytest.raises(ErroDeDescoberta):
        fontes.descobrir_pasta(Paginas({pasta: b"<html></html>"}), pasta)


def test_historico_da_cvm_e_fontes_abertas_novas_no_catalogo():
    ids = {f.id for f in fontes.FONTES}
    historico = {
        "cvm-hist-ipe",
        "cvm-hist-itr",
        "cvm-hist-dfp",
        "cvm-hist-fre",
        "cvm-hist-fca",
        "cvm-hist-vlmo",
        "cvm-hist-cda",
    }
    assert historico <= ids
    assert {"ccee-pld", "antt-pedagio", "tesouro-br-divida"} <= ids
    # curva de juros própria (B12): taxas do Tesouro Direto todo dia, leilões no domingo
    assert fontes.POR_ID["tesouro-br-direto"].grupo == "diaria"
    assert fontes.POR_ID["tesouro-br-leiloes"].grupo == "semanal"
    assert all(
        fontes.POR_ID[i].pesada for i in historico
    )  # GBs: só baixa quando os cabeçalhos mudam


def test_ckan_ignora_paineis_e_paginas_que_nao_sao_arquivos():
    # a ANTT lista um painel do Power BI entre os recursos (14/10/2026)
    portal = "https://dados.antt.gov.br"
    resposta = json.dumps(
        {
            "result": {
                "resources": [
                    {"url": "https://dados.antt.gov.br/x/2026.csv", "format": "CSV"},
                    {"url": "https://app.powerbi.com/view?r=abc", "format": "HTML"},
                    {"url": "https://app.powerbi.com/view?r=def", "format": ""},
                    {"url": "https://dados.antt.gov.br/x/pagina", "format": "html"},
                ]
            }
        }
    ).encode()
    cliente = Paginas({f"{portal}/api/3/action/package_show?id=pedagio": resposta})
    alvos = fontes.descobrir_ckan(cliente, portal, "pedagio")
    assert [a.url for a in alvos] == ["https://dados.antt.gov.br/x/2026.csv"]


def test_scr_do_bc_vem_dos_arquivos_por_ano_e_nao_do_ckan():
    # o firewall do BC responde "Requisição Inválida" à API do CKAN; os arquivos por ano baixam
    # (inventário da série 3, PR 7, 14/10/2026)
    from base import bcb_scr

    scr = fontes.POR_ID["bcb-scr"]
    cliente = Paginas({})
    urls = [a.url for a in scr.descobrir(cliente, AGORA)]
    assert urls == [bcb_scr.endereco_do_ano(ano) for ano in range(2012, 2027)]
    assert cliente.pedidos == []  # nenhum pedido ao catálogo
    assert scr.pesada  # ~2 GB: só baixa de novo quando os cabeçalhos mudam


def test_scr_do_ano_novo_so_entra_quando_o_bc_publica_janeiro():
    # janeiro sai no fim de fevereiro: antes de março o arquivo do ano não existe
    scr = fontes.POR_ID["bcb-scr"]
    fevereiro = datetime(2027, 2, 27, 5, tzinfo=UTC)
    marco = datetime(2027, 3, 1, 5, tzinfo=UTC)
    assert scr.descobrir(Paginas({}), fevereiro)[-1].url.endswith("scrdata_2026.zip")
    assert scr.descobrir(Paginas({}), marco)[-1].url.endswith("scrdata_2027.zip")


# prévia do balanço pelos reguladores, 1ª leva (14/10/2026)


def test_previa_do_balanco_no_catalogo():
    novas = {
        "anp-vendas-distribuidora": ("semanal", False),
        "anp-producao-poco": ("mensal", False),
        "anp-concessionarios": ("mensal", False),
        "ons-geracao-usina": ("semanal", True),
        "ons-restricao-eolica-solar": ("semanal", True),
        "ons-capacidade-geracao": ("semanal", False),
        "antt-siade": ("semanal", True),
        "comexstat": ("semanal", True),
        "anac-estatistico": ("mensal", True),
        "ans-beneficiarios": ("semanal", True),
    }
    for id_, (grupo, pesada) in novas.items():
        fonte = fontes.POR_ID[id_]
        assert (fonte.grupo, fonte.pesada) == (grupo, pesada), id_
    # a ANP não manda ETag: os ZIPs de vendas vêm por endereço fixo, sem perguntar cabeçalhos
    vendas = fontes.POR_ID["anp-vendas-distribuidora"].descobrir(Paginas({}), AGORA)
    assert [a.url.rsplit("/", 1)[-1] for a in vendas] == [
        "liquidos.zip",
        "glp.zip",
        "aviacao.zip",
    ]


def test_ckan_escolhe_so_os_formatos_pedidos():
    # o ONS publica cada mês em CSV, XLSX e Parquet: basta o Parquet (e o dicionário)
    portal = fontes.PORTAL_DO_ONS
    resposta = json.dumps(
        {
            "result": {
                "resources": [
                    {"url": f"{portal}/d/dicionario.pdf", "format": "PDF"},
                    {"url": f"{portal}/d/2026_10.csv", "format": "CSV"},
                    {"url": f"{portal}/d/2026_10.xlsx", "format": "XLSX"},
                    {"url": f"{portal}/d/2026_10.parquet", "format": "PARQUET"},
                ]
            }
        }
    ).encode()
    cliente = Paginas({f"{portal}/api/3/action/package_show?id=g": resposta})
    alvos = fontes.descobrir_ckan(cliente, portal, "g", formatos=("parquet", "pdf"))
    assert [a.url.rsplit("/", 1)[-1] for a in alvos] == [
        "dicionario.pdf",
        "2026_10.parquet",
    ]


def test_producao_da_anp_sai_dos_links_da_pagina():
    pasta = (
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/"
        "arquivos-fase-de-desenvolvimento-e-producao/"
        "arquivos-producao-de-petroleo-e-gas-natural-nacional/"
    )
    pagina = (
        f'<a href="{pasta}pm/producao-mar-2026.csv">2026</a>'
        f'<a href="{pasta}pm/producao_por_poco_2024.csv">2024</a>'
        f'<a href="{pasta}pt/2026/producao_por_poco_terra_2026_2_trim.csv">terra</a>'
        f'<a href="{pasta}pm/producao-mar-2026.csv">de novo</a>'
        '<a href="https://www.gov.br/anp/outra-coisa.csv">fora</a>'
    ).encode()
    cliente = Paginas({fontes.PAGINA_DA_PRODUCAO_DA_ANP: pagina})
    alvos = fontes.POR_ID["anp-producao-poco"].descobrir(cliente, AGORA)
    assert [a.url.rsplit("/", 1)[-1] for a in alvos] == [
        "producao-mar-2026.csv",
        "producao_por_poco_2024.csv",
        "producao_por_poco_terra_2026_2_trim.csv",
    ]
    with pytest.raises(ErroDeDescoberta):
        fontes.descobrir_links(
            Paginas({"https://x/p": b"<html></html>"}),
            "https://x/p",
            fontes.PRODUCAO_POR_POCO,
        )


def test_comex_tem_todos_os_anos_e_o_ano_novo_so_depois_de_janeiro():
    alvos = [a.url for a in fontes.descobrir_comex(Paginas({}), AGORA)]
    anos = 2026 - 1997 + 1
    assert len(alvos) == 4 * anos + 2 + len(fontes.TABELAS_DO_COMEX)
    assert f"{fontes.COMEX}comexstat-bd/ncm/EXP_1997.csv" in alvos
    assert f"{fontes.COMEX}comexstat-bd/mun/IMP_2026_MUN.csv" in alvos
    janeiro = [
        a.url
        for a in fontes.descobrir_comex(Paginas({}), datetime(2027, 1, 20, tzinfo=UTC))
    ]
    assert not any("_2027" in url for url in janeiro)
    assert f"{fontes.COMEX}comexstat-bd/ncm/EXP_2026.csv" in janeiro


def test_beneficiarios_da_ans_so_as_duas_safras_mais_recentes():
    raiz = fontes.BENEFICIARIOS_DA_ANS
    cliente = Paginas(
        {
            raiz: b'<a href="202606/">x</a><a href="202607/">x</a>'
            b'<a href="202608/">x</a><a href="dicionario/">x</a>',
            f"{raiz}202607/": b'<a href="pda-024-icb-AC-2026_07.zip">AC</a>',
            f"{raiz}202608/": b'<a href="pda-024-icb-AC-2026_08.zip">AC</a>'
            b'<a href="pda-024-icb-SP-2026_08.zip">SP</a>',
        }
    )
    alvos = fontes.descobrir_beneficiarios_ans(cliente, AGORA)
    assert [a.url.removeprefix(raiz) for a in alvos] == [
        "202607/pda-024-icb-AC-2026_07.zip",
        "202608/pda-024-icb-AC-2026_08.zip",
        "202608/pda-024-icb-SP-2026_08.zip",
    ]
    with pytest.raises(ErroDeDescoberta):
        fontes.descobrir_beneficiarios_ans(Paginas({raiz: b"<html></html>"}), AGORA)


def test_endereco_da_anac_vai_codificado():
    assert " " not in fontes.ESTATISTICO_DA_ANAC
    assert fontes.ESTATISTICO_DA_ANAC.endswith("/Dados_Estatisticos.csv")


def test_meses_recentes_do_fidc_e_do_cda_todo_dia():
    """O dia em que cada informe apareceu (`base/publicacao.py`): os meses mais novos, todo dia, e o
    que ainda não saiu fica como "não encontrado" (a prova de que faltava)."""
    from datetime import UTC, datetime

    agora = datetime(2026, 10, 16, 5, 0, tzinfo=UTC)
    fidc = fontes.POR_ID["cvm-fidc-recente"]
    cda = fontes.POR_ID["cvm-cda-recente"]
    assert (fidc.grupo, cda.grupo) == ("diaria", "diaria")
    assert not (fidc.pesada or cda.pesada)  # a CVM regrava sem mudar os cabeçalhos
    alvos_fidc = fidc.descobrir(None, agora)  # type: ignore[arg-type]
    assert [a.url.rsplit("_", 1)[-1] for a in alvos_fidc] == [
        "202606.zip",
        "202607.zip",
        "202608.zip",
        "202609.zip",
    ]
    assert alvos_fidc[0].url.startswith(
        "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/inf_mensal_fidc_"
    )
    assert all(a.obter is not None for a in alvos_fidc)  # 404 vira "nao_encontrado"
    alvos_cda = cda.descobrir(None, agora)  # type: ignore[arg-type]
    assert [a.url.rsplit("/", 1)[-1] for a in alvos_cda] == [
        f"cda_fi_2026{m:02d}.zip" for m in range(5, 10)
    ]
    # virada do ano, no fuso de São Paulo (1º/01 às 01h UTC ainda é 31/12)
    janeiro = fidc.descobrir(None, datetime(2027, 1, 1, 1, 0, tzinfo=UTC))  # type: ignore[arg-type]
    assert [a.url[-10:-4] for a in janeiro] == ["202608", "202609", "202610", "202611"]


def test_clima_do_cafe_inmet_por_ano_chirps_por_mes_e_malha_por_uf():
    """Plano do café, PR 8: os zips anuais do INMET (todos, pesados: ETag e Last-Modified evitam a
    baixa repetida), os GeoTIFFs dos meses recentes do CHIRPS (o que falta é 404, não falha) e a
    malha municipal das seis UFs com região cafeeira."""
    agora = datetime(2026, 10, 18, 12, tzinfo=UTC)
    inmet = fontes.POR_ID["inmet-bdmep"]
    assert (inmet.grupo, inmet.tipo, inmet.pesada) == ("mensal", "zip", True)
    anos = inmet.descobrir(None, agora)  # type: ignore[arg-type]
    assert [a.url.rsplit("/", 1)[-1] for a in anos][:2] == ["2000.zip", "2001.zip"]
    assert (
        anos[-1].url == "https://portal.inmet.gov.br/uploads/dadoshistoricos/2026.zip"
    )
    chirps = fontes.POR_ID["chirps-mensal"]
    assert chirps.grupo == "mensal" and chirps.pesada
    meses = chirps.descobrir(None, agora)  # type: ignore[arg-type]
    assert [a.url.rsplit("/", 1)[-1] for a in meses] == [
        f"chirps-v2.0.2026.{m:02d}.tif.gz" for m in (7, 8, 9)
    ]
    assert all(a.obter is not None and a.extensao == ".tif.gz" for a in meses)
    malhas = fontes.POR_ID["ibge-malha-municipal"].descobrir(None, agora)  # type: ignore[arg-type]
    assert [a.url.split("/estados/")[1][:2] for a in malhas] == [
        "31",
        "32",
        "35",
        "41",
        "29",
        "11",
    ]
    assert all("qualidade=minima" in a.url and a.extensao == ".json" for a in malhas)
    assert fontes.TERMOS["termos-inmet"].startswith("https://portal.inmet.gov.br/")


def test_mapbiomas_cafe_e_um_zip_pesado_no_google_drive_atras_da_confirmacao():
    """Plano do café, PR 8 (8.4): a cobertura de café por município do MapBiomas (Coleção 11) é
    uma planilha zipada no Google Drive; o `obter` do alvo segue a página de confirmação de arquivo
    grande em vez de guardar o HTML dela."""
    fonte = fontes.POR_ID["mapbiomas-cafe"]
    assert (fonte.grupo, fonte.tipo, fonte.pesada) == ("mensal", "zip", True)
    (alvo,) = fonte.descobrir(None, datetime(2026, 10, 18, tzinfo=UTC))  # type: ignore[arg-type]
    assert alvo.url.startswith("https://drive.google.com/uc?id=")
    assert alvo.extensao == ".zip" and alvo.obter is not None
