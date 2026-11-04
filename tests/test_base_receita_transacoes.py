"""Transações tributárias da Receita: pessoa física fora, chave, hash da linha e `disponivel_em`."""

import io
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base import licenca
from base import receita_transacoes as transacoes
from scripts import carga_receita_transacoes as carga

AMOSTRAS = Path(__file__).resolve().parent.parent / "dados_de_exemplo" / "receita"
MODIFICADO = date(2026, 10, 13)
CABECALHO_ADESAO = b"A;B;C;D;E;F;G;H;I;J\r\n"
LINHA_ADESAO = "11.222.333/0001-81;PRLF 2023 art. 11 I (Geral);31/07/2023;3057774,82;1987553,63;0,00;0,00;0,00;0,00;6\r\n"


def _individual(bruto: bytes | None = None, contagem=None) -> pd.DataFrame:
    conteudo = (
        bruto
        if bruto is not None
        else (AMOSTRAS / "transacoes_individual_amostra.csv").read_bytes()
    )
    return transacoes.ler_individual(io.BytesIO(conteudo), MODIFICADO, contagem)


def _adesao(bruto: bytes | None = None, contagem=None) -> pd.DataFrame:
    conteudo = (
        bruto
        if bruto is not None
        else (AMOSTRAS / "transacoes_adesao_amostra.csv").read_bytes()
    )
    return transacoes.ler_adesao(io.BytesIO(conteudo), MODIFICADO, contagem)


def test_individual_descarta_cpf_mascarado_e_nao_guarda_o_nome_dele():
    contagem = transacoes.Contagem()
    tabela = _individual(contagem=contagem)
    assert len(tabela) == 2
    assert (contagem.lidas, contagem.sem_cnpj_descartadas) == (3, 1)
    assert not tabela["contribuinte"].str.contains("PESSOA F").any()
    assert list(tabela["cnpj"]) == ["11222333000181", "44555666000100"]


def test_individual_valores_com_ponto_de_milhar_e_data_so_com_mes():
    alfa = _individual().iloc[0]
    assert alfa["divida_transacionada"] == 1890254972
    assert alfa["saldo_devedor"] == 663641387
    assert pd.isna(alfa["creditos_pf_bcn"])
    assert alfa["data_acordo"] == pd.Timestamp(2023, 10, 1)
    assert alfa["contribuinte"].endswith("RECUPERAÇÃO JUDICIAL")


def test_individual_disponivel_em_e_a_data_passada():
    assert set(_individual()["disponivel_em"]) == {pd.Timestamp(MODIFICADO)}


def test_individual_chave_repetida_levanta_erro():
    bruto = (AMOSTRAS / "transacoes_individual_amostra.csv").read_bytes()
    repetida = "OUTRO;11.222.333/0001-81;10000.000001/2023-01;out/23;1;1;1;;1\r\n"
    with pytest.raises(ValueError, match="chave repetida"):
        _individual(bruto + repetida.encode())


def test_individual_data_torta_e_campos_a_menos_levantam_erro():
    cabecalho = "C;D;P;Data;V;R;D;C;S\r\n"
    with pytest.raises(ValueError, match="mmm/aa"):
        _individual(
            (cabecalho + "A;11.222.333/0001-81;P;13/2023;1;1;1;;1\r\n").encode()
        )
    with pytest.raises(ValueError, match="campos"):
        _individual((cabecalho + "A;11.222.333/0001-81\r\n").encode())


def test_individual_cpf_inteiro_tambem_e_descartado():
    cabecalho = "C;D;P;Data;V;R;D;C;S\r\n"
    contagem = transacoes.Contagem()
    tabela = _individual(
        (cabecalho + "FULANO;123.456.789-09;P;jan/24;1;1;1;;1\r\n").encode(), contagem
    )
    assert tabela.empty and contagem.sem_cnpj_descartadas == 1


def test_adesao_le_latin1_e_descarta_o_cpf_mascarado():
    contagem = transacoes.Contagem()
    tabela = _adesao(contagem=contagem)
    assert len(tabela) == 3
    assert (contagem.lidas, contagem.sem_cnpj_descartadas) == (5, 2)
    primeira = tabela.iloc[0]
    assert primeira["cnpj"] == "11222333000181"
    assert primeira["divida_sem_reducao"] == 3057774.82
    assert primeira["data_requerimento"] == pd.Timestamp(2023, 7, 31)
    assert primeira["parcelas"] == 6


def test_adesao_nao_guarda_nada_de_pessoa_fisica():
    tabela = _adesao()
    assert tabela["cnpj"].str.len().eq(14).all()
    assert "*" not in tabela.to_csv()


def test_adesao_linhas_identicas_ficam_com_hash_diferente():
    contagem = transacoes.Contagem()
    tabela = _adesao(contagem=contagem)
    assert contagem.identicas_numeradas == 1
    assert tabela["hash_linha"].is_unique
    beta = tabela[tabela["cnpj"] == "44555666000100"]
    assert len(beta) == 2


def test_adesao_hash_e_estavel_e_nao_depende_da_ordem_das_outras_linhas():
    sozinha = _adesao(CABECALHO_ADESAO + LINHA_ADESAO.encode("latin-1"))
    de_novo = _adesao(
        CABECALHO_ADESAO
        + b"44.555.666/0001-00;X;03/03/2023;1,00;0,00;0,00;0,00;0,00;0,00;1\r\n"
        + LINHA_ADESAO.encode("latin-1")
    )
    hash_sozinha = sozinha.iloc[0]["hash_linha"]
    assert hash_sozinha in set(de_novo["hash_linha"])
    assert len(hash_sozinha) == 64


def test_adesao_disponivel_em_e_o_periodo_fica_a_parte():
    tabela = _adesao()
    assert set(tabela["disponivel_em"]) == {pd.Timestamp(MODIFICADO)}
    assert "data_requerimento" in tabela.columns


def test_adesao_data_torta_e_campos_a_menos_levantam_erro():
    with pytest.raises(ValueError):
        _adesao(
            CABECALHO_ADESAO + LINHA_ADESAO.replace("31/07/2023", "2023-07").encode()
        )
    with pytest.raises(ValueError, match="campos"):
        _adesao(CABECALHO_ADESAO + b"11.222.333/0001-81;X\r\n")


def test_data_de_atualizacao_sai_da_pagina_do_arquivo():
    pagina = '<div>Atualizado em</div><div class="x"> 13/10/2026 10h48 </div>'
    assert carga.data_de_atualizacao(pagina) == date(2026, 10, 13)
    with pytest.raises(RuntimeError):
        carga.data_de_atualizacao("<html>sem data</html>")


def test_endereco_das_transacoes_tem_familia_propria_e_nao_a_geral_da_receita():
    url = f"{carga.RAIZ}transacoes-adesao.csv/@@download/file"
    assert licenca.familia_do_endereco(url) == "rfb-transacoes"
    outra = "https://www.gov.br/receitafederal/pt-br/assuntos/x.xlsx"
    assert licenca.familia_do_endereco(outra) == "rfb"


def test_baixar_recusa_pasta_que_nao_esta_vazia(tmp_path):
    (tmp_path / "ja_tem.txt").write_text("x")
    with pytest.raises(SystemExit):
        carga.baixar(tmp_path)


def test_carga_grava_os_dois_parquets_sem_pessoa_fisica(tmp_path):
    origem, saida = tmp_path / "origem", tmp_path / "saida"
    origem.mkdir()
    (origem / carga.ARQUIVO_INDIVIDUAL).write_bytes(
        (AMOSTRAS / "transacoes_individual_amostra.csv").read_bytes()
    )
    (origem / carga.ARQUIVO_ADESAO).write_bytes(
        (AMOSTRAS / "transacoes_adesao_amostra.csv").read_bytes()
    )
    (origem / carga.MODIFICADOS).write_text(
        json.dumps(
            {carga.ARQUIVO_INDIVIDUAL: "2026-07-28", carga.ARQUIVO_ADESAO: "2026-10-13"}
        ),
        encoding="utf-8",
    )
    assert carga.carregar_individual(origem, saida) == "gravado"
    assert carga.carregar_adesao(origem, saida) == "gravado"
    assert carga.carregar_adesao(origem, saida) == "igual"
    individual = pd.read_parquet(saida / "receita" / "transacoes_individual.parquet")
    adesao = pd.read_parquet(saida / "receita" / "transacoes_adesao.parquet")
    assert len(individual) == 2 and len(adesao) == 3
    assert individual["disponivel_em"].iloc[0] == pd.Timestamp(2026, 7, 28)
    assert adesao["disponivel_em"].iloc[0] == pd.Timestamp(2026, 10, 13)
    manifesto = json.loads(
        (saida / "receita" / "transacoes_adesao.json").read_text(encoding="utf-8")
    )
    assert "vendável" not in json.dumps(manifesto["licenca"], ensure_ascii=False)
