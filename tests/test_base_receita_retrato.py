"""Leitor do retrato mensal do CNPJ aberto (plano da base de CNPJ, PR 3; ADR 0106).

Layout (conferido em 15 e 17/10/2026): sem cabeçalho, `;`, aspas, latin-1. Estabelecimentos tem 30
campos, Simples 7, Sócios 11. O nome e o CPF mascarado do sócio saem num quadro à parte
(`pessoas_brutas`); faixa etária, representante, telefone, fax e e-mail nunca saem do leitor.
Arquivos de mentira.
"""

import io
import zipfile

import pandas as pd
import pytest

from base import cnpj
from base import receita_retrato as rr


def _zip(texto: str) -> io.BytesIO:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr("K3241.K03200Y0.D61010.ESTABELE", texto.encode("latin-1"))
    saida.seek(0)
    return saida


def _estab(
    basico="33000167", ordem="0001", matriz="1", situacao="02", inicio="19980101",
    cnae="1921700", logradouro="AVENIDA REPUBLICA DO CHILE", cep="20031170",
    municipio="6001", telefone="21", especial="", fantasia="PETROBRAS",
):  # fmt: skip
    dv = cnpj.digitos_verificadores(basico + ordem)
    campos = [
        basico, ordem, dv, matriz, fantasia, situacao, "20050101", "00", "", "",
        inicio, cnae, "1921701,1921702", "AVENIDA", logradouro, "65", "ANDAR 3",
        "CENTRO", cep, "RJ", municipio, telefone, "32241000", "", "", "", "",
        "contato@exemplo.com.br", especial, "00000000",
    ]  # fmt: skip
    return ";".join(f'"{c}"' for c in campos) + "\n"


def _simples(basico, opcao="S", d_opcao="20200101", d_excl="00000000", mei="N"):
    return (
        ";".join(f'"{c}"' for c in (basico, opcao, d_opcao, d_excl, mei, "0", "0"))
        + "\n"
    )


def _socio(basico, tipo, nome, doc, qualif="49", entrada="20190301", pais="", rep="***000000**",
           nome_rep="REPRESENTANTE", qual_rep="00", faixa="4"):  # fmt: skip
    campos = [
        basico,
        tipo,
        nome,
        doc,
        qualif,
        entrada,
        pais,
        rep,
        nome_rep,
        qual_rep,
        faixa,
    ]
    return ";".join(f'"{c}"' for c in campos) + "\n"


def _lido(gerador):
    return pd.concat(list(gerador), ignore_index=True)


def test_retrato_so_com_as_colunas_permitidas():
    tabela = _lido(rr.ler_estabelecimentos(_zip(_estab())))
    proibidas = {
        "nome_fantasia",
        "ddd1",
        "telefone1",
        "ddd2",
        "telefone2",
        "fax",
        "email",
    }
    assert not proibidas & set(tabela.columns)
    texto = tabela.to_csv()
    for sobra in ("PETROBRAS", "32241000", "contato@exemplo"):
        assert sobra not in texto
    linha = tabela.iloc[0]
    assert linha["cnpj"] == "33000167" + "0001" + cnpj.digitos_verificadores(
        "330001670001"
    )
    assert linha["logradouro"] == "AVENIDA REPUBLICA DO CHILE"
    assert linha["cep"] == "20031170"
    assert linha["uf"] == "RJ"
    assert linha["matriz"]


def test_cnpj_com_letras():
    linha = _lido(
        rr.ler_estabelecimentos(_zip(_estab(basico="12ABC345", ordem="01DE")))
    ).iloc[0]
    assert linha["cnpj"].startswith("12ABC34501DE")
    assert cnpj.tem_letra(linha["cnpj"])
    assert linha["dv_confere"]


def test_dv_errado_vira_alerta_e_nao_descarte():
    errada = _estab().replace(
        f'"{cnpj.digitos_verificadores("330001670001")}"', '"99"', 1
    )
    tabela = _lido(rr.ler_estabelecimentos(_zip(errada + _estab(basico="11222333"))))
    assert list(tabela["dv_confere"]) == [False, True]


def test_datas_vazias_viram_nat():
    texto = _estab(inicio="0") + _estab(basico="11222333", inicio="00000000")
    texto += _estab(basico="22333444", inicio="")
    tabela = _lido(rr.ler_estabelecimentos(_zip(texto)))
    assert tabela["data_inicio_atividade"].isna().all()
    assert pd.api.types.is_datetime64_any_dtype(tabela["data_inicio_atividade"])
    assert tabela["data_situacao_cadastral"].notna().all()


def test_mei_e_ei_so_com_municipio_e_uf():
    texto = _estab() + _estab(basico="11222333")
    tabela = _lido(rr.ler_estabelecimentos(_zip(texto), so_municipio={"11222333"}))
    pj, pessoa = tabela.iloc[0], tabela.iloc[1]
    assert pj["logradouro"] == "AVENIDA REPUBLICA DO CHILE"
    for coluna in (
        "tipo_logradouro",
        "logradouro",
        "numero",
        "complemento",
        "bairro",
        "cep",
    ):
        assert pessoa[coluna] == ""
    assert (pessoa["uf"], pessoa["municipio"]) == ("RJ", "6001")


def test_linha_com_campos_a_mais_quebra_com_aviso():
    longa = ";".join(['"1"'] * 31) + "\n"
    with pytest.raises(rr.ErroDeLayout):
        _lido(rr.ler_estabelecimentos(_zip(longa + _estab())))


def test_simples_traz_opcoes_e_datas():
    texto = _simples("11222333", mei="S") + _simples(
        "33000167", opcao="N", d_excl="20211231"
    )
    tabela = _lido(rr.ler_simples(_zip(texto)))
    assert list(tabela.columns) == [
        "cnpj_basico", "optante_simples", "data_opcao_simples", "data_exclusao_simples",
        "optante_mei", "data_opcao_mei", "data_exclusao_mei",
    ]  # fmt: skip
    assert list(tabela["optante_mei"]) == [True, False]
    assert tabela["data_exclusao_simples"].tolist()[0] is pd.NaT
    assert tabela["data_exclusao_simples"].iloc[1] == pd.Timestamp("2021-12-31")


def test_qsa_le_o_que_a_receita_publica():
    texto = (
        _socio(
            "33000167",
            "1",
            "HOLDING DE MENTIRA SA",
            "11222333",
            qualif="22",
            entrada="20100101",
        )
        + _socio("33000167", "2", "MARIA DA SILVA", "***123456**", qualif="49")
        + _socio("33000167", "3", "JOHN SMITH", "00000000000", qualif="37", pais="249")
    )
    partes = list(rr.ler_qsa([_zip(texto)]))
    socios = pd.concat([p.socios for p in partes], ignore_index=True)
    brutas = pd.concat([p.pessoas_brutas for p in partes], ignore_index=True)
    assert list(socios["tipo_socio"]) == ["1", "2", "3"]
    assert list(socios["raiz_socio_pj"].fillna("-")) == ["11222333", "-", "-"]
    assert list(socios["qualificacao"]) == ["22", "49", "37"]
    assert socios["data_entrada"].iloc[0] == pd.Timestamp("2010-01-01")
    assert socios["pais"].iloc[2] == "249"
    assert set(socios.columns).isdisjoint({"nome_socio", "cpf_mascarado"})
    assert list(brutas["nome_socio"]) == ["MARIA DA SILVA", "JOHN SMITH"]
    assert brutas["cpf_mascarado"].iloc[0] == "***123456**"


def test_qsa_nunca_le_faixa_nem_representante():
    texto = _socio("33000167", "2", "MARIA DA SILVA", "***123456**", rep="***999999**",
                   nome_rep="NOME DO REPRESENTANTE", faixa="9")  # fmt: skip
    (parte,) = list(rr.ler_qsa([_zip(texto)]))
    tudo = parte.socios.to_csv() + parte.pessoas_brutas.to_csv()
    assert "NOME DO REPRESENTANTE" not in tudo
    assert "999999" not in tudo
    colunas = set(parte.socios.columns) | set(parte.pessoas_brutas.columns)
    assert not {"faixa_etaria", "representante_legal", "nome_representante"} & colunas


def test_qsa_recusa_cpf_inteiro():
    texto = _socio("33000167", "2", "MARIA DA SILVA", "52998224725")
    with pytest.raises(rr.ErroDeCpfInteiro):
        list(rr.ler_qsa([_zip(texto)]))


def test_socio_pj_normalizado_para_a_raiz():
    # desde 08/2026 a Receita traz os 8 caracteres da raiz; os meses antigos, os 14
    texto = _socio("33000167", "1", "A", "11222333000181") + _socio(
        "33000167", "1", "B", "11222333"
    )
    (parte,) = list(rr.ler_qsa([_zip(texto)]))
    assert list(parte.socios["raiz_socio_pj"]) == ["11222333", "11222333"]


def test_datas_do_qsa_vazias_viram_nat():
    texto = _socio("33000167", "1", "A", "11222333", entrada="0") + _socio(
        "33000167", "1", "B", "11222333", entrada="00000000"
    )
    (parte,) = list(rr.ler_qsa([_zip(texto)]))
    assert parte.socios["data_entrada"].isna().all()
