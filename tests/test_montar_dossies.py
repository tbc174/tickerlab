"""As fichas do dossiê gravadas a partir de uma mini-base (plano de 17/10/2026, PR 1, tarefa 8).

A mini-base: a CPFL (ticker CPFE3, auditor, uma distribuidora na ANEEL, um fato relevante de aquisição)
e a Sem Nada S.A. (ticker, mas nenhuma tabela fala dela). Um auditor pessoa física na rede.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from base import dossie
from scripts import montar_dossies

D = pd.Timestamp
CPFL, SEM_NADA = "02.429.144/0001-93", "11.111.111/0001-11"
CPFL_DIGITOS = "02429144000193"
DISTRIBUIDORA = "33050196000188"


def _gravar(pasta: Path, relativo: str, tabela: pd.DataFrame) -> None:
    destino = pasta / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(destino)
    destino.with_suffix(".json").write_text(
        json.dumps({"sha256_da_tabela": f"hash-{destino.stem}"}), encoding="utf-8"
    )


def _mini_base(pasta: Path) -> None:
    _gravar(
        pasta,
        "fca/tickers.parquet",
        pd.DataFrame(
            {
                "codigo": ["CPFE3", "SNDA3", "VELH3"],
                "cnpj": [CPFL, SEM_NADA, "22.222.222/0001-22"],
                "empresa": ["CPFL ENERGIA S.A.", "SEM NADA S.A.", "VELHA S.A."],
                "valido_ate": [pd.NaT, pd.NaT, D("2020-01-01")],
            }
        ),
    )
    _gravar(
        pasta,
        "auditores/2025.parquet",
        pd.DataFrame(
            {
                "cnpj": [CPFL],
                "referencia": [D("2025-01-01")],
                "versao": [1],
                "auditor_id": ["rede:deloitte"],
                "auditor": ["Deloitte"],
                "auditor_cnpj": ["49928567000111"],
                "inicio": [D("2025-04-01")],
                "fim": [pd.NaT],
            }
        ),
    )
    _gravar(
        pasta,
        "eventos/2025.parquet",
        pd.DataFrame(
            {
                "cnpj": [CPFL, CPFL],
                "rotulo": ["Fato relevante", "Fato relevante"],
                "assunto": ["Aquisição da Enercan", "Resultado do 2T25"],
                "publicado_em": [D("2025-03-01"), D("2025-08-01")],
                "link": ["l1", "l2"],
            }
        ),
    )
    _gravar(
        pasta,
        "empresa_serie/empresa_serie.parquet",
        pd.DataFrame(
            {
                "fonte": ["aneel-samp"],
                "chave": [DISTRIBUIDORA],
                "nome": ["CPFL Paulista"],
                "cnpj_companhia": [CPFL_DIGITOS],
                "via": ["controlada"],
                "principal": [True],
                "desde": [D("2010-05-01")],
            }
        ),
    )
    _gravar(
        pasta,
        "setoriais/aneel/2025.parquet",
        pd.DataFrame(
            {
                "competencia": [D("2025-11-30"), D("2025-12-31"), D("2025-12-31")],
                "cnpj": [DISTRIBUIDORA, DISTRIBUIDORA, "99999999000199"],
                "valor": [100.0, 110.0, 890.0],
                "detalhe_do_mercado": ["Número de consumidores"] * 3,
                "tipo_de_mercado": ["Regular"] * 3,
            }
        ),
    )
    _gravar(
        pasta,
        "rede/entidades.parquet",
        pd.DataFrame(
            {
                "id_entidade": ["E1"],
                "nome": ["Fulano de Tal"],
                "trata_como_pessoa": [True],
            }
        ),
    )


def _montar(pasta: Path, saida: Path) -> montar_dossies.Resumo:
    return montar_dossies.montar(pasta, saida, D("2026-10-17 07:00"), "abc1234")


def test_grava_uma_ficha_por_empresa_com_dados(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    pasta_do_dia = tmp_path / "dossies" / "2026-10-17"
    assert sorted(p.name for p in pasta_do_dia.iterdir()) == [
        f"{CPFL_DIGITOS}.json",
        "manifesto.json",
    ]
    ficha = json.loads(
        (pasta_do_dia / f"{CPFL_DIGITOS}.json").read_text(encoding="utf-8")
    )
    chaves = [s["chave"] for s in ficha["secoes"]]
    assert chaves == ["auditor_e_controladas", "setor_regulado", "negocios"]
    setor = ficha["secoes"][1]["tabelas"]["aneel_consumidores"][0]
    assert setor == {"ano": 2025, "valor": 110.0, "participacao": pytest.approx(0.11)}
    assert resumo.fichas == 1
    assert resumo.empresas == 2  # o ticker que deixou de valer fica fora
    assert resumo.falhas == []


def test_manifesto_traz_versao_hashes_e_tabelas_que_faltam(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    _montar(tmp_path / "base", tmp_path / "dossies")
    manifesto = json.loads(
        (tmp_path / "dossies" / "2026-10-17" / "manifesto.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifesto["versao_do_esquema"] == dossie.VERSAO_DO_ESQUEMA
    assert manifesto["versao_do_codigo"] == "abc1234"
    assert manifesto["tabelas"]["auditores/2025"] == "hash-2025"
    assert "trocas_de_auditor/trocas" in manifesto["faltando"]
    assert manifesto["fichas"] == 1


def test_secao_que_quebra_nao_derruba_as_outras(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mini_base(tmp_path / "base")

    def quebra(*_: object) -> None:
        raise ValueError("coluna sumiu")

    monkeypatch.setattr(montar_dossies.dossie, "secao_negocios", quebra)
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    assert resumo.fichas == 1
    assert resumo.falhas == ["negocios: ValueError: coluna sumiu (2 empresas)"]


def test_ficha_com_pessoa_nao_e_gravada(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    # uma "controlada" que é um empresário individual: o nome é o de uma pessoa da rede
    _gravar(
        tmp_path / "base",
        "controladas/2025.parquet",
        pd.DataFrame(
            {
                "cnpj_companhia": [CPFL_DIGITOS],
                "referencia": [D("2025-01-01")],
                "versao": [1],
                "cnpj": [""],
                "razao_social": ["Fulano de Tal"],
                "tipo": ["controlada"],
                "participacao": [100.0],
            }
        ),
    )
    resumo = _montar(tmp_path / "base", tmp_path / "dossies")
    assert resumo.fichas == 0
    assert resumo.falhas == [f"{CPFL_DIGITOS}: PessoaNaFichaError"]


def test_mesmo_dia_regrava_a_pasta_inteira(tmp_path: Path) -> None:
    _mini_base(tmp_path / "base")
    sobra = tmp_path / "dossies" / "2026-10-17" / "00000000000000.json"
    sobra.parent.mkdir(parents=True)
    sobra.write_text("{}", encoding="utf-8")
    _montar(tmp_path / "base", tmp_path / "dossies")
    assert not sobra.exists()


def test_main_avisa_as_falhas_na_ultima_linha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(montar_dossies, "exigir_versao_do_codigo", lambda: "abc1234")
    saida = montar_dossies.main(
        ["--pasta", str(tmp_path / "nada"), "--saida", str(tmp_path / "d")]
    )
    assert saida == 1
    assert (
        capsys.readouterr().out.strip().splitlines()[-1].startswith("FALHAS: dossiês:")
    )
