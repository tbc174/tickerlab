"""Os vínculos de uma empresa na API externa (linha 736, PR 5): o leitor `conjuntos/vinculos.py`.

Base de mentira, sem internet; os CNPJs são de ninguém. A ALFA é controlada da MAE, controla a FILHA (que
controla a NETA, que controla a BISNETA), tem uma coligada e é auditada por uma firma. Uma controlada só ficou
pública depois do dia; uma acabou e se soube antes do dia; outra acabou, mas só se soube depois. Há também o
que nunca sai: a controlada que a rede trata como pessoa, o sócio pessoa física, o fundo que detém o papel e a
série do regulador. O nome de cada ponta vem do histórico datado da Receita: a ALFA mudou de nome depois do
dia, a COLIGADA não tem retrato e a VENDIDA_DEPOIS saiu do arquivo antes do dia. Riscos: olhar o futuro (também
no nome, que a rede guarda só como é hoje), vazar pessoa e servir ligação ou nome de fonte sem direito.
"""

from datetime import date

import pandas as pd
import pytest

from base import cnpj as cnpj_
from base.porta import Porta
from base.rede import ligacoes as ligacoes_da_rede
from src.api_externa.conjuntos import vinculos

DIA = date(2025, 6, 30)
FRE, FCA, RECEITA = "cvm-hist-fre", "cvm-hist-fca", "rfb-cnpj"


def _cnpj(raiz: str, ordem: str = "0001") -> str:
    primeiros = f"{raiz}{ordem}"
    return primeiros + cnpj_.digitos_verificadores(primeiros)


# (id, raiz, tipo, nome, fontes, trata como pessoa, pública em)
ENTIDADES = [
    ("EALFA", "11111111", "empresa", "ALFA S.A.", "cvm-cadastro,cvm-fre", False, "2010-01-01"),
    ("EMAE", "22222222", "empresa", "MAE PARTICIPACOES S.A.", "cvm-cadastro", False, "2010-01-01"),
    ("EFILHA", "55555555", "empresa", "FILHA LTDA", "cvm-fre", False, "2010-01-01"),
    ("ENETA", "56565656", "empresa", "NETA LTDA", "cvm-fre", False, "2010-01-01"),
    ("EBISNETA", "57575757", "empresa", "BISNETA LTDA", "cvm-fre", False, "2010-01-01"),
    ("ECOLIGADA", "66666666", "empresa", "COLIGADA PELO GLEIF", "cvm-fre,gleif", False, "2010-01-01"),
    ("EFUTURA", "67676767", "empresa", "FUTURA LTDA", "cvm-fre", False, "2025-07-10"),
    ("EVENDIDA", "68686868", "empresa", "VENDIDA LTDA", "cvm-fre", False, "2010-01-01"),
    ("EVENDIDA_DEPOIS", "69696969", "empresa", "VENDIDA DEPOIS LTDA", "cvm-fre", False, "2010-01-01"),
    ("EINDIVIDUAL", "12121212", "empresa", None, "cvm-fre", True, "2010-01-01"),
    ("EAUDITORA", "99999999", "auditor", "AUDITORA UM", "cvm-fca-auditores", False, "2010-01-01"),
    ("EFUNDO", "88888888", "fundo", "FUNDO X", "cvm-fundos", False, "2010-01-01"),
    ("EPESSOA", "33333333", "empresa", None, "cvm-cadastro", True, "2010-01-01"),
]  # fmt: skip
ALFA = _cnpj("11111111")
PESSOA = _cnpj("33333333")
FORA_DA_REDE = _cnpj("44444444")

# o histórico datado da razão social (cnpj_empresas_historico): (raiz, mês do retrato, disponível em, consta,
# natureza, razão social). O nome da rede (ENTIDADES) é o de hoje e nunca sai.
NOMES = [
    ("11111111", "2023-05", "2023-05-21", True, "2046", "ALFA LTDA"),
    ("11111111", "2025-07", "2025-07-21", True, "2046", "ALFA HOLDING S.A."),
    ("22222222", "2023-05", "2023-05-21", True, "2046", "MAE PARTICIPACOES S.A."),
    ("55555555", "2023-05", "2023-05-21", True, "2062", "FILHA LTDA"),
    ("56565656", "2023-05", "2023-05-21", True, "2062", "NETA LTDA"),
    ("57575757", "2023-05", "2023-05-21", True, "2062", "BISNETA LTDA"),
    ("67676767", "2023-05", "2023-05-21", True, "2062", "FUTURA LTDA"),
    ("68686868", "2023-05", "2023-05-21", True, "2062", "VENDIDA LTDA"),
    ("69696969", "2023-05", "2023-05-21", True, "2062", "VENDIDA DEPOIS LTDA"),
    ("69696969", "2025-03", "2025-03-21", False, None, None),
    ("99999999", "2023-05", "2023-05-21", True, "2240", "AUDITORA UM"),
    ("12121212", "2023-05", "2023-05-21", True, "2135", None),
]  # fmt: skip

# (de, para, tipo, participação, aconteceu em, público em, até, fim público em, fonte)
LIGACOES = [
    ("EALFA", "EMAE", "controlada_de", 60.0, "2018-12-31", "2019-05-31", None, None, "cvm-fre"),
    ("EFILHA", "EALFA", "controlada_de", 100.0, "2018-12-31", "2019-05-31", None, None, "cvm-fre"),
    ("ENETA", "EFILHA", "controlada_de", 99.5, "2019-12-31", "2020-05-31", None, None, "cvm-fre"),
    ("EBISNETA", "ENETA", "controlada_de", 70.0, "2019-12-31", "2020-05-31", None, None, "cvm-fre"),
    ("ECOLIGADA", "EALFA", "coligada_de", 30.0, "2019-12-31", "2020-05-31", None, None, "cvm-fre"),
    ("EFUTURA", "EALFA", "controlada_de", 51.0, "2024-12-31", "2025-07-10", None, None, "cvm-fre"),
    ("EVENDIDA", "EALFA", "controlada_de", 80.0, "2018-12-31", "2019-05-31", "2024-12-31", "2025-05-31",
     "cvm-fre"),
    ("EVENDIDA_DEPOIS", "EALFA", "controlada_de", 90.0, "2018-12-31", "2019-05-31", "2024-12-31",
     "2025-07-31", "cvm-fre"),
    ("EINDIVIDUAL", "EALFA", "controlada_de", 100.0, "2018-12-31", "2019-05-31", None, None, "cvm-fre"),
    ("EAUDITORA", "EALFA", "audita", None, "2022-01-01", "2022-05-31", None, None, "cvm-fca"),
    ("EFUNDO", "EALFA", "detem", None, "2022-01-01", "2022-05-31", None, None, "cvm-cda"),
    ("EMAE", "EALFA", "opera_para", None, "2022-01-01", "2022-05-31", None, None, "empresa_serie"),
    ("P0123456789abcdef0123", "EALFA", "socio_de", 50.0, "2018-01-01", "2019-05-31", None, None, "rfb-qsa"),
]  # fmt: skip


def _gravar(pasta, caminho: str, tabela: pd.DataFrame) -> None:
    arquivo = pasta / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(arquivo, index=False)


def _gravar_nomes(base, nomes: list[tuple]) -> None:
    tabela = pd.DataFrame(
        nomes,
        columns=["cnpj_basico", "mes_do_retrato", "disponivel_em", "consta", "natureza_juridica", "razao_social"],
    )  # fmt: skip
    tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"]).dt.date
    tabela = tabela.assign(
        origem_sha256="0" * 64,
        montado_em=pd.Timestamp("2026-11-05", tz="UTC"),
        versao_do_codigo="teste",
    )
    _gravar(base, "cnpj_empresas_historico/1.parquet", tabela)


def gravar_base(
    base, ligacoes: list[tuple] | None = None, nomes: list[tuple] | None = None
):
    """A base de mentira dos vínculos (também a da rota, em `..._vinculos_rota.py`)."""
    _gravar_nomes(base, NOMES if nomes is None else nomes)
    entidades = pd.DataFrame(
        ENTIDADES,
        columns=["id_entidade", "raiz", "tipo", "nome", "fontes", "trata_como_pessoa", "publico_em"],
    )  # fmt: skip
    entidades["publico_em"] = pd.to_datetime(entidades["publico_em"])
    _gravar(
        base,
        "rede/entidades.parquet",
        entidades.drop(columns="raiz").assign(
            natureza_juridica="2046", natureza_fonte="receita", mei=False
        ),
    )
    _gravar(
        base,
        "rede/identificadores.parquet",
        pd.DataFrame(
            {
                "id_entidade": entidades["id_entidade"],
                "sistema": "cnpj_raiz",
                "valor": entidades["raiz"],
                "desde": pd.NaT,
                "ate": pd.NaT,
                "publico_em": entidades["publico_em"],
            }
        ).assign(regra=1, conferido_por="regra", fontes="cvm-cadastro"),
    )
    colunas = ["de", "para", "tipo", "participacao", "aconteceu_em", "publico_em", "ate",
               "ate_publico_em", "fonte"]  # fmt: skip
    tabela = pd.DataFrame(LIGACOES if ligacoes is None else ligacoes, columns=colunas)
    _gravar(
        base,
        "rede/ligacoes.parquet",
        ligacoes_da_rede.normalizar(
            tabela.assign(
                papel=None,
                infracao_em=None,
                coletado_em="2025-09-01",
                situacao=None,
                encerrada_por=None,
                origem_sha256="abc",
                conferido_por="regra",
            )
        ),
    )
    return base


@pytest.fixture
def pasta(tmp_path):
    return gravar_base(tmp_path / "base")


def _tudo(_fonte: str, _campo: str, _derivado: bool) -> bool:
    return True


def _ler(
    pasta,
    cnpj: str = ALFA,
    dia: date = DIA,
    profundidade: int = 1,
    tipos: tuple[str, ...] = tuple(vinculos.TIPOS),
    permitido=_tudo,
    linhas_maximas: int = 1000,
):
    with Porta(pasta) as porta:
        return vinculos.LeitorDeVinculos(porta, permitido, linhas_maximas).vinculos(
            cnpj, dia, profundidade, tipos
        )


def _pares(servido) -> list[tuple[str, str, str]]:
    return [
        (v["tipo"]["valor"], v["de"]["id_na_rede"], v["para"]["id_na_rede"])
        for v in servido.corpo["vinculos"]
    ]


def test_os_vinculos_de_um_salto_como_eram_no_dia(pasta):
    servido = _ler(pasta)
    assert _pares(servido) == [
        ("subsidiary_of", "EALFA", "EMAE"),
        ("subsidiary_of", "EFILHA", "EALFA"),
        ("subsidiary_of", "EVENDIDA_DEPOIS", "EALFA"),
        ("affiliate_of", "ECOLIGADA", "EALFA"),
        ("audits", "EAUDITORA", "EALFA"),
    ]
    assert servido.corpo["cnpj"] == ALFA
    assert servido.corpo["como_era_em"] == "2025-06-30"
    assert servido.corpo["profundidade"] == 1
    assert servido.corpo["cortada"] is False
    assert servido.linhas == 5
    assert servido.fontes == {FRE, FCA, RECEITA}


def test_cada_campo_sai_no_envelope_com_a_fonte_e_o_dia_publico(pasta):
    (mae, filha, *_resto) = _ler(pasta).corpo["vinculos"]
    assert mae["salto"] == 1
    assert (
        mae["de"]
        == {
            "id_na_rede": "EALFA",
            "raiz_do_cnpj": "11111111",
            "razao_social": {
                "valor": "ALFA LTDA",
                "fonte": RECEITA,
                "publico_em": "2023-05-31",  # o retrato é mensal: vale pelo último dia do mês
                "visto_em": None,
            },
        }
    )
    assert mae["participacao_no_capital"] == {
        "valor": 60.0, "fonte": FRE, "publico_em": "2019-05-31", "visto_em": None,
    }  # fmt: skip
    assert mae["tipo"] == {
        "valor": "subsidiary_of",
        "fonte": FRE,
        "publico_em": "2019-05-31",
        "visto_em": None,
    }
    assert mae["aconteceu_em"]["valor"] == "2018-12-31"
    assert "ate" not in mae  # ainda vale
    assert filha["de"]["razao_social"]["valor"] == "FILHA LTDA"


def test_o_auditor_sai_pelo_fca_sem_participacao(pasta):
    auditoria = _ler(pasta).corpo["vinculos"][-1]
    assert auditoria["tipo"]["valor"] == "audits"
    assert auditoria["de"]["razao_social"] == {
        "valor": "AUDITORA UM", "fonte": RECEITA, "publico_em": "2023-05-31", "visto_em": None,
    }  # fmt: skip
    assert "participacao_no_capital" not in auditoria
    assert auditoria["tipo"]["fonte"] == FCA


def test_ponta_sem_retrato_da_receita_sai_sem_nome(pasta):
    coligada = next(
        v for v in _ler(pasta).corpo["vinculos"] if v["tipo"]["valor"] == "affiliate_of"
    )
    # a rede sabe um nome (do GLEIF), mas ele é o de hoje e de fonte que não sai: só o da Receita no dia sai
    assert coligada["de"] == {"id_na_rede": "ECOLIGADA", "raiz_do_cnpj": "66666666"}
    assert coligada["participacao_no_capital"]["valor"] == 30.0


def _nome(servido, id_na_rede: str) -> object:
    for vinculo in servido.corpo["vinculos"]:
        for ponta in (vinculo["de"], vinculo["para"]):
            if ponta["id_na_rede"] == id_na_rede:
                return ponta.get("razao_social", {}).get("valor")
    raise AssertionError(f"{id_na_rede} não está nos vínculos")


def test_o_nome_da_ponta_e_o_que_valia_no_dia_nao_o_de_hoje(pasta):
    # a ALFA virou ALFA HOLDING em 07/2025: no dia ela ainda era ALFA LTDA (o nome da rede, ALFA S.A., é o de hoje)
    assert _nome(_ler(pasta), "EALFA") == "ALFA LTDA"
    assert _nome(_ler(pasta, dia=date(2025, 7, 31)), "EALFA") == "ALFA HOLDING S.A."


def test_antes_do_primeiro_retrato_a_ponta_sai_sem_nome(pasta):
    servido = _ler(pasta, dia=date(2022, 6, 1))
    assert servido.corpo["vinculos"]
    assert all(
        "razao_social" not in v["de"] and "razao_social" not in v["para"]
        for v in servido.corpo["vinculos"]
    )
    assert RECEITA not in servido.fontes


def test_a_raiz_que_saiu_do_arquivo_sai_sem_nome(pasta):
    # a VENDIDA_DEPOIS não consta do retrato de 03/2025 (o último antes do dia)
    assert _nome(_ler(pasta), "EVENDIDA_DEPOIS") is None
    assert (
        _nome(_ler(pasta, dia=date(2025, 3, 1)), "EVENDIDA_DEPOIS")
        == "VENDIDA DEPOIS LTDA"
    )


def test_a_ponta_que_era_empresario_individual_sai_sem_nome_no_periodo(tmp_path):
    # a MAE era empresário individual (razão social vazia, ADR 0106) até virar S.A. depois do dia
    nomes = [linha for linha in NOMES if linha[0] != "22222222"] + [
        ("22222222", "2023-05", "2023-05-21", True, "2135", None),
        ("22222222", "2025-07", "2025-07-21", True, "2046", "MAE PARTICIPACOES S.A."),
    ]
    pasta = gravar_base(tmp_path / "base", nomes=nomes)
    assert _nome(_ler(pasta), "EMAE") is None
    assert _nome(_ler(pasta, dia=date(2025, 7, 31)), "EMAE") == "MAE PARTICIPACOES S.A."


def test_sem_o_historico_da_receita_as_pontas_saem_sem_nome(pasta):
    for arquivo in (pasta / "cnpj_empresas_historico").glob("*.parquet"):
        arquivo.unlink()
    (pasta / "cnpj_empresas_historico").rmdir()
    servido = _ler(pasta)
    assert len(servido.corpo["vinculos"]) == 5
    assert RECEITA not in servido.fontes


def test_a_ligacao_publicada_depois_do_dia_nao_entra(pasta):
    assert "EFUTURA" not in {de for _, de, _ in _pares(_ler(pasta))}
    depois = _ler(pasta, dia=date(2025, 7, 10))
    assert "EFUTURA" in {de for _, de, _ in _pares(depois)}


def test_a_ligacao_que_acabou_e_se_soube_antes_do_dia_nao_entra(pasta):
    assert "EVENDIDA" not in {de for _, de, _ in _pares(_ler(pasta))}
    antes = _ler(pasta, dia=date(2024, 12, 30))
    assert "EVENDIDA" in {de for _, de, _ in _pares(antes)}


def test_o_fim_que_so_se_soube_depois_do_dia_nao_aparece(pasta):
    # D5: no dia, ninguém sabia que a EVENDIDA_DEPOIS tinha sido vendida; o fim não aparece
    no_dia = next(
        v
        for v in _ler(pasta).corpo["vinculos"]
        if v["de"]["id_na_rede"] == "EVENDIDA_DEPOIS"
    )
    assert "ate" not in no_dia
    depois = _ler(pasta, dia=date(2025, 7, 31)).corpo["vinculos"]
    assert "EVENDIDA_DEPOIS" not in {v["de"]["id_na_rede"] for v in depois}


def test_nenhum_campo_publicado_depois_do_dia(pasta):
    for dia in (date(2019, 6, 1), date(2022, 6, 1), DIA, date(2025, 12, 31)):
        servido = _ler(pasta, dia=dia, profundidade=3)
        for vinculo in servido.corpo["vinculos"]:
            pontas = (
                vinculo["de"].get("razao_social"),
                vinculo["para"].get("razao_social"),
            )
            for valor in (*vinculo.values(), *pontas):
                if isinstance(valor, dict) and "publico_em" in valor:
                    assert valor["publico_em"] <= dia.isoformat(), (dia, vinculo)


def test_cortar_o_futuro_da_base_nao_muda_a_resposta(tmp_path):
    inteira = gravar_base(tmp_path / "inteira")
    sem_futuro = [linha for linha in LIGACOES if linha[5] <= DIA.isoformat()]
    nomes_sem_futuro = [linha for linha in NOMES if linha[2] <= DIA.isoformat()]
    cortada = gravar_base(tmp_path / "cortada", sem_futuro, nomes_sem_futuro)
    assert _ler(inteira).corpo == _ler(cortada).corpo


def test_a_profundidade_anda_pela_cadeia_de_controle(pasta):
    dois = _pares(_ler(pasta, profundidade=2))
    assert ("subsidiary_of", "ENETA", "EFILHA") in dois
    assert ("subsidiary_of", "EBISNETA", "ENETA") not in dois
    tres = _ler(pasta, profundidade=3).corpo["vinculos"]
    bisneta = next(v for v in tres if v["de"]["id_na_rede"] == "EBISNETA")
    assert bisneta["salto"] == 3
    assert [v["salto"] for v in tres] == sorted(v["salto"] for v in tres)


@pytest.mark.parametrize("profundidade", [0, 4, -1])
def test_profundidade_fora_de_1_a_3_e_pedido_invalido(pasta, profundidade):
    with pytest.raises(vinculos.PedidoInvalido) as erro:
        _ler(pasta, profundidade=profundidade)
    assert erro.value.codigo == "invalid_depth"


def test_os_tipos_filtram_pelo_nome_de_fora(pasta):
    so_controle = vinculos.tipos_do_pedido(["subsidiary_of"])
    assert so_controle == ("controlada_de",)
    assert {t for t, _, _ in _pares(_ler(pasta, tipos=so_controle))} == {
        "subsidiary_of"
    }
    assert vinculos.tipos_do_pedido([]) == tuple(vinculos.TIPOS)
    with pytest.raises(vinculos.PedidoInvalido) as erro:
        vinculos.tipos_do_pedido(
            ["controlada_de"]
        )  # o nome de dentro não vale por fora
    assert erro.value.codigo == "invalid_link_type"


def test_nunca_sai_pessoa_nem_ligacao_de_outro_tipo(pasta):
    servido = _ler(pasta, profundidade=3)
    ids = {v["de"]["id_na_rede"] for v in servido.corpo["vinculos"]} | {
        v["para"]["id_na_rede"] for v in servido.corpo["vinculos"]
    }
    # a controlada tratada como pessoa, o sócio pessoa física, o fundo (detem) e a série (opera_para)
    assert not ids & {"EINDIVIDUAL", "EFUNDO", "EPESSOA"}
    assert not any(i.startswith("P") for i in ids)
    assert {v["tipo"]["valor"] for v in servido.corpo["vinculos"]} <= set(
        vinculos.TIPO_PELO_NOME_DE_FORA
    )


def test_quem_a_rede_trata_como_pessoa_ou_nao_conhece_nao_e_servido(pasta):
    assert _ler(pasta, cnpj=PESSOA) is None
    assert _ler(pasta, cnpj=FORA_DA_REDE) is None


def test_ponta_sem_saber_se_e_pessoa_nao_sai(tmp_path):
    base = gravar_base(tmp_path / "base")
    entidades = pd.read_parquet(base / "rede" / "entidades.parquet")
    entidades["trata_como_pessoa"] = entidades["trata_como_pessoa"].astype(object)
    entidades.loc[entidades["id_entidade"] == "EFILHA", "trata_como_pessoa"] = None
    entidades.to_parquet(base / "rede" / "entidades.parquet", index=False)
    assert "EFILHA" not in {de for _, de, _ in _pares(_ler(base))}


def test_antes_de_a_empresa_entrar_na_rede_a_lista_sai_vazia(pasta):
    servido = _ler(pasta, dia=date(2009, 1, 1))
    assert servido is None or servido.corpo["vinculos"] == []


def test_empresa_sem_vinculo_no_dia_sai_com_a_lista_vazia(pasta):
    servido = _ler(pasta, dia=date(2018, 1, 1))
    assert servido.corpo["vinculos"] == []
    assert servido.linhas == 0
    assert servido.fontes == set()


def test_sem_a_tabela_de_ligacoes_a_lista_sai_vazia(pasta):
    (pasta / "rede" / "ligacoes.parquet").unlink()
    assert _ler(pasta).corpo["vinculos"] == []


def test_campo_negado_some_e_sem_o_tipo_a_ligacao_nao_sai(pasta):
    def sem_participacao(fonte: str, nome: str, _derivado: bool) -> bool:
        return nome != "participacao"

    servido = _ler(pasta, permitido=sem_participacao)
    assert all("participacao_no_capital" not in v for v in servido.corpo["vinculos"])

    def sem_o_fca(fonte: str, _campo: str, _derivado: bool) -> bool:
        return fonte != FCA

    servido = _ler(pasta, permitido=sem_o_fca)
    assert "audits" not in {t for t, _, _ in _pares(servido)}
    assert FCA not in servido.fontes


def test_nome_negado_some_mas_a_ponta_fica(pasta):
    def sem_nome(fonte: str, nome: str, _derivado: bool) -> bool:
        return (fonte, nome) != (RECEITA, "razao_social")

    servido = _ler(pasta, permitido=sem_nome)
    assert servido.corpo["vinculos"]
    assert all(
        "razao_social" not in v["de"] and "razao_social" not in v["para"]
        for v in servido.corpo["vinculos"]
    )
    assert RECEITA not in servido.fontes


def test_sem_nenhum_tipo_liberado_nada_sai(pasta):
    assert _ler(pasta, permitido=lambda *_: False) is None
    so_fre = vinculos.tipos_do_pedido(["audits"])
    assert _ler(pasta, tipos=so_fre, permitido=lambda f, *_: f != FCA) is None


def test_a_pagina_vai_ate_o_limite_de_linhas(pasta):
    servido = _ler(pasta, linhas_maximas=2)
    assert servido.linhas == 2
    assert servido.corpo["cortada"] is True
    assert _pares(servido) == _pares(_ler(pasta))[:2]


def test_cnpj_invalido_e_erro(pasta):
    with pytest.raises(ValueError, match="CNPJ inválido"):
        _ler(pasta, cnpj="123")


def test_a_pagina_cortada_so_busca_o_nome_das_pontas_dela(pasta, monkeypatch):
    raizes_pedidas = []
    original = vinculos.LeitorDeVinculos._nomes

    def espiao(self, raizes, como_era_em):
        raizes_pedidas.append(set(raizes))
        return original(self, raizes, como_era_em)

    monkeypatch.setattr(vinculos.LeitorDeVinculos, "_nomes", espiao)
    servido = _ler(pasta, linhas_maximas=1)
    assert servido.corpo["cortada"] is True
    assert raizes_pedidas == [
        {"11111111", "22222222"}
    ]  # só a ALFA e a MAE, da única ligação da página


def test_as_fontes_na_rede_sao_as_que_a_montagem_grava():
    from base.rede import ligacoes_das_fontes as das_fontes

    assert set(vinculos.TIPOS) <= {
        das_fontes.CONTROLADA_DE, das_fontes.COLIGADA_DE, das_fontes.PARTICIPADA_DE, das_fontes.AUDITA,
    }  # fmt: skip
