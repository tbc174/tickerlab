"""Lote Brasil, segunda camada, do arquivista (rodada 3 da pesquisa de dados escondidos, 22/10/2026).

Portal da Transparência (CGU: transferências, compras, licitações, despesas, orçamento e emendas),
BNDES (operações, estatísticas e contas), INSS (folha e requerimentos agregados) e os arquivos do SES
da SUSEP que ainda não estavam na base. Cada fonte é um `Fonte` do arquivista (`base/arquivo/coleta.py`);
aqui só se descobre o que baixar e, quando o arquivo traz pessoa física, o que sai **antes** de guardar.
Este módulo não importa `fontes.py` (que importa este): por isso leva cópias pequenas de `_ckan`.

Escolhas (testes em `tests/test_base_arquivo_lote_brasil2.py`):
- **LGPD (ADR 0088): só CNPJ e agregados.** O acervo guarda a linha de um arquivo com documento só se
  o documento é um CNPJ (14 caracteres entre dígitos e `*`, depois de tirar a pontuação); CPF (11),
  CPF mascarado, código estrangeiro, "sigiloso" e documento em branco saem. Colunas de pessoa (autor
  da emenda, gestor do contrato) saem de todas as linhas. O registro diz que o arquivo foi filtrado;
- **ZIP da CGU regravado, com lista fechada:** cada arquivo de dentro do ZIP tem a sua regra; um
  arquivo novo que a CGU ponha no ZIP faz a coleta falhar (alguém lê o cabeçalho e decide), em vez de
  entrar sem filtro. O ZIP regravado é determinístico (mesmas datas, mesma ordem): a mesma origem dá o
  mesmo SHA-256 e a deduplicação do acervo funciona;
- **mês que a CGU ainda não publicou:** o S3 dela responde 403 (não 404) a arquivo que não existe; a
  descoberta confere por HEAD os últimos meses e pega os mais novos que existem. A licitação parou em
  abril de 2024 no portal: a descoberta anda para trás até achá-la;
- **fora do lote, na fila:** cartão de pagamento do governo (CPGF, todo portador é pessoa física),
  CEIS, CNEP, CEPIM e acordos de leniência (já em `cgu-*`, só uso interno, com as pessoas), SES da
  SUSEP com pessoas (administradores, contatos, acionistas, endereços) e os de mais de 250 MB, pacotes
  do BNDES e do INSS com empregados, conselheiros, viagens, benefícios e servidores.
"""

import csv
import io
import json
import re
import unicodedata
import zipfile
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO

import requests

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte
from base.arquivo.obter import extrair_do_zip_remoto, membros_do_zip_remoto

MENSAL = "mensal"
PAINEIS = ("powerbi.com", "app.powerbi", "lookerstudio.google", "datastudio.google")
STATUS_QUE_DIZEM_QUE_NAO_EXISTE = (
    403,
    404,
)  # o S3 da CGU responde 403 ao que não existe

CODIFICACAO_DOS_CSV = (
    "latin-1"  # cp1252 e latin-1 diferem só em 0x80–0x9F; a ida e volta é sem perda
)
SEPARADOR = ";"
LIMITE_DO_CAMPO = (
    50 * 1024**2
)  # há campos de texto longos (objeto de contrato); o padrão é 128 KB
DATA_DO_ZIP = (
    1980,
    1,
    1,
    0,
    0,
    0,
)  # o ZIP regravado não leva a data do momento (SHA-256 estável)
DOCUMENTO_COM_NOME = " - "  # "43588755000161 - NOME DA EMPRESA" (BNDES)
CARACTERES_DO_CNPJ = re.compile(r"[0-9*]{14}")
PONTUACAO_DO_DOCUMENTO = re.compile(r"[.\-/\s]")
# CPF solto no texto: o nome do MEI e do empresário individual é "NOME 02903737789"; os lookarounds
# deixam passar valor em reais ("34762323258,00"), número de processo e CNPJ
CPF_NO_TEXTO = re.compile(
    r"(?<![\d.,/*-])\d{11}(?!\d|[.,/-]\d)|(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)|\*{3}\.\d{3}\.\d{3}-\*{2}"
)
BOM_LIDO_COMO_LATIN_1 = "ï»¿"

# ---- Portal da Transparência (CGU): ZIPs sem chave, no S3 de download ----
RAIZ_DA_CGU = "https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida"
MESES_DA_CGU = 2  # o mês mais novo e o anterior (a CGU revisa o último)
MESES_PARA_TRAS_DA_CGU = (
    36  # quanto a descoberta anda atrás do mês corrente (licitações: abril/2024)
)
ANOS_DO_ORCAMENTO = 2

# ---- BNDES (CKAN) ----
PORTAL_DO_BNDES = "https://dadosabertos.bndes.gov.br"
# bndes-estatisticas: agregados por forma de apoio, porte, UF e setor; entes públicos; cadastros de
# instituições e de itens financiáveis (CNPJ de empresa)
PACOTES_DE_ESTATISTICAS_DO_BNDES = (
    "aprovacoes",
    "consultas",
    "desembolsos",
    "desembolsos-mpme",
    "desembolsos-finame",
    "desembolsos-pos",
    "operacoes-equalizadas",
    "operacoes-com-entes-da-administracao-publica-direta",
    "fontes-recursos",
    "politicas-operacionais",
    "medidas-emergenciais-covid19",
    "instituicoes-financeiras-credenciadas",
    "instituicoes-repassadoras-microcredito",
    "itens-financiaveis",
)
# bndes-contas: as contas do próprio BNDES e a carteira de participações da BNDESPAR
PACOTES_DE_CONTAS_DO_BNDES = (
    "balanco-patrimonial",
    "demonstracao-de-resultados",
    "indicadores-financeiros",
    "indicadores-estrategicos",
    "renda-variavel",
    "distribuicao-dividendos-juros",
    "recebimento-dividendos",
    "emissoes-titulos-externos",
    "execucao-orcamentaria",
    "captacoes-devolucoes-tesouro",
    "saldos-contabeis-repasses-tesouro",
)
FORMATOS_DAS_ESTATISTICAS_DO_BNDES = ("csv", "pdf")
FORMATOS_DAS_CONTAS_DO_BNDES = ("csv", "pdf")
INDIRETAS_AUTOMATICAS = re.compile(r"indiretas-automaticas")
# operações com cliente: só as de CNPJ; o gestor do contrato (empregado) sai
PACOTES_DE_OPERACOES_DO_BNDES = (
    "operacoes-financiamento",
    "operacoes-exportacao",
)
PACOTES_DE_COMPRAS_DO_BNDES = ("compras-contratos-administrativos", "licitacoes")
COLUNAS_DE_PESSOA_DO_BNDES = ("nome_do_gestor",)
# a coluna do documento muda de arquivo para arquivo (cnpj, cpf_cnpj, cnpj_do_exportador...)
COLUNAS_DE_DOCUMENTO_DO_BNDES = (
    "cpf_cnpj",
    "cnpj",
    "cnpj_do_exportador",
    "cnpj_ou_cpf_do_fornecedor",
    "contratado",
)

# ---- INSS (CKAN): só os agregados, sem pessoa ----
PORTAL_DO_INSS = "https://dadosabertos.inss.gov.br"
FOLHA_AGREGADA_DO_INSS = "dados-agregados-da-folha-de-pagamento-beneficios-emitidos-plano-de-dados-abertos-jun-2023-a-dez-2027"
ACORDOS_INTERNACIONAIS_DO_INSS = "acordos"
REQUERIMENTOS_DO_INSS = {
    "inss-requerimentos-pendentes": "dados-de-requerimentos-administrativos-pendentes-plano-de-dados-abertos-jun-2023-a-dez-2027",
    "inss-requerimentos-solicitados": "dados-de-requerimentos-administrativos-solicitados-plano-de-dados-abertos-jun-2023-a-jun-2025",
}
FORMATOS_DAS_PLANILHAS_DO_INSS = ("xlsx", "xls")
RECENTES_DO_INSS = (
    3  # cada CSV de requerimentos tem 30 a 65 MB; os três meses mais novos bastam
)
COMPETENCIA_NA_URL = re.compile(r"(?<!\d)(\d{6})(?!\d)")

# ---- SUSEP: arquivos do SES (ZIP de ~580 MB) que o `susep-ses` não leva; ver `fontes.py` ----
SES_DA_SUSEP = "https://www2.susep.gov.br/download/estatisticas/BaseCompleta.zip"
# fora, de propósito: Administradores, contatos, dependencias (endereço), grupos_economicos, part_acion
# (acionistas) e os de mais de 250 MB (Balanco, rmovram, valoresresmovgrupos); a lista é fechada
CSVS_COMPLEMENTARES_DA_SUSEP = (
    "Ses_campos.csv",
    "Ses_diversos.csv",
    "Ses_limite_ret.csv",
    "LimiteRetProxVig.csv",
    "Ses_pl_margem.csv",
    "Ses_prov.csv",
    "SES_prov_segprev.csv",
    "Ses_seg_prov_det.csv",
    "ses_provramos.csv",
    "Ses_Cessoes_Recebidas.csv",
    "Ses_vgbl_fundos.csv",
    "Ses_vgbl_resgates.csv",
    "ses_pgbl_fundos.csv",
    "ses_pgbl_resgates.csv",
    "ses_pgbl_contrib.csv",
    "ses_pgbl_uf.csv",
    "ses_prev_trad_resgates.csv",
    "ses_prev_uf.csv",
    "ses_prev_cap_uf.csv",
    "ses_quantprev_benef.csv",
    "ses_quantprev_part.csv",
    "Ses_Contrib_Benef.csv",
    "ses_quantcap.csv",
    "ses_cap_uf.csv",
    "Ses_Dados_Cap.csv",
    "ses_transferenciasexternas.csv",
)


# ---------- filtro de pessoa física ----------


@dataclass(frozen=True)
class RegraDoMembro:
    """O que sai de um CSV antes de guardar: colunas de pessoa e, se há documento, a linha sem CNPJ."""

    colunas_fora: tuple[str, ...] = ()
    documento: tuple[
        str, ...
    ] = ()  # nomes possíveis da coluna do CPF/CNPJ; vazio: sem filtro de linha


def _chave(nome: str) -> str:
    """O nome da coluna sem acento, caixa nem espaço nas pontas ("CÓDIGO FAVORECIDO" → "codigo favorecido")."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return sem_acento.strip().lower()


def e_cnpj(valor: str) -> bool:
    """O documento é um CNPJ (com ou sem pontuação, mascarado ou não; CPF, código estrangeiro e vazio não)."""
    documento = valor.split(DOCUMENTO_COM_NOME)[0]
    return bool(CARACTERES_DO_CNPJ.fullmatch(PONTUACAO_DO_DOCUMENTO.sub("", documento)))


def tem_cpf_no_texto(linha: Iterable[str]) -> bool:
    """Algum campo da linha traz um CPF (completo, formatado ou mascarado) no meio do texto."""
    return any(CPF_NO_TEXTO.search(campo) for campo in linha)


def _indices(cabecalho: list[str], nomes: Iterable[str]) -> list[int]:
    procurados = {_chave(n) for n in nomes}
    return [i for i, coluna in enumerate(cabecalho) if _chave(coluna) in procurados]


def filtrar_csv(origem: IO[bytes], destino: IO[bytes], regra: RegraDoMembro) -> int:
    """Copia o CSV (";") sem as colunas de pessoa e, se a regra pede, só com as linhas de CNPJ.

    Devolve quantas linhas ficaram. Coluna de documento que não existe no cabeçalho é erro (a fonte
    mudou de formato: nada é guardado sem filtro); linha com número de colunas diferente do
    cabeçalho sai (não dá para saber qual coluna é qual). Com coluna de documento, sai também a
    linha de CNPJ cujo nome traz o CPF do dono (MEI).
    """
    csv.field_size_limit(LIMITE_DO_CAMPO)
    entrada = _texto(origem)
    saida = _texto(destino)
    leitor = csv.reader(_sem_bom(entrada), delimiter=SEPARADOR)
    escritor = csv.writer(
        saida, delimiter=SEPARADOR, quoting=csv.QUOTE_ALL, lineterminator="\r\n"
    )
    cabecalho = next(leitor, None)
    if cabecalho is None:
        raise ValueError("CSV vazio")
    achados = _indices(cabecalho, regra.documento)
    if regra.documento and len(achados) != 1:
        raise ValueError(
            f"coluna do documento {regra.documento} {len(achados)} vezes no cabeçalho"
        )
    fora = set(_indices(cabecalho, regra.colunas_fora))
    mantidas = [i for i in range(len(cabecalho)) if i not in fora]
    escritor.writerow([cabecalho[i] for i in mantidas])
    mantidas_na_linha = 0
    for linha in leitor:
        if len(linha) != len(cabecalho):
            continue
        if achados and (not e_cnpj(linha[achados[0]]) or tem_cpf_no_texto(linha)):
            continue
        escritor.writerow([linha[i] for i in mantidas])
        mantidas_na_linha += 1
    saida.flush()
    saida.detach()
    return mantidas_na_linha


def _sem_bom(linhas: Iterable[str]) -> Iterator[str]:
    """As linhas do texto sem a marca de ordem de bytes do começo (lida como latin-1: "ï»¿")."""
    iterador = iter(linhas)
    primeira = next(iterador, None)
    if primeira is not None:
        yield primeira.removeprefix(BOM_LIDO_COMO_LATIN_1)
    yield from iterador


def _texto(binario: IO[bytes]) -> io.TextIOWrapper:
    return io.TextIOWrapper(binario, encoding=CODIFICACAO_DOS_CSV, newline="")


def csv_so_cnpj(
    url: str, documento: tuple[str, ...], colunas_fora: tuple[str, ...] = ()
) -> Callable[[Cliente, Path], Mapping[str, str]]:
    """Baixa o CSV e grava em `destino` só as linhas de CNPJ, sem as colunas de pessoa."""
    regra = RegraDoMembro(colunas_fora, documento)

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            with bruto.open("rb") as entrada, destino.open("wb") as saida:
                filtrar_csv(entrada, saida, regra)
        except BaseException:
            destino.unlink(missing_ok=True)  # nunca fica CSV pela metade
            raise
        finally:
            bruto.unlink(missing_ok=True)
        return cabecalhos

    return obter


def _regra_do_membro(
    nome: str, regras: tuple[tuple[str, RegraDoMembro], ...]
) -> RegraDoMembro:
    for padrao, regra in regras:
        if re.search(padrao, nome):
            return regra
    raise ValueError(
        f"{nome}: arquivo sem regra no ZIP da CGU (pode trazer pessoa; alguém lê o cabeçalho e "
        "decide)"
    )


def zip_so_cnpj(
    url: str, regras: tuple[tuple[str, RegraDoMembro], ...]
) -> Callable[[Cliente, Path], Mapping[str, str]]:
    """Baixa o ZIP da CGU e grava em `destino` outro ZIP, com cada CSV passado pela regra dele."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            with (
                zipfile.ZipFile(bruto) as origem,
                zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as novo,
            ):
                for info in sorted(origem.infolist(), key=lambda i: i.filename):
                    regra = _regra_do_membro(info.filename, regras)
                    saida = zipfile.ZipInfo(info.filename, DATA_DO_ZIP)
                    saida.compress_type = zipfile.ZIP_DEFLATED
                    with origem.open(info) as entrada, novo.open(saida, "w") as grava:
                        filtrar_csv(entrada, grava, regra)
        except BaseException:
            destino.unlink(missing_ok=True)  # nunca fica ZIP pela metade
            raise
        finally:
            bruto.unlink(missing_ok=True)
        return cabecalhos

    return obter


# ---------- Portal da Transparência ----------

# nome do arquivo no S3: AAAAMM (ou AAAA) e o conjunto; os nomes de dentro do ZIP trazem acento
# gravado de dois jeitos, então as regras casam só o começo
TRANSFERENCIAS = (
    (
        r"^\d{6}_Transferencias\.csv$",
        RegraDoMembro(documento=("CÓDIGO FAVORECIDO",)),
    ),
)
COMPRAS = (
    (
        r"^\d{6}_Compras\.csv$",
        RegraDoMembro(documento=("Código Contratado",)),
    ),
    (r"^\d{6}_ItemCompra\.csv$", RegraDoMembro()),
    (r"^\d{6}_TermoAditivo\.csv$", RegraDoMembro()),
    (r"^\d{6}_Apostilamento\.csv$", RegraDoMembro()),
)
LICITACOES = (
    (r"^\d{6}_EmpenhosRelacionados\.csv$", RegraDoMembro()),
    (r"^\d{6}_ItemLicita[^.]*\.csv$", RegraDoMembro(documento=("Código Vencedor",))),
    (r"^\d{6}_Licita[^.]*\.csv$", RegraDoMembro()),
    (
        r"^\d{6}_ParticipantesLicita[^.]*\.csv$",
        RegraDoMembro(documento=("Código Participante",)),
    ),
)
# a despesa por ação e unidade gestora; o autor da emenda é parlamentar (pessoa física)
DESPESAS = (
    (
        r"^\d{6}_Despesas\.csv$",
        RegraDoMembro(colunas_fora=("Código Autor Emenda", "Nome Autor Emenda")),
    ),
)
ORCAMENTO = ((r"^\d{4}_OrcamentoDespesa\.csv$", RegraDoMembro()),)
EMENDAS = (
    (
        r"^EmendasParlamentares\.csv$",
        RegraDoMembro(
            colunas_fora=("Código do Autor da Emenda", "Nome do Autor da Emenda")
        ),
    ),
    (r"^EmendasParlamentares_Convenios\.csv$", RegraDoMembro()),
    (
        r"^EmendasParlamentares_PorFavorecido\.csv$",
        RegraDoMembro(
            colunas_fora=("Código do Autor da Emenda", "Nome do Autor da Emenda"),
            documento=("Código do Favorecido",),
        ),
    ),
)


def _existe(cliente: Cliente, url: str) -> bool:
    """O arquivo existe no S3 da CGU (HEAD; 403 e 404 dizem que não)."""
    try:
        cliente.cabecalhos(url)
    except requests.HTTPError as erro:
        resposta = erro.response
        if (
            resposta is not None
            and resposta.status_code in STATUS_QUE_DIZEM_QUE_NAO_EXISTE
        ):
            return False
        raise
    return True


def _periodos(agora: datetime, anual: bool) -> Iterable[str]:
    """O período corrente, depois os anteriores: "202610", "202609"... ou "2026", "2025"..."""
    if anual:
        for ano in range(agora.year, agora.year - MESES_PARA_TRAS_DA_CGU, -1):
            yield f"{ano}"
        return
    ano, mes = agora.year, agora.month
    for _ in range(MESES_PARA_TRAS_DA_CGU):
        yield f"{ano}{mes:02d}"
        ano, mes = (ano, mes - 1) if mes > 1 else (ano - 1, 12)


def descobrir_zips_da_cgu(
    pasta: str,
    arquivo: str,
    regras: tuple[tuple[str, RegraDoMembro], ...],
    *,
    quantos: int = MESES_DA_CGU,
    anual: bool = False,
) -> Descobrir:
    """Os `quantos` períodos mais novos que existem no S3 da CGU (sem chave); nenhum é erro."""

    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        alvos: list[Alvo] = []
        for periodo in _periodos(agora, anual):
            url = f"{RAIZ_DA_CGU}/{pasta}/{arquivo.format(periodo=periodo)}"
            if _existe(cliente, url):
                alvos.append(Alvo(url, ".zip", zip_so_cnpj(url, regras)))
            if len(alvos) == quantos:
                break
        if not alvos:
            raise ErroDeDescoberta(
                f"CGU {pasta}: nenhum arquivo nos últimos {MESES_PARA_TRAS_DA_CGU} períodos"
            )
        return alvos

    return descobrir


def descobrir_emendas_da_cgu(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """O ZIP único das emendas parlamentares (a CGU o reescreve a cada atualização)."""
    url = f"{RAIZ_DA_CGU}/emendas-parlamentares/EmendasParlamentares.zip"
    if not _existe(cliente, url):
        raise ErroDeDescoberta(f"CGU emendas: {url} não existe")
    return [Alvo(url, ".zip", zip_so_cnpj(url, EMENDAS))]


# ---------- CKAN (BNDES, INSS) ----------


def _e_arquivo(recurso: dict) -> bool:
    url = recurso.get("url") or ""
    formato = (recurso.get("format") or "").lower()
    return bool(url) and formato != "html" and not any(p in url for p in PAINEIS)


def _recursos(cliente: Cliente, portal: str, pacote: str) -> list[dict]:
    resposta = cliente.ler(f"{portal}/api/3/action/package_show?id={pacote}")
    recursos = [
        r
        for r in json.loads(resposta.conteudo).get("result", {}).get("resources", [])
        if _e_arquivo(r)
    ]
    if not recursos:
        raise ErroDeDescoberta(f"{pacote}: pacote sem arquivos em {portal}")
    return recursos


def descobrir_ckan(
    cliente: Cliente, portal: str, *pacotes: str, formatos: tuple[str, ...] = ()
) -> list[Alvo]:
    """Os arquivos (recursos) dos pacotes de um portal CKAN; `formatos` escolhe um por recurso."""
    alvos: list[Alvo] = []
    for pacote in pacotes:
        achados = [
            r
            for r in _recursos(cliente, portal, pacote)
            if not formatos or (r.get("format") or "").lower() in formatos
        ]
        if not achados:
            raise ErroDeDescoberta(f"{pacote}: nenhum arquivo nos formatos {formatos}")
        alvos += [Alvo(r["url"]) for r in achados]
    return alvos


def _ckan(portal: str, *pacotes: str, formatos: tuple[str, ...] = ()) -> Descobrir:
    return lambda cliente, agora: descobrir_ckan(
        cliente, portal, *pacotes, formatos=formatos
    )


def descobrir_bndes_so_cnpj(
    pacotes: tuple[str, ...],
    *,
    so_estes: re.Pattern[str] | None = None,
    menos_estes: re.Pattern[str] | None = None,
    colunas_fora: tuple[str, ...] = (),
) -> Descobrir:
    """Os CSVs dos pacotes do BNDES só com as linhas de CNPJ (os PDFs do dicionário vão como estão)."""

    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        alvos: list[Alvo] = []
        for pacote in pacotes:
            for r in _recursos(cliente, PORTAL_DO_BNDES, pacote):
                url, formato = r["url"], (r.get("format") or "").lower()
                if (so_estes and not so_estes.search(url)) or (
                    menos_estes and menos_estes.search(url)
                ):
                    continue
                if formato == "csv":
                    alvos.append(
                        Alvo(
                            url,
                            ".csv",
                            csv_so_cnpj(
                                url, COLUNAS_DE_DOCUMENTO_DO_BNDES, colunas_fora
                            ),
                        )
                    )
                elif formato == "pdf":
                    alvos.append(Alvo(url))
        if not any(a.obter for a in alvos):
            raise ErroDeDescoberta(f"BNDES {pacotes}: nenhum CSV de operações")
        return alvos

    return descobrir


def _competencia(alvo: Alvo) -> str:
    achados = COMPETENCIA_NA_URL.findall(alvo.url)
    return achados[-1] if achados else ""


def descobrir_inss_recentes(pacote: str, quantos: int = RECENTES_DO_INSS) -> Descobrir:
    """Os CSVs dos `quantos` meses mais novos do pacote (o mês está no nome: `..._PEND_202609.csv`)."""

    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        alvos = descobrir_ckan(cliente, PORTAL_DO_INSS, pacote, formatos=("csv",))
        return sorted(alvos, key=_competencia)[-quantos:]

    return descobrir


# ---------- SUSEP ----------


def descobrir_susep_complementos(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os CSVs complementares de dentro do ZIP do SES (o endereço guarda `zip#arquivo`)."""
    membros = set(membros_do_zip_remoto(cliente, SES_DA_SUSEP))
    if faltam := [m for m in CSVS_COMPLEMENTARES_DA_SUSEP if m not in membros]:
        raise ErroDeDescoberta(f"SUSEP: o ZIP do SES não tem {', '.join(faltam)}")
    return [
        Alvo(
            f"{SES_DA_SUSEP}#{membro}",
            ".csv",
            extrair_do_zip_remoto(SES_DA_SUSEP, membro),
        )
        for membro in CSVS_COMPLEMENTARES_DA_SUSEP
    ]


# ---------- as fontes ----------


def fontes() -> list[Fonte]:
    """As fontes do lote, para a lista `FONTES` (os ids seguem a família: `transparencia-...`, `bndes-...`)."""
    transparencia = [
        Fonte(
            "transparencia-transferencias",
            MENSAL,
            descobrir_zips_da_cgu(
                "transferencias", "{periodo}_Transferencias.zip", TRANSFERENCIAS
            ),
            pesada=True,
        ),
        Fonte(
            "transparencia-compras",
            MENSAL,
            descobrir_zips_da_cgu("compras", "{periodo}_Compras.zip", COMPRAS),
            pesada=True,
        ),
        Fonte(
            "transparencia-licitacoes",
            MENSAL,
            descobrir_zips_da_cgu(
                "licitacoes", "{periodo}_Licitacoes.zip", LICITACOES, quantos=1
            ),
            pesada=True,
        ),
        Fonte(
            "transparencia-despesas",
            MENSAL,
            descobrir_zips_da_cgu(
                "despesas-execucao", "{periodo}_Despesas.zip", DESPESAS
            ),
            pesada=True,
        ),
        Fonte(
            "transparencia-orcamento",
            MENSAL,
            descobrir_zips_da_cgu(
                "orcamento-despesa",
                "{periodo}_OrcamentoDespesa.zip",
                ORCAMENTO,
                quantos=ANOS_DO_ORCAMENTO,
                anual=True,
            ),
            pesada=True,
        ),
        Fonte("transparencia-emendas", MENSAL, descobrir_emendas_da_cgu, pesada=True),
    ]
    bndes = [
        Fonte(
            "bndes-estatisticas",
            MENSAL,
            _ckan(
                PORTAL_DO_BNDES,
                *PACOTES_DE_ESTATISTICAS_DO_BNDES,
                formatos=FORMATOS_DAS_ESTATISTICAS_DO_BNDES,
            ),
            pesada=True,
        ),
        Fonte(
            "bndes-desembolsos-mensais",
            MENSAL,
            _ckan(
                PORTAL_DO_BNDES,
                "desembolsos-mensais",
                formatos=FORMATOS_DAS_ESTATISTICAS_DO_BNDES,
            ),
            pesada=True,
        ),
        Fonte(
            "bndes-contas",
            MENSAL,
            _ckan(
                PORTAL_DO_BNDES,
                *PACOTES_DE_CONTAS_DO_BNDES,
                formatos=FORMATOS_DAS_CONTAS_DO_BNDES,
            ),
            pesada=True,
        ),
        Fonte(
            "bndes-operacoes",
            MENSAL,
            descobrir_bndes_so_cnpj(
                PACOTES_DE_OPERACOES_DO_BNDES, menos_estes=INDIRETAS_AUTOMATICAS
            ),
            pesada=True,
        ),
        # 1,2 GB: fonte à parte, para a falha de uma não derrubar a outra
        Fonte(
            "bndes-operacoes-indiretas",
            MENSAL,
            descobrir_bndes_so_cnpj(
                ("operacoes-financiamento",), so_estes=INDIRETAS_AUTOMATICAS
            ),
            pesada=True,
        ),
        Fonte(
            "bndes-compras",
            MENSAL,
            descobrir_bndes_so_cnpj(
                PACOTES_DE_COMPRAS_DO_BNDES, colunas_fora=COLUNAS_DE_PESSOA_DO_BNDES
            ),
            pesada=True,
        ),
    ]
    inss = [
        Fonte(
            "inss-folha-agregada",
            MENSAL,
            _ckan(
                PORTAL_DO_INSS,
                FOLHA_AGREGADA_DO_INSS,
                formatos=FORMATOS_DAS_PLANILHAS_DO_INSS,
            ),
        ),
        Fonte(
            "inss-acordos-internacionais",
            MENSAL,
            _ckan(
                PORTAL_DO_INSS,
                ACORDOS_INTERNACIONAIS_DO_INSS,
                formatos=FORMATOS_DAS_PLANILHAS_DO_INSS,
            ),
        ),
        *(
            Fonte(id_, MENSAL, descobrir_inss_recentes(pacote), pesada=True)
            for id_, pacote in REQUERIMENTOS_DO_INSS.items()
        ),
    ]
    return [
        *transparencia,
        *bndes,
        *inss,
        Fonte(
            "susep-ses-complementos", MENSAL, descobrir_susep_complementos, pesada=True
        ),
    ]
