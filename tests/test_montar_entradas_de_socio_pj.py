"""O script que monta `entradas_de_socio_pj` no servidor (linha 810, PR 2): lê só do disco, grava repartido
pela raiz, não regrava o mesmo mês e para se a lista sem pessoa for de outro mês. Dados de mentira."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from base import receita_diff, socios_pj
from scripts import montar_entradas_de_socio_pj as script

AGORA = datetime(2026, 11, 11, 12, tzinfo=UTC)
EMPRESA, HOLDING, FUNDO = "11111111", "11222222", "33333333"
QSA = [
    "cnpj_basico",
    "tipo_socio",
    "qualificacao",
    "data_entrada",
    "pais",
    "raiz_socio_pj",
    "id_pessoa",
]


def _linha(empresa: str, tipo: str, raiz: str, pseudonimo: str, entrada: str) -> dict:
    return dict(
        zip(
            QSA,
            [empresa, tipo, "22", pd.Timestamp(entrada), None, raiz, pseudonimo],
            strict=True,
        )
    )


def _acervo(tmp_path: Path, mes_da_lista: str = "2023-06") -> tuple[Path, Path]:
    cnpj, destino = tmp_path / "cnpj", tmp_path / "base"
    maio = pd.DataFrame(
        [
            _linha(EMPRESA, "1", HOLDING, "", "2010-01-01"),
            _linha(EMPRESA, "2", "", "pseudonimo-1", "2010-01-01"),
        ]
    )
    junho = pd.concat(
        [maio, pd.DataFrame([_linha(EMPRESA, "1", FUNDO, "", "2023-06-02")])],
        ignore_index=True,
    )
    (cnpj / "vigente" / "qsa").mkdir(parents=True)
    junho.to_parquet(cnpj / "vigente" / "qsa" / "11.parquet", index=False)
    (cnpj / "mudancas" / "qsa").mkdir(parents=True)
    receita_diff.diff(maio, junho, receita_diff.CHAVE_DO_QSA, "2023-06").to_parquet(
        cnpj / "mudancas" / "qsa" / "2023-06.parquet", index=False
    )
    manifesto = {
        "meses": {
            m: {"arquivos": {"Socios0.zip": "a" * 64, "Simples.zip": "b" * 64}}
            for m in ("2023-05", "2023-06")
        }
    }
    (cnpj / "manifesto.json").write_text(json.dumps(manifesto), encoding="utf-8")
    lista = destino / "cnpj_estabelecimentos_pj"
    lista.mkdir(parents=True)
    pd.DataFrame(
        {"cnpj_basico": [EMPRESA, HOLDING, FUNDO], "mes_do_retrato": mes_da_lista}
    ).to_parquet(lista / "11.parquet", index=False)
    return cnpj, destino


def _rodar(cnpj: Path, destino: Path, *extras: str) -> int:
    return script.main(
        ["--cnpj", str(cnpj), "--destino", str(destino), *extras], agora=lambda: AGORA
    )


def test_grava_repartido_pela_raiz_sem_pessoa(tmp_path):
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino) == 0
    arquivos = sorted((destino / socios_pj.TABELA).glob("*.parquet"))
    assert [a.name for a in arquivos] == ["11.parquet"]
    tabela = pd.read_parquet(arquivos[0])
    assert sorted(
        zip(tabela["raiz_socio_pj"], tabela["mes_do_retrato"], strict=True)
    ) == [
        (HOLDING, "2023-05"),
        (FUNDO, "2023-06"),
    ]
    assert "id_pessoa" not in tabela.columns
    assert not tabela.astype(str).isin(["pseudonimo-1"]).any().any()
    manifesto = json.loads(
        (destino / socios_pj.TABELA / "11.json").read_text(encoding="utf-8")
    )
    assert "Socios0.zip" in json.dumps(manifesto) and "Simples.zip" not in json.dumps(
        manifesto
    )


def test_remontar_o_mesmo_mes_nao_regrava(tmp_path):
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino) == 0
    arquivo = destino / socios_pj.TABELA / "11.parquet"
    antes = arquivo.stat().st_mtime_ns
    assert (
        script.main(
            ["--cnpj", str(cnpj), "--destino", str(destino)],
            agora=lambda: datetime.now(UTC),
        )
        == 0
    )
    assert arquivo.stat().st_mtime_ns == antes


def test_lista_sem_pessoa_de_outro_mes_para(tmp_path, capsys):
    cnpj, destino = _acervo(tmp_path, mes_da_lista="2023-05")
    assert _rodar(cnpj, destino) == 1
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("FALHAS:")
    assert not (destino / socios_pj.TABELA).exists()


def test_sem_a_lista_sem_pessoa_para(tmp_path, capsys):
    """Sem `cnpj_estabelecimentos_pj` não há como tirar MEI e empresário individual: não grava nada."""
    cnpj, destino = _acervo(tmp_path)
    for arquivo in (destino / "cnpj_estabelecimentos_pj").glob("*.parquet"):
        arquivo.unlink()
    assert _rodar(cnpj, destino) == 1
    assert "montar_empresas_pj" in capsys.readouterr().out.strip().splitlines()[-1]
    assert not (destino / socios_pj.TABELA).exists()


def test_ensaio_so_conta(tmp_path, capsys):
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino, "--ensaio") == 0
    assert "'entrou': 2" in capsys.readouterr().out
    assert not (destino / socios_pj.TABELA).exists()
