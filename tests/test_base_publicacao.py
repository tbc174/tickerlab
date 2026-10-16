"""Quando cada informe apareceu na CVM (`visto_em`; relatórios de cruzamentos 5 e 7, 16/10/2026)."""

from datetime import UTC, datetime

import pandas as pd

from base import publicacao

CHAVE = ["competencia", "cnpj_fundo"]
SETEMBRO = pd.Timestamp("2026-09-30")


def _chaves(*fundos: str) -> pd.DataFrame:
    return pd.DataFrame({"competencia": SETEMBRO, "cnpj_fundo": list(fundos)})


def _dia(texto: str) -> pd.Timestamp:
    return pd.Timestamp(texto)


def test_fundo_que_entra_numa_versao_seguinte_e_visto_no_dia_dela():
    versoes = [
        (_dia("2026-10-14"), _chaves("A")),
        (_dia("2026-10-20"), _chaves("A", "B")),
    ]
    vistos = publicacao.primeiras_aparicoes(versoes, CHAVE, ausente_antes=False)
    por_fundo = dict(zip(vistos.cnpj_fundo, vistos.visto_em, strict=True))
    assert pd.isna(por_fundo["A"])  # já estava na 1ª versão: não sabemos quando entrou
    assert por_fundo["B"] == _dia("2026-10-20")


def test_arquivo_que_faltava_antes_da_1a_versao_data_todos_os_fundos_dela():
    versoes = [(_dia("2026-11-03"), _chaves("A", "B"))]
    vistos = publicacao.primeiras_aparicoes(versoes, CHAVE, ausente_antes=True)
    assert (vistos.visto_em == _dia("2026-11-03")).all()


def test_fundo_que_some_e_volta_fica_com_a_primeira_vez():
    versoes = [
        (_dia("2026-11-03"), _chaves("A")),
        (_dia("2026-11-04"), _chaves()),
        (_dia("2026-11-05"), _chaves("A")),
    ]
    vistos = publicacao.primeiras_aparicoes(versoes, CHAVE, ausente_antes=True)
    assert vistos.visto_em.tolist() == [_dia("2026-11-03")]


def test_sem_versao_nenhuma_nao_ha_aparicao():
    vistos = publicacao.primeiras_aparicoes([], CHAVE, ausente_antes=False)
    assert vistos.empty and list(vistos.columns) == [*CHAVE, publicacao.VISTO_EM]


def test_dia_da_coleta_e_o_dia_de_sao_paulo():
    # 02h10 de 15/10 em UTC ainda é 14/10 em São Paulo
    assert publicacao.dia_da_coleta(datetime(2026, 10, 15, 2, 10, tzinfo=UTC)) == _dia(
        "2026-10-14"
    )
    # o SQLite devolve sem fuso: é UTC
    sem_fuso = datetime(2026, 10, 15, 12, 0)  # noqa: DTZ001 (é o que o SQLite devolve)
    assert publicacao.dia_da_coleta(sem_fuso) == _dia("2026-10-15")


def test_atrasado_so_fica_publico_quando_foi_visto_e_o_prazo_continua_o_piso():
    tabela = pd.DataFrame(
        {
            "competencia": SETEMBRO,
            "cnpj_fundo": ["A", "B", "C", "C"],
            "disponivel_em": SETEMBRO + pd.Timedelta(days=45),  # 14/11
        }
    )
    vistos = pd.DataFrame(
        {
            "competencia": SETEMBRO,
            "cnpj_fundo": ["A", "B", "C"],
            "visto_em": [pd.NaT, _dia("2026-10-20"), _dia("2026-12-01")],
        }
    )
    saida = publicacao.com_visto_em(tabela, vistos, CHAVE)
    assert saida.visto_em.isna().tolist() == [True, False, False, False]
    assert saida.disponivel_em.tolist() == [
        _dia("2026-11-14"),  # sem data vista: o prazo
        _dia("2026-11-14"),  # visto antes do prazo: o prazo (piso)
        _dia("2026-12-01"),  # entregou atrasado: só quando apareceu
        _dia("2026-12-01"),
    ]
    assert len(saida) == len(tabela)


def test_chave_vista_em_dois_arquivos_vale_a_primeira_e_desconhecida_vence():
    vistos = pd.concat(
        [
            pd.DataFrame({"competencia": SETEMBRO, "cnpj_fundo": ["A", "B"], "visto_em": [_dia("2026-10-20"), pd.NaT]}),
            pd.DataFrame({"competencia": SETEMBRO, "cnpj_fundo": ["A", "B"], "visto_em": [_dia("2026-10-18"), _dia("2026-10-19")]}),
        ]
    )  # fmt: skip
    unicos = publicacao.uma_por_chave(vistos, CHAVE)
    por_fundo = dict(zip(unicos.cnpj_fundo, unicos.visto_em, strict=True))
    assert por_fundo["A"] == _dia("2026-10-18")
    assert pd.isna(
        por_fundo["B"]
    )  # já estava num arquivo antes de olharmos: não sabemos


def test_sem_nada_visto_fica_o_prazo_e_a_coluna_vazia():
    tabela = pd.DataFrame(
        {"competencia": [SETEMBRO], "cnpj_fundo": ["A"], "disponivel_em": [SETEMBRO]}
    )
    vazio = pd.DataFrame(columns=[*CHAVE, publicacao.VISTO_EM])
    saida = publicacao.com_visto_em(tabela, vazio, CHAVE)
    assert saida["visto_em"].isna().all() and saida["disponivel_em"].equals(
        tabela["disponivel_em"]
    )


def test_arquivo_de_uma_versao_so_nem_e_lido():
    def nao_leia(conteudo):
        raise AssertionError("não devia ler")

    unica = publicacao.Versao("u", "s", _dia("2026-10-14"), "caminho")
    assert publicacao.vistos_nas_versoes([unica], nao_leia, CHAVE).empty
