"""O que a comunicação do DJEN diz (plano de 03/11/2026, PR 2, grupo 4; ADR 0121): o tipo de ato, o
resultado e o maior valor em reais citado, tirados do teor por regra.

- **Só a fórmula do dispositivo.** O resultado sai do verbo no presente ("JULGO PROCEDENTE", "NEGO
  PROVIMENTO", "HOMOLOGO O ACORDO", "EXTINGO O PROCESSO"); a decisão de antes contada no passado ("a
  sentença julgou improcedente") não conta. Dois dispositivos que se contradizem no mesmo texto (a ação
  procedente e a reconvenção improcedente) deixam o resultado vazio. O resultado é o do pedido, não o da
  companhia: quem ganhou depende do polo (`processos_partes`).
- **Nenhum texto livre guardado.** O trecho de prova é a fórmula montada com as palavras da própria
  regra; o que estiver entre o verbo e a palavra-chave (pode ser um nome) vira "...".
- **Lista de muitos processos não se lê.** Pauta, distribuição, edital e certidão não decidem nada, e
  um texto de mais de `MAX_CARACTERES` é lista (ata, pauta): o dispositivo pode ser de outro processo.
- **O valor** é o maior "R$" do texto: pode ser a condenação, a causa ou os honorários. É o que o texto
  cita, não o valor da causa (o DJEN não traz).

A regra não decide sozinha o que sai: `base/conferencia_processos.py` compara com um segundo modelo
numa amostra e só publica o campo que passa no critério.
"""

import html
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

VERSAO_DA_REGRA = "v1"
MAX_CARACTERES = (
    20_000  # a mediana da amostra de 04/11 tem ~1.200; acima de 20 mil é lista
)
MAX_LETRAS_ENTRE_VERBO_E_CHAVE = 120

SENTENCA = "sentenca"
ATOS = (
    SENTENCA,
    "acordao",
    "decisao",
    "despacho",
    "despacho_ou_decisao",
    "ato_ordinatorio",
    "ata_de_julgamento",
    "pauta",
    "distribuicao",
    "edital",
    "certidao",
)
# o tipo do documento como o tribunal escreve (sem acento, maiúsculas) → o ato; a primeira que bate
_ATO_PELO_DOCUMENTO = (
    (re.compile(r"SENTENC"), SENTENCA),
    (re.compile(r"ACORDAO|EMENTA"), "acordao"),
    (re.compile(r"ATA DE SESS"), "ata_de_julgamento"),
    (re.compile(r"PAUTA|PROXIMOS JULGADOS"), "pauta"),
    (re.compile(r"DISTRIBUI"), "distribuicao"),
    (re.compile(r"EDITAL"), "edital"),
    (re.compile(r"ATO ORDINAT"), "ato_ordinatorio"),
    (re.compile(r"DESPACHO\s*/\s*DECIS"), "despacho_ou_decisao"),
    (re.compile(r"DECIS"), "decisao"),
    (re.compile(r"DESPACHO"), "despacho"),
    (re.compile(r"CERTID"), "certidao"),
)
SEM_LEITURA = frozenset(
    {"pauta", "distribuicao", "edital", "certidao", "ato_ordinatorio"}
)

RESULTADOS_DE_SENTENCA = (
    "procedente",
    "parcialmente_procedente",
    "improcedente",
    "acordo_homologado",
    "extinto",
)
RESULTADOS_DE_RECURSO = (
    "recurso_provido",
    "recurso_parcialmente_provido",
    "recurso_nao_provido",
)
RESULTADOS = (*RESULTADOS_DE_SENTENCA, *RESULTADOS_DE_RECURSO)

_MEIO = rf"(?P<meio>[^.;:]{{0,{MAX_LETRAS_ENTRE_VERBO_E_CHAVE}}}?)"
_JULGAMENTO = re.compile(
    rf"(?P<verbo>\bJULG(?:O|A-SE|AM-SE))\b{_MEIO}\b"
    r"(?P<chave>PARCIALMENTE PROCEDENTES?|PROCEDENTES? EM PARTE|IMPROCEDENTES?|PROCEDENTES?)\b"
)
_HOMOLOGACAO = re.compile(
    rf"(?P<verbo>\bHOMOLOG(?:O|A-SE))\b{_MEIO}\b(?P<chave>ACORDO|TRANSACAO|CONCILIACAO)\b"
)
_EXTINCAO = re.compile(
    r"(?P<verbo>\b(?:EXTINGO|(?:JULGO|DECLARO|JULGA-SE) EXTINT[OA]))\b(?P<meio>[^.;:]{0,40}?)\b"
    r"(?P<chave>PROCESSO|FEITO|EXECUCAO|ACAO|CUMPRIMENTO DE SENTENCA)\b"
)
_DAR = r"D(?:OU|AR|ERAM|A-SE|EU-SE)"
_RECURSOS = (
    (
        re.compile(
            r"\b(?:NEG(?:O|AR|ARAM|A-SE|OU-SE)\s+(?:INTEGRAL\s+)?PROVIMENTO|"
            r"RECURSOS?\s+(?:NAO\s+PROVIDOS?|IMPROVIDOS?|DESPROVIDOS?))\b"
        ),
        "recurso_nao_provido",
    ),
    (
        re.compile(
            rf"\b(?:{_DAR}\s+PARCIAL\s+PROVIMENTO|PROVIMENTO\s+PARCIAL|"
            r"RECURSOS?\s+PARCIALMENTE\s+PROVIDOS?)\b"
        ),
        "recurso_parcialmente_provido",
    ),
    (
        re.compile(rf"\b(?:{_DAR}\s+PROVIMENTO(?!\s+PARCIAL)|RECURSOS?\s+PROVIDOS?)\b"),
        "recurso_provido",
    ),
)
_RESULTADO_DA_CHAVE = {
    "PARCIALMENTE PROCEDENTE": "parcialmente_procedente",
    "PROCEDENTE EM PARTE": "parcialmente_procedente",
    "IMPROCEDENTE": "improcedente",
    "PROCEDENTE": "procedente",
}
# palavras que podem ficar entre o verbo e a chave no trecho sem virar "..."
_ARTIGOS = frozenset({"", "O", "A", "OS", "AS"})

_VALOR = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?")
_TAG = re.compile(r"<[^>]+>")
_ESPACOS = re.compile(r"\s+")


@dataclass(frozen=True)
class Leitura:
    tipo_de_ato: str | None
    resultado: str | None
    resultado_trecho: str | None
    valor_citado: float | None


def sem_html(texto: object) -> str:
    """O texto sem as marcas de HTML, com um espaço só entre as palavras."""
    return _ESPACOS.sub(" ", html.unescape(_TAG.sub(" ", str(texto or "")))).strip()


def texto_limpo(texto: object) -> str:
    """Sem HTML, sem acento, em maiúsculas, com um espaço só entre as palavras."""
    sem_acento = "".join(
        c
        for c in unicodedata.normalize("NFKD", sem_html(texto))
        if not unicodedata.combining(c)
    )
    return _ESPACOS.sub(" ", sem_acento).strip().upper()


def _trecho(achado: re.Match[str]) -> str:
    meio = achado["meio"].strip()
    junta = f" {meio} " if meio in _ARTIGOS else " ... "
    return _ESPACOS.sub(" ", f"{achado['verbo']}{junta}{achado['chave']}")


def _dispositivos(texto: str) -> list[tuple[str, str]]:
    """Cada dispositivo de julgamento, homologação ou recurso achado: (resultado, trecho)."""
    achados = [
        (_RESULTADO_DA_CHAVE[re.sub(r"S\b", "", a["chave"])], _trecho(a))
        for a in _JULGAMENTO.finditer(texto)
    ]
    achados += [("acordo_homologado", _trecho(a)) for a in _HOMOLOGACAO.finditer(texto)]
    for padrao, resultado in _RECURSOS:
        achados += [(resultado, a[0]) for a in padrao.finditer(texto)]
    return achados


def resultado(texto: str) -> tuple[str, str] | None:
    """O resultado e a fórmula que o provou, de um texto já limpo (`texto_limpo`). Vazio se não há
    dispositivo ou se há dois que se contradizem. A extinção só conta sem outro dispositivo: "julgo
    procedente e extingo o processo com resolução do mérito" é procedente."""
    achados = _dispositivos(texto)
    diferentes = {r for r, _ in achados}
    if len(diferentes) == 1:
        return achados[0]
    if diferentes:
        return None
    extincao = _EXTINCAO.search(texto)
    return ("extinto", _trecho(extincao)) if extincao else None


def tipo_de_ato(tipo_documento: object, texto: str) -> str | None:
    """O ato pelo tipo do documento que o tribunal informou; no tipo genérico ("Intimação",
    "Outros"), sentença só quando o texto tem o dispositivo de uma. Recurso julgado em texto genérico
    fica sem tipo: pode ser acórdão ou decisão do relator."""
    documento = texto_limpo(tipo_documento)
    for padrao, ato in _ATO_PELO_DOCUMENTO:
        if padrao.search(documento):
            return ato
    limpo = texto_limpo(texto)
    if len(limpo) > MAX_CARACTERES:
        return None
    achado = resultado(limpo)
    return SENTENCA if achado and achado[0] in RESULTADOS_DE_SENTENCA else None


def maior_valor(texto: str) -> float | None:
    """O maior valor em reais escrito no texto ("R$ 1.234,56"); vazio se não há nenhum acima de zero."""
    valores = [
        float(inteiro.replace(".", "") + "." + (centavos or "0"))
        for inteiro, centavos in _VALOR.findall(texto)
    ]
    maior = max(valores, default=0.0)
    return maior if maior > 0 else None


def ler(item: Mapping[str, Any]) -> Leitura:
    """A leitura de uma comunicação do DJEN como a API entrega (`tipoDocumento`, `texto`)."""
    texto = texto_limpo(item.get("texto"))
    ato = tipo_de_ato(item.get("tipoDocumento"), texto)
    if ato in SEM_LEITURA or len(texto) > MAX_CARACTERES:
        return Leitura(ato, None, None, None)
    achado = resultado(texto)
    return Leitura(
        ato,
        achado[0] if achado else None,
        achado[1] if achado else None,
        maior_valor(texto),
    )
