"""DIRBI, ECF e habilitados do SIGSIF na base: só pessoa jurídica, nenhum nome, sem olhar o futuro (linha 904).

Todos os dados daqui são inventados. A Receita guardada é um dublê (`descobrir`): devolve as raízes de pessoa."""

import io
import json
import zipfile
from datetime import date
from pathlib import Path
from typing import ClassVar

import numpy as np
import pandas as pd
import pytest

from base import cnpj as cnpjs
from base import derivadas_do_lote_3 as derivadas
from base import receita_renuncias as renuncias
from base import sigsif
from base.parquet import GRAVADO, IGUAL
from scripts import carga_receita_renuncias as carga
from scripts import montar_tabelas_lote_3 as montagem


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
OUTRA = _cnpj("33000167")
MEI = _cnpj("44555666")  # raiz que a Receita guardada diz ser de pessoa
INVALIDO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)
DIA = date(2026, 11, 2)


def _formatado(cnpj: str) -> str:
    """A fonte entrega o CNPJ com máscara; o mascarado de verdade (com asteriscos) passa como veio."""
    return cnpjs.formatar(cnpj) if cnpj.isalnum() else cnpj


def _descobrir(*pessoas: str):
    numeros = cnpjs.ordenados(
        cnpjs.raizes_em_numeros(pd.Series([p[:8] for p in pessoas], dtype="string"))
    )
    return lambda _raizes: numeros


def _tudo_pessoa(raizes: np.ndarray) -> np.ndarray:
    return raizes


# --- separar_pessoa_juridica ---


def test_pessoa_sai_da_tabela_inteira_e_a_contagem_diz_quantas():
    tabela = pd.DataFrame(
        {
            "cnpj": [EMPRESA, EMPRESA, MEI, INVALIDO, OUTRA, None],
            "valor": [1, 2, 3, 4, 5, 6],
        }
    )
    pj, contagem = derivadas.separar_pessoa_juridica(tabela, _descobrir(MEI))
    assert sorted(pj["valor"]) == [1, 2, 5]
    assert set(pj["cnpj"]) == {cnpjs.formatar(EMPRESA), cnpjs.formatar(OUTRA)}
    assert set(pj["cnpj_basico"]) == {EMPRESA[:8], OUTRA[:8]}
    assert not pj["trata_como_pessoa"].any()
    assert contagem == {
        "linhas": 6,
        "cnpj_invalido": 2,
        "pessoa_ou_fora_da_receita": 1,
        "linhas_na_tabela": 3,
        "cnpjs_na_tabela": 2,
    }


def test_sem_a_receita_guardada_toda_raiz_conta_como_pessoa_e_a_tabela_fica_vazia():
    tabela = pd.DataFrame({"cnpj": [EMPRESA, OUTRA], "valor": [1, 2]})
    pj, contagem = derivadas.separar_pessoa_juridica(tabela, _tudo_pessoa)
    assert pj.empty
    assert contagem["linhas_na_tabela"] == 0


def test_cnpj_sem_nenhum_valido_nao_chama_a_receita():
    def nunca(_r: np.ndarray) -> np.ndarray:
        raise AssertionError("não devia perguntar")

    pj, contagem = derivadas.separar_pessoa_juridica(
        pd.DataFrame({"cnpj": [INVALIDO, "123"], "valor": [1, 2]}), nunca
    )
    assert pj.empty and contagem["cnpj_invalido"] == 2


# --- DIRBI ---


def _csv_dirbi(*linhas: str) -> list[bytes]:
    cabecalho = "CNPJ;Nome;Municipio;UF;CNAE;Mes;Ano;Codigo;Tributo;Valor"
    return [(x + "\n").encode() for x in (cabecalho, *linhas)]


def _linha_dirbi(cnpj: str, mes: int = 1, valor: str = "10,50") -> str:
    return (
        f'"{_formatado(cnpj)}","EMPRESA DE MENTIRA","SAO PAULO","SP","1234567",'
        f'"{mes}","2026","101","IRPJ","{valor}"'
    )


def test_dirbi_nao_grava_nome_e_so_leva_pessoa_juridica():
    lido = renuncias.ler_dirbi(
        _csv_dirbi(
            _linha_dirbi(EMPRESA), _linha_dirbi(MEI), _linha_dirbi(EMPRESA, mes=2)
        ),
        DIA,
    )
    tabela, contagem = derivadas.dirbi_para_a_base(lido, _descobrir(MEI))
    assert list(tabela.columns) == [
        *derivadas.COLUNAS_DO_DIRBI,
        "trata_como_pessoa",
        "disponivel_em",
    ]
    assert "nome" not in tabela.columns
    assert len(tabela) == 2 and set(tabela["mes"]) == {1, 2}
    assert set(tabela["periodo"]) == {date(2026, 1, 1), date(2026, 2, 1)}
    assert contagem["pessoa_ou_fora_da_receita"] == 1
    assert not tabela.duplicated(list(derivadas.CHAVE_DO_DIRBI)).any()
    assert not any(isinstance(t, pd.CategoricalDtype) for t in tabela.dtypes), (
        "texto comum no Parquet"
    )


def test_dirbi_cnpj_mascarado_e_descartado_na_leitura():
    lido = renuncias.ler_dirbi(
        _csv_dirbi(_linha_dirbi("**.123.456/0001-**"), _linha_dirbi(EMPRESA)), DIA
    )
    assert len(lido) == 1


# --- ECF ---


def _linha_ecf(cnpj: str, exercicio: str = "2024") -> str:
    campos = [
        _formatado(cnpj), "EMPRESA DE MENTIRA SA", "", "01/01/2024", "31/12/2024", "1", "A", "1",
        "0", "1234567", "1",
    ]  # fmt: skip
    campos += ["0,00"] * len(renuncias.COLUNAS_DE_BENEFICIO_DA_ECF) + [exercicio]
    return "|".join(campos)


def _ecf(*linhas: str) -> list[bytes]:
    cabecalho = "|".join(renuncias.COLUNAS_DA_ECF)
    return [(x + "\n").encode() for x in (cabecalho, *linhas)]


def test_ecf_nao_grava_razao_social_e_tira_pessoa():
    lido = renuncias.ler_ecf(_ecf(_linha_ecf(EMPRESA), _linha_ecf(MEI)), DIA)
    tabela, contagem = derivadas.ecf_para_a_base(lido, _descobrir(MEI))
    assert "razao_social" not in tabela.columns
    assert len(tabela) == 1 and tabela["cnpj"].iloc[0] == cnpjs.formatar(EMPRESA)
    assert contagem["pessoa_ou_fora_da_receita"] == 1
    assert tabela["dt_ini"].iloc[0] == date(2024, 1, 1)
    assert not tabela.duplicated(list(derivadas.CHAVE_DA_ECF)).any()


# --- SIGSIF habilitados ---


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


def _habilitados(*sifs: str) -> bytes:
    cabecalho = "PAIS;AREA;ESTABELECIMENTO;SIF;UF;MUNICIPIO;PRODUTO;DT_VALIDADE;DT_OCORRENCIA;DT_SUSPENSAO"
    linhas = [
        f"CHILE;CARNES;ESTAB DE MENTIRA;{sif};GO;CIDADE;CARNE BOVINA;01/01/2027;;"
        for sif in sifs
    ]
    return "\n".join([cabecalho, *linhas]).encode()


def test_habilitados_sem_cnpj_pelo_sif_nao_entra_e_nome_do_estabelecimento_nao_vaza():
    cadastro = sigsif.ler_estabelecimentos(
        _registrados((cnpjs.formatar(EMPRESA), "100"), (cnpjs.formatar(MEI), "200")),
        DIA,
    )
    lido = sigsif.ler_habilitados(_habilitados("100", "200", "999"), cadastro, DIA)
    tabela, contagem = derivadas.habilitados_para_a_base(lido, _descobrir(MEI))
    assert "estabelecimento" not in tabela.columns
    assert list(tabela["sif"]) == ["100"]
    assert contagem["sem_cnpj_pelo_sif"] == 1
    assert contagem["pessoa_ou_fora_da_receita"] == 1
    assert contagem["linhas"] == 3
    assert tabela["dt_validade"].iloc[0] == date(2027, 1, 1)
    assert not tabela.duplicated(list(derivadas.CHAVE_DOS_HABILITADOS)).any()


def test_sif_dividido_entre_dois_cnpjs_fica_sem_cnpj():
    cadastro = sigsif.ler_estabelecimentos(
        _registrados((cnpjs.formatar(EMPRESA), "100"), (cnpjs.formatar(OUTRA), "100")),
        DIA,
    )
    lido = sigsif.ler_habilitados(_habilitados("100"), cadastro, DIA)
    tabela, contagem = derivadas.habilitados_para_a_base(lido, _descobrir())
    assert tabela.empty and contagem["sem_cnpj_pelo_sif"] == 1


# --- linhagem e "sem olhar o futuro" ---


def test_linhagem_carimba_origem_e_disponivel_em_e_nada_antes_do_arquivo():
    tabela = pd.DataFrame({"cnpj": ["x"]})
    agora = pd.Timestamp("2026-11-13T12:00:00Z")
    pronta = derivadas.com_linhagem(
        tabela, DIA, "abc", pd.Timestamp("2026-11-13T10:00:00Z"), agora, "v1"
    )
    assert pronta["disponivel_em"].iloc[0] == DIA
    assert set(derivadas.LINHAGEM) <= set(pronta.columns)
    assert pronta["montado_em"].iloc[0] == agora.isoformat()


# --- montagem de ponta a ponta (arquivos de mentira) ---


def _pasta_da_receita(pasta: Path) -> None:
    for nome in carga.ARQUIVOS_DO_DIRBI:
        with zipfile.ZipFile(pasta / nome, "w") as z:
            z.writestr(
                "dirbi.csv",
                "".join(
                    x.decode()
                    for x in _csv_dirbi(_linha_dirbi(EMPRESA), _linha_dirbi(MEI))
                ),
            )
    (pasta / carga.ARQUIVO_DA_ECF).write_bytes(
        b"".join(_ecf(_linha_ecf(EMPRESA), _linha_ecf(MEI)))
    )
    datas = {
        n: DIA.isoformat() for n in (*carga.ARQUIVOS_DO_DIRBI, carga.ARQUIVO_DA_ECF)
    }
    (pasta / montagem.MODIFICADOS).write_text(json.dumps(datas), encoding="utf-8")


def _pasta_do_sigsif(pasta: Path) -> None:
    (pasta / "registrados.csv").write_bytes(
        _registrados((cnpjs.formatar(EMPRESA), "100"), (cnpjs.formatar(MEI), "200"))
    )
    (pasta / "habilitados.csv").write_bytes(_habilitados("100", "200"))
    datas = {"registrados.csv": DIA.isoformat(), "habilitados.csv": DIA.isoformat()}
    (pasta / montagem.MODIFICADOS).write_text(json.dumps(datas), encoding="utf-8")


def test_montagem_grava_so_pessoa_juridica_sem_nome_e_nao_regrava_igual(tmp_path):
    receita, mapa, saida = tmp_path / "r", tmp_path / "s", tmp_path / "base"
    receita.mkdir()
    mapa.mkdir()
    _pasta_da_receita(receita)
    _pasta_do_sigsif(mapa)
    agora = pd.Timestamp("2026-11-13T12:00:00Z")
    descobrir = _descobrir(MEI)

    dirbi = montagem.montar_dirbi(receita, saida, descobrir, agora, "v1")
    ecf = montagem.montar_ecf(receita, saida, descobrir, agora, "v1")
    hab = montagem.montar_habilitados(mapa, saida, descobrir, agora, "v1")

    assert {d["gravou"] for d in dirbi.values()} == {GRAVADO}
    assert ecf["gravou"] == hab["gravou"] == GRAVADO
    for tabela in ("receita_dirbi", "receita_ecf_renuncia", "sigsif_habilitados"):
        lidas = pd.concat(
            pd.read_parquet(f) for f in (saida / tabela).glob("*.parquet")
        )
        assert set(lidas["cnpj"]) == {cnpjs.formatar(EMPRESA)}
        assert not lidas["trata_como_pessoa"].any()
        proibidas = {"nome", "razao_social", "estabelecimento", "nome_fantasia"}
        assert not proibidas & set(lidas.columns)

    de_novo = montagem.montar_dirbi(receita, saida, descobrir, agora, "v1")
    assert {d["gravou"] for d in de_novo.values()} == {IGUAL}


def test_main_recusa_arquivo_faltando(tmp_path, monkeypatch):
    monkeypatch.setattr(montagem, "exigir_versao_do_codigo", lambda: "v1")
    assert montagem.main(["--receita", str(tmp_path), "--pasta", str(tmp_path)]) == 1


def test_baixar_sigsif_recusa_pasta_com_arquivo(tmp_path):
    (tmp_path / "x").write_text("x")
    with pytest.raises(SystemExit):
        montagem.baixar_sigsif(tmp_path)


def test_baixar_sigsif_grava_os_dois_csv_e_o_last_modified(tmp_path, monkeypatch):
    class Resposta:
        headers: ClassVar[dict[str, str]] = {
            "Last-Modified": "Mon, 02 Nov 2026 06:02:00 GMT"
        }

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, _n):
            return [io.BytesIO(b"a;b\n").read()]

    monkeypatch.setattr(montagem.rede, "get_com_agente", lambda *_a, **_k: Resposta())
    destino = tmp_path / "novo"
    registro = montagem.baixar_sigsif(destino)
    assert registro == {
        "registrados.csv": "2026-11-02",
        "habilitados.csv": "2026-11-02",
    }
    assert (destino / "habilitados.csv").read_bytes() == b"a;b\n"


def test_sem_a_receita_as_tres_tabelas_ficam_vazias_sem_quebrar():
    dirbi, _ = derivadas.dirbi_para_a_base(
        renuncias.ler_dirbi(_csv_dirbi(_linha_dirbi(EMPRESA)), DIA), _tudo_pessoa
    )
    ecf, _ = derivadas.ecf_para_a_base(
        renuncias.ler_ecf(_ecf(_linha_ecf(EMPRESA)), DIA), _tudo_pessoa
    )
    cadastro = sigsif.ler_estabelecimentos(
        _registrados((cnpjs.formatar(EMPRESA), "100")), DIA
    )
    hab, _ = derivadas.habilitados_para_a_base(
        sigsif.ler_habilitados(_habilitados("100"), cadastro, DIA), _tudo_pessoa
    )
    assert dirbi.empty and ecf.empty and hab.empty


def test_habilitado_vale_desde_o_mais_novo_dos_dois_arquivos(tmp_path):
    """O CNPJ vem do cadastro (outro arquivo): a linha não pode valer antes de o cadastro existir assim."""
    pasta = tmp_path / "s"
    pasta.mkdir()
    _pasta_do_sigsif(pasta)
    datas = {"registrados.csv": "2026-11-10", "habilitados.csv": "2026-11-02"}
    (pasta / montagem.MODIFICADOS).write_text(json.dumps(datas), encoding="utf-8")
    saida = tmp_path / "base"
    agora = pd.Timestamp("2026-11-13T12:00:00Z")

    montagem.montar_habilitados(pasta, saida, _descobrir(MEI), agora, "v1")

    lidas = pd.read_parquet(saida / "sigsif_habilitados" / "sigsif_habilitados.parquet")
    assert set(lidas["disponivel_em"]) == {date(2026, 11, 10)}


def test_sif_dividido_entre_cpf_e_cnpj_nao_entra(tmp_path):
    pasta = tmp_path / "s"
    pasta.mkdir()
    (pasta / "registrados.csv").write_bytes(
        _registrados(
            (cnpjs.formatar(EMPRESA), "100"),
            ("123.456.789-09", "100"),
            (cnpjs.formatar(OUTRA), "300"),
        )
    )
    (pasta / "habilitados.csv").write_bytes(_habilitados("100", "300"))
    datas = {"registrados.csv": DIA.isoformat(), "habilitados.csv": DIA.isoformat()}
    (pasta / montagem.MODIFICADOS).write_text(json.dumps(datas), encoding="utf-8")
    saida = tmp_path / "base"

    montagem.montar_habilitados(
        pasta, saida, _descobrir(), pd.Timestamp("2026-11-13T12:00:00Z"), "v1"
    )

    lidas = pd.read_parquet(saida / "sigsif_habilitados" / "sigsif_habilitados.parquet")
    assert set(lidas["cnpj"]) == {cnpjs.formatar(OUTRA)}


def test_vazia_so_quando_montou_e_nao_deixou_linha():
    assert montagem._vazia({"linhas_na_tabela": 0})
    assert not montagem._vazia({"linhas_na_tabela": 3})
    assert not montagem._vazia({"gravou": IGUAL})
