"""O contrato comum dos fatos financeiros documentais (`base/fatos_documentais.py`; linha 718 da fila,
ADR 0124): quatro tabelas que guardam cada valor com a página, a data-base e a unidade de onde saiu.

Regras que estes testes travam (briefing de 04/11/2026): nulo, traço e zero são três valores; um
conflito guarda as duas provas, nunca uma média; vínculo econômico nunca soma; reconciliação não vira um
terceiro saldo; avalista pessoa física não entra; nome aproximado é só candidato; cada linha leva o
carimbo do documento de onde saiu, e um vínculo só vale quando os dois documentos são públicos.

Os valores são os do briefing (São Braz e Bem Brasil), mas página e célula aqui são ilustrativas.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pyarrow as pa
import pytest

from base import fatos_documentais as fd

SHA_SAO_BRAZ = "76405c8580752e840f1daa91387d5076f14d074c35e15be3f51d2296756500e8"
SHA_BEM_BRASIL = "a588b0345f058ded8e346f6f54e22ea268be1a74921cdd6fe8ca8aed4f891d44"
AGORA = datetime(2026, 11, 5, 22, 0, tzinfo=UTC)
COLETADO_EM = datetime(2026, 11, 4, 3, 17, tzinfo=UTC)
PAGINA_DO_JORNAL = "https://auniao.pb.gov.br/servicos/copy_of_jornal-a-uniao/2026/abril"


def _documento(
    sha256: str = SHA_SAO_BRAZ, disponivel_em: date = date(2026, 4, 23)
) -> fd.Documento:
    return fd.Documento(
        sha256=sha256,
        url_observada=PAGINA_DO_JORNAL + "/jornal-em-pdf-23-04-26-cdepc.pdf",
        pagina_que_publicou=PAGINA_DO_JORNAL,
        bytes=17_198_464,
        coletado_em=COLETADO_EM,
        disponivel_em=disponivel_em,
        data_declarada=date(2025, 12, 31),
        formato="pdf",
        paginas=34,
        familia="divida",
        guardado_em="originais/fatos_documentais/76405c85.pdf",
        licenca="só prova interna (ADR 0124)",
    )


def _identidade(
    *,
    documento: str = SHA_SAO_BRAZ,
    nome: str = "São Braz S.A. Indústria e Comércio de Alimentos",
    papel: str = "devedora",
    cnpj: str = "08811226000184",
    candidato: bool = False,
) -> fd.Identidade:
    return fd.Identidade(
        documento=documento,
        identificador_na_fonte=nome,
        papel=papel,
        cnpj=cnpj,
        evidencia="p. 27, nota 2(c)",
        candidato=candidato,
    )


def _fato(
    valor_original: str = "41.250",
    *,
    documento: str = SHA_SAO_BRAZ,
    identidade: str | None = None,
    medida: str = "emprestimos_e_financiamentos",
    celula_ou_linha: str = "Caixa Econômica Federal",
    pagina_pdf: int = 27,
    unidade_declarada: str = "mil",
) -> fd.Fato:
    return fd.Fato(
        documento=documento,
        identidade=identidade or _identidade().chave,
        medida=medida,
        data_base=date(2025, 12, 31),
        visao="consolidada",
        pagina_pdf=pagina_pdf,
        celula_ou_linha=celula_ou_linha,
        valor_original=valor_original,
        unidade_declarada=unidade_declarada,
        natureza="estoque",
        pagina_impressa=pagina_pdf,
    )


def _registros(
    fatos: list[fd.Fato],
    *,
    documentos: list[fd.Documento] | None = None,
    identidades: list[fd.Identidade] | None = None,
    vinculos: list[fd.Vinculo] | None = None,
) -> fd.Registros:
    return fd.Registros(
        documentos=documentos or [_documento()],
        identidades=identidades or [_identidade()],
        fatos=fatos,
        vinculos=vinculos or [],
    )


def test_valor_so_com_numero_em_portugues():
    assert _fato("70.584.033,86", unidade_declarada="unidade").valor == Decimal(
        "70584033.86"
    )
    assert _fato("(12.823)").valor == Decimal(-12823000)  # parênteses: negativo, em mil
    with pytest.raises(ValueError, match="número"):
        _fato("quarenta e um mil")
    with pytest.raises(ValueError, match="casas"):
        _fato(
            "3,6375", unidade_declarada="unidade"
        )  # a tabela guarda duas casas: não arredonda


def test_nulo_traco_zero_distintos():
    vazio = _fato("", celula_ou_linha="linha sem valor")
    traco = _fato("-", celula_ou_linha="linha com traço")
    zero = _fato("0", celula_ou_linha="2025 (zero informado)")

    assert (vazio.valor, traco.valor, zero.valor) == (None, None, Decimal(0))
    assert [f.classe_do_valor for f in (vazio, traco, zero)] == [
        "nulo",
        "traco",
        "zero",
    ]
    tabela = fd.montar(_registros([vazio, traco, zero]), AGORA)["fato_financeiro"]
    assert tabela["valor_original"].tolist() == ["", "-", "0"]
    assert tabela["valor"].tolist() == [None, None, Decimal(0)]


def test_conflito_guarda_as_duas_provas():
    documento = _documento(SHA_BEM_BRASIL, date(2025, 10, 9))
    identidade = _identidade(
        documento=SHA_BEM_BRASIL,
        nome="Bem Brasil Alimentos S.A.",
        cnpj="06004860000180",
    )
    na_capa = _fato(
        "3,63",
        documento=SHA_BEM_BRASIL,
        identidade=identidade.chave,
        medida="spread_sobre_ipca_aa",
        unidade_declarada="unidade",
        pagina_pdf=12,
        celula_ou_linha="taxa na capa",
    )
    na_nota = _fato(
        "3,87",
        documento=SHA_BEM_BRASIL,
        identidade=identidade.chave,
        medida="spread_sobre_ipca_aa",
        unidade_declarada="unidade",
        pagina_pdf=880,
        celula_ou_linha="taxa na nota",
    )

    um, dois = fd.conflito(na_capa, na_nota)

    assert um.estado == dois.estado == "conflito"
    assert um.grupo_de_conflito == dois.grupo_de_conflito
    assert (um.valor_original, um.pagina_pdf) == ("3,63", 12)
    assert (dois.valor_original, dois.pagina_pdf) == ("3,87", 880)
    registros = _registros([um, dois], documentos=[documento], identidades=[identidade])
    tabela = fd.montar(registros, AGORA)["fato_financeiro"]
    assert sorted(tabela["valor"]) == [
        Decimal("3.63"),
        Decimal("3.87"),
    ]  # as duas, sem média
    assert tabela["grupo_de_conflito"].nunique() == 1
    with pytest.raises(ValueError, match="mesmo"):
        fd.conflito(na_capa, na_capa)  # o mesmo valor duas vezes não é conflito
    outra_medida = _fato(
        "146.335", documento=SHA_BEM_BRASIL, identidade=identidade.chave
    )
    with pytest.raises(ValueError, match="medida"):
        fd.conflito(na_capa, outra_medida)


def test_vinculo_nao_soma():
    vinculo = fd.Vinculo(
        operacao="mesma emissão vista em dois documentos",
        documento_a=SHA_SAO_BRAZ,
        documento_b=SHA_BEM_BRASIL,
        relacao="mesma-operacao",
    )
    assert vinculo.aditivo is False
    with pytest.raises(ValueError, match="soma"):
        fd.Vinculo(
            operacao="emissão e saldo",
            documento_a=SHA_SAO_BRAZ,
            documento_b=SHA_BEM_BRASIL,
            relacao="emissao-saldo",
            aditivo=True,
        )
    with pytest.raises(ValueError, match="relação"):
        fd.Vinculo(
            operacao="x",
            documento_a=SHA_SAO_BRAZ,
            documento_b=SHA_BEM_BRASIL,
            relacao="soma",
        )


def test_reconciliacao_nao_e_saldo():
    nominal = _fato("102.042", medida="valor_nominal", celula_ou_linha="Total nominal")
    juros = _fato(
        "27.245",
        medida="juros_a_transcorrer",
        celula_ou_linha="(-) Juros a transcorrer",
    )
    reconciliacao = fd.Vinculo(
        operacao="nominal menos juros a transcorrer",
        documento_a=SHA_SAO_BRAZ,
        documento_b=SHA_SAO_BRAZ,
        relacao="reconciliacao",
    )

    tabelas = fd.montar(_registros([nominal, juros], vinculos=[reconciliacao]), AGORA)

    # os dois fatos como estão no documento; nenhum 74.797.000 derivado
    assert sorted(tabelas["fato_financeiro"]["valor"]) == [
        Decimal(27245000),
        Decimal(102042000),
    ]
    vinculos = tabelas["vinculo_economico"][["relacao", "aditivo"]].to_dict("records")
    assert vinculos == [{"relacao": "reconciliacao", "aditivo": False}]


def test_avalista_pf_nao_entra():
    with pytest.raises(ValueError, match="pessoa física"):
        _identidade(papel="avalista-pf")
    with pytest.raises(ValueError, match="CNPJ"):
        _identidade(papel="avalista-pj", cnpj="12345678901")  # 11 dígitos é CPF


def test_nome_aproximado_so_candidato():
    candidato = _identidade(
        nome="HFS Administração e Investimentos", cnpj="", candidato=True
    )
    assert (candidato.cnpj, candidato.candidato) == ("", True)
    with pytest.raises(ValueError, match="candidato"):
        _identidade(cnpj="")  # sem CNPJ e sem ser candidato
    with pytest.raises(ValueError, match="candidato"):
        _identidade(cnpj="37980530000404", candidato=True)  # candidato não leva CNPJ


def test_montar_carimba_cada_linha_com_o_documento():
    tabela = fd.montar(_registros([_fato()]), AGORA)["fato_financeiro"]

    assert tabela["consta"].tolist() == [True]
    [linha] = tabela.to_dict("records")
    assert linha["visto_em"] == AGORA
    assert linha["disponivel_em"] == date(2026, 4, 23)
    assert linha["origem_sha256"] == SHA_SAO_BRAZ
    assert linha["origem_coletada_em"] == COLETADO_EM
    with pytest.raises(ValueError, match="documento"):
        fd.montar(_registros([_fato(documento=SHA_BEM_BRASIL)]), AGORA)


def test_vinculo_so_vale_quando_os_dois_documentos_sao_publicos():
    primeiro = _documento(SHA_SAO_BRAZ, date(2026, 4, 17))
    segundo = _documento(SHA_BEM_BRASIL, date(2026, 4, 20))
    vinculo = fd.Vinculo(
        operacao="mesma emissão em dois documentos",
        documento_a=SHA_SAO_BRAZ,
        documento_b=SHA_BEM_BRASIL,
        relacao="mesma-operacao",
    )
    registros = fd.Registros(documentos=[primeiro, segundo], vinculos=[vinculo])

    tabela = fd.montar(registros, AGORA)["vinculo_economico"]

    assert tabela["disponivel_em"].tolist() == [date(2026, 4, 20)]


def test_esquemas_das_quatro_tabelas():
    esquemas = fd.esquemas()
    assert set(esquemas) == {
        "documento",
        "identidade_documental",
        "fato_financeiro",
        "vinculo_economico",
    }
    assert esquemas["fato_financeiro"].field("valor").type == pa.decimal128(18, 2)
    tabelas = fd.montar(_registros([_fato()]), AGORA)
    for nome, tabela in tabelas.items():
        assert list(tabela.columns) == esquemas[nome].names
        assert fd.como_arrow(nome, tabela).schema.equals(esquemas[nome])


def _valor(gabarito, cnpj: str, medida: str) -> Decimal:
    [texto] = gabarito.loc[
        (gabarito["cnpj"] == cnpj) & (gabarito["medida"] == medida), "valor"
    ].tolist()
    return Decimal(texto)


def test_gabarito_tem_documento_pagina_e_data():
    gabarito = fd.gabarito()

    assert len(gabarito) > 0
    assert gabarito["documento_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    tem_lugar = (gabarito["pagina_pdf"] != "") | (gabarito["celula_ou_linha"] != "")
    assert tem_lugar.all(), gabarito.loc[~tem_lugar, ["cnpj", "medida"]]
    assert gabarito["conferido_em"].str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()
    assert gabarito["fonte"].str.startswith("https://").all()
    assert (
        gabarito["cnpj"].str.fullmatch(r"\d{8}|\d{14}").all()
    )  # raiz ou CNPJ; nunca CPF


def test_gabarito_bate_com_o_briefing():
    g = fd.gabarito()
    sao_braz, alibem, frico, hfs = (
        "08811226000184",
        "03941052000150",
        "07014305000100",
        "37980530000404",
    )

    bancos = ["caixa", "santander", "bnb"]
    assert sum(_valor(g, sao_braz, f"divida_{b}") for b in bancos) == Decimal(74797000)
    circulante_mais_longo = _valor(g, sao_braz, "divida_circulante") + _valor(
        g, sao_braz, "divida_nao_circulante"
    )
    assert circulante_mais_longo == _valor(g, sao_braz, "divida_total")
    assert _valor(g, sao_braz, "valor_nominal") - _valor(
        g, sao_braz, "juros_a_transcorrer"
    ) == _valor(
        g, sao_braz, "divida_total"
    )  # reconciliação: confere, não vira linha nova
    assert _valor(g, alibem, "divida_modalidades") - _valor(
        g, alibem, "custos_de_captacao_a_apropriar"
    ) == _valor(g, alibem, "divida_liquida_de_custos")
    assert _valor(g, frico, "liberacao_2024") + _valor(
        g, frico, "liberacao_2025"
    ) == _valor(g, frico, "liberado_projeto")
    assert _valor(g, frico, "liberado_projeto") != _valor(
        g, frico, "participacao_contratada"
    )
    assert _valor(g, hfs, "liberacao_2025") == 0  # zero informado: está lá, não é vazio
    # conflitos guardados nos dois lados, nunca uma média
    assert sorted(g.loc[g["medida"] == "spread_sobre_ipca_aa", "valor"]) == [
        "3.63",
        "3.87",
    ]
    assert (
        len(g.loc[(g["cnpj"] == sao_braz) & (g["medida"] == "vencimento_santander")])
        == 2
    )
    # PIS e Cofins da J.B.World têm o mesmo valor e ficam em duas linhas, sem somar
    jb = g.loc[g["cnpj"] == "85248987"]
    assert sorted(jb["medida"]) == ["perse_cofins", "perse_pis"]
    assert set(jb["valor"]) == {"492285396.03"}
    empresas = {
        sao_braz, alibem, "06004860000180", hfs, frico, "51166456000167",
        "85248987", "15195705", "11200595000145", "16921603000166",
    }  # fmt: skip
    assert set(g["cnpj"]) == empresas
