"""Montagem periódica das tabelas do modelo 8 com relatório de qualidade (critério de pronto, PR D).
Sem internet: as tabelas são Parquets de mentira, e as montagens de verdade (testadas em seus
próprios arquivos) são trocadas por funções que só anotam a ordem."""

import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from base import historico
from base.dicionario import TABELAS
from scripts import montar_modelo_8

ANOS = (2020, 2021, 2022)


def _gravar(pasta, nome: str, linhas: list[dict]) -> None:
    padrao = montar_modelo_8.ARQUIVOS[nome]
    destino = pasta / padrao.replace("*", "2020")
    destino.parent.mkdir(parents=True, exist_ok=True)
    colunas = {c: None for c in TABELAS[nome].colunas}
    pd.DataFrame([{**colunas, **linha} for linha in linhas]).to_parquet(destino)


def _base(pasta, anos=ANOS, valor=5e8) -> None:
    data = [pd.Timestamp(f"{a}-12-31") for a in anos]
    _gravar(
        pasta,
        "rotulos_atraso",
        [
            {"cnpj": f"{a}", "documento": "DFP", "referencia": d}
            for a, d in zip(anos, data, strict=True)
        ],
    )
    _gravar(
        pasta,
        "demonstracoes_como_era",
        [
            {
                "cnpj": "1",
                "documento": "DFP",
                "referencia": d,
                "versao": 1,
                "demonstracao": "BPA",
                "grupo": "con",
                "conta": "1",
                "inicio": None,
                "fim": d,
                "divulgado_em": d,
                "valor": valor,
            }
            for d in data
        ],
    )
    _gravar(
        pasta,
        "colunas_atraso",
        [
            {"cnpj": f"{a}", "documento": "DFP", "referencia": d}
            for a, d in zip(anos, data, strict=True)
        ],
    )
    for nome in ("auditores", "fca_geral", "insolvencia", "eventos"):
        _gravar(
            pasta,
            nome,
            [
                {
                    "cnpj": "1",
                    "protocolo": str(a),
                    "versao": 1,
                    "referencia": d,
                    "auditor_id": "x",
                    "rotulo": "rj",
                    "ano_do_arquivo": a,
                }
                for a, d in zip(anos, data, strict=True)
            ],
        )
    _gravar(
        pasta,
        "trocas_de_auditor",
        [
            {"cnpj": "1", "efetiva_em": d, "novo_id": "x", "conhecido_em": d}
            for d in data
        ],
    )


def _rodar(pasta, *opcoes: str) -> int:
    return montar_modelo_8.main(["--pasta", str(pasta), "--sem-montar", *opcoes])


def test_primeira_montagem_grava_o_relatorio_sem_alerta(tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _base(tmp_path)
    assert _rodar(tmp_path) == 0
    (relatorio,) = (tmp_path / "qualidade" / "modelo_8").glob("*.json")
    dados = json.loads(relatorio.read_text(encoding="utf-8"))
    assert dados["alertas"] == [] and dados["versao_do_codigo"] == "0123abc"
    assert dados["tabelas"]["rotulos_atraso"]["linhas_por_ano"] == {
        "2020": 1,
        "2021": 1,
        "2022": 1,
    }
    assert dados["tabelas"]["demonstracoes_como_era"]["escala_por_ano"]["2021"] == 5e8


def test_ano_que_some_ou_escala_que_muda_faz_a_montagem_falhar(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _base(tmp_path)
    assert _rodar(tmp_path, "--dia", "2026-10-10") == 0
    _base(
        tmp_path, anos=(2020, 2021), valor=5e5
    )  # 2022 sumiu e os reais viraram milhares
    assert _rodar(tmp_path, "--dia", "2026-10-17") == 1
    saida = capsys.readouterr().out
    falhas = [linha for linha in saida.splitlines() if linha.startswith("FALHAS: ")]
    assert len(falhas) == 1
    assert "rotulos_atraso: 2022 sumiu" in falhas[0]
    assert "escala de 2020 mudou 1000 vezes" in saida


def test_tabela_sem_arquivo_faz_a_montagem_falhar(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _base(tmp_path)
    (tmp_path / "trocas_de_auditor" / "trocas.parquet").unlink()
    assert _rodar(tmp_path) == 1
    assert "trocas_de_auditor: sem arquivo" in capsys.readouterr().out


def test_monta_na_ordem_e_falha_quando_um_original_nao_abre(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _base(tmp_path)
    ordem: list[str] = []

    def historica(nome, _conexao, _pasta, _agora):
        ordem.append(nome)
        if nome == "eventos":
            raise historico.ArquivoIlegivel("eventos 2021: zip quebrado")
        return {2020: 1}

    monkeypatch.setattr(montar_modelo_8.historico, "montar", historica)
    monkeypatch.setattr(
        montar_modelo_8.auditores,
        "montar_trocas",
        lambda *_: ordem.append("trocas") or 1,
    )
    monkeypatch.setattr(
        montar_modelo_8.rotulo, "montar", lambda *_: ordem.append("rotulo") or 1
    )
    monkeypatch.setattr(
        montar_modelo_8, "montar_colunas", lambda *_: ordem.append("colunas") or 1
    )
    monkeypatch.setattr(montar_modelo_8, "obter_engine", lambda: _SemBanco())

    saida = montar_modelo_8.main(["--pasta", str(tmp_path)])

    assert ordem == [
        "auditores", "fca_geral", "insolvencia", "eventos", "trocas", "rotulo", "colunas",
    ]  # fmt: skip
    assert saida == 1
    assert "eventos 2021: zip quebrado" in capsys.readouterr().out


def test_sem_versao_do_codigo_nada_e_montado(tmp_path, monkeypatch):
    monkeypatch.delenv("TICKERLAB_VERSAO", raising=False)
    monkeypatch.setattr(montar_modelo_8, "exigir_versao_do_codigo", _sem_versao)
    with pytest.raises(SystemExit):
        montar_modelo_8.main(["--pasta", str(tmp_path)])


def _sem_versao() -> str:
    raise SystemExit("sem versão do código")


class _SemBanco:
    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_dia_do_relatorio_e_o_de_brasilia():
    assert montar_modelo_8.dia_de(datetime(2026, 10, 17, 2, tzinfo=UTC)) == "2026-10-16"


def test_os_caminhos_das_tabelas_sao_os_da_porta():
    from base.porta.duckdb import ARQUIVOS

    for tabela, padrao in montar_modelo_8.ARQUIVOS.items():
        assert ARQUIVOS[tabela] == padrao, tabela
    assert set(montar_modelo_8.ARQUIVOS) == set(montar_modelo_8.RESUMOS)
