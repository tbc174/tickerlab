"""Carga do IF.data e do SCR.data para a base (série 3 da base de ML, PR 7). Sem internet."""

import json
from pathlib import Path

import pandas as pd
import pytest

from base.parquet import conferir_tabela, gravar_tabela
from scripts import carga_bcb_credito as carga
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import com_registro
from src.banco.conexao import migrar_para
from tests.test_base_bcb import ITAU, _empresas_e_tickers

PASTA = Path(__file__).parent / "arquivos" / "bcb"
VERSAO = "c4e1f00d9e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b"
VAZIO = json.dumps({"@odata.context": "x", "value": []}).encode()


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    monkeypatch.setattr(carga, "PAUSA_IFDATA", 0)
    monkeypatch.setattr(carga, "PAUSA_SCR", 0)
    migrar_para("head", url=url)
    respostas = {
        "@AnoMes=202506&@TipoInstituicao=1&@Relatorio='1'": (
            PASTA / "ifdata" / "valores_202506_t1_r1.json"
        ).read_bytes(),
        "IfDataCadastro(AnoMes=@AnoMes)?@AnoMes=202506": (
            PASTA / "ifdata" / "cadastro_202506.json"
        ).read_bytes(),
        "scrdata_2012.zip": (PASTA / "scr" / "scrdata_2012.zip").read_bytes(),
    }
    pedidos: list[str] = []

    def baixar_falso(endereco: str) -> bytes | None:
        pedidos.append(endereco)
        for pedaco, conteudo in respostas.items():
            if pedaco in endereco:
                return conteudo
        return VAZIO if "olinda" in endereco else None  # IF.data vazio; SCR: 404

    monkeypatch.setattr(
        carga, "baixar_ifdata", com_registro(carga.FONTE_IFDATA, baixar_falso)
    )
    monkeypatch.setattr(
        carga, "baixar_scr", com_registro(carga.FONTE_SCR, baixar_falso)
    )
    fca = tmp_path / "acervo" / "base" / "fca"
    empresas, tickers = _empresas_e_tickers()
    gravar_tabela(empresas, fca / "emissores", [], ["emissor"])
    gravar_tabela(tickers, fca / "tickers", [], ["codigo"])
    return tmp_path / "base" / "bcb", respostas, pedidos


def _rodar(pasta: Path, *opcoes: str) -> int:
    return carga.main(["--pasta", str(pasta), *opcoes])


def test_ifdata_grava_valores_cadastro_e_ligacao(ambiente):
    pasta, _, pedidos = ambiente
    assert _rodar(pasta, "--so", "ifdata", "--desde", "2025", "--ate", "2025") == 0
    valores = pasta / "ifdata" / "valores" / "tipo_1" / "202506.parquet"
    assert conferir_tabela(valores)
    tabela = pd.read_parquet(valores)
    assert (tabela["disponivel_em"] > tabela["data_base"]).all()
    # as datas sem resposta (2025-03, -09, -12 e os outros tipos) não viram arquivo
    assert sorted(
        p.name for p in (pasta / "ifdata" / "valores").rglob("*.parquet")
    ) == ["202506.parquet"]
    assert conferir_tabela(pasta / "ifdata" / "cadastro" / "202506.parquet")
    ligacao = pd.read_parquet(pasta / "ifdata" / "ligacao_dos_bancos.parquet")
    assert ligacao.set_index("cod_inst").loc[ITAU, "tickers"] == "ITUB3,ITUB4"
    # câmbio (relatório 15) nunca é pedido
    assert not [p for p in pedidos if "@Relatorio='15'" in p]


def test_revisao_do_bc_vira_versao(ambiente):
    pasta, respostas, _ = ambiente
    _rodar(pasta, "--so", "ifdata", "--desde", "2025", "--ate", "2025")
    destino = pasta / "ifdata" / "valores" / "tipo_1"
    manifesto = json.loads((destino / "202506.json").read_text(encoding="utf-8"))

    # sem mudança no BC: nada é regravado
    _rodar(pasta, "--so", "ifdata", "--desde", "2025", "--ate", "2025")
    assert (
        json.loads((destino / "202506.json").read_text(encoding="utf-8")) == manifesto
    )
    assert not list(destino.glob("202506.v*"))

    # o BC revisa o ativo do Itaú: a versão anterior fica guardada e a nova entra
    chave = "@AnoMes=202506&@TipoInstituicao=1&@Relatorio='1'"
    resposta = json.loads(respostas[chave])
    for linha in resposta["value"]:
        if linha["CodInst"] == ITAU and linha["NomeColuna"] == "Ativo Total":
            linha["Saldo"] = 1.0
    respostas[chave] = json.dumps(resposta).encode()
    _rodar(pasta, "--so", "ifdata", "--desde", "2025", "--ate", "2025")
    assert list(destino.glob("202506.v1.*"))
    nova = pd.read_parquet(destino / "202506.parquet")
    itau = nova[(nova["cod_inst"] == ITAU) & (nova["coluna"] == "Ativo Total")]
    assert itau["saldo"].iloc[0] == 1.0


def test_scr_grava_um_parquet_por_ano(ambiente):
    pasta, _, _ = ambiente
    assert _rodar(pasta, "--so", "scr", "--desde", "2012", "--ate", "2013") == 0
    arquivo = pasta / "scr" / "2012.parquet"
    assert conferir_tabela(arquivo)
    tabela = pd.read_parquet(arquivo)
    assert len(tabela) == 480
    assert (
        tabela["disponivel_em"] - tabela["data_base"] == pd.Timedelta(days=60)
    ).all()
    assert not (pasta / "scr" / "2013.parquet").exists()  # 404: pulado


def test_recusa_rodar_sem_a_versao_do_codigo(ambiente, monkeypatch):
    pasta, _, _ = ambiente
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError, match=vc.VARIAVEL):
        _rodar(pasta, "--so", "scr")
    assert not pasta.exists()


def test_linhagem_do_ifdata_e_do_scr_e_completa(ambiente):
    """Exigência 13 da ADR 0055 (série 3, PR 8): de cada tabela do BC, chegar à resposta original,
    à data da coleta e à versão do código."""
    from base.linhagem import linhagem_da_tabela
    from src.banco.conexao import criar_engine

    pasta, _, _ = ambiente
    _rodar(pasta, "--so", "ifdata", "--desde", "2025", "--ate", "2025")
    _rodar(pasta, "--so", "scr", "--desde", "2012", "--ate", "2012")
    motor = criar_engine()
    try:
        with motor.connect() as c:
            for arquivo in (
                pasta / "ifdata" / "valores" / "tipo_1" / "202506.parquet",
                pasta / "ifdata" / "cadastro" / "202506.parquet",
                pasta / "scr" / "2012.parquet",
            ):
                caminho = linhagem_da_tabela(c, arquivo)
                assert caminho.completa, arquivo
                assert caminho.versao_do_codigo == VERSAO
    finally:
        motor.dispose()


def test_scr_repetido_da_o_mesmo_resultado(ambiente):
    """Exigência 9 da ADR 0027 (série 3, PR 8): os mesmos originais dão a mesma tabela."""
    pasta, _, _ = ambiente
    _rodar(pasta, "--so", "scr", "--desde", "2012", "--ate", "2012")
    manifesto = pasta / "scr" / "2012.json"
    antes = json.loads(manifesto.read_text(encoding="utf-8"))
    _rodar(pasta, "--so", "scr", "--desde", "2012", "--ate", "2012")
    assert json.loads(manifesto.read_text(encoding="utf-8")) == antes
    assert not list((pasta / "scr").glob("2012.v*"))


def test_ligacao_nao_le_as_versoes_anteriores_do_cadastro(ambiente):
    """Achado no fechamento da série 3: a ligação lia `202506.v1.parquet` junto com o cadastro atual
    e duplicava as instituições da data-base."""
    pasta, _, _ = ambiente
    _rodar(pasta, "--so", "ifdata", "--desde", "2025", "--ate", "2025")
    cadastro = pasta / "ifdata" / "cadastro"
    for extensao in (".parquet", ".json"):
        (cadastro / f"202506.v1{extensao}").write_bytes(
            (cadastro / f"202506{extensao}").read_bytes()
        )
    carga.montar_ligacao(pasta, pasta.parent.parent / "acervo" / "base" / "fca")
    ligacao = pd.read_parquet(pasta / "ifdata" / "ligacao_dos_bancos.parquet")
    assert not ligacao.duplicated(["data_base", "cod_inst"]).any()
