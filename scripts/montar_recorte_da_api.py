"""Manda ao VPS o recorte da base que a API lê (linha 739; plano `planos/2026-11-10-api-producao-com-base-739.md`).

O contêiner `tickerlab-api` de produção não tinha `<acervo>/base`: sem ela a API externa (`/data/v1`) e a
`/v1/base/tabelas` respondem 503. Este script monta, a partir da base de casa, uma cópia **só do que a API
serve**, em degraus (`--degrau 1`: o núcleo da API externa; `--degrau 2`: mais as tabelas da consulta
aberta da v1; `--degrau 3`: mais a rede só de pessoa jurídica, linha 843; `--degrau 4`: mais as cópias reduzidas
da lista de compradores, linha 844; `--degrau 5`: mais as cópias reduzidas dos cinco cadastros, linha 915), e a entrega ao VPS num tar pela mesma chave dos dossiês (pedido `receber-base-api`).

Lista de permissão (Diretoria, 10/11/2026, ADR 0101 Emenda 4): só vai a tabela escrita em `DEGRAU_1` ou
`DEGRAU_2_ACRESCENTA`, e só a coluna que o dicionário (`base/dicionario.py`) conhece, menos as
`COLUNAS_DE_PESSOA`; a linha que a porta esconde como pessoa (`Tabela.linhas_de_pessoa`, vazio conta como
pessoa) não vai. O que não está na lista não vai: `cnpj/`, `restrito/`, `pessoas/`, os temporários `tmp*` e
as tabelas de pessoa nem são lidos. Arquivo sem nada a tirar segue **byte a byte** (o hash do manifesto ao lado
continua valendo para a linhagem); arquivo com coluna ou linha a tirar é regravado, e a saída é lida de novo e
conferida antes do envio: pessoa na saída é erro e nada sai.

A rede (`entidades`, `identificadores`, `ligacoes`) não passa pela cópia por arquivo: vai inteira no degrau 3, pelo
filtro e pela trava de `base/rede/recorte_so_pj.py` (só PJ da `cnpj_empresas_pj` da mesma saída, sem `nome`, só os
tipos de ligação da `links`). A trava lê a saída e derruba a montagem em qualquer pessoa; o envio do degrau 3 pede
o pode da Diretoria com as contagens que ela devolve.

As cópias reduzidas da lista de compradores (`controladas_pj` e `fips_registrados`, linha 844) também não passam
pela cópia por arquivo: vão no degrau 4, pelo filtro e pela trava de `base/recorte_dos_compradores.py` (só as
colunas listadas, só raízes da `cnpj_empresas_pj` da mesma saída, sem gestor, administrador, nome nem CPF). O cron
diário segue no degrau 2; o envio do degrau 4 pede o pode da Diretoria com as contagens e a prova de zero pessoa.

Os cinco cadastros em retrato (ANS, SUSEP, Lista Suja, ponte da GLEIF e embargos do IBAMA, linha 915) são tabelas de
pessoa no dicionário e também não passam pela cópia por arquivo: vão no degrau 5, pelo filtro e pela trava de
`base/recorte_dos_cadastros.py` (só a linha de pessoa jurídica, só raízes da `cnpj_empresas_pj` da mesma saída, sem
nome nem texto livre), com o mesmo nome de tabela que a API lê. O envio do degrau 5 pede o pode da Diretoria.

    python -m scripts.montar_recorte_da_api --degrau 1 --base <acervo>/base --saida /tmp/base-api
    python -m scripts.montar_recorte_da_api --degrau 2 --base <acervo>/base --enviar
    python -m scripts.montar_recorte_da_api --degrau 3 --base <acervo>/base --saida /tmp/base-api-rede
    python -m scripts.montar_recorte_da_api --degrau 4 --base <acervo>/base --saida /tmp/base-api-compradores
    python -m scripts.montar_recorte_da_api --degrau 5 --base <acervo>/base --saida /tmp/base-api-cadastros

Saída 0 tudo certo; 1 falha, com a última linha `FALHAS: ...` (vai para o aviso do Kuma).

Roda: cron de casa pelo ~/bin/enviar-base-ao-vps.sh (depois da coleta da noite); manual com --saida.
"""

import argparse
import io
import logging
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

import duckdb

from base import recorte_dos_cadastros, recorte_dos_compradores
from base.cpf_no_texto import tem_cpf_valido
from base.dicionario import TABELAS
from base.dossie import (
    COLUNAS_DE_PESSOA,
    SO_PELA_API_EXTERNA,
    pode_consultar,
    pode_mostrar,
    tem_dia_publico,
)
from base.porta.duckdb import (
    ARQUIVOS,
    PASTA_TEMPORARIA,
    arquivos_da_tabela,
    servida_pela_porta,
)
from base.rede import recorte_so_pj
from base.rede.entidades import EMPRESARIO_INDIVIDUAL, GRUPO_DAS_PESSOAS_FISICAS
from src import acervo

log = logging.getLogger("montar_recorte_da_api")

# O núcleo da API externa (`src/api_externa/conjuntos/`): demonstrações, rede (empresas) e fundos.
DEGRAU_1 = (
    "demonstracoes_como_era",
    "cadastro_de_fundos",
    "carteiras_dos_fundos",
)
# Fica em casa: pesadas demais para o contêiner (linha 741 para a fidc_informe) ou com nome de parte de
# processo (pessoa possível). Só saem daqui com outra decisão.
FICAM_EM_CASA = (
    "scr_credito",
    "ons_geracao",
    "comex_preco_medio",
    "fidc_informe",
    "processos_partes",
    # Situação especial tem pessoa (falência de MEI): só vai ao VPS filtrada, depois da linha 787 (Diretoria,
    # 10/11/2026). A rede saiu daqui para `REDE_SO_PJ` (linha 843).
    "cnpj_situacao_especial",
    # Têm linha de pessoa (EI/MEI, auditor sem CNPJ de firma) ou dúvida, achadas pela 789 em 10/11/2026 depois de
    # subirem no degrau 2; apagadas do VPS com o pode da Diretoria. Só voltam com a marca de pessoa por linha.
    "anatel_acessos",
    "ifdata_cadastro",
    "carteiras_bloco_8",
    "controladas",
    "auditores",
    "ofertas_antigas",
    "trocas_de_auditor",
    "ofertas_resolucao_160",
    # raízes de MEI e EI (pessoa física) sem marca por linha: esperam a decisão da Diretoria (revisão cruzada, 10/11)
    "cnpj_empresas_historico",
    "cnpj_simples_historico",
    # lote 1 das 300 pelo CNPJ (linha 904): têm a marca de pessoa por linha, mas o envio ao VPS pede o pode da
    # Diretoria com a prova de zero pessoa da 1ª carga (linha 908). Até lá, ficam em casa.
    "fip_informe",
    "fii_informe_mensal",
    "fii_ativos",
    "fii_administradores",
    "aneel_inadimplencia",
    "aneel_indicadores_comerciais",
    "ans_idss",
    # linha 904 (lote 2): titulares do INPI só com empresa; o envio ao VPS pede o "pode" da Diretoria e a leitura da
    # licença (CC Atribuição-SemDerivações 3.0, a confirmar para tabela derivada)
    "inpi_marcas_titulares",
    "inpi_patentes_depositantes",
    "inpi_desenhos_depositantes",
    "inpi_programas_titulares",
    # linha 904 (lote 2, ANEEL): agentes, autos de infração e termos de notificação só com CNPJ; o envio ao VPS pede
    # o "pode" da Diretoria com a prova de zero pessoa da 1ª carga (ODbL da ANEEL, citar)
    "aneel_agentes",
    "aneel_autos_de_infracao",
    "aneel_termos_de_notificacao",
)
# As demais que `base.dossie.pode_consultar` libera (a consulta aberta da v1). Tabela nova que a porta liberar
# não entra sozinha: o teste falha até ela ser escrita aqui ou em FICAM_EM_CASA.
DEGRAU_2_ACRESCENTA = (
    "anac_estatistico", "aneel_samp", "anm_amb_agua_mineral",
    "anm_amb_producao_beneficiada", "anm_amb_producao_bruta", "anm_cfem_arrecadacao",
    "anm_sigbm_barragens", "anp_concessionarios", "anp_vendas", "ans_beneficiarios",
    "antt_siade", "area_cafe_municipio", "bcb_selic_focus",
    "ccee_pld", "cda_cotas", "cftc_cot_agro", "clima_regiao_cafe",
    "cnes_competencias",
    "codigos_invalidos", "comex_cafe", "comex_urf", "comex_via", "conab_cafe",
    "curva_juros", "cvm_fiagro", "debentures_assembleias", "dmpl_como_era",
    "emissores", "eventos", "faostat_cafe", "fca_geral", "fre_capital_social",
    "fre_comites", "fre_conselho", "fre_distribuicao_capital", "fre_diversidade",
    "fre_empregados", "fre_remuneracao", "fre_remuneracao_extremos", "ifdata_valores", "insolvencia", "ma_candidatos", "ma_datas", "ma_regua", "negociacoes",
    "noticias_fatos", "noticias_numeros", "ons_capacidade", "ons_restricao", "painel_dos_fundos", "pareceres_dfp",
    "pareceres_itr", "pgfn_divida", "processos", "processos_comunicacoes",
    "processos_nas_notas", "ratings", "release_x_oficial",
    "rotulos_atraso", "securitizacao_cedente_devedor", "securitizacao_certificados",
    "sus_ambulatorial", "sus_internacoes", "susep_seguros", "tickers_no_tempo",
    "usda_psd_cafe", "valores_mobiliarios",
    # sem pessoa por desenho (linha 584): 213-5, grupo 4 e CPF fora na origem; o MEI com natureza de empresa sai aqui (`tirar_raizes_de_mei`); a saída ainda é conferida
    # aqui (`conferir_sem_pessoa_do_cnpj`). Pode da Diretoria, 10/11/2026 18h31 (Emenda 4), linha 796.
    "cnpj_empresas_pj", "cnpj_estabelecimentos_pj",
    # sem pessoa por desenho (linha 810, PR 2): sócia PJ de empresa PJ, só para a API externa (a consulta aberta
    # não a serve: `base.dossie.SO_PELA_API_EXTERNA`). Vai neste degrau porque a guarda `conferir_raizes_so_pj`
    # exige `cnpj_empresas_pj` na mesma saída. Pode da Diretoria, 11/11/2026 (Emenda 4).
    "entradas_de_socio_pj",
    # sem pessoa por desenho (linha 841): só das raízes de `cnpj_estabelecimentos_pj`, só para a API externa
    # (ficha por CNPJ e crédito). A mesma guarda (`conferir_raizes_so_pj`) confere cada raiz na saída.
    "cnpj_situacao_cadastral",
)  # fmt: skip
# A rede só PJ (linha 843; desenho aceito pela Diretoria em 11/11/2026): só no degrau 3, inteira, pelo filtro e pela
# trava de `base/rede/recorte_so_pj.py`, nunca pela cópia por arquivo.
REDE_SO_PJ = recorte_so_pj.REDE
# As cópias reduzidas da lista de compradores (linha 844): só no degrau 4, pelo filtro e pela trava de
# `base/recorte_dos_compradores.py`, nunca pela cópia por arquivo. As tabelas inteiras seguem em casa.
REDUZIDAS = recorte_dos_compradores.REDUZIDAS
# As cópias reduzidas dos cinco cadastros em retrato (linha 915): só no degrau 5, pelo filtro e pela trava de
# `base/recorte_dos_cadastros.py`, nunca pela cópia por arquivo. As tabelas inteiras seguem em casa.
CADASTROS = recorte_dos_cadastros.CADASTROS
# o que tem filtro e trava próprios (não passa pela cópia por arquivo)
COM_FILTRO_PROPRIO = (*REDE_SO_PJ, *REDUZIDAS, *CADASTROS)
# Nada daqui vai, em nenhum degrau: pastas inteiras com pessoa ou de trabalho.
PASTAS_PROIBIDAS = ("cnpj", "restrito", "pessoas")
SUFIXO_DO_MANIFESTO = ".json"
PREFIXO_DA_LINHAGEM = (
    "origem_",
)  # colunas de linhagem que o dicionário agrupa em `_ORIGEM_*`


class RecorteErro(Exception):
    """O recorte não pode sair: um pedido fora da lista ou pessoa na saída."""


@dataclass(frozen=True)
class Resultado:
    tabela: str
    arquivos: int
    copiados: int
    recortados: int
    linhas_tiradas: int
    bytes_enviados: int


def tabelas_do_degrau(degrau: int) -> tuple[str, ...]:
    """As tabelas do degrau (1 = núcleo; 2 = núcleo + consulta aberta; 3 = o 2 + a rede só PJ; 4 = o 3 + as cópias
    reduzidas da lista de compradores; 5 = o 4 + as cópias reduzidas dos cinco cadastros), na ordem da lista."""
    if degrau == 1:
        return DEGRAU_1
    if degrau == 2:
        return (*DEGRAU_1, *DEGRAU_2_ACRESCENTA)
    if degrau == 3:
        return (*DEGRAU_1, *DEGRAU_2_ACRESCENTA, *REDE_SO_PJ)
    if degrau == 4:
        return (*DEGRAU_1, *DEGRAU_2_ACRESCENTA, *REDE_SO_PJ, *REDUZIDAS)
    if degrau == 5:
        return (*DEGRAU_1, *DEGRAU_2_ACRESCENTA, *REDE_SO_PJ, *REDUZIDAS, *CADASTROS)
    raise RecorteErro(f"degrau {degrau} não existe (1 a 5)")


def conferir_a_lista(tabelas: tuple[str, ...]) -> None:
    """Falha se uma tabela da lista não pode sair: sem arquivo na porta, de pessoa ou fora do que a porta mostra."""
    for nome in tabelas:
        if nome in REDE_SO_PJ:
            raise RecorteErro(
                f"{nome}: a rede só vai pelo degrau 3, com o filtro e a trava"
            )
        if nome in REDUZIDAS:
            raise RecorteErro(
                f"{nome}: a cópia reduzida só vai pelo degrau 4, com o filtro e a trava"
            )
        if nome in CADASTROS:
            raise RecorteErro(
                f"{nome}: o cadastro só vai pelo degrau 5, com o filtro e a trava"
            )
        if nome not in ARQUIVOS or nome not in TABELAS:
            raise RecorteErro(f"{nome}: a porta não serve esta tabela")
        if TABELAS[nome].pessoa:
            raise RecorteErro(f"{nome}: tabela de pessoa natural")
        if nome in FICAM_EM_CASA:
            raise RecorteErro(f"{nome}: fica em casa")
        if nome in SO_PELA_API_EXTERNA:
            # fora da consulta aberta só por estar nesta lista: o resto da regra de consultar ainda vale
            if not (
                pode_mostrar(nome)
                and servida_pela_porta(nome)
                and tem_dia_publico(nome)
            ):
                raise RecorteErro(f"{nome}: a API externa não pode servi-la")
        elif nome not in DEGRAU_1 and not pode_consultar(nome):
            raise RecorteErro(f"{nome}: a consulta aberta não a libera")
        if ARQUIVOS[nome].split("/")[0] in PASTAS_PROIBIDAS:
            raise RecorteErro(f"{nome}: mora em pasta proibida")


def colunas_permitidas(nome: str, colunas: list[str]) -> list[str]:
    """As colunas do arquivo que podem sair: as que o dicionário da tabela conhece, sem as de pessoa."""
    tabela = TABELAS[nome]
    conhecidas = {
        *tabela.colunas,
        *tabela.datas.values(),
        *tabela.chaves,
        *([tabela.linhas_de_pessoa] if tabela.linhas_de_pessoa else []),
    }
    return [
        c
        for c in colunas
        if c not in COLUNAS_DE_PESSOA
        and (c in conhecidas or c.startswith(PREFIXO_DA_LINHAGEM))
    ]


def _aspas(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def _colunas_do_arquivo(con: duckdb.DuckDBPyConnection, arquivo: Path) -> list[str]:
    cursor = con.execute(
        f"SELECT * FROM read_parquet({_aspas(arquivo.as_posix())}) LIMIT 0"
    )
    return [c[0] for c in cursor.description]


def _contar(con: duckdb.DuckDBPyConnection, arquivo: Path, onde: str) -> int:
    consulta = (
        f"SELECT count(*) FROM read_parquet({_aspas(arquivo.as_posix())}) WHERE {onde}"
    )
    return int(con.execute(consulta).fetchone()[0])  # type: ignore[index]


def _onde_pessoa(coluna: str) -> str:
    """Linha de pessoa: marcada ou sem marca (na dúvida é pessoa, como a porta)."""
    return f'coalesce("{coluna}", true)'


def _copiar_manifesto(origem: Path, destino: Path) -> None:
    manifesto = origem.with_suffix(SUFIXO_DO_MANIFESTO)
    if manifesto.is_file():
        shutil.copy2(manifesto, destino.with_suffix(SUFIXO_DO_MANIFESTO))


def recortar_arquivo(
    con: duckdb.DuckDBPyConnection, nome: str, origem: Path, destino: Path
) -> tuple[bool, int]:
    """Põe em `destino` o que de `origem` pode sair. Devolve (copiado byte a byte?, linhas tiradas).

    Sem coluna nem linha a tirar o arquivo vai igual. Com `linhas_de_pessoa` declarada mas ausente do arquivo
    a porta não serve linha nenhuma: aqui também nada sai (erro).
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    colunas = _colunas_do_arquivo(con, origem)
    mantidas = colunas_permitidas(nome, colunas)
    marca = TABELAS[nome].linhas_de_pessoa
    if marca and marca not in colunas:
        raise RecorteErro(
            f"{nome}: {origem.name} não tem `{marca}`: não dá para separar pessoa"
        )
    de_pessoa = _contar(con, origem, _onde_pessoa(marca)) if marca else 0
    if mantidas == colunas and de_pessoa == 0:
        shutil.copy2(origem, destino)
        _copiar_manifesto(origem, destino)
        return True, 0
    if not mantidas:
        raise RecorteErro(f"{nome}: {origem.name} ficaria sem coluna")
    selecao = ", ".join(f'"{c}"' for c in mantidas)
    onde = f"NOT {_onde_pessoa(marca)}" if marca else "true"
    con.execute(
        f"COPY (SELECT {selecao} FROM read_parquet({_aspas(origem.as_posix())}) WHERE {onde}) "
        f"TO {_aspas(destino.as_posix())} (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    _copiar_manifesto(origem, destino)
    return False, de_pessoa


def conferir_saida(con: duckdb.DuckDBPyConnection, nome: str, arquivo: Path) -> None:
    """Lê o arquivo que vai sair e falha se tiver coluna de pessoa ou linha de pessoa."""
    colunas = _colunas_do_arquivo(con, arquivo)
    proibidas = sorted(set(colunas) & COLUNAS_DE_PESSOA)
    if proibidas:
        raise RecorteErro(
            f"{nome}: {arquivo.name} saiu com coluna de pessoa {proibidas}"
        )
    marca = TABELAS[nome].linhas_de_pessoa
    if marca and (
        marca not in colunas or _contar(con, arquivo, _onde_pessoa(marca)) > 0
    ):
        raise RecorteErro(f"{nome}: {arquivo.name} saiu com linha de pessoa")


# Os mesmos padrões de `base.receita_empresas.NUMERO_COMPRIDO_DE_PESSOA`, na sintaxe do DuckDB (RE2).
_NUMERO_DE_PESSOA = r"(^|\D)(\d{11,12}|\d{3}[.\s]?\d{3}[.\s]?\d{3}[-./\s]?\d{2})(\D|$)"


def conferir_sem_pessoa_do_cnpj(
    con: duckdb.DuckDBPyConnection, nome: str, arquivo: Path
) -> None:
    """Na saída de `cnpj_empresas_pj`: nenhum 213-5, grupo 4 ou número de CPF na razão social."""
    if nome != "cnpj_empresas_pj":
        return
    fonte = f"read_parquet({_aspas(arquivo.as_posix())})"
    achadas = con.execute(
        f"SELECT count(*) FROM {fonte} WHERE trim(natureza_juridica) = '{EMPRESARIO_INDIVIDUAL}' "
        f"OR trim(natureza_juridica) LIKE '{GRUPO_DAS_PESSOAS_FISICAS}%' "
        f"OR regexp_matches(razao_social, '{_NUMERO_DE_PESSOA}')"
    ).fetchone()
    if achadas and achadas[0]:
        raise RecorteErro(
            f"{nome}: {arquivo.name} saiu com pessoa ({achadas[0]} linha(s))"
        )


# texto escrito por quem entrega o documento (o assunto de um fato relevante): pode trazer o CPF de uma pessoa
# (linha 884). As colunas que o recorte confere; coluna que o arquivo não tem é ignorada.
TEXTOS_LIVRES: dict[str, tuple[str, ...]] = {
    "eventos": ("assunto",),
    "insolvencia": ("assunto",),
    "debentures_assembleias": ("assunto",),
    "ma_candidatos": ("assunto",),
    "ratings": ("evidencia", "outras_notas", "nota_original"),
    "noticias_fatos": ("trecho",),
}
_CANDIDATO_A_CPF_SQL = (
    r"(^|\D)\d{3}[.\s\x{00A0}]?\d{3}[.\s\x{00A0}]?\d{3}[-\s\x{00A0}]?\d{2}($|\D)"
)


def conferir_sem_cpf_no_texto(
    con: duckdb.DuckDBPyConnection, nome: str, arquivo: Path
) -> None:
    """Na saída de uma tabela com texto livre: nenhum número de CPF que confere. Diz só a coluna e a contagem."""
    fonte = f"read_parquet({_aspas(arquivo.as_posix())})"
    presentes = set(_colunas_do_arquivo(con, arquivo))
    for coluna in TEXTOS_LIVRES.get(nome, ()):
        if coluna not in presentes:
            continue
        candidatos = con.execute(
            f"SELECT {coluna} FROM {fonte} WHERE regexp_matches({coluna}, '{_CANDIDATO_A_CPF_SQL}')"
        ).fetchall()
        achadas = sum(tem_cpf_valido(c[0]) for c in candidatos)
        if achadas:
            raise RecorteErro(
                f"{nome}: {arquivo.name} saiu com CPF no texto da coluna {coluna} ({achadas} linha(s))"
            )


def tirar_raizes_de_mei(
    con: duckdb.DuckDBPyConnection, saida: Path, tabelas: tuple[str, ...]
) -> int:
    """Em `cnpj_empresas_pj` da saída, deixa só a raiz que tem estabelecimento em `cnpj_estabelecimentos_pj`.

    A vista de estabelecimentos já tira o MEI (opção pelo Simples), mas a tabela de empresas só tira por
    natureza: MEI com natureza de empresa tem a razão social = nome da pessoa (revisão cruzada, 10/11/2026).
    As duas vão juntas ou nenhuma; devolve as linhas tiradas.
    """
    if "cnpj_empresas_pj" not in tabelas:
        return 0
    if "cnpj_estabelecimentos_pj" not in tabelas:
        raise RecorteErro("cnpj_empresas_pj só vai junto com cnpj_estabelecimentos_pj")
    tiradas = 0
    for arquivo in sorted((saida / "cnpj_empresas_pj").glob("*.parquet")):
        estab = saida / "cnpj_estabelecimentos_pj" / arquivo.name
        if not estab.is_file():
            raise RecorteErro(
                f"{arquivo.name}: sem estabelecimentos para conferir o MEI"
            )
        ficam = (
            f"SELECT * FROM read_parquet({_aspas(arquivo.as_posix())}) "
            f"WHERE cnpj_basico IN (SELECT cnpj_basico FROM read_parquet({_aspas(estab.as_posix())}))"
        )
        antes = _contar(con, arquivo, "true")
        novo = arquivo.with_suffix(".novo")
        con.execute(
            f"COPY ({ficam}) TO {_aspas(novo.as_posix())} (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        depois = _contar(con, novo, "true")
        novo.replace(arquivo)
        if (
            antes != depois
        ):  # o manifesto (hash) era do arquivo de origem: não vale mais
            arquivo.with_suffix(SUFIXO_DO_MANIFESTO).unlink(missing_ok=True)
        tiradas += antes - depois
    return tiradas


# As tabelas só de PJ por desenho e as colunas de raiz de cada uma: toda raiz tem de estar em `cnpj_empresas_pj`
# da mesma saída (`conferir_raizes_so_pj`).
RAIZES_SO_PJ: dict[str, tuple[str, ...]] = {
    "entradas_de_socio_pj": (
        "cnpj_basico",
        "raiz_socio_pj",
    ),  # a empresa e a sócia (linha 810)
    "cnpj_situacao_cadastral": ("cnpj_basico",),  # o estabelecimento (linha 841)
}
# A tabela que também traz o CNPJ inteiro: a raiz conferida tem de ser a do CNPJ (senão a guarda olharia outra).
CNPJ_DA_RAIZ: dict[str, str] = {"cnpj_situacao_cadastral": "cnpj"}


def conferir_raizes_so_pj(
    con: duckdb.DuckDBPyConnection, saida: Path, tabelas: tuple[str, ...]
) -> None:
    """Toda raiz das tabelas de `RAIZES_SO_PJ` da saída está em `cnpj_empresas_pj` da saída.

    As tabelas são só PJ por desenho (linhas 810 e 841); a garantia não pode depender da contagem de um dia: a
    raiz que a saída de empresas não tem (fora da lista, ou MEI tirado por `tirar_raizes_de_mei`) derruba o envio.
    """
    for nome, colunas in RAIZES_SO_PJ.items():
        if nome not in tabelas:
            continue
        if "cnpj_empresas_pj" not in tabelas:
            raise RecorteErro(f"{nome} só vai junto com cnpj_empresas_pj")
        arquivos = sorted((saida / nome).glob("*.parquet"))
        empresas = sorted((saida / "cnpj_empresas_pj").glob("*.parquet"))
        if not arquivos:
            continue
        if not empresas:
            raise RecorteErro(f"{nome} sem cnpj_empresas_pj na saída para conferir")
        _conferir_raizes(con, nome, colunas, arquivos, empresas)


def _conferir_raizes(
    con: duckdb.DuckDBPyConnection,
    nome: str,
    colunas: tuple[str, ...],
    arquivos: list[Path],
    empresas: list[Path],
) -> None:
    lista = ", ".join(_aspas(a.as_posix()) for a in empresas)
    fonte = ", ".join(_aspas(a.as_posix()) for a in arquivos)
    juncoes = " ".join(
        f'LEFT JOIN pj j{i} ON j{i}.cnpj_basico = t."{coluna}"'
        for i, coluna in enumerate(colunas)
    )
    # raiz nula também é fora: a junção não acha nada
    fora_da_lista = " OR ".join(
        f"j{i}.cnpj_basico IS NULL" for i in range(len(colunas))
    )
    fora = con.execute(
        f"WITH pj AS (SELECT DISTINCT cnpj_basico FROM read_parquet([{lista}])) "
        f"SELECT count(*) FROM read_parquet([{fonte}]) t {juncoes} WHERE {fora_da_lista}"
    ).fetchone()
    if fora and fora[0]:
        raise RecorteErro(
            f"{nome}: {fora[0]} linha(s) com raiz fora da lista sem pessoa"
        )
    if nome in CNPJ_DA_RAIZ:
        trocadas = con.execute(
            f"SELECT count(*) FROM read_parquet([{fonte}]) "
            f"WHERE cnpj_basico IS DISTINCT FROM "
            f"left(regexp_replace(\"{CNPJ_DA_RAIZ[nome]}\", '[^0-9]', '', 'g'), 8)"
        ).fetchone()
        if trocadas and trocadas[0]:
            raise RecorteErro(
                f"{nome}: {trocadas[0]} linha(s) com a raiz diferente da do CNPJ"
            )


def conectar() -> duckdb.DuckDBPyConnection:
    """Uma conexão do DuckDB que despeja na temporária do sistema, não em `.tmp` da pasta atual.

    No cron a pasta atual é a `/app` da imagem, sem permissão de escrita: a junção da conferência das entradas
    de sócio PJ passou da memória do contêiner e o envio de 11/11/2026 caiu ali (a porta teve a mesma falha
    em 20/10, `base.porta.duckdb.conectar`)."""
    con = duckdb.connect()
    con.execute("SET temp_directory = " + _aspas(str(PASTA_TEMPORARIA)))
    return con


def _origem_da_rede(base: Path, nome: str) -> list[Path]:
    arquivos = arquivos_da_tabela(base, ARQUIVOS[nome])
    if not arquivos:
        raise RecorteErro(f"{nome}: sem arquivo na base: a rede vai inteira ou não vai")
    for origem in arquivos:
        if origem.relative_to(base).parts[0] in PASTAS_PROIBIDAS:
            raise RecorteErro(
                f"{nome}: {origem.relative_to(base)} está em pasta proibida"
            )
    return arquivos


def _colunas_da_rede(
    con: duckdb.DuckDBPyConnection, nome: str, arquivos: list[Path]
) -> list[str]:
    """As colunas que podem sair: as que o dicionário conhece (de todos os arquivos), sem as de pessoa."""
    todas = list(
        dict.fromkeys(c for a in arquivos for c in _colunas_do_arquivo(con, a))
    )
    return colunas_permitidas(nome, todas)


def montar_rede(
    con: duckdb.DuckDBPyConnection, base: Path, saida: Path, tabelas: tuple[str, ...]
) -> list[Resultado]:
    """A rede só PJ (degrau 3): as três tabelas inteiras, pelo filtro, e a trava de zero pessoa na saída.

    Roda depois de `tirar_raizes_de_mei`: a lista sem pessoa que a trava usa é a `cnpj_empresas_pj` da saída."""
    if set(REDE_SO_PJ) - set(tabelas):
        raise RecorteErro(
            "a rede vai inteira ou não vai (entidades, identificadores e ligacoes)"
        )
    if "cnpj_empresas_pj" not in tabelas:
        raise RecorteErro("a rede só vai junto com cnpj_empresas_pj")
    empresas = sorted((saida / "cnpj_empresas_pj").glob("*.parquet"))
    origem = {nome: _origem_da_rede(base, nome) for nome in REDE_SO_PJ}
    destino = {nome: saida / ARQUIVOS[nome] for nome in REDE_SO_PJ}
    colunas = {nome: _colunas_da_rede(con, nome, origem[nome]) for nome in REDE_SO_PJ}
    try:
        linhas = recorte_so_pj.recortar_rede(con, origem, empresas, destino, colunas)
        contagens = recorte_so_pj.conferir_rede_so_pj(con, destino, empresas)
    except recorte_so_pj.RedeComPessoa as erro:
        raise RecorteErro(str(erro)) from erro
    for nome, por_tipo in contagens.items():
        log.info("%s na saída (zero pessoa conferido): %s", nome, por_tipo)
    return [
        Resultado(
            nome,
            len(origem[nome]),
            0,
            1,
            linhas[nome][0] - linhas[nome][1],
            destino[nome].stat().st_size,
        )
        for nome in REDE_SO_PJ
    ]


def _origem_das_reduzidas(base: Path, nome: str) -> list[Path]:
    """Os Parquets da tabela inteira de onde a cópia reduzida sai (nunca de pasta proibida)."""
    inteira = recorte_dos_compradores.ORIGEM[nome]
    arquivos = arquivos_da_tabela(base, ARQUIVOS[inteira])
    if not arquivos:
        raise RecorteErro(f"{nome}: sem {inteira} na base")
    for origem in arquivos:
        if origem.relative_to(base).parts[0] in PASTAS_PROIBIDAS:
            raise RecorteErro(
                f"{nome}: {origem.relative_to(base)} está em pasta proibida"
            )
    return arquivos


def montar_reduzidas(
    con: duckdb.DuckDBPyConnection, base: Path, saida: Path, tabelas: tuple[str, ...]
) -> list[Resultado]:
    """As cópias reduzidas da lista de compradores (degrau 4): o filtro e a trava de zero pessoa na saída.

    Roda depois de `tirar_raizes_de_mei`: a lista sem pessoa é a `cnpj_empresas_pj` da saída."""
    if "cnpj_empresas_pj" not in tabelas:
        raise RecorteErro("as cópias reduzidas só vão junto com cnpj_empresas_pj")
    nomes = tuple(t for t in REDUZIDAS if t in tabelas)
    empresas = sorted((saida / "cnpj_empresas_pj").glob("*.parquet"))
    origem = {nome: _origem_das_reduzidas(base, nome) for nome in nomes}
    destino = {nome: saida / nome / f"{nome}.parquet" for nome in nomes}
    montadoras = {
        recorte_dos_compradores.CONTROLADAS_PJ: recorte_dos_compradores.montar_controladas_pj,
        recorte_dos_compradores.FIPS_REGISTRADOS: recorte_dos_compradores.montar_fips_registrados,
    }
    try:
        for nome in nomes:
            montadoras[nome](con, origem[nome], empresas, destino[nome])
        linhas = recorte_dos_compradores.conferir_reduzidas(con, destino, empresas)
    except recorte_dos_compradores.ReduzidaComPessoa as erro:
        raise RecorteErro(str(erro)) from erro
    for nome, total in linhas.items():
        log.info("%s na saída (zero pessoa conferido): %d linha(s)", nome, total)
    return [
        Resultado(nome, len(origem[nome]), 0, 1, 0, destino[nome].stat().st_size)
        for nome in nomes
    ]


def montar_cadastros(
    con: duckdb.DuckDBPyConnection, base: Path, saida: Path, tabelas: tuple[str, ...]
) -> list[Resultado]:
    """As cópias reduzidas dos cinco cadastros (degrau 5): o filtro e a trava de zero pessoa na saída.

    Roda depois de `tirar_raizes_de_mei`: a lista sem pessoa é a `cnpj_empresas_pj` da saída. Cada arquivo sai no
    mesmo caminho relativo (a API lê a tabela pelo nome); cadastro sem arquivo na base derruba o envio."""
    if "cnpj_empresas_pj" not in tabelas:
        raise RecorteErro("os cadastros só vão junto com cnpj_empresas_pj")
    nomes = tuple(t for t in CADASTROS if t in tabelas)
    empresas = sorted((saida / "cnpj_empresas_pj").glob("*.parquet"))
    origem = {nome: _origem_do_cadastro(base, nome) for nome in nomes}
    destinos: dict[str, list[Path]] = {}
    tiradas: dict[str, int] = {}
    try:
        for nome in nomes:
            destinos[nome] = [
                saida / arquivo.relative_to(base) for arquivo in origem[nome]
            ]
            tiradas[nome] = sum(
                recorte_dos_cadastros.montar_cadastro(
                    con, nome, arquivo, empresas, destino
                )[1]
                for arquivo, destino in zip(origem[nome], destinos[nome], strict=True)
            )
        linhas = recorte_dos_cadastros.conferir_cadastros(con, destinos, empresas)
    except recorte_dos_cadastros.CadastroComPessoa as erro:
        raise RecorteErro(str(erro)) from erro
    for nome, total in linhas.items():
        log.info(
            "%s na saída (zero pessoa conferido): %d linha(s), %d tirada(s)",
            nome,
            total,
            tiradas[nome],
        )
    return [
        Resultado(
            nome,
            len(origem[nome]),
            0,
            len(origem[nome]),
            tiradas[nome],
            sum(d.stat().st_size for d in destinos[nome]),
        )
        for nome in nomes
    ]


def _origem_do_cadastro(base: Path, nome: str) -> list[Path]:
    """Os Parquets do cadastro na base (nunca de pasta proibida); sem nenhum, nada sai."""
    arquivos = arquivos_da_tabela(base, ARQUIVOS[nome])
    if not arquivos:
        raise RecorteErro(
            f"{nome}: sem arquivo na base (a montagem da linha 915 já rodou?)"
        )
    for origem in arquivos:
        if origem.relative_to(base).parts[0] in PASTAS_PROIBIDAS:
            raise RecorteErro(
                f"{nome}: {origem.relative_to(base)} está em pasta proibida"
            )
    return arquivos


def montar(base: Path, saida: Path, tabelas: tuple[str, ...]) -> list[Resultado]:
    """Monta em `saida` (= a futura `<acervo>/base` do VPS) o recorte das tabelas; confere tudo."""
    rede = tuple(t for t in tabelas if t in REDE_SO_PJ)
    reduzidas = tuple(t for t in tabelas if t in REDUZIDAS)
    cadastros = tuple(t for t in tabelas if t in CADASTROS)
    tabelas_por_arquivo = tuple(t for t in tabelas if t not in COM_FILTRO_PROPRIO)
    conferir_a_lista(tabelas_por_arquivo)
    base = base.resolve()
    resultados: list[Resultado] = []
    con = conectar()
    try:
        for nome in tabelas_por_arquivo:
            arquivos = arquivos_da_tabela(base, ARQUIVOS[nome])
            copiados = recortados = tiradas = enviados = 0
            for origem in arquivos:
                relativo = origem.relative_to(base)
                if relativo.parts[0] in PASTAS_PROIBIDAS:
                    raise RecorteErro(f"{nome}: {relativo} está em pasta proibida")
                destino = saida / relativo
                igual, tirou = recortar_arquivo(con, nome, origem, destino)
                conferir_saida(con, nome, destino)
                conferir_sem_pessoa_do_cnpj(con, nome, destino)
                conferir_sem_cpf_no_texto(con, nome, destino)
                copiados += igual
                recortados += not igual
                tiradas += tirou
                enviados += destino.stat().st_size
            resultados.append(
                Resultado(nome, len(arquivos), copiados, recortados, tiradas, enviados)
            )
        tiradas_de_mei = tirar_raizes_de_mei(con, saida, tabelas)
        if tiradas_de_mei:
            log.info("cnpj_empresas_pj: %d raiz(es) de MEI tiradas", tiradas_de_mei)
        conferir_raizes_so_pj(con, saida, tabelas)
        if rede:
            resultados += montar_rede(con, base, saida, tabelas)
        if reduzidas:
            resultados += montar_reduzidas(con, base, saida, tabelas)
        if cadastros:
            resultados += montar_cadastros(con, base, saida, tabelas)
    finally:
        con.close()
    return resultados


def empacotar(saida: Path, destino: io.BufferedIOBase) -> int:
    """Escreve o tar de `saida` (caminhos relativos, só arquivo comum). Devolve quantos arquivos."""
    total = 0
    with tarfile.open(fileobj=destino, mode="w|") as tar:  # type: ignore[call-overload]
        for arquivo in sorted(saida.rglob("*")):
            if arquivo.is_symlink():
                raise RecorteErro(f"{arquivo} é link simbólico")
            if not arquivo.is_file():
                continue
            info = tar.gettarinfo(
                str(arquivo), arcname=arquivo.relative_to(saida).as_posix()
            )
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with arquivo.open("rb") as f:
                tar.addfile(info, f)
            total += 1
    return total


def enviar(saida: Path, comando_ssh: list[str]) -> int:
    """Manda o tar de `saida` pela entrada padrão do ssh; devolve o código de saída do ssh."""
    with subprocess.Popen(comando_ssh, stdin=subprocess.PIPE) as processo:
        assert processo.stdin is not None
        empacotar(saida, processo.stdin)  # type: ignore[arg-type]
        processo.stdin.close()
        return processo.wait()


def comando_ssh_padrao() -> list[str]:
    return [
        "ssh", "-T", "-i", str(Path.home() / ".ssh" / "enviar_dossies"),
        "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=30",
        "tiago@tickerlab-vps.taila57363.ts.net", "receber-base-api",
    ]  # fmt: skip


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Recorte da base para o VPS (linha 739)")
    p.add_argument("--degrau", type=int, choices=(1, 2, 3, 4, 5), required=True)
    p.add_argument(
        "--base", type=Path, help="<acervo>/base (padrão: o acervo do ambiente)"
    )
    p.add_argument(
        "--saida", type=Path, help="pasta onde montar o recorte (padrão: temporária)"
    )
    p.add_argument(
        "--enviar",
        action="store_true",
        help="manda o recorte ao VPS (receber-base-api)",
    )
    return p.parse_args(argv)


def _exigir_saida_vazia(saida: Path) -> None:
    """O tar leva tudo o que está em `saida`: sobra de rodada antiga (ou de outra versão) não pode ir junto."""
    if saida.exists() and any(saida.iterdir()):
        raise RecorteErro(f"a pasta de saída {saida} não está vazia")


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    base = args.base
    if base is None:
        raiz = acervo.pasta_do_acervo()
        if raiz is None:
            print("FALHAS: acervo desligado (TICKERLAB_ACERVO)")
            return 1
        base = raiz / "base"
    temporaria = None
    saida = args.saida
    if saida is None:
        temporaria = tempfile.mkdtemp(prefix="base-api-")
        saida = Path(temporaria)
    try:
        _exigir_saida_vazia(saida)
        resultados = montar(base, saida, tabelas_do_degrau(args.degrau))
        for r in resultados:
            log.info(
                "%s: %d arquivo(s), %d iguais, %d recortados, %d linha(s) de pessoa fora, %.1f MB",
                r.tabela, r.arquivos, r.copiados, r.recortados, r.linhas_tiradas, r.bytes_enviados / 1e6,
            )  # fmt: skip
        vazias = [
            r.tabela for r in resultados if r.arquivos == 0 and r.tabela in DEGRAU_1
        ]
        if vazias:
            print(f"FALHAS: sem arquivo na base: {', '.join(vazias)}")
            return 1
        if args.enviar:
            codigo = enviar(saida, comando_ssh_padrao())
            if codigo:
                print(f"FALHAS: o ssh saiu com {codigo}")
                return 1
        return 0
    except (RecorteErro, duckdb.Error, OSError) as erro:
        print(f"FALHAS: {erro}")
        return 1
    finally:
        if temporaria:
            shutil.rmtree(temporaria, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
