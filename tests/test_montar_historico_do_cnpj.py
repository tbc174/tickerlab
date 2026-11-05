"""Montagem do histórico datado do CNPJ em arquivos (`scripts/montar_historico_do_cnpj.py`, linha 686)."""

import io
import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import cnpj_historico as historico
from base.porta import Porta
from base.receita_diff import diff, disponivel_em
from scripts import montar_historico_do_cnpj as montar

AGORA = datetime(2026, 11, 5, 18, tzinfo=UTC)
MESES = ("2023-05", "2023-06", "2023-07")
A, B, C = "11111111", "22222222", "33333333"  # A e C no prefixo 11 e 33; B no 22


def _simples(raiz: str, optante: bool, opcao: str | None = "2020-01-01") -> dict:
    return {
        "cnpj_basico": raiz,
        "optante_simples": optante,
        "data_opcao_simples": pd.Timestamp(opcao) if opcao else pd.NaT,
        "data_exclusao_simples": pd.NaT,
        "optante_mei": False,
        "data_opcao_mei": pd.NaT,
        "data_exclusao_mei": pd.NaT,
    }


RETRATOS = [
    pd.DataFrame([_simples(A, True), _simples(B, True)]),
    pd.DataFrame([_simples(A, False), _simples(B, True)]),
    pd.DataFrame([_simples(A, False), _simples(C, True, None)]),
]


def _base_do_cnpj(pasta: Path, retratos=RETRATOS, meses=MESES) -> Path:
    """A base como a carga grava: vigente por prefixo, mudanças por mês (o último numa pasta) e manifesto."""
    vigente = pasta / "vigente" / "simples"
    vigente.mkdir(parents=True)
    for prefixo, parte in retratos[-1].groupby(retratos[-1]["cnpj_basico"].str[:2]):
        parte.to_parquet(vigente / f"{prefixo}.parquet", index=False)
        (vigente / f"{prefixo}.json").write_text("{}", encoding="utf-8")
    mudancas = pasta / "mudancas" / "simples"
    mudancas.mkdir(parents=True)
    for antes, depois, mes in zip(retratos, retratos[1:], meses[1:], strict=False):
        mudou = diff(antes, depois, ["cnpj_basico"], mes)
        if mes == meses[-1]:  # mês grande: uma pasta com um arquivo por prefixo
            for prefixo, parte in mudou.groupby(mudou["cnpj_basico"].str[:2]):
                (mudancas / mes).mkdir(exist_ok=True)
                parte.to_parquet(mudancas / mes / f"{prefixo}.parquet", index=False)
        else:
            mudou.to_parquet(mudancas / f"{mes}.parquet", index=False)
            (mudancas / f"{mes}.json").write_text("{}", encoding="utf-8")
    manifesto = {
        "meses": {
            mes: {"arquivos": {"Simples.zip": f"sha-{mes}", "Socios0.zip": "outro"}}
            for mes in meses
        }
    }
    (pasta / "manifesto.json").write_text(json.dumps(manifesto), encoding="utf-8")
    return pasta


def _historico_do_simples(destino: Path) -> pd.DataFrame:
    arquivos = sorted((destino / montar.SIMPLES).glob("??.parquet"))
    return pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)


def test_simples_vira_versoes_por_prefixo_com_a_origem_de_cada_mes(tmp_path):
    cnpj, destino = _base_do_cnpj(tmp_path / "cnpj"), tmp_path / "base"
    contagem = montar.montar_simples(cnpj, destino, AGORA)
    assert set(contagem) == {"11", "22", "33"}
    assert not (destino / montar.SIMPLES / montar.TRABALHO).exists()
    versoes = _historico_do_simples(destino)
    da_a = versoes[versoes["cnpj_basico"] == A]
    assert list(da_a[historico.MES]) == ["2023-05", "2023-06"]
    assert list(da_a["optante_simples"]) == [True, False]
    assert list(da_a["origem_sha256"]) == ["sha-2023-05", "sha-2023-06"]
    da_b = versoes[versoes["cnpj_basico"] == B]
    assert list(da_b[historico.CONSTA]) == [True, False]
    assert (destino / montar.SIMPLES / "11.json").is_file()  # manifesto com as origens


def test_remontar_sem_mes_novo_nao_regrava(tmp_path):
    cnpj, destino = _base_do_cnpj(tmp_path / "cnpj"), tmp_path / "base"
    montar.montar_simples(cnpj, destino, AGORA)
    arquivo = destino / montar.SIMPLES / "11.parquet"
    antes = arquivo.read_bytes()
    montar.montar_simples(cnpj, destino, datetime(2026, 12, 1, tzinfo=UTC))
    assert arquivo.read_bytes() == antes


def test_historico_que_nao_confere_com_o_vigente_para_tudo(tmp_path, capsys):
    cnpj, destino = _base_do_cnpj(tmp_path / "cnpj"), tmp_path / "base"
    vigente = cnpj / "vigente" / "simples" / "11.parquet"
    pd.read_parquet(vigente).assign(optante_simples=True).to_parquet(
        vigente, index=False
    )
    saida = montar.main(["simples", "--cnpj", str(cnpj), "--destino", str(destino)])
    assert saida == 1
    assert "FALHAS: histórico do CNPJ: HistoricoNaoConfere" in capsys.readouterr().out
    assert not (destino / montar.SIMPLES / montar.TRABALHO).exists()


def test_main_do_simples(tmp_path):
    cnpj, destino = _base_do_cnpj(tmp_path / "cnpj"), tmp_path / "base"
    assert montar.main(["simples", "--cnpj", str(cnpj), "--destino", str(destino)]) == 0
    assert (destino / montar.SIMPLES / "22.parquet").is_file()


def test_a_porta_le_o_simples_como_era_sem_o_futuro(tmp_path):
    """A versão de 2023-06 vale desde o dia 21 (`disponivel_em`); a porta, mensal como as outras fontes de
    governo, só a mostra a partir do último dia do mês."""
    cnpj, destino = _base_do_cnpj(tmp_path / "cnpj"), tmp_path / "base"
    montar.montar_simples(cnpj, destino, AGORA)
    porta = Porta(destino, None)

    def meses_em(dia: date) -> list[str]:
        linhas = porta.ler(
            "cnpj_simples_historico", como_era_em=dia, filtros={"cnpj_basico": A}
        )
        return sorted(linhas[historico.MES])

    assert meses_em(date(2023, 5, 30)) == []
    assert meses_em(date(2023, 6, 29)) == ["2023-05"]
    assert meses_em(date(2023, 6, 30)) == ["2023-05", "2023-06"]


# --- Empresas --------------------------------------------------------------------------------------
def _zip(pasta: Path, nome: str, linhas: list[tuple[str, str, str]]) -> Path:
    texto = "\n".join(f'"{r}";"{s}";"{n}";"49";"1000,00";"01";""' for r, s, n in linhas)
    arquivo = pasta / nome
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as zipado:
        zipado.writestr("EMPRECSV", texto.encode("latin-1"))
    arquivo.write_bytes(memoria.getvalue())
    return arquivo


EMPRESAS_POR_MES = {
    "2023-05": [[(A, "ALFA LTDA", "2062")], [(B, "FULANO 12345678909", "2135")]],
    "2023-06": [[(A, "ALFA S.A.", "2054")], [(B, "FULANO 12345678909", "2135")]],
    "2023-07": [[(A, "ALFA S.A.", "2054")], [(C, "GAMA LTDA", "2062")]],
}


def _baixar(_pasta: Path):
    def baixar(mes: str, temporaria: Path) -> list[Path]:
        return [
            _zip(temporaria, f"Empresas{n}.zip", linhas)
            for n, linhas in enumerate(EMPRESAS_POR_MES[mes])
        ]

    return baixar


def _historico_de_empresas(destino: Path) -> pd.DataFrame:
    arquivos = sorted((destino / montar.EMPRESAS).glob("??.parquet"))
    return pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)


def test_empresas_mes_a_mes_sem_nome_de_pessoa(tmp_path):
    destino = tmp_path / "base"
    montar.carregar_empresas(MESES, destino, _baixar(tmp_path), lambda: AGORA)
    versoes = _historico_de_empresas(destino)
    da_a = versoes[versoes["cnpj_basico"] == A]
    assert list(da_a["razao_social"]) == ["ALFA LTDA", "ALFA S.A."]
    assert list(da_a["natureza_juridica"]) == ["2062", "2054"]
    assert list(da_a[historico.DISPONIVEL_EM]) == [
        disponivel_em("2023-05"),
        disponivel_em("2023-06"),
    ]
    da_b = versoes[versoes["cnpj_basico"] == B]
    assert (
        da_b["razao_social"].isna().all()
    )  # empresário individual: o nome é da pessoa
    assert list(da_b[historico.CONSTA]) == [True, False]
    assert "12345678909" not in versoes.to_string()
    gravados = json.loads(
        (destino / montar.EMPRESAS / montar.MESES).read_text(encoding="utf-8")
    )
    assert sorted(gravados["meses"]) == list(MESES)
    assert not (destino / montar.EMPRESAS / montar.TRABALHO).exists()


def test_empresas_retoma_do_ultimo_mes_e_nao_volta_no_tempo(tmp_path):
    destino = tmp_path / "base"
    montar.carregar_empresas(MESES[:2], destino, _baixar(tmp_path), lambda: AGORA)
    assert montar.pendentes(MESES, destino) == ["2023-07"]
    pedidos = []

    def baixar(mes, temporaria):
        pedidos.append(mes)
        return _baixar(tmp_path)(mes, temporaria)

    montar.carregar_empresas(MESES, destino, baixar, lambda: AGORA)
    assert pedidos == ["2023-07"]
    zips = _baixar(tmp_path)("2023-05", tmp_path)
    with pytest.raises(montar.MesForaDeOrdem):
        montar.processar_mes_de_empresas("2023-05", destino, zips, AGORA)


def test_empresas_mes_pela_metade_nao_duplica_versao(tmp_path):
    """Queda depois de gravar os prefixos e antes do `meses.json`: repetir o mês não acrescenta nada."""
    destino = tmp_path / "base"
    montar.carregar_empresas(MESES, destino, _baixar(tmp_path), lambda: AGORA)
    antes = _historico_de_empresas(destino)
    arquivo = destino / montar.EMPRESAS / montar.MESES
    gravados = json.loads(arquivo.read_text(encoding="utf-8"))
    del gravados["meses"]["2023-07"]
    arquivo.write_text(json.dumps(gravados), encoding="utf-8")
    zips = _baixar(tmp_path)("2023-07", tmp_path)
    assert montar.processar_mes_de_empresas("2023-07", destino, zips, AGORA) == 0
    pd.testing.assert_frame_equal(_historico_de_empresas(destino), antes)
