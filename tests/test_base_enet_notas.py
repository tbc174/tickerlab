"""Notas explicativas da DFP (linha 135 da fila): o texto do PDF do pacote do ENET, página por página,
guardado no acervo e montado em `notas_dfp` com a data em que a entrega ficou pública. Sem internet."""

import io
import zipfile
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from base.enet_antigo import FormatoNaoLido
from base.enet_notas import (
    COLUNAS,
    FONTE,
    desempacotar,
    empacotar,
    entregues_ate,
    guardar_notas,
    ja_guardadas,
    montar_tabela,
    paginas_do_pdf,
    pdf_do_pacote,
)
from src import acervo
from src.banco.modelo import coletas
from tests.ajudantes_da_sala import pdf

LINK = "http://www.rad.cvm.gov.br/ENETCONSULTA/frmDownloadDocumento.aspx?NumeroSequencialDocumento=1"
OUTRO = "http://www.rad.cvm.gov.br/ENETCONSULTA/frmDownloadDocumento.aspx?NumeroSequencialDocumento=2"
AGORA = datetime(2026, 10, 24, 15, tzinfo=UTC)


def _pacote(conteudo_do_pdf: bytes | None) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("014206DFP31-12-2025v1.xml", b"<xml />")
        if conteudo_do_pdf is not None:
            z.writestr("124061_014206_24102026071621.pdf", conteudo_do_pdf)
        z.writestr("DadosDocumento.xlsx", b"planilha")
    return saida.getvalue()


def _indice(*linhas) -> pd.DataFrame:
    return pd.DataFrame(
        linhas,
        columns=[
            "cnpj",
            "empresa",
            "documento",
            "referencia",
            "versao",
            "recebido_em",
            "link",
        ],
    ).assign(
        referencia=lambda d: pd.to_datetime(d["referencia"]),
        recebido_em=lambda d: pd.to_datetime(d["recebido_em"]),
    )


def _cadastro() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cnpj": ["11.111.111/0001-11"],
            "registro": pd.to_datetime(["2000-01-01"]),
            "cancelamento": pd.to_datetime([None]),
        }
    )


# --- do pacote ao texto --------------------------------------------------------------------------
def test_pdf_do_pacote_acha_o_pdf_e_recusa_pacote_sem_ele():
    documento = pdf("Nota 12 Empréstimos")
    assert pdf_do_pacote(_pacote(documento)) == documento
    with pytest.raises(FormatoNaoLido, match="PDF"):
        pdf_do_pacote(_pacote(None))


def test_pdf_que_nao_e_pdf_e_recusado():
    with pytest.raises(FormatoNaoLido, match="PDF"):
        pdf_do_pacote(_pacote(b"<html>Limite de downloads</html>"))


def test_paginas_do_pdf_uma_por_pagina_e_pagina_em_branco_fica_vazia():
    paginas = paginas_do_pdf(pdf("Nota 1 Contexto", "", "Nota 3 Caixa"))
    assert len(paginas) == 3
    assert "Contexto" in paginas[0] and paginas[1] == "" and "Caixa" in paginas[2]


def test_empacotar_e_desempacotar_dao_as_mesmas_paginas():
    paginas = ["Nota 1", "", "Ação — R$ 1.234"]
    assert desempacotar(empacotar(paginas)) == paginas
    assert empacotar(paginas) == empacotar(paginas)  # o mesmo texto, o mesmo original


# --- acervo --------------------------------------------------------------------------------------
def test_guarda_o_texto_no_acervo_restrito_e_registra_a_coleta(banco):
    with banco.begin() as c:
        paginas = guardar_notas(c, LINK, _pacote(pdf("Nota 12 Empréstimos")), AGORA)
        assert ja_guardadas(c) == {LINK}
    assert len(paginas) == 1
    with banco.connect() as c:
        linha = c.execute(sa.select(coletas)).one()
    assert (linha.fonte, linha.situacao) == (FONTE, "ok")
    assert linha.caminho_do_original.startswith("restrito/cvm-enet-notas/")
    assert linha.caminho_do_original.endswith(".json.gz")
    assert desempacotar(acervo.ler_original(linha.caminho_do_original)) == paginas


def test_nao_guarda_o_que_nao_e_pdf_e_a_fonte_nao_conta_como_guardada(banco):
    with pytest.raises(FormatoNaoLido), banco.begin() as c:
        guardar_notas(c, LINK, _pacote(None), AGORA)
    with banco.connect() as c:
        assert ja_guardadas(c) == set()


def test_pdf_so_de_imagem_guarda_paginas_vazias_sem_inventar_texto(banco):
    with banco.begin() as c:
        paginas = guardar_notas(c, LINK, _pacote(pdf("", "")), AGORA)
    assert paginas == ["", ""]


# --- a tabela ------------------------------------------------------------------------------------
def test_tabela_tem_uma_linha_por_pagina_com_texto_e_a_data_da_entrega():
    indice = _indice(
        ("11.111.111/0001-11", "Cia A", "DFP", "2025-12-31", 1, "2026-03-10", LINK)
    )
    tabela = montar_tabela(
        indice, {LINK: ["Nota 1", "", "Nota 3"]}, cadastro=_cadastro()
    )
    assert list(tabela.columns) == list(COLUNAS)
    assert tabela["pagina"].tolist() == [1, 3]  # página em branco não vira linha
    assert tabela["texto"].tolist() == ["Nota 1", "Nota 3"]
    assert set(tabela["disponivel_em"]) == {date(2026, 3, 10)}
    assert set(tabela["referencia"]) == {date(2025, 12, 31)}


def test_so_entra_dfp_cujo_texto_esta_no_acervo_e_itr_fica_de_fora():
    indice = _indice(
        ("11.111.111/0001-11", "Cia A", "DFP", "2025-12-31", 1, "2026-03-10", LINK),
        ("11.111.111/0001-11", "Cia A", "DFP", "2025-12-31", 2, "2026-04-02", OUTRO),
        ("11.111.111/0001-11", "Cia A", "ITR", "2026-03-31", 1, "2026-05-10", "itr"),
    )
    tabela = montar_tabela(
        indice, {LINK: ["Nota 1"], "itr": ["Nota X"]}, cadastro=_cadastro()
    )
    assert tabela["versao"].tolist() == [
        1
    ]  # a versão 2 ainda não foi baixada: sem linha


def test_cada_versao_vale_a_partir_da_propria_entrega():
    indice = _indice(
        ("11.111.111/0001-11", "Cia A", "DFP", "2025-12-31", 1, "2026-03-10", LINK),
        ("11.111.111/0001-11", "Cia A", "DFP", "2025-12-31", 2, "2026-04-02", OUTRO),
    )
    tabela = montar_tabela(
        indice,
        {LINK: ["Nota 1 antiga"], OUTRO: ["Nota 1 corrigida"]},
        cadastro=_cadastro(),
    )
    em_marco = entregues_ate(tabela, date(2026, 3, 31))
    assert em_marco["texto"].tolist() == ["Nota 1 antiga"]
    assert len(entregues_ate(tabela, date(2026, 4, 2))) == 2


def test_sem_olhar_o_futuro_cortar_o_futuro_nao_muda_o_passado():
    indice = _indice(
        ("11.111.111/0001-11", "Cia A", "DFP", "2025-12-31", 1, "2026-03-10", LINK),
        ("11.111.111/0001-11", "Cia A", "DFP", "2025-12-31", 2, "2026-04-02", OUTRO),
    )
    textos = {LINK: ["a"], OUTRO: ["b"]}
    inteira = montar_tabela(indice, textos, cadastro=_cadastro())
    cortada = montar_tabela(
        indice[indice["recebido_em"] <= "2026-03-31"], textos, cadastro=_cadastro()
    )
    corte = date(2026, 3, 31)
    pd.testing.assert_frame_equal(
        entregues_ate(inteira, corte), entregues_ate(cortada, corte)
    )


def test_empresa_entregue_antes_do_registro_vale_so_a_partir_do_registro():
    cadastro = _cadastro().assign(registro=pd.to_datetime(["2026-06-01"]))
    indice = _indice(
        ("11.111.111/0001-11", "Cia A", "DFP", "2025-12-31", 1, "2026-03-10", LINK)
    )
    tabela = montar_tabela(indice, {LINK: ["Nota 1"]}, cadastro=cadastro)
    assert tabela["disponivel_em"].iloc[0] == date(2026, 6, 1)


def test_sem_nenhum_texto_a_tabela_vem_vazia_com_as_colunas():
    tabela = montar_tabela(_indice(), {}, cadastro=_cadastro())
    assert tabela.empty and list(tabela.columns) == list(COLUNAS)
