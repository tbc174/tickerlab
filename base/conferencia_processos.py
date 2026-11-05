"""A conferência automática do teor dos processos (plano de 03/11/2026, PR 2, grupo 4; ADR 0121): o
Tiago não confere à mão, então um segundo modelo confere a regra (`base/processos_teor.py`).

- **Amostra com semente gravada.** Para cada campo, até `POR_CAMPO` comunicações em que a regra o
  preencheu, sorteadas com a semente (quem refizer o sorteio acha as mesmas).
- **Gabarito de outro modelo.** O modelo (`MODELO_DO_GABARITO`) lê o mesmo teor, com os nomes das
  partes, dos advogados e os CPFs trocados por marcas (`mascarar`), e responde os três campos.
- **Critério escrito antes de medir:** precisão de pelo menos 95% (`CRITERIO`) por campo. Campo
  abaixo disso não sai em nenhuma comunicação (a seção se desliga) e a carga da conferência sai com 1
  (abre a ficha de falha).
- **Regra e modelo discordam: o campo fica vazio** naquela comunicação, nesta e nas conferências
  seguintes da mesma versão da regra.
- **Uma amostra nova a cada carga.** A conferência cobre as comunicações vistas até o dia da amostra
  (`cobre_ate`); a que chegou depois espera a próxima. Sem conferência da versão da regra, nada do
  teor sai.

Este módulo não chama a API: monta o pedido, sorteia, mede e aplica. A conferência (só ids e
contagens, sem texto) fica em `<base>/conferencias/processos-teor/AAAA-MM-DD.json`.
"""

import hashlib
import json
import random
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from base import processos_teor as pt
from base.processos_teor import Leitura

CRITERIO = 0.95
POR_CAMPO = 100
MODELO_DO_GABARITO = "claude-sonnet-5-5"
MAX_TOKENS_DA_RESPOSTA = 300
TOLERANCIA_DO_VALOR = 0.01  # um centavo
CAMPOS = ("tipo_de_ato", "resultado", "valor_citado")
PASTA = Path("conferencias") / "processos-teor"
NAO_IDENTIFICADO = "nao_identificado"
NENHUM = "nenhum"

PARTE = "[parte]"
ADVOGADO = "[advogado]"
CPF = "[cpf]"
# "BELTRANO DA SILVA (OAB 12345/SP)", "Ciclano Souza - OAB/RJ 999": o nome antes da OAB e o número
_NOME = r"[A-ZÀ-Ý][\wÀ-ÿ'.]*(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ý][\wÀ-ÿ'.]*){0,7}"
_ADVOGADO = re.compile(rf"{_NOME}\s*(?:[-–,]\s*)?\(?\s*OAB\b[^),;]{{0,20}}\)?")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")

GUIA = f"""Você confere a leitura de comunicações de processos judiciais publicadas no Diário de
Justiça Eletrônico Nacional. Leia o teor e responda três campos, sem copiar nomes.

tipo_de_ato: o ato que a comunicação publica. Use o tipo do documento que o tribunal informou quando
ele diz o ato (Sentença, Acórdão, Decisão, Despacho, "Despacho/Decisão", Ato ordinatório, Ata de sessão
de julgamento, Pauta, Ata de distribuição, Edital, Certidão). Quando o tipo é genérico (Intimação,
Outros), responda "sentenca" só se o teor é uma sentença que julga o pedido, homologa um acordo ou
extingue o processo; senão, "{NAO_IDENTIFICADO}". Valores: {", ".join(pt.ATOS)}, {NAO_IDENTIFICADO}.

resultado: o que esta comunicação decide, pela fórmula do dispositivo no presente (julgo procedente,
nego provimento, homologo o acordo, extingo o processo). A decisão de antes contada no passado ("a
sentença julgou improcedente") não é o resultado. Se o teor tem dois dispositivos que se contradizem
(ação procedente e reconvenção improcedente), ou nenhum, responda "{NENHUM}". Extinção só quando não há
outro dispositivo; homologação de acordo vence a extinção que vem junto. Valores: {", ".join(pt.RESULTADOS)},
{NENHUM}.

maior_valor: o maior valor em reais escrito no teor (R$), em número (1234.56); null se não há nenhum
acima de zero."""


def _enum(valores: Iterable[str]) -> dict[str, Any]:
    return {"type": "string", "enum": list(valores)}


ESQUEMA_DA_RESPOSTA = {
    "type": "object",
    "properties": {
        "tipo_de_ato": _enum((*pt.ATOS, NAO_IDENTIFICADO)),
        "resultado": _enum((*pt.RESULTADOS, NENHUM)),
        "maior_valor": {"anyOf": [{"type": "number"}, {"type": "null"}]},
    },
    "required": ["tipo_de_ato", "resultado", "maior_valor"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Campo:
    casos: int
    acertos: int

    @property
    def precisao(self) -> float | None:
        return self.acertos / self.casos if self.casos else None

    @property
    def aprovado(self) -> bool:
        return self.precisao is not None and self.precisao >= CRITERIO


@dataclass(frozen=True)
class Conferencia:
    feita_em: date
    versao_da_regra: str
    modelo: str
    semente: int
    cobre_ate: date
    campos: dict[str, Campo]
    discordantes: dict[str, tuple[str, ...]]

    def para_json(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "feita_em": self.feita_em.isoformat(),
            "cobre_ate": self.cobre_ate.isoformat(),
            "criterio": CRITERIO,
            "precisao": {c: v.precisao for c, v in self.campos.items()},
            "aprovados": [c for c, v in self.campos.items() if v.aprovado],
        }

    @classmethod
    def de_json(cls, dados: Mapping[str, Any]) -> "Conferencia":
        return cls(
            feita_em=date.fromisoformat(dados["feita_em"]),
            versao_da_regra=dados["versao_da_regra"],
            modelo=dados["modelo"],
            semente=int(dados["semente"]),
            cobre_ate=date.fromisoformat(dados["cobre_ate"]),
            campos={c: Campo(**v) for c, v in dados["campos"].items()},
            discordantes={c: tuple(v) for c, v in dados["discordantes"].items()},
        )


@dataclass(frozen=True)
class Vigente:
    """O que a montagem precisa: a conferência mais nova da versão da regra, com quem discordou em
    qualquer uma delas."""

    feita_em: date
    cobre_ate: date
    aprovados: frozenset[str]
    discordantes: dict[str, frozenset[str]]


# --- a amostra e o pedido ------------------------------------------------------------------------


def sortear(
    leituras: Mapping[str, Leitura], semente: int, por_campo: int = POR_CAMPO
) -> dict[str, list[str]]:
    """Cada campo -> as comunicações sorteadas entre as que a regra preencheu (ordem do id)."""
    sorteio = random.Random(semente)
    amostra = {}
    for campo in CAMPOS:
        preenchidas = sorted(
            i for i, l in leituras.items() if getattr(l, campo) is not None
        )
        escolhidas = sorteio.sample(preenchidas, min(por_campo, len(preenchidas)))
        amostra[campo] = sorted(escolhidas)
    return amostra


def mascarar(texto: str, nomes: Iterable[str]) -> str:
    """O teor sem os nomes das partes que o DJEN informa, sem os advogados (o nome antes da OAB) e
    sem CPF. Nome de pessoa que só aparece no meio do texto pode sobrar: o guia manda não copiar."""
    for nome in sorted(
        {n.strip() for n in nomes if n and n.strip()}, key=len, reverse=True
    ):
        texto = re.sub(re.escape(nome), PARTE, texto, flags=re.IGNORECASE)
    return _CPF.sub(CPF, _ADVOGADO.sub(ADVOGADO, texto))


def texto_do_envio(item: Mapping[str, Any]) -> str:
    nomes = [d.get("nome") or "" for d in item.get("destinatarios") or []]
    return mascarar(pt.sem_html(item.get("texto")), nomes)[: pt.MAX_CARACTERES]


def pedido(item: Mapping[str, Any], modelo: str = MODELO_DO_GABARITO) -> dict[str, Any]:
    """Os parâmetros de `messages.create` (os mesmos servem para o lote) de uma comunicação."""
    return {
        "model": modelo,
        "max_tokens": MAX_TOKENS_DA_RESPOSTA,
        "system": [
            {"type": "text", "text": GUIA, "cache_control": {"type": "ephemeral"}}
        ],
        "output_config": {
            "effort": "low",
            "format": {"type": "json_schema", "schema": ESQUEMA_DA_RESPOSTA},
        },
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Tipo do documento informado pelo tribunal: "
                    f"{item.get('tipoDocumento') or '(vazio)'}\n\nTeor:\n{texto_do_envio(item)}"
                ),
            }
        ],
    }


# --- a medida ------------------------------------------------------------------------------------


def _concorda(campo: str, leitura: Leitura, resposta: Mapping[str, Any] | None) -> bool:
    if resposta is None:
        return False
    if campo == "valor_citado":
        lido = resposta.get("maior_valor")
        return (
            isinstance(lido, int | float)
            and leitura.valor_citado is not None
            and abs(lido - leitura.valor_citado) <= TOLERANCIA_DO_VALOR
        )
    return resposta.get(campo) == getattr(leitura, campo)


def medir(
    leituras: Mapping[str, Leitura],
    respostas: Mapping[str, Mapping[str, Any]],
    amostra: Mapping[str, Sequence[str]],
) -> tuple[dict[str, Campo], dict[str, tuple[str, ...]]]:
    """Acertos da regra contra o gabarito, campo a campo, e quem discordou. Resposta que falta conta
    como discordância."""
    campos, discordantes = {}, {}
    for campo in CAMPOS:
        ids = amostra.get(campo, [])
        errados = tuple(
            i for i in ids if not _concorda(campo, leituras[i], respostas.get(i))
        )
        campos[campo] = Campo(casos=len(ids), acertos=len(ids) - len(errados))
        discordantes[campo] = errados
    return campos, discordantes


# --- gravar, ler e aplicar -----------------------------------------------------------------------


def gravar(conferencia: Conferencia, pasta: Path) -> Path:
    """`<pasta>/conferencias/processos-teor/AAAA-MM-DD.json` (a pasta é a da base)."""
    destino = pasta / PASTA / f"{conferencia.feita_em.isoformat()}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(conferencia.para_json(), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return destino


def arquivos(pasta: Path) -> list[Path]:
    return sorted((pasta / PASTA).glob("*.json"))


def origens(pasta: Path) -> list[dict[str, str]]:
    """As conferências como origem da montagem: uma nova refaz a tabela."""
    return [
        {
            "url": f"{PASTA.as_posix()}/{a.name}",
            "sha256": hashlib.sha256(a.read_bytes()).hexdigest(),
        }
        for a in arquivos(pasta)
    ]


def vigente(pasta: Path, versao_da_regra: str = pt.VERSAO_DA_REGRA) -> Vigente | None:
    da_versao = [
        c
        for c in (
            Conferencia.de_json(json.loads(a.read_text(encoding="utf-8")))
            for a in arquivos(pasta)
        )
        if c.versao_da_regra == versao_da_regra
    ]
    if not da_versao:
        return None
    ultima = max(da_versao, key=lambda c: c.feita_em)
    return Vigente(
        feita_em=ultima.feita_em,
        cobre_ate=ultima.cobre_ate,
        aprovados=frozenset(c for c, v in ultima.campos.items() if v.aprovado),
        discordantes={
            campo: frozenset(
                i for c in da_versao for i in c.discordantes.get(campo, ())
            )
            for campo in CAMPOS
        },
    )


def aplicar(comunicacoes: pd.DataFrame, conferida: Vigente | None) -> pd.DataFrame:
    """As comunicações com o teor que passou na conferência: campo reprovado, comunicação que
    discordou e comunicação vista depois da amostra ficam vazios; `teor_conferido_em` diz de quando é
    a conferência que cobre a linha."""
    saida = comunicacoes.copy()
    if conferida is None:
        coberta = pd.Series(False, index=saida.index)
    else:
        coberta = pd.to_datetime(saida["visto_em"]).dt.date <= conferida.cobre_ate
    for campo in CAMPOS:
        vale = coberta.copy()
        if conferida is None or campo not in conferida.aprovados:
            vale[:] = False
        else:
            vale &= ~saida["id_na_fonte"].isin(conferida.discordantes[campo])
        saida[campo] = saida[campo].astype(object).where(vale, None)
        if campo == "resultado":
            saida["resultado_trecho"] = (
                saida["resultado_trecho"].astype(object).where(vale, None)
            )
    feita_em = conferida.feita_em if conferida else None
    saida["teor_conferido_em"] = [feita_em if c else None for c in coberta]
    return saida
