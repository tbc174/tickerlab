"""A CONAB no arquivista: descobrir as planilhas de cada levantamento e o destino da fonte."""

from datetime import UTC, datetime

import pytest

from base.arquivo import destinos, fontes
from base.arquivo.coleta import ErroDeDescoberta, Resposta

SAFRA = "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-cafe/"
AGORA = datetime(2026, 10, 18, 5, tzinfo=UTC)


class Paginas:
    def __init__(self, paginas: dict[str, str]):
        self.paginas = paginas

    def ler(self, url, **_):
        return Resposta(url, self.paginas[url].encode(), {})


def _link(caminho: str) -> str:
    return f'<a href="{SAFRA}{caminho}">x</a>'


PAGINA_ATUAL = "".join(
    [
        _link("3o-levantamento-de-cafe-safra-2026/3o-levantamento-de-cafe-safra-2026"),
        _link(
            "3o-levantamento-de-cafe-safra-2026/site_previsao-de-safra-cafe-set-2026.xls"
        ),
        _link("3o-levantamento-de-cafe-safra-2026/boletim-de-safras-cafe-set_26.pdf"),
    ]
)
PAGINA_ANTIGA = "".join(
    [
        _link(
            "3o-levantamento-de-cafe-safra-2024/tabela-de-dados-estimativas-da-producao-e-colheita"
        ),
        _link("3o-levantamento-de-cafe-safra-2024/boletim-cafe-setembro-2024"),
    ]
)
PAGINAS = Paginas(
    {
        fontes.PAGINA_DOS_LEVANTAMENTOS_DA_CONAB: PAGINA_ATUAL,
        fontes.PAGINA_ANTIGA_DA_CONAB: PAGINA_ANTIGA,
    }
)


def test_descobre_so_a_planilha_de_cada_levantamento_atual_e_antigo():
    urls = [a.url for a in fontes.descobrir_cafe_conab(PAGINAS, AGORA)]
    assert urls == [
        SAFRA
        + "3o-levantamento-de-cafe-safra-2026/site_previsao-de-safra-cafe-set-2026.xls",
        SAFRA
        + "3o-levantamento-de-cafe-safra-2024/tabela-de-dados-estimativas-da-producao-e-colheita",
    ]


def test_sem_nenhuma_planilha_e_erro_de_descoberta():
    vazias = Paginas({p: "<html></html>" for p in PAGINAS.paginas})
    with pytest.raises(ErroDeDescoberta):
        fontes.descobrir_cafe_conab(vazias, AGORA)


def test_a_fonte_esta_na_lista_e_vira_tabela():
    assert "conab-cafe-safra" in fontes.POR_ID
    assert destinos.DESTINOS["conab-cafe-safra"].tabelas == ("conab_cafe",)
