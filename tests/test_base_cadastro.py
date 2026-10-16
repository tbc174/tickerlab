"""Cadastro histórico (série 1 da base de ML, PR 8; ADR 0027, exigência 4: sem viés de
sobrevivência): as companhias canceladas continuam na base, com data e motivo, e cada ticker tem
o período em que existiu. Sem internet."""

import io
import zipfile

import pandas as pd

from base.cadastro import (
    FonteETabela,
    canceladas,
    cobertura_das_canceladas,
    conferir_canceladas,
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
PRINCIPAL_CABECALHO = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC"
)


def _documento(cnpj, data, versao):
    """O número do documento na CVM: um por companhia, referência e versão."""
    return f"{cnpj[:2]}{data[:4]}{versao}"


def _fca(ano, *linhas, recebido=None, vazios=()):
    """Um zip do FCA com o arquivo de valores mobiliários e o principal.

    `recebido`: data de entrega de cada documento (padrão: 31/05 do ano). `vazios`: documentos
    (cnpj, data, versão) que estão no arquivo principal sem nenhuma linha de valores mobiliários.
    """
    recebido = recebido or f"{ano}-05-31"
    documentos = {tuple(linha.split(";")[:3]) for linha in linhas} | set(vazios)
    principal = [
        f"{cnpj};{data};{versao};EMPRESA;1;FCA;{_documento(cnpj, data, versao)};{recebido};"
        for cnpj, data, versao in sorted(documentos)
    ]
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            f"fca_cia_aberta_valor_mobiliario_{ano}.csv",
            "\n".join([FCA_CABECALHO, *linhas]).encode("latin-1"),
        )
        z.writestr(
            f"fca_cia_aberta_{ano}.csv",
            "\n".join([PRINCIPAL_CABECALHO, *principal]).encode("latin-1"),
        )
    return saida.getvalue()


def _linha(
    cnpj, data, codigo, nome="EMPRESA", inicio="", fim="", mercado="Bolsa", versao=1
):
    return (
        f"{cnpj};{data};{versao};{_documento(cnpj, data, versao)};{nome};Ações Ordinárias;;;"
        f"{codigo};;{mercado};B3;B3 S.A.;{inicio};{fim};Novo Mercado;;"
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
    # as datas são as entregas dos formulários, não as datas de referência
    assert tickers.loc["BBBB3", "ultimo_visto"] == pd.Timestamp("2022-05-31")
    assert pd.isna(tickers.loc["BBBB3", "valido_ate"])  # no último FCA que a B entregou
    assert tickers.loc["AAAA3", "primeiro_visto"] == pd.Timestamp("2020-05-31")
    assert tickers.loc["AAAA3", "ultimo_visto"] == pd.Timestamp("2022-05-31")
    # trocou de código: deixa de valer na entrega do FCA que veio sem ele
    assert tickers.loc["AAAA3", "valido_ate"] == pd.Timestamp("2024-05-31")
    assert tickers.loc["AAAA3", "empresa"] == "EMPRESA A NOVA"  # o nome mais recente
    assert pd.isna(tickers.loc["ABCD3", "fim_negociacao"])


def test_reentrega_de_formulario_antigo_nao_volta_o_ticker():
    """Vale o FCA de referência mais nova entre os já entregues: a 2ª versão do FCA de 2021, entregue
    depois do de 2022 (acontece: 46 vezes de 2010 a 2026), não traz o código antigo de volta."""
    arquivos = [
        _fca(2021, _linha(A, "2021-01-01", "AAAA3", versao=2), recebido="2022-08-01"),
        _fca(2022, _linha(A, "2022-01-01", "ABCD3"), recebido="2022-05-31"),
    ]
    tickers = tickers_no_tempo(arquivos).set_index("codigo")
    assert list(tickers.index) == ["ABCD3"]
    assert pd.isna(tickers.loc["ABCD3", "valido_ate"])


def test_formulario_sem_valores_mobiliarios_nao_encerra_o_ticker():
    """264 FCA de empresas com ação na bolsa (CCR, BRF, Cielo em 2011) vêm sem nenhuma linha de valores
    mobiliários e depois voltam a ter: o vazio é falta de dado, não saída da bolsa."""
    arquivos = [
        _fca(2020, _linha(A, "2020-01-01", "AAAA3")),
        _fca(2021, vazios=[(A, "2021-01-01", "1")]),
        _fca(2022, _linha(A, "2022-01-01", "AAAA3")),
    ]
    tickers = tickers_no_tempo(arquivos)
    assert len(tickers) == 1
    assert tickers["primeiro_visto"].iloc[0] == pd.Timestamp("2020-05-31")
    assert pd.isna(tickers["valido_ate"].iloc[0])


def test_codigo_que_some_e_volta_tem_dois_periodos():
    arquivos = [
        _fca(2020, _linha(A, "2020-01-01", "AAAA3")),
        _fca(2021, _linha(A, "2021-01-01", "ABCD3")),
        _fca(2022, _linha(A, "2022-01-01", "AAAA3")),
    ]
    aaaa3 = tickers_no_tempo(arquivos).query("codigo == 'AAAA3'")
    assert aaaa3["primeiro_visto"].tolist() == [
        pd.Timestamp("2020-05-31"),
        pd.Timestamp("2022-05-31"),
    ]
    assert aaaa3["valido_ate"].iloc[0] == pd.Timestamp("2021-05-31")


def test_ticker_com_numero_no_emissor_entra_no_tempo():
    """Série 3, PR 5: B3SA3 (a própria B3) não casava com "4 letras e 1 ou 2 números" e sumia."""
    b3 = "09.346.601/0001-25"
    conteudo = _fca(
        2019, _linha(b3, "2019-01-01", "B3SA3", nome="B3 S.A.", inicio="2007-10-26")
    )
    assert list(tickers_no_tempo([conteudo])["codigo"]) == ["B3SA3"]


def test_cadastro_traz_a_uf_da_sede():
    com_uf = (
        "CNPJ_CIA;DENOM_SOCIAL;DT_REG;DT_CANCEL;MOTIVO_CANCEL;SIT;SETOR_ATIV;UF\n"
        f"{A};EMPRESA A;2001-05-10;;;ATIVO;Energia Elétrica; rs \n"
    ).encode("latin-1")
    assert ler_cadastro(com_uf)["uf"].tolist() == ["RS"]
    assert ler_cadastro(CADASTRO)["uf"].tolist() == ["", "", ""]  # arquivo sem a coluna


# --- conferência medida das canceladas (ADR 0027, exigência 4; critério de pronto do modelo 8) ---
D = "44.444.444/0001-44"
E = "55.555.555/0001-55"
CANCELADAS = (
    "CNPJ_CIA;DENOM_SOCIAL;DT_REG;DT_CANCEL;MOTIVO_CANCEL;SIT;SETOR_ATIV\n"
    f"{A};EMPRESA A;2001-05-10;;;ATIVO;Energia Elétrica\n"
    f"{B};EMPRESA B;1990-01-02;2023-11-30;Cancelamento voluntário;CANCELADA;Têxtil\n"
    f"{C};EMPRESA C;2005-03-01;2010-06-15;Incorporação;CANCELADA;Bancos\n"
    f"{D};EMPRESA D;1977-07-20;2014-01-09;Cancelamento de ofício;CANCELADA;Têxtil\n"
    f"{E};EMPRESA E;1998-02-20;2015-12-08;Cancelamento voluntário;CANCELADA;Bancos\n"
).encode("latin-1")


def test_conferencia_separa_falta_da_fonte_de_empresa_perdida_na_montagem():
    cadastro = ler_cadastro(CANCELADAS)
    tabelas = {
        "demonstracoes": FonteETabela(
            na_fonte={A, B, E}, na_tabela={A, B}, comeca_em="2011-03-31"
        )
    }
    conferencia = conferir_canceladas(cadastro, tabelas, desde="2010-01-01")
    situacao = conferencia.set_index("cnpj")["situacao"].to_dict()
    assert situacao == {
        B: "na_tabela",
        C: "saiu_antes_da_tabela",  # cancelada antes do primeiro prazo que a fonte cobre
        D: "sem_documento_na_fonte",  # a CVM não publica nada dela: limite da fonte
        E: "perdida_na_montagem",  # a fonte tem, a base não: é erro
    }
    assert conferencia.attrs["perdidas"] == 1
    assert set(conferencia["motivo_cancelamento"]) >= {"Cancelamento de ofício"}


def test_falta_explicada_a_mao_deixa_de_ser_perdida():
    cadastro = ler_cadastro(CANCELADAS)
    tabelas = {
        "eventos": FonteETabela(na_fonte={E}, na_tabela=set(), comeca_em="2003-01-01")
    }
    explicadas = {("eventos", E): "só documentos que o leitor do IPE não classifica"}
    conferencia = conferir_canceladas(
        cadastro, tabelas, desde="2010-01-01", explicadas=explicadas
    )
    linha = conferencia.set_index("cnpj").loc[E]
    assert (linha["situacao"], linha["explicacao"]) == (
        "explicada_a_mao",
        "só documentos que o leitor do IPE não classifica",
    )
    assert conferencia.attrs["perdidas"] == 0


def test_empresa_com_um_registro_ainda_ativo_nao_e_cancelada():
    cadastro = ler_cadastro(
        CANCELADAS + f"{B};EMPRESA B;2024-05-01;;;ATIVO;Têxtil\n".encode("latin-1")
    )
    tabelas = {
        "x": FonteETabela(na_fonte=set(), na_tabela=set(), comeca_em="2003-01-01")
    }
    conferencia = conferir_canceladas(cadastro, tabelas, desde="2010-01-01")
    assert B not in set(conferencia["cnpj"])
