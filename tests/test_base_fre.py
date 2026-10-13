"""Leitor do FRE da CVM (série 2 da base de ML, PR 6): proventos por exercício e eventos de capital
(desdobramentos, grupamentos, aumentos, reduções) das tabelas do formato antigo (até 2022; desde a
Resolução CVM 59 o FRE aberto não traz mais essas tabelas). Só essas tabelas são lidas: o FRE também
tem nomes de administradores, que não entram. CSVs pequenos com os cabeçalhos reais."""

import io
import zipfile

import pandas as pd
import pytest

from base.fre import ler_eventos_de_capital, ler_proventos

DIV = (
    "CNPJ_Companhia;Data_Referencia;Versao;ID_Documento;Nome_Companhia;Data_Inicio_Exercicio_Social;"
    "Data_Fim_Exercicio_Social;Lucro_Liquido_Ajustado;Taxa_Retorno_Patrimonio_Liquido_Emissor;"
    "Lucro_Liquido_Retido;Dividendo_Distribuido_Lucro_Liquido_Ajustado;Dividendo_Distribuido_Total;"
    "Data_Aprovacao_Retencao"
)
DIV_CLASSE = (
    "CNPJ_Companhia;Data_Referencia;Versao;ID_Documento;Nome_Companhia;Data_Inicio_Exercicio_Social;"
    "Data_Fim_Exercicio_Social;Especie_Acao;Classe_Acao;Dividendo_Distribuido;Montante;"
    "Data_Pagamento_Dividendo"
)
DESDOBRAMENTO = (
    "CNPJ_Companhia;Data_Referencia;Versao;ID_Documento;Nome_Companhia;"
    "ID_Capital_Social_Desdobramento;Data_Aprovacao;Tipo_Evento;"
    "Quantidade_Acoes_Ordinarias_Antes_Aprovacao;Quantidade_Acoes_Preferenciais_Antes_Aprovacao;"
    "Quantidade_Total_Acoes_Antes_Aprovacao;Quantidade_Acoes_Ordinarias_Depois_Aprovacao;"
    "Quantidade_Acoes_Preferenciais_Depois_Aprovacao;Quantidade_Total_Acoes_Depois_Aprovacao"
)
AUMENTO = (
    "CNPJ_Companhia;Data_Referencia;Versao;ID_Documento;Nome_Companhia;ID_Capital_Social_Aumento;"
    "Data_Deliberacao;Orgao_Deliberacao_Aumento;Data_Emissao;Valor_Total_Emissao;Tipo_Subscricao;"
    "Quantidade_Acoes_Ordinarias;Quantidade_Acoes_Preferenciais;Quantidade_Total_Acoes;"
    "Subscricao_Capital_Anterior;Fator_Cotacao;Preco_Emissao;Criterio_Determinacao_Preco_Emissao;"
    "Forma_Integralizacao"
)
ADMINISTRADOR = "CNPJ_Companhia;Data_Referencia;Versao;Nome;CPF"
A = "11.111.111/0001-11"


def _zip(arquivos: dict[str, list[str]], ano: int = 2022) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        for nome, linhas in arquivos.items():
            z.writestr(
                f"fre_cia_aberta_{nome}_{ano}.csv", "\n".join(linhas).encode("latin-1")
            )
    return saida.getvalue()


def _fre(versao_nova: str = "3") -> bytes:
    return _zip(
        {
            "distribuicao_dividendos": [
                DIV,
                f"{A};2022-01-01;2;9;EMPRESA A;2021-01-01;2021-12-31;1000.00;10.0;600.00;40.00;400.00;",
                f"{A};2022-01-01;{versao_nova};9;EMPRESA A;2021-01-01;2021-12-31;1000.00;10.0;500.00;50.00;500.00;",
            ],
            "distribuicao_dividendos_classe_acao": [
                DIV_CLASSE,
                f"{A};2022-01-01;{versao_nova};9;EMPRESA A;2021-01-01;2021-12-31;Ordinária;;Dividendo Obrigatório;300.00;2022-05-02",
                f"{A};2022-01-01;{versao_nova};9;EMPRESA A;2021-01-01;2021-12-31;Ordinária;;Juros Sobre Capital Próprio;200.00;2021-12-20",
            ],
            "capital_social_desdobramento": [
                DESDOBRAMENTO,
                f"{A};2022-01-01;{versao_nova};9;EMPRESA A;1;2020-08-03;Desdobramento;100;0;100;1000;0;1000",
            ],
            "capital_social_aumento": [
                AUMENTO,
                f"{A};2022-01-01;{versao_nova};9;EMPRESA A;2;2021-03-10;AGE;2021-04-01;5000.00;Pública;50;0;50;0.05;R$ por Unidade;100.00;Mercado;Dinheiro",
            ],
            "administrador_membro_conselho_fiscal": [
                ADMINISTRADOR,
                f"{A};2022-01-01;3;Fulana;123",
            ],
        }
    )


def test_proventos_por_exercicio_na_versao_mais_nova():
    proventos = ler_proventos(_fre())
    assert len(proventos) == 1
    linha = proventos.iloc[0]
    assert (linha["cnpj"], linha["exercicio"]) == (A, pd.Timestamp("2021-12-31"))
    assert linha["versao"] == 3
    assert linha["dividendo_total"] == pytest.approx(500.0)
    assert linha["payout"] == pytest.approx(0.50)  # a CVM informa em %
    assert linha["dividendos"] == pytest.approx(300.0)
    assert linha["jcp"] == pytest.approx(200.0)


def test_eventos_de_capital_desdobramento_e_aumento():
    eventos = ler_eventos_de_capital(_fre()).set_index("tipo")
    desdobramento = eventos.loc["desdobramento"]
    assert desdobramento["data"] == pd.Timestamp("2020-08-03")
    assert desdobramento["fator"] == pytest.approx(10.0)  # 100 ações viraram 1000
    aumento = eventos.loc["aumento"]
    assert aumento["acoes_novas"] == 50 and aumento["valor"] == pytest.approx(5000.0)


def test_fre_do_formato_novo_nao_tem_essas_tabelas_e_nao_quebra():
    novo = _zip({"capital_social": ["CNPJ_Companhia;Data_Referencia"]}, ano=2026)
    assert ler_proventos(novo).empty and ler_eventos_de_capital(novo).empty


def test_nao_le_dados_pessoais():
    """O FRE tem nomes de administradores: nenhuma coluna lida pode trazer isso."""
    for tabela in (ler_proventos(_fre()), ler_eventos_de_capital(_fre())):
        assert not {"Nome", "CPF", "nome", "cpf"} & set(tabela.columns)
