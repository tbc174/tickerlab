"""P0-4: a rodada completa com dados sintéticos e um registro temporário, e o carregador da base."""

import pandas as pd
import pytest

from tests.ajudantes_pares import CNPJS, dados_sinteticos
from trader import criterio_quant
from trader.estrategias import dados_f_b3, dados_pares, pares
from trader.estrategias import rodar_pares as rodar

# A rodada do fixture de módulo demora; num processo só ela roda uma vez (CI com --dist loadgroup).
pytestmark = pytest.mark.xdist_group("rodar_pares")
# Nos dados sintéticos, 12 meses de formação não bastam para o teste de cointegração passar a
# correção de Benjamini-Hochberg (ver o relatório da ficha); com 24 os pares verdadeiros passam.
P = pares.Parametros(meses_de_formacao=24)


@pytest.fixture(scope="module")
def rodada(tmp_path_factory):
    registro = rodar.abrir_registro(tmp_path_factory.mktemp("pares") / "registro.db")
    dados = dados_sinteticos()
    saida = rodar.executar(dados, registro, P)
    return dados, registro, saida


def test_registra_uma_tentativa_na_familia_p0_4(rodada):
    _, registro, saida = rodada
    assert registro.contar() == 1
    guardado = registro.obter(saida["id"])
    assert guardado["familia"] == "P0-4"
    assert guardado["spec"]["pre_registro"] == criterio_quant.HASH_DO_CRITERIO
    assert guardado["spec"]["z_entrada"] == 2.0
    assert guardado["resultado"]["veredito"]["itens"]
    assert guardado["resultado"]["vizinhos"]  # o platô fica dentro da tentativa
    assert guardado["resultado"]["sobrevivencia"]["deslistadas"] == 1
    assert guardado["resultado"]["janelas"][0]["pares"]


def test_rodar_de_novo_nao_conta_tentativa_nova(rodada):
    dados, registro, _ = rodada
    rodar.executar(dados, registro, P)
    assert registro.contar() == 1


def test_veredito_tem_os_itens_do_pre_registro_sem_pbo(rodada):
    veredito = rodada[2]["veredito"]
    itens = {i.codigo: i for i in veredito.itens}
    assert {"A1", "A2", "A3", "A6", "V"} <= set(itens)
    assert itens["A2"].passou and itens["A2"].valor is None  # a ficha não tem PBO
    assert itens[
        "V"
    ].passou  # executar no sinal infla, reexecução idêntica, dados, corte


def test_o_candidato_opera_e_paga_aluguel(rodada):
    resumo = rodada[2]["resumo"]
    assert resumo["operacoes"] > 0
    assert resumo["aluguel"] > 0
    assert resumo["fechadas_no_dia_da_entrada"] == 0


def test_teste_do_brasil_tem_as_quatro_partes(rodada):
    brasil = rodada[2]["brasil"]
    assert set(brasil) == {"aluguel", "lote", "conjuntos", "deslistadas"}
    assert set(brasil["aluguel"]) == set(rodar.TAXAS_DO_ALUGUEL)
    assert set(brasil["conjuntos"]) == set(rodar.CONJUNTOS)
    aluguel = [brasil["aluguel"][n]["aluguel"] for n in rodar.TAXAS_DO_ALUGUEL]
    assert aluguel == sorted(aluguel)  # mais taxa, mais aluguel
    assert (
        brasil["lote"]["lote de 100"]["operacoes"]
        <= brasil["lote"]["ações inteiras (candidato)"]["operacoes"]
    )
    on_pn = brasil["conjuntos"]["só ON/PN da mesma empresa"]
    assert on_pn["pares_selecionados"] <= len(rodada[2]["janelas"])  # um par ON/PN só
    assert all(
        {"sharpe_do_excesso", "retorno_anual", "aluguel", "imposto"} <= set(v)
        for parte in brasil.values()
        for v in parte.values()
    )


def test_bruto_sem_custos_e_estresse_mais_caro(rodada):
    saida = rodada[2]
    assert saida["bruto"]["custos"] == 0 and saida["bruto"]["aluguel"] == 0
    assert saida["estresse"]["custos"] > saida["resumo"]["custos"]


def test_regua_vizinhos_e_tentativas(rodada):
    saida = rodada[2]
    assert set(saida["reguas"]) == {"CDI"}
    assert set(saida["vizinhos"]) == set(rodar.VIZINHOS)
    assert saida["tentativas_totais"] >= criterio_quant.tentativas_anteriores() + 1


def test_vizinhos_de_formacao_ficam_no_periodo_do_candidato():
    indice = pd.bdate_range("2020-01-01", periods=5)
    cdi = pd.Series(0.001, index=pd.bdate_range("2019-12-01", "2020-02-01"))
    mais_tarde = pd.Series(0.01, index=indice[2:])
    serie = rodar._no_periodo(mais_tarde, indice, cdi)
    assert list(serie.index) == list(indice)
    assert serie.iloc[:2].tolist() == [0.001, 0.001]  # no caixa antes da 1ª janela
    assert serie.iloc[2:].tolist() == [0.01, 0.01, 0.01]


def test_sem_pares_a_rodada_nao_quebra(tmp_path):
    """Com a formação da ficha (12 meses), nenhum par sintético passa: reprova no A1 sem quebrar."""
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    saida = rodar.executar(dados_sinteticos(), registro)
    assert registro.contar() == 1
    assert not saida["veredito"].aprovado
    assert (
        saida["resumo"]["operacoes"] == 0
    )  # nem os pares verdadeiros passam com 12 meses
    assert saida["veredito"] is rodar.VEREDITO_SEM_OPERACAO
    assert saida["veredito"].reprovados == ["A1"]
    assert saida["acaso"]["p_valor"] == 1.0
    texto = rodar.escrever_relatorio(saida, tmp_path).read_text(encoding="utf-8")
    assert "## As janelas" in texto


def test_sem_deslistadas_o_veredito_reprova_por_dados(tmp_path):
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    saida = rodar.executar(dados_sinteticos(com_deslistada=False), registro, P)
    assert saida["sobrevivencia"]["vies"]
    assert not saida["veredito"].aprovado
    assert not {i.codigo: i for i in saida["veredito"].itens}["V"].passou
    texto = rodar.escrever_relatorio(saida, tmp_path).read_text(encoding="utf-8")
    assert "Viés de sobrevivência" in texto


def test_pre_registro_alterado_nao_roda_nem_registra(tmp_path, monkeypatch):
    def recusar(*_, **__):
        raise criterio_quant.PreRegistroAlteradoError("mudou")

    monkeypatch.setattr(rodar.criterio_quant, "conferir", recusar)
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    with pytest.raises(criterio_quant.PreRegistroAlteradoError):
        rodar.executar(dados_sinteticos(), registro, P)
    assert registro.contar() == 0


def test_relatorio_e_escrito_com_limites_e_cuidados(rodada, tmp_path):
    texto = rodar.escrever_relatorio(rodada[2], tmp_path).read_text(encoding="utf-8")
    assert "Veredito dos pares cointegrados na B3" in texto
    assert "| V |" in texto
    assert "teste do Brasil" in texto
    assert "Aluguel da perna vendida" in texto
    assert "OPA e deslistagem" in texto
    assert "## Limites e cuidados" in texto
    assert "recomendação de investimento" in texto


# --- a base ---------------------------------------------------------------------------------------


def test_conferir_base_nao_pede_a_quantidade_de_acoes(tmp_path):
    faltas = dados_pares.conferir_base(tmp_path)
    assert faltas[0] == "COTAHIST_A2009.ZIP"
    assert "precos_ajustados.parquet" in faltas
    assert dados_f_b3.ARQUIVO_DE_ACOES not in faltas
    assert len(faltas) == 15 + 1
    assert dados_f_b3.ARQUIVO_DE_ACOES in dados_f_b3.conferir_base(tmp_path)


def test_main_sem_base_e_inconclusiva_e_nao_abre_o_registro(
    tmp_path, monkeypatch, capsys
):
    def nao_abrir(*_, **__):
        raise AssertionError("o registro não pode ser aberto sem a base")

    monkeypatch.setattr(rodar, "abrir_registro", nao_abrir)
    assert rodar.main(tmp_path) == rodar.SAIDA_SEM_BASE
    saida = capsys.readouterr().out
    assert saida.startswith("INCONCLUSIVA")
    assert "P0-4" in saida and "COTAHIST_A2009.ZIP" in saida


def test_carregar_tabelas_sem_base_falha_listando_o_que_falta(tmp_path):
    with pytest.raises(FileNotFoundError, match="P0-4"):
        dados_pares.carregar_tabelas(tmp_path, tmp_path)


def _fca(tmp_path, ano, linhas):
    pasta = tmp_path / "fca_geral"
    pasta.mkdir(exist_ok=True)
    pd.DataFrame(linhas).to_parquet(pasta / f"{ano}.parquet")


def test_setores_do_fca_ponto_no_tempo_e_sem_o_holdout(tmp_path):
    cnpj = CNPJS["AAA"]
    _fca(
        tmp_path,
        2015,
        [
            {"cnpj": cnpj, "setor": "Energia", "conhecido_em": "2015-05-29", "x": 1},
            {"cnpj": "99", "setor": None, "conhecido_em": "2015-05-29", "x": 1},
        ],
    )
    _fca(
        tmp_path,
        2023,
        [
            {"cnpj": cnpj, "setor": "Bancos", "conhecido_em": "2023-05-30", "x": 1},
            {"cnpj": cnpj, "setor": "Varejo", "conhecido_em": "2023-10-02", "x": 1},
        ],
    )
    setores = dados_pares.setores_do_fca(tmp_path)
    assert list(setores.columns) == list(pares.COLUNAS_DOS_SETORES)
    assert setores["setor"].tolist() == ["Energia", "Bancos"]  # sem vazio nem holdout
    digitos = "".join(c for c in cnpj if c.isdigit())
    assert pares.setores_em(setores, pd.Timestamp("2016-01-04"))[digitos] == "Energia"
    assert pares.setores_em(setores, pd.Timestamp("2023-06-01"))[digitos] == "Bancos"


def test_setores_do_fca_sem_arquivos_vem_vazio(tmp_path):
    setores = dados_pares.setores_do_fca(tmp_path)
    assert setores.empty
    assert list(setores.columns) == list(pares.COLUNAS_DOS_SETORES)
