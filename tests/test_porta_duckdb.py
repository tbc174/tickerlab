"""A porta em DuckDB: uma view por tabela, os apelidos das três datas e a versão antiga servida por
vista (ADR 0077, itens 8 e 9; plano da rede, PR 4, tarefa 4.1, D9 e D12)."""

import json
import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base.contrato import contrato_da_tabela
from base.dicionario import DATA, MOMENTO, NUMERO, REAIS_EXATOS, TABELAS, TEXTO, Tabela
from base.porta import Porta
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


def test_linhas_de_pessoa_entram_no_contrato_so_quando_existem():
    sem = contrato_da_tabela("fatos", FATOS)
    com = contrato_da_tabela(
        "fatos", replace(FATOS, linhas_de_pessoa="trata_como_pessoa")
    )
    assert "linhas_de_pessoa" not in sem
    assert com["linhas_de_pessoa"] == "trata_como_pessoa"


def test_linhas_de_pessoa_apontam_coluna_da_propria_tabela_sem_pessoa():
    """A marca só faz sentido numa tabela de empresas (`pessoa` falso) e numa coluna que ela tem."""
    marcadas = {n: t for n, t in TABELAS.items() if t.linhas_de_pessoa}
    assert "pgfn_divida" in marcadas
    for nome, tabela in marcadas.items():
        assert tabela.linhas_de_pessoa in tabela.colunas, nome
        assert not tabela.pessoa, nome


# --- as linhas de pessoa ficam fora da porta (ADR 0075 depois da virada de 5/11/2026) -------------

DIVIDAS = _tabela(
    colunas={
        "id": ("Identificador", TEXTO),
        "trata_como_pessoa": ("Empresário individual ou MEI (ADR 0075)", TEXTO),
        "publicado_em": ("Entrega", DATA),
    },
    datas={"publico_em": "publicado_em"},
    linhas_de_pessoa="trata_como_pessoa",
)


def _dividas(**colunas: list) -> pd.DataFrame:
    dias = pd.to_datetime(["2024-01-02"] * len(colunas["id"]))
    return pd.DataFrame({"publicado_em": dias, **colunas})


def _porta_das_dividas(pasta, tabela: Tabela = DIVIDAS):
    return conectar(
        pasta,
        tabelas={"dividas": tabela},
        arquivos={"dividas": "dividas/*.parquet"},
        contratos=pasta / "contratos",
    )


def test_view_esconde_as_linhas_marcadas_como_pessoa(tmp_path):
    """A linha do empresário individual e do MEI não sai da porta, nem na vista da versão; a linha com
    a marca vazia também fica fora (na dúvida, é pessoa)."""
    _gravar(
        tmp_path,
        "dividas/2024.parquet",
        _dividas(
            id=["empresa", "mei", "sem_marca"], trata_como_pessoa=[False, True, None]
        ),
    )
    with _porta_das_dividas(tmp_path) as con:
        servidas = con.execute("SELECT id FROM dividas ORDER BY id").fetchall()
        na_versao = con.execute(
            f"SELECT id FROM {nome_da_view('dividas', '1')} ORDER BY id"
        ).fetchall()
    assert servidas == [("empresa",)]
    assert na_versao == servidas


def test_sem_a_coluna_da_pessoa_a_view_nao_serve_linha_nenhuma(tmp_path):
    """Sem a marca no arquivo não dá para separar empresa de pessoa: o conservador é não servir."""
    _gravar(tmp_path, "dividas/2024.parquet", _dividas(id=["empresa"]))
    with _porta_das_dividas(tmp_path) as con:
        assert con.execute("SELECT count(*) FROM dividas").fetchone() == (0,)


def test_tabela_sem_a_marca_de_pessoa_serve_toda_linha(tmp_path):
    """A marca só vale para a tabela que a declara: as outras seguem servindo tudo."""
    _gravar(
        tmp_path,
        "dividas/2024.parquet",
        _dividas(id=["a", "b"], trata_como_pessoa=[True, True]),
    )
    with _porta_das_dividas(tmp_path, replace(DIVIDAS, linhas_de_pessoa="")) as con:
        assert con.execute("SELECT count(*) FROM dividas").fetchone() == (2,)


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


def test_arquivos_temporarios_nao_dependem_da_pasta_atual(tmp_path, monkeypatch):
    """Regressão de 20 e 21/10: na noite o DuckDB tentou criar `.tmp` na pasta atual (sem permissão)."""
    atual = tmp_path / "atual"
    atual.mkdir()
    (atual / ".tmp").write_text("um arquivo no lugar da pasta: criar `.tmp` falharia")
    monkeypatch.chdir(atual)
    temporaria = tmp_path / "temporaria"
    with conectar(tmp_path, memoria="200MB", threads=1, temporaria=temporaria) as con:
        # ordena mais do que cabe na memória: o DuckDB precisa despejar em arquivo temporário
        linhas = con.execute(
            "SELECT count(*) FROM (SELECT i, md5(i::VARCHAR) AS h FROM range(12000000) t(i) ORDER BY h)"
        ).fetchone()
        pasta = con.execute("SELECT current_setting('temp_directory')").fetchone()
    assert linhas == (12000000,)
    assert pasta is not None and Path(pasta[0]) == temporaria
    assert (atual / ".tmp").is_file()  # nada foi criado na pasta atual


def test_pasta_temporaria_padrao_e_a_do_sistema(tmp_path):
    with conectar(tmp_path) as con:
        pasta = con.execute("SELECT current_setting('temp_directory')").fetchone()
    assert pasta is not None
    assert Path(pasta[0]) == Path(tempfile.gettempdir()) / "tickerlab-duckdb"


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


# --- ler_pagina e contar: a consulta aberta pela API e pelo site (virada de 5/11, fase 1, PR 3) ---
SALDOS = _tabela(
    colunas={
        "cnpj": ("CNPJ", TEXTO),
        "ano": ("Ano", NUMERO),
        "valor": ("Saldo", REAIS_EXATOS),
        "disponivel_em": ("Público em", DATA),
    },
    chaves=("cnpj", "ano"),
    datas={"publico_em": "disponivel_em"},
)
# revisão gravada como linha nova da mesma chave, como a ANS e a Anatel (`base/setoriais/revisoes.py`)
REVISADOS = _tabela(
    colunas={
        "cnpj": ("CNPJ", TEXTO),
        "mes": ("Mês", TEXTO),
        "valor": ("Valor", NUMERO),
        "visto_em": ("Visto em", DATA),
    },
    chaves=("cnpj", "mes", "visto_em"),
    datas={"publico_em": "visto_em"},
)


def _porta_paginada(pasta) -> Porta:
    # dois arquivos fora de ordem: a página só é estável se a ordem vem das chaves, não do arquivo
    _gravar(
        pasta,
        "saldos/2024.parquet",
        pd.DataFrame(
            {
                "cnpj": ["B", "A", "C"],
                "ano": [2024, 2024, 2024],
                "valor": [20.0, 10.0, 30.0],
                "disponivel_em": pd.to_datetime(
                    ["2024-06-30", "2024-03-01", "2024-06-30"]
                ),
            }
        ),
    )
    _gravar(
        pasta,
        "saldos/2023.parquet",
        pd.DataFrame(
            {
                "cnpj": ["A", "B"],
                "ano": [2023, 2023],
                "valor": [1.0, 2.0],
                "disponivel_em": pd.to_datetime(["2024-01-15", "2024-01-15"]),
            }
        ),
    )
    _gravar(
        pasta,
        "revisados/tudo.parquet",
        pd.DataFrame(
            {
                "cnpj": ["A", "A", "B"],
                "mes": ["2024-01"] * 3,
                "valor": [1, 2, 3],
                "visto_em": pd.to_datetime(["2024-02-10", "2024-03-10", "2024-02-10"]),
            }
        ),
    )
    return Porta(
        pasta,
        tabelas={"saldos": SALDOS, "revisados": REVISADOS},
        arquivos={"saldos": "saldos/*.parquet", "revisados": "revisados/*.parquet"},
        contratos=pasta / "contratos",
    )


def test_ler_pagina_ordena_pelas_chaves_e_corta_no_sql(tmp_path):
    """A página vem na ordem das chaves do contrato (não na do arquivo), do tamanho pedido; a seguinte
    continua de onde a anterior parou; depois do fim vem vazia, com as mesmas colunas."""
    with _porta_paginada(tmp_path) as p:
        primeira = p.ler_pagina("saldos", limite=2)
        segunda = p.ler_pagina("saldos", limite=2, deslocamento=2)
        resto = p.ler_pagina("saldos", limite=2, deslocamento=4)
        vazia = p.ler_pagina("saldos", limite=2, deslocamento=10)
        so_valor = p.ler_pagina("saldos", colunas=["valor"], limite=5)
        assert p.contar("saldos") == 5

    def chaves(pagina):
        return list(zip(pagina["cnpj"], pagina["ano"], strict=True))

    assert chaves(primeira) == [("A", 2023), ("A", 2024)]
    assert chaves(segunda) == [("B", 2023), ("B", 2024)]
    assert chaves(resto) == [("C", 2024)]
    assert vazia.empty and list(vazia.columns) == list(primeira.columns)
    assert (
        "publico_em" in primeira.columns
    )  # a página traz os apelidos das datas, como `ler`
    # só a coluna pedida, ainda assim na ordem das chaves
    assert list(so_valor.columns) == ["valor"]
    assert list(so_valor["valor"]) == [1.0, 10.0, 2.0, 20.0, 30.0]


def test_ler_pagina_recusa_o_que_nao_existe(tmp_path):
    """Filtro ou coluna que a tabela não tem é recusado antes de virar SQL; limite e deslocamento fora
    da faixa também; tabela fora do dicionário é KeyError."""
    with _porta_paginada(tmp_path) as p:
        with pytest.raises(ValueError, match="coluna 'nao_existe'"):
            p.ler_pagina("saldos", filtros={"nao_existe": 1}, limite=10)
        with pytest.raises(ValueError, match="coluna 'nao_existe'"):
            p.ler_pagina("saldos", colunas=["nao_existe"], limite=10)
        with pytest.raises(ValueError, match="coluna 'nao_existe'"):
            p.contar("saldos", filtros={"nao_existe": 1})
        with pytest.raises(ValueError, match="limite"):
            p.ler_pagina("saldos", limite=0)
        with pytest.raises(ValueError, match="deslocamento"):
            p.ler_pagina("saldos", limite=1, deslocamento=-1)
        with pytest.raises(KeyError):
            p.ler_pagina("nao_existe", limite=1)


def test_ler_pagina_e_contar_respeitam_como_era_em_e_os_filtros(tmp_path):
    """ "Como era em D" só enxerga o que já era público em D, e `contar` conta exatamente as linhas
    que as páginas trazem, com os mesmos filtros."""
    with _porta_paginada(tmp_path) as p:
        em_marco = p.ler_pagina("saldos", como_era_em="2024-03-01", limite=10)
        total_em_marco = p.contar("saldos", como_era_em="2024-03-01")
        antes = p.contar("saldos", como_era_em="2023-12-31")
        so_a = p.ler_pagina("saldos", filtros={"cnpj": "A"}, limite=10)
        total_a = p.contar("saldos", filtros={"cnpj": "A"})
        total_a_em_janeiro = p.contar(
            "saldos", filtros={"cnpj": "A"}, como_era_em="2024-01-31"
        )
        # `ao_menos` continua valendo, junto com os filtros
        grandes = p.contar("saldos", ao_menos={"valor": 10}, filtros={"ano": 2024})
    assert list(zip(em_marco["cnpj"], em_marco["ano"], strict=True)) == [
        ("A", 2023),
        ("A", 2024),
        ("B", 2023),
    ]
    assert total_em_marco == 3 and antes == 0
    assert list(so_a["ano"]) == [2023, 2024] and total_a == 2
    assert total_a_em_janeiro == 1
    assert grandes == 3


def test_contar_com_como_era_em_fica_so_com_a_revisao_mais_nova(tmp_path):
    """Numa foto de D, de cada chave fica a revisão mais nova já pública (como em `ler`): `contar`
    conta depois desse corte, senão o total não bate com as páginas."""
    with _porta_paginada(tmp_path) as p:
        tudo = p.contar("revisados")
        fevereiro = p.ler_pagina("revisados", como_era_em="2024-02-28", limite=10)
        marco = p.ler_pagina("revisados", como_era_em="2024-03-31", limite=10)
        totais = (
            p.contar("revisados", como_era_em="2024-02-28"),
            p.contar("revisados", como_era_em="2024-03-31"),
        )
    assert tudo == 3
    assert list(zip(fevereiro["cnpj"], fevereiro["valor"], strict=True)) == [
        ("A", 1),
        ("B", 3),
    ]
    assert list(zip(marco["cnpj"], marco["valor"], strict=True)) == [("A", 2), ("B", 3)]
    assert totais == (len(fevereiro), len(marco)) == (2, 2)


def test_tipos_diz_o_que_e_dia_o_que_e_momento_e_o_que_e_texto(tmp_path):
    """Quem serve a tabela em JSON ou CSV separa o dia (`DATE`), o momento e o texto pelos tipos do
    DuckDB, sem ler linha nenhuma; o apelido `publico_em` é sempre um dia."""
    with _porta_paginada(tmp_path) as porta:
        tipos = porta.tipos("saldos")
        assert list(tipos) == porta.colunas("saldos")
    assert set(tipos) == set(SALDOS.colunas) | {"publico_em"}
    assert tipos["cnpj"] == "VARCHAR"
    assert tipos["ano"] == "BIGINT"
    assert tipos["valor"] == "DOUBLE"
    assert tipos["disponivel_em"].startswith("TIMESTAMP")  # o arquivo guarda o momento
    assert tipos["publico_em"] == "DATE"  # o apelido entrega só o dia


REPETIDOS = _tabela(
    colunas={
        "cnpj": ("CNPJ", TEXTO),
        "valor": ("Valor", NUMERO),
        "nota": ("Nota", TEXTO),
        "disponivel_em": ("Público em", DATA),
    },
    chaves=(
        "cnpj",
    ),  # a chave do contrato que se repete na base (negociacoes, controladas...)
    datas={"publico_em": "disponivel_em"},
)
LINHAS_EM_LOTES = 5_000  # mais que dois vetores do DuckDB (2.048 linhas): vários lotes


def _porta_com_chave_repetida(pasta) -> Porta:
    # a mesma chave em vários arquivos e fora de ordem, como na base real
    for parte, valores in enumerate([[3.0, 1.0], [2.0, 5.0], [4.0]]):
        _gravar(
            pasta,
            f"repetidos/{parte}.parquet",
            pd.DataFrame(
                {
                    "cnpj": ["A"] * len(valores),
                    "valor": valores,
                    "nota": ["x"] * len(valores),
                    "disponivel_em": pd.to_datetime(["2024-01-15"] * len(valores)),
                }
            ),
        )
    _gravar(
        pasta,
        "muitos/tudo.parquet",
        pd.DataFrame(
            {
                "cnpj": [f"C{i % 7}" for i in range(LINHAS_EM_LOTES)],
                "valor": [float(LINHAS_EM_LOTES - i) for i in range(LINHAS_EM_LOTES)],
                "nota": ["y"] * LINHAS_EM_LOTES,
                "disponivel_em": pd.to_datetime(
                    ["2024-01-15", "2025-01-15"] * (LINHAS_EM_LOTES // 2)
                ),
            }
        ),
    )
    return Porta(
        pasta,
        tabelas={"repetidos": REPETIDOS, "muitos": REPETIDOS},
        arquivos={"repetidos": "repetidos/*.parquet", "muitos": "muitos/*.parquet"},
        contratos=pasta / "contratos",
    )


def test_ler_pagina_desempata_a_chave_repetida_pelas_outras_colunas(tmp_path):
    """Regressão (revisão do PR 3): com a chave repetida, cada página era uma consulta com empate, e o
    DuckDB não repete a ordem entre empatadas; o CSV de 5.000 em 5.000 perdia umas linhas e repetia
    outras, com o total certo. A ordem total (chaves e depois as outras colunas) percorre a tabela
    inteira, sem repetir, e do mesmo jeito em toda leitura."""
    with _porta_com_chave_repetida(tmp_path) as p:
        uma_a_uma = pd.concat(
            [p.ler_pagina("repetidos", limite=1, deslocamento=k) for k in range(5)]
        )
        inteira = p.ler("repetidos")
        so_valor = p.ler_pagina("repetidos", colunas=["valor"], limite=10)
    assert list(uma_a_uma["valor"]) == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert sorted(uma_a_uma["valor"]) == sorted(inteira["valor"])
    assert list(so_valor["valor"]) == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_ler_em_lotes_traz_numa_consulta_o_que_as_paginas_trazem(tmp_path):
    """Os lotes, juntos, são as primeiras `limite` linhas na ordem de `ler_pagina`, sem `OFFSET`;
    `como_era_em` e os filtros valem do mesmo jeito; depois do último lote não vem nada."""
    with _porta_com_chave_repetida(tmp_path) as p:
        lotes = list(p.ler_em_lotes("muitos", limite=LINHAS_EM_LOTES))
        juntos = pd.concat(lotes, ignore_index=True)
        paginas = p.ler_pagina("muitos", limite=LINHAS_EM_LOTES)
        cortados = pd.concat(p.ler_em_lotes("muitos", limite=10), ignore_index=True)
        em_2024 = pd.concat(
            p.ler_em_lotes(
                "muitos",
                como_era_em="2024-12-31",
                filtros={"cnpj": "C1"},
                colunas=["cnpj", "valor"],
                limite=LINHAS_EM_LOTES,
            ),
            ignore_index=True,
        )
        assert p.contar("muitos", como_era_em="2024-12-31", filtros={"cnpj": "C1"}) == (
            len(em_2024)
        )
        with pytest.raises(ValueError, match="limite"):
            next(p.ler_em_lotes("muitos", limite=0))
    assert len(lotes) > 1
    pd.testing.assert_frame_equal(juntos, paginas)
    pd.testing.assert_frame_equal(cortados, paginas.head(10))
    assert list(em_2024.columns) == ["cnpj", "valor"]
    assert set(em_2024["cnpj"]) == {"C1"} and em_2024["valor"].is_monotonic_increasing
