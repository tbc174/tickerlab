"""As conferências por CNPJ para a ficha do Ficha Clara (`base/conferencias_por_cnpj.py`; etapa 6).

Dados de mentira, sem internet: Parquets gravados à mão com as colunas das tabelas da base.
"""

import json
import sqlite3
from datetime import UTC, datetime

import pandas as pd
import pytest

from base import conferencias_por_cnpj as conferencias
from scripts import exportar_conferencias, montar_vista_do_cnpj
from tests import ajudantes_do_cnpj as exemplo

AGORA = datetime(2026, 10, 29, 12, tzinfo=UTC)
RAIZ, OUTRA, MEI = "11222333", "44555666", "77888999"


def _cnpj(raiz: str, filial: str = "0001") -> str:
    return f"{raiz[:2]}.{raiz[2:5]}.{raiz[5:]}/{filial}-00"


def _sancao(raiz: str, id_na_fonte: str, visto: str, **campos) -> dict:
    return {
        "cadastro": "ceis",
        "id_na_fonte": id_na_fonte,
        "cnpj": _cnpj(raiz),
        "cnpj_basico": raiz,
        "categoria": campos.get("categoria", "Impedimento"),
        "situacao": "",
        "assunto": "texto livre com Fulano de Tal",
        "orgao": "Ministério de Teste",
        "inicio": pd.Timestamp(campos.get("inicio", "2025-01-10")),
        "valor_multa": None,
        "consta": campos.get("consta", True),
        "trata_como_pessoa": campos.get("pessoa", False),
        "visto_em": pd.Timestamp(visto),
        "disponivel_em": pd.Timestamp(campos.get("disponivel", visto)),
    }


def _gravar(base, tabela: str, linhas: list[dict], arquivo: str = "a") -> None:
    pasta = base / tabela
    pasta.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(linhas).to_parquet(pasta / f"{arquivo}.parquet", index=False)


def _divida(raiz: str, retrato: str, valor: float, **campos) -> dict:
    return {
        "cnpj": _cnpj(raiz),
        "cnpj_basico": raiz,
        "tipo_divida": campos.get("tipo", "sida"),
        "situacao_inscricao": "Ativa",
        "inscricoes": 1,
        "valor_consolidado": valor,
        "data_do_retrato": pd.Timestamp(retrato),
        "trata_como_pessoa": False,
        "disponivel_em": pd.Timestamp(campos.get("disponivel", retrato)),
    }


@pytest.fixture
def base(tmp_path):
    pasta = tmp_path / "base"
    _gravar(
        pasta,
        "sancoes_cgu",
        [
            _sancao(RAIZ, "1", "2026-09-01", categoria="Suspensão"),
            _sancao(RAIZ, "1", "2026-10-01", categoria="Impedimento"),  # a mesma, mudou
            _sancao(RAIZ, "2", "2026-09-01"),
            _sancao(RAIZ, "2", "2026-10-01", consta=False),  # saiu da fonte
            _sancao(OUTRA, "3", "2026-11-01"),  # do futuro
            _sancao(MEI, "4", "2026-10-01", pessoa=True),
        ],
    )
    pgfn = pasta / "pgfn_divida"
    _gravar(pgfn, "2026-07", [_divida(RAIZ, "2026-06-30", 10.0)])
    _gravar(
        pgfn,
        "2026-10",
        [_divida(RAIZ, "2026-09-30", 25.5), _divida(OUTRA, "2026-09-30", 3.0)],
    )
    _gravar(
        pgfn, "2027-01", [_divida(RAIZ, "2026-12-31", 99.0, disponivel="2027-01-05")]
    )
    _gravar(
        pasta,
        "bcb_rde_ied",
        [
            {
                "id_na_fonte": "9",
                "cnpj_basico": OUTRA,
                "codigo_rde": "RDE1",
                "uf": "SP",
                "pais": "Portugal",
                "ocorrencia": "Registro",
                "mes": "2020-05",
                "consta": True,
                "trata_como_pessoa": False,
                "visto_em": pd.Timestamp("2026-10-29"),
                "disponivel_em": pd.Timestamp("2026-10-29"),
            }
        ],
    )
    return pasta


def _abrir(arquivo):
    banco = sqlite3.connect(arquivo)
    estado = json.loads(
        banco.execute("SELECT valor FROM meta WHERE chave = 'estado'").fetchone()[0]
    )
    return banco, estado


def _registros(banco, raiz: str, tabela: str) -> tuple[int, list[dict]] | None:
    linha = banco.execute(
        "SELECT total, linhas FROM registros WHERE raiz = ? AND tabela = ?",
        (raiz, tabela),
    ).fetchone()
    return None if linha is None else (linha[0], json.loads(linha[1]))


def test_sancao_vigente_e_a_mais_nova_ja_publica_e_que_ainda_consta(base, tmp_path):
    destino = tmp_path / "conferencias.sqlite"
    conferencias.montar(base, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, linhas = _registros(banco, RAIZ, "sancoes_cgu")
    assert total == 1
    assert linhas[0]["categoria"] == "Impedimento" and linhas[0]["cnpj"] == _cnpj(RAIZ)
    assert linhas[0]["inicio"] == "2025-01-10"
    assert _registros(banco, OUTRA, "sancoes_cgu") is None  # ainda não era pública
    assert _registros(banco, MEI, "sancoes_cgu") is None  # pessoa não entra


def test_divida_e_o_retrato_mais_novo_ja_publico(base, tmp_path):
    destino = tmp_path / "conferencias.sqlite"
    estado = conferencias.montar(base, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, linhas = _registros(banco, RAIZ, "pgfn_divida")
    assert total == 1 and linhas[0]["valor_consolidado"] == 25.5
    assert linhas[0]["data_do_retrato"] == "2026-09-30"
    (divida,) = [f for f in estado["fontes"] if f["tabela"] == "pgfn_divida"]
    assert divida["conferido_ate"] == "2026-09-30" and divida["empresas"] == 2


def test_fonte_sem_arquivo_fica_nao_conferida(base, tmp_path):
    estado = conferencias.montar(base, tmp_path / "c.sqlite", agora=AGORA)
    presentes = {f["tabela"] for f in estado["fontes"]}
    assert presentes == {"sancoes_cgu", "pgfn_divida", "bcb_rde_ied"}
    (sancoes,) = [f for f in estado["fontes"] if f["tabela"] == "sancoes_cgu"]
    assert sancoes["conferido_ate"] == "2026-10-01"  # o dia do retrato mais novo lido
    assert sancoes["orgao"] == "CGU" and sancoes["endereco"].startswith("https://")
    assert estado["grupo"] is None and estado["esquema"] == conferencias.ESQUEMA


def test_fonte_pela_raiz(base, tmp_path):
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, (linha,) = _registros(banco, OUTRA, "bcb_rde_ied")
    assert total == 1 and linha == {
        "codigo_rde": "RDE1",
        "uf": "SP",
        "pais": "Portugal",
        "ocorrencia": "Registro",
        "mes": "2020-05",
    }


def test_limite_de_linhas_mostra_as_mais_novas_e_conta_todas(tmp_path):
    base = tmp_path / "base"
    _gravar(
        base,
        "sancoes_cgu",
        [
            _sancao(RAIZ, str(i), "2026-10-01")
            | {"inicio": pd.Timestamp("2000-01-01") + pd.Timedelta(days=i)}
            for i in range(conferencias.LINHAS_POR_FONTE + 7)
        ],
    )
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, linhas = _registros(banco, RAIZ, "sancoes_cgu")
    assert total == conferencias.LINHAS_POR_FONTE + 7
    assert len(linhas) == conferencias.LINHAS_POR_FONTE
    assert linhas[0]["inicio"] > linhas[-1]["inicio"]


def test_nada_de_texto_livre_nem_de_pessoa_no_arquivo(base, tmp_path):
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base, destino, agora=AGORA)
    conteudo = "\n".join(
        str(linha)
        for linha in sqlite3.connect(destino).execute("SELECT * FROM registros")
    )
    assert "Fulano" not in conteudo and "assunto" not in conteudo
    assert MEI not in conteudo


def test_grupo_leva_as_ligacoes_da_vista_sem_pessoa(base, tmp_path):
    vista = tmp_path / "vista"
    montar_vista_do_cnpj.montar(exemplo.gravar_base(tmp_path / "cnpj"), vista)
    destino = tmp_path / "c.sqlite"
    estado = conferencias.montar(base, destino, vista=vista, agora=AGORA)
    assert estado["grupo"]["retrato"] == exemplo.ULTIMO_MES
    assert estado["grupo"]["ligacoes"] == 1
    banco = sqlite3.connect(destino)
    assert banco.execute("SELECT socia, empresa FROM ligacoes").fetchall() == [
        (exemplo.SOCIO_PJ, exemplo.LIMITADA)
    ]
    texto = "\n".join(str(linha) for linha in banco.execute("SELECT * FROM ligacoes"))
    assert exemplo.NOME_DO_SOCIO not in texto and exemplo.ID_DO_SOCIO not in texto


def test_arquivo_novo_substitui_o_velho_por_inteiro(base, tmp_path):
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base, destino, agora=AGORA)
    conferencias.montar(base, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    assert banco.execute("SELECT count(*) FROM registros").fetchone()[0] == 4
    assert not (tmp_path / "c.sqlite.parcial").exists()


def test_comando_grava_o_arquivo(base, tmp_path, monkeypatch):
    monkeypatch.setattr(
        exportar_conferencias, "exigir_versao_do_codigo", lambda: "teste"
    )
    destino = tmp_path / "saida" / "conferencias.sqlite"
    assert (
        exportar_conferencias.main(["--base", str(base), "--destino", str(destino)])
        == 0
    )
    _, estado = _abrir(destino)
    assert len(estado["fontes"]) == 3
