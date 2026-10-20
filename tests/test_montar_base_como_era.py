"""Montagem da base "como era na data" (série 1 da base de ML, PR 6): junta os dados abertos de dois
anos e as versões antigas do ENET que estiverem no acervo, e grava um Parquet por ano. Sem internet."""

import io
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from base.dmpl import FORMATO_DMPL
from base.enet_coleta import guardar
from base.ponto_no_tempo import como_era_em, ler_parquet
from scripts import montar_base_como_era as montar
from src import acervo
from src import demonstracoes as dm
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para
from tests.test_base_enet import _dfp
from tests.test_base_enet_coleta import _pacote

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
COLETADO_EM = datetime(2026, 10, 12, 7, tzinfo=UTC)


VERSAO = "7ddaf09c1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b"


@pytest.fixture
def url(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)  # a carga da base exige a versão do código
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    migrar_para("head", url=url)
    motor = criar_engine(url)
    with motor.begin() as c:
        for ano in (2024, 2025):
            conteudo = (PASTA / f"dfp_cia_aberta_{ano}.zip").read_bytes()
            endereco = dm.URL_DO_DFP.format(ano=ano)
            caminho = acervo.guardar_original(
                "cvm-dfp-itr", endereco, conteudo, COLETADO_EM
            )
            registrar(
                c, "cvm-dfp-itr", endereco, conteudo, "ok", caminho_do_original=caminho
            )
    motor.dispose()
    return url


@pytest.fixture
def sem_internet(monkeypatch):
    """Só existem os arquivos de teste; o resto é 404. Guarda o que a montagem pediu."""
    pedidos: list[str] = []

    def baixar_falso(endereco: str) -> bytes | None:
        pedidos.append(endereco)
        nome = endereco.rsplit("/", 1)[-1]
        return (PASTA / nome).read_bytes() if (PASTA / nome).exists() else None

    monkeypatch.setattr(montar, "baixar", baixar_falso)
    return pedidos


def test_monta_o_ano_com_os_dois_arquivos_e_grava_o_parquet(
    url, sem_internet, tmp_path
):
    saida = tmp_path / "base"
    assert montar.main(["--anos", "2024", "--pasta", str(saida)]) == 0
    assert (saida / "2024.parquet").exists()
    base = ler_parquet(saida)
    assert set(base["fim"].dt.year) == {2024}
    # os fatos de 2024 também saem no DFP de 2025, na coluna do ano anterior
    assert {"ultimo", "penultimo"} <= set(base["ordem"])
    assert set(base["referencia"].dt.year) >= {2024, 2025}
    no_acervo = {dm.URL_DO_DFP.format(ano=a) for a in (2024, 2025)}
    assert not no_acervo & set(sem_internet)  # vieram do acervo, sem baixar de novo
    foto = como_era_em(base, "2025-06-30")
    assert not foto.empty and (foto["divulgado_em"] <= pd.Timestamp("2025-06-30")).all()


def test_versao_antiga_que_esta_no_acervo_entra_e_a_que_falta_e_contada(url):
    motor = criar_engine(url)
    indice = pd.DataFrame(
        {
            "cnpj": ["00.000.208/0001-00"] * 3,
            "referencia": [pd.Timestamp("2022-12-31")] * 3,
            "versao": pd.array([1, 2, 3], dtype="Int64"),  # a 3 vem dos dados abertos
            "recebido_em": pd.to_datetime(["2023-03-10", "2023-04-20", "2023-06-01"]),
            "link": ["http://enet/1", "http://enet/2", "http://enet/3"],
        }
    )
    with motor.begin() as c:
        guardar(c, "http://enet/1", _pacote(_dfp(versao=1)), COLETADO_EM)
    with motor.connect() as c:
        documentos, faltando, origens = montar.documentos_do_enet(c, indice)
    motor.dispose()
    assert [d.versao for d in documentos] == [1]
    assert faltando == ["http://enet/2"]
    assert [o["url"] for o in origens] == ["http://enet/1"] and len(
        origens[0]["sha256"]
    ) == 64


def test_montar_de_novo_da_o_mesmo_hash_e_conferir_confirma(
    url, sem_internet, tmp_path, capsys
):
    import json

    saida = tmp_path / "base"
    assert montar.main(["--anos", "2024", "--pasta", str(saida)]) == 0
    primeiro = json.loads((saida / "2024.json").read_text(encoding="utf-8"))
    assert montar.main(["--anos", "2024", "--pasta", str(saida)]) == 0
    segundo = json.loads((saida / "2024.json").read_text(encoding="utf-8"))
    assert primeiro["sha256_da_base"] == segundo["sha256_da_base"]
    urls = {o["url"] for o in primeiro["origens"]}
    assert {dm.URL_DO_DFP.format(ano=2024), dm.URL_DO_DFP.format(ano=2025)} <= urls
    assert dm.URL_DO_CADASTRO in urls  # o registro seguinte vem do cadastro
    assert montar.main(["--conferir", "--pasta", str(saida)]) == 0
    assert "2024: ok" in capsys.readouterr().out


def test_sem_a_versao_do_codigo_a_base_nao_e_gravada(
    url, sem_internet, tmp_path, monkeypatch
):
    """Exigência 13 da ADR 0055: número sem a versão do código que o fez não entra na base."""
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError, match=vc.VARIAVEL):  # desconhecida
        montar.main(["--anos", "2024", "--pasta", str(tmp_path / "base")])
    assert not (tmp_path / "base").exists()


def test_manifesto_leva_a_versao_do_codigo(url, sem_internet, tmp_path):
    import json

    saida = tmp_path / "base"
    assert montar.main(["--anos", "2024", "--pasta", str(saida)]) == 0
    manifesto = json.loads((saida / "2024.json").read_text(encoding="utf-8"))
    assert manifesto["versao_do_codigo"] == VERSAO


def test_versao_do_enet_sem_cnpj_no_xml_fica_com_o_do_indice(url):
    """Alguns XMLs do ENET vêm com `CnpjEmpresa` vazio: as contas não achavam a data de divulgação."""
    motor = criar_engine(url)
    indice = pd.DataFrame(
        {
            "cnpj": ["00.000.208/0001-00"] * 2,
            "referencia": [pd.Timestamp("2022-12-31")] * 2,
            "versao": pd.array([1, 2], dtype="Int64"),
            "recebido_em": pd.to_datetime(["2023-03-10", "2023-06-01"]),
            "link": ["http://enet/1", "http://enet/2"],
        }
    )
    xml = _dfp(versao=1)
    sem_cnpj = xml.replace(
        b"<CnpjEmpresa>00000208000100</CnpjEmpresa>", b"<CnpjEmpresa />"
    )
    assert sem_cnpj != xml
    with motor.begin() as c:
        guardar(c, "http://enet/1", _pacote(sem_cnpj), COLETADO_EM)
    with motor.connect() as c:
        documentos, _, _ = montar.documentos_do_enet(c, indice)
    motor.dispose()
    assert documentos[0].cnpj == "00.000.208/0001-00"
    assert set(documentos[0].contas["cnpj"]) == {"00.000.208/0001-00"}
    assert set(documentos[0].dmpl["cnpj"]) == {"00.000.208/0001-00"}


# --- série T1 -----------------------------------------------------------------------------------------
CABECALHO_DA_DMPL = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;"
    "DT_INI_EXERC;DT_FIM_EXERC;COLUNA_DF;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA"
)
LINHA_DA_DMPL = (
    "00.000.000/0001-91;2024-12-31;1;BCO BRASIL S.A.;001023;DF Consolidado - Demonstração das "
    "Mutações do Patrimônio Líquido;REAL;MIL;ÚLTIMO;2024-01-01;2024-12-31;Patrimônio Líquido;"
    "5.07;Saldos Finais;200000.0000000000;S"
)


def _com_dmpl(conteudo: bytes) -> bytes:
    """O zip de teste com uma DMPL do Banco do Brasil (os arquivos de teste não trazem a DMPL)."""
    saida = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(conteudo)) as entrada,
        zipfile.ZipFile(saida, "w") as z,
    ):
        for nome in entrada.namelist():
            z.writestr(nome, entrada.read(nome))
        z.writestr(
            "dfp_cia_aberta_DMPL_con_2024.csv",
            f"{CABECALHO_DA_DMPL}\n{LINHA_DA_DMPL}".encode("latin-1"),
        )
    return saida.getvalue()


@pytest.fixture
def com_dmpl_no_acervo(url):
    """Um DFP 2024 mais novo no acervo, com a DMPL."""
    conteudo = _com_dmpl((PASTA / "dfp_cia_aberta_2024.zip").read_bytes())
    endereco = dm.URL_DO_DFP.format(ano=2024)
    depois = datetime.now(UTC) + timedelta(
        minutes=1
    )  # mais novo que o da fixture `url`
    motor = criar_engine(url)
    with motor.begin() as c:
        caminho = acervo.guardar_original("cvm-dfp-itr", endereco, conteudo, depois)
        registrar(
            c,
            "cvm-dfp-itr",
            endereco,
            conteudo,
            "ok",
            caminho_do_original=caminho,
            agora=depois,
        )
    motor.dispose()
    return url


def test_sem_a_serie_t1_a_montagem_e_a_de_antes(
    com_dmpl_no_acervo, sem_internet, tmp_path
):
    """O cron semanal do servidor não muda o formato da tabela antes da remontagem autorizada."""
    saida = tmp_path / "base" / "demonstracoes"
    assert montar.main(["--anos", "2024", "--pasta", str(saida)]) == 0
    base = ler_parquet(saida)
    assert set(base["demonstracao"]) == {"BPA", "BPP", "DRE"}
    assert not (tmp_path / "base" / "dmpl").exists()


def test_serie_t1_traz_a_dfc_e_grava_a_dmpl_ao_lado(
    com_dmpl_no_acervo, sem_internet, tmp_path, capsys
):
    saida = tmp_path / "base" / "demonstracoes"
    argumentos = ["--anos", "2024", "--pasta", str(saida), "--serie-t1"]
    assert montar.main(argumentos) == 0
    base = ler_parquet(saida)
    assert "DFC_MI" in set(base["demonstracao"])
    dfc = base[base["demonstracao"] == "DFC_MI"]
    assert dfc["divulgado_em"].notna().all()
    pasta_dmpl = tmp_path / "base" / "dmpl"
    dmpl = ler_parquet(pasta_dmpl, formato=FORMATO_DMPL)
    assert dmpl[["coluna", "valor"]].values.tolist() == [
        ["patrimonio_liquido", 200_000_000.0]
    ]
    assert dmpl["divulgado_em"].tolist() == [pd.Timestamp("2025-02-19")]
    assert montar.main(["--conferir", "--pasta", str(saida), "--serie-t1"]) == 0
    saida_do_conferir = capsys.readouterr().out
    assert saida_do_conferir.count("2024: ok") == 2  # as demonstrações e a DMPL


def test_versao_antiga_no_formato_dfp_do_acervo_entra_na_montagem(url):
    from tests.test_base_enet_antigo import _pacote_antigo

    motor = criar_engine(url)
    indice = pd.DataFrame(
        {
            "cnpj": ["08.493.364/0001-62"] * 3,
            "referencia": [pd.Timestamp("2015-03-31")] * 3,
            "versao": pd.array([1, 2, 3], dtype="Int64"),  # a 3 vem dos dados abertos
            "recebido_em": pd.to_datetime(["2015-04-10", "2015-05-10", "2015-06-01"]),
            "link": [f"http://enet/antigo/{v}" for v in (1, 2, 3)],
        }
    )
    with motor.begin() as c:
        guardar(c, "http://enet/antigo/2", _pacote_antigo(), COLETADO_EM)
    with motor.connect() as c:
        documentos, faltando, _ = montar.documentos_do_enet(c, indice)
    motor.dispose()
    assert [d.versao for d in documentos] == [2]
    assert faltando == ["http://enet/antigo/1"]
    assert documentos[0].contas["fim"].max() <= documentos[0].referencia
