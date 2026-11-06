"""Rótulos de recuperação judicial, falência e liquidação (série B2), "como era na data"."""

import io
import zipfile

import pandas as pd

from base import historico, rotulos

CABECALHO = (
    "CNPJ_Companhia;Nome_Companhia;Codigo_CVM;Data_Referencia;Categoria;Tipo;Especie;Assunto;"
    "Data_Entrega;Tipo_Apresentacao;Protocolo_Entrega;Versao;Link_Download"
)


def _linha(cnpj, categoria, tipo, assunto, entrega, protocolo, versao="1", nome=None):
    nome = nome or f"EMPRESA {cnpj[:2]}"
    return (
        f"{cnpj};{nome};1;{entrega};{categoria};{tipo};;{assunto};{entrega};AP;"
        f"{protocolo};{versao};https://www.rad.cvm.gov.br/x?n={protocolo}"
    )


def _zip(*linhas: str, ano: int = 2019) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        texto = "\n".join([CABECALHO, *linhas])
        z.writestr(f"ipe_cia_aberta_{ano}.csv", texto.encode("latin-1"))
    return saida.getvalue()


RJ = "Informações de Companhias em Recuperação Judicial ou Extrajudicial"
FR = "Fato Relevante"


def test_categorias_proprias_da_cvm_viram_rotulos():
    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            _linha(
                "11.111.111/0001-11",
                RJ,
                "Petição Inicial",
                "Pedido de recuperação judicial",
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


def test_cada_versao_da_entrega_fica_com_a_propria_data():
    """Achado 3e do Codex (17/10/2026): a reapresentação não apaga a data da 1ª versão."""
    versao_1 = _linha(
        "11.111.111/0001-11", RJ, "Sentenças", "", "2019-03-01", "300", "1"
    )
    versao_2 = _linha(
        "11.111.111/0001-11", RJ, "Sentenças", "", "2019-03-05", "300", "2"
    )
    tabela = rotulos.ler_insolvencia_do_ipe(_zip(versao_1, versao_2))
    assert sorted(int(v) for v in tabela["versao"]) == [1, 2]
    primeiros = rotulos.primeira_ocorrencia(tabela)
    assert str(primeiros["conhecido_em"].iloc[0]) == "2019-03-01"
    # cortar o futuro não muda o passado: em 03/03 só a versão 1 existia, e ela já estava lá
    so_a_1 = rotulos.ler_insolvencia_do_ipe(_zip(versao_1))
    ate_03_03 = tabela[tabela["conhecido_em"] <= pd.Timestamp("2019-03-03").date()]
    pd.testing.assert_frame_equal(ate_03_03.reset_index(drop=True), so_a_1)


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


def test_arquivos_antigos_sem_protocolo_usam_o_link_do_documento():
    # o IPE de 2003 a 2014 vem com Protocolo_Entrega vazio em todas as linhas
    def sem_protocolo(cnpj, entrega, numero):
        return (
            f"{cnpj};EMPRESA;1;{entrega};{RJ};Petição Inicial;;;{entrega};AP;;1;"
            f"https://www.rad.cvm.gov.br/x?n={numero}"
        )

    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            sem_protocolo("11.111.111/0001-11", "2010-03-01", "900"),
            sem_protocolo("22.222.222/0001-22", "2010-04-01", "901"),
        )
    )
    assert len(tabela) == 2
    assert set(tabela["protocolo"]) == {
        "https://www.rad.cvm.gov.br/x?n=900",
        "https://www.rad.cvm.gov.br/x?n=901",
    }


# --- de quem é a recuperação (relatório 4 dos cruzamentos v2, 16/10/2026) ------------------------
# Os casos do relatório, com CNPJs de mentira e o assunto como a companhia escreveu.


def _rotulo_e_evento(tabela):
    return {
        assunto: (rotulo, evento)
        for assunto, rotulo, evento in zip(
            tabela["assunto"], tabela["rotulo"], tabela["evento"], strict=True
        )
    }


def test_fato_sobre_a_recuperacao_de_outra_empresa_vira_exposicao_a_terceiro():
    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            # Vale, 09/04/2021: a RJ é da Samarco (investida), não da Vale
            _linha(
                "11.111.111/0001-11",
                FR,
                "",
                "Samarco ajuíza pedido de recuperação judicial",
                "2021-04-09",
                "600",
                nome="VALE S.A.",
            ),
            # V.tal, 06/03/2023: a RJ é da Oi (acionista)
            _linha(
                "22.222.222/0001-22",
                FR,
                "",
                "Pedido de recuperação judicial pela Oi S.A. - Em Recuperação Judicial",
                "2023-03-06",
                "601",
                nome="V. TAL - REDE NEUTRA DE TELECOMUNICAÇÕES S.A.",
            ),
            # Energisa, 02/09/2016: a RJ é da controlada
            _linha(
                "33.333.333/0001-33",
                FR,
                "",
                "Encerramento da Recuperação Judicial da controlada Rede Energia e outras",
                "2016-09-02",
                "602",
                nome="ENERGISA SA",
            ),
            # Embraer, 29/02/2016: a RJ é de um cliente (assunto todo em maiúsculas)
            _linha(
                "44.444.444/0001-44",
                FR,
                "",
                "NOTA DA EMBRAER EM RELAÇÃO AO PEDIDO DE RECUPERAÇÃO JUDICIAL DA REPUBLIC AIRWAYS",
                "2016-02-29",
                "603",
                nome="EMBRAER S.A.",
            ),
        )
    )
    assert set(tabela["rotulo"]) == {"exposicao_a_terceiro"}
    assert set(tabela["evento"]) == {"recuperacao_judicial"}
    primeiras = rotulos.primeira_ocorrencia(tabela)
    assert "recuperacao_judicial" not in set(primeiras["rotulo"])


def test_recuperacao_extrajudicial_de_outra_empresa_tambem_e_de_terceiro():
    # Cosan, 11/03/2026: a recuperação extrajudicial é da Raízen
    assunto = "Pedido de recuperação extrajudicial da Raízen"
    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            _linha(
                "11.111.111/0001-11",
                FR,
                "",
                assunto,
                "2026-03-11",
                "610",
                nome="COSAN S.A.",
            )
        )
    )
    assert _rotulo_e_evento(tabela) == {
        assunto: ("exposicao_a_terceiro", "recuperacao_extrajudicial")
    }


def test_extrajudicial_nunca_vira_judicial_mesmo_pela_categoria_da_cvm():
    # Casas Bahia, 2024: a categoria da CVM é "Recuperação Judicial ou Extrajudicial" e o tipo
    # "Sentenças" não diz qual; o assunto diz. O documento sem pista herda o processo aberto.
    def casas_bahia(tipo, assunto, entrega, protocolo):
        return _linha(
            "11.111.111/0001-11",
            RJ,
            tipo,
            assunto,
            entrega,
            protocolo,
            nome="GRUPO CASAS BAHIA S.A.",
        )

    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            casas_bahia(
                "Plano de Recuperação",
                "Plano de Recuperação Extrajudicial",
                "2024-04-29",
                "620",
            ),
            casas_bahia(
                "Sentenças",
                "Setença Plano de Recuperação Extrajudicial",
                "2024-06-21",
                "621",
            ),
            casas_bahia("Outros documentos", "Material blowout", "2024-07-01", "622"),
            casas_bahia("Petição Inicial", "Petição Inicial - RE", "2024-07-02", "623"),
        )
    )
    assert set(tabela["rotulo"]) == {"recuperacao_extrajudicial"}


def test_recuperacao_judicial_depois_da_extrajudicial_e_judicial():
    # Casas Bahia, 16/08/2026: depois da RE de 2024, o pedido de RJ
    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            _linha(
                "11.111.111/0001-11",
                RJ,
                "Plano de Recuperação",
                "Plano de Recuperação Extrajudicial",
                "2024-04-29",
                "630",
                nome="GRUPO CASAS BAHIA S.A.",
            ),
            _linha(
                "11.111.111/0001-11",
                FR,
                "",
                "Pedido de Recuperação Judicial",
                "2026-08-16",
                "631",
                nome="GRUPO CASAS BAHIA S.A.",
            ),
            _linha(
                "11.111.111/0001-11",
                RJ,
                "Petição Inicial",
                "Petição inicial",
                "2026-08-18",
                "632",
                nome="GRUPO CASAS BAHIA S.A.",
            ),
        )
    )
    assert list(tabela["rotulo"]) == [
        "recuperacao_extrajudicial",
        "recuperacao_judicial",
        "recuperacao_judicial",
    ]


def test_recuperacao_da_propria_companhia_continua_recuperacao_judicial():
    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            # Americanas, 19/01/2023: o fato relevante é o primeiro sinal público
            _linha(
                "11.111.111/0001-11",
                FR,
                "",
                "Ajuizamento de Recuperação Judicial",
                "2023-01-19",
                "640",
                nome="AMERICANAS S.A.",
            ),
            _linha(
                "11.111.111/0001-11",
                RJ,
                "Outros documentos",
                "Lista atualizada de credores RJ",
                "2023-02-10",
                "641",
                nome="AMERICANAS S.A.",
            ),
            # Oi, 20/06/2016: o fato relevante do dia, a petição e as contas mensais, sem texto
            _linha(
                "22.222.222/0001-22",
                FR,
                "",
                "Pedido de Recuperação Judicial",
                "2016-06-20",
                "6420",
                nome="OI S.A.",
            ),
            _linha(
                "22.222.222/0001-22",
                RJ,
                "Petição Inicial",
                "Petição Inicial",
                "2016-06-20",
                "642",
                nome="OI S.A.",
            ),
            _linha(
                "22.222.222/0001-22",
                RJ,
                "Contas demonstrativas mensais",
                "",
                "2016-07-31",
                "643",
                nome="OI S.A.",
            ),
            # Brasil Biofuels, 31/07/2025: a companhia e as subsidiárias juntas
            _linha(
                "33.333.333/0001-33",
                FR,
                "",
                "Pedido de Recuperação Judicial da Companhia e de certas Subsidiárias",
                "2025-07-31",
                "644",
                nome="BRASIL BIOFUELS S.A.",
            ),
        )
    )
    assert set(tabela["rotulo"]) == {"recuperacao_judicial"}
    assert set(tabela["evento"]) == {"recuperacao_judicial"}


def test_securitizadora_falando_da_devedora_e_exposicao_a_terceiro():
    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            _linha(
                "11.111.111/0001-11",
                FR,
                "",
                "Alteração nos Direitos e Vantagens dos Valores Mobiliários||CRI 6aS 5aE||"
                "Plano de Recuperação Judicial da Devedora (Urbplan)",
                "2019-05-28",
                "650",
                nome="PLANETA SECURITIZADORA S.A.",
            ),
            # Habitasec, 28/06/2016: sem pista no texto; a securitizadora fala do devedor
            _linha(
                "22.222.222/0001-22",
                FR,
                "",
                "Recuperação Judicial",
                "2016-06-28",
                "651",
                nome="HABITASEC SECURITIZADORA SA",
            ),
        )
    )
    assert set(tabela["rotulo"]) == {"exposicao_a_terceiro"}


def test_documento_sem_pista_e_sem_processo_anterior_nao_escolhe_o_tipo():
    # Hopi Hari, 26/08/2016: "Ofício 2945/2016" na categoria da CVM; até ali nada dizia se era
    # judicial ou extrajudicial (o plano de RJ só apareceu em 09/02/2017)
    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            _linha(
                "11.111.111/0001-11",
                RJ,
                "Petição Inicial",
                "Ofício 2945/2016",
                "2016-08-26",
                "660",
                nome="HOPI HARI SA",
            ),
            _linha(
                "11.111.111/0001-11",
                FR,
                "",
                "Apresentação do Plano de Recuperação Judicial",
                "2017-02-09",
                "661",
                nome="HOPI HARI SA",
            ),
        )
    )
    assert list(tabela["rotulo"]) == [
        "recuperacao_judicial_ou_extrajudicial",
        "recuperacao_judicial",
    ]


def test_cada_linha_diz_a_regra_que_decidiu_o_rotulo():
    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            _linha(
                "11.111.111/0001-11",
                FR,
                "",
                "Samarco ajuíza pedido de recuperação judicial",
                "2021-04-09",
                "670",
                nome="VALE S.A.",
            ),
            _linha(
                "22.222.222/0001-22",
                FR,
                "",
                "Recuperação judicial da controladora Galvão",
                "2015-03-26",
                "671",
                nome="IGUA SANEAMENTO S.A.",
            ),
            _linha(
                "33.333.333/0001-33",
                RJ,
                "Petição Inicial",
                "Petição Inicial",
                "2016-06-20",
                "672",
                nome="OI S.A.",
            ),
        )
    )
    regras = dict(zip(tabela["cnpj"], tabela["regra"], strict=True))
    assert regras == {
        "11.111.111/0001-11": "outra_empresa (samarco)",
        "22.222.222/0001-22": "texto_de_terceiro",
        "33.333.333/0001-33": "categoria_ipe",
    }


def test_cortar_o_futuro_nao_muda_o_rotulo_do_passado():
    cbd = "COMPANHIA BRASILEIRA DE DISTRIBUIÇÃO"
    linhas = [
        _linha(
            "11.111.111/0001-11",
            RJ,
            "Petição Inicial",
            "Petição inicial - Recuperação Extrajudicial",
            "2026-03-10",
            "680",
            nome=cbd,
        ),
        _linha(
            "11.111.111/0001-11",
            RJ,
            "Outros documentos",
            "Anexos",
            "2026-03-20",
            "681",
            nome=cbd,
        ),
        _linha(
            "11.111.111/0001-11",
            FR,
            "",
            "Pedido de Recuperação Judicial",
            "2026-08-16",
            "682",
            nome=cbd,
        ),
        _linha(
            "11.111.111/0001-11",
            RJ,
            "Outros documentos",
            "Anexos",
            "2026-08-20",
            "683",
            nome=cbd,
        ),
        _linha(
            "22.222.222/0001-22",
            FR,
            "",
            "Recuperação Judicial da Samarco",
            "2026-03-11",
            "684",
            nome="EMPRESA PARTICIPACOES S.A.",
        ),
        _linha(
            "22.222.222/0001-22",
            RJ,
            "Petição Inicial",
            "Petição Inicial",
            "2026-05-01",
            "685",
            nome="EMPRESA PARTICIPACOES S.A.",
        ),
    ]
    completa = rotulos.ler_insolvencia_do_ipe(_zip(*linhas))
    for corte in ("2026-03-10", "2026-03-20", "2026-05-01", "2026-08-16"):
        cortada = rotulos.ler_insolvencia_do_ipe(
            _zip(*(x for x in linhas if x.split(";")[8] <= corte))
        )
        antes = completa[completa["conhecido_em"].astype(str) <= corte]
        assert list(cortada["rotulo"]) == list(antes["rotulo"]), corte
        assert list(cortada["regra"]) == list(antes["regra"]), corte


def test_o_contexto_atravessa_os_arquivos_anuais():
    # Atma: a RE começa no arquivo de 2019 e o documento sem pista está no de 2020
    def do_ano(ano, assunto, tipo, entrega, protocolo):
        linha = _linha(
            "11.111.111/0001-11",
            RJ,
            tipo,
            assunto,
            entrega,
            protocolo,
            nome="ATMA PARTICIPAÇÕES S.A.",
        )
        return rotulos.ler_insolvencia_do_ipe(_zip(linha, ano=ano)).assign(
            ano_do_arquivo=ano
        )

    juntos = rotulos.rotular_com_contexto(
        pd.concat(
            [
                do_ano(
                    2019,
                    "Pedido de Homologação de Plano de Recuperação Extrajudicial",
                    "Petição Inicial",
                    "2019-12-30",
                    "690",
                ),
                do_ano(2020, "Efeito Suspensivo", "Sentenças", "2020-08-16", "691"),
            ],
            ignore_index=True,
        )
    )
    assert list(juntos["rotulo"]) == ["recuperacao_extrajudicial"] * 2
    assert list(juntos["ano_do_arquivo"]) == [2019, 2020]
    insolvencia = historico.TABELAS["insolvencia"]
    assert insolvencia.com_todos_os_anos is rotulos.rotular_com_contexto


def test_recuperacao_de_terceiro_nao_vira_o_processo_da_companhia():
    # TPI: RE própria em 2017; em 2018 a RJ é da investida Viracopos. O documento seguinte, sem
    # pista, continua no processo da TPI (extrajudicial), não no da investida
    def tpi(categoria, tipo, assunto, entrega, protocolo):
        return _linha(
            "11.111.111/0001-11",
            categoria,
            tipo,
            assunto,
            entrega,
            protocolo,
            nome="TPI - TRIUNFO PARTICIPACOES E INVESTIMENTOS S.A.",
        )

    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            tpi(
                RJ,
                "Plano de Recuperação",
                "Planos de recuperação extrajudicial",
                "2017-07-22",
                "700",
            ),
            tpi(FR, "", "Recuperação Judicial - Viracopos", "2018-05-07", "701"),
            tpi(RJ, "Outros documentos", "", "2018-05-07", "702"),
        )
    )
    assert list(tabela["rotulo"]) == [
        "recuperacao_extrajudicial",
        "exposicao_a_terceiro",
        "recuperacao_extrajudicial",
    ]


def test_pedido_da_propria_companhia_nao_herda_o_terceiro_de_antes():
    # Rede Energia: em maio de 2012 a RJ era da controlada CELPA; em novembro, a própria pediu
    def rede(assunto, entrega, protocolo):
        return _linha(
            "11.111.111/0001-11",
            FR,
            "",
            assunto,
            entrega,
            protocolo,
            nome="REDE ENERGIA PARTICIPAÇÕES S.A.",
        )

    tabela = rotulos.ler_insolvencia_do_ipe(
        _zip(
            rede(
                "Plano de Recuperação Judicial da controlada CELPA", "2012-05-07", "710"
            ),
            rede("Ajuizamento de pedido de Recuperação Judicial", "2012-11-23", "711"),
        )
    )
    assert list(tabela["rotulo"]) == ["exposicao_a_terceiro", "recuperacao_judicial"]
