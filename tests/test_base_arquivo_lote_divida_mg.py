"""Coleta da dívida ativa de Minas Gerais (SEF-MG, linha 755 da fila; motor de risco cedente/sacado).

A SEF-MG publica duas planilhas `.xlsb` de pessoa jurídica (as certidões de dívida ativa e os
parcelamentos) em endereço fixo. Aqui se confere o que a coleta baixa e o que sai **antes** de guardar:
só linha de CNPJ com dígito certo, sem o nome do devedor (firma individual leva o nome da pessoa) e sem
linha com CPF no nome (ADR 0075 e 0088). Os arquivos são `.xlsx` de mentira: o leitor reconhece o
formato pelo conteúdo, então a conta é a mesma.
"""

import csv
import io
from datetime import UTC, date, datetime
from pathlib import Path

import openpyxl
import pytest

from base.arquivo import lote_divida_estadual as lote
from base.arquivo import registro
from base.arquivo.coleta import Resposta
from base.arquivo.fontes import FONTES, POR_ID
from base.licenca import familia_do_endereco
from src.banco.coletas import Marca, licenca_da_fonte, marca_da_fonte

AGORA = datetime(2026, 11, 6, 22, tzinfo=UTC)
CDAS = f"{lote.PASTA_DE_MG}/{lote.ARQUIVO_DAS_CDAS_DE_MG}"
PARCELAMENTOS = f"{lote.PASTA_DE_MG}/{lote.ARQUIVO_DOS_PARCELAMENTOS_DE_MG}"
CABECALHO_DAS_CDAS = [
    "CNPJ",
    "Nº CDA",
    "Devedor Principal",
    "Data Inscrição",
    "Espécie",
    "Saldo CDA R$",
    "Saldo Núcleo R$",
]
CABECALHO_DOS_PARCELAMENTOS = [
    "Identificação",
    "N° Parcelamento",
    "Devedor Principal",
    "Espécie",
    "Data Parcelamento",
    "Qtde Parcelas",
    "Débito R$",
]
EMPRESA = "11.222333/0001-81"  # a máscara de MG: DD.DDDDDD/DDDD-DD
OUTRA = "33.000167/0001-01"
COM_ZERO = "00.123456/0001-49"  # a planilha escreve o zero à esquerda
INSCRICAO_ESTADUAL = " 0.015381/1600-46"  # 13 dígitos com espaço na frente: não é CNPJ


class Servidor:
    """Dublê do `Cliente`: a planilha fixa."""

    def __init__(self, conteudo: bytes):
        self.conteudo = conteudo
        self.pedidos: list[str] = []

    def ler(self, url, **_):
        self.pedidos.append(url)
        return Resposta(url, self.conteudo, {})

    def baixar(self, url, destino: Path):
        self.pedidos.append(url)
        destino.write_bytes(self.conteudo)
        return {"ETag": "x"}


def _planilha(cabecalho: list[str], linhas: list[list[object]]) -> bytes:
    livro = openpyxl.Workbook()
    aba = livro.active
    assert aba is not None
    aba.append(cabecalho)
    for linha in linhas:
        aba.append(linha)
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def _cda(
    cnpj: str,
    numero: object = 1001,
    nome: str = "EMPRESA SA",
    saldo: float = 1500.5,
) -> list[object]:
    return [cnpj, numero, nome, date(2020, 3, 4), "ICMS", saldo, 900.25]


def _filtrar(
    linhas: list[list[object]], cabecalho=None, colunas=None
) -> list[list[str]]:
    livro = _planilha(cabecalho or CABECALHO_DAS_CDAS, linhas)
    saida = io.BytesIO()
    entrada = io.BytesIO(livro)
    lote.filtrar_planilha_de_mg(
        lote._linhas_da_planilha(entrada),
        colunas or lote.COLUNAS_DAS_CDAS_DE_MG,
        saida,
    )
    texto = saida.getvalue().decode("utf-8")
    return list(csv.reader(io.StringIO(texto), delimiter=lote.SEPARADOR_GUARDADO))


def test_o_endereco_e_as_planilhas_sao_os_lidos_em_06_11():
    assert lote.PORTAL_DE_MG == "https://www.fazenda.mg.gov.br"
    assert lote.ARQUIVO_DAS_CDAS_DE_MG.endswith("_PTA_PJ.xlsb")
    assert lote.ARQUIVO_DOS_PARCELAMENTOS_DE_MG.endswith("_PARCELAMENTO_PJ.xlsb")
    assert lote.COLUNA_DE_PESSOA_DE_MG not in lote.COLUNAS_DAS_CDAS_DE_MG
    assert lote.COLUNA_DE_PESSOA_DE_MG not in lote.COLUNAS_DOS_PARCELAMENTOS_DE_MG


def test_descobre_as_duas_planilhas_de_pj_sem_ler_nada():
    servidor = Servidor(b"")
    alvos = lote.descobrir_o_mg(servidor, AGORA)
    assert [a.url for a in alvos] == [CDAS, PARCELAMENTOS]
    assert all(a.extensao == ".csv" and a.obter is not None for a in alvos)
    assert servidor.pedidos == []


@pytest.mark.parametrize(
    ("titulo", "chave"),
    [
        ("Nº CDA", "NCDA"),
        ("N° Parcelamento", "NPARCELAMENTO"),
        ("Data Inscrição", "DATAINSCRICAO"),
        ("Saldo Núcleo R$", "SALDONUCLEOR"),
        ("Débito R$", "DEBITOR"),
    ],
)
def test_o_titulo_da_coluna_vira_chave_sem_acento_nem_simbolo(titulo, chave):
    assert lote._chave_da_coluna(titulo) == chave


def test_a_mascara_do_cnpj_de_mg_vira_cnpj_formatado():
    assert lote._cnpj_da_mascara(EMPRESA) == "11.222.333/0001-81"
    assert lote._cnpj_da_mascara(COM_ZERO) == "00.123.456/0001-49"
    assert (
        lote._cnpj_da_mascara(EMPRESA + "  ") == "11.222.333/0001-81"
    )  # espaço no fim
    for ruim in (
        "11.222333/0001-82",  # dígito errado
        "11.222.333/0001-81",  # sem a máscara
        "11.222333/0001-81 - EMPRESA 888.000.000-46",  # texto junto
        "",
        None,
        "888.000.000-46",  # CPF
        INSCRICAO_ESTADUAL,  # espaço na frente: 13 dígitos, nunca um CNPJ com o zero apagado
        "  . 12345/0001-81",  # CPF na planilha de parcelamentos: "000"+CPF não pode virar CNPJ
    ):
        assert lote._cnpj_da_mascara(ruim) is None


def test_espaco_na_frente_nunca_vira_zero_mesmo_que_o_digito_do_cnpj_passe():
    """Regressão da revisão cruzada: a inscrição estadual (13 dígitos) ou um CPF levava um "0" na frente e,
    em 1 caso em 100, passava no dígito do CNPJ e entrava como CNPJ de outra empresa."""
    for dv in range(100):
        digitos = f"0015381160{dv:04d}"[:13]
        mascarado = f" {digitos[0]}.{digitos[1:7]}/{digitos[7:11]}-{digitos[11:13]}"
        assert lote._cnpj_da_mascara(mascarado) is None


def test_filtro_guarda_so_cnpj_sem_nome_e_sem_cpf_no_nome():
    linhas = _filtrar(
        [
            _cda(EMPRESA, 1, "CALCADOS BIRU LTDA"),
            _cda(COM_ZERO, 2, "FORTQUIM LTDA", 99.0),
            _cda("11.222333/0001-82", 3, "DIGITO ERRADO"),
            _cda("888.000.000-46", 4, "PESSOA INVENTADA LICITACAO"),
            _cda(OUTRA, 5, "JOAO ADOEZIO 888.000.000-46"),  # CPF no nome
            _cda("", 6, "SEM DOCUMENTO"),
        ]
    )
    assert linhas[0] == list(lote.COLUNAS_DAS_CDAS_DE_MG.values())
    assert [l[0] for l in linhas[1:]] == ["11.222.333/0001-81", "00.123.456/0001-49"]
    guardado = "\n".join(";".join(l) for l in linhas)
    for nome_ou_cpf in ("BIRU", "FORTQUIM", "JOAO", "888.000.000-46", "Devedor"):
        assert nome_ou_cpf not in guardado


def test_cpf_no_nome_sem_pontuacao_tambem_tira_a_linha():
    linhas = _filtrar(
        [
            _cda(EMPRESA, 1, "JOAO 88800000046"),
            _cda(EMPRESA, 2, "MARIA 888000000-46"),
            _cda(EMPRESA, 3, "FIRMA 888.000.000-46 ME"),
            _cda(OUTRA, 4, "EMPRESA 2000 LTDA"),  # número que não é CPF
        ]
    )
    assert [l[1] for l in linhas[1:]] == ["4"]


def test_filtro_nao_guarda_inscricao_estadual_como_cnpj():
    linhas = _filtrar([_cda(INSCRICAO_ESTADUAL, 1), _cda(EMPRESA, 2)])
    assert [l[1] for l in linhas[1:]] == ["2"]


def test_filtro_grava_data_em_iso_e_numero_sem_zero_inutil():
    (_, linha) = _filtrar([_cda(EMPRESA, 1001.0, saldo=1500.5)])
    assert linha == [
        "11.222.333/0001-81",
        "1001",
        "2020-03-04",
        "ICMS",
        "1500.5",
        "900.25",
    ]


def test_filtro_le_a_planilha_dos_parcelamentos():
    linhas = _filtrar(
        [[EMPRESA, 77, "EMPRESA SA", "ICMS", date(2022, 1, 31), 60, 12345.67]],
        CABECALHO_DOS_PARCELAMENTOS,
        lote.COLUNAS_DOS_PARCELAMENTOS_DE_MG,
    )
    assert linhas[0] == list(lote.COLUNAS_DOS_PARCELAMENTOS_DE_MG.values())
    assert linhas[1] == [
        "11.222.333/0001-81",
        "77",
        "ICMS",
        "2022-01-31",
        "60",
        "12345.67",
    ]


def test_filtro_descarta_linha_com_numero_de_colunas_diferente():
    livro = _planilha(CABECALHO_DAS_CDAS, [_cda(EMPRESA)])
    # a biblioteca devolve linhas do tamanho da aba; aqui a conferência é do código: linha curta sai
    saida = io.BytesIO()
    linhas = iter([CABECALHO_DAS_CDAS, [EMPRESA, 1], _cda(OUTRA)])
    lote.filtrar_planilha_de_mg(linhas, lote.COLUNAS_DAS_CDAS_DE_MG, saida)
    assert livro  # a planilha de mentira é válida
    assert len(saida.getvalue().decode("utf-8").strip().splitlines()) == 2


@pytest.mark.parametrize("faltando", ["CNPJ", "Devedor Principal", "Saldo CDA R$"])
def test_filtro_recusa_cabecalho_sem_coluna_esperada(faltando):
    cabecalho = [c if c != faltando else "Outra" for c in CABECALHO_DAS_CDAS]
    with pytest.raises(ValueError, match="coluna"):
        _filtrar([_cda(EMPRESA)], cabecalho)


def test_filtro_recusa_coluna_repetida_e_planilha_vazia():
    repetido = [*CABECALHO_DAS_CDAS, "CNPJ"]
    with pytest.raises(ValueError, match="2 vezes"):
        lote.filtrar_planilha_de_mg(
            iter([repetido]), lote.COLUNAS_DAS_CDAS_DE_MG, io.BytesIO()
        )
    with pytest.raises(ValueError, match="vazia"):
        lote.filtrar_planilha_de_mg(iter([]), lote.COLUNAS_DAS_CDAS_DE_MG, io.BytesIO())


def test_recusa_arquivo_com_mais_de_uma_aba():
    livro = openpyxl.Workbook()
    livro.create_sheet("outra")
    saida = io.BytesIO()
    livro.save(saida)
    with pytest.raises(ValueError, match="2 abas"):
        lote._linhas_da_planilha(io.BytesIO(saida.getvalue()))


def test_obter_grava_o_csv_filtrado_e_nao_deixa_o_original(tmp_path):
    planilha = _planilha(CABECALHO_DAS_CDAS, [_cda(EMPRESA, 1, "CALCADOS BIRU LTDA")])
    servidor = Servidor(planilha)
    destino = tmp_path / "saida.csv"
    alvo = lote.alvo_da_planilha_de_mg(CDAS, lote.COLUNAS_DAS_CDAS_DE_MG)
    assert alvo.obter is not None
    alvo.obter(servidor, destino)
    assert "BIRU" not in destino.read_text(encoding="utf-8")
    assert [p.name for p in tmp_path.iterdir()] == ["saida.csv"]


def test_obter_nao_deixa_arquivo_quando_a_planilha_muda_de_forma(tmp_path):
    ruim = _planilha(["A", "B"], [[1, 2]])
    for conteudo in (ruim, b"isto nao e uma planilha"):
        servidor = Servidor(conteudo)
        alvo = lote.alvo_da_planilha_de_mg(CDAS, lote.COLUNAS_DAS_CDAS_DE_MG)
        with pytest.raises(Exception):  # noqa: B017 (a biblioteca levanta o seu próprio erro)
            alvo.obter(servidor, tmp_path / "saida.csv")  # type: ignore[misc]
        assert list(tmp_path.iterdir()) == []


def test_obter_apaga_o_original_que_sobrou_de_uma_rodada_morta(tmp_path):
    destino = tmp_path / "saida.csv"
    (tmp_path / "saida.csv.bruto").write_bytes(b"nome de devedor de rodada anterior")
    servidor = Servidor(_planilha(CABECALHO_DAS_CDAS, [_cda(EMPRESA)]))
    lote.alvo_da_planilha_de_mg(CDAS, lote.COLUNAS_DAS_CDAS_DE_MG).obter(  # type: ignore[misc]
        servidor, destino
    )
    assert [p.name for p in tmp_path.iterdir()] == ["saida.csv"]


def test_a_fonte_esta_no_registro_semanal():
    fonte = POR_ID["sefmg-divida-ativa"]
    assert fonte in FONTES and fonte.grupo == "semanal"
    assert fonte in lote.fontes()


def test_a_licenca_e_a_confirmar_vendavel_por_risco_assumido_e_o_portal_foi_lido():
    fonte = "sefmg-divida-ativa"
    assert "a confirmar" in licenca_da_fonte(fonte)
    assert len(licenca_da_fonte(fonte)) <= 80
    assert marca_da_fonte(fonte) == Marca.VENDAVEL
    assert registro.TERMOS_LIDOS_EM["sefmg"] == date(2026, 11, 6)
    assert familia_do_endereco(CDAS) == "sefmg"
    assert familia_do_endereco(PARCELAMENTOS) == "sefmg"
