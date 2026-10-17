"""A porta em DuckDB: uma view por tabela, os apelidos das três datas e a versão antiga servida por
vista (ADR 0077, itens 8 e 9; plano da rede, PR 4, tarefa 4.1, D9 e D12)."""

import json
from dataclasses import replace
from datetime import date

import pandas as pd
import pytest

from base.contrato import contrato_da_tabela
from base.dicionario import DATA, MOMENTO, TABELAS, TEXTO, Tabela
from base.porta import duckdb as porta_duckdb
from base.porta.duckdb import (
    ARQUIVOS,
    CONFERIDAS,
    FORA_DA_PORTA,
    arquivos_da_tabela,
    conectar,
    nome_da_view,
    sem_o_fim_futuro,
)


def _tabela(**campos: object) -> Tabela:
    """Uma tabela de mentira com o mínimo que o contrato pede."""
    padrao: dict[str, object] = {
        "descricao": "de mentira",
        "fonte": "teste",
        "familia_da_fonte": "cvm",
        "frequencia": "diária",
        "atraso": "nenhum",
        "onde": "Parquet em `<acervo>/base/fatos/<ano>.parquet`",
        "linhagem": "teste",
        "modulo": "teste",
        "chaves": ("id",),
        "granularidade_do_publico_em": "dia",
    }
    return Tabela(**{**padrao, **campos})  # type: ignore[arg-type]


def _gravar(pasta, caminho: str, tabela: pd.DataFrame) -> None:
    arquivo = pasta / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(arquivo, index=False)


def _congelar(contratos, nome: str, tabela: Tabela) -> None:
    maior = tabela.versao_do_contrato.split(".")[0]
    arquivo = contratos / f"v{maior}" / f"{nome}.json"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(
        json.dumps(contrato_da_tabela(nome, tabela), ensure_ascii=False),
        encoding="utf-8",
    )


FATOS = _tabela(
    colunas={
        "id": ("Identificador", TEXTO),
        "referencia": ("Data do fato", DATA),
        "publicado_em": ("Entrega", DATA),
        "origem_coletada_em": ("Coleta", MOMENTO),
    },
    datas={
        "aconteceu_em": "referencia",
        "publico_em": "publicado_em",
        "coletado_em": "origem_coletada_em",
    },
)


def test_view_respeita_o_apelido_das_datas(tmp_path):
    """Cada view tem `aconteceu_em`, `publico_em` e `coletado_em` como dia, venha a coluna como data,
    texto ISO ou momento em UTC (o dia é o de UTC, não o do relógio do PC), e o mês do retrato vale
    pelo último dia do mês (o conservador: nada antes de o mês terminar)."""
    _gravar(
        tmp_path,
        "fatos/2024.parquet",
        pd.DataFrame(
            {
                "id": ["a"],
                "referencia": pd.to_datetime(["2023-12-31"]),
                "publicado_em": ["2024-03-01"],
                # 1h da manhã em UTC = 22h do dia anterior em São Paulo
                "origem_coletada_em": ["2024-03-02T01:00:00+00:00"],
            }
        ),
    )
    _gravar(
        tmp_path,
        "retratos/2024-02.parquet",
        pd.DataFrame({"id": ["b"], "mes_do_retrato": ["2024-02"]}),
    )
    retratos = _tabela(
        colunas={
            "id": ("Identificador", TEXTO),
            "mes_do_retrato": ("Mês", "AAAA-MM"),
        },
        datas={"publico_em": "mes_do_retrato"},
        granularidade_do_publico_em="mes",
    )
    with conectar(
        tmp_path,
        tabelas={"fatos": FATOS, "retratos": retratos},
        arquivos={"fatos": "fatos/*.parquet", "retratos": "retratos/*.parquet"},
        contratos=tmp_path / "contratos",
    ) as con:
        fatos = con.execute(
            "SELECT id, referencia, aconteceu_em, publico_em, coletado_em FROM fatos"
        ).fetchall()
        retrato = con.execute("SELECT publico_em FROM retratos").fetchone()
        sem_data = con.execute("SELECT column_name FROM (DESCRIBE retratos)").fetchall()
    assert fatos[0][0] == "a"
    assert fatos[0][2:] == (date(2023, 12, 31), date(2024, 3, 1), date(2024, 3, 2))
    assert retrato == (date(2024, 2, 29),)
    # só os apelidos que a tabela tem: sem inventar data onde a fonte não dá
    assert {"aconteceu_em", "coletado_em"}.isdisjoint({c for (c,) in sem_data})


def test_momento_com_fuso_vira_o_dia_de_utc(tmp_path):
    """Momento gravado com fuso (TIMESTAMP WITH TIME ZONE) vira o dia de UTC, não o do relógio."""
    momentos = _tabela(
        colunas={"id": ("Identificador", TEXTO), "baixado": ("Coleta", MOMENTO)},
        datas={"coletado_em": "baixado"},
    )
    _gravar(
        tmp_path,
        "momentos/m.parquet",
        pd.DataFrame(
            {"id": ["a"], "baixado": pd.to_datetime(["2024-03-02T01:00:00+00:00"])}
        ),
    )
    with conectar(
        tmp_path,
        tabelas={"momentos": momentos},
        arquivos={"momentos": "momentos/*.parquet"},
        contratos=tmp_path / "contratos",
    ) as con:
        assert con.execute("SELECT coletado_em FROM momentos").fetchone() == (
            date(2024, 3, 2),
        )


def test_apelido_com_nome_de_outra_coluna_e_erro(tmp_path):
    _gravar(
        tmp_path,
        "fatos/2024.parquet",
        pd.DataFrame({"id": ["a"], "publico_em": ["x"], "entrega": ["2024-01-01"]}),
    )
    confusa = _tabela(
        colunas={
            "id": ("Identificador", TEXTO),
            "publico_em": ("Outra coisa", TEXTO),
            "entrega": ("Entrega", DATA),
        },
        datas={"publico_em": "entrega"},
    )
    with pytest.raises(ValueError, match="publico_em"):
        conectar(
            tmp_path,
            tabelas={"fatos": confusa},
            arquivos={"fatos": "fatos/*.parquet"},
            contratos=tmp_path / "contratos",
        )


def test_view_nao_le_as_versoes_guardadas(tmp_path):
    """`2024.v1.parquet` é a tabela de antes (ADR 0078): a view só lê as vigentes."""
    linha = pd.DataFrame(
        {
            "id": ["nova"],
            "referencia": ["2024-01-01"],
            "publicado_em": ["2024-01-02"],
            "origem_coletada_em": ["2024-01-03T00:00:00+00:00"],
        }
    )
    _gravar(tmp_path, "fatos/2024.parquet", linha)
    _gravar(tmp_path, "fatos/2024.v1.parquet", linha.assign(id="antiga"))
    assert [a.name for a in arquivos_da_tabela(tmp_path, "fatos/*.parquet")] == [
        "2024.parquet"
    ]
    with conectar(
        tmp_path,
        tabelas={"fatos": FATOS},
        arquivos={"fatos": "fatos/*.parquet"},
        contratos=tmp_path / "contratos",
    ) as con:
        assert con.execute("SELECT id FROM fatos").fetchall() == [("nova",)]


def test_tabela_sem_arquivo_fica_sem_view(tmp_path):
    with conectar(
        tmp_path,
        tabelas={"fatos": FATOS},
        arquivos={"fatos": "fatos/*.parquet"},
        contratos=tmp_path / "contratos",
    ) as con:
        views = {nome for (nome,) in con.execute("SHOW TABLES").fetchall()}
    assert "fatos" not in views


def test_versao_antiga_servida_pela_vista(tmp_path):
    """Coluna renomeada numa v2 de mentira: a view da v1 devolve o nome antigo pelo contrato
    congelado, sem a coluna nova e sem segunda cópia em Parquet (D12)."""
    v1 = _tabela(
        colunas={"id": ("Identificador", TEXTO), "empresa": ("Nome", TEXTO)},
    )
    v2 = replace(
        v1,
        colunas={
            "id": ("Identificador", TEXTO),
            "nome": ("Nome", TEXTO),
            "setor": ("Setor", TEXTO),
        },
        versao_do_contrato="2.0.0",
        renomeadas={"empresa": "nome"},
    )
    contratos = tmp_path / "contratos"
    _congelar(contratos, "fatos", v1)
    _congelar(contratos, "fatos", v2)
    _gravar(
        tmp_path / "base",
        "fatos/2024.parquet",
        pd.DataFrame({"id": ["a"], "nome": ["Petro"], "setor": ["óleo"]}),
    )
    with conectar(
        tmp_path / "base",
        tabelas={"fatos": v2},
        arquivos={"fatos": "fatos/*.parquet"},
        contratos=contratos,
    ) as con:
        atual = con.execute(f"SELECT * FROM {nome_da_view('fatos')}").df()
        antiga = con.execute(f"SELECT * FROM {nome_da_view('fatos', '1')}").df()
        pela_versao = con.execute(
            f"SELECT * FROM {nome_da_view('fatos', '2.0.0')}"
        ).df()
    assert list(atual.columns) == ["id", "nome", "setor"]
    assert list(antiga.columns) == ["id", "empresa"]
    assert antiga.to_dict("records") == [{"id": "a", "empresa": "Petro"}]
    assert pela_versao.equals(atual)  # a versão de hoje também tem nome com o número
    assert [a.name for a in (tmp_path / "base").rglob("*.parquet")] == ["2024.parquet"]


def test_coluna_que_sumiu_sem_renomear_volta_vazia(tmp_path):
    v1 = _tabela(colunas={"id": ("Identificador", TEXTO), "velha": ("Saiu", TEXTO)})
    v2 = replace(
        v1, colunas={"id": ("Identificador", TEXTO)}, versao_do_contrato="2.0.0"
    )
    contratos = tmp_path / "contratos"
    _congelar(contratos, "fatos", v1)
    _gravar(tmp_path / "base", "fatos/2024.parquet", pd.DataFrame({"id": ["a"]}))
    with conectar(
        tmp_path / "base",
        tabelas={"fatos": v2},
        arquivos={"fatos": "fatos/*.parquet"},
        contratos=contratos,
    ) as con:
        antiga = con.execute(f"SELECT * FROM {nome_da_view('fatos', '1')}").fetchall()
    assert antiga == [("a", None)]


def test_renomeadas_entram_no_contrato_so_quando_existem():
    sem = contrato_da_tabela("fatos", FATOS)
    com = contrato_da_tabela("fatos", replace(FATOS, renomeadas={"a": "b"}))
    assert "renomeadas" not in sem
    assert com["renomeadas"] == {"a": "b"}


def _cnpj(raiz: str) -> str:
    return f"{raiz[:2]}.{raiz[2:5]}.{raiz[5:8]}/0001-00"


def test_eventos_da_rede(tmp_path):
    """D9: uma view com os eventos de `eventos`, `insolvencia`, `trocas_de_auditor`,
    `cnpj_situacao_especial` e `achados_de_qualidade`, com as três datas pelos apelidos e a
    entidade pela raiz do CNPJ."""
    raiz = "12345678"
    _gravar(
        tmp_path,
        "eventos/2024.parquet",
        pd.DataFrame(
            {
                "protocolo": ["p1"],
                "versao": [1],
                "cnpj": [_cnpj(raiz)],
                "rotulo": ["fato_relevante"],
                "assunto": ["Aquisição"],
                "referencia": ["2024-05-01"],
                "publicado_em": ["2024-05-02"],
                "origem_coletada_em": ["2024-05-03T12:00:00+00:00"],
            }
        ),
    )
    _gravar(
        tmp_path,
        "insolvencia/2024.parquet",
        pd.DataFrame(
            {
                "cnpj": [_cnpj(raiz)],
                "rotulo": ["recuperacao_judicial"],
                "assunto": ["Pedido de RJ"],
                "referencia": ["2024-06-01"],
                "conhecido_em": ["2024-06-02"],
                "origem_coletada_em": ["2024-06-03T12:00:00+00:00"],
            }
        ),
    )
    _gravar(
        tmp_path,
        "trocas_de_auditor/trocas.parquet",
        pd.DataFrame(
            {
                "cnpj": [_cnpj(raiz)],
                "efetiva_em": ["2024-01-01"],
                "conhecido_em": ["2024-01-10"],
                "anterior": ["Firma A"],
                "novo": ["Firma B"],
            }
        ),
    )
    _gravar(
        tmp_path,
        "cnpj_situacao_especial/2024-07.parquet",
        pd.DataFrame(
            {
                "cnpj": ["12345678000100"],
                "rotulo": ["falencia"],
                "situacao_especial": ["FALIDO"],
                "data_situacao_especial": ["2024-07-05"],
                "mes_do_retrato": ["2024-07"],
                "disponivel_em": [pd.Timestamp("2024-07-31").date()],
                "origem_coletada_em": ["2024-07-10T12:00:00+00:00"],
            }
        ),
    )
    _gravar(
        tmp_path,
        "rede/identificadores.parquet",
        pd.DataFrame(
            {
                "id_entidade": ["E1", "E1"],
                "sistema": ["cnpj_raiz", "ticker"],
                "valor": [raiz, "ABCD3"],
                "desde": [None, None],
                "ate": [None, None],
                "publico_em": pd.to_datetime(["2010-01-01", "2010-01-01"]),
            }
        ),
    )
    achados = pd.DataFrame(
        {
            "regra": ["R8"],
            "cnpj": [_cnpj(raiz)],
            "porque": ["Entregou com atraso"],
            "referencia": ["2024-03-31"],
            "valido_desde": ["2024-04-20T15:00:00+00:00"],
            "calculado_em": ["2024-04-21T15:00:00+00:00"],
        }
    )
    with conectar(tmp_path, extras={"achados_de_qualidade": achados}) as con:
        eventos = con.execute("SELECT * FROM eventos_da_rede ORDER BY publico_em").df()
    assert list(eventos["tabela"]) == [
        "trocas_de_auditor",
        "achados_de_qualidade",
        "eventos",
        "insolvencia",
        "cnpj_situacao_especial",
    ]
    assert list(eventos["evento"]) == [
        "troca_de_auditor",
        "R8",
        "fato_relevante",
        "recuperacao_judicial",
        "falencia",
    ]
    assert set(eventos["raiz"]) == {raiz}
    assert set(eventos["id_entidade"]) == {"E1"}
    assert list(eventos["publico_em"].astype("datetime64[ns]")) == list(
        pd.to_datetime(
            ["2024-01-10", "2024-04-20", "2024-05-02", "2024-06-02", "2024-07-31"]
        )
    )
    assert eventos.loc[0, "detalhe"] == "Firma A → Firma B"


def test_eventos_da_rede_sem_nenhuma_fonte_fica_vazia(tmp_path):
    with conectar(tmp_path) as con:
        assert con.execute("SELECT count(*) FROM eventos_da_rede").fetchone() == (0,)


def test_sem_o_fim_futuro_so_mexe_na_situacao_da_ligacao():
    """A `situacao` de um cadastro (ATIVO, CANCELADA) não é a da ligação: fica como veio."""
    cadastro = pd.DataFrame(
        {"situacao": ["CANCELADA"], "ate": pd.to_datetime(["2023-01-01"])}
    )
    ligacao = cadastro.assign(situacao="encerrada", encerrada_por="fonte")
    assert sem_o_fim_futuro(cadastro)["situacao"].tolist() == ["CANCELADA"]
    assert sem_o_fim_futuro(cadastro)["ate"].isna().all()
    assert sem_o_fim_futuro(ligacao)["situacao"].tolist() == ["vigente"]
    assert sem_o_fim_futuro(ligacao)["encerrada_por"].isna().all()


def test_memoria_e_threads(tmp_path):
    with conectar(tmp_path, memoria="256MB", threads=2) as con:
        threads = con.execute("SELECT current_setting('threads')").fetchone()
        fuso = con.execute("SELECT current_setting('TimeZone')").fetchone()
        barra = con.execute("SELECT current_setting('enable_progress_bar')").fetchone()
    assert threads == (2,)
    assert fuso == ("UTC",)
    assert barra == (False,)


# --- o mapa das tabelas: cada tabela do dicionário tem lugar na porta ou um motivo para não ter ---


def test_toda_tabela_tem_arquivo_ou_motivo():
    lugares = [set(ARQUIVOS), set(CONFERIDAS), set(FORA_DA_PORTA)]
    assert set.union(*lugares) == set(TABELAS)
    assert sum(len(lugar) for lugar in lugares) == len(TABELAS)  # cada uma num lugar só
    assert all(motivo.strip() for motivo in FORA_DA_PORTA.values())


@pytest.mark.parametrize("nome", sorted(ARQUIVOS))
def test_arquivo_bate_com_o_dicionario(nome):
    """A pasta que a porta lê é a que o dicionário diz em `onde` (um lugar só para cada verdade)."""
    onde = TABELAS[nome].onde
    pastas = [p for p in ARQUIVOS[nome].split("/")[:-1] if "*" not in p]
    assert f"<acervo>/base/{pastas[0]}/" in onde, nome
    assert all(p in onde for p in pastas), nome


def test_o_modulo_tem_o_nome_do_arquivo():
    """`base/porta/duckdb.py` não esconde o pacote `duckdb` de verdade."""
    assert porta_duckdb.duckdb.__name__ == "duckdb"


def test_conferida_lida_do_repositorio(tmp_path):
    """As tabelas conferidas à mão vêm do CSV do repositório, com a data da conferência."""
    with conectar(tmp_path) as con:
        linhas, conferidas_em = con.execute(
            "SELECT count(*), min(coletado_em) FROM emissores_antigos"
        ).fetchone()
    assert linhas > 0
    assert isinstance(conferidas_em, date)
