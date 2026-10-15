"""Montagem da rede no acervo (`scripts/montar_rede.py`; plano, tarefa 2.6). Sem internet.

Um acervo de mentira com o registro de coletas: o cadastro da CVM, uma página do GLEIF e a Receita
(Empresas e Simples) guardados como originais, e as tabelas de entrada gravadas com manifesto apontando
para um original registrado. Remontar dá o mesmo hash, e a linhagem chega aos originais.
"""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from base.linhagem import linhagem_da_tabela
from base.parquet import IGUAL, gravar_tabela
from scripts import montar_rede
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import com_registro
from src.banco.conexao import criar_engine, migrar_para
from tests.test_rede_montar import _entradas

VERSAO = "7b2d29a1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b2"
GLEIF = (Path(__file__).parent / "arquivos" / "gleif" / "pagina.json").read_bytes()
CADASTRO = (
    "CNPJ_CIA;DENOM_SOCIAL;DT_REG;DT_CANCEL;MOTIVO_CANCEL;SIT;SETOR_ATIV\n"
    "33.000.167/0001-01;PETROLEO BRASILEIRO S.A. PETROBRAS;1977-07-20;;;ATIVO;Petróleo\n"
)
RECEITA = "https://arquivos.receitafederal.gov.br/x/Dados/Cadastros/CNPJ/2026-10/"
FCA = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_2026.zip"


def _zip(nome: str, texto: str) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr(nome, texto.encode("latin-1"))
    return saida.getvalue()


ORIGINAIS = {
    (
        "cvm-cadastros",
        "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv",
    ): (CADASTRO.encode("latin-1")),
    ("gleif-br", "https://api.gleif.org/api/v1/lei-records?page=1"): GLEIF,
    ("rfb-cnpj", RECEITA + "Empresas0.zip"): _zip(
        "EMPRECSV", '"33000167";"PETROLEO";"2038";"10";"1,00";"05";""\n'
    ),
    ("rfb-cnpj", RECEITA + "Simples.zip"): _zip(
        "SIMPLES.CSV",
        '"44555666";"S";"20200101";"00000000";"S";"20200101";"00000000"\n',
    ),
    ("cvm-hist-fca", FCA): b"PK fca de mentira",
}


@pytest.fixture
def base(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    for (fonte, endereco), conteudo in ORIGINAIS.items():
        com_registro(fonte, lambda _endereco, c=conteudo: c)(endereco)
    pasta = tmp_path / "acervo" / "base"
    entradas = _entradas()
    origem = [
        {
            "url": FCA,
            "sha256": hashlib.sha256(ORIGINAIS[("cvm-hist-fca", FCA)]).hexdigest(),
        }
    ]
    for tabela, destino in (
        (entradas.tickers, pasta / "fca" / "tickers"),
        (entradas.emissores, pasta / "fca" / "emissores"),
        (entradas.controladas, pasta / "controladas" / "2026"),
        (entradas.empresa_serie, pasta / "empresa_serie" / "empresa_serie"),
        (entradas.fundos, pasta / "fidc" / "cadastro" / "cad_fi"),
        (entradas.ifdata, pasta / "bcb" / "ifdata" / "cadastro" / "202506"),
    ):
        gravar_tabela(tabela, destino, origem, [])
    return pasta


def _montar(pasta: Path) -> montar_rede.Resumo:
    motor = criar_engine()
    try:
        with motor.connect() as conexao:
            return montar_rede.montar_no_acervo(conexao, pasta)
    finally:
        motor.dispose()


def _manifesto(pasta: Path, tabela: str) -> dict:
    return json.loads((pasta / "rede" / f"{tabela}.json").read_text(encoding="utf-8"))


def test_monta_entidades_e_identificadores_com_natureza_da_receita(base):
    resumo = _montar(base)
    assert resumo.gravadas == {"entidades": "gravado", "identificadores": "gravado"}
    entidades = pd.read_parquet(base / "rede" / "entidades.parquet")
    assert resumo.entidades == len(entidades) > 0
    petrobras = entidades[
        entidades["nome"] == "PETROLEO BRASILEIRO S.A. PETROBRAS"
    ].iloc[0]
    assert petrobras["natureza_juridica"] == "2038"  # da Receita, não da fonte
    identificadores = pd.read_parquet(base / "rede" / "identificadores.parquet")
    assert "5493000J2N45DDNE4Y28" not in set(
        identificadores["valor"]
    )  # a página tem outros LEIs
    assert "LEI0000000000000RFB1" in set(
        identificadores["valor"]
    )  # o LEI da Petrobras de mentira


def test_remontar_da_o_mesmo_hash(base):
    _montar(base)
    antes = {
        t: _manifesto(base, t)["sha256_da_tabela"]
        for t in ("entidades", "identificadores")
    }
    de_novo = _montar(base)
    assert de_novo.gravadas == {"entidades": IGUAL, "identificadores": IGUAL}
    assert de_novo.entidades == _manifesto(base, "entidades")["linhas"]
    (base / "rede" / "entidades.json").unlink()  # obriga a montar de novo do zero
    (base / "rede" / "identificadores.json").unlink()
    _montar(base)
    depois = {
        t: _manifesto(base, t)["sha256_da_tabela"]
        for t in ("entidades", "identificadores")
    }
    assert depois == antes


def test_linha_volta_ao_original(base):
    """Exigência 13 da ADR 0055: das duas tabelas, chegar aos originais, à coleta e à versão."""
    _montar(base)
    motor = criar_engine()
    try:
        with motor.connect() as conexao:
            for tabela in ("entidades", "identificadores"):
                caminho = linhagem_da_tabela(
                    conexao, base / "rede" / f"{tabela}.parquet"
                )
                assert caminho.completa, tabela
                assert caminho.versao_do_codigo == VERSAO
                urls = {o.url for o in caminho.originais()}
                assert FCA in urls and RECEITA + "Simples.zip" in urls
                assert "base/conferidas/entidades.csv" in urls
    finally:
        motor.dispose()


def test_sem_a_versao_do_codigo_nao_monta(base, monkeypatch):
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError, match=vc.VARIAVEL):
        montar_rede.main(["--pasta", str(base)])
    assert not (base / "rede").exists()


def test_amostra_para_conferir(base, tmp_path):
    _montar(base)
    destino = tmp_path / "amostra.csv"
    montar_rede.gravar_amostra(base, destino)
    tabela = pd.read_csv(destino, sep=";", dtype=str, keep_default_na=False)
    assert {
        "regra",
        "id_entidade",
        "sistema",
        "valor",
        "tipo",
        "nome",
        "do_tiago",
    } <= set(tabela.columns)
    assert set(tabela["do_tiago"]) <= {"sim", "nao"}
    assert len(tabela) > 0
