"""Fontes da conferência de 14/11/2026 no arquivista (base/arquivo/lote_conferidas_14_11.py, linha 904, PR 1):
ECF por forma de tributação, PAT, TAH, PADOs, homologados e tancagem. Sem internet, com dublês; nenhum
documento real (o CPF é o de teste, montado na hora)."""

import csv
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook

from base import licenca
from base.arquivo import lote_conferidas_14_11 as lote
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from base.arquivo.fontes import FONTES, POR_ID
from base.arquivo.obter import csv_so_com_colunas
from src.banco.coletas import (
    SEM_LICENCA_CONHECIDA,
    Marca,
    licenca_da_fonte,
    marca_da_fonte,
)
from tests.ajudantes_de_cpf import CPF_DE_TESTE, no_formato

AGORA = datetime(2026, 11, 14, 15, tzinfo=UTC)
IDS_DO_LOTE = [f.id for f in lote.fontes()]
CNPJ_INVENTADO = "12345678000195"
NOME_INVENTADO = "EMPRESA FICTICIA DE TESTE LTDA"
CPF_MASCARADO = no_formato(CPF_DE_TESTE, "***.ddd.ddd-**")


class Servidor:
    """Responde `ler` e `baixar` com bytes em memória; `redireciona` dá o endereço final de um pedido."""

    def __init__(
        self, arquivos: dict[str, bytes], redireciona: dict[str, str] | None = None
    ):
        self.arquivos = arquivos
        self.redireciona = redireciona or {}
        self.baixados: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        return Resposta(self.redireciona.get(url, url), self.arquivos.get(url, b""), {})

    def baixar(self, url, destino: Path):
        self.baixados.append(url)
        destino.write_bytes(self.arquivos[url])
        return {"ETag": '"x"'}


def _zip(membros: dict[str, bytes]) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        for nome, conteudo in membros.items():
            arquivo.writestr(nome, conteudo)
    return saida.getvalue()


def _linhas_do_csv(destino: Path, codificacao: str = "utf-8") -> list[dict[str, str]]:
    with destino.open(encoding=codificacao, newline="") as texto:
        return list(csv.DictReader(texto, delimiter=";"))


# --- Receita: ECF -----------------------------------------------------------------------------------------
def test_a_ecf_guarda_o_endereco_publico_e_baixa_pelo_token_do_compartilhamento(
    tmp_path,
):
    nome = lote.ZIPS_DA_ECF["rfb-renuncias-regime-presumido"]
    download = lote.DOWNLOAD_DA_RECEITA.format(
        token="AbC123", caminho=lote.PASTA_DA_ECF + nome
    )
    servidor = Servidor(
        {download: b"zip"},
        {lote.RAIZ_DA_RECEITA: lote.RAIZ_DA_RECEITA + "index.php/s/AbC123"},
    )
    (alvo,) = POR_ID["rfb-renuncias-regime-presumido"].descobrir(servidor, AGORA)
    assert alvo.url == lote.RAIZ_DA_RECEITA + lote.PASTA_DA_ECF + nome
    assert licenca.familia_do_endereco(alvo.url) == "rfb-renuncias"
    assert alvo.obter is not None
    alvo.obter(servidor, tmp_path / "ecf.zip")
    assert servidor.baixados == [download]
    assert (tmp_path / "ecf.zip").read_bytes() == b"zip"


def test_a_ecf_sem_o_token_no_redirecionamento_e_erro_de_descoberta(tmp_path):
    (alvo,) = POR_ID["rfb-renuncias-regime-real"].descobrir(Servidor({}), AGORA)
    assert alvo.obter is not None
    with pytest.raises(ErroDeDescoberta, match="token"):
        alvo.obter(Servidor({}), tmp_path / "ecf.zip")


def test_os_quatro_regimes_tem_um_zip_cada():
    assert len(set(lote.ZIPS_DA_ECF.values())) == 4
    assert {POR_ID[i].id for i in lote.ZIPS_DA_ECF} == set(lote.ZIPS_DA_ECF)


# --- MTE: PAT ---------------------------------------------------------------------------------------------
def _pagina_do_pat(*links: str) -> bytes:
    return "".join(f'<a href="{link}">x</a>' for link in links).encode()


def test_o_pat_acha_a_planilha_da_relacao_so_na_pasta_do_mte():
    beneficiarias = lote.PASTA_DO_PAT + "beneficiarias-ativas-2026-11.xlsx"
    pagina = _pagina_do_pat(
        "https://exemplo.invalido/beneficiarias-ativas.xlsx",
        beneficiarias,
        lote.PASTA_DO_PAT + "nutricionistas-2026-11.xlsx",
    )
    servidor = Servidor({lote.PAGINA_DO_PAT: pagina})
    (alvo,) = POR_ID["mte-pat-beneficiarias"].descobrir(servidor, AGORA)
    assert alvo.url == beneficiarias
    assert licenca.familia_do_endereco(alvo.url) == "mte-pat"
    with pytest.raises(ErroDeDescoberta, match="fornecedoras"):
        POR_ID["mte-pat-fornecedoras"].descobrir(servidor, AGORA)


def test_a_relacao_de_nutricionistas_nunca_vira_fonte():
    assert lote.PESSOA_FISICA_DO_PAT not in " ".join(lote.RELACOES_DO_PAT.values())
    assert not [i for i in IDS_DO_LOTE if lote.PESSOA_FISICA_DO_PAT in i]


def _planilha(cabecalho: list[str], *linhas: list[object]) -> bytes:
    livro = Workbook()
    aba = livro.active
    assert aba is not None
    aba.append(cabecalho)
    for linha in linhas:
        aba.append(linha)
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


CABECALHO_DO_PAT = [
    "CNPJ",
    "RAZÃO SOCIAL",
    "MATRIZ OU FILIAL",
    "MUNICÍPIO",
    "UF",
    "Nº REGISTRO",
    "DATA CADASTRO",
    "ATÉ 5 SALÁRIOS MÍNIMOS",
    "ACIMA DE 5 SALÁ­RIOS MÍNIMOS",  # o hífen invisível que o MTE põe no meio da palavra
    "TOTAL TRABALHADORES ATENDIDOS",
    "SITUAÇÃO",
]


def _linha_do_pat(documento: str, registro: str) -> list[object]:
    return [
        documento,
        NOME_INVENTADO,
        "MATRIZ",
        "SÃO PAULO",
        "SP",
        registro,
        datetime(2020, 3, 4),  # noqa: DTZ001 (a célula do Excel não tem fuso)
        10,
        2,
        12,
        "ATIVA",
    ]


def test_a_planilha_do_pat_vira_csv_so_com_cnpj_inteiro_e_sem_a_razao_social(tmp_path):
    url = lote.PASTA_DO_PAT + "beneficiarias.xlsx"
    planilha = _planilha(
        CABECALHO_DO_PAT,
        _linha_do_pat(CNPJ_INVENTADO, "R1"),
        _linha_do_pat(CPF_DE_TESTE, "R2"),
        _linha_do_pat(CPF_MASCARADO, "R3"),
        _linha_do_pat("", "R4"),
    )
    destino = tmp_path / "pat.csv"
    lote.xlsx_do_pat(url)(Servidor({url: planilha}), destino)
    linhas = _linhas_do_csv(destino)
    assert [linha["NOREGISTRO"] for linha in linhas] == ["R1"]
    assert linhas[0]["DATACADASTRO"] == "2020-03-04"
    assert list(linhas[0]) == list(lote.COLUNAS_DO_PAT)
    assert NOME_INVENTADO not in destino.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.bruto"))


def test_planilha_do_pat_sem_uma_coluna_e_erro_nunca_vazia():
    sem_o_cnpj = _planilha(
        CABECALHO_DO_PAT[1:], _linha_do_pat(CNPJ_INVENTADO, "R1")[1:]
    )
    with pytest.raises(ValueError, match="CNPJ"):
        lote.planilha_do_pat(sem_o_cnpj, "pat.xlsx")


# --- ANM, Anatel: só a linha com CNPJ inteiro e sem a coluna do nome ------------------------------------
def test_a_tah_chega_sem_o_nome_do_titular_e_sem_cpf(tmp_path):
    cabecalho = "NRProcesso,NRAnoProcesso,NRCpfCnpj,NMPessoa,DSFaseProcesso,NMSuperintendencia,NRHectares,DTQuitacao,VLPago,VLTotal"
    corpo = [
        f'1,2020,{CNPJ_INVENTADO},{NOME_INVENTADO},AUTORIZAÇÃO DE PESQUISA,SP,"10,5",2026-01-31,"100,00","100,00"',
        f'2,2020,{CPF_MASCARADO},{NOME_INVENTADO},AUTORIZAÇÃO DE PESQUISA,SP,"1,0",,"0,00","10,00"',
    ]
    (alvo,) = POR_ID["anm-tah"].descobrir(Servidor({}), AGORA)
    assert alvo.url == lote.TAH_DA_ANM
    assert alvo.obter is not None
    destino = tmp_path / "tah.csv"
    alvo.obter(
        Servidor({lote.TAH_DA_ANM: "\n".join([cabecalho, *corpo]).encode("latin-1")}),
        destino,
    )
    linhas = _linhas_do_csv(destino, "latin-1")
    assert [linha["NRProcesso"] for linha in linhas] == ["1"]
    assert "NMPessoa" not in linhas[0]
    assert NOME_INVENTADO not in destino.read_text(encoding="latin-1")


def test_os_pados_leem_so_o_csv_dos_processos_no_zip_e_tiram_o_cpf(tmp_path):
    cabecalho = "Processo;Anexação;Tema;Empresa;Grupo Econômico;CPF/CNPJ;Serviço;Status do Processo;Fase;Multa Aplicada no Processo;Situação do Pagamento"
    corpo = [
        f"P1;Principal;Qualidade;{NOME_INVENTADO};GRUPO;{CNPJ_INVENTADO};SMP;Encerrado;Decisão;1.000,00;Pago",
        f"P2;Principal;Qualidade;{NOME_INVENTADO};GRUPO;{CPF_DE_TESTE};SCM;Encerrado;Decisão;10,00;Pago",
    ]
    conteudo = _zip(
        {
            lote.MEMBRO_DOS_PADOS: ("﻿" + "\n".join([cabecalho, *corpo])).encode(
                "utf-8"
            ),
            "CSV_INFRACOES.csv": b"Processo;Infracao\nP1;Art. 1\n",
        }
    )
    (alvo,) = POR_ID["anatel-pados"].descobrir(Servidor({}), AGORA)
    assert alvo.obter is not None
    destino = tmp_path / "pados.csv"
    alvo.obter(Servidor({lote.PADOS_DA_ANATEL: conteudo}), destino)
    linhas = _linhas_do_csv(destino)
    assert [linha["Processo"] for linha in linhas] == ["P1"]
    assert not {"Empresa", "Grupo Econômico"} & set(linhas[0])
    assert NOME_INVENTADO not in destino.read_text(encoding="utf-8")


def test_zip_com_dois_csvs_sem_dizer_o_membro_e_erro(tmp_path):
    url = "https://exemplo.invalido/dois.zip"
    obter = csv_so_com_colunas(url, ("A",), "utf-8", dentro_do_zip=True)
    servidor = Servidor({url: _zip({"um.csv": b"A\n1\n", "dois.csv": b"A\n2\n"})})
    with pytest.raises(ValueError, match="um CSV só"):
        obter(servidor, tmp_path / "x.csv")


def test_os_homologados_chegam_sem_o_nome_do_solicitante_e_do_fabricante(tmp_path):
    colunas = list(lote.COLUNAS_DOS_HOMOLOGADOS)
    cabecalho = ";".join([*colunas, "Nome do Solicitante", "Nome do Fabricante"])

    def linha(documento: str) -> str:
        valores = {c: "x" for c in colunas} | {"CNPJ do Solicitante": documento}
        return ";".join(
            [*(valores[c] for c in colunas), NOME_INVENTADO, NOME_INVENTADO]
        )

    conteudo = _zip(
        {
            "produtos.csv": "\n".join(
                [cabecalho, linha(CNPJ_INVENTADO), linha(CPF_DE_TESTE)]
            ).encode()
        }
    )
    (alvo,) = POR_ID["anatel-homologados"].descobrir(Servidor({}), AGORA)
    assert alvo.obter is not None
    destino = tmp_path / "homologados.csv"
    alvo.obter(Servidor({lote.HOMOLOGADOS_DA_ANATEL: conteudo}), destino)
    linhas = _linhas_do_csv(destino)
    assert [linha_["CNPJ do Solicitante"] for linha_ in linhas] == [CNPJ_INVENTADO]
    assert NOME_INVENTADO not in destino.read_text(encoding="utf-8")


# --- ANP: tancagem ----------------------------------------------------------------------------------------
def test_a_tancagem_pega_o_ultimo_csv_do_ano_mais_alto_e_so_da_pasta_da_anp():
    def link(ano: int, mes: str) -> str:
        return f"{lote.PASTA_DA_TANCAGEM}{ano}/tancagem-{mes}.csv"

    pagina = "".join(
        f'<a href="{u}">x</a>'
        for u in [
            link(2026, "01"),
            link(2026, "02"),
            link(2025, "12"),
            "https://exemplo.invalido/2027/tancagem-01.csv",
        ]
    ).encode()
    alvos = lote.descobrir_tancagem(Servidor({lote.PAGINA_DA_TANCAGEM: pagina}), AGORA)
    assert [a.url for a in alvos] == [link(2026, "02")]
    assert licenca.familia_do_endereco(alvos[0].url) == "anp-tancagem"


def test_a_tancagem_sem_csv_e_erro_de_descoberta():
    with pytest.raises(ErroDeDescoberta, match="tancagem"):
        lote.descobrir_tancagem(
            Servidor({lote.PAGINA_DA_TANCAGEM: b"<html></html>"}), AGORA
        )


# --- o lote na lista do arquivista e a licença de cada conjunto -------------------------------------------
def test_o_lote_tem_onze_fontes_sem_id_repetido_e_dentro_da_lista_do_arquivista():
    assert len(IDS_DO_LOTE) == 11 == len(set(IDS_DO_LOTE))
    ids = [f.id for f in FONTES]
    assert len(ids) == len(set(ids))
    assert set(IDS_DO_LOTE) <= set(ids)


def test_cada_fonte_do_lote_tem_a_licenca_lida_em_14_11():
    for id_ in IDS_DO_LOTE:
        assert licenca_da_fonte(id_) != SEM_LICENCA_CONHECIDA, id_
    for id_ in lote.ZIPS_DA_ECF:
        assert marca_da_fonte(id_) is Marca.VENDAVEL, (
            id_
        )  # a mesma leitura da DIRBI e da ECF (ADR 0122)
    for id_ in lote.RELACOES_DO_PAT:
        assert marca_da_fonte(id_) is Marca.USO_INTERNO, (
            id_
        )  # só o rodapé CC BY-ND do gov.br
    for id_ in ("anm-tah", "anatel-pados", "anatel-homologados", "anp-tancagem"):
        assert marca_da_fonte(id_) is Marca.A_CONFIRMAR, id_
        assert "14/11/2026" in licenca_da_fonte(id_), id_


def test_os_enderecos_das_fontes_caem_na_familia_da_licenca():
    assert licenca.familia_do_endereco(lote.TAH_DA_ANM) == "anm-tah"
    assert licenca.familia_do_endereco(lote.PADOS_DA_ANATEL) == "anatel-pados"
    assert (
        licenca.familia_do_endereco(lote.HOMOLOGADOS_DA_ANATEL) == "anatel-homologados"
    )


def test_so_a_tah_e_os_homologados_sao_pesados():
    assert {f.id for f in lote.fontes() if f.pesada} == {
        "anm-tah",
        "anatel-homologados",
    }
