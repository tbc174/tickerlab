"""Candidatos a operação de M&A no IPE da CVM (série 1, PR 1): quais documentos entram e com qual pista."""

import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from base import ma_ipe
from base.ancoragem import parquets_sem_manifesto
from base.licenca import licenca_da_tabela
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import Marca, registrar
from src.banco.conexao import criar_engine, migrar_para
from tests.test_ratings import _linha, _zip

FATO = ("Fato Relevante", "")
COMUNICADO = (
    "Comunicado ao Mercado",
    "Outros Comunicados Não Considerados Fatos Relevantes",
)
OPA = ("OPA - Edital de Oferta Pública de Ações", "Edital")
VERSAO = "9b1e0c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7c"
AGORA = datetime(2026, 10, 19, 12, tzinfo=UTC)


def _candidatos(*linhas: str) -> pd.DataFrame:
    return ma_ipe.ler_candidatos_do_ipe(_zip(*linhas))


def _pista(
    categoria_e_tipo: tuple[str, str], assunto: str
) -> tuple[object, object] | None:
    """(tipo_provavel, evidencia) do documento, ou None se ele não entra."""
    tabela = _candidatos(_linha(*categoria_e_tipo, assunto))
    if tabela.empty:
        return None
    linha = tabela.iloc[0]
    return (
        None if pd.isna(linha["tipo_provavel"]) else linha["tipo_provavel"],
        linha["evidencia"],
    )


@pytest.mark.parametrize(
    ("assunto", "tipo"),
    [
        ("Acordo ou Contrato de Transferência do Controle Acionário", "ALIEN_CONTROLE"),
        ("Aprovação da incorporação de ações da controlada", "INC_ACOES"),
        ("Incorporação da subsidiária XYZ Ltda.", "INC_EMPRESA"),
        ("Cisão parcial com versão de parcela para a Beta", "CISAO"),
        ("Assinatura de contrato de compra e venda de ações da Gama", "VENDA_ATIVO"),
        ("Aquisição da Delta Participações", "AQUISICAO"),
        ("Celebração de acordo de investimento", "AQUISICAO"),
        ("Memorando de entendimentos com a Ômega", "NEGOCIACAO"),
        ("OPA para cancelamento de registro", "OPA"),
        ("Joint venture com a Épsilon", "JV"),
        ("Alienação de UPI no processo de recuperação judicial", "UPI"),
    ],
)
def test_assunto_que_diz_a_operacao_entra_com_o_tipo_provavel(assunto, tipo):
    assert _pista(FATO, assunto) == (tipo, "assunto")


@pytest.mark.parametrize(
    "assunto",
    [
        "Reorganização Societária - Incorporação, Cisão ou Fusão da Companhia",
        "Cancelamento de Registro de Companhia Aberta",
        "Mudança de Controle da Companhia",
        "Celebração ou Extinção de Contrato",
        "Fato Relevante",
        "",
        "Esclarecimento sobre notícia veiculada na imprensa",
        "Aumento de capital||Reestruturação Societária",  # o genérico vence a exclusão
    ],
)
def test_assunto_generico_entra_sem_tipo_para_o_texto_decidir(assunto):
    assert _pista(FATO, assunto) == (None, "assunto_generico")


@pytest.mark.parametrize(
    "assunto",
    [
        "Aquisição de Ações de Emissão da Própria Companhia",
        "Participação em leilão para compra de ações ordinárias de emissão da Companhia",
        "Programa de Recompra de Ações",
        "Renegociação de Dívidas",
        "Pagamento de dividendos",
        "Aquisição de direitos creditórios",
        "Laudo de avaliação de terras",
    ],
)
def test_recompra_proventos_e_divida_ficam_fora(assunto):
    assert _pista(FATO, assunto) is None


def test_exclusao_nao_derruba_tipo_forte():
    """Incorporação, fusão, cisão e OPA entram mesmo com palavra de exclusão (aumento de capital)."""
    assert _pista(FATO, "Incorporação da Beta com aumento de capital") == (
        "INC_EMPRESA",
        "assunto",
    )


def test_edital_de_opa_entra_pela_categoria():
    assert _pista(OPA, "Edital de OPA por alienação de controle") == (
        "OPA",
        "categoria",
    )


def test_comunicado_entra_so_com_tipo_no_assunto():
    assert _pista(COMUNICADO, "Conclusão da aquisição da Zeta") == (
        "AQUISICAO",
        "assunto",
    )
    assert _pista(COMUNICADO, "Reestruturação societária") is None  # genérico demais
    assert _pista(COMUNICADO, "Pagamento de dividendos") is None
    participacao = (
        "Comunicado ao Mercado",
        "Aquisição ou Alienação de Participação Acionária Relevante (art. 12)",
    )
    assert _pista(participacao, "Aquisição de participação relevante") is None


def test_outras_categorias_ficam_fora():
    assert _pista(("Assembleia", "AGE"), "Aprovação da incorporação da Beta") is None


def test_uma_linha_por_versao_com_data_publica_da_entrega():
    tabela = _candidatos(
        _linha(
            *FATO, "Aquisição da Beta", entrega="2024-03-05", protocolo="7", versao="1"
        ),
        _linha(
            *FATO, "Aquisição da Beta", entrega="2024-03-09", protocolo="7", versao="2"
        ),
    )
    assert tabela["versao"].tolist() == [1, 2]
    assert [str(d) for d in tabela["publico_em"]] == ["2024-03-05", "2024-03-09"]
    assert list(tabela.columns) == list(ma_ipe.COLUNAS)


# --- montagem pelo acervo -----------------------------------------------------------------------
def _guardar(url: str, conteudo: bytes) -> None:
    quando = datetime(2026, 10, 18, 23, tzinfo=UTC)
    caminho = acervo.guardar_original(ma_ipe.FONTE_DO_IPE, url, conteudo, quando)
    with criar_engine().begin() as c:
        registrar(
            c,
            ma_ipe.FONTE_DO_IPE,
            url,
            conteudo,
            "ok",
            agora=quando,
            caminho_do_original=caminho,
        )


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    _guardar(
        ma_ipe.URL_DO_IPE.format(ano=2024),
        _zip(
            _linha(*FATO, "Aquisição da Beta", protocolo="1"),
            _linha(*FATO, "Pagamento de dividendos", protocolo="2"),
            _linha(*OPA, "Edital", protocolo="3"),
        ),
    )
    return tmp_path


def test_montar_grava_a_tabela_com_manifesto_e_licenca_vendavel(ambiente):
    with criar_engine().connect() as conexao:
        resumo = ma_ipe.montar(conexao, ambiente / "base", AGORA)
    arquivo = ambiente / "base" / "ma" / "candidatos" / "candidatos.parquet"
    tabela = pd.read_parquet(arquivo)
    assert tabela["protocolo"].tolist() == ["1", "3"]
    assert resumo == {"assunto": 1, "assunto_generico": 0, "categoria": 1}
    assert tabela["versao_do_codigo"].iloc[0] == VERSAO
    assert parquets_sem_manifesto(ambiente / "base") == []
    manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    assert manifesto["conferencia_do_contrato"]["aprovada"]
    assert licenca_da_tabela(arquivo).marca == Marca.VENDAVEL


def test_comando_monta_e_nao_regrava_o_igual(ambiente, tmp_path):
    from scripts import montar_ma_candidatos

    assert montar_ma_candidatos.main(["--pasta", str(tmp_path / "b")]) == 0
    assert (tmp_path / "b" / "ma" / "candidatos" / "candidatos.parquet").exists()
    assert montar_ma_candidatos.main(["--pasta", str(tmp_path / "b")]) == 0


def test_referencia_depois_da_entrega_nao_tira_a_tabela_do_contrato(tmp_path):
    # o fato relevante anuncia a assembleia que vai aprovar a operação: a data de referência que a
    # companhia informa ao IPE vem depois da entrega (479 linhas na primeira carga, 18/10/2026)
    from base.conferencia import conferir

    tabela = _candidatos(
        _linha(
            *FATO, "Incorporação da Beta", entrega="2024-03-05", referencia="2024-04-10"
        )
    )
    problemas = conferir(tabela, "ma_candidatos").problemas
    assert not [p for p in problemas if p.startswith("datas")]
