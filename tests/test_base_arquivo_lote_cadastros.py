"""Lote cadastros globais (base/arquivo/lote_cadastros.py): golden copy do GLEIF, Wikidata, tickers
da SEC e sanções de empresas (OFAC, UE, OFSI). Nada vai à internet: as respostas são dublês de
`tests/arquivos/cadastros/`. O que não pode faltar aqui é a LGPD: pessoa física nunca chega ao acervo."""

import csv
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from base.arquivo import destinos, fontes
from base.arquivo import lote_cadastros as lote
from base.arquivo.agente import AGENTE
from base.arquivo.coleta import ErroDeDescoberta, Resposta, assinatura
from base.arquivo.registro import TERMOS_LIDOS_EM
from src.banco.coletas import (
    SEM_LICENCA_CONHECIDA,
    Marca,
    licenca_da_fonte,
    marca_da_fonte,
)

AGORA = datetime(2026, 10, 23, 4, tzinfo=UTC)
PASTA = Path(__file__).parent / "arquivos" / "cadastros"
FAMILIAS_NOVAS = {"wikidata", "ofac", "eufsf", "ofsi"}
CABECALHOS_DO_ZIP = {
    "ETag": '"1e272f88-65e77f944ffba"',
    "Last-Modified": "Fri, 23 Oct 2026 01:33:56 GMT",
    "Content-Length": "505884552",
}
URL_DO_LEI2 = (
    "https://goldencopy.gleif.org/storage/golden-copy-files/2026/10/23/1291880/"
    "20261023-0000-gleif-goldencopy-lei2-golden-copy.csv.zip"
)


class Fonte:
    """Um cliente de mentira: `ler` e `cabecalhos` por endereço; `baixar` grava os bytes de `arquivos`."""

    def __init__(self, paginas=None, cabecalhos=None, arquivos=None):
        self.paginas = paginas or {}
        self.respostas_de_cabecalhos = cabecalhos or {}
        self.arquivos = arquivos or {}
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        return Resposta(url, self.paginas[url], {})

    def cabecalhos(self, url):
        return self.respostas_de_cabecalhos.get(url, {})

    def baixar(self, url, destino: Path):
        self.pedidos.append(url)
        destino.write_bytes(self.arquivos[url])
        return self.respostas_de_cabecalhos.get(url, {})


def _fixture(nome: str) -> bytes:
    return (PASTA / nome).read_bytes()


def _zip_do_lei2() -> bytes:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as arquivo_zip:
        arquivo_zip.writestr(
            "20261023-0000-gleif-goldencopy-lei2-golden-copy.csv",
            _fixture("lei2_duble.csv"),
        )
    return memoria.getvalue()


def _linhas_do_zip(caminho: Path) -> list[list[str]]:
    with zipfile.ZipFile(caminho) as arquivo_zip:
        (membro,) = arquivo_zip.namelist()
        texto = arquivo_zip.read(membro).decode("utf-8")
    return list(csv.reader(io.StringIO(texto)))


def _fontes_do_lote():
    return lote.fontes()


def _por_id():
    return {f.id: f for f in _fontes_do_lote()}


# ---- o lote como um todo ---------------------------------------------------------------------
def test_ids_sem_duplicata_no_lote_e_no_catalogo():
    ids = [f.id for f in _fontes_do_lote()]
    assert len(ids) == len(set(ids))
    todos = [f.id for f in fontes.FONTES]
    assert len(todos) == len(set(todos))
    assert set(ids) <= set(todos)


def test_toda_fonte_do_lote_tem_licenca_marca_data_da_leitura_e_destino():
    for fonte in _fontes_do_lote():
        familia = fonte.id.split("-", 1)[0]
        assert licenca_da_fonte(fonte.id) != SEM_LICENCA_CONHECIDA, fonte.id
        assert len(licenca_da_fonte(fonte.id)) <= 80, fonte.id
        assert TERMOS_LIDOS_EM[familia].year == 2026, fonte.id
        assert fonte.grupo in fontes.GRUPOS, fonte.id
        assert fonte.id in destinos.DESTINOS, fonte.id
        assert fonte.pausa_minima > 0, fonte.id


def test_todas_as_fontes_do_lote_sao_vendaveis_com_atribuicao():
    # CC0, domínio público, reuso da UE e OGL v3: nenhuma é só interna nem não comercial
    for fonte in _fontes_do_lote():
        assert marca_da_fonte(fonte.id) == Marca.VENDAVEL, fonte.id


def test_as_familias_do_lote():
    familias = {f.id.split("-", 1)[0] for f in _fontes_do_lote()}
    assert familias == FAMILIAS_NOVAS | {"gleif", "sec"}


def test_o_lote_nao_pega_o_que_ficou_de_fora_de_proposito():
    fora = ("opensanctions", "occrp", "icij", "onu", "un", "opencorporates", "openfigi")
    fora += ("bris", "companieshouse", "psc", "bods")
    ids = {f.id for f in _fontes_do_lote()}
    assert not [i for i in ids if any(p in i.split("-") for p in fora)]
    # o que já existia em `fontes.py` ou em outro lote não é coletado duas vezes
    assert not ids & {"gleif-br", "gleif-emissores", "gleif-autoridades-de-registro"}


def test_a_sec_company_tickers_nao_estava_em_outro_lote():
    ids_de_fora = {f.id for f in fontes.FONTES} - {f.id for f in _fontes_do_lote()}
    assert "sec-company-tickers" not in ids_de_fora
    assert not [i for i in ids_de_fora if "company-tickers" in i]


def test_cada_familia_nova_tem_vigia_ou_motivo_e_o_ofac_nao_tem_pagina_de_termos():
    termos = lote.termos()
    assert set(termos) == {"termos-wikidata", "termos-eufsf", "termos-ofsi"}
    assert all(u.startswith("https://") for u in termos.values())
    assert set(termos) <= set(fontes.TERMOS)
    assert all(destinos.DESTINOS[i].tipo == destinos.VIGIA for i in termos)


# ---- GLEIF, golden copy ----------------------------------------------------------------------
def test_golden_copy_roda_por_mes_e_a_relacao_por_semana_e_todas_sao_pesadas():
    por_id = _por_id()
    assert por_id["gleif-goldencopy-lei2"].grupo == "mensal"
    assert por_id["gleif-goldencopy-repex"].grupo == "mensal"
    assert por_id["gleif-goldencopy-rr"].grupo == "semanal"
    assert all(f.pesada for i, f in por_id.items() if i.startswith("gleif-golden"))


def test_a_golden_copy_usa_o_endereco_estavel_como_chave_e_a_versao_do_zip():
    latest = lote.endereco_do_ultimo_da_golden_copy("lei2")
    cliente = Fonte(
        paginas={latest: _fixture("golden_copy_lei2_ultimo.json")},
        cabecalhos={URL_DO_LEI2: CABECALHOS_DO_ZIP},
    )
    (alvo,) = lote.descobrir_golden_copy("lei2")(cliente, AGORA)
    assert alvo.url == latest  # o endereço do arquivo muda todo dia; a chave não
    assert alvo.extensao == ".csv.zip"
    assert alvo.versao == assinatura(CABECALHOS_DO_ZIP)
    assert alvo.obter is not None


def test_golden_copy_sem_cabecalhos_de_versao_nao_finge_uma_versao():
    latest = lote.endereco_do_ultimo_da_golden_copy("rr")
    cliente = Fonte(paginas={latest: _fixture("golden_copy_rr_ultimo.json")})
    (alvo,) = lote.descobrir_golden_copy("rr")(cliente, AGORA)
    assert alvo.versao is None


def test_resposta_inesperada_da_golden_copy_e_falha_nunca_nada_novo():
    latest = lote.endereco_do_ultimo_da_golden_copy("lei2")
    cliente = Fonte(paginas={latest: b'{"data": {"full_file": {}}}'})
    with pytest.raises(ErroDeDescoberta, match="GLEIF"):
        lote.descobrir_golden_copy("lei2")(cliente, AGORA)


def test_lgpd_lei2_perde_as_firmas_individuais_e_guarda_o_resto(tmp_path):
    bruto = tmp_path / "bruto.zip"
    bruto.write_bytes(_zip_do_lei2())
    destino = tmp_path / "filtrado.zip"
    removidas = lote.lei2_so_com_pessoa_juridica(bruto, destino)
    linhas = _linhas_do_zip(destino)
    assert removidas == 2
    assert [l[0] for l in linhas[1:]] == [
        "5299007FATCKT9465814",
        "549300EXEMPLOFUNDO0001",
        "391200AGENCIAGOV000001",
    ]
    texto = destino.read_bytes() + b"".join(",".join(l).encode() for l in linhas)
    assert b"MARIA EXEMPLO" not in texto and b"JOSE EXEMPLO" not in texto
    assert linhas[0][2] == "Entity.EntityCategory"  # o cabeçalho continua igual


def test_lgpd_o_arquivo_que_vai_ao_acervo_e_o_filtrado_e_o_bruto_some(tmp_path):
    latest = lote.endereco_do_ultimo_da_golden_copy("lei2")
    cliente = Fonte(
        paginas={latest: _fixture("golden_copy_lei2_ultimo.json")},
        cabecalhos={URL_DO_LEI2: CABECALHOS_DO_ZIP},
        arquivos={URL_DO_LEI2: _zip_do_lei2()},
    )
    (alvo,) = lote.descobrir_golden_copy("lei2")(cliente, AGORA)
    destino = tmp_path / "saida.zip"
    cabecalhos = alvo.obter(cliente, destino)
    assert cabecalhos == CABECALHOS_DO_ZIP  # a versão é a do arquivo de origem
    assert len(_linhas_do_zip(destino)) == 1 + 3
    assert list(tmp_path.iterdir()) == [destino]  # nenhum `.bruto` sobrou


def test_lgpd_lei2_que_falha_no_meio_nao_deixa_o_bruto_nem_um_arquivo_inteiro(tmp_path):
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as arquivo_zip:
        arquivo_zip.writestr(
            "lei2.csv", "LEI,Entity.LegalName\nX,Y\n"
        )  # sem a categoria
    cliente = Fonte(arquivos={URL_DO_LEI2: memoria.getvalue()})
    obter = lote._filtrado(URL_DO_LEI2, lote.lei2_so_com_pessoa_juridica)
    with pytest.raises(ErroDeDescoberta, match="Entity.EntityCategory"):
        obter(cliente, tmp_path / "saida.zip")
    assert not (tmp_path / "saida.zip.bruto").exists()


def test_a_relacao_e_a_excecao_do_gleif_vem_inteiras_sem_filtro(tmp_path):
    latest = lote.endereco_do_ultimo_da_golden_copy("rr")
    url = "https://goldencopy.gleif.org/storage/golden-copy-files/2026/10/23/1291925/20261023-0000-gleif-goldencopy-rr-golden-copy.csv.zip"
    cliente = Fonte(
        paginas={latest: _fixture("golden_copy_rr_ultimo.json")},
        arquivos={url: b"PK-relacoes"},
    )
    (alvo,) = lote.descobrir_golden_copy("rr")(cliente, AGORA)
    destino = tmp_path / "rr.zip"
    alvo.obter(cliente, destino)
    assert destino.read_bytes() == b"PK-relacoes"


# ---- sanções: só entidades -------------------------------------------------------------------
def test_lgpd_ofac_so_com_entidades(tmp_path):
    bruto = tmp_path / "sdn.csv"
    bruto.write_bytes(_fixture("sdn_duble.csv"))
    destino = tmp_path / "saida.csv"
    lote.sdn_so_com_entidades(bruto, destino)
    texto = destino.read_text(encoding="latin-1")
    assert "AEROCARIBBEAN AIRLINES" in texto and "BANCO NACIONAL DE CUBA" in texto
    assert "EXEMPLO, Fulano" not in texto  # pessoa
    assert "MV EXEMPLO" not in texto and "EXEMPLO CARGO" not in texto  # navio e avião
    assert len(texto.strip().splitlines()) == 2


def test_lgpd_uniao_europeia_so_com_empresas_e_a_marca_do_bom_fica(tmp_path):
    bruto = tmp_path / "ue.csv"
    bruto.write_bytes(_fixture("ue_duble.csv"))
    destino = tmp_path / "saida.csv"
    lote.sancoes_da_ue_so_com_empresas(bruto, destino)
    texto = destino.read_text(encoding="utf-8-sig")
    assert "EXEMPLO ENERGIA LTDA" in texto and "EXEMPLO ENERGY LLC" in texto
    assert "FULANO EXEMPLO" not in texto and "BELTRANO" not in texto
    assert texto.splitlines()[0].startswith("fileGenerationDate;")  # cabeçalho mantido


def test_uniao_europeia_sem_a_coluna_do_tipo_e_falha(tmp_path):
    bruto = tmp_path / "ue.csv"
    bruto.write_text("a;b\n1;2\n", encoding="utf-8")
    with pytest.raises(ErroDeDescoberta, match=lote.COLUNA_DO_TIPO_NA_UE):
        lote.sancoes_da_ue_so_com_empresas(bruto, tmp_path / "saida.csv")


def test_lgpd_reino_unido_so_com_entidades_e_mantem_as_duas_linhas_de_cabecalho(
    tmp_path,
):
    bruto = tmp_path / "uk.csv"
    bruto.write_bytes(_fixture("uk_sanctions_duble.csv"))
    destino = tmp_path / "saida.csv"
    lote.sancoes_do_reino_unido_so_com_entidades(bruto, destino)
    linhas = destino.read_text(encoding="utf-8-sig").splitlines()
    assert linhas[0].startswith("Report Date:")
    assert linhas[1].startswith("Last Updated,Unique ID,")
    assert len(linhas) == 3 and "EXEMPLO BANK" in linhas[2]
    assert "Fulano" not in "\n".join(linhas) and "MV EXEMPLO" not in linhas[2]


def test_reino_unido_sem_a_coluna_do_tipo_e_falha(tmp_path):
    bruto = tmp_path / "uk.csv"
    bruto.write_text("Report Date: x\nName 6,Name 1\nA,B\n", encoding="utf-8")
    with pytest.raises(ErroDeDescoberta, match=lote.COLUNA_DO_TIPO_NO_REINO_UNIDO):
        lote.sancoes_do_reino_unido_so_com_entidades(bruto, tmp_path / "saida.csv")


def test_reino_unido_le_a_lista_do_fcdo_e_nao_a_conlist_aposentada():
    # a ConList do OFSI saiu do ar (409 em 28/10/2026); o Reino Unido publica tudo na UK
    # Sanctions List do FCDO
    assert lote.SANCOES_DO_REINO_UNIDO.startswith("https://sanctionslist.fcdo.gov.uk/")
    assert "ofsistorage" not in lote.SANCOES_DO_REINO_UNIDO


@pytest.mark.parametrize(
    "id_, url",
    [
        ("ofac-sdn", lote.OFAC_SDN),
        ("eufsf-sancoes", lote.UE_SANCOES),
        ("ofsi-conlist", lote.SANCOES_DO_REINO_UNIDO),
    ],
)
def test_toda_lista_de_sancoes_guarda_o_arquivo_filtrado_nunca_o_bruto(
    id_, url, tmp_path
):
    fonte = _por_id()[id_]
    (alvo,) = fonte.descobrir(None, AGORA)  # type: ignore[arg-type]
    assert alvo.url == url
    assert alvo.obter is not None  # sem `obter` o `cliente.baixar` guardaria as pessoas
    assert fonte.grupo == "diaria" and not fonte.pesada


def test_a_lista_da_ue_usa_o_token_publico_do_proprio_site():
    assert lote.UE_SANCOES.endswith("?token=dG9rZW4tMjAxNw")


def test_a_lista_da_onu_nao_entra():
    assert not [i for i in _por_id() if "onu" in i or "un-" in i]


# ---- Wikidata e SEC --------------------------------------------------------------------------
def test_wikidata_um_pedido_por_identificador_em_json_e_com_pausa_grande():
    por_id = _por_id()
    ids = {i for i in por_id if i.startswith("wikidata-")}
    assert ids == {
        "wikidata-lei",
        "wikidata-isin",
        "wikidata-cnpj",
        "wikidata-cik",
        "wikidata-b3",
    }
    for id_ in ids:
        (alvo,) = por_id[id_].descobrir(None, AGORA)  # type: ignore[arg-type]
        assert alvo.url.startswith(lote.WIKIDATA + "?format=json&query=")
        assert por_id[id_].tipo == "json"
        assert por_id[id_].pausa_minima >= 5


def test_wikidata_nunca_traz_gente_e_a_ordem_e_fixa():
    consultas = [
        *(
            lote.consulta_do_wikidata(p)
            for p in lote.IDENTIFICADORES_DO_WIKIDATA.values()
        ),
        lote.consulta_dos_listados_na_b3(),
    ]
    for consulta in consultas:
        assert "FILTER NOT EXISTS { ?item wdt:P31 wd:Q5 }" in consulta
        assert " ORDER BY ?item" in consulta
    assert lote.IDENTIFICADORES_DO_WIKIDATA == {
        "wikidata-lei": "P1278",
        "wikidata-isin": "P946",
        "wikidata-cnpj": "P6204",
        "wikidata-cik": "P5531",
    }
    assert f"wd:{lote.ITEM_B3}" in lote.consulta_dos_listados_na_b3()
    assert lote.ITEM_B3 == "Q796297"


def test_o_endereco_do_wikidata_guarda_a_consulta_inteira():
    consulta = lote.consulta_do_wikidata("P1278")
    url = lote.endereco_do_wikidata(consulta)
    assert "wdt%3AP1278" in url and "format=json" in url


def test_sec_company_tickers_e_semanal_e_usa_o_agente_com_contato():
    fonte = _por_id()["sec-company-tickers"]
    (alvo,) = fonte.descobrir(None, AGORA)  # type: ignore[arg-type]
    assert alvo.url == "https://www.sec.gov/files/company_tickers.json"
    assert fonte.grupo == "semanal" and fonte.tipo == "json"
    assert (
        "contato@tickerlab.com.br" in AGENTE
    )  # a SEC pede nome e e-mail no User-Agent
    amostra = json.loads(_fixture("sec_company_tickers_amostra.json"))
    assert {v["ticker"] for v in amostra.values()} == {"AAPL", "MSFT"}
