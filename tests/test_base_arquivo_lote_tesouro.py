"""Lote Tesouro (base/arquivo/lote_tesouro.py): pacotes novos do Tesouro Transparente e a dívida ativa da
PGFN de todos os trimestres. Nada vai à internet: as respostas do `package_show` e as listagens da PGFN
são dublês de `tests/arquivos/tesouro/`. O que não pode faltar aqui é a LGPD: dado por investidor não entra."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from base.arquivo import destinos, fontes
from base.arquivo import lote_tesouro as lote
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from src.banco.coletas import SEM_LICENCA_CONHECIDA, licenca_da_fonte, revenda_da_fonte

AGORA = datetime(2026, 10, 23, 22, tzinfo=UTC)
PASTA = Path(__file__).parent / "arquivos" / "tesouro"
PACOTES_POR_INVESTIDOR = {
    "investidores-do-tesouro-direto",
    "operacoes-do-tesouro-direto",
}
PACOTES_SEM_ARQUIVO = {"seriestemporaisdotesouronacional"}


class Portal:
    """Um cliente de mentira: responde ao `package_show` e às listagens da PGFN com o gravado."""

    def __init__(self, respostas: dict[str, bytes]):
        self.respostas = respostas
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        chave = url.rsplit("=", 1)[-1] if "package_show" in url else url
        return Resposta(url, self.respostas[chave], {})


def _gravado(nome: str) -> bytes:
    return (PASTA / nome).read_bytes()


def _fonte(id_: str):
    return next(f for f in lote.fontes() if f.id == id_)


def _urls(id_: str, pacote: str) -> list[str]:
    portal = Portal({pacote: _gravado(f"{pacote}.json")})
    return [a.url for a in _fonte(id_).descobrir(portal, AGORA)]


def test_nenhum_id_repetido_nem_igual_ao_de_outro_lote():
    ids = [f.id for f in lote.fontes()]
    assert len(ids) == len(set(ids))
    todos = [f.id for f in fontes.FONTES]
    assert len(todos) == len(set(todos))
    assert set(ids) <= set(todos)


def test_so_pacotes_sem_dado_por_investidor_nem_sem_arquivo():
    usados = {p for _, pacotes, _, _ in lote.PACOTES.values() for p in pacotes}
    assert not usados & PACOTES_POR_INVESTIDOR
    assert not usados & PACOTES_SEM_ARQUIVO
    assert all(i.startswith("tesouro-br-") for i in lote.PACOTES)


def test_pega_so_o_formato_do_dado_e_deixa_pdf_e_api():
    urls = _urls("tesouro-br-rtn", "resultado-do-tesouro-nacional")
    assert [u.rsplit("/", 1)[-1] for u in urls] == [
        "seriehistoricajul26.xlsx",
        "metadados---nfgc.xlsx",
    ]


def test_csv_dos_pacotes_de_csv_sem_o_pdf_gemeo():
    portal = Portal(
        {
            "garantias-concedidas-em-operacoes-de-credito": _gravado(
                "garantias-concedidas-em-operacoes-de-credito.json"
            )
        }
    )
    alvos = lote.descobrir_ckan(
        portal,
        lote.PORTAL_DO_TESOURO,
        "garantias-concedidas-em-operacoes-de-credito",
        formatos=lote.CSV,
    )
    assert [a.url.rsplit("/", 1)[-1] for a in alvos] == [
        "concessao-de-garantias-externas.csv"
    ]


def test_subsidios_do_bndes_so_existem_em_pdf_e_vao_em_pdf():
    urls = _urls("tesouro-br-subsidios-bndes", "relatorio-de-subsidios-ao-bndes")
    assert len(urls) == 2
    assert all(u.endswith(".pdf") for u in urls)


def test_pacote_sem_arquivo_do_formato_e_erro_com_o_nome_dele():
    portal = Portal(
        {
            "resultado-do-tesouro-nacional": _gravado(
                "seriestemporaisdotesouronacional.json"
            )
        }
    )
    with pytest.raises(ErroDeDescoberta, match="resultado-do-tesouro-nacional"):
        _fonte("tesouro-br-rtn").descobrir(portal, AGORA)


def test_as_grandes_sao_pesadas_e_o_resto_nao():
    pesadas = {f.id for f in lote.fontes() if f.pesada}
    assert pesadas == {
        "tesouro-br-despesas",
        "tesouro-br-transferencias",
        "tesouro-br-capag-municipios",
        "pgfn-divida-historico",
    }
    assert {f.grupo for f in lote.fontes()} <= {"semanal", "mensal", "carga-unica"}


def test_pgfn_historica_nao_devolve_o_ultimo_trimestre():
    raiz = lote.RAIZ_DA_PGFN
    respostas = {
        raiz: _gravado("pgfn_raiz.html"),
        f"{raiz}2025_trimestre_04/": _gravado("pgfn_pasta.html"),
        f"{raiz}2026_trimestre_01/": _gravado("pgfn_pasta.html"),
        f"{raiz}2026_trimestre_02/": _gravado("pgfn_pasta.html"),
    }
    cliente = Portal(respostas)
    urls = [a.url for a in lote.descobrir_pgfn_historico(cliente, AGORA)]
    assert len(urls) == 6
    assert all("2026_trimestre_02" not in u for u in urls)
    assert f"{raiz}2025_trimestre_04/Dados_abertos_FGTS.zip" in urls
    assert f"{raiz}2026_trimestre_02/" not in cliente.pedidos


def test_pgfn_historica_com_um_trimestre_so_e_erro():
    um = b'<a href="2026_trimestre_02/">2026_trimestre_02/</a>'
    with pytest.raises(ErroDeDescoberta, match="PGFN"):
        lote.descobrir_pgfn_historico(Portal({lote.RAIZ_DA_PGFN: um}), AGORA)


def test_pgfn_historica_e_carga_unica_e_convive_com_a_do_ultimo_trimestre():
    assert _fonte("pgfn-divida-historico").grupo == "carga-unica"
    assert "pgfn-divida" in {f.id for f in fontes.FONTES}


def test_toda_fonte_nova_tem_licenca_conhecida_e_destino():
    for f in lote.fontes():
        assert licenca_da_fonte(f.id) != SEM_LICENCA_CONHECIDA
        assert len(licenca_da_fonte(f.id)) <= 80
        assert f.id in destinos.DESTINOS


def test_revenda_igual_a_das_irmas():
    assert revenda_da_fonte("tesouro-br-rtn") == revenda_da_fonte("tesouro-br-divida")
    assert revenda_da_fonte("pgfn-divida-historico") == revenda_da_fonte("pgfn-divida")


def test_macro_fiscal_e_dividendos_apontam_para_o_research():
    for id_ in ("tesouro-br-rtn", "tesouro-br-receitas", "tesouro-br-despesas"):
        assert "macro-fiscal" in destinos.DESTINOS[id_].onde
    assert "dividendos" in destinos.DESTINOS["tesouro-br-dividendos-estatais"].onde
    assert destinos.DESTINOS["pgfn-divida-historico"].onde == "pgfn/historico"
