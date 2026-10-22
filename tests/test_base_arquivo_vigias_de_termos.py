"""Vigias de termos (linha 124 da fila): toda família com licença registrada tem vigia ou um motivo escrito."""

from datetime import date

import pytest

from base.arquivo.fontes import CATALOGOS, FONTES, TERMOS
from base.arquivo.registro import TERMOS_LIDOS_EM
from src.banco.coletas import LICENCAS

# id do vigia (depois de "termos-") → família do `LICENCAS` cujo termo ele vigia, quando os nomes diferem
_FAMILIA_DO_VIGIA = {"banco-mundial": "bm", "igc": "assessoria", "cnpj": "rfb-cnpj"}

_FONTES_NOVAS = {
    "termos-kraken": "kraken",
    "termos-yahoo": "yahoo",
    "termos-gdelt": "gdelt",
    "termos-gleif": "gleif",
    "termos-faostat": "faostat",
    "termos-chirps": "chirps",
    "termos-mapbiomas": "mapbiomas",
    "termos-iex": "iex",
    "termos-banco-mundial": "bm",
}

# família sem vigia de termos → por quê (o motivo precisa ser verdadeiro hoje; trocar por vigia quando mudar)
_SEM_VIGIA = {
    # licença dita no catálogo do dados.gov.br ou no portal CKAN, sem página de termos própria
    **dict.fromkeys(
        (
            "anac",
            "anatel",
            "aneel",
            "anp",
            "ans",
            "antt",
            "susep",
            "ibama",
            "mte",
            "ons",
            "cvm",
            "bcb",
            "tesouro",
            "tesouro-br",
            "tesouro-br-direto",
            "tesouro-br-divida",
            "tesouro-br-leiloes",
            "tce-pr",
            "tce-pr-despesa",
            "tce-pr-pit",
            "tce-rs",
            "tce-rs-empenhos",
            "cgu",
            "pgfn",
            "conab",
            "comexstat",
        ),
        "a licença está na ficha do catálogo ou no rodapé do portal, não numa página de termos",
    ),
    "bcb-sgs-189": "a licença é da FGV IBRE (IGP-M), sem página própria lida",
    # a página de termos não abre com o nosso agente; não se contorna (fila)
    "fmi": "imf.org responde 403 (Akamai) ao nosso agente",
    "ccee": "dadosabertos.ccee.org.br responde 403 ao nosso agente",
    "mb": "mercadobitcoin.com.br/termos-de-uso respondeu 403 ao leitor",
    "wayback": "a página de termos do Internet Archive veio vazia",
    "cftc": "a página de política da CFTC deu 404 (domínio público, obra do governo dos EUA)",
    "usda": "usda.gov e fas.usda.gov respondem 403 (domínio público pela política do USDA)",
    "ico": "ico.org não publica termos, só o aviso de copyright",
    # não há página de termos de terceiro a vigiar
    "btc": "nó próprio, sem terceiro",
    "rfb": "a página da Receita pede login",
    "wiki": "a documentação da API deu 502 e as páginas lidas não dizem a licença",
    "termos": "são as próprias cópias das páginas vigiadas",
    "contrapartes": "páginas de terceiros guardadas como prova, sem coleta recorrente do termo",
}


def _familias_vigiadas() -> set[str]:
    familias = {"catalogo"} if CATALOGOS else set()
    for fonte in FONTES:
        if fonte.vigia and fonte.id.startswith("termos-"):
            nome = fonte.id.removeprefix("termos-")
            primeiro = nome.split("-", 1)[0]
            familias.add(
                _FAMILIA_DO_VIGIA.get(nome) or _FAMILIA_DO_VIGIA.get(primeiro, primeiro)
            )
    return familias


@pytest.mark.parametrize("vigia, familia", sorted(_FONTES_NOVAS.items()))
def test_vigia_novo_tem_endereco_e_a_familia_tem_data_de_leitura(vigia, familia):
    assert TERMOS[vigia].startswith("https://")
    assert TERMOS_LIDOS_EM[familia] == date(2026, 10, 21)
    assert vigia in {f.id for f in FONTES if f.vigia}


def test_toda_familia_de_licenca_tem_vigia_ou_motivo_escrito():
    vigiadas = _familias_vigiadas()
    sem_nada = sorted(f for f in LICENCAS if f not in vigiadas and f not in _SEM_VIGIA)
    assert not sem_nada, (
        f"família sem vigia de termos e sem motivo em _SEM_VIGIA: {sem_nada}"
    )


def test_o_motivo_escrito_nao_sobra_numa_familia_que_ja_tem_vigia():
    vigiadas = _familias_vigiadas()
    assert sorted(f for f in _SEM_VIGIA if f in vigiadas) == []
    assert sorted(f for f in _SEM_VIGIA if f not in LICENCAS) == []
