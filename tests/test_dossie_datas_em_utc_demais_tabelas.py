"""Dossiê: as demais tabelas da ficha com a data em UTC (com fuso) contra `hoje` sem fuso.

Continuação de `test_dossie_datas_em_utc.py`: na base real várias colunas de data chegam como momento em
UTC, e `hoje` é um dia sem fuso. Comparar as duas coisas levanta TypeError, e cortar no instante errado
deixaria entrar (ou sumir) um dado do dia seguinte. Em cada teste a linha "antes" já era pública e a
"depois" só ficou pública um dia depois de `hoje`: o corte do futuro tem de pegar essa diferença.
As tabelas são de mentira e o momento fica perto da meia-noite de UTC.
"""

import pandas as pd

from base import dossie

HOJE = pd.Timestamp("2026-06-30")
ANTES = "2026-03-01T23:30:00Z"  # já divulgado
DEPOIS = "2026-07-01T00:30:00Z"  # depois de `hoje`: não pode entrar


def _utc(*momentos: str) -> pd.Series:
    return pd.Series(pd.to_datetime(list(momentos), utc=True))


def test_lucro_por_exercicio_corta_o_futuro_com_data_em_utc():
    como_era = pd.DataFrame(
        {
            "demonstracao": ["DRE", "DRE"],
            "documento": ["DFP", "DFP"],
            "grupo": ["con", "con"],
            "descricao": ["Lucro/Prejuízo do Período"] * 2,
            "conta": ["3.11", "3.11"],
            "fim": ["2024-12-31", "2025-12-31"],
            "valor": [10.0, 20.0],
            "divulgado_em": _utc(ANTES, DEPOIS),
        }
    )
    tabela = dossie._lucro_por_exercicio(como_era, HOJE)
    assert tabela["exercicio"].tolist() == [2024]


def test_releases_corta_o_futuro_com_data_em_utc():
    releases = pd.DataFrame(
        {
            "periodo": ["2024", "2025"],
            "referencia": ["a", "b"],
            "linha": ["lucro", "lucro"],
            "periodo_lido": ["2024", "2025"],
            "leitura": ["x", "x"],
            "classe": ["igual", "igual"],
            "versao": [1, 1],
            "data_entrega": _utc(ANTES, DEPOIS),
            "publico_em": _utc(ANTES, DEPOIS),
            "valor_release_reais": [1.0, 1.0],
            "valor_oficial_reais": [1.0, 1.0],
            "diferenca_pct": [0.0, 0.0],
            "link": ["l1", "l2"],
        }
    )
    itens, _ = dossie._releases(releases, HOJE)
    comparados = next(i for i in itens if i["chave"] == "releases_comparados")
    assert comparados["valor"] == 1  # o release de depois de hoje fica fora


def test_insiders_corta_o_futuro_com_data_em_utc():
    negociacoes = pd.DataFrame(
        {
            "entregue_em": _utc(ANTES, DEPOIS),
            "data": _utc("2026-02-27T23:30:00Z", "2026-06-29T23:30:00Z"),
            "operacao": ["compra", "compra"],
            "cargo": ["Diretor", "Diretor"],
            "valor": [100.0, 900.0],
            "referencia": ["a", "b"],
        }
    )
    itens, _ = dossie._insiders(negociacoes, HOJE)
    compras = next(i for i in itens if i["chave"] == "insiders_compras_12m")
    assert compras["valor"] == 100.0  # a entrega de depois de hoje fica fora


def test_eventos_de_capital_corta_o_futuro_com_data_em_utc():
    eventos = pd.DataFrame(
        {
            "data": _utc(ANTES, DEPOIS),
            "tipo": ["Desdobramento", "Bonificação"],
            "fator": [2.0, 1.1],
            "acoes_novas": [1, 1],
            "valor": [0.0, 0.0],
            "referencia": ["a", "a"],
            "versao": [1, 1],
        }
    )
    _, tabela = dossie._eventos_de_capital(eventos, HOJE)
    assert tabela["tipo"].tolist() == ["Desdobramento"]


def test_proventos_por_exercicio_corta_o_futuro_com_data_em_utc():
    proventos = pd.DataFrame(
        {
            "conhecido_em": _utc(ANTES, DEPOIS),
            "exercicio": _utc("2025-01-01T00:00:00Z", "2025-12-31T00:00:00Z"),
            "referencia": ["a", "b"],
            "versao": [1, 1],
            "lucro_ajustado": [1.0, 2.0],
            "dividendo_total": [0.5, 0.7],
            "payout": [0.5, 0.35],
        }
    )
    tabela = dossie._proventos_por_exercicio(proventos, HOJE)
    assert tabela["lucro_ajustado"].tolist() == [1.0]


def test_por_exercicio_do_fre_com_fim_do_exercicio_em_utc():
    tabela = pd.DataFrame(
        {
            "conhecido_em": _utc(ANTES, ANTES),
            "referencia": ["a", "a"],
            "versao": [1, 1],
            "fim_do_exercicio": _utc("2025-12-31T00:00:00Z", "2026-12-31T00:00:00Z"),
        }
    )
    encerrados = dossie._por_exercicio(tabela, HOJE)
    assert len(encerrados) == 1  # o exercício que termina depois de hoje é o previsto


def test_ratings_publicos_com_data_em_utc():
    ratings = pd.DataFrame(
        {
            "publico_em": _utc(ANTES, DEPOIS),
            "situacao_extracao": [dossie.EXTRAIDO] * 2,
            "agencia": ["A", "B"],
            "nota": ["AAA", "AA"],
            "escala": ["nacional", "nacional"],
            "acao": ["afirmou", "rebaixou"],
            "data_acao": _utc(ANTES, DEPOIS),
            "documento": ["d1", "d2"],
        }
    )
    publicos = dossie._ratings_publicos(ratings, HOJE)
    assert publicos["agencia"].tolist() == ["A"]


def test_assembleias_publicas_com_data_em_utc():
    assembleias = pd.DataFrame(
        {
            "publico_em": _utc(ANTES, DEPOIS),
            "documento": [dossie.ASSEMBLEIA] * 2,
            "protocolo": ["p1", "p2"],
            "versao": [1, 1],
        }
    )
    publicas = dossie._assembleias_publicas(assembleias, HOJE)
    assert publicas["protocolo"].tolist() == ["p1"]


def test_ligacoes_dos_bancos_com_data_base_em_utc():
    ligacao = pd.DataFrame(
        {
            "cod_inst": ["1", "2"],
            "cnpj": ["11111111000111", "22222222000122"],
            "instituicao": ["Banco A", "Banco B"],
            "ligado_por": ["cnpj", "cnpj"],
            "data_base": _utc(ANTES, DEPOIS),
        }
    )
    ligadas = dossie.ligacoes_dos_bancos(ligacao, {"1", "2"}, HOJE)
    assert len(ligadas) == 1  # a data-base de depois de hoje ainda não era pública
    assert ligadas["desde"].dt.tz is None


def test_fatos_da_cvm_com_conhecido_em_utc():
    insolvencia = pd.DataFrame(
        {
            "rotulo": ["recuperacao_judicial"] * 2,
            "protocolo": ["p1", "p2"],
            "referencia": ["2026-02-01", "2026-06-01"],
            "conhecido_em": _utc(ANTES, DEPOIS),
            "link": ["l1", "l2"],
        }
    )
    fatos = dossie._fatos_da_cvm(insolvencia, HOJE)
    assert fatos["link"].tolist() == ["l1"]


def test_fatos_da_receita_com_disponivel_em_utc():
    especial = pd.DataFrame(
        {
            "rotulo": ["recuperacao_judicial"] * 2,
            "data_situacao_especial": ["2026-02-01", "2026-06-01"],
            "disponivel_em": _utc(ANTES, DEPOIS),
        }
    )
    fatos = dossie._fatos_da_receita(especial, HOJE)
    assert fatos["aconteceu_em"].dt.strftime("%Y-%m-%d").tolist() == ["2026-02-01"]


def test_ratings_completos_com_data_em_utc():
    ratings = pd.DataFrame(
        {
            "publico_em": _utc(ANTES, DEPOIS),
            "situacao_extracao": [dossie.EXTRAIDO] * 2,
            "agencia": ["A", "A"],
            "nota": ["AAA", "AA"],
            "nota_original": ["AAA", "AA"],
            "escala": ["nacional", "nacional"],
            "acao": ["afirmacao", "rebaixamento"],
            "perspectiva": ["estável", "negativa"],
            "data_acao": _utc(ANTES, DEPOIS),
            "link": ["l1", "l2"],
        }
    )
    itens, tabelas = dossie._ratings(ratings, HOJE)
    rebaixamentos = next(i for i in itens if i["chave"] == "ratings_rebaixamentos_12m")
    assert rebaixamentos["valor"] == 0  # o rebaixamento de depois de hoje fica fora
    assert tabelas["ratings"]["publico_em"].dt.tz is None


def test_assembleias_completas_com_data_em_utc():
    assembleias = pd.DataFrame(
        {
            "publico_em": _utc(ANTES, DEPOIS),
            "documento": [dossie.ASSEMBLEIA] * 2,
            "protocolo": ["p1", "p2"],
            "versao": [1, 1],
            "especie": ["AGD", "AGD"],
            "assunto": ["a", "b"],
            "link": ["l1", "l2"],
        }
    )
    itens, tabelas = dossie._assembleias(assembleias, HOJE)
    assert itens[0]["valor"] == 1
    assert tabelas["assembleias_recentes"]["link"].tolist() == ["l1"]


def test_insolvencia_com_contestacao_em_utc():
    insolvencia = pd.DataFrame(
        {
            "rotulo": ["recuperacao_judicial"],
            "protocolo": ["p1"],
            "referencia": ["2026-02-01"],
            "conhecido_em": _utc(ANTES),
            "link": ["l1"],
        }
    )
    contestacoes = pd.DataFrame(
        {
            "cnpj": ["11111111000111", "11111111000111"],
            "registro": ["recuperacao_judicial"] * 2,
            "aconteceu_em": [pd.NaT, pd.NaT],
            "recebida_em": _utc(ANTES, DEPOIS),
            "texto": ["a empresa contesta", "texto de depois de hoje"],
        }
    )
    secao = dossie.secao_insolvencia(insolvencia, None, contestacoes, HOJE)
    assert secao is not None
    assert "texto de depois de hoje" not in str(secao)
    assert "a empresa contesta" in str(secao)


def test_raizes_do_fre_em_dia_com_conhecido_em_em_utc():
    controladas = pd.DataFrame(
        {
            "cnpj_companhia": ["11111111000111", "22222222000122"],
            "cnpj": ["33333333000133", "44444444000144"],
            "referencia": ["2026-01-01", "2026-01-01"],
            "versao": [1, 1],
            "conhecido_em": _utc(ANTES, DEPOIS),
        }
    )
    pares = dossie.raizes_do_fre_em_dia(controladas, HOJE)
    assert pares == {
        ("11111111", "33333333")
    }  # o FRE entregue depois de hoje fica fora
