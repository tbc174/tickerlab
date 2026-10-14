"""Evidências (etapa 1 dos porquês): o formato único, as regras dele (sem olhar o futuro, modelo só
com acerto) e o adaptador das notas da tela, com a mesma frase e o mesmo número."""

import json
from dataclasses import replace
from datetime import date

import pandas as pd
import pytest

from src import demonstracoes as dm
from src import evidencias as ev
from src import fundamentos, notas
from src.padroes import VERSAO_DOS_PADROES
from src.setores import grupo_do_setor

SETOR = "Energia Elétrica"
GRUPO = grupo_do_setor(SETOR)
PERCENTIS = {"10": 0.01, "20": 0.02, "25": 0.025, "33": 0.033, "40": 0.04, "50": 0.05,
             "60": 0.06, "67": 0.067, "75": 0.075, "80": 0.08, "90": 0.09}  # fmt: skip
CORTE = date(2025, 4, 30)
ENTREGA_1, ENTREGA_2 = date(2025, 3, 20), date(2025, 6, 10)


def _evidencia(**mudancas) -> ev.Evidencia:
    base = {
        "id": "macro.selic.subiu",
        "tipo": ev.MACRO,
        "ativo": None,
        "frase": "A Selic subiu 1 ponto em 12 meses.",
        "valor": 0.01,
        "unidade": fundamentos.FRACAO,
        "data_de_corte": CORTE,
        "divulgado_em": date(2025, 3, 19),
        "fonte": "BCB, SGS 432",
        "regra": "macro/selic@1",
        "forca": ev.FATO,
    }
    return ev.Evidencia(**{**base, **mudancas})


# --- o formato -------------------------------------------------------------------------------------
def test_evidencia_vira_json_com_datas_iso():
    acerto = ev.Acerto("erro médio absoluto", 0.21, 0.27, "2015-2025", date(2026, 1, 5))
    modelo = _evidencia(forca=ev.MODELO, tipo=ev.QUANTITATIVO, acerto=acerto)
    dados = modelo.como_dict()
    assert dados["data_de_corte"] == "2025-04-30"
    assert dados["acerto"]["testado_em"] == "2026-01-05"
    json.dumps(dados)


def test_numero_divulgado_depois_do_corte_e_recusado():
    """Sem olhar o futuro: a evidência não existe antes de o número ser público."""
    with pytest.raises(ev.EvidenciaInvalidaError, match="depois do corte"):
        _evidencia(divulgado_em=date(2025, 5, 2))


def test_divulgado_no_proprio_dia_do_corte_vale():
    assert _evidencia(divulgado_em=CORTE).divulgado_em == CORTE


def test_indisponivel_tem_motivo_e_nenhuma_data():
    falta = _evidencia(valor=None, divulgado_em=None, frase="Sem a dívida no balanço.")
    assert falta.valor is None


def test_numero_sem_data_de_divulgacao_e_recusado():
    with pytest.raises(ev.EvidenciaInvalidaError, match="sem data"):
        _evidencia(divulgado_em=None)


def test_modelo_so_fala_com_o_acerto_contra_o_ingenuo():
    with pytest.raises(ev.EvidenciaInvalidaError, match="sem o acerto"):
        _evidencia(forca=ev.MODELO)


def test_fato_e_padrao_nao_levam_acerto():
    acerto = ev.Acerto("erro", 1.0, 2.0, "2020", date(2026, 1, 1))
    with pytest.raises(ev.EvidenciaInvalidaError, match="só modelo"):
        _evidencia(acerto=acerto)


@pytest.mark.parametrize(
    ("campo", "valor"), [("tipo", "astrologia"), ("forca", "palpite")]
)
def test_tipo_e_forca_desconhecidos_sao_recusados(campo, valor):
    with pytest.raises(ev.EvidenciaInvalidaError, match="desconhecid"):
        _evidencia(**{campo: valor})


# --- o adaptador das notas -------------------------------------------------------------------------
def _padroes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "grupo": GRUPO,
                "indicador": "margem_liquida",
                "empresas": 40,
                "percentis": PERCENTIS,
            }
        ]
    )


def test_nota_vira_evidencia_com_a_mesma_frase_e_o_mesmo_numero_da_tela():
    (nota,) = notas.notas_da_empresa(
        {"margem_liquida": 0.085}, GRUPO, _padroes(), CORTE
    )
    evidencia = ev.de_nota(nota, "TAEE11.SA", CORTE, ENTREGA_1)
    assert evidencia.frase == nota.texto and evidencia.valor == nota.valor
    assert evidencia.id == "fund.margem_liquida.otimo"
    assert evidencia.regra == f"padroes/margem_liquida@{VERSAO_DOS_PADROES}"
    assert (evidencia.tipo, evidencia.forca) == (ev.FUNDAMENTALISTA, ev.PADRAO)
    assert evidencia.limites == (notas.AVISO,)
    assert evidencia.fonte == notas.FONTE


def test_nota_por_faixa_fixa_tambem_vira_evidencia():
    nota = notas.nota_por_faixa("conversao_de_caixa", 2.0)
    assert nota is not None
    evidencia = ev.de_nota(nota, "PETR4.SA", CORTE, ENTREGA_1)
    assert evidencia.id == "fund.conversao_de_caixa.conferir-o-lucro"
    assert evidencia.frase == nota.texto
    assert evidencia.unidade == fundamentos.VEZES
    assert evidencia.regra == f"faixa-fixa/conversao_de_caixa@{notas.VERSAO_DAS_FAIXAS}"
    assert evidencia.limites == (ev.LIMITE_DA_FAIXA,)


def test_numero_em_conferencia_leva_o_aviso_na_frase():
    (nota,) = notas.notas_da_empresa(
        {"margem_liquida": 0.085}, GRUPO, _padroes(), CORTE, em_conferencia=True
    )
    assert "Número em conferência" in ev.de_nota(nota, None, CORTE, ENTREGA_1).frase


# --- sem olhar o futuro, do balanço até a evidência ------------------------------------------------
def _conta(conta: str, valor: float, versao: int, periodo: str = dm.EXERCICIO) -> dict:
    referencia = date(2024, 12, 31)
    return {
        "cnpj": "A", "documento": "DFP", "referencia": referencia, "versao": versao,
        "periodo": periodo, "inicio": date(2024, 1, 1) if periodo == dm.EXERCICIO else None,
        "fim": referencia, "conta": conta, "valor": valor,
    }  # fmt: skip


def _versao(versao: int, lucro: float) -> list[dict]:
    return [
        _conta("receita", 1000.0, versao),
        _conta("ebit", 150.0, versao),
        _conta("lucro_liquido", lucro, versao),
        _conta("patrimonio_liquido", 500.0, versao, dm.POSICAO),
        _conta("ativo_total", 2000.0, versao, dm.POSICAO),
    ]


def _entrega(versao: int, recebido: date) -> dict:
    return {
        "cnpj": "A", "documento": "DFP", "referencia": date(2024, 12, 31),
        "versao": versao, "recebido_em": pd.Timestamp(recebido),
    }  # fmt: skip


def _entrada(com_a_reapresentacao: bool) -> ev.EntradaFundamentalista:
    """A DFP de 2024 (lucro 85) e, se pedido, a reapresentação de junho (lucro 50)."""
    contas, documentos = _versao(1, 85.0), [_entrega(1, ENTREGA_1)]
    if com_a_reapresentacao:
        contas += _versao(2, 50.0)
        documentos.append(_entrega(2, ENTREGA_2))
    return ev.EntradaFundamentalista(
        pd.DataFrame(contas), pd.DataFrame(documentos), SETOR, _padroes(), "TAEE11.SA"
    )


def test_cortar_o_futuro_nao_muda_as_evidencias_do_passado():
    com_futuro = ev.fundamentalistas_em(_entrada(com_a_reapresentacao=True), CORTE)
    sem_futuro = ev.fundamentalistas_em(_entrada(com_a_reapresentacao=False), CORTE)
    assert com_futuro == sem_futuro
    (margem,) = com_futuro
    assert margem.valor == pytest.approx(0.085)
    assert margem.divulgado_em == ENTREGA_1


def test_depois_da_reapresentacao_vale_o_numero_novo():
    (margem,) = ev.fundamentalistas_em(
        _entrada(com_a_reapresentacao=True), date(2025, 7, 31)
    )
    assert margem.valor == pytest.approx(0.05)
    assert margem.divulgado_em == ENTREGA_2
    assert margem.id == "fund.margem_liquida.medio"


def test_nada_publico_ate_o_corte_nao_gera_evidencia():
    assert ev.fundamentalistas_em(_entrada(False), date(2025, 1, 31)) == []


def test_ultima_divulgacao_ignora_o_que_veio_depois():
    documentos = pd.DataFrame([_entrega(1, ENTREGA_1), _entrega(2, ENTREGA_2)])
    assert ev.ultima_divulgacao(documentos, CORTE) == ENTREGA_1
    assert ev.ultima_divulgacao(documentos, ENTREGA_2) == ENTREGA_2


def test_evidencia_e_imutavel():
    evidencia = _evidencia()
    assert replace(evidencia, valor=0.02).valor == 0.02
    with pytest.raises(AttributeError):
        evidencia.valor = 0.5  # type: ignore[misc]
