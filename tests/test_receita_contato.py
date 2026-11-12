"""Leitor do contato do estabelecimento para a tela da equipe (linha 808).

Riscos que estes testes pegam: sair estabelecimento que não está ativo, nome fantasia ou fax; um CPF passar
escondido no endereço, no telefone ou no e-mail. Todo endereço, telefone e e-mail aqui é inventado.
"""

import io
import zipfile
from collections import Counter

import pandas as pd
import pytest

from base import receita_contato as rc
from base.receita_retrato import ErroDeLayout

CPF_VALIDO = (
    "52998224725"  # número de exemplo que fecha nos dígitos; não é de ninguém conhecido
)


def _linha(raiz="11222333", ordem="0001", dv="81", **campos) -> str:
    """Uma linha do `Estabelecimentos*.zip` (30 campos), com um contato de mentira por padrão."""
    valores = {
        3: "1", 4: "FANTASIA DE MENTIRA", 5: "02", 13: "RUA", 14: "DOS EXEMPLOS", 15: "100",
        16: "SALA 2", 17: "CENTRO", 18: "01001000", 19: "SP", 20: "7107", 21: "11",
        22: "30001000", 23: "11", 24: "990001000", 25: "11", 26: "30002000",
        27: "CONTATO@EXEMPLO.COM.BR",
    }  # fmt: skip
    nomes = {nome: posicao for posicao, nome in rc.ESTABELECIMENTO.items()}
    nomes |= {"fantasia": 4, "ddd_fax": 25, "fax": 26}
    for nome, valor in campos.items():
        valores[nomes[nome]] = valor
    valores |= {0: raiz, 1: ordem, 2: dv}
    return ";".join(f'"{valores.get(i, "")}"' for i in range(30)) + "\n"


def _zip(*linhas: str) -> io.BytesIO:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as arquivo:
        arquivo.writestr("K.ESTABELE", "".join(linhas).encode("latin-1"))
    memoria.seek(0)
    return memoria


def _ler(*linhas: str) -> tuple[pd.DataFrame, Counter]:
    partes = list(rc.ler_contato(_zip(*linhas), set()))
    tabela = pd.concat([p.estabelecimentos for p in partes], ignore_index=True)
    return tabela, sum((p.descartes for p in partes), Counter())


def test_ativo_sai_com_endereco_telefones_e_email_e_nada_mais():
    tabela, descartes = _ler(_linha())
    assert list(tabela.columns) == list(rc.COLUNAS)
    assert tabela.iloc[0].to_dict() == {
        "cnpj_basico": "11222333",
        "cnpj": "11222333000181",
        "matriz": True,
        "tipo_logradouro": "RUA",
        "logradouro": "DOS EXEMPLOS",
        "numero": "100",
        "complemento": "SALA 2",
        "bairro": "CENTRO",
        "cep": "01001000",
        "municipio": "7107",
        "uf": "SP",
        "telefone_1": "1130001000",
        "telefone_2": "11990001000",
        "email": "contato@exemplo.com.br",
    }
    assert not descartes
    texto = tabela.to_csv()
    assert "FANTASIA" not in texto and "30002000" not in texto  # nem fantasia nem fax


@pytest.mark.parametrize("situacao", ["01", "03", "04", "08", ""])
def test_so_o_estabelecimento_ativo_sai(situacao):
    tabela, descartes = _ler(_linha(situacao_cadastral=situacao), _linha(ordem="0002"))
    assert list(tabela["cnpj"]) == ["11222333000281"]
    assert descartes == {rc.NAO_ATIVO: 1}


def test_filial_nao_e_matriz():
    tabela, _ = _ler(_linha(ordem="0002", matriz="2"))
    assert not tabela.loc[0, "matriz"]


@pytest.mark.parametrize(
    ("ddd", "numero", "esperado"),
    [
        ("11", "30001000", "1130001000"),
        ("011", "990001000", "11990001000"),
        ("11", "3000-1000", "1130001000"),
        ("", "30001000", None),  # sem DDD
        ("11", "3000", None),  # curto
        ("", CPF_VALIDO, None),  # um CPF digitado no campo do telefone
        ("11", CPF_VALIDO, None),
        ("", "", None),
    ],
)
def test_telefone_so_no_formato(ddd, numero, esperado):
    tabela, descartes = _ler(_linha(ddd_1=ddd, telefone_1=numero))
    achado = tabela.loc[0, "telefone_1"]
    assert (achado == esperado) if esperado else pd.isna(achado)
    fora = 0 if esperado or not numero else 1
    assert descartes[rc.TELEFONE_FORA_DO_FORMATO] == fora
    assert CPF_VALIDO not in tabela.to_csv()


@pytest.mark.parametrize(
    ("email", "motivo"),
    [
        (f"{CPF_VALIDO}@exemplo.com", rc.EMAIL_COM_CARA_DE_CPF),
        ("529.982.247-25@exemplo.com", rc.EMAIL_COM_CARA_DE_CPF),
        (f"fulano{CPF_VALIDO}x@exemplo.com", rc.EMAIL_COM_CARA_DE_CPF),
        ("11990001000@exemplo.com", rc.EMAIL_COM_CARA_DE_CPF),  # na dúvida, sai
        ("sem arroba", rc.EMAIL_FORA_DO_FORMATO),
        ("dois@@exemplo.com", rc.EMAIL_FORA_DO_FORMATO),
        ("a@" + "b" * 120 + ".com", rc.EMAIL_FORA_DO_FORMATO),
    ],
)
def test_email_fora_do_formato_ou_com_cara_de_cpf_fica_vazio(email, motivo):
    tabela, descartes = _ler(_linha(email=email))
    assert pd.isna(tabela.loc[0, "email"])
    assert descartes == {motivo: 1}
    assert len(tabela) == 1  # o estabelecimento fica, sem o e-mail


def test_email_nao_informado_nao_conta_como_descarte():
    tabela, descartes = _ler(_linha(email=""))
    assert pd.isna(tabela.loc[0, "email"]) and not descartes


@pytest.mark.parametrize("campo", ["logradouro", "numero", "complemento", "bairro"])
@pytest.mark.parametrize("cpf", [CPF_VALIDO, "529.982.247-25", "***.982.247-**"])
def test_cpf_escrito_no_endereco_sai(campo, cpf):
    tabela, _ = _ler(_linha(**{campo: f"CASA {cpf} FUNDOS"}))
    assert tabela.loc[0, campo] == "CASA FUNDOS"


def test_campo_vazio_vem_ausente_e_cep_torto_tambem():
    tabela, _ = _ler(
        _linha(complemento="  ", cep="123", uf="", telefone_2="", ddd_2="")
    )
    linha = tabela.iloc[0]
    assert all(pd.isna(linha[c]) for c in ("complemento", "cep", "uf", "telefone_2"))


def test_cnpj_com_letras_sai_em_maiusculas():
    tabela, _ = _ler(_linha(raiz="1a2b3c4d", ordem="000a"))
    assert tabela.loc[0, "cnpj"] == "1A2B3C4D000A81"
    assert tabela.loc[0, "cnpj_basico"] == "1A2B3C4D"


def test_layout_com_campo_a_mais_quebra_a_leitura():
    with pytest.raises(ErroDeLayout):
        list(rc.ler_contato(_zip(_linha().rstrip("\n") + ';"X"\n'), set()))


@pytest.mark.parametrize(
    "texto",
    [
        "CPF 529982247-25", "CPF:529982247-25", "CPF 529 982 247 25", "CPF-52998224725",
        "CPF/52998224725", "N.52998224725", "CASA,52998224725", "529.982.247/25",
    ],
)  # fmt: skip
def test_cpf_em_formatos_variados_no_complemento_sai(texto):
    tabela, _ = _ler(_linha(complemento=texto))
    achado = (
        "" if pd.isna(tabela.loc[0, "complemento"]) else tabela.loc[0, "complemento"]
    )
    assert sum(c.isdigit() for c in achado) < 11


def test_cpf_no_numero_sai():
    tabela, _ = _ler(_linha(numero="529982247-25"))
    assert pd.isna(tabela.loc[0, "numero"])


@pytest.mark.parametrize(
    "email",
    [
        "529_982_247_25@exemplo.com", "529/982/247/25@exemplo.com",
        "contato@52998224725.com.br", "contato@529.982.247-25.com",
    ],
)  # fmt: skip
def test_cpf_em_formatos_variados_no_email_deixa_o_email_vazio(email):
    tabela, _ = _ler(_linha(email=email))
    assert pd.isna(tabela.loc[0, "email"])


def test_numero_de_rua_e_cep_comuns_nao_sao_confundidos_com_cpf():
    tabela, _ = _ler(_linha(numero="1234", complemento="BLOCO 2 APTO 301"))
    assert tabela.loc[0, "numero"] == "1234"
    assert tabela.loc[0, "complemento"] == "BLOCO 2 APTO 301"


# ---------------------------------------- individual e MEI: só município e UF no endereço (linha 859)


def _raizes(*raizes: str) -> rc.RaizesDeIndividual:
    conjunto = rc.RaizesDeIndividual()
    conjunto.juntar(pd.Series(list(raizes)))
    return conjunto


def test_individual_sai_so_com_municipio_uf_telefone_e_email():
    partes = list(rc.ler_contato(_zip(_linha()), set(), _raizes("11222333")))
    tabela = pd.concat([p.estabelecimentos for p in partes], ignore_index=True)
    linha = tabela.iloc[0]
    for coluna in (*rc.ENDERECO, "cep"):
        assert pd.isna(linha[coluna]), coluna
    assert (linha["municipio"], linha["uf"]) == ("7107", "SP")
    assert linha["telefone_1"] == "1130001000" and linha["email"]
    assert sum((p.descartes for p in partes), Counter())[rc.ENDERECO_CORTADO] == 1


def test_empresa_que_nao_e_individual_segue_com_o_endereco_inteiro():
    linhas = _zip(_linha(), _linha("22333444"))
    partes = list(rc.ler_contato(linhas, set(), _raizes("22333444")))
    tabela = pd.concat([p.estabelecimentos for p in partes], ignore_index=True)
    inteira = tabela[tabela["cnpj_basico"] == "11222333"].iloc[0]
    assert inteira["logradouro"] == "DOS EXEMPLOS" and inteira["cep"] == "01001000"
    cortada = tabela[tabela["cnpj_basico"] == "22333444"].iloc[0]
    assert pd.isna(cortada["logradouro"]) and pd.isna(cortada["cep"])


def test_sem_raizes_de_individual_o_conjunto_vazio_nao_corta_nada():
    partes = list(rc.ler_contato(_zip(_linha()), set(), rc.RaizesDeIndividual()))
    assert partes[0].estabelecimentos.iloc[0]["logradouro"] == "DOS EXEMPLOS"
