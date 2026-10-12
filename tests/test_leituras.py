"""Leituras guardadas (Research R5): o banco, a leitura do 10-K na coleta da SEC e a coleta dos
fatos relevantes da CVM. Sem internet: a SEC e a CVM são simuladas."""

import json
import uuid
from datetime import date, datetime

import pytest
import sqlalchemy as sa

from scripts import atualizar_leituras_cvm
from src import coleta_sec, leitura
from src import eventos_sec as sec
from src.banco import leituras as repo
from src.banco.modelo import eventos
from src.eventos import FONTE_IPE
from src.relatorios import FUSO
from tests.test_fundamentos_sec import _abrir, _coletar_apple
from tests.test_leitura import FATO, RISCOS_ANTES, _10k, _pdf
from tests.test_research_no_app import _app_local, _coletar

CIK = 320193
CHAVE = sec.cik_como_chave(CIK)
RISCO_NOVO = (
    "Tariffs imposed on imported semiconductors could materially increase our costs, and "
    "further tariffs and export restrictions may disrupt our supply chain."
)


# --- banco ---------------------------------------------------------------------------------------
def test_gravar_troca_a_leitura_anterior(banco):
    with banco.begin() as c:
        repo.gravar_leitura(c, FONTE_IPE, "p1", repo.RESUMO, "cnpj", None, {"a": 1})
        repo.gravar_leitura(c, FONTE_IPE, "p1", repo.RESUMO, "cnpj", None, {"a": 2})
    with banco.connect() as c:
        assert repo.resumos(c, FONTE_IPE, ["p1", "p2"]) == {"p1": {"a": 2}}
        assert repo.lidos(c, FONTE_IPE, repo.RESUMO, ["p1", "p2"]) == {"p1"}
        assert repo.lidos(c, FONTE_IPE, repo.RISCOS, ["p1"]) == set()


def test_versao_antiga_conta_como_nao_lida(banco, monkeypatch):
    with banco.begin() as c:
        repo.gravar_leitura(c, FONTE_IPE, "p1", repo.RESUMO, "cnpj", None, {})
    monkeypatch.setattr(repo, "VERSAO", "2")  # o algoritmo mudou: refazer
    with banco.connect() as c:
        assert repo.lidos(c, FONTE_IPE, repo.RESUMO, ["p1"]) == set()


def test_ultima_de_riscos_e_a_mais_recente_mesmo_com_data_vazia(banco):
    with banco.begin() as c:
        for protocolo, referencia in (
            ("velho", date(2024, 9, 28)),
            ("sem-data", None),
            ("novo", date(2025, 9, 27)),
        ):
            repo.gravar_leitura(
                c, sec.FONTE_SEC, protocolo, repo.RISCOS, CHAVE, referencia, {}
            )
    with banco.connect() as c:
        assert repo.ultima_de_riscos(c, CHAVE)[:2] == ("novo", date(2025, 9, 27))
        assert repo.ultima_de_riscos(c, "outra") is None


def _fato(
    c, protocolo: str, publicado: date, categoria: str = "Fato Relevante"
) -> None:
    c.execute(
        sa.insert(eventos).values(
            id=uuid.uuid4(),
            fonte=FONTE_IPE,
            protocolo=protocolo,
            cnpj="11.111.111/0001-11",
            empresa="Exemplo",
            categoria=categoria,
            rotulo="Fato relevante",
            tema="outros",
            materialidade=3,
            publicado_em=publicado,
            link=f"https://cvm/{protocolo}",
        )
    )


def test_fatos_sem_leitura(banco):
    with banco.begin() as c:
        _fato(c, "antigo", date(2026, 8, 1))
        _fato(c, "lido", date(2026, 10, 1))
        _fato(c, "novo", date(2026, 10, 10))
        _fato(c, "comunicado", date(2026, 10, 11), categoria="Comunicado ao Mercado")
        repo.gravar_leitura(c, FONTE_IPE, "lido", repo.RESUMO, "x", None, {})
    with banco.connect() as c:
        pendentes = repo.fatos_sem_leitura(
            c, FONTE_IPE, "Fato Relevante", date(2026, 9, 12), 10
        )
    assert [p[0] for p in pendentes] == ["novo"]
    assert pendentes[0][2:] == (date(2026, 10, 10), "https://cvm/novo")


# --- SEC: fatores de risco do 10-K ----------------------------------------------------------------
def _lista(
    recentes: list[tuple[str, str, str, str]], paginas: tuple[str, ...] = ()
) -> bytes:
    """A lista de documentos da SEC: (formulário, protocolo, data-base, documento)."""
    colunas = {
        "form": [r[0] for r in recentes],
        "accessionNumber": [r[1] for r in recentes],
        "reportDate": [r[2] for r in recentes],
        "primaryDocument": [r[3] for r in recentes],
    }
    return json.dumps(
        {"filings": {"recent": colunas, "files": [{"name": nome} for nome in paginas]}}
    ).encode()


def _sec(pedidos: list[str], paginas: dict[str, bytes] | None = None):
    documentos = {
        "novo.htm": _10k([*RISCOS_ANTES, RISCO_NOVO]).encode(),
        "velho.htm": _10k(RISCOS_ANTES).encode(),
    }

    def transporte(url: str, agente: str) -> bytes:
        pedidos.append(url)
        nome = url.rsplit("/", 1)[-1]
        if nome in documentos:
            return documentos[nome]
        if paginas and nome in paginas:
            return paginas[nome]
        raise AssertionError(f"consulta inesperada: {url}")

    return coleta_sec.ClienteSec("TickerLab contato@tickerlab.com.br", 0, transporte)


DOIS_10K = [
    ("10-K", "0000320193-25-000079", "2025-09-27", "novo.htm"),
    ("8-K", "0000320193-25-000070", "2025-08-01", "oito.htm"),
    ("10-K/A", "0000320193-25-000010", "2025-01-10", "retificado.htm"),
    ("10-K", "0000320193-24-000123", "2024-09-28", "velho.htm"),
]


def test_compara_os_dois_ultimos_10k(banco):
    pedidos = []
    assert coleta_sec.gravar_leitura_do_10k(banco, _sec(pedidos), _lista(DOIS_10K), CIK)
    with banco.connect() as c:
        protocolo, referencia, resultado = repo.ultima_de_riscos(c, CHAVE)
    assert (protocolo, referencia) == ("0000320193-25-000079", date(2025, 9, 27))
    assert resultado["novas_no_total"] == 1 and resultado["frases_novas"] == [
        RISCO_NOVO
    ]
    assert resultado["referencia_antes"] == "2024-09-28"
    assert resultado["link_antes"].endswith("/000032019324000123/velho.htm")
    assert len(pedidos) == 2  # só os dois 10-K (nada de 8-K nem de retificação)


def test_10k_ja_lido_nao_baixa_de_novo(banco):
    coleta_sec.gravar_leitura_do_10k(banco, _sec([]), _lista(DOIS_10K), CIK)
    pedidos = []
    assert not coleta_sec.gravar_leitura_do_10k(
        banco, _sec(pedidos), _lista(DOIS_10K), CIK
    )
    assert pedidos == []


def test_10k_anterior_na_pagina_antiga(banco):
    """Num banco grande, o 10-K do ano anterior fica fora dos ~1.000 documentos recentes."""
    pagina = _lista(
        [DOIS_10K[3]]
    )  # a página antiga tem as colunas direto, sem "filings"
    pagina = json.dumps(json.loads(pagina)["filings"]["recent"]).encode()
    nome = "CIK0000320193-submissions-001.json"
    pedidos = []
    cliente = _sec(pedidos, {nome: pagina})
    assert coleta_sec.gravar_leitura_do_10k(
        banco, cliente, _lista(DOIS_10K[:1], (nome,)), CIK
    )
    assert pedidos[0] == coleta_sec.URL_DA_PAGINA_ANTIGA.format(nome=nome)
    with banco.connect() as c:
        assert repo.ultima_de_riscos(c, CHAVE)[2]["referencia_antes"] == "2024-09-28"


def test_um_10k_so_nao_compara(banco):
    pedidos = []
    assert not coleta_sec.gravar_leitura_do_10k(
        banco, _sec(pedidos), _lista(DOIS_10K[:1]), CIK
    )
    assert pedidos == []


def test_10k_sem_a_secao_grava_o_motivo(banco):
    def transporte(url: str, agente: str) -> bytes:
        return b"<html><p>Documento sem a se\xc3\xa7\xc3\xa3o.</p></html>"

    cliente = coleta_sec.ClienteSec("TickerLab contato@tickerlab.com.br", 0, transporte)
    assert coleta_sec.gravar_leitura_do_10k(banco, cliente, _lista(DOIS_10K), CIK)
    with banco.connect() as c:
        resultado = repo.ultima_de_riscos(c, CHAVE)[2]
    assert "motivo" in resultado and resultado["versao"] == leitura.VERSAO


# --- CVM: fatos relevantes ------------------------------------------------------------------------
@pytest.fixture
def cvm(banco, monkeypatch):
    """Dois fatos relevantes pendentes; a CVM simulada devolve o que estiver em `respostas`."""
    hoje = datetime.now(FUSO).date()  # o mesmo "hoje" da coleta (São Paulo)
    with banco.begin() as c:
        _fato(c, "f1", hoje)
        _fato(c, "f2", hoje)
    respostas: list[bytes] = []
    monkeypatch.setattr(atualizar_leituras_cvm, "baixar", lambda url: respostas.pop(0))
    monkeypatch.setattr(atualizar_leituras_cvm.time, "sleep", lambda s: None)
    return respostas


def test_coleta_da_cvm_grava_os_resumos(banco, cvm):
    cvm.extend([_pdf(" ".join(FATO.split())), _pdf("Curto.")])
    assert atualizar_leituras_cvm.main([]) == 0
    with banco.connect() as c:
        guardados = repo.resumos(c, FONTE_IPE, ["f1", "f2"])
    assert len(guardados) == 2
    assert any(
        "motivo" in r for r in guardados.values()
    )  # o PDF sem texto guarda o motivo
    assert any("frases" in r for r in guardados.values())


def test_coleta_da_cvm_para_no_limite_de_downloads(banco, cvm):
    cvm.extend([b"<html>Limite de downloads</html>", _pdf("nunca pedido")])
    assert atualizar_leituras_cvm.main([]) == 0
    assert len(cvm) == 1  # parou no aviso, sem pedir o segundo
    with banco.connect() as c:
        assert repo.resumos(c, FONTE_IPE, ["f1", "f2"]) == {}


def test_pdf_ilegivel_guarda_o_motivo():
    resultado = atualizar_leituras_cvm.ler(b"%PDF-1.4 lixo %%EOF")
    assert resultado == {"motivo": "PDF ilegível.", "versao": leitura.VERSAO}


# --- telas ----------------------------------------------------------------------------------------
def test_acontecimentos_mostra_o_resumo_do_fato(banco):
    _coletar(banco)
    with banco.begin() as c:
        protocolos = c.execute(sa.select(eventos.c.protocolo, eventos.c.cnpj)).all()
        for protocolo, cnpj in protocolos:
            resumo = leitura.resumir_fato_relevante(FATO).para_guardar()
            repo.gravar_leitura(
                c, FONTE_IPE, protocolo, repo.RESUMO, cnpj, None, resumo
            )
    app = _app_local()
    assert not app.exception
    resumos = [e for e in app.expander if e.label == "Resumo automático do documento"]
    assert resumos
    texto = " ".join(m.value for m in resumos[0].markdown)
    assert "aquisição de 100%" in texto
    assert "sem inteligência artificial" in " ".join(
        c.value for c in resumos[0].caption
    )


def test_fundamentos_mostra_o_que_mudou_nos_riscos(banco):
    _coletar_apple(banco)
    coleta_sec.gravar_leitura_do_10k(banco, _sec([]), _lista(DOIS_10K), CIK)
    app = _abrir("AAPL")
    assert not app.exception
    assert any("Fatores de risco" in m.value for m in app.markdown)
    metricas = {m.label: m.value for m in app.metric}
    assert metricas["Frases novas"] == "1"
    assert "Lazy Prices" in " ".join(c.value for c in app.caption)
