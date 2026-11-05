"""A conferência automática do teor dos processos (plano de 03/11/2026, PR 2, grupo 4): amostra com
semente gravada, gabarito de um segundo modelo, regra e modelo que discordam deixam o campo vazio e
campo abaixo do critério não sai."""

import json
from datetime import date

import pandas as pd

from base import conferencia_processos as cp
from base.processos_teor import Leitura

SENTENCA = Leitura("sentenca", "procedente", "JULGO PROCEDENTE", 5000.0)
DESPACHO = Leitura("despacho", None, None, None)
ACORDAO = Leitura("acordao", "recurso_nao_provido", "NEGO PROVIMENTO", None)


def _resposta(tipo, resultado, valor):
    return {"tipo_de_ato": tipo, "resultado": resultado, "maior_valor": valor}


def test_sortear_repete_com_a_mesma_semente_e_so_pega_campo_preenchido():
    leituras = {f"s{n:03d}": SENTENCA for n in range(50)} | {
        f"d{n:03d}": DESPACHO for n in range(50)
    }
    amostra = cp.sortear(leituras, semente=20261108, por_campo=10)
    assert amostra == cp.sortear(leituras, semente=20261108, por_campo=10)
    assert amostra != cp.sortear(leituras, semente=1, por_campo=10)
    assert len(amostra["tipo_de_ato"]) == 10
    # resultado e valor só existem nas sentenças: a amostra deles só tem sentença
    assert all(i.startswith("s") for i in amostra["resultado"])
    assert all(i.startswith("s") for i in amostra["valor_citado"])
    # menos itens que o tamanho da amostra: todos entram
    assert cp.sortear({"a": SENTENCA}, semente=1, por_campo=10)["resultado"] == ["a"]
    assert cp.sortear({"a": DESPACHO}, semente=1, por_campo=10)["resultado"] == []


def test_mascarar_tira_partes_advogados_e_cpf():
    texto = (
        "Autor: FULANO DE TAL, CPF 123.456.789-00. Ré: COMPANHIA EXEMPLO S.A. "
        "JULGO PROCEDENTE. - ADV: BELTRANO DA SILVA (OAB 12345/SP), Ciclano Souza - OAB/RJ 999"
    )
    mascarado = cp.mascarar(texto, ["FULANO DE TAL", "COMPANHIA EXEMPLO S.A."])
    for nome in (
        "FULANO",
        "COMPANHIA EXEMPLO",
        "BELTRANO",
        "Ciclano",
        "123.456",
        "12345",
    ):
        assert nome not in mascarado
    assert "[parte]" in mascarado and "[advogado]" in mascarado
    assert "JULGO PROCEDENTE" in mascarado


def test_pedido_leva_o_texto_mascarado_e_o_esquema_fechado():
    item = {
        "hash": "abc",
        "tipoDocumento": "Intimação",
        "texto": "<p>FULANO DE TAL x EMPRESA. JULGO PROCEDENTE o pedido.</p>",
        "destinatarios": [{"nome": "FULANO DE TAL", "polo": "A"}],
    }
    pedido = cp.pedido(item)
    assert pedido["model"] == cp.MODELO_DO_GABARITO
    enviado = json.dumps(pedido, ensure_ascii=False)
    assert "FULANO" not in enviado and "<p>" not in enviado
    assert "JULGO PROCEDENTE" in enviado and "Intimação" in enviado
    esquema = pedido["output_config"]["format"]["schema"]
    assert cp.NAO_IDENTIFICADO in esquema["properties"]["tipo_de_ato"]["enum"]
    assert cp.NENHUM in esquema["properties"]["resultado"]["enum"]
    assert esquema["additionalProperties"] is False


def test_medir_conta_acerto_por_campo_e_lista_quem_discordou():
    leituras = {"a": SENTENCA, "b": SENTENCA, "c": ACORDAO}
    amostra = {
        "tipo_de_ato": ["a", "b", "c"],
        "resultado": ["a", "b", "c"],
        "valor_citado": ["a", "b"],
    }
    respostas = {
        "a": _resposta("sentenca", "procedente", 5000.0),
        # o modelo leu improcedente e outro valor: discorda nos dois
        "b": _resposta("sentenca", "improcedente", 4000.0),
        # "c" não voltou: conta como erro nos campos em que foi sorteado
    }
    campos, discordantes = cp.medir(leituras, respostas, amostra)
    assert campos["tipo_de_ato"] == cp.Campo(casos=3, acertos=2)
    assert campos["resultado"] == cp.Campo(casos=3, acertos=1)
    assert campos["valor_citado"] == cp.Campo(casos=2, acertos=1)
    assert discordantes == {
        "tipo_de_ato": ("c",),
        "resultado": ("b", "c"),
        "valor_citado": ("b",),
    }


def test_valor_concorda_dentro_de_um_centavo():
    leituras = {"a": SENTENCA}
    amostra = {"tipo_de_ato": [], "resultado": [], "valor_citado": ["a"]}
    campos, _ = cp.medir(leituras, {"a": _resposta(None, None, 5000.004)}, amostra)
    assert campos["valor_citado"] == cp.Campo(casos=1, acertos=1)


def test_criterio_de_95_por_cento_escrito_antes_de_medir():
    assert cp.CRITERIO == 0.95
    assert cp.Campo(casos=100, acertos=95).aprovado
    assert not cp.Campo(casos=100, acertos=94).aprovado
    # campo sem caso nenhum não tem o que publicar
    assert not cp.Campo(casos=0, acertos=0).aprovado
    assert cp.Campo(casos=0, acertos=0).precisao is None


def _conferencia(feita_em, aprovados=cp.CAMPOS, discordantes=None, versao="v1"):
    return cp.Conferencia(
        feita_em=feita_em,
        versao_da_regra=versao,
        modelo=cp.MODELO_DO_GABARITO,
        semente=1,
        cobre_ate=feita_em,
        campos={c: cp.Campo(100, 100 if c in aprovados else 50) for c in cp.CAMPOS},
        discordantes={c: tuple((discordantes or {}).get(c, ())) for c in cp.CAMPOS},
    )


def test_gravar_e_ler_a_vigente_da_versao(tmp_path):
    cp.gravar(
        _conferencia(date(2026, 11, 1), discordantes={"resultado": ["x"]}), tmp_path
    )
    cp.gravar(
        _conferencia(
            date(2026, 11, 8),
            aprovados=("tipo_de_ato",),
            discordantes={"resultado": ["y"]},
        ),
        tmp_path,
    )
    # a de outra versão da regra não conta, mesmo mais nova
    cp.gravar(_conferencia(date(2026, 11, 9), versao="v0"), tmp_path)
    vigente = cp.vigente(tmp_path, "v1")
    assert vigente == cp.Vigente(
        feita_em=date(2026, 11, 8),
        cobre_ate=date(2026, 11, 8),
        aprovados=frozenset({"tipo_de_ato"}),
        # quem discordou numa amostra antiga continua vazio
        discordantes={
            "tipo_de_ato": frozenset(),
            "resultado": frozenset({"x", "y"}),
            "valor_citado": frozenset(),
        },
    )
    assert cp.vigente(tmp_path, "v2") is None
    assert len(cp.arquivos(tmp_path)) == 3


def _comunicacoes():
    return pd.DataFrame(
        {
            "id_na_fonte": ["a", "b", "c"],
            "visto_em": pd.to_datetime(["2026-11-01", "2026-11-01", "2026-11-10"]),
            "tipo_de_ato": ["sentenca", "sentenca", "sentenca"],
            "resultado": ["procedente", "improcedente", "procedente"],
            "resultado_trecho": [
                "JULGO PROCEDENTE",
                "JULGO IMPROCEDENTE",
                "JULGO PROCEDENTE",
            ],
            "valor_citado": [5000.0, 10.0, 1.0],
        }
    )


def test_aplicar_deixa_vazio_o_que_nao_passou():
    vigente = cp.Vigente(
        feita_em=date(2026, 11, 8),
        cobre_ate=date(2026, 11, 8),
        aprovados=frozenset({"tipo_de_ato", "resultado"}),
        discordantes={
            "tipo_de_ato": frozenset(),
            "resultado": frozenset({"b"}),
            "valor_citado": frozenset(),
        },
    )
    saida = cp.aplicar(_comunicacoes(), vigente)
    # "c" foi vista depois da amostra: espera a próxima conferência
    assert saida["tipo_de_ato"].tolist() == ["sentenca", "sentenca", None]
    # "b" discordou na amostra; o trecho segue o resultado
    assert saida["resultado"].tolist() == ["procedente", None, None]
    assert saida["resultado_trecho"].tolist() == ["JULGO PROCEDENTE", None, None]
    # o valor não passou no critério: a coluna inteira fica vazia
    assert saida["valor_citado"].isna().all()
    assert saida["teor_conferido_em"].tolist() == [date(2026, 11, 8)] * 2 + [None]


def test_aplicar_sem_conferencia_nao_publica_nada_do_teor():
    saida = cp.aplicar(_comunicacoes(), None)
    for coluna in (*cp.CAMPOS, "resultado_trecho", "teor_conferido_em"):
        assert saida[coluna].isna().all()
    assert saida["id_na_fonte"].tolist() == ["a", "b", "c"]
