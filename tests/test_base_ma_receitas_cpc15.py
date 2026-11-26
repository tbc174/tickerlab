"""A receita das empresas compradas, tirada da nota de combinação de negócios (CPC 15) das DFPs
(`base/ma_receitas_cpc15.py`, linha 1129). Empresas inventadas, no formato das notas reais. Sem internet."""

import zipfile
from datetime import date

import pandas as pd
import pytest

from base import ma_receitas_cpc15 as cpc15
from base import ma_regua
from base.parquet import ler_tabela
from scripts import carga_ma_assessorias as carga
from scripts import montar_recorte_da_api as envio

DEZ_2023 = date(2023, 12, 31)
COMPRADORA = "11.111.111/0001-11"
CABECALHO = (
    "Compradora Exemplo S.A.\r\nNotas explicativas às demonstrações financeiras\r\n"
    "Exercícios findos em 31 de dezembro de 2023\r\n"
    "Em milhares de reais, exceto quando indicado de outra forma\r\n"
)


def _pagina(corpo: str, impressa: int) -> str:
    return (
        f"{CABECALHO}{corpo}\r\nNotas Explicativas\r\nPÁGINA: {impressa} de 145\r\n"
        "DFP - Demonstrações Financeiras Padronizadas - 31/12/2023 - COMPRADORA EXEMPLO S.A. Versão : 1"
    )


def _paginas(*corpos: str) -> list[tuple[int, str]]:
    return [(40 + i, _pagina(c, 38 + i)) for i, c in enumerate(corpos)]


AQUISICAO_ALFA = (
    "1.2.2 Aquisição Alfa Distribuidora de Peças Ltda. (“Alfa Tratores”)\r\n"
    "Em 8 de agosto de 2023, a Companhia realizou o fechamento da aquisição da Alfa Distribuidora de "
    "Peças Ltda. (“Alfa Tratores”), através de sua controlada Vetor Máquinas S.A. (“Vetor”), após a "
    "aprovação do CADE. Do preço de aquisição de R$96.986, R$30.896 foram pagos à vista."
)
RESULTADO_ALFA = (
    "Resultado da combinação de negócios\r\nEsta combinação de negócios contribuiu para o resultado do "
    "exercício findo em 31 de dezembro de 2023 da Companhia com R$ 57.164 de receita líquida e R$ 1.254 "
    "de prejuízo líquido, a partir de 8 de agosto de 2023, data em que a Companhia assumiu o controle. Se "
    "a aquisição da empresa tivesse ocorrido em 1 de\r\njaneiro de 2023, a receita líquida consolidada da "
    "Companhia para o exercício seria aumentada em R$ \r\n64.456 e o lucro líquido consolidado aumentado "
    "em R$ 7.087 (valores não auditados)."
)


def _unica(paginas, referencia=DEZ_2023):
    leituras, recusadas = cpc15.ler_notas(paginas, referencia)
    assert len(leituras) == 1, recusadas
    return leituras[0]


# --- as três formas da nota -------------------------------------------------------------------------
def test_forma_do_aumento_soma_o_que_entrou_desde_a_compra():
    lida = _unica(_paginas(AQUISICAO_ALFA, RESULTADO_ALFA))
    assert lida.nome == "Alfa Distribuidora de Peças Ltda."
    assert lida.forma == cpc15.AUMENTO
    assert lida.valor_pro_forma == 64_456_000
    assert lida.valor_desde_a_compra == 57_164_000
    assert cpc15.receita_do_ano(lida) == 121_620_000
    assert (lida.pagina, lida.pagina_impressa, lida.pagina_da_secao) == (41, 39, 40)
    assert lida.exercicio_fim == DEZ_2023
    assert "57.164" in lida.trecho and "64.456" in lida.trecho
    assert (
        "preço de aquisição" not in lida.trecho
    )  # o trecho é só o que prova a receita


def test_forma_so_da_adquirida_com_o_valor_depois():
    corpo = (
        "Beta Telecomunicações Ltda. (“BETA”)\r\nA partir de 1º de outubro de 2023, a controlada adquiriu "
        "57,38% das quotas do capital social da empresa Beta Telecomunicações Ltda. O valor total pago foi "
        "de R$ 210.548. Se esta aquisição tivesse ocorrido em 1 de janeiro de 2023, representaria uma "
        "receita líquida de R$241.958 e um resultado líquido de R$44.753 no exercício findo em 31 de "
        "dezembro de 2023. No exercício findo em 31 de dezembro de 2023, a empresa Beta contribuiu para os "
        "números consolidados em R$ 57.924 de receita líquida e R$15.771 de lucro."
    )
    lida = _unica(_paginas(corpo))
    assert lida.forma == cpc15.SO_DA_ADQUIRIDA
    assert cpc15.receita_do_ano(lida) == 241_958_000
    assert lida.valor_desde_a_compra == 57_924_000


def test_forma_so_da_adquirida_com_bruta_e_liquida_pega_a_liquida():
    corpo = (
        "2.1.1. Aquisição da empresa Gama S.A. (“Gama”)\r\nEm termos de resultado, a Gama contribuiu com R$ 855 "
        "de receita bruta e R$ 799 de receita líquida no ano de 2023 desde a sua aquisição em outubro. Se a "
        "aquisição tivesse ocorrido em 01 de janeiro de 2023, a Gama teria contribuído com R$ 3.282 de "
        "receita bruta, R$ 3.066 de receita líquida e R$ (3.213) de prejuízo líquido."
    )
    lida = _unica(_paginas(corpo))
    assert cpc15.receita_do_ano(lida) == 3_066_000
    assert lida.valor_desde_a_compra == 799_000


def test_forma_do_consolidado_inteiro_pede_a_dre_da_compradora():
    corpo = (
        "Aquisição Delta Veículos Ltda. (“Delta”)\r\nA Delta contribuiu para o resultado com R$ 10.000 de "
        "receita líquida desde a aquisição. Se a aquisição tivesse ocorrido em 1 de janeiro de 2023, a "
        "receita líquida consolidada da Companhia seria de R$ 530.000."
    )
    lida = _unica(_paginas(corpo))
    assert lida.forma == cpc15.CONSOLIDADO
    assert cpc15.receita_do_ano(lida) is None  # sem a DRE, não se chuta
    assert cpc15.receita_do_ano(lida, dre_consolidada=500_000_000) == 40_000_000


def test_linha_que_comeca_por_exercicio_findo_nao_e_cabecalho():
    # a quebra de linha do PDF deixa "exercício findo em ..." no começo de uma linha sem R$ (caso real)
    quebrado = RESULTADO_ALFA.replace(
        "resultado do exercício", "resultado do\r\nexercício"
    ).replace("da Companhia com R$", "da Companhia com\r\nR$")
    lida = _unica(_paginas(AQUISICAO_ALFA, quebrado))
    assert cpc15.receita_do_ano(lida) == 121_620_000


# --- o que fica vazio ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "frase, motivo",
    [
        (
            (
                "Se a aquisição das três empresas tivesse ocorrido em 1 de janeiro de 2023, a receita e o lucro "
                "líquido consolidado seriam de R$1.366.453 e R$9.991, respectivamente."
            ),
            cpc15.VARIAS_ALVOS,
        ),
        (
            (
                "Se a aquisição tivesse ocorrido em 1 de janeiro de 2023, a receita bruta da adquirida teria sido "
                "de R$ 9.000."
            ),
            cpc15.SEM_VALOR,
        ),
        (
            (
                "Se a aquisição tivesse ocorrido em 1 de janeiro de 2023, representaria uma receita líquida de "
                "R$ 12.000 ou uma receita líquida ajustada de R$ 15.000."
            ),
            cpc15.LEITURAS_DIVERGEM,
        ),
        (
            (
                "Se a aquisição tivesse ocorrido em 1 de janeiro de 2021, representaria uma receita líquida de "
                "R$ 12.000."
            ),
            cpc15.OUTRO_ANO,
        ),
        (
            (
                "Se a aquisição tivesse ocorrido em 1 de janeiro de 2023, a receita líquida consolidada seria "
                "aumentada em R$ 5.000."
            ),
            cpc15.SEM_O_DESDE_A_COMPRA,
        ),
    ],
)
def test_sem_prova_o_valor_fica_vazio(frase, motivo):
    paginas = _paginas(f"Aquisição Alfa Distribuidora de Peças Ltda.\r\n{frase}")
    leituras, recusadas = cpc15.ler_notas(paginas, DEZ_2023)
    assert leituras == []
    assert motivo in recusadas


def test_sem_a_unidade_o_valor_fica_vazio():
    texto = (
        "Aquisição Alfa Distribuidora de Peças Ltda.\r\nSe a aquisição tivesse ocorrido em 1 de janeiro de "
        "2023, representaria uma receita líquida de R$ 12.000."
    )
    leituras, recusadas = cpc15.ler_notas([(1, texto)], DEZ_2023)
    assert leituras == []
    assert cpc15.SEM_UNIDADE in recusadas


def test_unidade_escrita_no_numero_vale_sem_cabecalho():
    texto = (
        "Aquisição Alfa Distribuidora de Peças Ltda.\r\nSe a aquisição tivesse ocorrido em 1 de janeiro de "
        "2023, representaria uma receita líquida de R$ 1,2 milhão."
    )
    lida = cpc15.ler_notas([(1, texto)], DEZ_2023)[0][0]
    assert cpc15.receita_do_ano(lida) == 1_200_000


def test_sem_o_nome_da_alvo_fica_vazio():
    texto = (
        "Se a aquisição tivesse ocorrido em 1 de janeiro de 2023, representaria uma receita líquida de "
        "R$ 12.000."
    )
    leituras, recusadas = cpc15.ler_notas(_paginas(texto), DEZ_2023)
    assert leituras == []
    assert cpc15.SEM_ALVO in recusadas


def test_frase_com_nome_de_pessoa_nao_entra():
    frase = (
        "Aquisição Alfa Distribuidora de Peças Ltda.\r\nSe a aquisição tivesse ocorrido em 1 de janeiro de "
        "2023, conforme o Sr. Fulano de Tal, representaria uma receita líquida de R$ 12.000."
    )
    leituras, recusadas = cpc15.ler_notas(_paginas(frase), DEZ_2023)
    assert leituras == []
    assert cpc15.COM_PESSOA in recusadas


@pytest.mark.parametrize(
    "vendedores",
    [
        "de FULANO EXEMPLAR e de Beltrano de Tal",
        "do Dr. Fulano Exemplar e da Dra. Beltrana de Tal",
        "dos Srs. Fulano Exemplar e Beltrano de Tal, inscritos sob o 88800000046,",
    ],
)
def test_o_trecho_nao_leva_nome_proprio_que_nao_seja_o_da_alvo(vendedores):
    # a nota que cita o vendedor na mesma frase: o número prova, o nome não vai à tabela
    corpo = (
        "Aquisição Alfa Distribuidora de Peças Ltda.\r\nEm 8 de agosto de 2023, a Companhia adquiriu "
        f"{vendedores} as quotas da empresa Alfa Distribuidora de Peças Ltda. Se a aquisição tivesse "
        "ocorrido em 1 de janeiro de 2023, representaria uma receita líquida de R$ 12.000."
    )
    leituras, _ = cpc15.ler_notas(_paginas(corpo), DEZ_2023)
    for lida in leituras:
        for pedaco in (
            "Fulan",
            "FULANO",
            "Exemplar",
            "EXEMPLAR",
            "Beltran",
            "Tal",
            "88800000046",
        ):
            assert pedaco not in lida.trecho
        assert "R$ 12.000" in lida.trecho
    if "Srs." not in vendedores:
        assert len(leituras) == 1


# --- a ligação do nome ao CNPJ ---------------------------------------------------------------------
def _controladas(*linhas, entregue=date(2023, 5, 31)):
    quadro = pd.DataFrame(linhas, columns=["cnpj", "razao_social"])
    # as da própria compradora, num FRE entregue antes da DFP
    return quadro.assign(cnpj_companhia="11111111000111", conhecido_em=entregue)


def _dre(receita=5_000_000_000, versoes=(1, 2, 3)):
    colunas = ["cnpj", "referencia", "versao", "exercicio_fim", "receita"]
    linhas = [(COMPRADORA, DEZ_2023, v, DEZ_2023, receita) for v in versoes]
    return pd.DataFrame(linhas, columns=colunas)


def _receita(*linhas):
    colunas = ["raiz", "nome_normalizado", "por", "pessoa", "abertura", "pequena"]
    return pd.DataFrame(linhas, columns=colunas)


def _da_receita(raiz, nome, pessoa=False, abertura="2000-01-01", pequena=False):
    return (raiz, nome, "razao_social", pessoa, pd.Timestamp(abertura), pequena)


def test_ligacao_pelas_controladas_ignora_o_apelido_entre_parenteses():
    ligada = cpc15.ligar_nomes(
        ["Alfa Distribuidora de Peças Ltda."],
        _controladas(
            ("22222222000122", 'ALFA DISTRIBUIDORA DE PEÇAS LTDA ("ALFA - VALTRA")')
        ),
        _receita(),
        publico_em=DEZ_2023,
        compradora=COMPRADORA,
    )
    assert ligada["Alfa Distribuidora de Peças Ltda."] == (
        "22222222",
        cpc15.PELAS_CONTROLADAS,
    )


def test_ligacao_pela_razao_social_unica_da_receita():
    ligada = cpc15.ligar_nomes(
        ["Beta Telecomunicações Ltda."],
        _controladas(),
        _receita(_da_receita("33333333", "beta telecomunicacoes")),
        publico_em=DEZ_2023,
    )
    assert ligada["Beta Telecomunicações Ltda."] == ("33333333", cpc15.PELA_RECEITA)


@pytest.mark.parametrize(
    "controladas, receita",
    [
        # homônimos na Receita: nunca se escolhe
        ([], [_da_receita("33333333", "beta"), _da_receita("44444444", "beta")]),
        # pessoa (MEI, empresário individual) não vira ligação
        ([], [_da_receita("33333333", "beta", pessoa=True)]),
        # nome de uma palavra só em microempresa: outra empresa com o mesmo nome curto
        ([], [_da_receita("33333333", "beta", pequena=True)]),
        # CNPJ aberto depois de a nota ficar pública não é a alvo
        ([], [_da_receita("33333333", "beta", abertura="2025-01-01")]),
        # as controladas e a Receita se contradizem
        ([("22222222000122", "Beta S.A.")], [_da_receita("33333333", "beta")]),
    ],
)
def test_ligacao_na_duvida_nao_liga(controladas, receita):
    ligada = cpc15.ligar_nomes(
        ["Beta S.A."],
        _controladas(*controladas),
        _receita(*receita),
        publico_em=DEZ_2023,
    )
    assert ligada == {}


# --- a tabela e a régua ----------------------------------------------------------------------------
def _notas(paginas, versao=1, disponivel_em=date(2024, 3, 18), cnpj=COMPRADORA):
    return pd.DataFrame(
        [
            {
                "cnpj": cnpj,
                "empresa": "COMPRADORA EXEMPLO S.A.",
                "referencia": DEZ_2023,
                "versao": versao,
                "pagina": numero,
                "texto": texto,
                "disponivel_em": disponivel_em,
                "link": f"https://exemplo/dfp?v={versao}",
                "origem_sha256": "a" * 64,
                "origem_coletada_em": "2026-11-01T00:00:00+00:00",
            }
            for numero, texto in paginas
        ]
    )


CONTROLADAS_ALFA = [("22222222000122", "Alfa Distribuidora de Peças Ltda.")]


def _tabela(notas, controladas=CONTROLADAS_ALFA, dre=None):
    dre = _dre() if dre is None else dre
    return cpc15.montar_tabela(notas, _controladas(*controladas), _receita(), dre)[0]


def test_a_linha_diz_a_fonte_o_ano_a_pagina_e_a_data_publica():
    tabela = _tabela(_notas(_paginas(AQUISICAO_ALFA, RESULTADO_ALFA)))
    linha = tabela.iloc[0]
    assert list(tabela.columns) == list(cpc15.COLUNAS)
    assert linha["cnpj_raiz"] == "22222222"
    assert linha["receita"] == 121_620_000
    assert linha["disponivel_em"] == date(2024, 3, 18)
    assert linha["resumo"] == (
        "R$ 121,6 mi em 2023, nota CPC 15 da DFP de COMPRADORA EXEMPLO S.A., página 41"
    )


def test_a_alvo_sem_ligacao_nao_vira_linha():
    tabela, recusadas = cpc15.montar_tabela(
        _notas(_paginas(AQUISICAO_ALFA, RESULTADO_ALFA)),
        _controladas(),
        _receita(),
        pd.DataFrame(
            columns=["cnpj", "referencia", "versao", "exercicio_fim", "receita"]
        ),
    )
    assert tabela.empty and recusadas[cpc15.SEM_CNPJ] == 1


def test_consolidado_usa_a_dre_da_mesma_versao_e_nao_de_outra():
    corpo = (
        "Aquisição Alfa Distribuidora de Peças Ltda.\r\nA Alfa contribuiu desde a aquisição com R$ 10.000 de receita líquida. "
        "Se a aquisição tivesse ocorrido em 1 de janeiro de 2023, a receita líquida consolidada da Companhia "
        "seria de R$ 530.000."
    )
    dre = pd.DataFrame(
        [(COMPRADORA, DEZ_2023, 2, DEZ_2023, 500_000_000.0)],
        columns=["cnpj", "referencia", "versao", "exercicio_fim", "receita"],
    )
    assert _tabela(_notas(_paginas(corpo), versao=1), dre=dre).empty
    assert (
        _tabela(_notas(_paginas(corpo), versao=2), dre=dre).iloc[0]["receita"]
        == 40_000_000
    )


def test_sem_olhar_o_futuro_a_versao_nova_nao_muda_a_linha_de_antes():
    antes = _notas(_paginas(AQUISICAO_ALFA, RESULTADO_ALFA))
    corrigida = RESULTADO_ALFA.replace("64.456", "74.456")
    depois = _notas(
        _paginas(AQUISICAO_ALFA, corrigida), versao=2, disponivel_em=date(2025, 1, 10)
    )
    tudo = _tabela(pd.concat([antes, depois], ignore_index=True))
    so_antes = tudo[tudo["disponivel_em"] <= date(2024, 12, 31)].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        so_antes.drop(columns="montado_em", errors="ignore"),
        _tabela(antes).drop(columns="montado_em", errors="ignore"),
    )
    assert list(tudo["receita"]) == [121_620_000, 131_620_000]


def test_dois_valores_para_a_mesma_alvo_no_mesmo_documento_nao_entram():
    outra = RESULTADO_ALFA.replace("64.456", "74.456")
    notas = _notas(_paginas(AQUISICAO_ALFA, RESULTADO_ALFA, AQUISICAO_ALFA, outra))
    assert _tabela(notas).empty


def test_receitas_para_a_regua_sao_cpc15_com_a_data_do_documento():
    tabela = _tabela(_notas(_paginas(AQUISICAO_ALFA, RESULTADO_ALFA)))
    receitas = cpc15.receitas_para_a_regua(tabela)
    assert list(receitas.columns) == list(ma_regua.COLUNAS_DAS_RECEITAS)
    linha = receitas.iloc[0]
    assert (linha["cnpj_raiz"], linha["fonte"]) == ("22222222", ma_regua.CPC15)
    assert linha["publico_em"] == date(2024, 3, 18)
    assert "página 41" in linha["documento"]


# --- a carga ---------------------------------------------------------------------------------------
def test_a_carga_grava_a_tabela_e_a_regua_a_le(tmp_path, monkeypatch, capsys):
    (tmp_path / "notas_dfp").mkdir()
    (tmp_path / "controladas").mkdir()
    (tmp_path / "demonstracoes").mkdir()
    pd.DataFrame(
        {"cnpj": [COMPRADORA], "demonstracao": ["DRE"], "conta": ["3.01"]}
    ).to_parquet(tmp_path / "demonstracoes" / "2023.parquet")
    monkeypatch.setattr(cpc15, "dre_consolidada", lambda _: _dre())
    notas = _notas(_paginas(AQUISICAO_ALFA, RESULTADO_ALFA))
    notas.to_parquet(tmp_path / "notas_dfp" / "2023.parquet")
    _controladas(*CONTROLADAS_ALFA).to_parquet(
        tmp_path / "controladas" / "2023.parquet"
    )
    arquivos = {"Empresas": ["Empresas0.zip"], "Estabelecimentos": [], "Simples": []}
    monkeypatch.setattr(carga, "_receita", lambda _: (arquivos, []))
    monkeypatch.setattr(carga.ma_ligacao, "ler_receita", lambda *_: _receita())
    monkeypatch.setattr(carga.ma_ligacao, "raizes_de_empresa", lambda *a: set(a[-1]))

    carga.montar_receitas_cpc15(None, tmp_path)  # type: ignore[arg-type]

    gravada = ler_tabela(tmp_path / "ma" / "receitas_cpc15" / "dfp.parquet")
    assert list(gravada["receita"]) == [121_620_000]
    assert "1 linhas, 1 alvos" in capsys.readouterr().out
    # a régua usa a receita num negócio posterior ao documento, não no que a própria nota contou
    datas = pd.DataFrame(
        {
            "assessoria": ["x", "x"],
            "url": ["antes", "depois"],
            "id_negocio": ["N1", "N2"],
            "conhecido_em_do_negocio": pd.to_datetime(
                ["2023-09-01", "2025-01-10"], utc=True
            ),
            "fechamento_em": [None, None],
        }
    )
    partes = pd.DataFrame(
        {
            "assessoria": "x",
            "url": ["antes", "depois"],
            "papel": "alvo",
            "cnpj_raiz": "22222222",
        }
    )
    regua = ma_regua.medir(
        datas,
        partes,
        cpc15.receitas_para_a_regua(gravada),
        ma_regua.portes_do_cnpj([], set()),
    ).set_index("url")
    assert regua.loc["depois", "receita_fonte"] == ma_regua.CPC15
    assert regua.loc["depois", "middle_market"] == ma_regua.SIM
    assert pd.isna(regua.loc["antes", "receita"])


def _zip_da_receita(caminho, linhas):
    texto = "".join(";".join(f'"{c}"' for c in linha) + "\n" for linha in linhas)
    with zipfile.ZipFile(caminho, "w") as zipado:
        zipado.writestr("K3241.K03200Y0.D61010.CSV", texto.encode("latin-1"))
    return caminho


@pytest.mark.parametrize(
    ("natureza", "opcao_mei", "entra"),
    [
        ("2062", "N", True),  # sociedade limitada
        ("2135", "N", False),  # empresário individual
        ("4000", "N", False),  # grupo 4: pessoa física
        ("2062", "S", False),  # MEI
        (None, "N", False),  # a Receita não deu a natureza: fica fora
    ],
)
def test_so_raiz_de_empresa_entra_na_tabela(tmp_path, natureza, opcao_mei, entra):
    # "zero pessoa": vale também para o CNPJ que veio das controladas, sem passar pelo nome na Receita
    from base import ma_ligacao

    empresas = _zip_da_receita(
        tmp_path / "Empresas0.zip",
        [["22222222", "NOME QUALQUER", natureza or "", "49", "0", "03", ""]],
    )
    simples = _zip_da_receita(
        tmp_path / "Simples.zip", [["22222222", "N", "", "", opcao_mei, "", ""]]
    )

    achadas = ma_ligacao.raizes_de_empresa(
        [empresas], [simples], {"22222222", "99999999"}
    )

    assert achadas == ({"22222222"} if entra else set())


def test_a_montagem_tira_a_raiz_que_nao_e_de_empresa(monkeypatch):
    monkeypatch.setattr(cpc15, "dre_consolidada", lambda _: _dre())
    notas = _notas(_paginas(AQUISICAO_ALFA, RESULTADO_ALFA))

    tabela, recusadas = cpc15.montar_dos_anos(
        [notas],
        _controladas(*CONTROLADAS_ALFA),
        lambda _: _receita(),
        lambda _: pd.DataFrame({"cnpj": [COMPRADORA]}),
        lambda _: set(),
    )

    assert tabela.empty
    assert recusadas[cpc15.SEM_CNPJ] == 1


# --- achados da revisão cruzada: número do grupo, de outra empresa ou de outro CNPJ -------------------
CABECA_ALFA = "Aquisição Alfa Distribuidora de Peças Ltda.\r\nSe a aquisição tivesse ocorrido em 1 de janeiro de 2023, "


@pytest.mark.parametrize(
    "resto",
    [
        "a receita líquida consolidada da Companhia, incluindo a contribuição da adquirida, seria de R$ 5.123.456.",
        "a Companhia teria apresentado receita líquida consolidada de R$ 5.123.456.",
        "a receita líquida consolidada representaria R$ 5.123.456.",
        "a adquirida teria contribuído com receita líquida adicional de R$ 5.000.",
    ],
)
def test_receita_do_grupo_ou_de_parte_do_ano_nao_vira_a_da_adquirida(resto):
    leituras, _ = cpc15.ler_notas(_paginas(CABECA_ALFA + resto), DEZ_2023)
    assert leituras == []


@pytest.mark.parametrize("dre", [None, 100_000_000])
def test_sem_a_dre_ou_do_tamanho_da_compradora_nao_entra(dre):
    # sem a receita da compradora não há como conferir; um valor do tamanho dela é o do grupo
    notas = _notas(_paginas(AQUISICAO_ALFA, RESULTADO_ALFA))
    colunas = ["cnpj", "referencia", "versao", "exercicio_fim", "receita"]
    linhas = [] if dre is None else [(COMPRADORA, DEZ_2023, 1, DEZ_2023, dre)]

    tabela, recusadas = cpc15.montar_tabela(
        notas,
        _controladas(*CONTROLADAS_ALFA),
        _receita(),
        pd.DataFrame(linhas, columns=colunas),
    )

    assert tabela.empty
    assert recusadas[cpc15.SEM_DRE if dre is None else cpc15.INCONSISTENTE] == 1


@pytest.mark.parametrize(
    "compra",
    [
        "a Companhia adquiriu 100% das quotas da Gama Comércio Ltda.",
        "a Companhia obteve o controle da Gama Comércio Ltda., mediante a compra de 100% das quotas.",
        "a Companhia assumiu o controle da Gama.",
        "a Companhia incorporou a Gama Comércio Ltda.",
        "passaram a integrar o grupo os negócios que a Gama conduzia.",
    ],
)
def test_a_compra_de_outra_empresa_no_meio_nao_leva_o_nome_da_anterior(compra):
    antiga = "Em 2021, a Companhia concluiu a aquisição da Zeta Logística Ltda."
    nova = (
        f"Em 1º de outubro de 2023, {compra} Se a aquisição tivesse ocorrido em 1 de janeiro de 2023, "
        "a Gama teria contribuído com R$ 241.958 de receita líquida."
    )

    leituras, recusadas = cpc15.ler_notas(_paginas(antiga, nova), DEZ_2023)

    assert leituras == []
    assert recusadas[cpc15.SEM_ALVO] == 1


def test_a_controlada_que_faz_a_compra_nao_conta_como_outra_empresa():
    # "através de sua controlada Vetor S.A." está no meio e não é a comprada
    assert (
        _unica(_paginas(AQUISICAO_ALFA, RESULTADO_ALFA)).nome
        == "Alfa Distribuidora de Peças Ltda."
    )


@pytest.mark.parametrize(
    ("dona", "homonimas", "ligada"),
    [
        # a controlada é de outra companhia e a Receita tem duas empresas com o nome: não liga
        ("99.999.999/0001-99", ["22222222", "33333333"], None),
        # a controlada é de outra companhia e a Receita não tem o nome: não liga
        ("99.999.999/0001-99", [], None),
        # é da própria compradora: desempata os homônimos
        (COMPRADORA, ["22222222", "33333333"], "22222222"),
        # de outra companhia, mas a Receita tem uma só e é a mesma raiz: liga
        ("99.999.999/0001-99", ["22222222"], "22222222"),
    ],
)
def test_controlada_de_outra_companhia_so_liga_se_a_receita_confirma(
    dona, homonimas, ligada
):
    controladas = pd.DataFrame(
        [(dona, "22222222000122", "Beta S.A.")],
        columns=["cnpj_companhia", "cnpj", "razao_social"],
    )
    controladas["conhecido_em"] = date(2023, 5, 31)
    receita = _receita(*[_da_receita(raiz, "beta") for raiz in homonimas])

    achada = cpc15.ligar_nomes(
        ["Beta S.A."], controladas, receita, DEZ_2023, COMPRADORA
    )

    assert achada.get("Beta S.A.", (None,))[0] == ligada


def test_a_tabela_fica_em_casa_porque_leva_trecho_de_nota():
    assert "ma_receitas_cpc15" in envio.FICAM_EM_CASA
    assert "ma_receitas_cpc15" not in envio.tabelas_do_degrau(7)


# --- achados da revisão do Codex: o FRE posterior e a parcela de um trimestre ------------------------
def test_o_cnpj_que_so_um_fre_posterior_identifica_data_a_linha():
    # DFP de março, FRE de agosto, negócio de junho: em junho a ligação ainda não era pública
    tabela = cpc15.montar_tabela(
        _notas(_paginas(AQUISICAO_ALFA, RESULTADO_ALFA)),
        _controladas(*CONTROLADAS_ALFA, entregue=date(2024, 8, 5)),
        _receita(),
        _dre(),
    )[0]
    assert list(tabela["disponivel_em"]) == [date(2024, 8, 5)]
    datas = pd.DataFrame(
        {
            "assessoria": "x",
            "url": ["junho", "setembro"],
            "id_negocio": ["N1", "N2"],
            "conhecido_em_do_negocio": pd.to_datetime(
                ["2024-06-10", "2024-09-10"], utc=True
            ),
            "fechamento_em": [None, None],
        }
    )
    partes = pd.DataFrame(
        {
            "assessoria": "x",
            "url": ["junho", "setembro"],
            "papel": "alvo",
            "cnpj_raiz": "22222222",
        }
    )
    regua = ma_regua.medir(
        datas,
        partes,
        cpc15.receitas_para_a_regua(tabela),
        ma_regua.portes_do_cnpj([], set()),
    ).set_index("url")
    assert pd.isna(regua.loc["junho", "receita"])
    assert regua.loc["setembro", "receita"] == 121_620_000


def test_o_fre_posterior_nao_muda_a_data_de_quem_a_receita_ja_identificava():
    receita = _receita(_da_receita("22222222", "alfa distribuidora de pecas"))
    tabela = cpc15.montar_tabela(
        _notas(_paginas(AQUISICAO_ALFA, RESULTADO_ALFA)),
        _controladas(*CONTROLADAS_ALFA, entregue=date(2024, 8, 5)),
        receita,
        _dre(),
    )[0]
    assert list(tabela["disponivel_em"]) == [date(2024, 3, 18)]
    assert list(tabela["ligacao_por"]) == [cpc15.PELA_RECEITA]


@pytest.mark.parametrize(
    "periodo",
    [
        "no quarto trimestre",
        "no segundo semestre do exercício",
        "nos últimos três meses",
        "em dezembro",
        "de outubro a dezembro de 2023",
        "para o Grupo",
    ],
)
def test_a_parcela_de_um_pedaco_do_periodo_nao_vira_o_desde_a_compra(periodo):
    resultado = (
        f"Esta combinação de negócios contribuiu {periodo} com R$ 8.000 de receita líquida. Se a aquisição "
        "da empresa tivesse ocorrido em 1 de janeiro de 2023, a receita líquida consolidada da Companhia "
        "seria aumentada em R$ 15.000."
    )

    leituras, recusadas = cpc15.ler_notas(_paginas(AQUISICAO_ALFA, resultado), DEZ_2023)

    assert leituras == []
    assert recusadas[cpc15.SEM_O_DESDE_A_COMPRA] == 1


def test_o_pro_forma_de_um_trimestre_nao_vira_o_do_ano():
    resultado = RESULTADO_ALFA.replace(
        "Se a ", "Considerado só o quarto trimestre, se a "
    )
    assert resultado != RESULTADO_ALFA

    leituras, recusadas = cpc15.ler_notas(_paginas(AQUISICAO_ALFA, resultado), DEZ_2023)

    assert leituras == []
    assert recusadas[cpc15.OUTRO_ANO] == 1
