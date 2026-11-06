"""Lote CVM (base/arquivo/lote_cvm.py): fundos 555, FII, FIP, securitizadoras, fundos estruturados e
arrecadação do portal de dados abertos. Nada vai à internet: as respostas do `package_show` são dublês
de `tests/arquivos/cvm_lote/`. O que não pode faltar aqui é a LGPD: cadastro com pessoa não entra."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from base.arquivo import destinos, fontes
from base.arquivo import lote_cvm as lote
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from src.banco.coletas import SEM_LICENCA_CONHECIDA, licenca_da_fonte

AGORA = datetime(2026, 10, 23, 4, tzinfo=UTC)
PASTA = Path(__file__).parent / "arquivos" / "cvm_lote"
PACOTES_COM_PESSOA = {
    "invnr-cad",
    "adm_cart-cad",
    "crowdfunding-cad",
    "fi-cad",
    "emissor_cepac-cad",
    "cia_incent-cad",
    "ato_declr-intermed",
    "agente_auton-cad",
    "consultor_vlmob-cad",
}
PACOTES_SEM_ARQUIVO = {"distrpubl", "emissores"}


class Portal:
    """Um cliente de mentira: responde ao `package_show` com o JSON gravado."""

    def __init__(self, respostas: dict[str, bytes]):
        self.respostas = respostas
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        return Resposta(url, self.respostas[url.rsplit("=", 1)[-1]], {})


def _gravado(nome: str) -> bytes:
    return (PASTA / f"{nome}.json").read_bytes()


def _alvos(fonte, nome: str) -> list[str]:
    pacote = json.loads(_gravado(nome))["result"]["name"]
    portal = Portal({pacote: _gravado(nome)})
    return [a.url for a in fonte.descobrir(portal, AGORA)]


def _fonte(id_: str):
    return next(f for f in lote.fontes() if f.id == id_)


def test_nenhum_id_repetido_nem_igual_ao_de_outro_lote():
    ids = [f.id for f in lote.fontes()]
    assert len(ids) == len(set(ids))
    todos = [f.id for f in fontes.FONTES]
    assert len(todos) == len(set(todos))
    assert set(ids) <= set(todos)


def test_so_cvm_e_so_pacotes_sem_pessoa():
    usados = {p for _, _, pacotes in lote.PACOTES.values() for p in pacotes}
    assert not usados & PACOTES_COM_PESSOA
    assert not usados & PACOTES_SEM_ARQUIVO
    assert all(i.startswith("cvm-") for i in lote.PACOTES)


@pytest.mark.parametrize(
    ("id_", "nome"),
    [
        ("cvm-fundos-informe-diario", "fundo-555"),
        ("cvm-fii-mensal", "fii"),
        ("cvm-securitizadoras-ots", "securitizadora"),
        ("cvm-fii-administradores", "cadastro"),
    ],
)
def test_descobre_os_arquivos_do_pacote(id_, nome):
    urls = _alvos(_fonte(id_), nome)
    assert urls
    assert all(u.startswith("https://dados.cvm.gov.br/dados/") for u in urls)


def test_arrecadacao_ignora_a_pagina_html_e_fica_com_o_csv():
    urls = _alvos(_fonte("cvm-arrecadacao"), "arrecadacao")
    assert len(urls) == 1
    assert "consulta/baixar" in urls[0]


def test_pacote_sem_arquivo_e_erro_com_o_nome_dele():
    vazio = json.dumps({"result": {"resources": []}}).encode()
    portal = Portal({"fi-doc-lamina": vazio})
    with pytest.raises(ErroDeDescoberta, match="fi-doc-lamina"):
        _fonte("cvm-fundos-lamina").descobrir(portal, AGORA)


def test_as_grandes_sao_pesadas_e_o_resto_nao():
    pesadas = {f.id for f in lote.fontes() if f.pesada}
    assert pesadas == {
        "cvm-fundos-informe-diario",
        "cvm-fundos-balancete",
        "cvm-fundos-entrega",
    }
    assert {f.grupo for f in lote.fontes()} <= {"semanal", "mensal"}


# fontes do lote que já viraram tabela na base (informe mensal de CRI/CRA/OTS, B-16)
JA_NA_BASE = {"cvm-securitizadoras-ots"}


def test_toda_fonte_nova_tem_licenca_conhecida_e_destino_planejado():
    for f in lote.fontes():
        assert licenca_da_fonte(f.id) != SEM_LICENCA_CONHECIDA
        if f.id in JA_NA_BASE:
            assert destinos.DESTINOS[f.id].tipo == destinos.TABELA
            continue
        assert destinos.DESTINOS[f.id].tipo == destinos.PLANEJADA
        assert destinos.DESTINOS[f.id].porque


def test_informe_diario_e_fii_apontam_para_o_lote_2():
    assert "cota-por-fundo" in destinos.DESTINOS["cvm-fundos-informe-diario"].onde
    for id_ in ("cvm-fii-mensal", "cvm-fii-trimestral", "cvm-fii-anual"):
        assert "tela-de-fii" in destinos.DESTINOS[id_].onde
