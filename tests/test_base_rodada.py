"""Rodada diária das regras de qualidade (série 1 da base de ML, PR 3): que regras rodam com os
arquivos que existem, de quando vale cada achado e que uma regra quebrada não derruba as outras."""

import io
import zipfile

import pandas as pd
import pytest

from base import rodada
from base.cadastro import ler_cadastro
from base.contas_cvm import COLUNAS, LeituraDeContas, ler_indice
from base.rodada import (
    REGRAS_DE_UM_DOCUMENTO,
    Arquivo,
    esperadas,
    principais,
    regras_de_um_documento,
    regras_entre_documentos,
)

A = "11.111.111/0001-11"
B = "22.222.222/0001-22"
DFP_2024 = pd.Timestamp("2024-12-31")
DFP_2025 = pd.Timestamp("2025-12-31")
HOJE = pd.Timestamp("2026-10-13")
SEM_EVENTOS = pd.DataFrame(columns=["cnpj", "publicado_em"])
CABECALHO_DO_INDICE = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC"
)


def _conta(
    conta="1", valor=100.0, cnpj=A, referencia=DFP_2025, ordem="ultimo", **outros
):
    demonstracao = {"1": "BPA", "2": "BPP"}.get(conta.split(".")[0], "DRE")
    fim = referencia if ordem == "ultimo" else referencia - pd.DateOffset(years=1)
    linha = {
        "cnpj": cnpj,
        "empresa": "EMPRESA",
        "documento": "DFP",
        "referencia": referencia,
        "versao": 1,
        "demonstracao": demonstracao,
        "grupo": "con",
        "ordem": ordem,
        "inicio": fim - pd.DateOffset(years=1) + pd.Timedelta(days=1),
        "fim": fim,
        "conta": conta,
        "descricao": "Ativo Total" if conta == "1" else "Conta",
        "conta_fixa": True,
        "valor": valor,
    }
    return linha | outros


def _leitura(*linhas):
    contas = pd.DataFrame(list(linhas), columns=list(COLUNAS))
    return LeituraDeContas(
        contas,
        pd.DataFrame(columns=["cnpj", "referencia", "demonstracao", "grupo", "linhas"]),
    )


def _indice(*entregas):
    """(cnpj, referencia, versao, recebido_em) → o índice como `ler_indice` devolve."""
    return pd.DataFrame(
        [
            {
                "cnpj": cnpj,
                "empresa": "EMPRESA",
                "documento": "DFP",
                "referencia": referencia,
                "versao": versao,
                "recebido_em": pd.Timestamp(recebido),
            }
            for cnpj, referencia, versao, recebido in entregas
        ],
        columns=["cnpj", "empresa", "documento", "referencia", "versao", "recebido_em"],
    )


def _arquivo(ano, contas=(), indice=None):
    return Arquivo(
        documento="DFP",
        ano=ano,
        principais=principais(pd.DataFrame(list(contas), columns=list(COLUNAS))),
        indice=indice if indice is not None else _indice(),
    )


def _zip_do_indice(*linhas):
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            "dfp_cia_aberta_2025.csv",
            "\n".join([CABECALHO_DO_INDICE, *linhas]).encode("latin-1"),
        )
    return saida.getvalue()


# --- leitura do índice e do cadastro --------------------------------------------------------------
def test_ler_indice_traz_todas_as_versoes_com_a_data_de_entrega():
    zip_bytes = _zip_do_indice(
        f"{A};2025-12-31;1;EMPRESA A;001;DFP;1;2026-03-20;http://x",
        f"{A};2025-12-31;2;EMPRESA A;001;DFP;2;2026-05-02;http://x",
    )
    indice = ler_indice(zip_bytes, "DFP")
    assert indice["versao"].tolist() == [1, 2]
    assert indice["recebido_em"].tolist() == [
        pd.Timestamp("2026-03-20"),
        pd.Timestamp("2026-05-02"),
    ]
    assert set(indice["documento"]) == {"DFP"}


def test_ler_cadastro_com_as_datas_de_registro_e_cancelamento():
    texto = (
        "CNPJ_CIA;DENOM_SOCIAL;DT_REG;DT_CANCEL;SIT\n"
        f"{A};EMPRESA A;2001-05-10;;ATIVO\n"
        f"{B};EMPRESA B;1990-01-02;2025-11-30;CANCELADA\n"
    )
    cadastro = ler_cadastro(texto.encode("latin-1"))
    b = cadastro[cadastro["cnpj"] == B].iloc[0]
    assert b["cancelamento"] == pd.Timestamp("2025-11-30")
    assert pd.isna(cadastro[cadastro["cnpj"] == A].iloc[0]["cancelamento"])


def test_ler_cadastro_sem_as_datas_usa_a_situacao():
    texto = f"CNPJ_CIA;DENOM_SOCIAL;SIT\n{A};EMPRESA A;ATIVO\n{B};EMPRESA B;CANCELADA\n"
    cadastro = ler_cadastro(texto.encode("latin-1")).set_index("cnpj")
    assert pd.isna(cadastro.loc[A, "cancelamento"])
    assert cadastro.loc[B, "cancelamento"] == pd.Timestamp.min


# --- regras de um documento só --------------------------------------------------------------------
def test_um_documento_vale_desde_a_entrega_da_versao_mais_nova():
    leitura = _leitura(
        _conta("1", -10_000_000.0), _conta("2", -10_000_000.0)
    )  # ativo total negativo: R4
    indice = _indice((A, DFP_2025, 1, "2026-03-20"), (A, DFP_2025, 2, "2026-05-02"))
    resultado = regras_de_um_documento(leitura, "DFP", indice, HOJE)
    assert resultado.regras == REGRAS_DE_UM_DOCUMENTO
    assert resultado.referencias == (DFP_2025,)
    r4 = [a for a in resultado.achados if a.regra == "R4"]
    assert len(r4) == 1
    assert r4[0].valido_desde == pd.Timestamp("2026-05-02")


def test_regra_que_quebra_fica_fora_da_rodada_e_as_outras_rodam(monkeypatch):
    def quebrada(_contas):
        raise KeyError("coluna")

    monkeypatch.setattr(rodada, "r1_ativo_passivo", quebrada)
    leitura = _leitura(_conta("1", -10_000_000.0), _conta("2", -10_000_000.0))
    resultado = regras_de_um_documento(
        leitura, "DFP", _indice((A, DFP_2025, 1, "2026-03-20")), HOJE
    )
    assert "R1" not in resultado.regras  # não fecha os achados antigos da R1
    assert "R4" in resultado.regras
    assert [a.regra for a in resultado.achados] == ["R4"]
    assert resultado.falhas == ("R1",)


def test_repetidas_ganham_o_documento_mesmo_sem_contas():
    repetidas = pd.DataFrame(
        [
            {
                "cnpj": A,
                "referencia": DFP_2025,
                "demonstracao": "DFC_MI",
                "grupo": "con",
                "linhas": 2,
            }
        ]
    )
    leitura = LeituraDeContas(pd.DataFrame(columns=list(COLUNAS)), repetidas)
    resultado = regras_de_um_documento(
        leitura, "DFP", _indice((A, DFP_2025, 1, "2026-03-20")), HOJE
    )
    assert [(a.regra, a.documento) for a in resultado.achados] == [("R9", "DFP")]


def test_principais_guarda_so_as_contas_das_regras_entre_documentos():
    contas = pd.DataFrame(
        [
            _conta("1"),
            _conta("1.01"),
            _conta("3.01"),
            _conta("3.04.02"),
            _conta("2.03", descricao="Patrimônio Líquido Consolidado"),
        ],
        columns=list(COLUNAS),
    )
    assert sorted(principais(contas)["conta"]) == ["1", "2.03", "3.01"]


# --- regras que comparam documentos ---------------------------------------------------------------
def test_sem_anterior_nem_seguinte_so_roda_a_r7():
    atual = _arquivo(2025, [_conta("1")], _indice((A, DFP_2025, 1, "2026-03-20")))
    rodadas = regras_entre_documentos(atual, None, None, SEM_EVENTOS, None, HOJE)
    assert [r.regras for r in rodadas] == [("R7",)]


def test_r6_vale_desde_a_entrega_do_documento_seguinte():
    atual = _arquivo(
        2024,
        [_conta("1", 100_000_000.0, referencia=DFP_2024)],
        _indice((A, DFP_2024, 1, "2025-03-20")),
    )
    seguinte = _arquivo(
        2025,
        [_conta("1", 100_000_000.0), _conta("1", 50_000_000.0, ordem="penultimo")],
        _indice((A, DFP_2025, 1, "2026-03-25")),
    )
    rodadas = {
        r.regras: r
        for r in regras_entre_documentos(atual, None, seguinte, SEM_EVENTOS, None, HOJE)
    }
    r6 = rodadas[("R6",)]
    assert r6.referencias == (DFP_2024,)
    assert [(a.regra, a.valido_desde) for a in r6.achados] == [
        ("R6", pd.Timestamp("2026-03-25"))
    ]


def test_r8_espera_quem_entregou_no_ano_anterior_e_estava_registrada_no_prazo():
    anterior = _arquivo(
        2024,
        indice=_indice((A, DFP_2024, 1, "2025-03-20"), (B, DFP_2024, 1, "2025-03-21")),
    )
    atual = _arquivo(2025, indice=_indice())  # ninguém entregou a DFP de 2025
    cadastro = pd.DataFrame(
        [
            {
                "cnpj": A,
                "empresa": "A",
                "registro": pd.Timestamp("2001-01-01"),
                "cancelamento": pd.NaT,
            },
            {
                "cnpj": B,
                "empresa": "B",
                "registro": pd.Timestamp("1990-01-01"),
                "cancelamento": pd.Timestamp("2025-11-30"),
            },
        ]
    )
    rodadas = {
        r.regras: r
        for r in regras_entre_documentos(
            atual, anterior, None, SEM_EVENTOS, cadastro, HOJE
        )
    }
    r8 = rodadas[("R8",)]
    assert r8.referencias == (DFP_2025,)
    assert [a.cnpj for a in r8.achados] == [A]  # B saiu da bolsa antes do prazo


def test_r8_nao_roda_sem_o_cadastro():
    anterior = _arquivo(2024, indice=_indice((A, DFP_2024, 1, "2025-03-20")))
    atual = _arquivo(2025, indice=_indice())
    regras = [
        r.regras
        for r in regras_entre_documentos(atual, anterior, None, SEM_EVENTOS, None, HOJE)
    ]
    assert ("R8",) not in regras
    assert ("R3",) in regras


@pytest.mark.parametrize("documento", ["DFP", "ITR"])
def test_rodada_vazia_nao_quebra(documento):
    leitura = LeituraDeContas(
        pd.DataFrame(columns=list(COLUNAS)),
        pd.DataFrame(columns=["cnpj", "referencia", "demonstracao", "grupo", "linhas"]),
    )
    resultado = regras_de_um_documento(leitura, documento, _indice(), HOJE)
    assert resultado.achados == [] and resultado.falhas == ()


def test_ler_indice_traz_o_link_de_cada_versao():
    zip_bytes = _zip_do_indice(
        f"{A};2025-12-31;1;EMPRESA A;001;DFP;1;2026-03-20;http://enet/1",
        f"{A};2025-12-31;2;EMPRESA A;001;DFP;2;2026-05-02;http://enet/2",
    )
    assert ler_indice(zip_bytes, "DFP")["link"].tolist() == [
        "http://enet/1",
        "http://enet/2",
    ]


def test_esperadas_levam_a_uf_da_sede():
    anterior = pd.DataFrame([{"cnpj": A, "empresa": "A"}, {"cnpj": B, "empresa": "B"}])
    cadastro = pd.DataFrame(
        [
            {"cnpj": A, "registro": pd.NaT, "cancelamento": pd.NaT, "uf": "RS"},
            {"cnpj": B, "registro": pd.NaT, "cancelamento": pd.NaT, "uf": ""},
        ]
    )
    devem = esperadas(anterior, cadastro, pd.Timestamp("2024-05-15"))
    assert devem.set_index("cnpj")["uf"].to_dict() == {A: "RS", B: ""}
