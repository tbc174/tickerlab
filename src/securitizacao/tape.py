"""Tape de recebíveis: gerador sintético por semente e validador (protótipo D, parte 1, B-10).

Um **tape** é a lista de recebíveis de uma carteira numa data de corte. Tipos simples, fáceis de virar JSON:

    {"data_de_corte": "2026-09-30",
     "recebiveis": [{"recebivel_id": "R0001", "cedente_cnpj": "...", "sacado_cnpj": "...",
                     "emissao": "2026-03-01", "vencimento": "2026-12-01",
                     "valor_face": 100000, "valor_pago": 25000, "saldo": 75000}, ...]}

Dinheiro em **centavos inteiros**, datas em ISO (AAAA-MM-DD). O validador **não conserta nada**: devolve
achados (`AchadoDeTape`), um por problema, com regra, linha e gravidade. Faltante e duplicado viram
achado, nunca exceção silenciosa (dossiê, `data_model.md`). Os campos do achado seguem os do achado de
qualidade que já existe (`base/regras.py`: regra, valor, valor_esperado, porque); aqui no lugar da empresa
e do documento entram a linha e o campo do tape.

Regras (a numeração é estável; a de esquema vem primeiro porque as outras dependem dos tipos):

- **T01 esquema**: campo faltando, de tipo errado, data ilegível ou valor negativo em face e pago.
  Uma linha com T01 não passa pelas outras regras (os campos dela não são confiáveis).
- **T02 duplicidade**: `recebivel_id` repetido; o achado fica nas repetições (da segunda em diante).
- **T03 vencimento antes da emissão**.
- **T04 data no futuro**: emissão depois da data de corte (um vencimento futuro é o normal).
- **T05 saldo negativo**.
- **T06 saldo que não fecha**: `valor_face - valor_pago != saldo` (saldo negativo é só T05).
- **T07 cedente** e **T08 sacado** com identificador inválido. Cada contraparte tem um tipo de identificador
  opcional (`cedente_tipo_id`, `sacado_tipo_id`): `cnpj` (o padrão, para os tapes antigos) confere 14
  caracteres, alfanumérico aceito, DV conferido; `externo` (id de fora do Brasil, como o ABS-EE da SEC, que
  não tem CNPJ) só pede texto de até `TAMANHO_MAXIMO_DO_ID_EXTERNO` caracteres e sem quebra de linha, e
  nunca vira CNPJ. Um id vazio é T01 em qualquer tipo; um tipo que não seja `cnpj` nem `externo` é T01.
  O do cedente é erro; o do sacado é aviso (a fonte do sacado costuma vir pior).

Linhas contam de 1, na ordem do tape; `linha` 0 é o tape inteiro.
"""

from __future__ import annotations

import hashlib
import json
import random
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

from base import cnpj as cnpj_base

VERSAO_DAS_REGRAS = "1.0.0"

ESQUEMA = "T01"
DUPLICIDADE = "T02"
VENCIMENTO_ANTES_DA_EMISSAO = "T03"
DATA_NO_FUTURO = "T04"
SALDO_NEGATIVO = "T05"
SALDO_NAO_FECHA = "T06"
CEDENTE_INVALIDO = "T07"
SACADO_INVALIDO = "T08"
REGRAS = (
    ESQUEMA,
    DUPLICIDADE,
    VENCIMENTO_ANTES_DA_EMISSAO,
    DATA_NO_FUTURO,
    SALDO_NEGATIVO,
    SALDO_NAO_FECHA,
    CEDENTE_INVALIDO,
    SACADO_INVALIDO,
)

ERRO = "erro"
AVISO = "aviso"

CAMPOS_TEXTO = ("recebivel_id", "cedente_cnpj", "sacado_cnpj")
CAMPOS_TIPO_DE_ID = ("cedente_tipo_id", "sacado_tipo_id")  # opcionais
CAMPOS_DATA = ("emissao", "vencimento")
CAMPOS_VALOR = ("valor_face", "valor_pago", "saldo")
CAMPOS = CAMPOS_TEXTO + CAMPOS_DATA + CAMPOS_VALOR

TIPO_CNPJ = "cnpj"
TIPO_EXTERNO = "externo"
TIPOS_DE_ID = (TIPO_CNPJ, TIPO_EXTERNO)
TAMANHO_MAXIMO_DO_ID_EXTERNO = 128
DATA_DE_CORTE_PADRAO = date(2026, 9, 30)
ALFABETO_DO_CNPJ = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
FATIA_DE_CNPJ_ALFANUMERICO = (
    5  # 1 em cada 5 CNPJs gerados tem letra, para a regra ser exercida
)
FACE_MINIMA = 10_000  # R$ 100,00 em centavos
FACE_MAXIMA = 5_000_000
PRAZO_MAXIMO_EM_DIAS = 360
IDADE_MAXIMA_EM_DIAS = 300


@dataclass(frozen=True)
class AchadoDeTape:
    regra: str
    linha: int
    campo: str  # vazio quando a regra olha a linha inteira
    gravidade: str  # "erro" ou "aviso"
    valor: str | int | None  # o que o tape trouxe
    valor_esperado: str | int | None  # o que a regra esperava
    porque: str  # frase em português


def achado_em_dicionario(achado: AchadoDeTape) -> dict[str, Any]:
    return asdict(achado)


# --- gerador -----------------------------------------------------------------------------------


def _cnpj_valido(sorteio: random.Random) -> str:
    """Um CNPJ de 14 caracteres com DV correto; às vezes alfanumérico."""
    base = "".join(sorteio.choices("0123456789", k=12))
    if sorteio.randrange(FATIA_DE_CNPJ_ALFANUMERICO) == 0:
        base = "".join(sorteio.choices(ALFABETO_DO_CNPJ, k=8)) + base[8:]
    if base == base[0] * 12:  # DV de sequência repetida é recusado pelo validador
        base = base[:-1] + ("1" if base[-1] != "1" else "2")
    return base + cnpj_base.digitos_verificadores(base)


def _recebivel(
    sorteio: random.Random, numero: int, corte: date, cedentes: list[str]
) -> dict:
    emissao = corte - timedelta(days=sorteio.randint(1, IDADE_MAXIMA_EM_DIAS))
    vencimento = emissao + timedelta(days=sorteio.randint(1, PRAZO_MAXIMO_EM_DIAS))
    face = sorteio.randint(FACE_MINIMA, FACE_MAXIMA)
    pago = sorteio.randint(0, face)
    return {
        "recebivel_id": f"R{numero:05d}",
        "cedente_cnpj": sorteio.choice(cedentes),
        "sacado_cnpj": _cnpj_valido(sorteio),
        "emissao": emissao.isoformat(),
        "vencimento": vencimento.isoformat(),
        "valor_face": face,
        "valor_pago": pago,
        "saldo": face - pago,
    }


def hash_do_tape(tape: dict[str, Any]) -> str:
    """SHA-256 do tape em JSON canônico (chaves ordenadas, sem espaços), sem o próprio hash."""
    conteudo = {k: v for k, v in tape.items() if k != "hash_do_tape"}
    texto = json.dumps(
        conteudo, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def com_hash(tape: dict[str, Any]) -> dict[str, Any]:
    return {**tape, "hash_do_tape": hash_do_tape(tape)}


def gerar_tape(
    semente: int, n_recebiveis: int = 50, data_de_corte: date = DATA_DE_CORTE_PADRAO
) -> dict[str, Any]:
    """Tape limpo e sintético: a mesma semente dá o mesmo tape e o mesmo `hash_do_tape`."""
    if n_recebiveis < 1:
        raise ValueError("o tape precisa de pelo menos 1 recebível")
    sorteio = random.Random(semente)
    cedentes = [_cnpj_valido(sorteio) for _ in range(max(1, n_recebiveis // 10))]
    recebiveis = [
        _recebivel(sorteio, numero, data_de_corte, cedentes)
        for numero in range(1, n_recebiveis + 1)
    ]
    return com_hash(
        {"data_de_corte": data_de_corte.isoformat(), "recebiveis": recebiveis}
    )


def _cnpj_com_dv_errado(cnpj: str) -> str:
    ultimo = "0" if cnpj[-1] != "0" else "1"
    return cnpj[:-1] + ultimo


def _plantar_esquema(r: dict) -> None:
    r["valor_face"] = "abc"


def _plantar_vencimento_antes(r: dict) -> None:
    r["vencimento"] = (date.fromisoformat(r["emissao"]) - timedelta(days=1)).isoformat()


def _plantar_futuro(corte: date, r: dict) -> None:
    emissao = corte + timedelta(days=1)
    r["emissao"] = emissao.isoformat()
    r["vencimento"] = (emissao + timedelta(days=30)).isoformat()


def _plantar_saldo_negativo(r: dict) -> None:
    r["valor_pago"] = r["valor_face"] + 1
    r["saldo"] = -1


def _plantar_saldo_que_nao_fecha(r: dict) -> None:
    r["saldo"] = r["valor_face"] - r["valor_pago"] + 1


def plantar_erros(
    tape: dict[str, Any], plantas: list[tuple[str, int]]
) -> dict[str, Any]:
    """Cópia do tape com um erro de cada tipo na linha dada (`(regra, linha)`, linha de 1).

    Cada linha leva no máximo um erro, para o validador poder apontar exatamente esse. A duplicidade
    acrescenta no fim uma cópia da linha (que deve estar limpa); a linha do achado é a da cópia.
    """
    linhas = [linha for _, linha in plantas]
    if len(set(linhas)) != len(linhas):
        raise ValueError("cada linha leva no máximo um erro plantado")
    corte = date.fromisoformat(tape["data_de_corte"])
    novo = deepcopy({k: v for k, v in tape.items() if k != "hash_do_tape"})
    recebiveis = novo["recebiveis"]
    copias = []
    for regra, linha in plantas:
        if not 1 <= linha <= len(tape["recebiveis"]):
            raise ValueError(f"linha {linha} fora do tape")
        r = recebiveis[linha - 1]
        if regra == DUPLICIDADE:
            copias.append(deepcopy(r))
        elif regra == ESQUEMA:
            _plantar_esquema(r)
        elif regra == VENCIMENTO_ANTES_DA_EMISSAO:
            _plantar_vencimento_antes(r)
        elif regra == DATA_NO_FUTURO:
            _plantar_futuro(corte, r)
        elif regra == SALDO_NEGATIVO:
            _plantar_saldo_negativo(r)
        elif regra == SALDO_NAO_FECHA:
            _plantar_saldo_que_nao_fecha(r)
        elif regra == CEDENTE_INVALIDO:
            r["cedente_cnpj"] = _cnpj_com_dv_errado(r["cedente_cnpj"])
        elif regra == SACADO_INVALIDO:
            r["sacado_cnpj"] = _cnpj_com_dv_errado(r["sacado_cnpj"])
        else:
            raise ValueError(f"regra desconhecida: {regra}")
    recebiveis.extend(copias)
    return com_hash(novo)


# --- validador ---------------------------------------------------------------------------------


def _data(valor: object) -> date | None:
    if not isinstance(valor, str):
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def _e_inteiro(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _problema_do_campo(r: dict, campo: str) -> str | None:
    """A frase do problema de esquema do campo, ou None se está certo."""
    if campo not in r or r[campo] is None:
        return f"campo {campo} faltando"
    valor = r[campo]
    if campo in CAMPOS_TEXTO and not (isinstance(valor, str) and valor.strip()):
        return f"{campo} deve ser texto não vazio"
    if campo in CAMPOS_DATA and _data(valor) is None:
        return f"{campo} deve ser uma data AAAA-MM-DD"
    if campo in CAMPOS_VALOR and not _e_inteiro(valor):
        return f"{campo} deve ser um número inteiro de centavos"
    if campo in ("valor_face", "valor_pago") and _e_inteiro(valor) and valor < 0:
        return f"{campo} não pode ser negativo"
    return None


def _problema_do_tipo_de_id(r: dict, campo: str) -> str | None:
    """Problema de esquema do tipo de identificador (campo opcional), ou None."""
    if campo in r and r[campo] not in TIPOS_DE_ID:
        return f"{campo} deve ser {TIPO_CNPJ!r} ou {TIPO_EXTERNO!r}"
    return None


def _achados_de_esquema(r: dict, linha: int) -> list[AchadoDeTape]:
    achados = []
    for campo in CAMPOS_TIPO_DE_ID:
        problema = _problema_do_tipo_de_id(r, campo)
        if problema:
            achados.append(
                AchadoDeTape(ESQUEMA, linha, campo, ERRO, str(r[campo]), None, problema)
            )
    for campo in CAMPOS:
        problema = _problema_do_campo(r, campo)
        if problema:
            valor = r.get(campo)
            achados.append(
                AchadoDeTape(
                    ESQUEMA,
                    linha,
                    campo,
                    ERRO,
                    None if valor is None else str(valor),
                    None,
                    problema,
                )
            )
    return achados


def _achados_de_datas(r: dict, linha: int, corte: date) -> list[AchadoDeTape]:
    emissao, vencimento = _data(r["emissao"]), _data(r["vencimento"])
    assert emissao is not None and vencimento is not None  # o esquema já passou
    achados = []
    if vencimento < emissao:
        achados.append(
            AchadoDeTape(
                VENCIMENTO_ANTES_DA_EMISSAO, linha, "vencimento", ERRO, r["vencimento"],
                r["emissao"], f"vencimento {r['vencimento']} antes da emissão {r['emissao']}",
            )
        )  # fmt: skip
    if emissao > corte:
        achados.append(
            AchadoDeTape(
                DATA_NO_FUTURO, linha, "emissao", ERRO, r["emissao"], corte.isoformat(),
                f"emissão {r['emissao']} depois da data de corte {corte.isoformat()}",
            )
        )  # fmt: skip
    return achados


def _achados_de_saldo(r: dict, linha: int) -> list[AchadoDeTape]:
    if r["saldo"] < 0:
        return [
            AchadoDeTape(
                SALDO_NEGATIVO, linha, "saldo", ERRO, r["saldo"], 0, "saldo negativo"
            )
        ]
    esperado = r["valor_face"] - r["valor_pago"]
    if esperado != r["saldo"]:
        return [
            AchadoDeTape(
                SALDO_NAO_FECHA, linha, "saldo", ERRO, r["saldo"], esperado,
                f"saldo {r['saldo']} não fecha com face menos pago ({esperado})",
            )
        ]  # fmt: skip
    return []


def _cnpj_confere(texto: str) -> bool:
    cnpj = cnpj_base.completo(texto)
    return cnpj is not None and cnpj_base.dv_confere(cnpj)


def _id_externo_confere(texto: str) -> bool:
    return len(texto) <= TAMANHO_MAXIMO_DO_ID_EXTERNO and not any(
        quebra in texto for quebra in ("\n", "\r")
    )


def _achados_de_identificador(r: dict, linha: int) -> list[AchadoDeTape]:
    achados = []
    for campo, campo_tipo, regra, gravidade in (
        ("cedente_cnpj", "cedente_tipo_id", CEDENTE_INVALIDO, ERRO),
        ("sacado_cnpj", "sacado_tipo_id", SACADO_INVALIDO, AVISO),
    ):
        if r.get(campo_tipo, TIPO_CNPJ) == TIPO_EXTERNO:
            confere = _id_externo_confere(r[campo])
            porque = f"{campo} não é um id externo válido (até {TAMANHO_MAXIMO_DO_ID_EXTERNO} caracteres, sem quebra de linha)"
        else:
            confere = _cnpj_confere(r[campo])
            porque = f"{campo} não é um CNPJ válido (tamanho, caractere ou dígito verificador)"
        if not confere:
            achados.append(
                AchadoDeTape(regra, linha, campo, gravidade, r[campo], None, porque)
            )
    return achados


def _achados_do_tape_inteiro(tape: object) -> list[AchadoDeTape]:
    if not isinstance(tape, dict):
        return [
            AchadoDeTape(ESQUEMA, 0, "", ERRO, None, None, "o tape deve ser um objeto")
        ]
    achados = []
    if _data(tape.get("data_de_corte")) is None:
        achados.append(
            AchadoDeTape(
                ESQUEMA, 0, "data_de_corte", ERRO, None, None,
                "data_de_corte faltando ou fora do formato AAAA-MM-DD",
            )
        )  # fmt: skip
    if not isinstance(tape.get("recebiveis"), list):
        achados.append(
            AchadoDeTape(
                ESQUEMA,
                0,
                "recebiveis",
                ERRO,
                None,
                None,
                "recebiveis deve ser uma lista",
            )
        )
    return achados


def validar_tape(tape: object) -> list[AchadoDeTape]:
    """Todos os achados do tape, na ordem das linhas (e das regras, dentro da linha). Não conserta nada."""
    achados = _achados_do_tape_inteiro(tape)
    if achados:
        return achados
    assert isinstance(tape, dict)
    corte = _data(tape["data_de_corte"])
    assert corte is not None
    vistos: set[str] = set()
    for linha, r in enumerate(tape["recebiveis"], start=1):
        if not isinstance(r, dict):
            achados.append(
                AchadoDeTape(
                    ESQUEMA, linha, "", ERRO, None, None, "linha deve ser um objeto"
                )
            )
            continue
        de_esquema = _achados_de_esquema(r, linha)
        if de_esquema:
            achados.extend(de_esquema)
            continue
        if r["recebivel_id"] in vistos:
            achados.append(
                AchadoDeTape(
                    DUPLICIDADE, linha, "recebivel_id", ERRO, r["recebivel_id"], None,
                    f"recebivel_id {r['recebivel_id']} já apareceu antes no tape",
                )
            )  # fmt: skip
        vistos.add(r["recebivel_id"])
        achados.extend(_achados_de_datas(r, linha, corte))
        achados.extend(_achados_de_saldo(r, linha))
        achados.extend(_achados_de_identificador(r, linha))
    return sorted(achados, key=lambda a: (a.linha, REGRAS.index(a.regra)))
