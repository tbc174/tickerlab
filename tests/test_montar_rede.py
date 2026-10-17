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
from tests.test_rede_ligacoes_das_fontes import _auditores, _posicoes
from tests.test_rede_montar import _entradas

VERSAO = "7b2d29a1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b2"
GLEIF = (Path(__file__).parent / "arquivos" / "gleif" / "pagina.json").read_bytes()
CADASTRO = (
    "CNPJ_CIA;DENOM_SOCIAL;DT_REG;DT_CANCEL;MOTIVO_CANCEL;SIT;SETOR_ATIV\n"
    "33.000.167/0001-01;PETROLEO BRASILEIRO S.A. PETROBRAS;1977-07-20;;;ATIVO;Petróleo\n"
)
RECEITA = "https://arquivos.receitafederal.gov.br/x/Dados/Cadastros/CNPJ/2026-10/"
FCA = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_2026.zip"
TABELAS_DA_REDE = ("entidades", "identificadores", "ligacoes")


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
        (entradas.fundos, pasta / "fidc" / "cadastro" / "cad_fi"),
        (entradas.ifdata, pasta / "bcb" / "ifdata" / "cadastro" / "202506"),
    ):
        gravar_tabela(tabela, destino, origem, [])
    # como no servidor: as históricas da série B não têm manifesto, a origem vai em cada linha
    for tabela, destino in (
        (entradas.controladas, pasta / "controladas" / "2026.parquet"),
        (entradas.empresa_serie, pasta / "empresa_serie" / "empresa_serie.parquet"),
    ):
        destino.parent.mkdir(parents=True, exist_ok=True)
        tabela.assign(origem_sha256=origem[0]["sha256"]).to_parquet(
            destino, index=False
        )
    # os auditores levam a origem em cada linha; as carteiras, no manifesto do ano
    destino = pasta / "auditores" / "2022.parquet"
    destino.parent.mkdir(parents=True, exist_ok=True)
    _auditores().assign(origem_sha256=origem[0]["sha256"]).to_parquet(
        destino, index=False
    )
    gravar_tabela(
        _posicoes().drop(columns="origem_sha256"), pasta / "cda" / "2021", origem, []
    )
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
    assert resumo.gravadas == dict.fromkeys(TABELAS_DA_REDE, "gravado")
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
    antes = {t: _manifesto(base, t)["sha256_da_tabela"] for t in TABELAS_DA_REDE}
    de_novo = _montar(base)
    assert de_novo.gravadas == dict.fromkeys(TABELAS_DA_REDE, IGUAL)
    assert de_novo.entidades == _manifesto(base, "entidades")["linhas"]
    (base / "rede" / "entidades.json").unlink()  # obriga a montar de novo do zero
    (base / "rede" / "identificadores.json").unlink()
    (base / "rede" / "ligacoes.json").unlink()
    (base / "rede" / "ligacoes.parquet").unlink()
    _montar(base)
    depois = {t: _manifesto(base, t)["sha256_da_tabela"] for t in TABELAS_DA_REDE}
    assert depois == antes


def test_linha_volta_ao_original(base):
    """Exigência 13 da ADR 0055: das duas tabelas, chegar aos originais, à coleta e à versão."""
    _montar(base)
    motor = criar_engine()
    try:
        with motor.connect() as conexao:
            for tabela in TABELAS_DA_REDE:
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
    montar_rede.gravar_amostra(base / "rede", destino)
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


def test_ensaio_grava_fora_da_base(base, tmp_path):
    motor = criar_engine()
    try:
        with motor.connect() as conexao:
            montar_rede.montar_no_acervo(conexao, base, tmp_path / "ensaio")
    finally:
        motor.dispose()
    assert (tmp_path / "ensaio" / "entidades.parquet").is_file()
    assert not (base / "rede").exists()


def test_tabelas_conferidas_vem_do_pacote_base():
    """Na imagem o script roda por `python - < scripts/montar_rede.py` (sem `__file__` útil)."""
    from base.rede import ids

    assert ids.TABELA_CONFERIDA.parent == montar_rede.CONFERIDAS
    assert (montar_rede.CONFERIDAS / "emissores_antigos.csv").is_file()


def _ligacoes(pasta: Path) -> pd.DataFrame:
    return pd.read_parquet(pasta / "rede" / "ligacoes.parquet")


def test_ligacoes_de_todas_as_fontes_com_coletado_em(base):
    resumo = _montar(base)
    tabela = _ligacoes(base)
    assert resumo.ligacoes == len(tabela)
    assert {"controlada_de", "opera_para", "audita", "emite", "detem"} <= set(
        tabela["tipo"]
    )
    # o original do FCA foi guardado hoje (no teste): é o `coletado_em` das linhas que vêm dele
    assert tabela["coletado_em"].notna().all()
    assert set(tabela["situacao"]) <= {"vigente", "encerrada"}


def test_segunda_carga_nao_apaga_e_guarda_a_versao(base):
    """A posição que some do CDA fica, encerrada pela carga; a carga anterior fica como `.v1`."""
    _montar(base)
    origem = json.loads((base / "cda" / "2021.json").read_text(encoding="utf-8"))[
        "origens"
    ]
    # a PETR4 de maio (o período que estava vigente) some do CDA
    sem_maio = _posicoes().drop(columns="origem_sha256").iloc[[0, 1, 2, 4]]
    gravar_tabela(sem_maio, base / "cda" / "2021", origem, [])
    motor = criar_engine()
    try:
        with motor.connect() as conexao:
            montar_rede.montar_no_acervo(conexao, base, hoje=pd.Timestamp("2026-10-17"))
    finally:
        motor.dispose()
    tabela = _ligacoes(base)
    sumiu = tabela[(tabela["tipo"] == "detem") & (tabela["situacao"] == "encerrada")]
    assert (sumiu["encerrada_por"] == "carga").any()
    assert pd.Timestamp("2026-10-17") in set(sumiu["ate"])
    assert (base / "rede" / "ligacoes.v1.parquet").is_file()
    assert len(tabela) >= len(pd.read_parquet(base / "rede" / "ligacoes.v1.parquet"))


def test_forcar_refaz_com_as_mesmas_origens(base):
    """Corrigir o código não refaz o que já está gravado (lição do #333): a rede de antes do
    `ate_publico_em` (#373) fica igual sem `--forcar` e ganha a coluna com ele."""
    _montar(base)
    antiga = _ligacoes(base).drop(columns="ate_publico_em")
    origens = _manifesto(base, "ligacoes")["origens"]
    gravar_tabela(
        antiga, base / "rede" / "ligacoes", origens, montar_rede.ORDEM_DAS_LIGACOES
    )
    assert montar_rede.main(["--pasta", str(base)]) == 0
    assert "ate_publico_em" not in _ligacoes(base).columns
    assert montar_rede.main(["--pasta", str(base), "--forcar"]) == 0
    assert "ate_publico_em" in _ligacoes(base).columns
    assert (base / "rede" / "ligacoes.v1.parquet").is_file()  # a antiga fica guardada


def test_montar_rede_sem_entradas_nao_grava(tmp_path, base, capsys):
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    assert montar_rede.main(["--pasta", str(vazia)]) == 1
    assert capsys.readouterr().out.strip().startswith("FALHAS: rede: SemEntradasError")
    assert not (vazia / "rede").exists()


def test_montar_rede_devolve_codigo_para_o_kuma(base, capsys, monkeypatch):
    assert montar_rede.main(["--pasta", str(base)]) == 0
    assert "FALHAS" not in capsys.readouterr().out

    def quebra(*_args, **_kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(montar_rede, "gravar_com_versoes", quebra)
    (base / "rede" / "entidades.json").unlink()
    assert montar_rede.main(["--pasta", str(base)]) == 1
    saida = capsys.readouterr().out.strip().splitlines()[-1]
    assert saida == "FALHAS: rede: OSError: disco cheio"
    assert len(saida) <= montar_rede.TAMANHO_MAXIMO_DO_RESUMO
