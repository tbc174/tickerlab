"""A ligação das etapas (série 1, PR 3 do plano da base de M&A): os documentos da mesma operação viram
uma linha de operação.

Uma operação aparece em vários documentos: a compradora e a alvo publicam cada uma o seu fato relevante
no mesmo dia (BTG e Pan, Totvs e Bematech na amostra de ouro), e depois vêm a assembleia, o CADE e o
fechamento. Contar cada documento como uma operação duplicaria o placar e os precedentes.

Regra (fixa e explicável, sem modelo): dois documentos lidos são da mesma operação quando
1. nenhum dos dois é "não é operação";
2. os tipos são da mesma família (`FAMILIAS`: a venda de um lado é a aquisição do outro);
3. a alvo é a mesma empresa (`mesma_empresa`: as palavras que distinguem o nome mais curto estão
   todas no outro; a `nomes_batem` da medida juntaria "Banco BTG Pactual" e "Banco Pan");
4. se os dois dizem quem compra, é o mesmo comprador (a mesma alvo vendida duas vezes são duas operações);
5. a distância até algum documento da operação é de no máximo `JANELA_EM_DIAS`.
A ligação é transitiva: a assembleia liga ao anúncio, o fechamento à assembleia. Documento sem alvo
provada fica sozinho (sem prova, não liga).
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date

import pandas as pd

from base import ma_extracao as mx

JANELA_EM_DIAS = (
    540  # o CADE leva até ~1 ano nos casos complexos; depois disso, é outra operação
)

FAMILIAS = {
    "controle": {
        "AQ_CONTROLE", "AQ_MINORITARIA", "ALIEN_CONTROLE", "OPA_ALIENACAO", "PRIVATIZACAO",
        "VENDA_ATIVO", "UPI", "PE_VC",
    },
    "reorganizacao": {"FUSAO", "INC_EMPRESA", "INC_ACOES", "CISAO", "REORG"},
    "opa": {"OPA_CANCEL", "OPA_AUMENTO", "OPA_VOLUNTARIA"},
    "jv": {"JV"},
    "ecm": {"ECM"},
    "dcm": {"DCM"},
}  # fmt: skip
FAMILIA_DO_TIPO = {
    tipo: familia for familia, tipos in FAMILIAS.items() for tipo in tipos
}

# a situação pela etapa mais avançada que algum documento provou (a mais forte vence)
ANUNCIADA, APROVADA, CONCLUIDA, CANCELADA = (
    "anunciada",
    "aprovada",
    "concluida",
    "cancelada",
)
SITUACAO_DA_ETAPA = {
    "ASSEMBLEIA": APROVADA,
    "CADE_APROVADO": APROVADA,
    "CADE_RESTRICOES": APROVADA,
    "OUTRO_REGULADOR": APROVADA,
    "OPA_LEILAO": CONCLUIDA,
    "FECHAMENTO": CONCLUIDA,
    "CADE_REPROVADO": CANCELADA,
    "CANCELAMENTO": CANCELADA,
}
FORCA_DA_SITUACAO = {ANUNCIADA: 0, APROVADA: 1, CONCLUIDA: 2, CANCELADA: 3}


@dataclass(frozen=True)
class DocumentoLido:
    protocolo: str
    publico_em: date
    leitura: mx.LeituraDaOperacao  # já conferida no texto (`mx.conferir`)


def _nomes(documento: DocumentoLido, papel: str) -> list[str]:
    return [p.nome for p in documento.leitura.partes if p.papel == papel]


def _algum_bate(a: list[str], b: list[str]) -> bool:
    return any(mx.mesma_empresa(x, y) for x in a for y in b)


def mesma_operacao(a: DocumentoLido, b: DocumentoLido) -> bool:
    """As regras 1 a 4 do módulo (a janela de datas fica com `ligar`, que a mede na operação)."""
    familia_a = FAMILIA_DO_TIPO.get(a.leitura.tipo)
    if familia_a is None or familia_a != FAMILIA_DO_TIPO.get(b.leitura.tipo):
        return False
    if not _algum_bate(_nomes(a, "alvo"), _nomes(b, "alvo")):
        return False
    compradores_a, compradores_b = _nomes(a, "comprador"), _nomes(b, "comprador")
    return not (compradores_a and compradores_b) or _algum_bate(
        compradores_a, compradores_b
    )


def ligar(documentos: list[DocumentoLido]) -> dict[str, str]:
    """O protocolo de cada documento de operação → o id da operação (o protocolo do 1º documento)."""
    ordem = sorted(documentos, key=lambda d: (d.publico_em, d.protocolo))
    chefe = {d.protocolo: d.protocolo for d in ordem}
    lugar = {
        d.protocolo: i for i, d in enumerate(ordem)
    }  # a raiz é o documento mais antigo

    def raiz(protocolo: str) -> str:
        while chefe[protocolo] != protocolo:
            chefe[protocolo] = chefe[chefe[protocolo]]
            protocolo = chefe[protocolo]
        return protocolo

    da_familia: dict[str, list[DocumentoLido]] = {}  # só se compara dentro da família
    for documento in ordem:
        familia = FAMILIA_DO_TIPO.get(documento.leitura.tipo)
        if familia is None:
            continue
        anteriores = da_familia.setdefault(familia, [])
        for anterior in reversed(anteriores):
            if (documento.publico_em - anterior.publico_em).days > JANELA_EM_DIAS:
                break
            if mesma_operacao(anterior, documento):
                a, b = raiz(anterior.protocolo), raiz(documento.protocolo)
                primeiro, depois = sorted((a, b), key=lugar.__getitem__)
                chefe[depois] = primeiro
        anteriores.append(documento)
    return {
        d.protocolo: raiz(d.protocolo)
        for d in ordem
        if d.leitura.tipo != mx.NAO_E_OPERACAO
    }


def _situacao(documentos: list[DocumentoLido]) -> str:
    etapas = [d.leitura.etapa for d in documentos] + [
        e.etapa for d in documentos for e in d.leitura.datas
    ]
    situacoes = [SITUACAO_DA_ETAPA.get(e or "", ANUNCIADA) for e in etapas]
    return max(situacoes, key=FORCA_DA_SITUACAO.__getitem__, default=ANUNCIADA)


def _tipo(documentos: list[DocumentoLido]) -> str:
    """O tipo mais lido; no empate, o do documento mais novo (ele já sabe mais da operação)."""
    contagem = Counter(d.leitura.tipo for d in documentos)
    return max(
        reversed(documentos), key=lambda d: contagem[d.leitura.tipo]
    ).leitura.tipo


def operacoes(documentos: list[DocumentoLido]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A tabela de operações e a de documentos de cada operação."""
    ligacao = ligar(documentos)
    por_protocolo = {d.protocolo: d for d in documentos}
    grupos: dict[str, list[DocumentoLido]] = {}
    for protocolo, operacao in ligacao.items():
        grupos.setdefault(operacao, []).append(por_protocolo[protocolo])
    linhas = []
    for operacao, membros in grupos.items():
        membros.sort(key=lambda d: (d.publico_em, d.protocolo))
        tipo = _tipo(membros)
        alvos = [n for d in membros for n in _nomes(d, "alvo")]
        linhas.append(
            {
                "operacao": operacao,
                "tipo": tipo,
                "familia": FAMILIA_DO_TIPO[tipo],
                "situacao": _situacao(membros),
                "alvo": alvos[0] if alvos else None,
                "primeira_data_publica": membros[0].publico_em,
                "ultima_data_publica": membros[-1].publico_em,
                "documentos": len(membros),
            }
        )
    tabela = pd.DataFrame(linhas, columns=_COLUNAS)
    ligacoes = pd.DataFrame(
        sorted(ligacao.items(), key=lambda par: (par[1], par[0])),
        columns=["protocolo", "operacao"],
    )
    return tabela.sort_values(["primeira_data_publica", "operacao"]).reset_index(
        drop=True
    ), ligacoes


def pares(ligacao: dict[str, str]) -> set[frozenset[str]]:
    """Os pares de documentos que ficaram na mesma operação."""
    grupos: dict[str, list[str]] = {}
    for protocolo, operacao in ligacao.items():
        grupos.setdefault(operacao, []).append(protocolo)
    return {
        frozenset((a, b))
        for membros in grupos.values()
        for i, a in enumerate(membros)
        for b in membros[i + 1 :]
    }


def comparar(
    lida: dict[str, str], gabarito: dict[str, str]
) -> dict[str, list[list[str]]]:
    """Onde a ligação das leituras difere da do gabarito, só nos documentos que os dois têm:
    `separadas` são as duplicadas (o gabarito junta, a leitura não) e `juntadas` as operações
    diferentes que viraram uma."""
    comuns = set(lida) & set(gabarito)
    da_leitura = pares({p: o for p, o in lida.items() if p in comuns})
    do_gabarito = pares({p: o for p, o in gabarito.items() if p in comuns})
    return {
        "no_gabarito": sorted(sorted(par) for par in do_gabarito),
        "separadas": sorted(sorted(par) for par in do_gabarito - da_leitura),
        "juntadas": sorted(sorted(par) for par in da_leitura - do_gabarito),
    }


_COLUNAS = [
    "operacao",
    "tipo",
    "familia",
    "situacao",
    "alvo",
    "primeira_data_publica",
    "ultima_data_publica",
    "documentos",
]
