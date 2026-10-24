"""Lote reguladores (base/arquivo/lote_reguladores.py): pacotes de energia da ANEEL, do ONS e da CCEE que o lote
setoriais não guarda. Nada vai à internet: as respostas do `package_show` são dublês de
`tests/arquivos/reguladores/`. O que não pode faltar aqui é a LGPD: dado por titular ou beneficiário não entra."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from base.arquivo import destinos, fontes
from base.arquivo import lote_reguladores as lote
from base.arquivo import lote_setoriais as setoriais
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from src.banco.coletas import SEM_LICENCA_CONHECIDA, licenca_da_fonte, revenda_da_fonte

AGORA = datetime(2026, 10, 23, 23, tzinfo=UTC)
PASTA = Path(__file__).parent / "arquivos" / "reguladores"
PACOTES_DE_PESSOA = {
    "relacao-de-empreendimentos-de-geracao-distribuida",
    "tarifa-social-de-energia-eletrica-beneficiarios",
    "beneficiarios-da-cde",
    "agentes-de-geracao-de-energia-eletrica",
    "bdgd",
    "programacao_diaria",
    "lista_agente_associado",
    "lista_perfil",
    "varejista_consumidor",
    "mve_contrapartes",
}


class Portal:
    """Um cliente de mentira: responde ao `package_show` com o gravado."""

    def __init__(self, respostas: dict[str, bytes]):
        self.respostas = respostas
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        return Resposta(url, self.respostas[url.rsplit("=", 1)[-1]], {})


def _gravado(nome: str) -> bytes:
    return (PASTA / nome).read_bytes()


def _fonte(id_: str):
    return next(f for f in lote.fontes() if f.id == id_)


def _todos_os_pacotes() -> list[str]:
    ons = [p for _, pacotes, _ in lote.PACOTES_DO_ONS.values() for p in pacotes]
    ccee = [p for _, pacotes, _ in lote.PACOTES_DA_CCEE.values() for p in pacotes]
    aneel = [p for pacotes in lote.PACOTES_DA_ANEEL.values() for p in pacotes]
    return [*aneel, *ons, *ccee]


def test_nenhum_id_repetido_nem_igual_ao_de_outro_lote():
    ids = [f.id for f in lote.fontes()]
    assert len(ids) == len(set(ids))
    todos = [f.id for f in fontes.FONTES]
    assert len(todos) == len(set(todos))
    assert set(ids) <= set(todos)


def test_nenhum_pacote_repetido_nem_ja_guardado_pelo_lote_setoriais():
    pacotes = _todos_os_pacotes()
    assert len(pacotes) == len(set(pacotes))
    ja_guardados = {
        *(p for ps in setoriais.PACOTES_DA_ANEEL.values() for p in ps),
        *(p for ps in setoriais.PACOTES_DO_ONS.values() for p in ps),
        *(p for ps in setoriais.PACOTES_DA_CCEE.values() for p in ps),
        "pld_horario",
        "pld_media_diaria",
        "pld_media_mensal",
    }
    assert not set(pacotes) & ja_guardados


def test_nenhum_pacote_traz_dado_por_pessoa_nem_o_que_foi_barrado_por_volume():
    assert not set(_todos_os_pacotes()) & PACOTES_DE_PESSOA


def test_id_comeca_pela_familia_que_ja_tem_licenca_e_revenda():
    for f in lote.fontes():
        assert f.id.split("-", 1)[0] in {"aneel", "ons", "ccee"}
        assert licenca_da_fonte(f.id) != SEM_LICENCA_CONHECIDA
        assert revenda_da_fonte(f.id) is not None


def test_aneel_pega_o_csv_e_deixa_o_xml():
    portal = Portal(
        {"indqual-inadimplencia": _gravado("aneel_indqual-inadimplencia.json")}
    )
    alvos = _fonte("aneel-inadimplencia").descobrir(portal, AGORA)
    assert [a.url.rsplit("/", 1)[-1] for a in alvos] == [
        "dm-inadimplencia.pdf",
        "inadimplencia.csv",
        "dominio-indicadores.csv",
    ]
    assert "package_show?id=indqual-inadimplencia" in portal.pedidos[0]


def test_ons_pega_o_csv_do_ano_e_deixa_parquet_e_xlsx():
    portal = Portal({"demanda_maxima_di": _gravado("ons_demanda_maxima_di.json")})
    alvos = _fonte("ons-demanda-maxima").descobrir(portal, AGORA)
    assert [a.url.rsplit("/", 1)[-1] for a in alvos] == [
        "DEMANDA_MAXIMA_DI_2026.csv",
        "dicionario.pdf",
    ]


def test_ccee_pede_ao_portal_da_ccee_e_leva_todo_arquivo():
    portal = Portal(
        {
            p: _gravado("ccee_pldx_valor_anual.json")
            for p in ("pldx_valor_anual", "pld_sombra")
        }
    )
    alvos = _fonte("ccee-preco-futuro").descobrir(portal, AGORA)
    assert all(p.startswith(setoriais.PORTAL_DA_CCEE) for p in portal.pedidos)
    assert len(alvos) == 2


def test_pacote_sem_arquivo_e_erro_com_o_nome_dele():
    portal = Portal(
        {
            "pldx_valor_anual": _gravado("ccee_pldx_valor_anual.json"),
            "pld_sombra": _gravado("ccee_sem_arquivo.json"),
        }
    )
    with pytest.raises(ErroDeDescoberta, match="pld_sombra"):
        _fonte("ccee-preco-futuro").descobrir(portal, AGORA)


def test_ritmo_pelo_calendario_e_pesadas_so_as_grandes_do_ons_e_da_ccee():
    ritmos = {f.id: f.grupo for f in lote.fontes()}
    assert ritmos["ons-demanda-maxima"] == "diaria"
    assert ritmos["ons-cmo-semi-horario"] == "diaria"
    assert ritmos["aneel-encargos"] == "mensal"
    assert ritmos["ccee-risco-hidrologico"] == "mensal"
    assert {f.id for f in lote.fontes() if f.pesada} == {
        "ons-hidrologia-detalhe",
        "ons-cmo-semi-horario",
        "ons-disponibilidade",
        "ccee-consumo-horario",
    }


def test_toda_fonte_nova_tem_destino_e_o_gsf_e_planejado():
    for f in lote.fontes():
        assert f.id in destinos.DESTINOS
    gsf = destinos.DESTINOS["ccee-risco-hidrologico"]
    assert gsf.tipo == destinos.PLANEJADA
    assert gsf.onde == "hidreletricas/gsf"
    assert destinos.DESTINOS["ons-itaipu"].tipo == destinos.SO_PESQUISA
