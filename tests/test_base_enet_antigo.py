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
    ler_documento_antigo,
    tem_dfp_antigo,
    tem_itr_antigo,
)
from base.enet_coleta import (
    ler_documento_guardado,
    original_do_pacote,
    xml_do_pacote,
)
from tests.test_base_enet import _dfp
from tests.test_base_enet_coleta import _pacote

PASTA = Path(__file__).parent / "arquivos" / "enet_antigo"
PASTA_ITR = Path(__file__).parent / "arquivos" / "enet_antigo_itr"


def _dfp_interno(
    sem: str | None = None,
    troca: dict[str, bytes] | None = None,
    pasta: Path = PASTA,
) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        for nome in (*ARQUIVOS_GUARDADOS, "ResponsavelEsclarecimentoDuvidas.xml"):
            if nome == sem:
                continue
            fonte = pasta / nome
            conteudo = (troca or {}).get(nome) or (
                fonte.read_bytes()
                if fonte.exists()
                else b"<Responsavel>Fulana de Tal fulana@empresa.com.br</Responsavel>"
            )
            z.writestr(nome, conteudo)
    return saida.getvalue()


def _pacote_itr(troca: dict[str, bytes] | None = None) -> bytes:
    return _pacote_antigo(_dfp_interno(troca=troca, pasta=PASTA_ITR), "124062.itr")


def _pacote_antigo(interno: bytes | None = None, nome: str = "124061.dfp") -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(nome, interno if interno is not None else _dfp_interno())
        z.writestr("124061_014206_15032015.pdf", b"%PDF-1.4 " + b"x" * 5000)
    return saida.getvalue()


def test_pacote_antigo_da_os_totais_que_o_xml_mostra():
    documento = ler_documento_antigo(enxugar(_pacote_antigo()))
    assert (documento.documento, documento.versao) == ("DFP", 2)
    assert documento.cnpj == "08.493.364/0001-62"
    assert documento.motivo == "Alterar o DFC"
    assert documento.referencia == pd.Timestamp("2015-03-31")
    contas = documento.contas
    ativo = contas[(contas["conta"] == "2") | (contas["demonstracao"] == "BPA")]
    por_ordem = ativo.set_index("ordem")["valor"]
    assert por_ordem["ultimo"] == 85832.5 * 1000  # escala 2 = mil, ponto decimal real
    assert por_ordem["penultimo"] == 70000.0 * 1000
    assert set(contas["demonstracao"]) == {"BPA", "BPP", "DRE"}  # a DMPL vai à parte
    assert not documento.dmpl.empty


def test_datas_dos_exercicios_vem_do_arquivo_de_periodos():
    contas = ler_documento_antigo(enxugar(_pacote_antigo())).contas
    balanco = contas[contas["demonstracao"] == "BPA"].set_index("ordem")
    assert balanco.loc["ultimo", "fim"] == pd.Timestamp("2015-03-31")
    assert balanco.loc["penultimo", "fim"] == pd.Timestamp("2014-03-31")
    assert pd.isna(balanco.loc["ultimo", "inicio"])
    dre = contas[contas["demonstracao"] == "DRE"].set_index("ordem")
    assert dre.loc["ultimo", "inicio"] == pd.Timestamp("2014-04-01")
    assert dre.loc["penultimo", "valor"] == 0  # zero fica, como no formato novo


def test_sem_olhar_o_futuro_nenhuma_data_passa_da_referencia():
    documento = ler_documento_antigo(enxugar(_pacote_antigo()))
    assert documento.contas["fim"].max() <= documento.referencia


def test_periodos_que_nao_batem_com_a_data_do_documento_sao_recusados():
    periodos = (PASTA / "PeriodoDemonstracaoFinanceira.xml").read_bytes()
    trocado = periodos.replace(b"2015-03-31", b"2015-06-30")
    pacote = _pacote_antigo(_dfp_interno(troca={ARQUIVOS_GUARDADOS[1]: trocado}))
    with pytest.raises(FormatoNaoLido, match="períodos"):
        ler_documento_antigo(enxugar(pacote))


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


def _texto_itr(nome: str) -> str:
    return (PASTA_ITR / nome).read_text(encoding="utf8")


def test_dmpl_do_dfp_antigo_ganha_o_nome_das_colunas_pela_posicao():
    dmpl = ler_documento_antigo(enxugar(_pacote_antigo())).dmpl
    ind = dmpl[dmpl["grupo"] == "ind"]
    ultimo = ind[ind["ordem"] == "ultimo"].set_index("coluna")["valor"]
    assert ultimo["capital_social"] == 203364 * 1000
    assert ultimo["reservas_de_lucro"] == 4164 * 1000
    assert ultimo["lucros_acumulados"] == -81818 * 1000
    assert ultimo["patrimonio_liquido"] == 119919 * 1000
    assert (
        "patrimonio_liquido_consolidado" not in ultimo
    )  # o individual tem seis colunas
    assert set(ind["fim"]) == {pd.Timestamp("2015-03-31"), pd.Timestamp("2014-03-31")}
    assert set(ind["inicio"]) == {
        pd.Timestamp("2014-04-01"),
        pd.Timestamp("2013-04-01"),
    }
    assert (dmpl["demonstracao"] == "DMPL").all()


def test_dmpl_consolidada_traz_as_oito_colunas():
    dmpl = ler_documento_antigo(enxugar(_pacote_antigo())).dmpl
    con = dmpl[dmpl["grupo"] == "con"].set_index("coluna")["valor"]
    assert con["reservas_de_capital"] == 4164 * 1000
    assert con["nao_controladores"] == 10 * 1000
    assert con["patrimonio_liquido_consolidado"] == 119929 * 1000
    assert len(con) == 8


def test_dmpl_sem_periodo_ou_do_antepenultimo_fica_de_fora():
    dmpl = ler_documento_antigo(enxugar(_pacote_antigo())).dmpl
    assert 7 * 1000 not in set(dmpl["valor"])  # o bloco de período 0
    assert 1 * 1000 not in set(dmpl["valor"])  # o de período 3 (antepenúltimo)


def test_itr_antigo_e_lido_e_marcado_como_itr():
    documento = ler_documento_antigo(enxugar(_pacote_itr()))
    assert (documento.documento, documento.versao) == ("ITR", 1)
    assert documento.cnpj == "00.070.698/0001-11"
    assert documento.referencia == pd.Timestamp("2016-06-30")


def test_itr_balanco_tem_o_trimestre_e_o_fim_do_ano_anterior():
    contas = ler_documento_antigo(enxugar(_pacote_itr())).contas
    ativo = contas[contas["demonstracao"] == "BPA"].set_index("ordem")
    assert ativo.loc["ultimo", "valor"] == 1000.5 * 1000
    assert ativo.loc["ultimo", "fim"] == pd.Timestamp("2016-06-30")
    assert ativo.loc["penultimo", "valor"] == 900 * 1000
    assert ativo.loc["penultimo", "fim"] == pd.Timestamp("2015-12-31")
    assert ativo["inicio"].isna().all()


def test_itr_resultado_separa_trimestre_e_acumulado_com_as_datas_certas():
    contas = ler_documento_antigo(enxugar(_pacote_itr())).contas
    receita = contas[(contas["demonstracao"] == "DRE") & (contas["conta"] == "3.01")]
    por_periodo = {
        (r.ordem, str(r.inicio.date()), str(r.fim.date())): r.valor
        for r in receita.itertuples()
    }
    assert por_periodo == {
        ("ultimo", "2016-04-01", "2016-06-30"): 300 * 1000,
        ("ultimo", "2016-01-01", "2016-06-30"): 700 * 1000,
        ("penultimo", "2015-04-01", "2015-06-30"): 250 * 1000,
        ("penultimo", "2015-01-01", "2015-06-30"): 650 * 1000,
    }


def test_itr_fluxo_de_caixa_so_tem_o_acumulado():
    contas = ler_documento_antigo(enxugar(_pacote_itr())).contas
    fluxo = contas[contas["demonstracao"] == "DFC_MD"]
    assert sorted(fluxo["valor"]) == [40 * 1000, 50 * 1000]  # sem linha de trimestre


def test_itr_sem_olhar_o_futuro_nenhuma_data_passa_da_referencia():
    documento = ler_documento_antigo(enxugar(_pacote_itr()))
    assert documento.contas["fim"].max() <= documento.referencia
    assert documento.dmpl["fim"].max() <= documento.referencia


def test_itr_dmpl_usa_o_periodo_do_bloco_e_as_posicoes_fixas():
    dmpl = ler_documento_antigo(enxugar(_pacote_itr())).dmpl
    ind = dmpl[dmpl["grupo"] == "ind"]
    atual = ind[ind["ordem"] == "ultimo"].set_index("coluna")["valor"]
    anterior = ind[ind["ordem"] == "penultimo"].set_index("coluna")["valor"]
    assert atual["patrimonio_liquido"] == 95 * 1000
    assert anterior["patrimonio_liquido"] == 75 * 1000
    assert set(ind["inicio"]) == {
        pd.Timestamp("2016-01-01"),
        pd.Timestamp("2015-01-01"),
    }
    con = dmpl[(dmpl["grupo"] == "con") & (dmpl["ordem"] == "ultimo")]
    assert con.set_index("coluna")["valor"]["patrimonio_liquido_consolidado"] == 115_000


def test_primeiro_trimestre_vale_a_coluna_que_a_empresa_preencheu():
    # no 1º trimestre o trimestre e o acumulado são o mesmo período; a empresa preenche um só
    datas = (
        _texto_itr("PeriodoDemonstracaoFinanceira.xml")
        .replace("2016-04-01", "2016-01-01")
        .replace("2016-06-30", "2016-03-31")
        .replace("2015-04-01", "2015-01-01")
        .replace("2015-06-30", "2015-03-31")
    )
    valores = (
        _texto_itr("InfoFinaDFin.xml")
        .replace("<ValorConta2>300</ValorConta2>", "<ValorConta2>0</ValorConta2>")
        .replace("<ValorConta2>-100</ValorConta2>", "<ValorConta2>0</ValorConta2>")
        .replace("<ValorConta5>250</ValorConta5>", "<ValorConta5>0</ValorConta5>")
    )
    pacote = _pacote_itr(
        {
            "Documento.xml": _texto_itr("Documento.xml")
            .replace("2016-06-30", "2016-03-31")
            .encode(),
            ARQUIVOS_GUARDADOS[1]: datas.encode(),
            ARQUIVOS_GUARDADOS[2]: valores.encode(),
        }
    )
    contas = ler_documento_antigo(enxugar(pacote)).contas
    receita = contas[(contas["demonstracao"] == "DRE") & (contas["conta"] == "3.01")]
    assert sorted(receita["valor"]) == [650 * 1000, 700 * 1000]


def test_dois_valores_diferentes_para_o_mesmo_periodo_sao_recusados():
    datas = _texto_itr("PeriodoDemonstracaoFinanceira.xml").replace(
        "2016-04-01", "2016-01-01"
    )  # o trimestre vira o acumulado, mas a empresa preencheu os dois
    pacote = _pacote_itr({ARQUIVOS_GUARDADOS[1]: datas.encode()})
    with pytest.raises(FormatoNaoLido, match="valores diferentes"):
        ler_documento_antigo(enxugar(pacote))


def test_documento_de_tipo_desconhecido_e_recusado():
    documento = _texto_itr("Documento.xml").replace(
        "<CodigoTipoDocumento>3<", "<CodigoTipoDocumento>9<"
    )
    pacote = _pacote_itr({"Documento.xml": documento.encode()})
    with pytest.raises(FormatoNaoLido, match="tipo de documento"):
        ler_documento_antigo(enxugar(pacote))


def test_pacote_com_itr_antigo_e_guardado_como_zip_enxuto():
    pacote = _pacote_itr()
    assert tem_itr_antigo(pacote) and not tem_dfp_antigo(pacote)
    conteudo, extensao = original_do_pacote(pacote)
    assert extensao == ".zip" and eh_pacote_enxuto(conteudo)
    assert ler_documento_guardado(conteudo).documento == "ITR"
