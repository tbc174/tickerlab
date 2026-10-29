"""As conferências por CNPJ que a ficha do Ficha Clara mostra (linha 525 da fila; Ficha Clara, etapa 6).

Um arquivo SQLite só de leitura, montado em casa a partir das tabelas da base, para o portal abrir sem DuckDB
nem Parquet (o mesmo jeito dos contratos do PNCP). Uma seção por tema na ficha, e cada fonte diz o que é:
- **consta**: a raiz tem linhas vigentes na fonte (`registros`, até `LINHAS_POR_FONTE`, as mais novas antes);
- **não consta**: a fonte está no arquivo (`meta.estado`, com a data até onde foi conferida) e a raiz não;
- **não conferido**: a fonte não está no arquivo. A ficha nunca confunde isso com "não consta".

**Vigente.** Nas tabelas de retratos (sanções, licenças e incentivos), o valor mais novo de cada registro já
público no dia da montagem (`como_era_em`) e só se ainda consta na fonte. Na dívida ativa, o retrato mais novo
já público de cada tipo de dívida. Nada do futuro: a linha que ainda não era pública fica de fora.

**Sem pessoa física.** A linha marcada `trata_como_pessoa` (empresário individual e MEI, ADR 0075) não entra,
nem coluna de texto livre que possa levar nome (assunto, origem da informação, complemento). A ficha também não
mostra estas seções para empresário individual e MEI, para não dizer nada da pessoa nem pela ausência.

**Grupo.** As ligações por sócia pessoa jurídica do QSA vigente da vista do CNPJ (`base/rede/grupo_do_qsa.py`),
para o portal andar o grupo do mesmo jeito; sem pessoa física, sem pseudônimo e sem nome.
"""

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pandas as pd

from base.dicionario import TABELAS
from base.parquet import gravar_atomico
from base.porta import Porta, vista_do_cnpj
from base.porta.duckdb import nome_da_view
from base.porta.rede import views
from base.rede import grupo_do_qsa

ESQUEMA = "1"  # o portal recusa outro: campo novo só entra com o contrato da integração
LINHAS_POR_FONTE = 50  # por raiz e fonte; `total` diz quantas há
TEMAS = {
    "sinais": "Sanções, penalidades e dívida ativa",
    "licencas": "Licenças e registros",
    "incentivos": "Incentivos e benefícios",
}
RAIZ_DA_FONTE = "raiz"  # a fonte só traz a raiz do CNPJ (o RDE-IED)

_SANCOES = (
    "cadastro", "cnpj", "categoria", "situacao", "orgao", "uf_do_orgao", "esfera_do_orgao",
    "fundamentacao_legal", "abrangencia", "processo", "inicio", "fim", "publicado_em",
    "transito_em_julgado", "valor_multa",
)  # fmt: skip
_LICENCAS = (
    "cadastro", "cnpj", "registro", "categoria", "descricao", "situacao", "uf", "municipio",
    "concedido_em", "vence_em", "cancelado_em",
)  # fmt: skip


@dataclass(frozen=True)
class Fonte:
    """Uma tabela da base na ficha: o que mostrar dela e de onde ela vem."""

    tabela: str
    tema: str  # uma chave de `TEMAS`
    nome: str  # o que a ficha escreve
    orgao: str
    endereco: str  # a página pública da fonte, para conferir
    colunas: tuple[str, ...]  # só estas vão para o arquivo
    ordem: str  # a linha mais nova (ou maior) primeiro
    chave: str = "cnpj"  # "cnpj" (a raiz sai do CNPJ inteiro) ou `RAIZ_DA_FONTE`


FONTES = (
    Fonte("sancoes_cgu", "sinais", "Sanções do CEIS, CNEP, CEPIM e acordos de leniência", "CGU",
          "https://portaldatransparencia.gov.br/download-de-dados", _SANCOES, "inicio"),
    Fonte("ans_penalidades", "sinais", "Penalidades a operadoras de planos de saúde", "ANS",
          "https://dadosabertos.ans.gov.br/", _SANCOES, "inicio"),
    Fonte("pgfn_divida", "sinais", "Dívida ativa da União, da Previdência e do FGTS", "PGFN",
          "https://dadosabertos.pgfn.gov.br/",
          ("cnpj", "tipo_divida", "tipo_situacao", "situacao_inscricao", "ajuizado", "inscricoes",
           "valor_consolidado", "primeira_inscricao", "ultima_inscricao", "data_do_retrato"),
          "valor_consolidado"),
    Fonte("anvisa_registros", "licencas", "Autorizações de funcionamento e registros de produtos", "Anvisa",
          "https://dados.anvisa.gov.br/dados/", _LICENCAS, "concedido_em"),
    Fonte("antt_rntrc", "licencas", "Registro de transportador rodoviário de cargas (RNTRC)", "ANTT",
          "https://dados.antt.gov.br", _LICENCAS, "concedido_em"),
    Fonte("mapa_sipeagro", "licencas", "Registros de estabelecimentos agropecuários (SIPEAGRO)", "MAPA",
          "https://dados.agricultura.gov.br", _LICENCAS, "concedido_em"),
    Fonte("anatel_outorgas", "licencas", "Outorgas de serviços de telecomunicações", "Anatel",
          "https://www.anatel.gov.br/dadosabertos/", _LICENCAS, "concedido_em"),
    Fonte("anm_titulos", "licencas", "Títulos minerários (Cadastro Mineiro)", "ANM",
          "https://dadosabertos.anm.gov.br/", _LICENCAS, "concedido_em"),
    Fonte("ancine_agentes", "licencas", "Registro de agente econômico do audiovisual", "Ancine",
          "https://dados.ancine.gov.br/dados-abertos/", _LICENCAS, "concedido_em"),
    Fonte("mme_reidi", "incentivos", "Projetos de energia enquadrados no REIDI", "MME",
          "https://dadosabertos.mme.gov.br",
          ("cnpj", "projeto", "nome_do_projeto", "portaria", "uf", "municipio", "portaria_em",
           "execucao_desde", "execucao_ate", "valor_do_beneficio"),
          "portaria_em"),
    Fonte("aneel_cde", "incentivos", "Descontos tarifários pagos pela CDE", "ANEEL",
          "https://dadosabertos.aneel.gov.br",
          ("cnpj", "arquivo", "mes", "distribuidora", "classe", "grupo_tarifario", "tipo_de_desconto",
           "valor_do_desconto"),
          "mes"),
    Fonte("bcb_rde_ied", "incentivos", "Registros de investimento estrangeiro direto (RDE-IED)",
          "Banco Central", "https://dadosabertos.bcb.gov.br",
          ("codigo_rde", "uf", "pais", "ocorrencia", "mes"), "mes", RAIZ_DA_FONTE),
)  # fmt: skip

_CNPJ_LIMPO = "regexp_replace(upper(CAST(cnpj AS VARCHAR)), '[^0-9A-Z]', '', 'g')"


def _view(tabela: str) -> str:
    return '"' + nome_da_view(tabela).replace('"', '""') + '"'


def _vigentes_sql(fonte: Fonte, hoje: date) -> str:
    """As linhas vigentes da fonte no dia `hoje`, com a `raiz`, sem pessoa e já públicas."""
    dia = f"DATE '{hoje.isoformat()}'"
    raiz = (
        "upper(CAST(cnpj_basico AS VARCHAR))"
        if fonte.chave == RAIZ_DA_FONTE
        else f"left({_CNPJ_LIMPO}, 8)"
    )
    filtro_cnpj = (
        "" if fonte.chave == RAIZ_DA_FONTE else f"AND length({_CNPJ_LIMPO}) = 14"
    )
    if fonte.tabela == "pgfn_divida":
        janela = "rank() OVER (PARTITION BY tipo_divida ORDER BY data_do_retrato DESC)"
        condicao = "n = 1"
    else:
        chaves = ", ".join(c for c in TABELAS[fonte.tabela].chaves if c != "visto_em")
        janela = f"row_number() OVER (PARTITION BY {chaves} ORDER BY disponivel_em DESC, visto_em DESC)"
        condicao = "n = 1 AND consta"
    return f"""
        SELECT {raiz} AS raiz, *, CAST(disponivel_em AS DATE) AS publico_desde FROM (
            SELECT *, {janela} AS n FROM {_view(fonte.tabela)}
            WHERE CAST(disponivel_em AS DATE) <= {dia}
        )
        WHERE {condicao} AND NOT coalesce(trata_como_pessoa, false) {filtro_cnpj}
    """


def _valor(valor: object) -> object:
    """Um valor de célula em tipo de JSON: data em ISO, vazio em None."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):  # type: ignore[arg-type]
        return None
    if isinstance(valor, pd.Timestamp | datetime | date):
        return valor.isoformat()[:10]
    if isinstance(valor, bool | int | float | str):
        return valor
    return str(valor)


def _linhas_da_fonte(
    con: duckdb.DuckDBPyConnection, fonte: Fonte, hoje: date
) -> tuple[pd.DataFrame, str | None]:
    """As linhas vigentes (só as colunas da ficha e a raiz) e o dia mais novo conferido na fonte."""
    con.execute(f"CREATE OR REPLACE TEMP VIEW vigentes AS {_vigentes_sql(fonte, hoje)}")
    presentes = {linha[0] for linha in con.execute("DESCRIBE vigentes").fetchall()}
    colunas = [c for c in fonte.colunas if c in presentes]
    selecao = ", ".join(["raiz", *colunas])
    tabela = con.execute(
        f"SELECT {selecao} FROM vigentes ORDER BY raiz, {fonte.ordem} DESC NULLS LAST"
    ).df()
    dia = "data_do_retrato" if fonte.tabela == "pgfn_divida" else "visto_em"
    conferido = con.execute(
        f"SELECT max(CAST({dia} AS DATE)) FROM {_view(fonte.tabela)} "
        f"WHERE CAST(disponivel_em AS DATE) <= DATE '{hoje.isoformat()}'"
    ).fetchone()
    ultimo = conferido[0] if conferido else None
    return tabela, (ultimo.isoformat() if ultimo else None)


def _por_raiz(tabela: pd.DataFrame) -> Iterator[tuple[str, int, str]]:
    """(raiz, total, linhas em JSON) por raiz; as linhas já vêm em ordem."""
    colunas = [c for c in tabela.columns if c != "raiz"]
    for raiz, grupo in tabela.groupby("raiz", sort=True):
        linhas = [
            {c: _valor(v) for c, v in zip(colunas, linha, strict=True)}
            for linha in grupo[colunas].head(LINHAS_POR_FONTE).itertuples(index=False)
        ]
        yield str(raiz), len(grupo), json.dumps(linhas, ensure_ascii=False)


def _criar(banco: sqlite3.Connection) -> None:
    banco.executescript(
        """
        CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
        CREATE TABLE registros (
            raiz TEXT NOT NULL, tabela TEXT NOT NULL, total INTEGER NOT NULL, linhas TEXT NOT NULL,
            PRIMARY KEY (raiz, tabela)
        ) WITHOUT ROWID;
        CREATE TABLE ligacoes (socia TEXT NOT NULL, empresa TEXT NOT NULL, qualificacao TEXT, entrada_em TEXT);
        """
    )


def _gravar_ligacoes(banco: sqlite3.Connection, vista: Path) -> dict | None:
    """As ligações do QSA vigente da vista; None se a vista não chegou."""
    manifesto = vista_do_cnpj.manifesto(vista)
    if manifesto is None:
        return None
    total = 0
    for parte in vista_do_cnpj.participacoes(vista):
        linhas = grupo_do_qsa.ligacoes(parte)
        banco.executemany(
            "INSERT INTO ligacoes VALUES (?, ?, ?, ?)",
            [(v.socia, v.empresa, v.qualificacao, v.entrada_em) for v in linhas],
        )
        total += len(linhas)
    banco.execute("CREATE INDEX ligacoes_da_socia ON ligacoes (socia)")
    banco.execute("CREATE INDEX ligacoes_da_empresa ON ligacoes (empresa)")
    return {
        "retrato": manifesto.get("mes"),
        "disponivel_em": manifesto.get("disponivel_em"),
        "ligacoes": total,
    }


def montar(
    base: Path,
    destino: Path,
    vista: Path | None = None,
    agora: datetime | None = None,
) -> dict:
    """Grava o arquivo das conferências em `destino` (troca no fim) e devolve o estado gravado.

    Só entra a fonte que tem arquivo na `base`: a que falta fica "não conferida" na ficha.
    """
    agora = agora or datetime.now(UTC)
    hoje = agora.date()
    estado: dict = {
        "esquema": ESQUEMA,
        "gerado_em": agora.isoformat(),
        "temas": TEMAS,
        "fontes": [],
    }

    def gravar(caminho: Path) -> None:
        caminho.unlink(missing_ok=True)
        banco = sqlite3.connect(caminho)
        try:
            _criar(banco)
            with Porta(base) as porta:
                existem = views(porta.con)
                for fonte in FONTES:
                    if nome_da_view(fonte.tabela) not in existem:
                        continue
                    tabela, conferido = _linhas_da_fonte(porta.con, fonte, hoje)
                    linhas = list(_por_raiz(tabela))
                    banco.executemany(
                        "INSERT INTO registros VALUES (?, ?, ?, ?)",
                        [(raiz, fonte.tabela, total, js) for raiz, total, js in linhas],
                    )
                    estado["fontes"].append(
                        {
                            "tabela": fonte.tabela, "tema": fonte.tema, "nome": fonte.nome,
                            "orgao": fonte.orgao, "endereco": fonte.endereco,
                            "conferido_ate": conferido, "empresas": len(linhas),
                            "registros": len(tabela),
                        }
                    )  # fmt: skip
            estado["grupo"] = _gravar_ligacoes(banco, vista) if vista else None
            banco.executemany(
                "INSERT INTO meta VALUES (?, ?)",
                [
                    ("schema", ESQUEMA),
                    ("estado", json.dumps(estado, ensure_ascii=False)),
                ],
            )
            banco.commit()
        finally:
            banco.close()

    destino.parent.mkdir(parents=True, exist_ok=True)
    gravar_atomico(destino, gravar)
    return estado
