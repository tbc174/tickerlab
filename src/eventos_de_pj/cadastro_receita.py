"""Os eventos de PJ do cadastro da Receita (a vista do CNPJ, `src/cadastro_da_receita.py`).

- **mudou:** cada linha das mudanças de 12 meses da vista. Na linha "mudou", um evento por campo que
  a busca mostra e mudou (`estabelecimentos.situacao_cadastral`); na que entrou ou saiu (um sócio,
  um estabelecimento), um evento com os campos como evidência (`qsa.entrou`). Os estabelecimentos
  são só os do CNPJ pedido; o Simples e o quadro de sócios são da raiz.
- **não observado:** o CNPJ que não está no retrato vigente da vista.
- **fonte falhou:** o mês que a Receita já tinha publicado (`receita_diff.disponivel_em`) e falta na
  vista, nos 12 meses até o último publicado.

O evento do mês existe a partir do dia em que a Receita o publicou (`receita_diff.disponivel_em`).
Do sócio vai só o tipo e, quando é pessoa jurídica, a raiz do CNPJ dele: a vista não tem nome nem
pseudônimo, e este módulo não lê o restrito.

Limite honesto: a vista é o retrato de hoje com a janela de 12 meses, então "como era em" uma data
antiga só vale para as mudanças (o "não observado" é do retrato vigente).
"""

from datetime import date
from pathlib import Path

import pandas as pd

from base.porta import vista_do_cnpj
from base.receita_diff import disponivel_em as publicacao_do_mes
from src.cadastro_da_receita import CadastroDaReceita, cadastro_do_cnpj, pasta_da_vista
from src.eventos_de_pj.evento import (
    ASSUNTO_DA_LEITURA,
    FONTE_FALHOU,
    MUDOU,
    NAO_OBSERVADO,
    DescricaoDaFonte,
    Estado,
    EventoDePJ,
    Evidencia,
    cnpj_do_objeto,
    em_ordem,
    novo_evento,
)

DESCRICAO = DescricaoDaFonte(
    fonte="rfb-cnpj",
    objeto_tipo="pj",
    documento="dados abertos do CNPJ (Receita Federal)",
    versao_do_calculo="eventos_receita 1",
    formula="mudança = o campo de um mês contra o do mês anterior publicado",
)
MUDOU_NA_VISTA = (
    "mudou"  # o `tipo` da linha em que um campo mudou (as outras: "entrou", "saiu")
)
TIPO_PESSOA_JURIDICA = "1"  # `tipo_socio` do sócio que é empresa: só dele vai a raiz
CAMPOS_DO_SOCIO_PJ = ("tipo_socio", "raiz_socio_pj")
MESES_NO_ANO = 12


def _primeiro_dia(mes: str) -> date:
    return date(int(mes[:4]), int(mes[5:]), 1)


def _mes_somado(mes: str, quantos: int) -> str:
    total = int(mes[:4]) * MESES_NO_ANO + int(mes[5:]) - 1 + quantos
    return f"{total // MESES_NO_ANO:04d}-{total % MESES_NO_ANO + 1:02d}"


def ultimo_mes_publicado(hoje: date) -> str:
    """O mês mais novo que a Receita já tinha publicado no dia `hoje`."""
    mes = hoje.strftime("%Y-%m")
    return mes if publicacao_do_mes(mes) <= hoje else _mes_somado(mes, -1)


def meses_esperados(hoje: date) -> list[str]:
    """Os 12 meses publicados até `hoje`, do mais antigo para o mais novo."""
    ultimo = ultimo_mes_publicado(hoje)
    return [
        _mes_somado(ultimo, -k)
        for k in range(vista_do_cnpj.MESES_DAS_MUDANCAS - 1, -1, -1)
    ]


def _valor(valor: object) -> object:
    """O valor em tipo simples: vazio vira None, data vira texto ISO."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):  # type: ignore[arg-type]
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.date().isoformat()
    if hasattr(valor, "item"):
        return valor.item()  # type: ignore[union-attr]
    return valor


def _evidencia_da_linha(
    tabela: str, linha: pd.Series, campos: tuple[str, ...]
) -> tuple[Evidencia, ...]:
    chaves = CAMPOS_DO_SOCIO_PJ if tabela == "qsa" else ()
    das_chaves = tuple(
        Evidencia(tabela, chave, None, _valor(linha.get(chave)))
        for chave in chaves
        if chave == "tipo_socio" or str(linha.get("tipo_socio")) == TIPO_PESSOA_JURIDICA
    )
    dos_campos = tuple(
        Evidencia(
            tabela,
            campo,
            _valor(linha.get(f"{campo}_antes")),
            _valor(linha.get(f"{campo}_depois")),
        )
        for campo in campos
    )
    return das_chaves + dos_campos


def _eventos_da_linha(
    cnpj: str, tabela: str, linha: pd.Series, hoje: date
) -> list[EventoDePJ]:
    mes = str(linha["mes"])
    publico_em = publicacao_do_mes(mes)
    if publico_em > hoje:
        return []
    _, campos = vista_do_cnpj.MUDANCAS[tabela]
    evidencia = _evidencia_da_linha(tabela, linha, campos)

    def evento(assunto: str, provas: tuple[Evidencia, ...]) -> EventoDePJ:
        return novo_evento(
            DESCRICAO, cnpj, MUDOU, assunto, _primeiro_dia(mes), publico_em, provas
        )

    if linha["tipo"] != MUDOU_NA_VISTA:
        return [evento(f"{tabela}.{linha['tipo']}", evidencia)]
    chaves = tuple(e for e in evidencia if e.campo in CAMPOS_DO_SOCIO_PJ)
    return [
        evento(f"{tabela}.{prova.campo}", (*chaves, prova))
        for prova in evidencia
        if prova.campo in campos and prova.antes != prova.depois
    ]


def _do_cnpj(tabela: str, mudancas: pd.DataFrame, cnpj: str) -> pd.DataFrame:
    if mudancas.empty or tabela != "estabelecimentos":
        return mudancas
    return mudancas[mudancas["cnpj"] == cnpj]


def _mudancas(cnpj: str, cadastro: CadastroDaReceita, hoje: date) -> list[EventoDePJ]:
    eventos = []
    for tabela, mudancas in cadastro.mudancas.items():
        for _, linha in _do_cnpj(tabela, mudancas, cnpj).iterrows():
            eventos.extend(_eventos_da_linha(cnpj, tabela, linha, hoje))
    return eventos


def _da_leitura(cnpj: str, estado: Estado, mes: str, publico_em: date) -> EventoDePJ:
    return novo_evento(
        DESCRICAO, cnpj, estado, ASSUNTO_DA_LEITURA, _primeiro_dia(mes), publico_em
    )


def eventos_do_cadastro(
    cnpj: str, manifesto: dict, cadastro: CadastroDaReceita | None, *, hoje: date
) -> list[EventoDePJ]:
    """Os eventos do CNPJ nos três estados, com a vista descrita por `manifesto`, no dia `hoje`."""
    cnpj = cnpj_do_objeto(cnpj)
    lidos = set(manifesto.get("meses_das_mudancas", ()))
    falhas = [
        _da_leitura(cnpj, FONTE_FALHOU, mes, publicacao_do_mes(mes))
        for mes in meses_esperados(hoje)
        if mes not in lidos
    ]
    retrato_em = date.fromisoformat(manifesto["disponivel_em"])
    if cadastro is None:
        ausencia = (
            []
            if retrato_em > hoje
            else [_da_leitura(cnpj, NAO_OBSERVADO, manifesto["mes"], retrato_em)]
        )
        return em_ordem([*falhas, *ausencia])
    return em_ordem([*falhas, *_mudancas(cnpj, cadastro, hoje)])


def eventos_do_cnpj(
    cnpj: str, hoje: date, vista: Path | None = None
) -> list[EventoDePJ]:
    """Os eventos do CNPJ lidos da vista do servidor; sem vista, nenhum (ela ainda não chegou)."""
    vista = vista or pasta_da_vista()
    manifesto = vista_do_cnpj.manifesto(vista)
    if manifesto is None:
        return []
    cnpj = cnpj_do_objeto(cnpj)
    return eventos_do_cadastro(
        cnpj, manifesto, cadastro_do_cnpj(cnpj, vista), hoje=hoje
    )
