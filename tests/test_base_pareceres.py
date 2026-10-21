"""Parecer do auditor pelos CSVs do DFP e do ITR (série T, T2); sem internet.

Os trechos de texto são frases curtas dos relatórios reais da CVM (DFP e ITR de 2024), sem nome de pessoa.
"""

import io
import zipfile
from datetime import date

import pandas as pd

from base import pareceres
from base.pareceres import NAO, NAO_CLASSIFICADO, SIM

PADRAO = (
    "Opinião. Examinamos as demonstrações financeiras individuais e consolidadas da Companhia. "
    "Base para opinião. Conduzimos nossa auditoria de acordo com as normas brasileiras. "
    "Responsabilidades da administração e da governança pelas demonstrações financeiras. "
    "A administração é responsável por avaliar a capacidade de continuidade operacional. "
    "Nossos objetivos são obter segurança razoável de que as demonstrações financeiras estão livres de "
    "distorção relevante. Concluímos sobre a adequação do uso, pela administração, da base contábil de "
    "continuidade operacional e, com base nas evidências obtidas, se existe incerteza relevante em "
    "relação a eventos ou condições que possam levantar dúvida significativa. "
    "Principais assuntos de auditoria. Os principais assuntos de auditoria são aqueles que, em nosso "
    "julgamento profissional, foram os mais significativos. Valor recuperável dos ativos: a Companhia "
    "conduziu testes de impairment, com ênfase nas operações de níquel."
)
ENFASE = (
    " Ênfase - Reapresentação das demonstrações financeiras. Chamamos atenção à nota explicativa 2.5 "
    "às demonstrações financeiras, que foram alteradas e estão sendo reapresentadas. Nossa opinião não "
    "contém ressalva relacionada a esse assunto."
)
INCERTEZA = (
    " Incerteza relevante relacionada com a continuidade operacional. Chamamos a atenção para a Nota "
    "1.2 às demonstrações contábeis, que versa sobre a continuidade operacional em relação a um litígio."
)
SO_ATENCAO = (
    " Chamamos a atenção para a nota explicativa 7, sobre a venda de uma controlada."
)
ASSUNTO_PRINCIPAL = (
    " Continuidade operacional e os impactos da homologação do plano de recuperação judicial. "
    "Conforme mencionado na Nota Explicativa 1, a Companhia obteve a homologação do plano."
)
DECLARACAO = "Declaração dos diretores sobre as demonstrações financeiras. Revisamos e concordamos."


def _zip_do_dfp(
    linhas_parecer: list[dict], principal: list[dict], itr: bool = False
) -> bytes:
    sigla = "itr" if itr else "dfp"
    coluna = "TP_RELAT_ESP" if itr else "TP_RELAT_AUD"
    parecer = pd.DataFrame(linhas_parecer).rename(columns={"opiniao": coluna})
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as arquivo:
        arquivo.writestr(
            f"{sigla}_cia_aberta_parecer_2024.csv",
            parecer.to_csv(sep=";", index=False).encode("latin-1"),
        )
        arquivo.writestr(
            f"{sigla}_cia_aberta_2024.csv",
            pd.DataFrame(principal).to_csv(sep=";", index=False),
        )
    return memoria.getvalue()


def _item(cnpj: str, texto: str, item: int = 1, tipo: str = "Relatório do Auditor Independente",
          opiniao: str = "Sem Ressalva", versao: str = "1", referencia: str = "2024-12-31") -> dict:  # fmt: skip
    return {
        "CNPJ_CIA": cnpj, "DT_REFER": referencia, "VERSAO": versao, "DENOM_CIA": f"EMPRESA {cnpj[:2]}",
        "opiniao": opiniao, "TP_PARECER_DECL": tipo, "NUM_ITEM_PARECER_DECL": str(item),
        "TXT_PARECER_DECL": texto,
    }  # fmt: skip


def _entrega(cnpj: str, recebido: str, documento: str, versao: str = "1", referencia: str = "2024-12-31") -> dict:  # fmt: skip
    return {
        "CNPJ_CIA": cnpj, "DT_REFER": referencia, "VERSAO": versao, "ID_DOC": documento,
        "DT_RECEB": recebido,
    }  # fmt: skip


A, B, C, D = (
    "11.111.111/0001-11",
    "22.222.222/0001-22",
    "33.333.333/0001-33",
    "44.444.444/0001-44",
)


def _classe(texto: str) -> tuple[str, str]:
    return pareceres.classificar_texto(texto)


def test_texto_padrao_sem_titulo_nao_tem_enfase_nem_incerteza():
    # o texto padrão fala em "continuidade operacional", "incerteza relevante" e até "com ênfase nas
    # operações": nada disso é parecer com ênfase nem com incerteza
    assert _classe(PADRAO) == (NAO, NAO)


def test_titulo_de_enfase_e_de_incerteza_sao_achados():
    assert _classe(PADRAO + ENFASE) == (SIM, NAO)
    assert _classe(PADRAO + INCERTEZA) == (NAO, SIM)
    assert _classe(PADRAO + ENFASE + INCERTEZA) == (SIM, SIM)


def test_variantes_do_titulo_de_enfase():
    assert (
        _classe(PADRAO + " Ênfases Subvenção para investimento. Chamamos atenção.")[0]
        == SIM
    )
    assert _classe(PADRAO + " ÊNFASE Chamamos atenção à nota 3.")[0] == SIM
    assert _classe(PADRAO + " Enfase sem acento Chamamos atenção à nota 3.")[0] == SIM
    assert (
        _classe(PADRAO + " Incerteza relacionada com a continuidade operacional.")[1]
        == SIM
    )
    assert (
        _classe(
            PADRAO + " conforme incerteza relevante quanto à continuidade operacional."
        )[1]
        == SIM
    )


def test_o_que_nao_da_para_decidir_fica_nao_classificado():
    # "chamamos a atenção" sem título de ênfase; título "Continuidade operacional" que pode ser só
    # assunto principal de auditoria; relatório curto demais (anexo, aviso)
    assert _classe(PADRAO + SO_ATENCAO) == (NAO_CLASSIFICADO, NAO)
    assert _classe(PADRAO + ASSUNTO_PRINCIPAL) == (NAO, NAO_CLASSIFICADO)
    assert _classe("Relatório de revisão sem ressalva.") == (
        NAO_CLASSIFICADO,
        NAO_CLASSIFICADO,
    )
    assert _classe("") == (NAO_CLASSIFICADO, NAO_CLASSIFICADO)


def test_chamamos_a_atencao_da_incerteza_nao_vira_enfase():
    assert _classe(PADRAO + INCERTEZA)[0] == NAO


def _dfp() -> pd.DataFrame:
    linhas = [
        _item(A, PADRAO[:900], 1), _item(A, PADRAO[900:] + ENFASE, 2),  # relatório em dois itens
        _item(A, DECLARACAO, 1, "Declaração dos Diretores sobre as Demonstrações Financeiras", ""),
        _item(B, PADRAO + INCERTEZA, opiniao="Negativa de Opinião"),
        _item(C, PADRAO, opiniao="Com Ressalva"),
        _item(C, "Parecer do conselho fiscal", 1, "Parecer do Conselho Fiscal ou Órgão Equivalente", ""),
        _item(D, DECLARACAO, 1, "Declaração dos Diretores sobre as Demonstrações Financeiras", ""),
    ]  # fmt: skip
    principal = [
        _entrega(A, "2025-03-10", "100"), _entrega(B, "2025-04-01", "200"),
        _entrega(C, "2025-02-20", "300"), _entrega(D, "2025-02-21", "400"),
        _entrega(A, "2025-03-12", "101"),  # a mesma versão entregue de novo: vale a 1ª entrega
    ]  # fmt: skip
    return pareceres.ler_pareceres_do_dfp(_zip_do_dfp(linhas, principal))


def test_uma_linha_por_documento_com_relatorio_do_auditor():
    tabela = _dfp().set_index("cnpj")
    assert list(tabela.index) == [A, B, C]  # D só tem a declaração dos diretores
    assert list(_dfp().columns) == list(pareceres.COLUNAS)
    assert tabela.loc[A, "opiniao"] == "sem_ressalva"
    assert (tabela.loc[A, "enfase"], tabela.loc[A, "continuidade_operacional"]) == (
        SIM,
        NAO,
    )
    assert tabela.loc[B, "opiniao"] == "abstencao"
    assert tabela.loc[B, "continuidade_operacional"] == SIM
    assert tabela.loc[C, "opiniao"] == "com_ressalva"
    assert tabela.loc[A, "referencia"] == date(2024, 12, 31)


def test_itens_na_ordem_do_numero_e_data_da_primeira_entrega():
    tabela = _dfp().set_index("cnpj")
    assert tabela.loc[A, "disponivel_em"] == date(2025, 3, 10)
    assert tabela.loc[A, "id_documento"] == "100"
    # o parágrafo de ênfase está no item 2: o texto foi juntado na ordem dos itens
    assert tabela.loc[A, "caracteres_do_relatorio"] > len(PADRAO)


def test_o_texto_do_relatorio_nao_e_guardado():
    assert not any("texto" in coluna for coluna in _dfp().columns)


def test_opiniao_vazia_ou_nova_nao_e_chutada():
    linhas = [
        _item(A, PADRAO, opiniao=""),
        _item(B, PADRAO, opiniao="Opinião Modificada"),
    ]
    principal = [_entrega(A, "2025-03-10", "1"), _entrega(B, "2025-03-11", "2")]
    tabela = pareceres.ler_pareceres_do_dfp(_zip_do_dfp(linhas, principal)).set_index(
        "cnpj"
    )
    assert tabela["opiniao"].tolist() == [NAO_CLASSIFICADO, NAO_CLASSIFICADO]


def test_itr_le_a_revisao_especial():
    linhas = [
        _item(A, PADRAO, tipo="Relatório da Revisão Especial", referencia="2024-03-31"),
        _item(
            A,
            DECLARACAO,
            1,
            "Declaração dos Diretores sobre o Relatório do Auditor Independente",
            "",
            referencia="2024-03-31",
        ),
    ]
    principal = [_entrega(A, "2024-05-08", "9", referencia="2024-03-31")]
    tabela = pareceres.ler_pareceres_do_itr(_zip_do_dfp(linhas, principal, itr=True))
    assert len(tabela) == 1
    assert tabela.loc[0, "opiniao"] == "sem_ressalva"
    assert tabela.loc[0, "referencia"] == date(2024, 3, 31)


def test_documento_sem_entrega_no_arquivo_principal_nao_tem_data_e_fica_de_fora():
    linhas = [_item(A, PADRAO), _item(B, PADRAO)]
    tabela = pareceres.ler_pareceres_do_dfp(
        _zip_do_dfp(linhas, [_entrega(A, "2025-03-10", "1")])
    )
    assert tabela["cnpj"].tolist() == [A]


def test_cortar_o_futuro_nao_muda_o_passado():
    """Montar só com o que foi entregue até uma data dá as mesmas linhas que montar tudo e cortar."""
    tudo = _dfp()
    corte = date(2025, 3, 1)
    linhas = [
        _item(A, PADRAO[:900], 1), _item(A, PADRAO[900:] + ENFASE, 2),
        _item(B, PADRAO + INCERTEZA, opiniao="Negativa de Opinião"),
        _item(C, PADRAO, opiniao="Com Ressalva"),
    ]  # fmt: skip
    so_ate_o_corte = [_entrega(C, "2025-02-20", "300")]
    parcial = pareceres.ler_pareceres_do_dfp(_zip_do_dfp(linhas, so_ate_o_corte))
    cortada = pareceres.entregues_ate(tudo, corte)
    pd.testing.assert_frame_equal(parcial, cortada)
    assert cortada["cnpj"].tolist() == [C]
