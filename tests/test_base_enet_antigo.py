"""Leitor dos pacotes antigos do ENET (o `.dfp` com `InfoFinaDFin.xml`) e a escolha do leitor pelo
que o pacote contém, não pelo ano. Os XMLs de `tests/arquivos/enet_antigo/` são mínimos e
sintéticos, no desenho real conferido em 20/10/2026. Sem internet."""

import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from base.enet_antigo import (
    ARQUIVOS_GUARDADOS,
    FormatoNaoLido,
    eh_pacote_enxuto,
    enxugar,
    ler_dfp_antigo,
    tem_dfp_antigo,
)
from base.enet_coleta import (
    ler_documento_guardado,
    original_do_pacote,
    xml_do_pacote,
)
from tests.test_base_enet import _dfp
from tests.test_base_enet_coleta import _pacote

PASTA = Path(__file__).parent / "arquivos" / "enet_antigo"


def _dfp_interno(
    sem: str | None = None, troca: dict[str, bytes] | None = None
) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        for nome in (*ARQUIVOS_GUARDADOS, "ResponsavelEsclarecimentoDuvidas.xml"):
            if nome == sem:
                continue
            fonte = PASTA / nome
            conteudo = (troca or {}).get(nome) or (
                fonte.read_bytes()
                if fonte.exists()
                else b"<Responsavel>Fulana de Tal fulana@empresa.com.br</Responsavel>"
            )
            z.writestr(nome, conteudo)
    return saida.getvalue()


def _pacote_antigo(interno: bytes | None = None, nome: str = "124061.dfp") -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(nome, interno if interno is not None else _dfp_interno())
        z.writestr("124061_014206_15032015.pdf", b"%PDF-1.4 " + b"x" * 5000)
    return saida.getvalue()


def test_pacote_antigo_da_os_totais_que_o_xml_mostra():
    documento = ler_dfp_antigo(enxugar(_pacote_antigo()))
    assert (documento.documento, documento.versao) == ("DFP", 2)
    assert documento.cnpj == "08.493.364/0001-62"
    assert documento.motivo == "Alterar o DFC"
    assert documento.referencia == pd.Timestamp("2015-03-31")
    contas = documento.contas
    ativo = contas[(contas["conta"] == "2") | (contas["demonstracao"] == "BPA")]
    por_ordem = ativo.set_index("ordem")["valor"]
    assert por_ordem["ultimo"] == 85832.5 * 1000  # escala 2 = mil, ponto decimal real
    assert por_ordem["penultimo"] == 70000.0 * 1000
    assert set(contas["demonstracao"]) == {"BPA", "BPP", "DRE"}  # a DMPL fica de fora
    assert documento.dmpl.empty


def test_datas_dos_exercicios_vem_do_arquivo_de_periodos():
    contas = ler_dfp_antigo(enxugar(_pacote_antigo())).contas
    balanco = contas[contas["demonstracao"] == "BPA"].set_index("ordem")
    assert balanco.loc["ultimo", "fim"] == pd.Timestamp("2015-03-31")
    assert balanco.loc["penultimo", "fim"] == pd.Timestamp("2014-03-31")
    assert pd.isna(balanco.loc["ultimo", "inicio"])
    dre = contas[contas["demonstracao"] == "DRE"].set_index("ordem")
    assert dre.loc["ultimo", "inicio"] == pd.Timestamp("2014-04-01")
    assert dre.loc["penultimo", "valor"] == 0  # zero fica, como no formato novo


def test_sem_olhar_o_futuro_nenhuma_data_passa_da_referencia():
    documento = ler_dfp_antigo(enxugar(_pacote_antigo()))
    assert documento.contas["fim"].max() <= documento.referencia


def test_periodos_que_nao_batem_com_a_data_do_documento_sao_recusados():
    periodos = (PASTA / "PeriodoDemonstracaoFinanceira.xml").read_bytes()
    trocado = periodos.replace(b"2015-03-31", b"2015-06-30")
    pacote = _pacote_antigo(_dfp_interno(troca={ARQUIVOS_GUARDADOS[1]: trocado}))
    with pytest.raises(FormatoNaoLido, match="períodos"):
        ler_dfp_antigo(enxugar(pacote))


def test_enxugar_tira_o_pdf_e_os_dados_de_quem_entregou_e_e_deterministico():
    pacote = _pacote_antigo()
    enxuto = enxugar(pacote)
    assert enxuto == enxugar(pacote)
    with zipfile.ZipFile(io.BytesIO(enxuto)) as z:
        assert sorted(z.namelist()) == sorted(ARQUIVOS_GUARDADOS)
    assert b"Fulana" not in enxuto and b"%PDF" not in enxuto
    assert len(enxuto) < len(pacote)


def test_dfp_sem_um_dos_xmls_e_formato_nao_lido():
    pacote = _pacote_antigo(_dfp_interno(sem="InfoFinaDFin.xml"))
    with pytest.raises(FormatoNaoLido, match="InfoFinaDFin.xml"):
        enxugar(pacote)


def test_reconhece_o_formato_pelo_conteudo_e_nao_pelo_ano():
    assert tem_dfp_antigo(_pacote_antigo())
    assert not tem_dfp_antigo(_pacote(_dfp()))
    conteudo, extensao = original_do_pacote(_pacote_antigo())
    assert extensao == ".zip" and eh_pacote_enxuto(conteudo)


def test_pacote_novo_continua_igual():
    xml = _dfp()
    conteudo, extensao = original_do_pacote(_pacote(xml))
    assert extensao == ".xml"
    assert not eh_pacote_enxuto(conteudo)
    assert ler_documento_guardado(conteudo).versao == ler_documento_guardado(xml).versao
    assert xml_do_pacote(_pacote(xml)) == xml


def test_formato_desconhecido_da_erro_claro_e_continua_sendo_value_error():
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("coisa.txt", b"?")
    with pytest.raises(FormatoNaoLido, match="coisa.txt") as erro:
        original_do_pacote(saida.getvalue())
    assert isinstance(erro.value, ValueError)
    with pytest.raises(ValueError, match="não tem o XML do documento"):
        xml_do_pacote(saida.getvalue())


def test_itr_antigo_tem_mensagem_propria():
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("555.itr", b"zip")
    with pytest.raises(FormatoNaoLido, match=r"\.itr"):
        original_do_pacote(saida.getvalue())
