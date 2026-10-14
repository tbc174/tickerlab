"""Rótulos de recuperação judicial, falência e liquidação (série B2), "como era na data"."""

import io
import zipfile

from base import historico, rotulos

CABECALHO = (
    "CNPJ_Companhia;Nome_Companhia;Codigo_CVM;Data_Referencia;Categoria;Tipo;Especie;Assunto;"
    "Data_Entrega;Tipo_Apresentacao;Protocolo_Entrega;Versao;Link_Download"
)


def _linha(cnpj, categoria, tipo, assunto, entrega, protocolo, versao="1"):
    return (
        f"{cnpj};EMPRESA {cnpj[:2]};1;{entrega};{categoria};{tipo};;{assunto};{entrega};AP;"
        f"{protocolo};{versao};https://www.rad.cvm.gov.br/x?n={protocolo}"
    )


def _zip(*linhas: str) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        texto = "\n".join([CABECALHO, *linhas])
        z.writestr("ipe_cia_aberta_2019.csv", texto.encode("latin-1"))
    return saida.getvalue()


RJ = "Informações de Companhias em Recuperação Judicial ou Extrajudicial"


def test_categorias_proprias_da_cvm_viram_rotulos():
    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            _linha(
                "11.111.111/0001-11",
                RJ,
                "Petição Inicial",
                "Pedido",
                "2019-03-01",
                "100",
            ),
            _linha(
                "22.222.222/0001-22",
                RJ,
                "Pedido de homologação de Plano de Recuperação Extrajudicial",
                "",
                "2019-04-01",
                "101",
            ),
            _linha(
                "33.333.333/0001-33",
                "Informações Companhias em Falência",
                "Contas demonstrativas da administração",
                "",
                "2019-05-01",
                "102",
            ),
            _linha(
                "44.444.444/0001-44", "Pedidos de falência", "", "", "2019-06-01", "103"
            ),
            _linha(
                "55.555.555/0001-55",
                "Informações Companhias em Liquidação",
                "Nomeação de Liquidante",
                "",
                "2019-07-01",
                "104",
            ),
            _linha(
                "66.666.666/0001-66",
                "Fato Relevante",
                "",
                "Aquisição de controle",
                "2019-08-01",
                "105",
            ),
        )
    )
    por_cnpj = dict(zip(tabela["cnpj"], tabela["rotulo"], strict=True))
    assert por_cnpj == {
        "11.111.111/0001-11": "recuperacao_judicial",
        "22.222.222/0001-22": "recuperacao_extrajudicial",
        "33.333.333/0001-33": "falencia",
        "44.444.444/0001-44": "pedido_de_falencia",
        "55.555.555/0001-55": "liquidacao",
    }
    assert set(tabela["evidencia"]) == {"categoria_ipe"}
    assert (
        str(tabela.loc[tabela["cnpj"] == "11.111.111/0001-11", "conhecido_em"].iloc[0])
        == "2019-03-01"
    )


def test_fato_relevante_que_anuncia_o_pedido_tambem_conta_como_evidencia():
    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            _linha(
                "11.111.111/0001-11",
                "Fato Relevante",
                "",
                "Ajuizamento de Pedido de Recuperação Judicial",
                "2019-02-10",
                "200",
            ),
            _linha(
                "22.222.222/0001-22",
                "Comunicado ao Mercado",
                "",
                "Esclarecimento sobre recuperação extrajudicial",
                "2019-02-11",
                "201",
            ),
            _linha(
                "33.333.333/0001-33",
                "Fato Relevante",
                "",
                "Liquidação financeira de debêntures",
                "2019-02-12",
                "202",
            ),
        )
    )
    assert list(tabela["rotulo"]) == [
        "recuperacao_judicial",
        "recuperacao_extrajudicial",
    ]
    assert set(tabela["evidencia"]) == {"fato_relevante"}


def test_versoes_repetidas_ficam_so_com_a_mais_nova():
    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            _linha("11.111.111/0001-11", RJ, "Sentenças", "", "2019-03-01", "300", "1"),
            _linha("11.111.111/0001-11", RJ, "Sentenças", "", "2019-03-05", "300", "2"),
        )
    )
    assert len(tabela) == 1
    assert int(tabela["versao"].iloc[0]) == 2


def test_primeira_data_por_empresa_e_rotulo():
    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            _linha(
                "11.111.111/0001-11",
                RJ,
                "Contas demonstrativas mensais",
                "",
                "2019-05-01",
                "400",
            ),
            _linha(
                "11.111.111/0001-11",
                "Fato Relevante",
                "",
                "Pedido de recuperação judicial",
                "2019-02-10",
                "401",
            ),
        )
    )
    primeiros = rotulos.primeira_ocorrencia(tabela)
    assert len(primeiros) == 1
    assert str(primeiros["conhecido_em"].iloc[0]) == "2019-02-10"
    assert primeiros["evidencia"].iloc[0] == "fato_relevante"


def test_rotulos_entram_na_base_historica():
    assert historico.TABELAS["insolvencia"].fonte == "cvm-hist-ipe"


def test_nome_de_tribunal_ou_lei_nao_vira_falencia():
    # Oi, 22/06/2016: "Deferimento pelo Tribunal de Falências" era a recuperação judicial
    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            _linha(
                "11.111.111/0001-11",
                "Fato Relevante",
                "",
                "Deferimento pelo Tribunal de Falências no Distrito",
                "2016-06-22",
                "500",
            ),
            _linha(
                "22.222.222/0001-22",
                "Fato Relevante",
                "",
                "Lei de Falências: alteração",
                "2016-06-23",
                "501",
            ),
            _linha(
                "33.333.333/0001-33",
                "Fato Relevante",
                "",
                "Decretação de falência da Companhia",
                "2016-06-24",
                "502",
            ),
            _linha(
                "44.444.444/0001-44",
                "Fato Relevante",
                "",
                "Esclarecimentos sobre requerimento de falência",
                "2016-06-25",
                "503",
            ),
        )
    )
    assert dict(zip(tabela["cnpj"], tabela["rotulo"], strict=True)) == {
        "33.333.333/0001-33": "falencia",
        "44.444.444/0001-44": "pedido_de_falencia",
    }
