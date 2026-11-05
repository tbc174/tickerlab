"""Preços máximos da CMED (base/cmed.py e a fonte `anvisa-cmed`).

As fixtures em `tests/arquivos/cmed/` são recortes reais de 09/10/2026 (1.195 apresentações dos
produtos registrados de uma coorte de CNPJs), com o nome do laboratório trocado. Elas não provam o
universo inteiro (26.635 apresentações de 262 CNPJs): isso só a carga sobre os arquivos completos confere.
"""

import csv
import gzip
import hashlib
import io
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest
import sqlalchemy as sa

from base import cmed, licencas
from base.arquivo import destinos, fontes
from base.dicionario import TABELAS
from base.parquet import LINHAGEM
from base.setoriais.revisoes import como_era_em
from src.banco import coletas
from src.banco.coletas import (
    Marca,
    com_registro,
    licenca_da_fonte,
    marca_da_fonte,
)
from tests.test_base_arquivo_obter import ServidorComTrechos

PASTA = Path(__file__).parent / "arquivos" / "cmed"
ARQUIVOS = {"consumidor": "consumidor.csv.gz", "governo": "governo.csv.gz"}
APRESENTACOES_NA_FIXTURE = 1195


def _bruto(lista: str) -> bytes:
    return gzip.decompress((PASTA / ARQUIVOS[lista]).read_bytes())


def _cabecalho(lista: str) -> list[str]:
    return next(
        csv.reader(io.StringIO(_bruto(lista).decode("utf-8-sig")), delimiter=";")
    )


def _cadastro(lista: str) -> fontes.CsvDeCadastro:
    url = fontes.PRECOS_DA_CMED + fontes.ARQUIVOS_DA_CMED[lista]
    (cadastro,) = [c for c in fontes.CADASTROS_DE_PRECOS_DA_CMED if c.url == url]
    return cadastro


# ---- a fonte no arquivista -------------------------------------------------------------------
def test_a_fonte_pega_as_duas_listas_e_nao_repete_a_consulta_de_medicamentos():
    (fonte,) = [f for f in fontes.FONTES if f.id == "anvisa-cmed"]
    alvos = fonte.descobrir(None, None)  # type: ignore[arg-type]
    assert [a.url for a in alvos] == [
        "https://dados.anvisa.gov.br/dados/TA_PRECO_MEDICAMENTO.csv",
        "https://dados.anvisa.gov.br/dados/TA_PRECO_MEDICAMENTO_GOV.csv",
    ]
    # a consulta de medicamentos já é da `anvisa-produtos`: uma fonte só a coleta
    consultas = [
        f.id
        for f in fontes.FONTES
        if f.id.startswith("anvisa-")
        for a in f.descobrir(None, None)  # type: ignore[arg-type]
        if a.url.endswith("TA_CONSULTA_MEDICAMENTOS.CSV")
    ]
    assert consultas == ["anvisa-produtos"]


def test_a_fonte_fica_a_confirmar_e_tem_destino_nos_precos():
    # as listas não trazem licença própria: não herdam a CC BY do resto da Anvisa (ADR 0102, Emenda 2)
    # sem licença própria: vendável por risco assumido (ADR 0122), com o texto da licença intacto
    assert "a confirmar" in licenca_da_fonte("anvisa-cmed")
    assert marca_da_fonte("anvisa-cmed") == Marca.VENDAVEL
    assert marca_da_fonte("anvisa-produtos") == Marca.VENDAVEL
    assert destinos.DESTINOS["anvisa-cmed"].tabelas == ("cmed_precos",)


@pytest.mark.parametrize("lista", ARQUIVOS)
def test_toda_coluna_pedida_existe_no_cabecalho_real(lista):
    # a coleta guarda a interseção: uma coluna renomeada sumiria calada, então o teste pega antes
    cabecalho = _cabecalho(lista)
    faltam = [c for c in _cadastro(lista).colunas if c not in cabecalho]
    assert faltam == []


@pytest.mark.parametrize("lista", ARQUIVOS)
def test_a_lista_tem_o_pf_e_so_o_preco_maximo_dela(lista):
    colunas = _cadastro(lista).colunas
    maximo = fontes.LISTAS_DA_CMED[lista]
    outro = "PMVG" if maximo == "PMC" else "PMC"
    assert set(fontes.colunas_de_preco_da_cmed("PF")) <= set(colunas)
    assert set(fontes.colunas_de_preco_da_cmed(maximo)) <= set(colunas)
    assert not [c for c in colunas if c.startswith(outro)]
    assert len(fontes.colunas_de_preco_da_cmed("PF")) == 26


@pytest.mark.parametrize("lista", ARQUIVOS)
def test_a_coleta_tira_o_laboratorio_e_o_bom_e_guarda_toda_apresentacao(
    lista, tmp_path
):
    cadastro = _cadastro(lista)
    destino = tmp_path / "cmed.csv"
    obter = cadastro.alvo().obter
    assert obter is not None
    obter(ServidorComTrechos({cadastro.url: _bruto(lista)}), destino)
    texto = destino.read_text(encoding="utf-8")
    assert not texto.startswith("﻿")
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=";"))
    assert len(linhas) == APRESENTACOES_NA_FIXTURE  # todo CNPJ da lista é inteiro
    assert set(linhas[0]) == set(cadastro.colunas)
    assert "LABORATÓRIO" not in linhas[0]
    assert "LABORATORIO DE MENTIRA" not in texto
    # os anos e a coluna vazia de nome instável ficam de fora
    assert not [c for c in linhas[0] if "COMERCIALIZAÇÃO" in c or "DESTINAÇÃO" in c]


# ---- a leitura de um retrato (base/cmed.py) --------------------------------------------------
ORENCIA = (
    "1018003900019"  # controle da pesquisa: PF 0% 2123,68; PMVG 0% 1703,40; PMC vazio
)
EVRYSDI = {
    "CNPJ": "33.009.945/0001-23",
    "CÓDIGO GGREM": "529226090029607",
    "REGISTRO": "    -     ",
}


def _linhas(lista: str) -> tuple[list[str], list[dict[str, str]]]:
    texto = _bruto(lista).decode("utf-8-sig")
    leitor = csv.DictReader(io.StringIO(texto), delimiter=";")
    return list(leitor.fieldnames or []), list(leitor)


def _gravar(tmp_path: Path, cabecalho: list[str], linhas: list[dict[str, str]]) -> Path:
    """Um CSV como a coleta grava (";", UTF-8 sem BOM)."""
    saida = io.StringIO()
    escritor = csv.DictWriter(saida, cabecalho, delimiter=";", extrasaction="ignore")
    escritor.writeheader()
    escritor.writerows(linhas)
    caminho = tmp_path / "cmed.csv"
    caminho.write_text(saida.getvalue(), encoding="utf-8")
    return caminho


def _uma(lista: str, tmp_path: Path, **trocas: str) -> pd.Series:
    """A linha do ORENCIA lida, com as células de `trocas` (nome da fonte com "_" no lugar do espaço)."""
    cabecalho, linhas = _linhas(lista)
    linha = next(l for l in linhas if l["REGISTRO"] == ORENCIA)
    linha.update({k.replace("_", " "): v for k, v in trocas.items()})
    tabela, _ = cmed.ler_retrato(_gravar(tmp_path, cabecalho, [linha]), lista)
    (lida,) = tabela.itertuples(index=False)
    return pd.Series(lida._asdict())


@pytest.mark.parametrize("lista", ARQUIVOS)
def test_controle_do_orencia(lista):
    tabela, contagem = cmed.ler_retrato(PASTA / ARQUIVOS[lista], lista)
    (orencia,) = tabela[tabela["registro"] == ORENCIA].itertuples(index=False)
    assert orencia.pf_0 == Decimal("2123.68")
    assert orencia.pmc_0 is None  # vazio é nulo, nunca zero
    assert orencia.pmvg_0 == (Decimal("1703.40") if lista == "governo" else None)
    assert orencia.registro_produto == ORENCIA[:9]
    assert orencia.id_na_fonte == "56998982000107|505107701157215"
    assert orencia.cnpj == "56.998.982/0001-07"
    assert contagem["linhas"] == APRESENTACOES_NA_FIXTURE
    assert len(tabela) == tabela["id_na_fonte"].nunique() == APRESENTACOES_NA_FIXTURE


def test_pmc_vazio_e_nulo_e_a_contagem_e_de_apresentacoes():
    tabela, contagem = cmed.ler_retrato(PASTA / ARQUIVOS["consumidor"], "consumidor")
    sem_pmc = (
        tabela[[c for c in cmed.PRECOS if c.startswith("pmc_")]].isna().all(axis=1)
    )
    # 94 apresentações sem PMC são 2.444 células vazias: a conta é de apresentações
    assert contagem["sem_pmc"] == int(sem_pmc.sum()) == 94
    assert tabela.loc[sem_pmc, "pf_0"].notna().all()


def test_zero_e_zero_e_o_asterisco_sai_do_numero(tmp_path):
    lida = _uma("governo", tmp_path, **{"PF_0%": "0,00", "PMVG_0_%": "25614,71*"})
    assert lida["pf_0"] == Decimal("0.00")
    assert lida["pmvg_0"] == Decimal("25614.71")
    assert "pmvg_0" in lida["precos_com_asterisco"].split(" / ")
    assert "pf_0" not in lida["precos_com_asterisco"].split(" / ")


def test_texto_que_nao_e_preco_fica_nulo_com_o_texto_guardado(tmp_path):
    lida = _uma("consumidor", tmp_path, **{"PF_0%": "1.234,56", "PF_12_%": "12,345"})
    assert (
        lida["pf_0"] is None and lida["pf_12"] is None
    )  # nunca arredondado nem adivinhado
    assert lida["precos_ilegiveis"] == "pf_0=1.234,56 / pf_12=12,345"


def test_marcas_sim_nao_e_o_resto_nulo(tmp_path):
    lida = _uma("consumidor", tmp_path, CAP="Não", CONFAZ_87="Sim", **{"ICMS_0%": "?"})
    assert lida["cap"] is False and lida["confaz_87"] is True
    assert lida["icms_0"] is None


def test_o_marcador_do_evrysdi_nao_vira_registro(tmp_path):
    cabecalho, linhas = _linhas("consumidor")
    linha = {**linhas[0], **EVRYSDI, "PF 0%": "58405,53", "PMC 0 %": "78348,94"}
    tabela, contagem = cmed.ler_retrato(
        _gravar(tmp_path, cabecalho, [linha]), "consumidor"
    )
    (lida,) = tabela.itertuples(index=False)
    assert lida.registro is None and lida.registro_produto is None
    assert lida.pmc_0 == Decimal("78348.94")
    assert contagem["registro_fora_do_padrao"] == 1


def test_uma_linha_por_apresentacao_qualquer_que_seja_a_ordem(tmp_path):
    cabecalho, linhas = _linhas("consumidor")
    repetida = {**linhas[0], "PF 0%": "1,00"}
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a, _ = cmed.ler_retrato(
        _gravar(tmp_path / "a", cabecalho, [linhas[0], repetida]), "consumidor"
    )
    b, contagem = cmed.ler_retrato(
        _gravar(tmp_path / "b", cabecalho, [repetida, linhas[0]]), "consumidor"
    )
    assert contagem["id_repetido"] == 1
    pd.testing.assert_frame_equal(a, b)


def test_cnpj_que_nao_e_inteiro_nao_entra(tmp_path):
    cabecalho, linhas = _linhas("consumidor")
    mascarado = {**linhas[1], "CNPJ": "***.456.789-**"}
    tabela, contagem = cmed.ler_retrato(
        _gravar(tmp_path, cabecalho, [linhas[0], mascarado]), "consumidor"
    )
    assert len(tabela) == 1 and contagem["cnpj_invalido"] == 1


def test_o_laboratorio_nao_e_lido_e_cada_preco_tem_coluna_propria():
    tabela, _ = cmed.ler_retrato(PASTA / ARQUIVOS["consumidor"], "consumidor")
    assert list(tabela.columns) == [c for c in cmed.COLUNAS if c in tabela.columns]
    assert not [c for c in tabela.columns if "laborat" in c]
    assert (
        len(cmed.PRECOS) == 78
    )  # PF, PMC e PMVG: sem imposto, 0% e 12 alíquotas com e sem ALC
    assert {"pf_17_5_alc", "pmc_sem_impostos", "pmvg_0", "pf_0"} <= set(cmed.PRECOS)


def test_layout_novo_e_avisado(tmp_path):
    cabecalho, linhas = _linhas("governo")
    sem_pmvg = [c for c in cabecalho if not c.startswith("PMVG")]
    with pytest.raises(cmed.LayoutNovo, match="PMVG0"):
        cmed.ler_retrato(_gravar(tmp_path, sem_pmvg, linhas[:3]), "governo")


# ---- a história, a ponte e a carga -----------------------------------------------------------
AGORA = datetime(2026, 12, 1, 22, tzinfo=UTC)
PRIMEIRO_DIA = date(2026, 11, 4)
SEGUNDO_DIA = date(2026, 12, 1)
PUBLICADA = "Fri, 09 Oct 2026 21:15:02 GMT"
VITAMEDIC = (
    "1039200910036",
    "1039200910052",
)  # o ID 937 é deles só entre os REGISTRADOS


def _url(lista: str) -> str:
    return fontes.PRECOS_DA_CMED + fontes.ARQUIVOS_DA_CMED[lista]


def _como_a_coleta(lista: str, linhas: list[dict[str, str]]) -> bytes:
    """O arquivo como o arquivista o guarda: só as colunas pedidas, ";" e UTF-8 sem BOM."""
    cabecalho, _ = _linhas(lista)
    saida = io.StringIO()
    escritor = csv.DictWriter(saida, cabecalho, delimiter=";", extrasaction="ignore")
    escritor.writeheader()
    escritor.writerows(linhas)
    cadastro = _cadastro(lista)
    obter = cadastro.alvo().obter
    assert obter is not None
    with tempfile.TemporaryDirectory() as pasta:
        destino = Path(pasta) / "lista.csv"
        obter(
            ServidorComTrechos({cadastro.url: saida.getvalue().encode("utf-8-sig")}),
            destino,
        )
        return destino.read_bytes()


def _coletar(banco, url: str, conteudo: bytes, dia: date, detalhe: str = "") -> None:
    """Uma coleta guardada no acervo, como se o arquivista a tivesse baixado no `dia`."""
    com_registro(cmed.FONTE, lambda _url: conteudo)(url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(
                coletas.coletas.c.url == url,
                coletas.coletas.c.sha256 == hashlib.sha256(conteudo).hexdigest(),
            )
            .values(
                baixado_em=datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC),
                detalhe=detalhe,
            )
        )


def _montar(banco, pasta: Path) -> dict:
    with banco.connect() as conexao:
        return cmed.montar(conexao, pasta, AGORA, pessoas=set())


def _parquet(pasta: Path, lista: str) -> pd.DataFrame:
    return pd.read_parquet(pasta / cmed.TABELA / f"{lista}.parquet")


def test_dois_retratos_e_o_dia_seguinte_nao_reescreve_o_passado(
    banco, tmp_path, monkeypatch
):
    """O preço que muda vira linha nova desde o dia do retrato novo; a apresentação que some ganha
    `consta` falso; montar de novo depois não muda as linhas do primeiro dia."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _, linhas = _linhas("consumidor")
    orencia = next(l for l in linhas if l["REGISTRO"] == ORENCIA)
    primeiras = [orencia, *[l for l in linhas if l is not orencia][:9]]
    _coletar(
        banco,
        _url("consumidor"),
        _como_a_coleta("consumidor", primeiras),
        PRIMEIRO_DIA,
        f"Last-Modified={PUBLICADA}; ETag=abc; Content-Length=1",
    )
    resumo = _montar(banco, tmp_path)
    assert resumo["consumidor"]["apresentacoes"] == 10
    assert "governo" not in resumo  # lista sem arquivo guardado fica de fora
    antes = _parquet(tmp_path, "consumidor")
    assert set(antes["lista_publicada_em"]) == {date(2026, 10, 9)}
    assert set(antes["disponivel_em"]) == {PRIMEIRO_DIA}
    arquivo = tmp_path / cmed.TABELA / "consumidor.parquet"
    assert pq.read_schema(arquivo).field("pf_0").type == cmed.TIPO_DO_PRECO  # exato

    reajustada = {**orencia, "PF 0%": "2200,00"}
    _coletar(
        banco,
        _url("consumidor"),
        _como_a_coleta("consumidor", [reajustada, *primeiras[1:9]]),
        SEGUNDO_DIA,
    )
    resumo = _montar(banco, tmp_path)
    assert resumo["consumidor"]["retratos"] == 2
    assert resumo["consumidor"]["apresentacoes"] == 9
    depois = _parquet(tmp_path, "consumidor")
    assert not list(
        (tmp_path / cmed.TABELA).glob("*.v*")
    )  # o passado não foi regravado
    pd.testing.assert_frame_equal(
        depois[depois["visto_em"] == PRIMEIRO_DIA]
        .drop(columns=list(LINHAGEM))
        .reset_index(drop=True),
        antes.drop(columns=list(LINHAGEM)).reset_index(drop=True),
    )
    novas = depois[depois["visto_em"] == SEGUNDO_DIA].set_index("registro")
    assert novas.loc[ORENCIA, "pf_0"] == Decimal("2200.00")
    assert (
        novas["lista_publicada_em"].isna().all()
    )  # o servidor não mandou o Last-Modified
    (saiu,) = novas[~novas["consta"].astype(bool)].index
    assert saiu == primeiras[9]["REGISTRO"]
    datas = depois.assign(
        disponivel_em=pd.to_datetime(depois["disponivel_em"]),
        visto_em=pd.to_datetime(depois["visto_em"]),
    )
    no_primeiro = como_era_em(datas, PRIMEIRO_DIA, ["id_na_fonte"]).set_index(
        "registro"
    )
    assert no_primeiro.loc[ORENCIA, "pf_0"] == Decimal("2123.68")  # sem olhar o futuro
    assert no_primeiro["consta"].astype(bool).all()


def _medicamentos() -> pd.DataFrame:
    tabela, _ = licencas.ler_retrato(
        PASTA / "medicamentos.csv.gz", licencas.CADASTROS["medicamentos"]
    )
    return tabela


def test_ponte_pelo_cnpj_e_registro_so_entre_os_registrados():
    apresentacoes, _ = cmed.ler_retrato(PASTA / ARQUIVOS["consumidor"], "consumidor")
    medicamentos = _medicamentos()
    ligadas = cmed.ponte(apresentacoes, medicamentos)
    assert len(ligadas) == APRESENTACOES_NA_FIXTURE  # nunca multiplica a apresentação
    assert set(ligadas["correspondencia"]) == {"unica"}
    assert ligadas["medicamento"].nunique() == 438
    # sem a situação: o arquivo dos registros não a tem por apresentação
    assert list(ligadas.columns) == [
        "id_na_fonte",
        "correspondencia",
        "medicamento",
        "processo",
    ]
    vitamedic = apresentacoes[apresentacoes["registro"].isin(VITAMEDIC)]["id_na_fonte"]
    assert len(vitamedic) == len(VITAMEDIC)
    # o mesmo 937 é um NOTIFICADO de outra empresa; a ordem do arquivo não muda a escolha
    for medicamentos_em in (
        medicamentos,
        medicamentos.sample(frac=1, random_state=7),
        medicamentos.iloc[::-1],
    ):
        ligadas = cmed.ponte(apresentacoes, medicamentos_em).set_index("id_na_fonte")
        assert set(ligadas.loc[vitamedic, "medicamento"]) == {"REGISTRADO|937"}


def test_ponte_sem_registro_ausente_e_multipla_nao_escolhe():
    apresentacoes = pd.DataFrame(
        {
            "id_na_fonte": ["a", "b", "c"],
            "cnpj": ["11.222.333/0001-81"] * 3,
            "registro_produto": [None, "100000001", "100000002"],
        }
    )
    medicamentos = pd.DataFrame(
        {
            "id_na_fonte": ["REGISTRADO|1", "REGISTRADO|2", "NOTIFICADO|3"],
            "cnpj": ["11222333000181"] * 3,
            "registro": ["100000002", "100000002", "100000001"],
            "processo": ["p1", "p2", "p3"],
        }
    )
    ligadas = cmed.ponte(apresentacoes, medicamentos).set_index("id_na_fonte")
    assert ligadas["correspondencia"].to_dict() == {
        "a": "sem_registro",
        "b": "ausente",  # só o NOTIFICADO tem esse registro
        "c": "multipla",
    }
    assert ligadas["medicamento"].isna().all()


def test_comando_monta_e_sem_nada_guardado_sai_com_1(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import carga_cmed

    assert carga_cmed.main(["--pasta", str(tmp_path / "b")]) == 1
    for lista in ARQUIVOS:
        _, linhas = _linhas(lista)
        _coletar(banco, _url(lista), _como_a_coleta(lista, linhas), PRIMEIRO_DIA)
    assert carga_cmed.main(["--pasta", str(tmp_path / "b")]) == 0
    for lista in ARQUIVOS:
        tabela = _parquet(tmp_path / "b", lista)
        assert tabela["id_na_fonte"].nunique() == APRESENTACOES_NA_FIXTURE
        assert tabela[
            "trata_como_pessoa"
        ].all()  # sem a Receita guardada: o conservador
    assert (
        carga_cmed.resumo_da_ponte(tmp_path / "b") == {}
    )  # sem os medicamentos montados


def test_resumo_da_ponte_com_os_medicamentos_montados(tmp_path):
    from scripts import carga_cmed

    cadastro = licencas.CADASTROS["medicamentos"]
    (tmp_path / cadastro.tabela).mkdir()
    _medicamentos().assign(visto_em=PRIMEIRO_DIA, consta=True).to_parquet(
        tmp_path / cadastro.tabela / f"{cadastro.nome}.parquet"
    )
    apresentacoes, _ = cmed.ler_retrato(PASTA / ARQUIVOS["governo"], "governo")
    (tmp_path / cmed.TABELA).mkdir()
    apresentacoes.assign(visto_em=PRIMEIRO_DIA, consta=True).to_parquet(
        tmp_path / cmed.TABELA / "governo.parquet"
    )
    assert carga_cmed.resumo_da_ponte(tmp_path) == {
        "governo": {"unica": APRESENTACOES_NA_FIXTURE, "produtos": 438}
    }


def test_o_dicionario_descreve_cada_coluna_e_o_contrato_tem_as_chaves():
    tabela = TABELAS["cmed_precos"]
    assert set(tabela.colunas) == {*cmed.COLUNAS, *LINHAGEM}
    assert tabela.chaves == ("lista", "id_na_fonte", "visto_em")
    assert tabela.pasta == cmed.TABELA
    assert tabela.datas["publico_em"] == "disponivel_em"
    precos = {
        c for c, (_, unidade) in tabela.colunas.items() if unidade == "reais (R$)"
    }
    assert precos == set(cmed.PRECOS)
