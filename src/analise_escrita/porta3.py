"""A porta 3 (0093): o Tiago lê a análise no Obsidian, com a fonte de cada frase aberta ao lado.

Uma nota por relatório (`tipo: revisao`), com `veredito:` vazio até ele decidir: `aprovado`,
`numero_errado` ou `tom`. Enquanto a porta 3 for total, só texto aprovado vai ao ar. Ela vira
amostra quando o critério de saída da 0100 é atingido: zero número errado em 200 relatórios
seguidos e no máximo 2% deles reprovados por tom.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from src.analise_escrita import saida

APROVADO, NUMERO_ERRADO, TOM = "aprovado", "numero_errado", "tom"
VEREDITOS = (APROVADO, NUMERO_ERRADO, TOM)
ESPERANDO = "esperando você"
SEGUIDOS_PARA_SAIR = 200
MAXIMO_POR_TOM = 0.02
CAMPOS_FORA_DA_NOTA = frozenset({"id", "secao", "tipo", "so_pro"})
_DELIMITADOR = "---"


@dataclass(frozen=True)
class Revisao:
    cnpj: str
    hash_da_entrada: str
    veredito: str
    motivo: str


@dataclass(frozen=True)
class Saida:
    seguidos: int  # relatórios mais recentes sem número errado, um atrás do outro
    por_tom: int  # quantos deles foram reprovados por tom
    atingido: bool


# --- a nota ---------------------------------------------------------------------------------------
def _comparacao(linha: dict[str, Any]) -> str:
    comparacao = linha.get("comparacao") or {}
    if not comparacao.get("texto"):
        return ""
    return f"; contra {comparacao.get('contra', '')}: {comparacao['texto']}"


def _linha_aberta(linha: dict[str, Any]) -> str:
    """O que a linha citada diz, numa linha só: nome e valor, medido em, fonte e comparação."""
    if "celulas" in linha:
        celulas = "; ".join(f"{k}: {v}" for k, v in linha["celulas"].items())
        return f"{linha.get('tabela', '')}: {celulas}"
    valor = linha.get("motivo") or linha.get("texto", "")
    nome = f"{linha['nome']}: " if linha.get("nome") else ""
    origem = ", ".join(str(linha[c]) for c in ("medido_em", "fonte") if linha.get(c))
    return f"{nome}{valor}" + (f" ({origem})" if origem else "") + _comparacao(linha)


def _conta_aberta(conta: saida.Conta) -> str:
    operandos = ", ".join(
        o.id or (f"conta {o.conta}" if o.conta is not None else f"{o.valor:g}")
        for o in conta.de
    )
    return f"conta nossa: {conta.operacao}({operandos}) = {conta.resultado:g}"


def _frase(frase: saida.Frase, linhas: dict[str, dict[str, Any]]) -> Iterator[str]:
    yield f"- {frase.texto}"
    for nota in frase.notas:
        linha = linhas.get(nota)
        aberta = _linha_aberta(linha) if linha else "id fora da ficha"
        yield f"    - `{nota}` {aberta}"
    for conta in frase.contas:
        yield f"    - {_conta_aberta(conta)}"


def _parte(
    numero: int, parte: saida.Parte, linhas: dict[str, dict[str, Any]]
) -> Iterator[str]:
    yield f"## {numero}. {saida.TITULOS[parte.chave]} (origem: {parte.origem})"
    for paragrafo in parte.paragrafos:
        yield ""
        if paragrafo.tipo == saida.LEITURA:
            yield "*Leitura.*"
        for frase in paragrafo.frases:
            yield from _frase(frase, linhas)
    yield ""


def nota(
    analise: saida.Analise, entrada: dict[str, Any], linhagem: dict[str, Any]
) -> str:
    """A nota de revisão em Markdown, com as propriedades que o painel do Obsidian lê."""
    propriedades = {
        "tipo": "revisao",
        "situacao": ESPERANDO,
        "empresa": entrada["empresa"],
        "cnpj": entrada["cnpj"],
        "modelo": linhagem.get("modelo", ""),
        "hash_da_entrada": linhagem["hash_da_entrada"],
        "veredito": "",
        "motivo": "",
    }
    linhas = {linha["id"]: linha for linha in entrada["linhas"]}
    texto = [
        _DELIMITADOR,
        *(f"{k}: {v}" for k, v in propriedades.items()),
        _DELIMITADOR,
        "",
        f"# Revisão: {entrada['empresa']}",
        "",
        f"Preencha `veredito` com {', '.join(VEREDITOS)} (e o `motivo`, se não aprovar).",
        "",
    ]
    for numero, parte in enumerate(analise.partes, start=1):
        texto += _parte(numero, parte, linhas)
    return "\n".join(texto)


# --- o veredito -----------------------------------------------------------------------------------
def propriedades(nota: str) -> dict[str, str]:
    """As propriedades entre as linhas `---` do topo (o Obsidian pode pôr aspas no valor)."""
    linhas = nota.splitlines()
    if not linhas or linhas[0].strip() != _DELIMITADOR:
        return {}
    fim = linhas.index(_DELIMITADOR, 1)
    pares = (linha.partition(":") for linha in linhas[1:fim])
    return {k.strip(): v.strip().strip("\"'") for k, _, v in pares}


def ler_revisao(nota: str) -> Revisao | None:
    """O veredito da nota; None enquanto ele estiver vazio. Veredito fora da lista é erro."""
    campos = propriedades(nota)
    veredito = campos.get("veredito", "")
    if not veredito:
        return None
    if veredito not in VEREDITOS:
        raise ValueError(f"veredito fora da lista ({', '.join(VEREDITOS)}): {veredito}")
    return Revisao(
        campos["cnpj"], campos["hash_da_entrada"], veredito, campos.get("motivo", "")
    )


def criterio_de_saida(vereditos: Sequence[str]) -> Saida:
    """Conta, do mais recente para trás, os relatórios seguidos sem número errado."""
    seguidos = 0
    for veredito in reversed(vereditos):
        if veredito == NUMERO_ERRADO:
            break
        seguidos += 1
    recentes = vereditos[len(vereditos) - seguidos :]
    por_tom = sum(v == TOM for v in recentes)
    atingido = seguidos >= SEGUIDOS_PARA_SAIR and por_tom <= MAXIMO_POR_TOM * seguidos
    return Saida(seguidos, por_tom, atingido)
