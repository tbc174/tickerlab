"""As partes do CI juntas rodam todos os testes, uma vez cada, com tempos parecidos."""

import json

import pytest

from scripts.repartir_testes import (
    ARQUIVO_DE_DURACOES,
    arquivos_da_parte,
    e_do_trader,
    juntar_duracoes,
    ler_parte,
    repartir,
)

ARQUIVOS = [
    "tests/test_a.py",
    "tests/test_b.py",
    "tests/test_c.py",
    "tests/test_d.py",
    "tests/test_e.py",
    "tests/test_trader_dados.py",
    "tests/test_c1_modelos.py",
]
DURACOES = {
    "tests/test_a.py": 90,
    "tests/test_b.py": 60,
    "tests/test_c.py": 30,
    "tests/test_d.py": 30,
}


def test_trader_e_c1_sao_da_parte_do_trader():
    assert e_do_trader("tests/test_trader_dados.py")
    assert e_do_trader("tests/test_c1_modelos.py")
    assert not e_do_trader("tests/test_backtest_no_app.py")
    assert not e_do_trader("tests/test_ficha.py")


@pytest.mark.parametrize("total", [1, 2, 3, 4])
def test_as_partes_juntas_rodam_cada_arquivo_uma_vez(total):
    partes = [
        arquivos_da_parte(f"{k}/{total}", ARQUIVOS, DURACOES)
        for k in range(1, total + 1)
    ]
    partes.append(arquivos_da_parte("trader", ARQUIVOS, DURACOES))
    juntas = [arquivo for parte in partes for arquivo in parte]
    assert sorted(juntas) == sorted(ARQUIVOS)


def test_o_trader_fica_fora_das_partes_do_app():
    assert arquivos_da_parte("trader", ARQUIVOS, DURACOES) == {
        "tests/test_trader_dados.py",
        "tests/test_c1_modelos.py",
    }
    assert not any(
        e_do_trader(arquivo) for arquivo in arquivos_da_parte("1/1", ARQUIVOS, DURACOES)
    )


def test_reparte_por_tempo_e_nao_por_quantidade():
    duracoes = {
        "tests/test_a.py": 90,
        "tests/test_b.py": 30,
        "tests/test_c.py": 30,
        "tests/test_d.py": 30,
    }
    grupos = repartir(list(duracoes), duracoes, 2)
    # 90 sozinho de um lado e 30 + 30 + 30 do outro (contar arquivos daria 2 e 2: 120 contra 60)
    assert grupos == [
        ["tests/test_a.py"],
        ["tests/test_b.py", "tests/test_c.py", "tests/test_d.py"],
    ]


def test_arquivo_sem_tempo_conta_como_a_mediana():
    grupos = repartir(
        ["tests/test_a.py", "tests/test_b.py", "tests/test_novo.py"],
        {"tests/test_a.py": 10, "tests/test_b.py": 30},
        2,
    )
    # o novo vale 20 (a mediana): o test_b (30) fica sozinho e o novo vai com o test_a (10)
    assert grupos == [["tests/test_b.py"], ["tests/test_novo.py", "tests/test_a.py"]]


def test_a_reparticao_nao_depende_da_ordem_em_que_os_arquivos_chegam():
    # cada processo do xdist reparte sozinho: todos precisam chegar ao mesmo resultado
    invertidos = list(reversed(ARQUIVOS))
    for k in (1, 2, 3):
        assert arquivos_da_parte(f"{k}/3", ARQUIVOS, DURACOES) == arquivos_da_parte(
            f"{k}/3", invertidos, DURACOES
        )


@pytest.mark.parametrize("texto", ["0/3", "4/3", "3", "a/b", "1/0", ""])
def test_parte_sem_sentido_e_recusada(texto):
    with pytest.raises(ValueError, match="parte inválida"):
        ler_parte(texto)


def test_juntar_duracoes_atualiza_e_esquece_o_arquivo_apagado():
    antigas = {"tests/test_a.py": 10.0, "tests/test_apagado.py": 5.0}
    medidas = {"tests/test_a.py": 12.34, "tests/test_b.py": 3.0}
    existentes = ["tests/test_a.py", "tests/test_b.py"]
    assert juntar_duracoes(antigas, medidas, existentes) == {
        "tests/test_a.py": 12.3,
        "tests/test_b.py": 3.0,
    }


def test_os_tempos_guardados_cobrem_os_arquivos_de_teste():
    # tempo velho só equilibra pior; mas sem os tempos as partes ficariam bem desiguais
    duracoes = json.loads(ARQUIVO_DE_DURACOES.read_text(encoding="utf-8"))
    arquivos = {
        f"tests/{arquivo.name}"
        for arquivo in ARQUIVO_DE_DURACOES.parent.glob("test_*.py")
    }
    sem_tempo = arquivos - set(duracoes)
    assert len(sem_tempo) <= len(arquivos) // 4, sorted(sem_tempo)
