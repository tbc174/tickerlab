"""Carga do CDA para a base (série 3 da base de ML, PR 4): um Parquet por ano com manifesto, o
"como era na data" de cada posição, ano repetido pulado e arquivo regravado pela CVM guardado como
versão, sem apagar a anterior. Sem internet."""

import json
from pathlib import Path

import pandas as pd
import pytest

from base.parquet import conferir_tabela
from scripts import carga_cda
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import com_registro
from src.banco.conexao import criar_engine, migrar_para

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "cda"
VERSAO = "3af11e4c1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b"


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    arquivos = {p.name: p.read_bytes() for p in PASTA.glob("*.zip")}
    pedidos: list[str] = []

    def baixar_falso(endereco: str) -> bytes | None:
        pedidos.append(endereco)
        return arquivos.get(endereco.rsplit("/", 1)[-1])  # o resto: 404

    monkeypatch.setattr(
        carga_cda, "baixar", com_registro(carga_cda.FONTE, baixar_falso)
    )
    return tmp_path / "base" / "cda", arquivos, pedidos


def test_ano_historico_e_ano_mensal_viram_parquet_com_manifesto(ambiente):
    pasta, _, _ = ambiente
    assert (
        carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"]) == 0
    )
    assert (
        carga_cda.main(["--pasta", str(pasta), "--desde", "2025", "--ate", "2025"]) == 0
    )
    for ano, competencias in (("2005", {"2005-01", "2005-02"}), ("2025", {"2025-09"})):
        arquivo = pasta / f"{ano}.parquet"
        assert conferir_tabela(arquivo)
        tabela = pd.read_parquet(arquivo)
        assert set(tabela["competencia"].dt.strftime("%Y-%m")) == competencias
        assert (
            tabela["disponivel_em"] >= tabela["competencia"] + pd.Timedelta(days=90)
        ).all()
        manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
        assert manifesto["versao_do_codigo"] == VERSAO and manifesto["origens"]


def test_ano_igual_ao_que_ja_tem_e_pulado(ambiente):
    pasta, _, pedidos = ambiente
    carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"])
    antes = (pasta / "2005.json").read_text(encoding="utf-8")
    carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"])
    assert (pasta / "2005.json").read_text(encoding="utf-8") == antes
    assert sum("cda_fi_2005" in p for p in pedidos) == 1  # a 2ª vez leu do acervo


def test_arquivo_regravado_vira_versao_nova_sem_apagar(ambiente, monkeypatch):
    """A CVM regrava anos antigos: o Parquet anterior fica como `2005.v1` e o novo entra no lugar."""
    pasta, arquivos, _ = ambiente
    carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"])
    primeiro = pd.read_parquet(pasta / "2005.parquet")
    regravado = PASTA.joinpath(
        "cda_fi_2014.zip"
    ).read_bytes()  # outro conteúdo no mesmo endereço
    monkeypatch.setattr(
        carga_cda, "original_mais_recente", lambda conexao, url: None
    )  # a CVM mudou o arquivo
    arquivos["cda_fi_2005.zip"] = regravado
    carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"])
    assert conferir_tabela(pasta / "2005.v1.parquet")
    pd.testing.assert_frame_equal(pd.read_parquet(pasta / "2005.v1.parquet"), primeiro)
    assert not pd.read_parquet(pasta / "2005.parquet").equals(primeiro)


def test_sem_a_versao_do_codigo_nao_grava(ambiente, monkeypatch):
    pasta, _, _ = ambiente
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError, match=vc.VARIAVEL):
        carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"])
    assert not pasta.exists()


def test_linhagem_do_ano_e_completa(ambiente):
    """Exigência 13 da ADR 0055: do Parquet do ano ao arquivo do CDA, à coleta e à versão."""
    from base.linhagem import linhagem_da_tabela
    from src.banco.conexao import criar_engine

    pasta, _, _ = ambiente
    carga_cda.main(["--pasta", str(pasta), "--desde", "2025", "--ate", "2025"])
    motor = criar_engine()
    try:
        with motor.connect() as c:
            assert linhagem_da_tabela(c, pasta / "2025.parquet").completa
    finally:
        motor.dispose()


def test_ano_grava_tambem_as_acoes_do_bloco_8(ambiente):
    """Achado da série 4: as ações que os fundos informam no bloco 8 vão para `cda_bloco_8/<ano>`,
    ao lado do CDA, com manifesto, "como era na data" e linhagem até o arquivo da CVM."""
    from base.linhagem import linhagem_da_tabela
    from src.banco.conexao import criar_engine

    pasta, _, _ = ambiente
    assert (
        carga_cda.main(["--pasta", str(pasta), "--desde", "2016", "--ate", "2016"]) == 0
    )
    arquivo = pasta.parent / "cda_bloco_8" / "2016.parquet"
    assert conferir_tabela(arquivo)
    tabela = pd.read_parquet(arquivo)
    assert set(tabela["cnpj_emissor"]) == {"33.000.167/0001-01"}
    assert (
        tabela["disponivel_em"] >= tabela["competencia"] + pd.Timedelta(days=90)
    ).all()
    motor = criar_engine()
    try:
        with motor.connect() as c:
            assert linhagem_da_tabela(c, arquivo).completa
    finally:
        motor.dispose()
    # ano sem o bloco 8 no arquivo: tabela vazia, com as colunas
    carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"])
    vazio = pd.read_parquet(pasta.parent / "cda_bloco_8" / "2005.parquet")
    assert vazio.empty and "cnpj_emissor" in vazio.columns


def test_carteira_entregue_depois_so_vale_do_dia_em_que_apareceu(ambiente):
    """Relatório de cruzamentos 7 (16/10/2026): o prazo de 90 dias não é a data em que a carteira
    apareceu; quem entrega depois do prazo só vale do dia em que foi visto."""
    import io
    import zipfile
    from datetime import UTC, datetime

    from base import cda
    from src.banco.coletas import registrar

    pasta, arquivos, _ = ambiente
    url = carga_cda.PASTA_DA_CVM + "cda_fi_202509.zip"
    completo = arquivos["cda_fi_202509.zip"]
    atrasado = next(cda.ler_posicoes_historicas(completo))["cnpj_fundo"].iloc[-1]
    saida = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(completo)) as entrada,
        zipfile.ZipFile(saida, "w") as nova,
    ):
        for nome in entrada.namelist():
            linhas = entrada.read(nome).decode("latin-1").splitlines(keepends=True)
            nova.writestr(
                nome,
                "".join(
                    linhas[:1] + [x for x in linhas[1:] if atrasado not in x]
                ).encode("latin-1"),
            )
    motor = criar_engine()
    try:
        for conteudo, quando in (
            (saida.getvalue(), datetime(2025, 10, 20, 5, tzinfo=UTC)),
            (completo, datetime(2026, 2, 10, 5, tzinfo=UTC)),
        ):
            caminho = acervo.guardar_original("cvm-cda-recente", url, conteudo, quando)
            with motor.begin() as c:
                registrar(
                    c, "cvm-cda-recente", url, conteudo, "ok", None, quando, caminho
                )
    finally:
        motor.dispose()

    carga_cda.main(["--pasta", str(pasta), "--desde", "2025", "--ate", "2025"])

    for arquivo in (
        pasta / "2025.parquet",
        pasta.parent / "cda_bloco_8" / "2025.parquet",
    ):
        tabela = pd.read_parquet(arquivo)
        assert "visto_em" in tabela.columns, arquivo
    tabela = pd.read_parquet(pasta / "2025.parquet")
    tarde = tabela["cnpj_fundo"] == atrasado
    assert tarde.any() and (~tarde).any()
    assert (tabela.loc[tarde, "visto_em"] == pd.Timestamp("2026-02-10")).all()
    assert (tabela.loc[tarde, "disponivel_em"] >= pd.Timestamp("2026-02-10")).all()
    assert tabela.loc[~tarde, "visto_em"].isna().all()  # já na 1ª versão: vale o prazo
    no_prazo = tabela.loc[~tarde]
    assert no_prazo["disponivel_em"].tolist() == cda.disponivel_em(no_prazo).tolist()


def test_refazer_regrava_o_cda_com_as_mesmas_origens(ambiente, monkeypatch):
    pasta, _, _ = ambiente
    carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"])
    antiga = pd.read_parquet(pasta / "2005.parquet")
    original = carga_cda.cda.disponivel_em
    monkeypatch.setattr(
        carga_cda.cda, "disponivel_em", lambda t: original(t) + pd.Timedelta(days=1)
    )
    carga_cda.main(
        ["--pasta", str(pasta), "--desde", "2005", "--ate", "2005", "--refazer"]
    )
    assert not pd.read_parquet(pasta / "2005.parquet").equals(antiga)
    assert (pasta / "2005.v1.parquet").exists()
