"""P0-5: a rodada completa com dados sintéticos e um registro temporário, e o carregador do IPE."""

import io
import sys

import pandas as pd
import pytest

from tests.ajudantes_pead import TICKERS, dados_sinteticos, deslistar
from trader import criterio_quant
from trader.estrategias import dados_f_b3, dados_pead, pead
from trader.estrategias import rodar_pead as rodar

# A rodada do fixture de módulo demora; num processo só ela roda uma vez (CI com --dist loadgroup).
pytestmark = pytest.mark.xdist_group("rodar_pead")
DESLISTADA = TICKERS[-1]


def _dados():
    return deslistar(dados_sinteticos(), DESLISTADA, pd.Timestamp("2015-09-15"))


@pytest.fixture(scope="module")
def rodada(tmp_path_factory):
    registro = rodar.abrir_registro(tmp_path_factory.mktemp("pead") / "registro.db")
    dados = _dados()
    saida = rodar.executar(dados, registro)
    return dados, registro, saida


def test_registra_uma_tentativa_na_familia_p0_5(rodada):
    _, registro, saida = rodada
    assert registro.contar() == 1
    guardado = registro.obter(saida["id"])
    assert guardado["familia"] == "P0-5"
    assert guardado["spec"]["pre_registro"] == criterio_quant.HASH_DO_CRITERIO
    assert guardado["spec"]["trimestres_do_desvio"] == 8
    assert guardado["resultado"]["veredito"]["itens"]
    assert guardado["resultado"]["vizinhos"]  # o platô fica dentro da tentativa
    assert guardado["resultado"]["estudo"]["por_tipo"]  # o CAR também
    assert guardado["resultado"]["sobrevivencia"]["deslistadas"] == 1


def test_rodar_de_novo_nao_conta_tentativa_nova(rodada):
    dados, registro, _ = rodada
    rodar.executar(dados, registro)
    assert registro.contar() == 1


def test_veredito_tem_os_itens_do_pre_registro_sem_pbo(rodada):
    itens = {i.codigo: i for i in rodada[2]["veredito"].itens}
    assert {"A1", "A2", "A3", "A6", "V"} <= set(itens)
    assert itens["A2"].passou and itens["A2"].valor is None  # a ficha não tem PBO


def test_periodo_comeca_na_primeira_posicao(rodada):
    saida = rodada[2]
    inicio, _ = saida["periodo"]
    assert pd.Timestamp(inicio) > pd.Timestamp("2012-06-01")  # a SUE pede 12 trimestres
    assert saida["resumo"]["exposicao_media"] > 0.3


def test_teste_do_brasil_otimista_e_deslistadas(rodada):
    saida = rodada[2]
    assert set(saida["brasil"]) == {
        "dia zero = D+1 (candidato)",
        "dia zero = D (otimista, proibido)",
    }
    assert saida["deslistadas"]["só sobreviventes"]["posicoes"] > 0
    assert saida["contagem"]["com_sue"] > 0


def test_bruto_sem_custos_e_estresse_mais_caro(rodada):
    saida = rodada[2]
    assert saida["bruto"]["custos"] == 0
    assert saida["estresse"]["custos"] > saida["resumo"]["custos"]


def test_reguas_vizinhos_e_tentativas(rodada):
    saida = rodada[2]
    assert set(saida["reguas"]) == {"CDI", rodar.REGUA_DO_IBOVESPA}
    assert set(saida["vizinhos"]) == set(rodar.VIZINHOS)
    assert saida["tentativas_totais"] >= criterio_quant.tentativas_anteriores() + 1


def test_vizinhos_sao_mais_ou_menos_20_por_cento():
    padrao = pead.Parametros()
    for mudanca in rodar.VIZINHOS.values():
        ((nome, valor),) = mudanca.items()
        base = getattr(padrao, nome)
        alvos = {base * 0.8, base * 1.2}
        if isinstance(
            base, int
        ):  # inteiro: o mais perto de ±20% (8 trimestres viram 6 e 10)
            alvos = {round(a) for a in alvos}
        assert any(valor == pytest.approx(a) for a in alvos)


def test_sem_eventos_a_rodada_nao_quebra(tmp_path):
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    dados = _dados()
    assert dados.documentos is not None
    vazio = pead.Dados(
        **{
            **dados.__dict__,
            "fundamentos": dados.fundamentos.iloc[:0],
            "documentos": dados.documentos.iloc[:0],
        }
    )
    saida = rodar.executar(vazio, registro)
    assert registro.contar() == 1
    assert saida["veredito"] is rodar.VEREDITO_SEM_OPERACAO
    assert saida["acaso"]["p_valor"] == 1.0
    texto = rodar.escrever_relatorio(saida, tmp_path).read_text(encoding="utf-8")
    assert "## Limites e cuidados" in texto


def test_pre_registro_alterado_nao_roda_nem_registra(tmp_path, monkeypatch):
    def recusar(*_, **__):
        raise criterio_quant.PreRegistroAlteradoError("mudou")

    monkeypatch.setattr(rodar.criterio_quant, "conferir", recusar)
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    with pytest.raises(criterio_quant.PreRegistroAlteradoError):
        rodar.executar(_dados(), registro)
    assert registro.contar() == 0


def test_relatorio_e_escrito_com_limites_e_cuidados(rodada, tmp_path):
    texto = rodar.escrever_relatorio(rodada[2], tmp_path).read_text(encoding="utf-8")
    assert "Veredito do PEAD (surpresa de lucro) na B3" in texto
    assert "| V |" in texto
    assert "O teste do Brasil" in texto
    assert "CAR (+1, +60)" in texto
    assert "Por tercil da SUE" in texto
    assert "## Limites e cuidados" in texto
    assert texto.count("recomendação de investimento") >= 2


# --- a base ---------------------------------------------------------------------------------------


def test_conferir_base_pede_o_ipe_e_nao_a_quantidade_de_acoes(tmp_path):
    faltas = dados_pead.conferir_base(tmp_path, tmp_path)
    assert faltas[0] == "COTAHIST_A2009.ZIP"
    assert dados_f_b3.ARQUIVO_DE_ACOES not in faltas
    assert any("IPE" in f for f in faltas)


def test_main_sem_base_e_inconclusiva_e_nao_abre_o_registro(
    tmp_path, monkeypatch, capsys
):
    def nao_abrir(*_, **__):
        raise AssertionError("o registro não pode ser aberto sem a base")

    monkeypatch.setattr(rodar, "abrir_registro", nao_abrir)
    assert rodar.main(tmp_path, tmp_path) == rodar.SAIDA_SEM_BASE
    saida = capsys.readouterr().out
    assert saida.startswith("INCONCLUSIVA")
    assert "P0-5" in saida


def test_documentos_do_ipe_so_do_desenvolvimento(tmp_path):
    pasta = tmp_path / dados_pead.PASTA_DO_IPE
    pasta.mkdir()
    linhas = pd.DataFrame(
        {
            "cnpj": ["a", "b", "c"],
            "categoria": "Fato Relevante",
            "tipo": "",
            "tema": "eventos",
            "referencia": ["2023-06-30", "2023-09-30", "2023-09-30"],
            "publicado_em": ["2023-07-01", "2023-09-08", "2023-10-20"],
            "versao": 1,
            "link": "x",
        }
    )
    linhas.to_parquet(pasta / "2023.parquet")
    documentos = dados_pead.documentos_do_ipe(tmp_path)
    assert list(documentos["cnpj"]) == ["a", "b"]  # 20/10/2023 é holdout
    assert set(documentos.columns) == set(pead.COLUNAS_DOS_DOCUMENTOS)
    assert dados_pead.documentos_do_ipe(tmp_path / "vazio").empty


def test_carregar_tabelas_sem_base_falha_listando_o_que_falta(tmp_path):
    with pytest.raises(FileNotFoundError, match="P0-5"):
        dados_pead.carregar_tabelas(tmp_path, tmp_path)


def test_imprimir_num_terminal_sem_utf8_nao_quebra(monkeypatch):
    # Regressão da tentativa 1: o β do relatório derrubou o print no cp1252 do Windows.
    bruto = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(bruto, encoding="cp1252"))
    rodar.imprimir("o β é estimado em 252 pregões")
    sys.stdout.flush()
    assert bruto.getvalue().decode("cp1252").startswith("o ? é estimado em 252 pregões")
