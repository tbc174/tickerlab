"""Linhagem para auditoria (série 3 da base de ML, PR 1; ADR 0055, exigência 13): de qualquer linha
da base, chegar ao arquivo original, à data da coleta e à versão do código que a processou."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa

from base.linhagem import linhagem_da_linha
from base.ponto_no_tempo import gravar_parquet, montar_base
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para
from tests.test_base_ponto_no_tempo import _tres_publicacoes

URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_2022.zip"
ORIGINAL = b"PK\x03\x04 arquivo da CVM (recorte)"
BAIXADO_EM = datetime(2026, 10, 13, 0, 30, tzinfo=UTC)
VERSAO = "7ddaf09c1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b"


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Acervo e registro de coletas de mentira, com um original guardado e registrado."""
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    url_do_banco = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    migrar_para("head", url=url_do_banco)
    motor = criar_engine(url_do_banco)
    caminho = acervo.guardar_original("cvm-dfp-itr", URL, ORIGINAL, BAIXADO_EM)
    with motor.begin() as c:
        registrar(
            c,
            "cvm-dfp-itr",
            URL,
            ORIGINAL,
            "ok",
            agora=BAIXADO_EM,
            caminho_do_original=caminho,
        )
    origens = [{"url": URL, "sha256": hashlib.sha256(ORIGINAL).hexdigest()}]
    pasta = tmp_path / "base"
    gravar_parquet(montar_base(_tres_publicacoes()), pasta, origens=origens)
    yield motor, pasta
    motor.dispose()


def test_manifesto_do_ano_tem_a_versao_do_codigo(ambiente):
    _, pasta = ambiente
    manifesto = json.loads((pasta / "2022.json").read_text(encoding="utf-8"))
    assert manifesto["versao_do_codigo"] == VERSAO


def test_linha_sorteada_volta_ao_original(ambiente):
    motor, pasta = ambiente
    base = pd.concat(pd.read_parquet(p) for p in sorted(pasta.glob("*.parquet")))
    linha = base.sample(1, random_state=13).iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    assert caminho.versao_do_codigo == VERSAO
    assert caminho.base_confere  # o Parquet ainda tem o hash do manifesto
    [origem] = caminho.origens
    assert origem.url == URL
    assert origem.baixado_em.replace(tzinfo=None) == BAIXADO_EM.replace(tzinfo=None)
    assert origem.original_confere  # o arquivo no acervo tem o SHA-256 do registro
    assert caminho.completa


def test_original_mexido_no_acervo_quebra_a_linhagem(ambiente):
    motor, pasta = ambiente
    with motor.connect() as c:
        relativo = c.execute(
            sa.text("select caminho_do_original from coletas")
        ).scalar_one()
    (acervo.pasta_do_acervo() / relativo).write_bytes(b"outro conteudo")
    linha = pd.read_parquet(pasta / "2022.parquet").iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    assert not caminho.origens[0].original_confere and not caminho.completa


def test_origem_sem_coleta_registrada_quebra_a_linhagem(ambiente):
    motor, pasta = ambiente
    with motor.begin() as c:
        c.execute(sa.text("delete from coletas"))
    linha = pd.read_parquet(pasta / "2022.parquet").iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    assert caminho.origens[0].baixado_em is None and not caminho.completa


def test_manifesto_antigo_sem_versao_nao_e_linhagem_completa(ambiente):
    """Os Parquet da série 1 foram gravados antes da exigência 13: a linhagem diz que falta."""
    motor, pasta = ambiente
    manifesto = pasta / "2022.json"
    dados = json.loads(manifesto.read_text(encoding="utf-8"))
    del dados["versao_do_codigo"]
    manifesto.write_text(json.dumps(dados), encoding="utf-8")
    linha = pd.read_parquet(pasta / "2022.parquet").iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    assert caminho.versao_do_codigo is None and not caminho.completa


def _com_a_tabela_conferida(pasta, sha256: str) -> None:
    manifesto = pasta / "2022.json"
    dados = json.loads(manifesto.read_text(encoding="utf-8"))
    dados["origens"].append(
        {"url": "base/conferidas/codigos_fora_do_fca.csv", "sha256": sha256}
    )
    manifesto.write_text(json.dumps(dados), encoding="utf-8")


def test_tabela_conferida_do_repositorio_e_origem_valida(ambiente):
    """Série 3, PR 8: a tabela conferida à mão não tem coleta; o elo é o arquivo no repositório com
    o mesmo SHA-256 (cada linha dela diz a fonte e quando foi conferida)."""
    from base.fca import CODIGOS_CONFERIDOS

    motor, pasta = ambiente
    _com_a_tabela_conferida(
        pasta, hashlib.sha256(CODIGOS_CONFERIDOS.read_bytes()).hexdigest()
    )
    linha = pd.read_parquet(pasta / "2022.parquet").iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    conferida = caminho.origens[-1]
    assert conferida.no_repositorio and conferida.original_confere
    assert caminho.completa


def test_tabela_conferida_mudada_depois_quebra_a_linhagem(ambiente):
    """A tabela mudou depois da carga: a base precisa ser remontada (a versão antiga está no Git)."""
    motor, pasta = ambiente
    _com_a_tabela_conferida(pasta, "0" * 64)
    linha = pd.read_parquet(pasta / "2022.parquet").iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    assert not caminho.origens[-1].original_confere and not caminho.completa


def test_endereco_que_sai_da_pasta_das_conferidas_nao_confere(ambiente):
    motor, pasta = ambiente
    manifesto = pasta / "2022.json"
    dados = json.loads(manifesto.read_text(encoding="utf-8"))
    alvo = "base/conferidas/../../README.md"
    conteudo = (Path(__file__).resolve().parent.parent / "README.md").read_bytes()
    dados["origens"].append(
        {"url": alvo, "sha256": hashlib.sha256(conteudo).hexdigest()}
    )
    manifesto.write_text(json.dumps(dados), encoding="utf-8")
    linha = pd.read_parquet(pasta / "2022.parquet").iloc[0]
    with motor.connect() as c:
        caminho = linhagem_da_linha(c, pasta, linha)
    assert not caminho.origens[-1].original_confere and not caminho.completa
