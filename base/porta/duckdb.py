"""A base lida pelo DuckDB: uma view por tabela, com as três datas pelos apelidos e a versão antiga
do contrato servida como vista (ADR 0077, itens 8 e 9; plano da rede, PR 4, tarefa 4.1).

Nada é copiado: cada view lê os Parquets vigentes da tabela no acervo (as versões guardadas,
`2024.v1.parquet`, ficam de fora) ou a tabela conferida no repositório. Por tabela:

- `<tabela>`: as colunas como estão, mais `aconteceu_em`, `publico_em` e `coletado_em` (só as que o
  contrato dá) como **dia**. Momento em UTC vira o dia de UTC (o relógio da conexão fica em UTC);
  `publico_em` por mês vale pelo **último dia do mês** e por ano pelo último dia do ano (o
  conservador: nada é público antes de o período terminar);
- `<tabela>__v<N>`: a versão maior N. A de hoje é a mesma view; uma antiga traduz as colunas pelo
  contrato congelado (`base/contratos/v<N>/`): renomeada volta com o nome antigo, a que saiu volta
  vazia, a nova não aparece (D12: vista, nunca segunda cópia);
- `eventos_da_rede` (D9): os eventos de `eventos`, `insolvencia`, `trocas_de_auditor`,
  `cnpj_situacao_especial` e `achados_de_qualidade`, com as três datas e a entidade pela raiz do CNPJ.

`achados_de_qualidade` mora no banco do app: entra só quando quem conecta a passa em `extras`.
"""

import json
import re
from collections.abc import Mapping
from pathlib import Path

import duckdb
import pandas as pd

from base.contrato import PASTA as PASTA_DOS_CONTRATOS
from base.contrato import versao_em_numeros
from base.dicionario import TABELAS, Tabela
from base.parquet import VERSAO_GUARDADA
from base.rede.ligacoes import VIGENTE

RAIZ_DO_REPOSITORIO = Path(__file__).resolve().parents[2]
APELIDOS = ("aconteceu_em", "publico_em", "coletado_em")

# tabela → arquivos dentro de `<acervo>/base` (o `onde` do dicionário diz o mesmo; um teste confere)
ARQUIVOS: dict[str, str] = {
    "demonstracoes_como_era": "demonstracoes/*.parquet",
    "tickers_no_tempo": "fca/tickers.parquet",
    "valores_mobiliarios": "fca/valores_mobiliarios.parquet",
    "emissores": "fca/emissores.parquet",
    "codigos_invalidos": "fca/codigos_invalidos.parquet",
    "carteiras_dos_fundos": "cda/*.parquet",
    "carteiras_bloco_8": "cda_bloco_8/*.parquet",
    "cda_cotas": "cda_cotas/*.parquet",
    "fidc_informe": "fidc/informe/*/*.parquet",
    "cadastro_de_fundos": "fidc/cadastro/cad_fi.parquet",
    "painel_dos_fundos": "fundos/painel_emissor/*.parquet",
    "cobertura_dos_fundos": "fundos/cobertura.parquet",
    "buracos_dos_fundos": "fundos/buracos.parquet",
    "anac_estatistico": "setoriais/anac/*.parquet",
    "anp_vendas": "setoriais/anp/*.parquet",
    "ons_geracao": "setoriais/ons/*.parquet",
    "aneel_samp": "setoriais/aneel/*.parquet",
    "anatel_acessos": "setoriais/anatel/*.parquet",
    "ans_beneficiarios": "setoriais/ans/*.parquet",
    "susep_seguros": "setoriais/susep/*.parquet",
    "setoriais_buracos": "setoriais/buracos.parquet",
    "fre_conselho": "fre_conselho/*.parquet",
    "fre_comites": "fre_comites/*.parquet",
    "fre_remuneracao": "fre_remuneracao/*.parquet",
    "fre_remuneracao_extremos": "fre_remuneracao_extremos/*.parquet",
    "fre_diversidade": "fre_diversidade/*.parquet",
    "ofertas_antigas": "ofertas/antigas.parquet",
    "ofertas_resolucao_160": "ofertas/resolucao_160.parquet",
    "amostra_painel": "amostra/v1/painel/*.parquet",
    "ifdata_valores": "bcb/ifdata/valores/*/*.parquet",
    "ifdata_cadastro": "bcb/ifdata/cadastro/*.parquet",
    "ligacao_dos_bancos": "bcb/ifdata/ligacao_dos_bancos.parquet",
    "scr_credito": "bcb/scr/*.parquet",
    "eventos": "eventos/*.parquet",
    "negociacoes": "negociacoes/*.parquet",
    "proventos": "proventos/*.parquet",
    "eventos_de_capital": "eventos_de_capital/*.parquet",
    "insolvencia": "insolvencia/*.parquet",
    "cnpj_situacao_especial": "cnpj_situacao_especial/*.parquet",
    "pgfn_divida": "pgfn_divida/*/*.parquet",
    "ratings": "ratings/*.parquet",
    "debentures_assembleias": "debentures_assembleias/*.parquet",
    "auditores": "auditores/*.parquet",
    "trocas_de_auditor": "trocas_de_auditor/trocas.parquet",
    "curva_juros": "curva_juros/*.parquet",
    "bcb_selic_focus": "bcb_selic_focus/bcb_selic_focus.parquet",
    "noticias_fatos": "noticias_fatos/*.parquet",
    "noticias_numeros": "noticias_numeros/*.parquet",
    "controladas": "controladas/*.parquet",
    "rotulos_atraso": "rotulos_atraso/rotulos_atraso.parquet",
    "empresa_serie": "empresa_serie/empresa_serie.parquet",
    "entidades": "rede/entidades.parquet",
    "identificadores": "rede/identificadores.parquet",
    "ligacoes": "rede/ligacoes.parquet",
    "ma_assessorias": "ma/assessorias/*.parquet",
    "ma_partes": "ma/ligacao/partes.parquet",
    "ma_negocios": "ma/ligacao/negocios.parquet",
    "ma_datas": "ma/datas/negocios.parquet",
    "ma_regua": "ma/regua/negocios.parquet",
}
# tabela conferida à mão → CSV no repositório (separado por `;`)
CONFERIDAS: dict[str, str] = {
    "emissores_sem_ligacao": "base/conferidas/emissores_sem_ligacao.csv",
    "emissores_antigos": "base/conferidas/emissores_antigos.csv",
    "codigos_fora_do_fca": "base/conferidas/codigos_fora_do_fca.csv",
}
_NO_BANCO = "mora no banco do app (VPS), não no acervo: entra só por `extras`"
FORA_DA_PORTA: dict[str, str] = {
    "achados_de_qualidade": _NO_BANCO,
    "padroes_setoriais": _NO_BANCO,
    "fre_proventos": _NO_BANCO,
    "fre_eventos_de_capital": _NO_BANCO,
    "cadastro_das_companhias": (
        "não é Parquet da base: é lido do original no acervo (`base/cadastro.py::ler_cadastro`)"
    ),
}

# D9: tabela → (o evento, o detalhe), em SQL sobre as colunas dela
EVENTOS_DA_REDE: dict[str, tuple[str, str]] = {
    "eventos": ("rotulo", "assunto"),
    "insolvencia": ("rotulo", "assunto"),
    "trocas_de_auditor": ("'troca_de_auditor'", "anterior || ' → ' || novo"),
    "cnpj_situacao_especial": ("rotulo", "situacao_especial"),
    "achados_de_qualidade": ("regra", "porque"),
}
_MEMORIA = re.compile(r"^\d+(\.\d+)?\s*[KMGT]i?B$", re.IGNORECASE)


def _nome(identificador: str) -> str:
    """Um identificador do SQL entre aspas (o nome da coluna nunca vira código)."""
    return '"' + identificador.replace('"', '""') + '"'


def _texto(valor: str) -> str:
    return "'" + valor.replace("'", "''") + "'"


def nome_da_view(tabela: str, versao: str | None = None) -> str:
    """`tabela` ou, com a versão (`"1"`, `"1.2.0"`), `tabela__v<maior>`."""
    if versao is None:
        return tabela
    return f"{tabela}__v{str(versao).split('.')[0]}"


def arquivos_da_tabela(pasta: Path, padrao: str) -> list[Path]:
    """Os Parquets vigentes de `padrao` dentro de `pasta`, sem as versões guardadas."""
    return sorted(
        a
        for a in pasta.glob(padrao)
        if a.is_file() and not VERSAO_GUARDADA.search(a.with_suffix("").name)
    )


def _dia(coluna: str, granularidade: str = "dia") -> str:
    texto = f"CAST({_nome(coluna)} AS VARCHAR)"
    if granularidade == "mes":
        return f"last_day(TRY_CAST(left({texto}, 7) || '-01' AS DATE))"
    if granularidade == "ano":
        return f"make_date(TRY_CAST(left({texto}, 4) AS INTEGER), 12, 31)"
    return f"TRY_CAST(left({texto}, 10) AS DATE)"


def _colunas(con: duckdb.DuckDBPyConnection, fonte: str) -> list[str]:
    return [
        linha[0] for linha in con.execute(f"DESCRIBE SELECT * FROM {fonte}").fetchall()
    ]


def _select_com_apelidos(
    nome: str, tabela: Tabela, colunas: list[str], fonte: str
) -> str:
    trocar, somar = [], []
    for apelido, coluna in tabela.datas.items():
        granularidade = (
            tabela.granularidade_do_publico_em if apelido == "publico_em" else "dia"
        )
        expressao = (
            _dia(coluna, granularidade) if coluna in colunas else "CAST(NULL AS DATE)"
        )
        if apelido in colunas and apelido != coluna:
            raise ValueError(
                f"{nome}: a coluna `{apelido}` já existe e não é a data `{apelido}` "
                f"(o contrato aponta `{coluna}`); renomeie uma das duas"
            )
        (trocar if apelido in colunas else somar).append(
            f"{expressao} AS {_nome(apelido)}"
        )
    partes = ["*" + (f" REPLACE ({', '.join(trocar)})" if trocar else ""), *somar]
    return f"SELECT {', '.join(partes)} FROM {fonte}"


def _contratos_congelados(pasta: Path, nome: str) -> dict[int, dict]:
    congelados = {}
    for arquivo in pasta.glob(f"v*/{nome}.json"):
        maior = arquivo.parent.name[1:]
        if maior.isdigit():
            congelados[int(maior)] = json.loads(arquivo.read_text(encoding="utf-8"))
    return congelados


def _coluna_de_hoje(antiga: str, tabela: Tabela, colunas: list[str]) -> str | None:
    """O nome de hoje da coluna `antiga`, seguindo as renomeações (None se ela saiu)."""
    atual, vistas = antiga, set()
    while atual not in colunas and atual in tabela.renomeadas and atual not in vistas:
        vistas.add(atual)
        atual = tabela.renomeadas[atual]
    return atual if atual in colunas else None


def _views_das_versoes(
    con: duckdb.DuckDBPyConnection, nome: str, tabela: Tabela, contratos: Path
) -> None:
    hoje = versao_em_numeros(tabela.versao_do_contrato)[0]
    con.execute(
        f"CREATE VIEW {_nome(nome_da_view(nome, str(hoje)))} AS SELECT * FROM {_nome(nome)}"
    )
    colunas = _colunas(con, _nome(nome))
    for maior, contrato in sorted(_contratos_congelados(contratos, nome).items()):
        if maior >= hoje:
            continue
        antigas = [
            *contrato["colunas"],
            *(a for a in contrato.get("datas", {}) if a not in contrato["colunas"]),
        ]
        partes = []
        for antiga in antigas:
            atual = _coluna_de_hoje(antiga, tabela, colunas)
            partes.append(
                f"NULL AS {_nome(antiga)}"
                if atual is None
                else f"{_nome(atual)} AS {_nome(antiga)}"
            )
        con.execute(
            f"CREATE VIEW {_nome(nome_da_view(nome, str(maior)))} AS "
            f"SELECT {', '.join(partes)} FROM {_nome(nome)}"
        )


def _fonte_dos_arquivos(arquivos: list[Path]) -> str:
    lista = ", ".join(_texto(a.as_posix()) for a in arquivos)
    return f"read_parquet([{lista}], union_by_name = true)"


def _fonte_da_conferida(caminho: Path) -> str:
    return (
        f"read_csv({_texto(caminho.as_posix())}, delim = ';', header = true, quote = '\"', "
        "all_varchar = true)"
    )


def _view_de_eventos(
    con: duckdb.DuckDBPyConnection, tabelas: Mapping[str, Tabela], existem: set[str]
) -> None:
    partes = []
    for nome, (evento, detalhe) in EVENTOS_DA_REDE.items():
        if nome not in existem:
            continue
        cnpj = "upper(regexp_replace(CAST(cnpj AS VARCHAR), '[^0-9A-Za-z]', '', 'g'))"
        datas = ", ".join(
            f"{a}" if a in tabelas[nome].datas else f"CAST(NULL AS DATE) AS {a}"
            for a in APELIDOS
        )
        partes.append(
            f"SELECT {_texto(nome)} AS tabela, {cnpj} AS cnpj, left({cnpj}, 8) AS raiz, "
            f"CAST({evento} AS VARCHAR) AS evento, CAST({detalhe} AS VARCHAR) AS detalhe, "
            f"{datas} FROM {_nome(nome)}"
        )
    if not partes:
        partes.append(
            "SELECT NULL::VARCHAR AS tabela, NULL::VARCHAR AS cnpj, NULL::VARCHAR AS raiz, "
            "NULL::VARCHAR AS evento, NULL::VARCHAR AS detalhe, NULL::DATE AS aconteceu_em, "
            "NULL::DATE AS publico_em, NULL::DATE AS coletado_em WHERE false"
        )
    ids = (
        "(SELECT valor, min(id_entidade) AS id_entidade FROM identificadores "
        "WHERE sistema = 'cnpj_raiz' GROUP BY valor)"
        if "identificadores" in existem
        else "(SELECT NULL::VARCHAR AS valor, NULL::VARCHAR AS id_entidade WHERE false)"
    )
    con.execute(
        "CREATE VIEW eventos_da_rede AS SELECT e.tabela, e.cnpj, e.raiz, ids.id_entidade, "
        "e.evento, e.detalhe, e.aconteceu_em, e.publico_em, e.coletado_em "
        f"FROM ({' UNION ALL '.join(partes)}) e LEFT JOIN {ids} ids ON ids.valor = e.raiz"
    )


def conectar(
    pasta: Path,
    memoria: str | None = None,
    threads: int | None = None,
    *,
    tabelas: Mapping[str, Tabela] = TABELAS,
    arquivos: Mapping[str, str] = ARQUIVOS,
    conferidas: Mapping[str, str] = CONFERIDAS,
    contratos: Path = PASTA_DOS_CONTRATOS,
    extras: Mapping[str, pd.DataFrame] | None = None,
) -> duckdb.DuckDBPyConnection:
    """Uma conexão do DuckDB na memória com as views da base em `pasta` (`<acervo>/base`).

    `memoria` ("2GB") e `threads` limitam o DuckDB (no VPS, constantes medidas; D10). `extras`:
    tabelas que não moram no acervo (as do banco do app), como DataFrame.
    """
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'UTC'")
        con.execute(
            "SET enable_progress_bar = false"
        )  # a barra encheria os logs da noite
        if memoria is not None:
            if not _MEMORIA.match(memoria):
                raise ValueError(f"memória inválida: {memoria!r} (ex.: '2GB')")
            con.execute(f"SET memory_limit = {_texto(memoria)}")
        if threads is not None:
            con.execute(f"SET threads = {int(threads)}")
        fontes: dict[str, str] = {}
        for nome, padrao in arquivos.items():
            achados = arquivos_da_tabela(pasta, padrao)
            if achados:
                fontes[nome] = _fonte_dos_arquivos(achados)
        for nome, caminho in conferidas.items():
            if (RAIZ_DO_REPOSITORIO / caminho).is_file():
                fontes[nome] = _fonte_da_conferida(RAIZ_DO_REPOSITORIO / caminho)
        for nome, tabela in (extras or {}).items():
            con.register(f"_extra_{nome}", tabela)
            fontes[nome] = _nome(f"_extra_{nome}")
        for nome, fonte in fontes.items():
            if nome not in tabelas:
                continue
            select = _select_com_apelidos(
                nome, tabelas[nome], _colunas(con, fonte), fonte
            )
            con.execute(f"CREATE VIEW {_nome(nome)} AS {select}")
            _views_das_versoes(con, nome, tabelas[nome], contratos)
        _view_de_eventos(con, tabelas, {n for n in fontes if n in tabelas})
    except Exception:
        con.close()
        raise
    return con


# --- "como era em D" (plano, D5): o que já era público no dia e ainda valia ---------------------
def dia_de(valor: object) -> str:
    """O dia em ISO (`"2020-12-31"`), de texto, data ou momento."""
    return pd.Timestamp(valor).date().isoformat()  # type: ignore[arg-type]


def condicao_como_era(colunas: list[str], tabela: str) -> str:
    """`publico_em ≤ D` e (`ate` vazio ou `ate > D` ou, se a tabela diz, `ate_publico_em > D`: o fim
    que ainda não era público não conta), com o dia no parâmetro `$dia`."""
    if "publico_em" not in colunas:
        raise ValueError(
            f"{tabela}: sem `publico_em` no contrato, não dá para dizer como era numa data"
        )
    condicao = "publico_em <= CAST($dia AS DATE)"
    if "ate" in colunas:
        ate = _dia("ate")
        valia = f"{ate} IS NULL OR {ate} > CAST($dia AS DATE)"
        if "ate_publico_em" in colunas:
            valia += f" OR {_dia('ate_publico_em')} > CAST($dia AS DATE)"
        condicao += f" AND ({valia})"
    return condicao


def sem_o_fim_futuro(tabela: pd.DataFrame) -> pd.DataFrame:
    """Numa foto de D, o que ainda valia não mostra o fim que só veio depois: `ate` vazio e, na
    ligação, `situacao` = vigente sem `encerrada_por` (toda linha que sobra valia em D)."""
    tabela = tabela.copy()
    for coluna in ("ate", "ate_publico_em"):
        if coluna in tabela.columns:
            tabela[coluna] = tabela[coluna].mask(tabela[coluna].notna())
    if (
        "encerrada_por" in tabela.columns
    ):  # só a ligação (outras tabelas têm outra `situacao`)
        tabela["situacao"] = VIGENTE
        tabela["encerrada_por"] = None
    return tabela
