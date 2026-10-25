"""B-30c: situação cadastral do CNPJ mês a mês, só código e sem olhar o futuro."""

import io
import tempfile
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from base import situacao_cadastral
from base.ancoragem import parquets_sem_manifesto
from base.porta.duckdb import conectar
from src import acervo
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 10, 14, 7, tzinfo=UTC)
URL = (
    "https://arquivos.receitafederal.gov.br/public.php/dav/files/TOKEN/Dados/Cadastros/CNPJ/"
    "{mes}/Estabelecimentos0.zip"
)


def _estabelecimento(basico, ordem, dv, matriz, situacao, data, motivo="01"):
    campos = ["X"] * 30
    campos[0:4] = [basico, ordem, dv, matriz]
    campos[4] = "NOME FANTASIA PESSOAL"  # dado pessoal: nunca pode sair
    campos[5:8] = [situacao, data, motivo]
    campos[27] = "email.pessoal@exemplo.com"
    campos[28:30] = ["", ""]
    return ";".join(f'"{c}"' for c in campos)


def _zip(*linhas: str) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            "K3241.K03200Y7.D61010.ESTABELE", "\n".join(linhas).encode("latin-1")
        )
    return saida.getvalue()


def test_le_cnpj_e_codigos_sem_nome_nem_contato():
    tabela = situacao_cadastral.ler_situacao_cadastral_do_cnpj(
        _zip(
            _estabelecimento("11111111", "0001", "11", "1", "2", "20200105", "0"),
            _estabelecimento("22222222", "0002", "22", "2", "08", "20240310", "01"),
            _estabelecimento("33333333", "0001", "33", "1", "4", "0", "63"),
        )
    )
    assert list(tabela["cnpj"]) == [
        "11.111.111/0001-11",
        "22.222.222/0002-22",
        "33.333.333/0001-33",
    ]
    assert list(tabela["situacao_cadastral"]) == ["02", "08", "04"]
    assert list(tabela["motivo_situacao"]) == ["00", "01", "63"]
    assert list(tabela["matriz"]) == [True, False, True]
    assert str(tabela["data_situacao_cadastral"].iloc[0]) == "2020-01-05"
    assert pd.isna(tabela["data_situacao_cadastral"].iloc[2])
    assert list(tabela.columns) == list(situacao_cadastral.COLUNAS)
    texto = tabela.to_csv()
    assert "NOME FANTASIA" not in texto and "email.pessoal" not in texto


def _guardar(banco, mes, quando, *linhas):
    conteudo = _zip(*linhas)
    url = URL.format(mes=mes)
    with banco.begin() as conexao:
        coletas.registrar(
            conexao,
            "rfb-cnpj",
            url,
            conteudo,
            "ok",
            agora=quando,
            caminho_do_original=acervo.guardar_original(
                "rfb-cnpj", url, conteudo, quando
            ),
        )


def test_cada_mes_guardado_vira_um_parquet_com_a_origem(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    conteudo = _zip(_estabelecimento("11111111", "0001", "11", "1", "2", "20200105"))
    com_registro("rfb-cnpj", lambda _url: conteudo)(URL.format(mes="2026-10"))
    with banco.connect() as conexao:
        linhas = situacao_cadastral.montar(conexao, tmp_path / "base", AGORA)
    assert linhas == {"2026-10": 1}
    tabela = pd.read_parquet(
        tmp_path / "base" / "cnpj_situacao_cadastral" / "2026-10.parquet"
    )
    assert tabela["mes_do_retrato"].iloc[0] == "2026-10"
    assert len(tabela["origem_sha256"].iloc[0]) == 64
    assert tabela["versao_do_codigo"].iloc[0] == "0123abc"
    assert parquets_sem_manifesto(tmp_path / "base") == []


def test_arquivo_que_nao_e_de_estabelecimentos_fica_de_fora(banco, tmp_path):
    url = URL.format(mes="2026-10").replace("Estabelecimentos0", "Socios0")
    com_registro("rfb-cnpj", lambda _url: b"PK")(url)
    with banco.connect() as conexao:
        assert situacao_cadastral.montar(conexao, tmp_path / "base", AGORA) == {}


def _montado(banco, tmp_path, mes, quando):
    _guardar(
        banco,
        mes,
        quando,
        _estabelecimento("11111111", "0001", "11", "1", "8", "20210311"),
    )
    with banco.connect() as conexao:
        situacao_cadastral.montar(conexao, tmp_path / "base", AGORA)
    return pd.read_parquet(
        tmp_path / "base" / "cnpj_situacao_cadastral" / f"{mes}.parquet"
    )


def test_retrato_visto_dentro_do_mes_vale_do_fim_do_mes(banco, tmp_path):
    visto = datetime(2026, 10, 13, 23, tzinfo=UTC)
    tabela = _montado(banco, tmp_path, "2026-10", visto)
    assert str(tabela["disponivel_em"].iloc[0]) == "2026-10-31"


def test_retrato_visto_depois_do_mes_vale_do_dia_em_que_foi_visto(banco, tmp_path):
    """Sem olhar o futuro: baixado em 10/11, antes disso ninguém sabia."""
    visto = datetime(2026, 11, 10, 12, tzinfo=UTC)
    tabela = _montado(banco, tmp_path, "2026-10", visto)
    assert str(tabela["disponivel_em"].iloc[0]) == "2026-11-10"


def test_comando_monta_a_situacao_cadastral(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import montar_base_historica

    conteudo = _zip(_estabelecimento("11111111", "0001", "11", "1", "2", "20200105"))
    com_registro("rfb-cnpj", lambda _url: conteudo)(URL.format(mes="2026-10"))
    argumentos = ["cnpj_situacao_cadastral", "--pasta", str(tmp_path / "b")]
    assert montar_base_historica.main(argumentos) == 0
    assert (tmp_path / "b" / "cnpj_situacao_cadastral" / "2026-10.parquet").exists()


RETRATOS = [
    ("2026-07", "2026-07-31", "02"),
    ("2026-08", "2026-08-31", "02"),
    ("2026-09", "2026-09-30", "04"),
    ("2026-10", "2026-10-31", "08"),
]


def _gravar_retrato(pasta: Path, mes: str, fim: str, situacao: str) -> None:
    tabela = pd.DataFrame(
        {
            "cnpj": ["11.111.111/0001-11"],
            "cnpj_basico": ["11111111"],
            "situacao_cadastral": [situacao],
            "mes_do_retrato": [mes],
            "disponivel_em": [date.fromisoformat(fim)],
            "origem_coletada_em": [f"{fim}T12:00:00+00:00"],
        }
    )
    caminho = pasta / "cnpj_situacao_cadastral" / f"{mes}.parquet"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(caminho, index=False)


def _como_era(pasta: Path, dia: date) -> str | None:
    """A situação do retrato mais recente que já era público em `dia`, pela porta."""
    with conectar(pasta) as con:
        linhas = con.execute(
            "SELECT situacao_cadastral FROM cnpj_situacao_cadastral "
            f"WHERE publico_em <= DATE '{dia}' ORDER BY publico_em DESC LIMIT 1"
        ).fetchall()
    return linhas[0][0] if linhas else None


@settings(max_examples=25, deadline=None)
@given(dia=st.dates(min_value=date(2026, 6, 1), max_value=date(2026, 11, 30)))
def test_cortar_o_futuro_nao_muda_o_passado(dia):
    """Pela porta, "como era em D" é igual com todos os retratos e só com os que já eram públicos
    em D: os retratos posteriores não mudam a resposta."""
    with tempfile.TemporaryDirectory() as bruto:
        todos, ate_o_dia = Path(bruto) / "todos", Path(bruto) / "ate_o_dia"
        for mes, fim, situacao in RETRATOS:
            _gravar_retrato(todos, mes, fim, situacao)
            if date.fromisoformat(fim) <= dia:
                _gravar_retrato(ate_o_dia, mes, fim, situacao)
        if not (ate_o_dia / "cnpj_situacao_cadastral").exists():
            # nenhum retrato público ainda: a porta só abre a tabela se houver arquivo
            assert _como_era(todos, dia) is None
            return
        assert _como_era(ate_o_dia, dia) == _como_era(todos, dia)
