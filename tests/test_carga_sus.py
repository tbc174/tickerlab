"""Carga dos totais do SUS por competência (scripts/carga_sus.py). Nada vai à internet: o FTP é um dublê.

O que importa aqui: a pasta da carga só recebe o agregado (Parquet e manifesto, nenhum DBC), a data de
quando o dado foi visto não anda para frente ao olhar de novo, e o reprocesso do DATASUS vira versão nova.
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base import sus
from base.parquet import GRAVADO, IGUAL, ler_tabela
from scripts import carga_sus
from src.banco import coletas
from tests.test_base_sus import dbc_do_sia, dbc_do_sih, internacao, procedimento

PRIMEIRA = date(2026, 11, 5)
DEPOIS = date(2026, 12, 5)
COMPETENCIA = 202607


def _ftp(arquivos: dict[str, bytes]) -> tuple[sus.Listador, sus.Baixador]:
    def listar(pasta: str) -> list[str]:
        return list(arquivos)

    def baixar(pasta: str, nome: str) -> bytes:
        return arquivos[nome]

    return listar, baixar


def _carregar(
    sistema: sus.Sistema, arquivos: dict[str, bytes], saida: Path, quando: date
) -> tuple[str, str]:
    listar, baixar = _ftp(arquivos)
    return carga_sus.carregar_competencia(
        sistema, COMPETENCIA, saida, quando, listar=listar, baixar=baixar, ufs=("AC",)
    )


def test_grava_a_tabela_e_a_situacao(tmp_path: Path):
    resultado = _carregar(
        sus.SIH, {"RDAC2607.dbc": dbc_do_sih([internacao()] * 12)}, tmp_path, PRIMEIRA
    )
    assert resultado == (GRAVADO, GRAVADO)
    tabela = ler_tabela(tmp_path / "sus_internacoes" / "202607.parquet")
    assert list(tabela.columns) == list(sus.SIH.colunas_da_tabela)
    assert tabela.loc[0, "internacoes"] == 12
    situacao = ler_tabela(tmp_path / "sus_competencias" / "sih-202607.parquet")
    assert list(situacao.columns) == list(sus.COLUNAS_DA_SITUACAO)


def test_ambulatorial_vai_para_a_propria_tabela(tmp_path: Path):
    _carregar(
        sus.SIA, {"PAAC2607.dbc": dbc_do_sia([procedimento()] * 12)}, tmp_path, PRIMEIRA
    )
    tabela = ler_tabela(tmp_path / "sus_ambulatorial" / "202607.parquet")
    assert tabela.loc[0, "quantidade_aprovada"] == 12
    assert (tmp_path / "sus_competencias" / "sia-202607.parquet").exists()


def test_carga_so_grava_o_agregado(tmp_path: Path):
    """Nenhum DBC, DBF ou coluna da linha do paciente chega ao disco."""
    _carregar(
        sus.SIH, {"RDAC2607.dbc": dbc_do_sih([internacao()] * 12)}, tmp_path, PRIMEIRA
    )
    _carregar(
        sus.SIA, {"PAAC2607.dbc": dbc_do_sia([procedimento()] * 12)}, tmp_path, PRIMEIRA
    )
    gravados = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert gravados
    assert {p.suffix for p in gravados} <= {".parquet", ".json"}
    for arquivo in gravados:
        if arquivo.suffix == ".parquet":
            assert not set(ler_tabela(arquivo).columns) & sus.COLUNAS_PROIBIDAS


def test_origens_tem_o_hash_de_cada_arquivo(tmp_path: Path):
    import hashlib
    import json

    conteudo = dbc_do_sih([internacao()] * 12)
    _carregar(sus.SIH, {"RDAC2607.dbc": conteudo}, tmp_path, PRIMEIRA)
    manifesto = json.loads(
        (tmp_path / "sus_internacoes" / "202607.json").read_text(encoding="utf-8")
    )
    texto = json.dumps(manifesto)
    assert hashlib.sha256(conteudo).hexdigest() in texto
    assert "RDAC2607.dbc" in texto


def test_olhar_de_novo_sem_dado_novo_nao_empurra_a_data(tmp_path: Path):
    arquivos = {"RDAC2607.dbc": dbc_do_sih([internacao()] * 12)}
    _carregar(sus.SIH, arquivos, tmp_path, PRIMEIRA)
    assert _carregar(sus.SIH, arquivos, tmp_path, DEPOIS) == (IGUAL, IGUAL)
    tabela = ler_tabela(tmp_path / "sus_internacoes" / "202607.parquet")
    assert tabela.loc[0, "disponivel_em"] == pd.Timestamp(PRIMEIRA)


def test_reprocesso_vira_versao_com_data_nova(tmp_path: Path):
    _carregar(
        sus.SIH, {"RDAC2607.dbc": dbc_do_sih([internacao()] * 12)}, tmp_path, PRIMEIRA
    )
    novo = {"RDAC2607.dbc": dbc_do_sih([internacao()] * 15)}
    assert _carregar(sus.SIH, novo, tmp_path, DEPOIS)[0] == GRAVADO
    tabela = ler_tabela(tmp_path / "sus_internacoes" / "202607.parquet")
    assert tabela.loc[0, "internacoes"] == 15
    assert tabela.loc[0, "disponivel_em"] == pd.Timestamp(DEPOIS)
    versoes = [
        p
        for p in (tmp_path / "sus_internacoes").rglob("*.parquet")
        if p.name != "202607.parquet"
    ]
    assert versoes, "a versão anterior fica guardada"


def test_cortar_o_futuro_nao_muda_o_passado(tmp_path: Path):
    """O que foi visto em PRIMEIRA continua igual quando se filtra pela data, depois do reprocesso."""
    _carregar(
        sus.SIH, {"RDAC2607.dbc": dbc_do_sih([internacao()] * 12)}, tmp_path, PRIMEIRA
    )
    antes = ler_tabela(tmp_path / "sus_internacoes" / "202607.parquet")
    _carregar(
        sus.SIH, {"RDAC2607.dbc": dbc_do_sih([internacao()] * 15)}, tmp_path, DEPOIS
    )
    depois = ler_tabela(tmp_path / "sus_internacoes" / "202607.parquet")
    assert not (depois["disponivel_em"] <= pd.Timestamp(PRIMEIRA)).any()
    assert (antes["disponivel_em"] <= pd.Timestamp(PRIMEIRA)).all()


def test_competencia_nao_publicada_grava_so_a_situacao(tmp_path: Path):
    resultado = _carregar(sus.SIH, {}, tmp_path, PRIMEIRA)
    situacao = ler_tabela(tmp_path / "sus_competencias" / "sih-202607.parquet")
    assert situacao.loc[0, "situacao"] == sus.COMPETENCIA_VAZIA
    assert resultado[0] == carga_sus.SEM_DADOS
    assert not (tmp_path / "sus_internacoes").exists()


def test_main_por_sistema_e_competencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    chamadas: list[tuple[str, int]] = []

    def falso(sistema, competencia, saida, coletado_em, **_):
        chamadas.append((sistema.nome, competencia))
        assert saida == tmp_path
        return (GRAVADO, GRAVADO)

    monkeypatch.setattr(carga_sus, "carregar_competencia", falso)
    monkeypatch.setattr(carga_sus, "exigir_versao_do_codigo", lambda: "teste")
    argumentos = [
        "--sistema",
        "sia",
        "--competencia",
        "202607",
        "--competencia",
        "202608",
    ]
    assert carga_sus.main([*argumentos, "--pasta", str(tmp_path)]) == 0
    assert chamadas == [("sia", 202607), ("sia", 202608)]


def test_main_devolve_1_quando_uma_competencia_falha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def falha(*_args, **_kwargs):
        raise ValueError("UFs ainda sem arquivo: AP")

    monkeypatch.setattr(carga_sus, "carregar_competencia", falha)
    monkeypatch.setattr(carga_sus, "exigir_versao_do_codigo", lambda: "teste")
    assert (
        carga_sus.main(
            ["--sistema", "sih", "--competencia", "202607", "--pasta", str(tmp_path)]
        )
        == 1
    )


def test_fonte_e_do_datasus_e_nao_treina():
    for sistema in (sus.SIH, sus.SIA):
        assert sistema.fonte.startswith("ms-")
        assert coletas.licenca_da_fonte(sistema.fonte)
        assert not coletas.pode_usar("treinar", sistema.fonte)
        assert coletas.pode_usar(coletas.MOSTRAR, sistema.fonte)


def test_manifesto_leva_a_familia_ms_pelo_endereco_do_ftp(tmp_path: Path):
    """As origens são `ftp://ftp.datasus.gov.br/...`: a licença do manifesto sai do DATASUS, não "a confirmar"."""
    import json

    _carregar(
        sus.SIH, {"RDAC2607.dbc": dbc_do_sih([internacao()] * 12)}, tmp_path, PRIMEIRA
    )
    manifesto = json.loads(
        (tmp_path / "sus_internacoes" / "202607.json").read_text(encoding="utf-8")
    )
    assert list(manifesto["licenca"]["fontes"]) == ["ms"]
    assert "sem_fonte" not in manifesto["licenca"]


def test_dicionario_diz_os_limites_da_supressao_de_base_sus():
    """O dicionário não importa `base/sus.py`: o texto dos limites tem de bater com as constantes."""
    from base.dicionario import TABELAS

    texto = " ".join(
        descricao
        for nome in ("sus_internacoes", "sus_ambulatorial")
        for descricao, _ in TABELAS[nome].colunas.values()
    )
    assert f"menos de {sus.MINIMO_PARA_PUBLICAR} " in texto
    assert f"menos de {sus.MINIMO_PARA_OBITOS}" in texto


def test_situacao_das_coletas_e_so_interna():
    """`registros` menos a soma publicada revelaria a célula suprimida: fora do site, da porta e da API."""
    from base import vitrine
    from base.contrato import catalogo
    from base.porta.duckdb import ARQUIVOS, FORA_DA_PORTA

    completo = catalogo()
    publico = vitrine.catalogo_publico(
        completo, montadas=frozenset(completo["tabelas"])
    )
    assert carga_sus.PASTA_DA_SITUACAO in completo["tabelas"]
    assert carga_sus.PASTA_DA_SITUACAO not in publico["tabelas"]
    assert carga_sus.PASTA_DA_SITUACAO in FORA_DA_PORTA
    assert carga_sus.PASTA_DA_SITUACAO not in ARQUIVOS
    for pasta in carga_sus.PASTA_DA_TABELA.values():
        assert pasta in publico["tabelas"]
        assert pasta in ARQUIVOS
