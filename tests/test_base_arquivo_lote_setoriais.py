"""Lote setoriais Brasil do arquivista (base/arquivo/lote_setoriais.py): como cada fonte acha os seus arquivos."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
import requests

from base.arquivo import lote_setoriais, registro, robots
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from base.arquivo.fontes import FONTES, POR_ID
from src.banco.coletas import Marca, licenca_da_fonte, marca_da_fonte

AGORA = datetime(2026, 10, 22, 14, tzinfo=UTC)
DUBLES = Path(__file__).parent / "arquivos" / "setoriais" / "lote"
FONTES_DO_LOTE = {f.id: f for f in lote_setoriais.fontes()}


class Paginas:
    """Responde `ler` com páginas fixas; um valor `int` vira erro HTTP com esse código."""

    def __init__(self, paginas: dict[str, bytes | int]):
        self.paginas = paginas
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        pagina = self.paginas[url]
        if isinstance(pagina, int):
            resposta = requests.Response()
            resposta.status_code = pagina
            raise requests.HTTPError(response=resposta)
        return Resposta(url, pagina, {})


def _urls(alvos):
    return [a.url for a in alvos]


def _dubles(nome: str) -> bytes:
    return (DUBLES / nome).read_bytes()


def _pacote(*recursos: tuple[str, str]) -> bytes:
    """A resposta do `package_show` do CKAN com (formato, endereço) por recurso."""
    return json.dumps(
        {"result": {"resources": [{"format": f, "url": u} for f, u in recursos]}}
    ).encode()


def _pagina_do_pacote(*recursos: tuple[str, str]) -> bytes:
    """A página `/dataset/<pacote>` do CKAN com (formato, link de download) por recurso, no formato
    do portal da CCEE."""
    itens = "".join(
        f'<li class="resource-item" data-id="{n}">\n'
        f'  <a class="heading" href="/dataset/p/resource/{n}">r{n}'
        f'<span class="format-label" data-format="{f}">{f.upper()}</span></a>\n'
        f'  <a class="dropdown-item" href="/dataset/p/resource/{n}">preview</a>\n'
        f'  <a class="dropdown-item resource-url-analytics" href="{u}" target="_blank">download</a>\n'
        "</li>\n"
        for n, (f, u) in enumerate(recursos)
    )
    return (
        f'<ul class="resource-list">\n{itens}</ul>\n<a href="/sobre">sobre</a>'.encode()
    )


def _anterior(dias_atras: int):
    return SimpleNamespace(baixado_em=datetime.now(UTC) - timedelta(days=dias_atras))


# ---------------------------------------------------------------- catálogo
def test_ids_do_lote_sao_unicos_e_estao_no_catalogo_geral():
    ids = [f.id for f in lote_setoriais.fontes()]
    assert len(ids) == len(set(ids))
    assert set(ids) <= set(POR_ID)
    assert len([f for f in FONTES if f.id in ids]) == len(ids)


def test_o_lote_nao_repete_nenhuma_fonte_que_ja_existia():
    ids_antigos = {f.id for f in FONTES if f.id not in FONTES_DO_LOTE}
    assert not set(FONTES_DO_LOTE) & ids_antigos
    # o Comex Stat (NCM e município) já é coletado: nada de `comexstat-*` aqui
    assert not any(i.startswith("comexstat") for i in FONTES_DO_LOTE)


def test_grupos_do_lote_sao_conhecidos():
    assert {f.grupo for f in FONTES_DO_LOTE.values()} <= {"diaria", "semanal", "mensal"}


def test_todas_as_familias_pedidas_estao_no_lote():
    familias = {i.split("-", 1)[0] for i in FONTES_DO_LOTE}
    assert familias == {
        "ccee",
        "epe",
        "ons",
        "aneel",
        "ans",
        "anatel",
        "anac",
        "inep",
        "senatran",
        "anp",
        "inpi",
    }


@pytest.mark.parametrize("fonte", sorted(FONTES_DO_LOTE))
def test_toda_fonte_do_lote_tem_licenca_marca_e_data_dos_termos(fonte):
    assert not licenca_da_fonte(fonte).startswith("Desconhecida")
    familia = fonte.split("-", 1)[0]
    assert registro.TERMOS_LIDOS_EM[familia] >= date(2026, 10, 14)
    sem_licenca_aberta = {"inep", "senatran", "inpi"}
    esperada = (
        Marca.A_CONFIRMAR
        if familia in sem_licenca_aberta or fonte == "ans-demonstracoes"
        else Marca.VENDAVEL
    )
    assert marca_da_fonte(fonte) == esperada


def test_as_demonstracoes_da_ans_nao_herdam_o_cc_by_dos_beneficiarios():
    assert marca_da_fonte("ans-beneficiarios") == Marca.VENDAVEL
    assert marca_da_fonte("ans-demonstracoes") == Marca.A_CONFIRMAR
    assert "sem licença declarada" in licenca_da_fonte("ans-demonstracoes")


def test_fonte_que_recusa_head_nao_e_pesada():
    # a ANP responde 403 e o INPI 500 ao HEAD: uma fonte pesada derrubaria a coleta inteira
    for id_, fonte in FONTES_DO_LOTE.items():
        if id_.startswith(("anp-", "inpi-", "ccee-")):
            assert not fonte.pesada, id_


def test_fontes_com_etag_conferem_a_assinatura_antes_de_baixar():
    pesadas = {i for i, f in FONTES_DO_LOTE.items() if f.pesada}
    assert {
        "epe-consumo-mensal",
        "ons-carga",
        "aneel-tarifas",
        "ans-demonstracoes",
        "anatel-acessos-telefonia-fixa",
        "anac-horas-voadas",
        "inep-censo-superior",
        "senatran-frota",
    } <= pesadas


# --------------------------------------------------------------- CKAN
def test_ckan_devolve_os_arquivos_de_cada_pacote_e_deixa_o_painel_de_fora():
    portal = lote_setoriais.PORTAL_DA_ANEEL
    cliente = Paginas(
        {
            f"{portal}/api/3/action/package_show?id=a": _pacote(
                ("CSV", "https://x/a1"),
                ("HTML", "https://x/pagina"),
                ("CSV", "https://app.powerbi.com/painel"),
            ),
            f"{portal}/api/3/action/package_show?id=b": _pacote(
                ("CSV", "https://x/b1")
            ),
        }
    )
    alvos = lote_setoriais.descobrir_ckan(cliente, portal, "a", "b")
    assert _urls(alvos) == ["https://x/a1", "https://x/b1"]


def test_ckan_com_formatos_escolhe_so_esses_e_pacote_vazio_e_falha():
    portal = lote_setoriais.PORTAL_DO_ONS
    cliente = Paginas(
        {
            f"{portal}/api/3/action/package_show?id=carga": _pacote(
                ("PDF", "https://x/dicionario.pdf"),
                ("CSV", "https://x/carga_2025.csv"),
                ("XLSX", "https://x/carga_2025.xlsx"),
                ("Parquet", "https://x/carga_2025.parquet"),
            ),
            f"{portal}/api/3/action/package_show?id=vazio": _pacote(
                ("JSON", "https://x/a.json")
            ),
        }
    )
    alvos = lote_setoriais.descobrir_ckan(
        cliente, portal, "carga", formatos=lote_setoriais.FORMATOS_DO_ONS
    )
    assert _urls(alvos) == ["https://x/dicionario.pdf", "https://x/carga_2025.csv"]
    with pytest.raises(ErroDeDescoberta, match="vazio"):
        lote_setoriais.descobrir_ckan(
            cliente, portal, "vazio", formatos=lote_setoriais.FORMATOS_DO_ONS
        )


def test_ckan_pela_pagina_devolve_os_downloads_e_deixa_pagina_e_painel_de_fora():
    portal = lote_setoriais.PORTAL_DA_CCEE
    cliente = Paginas(
        {
            f"{portal}/dataset/a": _pagina_do_pacote(
                ("csv", "https://pda-download.ccee.org.br/a1/content"),
                ("html", "https://www.ccee.org.br/pagina"),
                ("csv", "https://app.powerbi.com/painel"),
                ("csv", "/dataset/a/resource/9/download/a.csv?v=1&amp;x=2"),
            ),
            f"{portal}/dataset/b": _pagina_do_pacote(
                ("csv", "https://pda-download.ccee.org.br/b1/content")
            ),
        }
    )
    alvos = lote_setoriais.descobrir_ckan_pela_pagina(cliente, portal, "a", "b")
    assert _urls(alvos) == [
        "https://pda-download.ccee.org.br/a1/content",
        f"{portal}/dataset/a/resource/9/download/a.csv?v=1&x=2",
        "https://pda-download.ccee.org.br/b1/content",
    ]
    assert cliente.pedidos == [f"{portal}/dataset/a", f"{portal}/dataset/b"]


def test_ckan_pela_pagina_sem_recurso_e_falha_com_o_nome_do_pacote():
    portal = lote_setoriais.PORTAL_DA_CCEE
    cliente = Paginas({f"{portal}/dataset/vazio": b"<p>sem dados</p>"})
    with pytest.raises(ErroDeDescoberta, match="vazio"):
        lote_setoriais.descobrir_ckan_pela_pagina(cliente, portal, "vazio")


@pytest.mark.parametrize("id_", sorted(lote_setoriais.PACOTES_DA_CCEE))
def test_cada_fonte_da_ccee_le_a_pagina_de_todos_os_seus_pacotes(id_):
    portal = lote_setoriais.PORTAL_DA_CCEE
    pacotes = lote_setoriais.PACOTES_DA_CCEE[id_]
    cliente = Paginas(
        {
            f"{portal}/dataset/{p}": _pagina_do_pacote(("csv", f"https://x/{p}.csv"))
            for p in pacotes
        }
    )
    alvos = FONTES_DO_LOTE[id_].descobrir(cliente, AGORA)
    assert cliente.pedidos == [f"{portal}/dataset/{p}" for p in pacotes]
    assert _urls(alvos) == [f"https://x/{p}.csv" for p in pacotes]


class PortalQualquer:
    """Responde a qualquer página de pacote com um recurso; anota os pedidos."""

    def __init__(self):
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        return Resposta(url, _pagina_do_pacote(("csv", "https://x/a.csv")), {})


def test_nenhuma_fonte_da_ccee_pede_o_que_o_robots_txt_da_ccee_proibe():
    # 28/10/2026: o robots.txt da CCEE proíbe a `/api/` (o `package_show`) e o portal passou a
    # devolver 403 ao servidor de casa desde 24/10
    proibido = (
        Path(__file__).parent / "arquivos" / "reguladores" / "ccee_robots.txt"
    ).read_text(encoding="utf-8")
    assert not robots.pode_buscar(proibido, "/api/3/action/package_show?id=pld_horario")
    cliente = PortalQualquer()
    for fonte in FONTES:
        if fonte.id.startswith("ccee-"):
            fonte.descobrir(cliente, AGORA)
    assert cliente.pedidos
    for pedido in cliente.pedidos:
        partes = urlsplit(pedido)
        assert partes.netloc == "dadosabertos.ccee.org.br", pedido
        assert robots.pode_buscar(proibido, partes.path), pedido


@pytest.mark.parametrize(
    ("id_", "portal", "pacotes"),
    [
        *[
            (i, lote_setoriais.PORTAL_DO_ONS, p)
            for i, p in lote_setoriais.PACOTES_DO_ONS.items()
        ],
        *[
            (i, lote_setoriais.PORTAL_DA_ANEEL, p)
            for i, p in lote_setoriais.PACOTES_DA_ANEEL.items()
        ],
    ],
)
def test_cada_fonte_ckan_pede_o_package_show_de_todos_os_seus_pacotes(
    id_, portal, pacotes
):
    cliente = Paginas(
        {
            f"{portal}/api/3/action/package_show?id={p}": _pacote(
                ("CSV", f"https://x/{p}.csv"), ("PDF", f"https://x/{p}.pdf")
            )
            for p in pacotes
        }
    )
    alvos = FONTES_DO_LOTE[id_].descobrir(cliente, AGORA)
    assert cliente.pedidos == [
        f"{portal}/api/3/action/package_show?id={p}" for p in pacotes
    ]
    assert len(alvos) >= len(pacotes)


def test_nenhum_pacote_do_lote_e_de_pessoas_nem_repete_o_que_ja_existe():
    todos = [
        p
        for grupo in (
            lote_setoriais.PACOTES_DA_CCEE,
            lote_setoriais.PACOTES_DO_ONS,
            lote_setoriais.PACOTES_DA_ANEEL,
        )
        for ps in grupo.values()
        for p in ps
    ]
    assert len(todos) == len(set(todos))
    jah_existentes = {"pld_horario", "pld_media_diaria", "pld_media_mensal"}
    jah_existentes |= {"geracao-usina-2", "capacidade-geracao"}
    assert not set(todos) & jah_existentes
    proibidos = ("beneficiarios", "distribuida", "consumidores", "lista_", "lista-")
    assert not [p for p in todos if any(x in p for x in proibidos)]


# --------------------------------------------------------------- ANS
def _pastas_da_ans(**por_ano):
    raiz = lote_setoriais.RAIZ_DAS_DEMONSTRACOES_DA_ANS
    paginas = {raiz: _dubles("ans_raiz.html")}
    paginas |= {f"{raiz}{ano}/": conteudo for ano, conteudo in por_ano.items()}
    return Paginas(paginas)


def test_ans_pega_o_zip_de_cada_trimestre_de_cada_ano():
    raiz = lote_setoriais.RAIZ_DAS_DEMONSTRACOES_DA_ANS
    cliente = _pastas_da_ans(
        **{
            "2001": b"<html></html>",  # ano sem zip é pulado
            "2012": _dubles("ans_2012.html"),
            "2025": _dubles("ans_2026.html"),
            "2026": _dubles("ans_2026.html"),
        }
    )
    alvos = FONTES_DO_LOTE["ans-demonstracoes"].descobrir(cliente, AGORA)
    assert _urls(alvos) == [
        f"{raiz}2012/20130416_1T2012.zip",
        f"{raiz}2012/20130416_2T2012.zip",
        f"{raiz}2012/20130416_3T2012.zip",
        f"{raiz}2012/20130416_4T2012.zip",
        f"{raiz}2025/1T2026.zip",
        f"{raiz}2025/2T2026.zip",
        f"{raiz}2026/1T2026.zip",
        f"{raiz}2026/2T2026.zip",
    ]
    assert {a.extensao for a in alvos} == {".zip"}


def test_ans_sem_nenhum_zip_em_nenhum_ano_e_falha():
    cliente = _pastas_da_ans(
        **{"2001": b"", "2012": b"", "2025": b"", "2026": b"<html></html>"}
    )
    with pytest.raises(ErroDeDescoberta, match="ANS"):
        FONTES_DO_LOTE["ans-demonstracoes"].descobrir(cliente, AGORA)


# --------------------------------------------------------------- Anatel
def test_anatel_fixa_guarda_so_os_csv_colunas_e_total_do_zip(monkeypatch):
    url = lote_setoriais.ZIP_DA_TELEFONIA_FIXA
    membros = [
        "Acessos_Telefonia_Fixa_Autorizadas_2005-201306_Colunas.csv",
        "Acessos_Telefonia_Fixa_Total.csv",
        "Acessos_Telefonia_Fixa_Dicionario.csv",
        "LEIA-ME.txt",
    ]
    monkeypatch.setattr(lote_setoriais, "membros_do_zip_remoto", lambda c, u: membros)
    alvos = FONTES_DO_LOTE["anatel-acessos-telefonia-fixa"].descobrir(None, AGORA)
    assert _urls(alvos) == [f"{url}#{membros[0]}", f"{url}#{membros[1]}"]
    assert all(a.obter is not None and a.extensao == ".csv" for a in alvos)


def test_anatel_fixa_sem_csv_no_zip_e_falha(monkeypatch):
    monkeypatch.setattr(lote_setoriais, "membros_do_zip_remoto", lambda c, u: ["a.txt"])
    with pytest.raises(ErroDeDescoberta, match="Anatel"):
        FONTES_DO_LOTE["anatel-acessos-telefonia-fixa"].descobrir(None, AGORA)


# --------------------------------------------------------------- INEP
def test_inep_pede_o_ano_corrente_e_os_quatro_anteriores_e_tolera_o_que_nao_saiu():
    alvos = FONTES_DO_LOTE["inep-censo-superior"].descobrir(None, AGORA)
    anos = [a.url.rsplit("_", 1)[1] for a in alvos]
    assert anos == ["2022.zip", "2023.zip", "2024.zip", "2025.zip", "2026.zip"]
    assert all(
        a.url.startswith("https://download.inep.gov.br/microdados/") for a in alvos
    )
    assert all(a.extensao == ".zip" and a.obter is not None for a in alvos)


# --------------------------------------------------------------- Senatran
def _paginas_da_frota(**por_ano):
    return Paginas(
        {
            lote_setoriais.PAGINA_DA_FROTA.format(ano=ano): p
            for ano, p in por_ano.items()
        }
    )


def test_senatran_pega_uf_municipio_e_ano_de_fabricacao_do_ano_e_do_anterior():
    cliente = _paginas_da_frota(
        **{"2025": _dubles("senatran_2025.html"), "2026": _dubles("senatran_2026.html")}
    )
    alvos = FONTES_DO_LOTE["senatran-frota"].descobrir(cliente, AGORA)
    nomes = [a.url.rsplit("/@@download", 1)[0].rsplit("/", 1)[-1] for a in alvos]
    # 2025 (nomes irregulares: "FrotaporUFeTipo", "Municpio", "frota-por-...") e 2026
    assert len(alvos) == 9 + 6
    assert "copy_of_FrotaporMunicpioeTipoSETEMBRO2025.xlsx" in nomes
    assert "frota-por-uf-e-tipo-de-veiculo-agosto-2025.xlsx" in nomes
    assert "F_Frota_por_UF_Municipio_ANO_FAB_MOD_Setembro_2026.xlsx" in nomes
    # CEP, cor, combustível, potência, restrição e espécie ficam de fora
    assert not [
        n for n in nomes if any(x in n.upper() for x in ("CEP", "_COR_", "COMBUST"))
    ]
    assert all(a.url.startswith("https://www.gov.br/transportes/") for a in alvos)
    assert {a.extensao for a in alvos} == {".xlsx"}


def test_senatran_pula_o_ano_anterior_sem_pagina_mas_nao_o_corrente_sem_planilha():
    cliente = _paginas_da_frota(**{"2025": 404, "2026": _dubles("senatran_2026.html")})
    assert len(FONTES_DO_LOTE["senatran-frota"].descobrir(cliente, AGORA)) == 6
    vazio = _paginas_da_frota(**{"2025": 404, "2026": b"<html></html>"})
    with pytest.raises(ErroDeDescoberta, match="Senatran"):
        FONTES_DO_LOTE["senatran-frota"].descobrir(vazio, AGORA)


def test_senatran_erro_diferente_de_404_nao_e_engolido():
    cliente = _paginas_da_frota(**{"2025": 500, "2026": _dubles("senatran_2026.html")})
    with pytest.raises(requests.HTTPError):
        FONTES_DO_LOTE["senatran-frota"].descobrir(cliente, AGORA)


# --------------------------------------------------------------- ANP
def _pagina_da_anp():
    return Paginas(
        {lote_setoriais.PAGINA_DOS_PRECOS_DA_ANP: _dubles("anp_precos.html")}
    )


def test_anp_semestral_pega_so_ca_e_glp_semestrais():
    alvos = FONTES_DO_LOTE["anp-precos-semestral"].descobrir(_pagina_da_anp(), AGORA)
    nomes = sorted(a.url.rsplit("/", 1)[1] for a in alvos)
    assert nomes == sorted(
        [
            "ca-2024-01.zip",
            "ca-2024-02.zip",
            "ca-2025-01.zip",
            "ca-2025-02.zip",
            "ca-2026-01.zip",
            "glp-2024-01.csv",
            "glp-2024-02.csv",
            "glp-2025-01.csv",
            "glp-2025-02.csv",
            "glp-2026-01.csv",
        ]
    )


def test_anp_mensal_pega_o_ano_corrente_e_o_anterior_inclusive_sem_extensao():
    alvos = FONTES_DO_LOTE["anp-precos-mensal"].descobrir(_pagina_da_anp(), AGORA)
    urls = _urls(alvos)
    assert all("/dsan/2025/" in u or "/dsan/2026/" in u for u in urls)
    assert not [u for u in urls if "/dsan/2024/" in u]
    # o nome muda de mês a mês e abril de 2026 foi publicado sem ".csv"
    assert any(u.endswith("04-dados-abertos-precos-glp") for u in urls)
    assert any(u.endswith("02-cados-abertos-preco-gasolina-etanol.csv") for u in urls)
    assert {a.extensao for a in alvos} == {".csv"}


def test_anp_pagina_sem_links_de_preco_e_falha():
    vazia = Paginas({lote_setoriais.PAGINA_DOS_PRECOS_DA_ANP: b"<html></html>"})
    for id_ in ("anp-precos-semestral", "anp-precos-mensal"):
        with pytest.raises(ErroDeDescoberta, match="ANP"):
            FONTES_DO_LOTE[id_].descobrir(vazia, AGORA)


def test_anp_ultimas_semanas_sao_tres_arquivos_fixos():
    alvos = FONTES_DO_LOTE["anp-precos-ultimas-semanas"].descobrir(None, AGORA)
    assert [a.url.rsplit("/", 1)[1] for a in alvos] == [
        "ultimas-4-semanas-diesel-gnv.csv",
        "ultimas-4-semanas-gasolina-etanol.csv",
        "ultimas-4-semanas-glp.csv",
    ]


def test_anp_semestre_fechado_nao_e_baixado_de_novo_mas_o_recente_sim():
    vale = FONTES_DO_LOTE["anp-precos-semestral"].guardado_vale
    assert vale is not None
    assert vale(_anterior(lote_setoriais.DIAS_DO_SEMESTRE_FECHADO + 1)) is True
    assert vale(_anterior(10)) is False


def test_baixado_sem_fuso_vale_como_utc():
    sem_fuso = SimpleNamespace(
        baixado_em=(datetime.now(UTC) - timedelta(days=200)).replace(tzinfo=None)
    )
    assert lote_setoriais._semestre_fechado(sem_fuso) is True


# --------------------------------------------------------------- INPI
def test_inpi_so_leva_arquivos_sem_coluna_de_pessoa():
    todos = [
        a
        for id_ in ("inpi-patentes", "inpi-contratos")
        for a in FONTES_DO_LOTE[id_].descobrir(None, AGORA)
    ]
    nomes = [a.url.rsplit("/", 1)[1] for a in todos]
    assert nomes == [
        "PATENTES_DADOS_BIBLIOGRAFICOS.csv",
        "PATENTES_CLASSIFICACAO_IPC.csv",
        "PATENTES_VINCULOS.csv",
        "PATENTES_DESPACHOS.csv",
        "CONTRATOS_DADOS_BASICOS.csv",
        "CONTRATOS_DESPACHO.csv",
    ]
    pessoas = ("INVENTOR", "PROCURADOR", "AUTOR", "DEPOSITANTE", "TITULAR", "CEDENTE")
    pessoas += ("CESSIONARIO",)
    assert not [n for n in nomes if any(p in n for p in pessoas)]
    assert all(
        a.url.startswith("https://dadosabertos.inpi.gov.br/download/") for a in todos
    )
    assert not any("MARCAS" in n for n in nomes)  # 1,9 GB: na fila


def test_inpi_arquivo_baixado_este_mes_vale_e_o_antigo_e_baixado_de_novo():
    vale = FONTES_DO_LOTE["inpi-patentes"].guardado_vale
    assert vale is not None
    assert vale(_anterior(5)) is True
    assert vale(_anterior(lote_setoriais.DIAS_DA_ATUALIZACAO_DO_INPI + 2)) is False
    assert FONTES_DO_LOTE["inpi-contratos"].guardado_vale is vale
