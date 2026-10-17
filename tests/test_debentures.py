"""Tabela `debentures_assembleias` (modelo 18, PR 1): assembleias de debenturistas, avisos e notificações
do agente fiduciário que as companhias entregam no IPE, com o tema lido do assunto. Sem internet: o
IPE é montado aqui e guardado num acervo de mentira."""

import io
import json
import zipfile
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base import debentures
from base.ancoragem import parquets_sem_manifesto
from base.licenca import licenca_da_tabela
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import Marca, registrar
from src.banco.conexao import criar_engine, migrar_para

VERSAO = "9b1e0c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7c"
AGORA = datetime(2026, 10, 17, 12, tzinfo=UTC)
RAD = "https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?Tela=ext&descTipo=IPE"
CNPJ = "11.111.111/0001-11"
COLUNAS_DO_IPE = (
    "CNPJ_Companhia",
    "Nome_Companhia",
    "Codigo_CVM",
    "Data_Referencia",
    "Categoria",
    "Tipo",
    "Especie",
    "Assunto",
    "Data_Entrega",
    "Tipo_Apresentacao",
    "Protocolo_Entrega",
    "Versao",
    "Link_Download",
)
ASSEMBLEIA = ("Assembleia", "AGDEB", "Ata")
EDITAL = ("Assembleia", "AGDEB", "Edital de Convocação")
AVISO = ("Aviso aos Debenturistas", "", "")
NOTIFICACAO = (
    "Dados Econômico-Financeiros",
    "Notificação do agente fiduciário aos debenturistas",
    "",
)
RELATORIO_DO_AGENTE = (
    "Dados Econômico-Financeiros",
    "Relatório de Agente Fiduciário",
    "",
)
AGE = ("Assembleia", "AGE", "Ata")


def _linha(
    protocolo: str,
    tipo: tuple[str, str, str] = ASSEMBLEIA,
    assunto: str = "Ata da AGD",
    entrega: str = "2023-07-10",
    referencia: str | None = None,
    versao: str = "1",
) -> dict[str, str]:
    categoria, tipo_ipe, especie = tipo
    return {
        "CNPJ_Companhia": CNPJ,
        "Nome_Companhia": "LIGHT S.A.",
        "Codigo_CVM": "9999",
        "Data_Referencia": referencia or entrega,
        "Categoria": categoria,
        "Tipo": tipo_ipe,
        "Especie": especie,
        "Assunto": assunto,
        "Data_Entrega": entrega,
        "Tipo_Apresentacao": "AP - Apresentação",
        "Protocolo_Entrega": protocolo,
        "Versao": versao,
        "Link_Download": f"{RAD}&numProtocolo={protocolo or 'sem'}&numVersao={versao}",
    }


def _bruto(*linhas: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame(list(linhas), columns=list(COLUNAS_DO_IPE)).fillna("")


# --- temas pelo assunto --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("assunto", "temas", "estresse"),
    [
        ("Vencimento Antecipado de Debêntures", {"vencimento_antecipado"}, True),
        ("Não vencimento antecipado das debêntures", {"vencimento_antecipado"}, True),
        ("ATA da AGD - Waiver", {"waiver"}, True),
        ("Concessão de anuência", {"waiver"}, True),
        (
            "Alteração dos índices e limites (covenants financeiros)",
            {"covenant"},
            True,
        ),
        (
            "3ª Emissão - 1ª Série - Aprovação Postergação Remuneração",
            {"repactuacao"},
            True,
        ),
        (
            "(i) Deliberar sobre a suspensão do pagamento da Amortização",
            {"repactuacao"},
            True,
        ),
        ("Pedido de recuperação judicial da Emissora", {"inadimplemento"}, True),
        (
            "Consentimento prévio para a transferência do controle acionário indireto",
            {"waiver", "reorganizacao"},
            False,  # pedir licença para vender a empresa não é aperto de crédito
        ),
        ("Resgate antecipado facultativo total", {"resgate"}, False),
        # achados da conferência de 17/10/2026 (Eletropaulo, CVC e Locamerica)
        (
            "Consentimento prévio (waiver) para a aquisição do controle da Emissora",
            {"waiver", "reorganizacao"},
            False,
        ),
        (
            "Alteração das condições da Oferta de Resgate Antecipado, aprovação de waiver fee",
            {"waiver", "resgate"},
            False,
        ),
        (
            "Anuência prévia para a oferta pública inicial de ações da Companhia",
            {"waiver", "reorganizacao"},
            False,
        ),
        ("Liberação parcial da alienação fiduciária", {"garantia"}, False),
        ("Ata da Assembleia de Debenturistas - 4ª emissão", set(), False),
        ("", set(), False),
    ],
)
def test_temas_da_assembleia_pelo_assunto(assunto, temas, estresse):
    tabela = debentures.documentos_de_debenturistas(
        _bruto(_linha("1", assunto=assunto))
    )
    linha = tabela.iloc[0]
    achados = {t for t in debentures.TEMAS if linha[f"tema_{t}"]}
    assert achados == temas
    assert linha["estresse"] is estresse or linha["estresse"] == estresse
    assert linha["generico"] == (not temas)


def test_aviso_de_repactuacao_programada_nao_e_estresse():
    """No aviso aos debenturistas, a repactuação é a programada na escritura e o pagamento é rotina:
    só vencimento antecipado e inadimplemento contam como estresse."""
    tabela = debentures.documentos_de_debenturistas(
        _bruto(
            _linha("1", AVISO, "Repactuação programada - 2ª série"),
            _linha("2", AVISO, "Pagamento de juros - 5ª emissão"),
            _linha("3", AVISO, "Declaração de vencimento antecipado"),
        )
    )
    assert tabela["documento"].tolist() == ["aviso"] * 3
    assert tabela["tema_repactuacao"].tolist() == [True, False, False]
    assert tabela["tema_pagamento"].tolist() == [False, True, False]
    assert tabela["estresse"].tolist() == [False, False, True]


@pytest.mark.parametrize(
    ("assunto", "emissao"),
    [
        ("Relatório - 10ª emissão de debêntures", 10),
        ("ATA AGDEB - 1ª Série da 5ª Emissão de Debêntures Simples", 5),
        ("Terceira emissão de debêntures", 3),
        ("Décima Segunda Emissão", 12),
        ("AGD da 1a Emissão", 1),
        ("AGT - (13ª Emissão de Debêntures) - 7ª Emissão", None),  # duas: não escolhe
        ("Ata da AGD", None),
    ],
)
def test_emissao_lida_do_assunto(assunto, emissao):
    assert debentures.emissao_do_assunto(assunto) == emissao


# --- quais documentos entram e com que datas -----------------------------------------------------
def test_entram_assembleias_avisos_e_notificacoes_e_mais_nada():
    tabela = debentures.documentos_de_debenturistas(
        _bruto(
            _linha("1", ASSEMBLEIA),
            _linha("2", EDITAL),
            _linha("3", AVISO, "Pagamento de juros"),
            _linha("4", NOTIFICACAO, "Notificação de inadimplemento"),
            _linha("5", RELATORIO_DO_AGENTE, "Relatório anual"),  # PR 3, pelo PDF
            _linha(
                "6", AGE, "Vencimento antecipado das debêntures"
            ),  # assembleia de acionistas
            _linha("7", ("Fato Relevante", "", ""), "Vencimento antecipado"),
        )
    )
    assert tabela["protocolo"].tolist() == ["1", "2", "3", "4"]
    assert tabela["documento"].tolist() == [
        "assembleia",
        "assembleia",
        "aviso",
        "notificacao_do_agente",
    ]
    assert tabela["especie"].tolist() == ["Ata", "Edital de Convocação", "", ""]
    assert tabela.loc[3, "estresse"]


def test_data_publica_e_a_entrega_e_o_edital_anuncia_o_futuro():
    """O edital é entregue antes da assembleia: `referencia` (o dia da assembleia) pode vir depois de
    `publico_em`, que é sempre a entrega à CVM."""
    tabela = debentures.documentos_de_debenturistas(
        _bruto(_linha("1", EDITAL, entrega="2023-07-10", referencia="2023-07-31"))
    )
    linha = tabela.iloc[0]
    assert (linha["referencia"], linha["publico_em"]) == (
        date(2023, 7, 31),
        date(2023, 7, 10),
    )


def test_cada_versao_e_uma_linha_e_sem_protocolo_vale_o_link():
    tabela = debentures.documentos_de_debenturistas(
        _bruto(
            _linha("9", entrega="2023-07-10", versao="1"),
            _linha("9", entrega="2023-07-20", versao="2"),
            _linha("", entrega="2011-03-01"),  # de 2003 a 2014 a CVM não dá protocolo
            _linha(
                "9", entrega="2023-07-10", versao="1"
            ),  # repetida em dois arquivos anuais
        )
    )
    assert len(tabela) == 3
    assert tabela["versao"].tolist() == [1, 1, 2]
    assert tabela.loc[0, "protocolo"].startswith("https://www.rad.cvm.gov.br/")


@pytest.mark.parametrize(
    "data", ["2023-07-09", "2023-07-10", "2023-07-15", "2024-01-01"]
)
def test_como_era_na_data_nao_traz_nada_entregue_depois(data):
    bruto = _bruto(
        _linha("1", entrega="2023-07-10"),
        _linha("2", EDITAL, entrega="2023-07-12", referencia="2023-08-30"),
        _linha("3", AVISO, entrega="2023-08-01"),
    )
    ate = date.fromisoformat(data)
    tabela = debentures.documentos_de_debenturistas(bruto, ate=ate)
    assert (tabela["publico_em"] <= ate).all()
    inteira = debentures.documentos_de_debenturistas(bruto)
    pd.testing.assert_frame_equal(
        tabela, inteira[inteira["publico_em"] <= ate].reset_index(drop=True)
    )


# --- montagem pelo acervo ------------------------------------------------------------------------
def _zip_do_ipe(bruto: pd.DataFrame) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            "ipe_cia_aberta_2023.csv",
            bruto.to_csv(sep=";", index=False).encode("cp1252"),
        )
    return saida.getvalue()


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    conteudo = _zip_do_ipe(
        _bruto(
            _linha("1", assunto="Waiver - 9ª emissão"),
            _linha("2", AVISO, "Pagamento de juros"),
            _linha("3", AGE),
        )
    )
    quando = datetime(2026, 10, 16, 23, tzinfo=UTC)
    endereco = debentures.URL_DO_IPE.format(ano=2023)
    caminho = acervo.guardar_original(
        debentures.FONTE_DO_IPE, endereco, conteudo, quando
    )
    with criar_engine().begin() as c:
        registrar(
            c,
            debentures.FONTE_DO_IPE,
            endereco,
            conteudo,
            "ok",
            agora=quando,
            caminho_do_original=caminho,
        )
    return tmp_path


def test_montar_grava_a_tabela_com_manifesto_linhagem_e_licenca_vendavel(ambiente):
    with criar_engine().connect() as conexao:
        resumo = debentures.montar(conexao, ambiente / "base", AGORA)
    arquivo = (
        ambiente / "base" / "debentures_assembleias" / "debentures_assembleias.parquet"
    )
    tabela = pd.read_parquet(arquivo)
    assert tabela["protocolo"].tolist() == ["1", "2"]
    assert tabela["tema_waiver"].tolist() == [True, False]
    assert tabela["emissao"].tolist()[0] == 9
    assert resumo == {"documentos": 2, "estresse": 1, "generico": 0}
    assert len(tabela["origem_sha256"].iloc[0]) == 64
    assert tabela["versao_do_codigo"].iloc[0] == VERSAO
    assert tabela["montado_em"].iloc[0] == AGORA.isoformat()
    assert parquets_sem_manifesto(ambiente / "base") == []
    manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    assert manifesto["conferencia_do_contrato"]["aprovada"]
    # a CVM é ODbL: a tabela pode ser vendida, com atribuição (ADR 0008)
    assert licenca_da_tabela(arquivo).marca == Marca.VENDAVEL


def test_comando_monta_e_nao_regrava_o_que_nao_mudou(ambiente, tmp_path):
    from scripts import montar_debentures_assembleias

    pasta = tmp_path / "b"
    assert montar_debentures_assembleias.main(["--pasta", str(pasta)]) == 0
    arquivo = pasta / "debentures_assembleias" / "debentures_assembleias.parquet"
    antes = arquivo.stat().st_mtime_ns
    assert montar_debentures_assembleias.main(["--pasta", str(pasta)]) == 0
    assert arquivo.stat().st_mtime_ns == antes
