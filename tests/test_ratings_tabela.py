"""Tabela `ratings` da base: uma linha por documento lido, sem olhar o futuro e sem contar o mesmo
evento duas vezes (relatório da agência + comunicado da companhia). Sem internet: o IPE e os PDFs são
montados aqui e guardados num acervo de mentira."""

import io
import json
import zipfile
from datetime import UTC, date, datetime

import pandas as pd
import pytest
from fpdf import FPDF

from base import ratings
from base.ancoragem import parquets_sem_manifesto
from base.licenca import licenca_da_tabela
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import Marca, registrar
from src.banco.conexao import criar_engine, migrar_para

VERSAO = "9b1e0c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7c"
AGORA = datetime(2026, 10, 17, 12, tzinfo=UTC)
RAD = "https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?Tela=ext&descTipo=IPE"
CNPJ = "11.111.111/0001-11"
FITCH = (
    "RATING ACTION COMMENTARY Fitch Afirma Rating 'AA(bra)' da Rodobens; Perspectiva Estável "
    "Fitch Ratings - Rio de Janeiro - 07 Jul 2023: A Fitch Ratings afirmou o Rating Nacional de "
    "Longo Prazo 'AA(bra)', com Perspectiva Estável, da Rodobens S.A."
)
COMUNICADO_DA_FITCH = (
    "RODOBENS S.A. Comunicado ao Mercado A Rodobens comunica que, em 7 de julho de 2023, a Fitch "
    "Ratings afirmou o Rating Nacional de Longo Prazo 'AA(bra)' da Companhia, perspectiva estável."
)
SEM_NOTA = "Comunicado ao Mercado: a Companhia contratou a Fitch Ratings para avaliar a emissão."


def _documento(protocolo: str, publico_em: str, **outros: object) -> dict[str, object]:
    return {
        "cnpj": CNPJ,
        "empresa": "RODOBENS S.A.",
        "codigo_cvm": "9999",
        "evidencia": "relatorio_de_agencia",
        "categoria": "Dados Econômico-Financeiros",
        "tipo": "Relatório de Agência de Rating",
        "assunto": "Fitch",
        "referencia": date.fromisoformat(publico_em),
        "publico_em": date.fromisoformat(publico_em),
        "protocolo": protocolo,
        "versao": 1,
        "link": f"{RAD}&numProtocolo={protocolo}",
        **outros,
    }


def _documentos(*linhas: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(list(linhas), columns=list(ratings.COLUNAS)).astype(
        {"versao": "Int64"}
    )


def _textos(documentos: pd.DataFrame, *textos: str | None) -> dict[str, str | None]:
    return dict(zip(documentos["link"], textos, strict=True))


# --- montar_ratings -----------------------------------------------------------------------------
def test_uma_linha_por_documento_lido_com_a_situacao_da_extracao():
    documentos = _documentos(
        _documento("1", "2023-07-10"),
        _documento("2", "2023-08-01"),
        _documento("3", "2023-09-01"),
        _documento("4", "2023-10-01"),  # ainda não baixado: fica de fora
    )
    tabela = ratings.montar_ratings(
        documentos, _textos(documentos.iloc[:3], FITCH, SEM_NOTA, None)
    )
    assert list(tabela.columns) == list(ratings.COLUNAS_DA_TABELA)
    assert tabela["protocolo"].tolist() == ["1", "2", "3"]
    assert tabela["situacao_extracao"].tolist() == [
        "extraido",
        "nao_extraido",
        "nao_e_pdf",
    ]
    extraida = tabela.iloc[0]
    assert (extraida["agencia"], extraida["escala"], extraida["nota"]) == (
        "fitch",
        "nacional",
        "AA",
    )
    assert (extraida["nivel"], extraida["perspectiva"], extraida["acao"]) == (
        3,
        "estavel",
        "afirmacao",
    )
    assert extraida["data_acao"] == date(2023, 7, 7)
    assert extraida["documentos"] == "1"
    # sem nota, sem inventar: as colunas do rating ficam vazias
    assert tabela.iloc[1][["agencia", "nota", "nivel", "data_acao"]].isna().all()


def test_passa_o_nome_da_companhia_para_a_extracao(monkeypatch):
    vistos: list[str | None] = []

    def extrair(texto: str, empresa: str | None = None) -> None:
        vistos.append(empresa)

    monkeypatch.setattr(ratings, "extrair_rating", extrair)
    documentos = _documentos(_documento("1", "2023-07-10"))
    ratings.montar_ratings(documentos, _textos(documentos, FITCH))
    assert vistos == ["RODOBENS S.A."]


def test_data_da_acao_depois_da_entrega_fica_vazia():
    """Data da ação depois da entrega à CVM é erro de leitura ou de digitação: nunca olha o futuro."""
    documentos = _documentos(_documento("1", "2023-07-01"))  # o texto diz 07/07/2023
    tabela = ratings.montar_ratings(documentos, _textos(documentos, FITCH))
    assert tabela["nota"].tolist() == ["AA"]
    assert tabela["data_acao"].isna().all()


def test_relatorio_e_comunicado_do_mesmo_evento_viram_uma_linha():
    documentos = _documentos(
        _documento(
            "20", "2023-07-12", evidencia="assunto", tipo="Comunicado ao Mercado"
        ),
        _documento("10", "2023-07-10"),
    )
    tabela = ratings.montar_ratings(
        documentos, _textos(documentos, COMUNICADO_DA_FITCH, FITCH)
    )
    assert len(tabela) == 1
    linha = tabela.iloc[0]
    assert (linha["publico_em"], linha["protocolo"]) == (date(2023, 7, 10), "10")
    assert linha["documentos"] == "10; 20"  # pela data de entrega


def test_sem_data_da_acao_nao_junta_documentos():
    """Sem a data da ação não dá para saber se é o mesmo evento: cada documento fica com a sua linha."""
    sem_data = "A Fitch Ratings afirmou o Rating Nacional de Longo Prazo 'AA(bra)' da Rodobens."
    documentos = _documentos(
        _documento("1", "2023-07-10"), _documento("2", "2024-07-10")
    )
    tabela = ratings.montar_ratings(documentos, _textos(documentos, sem_data, sem_data))
    assert tabela["protocolo"].tolist() == ["1", "2"]


@pytest.mark.parametrize(
    "data", ["2023-07-09", "2023-07-11", "2023-07-12", "2024-01-01"]
)
def test_como_era_na_data_nao_traz_nada_entregue_depois(data):
    documentos = _documentos(
        _documento("10", "2023-07-10"),
        _documento("20", "2023-07-12", evidencia="assunto"),
        _documento("30", "2023-08-01"),
    )
    textos = _textos(documentos, FITCH, COMUNICADO_DA_FITCH, SEM_NOTA)
    ate = date.fromisoformat(data)
    tabela = ratings.montar_ratings(documentos, textos, ate=ate)
    assert (tabela["publico_em"] <= ate).all()
    entregues_depois = set(documentos.loc[documentos["publico_em"] > ate, "protocolo"])
    citados = {p for d in tabela["documentos"] for p in d.split("; ")}
    assert not citados & entregues_depois
    # e é a tabela inteira cortada na data (fora a lista dos documentos do evento)
    inteira = ratings.montar_ratings(documentos, textos)
    cortada = inteira[inteira["publico_em"] <= ate].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        tabela.drop(columns="documentos"), cortada.drop(columns="documentos")
    )


def test_ler_texto_nao_quebra_com_o_que_nao_e_pdf():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=11)
    pdf.multi_cell(0, 6, FITCH)
    assert "Rodobens" in (ratings.ler_texto(bytes(pdf.output())) or "")
    assert ratings.ler_texto(b"PK\x03\x04 um .docx") is None
    assert ratings.ler_texto(b"%PDF-1.4 cortado") is None
    assert ratings.ler_texto(b"") is None


# --- montagem pelo acervo ----------------------------------------------------------------------
CABECALHO = (
    "CNPJ_Companhia;Nome_Companhia;Codigo_CVM;Data_Referencia;Categoria;Tipo;Especie;Assunto;"
    "Data_Entrega;Tipo_Apresentacao;Protocolo_Entrega;Versao;Link_Download"
)


def _ipe(*protocolos_e_datas: tuple[str, str]) -> bytes:
    linhas = [
        f"{CNPJ};RODOBENS S.A.;9999;{data};Dados Econômico-Financeiros;"
        f"Relatório de Agência de Rating;;Fitch;{data};AP;{p};1;{RAD}&numProtocolo={p}"
        for p, data in protocolos_e_datas
    ]
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            "ipe_cia_aberta_2023.csv", "\n".join([CABECALHO, *linhas]).encode("cp1252")
        )
    return saida.getvalue()


def _pdf(texto: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=11)
    pdf.multi_cell(0, 6, texto)
    return bytes(pdf.output())


def _guardar(fonte: str, url: str, conteudo: bytes) -> None:
    quando = datetime(2026, 10, 16, 23, tzinfo=UTC)
    caminho = acervo.guardar_original(fonte, url, conteudo, quando)
    with criar_engine().begin() as c:
        registrar(
            c, fonte, url, conteudo, "ok", agora=quando, caminho_do_original=caminho
        )


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    _guardar(
        ratings.FONTE_DO_IPE,
        ratings.URL_DO_IPE.format(ano=2023),
        _ipe(("10", "2023-07-10"), ("20", "2023-08-01"), ("30", "2023-09-01")),
    )
    _guardar(ratings.FONTE_DOS_PDFS, f"{RAD}&numProtocolo=10", _pdf(FITCH))
    _guardar(ratings.FONTE_DOS_PDFS, f"{RAD}&numProtocolo=20", b"PK\x03\x04 Word")
    return tmp_path


def test_montar_grava_a_tabela_com_manifesto_e_licenca_vendavel(ambiente):
    with criar_engine().connect() as conexao:
        resumo = ratings.montar(conexao, ambiente / "base", AGORA)
    arquivo = ambiente / "base" / "ratings" / "ratings.parquet"
    tabela = pd.read_parquet(arquivo)
    assert tabela["protocolo"].tolist() == ["10", "20"]  # o 30 ainda não veio
    assert tabela["situacao_extracao"].tolist() == ["extraido", "nao_e_pdf"]
    assert resumo == {"extraido": 1, "nao_extraido": 0, "nao_e_pdf": 1}
    assert len(tabela["origem_sha256"].iloc[0]) == 64
    assert tabela["versao_do_codigo"].iloc[0] == VERSAO
    assert tabela["montado_em"].iloc[0] == AGORA.isoformat()
    assert parquets_sem_manifesto(ambiente / "base") == []
    manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    assert manifesto["conferencia_do_contrato"]["aprovada"]
    # a CVM é ODbL: a tabela pode ser vendida, com atribuição (ADR 0008)
    assert licenca_da_tabela(arquivo).marca == Marca.VENDAVEL


def test_comando_monta_e_avisa_quando_nada_foi_baixado(ambiente, tmp_path):
    from scripts import montar_ratings

    assert montar_ratings.main(["--pasta", str(tmp_path / "b")]) == 0
    assert (tmp_path / "b" / "ratings" / "ratings.parquet").exists()
    assert (
        montar_ratings.main(["--pasta", str(tmp_path / "b")]) == 0
    )  # igual: nada regravado
