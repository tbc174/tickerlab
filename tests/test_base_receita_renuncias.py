"""DIRBI e ECF da Receita: leitura em fluxo por posição, chave, CNPJ mascarado e `disponivel_em`."""

import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base import licenca
from base import receita_renuncias as renuncias
from scripts import carga_receita_renuncias as carga

AMOSTRAS = Path(__file__).resolve().parent.parent / "dados_de_exemplo" / "receita"
MODIFICADO = date(2026, 9, 8)
CABECALHO = b"CNPJ,Nome,M,UF,C,Mes,Ano,Cod,Tributo,Valor\r\n"


def _dirbi(
    bruto: bytes | None = None, contagem: renuncias.Contagem | None = None
) -> pd.DataFrame:
    conteudo = (
        bruto if bruto is not None else (AMOSTRAS / "dirbi_amostra.csv").read_bytes()
    )
    return renuncias.ler_dirbi(io.BytesIO(conteudo), MODIFICADO, contagem)


def _ecf(
    bruto: bytes | None = None, contagem: renuncias.Contagem | None = None
) -> pd.DataFrame:
    conteudo = (
        bruto if bruto is not None else (AMOSTRAS / "ecf_amostra.csv").read_bytes()
    )
    return renuncias.ler_ecf(io.BytesIO(conteudo), date(2026, 9, 19), contagem)


def test_dirbi_le_por_posicao_e_descarta_o_cnpj_mascarado():
    contagem = renuncias.Contagem()
    tabela = _dirbi(contagem=contagem)
    assert len(tabela) == 4
    assert (contagem.lidas, contagem.mascaradas) == (5, 1)
    primeira = tabela.iloc[0]
    assert primeira["cnpj"] == "11222333000181"
    assert primeira["municipio"] == "SÃO PAULO"
    assert (primeira["ano"], primeira["mes"], primeira["codigo_in"]) == (2026, 1, "79")
    assert primeira["valor"] == 32082.5


def test_dirbi_nome_com_virgula_e_sufixo_de_verificacao():
    tabela = _dirbi()
    beta = tabela[tabela["cnpj"] == "44555666000100"].iloc[0]
    assert beta["nome"] == "EXEMPLO BETA, COMERCIO LTDA"
    assert bool(beta["em_verificacao"])
    assert not bool(tabela.iloc[0]["em_verificacao"])


def test_dirbi_corpo_em_latin1_tambem_le():
    texto = (AMOSTRAS / "dirbi_amostra.csv").read_text(encoding="utf-8")
    assert _dirbi(texto.encode("latin-1")).iloc[0]["municipio"] == "SÃO PAULO"


def test_dirbi_disponivel_em_e_o_last_modified_e_o_periodo_fica_a_parte():
    tabela = _dirbi()
    assert set(tabela["disponivel_em"]) == {pd.Timestamp(MODIFICADO)}
    assert {"ano", "mes"} <= set(tabela.columns)


def test_dirbi_chave_repetida_levanta_erro():
    bruto = (AMOSTRAS / "dirbi_amostra.csv").read_bytes()
    repetida = b'11.222.333/0001-81,OUTRO,SP,SP,1,1,2026,79,Cofins,"1,0"\r\n'
    with pytest.raises(ValueError, match="repetid"):
        _dirbi(bruto + repetida)


def test_dirbi_mes_fora_de_1_a_12_e_campos_a_menos_levantam_erro():
    with pytest.raises(ValueError):
        _dirbi(CABECALHO + b'11.222.333/0001-81,A,B,SP,1,13,2026,79,Cofins,"1,0"\r\n')
    with pytest.raises(ValueError):
        _dirbi(CABECALHO + b"11.222.333/0001-81,A,B\r\n")


def test_dirbi_por_mes_reparte_mesmo_com_os_meses_misturados():
    partes = dict(renuncias.dirbi_por_mes(_dirbi()))
    assert sorted(partes) == [(2026, 1), (2026, 2)]
    assert len(partes[(2026, 1)]) == 3


def test_dirbi_valor_vazio_fica_nao_declarado():
    tabela = _dirbi(CABECALHO + b"11.222.333/0001-81,A,B,SP,1,1,2026,79,Cofins,\r\n")
    assert tabela["valor"].isna().all()


def test_ecf_uma_linha_por_chave_e_repetida_inteira_sai():
    contagem = renuncias.Contagem()
    tabela = _ecf(contagem=contagem)
    assert len(tabela) == 3
    assert contagem.repetidas == 1
    assert not tabela.duplicated(renuncias.CHAVE_DA_ECF).any()
    beta = tabela[tabela["cnpj"] == "44555666000100"]
    assert len(beta) == 2 and set(beta["exercicio"]) == {2024}


def test_ecf_vazio_e_nao_declarado_e_zero_e_zero():
    alfa = _ecf().iloc[0]
    assert alfa["horario_eleitoral_deducao_lalur"] == 0
    assert pd.isna(alfa["prouni_universidade_para_todos"])
    assert alfa["pat_deducao_ir"] == 295891.94
    assert alfa["dt_ini"] == pd.Timestamp(2025, 1, 1)


def test_ecf_mesma_chave_com_valores_diferentes_fica_a_mais_preenchida():
    linhas = (AMOSTRAS / "ecf_amostra.csv").read_text(encoding="utf-8").splitlines()
    alfa = linhas[1].split("|")
    vazia = list(alfa)
    inicio = len(renuncias.COLUNAS_DE_IDENTIFICACAO_DA_ECF)
    vazia[inicio:-1] = [""] * len(renuncias.COLUNAS_DE_BENEFICIO_DA_ECF)
    bruto = "\n".join([linhas[0], "|".join(vazia), "|".join(alfa)]) + "\n"
    contagem = renuncias.Contagem()
    tabela = _ecf(bruto.encode(), contagem)
    assert len(tabela) == 1 and contagem.conflitantes == 1
    assert tabela.iloc[0]["pat_deducao_ir"] == 295891.94


def test_ecf_em_formato_longo_so_com_beneficio_diferente_de_zero():
    longa = renuncias.beneficios_declarados(_ecf())
    assert set(longa["beneficio"]) == {
        "pat_deducao_ir",
        "prouni_universidade_para_todos",
    }
    assert (longa["valor"] != 0).all()


def test_endereco_da_receita_tem_familia_propria_e_nao_a_do_cnpj():
    url = f"{carga.ENDERECO_PUBLICO}DIRBI/renuncia-por-regime-2026.zip"
    assert licenca.familia_do_endereco(url) == "rfb-renuncias"
    cnpj = "https://arquivos.receitafederal.gov.br/dados/cnpj/x.zip"
    assert licenca.familia_do_endereco(cnpj) != "rfb-renuncias"


def test_baixar_recusa_pasta_que_nao_esta_vazia(tmp_path):
    (tmp_path / "ja_tem.txt").write_text("x")
    with pytest.raises(SystemExit):
        carga.baixar(tmp_path)


def test_carga_grava_um_parquet_por_mes_e_a_ecf(tmp_path, monkeypatch):
    origem, saida = tmp_path / "origem", tmp_path / "saida"
    origem.mkdir()
    zips = ("renuncia-por-regime-2025.zip", "renuncia-por-regime-2026.zip")
    amostra = (AMOSTRAS / "dirbi_amostra.csv").read_bytes()
    with zipfile.ZipFile(origem / zips[1], "w") as arquivo:
        arquivo.writestr("2026.csv", amostra)
    monkeypatch.setattr(carga, "ARQUIVOS_DO_DIRBI", zips[1:])
    (origem / carga.ARQUIVO_DA_ECF).write_bytes(
        (AMOSTRAS / "ecf_amostra.csv").read_bytes()
    )
    (origem / carga.MODIFICADOS).write_text(
        json.dumps({zips[1]: "2026-09-08", carga.ARQUIVO_DA_ECF: "2026-09-19"}),
        encoding="utf-8",
    )
    assert carga.carregar_dirbi(origem, saida) == {
        "202601": "gravado",
        "202602": "gravado",
    }
    assert carga.carregar_ecf(origem, saida) == "gravado"
    assert carga.carregar_dirbi(origem, saida) == {"202601": "igual", "202602": "igual"}
    janeiro = pd.read_parquet(saida / "receita" / "dirbi" / "202601.parquet")
    assert len(janeiro) == 3
    ecf = pd.read_parquet(saida / "receita" / "ecf_renuncia.parquet")
    assert len(ecf) == 3
    manifesto = json.loads(
        (saida / "receita" / "ecf_renuncia.json").read_text(encoding="utf-8")
    )
    assert "vendável" not in json.dumps(manifesto["licenca"], ensure_ascii=False)
