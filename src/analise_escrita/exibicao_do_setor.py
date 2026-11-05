"""Os gráficos do relatório do setor (plano de 23/10/2026, PR 4): o cardápio da empresa com as tabelas do setor.

O relatório do setor não mostra o texto da análise, então o gráfico não se prende a um parágrafo:
entra no fim da seção da tabela de onde saem os números dele (`GraficoDaTela.secao`), com o achado
embaixo e as linhas da ficha em `pontos.ids`. Vale a escolha publicada do modelo (o arquivo
`setor-<chave>.json` da pasta das análises, no mesmo formato do lote da empresa) quando foi feita
para esta ficha; senão, e para completar o mínimo, a reserva por regras. A entrada é a do plano de
quem vê: a seção trancada fica de fora, e gráfico de tabela que não está na ficha não passa na porta 1.
"""

from datetime import date
from pathlib import Path
from typing import Any

from src import graficos_do_relatorio as gdr
from src.analise_escrita import entrada as en
from src.analise_escrita import graficos as gr
from src.analise_escrita import reserva_dos_graficos as rg
from src.analise_escrita import saida, setor
from src.analise_escrita.exibicao import (
    CAMPO_DOS_GRAFICOS,
    SEM_ESCOLHA,
    escolha_publicada,
    ler_lote,
    pasta_das_analises,
)
from src.analise_escrita.modelo_da_tela import FraseDaTela, GraficoDaTela
from src.analise_escrita.molde import molde

__all__ = ["CAMPO_DOS_GRAFICOS", "graficos_do_setor"]


def _entrada(relatorio: dict[str, Any], corte: date) -> dict[str, Any] | None:
    try:
        return setor.entrada_do_setor(relatorio, corte)
    except (ValueError, en.DataDepoisDoCorteError, en.PessoaNaEntradaError):
        return None


def _lote_publicado(relatorio: dict[str, Any], pasta: Path) -> dict[str, Any] | None:
    lote = ler_lote(f"setor-{relatorio['setor']}", pasta)
    return lote if lote is not None and lote["publicavel"] is True else None


def _do_modelo(
    lote: dict[str, Any], entrada: dict[str, Any]
) -> tuple[gr.Escolha, saida.Analise] | None:
    """A escolha publicada e o texto dela, se são desta ficha."""
    if lote["hash_da_entrada_atual"] != en.hash_da_entrada(entrada):
        return None
    texto = saida.ler_analise(lote["analise"], saida.PARTES_DO_SETOR)
    return escolha_publicada(lote, entrada, texto), texto


def _da_tela(grafico: gr.Grafico, entrada: dict[str, Any]) -> GraficoDaTela:
    pontos = gdr.pontos_do_grafico(grafico, entrada)
    return GraficoDaTela(
        parte=grafico.parte,
        paragrafo=grafico.paragrafo,
        tipo=grafico.tipo,
        titulo=grafico.titulo,
        por_que=FraseDaTela(grafico.por_que.texto, ()),
        origem=grafico.origem,
        pontos=pontos,
        escala=gdr.escala_para(pontos),
        secao=grafico.tabela.split(".")[0],
    )


def graficos_do_setor(
    relatorio: dict[str, Any], hoje: date, pasta: Path | None = None
) -> tuple[GraficoDaTela, ...]:
    """Os gráficos do relatório do setor (`RelatorioDoSetor.como_dict()`, já com as seções
    trancadas do plano de quem vê), na ordem da escolha e depois da reserva."""
    lote = _lote_publicado(relatorio, pasta or pasta_das_analises())
    corte = date.fromisoformat(lote["corte"]) if lote else hoje
    entrada = _entrada(relatorio, corte) or _entrada(relatorio, hoje)
    if entrada is None:
        return ()
    escolha, texto = SEM_ESCOLHA, molde(entrada)
    publicada = _do_modelo(lote, entrada) if lote else None
    if publicada is not None:
        escolha, texto = publicada
    finais = rg.graficos_finais(escolha, entrada, texto, frozenset())
    return tuple(_da_tela(g, entrada) for g in finais.graficos)
