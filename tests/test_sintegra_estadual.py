"""Cadastros inteiramente inventados, sem rede nem documento real."""

import hashlib
import json
import zipfile
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base.cnpj import digitos_verificadores
from tests.ajudantes_de_cpf import cpf_que_tambem_passa_como_cnpj

TABELA = "sintegra_estadual"
QUANDO = datetime(2026, 11, 27, tzinfo=UTC)


def _cnpj(numero=1):
    base = f"{99_000_000 + numero:08d}0001"
    return base + digitos_verificadores(base)


def _linha(uf, documento=None, **mudancas):
    campos = {
        "PR": [
            "9900000001",
            documento or _cnpj(),
            "202001",
            "12345678",
            "99000",
            "1234567",
        ],
        "RS": [
            "9900000001",
            documento or _cnpj(),
            "S NAC",
            "31/01/2020",
            "1234567",
            "RS",
            "123456789",
        ],
        "MG": ["9900000000001", documento or _cnpj(), "CAMPO PROIBIDO", "H", "1234567"],
    }[uf]
    for indice, valor in mudancas.items():
        campos[int(indice)] = valor
    return ";".join(campos) + "\r\n"


def _arquivo(tmp_path, uf, linhas=None):
    conteudo = "".join(linhas or [_linha(uf)]).encode("latin-1")
    destino = tmp_path / ("entrada.zip" if uf == "RS" else "entrada.txt")
    if uf == "RS":
        with zipfile.ZipFile(destino, "w") as pacote:
            pacote.writestr("ICS_Ativo.txt", conteudo)
    else:
        destino.write_bytes(conteudo)
    return destino


def test_tabela_nasce_restrita_sem_catalogo_nem_historico_inventado():
    from base.contrato import catalogo, contrato_da_tabela
    from base.dicionario import TABELAS
    from base.dossie import pode_consultar, pode_consultar_aberto, pode_mostrar
    from base.porta.duckdb import ARQUIVOS, FORA_DA_PORTA
    from base.vitrine import TABELAS_SO_INTERNAS, catalogo_publico

    assert TABELA in TABELAS
    tabela = TABELAS[TABELA]
    assert tabela.pessoa and not tabela.historico_desde
    assert tabela.datas["publico_em"] == "disponivel_em"
    assert TABELA in FORA_DA_PORTA and TABELA not in ARQUIVOS
    assert TABELA in TABELAS_SO_INTERNAS
    assert not any(
        f(TABELA) for f in (pode_consultar, pode_consultar_aberto, pode_mostrar)
    )
    assert (
        TABELA
        not in catalogo_publico(catalogo(), montadas=frozenset({TABELA}))["tabelas"]
    )
    assert (
        contrato_da_tabela(TABELA, tabela)["licenca"]
        == "não declarada pela fonte; uso interno"
    )


@pytest.mark.parametrize("uf", ["PR", "RS", "MG"])
def test_leitores_descartam_documentos_invalidos_e_so_guardam_colunas_permitidas(
    tmp_path, uf
):
    from base import sintegra_estadual as sintegra

    invalidos = ["0" * 14, "1" * 14, "123", "000" + cpf_que_tambem_passa_como_cnpj()]
    linhas = [_linha(uf), *[_linha(uf, d) for d in invalidos]]
    tabela = sintegra.ler_arquivo(_arquivo(tmp_path, uf, linhas), uf, "ativos")
    assert list(tabela.cnpj) == [_cnpj()]
    assert set(tabela) == set(sintegra.COLUNAS)
    assert "CAMPO PROIBIDO" not in tabela.to_csv()
    assert tabela.iloc[0].uf == uf
    assert (
        tabela.iloc[0].categoria == "S NAC"
        if uf == "RS"
        else tabela.categoria.isna().all()
    )


@pytest.mark.parametrize("uf", ["PR", "RS", "MG"])
def test_layout_inesperado_e_chave_duplicada_recusam_arquivo(tmp_path, uf):
    from base import sintegra_estadual as sintegra

    for linhas in [
        [_linha(uf).strip() + ";coluna nova\n"],
        [_linha(uf)] * 2,
        ["<html>desafio</html>\n"],
    ]:
        with pytest.raises(ValueError):
            sintegra.ler_arquivo(_arquivo(tmp_path, uf, linhas), uf, "ativos")


@pytest.mark.parametrize(
    "uf,mudancas",
    [
        ("PR", {"2": "202013"}),
        ("PR", {"3": "CAMPO PROIBIDO"}),
        ("RS", {"2": "OUTRO"}),
        ("RS", {"3": "31/02/2020"}),
        ("RS", {"5": "ZZ"}),
        ("MG", {"3": "X"}),
        ("MG", {"4": "nome"}),
    ],
)
def test_campo_fora_do_layout_falha_sem_reproduzir_conteudo(tmp_path, uf, mudancas):
    from base import sintegra_estadual as sintegra

    with pytest.raises(ValueError) as erro:
        sintegra.ler_arquivo(
            _arquivo(tmp_path, uf, [_linha(uf, **mudancas)]), uf, "ativos"
        )
    assert "CAMPO PROIBIDO" not in str(erro.value)


@pytest.mark.parametrize("uf,motivo", [("RS", "robots.txt"), ("MG", "404")])
def test_download_rs_mg_recusado_antes_de_qualquer_rede(tmp_path, uf, motivo):
    from scripts import carga_sintegra_estadual as carga

    class SemRede:
        def baixar(self, *args):
            pytest.fail("não pode baixar esta UF")

    with pytest.raises(ValueError, match=motivo):
        carga.carregar_uf(uf, tmp_path, QUANDO, SemRede())
    assert not list(tmp_path.iterdir())


class _Servidor:
    def __init__(self, cancelados=None):
        self.pedidos = []
        self.arquivos = {
            "ativos": _linha("PR"),
            "cancelados": cancelados or _linha("PR", _cnpj(2)),
        }

    def baixar(self, url, destino):
        self.pedidos.append(url)
        destino.write_bytes(self.arquivos[url.rsplit("/", 1)[-1]].encode())
        return {"Last-Modified": "Mon, 11 May 2026 09:00:00 GMT"}


def test_carga_pr_grava_linhagem_e_datas_sem_retroagir(tmp_path, monkeypatch):
    from base.dicionario import TABELAS
    from base.parquet import conferir_tabela
    from scripts import carga_sintegra_estadual as carga

    monkeypatch.setattr(
        carga, "espaco_do_disco", lambda pasta: (1000 * 1024**3, 800 * 1024**3)
    )
    servidor = _Servidor()
    assert carga.carregar_uf("PR", tmp_path, QUANDO, servidor) == "gravado"
    arquivo = tmp_path / TABELA / "PR/2026-05-11.parquet"
    tabela = pd.read_parquet(arquivo)
    assert conferir_tabela(arquivo)
    assert set(tabela) == set(TABELAS[TABELA].colunas)
    assert len(tabela) == 2
    assert set(tabela.disponivel_em) == {QUANDO.date()}
    assert set(tabela.publico_em) == {QUANDO.date()}
    assert set(tabela.data_arquivo) == {date(2026, 5, 11)}
    assert tabela.optante_simples.isna().all()
    assert len(servidor.pedidos) == len(set(servidor.pedidos)) == 2
    manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    origens = manifesto["origens"]
    assert len(origens) == 2 and all(o["data_arquivo"] == "2026-05-11" for o in origens)
    assert (
        origens[0]["sha256"]
        == hashlib.sha256(servidor.arquivos["ativos"].encode()).hexdigest()
    )
    assert not list(tmp_path.glob("sintegra-*"))
    assert (
        carga.carregar_uf("PR", tmp_path, datetime(2026, 11, 28, tzinfo=UTC), servidor)
        == "igual"
    )
    assert pd.read_parquet(arquivo).iloc[0].disponivel_em == QUANDO.date()
    novo = _Servidor(_linha("PR", _cnpj(3)))
    carga.carregar_uf("PR", tmp_path, datetime(2026, 11, 28, tzinfo=UTC), novo)
    assert conferir_tabela(arquivo.with_name("2026-05-11.v1.parquet"))


def test_segundo_arquivo_invalido_nao_publica_meia_uf(tmp_path, monkeypatch):
    from scripts import carga_sintegra_estadual as carga

    monkeypatch.setattr(
        carga, "espaco_do_disco", lambda pasta: (1000 * 1024**3, 800 * 1024**3)
    )
    with pytest.raises(ValueError):
        carga.carregar_uf(
            "PR", tmp_path, QUANDO, _Servidor("<html>CAMPO PROIBIDO</html>")
        )
    assert not list(tmp_path.rglob("*.parquet"))
    assert not list(tmp_path.glob("sintegra-*"))


def test_freio_de_disco_impede_download(tmp_path, monkeypatch):
    from base.arquivo.coleta import FreioDeDisco
    from scripts import carga_sintegra_estadual as carga

    monkeypatch.setattr(carga, "espaco_do_disco", lambda pasta: (1000, 1))
    servidor = _Servidor()
    with pytest.raises(FreioDeDisco):
        carga.carregar_uf("PR", tmp_path, QUANDO, servidor)
    assert servidor.pedidos == []


def test_simples_local_liga_pela_raiz_sem_substituir_categoria_estadual(
    tmp_path, monkeypatch
):
    from scripts import carga_sintegra_estadual as carga

    monkeypatch.setattr(
        carga, "espaco_do_disco", lambda pasta: (1000 * 1024**3, 800 * 1024**3)
    )
    simples = tmp_path / "cnpj/vigente/simples/99.parquet"
    simples.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "cnpj_basico": [_cnpj()[:8]],
            "optante_simples": [True],
            "optante_mei": [False],
            "data_opcao_simples": [date(2020, 1, 1)],
            "data_exclusao_simples": [None],
            "data_opcao_mei": [None],
            "data_exclusao_mei": [None],
            "nome": ["CAMPO PROIBIDO"],
        }
    ).to_parquet(simples)
    carga.carregar_uf("PR", tmp_path, QUANDO, _Servidor())
    tabela = pd.read_parquet(tmp_path / TABELA / "PR/2026-05-11.parquet").set_index(
        "cnpj"
    )
    assert tabela.loc[_cnpj(), "optante_simples"]
    assert not tabela.loc[_cnpj(), "optante_mei"]
    assert pd.isna(tabela.loc[_cnpj(2), "optante_simples"])
    assert tabela.categoria.isna().all()
    assert "CAMPO PROIBIDO" not in tabela.to_csv()


def test_rs_zip_ambiguo_ou_grande_nao_e_extraido(tmp_path, monkeypatch):
    from base import sintegra_estadual as sintegra

    arquivo = _arquivo(tmp_path, "RS")
    with zipfile.ZipFile(arquivo, "a") as pacote:
        pacote.writestr("outra/ICS_Ativo.txt", _linha("RS"))
    with pytest.raises(ValueError):
        sintegra.ler_arquivo(arquivo, "RS", "ativos")
    arquivo = _arquivo(tmp_path, "RS")
    monkeypatch.setattr(sintegra, "MAX_TEXTO", 10)
    with pytest.raises(ValueError):
        sintegra.ler_arquivo(arquivo, "RS", "ativos")
    assert not (tmp_path / "ICS_Ativo.txt").exists()


def test_pr_aceita_txt_dentro_de_zip_sem_extrair(tmp_path):
    from base import sintegra_estadual as sintegra

    arquivo = tmp_path / "ativos.zip"
    with zipfile.ZipFile(arquivo, "w") as pacote:
        pacote.writestr("ativos.txt", _linha("PR"))
    tabela = sintegra.ler_arquivo(arquivo, "PR", "ativos")
    assert list(tabela.cnpj) == [_cnpj()]
    assert not (tmp_path / "ativos.txt").exists()


def test_mg_descarta_nome_com_separador_entre_aspas(tmp_path):
    from base import sintegra_estadual as sintegra

    linha = _linha("MG", **{"2": '"CAMPO;PROIBIDO"'})
    tabela = sintegra.ler_arquivo(_arquivo(tmp_path, "MG", [linha]), "MG", "ativos")
    assert list(tabela.cnpj) == [_cnpj()]
    assert "PROIBIDO" not in tabela.to_csv()


def test_falha_no_download_remove_parcial_sem_substituir_edicao(tmp_path, monkeypatch):
    from scripts import carga_sintegra_estadual as carga

    monkeypatch.setattr(
        carga, "espaco_do_disco", lambda pasta: (1000 * 1024**3, 800 * 1024**3)
    )
    carga.carregar_uf("PR", tmp_path, QUANDO, _Servidor())
    arquivo = tmp_path / TABELA / "PR/2026-05-11.parquet"
    antes = arquivo.read_bytes()

    class Interrompido:
        def baixar(self, url, destino):
            destino.write_bytes(b"PARCIAL")
            raise OSError("CAMPO PROIBIDO")

    with pytest.raises(OSError):
        carga.carregar_uf("PR", tmp_path, QUANDO, Interrompido())
    assert arquivo.read_bytes() == antes
    assert not list(tmp_path.glob("sintegra-*"))


def test_cli_zip_corrompido_falha_sem_conteudo_da_fonte(tmp_path, monkeypatch, caplog):
    from scripts import carga_sintegra_estadual as carga

    class Cliente:
        class Sessao:
            def close(self):
                pass

        sessao = Sessao()

    monkeypatch.setattr(carga, "ClienteSintegra", Cliente)
    monkeypatch.setattr(carga, "exigir_versao_do_codigo", lambda: "abc")

    def corrompido(*args):
        raise zipfile.BadZipFile("CAMPO PROIBIDO")

    monkeypatch.setattr(carga, "carregar_uf", corrompido)
    assert carga.main(["--uf", "PR", "--pasta", str(tmp_path)]) == 1
    assert "CAMPO PROIBIDO" not in caplog.text
