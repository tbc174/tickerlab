"""O comando da conferência do teor (`scripts/conferir_teor_processos.py`): a amostra com semente vai
para a área restrita com o teor mascarado; a medida grava a conferência e sai com 1 abaixo do
critério. Tudo inventado, como em `tests/test_base_processos.py`."""

import json
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from base import conferencia_processos, numero_cnj, processos
from base.arquivo import djen
from scripts import conferir_teor_processos as comando
from src.banco import coletas
from src.banco.coletas import com_registro

PESSOA = "FULANA INVENTADA DE TAL"
CADASTRO = pd.DataFrame(
    {"cnpj": ["11.222.333/0001-81"], "empresa": ["ENERGIA EXEMPLO S.A."]}
)
DIA = "2026-11-08"


def _numero(sequencial: int) -> str:
    partes = (f"{sequencial:07d}", "2024", "8", "26", "0100")
    return f"{partes[0]}{numero_cnj.digito_esperado(*partes)}{''.join(partes[1:])}"


def _item(hash_: str, sequencial: int, texto: str) -> dict:
    return {
        "id": sequencial,
        "hash": hash_,
        "numero_processo": _numero(sequencial),
        "siglaTribunal": "TJSP",
        "tipoDocumento": "Sentença",
        "data_disponibilizacao": "2026-10-28",
        "destinatarios": [
            {"nome": PESSOA, "polo": "A"},
            {"nome": "ENERGIA EXEMPLO S.A.", "polo": "P"},
        ],
        "texto": texto,
    }


ITENS = [
    _item("a", 1, f"{PESSOA} x ENERGIA EXEMPLO S.A. JULGO PROCEDENTE. Valor R$ 10,00."),
    _item("b", 2, f"{PESSOA} x ENERGIA EXEMPLO S.A. JULGO IMPROCEDENTE o pedido."),
    # sem companhia entre as partes: fica fora da tabela e da amostra
    {
        **_item("c", 3, "JULGO PROCEDENTE."),
        "destinatarios": [{"nome": PESSOA, "polo": "A"}],
    },
]


def _preparar(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    monkeypatch.setattr(
        processos,
        "cadastro_do_acervo",
        lambda _c: (CADASTRO, {"url": "c", "sha256": "c"}),
    )
    monkeypatch.setattr(comando, "obter_engine", lambda: banco)
    url = djen.consulta("ENERGIA EXEMPLO S.A.", date(2026, 10, 26), date(2026, 11, 1))
    com_registro(djen.ID, lambda _url: json.dumps({"items": ITENS}).encode())(url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(coletas.coletas.c.url == url)
            .values(baixado_em=datetime(2026, 11, 2, 3, tzinfo=UTC))
        )
    return tmp_path / "base"


def _respostas(tmp_path, resultado_de_b: str):
    arquivo = tmp_path / "respostas.jsonl"
    linhas = [
        {
            "id": "a",
            "tipo_de_ato": "sentenca",
            "resultado": "procedente",
            "maior_valor": 10.0,
        },
        {
            "id": "b",
            "tipo_de_ato": "sentenca",
            "resultado": resultado_de_b,
            "maior_valor": None,
        },
    ]
    arquivo.write_text(
        "\n".join(json.dumps(linha) for linha in linhas), encoding="utf-8"
    )
    return arquivo


def test_amostra_vai_para_a_area_restrita_com_o_teor_mascarado(
    banco, tmp_path, monkeypatch
):
    pasta = _preparar(banco, tmp_path, monkeypatch)
    assert comando.main(["amostra", "--pasta", str(pasta), "--dia", DIA]) == 0

    trabalho = tmp_path / "restrito" / "conferencias" / "processos-teor" / DIA
    amostra = json.loads((trabalho / "amostra.json").read_text(encoding="utf-8"))
    assert amostra["semente"] == 20261108
    assert amostra["cobre_ate"] == "2026-11-02"
    assert amostra["amostra"]["resultado"] == ["a", "b"]
    assert amostra["amostra"]["valor_citado"] == ["a"]
    assert amostra["leituras"]["a"]["resultado_trecho"] == "JULGO PROCEDENTE"
    pedidos = (trabalho / "pedidos.jsonl").read_text(encoding="utf-8")
    assert [json.loads(linha)["id"] for linha in pedidos.splitlines()] == ["a", "b"]
    assert PESSOA not in pedidos and "JULGO IMPROCEDENTE" in pedidos
    # nada do teor fora da área restrita
    assert not pasta.exists() or PESSOA not in "".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in pasta.rglob("*")
        if p.is_file()
    )


def test_medir_grava_a_conferencia_e_a_montagem_publica(banco, tmp_path, monkeypatch):
    pasta = _preparar(banco, tmp_path, monkeypatch)
    comando.main(["amostra", "--pasta", str(pasta), "--dia", DIA])
    respostas = _respostas(tmp_path, "improcedente")
    assert (
        comando.main(
            [
                "medir",
                "--pasta",
                str(pasta),
                "--dia",
                DIA,
                "--respostas",
                str(respostas),
            ]
        )
        == 0
    )

    vigente = conferencia_processos.vigente(pasta)
    assert vigente is not None
    assert vigente.aprovados == frozenset(conferencia_processos.CAMPOS)
    with banco.connect() as conexao:
        processos.montar(conexao, pasta, datetime(2026, 11, 8, tzinfo=UTC))
    tabela = pd.read_parquet(pasta / "processos_comunicacoes" / "djen.parquet")
    assert sorted(tabela["resultado"]) == ["improcedente", "procedente"]


def test_medir_abaixo_do_criterio_sai_com_1_e_desliga_o_campo(
    banco, tmp_path, monkeypatch
):
    pasta = _preparar(banco, tmp_path, monkeypatch)
    comando.main(["amostra", "--pasta", str(pasta), "--dia", DIA])
    respostas = _respostas(
        tmp_path, "procedente"
    )  # o modelo discorda em "b": 50% no resultado
    assert (
        comando.main(
            [
                "medir",
                "--pasta",
                str(pasta),
                "--dia",
                DIA,
                "--respostas",
                str(respostas),
            ]
        )
        == 1
    )

    vigente = conferencia_processos.vigente(pasta)
    assert vigente is not None and "resultado" not in vigente.aprovados


def test_medir_sem_amostra_sai_com_2(banco, tmp_path, monkeypatch):
    pasta = _preparar(banco, tmp_path, monkeypatch)
    respostas = _respostas(tmp_path, "improcedente")
    assert (
        comando.main(
            [
                "medir",
                "--pasta",
                str(pasta),
                "--dia",
                DIA,
                "--respostas",
                str(respostas),
            ]
        )
        == 2
    )
