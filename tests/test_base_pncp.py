"""Contratos do PNCP: lotes incrementais, somente PJ e datas sem antecipar retificações."""

import gzip
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa

from base import pncp, porta
from base.dicionario import TABELAS
from src.banco import coletas
from tests.ajudantes_de_cpf import CPF_DE_TESTE, formatado

ARQUIVO = Path(__file__).parent / "arquivos" / "pncp" / "contratos.jsonl"
COLETA = datetime(2026, 11, 26, 12, tzinfo=UTC)
EMPRESA = "11222333000181"


def _linha(**mudancas):
    return {**json.loads(ARQUIVO.read_text(encoding="utf-8")), **mudancas}


def _lote(*linhas):
    return "\n".join(json.dumps(linha) for linha in linhas).encode()


def test_le_jsonl_do_acervo_so_com_campos_estruturados():
    tabela, resumo = pncp.ler(ARQUIVO.read_bytes(), COLETA)
    assert tabela["cnpj"].tolist() == [EMPRESA]
    assert tabela["valor_global"].tolist() == [1234.5]
    assert tabela["disponivel_em"].tolist() == [date(2026, 11, 25)]
    assert resumo["linhas"] == 1
    assert not {"objetoContrato", "nomeRazaoSocialFornecedor", "usuarioNome"} & set(
        tabela
    )
    assert "TEXTO INVENTADO" not in tabela.to_json()


@pytest.mark.parametrize(
    "documento",
    [
        CPF_DE_TESTE,
        formatado(CPF_DE_TESTE),
        "***.888.888-**",
        "11222333000182",
        "ABC11222333000181",
        "",
        None,
        11222333000181,
    ],
)
def test_documento_invalido_ou_cpf_nao_entra(documento):
    tabela, resumo = pncp.ler(_lote(_linha(niFornecedor=documento)), COLETA)
    assert tabela.empty
    assert resumo["cnpj_invalido"] == 1


@pytest.mark.parametrize("tipo", ["PF", "PE", "", None])
def test_tipo_tem_de_ser_pj_mesmo_com_documento_de_14_digitos(tipo):
    tabela, resumo = pncp.ler(_lote(_linha(tipoPessoa=tipo)), COLETA)
    assert tabela.empty
    assert resumo["tipo_nao_pj"] == 1


def test_cnpj_formatado_e_aceito_e_subcontratado_pessoa_nao_sai():
    tabela, _ = pncp.ler(
        _lote(
            _linha(
                niFornecedor="11.222.333/0001-81",
                tipoPessoaSubContratada="PF",
                niFornecedorSubContratado=CPF_DE_TESTE,
                nomeFornecedorSubContratado="TEXTO INVENTADO",
                objetoContrato=f"TEXTO INVENTADO {CPF_DE_TESTE}",
            )
        ),
        COLETA,
    )
    assert tabela["cnpj"].tolist() == [EMPRESA]
    assert CPF_DE_TESTE not in tabela.to_json()
    assert "TEXTO INVENTADO" not in tabela.to_json()


@pytest.mark.parametrize(
    "mudancas,atualizados,esperada",
    [
        (
            {"dataAtualizacao": "2026-11-26T10:00:00", "numeroRetificacao": 1},
            False,
            date(2026, 11, 26),
        ),
        ({"numeroRetificacao": 1}, False, COLETA.date()),
        ({"numeroRetificacao": None}, False, COLETA.date()),
        ({}, True, COLETA.date()),
        ({"dataPublicacaoPncp": None}, False, COLETA.date()),
        ({"dataPublicacaoPncp": "ilegivel"}, False, COLETA.date()),
        (
            {"dataPublicacaoPncp": "2026-11-27T10:00:00", "numeroRetificacao": 1},
            False,
            date(2026, 11, 27),
        ),
        ({"dataAtualizacaoGlobal": "2026-11-27T10:00:00"}, True, date(2026, 11, 27)),
    ],
)
def test_data_publica_e_da_versao_ou_da_coleta(mudancas, atualizados, esperada):
    tabela, _ = pncp.ler(_lote(_linha(**mudancas)), COLETA, atualizados=atualizados)
    assert tabela["disponivel_em"].tolist() == [esperada]


@pytest.mark.parametrize(
    "conteudo", [b'{"data": []}', b"[]", b"{", b'{"tipoPessoa": "PJ"}']
)
def test_layout_invalido_falha_sem_imprimir_conteudo(conteudo):
    with pytest.raises(ValueError, match="PNCP"):
        pncp.ler(conteudo, COLETA)


def _guardar(banco, fonte, linhas, quando):
    conteudo = _lote(*linhas)
    url = f"https://pncp.gov.br/teste/{fonte}/{quando.isoformat()}"
    coletas.com_registro(fonte, lambda _: conteudo)(url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(
                coletas.coletas.c.url == url,
                coletas.coletas.c.sha256 == hashlib.sha256(conteudo).hexdigest(),
            )
            .values(baixado_em=quando)
        )


def test_montagem_junta_as_duas_coletas_preserva_versoes_e_nao_exclui_ausentes(
    banco, tmp_path
):
    outro_contrato = _linha(numeroControlePNCP="11222333000181-2-000002/2026")
    _guardar(banco, "pncp-contratos", [_linha(), outro_contrato], COLETA)
    depois = datetime(2026, 11, 27, 12, tzinfo=UTC)
    _guardar(
        banco,
        "pncp-contratos-atualizados",
        [
            _linha(
                valorGlobal=2000,
                numeroRetificacao=1,
                dataAtualizacao="2026-11-27T10:00:00",
            )
        ],
        depois,
    )
    with banco.connect() as conexao:
        pncp.montar(conexao, tmp_path, depois, pessoas=set())
        resumo = pncp.montar(conexao, tmp_path, depois, pessoas=set())
    tabela = pd.read_parquet(tmp_path / "pncp_contratos" / "contratos.parquet")
    assert len(tabela) == 3
    assert tabela["valor_global"].tolist().count(2000) == 1
    assert not tabela["trata_como_pessoa"].any()
    assert resumo == {"contratos": {"ja_montado": 1}}
    with porta.Porta(tmp_path) as p:
        antes = p.ler("pncp_contratos", como_era_em="2026-11-26")
    assert len(antes) == 2
    assert set(antes["valor_global"]) == {1234.5}


def test_mei_fica_marcado_e_a_porta_o_retira(banco, tmp_path):
    _guardar(banco, "pncp-contratos", [_linha()], COLETA)
    with banco.connect() as conexao:
        pncp.montar(conexao, tmp_path, COLETA, pessoas={EMPRESA[:8]})
    with porta.Porta(tmp_path) as p:
        assert p.ler("pncp_contratos").empty


def test_le_o_gzip_como_o_arquivista_guarda(tmp_path):
    arquivo = tmp_path / "contratos.jsonl.gz"
    arquivo.write_bytes(gzip.compress(ARQUIVO.read_bytes(), mtime=0))
    from base.retratos import original

    tabela, _ = pncp.ler(original(arquivo), COLETA)
    assert tabela["cnpj"].tolist() == [EMPRESA]


def test_contrato_pncp_e_de_empresa_e_tem_data_publica():
    assert "pncp_contratos" in TABELAS
    contrato = TABELAS["pncp_contratos"]
    assert contrato.pessoa is False
    assert contrato.linhas_de_pessoa == "trata_como_pessoa"
    assert contrato.datas["publico_em"] == "disponivel_em"


def test_mesma_licenca_do_arquivista_e_carga_existente():
    from base.arquivo.destinos import DESTINOS
    from base.contrato import contrato_da_tabela
    from scripts.carga_fundos_e_reguladores import MODULOS

    contrato = contrato_da_tabela("pncp_contratos", TABELAS["pncp_contratos"])
    assert contrato["licenca"] == coletas.licenca_da_fonte("pncp")
    assert contrato["revenda"] == coletas.revenda_da_fonte("pncp")
    assert pncp in MODULOS
    assert all(DESTINOS[fonte].tabelas == ("pncp_contratos",) for fonte in pncp.FONTES)


def test_sem_receita_todas_as_linhas_ficam_marcadas(banco, tmp_path):
    _guardar(banco, "pncp-contratos", [_linha()], COLETA)
    with banco.connect() as conexao:
        pncp.montar(conexao, tmp_path, COLETA)
    with porta.Porta(tmp_path) as p:
        assert p.ler("pncp_contratos").empty


def test_repeticao_entre_lotes_nao_duplica_e_mudanca_sem_data_nao_reescreve_passado(
    banco, tmp_path
):
    _guardar(banco, "pncp-contratos", [_linha(), _linha()], COLETA)
    repeticao = datetime(2026, 11, 27, 12, tzinfo=UTC)
    _guardar(banco, "pncp-contratos-atualizados", [_linha()], repeticao)
    mudanca = datetime(2026, 11, 28, 12, tzinfo=UTC)
    with banco.connect() as conexao:
        pncp.montar(conexao, tmp_path, repeticao, pessoas=set())
    antes = pd.read_parquet(tmp_path / "pncp_contratos" / "contratos.parquet")
    assert len(antes) == 1
    _guardar(banco, "pncp-contratos", [_linha(valorGlobal=2000)], mudanca)
    with banco.connect() as conexao:
        pncp.montar(conexao, tmp_path, mudanca, pessoas=set())
    depois = pd.read_parquet(tmp_path / "pncp_contratos" / "contratos.parquet")
    assert len(depois) == 2
    assert depois["disponivel_em"].tolist() == [date(2026, 11, 25), mudanca.date()]
    pd.testing.assert_frame_equal(
        antes.drop(columns="montado_em"), depois.iloc[:1].drop(columns="montado_em")
    )


def test_so_cpf_gera_tabela_vazia_com_contrato_completo(banco, tmp_path):
    _guardar(banco, "pncp-contratos", [_linha(niFornecedor=CPF_DE_TESTE)], COLETA)
    with banco.connect() as conexao:
        pncp.montar(conexao, tmp_path, COLETA, pessoas=set())
    tabela = pd.read_parquet(tmp_path / "pncp_contratos" / "contratos.parquet")
    assert tabela.empty
    assert set(tabela.columns) == set(TABELAS["pncp_contratos"].colunas)


def test_duas_mudancas_no_mesmo_dia_preservam_momentos_distintos(banco, tmp_path):
    _guardar(banco, "pncp-contratos", [_linha()], COLETA)
    depois = datetime(2026, 11, 26, 18, tzinfo=UTC)
    _guardar(banco, "pncp-contratos-atualizados", [_linha(valorGlobal=2000)], depois)
    with banco.connect() as conexao:
        pncp.montar(conexao, tmp_path, depois, pessoas=set())
    tabela = pd.read_parquet(tmp_path / "pncp_contratos" / "contratos.parquet")
    assert len(tabela) == 2
    assert not tabela.duplicated(list(TABELAS["pncp_contratos"].chaves)).any()
