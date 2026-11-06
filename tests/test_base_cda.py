"""Carteiras dos fundos desde 2005 (série 3 da base de ML, PR 4; pedido 1 da sessão "FactSet").

Amostras reais recortadas do bloco de ações do CDA (`tests/arquivos/cvm/cda/`: Petrobras PN, Vale ON,
Magnesita PNC e Itaú PN, poucos fundos, nos arquivos de 2005, 2014, 2022 e set/2025). Inventário de
14/10/2026: as mesmas 21 colunas de 2005 a 2022; na CVM 175 só mudam `CNPJ_FUNDO` e `TP_FUNDO`.
"""

import io
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base import cda

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "cda"
ARQUIVOS = (
    "cda_fi_2005.zip",
    "cda_fi_2014.zip",
    "cda_fi_2022.zip",
    "cda_fi_202509.zip",
)


def _ler(nome: str, tamanho: int = cda.LINHAS_POR_PEDACO) -> pd.DataFrame:
    partes = cda.ler_posicoes_historicas((PASTA / nome).read_bytes(), tamanho)
    return pd.concat(list(partes), ignore_index=True)


def _bruto(nome: str) -> pd.DataFrame:
    """O CSV do jeito que a CVM entrega, para conferir os totais por fora do leitor."""
    with zipfile.ZipFile(PASTA / nome) as arquivo:
        texto = arquivo.read(arquivo.namelist()[0])
    return pd.read_csv(io.BytesIO(texto), sep=";", encoding="latin-1", dtype=str)


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_le_o_cda_de_cada_layout(nome):
    tabela = _ler(nome)
    assert list(tabela.columns) == list(cda.COLUNAS)
    assert tabela["cnpj_fundo"].str.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}").all()
    bruto = _bruto(nome)
    assert (
        len(tabela) == bruto["TP_APLIC"].isin(cda.TIPOS).sum()
    )  # futuro e opção ficam de fora


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_valor_e_quantidade_batem_com_o_arquivo(nome):
    tabela = _ler(nome)
    bruto = _bruto(nome)
    bruto = bruto[bruto["TP_APLIC"].isin(cda.TIPOS)]
    assert tabela["valor"].sum() == pytest.approx(
        pd.to_numeric(bruto["VL_MERC_POS_FINAL"]).sum()
    )
    assert tabela["quantidade"].sum() == pytest.approx(
        pd.to_numeric(bruto["QT_POS_FINAL"]).sum()
    )


def test_comprado_emprestado_e_vendido_separados():
    tipos = set(pd.concat([_ler(n) for n in ARQUIVOS])["tipo"])
    assert (
        tipos <= {cda.COMPRADO, cda.EMPRESTADO, cda.VENDIDO} and cda.COMPRADO in tipos
    )


def test_emissor_vem_do_isin():
    tabela = _ler("cda_fi_2005.zip")
    petrobras = tabela[tabela["isin"] == "BRPETRACNPR6"]
    assert not petrobras.empty and set(petrobras["emissor"]) == {"PETR"}
    assert set(tabela.loc[tabela["isin"] == "BRMAGSACNPC8", "emissor"]) == {"MAGS"}


def test_leitura_em_pedacos_da_o_mesmo_que_inteira():
    pd.testing.assert_frame_equal(
        _ler("cda_fi_2022.zip", 7), _ler("cda_fi_2022.zip", 10**6)
    )


def test_posicao_so_aparece_depois_da_divulgacao():
    """Sem data de entrega no arquivo, a posição de março só vale "como era" 90 dias depois; se
    ficou em sigilo até mais tarde (`DT_CONFID_APLIC`), só a partir do fim do sigilo."""
    tabela = pd.DataFrame(
        {
            "competencia": pd.to_datetime(["2022-03-31", "2022-03-31"]),
            "confidencial_ate": pd.to_datetime([None, "2022-09-30"]),
        }
    )
    publica = cda.disponivel_em(tabela)
    assert publica.tolist() == [pd.Timestamp("2022-06-29"), pd.Timestamp("2022-09-30")]
    com_data = tabela.assign(disponivel_em=publica)
    assert len(cda.como_era_em(com_data, date(2022, 6, 28))) == 0
    assert len(cda.como_era_em(com_data, date(2022, 6, 29))) == 1
    assert len(cda.como_era_em(com_data, date(2022, 9, 30))) == 2


# --- bloco 8 ("demais ativos", achado da série 4): fundos que informam ações da bolsa sem o código
# estruturado. Em 2020, R$ 1,14 tri (soma dos meses) em ações de companhias com ticker, ~26% a mais
# sobre o bloco 4, e quase nada repetido entre os blocos. Amostra real de 06/2016: a Itaú Ações
# Petrobras e o Caixa FMP-FGTS Petrobras III, que só informam a Petrobras no bloco 8
PETROBRAS = "33.000.167/0001-01"
CPF_DE_TESTE = "529.982.247-25"  # CPF válido usado só em testes (não é de ninguém)


def _bloco_8(conteudo: bytes) -> pd.DataFrame:
    partes = list(cda.ler_acoes_do_bloco_8(conteudo))
    return (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=list(cda.COLUNAS_DO_BLOCO_8))
    )


def test_bloco_8_traz_as_acoes_com_o_cnpj_do_emissor():
    linhas = _bloco_8((PASTA / "cda_fi_2016.zip").read_bytes())
    assert list(linhas.columns) == list(cda.COLUNAS_DO_BLOCO_8)
    assert set(linhas["cnpj_emissor"]) == {
        PETROBRAS
    }  # o título público do fundo fica fora
    assert sorted(linhas["tipo"]) == ["comprado", "comprado", "emprestado"]
    fmp = linhas[linhas["cnpj_fundo"] == "03.915.903/0001-90"].iloc[0]
    assert fmp["valor"] == pytest.approx(323_035_090.53)
    assert fmp["quantidade"] == 28_065_603
    assert fmp["descricao"] == "Ações - PETR3"


def _com_linhas_a_mais(*linhas: str) -> bytes:
    with zipfile.ZipFile(PASTA / "cda_fi_2016.zip") as original:
        blocos = {n: original.read(n) for n in original.namelist()}
    nome = "cda_fi_BLC_8_2016.csv"
    texto = blocos[nome].decode("latin-1").rstrip("\r\n") + "\r\n" + "\r\n".join(linhas)
    blocos[nome] = (texto + "\r\n").encode("latin-1")
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        for n, conteudo in blocos.items():
            z.writestr(n, conteudo)
    return saida.getvalue()


def _linha_do_bloco_8(pf_pj: str, documento: str) -> str:
    colunas = [
        "FI", "11.111.111/0001-11", "FUNDO DE TESTE", "2016-06-30", "Ações", "Ação ordinária", "N",
        "Para negociação", "", "", "", "", "100.000000", "1000.00", "", "", "AÇÕES DE TESTE",
        pf_pj, documento, "EMISSOR DE TESTE",
    ]  # fmt: skip
    return ";".join(colunas)


def test_bloco_8_nunca_guarda_cpf():
    """O bloco 8 traz o CPF do emissor pessoa física: a linha é descartada na leitura, e também a
    marcada como PJ cujo número pode ser um CPF (na dúvida, é dado pessoal)."""
    conteudo = _com_linhas_a_mais(
        _linha_do_bloco_8("PF", CPF_DE_TESTE),
        _linha_do_bloco_8("PJ", CPF_DE_TESTE),
    )
    linhas = _bloco_8(conteudo)
    assert len(linhas) == 3  # só as da amostra
    digitos = CPF_DE_TESTE.replace(".", "").replace("-", "")
    texto = linhas.astype(str).to_csv()
    assert CPF_DE_TESTE not in texto and digitos not in texto
    assert "11.111.111/0001-11" not in set(linhas["cnpj_fundo"])


def test_arquivo_sem_o_bloco_8_nao_traz_nada():
    assert _bloco_8((PASTA / "cda_fi_2005.zip").read_bytes()).empty


def _zip(**arquivos: str) -> bytes:
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        for nome, texto in arquivos.items():
            arquivo.writestr(nome, texto.encode("latin-1"))
    return conteudo.getvalue()


def test_chaves_do_cda_vem_do_arquivo_de_pl_um_fundo_por_linha():
    conteudo = _zip(
        cda_fi_PL_202609="TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;VL_PATRIM_LIQ\n"
        "FI;11.222.333/0001-81 ;A;2026-09-30;10\nFI;44.555.666/0001-81;B;2026-09-30;20\n",
        cda_fi_BLC_4_202609="nada que precise ser lido",
    )
    chaves = cda.chaves_do_cda(conteudo)
    assert list(chaves.columns) == ["competencia", "cnpj_fundo"]
    assert chaves["cnpj_fundo"].tolist() == ["11.222.333/0001-81", "44.555.666/0001-81"]
    assert (chaves["competencia"] == pd.Timestamp("2026-09-30")).all()


def test_chaves_do_cda_sem_pl_vem_do_bloco_4():
    conteudo = (PASTA / "cda_fi_202509.zip").read_bytes()
    posicoes = _ler("cda_fi_202509.zip")
    chaves = cda.chaves_do_cda(conteudo)
    esperado = posicoes[["competencia", "cnpj_fundo"]].drop_duplicates()
    assert set(map(tuple, chaves.to_numpy())) >= set(map(tuple, esperado.to_numpy()))
    assert not chaves.duplicated().any()


# --- bloco 2 (cotas de fundos que cada fundo tem; relatório da base de crédito, 16/10/2026): quem compra
# cotas de FIDC. Amostras reais recortadas de 2005, 2022 (layout antigo: `CNPJ_FUNDO_COTA`) e set/2025
# (CVM 175: `CNPJ_FUNDO_CLASSE_COTA`, `ID_SUBCLASSE`). Inventário de 16/10/2026 no acervo: 64 arquivos, um
# cabeçalho por arquivo, dois layouts; nomes com aspas sem fechar (2005 tem 54 linhas com aspas)
ARQUIVOS_DO_BLOCO_2 = ("cda_fi_2005.zip", "cda_fi_2022.zip", "cda_fi_202509.zip")
CNPJ = r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"


def _cotas(conteudo: bytes, tamanho: int = cda.LINHAS_POR_PEDACO) -> pd.DataFrame:
    partes = list(cda.ler_cotas_de_fundos(conteudo, tamanho))
    return (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=list(cda.COLUNAS_DAS_COTAS))
    )


def _bruto_do_bloco_2(nome: str) -> pd.DataFrame:
    with zipfile.ZipFile(PASTA / nome) as arquivo:
        bloco = next(n for n in arquivo.namelist() if "_BLC_2_" in n)
        texto = arquivo.read(bloco)
    return pd.read_csv(
        io.BytesIO(texto), sep=";", encoding="latin-1", dtype=str, quoting=3
    )


@pytest.mark.parametrize("nome", ARQUIVOS_DO_BLOCO_2)
def test_bloco_2_le_as_cotas_de_cada_layout(nome):
    cotas = _cotas((PASTA / nome).read_bytes())
    bruto = _bruto_do_bloco_2(nome)
    assert list(cotas.columns) == list(cda.COLUNAS_DAS_COTAS)
    assert len(cotas) == len(bruto)  # nenhuma linha perdida nem engolida pelas aspas
    assert cotas["cnpj_fundo"].str.fullmatch(CNPJ).all()
    assert cotas["cnpj_fundo_investido"].str.fullmatch(CNPJ).all()
    investido = next(
        c for c in ("CNPJ_FUNDO_CLASSE_COTA", "CNPJ_FUNDO_COTA") if c in bruto
    )
    assert (
        cotas["cnpj_fundo_investido"].tolist() == bruto[investido].str.strip().tolist()
    )
    assert cotas["valor"].sum() == pytest.approx(
        pd.to_numeric(bruto["VL_MERC_POS_FINAL"]).sum()
    )


def test_bloco_2_traz_a_cota_de_fidc_com_valor_e_emissor_ligado():
    cotas = _cotas((PASTA / "cda_fi_2022.zip").read_bytes())
    linha = cotas[
        (cotas["cnpj_fundo"] == "00.322.699/0001-06")
        & (cotas["cnpj_fundo_investido"] == "30.365.876/0001-00")
    ].iloc[0]
    assert linha["competencia"] == pd.Timestamp("2022-11-30")
    assert linha["tipo_do_ativo"] == "FIDC"
    assert linha["valor"] == pytest.approx(17_976_349.58)
    assert linha["quantidade"] == pytest.approx(17_536)
    assert linha["emissor_ligado"] == True
    dezembro = cotas[
        (cotas["cnpj_fundo"] == "00.322.699/0001-06")
        & (cotas["competencia"] == pd.Timestamp("2022-12-31"))
    ]
    assert (dezembro["emissor_ligado"] == False).all()
    # "Cotas de fundos" sem a coluna preenchida: nem sim nem não
    assert (
        cotas.loc[cotas["tipo_do_ativo"] == "Cotas de fundos", "emissor_ligado"]
        .isna()
        .all()
    )


def test_bloco_2_guarda_o_fim_do_sigilo_e_o_prazo_de_divulgacao():
    cotas = _cotas((PASTA / "cda_fi_2022.zip").read_bytes())
    sigilo = cotas[cotas["cnpj_fundo"] == "00.524.617/0001-06"]
    assert (sigilo["confidencial_ate"] == pd.Timestamp("2023-02-28")).all()
    publica = cda.disponivel_em(cotas)
    assert (publica >= cotas["competencia"] + pd.Timedelta(days=90)).all()


def test_bloco_2_le_nome_com_aspas_sem_fechar_sem_engolir_a_linha_seguinte():
    """O CSV da CVM tem aspas no meio dos nomes (`CURTO PRAZO "2"`) e às vezes sem fechar: lido sem
    tratar aspas (`quoting=3`), cada linha do arquivo é uma posição."""
    cotas = _cotas((PASTA / "cda_fi_2005.zip").read_bytes())
    basa = cotas[
        cotas["cnpj_fundo"] == "07.143.386/0001-30"
    ]  # FUNDO BASA [...] CURTO PRAZO "2"
    assert basa["cnpj_fundo_investido"].tolist() == [
        "01.671.480/0001-85",
        "04.877.280/0001-71",
    ]
    aberta = (
        'FI;11.111.111/0001-11;"FUNDO SEM FECHAR AS ASPAS;2025-09-30;Cotas de Fundos;FIDC;N;;;;;;'
        "10.000000;1000.00;;;22.222.222/0001-22;;FIDC DE TESTE"
    )
    seguinte = (
        "FI;33.333.333/0001-33;OUTRO FUNDO;2025-09-30;Cotas de Fundos;FIDC;N;;;;;;"
        "5.000000;500.00;;;22.222.222/0001-22;ABCDE1234567890;FIDC DE TESTE"
    )
    conteudo = _bloco_2_com_linhas_a_mais("cda_fi_202509.zip", aberta, seguinte)
    lidas = _cotas(conteudo)
    novas = lidas[lidas["cnpj_fundo_investido"] == "22.222.222/0001-22"]
    assert novas["cnpj_fundo"].tolist() == ["11.111.111/0001-11", "33.333.333/0001-33"]
    assert novas["valor"].tolist() == [1000.0, 500.0]
    assert novas["id_subclasse"].tolist()[1] == "ABCDE1234567890"


def _bloco_2_com_linhas_a_mais(nome: str, *linhas: str) -> bytes:
    with zipfile.ZipFile(PASTA / nome) as original:
        blocos = {n: original.read(n) for n in original.namelist()}
    bloco = next(n for n in blocos if "_BLC_2_" in n)
    texto = (
        blocos[bloco].decode("latin-1").rstrip("\r\n") + "\r\n" + "\r\n".join(linhas)
    )
    blocos[bloco] = (texto + "\r\n").encode("latin-1")
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        for n, conteudo in blocos.items():
            z.writestr(n, conteudo)
    return saida.getvalue()


def test_bloco_2_junta_as_colunas_de_nome_antigo_e_novo():
    """Lição do #333 (informe de FIDC): com as duas colunas no mesmo arquivo, vale a primeira não
    vazia de cada linha, nunca só a primeira coluna. Cabeçalho repetido no meio do arquivo sai."""
    cabecalho = (
        "TP_FUNDO;TP_FUNDO_CLASSE;CNPJ_FUNDO;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;TP_APLIC;"
        "TP_ATIVO;EMISSOR_LIGADO;QT_POS_FINAL;VL_MERC_POS_FINAL;DT_CONFID_APLIC;CNPJ_FUNDO_COTA;"
        "CNPJ_FUNDO_CLASSE_COTA;NM_FUNDO_COTA;NM_FUNDO_CLASSE_SUBCLASSE_COTA"
    )
    conteudo = _zip(
        cda_fi_BLC_2_202301=cabecalho + "\n"
        "FI;;11.111.111/0001-11;;ANTIGO;2023-01-31;Cotas de Fundos;FIDC;N;1;100.00;;"
        "22.222.222/0001-22;;FIDC A;\n" + cabecalho + "\n"
        ";CLASSES - FIF;;33.333.333/0001-33;NOVO;2023-01-31;Cotas de Fundos;FIDC;S;2;200.00;;"
        ";44.444.444/0001-44;;FIDC B\n"
    )
    cotas = _cotas(conteudo)
    assert cotas["cnpj_fundo"].tolist() == ["11.111.111/0001-11", "33.333.333/0001-33"]
    assert cotas["cnpj_fundo_investido"].tolist() == [
        "22.222.222/0001-22",
        "44.444.444/0001-44",
    ]
    assert cotas["tipo_do_fundo"].tolist() == ["FI", "CLASSES - FIF"]


def test_bloco_2_em_pedacos_da_o_mesmo_que_inteiro():
    conteudo = (PASTA / "cda_fi_2022.zip").read_bytes()
    pd.testing.assert_frame_equal(_cotas(conteudo, 5), _cotas(conteudo, 10**6))


def test_arquivo_sem_o_bloco_2_nao_traz_nada():
    assert _cotas((PASTA / "cda_fi_2014.zip").read_bytes()).empty


def test_bloco_2_guarda_o_texto_no_formato_compacto():
    """O bloco 2 de 2022 tem 2,2 milhões de linhas: com texto em objeto Python a tabela passava de 1,5 GB
    no servidor de casa (8 GB para tudo); no formato de texto do pandas fica com menos da metade."""
    cotas = _cotas((PASTA / "cda_fi_2022.zip").read_bytes())
    textos = ["cnpj_fundo", "tipo_do_fundo", "tipo_do_ativo", "cnpj_fundo_investido"]
    assert all(cotas[c].dtype == "str" for c in textos)
