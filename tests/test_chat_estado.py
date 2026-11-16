"""O estado do chat para a tela "Perguntar" e as fontes de cada consulta (linha 903), sem banco nem rede.

Riscos que estes testes pegam: (1) a tela dizer "pode perguntar" quando a pergunta seria recusada, ou na
ordem errada das recusas; (2) o gasto em dinheiro sair na resposta da tela; (3) a lista de fontes depender
do texto do modelo, repetir fonte, crescer sem limite ou quebrar com resposta que não é JSON.
"""

import json
from dataclasses import replace

import pytest

from src.chat import estado as es
from src.chat.fontes import MAXIMO_DE_FONTES, FonteUsada, fontes_do_resultado
from src.planos import LIMITES_DO_CHAT

PRONTO = es.FatosDoChat(
    ligado=True,
    tem_organizacao=True,
    tem_chave_da_api=True,
    perguntas_hoje=0,
    perguntas_no_mes=0,
    pausado=False,
)


# ---------------------------------------------------------------- a situação


def test_tudo_certo_e_pronto():
    assert es.situacao_do_chat(PRONTO, LIMITES_DO_CHAT) == "pronto"


@pytest.mark.parametrize(
    ("mudanca", "situacao"),
    [
        ({"ligado": False}, "desligado"),
        ({"tem_organizacao": False}, "sem_organizacao"),
        ({"tem_chave_da_api": False}, "sem_chave"),
        ({"perguntas_hoje": LIMITES_DO_CHAT.perguntas_por_dia}, "cota_do_dia"),
        ({"perguntas_no_mes": LIMITES_DO_CHAT.perguntas_por_mes}, "cota_do_mes"),
        ({"pausado": True}, "pausado"),
    ],
)
def test_cada_recusa(mudanca, situacao):
    assert es.situacao_do_chat(replace(PRONTO, **mudanca), LIMITES_DO_CHAT) == situacao


def test_a_ordem_e_a_da_rota_de_perguntar():
    """Desligado vence tudo; a cota vem antes do teto, como em `POST /v1/chat`."""
    tudo_errado = es.FatosDoChat(
        ligado=False,
        tem_organizacao=False,
        tem_chave_da_api=False,
        perguntas_hoje=99,
        perguntas_no_mes=999,
        pausado=True,
    )
    assert es.situacao_do_chat(tudo_errado, LIMITES_DO_CHAT) == "desligado"
    cota_e_teto = replace(PRONTO, perguntas_hoje=99, pausado=True)
    assert es.situacao_do_chat(cota_e_teto, LIMITES_DO_CHAT) == "cota_do_dia"


def test_uma_abaixo_da_cota_ainda_pergunta():
    fatos = replace(
        PRONTO,
        perguntas_hoje=LIMITES_DO_CHAT.perguntas_por_dia - 1,
        perguntas_no_mes=LIMITES_DO_CHAT.perguntas_por_mes - 1,
    )
    assert es.situacao_do_chat(fatos, LIMITES_DO_CHAT) == "pronto"


# ---------------------------------------------------------------- a resposta da tela


def test_estado_para_a_tela_tem_os_numeros_dos_limites():
    estado = es.estado_para_a_tela(replace(PRONTO, perguntas_hoje=3), LIMITES_DO_CHAT)
    assert estado["pode_perguntar"] is True and estado["mensagem"] is None
    assert estado["perguntas_hoje"] == 3
    assert estado["perguntas_por_dia"] == LIMITES_DO_CHAT.perguntas_por_dia
    assert estado["perguntas_por_mes"] == LIMITES_DO_CHAT.perguntas_por_mes
    json.dumps(estado)  # tipos simples, prontos para virar JSON


def test_toda_recusa_tem_frase():
    for mudanca in ({"ligado": False}, {"tem_chave_da_api": False}, {"pausado": True}):
        estado = es.estado_para_a_tela(replace(PRONTO, **mudanca), LIMITES_DO_CHAT)
        assert estado["pode_perguntar"] is False and estado["mensagem"]


def test_desligado_diz_o_que_o_chat_vai_fazer():
    estado = es.estado_para_a_tela(replace(PRONTO, ligado=False), LIMITES_DO_CHAT)
    assert estado["mensagem"] == es.MENSAGEM_AINDA_NAO_LIGADO


def test_nenhum_campo_de_dinheiro():
    estado = es.estado_para_a_tela(PRONTO, LIMITES_DO_CHAT)
    assert not [
        c for c in estado if any(p in c for p in ("gasto", "custo", "teto", "dolar"))
    ]


def test_limites_usam_os_numeros_de_planos():
    limites = es.limites_para_a_tela(LIMITES_DO_CHAT)
    texto = " ".join(limites)
    assert f"Até {LIMITES_DO_CHAT.perguntas_por_dia} perguntas por dia" in texto
    assert "2.000 caracteres" in texto
    assert limites[-1] == "Nada aqui é recomendação de investimento."


def test_milhar_em_portugues():
    assert es._milhar(2000) == "2.000"
    assert es._milhar(120_000) == "120.000"
    assert es._milhar(12) == "12"


# ---------------------------------------------------------------- as fontes de cada consulta


def test_fontes_da_lista_e_dos_valores_uma_vez_cada_com_a_data_mais_nova():
    resposta = {
        "data": [
            {"value": 1, "source": "rfb-cnpj", "published_at": "2026-10-12"},
            {"value": 2, "source": "rfb-cnpj", "published_at": "2026-11-09T00:00:00Z"},
            {"nested": {"source": "cvm-dfp", "published_at": "2026-03-31"}},
        ],
        "sources": [
            {
                "source": "rfb-cnpj",
                "attribution": "Receita Federal",
                "license": "aberta",
            },
        ],
    }
    assert fontes_do_resultado(json.dumps(resposta)) == (
        FonteUsada("cvm-dfp", publicado_em="2026-03-31"),
        FonteUsada("rfb-cnpj", "Receita Federal", "aberta", "2026-11-09"),
    )


def test_resposta_que_nao_e_json_nao_tem_fonte():
    assert fontes_do_resultado("Erro: tente de novo") == ()
    assert fontes_do_resultado("") == ()


def test_valor_sem_data_valida_nao_vira_fonte():
    resposta = [
        {"source": "x", "published_at": "ontem"},
        {"source": "", "published_at": "2026-01-01"},
    ]
    assert fontes_do_resultado(json.dumps(resposta)) == ()


def test_fontes_tem_limite_e_texto_curto():
    resposta = {
        "sources": [
            {"source": f"f{i:03d}" + "x" * 500} for i in range(MAXIMO_DE_FONTES + 5)
        ]
    }
    fontes = fontes_do_resultado(json.dumps(resposta))
    assert len(fontes) == MAXIMO_DE_FONTES
    assert all(len(f.fonte) <= 200 for f in fontes)


def test_resposta_funda_nao_estoura_a_pilha():
    """Funda até onde o JSON lê: a fonte sai; mais funda que isso: nenhuma fonte, e a conversa segue."""
    valor = '{"source": "rfb-cnpj", "published_at": "2026-01-01"}'
    funda = '{"x": ' * 500 + valor + "}" * 500
    assert [f.fonte for f in fontes_do_resultado(funda)] == ["rfb-cnpj"]
    fundissima = '{"x": ' * 100_000 + valor + "}" * 100_000
    assert fontes_do_resultado(fundissima) == ()


def test_para_a_tela_e_tipo_simples():
    assert FonteUsada("rfb-cnpj").para_a_tela() == {
        "fonte": "rfb-cnpj",
        "atribuicao": None,
        "licenca": None,
        "publicado_em": None,
    }
