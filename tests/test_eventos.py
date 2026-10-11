"""Eventos da CVM (Research, etapa 2a): leitura, classificação, gravação e consulta, sem internet
(amostras reais em `tests/arquivos/cvm/`)."""

import io
import zipfile
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa

from scripts import atualizar_eventos
from src import eventos as ev
from src.banco import eventos as repo
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para

PASTA = Path(__file__).parent / "arquivos" / "cvm"
PETROBRAS, VALE = "33.000.167/0001-01", "33.592.510/0001-54"


def _zip(nome_no_zip: str, arquivo_csv: str) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(nome_no_zip, (PASTA / arquivo_csv).read_bytes())
    return saida.getvalue()


@pytest.fixture(scope="module")
def ipe():
    return ev.ler_ipe(_zip("ipe_cia_aberta_2026.csv", "ipe_amostra.csv"))


@pytest.fixture(scope="module")
def tickers():
    return ev.ler_tickers_do_fca(
        [
            _zip("fca_cia_aberta_valor_mobiliario_2024.csv", "fca_vm_2024.csv"),
            _zip("fca_cia_aberta_valor_mobiliario_2026.csv", "fca_vm_2026.csv"),
        ]
    )


# --- classificação ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("categoria", "tipo", "assunto", "esperado"),
    [
        ("Fato Relevante", "", "", ("eventos", 100)),
        ("Relatório Proventos", "", "", ("proventos", 80)),
        (
            "Aviso aos Acionistas",
            "Outros avisos",
            "Pagamento de dividendos do 2T26",
            ("proventos", 80),
        ),
        (
            "Aviso aos Acionistas",
            "Outros avisos",
            "Juros sobre capital próprio",
            ("proventos", 80),
        ),
        (
            "Aviso aos Acionistas",
            "Outros avisos",
            "Data da assembleia",
            ("eventos", 40),
        ),
        ("Dados Econômico-Financeiros", "Press-release", "", ("resultados", 70)),
        (
            "Dados Econômico-Financeiros",
            "Relatório de Agência de Rating",
            "",
            ("risco", 40),
        ),
        (
            "Comunicado ao Mercado",
            "Apresentações a analistas/agentes do mercado",
            "",
            ("resultados", 50),
        ),
        ("Assembleia", "AGO", "", ("eventos", 30)),
    ],
)
def test_classificacao_por_tema_e_materialidade(categoria, tipo, assunto, esperado):
    classe = ev.classificar(categoria, tipo, assunto)
    assert (classe.tema, classe.materialidade) == esperado


@pytest.mark.parametrize(
    ("categoria", "tipo"),
    [
        ("Valores Mobiliários negociados e detidos (art. 11 da Instr. CVM nº 358)", ""),
        ("Dados Econômico-Financeiros", "Relatório de Agente Fiduciário"),
        ("Estatuto Social", ""),
    ],
)
def test_categorias_de_pouco_interesse_nao_viram_evento(categoria, tipo):
    assert ev.classificar(categoria, tipo) is None


def test_todo_tema_existe_no_catalogo_de_parametros():
    from src.parametros import TEMAS

    temas = {
        ev.classificar(c, t, a).tema
        for c, t, a in [
            ("Fato Relevante", "", ""),
            ("Relatório Proventos", "", ""),
            ("Dados Econômico-Financeiros", "Press-release", ""),
            ("Dados Econômico-Financeiros", "Rating", ""),
        ]
    }
    assert temas <= set(TEMAS)


# --- leitura dos arquivos da CVM ---------------------------------------------------------------------
def test_ipe_ignora_o_que_nao_e_evento_e_nao_repete_entregas(ipe):
    assert not ipe["categoria"].str.startswith("Valores Mobiliários").any()
    assert ipe["protocolo"].is_unique


def test_relatorio_de_proventos_sem_protocolo_usa_o_numero_do_link(ipe):
    """Na CVM, os relatórios de proventos vêm com a coluna de protocolo vazia."""
    proventos = ipe[ipe["categoria"] == "Relatório Proventos"]
    assert len(proventos) == 2
    assert proventos["protocolo"].str.fullmatch(r"rad-\d+").all()


def test_versao_mais_nova_vence():
    bruto = (PASTA / "ipe_amostra.csv").read_text(encoding="cp1252").splitlines()
    cabecalho, primeira = bruto[0], next(l for l in bruto[1:] if "Fato Relevante" in l)
    nova = primeira.replace(
        ";1;https", ";2;https"
    )  # a mesma entrega, reapresentada (versão 2)
    conteudo = f"{cabecalho}\n{primeira}\n{nova}".encode("cp1252")
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("ipe_cia_aberta_2026.csv", conteudo)
    lido = ev.ler_ipe(saida.getvalue())
    assert len(lido) == 1 and lido["versao"].iloc[0] == 2


def test_ipe_tem_datas_link_e_ordem_do_mais_novo(ipe):
    assert all(isinstance(d, date) for d in ipe["publicado_em"])
    assert ipe["link"].str.startswith("https://www.rad.cvm.gov.br/").all()
    assert list(ipe["publicado_em"]) == sorted(ipe["publicado_em"], reverse=True)
    assert set(ipe["cnpj"]) >= {PETROBRAS, VALE}


def test_fca_junta_os_anos_e_fica_com_o_registro_mais_novo(tickers):
    por_codigo = tickers.set_index("codigo")
    assert por_codigo.loc["PETR4", "cnpj"] == PETROBRAS
    assert por_codigo.loc["PETR4", "ticker"] == "PETR4.SA"
    assert "WEGE3" in por_codigo.index  # só no FCA de 2024: continua valendo
    assert tickers["codigo"].is_unique


# --- banco ----------------------------------------------------------------------------------------------
@pytest.fixture
def motor(tmp_path):
    url = f"sqlite:///{(tmp_path / 'e.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()


def test_gravar_duas_vezes_nao_duplica_e_versao_nova_atualiza(motor, ipe):
    with motor.begin() as c:
        assert repo.gravar_eventos(c, ipe) == (len(ipe), 0)
        assert repo.gravar_eventos(c, ipe) == (0, 0)
        mais_nova = ipe.head(1).assign(
            versao=ipe["versao"].iloc[0] + 1, assunto="corrigido"
        )
        assert repo.gravar_eventos(c, mais_nova) == (0, 1)
        assunto = c.execute(sa.text("select assunto from eventos where protocolo = :p"),
                            {"p": ipe["protocolo"].iloc[0]}).scalar()  # fmt: skip
        assert assunto == "corrigido"


def test_mapa_vazio_nao_apaga_o_mapa_guardado(motor, tickers):
    with motor.begin() as c:
        assert repo.gravar_tickers(c, tickers) == len(tickers)
        assert repo.gravar_tickers(c, tickers.iloc[0:0]) == 0
        assert len(repo.empresas_dos_tickers(c, tickers["ticker"])) == len(tickers)


def test_eventos_dos_tickers_usa_o_ticker_pedido_filtra_data_e_tema(
    motor, ipe, tickers
):
    with motor.begin() as c:
        repo.gravar_tickers(c, tickers)
        repo.gravar_eventos(c, ipe)
        todos = repo.eventos_dos_tickers(
            c, ["PETR4.SA", "PETR3.SA", "AAPL"], date(2000, 1, 1)
        )
        assert todos and {e.ticker for e in todos} == {
            "PETR4.SA"
        }  # PETR3 é a mesma empresa
        assert all("PETROBRAS" in e.empresa.upper() for e in todos)
        so_petr3 = repo.eventos_dos_tickers(c, ["PETR3.SA"], date(2000, 1, 1))
        assert {e.ticker for e in so_petr3} == {"PETR3.SA"}
        recentes = repo.eventos_dos_tickers(c, ["PETR4.SA"], todos[0].publicado_em)
        assert all(e.publicado_em >= todos[0].publicado_em for e in recentes)
        fatos = repo.eventos_dos_tickers(
            c, ["PETR4.SA", "VALE3.SA"], date(2000, 1, 1), temas=["eventos"]
        )
        assert fatos and all(e.tema == "eventos" for e in fatos)
        assert (
            repo.eventos_dos_tickers(c, ["AAPL"], date(2000, 1, 1)) == []
        )  # sem cadastro na CVM
        assert repo.ultima_coleta(c) is not None


def test_script_de_coleta_grava_sem_internet(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 's.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)

    def baixar_falso(endereco: str) -> bytes:
        if "IPE" in endereco:
            return _zip("ipe_cia_aberta_2026.csv", "ipe_amostra.csv")
        return _zip("fca_cia_aberta_valor_mobiliario_2026.csv", "fca_vm_2026.csv")

    monkeypatch.setattr(atualizar_eventos, "baixar", baixar_falso)
    assert atualizar_eventos.main(["--anos", "1"]) == 0
    with criar_engine(url).connect() as c:
        assert c.execute(sa.text("select count(*) from eventos")).scalar() > 0
        assert (
            c.execute(sa.text("select count(*) from tickers_dos_emissores")).scalar()
            == 4
        )


def test_falha_da_cvm_sai_com_erro_e_nao_apaga_nada(tmp_path, monkeypatch):
    import requests

    monkeypatch.setenv(
        "TICKERLAB_DATABASE_URL", f"sqlite:///{(tmp_path / 'f.sqlite').as_posix()}"
    )

    def fora_do_ar(endereco: str) -> bytes:
        raise requests.ConnectionError("sem conexão")

    monkeypatch.setattr(atualizar_eventos, "baixar", fora_do_ar)
    assert atualizar_eventos.main(["--anos", "1"]) == 1


def test_migracao_0008_vai_e_volta(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.sqlite').as_posix()}"
    migrar_para("head", url=url)
    assert {"eventos", "tickers_dos_emissores"} <= set(
        sa.inspect(criar_engine(url)).get_table_names()
    )
    desfazer_ate("0007", url=url)
    assert "eventos" not in sa.inspect(criar_engine(url)).get_table_names()
    migrar_para("head", url=url)
