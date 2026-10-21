"""`base.porta`: catálogo, ler, rede, linhagem e carteira (ADR 0077, item 9; plano da rede, PR 4,
tarefa 4.2). Tudo com uma base de mentira, sem nome de pessoa."""

import hashlib
from datetime import UTC, date, datetime
from itertools import pairwise

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import porta
from base.parquet import gravar_tabela
from base.porta import Porta
from base.rede import ligacoes as ligacoes_da_rede
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine
from src.banco.modelo import coletas

RAIZ = "11222333"
CNPJ = "11.222.333/0001-81"
DIA = "2020-12-31"


def _gravar(pasta, caminho: str, tabela: pd.DataFrame) -> None:
    arquivo = pasta / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(arquivo, index=False)


def _dias(*datas: str | None) -> pd.Series:
    return pd.to_datetime(pd.Series(datas, dtype=object))


def _ligacoes(*linhas: dict) -> pd.DataFrame:
    padrao = {
        "papel": None,
        "participacao": None,
        "aconteceu_em": "2015-01-01",
        "infracao_em": None,
        "coletado_em": "2026-10-15",
        "ate": None,
        "situacao": None,
        "encerrada_por": None,
        "fonte": "cvm-fre",
        "origem_sha256": "abc",
        "conferido_por": "regra",
    }
    return ligacoes_da_rede.normalizar(
        pd.DataFrame([{**padrao, **linha} for linha in linhas])
    )


def _entidades(*ids: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id_entidade": list(ids),
            "tipo": ["auditor" if i == "EAUD" else "empresa" for i in ids],
            "nome": [f"Empresa {i}" for i in ids],
            "natureza_juridica": ["2046"] * len(ids),
            "natureza_fonte": ["fonte"] * len(ids),
            "mei": [False] * len(ids),
            "trata_como_pessoa": [False] * len(ids),
            "fontes": ["cvm"] * len(ids),
            "publico_em": _dias(*["2010-01-01"] * len(ids)),
        }
    )


def _identificadores(*linhas: tuple) -> pd.DataFrame:
    tabela = pd.DataFrame(
        linhas,
        columns=["id_entidade", "sistema", "valor", "desde", "ate", "publico_em"],
    )
    for coluna in ("desde", "ate", "publico_em"):
        tabela[coluna] = pd.to_datetime(tabela[coluna])
    return tabela.assign(regra=1, conferido_por="regra", fontes="cvm")


@pytest.fixture
def base(tmp_path):
    """A empresa A com 2 controladas públicas em 2020, 1 controlada que só ficou pública em 2021,
    1 auditor, 1 ticker antigo (até 2015), 1 de hoje e 1 que só apareceu em 2022."""
    pasta = tmp_path / "base"
    _gravar(
        pasta,
        "rede/entidades.parquet",
        _entidades("EA", "EC1", "EC2", "EC3", "EC4", "EAUD", "EX"),
    )
    _gravar(
        pasta,
        "rede/identificadores.parquet",
        _identificadores(
            ("EA", "cnpj_raiz", RAIZ, None, None, "2010-01-01"),
            ("EA", "ticker", "VELH3", "2010-01-01", "2015-06-01", "2010-01-01"),
            ("EA", "ticker", "NOVA3", "2015-06-01", "2022-03-01", "2015-06-01"),
            ("EA", "ticker", "FUTR3", "2022-03-01", None, "2022-03-01"),
            ("EC1", "cnpj_raiz", "44555666", None, None, "2010-01-01"),
        ),
    )
    _gravar(
        pasta,
        "rede/ligacoes.parquet",
        _ligacoes(
            {
                "de": "EC1",
                "para": "EA",
                "tipo": "controlada_de",
                "publico_em": "2016-05-31",
            },
            {
                "de": "EC2",
                "para": "EA",
                "tipo": "controlada_de",
                "publico_em": "2019-05-31",
                "ate": "2023-01-01",
            },
            {
                "de": "EC3",
                "para": "EA",
                "tipo": "controlada_de",
                "publico_em": "2021-05-31",
            },
            {
                "de": "EAUD",
                "para": "EA",
                "tipo": "auditada_por",
                "publico_em": "2018-03-01",
                "fonte": "cvm-fca",
            },
            {
                "de": "EX",
                "para": "EC1",
                "tipo": "controlada_de",
                "publico_em": "2017-05-31",
            },
            {  # acabou em 2020, mas o fim só ficou público em 2021: em 2020 ainda valia
                "de": "EC4",
                "para": "EA",
                "tipo": "controlada_de",
                "publico_em": "2017-05-31",
                "ate": "2020-01-01",
                "ate_publico_em": "2021-04-23",
            },
        ),
    )
    return pasta


def test_catalogo(base):
    catalogo = Porta(base).catalogo()
    tabelas = catalogo["tabelas"]
    assert tabelas["ligacoes"]["versao"] == "1.1.0"  # coluna `ate_publico_em`
    assert tabelas["ligacoes"]["datas"]["publico_em"] == "publico_em"
    assert tabelas["ligacoes"]["na_porta"] is True
    assert tabelas["eventos"]["na_porta"] is False  # sem arquivo nesta base
    assert "banco do app" in tabelas["achados_de_qualidade"]["fora_da_porta"]
    assert tabelas["ligacoes"]["versoes"] == ["1"]


def test_ler_com_como_era_em(base):
    """D5: `publico_em ≤ D` e (`ate` vazio ou `ate > D`); um fim que é de depois de D não aparece."""
    with Porta(base) as p:
        tudo = p.ler("ligacoes")
        em_2020 = p.ler("ligacoes", como_era_em=DIA)
        so_ea = p.ler("ligacoes", como_era_em=DIA, filtros={"para": "EA"})
        tipos = p.ler("ligacoes", filtros={"de": ["EC1", "EAUD"]})
    assert len(tudo) == 6
    assert set(em_2020["de"]) == {"EC1", "EC2", "EC4", "EAUD", "EX"}
    ec2 = em_2020[em_2020["de"] == "EC2"].iloc[0]
    assert (
        pd.isna(ec2["ate"]) and ec2["situacao"] == "vigente"
    )  # o fim de 2023 era futuro
    ec4 = em_2020[em_2020["de"] == "EC4"].iloc[0]
    assert pd.isna(ec4["ate"]) and pd.isna(
        ec4["ate_publico_em"]
    )  # o fim de 2020 era segredo
    assert ec4["situacao"] == "vigente"
    assert set(so_ea["de"]) == {"EC1", "EC2", "EC4", "EAUD"}
    assert set(tipos["de"]) == {"EC1", "EAUD"}


def test_ler_recusa_o_que_nao_conhece(base):
    with Porta(base) as p:
        with pytest.raises(KeyError, match="nao_existe"):
            p.ler("nao_existe")
        with pytest.raises(KeyError, match="eventos"):
            p.ler("eventos")  # no dicionário, mas sem arquivo nesta base
        with pytest.raises(ValueError, match="coluna"):
            p.ler("ligacoes", filtros={"de; DROP TABLE x": "EA"})
        with pytest.raises(KeyError, match="versão 7"):
            p.ler("ligacoes", versao="7")


def test_distintos_traz_os_valores_sem_a_tabela_inteira(base):
    with Porta(base) as p:
        assert p.distintos("ligacoes", "para") == {"EA", "EC1"}
        with pytest.raises(ValueError, match="coluna"):
            p.distintos("ligacoes", "nao_existe")
        with pytest.raises(KeyError, match="eventos"):
            p.distintos("eventos", "cnpj")  # no dicionário, mas sem arquivo nesta base


def test_ler_so_as_colunas_pedidas(base):
    """Tabela grande lida só nas colunas que o leitor usa; a data `como_era_em` filtra mesmo assim."""
    with Porta(base) as p:
        duas = p.ler("ligacoes", colunas=["de", "para"])
        em_2020 = p.ler("ligacoes", como_era_em=DIA, colunas=["de"])
        assert "situacao" in p.colunas("ligacoes")
        with pytest.raises(ValueError, match="coluna"):
            p.ler("ligacoes", colunas=["de", "nao_existe"])
        with pytest.raises(KeyError, match="eventos"):
            p.colunas("eventos")
    assert list(duas.columns) == ["de", "para"] and len(duas) == 6
    assert list(em_2020.columns) == ["de"]
    assert set(em_2020["de"]) == {"EC1", "EC2", "EC4", "EAUD", "EX"}


def test_somar_agrupa_no_duckdb(base):
    """Série grande (Anatel: milhões de linhas) volta já somada: só o agregado vem para o pandas."""
    _gravar(
        base,
        "setoriais/anatel/Acessos_2025_Colunas.parquet",
        pd.DataFrame(
            {
                "competencia": ["2025-01-31", "2025-01-31", "2025-01-31", "2025-02-28"],
                "cnpj": ["A", "A", "B", "A"],
                "servico": ["movel"] * 4,
                "recorte": ["completo", "completo", "completo", "tecnologia"],
                "acessos": [1.0, 2.0, 5.0, 7.0],
            }
        ),
    )
    with Porta(base) as p:
        somado = p.somar(
            "anatel_acessos",
            por=["competencia", "cnpj"],
            valor="acessos",
            filtros={"recorte": ["completo", "modalidade"]},
        )
        with pytest.raises(ValueError, match="coluna"):
            p.somar("anatel_acessos", por=["nao_existe"], valor="acessos")
    assert somado.sort_values("cnpj").to_dict("records") == [
        {"competencia": "2025-01-31", "cnpj": "A", "acessos": 3.0},
        {"competencia": "2025-01-31", "cnpj": "B", "acessos": 5.0},
    ]


def test_somar_conta_so_a_revisao_mais_nova(base):
    """A Anatel republica o arquivo e a revisão vira uma linha nova (`visto_em` diferente) da mesma chave:
    somar tudo contaria o mês duas vezes. Fica a linha mais nova de cada chave; com `como_era_em`, a
    mais nova que já era pública no dia (a revisão vista depois não entra)."""
    _gravar(
        base,
        "setoriais/anatel/Acessos_2025_Colunas.parquet",
        pd.DataFrame(
            {
                "competencia": pd.to_datetime(["2025-01-31"] * 3 + ["2025-02-28"]),
                "cnpj": ["A", "A", "B", "A"],
                "servico": ["movel"] * 4,
                "recorte": ["completo"] * 4,
                "acessos": [10.0, 12.0, 5.0, 7.0],
                "visto_em": pd.to_datetime(
                    ["2026-10-14", "2026-11-14", "2026-10-14", "2026-10-14"]
                ),
                "disponivel_em": pd.to_datetime(
                    ["2025-04-01", "2026-11-14", "2025-04-01", "2025-04-30"]
                ),
            }
        ),
    )
    with Porta(base) as p:
        agora = p.somar("anatel_acessos", por=["cnpj"], valor="acessos")
        antes = p.somar(
            "anatel_acessos",
            por=["cnpj"],
            valor="acessos",
            como_era_em="2026-10-20",
        )
    assert agora.sort_values("cnpj")["acessos"].tolist() == [
        19.0,
        5.0,
    ]  # 12 + 7, não 10 + 12 + 7
    assert antes.sort_values("cnpj")["acessos"].tolist() == [
        17.0,
        5.0,
    ]  # a revisão ainda não era pública


def test_ler_como_era_em_devolve_uma_linha_por_chave_antes_e_depois_da_revisao(base):
    """IF.data: o BC revisou o saldo; a revisão é linha nova da mesma chave e só vale desde o dia em que
    foi vista. Um dia antes, o `como_era_em` devolve o número antigo (e uma linha só)."""
    _gravar(
        base,
        "bcb/ifdata/valores/tipo_1/202506.parquet",
        pd.DataFrame(
            {
                "data_base": pd.to_datetime(["2025-06-30"] * 2),
                "tipo_instituicao": [1, 1],
                "cod_inst": ["C1", "C1"],
                "relatorio": [1, 1],
                "grupo": ["g", "g"],
                "conta": ["1", "1"],
                "coluna": ["Ativo Total"] * 2,
                "saldo": [10.0, 99.0],
                "visto_em": pd.to_datetime(["2026-10-14", "2026-11-14"]),
                "disponivel_em": pd.to_datetime(["2025-10-28", "2026-11-14"]),
            }
        ),
    )
    with Porta(base) as p:
        antes = p.ler("ifdata_valores", como_era_em="2026-11-13")
        depois = p.ler("ifdata_valores", como_era_em="2026-11-14")
    assert antes["saldo"].tolist() == [10.0]
    assert depois["saldo"].tolist() == [99.0]


def test_somar_e_exato(base):
    """Em DOUBLE, 0,1 + 0,2 dá 0,30000000000000004 e a ordem da soma mexe na 15ª casa; em DECIMAL não."""
    _gravar(
        base,
        "setoriais/anatel/Acessos_2025_Colunas.parquet",
        pd.DataFrame(
            {
                "competencia": ["2025-01-31"] * 2,
                "cnpj": ["A"] * 2,
                "servico": ["movel"] * 2,
                "recorte": ["completo"] * 2,
                "acessos": [0.1, 0.2],
            }
        ),
    )
    with Porta(base) as p:
        somado = p.somar("anatel_acessos", por=["cnpj"], valor="acessos")
    assert somado["acessos"].tolist() == [0.3]


def test_hashes_dos_arquivos_da_tabela(base):
    """ADR 0078: quem lê anota o hash de cada arquivo (do manifesto ao lado) para refazer e conferir."""
    (base / "rede" / "ligacoes.json").write_text(
        '{"sha256_da_tabela": "h-lig"}', encoding="utf-8"
    )
    _gravar(base, "auditores/2024.parquet", pd.DataFrame({"cnpj": [CNPJ]}))
    _gravar(base, "auditores/2024.v1.parquet", pd.DataFrame({"cnpj": [CNPJ]}))
    with Porta(base) as p:
        assert p.hashes("ligacoes") == {"rede/ligacoes": "h-lig"}
        assert p.hashes("auditores") == {"auditores/2024": None}  # sem manifesto
        with pytest.raises(KeyError, match="eventos"):
            p.hashes("eventos")


def test_ler_como_era_em_sem_data_publica_e_erro(tmp_path):
    """Sem `publico_em` no contrato, a porta não finge saber como era."""
    _gravar(
        tmp_path,
        "fundos/buracos.parquet",
        pd.DataFrame({"emissor": ["ABCD"], "meses": [3]}),
    )
    with Porta(tmp_path) as p:
        assert len(p.ler("buracos_dos_fundos")) == 1
        with pytest.raises(ValueError, match="publico_em"):
            p.ler("buracos_dos_fundos", como_era_em=DIA)


DIAS = st.dates(min_value=date(2015, 1, 1), max_value=date(2025, 12, 31))


@settings(max_examples=20, deadline=None)
@given(
    linhas=st.lists(
        st.tuples(DIAS, st.one_of(st.none(), DIAS)), min_size=1, max_size=12
    ),
    dia=DIAS,
)
def test_como_era_em_nao_traz_o_que_ficou_publico_depois(tmp_path_factory, linhas, dia):
    """Igual à regra de `base/rede/ligacoes.py::como_era_em`, e cortar o futuro não muda o passado."""
    pasta = tmp_path_factory.mktemp("base")
    tabela = _ligacoes(
        *(
            {
                "de": f"E{i}",
                "para": "EA",
                "tipo": "controlada_de",
                "publico_em": str(publico),
                "ate": None if ate is None else str(ate),
            }
            for i, (publico, ate) in enumerate(linhas)
        )
    )
    _gravar(pasta, "rede/ligacoes.parquet", tabela)
    with Porta(pasta, conferidas={}) as p:
        pela_porta = set(p.ler("ligacoes", como_era_em=str(dia))["de"])
    esperado = set(ligacoes_da_rede.como_era_em(tabela, pd.Timestamp(dia))["de"])
    assert pela_porta == esperado
    cortada = tabela[tabela["publico_em"] <= pd.Timestamp(dia)]
    _gravar(pasta, "rede/ligacoes.parquet", cortada)
    with Porta(pasta, conferidas={}) as p:
        assert set(p.ler("ligacoes", como_era_em=str(dia))["de"]) == pela_porta


def test_rede_de_uma_empresa_de_mentira(base):
    """2 controladas, 1 ticker antigo e 1 auditor: só o que já era público em 2020."""
    with Porta(base) as p:
        rede = p.rede(CNPJ, como_era_em=DIA)
        pelo_ticker = p.rede("NOVA3", como_era_em=DIA)
    assert rede.centro == "EA"
    assert pelo_ticker.centro == "EA"
    assert sorted(zip(rede.ligacoes["de"], rede.ligacoes["tipo"], strict=True)) == [
        ("EAUD", "auditada_por"),
        ("EC1", "controlada_de"),
        ("EC2", "controlada_de"),
        ("EC4", "controlada_de"),
    ]
    assert set(rede.ligacoes["salto"]) == {1}
    assert set(rede.entidades["id_entidade"]) == {"EA", "EC1", "EC2", "EC4", "EAUD"}
    tickers = rede.identificadores[rede.identificadores["sistema"] == "ticker"]
    assert set(tickers["valor"]) == {"VELH3", "NOVA3"}  # o FUTR3 só apareceu em 2022
    nova = tickers[tickers["valor"] == "NOVA3"].iloc[0]
    assert pd.isna(nova["ate"])  # em 2020 o NOVA3 ainda valia: o fim de 2022 era futuro


def test_rede_sem_data_traz_tudo_e_tipos_filtram(base):
    with Porta(base) as p:
        hoje = p.rede(RAIZ)
        so_controle = p.rede(RAIZ, tipos=["controlada_de"])
    assert set(hoje.ligacoes["de"]) == {"EC1", "EC2", "EC3", "EC4", "EAUD"}
    assert set(so_controle.ligacoes["de"]) == {"EC1", "EC2", "EC3", "EC4"}


def test_rede_de_quem_nao_existe_e_erro(base):
    with Porta(base) as p:
        with pytest.raises(LookupError, match="99888777"):
            p.rede("99888777")
        with pytest.raises(LookupError, match="FUTR3"):
            p.rede("FUTR3", como_era_em=DIA)  # o ticker ainda não era público


def test_rede_com_profundidade(tmp_path):
    """Uma corrente A ← B ← C ← D ← E: `profundidade=3` não passa de 3 saltos."""
    corrente = ["EA", "EB", "EC", "ED", "EE"]
    _gravar(tmp_path, "rede/entidades.parquet", _entidades(*corrente))
    _gravar(
        tmp_path,
        "rede/identificadores.parquet",
        _identificadores(("EA", "cnpj_raiz", RAIZ, None, None, "2010-01-01")),
    )
    _gravar(
        tmp_path,
        "rede/ligacoes.parquet",
        _ligacoes(
            *(
                {
                    "de": de,
                    "para": para,
                    "tipo": "controlada_de",
                    "publico_em": "2016-05-31",
                }
                for para, de in pairwise(corrente)
            )
        ),
    )
    with Porta(tmp_path) as p:
        um = p.rede(RAIZ)
        tres = p.rede(RAIZ, profundidade=3)
    assert set(um.entidades["id_entidade"]) == {"EA", "EB"}
    assert set(tres.entidades["id_entidade"]) == {"EA", "EB", "EC", "ED"}
    assert dict(zip(tres.entidades["id_entidade"], tres.entidades["salto"], strict=True)) == {
        "EA": 0, "EB": 1, "EC": 2, "ED": 3,
    }  # fmt: skip
    assert tres.ligacoes["salto"].max() == 3
    with pytest.raises(ValueError, match="profundidade"):
        Porta(tmp_path).rede(RAIZ, profundidade=0)


def test_rede_por_id_direto_de_quem_ainda_nao_era_publico_e_erro(base):
    """N10: pelo id (não pelo CNPJ), a entidade que só ficou pública depois do dia não aparece."""
    entidades = _entidades("EA", "EC1", "EC2", "EC3", "EC4", "EAUD", "EX")
    entidades.loc[entidades["id_entidade"] == "EA", "publico_em"] = pd.Timestamp(
        "2021-05-31"
    )
    _gravar(base, "rede/entidades.parquet", entidades)
    with Porta(base) as p:
        assert p.rede("EA").centro == "EA"  # sem data, a de hoje
        with pytest.raises(LookupError, match="pública até 2020-12-31"):
            p.rede("EA", como_era_em=DIA)


@settings(max_examples=20, deadline=None)
@given(
    publicas=st.lists(DIAS, min_size=2, max_size=6),
    ligacoes=st.lists(
        st.tuples(
            st.integers(0, 5), st.integers(0, 5), DIAS, st.one_of(st.none(), DIAS)
        ),
        min_size=1,
        max_size=12,
    ),
    dia=DIAS,
)
def test_rede_por_id_direto_nao_traz_o_que_ficou_publico_depois(
    tmp_path_factory, publicas, ligacoes, dia
):
    """N10: pedir a rede pelo id direto não traz entidade nem ligação pública só depois do dia, e
    cortar o futuro das tabelas não muda a rede de antes."""
    ids = [f"E{i}" for i in range(len(publicas))]
    entidades = _entidades(*ids).assign(publico_em=pd.to_datetime(publicas))
    # uma linha por (de, para, dia): a chave da ligação não se repete
    unicas = {
        (ids[de % len(ids)], ids[para % len(ids)], publico): ate
        for de, para, publico, ate in ligacoes
        if de % len(ids) != para % len(ids)
    }
    if not unicas:
        return
    tabela = _ligacoes(
        *(
            {
                "de": de,
                "para": para,
                "tipo": "controlada_de",
                "aconteceu_em": str(publico),
                "publico_em": str(publico),
                "ate": None if ate is None else str(ate),
            }
            for (de, para, publico), ate in unicas.items()
        )
    )
    dia_ = pd.Timestamp(dia)

    def _rede(pasta, entidades_, ligacoes_):
        _gravar(pasta, "rede/entidades.parquet", entidades_)
        _gravar(pasta, "rede/ligacoes.parquet", ligacoes_)
        _gravar(
            pasta,
            "rede/identificadores.parquet",
            _identificadores(("E0", "cnpj_raiz", RAIZ, None, None, "2010-01-01")),
        )
        with Porta(pasta, conferidas={}) as p:
            try:
                return p.rede("E0", como_era_em=str(dia), profundidade=3)
            except LookupError:
                return None

    # uma pasta por exemplo, com as duas bases dentro: criar a pasta é o que demora
    pasta = tmp_path_factory.mktemp("base")
    inteira = _rede(pasta / "inteira", entidades, tabela)
    cortada = _rede(
        pasta / "cortada",
        entidades[entidades["publico_em"] <= dia_],
        tabela[tabela["publico_em"] <= dia_],
    )
    if entidades.iloc[0]["publico_em"] > dia_:
        assert inteira is None and cortada is None
        return
    assert inteira is not None and cortada is not None
    assert (inteira.ligacoes["publico_em"] <= dia_).all()
    assert (inteira.entidades["publico_em"].dropna() <= dia_).all()
    assert inteira.entidades["nome"].notna().tolist() == (
        inteira.entidades["publico_em"].notna().tolist()
    )

    def _linhas(tabela, colunas):
        return sorted(map(tuple, tabela[colunas].astype(str).to_numpy()))

    assert _linhas(inteira.ligacoes, ligacoes_da_rede.CHAVE) == _linhas(
        cortada.ligacoes, ligacoes_da_rede.CHAVE
    )
    assert _linhas(inteira.entidades, ["id_entidade", "salto", "nome"]) == _linhas(
        cortada.entidades, ["id_entidade", "salto", "nome"]
    )


URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
ORIGINAL = b"cadastro de mentira"
BAIXADO_EM = datetime(2026, 10, 13, 0, 30, tzinfo=UTC)


def test_linhagem_pela_porta(tmp_path, monkeypatch):
    """De uma linha lida pela porta ao original, à coleta e à versão do código."""
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, "7ddaf09c1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b")
    motor = criar_engine(f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}")
    coletas.create(
        motor
    )  # só o registro de coletas: as migrações inteiras levam ~1 min
    caminho = acervo.guardar_original("cvm-cadastro", URL, ORIGINAL, BAIXADO_EM)
    with motor.begin() as c:
        registrar(
            c, "cvm-cadastro", URL, ORIGINAL, "ok",
            agora=BAIXADO_EM, caminho_do_original=caminho,
        )  # fmt: skip
    pasta = tmp_path / "base"
    gravar_tabela(
        _entidades("EA", "EB"),
        pasta / "rede" / "entidades",
        [{"url": URL, "sha256": hashlib.sha256(ORIGINAL).hexdigest()}],
        ["id_entidade"],
    )
    with motor.connect() as banco, Porta(pasta, banco=banco) as p:
        linha = p.ler("entidades", filtros={"id_entidade": "EB"}).iloc[0]
        caminho_da_linha = p.linhagem("entidades", linha)
        with pytest.raises(LookupError):
            p.linhagem("entidades", {"id_entidade": "ZZ"})
    motor.dispose()
    assert caminho_da_linha.completa
    assert [o.url for o in caminho_da_linha.originais()] == [URL]
    with Porta(pasta) as sem_banco, pytest.raises(ValueError, match="banco"):
        sem_banco.linhagem("entidades", {"id_entidade": "EB"})


def test_carteira(base):
    """Os eventos dos CNPJs de uma carteira desde uma data, com a entidade e o CNPJ como veio."""
    _gravar(
        base,
        "insolvencia/2024.parquet",
        pd.DataFrame(
            {
                "cnpj": [CNPJ, CNPJ, "44.555.666/0001-00", "77.888.999/0001-00"],
                "rotulo": [
                    "recuperacao_judicial",
                    "pedido_de_falencia",
                    "falencia",
                    "falencia",
                ],
                "assunto": ["RJ", "Antigo", "Controlada", "Outra"],
                "referencia": ["2024-06-01", "2019-01-01", "2024-07-01", "2024-07-01"],
                "conhecido_em": [
                    "2024-06-02",
                    "2019-01-02",
                    "2024-07-02",
                    "2024-07-02",
                ],
                "origem_coletada_em": ["2024-06-03T00:00:00+00:00"] * 4,
            }
        ),
    )
    with Porta(base) as p:
        eventos = p.carteira([CNPJ, "44555666000100"], desde="2024-01-01")
    assert list(eventos["evento"]) == ["recuperacao_judicial", "falencia"]
    assert list(eventos["cnpj_da_carteira"]) == [CNPJ, "44555666000100"]
    assert list(eventos["id_entidade"]) == ["EA", "EC1"]


def test_funcoes_do_modulo_usam_o_acervo(base, monkeypatch):
    """`base.porta.ler(...)` sem abrir nada: a base é `<acervo>/base`."""
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(base.parent))
    assert len(porta.ler("ligacoes", como_era_em=DIA)) == 5
    assert porta.rede(RAIZ).centro == "EA"
    assert "ligacoes" in porta.catalogo()["tabelas"]
    assert porta.carteira([CNPJ], desde="2024-01-01").empty
