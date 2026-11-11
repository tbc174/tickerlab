"""O exportador das novidades da pesquisa (linha 830): só prova gravada, só órgão da tabela, nunca pessoa.

Memória do bot de mentira (SQLite em `tmp_path`); nomes e CPF inventados.
"""

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pesquisa import novidades
from pesquisa.memoria import Memoria, Visto
from scripts import exportar_novidades

AGORA = datetime(2026, 11, 11, 12, tzinfo=UTC)
HASH = "a" * 64
URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/exemplo.csv"
TRECHO = "Parque Exemplo Eólico: 120 MW, vigência 2035, CNPJ 11.222.333/0001-81"
CPF_INVENTADO = "529.982.247-25"
CNPJ = "11.222.333/0001-81"


def SEMPRE(
    cnpj: str,
) -> bool:  # a lista sem pessoa do acervo, de mentira: todo CNPJ está nela
    return True


@pytest.fixture
def base_de_mentira(monkeypatch):
    """O script abre a base do acervo; aqui a porta é de mentira e todo CNPJ está na lista sem pessoa."""

    @contextmanager
    def abrir(pasta=None):
        yield object()

    monkeypatch.setattr(exportar_novidades.porta, "abrir", abrir)
    monkeypatch.setattr(exportar_novidades, "e_empresa", lambda base, cnpj: True)


def _memoria(tmp_path: Path) -> Memoria:
    return Memoria(tmp_path / "memoria.sqlite")


def _visto(memoria: Memoria, url: str = URL, sha: str = HASH) -> None:
    memoria.lembrar(Visto(url, None, sha, "csv", 10, None, "2026-11-10T10:00:00", "r1"))


def _fato(
    memoria: Memoria,
    *,
    trecho: str = TRECHO,
    sha: str = HASH,
    veredito: str = "confirmado",
    afirmacao: str = "Parque Exemplo: 120 MW",
) -> None:
    memoria.registrar_fato(
        "r1",
        "hipótese",
        {
            "afirmacao": afirmacao,
            "valor": "120",
            "trecho": trecho,
            "sha256": sha,
            "posicao": "linha 3",
        },
        veredito,
        [],
    )


def test_item_provado_sai_com_orgao_data_trecho_e_hash(tmp_path):
    memoria = _memoria(tmp_path)
    _visto(memoria)
    _fato(memoria)
    saida = novidades.exportar(memoria, e_empresa=SEMPRE, agora=datetime.now(UTC))
    assert len(saida.itens) == 1
    item = saida.itens[0]
    assert item["orgao"] == "CVM"
    assert item["fonte"] == "cvm"
    assert item["fonte_url"] == URL
    assert item["trecho"] == TRECHO
    assert item["sha256"] == HASH
    assert item["data"] == datetime.now(UTC).date().isoformat()


def test_nao_confirmado_e_sem_endereco_ficam_de_fora_com_motivo(tmp_path):
    memoria = _memoria(tmp_path)
    _visto(memoria)
    _fato(memoria, veredito="pendente")
    _fato(memoria, sha="b" * 64)  # sem `visto`: não há endereço de origem
    saida = novidades.exportar(memoria, e_empresa=SEMPRE, agora=datetime.now(UTC))
    assert saida.itens == []
    assert saida.descartados == {
        novidades.MOTIVO_NAO_CONFIRMADO: 1,
        novidades.MOTIVO_SEM_PROVA: 1,
    }


def test_dominio_fora_da_tabela_nao_sai(tmp_path):
    memoria = _memoria(tmp_path)
    _visto(memoria, url="https://blog.exemplo.com.br/x")
    _fato(memoria)
    saida = novidades.exportar(memoria, e_empresa=SEMPRE, agora=datetime.now(UTC))
    assert saida.itens == []
    assert saida.descartados == {novidades.MOTIVO_ORGAO: 1}


def test_fora_da_janela_nao_sai(tmp_path):
    memoria = _memoria(tmp_path)
    _visto(memoria)
    _fato(memoria)
    saida = novidades.exportar(
        memoria, e_empresa=SEMPRE, dias=7, agora=datetime(2027, 1, 1, tzinfo=UTC)
    )
    assert saida.itens == []
    assert saida.descartados == {novidades.MOTIVO_FORA_DA_JANELA: 1}


@pytest.mark.parametrize(
    "trecho",
    [
        f"Sócio com CPF {CPF_INVENTADO} entrou na empresa em 2025",
        "Sócio 52998224725 entrou na empresa em 2025",
        "Sócio 529 982 247 25 entrou na empresa em 2025",
        "Sócio 529.982.24725 entrou na empresa em 2025",
        "inscrito sob o nº 52998224725.",
        "ID-52998224725 entrou",
        "CPF 529.982.247–25 entrou",
        "Sócio 529 982 247 25 entrou",
        "Sócio 529.982.247/25 entrou",
        "Sócio 529 . 982 . 247 - 25 entrou",
        "Sócio ５２９．９８２．２４７－２５ entrou",
        "JOSE DA SILVA | ***.982.247-** | R$ 10.000",
    ],
)
def test_cpf_no_trecho_derruba_o_exportador(tmp_path, trecho):
    memoria = _memoria(tmp_path)
    _visto(memoria)
    _fato(memoria, trecho=trecho)
    with pytest.raises(novidades.CpfNoTrechoError):
        novidades.exportar(memoria, e_empresa=SEMPRE, agora=datetime.now(UTC))


def test_numero_de_cnpj_nao_e_confundido_com_cpf():
    assert not novidades.achar_cpf("CNPJ 11.222.333/0001-81 e 11222333000181")


def test_nome_de_pessoa_com_tratamento_e_descartado_e_contado(tmp_path):
    memoria = _memoria(tmp_path)
    _visto(memoria)
    _fato(memoria, trecho="O Sr. Fulano Inventado de Tal assinou o contrato em 2025")
    saida = novidades.exportar(memoria, e_empresa=SEMPRE, agora=datetime.now(UTC))
    assert saida.itens == []
    assert saida.descartados == {novidades.MOTIVO_PESSOA: 1}


def test_trecho_acima_do_maximo_nao_sai(tmp_path):
    memoria = _memoria(tmp_path)
    _visto(memoria)
    _fato(memoria, trecho=f"{CNPJ} " + "Parque Exemplo " * 40)
    saida = novidades.exportar(memoria, e_empresa=SEMPRE, agora=datetime.now(UTC))
    assert saida.descartados == {novidades.MOTIVO_TRECHO_LONGO: 1}


def test_mesmo_original_e_trecho_so_uma_vez(tmp_path):
    memoria = _memoria(tmp_path)
    _visto(memoria)
    _fato(memoria)
    _fato(memoria)
    saida = novidades.exportar(memoria, e_empresa=SEMPRE, agora=datetime.now(UTC))
    assert len(saida.itens) == 1
    assert saida.descartados == {novidades.MOTIVO_REPETIDO: 1}


def test_script_grava_o_arquivo_e_imprime_a_contagem(tmp_path, capsys, base_de_mentira):
    memoria = _memoria(tmp_path)
    _visto(memoria)
    _fato(memoria)
    _fato(memoria, veredito="pendente", sha="c" * 64)
    destino = tmp_path / "novidades.json"
    codigo = exportar_novidades.main(
        ["--pasta", str(tmp_path), "--saida", str(destino)]
    )
    assert codigo == 0
    # a data do fato é "agora", dentro da janela de 7 dias
    arquivo = json.loads(destino.read_text(encoding="utf-8"))
    assert arquivo["versao"] == 1
    assert len(arquivo["itens"]) == 1
    texto = capsys.readouterr().out
    assert "1 itens" in texto
    assert "descartados: 1 (veredito não confirmado)" in texto


def test_script_para_e_nao_grava_se_achar_cpf(tmp_path, capsys, base_de_mentira):
    memoria = _memoria(tmp_path)
    _visto(memoria)
    _fato(memoria, trecho=f"Sócio com CPF {CPF_INVENTADO} entrou em 2025")
    destino = tmp_path / "novidades.json"
    codigo = exportar_novidades.main(
        ["--pasta", str(tmp_path), "--saida", str(destino)]
    )
    assert codigo == 2
    assert not destino.exists()
    assert "PAROU" in capsys.readouterr().err


def test_pessoa_fisica_e_url_com_cpf_nao_saem(tmp_path):
    memoria = _memoria(tmp_path)
    _visto(memoria, url="https://dados.cvm.gov.br/x.csv?cpf=" + "52998224725")
    _fato(memoria)
    with pytest.raises(novidades.CpfNoTrechoError):
        novidades.exportar(memoria, e_empresa=SEMPRE, agora=datetime.now(UTC))


def test_endereco_com_barra_invertida_ou_sem_http_nao_e_orgao():
    from src.novidades_da_pesquisa import orgao_da_url

    assert orgao_da_url("https://dados.cvm.gov.br/x") is not None
    assert orgao_da_url(r"https://evil.com\@dados.cvm.gov.br/x") is None
    assert orgao_da_url("javascript://dados.cvm.gov.br/x") is None


def test_fonte_so_de_empresa_nome_sem_tratamento_em_fonte_que_saiu_da_lista_nao_sai(
    tmp_path,
):
    # TCU e Portal da Transparência têm linha de pessoa física: saíram da tabela de órgãos
    for dominio in ("dadosabertos.tcu.gov.br", "portaldatransparencia.gov.br"):
        memoria = _memoria(tmp_path / dominio.split(".")[0])
        _visto(memoria, url=f"https://{dominio}/x.csv")
        _fato(memoria, trecho=f"{CNPJ} | NOME FICTICIO DE TESTE | multa | 120.000,00")
        saida = novidades.exportar(memoria, e_empresa=SEMPRE, agora=datetime.now(UTC))
        assert saida.itens == []
        assert saida.descartados == {novidades.MOTIVO_ORGAO: 1}


def test_fonte_liberada_sem_cnpj_valido_nao_sai(tmp_path):
    memoria = _memoria(tmp_path)
    _visto(memoria)
    _fato(memoria, trecho="NOME FICTICIO DE TESTE | multa | 120.000,00")
    _visto(memoria, url=URL + "?2", sha="b" * 64)
    # CNPJ com dígito verificador errado
    _fato(memoria, sha="b" * 64, trecho="Empresa 11.222.333/0001-80 | multa | 120")
    saida = novidades.exportar(memoria, e_empresa=SEMPRE, agora=datetime.now(UTC))
    assert saida.itens == []
    assert saida.descartados == {novidades.MOTIVO_SEM_CNPJ: 2}


def test_cnpj_fora_da_lista_sem_pessoa_nao_sai(tmp_path):
    memoria = _memoria(tmp_path)
    _visto(memoria)
    _fato(memoria)
    saida = novidades.exportar(
        memoria, e_empresa=lambda cnpj: False, agora=datetime.now(UTC)
    )
    assert saida.itens == []
    assert saida.descartados == {novidades.MOTIVO_CNPJ_FORA_DA_LISTA: 1}


def test_so_sai_com_todos_os_cnpjs_na_lista(tmp_path):
    memoria = _memoria(tmp_path)
    _visto(memoria)
    _fato(memoria, trecho=f"{CNPJ} controlada por 33.000.167/0001-01 | 120 MW")
    na_lista = {"11222333000181"}
    saida = novidades.exportar(
        memoria, e_empresa=lambda c: c in na_lista, agora=datetime.now(UTC)
    )
    assert saida.itens == []
    assert saida.descartados == {novidades.MOTIVO_CNPJ_FORA_DA_LISTA: 1}


def test_script_sem_base_do_acervo_para_e_nao_grava(tmp_path, capsys, monkeypatch):
    memoria = _memoria(tmp_path)
    _visto(memoria)
    _fato(memoria)

    def sem_acervo(pasta=None):
        raise ValueError("acervo desligado")

    monkeypatch.setattr(exportar_novidades.porta, "abrir", sem_acervo)
    destino = tmp_path / "novidades.json"
    codigo = exportar_novidades.main(
        ["--pasta", str(tmp_path), "--saida", str(destino)]
    )
    assert codigo == 3
    assert not destino.exists()
