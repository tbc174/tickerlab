"""Formas especiais de obter (base/arquivo/obter.py) e a 2ª leva da prévia do balanço."""

import copy
import io
import json
import random
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base.arquivo import coleta, fontes, obter
from base.arquivo.coleta import Alvo, Fonte, Resposta
from src.banco import coletas

AGORA = datetime(2026, 10, 14, 5, tzinfo=UTC)
URL_DO_ZIP = "https://www.anatel.gov.br/dadosabertos/x/acessos.zip"


def _zip(arquivos: dict[str, bytes], compressao: int = zipfile.ZIP_DEFLATED) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", compressao) as arquivo_zip:
        for nome, conteudo in arquivos.items():
            arquivo_zip.writestr(nome, conteudo)
    return saida.getvalue()


class ServidorComTrechos:
    """Responde HEAD e pedidos de trecho sobre arquivos em memória; conta os bytes servidos."""

    def __init__(self, arquivos: dict[str, bytes], cabecalhos: dict | None = None):
        self.arquivos = arquivos
        self.extra = cabecalhos or {}
        self.bytes_servidos = 0
        self.baixados: list[str] = []

    def cabecalhos(self, url):
        return {"Content-Length": str(len(self.arquivos[url])), **self.extra}

    def ler_trecho(self, url, inicio, fim):
        trecho = self.arquivos[url][inicio : fim + 1]
        self.bytes_servidos += len(trecho)
        return trecho

    def ler(self, url, *, metodo="GET", cabecalhos=None):
        return Resposta(url, self.arquivos[url], {})

    def baixar(self, url, destino: Path):
        self.baixados.append(url)
        destino.write_bytes(self.arquivos[url])
        return {"ETag": '"samp"'}


def test_zip_remoto_le_so_o_indice_e_o_arquivo_pedido(tmp_path):
    # 3 trechos de leitura de bytes aleatórios, sem compressão: o ZIP inteiro é bem maior que o
    # índice mais o pedaço do CSV pedido
    grande = random.Random(0).randbytes(3 * obter.TAMANHO_DO_TRECHO)
    conteudo = _zip(
        {
            "Acessos_2026_Colunas.csv": b"Ano;Acessos\n2026;10\n",
            "Acessos_Longo.csv": grande,
        },
        zipfile.ZIP_STORED,
    )
    servidor = ServidorComTrechos({URL_DO_ZIP: conteudo}, {"ETag": '"zip-1"'})
    assert obter.membros_do_zip_remoto(servidor, URL_DO_ZIP) == [
        "Acessos_2026_Colunas.csv",
        "Acessos_Longo.csv",
    ]
    servidor.bytes_servidos = 0
    destino = tmp_path / "saida.csv"
    cabecalhos = obter.extrair_do_zip_remoto(URL_DO_ZIP, "Acessos_2026_Colunas.csv")(
        servidor, destino
    )
    assert destino.read_bytes() == b"Ano;Acessos\n2026;10\n"
    assert cabecalhos["ETag"] == '"zip-1"'  # a pesada pula quando o ZIP não mudou
    # não baixou o ZIP inteiro: só o índice (fim) e o pedaço do CSV pedido
    assert servidor.bytes_servidos < len(conteudo)


def test_parquet_sai_sem_as_colunas_pessoais(tmp_path):
    origem = tmp_path / "origem.parquet"
    pd.DataFrame(
        {
            "SigAgenteDistribuidora": ["CEMIG", "LIGHT"],
            "NumCNPJAgenteAcessante": [12345678901.0, 0.0],  # CPF guardado como número
            "NomAgenteAcessante": ["Fulana de Tal", ""],
            "VlrMercado": [10.5, 20.0],
        }
    ).to_parquet(origem, index=False)
    url = "https://dadosabertos.aneel.gov.br/samp-2026.parquet"
    servidor = ServidorComTrechos({url: origem.read_bytes()})
    destino = tmp_path / "guardado.parquet"
    cabecalhos = obter.parquet_sem_colunas(url, fontes.COLUNAS_PESSOAIS_DO_SAMP)(
        servidor, destino
    )
    guardado = pd.read_parquet(destino)
    assert list(guardado.columns) == ["SigAgenteDistribuidora", "VlrMercado"]
    assert len(guardado) == 2
    assert cabecalhos == {"ETag": '"samp"'}
    assert not list(tmp_path.glob("*.bruto"))  # o original com CPF não fica no disco


def test_anatel_escolhe_colunas_e_totais_de_cada_zip():
    conteudo = _zip(
        {
            "Acessos_2026_1S_Colunas.csv": b"a",
            "Acessos_Total.csv": b"b",
            "Acessos_2026_1S.csv": b"c",
            "Densidades.pdf": b"d",
        }
    )
    servidor = ServidorComTrechos(dict.fromkeys(fontes.ZIPS_DA_ANATEL, conteudo))
    alvos = fontes.descobrir_anatel(servidor, AGORA)
    assert len(alvos) == 2 * len(fontes.ZIPS_DA_ANATEL)
    assert alvos[0].url == f"{fontes.ZIPS_DA_ANATEL[0]}#Acessos_2026_1S_Colunas.csv"
    assert all(a.extensao == ".csv" and a.obter is not None for a in alvos)


def test_anatel_sem_csv_de_acessos_e_falha():
    servidor = ServidorComTrechos(
        dict.fromkeys(fontes.ZIPS_DA_ANATEL, _zip({"Densidades.pdf": b"d"}))
    )
    with pytest.raises(coleta.ErroDeDescoberta):
        fontes.descobrir_anatel(servidor, AGORA)


def test_susep_tira_do_zip_so_os_csvs_sem_pessoas():
    """O ZIP do SES traz administradores, contatos e acionistas: nunca entram (série 4, PR 5b)."""
    com_pessoas = ("Ses_Administradores.csv", "ses_contatos.csv", "Ses_part_acion.csv")
    conteudo = _zip(
        dict.fromkeys([*fontes.CSVS_DA_SUSEP, *com_pessoas, "SES_Balanco.csv"], b"x")
    )
    servidor = ServidorComTrechos({fontes.SES_DA_SUSEP: conteudo})
    alvos = fontes.descobrir_susep(servidor, AGORA)
    membros = [a.url.rpartition("#")[2] for a in alvos]
    assert membros == list(fontes.CSVS_DA_SUSEP)
    assert not set(membros) & set(com_pessoas)
    assert all(a.extensao == ".csv" and a.obter is not None for a in alvos)


def test_susep_sem_o_csv_de_seguros_falha():
    conteudo = _zip(dict.fromkeys(fontes.CSVS_DA_SUSEP[1:], b"x"))
    servidor = ServidorComTrechos({fontes.SES_DA_SUSEP: conteudo})
    with pytest.raises(coleta.ErroDeDescoberta, match="Ses_seguros"):
        fontes.descobrir_susep(servidor, AGORA)


def test_pix_pede_o_fim_dos_tres_ultimos_meses_fechados():
    datas = [a.url.split("@Data='")[1][:10] for a in fontes.descobrir_pix(None, AGORA)]
    assert datas == ["2026-07-31", "2026-08-31", "2026-09-30"]
    virada = fontes.descobrir_pix(None, datetime(2026, 3, 5, tzinfo=UTC))
    assert [a.url.split("@Data='")[1][:10] for a in virada] == [
        "2025-12-31",
        "2026-01-31",
        "2026-02-28",
    ]
    assert fontes.POR_ID["bcb-pix-chaves"].tipo == "json"


def test_samp_so_parquet_e_sempre_sem_dado_pessoal():
    portal = fontes.PORTAL_DA_ANEEL
    resposta = (
        b'{"result": {"resources": ['
        b'{"url": "https://d/samp-2026.csv", "format": "CSV"},'
        b'{"url": "https://d/samp-2026.parquet", "format": "PARQUET"}]}}'
    )
    servidor = ServidorComTrechos(
        {f"{portal}/api/3/action/package_show?id=samp": resposta}
    )
    alvos = fontes.descobrir_samp(servidor, AGORA)
    assert [a.url for a in alvos] == ["https://d/samp-2026.parquet"]
    assert alvos[0].obter is not None


def test_arquivista_usa_a_forma_especial_de_obter(banco, tmp_path):
    def obter_falso(cliente, destino):
        destino.write_bytes(b"PK\x03\x04 conteudo tratado")
        return {"ETag": '"x"'}

    url = "https://exemplo.gov.br/grande.zip#dentro.csv"
    fonte = Fonte(
        "teste-especial",
        "diaria",
        lambda cliente, agora: [Alvo(url, ".csv", obter_falso)],
    )
    servidor = ServidorComTrechos({})
    resultado = coleta.arquivar(fonte, servidor, AGORA, tmp_path / "t", pausa=0)
    assert (resultado.novos, resultado.falhas) == (1, [])
    assert servidor.baixados == []  # não baixou o endereço inteiro
    with banco.connect() as conexao:
        assert coletas.ultima_coleta_ok(conexao, url) is not None


def test_pacote_de_certificados_soma_os_intermediarios(tmp_path):
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    assert coleta.pacote_de_certificados(vazio) == coleta.certifi.where()
    (tmp_path / "extra.pem").write_text(
        "-----BEGIN CERTIFICATE-----\nAAA\n-----END CERTIFICATE-----\n",
        encoding="ascii",
    )
    pacote = Path(coleta.pacote_de_certificados(tmp_path)).read_text(encoding="ascii")
    assert pacote.startswith(Path(coleta.certifi.where()).read_text(encoding="ascii"))
    assert pacote.endswith("AAA\n-----END CERTIFICATE-----\n")
    # o intermediário do SERPRO (Comex Stat) vai no repositório
    assert list(coleta.CERTIFICADOS_EXTRAS.glob("*.pem"))


def test_cadastro_da_ans_e_guardado_sem_representante_nem_contato(tmp_path):
    """O cadastro das operadoras traz o nome do representante, e-mail e telefone: nunca entram."""
    bruto = (
        b"REGISTRO_OPERADORA;CNPJ;RAZAO_SOCIAL;TELEFONE;ENDERECO_ELETRONICO;REPRESENTANTE;"
        b"CARGO_REPRESENTANTE;DATA_REGISTRO_ANS\n"
        b'"393321";"44649812000138";"OPERADORA FICTICIA";"11999999999";"x@y.com";'
        b'"PESSOA FICTICIA";"DIRETOR";"2000-01-01"\n'
    )
    alvos = fontes.descobrir_cadastro_da_ans(None, AGORA)
    assert len(alvos) == 2
    servidor = ServidorComTrechos({alvos[0].url: bruto})
    destino = tmp_path / "ans.csv"
    alvos[0].obter(servidor, destino)
    guardado = destino.read_text(encoding="utf-8")
    assert (
        guardado.splitlines()[0]
        == "REGISTRO_OPERADORA;CNPJ;RAZAO_SOCIAL;DATA_REGISTRO_ANS"
    )
    assert "PESSOA FICTICIA" not in guardado and "x@y.com" not in guardado
    assert not list(tmp_path.glob("*.bruto"))


def test_cadastro_da_susep_e_guardado_so_com_codigo_nome_e_cnpj(tmp_path):
    bruto = json.dumps(
        {"value": [{"entcodigofip": "05886", "entnome": "PORTO", "entcgc": "61198164000160",
                    "telefone": "1199", "endereco": "RUA X", "mercodigo": 2,
                    "dataautorizacao": "1945-12-06"}]}
    ).encode()  # fmt: skip
    alvo = fontes.descobrir_cadastro_da_susep(None, AGORA)[0]
    destino = tmp_path / "susep.json"
    alvo.obter(ServidorComTrechos({alvo.url: bruto}), destino)
    item = json.loads(destino.read_text(encoding="utf-8"))["value"][0]
    assert set(item) == set(fontes.CAMPOS_DO_CADASTRO_DA_SUSEP)
    assert item["entcgc"] == "61198164000160"


def test_membro_do_zip_remoto_sai_em_dois_trechos_e_com_o_crc_conferido():
    # ZIP dentro de ZIP (PIT do TCE-PR): o índice do ZIP anual dá a posição e o tamanho de cada ZIP
    # interno; ler um deles custa o cabeçalho local e os dados, nada além
    interno = _zip({"a.xml": b"<root/>" * 50})
    grande = random.Random(1).randbytes(2 * obter.TAMANHO_DO_TRECHO)
    conteudo = _zip({"um.zip": interno, "outro.bin": grande}, zipfile.ZIP_DEFLATED)
    servidor = ServidorComTrechos({URL_DO_ZIP: conteudo})
    um, _ = obter.indice_do_zip_remoto(servidor, URL_DO_ZIP)
    servidor.bytes_servidos = 0
    pedidos: list[tuple[int, int]] = []
    ler_trecho = servidor.ler_trecho
    servidor.ler_trecho = lambda url, i, f: (
        pedidos.append((i, f)) or ler_trecho(url, i, f)
    )
    assert obter.ler_membro(servidor, URL_DO_ZIP, um) == interno
    assert len(pedidos) == 2
    assert servidor.bytes_servidos < um.compress_size + 100
    # o CRC do índice confere o que chegou
    torto = copy.copy(um)
    torto.CRC = um.CRC ^ 1
    with pytest.raises(zipfile.BadZipFile):
        obter.ler_membro(servidor, URL_DO_ZIP, torto)


def test_le_utf16_e_utf8_e_limpa_controle():
    texto = '<root><Contrato vlContrato="1\x0b0" flSubContratacao="NÃO"/></root>'
    utf8 = b"\xef\xbb\xbf" + texto.encode("utf-8")
    utf16 = texto.encode("utf-16")  # 2013: começa com FF FE
    assert utf16[:2] == b"\xff\xfe"
    esperado = '<root><Contrato vlContrato="10" flSubContratacao="NÃO"/></root>'
    assert obter.decodificar_xml(utf8) == esperado
    assert obter.decodificar_xml(utf16) == esperado
    assert obter.decodificar_xml(texto.encode("utf-8")) == esperado  # sem BOM: UTF-8


def test_cabecalhos_do_membro_dizem_a_versao_pelo_crc():
    interno = zipfile.ZipInfo("x.zip")
    interno.CRC, interno.file_size = 0xABCDEF01, 1234
    cabecalhos = obter.cabecalhos_do_membro(interno, b"conteudo")
    assert cabecalhos["ETag"] == '"crc32-abcdef01"'
    assert cabecalhos["Content-Length"] == "1234"
    assert len(cabecalhos[obter.SHA256_DA_ORIGEM]) == 64
    assert coleta.assinatura(cabecalhos) == obter.versao_do_membro(interno)
