"""Natureza jurídica e opção pelo MEI do CNPJ aberto da Receita (Q1 do plano = sim, 15/10/2026).

Só duas colunas de cada arquivo: (CNPJ básico, natureza) do Empresas e (CNPJ básico, opção pelo MEI)
do Simples. Layout conferido no servidor de casa em 15/10 (cópia de 2026-10): sem cabeçalho, `;`,
aspas, latin-1; a razão social às vezes tem `;` dentro das aspas. Arquivos de mentira.
"""

import io
import zipfile

from base import receita_natureza as rn

EMPRESAS = (
    '"33000167";"PETROLEO DE MENTIRA S.A.";"2046";"10";"1000,00";"05";""\n'
    '"12ABC345";"NOVA; COM PONTO E VIRGULA LTDA";"2062";"49";"0,00";"01";""\n'
    '"11222333";"FULANO DE TAL 52998224725";"2135";"50";"5000,00";"01";""\n'
    '"99999999";"FORA DA REDE SA";"2054";"10";"1,00";"05";""\n'
)
SIMPLES = (
    '"11222333";"S";"20200101";"00000000";"S";"20200101";"00000000"\n'
    '"12ABC345";"S";"20200101";"00000000";"N";"00000000";"00000000"\n'
    '"99999999";"N";"20070701";"20070701";"S";"20090701";"00000000"\n'
)


def _zip(nome: str, texto: str) -> io.BytesIO:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr(nome, texto.encode("latin-1"))
    saida.seek(0)
    return saida


def test_natureza_so_das_raizes_pedidas():
    tabela = rn.ler_naturezas(
        _zip("K3241.K03200Y0.D61010.EMPRECSV", EMPRESAS),
        {"33000167", "12ABC345", "11222333"},
    )
    assert dict(
        zip(tabela["cnpj_basico"], tabela["natureza_juridica"], strict=True)
    ) == {
        "33000167": "2046",
        "12ABC345": "2062",
        "11222333": "2135",
    }


def test_receita_so_duas_colunas():
    """O leitor nunca devolve razão social (nem o CPF que o nome do MEI e do EI carrega)."""
    tabela = rn.ler_naturezas(_zip("EMPRECSV", EMPRESAS), {"11222333", "12ABC345"})
    assert list(tabela.columns) == ["cnpj_basico", "natureza_juridica"]
    texto = tabela.astype(str).to_string()
    assert (
        "FULANO" not in texto and "52998224725" not in texto and "VIRGULA" not in texto
    )
    mei = rn.ler_mei(_zip("SIMPLES.CSV", SIMPLES), {"11222333"})
    assert list(mei.columns) == ["cnpj_basico", "mei"]


def test_mei_e_a_opcao_atual():
    mei = rn.ler_mei(_zip("SIMPLES.CSV", SIMPLES), {"11222333", "12ABC345", "33000167"})
    assert dict(zip(mei["cnpj_basico"], mei["mei"], strict=True)) == {
        "11222333": True,
        "12ABC345": False,
    }  # quem não está no Simples não aparece (não é MEI)


def test_arquivos_em_partes(monkeypatch):
    """Os arquivos têm ~2 GB: a leitura vai por partes, sem perder linha entre elas."""
    monkeypatch.setattr(rn, "TAMANHO_DA_PARTE", 1)
    tabela = rn.ler_naturezas(_zip("EMPRECSV", EMPRESAS), {"33000167", "99999999"})
    assert sorted(tabela["cnpj_basico"]) == ["33000167", "99999999"]
