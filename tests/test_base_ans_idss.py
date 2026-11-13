"""Histórico do IDSS das operadoras da ANS em retrato (linha 904): formato longo, nota com vírgula, `ND` e
faixa, o `__` do nome da coluna, só CNPJ de DV certo, MEI marcado como pessoa, o arquivo de 2016 em diante
pelo prefixo e sem olhar o futuro. Arquivos de mentira, no formato conferido em 13/11/2026."""

import hashlib
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from base import ans_idss
from base import cadastros_em_retrato as montagem
from base import cnpj as cnpjs
from base.parquet import LINHAGEM
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
PRIMEIRO_DIA = date(2026, 11, 4)
SEGUNDO_DIA = date(2026, 12, 1)
PASTA = "https://dadosabertos.ans.gov.br/FTP/PDA/historico_idss-020"
URL_2009 = f"{PASTA}/pda-020-historico-idss-2009_2011.csv"
URL_2016 = f"{PASTA}/pda-020-historico-idss-2016_2025.csv"
URL_2016_NOVO = f"{PASTA}/pda-020-historico-idss-2016_2026.csv"
URL_PENALIDADES = (
    "https://dadosabertos.ans.gov.br/FTP/PDA/x/penalidades_aplicadas_a_operadoras.csv"
)
PROIBIDAS = ("nome", "razao", "cpf", "email", "telefone", "endereco", "contato")
COLUNAS_FIXAS = ["REGISTRO_OPERADORA", "CNPJ", "RAZAO_SOCIAL", "MODALIDADE"]


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


def _cpf(primeiros_9: str) -> str:
    for dv in range(100):
        if cnpjs.cpf_confere(bruto := f"{primeiros_9}{dv:02d}"):
            return bruto
    raise AssertionError(primeiros_9)


EMPRESA = cnpjs.formatar(_cnpj("11222333"))
OUTRA = cnpjs.formatar(_cnpj("33000167"))
MEI = cnpjs.formatar(_cnpj("44555666"))
DV_ERRADO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)
CPF = _cpf("888000005")
CPF_FORMATADO = f"{CPF[:3]}.{CPF[3:6]}.{CPF[6:9]}-{CPF[9:]}"


def _coletar(banco, url: str, conteudo: bytes, dia: date) -> None:
    com_registro(ans_idss.FONTE, lambda _url: conteudo)(url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(
                coletas.coletas.c.url == url,
                coletas.coletas.c.sha256 == hashlib.sha256(conteudo).hexdigest(),
            )
            .values(baixado_em=datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC))
        )


def _idss(notas: list[str], *linhas: tuple[str, str, list[str]]) -> bytes:
    """`notas`: os nomes das colunas de nota; `linhas`: (registro, CNPJ, uma nota por coluna)."""

    def linha(campos: list[str]) -> str:
        return ";".join(f'"{c}"' for c in campos)

    corpo = [
        linha([registro, cnpj, f"OPERADORA {registro}", "Medicina de Grupo", *valores])
        for registro, cnpj, valores in linhas
    ]
    return "\r\n".join([linha([*COLUNAS_FIXAS, *notas]), *corpo]).encode("utf-8")


NOTAS_DE_2016 = ["IDSS_2016_2015", "IDQS_2016_2015", "IDSS_2017_2016"]
NOTAS_DE_2009 = ["IDSS_2009_2008", "IDSS_2010__2009", "IDAS_2011_2010"]


def _de_2016(nota_da_empresa: str = "0,5222") -> bytes:
    return _idss(
        NOTAS_DE_2016,
        ("300001", EMPRESA, [nota_da_empresa, "ND", "1"]),
        ("300002", MEI, ["0,7000", "0,1", ""]),
    )


def _montar(banco, pasta, pessoas=frozenset()) -> dict:
    with banco.connect() as conexao:
        return ans_idss.montar(conexao, pasta, AGORA, pessoas=set(pessoas))


def _ler(pasta, nome: str) -> pd.DataFrame:
    return pd.read_parquet(pasta / ans_idss.TABELA / f"{nome}.parquet")


def test_le_nota_com_virgula_e_nd_em_formato_longo():
    tabela, contagem = ans_idss.ler_retrato(_de_2016())
    assert contagem["nao_disponivel"] == 1 and contagem["sem_nota"] == 1
    empresa = tabela[tabela["registro_operadora"] == "300001"].set_index("id_na_fonte")
    assert list(empresa.index) == ["300001|IDSS|2016", "300001|IDSS|2017"]
    assert list(empresa["valor"]) == [0.5222, 1.0]
    assert list(empresa["ano_avaliacao"]) == [2016, 2017]
    assert list(empresa["ano_base"]) == [2015, 2016]
    assert empresa["faixa"].isna().all()
    assert set(empresa["cnpj"]) == {EMPRESA}
    assert set(empresa["cnpj_basico"]) == {EMPRESA.replace(".", "")[:8]}
    assert set(empresa["modalidade"]) == {"Medicina de Grupo"}
    assert "OPERADORA" not in tabela.astype(str).to_csv()  # a razão social fica de fora


def test_le_a_faixa_e_o_nome_de_coluna_com_dois_sublinhados():
    tabela, contagem = ans_idss.ler_retrato(
        _idss(NOTAS_DE_2009, ("300001", EMPRESA, ["0,40 a 0,59", "0,60 a 0,79", "ND"]))
    )
    assert contagem["nao_disponivel"] == 1
    assert list(tabela["id_na_fonte"]) == ["300001|IDSS|2009", "300001|IDSS|2010"]
    assert list(tabela["faixa"]) == ["0,40 a 0,59", "0,60 a 0,79"]
    assert tabela["valor"].isna().all()
    assert list(tabela["ano_base"]) == [2008, 2009]  # `IDSS_2010__2009`


def test_cnpj_de_dv_errado_e_cpf_saem_e_sao_contados():
    tabela, contagem = ans_idss.ler_retrato(
        _idss(
            ["IDSS_2016_2015"],
            ("300001", EMPRESA, ["0,5"]),
            ("300003", DV_ERRADO, ["0,5"]),
            ("300004", CPF_FORMATADO, ["0,5"]),
        )
    )
    assert contagem["pessoa_fisica"] == 1 and contagem["cnpj_invalido"] == 1
    assert list(tabela["registro_operadora"]) == ["300001"]


def test_montar_acha_cada_arquivo_pelo_prefixo_e_marca_o_mei(banco, tmp_path):
    _coletar(banco, URL_2016, _de_2016(), PRIMEIRO_DIA)
    _coletar(banco, URL_2016_NOVO, _de_2016("0,6000"), SEGUNDO_DIA)
    _coletar(
        banco,
        URL_2009,
        _idss(NOTAS_DE_2009, ("300001", EMPRESA, ["0,40 a 0,59", "ND", "ND"])),
        PRIMEIRO_DIA,
    )
    _coletar(banco, URL_PENALIDADES, b"NRDEMANDA;CNPJ\r\n1;2", PRIMEIRO_DIA)
    resumo = _montar(banco, tmp_path, pessoas={MEI.replace(".", "")[:8]})
    assert set(resumo) == {"de_2009", "de_2016"}  # sem arquivo de 2012 guardado
    assert resumo["de_2016"]["enderecos_ignorados"] == 1
    assert resumo["de_2016"]["retratos"] == 1
    de_2016 = _ler(tmp_path, "de_2016")
    assert (
        de_2016.loc[de_2016["id_na_fonte"] == "300001|IDSS|2016", "valor"].item() == 0.6
    )
    assert dict(
        zip(de_2016["registro_operadora"], de_2016["trata_como_pessoa"], strict=True)
    ) == {"300001": False, "300002": True}
    for nome in ("de_2009", "de_2016"):
        tabela = _ler(tmp_path, nome)
        assert list(tabela.columns) == [
            *ans_idss.COLUNAS, *montagem.CARIMBOS_DA_LINHA, *LINHAGEM,
        ]  # fmt: skip
        assert not [c for c in tabela.columns if any(p in c.lower() for p in PROIBIDAS)]


def test_disponivel_em_e_o_dia_do_retrato(banco, tmp_path):
    _coletar(banco, URL_2016, _de_2016(), PRIMEIRO_DIA)
    _montar(banco, tmp_path)
    tabela = _ler(tmp_path, "de_2016")
    assert set(tabela["disponivel_em"]) == {PRIMEIRO_DIA}


def test_cortar_o_futuro_nao_muda_o_passado(banco, tmp_path):
    _coletar(banco, URL_2016, _de_2016(), PRIMEIRO_DIA)
    _montar(banco, tmp_path / "so_o_primeiro")
    _coletar(banco, URL_2016, _de_2016("0,9000"), SEGUNDO_DIA)
    _montar(banco, tmp_path / "com_os_dois")
    antes = _ler(tmp_path / "so_o_primeiro", "de_2016")
    depois = _ler(tmp_path / "com_os_dois", "de_2016")
    ja_valiam = depois[depois["disponivel_em"] <= PRIMEIRO_DIA]
    pd.testing.assert_frame_equal(
        ja_valiam.drop(columns=list(LINHAGEM)).reset_index(drop=True),
        antes.drop(columns=list(LINHAGEM)),
    )
    mudou = depois[depois["disponivel_em"] > PRIMEIRO_DIA]
    assert list(mudou["id_na_fonte"]) == ["300001|IDSS|2016"]
    assert list(mudou["valor"]) == [0.9]
    assert (depois["disponivel_em"] <= depois["visto_em"]).all()


def test_segundo_montar_sem_retrato_novo_e_ja_montado(banco, tmp_path):
    _coletar(banco, URL_2016, _de_2016(), PRIMEIRO_DIA)
    _montar(banco, tmp_path)
    assert _montar(banco, tmp_path) == {"de_2016": montagem.JA_MONTADO}
