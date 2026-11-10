"""A resposta da tela do analista numa planilha do Excel (linha 798), no molde da planilha da CLI (linha 773).

A mesma forma de `cli/tickerlab/planilha.py`, para a equipe achar as mesmas abas pelo app e pela CLI: a aba
`campos` com os campos soltos (o caminho, o valor cru, a fonte e o dia em que ficou público), uma aba por lista
da resposta (uma linha por item, com a fonte e o dia no fim) e a aba `fontes` com a atribuição e a licença que
cada fonte pede e o aviso de que nada é recomendação de investimento. Os nomes ficam em português (a tela fala
português; a CLI recebe a resposta da API, em inglês). A CLI não importa `src/` (instala num PC de fora), então
o código é outro; um teste confere que as duas dão a mesma forma para a mesma resposta.

Texto da base (a razão social, por exemplo) vai sempre como texto, nunca como fórmula: um nome que começa com
`=` não pode virar fórmula no Excel de quem abre o arquivo.
"""

import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from openpyxl import Workbook
from openpyxl.cell.cell import TYPE_STRING

COLUNA_DA_FONTE = "fonte"
COLUNA_DA_DATA = "publicado_em"
CHAVE_DAS_FONTES = "fontes"
SEPARADOR = " › "
AVISO = "Nada aqui é recomendação de investimento."  # o mesmo aviso da CLI (`tickerlab.formato.AVISO`)
LIMITE_DO_NOME_DA_ABA = 31  # o Excel não abre aba com nome maior
DATA_FIXA = datetime(2026, 1, 1, tzinfo=UTC)  # a mesma resposta dá o mesmo arquivo

Valor = str | int | float | bool | None


@dataclass
class Aba:
    """Uma aba da planilha: o nome (o caminho na resposta), o cabeçalho e as linhas com valores crus."""

    nome: str
    cabecalho: list[str]
    linhas: list[list[Valor]] = field(default_factory=list)


def _e_envelope(valor: object) -> bool:
    return isinstance(valor, Mapping) and "valor" in valor and "fonte" in valor


def _cru(valor: object) -> Valor:
    """O valor como a planilha o guarda: o `valor` do envelope; lista ou objeto vira texto."""
    if _e_envelope(valor):
        valor = valor["valor"]  # type: ignore[index]
    if valor is None or isinstance(valor, str | int | float | bool):
        return valor
    return str(valor)


def _fonte_e_data(envelopes: Sequence[Mapping]) -> list[Valor]:
    """As fontes e as datas de publicação distintas da linha, juntas (quase sempre uma de cada)."""
    fontes = dict.fromkeys(str(env.get("fonte")) for env in envelopes)
    datas = dict.fromkeys(str(env.get("publico_em") or "") for env in envelopes)
    return [", ".join(fontes), ", ".join(d for d in datas if d) or None]


def _juntar(caminho: str, nome: str) -> str:
    return f"{caminho}{SEPARADOR}{nome}" if caminho else nome


def _aba_de_linhas(nome: str, itens: Sequence[Mapping]) -> Aba:
    colunas = list(dict.fromkeys(chave for item in itens for chave in item))
    com_fonte = any(_e_envelope(v) for item in itens for v in item.values())
    aba = Aba(
        nome, [*colunas, *([COLUNA_DA_FONTE, COLUNA_DA_DATA] if com_fonte else [])]
    )
    for item in itens:
        valores = [_cru(item.get(coluna)) for coluna in colunas]
        if com_fonte:
            valores += _fonte_e_data([v for v in item.values() if _e_envelope(v)])
        aba.linhas.append(valores)
    return aba


def _percorrer(caminho: str, dado: Mapping, campos: Aba, abas: list[Aba]) -> None:
    """Os campos com fonte vão para `campos`; cada lista vira uma aba; o resto desce."""
    for nome, valor in dado.items():
        if nome == CHAVE_DAS_FONTES and not caminho:
            continue
        lugar = _juntar(caminho, str(nome))
        if _e_envelope(valor):
            campos.linhas.append([lugar, _cru(valor), *_fonte_e_data([valor])])
        elif valor is None or isinstance(valor, str | int | float | bool):
            # o que identifica o pedido (CNPJ, dia): sem fonte, não é dado de fonte
            campos.linhas.append([lugar, valor, None, None])
        elif isinstance(valor, Mapping):
            _percorrer(lugar, valor, campos, abas)
        elif isinstance(valor, list):
            _lista(lugar, valor, abas)


def _lista(caminho: str, itens: list, abas: list[Aba]) -> None:
    if objetos := [item for item in itens if isinstance(item, Mapping)]:
        abas.append(_aba_de_linhas(caminho, objetos))
    elif textos := [item for item in itens if isinstance(item, str)]:
        abas.append(Aba(caminho, ["texto"], [[texto] for texto in textos]))


def _aba_das_fontes(corpo: Mapping) -> Aba:
    fontes = Aba(CHAVE_DAS_FONTES, ["fonte", "atribuicao", "licenca"])
    for item in corpo.get(CHAVE_DAS_FONTES) or []:
        if isinstance(item, Mapping):
            fontes.linhas.append(
                [
                    _cru(item.get("fonte")),
                    _cru(item.get("atribuicao")),
                    _cru(item.get("licenca")),
                ]
            )
    fontes.linhas.append(["aviso", AVISO, None])
    return fontes


def abas(corpo: Mapping) -> list[Aba]:
    """As abas da planilha: `campos`, uma por lista da resposta e `fontes` no fim."""
    campos = Aba("campos", ["campo", "valor", COLUNA_DA_FONTE, COLUNA_DA_DATA])
    listas: list[Aba] = []
    _percorrer("", corpo, campos, listas)
    return [*([campos] if campos.linhas else []), *listas, _aba_das_fontes(corpo)]


def _nome_da_aba(nome: str, usados: set[str]) -> str:
    """O fim do caminho, cortado no tamanho que o Excel aceita e sem repetir."""
    base = nome.split(SEPARADOR)[-1][:LIMITE_DO_NOME_DA_ABA] or "tabela"
    final, extra = base, 2
    while final.lower() in usados:
        sufixo = f"~{extra}"
        final, extra = base[: LIMITE_DO_NOME_DA_ABA - len(sufixo)] + sufixo, extra + 1
    usados.add(final.lower())
    return final


def xlsx(corpo: Mapping) -> bytes:
    """O arquivo XLSX da resposta, uma aba por tabela; texto sempre como texto, nunca como fórmula."""
    pasta = Workbook()
    pasta.remove(pasta.active)  # type: ignore[arg-type]
    pasta.properties.creator = "TickerLab"
    pasta.properties.created = pasta.properties.modified = DATA_FIXA
    usados: set[str] = set()
    for aba in abas(corpo):
        folha = pasta.create_sheet(_nome_da_aba(aba.nome, usados))
        for numero, valores in enumerate([aba.cabecalho, *aba.linhas], start=1):
            for coluna, valor in enumerate(valores, start=1):
                if valor is None:
                    continue
                celula = folha.cell(row=numero, column=coluna, value=valor)
                if isinstance(valor, str):
                    celula.data_type = (
                        TYPE_STRING  # o openpyxl leria "=..." como fórmula
                    )
    saida = io.BytesIO()
    pasta.save(saida)
    return saida.getvalue()
