"""Quando cada negócio de M&A ficou público, provado, e a confirmação pelo CNPJ (base/ma_datas.py; ADR
0082, série 5 do plano de M&A, passo 4).

Tudo aqui é inventado: empresas, raízes de CNPJ, consultas do Wayback e arquivos da Receita.
"""

import io
import json
import zipfile
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base import ma_assessorias as ma
from base import ma_datas as datas
from base import ma_ligacao as lig
from base.arquivo import wayback
from base.dicionario import TABELAS
from base.parquet import conferir_tabela, ler_tabela
from scripts import carga_ma_assessorias as carga
from src import acervo
from src.banco.coletas import registrar
from tests.test_base_ma_ligacao import (
    RAIZ_ALFA,
    RAIZ_DELTA,
    RECEITA,
    _negocio,
    _zip,
    ambiente,  # noqa: F401 (fixture)
)

COLETA = datetime(2026, 10, 16, 3, tzinfo=UTC)
CNPJ_BAIXADO = datetime(2026, 10, 14, 4, 42, tzinfo=UTC)
URL = "https://www.igcp.com.br/transactions/a-alfa-foi-adquirida-pela-delta"


def _cdx(*capturas: tuple[str, str]) -> bytes:
    linhas = [["timestamp", "original", "statuscode", "digest"]]
    linhas += [[ts, URL, status, "D"] for ts, status in capturas]
    return json.dumps(linhas).encode()


# --- Wayback ---------------------------------------------------------------------------------------
def test_primeira_copia_e_a_mais_antiga_que_respondeu_200():
    cdx = _cdx(
        ("20260601000000", "200"), ("20260412004611", "301"), ("20260412042937", "200")
    )
    assert datas.primeira_copia(cdx) == (
        "20260412042937",
        datetime(2026, 4, 12, 4, 29, 37, tzinfo=UTC),
    )


@pytest.mark.parametrize("cdx", [b"[]", _cdx(("20260412004611", "301"))])
def test_sem_copia_200_nao_ha_data_do_wayback(cdx):
    assert datas.primeira_copia(cdx) is None


def test_copia_do_wayback_aponta_a_consulta_guardada_e_o_link_da_copia():
    consulta = wayback.consulta(URL)
    guardada = datas.Guardado(consulta, "a" * 64, COLETA)
    tabela = datas.copias_do_wayback([(guardada, _cdx(("20260412042937", "200")))])
    linha = tabela.iloc[0]
    assert linha["url"] == URL
    assert linha["wayback_consulta"] == consulta
    assert linha["wayback_sha256"] == "a" * 64
    assert linha["wayback_copia"] == f"https://web.archive.org/web/20260412042937/{URL}"


# --- sócios da Receita -----------------------------------------------------------------------------
def _socios() -> io.BytesIO:
    # básico; identificador (1 PJ, 2 PF, 3 estrangeiro); nome; CNPJ/CPF; qualificação; entrada; país;
    # CPF do representante; nome do representante; qualificação dele; faixa etária
    return _zip(
        [
            [RAIZ_ALFA, "1", "DELTA HOLDING LTDA", RAIZ_DELTA, "22", "20250310", "", "***111222**", "FULANO", "05", "0"],
            [RAIZ_ALFA, "2", "BELTRANO DA SILVA", "***333444**", "49", "20100101", "", "", "", "00", "6"],
            [RAIZ_ALFA, "3", "FOREIGN CO", "", "37", "20200101", "249", "", "", "00", "0"],
            ["99999999", "1", "OUTRA SA", "88888888", "22", "20200101", "", "", "", "00", "0"],
            ["77777777", "1", "COM CNPJ INTEIRO", "06543210000191", "22", "20190101", "", "", "", "00", "0"],
        ]
    )  # fmt: skip


def test_socios_so_pessoa_juridica_e_so_as_raizes_pedidas():
    guardado = datas.Guardado(RECEITA + "Socios0.zip", "b" * 64, CNPJ_BAIXADO)
    socios = datas.ler_socios_pj([(_socios(), guardado)], {RAIZ_ALFA, "77777777"})
    assert list(socios.columns) == list(datas.COLUNAS_DOS_SOCIOS)
    pares = set(zip(socios["raiz"], socios["socio_raiz"], strict=True))
    assert pares == {(RAIZ_ALFA, RAIZ_DELTA), ("77777777", "06543210")}
    linha = socios[socios["raiz"] == RAIZ_ALFA].iloc[0]
    assert linha["entrada_em"] == date(2025, 3, 10)
    assert (linha["prova_url"], linha["prova_sha256"]) == (
        guardado.url,
        guardado.sha256,
    )
    # nada de pessoa: nem o nome do sócio nem o representante saem do leitor
    texto = socios.to_string()
    assert "FULANO" not in texto and "BELTRANO" not in texto and "***" not in texto


# --- as datas --------------------------------------------------------------------------------------
def _entrada(
    wayback_em: datetime | None = None,
    socio_desde: str | None = None,
    comprador_raiz: str | None = RAIZ_DELTA,
):
    tabela = ma.tabela(
        [
            {
                **_negocio(url=URL, alvo="Alfa", comprador="Delta"),
                "sha256": "c" * 64,
                "coletado_em": COLETA,
            }
        ]
    )
    partes = lig.partes(tabela).assign(
        id_entidade=None, lei=None, ligacao_por="nome_exato", candidatos=1,
        cnpj_raiz=lambda t: t["nome"].map({"Alfa": RAIZ_ALFA, "Delta": comprador_raiz}),
    )  # fmt: skip
    negocios = pd.DataFrame({"assessoria": ["igc"], "url": [URL], "id_negocio": ["N1"]})
    copias = datas.copias_do_wayback(
        []
        if wayback_em is None
        else [
            (
                datas.Guardado(wayback.consulta(URL), "a" * 64, COLETA),
                _cdx((f"{wayback_em:%Y%m%d%H%M%S}", "200")),
            )
        ]
    )
    socios = pd.DataFrame(
        []
        if socio_desde is None
        else [
            {
                "raiz": RAIZ_ALFA,
                "socio_raiz": RAIZ_DELTA,
                "entrada_em": date.fromisoformat(socio_desde),
                "prova_url": RECEITA + "Socios0.zip",
                "prova_sha256": "b" * 64,
                "prova_em": CNPJ_BAIXADO,
            }
        ],
        columns=list(datas.COLUNAS_DOS_SOCIOS),
    )
    return datas.datar(tabela, partes, negocios, copias, socios).iloc[0]


def test_sem_nenhuma_prova_fica_a_data_da_coleta():
    linha = _entrada(comprador_raiz=None)
    assert linha["conhecido_em"] == COLETA
    assert linha["conhecido_por"] == "coleta"
    assert (linha["prova_url"], linha["prova_sha256"]) == (URL, "c" * 64)
    assert linha["conferencia"] == "assessoria"


def test_a_copia_do_wayback_antes_da_coleta_vira_o_conhecido_em():
    linha = _entrada(wayback_em=datetime(2026, 4, 12, 4, 29, 37, tzinfo=UTC))
    assert linha["conhecido_em"] == datetime(2026, 4, 12, 4, 29, 37, tzinfo=UTC)
    assert linha["conhecido_por"] == "wayback"
    assert linha["prova_url"] == wayback.consulta(URL)
    assert linha["prova_sha256"] == "a" * 64


def test_copia_do_wayback_depois_da_coleta_nao_muda_nada():
    linha = _entrada(wayback_em=datetime(2026, 10, 17, tzinfo=UTC))
    assert linha["conhecido_por"] == "coleta"
    assert linha["wayback_em"] == datetime(2026, 10, 17, tzinfo=UTC)


def test_comprador_socio_pj_da_alvo_confirma_e_da_a_data_de_fechamento():
    linha = _entrada(socio_desde="2025-03-10")
    assert linha["conferencia"] == "confirmado"
    assert linha["confirmado_por"] == "rfb-cnpj"
    assert linha["fechamento_em"] == date(2025, 3, 10)
    assert (linha["confirmacao_url"], linha["confirmacao_sha256"]) == (
        RECEITA + "Socios0.zip",
        "b" * 64,
    )
    # o CNPJ guardado (14/10) é prova mais antiga que a coleta da página (16/10)
    assert linha["conhecido_em"] == CNPJ_BAIXADO
    assert linha["conhecido_por"] == "rfb-cnpj"


def test_sem_olhar_o_futuro_a_data_da_etapa_nunca_vira_o_conhecido_em():
    """A entrada do sócio em 2019 é a data do fechamento, não a de quando ficou público: o
    conhecido_em é a prova mais antiga guardada (o arquivo da Receita baixado em 14/10/2026)."""
    linha = _entrada(socio_desde="2019-01-02")
    assert linha["fechamento_em"] == date(2019, 1, 2)
    assert linha["conhecido_em"] == CNPJ_BAIXADO


@pytest.mark.parametrize(
    "wayback_em, socio_desde",
    [
        (None, None),
        (datetime(2026, 4, 12, tzinfo=UTC), None),
        (datetime(2026, 10, 15, tzinfo=UTC), "2025-03-10"),
        (datetime(2026, 10, 1, tzinfo=UTC), "2025-03-10"),
        (datetime(2027, 1, 1, tzinfo=UTC), "2019-01-02"),
    ],
)
def test_conhecido_em_e_sempre_a_prova_mais_antiga_e_nunca_antes_dela(
    wayback_em, socio_desde
):
    linha = _entrada(wayback_em=wayback_em, socio_desde=socio_desde)
    provas = [COLETA]
    if wayback_em is not None:
        provas.append(wayback_em)
    if socio_desde is not None:
        provas.append(CNPJ_BAIXADO)
    assert linha["conhecido_em"] == min(provas)
    assert linha["prova_url"] and len(linha["prova_sha256"]) == 64


def test_confirmado_so_com_a_prova_apontada():
    for linha in (_entrada(socio_desde="2025-03-10"), _entrada()):
        if linha["conferencia"] == "confirmado":
            assert linha["confirmacao_url"] and len(linha["confirmacao_sha256"]) == 64
            assert pd.notna(linha["confirmacao_em"])
        else:
            assert pd.isna(linha["confirmado_por"]) and pd.isna(
                linha["confirmacao_url"]
            )


def test_socio_de_outra_empresa_nao_confirma():
    assert (
        _entrada(socio_desde="2025-03-10", comprador_raiz="12121212")["conferencia"]
        == "assessoria"
    )


def test_negocio_com_varias_paginas_fica_com_a_data_mais_antiga():
    tabela = ma.tabela(
        [
            {**_negocio(url=u, alvo="Alfa", comprador="Delta"), "sha256": "c" * 64, "coletado_em": quando}
            for u, quando in (("u1", COLETA), ("u2", datetime(2026, 9, 1, tzinfo=UTC)))
        ]
    )  # fmt: skip
    partes = lig.partes(tabela).assign(
        id_entidade=None,
        lei=None,
        ligacao_por="sem_ligacao",
        candidatos=0,
        cnpj_raiz=None,
    )
    negocios = pd.DataFrame(
        {"assessoria": ["igc", "igc"], "url": ["u1", "u2"], "id_negocio": ["N1", "N1"]}
    )
    vazio = pd.DataFrame(columns=list(datas.COLUNAS_DOS_SOCIOS))
    saida = datas.datar(tabela, partes, negocios, datas.copias_do_wayback([]), vazio)
    assert set(saida["conhecido_em_do_negocio"]) == {datetime(2026, 9, 1, tzinfo=UTC)}


def test_tabela_tem_as_colunas_do_dicionario():
    assert set(TABELAS["ma_datas"].colunas) == set(datas.COLUNAS)
    assert TABELAS["ma_datas"].datas["publico_em"] == "conhecido_em"


def test_resumo_conta_cada_prova():
    saida = pd.DataFrame(
        {
            "conhecido_por": ["wayback", "coleta", "rfb-cnpj"],
            "wayback_em": [COLETA, None, None],
            "conferencia": ["assessoria", "assessoria", "confirmado"],
            "fechamento_em": [None, None, date(2025, 3, 10)],
        }
    )
    assert datas.resumo(saida) == (
        "3 páginas; 1 com cópia no Wayback; conhecido_em pelo wayback 1, pelo rfb-cnpj 1, "
        "pela coleta 1; 1 confirmadas pelo CNPJ (1 com data de fechamento)"
    )


# --- carga -----------------------------------------------------------------------------------------
QUANDO_DO_WAYBACK = datetime(2026, 10, 18, 6, tzinfo=UTC)


def _guardar(fonte: str, endereco: str, conteudo: bytes, quando: datetime) -> None:
    from src.banco.conexao import obter_engine

    with obter_engine().begin() as c:
        caminho = acervo.guardar_original(fonte, endereco, conteudo, quando)
        registrar(
            c,
            fonte,
            endereco,
            conteudo,
            "ok",
            agora=quando,
            caminho_do_original=caminho,
        )


def test_carga_grava_as_datas_com_manifesto(ambiente, capsys):  # noqa: F811
    alfa = "https://www.igcp.com.br/transactions/a-alfa-oleos-foi-adquirida-pela-delta"
    _guardar(
        "wayback-igc", wayback.consulta(alfa),
        json.dumps([["timestamp", "original", "statuscode", "digest"], ["20250102030405", alfa, "200", "D"]]).encode(),
        QUANDO_DO_WAYBACK,
    )  # fmt: skip
    assert carga.main(["--base", str(ambiente)]) == 0
    arquivo = ambiente / "ma" / "datas" / "negocios.parquet"
    assert conferir_tabela(arquivo)
    manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    urls = {o["url"] for o in manifesto["origens"]}
    assert wayback.consulta(alfa) in urls
    assert "ma/ligacao/partes.parquet" in urls
    saida = ler_tabela(arquivo).set_index("url")
    assert saida.loc[alfa, "conhecido_por"] == "wayback"
    assert saida.loc[alfa, "conhecido_em"] == pd.Timestamp(
        "2025-01-02 03:04:05", tz="UTC"
    )
    assert "1 com cópia no Wayback" in capsys.readouterr().out
    # a ligação não ganha versão nova por causa dos sócios: as origens dela não mudaram
    assert not list((ambiente / "ma" / "ligacao").glob("*.v*"))


def test_carga_le_os_socios_do_mes_mais_recente(ambiente, capsys):  # noqa: F811
    _guardar(
        "rfb-cnpj",
        RECEITA + "Socios0.zip",
        _socios_da_carga(),
        datetime(2026, 10, 14, tzinfo=UTC),
    )
    assert carga.main(["--base", str(ambiente)]) == 0
    saida = ler_tabela(ambiente / "ma" / "datas" / "negocios.parquet").set_index("url")
    alfa = "https://www.igcp.com.br/transactions/a-alfa-oleos-foi-adquirida-pela-delta"
    assert saida.loc[alfa, "conferencia"] == "confirmado"
    assert saida.loc[alfa, "conhecido_por"] == "rfb-cnpj"


def _socios_da_carga() -> bytes:
    linhas = [
        [
            RAIZ_ALFA,
            "1",
            "DELTA LTDA",
            RAIZ_DELTA,
            "22",
            "20240505",
            "",
            "",
            "",
            "00",
            "0",
        ]
    ]
    texto = "\n".join(";".join(f'"{c}"' for c in linha) for linha in linhas) + "\n"
    arquivo = io.BytesIO()
    with zipfile.ZipFile(arquivo, "w") as z:
        z.writestr("K3241.K03200Y0.D61010.SOCIOCSV", texto.encode("latin-1"))
    return arquivo.getvalue()
