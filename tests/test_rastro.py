"""O rastro de todo número do relatório da empresa (B-02; item 7 do lançamento: "como foi calculado"
em um clique). Todo número devolve a fórmula, a versão do cálculo, a fonte (o id da coleta, que leva a
licença) e quando o documento usado ficou público; o gabarito fixa cada indicador da WEG real das
amostras, para que mudar uma fórmula sem subir a versão quebre aqui."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src import demonstracoes as dm
from src import fundamentalista, fundamentos, notas_classicas
from src import relatorio_empresa as re_
from src.api_v1.esquemas import de_relatorio_da_empresa
from src.banco.coletas import LICENCAS
from src.banco.demonstracoes import DadosDaEmpresa
from src.rastro import FONTE, FORMULA, PUBLICADO_EM, VERSAO, DocumentoUsado, Rastro

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
GABARITO = Path(__file__).parent / "arquivos" / "rastro" / "weg.json"
WEG = "84.429.695/0001-11"
DFP_DE_2025_RECEBIDA = date(
    2026, 2, 25
)  # o recebido_em da DFP de 2025 da WEG na amostra
ULTIMO_FECHAMENTO = date(2026, 10, 16)


@pytest.fixture(scope="module")
def dados_da_weg():
    return _ler_a_weg()


def _ler_a_weg() -> DadosDaEmpresa:
    partes, documentos = [], []
    for arquivo in ("dfp_cia_aberta_2024.zip", "dfp_cia_aberta_2025.zip"):
        contas, docs = dm.ler_demonstracoes((PASTA / arquivo).read_bytes(), "DFP")
        partes.append(contas[contas["cnpj"] == WEG])
        documentos.append(docs[docs["cnpj"] == WEG])
    return DadosDaEmpresa(
        contas=pd.concat(partes).drop(columns="cnpj"),
        documentos=pd.concat(documentos),
        setor="Máquinas, Equipamentos, Veículos e Peças",
    )


def _entradas(dados, **outros):
    fechamentos = pd.Series(
        [49.0, 50.0], index=pd.to_datetime([date(2026, 10, 15), ULTIMO_FECHAMENTO])
    )
    campos = {"dados": dados, "cnpj": WEG, "empresa": "WEG S.A.", "ticker": "WEGE3.SA",
              "preco": 50.0, "fechamentos": fechamentos}  # fmt: skip
    return re_.Entradas(**(campos | outros))


def _numeros(relatorio: re_.Relatorio) -> dict[str, re_.Item]:
    """Os itens que são número (não frase), de todas as seções."""
    return {
        i.chave: i for s in relatorio.secoes for i in s.itens if i.unidade != re_.TEXTO
    }


# --- o contrato ------------------------------------------------------------------------------------
def _completo(**mudar) -> Rastro:
    documento = DocumentoUsado(
        "DFP de 31/12/2025, versão 1", date(2026, 2, 25), "https://x"
    )
    campos = {"formula": "lucro ÷ receita", "versao_do_calculo": "fundamentos 2",
              "fonte_id": "cvm", "publicado_em": date(2026, 2, 25), "documentos": (documento,)}  # fmt: skip
    return Rastro(**(campos | mudar))


def test_rastro_completo_nao_tem_o_que_faltar():
    assert _completo().o_que_falta() == []


def test_rastro_diz_cada_parte_que_falta():
    falta = _completo(formula="", versao_do_calculo="", fonte_id="", publicado_em=None)
    assert falta.o_que_falta() == [FORMULA, VERSAO, FONTE, PUBLICADO_EM]


def test_publicado_em_e_o_documento_mais_recente():
    documentos = (
        DocumentoUsado("DFP de 31/12/2025, versão 1", date(2026, 2, 25)),
        DocumentoUsado("ITR de 30/06/2026, versão 1", date(2026, 8, 1)),
        DocumentoUsado("fechamento sem data", None),
    )
    rastro = Rastro.dos_documentos("x", "fundamentos 2", "cvm", documentos)
    assert rastro.publicado_em == date(2026, 8, 1)
    assert Rastro.dos_documentos("x", "v", "cvm", ()).publicado_em is None


# --- as fórmulas ficam ao lado do código que calcula -----------------------------------------------
def test_todo_indicador_calculado_tem_formula(dados_da_weg):
    tela = fundamentos.calcular(dados_da_weg, 50.0).indicadores
    extra = fundamentalista.calcular(dados_da_weg).indicadores
    assert set(tela) == set(fundamentos.FORMULAS)
    assert set(extra) == set(fundamentalista.FORMULAS) - set(
        fundamentalista.DOS_DIVIDENDOS
    )
    assert all(fundamentos.FORMULAS.values()) and all(fundamentalista.FORMULAS.values())


def test_notas_classicas_tem_versao():
    assert notas_classicas.VERSAO_DAS_NOTAS_CLASSICAS


# --- todo número do relatório tem o rastro inteiro -------------------------------------------------
def test_todo_numero_do_relatorio_tem_o_rastro_inteiro(dados_da_weg):
    numeros = _numeros(re_.montar(_entradas(dados_da_weg)))
    assert (
        len(numeros) > 30
    )  # os indicadores da tela, os novos, as notas, o valuation e os dividendos
    sem_rastro = {
        c: i.rastro.o_que_falta() if i.rastro else ["rastro"]
        for c, i in numeros.items()
    }
    assert {c: f for c, f in sem_rastro.items() if f} == {}


def test_fonte_do_rastro_e_uma_coleta_com_licenca(dados_da_weg):
    for item in _numeros(re_.montar(_entradas(dados_da_weg))).values():
        assert item.rastro is not None
        assert {item.rastro.fonte_id, *item.rastro.outras_fontes} <= set(LICENCAS)


def test_publicado_em_e_a_entrega_da_dfp_nao_a_data_do_balanco(dados_da_weg):
    receita = _numeros(re_.montar(_entradas(dados_da_weg)))["receita"]
    assert receita.rastro is not None
    assert receita.rastro.publicado_em == DFP_DE_2025_RECEBIDA
    (documento,) = receita.rastro.documentos
    assert documento.nome == "DFP de 31/12/2025, versão 1"
    assert documento.url.startswith("https://www.rad.cvm.gov.br/")


def test_numero_com_preco_cita_o_yahoo_e_o_dia_do_fechamento(dados_da_weg):
    numeros = _numeros(re_.montar(_entradas(dados_da_weg)))
    for chave in ("p_l", "p_vp", "valor_de_mercado", "dividend_yield"):
        rastro = numeros[chave].rastro
        assert rastro is not None
        assert rastro.fonte_id == "cvm" and rastro.outras_fontes == ("yahoo",)
        fechamento = rastro.documentos[-1]
        assert (
            fechamento.publicado_em == ULTIMO_FECHAMENTO and "WEGE3" in fechamento.nome
        )
        assert rastro.publicado_em == ULTIMO_FECHAMENTO  # o insumo mais novo é o preço
    assert numeros["receita"].rastro.outras_fontes == ()  # type: ignore[union-attr]


def test_preco_sem_fechamentos_fica_sem_dia_e_o_rastro_segue_pela_dfp(dados_da_weg):
    p_l = _numeros(re_.montar(_entradas(dados_da_weg, fechamentos=None)))["p_l"].rastro
    assert p_l is not None and p_l.documentos[-1].publicado_em is None
    assert p_l.publicado_em == DFP_DE_2025_RECEBIDA


def test_crescimento_e_notas_classicas_citam_as_dfps_dos_anos_usados(dados_da_weg):
    numeros = _numeros(re_.montar(_entradas(dados_da_weg)))
    piotroski = numeros["piotroski"].rastro
    assert piotroski is not None
    assert [d.nome for d in piotroski.documentos] == [
        "DFP de 31/12/2024, versão 1",
        "DFP de 31/12/2025, versão 1",
    ]
    assert piotroski.formula == notas_classicas.PIOTROSKI_FORMULA
    assert piotroski.versao_do_calculo.startswith("notas clássicas ")
    crescimento = numeros["crescimento_receita"].rastro
    assert crescimento is not None and len(crescimento.documentos) == 2


def test_numero_indisponivel_tambem_diz_como_seria_calculado(dados_da_weg):
    sem_preco = _numeros(
        re_.montar(_entradas(dados_da_weg, preco=None, fechamentos=None))
    )
    p_l = sem_preco["p_l"]
    assert p_l.valor is None and p_l.rastro is not None and p_l.rastro.formula


def test_rastro_vai_no_json_e_na_api(dados_da_weg):
    relatorio = re_.montar(_entradas(dados_da_weg))
    texto = json.dumps(relatorio.como_dict(), ensure_ascii=False)
    assert '"publicado_em": "2026-02-25"' in texto
    api = de_relatorio_da_empresa(relatorio)
    receita = next(i for s in api.secoes for i in s.itens if i.chave == "receita")
    assert receita.rastro is not None and receita.rastro.fonte_id == "cvm"


def test_metricas_do_relatorio(dados_da_weg):
    relatorio = re_.montar(_entradas(dados_da_weg))
    metricas = relatorio.metricas()
    receita = next(m for m in metricas if m.chave == "receita")
    item = _numeros(relatorio)["receita"]
    assert (receita.entidade_id, receita.periodo, receita.valor) == (
        WEG,
        item.base,
        item.valor,
    )
    assert receita.rastro == item.rastro
    assert len({m.chave for m in metricas}) == len(
        metricas
    )  # um indicador, uma métrica
    texto = json.dumps([m.como_dict() for m in metricas], ensure_ascii=False)
    assert '"publicado_em": "2026-02-25"' in texto


def test_secao_trancada_nao_devolve_metrica():
    item = re_.Item("a", "A", "1", 1.0, "reais", "", rastro=_completo())
    trancada = re_.Secao("auditor_e_controladas", "x", [item], trancada=True)
    relatorio = re_.Relatorio("E", WEG, "X", "s", "g", [trancada], (), "", False)
    assert relatorio.metricas() == []


# --- o gabarito por indicador ----------------------------------------------------------------------
def _como_no_gabarito(item: re_.Item) -> dict:
    assert item.rastro is not None
    return {
        "valor": item.valor,
        "formula": item.rastro.formula,
        "versao_do_calculo": item.rastro.versao_do_calculo,
        "fonte_id": item.rastro.fonte_id,
        "outras_fontes": list(item.rastro.outras_fontes),
        "publicado_em": item.rastro.publicado_em.isoformat()
        if item.rastro.publicado_em
        else None,
        "documentos": [d.nome for d in item.rastro.documentos],
    }


def _atual(dados) -> dict[str, dict]:
    numeros = _numeros(re_.montar(_entradas(dados)))
    return {chave: _como_no_gabarito(item) for chave, item in sorted(numeros.items())}


def test_gabarito_por_indicador(dados_da_weg):
    """Cada indicador da WEG com valor, fórmula, versão, fonte e documentos fixos. Mudou a fórmula?
    Suba a versão do cálculo no módulo dela e refaça o gabarito (`python -m tests.test_rastro`)."""
    gabarito = json.loads(GABARITO.read_text(encoding="utf-8"))
    atual = _atual(dados_da_weg)
    assert set(atual) == set(gabarito), "indicador novo ou removido: refaça o gabarito"
    for chave, esperado in gabarito.items():
        agora = atual[chave]
        if esperado["formula"] != agora["formula"]:
            assert esperado["versao_do_calculo"] != agora["versao_do_calculo"], (
                f"{chave}: a fórmula mudou sem subir a versão do cálculo"
            )
        valor = esperado["valor"]
        aproximado = valor if valor is None else pytest.approx(valor, rel=1e-9)
        assert agora == {**esperado, "valor": aproximado}, chave


if __name__ == "__main__":  # refaz o gabarito: python -m tests.test_rastro
    GABARITO.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(_atual(_ler_a_weg()), ensure_ascii=False, indent=2)
    GABARITO.write_text(texto + "\n", encoding="utf-8")
