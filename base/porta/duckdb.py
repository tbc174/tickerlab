"""A base lida pelo DuckDB: uma view por tabela, com as três datas pelos apelidos e a versão antiga
do contrato servida como vista (ADR 0077, itens 8 e 9; plano da rede, PR 4, tarefa 4.1).

Nada é copiado: cada view lê os Parquets vigentes da tabela no acervo (as versões guardadas,
`2024.v1.parquet`, ficam de fora) ou a tabela conferida no repositório. Por tabela:

- `<tabela>`: as colunas como estão, mais `aconteceu_em`, `publico_em` e `coletado_em` (só as que o
  contrato dá) como **dia**. Momento em UTC vira o dia de UTC (o relógio da conexão fica em UTC);
  `publico_em` por mês vale pelo **último dia do mês** e por ano pelo último dia do ano (o
  conservador: nada é público antes de o período terminar). Se o dicionário marca `linhas_de_pessoa`
  (a coluna booleana da pessoa natural, `trata_como_pessoa` na `pgfn_divida`), a view esconde essas
  linhas (ADR 0075: nada negativo sobre pessoa sai da base), e a marca vazia também esconde; sem a
  coluna no arquivo, não serve linha nenhuma (o conservador: na dúvida, é pessoa);
- `<tabela>__v<N>`: a versão maior N. A de hoje é a mesma view; uma antiga traduz as colunas pelo
  contrato congelado (`base/contratos/v<N>/`): renomeada volta com o nome antigo, a que saiu volta
  vazia, a nova não aparece (D12: vista, nunca segunda cópia);
- `eventos_da_rede` (D9): os eventos de `eventos`, `insolvencia`, `trocas_de_auditor`,
  `cnpj_situacao_especial` e `achados_de_qualidade`, com as três datas e a entidade pela raiz do CNPJ.

`achados_de_qualidade` mora no banco do app: entra só quando quem conecta a passa em `extras`.
"""

import json
import re
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import duckdb
import pandas as pd

from base.contrato import PASTA as PASTA_DOS_CONTRATOS
from base.contrato import versao_em_numeros
from base.dicionario import TABELAS, Tabela
from base.parquet import VERSAO_GUARDADA
from base.rede.ids import PREFIXO_DE_PESSOA
from base.rede.ligacoes import VIGENTE
from base.rede.vistas import TIPOS_NEGATIVOS

RAIZ_DO_REPOSITORIO = Path(__file__).resolve().parents[2]
APELIDOS = ("aconteceu_em", "publico_em", "coletado_em")
# onde o DuckDB despeja o que não cabe na memória: sem isto ele usa `.tmp` na pasta atual, e o
# usuário do contêiner da noite não escreve em `/app` ("Failed to create directory '.tmp'", 20 e 21/10)
PASTA_TEMPORARIA = Path(tempfile.gettempdir()) / "tickerlab-duckdb"

# tabela → arquivos dentro de `<acervo>/base` (o `onde` do dicionário diz o mesmo; um teste confere)
ARQUIVOS: dict[str, str] = {
    "demonstracoes_como_era": "demonstracoes/*.parquet",
    "dmpl_como_era": "dmpl/*.parquet",
    "tickers_no_tempo": "fca/tickers.parquet",
    "valores_mobiliarios": "fca/valores_mobiliarios.parquet",
    "emissores": "fca/emissores.parquet",
    "codigos_invalidos": "fca/codigos_invalidos.parquet",
    "carteiras_dos_fundos": "cda/*.parquet",
    "carteiras_bloco_8": "cda_bloco_8/*.parquet",
    "cda_cotas": "cda_cotas/*.parquet",
    "fidc_informe": "fidc/informe/*/*.parquet",
    "cadastro_de_fundos": "fidc/cadastro/cad_fi.parquet",
    "cadastro_gestor_hist": "fidc/cadastro/hist_gestor.parquet",
    "cadastro_admin_hist": "fidc/cadastro/hist_admin.parquet",
    "registro_de_fundos": "fidc/cadastro/registro_fundo.parquet",
    "fips_registrados": "fips_registrados/*.parquet",  # só no VPS (linha 844)
    "painel_dos_fundos": "fundos/painel_*/*.parquet",  # os dois: o por empresa não tem `emissor`
    "cobertura_dos_fundos": "fundos/cobertura.parquet",
    "buracos_dos_fundos": "fundos/buracos.parquet",
    "anac_estatistico": "setoriais/anac/*.parquet",
    "anp_vendas": "setoriais/anp/*.parquet",
    "comex_cafe": "commodities/comex_cafe/*.parquet",
    "conab_cafe": "commodities/conab_cafe/*.parquet",
    "ons_geracao": "setoriais/ons/*.parquet",
    "ccee_pld": "setoriais/ccee/*.parquet",
    "ons_restricao": "setoriais/ons_restricao/*.parquet",
    "ons_capacidade": "setoriais/ons_capacidade/*.parquet",
    "anp_concessionarios": "setoriais/anp_concessionarios/*.parquet",
    "antt_siade": "setoriais/antt_siade/*.parquet",
    "comex_preco_medio": "setoriais/comex_preco_medio/*.parquet",
    "comex_urf": "setoriais/comex_urf/*.parquet",
    "comex_via": "setoriais/comex_via/*.parquet",
    "cftc_cot_agro": "setoriais/cftc/*.parquet",
    "aneel_samp": "setoriais/aneel/*.parquet",
    "anatel_acessos": "setoriais/anatel/*.parquet",
    "ans_beneficiarios": "setoriais/ans/*.parquet",
    "susep_seguros": "setoriais/susep/*.parquet",
    "setoriais_buracos": "setoriais/buracos.parquet",
    "clima_regiao_cafe": "commodities/clima_regiao_cafe/*.parquet",
    "area_cafe_municipio": "commodities/area_cafe_municipio/*.parquet",
    "fre_conselho": "fre_conselho/*.parquet",
    "fre_comites": "fre_comites/*.parquet",
    "fre_remuneracao": "fre_remuneracao/*.parquet",
    "fre_remuneracao_extremos": "fre_remuneracao_extremos/*.parquet",
    "fre_diversidade": "fre_diversidade/*.parquet",
    "fre_capital_social": "fre_capital_social/*.parquet",
    "fre_empregados": "fre_empregados/*.parquet",
    "fre_acionistas": "fre_acionistas/*.parquet",
    "fre_distribuicao_capital": "fre_distribuicao_capital/*.parquet",
    "fre_partes_relacionadas": "fre_partes_relacionadas/*.parquet",
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
    "cnpj_situacao_cadastral": "cnpj_situacao_cadastral/*.parquet",
    "cnpj_simples_historico": "cnpj_simples_historico/*.parquet",
    "cnpj_empresas_historico": "cnpj_empresas_historico/*.parquet",
    "cnpj_empresas_pj": "cnpj_empresas_pj/*.parquet",
    "cnpj_estabelecimentos_pj": "cnpj_estabelecimentos_pj/*.parquet",
    "entradas_de_socio_pj": "entradas_de_socio_pj/*.parquet",
    "pgfn_divida": "pgfn_divida/*/*.parquet",
    "sancoes_cgu": "sancoes_cgu/*.parquet",
    "ans_penalidades": "ans_penalidades/*.parquet",
    "processos_comunicacoes": "processos_comunicacoes/*.parquet",
    "processos": "processos/*.parquet",
    "processos_partes": "processos_partes/*.parquet",
    "anvisa_registros": "anvisa_registros/*.parquet",
    "anvisa_por_empresa": "anvisa_por_empresa/*.parquet",
    "receita_dirbi": "receita_dirbi/*.parquet",
    "receita_ecf_renuncia": "receita_ecf_renuncia/*.parquet",
    "sigsif_habilitados": "sigsif_habilitados/*.parquet",
    "sigsif_estabelecimentos": "sigsif_estabelecimentos/*.parquet",
    "receita_transacoes_individual": "receita_transacoes_individual/*.parquet",
    "receita_transacoes_adesao": "receita_transacoes_adesao/*.parquet",
    "antt_rntrc": "antt_rntrc/*.parquet",
    "mapa_sipeagro": "mapa_sipeagro/*.parquet",
    "anatel_outorgas": "anatel_outorgas/*.parquet",
    "anm_titulos": "anm_titulos/*.parquet",
    "ancine_agentes": "ancine_agentes/*.parquet",
    "financiamentos_bndes": "financiamentos_bndes/*.parquet",
    "financiamentos_finep": "financiamentos_finep/*.parquet",
    "cmed_precos": "cmed_precos/*.parquet",
    "ans_operadoras": "ans_operadoras/*.parquet",
    "susep_cadastro": "susep_cadastro/*.parquet",
    "mte_lista_suja": "mte_lista_suja/*.parquet",
    "ibama_embargos": "ibama_embargos/*.parquet",
    "inpi_marcas_titulares": "inpi_marcas_titulares/*.parquet",
    "inpi_patentes_depositantes": "inpi_patentes_depositantes/*.parquet",
    "inpi_desenhos_depositantes": "inpi_desenhos_depositantes/*.parquet",
    "inpi_programas_titulares": "inpi_programas_titulares/*.parquet",
    "cvm_fiagro": "cvm_fiagro/*.parquet",
    "fip_informe": "fip_informe/*.parquet",
    "fii_informe_mensal": "fii_informe_mensal/*.parquet",
    "fii_ativos": "fii_ativos/*.parquet",
    "fii_administradores": "fii_administradores/*.parquet",
    "aneel_inadimplencia": "aneel_inadimplencia/*.parquet",
    "aneel_indicadores_comerciais": "aneel_indicadores_comerciais/*.parquet",
    "ans_idss": "ans_idss/*.parquet",
    "gleif_ponte": "gleif_ponte/*.parquet",
    "cnes_estabelecimentos": "cnes_estabelecimentos/*.parquet",
    "cnes_competencias": "cnes_competencias/*.parquet",
    "sus_internacoes": "sus_internacoes/*.parquet",
    "sus_ambulatorial": "sus_ambulatorial/*.parquet",
    "anm_cfem_arrecadacao": "anm_cfem_arrecadacao/*.parquet",
    "anm_sigbm_barragens": "anm_sigbm_barragens/*.parquet",
    "anm_amb_producao_bruta": "anm_amb_producao_bruta/*.parquet",
    "anm_amb_producao_beneficiada": "anm_amb_producao_beneficiada/*.parquet",
    "anm_amb_agua_mineral": "anm_amb_agua_mineral/*.parquet",
    "tce_pe_contratos": "tce_pe_contratos/*.parquet",
    "tce_pe_aditivos": "tce_pe_aditivos/*.parquet",
    "tce_pe_licitacoes": "tce_pe_licitacoes/*.parquet",
    "tce_sp_despesas": "tce_sp_despesas/*.parquet",
    "tce_ce_contratos": "tce_ce_contratos/*.parquet",
    "tce_rs_contratos": "tce_rs_contratos/*.parquet",
    "mme_reidi": "mme_reidi/*.parquet",
    "aneel_cde": "aneel_cde/*.parquet",
    "bcb_rde_ied": "bcb_rde_ied/*.parquet",
    "sefaz_pe_beneficios": "sefaz_pe_beneficios/*.parquet",
    "sefa_pr_divida_ativa": "sefa_pr_divida_ativa/*.parquet",
    "sef_mg_divida_ativa": "sef_mg_divida_ativa/*.parquet",
    "sef_mg_parcelamentos": "sef_mg_parcelamentos/*.parquet",
    "sefaz_pe_ordem_cronologica": "sefaz_pe_ordem_cronologica/*.parquet",
    "es_ordem_cronologica": "es_ordem_cronologica/*.parquet",
    "ratings": "ratings/*.parquet",
    "debentures_assembleias": "debentures_assembleias/*.parquet",
    "auditores": "auditores/*.parquet",
    "fca_geral": "fca_geral/*.parquet",
    "pareceres_dfp": "pareceres_dfp/*.parquet",
    "pareceres_itr": "pareceres_itr/*.parquet",
    "notas_dfp": "notas_dfp/*.parquet",
    "processos_nas_notas": "processos_nas_notas/*.parquet",
    "securitizacao_certificados": "securitizacao_certificados/*.parquet",
    "securitizacao_cedente_devedor": "securitizacao_cedente_devedor/*.parquet",
    "trocas_de_auditor": "trocas_de_auditor/trocas.parquet",
    "curva_juros": "curva_juros/*.parquet",
    "bcb_selic_focus": "bcb_selic_focus/bcb_selic_focus.parquet",
    "release_x_oficial": "release_x_oficial/release_x_oficial.parquet",
    "noticias_fatos": "noticias_fatos/*.parquet",
    "noticias_numeros": "noticias_numeros/*.parquet",
    "controladas": "controladas/*.parquet",
    "controladas_pj": "controladas_pj/*.parquet",  # só no VPS (linha 844)
    "rotulos_atraso": "rotulos_atraso/rotulos_atraso.parquet",
    "colunas_atraso": "colunas_atraso/colunas_atraso.parquet",
    "empresa_serie": "empresa_serie/empresa_serie.parquet",
    "entidades": "rede/entidades.parquet",
    "identificadores": "rede/identificadores.parquet",
    "ligacoes": "rede/ligacoes.parquet",
    "ma_assessorias": "ma/assessorias/*.parquet",
    "ma_candidatos": "ma/candidatos/candidatos.parquet",
    "ma_partes": "ma/ligacao/partes.parquet",
    "ma_negocios": "ma/ligacao/negocios.parquet",
    "ma_datas": "ma/datas/negocios.parquet",
    "ma_regua": "ma/regua/negocios.parquet",
    "usda_psd_cafe": "commodities/usda_psd/*.parquet",
    "faostat_cafe": "commodities/faostat_cafe/*.parquet",
}
# tabela conferida à mão → CSV no repositório (separado por `;`)
CONFERIDAS: dict[str, str] = {
    "emissores_sem_ligacao": "base/conferidas/emissores_sem_ligacao.csv",
    "emissores_antigos": "base/conferidas/emissores_antigos.csv",
    "codigos_fora_do_fca": "base/conferidas/codigos_fora_do_fca.csv",
    "contraparte_cafe": "base/conferidas/contrapartes_cafe.csv",
}
_NO_BANCO = "mora no banco do app (VPS), não no acervo: entra só por `extras`"
_CNPJ_DA_CARGA = (
    "a carga mensal do CNPJ (`scripts/carga_receita_retrato.py`) grava em pasta própria "
    "(`vigente/` e `mudancas/`) e ainda não rodou no servidor (fila 120): entra na porta depois "
    "dela e do portão de qualidade da API externa"
)
FORA_DA_PORTA: dict[str, str] = {
    "achados_de_qualidade": _NO_BANCO,
    "padroes_setoriais": _NO_BANCO,
    "fre_proventos": _NO_BANCO,
    "fre_eventos_de_capital": _NO_BANCO,
    "sus_competencias": (
        "só interna (`vitrine.TABELAS_SO_INTERNAS`): `registros` menos a soma publicada revelaria a célula "
        "suprimida; a conferência com o TabNet lê o Parquet direto"
    ),
    "cadastro_das_companhias": (
        "não é Parquet da base: é lido do original no acervo (`base/cadastro.py::ler_cadastro`)"
    ),
    **dict.fromkeys(
        ("processos_datajud", "processos_datajud_movimentos"),
        (
            "só uso interno (`coletas.FONTES_SO_INTERNAS`): a porta serve a API e o site; o "
            "treino lê o Parquet direto"
        ),
    ),
    **{
        f"cnpj_{nome}{sufixo}": _CNPJ_DA_CARGA
        for nome in ("estabelecimentos", "simples", "qsa")
        for sufixo in ("", "_mudancas")
    },
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


def servida_pela_porta(tabela: str) -> bool:
    """Se a porta serve a tabela por Parquet do acervo (`ARQUIVOS`): as conferidas no repositório e
    as de `FORA_DA_PORTA` ficam de fora da consulta aberta (API e site)."""
    return tabela in ARQUIVOS


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


def _sem_as_linhas_de_pessoa(select: str, tabela: Tabela, colunas: list[str]) -> str:
    """Esconde as linhas marcadas como pessoa natural (`tabela.linhas_de_pessoa`, ADR 0075). Na dúvida
    é pessoa: a marca vazia também esconde, e sem a coluna no arquivo (não dá para separar empresa de
    pessoa) a view não serve linha nenhuma."""
    if not tabela.linhas_de_pessoa:
        return select
    if tabela.linhas_de_pessoa not in colunas:
        return f"{select} WHERE false"
    return f"{select} WHERE NOT coalesce({_nome(tabela.linhas_de_pessoa)}, true)"


# --- a rede sem pessoa (linha 787; ADR 0075 e `base/rede/vistas.py`) ------------------------------
SEM_EMPRESAS = "SELECT CAST(NULL AS VARCHAR) AS id_entidade WHERE false"


def _empresas_da_rede(con: duckdb.DuckDBPyConnection, fontes: Mapping[str, str]) -> str:
    """SQL com os `id_entidade` que a rede diz que não são pessoa. Sem a tabela de entidades, ou sem a
    marca nela, nenhum: na dúvida, é pessoa."""
    fonte = fontes.get("entidades")
    if fonte is None or not {"id_entidade", "trata_como_pessoa"} <= set(
        _colunas(con, fonte)
    ):
        return SEM_EMPRESAS
    return (
        f"SELECT id_entidade FROM {fonte} "
        "WHERE id_entidade IS NOT NULL AND NOT coalesce(trata_como_pessoa, true)"
    )


def _sem_nome_de_pessoa(select: str, colunas: list[str]) -> str:
    """`entidades`: a linha fica (é ela que diz que o id é de pessoa), o nome de quem é tratado como
    pessoa sai. Sem a marca no arquivo, nenhum nome sai."""
    if "nome" not in colunas:
        return select
    nome = (
        "CASE WHEN coalesce(trata_como_pessoa, true) THEN NULL ELSE nome END"
        if "trata_como_pessoa" in colunas
        else "NULL"
    )
    return f"SELECT * REPLACE (CAST({nome} AS VARCHAR) AS nome) FROM ({select})"


SISTEMAS_DE_CNPJ = ("cnpj_raiz", "cnpj")
TAMANHO_DA_RAIZ = 8  # a raiz do CNPJ: os 8 primeiros dígitos


def _sem_ids_de_pessoa(select: str, colunas: list[str]) -> str:
    """`identificadores` sem o id de pessoa (P..., só da vista interna; o hash sai do CPF). O CNPJ de
    quem é tratado como pessoa fica, porque é por ele que as rotas, o crédito e a API externa sabem
    que aquele CNPJ é de pessoa (sem a linha, o "não achou" viraria empresa):

    - leva à entidade E marcada (MEI, EI), que sai sem o nome; o id E não esconde ninguém (é o
      SHA-256 da raiz);
    - se leva a uma pessoa da rede, o id sai sem o hash: `P` e a raiz da própria linha (um por
      raiz, para que a rede de uma pessoa não junte os CNPJs de todas).

    Outro identificador de pessoa (CPF, por exemplo) não sai. Sem o `id_entidade` ou o `sistema`
    no arquivo, nenhum."""
    if not {"id_entidade", "sistema"} <= set(colunas):
        return f"{select} WHERE false"
    pessoa = _texto(PREFIXO_DE_PESSOA)
    de_cnpj = ", ".join(_texto(s) for s in SISTEMAS_DE_CNPJ)
    return (
        f"SELECT * REPLACE (CASE WHEN starts_with(id_entidade, {pessoa}) "
        f"THEN {pessoa} || left(valor, {TAMANHO_DA_RAIZ}) "
        f"ELSE id_entidade END AS id_entidade) FROM ({select}) "
        f"WHERE NOT starts_with(id_entidade, {pessoa}) OR sistema IN ({de_cnpj})"
    )


def _ligacoes_publicadas(select: str, colunas: list[str], empresas: str) -> str:
    """`ligacoes` como a vista publicada (`base/rede/vistas.py::vista_publicada`): sem ponta vazia,
    sem aresta de pessoa e sem sinal negativo sobre quem não é empresa. Sem as pontas ou o tipo no
    arquivo, nenhuma (não dá para saber quem é pessoa)."""
    if not {"de", "para", "tipo"} <= set(colunas):
        return f"{select} WHERE false"
    pessoa = _texto(PREFIXO_DE_PESSOA)
    negativos = ", ".join(_texto(t) for t in TIPOS_NEGATIVOS)
    return (
        f"SELECT * FROM ({select}) WHERE de IS NOT NULL AND para IS NOT NULL "
        f"AND NOT starts_with(de, {pessoa}) AND NOT starts_with(para, {pessoa}) "
        f"AND (coalesce(tipo NOT IN ({negativos}), true) OR de IN ({empresas}))"
    )


def _rede_sem_pessoa(nome: str, select: str, colunas: list[str], empresas: str) -> str:
    """O que a porta serve das três tabelas da rede: nada que seja pessoa, para quem quer que leia."""
    if nome == "entidades":
        return _sem_nome_de_pessoa(select, colunas)
    if nome == "identificadores":
        return _sem_ids_de_pessoa(select, colunas)
    if nome == "ligacoes":
        return _ligacoes_publicadas(select, colunas, empresas)
    return select


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


def fonte_dos_arquivos(arquivos: Sequence[Path]) -> str:
    """A fonte SQL que lê estes Parquets juntos (colunas pelo nome). Pública para quem confere uma saída de
    montador já gravada (o recorte da rede só PJ, `base/rede/recorte_so_pj.py`) sem ler Parquet por fora da
    porta."""
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
    temporaria: Path | None = None,
) -> duckdb.DuckDBPyConnection:
    """Uma conexão do DuckDB na memória com as views da base em `pasta` (`<acervo>/base`).

    `memoria` ("2GB") e `threads` limitam o DuckDB (no VPS, constantes medidas; D10). `extras`:
    tabelas que não moram no acervo (as do banco do app), como DataFrame. `temporaria`: pasta dos
    arquivos temporários do DuckDB (padrão: a temporária do sistema, gravável de qualquer pasta atual).
    """
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'UTC'")
        con.execute(
            f"SET temp_directory = {_texto(str(temporaria or PASTA_TEMPORARIA))}"
        )
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
                fontes[nome] = fonte_dos_arquivos(achados)
        for nome, caminho in conferidas.items():
            if (RAIZ_DO_REPOSITORIO / caminho).is_file():
                fontes[nome] = _fonte_da_conferida(RAIZ_DO_REPOSITORIO / caminho)
        for nome, tabela in (extras or {}).items():
            con.register(f"_extra_{nome}", tabela)
            fontes[nome] = _nome(f"_extra_{nome}")
        empresas = _empresas_da_rede(con, fontes)
        for nome, fonte in fontes.items():
            if nome not in tabelas:
                continue
            colunas = _colunas(con, fonte)
            select = _rede_sem_pessoa(
                nome,
                _sem_as_linhas_de_pessoa(
                    _select_com_apelidos(nome, tabelas[nome], colunas, fonte),
                    tabelas[nome],
                    colunas,
                ),
                colunas,
                empresas,
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
