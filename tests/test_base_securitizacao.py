"""Informes mensais de CRI, CRA e outros títulos de securitização (OTS) da CVM, sem dado pessoal.

Amostras reais recortadas (`tests/arquivos/cvm/securitizacao/`: 4 certificados por arquivo, todos os
quadros), geradas uma vez dos arquivos de 18/10/2026: CPFs e nomes trocados por fictícios, textos
livres por um texto neutro. Ficam os casos que o leitor precisa tratar: a linha quebrada do CRA
(um `;` dentro do campo), a chave repetida do OTS, o quadro `responsavel` do CRI de 2019 (nome e
cargo de pessoa) e valores que não são CNPJ no campo `CNPJ` dos cedentes e devedores.
"""

import io
import re
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import securitizacao

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "securitizacao"
ARQUIVOS = {
    "inf_mensal_cri_2019.zip": "cri",
    "inf_mensal_cri_2026.zip": "cri",
    "inf_mensal_cra_2026.zip": "cra",
    "inf_mensal_ots_2026.zip": "ots",
}
CPF_FICTICIO = "52998224725"  # dígitos verificadores certos, de ninguém
QUADROS_DA_CVM_175 = {
    "geral",
    "ativo_passivo",
    "classe",
    "direitos_creditorios",
    "cedente_devedor",
    "fluxo_caixa",
    "desembolso",
    "derivativos",
}
QUADROS_DO_CRI = {
    "geral",
    "ativo_passivo",
    "carteira",
    "carteira_modificacao",
    "classe",
    "creditos",
    "derivativos",
    "desembolso",
    "fluxo_caixa",
}


def _bytes(nome: str) -> bytes:
    return (PASTA / nome).read_bytes()


def _ler(nome: str) -> securitizacao.Leitura:
    return securitizacao.ler_informe(_bytes(nome), ARQUIVOS[nome])


def _linhas_distintas(nome: str, quadro: str) -> int:
    """As linhas diferentes do quadro no arquivo bruto com o número certo de campos."""
    with zipfile.ZipFile(PASTA / nome) as arquivo:
        (interno,) = [
            n for n in arquivo.namelist() if re.search(rf"_{quadro}_\d{{4}}", n)
        ]
        linhas = arquivo.read(interno).decode("latin-1").splitlines()
    campos = linhas[0].count(";")
    return len({linha for linha in linhas[1:] if linha.count(";") == campos})


@pytest.mark.parametrize(
    ("nome", "esperados"),
    [
        ("inf_mensal_cri_2019.zip", QUADROS_DO_CRI),
        # em 2026 o CRI ganhou cedentes e devedores e perdeu as modificações da carteira
        (
            "inf_mensal_cri_2026.zip",
            QUADROS_DO_CRI - {"carteira_modificacao"} | {"cedente_devedor"},
        ),
        ("inf_mensal_cra_2026.zip", QUADROS_DA_CVM_175),
        ("inf_mensal_ots_2026.zip", QUADROS_DA_CVM_175),
    ],
)
def test_quadros_por_ano(nome, esperados):
    assert esperados <= securitizacao.quadros_do_arquivo(_bytes(nome), ARQUIVOS[nome])
    assert esperados <= set(_ler(nome).tabelas)


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_chave_e_competencia(nome):
    tabelas = _ler(nome).tabelas
    assert tabelas
    for quadro, tabela in tabelas.items():
        assert list(tabela.columns[:3]) == list(securitizacao.CHAVE), quadro
        assert (tabela["competencia"].dt.day == 1).all(), quadro
        assert (
            tabela["cnpj_securitizadora"]
            .str.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
            .all()
        ), quadro
        assert tabela["codigo_certificado"].notna().all(), quadro
        # linha repetida inteira (o OTS tem) entra uma vez só
        assert len(tabela) == _linhas_distintas(nome, quadro), quadro


def test_competencia_do_ots_e_o_primeiro_dia_do_mes():
    # o OTS informa o último dia do mês (2026-03-31); CRI e CRA, o primeiro
    geral = _ler("inf_mensal_ots_2026.zip").tabelas["geral"]
    linha = geral[geral["codigo_certificado"] == "BRPCHSDBS131"]
    assert pd.Timestamp("2026-03-01") in set(linha["competencia"])
    assert "2026-03-31" in set(linha["Data_Referencia"])


def test_produto_desconhecido_recusa():
    with pytest.raises(ValueError, match="fiagro"):
        securitizacao.ler_informe(_bytes("inf_mensal_cri_2026.zip"), "fiagro")


def test_quadro_responsavel_nao_entra():
    # nome e cargo de quem assina o informe (CRI até 2019): dado pessoal, fica só no acervo
    conteudo = _bytes("inf_mensal_cri_2019.zip")
    assert "responsavel" not in securitizacao.quadros_do_arquivo(conteudo, "cri")
    tabelas = securitizacao.ler_informe(conteudo, "cri").tabelas
    assert "responsavel" not in tabelas
    for quadro, tabela in tabelas.items():
        assert not {"Nome", "Cargo"} & set(tabela.columns), quadro


def _cpf(nove: str) -> str:
    """Os 11 dígitos de um CPF com dígitos verificadores certos, a partir dos 9 primeiros."""
    digitos = nove
    for tamanho in (9, 10):
        pesos = range(tamanho + 1, 1, -1)
        resto = sum(int(d) * p for d, p in zip(digitos, pesos, strict=True)) % 11
        digitos += str(0 if resto < 2 else 11 - resto)
    return digitos


def _digitos_de_cpf_valido(digitos: str) -> bool:
    return digitos != digitos[0] * 11 and _cpf(digitos[:9]) == digitos


def _e_documento(coluna: str) -> bool:
    return coluna.startswith(("CNPJ", "CPF", "cnpj")) or coluna == "Retentor_Risco"


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_nenhum_cpf_valido_sobra(nome):
    tabelas = _ler(nome).tabelas
    for quadro, tabela in tabelas.items():
        for coluna in tabela.columns:
            valores = tabela[coluna].dropna().astype(str)
            assert not valores.str.contains(CPF_FICTICIO).any(), (quadro, coluna)
            if not _e_documento(coluna):  # valor em dinheiro pode fechar como CPF
                continue
            documentos = valores.map(lambda v: re.sub(r"\D", "", v))
            curtos = documentos[documentos.str.len().between(1, 11)]
            assert not curtos.map(
                lambda d: _digitos_de_cpf_valido(d.zfill(11))
            ).any(), (
                quadro,
                coluna,
            )
    if "cedente_devedor" in tabelas:  # o CNPJ de empresa fica, formatado
        cnpjs = tabelas["cedente_devedor"]["CNPJ"].dropna()
        assert len(cnpjs) > 0
        assert cnpjs.str.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}").all()


def _cabecalhos(nome: str) -> set[str]:
    with zipfile.ZipFile(PASTA / nome) as arquivo:
        return {
            coluna
            for n in arquivo.namelist()
            for coluna in arquivo.read(n).decode("latin-1").splitlines()[0].split(";")
        }


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_textos_livres_saem(nome):
    # campo de texto livre pode trazer nome de pessoa (avalista, devedor): fica só no acervo
    presentes = _cabecalhos(nome) & set(securitizacao.TEXTOS_LIVRES)
    assert presentes  # a amostra tem textos livres para tirar
    for quadro, tabela in _ler(nome).tabelas.items():
        assert not presentes & set(tabela.columns), quadro


FORMATOS_DE_CPF = (
    lambda c: c,
    lambda c: c.lstrip("0") or "0",  # a CVM tira os zeros da esquerda
    lambda c: f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}",
    lambda c: f"{c} -",
)


@settings(max_examples=60, deadline=None)
@given(
    nove=st.text("0123456789", min_size=9, max_size=9),
    formato=st.sampled_from(FORMATOS_DE_CPF),
    coluna=st.sampled_from(["CNPJ", "Retentor_Risco"]),
)
def test_documento_de_empresa_nas_colunas(nove, formato, coluna):
    cpf = _cpf(nove)
    if cpf == cpf[0] * 11:
        return
    quadro = "cedente_devedor" if coluna == "CNPJ" else "geral"
    texto = (
        f"CNPJ_Emissora;Codigo_Identificacao_Certificado;Data_Referencia;Versao;{coluna}\n"
        f"02.773.542/0001-22;BRTESTECRA01;2026-05-01;1;{formato(cpf)}\n"
    )
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        arquivo.writestr(f"inf_mensal_cra_{quadro}_2026.csv", texto.encode("latin-1"))
    tabela = securitizacao.ler_informe(conteudo.getvalue(), "cra").tabelas[quadro]
    assert tabela[coluna].isna().all()


def _zip_com(quadros: dict[str, str], produto: str = "cra") -> bytes:
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        for quadro, texto in quadros.items():
            nome = f"inf_mensal_{produto}_{quadro}_2026.csv"
            arquivo.writestr(nome, texto.encode("latin-1"))
    return conteudo.getvalue()


def test_linha_quebrada_conta_e_avisa(caplog):
    # um ";" dentro de um campo do CRA de 2026: a linha sai, contada e avisada (vai para o manifesto)
    with caplog.at_level("WARNING", logger="base.securitizacao"):
        leitura = _ler("inf_mensal_cra_2026.zip")
    assert leitura.linhas_quebradas == {"cedente_devedor": 1}
    assert "cedente_devedor" in caplog.text
    assert _ler("inf_mensal_cri_2026.zip").linhas_quebradas == {}


CABECALHO = "CNPJ_Emissora;Codigo_Identificacao_Certificado;Data_Referencia;Versao"


def test_fica_a_maior_versao():
    geral = (
        f"{CABECALHO};Data_Entrega;Quantidade_Series\n"
        "02.773.542/0001-22;BRTESTECRA01;2026-05-01;1;2026-06-20;1\n"
        "02.773.542/0001-22;BRTESTECRA01;2026-05-01;2;2026-08-03;3\n"
        "02.773.542/0001-22;BRTESTECRA02;2026-05-01;1;2026-06-21;5\n"
    )
    cedentes = (
        f"{CABECALHO};Tipo;CNPJ;Percentual\n"
        "02.773.542/0001-22;BRTESTECRA01;2026-05-01;1;Cedente;33000167000101;0.5\n"
        "02.773.542/0001-22;BRTESTECRA01;2026-05-01;1;Cedente;07526557000100;0.5\n"
        "02.773.542/0001-22;BRTESTECRA01;2026-05-01;10;Cedente;33000167000101;1\n"
    )
    tabelas = securitizacao.ler_informe(
        _zip_com({"geral": geral, "cedente_devedor": cedentes}), "cra"
    ).tabelas
    series = tabelas["geral"].set_index("codigo_certificado")["Quantidade_Series"]
    assert series.to_dict() == {"BRTESTECRA01": "3", "BRTESTECRA02": "5"}
    # a versão 10 vence a 1 pelo número, não pelo texto; as linhas da versão vencida saem todas
    assert tabelas["cedente_devedor"]["Versao"].tolist() == ["10"]
