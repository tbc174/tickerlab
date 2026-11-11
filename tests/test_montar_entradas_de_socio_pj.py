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


def test_lista_reduzida_as_raizes_do_qsa_sem_raiz_fora_da_lista(tmp_path):
    """A lista sem pessoa é lida só nas raízes do QSA (memória), e nenhuma raiz fora dela sai na tabela."""
    cnpj, destino = _acervo(tmp_path)
    lista = destino / "cnpj_estabelecimentos_pj" / "11.parquet"
    fora_do_qsa = ["99999999", "98888888"]
    pd.DataFrame(
        {"cnpj_basico": [EMPRESA, HOLDING, *fora_do_qsa], "mes_do_retrato": "2023-06"}
    ).to_parquet(lista, index=False)  # o fundo deixou de ser só empresa
    assert script._pessoas_juridicas(destino, "2023-06", {EMPRESA, HOLDING, FUNDO}) == {
        EMPRESA,
        HOLDING,
    }
    assert _rodar(cnpj, destino) == 0
    tabela = pd.read_parquet(destino / socios_pj.TABELA / "11.parquet")
    raizes = set(tabela["cnpj_basico"]) | set(tabela["raiz_socio_pj"])
    assert raizes == {EMPRESA, HOLDING}


OUTRA = "44444444"


def _mes_seguinte(cnpj: Path, destino: Path) -> None:
    """Chega o retrato de 2023-07, em que a empresa ganha mais uma sócia PJ."""
    vigente = cnpj / "vigente" / "qsa" / "11.parquet"
    junho = pd.read_parquet(vigente)
    julho = pd.concat(
        [junho, pd.DataFrame([_linha(EMPRESA, "1", OUTRA, "", "2023-07-03")])],
        ignore_index=True,
    )
    julho.to_parquet(vigente, index=False)
    receita_diff.diff(junho, julho, receita_diff.CHAVE_DO_QSA, "2023-07").to_parquet(
        cnpj / "mudancas" / "qsa" / "2023-07.parquet", index=False
    )
    manifesto = json.loads((cnpj / "manifesto.json").read_text(encoding="utf-8"))
    manifesto["meses"]["2023-07"] = manifesto["meses"]["2023-06"]
    (cnpj / "manifesto.json").write_text(json.dumps(manifesto), encoding="utf-8")
    pd.DataFrame(
        {"cnpj_basico": [EMPRESA, HOLDING, FUNDO, OUTRA], "mes_do_retrato": "2023-07"}
    ).to_parquet(destino / "cnpj_estabelecimentos_pj" / "11.parquet", index=False)


def test_mes_novo_fora_da_faixa_nao_substitui_a_tabela(tmp_path, capsys, monkeypatch):
    """Guarda de faixa (Diretoria, 11/11/2026): um mês novo com entradas ou saídas demais é arquivo da Receita com
    defeito, como o de 2024-09; a tabela gravada fica como estava e a saída é de falha, com o mês e a contagem."""
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino) == 0
    arquivo = destino / socios_pj.TABELA / "11.parquet"
    antes = arquivo.read_bytes()
    _mes_seguinte(cnpj, destino)
    monkeypatch.setitem(script.MAXIMO_POR_MES, receita_diff.ENTROU, 0)
    assert _rodar(cnpj, destino) == 1
    ultima = capsys.readouterr().out.strip().splitlines()[-1]
    assert ultima.startswith("FALHAS:") and "2023-07" in ultima and "entrou 1" in ultima
    assert "2023-06" not in ultima  # mês já gravado não conta de novo
    assert arquivo.read_bytes() == antes


def test_mes_novo_dentro_da_faixa_grava(tmp_path):
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino) == 0
    _mes_seguinte(cnpj, destino)
    assert _rodar(cnpj, destino) == 0
    tabela = pd.read_parquet(destino / socios_pj.TABELA / "11.parquet")
    assert (OUTRA, "2023-07") in set(
        zip(tabela["raiz_socio_pj"], tabela["mes_do_retrato"], strict=True)
    )


def test_primeiro_mes_nao_conta_na_faixa(monkeypatch):
    """O primeiro mês traz todas as sócias que já estavam (meio milhão na base): não é movimento do mês."""
    monkeypatch.setitem(script.MAXIMO_POR_MES, receita_diff.ENTROU, 0)
    tabela = pd.DataFrame(
        {"movimento": [receita_diff.ENTROU] * 3, socios_pj.MES: "2023-05"}
    )
    script._conferir_faixa(tabela, "2023-05", set())
    try:
        script._conferir_faixa(tabela, "2023-04", set())
    except ValueError as erro:
        assert "2023-05 entrou 3" in str(erro)
    else:
        raise AssertionError("o mês novo acima da faixa devia parar")


def test_faixa_da_base():
    assert script.MAXIMO_POR_MES == {
        receita_diff.ENTROU: 30_000,
        receita_diff.SAIU: 10_000,
    }


def test_se_houver_mes_novo_nao_remonta_o_mes_gravado(tmp_path, capsys):
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino) == 0
    arquivo = destino / socios_pj.TABELA / "11.parquet"
    antes = arquivo.stat().st_mtime_ns
    assert _rodar(cnpj, destino, "--se-houver-mes-novo") == 0
    assert "a tabela já tem 2023-06" in capsys.readouterr().out
    assert arquivo.stat().st_mtime_ns == antes


def test_se_houver_mes_novo_espera_a_lista_do_mes(tmp_path, capsys):
    """Retrato novo no QSA, mas o montar_empresas_pj ainda não rodou: espera, sem falhar (o cron é diário)."""
    cnpj, destino = _acervo(tmp_path, mes_da_lista="2023-05")
    assert _rodar(cnpj, destino, "--se-houver-mes-novo") == 0
    assert "esperando o montar_empresas_pj de 2023-06" in capsys.readouterr().out
    assert not (destino / socios_pj.TABELA).exists()


def test_se_houver_mes_novo_monta_o_mes_novo(tmp_path):
    cnpj, destino = _acervo(tmp_path)
    assert _rodar(cnpj, destino) == 0
    _mes_seguinte(cnpj, destino)
    assert _rodar(cnpj, destino, "--se-houver-mes-novo") == 0
    tabela = pd.read_parquet(destino / socios_pj.TABELA / "11.parquet")
    assert "2023-07" in set(tabela["mes_do_retrato"])
