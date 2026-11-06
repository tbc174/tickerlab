"""Carga do FIDC e do cadastro de fundos para a base (série 3 da base de ML, PR 6). Sem internet."""

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from base.parquet import conferir_tabela
from scripts import carga_fidc
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import com_registro
from src.banco.conexao import migrar_para
from tests.test_base_fidc import CADASTRO

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fidc"
VERSAO = "7b2d29a1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b2"


def _historico() -> bytes:
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        arquivo.writestr(
            "cad_fi_hist_admin.csv",
            "CNPJ_FUNDO;DT_REG;CNPJ_ADMIN;ADMIN;DT_INI_ADMIN;DT_FIM_ADMIN\n"
            "11.111.111/0001-11;2010-01-01;22.222.222/0001-22;ADMIN A;2010-01-01;\n",
        )
        arquivo.writestr(
            "cad_fi_hist_diretor_resp.csv", "CNPJ_FUNDO;DIRETOR\n1;FULANO\n"
        )
    return conteudo.getvalue()


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    arquivos = {p.name: p.read_bytes() for p in PASTA.glob("*.zip")}
    arquivos["cad_fi.csv"] = CADASTRO.encode("latin-1")
    arquivos["cad_fi_hist.zip"] = _historico()

    def baixar_falso(endereco: str) -> bytes | None:
        return arquivos.get(endereco.rsplit("/", 1)[-1])  # o resto: 404

    monkeypatch.setattr(
        carga_fidc, "baixar", com_registro(carga_fidc.FONTE, baixar_falso)
    )
    return tmp_path / "base" / "fidc"


def test_informe_vira_uma_tabela_por_quadro_e_ano(ambiente):
    pasta = ambiente
    assert (
        carga_fidc.main(["--pasta", str(pasta), "--desde", "2013", "--ate", "2013"])
        == 0
    )
    assert (
        carga_fidc.main(["--pasta", str(pasta), "--desde", "2026", "--ate", "2026"])
        == 0
    )
    for quadro in ("tab_I", "tab_IV", "tab_X_1"):
        for ano in (2013, 2026):
            arquivo = pasta / "informe" / quadro / f"{ano}.parquet"
            assert conferir_tabela(arquivo), arquivo
            tabela = pd.read_parquet(arquivo)
            assert (tabela["disponivel_em"] > tabela["competencia"]).all()


def test_cadastro_entra_sem_dado_pessoal(ambiente):
    pasta = ambiente
    carga_fidc.main(["--pasta", str(pasta), "--desde", "2013", "--ate", "2013"])
    cadastro = pd.read_parquet(pasta / "cadastro" / "cad_fi.parquet")
    assert "DIRETOR" not in cadastro.columns and cadastro["GESTOR"].isna().sum() == 1
    assert (pasta / "cadastro" / "hist_admin.parquet").exists()
    assert not (pasta / "cadastro" / "hist_diretor_resp.parquet").exists()


def test_sem_a_versao_do_codigo_nao_grava(ambiente, monkeypatch):
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError, match=vc.VARIAVEL):
        carga_fidc.main(["--pasta", str(ambiente)])
    assert not ambiente.exists()


def test_carga_repetida_da_o_mesmo_resultado(ambiente):
    """Exigência 9 da ADR 0027 (série 3, PR 8): refazer a partir dos mesmos originais não muda nada."""
    import json

    pasta = ambiente
    carga_fidc.main(["--pasta", str(pasta), "--desde", "2019", "--ate", "2019"])
    manifesto = pasta / "informe" / "tab_I" / "2019.json"
    antes = json.loads(manifesto.read_text(encoding="utf-8"))
    carga_fidc.main(["--pasta", str(pasta), "--desde", "2019", "--ate", "2019"])
    assert json.loads(manifesto.read_text(encoding="utf-8")) == antes
    assert not list((pasta / "informe" / "tab_I").glob("2019.v*"))


def test_linhagem_do_informe_e_do_cadastro_e_completa(ambiente):
    """Exigência 13 da ADR 0055 (série 3, PR 8): de cada tabela, chegar ao original, à coleta e à
    versão do código."""
    from base.linhagem import linhagem_da_tabela
    from src.banco.conexao import criar_engine

    pasta = ambiente
    carga_fidc.main(["--pasta", str(pasta), "--desde", "2013", "--ate", "2013"])
    motor = criar_engine()
    try:
        with motor.connect() as c:
            for arquivo in (
                pasta / "informe" / "tab_I" / "2013.parquet",
                pasta / "cadastro" / "cad_fi.parquet",
                pasta / "cadastro" / "hist_admin.parquet",
            ):
                caminho = linhagem_da_tabela(c, arquivo)
                assert caminho.completa, arquivo
                assert caminho.versao_do_codigo == VERSAO
    finally:
        motor.dispose()


def _guardar(url: str, conteudo: bytes | None, quando) -> None:
    """Uma coleta do arquivista num dia escolhido (None: a CVM respondeu 404)."""
    from src.banco.coletas import registrar
    from src.banco.conexao import criar_engine

    caminho = (
        None
        if conteudo is None
        else acervo.guardar_original("cvm-fidc-recente", url, conteudo, quando)
    )
    situacao = "nao_encontrado" if conteudo is None else "ok"
    motor = criar_engine()
    try:
        with motor.begin() as c:
            registrar(
                c, "cvm-fidc-recente", url, conteudo, situacao, None, quando, caminho
            )
    finally:
        motor.dispose()


def _sem_o_fundo(conteudo: bytes, cnpj: str) -> bytes:
    """O mesmo arquivo sem as linhas de um fundo (a versão de antes de ele entregar)."""
    saida = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(conteudo)) as entrada,
        zipfile.ZipFile(saida, "w") as nova,
    ):
        for nome in entrada.namelist():
            linhas = entrada.read(nome).decode("latin-1").splitlines(keepends=True)
            nova.writestr(
                nome,
                "".join(linhas[:1] + [x for x in linhas[1:] if cnpj not in x]).encode(
                    "latin-1"
                ),
            )
    return saida.getvalue()


def test_informe_entregue_depois_so_vale_do_dia_em_que_apareceu(ambiente):
    """Relatórios de cruzamentos 5 e 7 (16/10/2026): o prazo não é a data em que o dado apareceu."""
    from datetime import UTC, datetime

    from base import fidc

    pasta = ambiente
    url = carga_fidc.PASTA_DO_INFORME + "inf_mensal_fidc_202608.zip"
    completo = (PASTA / "inf_mensal_fidc_202608.zip").read_bytes()
    fundos = fidc.chaves_do_informe(completo)["cnpj_fundo"]
    atrasado = fundos.iloc[-1]
    _guardar(
        url, None, datetime(2026, 9, 2, 5, 0, tzinfo=UTC)
    )  # o mês ainda não tinha saído
    _guardar(
        url, _sem_o_fundo(completo, atrasado), datetime(2026, 9, 20, 5, 0, tzinfo=UTC)
    )
    _guardar(url, completo, datetime(2026, 11, 20, 5, 0, tzinfo=UTC))

    carga_fidc.main(["--pasta", str(pasta), "--desde", "2026", "--ate", "2026"])

    for quadro in ("tab_I", "tab_IV"):
        tabela = pd.read_parquet(pasta / "informe" / quadro / "2026.parquet")
        agosto = tabela[tabela["competencia"] == pd.Timestamp("2026-08-31")]
        tarde = agosto["cnpj_fundo"] == atrasado
        assert (agosto.loc[tarde, "visto_em"] == pd.Timestamp("2026-11-20")).all()
        assert (agosto.loc[tarde, "disponivel_em"] == pd.Timestamp("2026-11-20")).all()
        assert (agosto.loc[~tarde, "visto_em"] == pd.Timestamp("2026-09-20")).all()
        assert (
            agosto.loc[~tarde, "disponivel_em"] == pd.Timestamp("2026-10-15")
        ).all()  # o piso
    manifesto = json.loads(
        (pasta / "informe" / "tab_I" / "2026.json").read_text(encoding="utf-8")
    )
    assert [o["url"] for o in manifesto["origens"]].count(
        url
    ) == 2  # as duas versões usadas


def test_passado_sem_data_vista_fica_com_o_prazo(ambiente):
    pasta = ambiente
    carga_fidc.main(["--pasta", str(pasta), "--desde", "2019", "--ate", "2019"])
    tabela = pd.read_parquet(pasta / "informe" / "tab_I" / "2019.parquet")
    assert tabela["visto_em"].isna().all()
    assert (
        tabela["disponivel_em"] == tabela["competencia"] + pd.Timedelta(days=45)
    ).all()


def test_refazer_regrava_com_as_mesmas_origens(ambiente, monkeypatch):
    """Corrigir o leitor não refaz o que já está gravado com as mesmas origens (lição do #333)."""
    pasta = ambiente
    carga_fidc.main(["--pasta", str(pasta), "--desde", "2019", "--ate", "2019"])
    arquivo = pasta / "informe" / "tab_I" / "2019.parquet"
    antiga = pd.read_parquet(arquivo)
    original = carga_fidc.fidc.disponivel_em
    monkeypatch.setattr(
        carga_fidc.fidc, "disponivel_em", lambda t: original(t) + pd.Timedelta(days=1)
    )
    carga_fidc.main(["--pasta", str(pasta), "--desde", "2019", "--ate", "2019"])
    assert pd.read_parquet(arquivo).equals(antiga)  # mesmas origens: nem leu
    carga_fidc.main(
        ["--pasta", str(pasta), "--desde", "2019", "--ate", "2019", "--refazer"]
    )
    assert not pd.read_parquet(arquivo).equals(antiga)
    pd.testing.assert_frame_equal(
        pd.read_parquet(arquivo.with_name("2019.v1.parquet")), antiga
    )
