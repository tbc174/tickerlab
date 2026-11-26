"""A tabela `cnpj_nomes_pj` (linha 1033; `base/nomes_de_empresa.py` e `scripts/montar_nomes_pj.py`): razão social,
nome fantasia e razão social antiga só de empresa. Arquivos de mentira, sem internet, nomes inventados."""

import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import nomes_de_empresa as nomes
from scripts import montar_nomes_pj as montar
from tests.ajudantes_de_cpf import CPF_DE_TESTE, formatado

AGORA = datetime(2026, 11, 26, tzinfo=UTC)


def _linha_do_estabelecimento(raiz: str, ordem: str, fantasia: str) -> str:
    campos = [""] * 30
    campos[0], campos[1], campos[2], campos[3], campos[4] = (
        raiz,
        ordem,
        "00",
        "1",
        fantasia,
    )
    campos[13], campos[14] = "RUA", "ENDERECO QUE NAO SAI"
    campos[27] = "CONTATO@EXEMPLO.INVALID"
    return ";".join(f'"{c}"' for c in campos)


ESTABELECIMENTOS = [
    ("33000167", "0001", "MARCA ALFA"),
    ("33000167", "0002", "MARCA ALFA"),  # a filial repete o nome: uma linha só
    ("33000167", "0003", "ALFA POSTO CENTRO"),
    (
        "33111222",
        "0001",
        "BAR DO FULANO",
    ),  # fora da vista sem pessoa (MEI ou individual)
    ("33444555", "0001", ""),
    ("33444555", "0002", f"BETA {formatado(CPF_DE_TESTE)}"),  # CPF escrito no nome sai
    ("33444555", "0003", "VENDAS@BETA.INVALID"),  # contato não é nome
    (
        "33444555",
        "0004",
        "BETA COMERCIO",
    ),  # igual à razão social sem a forma jurídica: fica uma vez
]


def _zip(tmp_path: Path) -> Path:
    caminho = tmp_path / "Estabelecimentos0.zip"
    texto = (
        "\n".join(_linha_do_estabelecimento(*linha) for linha in ESTABELECIMENTOS)
        + "\n"
    )
    with zipfile.ZipFile(caminho, "w") as arquivo:
        arquivo.writestr("K.ESTABELE", texto.encode("latin-1"))
    return caminho


def _base(tmp_path: Path, com_historico: bool = True) -> Path:
    destino = tmp_path / "base"
    empresas = pd.DataFrame(
        {
            "cnpj_basico": ["33000167", "33444555", "33666777"],
            "razao_social": [
                "ALFA ENERGIA S.A.",
                "BETA COMERCIO LTDA",
                "SO NA LISTA DE EMPRESAS LTDA",
            ],
            "mes_do_retrato": "2026-10",
        }
    )
    vista = pd.DataFrame(
        {"cnpj_basico": ["33000167", "33444555"], "mes_do_retrato": "2026-10"}
    )
    tabelas = {"cnpj_empresas_pj": empresas, "cnpj_estabelecimentos_pj": vista}
    if com_historico:
        tabelas["cnpj_empresas_historico"] = pd.DataFrame(
            {
                "cnpj_basico": ["33000167", "33000167", "33000167", "33111222"],
                "mes_do_retrato": ["2023-05", "2024-03", "2025-01", "2023-05"],
                "consta": True,
                "razao_social": [
                    "PETRO ANTIGA S.A.",
                    "ALFA ENERGIA S/A",
                    "ALFA ENERGIA S.A.",
                    "FULANO DE TAL",
                ],
            }
        )
    for nome, tabela in tabelas.items():
        pasta = destino / nome
        pasta.mkdir(parents=True)
        tabela.to_parquet(pasta / "33.parquet", index=False)
    return destino


def _linhas(destino: Path) -> pd.DataFrame:
    return pd.read_parquet(destino / montar.NOMES / "33.parquet")


def test_normalizar_tira_acento_pontuacao_e_junta_letras_soltas():
    assert (
        nomes.normalizar("  D P B Avicultura - Comércio S/A ")
        == "DPB AVICULTURA COMERCIO SA"
    )
    assert nomes.normalizar("Silva e Filhos") == "SILVA E FILHOS"
    assert nomes.sem_forma_juridica("ALFA ENERGIA SA") == "ALFA ENERGIA"
    assert nomes.sem_forma_juridica("BETA COMERCIO LTDA ME") == "BETA COMERCIO"
    assert nomes.sem_forma_juridica("SA") == "SA"  # nunca fica vazio


def test_monta_razao_fantasia_e_antiga_so_de_empresa(tmp_path):
    destino = _base(tmp_path)
    contagem = montar.montar(destino, [_zip(tmp_path)], AGORA)
    linhas = _linhas(destino)
    assert set(linhas["cnpj_basico"]) == {"33000167", "33444555"}
    pares = set(zip(linhas["tipo_de_nome"], linhas["nome_de_empresa"], strict=True))
    assert pares == {
        ("razao_social", "ALFA ENERGIA S.A."),
        ("nome_fantasia", "MARCA ALFA"),
        ("nome_fantasia", "ALFA POSTO CENTRO"),
        ("razao_social_anterior", "PETRO ANTIGA S.A."),
        ("razao_social", "BETA COMERCIO LTDA"),
        ("nome_fantasia", "BETA"),
    }
    antiga = linhas[linhas["tipo_de_nome"] == "razao_social_anterior"].iloc[0]
    assert antiga["trocado_em_mes"] == "2024-03"
    assert set(linhas["mes_do_retrato"]) == {"2026-10"}
    assert contagem == {
        "razao_social": 2,
        "nome_fantasia": 3,
        "razao_social_anterior": 1,
    }
    tudo = linhas.to_csv()
    cpf = formatado(CPF_DE_TESTE)[:7]
    for proibido in ("FULANO", cpf, "@", "ENDERECO", "SO NA LISTA"):
        assert proibido not in tudo


def _acrescentar_ao_historico(destino: Path, **versao: object) -> None:
    arquivo = destino / montar.HISTORICO / "33.parquet"
    historico = pd.read_parquet(arquivo)
    nova = pd.DataFrame([{"cnpj_basico": "33000167", "consta": True, **versao}])
    pd.concat([historico, nova], ignore_index=True).to_parquet(arquivo, index=False)


def test_mes_do_historico_depois_do_retrato_nao_entra(tmp_path):
    """O histórico pode estar um mês à frente das listas: o nome desse mês é futuro para o retrato."""
    destino = _base(tmp_path)
    _acrescentar_ao_historico(
        destino, mes_do_retrato="2026-11", razao_social="NOME DO MES QUE VEM LTDA"
    )
    montar.montar(destino, [_zip(tmp_path)], AGORA)
    linhas = _linhas(destino)
    assert "NOME DO MES QUE VEM LTDA" not in set(linhas["nome_de_empresa"])
    assert "2026-11" not in set(linhas["trocado_em_mes"])
    de_hoje = linhas[linhas["nome_de_empresa"] == "ALFA ENERGIA S.A."]
    assert set(de_hoje["trocado_em_mes"]) == {""}


def test_versao_do_tempo_de_empresario_individual_nunca_vira_nome_antigo(tmp_path):
    """Quem era empresário individual e virou sociedade tinha o nome da pessoa como razão social."""
    destino = _base(tmp_path)
    _acrescentar_ao_historico(
        destino,
        mes_do_retrato="2023-04",
        razao_social="PESSOA INVENTADA DE TAL",
        natureza_juridica="2135",
    )
    montar.montar(destino, [_zip(tmp_path)], AGORA)
    assert "PESSOA INVENTADA" not in _linhas(destino).to_csv()


def test_versao_guardada_das_listas_nao_vira_prefixo(tmp_path):
    destino = _base(tmp_path)
    for tabela in (montar.EMPRESAS, montar.ESTABELECIMENTOS):
        antiga = pd.read_parquet(destino / tabela / "33.parquet")
        antiga.to_parquet(destino / tabela / "33.v1.parquet", index=False)
    contagem = montar.montar(destino, [_zip(tmp_path)], AGORA)
    assert contagem["razao_social"] == 2
    assert sorted(p.name for p in (destino / montar.NOMES).rglob("*.parquet")) == [
        "33.parquet"
    ]


def test_sem_o_historico_monta_sem_razao_social_antiga(tmp_path):
    destino = _base(tmp_path, com_historico=False)
    contagem = montar.montar(destino, [_zip(tmp_path)], AGORA)
    assert contagem["razao_social_anterior"] == 0
    assert contagem["nome_fantasia"] == 3


def test_remontar_o_mesmo_mes_nao_regrava(tmp_path):
    destino = _base(tmp_path)
    zipado = _zip(tmp_path)
    montar.montar(destino, [zipado], AGORA)
    arquivo = destino / montar.NOMES / "33.parquet"
    antes = arquivo.stat().st_mtime_ns
    montar.montar(destino, [zipado], datetime(2026, 11, 27, tzinfo=UTC))
    assert arquivo.stat().st_mtime_ns == antes


def test_sem_as_listas_sem_pessoa_a_montagem_para(tmp_path):
    with pytest.raises(montar.SemListaDeEmpresas):
        montar.montar(tmp_path / "base", [_zip(tmp_path)], AGORA)


def test_vista_de_outro_mes_para_a_montagem(tmp_path):
    destino = _base(tmp_path)
    arquivo = destino / montar.ESTABELECIMENTOS / "33.parquet"
    pd.read_parquet(arquivo).assign(mes_do_retrato="2026-09").to_parquet(arquivo)
    with pytest.raises(montar.SemListaDeEmpresas):
        montar.montar(destino, [_zip(tmp_path)], AGORA)


def test_prefixo_que_ficou_no_mes_anterior_para_a_montagem(tmp_path):
    """Montagem das listas interrompida: um prefixo velho deixaria passar quem virou empresário individual."""
    destino = _base(tmp_path)
    for tabela in (montar.EMPRESAS, montar.ESTABELECIMENTOS):
        velho = pd.read_parquet(destino / tabela / "33.parquet").head(1)
        velho.assign(cnpj_basico="44000167", mes_do_retrato="2026-09").to_parquet(
            destino / tabela / "44.parquet", index=False
        )
    with pytest.raises(montar.SemListaDeEmpresas):
        montar.montar(destino, [_zip(tmp_path)], AGORA)


@pytest.mark.parametrize(
    "fantasia",
    [
        "DISK TESTE 3333-4444",
        "DISK TESTE (11) 98888-7777",
        "GAS INVENTADO 33334444",
        "TELE INVENTADA 0800 123 456",
        "OFICINA RUA INVENTADA 123",
        "MERCADO AV. INVENTADA, 45",
        "LOJA 01000-000",
        "GAS INVENTADO " + "1" * 10,  # telefone com DDD, sem separador
    ],
)
def test_nome_fantasia_com_telefone_ou_endereco_nao_entra(fantasia):
    assert _fantasias_que_ficam(fantasia) == []


@pytest.mark.parametrize(
    "fantasia",
    [
        "POSTO 2000",
        "MERCADO 24 HORAS",
        "AV TECNOLOGIA",
        "AUTO PECAS BR 101",
        "AGRO DESDE 1990",
    ],
)
def test_nome_fantasia_com_numero_de_negocio_fica(fantasia):
    assert _fantasias_que_ficam(fantasia) == [fantasia]


def _fantasias_que_ficam(fantasia: str) -> list[str]:
    empresas = pd.DataFrame(
        {"cnpj_basico": ["33000167"], "razao_social": ["ALFA S.A."]}
    )
    fantasias = pd.DataFrame({"cnpj_basico": ["33000167"], "nome_fantasia": [fantasia]})
    tabela = nomes.tabela_de_nomes(empresas, fantasias, None)
    return list(tabela[tabela["tipo_de_nome"] == "nome_fantasia"]["nome_de_empresa"])


def test_carregar_baixa_o_mes_da_lista_de_empresas_e_nao_deixa_o_zip(tmp_path):
    destino = _base(tmp_path)
    pedidos = []

    def baixar(mes: str, pasta: Path) -> list[Path]:
        pedidos.append(mes)
        return [_zip(pasta)]

    montar.carregar(destino, baixar, lambda: AGORA)
    assert pedidos == ["2026-10"]
    assert not list(destino.rglob("*.zip"))
