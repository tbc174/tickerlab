"""Leitor do XML do ENET da CVM (série 1 da base de ML, PR 5): as contas de cada versão de DFP e
ITR, como os dados abertos as mostram, sem guardar o PDF embutido nem os dados de quem entregou.
Os XMLs daqui são pequenos e montados no formato real (conferido em 13/10/2026 com o DFP 2022 v1
e o DFP 2024 v2 do BRB e o ITR 1T26 do Banco do Brasil)."""

import base64

import pandas as pd
import pytest

from base.contas_cvm import COLUNAS
from base.enet import DocumentoEnet, ler_xml_enet, limpar_xml
from base.regras import r5_reapresentado

PDF_FALSO = base64.b64encode(b"%PDF-1.7 " + b"x" * 5000).decode()
NOME_DE_QUEM_ENTREGOU = "Fulana de Tal"
EMAIL_DE_QUEM_ENTREGOU = "fulana@empresa.com.br"


def _conta(codigo, descricao, colunas, fixa=True):
    valores = "".join(f"<{nome}>{valor}</{nome}>" for nome, valor in colunas.items())
    return (
        f"<Conta><ContaFixa>{fixa}</ContaFixa><CodigoConta>{codigo}</CodigoConta>"
        f"<DescricaoConta>{descricao}</DescricaoConta>{valores}</Conta>"
    )


def _dfp_conta(codigo, descricao, ultimo, penultimo="", antepenultimo="0"):
    return _conta(
        codigo,
        descricao,
        {
            "UltimoExercicio": ultimo,
            "PenultimoExercicio": penultimo,
            "AntepenultimoExercicio": antepenultimo,
        },
    )


def _documento(versao, motivo, tipo):
    return (
        "<Documento>"
        f"<MotivoReapresentacao>{motivo}</MotivoReapresentacao><NumeroExigencia />"
        "<ResponsavelDocumento><DddResponsavel>61</DddResponsavel>"
        f"<EmailResponsavel>{EMAIL_DE_QUEM_ENTREGOU}</EmailResponsavel>"
        f"<NomeResponsavel>{NOME_DE_QUEM_ENTREGOU}</NomeResponsavel>"
        "<TelefoneResponsavel>33330000</TelefoneResponsavel></ResponsavelDocumento>"
        f"<TipoApresentacao>1</TipoApresentacao><TipoDocumento>{tipo}</TipoDocumento>"
        f"<VersaoDocumento>{versao}</VersaoDocumento></Documento>"
    )


def _anexo(raiz, dados):
    return (
        f"<AnexosDocumento><{raiz}{dados}AnexoDocumento>"
        f"<ImagemObjetoArquivoPdf>{PDF_FALSO}</ImagemObjetoArquivoPdf>"
        f"<NomeArquivoPdf>RA 4T22.pdf</NomeArquivoPdf></{raiz}{dados}AnexoDocumento>"
        "</AnexosDocumento>"
    )


EMPRESA = (
    "<DadosEmpresa><CnpjEmpresa>00000208000100</CnpjEmpresa><CodigoCvm>014206</CodigoCvm>"
    "<RazaoSocialEmpresa>BRB BCO DE BRASILIA S.A.</RazaoSocialEmpresa>"
    "<TipoEmpresa>2</TipoEmpresa></DadosEmpresa>"
)


def _dfp(versao=1, motivo="", escala="2", lucro="512.345", consolidado_ultimo=""):
    individuais = (
        "<DfIndividuais><BalancoPatrimonialAtivo>"
        + _dfp_conta("1", "Ativo Total", "40.090.803", "30.312.337")
        + _dfp_conta("1.01", "Ativo Circulante", "10.000", "9.000")
        + "</BalancoPatrimonialAtivo><BalancoPatrimonialPassivo>"
        + _dfp_conta("2", "Passivo Total", "40.090.803", "30.312.337")
        + "</BalancoPatrimonialPassivo><DemonstracaoResultado>"
        + _dfp_conta(
            "3.01", "Receitas de Intermediação Financeira", "5.528.457", "2.968.650"
        )
        + _dfp_conta("3.11", "Lucro/Prejuízo do Período", lucro, "-1.234")
        + "</DemonstracaoResultado><DemonstracaoValorAdicionado>"
        + _dfp_conta("7.01", "Receitas", "5.081.911", "2.473.503")
        + "</DemonstracaoValorAdicionado></DfIndividuais>"
    )
    consolidadas = (
        "<DfConsolidadas><BalancoPatrimonialAtivo>"
        + _dfp_conta("1", "Ativo Total", consolidado_ultimo, "31751760,0000000000")
        + "</BalancoPatrimonialAtivo><DemonstracaoMutacoesPatrimonioLiquido><DMPL>"
        + "<Contas>"
        + _conta("5.01", "Saldos Iniciais", {"PatrimonioLiquido": "2.364.833"})
        + "</Contas></DMPL></DemonstracaoMutacoesPatrimonioLiquido></DfConsolidadas>"
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\r\n<XmlDemonstracoesFinanceiras>'
        + EMPRESA
        + "<DadosDFP>"
        + _anexo("XmlDemonstracoesFinanceiras", "DadosDFP")
        + "<DataReferencia>31/12/2022</DataReferencia>"
        # o ENET informa o começo do ano como 01/12 (dia errado na fonte): não é usado
        + "<DtFimPenultimoExercicioSocial>31/12/2021</DtFimPenultimoExercicioSocial>"
        + "<DtFimUltimoExercicioSocial>31/12/2022</DtFimUltimoExercicioSocial>"
        + "<DtInicioPenultimoExercicioSocial>01/12/2021</DtInicioPenultimoExercicioSocial>"
        + "<DtInicioUltimoExercicioSocial>01/12/2022</DtInicioUltimoExercicioSocial>"
        + f"<EscalaMoeda>{escala}</EscalaMoeda><EscalaQtdAcoes>2</EscalaQtdAcoes>"
        + "<Formulario>"
        + individuais
        + consolidadas
        + "</Formulario><Moeda>1</Moeda></DadosDFP>"
        + _documento(versao, motivo, 4)
        + "</XmlDemonstracoesFinanceiras>"
    ).encode("utf-8")


def _itr_conta_do_balanco(codigo, descricao, atual, anterior):
    return _conta(
        codigo, descricao, {"ExercicioAnterior": anterior, "TrimestreAtual": atual}
    )


def _itr_conta_do_resultado(codigo, descricao, trimestre, acumulado, tri_ant, acum_ant):
    return _conta(
        codigo,
        descricao,
        {
            "AcumuladoExercicioAnterior": acum_ant,
            "AcumuladoExercicioAtual": acumulado,
            "TrimestreAnterior": tri_ant,
            "TrimestreAtual": trimestre,
        },
    )


def _itr():
    formulario = (
        "<Formulario><DfConsolidadas><BalancoPatrimonialAtivo>"
        + _itr_conta_do_balanco("1", "Ativo Total", "2563995608", "2414775306")
        + "</BalancoPatrimonialAtivo><DemonstracaoResultado>"
        + _itr_conta_do_resultado("3.01", "Receitas", "400", "1000", "300", "800")
        + "</DemonstracaoResultado></DfConsolidadas></Formulario>"
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\r\n<XmlInformacoesTrimestraisFinanceiras>'
        "<DadosEmpresa><CnpjEmpresa>00000000000191</CnpjEmpresa>"
        "<RazaoSocialEmpresa>BCO BRASIL S.A.</RazaoSocialEmpresa></DadosEmpresa>"
        "<DadosITR>"
        + _anexo("XmlInformacoesTrimestraisFinanceiras", "DadosITR")
        + "<DataReferencia>30/06/2026</DataReferencia>"
        "<DtFimExercicioSocialAnterior>31/12/2025</DtFimExercicioSocialAnterior>"
        "<DtFimTrimestreAtual>30/06/2026</DtFimTrimestreAtual>"
        "<DtInicioExercicioSocialCurso>01/01/2026</DtInicioExercicioSocialCurso>"
        "<DtInicioTrimestreAtual>01/04/2026</DtInicioTrimestreAtual>"
        "<EscalaMoeda>1</EscalaMoeda>"
        + formulario
        + "</DadosITR>"
        + _documento(1, "", 3)
        + "</XmlInformacoesTrimestraisFinanceiras>"
    ).encode("utf-8")


def _valor(contas, grupo, conta, ordem="ultimo", inicio=None):
    linhas = contas[
        (contas["grupo"] == grupo)
        & (contas["conta"] == conta)
        & (contas["ordem"] == ordem)
    ]
    if inicio is not None:
        linhas = linhas[linhas["inicio"] == pd.Timestamp(inicio)]
    assert len(linhas) == 1, linhas
    return linhas["valor"].iloc[0]


# --- leitura ----------------------------------------------------------------------------------------
def test_le_versao_motivo_e_empresa():
    documento = ler_xml_enet(_dfp(versao=2, motivo="Ajuste do quadro DRE."))
    assert isinstance(documento, DocumentoEnet)
    assert (documento.cnpj, documento.documento, documento.versao) == (
        "00.000.208/0001-00",
        "DFP",
        2,
    )
    assert documento.referencia == pd.Timestamp("2022-12-31")
    assert documento.motivo == "Ajuste do quadro DRE."
    assert documento.empresa == "BRB BCO DE BRASILIA S.A."


def test_le_contas_individuais_e_consolidadas_no_formato_dos_dados_abertos():
    contas = ler_xml_enet(_dfp()).contas
    assert list(contas.columns) == list(COLUNAS)
    assert set(contas["grupo"]) == {"ind", "con"}
    assert set(contas["demonstracao"]) == {
        "BPA",
        "BPP",
        "DRE",
    }  # DVA e DMPL ficam de fora
    assert set(contas["ordem"]) == {"ultimo", "penultimo"}
    assert set(contas["versao"]) == {1} and set(contas["documento"]) == {"DFP"}


def test_escala_mil_e_os_dois_formatos_de_numero():
    contas = ler_xml_enet(_dfp()).contas
    assert _valor(contas, "ind", "1") == 40_090_803_000
    assert _valor(contas, "con", "1", "penultimo") == 31_751_760_000
    assert _valor(contas, "ind", "3.11", "penultimo") == -1_234_000


def test_escala_unidade_e_escala_desconhecida():
    assert _valor(ler_xml_enet(_dfp(escala="1")).contas, "ind", "1") == 40_090_803
    with pytest.raises(ValueError, match="escala"):
        ler_xml_enet(_dfp(escala="9"))


def test_valor_em_branco_fica_vazio():
    contas = ler_xml_enet(_dfp()).contas
    assert pd.isna(_valor(contas, "con", "1"))


def test_datas_dos_periodos_como_nos_dados_abertos():
    contas = ler_xml_enet(_dfp()).contas
    dre = contas[(contas["demonstracao"] == "DRE") & (contas["ordem"] == "ultimo")]
    assert set(dre["inicio"]) == {pd.Timestamp("2022-01-01")}  # não o 01/12 do ENET
    assert set(dre["fim"]) == {pd.Timestamp("2022-12-31")}
    balanco = contas[contas["demonstracao"] == "BPA"]
    assert balanco["inicio"].isna().all()  # saldo numa data: sem início, como no CSV
    assert set(balanco.loc[balanco["ordem"] == "penultimo", "fim"]) == {
        pd.Timestamp("2021-12-31")
    }


def test_itr_traz_o_trimestre_e_o_acumulado():
    documento = ler_xml_enet(_itr())
    contas = documento.contas
    assert (documento.documento, documento.cnpj) == ("ITR", "00.000.000/0001-91")
    assert _valor(contas, "con", "3.01", inicio="2026-04-01") == 400  # o trimestre
    assert (
        _valor(contas, "con", "3.01", inicio="2026-01-01") == 1000
    )  # o acumulado do ano
    assert _valor(contas, "con", "3.01", "penultimo", inicio="2025-01-01") == 800
    assert _valor(contas, "con", "3.01", "penultimo", inicio="2025-04-01") == 300
    assert _valor(contas, "con", "1", "penultimo") == 2414775306
    balanco = contas[contas["demonstracao"] == "BPA"]
    assert set(balanco["fim"]) == {
        pd.Timestamp("2026-06-30"),
        pd.Timestamp("2025-12-31"),
    }


def test_r5_compara_a_versao_1_com_a_2():
    v1 = ler_xml_enet(_dfp(versao=1, lucro="512.345"))
    v2 = ler_xml_enet(
        _dfp(versao=2, lucro="12.345", motivo="Despesa digitada em duplicidade.")
    )
    achados = r5_reapresentado(v1.contas, v2.contas, v2.motivo, None)
    assert [(a.regra, a.grupo, a.conta) for a in achados] == [("R5", "ind", "3.11")]
    assert "Despesa digitada em duplicidade." in achados[0].porque


# --- limpeza ------------------------------------------------------------------------------------------
def test_limpar_tira_o_pdf_e_os_dados_de_quem_entregou_sem_mudar_as_contas():
    original = _dfp(versao=2, motivo="Ajuste.")
    limpo = limpar_xml(original)
    assert PDF_FALSO.encode() not in limpo
    assert NOME_DE_QUEM_ENTREGOU.encode() not in limpo
    assert EMAIL_DE_QUEM_ENTREGOU.encode() not in limpo
    assert len(limpo) < len(original) / 2
    antes, depois = ler_xml_enet(original), ler_xml_enet(limpo)
    pd.testing.assert_frame_equal(antes.contas, depois.contas)
    assert (depois.versao, depois.motivo) == (2, "Ajuste.")


def test_limpar_duas_vezes_da_o_mesmo_resultado():
    limpo = limpar_xml(_itr())
    assert limpar_xml(limpo) == limpo


def test_cnpj_alfanumerico_atravessa_enet():
    xml = _dfp().replace(b"00000208000100", b"12ABC34501DE35")
    assert ler_xml_enet(xml).cnpj == "12.ABC.345/01DE-35"
