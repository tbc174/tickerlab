"""Carga offline com retratos minúsculos e todas as chaves inventadas."""

import json
from datetime import UTC, datetime
from itertools import pairwise

import pandas as pd
import pytest

from base import receita_diff, socios_pf
from base.cnpj import digitos_verificadores
from base.dicionario import TABELAS
from base.parquet import como_no_disco, conferir_tabela
from base.porta import Porta
from base.porta.duckdb import ARQUIVOS, conectar
from scripts import montar_movimento_socios_pf as script
from tests.test_movimento_socios_pf import EMPRESA, MESES, OUTRA, montar, retratos

AGORA = datetime(2026, 11, 27, tzinfo=UTC)


@pytest.fixture
def acervo(tmp_path, monkeypatch):
    monkeypatch.setattr(
        script, "exigir_versao_do_codigo", lambda: "a" * 40, raising=False
    )
    monkeypatch.setattr(
        script, "espaco_do_disco", lambda _: (200 * 1024**3, 150 * 1024**3)
    )
    cnpj, destino = tmp_path / "cnpj", tmp_path / "base"
    quadros = retratos()
    qsa = cnpj / "vigente" / "qsa"
    qsa.mkdir(parents=True)
    for prefixo, parte in quadros[MESES[-1]].groupby(
        quadros[MESES[-1]].cnpj_basico.str[:2]
    ):
        parte.to_parquet(qsa / f"{prefixo}.parquet", index=False)
    pasta = cnpj / "mudancas" / "qsa"
    pasta.mkdir(parents=True)
    contagens = dict.fromkeys(MESES, 0)
    for a, b in pairwise(MESES):
        diff = receita_diff.diff(quadros[a], quadros[b], receita_diff.CHAVE_DO_QSA, b)
        diff.to_parquet(pasta / f"{b}.parquet", index=False)
        contagens[b] = len(diff)
    manifesto = {
        "meses": {
            m: {
                "arquivos": {"Socios0.zip": "a" * 64},
                "mudancas": {"qsa": contagens[m]},
            }
            for m in MESES
        }
    }
    (cnpj / script.MANIFESTO).write_text(json.dumps(manifesto), encoding="utf-8")
    lista = destino / script.ESTABELECIMENTOS
    lista.mkdir(parents=True)
    for raiz in (EMPRESA, OUTRA):
        base = raiz + "0001"
        pd.DataFrame(
            {
                "cnpj": [base + digitos_verificadores(base)],
                "cnpj_basico": [raiz],
                "mes_do_retrato": [MESES[-1]],
            }
        ).to_parquet(lista / f"{raiz[:2]}.parquet", index=False)
    return cnpj, destino


def rodar(acervo, *extras):
    cnpj, destino = acervo
    return script.main(
        ["--cnpj", str(cnpj), "--destino", str(destino), *extras], agora=lambda: AGORA
    )


def test_grava_so_contagens_com_manifesto_e_credito(acervo, capsys):
    assert rodar(acervo) == 0
    arquivos = sorted((acervo[1] / socios_pf.TABELA).glob("*.parquet"))
    resultado = pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)
    pd.testing.assert_frame_equal(resultado[socios_pf.COLUNAS], como_no_disco(montar()))
    assert set(resultado) == set(TABELAS[socios_pf.TABELA].colunas)
    for arquivo in arquivos:
        assert conferir_tabela(arquivo)
        manifesto = arquivo.with_suffix(".json").read_text(encoding="utf-8")
        assert "Socios0.zip" in manifesto
        assert "id_pessoa" not in manifesto and "***" not in manifesto
    assert "***" not in capsys.readouterr().out


def test_repetir_retrato_nao_regrava_nem_cria_versao(acervo):
    assert rodar(acervo) == 0
    pasta = acervo[1] / socios_pf.TABELA
    antes = {p.name: p.stat().st_mtime_ns for p in pasta.iterdir()}
    script.montar(*acervo, datetime(2026, 11, 28, tzinfo=UTC))
    assert antes == {p.name: p.stat().st_mtime_ns for p in pasta.iterdir()}


def test_ensaio_nao_grava(acervo):
    assert rodar(acervo, "--ensaio") == 0
    assert not (acervo[1] / socios_pf.TABELA).exists()


@pytest.mark.parametrize("total,livre", [(200, 40), (1000, 200)])
def test_freio_para_antes_de_gravar(acervo, monkeypatch, total, livre):
    monkeypatch.setattr(
        script, "espaco_do_disco", lambda _: (total * 1024**3, livre * 1024**3)
    )
    assert rodar(acervo) == 1
    assert not (acervo[1] / socios_pf.TABELA).exists()


def test_lista_de_outro_mes_para_sem_publicar(acervo):
    arquivo = acervo[1] / script.ESTABELECIMENTOS / "11.parquet"
    tabela = pd.read_parquet(arquivo).assign(mes_do_retrato="2023-07")
    tabela.to_parquet(arquivo, index=False)
    assert rodar(acervo) == 1
    assert not (acervo[1] / socios_pf.TABELA).exists()


def test_mudancas_ausentes_nao_viram_mes_sem_movimentos(acervo):
    (acervo[0] / "mudancas" / "qsa" / "2023-06.parquet").unlink()
    assert rodar(acervo) == 1
    assert not (acervo[1] / socios_pf.TABELA).exists()


def test_mes_repartido_em_arquivos_por_prefixo(acervo):
    pasta = acervo[0] / "mudancas" / "qsa"
    arquivo = pasta / "2023-06.parquet"
    tabela = pd.read_parquet(arquivo)
    (pasta / "2023-06").mkdir()
    for prefixo, parte in tabela.groupby(tabela.cnpj_basico.str[:2]):
        parte.to_parquet(pasta / "2023-06" / f"{prefixo}.parquet", index=False)
    arquivo.unlink()
    assert rodar(acervo) == 0


def test_raiz_retirada_da_lista_nao_sobra_na_particao_antiga(acervo):
    assert rodar(acervo) == 0
    (acervo[1] / script.ESTABELECIMENTOS / "22.parquet").unlink()
    assert rodar(acervo) == 0
    assert pd.read_parquet(acervo[1] / socios_pf.TABELA / "22.parquet").empty


def test_erro_nao_copia_identificador_para_saida(acervo, capsys):
    arquivo = acervo[0] / "vigente" / "qsa" / "11.parquet"
    tabela = pd.read_parquet(arquivo).drop(columns="tipo_socio")
    tabela.to_parquet(arquivo, index=False)
    assert rodar(acervo) == 1
    saida = capsys.readouterr().out
    assert "FALHAS" in saida and "***" not in saida and "sintético" not in saida


def test_guarda_de_faixa_nao_publica_prefixo_antes_de_conferir_mes(
    acervo, monkeypatch, capsys
):
    monkeypatch.setattr(
        script,
        "MAXIMO_POR_MES",
        {"socios_pf_entraram": 0, "socios_pf_sairam": 0},
        raising=False,
    )
    assert rodar(acervo) == 1
    assert not (acervo[1] / socios_pf.TABELA).exists()
    assert "2023-06" in capsys.readouterr().out


def test_guarda_nao_reprova_mes_ja_gravado(acervo, monkeypatch):
    assert rodar(acervo) == 0
    monkeypatch.setattr(
        script,
        "MAXIMO_POR_MES",
        {"socios_pf_entraram": 0, "socios_pf_sairam": 0},
        raising=False,
    )
    assert rodar(acervo) == 0


def test_ensaio_imprime_totais_por_mes_sem_identificador(acervo, capsys):
    assert rodar(acervo, "--ensaio") == 0
    saida = capsys.readouterr().out
    assert "2023-07: entraram=0 sairam=2" in saida
    assert "sem_correcao" in saida and "com_correcao" in saida
    assert "***" not in saida and EMPRESA not in saida


def test_versao_desconhecida_interrompe_sem_gravar(acervo, monkeypatch):
    from src.versao_do_codigo import VersaoDesconhecidaError

    def desconhecida():
        raise VersaoDesconhecidaError("sem commit")

    monkeypatch.setattr(script, "exigir_versao_do_codigo", desconhecida, raising=False)
    assert rodar(acervo) == 1
    assert not (acervo[1] / socios_pf.TABELA).exists()


def test_freio_e_conferido_de_novo_antes_de_cada_gravacao(acervo, monkeypatch):
    disco = iter([(200, 150), (200, 150), (200, 40)])
    monkeypatch.setattr(
        script, "espaco_do_disco", lambda _: tuple(n * 1024**3 for n in next(disco))
    )
    assert rodar(acervo) == 1
    assert not (acervo[1] / socios_pf.TABELA).exists()


def test_freio_tambem_antes_de_publicar_cada_prefixo(acervo, monkeypatch):
    # Início, dois temporários, primeira publicação, segunda publicação (sem espaço).
    disco = iter([(200, 150)] * 4 + [(200, 40)])
    monkeypatch.setattr(
        script, "espaco_do_disco", lambda _: tuple(n * 1024**3 for n in next(disco))
    )
    assert rodar(acervo) == 1
    pasta = acervo[1] / socios_pf.TABELA
    assert (pasta / "11.parquet").exists()
    assert not (pasta / "22.parquet").exists()


def test_guarda_preserva_tabela_anterior_e_limpa_temporarios(acervo, monkeypatch):
    assert rodar(acervo) == 0
    pasta = acervo[1] / socios_pf.TABELA
    antes = {p.name: p.read_bytes() for p in pasta.iterdir()}
    # Trata todos os meses como novos para exercitar a guarda diante de uma tabela existente.
    monkeypatch.setattr(script, "_meses_gravados", lambda _: set())
    monkeypatch.setattr(
        script, "MAXIMO_POR_MES", {"socios_pf_entraram": 0, "socios_pf_sairam": 0}
    )
    assert rodar(acervo) == 1
    assert antes == {p.name: p.read_bytes() for p in pasta.iterdir()}
    assert not list(acervo[1].glob("movimento-pf-*"))


def test_porta_le_publicacao_no_fim_do_mes_e_nenhum_id(acervo):
    assert rodar(acervo) == 0
    nome = socios_pf.TABELA
    with conectar(
        acervo[1], tabelas={nome: TABELAS[nome]}, arquivos={nome: ARQUIVOS[nome]}
    ) as con:
        tabela = con.execute(
            f"SELECT * FROM {nome} WHERE publico_em <= DATE '2023-06-29'"
        ).df()
        assert set(tabela.mes_do_retrato) == {"2023-05"}
        assert not {"id_pessoa", "nome", "cpf"} & set(tabela)
    with Porta(
        acervo[1], tabelas={nome: TABELAS[nome]}, arquivos={nome: ARQUIVOS[nome]}
    ) as porta:
        consulta = porta.ler(
            nome, como_era_em="2023-06-30", filtros={"cnpj_basico": EMPRESA}
        )
        assert set(consulta.mes_do_retrato) == {"2023-05", "2023-06"}
        assert list(consulta.socios_pf_entraram) == [0, 1]
