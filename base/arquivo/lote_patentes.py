"""Lote patentes e marcas do arquivista (rodada 4 da pesquisa de dados escondidos, 23/10/2026;
ADR 0102: licença lida vira marca, coleta com ritmo, uso citando a fonte).

Três famílias, uma por provedor (a família decide a licença e a marca em `src/banco/coletas.py`):
- **INPI** (`inpi-*`, dados abertos, marca `a_confirmar`): marcas, desenhos industriais, programas
  de computador, os pedidos de patente que o lote setoriais não pegou (titulares, prioridades,
  renumerações) e as partes dos contratos de tecnologia. O que já está em `lote_setoriais`
  (dados bibliográficos, IPC, vínculos e despachos de patentes; dados básicos e despachos de
  contratos) não se repete;
- **EPO Linked open EP data** (`epo-*`, SPARQL, CC BY 4.0, vendável com atribuição): as publicações
  de patente europeia de uma lista de empresas, um pedido por empresa, nunca no horário europeu;
- **WIPO IP Statistics** (`wipo-*`, só uso interno): os ZIPs de indicadores de patentes, marcas e
  desenhos industriais (citar "WIPO Statistics Database"; não republicar nem revender).

Regras (testes em `tests/test_base_arquivo_lote_patentes.py`):
- **LGPD no INPI** (nível 1 da ADR 0101: nada além disto sem o "pode" do Tiago): pessoa física só
  entra como contagem. O titular só fica com nome e documento se o documento for um CNPJ de 14
  dígitos; estrangeiro, pessoa física, "N/D" e vazio têm o nome e o documento esvaziados (ficam o
  país, o estado e o tipo, que viram contagem). O representante legal e o procurador nunca entram.
  Inventores e autores viram uma linha por pedido com a quantidade (nunca o nome). Contratos: o INPI
  não dá documento das partes, então os nomes de cedente e cessionária ficam de fora também;
- **fora de propósito, anotado na fila:** classificações NICE, Viena e nacionais das marcas, os
  despachos (texto livre com nome de pessoa), o conteúdo das patentes (758 MB de texto), os
  procuradores e a RPI em texto (403 do próprio INPI);
- **servidor instável:** o INPI recusa HEAD (500), então as fontes não são `pesada`; o
  `guardado_vale` evita baixar de novo o que foi baixado há menos de um mês e o `ClienteHttp` já
  retenta com espera crescente;
- **EPO por nome exato:** a busca por trecho do nome estoura o tempo (503); só o nome exato do
  depositante (`vcard:fn`) responde rápido. A lista é uma semente a ampliar (ver a fila). Nunca se
  consulta o inventor (`inventorVC`: pessoas). O serviço "não foi feito para ser banco de dados de
  retaguarda": um pedido por vez, pausa entre eles, e só de 19h a 7h GMT (fora do dia europeu);
- **USPTO ODP/PatentsView e EPO OPS ficam fora**: dependem de conta e chave (linha própria na fila).
"""

import csv
import hashlib
import io
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO
from urllib.parse import urlencode

from base.arquivo.coleta import (
    Alvo,
    Cliente,
    Descobrir,
    Fonte,
    Obter,
    SemArquivo,
)
from base.arquivo.lote_brasil2 import CPF_NO_TEXTO, LIMITE_DO_CAMPO
from base.arquivo.lote_setoriais import RAIZ_DO_INPI, _baixado_neste_mes

MENSAL = "mensal"
PAUSA_DO_EPO_EM_SEGUNDOS = 5.0
HORA_EM_QUE_A_EUROPA_ACORDA = 7  # GMT: de 7h a 19h o EPO atende o expediente
HORA_EM_QUE_A_EUROPA_DORME = 19
CODIFICACAO_DO_INPI = "utf-8-sig"  # UTF-8, às vezes com a marca de ordem de bytes
PONTUACAO_DO_DOCUMENTO = re.compile(r"[.\-/\s]")
CNPJ_DE_14_DIGITOS = re.compile(r"\d{14}")


# ---------- INPI: filtro de pessoa física ----------


@dataclass(frozen=True)
class RegraDoInpi:
    """O que sai de um CSV do INPI antes de guardar (vírgula, UTF-8)."""

    colunas_fora: tuple[str, ...] = ()  # nunca entram (representante legal, anotações)
    documento: str | None = None  # coluna do CPF/CNPJ do titular
    nomes: tuple[str, ...] = ()  # esvaziadas quando o documento não é CNPJ
    texto: tuple[str, ...] = ()  # esvaziadas quando trazem CPF no meio do texto


@dataclass(frozen=True)
class RegraDeContagem:
    """Um arquivo de inventores ou autores vira `numero_inpi,quantidade_de_autores`."""

    autor: str  # a coluna do nome (só serve para contar; o nome nunca é gravado)


Tratamento = RegraDoInpi | RegraDeContagem | None


def e_cnpj_do_inpi(documento: str) -> bool:
    """O documento é um CNPJ completo (14 dígitos, com ou sem pontuação). CPF, máscara e vazio, não."""
    return bool(CNPJ_DE_14_DIGITOS.fullmatch(PONTUACAO_DO_DOCUMENTO.sub("", documento)))


def _leitor(origem: IO[bytes]) -> tuple[Iterator[list[str]], list[str]]:
    csv.field_size_limit(LIMITE_DO_CAMPO)
    texto = io.TextIOWrapper(origem, encoding=CODIFICACAO_DO_INPI, newline="")
    leitor = csv.reader(texto)
    cabecalho = [c.strip() for c in next(leitor, [])]
    if not cabecalho:
        raise ValueError("CSV vazio")
    return leitor, cabecalho


def _indice(cabecalho: list[str], coluna: str) -> int:
    achadas = [i for i, c in enumerate(cabecalho) if c == coluna]
    if len(achadas) != 1:
        raise ValueError(f"coluna {coluna!r} {len(achadas)} vezes no cabeçalho")
    return achadas[0]


def _indices(cabecalho: list[str], colunas: Iterable[str]) -> list[int]:
    return [_indice(cabecalho, c) for c in colunas]


def filtrar_titulares(origem: IO[bytes], destino: IO[bytes], regra: RegraDoInpi) -> int:
    """Copia o CSV sem as colunas de pessoa e com o titular que não é CNPJ sem nome nem documento.

    Devolve quantas linhas foram gravadas. Coluna da regra que não está no cabeçalho é erro (a fonte
    mudou de formato: nada é guardado sem filtro); linha com número de colunas diferente do
    cabeçalho sai (não dá para saber qual coluna é qual).
    """
    leitor, cabecalho = _leitor(origem)
    fora = set(_indices(cabecalho, regra.colunas_fora))
    mantidas = [i for i in range(len(cabecalho)) if i not in fora]
    i_documento = _indice(cabecalho, regra.documento) if regra.documento else None
    nomes = _indices(cabecalho, regra.nomes)
    texto = _indices(cabecalho, regra.texto)
    saida = io.TextIOWrapper(destino, encoding="utf-8", newline="")
    escritor = csv.writer(saida, lineterminator="\n")
    escritor.writerow([cabecalho[i] for i in mantidas])
    gravadas = 0
    for linha in leitor:
        if len(linha) != len(cabecalho):
            continue
        linha = [c.strip() for c in linha]
        if i_documento is not None and not e_cnpj_do_inpi(linha[i_documento]):
            for i in (i_documento, *nomes):
                linha[i] = ""
        for i in texto:
            if CPF_NO_TEXTO.search(linha[i]):
                linha[i] = ""
        for i in nomes:
            if CPF_NO_TEXTO.search(
                linha[i]
            ):  # MEI: o nome da empresa traz o CPF do dono
                linha[i] = ""
        escritor.writerow([linha[i] for i in mantidas])
        gravadas += 1
    saida.flush()
    saida.detach()
    return gravadas


def contar_autores(
    origem: IO[bytes], destino: IO[bytes], regra: RegraDeContagem
) -> int:
    """Grava `numero_inpi,quantidade_de_autores`, ordenado; o nome do autor nunca sai da memória.

    A quantidade é a maior `ordem` do pedido, quando o arquivo tem essa coluna; sem ela, é o número
    de nomes diferentes (contados pelo resumo do nome, não pelo nome).
    """
    leitor, cabecalho = _leitor(origem)
    i_numero = _indice(cabecalho, "numero_inpi")
    i_autor = _indice(cabecalho, regra.autor)
    i_ordem = cabecalho.index("ordem") if "ordem" in cabecalho else None
    maior_ordem: dict[str, int] = {}
    distintos: dict[str, set[bytes]] = {}
    for linha in leitor:
        if len(linha) != len(cabecalho):
            continue
        numero = linha[i_numero].strip()
        ordem = linha[i_ordem].strip() if i_ordem is not None else ""
        if ordem.isdigit():
            maior_ordem[numero] = max(maior_ordem.get(numero, 0), int(ordem))
        elif linha[i_autor].strip():
            resumo = hashlib.blake2b(
                linha[i_autor].strip().casefold().encode(), digest_size=8
            ).digest()
            distintos.setdefault(numero, set()).add(resumo)
    saida = io.TextIOWrapper(destino, encoding="utf-8", newline="")
    escritor = csv.writer(saida, lineterminator="\n")
    escritor.writerow(["numero_inpi", "quantidade_de_autores"])
    numeros = sorted(maior_ordem.keys() | distintos.keys())
    for numero in numeros:
        quantidade = max(maior_ordem.get(numero, 0), len(distintos.get(numero, ())))
        escritor.writerow([numero, quantidade])
    saida.flush()
    saida.detach()
    return len(numeros)


def tratar_csv_do_inpi(url: str, tratamento: Tratamento) -> Obter:
    """Baixa o CSV e grava em `destino` o que a regra deixa; nunca fica arquivo pela metade."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            with bruto.open("rb") as entrada, destino.open("wb") as saida:
                if isinstance(tratamento, RegraDeContagem):
                    contar_autores(entrada, saida, tratamento)
                else:
                    filtrar_titulares(entrada, saida, tratamento or RegraDoInpi())
        except BaseException:
            destino.unlink(missing_ok=True)
            raise
        finally:
            bruto.unlink(missing_ok=True)
        return cabecalhos

    return obter


# ---------- INPI: o que se coleta ----------

REPRESENTANTE_DAS_MARCAS = (
    "nome_representante_legal",
    "cnpj_cpf_representante_legal",
    "tipo_pfpj_representante_legal",
)
TITULAR_DE_PATENTE_OU_DESENHO = RegraDoInpi(
    documento="cgccpfdepositante", nomes=("depositante",)
)
# id da fonte → (caminho dentro de /download/, tratamento). Sem tratamento: o arquivo não tem coluna
# de pessoa e vai como veio
ARQUIVOS_DO_INPI: dict[str, tuple[tuple[str, Tratamento], ...]] = {
    "inpi-patentes-partes": (
        ("patentes/PATENTES_DEPOSITANTES.csv", TITULAR_DE_PATENTE_OU_DESENHO),
        ("patentes/PATENTES_INVENTORES.csv", RegraDeContagem("autor")),
        ("patentes/PATENTES_PRIORIDADES.csv", None),
        ("patentes/PATENTES_RENUMERACOES.csv", None),
    ),
    "inpi-marcas": (
        # a "apostila" é anotação em texto livre (já houve nome de pessoa nela)
        (
            "marcas/MARCAS_DADOS_BIBLIOGRAFICOS.csv",
            RegraDoInpi(colunas_fora=("apostila",), texto=("elemento_nominativo",)),
        ),
        (
            "marcas/MARCAS_DEPOSITANTES.csv",
            RegraDoInpi(
                colunas_fora=REPRESENTANTE_DAS_MARCAS,
                documento="cnpj_cpf_titular",
                nomes=("nome",),
            ),
        ),
        ("marcas/MARCAS_PRIORIDADES.csv", None),
    ),
    "inpi-desenhos": (
        ("desenhos_industriais/DI_DADOS_BIBLIOGRAFICOS.csv", None),
        ("desenhos_industriais/DI_DEPOSITANTES.csv", TITULAR_DE_PATENTE_OU_DESENHO),
        ("desenhos_industriais/DI_AUTORES.csv", RegraDeContagem("autor")),
        ("desenhos_industriais/DI_CLASSIFICACOES.csv", None),
        ("desenhos_industriais/DI_PRIORIDADES.csv", None),
        ("desenhos_industriais/DI_VINCULOS.csv", None),
        (
            "desenhos_industriais/DI_CONTEUDO.csv",
            RegraDoInpi(texto=("titulo",)),
        ),
    ),
    "inpi-programas": (
        (
            "programas_de_computador/PROG_COMP_DADOS_BASICOS.csv",
            RegraDoInpi(texto=("titulo_programa",)),
        ),
        (
            "programas_de_computador/PROG_COMP_TITULAR.csv",
            RegraDoInpi(documento="cnpj_cpf_titular", nomes=("nome_titular",)),
        ),
        (
            "programas_de_computador/PROG_COMP_AUTORES.csv",
            RegraDeContagem("nome_autor"),
        ),
        ("programas_de_computador/PROG_COMP_CAMPOS.csv", None),
        ("programas_de_computador/PROG_COMP_LINGUAGEM.csv", None),
        ("programas_de_computador/PROG_COMP_TIPO.csv", None),
    ),
    "inpi-contratos-partes": (
        # sem documento das partes não dá para saber quem é pessoa jurídica: os nomes ficam de fora
        (
            "contratos/CONTRATOS_CEDENTE.csv",
            RegraDoInpi(colunas_fora=("nome_cedente",)),
        ),
        (
            "contratos/CONTRATOS_CESSIONARIOS.csv",
            RegraDoInpi(colunas_fora=("nome_cessionaria",)),
        ),
        ("contratos/CONTRATOS_MODALIDADE.csv", None),
    ),
}


def _arquivos_do_inpi(arquivos: tuple[tuple[str, Tratamento], ...]) -> Descobrir:
    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        return [
            Alvo(
                RAIZ_DO_INPI + caminho,
                ".csv",
                obter=tratar_csv_do_inpi(RAIZ_DO_INPI + caminho, tratamento),
            )
            for caminho, tratamento in arquivos
        ]

    return descobrir


# ---------- EPO: Linked open EP data ----------

PONTO_DO_EPO = "https://data.epo.org/linked-data/query"
RESPOSTA_DO_SPARQL = "application/sparql-results+json"
# nomes exatos do depositante (`vcard:fn`) que existem no EPO, conferidos em 23/10/2026; a busca por
# trecho estoura o tempo, então a lista é uma semente que se amplia na fila
EMPRESAS_NO_EPO = (
    "Embraer S.A.",
    "Petroleo Brasileiro S.A. - PETROBRAS",
    "Petroleo Brasileiro S.A. Petrobras",
    "Vale S.A.",
    "Braskem S.A.",
    "Natura Cosmeticos S.A.",
    "Suzano S.A.",
    "Suzano Papel e Celulose S.A.",
    "Klabin S.A.",
    "JBS S.A.",
    "Banco Bradesco S.A.",
    "Whirlpool S.A.",
    "Tupy S.A.",
    "Metalfrio Solutions S.A.",
    "Localiza Rent a Car S.A.",
    "Fibria Celulose S.A.",
    "Iochpe-Maxion S.A.",
    "Mahle Metal Leve S.A.",
    "Totvs S.A.",
    "Grendene S.A.",
    "Duratex S.A.",
    "Forjas Taurus S.A.",
    "Bunge Alimentos S.A.",
)
# só o depositante (pessoa jurídica) e o que ele depositou; o inventor (`inventorVC`) nunca é consultado
CONSULTA_DO_EPO = """\
PREFIX vc: <http://www.w3.org/2006/vcard/ns#>
PREFIX patent: <http://data.epo.org/linked-data/def/patent/>
SELECT ?pub ?data ?titulo ?depos WHERE {{
  ?v vc:fn {nome} .
  ?v patent:vcApplicantOf ?pub .
  ?pub patent:publicationDate ?data .
  OPTIONAL {{ ?pub patent:titleOfInvention ?titulo . FILTER(LANG(?titulo) = "en") }}
  OPTIONAL {{ ?pub patent:application ?ap . ?ap patent:filingDate ?depos }}
}} ORDER BY ?pub ?titulo ?depos"""


def _literal_sparql(texto: str) -> str:
    """O nome como literal SPARQL entre aspas (a lista é nossa, mas a aspa nunca passa)."""
    return json.dumps(texto, ensure_ascii=False)


def endereco_do_epo(empresa: str) -> str:
    consulta = CONSULTA_DO_EPO.format(nome=_literal_sparql(empresa))
    return f"{PONTO_DO_EPO}?{urlencode({'output': 'json', 'query': consulta})}"


def e_horario_europeu(agora: datetime) -> bool:
    hora = agora.astimezone(UTC).hour
    return HORA_EM_QUE_A_EUROPA_ACORDA <= hora < HORA_EM_QUE_A_EUROPA_DORME


def _agora_utc() -> datetime:
    return datetime.now(UTC)


def _obter_do_epo(url: str) -> Obter:
    """Um pedido ao SPARQL do EPO, fora do horário europeu; grava o JSON com as linhas ordenadas."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        if e_horario_europeu(_agora_utc()):
            raise SemArquivo(
                "EPO: o serviço não é banco de dados de retaguarda; só de 19h a 7h GMT"
            )
        resposta = cliente.ler(url, cabecalhos={"Accept": RESPOSTA_DO_SPARQL})
        dados = json.loads(resposta.conteudo)
        dados["results"]["bindings"].sort(key=lambda b: json.dumps(b, sort_keys=True))
        destino.write_text(
            json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8",
        )
        return {}

    return obter


def descobrir_epo(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Um alvo por empresa da lista; o horário só é conferido na hora de pedir."""
    return [
        Alvo(
            endereco_do_epo(empresa),
            ".json",
            obter=_obter_do_epo(endereco_do_epo(empresa)),
        )
        for empresa in EMPRESAS_NO_EPO
    ]


# ---------- WIPO: IP Statistics Data Center ----------

ZIPS_DA_WIPO = (
    "https://www.wipo.int/documents/d/ip-statistics/wipo-data-patent-indicators.zip",
    "https://www.wipo.int/documents/d/ip-statistics/wipo-data-trademark-indicators.zip",
    "https://www.wipo.int/documents/d/ip-statistics/docs-en-wipo-data-design-indicators.zip",
    "https://www.wipo.int/documents/2948119/3215563/wipo_ip_historical_data.zip",
)


def descobrir_wipo(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [Alvo(url, ".zip") for url in ZIPS_DA_WIPO]


# ---------- as fontes ----------

TERMOS_DE_PATENTES = {
    "termos-epo": "https://www.epo.org/en/searching-for-patents/data/linked-open-data",
    "termos-wipo": "https://www.wipo.int/en/web/ip-statistics",
}


def fontes() -> list[Fonte]:
    """As fontes do lote, para a lista `FONTES` (os ids seguem a família: `inpi-...`, `epo-...`, `wipo-...`)."""
    inpi = [
        Fonte(
            id_,
            MENSAL,
            _arquivos_do_inpi(arquivos),
            guardado_vale=_baixado_neste_mes,
        )
        for id_, arquivos in ARQUIVOS_DO_INPI.items()
    ]
    return [
        *inpi,
        Fonte(
            "epo-linked-patentes",
            MENSAL,
            descobrir_epo,
            "json",
            guardado_vale=_baixado_neste_mes,
            pausa_minima=PAUSA_DO_EPO_EM_SEGUNDOS,
        ),
        Fonte("wipo-estatisticas", MENSAL, descobrir_wipo, "zip", pesada=True),
    ]


def termos() -> dict[str, str]:
    """Os endereços de termos de uso do lote, para o `TERMOS` do arquivista."""
    return dict(TERMOS_DE_PATENTES)
