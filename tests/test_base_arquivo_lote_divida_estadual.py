"""Coleta da dívida ativa do Paraná (Sefa-PR, linha 755 da fila; motor de risco cedente/sacado).

O Portal do Devedor (`listadevedores.sefa.pr.gov.br`) oferece na aba "Arquivo" um ZIP gerado todo dia
com um CSV de todos os débitos, de pessoa física e jurídica. Aqui se confere o que a coleta baixa e o
que sai **antes** de guardar: só linha de CNPJ, sem a coluna `CPF` nem `Nome/razão social` (ADR 0075 e
0088). Os arquivos são de mentira.
"""

import io
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from base.arquivo import lote_divida_estadual as lote
from base.arquivo import registro
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from base.arquivo.fontes import FONTES, POR_ID
from base.licenca import familia_do_endereco
from src.banco.coletas import Marca, licenca_da_fonte, marca_da_fonte

AGORA = datetime(2026, 11, 6, 22, tzinfo=UTC)
PORTAL = lote.PORTAL_DO_PR
PAGINA = lote.PAGINA_DO_PR
ZIP = f"{PORTAL}/portal-devedor/download/csv/lista-devedores-pr_06-11-2026_04_00.zip"
CABECALHO = (
    "Dívida ativa,Data da inscrição do débito,Data da atualização,Valor do imposto,"
    "Valor da multa,Valor dos juros,Valor total,Tipo do crédito,CPF,CNPJ,Nome/razão social,"
    "Suspensão de exigibilidade,Indicativo de garantia,Indicativo de parcelamento ativo\n"
)
EMPRESA = "76.568.617/0001-70"
OUTRA = "08.811.226/0010-75"


class Servidor:
    """Dublê do `Cliente`: a página do portal e o ZIP, fixos."""

    def __init__(self, existem: dict[str, bytes]):
        self.existem = existem
        self.pedidos: list[str] = []

    def ler(self, url, **_):
        self.pedidos.append(url)
        return Resposta(url, self.existem[url], {})

    def baixar(self, url, destino: Path):
        self.pedidos.append(url)
        destino.write_bytes(self.existem[url])
        return {"ETag": "x"}


def _pagina(*enderecos: str) -> bytes:
    links = "".join(f'<li><a href="{e}">baixar</a></li>' for e in enderecos)
    return f"<html><body><ul>{links}</ul></body></html>".encode()


def _linha(
    numero: str,
    cnpj: str,
    nome: str = "EMPRESA SA",
    cpf: str = "",
    suspensao: str = "Não",
) -> str:
    return (
        f"{numero},18/06/1973,01/11/2026,1787.10,5.91,0.00,1793.01,ICMS,{cpf},{cnpj},"
        f"{nome},{suspensao},Não,Não\n"
    )


def _zip(csv: str, nome: str = "portal-devedores.csv") -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr(nome, csv.encode("utf-8-sig"))
    return saida.getvalue()


def _filtrar(conteudo: str) -> str:
    saida = io.BytesIO()
    lote.filtrar_csv_do_pr(io.BytesIO(conteudo.encode("utf-8-sig")), saida)
    return saida.getvalue().decode("utf-8")


def test_o_portal_e_a_pagina_sao_os_lidos_em_06_11():
    assert PORTAL == "https://listadevedores.sefa.pr.gov.br"
    assert PAGINA.removeprefix(PORTAL) == "/portal-devedor/arquivo"
    assert "CPF" not in lote.COLUNAS_GUARDADAS_NO_PR
    assert "Nome/razão social" not in lote.COLUNAS_GUARDADAS_NO_PR


def test_descobre_o_zip_do_dia_pela_pagina():
    servidor = Servidor({PAGINA: _pagina(ZIP, ZIP, f"{PORTAL}/portal-devedor/outro")})
    alvos = lote.descobrir_o_pr(servidor, AGORA)
    assert [a.url for a in alvos] == [ZIP]
    assert alvos[0].extensao == ".csv"
    assert alvos[0].obter is not None  # nada é guardado sem o filtro
    assert servidor.pedidos == [PAGINA]


def test_so_baixa_do_proprio_portal_e_resolve_link_relativo():
    """Link vindo da página é dado, não ordem: de outro host ou de outro esquema, não se baixa."""
    relativo = "/portal-devedor/download/csv/a.zip"
    servidor = Servidor(
        {
            PAGINA: _pagina(
                relativo,
                "https://outro.exemplo/portal-devedor/download/csv/b.zip",
                "http://127.0.0.1/portal-devedor/download/csv/c.zip",
                "http://listadevedores.sefa.pr.gov.br/portal-devedor/download/csv/d.zip",
                f"{PORTAL}.outro.exemplo/portal-devedor/download/csv/e.zip",
            )
        }
    )
    assert [a.url for a in lote.descobrir_o_pr(servidor, AGORA)] == [
        f"{PORTAL}{relativo}"
    ]


def test_pagina_sem_zip_do_portal_e_erro_de_descoberta():
    servidor = Servidor({PAGINA: _pagina("https://outro.exemplo/download/csv/a.zip")})
    with pytest.raises(ErroDeDescoberta, match="nenhum ZIP"):
        lote.descobrir_o_pr(servidor, AGORA)


def test_filtro_guarda_so_cnpj_sem_nome_e_sem_cpf():
    bruto = (
        CABECALHO
        + _linha("1", EMPRESA, "CALCADOS BIRU LTDA")
        + _linha("2", "", "JOAO DA SILVA", cpf="123.456.789-09")  # pessoa física
        + _linha(
            "3", "00.184.780/0001-77", "JOAO ADOEZIO 123.456.789-09"
        )  # CPF no nome
        + _linha(
            "4", "00.184.780/0001-78", "OUTRA", cpf="123.456.789-09"
        )  # CPF na coluna
        + _linha("5", "", "SEM DOCUMENTO")
        + _linha("6", OUTRA, "FORTQUIM LTDA", suspensao="DEPOSITO JUDICIAL")
    )
    guardado = _filtrar(bruto)
    linhas = guardado.strip().splitlines()
    assert linhas[0].startswith('"Dívida ativa";"Data da inscrição do débito"')
    assert len(linhas) == 3
    assert EMPRESA in linhas[1] and OUTRA in linhas[2]
    assert "DEPOSITO JUDICIAL" in linhas[2]
    for nome_ou_cpf in (
        "BIRU",
        "FORTQUIM",
        "JOAO",
        "123.456.789-09",
        "Nome/raz",
        "CPF",
    ):
        assert nome_ou_cpf not in guardado


def test_filtro_recusa_documento_com_texto_junto_do_cnpj():
    """A coluna do documento é gravada como veio: "CNPJ - razão social" levaria o nome ao disco."""
    bruto = (
        CABECALHO
        + _linha("1", f"{EMPRESA} - FULANO 029.037.377-89")
        + _linha("2", EMPRESA)
    )
    guardado = _filtrar(bruto)
    assert len(guardado.strip().splitlines()) == 2
    assert "FULANO" not in guardado and "029.037" not in guardado


def test_filtro_mantem_datas_e_valores_como_a_fonte_escreve():
    guardado = _filtrar(CABECALHO + _linha("1", EMPRESA))
    assert '"18/06/1973"' in guardado and '"1787.10"' in guardado


def test_filtro_descarta_linha_com_numero_de_colunas_diferente():
    guardado = _filtrar(CABECALHO + "1,quebrada\n" + _linha("2", EMPRESA))
    assert len(guardado.strip().splitlines()) == 2


def test_filtro_recusa_cabecalho_sem_coluna_esperada():
    with pytest.raises(ValueError, match="CNPJ"):
        _filtrar(CABECALHO.replace(",CNPJ,", ",Documento,") + "x\n")


def test_filtro_recusa_cabecalho_sem_a_coluna_de_pessoa():
    """Sem a coluna `CPF` não dá para garantir que o arquivo não mudou de forma: não guarda."""
    with pytest.raises(ValueError, match="CPF"):
        _filtrar(CABECALHO.replace(",CPF,", ",Outra,") + "x\n")


def test_filtro_recusa_arquivo_vazio():
    with pytest.raises(ValueError, match="vazio"):
        _filtrar("")


def test_obter_grava_o_csv_filtrado_e_nao_deixa_o_bruto(tmp_path):
    csv = CABECALHO + _linha("1", EMPRESA, "CALCADOS BIRU LTDA")
    servidor = Servidor({ZIP: _zip(csv)})
    destino = tmp_path / "saida.csv"
    alvo = lote.alvo_do_zip_do_pr(ZIP)
    assert alvo.obter is not None
    alvo.obter(servidor, destino)
    assert "BIRU" not in destino.read_text(encoding="utf-8")
    assert [p.name for p in tmp_path.iterdir()] == ["saida.csv"]


@pytest.mark.parametrize("conteudo", [_zip(CABECALHO, "a.txt"), b"isto nao e um zip"])
def test_obter_nao_deixa_arquivo_quando_o_zip_muda_de_forma(tmp_path, conteudo):
    servidor = Servidor({ZIP: conteudo})
    with pytest.raises((ValueError, zipfile.BadZipFile)):
        lote.alvo_do_zip_do_pr(ZIP).obter(servidor, tmp_path / "saida.csv")  # type: ignore[misc]
    assert list(tmp_path.iterdir()) == []


def test_obter_apaga_o_bruto_que_sobrou_de_uma_rodada_morta(tmp_path):
    destino = tmp_path / "saida.csv"
    sobra = tmp_path / "saida.csv.bruto"
    sobra.write_bytes(b"CPF e nome de rodada anterior")
    servidor = Servidor({ZIP: _zip(CABECALHO + _linha("1", EMPRESA))})
    lote.alvo_do_zip_do_pr(ZIP).obter(servidor, destino)  # type: ignore[misc]
    assert [p.name for p in tmp_path.iterdir()] == ["saida.csv"]


def test_obter_recusa_zip_com_dois_csvs(tmp_path):
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr("a.csv", CABECALHO)
        arquivo.writestr("b.csv", CABECALHO)
    servidor = Servidor({ZIP: saida.getvalue()})
    with pytest.raises(ValueError, match="2 CSVs"):
        lote.alvo_do_zip_do_pr(ZIP).obter(servidor, tmp_path / "saida.csv")  # type: ignore[misc]
    assert list(tmp_path.iterdir()) == []


def test_a_fonte_esta_no_registro_semanal():
    fonte = POR_ID["sefapr-divida-ativa"]
    assert fonte in FONTES and fonte.grupo == "semanal"
    assert fonte in lote.fontes()


def test_a_licenca_e_a_confirmar_vendavel_por_risco_assumido_e_o_portal_foi_lido():
    fonte = "sefapr-divida-ativa"
    assert "a confirmar" in licenca_da_fonte(fonte)
    assert len(licenca_da_fonte(fonte)) <= 80
    assert marca_da_fonte(fonte) == Marca.VENDAVEL
    assert registro.TERMOS_LIDOS_EM["sefapr"] == date(2026, 11, 6)
    assert familia_do_endereco(ZIP) == "sefapr"
