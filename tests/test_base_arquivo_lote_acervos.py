"""Lote acervos históricos (base/arquivo/lote_acervos.py): COTAHIST anual da B3, relatórios e SGS antigo do
BCB, FTP do IBGE, pacotes de dívida do Tesouro e IPEADATA. Nada vai à internet: as listagens e as respostas
do CKAN são dublês de `tests/arquivos/acervos/`. Nenhuma fonte do lote traz pessoa física (ADR 0088)."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from base.arquivo import destinos, fontes
from base.arquivo import lote_acervos as lote
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from base.arquivo.registro import TERMOS_LIDOS_EM
from src.banco.coletas import (
    A_CONFIRMAR,
    NAO_COMERCIAL,
    SEM_LICENCA_CONHECIDA,
    VENDAVEL_COM_ATRIBUICAO,
    VENDAVEL_ODBL,
    licenca_da_fonte,
    revenda_da_fonte,
)

AGORA = datetime(2026, 10, 24, 6, tzinfo=UTC)
PASTA = Path(__file__).parent / "arquivos" / "acervos"


class Servidor:
    """Um cliente de mentira: responde com o gravado e lembra o que foi pedido."""

    def __init__(self, respostas: dict[str, bytes]):
        self.respostas = respostas
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        return Resposta(url, self.respostas[url], {})


def _dia(texto: str) -> date:
    dia, mes, ano = texto.split("/")
    return date(int(ano), int(mes), int(dia))


def _gravado(nome: str) -> bytes:
    return (PASTA / nome).read_bytes()


def _fonte(id_: str):
    return next(f for f in lote.fontes() if f.id == id_)


def _urls(id_: str, cliente=None) -> list[str]:
    return [a.url for a in _fonte(id_).descobrir(cliente or Servidor({}), AGORA)]


def test_nenhum_id_repetido_nem_igual_ao_de_outro_lote():
    ids = [f.id for f in lote.fontes()]
    assert len(ids) == len(set(ids))
    todos = [f.id for f in fontes.FONTES]
    assert len(todos) == len(set(todos))
    assert set(ids) <= set(todos)


def test_toda_fonte_tem_licenca_marca_data_e_destino():
    for f in lote.fontes():
        familia = f.id.split("-", 1)[0]
        assert licenca_da_fonte(f.id) != SEM_LICENCA_CONHECIDA, f.id
        assert revenda_da_fonte(f.id), f.id
        assert familia in TERMOS_LIDOS_EM, f.id
        assert f.id in destinos.DESTINOS, f.id


def test_marca_de_cada_familia():
    assert revenda_da_fonte("b3-cotahist-anual") == NAO_COMERCIAL
    assert revenda_da_fonte("bcb-relatorio-anual") == VENDAVEL_ODBL
    assert revenda_da_fonte("bcb-sgs-pre-2000") == VENDAVEL_ODBL
    assert revenda_da_fonte("ibge-precos-ftp") == VENDAVEL_COM_ATRIBUICAO
    assert revenda_da_fonte("ibge-contas-nacionais-ftp") == VENDAVEL_COM_ATRIBUICAO
    assert revenda_da_fonte("tesouro-br-divida-emissoes-diretas") == (
        VENDAVEL_COM_ATRIBUICAO
    )
    assert revenda_da_fonte("ipea-odata-series") == A_CONFIRMAR
    assert revenda_da_fonte("ipea-odata-metadados") == A_CONFIRMAR


def test_ritmo_o_que_nunca_muda_so_roda_pelo_id():
    carga_unica = {f.id for f in lote.fontes() if f.grupo == lote.CARGA_UNICA}
    assert carga_unica == {
        "b3-cotahist-anual",
        "bcb-relatorio-anual",
        "bcb-sgs-pre-2000",
    }
    assert {f.grupo for f in lote.fontes()} <= {lote.CARGA_UNICA, lote.MENSAL}


def test_as_grandes_sao_pesadas():
    pesadas = {f.id for f in lote.fontes() if f.pesada}
    assert {
        "b3-cotahist-anual",
        "bcb-relatorio-anual",
        "ibge-precos-ftp",
        "ibge-contas-nacionais-ftp",
        "ipea-odata-metadados",
    } <= pesadas


# ---------- B3 ----------


def test_cotahist_anual_vai_de_1986_a_2009_um_zip_por_ano():
    urls = _urls("b3-cotahist-anual")
    anos = [int(u.rsplit("_A", 1)[1][:4]) for u in urls]
    assert anos == list(range(1986, 2010))
    assert urls[0].endswith("COTAHIST_A1986.ZIP")
    assert not any("A1985" in u for u in urls)
    assert not any("A2010" in u for u in urls)


def test_cotahist_anual_nao_lista_a_pasta_que_responde_403():
    servidor = Servidor({})
    _urls("b3-cotahist-anual", servidor)
    assert servidor.pedidos == []


# ---------- BCB ----------


def test_relatorios_anuais_de_1997_a_2011():
    servidor = Servidor(
        {
            pagina: _gravado("bcb_capitulos_1998.html")
            for pagina in lote.PAGINAS_DOS_RELATORIOS_EM_CAPITULOS
        }
    )
    urls = _urls("bcb-relatorio-anual", servidor)
    assert urls[0] == lote.RELATORIO_DE_1997
    assert f"{lote.PASTA_DO_RELATORIO}banual98/rel1998cap1p.pdf" in urls
    assert f"{lote.PASTA_DO_RELATORIO}banual99/rel1998apendp.pdf" in urls
    assert urls.count(f"{lote.PASTA_DO_RELATORIO}banual98/rel1998cap1p.pdf") == 1
    assert f"{lote.PASTA_DO_RELATORIO}banual2000/rel2000p.pdf" in urls
    assert urls[-1] == f"{lote.PASTA_DO_RELATORIO}banual2011/rel2011p.pdf"
    assert not any("banual2012" in u or "banual96" in u for u in urls)
    assert all(u.endswith(".pdf") for u in urls)


def test_pagina_de_capitulos_sem_pdf_e_erro_com_o_nome_dela():
    pagina = lote.PAGINAS_DOS_RELATORIOS_EM_CAPITULOS[0]
    servidor = Servidor({pagina: b"<html>mudou o site</html>"})
    with pytest.raises(ErroDeDescoberta, match="banual98"):
        _fonte("bcb-relatorio-anual").descobrir(servidor, AGORA)


def test_janelas_do_sgs_tem_ate_dez_anos_sem_buraco_nem_sobreposicao():
    achadas = lote.janelas(date(1984, 11, 28), date(1999, 12, 31))
    assert achadas == [
        (date(1984, 11, 28), date(1994, 11, 27)),
        (date(1994, 11, 28), date(1999, 12, 31)),
    ]
    assert lote.janelas(date(1990, 1, 1), date(1990, 1, 1)) == [
        (date(1990, 1, 1), date(1990, 1, 1))
    ]


def test_janela_que_comeca_em_29_de_fevereiro_nao_quebra():
    achadas = lote.janelas(date(1980, 2, 29), date(1999, 12, 31))
    assert achadas[0] == (date(1980, 2, 29), date(1990, 2, 27))
    assert achadas[1][0] == date(1990, 2, 28)


def test_sgs_antigo_pede_cada_serie_ate_31_12_1999_em_json():
    alvos = _fonte("bcb-sgs-pre-2000").descobrir(Servidor({}), AGORA)
    assert all(a.extensao == ".json" for a in alvos)
    codigos = {int(a.url.split("bcdata.sgs.")[1].split("/")[0]) for a in alvos}
    assert codigos == set(lote.SERIES_DO_SGS_ANTIGO)
    assert all(
        "dataFinal=31/12/1999" in a.url
        for a in alvos
        if "dataInicial=01/01/1995" in a.url
    )
    assert not any("dataFinal=0" in a.url and "/2000" in a.url for a in alvos)
    assert any("dataInicial=28/11/1984" in a.url for a in alvos)
    assert any("dataInicial=04/06/1986" in a.url for a in alvos)


def test_sgs_antigo_nenhum_pedido_passa_de_dez_anos():
    for a in _fonte("bcb-sgs-pre-2000").descobrir(Servidor({}), AGORA):
        inicio = _dia(a.url.split("dataInicial=")[1][:10])
        fim = _dia(a.url.split("dataFinal=")[1][:10])
        assert (fim - inicio).days < 366 * 10, a.url
        assert fim.year <= 1999


# ---------- IBGE ----------


def test_listagem_do_ibge_ignora_ordenacao_pai_site_e_pagina_html():
    pasta = "https://ftp.ibge.gov.br/Teste/"
    servidor = Servidor({pasta: _gravado("ibge_listagem.html")})
    alvos = lote.arquivos_da_pasta(servidor, pasta, 0)
    assert [a.url for a in alvos] == [
        pasta + "inpc_SerieHist.zip",
        pasta + "Leia_me.txt",
    ]


def test_listagem_do_ibge_desce_so_os_niveis_pedidos():
    pasta = "https://ftp.ibge.gov.br/Teste/"
    sub = pasta + "Subpasta/"
    servidor = Servidor(
        {
            pasta: _gravado("ibge_listagem.html"),
            sub: _gravado("ibge_subpasta.html"),
        }
    )
    um_nivel = [a.url for a in lote.arquivos_da_pasta(servidor, pasta, 1)]
    assert sub + "Tabela_2005.XLS" in um_nivel
    assert sub + "Pasta_Funda/" not in servidor.pedidos
    assert not any(u.endswith("/") for u in um_nivel)


def test_precos_do_ibge_pega_as_quatro_pastas_e_so_arquivo_de_dado():
    respostas = {
        pasta: _gravado("ibge_listagem.html")
        for pasta, _ in lote.PASTAS_DE_PRECOS_DO_IBGE
    }
    urls = _urls("ibge-precos-ftp", Servidor(respostas))
    assert len(urls) == 2 * len(lote.PASTAS_DE_PRECOS_DO_IBGE)
    assert all(u.lower().endswith((".zip", ".txt")) for u in urls)
    assert not any(u.endswith(".html") for u in urls)


def test_precos_do_ibge_com_pasta_vazia_falha_com_o_nome_dela():
    vazia = b'<a href="?C=N;O=D">Name</a><a href="/x/">Parent Directory</a>'
    respostas = {
        pasta: _gravado("ibge_listagem.html")
        for pasta, _ in lote.PASTAS_DE_PRECOS_DO_IBGE
    }
    pasta_sem_nada = lote.PASTAS_DE_PRECOS_DO_IBGE[2][0]
    respostas[pasta_sem_nada] = vazia
    with pytest.raises(ErroDeDescoberta, match="INPC/"):
        _fonte("ibge-precos-ftp").descobrir(Servidor(respostas), AGORA)


def test_contas_nacionais_pega_as_pastas_de_ano_e_deixa_notas_e_seminarios():
    raiz = lote.CONTAS_DO_IBGE
    a2023 = raiz + "2023/"
    servidor = Servidor(
        {
            raiz: _gravado("ibge_contas_raiz.html"),
            raiz + "2005/": _gravado("ibge_contas_2005.html"),
            a2023: _gravado("ibge_contas_2023.html"),
            a2023 + "tabelas_xls/": _gravado("ibge_contas_2023_xls.html"),
            a2023 + "tabelas_xls/sinoticas/": _gravado(
                "ibge_contas_2023_sinoticas.html"
            ),
        }
    )
    urls = _urls("ibge-contas-nacionais-ftp", servidor)
    assert raiz + "2005/Consolidado.zip" in urls
    assert a2023 + "tabelas_xls/sinoticas/Tabela1.xls" in urls
    assert a2023 + "indice_tabelas_sinoticas.pdf" in urls
    assert not any(
        "Notas_Metodologicas" in p or "Seminarios" in p for p in servidor.pedidos
    )


def test_contas_nacionais_sem_pasta_de_ano_e_erro():
    servidor = Servidor({lote.CONTAS_DO_IBGE: b'<a href="Notas/">Notas/</a>'})
    with pytest.raises(ErroDeDescoberta, match="Contas_Nacionais"):
        _fonte("ibge-contas-nacionais-ftp").descobrir(servidor, AGORA)


# ---------- Tesouro ----------


def test_pacotes_de_divida_pegam_so_o_csv_e_deixam_o_pdf():
    pacote = "estoque-da-divida-de-estados-e-do-distrito-federal"
    servidor = Servidor(
        {
            f"{lote.PORTAL_DO_TESOURO}/api/3/action/package_show?id={pacote}": _gravado(
                "divida-dos-estados.json"
            )
        }
    )
    urls = _urls("tesouro-br-divida-estados-estoque", servidor)
    assert [u.rsplit("/", 1)[-1] for u in urls] == ["relatorio-estoque-final.csv"]


def test_pacote_sem_arquivo_do_formato_e_erro_com_o_nome_dele():
    pacote = "servico-da-divida-de-estados-e-do-distrito-federal"
    servidor = Servidor(
        {
            f"{lote.PORTAL_DO_TESOURO}/api/3/action/package_show?id={pacote}": (
                b'{"result": {"resources": [{"format": "PDF", "url": "https://x/a.pdf"}]}}'
            )
        }
    )
    with pytest.raises(ErroDeDescoberta, match=pacote):
        _fonte("tesouro-br-divida-estados-servico").descobrir(servidor, AGORA)


def test_nao_coleta_os_pacotes_sem_licenca_escrita():
    usados = {pacote for pacote, _ in lote.PACOTES_DE_DIVIDA.values()}
    assert not usados & lote.NAO_COLETADOS_DO_TESOURO
    assert all(i.startswith("tesouro-br-divida-") for i in lote.PACOTES_DE_DIVIDA)


def test_pacotes_de_divida_nao_repetem_os_do_lote_do_tesouro():
    from base.arquivo import lote_tesouro

    assert not set(lote.PACOTES_DE_DIVIDA) & {f.id for f in lote_tesouro.fontes()}
    ja_usados = {
        p for _, pacotes, _, _ in lote_tesouro.PACOTES.values() for p in pacotes
    }
    assert not {pacote for pacote, _ in lote.PACOTES_DE_DIVIDA.values()} & ja_usados


# ---------- IPEADATA ----------


def test_ipeadata_pega_os_metadados_e_cada_serie_pelo_codigo():
    assert _urls("ipea-odata-metadados") == [lote.METADADOS_DO_IPEADATA]
    urls = _urls("ipea-odata-series")
    assert len(urls) == len(lote.SERIES_DO_IPEADATA)
    assert f"{lote.RAIZ_DO_IPEADATA}ValoresSerie(SERCODIGO='GM366_IBVSP366')" in urls
    assert all(
        a.extensao == ".json"
        for a in _fonte("ipea-odata-series").descobrir(Servidor({}), AGORA)
    )


def test_ibovespa_do_ipeadata_avisa_que_1995_nao_e_serie_limpa():
    assert "implausíveis" in lote.SERIES_DO_IPEADATA["GM366_IBVSP366"]


# ---------- LGPD (ADR 0088) ----------


def test_nenhuma_fonte_do_lote_aponta_para_arquivo_de_pessoa_fisica():
    """Nada de FRE, cadastro de pessoa, investidor ou sócio: o lote só guarda série, índice e relatório."""
    proibidas = ("fre", "investidor", "socio", "pessoa", "cpf", "servidor", "diretor")
    enderecos = [
        *lote.PACOTES_DE_DIVIDA,
        *(pacote for pacote, _ in lote.PACOTES_DE_DIVIDA.values()),
        *(f.id for f in lote.fontes()),
        *lote.SERIES_DO_IPEADATA,
        lote.COTAHIST_ANUAL,
        lote.PRECOS_DO_IBGE,
        lote.CONTAS_DO_IBGE,
    ]
    for texto in enderecos:
        assert not any(p in texto.lower() for p in proibidas), texto
    assert not any(f.id.startswith("cvm-") for f in lote.fontes())
