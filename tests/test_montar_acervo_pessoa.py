"""Montagem do `acervo_pessoa/` (linha 808): arquivos de mentira, sem internet. Todo nome é inventado."""

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import receita_pessoa as rp
from scripts import montar_acervo_pessoa as montar

AGORA = datetime(2026, 11, 10, tzinfo=UTC)
SEM_REP = '"***000000**";"";"00"'


def _linha(raiz, tipo, nome, faixa="5", representante=SEM_REP):
    return (
        f'"{raiz}";"{tipo}";"{nome}";"***123456**";"49";"20200131";"";'
        f'{representante};"{faixa}"\n'
    )


SOCIOS_0 = (
    _linha("11222333", "2", "FULANA EXEMPLO")
    + _linha("11222333", "2", "FULANA EXEMPLO")  # repetida: sai uma só
    + _linha("11222333", "2", "CRIANCA EXEMPLO", faixa="1")
    + _linha("11222333", "1", "HOLDING DE MENTIRA LTDA", faixa="0")
)
SOCIOS_1 = _linha("22333444", "2", "BELTRANO EXEMPLO") + _linha(
    "22333444", "2", "REPRESENTADO EXEMPLO", representante='"***654321**";"MAE";"35"'
)


def _acervo(tmp_path: Path) -> tuple[Path, Path]:
    """Um acervo de mentira: `base/cnpj/manifesto.json` e os ZIPs no bruto pelo SHA-256."""
    acervo = tmp_path / "acervo"
    cnpj, bruto = acervo / "base" / "cnpj", acervo / "bruto" / "rfb-cnpj"
    cnpj.mkdir(parents=True)
    (bruto / "2026").mkdir(parents=True)
    arquivos = {}
    for nome, texto in (("Socios0.zip", SOCIOS_0), ("Socios1.zip", SOCIOS_1)):
        provisorio = tmp_path / nome
        with zipfile.ZipFile(provisorio, "w") as arquivo:
            arquivo.writestr("K.SOCIOCSV", texto.encode("latin-1"))
        sha = hashlib.sha256(provisorio.read_bytes()).hexdigest()
        provisorio.rename(bruto / "2026" / f"{sha}.zip")
        arquivos[nome] = sha
    arquivos["Empresas0.zip"] = "0" * 64  # não é de sócios: nem é procurado
    meses = {"2026-09": {"arquivos": {}}, "2026-10": {"arquivos": arquivos}}
    (cnpj / "manifesto.json").write_text(json.dumps({"meses": meses}))
    return cnpj, bruto


def _tabela(destino: Path) -> pd.DataFrame:
    partes = sorted((destino / montar.SOCIOS).glob("*.parquet"))
    return pd.concat([pd.read_parquet(p) for p in partes], ignore_index=True)


def test_monta_so_os_adultos_e_conta_os_descartes(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    manifesto = montar.carregar(cnpj, bruto, destino, AGORA)

    tabela = _tabela(destino)
    assert sorted(tabela["nome_socio"]) == ["BELTRANO EXEMPLO", "FULANA EXEMPLO"]
    assert set(tabela.columns) == {
        "cnpj_basico",
        "nome_socio",
        "qualificacao",
        "data_entrada",
        "mes_do_retrato",
    }
    assert set(tabela["mes_do_retrato"]) == {"2026-10"}
    assert sorted(p.name for p in (destino / montar.SOCIOS).iterdir()) == [
        "11.parquet",
        "22.parquet",
    ]
    assert manifesto["tabelas"] == {montar.SOCIOS: {"linhas": 2, "empresas": 2}}
    assert manifesto["descartes"][rp.MENOR_PELA_FAIXA] == 1
    assert manifesto["descartes"][rp.COM_REPRESENTANTE] == 1
    assert manifesto["descartes"][rp.NAO_E_PESSOA_FISICA] == 1
    assert not (destino / montar.TRABALHO).exists()


def test_manifesto_gravado_so_tem_numeros_e_sha(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    montar.carregar(cnpj, bruto, destino, AGORA)
    texto = (destino / montar.MANIFESTO).read_text(encoding="utf-8")
    assert "EXEMPLO" not in texto and "***" not in texto
    assert json.loads(texto)["mes_do_retrato"] == "2026-10"


def test_remontar_troca_a_tabela_inteira(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    montar.carregar(cnpj, bruto, destino, AGORA)
    velho = destino / montar.SOCIOS / "99.parquet"
    pd.DataFrame({"cnpj_basico": ["99000000"]}).to_parquet(velho)
    montar.carregar(cnpj, bruto, destino, AGORA)
    assert not velho.exists()
    assert len(_tabela(destino)) == 2


@pytest.mark.parametrize("pasta", ["base/acervo_pessoa", "acervo_pessoa"])
def test_destino_dentro_do_acervo_e_recusado(tmp_path, pasta):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "acervo" / pasta
    with pytest.raises(montar.DestinoRecusadoError):
        montar.carregar(cnpj, bruto, destino, AGORA)
    assert not destino.exists()


def test_destino_com_outro_nome_e_recusado(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    with pytest.raises(montar.DestinoRecusadoError):
        montar.carregar(cnpj, bruto, tmp_path / "fora" / "acervo_api", AGORA)


def test_zip_que_nao_esta_no_bruto_para_tudo(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    next((bruto / "2026").glob("*.zip")).unlink()
    destino = tmp_path / "fora" / "acervo_pessoa"
    with pytest.raises(montar.ZipAusenteError):
        montar.carregar(cnpj, bruto, destino, AGORA)
    assert not (destino / montar.SOCIOS).exists()


def test_zip_adulterado_para_tudo(tmp_path):
    cnpj, bruto = _acervo(tmp_path)
    guardado = next((bruto / "2026").glob("*.zip"))
    with zipfile.ZipFile(guardado, "w") as arquivo:
        arquivo.writestr("K.SOCIOCSV", _linha("11222333", "2", "OUTRO EXEMPLO"))
    destino = tmp_path / "fora" / "acervo_pessoa"
    with pytest.raises(montar.ZipAusenteError):
        montar.carregar(cnpj, bruto, destino, AGORA)
    assert not (destino / montar.SOCIOS).exists()


def test_ensaio_diz_o_mes_e_nao_grava(tmp_path, capsys):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    argumentos = ["--cnpj", str(cnpj), "--bruto", str(bruto), "--destino", str(destino)]
    assert montar.main([*argumentos, "--ensaio"]) == 0
    saida = capsys.readouterr().out
    assert "2026-10" in saida and "Socios0.zip" in saida
    assert not destino.exists()


def test_main_monta_e_a_saida_nao_tem_nome(tmp_path, capsys):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "fora" / "acervo_pessoa"
    argumentos = ["--cnpj", str(cnpj), "--bruto", str(bruto), "--destino", str(destino)]
    assert montar.main(argumentos) == 0
    saida = capsys.readouterr().out
    assert '"linhas": 2' in saida and "EXEMPLO" not in saida


def test_main_com_destino_recusado_sai_com_falha(tmp_path, capsys):
    cnpj, bruto = _acervo(tmp_path)
    destino = tmp_path / "acervo" / "acervo_pessoa"
    argumentos = ["--cnpj", str(cnpj), "--bruto", str(bruto), "--destino", str(destino)]
    assert montar.main(argumentos) == 1
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("FALHAS:")
