"""Séries do IPEADATA que o arquivista guarda (base/arquivo/ipeadata_series.py, linha 388 da fila): a lista
escolhida por relevância para o app, com a fonte original de cada série copiada do `Metadados` do Ipeadata.
Nada vai à internet. A licença é a da fonte original (ADR 0102): sem termos publicados, marca `a_confirmar`."""

import re
from datetime import UTC, datetime

from base.arquivo import fontes as todas_as_fontes
from base.arquivo import ipeadata_series as ipea
from base.arquivo import lote_acervos as lote
from base.arquivo.coleta import Resposta
from src.banco.coletas import VENDAVEL_RISCO_ASSUMIDO, revenda_da_fonte

AGORA = datetime(2026, 11, 5, 22, tzinfo=UTC)

TEMAS_DO_APP = {"juros", "cambio", "inflacao", "atividade", "bolsa"}
# fontes originais com termos que proíbem uso comercial, ou privadas: repasse pelo Ipeadata não limpa a licença
# (licencas-por-fonte.md, linha do FGV IBRE)
FONTES_QUE_FICAM_DE_FORA = (
    "FGV",
    "Fipe",
    "Funcex",
    "Anbima",
    "Anfavea",
    "CNI",
    "CNC",
    "Seab",
    "Fenabrave",
    "FMI",
    "Banco Mundial",
    "Eletrobras",
    "Valor Econômico",
    "Dieese",
    "TSE",
    "DATASUS",
    "Outras fontes",
    "OUTFONTE",
)


class _Servidor:
    def ler(self, url, **_):
        return Resposta(url, b"{}", {})


def test_as_seis_series_do_lote_acervos_continuam():
    antigas = {
        "GM366_IBVSP366",
        "GM366_IBVSPV366",
        "BM12_TJOVER12",
        "BM12_ERV12",
        "PRECOS12_IPCA12",
        "PRECOS12_INPC12",
    }
    assert antigas <= set(ipea.SERIES)


def test_a_lista_cobre_os_temas_do_app_e_cresceu_bem_alem_de_seis():
    assert {s.tema for s in ipea.SERIES.values()} >= TEMAS_DO_APP
    assert len(ipea.SERIES) >= 60


def test_cada_serie_tem_tema_conhecido_nome_periodicidade_e_fonte():
    for codigo, serie in ipea.SERIES.items():
        assert serie.tema in ipea.TEMAS, codigo
        assert serie.nome.strip(), codigo
        assert serie.periodicidade.strip(), codigo
        assert serie.fonte in ipea.FONTES_ORIGINAIS, codigo


def test_codigo_da_serie_so_tem_letra_numero_e_sublinhado():
    """O código entra no endereço `ValoresSerie(SERCODIGO='...')`: nada de aspas nem de espaço."""
    for codigo in ipea.SERIES:
        assert re.fullmatch(r"[A-Za-z0-9_]+", codigo), codigo


def test_a_fonte_original_vem_por_extenso_e_cita_a_instituicao():
    for sigla, nome in ipea.FONTES_ORIGINAIS.items():
        assert len(nome) > len(sigla) / 2, sigla
    assert "Banco Central do Brasil" in ipea.FONTES_ORIGINAIS["Bacen Outras/SGS"]
    assert "Instituto Brasileiro de Geografia" in ipea.FONTES_ORIGINAIS["IBGE/SNIPC"]


def test_nenhuma_fonte_de_terceiro_com_restricao_entra_na_lista():
    for sigla in ipea.FONTES_ORIGINAIS:
        assert not any(sigla.startswith(f) for f in FONTES_QUE_FICAM_DE_FORA), sigla


def test_todas_as_fontes_listadas_sao_usadas_por_alguma_serie():
    usadas = {s.fonte for s in ipea.SERIES.values()}
    assert usadas == set(ipea.FONTES_ORIGINAIS)


def test_futuros_da_b3_ficam_de_fora_so_o_ibovespa_do_lote_anterior_continua():
    """Derivativos da B3 têm termos de redistribuição mais duros que o índice: decisão da linha 388."""
    assert not [c for c in ipea.SERIES if c.startswith("BMF")]


def test_ibovespa_avisa_que_1995_nao_e_serie_limpa():
    assert "implausíveis" in ipea.descricao("GM366_IBVSP366")


def test_descricao_de_cada_serie_cita_a_fonte_original():
    for codigo, serie in ipea.SERIES.items():
        assert serie.fonte in ipea.descricao(codigo), codigo


def test_o_lote_acervos_guarda_exatamente_as_series_da_lista():
    assert set(lote.SERIES_DO_IPEADATA) == set(ipea.SERIES)
    urls = [
        a.url
        for a in lote.descobrir_series_do_ipeadata(_Servidor(), AGORA)  # type: ignore[arg-type]
    ]
    assert len(urls) == len(ipea.SERIES) == len(set(urls))
    assert all(a.startswith(lote.RAIZ_DO_IPEADATA) for a in urls)


def test_a_marca_continua_a_confirmar_vendavel_citando_a_fonte():
    for id_ in ("ipea-odata-series", "ipea-odata-metadados"):
        assert revenda_da_fonte(id_) == VENDAVEL_RISCO_ASSUMIDO
    assert {f.id for f in todas_as_fontes.FONTES} >= {
        "ipea-odata-series",
        "ipea-odata-metadados",
    }
