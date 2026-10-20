"""O rastro de cada item do dossiê da base (B-02, PR 2, 20/10/2026): a fórmula, a versão do cálculo, a
fonte (a família da licença) e o dia em que o dado mais novo usado ficou público.

A ficha da CPFL é montada pela noite inteira (`scripts/gerar_dossies.py`) sobre uma mini-base com todas
as seções; o gabarito fixa o rastro de cada item, para que mudar uma fórmula sem subir
`VERSAO_DO_DOSSIE` quebre aqui.
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base import dossie
from base.dicionario import TABELAS
from src import dossie as dossie_do_app
from src.banco.coletas import LICENCAS
from tests import test_dossie_geracao_de_caixa as geracao_de_caixa
from tests.test_gerar_dossies import (
    CPFL,
    CPFL_DIGITOS,
    DISTRIBUIDORA,
    _ficha_da_cpfl,
    _governanca_e_credito,
    _gravar,
    _lucro_e_capital,
    _mini_base,
    _montar,
    _rede_da_cpfl,
)

D = pd.Timestamp
GABARITO = Path(__file__).parent / "arquivos" / "rastro" / "dossie.json"
AUDITOR_CONHECIDO_EM = "2025-05-20"
INSIDER_ENTREGUE_EM = (
    "2026-06-10"  # a outra declaração só é entregue em 2026-11-10, depois do dia
)
ANEEL_DE_DEZEMBRO = "2026-02-15"


def _o_resto_com_a_publicacao(pasta: Path) -> None:
    """O que a mini-base não tem ou grava sem a coluna de quando ficou público."""
    _gravar(
        pasta,
        "auditores/2025.parquet",
        pd.DataFrame(
            {
                "cnpj": [CPFL],
                "referencia": [D("2025-01-01")],
                "versao": [1],
                "auditor_id": ["rede:deloitte"],
                "auditor": ["Deloitte"],
                "auditor_cnpj": ["49928567000111"],
                "inicio": [D("2025-04-01")],
                "fim": [pd.NaT],
                "conhecido_em": [D(AUDITOR_CONHECIDO_EM)],
            }
        ),
    )
    _gravar(
        pasta,
        "trocas_de_auditor/trocas.parquet",
        pd.DataFrame(
            {
                "cnpj": [CPFL],
                "efetiva_em": [D("2025-04-01")],
                "anterior": ["KPMG"],
                "novo": ["Deloitte"],
                "anos_com_o_anterior": [5],
                "conhecido_em": [D(AUDITOR_CONHECIDO_EM)],
            }
        ),
    )
    _gravar(
        pasta,
        "ofertas/resolucao_160.parquet",
        pd.DataFrame(
            {
                "cnpj_emissor": [CPFL],
                "nome_emissor": ["CPFL ENERGIA S.A."],
                "data_registro": [D("2025-06-01")],
                "data_requerimento": [D("2025-05-01")],
                "valor_mobiliario": ["Debêntures"],
                "tipo_oferta": ["Primária"],
                "valor_total_registrado": [1e9],
                "status_requerimento": ["Registrada"],
                "disponivel_em": [D("2025-06-02")],
            }
        ),
    )
    meses = pd.date_range("2025-01-31", periods=13, freq="ME")
    _gravar(
        pasta,
        "fundos/painel_empresa/2025.parquet",
        pd.DataFrame(
            {
                "competencia": meses,
                "cnpj": [CPFL_DIGITOS] * 13,
                "tipo": ["comprado"] * 13,
                "fundos": [400] * 13,
                "valor": [9.0e9] * 13,
                "compras": [1.0e8] * 13,
                "vendas": [5.0e7] * 13,
                "disponivel_em": meses + pd.DateOffset(days=40),
            }
        ),
    )
    _gravar(  # o painel por emissor divide a tabela com o por empresa (a noite filtra pelo emissor)
        pasta,
        "fundos/painel_emissor/2025.parquet",
        pd.DataFrame(
            {
                "competencia": meses,
                "emissor": ["CPFL ENERGIA"] * 13,
                "tipo": ["comprado"] * 13,
            }
        ),
    )
    _gravar(
        pasta,
        "setoriais/aneel/2025.parquet",
        pd.DataFrame(
            {
                "competencia": [D("2025-11-30"), D("2025-12-31"), D("2025-12-31")],
                "cnpj": [DISTRIBUIDORA, DISTRIBUIDORA, "99999999000199"],
                "valor": [100.0, 110.0, 890.0],
                "detalhe_do_mercado": ["Número de consumidores"] * 3,
                "tipo_de_mercado": ["Regular"] * 3,
                "disponivel_em": [
                    D("2026-01-15"),
                    D(ANEEL_DE_DEZEMBRO),
                    D(ANEEL_DE_DEZEMBRO),
                ],
            }
        ),
    )
    _gravar(
        pasta,
        "demonstracoes/2025.parquet",
        geracao_de_caixa._como_era().assign(cnpj=CPFL),
    )


def _base_completa(pasta: Path) -> None:
    _mini_base(pasta)
    _lucro_e_capital(pasta)
    _governanca_e_credito(pasta)
    _rede_da_cpfl(pasta, com_o_futuro=False)
    _o_resto_com_a_publicacao(pasta)


@pytest.fixture(scope="module")
def ficha(tmp_path_factory: pytest.TempPathFactory) -> dict:
    pasta = tmp_path_factory.mktemp("rastro")
    _base_completa(pasta / "base")
    resumo = _montar(pasta / "base", pasta / "dossies")
    assert resumo.falhas == []
    return _ficha_da_cpfl(pasta / "dossies")


def _itens(ficha: dict) -> dict[str, dict]:
    """Os itens de todas as seções, por "seção.chave" (a chave sozinha repete: "controladas")."""
    return {
        f"{s['chave']}.{i['chave']}": i for s in ficha["secoes"] for i in s["itens"]
    }


# --- o registro ------------------------------------------------------------------------------------
def test_todo_item_registrado_tem_tabela_fonte_com_licenca_e_formula():
    origens = {**dossie.ORIGEM_DOS_ITENS, **dossie.ORIGEM_DAS_RELACOES}
    for chave, origem in origens.items():
        assert origem.tabela in TABELAS, chave
        assert TABELAS[origem.tabela].familia_da_fonte in LICENCAS, chave
        assert origem.formula.strip(), chave
    assert set(dossie.ITENS_SEM_DATA_DE_PUBLICACAO) <= set(origens)


def test_item_sem_data_e_so_de_tabela_sem_a_coluna_da_publicacao():
    """A exceção só vale onde a base não guarda o dia: se a tabela ganhar a coluna, o item sai da lista."""
    for chave in dossie.ITENS_SEM_DATA_DE_PUBLICACAO:
        tabela = dossie.ORIGEM_DOS_ITENS[chave].tabela
        assert "publico_em" not in TABELAS[tabela].datas, chave


def test_toda_serie_e_toda_relacao_tem_origem():
    series = (*dossie.SERIES_DAS_AGENCIAS, *dossie.SERIES_DOS_BANCOS)
    for s in series:
        for chave in (s.nome, f"mercado_{s.nome}", f"hhi_{s.nome}", f"cr4_{s.nome}"):
            assert dossie.ORIGEM_DOS_ITENS[chave].tabela == s.tabela
    assert set(dossie.ORIGEM_DAS_RELACOES) == {r.chave for r in dossie.RELACOES}


def test_chave_sem_origem_quebra_ao_montar_o_item():
    with pytest.raises(KeyError):
        dossie._item("inventado", "Inventado", 1, "", None, publicado_em=None)


# --- a ficha da noite ------------------------------------------------------------------------------
def test_todo_item_da_ficha_tem_o_rastro_inteiro(ficha):
    itens = _itens(ficha)
    secoes = {chave.split(".")[0] for chave in itens}
    assert (
        len(secoes) >= 10 and len(itens) >= 35
    )  # todas as seções, menos as dos bancos
    faltando = {}
    for chave, item in itens.items():
        rastro = item["rastro"]
        partes = ["formula", "versao_do_calculo", "fonte_id", "publicado_em"]
        if item["chave"] in dossie.ITENS_SEM_DATA_DE_PUBLICACAO:
            partes.remove("publicado_em")
        if falta := [p for p in partes if not rastro[p]]:
            faltando[chave] = falta
    assert faltando == {}


def test_fonte_do_rastro_e_uma_familia_com_licenca(ficha):
    for item in _itens(ficha).values():
        rastro = item["rastro"]
        assert {rastro["fonte_id"], *rastro["outras_fontes"]} <= set(LICENCAS)
        assert rastro["versao_do_calculo"] == dossie.CALCULO_DO_DOSSIE


def test_publicado_em_e_a_entrega_nao_a_data_do_fato(ficha):
    itens = _itens(ficha)
    auditor = itens["auditor_e_controladas.auditor_atual"]
    assert auditor["base"] == "2025-01-01"  # o FRE é de janeiro
    assert auditor["rastro"]["publicado_em"] == AUDITOR_CONHECIDO_EM
    setor = itens["setor_regulado.aneel_consumidores"]["rastro"]
    assert (setor["fonte_id"], setor["publicado_em"]) == ("aneel", ANEEL_DE_DEZEMBRO)
    controladas = itens["auditor_e_controladas.controladas"]["rastro"]["publicado_em"]
    assert controladas == "2026-05-31"  # a entrega do FRE de 2025


def test_publicado_em_nao_olha_o_futuro(ficha):
    """A declaração entregue depois do dia da ficha não conta na soma nem no dia da publicação."""
    insiders = _itens(ficha)["capital_e_acionistas.insiders_compras_12m"]
    assert insiders["valor"] == 2e6
    assert insiders["rastro"]["publicado_em"] == INSIDER_ENTREGUE_EM


def test_relacao_da_rede_tem_o_rastro_da_rede(ficha):
    itens = _itens(ficha)
    da_rede = itens["rede.controladas"]["rastro"]
    do_fre = itens["auditor_e_controladas.controladas"]["rastro"]
    assert da_rede["formula"] != do_fre["formula"]
    assert da_rede["publicado_em"] == "2016-05-31"  # quando a ligação ficou pública


def test_o_app_le_o_rastro_da_ficha(ficha):
    lida = dossie_do_app.Ficha.model_validate(ficha)
    itens = {
        (s.chave, i.chave): i
        for s in dossie_do_app.secoes_da_ficha(lida)
        for i in s.itens
    }
    auditor = itens[("auditor_e_controladas", "auditor_atual")]
    assert auditor.rastro is not None
    assert auditor.rastro.publicado_em == date.fromisoformat(AUDITOR_CONHECIDO_EM)
    assert auditor.rastro.versao_do_calculo == dossie.CALCULO_DO_DOSSIE


def test_ficha_de_antes_do_rastro_ainda_abre(ficha):
    velha = json.loads(json.dumps(ficha))
    for secao in velha["secoes"]:
        for item in secao["itens"]:
            item.pop("rastro")
    lida = dossie_do_app.Ficha.model_validate(velha)
    itens = [i for s in dossie_do_app.secoes_da_ficha(lida) for i in s.itens]
    assert itens and all(i.rastro is None for i in itens)


# --- o gabarito por item ---------------------------------------------------------------------------
def _atual(ficha: dict) -> dict[str, dict]:
    return {
        chave: {"valor": item["valor"], **item["rastro"]}
        for chave, item in sorted(_itens(ficha).items())
    }


def test_gabarito_por_item(ficha):
    """Cada item da CPFL com valor e rastro fixos. Mudou a conta de um item? Suba `VERSAO_DO_DOSSIE`
    em `base/dossie.py` e refaça o gabarito (`python -m tests.test_dossie_rastro`)."""
    gabarito = json.loads(GABARITO.read_text(encoding="utf-8"))
    atual = _atual(ficha)
    assert set(atual) == set(gabarito), "item novo ou removido: refaça o gabarito"
    for chave, esperado in gabarito.items():
        agora = atual[chave]
        if esperado["formula"] != agora["formula"]:
            assert esperado["versao_do_calculo"] != agora["versao_do_calculo"], (
                f"{chave}: a fórmula mudou sem subir a versão do cálculo"
            )
        valor = esperado["valor"]
        aproximado = (
            pytest.approx(valor, rel=1e-9) if isinstance(valor, float) else valor
        )
        assert agora == {**esperado, "valor": aproximado}, chave


if __name__ == "__main__":  # refaz o gabarito: python -m tests.test_dossie_rastro
    import tempfile

    with tempfile.TemporaryDirectory() as temporaria:
        pasta = Path(temporaria)
        _base_completa(pasta / "base")
        _montar(pasta / "base", pasta / "dossies")
        texto = json.dumps(
            _atual(_ficha_da_cpfl(pasta / "dossies")), ensure_ascii=False, indent=2
        )
    GABARITO.parent.mkdir(parents=True, exist_ok=True)
    GABARITO.write_text(texto + "\n", encoding="utf-8")
