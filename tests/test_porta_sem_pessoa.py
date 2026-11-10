"""Nenhuma tabela ou view que a porta serve para fora devolve linha de pessoa (linha 787, ADR 0075).

Duas travas:

- **o comportamento:** um acervo de mentira com MEI, empresário individual, natureza não informada e
  pessoa na rede (todos fictícios); nenhuma view da conexão devolve a raiz, o nome ou o id da pessoa;
- **o contrato:** toda tabela da consulta em lote (`pode_consultar`) com coluna de CNPJ tem a marca de
  pessoa (`linhas_de_pessoa`), é da rede (filtrada na porta) ou está no inventário congelado abaixo, que
  a fila 789 confere uma a uma. O inventário só encolhe: tabela nova sem a marca falha aqui.
"""

import re
from pathlib import Path

import pandas as pd
import pytest

from base.dicionario import TABELAS
from base.dossie import pode_consultar
from base.porta.duckdb import ARQUIVOS, conectar

RAIZ_DO_MEI, RAIZ_SEM_MARCA, RAIZ_DA_EMPRESA = "90000001", "90000002", "12345678"
EMPRESA_A, EMPRESA_B, ORGAO = "E" + "a" * 20, "E" + "b" * 20, "E" + "f" * 20
ENTIDADE_MEI, SEM_NATUREZA = "E" + "c" * 20, "E" + "d" * 20
PESSOA = "P" + "e" * 20
NOME_FICTICIO = "Nome Ficticio de Exemplo"
# o que não pode aparecer em linha nenhuma: as raízes de quem é (ou pode ser) pessoa, o nome e o id P
DE_PESSOA = (RAIZ_DO_MEI, RAIZ_SEM_MARCA, NOME_FICTICIO, PESSOA)

# a rede não tem a marca por linha: a porta a filtra pela `trata_como_pessoa` das entidades
DA_REDE = frozenset({"entidades", "ligacoes", "identificadores"})
COLUNA_DE_CNPJ = re.compile(r"cnpj|raiz|cpf")
# Inventário de 10/11/2026 (linha 787): consultáveis com coluna de CNPJ e sem a marca de pessoa. A maior
# parte é de quem tem registro na CVM ou no BCB, mas nenhuma foi conferida; a fila 789 confere uma a uma
# (marca na montagem, sai da consulta em lote ou fica aqui com o motivo). Só encolhe.
AINDA_SEM_A_MARCA = frozenset(
    {
        "anatel_acessos",
        "aneel_samp",
        "anm_cfem_arrecadacao",
        "anm_sigbm_barragens",
        "anp_concessionarios",
        "auditores",
        "carteiras_bloco_8",
        "carteiras_dos_fundos",
        "cda_cotas",
        "cnpj_empresas_historico",
        "cnpj_simples_historico",
        "codigos_invalidos",
        "controladas",
        "cvm_fiagro",
        "debentures_assembleias",
        "demonstracoes_como_era",
        "dmpl_como_era",
        "emissores",
        "eventos",
        "fca_geral",
        "fidc_informe",
        "fre_capital_social",
        "fre_comites",
        "fre_conselho",
        "fre_distribuicao_capital",
        "fre_diversidade",
        "fre_empregados",
        "fre_remuneracao",
        "fre_remuneracao_extremos",
        "ifdata_cadastro",
        "insolvencia",
        "ma_candidatos",
        "ma_regua",
        "negociacoes",
        "noticias_fatos",
        "ofertas_antigas",
        "ofertas_resolucao_160",
        "painel_dos_fundos",
        "pareceres_dfp",
        "pareceres_itr",
        "processos_nas_notas",
        "processos_partes",
        "ratings",
        "release_x_oficial",
        "rotulos_atraso",
        "securitizacao_cedente_devedor",
        "securitizacao_certificados",
        "sus_ambulatorial",
        "sus_internacoes",
        "tickers_no_tempo",
        "trocas_de_auditor",
        "valores_mobiliarios",
    }
)
COM_A_MARCA = sorted(
    nome
    for nome, tabela in TABELAS.items()
    if tabela.linhas_de_pessoa and nome in ARQUIVOS
)


def _gravar(pasta: Path, caminho: str, tabela: pd.DataFrame) -> None:
    arquivo = pasta / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(arquivo, index=False)


def _caminho(padrao: str) -> str:
    """Um arquivo concreto que o padrão de `ARQUIVOS` acha (`pgfn_divida/*/*.parquet` → `x/x`)."""
    return padrao.replace("*", "x")


def _com_a_marca(nome: str) -> pd.DataFrame:
    """Toda coluna do contrato (texto qualquer) e três linhas: a empresa (marca falsa), o MEI
    (verdadeira) e a marca vazia (na dúvida, é pessoa)."""
    tabela = TABELAS[nome]
    cnpjs = [
        f"{RAIZ_DA_EMPRESA}000100",
        f"{RAIZ_DO_MEI}000100",
        f"{RAIZ_SEM_MARCA}000100",
    ]
    linhas = {coluna: ["x"] * len(cnpjs) for coluna in tabela.colunas}
    linhas.update(
        {
            "cnpj": cnpjs,
            "cnpj_basico": [c[:8] for c in cnpjs],
            tabela.datas["publico_em"]: ["2024-07-31"] * len(cnpjs),
            tabela.linhas_de_pessoa: [False, True, None],
        }
    )
    return pd.DataFrame(linhas)


def _gravar_acervo_com_pessoa(pasta: Path) -> None:
    for nome in COM_A_MARCA:
        _gravar(
            pasta,
            _caminho(ARQUIVOS[nome]),
            _com_a_marca(nome),
        )
    _gravar(
        pasta,
        ARQUIVOS["entidades"],
        pd.DataFrame(
            {
                "id_entidade": [EMPRESA_A, EMPRESA_B, ENTIDADE_MEI, SEM_NATUREZA],
                "tipo": ["empresa"] * 4,
                "nome": ["Alfa Exemplo S.A.", "Beta Exemplo Ltda", None, NOME_FICTICIO],
                "trata_como_pessoa": [False, False, True, True],
                "publico_em": pd.to_datetime(["2020-01-01"] * 4),
            }
        ),
    )
    arestas = [
        (EMPRESA_A, EMPRESA_B, "controlada_de"),
        (PESSOA, EMPRESA_A, "socio_de"),
        (ENTIDADE_MEI, ORGAO, "sancionada_por"),
        (SEM_NATUREZA, ORGAO, "deve_a"),
    ]
    _gravar(
        pasta,
        ARQUIVOS["ligacoes"],
        pd.DataFrame(
            {
                "de": [a[0] for a in arestas],
                "para": [a[1] for a in arestas],
                "tipo": [a[2] for a in arestas],
                "publico_em": pd.to_datetime(["2020-01-02"] * len(arestas)),
            }
        ),
    )
    donos = [EMPRESA_A, ENTIDADE_MEI, SEM_NATUREZA]
    _gravar(
        pasta,
        ARQUIVOS["identificadores"],
        pd.DataFrame(
            {
                "id_entidade": donos,
                "sistema": ["cnpj_raiz"] * len(donos),
                "valor": [RAIZ_DA_EMPRESA, RAIZ_DO_MEI, RAIZ_SEM_MARCA],
                "publico_em": pd.to_datetime(["2010-01-01"] * len(donos)),
            }
        ),
    )


def _linhas_de_pessoa(con, view: str) -> list[str]:
    linhas = con.execute(f'SELECT * FROM "{view}"').fetchall()
    return [
        f"{view}: {valor}"
        for linha in linhas
        for valor in linha
        if valor is not None and any(marca in str(valor) for marca in DE_PESSOA)
    ]


def test_nenhuma_view_da_porta_devolve_pessoa(tmp_path):
    """Varre toda view da conexão (tabelas, versões e `eventos_da_rede`): nenhuma raiz de MEI ou de
    marca vazia, nenhum nome de entidade tratada como pessoa, nenhum id de pessoa (P...)."""
    _gravar_acervo_com_pessoa(tmp_path)
    with conectar(tmp_path) as con:
        views = [
            nome
            for (nome,) in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_type = 'VIEW'"
            ).fetchall()
        ]
        assert {*COM_A_MARCA, *DA_REDE, "eventos_da_rede"} <= set(views)
        vazadas = [linha for view in views for linha in _linhas_de_pessoa(con, view)]
        # a empresa sai: o filtro não apagou tudo
        assert con.execute("SELECT raiz FROM eventos_da_rede").fetchall() == [
            (RAIZ_DA_EMPRESA,)
        ]
    assert vazadas == []


@pytest.mark.parametrize("nome", COM_A_MARCA)
def test_tabela_com_a_marca_so_serve_a_empresa(tmp_path, nome):
    _gravar(tmp_path, _caminho(ARQUIVOS[nome]), _com_a_marca(nome))
    with conectar(tmp_path) as con:
        servidos = con.execute(f'SELECT cnpj FROM "{nome}"').fetchall()
    assert servidos == [(f"{RAIZ_DA_EMPRESA}000100",)]


def test_toda_consultavel_com_cnpj_tem_a_marca_ou_esta_no_inventario():
    """Tabela nova na consulta em lote com coluna de CNPJ nasce com a marca de pessoa. A que saiu do
    inventário (ganhou a marca ou deixou a consulta) sai daqui também."""
    sem_a_marca = {
        nome
        for nome, tabela in TABELAS.items()
        if pode_consultar(nome)
        and not tabela.linhas_de_pessoa
        and nome not in DA_REDE
        and any(COLUNA_DE_CNPJ.search(coluna) for coluna in tabela.colunas)
    }
    assert sem_a_marca == AINDA_SEM_A_MARCA


def test_a_rede_e_consultavel_so_porque_a_porta_a_filtra():
    """Se a rede sair de `ARQUIVOS` (outro caminho até o Parquet), o filtro da porta some junto."""
    assert set(ARQUIVOS) >= DA_REDE
    assert all(pode_consultar(nome) for nome in DA_REDE)
