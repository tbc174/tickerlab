"""Lote licitações e contratos do arquivista (rodada 4 da pesquisa de dados escondidos, 22/10/2026).

Quem vende ao governo, por quanto e quando: o repositório de dados da SEGES (compras do PNCP, atas
de registro de preço, compras legadas, pesquisa de preços, propostas, catálogo e SICONV), o
compras.gov.br, as APIs do Transferegov, o PNCP, a lista de inidôneos do TCU e os contratos de Minas
Gerais e Santa Catarina. Cada fonte é um `Fonte` do arquivista (`base/arquivo/coleta.py`); aqui só se
descobre o que baixar. Este módulo não importa `fontes.py` (que importa este).

Escolhas (testes em `tests/test_base_arquivo_lote_licitacoes.py`):
- **LGPD (ADR 0088): só pessoa jurídica.** CSVs e APIs misturam CPF e CNPJ e trazem nomes de
  servidores. Tudo passa por `obter_pj`: fica a linha cujo documento tem 14 dígitos (ou está em
  branco), sem as colunas de pessoa (CPF, usuário, responsável, e-mail, telefone, conta bancária).
  O acervo guarda o arquivo da fonte **menos as pessoas físicas**; nunca se consulta por CPF;
- **ritmo pelo calendário da fonte:** os CSVs mensais da SEGES são regerados aos sábados e domingos
  (`pesada=True`: o ETag do HEAD decide, e o que não mudou não baixa de novo); as APIs vão por janela
  (um dia por alvo) e a janela que já fechou não é consultada de novo (`guardado_vale`);
- **janela que ainda não tem dado** (dia sem resultado, mês que a fonte não abriu) é `SemArquivo`,
  nunca erro; a API que não para de paginar é erro (`PaginacaoSemFim`), nunca um arquivo cortado;
- **PNCP e TCU sem licença escrita** vão com a marca `a_confirmar` (ADR 0102): coleta citando a fonte;
- **de fora, de propósito:** o `siconv.zip` de 3 GB e as tabelas físicas do SICONV (obras, cronogramas),
  as atas e os contratos SIASG do compras.gov.br (rota 404, 22/10/2026), os inabilitados do TCU, o
  RS (contratada sem documento: pessoa física não se separa), o RJ (só XLSX e PDF) e a BA (sem licença).
  O Portal da Transparência e o BNDES estão no lote Brasil segunda camada; ver a fila.
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode

import requests
import sqlalchemy as sa

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte
from base.arquivo.obter_pj import csv_so_pj, json_paginado

HTTP_NAO_ENCONTRADO = 404
SEMANAL = "semanal"
MENSAL = "mensal"

# ---- repositório da SEGES (nginx com listagem de pastas; CSV em ZIP, regerados nos fins de semana) ----
SEGES = "https://repositorio.dados.gov.br/seges/"
LINK_NA_PASTA = re.compile(rb'href="([^"/?][^"?]*)"')
PRIMEIRO_ANO_DO_PNCP = 2021
PRIMEIRO_ANO_DAS_ATAS = 2023
PRIMEIRO_ANO_DO_LEGADO = 2000
PRIMEIRO_ANO_DA_PESQUISA_DE_PRECOS = 2019
PRIMEIRO_ANO_DAS_PROPOSTAS = 2021
MODALIDADES_DO_LEGADO = {
    "seges-legado-licitacao": "licitacao",
    "seges-legado-pregao": "pregao",
    "seges-legado-rdc": "rdc",
    "seges-legado-sem-licitacao": "compra_sem_licitacao",
}
CATALOGOS_DA_SEGES = ("catmat.csv", "catser.csv")
# as tabelas do SICONV (convênios e contratos de repasse) com fornecedor, convenente ou valor; as de
# obra física, cronograma e indicador ficam de fora, e o `siconv.zip` (3 GB) repete tudo
TABELAS_DO_SICONV = (
    "contrato", "convenio", "licitacao", "pagamento", "proponentes", "proposta", "programa",
    "empenho", "desembolso", "termo_aditivo", "obtv_convenente", "consorcios",
    "historico_situacao", "emenda", "inst_cont_aio_mod_empresas", "acomp_obras_mod_empresas",
    "vrpl_mod_empresas", "programa_proponentes",
)  # fmt: skip
ITENS_DE_LICITACAO_DO_SICONV = (
    "siconv_itens_licitacao.zip"  # o único que não é ".csv.zip"
)

# ---- compras.gov.br: itens homologados, com o vencedor por CNPJ (nunca consultar por CPF) ----
RESULTADO_DE_ITENS = (
    "https://dadosabertos.compras.gov.br/modulo-contratacoes/"
    "3_consultarResultadoItensContratacoes_PNCP_14133"
)
POR_PAGINA_DO_COMPRASGOV = 500
DIAS_DO_COMPRASGOV = 90  # a API aceita até 365; o resto do passado vai pela SEGES
DIAS_ATE_FECHAR_O_DIA = (
    30  # o resultado de um dia ainda ganha registro nas semanas seguintes
)
MAXIMO_DE_PAGINAS_POR_DIA = 400

# ---- Transferegov: APIs PostgREST abertas (offset e limit; a primeira coluna é sempre a chave) ----
API_DO_TRANSFEREGOV = "https://api.transferegov.gestao.gov.br"
TABELAS_DO_TRANSFEREGOV = {
    "transferegov-especiais": (
        "transferenciasespeciais",
        (
            "plano_acao_especial",
            "executor_especial",
            "empenho_especial",
            "documento_habil_especial",
            "ordem_pagamento_ordem_bancaria_especial",
            "historico_pagamento_especial",
            "programa_especial",
            "plano_trabalho_especial",
        ),
    ),
    "transferegov-ted": (
        "ted",
        (
            "programa",
            "plano_acao",
            "termo_execucao",
            "nota_credito",
            "programacao_financeira",
        ),
    ),
    "transferegov-fundo-a-fundo": (
        "fundoafundo",
        ("programa", "plano_acao", "empenho", "termo_adesao"),
    ),
}
LINHAS_POR_PAGINA_DO_TRANSFEREGOV = 1000
MAXIMO_DE_PAGINAS_DO_TRANSFEREGOV = 500
DIAS_DA_ATUALIZACAO_DO_TRANSFEREGOV = (
    25  # as tabelas mudam o tempo todo; olhar uma vez por mês basta
)

# ---- TCU: responsáveis inidôneos para licitar (ORDS; o CPF vem formatado, o CNPJ também) ----
INIDONEOS_DO_TCU = "https://contas.tcu.gov.br/ords/condenacao/consulta/inidoneos"
POR_PAGINA_DO_TCU = 500
MAXIMO_DE_PAGINAS_DO_TCU = 100

# ---- PNCP: contratos por data de publicação (3 a 12 s por página; as atas levam 40 s e ficam de fora) ----
CONTRATOS_DO_PNCP = "https://pncp.gov.br/api/consulta/v1/contratos"
POR_PAGINA_DO_PNCP = 500
DIAS_DO_PNCP = 14
DIAS_ATE_FECHAR_O_DIA_DO_PNCP = 7
MAXIMO_DE_PAGINAS_DO_PNCP = 500
PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS = 1.0
PAUSA_ENTRE_DIAS_EM_SEGUNDOS = 5.0

# ---- estados: portais CKAN com os contratos (MG: CC BY 4.0; SC: CC BY) ----
PORTAL_DE_MG = "https://dados.mg.gov.br"
PACOTE_DE_MG = "compras_contratos"
PORTAL_DE_SC = "https://dados.sc.gov.br"
PACOTE_DE_SC = "contratos"
DIAS_DA_ATUALIZACAO_DOS_ESTADOS = 25


def _baixado_ha_mais_de(dias: int, anterior: sa.Row) -> bool:
    baixado = anterior.baixado_em
    if baixado.tzinfo is None:  # o SQLite dos testes devolve sem fuso
        baixado = baixado.replace(tzinfo=UTC)
    return datetime.now(UTC) - baixado > timedelta(days=dias)


def _baixado_neste_mes(dias: int) -> Callable[[sa.Row], bool]:
    """Baixado há pouco: a fonte só renova o arquivo (sem ETag para conferir), uma vez por mês basta."""
    return lambda anterior: not _baixado_ha_mais_de(dias, anterior)


def _dia_na_url(url: str) -> date:
    achado = re.search(r"(\d{4})-?(\d{2})-?(\d{2})(?!.*\d{4}-?\d{2}-?\d{2})", url)
    if achado is None:
        raise ValueError(f"sem data no endereço: {url}")
    return date(*(int(g) for g in achado.groups()))


def _dia_fechado(dias: int) -> Callable[[sa.Row], bool]:
    """O dia da janela (lido do endereço) já foi baixado depois de `dias` dias dele: não muda mais."""

    def guardado(anterior: sa.Row) -> bool:
        fechou_em = datetime.combine(
            _dia_na_url(anterior.url), datetime.min.time(), UTC
        )
        baixado = anterior.baixado_em
        if baixado.tzinfo is None:
            baixado = baixado.replace(tzinfo=UTC)
        return baixado >= fechou_em + timedelta(days=dias)

    return guardado


# ---------- SEGES ----------


def _pasta_ou_nada(cliente: Cliente, url: str) -> bytes | None:
    """A listagem da pasta, ou None se ela não existe (o mês que a SEGES ainda não abriu)."""
    try:
        return cliente.ler(url).conteudo
    except requests.HTTPError as erro:
        if (
            erro.response is not None
            and erro.response.status_code == HTTP_NAO_ENCONTRADO
        ):
            return None
        raise


def _pastas_por_mes(raiz: str, primeiro_ano: int) -> Callable[[datetime], list[str]]:
    def pastas(agora: datetime) -> list[str]:
        return [
            f"{raiz}/{ano}/{mes:02d}/"
            for ano in range(primeiro_ano, agora.year + 1)
            for mes in range(1, 13)
            if (ano, mes) <= (agora.year, agora.month)
        ]

    return pastas


def _pastas_por_ano(raiz: str, primeiro_ano: int) -> Callable[[datetime], list[str]]:
    return lambda agora: [
        f"{raiz}/{ano}/" for ano in range(primeiro_ano, agora.year + 1)
    ]


def _descobrir_na_seges(
    pastas: Callable[[datetime], list[str]],
    nome: re.Pattern[str],
    recipiente: str = "zip",
) -> Descobrir:
    """Os arquivos de nome `nome` em cada pasta (pasta que não existe é pulada; sem nenhum é erro)."""

    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        alvos: list[Alvo] = []
        for pasta in pastas(agora):
            listagem = _pasta_ou_nada(cliente, SEGES + pasta)
            if listagem is None:
                continue
            for achado in dict.fromkeys(LINK_NA_PASTA.findall(listagem)):
                arquivo = achado.decode()
                if nome.fullmatch(arquivo):
                    url = f"{SEGES}{pasta}{arquivo}"
                    alvos.append(Alvo(url, ".csv", csv_so_pj(url, recipiente)))
        if not alvos:
            raise ErroDeDescoberta(f"SEGES: nenhum arquivo {nome.pattern} nas pastas")
        return alvos

    return descobrir


def _arquivos_do_siconv(cliente: Cliente, agora: datetime) -> list[Alvo]:
    nomes = [f"siconv_{tabela}.csv.zip" for tabela in TABELAS_DO_SICONV]
    nomes.append(ITENS_DE_LICITACAO_DO_SICONV)
    return [
        Alvo(url, ".csv", csv_so_pj(url, "zip"))
        for url in (f"{SEGES}detru/{nome}" for nome in nomes)
    ]


def _catalogos(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [
        Alvo(f"{SEGES}comprasgov/catalogo_cnbs/{nome}") for nome in CATALOGOS_DA_SEGES
    ]


def _nome_do_pncp(prefixo: str) -> re.Pattern[str]:
    return re.compile(rf"{prefixo}_\d{{4}}_\d{{2}}\.csv\.zip")


# ---------- compras.gov.br ----------


def _dias_da_janela(agora: datetime, dias: int) -> list[date]:
    """Os `dias` dias fechados antes de hoje, do mais velho ao mais novo."""
    hoje = agora.date()
    return [hoje - timedelta(days=n) for n in range(dias, 0, -1)]


def _endereco_dos_resultados(dia: date, pagina: int) -> str:
    dia_texto = dia.isoformat()
    consulta = urlencode(
        {
            "pagina": pagina,
            "tamanhoPagina": POR_PAGINA_DO_COMPRASGOV,
            "dataResultadoPncpInicial": dia_texto,
            "dataResultadoPncpFinal": dia_texto,
        }
    )
    return f"{RESULTADO_DE_ITENS}?{consulta}"


def _resultados_do_comprasgov(resposta: dict) -> tuple[list[dict], bool]:
    return resposta.get("resultado") or [], (resposta.get("paginasRestantes") or 0) > 0


def descobrir_resultados_do_comprasgov(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Um alvo por dia da janela; o dia sem resultado vira `SemArquivo` na hora de obter."""
    return [
        Alvo(
            _endereco_dos_resultados(dia, 1),
            ".jsonl",
            json_paginado(
                lambda pagina, dia=dia: _endereco_dos_resultados(dia, pagina),
                _resultados_do_comprasgov,
                maximo_de_paginas=MAXIMO_DE_PAGINAS_POR_DIA,
                pausa_s=PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS / 2,
            ),
        )
        for dia in _dias_da_janela(agora, DIAS_DO_COMPRASGOV)
    ]


# ---------- Transferegov ----------


def _endereco_do_transferegov(esquema: str, tabela: str, pagina: int) -> str:
    consulta = urlencode(
        {
            "limit": LINHAS_POR_PAGINA_DO_TRANSFEREGOV,
            "offset": (pagina - 1) * LINHAS_POR_PAGINA_DO_TRANSFEREGOV,
            "order": _CHAVES_DO_TRANSFEREGOV.get(tabela, f"id_{tabela}"),
        }
    )
    return f"{API_DO_TRANSFEREGOV}/{esquema}/{tabela}?{consulta}"


# a primeira coluna de cada tabela (conferida em 22/10/2026); o PostgREST só pagina estável com `order`
_CHAVES_DO_TRANSFEREGOV = {
    "plano_acao_especial": "id_plano_acao",
    "executor_especial": "id_executor",
    "empenho_especial": "id_empenho",
    "documento_habil_especial": "id_dh",
    "ordem_pagamento_ordem_bancaria_especial": "id_op_ob",
    "historico_pagamento_especial": "id_historico_op_ob",
    "programa_especial": "id_programa",
    "plano_trabalho_especial": "id_plano_trabalho",
    "programa": "id_programa",
    "plano_acao": "id_plano_acao",
    "termo_execucao": "id_termo",
    "nota_credito": "id_nota",
    "programacao_financeira": "id_programacao",
    "empenho": "id_empenho",
    "termo_adesao": "id_termo_adesao",
}


def _linhas_do_transferegov(resposta: object) -> tuple[list[dict], bool]:
    linhas = resposta if isinstance(resposta, list) else []
    return linhas, len(linhas) == LINHAS_POR_PAGINA_DO_TRANSFEREGOV


def _tabelas_do_transferegov(esquema: str, tabelas: tuple[str, ...]) -> Descobrir:
    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        return [
            Alvo(
                _endereco_do_transferegov(esquema, tabela, 1),
                ".jsonl",
                json_paginado(
                    lambda pagina, tabela=tabela: _endereco_do_transferegov(
                        esquema, tabela, pagina
                    ),
                    _linhas_do_transferegov,
                    maximo_de_paginas=MAXIMO_DE_PAGINAS_DO_TRANSFEREGOV,
                    pausa_s=PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS / 2,
                ),
            )
            for tabela in tabelas
        ]

    return descobrir


# ---------- TCU ----------


def _endereco_dos_inidoneos(pagina: int) -> str:
    consulta = urlencode(
        {"offset": (pagina - 1) * POR_PAGINA_DO_TCU, "limit": POR_PAGINA_DO_TCU}
    )
    return f"{INIDONEOS_DO_TCU}?{consulta}"


def _itens_do_tcu(resposta: dict) -> tuple[list[dict], bool]:
    return resposta.get("items") or [], bool(resposta.get("hasMore"))


def descobrir_inidoneos_do_tcu(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [
        Alvo(
            _endereco_dos_inidoneos(1),
            ".jsonl",
            json_paginado(
                _endereco_dos_inidoneos,
                _itens_do_tcu,
                maximo_de_paginas=MAXIMO_DE_PAGINAS_DO_TCU,
            ),
        )
    ]


# ---------- PNCP ----------


def _endereco_dos_contratos_do_pncp(dia: date, pagina: int) -> str:
    dia_texto = dia.strftime("%Y%m%d")
    consulta = urlencode(
        {
            "dataInicial": dia_texto,
            "dataFinal": dia_texto,
            "pagina": pagina,
            "tamanhoPagina": POR_PAGINA_DO_PNCP,
        }
    )
    return f"{CONTRATOS_DO_PNCP}?{consulta}"


def _contratos_do_pncp(resposta: dict) -> tuple[list[dict], bool]:
    return resposta.get("data") or [], (resposta.get("paginasRestantes") or 0) > 0


def descobrir_contratos_do_pncp(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Um alvo por dia dos últimos `DIAS_DO_PNCP` (`usuarioNome` e a pessoa física saem em `obter_pj`)."""
    return [
        Alvo(
            _endereco_dos_contratos_do_pncp(dia, 1),
            ".jsonl",
            json_paginado(
                lambda pagina, dia=dia: _endereco_dos_contratos_do_pncp(dia, pagina),
                _contratos_do_pncp,
                maximo_de_paginas=MAXIMO_DE_PAGINAS_DO_PNCP,
                pausa_s=PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS,
            ),
        )
        for dia in _dias_da_janela(agora, DIAS_DO_PNCP)
    ]


# ---------- estados (CKAN) ----------


def _csv_do_recurso(recurso: dict) -> bool:
    url = (recurso.get("url") or "").lower()
    return url.endswith((".csv", ".csv.gz"))


def descobrir_csv_do_ckan(portal: str, pacote: str) -> Descobrir:
    """Os CSVs (soltos ou em GZIP) do pacote, cada um só com pessoa jurídica."""

    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        resposta = cliente.ler(f"{portal}/api/3/action/package_show?id={pacote}")
        recursos = json.loads(resposta.conteudo).get("result", {}).get("resources", [])
        alvos = [
            Alvo(
                r["url"],
                ".csv",
                csv_so_pj(
                    r["url"], "gz" if r["url"].lower().endswith(".gz") else "csv"
                ),
            )
            for r in recursos
            if _csv_do_recurso(r)
        ]
        if not alvos:
            raise ErroDeDescoberta(f"{pacote}: pacote sem CSV em {portal}")
        return alvos

    return descobrir


# ---------- as fontes ----------


def fontes() -> list[Fonte]:
    """As fontes do lote, para a lista `FONTES` (os ids seguem a família: `seges-...`, `pncp-...`)."""
    legado = [
        Fonte(
            id_,
            MENSAL,
            _descobrir_na_seges(
                _pastas_por_ano(
                    f"comprasgov/compras_legado/{pasta}", PRIMEIRO_ANO_DO_LEGADO
                ),
                re.compile(r".*\.csv\.zip"),
            ),
            pesada=True,
        )
        for id_, pasta in MODALIDADES_DO_LEGADO.items()
    ]
    transferegov = [
        Fonte(
            id_,
            MENSAL,
            _tabelas_do_transferegov(esquema, tabelas),
            guardado_vale=_baixado_neste_mes(DIAS_DA_ATUALIZACAO_DO_TRANSFEREGOV),
            pausa_minima=PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS,
        )
        for id_, (esquema, tabelas) in TABELAS_DO_TRANSFEREGOV.items()
    ]
    estados = [
        Fonte(
            id_,
            MENSAL,
            descobrir_csv_do_ckan(portal, pacote),
            guardado_vale=_baixado_neste_mes(DIAS_DA_ATUALIZACAO_DOS_ESTADOS),
            pausa_minima=PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS,
        )
        for id_, portal, pacote in (
            ("govmg-compras-contratos", PORTAL_DE_MG, PACOTE_DE_MG),
            ("govsc-contratos", PORTAL_DE_SC, PACOTE_DE_SC),
        )
    ]
    return [
        *(
            Fonte(
                f"seges-pncp-{sufixo}",
                MENSAL,
                _descobrir_na_seges(
                    _pastas_por_mes("comprasgov/pncp", PRIMEIRO_ANO_DO_PNCP),
                    _nome_do_pncp(prefixo),
                ),
                pesada=True,
            )
            for sufixo, prefixo in (
                ("compras", "compra"),
                ("itens", "compra_item"),
                ("resultados", "item_resultado"),
            )
        ),
        *(
            Fonte(
                f"seges-arp-{sufixo}",
                MENSAL,
                _descobrir_na_seges(
                    _pastas_por_ano("comprasgov/arp", PRIMEIRO_ANO_DAS_ATAS),
                    re.compile(rf"{prefixo}_\d{{4}}\.csv\.zip"),
                ),
                pesada=True,
            )
            for sufixo, prefixo in (("atas", "atas"), ("itens", "atas_itens"))
        ),
        *legado,
        Fonte(
            "seges-pesquisa-precos",
            MENSAL,
            _descobrir_na_seges(
                _pastas_por_mes(
                    "comprasgov/pesquisa_precos", PRIMEIRO_ANO_DA_PESQUISA_DE_PRECOS
                ),
                re.compile(r"(material|servico)_\d{4}_\d{2}\.csv\.zip"),
            ),
            pesada=True,
        ),
        Fonte(
            "seges-propostas",
            MENSAL,
            _descobrir_na_seges(
                _pastas_por_mes("comprasgov/propostas", PRIMEIRO_ANO_DAS_PROPOSTAS),
                re.compile(r"propostas-\d{4}-\d{2}\.csv\.zip"),
            ),
            pesada=True,
        ),
        Fonte("seges-catalogo", MENSAL, _catalogos, pesada=True),
        Fonte("seges-siconv", MENSAL, _arquivos_do_siconv, pesada=True),
        Fonte(
            "comprasgov-resultado-itens",
            SEMANAL,
            descobrir_resultados_do_comprasgov,
            guardado_vale=_dia_fechado(DIAS_ATE_FECHAR_O_DIA),
            pausa_minima=PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS,
        ),
        *transferegov,
        Fonte(
            "pncp-contratos",
            SEMANAL,
            descobrir_contratos_do_pncp,
            guardado_vale=_dia_fechado(DIAS_ATE_FECHAR_O_DIA_DO_PNCP),
            pausa_minima=PAUSA_ENTRE_DIAS_EM_SEGUNDOS,
        ),
        Fonte(
            "tcu-inidoneos",
            SEMANAL,
            descobrir_inidoneos_do_tcu,
            pausa_minima=PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS,
        ),
        *estados,
    ]


def termos() -> dict[str, str]:
    """Sem vigia de termos neste lote: a licença vem do decreto, da ficha do portal ou não existe."""
    return {}
