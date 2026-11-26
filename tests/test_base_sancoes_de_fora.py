"""Sanções de fora (OFAC, União Europeia e Reino Unido) na base: só entidades, nunca pessoa física.

O que não pode faltar aqui é a LGPD: pessoa, navio, aeronave e registro sem tipo não passam, nem para o
acervo nem para a tabela. Os XML são inventados (`tests/arquivos/sancoes_de_fora/dubles.py`).
"""

import hashlib
import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa

from base import dossie, sancoes_de_fora
from base.arquivo import destinos, sancoes_xml
from base.arquivo import lote_cadastros as lote
from base.arquivo.coleta import ErroDeDescoberta
from base.dicionario import TABELAS
from src.banco import coletas
from src.banco.coletas import com_registro

_DUBLES = Path(__file__).parent / "arquivos" / "sancoes_de_fora" / "dubles.py"
_spec = importlib.util.spec_from_file_location("dubles_de_sancoes_de_fora", _DUBLES)
assert _spec is not None and _spec.loader is not None
dubles = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dubles)

AGORA = datetime(2026, 11, 26, 22, tzinfo=UTC)
OFAC_SDN, OFAC_CONS, UE, UK = (
    sancoes_xml.OFAC_SDN,
    sancoes_xml.OFAC_CONSOLIDADA,
    sancoes_xml.UNIAO_EUROPEIA,
    sancoes_xml.REINO_UNIDO,
)
LISTAS = [
    (OFAC_SDN, dubles.sdn, {"100", "101"}),
    (OFAC_CONS, dubles.consolidada, {"101", "300"}),
    (UE, dubles.uniao_europeia, {"1", "2"}),
    (UK, dubles.reino_unido, {"INV0001"}),
]


def _filtrar(tmp_path: Path, formato, conteudo: bytes) -> bytes:
    bruto, destino = tmp_path / "bruto.xml", tmp_path / "filtrado.xml"
    bruto.write_bytes(conteudo)
    sancoes_xml.so_entidades(bruto, destino, formato)
    return destino.read_bytes()


# --- o filtro da coleta (o que chega ao acervo) ----------------------------------------------------
@pytest.mark.parametrize("formato, duble, ids", LISTAS)
def test_lgpd_o_acervo_so_recebe_entidade_e_so_os_campos_da_tabela(
    tmp_path, formato, duble, ids
):
    filtrado = _filtrar(tmp_path, formato, duble())
    texto = filtrado.decode("utf-8")
    for proibido in dubles.NAO_SAI:
        assert proibido not in texto, proibido
    assert {r.id for r in sancoes_xml.entidades(filtrado, formato)} == ids


@pytest.mark.parametrize("formato, duble, ids", LISTAS)
def test_lgpd_a_leitura_sozinha_tambem_barra_pessoa(formato, duble, ids):
    """Defesa em dobro: um arquivo sem filtro (o original da fonte) não deixa pessoa passar."""
    lidos = sancoes_xml.entidades(duble(), formato)
    assert {r.id for r in lidos} == ids
    nomes = " ".join(n for r in lidos for n in (r.nome, *r.outros_nomes))
    for pessoa in dubles.PESSOAS:
        assert pessoa not in nomes


@pytest.mark.parametrize(
    "nome",
    [
        "IP INVENTADO",
        "ИП ИНВЕНТАДО",
        "INVENTADO INDIVIDUAL ENTREPRENEUR",
        "Private Entrepreneur Inventado",
        "SOLE TRADER INVENTADO",
        "INDIVIDUALNYI PREDPRINIMATEL INVENTADO",
        "Individualniy Predprinimatel Inventado",
        "INVENTADO FIZYCHNA OSOBA-PIDPRYEMETS",
        "FOP INVENTADO",
        "ФОП ІНВЕНТАДО",
        "ІП ІНВЕНТАДО",
        "ЧП ИНВЕНТАДО",
        "ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ ИНВЕНТАДО",
        "ФІЗИЧНА ОСОБА-ПІДПРИЄМЕЦЬ ІНВЕНТАДО",
        "FIZICHESKOE LITSO INVENTADO",
        "INDIVIDUAL'NYY PREDPRINIMATEL' INVENTADO",
        "ФИЗИЧЕСКОЕ ЛИЦО ИНВЕНТАДО",
        "ИНДИВИДУАЛЬНОГО ПРЕДПРИНИМАТЕЛЯ ИНВЕНТАДО",
    ],
)
def test_empresario_individual_pelo_nome_nao_passa(nome):
    assert sancoes_xml.e_empresario_individual(nome)


@pytest.mark.parametrize(
    "nome",
    [
        "EXEMPLO IP HOLDINGS",
        "IPANEMA EXEMPLO SA",
        "EXEMPLO ENTERPRISES",
        "FOPEXEMPLO SA",
        "ЮРИДИЧЕСКОЕ ЛИЦО ПРИМЕР",  # "pessoa jurídica" em russo
    ],
)
def test_empresa_com_ip_no_nome_passa(nome):
    assert not sancoes_xml.e_empresario_individual(nome)


@pytest.mark.parametrize("formato", [OFAC_SDN, UE, UK])
def test_formato_que_mudou_e_falha_nunca_lista_vazia(tmp_path, formato):
    with pytest.raises(ErroDeDescoberta):
        _filtrar(tmp_path, formato, b"<outraCoisa><item/></outraCoisa>")


def test_o_mesmo_conteudo_com_outra_data_de_geracao_da_o_mesmo_arquivo(tmp_path):
    original = dubles.sdn()
    outro_dia = original.replace(b"2026-11-26T00:00:00", b"2026-11-27T00:00:00")
    assert _filtrar(tmp_path, OFAC_SDN, original) == _filtrar(
        tmp_path, OFAC_SDN, outro_dia
    )


# --- o que se lê de cada lista ----------------------------------------------------------------------
def test_ofac_nome_apelidos_pais_programa_e_data():
    (empresa, banco) = sancoes_xml.entidades(dubles.sdn(), OFAC_SDN)
    assert empresa.nome == "EXEMPLO TRADING LLC"
    assert empresa.outros_nomes == ("EXEMPLO TRADE",)  # o apelido fraco fica fora
    assert empresa.paises == ("Pais Inventado",)
    assert empresa.programas == ("PROGRAMA-A",)
    assert empresa.listas == (("SDN List", "2022-03-01"),)
    # a SDN sai só do arquivo da SDN; as outras listas, só do arquivo consolidado
    assert banco.listas == (("SDN List", "2022-03-01"),)


def test_ofac_consolidada_nao_repete_a_sdn_nem_o_guarda_chuva():
    lidos = {r.id: r for r in sancoes_xml.entidades(dubles.consolidada(), OFAC_CONS)}
    assert lidos["101"].listas == (
        ("Sectoral Sanctions Identifications List", "2022-03-03"),
    )
    assert lidos["300"].listas == (("Non-SDN CMIC List", "2022-03-02"),)


def test_reino_unido_pega_o_nome_principal_e_a_data_a_brasileira():
    (empresa,) = sancoes_xml.entidades(dubles.reino_unido(), UK)
    assert empresa.nome == "EXEMPLO ENERGIA SA"
    assert empresa.outros_nomes == ("EXEMPLO ENERGY",)
    assert empresa.paises == ("Pais Inventado",)
    assert empresa.programas == ("Regime Inventado",)
    assert empresa.listas == (("UK Sanctions List", "2022-03-15"),)


def test_uniao_europeia_sem_data_fica_sem_data_e_unknown_nao_e_pais():
    (primeira, sem_data) = sancoes_xml.entidades(dubles.uniao_europeia(), UE)
    assert primeira.nome == "EXEMPLO CHEMICAL JSC"
    assert primeira.outros_nomes == ("EXEMPLO QUIMICA",)
    assert primeira.paises == ("PAIS INVENTADO",)
    assert primeira.programas == ("PRG",)
    assert sem_data.listas == (("EU Financial Sanctions List", None),)


# --- a coleta ---------------------------------------------------------------------------------------
def test_toda_lista_de_sancoes_baixa_o_xml_oficial_e_guarda_so_o_filtrado(tmp_path):
    esperado = {
        "ofac-sdn": [OFAC_SDN, OFAC_CONS],
        "eufsf-sancoes": [UE],
        "ofsi-conlist": [UK],
    }
    por_id = {f.id: f for f in lote.fontes()}
    for id_, formatos in esperado.items():
        fonte = por_id[id_]
        alvos = fonte.descobrir(None, AGORA)  # type: ignore[arg-type]
        assert [a.url for a in alvos] == [f.url for f in formatos]
        assert all(a.obter is not None and a.extensao == ".xml" for a in alvos)
        assert fonte.grupo == "diaria" and not fonte.pesada


def test_a_coleta_apaga_o_original_com_as_pessoas(tmp_path):
    class Cliente:
        def baixar(self, url, destino: Path):
            destino.write_bytes(dubles.sdn())
            return {"ETag": "x"}

    (alvo, _) = {f.id: f for f in lote.fontes()}["ofac-sdn"].descobrir(None, AGORA)  # type: ignore[arg-type]
    destino = tmp_path / "saida.xml"
    assert alvo.obter is not None
    assert alvo.obter(Cliente(), destino) == {"ETag": "x"}  # type: ignore[arg-type]
    assert list(tmp_path.iterdir()) == [destino]
    assert "FULANA INVENTADA" not in destino.read_text(encoding="utf-8")


# --- a tabela ----------------------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def versao(monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")


def _coletar(banco, fonte: str, url: str, conteudo: bytes, dia: date) -> None:
    com_registro(fonte, lambda _url: conteudo)(url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(
                coletas.coletas.c.url == url,
                coletas.coletas.c.sha256 == hashlib.sha256(conteudo).hexdigest(),
            )
            .values(baixado_em=datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC))
        )


def _coletar_uk(banco, dia: date, *extras: str) -> None:
    _coletar(banco, "ofsi-conlist", UK.url, dubles.reino_unido(*extras), dia)


def _montar(banco, tmp_path) -> dict:
    with banco.connect() as conexao:
        return sancoes_de_fora.montar(conexao, tmp_path / "base", AGORA)


def _tabela(tmp_path, cadastro: str) -> pd.DataFrame:
    return pd.read_parquet(
        tmp_path / "base" / "sancoes_de_fora" / f"{cadastro}.parquet"
    )


def test_tabela_uma_linha_por_entidade_e_lista_sem_pessoa(banco, tmp_path):
    dia = date(2026, 11, 26)
    _coletar(banco, "ofac-sdn", OFAC_SDN.url, dubles.sdn(), dia)
    _coletar(banco, "ofac-sdn", OFAC_CONS.url, dubles.consolidada(), dia)
    _coletar(banco, "eufsf-sancoes", UE.url, dubles.uniao_europeia(), dia)
    _coletar_uk(banco, dia)
    resumo = _montar(banco, tmp_path)
    assert {c: r["na_tabela"] for c, r in resumo.items()} == {
        "ofac_sdn": 2,
        "ofac_consolidada": 2,
        "uniao_europeia": 2,
        "reino_unido": 1,
    }
    tudo = pd.concat(
        pd.read_parquet(p)
        for p in (tmp_path / "base" / "sancoes_de_fora").glob("*.parquet")
    )
    assert not tudo.duplicated(["lista", "id_na_fonte", "visto_em"]).any()
    texto = tudo.astype(str).to_csv(index=False)
    for proibido in dubles.NAO_SAI:
        assert proibido not in texto, proibido
    assert list(tudo.columns) == sancoes_de_fora.COLUNAS_GRAVADAS
    britanica = _tabela(tmp_path, "reino_unido").iloc[0]
    assert britanica["lista"] == "UK Sanctions List"
    assert britanica["id_na_fonte"] == "INV0001"
    assert britanica["nome"] == "EXEMPLO ENERGIA SA"
    assert britanica["outros_nomes"] == "EXEMPLO ENERGY"
    assert britanica["designado_em"] == date(2022, 3, 15)
    assert britanica["fonte"] == "Reino Unido (FCDO, UK Sanctions List), OGL v3.0"
    assert britanica["url_da_fonte"] == UK.url
    europeia = _tabela(tmp_path, "uniao_europeia")["fonte"].unique().tolist()
    assert europeia == [
        (
            "Comissão Europeia (DG FISMA), Decisão 2011/833/UE; mantidas só as entidades; "
            "só o Jornal Oficial da UE é autêntico"
        )
    ]
    for lista in ("ofac_sdn", "ofac_consolidada"):
        do_tesouro = _tabela(tmp_path, lista)["fonte"].unique().tolist()
        assert do_tesouro == ["OFAC, U.S. Department of the Treasury"]


def _como_era(tabela, dia: date):
    """O que a base dizia no dia: a última versão já pública de cada entidade e lista que constava."""
    publicas = tabela[tabela["disponivel_em"] <= dia].sort_values("visto_em")
    valendo = publicas.drop_duplicates(["lista", "id_na_fonte"], keep="last")
    return valendo[valendo["consta"]]


def test_sem_olhar_o_futuro_a_linha_vale_do_dia_em_que_o_arquivo_foi_visto(
    banco, tmp_path
):
    """A designação é de 2022, mas a base só soube dela no dia do primeiro arquivo; o que entra ou sai
    depois vale do dia do arquivo seguinte, e o passado não muda."""
    primeiro, segundo, terceiro = (
        date(2026, 11, 20),
        date(2026, 11, 21),
        date(2026, 11, 22),
    )
    nova = dubles.uk_entidade("INV0002", "EXEMPLO NOVA SA")
    outra = dubles.uk_entidade("INV0003", "EXEMPLO OUTRA SA")
    _coletar_uk(banco, primeiro, outra)
    _montar(banco, tmp_path)
    antes = _tabela(tmp_path, "reino_unido")
    assert set(antes["disponivel_em"]) == {primeiro}
    _coletar_uk(banco, segundo, outra, nova)
    _coletar_uk(banco, terceiro, nova)  # a "outra" saiu da lista
    _montar(banco, tmp_path)
    depois = _tabela(tmp_path, "reino_unido")
    assert _como_era(depois, date(2026, 11, 19)).empty
    assert set(_como_era(depois, primeiro)["id_na_fonte"]) == {"INV0001", "INV0003"}
    assert set(_como_era(depois, segundo)["id_na_fonte"]) == {
        "INV0001",
        "INV0002",
        "INV0003",
    }
    saida = depois[(depois["id_na_fonte"] == "INV0003") & ~depois["consta"]]
    assert saida["disponivel_em"].tolist() == [terceiro]
    assert (depois["disponivel_em"] == depois["visto_em"]).all()


# os endereços do CSV que o arquivista guardou até o XML: o da União Europeia termina igual ao do XML
CSV_ANTIGOS = [
    (
        "ofac-sdn",
        "https://www.treasury.gov/ofac/downloads/sdn.csv",
        OFAC_SDN,
        dubles.sdn,
        "ofac_sdn",
    ),
    (
        "eufsf-sancoes",
        (
            "https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList_1_1/content"
            "?token=dG9rZW4tMjAxNw"
        ),
        UE,
        dubles.uniao_europeia,
        "uniao_europeia",
    ),
    (
        "ofsi-conlist",
        "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.csv",
        UK,
        dubles.reino_unido,
        "reino_unido",
    ),
]


@pytest.mark.parametrize(
    ("fonte", "antigo", "formato", "duble", "cadastro"), CSV_ANTIGOS
)
def test_o_csv_antigo_da_mesma_fonte_fica_fora(
    banco, tmp_path, fonte, antigo, formato, duble, cadastro
):
    """O acervo continua com o CSV de antes: a carga o ignora em vez de tentar ler como XML."""
    csv = b"Report Date: x;Entity_LogicalId;SubjectType"  # não é XML
    _coletar(banco, fonte, antigo, csv, date(2026, 11, 1))
    assert _montar(banco, tmp_path) == {}
    _coletar(banco, fonte, formato.url, duble(), date(2026, 11, 20))
    assert _montar(banco, tmp_path)[cadastro]["retratos"] == 1


def test_comando_sem_nada_guardado_sai_com_1_e_depois_monta(banco, tmp_path):
    from scripts import carga_sancoes_de_fora

    assert carga_sancoes_de_fora.main(["--pasta", str(tmp_path / "b")]) == 1
    _coletar_uk(banco, date(2026, 11, 26))
    assert carga_sancoes_de_fora.main(["--pasta", str(tmp_path / "b")]) == 0
    assert (tmp_path / "b" / "sancoes_de_fora" / "reino_unido.parquet").exists()


# --- o registro da tabela ----------------------------------------------------------------------------
def test_contrato_destino_e_so_no_modo_dono():
    tabela = TABELAS["sancoes_de_fora"]
    assert not tabela.pessoa
    assert tabela.familia_da_fonte == "ofac"
    assert "Decisão 2011/833/UE" in tabela.ressalva_de_revenda
    assert "OGL" in tabela.ressalva_de_revenda
    assert set(tabela.colunas) >= set(sancoes_de_fora.COLUNAS)
    for fonte in ("ofac-sdn", "eufsf-sancoes", "ofsi-conlist"):
        assert destinos.DESTINOS[fonte].tabelas == ("sancoes_de_fora",)
    # não sai no site, na API aberta nem para organização: conector e análise são outro passo
    assert "sancoes_de_fora" in dossie.SO_NO_MODO_DONO
    assert not dossie.pode_mostrar("sancoes_de_fora")
    assert not dossie.pode_consultar("sancoes_de_fora")


def test_a_licenca_a_atribuicao_e_o_limite_da_tabela():
    """Condições do "pode" da licença (Diretoria, 26/11/2026)."""
    tabela = TABELAS["sancoes_de_fora"]
    ofac = coletas.licenca_da_fonte("ofac")
    assert "sem licença declarada" in ofac.lower()
    assert "17 U.S.C. 105" in ofac and "citar a fonte" in ofac
    assert "DG FISMA" in coletas.licenca_da_fonte("eufsf")
    assert "só entidades mantidas" in coletas.licenca_da_fonte("eufsf")
    assert "sem licença declarada na página" in tabela.ressalva_de_revenda
    assert "Jornal Oficial" in tabela.fonte
    assert "FCDO" in coletas.licenca_da_fonte("ofsi")
    assert "OGL v3.0" in coletas.licenca_da_fonte("ofsi")
    for citado in (
        "U.S. Department of the Treasury",
        "sem endosso",
        "DG FISMA",
        "FCDO",
        "OGL",
    ):
        assert citado in tabela.fonte, citado
    assert "não é determinação de conformidade" in tabela.descricao
