"""Conferência cruzada entre duas fontes (exigência 6 da ADR 0027; plano do placar, PR 1)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from base import cruzada
from base.cruzada import (
    MESMA_FONTE_OUTRO_DOCUMENTO,
    MESMO_DOCUMENTO,
    OUTRO_ORGAO,
    PARES,
    Par,
    Tolerancia,
    comparar,
    ler_explicadas,
    montar_relatorio_do_dia,
    par_sem_dados,
)

PAR = Par(
    nome="exemplo",
    descricao="par de teste",
    chave=("k",),
    tolerancia=Tolerancia(absoluta=1.0),
    independencia=OUTRO_ORGAO,
)


def _lado(**valores: float) -> pd.DataFrame:
    return pd.DataFrame({"k": list(valores), "valor": list(valores.values())})


def test_comparar_classifica() -> None:
    a = pd.DataFrame(
        {"k": ["igual", "perto", "longe", "so_a"], "valor": [10.0, 10.0, 10.0, 1.0]}
    )
    b = pd.DataFrame(
        {"k": ["igual", "perto", "longe", "so_b"], "valor": [10.0, 10.5, 13.0, 1.0]}
    )
    r = comparar(PAR, a, b, set())
    assert (r.comparadas, r.iguais, r.pela_tolerancia, r.diferentes) == (3, 1, 1, 1)
    assert (r.so_em_a, r.so_em_b) == (1, 1)
    d = r.divergencias[0]
    assert d.chave == "longe" and d.diferenca == pytest.approx(3.0)
    assert d.diferenca_pct == pytest.approx(3 / 13 * 100)


def test_tolerancia_no_limite() -> None:
    for diferenca, esperado in (
        (0.0, "iguais"),
        (0.5, "pela_tolerancia"),
        (1.0, "pela_tolerancia"),
        (1.5, "diferentes"),
    ):
        r = comparar(PAR, _lado(x=10.0), _lado(x=10.0 + diferenca), set())
        assert getattr(r, esperado) == 1, (diferenca, esperado)


def test_tolerancia_relativa() -> None:
    par = Par("rel", "d", ("k",), Tolerancia(relativa=0.02), OUTRO_ORGAO)
    assert comparar(par, _lado(x=100.0), _lado(x=101.9), set()).pela_tolerancia == 1
    assert comparar(par, _lado(x=100.0), _lado(x=103.0), set()).diferentes == 1


def test_divergencia_sem_explicacao_e_vermelha() -> None:
    r = comparar(PAR, _lado(x=1.0), _lado(x=9.0), set())
    assert r.sem_explicacao == 1 and r.vermelho


def test_divergencia_explicada_sai_do_vermelho() -> None:
    r = comparar(PAR, _lado(x=1.0), _lado(x=9.0), {("exemplo", "x")})
    assert r.diferentes == 1 and r.sem_explicacao == 0 and not r.vermelho


def test_so_de_um_lado_nao_e_vermelho() -> None:
    r = comparar(PAR, _lado(x=1.0), _lado(y=1.0), set())
    assert r.comparadas == 0 and not r.vermelho


def test_chave_composta_e_vazio() -> None:
    par = Par("c", "d", ("k", "j"), Tolerancia(), OUTRO_ORGAO)
    a = pd.DataFrame({"k": ["a", "a"], "j": [1, 2], "valor": [1.0, float("nan")]})
    b = pd.DataFrame({"k": ["a", "a"], "j": [1, 2], "valor": [1.0, 5.0]})
    r = comparar(par, a, b, set())
    assert r.iguais == 1 and r.so_em_b == 1  # valor vazio não é comparado


def test_ler_explicadas() -> None:
    texto = (
        "par;chave;explicacao;conferido_em\nexemplo;x;perímetro diferente;2026-11-03\n"
    )
    assert ler_explicadas(texto) == {("exemplo", "x")}


def test_explicadas_do_repositorio_leem() -> None:
    assert isinstance(
        ler_explicadas(cruzada.CAMINHO_EXPLICADAS.read_text(encoding="utf-8")), set
    )


def test_placar_separa_independencia() -> None:
    relatorios = [comparar(PAR, _lado(x=1.0), _lado(x=1.0), set())]
    outro = Par("mesma", "d", ("k",), Tolerancia(), MESMA_FONTE_OUTRO_DOCUMENTO)
    relatorios.append(comparar(outro, _lado(x=1.0), _lado(x=2.0), set()))
    dia = montar_relatorio_do_dia("2026-11-03", relatorios)
    assert dia["por_independencia"][OUTRO_ORGAO]["comparadas"] == 1
    assert dia["por_independencia"][MESMA_FONTE_OUTRO_DOCUMENTO]["diferentes"] == 1
    assert dia["vermelho"] is True
    json.dumps(dia)  # tipos simples


def test_relatorio_sem_pessoas() -> None:
    dia = montar_relatorio_do_dia(
        "2026-11-03", [comparar(PAR, _lado(x=1.0), _lado(x=9.0), set())]
    )
    assert set(dia) == {"dia", "pares", "por_independencia", "vermelho"}


def test_pares_declaram_independencia_e_tolerancia() -> None:
    assert len(PARES) == 4
    assert {p.independencia for p in PARES} >= {OUTRO_ORGAO, MESMO_DOCUMENTO}
    assert len({p.nome for p in PARES}) == 4


def test_par_selic_com_dados_de_exemplo() -> None:
    selic = pd.DataFrame(
        {
            "serie": ["bcb-sgs-432"] * 3,
            "referencia": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-21"]),
            "valor": [11.75, 11.25, 10.75],
            "divulgado_em": pd.to_datetime(["2024-01-02", "2024-02-02", "2024-03-22"]),
        }
    )
    copom = pd.DataFrame(
        {"data": ["2024-01-31", "2024-03-20"], "meta_selic": [11.25, 10.80]}
    )
    par = next(p for p in PARES if p.nome == "selic_meta_sgs_x_copom")
    a, b = par.preparar({"bcb_selic_focus": selic, "copom_reunioes": copom})
    r = comparar(par, a, b, set())
    assert (
        r.iguais == 1 and r.pela_tolerancia == 0 and r.diferentes == 1
    )  # 20/03: 10,75 × 10,80


def _bancos() -> dict[str, pd.DataFrame]:
    ifdata = pd.DataFrame(
        {
            "data_base": pd.to_datetime(["2024-12-31"] * 4),
            "tipo_instituicao": [2, 1, 2, 2],
            "cod_inst": ["C001", "C002", "C001", "C001"],
            "relatorio": [1, 1, 1, 1],
            "coluna": [
                "Ativo Total",
                "Ativo Total",
                "Patrimônio Líquido",
                "Lucro Líquido",
            ],
            "saldo": [1000.0, 999.0, 100.0, 5.0],
        }
    )
    ligacao = pd.DataFrame(
        {
            "data_base": pd.to_datetime(["2024-12-31", "2024-12-31"]),
            "cod_inst": ["C001", "C002"],
            "cnpj": ["11.111.111/0001-11", "11.111.111/0001-11"],
        }
    )
    dfp = pd.DataFrame(
        {
            "cnpj": ["11.111.111/0001-11"] * 3,
            "grupo": ["con"] * 3,
            "demonstracao": ["BPA", "BPP", "BPP"],
            "conta": ["1", "2.07", "2.05"],
            "descricao": [
                "Ativo Total",
                "Patrimônio Líquido Consolidado",
                "Outros Passivos",
            ],
            "documento": ["DFP"] * 3,
            "referencia": pd.to_datetime(["2024-12-31"] * 3),
            "ordem": ["ultimo"] * 3,
            "valor": [1010.0, 101.0, 7.0],
        }
    )
    return {
        "ifdata_valores": ifdata,
        "ligacao_dos_bancos": ligacao,
        "demonstracoes_como_era": dfp,
    }


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("banco_ativo_total_ifdata_x_dfp", 1010.0),
        ("banco_patrimonio_liquido_ifdata_x_dfp", 101.0),
    ],
)
def test_pares_dos_bancos(nome: str, esperado: float) -> None:
    par = next(p for p in PARES if p.nome == nome)
    a, b = par.preparar(_bancos())
    assert (
        len(a) == len(b) == 1
    )  # prefere o conglomerado financeiro (tipo 2) ao prudencial
    assert b["valor"].iloc[0] == esperado
    assert (
        comparar(par, a, b, set()).pela_tolerancia == 1
    )  # 1% de diferença cabe nos 2%


def test_par_sem_dados_nao_e_vermelho_nem_prova() -> None:
    r = par_sem_dados(PAR, "tabela ausente")
    assert (
        r.comparadas == 0
        and not r.vermelho
        and r.como_dict()["sem_dados"] == "tabela ausente"
    )


def test_script_grava_o_json_e_sai_com_1_quando_vermelho(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts import conferir_cruzado

    monkeypatch.setenv("TICKERLAB_ACERVO", str(tmp_path))
    relatorio = comparar(PAR, _lado(x=1.0), _lado(x=9.0), set())
    monkeypatch.setattr(conferir_cruzado, "conferir", lambda dia: [relatorio])
    assert conferir_cruzado.main(["--dia", "2026-11-03"]) == 1
    assert "FALHAS: exemplo (1 sem explicação)" in capsys.readouterr().out
    gravado = json.loads(
        (tmp_path / "placar" / "2026-11-03" / "cruzada.json").read_text(
            encoding="utf-8"
        )
    )
    assert gravado["vermelho"] is True and gravado["pares"][0]["nome"] == "exemplo"


def test_script_sai_com_0_quando_tudo_confere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import conferir_cruzado

    monkeypatch.setenv("TICKERLAB_ACERVO", str(tmp_path))
    relatorio = comparar(PAR, _lado(x=1.0), _lado(x=1.0), set())
    monkeypatch.setattr(conferir_cruzado, "conferir", lambda dia: [relatorio])
    assert conferir_cruzado.main(["--dia", "2026-11-03"]) == 0


def test_cada_par_diz_de_que_tabelas_e_prova() -> None:
    from base.dicionario import TABELAS

    for par in PARES:
        assert par.tabelas and set(par.tabelas) <= set(TABELAS)
        assert par_sem_dados(par, "x").como_dict()["tabelas"] == list(par.tabelas)


def test_par_informativo_fica_visivel_mas_nunca_deixa_o_placar_vermelho() -> None:
    """Regra: o par só conta para a exigência 6 quando os dois lados medem o mesmo perímetro."""
    informativo = Par(
        "perimetros",
        "d",
        ("k",),
        Tolerancia(),
        OUTRO_ORGAO,
        informativo="perímetros diferentes",
    )
    r = comparar(informativo, _lado(x=1.0), _lado(x=9.0), set())
    assert r.diferentes == 1 and r.sem_explicacao == 1
    assert not r.vermelho
    dia = montar_relatorio_do_dia("2026-11-10", [r])
    assert dia["vermelho"] is False
    assert dia["por_independencia"] == {}  # não soma na prova
    assert (
        dia["pares"][0]["informativo"] == "perímetros diferentes"
    )  # e continua à vista


def test_pares_dos_bancos_sao_informativos_com_a_causa() -> None:
    from base.cruzada import PARES

    bancos = [p for p in PARES if p.nome.startswith("banco_")]
    assert len(bancos) == 2
    assert all("perímetro" in p.informativo for p in bancos)


def test_par_do_enet_casa_balanco_sem_inicio_e_so_o_ultimo_exercicio() -> None:
    from base.cruzada import PARES

    par = next(p for p in PARES if p.nome == "dfp_enet_x_nossa_leitura")
    assert par.tabelas == ("demonstracoes_como_era",)
    assert (
        not par.informativo
    )  # os dois lados são o mesmo documento: conta para a prova
    base = {"cnpj": "1", "grupo": "DF_CONS", "demonstracao": "BPA", "conta": "1"}
    nossa = pd.DataFrame(
        [
            {
                **base,
                "ordem": "ultimo",
                "inicio": pd.NaT,
                "fim": "2024-12-31",
                "valor": 10.0,
            },
            {
                **base,
                "ordem": "penultimo",
                "inicio": pd.NaT,
                "fim": "2023-12-31",
                "valor": 7.0,
            },
        ]
    )
    enet = nossa.assign(valor=[10.1, 7.0])
    assert par.preparar is not None
    a, b = par.preparar({"demonstracoes_como_era": nossa, "enet_amostra": enet})
    r = comparar(par, a, b, set())
    assert r.comparadas == 1 and r.diferentes == 0  # 1% < 2%; o penúltimo ficou de fora
