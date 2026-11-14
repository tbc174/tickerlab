"""`scripts/carga_cadastros.py` (linha 915): monta as cinco tabelas de cadastro em retrato, só as pedidas, e
pessoa física fica de fora (CPF e nome nunca entram; sem a Receita guardada, toda linha fica marcada como
de pessoa, o lado conservador).

Os arquivos daqui são de mentira, no formato dos guardados pelo arquivista."""

import hashlib
from datetime import UTC, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from base import cnpj as cnpjs
from scripts import carga_cadastros
from src.banco import coletas
from src.banco.coletas import com_registro

URL_DO_MTE = "https://www.gov.br/trabalho-e-emprego/x/cadastro_de_empregadores.csv"
URL_DA_ANS = "https://dadosabertos.ans.gov.br/x/Relatorio_cadop.csv"
CPF = "888.000.005-51"
NOME_DA_PESSOA = "JOAQUIM PRODUTOR DE MENTIRA"


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
OUTRA = _cnpj("33000167")


def _coletar(banco, fonte: str, url: str, conteudo: bytes) -> None:
    com_registro(fonte, lambda _url: conteudo)(url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(
                coletas.coletas.c.url == url,
                coletas.coletas.c.sha256 == hashlib.sha256(conteudo).hexdigest(),
            )
            .values(baixado_em=datetime(2026, 11, 1, 3, tzinfo=UTC))
        )


def _mte() -> bytes:
    linhas = [
        "ID;Ano da ação fiscal;UF;Empregador;CNPJ/CPF;Estabelecimento;Inclusão no Cadastro de Empregadores",
        f"1;2021;PA;EMPRESA DE MENTIRA LTDA;{cnpjs.formatar(EMPRESA)};FAZENDA A;05/04/2024",
        f"2;2024;MS;{NOME_DA_PESSOA};{CPF};FAZENDA B;01/01/2025",
    ]
    return "\r\n".join(linhas).encode("latin-1")


def _ans() -> bytes:
    cabecalho = "REGISTRO_OPERADORA;CNPJ;RAZAO_SOCIAL;NOME_FANTASIA;MODALIDADE;UF;DATA_REGISTRO_ANS"
    return f"{cabecalho}\n123;{OUTRA};OPERADORA DE MENTIRA;;Cooperativa Médica;SP;1999-05-20".encode()


@pytest.fixture(autouse=True)
def _com_versao(monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")


def test_as_cinco_tabelas_estao_no_comando_do_menor_ao_maior():
    assert list(carga_cadastros.MODULOS) == [
        "ans_operadoras",
        "susep_cadastro",
        "mte_lista_suja",
        "gleif_ponte",
        "ibama_embargos",
    ]


def test_sem_nada_guardado_sai_com_1(banco, tmp_path):
    assert carga_cadastros.main(["--pasta", str(tmp_path / "b")]) == 1
    assert not (tmp_path / "b").exists()


def test_monta_o_que_ha_guardado_e_pessoa_fisica_fica_de_fora(banco, tmp_path):
    _coletar(banco, "mte-lista-suja", URL_DO_MTE, _mte())
    _coletar(banco, "ans-operadoras", URL_DA_ANS, _ans())
    assert carga_cadastros.main(["--pasta", str(tmp_path / "b")]) == 0
    mte = pd.read_parquet(tmp_path / "b" / "mte_lista_suja" / "empregadores.parquet")
    assert list(mte["cnpj"]) == [cnpjs.formatar(EMPRESA)]
    texto = mte.astype(str).to_csv()
    assert NOME_DA_PESSOA not in texto
    assert "88800000551" not in texto.replace(".", "").replace("-", "")
    assert mte["trata_como_pessoa"].all()  # sem a Receita guardada: o conservador
    ans = pd.concat(
        pd.read_parquet(p)
        for p in (tmp_path / "b" / "ans_operadoras").glob("*.parquet")
    )
    assert list(ans["cnpj"]) == [cnpjs.formatar(OUTRA)]
    assert ans["trata_como_pessoa"].all()


def test_tabela_pedida_monta_so_ela(banco, tmp_path):
    _coletar(banco, "mte-lista-suja", URL_DO_MTE, _mte())
    _coletar(banco, "ans-operadoras", URL_DA_ANS, _ans())
    pasta = tmp_path / "b"
    assert (
        carga_cadastros.main(["--pasta", str(pasta), "--tabela", "mte_lista_suja"]) == 0
    )
    assert [p.name for p in pasta.iterdir()] == ["mte_lista_suja"]
    # pedida sem arquivo guardado: nada montado, saída 1
    assert carga_cadastros.main(["--pasta", str(pasta), "--tabela", "gleif_ponte"]) == 1


def test_tabela_que_nao_existe_e_recusada(tmp_path):
    with pytest.raises(SystemExit):
        carga_cadastros.main(["--pasta", str(tmp_path), "--tabela", "outra_tabela"])
