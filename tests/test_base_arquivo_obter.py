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


def test_zip_remoto_aceita_cabecalho_em_minusculas():
    # o IIS do TCE-PR responde "content-length" (medido em 17/10/2026)
    conteudo = _zip({"a.csv": b"x;y\n"})

    class ServidorMinusculo(ServidorComTrechos):
        def cabecalhos(self, url):
            return {"content-length": str(len(self.arquivos[url]))}

    servidor = ServidorMinusculo({URL_DO_ZIP: conteudo})
    assert obter.membros_do_zip_remoto(servidor, URL_DO_ZIP) == ["a.csv"]


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


def test_filtro_por_cnpj_tira_cpf_e_cnpj_mascarado(tmp_path):
    """Linha de pessoa física (CPF) ou com CNPJ mascarado não chega ao acervo; o separador "," vira ";"."""
    bruto = (
        '"Processo","CPF/CNPJ do titular","Titular","Situação"\n'
        '"1/2020","12.345.678/0001-95","EMPRESA FICTICIA","Ativo"\n'
        '"2/2020","123.456.789-09","PESSOA FICTICIA","Ativo"\n'
        '"3/2020","**.***.678/0001-**","OUTRA","Ativo"\n'
    ).encode("latin-1")
    url = "https://exemplo/scm.csv"
    obter_ = obter.csv_so_com_colunas(
        url, ("Processo", "CPF/CNPJ do titular", "Situação"), "latin-1",
        separador=",", so_com_cnpj_em="CPF/CNPJ do titular",
    )  # fmt: skip
    destino = tmp_path / "scm.csv"
    obter_(ServidorComTrechos({url: bruto}), destino)
    linhas = destino.read_text(encoding="latin-1").splitlines()
    assert linhas == [
        "Processo;CPF/CNPJ do titular;Situação",
        "1/2020;12.345.678/0001-95;Ativo",
    ]


def test_filtro_le_o_csv_dentro_do_zip_e_grava_sem_bom(tmp_path):
    csv_ = "﻿CNPJ ou CPF;Nome Entidade;Tipo de Outorga\n12345678000195;FICTICIA;Autorização\n"
    url = "https://exemplo/prestadoras.zip"
    obter_ = obter.csv_so_com_colunas(
        url, ("CNPJ ou CPF", "Tipo de Outorga"), "utf-8-sig",
        so_com_cnpj_em="CNPJ ou CPF", dentro_do_zip=True,
    )  # fmt: skip
    destino = tmp_path / "anatel.csv"
    obter_(ServidorComTrechos({url: _zip({"p.csv": csv_.encode("utf-8")})}), destino)
    esperado = "CNPJ ou CPF;Tipo de Outorga\r\n12345678000195;Autorização\r\n"
    assert destino.read_bytes() == esperado.encode()
    assert not list(tmp_path.glob("*.bruto"))


def test_filtro_sem_a_coluna_do_documento_falha(tmp_path):
    """Se a fonte renomear a coluna do CNPJ, a coleta para em vez de gravar CPF sem filtro."""
    url = "https://exemplo/x.csv"
    obter_ = obter.csv_so_com_colunas(url, ("A", "DOC"), "utf-8", so_com_cnpj_em="DOC")
    with pytest.raises(ValueError, match="DOC"):
        obter_(ServidorComTrechos({url: b"A;DOCUMENTO\n1;123\n"}), tmp_path / "x.csv")
    assert not list(tmp_path.glob("*.bruto"))


CADASTROS_DE_LICENCAS = (
    *fontes.CADASTROS_DE_EMPRESAS_DA_ANVISA,
    *fontes.CADASTROS_DE_PRODUTOS_DA_ANVISA,
    *fontes.CADASTROS_DO_SIPEAGRO,
    fontes.OUTORGAS_DA_ANATEL_FILTRADAS,
    *fontes.CADASTRO_MINEIRO_FILTRADO,
    fontes.AGENTES_DA_ANCINE_FILTRADOS,
)
# pedaços de nome de coluna que trazem pessoa, contato ou endereço (Ficha Clara: sem pessoa física)
COLUNA_DE_PESSOA = (
    "RAZAO", "FANTASIA", "TITULAR", "NOME_TRANSPORTADOR", "NOME ENTIDADE", "REPRESENTANTE",
    "RESPONSAVEL", "EMAIL", "ELETRÔNICO", "TELEFONE", "CEP", "ENDERECO", "LOGRADOURO", "BAIRRO",
    "HOMEPAGE", "SAC",
)  # fmt: skip


@pytest.mark.parametrize(
    "colunas",
    [c.colunas for c in CADASTROS_DE_LICENCAS] + [fontes.COLUNAS_DO_RNTRC],
)
def test_cadastros_de_licencas_nao_guardam_coluna_de_pessoa(colunas):
    for coluna in colunas:
        nome = coluna.upper().replace(" DO ", " ").replace(" DA ", " ")
        if nome == "CPF/CNPJ TITULAR":
            continue  # o documento, que só fica quando é CNPJ
        assert not any(p in nome for p in COLUNA_DE_PESSOA), coluna


def test_cadastros_de_licencas_guardam_a_coluna_do_cnpj():
    for cadastro in CADASTROS_DE_LICENCAS:
        assert cadastro.cnpj_em in cadastro.colunas, cadastro.url


def test_rntrc_pega_so_o_csv_mais_novo_e_tira_o_nome(tmp_path):
    pacote = {
        "result": {
            "resources": [
                {
                    "url": "https://x/ago.csv",
                    "format": "CSV",
                    "created": "2026-09-10T00:00",
                },
                {
                    "url": "https://x/set.csv",
                    "format": "CSV",
                    "created": "2026-10-10T00:00",
                },
                {
                    "url": "https://x/painel",
                    "format": "HTML",
                    "created": "2026-10-20T00:00",
                },
            ]
        }
    }
    bruto = (
        "nome_transportador;numero_rntrc;cpfcnpjtransportador;cep;uf\n"
        "EMPRESA FICTICIA;1;12345678000195;01000000;SP\n"
        "PESSOA FICTICIA;2;12345678909;02000000;RJ\n"
    ).encode("latin-1")
    url_do_pacote = f"{fontes.PORTAL_DA_ANTT}/api/3/action/package_show?id=rntrc"
    servidor = ServidorComTrechos(
        {url_do_pacote: json.dumps(pacote).encode(), "https://x/set.csv": bruto}
    )
    (alvo,) = fontes.descobrir_rntrc(servidor, AGORA)
    assert alvo.url == "https://x/set.csv" and alvo.obter is not None
    destino = tmp_path / "rntrc.csv"
    alvo.obter(servidor, destino)
    assert destino.read_text(encoding="latin-1").splitlines() == [
        "numero_rntrc;cpfcnpjtransportador;uf",
        "1;12345678000195;SP",
    ]


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


def test_referencia_a_caractere_de_controle_sai_e_as_validas_ficam():
    # o PIT escreve controles como referência (2013 e 2025: "reference to invalid character number")
    texto = '<root><X a="1&#11;0" b="&#x1F;ok" c="S&#227;o &#x26; &#10;"/></root>'
    assert obter.decodificar_xml(texto.encode()) == (
        '<root><X a="10" b="ok" c="S&#227;o &#x26; &#10;"/></root>'
    )


def test_cabecalhos_do_membro_dizem_a_versao_pelo_crc():
    interno = zipfile.ZipInfo("x.zip")
    interno.CRC, interno.file_size = 0xABCDEF01, 1234
    cabecalhos = obter.cabecalhos_do_membro(interno, b"conteudo")
    assert cabecalhos["ETag"] == '"crc32-abcdef01"'
    assert cabecalhos["Content-Length"] == "1234"
    assert len(cabecalhos[obter.SHA256_DA_ORIGEM]) == 64
    assert coleta.assinatura(cabecalhos) == obter.versao_do_membro(interno)


def test_bomba_de_descompressao_para_no_tamanho_do_indice():
    # 50 MB de zeros comprimidos em poucos KB, com o índice dizendo 100 bytes: nunca descomprime tudo
    bomba = _zip({"bomba.zip": bytes(50 * 1024**2)})
    servidor = ServidorComTrechos({URL_DO_ZIP: bomba})
    [membro] = obter.indice_do_zip_remoto(servidor, URL_DO_ZIP)
    mentiroso = copy.copy(membro)
    mentiroso.file_size = 100
    with pytest.raises(zipfile.BadZipFile, match="tamanho"):
        obter.ler_membro(servidor, URL_DO_ZIP, mentiroso)
    grande = copy.copy(membro)
    grande.file_size = obter.LIMITE_DO_MEMBRO + 1
    with pytest.raises(zipfile.BadZipFile, match="limite"):
        obter.ler_membro(servidor, URL_DO_ZIP, grande)


class ServidorQueFalha(ServidorComTrechos):
    """Responde `baixar` com o erro HTTP do código dado."""

    def __init__(self, codigo: int):
        super().__init__({})
        self.codigo = codigo

    def baixar(self, url, destino: Path):
        import requests

        resposta = requests.Response()
        resposta.status_code = self.codigo
        raise requests.HTTPError(response=resposta)


def test_arquivo_que_pode_faltar_404_vira_sem_arquivo_e_outro_erro_sobe(tmp_path):
    url = "https://data.chc.ucsb.edu/chirps-v2.0.2026.10.tif.gz"
    with pytest.raises(coleta.SemArquivo, match="404"):
        obter.arquivo_que_pode_faltar(url)(ServidorQueFalha(404), tmp_path / "a.tif.gz")
    with pytest.raises(Exception, match="") as erro:
        obter.arquivo_que_pode_faltar(url)(ServidorQueFalha(500), tmp_path / "a.tif.gz")
    assert not isinstance(erro.value, coleta.SemArquivo)
    servidor = ServidorComTrechos({url: b"tif"})
    cabecalhos = obter.arquivo_que_pode_faltar(url)(servidor, tmp_path / "b.tif.gz")
    assert cabecalhos == {"ETag": '"samp"'} and servidor.baixados == [url]


PAGINA_DE_CONFIRMACAO_DO_DRIVE = (
    b"<!DOCTYPE html><html><head><title>Google Drive - Virus scan warning</title></head><body>"
    b'<form id="download-form" action="https://drive.usercontent.google.com/download" method="get">'
    b'<input type="submit" id="uc-download-link" value="Download anyway">'
    b'<input type="hidden" name="id" value="1otO"><input type="hidden" name="export" value="download">'
    b'<input type="hidden" name="confirm" value="t"><input type="hidden" name="uuid" value="ab-12">'
    b"</form></body></html>"
)


def test_arquivo_do_google_drive_segue_a_pagina_de_confirmacao(tmp_path):
    """Arquivo grande no Drive vem atrás de uma página "não foi possível verificar vírus": o obter
    lê o formulário dela e baixa do endereço certo; arquivo pequeno vem direto; HTML sem formulário
    (arquivo privado ou removido) é erro, nunca um "zip" com HTML dentro."""
    url = "https://drive.google.com/uc?id=1otO&export=download"
    confirmado = "https://drive.usercontent.google.com/download?id=1otO&export=download&confirm=t&uuid=ab-12"
    destino = tmp_path / "mapbiomas.zip"
    servidor = ServidorComTrechos(
        {url: PAGINA_DE_CONFIRMACAO_DO_DRIVE, confirmado: b"PK\x03\x04zip"}
    )
    obter.arquivo_do_google_drive(url)(servidor, destino)
    assert destino.read_bytes() == b"PK\x03\x04zip"
    assert servidor.baixados == [url, confirmado]
    direto = ServidorComTrechos({url: b"PK\x03\x04zip"})
    obter.arquivo_do_google_drive(url)(direto, destino)
    assert direto.baixados == [url] and destino.read_bytes() == b"PK\x03\x04zip"
    sem_formulario = ServidorComTrechos({url: b"<html><body>Sem acesso</body></html>"})
    with pytest.raises(ValueError, match="formul"):
        obter.arquivo_do_google_drive(url)(sem_formulario, destino)


# a ficha como a rota `/dados/api/publico/conjuntos-dados/` responde desde 2026 (campos em português;
# a antiga, do CKAN, trazia `license_id` e `license_title`)
FICHA_DO_CNPJ = {
    "id": "d0e6983f-c44e-4317-9f0b-820ae8a09ae8",
    "nome": "cadastro-nacional-da-pessoa-juridica---cnpj",
    "titulo": "Cadastro Nacional da Pessoa Jurídica - CNPJ",
    "licenca": "cc-by",
    "dataUltimaAtualizacaoArquivo": "23/10/2026 10:00:00",  # muda todo mês: fora da vigia
    "emailResponsavel": "contato@exemplo.gov.br",  # dado de pessoa: não pode ser guardado
}


class PortalComChave:
    """Responde a ficha só com a chave certa no cabeçalho (sem ela, o portal real dá 401)."""

    def __init__(self, ficha: object):
        self.ficha = ficha
        self.cabecalhos_recebidos: dict = {}

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.cabecalhos_recebidos = dict(cabecalhos or {})
        return Resposta(url, json.dumps(self.ficha).encode(), {})


def test_vigia_da_licenca_do_cnpj_guarda_so_a_licenca_e_manda_a_chave(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CHAVE_DE_TESTE", "segredo-de-teste")
    portal = PortalComChave(FICHA_DO_CNPJ)
    destino = tmp_path / "ficha.json"
    obter.licenca_da_ficha_do_dados_gov_br("https://x/ficha", "CHAVE_DE_TESTE")(
        portal, destino
    )
    assert portal.cabecalhos_recebidos["chave-api-dados-abertos"] == "segredo-de-teste"
    guardado = json.loads(destino.read_text(encoding="utf-8"))
    assert guardado == {
        "id": FICHA_DO_CNPJ["id"],
        "nome": FICHA_DO_CNPJ["nome"],
        "titulo": FICHA_DO_CNPJ["titulo"],
        "licenca": "cc-by",
    }
    assert "segredo-de-teste" not in destino.read_text(encoding="utf-8")


def test_vigia_da_licenca_do_cnpj_sem_chave_falha_sem_gravar(tmp_path, monkeypatch):
    monkeypatch.delenv("CHAVE_DE_TESTE", raising=False)
    destino = tmp_path / "ficha.json"
    with pytest.raises(obter.SemChaveDoPortal):
        obter.licenca_da_ficha_do_dados_gov_br("https://x/ficha", "CHAVE_DE_TESTE")(
            PortalComChave(FICHA_DO_CNPJ), destino
        )
    assert not destino.exists()


@pytest.mark.parametrize(
    "ficha", [{}, {"licenca": ""}, {"license_id": "cc-by"}, ["lista"], "texto"]
)
def test_vigia_da_licenca_do_cnpj_falha_se_a_ficha_nao_traz_a_licenca(
    tmp_path, monkeypatch, ficha
):
    monkeypatch.setenv("CHAVE_DE_TESTE", "segredo-de-teste")
    destino = tmp_path / "ficha.json"
    with pytest.raises(ValueError):
        obter.licenca_da_ficha_do_dados_gov_br("https://x/ficha", "CHAVE_DE_TESTE")(
            PortalComChave(ficha), destino
        )
    assert not destino.exists()


def test_vigia_do_cnpj_avisa_quando_a_licenca_muda(tmp_path, monkeypatch):
    """Ponta a ponta: a coleta da fonte registra a licença e, na rodada seguinte, avisa a troca."""
    monkeypatch.setenv(fontes.VARIAVEL_DA_CHAVE_DO_DADOS_GOV_BR, "segredo-de-teste")
    fonte = next(f for f in fontes.FONTES if f.id == "termos-cnpj-licenca")
    assert fonte.vigia and fonte.tipo == "json"
    [alvo] = fonte.descobrir(PortalComChave(FICHA_DO_CNPJ), AGORA)
    assert alvo.obter is not None
    destino = tmp_path / "a.json"
    alvo.obter(PortalComChave(FICHA_DO_CNPJ), destino)
    antes = coleta.texto_visivel(destino.read_bytes())
    mudou = dict(FICHA_DO_CNPJ, licenca="cc-by-nd")
    alvo.obter(PortalComChave(mudou), destino)
    assert coleta.texto_visivel(destino.read_bytes()) != antes
    # só as datas mudam: o texto vigiado é o mesmo
    mexida = dict(FICHA_DO_CNPJ, dataUltimaAtualizacaoArquivo="24/11/2026 10:00:00")
    alvo.obter(PortalComChave(mexida), destino)
    assert coleta.texto_visivel(destino.read_bytes()) == antes


def test_vigia_do_cnpj_usa_a_rota_da_ficha_que_aceita_a_chave():
    """Regressão (24/10/2026): sem o `/dados` no começo, a rota responde 401 mesmo com a chave."""
    assert fontes.FICHA_DO_CNPJ_NO_DADOS_GOV_BR.startswith(
        "https://dados.gov.br/dados/api/publico/conjuntos-dados/"
    )
