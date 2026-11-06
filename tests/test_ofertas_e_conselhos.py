"""Ofertas públicas e conselhos (série 4 da base de ML, PR 6): leitores sobre recortes reais da CVM (o
FRE com nome, CPF, nascimento e currículo trocados por valores fictícios ainda no servidor), a regra
de que nenhuma pessoa entra, e a carga com manifesto, versões e linhagem."""

import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import conselhos, ofertas
from base.parquet import conferir_tabela
from scripts import carga_ofertas_e_conselhos as carga
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para

ARQUIVOS = Path(__file__).parent / "arquivos"
FRE = (ARQUIVOS / "fre" / "fre_cia_aberta_2024.zip").read_bytes()
OFERTAS = (ARQUIVOS / "cvm" / "ofertas" / "oferta_distribuicao.zip").read_bytes()
URL_DO_FRE = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_2024.zip"
)
VERSAO = "6a2b0c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7c"
CPF = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
COLUNAS_PROIBIDAS = {c.lower() for c in conselhos.PESSOAIS} | {
    "nome_vendedor",
    "data_nascimento",
}
NOMES_PERMITIDOS = {
    "nome_emissor",
    "nome_lider",
    "nome_ofertante",
}  # empresas (com CNPJ)


def _com_pessoas() -> bytes:
    """O ZIP de ofertas com uma oferta secundária de pessoa física (vendedor e ofertante sem CNPJ)."""
    with zipfile.ZipFile(io.BytesIO(OFERTAS)) as original:
        arquivos = {n: original.read(n) for n in original.namelist()}
    linhas = arquivos[ofertas.ANTIGAS].decode("latin-1").splitlines(keepends=True)
    cabecalho = linhas[0].rstrip("\r\n").split(";")
    campos = linhas[-1].rstrip("\r\n").split(";")
    campos[cabecalho.index("Nome_Vendedor")] = "JOAO FICTICIO DA SILVA"
    campos[cabecalho.index("CNPJ_Ofertante")] = "123.456.789-09"
    campos[cabecalho.index("Nome_Ofertante")] = "MARIA FICTICIA SOUZA"
    arquivos[ofertas.ANTIGAS] = "".join([*linhas, ";".join(campos) + "\r\n"]).encode(
        "latin-1"
    )
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as novo:
        for nome, conteudo in arquivos.items():
            novo.writestr(nome, conteudo)
    return saida.getvalue()


def _todas_as_tabelas() -> dict[str, pd.DataFrame]:
    com_pessoas = _com_pessoas()
    return {
        "fre_conselho": conselhos.ler_conselho(FRE),
        "fre_comites": conselhos.ler_comites(FRE),
        "fre_remuneracao": conselhos.ler_remuneracao(FRE),
        "fre_remuneracao_extremos": conselhos.ler_remuneracao_extremos(FRE),
        "fre_diversidade": conselhos.ler_diversidade(FRE),
        "ofertas_antigas": ofertas.ler_antigas(com_pessoas),
        "ofertas_resolucao_160": ofertas.ler_resolucao_160(com_pessoas),
    }


# --- nenhuma pessoa entra ---------------------------------------------------------------------------
def test_nenhum_cpf_e_nenhuma_coluna_pessoal_proibida():
    for nome, tabela in _todas_as_tabelas().items():
        assert not tabela.empty, nome
        colunas = set(tabela.columns)
        assert not colunas & COLUNAS_PROIBIDAS, nome
        assert not {c for c in colunas if "cpf" in c}, nome
        assert {c for c in colunas if c.startswith("nome")} <= NOMES_PERMITIDOS, nome
        textos = [
            c for c in tabela.columns
            if not pd.api.types.is_numeric_dtype(tabela[c])
            and not pd.api.types.is_datetime64_any_dtype(tabela[c])
        ]  # fmt: skip
        assert textos, nome
        for coluna in textos:
            valores = tabela[coluna].astype(str)
            assert not valores.str.contains(CPF).any(), (nome, coluna)
            assert not valores.str.contains("FICTICI").any(), (nome, coluna)


def test_oferta_de_pessoa_fisica_entra_sem_o_nome_nem_o_cpf():
    sem = ofertas.ler_antigas(OFERTAS)
    com = ofertas.ler_antigas(_com_pessoas())
    assert len(com) == len(sem) + 1  # a oferta entra
    secundaria = com.iloc[[-1]]
    assert secundaria[["cnpj_ofertante", "nome_ofertante"]].isna().all(axis=None)
    assert "nome_vendedor" not in com.columns


# --- leitores ---------------------------------------------------------------------------------------
def test_conselho_conta_por_orgao_com_a_data_de_entrega():
    conselho = conselhos.ler_conselho(FRE)
    nome = "fre_cia_aberta_administrador_membro_conselho_fiscal_2024.csv"
    with zipfile.ZipFile(io.BytesIO(FRE)) as arquivo:
        bruto = pd.read_csv(arquivo.open(nome), sep=";", dtype=str, encoding="latin-1")
    assert conselho["membros"].sum() == len(bruto)
    petrobras = conselho[conselho["cnpj"] == "33.000.167/0001-01"]
    assert petrobras["conhecido_em"].notna().all()
    entregas = conselhos.entregas(FRE)
    assert set(petrobras["conhecido_em"]) == {
        entregas[i] for i in petrobras["id_documento"]
    }
    assert (conselho["independentes"] <= conselho["membros"]).all()


def test_remuneracao_e_diversidade_como_a_cvm_publica():
    remuneracao = conselhos.ler_remuneracao(FRE)
    assert remuneracao["total_do_orgao"].dtype.kind == "f"
    assert not remuneracao.duplicated().any()
    diversidade = conselhos.ler_diversidade(FRE)
    assert {"genero_feminino", "raca_preto", "pcd_pcd", "genero_nao_aplicavel"} <= set(
        diversidade.columns
    )
    assert set(diversidade["genero_nao_aplicavel"].dropna()) <= {"S", "N"}


def test_fre_sem_as_tabelas_novas_da_vazio_e_nao_quebra():
    saida = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(FRE)) as original,
        zipfile.ZipFile(saida, "w") as novo,
    ):
        for nome in original.namelist():
            if "declaracao" not in nome and "PCD" not in nome:
                novo.writestr(nome, original.read(nome))
    assert conselhos.ler_diversidade(saida.getvalue()).empty


def test_juntar_baixadas_guarda_a_versao_antiga_com_a_data_dela():
    nova = conselhos.ler_remuneracao(FRE)
    antiga = nova.head(2).assign(
        versao=1, id_documento="1", conhecido_em=pd.Timestamp("2024-05-29")
    )
    juntas = conselhos.juntar_baixadas([antiga, nova, nova])
    assert len(juntas) == len(nova) + 2


def test_datas_das_ofertas_nunca_adiantam():
    antigas = ofertas.ler_antigas(OFERTAS)
    assert (antigas["disponivel_em"] >= antigas["anunciada_em"]).all()
    restrita = antigas[antigas["rito_oferta"] == "ICVM 476"]
    assert (
        restrita["anunciada_em"] == restrita["data_comunicado"]
    ).all()  # só no comunicado
    registrada = antigas[antigas["rito_oferta"] == "ICVM 400 (com registro)"]
    assert (registrada["anunciada_em"] == registrada["data_registro_oferta"]).all()
    assert antigas["cnpj_emissor"].str.match(ofertas.CNPJ).all()  # sem CNPJ não entra
    novas = ofertas.ler_resolucao_160(OFERTAS)
    assert novas["data_registro"].notna().all()  # o requerimento em análise não entra
    assert not pd.api.types.is_numeric_dtype(novas["valor_mobiliario"])  # "Debêntures"


# --- carga ------------------------------------------------------------------------------------------
@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    quando = datetime(2026, 10, 15, 5, tzinfo=UTC)
    with criar_engine(url).begin() as c:
        for fonte, endereco, conteudo in (
            (ofertas.FONTE, ofertas.URL, OFERTAS),
            (carga.FONTE_DO_FRE, URL_DO_FRE, FRE),
        ):
            caminho = acervo.guardar_original(fonte, endereco, conteudo, quando)
            registrar(
                c,
                fonte,
                endereco,
                conteudo,
                "ok",
                agora=quando,
                caminho_do_original=caminho,
            )
    return tmp_path / "acervo" / "base"


def test_carga_grava_cada_tabela_com_manifesto_e_linhagem(ambiente):
    from base.linhagem import linhagem_da_tabela

    assert carga.main(["--base", str(ambiente)]) == 0
    arquivos = [
        ambiente / "ofertas" / "antigas.parquet",
        ambiente / "ofertas" / "resolucao_160.parquet",
        *(ambiente / pasta / "2024.parquet" for pasta in carga.TABELAS_DO_FRE),
    ]
    with criar_engine().connect() as c:
        for arquivo in arquivos:
            assert conferir_tabela(arquivo), arquivo
            manifesto = json.loads(
                arquivo.with_suffix(".json").read_text(encoding="utf-8")
            )
            assert manifesto["versao_do_codigo"] == VERSAO
            assert linhagem_da_tabela(c, arquivo).completa, arquivo
    antes = (ambiente / "fre_conselho" / "2024.json").read_text(encoding="utf-8")
    carga.main(["--base", str(ambiente)])
    assert (ambiente / "fre_conselho" / "2024.json").read_text(
        encoding="utf-8"
    ) == antes


def test_sem_a_versao_do_codigo_nao_grava(ambiente, monkeypatch):
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError):
        carga.main(["--base", str(ambiente)])
    assert not (ambiente / "ofertas").exists()


def test_cpf_no_meio_de_um_texto_vira_vazio():
    """Rede de segurança: um texto da CVM com um CPF no meio (achado num texto livre da 160) sai."""
    with zipfile.ZipFile(io.BytesIO(OFERTAS)) as original:
        arquivos = {n: original.read(n) for n in original.namelist()}
    linhas = arquivos[ofertas.RESOLUCAO_160].decode("latin-1").splitlines(keepends=True)
    cabecalho = linhas[0].rstrip("\r\n").split(";")
    campos = linhas[1].rstrip("\r\n").split(";")
    campos[cabecalho.index("Gestor")] = "GESTORA FICTICIA, SOCIO 123.456.789-09"
    linhas[1] = ";".join(campos) + "\r\n"
    arquivos[ofertas.RESOLUCAO_160] = "".join(linhas).encode("latin-1")
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as novo:
        for nome, conteudo in arquivos.items():
            novo.writestr(nome, conteudo)
    novas = ofertas.ler_resolucao_160(saida.getvalue())
    assert pd.isna(novas["gestor"].iloc[0])
    assert not novas["gestor"].astype(str).str.contains(CPF).any()
