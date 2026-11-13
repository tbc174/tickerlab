"""Estabelecimentos do SIF e transações da Receita na base: só pessoa jurídica, nenhum nome (linha 904, PR 2).

Todos os dados daqui são inventados. A Receita guardada é um dublê (`descobrir`): devolve as raízes de pessoa."""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from base import cnpj as cnpjs
from base import derivadas_do_lote_3b as derivadas
from base.parquet import GRAVADO, IGUAL
from scripts import carga_receita_transacoes as carga
from scripts import montar_tabelas_lote_3b as montagem


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
OUTRA = _cnpj("33000167")
MEI = _cnpj("44555666")  # raiz que a Receita guardada diz ser de pessoa
DIA = date(2026, 11, 2)
AGORA = pd.Timestamp("2026-11-13T12:00:00Z")


def _descobrir(*pessoas: str):
    numeros = cnpjs.ordenados(
        cnpjs.raizes_em_numeros(pd.Series([p[:8] for p in pessoas], dtype="string"))
    )
    return lambda _raizes: numeros


def _registrados(*pares: tuple[str, str]) -> bytes:
    cabecalho = (
        "CPF_CNPJ;RAZAO_SOCIAL;NOME_FANTASIA;NR_SIF;SITUACAO;MUNICIPIO;UF;"
        "AREA_CATEGORIA;CATEGORIA_CLASSE"
    )
    linhas = [
        f"{doc};EMPRESA DE MENTIRA;FANTASIA;{sif};ATIVO;CIDADE;GO;CARNES;ABATE"
        for doc, sif in pares
    ]
    return "\n".join([cabecalho, *linhas]).encode()


def _individual(*cnpjs_: str) -> bytes:
    linhas = [
        f"NOME INVENTADO {i};{cnpjs.formatar(c)};1000{i}.000001/2023-01;out/23;100;10;90;;50\r\n"
        for i, c in enumerate(cnpjs_)
    ]
    return ("C;D;P;Data;V;R;D;C;S\r\n" + "".join(linhas)).encode()


def _adesao(*cnpjs_: str) -> bytes:
    linhas = [
        f"{cnpjs.formatar(c)};PRLF 2023 art. 11 I (Geral);31/07/2023;300,00;200,00;0,00;0,00;0,00;0,00;6\r\n"
        for c in cnpjs_
    ]
    return ("A;B;C;D;E;F;G;H;I;J\r\n" + "".join(linhas)).encode()


def _pasta_do_sigsif(pasta: Path) -> None:
    (pasta / "registrados.csv").write_bytes(
        _registrados(
            (cnpjs.formatar(EMPRESA), "100"),
            (cnpjs.formatar(EMPRESA), "100"),  # listado duas vezes
            (cnpjs.formatar(MEI), "200"),
            ("***.123.456-**", "300"),  # CPF mascarado
        )
    )
    (pasta / montagem.MODIFICADOS).write_text(
        json.dumps({"registrados.csv": DIA.isoformat()}), encoding="utf-8"
    )


def _pasta_das_transacoes(pasta: Path) -> None:
    (pasta / carga.ARQUIVO_INDIVIDUAL).write_bytes(_individual(EMPRESA, MEI, OUTRA))
    (pasta / carga.ARQUIVO_ADESAO).write_bytes(_adesao(EMPRESA, MEI))
    datas = {n: DIA.isoformat() for n in carga.ARQUIVOS}
    (pasta / carga.MODIFICADOS).write_text(json.dumps(datas), encoding="utf-8")


def test_estabelecimentos_sem_razao_social_sem_pessoa_e_sem_repetida():
    from base import sigsif

    lido = sigsif.ler_estabelecimentos(
        _registrados(
            (cnpjs.formatar(EMPRESA), "100"),
            (cnpjs.formatar(EMPRESA), "100"),
            (cnpjs.formatar(MEI), "200"),
        ),
        DIA,
    )
    tabela, contagem = derivadas.estabelecimentos_para_a_base(lido, _descobrir(MEI))
    assert list(tabela["cnpj"]) == [cnpjs.formatar(EMPRESA)]
    assert "razao_social" not in tabela.columns
    assert contagem["repetidas"] == 1
    assert contagem["linhas_na_tabela"] == 1
    assert not tabela["trata_como_pessoa"].any()


def test_acordos_nao_levam_o_contribuinte_e_tiram_pessoa():
    import io

    from base import receita_transacoes as t

    lido = t.ler_individual(io.BytesIO(_individual(EMPRESA, MEI, OUTRA)), DIA)
    tabela, contagem = derivadas.acordos_para_a_base(lido, _descobrir(MEI))
    assert set(tabela["cnpj"]) == {cnpjs.formatar(EMPRESA), cnpjs.formatar(OUTRA)}
    assert "contribuinte" not in tabela.columns
    assert contagem["pessoa_ou_fora_da_receita"] == 1
    assert set(tabela["disponivel_em"]) == {pd.Timestamp(DIA)}


def test_adesoes_so_pessoa_juridica():
    import io

    from base import receita_transacoes as t

    lido = t.ler_adesao(io.BytesIO(_adesao(EMPRESA, MEI)), DIA)
    tabela, _ = derivadas.adesoes_para_a_base(lido, _descobrir(MEI))
    assert list(tabela["cnpj"]) == [cnpjs.formatar(EMPRESA)]
    assert "hash_linha" in tabela.columns


def test_montagem_grava_sem_nome_e_nao_regrava_igual(tmp_path):
    mapa, receita, saida = tmp_path / "s", tmp_path / "r", tmp_path / "base"
    mapa.mkdir()
    receita.mkdir()
    _pasta_do_sigsif(mapa)
    _pasta_das_transacoes(receita)
    descobrir = _descobrir(MEI)

    est = montagem.montar_estabelecimentos(mapa, saida, descobrir, AGORA, "v1")
    aco = montagem.montar_acordos(receita, saida, descobrir, AGORA, "v1")
    ade = montagem.montar_adesoes(receita, saida, descobrir, AGORA, "v1")

    assert est["gravou"] == aco["gravou"] == ade["gravou"] == GRAVADO
    for tabela, esperado in (
        ("sigsif_estabelecimentos", {cnpjs.formatar(EMPRESA)}),
        (
            "receita_transacoes_individual",
            {cnpjs.formatar(EMPRESA), cnpjs.formatar(OUTRA)},
        ),
        ("receita_transacoes_adesao", {cnpjs.formatar(EMPRESA)}),
    ):
        lidas = pd.read_parquet(saida / tabela / f"{tabela}.parquet")
        assert set(lidas["cnpj"]) == esperado
        assert not lidas["trata_como_pessoa"].any()
        proibidas = {"nome", "razao_social", "contribuinte", "nome_fantasia"}
        assert not proibidas & set(lidas.columns)

    de_novo = montagem.montar_acordos(receita, saida, descobrir, AGORA, "v1")
    assert de_novo["gravou"] == IGUAL


def test_main_recusa_arquivo_faltando(tmp_path, monkeypatch):
    monkeypatch.setattr(montagem, "exigir_versao_do_codigo", lambda: "v1")
    assert montagem.main(["--transacoes", str(tmp_path), "--pasta", str(tmp_path)]) == 1
    assert montagem.main(["--sigsif", str(tmp_path), "--pasta", str(tmp_path)]) == 1
