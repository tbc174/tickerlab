"""Carga dos informes mensais de CRI, CRA e OTS da CVM na base (B-16, série 6, PR 1): as tabelas
`securitizacao_certificados` e `securitizacao_cedente_devedor`, só com PJ, como eram na data de entrega.
Sem internet: zips reais pequenos em `tests/arquivos/cvm/securitizacao` e zips montados à mão."""

import io
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import historico, securitizacao
from base.dicionario import TABELAS
from src.banco.coletas import com_registro

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "securitizacao"
AGORA = datetime(2026, 10, 26, 18, tzinfo=UTC)
CNPJ_FORMATADO = re.compile(r"\d\d\.\d{3}\.\d{3}/\d{4}-\d\d")
CPF_FICTICIO = "52998224725"  # dígitos verificadores certos, de ninguém
URLS = {
    "cvm-cri": "https://dados.cvm.gov.br/dados/SECURIT/DOC/INF_MENSAL_CRI/DADOS/inf_mensal_cri_2026.zip",
    "cvm-cra": "https://dados.cvm.gov.br/dados/SECURIT/DOC/INF_MENSAL_CRA/DADOS/inf_mensal_cra_2026.zip",
    "cvm-securitizadoras-ots": "https://dados.cvm.gov.br/dados/SECURIT/DOC/INF_MENSAL_OTS/DADOS/inf_mensal_ots_2026.zip",
}
ARQUIVO_DA_FONTE = {
    "cvm-cri": "inf_mensal_cri_2026.zip",
    "cvm-cra": "inf_mensal_cra_2026.zip",
    "cvm-securitizadoras-ots": "inf_mensal_ots_2026.zip",
}
PRODUTO_DO_ARQUIVO = {
    "inf_mensal_cri_2026.zip": ("cri", "CRI"),
    "inf_mensal_cra_2026.zip": ("cra", "CRA"),
    "inf_mensal_ots_2026.zip": ("ots", "OTS"),
}


def _bytes(nome: str) -> bytes:
    return (PASTA / nome).read_bytes()


def _zip_com(quadros: dict[str, str], produto: str = "cra") -> bytes:
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        for quadro, texto in quadros.items():
            nome = f"inf_mensal_{produto}_{quadro}_2026.csv"
            arquivo.writestr(nome, texto.encode("latin-1"))
    return conteudo.getvalue()


CABECALHO = "CNPJ_Emissora;Codigo_Identificacao_Certificado;Data_Referencia;Versao"


def _informe_a_mao(data_entrega: str, documento: str = "33000167000101") -> bytes:
    geral = (
        f"{CABECALHO};Data_Entrega;Numero_Emissao;Nome_Emissao;Companhia_Emissora\n"
        f"02.773.542/0001-22;BRTESTECRA01;2026-05-01;1;{data_entrega};7;Série única;SECURITIZADORA SA\n"
    )
    cedentes = (
        f"{CABECALHO};Tipo;CNPJ;Percentual\n"
        f"02.773.542/0001-22;BRTESTECRA01;2026-05-01;1;Cedente;{documento};0.4\n"
        "02.773.542/0001-22;BRTESTECRA01;2026-05-01;1;Devedor;07526557000100;0.6\n"
    )
    return _zip_com({"geral": geral, "cedente_devedor": cedentes})


@pytest.mark.parametrize("nome", PRODUTO_DO_ARQUIVO)
def test_cedentes_e_devedores_so_pj_com_o_produto_e_a_chave(nome):
    produto, sigla = PRODUTO_DO_ARQUIVO[nome]
    tabela = securitizacao.ler_cedentes_e_devedores(_bytes(nome))
    assert list(tabela.columns) == list(securitizacao.COLUNAS_DO_CEDENTE_DEVEDOR)
    bruta = securitizacao.ler_informe(_bytes(nome), produto).tabelas["cedente_devedor"]
    assert len(tabela) == bruta["CNPJ"].notna().sum() > 0  # só o que tem CNPJ válido
    assert set(tabela["produto"]) == {sigla}
    assert set(tabela["papel"]) <= {"cedente", "devedor"}
    assert tabela["cnpj"].map(lambda c: bool(CNPJ_FORMATADO.fullmatch(c))).all()
    assert tabela["disponivel_em"].notna().all()
    assert (tabela["disponivel_em"] >= tabela["data_entrega"]).all()


@pytest.mark.parametrize("nome", PRODUTO_DO_ARQUIVO)
def test_certificados_um_por_mes_com_o_produto(nome):
    _, sigla = PRODUTO_DO_ARQUIVO[nome]
    tabela = securitizacao.ler_certificados(_bytes(nome))
    assert list(tabela.columns) == list(securitizacao.COLUNAS_DOS_CERTIFICADOS)
    assert set(tabela["produto"]) == {sigla}
    assert not tabela.duplicated(
        ["competencia", "cnpj_securitizadora", "codigo_certificado"]
    ).any()
    assert tabela["disponivel_em"].notna().all()


def test_zip_sem_quadro_do_informe_vira_tabela_vazia_com_as_colunas():
    # a CVM guarda no mesmo pacote as demonstrações financeiras (`dfin_*`): não são informe mensal
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        arquivo.writestr("dfin_cri_2026.csv", b"A;B\n1;2\n")
    vazio = conteudo.getvalue()
    for tabela, colunas in (
        (
            securitizacao.ler_cedentes_e_devedores(vazio),
            securitizacao.COLUNAS_DO_CEDENTE_DEVEDOR,
        ),
        (securitizacao.ler_certificados(vazio), securitizacao.COLUNAS_DOS_CERTIFICADOS),
    ):
        assert tabela.empty and list(tabela.columns) == list(colunas)


def test_cpf_e_documento_sem_digito_certo_nunca_viram_cedente():
    tabela = securitizacao.ler_cedentes_e_devedores(
        _informe_a_mao("2026-06-20", CPF_FICTICIO)
    )
    assert tabela["papel"].tolist() == ["devedor"]  # a linha do CPF sai inteira
    assert CPF_FICTICIO not in tabela.to_csv()


def test_nenhuma_coluna_guarda_nome_de_pessoa_ou_texto_livre():
    colunas = {
        *securitizacao.COLUNAS_DO_CEDENTE_DEVEDOR,
        *securitizacao.COLUNAS_DOS_CERTIFICADOS,
    }
    for proibida in ("cpf", "nome_cedente", "nome_devedor", "responsavel", "garantias"):
        assert not any(proibida in c for c in colunas)


def test_entrega_tardia_so_vale_dali_em_diante_e_cortar_o_futuro_nao_muda_o_passado():
    cedo = securitizacao.ler_cedentes_e_devedores(_informe_a_mao("2026-06-20"))
    tarde = securitizacao.ler_cedentes_e_devedores(_informe_a_mao("2027-01-15"))
    assert set(cedo["disponivel_em"]) == {pd.Timestamp("2026-06-20")}
    assert set(tarde["disponivel_em"]) == {pd.Timestamp("2027-01-15")}
    # em 2026-12-31 o informe entregue tarde ainda não existe; o entregue cedo já
    assert securitizacao.entregues_ate(tarde, pd.Timestamp("2026-12-31")).empty
    assert len(securitizacao.entregues_ate(cedo, pd.Timestamp("2026-12-31"))) == len(
        cedo
    )
    # cortar depois não muda o que já valia antes
    corte = pd.Timestamp("2026-06-30")
    assert securitizacao.entregues_ate(cedo, corte).equals(
        securitizacao.entregues_ate(
            securitizacao.entregues_ate(cedo, pd.Timestamp("2030-01-01")), corte
        )
    )


def test_as_tabelas_estao_no_dicionario_com_contrato_e_data_publica():
    for nome, colunas in (
        ("securitizacao_certificados", securitizacao.COLUNAS_DOS_CERTIFICADOS),
        ("securitizacao_cedente_devedor", securitizacao.COLUNAS_DO_CEDENTE_DEVEDOR),
    ):
        assert set(colunas) <= set(TABELAS[nome].colunas)
        assert "disponivel_em" in TABELAS[nome].colunas
    assert "Cedente e devedor" in TABELAS["securitizacao_cedente_devedor"].descricao


def _guardar(fonte: str, nome: str) -> None:
    conteudo = _bytes(nome)
    com_registro(fonte, lambda _: conteudo)(URLS[fonte])


def test_a_montagem_junta_cri_cra_e_ots_num_arquivo_por_ano(banco, tmp_path):
    for fonte, nome in ARQUIVO_DA_FONTE.items():
        _guardar(fonte, nome)
    with banco.connect() as conexao:
        linhas = historico.montar(
            "securitizacao_cedente_devedor", conexao, tmp_path / "base", AGORA
        )
        historico.montar(
            "securitizacao_certificados", conexao, tmp_path / "base", AGORA
        )
    assert set(linhas) == {2026}
    cedentes = pd.read_parquet(
        tmp_path / "base" / "securitizacao_cedente_devedor" / "2026.parquet"
    )
    assert len(cedentes) == linhas[2026]
    assert set(cedentes["produto"]) == {"CRI", "CRA", "OTS"}
    assert set(cedentes["origem_sha256"]) and set(cedentes["ano_do_arquivo"]) == {2026}
    certificados = pd.read_parquet(
        tmp_path / "base" / "securitizacao_certificados" / "2026.parquet"
    )
    assert set(certificados["produto"]) == {"CRI", "CRA", "OTS"}
