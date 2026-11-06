"""Lote BCB e SICONFI do arquivista (base/arquivo/lote_bcb.py): sem internet, com dublês."""

import json
from contextlib import contextmanager
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base.arquivo import lote_bcb
from base.arquivo.coleta import ErroDeDescoberta, Resposta, SemArquivo
from base.arquivo.fontes import FONTES, POR_ID
from base.arquivo.registro import registro_de_fontes
from src.banco.coletas import (
    SEM_LICENCA_CONHECIDA,
    Marca,
    licenca_da_fonte,
    marca_da_fonte,
)

AGORA = datetime(2026, 10, 22, 15, tzinfo=UTC)
JANEIRO = datetime(2027, 1, 12, 15, tzinfo=UTC)
IDS_DO_LOTE = [f.id for f in lote_bcb.fontes(lambda: ["60746948"])]


class Cliente:
    """Responde `ler` (páginas do SICONFI) e `baixar` (arquivos) com conteúdo fixo."""

    def __init__(self, paginas=None, arquivos=None):
        self.paginas = paginas or {}
        self.arquivos = arquivos or {}
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        return Resposta(url, json.dumps(self.paginas[url]).encode(), {"ETag": "x"})

    def baixar(self, url, destino):
        destino.write_bytes(self.arquivos[url])
        return {"Content-Type": "application/json"}


def _ente(codigo, esfera="M", capital="0  "):
    return {"cod_ibge": codigo, "esfera": esfera, "capital": capital, "ente": "x"}


def _pagina_de_entes(entes, mais=False):
    return {"items": entes, "hasMore": mais, "limit": 5000}


def _com_paginas(url, *paginas):
    """As páginas do dublê: `url` com `limit` e `offset` crescendo pelo número de itens já lidos."""
    pedidos, lidos = {}, 0
    for pagina in paginas:
        pedidos[f"{url}{'&' if '?' in url else '?'}limit=5000&offset={lidos}"] = pagina
        lidos += len(pagina["items"])
    return pedidos


# --- Olinda ---------------------------------------------------------------------------------------


def test_olinda_com_dados_guarda_a_lista(tmp_path):
    url = "https://olinda.bcb.gov.br/x"
    cliente = Cliente(arquivos={url: json.dumps({"value": [{"a": 1}]}).encode()})
    destino = tmp_path / "x.json"
    cabecalhos = lote_bcb.olinda_com_dados(url)(cliente, destino)
    assert json.loads(destino.read_bytes()) == {"value": [{"a": 1}]}
    assert cabecalhos == {"Content-Type": "application/json"}


def test_olinda_com_lista_vazia_e_sem_arquivo_nao_ok(tmp_path):
    url = "https://olinda.bcb.gov.br/x"
    cliente = Cliente(arquivos={url: b'{"value": []}'})
    with pytest.raises(SemArquivo):
        lote_bcb.olinda_com_dados(url)(cliente, tmp_path / "x.json")


def test_olinda_que_devolve_erro_nao_e_sem_arquivo(tmp_path):
    url = "https://olinda.bcb.gov.br/x"
    cliente = Cliente(arquivos={url: b'/*{ "codigo" : 500 }*/'})
    with pytest.raises(ValueError, match="value"):
        lote_bcb.olinda_com_dados(url)(cliente, tmp_path / "x.json")


def test_str_tem_um_alvo_por_entidade():
    alvos = lote_bcb.descobrir_str(Cliente(), AGORA)
    assert len(alvos) == len(lote_bcb.ENTIDADES_DO_STR) == 7
    assert alvos[0].url == (
        "https://olinda.bcb.gov.br/olinda/servico/STR/versao/v1/odata/"
        "GiroEvolucaoDiaria?$format=json"
    )


def test_consorcios_pedem_so_fins_de_trimestre_e_o_dicionario():
    alvos = lote_bcb.descobrir_consorcios(Cliente(), AGORA)
    meses = [a.url.split("@DataBase=")[1][:6] for a in alvos if "@DataBase=" in a.url]
    assert meses == [
        "202412",
        "202503",
        "202506",
        "202509",
        "202512",
        "202603",
        "202606",
        "202609",
    ]
    dicionarios = [a.url for a in alvos if "@DataBase=" not in a.url]
    assert len(dicionarios) == 2
    assert all(a.obter is None for a in alvos if "@DataBase=" not in a.url)
    assert all(a.obter is not None for a in alvos if "@DataBase=" in a.url)


def test_trimestres_fechados_atravessam_o_ano():
    assert lote_bcb.trimestres_fechados(datetime(2026, 2, 1, tzinfo=UTC), 3) == [
        "202506",
        "202509",
        "202512",
    ]


def test_leiloes_pedem_a_serie_toda_de_titulos_e_de_swap():
    alvos = lote_bcb.descobrir_leiloes(Cliente(), AGORA)
    assert [("leiloesTitulosPublicos" in a.url, "Swap" in a.url) for a in alvos] == [
        (True, False),
        (False, True),
    ]
    assert all("@a='2000-01-01'" in a.url and "@b='2099-12-31'" in a.url for a in alvos)


# --- bancos listados: tarifas e COSIF -------------------------------------------------------------


def test_meses_fechados_do_cosif_vao_do_mais_antigo_ao_ultimo_mes_fechado():
    meses = lote_bcb.meses_fechados(AGORA, 12)
    assert meses[0] == "202510" and meses[-1] == "202609" and len(meses) == 12
    assert lote_bcb.meses_fechados(datetime(2026, 1, 5, tzinfo=UTC), 2) == [
        "202511",
        "202512",
    ]


def test_cosif_pede_um_zip_por_banco_e_mes_e_404_vira_sem_arquivo():
    fonte = POR_ID["bcb-cosif"]
    assert fonte.tipo == "zip" and fonte.grupo == "mensal"
    fonte = next(
        f
        for f in lote_bcb.fontes(lambda: ["60746948", "00000000"])
        if f.id == "bcb-cosif"
    )
    alvos = fonte.descobrir(Cliente(), AGORA)
    assert len(alvos) == 2 * lote_bcb.MESES_DO_COSIF
    assert alvos[0].url == (
        "https://www4.bcb.gov.br/fis/cosif/cont/balan/individualizados/"
        "202510/4010/202510-4010-60746948.ZIP"
    )
    assert alvos[0].extensao == ".zip" and alvos[0].obter is not None


def test_tarifas_pedem_uma_lista_por_banco_e_lista_vazia_e_sem_arquivo():
    fonte = next(
        f
        for f in lote_bcb.fontes(lambda: ["60746948", "90400888"])
        if f.id == "bcb-tarifas-instituicao"
    )
    alvos = fonte.descobrir(Cliente(), AGORA)
    assert [a.url.split("@c='")[1][:8] for a in alvos] == ["60746948", "90400888"]
    assert all(a.obter is not None for a in alvos)


def test_sem_cadastro_da_cvm_a_descoberta_dos_bancos_falha():
    for fonte in lote_bcb.fontes(list):
        if fonte.id in ("bcb-cosif", "bcb-tarifas-instituicao"):
            with pytest.raises(ErroDeDescoberta, match="banco"):
                fonte.descobrir(Cliente(), AGORA)


def test_so_banco_ativo_do_setor_bancos_entra_pela_raiz_do_cnpj(monkeypatch):
    cadastro = pd.DataFrame(
        {
            "cnpj": [
                "60.746.948/0001-12",
                "60.746.948/0001-12",
                "00.000.000/0001-91",
                "11.111.111/0001-00",
                "22.222.222/0001-00",
            ],
            "setor": ["Bancos", "Bancos", "Bancos", "Bancos", "Energia Elétrica"],
            "situacao": ["ATIVO", "ATIVO", "ATIVO", "CANCELADA", "ATIVO"],
        }
    )

    class Motor:
        @contextmanager
        def connect(self):
            yield "conexao"

    monkeypatch.setattr(lote_bcb, "obter_engine", Motor)
    monkeypatch.setattr(
        lote_bcb, "cadastro_do_acervo", lambda conexao: (cadastro, {"url": "u"})
    )
    assert lote_bcb.cnpjs_dos_bancos_listados() == ["00000000", "60746948"]


def test_sem_cadastro_guardado_a_lista_de_bancos_e_vazia(monkeypatch):
    class Motor:
        @contextmanager
        def connect(self):
            yield "conexao"

    monkeypatch.setattr(lote_bcb, "obter_engine", Motor)
    monkeypatch.setattr(lote_bcb, "cadastro_do_acervo", lambda conexao: None)
    assert lote_bcb.cnpjs_dos_bancos_listados() == []


# --- SICONFI --------------------------------------------------------------------------------------


def test_siconfi_pagina_ate_acabar_e_soma_os_itens():
    url = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/entes"
    cliente = Cliente(
        _com_paginas(
            url,
            _pagina_de_entes([_ente(1), _ente(2)], mais=True),
            _pagina_de_entes([_ente(3)]),
        )
    )
    itens, cabecalhos = lote_bcb.itens_do_siconfi(cliente, url)
    assert [i["cod_ibge"] for i in itens] == [1, 2, 3]
    assert cliente.pedidos[1].endswith("limit=5000&offset=2")
    assert cabecalhos == {"ETag": "x"}


def test_siconfi_com_pergunta_na_url_continua_com_e_comercial():
    url = lote_bcb.DCA.format(ano=2025, ente=35)
    cliente = Cliente(_com_paginas(url, _pagina_de_entes([_ente(1)])))
    lote_bcb.itens_do_siconfi(cliente, url)
    assert cliente.pedidos == [f"{url}&limit=5000&offset=0"]


def test_siconfi_que_nunca_para_de_paginar_falha():
    url = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/entes"
    cliente = Cliente(
        {
            f"{url}?limit=5000&offset={n}": _pagina_de_entes([_ente(n)], mais=True)
            for n in range(lote_bcb.MAXIMO_DE_PAGINAS + 1)
        }
    )
    with pytest.raises(ValueError, match="páginas"):
        lote_bcb.itens_do_siconfi(cliente, url)


def test_siconfi_guarda_so_os_itens_sem_os_links_da_oracle(tmp_path):
    url = lote_bcb.DCA.format(ano=2025, ente=35)
    pagina = {
        "items": [{"cod_ibge": 35, "valor": 1.5, "conta": "Ativo ç"}],
        "hasMore": False,
        "links": [{"rel": "self", "href": "http://host-interno.oracle/ords/x"}],
    }
    cliente = Cliente(_com_paginas(url, pagina))
    destino = tmp_path / "dca.json"
    lote_bcb.siconfi_em_json(url)(cliente, destino)
    guardado = json.loads(destino.read_text(encoding="utf-8"))
    assert guardado == {"items": pagina["items"]}
    assert "oracle" not in destino.read_text(encoding="utf-8")


def test_siconfi_sem_item_e_sem_arquivo(tmp_path):
    url = lote_bcb.RREO.format(ano=2026, periodo=5, ente=35)
    cliente = Cliente(_com_paginas(url, _pagina_de_entes([])))
    with pytest.raises(SemArquivo):
        lote_bcb.siconfi_em_json(url)(cliente, tmp_path / "rreo.json")
    assert not (tmp_path / "rreo.json").exists()


def test_estados_df_e_capitais_sao_os_entes_de_interesse():
    entes = [
        _ente(35, "E"),
        _ente(53, "D"),
        _ente(3550308, "M", "1  "),
        _ente(3509502, "M", "0  "),
        _ente(1, "U"),
        _ente(11, "E"),
    ]
    assert lote_bcb.codigos_de_estados_e_capitais(entes) == [11, 35, 53, 3550308]


def test_rreo_so_pede_bimestre_que_ja_fechou_e_o_ano_passado_inteiro():
    urls = lote_bcb.urls_do_rreo(35, AGORA)
    periodos_de_2026 = [u for u in urls if "an_exercicio=2026" in u]
    assert len(periodos_de_2026) == 4  # em outubro: bimestres 1 a 4 (agosto fechou)
    assert len([u for u in urls if "an_exercicio=2025" in u]) == 6
    assert urls[-1].endswith("nr_periodo=4&co_tipo_demonstrativo=RREO&id_ente=35")


def test_rgf_e_quadrimestral_e_do_poder_executivo():
    urls = lote_bcb.urls_do_rgf(35, AGORA)
    assert len([u for u in urls if "an_exercicio=2026" in u]) == 2
    assert len([u for u in urls if "an_exercicio=2025" in u]) == 3
    assert all("in_periodicidade=Q" in u and "co_poder=E" in u for u in urls)


def test_em_janeiro_so_o_ano_passado_tem_rreo_e_rgf():
    assert all("an_exercicio=2026" in u for u in lote_bcb.urls_do_rreo(35, JANEIRO))
    assert len(lote_bcb.urls_do_rreo(35, JANEIRO)) == 6
    assert len(lote_bcb.urls_do_rgf(35, JANEIRO)) == 3


def test_dca_e_extrato_cobrem_os_anos_certos():
    anos_da_dca = [
        u.split("an_exercicio=")[1][:4] for u in lote_bcb.urls_da_dca(35, AGORA)
    ]
    assert anos_da_dca == ["2023", "2024", "2025"]
    entregas = lote_bcb.urls_das_entregas(35, AGORA)
    assert [u.split("an_referencia=")[1][:4] for u in entregas] == ["2025", "2026"]


def test_exercicio_fechado_so_depois_do_prazo_do_ano_passado():
    url = lote_bcb.DCA.format(ano=2025, ente=35)
    assert not lote_bcb.exercicio_fechado(url, date(2026, 4, 30))  # DCA vence em abril
    assert lote_bcb.exercicio_fechado(url, date(2026, 5, 1))
    assert lote_bcb.exercicio_fechado(
        lote_bcb.DCA.format(ano=2024, ente=35), date(2026, 1, 5)
    )
    assert not lote_bcb.exercicio_fechado(
        lote_bcb.DCA.format(ano=2026, ente=35), date(2026, 12, 31)
    )
    assert not lote_bcb.exercicio_fechado(lote_bcb.ENTES, date(2026, 12, 31))


def test_descoberta_do_siconfi_faz_um_alvo_por_ente_e_consulta():
    entes = [_ente(35, "E"), _ente(3550308, "M", "1  "), _ente(3509502)]
    cliente = Cliente(_com_paginas(lote_bcb.ENTES, _pagina_de_entes(entes)))
    fonte = POR_ID["tesouro-br-siconfi-dca"]
    alvos = fonte.descobrir(cliente, AGORA)
    assert len(alvos) == 2 * lote_bcb.ANOS_DA_DCA
    assert {a.extensao for a in alvos} == {".json"}
    assert all(a.obter is not None for a in alvos)
    assert len({a.url for a in alvos}) == len(alvos)


def test_siconfi_sem_estado_nem_capital_e_falha_de_descoberta():
    cliente = Cliente(_com_paginas(lote_bcb.ENTES, _pagina_de_entes([_ente(3509502)])))
    with pytest.raises(ErroDeDescoberta, match="SICONFI"):
        POR_ID["tesouro-br-siconfi-rreo"].descobrir(cliente, AGORA)


def test_entes_do_siconfi_e_um_alvo_so():
    alvos = POR_ID["tesouro-br-siconfi-entes"].descobrir(Cliente(), AGORA)
    assert [a.url for a in alvos] == [lote_bcb.ENTES]


# --- o lote dentro do arquivista ----------------------------------------------------------------


def test_o_lote_tem_onze_fontes_sem_id_repetido():
    assert len(IDS_DO_LOTE) == 11 == len(set(IDS_DO_LOTE))
    ids = [f.id for f in FONTES]
    assert len(ids) == len(set(ids))
    assert set(IDS_DO_LOTE) <= set(ids)


def test_toda_fonte_do_lote_tem_licenca_marca_e_data_de_leitura():
    registro = {r.id: r for r in registro_de_fontes()}
    for id_ in IDS_DO_LOTE:
        assert licenca_da_fonte(id_) != SEM_LICENCA_CONHECIDA, id_
        assert marca_da_fonte(id_) is Marca.VENDAVEL, id_
        assert registro[id_].termos_lidos_em == date(2026, 10, 22), id_


def test_siconfi_nao_herda_a_licenca_dos_eua():
    for id_ in IDS_DO_LOTE:
        assert "Fiscal Data" not in licenca_da_fonte(id_), id_
    assert "SICONFI" in licenca_da_fonte("tesouro-br-siconfi-rreo")


def test_ritmo_e_tipo_de_cada_fonte_do_lote():
    for id_ in IDS_DO_LOTE:
        fonte = POR_ID[id_]
        assert fonte.grupo in ("semanal", "mensal"), id_
        assert fonte.tipo == ("zip" if id_ == "bcb-cosif" else "json"), id_
        assert not fonte.pesada and not fonte.vigia, id_
