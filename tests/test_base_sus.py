"""Totais do SUS por estabelecimento e mês (base/sus.py): soma na hora, supressão e pessoa física fora.

ADR 0081 (itens 3 e 4) e ADR 0088 Emenda 1: a linha do paciente só existe na memória, colunas lidas numa
lista fechada, célula com menos de 10 no mês não sai, óbito com menos de 20 não sai, estabelecimento de
pessoa física não entra. Os DBCs são fabricados aqui (nenhum dado real); nada vai à internet.
"""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from hypothesis import assume, example, given, settings
from hypothesis import strategies as st

from base import cnpj as cnpj_de_teste
from base import dbc, sus
from tests.test_base_dbc import montar_dbc

HOSPITAL = "11222333000181"
PREFEITURA = "11444777000161"
CPF = "52998224725"  # CPF de exemplo com DVs válidos (nenhuma pessoa)
# sorteado: com "000" na frente também passa no DV de CNPJ, e a "filial" não é 0001
CPF_AMBIGUO = "74055068107"
COMPETENCIA = 202607
COLETADO_EM = date(2026, 11, 5)

CAMPOS_SIH = [
    ("CNES", 7), ("CGC_HOSP", 14), ("CNPJ_MANT", 14), ("MUNIC_MOV", 6), ("IDENT", 1),
    ("VAL_TOT", 14), ("VAL_UTI", 8), ("DIAS_PERM", 5), ("MORTE", 1),
    ("NASC", 8), ("CPF_AUT", 11), ("DIAG_PRINC", 4),
]  # fmt: skip
CAMPOS_SIA = [
    ("PA_CODUNI", 7), ("PA_CNPJCPF", 14), ("PA_CNPJMNT", 14), ("PA_UFMUN", 6),
    ("PA_QTDPRO", 11), ("PA_QTDAPR", 11), ("PA_VALPRO", 20), ("PA_VALAPR", 20),
    ("PA_CNSMED", 15), ("PA_SEXO", 1), ("PA_IDADE", 3),
]  # fmt: skip


def internacao(
    cnes: str = "1234567",
    cnpj: str = HOSPITAL,
    mantenedora: str = "",
    ident: str = "1",
    valor: str = "100.00",
    uti: str = "0.00",
    dias: str = "3",
    morte: str = "0",
) -> list[str]:
    return [
        cnes,
        cnpj,
        mantenedora,
        "120040",
        ident,
        valor,
        uti,
        dias,
        morte,
        "19800101",
        CPF,
        "I10",
    ]


def procedimento(
    cnes: str = "7654321",
    documento: str = HOSPITAL,
    mantenedora: str = "",
    apresentada: str = "1",
    aprovada: str = "1",
    valor_apresentado: str = "10.00",
    valor_aprovado: str = "10.00",
) -> list[str]:
    return [
        cnes, documento, mantenedora, "355030", apresentada, aprovada, valor_apresentado,
        valor_aprovado, "123456789012345", "F", "040",
    ]  # fmt: skip


def dbc_do_sih(linhas: list[list[str]]) -> bytes:
    return montar_dbc(CAMPOS_SIH, linhas)


def dbc_do_sia(linhas: list[list[str]]) -> bytes:
    return montar_dbc(CAMPOS_SIA, linhas)


def coletar(
    sistema: sus.Sistema, arquivos: dict[str, bytes], ufs: tuple[str, ...] = ("AC",)
) -> tuple[pd.DataFrame, pd.DataFrame]:
    def listar(pasta: str) -> list[str]:
        assert pasta == sistema.pasta_no_ftp
        return [*arquivos, "LEIAME.txt"]

    def baixar(pasta: str, nome: str) -> bytes:
        assert pasta == sistema.pasta_no_ftp
        return arquivos[nome]

    return sus.coletar_competencia(
        sistema, COMPETENCIA, COLETADO_EM, listar=listar, baixar=baixar, ufs=ufs
    )


def uma_linha(tabela: pd.DataFrame, cnes: str) -> pd.Series:
    linhas = tabela[tabela["codigo_cnes"] == cnes]
    assert len(linhas) == 1
    return linhas.iloc[0]


class TestColunasFechadas:
    def test_nenhuma_coluna_proibida_na_lista(self):
        for sistema in (sus.SIH, sus.SIA):
            assert not set(sistema.colunas) & sus.COLUNAS_PROIBIDAS

    def test_proibidas_cobrem_o_que_identifica_pessoa_no_layout_real(self):
        # nomes conferidos no cabeçalho real do RDAC2607.dbc e do PAAC2608.dbc (05/11/2026)
        pessoais = {
            "NASC", "CEP", "MUNIC_RES", "SEXO", "IDADE", "COD_IDADE", "RACA_COR", "ETNIA", "INSTRU",
            "NUM_FILHOS", "CPF_AUT", "GESTOR_CPF", "N_AIH", "DIAG_PRINC", "DIAG_SECUN", "CID_MORTE",
            "CID_NOTIF", "CBOR", "PA_CNSMED", "PA_AUTORIZ", "PA_IDADE", "PA_SEXO", "PA_RACACOR",
            "PA_MUNPCN", "PA_CIDPRI", "PA_CIDSEC", "PA_CIDCAS", "PA_ETNIA", "PA_CBOCOD",
        }  # fmt: skip
        assert pessoais <= sus.COLUNAS_PROIBIDAS

    def test_le_so_as_colunas_da_lista(self, monkeypatch):
        pedidas: list[tuple[str, ...]] = []
        original = dbc.ler_dbc

        def espiao(conteudo, colunas, *args, **kwargs):
            pedidas.append(colunas)
            return original(conteudo, colunas, *args, **kwargs)

        monkeypatch.setattr(sus.dbc, "ler_dbc", espiao)
        coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih([internacao()] * 10)})
        coletar(sus.SIA, {"PAAC2607.dbc": dbc_do_sia([procedimento()] * 10)})
        assert pedidas == [sus.SIH.colunas, sus.SIA.colunas]


class TestSomaDoSih:
    def test_soma_por_estabelecimento(self):
        linhas = [internacao(valor="100.10", uti="5.05", dias="2") for _ in range(11)]
        linhas.append(
            internacao(ident="5", valor="1.00", dias="30")
        )  # longa permanência
        tabela, _ = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        linha = uma_linha(tabela, "1234567")
        assert linha["internacoes"] == 11
        assert linha["valor_total"] == Decimal("1102.10")
        assert linha["valor_uti"] == Decimal("55.55")
        assert linha["dias_permanencia"] == 52
        assert linha["cnpj"] == HOSPITAL
        assert linha["codigo_ibge_municipio"] == "120040"
        assert linha["uf"] == "AC"
        assert linha["competencia"] == COMPETENCIA
        assert not linha["suprimida"]

    def test_dinheiro_exato(self):
        linhas = [internacao(valor="0.10") for _ in range(30)]
        tabela, _ = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        assert uma_linha(tabela, "1234567")["valor_total"] == Decimal("3.00")
        assert str(tabela["valor_total"].dtype).startswith("decimal128(18, 2)")

    def test_obito_de_longa_permanencia_nao_conta(self):
        linhas = [internacao(morte="1") for _ in range(20)]
        linhas += [internacao(ident="5", morte="1")]
        tabela, _ = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        assert uma_linha(tabela, "1234567")["obitos"] == 20

    def test_cnpj_mais_frequente_do_estabelecimento(self):
        linhas = [internacao() for _ in range(8)] + [internacao(cnpj=PREFEITURA)] * 3
        tabela, _ = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        assert uma_linha(tabela, "1234567")["cnpj"] == HOSPITAL

    def test_disponivel_em_e_o_dia_da_coleta(self):
        tabela, _ = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih([internacao()] * 10)})
        assert (tabela["disponivel_em"] == pd.Timestamp(COLETADO_EM)).all()

    def test_numero_invalido_e_erro(self):
        with pytest.raises(ValueError, match="VAL_TOT"):
            coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih([internacao(valor="abc")])})


class TestSupressao:
    @pytest.mark.parametrize(("quantas", "suprimida"), [(9, True), (10, False)])
    def test_fronteira_das_internacoes(self, quantas, suprimida):
        linhas = [internacao() for _ in range(quantas)]
        tabela, _ = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        linha = uma_linha(tabela, "1234567")
        assert bool(linha["suprimida"]) is suprimida
        numeros = [
            "internacoes",
            "valor_total",
            "valor_uti",
            "dias_permanencia",
            "obitos",
        ]
        if suprimida:
            assert all(pd.isna(linha[c]) for c in numeros)
        else:
            assert linha["internacoes"] == quantas

    @pytest.mark.parametrize(("obitos", "publicado"), [(19, None), (20, 20)])
    def test_fronteira_dos_obitos(self, obitos, publicado):
        linhas = [internacao(morte="1") for _ in range(obitos)]
        linhas += [internacao() for _ in range(30)]
        tabela, _ = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        linha = uma_linha(tabela, "1234567")
        assert not linha["suprimida"]
        if publicado is None:
            assert pd.isna(linha["obitos"]) and linha["obitos_suprimidos"]
        else:
            assert linha["obitos"] == publicado and not linha["obitos_suprimidos"]

    @pytest.mark.parametrize(("aprovada", "suprimida"), [(9, True), (10, False)])
    def test_fronteira_do_ambulatorio(self, aprovada, suprimida):
        linhas = [procedimento(apresentada="1", aprovada="1") for _ in range(aprovada)]
        tabela, _ = coletar(sus.SIA, {"PAAC2607.dbc": dbc_do_sia(linhas)})
        linha = uma_linha(tabela, "7654321")
        assert bool(linha["suprimida"]) is suprimida
        if suprimida:
            assert pd.isna(linha["quantidade_aprovada"]) and pd.isna(
                linha["valor_aprovado"]
            )

    def test_apresentada_pequena_tambem_suprime(self):
        linhas = [procedimento(apresentada="0", aprovada="2") for _ in range(10)]
        tabela, _ = coletar(sus.SIA, {"PAAC2607.dbc": dbc_do_sia(linhas)})
        assert uma_linha(tabela, "7654321")["suprimida"]

    def test_partes_do_sia_somam_antes_de_suprimir(self):
        arquivos = {
            "PAAC2607a.dbc": dbc_do_sia([procedimento() for _ in range(6)]),
            "PAAC2607b.dbc": dbc_do_sia([procedimento() for _ in range(6)]),
        }
        tabela, situacao = coletar(sus.SIA, arquivos)
        linha = uma_linha(tabela, "7654321")
        assert not linha["suprimida"] and linha["quantidade_aprovada"] == 12
        assert situacao.iloc[0]["arquivos"] == "PAAC2607a.dbc,PAAC2607b.dbc"

    @settings(max_examples=50, deadline=None)
    @given(
        st.lists(
            st.tuples(
                st.sampled_from(["1111111", "2222222", "3333333"]), st.booleans()
            ),
            max_size=80,
        )
    )
    def test_propriedade_nenhuma_celula_pequena_sai(self, internacoes):
        linhas = [internacao(cnes=c, morte="1" if m else "0") for c, m in internacoes]
        arquivos = {"RDAC2607.dbc": dbc_do_sih(linhas)} if linhas else {}
        tabela, _ = coletar(sus.SIH, arquivos)
        publicadas = tabela["internacoes"].dropna()
        assert (publicadas >= sus.MINIMO_PARA_PUBLICAR).all()
        assert (tabela["obitos"].dropna() >= sus.MINIMO_PARA_OBITOS).all()
        assert tabela.loc[tabela["suprimida"], "valor_total"].isna().all()


class TestPessoaFisicaFora:
    @pytest.mark.parametrize("documento", [CPF, CPF.zfill(14)])
    def test_cpf_no_documento_proprio_tira_o_estabelecimento(self, documento):
        linhas = [internacao(cnpj=documento, mantenedora=PREFEITURA) for _ in range(15)]
        tabela, situacao = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        assert tabela.empty
        assert situacao.iloc[0]["fora_pessoa_fisica"] == 1

    def test_sem_cnpj_nenhum_fica_fora(self):
        linhas = [internacao(cnpj="", mantenedora="") for _ in range(15)]
        tabela, situacao = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        assert tabela.empty
        assert situacao.iloc[0]["fora_sem_cnpj"] == 1

    def test_um_registro_de_cpf_basta(self):
        linhas = [internacao() for _ in range(14)] + [internacao(cnpj=CPF)]
        tabela, _ = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        assert tabela.empty

    def test_so_a_mantenedora_basta(self):
        linhas = [internacao(cnpj="", mantenedora=PREFEITURA) for _ in range(10)]
        tabela, _ = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        linha = uma_linha(tabela, "1234567")
        assert linha["cnpj"] == "" and linha["cnpj_mantenedora"] == PREFEITURA

    def test_cpf_no_sia(self):
        linhas = [procedimento(documento=CPF) for _ in range(15)]
        tabela, situacao = coletar(sus.SIA, {"PAAC2607.dbc": dbc_do_sia(linhas)})
        assert tabela.empty and situacao.iloc[0]["fora_pessoa_fisica"] == 1

    def test_cnpj_que_parece_cpf_com_zeros_continua_cnpj(self):
        """Raiz com zeros à esquerda e DV de CNPJ que confere: é empresa."""
        cnpj = "00000000000191"  # Banco do Brasil
        linhas = [internacao(cnpj=cnpj) for _ in range(10)]
        tabela, _ = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        assert uma_linha(tabela, "1234567")["cnpj"] == cnpj

    @pytest.mark.parametrize(
        "documento", ["52998224799", "00052998224799", "11222333000199"]
    )
    def test_documento_com_dv_errado_nunca_e_publicado(self, documento):
        """CPF digitado com o DV errado não passa por pessoa física, mas também não vira `cnpj`."""
        linhas = [internacao(cnpj=documento, mantenedora=PREFEITURA) for _ in range(10)]
        tabela, _ = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        linha = uma_linha(tabela, "1234567")
        assert linha["cnpj"] == "" and linha["cnpj_mantenedora"] == PREFEITURA

    def test_mantenedora_com_dv_errado_tambem_nao(self):
        linhas = [internacao(cnpj="", mantenedora="00052998224799") for _ in range(10)]
        tabela, situacao = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        assert tabela.empty and situacao.iloc[0]["fora_sem_cnpj"] == 1

    def test_cpf_com_zeros_que_tambem_passa_como_cnpj_e_pessoa(self):
        """1,4% dos CPFs com "000" na frente também têm o DV de CNPJ: fora da matriz, vale o CPF."""
        documento = "000" + CPF_AMBIGUO
        linhas = [internacao(cnpj=documento, mantenedora=PREFEITURA) for _ in range(15)]
        tabela, situacao = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        assert tabela.empty and situacao.iloc[0]["fora_pessoa_fisica"] == 1

    def test_mantenedora_que_parece_cpf_fica_vazia(self):
        linhas = [internacao(mantenedora="000" + CPF_AMBIGUO) for _ in range(10)]
        tabela, _ = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        linha = uma_linha(tabela, "1234567")
        assert linha["cnpj"] == HOSPITAL and linha["cnpj_mantenedora"] == ""

    @settings(max_examples=60, deadline=None)
    @given(st.integers(min_value=10**8, max_value=10**9 - 1), st.booleans())
    @example(
        int(CPF_AMBIGUO[:9]), True
    )  # o caso raro (1,4%) que o sorteio quase nunca acha
    def test_propriedade_nenhum_cpf_sai_nas_colunas_de_cnpj(self, base, com_zeros):
        """Para qualquer CPF válido, puro ou com "000", os 11 dígitos não aparecem em `cnpj` nem em
        `cnpj_mantenedora`; a única exceção é a matriz (filial 0001) que também é CNPJ válido."""
        validos = [
            f"{base}{dv:02d}"
            for dv in range(100)
            if cnpj_de_teste.cpf_confere(f"{base}{dv:02d}")
        ]
        assume(validos)  # 111111111 e afins não têm CPF válido
        cpf = validos[0]
        documento = "000" + cpf if com_zeros else cpf
        linhas = [internacao(cnpj=HOSPITAL, mantenedora=documento) for _ in range(10)]
        linhas += [
            internacao(cnes="7654321", cnpj=documento, mantenedora=PREFEITURA)
            for _ in range(10)
        ]
        tabela, _ = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        matriz = ("000" + cpf)[8:12] == "0001"
        publicados = set(tabela["cnpj"]) | set(tabela["cnpj_mantenedora"])
        if not matriz:
            assert not any(valor.endswith(cpf) for valor in publicados)

    def test_registro_sem_cnes_nao_vira_estabelecimento(self):
        """Sem o código, não há como saber de qual hospital é: não se soma num "estabelecimento" vazio."""
        linhas = [internacao(cnes="") for _ in range(12)] + [
            internacao() for _ in range(10)
        ]
        tabela, situacao = coletar(sus.SIH, {"RDAC2607.dbc": dbc_do_sih(linhas)})
        assert list(tabela["codigo_cnes"]) == ["1234567"]
        assert uma_linha(tabela, "1234567")["internacoes"] == 10
        assert situacao.iloc[0]["fora_sem_cnes"] == 12


class TestArquivosDaCompetencia:
    def test_nomes_do_sih(self):
        nomes = ["RDAC2607.dbc", "RDAC2606.dbc", "RDAP2607.dbc", "rdac2607.DBC"]
        assert sus.nomes_dos_arquivos(sus.SIH, "AC", COMPETENCIA, nomes) == [
            "RDAC2607.dbc",
            "rdac2607.DBC",
        ]

    def test_nomes_do_sia_com_partes(self):
        nomes = [
            "PASP2607a.dbc",
            "PASP2607b.dbc",
            "PASP2607.dbc",
            "PASP2608a.dbc",
            "PASPX2607.dbc",
        ]
        assert sus.nomes_dos_arquivos(sus.SIA, "SP", COMPETENCIA, nomes) == [
            "PASP2607.dbc",
            "PASP2607a.dbc",
            "PASP2607b.dbc",
        ]

    def test_nome_com_quebra_de_linha_nao_passa(self):
        """O `$` do `re` aceita uma quebra de linha no fim; o nome vai para o comando RETR do FTP."""
        nomes = ["RDAC2607.dbc\n", "RDAC2607.dbc\r\nDELE x"]
        assert sus.nomes_dos_arquivos(sus.SIH, "AC", COMPETENCIA, nomes) == []

    def test_sih_nao_aceita_partes(self):
        assert (
            sus.nomes_dos_arquivos(sus.SIH, "SP", COMPETENCIA, ["RDSP2607a.dbc"]) == []
        )

    def test_competencia_sem_arquivo_e_vazia(self):
        tabela, situacao = coletar(sus.SIH, {}, ufs=("AC", "AP"))
        assert tabela.empty
        assert list(situacao["situacao"]) == [sus.COMPETENCIA_VAZIA] * 2
        assert list(tabela.columns) == list(sus.SIH.colunas_da_tabela)

    def test_so_algumas_ufs_publicadas_e_erro(self):
        with pytest.raises(ValueError, match="AP"):
            coletar(
                sus.SIH, {"RDAC2607.dbc": dbc_do_sih([internacao()])}, ufs=("AC", "AP")
            )

    def test_situacao_guarda_o_hash_e_as_contagens(self):
        conteudo = dbc_do_sih([internacao()] * 10 + [internacao(cnes="9999999")] * 3)
        _, situacao = coletar(sus.SIH, {"RDAC2607.dbc": conteudo})
        linha = situacao.iloc[0]
        import hashlib

        assert linha["sha256"] == hashlib.sha256(conteudo).hexdigest()
        assert linha["registros"] == 13
        assert linha["estabelecimentos"] == 2
        assert linha["suprimidos"] == 1
        assert linha["situacao"] == sus.COMPETENCIA_COM_DADOS
        assert linha["sistema"] == "sih"

    def test_mesmo_cnes_em_duas_ufs_soma(self):
        arquivos = {
            "RDAC2607.dbc": dbc_do_sih([internacao()] * 5),
            "RDAP2607.dbc": dbc_do_sih([internacao()] * 5),
        }
        tabela, _ = coletar(sus.SIH, arquivos, ufs=("AC", "AP"))
        assert uma_linha(tabela, "1234567")["internacoes"] == 10


class TestFtp:
    class _FtpFalso:
        def __init__(self, servidor: str, timeout: int) -> None:
            assert servidor == "ftp.datasus.gov.br"
            self.comandos: list[str] = []

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def login(self) -> None:
            self.comandos.append("login")

        def cwd(self, pasta: str) -> None:
            self.comandos.append(f"cwd {pasta}")

        def nlst(self) -> list[str]:
            return ["RDAC2607.dbc"]

        def retrbinary(self, comando: str, retorno) -> None:
            assert (
                "/" not in comando
            )  # o FTP do DATASUS recusa RETR com caminho completo
            retorno(b"abc")
            retorno(b"def")

    def test_baixar_entra_na_pasta_e_junta_os_pedacos(self):
        assert sus.baixar_do_ftp(
            sus.SIH.pasta_no_ftp, "RDAC2607.dbc", abrir=self._FtpFalso
        ) == (b"abcdef")

    def test_listar_a_pasta(self):
        assert sus.listar_no_ftp(sus.SIH.pasta_no_ftp, abrir=self._FtpFalso) == [
            "RDAC2607.dbc"
        ]
