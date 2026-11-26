"""O XML de cada lista de sanção de fora (OFAC, União Europeia e Reino Unido): o que é entidade, o que
a coleta guarda e como se lê. Estrutura conferida em 26/11/2026 nos arquivos de verdade.

**Pessoa física nunca passa** (ADR 0088). O mesmo teste (`e_entidade`) vale na coleta e na leitura:

- só o tipo que a própria fonte informa como entidade; navio, aeronave e registro **sem tipo** saem;
- registro que a fonte chama de entidade mas traz sinal de pessoa (nascimento, gênero, prenome,
  cidadania, título, detalhes de indivíduo) sai;
- empresário individual pelo nome (`sole proprietor`, `individual entrepreneur`, `IP ...`) sai.

A coleta ainda guarda **só os campos que a tabela usa**: documento, endereço, contato, vínculo com outra
pessoa e texto livre (observações, motivos) não chegam ao acervo, porque podem trazer nome de gente.
"""

import io
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from defusedxml.ElementTree import iterparse

from base.arquivo.coleta import ErroDeDescoberta

# nome de quem negocia em nome próprio: é a pessoa, mesmo quando a fonte o lista como entidade. Além do
# inglês, as formas russa, ucraniana e bielorrussa, em cirílico e transliteradas
_PALAVRAS_DE_EMPRESARIO_INDIVIDUAL = re.compile(
    r"individual entrepreneur|sole propriet|sole trader|private entrepreneur"
    r"|individual'?n\w*'? predprinimatel|fizychn\w* osoba|fizichesk\w* li(?:ts|c)"
    r"|индивидуальн\w* предпринимател|физическ\w* лиц|фізична особа",
    re.IGNORECASE,
)
_PREFIXO_DE_EMPRESARIO_INDIVIDUAL = re.compile(r"^(IP|ИП|ІП|ЧП|FOP|ФОП)\s")
_CARACTERISTICA_DE_PESSOA = re.compile(r"birth|gender|citizen|passport", re.IGNORECASE)
_ATRIBUTOS_DE_PESSOA_NA_UE = ("firstName", "middleName", "lastName", "gender")
RAIZ_DO_FILTRADO = "registros"
SEM_PAIS = "UNKNOWN"  # a UE escreve assim o endereço sem país
LISTA_DA_SDN = "SDN List"
LISTA_GUARDA_CHUVA = "Consolidated List"  # reúne as listas não SDN da OFAC


@dataclass(frozen=True)
class Registro:
    """Uma entidade como a lista a publica. `listas`: (nome da lista, dia da designação ISO ou None)."""

    id: str
    nome: str
    outros_nomes: tuple[str, ...]
    paises: tuple[str, ...]
    programas: tuple[str, ...]
    listas: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True)
class Manter:
    """Do elemento, os atributos e os filhos que a coleta guarda; sem `filhos`, guarda o texto."""

    atributos: tuple[str, ...] = ()
    filhos: Mapping[str, "Manter"] = field(default_factory=dict)


@dataclass(frozen=True)
class Formato:
    """Uma lista: o endereço oficial, o elemento de cada registro e como filtrar e ler."""

    url: str
    elemento: str
    manter: Manter
    e_entidade: Callable[[ET.Element], bool]
    ler: Callable[[ET.Element], Registro]


# --- ajudantes (os arquivos usam espaço de nomes: só o nome local conta) ----------------------------
def _local(nome: str) -> str:
    return nome.rsplit("}", 1)[-1]


def _filhos(elemento: ET.Element | None, nome: str) -> list[ET.Element]:
    if elemento is None:
        return []
    return [f for f in elemento if _local(f.tag) == nome]


def _filho(elemento: ET.Element | None, *caminho: str) -> ET.Element | None:
    for nome in caminho:
        achados = _filhos(elemento, nome)
        elemento = achados[0] if achados else None
    return elemento


def _texto(elemento: ET.Element | None, *caminho: str) -> str:
    achado = _filho(elemento, *caminho)
    return ((achado.text if achado is not None else None) or "").strip()


def _sem_repetir(textos: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(t for t in textos if t))


def _dia(texto: str, formato: str) -> str | None:
    try:
        return datetime.strptime(texto, formato).replace(tzinfo=UTC).date().isoformat()
    except ValueError:
        return None  # a fonte não informou (ou escreveu outra coisa): fica sem data


def e_empresario_individual(nome: str) -> bool:
    return bool(
        _PALAVRAS_DE_EMPRESARIO_INDIVIDUAL.search(nome)
        or _PREFIXO_DE_EMPRESARIO_INDIVIDUAL.search(nome)
    )


# --- OFAC ------------------------------------------------------------------------------------------
def _traducoes(entidade: ET.Element) -> list[ET.Element]:
    return [
        t
        for nome in _filhos(_filho(entidade, "names"), "name")
        for t in _filhos(_filho(nome, "translations"), "translation")
    ]


def _e_entidade_na_ofac(entidade: ET.Element) -> bool:
    if _texto(entidade, "generalInfo", "entityType") != "Entity":
        return False
    sinais = (
        _texto(entidade, "generalInfo", "title"),
        *(_texto(t, "formattedFirstName") for t in _traducoes(entidade)),
    )
    caracteristicas = _filhos(_filho(entidade, "features"), "feature")
    return not (
        any(sinais)
        or any(
            _CARACTERISTICA_DE_PESSOA.search(_texto(f, "type")) for f in caracteristicas
        )
        or any(
            e_empresario_individual(_texto(t, "formattedFullName"))
            for t in _traducoes(entidade)
        )
    )


def _nome_na_escrita_principal(nome: ET.Element) -> str:
    principais = [
        t
        for t in _filhos(_filho(nome, "translations"), "translation")
        if _texto(t, "isPrimary") == "true"
    ]
    return _texto(principais[0], "formattedFullName") if principais else ""


def _ler_ofac(
    entidade: ET.Element, listas: tuple[tuple[str, str | None], ...]
) -> Registro:
    nomes = _filhos(_filho(entidade, "names"), "name")
    principais = [n for n in nomes if _texto(n, "isPrimary") == "true"]
    outros = [
        n for n in nomes if n not in principais and _texto(n, "isLowQuality") != "true"
    ]
    principal = _nome_na_escrita_principal(principais[0]) if principais else ""
    enderecos = _filhos(_filho(entidade, "addresses"), "address")
    programas = _filhos(_filho(entidade, "sanctionsPrograms"), "sanctionsProgram")
    return Registro(
        id=entidade.get("id", ""),
        nome=principal,
        outros_nomes=_sem_repetir(
            n for n in map(_nome_na_escrita_principal, outros) if n != principal
        ),
        paises=_sem_repetir(_texto(e, "country") for e in enderecos),
        programas=_sem_repetir((p.text or "").strip() for p in programas),
        listas=listas,
    )


def _listas_da_ofac(entidade: ET.Element) -> list[tuple[str, str | None]]:
    return [
        ((s.text or "").strip(), _dia(s.get("datePublished", "")[:10], "%Y-%m-%d"))
        for s in _filhos(_filho(entidade, "sanctionsLists"), "sanctionsList")
    ]


def _ler_sdn(entidade: ET.Element) -> Registro:
    """Do arquivo da SDN, só a SDN: as outras listas vêm do arquivo consolidado, sem repetir."""
    return _ler_ofac(
        entidade,
        tuple(x for x in _listas_da_ofac(entidade) if x[0] == LISTA_DA_SDN),
    )


def _ler_consolidada(entidade: ET.Element) -> Registro:
    todas = _listas_da_ofac(entidade)
    proprias = [x for x in todas if x[0] not in (LISTA_DA_SDN, LISTA_GUARDA_CHUVA)]
    if not proprias and not any(x[0] == LISTA_DA_SDN for x in todas):
        proprias = todas  # só o guarda-chuva: não perder a entidade
    return _ler_ofac(entidade, tuple(proprias))


# --- Reino Unido -----------------------------------------------------------------------------------
def _nome_do_reino_unido(nome: ET.Element) -> str:
    partes = (_texto(nome, f"Name{n}") for n in range(1, 7))
    return " ".join(p for p in partes if p)


def _e_entidade_no_reino_unido(designacao: ET.Element) -> bool:
    if _texto(designacao, "IndividualEntityShip") != "Entity":
        return False
    return _filho(designacao, "IndividualDetails") is None and not any(
        e_empresario_individual(_nome_do_reino_unido(n))
        for n in _filhos(_filho(designacao, "Names"), "Name")
    )


def _ler_reino_unido(designacao: ET.Element) -> Registro:
    nomes = _filhos(_filho(designacao, "Names"), "Name")
    primarios = [n for n in nomes if _texto(n, "NameType").casefold() == "primary name"]
    escritos = [_nome_do_reino_unido(n) for n in nomes]
    principal = (
        _nome_do_reino_unido(primarios[0])
        if primarios
        else next((n for n in escritos if n), "")
    )
    enderecos = _filhos(_filho(designacao, "Addresses"), "Address")
    return Registro(
        id=_texto(designacao, "UniqueID"),
        nome=principal,
        outros_nomes=_sem_repetir(n for n in escritos if n != principal),
        paises=_sem_repetir(_texto(e, "AddressCountry") for e in enderecos),
        programas=_sem_repetir([_texto(designacao, "RegimeName")]),
        listas=(
            (
                "UK Sanctions List",
                _dia(_texto(designacao, "DateDesignated"), "%d/%m/%Y"),
            ),
        ),
    )


# --- União Europeia ----------------------------------------------------------------------------------
def _e_entidade_na_uniao_europeia(registro: ET.Element) -> bool:
    tipo = _filho(registro, "subjectType")
    if tipo is None or tipo.get("classificationCode") != "E":
        return False
    nomes = _filhos(registro, "nameAlias")
    return not (
        _filhos(registro, "birthdate")
        or _filhos(registro, "citizenship")
        or any(n.get(a) for n in nomes for a in _ATRIBUTOS_DE_PESSOA_NA_UE)
        or any(e_empresario_individual(n.get("wholeName", "")) for n in nomes)
    )


def _ler_uniao_europeia(registro: ET.Element) -> Registro:
    nomes = _filhos(registro, "nameAlias")
    fortes = [n.get("wholeName", "") for n in nomes if n.get("strong") == "true"]
    principal = next(
        (n for n in [*fortes, *(x.get("wholeName", "") for x in nomes)] if n), ""
    )
    regulacao = _filho(registro, "regulation")
    return Registro(
        id=registro.get("logicalId", ""),
        nome=principal,
        outros_nomes=_sem_repetir(n for n in fortes if n != principal),
        paises=_sem_repetir(
            p
            for p in (
                e.get("countryDescription", "") for e in _filhos(registro, "address")
            )
            if p != SEM_PAIS
        ),
        programas=_sem_repetir(
            [regulacao.get("programme", "") if regulacao is not None else ""]
        ),
        listas=(
            (
                "EU Financial Sanctions List",
                _dia(registro.get("designationDate", ""), "%Y-%m-%d"),
            ),
        ),
    )


# --- as listas -------------------------------------------------------------------------------------
_TEXTO = Manter()
_MANTER_DA_OFAC = Manter(
    ("id",),
    {
        "generalInfo": Manter(filhos={"entityType": _TEXTO}),
        "sanctionsLists": Manter(filhos={"sanctionsList": Manter(("datePublished",))}),
        "sanctionsPrograms": Manter(filhos={"sanctionsProgram": _TEXTO}),
        "names": Manter(
            filhos={
                "name": Manter(
                    filhos={
                        "isPrimary": _TEXTO,
                        "isLowQuality": _TEXTO,
                        "translations": Manter(
                            filhos={
                                "translation": Manter(
                                    filhos={
                                        "isPrimary": _TEXTO,
                                        "formattedFullName": _TEXTO,
                                    }
                                )
                            }
                        ),
                    }
                )
            }
        ),
        "addresses": Manter(filhos={"address": Manter(filhos={"country": _TEXTO})}),
    },
)
_MANTER_DO_REINO_UNIDO = Manter(
    filhos={
        "UniqueID": _TEXTO,
        "DateDesignated": _TEXTO,
        "RegimeName": _TEXTO,
        "IndividualEntityShip": _TEXTO,
        "Names": Manter(
            filhos={
                "Name": Manter(
                    filhos=dict.fromkeys(
                        (*(f"Name{n}" for n in range(1, 7)), "NameType"), _TEXTO
                    )
                )
            }
        ),
        "Addresses": Manter(
            filhos={"Address": Manter(filhos={"AddressCountry": _TEXTO})}
        ),
    }
)
_MANTER_DA_UNIAO_EUROPEIA = Manter(
    ("logicalId", "designationDate"),
    {
        "subjectType": Manter(("classificationCode",)),
        "nameAlias": Manter(("wholeName", "strong")),
        "regulation": Manter(("programme",)),
        "address": Manter(("countryDescription",)),
    },
)

_SERVICO_DA_OFAC = (
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports"
)
OFAC_SDN = Formato(
    f"{_SERVICO_DA_OFAC}/SDN_ENHANCED.XML",
    "entity",
    _MANTER_DA_OFAC,
    _e_entidade_na_ofac,
    _ler_sdn,
)
OFAC_CONSOLIDADA = Formato(
    f"{_SERVICO_DA_OFAC}/CONS_ENHANCED.XML",
    "entity",
    _MANTER_DA_OFAC,
    _e_entidade_na_ofac,
    _ler_consolidada,
)
# o token é público (está no endereço de download do próprio site da Comissão Europeia)
UNIAO_EUROPEIA = Formato(
    "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content"
    "?token=dG9rZW4tMjAxNw",
    "sanctionEntity",
    _MANTER_DA_UNIAO_EUROPEIA,
    _e_entidade_na_uniao_europeia,
    _ler_uniao_europeia,
)
REINO_UNIDO = Formato(
    "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.xml",
    "Designation",
    _MANTER_DO_REINO_UNIDO,
    _e_entidade_no_reino_unido,
    _ler_reino_unido,
)


# --- filtrar e ler ---------------------------------------------------------------------------------
def _registros(arquivo: IO[bytes], formato: Formato) -> Iterator[ET.Element]:
    """Cada registro da lista, um por vez, solto da memória depois de usado."""
    for _, elemento in iterparse(arquivo, events=("end",)):
        if _local(elemento.tag) == formato.elemento:
            yield elemento
            elemento.clear()


def _enxuto(elemento: ET.Element, manter: Manter) -> ET.Element:
    """Uma cópia só com o que `manter` pede, sem espaço de nomes."""
    copia = ET.Element(
        _local(elemento.tag),
        {a: v for a, v in elemento.attrib.items() if a in manter.atributos},
    )
    if not manter.filhos:
        copia.text = (elemento.text or "").strip() or None
    for filho in elemento:
        regra = manter.filhos.get(_local(filho.tag))
        if regra is not None:
            copia.append(_enxuto(filho, regra))
    return copia


def so_entidades(bruto: Path, destino: Path, formato: Formato) -> None:
    """Grava em `destino` só as entidades, só com os campos da tabela. Arquivo sem registro ou sem
    entidade nenhuma é formato que mudou: falha, nunca uma lista vazia."""
    entidades_ = 0
    with bruto.open("rb") as entrada, destino.open("wb") as saida:
        saida.write(f"<{RAIZ_DO_FILTRADO}>\n".encode())
        for elemento in _registros(entrada, formato):
            if formato.e_entidade(elemento):
                entidades_ += 1
                saida.write(ET.tostring(_enxuto(elemento, formato.manter), "utf-8"))
                saida.write(b"\n")
        saida.write(f"</{RAIZ_DO_FILTRADO}>\n".encode())
    if not entidades_:
        raise ErroDeDescoberta(
            f"nenhuma entidade no elemento {formato.elemento!r} (formato mudou)"
        )


def entidades(conteudo: bytes, formato: Formato) -> list[Registro]:
    """As entidades de um arquivo da lista (o filtrado ou o original), com nome e identificador."""
    lidos = (
        formato.ler(e)
        for e in _registros(io.BytesIO(conteudo), formato)
        if formato.e_entidade(e)
    )
    return [r for r in lidos if r.id and r.nome]
