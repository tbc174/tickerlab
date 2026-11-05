"""Montagem em Parquet dos cadastros em retrato (linha 679): operadoras da ANS, entidades da SUSEP,
Cadastro de Empregadores do MTE e termos de embargo do IBAMA. Só CNPJ de DV certo, `trata_como_pessoa`
para MEI, um endereço por cadastro e nada novo quando não há retrato novo. Arquivos de mentira, no
formato conferido em 04/11/2026."""

import hashlib
import json
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from base import ans_operadoras, ibama_embargos, mte_lista_suja, susep_cadastro
from base import cadastros_em_retrato as montagem
from base import cnpj as cnpjs
from base.ancoragem import parquets_sem_manifesto
from base.arquivo import fontes
from base.arquivo.destinos import DESTINOS, TABELA
from base.dicionario import TABELAS
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
PRIMEIRO_DIA = date(2026, 11, 4)
SEGUNDO_DIA = date(2026, 12, 1)
URL_ATIVAS = fontes.CADASTRO_DA_ANS.format(
    situacao="ativas", arquivo=fontes.ARQUIVOS_DO_CADASTRO_DA_ANS["ativas"]
)
URL_CANCELADAS = fontes.CADASTRO_DA_ANS.format(
    situacao="canceladas", arquivo=fontes.ARQUIVOS_DO_CADASTRO_DA_ANS["canceladas"]
)
URL_DO_EMBARGO = "https://dadosabertos.ibama.gov.br/x/termo_embargo/termo_embargo.csv"
URL_DE_OUTRO_EMBARGO = "https://dadosabertos.ibama.gov.br/x/termo_embargo/anexo.csv"


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
OUTRA = _cnpj("33000167")
MEI = _cnpj("44555666")
CPF = "366.176.019-04"


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


def _ans(*linhas: tuple[str, str, str]) -> bytes:
    cabecalho = "REGISTRO_OPERADORA;CNPJ;RAZAO_SOCIAL;NOME_FANTASIA;MODALIDADE;UF;DATA_REGISTRO_ANS"
    return "\n".join(
        [
            cabecalho,
            *(f"{r};{c};{n};;Cooperativa Médica;SP;1999-05-20" for r, c, n in linhas),
        ]
    ).encode("utf-8")


def _montar(modulo, banco, tmp_path, pessoas=frozenset()) -> dict:
    with banco.connect() as conexao:
        return modulo.montar(conexao, tmp_path / "base", AGORA, pessoas=set(pessoas))


def test_cada_leitor_tem_tabela_no_dicionario_e_destino_de_tabela():
    for modulo in (ans_operadoras, susep_cadastro, mte_lista_suja, ibama_embargos):
        assert modulo.TABELA in TABELAS
        assert DESTINOS[modulo.FONTE.replace("_", "-")].tipo == TABELA
        assert DESTINOS[modulo.FONTE].tabelas == (modulo.TABELA,)
        colunas = set(TABELAS[modulo.TABELA].colunas)
        for cadastro in modulo.CADASTROS:
            assert set(cadastro.colunas) <= colunas, modulo.TABELA


def test_ans_grava_ativas_e_canceladas_e_marca_o_mei_como_pessoa(banco, tmp_path):
    _coletar(
        banco,
        "ans-operadoras",
        URL_ATIVAS,
        _ans(("1", EMPRESA, "OPERADORA A"), ("2", MEI, "OPERADORA MEI")),
        PRIMEIRO_DIA,
    )
    _coletar(
        banco,
        "ans-operadoras",
        URL_CANCELADAS,
        _ans(("3", OUTRA, "ANTIGA")),
        PRIMEIRO_DIA,
    )
    resumo = _montar(ans_operadoras, banco, tmp_path, pessoas={MEI[:8]})
    assert set(resumo) == {"ativas", "canceladas"}
    ativas = pd.read_parquet(tmp_path / "base/ans_operadoras/ativas.parquet")
    assert dict(
        zip(ativas["id_na_fonte"], ativas["trata_como_pessoa"], strict=True)
    ) == {
        "1": False,
        "2": True,
    }
    canceladas = pd.read_parquet(tmp_path / "base/ans_operadoras/canceladas.parquet")
    assert list(canceladas["situacao"]) == ["canceladas"]
    assert parquets_sem_manifesto(tmp_path / "base") == []
    for manifesto in (tmp_path / "base").rglob("*.json"):
        assert json.loads(manifesto.read_text(encoding="utf-8"))[
            "conferencia_do_contrato"
        ]["aprovada"]


def test_retrato_ja_montado_e_pulado_e_o_novo_so_acrescenta(banco, tmp_path):
    _coletar(
        banco, "ans-operadoras", URL_ATIVAS, _ans(("1", EMPRESA, "A")), PRIMEIRO_DIA
    )
    _montar(ans_operadoras, banco, tmp_path)
    assert _montar(ans_operadoras, banco, tmp_path)["ativas"] == montagem.JA_MONTADO
    _coletar(
        banco,
        "ans-operadoras",
        URL_ATIVAS,
        _ans(("1", EMPRESA, "A"))
        + b"\n2;"
        + OUTRA.encode()
        + b";B;;Cooperativa;SP;2000-01-01",
        SEGUNDO_DIA,
    )
    resumo = _montar(ans_operadoras, banco, tmp_path)["ativas"]
    assert resumo["retratos"] == 2
    tabela = pd.read_parquet(tmp_path / "base/ans_operadoras/ativas.parquet")
    novo = tabela[tabela["id_na_fonte"] == "2"].iloc[0]
    assert novo["disponivel_em"] <= SEGUNDO_DIA  # sem olhar o futuro


def test_susep_entidade_estrangeira_fica_sem_cnpj_e_nunca_e_de_pessoa(banco, tmp_path):
    itens = [
        {
            "entcodigofip": "1",
            "mercodigo": 1,
            "entnome": "SEGURADORA",
            "entcgc": EMPRESA,
            "dataautorizacao": "2001-01-01",
        },
        {
            "entcodigofip": "2",
            "mercodigo": 5,
            "entnome": "RESSEGURADOR",
            "entcgc": "",
            "dataautorizacao": "2010-01-01",
        },
        {
            "entcodigofip": "3",
            "mercodigo": 1,
            "entnome": "PESSOA",
            "entcgc": CPF.replace(".", "").replace("-", ""),
            "dataautorizacao": "",
        },
    ]
    _coletar(
        banco,
        "susep-cadastro",
        fontes.CADASTRO_DA_SUSEP,
        json.dumps({"value": itens}).encode(),
        PRIMEIRO_DIA,
    )
    resumo = _montar(susep_cadastro, banco, tmp_path)["entidades"]
    assert resumo["pessoa_fisica"] == 1
    tabela = pd.read_parquet(tmp_path / "base/susep_cadastro/entidades.parquet")
    assert sorted(tabela["id_na_fonte"]) == ["1", "2"]
    estrangeira = tabela[tabela["id_na_fonte"] == "2"].iloc[0]
    assert pd.isna(estrangeira["cnpj"]) and not estrangeira["trata_como_pessoa"]
    assert "PESSOA" not in tabela.astype(str).to_csv()


def test_mte_usa_so_o_csv_do_endereco_mais_novo(banco, tmp_path):
    cab = "ID;Ano da ação fiscal;UF;Empregador;CNPJ/CPF;Estabelecimento;Inclusão no Cadastro de Empregadores"

    def lista(cnpj: str) -> bytes:
        return f"{cab}\r\n1;2024;MG;EMPREGADOR;{cnpjs.formatar(cnpj)};FAZENDA;01/02/2025".encode(
            "latin-1"
        )

    _coletar(
        banco,
        "mte-lista-suja",
        "https://x.gov.br/antigo.csv",
        lista(OUTRA),
        PRIMEIRO_DIA,
    )
    _coletar(
        banco,
        "mte-lista-suja",
        "https://x.gov.br/novo.csv",
        lista(EMPRESA),
        SEGUNDO_DIA,
    )
    resumo = _montar(mte_lista_suja, banco, tmp_path)["empregadores"]
    assert resumo["enderecos_ignorados"] == 1
    tabela = pd.read_parquet(tmp_path / "base/mte_lista_suja/empregadores.parquet")
    assert list(tabela["cnpj"]) == [cnpjs.formatar(EMPRESA)]


def test_ibama_le_so_o_arquivo_do_termo_de_embargo(banco, tmp_path):
    cab = "SEQ_TAD;NUM_TAD;NOME_PESSOA_EMBARGADA;CPF_CNPJ_EMBARGADO;QTD_AREA_EMBARGADA;DAT_EMBARGO;UF"
    linha = f"10;T-1;EMPRESA;{cnpjs.formatar(EMPRESA)};12,5;2020-03-01;PA"
    _coletar(
        banco,
        "ibama-embargos",
        URL_DO_EMBARGO,
        f"{cab}\n{linha}".encode("latin-1"),
        PRIMEIRO_DIA,
    )
    _coletar(banco, "ibama-embargos", URL_DE_OUTRO_EMBARGO, b"X;Y\n1;2", SEGUNDO_DIA)
    resumo = _montar(ibama_embargos, banco, tmp_path)["termos"]
    assert resumo["retratos"] == 1
    tabela = pd.read_parquet(tmp_path / "base/ibama_embargos/termos.parquet")
    assert tabela["area_embargada_ha"].iloc[0] == 12.5
