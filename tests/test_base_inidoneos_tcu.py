"""Inidôneos do TCU (linha 904, lote 2): só CNPJ de DV certo (CPF e a coluna `nome` nunca entram), raiz de MEI
e raiz desconhecida ficam marcadas como pessoa (a porta não as serve), chave sem repetição e `disponivel_em`
sem olhar o futuro.

Os arquivos daqui são de mentira, no formato conferido em 13/11/2026 nos guardados pelo arquivista; os CNPJs
são de ninguém e o CPF é inventado."""

import hashlib
import json
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import inidoneos_tcu
from base.arquivo.destinos import DESTINOS, TABELA
from base.dicionario import TABELAS
from base.porta import Porta
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
PRIMEIRO_DIA = date(2026, 11, 4)
URL = "https://contas.tcu.gov.br/ords/condenacao/consulta/inidoneos?offset=0"
NOME_DE_MENTIRA = "FULANO DE TAL ME"


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
MEI = _cnpj("44555666")
DESCONHECIDA = _cnpj("77888999")
INVALIDO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)
CPF = "88800000551"


def _linha(documento: str, processo: str = "001.000/2020-1", **mais: str) -> dict:
    return {
        "nome": NOME_DE_MENTIRA,
        "cpf_cnpj": documento,
        "processo": processo,
        "deliberacao": "AC-000100/2020-PL",
        "data_transito_julgado": "2025-02-01T03:00:00Z",
        "data_final": "2028-02-01T03:00:00Z",
        "data_acordao": "2023-10-25T17:30:00Z",
        "uf": "DF",
        "municipio": None,
        **mais,
    }


def _arquivo(*linhas: dict) -> bytes:
    return "\n".join(json.dumps(linha) for linha in linhas).encode()


def test_so_cnpj_entra_e_nem_o_cpf_nem_o_nome_vazam():
    tabela, contagem = inidoneos_tcu.ler_retrato(
        _arquivo(
            _linha(EMPRESA),
            _linha(CPF, "002.000/2020-2"),
            _linha(INVALIDO, "003.000/2020-3"),
            _linha(EMPRESA),  # a mesma empresa no mesmo processo
            _linha(EMPRESA, "004.000/2020-4"),  # outro processo: outra linha
        )
    )
    assert list(tabela["id_na_fonte"]) == [
        f"{EMPRESA}|001.000/2020-1",
        f"{EMPRESA}|004.000/2020-4",
    ]
    assert contagem == {
        "linhas": 5,
        "pessoa_fisica": 1,
        "cnpj_invalido": 1,
        "id_repetido": 1,
    }
    tudo = tabela.astype(str).to_csv() + " ".join(tabela.columns)
    assert NOME_DE_MENTIRA not in tudo
    assert CPF not in tudo.replace(".", "").replace("-", "")
    assert "nome" not in tabela.columns
    assert {"uf", "municipio"}.isdisjoint(tabela.columns)  # a UF é sempre a do TCU


def test_datas_vem_em_dia_de_brasilia_e_vazio_fica_nulo():
    tabela, _ = inidoneos_tcu.ler_retrato(
        _arquivo(_linha(EMPRESA, data_acordao="", data_final="2028-02-01T03:00:00Z"))
    )
    linha = tabela.iloc[0]
    assert linha["data_transito_julgado"] == pd.Timestamp("2025-02-01")
    assert linha["data_final"] == pd.Timestamp("2028-02-01")
    assert pd.isna(linha["data_acordao"])


def test_disponivel_pelo_acordao_ou_transito_nunca_depois_do_retrato():
    dia = pd.Timestamp("2026-11-04")
    tabela = pd.DataFrame(
        {
            "data_acordao": pd.to_datetime(["2023-10-25", "2027-01-01", None, None]),
            "data_transito_julgado": pd.to_datetime(
                ["2025-02-01", "2023-01-01", None, "2024-05-05"]
            ),
        }
    )
    pronto = inidoneos_tcu.disponivel_no_primeiro(tabela, dia)
    assert list(pronto) == [
        pd.Timestamp("2025-02-01"),  # vale o trânsito, que veio depois do acórdão
        dia,  # data impossível (depois do retrato): vale o dia do retrato
        dia,  # sem nenhuma data: o dia do retrato
        pd.Timestamp("2024-05-05"),
    ]


def test_leitor_tem_tabela_no_dicionario_e_destino_de_tabela():
    assert inidoneos_tcu.TABELA in TABELAS
    assert DESTINOS[inidoneos_tcu.FONTE].tipo == TABELA
    assert DESTINOS[inidoneos_tcu.FONTE].tabelas == (inidoneos_tcu.TABELA,)
    colunas = set(TABELAS[inidoneos_tcu.TABELA].colunas)
    for cadastro in inidoneos_tcu.CADASTROS:
        assert set(cadastro.colunas) <= colunas
    assert TABELAS[inidoneos_tcu.TABELA].linhas_de_pessoa == "trata_como_pessoa"


def _coletar(banco, conteudo: bytes, dia: date) -> None:
    com_registro(inidoneos_tcu.FONTE, lambda *_: conteudo)(URL)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(
                coletas.coletas.c.url == URL,
                coletas.coletas.c.sha256 == hashlib.sha256(conteudo).hexdigest(),
            )
            .values(baixado_em=datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC))
        )


def test_so_empresa_de_verdade_chega_a_quem_consulta(banco, tmp_path):
    """CPF, raiz de MEI e raiz que a Receita não tem: nenhum passa pela porta (na dúvida, é pessoa)."""
    _coletar(
        banco,
        _arquivo(
            _linha(EMPRESA, "001.000/2020-1"),
            _linha(MEI, "002.000/2020-2"),
            _linha(DESCONHECIDA, "003.000/2020-3"),
            _linha(CPF, "004.000/2020-4"),
        ),
        PRIMEIRO_DIA,
    )
    pasta = tmp_path / "base"
    with banco.connect() as conexao:
        resumo = inidoneos_tcu.montar(
            conexao, pasta, AGORA, pessoas={MEI[:8], DESCONHECIDA[:8]}
        )
    assert resumo["inidoneos"]["pessoa_fisica"] == 1
    gravada = pd.read_parquet(pasta / "tcu_inidoneos/inidoneos.parquet")
    assert dict(
        zip(gravada["cnpj_basico"], gravada["trata_como_pessoa"], strict=True)
    ) == {EMPRESA[:8]: False, MEI[:8]: True, DESCONHECIDA[:8]: True}
    assert set(gravada["disponivel_em"]) == {date(2025, 2, 1)}
    with Porta(pasta) as porta:
        servidas = porta.con.execute("SELECT cnpj_basico FROM tcu_inidoneos").fetchall()
    assert servidas == [(EMPRESA[:8],)]
    assert NOME_DE_MENTIRA not in str(gravada.to_dict())
