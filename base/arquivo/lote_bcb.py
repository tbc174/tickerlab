"""Lote BCB e SICONFI da rodada 1 da pesquisa de dados escondidos (22/10/2026, linha 242 da fila).

O que o arquivista passa a guardar, sempre como veio (nome de pessoa não entra: só CNPJ, agregados e
contas públicas):

- Olinda do Banco Central: Mercado Imobiliário, STR, panorama de consórcios, leilões do Selic
  (títulos públicos e swap) e tarifas por banco listado;
- balancetes COSIF (documento 4010) dos bancos listados na B3;
- SICONFI do Tesouro: entes, extrato de entregas, RREO, RGF (Executivo) e DCA dos estados e das capitais.

Regras (testes em `tests/test_base_arquivo_lote_bcb.py`):
- a lista de bancos vem do cadastro da CVM que o arquivista já guardou (setor "Bancos", situação
  ativa), nunca digitada; sem esse cadastro a descoberta falha;
- o Olinda responde `value: []` para o que ainda não saiu: isso é `SemArquivo`, nunca "ok";
- o SICONFI pagina por `limit` e `offset`; só os itens são guardados (o JSON traz `links` para um host
  interno da Oracle, que não serve a ninguém); relatório sem item é `SemArquivo`;
- exercício já fechado (o do ano passado, depois de abril, ou mais velho) não é baixado de novo.

Ficou de fora, por falha ao vivo em 22/10/2026 (cada um é linha da fila): `taxaJuros` (o mensal vem
vazio e o diário dá 500), SICOR do Olinda (500 e tempo esgotado), PagamentosIntradia,
PortabilidadeDeCreditoPessoaNatural, leilões de compromissadas e depósitos voluntários (parâmetros que
o serviço recusa) e o histórico do COSIF e do SICONFI.
"""

import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from pathlib import Path

import sqlalchemy as sa

from base.arquivo.coleta import (
    Alvo,
    Cliente,
    Descobrir,
    ErroDeDescoberta,
    Fonte,
    Obter,
    SemArquivo,
)
from base.arquivo.obter import zip_que_pode_faltar
from base.cadastro import cadastro_do_acervo
from src.banco.conexao import obter_engine

OLINDA = "https://olinda.bcb.gov.br/olinda/servico/"
COSIF = (
    "https://www4.bcb.gov.br/fis/cosif/cont/balan/individualizados/"
    "{mes}/4010/{mes}-4010-{cnpj}.ZIP"
)
SICONFI = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"

MERCADO_IMOBILIARIO = (
    OLINDA + "MercadoImobiliario/versao/v1/odata/mercadoimobiliario?$format=json"
)
STR = OLINDA + "STR/versao/v1/odata/{entidade}?$format=json"
# as sete entidades do STR que responderam inteiras em 22/10/2026
ENTIDADES_DO_STR = (
    "GiroEvolucaoDiaria",
    "TEDEvolucaoDiaria",
    "RedescontoBCBIntradia",
    "PortabilidadeDeCredito",
    "PortabilidadeDeCreditoPJEArrendamentoMercantil",
    "GiroDetalhamento",
    "TEDHistograma21Dias",
)
CONSORCIOS = OLINDA + "PANORAMA_DE_CONSORCIOS/versao/v1/odata/"
METRICAS_DOS_CONSORCIOS = (
    CONSORCIOS + "Metricas(DataBase=@DataBase)?@DataBase={mes}&$format=json"
)
# o dicionário das métricas e dos grupos, para ler o panorama
CADASTROS_DOS_CONSORCIOS = (
    CONSORCIOS + "GrupoDeMetricas()?$format=json",
    CONSORCIOS + "CadastroDeMetricas()?$format=json",
)
TRIMESTRES_DOS_CONSORCIOS = 8  # o panorama só tem dado nos fins de trimestre
# todos os parâmetros vão na chamada, nulos onde não se usa; a data final distante pede a série toda
LEILOES = OLINDA + (
    "leiloes_selic/versao/v1/odata/leiloesTitulosPublicos("
    "dataMovimentoInicio=@a,dataMovimentoFim=@b,dataLiquidacao=@c,codigoTitulo=@d,"
    "dataVencimento=@e,edital=@f,tipoPublico=@g,tipoOferta=@h)"
    "?@a='2000-01-01'&@b='2099-12-31'&@c=null&@d=null&@e=null&@f=null&@g=null&@h=null"
    "&$format=json"
)
LEILOES_DE_SWAP = OLINDA + (
    "leiloes_selic/versao/v1/odata/leiloesContratosSwap("
    "dataMovimentoInicio=@a,dataMovimentoFim=@b,dataLiquidacao=@c,edital=@d,"
    "tipoPublico=@e,dataVencimento=@f,tipoOferta=@g)"
    "?@a='2000-01-01'&@b='2099-12-31'&@c=null&@d=null&@e=null&@f=null&@g=null"
    "&$format=json"
)
TARIFAS = OLINDA + (
    "Informes_ListaTarifasPorInstituicaoFinanceira/versao/v1/odata/"
    "ListaTarifasPorInstituicaoFinanceira(PessoaFisicaOuJuridica=@p,CNPJ=@c)"
    "?@p='J'&@c='{cnpj}'&$format=json"
)
MESES_DO_COSIF = 12  # o BC publica com meses de atraso: o que ainda não saiu volta 404

ENTES = SICONFI + "entes"
ENTREGAS = SICONFI + "extrato_entregas?id_ente={ente}&an_referencia={ano}"
RREO = (
    SICONFI
    + "rreo?an_exercicio={ano}&nr_periodo={periodo}&co_tipo_demonstrativo=RREO&id_ente={ente}"
)
RGF = (
    SICONFI + "rgf?an_exercicio={ano}&in_periodicidade=Q&nr_periodo={periodo}"
    "&co_tipo_demonstrativo=RGF&co_poder=E&id_ente={ente}"
)
DCA = SICONFI + "dca?an_exercicio={ano}&id_ente={ente}"
LIMITE_DA_PAGINA = 5000
MAXIMO_DE_PAGINAS = 100
# esfera "E" são os estados e "D" é o Distrito Federal; a capital vem marcada com "1" (a coluna
# chega com espaços à direita)
ESFERAS_ESTADUAIS = ("E", "D")
MARCA_DE_CAPITAL = "1"
MESES_DO_BIMESTRE = 2  # o RREO é bimestral e o RGF, quadrimestral
MESES_DO_QUADRIMESTRE = 4
PERIODOS_DO_RREO = range(1, 7)
PERIODOS_DO_RGF = range(1, 4)
ANOS_DA_DCA = 3  # a DCA de um ano sai no ano seguinte
ULTIMO_MES_DO_PRAZO_DO_ANO_ANTERIOR = (
    4  # a DCA vence em abril; o RREO e o RGF, em janeiro
)
ANO_NA_URL = re.compile(r"(?:an_exercicio|an_referencia)=(\d{4})")
DIGITOS_DA_RAIZ_DO_CNPJ = 8


def olinda_com_dados(url: str) -> Obter:
    """Baixa o JSON do Olinda; a lista `value` vazia (o que ainda não saiu) vira `SemArquivo`."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        cabecalhos = cliente.baixar(url, destino)
        try:
            itens = json.loads(destino.read_bytes())["value"]
        except (ValueError, KeyError) as erro:
            raise ValueError("o Olinda não devolveu a lista `value`") from erro
        if not itens:
            raise SemArquivo("o Olinda respondeu a lista vazia (ainda não publicou)")
        return cabecalhos

    return obter


def itens_do_siconfi(
    cliente: Cliente, url: str
) -> tuple[list[dict], Mapping[str, str]]:
    """Todos os itens da consulta (página a página) e os cabeçalhos da primeira resposta."""
    itens: list[dict] = []
    cabecalhos: Mapping[str, str] = {}
    for _ in range(MAXIMO_DE_PAGINAS):
        separador = "&" if "?" in url else "?"
        resposta = cliente.ler(
            f"{url}{separador}limit={LIMITE_DA_PAGINA}&offset={len(itens)}"
        )
        if not itens:
            cabecalhos = resposta.cabecalhos
        pagina = json.loads(resposta.conteudo.decode("utf-8", errors="replace"))
        itens.extend(pagina["items"])
        if not pagina.get("hasMore"):
            return itens, cabecalhos
    raise ValueError(f"SICONFI com mais de {MAXIMO_DE_PAGINAS} páginas em {url}")


def siconfi_em_json(url: str) -> Obter:
    """Guarda só os `items` da consulta (sem os `links` da Oracle); sem item é `SemArquivo`."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        itens, cabecalhos = itens_do_siconfi(cliente, url)
        if not itens:
            raise SemArquivo("o SICONFI não tem item (relatório ainda não entregue)")
        destino.write_text(
            json.dumps({"items": itens}, ensure_ascii=False), encoding="utf-8"
        )
        return cabecalhos

    return obter


def codigos_de_estados_e_capitais(entes: list[dict]) -> list[int]:
    """Os códigos do IBGE dos 26 estados, do Distrito Federal e das 27 capitais, em ordem."""
    return sorted(
        {
            int(ente["cod_ibge"])
            for ente in entes
            if ente["esfera"] in ESFERAS_ESTADUAIS
            or str(ente["capital"]).strip() == MARCA_DE_CAPITAL
        }
    )


def _bimestre_ou_quadrimestre_pode_ter_saido(
    ano: int, periodo: int, meses_do_periodo: int, agora: datetime
) -> bool:
    """O período já fechou? (o ente tem até 30 dias para entregar: pedir antes só traz lista vazia)"""
    return ano < agora.year or agora.month > periodo * meses_do_periodo


def urls_do_rreo(ente: int, agora: datetime) -> list[str]:
    return [
        RREO.format(ano=ano, periodo=periodo, ente=ente)
        for ano in (agora.year - 1, agora.year)
        for periodo in PERIODOS_DO_RREO
        if _bimestre_ou_quadrimestre_pode_ter_saido(
            ano, periodo, MESES_DO_BIMESTRE, agora
        )
    ]


def urls_do_rgf(ente: int, agora: datetime) -> list[str]:
    return [
        RGF.format(ano=ano, periodo=periodo, ente=ente)
        for ano in (agora.year - 1, agora.year)
        for periodo in PERIODOS_DO_RGF
        if _bimestre_ou_quadrimestre_pode_ter_saido(
            ano, periodo, MESES_DO_QUADRIMESTRE, agora
        )
    ]


def urls_da_dca(ente: int, agora: datetime) -> list[str]:
    return [
        DCA.format(ano=ano, ente=ente)
        for ano in range(agora.year - ANOS_DA_DCA, agora.year)
    ]


def urls_das_entregas(ente: int, agora: datetime) -> list[str]:
    return [ENTREGAS.format(ente=ente, ano=ano) for ano in (agora.year - 1, agora.year)]


def _por_ente(urls_do_ente: Callable[[int, datetime], list[str]]) -> Descobrir:
    """Um alvo por consulta de cada estado e capital da lista de entes do SICONFI."""

    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        entes, _ = itens_do_siconfi(cliente, ENTES)
        codigos = codigos_de_estados_e_capitais(entes)
        if not codigos:
            raise ErroDeDescoberta("SICONFI: nenhum estado nem capital em `entes`")
        return [
            Alvo(url, ".json", siconfi_em_json(url))
            for codigo in codigos
            for url in urls_do_ente(codigo, agora)
        ]

    return descobrir


def _os_entes(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [Alvo(ENTES, ".json", siconfi_em_json(ENTES))]


def exercicio_fechado(url: str, hoje: date) -> bool:
    """O exercício da consulta já não muda? O do ano passado fecha em abril; os mais velhos já fecharam."""
    achado = ANO_NA_URL.search(url)
    if achado is None:
        return False
    anos_atras = hoje.year - int(achado.group(1))
    return anos_atras >= 2 or (
        anos_atras == 1 and hoje.month > ULTIMO_MES_DO_PRAZO_DO_ANO_ANTERIOR
    )


def _exercicio_ja_guardado(anterior: sa.Row) -> bool:
    return exercicio_fechado(anterior.url, datetime.now(UTC).date())


def _olinda(url: str) -> Alvo:
    return Alvo(url, ".json")


def _olinda_com_dados(url: str) -> Alvo:
    return Alvo(url, ".json", olinda_com_dados(url))


def trimestres_fechados(agora: datetime, quantos: int) -> list[str]:
    """Os últimos `quantos` fins de trimestre (AAAAMM) até o mês de `agora`, em ordem."""
    meses: list[str] = []
    ano, mes = agora.year, agora.month
    while len(meses) < quantos:
        if mes % 3 == 0:
            meses.append(f"{ano}{mes:02d}")
        ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    return sorted(meses)


def meses_fechados(agora: datetime, quantos: int) -> list[str]:
    """Os `quantos` meses (AAAAMM) fechados antes de `agora`, em ordem."""
    meses: list[str] = []
    ano, mes = agora.year, agora.month
    for _ in range(quantos):
        ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
        meses.append(f"{ano}{mes:02d}")
    return sorted(meses)


def descobrir_str(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [_olinda(STR.format(entidade=e)) for e in ENTIDADES_DO_STR]


def descobrir_consorcios(cliente: Cliente, agora: datetime) -> list[Alvo]:
    metricas = [
        _olinda_com_dados(METRICAS_DOS_CONSORCIOS.format(mes=mes))
        for mes in trimestres_fechados(agora, TRIMESTRES_DOS_CONSORCIOS)
    ]
    return [*(_olinda(url) for url in CADASTROS_DOS_CONSORCIOS), *metricas]


def descobrir_leiloes(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [_olinda(LEILOES), _olinda(LEILOES_DE_SWAP)]


def cnpjs_dos_bancos_listados() -> list[str]:
    """A raiz do CNPJ (8 dígitos) de cada banco ativo do cadastro da CVM guardado no acervo."""
    with obter_engine().connect() as conexao:
        achado = cadastro_do_acervo(conexao)
    if achado is None:
        return []
    cadastro, _ = achado
    bancos = cadastro[
        (cadastro["setor"] == "Bancos") & (cadastro["situacao"] == "ATIVO")
    ]
    raizes = {
        "".join(c for c in cnpj if c.isdigit()).zfill(14)[:DIGITOS_DA_RAIZ_DO_CNPJ]
        for cnpj in bancos["cnpj"]
    }
    return sorted(raizes)


def _por_banco(
    alvos_do_banco: Callable[[str, datetime], list[Alvo]],
    ler_cnpjs: Callable[[], list[str]],
) -> Descobrir:
    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        cnpjs = ler_cnpjs()
        if not cnpjs:
            raise ErroDeDescoberta(
                "nenhum banco listado no cadastro da CVM do acervo (o arquivista ainda não o guardou?)"
            )
        return [alvo for cnpj in cnpjs for alvo in alvos_do_banco(cnpj, agora)]

    return descobrir


def _tarifas_do_banco(cnpj: str, agora: datetime) -> list[Alvo]:
    return [_olinda_com_dados(TARIFAS.format(cnpj=cnpj))]


def _balancetes_do_banco(cnpj: str, agora: datetime) -> list[Alvo]:
    urls = [
        COSIF.format(mes=mes, cnpj=cnpj)
        for mes in meses_fechados(agora, MESES_DO_COSIF)
    ]
    return [Alvo(url, ".zip", zip_que_pode_faltar(url)) for url in urls]


def fontes(
    ler_cnpjs: Callable[[], list[str]] = cnpjs_dos_bancos_listados,
) -> list[Fonte]:
    """As fontes do lote, para a lista `FONTES` (os ids seguem a família: `bcb-...`, `tesouro-br-...`)."""
    return [
        Fonte(
            "bcb-mercado-imobiliario",
            "mensal",
            lambda cliente, agora: [_olinda(MERCADO_IMOBILIARIO)],
            "json",
        ),
        Fonte("bcb-str", "semanal", descobrir_str, "json"),
        Fonte("bcb-consorcios", "mensal", descobrir_consorcios, "json"),
        Fonte("bcb-leiloes-selic", "semanal", descobrir_leiloes, "json"),
        Fonte(
            "bcb-tarifas-instituicao",
            "mensal",
            _por_banco(_tarifas_do_banco, ler_cnpjs),
            "json",
        ),
        Fonte(
            "bcb-cosif",
            "mensal",
            _por_banco(_balancetes_do_banco, ler_cnpjs),
            "zip",
        ),
        Fonte("tesouro-br-siconfi-entes", "mensal", _os_entes, "json"),
        Fonte(
            "tesouro-br-siconfi-entregas",
            "mensal",
            _por_ente(urls_das_entregas),
            "json",
            guardado_vale=_exercicio_ja_guardado,
        ),
        Fonte(
            "tesouro-br-siconfi-rreo",
            "mensal",
            _por_ente(urls_do_rreo),
            "json",
            guardado_vale=_exercicio_ja_guardado,
        ),
        Fonte(
            "tesouro-br-siconfi-rgf",
            "mensal",
            _por_ente(urls_do_rgf),
            "json",
            guardado_vale=_exercicio_ja_guardado,
        ),
        Fonte(
            "tesouro-br-siconfi-dca",
            "mensal",
            _por_ente(urls_da_dca),
            "json",
            guardado_vale=_exercicio_ja_guardado,
        ),
    ]
