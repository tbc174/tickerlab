"""Titulares do INPI (linha 904, lote 2): só CNPJ de DV certo e tipo que não é pessoa física entra; nome, CPF,
país e estado nunca chegam à tabela; raiz de MEI e raiz desconhecida ficam marcadas como pessoa (a porta não
as serve); o titular vale desde o dia do retrato (sem olhar o futuro) e o que some do arquivo ganha `consta` falso.

Os arquivos daqui são de mentira, no formato conferido em 13/11/2026 nos guardados pelo arquivista; os CNPJs
são de ninguém e o CPF é inventado."""

import hashlib
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import inpi_titulares
from base.arquivo.destinos import DESTINOS, TABELA
from base.dicionario import TABELAS
from base.inpi_titulares import ARQUIVOS, Titulares
from base.porta import Porta
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
PRIMEIRO_DIA = date(2026, 11, 4)
SEGUNDO_DIA = date(2026, 11, 11)
NOME_DE_MENTIRA = "FULANO DE TAL ME"


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
OUTRA = _cnpj("22333444")
MEI = _cnpj("44555666")
DESCONHECIDA = _cnpj("77888999")
INVALIDO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)
CPF = "88800000551"
FISICA_COM_14 = _cnpj("55666777")  # o INPI marca "F" com 14 dígitos em 8 mil desenhos


def _cpf_com_zeros() -> str:
    """ "000" + um CPF inventado que começa com 00: fecha o DV do CNPJ (achado da revisão cruzada, 13/11/2026)."""
    for i in range(1, 10**7):
        nove = f"00{i:07d}"
        d1 = (
            sum(int(c) * p for c, p in zip(nove, range(10, 1, -1), strict=True))
            * 10
            % 11
        ) % 10
        d2 = (
            sum(
                int(c) * p
                for c, p in zip(nove + str(d1), range(11, 1, -1), strict=True)
            )
            * 10
            % 11
        ) % 10
        cpf = f"{nove}{d1}{d2}"
        doc = "000" + cpf
        if cnpjs.cpf_confere(cpf) and cnpjs.dv_confere(doc) and doc[8:12] != "0001":
            return doc
    raise AssertionError


CPF_COM_ZEROS = _cpf_com_zeros()


def _matriz_de_raiz_com_zeros() -> str:
    """Empresa inventada de raiz `000xxxxx` e filial 0001 cujo DV fecha também como CPF (como a do Banco do Brasil)."""
    for i in range(1, 10**5):
        doc = _cnpj(f"000{i:05d}")
        if cnpjs.cpf_confere(doc[3:]):
            return doc
    raise AssertionError


MATRIZ_COM_ZEROS = _matriz_de_raiz_com_zeros()

MARCAS, PATENTES, DESENHOS, PROGRAMAS = ARQUIVOS


def _csv(arquivo: Titulares, *linhas: tuple[str, ...]) -> bytes:
    """(número, documento, tipo de pessoa[, data de fim da titularidade]) → o CSV de titulares, com as colunas que o INPI manda."""
    linhas = tuple((*linha, "") if len(linha) == 3 else linha for linha in linhas)  # type: ignore[assignment]
    if arquivo is MARCAS:
        cabecalho = "codigo_interno,numero_inpi,nome,cnpj_cpf_titular,tipo_pfpj_titular,estado,pais"
        corpo = [f"1,{n},{NOME_DE_MENTIRA},{d},{t},SP,Brasil" for n, d, t, _ in linhas]
    elif arquivo is PROGRAMAS:
        cabecalho = "codigo_interno,numero_inpi,nome_titular,data_inicio_titular,data_fim_titular,cnpj_cpf_titular,pais,estado"
        corpo = [
            f"1,{n},{NOME_DE_MENTIRA},2020-01-01,{f},{d},BR,SP" for n, d, _, f in linhas
        ]
    else:
        cabecalho = "codigo_interno,numero_inpi,ordem,depositante,cgccpfdepositante,tipopessoadepositante,pais,estado"
        corpo = [f"1,{n},1,{NOME_DE_MENTIRA},{d},{t},BR,SP" for n, d, t, _ in linhas]
        if arquivo is PATENTES:
            cabecalho += ",data_inicio_depositante,data_fim_depositante"
            corpo = [
                f"{c},2020-01-01,{f}" for c, (*_, f) in zip(corpo, linhas, strict=True)
            ]
    return ("\n".join([cabecalho, *corpo]) + "\n").encode()


def _url(arquivo: Titulares) -> str:
    return f"https://dadosabertos.inpi.gov.br/download/x/{arquivo.termina_em}"


@pytest.mark.parametrize("arquivo", ARQUIVOS, ids=lambda a: a.tabela)
def test_so_cnpj_de_empresa_entra_e_nem_o_cpf_nem_o_nome_vazam(arquivo):
    tipo_pj = {
        MARCAS: "PESSOA JURÍDICA",
        PATENTES: "pessoa jurídica",
        DESENHOS: "J",
    }.get(arquivo, "")
    tipo_pf = {MARCAS: "PESSOA FÍSICA", PATENTES: "pessoa física", DESENHOS: "F"}.get(
        arquivo, ""
    )
    tabela, contagem = inpi_titulares.ler_retrato(
        _csv(
            arquivo,
            ("900000001", EMPRESA, tipo_pj),
            ("900000002", CPF, tipo_pf),
            ("900000003", INVALIDO, tipo_pj),
            ("900000001", EMPRESA, tipo_pj),  # a mesma empresa no mesmo pedido
            ("900000004", EMPRESA, tipo_pj),  # outro pedido: outra linha
            ("900000005", "", tipo_pj),  # titular sem documento (estrangeiro)
            ("900000006", FISICA_COM_14, tipo_pf),
            (
                "900000007",
                CPF_COM_ZEROS,
                tipo_pj,
            ),  # CPF completado com zeros que fecha o DV do CNPJ
            (
                "900000008",
                MATRIZ_COM_ZEROS,
                tipo_pj,
            ),  # empresa que também fecha como CPF: entra
        ),
        arquivo,
    )
    esperadas = ["900000001", "900000004", "900000008"]
    if arquivo is PROGRAMAS:  # sem tipo de pessoa: só o documento decide
        esperadas = ["900000001", "900000004", "900000006", "900000008"]
    assert list(tabela["numero_inpi"]) == esperadas
    assert tabela["id_na_fonte"].iloc[0] == f"900000001|{EMPRESA}"
    assert contagem["linhas"] == 9
    assert contagem["id_repetido"] == 1
    assert contagem["sem_cnpj_valido"] == 3  # CPF, DV errado e vazio
    assert contagem["tipo_pessoa_fisica"] == (0 if arquivo is PROGRAMAS else 1)
    assert contagem["cpf_com_zeros"] == 1
    assert "900000007" not in set(tabela["numero_inpi"])
    assert (
        CPF_COM_ZEROS not in tabela["cnpj"].str.replace(r"\D", "", regex=True).tolist()
    )
    tudo = tabela.astype(str).to_csv() + " ".join(tabela.columns)
    assert NOME_DE_MENTIRA not in tudo
    assert CPF not in tudo.replace(".", "").replace("-", "")
    assert set(tabela.columns) == {"id_na_fonte", "cnpj", "cnpj_basico", "numero_inpi"}


@pytest.mark.parametrize("arquivo", [PATENTES, PROGRAMAS], ids=lambda a: a.tabela)
def test_titularidade_com_data_de_fim_nao_entra(arquivo):
    tipo = "pessoa jurídica" if arquivo is PATENTES else ""
    tabela, contagem = inpi_titulares.ler_retrato(
        _csv(
            arquivo,
            ("900000001", EMPRESA, tipo, ""),
            ("900000002", EMPRESA, tipo, "2025-06-30"),  # transferiu o pedido
        ),
        arquivo,
    )
    assert list(tabela["numero_inpi"]) == ["900000001"]
    assert contagem["titularidade_encerrada"] == 1


def test_titular_que_transfere_o_pedido_ganha_consta_falso(banco, tmp_path):
    """Patentes: no retrato seguinte a empresa A ganha a data de fim; a tabela deixa de mostrá-la como atual."""
    tipo = "pessoa jurídica"
    _coletar(
        banco, PATENTES, _csv(PATENTES, ("900000001", EMPRESA, tipo, "")), PRIMEIRO_DIA
    )
    _coletar(
        banco,
        PATENTES,
        _csv(
            PATENTES,
            ("900000001", EMPRESA, tipo, "2026-11-05"),
            ("900000001", OUTRA, tipo, ""),
        ),
        SEGUNDO_DIA,
    )
    pasta = tmp_path / "base"
    with banco.connect() as conexao:
        inpi_titulares.montar(conexao, pasta, AGORA, pessoas=set())
    gravada = pd.read_parquet(pasta / PATENTES.tabela / "titulares.parquet")
    antigo = gravada[gravada["id_na_fonte"] == f"900000001|{EMPRESA}"]
    assert list(antigo["consta"]) == [True, False]
    novo = gravada[gravada["id_na_fonte"] == f"900000001|{OUTRA}"]
    assert list(novo["consta"]) == [True]


def test_arquivo_grande_lido_em_pedacos_da_o_mesmo_resultado(monkeypatch):
    linhas = [(f"9{i:08d}", EMPRESA, "PESSOA JURÍDICA") for i in range(25)]
    inteiro, _ = inpi_titulares.ler_retrato(_csv(MARCAS, *linhas), MARCAS)
    monkeypatch.setattr(inpi_titulares, "PEDACO", 4)
    em_pedacos, contagem = inpi_titulares.ler_retrato(_csv(MARCAS, *linhas), MARCAS)
    pd.testing.assert_frame_equal(inteiro, em_pedacos)
    assert contagem["linhas"] == 25


def test_titular_vale_desde_o_dia_do_retrato():
    novos = pd.DataFrame({"numero_inpi": ["1", "2"]})
    dia = pd.Timestamp("2026-11-04")
    assert list(inpi_titulares.disponivel_no_dia(novos, dia)) == [dia, dia]


def test_cada_arquivo_tem_tabela_no_dicionario_e_destino_de_tabela():
    assert len({a.tabela for a in ARQUIVOS}) == 4
    for arquivo in ARQUIVOS:
        assert arquivo.tabela in TABELAS
        assert DESTINOS[arquivo.fonte].tipo == TABELA
        assert DESTINOS[arquivo.fonte].tabelas == (arquivo.tabela,)
        assert TABELAS[arquivo.tabela].linhas_de_pessoa == "trata_como_pessoa"
    colunas = {a.tabela: set(TABELAS[a.tabela].colunas) for a in ARQUIVOS}
    for cadastro in inpi_titulares.CADASTROS:
        assert set(cadastro.colunas) <= colunas[cadastro.tabela]


def _coletar(banco, arquivo: Titulares, conteudo: bytes, dia: date) -> None:
    url = _url(arquivo)
    com_registro(arquivo.fonte, lambda *_: conteudo)(url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(
                coletas.coletas.c.url == url,
                coletas.coletas.c.sha256 == hashlib.sha256(conteudo).hexdigest(),
            )
            .values(baixado_em=datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC))
        )


@pytest.mark.parametrize("arquivo", ARQUIVOS, ids=lambda a: a.tabela)
def test_so_empresa_de_verdade_chega_a_quem_consulta(banco, tmp_path, arquivo):
    """CPF, raiz de MEI e raiz que a Receita não tem: nenhum passa pela porta (na dúvida, é pessoa)."""
    tipo = "J" if arquivo is DESENHOS else "pessoa jurídica"
    _coletar(
        banco,
        arquivo,
        _csv(
            arquivo,
            ("900000001", EMPRESA, tipo),
            ("900000002", MEI, tipo),
            ("900000003", DESCONHECIDA, tipo),
            ("900000004", CPF, tipo),
        ),
        PRIMEIRO_DIA,
    )
    pasta = tmp_path / "base"
    with banco.connect() as conexao:
        resumo = inpi_titulares.montar(
            conexao, pasta, AGORA, pessoas={MEI[:8], DESCONHECIDA[:8]}
        )
    assert resumo[arquivo.tabela]["sem_cnpj_valido"] == 1
    gravada = pd.read_parquet(pasta / arquivo.tabela / "titulares.parquet")
    assert dict(
        zip(gravada["cnpj_basico"], gravada["trata_como_pessoa"], strict=True)
    ) == {EMPRESA[:8]: False, MEI[:8]: True, DESCONHECIDA[:8]: True}
    assert set(gravada["disponivel_em"]) == {PRIMEIRO_DIA}
    with Porta(pasta) as porta:
        servidas = porta.con.execute(
            f"SELECT cnpj_basico, numero_inpi FROM {arquivo.tabela}"
        ).fetchall()
    assert servidas == [(EMPRESA[:8], "900000001")]
    assert NOME_DE_MENTIRA not in str(gravada.to_dict())


def test_titular_que_some_do_arquivo_ganha_linha_consta_falso(banco, tmp_path):
    tipo = "PESSOA JURÍDICA"
    primeiro = [("900000001", EMPRESA, tipo), ("900000002", OUTRA, tipo)]
    _coletar(banco, MARCAS, _csv(MARCAS, *primeiro), PRIMEIRO_DIA)
    _coletar(banco, MARCAS, _csv(MARCAS, primeiro[0]), SEGUNDO_DIA)
    pasta = tmp_path / "base"
    with banco.connect() as conexao:
        inpi_titulares.montar(conexao, pasta, AGORA, pessoas=set())
    gravada = pd.read_parquet(pasta / MARCAS.tabela / "titulares.parquet")
    saiu = gravada[gravada["id_na_fonte"] == f"900000002|{OUTRA}"]
    assert list(saiu["consta"]) == [True, False]
    assert list(saiu["disponivel_em"]) == [PRIMEIRO_DIA, SEGUNDO_DIA]
    ficou = gravada[gravada["id_na_fonte"] == f"900000001|{EMPRESA}"]
    assert list(ficou["consta"]) == [True]


def test_comando_monta_as_quatro_tabelas_e_sem_nada_guardado_sai_com_1(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import carga_inpi_titulares

    assert carga_inpi_titulares.main(["--pasta", str(tmp_path / "b")]) == 1
    _coletar(
        banco,
        PROGRAMAS,
        _csv(PROGRAMAS, ("900000001", EMPRESA, "")),
        PRIMEIRO_DIA,
    )
    assert carga_inpi_titulares.main(["--pasta", str(tmp_path / "b")]) == 0
    gravada = pd.read_parquet(tmp_path / "b" / PROGRAMAS.tabela / "titulares.parquet")
    assert gravada["trata_como_pessoa"].all()  # sem a Receita guardada: o conservador
