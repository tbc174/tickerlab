"""Registro de fontes (B-01): cada fonte do arquivista com licença, marca, ritmo e data da leitura dos termos."""

import re
from datetime import date
from pathlib import Path

import pytest

from base import contrato
from base.arquivo import registro
from base.arquivo.fontes import FONTES
from base.arquivo.orgaos import NAO_SAO_FONTE, ORGAO_DA_FAMILIA
from src.banco.coletas import (
    LICENCAS,
    REVENDA,
    USOS_SEM_COBRANCA,
    Marca,
    licenca_da_fonte,
)


def _tem_entrada(tabela: dict, fonte: str) -> bool:
    """A fonte (ou a família dela) tem linha própria: o padrão "a confirmar" não conta."""
    return fonte in tabela or fonte.split("-", 1)[0] in tabela


@pytest.mark.parametrize("fonte", [f.id for f in FONTES])
def test_toda_fonte_tem_marca_e_licenca_escritas(fonte):
    """Fonte nova sem marca nem licença registradas quebra aqui, em vez de cair no padrão calado."""
    assert _tem_entrada(REVENDA, fonte), (
        f"{fonte}: sem marca em REVENDA (src/banco/coletas.py)"
    )
    assert _tem_entrada(LICENCAS, fonte), (
        f"{fonte}: sem licença em LICENCAS (src/banco/coletas.py)"
    )


def test_o_registro_tem_uma_linha_por_fonte_na_ordem_do_catalogo():
    linhas = registro.registro_de_fontes()
    assert [r.id for r in linhas] == [f.id for f in FONTES]


def test_cada_linha_traz_licenca_marca_e_ritmo():
    for linha in registro.registro_de_fontes():
        assert linha.licenca and linha.marca and linha.ritmo, linha.id
        assert linha.marca in {
            "vendavel",
            "uso_interno",
            "nao_comercial",
            "a_confirmar",
        }
        assert linha.ritmo in {"diaria", "semanal", "mensal", "carga-unica"}


def test_marca_e_licenca_batem_com_as_funcoes_da_coleta():
    por_id = {r.id: r for r in registro.registro_de_fontes()}
    assert por_id["cvm-fidc"].marca == "vendavel"
    assert "ODbL" in por_id["cvm-fidc"].licenca
    assert por_id["rfb-cnpj"].marca == "vendavel"


def test_a_data_da_leitura_dos_termos_e_uma_data_ou_nada():
    por_id = {r.id: r for r in registro.registro_de_fontes()}
    assert por_id["inmet-bdmep"].termos_lidos_em == date(2026, 10, 21)
    assert por_id["cvm-fidc"].termos_lidos_em == date(2026, 10, 21)
    assert por_id["ibama-autos"].termos_lidos_em is None
    assert por_id["gleif-br"].termos_lidos_em == date(2026, 10, 21)


def test_toda_data_de_leitura_aponta_para_uma_familia_que_existe():
    # família coletada pelo arquivista ou com licença registrada (Kraken, Yahoo e outras vêm de outro coletor)
    familias = {f.id.split("-", 1)[0] for f in FONTES} | set(LICENCAS)
    assert set(registro.TERMOS_LIDOS_EM) <= familias


def test_a_exportacao_para_o_site_nao_leva_conversa_interna():
    for linha in registro.para_o_site():
        texto = " ".join(str(v) for v in linha.values())
        assert "ADR" not in texto and "src/" not in texto, linha["id"]
    assert registro.para_o_site()[0].keys() >= {
        "id",
        "licenca",
        "marca",
        "ritmo",
        "termos_lidos_em",
    }


def test_a_base_de_cnpj_tem_a_data_da_leitura_dos_termos():
    """Sem a data, o portão da API externa nega `rfb-cnpj` por `termos_sem_data`."""
    por_id = {r.id: r for r in registro.registro_de_fontes()}
    assert por_id["rfb-cnpj"].termos_lidos_em == date(2026, 10, 21)


# --- a lista por família da página Dados (linha 592 da fila) ---

RAIZ = Path(__file__).resolve().parents[1]
# sufixos largos: o domínio registrável tem uma parte a mais ("dados.cvm.gov.br" → "cvm.gov.br")
_SUFIXOS_LARGOS = {
    "gov.br",
    "org.br",
    "com.br",
    "leg.br",
    "jus.br",
    "gov.uk",
    "europa.eu",
    "ac.uk",
}


def _dominio(host: str) -> str:
    partes = host.lower().split(".")
    corte = 3 if ".".join(partes[-2:]) in _SUFIXOS_LARGOS else 2
    return ".".join(partes[-corte:])


@pytest.fixture(scope="module")
def catalogo():
    return contrato.catalogo()


@pytest.fixture(scope="module")
def familias(catalogo):
    return registro.familias_para_o_site(catalogo)


def test_toda_familia_tem_orgao():
    """Família nova (no arquivista ou só em LICENCAS) sem nome legível quebra aqui, não some da página."""
    todas = {f.id.split("-", 1)[0] for f in FONTES} | {
        k.split("-", 1)[0] for k in LICENCAS
    }
    faltam = todas - set(ORGAO_DA_FAMILIA) - set(NAO_SAO_FONTE)
    assert not faltam, f"sem órgão em base/arquivo/orgaos.py: {sorted(faltam)}"
    assert set(ORGAO_DA_FAMILIA) <= todas, "órgão de família que não existe"


def test_a_lista_publica_tem_todas_as_familias_menos_as_que_nao_sao_fonte(familias):
    nomes = [f["familia"] for f in familias]
    assert len(nomes) == len(set(nomes))
    assert set(nomes) == set(ORGAO_DA_FAMILIA)
    assert not set(nomes) & set(NAO_SAO_FONTE)


def test_registro_tem_as_fontes_do_app(familias):
    """As famílias lidas fora do arquivista entram, com a licença de LICENCAS e sem coletas."""
    por_familia = {f["familia"]: f for f in familias}
    for familia in registro.FONTES_DE_FORA_DO_ARQUIVISTA:
        linha = por_familia[familia]
        assert linha["licencas"] == [registro._licenca_publica(LICENCAS[familia])]
        assert linha["coletas"] == [] and linha["ritmo"] == registro.RITMO_DE_FORA


def test_uso_da_familia(catalogo):
    assert registro.uso_da_familia("cvm", catalogo) == "em_uso"  # tabelas do catálogo
    assert registro.uso_da_familia("yahoo", catalogo) == "em_uso"  # todo preço do app
    assert (
        registro.uso_da_familia("pgfn", catalogo) == "em_uso"
    )  # uso citado sem cobrança
    assert registro.uso_da_familia("nasa", catalogo) == "guardada"
    assert registro.uso_da_familia("kraken", catalogo) == "guardada"
    assert (
        registro.uso_da_familia("iex", catalogo) == "guardada"
    )  # só os scripts a leem


def test_em_uso_aponta_para_tabela_uso_citado_ou_modulo(familias, catalogo):
    """Dizer "em uso" do que não chega ao usuário seria promessa falsa: cada uma tem de onde sair."""
    no_catalogo = {t["licenca"] for t in catalogo["tabelas"].values()}
    citadas = {u.fonte.split("-", 1)[0] for u in USOS_SEM_COBRANCA}
    for linha in familias:
        if linha["uso"] != "em_uso":
            continue
        fontes = linha["coletas"] or [linha["familia"]]
        assert (
            any(licenca_da_fonte(f) in no_catalogo for f in fontes)
            or linha["familia"] in citadas
            or linha["familia"] in registro.FONTES_LIDAS_PELO_APP
        ), linha["familia"]


@pytest.mark.parametrize("familia", list(registro.FONTES_LIDAS_PELO_APP))
def test_modulo_do_app_existe(familia):
    caminho, palavra = registro.FONTES_LIDAS_PELO_APP[familia]
    arquivo = RAIZ / caminho
    assert arquivo.is_file(), caminho
    assert palavra in arquivo.read_text(encoding="utf-8"), (caminho, palavra)


def test_link_do_orgao_e_https_e_de_um_dominio_que_coletamos():
    """O link é do próprio órgão: o mesmo domínio de onde o código já baixa algo, nunca um inventado."""
    hosts = set()
    for pasta in ("base", "src", "scripts"):
        for arquivo in (RAIZ / pasta).rglob("*.py"):
            hosts |= set(
                re.findall(r"https?://([\w.-]+)", arquivo.read_text(encoding="utf-8"))
            )
    dominios = {_dominio(h) for h in hosts if "." in h}
    for familia, orgao in ORGAO_DA_FAMILIA.items():
        if orgao.link is None:
            continue
        assert orgao.link.startswith("https://"), familia
        host = re.match(r"https://([\w.-]+)", orgao.link).group(1)
        assert _dominio(host) in dominios, f"{familia}: {host} não aparece no código"


def test_lista_por_familia_nao_leva_conversa_interna(familias):
    for linha in familias:
        texto = " ".join(str(v) for v in linha.values())
        assert "ADR" not in texto and "src/" not in texto, linha["familia"]
        assert linha["uso"] in {"em_uso", "guardada"}
        assert linha["marca"] in {m.value for m in Marca}


def test_familia_reune_as_coletas_e_a_marca_mais_restrita(familias):
    por_familia = {f["familia"]: f for f in familias}
    cvm = por_familia["cvm"]
    assert "cvm-fidc" in cvm["coletas"]
    assert cvm["orgao"].startswith("CVM") and cvm["termos_lidos_em"] == "2026-10-21"
    assert por_familia["yahoo"]["marca"] == "nao_comercial"


def test_divida_do_tesouro_nacional_nao_leva_a_licenca_dos_eua():
    """Regressão: os pacotes `tesouro-br-divida-*` caíam na licença da família "tesouro" (a dos EUA)."""
    for f in FONTES:
        if f.id.startswith("tesouro-br"):
            assert "Tesouro Nacional" in licenca_da_fonte(f.id), f.id
