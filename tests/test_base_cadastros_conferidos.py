"""Tabelas da conferência de 14/11/2026 (base/cadastros_conferidos.py, linha 904, PR 1): regime tributário da
ECF, PAT, TAH, PADOs, homologados e tancagem. Só pessoa jurídica, sem coluna de nome, número com vírgula, data
nos dois formatos e sem olhar o futuro. Arquivos de mentira no formato conferido em 14/11/2026; nenhum documento
real (o CPF é o de teste, montado na hora)."""

import hashlib
import io
import zipfile
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from base import cadastros_conferidos as conferidos
from base import cadastros_em_retrato as montagem
from base import cnpj as cnpjs
from base.arquivo import lote_conferidas_14_11 as arquivista
from base.parquet import LINHAGEM
from src.banco import coletas
from src.banco.coletas import com_registro
from tests.ajudantes_de_cpf import CPF_DE_TESTE, no_formato

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
DIA = date(2026, 11, 14)
DIA_SEGUINTE = date(2026, 12, 14)
# o nome do produto (`nome_comercial`) fica; o de quem quer que seja, não
PROIBIDAS = (
    "nome_d",
    "razao",
    "cpf",
    "empresa",
    "grupo_economico",
    "titular",
    "nmpessoa",
)
NOME_INVENTADO = "EMPRESA INVENTADA DE TESTE LTDA"
CPF_MASCARADO = no_formato(CPF_DE_TESTE, "***.ddd.ddd-**")


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        if cnpjs.dv_confere(bruto := f"{raiz}{filial}{dv:02d}"):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
OUTRA = _cnpj("22333444")
MEI = _cnpj("44555666")
SCP = _cnpj("55666777")
DV_ERRADO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)


def _formatado(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def _sem_nome_e_sem_cpf(tabela: pd.DataFrame) -> None:
    assert not [c for c in tabela.columns if any(p in c.lower() for p in PROIBIDAS)]
    texto = set(tabela.astype(str).to_numpy().ravel())
    assert not {NOME_INVENTADO, CPF_DE_TESTE, CPF_MASCARADO} & texto


def _csv(cabecalho: list[str], linhas: list[list[str]], separador: str = ";") -> str:
    return "\n".join(separador.join(linha) for linha in [cabecalho, *linhas])


# --- Receita: ECF ------------------------------------------------------------------------------------------
def _ecf(*linhas: tuple[str, str, str, str, str]) -> bytes:
    """Cada linha: (ano, cnpj, cnpj da SCP, forma, escriturações); um ZIP com o CSV de vírgula."""
    texto = _csv(
        list(conferidos.COLUNAS_DA_ECF), [list(linha) for linha in linhas], ","
    )
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr("ecf_lucro_presumido.csv", ("﻿" + texto).encode("utf-8"))
    return saida.getvalue()


def test_regime_so_cnpj_com_dv_e_a_scp_formatada():
    tabela, contagem = conferidos.ler_regime(
        _ecf(
            ("2024", _formatado(EMPRESA), "", "LUCRO PRESUMIDO", "1"),
            ("2024", EMPRESA, SCP, "LUCRO PRESUMIDO", "2"),
            ("2024", CPF_DE_TESTE, "", "LUCRO PRESUMIDO", "1"),
            ("2024", DV_ERRADO, "", "LUCRO PRESUMIDO", "1"),
            ("2023", EMPRESA, "", "LUCRO PRESUMIDO", "1"),
            ("2023", EMPRESA, "", "LUCRO PRESUMIDO", "1"),
        )
    )
    assert (
        contagem["pessoa_fisica"],
        contagem["cnpj_invalido"],
        contagem["id_repetido"],
    ) == (1, 1, 1)
    assert len(tabela) == 3
    assert set(tabela["cnpj_basico"]) == {EMPRESA[:8]}
    assert sorted(tabela["ano"].tolist()) == [2023, 2024, 2024]
    assert set(tabela["cnpj_da_scp"].dropna()) == {_formatado(SCP)}
    assert tabela["escrituracoes"].sum() == 4
    _sem_nome_e_sem_cpf(tabela)


def test_regime_coluna_que_a_receita_tirou_e_erro():
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr("x.csv", f"ano,cnpj\n2024,{EMPRESA}\n")
    with pytest.raises(KeyError, match="forma_de_tributacao"):
        conferidos.ler_regime(saida.getvalue())


def test_regime_zip_sem_csv_e_erro():
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr("leia-me.txt", "nada")
    with pytest.raises(ValueError, match="CSV"):
        conferidos.ler_regime(saida.getvalue())


# --- MTE: PAT ----------------------------------------------------------------------------------------------
def _pat(*linhas: tuple[str, str, str, str]) -> bytes:
    """Cada linha: (cnpj, registro, data do cadastro, total atendido), no CSV que o arquivista grava."""
    corpo = [
        [
            cnpj,
            "MATRIZ",
            "SÃO PAULO",
            "SP",
            registro,
            cadastro,
            "10",
            "2",
            total,
            "ATIVA",
        ]
        for cnpj, registro, cadastro, total in linhas
    ]
    return _csv(list(arquivista.COLUNAS_DO_PAT), corpo).encode("utf-8")


def test_pat_conta_os_trabalhadores_e_le_a_data_nos_dois_formatos():
    tabela, contagem = conferidos.ler_pat(
        _pat(
            (EMPRESA, "R1", "2020-03-04", "12"),
            (OUTRA, "R2", "04/03/2021", ""),
            (CPF_DE_TESTE, "R3", "2020-03-04", "1"),
        )
    )
    assert contagem["pessoa_fisica"] == 1
    por_registro = tabela.set_index("registro_no_pat")
    assert por_registro.loc["R1", "data_do_cadastro"] == pd.Timestamp(2020, 3, 4)
    assert por_registro.loc["R2", "data_do_cadastro"] == pd.Timestamp(2021, 3, 4)
    assert por_registro.loc["R1", "trabalhadores_atendidos"] == 12
    assert pd.isna(por_registro.loc["R2", "trabalhadores_atendidos"])
    assert str(tabela["trabalhadores_ate_5_salarios"].dtype) == "Int64"
    _sem_nome_e_sem_cpf(tabela)


# --- ANM: TAH ----------------------------------------------------------------------------------------------
# formatos medidos nas amostras de 14/11/2026: TAH e PADOs com vírgula decimal e sem ponto de milhar;
# a tancagem de 2026 com ponto decimal (e ";" de separador)
def _tah(*linhas: tuple[str, str, str, str]) -> bytes:
    """Cada linha: (processo, documento, quitação, valor pago), Latin-1 com ";" como o arquivista grava."""
    corpo = [
        [
            processo,
            "2020",
            documento,
            "AUTORIZAÇÃO DE PESQUISA",
            "SÃO PAULO",
            "1234,5",
            quitacao,
            pago,
            "100,00",
        ]
        for processo, documento, quitacao, pago in linhas
    ]
    return _csv(list(arquivista.COLUNAS_DA_TAH), corpo).encode("latin-1")


def test_tah_numero_com_virgula_e_quitacao_vazia_vira_nulo():
    tabela, contagem = conferidos.ler_tah(
        _tah(
            ("1", _formatado(EMPRESA), "31/01/2026", "100,00"),
            ("2", EMPRESA, "", "0,00"),
            ("3", CPF_MASCARADO, "31/01/2026", "10,00"),
            ("4", DV_ERRADO, "31/01/2026", "10,00"),
        )
    )
    # o CPF mascarado não fecha o DV de CPF nem de CNPJ: sai como inválido (o arquivista já o tira antes)
    assert (contagem["pessoa_fisica"], contagem["cnpj_invalido"]) == (0, 2)
    por_processo = tabela.set_index("processo")
    assert por_processo.loc["1", "hectares"] == pytest.approx(1234.5)
    assert por_processo.loc["1", "valor_pago"] == pytest.approx(100.0)
    assert por_processo.loc["1", "data_da_quitacao"] == pd.Timestamp(2026, 1, 31)
    assert pd.isna(por_processo.loc["2", "data_da_quitacao"])
    assert por_processo.loc["2", "fase_do_processo"] == "AUTORIZAÇÃO DE PESQUISA"
    _sem_nome_e_sem_cpf(tabela)


# --- Anatel: PADOs e homologados ---------------------------------------------------------------------------
def _pados(*linhas: tuple[str, str, str, str]) -> bytes:
    """Cada linha: (processo, documento, serviço, multa)."""
    corpo = [
        [
            processo,
            "Principal",
            "Qualidade",
            documento,
            servico,
            "Encerrado",
            "Decisão",
            multa,
            "Pago",
        ]
        for processo, documento, servico, multa in linhas
    ]
    return _csv(list(arquivista.COLUNAS_DOS_PADOS), corpo).encode("utf-8")


def test_pados_a_multa_do_processo_se_repete_por_servico_e_a_linha_igual_e_contada():
    tabela, contagem = conferidos.ler_pados(
        _pados(
            ("P1", EMPRESA, "SMP", "1500,25"),
            ("P1", EMPRESA, "SCM", "1500,25"),
            ("P1", EMPRESA, "SCM", "1500,25"),
            ("P2", EMPRESA, "SMP", ""),
            ("P3", CPF_DE_TESTE, "SMP", "10,00"),
        )
    )
    assert (contagem["pessoa_fisica"], contagem["id_repetido"]) == (1, 1)
    assert len(tabela) == 3
    multas = tabela.groupby("processo")["multa_aplicada"].first()
    assert multas["P1"] == pytest.approx(1500.25)
    assert pd.isna(multas["P2"])
    _sem_nome_e_sem_cpf(tabela)


def _homologados(*linhas: tuple[str, str, str]) -> bytes:
    """Cada linha: (homologação, documento do solicitante, data da homologação)."""
    colunas = list(arquivista.COLUNAS_DOS_HOMOLOGADOS)

    def linha(homologacao: str, documento: str, dia: str) -> list[str]:
        valores = dict.fromkeys(colunas, "x") | {
            "Número de Homologação": homologacao,
            "CNPJ do Solicitante": documento,
            "Data da Homologação": dia,
            "Data do Certificado de Conformidade Técnica": dia,
            "Data de Validade do Certificado": "",
        }
        return [valores[c] for c in colunas]

    return _csv(colunas, [linha(*dados) for dados in linhas]).encode("utf-8")


def test_homologados_so_solicitante_pessoa_juridica_e_validade_vazia_nula():
    tabela, contagem = conferidos.ler_homologados(
        _homologados(
            ("H1", EMPRESA, "2024-05-06 10:00:00"),
            ("H2", EMPRESA, "06/05/2024"),
            ("H3", CPF_DE_TESTE, "2024-05-06"),
        )
    )
    assert contagem["pessoa_fisica"] == 1
    assert set(tabela["data_da_homologacao"]) == {pd.Timestamp(2024, 5, 6)}
    assert tabela["validade_do_certificado"].isna().all()
    _sem_nome_e_sem_cpf(tabela)


def test_coluna_que_a_anatel_tirou_e_erro():
    with pytest.raises(KeyError, match="Multa Aplicada"):
        conferidos.ler_pados(f"Processo;CPF/CNPJ\nP1;{EMPRESA}\n".encode())


# --- ANP: tancagem -----------------------------------------------------------------------------------------
LAYOUT_DE_2025 = [
    "Data",
    "UF",
    "Município",
    "Empresa",
    "CNPJ",
    "CodInstalacao",
    "Segmento",
    "Detalhe Instalação",
    "TAG",
    "Tipo da Unidade",
    "Grupo de Produtos",
    "Tancagem (m³)",
]
LAYOUT_DE_2026 = [
    "DATA",
    "UF",
    "MUNICÍPIO",
    "EMPRESA",
    "CNPJ",
    "CÓDIGO INSTALAÇÃO",
    "SEGMENTO",
    "DETALHE INSTALAÇÃO",
    "TAG",
    "TIPO DA UNIDADE",
    "GRUPO DE PRODUTOS",
    "TANCAGEM (M3)",
]


def _tancagem_de_2025(*linhas: tuple[str, str, str]) -> bytes:
    """UTF-8 com vírgula. Cada linha: (cnpj, tag, tancagem com ponto)."""
    corpo = [
        [
            "2025-12-01",
            "SP",
            "PAULINIA",
            NOME_INVENTADO,
            cnpj,
            "I1",
            "DISTRIBUIDOR",
            "BASE",
            tag,
            "TANQUE",
            "DIESEL",
            tancagem,
        ]
        for cnpj, tag, tancagem in linhas
    ]
    return _csv(LAYOUT_DE_2025, corpo, ",").encode("utf-8")


def _tancagem_de_2026(*linhas: tuple[str, str, str]) -> bytes:
    """Latin-1 com ";". Cada linha: (cnpj, tag, tancagem com ponto decimal)."""
    corpo = [
        [
            "01/01/2026",
            "SP",
            "PAULÍNIA",
            NOME_INVENTADO,
            cnpj,
            "I1",
            "DISTRIBUIDOR",
            "BASE",
            tag,
            "TANQUE",
            "DIESEL",
            tancagem,
        ]
        for cnpj, tag, tancagem in linhas
    ]
    return _csv(LAYOUT_DE_2026, corpo).encode("latin-1")


def test_tancagem_le_os_dois_layouts_e_o_nome_da_empresa_nao_entra():
    antigo, contagem_antiga = conferidos.ler_tancagem(
        _tancagem_de_2025((EMPRESA, "T1", "1500.5"), (DV_ERRADO, "T2", "10"))
    )
    novo, contagem_nova = conferidos.ler_tancagem(
        _tancagem_de_2026(
            (_formatado(EMPRESA), "T1", "1500.5"), (CPF_DE_TESTE, "T9", "1.0")
        )
    )
    assert contagem_antiga["cnpj_invalido"] == 1
    assert contagem_nova["pessoa_fisica"] == 1
    for tabela, dia in (
        (antigo, pd.Timestamp(2025, 12, 1)),
        (novo, pd.Timestamp(2026, 1, 1)),
    ):
        assert list(tabela["tag"]) == ["T1"]
        assert tabela["tancagem_m3"].iloc[0] == pytest.approx(1500.5)
        assert tabela["data_da_posicao"].iloc[0] == dia
        assert tabela["codigo_da_instalacao"].iloc[0] == "I1"
        _sem_nome_e_sem_cpf(tabela)
    assert novo["municipio"].iloc[0] == "PAULÍNIA"


def test_coluna_que_a_anp_tirou_e_erro():
    sem_a_tancagem = _csv(
        LAYOUT_DE_2026[:-1],
        [["01/01/2026", "SP", "X", "Y", EMPRESA, "I1", "S", "D", "T", "U", "G"]],
    )
    with pytest.raises(KeyError, match="tancagem_m3"):
        conferidos.ler_tancagem(sem_a_tancagem.encode("latin-1"))


# --- a montagem: arquivo guardado pelo arquivista → parquet em retrato -------------------------------------
def _coletar(banco, fonte: str, url: str, conteudo: bytes, dia: date) -> None:
    com_registro(fonte, lambda _url: conteudo)(url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(
                coletas.coletas.c.url == url,
                coletas.coletas.c.sha256 == hashlib.sha256(conteudo).hexdigest(),
            )
            .values(baixado_em=datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC))
        )


URL_DA_ECF = arquivista.RAIZ_DA_RECEITA + arquivista.PASTA_DA_ECF + "presumido.zip"
URL_DO_PAT = arquivista.PASTA_DO_PAT + "beneficiarias-2026-11.xlsx"
URL_DA_TANCAGEM = arquivista.PASTA_DA_TANCAGEM + "2026/tancagem-01.csv"


def _coletar_todos(banco, dia: date) -> None:
    _coletar(
        banco,
        "rfb-renuncias-regime-presumido",
        URL_DA_ECF,
        _ecf(
            ("2024", EMPRESA, "", "LUCRO PRESUMIDO", "1"),
            ("2024", MEI, "", "LUCRO PRESUMIDO", "1"),
        ),
        dia,
    )
    _coletar(
        banco,
        "mte-pat-beneficiarias",
        URL_DO_PAT,
        _pat((EMPRESA, "R1", "2020-03-04", "12"), (MEI, "R2", "2020-03-04", "1")),
        dia,
    )
    _coletar(
        banco,
        conferidos.FONTE_DA_TAH,
        arquivista.TAH_DA_ANM,
        _tah(("1", EMPRESA, "31/01/2026", "1,00"), ("2", MEI, "31/01/2026", "1,00")),
        dia,
    )
    _coletar(
        banco,
        conferidos.FONTE_DOS_PADOS,
        arquivista.PADOS_DA_ANATEL,
        _pados(("P1", EMPRESA, "SMP", "1,00"), ("P2", MEI, "SMP", "1,00")),
        dia,
    )
    _coletar(
        banco,
        conferidos.FONTE_DOS_HOMOLOGADOS,
        arquivista.HOMOLOGADOS_DA_ANATEL,
        _homologados(("H1", EMPRESA, "2024-05-06"), ("H2", MEI, "2024-05-06")),
        dia,
    )
    _coletar(
        banco,
        conferidos.FONTE_DA_TANCAGEM,
        URL_DA_TANCAGEM,
        _tancagem_de_2026((EMPRESA, "T1", "1.0"), (MEI, "T2", "1.0")),
        dia,
    )


MONTADOS = {
    "lucro_presumido",
    "beneficiarias",
    "tah",
    "pados",
    "homologados",
    "tancagem",
}


def test_montar_grava_as_seis_tabelas_marca_o_mei_e_vale_desde_o_dia_do_arquivo(
    banco, tmp_path
):
    _coletar_todos(banco, DIA)
    with banco.connect() as conexao:
        resumo = conferidos.montar(conexao, tmp_path, AGORA, pessoas={MEI[:8]})
    assert set(resumo) >= MONTADOS
    for cadastro in conferidos.CADASTROS:
        if cadastro.nome not in MONTADOS:
            continue
        tabela = pd.read_parquet(
            tmp_path / cadastro.tabela / f"{cadastro.nome}.parquet"
        )
        assert list(tabela.columns) == [
            *cadastro.colunas,
            *montagem.CARIMBOS_DA_LINHA,
            *LINHAGEM,
        ]
        _sem_nome_e_sem_cpf(tabela)
        assert dict(
            zip(tabela["cnpj_basico"], tabela["trata_como_pessoa"], strict=True)
        ) == {
            EMPRESA[:8]: False,
            MEI[:8]: True,
        }, cadastro.nome
        assert set(tabela["disponivel_em"]) == {DIA}, (
            cadastro.nome
        )  # o arquivo não diz quando foi publicado


def test_segundo_montar_sem_arquivo_novo_e_ja_montado(banco, tmp_path):
    _coletar_todos(banco, DIA)
    with banco.connect() as conexao:
        conferidos.montar(conexao, tmp_path, AGORA, pessoas=set())
        resumo = conferidos.montar(conexao, tmp_path, AGORA, pessoas=set())
    assert {nome: resumo[nome] for nome in MONTADOS} == dict.fromkeys(
        MONTADOS, montagem.JA_MONTADO
    )


def test_a_tancagem_junta_os_csvs_de_cada_mes_e_cada_linha_vale_do_dia_em_que_a_vimos(
    banco, tmp_path
):
    _coletar(
        banco,
        conferidos.FONTE_DA_TANCAGEM,
        URL_DA_TANCAGEM,
        _tancagem_de_2026((EMPRESA, "T1", "1.0")),
        DIA,
    )
    fevereiro = arquivista.PASTA_DA_TANCAGEM + "2026/tancagem-02.csv"
    _coletar(
        banco,
        conferidos.FONTE_DA_TANCAGEM,
        fevereiro,
        _tancagem_de_2026((OUTRA, "T7", "2.0")),
        DIA_SEGUINTE,
    )
    with banco.connect() as conexao:
        conferidos.montar(conexao, tmp_path, AGORA, pessoas=set())
    tabela = pd.read_parquet(
        tmp_path / conferidos.TABELA_DA_TANCAGEM / "tancagem.parquet"
    )
    primeira_vez = tabela.groupby("cnpj_basico")["disponivel_em"].min().to_dict()
    assert primeira_vez == {EMPRESA[:8]: DIA, OUTRA[:8]: DIA_SEGUINTE}


def test_os_cadastros_cobrem_as_onze_fontes_e_as_seis_tabelas():
    assert {c.fonte for c in conferidos.CADASTROS} == {
        f.id for f in arquivista.fontes()
    }
    assert {c.tabela for c in conferidos.CADASTROS} == {
        conferidos.TABELA_DO_REGIME,
        conferidos.TABELA_DO_PAT,
        conferidos.TABELA_DA_TAH,
        conferidos.TABELA_DOS_PADOS,
        conferidos.TABELA_DOS_HOMOLOGADOS,
        conferidos.TABELA_DA_TANCAGEM,
    }
