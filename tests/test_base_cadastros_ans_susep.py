"""Cadastros da ANS (operadoras) e da SUSEP (entidades supervisionadas): só CNPJ de DV certo, chave sem
repetição, entidade estrangeira da SUSEP fica sem CNPJ e `disponivel_em` sem olhar o futuro.

Os arquivos daqui são de mentira, no formato conferido em 04/11/2026 nos guardados pelo arquivista."""

import json
from pathlib import Path

import pandas as pd

from base import ans_operadoras, susep_cadastro
from base import cnpj as cnpjs
from base import retratos as motor


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
OUTRA = _cnpj("33000167")
INVALIDO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)
CPF = "88800000046"
DIA = pd.Timestamp("2026-10-14")

CABECALHO_ATIVAS = (
    "REGISTRO_OPERADORA;CNPJ;RAZAO_SOCIAL;NOME_FANTASIA;MODALIDADE;UF;DATA_REGISTRO_ANS"
)
CABECALHO_CANCELADAS = (
    f"{CABECALHO_ATIVAS};DATA_DESCREDENCIAMENTO;MOTIVO_DO_DESCREDENCIAMENTO"
)


def _csv(cabecalho: str, *linhas: str) -> bytes:
    return "\r\n".join([cabecalho, *linhas]).encode("utf-8-sig")


def _ativa(registro: str, cnpj: str, registrada: str = "2015-05-19") -> str:
    return f"{registro};{cnpj};OPERADORA DE MENTIRA LTDA;;Medicina de Grupo;MG;{registrada}"


def test_ans_le_so_cnpj_de_dv_certo_e_conta_o_resto():
    conteudo = _csv(
        CABECALHO_ATIVAS,
        _ativa("1", EMPRESA),
        _ativa("2", INVALIDO),
        _ativa("3", CPF),
        _ativa("1", OUTRA),  # registro repetido: fica o primeiro
    )
    tabela, contagem = ans_operadoras.ler_retrato(conteudo, ans_operadoras.ATIVAS)
    assert list(tabela["id_na_fonte"]) == ["1"]
    assert tabela["cnpj"].iloc[0] == cnpjs.formatar(EMPRESA)
    assert tabela["cnpj_basico"].iloc[0] == EMPRESA[:8]
    assert tabela["situacao"].iloc[0] == "ativas"
    assert contagem == {"linhas": 4, "cnpj_invalido": 2, "id_repetido": 1}


def test_ans_ativas_nao_tem_descredenciamento_e_canceladas_tem():
    ativas, _ = ans_operadoras.ler_retrato(
        _csv(CABECALHO_ATIVAS, _ativa("1", EMPRESA)), ans_operadoras.ATIVAS
    )
    assert ativas["descredenciada_em"].isna().all()
    canceladas, _ = ans_operadoras.ler_retrato(
        _csv(
            CABECALHO_CANCELADAS,
            f"{_ativa('9', OUTRA)};2020-03-02;Cancelamento a pedido",
        ),
        ans_operadoras.CANCELADAS,
    )
    linha = canceladas.iloc[0]
    assert linha["descredenciada_em"] == pd.Timestamp("2020-03-02")
    assert linha["motivo_do_descredenciamento"] == "Cancelamento a pedido"
    assert linha["situacao"] == "canceladas"


def test_ans_disponivel_pelo_registro_ou_descredenciamento_nunca_depois_do_retrato():
    tabela = pd.DataFrame(
        {
            "registrada_em": pd.to_datetime(["2015-05-19", "2026-12-01", None]),
            "descredenciada_em": pd.to_datetime([None, None, None]),
        }
    )
    pronto = ans_operadoras.disponivel_no_primeiro(tabela, DIA)
    assert list(pronto) == [pd.Timestamp("2015-05-19"), DIA, DIA]
    cancelada = pd.DataFrame(
        {
            "registrada_em": pd.to_datetime(["2015-05-19"]),
            "descredenciada_em": pd.to_datetime(["2020-03-02"]),
        }
    )
    assert ans_operadoras.disponivel_no_primeiro(cancelada, DIA).iloc[0] == (
        pd.Timestamp("2020-03-02")
    )


def _susep(*itens: dict) -> bytes:
    return json.dumps({"value": list(itens)}).encode("utf-8")


def _entidade(fip: str, cgc: str | None, autorizada: str | None = "1989-07-14") -> dict:
    return {
        "mercodigo": 1,
        "entcodigofip": fip,
        "entnome": "ENTIDADE DE MENTIRA",
        "entcgc": cgc,
        "dataautorizacao": autorizada,
    }


def test_susep_estrangeira_fica_sem_cnpj_e_so_o_cpf_sai():
    conteudo = _susep(
        _entidade("1", EMPRESA),
        _entidade("2", None),  # resseguradora admitida: sem CNPJ
        _entidade("3", CPF),
        _entidade("4", INVALIDO),
        _entidade("1", OUTRA),  # FIP repetido
    )
    tabela, contagem = susep_cadastro.ler_retrato(conteudo)
    assert list(tabela["id_na_fonte"]) == ["1", "2", "4"]
    assert tabela["cnpj"].iloc[0] == cnpjs.formatar(EMPRESA)
    assert tabela["cnpj_basico"].iloc[0] == EMPRESA[:8]
    assert tabela["cnpj"].iloc[1:].isna().all()  # sem CNPJ e com CNPJ de lixo
    assert contagem == {
        "linhas": 5,
        "pessoa_fisica": 1,
        "cnpj_invalido": 1,
        "id_repetido": 1,
    }
    assert CPF not in tabela.astype(str).to_csv()


def test_susep_disponivel_pela_autorizacao_nunca_depois_do_retrato():
    tabela, _ = susep_cadastro.ler_retrato(
        _susep(
            _entidade("1", EMPRESA, "1989-07-14"),
            _entidade("2", OUTRA, "2027-01-01"),
            _entidade("3", None, None),
        )
    )
    pronto = susep_cadastro.disponivel_no_primeiro(tabela, DIA)
    assert list(pronto) == [pd.Timestamp("1989-07-14"), DIA, DIA]


def test_susep_cadastro_vazio_devolve_tabela_vazia_com_as_colunas():
    tabela, contagem = susep_cadastro.ler_retrato(_susep())
    assert list(tabela.columns) == susep_cadastro.COLUNAS
    assert contagem["linhas"] == 0


def test_retrato_que_muda_vira_linha_nova_no_dia_em_que_foi_visto():
    def retrato(dia: str, _nome: str) -> motor.Retrato:
        return motor.Retrato(
            url="u", sha256="s", caminho=Path("x"), baixado_em=pd.Timestamp(dia)
        )

    antes, _ = susep_cadastro.ler_retrato(_susep(_entidade("1", EMPRESA)))
    depois = antes.assign(nome="ENTIDADE COM OUTRO NOME")
    tabela, pulados = susep_cadastro.juntar_retratos(
        [(retrato("2026-10-14", "a"), antes), (retrato("2026-10-15", "b"), depois)]
    )
    assert pulados == 0
    assert list(tabela["disponivel_em"]) == [
        pd.Timestamp("1989-07-14"),
        pd.Timestamp("2026-10-15"),
    ]
    assert list(tabela["consta"]) == [True, True]
