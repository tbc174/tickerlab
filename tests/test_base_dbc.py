"""Leitor de DBC do DATASUS (base/dbc.py) e a tabela do CNES a partir dele (base/cnes.py).

Nada vai à internet. O vetor do blast (`AIAIAIAIAIAIA`) vem do código original de Mark Adler e exercita
literais, comprimento, distância e o marcador de fim. Os DBCs de teste são montados aqui com um
compressor mínimo (só literais), que o leitor de verdade descomprime como qualquer outro fluxo PKWare.
"""

import struct
from datetime import date

import pytest

from base import cnes, dbc

VETOR_DO_BLAST = bytes.fromhex("00048224258f807f")


def _bits_do_codigo(codigo: dbc._Codigo, simbolo: int) -> list[int]:
    """Os bits (já invertidos, como vão no fluxo) do símbolo no código canônico do blast."""
    primeiro = 0
    for comprimento in range(1, dbc._MAXIMO_DE_BITS + 1):
        quantidade = codigo.quantidade[comprimento]
        if codigo.comprimentos[simbolo] == comprimento:
            posicao = [
                s for s in codigo.simbolos if codigo.comprimentos[s] == comprimento
            ]
            valor = primeiro + posicao.index(simbolo)
            return [1 - ((valor >> i) & 1) for i in range(comprimento - 1, -1, -1)]
        primeiro = (primeiro + quantidade) << 1
    raise AssertionError("símbolo sem código")


def comprimir_so_com_literais(dados: bytes) -> bytes:
    """Fluxo PKWare válido sem nenhuma repetição: tipo de literal 0, dicionário 4, literais, fim."""
    bits: list[int] = []
    for byte in dados:
        bits += [0] + [(byte >> i) & 1 for i in range(8)]
    bits += (
        [1] + _bits_do_codigo(dbc._CODIGO_COMPRIMENTO, 15) + [1] * 8
    )  # comprimento 519 = fim
    bits += [0] * (-len(bits) % 8)
    corpo = bytes(
        sum(bits[i + j] << j for j in range(8)) for i in range(0, len(bits), 8)
    )
    return bytes([0, 4]) + corpo


def montar_dbc(campos: list[tuple[str, int]], registros: list[list[str]]) -> bytes:
    """Um DBC com os campos de texto e os registros dados (e o cabeçalho do DBF sem compressão)."""
    tamanho_do_registro = 1 + sum(tamanho for _, tamanho in campos)
    tamanho_do_cabecalho = 32 + 32 * len(campos) + 1
    cabecalho = bytearray(32)
    cabecalho[0] = 0x03
    struct.pack_into(
        "<IHH", cabecalho, 4, len(registros), tamanho_do_cabecalho, tamanho_do_registro
    )
    for nome, tamanho in campos:
        descritor = bytearray(32)
        descritor[: len(nome)] = nome.encode()
        descritor[11] = ord("C")
        descritor[16] = tamanho
        cabecalho += descritor
    cabecalho += b"\x0d"
    corpo = b"".join(
        b" "
        + b"".join(
            valor.ljust(tamanho).encode("latin-1")
            for (_, tamanho), valor in zip(campos, linha, strict=True)
        )
        for linha in registros
    )
    return bytes(cabecalho) + b"\x00" * 4 + comprimir_so_com_literais(corpo)


CAMPOS = [
    ("CNES", 7), ("CODUFMUN", 6), ("PF_PJ", 1), ("CPF_CNPJ", 14), ("CNPJ_MAN", 14),
    ("TPGESTAO", 1), ("TP_UNID", 2), ("NAT_JUR", 4),
]  # fmt: skip
HOSPITAL = "11222333000181"
PREFEITURA = "11444777000161"


def _registro(
    cnes_: str, cnpj: str = "", mantenedora: str = "", pf_pj: str = "3"
) -> list[str]:
    return [cnes_, "330330", pf_pj, cnpj, mantenedora, "M", "05", "1023"]


class TestDescompressao:
    def test_vetor_do_blast(self):
        assert dbc.descomprimir_pkware(VETOR_DO_BLAST) == b"AIAIAIAIAIAIA"

    def test_literais_voltam_iguais(self):
        dados = bytes(range(256)) * 3
        assert dbc.descomprimir_pkware(comprimir_so_com_literais(dados)) == dados

    def test_fluxo_cortado_e_erro(self):
        with pytest.raises(dbc.DbcInvalido):
            dbc.descomprimir_pkware(VETOR_DO_BLAST[:-2])

    def test_dicionario_invalido_e_erro(self):
        with pytest.raises(dbc.DbcInvalido):
            dbc.descomprimir_pkware(bytes([0, 9, 0, 0]))

    def test_tabelas_de_huffman_sao_completas(self):
        for codigo in (
            dbc._CODIGO_LITERAL,
            dbc._CODIGO_COMPRIMENTO,
            dbc._CODIGO_DISTANCIA,
        ):
            assert sum(2.0**-c for c in codigo.comprimentos if c) == 1.0


class TestLeituraDoDbc:
    def test_le_so_as_colunas_pedidas(self):
        conteudo = montar_dbc(
            CAMPOS, [_registro("1234567", HOSPITAL), _registro("7654321")]
        )
        linhas = list(dbc.ler_dbc(conteudo, ("CNES", "CPF_CNPJ")))
        assert linhas == [
            {"CNES": "1234567", "CPF_CNPJ": HOSPITAL},
            {"CNES": "7654321", "CPF_CNPJ": ""},
        ]

    def test_coluna_ausente_e_erro(self):
        conteudo = montar_dbc(CAMPOS, [_registro("1234567")])
        with pytest.raises(dbc.DbcInvalido, match="ausentes"):
            list(dbc.ler_dbc(conteudo, ("NAO_EXISTE",)))

    def test_menos_registros_que_o_prometido_e_erro(self):
        conteudo = bytearray(montar_dbc(CAMPOS, [_registro("1234567")]))
        struct.pack_into("<I", conteudo, 4, 5)
        with pytest.raises(dbc.DbcInvalido, match="menos registros"):
            list(dbc.ler_dbc(bytes(conteudo), ("CNES",)))

    def test_nomes_das_colunas_sem_descomprimir(self):
        conteudo = montar_dbc(CAMPOS, [_registro("1234567")])
        assert dbc.nomes_das_colunas(conteudo) == [nome for nome, _ in CAMPOS]

    def test_arquivo_pequeno_e_erro(self):
        with pytest.raises(dbc.DbcInvalido):
            dbc.nomes_das_colunas(b"x")


class TestCnesPeloDbc:
    def test_disponibilidade_e_o_dia_15_do_mes_seguinte(self):
        assert cnes.disponivel_em_da_competencia(202608) == date(2026, 9, 15)
        assert cnes.disponivel_em_da_competencia(202612) == date(2027, 1, 15)

    def test_caminho_no_ftp(self):
        assert cnes.caminho_no_ftp("RJ", 202608) == (
            "/dissemin/publicos/CNES/200508_/Dados/ST/STRJ2608.dbc"
        )
        with pytest.raises(ValueError):
            cnes.caminho_no_ftp("XX", 202608)

    def test_tabela_tem_as_colunas_da_carga(self):
        conteudo = montar_dbc(CAMPOS, [_registro("1234567", HOSPITAL, PREFEITURA)])
        tabela = cnes.tabela_do_dbc(conteudo, 202608)
        assert list(tabela.columns) == list(cnes.COLUNAS)
        linha = tabela.iloc[0]
        assert (linha["codigo_cnes"], linha["cnpj"], linha["cnpj_mantenedora"]) == (
            "1234567", HOSPITAL, PREFEITURA,
        )  # fmt: skip
        assert linha["competencia"] == 202608
        assert linha["disponivel_em"].date() == date(2026, 9, 15)

    def test_cpf_de_pessoa_fisica_nao_entra(self):
        conteudo = montar_dbc(CAMPOS, [_registro("1234567", "88800000046", pf_pj="1")])
        tabela = cnes.tabela_do_dbc(conteudo, 202608)
        assert tabela.iloc[0]["cnpj"] == ""
        assert tabela.iloc[0]["razao_social"] == ""

    def test_coluna_cnpj_com_o_outro_nome(self):
        campos = [("CNPJ" if nome == "CPF_CNPJ" else nome, tam) for nome, tam in CAMPOS]
        conteudo = montar_dbc(campos, [_registro("1234567", HOSPITAL)])
        assert cnes.tabela_do_dbc(conteudo, 202608).iloc[0]["cnpj"] == HOSPITAL

    def test_sem_coluna_de_cnpj_e_erro(self):
        campos = [(n, t) for n, t in CAMPOS if n != "CPF_CNPJ"]
        conteudo = montar_dbc(
            campos, [["1234567", "330330", "3", "", "M", "05", "1023"]]
        )
        with pytest.raises(dbc.DbcInvalido, match="CNPJ"):
            cnes.tabela_do_dbc(conteudo, 202608)

    def test_estabelecimento_repetido_e_erro(self):
        conteudo = montar_dbc(CAMPOS, [_registro("1234567"), _registro("1234567")])
        with pytest.raises(ValueError, match="repetido"):
            cnes.tabela_do_dbc(conteudo, 202608)

    def test_baixar_usa_o_ftp_anonimo(self):
        chamadas: list[str] = []

        class FtpFalso:
            def __init__(self, servidor: str, timeout: int) -> None:
                chamadas.append(servidor)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def login(self) -> None:
                chamadas.append("login")

            def retrbinary(self, comando: str, retorno) -> None:
                chamadas.append(comando)
                retorno(b"ab")
                retorno(b"cd")

        assert cnes.baixar_dbc("AC", 202609, abrir=FtpFalso) == b"abcd"
        assert (
            chamadas[-1] == "RETR /dissemin/publicos/CNES/200508_/Dados/ST/STAC2609.dbc"
        )
        assert chamadas[:2] == ["ftp.datasus.gov.br", "login"]


class TestColetaDoPaisPeloFtp:
    """`coletar_competencia_ftp`: 27 UFs, uma tabela; nenhuma publicada = vazia; parcial = erro."""

    @staticmethod
    def _baixador(publicadas: dict[str, str]):
        def baixar(uf: str, competencia: int) -> bytes:
            if uf not in publicadas:
                raise FileNotFoundError(uf)
            return montar_dbc(CAMPOS, [_registro(publicadas[uf], HOSPITAL)])

        return baixar

    def test_junta_as_ufs_numa_tabela(self):
        todas = {uf: f"{i:07d}" for i, uf in enumerate(cnes.UFS, start=1)}
        tabela, situacao = cnes.coletar_competencia_ftp(
            202608, date(2026, 11, 5), self._baixador(todas)
        )
        assert len(tabela) == len(cnes.UFS)
        assert situacao["situacao"] == cnes.COMPETENCIA_COM_DADOS
        assert situacao["linhas"] == len(cnes.UFS)

    def test_nenhuma_uf_publicada_e_competencia_vazia(self):
        tabela, situacao = cnes.coletar_competencia_ftp(
            202609, date(2026, 11, 5), self._baixador({})
        )
        assert tabela.empty
        assert list(tabela.columns) == list(cnes.COLUNAS)
        assert situacao["situacao"] == cnes.COMPETENCIA_VAZIA

    def test_so_algumas_ufs_publicadas_e_erro(self):
        with pytest.raises(ValueError, match="ausente"):
            cnes.coletar_competencia_ftp(
                202609, date(2026, 11, 5), self._baixador({"AC": "0000001"})
            )

    def test_mesmo_cnes_em_duas_ufs_e_erro(self):
        todas = dict.fromkeys(cnes.UFS, "0000001")
        with pytest.raises(ValueError, match="repetido"):
            cnes.coletar_competencia_ftp(
                202608, date(2026, 11, 5), self._baixador(todas)
            )

    def test_arquivo_inexistente_no_ftp_vira_file_not_found(self, monkeypatch):
        def sem_arquivo(*_args, **_kwargs):
            raise cnes.ftplib.error_perm("550 No such file")

        monkeypatch.setattr(cnes, "baixar_dbc", sem_arquivo)
        with pytest.raises(FileNotFoundError):
            cnes.baixar_dbc_se_publicado("AC", 202609)

    def test_outro_erro_do_ftp_nao_vira_competencia_vazia(self, monkeypatch):
        def negado(*_args, **_kwargs):
            raise cnes.ftplib.error_perm("530 Login incorrect")

        monkeypatch.setattr(cnes, "baixar_dbc", negado)
        with pytest.raises(cnes.ftplib.error_perm):
            cnes.baixar_dbc_se_publicado("AC", 202609)

    def test_layout_real_do_stac2608_tem_as_colunas_lidas(self):
        """Nomes conferidos no STAC2608.dbc real (05/11/2026): o CNPJ do estabelecimento é `CPF_CNPJ`."""
        real = [
            "CNES", "CODUFMUN", "COD_CEP", "CPF_CNPJ", "PF_PJ", "NIV_DEP", "CNPJ_MAN", "TPGESTAO",
            "TP_UNID", "DT_ATUAL", "COMPETEN", "NAT_JUR",
        ]  # fmt: skip
        assert set(cnes.COLUNAS_DO_DBC) <= set(real)
        assert "CPF_CNPJ" in real
