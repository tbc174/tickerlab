"""Fontes da conferência de 19/11/2026 no arquivista (base/arquivo/lote_conferidas_19_11.py): SICAF e Banco de
Preços em Saúde. Sem internet, com dublês; nenhum documento real (o CPF é o de teste, montado na hora)."""

import csv
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from base import licenca
from base.arquivo import lote_conferidas_19_11 as lote
from base.arquivo.coleta import Resposta, SemArquivo
from base.arquivo.fontes import FONTES, POR_ID
from base.arquivo.obter_pj import PaginacaoSemFim
from src.banco.coletas import Marca, licenca_da_fonte, marca_da_fonte
from tests.ajudantes_de_cpf import CPF_DE_TESTE, no_formato

AGORA = datetime(2026, 11, 19, 12, tzinfo=UTC)
CNPJ_INVENTADO = "12345678000195"
NOME_INVENTADO = "EMPRESA FICTICIA DE TESTE LTDA"
NOME_DE_PESSOA_INVENTADO = "FULANO DE TESTE"
CPF_MASCARADO = no_formato(CPF_DE_TESTE, "***.ddd.ddd-**")


class Servidor:
    """Responde `ler`, `cabecalhos` e `baixar` com bytes em memória; `recusa` dá o status HTTP de um endereço."""

    def __init__(
        self, arquivos: dict[str, bytes], recusa: dict[str, int] | None = None
    ):
        self.arquivos = arquivos
        self.recusa = recusa or {}
        self.lidos: list[str] = []

    def _confere(self, url: str) -> None:
        if url in self.recusa:
            resposta = requests.Response()
            resposta.status_code = self.recusa[url]
            raise requests.HTTPError(response=resposta)

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self._confere(url)
        self.lidos.append(url)
        return Resposta(url, self.arquivos[url], {})

    def cabecalhos(self, url):
        self._confere(url)
        return {"ETag": '"x"'}

    def baixar(self, url, destino: Path):
        self._confere(url)
        destino.write_bytes(self.arquivos[url])
        return {"ETag": '"x"'}


@pytest.fixture(autouse=True)
def _sem_pausa(monkeypatch):
    monkeypatch.setattr(lote, "PAUSA_ENTRE_PAGINAS_DO_SICAF_EM_SEGUNDOS", 0.0)


# --- SICAF ------------------------------------------------------------------------------------------------
def _juridica(**extra) -> dict:
    return {
        "ativo": True,
        "cnpj": CNPJ_INVENTADO,
        "cpf": None,
        "habilitadoLicitar": True,
        "codigoCnae": 4120400,
        "nomeCnae": "Construção de edifícios",
        "nomeMunicipio": "Cidade de Teste",
        "naturezaJuridicaId": 2062,
        "naturezaJuridicaNome": "Sociedade Empresária Limitada",
        "porteEmpresaId": 3,
        "porteEmpresaNome": "Demais",
        "nomeRazaoSocialFornecedor": NOME_INVENTADO,
        "ufSigla": "SP",
        **extra,
    }


def _fisica(cpf: str = CPF_DE_TESTE) -> dict:
    return {
        **_juridica(),
        "cnpj": None,
        "cpf": cpf,
        "nomeRazaoSocialFornecedor": NOME_DE_PESSOA_INVENTADO,
    }


def _pagina(itens: list[dict], total: int, restantes: int) -> bytes:
    corpo = {
        "resultado": itens,
        "totalRegistros": total,
        "totalPaginas": 0,
        "paginasRestantes": restantes,
    }
    return json.dumps(corpo).encode()


def _paginas_do_sicaf(ativo: str, *paginas: bytes) -> dict[str, bytes]:
    endereco = lote.endereco_do_sicaf(ativo)
    return {endereco(n): pagina for n, pagina in enumerate(paginas, start=1)}


def _coleta(id_: str, servidor: Servidor, destino: Path) -> list[dict]:
    (alvo,) = POR_ID[id_].descobrir(servidor, AGORA)
    assert alvo.obter is not None
    alvo.obter(servidor, destino)
    return [
        json.loads(linha) for linha in destino.read_text(encoding="utf-8").splitlines()
    ]


def test_o_sicaf_guarda_so_a_pessoa_juridica_sem_cpf_e_sem_razao_social(tmp_path):
    servidor = Servidor(
        _paginas_do_sicaf(
            "true",
            _pagina([_juridica(), _fisica(), _fisica(CPF_MASCARADO)], 4, 1),
            _pagina([_juridica(cnpj="")], 4, 0),
        )
    )
    destino = tmp_path / "sicaf.jsonl"
    (item,) = _coleta("comprasgov-sicaf-ativos", servidor, destino)
    assert item["cnpj"] == CNPJ_INVENTADO
    assert set(item) == set(lote.CAMPOS_DO_SICAF)
    gravado = destino.read_text(encoding="utf-8")
    assert CPF_DE_TESTE not in gravado
    assert CPF_MASCARADO not in gravado
    assert NOME_DE_PESSOA_INVENTADO not in gravado
    assert NOME_INVENTADO not in gravado


def test_o_sicaf_pede_500_por_pagina_com_o_filtro_de_cada_fonte():
    for id_, ativo in lote.SITUACOES_DO_SICAF.items():
        (alvo,) = POR_ID[id_].descobrir(Servidor({}), AGORA)
        consulta = parse_qs(urlsplit(alvo.url).query)
        assert consulta == {"pagina": ["1"], "tamanhoPagina": ["500"], "ativo": [ativo]}
        assert licenca.familia_do_endereco(alvo.url) == "comprasgov"
    assert set(lote.SITUACOES_DO_SICAF.values()) == {"true", "false"}


def test_o_sicaf_com_contagem_diferente_da_api_e_erro(tmp_path):
    servidor = Servidor(
        _paginas_do_sicaf("false", _pagina([_juridica(), _fisica()], 3, 0))
    )
    with pytest.raises(lote.ContagemDoSicafDivergente, match="2 itens lidos"):
        _coleta("comprasgov-sicaf-inativos", servidor, tmp_path / "sicaf.jsonl")


def test_a_contagem_nao_passa_de_uma_coleta_para_a_outra(tmp_path):
    servidor = Servidor(_paginas_do_sicaf("true", _pagina([_juridica()], 1, 0)))
    _coleta("comprasgov-sicaf-ativos", servidor, tmp_path / "a.jsonl")
    assert len(_coleta("comprasgov-sicaf-ativos", servidor, tmp_path / "b.jsonl")) == 1


def test_o_sicaf_so_com_pessoa_fisica_nao_grava_nada(tmp_path):
    servidor = Servidor(_paginas_do_sicaf("true", _pagina([_fisica()], 1, 0)))
    with pytest.raises(SemArquivo):
        _coleta("comprasgov-sicaf-ativos", servidor, tmp_path / "sicaf.jsonl")


def test_o_sicaf_sem_fim_e_erro_nunca_um_pedaco(tmp_path, monkeypatch):
    monkeypatch.setattr(lote, "MAXIMO_DE_PAGINAS_DO_SICAF", 2)
    servidor = Servidor(
        _paginas_do_sicaf(
            "true", _pagina([_juridica()], 9, 5), _pagina([_juridica()], 9, 4)
        )
    )
    with pytest.raises(PaginacaoSemFim):
        _coleta("comprasgov-sicaf-ativos", servidor, tmp_path / "sicaf.jsonl")


# --- Banco de Preços em Saúde -----------------------------------------------------------------------------
COLUNAS_DO_CSV_DO_BPS = (
    *lote.COLUNAS_DO_BPS,
    "no_fornecedor",
    "no_fabricante",
    "ds_observacao",
)


def _zip_do_bps(ano: int, linhas: list[dict[str, str]]) -> bytes:
    texto = io.StringIO()
    escritor = csv.DictWriter(texto, COLUNAS_DO_CSV_DO_BPS, delimiter=";", restval="")
    escritor.writeheader()
    escritor.writerows(linhas)
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr(f"{ano}.csv", ("﻿" + texto.getvalue()).encode("utf-8"))
    return saida.getvalue()


def _linhas_do_csv(destino: Path) -> list[dict[str, str]]:
    with destino.open(encoding="utf-8", newline="") as texto:
        return list(csv.DictReader(texto, delimiter=";"))


def test_o_bps_guarda_so_a_linha_do_fornecedor_com_cnpj_e_sem_os_nomes(tmp_path):
    zip_ = _zip_do_bps(
        2020,
        [
            {
                "co_seq_bps": "1",
                "cnpj_fornecedor": CNPJ_INVENTADO,
                "cnpj_fabricante": CPF_DE_TESTE,
                "cnpj_instituicao": CNPJ_INVENTADO,
                "no_fornecedor": NOME_INVENTADO,
                "no_fabricante": NOME_DE_PESSOA_INVENTADO,
                "ds_observacao": NOME_DE_PESSOA_INVENTADO,
                "vl_preco_total": "10,5",
            },
            {
                "co_seq_bps": "2",
                "cnpj_fornecedor": CPF_DE_TESTE,
                "no_fornecedor": NOME_DE_PESSOA_INVENTADO,
            },
        ],
    )
    destino = tmp_path / "bps.csv"
    lote.obter_do_bps(2020)(Servidor({lote.zip_do_bps(2020): zip_}), destino)
    (linha,) = _linhas_do_csv(destino)
    assert linha["co_seq_bps"] == "1"
    assert linha["cnpj_instituicao"] == CNPJ_INVENTADO
    assert (
        linha["cnpj_fabricante"] == ""
    )  # um CPF na coluna do fabricante sai em branco
    assert linha["vl_preco_total"] == "10,5"
    assert set(linha) == set(lote.COLUNAS_DO_BPS)
    gravado = destino.read_text(encoding="utf-8")
    assert CPF_DE_TESTE not in gravado
    assert NOME_DE_PESSOA_INVENTADO not in gravado
    assert NOME_INVENTADO not in gravado
    assert not list(tmp_path.glob("*.bruto")) and not list(tmp_path.glob("*.limpo"))


def test_o_bps_que_falha_na_limpeza_nao_deixa_arquivo(tmp_path, monkeypatch):
    zip_ = _zip_do_bps(
        2020, [{"cnpj_fornecedor": CNPJ_INVENTADO, "cnpj_fabricante": CPF_DE_TESTE}]
    )

    def quebra(*_):
        raise OSError("disco cheio")

    monkeypatch.setattr(lote, "_regrava_sem_cnpj_quebrado", quebra)
    destino = tmp_path / "bps.csv"
    with pytest.raises(OSError, match="disco cheio"):
        lote.obter_do_bps(2020)(Servidor({lote.zip_do_bps(2020): zip_}), destino)
    assert not list(tmp_path.iterdir())


def test_o_bps_tem_um_alvo_por_ano_e_o_ano_corrente_so_quando_saiu():
    atual = lote.zip_do_bps(AGORA.year)
    sem_o_atual = POR_ID["bps"].descobrir(Servidor({}, {atual: 403}), AGORA)
    assert [a.url for a in sem_o_atual] == [
        lote.zip_do_bps(ano) for ano in range(2020, AGORA.year)
    ]
    com_o_atual = POR_ID["bps"].descobrir(Servidor({}), AGORA)
    assert com_o_atual[-1].url == atual
    assert all(licenca.familia_do_endereco(a.url) == "bps" for a in com_o_atual)
    assert {a.extensao for a in com_o_atual} == {".csv"}


def test_o_bps_com_outro_erro_no_ano_corrente_nao_esconde_a_falha():
    atual = lote.zip_do_bps(AGORA.year)
    with pytest.raises(requests.HTTPError):
        POR_ID["bps"].descobrir(Servidor({}, {atual: 500}), AGORA)


# --- registro ---------------------------------------------------------------------------------------------
def test_o_lote_tem_tres_fontes_sem_id_repetido_e_dentro_da_lista_do_arquivista():
    ids = [f.id for f in lote.fontes()]
    assert ids == ["comprasgov-sicaf-ativos", "comprasgov-sicaf-inativos", "bps"]
    todas = [f.id for f in FONTES]
    assert len(todas) == len(set(todas))
    assert set(ids) <= set(todas)


def test_a_licenca_de_cada_fonte():
    for id_ in lote.SITUACOES_DO_SICAF:
        assert "compras.gov.br" in licenca_da_fonte(id_)
        assert marca_da_fonte(id_) is Marca.VENDAVEL
    assert "19/11/2026" in licenca_da_fonte("bps")
    assert (
        marca_da_fonte("bps") is Marca.A_CONFIRMAR
    )  # a resposta do Fala.BR do "ms" não cobre o BPS
