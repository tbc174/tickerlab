"""A extração de operações de M&A dos documentos do IPE (série 1, PR 2 do plano da base de M&A).

O modelo de linguagem só **copia**: tipo, partes, valores e datas vêm cada um com o trecho literal do
documento. O código confere cada um antes de aceitar (o trecho existe, o nome, o número e a data estão
nele, a moeda bate com o símbolo); o que não prova é descartado (regra 3 do dicionário: número sem
trecho de origem sai). As regras de coerência (participações que passam de 100%, datas fora de ordem)
não descartam: mandam a leitura para revisão humana, como a divergência entre as duas leituras
independentes (Haiku e Sonnet). `medir` compara com a amostra de ouro (meta: campos-chave ≥ 90%).
Este módulo não chama a API: monta o pedido, confere a resposta, mede e calcula o custo.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, get_args

import pandas as pd
from pydantic import BaseModel, Field

from base import leitor_release as lr
from src import rotulos_ia as ri

MODELO = "claude-haiku-5-5"  # a primeira leitura (barata)
CONFERENTE = "claude-sonnet-5-5"  # a segunda leitura, independente
VERSAO_DO_GUIA = "v2"  # v2: regras para escolher o tipo (18/10, medida da amostra)
ARQUIVO_DO_GUIA = Path(__file__).with_name(f"ma_extracao_guia_{VERSAO_DO_GUIA}.md")
MAX_CARACTERES_DO_TEXTO = (
    15_000  # o p95 da amostra tem ~20 mil; o anúncio está no começo
)
MAX_TOKENS_DA_RESPOSTA = 3_000
SAIDA_ESTIMADA_POR_DOCUMENTO = 700  # a ficha com os trechos; a amostra mede o real
CARACTERES_POR_TOKEN = (
    3.0  # português dá ~3,5; 3 deixa a estimativa sem API acima do real
)
PESO_DA_ESCRITA_NO_CACHE = 1.25

# Preços em US$ por milhão de tokens (skill claude-api, 17/10/2026). Leitura do cache a 0,1 da entrada.
PRECOS = {
    MODELO: ri.Modelo(0.10, 0.50, 0.1, SAIDA_ESTIMADA_POR_DOCUMENTO),
    CONFERENTE: ri.Modelo(2.00, 10.00, 0.1, SAIDA_ESTIMADA_POR_DOCUMENTO),
}

Tipo = Literal[
    "AQ_CONTROLE", "AQ_MINORITARIA", "FUSAO", "INC_EMPRESA", "INC_ACOES", "CISAO", "JV",
    "VENDA_ATIVO", "UPI", "ALIEN_CONTROLE", "OPA_CANCEL", "OPA_AUMENTO", "OPA_ALIENACAO",
    "OPA_VOLUNTARIA", "PRIVATIZACAO", "REORG", "PE_VC", "ECM", "DCM", "NAO_E_OPERACAO",
]  # fmt: skip
Etapa = Literal[
    "RUMOR", "ESCLARECIMENTO", "NEGOCIACAO", "ASSINATURA", "ASSEMBLEIA", "CADE_NOTIFICADO",
    "CADE_APROVADO", "CADE_RESTRICOES", "CADE_REPROVADO", "OUTRO_REGULADOR", "OPA_EDITAL",
    "OPA_LEILAO", "FECHAMENTO", "CANCELAMENTO",
]  # fmt: skip
Papel = Literal["alvo", "comprador", "vendedor"]
CampoDoValor = Literal["valor_participacao", "valor_empresa", "preco_por_acao"]
Unidade = Literal["unidade", "mil", "milhoes", "bilhoes"]
Moeda = Literal["BRL", "USD", "EUR", "GBP", "outra"]
FormaDePagamento = Literal["dinheiro", "acoes", "misto", "outro", "nao_informado"]

NAO_E_OPERACAO = "NAO_E_OPERACAO"
PAPEIS: tuple[Papel, ...] = get_args(Papel)
ESCALA = {"unidade": 1.0, "mil": 1e3, "milhoes": 1e6, "bilhoes": 1e9}
TOLERANCIA_DO_VALOR = (
    0.01  # 1%: "R$ 1,25 bilhão" e "R$ 1.250 milhões" são o mesmo valor
)

# Motivos de descarte (o item sai da leitura)
TRECHO_AUSENTE = lr.TRECHO_AUSENTE
NUMERO_FORA_DO_TRECHO = lr.NUMERO_FORA_DO_TRECHO
NOME_FORA_DO_TRECHO = "nome_fora_do_trecho"
MOEDA_FORA_DO_TRECHO = "moeda_fora_do_trecho"
DATA_INVALIDA = "data_invalida"
DATA_FORA_DO_TRECHO = "data_fora_do_trecho"

# Problemas de coerência (a leitura fica, mas vai para revisão humana)
TIPO_SEM_TRECHO = "tipo_sem_trecho"
SEM_ALVO = "sem_alvo"
PARTICIPACOES_ACIMA_DE_100 = "participacoes_acima_de_100"
DATAS_FORA_DE_ORDEM = "datas_fora_de_ordem"
ASSINATURA_DEPOIS_DA_PUBLICACAO = "assinatura_depois_da_publicacao"
NAO_E_OPERACAO_COM_CAMPOS = "nao_e_operacao_com_campos"


class Parte(BaseModel):
    nome: str = Field(min_length=1)
    papel: Papel
    participacao_depois: float | None = None
    trecho: str = Field(min_length=1)


class ValorLido(BaseModel):
    campo: CampoDoValor
    valor: float
    unidade: Unidade
    moeda: Moeda
    trecho: str = Field(min_length=1)

    @property
    def em_unidades(self) -> float:
        return self.valor * ESCALA[self.unidade]


class DataLida(BaseModel):
    etapa: Etapa
    data: str  # AAAA-MM-DD
    trecho: str = Field(min_length=1)


class LeituraDaOperacao(BaseModel):
    tipo: Tipo
    etapa: Etapa | None = None
    trecho_do_tipo: str = ""
    partes: list[Parte] = []
    valores: list[ValorLido] = []
    datas: list[DataLida] = []
    forma_pagamento: FormaDePagamento = "nao_informado"


@dataclass(frozen=True)
class Descarte:
    motivo: str
    campo: str
    trecho: str


@dataclass(frozen=True)
class LeituraConferida:
    leitura: LeituraDaOperacao  # só o que o código provou no texto
    descartes: list[Descarte]
    problemas: list[str]  # regras de coerência que falharam

    @property
    def precisa_de_revisao(self) -> bool:
        return bool(self.problemas)


# --- conferência no texto ------------------------------------------------------------------------

_MOEDAS = {
    "USD": re.compile(r"US\$|\bUSD\b|d[óo]lar", re.IGNORECASE),
    "BRL": re.compile(r"(?<![A-Za-z])R\$|\bBRL\b|\breais\b", re.IGNORECASE),
    "EUR": re.compile(r"€|\bEUR\b|\beuros?\b", re.IGNORECASE),
    "GBP": re.compile(r"£|\bGBP\b|\blibras?\b", re.IGNORECASE),
}
_MESES = (
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)  # fmt: skip


def _sem_acento(texto: str) -> str:
    return (
        unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    )


def _moedas_do_trecho(trecho: str) -> set[str]:
    return {moeda for moeda, padrao in _MOEDAS.items() if padrao.search(trecho)}


def _formas_da_data(dia: date) -> list[str]:
    """Os jeitos de escrever a data num documento brasileiro, já sem acento e em minúsculas."""
    d, m, a = dia.day, dia.month, dia.year
    dias = [str(d), f"{d:02d}"] + (["1o", "1º"] if d == 1 else [])
    por_extenso = [f"{x} de {_MESES[m - 1]} de {a}" for x in dias]
    numericas = [
        f"{x}{sep}{y}{sep}{a}"
        for x in (str(d), f"{d:02d}")
        for y in (str(m), f"{m:02d}")
        for sep in "/.-"
    ]
    return por_extenso + numericas


def _data_no_trecho(dia: date, trecho: str) -> bool:
    simples = " ".join(_sem_acento(trecho).casefold().split())
    return any(forma in simples for forma in _formas_da_data(dia))


def _data(texto: str) -> date | None:
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def _nome_provado(nome: str, trecho: str, normalizado: str) -> bool:
    """O nome inteiro está no trecho; ou o trecho usa o nome curto que o documento definiu ("a
    Duane", "a SABER"): toda palavra que distingue o nome aparece no documento e o trecho tem ao
    menos uma delas. Palavra genérica ("Companhia", "Participações") não prova nada."""
    if lr.normalizar(nome) in lr.normalizar(trecho):
        return True
    distintas = _distintas(nome)
    return (
        bool(distintas)
        and distintas <= set(_palavras(normalizado))
        and bool(distintas & set(_palavras(trecho)))
    )


def _conferir_partes(
    partes: list[Parte], normalizado: str, descartes: list[Descarte]
) -> list[Parte]:
    aceitas = []
    for parte in partes:
        if lr.normalizar(parte.trecho) not in normalizado:
            descartes.append(Descarte(TRECHO_AUSENTE, parte.papel, parte.trecho))
            continue
        if not _nome_provado(parte.nome, parte.trecho, normalizado):
            descartes.append(Descarte(NOME_FORA_DO_TRECHO, parte.papel, parte.trecho))
            continue
        if parte.participacao_depois is not None and lr.motivo_do_descarte(
            parte.trecho, parte.participacao_depois, normalizado
        ):
            descartes.append(
                Descarte(NUMERO_FORA_DO_TRECHO, "participacao_depois", parte.trecho)
            )
            parte = parte.model_copy(update={"participacao_depois": None})
        aceitas.append(parte)
    return aceitas


def _conferir_valores(
    valores: list[ValorLido], normalizado: str, descartes: list[Descarte]
) -> list[ValorLido]:
    aceitos = []
    for valor in valores:
        motivo = lr.motivo_do_descarte(valor.trecho, valor.valor, normalizado)
        moedas = _moedas_do_trecho(valor.trecho)
        if motivo is None and moedas and valor.moeda not in moedas:
            motivo = MOEDA_FORA_DO_TRECHO
        if motivo:
            descartes.append(Descarte(motivo, valor.campo, valor.trecho))
        else:
            aceitos.append(valor)
    return aceitos


def _conferir_datas(
    datas: list[DataLida], normalizado: str, descartes: list[Descarte]
) -> list[DataLida]:
    aceitas = []
    for lida in datas:
        dia = _data(lida.data)
        if dia is None:
            motivo = DATA_INVALIDA
        elif lr.normalizar(lida.trecho) not in normalizado:
            motivo = TRECHO_AUSENTE
        elif not _data_no_trecho(dia, lida.trecho):
            motivo = DATA_FORA_DO_TRECHO
        else:
            aceitas.append(lida)
            continue
        descartes.append(Descarte(motivo, lida.etapa, lida.trecho))
    return aceitas


def _problemas(
    leitura: LeituraDaOperacao, normalizado: str, publico_em: date
) -> list[str]:
    """As regras de coerência sobre o que já foi provado no texto."""
    if leitura.tipo == NAO_E_OPERACAO:
        com_campos = leitura.partes or leitura.valores or leitura.datas
        return [NAO_E_OPERACAO_COM_CAMPOS] if com_campos else []
    problemas = []
    if (
        lr.normalizar(leitura.trecho_do_tipo) not in normalizado
        or not leitura.trecho_do_tipo.strip()
    ):
        problemas.append(TIPO_SEM_TRECHO)
    if not any(p.papel == "alvo" for p in leitura.partes):
        problemas.append(SEM_ALVO)
    soma = sum(
        p.participacao_depois or 0.0 for p in leitura.partes if p.papel != "alvo"
    )
    if soma > 100 + 1e-6:
        problemas.append(PARTICIPACOES_ACIMA_DE_100)
    por_etapa: dict[str, list[date]] = {}
    for lida in leitura.datas:
        dia = _data(lida.data)
        if dia:
            por_etapa.setdefault(lida.etapa, []).append(dia)
    assinaturas = por_etapa.get("ASSINATURA", [])
    fechamentos = por_etapa.get("FECHAMENTO", [])
    if assinaturas and fechamentos and min(assinaturas) > max(fechamentos):
        problemas.append(DATAS_FORA_DE_ORDEM)
    if any(dia > publico_em for dia in assinaturas):
        problemas.append(ASSINATURA_DEPOIS_DA_PUBLICACAO)
    return problemas


def conferir(
    leitura: LeituraDaOperacao, texto: str, publico_em: date
) -> LeituraConferida:
    """Fica só o que o código prova no texto que o modelo leu; depois, as regras de coerência."""
    normalizado = lr.normalizar(texto_do_envio(texto))
    descartes: list[Descarte] = []
    provada = leitura.model_copy(
        update={
            "partes": _conferir_partes(leitura.partes, normalizado, descartes),
            "valores": _conferir_valores(leitura.valores, normalizado, descartes),
            "datas": _conferir_datas(leitura.datas, normalizado, descartes),
        }
    )
    return LeituraConferida(
        provada, descartes, _problemas(provada, normalizado, publico_em)
    )


# --- nomes, valores e as duas leituras ----------------------------------------------------------

_GENERICAS = frozenset(
    [
        "sa",
        "ltda",
        "cia",
        "companhia",
        "grupo",
        "holding",
        "holdings",
        "participacoes",
        "part",
        "brasil",
        "brasileira",
        "brasileiro",
        "the",
        "inc",
        "llc",
        "ltd",
        "plc",
        "empreendimentos",
        "investimentos",
        "fundo",
        "fip",
        "ativos",
        "outros",
        "acoes",
        "sociedade",
        "comercio",
        "industria",
        "servicos",
        "energia",
        "do",
        "da",
        "de",
        "dos",
        "das",
        "em",
    ]
)


def _palavras(nome: str) -> list[str]:
    sem_apostrofo = re.sub(r"['’]", "", nome)  # L'Oréal e L’Oréal são o mesmo nome
    return re.findall(r"[a-z0-9]+", _sem_acento(sem_apostrofo).casefold())


def _distintas(nome: str) -> set[str]:
    return {p for p in _palavras(nome) if len(p) >= 3 and p not in _GENERICAS}


def nomes_batem(a: str, b: str) -> bool:
    """O mesmo nome de empresa: dividem uma palavra que distingue ("Energisa", "Logística"); sem
    palavra que distinga, só o nome inteiro igual."""
    distintas_a, distintas_b = _distintas(a), _distintas(b)
    if distintas_a and distintas_b:
        return bool(distintas_a & distintas_b)
    return _palavras(a) == _palavras(b)


def _nomes(leitura: LeituraDaOperacao, papel: str) -> list[str]:
    return [p.nome for p in leitura.partes if p.papel == papel]


def _mesmos_nomes(a: list[str], b: list[str]) -> bool:
    return all(any(nomes_batem(x, y) for y in b) for x in a) and all(
        any(nomes_batem(y, x) for x in a) for y in b
    )


def _perto(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCIA_DO_VALOR * max(abs(a), abs(b))


def _algum_perto(a: Iterable[float], b: Iterable[float]) -> bool:
    b = list(b)
    return any(_perto(x, y) for x in a for y in b)


def _valores_da_participacao(leitura: LeituraDaOperacao) -> list[float]:
    return [v.em_unidades for v in leitura.valores if v.campo == "valor_participacao"]


def divergencias(a: LeituraDaOperacao, b: LeituraDaOperacao) -> list[str]:
    """Os campos-chave em que as duas leituras independentes discordam (vão para revisão humana)."""
    campos = []
    if a.tipo != b.tipo:
        campos.append("tipo")
    campos += [
        papel
        for papel in PAPEIS
        if not _mesmos_nomes(_nomes(a, papel), _nomes(b, papel))
    ]
    va, vb = _valores_da_participacao(a), _valores_da_participacao(b)
    if (va or vb) and not _algum_perto(va, vb):
        campos.append("valor")
    return campos


# --- medida na amostra de ouro --------------------------------------------------------------------

_VALOR_DO_OURO = re.compile(
    r"(?:R\$|US\$|GBP|EUR|€|£)\s*(?P<numero>\d[\d.,]*\d|\d)\s*(?P<escala>mil\b|milh\w*|bilh\w*)?",
    re.IGNORECASE,
)
_ESCALA_DO_OURO = {"mil": 1e3, "milh": 1e6, "bilh": 1e9}
FORA_DA_MEDIDA = "duvida"  # a linha em que nem a conferência da amostra decidiu


def valores_do_ouro(texto: str) -> list[float]:
    """Os valores em dinheiro escritos na amostra de ouro ("R$ 2,121 bilhões"), em unidades."""
    valores = []
    for achado in _VALOR_DO_OURO.finditer(texto or ""):
        numero = float(achado["numero"].replace(".", "").replace(",", "."))
        escala = (achado["escala"] or "").casefold()
        valores.append(numero * _ESCALA_DO_OURO.get(escala[:4] or "", 1.0))
    return sorted(valores)


def _preenchido(valor: object) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


def medir(
    leituras: Mapping[str, LeituraDaOperacao], ouro: pd.DataFrame
) -> pd.DataFrame:
    """Acertos por campo-chave contra a amostra de ouro (uma leitura por protocolo). Leitura que
    falta conta como erro; parte e valor só contam onde a amostra tem o dado."""
    casos = dict.fromkeys(("tipo", *PAPEIS, "valor"), 0)
    acertos = dict.fromkeys(casos, 0)
    for linha in ouro.to_dict("records"):
        if linha["confere_tiago"] == FORA_DA_MEDIDA:
            continue
        lida = leituras.get(str(linha["Protocolo_Entrega"]))
        operacao = _preenchido(linha["tipo_conferido"])
        esperado = linha["tipo_conferido"] if operacao else NAO_E_OPERACAO
        casos["tipo"] += 1
        acertos["tipo"] += bool(lida and lida.tipo == esperado)
        for papel in PAPEIS:
            nome = linha[papel]
            if operacao and _preenchido(nome):
                casos[papel] += 1
                acertos[papel] += bool(
                    lida and any(nomes_batem(nome, n) for n in _nomes(lida, papel))
                )
        valores = valores_do_ouro(linha["valor"]) if _preenchido(linha["valor"]) else []
        if operacao and valores:
            casos["valor"] += 1
            acertos["valor"] += bool(
                lida and _algum_perto((v.em_unidades for v in lida.valores), valores)
            )
    placar = pd.DataFrame(
        {
            "campo": list(casos),
            "casos": list(casos.values()),
            "acertos": list(acertos.values()),
        }
    )
    total = pd.DataFrame(
        {"campo": ["campos_chave"], "casos": [placar["casos"].sum()],
         "acertos": [placar["acertos"].sum()]}
    )  # fmt: skip
    placar = pd.concat([placar, total], ignore_index=True)
    return placar.assign(
        taxa=placar["acertos"] / placar["casos"].where(placar["casos"] > 0)
    )


# --- pedido e custo -------------------------------------------------------------------------------


def _enum(literal: object) -> list[str]:
    return list(get_args(literal))


def _anulavel(esquema: dict) -> dict:
    return {"anyOf": [esquema, {"type": "null"}]}


def _objeto(propriedades: dict) -> dict:
    return {
        "type": "object",
        "properties": propriedades,
        "required": list(propriedades),
        "additionalProperties": False,
    }


_TEXTO = {"type": "string"}
ESQUEMA_DA_RESPOSTA = _objeto(
    {
        "tipo": {"type": "string", "enum": _enum(Tipo)},
        "etapa": _anulavel({"type": "string", "enum": _enum(Etapa)}),
        "trecho_do_tipo": _TEXTO,
        "partes": {"type": "array", "items": _objeto({
            "nome": _TEXTO,
            "papel": {"type": "string", "enum": _enum(Papel)},
            "participacao_depois": _anulavel({"type": "number"}),
            "trecho": _TEXTO,
        })},
        "valores": {"type": "array", "items": _objeto({
            "campo": {"type": "string", "enum": _enum(CampoDoValor)},
            "valor": {"type": "number"},
            "unidade": {"type": "string", "enum": _enum(Unidade)},
            "moeda": {"type": "string", "enum": _enum(Moeda)},
            "trecho": _TEXTO,
        })},
        "datas": {"type": "array", "items": _objeto({
            "etapa": {"type": "string", "enum": _enum(Etapa)},
            "data": _TEXTO,
            "trecho": _TEXTO,
        })},
        "forma_pagamento": {"type": "string", "enum": _enum(FormaDePagamento)},
    }
)  # fmt: skip


def guia() -> str:
    return ARQUIVO_DO_GUIA.read_text(encoding="utf-8")


def texto_do_envio(texto: str) -> str:
    """O que realmente vai para a API: pessoas mascaradas e o começo do documento."""
    return lr.mascarar_pessoas(texto)[:MAX_CARACTERES_DO_TEXTO]


def pedido(texto: str, modelo: str = MODELO) -> dict:
    """O pedido à API (formato da Batch API): o guia no prefixo em cache, o documento depois."""
    return {
        "model": modelo,
        "max_tokens": MAX_TOKENS_DA_RESPOSTA,
        "system": [
            {"type": "text", "text": guia(), "cache_control": {"type": "ephemeral"}}
        ],
        "output_config": {
            "effort": "low",
            "format": {"type": "json_schema", "schema": ESQUEMA_DA_RESPOSTA},
        },
        "messages": [{"role": "user", "content": texto_do_envio(texto)}],
    }


def preco(modelo: str) -> ri.Modelo:
    """O preço do modelo; um nome fora da lista é erro (nunca o preço de outro)."""
    if modelo not in PRECOS:
        raise ValueError(f"Modelo sem preço cadastrado: {modelo}")
    return PRECOS[modelo]


def custo_em_dolares(
    tokens_entrada: float, tokens_saida: float, lote: bool = True, modelo: str = MODELO
) -> float:
    """O custo pelos preços do modelo; pela Batch API, a metade."""
    p = preco(modelo)
    custo = (tokens_entrada * p.entrada + tokens_saida * p.saida) / 1_000_000
    return custo * (ri.DESCONTO_DO_LOTE if lote else 1.0)


def estimar_custo(textos: list[str], modelo: str = MODELO) -> float:
    """O custo projetado pela Batch API sem chamar a API (nem a contagem de tokens): caracteres ÷ 3,
    o guia escrito no cache uma vez e lido nos outros, a saída estimada por documento."""
    if not textos:
        return 0.0
    n = len(textos)
    documentos = sum(len(texto_do_envio(t)) for t in textos) / CARACTERES_POR_TOKEN
    prefixo = len(guia()) / CARACTERES_POR_TOKEN
    entrada = documentos + prefixo * (
        PESO_DA_ESCRITA_NO_CACHE + preco(modelo).leitura_do_cache * (n - 1)
    )
    return custo_em_dolares(entrada, SAIDA_ESTIMADA_POR_DOCUMENTO * n, modelo=modelo)
