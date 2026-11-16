"""Os ativos de uma empresa na API externa (linha 845): o leitor `conjuntos/ativos.py`.

Base de mentira, sem internet; os CNPJs são de ninguém e os nomes de campo, mina e barragem são inventados. A
ALFA é sócia de dois contratos da ANP (um pela filial; num deles a BETA também é sócia), tem uma barragem no
SIGBM e recolhe CFEM de dois processos; um contrato, uma barragem e uma CFEM só ficaram públicos depois do dia.
A VAZIA é empresa e não aparece em base nenhuma. Riscos: olhar o futuro, vazar pessoa (MEI, quem a rede trata
como pessoa, o nome do sócio e do empreendedor, as coordenadas), misturar outra empresa e esconder que não achou.
"""

from datetime import date

import pandas as pd
import pytest

from base import cnpj as cnpj_
from base.dicionario import TABELAS
from base.porta import Porta
from src.api_externa.conjuntos import ativos

DIA = date(2025, 6, 30)
ANP, SIGBM, CFEM = "anp-concessionarios", "anm-sigbm-barragens", "anm-cfem-arrecadacao"


def _cnpj(raiz: str, ordem: str = "0001") -> str:
    primeiros = f"{raiz}{ordem}"
    return primeiros + cnpj_.digitos_verificadores(primeiros)


ALFA = _cnpj("11111111")
ALFA_FILIAL = _cnpj("11111111", "0002")
BETA = _cnpj("22222222")
PESSOA = _cnpj("33333333")  # a rede a trata como pessoa
MEI = _cnpj("55555555")
VAZIA = _cnpj("66666666")
FORA_DA_REDE = _cnpj("44444444")
CONHECIDAS = [ALFA, BETA, PESSOA, MEI, VAZIA]
NOME_DO_SOCIO = "NOME DO SOCIO QUE NAO SAI"
NOME_DO_EMPREENDEDOR = "NOME DO EMPREENDEDOR QUE NAO SAI"

# (contrato, cnpj, fase, campo ou bloco, operador, participação, disponível em, visto em)
CONTRATOS = [
    ("48000.001/2010", ALFA, "Exploração", "BLOCO X", True, 60.0, "2020-01-10", "2020-01-10"),
    ("48000.001/2010", ALFA, "Produção", "CAMPO X", True, 60.0, "2025-03-01", "2025-03-01"),
    ("48000.001/2010", BETA, "Produção", "CAMPO X", False, 40.0, "2025-03-01", "2025-03-01"),
    ("48000.002/2015", ALFA_FILIAL, "Exploração", "BLOCO Y", False, 25.0, "2021-05-05", "2021-05-05"),
    ("48000.003/2025", ALFA, "Exploração", "BLOCO Z", True, 100.0, "2025-08-01", "2025-08-01"),
    ("48000.004/2018", PESSOA, "Produção", "CAMPO P", True, 100.0, "2020-01-10", "2020-01-10"),
]  # fmt: skip

# (id, cnpj, barragem, mina, uf, município, risco, dano, disponível em)
BARRAGENS = [
    ("B1", ALFA, "BARRAGEM UM", "MINA UM", "MG", "ITABIRA", "Baixa", "Alto", "2024-02-01"),
    ("B2", ALFA_FILIAL, "BARRAGEM DOIS", "MINA DOIS", "PA", "PARAUAPEBAS", "Média", "Médio", "2025-09-01"),
    ("B3", BETA, "BARRAGEM TRES", "MINA TRES", "MG", "MARIANA", "Baixa", "Baixo", "2025-06-15"),
]  # fmt: skip

# (ano, mês, processo, cnpj, substância, município, valor, disponível em)
RECOLHIMENTOS = [
    ("2025", "6", "830.001/2001", ALFA, "FERRO", "ITABIRA", 1000.0, "2025-06-20"),
    ("2025", "1", "830.001/2001", ALFA_FILIAL, "FERRO", "ITABIRA", 500.5, "2025-02-20"),
    ("2024", "7", "830.001/2001", ALFA, "FERRO", "ITABIRA", 250.0, "2024-08-20"),
    ("2024", "6", "830.001/2001", ALFA, "FERRO", "ITABIRA", 9999.0, "2024-07-20"),  # fora da janela
    ("2025", "6", "830.001/2001", ALFA, "FERRO", "ITABIRA", 777.0, "2025-07-20"),  # público depois do dia
    ("2023", "3", "830.002/1999", ALFA, "OURO", "PARACATU", 40.0, "2023-04-20"),  # parado: soma zero
    ("2025", "5", "830.003/2010", BETA, "BAUXITA", "ORIXIMINA", 3000.0, "2025-06-20"),
    ("2025", "5", "830.004/2012", MEI, "AREIA", "ITABIRA", 10.0, "2025-06-20"),
]  # fmt: skip


def _completa(tabela: str, linhas: pd.DataFrame) -> pd.DataFrame:
    """A tabela com todas as colunas do dicionário (as que o teste não usa, com um valor qualquer)."""
    for coluna in TABELAS[tabela].colunas:
        if coluna not in linhas:
            linhas[coluna] = "x"
    return linhas[list(TABELAS[tabela].colunas)]


def _dias(tabela: pd.DataFrame, *colunas: str) -> pd.DataFrame:
    for coluna in colunas:
        tabela[coluna] = pd.to_datetime(tabela[coluna]).dt.date
    return tabela


def _contratos() -> pd.DataFrame:
    tabela = pd.DataFrame(
        CONTRATOS,
        columns=["numero_do_contrato", "cnpj", "fase", "nome_fantasia", "operador", "participacao_pct",
                 "disponivel_em", "visto_em"],
    )  # fmt: skip
    tabela = tabela.assign(
        bid="R10", bacia="SANTOS", ambiente="Mar", empresa=NOME_DO_SOCIO
    )
    return _completa("anp_concessionarios", _dias(tabela, "disponivel_em", "visto_em"))


def _barragens() -> pd.DataFrame:
    tabela = pd.DataFrame(
        BARRAGENS,
        columns=["id", "cnpj", "nome", "nome_mina", "uf", "municipio", "categoria_risco", "dano_potencial",
                 "disponivel_em"],
    )  # fmt: skip
    tabela = tabela.assign(
        cnpj_raiz=tabela["cnpj"].str[:8], empreendedor=NOME_DO_EMPREENDEDOR, latitude=-19.6, longitude=-43.2,
        classificado_em=date(2024, 1, 1), nivel_emergencia="Sem emergência", situacao_operacional="Em operação",
        altura_atual_m=45.5, volume_atual_m3=1_200_000.0,
    )  # fmt: skip
    return _completa("anm_sigbm_barragens", _dias(tabela, "disponivel_em"))


def _recolhimentos() -> pd.DataFrame:
    tabela = pd.DataFrame(
        RECOLHIMENTOS,
        columns=["ano", "mes", "processo", "cnpj", "substancia", "municipio", "valor_recolhido", "disponivel_em"],
    )  # fmt: skip
    tabela = tabela.assign(
        cnpj_raiz=tabela["cnpj"].str[:8], ano_processo="2001", uf="MG", codigo_municipio="3131703",
        quantidade=1.0, unidade="t", criado_em=tabela["disponivel_em"],
    )  # fmt: skip
    return _completa(
        "anm_cfem_arrecadacao", _dias(tabela, "disponivel_em", "criado_em")
    )


def _gravar_rede(base) -> None:
    rede = pd.DataFrame(
        {
            "id_entidade": [f"E{c[:8]}{'0' * 12}" for c in CONHECIDAS],
            "valor": [c[:8] for c in CONHECIDAS],
            "sistema": "cnpj_raiz",
            "tipo": "empresa",
            "mei": [c == MEI for c in CONHECIDAS],
            "trata_como_pessoa": [c == PESSOA for c in CONHECIDAS],
        }
    )
    (base / "rede").mkdir(parents=True, exist_ok=True)
    rede[["id_entidade", "tipo", "mei", "trata_como_pessoa"]].assign(
        nome=None, natureza_juridica="2046", natureza_fonte="receita", fontes="cvm-cadastro",
        publico_em=date(2020, 1, 1),
    ).to_parquet(base / "rede" / "entidades.parquet", index=False)  # fmt: skip
    rede[["id_entidade", "sistema", "valor"]].assign(
        desde=None, ate=None, publico_em=date(2020, 1, 1), regra=2, conferido_por="regra",
        fontes="cvm-cadastro",
    ).to_parquet(base / "rede" / "identificadores.parquet", index=False)  # fmt: skip


def _gravar(pasta, tabela: pd.DataFrame) -> None:
    pasta.mkdir(parents=True)
    tabela.to_parquet(pasta / "x.parquet", index=False)


def gravar_base(base, com_anm: bool = True):
    """A base de mentira dos ativos (também a da rota, em `..._ativos_rota.py`)."""
    _gravar_rede(base)
    _gravar(base / "setoriais" / "anp_concessionarios", _contratos())
    if com_anm:
        _gravar(base / "anm_sigbm_barragens", _barragens())
        _gravar(base / "anm_cfem_arrecadacao", _recolhimentos())
    return base


@pytest.fixture
def pasta(tmp_path):
    return gravar_base(tmp_path / "base")


def _tudo(_fonte: str, _campo: str, _derivado: bool) -> bool:
    return True


def _ler(
    pasta, cnpj: str = ALFA, dia: date = DIA, permitido=_tudo, linhas_maximas=1000
):
    with Porta(pasta) as porta:
        return ativos.LeitorDeAtivos(porta, permitido, linhas_maximas).ativos(cnpj, dia)


def _valores(item: dict) -> dict:
    return {nome: envelope["valor"] for nome, envelope in item.items()}


def _chaves(dentro: object) -> set[str]:
    if isinstance(dentro, dict):
        return set(dentro) | {c for valor in dentro.values() for c in _chaves(valor)}
    if isinstance(dentro, list):
        return {c for item in dentro for c in _chaves(item)}
    return set()


# ---------------------------------------------------------------- o que sai


def test_contratos_da_anp_saem_so_com_a_parte_da_empresa_e_a_versao_do_dia(pasta):
    servido = _ler(pasta)
    assert servido is not None
    bloco = servido.corpo[ativos.PETROLEO_E_GAS]
    assert (
        bloco["achou"] is True and bloco["fonte"] == ANP and bloco["cortada"] is False
    )
    # o contrato 1 já era de produção no dia (a versão mais nova antes do dia); o 3 só ficou público depois
    assert [_valores(item) for item in bloco["itens"]] == [
        {"numero_do_contrato": "48000.002/2015", "bid": "R10", "fase": "Exploração", "nome_fantasia": "BLOCO Y",
         "bacia": "SANTOS", "ambiente": "Mar", "participacao_pct": 25.0, "operador": False},
        {"numero_do_contrato": "48000.001/2010", "bid": "R10", "fase": "Produção", "nome_fantasia": "CAMPO X",
         "bacia": "SANTOS", "ambiente": "Mar", "participacao_pct": 60.0, "operador": True},
    ]  # fmt: skip
    assert bloco["itens"][1]["fase"] == {
        "valor": "Produção", "fonte": ANP, "publico_em": "2025-03-01", "visto_em": "2025-03-01",
    }  # fmt: skip


def test_barragens_saem_sem_coordenadas_nem_empreendedor(pasta):
    bloco = _ler(pasta).corpo[ativos.BARRAGENS]
    assert bloco["achou"] is True and bloco["fonte"] == SIGBM
    assert [_valores(item) for item in bloco["itens"]] == [
        {"id": "B1", "nome": "BARRAGEM UM", "nome_mina": "MINA UM", "uf": "MG", "municipio": "ITABIRA",
         "categoria_risco": "Baixa", "dano_potencial": "Alto", "nivel_emergencia": "Sem emergência",
         "situacao_operacional": "Em operação", "altura_atual_m": 45.5, "volume_atual_m3": 1_200_000.0},
    ]  # fmt: skip
    assert bloco["itens"][0]["id"]["publico_em"] == "2024-02-01"
    assert bloco["itens"][0]["id"]["visto_em"] is None


def test_cfem_soma_os_12_meses_da_janela_e_diz_a_ultima_competencia(pasta):
    bloco = _ler(pasta).corpo[ativos.ROYALTIES]
    assert bloco["achou"] is True and bloco["fonte"] == CFEM
    assert bloco["periodo"] == {"inicio": "2024-07", "fim": "2025-06"}
    itens = [_valores(item) for item in bloco["itens"]]
    # 1000 + 500,50 (pela filial) + 250; o de 2024-06 fica fora da janela e o publicado depois do dia não entra
    assert itens == [
        {"processo": "830.001/2001", "substancia": "FERRO", "uf": "MG", "municipio": "ITABIRA",
         "recolhido_12_meses": 1750.5, "ultima_competencia": "2025-06"},
        {"processo": "830.002/1999", "substancia": "OURO", "uf": "MG", "municipio": "PARACATU",
         "recolhido_12_meses": 0.0, "ultima_competencia": "2023-03"},
    ]  # fmt: skip
    # o dia em que a soma ficou como está: a linha usada mais nova
    assert bloco["itens"][0]["recolhido_12_meses"]["publico_em"] == "2025-06-20"


def test_cada_bloco_diz_o_dado_mais_novo_da_base_no_dia(pasta):
    corpo = _ler(pasta).corpo
    assert corpo[ativos.PETROLEO_E_GAS]["dado_mais_novo"] == "2025-03-01"
    assert (
        corpo[ativos.BARRAGENS]["dado_mais_novo"] == "2025-06-15"
    )  # a da BETA conta: é a base inteira
    assert corpo[ativos.ROYALTIES]["dado_mais_novo"] == "2025-06-20"
    depois = _ler(pasta, dia=date(2026, 1, 1)).corpo
    assert depois[ativos.BARRAGENS]["dado_mais_novo"] == "2025-09-01"


def test_empresa_que_nenhuma_base_tem_sai_com_achou_falso(pasta):
    servido = _ler(pasta, VAZIA)
    assert servido is not None and servido.linhas == 0
    for tipo in ativos.ORIGENS:
        bloco = servido.corpo[tipo]
        assert bloco["achou"] is False and bloco["itens"] == [], tipo
        assert bloco["dado_mais_novo"] is not None and bloco["cobertura"], tipo
    assert servido.corpo["nao_coberto"] == list(
        ativos.NAO_COBERTO
    )  # os três blocos saem
    assert servido.corpo["limites"] == [
        ativos.LIMITES[0],
        *ativos.LIMITES_DO_BLOCO.values(),
        *ativos.LIMITES[1:],
    ]
    # a fonte vai na atribuição mesmo sem achar: o "não achou" também é da base dela
    assert servido.fontes == {ANP, SIGBM, CFEM}


def test_tabela_fora_da_base_nao_foi_consultada(tmp_path):
    """Sem o arquivo, o bloco não sai como "achou: false" (linha 917): vai em `nao_coberto`."""
    pasta = gravar_base(tmp_path / "base", com_anm=False)
    corpo = _ler(pasta).corpo
    assert corpo[ativos.PETROLEO_E_GAS]["achou"] is True
    assert ativos.BARRAGENS not in corpo
    assert ativos.FORA_DA_ROTA[ativos.BARRAGENS] in corpo["nao_coberto"]


def test_as_linhas_contam_os_itens_servidos(pasta):
    servido = _ler(pasta)
    assert servido.linhas == 2 + 1 + 2
    assert servido.corpo["cnpj"] == ALFA
    assert servido.corpo["como_era_em"] == DIA.isoformat()


def test_o_limite_de_linhas_corta_a_resposta_inteira(pasta):
    servido = _ler(pasta, linhas_maximas=3)
    corpo = servido.corpo
    assert servido.linhas == 3
    assert len(corpo[ativos.PETROLEO_E_GAS]["itens"]) == 2
    assert corpo[ativos.PETROLEO_E_GAS]["cortada"] is False
    assert len(corpo[ativos.BARRAGENS]["itens"]) == 1
    assert corpo[ativos.ROYALTIES]["itens"] == []
    assert corpo[ativos.ROYALTIES]["cortada"] is True
    assert corpo[ativos.ROYALTIES]["achou"] is True


# ---------------------------------------------------------------- sem olhar o futuro


def test_cortar_o_futuro_nao_muda_o_passado(pasta, tmp_path):
    antes = _ler(pasta).corpo
    ate_o_dia = tmp_path / "ate_o_dia"
    _gravar_rede(ate_o_dia)
    contratos, barragens, recolhimentos = _contratos(), _barragens(), _recolhimentos()
    _gravar(
        ate_o_dia / "setoriais" / "anp_concessionarios",
        contratos[contratos["disponivel_em"] <= DIA],
    )
    _gravar(
        ate_o_dia / "anm_sigbm_barragens", barragens[barragens["disponivel_em"] <= DIA]
    )
    _gravar(
        ate_o_dia / "anm_cfem_arrecadacao",
        recolhimentos[recolhimentos["disponivel_em"] <= DIA],
    )
    assert _ler(ate_o_dia).corpo == antes


def test_nada_publicado_depois_do_dia_sai(pasta):
    corpo = _ler(pasta).corpo
    envelopes = [
        envelope
        for tipo in ativos.ORIGENS
        for item in corpo[tipo]["itens"]
        for envelope in item.values()
    ]
    assert envelopes and all(e["publico_em"] <= DIA.isoformat() for e in envelopes)


# ---------------------------------------------------------------- sem pessoa e sem outra empresa


@pytest.mark.parametrize("cnpj", [PESSOA, MEI, FORA_DA_REDE])
def test_pessoa_e_quem_nao_e_empresa_nao_saem(pasta, cnpj):
    assert _ler(pasta, cnpj) is None


def test_nome_de_socio_empreendedor_e_coordenadas_nunca_saem(pasta):
    corpo = _ler(pasta).corpo
    proibidas = {"empresa", "empreendedor", "latitude", "longitude", "cnpj_raiz"}
    assert not _chaves(corpo) & proibidas
    texto = repr(corpo)
    assert NOME_DO_SOCIO not in texto and NOME_DO_EMPREENDEDOR not in texto
    assert "-19.6" not in texto and "-43.2" not in texto


def test_outra_empresa_nao_entra(pasta):
    texto = repr(_ler(pasta).corpo)
    assert "BARRAGEM TRES" not in texto and "830.003/2010" not in texto
    assert "40.0" not in texto and BETA not in texto


# ---------------------------------------------------------------- o portão


def test_bloco_que_o_portao_nao_libera_nao_aparece(pasta):
    def so_a_anp(fonte: str, _campo: str, _derivado: bool) -> bool:
        return fonte == ANP

    servido = _ler(pasta, permitido=so_a_anp)
    assert ativos.PETROLEO_E_GAS in servido.corpo
    assert ativos.BARRAGENS not in servido.corpo
    assert ativos.ROYALTIES not in servido.corpo
    assert servido.fontes == {ANP}
    # o bloco que não sai vira frase de "não cobre", antes dos ativos fora das bases
    assert servido.corpo["nao_coberto"] == [
        ativos.FORA_DA_ROTA[ativos.BARRAGENS],
        ativos.FORA_DA_ROTA[ativos.ROYALTIES],
        *ativos.NAO_COBERTO,
    ]
    # os limites não falam do bloco que não sai: nada da ANM nem da CFEM
    assert servido.corpo["limites"] == [
        ativos.LIMITES[0],
        ativos.LIMITES_DO_BLOCO[ativos.PETROLEO_E_GAS],
        *ativos.LIMITES[1:],
    ]


def test_toda_origem_tem_a_frase_de_fora_da_rota_e_o_limite():
    assert set(ativos.FORA_DA_ROTA) == set(ativos.ORIGENS)
    assert set(ativos.LIMITES_DO_BLOCO) == set(ativos.ORIGENS)


def test_sem_nenhum_bloco_liberado_nada_sai(pasta):
    assert _ler(pasta, permitido=lambda *_: False) is None


def test_campo_negado_nao_aparece(pasta):
    def sem_participacao(_fonte: str, campo: str, _derivado: bool) -> bool:
        return campo != "participacao_pct"

    itens = _ler(pasta, permitido=sem_participacao).corpo[ativos.PETROLEO_E_GAS][
        "itens"
    ]
    assert itens and all("participacao_pct" not in item for item in itens)


def test_as_contas_da_cfem_pedem_o_portao_como_derivado(pasta):
    pedidos: set[tuple[str, str, bool]] = set()

    def anota(fonte: str, campo: str, derivado: bool) -> bool:
        pedidos.add((fonte, campo, derivado))
        return campo != "valor_recolhido"

    itens = _ler(pasta, permitido=anota).corpo[ativos.ROYALTIES]["itens"]
    contas = {(CFEM, "valor_recolhido", True), (CFEM, "ano", True), (CFEM, "mes", True)}
    assert contas <= pedidos
    assert itens and all("recolhido_12_meses" not in item for item in itens)
    assert all("ultima_competencia" in item for item in itens)


def test_cfem_so_com_as_contas_liberadas_ainda_sai(pasta):
    def so_as_contas(fonte: str, _campo: str, derivado: bool) -> bool:
        return fonte == CFEM and derivado

    bloco = _ler(pasta, permitido=so_as_contas).corpo[ativos.ROYALTIES]
    assert [sorted(item) for item in bloco["itens"]] == [
        ["recolhido_12_meses", "ultima_competencia"]
    ] * 2


def test_cnpj_invalido_e_erro(pasta):
    with pytest.raises(ValueError, match="CNPJ inválido"):
        _ler(pasta, "123")
