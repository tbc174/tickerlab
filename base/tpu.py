"""A classe processual pela árvore das Tabelas Processuais Unificadas (TPU) do CNJ (Resolução CNJ
46/2007), guardada pelo arquivista (`base/arquivo/cnj_tpu.py`).

Cada classe tem uma classe mãe ("Ação Civil Pública" fica em "Procedimentos Especiais", que fica em
"Processo de Conhecimento"...). O `ramo` é um agrupamento nosso, para contar processos por tipo: a classe
mais próxima (ela mesma ou a mãe mais perto) que está em `RAMOS`. É pela classe, não pelo assunto (o DJEN
não traz o assunto): "consumidor" ou "tributário" fora da execução fiscal não dá para saber por aqui.

O código da classe não muda de sentido com o tempo, então a TPU mais recente serve para os processos
antigos também (classe que saiu da TPU continua nela, como inativa).
"""

import json
from dataclasses import dataclass

import sqlalchemy as sa

from base.arquivo import cnj_tpu
from src import acervo
from src.banco.coletas import originais_mais_recentes

# código da classe na TPU -> ramo; vale a classe mais próxima, então a ordem da árvore resolve os
# casos de dois ramos (o recurso inominado é do juizado, não um recurso comum)
RAMOS = {
    1116: "execucao_fiscal",  # Execução Fiscal
    1118: "execucao_fiscal",  # Embargos à Execução Fiscal
    210: "execucao_fiscal",  # Embargos Infringentes na Execução Fiscal
    129: "insolvencia",  # Recuperação Judicial
    128: "insolvencia",  # Recuperação Extrajudicial
    108: "insolvencia",  # Falência
    165: "insolvencia",  # Insolvência Civil
    65: "coletivo",  # Ação Civil Pública
    63: "coletivo",  # Ação Civil Coletiva
    66: "coletivo",  # Ação Popular
    119: "coletivo",  # Mandado de Segurança Coletivo
    15731: "coletivo",  # Cumprimento Coletivo de Sentença em Ações Coletivas
    15732: "coletivo",  # Cumprimento Coletivo Provisório de Sentença em Ações Coletivas
    436: "juizado_especial",  # Procedimento do Juizado Especial Cível
    14695: "juizado_especial",  # Procedimento do Juizado Especial da Fazenda Pública
    460: "juizado_especial",  # Recurso Inominado Cível
    268: "criminal",  # PROCESSO CRIMINAL
    197: "recurso",  # Recursos
    155: "cumprimento_de_sentenca",  # Procedimento de Cumprimento de Sentença/Decisão
    158: "execucao",  # Processo de Execução
    1106: "conhecimento",  # Processo de Conhecimento
}


@dataclass(frozen=True)
class Classe:
    codigo: int
    nome: str
    pai: int | None
    ativa: bool


def ler_classes(conteudo: bytes) -> dict[int, Classe]:
    """O código de cada classe -> a classe; `ValueError` se o conteúdo não é a lista da TPU."""
    lista = json.loads(conteudo)
    if not isinstance(lista, list) or not all("cod_item" in c for c in lista):
        raise ValueError("o arquivo não é a lista das classes da TPU do CNJ")
    return {
        int(c["cod_item"]): Classe(
            int(c["cod_item"]),
            str(c.get("nome") or "").strip(),
            int(c["cod_item_pai"]) if c.get("cod_item_pai") is not None else None,
            c.get("situacao") == "A",
        )
        for c in lista
    }


def _subindo(codigo: int, classes: dict[int, Classe]) -> list[Classe]:
    """A classe e as mães dela, da mais próxima à raiz (para num ciclo, que a TPU não deveria ter)."""
    vistas: list[Classe] = []
    atual = classes.get(codigo)
    while atual is not None and atual not in vistas:
        vistas.append(atual)
        atual = classes.get(atual.pai) if atual.pai is not None else None
    return vistas


def caminho(codigo: int, classes: dict[int, Classe]) -> list[str]:
    """Os nomes da raiz até a classe; vazio se a TPU não tem o código."""
    return [c.nome for c in reversed(_subindo(codigo, classes))]


def ramo(codigo: int, classes: dict[int, Classe]) -> str | None:
    return next(
        (RAMOS[c.codigo] for c in _subindo(codigo, classes) if c.codigo in RAMOS), None
    )


def classes_do_acervo(
    conexao: sa.Connection,
) -> tuple[dict[int, Classe], dict[str, str]] | None:
    """A TPU mais recente do acervo e a origem (`url`, `sha256`) para o manifesto; None se o
    arquivista ainda não a guardou."""
    for original in originais_mais_recentes(conexao, cnj_tpu.ID):
        conteudo = acervo.ler_original(original.caminho_do_original)
        if conteudo is not None:
            return ler_classes(conteudo), {
                "url": original.url,
                "sha256": original.sha256,
            }
    return None
