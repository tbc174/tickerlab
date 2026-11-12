"""CPF no texto livre (linha 884): a máscara é uma regra só, usada no acervo, no banco do app e na saída do recorte."""

import io
import zipfile
from pathlib import Path

import duckdb
import pandas as pd
import pytest
import sqlalchemy as sa

from base.cpf_no_texto import (
    MARCA,
    mascarar_coluna,
    mascarar_cpf,
    quantos_com_cpf_valido,
    tem_cpf_valido,
)
from scripts import montar_recorte_da_api as envio
from src import eventos as ev
from src.banco import eventos as repo
from src.banco.conexao import criar_engine, migrar_para
from src.banco.modelo import eventos
from tests.ajudantes_de_cpf import CPF_DE_TESTE, formatado, no_formato
from tests.test_eventos import PASTA, _zip

# número de teste que confere nos dois dígitos, montado na hora a partir de nove dígitos inventados
CPF = formatado(CPF_DE_TESTE)
CPF_COLADO = CPF_DE_TESTE
# a mesma forma, com o dígito verificador trocado (não confere)
CPF_DE_DIGITO_ERRADO = CPF[:-2] + f"{(int(CPF[-2:]) + 1) % 100:02d}"
CPF_COM_ESPACO_NAO_SEPARAVEL = no_formato(CPF_DE_TESTE, "ddd ddd ddd dd")


@pytest.mark.parametrize(
    "texto",
    [
        f"Ata assinada por {CPF}",
        f"cpf {CPF_COLADO} do sócio",
        f"{CPF[:3]} {CPF[4:7]} {CPF[8:]}",
    ],
)
def test_cpf_que_confere_e_achado_e_mascarado(texto):
    assert tem_cpf_valido(texto)
    assert MARCA in mascarar_cpf(texto)
    assert not tem_cpf_valido(mascarar_cpf(texto))


@pytest.mark.parametrize(
    "texto",
    [
        "protocolo 20190123456",  # 11 dígitos que não conferem
        "cnpj 11.222.333/0001-81",  # CNPJ não é CPF
        CPF_DE_DIGITO_ERRADO,  # forma de CPF, dígitos errados
        "00000000000",  # todos iguais
        f"9{CPF_COLADO}",  # parte de um número maior
        "",
        None,
    ],
)
def test_o_que_nao_e_cpf_fica_igual(texto):
    assert not tem_cpf_valido(texto)
    assert mascarar_cpf(texto) == (texto or "")


def test_a_coluna_e_mascarada_so_onde_precisa():
    serie = pd.Series(["sem nada", f"com {CPF}", None], index=[5, 6, 7])
    saida = mascarar_coluna(serie)
    assert list(saida.index) == [5, 6, 7]
    assert saida.tolist() == ["sem nada", f"com {MARCA}", ""]
    assert quantos_com_cpf_valido(serie) == 1


def _zip_do_ipe_com_cpf() -> bytes:
    bruto = pd.read_csv(
        PASTA / "ipe_amostra.csv", sep=";", encoding="latin-1", dtype=str
    )
    bruto["Assunto"] = bruto["Assunto"].fillna("") + f" assinado {CPF}"
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            "ipe_cia_aberta_2026.csv",
            bruto.to_csv(sep=";", index=False, encoding="latin-1").encode("latin-1"),
        )
    return saida.getvalue()


def test_o_leitor_do_ipe_ja_entrega_o_assunto_sem_cpf():
    base = ev.ler_ipe(_zip("ipe_cia_aberta_2026.csv", "ipe_amostra.csv"))
    lido = ev.ler_ipe(_zip_do_ipe_com_cpf())
    assert len(lido) == len(base) > 0
    assert quantos_com_cpf_valido(lido["assunto"]) == 0
    assert lido["assunto"].str.contains(MARCA, regex=False).all()


def test_gravar_eventos_mascara_mesmo_que_a_tabela_venha_com_cpf(tmp_path):
    url = f"sqlite:///{(tmp_path / 'c.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        tabela = ev.ler_ipe(_zip("ipe_cia_aberta_2026.csv", "ipe_amostra.csv")).head(2)
        tabela = tabela.assign(assunto=f"ata {CPF}")
        with motor.begin() as conexao:
            repo.gravar_eventos(conexao, tabela)
        with motor.connect() as conexao:
            textos = conexao.execute(sa.select(eventos.c.assunto)).scalars().all()
        assert textos and quantos_com_cpf_valido(textos) == 0
    finally:
        motor.dispose()


def _parquet(caminho: Path, selecao: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    duckdb.sql(f"COPY ({selecao}) TO '{caminho.as_posix()}' (FORMAT PARQUET)")


@pytest.mark.parametrize(
    "tabela", ["eventos", "insolvencia", "debentures_assembleias", "ma_candidatos"]
)
def test_o_recorte_recusa_texto_livre_com_cpf_valido(tmp_path, tabela):
    arquivo = tmp_path / tabela / "a.parquet"
    _parquet(arquivo, f"SELECT 'ata de {CPF}' AS assunto, 'x' AS outra")
    with pytest.raises(envio.RecorteErro, match="CPF no texto") as erro:
        envio.conferir_sem_cpf_no_texto(duckdb.connect(), tabela, arquivo)
    assert CPF not in str(erro.value) and CPF_COLADO not in str(erro.value)


def test_o_recorte_deixa_passar_texto_sem_cpf_e_numero_que_nao_confere(tmp_path):
    arquivo = tmp_path / "eventos" / "a.parquet"
    _parquet(
        arquivo,
        f"SELECT * FROM (VALUES ('fato relevante'), ('prot 20190123456'), ('{CPF_DE_DIGITO_ERRADO}'), "
        f"('cpf {MARCA}')) t(assunto)",
    )
    envio.conferir_sem_cpf_no_texto(duckdb.connect(), "eventos", arquivo)


def test_o_recorte_confere_a_coluna_so_das_tabelas_de_texto_livre(tmp_path):
    arquivo = tmp_path / "outra" / "a.parquet"
    _parquet(arquivo, f"SELECT '{CPF}' AS assunto")
    envio.conferir_sem_cpf_no_texto(duckdb.connect(), "outra_tabela", arquivo)


def test_o_recorte_ve_cpf_separado_por_espaco_nao_separavel_e_quebra_de_linha(tmp_path):
    arquivo = tmp_path / "eventos" / "a.parquet"
    _parquet(
        arquivo,
        f"SELECT * FROM (VALUES ('a {CPF_COM_ESPACO_NAO_SEPARAVEL}'), ('b {CPF[:11]}\n{CPF[12:]}')) t(assunto)",
    )
    with pytest.raises(envio.RecorteErro, match="CPF no texto"):
        envio.conferir_sem_cpf_no_texto(duckdb.connect(), "eventos", arquivo)


def test_os_leitores_de_ratings_e_de_rotulos_ja_entregam_o_assunto_sem_cpf():
    from base import ratings, rotulos

    conteudo = _zip_do_ipe_com_cpf()
    for leitor in (ratings.ler_ipe_bruto, rotulos._ler_ipe_bruto):
        bruto = leitor(conteudo)
        assert len(bruto) > 0
        assert quantos_com_cpf_valido(bruto["Assunto"]) == 0
        assert bruto["Assunto"].str.contains(MARCA, regex=False).all()
