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
    "2023-05": [[(A, "ALFA LTDA", "2062")], [(B, "FULANO 88800000046", "2135")]],
    "2023-06": [[(A, "ALFA S.A.", "2054")], [(B, "FULANO 88800000046", "2135")]],
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
    assert "88800000046" not in versoes.to_string()
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


# --- Situação cadastral (linha 841) ----------------------------------------------------------------
EMPRESA, OUTRA, MEI = (
    "11111111000111",
    "22222222000122",
    "11999999000199",
)  # o MEI no prefixo 11


def _estabelecimento(cnpj: str, situacao: str, fone: str = "1") -> dict:
    return {
        "cnpj": cnpj,
        "cnpj_basico": cnpj[:8],
        "matriz": True,
        "situacao_cadastral": situacao,
        "data_situacao_cadastral": pd.Timestamp("2010-01-01"),
        "motivo_situacao": "00",
        "nome_fantasia": "FANTASIA",  # o resto do arquivo: nunca vira coluna
        "telefone": fone,
    }


ESTABELECIMENTOS = [
    pd.DataFrame([_estabelecimento(EMPRESA, "02"), _estabelecimento(OUTRA, "02"), _estabelecimento(MEI, "02")]),
    pd.DataFrame([_estabelecimento(EMPRESA, "02", "2"), _estabelecimento(OUTRA, "08"), _estabelecimento(MEI, "08")]),
    pd.DataFrame([_estabelecimento(EMPRESA, "04", "2"), _estabelecimento(MEI, "08")]),
]  # fmt: skip


def _base_com_estabelecimentos(pasta: Path) -> Path:
    """Vigente de estabelecimentos por prefixo, mudanças por mês (o último numa pasta) e o manifesto."""
    cnpj = _base_do_cnpj(pasta)
    vigente = cnpj / "vigente" / "estabelecimentos"
    vigente.mkdir(parents=True)
    ultimo = ESTABELECIMENTOS[-1]
    for prefixo, parte in ultimo.groupby(ultimo["cnpj"].str[:2]):
        parte.to_parquet(vigente / f"{prefixo}.parquet", index=False)
    mudancas = cnpj / "mudancas" / "estabelecimentos"
    mudancas.mkdir(parents=True)
    pares = zip(ESTABELECIMENTOS, ESTABELECIMENTOS[1:], MESES[1:], strict=False)
    for antes, depois, mes in pares:
        mudou = diff(antes, depois, ["cnpj"], mes)
        if mes == MESES[-1]:
            (mudancas / mes).mkdir()
            mudou.to_parquet(mudancas / mes / "parte-0.parquet", index=False)
        else:
            mudou.to_parquet(mudancas / f"{mes}.parquet", index=False)
    manifesto = json.loads((cnpj / "manifesto.json").read_text(encoding="utf-8"))
    for mes in MESES:
        manifesto["meses"][mes]["arquivos"]["Estabelecimentos0.zip"] = f"est-{mes}"
    (cnpj / "manifesto.json").write_text(json.dumps(manifesto), encoding="utf-8")
    return cnpj


def _lista_sem_pessoa(destino: Path, mes: str = MESES[-1]) -> None:
    """A lista sem pessoa (`montar_empresas_pj`): a raiz do MEI não está."""
    for prefixo, raizes in (("11", [EMPRESA[:8]]), ("22", [OUTRA[:8]])):
        pasta = destino / montar.LISTA_SEM_PESSOA
        pasta.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"cnpj_basico": raizes, historico.MES: mes}).to_parquet(
            pasta / f"{prefixo}.parquet", index=False
        )


def test_a_lista_sem_pessoa_e_a_do_montar_empresas_pj():
    from scripts import montar_empresas_pj

    assert montar.LISTA_SEM_PESSOA == montar_empresas_pj.ESTABELECIMENTOS


def _situacoes(destino: Path) -> pd.DataFrame:
    arquivos = sorted((destino / montar.SITUACAO).glob("??.parquet"))
    return pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)


def test_situacao_vira_versoes_so_de_pj_com_a_origem_de_cada_mes(tmp_path):
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    _lista_sem_pessoa(destino)
    contagem = montar.montar_situacao(cnpj, destino, AGORA)
    assert set(contagem) == {"11", "22"}
    assert not (destino / montar.SITUACAO / montar.TRABALHO).exists()
    versoes = _situacoes(destino)
    assert set(versoes["cnpj_basico"]) == {EMPRESA[:8], OUTRA[:8]}  # nada do MEI
    assert "nome_fantasia" not in versoes.columns and "telefone" not in versoes.columns
    empresa = versoes[versoes["cnpj"] == "11.111.111/0001-11"]
    # o telefone mudou em 2023-06: não é versão nova
    assert list(empresa[historico.MES]) == ["2023-05", "2023-07"]
    assert list(empresa["situacao_cadastral"]) == ["02", "04"]
    assert list(empresa["origem_sha256"]) == ["est-2023-05", "est-2023-07"]
    outra = versoes[versoes["cnpj"] == "22.222.222/0001-22"]
    assert list(outra[historico.CONSTA]) == [True, True, False]
    assert (destino / montar.SITUACAO / "11.json").is_file()


def test_situacao_com_a_lista_de_outro_mes_para_tudo(tmp_path, capsys):
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    _lista_sem_pessoa(destino, mes="2023-06")
    saida = montar.main(["situacao", "--cnpj", str(cnpj), "--destino", str(destino)])
    assert saida == 1
    assert "ListaSemPessoaForaDoMes" in capsys.readouterr().out
    assert not (destino / montar.SITUACAO / "11.parquet").exists()
    assert not (destino / montar.SITUACAO / montar.TRABALHO).exists()


def test_situacao_sem_a_lista_sem_pessoa_nao_monta(tmp_path):
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    with pytest.raises(montar.ListaSemPessoaForaDoMes):
        montar.montar_situacao(cnpj, destino, AGORA)


def test_situacao_com_arquivo_do_formato_antigo_na_pasta_nao_monta(tmp_path):
    """O `<AAAA-MM>.parquet` da montagem antiga tinha MEI e não tinha `consta`: a porta leria os dois juntos."""
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    _lista_sem_pessoa(destino)
    antiga = destino / montar.SITUACAO
    antiga.mkdir(parents=True)
    (antiga / "2026-10.parquet").write_bytes(b"")
    with pytest.raises(montar.SituacaoNoFormatoAntigo):
        montar.montar_situacao(cnpj, destino, AGORA)
    assert not (antiga / "11.parquet").exists()


def test_main_da_situacao(tmp_path):
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    _lista_sem_pessoa(destino)
    argumentos = ["situacao", "--cnpj", str(cnpj), "--destino", str(destino)]
    assert montar.main(argumentos) == 0
    assert (destino / montar.SITUACAO / "22.parquet").is_file()


def test_a_porta_le_a_situacao_como_era_sem_o_futuro(tmp_path):
    """Antes do primeiro retrato público nada sai (a ficha dá not_available); a versão de 2023-07 só vale
    a partir do último dia do mês."""
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    _lista_sem_pessoa(destino)
    montar.montar_situacao(cnpj, destino, AGORA)
    porta = Porta(destino, None)

    def situacao_em(dia: date) -> list[str]:
        linhas = porta.ler(
            "cnpj_situacao_cadastral",
            como_era_em=dia,
            filtros={"cnpj": "11.111.111/0001-11"},
        )
        return list(linhas.sort_values(historico.MES)["situacao_cadastral"])

    assert situacao_em(date(2023, 5, 30)) == []
    assert situacao_em(date(2023, 7, 30)) == ["02"]
    assert situacao_em(date(2023, 7, 31)) == ["02", "04"]


# --- Situação só do vigente (linha 841, plano de segunda da Diretoria) -------------------------------------
def test_situacao_so_do_vigente_da_uma_versao_por_estabelecimento_do_mes_dele(tmp_path):
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    _lista_sem_pessoa(destino)
    montar.montar_situacao(cnpj, destino, AGORA, so_vigente=True)
    versoes = _situacoes(destino)
    # a OUTRA saiu do arquivo antes do vigente: sem a série, não tem versão; o MEI nunca entra
    assert list(versoes["cnpj"]) == ["11.111.111/0001-11"]
    assert list(versoes[historico.MES]) == [MESES[-1]]
    assert list(versoes["situacao_cadastral"]) == ["04"]
    assert list(versoes[historico.CONSTA]) == [True]
    assert list(versoes["origem_sha256"]) == [f"est-{MESES[-1]}"]
    assert "nome_fantasia" not in versoes.columns and "telefone" not in versoes.columns
    assert not (destino / montar.SITUACAO / montar.TRABALHO).exists()


def test_situacao_so_do_vigente_nem_le_as_mudancas(tmp_path, monkeypatch):
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    _lista_sem_pessoa(destino)
    # uma mudança quebrada (a cadeia de 2024-11 no servidor) não pode derrubar o modo só do vigente
    quebrada = cnpj / "mudancas" / "estabelecimentos" / f"{MESES[1]}.parquet"
    quebrada.write_bytes(b"nao e parquet")

    def nao_leia(*_argumentos):
        raise AssertionError("o modo só do vigente leu as mudanças")

    monkeypatch.setattr(montar, "_repartir_mudancas_de_estabelecimentos", nao_leia)
    contagem = montar.montar_situacao(cnpj, destino, AGORA, so_vigente=True)
    assert contagem == {"11": 1}


def test_situacao_so_do_vigente_com_a_lista_de_outro_mes_para(tmp_path):
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    _lista_sem_pessoa(destino, mes="2023-06")
    with pytest.raises(montar.ListaSemPessoaForaDoMes):
        montar.montar_situacao(cnpj, destino, AGORA, so_vigente=True)
    assert not (destino / montar.SITUACAO / "11.parquet").exists()


def test_main_da_situacao_so_do_vigente(tmp_path):
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    _lista_sem_pessoa(destino)
    argumentos = ["situacao", "--cnpj", str(cnpj), "--destino", str(destino)]
    assert montar.main([*argumentos, "--so-vigente"]) == 0
    assert set(_situacoes(destino)[historico.MES]) == {MESES[-1]}


def test_a_porta_le_a_situacao_so_do_vigente_so_depois_do_retrato(tmp_path):
    """Sem olhar o futuro: antes do último dia do mês do vigente, nada sai (a ficha dá not_available)."""
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    _lista_sem_pessoa(destino)
    montar.montar_situacao(cnpj, destino, AGORA, so_vigente=True)
    porta = Porta(destino, None)

    def situacao_em(dia: date) -> list[str]:
        linhas = porta.ler(
            "cnpj_situacao_cadastral",
            como_era_em=dia,
            filtros={"cnpj": "11.111.111/0001-11"},
        )
        return list(linhas["situacao_cadastral"])

    assert situacao_em(date(2023, 5, 30)) == []
    assert situacao_em(date(2023, 7, 30)) == []
    assert situacao_em(date(2023, 7, 31)) == ["04"]


def test_a_serie_completa_depois_do_so_vigente_tem_o_mesmo_contrato(tmp_path):
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    _lista_sem_pessoa(destino)
    montar.montar_situacao(cnpj, destino, AGORA, so_vigente=True)
    so_vigente = _situacoes(destino)
    (destino / montar.SITUACAO).rename(
        destino / "situacao-so-vigente"
    )  # movida para o lado, como manda o uso
    montar.montar_situacao(cnpj, destino, AGORA)
    completa = _situacoes(destino)
    assert list(completa.columns) == list(so_vigente.columns)
    assert dict(completa.dtypes) == dict(so_vigente.dtypes)
    # a versão que vale hoje é a mesma nos dois modos
    ultima = completa.sort_values(historico.MES).groupby("cnpj").tail(1)
    ultima = ultima[ultima[historico.CONSTA]]
    colunas = [
        "cnpj",
        "situacao_cadastral",
        "data_situacao_cadastral",
        "motivo_situacao",
        "matriz",
    ]
    assert ultima[colunas].reset_index(drop=True).equals(so_vigente[colunas])


@pytest.mark.parametrize("primeiro_so_vigente", [True, False])
def test_trocar_de_modo_sem_mover_a_pasta_para(tmp_path, capsys, primeiro_so_vigente):
    """Montar um modo por cima do outro mandaria o gravado para `.vN` sem aviso: para, sem regravar nada."""
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    _lista_sem_pessoa(destino)
    montar.montar_situacao(cnpj, destino, AGORA, so_vigente=primeiro_so_vigente)
    antes = _situacoes(destino)
    argumentos = ["situacao", "--cnpj", str(cnpj), "--destino", str(destino)]
    if not primeiro_so_vigente:
        argumentos.append("--so-vigente")
    assert montar.main(argumentos) == 1
    assert "SituacaoDeOutroModo" in capsys.readouterr().out
    assert _situacoes(destino).equals(antes)
    assert not list((destino / montar.SITUACAO).glob("*.v*"))


@pytest.mark.parametrize("so_vigente", [True, False])
def test_remontar_no_mesmo_modo_continua_valendo(tmp_path, so_vigente):
    cnpj, destino = _base_com_estabelecimentos(tmp_path / "cnpj"), tmp_path / "base"
    _lista_sem_pessoa(destino)
    montar.montar_situacao(cnpj, destino, AGORA, so_vigente=so_vigente)
    assert montar.montar_situacao(cnpj, destino, AGORA, so_vigente=so_vigente)
