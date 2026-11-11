"""Regressões da 2ª e 3ª rodadas de revisão das novidades (linha 830): pessoa não sai junto do CNPJ de empresa.

Só dado inventado: nomes, e-mails e telefones fictícios (domínio `.invalid`).
"""

from datetime import UTC, datetime

import pytest

from conector_remoto import pessoa as pessoa_do_conector
from pesquisa import novidades
from pesquisa.memoria import Memoria, Visto
from src import novidades_da_pesquisa as regras
from src import pessoa_no_texto

HASH = "a" * 64
DFP = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/exemplo.csv"
CNPJ = "11.222.333/0001-81"


def SEMPRE(cnpj: str) -> bool:
    return True


def _exportar(tmp_path, *, url=DFP, url_final=None, **fato):
    memoria = Memoria(tmp_path / "memoria.sqlite")
    memoria.lembrar(
        Visto(url, url_final, HASH, "csv", 10, None, "2026-11-10T10:00:00", "r1")
    )
    base = {
        "afirmacao": "Parque Exemplo: 120 MW",
        "valor": "120",
        "trecho": f"{CNPJ} | Parque Exemplo | 120 MW",
        "sha256": HASH,
        "posicao": "linha 3",
    }
    memoria.registrar_fato("r1", "hipótese", base | fato, "confirmado", [])
    return novidades.exportar(memoria, e_empresa=SEMPRE, agora=datetime.now(UTC))


# ---------------------------------------------------------------- conjunto por caminho


@pytest.mark.parametrize(
    "url",
    [
        "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv",
        "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv",
        "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/../../CAD/x.csv",
        "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/%2e%2e/x.csv",
        "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFPX/x.csv",
        "https://dadosabertos.aneel.gov.br/x.csv",
    ],
)
def test_conjunto_fora_da_lista_nao_sai(tmp_path, url):
    saida = _exportar(tmp_path, url=url)
    assert saida.itens == []
    assert saida.descartados == {novidades.MOTIVO_ORGAO: 1}


def test_url_malformada_nao_derruba_e_nao_e_fonte(tmp_path):
    assert (
        regras.orgao_da_url("https://[dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/x")
        is None
    )
    saida = _exportar(
        tmp_path, url="https://[dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/x"
    )
    assert saida.descartados == {novidades.MOTIVO_ORGAO: 1}


def test_url_final_fora_da_lista_derruba_o_item(tmp_path):
    saida = _exportar(
        tmp_path, url_final="https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/x.csv"
    )
    assert saida.itens == []
    assert saida.descartados == {novidades.MOTIVO_ORGAO: 1}


def test_url_e_url_final_na_lista_saem_com_o_endereco_final(tmp_path):
    final = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/final.csv"
    (item,) = _exportar(tmp_path, url_final=final).itens
    assert item["fonte_url"] == final


# ---------------------------------------------------------------- contato e pessoa em qualquer texto


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("trecho", f"{CNPJ} | fulano@exemplo.invalid | 120 MW"),
        ("trecho", f"{CNPJ} | (11) 91234-5678 | 120 MW"),
        ("trecho", f"{CNPJ} | +55 11 3456-7890 | 120 MW"),
        ("afirmacao", "contato fulano@exemplo.invalid"),
        ("afirmacao", "ligue 11 3456-7890"),
        ("posicao", "coluna fulano@exemplo.invalid"),
    ],
)
def test_email_ou_telefone_derruba_o_item(tmp_path, campo, valor):
    saida = _exportar(tmp_path, **{campo: valor})
    assert saida.itens == []
    assert saida.descartados == {novidades.MOTIVO_CONTATO: 1}


def test_marca_de_pessoa_na_posicao_derruba_o_item(tmp_path):
    saida = _exportar(tmp_path, posicao="coluna do Sr. Fulano")
    assert saida.descartados == {novidades.MOTIVO_PESSOA: 1}


def test_ano_em_intervalo_nao_e_telefone(tmp_path):
    (item,) = _exportar(tmp_path, trecho=f"{CNPJ} | vigência 2025-2035 | 120 MW").itens
    assert "2025-2035" in item["trecho"]


# ---------------------------------------------------------------- o CNPJ tem de estar no trecho que sai


def test_cnpj_so_na_afirmacao_nao_basta(tmp_path):
    saida = _exportar(
        tmp_path, afirmacao=f"CNPJ {CNPJ}", trecho="NOME FICTICIO | multa | 120 MW"
    )
    assert saida.itens == []
    assert saida.descartados == {novidades.MOTIVO_SEM_CNPJ: 1}


@pytest.mark.parametrize(
    "texto",
    [
        "11.222.333/0001-81",
        "11222333000181",
        "11 222 333 0001 81",
        "11.222.333 / 0001-81",
        "11.222.333/0001–81",
        "CNPJ11.222.333/0001-81",
        "11.222.333/0001-81x",
        "１１．２２２．３３３／０００１－８１",
    ],
)
def test_formas_do_cnpj_que_o_texto_pode_ter(texto):
    assert regras.cnpjs_validos(f"Empresa {texto} | 120") == {"11222333000181"}


def test_cnpj_alfanumerico_em_minuscula_conta():
    # 12.ABC.345/01DE-35 é o exemplo da Receita (DV 35)
    assert regras.cnpjs_validos("12.abc.345/01de-35") == {"12ABC34501DE35"}


@pytest.mark.parametrize(
    "texto", ["11.222.333/0001-80", "111.222.333/0001-81", "1122233300018"]
)
def test_cnpj_errado_ou_com_digito_colado_nao_conta(texto):
    assert regras.cnpjs_validos(texto) == set()


# ---------------------------------------------------------------- a mesma busca nas duas pontas


def test_a_busca_de_pessoa_do_conector_e_a_de_src_dizem_o_mesmo():
    amostras = [
        "529.982.247-25",
        "52998224725",
        "***.982.247-**",
        "fulano@exemplo.invalid",
        "11222333000181",
        "Parque Exemplo 120 MW",
    ]
    for texto in amostras:
        assert pessoa_do_conector.texto_de_pessoa(
            texto
        ) == pessoa_no_texto.texto_de_pessoa(texto)
