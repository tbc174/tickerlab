"""Tabelas da conferência de 19/11/2026 (base/cadastros_conferidos_19_11.py, PR 2): SICAF e Banco de Preços em
Saúde. Só pessoa jurídica, sem coluna de nome, o CNAE com o zero da frente, cada ZIP anual do BPS como série
própria e sem olhar o futuro. Arquivos de mentira no formato conferido em 19/11/2026; nenhum documento real (o
CPF é o de teste, montado na hora)."""

import hashlib
import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from base import cadastros_conferidos_19_11 as conferidos
from base import cadastros_em_retrato as montagem
from base import cnpj as cnpjs
from base.arquivo import lote_conferidas_19_11 as arquivista
from base.parquet import LINHAGEM
from src.banco import coletas
from src.banco.coletas import com_registro
from tests.ajudantes_de_cpf import CPF_DE_TESTE, no_formato

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
DIA = date(2026, 11, 19)
DIA_SEGUINTE = date(2026, 12, 19)
PROIBIDAS = ("nome_d", "no_fornecedor", "no_fabricante", "razao", "cpf", "observacao")
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
FABRICANTE = _cnpj("55666777")
HOSPITAL = _cnpj("66777888")
DV_ERRADO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)


def _formatado(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def _sem_nome_e_sem_cpf(tabela: pd.DataFrame) -> None:
    assert not [c for c in tabela.columns if any(p in c.lower() for p in PROIBIDAS)]
    texto = set(tabela.astype(str).to_numpy().ravel())
    assert not {NOME_INVENTADO, CPF_DE_TESTE, CPF_MASCARADO} & texto


# --- SICAF -------------------------------------------------------------------------------------------------
def _fornecedor(cnpj: str, ativo: bool = True, cnae: int = 4711302) -> dict:
    return {
        "cnpj": cnpj,
        "ativo": ativo,
        "habilitadoLicitar": not ativo,
        "codigoCnae": cnae,
        "nomeCnae": "Comércio varejista",
        "naturezaJuridicaId": 2062,
        "naturezaJuridicaNome": "Sociedade Empresária Limitada",
        "porteEmpresaId": 1,
        "porteEmpresaNome": "MICROEMPRESA",
        "nomeMunicipio": "BRASÍLIA",
        "ufSigla": "DF",
    }


def _sicaf(*itens: dict) -> bytes:
    return "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in itens).encode()


def test_sicaf_so_pessoa_juridica_booleanos_e_o_cnae_com_sete_digitos():
    tabela, contagem = conferidos.ler_sicaf(
        _sicaf(
            _fornecedor(EMPRESA),
            _fornecedor(_formatado(OUTRA), ativo=False, cnae=111301),
            _fornecedor(CPF_DE_TESTE),
            _fornecedor(DV_ERRADO),
            _fornecedor(EMPRESA),
        )
    )
    assert (
        contagem["pessoa_fisica"],
        contagem["cnpj_invalido"],
        contagem["id_repetido"],
    ) == (1, 1, 1)
    assert list(tabela.columns) == list(conferidos.COLUNAS_DO_SICAF)
    por_raiz = tabela.set_index("cnpj_basico")
    assert por_raiz.loc[EMPRESA[:8], "cnpj"] == _formatado(EMPRESA)
    assert bool(por_raiz.loc[EMPRESA[:8], "ativo"]) is True
    assert bool(por_raiz.loc[OUTRA[:8], "ativo"]) is False
    assert bool(por_raiz.loc[OUTRA[:8], "habilitado_a_licitar"]) is True
    assert por_raiz.loc[OUTRA[:8], "cnae"] == "0111301"
    assert por_raiz.loc[EMPRESA[:8], "natureza_juridica"] == "2062"
    _sem_nome_e_sem_cpf(tabela)


def test_sicaf_campo_que_a_api_nao_mandou_vira_nulo():
    item = _fornecedor(EMPRESA)
    del item["nomeMunicipio"]
    item["habilitadoLicitar"] = None
    tabela, _ = conferidos.ler_sicaf(_sicaf(item))
    assert pd.isna(tabela.loc[0, "municipio"])
    assert pd.isna(tabela.loc[0, "habilitado_a_licitar"])


# --- BPS ---------------------------------------------------------------------------------------------------
def _bps(*linhas: tuple[str, str, str, str]) -> bytes:
    """Cada linha: (co_seq_bps, cnpj do fornecedor, cnpj do fabricante, preço unitário), no CSV do arquivista."""
    colunas = list(arquivista.COLUNAS_DO_BPS)
    registros = []
    for seq, fornecedor, fabricante, preco in linhas:
        registro = dict.fromkeys(colunas, "")
        registro.update(
            co_seq_bps=seq,
            ano_compra="2021",
            dt_compra="15/03/2021",
            dt_insercao="20/03/2021",
            cnpj_fornecedor=fornecedor,
            cnpj_fabricante=fabricante,
            cnpj_instituicao=HOSPITAL,
            no_instituicao="HOSPITAL PÚBLICO DE TESTE",
            co_catmat="267734",
            ds_item="DIPIRONA 500 MG",
            qt_medicamento="1000",
            vl_preco_unitario=preco,
            vl_preco_total="120.5",
        )
        registros.append(";".join(registro[c] for c in colunas))
    return "\n".join([";".join(colunas), *registros]).encode()


def test_bps_so_fornecedor_pessoa_juridica_e_o_fabricante_formatado():
    tabela, contagem = conferidos.ler_bps(
        _bps(
            ("1", EMPRESA, FABRICANTE, "0.1205"),
            ("2", CPF_DE_TESTE, FABRICANTE, "1"),
            ("3", DV_ERRADO, FABRICANTE, "1"),
            ("4", OUTRA, "", "2,5"),
            ("1", EMPRESA, FABRICANTE, "0.1205"),
        )
    )
    assert (
        contagem["pessoa_fisica"],
        contagem["cnpj_invalido"],
        contagem["id_repetido"],
    ) == (1, 1, 1)
    assert list(tabela.columns) == list(conferidos.COLUNAS_DO_BPS)
    por_id = tabela.set_index("id_na_fonte")
    assert por_id.loc["1", "cnpj_do_fabricante"] == _formatado(FABRICANTE)
    assert por_id.loc["1", "cnpj_basico_do_fabricante"] == FABRICANTE[:8]
    assert pd.isna(por_id.loc["4", "cnpj_do_fabricante"])
    assert por_id.loc["1", "cnpj_da_instituicao"] == _formatado(HOSPITAL)
    assert por_id.loc["1", "preco_unitario"] == pytest.approx(0.1205)
    assert por_id.loc["4", "preco_unitario"] == pytest.approx(2.5)
    assert por_id.loc["1", "data_da_compra"] == pd.Timestamp("2021-03-15")
    assert por_id.loc["1", "ano_da_compra"] == 2021
    _sem_nome_e_sem_cpf(tabela)


def test_bps_coluna_que_o_ministerio_tirou_e_erro():
    with pytest.raises(KeyError, match="vl_preco_total"):
        conferidos.ler_bps(f"co_seq_bps;cnpj_fornecedor\n1;{EMPRESA}\n".encode())


# --- montagem ----------------------------------------------------------------------------------------------
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


URL_DOS_ATIVOS = arquivista.endereco_do_sicaf("true")(1)
URL_DOS_INATIVOS = arquivista.endereco_do_sicaf("false")(1)
ZIP_DE_2021 = arquivista.zip_do_bps(2021)
ZIP_DE_2022 = arquivista.zip_do_bps(2022)


def _coletar_todos(banco, dia: date) -> None:
    _coletar(
        banco,
        "comprasgov-sicaf-ativos",
        URL_DOS_ATIVOS,
        _sicaf(_fornecedor(EMPRESA), _fornecedor(MEI)),
        dia,
    )
    _coletar(
        banco,
        "comprasgov-sicaf-inativos",
        URL_DOS_INATIVOS,
        _sicaf(_fornecedor(OUTRA, ativo=False)),
        dia,
    )
    _coletar(
        banco,
        conferidos.FONTE_DO_BPS,
        ZIP_DE_2021,
        _bps(("1", EMPRESA, FABRICANTE, "1"), ("2", OUTRA, MEI, "1")),
        dia,
    )


MONTADOS = {"ativos", "inativos", "compras"}


def test_montar_grava_as_duas_tabelas_marca_o_mei_e_vale_desde_o_dia_do_arquivo(
    banco, tmp_path
):
    _coletar_todos(banco, DIA)
    with banco.connect() as conexao:
        resumo = conferidos.montar(conexao, tmp_path, AGORA, pessoas={MEI[:8]})
    assert set(resumo) == MONTADOS
    for cadastro in conferidos.CADASTROS:
        tabela = pd.read_parquet(
            tmp_path / cadastro.tabela / f"{cadastro.nome}.parquet"
        )
        assert list(tabela.columns) == [
            *cadastro.colunas,
            *montagem.CARIMBOS_DA_LINHA,
            *LINHAGEM,
        ]
        _sem_nome_e_sem_cpf(tabela)
        assert set(tabela["disponivel_em"]) == {DIA}, cadastro.nome
    ativos = pd.read_parquet(tmp_path / conferidos.TABELA_DO_SICAF / "ativos.parquet")
    assert dict(
        zip(ativos["cnpj_basico"], ativos["trata_como_pessoa"], strict=True)
    ) == {
        EMPRESA[:8]: False,
        MEI[:8]: True,
    }
    compras = pd.read_parquet(tmp_path / conferidos.TABELA_DO_BPS / "compras.parquet")
    # o fabricante MEI também marca a linha: a raiz dele sairia pela coluna do fabricante
    assert dict(
        zip(compras["id_na_fonte"], compras["trata_como_pessoa"], strict=True)
    ) == {
        "1": False,
        "2": True,
    }


def test_segundo_montar_sem_arquivo_novo_e_ja_montado(banco, tmp_path):
    _coletar_todos(banco, DIA)
    with banco.connect() as conexao:
        conferidos.montar(conexao, tmp_path, AGORA, pessoas=set())
        resumo = conferidos.montar(conexao, tmp_path, AGORA, pessoas=set())
    assert resumo == dict.fromkeys(MONTADOS, montagem.JA_MONTADO)


def test_cada_zip_anual_do_bps_e_uma_serie_e_a_compra_de_um_ano_nao_sai_pelo_outro(
    banco, tmp_path
):
    _coletar(
        banco, conferidos.FONTE_DO_BPS, ZIP_DE_2021, _bps(("1", EMPRESA, "", "1")), DIA
    )
    _coletar(
        banco,
        conferidos.FONTE_DO_BPS,
        ZIP_DE_2022,
        _bps(("9", OUTRA, "", "1")),
        DIA_SEGUINTE,
    )
    # o ZIP de 2021 de novo, no mês seguinte, com a compra 1 corrigida
    _coletar(
        banco,
        conferidos.FONTE_DO_BPS,
        ZIP_DE_2021,
        _bps(("1", EMPRESA, "", "2")),
        DIA_SEGUINTE,
    )
    with banco.connect() as conexao:
        conferidos.montar(conexao, tmp_path, AGORA, pessoas=set())
    compras = pd.read_parquet(tmp_path / conferidos.TABELA_DO_BPS / "compras.parquet")
    assert compras[
        "consta"
    ].all()  # nenhuma compra "saiu" por estar no ZIP de outro ano
    versoes = compras.groupby("id_na_fonte")["preco_unitario"].apply(list).to_dict()
    assert versoes == {"1": [1.0, 2.0], "9": [1.0]}
    primeira_vez = compras.groupby("id_na_fonte")["disponivel_em"].min().to_dict()
    assert primeira_vez == {"1": DIA, "9": DIA_SEGUINTE}


def test_os_cadastros_cobrem_as_tres_fontes_e_as_duas_tabelas():
    assert {c.fonte for c in conferidos.CADASTROS} == {
        f.id for f in arquivista.fontes()
    }
    assert {c.tabela for c in conferidos.CADASTROS} == {
        conferidos.TABELA_DO_SICAF,
        conferidos.TABELA_DO_BPS,
    }
