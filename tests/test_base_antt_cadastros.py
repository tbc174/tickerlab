"""Cadastros da ANTT em retrato (linha 904, lote 3): operadores de transporte multimodal e seguro de
responsabilidade civil dos transportadores. Só pessoa jurídica, o seguro uma linha por apólice (a placa e o
nome do segurado nunca entram), a vigência com o mês na frente e sem olhar o futuro. Arquivos de mentira, no
formato conferido em 13/11/2026; nenhum documento real."""

import hashlib
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from base import antt_cadastros as antt
from base import cadastros_em_retrato as montagem
from base import cnpj as cnpjs
from base.parquet import LINHAGEM
from src.banco import coletas
from src.banco.coletas import com_registro
from tests.ajudantes_de_cpf import CPF_DE_TESTE

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
DIA = date(2026, 11, 14)
URL_DOS_MULTIMODAIS = (
    "https://dados.antt.gov.br/dataset/x/resource/y/download/operador.csv"
)
URL_DO_SEGURO = "https://dados.antt.gov.br/dataset/x/resource/z/download/seguro-responsabilidade-civil.csv"
PROIBIDAS = (
    "nome",
    "razao",
    "cpf",
    "endereco",
    "logradouro",
    "cep",
    "mail",
    "placa",
)
NOME_INVENTADO = "TRANSPORTES INVENTADOS DE TESTE LTDA"


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        if cnpjs.dv_confere(bruto := f"{raiz}{filial}{dv:02d}"):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
MEI = _cnpj("44555666")
SEGURADORA = _cnpj("77888999")
DV_ERRADO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)


def _formatado(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def _multimodais(*linhas: tuple[str, str, str, str, str, str]) -> bytes:
    """Cada linha: (cnpj, uf, país, cotm, vigência, adesão). A razão social e o logradouro vêm, para sair."""
    cabecalho = "cnpj;razao_social;logradouro;cep;email;uf;pais_de_origem;cotm;vigencia;adesao_ao_decreto_1563_95"
    corpo = [
        f"{cnpj};{NOME_INVENTADO};Rua Inventada;01311000;a@exemplo.invalid;{uf};{pais};{cotm};{vigencia};{adesao}"
        for cnpj, uf, pais, cotm, vigencia, adesao in linhas
    ]
    return "\n".join([cabecalho, *corpo]).encode("latin-1")


def _seguro(*linhas: tuple[str, str, str, str, str, str, str]) -> bytes:
    """Cada linha: (cnpj, apólice, início, fim, endosso, placa, assentos); a seguradora e o registro são fixos."""
    cabecalho = (
        "cnpj_seg;data_registro;cnpj;nome_segurado;numero_apolice;inicio_apolice;fim_apolice;"
        "numero_endosso;placa;nr_assentos"
    )
    corpo = [
        f"{_formatado(SEGURADORA)};05/11/2026 10:30:00;{cnpj};{NOME_INVENTADO};{apolice};{inicio};{fim};"
        f"{endosso};{placa};{assentos}"
        for cnpj, apolice, inicio, fim, endosso, placa, assentos in linhas
    ]
    return "\n".join([cabecalho, *corpo]).encode("utf-8")


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


def test_multimodais_a_vigencia_tem_o_mes_na_frente_e_a_razao_social_nao_entra():
    tabela, contagem = antt.ler_multimodais(
        _multimodais(
            (
                _formatado(EMPRESA),
                "SP",
                "Brasil",
                "0123",
                "03/25/2027 00:00:00.000000",
                "Sim",
            ),
            (EMPRESA, "SP", "Brasil", "0124", "12/01/2027 00:00:00.000000", "Não"),
            (DV_ERRADO, "SP", "Argentina", "0125", "01/02/2027 00:00:00.000000", "Sim"),
            (CPF_DE_TESTE, "SP", "Brasil", "0126", "01/02/2027 00:00:00.000000", "Sim"),
        )
    )
    assert contagem["linhas"] == 4
    assert contagem["pessoa_fisica"] == 1
    assert contagem["cnpj_invalido"] == 1
    assert list(tabela["cotm"]) == ["0123", "0124"]
    assert list(tabela["vigencia_ate"]) == [
        pd.Timestamp(2027, 3, 25),
        pd.Timestamp(2027, 12, 1),
    ]
    assert list(tabela["adesao_ao_decreto_1563_95"]) == [True, False]
    assert set(tabela["cnpj_basico"]) == {EMPRESA[:8]}
    assert not tabela.astype(str).isin([NOME_INVENTADO, "Rua Inventada"]).any().any()


def test_multimodais_a_linha_repetida_por_inteiro_e_contada_e_fica_uma():
    linha = (EMPRESA, "SP", "Brasil", "0123", "03/25/2027 00:00:00.000000", "Sim")
    tabela, contagem = antt.ler_multimodais(_multimodais(linha, linha, linha))
    assert len(tabela) == 1
    assert contagem["id_repetido"] == 2


def test_coluna_que_a_antt_tirou_e_erro_nunca_arquivo_vazio():
    sem_a_coluna = b"cnpj;uf\n" + EMPRESA.encode() + b";SP"
    with pytest.raises(KeyError, match="cotm"):
        antt.ler_multimodais(sem_a_coluna)


def test_seguro_uma_linha_por_apolice_sem_placa_e_sem_nome_do_segurado():
    tabela, contagem = antt.ler_seguro(
        _seguro(
            (EMPRESA, "AP1", "01/01/2026", "31/12/2026", "0", "AAA1A11", "40"),
            (EMPRESA, "AP1", "01/01/2026", "31/12/2026", "0", "BBB2B22", "44"),
            (
                EMPRESA,
                "AP1",
                "01/01/2026",
                "30/06/2027",
                "1",
                "AAA1A11",
                "40",
            ),  # endosso: mesma placa
            (EMPRESA, "AP2", "01/02/2026", "31/01/2027", "0", "CCC3C33", ""),
            (CPF_DE_TESTE, "AP3", "01/01/2026", "31/12/2026", "0", "DDD4D44", "4"),
            (DV_ERRADO, "AP4", "01/01/2026", "31/12/2026", "0", "EEE5E55", "4"),
        )
    )
    assert contagem["pessoa_fisica"] == 1
    assert contagem["cnpj_invalido"] == 1
    assert len(tabela) == 2
    primeira = tabela.set_index("numero_da_apolice").loc["AP1"]
    assert (primeira["veiculos"], primeira["assentos"], primeira["endossos"]) == (
        2,
        84,
        2,
    )
    assert primeira["inicio_da_apolice"] == pd.Timestamp(2026, 1, 1)
    assert primeira["fim_da_apolice"] == pd.Timestamp(2027, 6, 30)
    assert primeira["registrada_em"] == pd.Timestamp(2026, 11, 5)
    assert primeira["cnpj_basico_seguradora"] == SEGURADORA[:8]
    segunda = tabela.set_index("numero_da_apolice").loc["AP2"]
    assert pd.isna(segunda["assentos"])
    texto = tabela.astype(str).to_numpy().ravel()
    assert not {"AAA1A11", "BBB2B22", NOME_INVENTADO} & set(texto)
    assert not [c for c in tabela.columns if any(p in c.lower() for p in PROIBIDAS)]


def _coletar_os_dois(banco, dia: date) -> None:
    _coletar(
        banco,
        antt.FONTE_DOS_MULTIMODAIS,
        URL_DOS_MULTIMODAIS,
        _multimodais(
            (EMPRESA, "SP", "Brasil", "0123", "03/25/2027 00:00:00.000000", "Sim"),
            (MEI, "RJ", "Brasil", "0200", "03/25/2027 00:00:00.000000", "Sim"),
        ),
        dia,
    )
    _coletar(
        banco,
        antt.FONTE_DO_SEGURO,
        URL_DO_SEGURO,
        _seguro(
            (EMPRESA, "AP1", "01/01/2026", "31/12/2026", "0", "AAA1A11", "40"),
            (MEI, "AP9", "01/01/2026", "31/12/2026", "0", "ZZZ9Z99", "4"),
        ),
        dia,
    )


def test_montar_grava_as_duas_tabelas_marca_o_mei_e_vale_desde_o_dia_do_arquivo(
    banco, tmp_path
):
    _coletar_os_dois(banco, DIA)
    with banco.connect() as conexao:
        resumo = antt.montar(conexao, tmp_path, AGORA, pessoas={MEI[:8]})
    assert set(resumo) == {"multimodais", "seguros"}
    for cadastro in antt.CADASTROS:
        tabela = pd.read_parquet(
            tmp_path / cadastro.tabela / f"{cadastro.nome}.parquet"
        )
        assert list(tabela.columns) == [
            *cadastro.colunas,
            *montagem.CARIMBOS_DA_LINHA,
            *LINHAGEM,
        ]
        assert not [c for c in tabela.columns if any(p in c.lower() for p in PROIBIDAS)]
        assert dict(
            zip(tabela["cnpj_basico"], tabela["trata_como_pessoa"], strict=True)
        ) == {
            EMPRESA[:8]: False,
            MEI[:8]: True,
        }
        assert set(tabela["disponivel_em"]) == {
            DIA
        }  # o arquivo não diz quando foi publicado


def test_segundo_montar_sem_arquivo_novo_e_ja_montado(banco, tmp_path):
    _coletar_os_dois(banco, DIA)
    with banco.connect() as conexao:
        antt.montar(conexao, tmp_path, AGORA, pessoas=set())
        assert antt.montar(conexao, tmp_path, AGORA, pessoas=set()) == {
            "multimodais": montagem.JA_MONTADO,
            "seguros": montagem.JA_MONTADO,
        }
