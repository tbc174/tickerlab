"""Os bancos na noite (molde D, PR 2): o IF.data lido pela porta, como era no dia da ficha.

A mini-base: o Itaú (com ticker) e a Caixa (sem) no tipo 1 do IF.data, de 2024 a junho de 2026. O BC
revisou dezembro de 2025: o arquivo vigente é a revisão e o `202512.v1` é o de antes. O tipo 2 repete os
números (o conglomerado financeiro), e a data-base de junho de 2026 só fica pública no fim de outubro.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts import gerar_dossies
from tests.test_gerar_dossies import _gravar

D = pd.Timestamp
ITAU = "60872504000123"
C_ITAU, C_CAIXA = "C0080099", "C0080000"
CREDITO = "Carteira de Crédito"


def _data_base(data: str, itau: float, caixa: float, tipo: int = 1) -> pd.DataFrame:
    """O relatório 1 de uma data-base: crédito, ativo e captações de cada conglomerado."""
    data_base = D(data)
    linhas = [
        (cod, coluna, valor * fator)
        for cod, valor in ((C_ITAU, itau), (C_CAIXA, caixa))
        for coluna, fator in ((CREDITO, 1), ("Ativo Total", 2), ("Captações", 1.5))
    ]
    return pd.DataFrame(
        {
            "data_base": data_base,
            "tipo_instituicao": tipo,
            "cod_inst": [cod for cod, _, _ in linhas],
            "relatorio": 1,
            "nome_relatorio": "Resumo",
            "grupo": None,
            "conta": "1",
            "coluna": [coluna for _, coluna, _ in linhas],
            "descricao": None,
            "saldo": [valor for _, _, valor in linhas],
            "disponivel_em": data_base + pd.Timedelta(days=120),
        }
    )


def _base(pasta: Path, com_o_futuro: bool) -> None:
    _gravar(
        pasta,
        "fca/tickers.parquet",
        pd.DataFrame(
            {
                "codigo": ["ITUB4"],
                "cnpj": ["60.872.504/0001-23"],
                "empresa": ["ITAU UNIBANCO HOLDING S.A."],
                "valido_ate": [pd.NaT],
            }
        ),
    )
    _gravar(
        pasta,
        "bcb/ifdata/ligacao_dos_bancos.parquet",
        pd.DataFrame(
            {
                "data_base": [D("2024-12-31"), D("2024-12-31")],
                "cod_inst": [C_ITAU, C_CAIXA],
                "instituicao": ["ITAU - PRUDENCIAL", "CAIXA - PRUDENCIAL"],
                "cnpj_raiz": ["60872504", None],
                "cnpj": ["60.872.504/0001-23", None],
                "ligado_por": ["líder do conglomerado", None],
                "tickers": ["ITUB4", None],
            }
        ),
    )
    valores = "bcb/ifdata/valores"
    # as quatro datas-base de cada ano (o ano completo); o estoque que conta é o de dezembro
    for ano, itau, caixa in ((2024, 40, 60), (2025, 45, 55)):
        for mes, dia in (("03", 31), ("06", 30), ("09", 30), ("12", 31)):
            _gravar(
                pasta,
                f"{valores}/tipo_1/{ano}{mes}.parquet",
                _data_base(f"{ano}-{mes}-{dia}", itau, caixa),
            )
    # a versão de antes da revisão de dezembro de 2025 e o conglomerado financeiro (tipo 2)
    _gravar(
        pasta, f"{valores}/tipo_1/202512.v1.parquet", _data_base("2025-12-31", 99, 1)
    )
    _gravar(
        pasta,
        f"{valores}/tipo_2/202512.parquet",
        _data_base("2025-12-31", 45, 55, tipo=2),
    )
    if com_o_futuro:
        _gravar(
            pasta, f"{valores}/tipo_1/202603.parquet", _data_base("2026-03-31", 30, 70)
        )
        _gravar(
            pasta, f"{valores}/tipo_1/202606.parquet", _data_base("2026-06-30", 90, 10)
        )


def _setor(pasta: Path, saida: Path, hoje: str = "2026-10-17") -> dict:
    gerar_dossies.montar(pasta, saida, D(f"{hoje} 07:00"), "abc1234")
    dia = saida / hoje
    manifesto = json.loads((dia / "manifesto.json").read_text(encoding="utf-8"))
    assert manifesto["setores"]["bancos"] == {"ficha": ITAU, "membros": [ITAU]}
    ficha = json.loads((dia / f"{ITAU}.json").read_text(encoding="utf-8"))
    return next(s for s in ficha["secoes"] if s["chave"] == "setor")


def _credito(secao: dict) -> dict[int, dict]:
    return {
        r["ano"]: r for r in secao["tabelas"]["concentracao_bcb_carteira_de_credito"]
    }


def test_bancos_na_noite_pelo_ifdata(tmp_path: Path) -> None:
    _base(tmp_path / "base", com_o_futuro=True)
    secao = _setor(tmp_path / "base", tmp_path / "dossies")
    credito = _credito(secao)
    # a revisão vigente (45 e 55), nem a versão guardada nem o tipo 2 somados
    assert credito[2025]["total"] == pytest.approx(100.0)
    assert credito[2025]["hhi"] == pytest.approx(45**2 + 55**2)
    # junho de 2026 ainda não era público em 17/10: o ano corrente fica com março
    assert credito[2026]["ultimo_mes"] == "2026-03-31"
    assert credito[2026]["meses"] == 3
    assert credito[2025]["delta_hhi"] == pytest.approx(45**2 + 55**2 - (40**2 + 60**2))
    itens = {item["chave"]: item for item in secao["itens"]}
    assert itens["mercado_bcb_ativo_total"]["valor"] == pytest.approx(200.0)
    assert [m["motivo"] for m in secao["tabelas"]["membros"]] == [
        "ligada ao Banco Central por 1 entidade"
    ]


def test_bancos_dezembro_so_entra_depois_de_publico(tmp_path: Path) -> None:
    """Em 17/4/2026 a data-base de dezembro de 2025 ainda não era pública (sai 120 dias depois)."""
    _base(tmp_path / "base", com_o_futuro=False)
    credito = _credito(_setor(tmp_path / "base", tmp_path / "dossies", "2026-04-17"))
    assert credito[2025]["ultimo_mes"] == "2025-09-30"
    assert credito[2025]["meses"] == 9 and credito[2025]["delta_hhi"] is None


def test_bancos_cortar_o_futuro_nao_muda_o_passado_na_noite(tmp_path: Path) -> None:
    linhas = []
    for com_o_futuro in (False, True):
        pasta = tmp_path / f"base-{com_o_futuro}"
        _base(pasta, com_o_futuro)
        secao = _setor(pasta, tmp_path / f"dossies-{com_o_futuro}")
        linhas.append([linha for ano, linha in _credito(secao).items() if ano <= 2025])
    assert linhas[0] == linhas[1]
    assert len(linhas[0]) == 2
