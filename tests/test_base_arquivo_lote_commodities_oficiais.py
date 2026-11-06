"""Lote commodities oficiais (base/arquivo/lote_commodities_oficiais.py): DG AGRI e, nos PRs seguintes, as outras
fontes oficiais da linha 396 da fila. Nada vai à internet: a descoberta só monta endereços e não pede nada."""

from datetime import UTC, datetime

import pytest

from base.arquivo import fontes
from base.arquivo import lote_commodities_oficiais as lote
from base.arquivo.coleta import Fonte
from src.banco.coletas import SEM_LICENCA_CONHECIDA, licenca_da_fonte, revenda_da_fonte

AGORA = datetime(2026, 11, 5, 22, tzinfo=UTC)
PORTAL = "https://ec.europa.eu/agrifood/api"


def _fonte(id_: str) -> Fonte:
    return next(f for f in lote.fontes() if f.id == id_)


def _alvos(id_: str):
    # a descoberta do DG AGRI só monta endereços: o cliente nunca é chamado
    return _fonte(id_).descobrir(None, AGORA)  # type: ignore[arg-type]


def test_nenhum_id_repetido_e_todos_estao_no_registro_do_arquivista():
    ids = [f.id for f in lote.fontes()]
    assert len(ids) == len(set(ids))
    todos = [f.id for f in fontes.FONTES]
    assert len(todos) == len(set(todos))
    assert set(ids) <= set(todos)


def test_toda_fonte_do_lote_tem_licenca_e_revenda_conhecidas():
    for f in lote.fontes():
        assert licenca_da_fonte(f.id) != SEM_LICENCA_CONHECIDA, f.id
        assert revenda_da_fonte(f.id) is not None, f.id


@pytest.mark.parametrize(
    ("produto", "primeiro_ano"), [("cereal", 2015), ("oilseeds", 2021), ("dairy", 1991)]
)
def test_dgagri_vira_uma_janela_por_ano_do_primeiro_dado_ate_o_ano_da_coleta(
    produto, primeiro_ano
):
    urls = [a.url for a in _alvos(f"dgagri-{produto}")]
    assert urls[0] == (
        f"{PORTAL}/{produto}/prices?beginDate=01/01/{primeiro_ano}"
        f"&endDate=31/12/{primeiro_ano}"
    )
    assert urls[-1].endswith(f"beginDate=01/01/{AGORA.year}&endDate=31/12/{AGORA.year}")
    assert len(urls) == AGORA.year - primeiro_ano + 1
    assert len(set(urls)) == len(urls)


def test_dgagri_ano_fechado_so_e_relido_uma_vez_por_ano_e_o_corrente_sempre():
    """Ano fechado leva `versao` (a descoberta já sabe, então não repete 10 MB por dia); o ano corrente muda toda semana."""
    alvos = _alvos("dgagri-cereal")
    fechados, corrente = alvos[:-1], alvos[-1]
    assert corrente.versao is None
    assert all(a.versao for a in fechados)
    assert len({a.versao for a in fechados}) == len(fechados)
    # virou o ano: o ano que fechou é relido uma vez (revisão tardia do país), com versão nova
    depois = _fonte("dgagri-cereal").descobrir(None, datetime(2027, 1, 10, tzinfo=UTC))  # type: ignore[arg-type]
    ano_2026_antes = next(a for a in alvos if "01/01/2026" in a.url)
    ano_2026_depois = next(a for a in depois if "01/01/2026" in a.url)
    assert ano_2026_antes.versao is None
    assert ano_2026_depois.versao


def test_dgagri_ano_sem_dado_e_nao_encontrado_e_nunca_falha():
    """O portal responde 404 para o ano em que o produto ainda não existe: é `SemArquivo`, não falha."""
    for id_ in ("dgagri-cereal", "dgagri-oilseeds", "dgagri-dairy"):
        assert all(a.obter is not None for a in _alvos(id_)), id_


def test_dgagri_acucar_e_um_retrato_so_porque_a_api_ignora_as_datas():
    alvos = _alvos("dgagri-sugar")
    assert [a.url for a in alvos] == [f"{PORTAL}/sugar/prices"]


def test_dgagri_nao_leva_carne_porque_o_endereco_dela_responde_404():
    assert "dgagri-meat" not in {f.id for f in lote.fontes()}
    assert "dgagri-beef" not in {f.id for f in lote.fontes()}


def test_dgagri_e_json_leve_semanal_e_com_pausa_entre_pedidos():
    for f in lote.fontes():
        assert f.tipo == "json", f.id
        assert f.grupo == "semanal", f.id
        assert not f.pesada, f.id
        assert f.pausa_minima >= 1.0, f.id


def test_dgagri_nao_filtra_por_pais_porque_a_licenca_e_da_comissao_para_todos_os_estados():
    for f in lote.fontes():
        for a in f.descobrir(None, AGORA):  # type: ignore[arg-type]
            assert "memberStateCodes" not in a.url
