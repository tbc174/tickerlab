"""Cadastro histórico (série 1 da base de ML, PR 8; ADR 0027, exigência 4: sem viés de
sobrevivência): as companhias canceladas continuam na base, com data e motivo, e cada ticker tem
o período em que existiu. Sem internet."""

import io
import zipfile

import pandas as pd

from base.cadastro import (
    canceladas,
    cobertura_das_canceladas,
    ler_cadastro,
    tickers_no_tempo,
)

A = "11.111.111/0001-11"
B = "22.222.222/0001-22"
C = "33.333.333/0001-33"
CADASTRO = (
    "CNPJ_CIA;DENOM_SOCIAL;DT_REG;DT_CANCEL;MOTIVO_CANCEL;SIT;SETOR_ATIV\n"
    f"{A};EMPRESA A;2001-05-10;;;ATIVO;Energia Elétrica\n"
    f"{B};EMPRESA B;1990-01-02;2023-11-30;Cancelamento voluntário;CANCELADA;Têxtil\n"
    f"{C};EMPRESA C;2005-03-01;2019-06-15;Incorporação;CANCELADA;Bancos\n"
).encode("latin-1")


def test_canceladas_com_data_e_motivo():
    cadastro = ler_cadastro(CADASTRO)
    b = cadastro.set_index("cnpj").loc[B]
    assert b["cancelamento"] == pd.Timestamp("2023-11-30")
    assert b["motivo_cancelamento"] == "Cancelamento voluntário"
    assert (b["situacao"], b["setor"]) == ("CANCELADA", "Têxtil")
    saidas = canceladas(cadastro, desde="2020-01-01")
    assert saidas["cnpj"].tolist() == [B]  # a C saiu antes de 2020


def test_cobertura_das_canceladas_mostra_quem_saiu_e_falta_na_base():
    cadastro = ler_cadastro(CADASTRO)
    cobertura = cobertura_das_canceladas({A, C}, cadastro, desde="2015-01-01")
    assert cobertura["na_base"].to_dict() == {B: False, C: True}
    assert cobertura.attrs["proporcao_na_base"] == 0.5


FCA_CABECALHO = (
    "CNPJ_Companhia;Data_Referencia;Versao;ID_Documento;Nome_Empresarial;Valor_Mobiliario;"
    "Sigla_Classe_Acao_Preferencial;Classe_Acao_Preferencial;Codigo_Negociacao;"
    "Composicao_BDR_Unit;Mercado;Sigla_Entidade_Administradora;Entidade_Administradora;"
    "Data_Inicio_Negociacao;Data_Fim_Negociacao;Segmento;Data_Inicio_Listagem;Data_Fim_Listagem"
)


def _fca(ano, *linhas):
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        texto = "\n".join([FCA_CABECALHO, *linhas])
        z.writestr(
            f"fca_cia_aberta_valor_mobiliario_{ano}.csv", texto.encode("latin-1")
        )
    return saida.getvalue()


def _linha(
    cnpj, data, codigo, nome="EMPRESA", inicio="", fim="", mercado="Bolsa", versao=1
):
    return (
        f"{cnpj};{data};{versao};1;{nome};Ações Ordinárias;;;{codigo};;{mercado};B3;B3 S.A.;"
        f"{inicio};{fim};Novo Mercado;;"
    )


def test_tickers_com_inicio_e_fim_e_historico_inteiro():
    arquivos = [
        _fca(2020, _linha(B, "2020-01-01", "BBBB3", inicio="2010-02-01"),
             _linha(A, "2020-01-01", "AAAA3", inicio="2015-03-02")),
        _fca(2022, _linha(B, "2022-01-01", "BBBB3", inicio="2010-02-01", fim="2023-11-30"),
             _linha(A, "2022-01-01", "AAAA3", nome="EMPRESA A NOVA", inicio="2015-03-02"),
             _linha(A, "2022-01-01", "ABCD3", inicio="2022-05-02")),
        _fca(2024, _linha(A, "2024-01-01", "ABCD3", inicio="2022-05-02"),
             _linha(A, "2024-01-01", "XXXX11", mercado="Balcão")),
    ]  # fmt: skip
    tickers = tickers_no_tempo(arquivos).set_index("codigo")
    assert sorted(tickers.index) == ["AAAA3", "ABCD3", "BBBB3"]  # balcão fica fora
    assert tickers.loc["BBBB3", "fim_negociacao"] == pd.Timestamp("2023-11-30")
    assert tickers.loc["BBBB3", "ultimo_visto"] == pd.Timestamp("2022-01-01")
    assert tickers.loc["AAAA3", "primeiro_visto"] == pd.Timestamp("2020-01-01")
    assert tickers.loc["AAAA3", "ultimo_visto"] == pd.Timestamp(
        "2022-01-01"
    )  # trocou de código
    assert tickers.loc["AAAA3", "empresa"] == "EMPRESA A NOVA"  # o nome mais recente
    assert pd.isna(tickers.loc["ABCD3", "fim_negociacao"])


def test_ticker_com_numero_no_emissor_entra_no_tempo():
    """Série 3, PR 5: B3SA3 (a própria B3) não casava com "4 letras e 1 ou 2 números" e sumia."""
    import io
    import zipfile

    from base.cadastro import tickers_no_tempo

    csv = (
        "CNPJ_Companhia;Data_Referencia;Versao;ID_Documento;Nome_Empresarial;Valor_Mobiliario;"
        "Sigla_Classe_Acao_Preferencial;Classe_Acao_Preferencial;Codigo_Negociacao;"
        "Composicao_BDR_Unit;Mercado;Sigla_Entidade_Administradora;Entidade_Administradora;"
        "Data_Inicio_Negociacao;Data_Fim_Negociacao;Segmento;Data_Inicio_Listagem;Data_Fim_Listagem\n"
        "09.346.601/0001-25;2019-01-01;1;1;B3 S.A.;Ações Ordinárias;;;B3SA3;;Bolsa;B3;B3;"
        "2007-10-26;;Novo Mercado;2007-10-26;\n"
    )
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        arquivo.writestr(
            "fca_cia_aberta_valor_mobiliario_2019.csv", csv.encode("latin-1")
        )
    assert list(tickers_no_tempo([conteudo.getvalue()])["codigo"]) == ["B3SA3"]
