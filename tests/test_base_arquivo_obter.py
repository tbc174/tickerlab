"""Formas especiais de obter (base/arquivo/obter.py) e a 2ª leva da prévia do balanço."""

import io
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
