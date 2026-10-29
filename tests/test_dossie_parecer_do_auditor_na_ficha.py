"""O parecer do auditor dentro da seção "Auditor e controladas" (linha 158, 28/10/2026, PR 2): os itens, a
tabela dos últimos exercícios e os textos aprovados pelo Tiago, escritos pela tela, pelo PDF e pela API
(que leem a mesma ficha). O dado e o rastro estão em `test_dossie_parecer_do_auditor.py`."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from base import dossie as dossie_da_base
from src import dossie
from tests.test_gerar_dossies import _ficha_da_cpfl, _gravar, _mini_base, _montar

D = pd.Timestamp
CNPJ = "00.000.000/0001-91"
HOJE = D("2025-06-01")


def _parecer(ano: int, entregue: str, **campos: object) -> dict:
    return {
        "cnpj": CNPJ,
        "referencia": date(ano, 12, 31),
        "versao": 1,
        "disponivel_em": date.fromisoformat(entregue),
        "opiniao": "sem_ressalva",
        "enfase": "nao",
        "continuidade_operacional": "nao",
        **campos,
    }


def _pareceres() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _parecer(2023, "2024-03-20"),
            _parecer(
                2024,
                "2025-03-18",
                opiniao="com_ressalva",
                enfase="sim",
                continuidade_operacional="nao_classificado",
            ),
            _parecer(2025, "2026-03-17", opiniao="adversa"),  # ainda não é público
        ]
    )


def _secao(pareceres: pd.DataFrame | None, hoje: pd.Timestamp = HOJE):
    vazia = pd.DataFrame()
    return dossie_da_base.secao_auditor_e_controladas(
        vazia, vazia, vazia, vazia, set(), pareceres, hoje
    )


def _escrita(secao: dict):
    """A seção como a tela a escreve (a ficha da noite passa pelo JSON)."""
    exemplo = json.loads(dossie.FICHA_DE_EXEMPLO.read_text(encoding="utf-8"))
    ficha = dossie.Ficha(
        versao_do_esquema=exemplo["versao_do_esquema"],
        cnpj="00000000000191",
        empresa="Empresa de Teste",
        gerado_em=datetime(2025, 6, 1, 7, 0, tzinfo=UTC),
        secoes=[dossie.SecaoDaFicha.model_validate(json.loads(json.dumps(secao)))],
    )
    [escrita] = dossie.secoes_da_ficha(ficha)
    return escrita


def test_a_secao_traz_os_tres_itens_do_ultimo_parecer_ja_entregue() -> None:
    secao = _secao(_pareceres())
    assert secao is not None
    itens = {i["chave"]: i for i in secao["itens"]}
    assert itens["parecer_opiniao"]["nome"] == "Opinião do auditor sobre a última DFP"
    assert (
        itens["parecer_opiniao"]["valor"] == "com_ressalva"
    )  # o JSON guarda o código da base
    assert itens["parecer_enfase"]["valor"] == "sim"
    assert "parecer_continuidade" not in itens  # não classificado não vira "não"


def test_a_tela_escreve_os_codigos_com_os_textos_aprovados() -> None:
    escrita = _escrita(_secao(_pareceres()))
    textos = {i.chave: i.texto for i in escrita.itens}
    assert textos == {"parecer_opiniao": "Com ressalva", "parecer_enfase": "Sim"}
    item = next(i for i in escrita.itens if i.chave == "parecer_opiniao")
    assert item.base == "31/12/2024"
    assert "pareceres_dfp" in item.fonte


def test_as_quatro_opinioes_e_o_sim_e_o_nao_tem_texto() -> None:
    textos = {
        codigo: dossie._escrever_valor(codigo, dossie_da_base.UNIDADE_DA_OPINIAO)
        for codigo in ("sem_ressalva", "com_ressalva", "adversa", "abstencao")
    }
    assert textos == {
        "sem_ressalva": "Sem ressalva",
        "com_ressalva": "Com ressalva",
        "adversa": "Adversa",
        "abstencao": "Abstenção de opinião",
    }
    assert dossie._escrever_valor("sim", dossie_da_base.UNIDADE_SIM_OU_NAO) == "Sim"
    assert dossie._escrever_valor("nao", dossie_da_base.UNIDADE_SIM_OU_NAO) == "Não"


def test_a_tabela_mostra_os_exercicios_ja_entregues_como_a_base_os_disse() -> None:
    escrita = _escrita(_secao(_pareceres()))
    tabela = escrita.tabelas["pareceres_do_auditor"]
    assert dossie.titulo_da_tabela("pareceres_do_auditor") == (
        "Parecer do auditor nos últimos exercícios"
    )
    assert [c["Exercício"] for c in tabela] == [
        "31/12/2024",
        "31/12/2023",
    ]  # 2025 ainda não saiu
    primeira = tabela[0]
    assert primeira["Opinião"] == "Com ressalva"
    assert primeira["Ênfase"] == "Sim"
    assert primeira["Continuidade"] == "Não classificado"
    assert primeira["Publicado em"] == "18/03/2025"


def test_a_secao_leva_o_paragrafo_do_parecer_antes_do_texto_antigo() -> None:
    secao = _secao(_pareceres())
    assert secao is not None
    limites = secao["paragrafos"][-1]
    assert limites.startswith(
        "Parecer: o relatório do auditor independente sobre a DFP"
    )
    assert "O texto do relatório não é guardado nem citado." in limites
    assert limites.index("Parecer:") < limites.index("Controladas e coligadas")
    assert any("CVM" in fonte for fonte in secao["fontes"])


def test_o_parecer_entregue_depois_do_dia_nao_aparece_na_ficha() -> None:
    """Sem olhar o futuro: a ficha de 01/06/2025 não sabe da DFP de 2025 (entregue em 17/03/2026)."""
    antes = _secao(_pareceres(), D("2025-06-01"))
    depois = _secao(_pareceres(), D("2026-03-17"))
    assert antes is not None and depois is not None
    assert {i["chave"]: i["valor"] for i in antes["itens"]}[
        "parecer_opiniao"
    ] == "com_ressalva"
    assert {i["chave"]: i["valor"] for i in depois["itens"]}[
        "parecer_opiniao"
    ] == "adversa"
    assert len(depois["tabelas"]["pareceres_do_auditor"]) == 3


def test_cortar_o_futuro_nao_muda_a_secao_do_passado() -> None:
    completa = _pareceres()
    cortada = completa[pd.to_datetime(completa["disponivel_em"]) <= D("2025-06-01")]
    assert _secao(completa) == _secao(cortada)


def test_sem_parecer_a_secao_sai_como_antes() -> None:
    assert _secao(None) is None
    assert _secao(pd.DataFrame()) is None
    sem_hoje = dossie_da_base.secao_auditor_e_controladas(
        *(pd.DataFrame(),) * 4, set(), _pareceres(), None
    )
    assert sem_hoje is None  # sem o dia da ficha, o parecer não entra


def test_so_o_parecer_ja_basta_para_a_secao_existir() -> None:
    secao = _secao(_pareceres())
    assert secao is not None
    assert secao["chave"] == "auditor_e_controladas"
    assert "pareceres_dfp" in dossie_da_base.SECOES[0].tabelas


def test_a_noite_le_a_tabela_pareceres_dfp(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    futuro = _parecer(
        2026, "2026-12-01", opiniao="abstencao"
    )  # depois do dia da ficha (17/10/2026)
    parecer = pd.concat([_pareceres(), pd.DataFrame([futuro])]).assign(
        cnpj="02.429.144/0001-93"
    )
    _gravar(tmp_path / "base", "pareceres_dfp/2025.parquet", parecer)
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    assert resumo.falhas == []
    secoes = {s["chave"]: s for s in _ficha_da_cpfl(tmp_path / "dossies")["secoes"]}
    itens = {i["chave"]: i["valor"] for i in secoes["auditor_e_controladas"]["itens"]}
    assert (
        itens["parecer_opiniao"] == "adversa"
    )  # a DFP de 2025, entregue em 17/03/2026
