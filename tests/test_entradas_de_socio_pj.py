"""Entradas e saídas de sócio pessoa jurídica no quadro da Receita (linha 810, PR 2).

A tabela diz quem **entrou como sócio** (ou saiu) de uma empresa, e quando: é o material da lista de
compradores por setor. Três promessas, cada uma com teste:
- **sem pessoa:** só sócio do tipo 1 (pessoa jurídica) e só raízes da lista sem pessoa do CNPJ (fora MEI,
  empresário individual e grupo 4, mesmo com CNPJ), dos dois lados;
- **sem olhar o futuro:** montar com os meses até M dá as mesmas linhas que montar com tudo e cortar em M;
- **sem movimento fantasma:** sair e entrar do mesmo jeito no mesmo mês (a troca de layout de 2024-09) não
  é entrada nem saída.
Dados de mentira: raízes e pseudônimos inventados.
"""

from datetime import date
from itertools import pairwise

import pandas as pd
import pytest

from base import receita_diff, socios_pj
from base.dicionario import TABELAS
from base.pessoas.proibidas import procurar
from base.porta.duckdb import ARQUIVOS, conectar

PRIMEIRO_MES = "2023-05"
MESES = ["2023-05", "2023-06", "2023-07", "2023-08"]
EMPRESA_A, EMPRESA_B, EMPRESA_C = "11111111", "22222222", "33333333"
HOLDING, FUNDO, GESTORA = "44444444", "55555555", "66666666"
EMPRESARIO_INDIVIDUAL = "77777777"  # tem CNPJ, mas a razão social é o nome da pessoa
MEI = "88888888"
PESSOAS_JURIDICAS = {EMPRESA_A, EMPRESA_B, EMPRESA_C, HOLDING, FUNDO, GESTORA}
COLUNAS_DO_QSA = [
    "cnpj_basico",
    "tipo_socio",
    "qualificacao",
    "data_entrada",
    "pais",
    "raiz_socio_pj",
    "id_pessoa",
]


def _socio_pj(empresa: str, socio: str, entrada: str, qualificacao: str = "22") -> dict:
    return {
        "cnpj_basico": empresa,
        "tipo_socio": "1",
        "qualificacao": qualificacao,
        "data_entrada": pd.Timestamp(entrada),
        "pais": None,
        "raiz_socio_pj": socio,
        "id_pessoa": "",
    }


def _socio_pf(empresa: str, pseudonimo: str, entrada: str) -> dict:
    return {
        "cnpj_basico": empresa,
        "tipo_socio": "2",
        "qualificacao": "49",
        "data_entrada": pd.Timestamp(entrada),
        "pais": None,
        "raiz_socio_pj": "",
        "id_pessoa": pseudonimo,
    }


def _retratos() -> dict[str, pd.DataFrame]:
    """Quatro meses de quadro de sócios, com o que acontece de verdade no arquivo da Receita."""
    inicial = [
        _socio_pj(EMPRESA_A, HOLDING, "2010-03-01"),  # já estava; fica
        _socio_pj(EMPRESA_B, GESTORA, "2015-06-10"),  # já estava; sai em 2023-07
        _socio_pf(EMPRESA_A, "pseudonimo-1", "2010-03-01"),
        _socio_pj(EMPRESA_C, EMPRESARIO_INDIVIDUAL, "2012-01-01"),
        _socio_pj(MEI, HOLDING, "2019-01-01"),
    ]
    junho = inicial + [
        _socio_pj(EMPRESA_C, FUNDO, "2023-06-02"),  # entra
        _socio_pf(EMPRESA_C, "pseudonimo-2", "2023-06-02"),
        _socio_pj(EMPRESA_B, EMPRESARIO_INDIVIDUAL, "2023-06-05"),
    ]
    julho = [s for s in junho if s["raiz_socio_pj"] != GESTORA] + [
        _socio_pj(EMPRESA_A, FUNDO, "2023-07-01"),  # entra
    ]
    agosto = julho + [_socio_pj(EMPRESA_B, HOLDING, "2023-08-03")]  # entra
    retratos = {
        "2023-05": inicial,
        "2023-06": junho,
        "2023-07": julho,
        "2023-08": agosto,
    }
    return {
        mes: pd.DataFrame(linhas, columns=COLUNAS_DO_QSA)
        for mes, linhas in retratos.items()
    }


def _mudancas(retratos: dict[str, pd.DataFrame], ate: str) -> pd.DataFrame:
    meses = [m for m in MESES if m <= ate]
    vazia = receita_diff.diff(
        retratos[meses[0]], retratos[meses[0]], receita_diff.CHAVE_DO_QSA, meses[0]
    )
    partes = [vazia] + [
        receita_diff.diff(
            retratos[antes], retratos[depois], receita_diff.CHAVE_DO_QSA, depois
        )
        for antes, depois in pairwise(meses)
    ]
    return pd.concat(partes, ignore_index=True)


def _montar(
    ate: str,
    retratos: dict[str, pd.DataFrame] | None = None,
    pessoas_juridicas: set[str] = PESSOAS_JURIDICAS,
) -> pd.DataFrame:
    retratos = retratos or _retratos()
    return socios_pj.entradas_e_saidas(
        retratos[ate], _mudancas(retratos, ate), PRIMEIRO_MES, pessoas_juridicas
    )


def _com_volta() -> dict[str, pd.DataFrame]:
    """A gestora sai de B em 2023-07 e volta em 2023-08 com a mesma data de entrada."""
    retratos = _retratos()
    volta = pd.DataFrame([_socio_pj(EMPRESA_B, GESTORA, "2015-06-10")])
    retratos["2023-08"] = pd.concat([retratos["2023-08"], volta], ignore_index=True)
    return retratos


def _com_data_trocada() -> dict[str, pd.DataFrame]:
    """Em 2023-07 a Receita troca a data de entrada da holding em A (o sócio continua)."""
    retratos = _retratos()
    for mes in ("2023-07", "2023-08"):
        quadro = retratos[mes]
        holding_em_a = (quadro["cnpj_basico"] == EMPRESA_A) & (
            quadro["raiz_socio_pj"] == HOLDING
        )
        quadro.loc[holding_em_a, "data_entrada"] = pd.Timestamp("2011-01-01")
    return retratos


def _da_dupla(tabela: pd.DataFrame, empresa: str, socio: str) -> list[tuple]:
    return [
        linha[0:1] + linha[3:]
        for linha in _como_lista(tabela)
        if linha[1:3] == (empresa, socio)
    ]


def _como_lista(tabela: pd.DataFrame) -> list[tuple]:
    colunas = [
        "movimento",
        "cnpj_basico",
        "raiz_socio_pj",
        "data_entrada",
        "mes_do_retrato",
    ]
    return sorted(tabela[colunas].itertuples(index=False, name=None))


def test_entradas_e_saidas_com_o_mes_em_que_a_base_viu():
    assert _como_lista(_montar("2023-08")) == [
        ("entrou", EMPRESA_A, HOLDING, pd.Timestamp("2010-03-01"), PRIMEIRO_MES),
        ("entrou", EMPRESA_A, FUNDO, pd.Timestamp("2023-07-01"), "2023-07"),
        ("entrou", EMPRESA_B, HOLDING, pd.Timestamp("2023-08-03"), "2023-08"),
        ("entrou", EMPRESA_B, GESTORA, pd.Timestamp("2015-06-10"), PRIMEIRO_MES),
        ("entrou", EMPRESA_C, FUNDO, pd.Timestamp("2023-06-02"), "2023-06"),
        ("saiu", EMPRESA_B, GESTORA, pd.Timestamp("2015-06-10"), "2023-07"),
    ]


def test_disponivel_em_e_o_piso_de_publicacao_do_mes():
    tabela = _montar("2023-08")
    linha = tabela[tabela["mes_do_retrato"] == "2023-07"].iloc[0]
    assert linha["disponivel_em"] == pd.Timestamp(receita_diff.disponivel_em("2023-07"))


def test_nenhuma_pessoa_sai_na_tabela():
    """Zero pessoa: nem sócio pessoa física, nem pseudônimo, nem MEI ou empresário individual (que têm CNPJ),
    de nenhum dos dois lados."""
    tabela = _montar("2023-08")
    assert not {"id_pessoa", "tipo_socio", "nome", "pais"} & set(tabela.columns)
    raizes = set(tabela["cnpj_basico"]) | set(tabela["raiz_socio_pj"])
    assert raizes <= PESSOAS_JURIDICAS
    assert not {EMPRESARIO_INDIVIDUAL, MEI} & raizes
    assert not tabela.astype(str).isin(["pseudonimo-1", "pseudonimo-2"]).any().any()
    assert procurar(tabela, socios_pj.TABELA) == []


@pytest.mark.parametrize("corte", MESES)
def test_cortar_o_futuro_nao_muda_o_passado(corte):
    """Montar só com os meses até o corte dá as mesmas linhas que montar com tudo e cortar."""
    tudo = _montar(MESES[-1])
    ate_o_corte = tudo[tudo["mes_do_retrato"] <= corte]
    assert _como_lista(_montar(corte)) == _como_lista(ate_o_corte)


@pytest.mark.parametrize("corte", MESES)
@pytest.mark.parametrize("cenario", [_com_volta, _com_data_trocada])
def test_cortar_o_futuro_nao_muda_o_passado_na_volta_e_na_data_trocada(cenario, corte):
    tudo = _montar(MESES[-1], cenario())
    ate_o_corte = tudo[tudo["mes_do_retrato"] <= corte]
    assert _como_lista(_montar(corte, cenario())) == _como_lista(ate_o_corte)


def test_quem_sai_e_volta_com_a_mesma_data_entra_de_novo():
    """A volta é uma entrada nova, no mês em que a base a viu, mesmo com a data de entrada de antes."""
    assert _da_dupla(_montar("2023-08", _com_volta()), EMPRESA_B, GESTORA) == [
        ("entrou", pd.Timestamp("2015-06-10"), PRIMEIRO_MES),
        ("entrou", pd.Timestamp("2015-06-10"), "2023-08"),
        ("saiu", pd.Timestamp("2015-06-10"), "2023-07"),
    ]


def test_data_trocada_pela_receita_nao_e_entrada():
    """O sócio continuou: a troca da data é `data_corrigida`, e não aparece entrada nova em 2023-07."""
    tabela = _montar("2023-08", _com_data_trocada())
    assert _da_dupla(tabela, EMPRESA_A, HOLDING) == [
        ("data_corrigida", pd.Timestamp("2011-01-01"), "2023-07"),
        ("entrou", pd.Timestamp("2010-03-01"), PRIMEIRO_MES),
    ]
    assert not (
        (tabela["movimento"] == "entrou")
        & (tabela["mes_do_retrato"] == "2023-07")
        & (tabela["raiz_socio_pj"] == HOLDING)
    ).any()


def test_raiz_que_sai_da_lista_sem_pessoa_some_da_historia_inteira():
    """A lista sem pessoa é a do mês mais recente e vale para todos os meses: a privacidade vem antes do ponto
    no tempo. Quem deixou de ser só empresa some do passado; o resto não muda."""
    com_holding = _montar("2023-08")
    sem_holding = _montar("2023-08", pessoas_juridicas=PESSOAS_JURIDICAS - {HOLDING})
    assert HOLDING not in set(sem_holding["raiz_socio_pj"]) | set(
        sem_holding["cnpj_basico"]
    )
    assert _como_lista(sem_holding) == _como_lista(
        com_holding[com_holding["raiz_socio_pj"] != HOLDING]
    )


def test_mes_sem_saida_com_a_data_de_antes_lida_como_texto():
    """Num mês só com entradas, a data de antes vem vazia e pode ser lida como texto: não quebra a montagem."""
    retratos = _retratos()
    mudancas = _mudancas(retratos, "2023-06")
    assert not (mudancas["tipo"] == "saiu").any()
    mudancas["data_entrada_antes"] = mudancas["data_entrada_antes"].astype(object)
    tabela = socios_pj.entradas_e_saidas(
        retratos["2023-06"], mudancas, PRIMEIRO_MES, PESSOAS_JURIDICAS
    )
    assert _como_lista(tabela) == _como_lista(_montar("2023-06"))


def test_sair_e_entrar_igual_no_mesmo_mes_nao_e_movimento():
    """Na troca de layout de 2024-09 a Receita tirou e pôs de volta milhares de sócios iguais: sem movimento."""
    retratos = _retratos()
    mudancas = _mudancas(retratos, "2023-08")
    holding = mudancas[mudancas["raiz_socio_pj"] == HOLDING].iloc[[0]]
    fantasma = pd.concat(
        [
            holding.assign(
                mes="2023-08",
                tipo="saiu",
                data_entrada_antes=pd.Timestamp("2010-03-01"),
                qualificacao_antes="22",
                cnpj_basico=EMPRESA_A,
                ordem=0,
            ),
            holding.assign(
                mes="2023-08",
                tipo="entrou",
                data_entrada_depois=pd.Timestamp("2010-03-01"),
                qualificacao_depois="22",
                cnpj_basico=EMPRESA_A,
                ordem=1,
            ),
        ],
        ignore_index=True,
    )
    com_fantasma = pd.concat([mudancas, fantasma], ignore_index=True)
    tabela = socios_pj.entradas_e_saidas(
        retratos["2023-08"], com_fantasma, PRIMEIRO_MES, PESSOAS_JURIDICAS
    )
    assert _como_lista(tabela) == _como_lista(_montar("2023-08"))


def test_qualificacao_vem_de_quando_entrou():
    retratos = _retratos()
    retratos["2023-08"].loc[
        retratos["2023-08"]["raiz_socio_pj"] == FUNDO, "qualificacao"
    ] = "05"
    tabela = socios_pj.entradas_e_saidas(
        retratos["2023-08"],
        _mudancas(retratos, "2023-08"),
        PRIMEIRO_MES,
        PESSOAS_JURIDICAS,
    )
    fundo_em_c = tabela[
        (tabela["cnpj_basico"] == EMPRESA_C) & (tabela["raiz_socio_pj"] == FUNDO)
    ]
    assert list(fundo_em_c["qualificacao"]) == ["22"]


def test_porta_serve_a_tabela_com_a_data_de_entrada(tmp_path):
    """A view lê o Parquet como o script grava e dá `aconteceu_em` = a data de entrada na sociedade."""
    arquivo = tmp_path / ARQUIVOS[socios_pj.TABELA].replace("*", "11")
    arquivo.parent.mkdir(parents=True)
    _montar("2023-08").to_parquet(arquivo, index=False)
    with conectar(
        tmp_path,
        tabelas={socios_pj.TABELA: TABELAS[socios_pj.TABELA]},
        arquivos={socios_pj.TABELA: ARQUIVOS[socios_pj.TABELA]},
    ) as con:
        linhas = con.execute(
            f"SELECT raiz_socio_pj, aconteceu_em FROM {socios_pj.TABELA} "
            f"WHERE movimento = 'entrou' AND cnpj_basico = '{EMPRESA_C}'"
        ).fetchall()
    assert linhas == [(FUNDO, date(2023, 6, 2))]


DEFEITO = {
    "2023-07": "2023-08"
}  # nos dados de mentira, 2023-07 faz o papel do retrato de 2024-09


def _com_retrato_com_defeito() -> dict[str, pd.DataFrame]:
    """O retrato de 2023-07 vem com defeito, como o de 2024-09 da Receita: tira a holding de A (que volta em
    2023-08 igual) e põe a gestora em C, que só existe nele. O resto de 2023-07 é verdade (a gestora sai de B
    e o fundo entra em A)."""
    retratos = _retratos()
    julho = retratos["2023-07"]
    holding_em_a = (julho["cnpj_basico"] == EMPRESA_A) & (
        julho["raiz_socio_pj"] == HOLDING
    )
    fantasma = pd.DataFrame([_socio_pj(EMPRESA_C, GESTORA, "2020-01-01")])
    retratos["2023-07"] = pd.concat([julho[~holding_em_a], fantasma], ignore_index=True)
    return retratos


def _montar_com_defeito(ate: str, defeito: dict[str, str] = DEFEITO) -> pd.DataFrame:
    retratos = _com_retrato_com_defeito()
    return socios_pj.entradas_e_saidas(
        retratos[ate],
        _mudancas(retratos, ate),
        PRIMEIRO_MES,
        PESSOAS_JURIDICAS,
        defeito,
    )


def test_sem_a_regra_o_retrato_com_defeito_inventa_movimentos():
    """O cenário reproduz o defeito: sem a regra, a holding sai e volta e a gestora aparece em C."""
    tabela = _montar_com_defeito("2023-08", defeito={})
    assert ("saiu", pd.Timestamp("2010-03-01"), "2023-07") in _da_dupla(
        tabela, EMPRESA_A, HOLDING
    )
    assert _da_dupla(tabela, EMPRESA_C, GESTORA) != []


def test_retrato_com_defeito_conta_no_mes_seguinte():
    """Comparar 2023-08 direto com 2023-06: some o que o defeito inventou, e o que mudou de verdade aparece em
    2023-08, com o piso de publicação de 2023-08 (nunca com o mês do retrato com defeito)."""
    tabela = _montar_com_defeito("2023-08")
    assert "2023-07" not in set(tabela["mes_do_retrato"])
    assert _da_dupla(tabela, EMPRESA_A, HOLDING) == [
        ("entrou", pd.Timestamp("2010-03-01"), PRIMEIRO_MES)
    ]
    assert _da_dupla(tabela, EMPRESA_C, GESTORA) == []
    assert _da_dupla(tabela, EMPRESA_B, GESTORA) == [
        ("entrou", pd.Timestamp("2015-06-10"), PRIMEIRO_MES),
        ("saiu", pd.Timestamp("2015-06-10"), "2023-08"),
    ]
    assert _da_dupla(tabela, EMPRESA_A, FUNDO) == [
        ("entrou", pd.Timestamp("2023-07-01"), "2023-08")
    ]
    depois_do_defeito = tabela[tabela["mes_do_retrato"] == "2023-08"]
    assert set(depois_do_defeito["disponivel_em"]) == {
        pd.Timestamp(receita_diff.disponivel_em("2023-08"))
    }


@pytest.mark.parametrize("corte", [m for m in MESES if m not in DEFEITO])
def test_cortar_o_futuro_nao_muda_o_passado_com_retrato_com_defeito(corte):
    """Fora o próprio retrato com defeito (que não é um ponto válido), montar até o corte é cortar o todo."""
    tudo = _montar_com_defeito(MESES[-1])
    ate_o_corte = tudo[tudo["mes_do_retrato"] <= corte]
    assert _como_lista(_montar_com_defeito(corte)) == _como_lista(ate_o_corte)


def test_o_retrato_com_defeito_da_base_e_so_o_de_2024_09():
    """Nenhuma regra geral sem evidência: só o mês contado no ensaio de 11/11/2026."""
    assert dict(socios_pj.RETRATOS_COM_DEFEITO) == {"2024-09": "2024-10"}
