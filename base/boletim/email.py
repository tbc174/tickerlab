"""O e-mail do boletim diário da base: monta o HTML e o texto puro e envia pelo Resend.

**Um destinatário só** (`TICKERLAB_BOLETIM_PARA`, no `.env` do servidor; nunca no código, que é
público): vazio, lista ou endereço malformado = recusa. O boletim é interno; não tem link de saída e
diz que não é recomendação de investimento. A chave de idempotência é a data: o Resend não manda dois
no mesmo dia, mesmo se o roteiro rodar de novo.
"""

import html
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import requests

from base.boletim import fotografia as fo
from base.boletim.analises import Secao
from base.boletim.formato import com_sinal, grande, num, tamanho
from base.boletim.leitura_ia import Leitura
from base.boletim.tarefas import EstadoDasTarefas
from src import marca
from src.envio_newsletter import Email, EnvioFalhouError, enviar_pelo_resend

__all__ = ["EnvioFalhouError"]

VARIAVEL_DO_DESTINATARIO = "TICKERLAB_BOLETIM_PARA"
VARIAVEL_DO_REMETENTE = "TICKERLAB_BOLETIM_REMETENTE"
REMETENTE_PADRAO = "TickerLab <boletim@tickerlab.com.br>"
AVISO = "Boletim interno, só para você. Não é recomendação de investimento."
MAXIMO_NA_LISTA = 15
MAXIMO_DE_CONJUNTOS = 12  # na tabela da evolução (os que mudaram entram sempre)
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
_ENDERECO = re.compile(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+")


class DestinatarioInvalidoError(ValueError):
    """O destinatário do boletim não é um endereço só."""


def destinatario() -> str:
    para = (os.environ.get(VARIAVEL_DO_DESTINATARIO) or "").strip()
    if not _ENDERECO.fullmatch(para):
        raise DestinatarioInvalidoError(
            f"{VARIAVEL_DO_DESTINATARIO} precisa ter um endereço de e-mail só"
        )
    return para


@dataclass(frozen=True)
class Conteudo:
    dia: date
    dia_anterior: date | None  # da fotografia comparada (None no 1º dia)
    foto: dict[str, Any]
    foto_anterior: dict[str, Any] | None
    tarefas: EstadoDasTarefas
    secao: Secao
    leitura: Leitura
    proxima: str  # o título da análise de amanhã


def _e(texto: object) -> str:
    return html.escape(str(texto), quote=True)


def _data(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _grupos(c: Conteudo) -> list[tuple[str, dict[str, int], int]]:
    """(conjunto, números de agora, linhas a mais desde a anterior), do maior para o menor."""
    agora = fo.por_grupo(c.foto)
    antes = fo.por_grupo(c.foto_anterior) if c.foto_anterior else {}
    return sorted(
        (
            (nome, g, g["linhas"] - antes.get(nome, {}).get("linhas", 0))
            for nome, g in agora.items()
        ),
        key=lambda x: -x[1]["linhas"],
    )


def _contrato_com_problemas(foto: dict[str, Any]) -> list[tuple[str, int]]:
    return sorted(
        ((nome, t["problemas_do_contrato"]) for nome, t in foto["tabelas"].items()
         if t.get("contrato") == "com_problemas"),
        key=lambda x: -x[1],
    )  # fmt: skip


def fatos(c: Conteudo) -> str:
    """Os fatos do dia em texto: o que a IA lê (os mesmos números do e-mail)."""
    d = fo.comparar(c.foto_anterior, c.foto)
    linhas = [f"Data: {_data(c.dia)}."]
    if d.primeira:
        linhas.append(f"Primeiro retrato da base: {grande(d.linhas_agora)} linhas em {num(len(c.foto['tabelas']))} tabelas.")  # fmt: skip
    else:
        linhas.append(
            f"Desde {_data(c.dia_anterior or c.dia)}: linhas {grande(d.linhas_antes)} → "
            f"{grande(d.linhas_agora)} ({com_sinal(d.linhas_agora - d.linhas_antes)}); "
            f"{num(len(d.novas))} tabelas novas, {num(len(d.mudaram))} mudaram, {num(len(d.sumidas))} sumiram."
        )  # fmt: skip
        mudou = [(n, g, delta) for n, g, delta in _grupos(c) if delta]
        if mudou:
            linhas.append("Conjuntos que cresceram ou diminuíram: " + "; ".join(f"{n} {com_sinal(delta)}" for n, _, delta in mudou[:8]) + ".")  # fmt: skip
    t = c.tarefas
    if t.disponivel:
        linhas.append(
            f"Tarefas do servidor: {num(len(t.falhas))} falharam"
            + (f" ({', '.join(f.nome for f in t.falhas)})" if t.falhas else "")
            + f", {num(len(t.atrasadas))} atrasadas"
            + (f" ({', '.join(a.nome for a in t.atrasadas)})" if t.atrasadas else "")
            + "."
        )
    problemas = _contrato_com_problemas(c.foto)
    if problemas:
        linhas.append(f"Tabelas com aviso do contrato: {num(len(problemas))}.")
    s = c.secao
    linhas.append(f"Análise do dia: {s.titulo}. {s.pergunta}")
    linhas.append("Destaques: " + "; ".join(f"{r}: {v}" for r, v in s.kpis) + ".")
    linhas.append(f"Achado: {s.achado}")
    return "\n".join(linhas)


# --- HTML ------------------------------------------------------------------------------------------
_P = f"margin:6px 0;line-height:1.5;color:{marca.PAPEL_TEXTO}"
_H2 = f"font-size:17px;margin:26px 0 6px;color:{marca.MARINHO}"
_TD = f"padding:4px 8px;border-bottom:1px solid {marca.PAPEL_LINHA};font-size:13px"
_TH = f"{_TD};text-align:left;color:{marca.PAPEL_APAGADO};font-weight:600"
_CAIXA = (
    "border-radius:8px;padding:10px 14px;margin:10px 0;font-size:14px;line-height:1.5"
)


def _tabela(cabecalho: list[str], linhas: list[list[str]]) -> str:
    def celula(i: int, x: str, tag: str, estilo: str) -> str:
        alinhar = ";text-align:right" if i > 0 else ""
        return f'<{tag} style="{estilo}{alinhar}">{_e(x)}</{tag}>'

    h = "".join(celula(i, x, "th", _TH) for i, x in enumerate(cabecalho))
    corpo = "".join(
        "<tr>" + "".join(celula(i, x, "td", _TD) for i, x in enumerate(l)) + "</tr>"
        for l in linhas
    )
    return f'<table style="border-collapse:collapse;width:100%;margin:6px 0"><tr>{h}</tr>{corpo}</table>'


def _kpis(itens: list[tuple[str, str]]) -> str:
    celulas = "".join(
        f'<td style="padding:8px 10px;background:{marca.PAPEL_SUPERFICIE};border-radius:8px;vertical-align:top">'
        f'<div style="font-size:20px;font-weight:800;color:{marca.MARINHO}">{_e(v)}</div>'
        f'<div style="font-size:12px;color:{marca.PAPEL_APAGADO}">{_e(r)}</div></td>'
        for r, v in itens
    )
    return f'<table style="border-collapse:separate;border-spacing:6px;width:100%"><tr>{celulas}</tr></table>'


def _lista(itens: list[str]) -> str:
    mostrar = itens[:MAXIMO_NA_LISTA]
    resto = len(itens) - len(mostrar)
    lis = "".join(f'<li style="font-size:13px">{_e(i)}</li>' for i in mostrar)
    return f'<ul style="margin:4px 0">{lis}</ul>' + (
        f'<p style="{_P};font-size:12px">… e mais {num(resto)}.</p>' if resto else ""
    )


def _assunto(c: Conteudo) -> str:
    d = fo.comparar(c.foto_anterior, c.foto)
    partes = []
    if c.tarefas.falhas:
        n = len(c.tarefas.falhas)
        partes.append(f"⚠ {n} falha{'s' if n > 1 else ''}")
    if not d.primeira:
        partes.append(f"{com_sinal(d.linhas_agora - d.linhas_antes)} linhas")
    partes.append(c.secao.titulo)
    return f"TickerLab · Boletim da base · {c.dia:%d/%m} · " + " · ".join(partes)


def montar(c: Conteudo) -> Email:
    d = fo.comparar(c.foto_anterior, c.foto)
    s, t = c.secao, c.tarefas
    corpo: list[str] = []
    texto: list[str] = []

    # 1. a leitura do dia
    if c.leitura.texto:
        corpo.append(f'<p style="{_P};font-size:15px">{_e(c.leitura.texto)}</p>')
        texto.append(c.leitura.texto)
    else:
        nota = f"Hoje o boletim sai sem o parágrafo de leitura: {c.leitura.motivo}."
        corpo.append(
            f'<p style="{_P};font-size:12px;color:{marca.PAPEL_SUTIL}">{_e(nota)}</p>'
        )
        texto.append(nota)

    # 2. a evolução da base
    if d.primeira:
        corpo.append(f'<h2 style="{_H2}">Primeiro retrato da base</h2>')
        texto.append("\n== Primeiro retrato da base ==")
    else:
        titulo = f"A base desde {_data(c.dia_anterior or c.dia)}"
        corpo.append(f'<h2 style="{_H2}">{_e(titulo)}</h2>')
        texto.append(f"\n== {titulo} ==")
    kpis = [
        ("tabelas", num(len(c.foto["tabelas"]))),
        ("linhas", grande(d.linhas_agora)),
        ("no disco", tamanho(d.bytes_agora)),
    ]
    if not d.primeira:
        kpis = [
            ("tabelas", f"{num(len(c.foto['tabelas']))} ({com_sinal(len(d.novas) - len(d.sumidas))})"),
            ("linhas", f"{grande(d.linhas_agora)} ({com_sinal(d.linhas_agora - d.linhas_antes)})"),
            ("tabelas que mudaram", num(len(d.mudaram))),
            ("no disco", tamanho(d.bytes_agora)),
        ]  # fmt: skip
    corpo.append(_kpis(kpis))
    texto.extend(f"- {r}: {v}" for r, v in kpis)
    grupos = _grupos(c)
    # os conjuntos que mudaram primeiro e todos eles; depois os maiores, até completar a lista
    mudaram = [x for x in grupos if x[2]]
    parados = [x for x in grupos if not x[2]]
    grupos = mudaram + parados[: max(0, MAXIMO_DE_CONJUNTOS - len(mudaram))]
    fora = len(mudaram) + len(parados) - len(grupos)
    cab = ["Conjunto", "Tabelas", "Linhas"] + (
        [] if d.primeira else ["Desde a anterior"]
    )
    linhas_g = [
        [n, num(g["tabelas"]), grande(g["linhas"])]
        + ([] if d.primeira else [com_sinal(delta)])
        for n, g, delta in grupos
    ]
    corpo.append(_tabela(cab, linhas_g))
    texto.extend("  " + " | ".join(l) for l in linhas_g)
    if fora:
        nota = (
            f"… e mais {num(fora)} "
            + ("conjuntos menores" if fora > 1 else "conjunto menor")
            + ("" if d.primeira else ", sem mudança")
            + "."
        )
        corpo.append(f'<p style="{_P};font-size:12px">{_e(nota)}</p>')
        texto.append(nota)
    if not d.primeira:
        for rotulo, itens in (
            ("Tabelas novas", d.novas),
            ("Tabelas que sumiram", d.sumidas),
            (
                "Tabelas que mudaram (linhas antes → agora; versões guardadas novas)",
                [
                    f"{m.tabela}: {grande(m.linhas_antes)} → {grande(m.linhas_agora)}"
                    + (f"; +{m.versoes_novas} versão guardada" if m.versoes_novas else "")
                    for m in sorted(d.mudaram, key=lambda m: -abs((m.linhas_agora or 0) - (m.linhas_antes or 0)))
                ],
            ),
        ):  # fmt: skip
            if itens:
                corpo.append(
                    f'<p style="{_P};font-weight:600">{_e(rotulo)} ({num(len(itens))})</p>'
                )
                corpo.append(_lista(itens))
                texto.append(f"{rotulo} ({len(itens)}):")
                texto.extend(f"  - {i}" for i in itens[:MAXIMO_NA_LISTA])
    problemas = _contrato_com_problemas(c.foto)
    if problemas:
        rotulo = "Tabelas com aviso do contrato (problemas)"
        itens = [f"{n}: {num(p)}" for n, p in problemas]
        corpo.append(
            f'<p style="{_P};font-weight:600">{_e(rotulo)} ({num(len(itens))})</p>'
        )
        corpo.append(_lista(itens))
        texto.append(f"{rotulo}:")
        texto.extend(f"  - {i}" for i in itens[:MAXIMO_NA_LISTA])

    # 3. as tarefas do servidor
    corpo.append(f'<h2 style="{_H2}">Coletas e montagens</h2>')
    texto.append("\n== Coletas e montagens ==")
    if not t.disponivel:
        nota = "O estado das tarefas não estava disponível para o boletim."
        corpo.append(f'<p style="{_P}">{_e(nota)}</p>')
        texto.append(nota)
    else:
        if not t.falhas and not t.atrasadas:
            nota = f"Nenhuma falha; {num(t.em_dia)} tarefas diárias em dia."
            corpo.append(f'<p style="{_P};color:{marca.PAPEL_ALTA}">{_e(nota)}</p>')
            texto.append(nota)
        for f in t.falhas:
            linha = f"{f.nome} falhou ({f.quando[:16].replace('T', ' ')})" + (
                f": {f.motivo}" if f.motivo else ""
            )
            corpo.append(f'<div style="{_CAIXA};background:#fdecee;border:1px solid #f3c2c7">{_e(linha)}</div>')  # fmt: skip
            texto.append(f"FALHOU: {linha}")
        for a in t.atrasadas:
            linha = f"{a.nome}: sem sucesso há {num(a.horas)} h"
            corpo.append(f'<div style="{_CAIXA};background:#fdf7ea;border:1px solid #f0d9a8">{_e(linha)}</div>')  # fmt: skip
            texto.append(f"ATRASADA: {linha}")
        if t.sem_marca:
            nota = "Ainda sem marca: " + ", ".join(e.nome for e in t.sem_marca) + "."
            corpo.append(f'<p style="{_P};font-size:12px">{_e(nota)}</p>')
            texto.append(nota)

    # 4. a análise do dia
    corpo.append(f'<h2 style="{_H2}">Análise do dia: {_e(s.titulo)}</h2>')
    corpo.append(f'<p style="{_P};color:{marca.PAPEL_APAGADO}">{_e(s.pergunta)}</p>')
    corpo.append(_kpis(s.kpis))
    corpo.append(_tabela(s.cabecalho, s.linhas))
    corpo.append(f'<div style="{_CAIXA};background:#fdf7ea;border:1px solid #f0d9a8"><b>Achado.</b> {_e(s.achado)}</div>')  # fmt: skip
    corpo.append(f'<p style="{_P};font-size:12px;color:{marca.PAPEL_APAGADO}"><b>Limites.</b> {_e(s.limites)} <b>Fonte:</b> {_e(s.fonte)}.</p>')  # fmt: skip
    texto.append(f"\n== Análise do dia: {s.titulo} ==")
    texto.append(s.pergunta)
    texto.extend(f"- {r}: {v}" for r, v in s.kpis)
    texto.append("  " + " | ".join(s.cabecalho))
    texto.extend("  " + " | ".join(l) for l in s.linhas)
    texto.append(f"Achado: {s.achado}")
    texto.append(f"Limites: {s.limites} Fonte: {s.fonte}.")

    amanha = f"Amanhã: {c.proxima}."
    assunto = _assunto(c)
    data_por_extenso = f"{_data(c.dia)} ({DIAS[c.dia.weekday()]})"
    html_final = (
        f'<div style="font-family:{marca.FONTE},Arial,sans-serif;color:{marca.PAPEL_TEXTO};'
        f'max-width:680px;margin:0 auto;padding:16px">'
        f'<p style="margin:0 0 2px;font-size:22px;font-weight:800;color:{marca.MARINHO}">'
        f'Ticker<span style="color:{marca.AZUL}">Lab</span> · boletim da base</p>'
        f'<p style="margin:0 0 12px;font-size:13px;color:{marca.PAPEL_SUTIL}">{_e(data_por_extenso)}</p>'
        + "".join(corpo)
        + f'<p style="{_P};margin-top:22px">{_e(amanha)}</p>'
        f'<p style="font-size:12px;color:{marca.PAPEL_SUTIL};margin-top:24px">{_e(AVISO)}</p>'
        "</div>"
    )
    texto_final = "\n".join(
        [assunto, data_por_extenso, "", *texto, "", amanha, "", AVISO]
    )
    return Email(assunto, html_final, texto_final)


Transporte = Callable[..., requests.Response]


def enviar(
    email: Email,
    para: str,
    dia: date,
    chave: str,
    transporte: Transporte = requests.post,
) -> str:
    remetente = os.environ.get(VARIAVEL_DO_REMETENTE) or REMETENTE_PADRAO
    return enviar_pelo_resend(
        para,
        email,
        None,
        f"boletim-da-base-{dia.isoformat()}",
        chave,
        transporte,
        remetente,
    )
