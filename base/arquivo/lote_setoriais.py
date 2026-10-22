"""Lote setoriais Brasil do arquivista (rodada 1 da pesquisa de dados escondidos, 22/10/2026).

Energia (CCEE, EPE, ONS, ANEEL), saúde suplementar (ANS), telecom (Anatel), aviação (ANAC), ensino
superior (INEP), frota de veículos (Senatran), combustíveis (ANP) e propriedade industrial (INPI):
séries setoriais que movem as empresas listadas e que ainda não estavam na base. O comércio
exterior (MDIC Comex Stat, NCM e município) já está em `fontes.descobrir_comex`; aqui não repete.
Cada fonte é um `Fonte` do arquivista (`base/arquivo/coleta.py`); aqui só se descobre o que baixar
e se guarda como a fonte publica. Este módulo não importa `fontes.py` (que importa este): por isso
leva cópias pequenas de `_um` e `descobrir_ckan`.

Escolhas (testes em `tests/test_base_arquivo_lote_setoriais.py`):
- **ritmo pelo calendário da fonte:** o que sai todo mês é `mensal`; os portais CKAN que ganham
  arquivo novo a qualquer hora são `semanal`; `pesada=True` onde o servidor manda ETag (a coleta
  confere no HEAD e só baixa o que mudou);
- **servidor que recusa HEAD não é pesado:** a ANP (403) e o INPI (500) ficam sem `pesada`; o
  acervo deduplica pelo SHA-256 e o `guardado_vale` evita baixar de novo o que não muda (semestre
  fechado da ANP, arquivo do INPI baixado há menos de um mês);
- **LGPD (INPI):** só os arquivos sem coluna de pessoa (dados bibliográficos, classificação IPC,
  vínculos e despachos de patentes; dados básicos e despachos de contratos). Inventores,
  procuradores, depositantes, cedentes e cessionários ficam de fora, e as marcas (1,9 GB) também;
  ver a fila;
- **ONS:** CSV (o Parquet nem sempre cobre todos os anos) e o dicionário de dados em PDF;
- **os que a ANAC publica aninhados por ano e mês** (VRA, atrasos e cancelamentos) ficam para a fila.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

import requests
import sqlalchemy as sa

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte
from base.arquivo.obter import (
    extrair_do_zip_remoto,
    membros_do_zip_remoto,
    zip_que_pode_faltar,
)

HTTP_NAO_ENCONTRADO = 404
SEMANAL = "semanal"
MENSAL = "mensal"
PAINEIS = ("powerbi.com", "app.powerbi", "lookerstudio.google", "datastudio.google")

# ---- Energia: portais CKAN (CCEE, ONS, ANEEL) ----
PORTAL_DA_CCEE = "https://dadosabertos.ccee.org.br"
PORTAL_DO_ONS = "https://dados.ons.org.br"
PORTAL_DA_ANEEL = "https://dadosabertos.aneel.gov.br"
# id da fonte → pacotes (o `pld_horario` e as médias diária e mensal já estão em `ccee-pld`; as
# listas de agentes e os `*_horario` por usina ficam de fora: pessoas e tamanho)
PACOTES_DA_CCEE = {
    "ccee-pld-detalhe": (
        "pld_horario_submercado",
        "pld_media_semanal",
        "pld_final_historico",
        "pld_final_medio",
    ),
    "ccee-consumo": (
        "consumo_mensal_ambiente_comercializacao",
        "consumo_classe_agente",
        "consumo_ramo_atividade",
    ),
    "ccee-geracao": (
        "geracao_fonte_primaria",
        "geracao_consolidada",
        "geracao_submercado",
    ),
    "ccee-contratos": (
        "contrato_montante_mensal_classe_vendedor",
        "contrato_montante_mensal_tipo",
    ),
    "ccee-mercado": (
        "energia_incentivada_mensal",
        "mre_mensal",
        "exposicao_financeira_mensal",
        "sumario_mensal_resultado",
        "sumario_mensal_liquidacao",
        "inadimplencia_ccrbt",
        "custo_variavel_unitario_estrutural",
        "garantia_fisica_fonte",
    ),
}
# o ONS publica um arquivo por ano (CSV, XLSX e Parquet) e o dicionário de dados em PDF
FORMATOS_DO_ONS = ("csv", "pdf")
PACOTES_DO_ONS = {
    "ons-carga": ("carga-energia", "carga-mensal", "curva-carga"),
    "ons-balanco": (
        "balanco-energia-subsistema",
        "intercambio-nacional",
        "intercambio-internacional",
    ),
    "ons-hidrologia": ("ear-diario-por-subsistema", "ena-diario-por-subsistema"),
    "ons-custos": ("cmo-semanal", "cvu-usitermica"),
    "ons-termica": ("geracao-termica-despacho-2",),
    "ons-fator-capacidade": ("fator-capacidade-2",),
}
FORMATOS_DA_ANEEL = ("csv", "pdf")
# tarifas e bandeiras, parque gerador e leilões, qualidade do fornecimento; ficam de fora os
# pacotes com consumidores (geração distribuída por unidade, beneficiários da CDE)
PACOTES_DA_ANEEL = {
    "aneel-tarifas": (
        "tarifas-distribuidoras-energia-eletrica",
        "componentes-tarifarias",
        "bandeiras-tarifarias",
    ),
    "aneel-geracao": (
        "siga-sistema-de-informacoes-de-geracao-da-aneel",
        "capacidade-instalada-por-unidade-da-federacao",
        "acrescimo-da-potencia-instalada",
        "resultado-de-leiloes",
    ),
    "aneel-qualidade": (
        "indicadores-coletivos-de-continuidade-dec-e-fec",
        "desempenho-das-concessionarias-de-transmissao",
    ),
}

# ---- EPE: consumo mensal de energia elétrica por classe (planilha única, reescrita todo mês) ----
CONSUMO_DA_EPE = (
    "https://www.epe.gov.br/sites-pt/publicacoes-dados-abertos/publicacoes/Documents/"
    "CONSUMO%20MENSAL%20DE%20ENERGIA%20EL%C3%89TRICA%20POR%20CLASSE.xlsx"
)

# ---- ANS: demonstrações contábeis das operadoras (uma pasta por ano, um zip por trimestre) ----
RAIZ_DAS_DEMONSTRACOES_DA_ANS = (
    "https://dadosabertos.ans.gov.br/FTP/PDA/demonstracoes_contabeis/"
)
ANO_NA_PASTA = re.compile(rb'href="(\d{4})/"')
ZIP_NA_PASTA = re.compile(rb'href="([^"/?]+\.zip)"')

# ---- Anatel: telefonia fixa (o zip tem 136 MB; os de móvel, banda larga e TV estão em `fontes`) ----
ZIP_DA_TELEFONIA_FIXA = "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/acessos/acessos_telefonia_fixa.zip"
CSV_DA_ANATEL = re.compile(r"(_Colunas|_Total)\.csv$", re.IGNORECASE)

# ---- ANAC: horas voadas por aeronave (o Dados_Estatisticos.csv já está em `fontes`) ----
HORAS_VOADAS_DA_ANAC = (
    "https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20opera%C3%A7%C3%B5es%20a%C3%A9reas/"
    "Horas%20Voadas%20de%20Aeronave/horas_voadas.csv"
)

# ---- INEP: microdados do Censo da Educação Superior (um zip por ano; o de 2024 tem 457 MB) ----
CENSO_SUPERIOR_DO_INEP = "https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_{ano}.zip"
ANOS_DO_CENSO_SUPERIOR = (
    5  # o ano corrente e os 4 anteriores: cobre os 3 últimos já publicados
)

# ---- Senatran: frota de veículos (uma página por ano, uma planilha por recorte e por mês) ----
PAGINA_DA_FROTA = "https://www.gov.br/transportes/pt-br/assuntos/transito/conteudo-Senatran/frota-de-veiculos-{ano}"
PLANILHA_DA_FROTA = re.compile(rb'href="([^"]+\.xlsx/@@download/file)"')
# UF × tipo, município × tipo e ano de fabricação, vistos só pelas letras do nome (a Senatran
# escreve "Frota_por_uf_e_tipo", "FrotaporUFeTipo" e "frota-por-uf-e-tipo", e até "Municpio")
RECORTE_DA_FROTA = re.compile(
    r"frotapor(?:uf|munic\w*?)etipo|frotaporufmunicipioanofab"
)

# ---- ANP: preços de combustíveis por posto (a página lista os links; o servidor recusa HEAD) ----
PAGINA_DOS_PRECOS_DA_ANP = (
    "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/"
    "serie-historica-de-precos-de-combustiveis"
)
LINK_DOS_PRECOS_DA_ANP = re.compile(
    rb'href="(https://www\.gov\.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/'
    rb'[^"]+)"'
)
ULTIMAS_SEMANAS_DA_ANP = (
    "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/qus/"
    "ultimas-4-semanas-{produto}.csv"
)
PRODUTOS_DA_ANP = ("diesel-gnv", "gasolina-etanol", "glp")
PRECOS_SEMESTRAIS_DA_ANP = re.compile(
    r"/shpc/dsas/(?:ca/ca|glp/glp)-\d{4}-\d{2}\.(?:csv|zip)$"
)
ANOS_DOS_PRECOS_MENSAIS_DA_ANP = (
    2  # o ano corrente e o anterior (os nomes mudam de mês a mês)
)
DIAS_DO_SEMESTRE_FECHADO = 60  # depois disso o semestre da ANP já não é reescrito

# ---- INPI: dados abertos (o servidor recusa HEAD e a raiz de /download/) ----
RAIZ_DO_INPI = "https://dadosabertos.inpi.gov.br/download/"
ARQUIVOS_DO_INPI = {
    "inpi-patentes": (
        "patentes/PATENTES_DADOS_BIBLIOGRAFICOS.csv",
        "patentes/PATENTES_CLASSIFICACAO_IPC.csv",
        "patentes/PATENTES_VINCULOS.csv",
        "patentes/PATENTES_DESPACHOS.csv",
    ),
    "inpi-contratos": (
        "contratos/CONTRATOS_DADOS_BASICOS.csv",
        "contratos/CONTRATOS_DESPACHO.csv",
    ),
}
DIAS_DA_ATUALIZACAO_DO_INPI = (
    25  # o INPI atualiza toda semana; o arquivista olha uma vez por mês
)


def _um(url: str, extensao: str | None = None) -> Descobrir:
    return lambda cliente, agora: [Alvo(url, extensao)]


def _e_arquivo(recurso: dict) -> bool:
    """Recurso que é arquivo de dados (não painel nem página)."""
    url = recurso.get("url") or ""
    formato = (recurso.get("format") or "").lower()
    return bool(url) and formato != "html" and not any(p in url for p in PAINEIS)


def descobrir_ckan(
    cliente: Cliente, portal: str, *pacotes: str, formatos: tuple[str, ...] = ()
) -> list[Alvo]:
    """Os arquivos (recursos) dos pacotes de um portal CKAN; `formatos` escolhe um por recurso."""
    alvos: list[Alvo] = []
    for pacote in pacotes:
        resposta = cliente.ler(f"{portal}/api/3/action/package_show?id={pacote}")
        recursos = [
            r
            for r in json.loads(resposta.conteudo)
            .get("result", {})
            .get("resources", [])
            if _e_arquivo(r)
            and (not formatos or (r.get("format") or "").lower() in formatos)
        ]
        if not recursos:
            raise ErroDeDescoberta(f"{pacote}: pacote sem arquivos em {portal}")
        alvos += [Alvo(r["url"]) for r in recursos]
    return alvos


def _ckan(portal: str, *pacotes: str, formatos: tuple[str, ...] = ()) -> Descobrir:
    return lambda cliente, agora: descobrir_ckan(
        cliente, portal, *pacotes, formatos=formatos
    )


def _nao_encontrado(erro: requests.HTTPError) -> bool:
    resposta = erro.response
    return resposta is not None and resposta.status_code == HTTP_NAO_ENCONTRADO


def _pagina_ou_nada(cliente: Cliente, url: str) -> bytes | None:
    """A página, ou None se ela não existe (o ano que a fonte ainda não abriu)."""
    try:
        return cliente.ler(url).conteudo
    except requests.HTTPError as erro:
        if _nao_encontrado(erro):
            return None
        raise


def _baixado_ha_mais_de(dias: int, anterior: sa.Row) -> bool:
    baixado = anterior.baixado_em
    if baixado.tzinfo is None:  # o SQLite dos testes devolve sem fuso
        baixado = baixado.replace(tzinfo=UTC)
    return datetime.now(UTC) - baixado > timedelta(days=dias)


def _semestre_fechado(anterior: sa.Row) -> bool:
    """O semestre já foi baixado há tempo: a ANP não o reescreve mais."""
    return _baixado_ha_mais_de(DIAS_DO_SEMESTRE_FECHADO, anterior)


def _baixado_neste_mes(anterior: sa.Row) -> bool:
    """Baixado há menos de ~um mês: o INPI só renova o arquivo, toda semana, sem ETag para conferir."""
    return not _baixado_ha_mais_de(DIAS_DA_ATUALIZACAO_DO_INPI, anterior)


# ---------- ANS ----------


def descobrir_demonstracoes_ans(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Um zip por trimestre em cada pasta de ano; ano sem zip é pulado, e sem nenhum é erro."""
    anos = dict.fromkeys(
        m.decode()
        for m in ANO_NA_PASTA.findall(
            cliente.ler(RAIZ_DAS_DEMONSTRACOES_DA_ANS).conteudo
        )
    )
    alvos: list[Alvo] = []
    for ano in anos:
        pasta = f"{RAIZ_DAS_DEMONSTRACOES_DA_ANS}{ano}/"
        nomes = dict.fromkeys(
            m.decode() for m in ZIP_NA_PASTA.findall(cliente.ler(pasta).conteudo)
        )
        alvos += [Alvo(pasta + nome, ".zip") for nome in nomes]
    if not alvos:
        raise ErroDeDescoberta(
            f"ANS: nenhum zip de demonstrações contábeis em {RAIZ_DAS_DEMONSTRACOES_DA_ANS}"
        )
    return alvos


# ---------- Anatel ----------


def descobrir_telefonia_fixa_da_anatel(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os CSVs "_Colunas" e "_Total" do zip de telefonia fixa (o endereço guarda `zip#arquivo`)."""
    membros = [
        m
        for m in membros_do_zip_remoto(cliente, ZIP_DA_TELEFONIA_FIXA)
        if CSV_DA_ANATEL.search(m)
    ]
    if not membros:
        raise ErroDeDescoberta(
            f"Anatel: nenhum CSV de acessos em {ZIP_DA_TELEFONIA_FIXA}"
        )
    return [
        Alvo(
            f"{ZIP_DA_TELEFONIA_FIXA}#{membro}",
            ".csv",
            extrair_do_zip_remoto(ZIP_DA_TELEFONIA_FIXA, membro),
        )
        for membro in membros
    ]


# ---------- INEP ----------


def descobrir_censo_superior(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os zips dos últimos anos; o que o INEP ainda não publicou vira `SemArquivo`, não falha."""
    urls = [
        CENSO_SUPERIOR_DO_INEP.format(ano=ano)
        for ano in range(agora.year - ANOS_DO_CENSO_SUPERIOR + 1, agora.year + 1)
    ]
    return [Alvo(url, ".zip", zip_que_pode_faltar(url)) for url in urls]


# ---------- Senatran ----------


def _letras(nome: str) -> str:
    return re.sub(r"[^a-z]", "", nome.lower())


def descobrir_frota(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """As planilhas de UF × tipo, município × tipo e ano de fabricação do ano e do anterior."""
    alvos: dict[str, Alvo] = {}
    for ano in (agora.year - 1, agora.year):
        pagina = PAGINA_DA_FROTA.format(ano=ano)
        conteudo = _pagina_ou_nada(cliente, pagina)
        if conteudo is None:
            continue
        for achado in PLANILHA_DA_FROTA.findall(conteudo):
            link = urljoin(pagina, achado.decode())
            nome = link.rsplit("/@@download", 1)[0].rsplit("/", 1)[-1]
            if RECORTE_DA_FROTA.search(_letras(nome)):
                alvos[link] = Alvo(link, ".xlsx")
    if not alvos:
        raise ErroDeDescoberta("Senatran: nenhuma planilha de frota nas páginas do ano")
    return list(alvos.values())


# ---------- ANP ----------


def _links_dos_precos_da_anp(cliente: Cliente) -> list[str]:
    conteudo = cliente.ler(PAGINA_DOS_PRECOS_DA_ANP).conteudo
    links = dict.fromkeys(m.decode() for m in LINK_DOS_PRECOS_DA_ANP.findall(conteudo))
    if not links:
        raise ErroDeDescoberta(
            f"ANP: nenhum link de preços em {PAGINA_DOS_PRECOS_DA_ANP}"
        )
    return list(links)


def descobrir_precos_semestrais_da_anp(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os arquivos semestrais (autorizações de revenda e GLP) linkados na página."""
    links = [
        link
        for link in _links_dos_precos_da_anp(cliente)
        if PRECOS_SEMESTRAIS_DA_ANP.search(link)
    ]
    if not links:
        raise ErroDeDescoberta("ANP: nenhum arquivo semestral de preços na página")
    return [Alvo(link) for link in links]


def descobrir_precos_mensais_da_anp(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os arquivos mensais do ano e do anterior (o nome muda de mês a mês, e alguns vêm sem ".csv")."""
    anos = [
        f"/shpc/dsan/{ano}/"
        for ano in range(
            agora.year - ANOS_DOS_PRECOS_MENSAIS_DA_ANP + 1, agora.year + 1
        )
    ]
    links = [
        link
        for link in _links_dos_precos_da_anp(cliente)
        if any(ano in link for ano in anos)
    ]
    if not links:
        raise ErroDeDescoberta("ANP: nenhum arquivo mensal de preços do ano na página")
    return [Alvo(link, ".csv") for link in links]


# ---------- INPI ----------


def _arquivos_do_inpi(*caminhos: str) -> Descobrir:
    return lambda cliente, agora: [Alvo(RAIZ_DO_INPI + c, ".csv") for c in caminhos]


# ---------- as fontes ----------


def fontes() -> list[Fonte]:
    """As fontes do lote, para a lista `FONTES` (os ids seguem a família: `ccee-...`, `ons-...`)."""
    ccee = [
        Fonte(id_, SEMANAL, _ckan(PORTAL_DA_CCEE, *pacotes))
        for id_, pacotes in PACOTES_DA_CCEE.items()
    ]
    ons = [
        Fonte(
            id_,
            SEMANAL,
            _ckan(PORTAL_DO_ONS, *pacotes, formatos=FORMATOS_DO_ONS),
            pesada=True,
        )
        for id_, pacotes in PACOTES_DO_ONS.items()
    ]
    aneel = [
        Fonte(
            id_,
            MENSAL,
            _ckan(PORTAL_DA_ANEEL, *pacotes, formatos=FORMATOS_DA_ANEEL),
            pesada=True,
        )
        for id_, pacotes in PACOTES_DA_ANEEL.items()
    ]
    inpi = [
        Fonte(
            id_,
            MENSAL,
            _arquivos_do_inpi(*caminhos),
            guardado_vale=_baixado_neste_mes,
        )
        for id_, caminhos in ARQUIVOS_DO_INPI.items()
    ]
    return [
        *ccee,
        Fonte("epe-consumo-mensal", MENSAL, _um(CONSUMO_DA_EPE), pesada=True),
        *ons,
        *aneel,
        Fonte("ans-demonstracoes", MENSAL, descobrir_demonstracoes_ans, pesada=True),
        Fonte(
            "anatel-acessos-telefonia-fixa",
            MENSAL,
            descobrir_telefonia_fixa_da_anatel,
            pesada=True,
        ),
        Fonte("anac-horas-voadas", MENSAL, _um(HORAS_VOADAS_DA_ANAC), pesada=True),
        Fonte("inep-censo-superior", MENSAL, descobrir_censo_superior, pesada=True),
        Fonte("senatran-frota", MENSAL, descobrir_frota, pesada=True),
        Fonte(
            "anp-precos-ultimas-semanas",
            SEMANAL,
            lambda cliente, agora: [
                Alvo(ULTIMAS_SEMANAS_DA_ANP.format(produto=produto))
                for produto in PRODUTOS_DA_ANP
            ],
        ),
        Fonte(
            "anp-precos-semestral",
            MENSAL,
            descobrir_precos_semestrais_da_anp,
            guardado_vale=_semestre_fechado,
        ),
        Fonte("anp-precos-mensal", MENSAL, descobrir_precos_mensais_da_anp),
        *inpi,
    ]
