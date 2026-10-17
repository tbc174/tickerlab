"""Ratings pelos documentos da CVM: quais documentos do IPE trazem rating e quando ficaram públicos."""

import io
import zipfile
from datetime import date

from base import ratings

CABECALHO = (
    "CNPJ_Companhia;Nome_Companhia;Codigo_CVM;Data_Referencia;Categoria;Tipo;Especie;Assunto;"
    "Data_Entrega;Tipo_Apresentacao;Protocolo_Entrega;Versao;Link_Download"
)
RAD = "https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?Tela=ext&descTipo=IPE"


def _linha(
    categoria,
    tipo,
    assunto,
    entrega="2024-03-05",
    protocolo="1001",
    versao="1",
    referencia=None,
    link=None,
):
    link = link or f"{RAD}&numProtocolo={protocolo}&numVersao={versao}"
    return (
        f"11.111.111/0001-11;EMPRESA SA;9999;{referencia or entrega};{categoria};{tipo};;"
        f"{assunto};{entrega};AP;{protocolo};{versao};{link}"
    )


def _zip(*linhas: str) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        texto = "\n".join([CABECALHO, *linhas])
        z.writestr("ipe_cia_aberta_2024.csv", texto.encode("cp1252"))
    return saida.getvalue()


RELATORIO = ("Dados Econômico-Financeiros", "Relatório de Agência de Rating")
COMUNICADO = (
    "Comunicado ao Mercado",
    "Outros Comunicados Não Considerados Fatos Relevantes",
)


def test_escolhe_relatorios_de_agencia_e_assuntos_com_rating():
    tabela = ratings.ler_documentos_do_ipe(
        _zip(
            _linha(*RELATORIO, "Relatorio de Credito - Moodys", protocolo="1"),
            _linha(*COMUNICADO, "Reafirmação de Rating", protocolo="2"),
            _linha(
                "Assembleia", "AGDEB", "Edital - classificação de risco", protocolo="3"
            ),
            _linha(*COMUNICADO, "Fitch eleva nota da Companhia", protocolo="4"),
            _linha(*COMUNICADO, "Pagamento de dividendos", protocolo="5"),
            _linha(
                "Dados Econômico-Financeiros",
                "Relatório de Agente Fiduciário",
                "Relatório anual",
                protocolo="6",
            ),
        )
    )
    assert sorted(tabela["protocolo"]) == ["1", "2", "3", "4"]
    evidencia = dict(zip(tabela["protocolo"], tabela["evidencia"], strict=True))
    assert evidencia["1"] == "relatorio_de_agencia"
    assert evidencia["2"] == "assunto"


def test_relatorio_de_agencia_entra_mesmo_sem_rating_no_assunto():
    tabela = ratings.ler_documentos_do_ipe(_zip(_linha(*RELATORIO, "", protocolo="7")))
    assert list(tabela["protocolo"]) == ["7"]


def test_data_publica_e_a_entrega_nunca_a_referencia():
    tabela = ratings.ler_documentos_do_ipe(
        _zip(
            _linha(*RELATORIO, "Fitch", entrega="2021-04-30", referencia="2021-04-28"),
            _linha(
                *RELATORIO,
                "S&P",
                protocolo="2002",
                entrega="2019-06-10",
                referencia="2019-08-01",  # referência depois da entrega: erro de preenchimento
            ),
        )
    )
    publico = dict(zip(tabela["protocolo"], tabela["publico_em"], strict=True))
    assert publico == {"1001": date(2021, 4, 30), "2002": date(2019, 6, 10)}


def test_cada_versao_e_um_documento_com_a_sua_data():
    tabela = ratings.ler_documentos_do_ipe(
        _zip(
            _linha(*RELATORIO, "Fitch", entrega="2023-07-07", versao="1"),
            _linha(*RELATORIO, "Fitch", entrega="2023-07-20", versao="2"),
        )
    )
    tabela = tabela.sort_values("versao")
    assert list(tabela["versao"]) == [1, 2]
    assert list(tabela["publico_em"]) == [date(2023, 7, 7), date(2023, 7, 20)]
    assert tabela["link"].is_unique


def test_link_fora_da_cvm_ou_sem_data_fica_de_fora():
    tabela = ratings.ler_documentos_do_ipe(
        _zip(
            _linha(*RELATORIO, "Fitch", protocolo="1", link="https://outro.site/x.pdf"),
            _linha(*RELATORIO, "Fitch", protocolo="2", entrega=""),
            _linha(
                *RELATORIO,
                "Fitch",
                protocolo="3",
                link="http://www.rad.cvm.gov.br/x?n=3",
            ),
        )
    )
    assert list(tabela["protocolo"]) == ["3"]
    assert tabela["link"].iloc[0].startswith("https://")


def test_protocolo_vazio_dos_anos_antigos_usa_o_link():
    tabela = ratings.ler_documentos_do_ipe(
        _zip(_linha(*RELATORIO, "Fitch", protocolo="", link=f"{RAD}&antigo=1"))
    )
    assert tabela["protocolo"].iloc[0] == f"{RAD}&antigo=1"
