"""A análise escrita no relatório da empresa: o que a página, o PDF e a API mostram (ADR 0100).

O lote (`scripts/escrever_analises.py`) deixa `analises/<cnpj>.json` na pasta das análises, que chega
ao app como as fichas do dossiê. Aqui a análise guardada vira `Relatorio.analise`, com cada nota
resolvida na linha da ficha de agora. Três travas, todas para nunca mostrar texto errado:

- só o texto aprovado na porta 3 (`publicavel`) vai ao ar;
- a ficha mudou desde que o texto foi escrito (o hash da entrada não bate): sai o molde, com o
  aviso de que a análise está sendo reescrita, nunca texto com número velho;
- quem não é Pro (D4) não vê a parte que cita o dossiê: ela sai do molde montado sem o dossiê.

Os gráficos escolhidos pelo modelo (plano de 23/10/2026) vêm no mesmo arquivo (`graficos`, gravado
pelo passo `publicar` de `scripts/escolher_graficos.py`) e valem só para a mesma ficha e o mesmo
texto; passam de novo pela porta 1 contra a ficha de agora, e a reserva por regras completa o mínimo.
Quem não é Pro não vê gráfico nem destaque do dossiê, nem o que se ancora numa parte que virou molde.

Sem arquivo, ilegível ou fora do formato, o relatório fica como estava: sem análise e sem erro. A
escolha dos gráficos fora do formato nunca derruba o texto: fica só a reserva.
"""

import dataclasses
import json
import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from src import graficos_do_relatorio as gdr
from src.analise_escrita import entrada as en
from src.analise_escrita import graficos as gr
from src.analise_escrita import montagem, saida, series
from src.analise_escrita import reserva_dos_graficos as rg
from src.analise_escrita.modelo_da_tela import (
    AnaliseDaTela,
    DestaqueDaTela,
    FraseDaTela,
    GraficoDaTela,
    NotaDaTela,
    ParagrafoDaTela,
    ParteDaTela,
)
from src.analise_escrita.molde import molde
from src.configuracao import PASTA_RAIZ
from src.planos import DOSSIE_DA_BASE, pode_usar
from src.relatorio_empresa import (
    Entradas,
    Premissas,
    Relatorio,
    escrever_celula,
    montar,
    rotulo_da_coluna,
)

log = logging.getLogger(__name__)

PASTA_DAS_ANALISES_PADRAO = PASTA_RAIZ / "dados_locais" / "analises"
TAMANHO_MAXIMO = 5_000_000  # bytes: uma análise tem algumas dezenas de KB
PLANO_COMPLETO = (
    "pro"  # a entrada é sempre a da ficha inteira (o grátis fica marcado em `so_pro`)
)
ROTULO_DA_LEITURA = "Leitura"
NOME_DA_LACUNA = "O que a base não tem"
CAMPOS_DO_LOTE = ("publicavel", "analise", "corte", "hash_da_entrada_atual")
CAMPO_DOS_GRAFICOS = "graficos"
SEM_ESCOLHA = gr.Escolha(())
AVISO_DA_ANALISE = (
    "Análise escrita por modelo de linguagem a partir de dados públicos, com cada afirmação "
    "conferida por código contra a fonte. Não é recomendação de investimento. Partes dos dados "
    "estão sob a Open Database License (ODbL 1.0): cite a fonte."
)


def pasta_das_analises() -> Path:
    return Path(os.environ.get("TICKERLAB_ANALISES") or PASTA_DAS_ANALISES_PADRAO)


def _ler_guardada(cnpj: str, pasta: Path) -> dict[str, Any] | None:
    """O arquivo do lote do CNPJ, ou None se não há, é grande demais ou está fora do formato."""
    caminho = pasta / f"{re.sub(r'\D', '', cnpj)}.json"
    try:
        if caminho.stat().st_size > TAMANHO_MAXIMO:
            log.warning("análise grande demais: %s", caminho)
            return None
        guardada = json.loads(caminho.read_text(encoding="utf-8"))
    except OSError:
        return None  # a empresa não tem análise (ou a pasta ainda não chegou)
    except ValueError:
        log.warning("análise ilegível: %s", caminho)
        return None
    if not isinstance(guardada, dict) or any(c not in guardada for c in CAMPOS_DO_LOTE):
        log.warning("análise fora do formato do lote: %s", caminho)
        return None
    return guardada


def _entrada_de_hoje(entradas: Entradas, corte: date) -> dict[str, Any] | None:
    """A entrada da ficha de agora, montada como o lote a montou (sem preço, no corte do texto)."""
    sem_preco = dataclasses.replace(
        entradas, preco=None, fechamentos=None, premissas=Premissas()
    )
    com = montar(sem_preco, PLANO_COMPLETO)
    sem = montar(dataclasses.replace(sem_preco, dossie=None), PLANO_COMPLETO)
    try:
        return en.entrada_da_ficha(com, corte, sem_dossie=sem)
    except (en.DataDepoisDoCorteError, en.PessoaNaEntradaError):
        return None


def _nota(numero: int, linha: dict[str, Any], entrada: dict[str, Any]) -> NotaDaTela:
    """A linha da entrada como a pessoa lê: nome, valor escrito, de quando, de onde, comparação."""
    secao = entrada["secoes"].get(linha.get("secao"), "")
    fonte = ""
    match linha["tipo"]:
        case "numero":
            nome = linha["nome"]
            texto = linha.get("texto") or linha.get("motivo", "")
            fonte = linha.get("fonte", "")
        case "linha":
            nome = f"{secao}: {linha['tabela']}"
            texto = "; ".join(
                f"{rotulo_da_coluna(k)} {escrever_celula(v)}"
                for k, v in linha["celulas"].items()
            )
        case "ponto":
            nome, texto, fonte = secao, linha["texto"], linha.get("tabela", "")
        case "lacuna":
            nome, texto = NOME_DA_LACUNA, linha["texto"]
        case _:
            nome, texto = secao, linha["texto"]
    comparacao = linha.get("comparacao")
    return NotaDaTela(
        numero=numero,
        id=linha["id"],
        nome=nome,
        texto=texto,
        medido_em=linha.get("medido_em", ""),
        fonte=fonte,
        comparacao=(
            f"Contra {comparacao['contra']}: {comparacao['texto']}"
            if comparacao
            else ""
        ),
    )


def _frase(
    frase: saida.Frase, linhas: dict[str, Any], numeros: dict[str, int]
) -> FraseDaTela:
    ids = [i for i in dict.fromkeys(frase.notas) if i in linhas]
    for id_ in ids:
        numeros.setdefault(id_, len(numeros) + 1)
    return FraseDaTela(frase.texto, tuple(numeros[i] for i in ids))


def _paragrafo(
    paragrafo: saida.Paragrafo, linhas: dict[str, Any], numeros: dict[str, int]
) -> ParagrafoDaTela:
    frases = tuple(_frase(frase, linhas, numeros) for frase in paragrafo.frases)
    rotulo = ROTULO_DA_LEITURA if paragrafo.tipo == saida.LEITURA else ""
    return ParagrafoDaTela(paragrafo.tipo, rotulo, frases)


@dataclasses.dataclass
class _Numeracao:
    """As notas numeradas na ordem de leitura: o parágrafo, os gráficos que vêm depois dele e, no
    fim da parte, os destaques dela. O mesmo id leva o mesmo número."""

    entrada: dict[str, Any]  # a ampliada: as notas dos gráficos citam as séries
    vista: dict[str, Any]  # a ficha que quem lê pode ver: os pontos saem só dela
    escolha: gr.Escolha
    numeros: dict[str, int] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        self.linhas = {linha["id"]: linha for linha in self.entrada["linhas"]}

    def _grafico(self, grafico: gr.Grafico) -> GraficoDaTela:
        pontos = gdr.pontos_do_grafico(grafico, self.vista)
        return GraficoDaTela(
            parte=grafico.parte,
            paragrafo=grafico.paragrafo,
            tipo=grafico.tipo,
            titulo=grafico.titulo,
            por_que=_frase(grafico.por_que, self.linhas, self.numeros),
            origem=grafico.origem,
            pontos=pontos,
            escala=gdr.escala_para(pontos),
        )

    def _destaque(self, destaque: gr.Destaque) -> DestaqueDaTela:
        return DestaqueDaTela(
            parte=destaque.parte,
            secao=destaque.secao,
            titulo=self.vista["secoes"][destaque.secao],
            por_que=_frase(destaque.por_que, self.linhas, self.numeros),
            origem=destaque.origem,
        )

    def parte(
        self, parte: saida.Parte
    ) -> tuple[ParteDaTela, list[GraficoDaTela], list[DestaqueDaTela]]:
        paragrafos, graficos = [], []
        for i, paragrafo in enumerate(parte.paragrafos):
            paragrafos.append(_paragrafo(paragrafo, self.linhas, self.numeros))
            graficos += [
                self._grafico(g)
                for g in self.escolha.graficos
                if (g.parte, g.paragrafo) == (parte.chave, i)
            ]
        destaques = [
            self._destaque(d) for d in self.escolha.destaques if d.parte == parte.chave
        ]
        titulo = saida.TITULOS[parte.chave]
        tela = ParteDaTela(parte.chave, titulo, parte.origem, tuple(paragrafos))
        return tela, graficos, destaques


def _para_a_tela(
    analise: saida.Analise,
    entrada: dict[str, Any],
    motivo: str | None,
    escolha: gr.Escolha = SEM_ESCOLHA,
    vista: dict[str, Any] | None = None,
) -> AnaliseDaTela:
    """Numera as notas na ordem de leitura e as resolve; põe gráficos e destaques nas partes."""
    numeracao = _Numeracao(entrada, vista or entrada, escolha)
    partes, graficos, destaques = [], [], []
    for parte in analise.partes:
        tela, da_parte, perto = numeracao.parte(parte)
        partes.append(tela)
        graficos += da_parte
        destaques += perto
    notas = tuple(
        _nota(n, numeracao.linhas[i], entrada) for i, n in numeracao.numeros.items()
    )
    return AnaliseDaTela(
        tuple(partes),
        notas,
        AVISO_DA_ANALISE,
        motivo,
        tuple(graficos),
        tuple(destaques),
    )


def _analise_a_mostrar(
    guardada: dict[str, Any], entrada: dict[str, Any], e_pro: bool
) -> tuple[saida.Analise, saida.Analise | None, str | None]:
    """O texto a mostrar e o publicado (None se a ficha mudou): o do modelo, o molde (ficha nova)
    ou o texto sem as partes do dossiê (quem não é Pro)."""
    if guardada["hash_da_entrada_atual"] != en.hash_da_entrada(entrada):
        return molde(entrada, e_pro), None, montagem.FICHA_NOVA
    publicada = saida.ler_analise(guardada["analise"])
    mostrada = publicada if e_pro else montagem.sem_o_dossie(publicada, entrada)
    return mostrada, publicada, None


def _escolha_publicada(
    guardada: dict[str, Any], ampliada: dict[str, Any], publicada: saida.Analise
) -> gr.Escolha:
    """A escolha do modelo, se foi feita para esta ficha e este texto; senão, nenhuma."""
    registro = guardada.get(CAMPO_DOS_GRAFICOS)
    if not isinstance(registro, dict):
        return SEM_ESCOLHA
    if registro.get("hash_da_entrada") != en.hash_da_entrada(ampliada):
        return (
            SEM_ESCOLHA  # a ficha mudou desde a escolha: o achado do porquê seria velho
        )
    if registro.get("hash_do_texto") != gr.hash_do_texto(publicada):
        return SEM_ESCOLHA  # outro texto: o parágrafo âncora pode ser outro
    try:
        return gr.ler_escolha(registro.get("escolha"))  # type: ignore[arg-type]
    except (saida.RespostaInvalidaError, ValueError, KeyError, TypeError):
        log.warning("gráficos de %s fora do formato", guardada.get("cnpj"))
        return SEM_ESCOLHA


def _sem_o_dossie(entrada: dict[str, Any]) -> dict[str, Any]:
    """A ficha de quem não é Pro: sem as linhas do dossiê (gráfico delas não passa na porta 1)."""
    return {**entrada, "linhas": [li for li in entrada["linhas"] if not li["so_pro"]]}


def _ancorada_no_mesmo_texto(
    escolha: gr.Escolha, publicada: saida.Analise, mostrada: saida.Analise
) -> gr.Escolha:
    """Só o que se ancora numa parte mostrada como foi escrita: a que virou molde tem outros
    parágrafos."""
    iguais = {p.chave for p in mostrada.partes if p in publicada.partes}
    return gr.Escolha(
        tuple(g for g in escolha.graficos if g.parte in iguais),
        tuple(d for d in escolha.destaques if d.parte in iguais),
    )


def _graficos_a_mostrar(
    guardada: dict[str, Any],
    ampliada: dict[str, Any],
    textos: tuple[saida.Analise, saida.Analise | None],
    e_pro: bool,
) -> tuple[gr.Escolha, dict[str, Any]]:
    """A escolha que vai à tela (a do modelo conferida de novo, mais a reserva) e a ficha vista.

    `textos` são o mostrado e o publicado (None quando saiu o molde: aí só a reserva)."""
    mostrada, publicada = textos
    vista = ampliada if e_pro else _sem_o_dossie(ampliada)
    escolha = SEM_ESCOLHA
    if publicada is not None:
        escolha = _escolha_publicada(guardada, ampliada, publicada)
        escolha = _ancorada_no_mesmo_texto(escolha, publicada, mostrada)
    # a porta 2 julgou antes de publicar (o passo `publicar` só grava o que passou nela); a porta 1
    # confere de novo, contra a ficha que quem lê pode ver
    return rg.graficos_finais(escolha, vista, mostrada, frozenset()), vista


def com_analise(
    relatorio: Relatorio,
    entradas: Entradas,
    plano: str | None,
    pasta: Path | None = None,
) -> Relatorio:
    """O relatório com a análise escrita, se há texto aprovado; senão, o mesmo relatório.

    `entradas` são as do relatório (para montar a ficha de agora e conferir o hash); `plano`, o de
    quem vê. A página, o PDF e a API chamam esta função e leem `relatorio.analise`.
    """
    guardada = _ler_guardada(relatorio.cnpj, pasta or pasta_das_analises())
    if guardada is None or guardada["publicavel"] is not True:
        return relatorio  # enquanto a porta 3 for total, só texto aprovado vai ao ar
    try:
        entrada = _entrada_de_hoje(entradas, date.fromisoformat(guardada["corte"]))
        if entrada is None:
            return relatorio
        e_pro = pode_usar(plano, DOSSIE_DA_BASE)
        mostrada, publicada, motivo = _analise_a_mostrar(guardada, entrada, e_pro)
    except (saida.RespostaInvalidaError, ValueError, KeyError, TypeError):
        log.warning("análise de %s fora do formato", relatorio.cnpj)
        return relatorio
    ampliada = series.ampliar(entrada)
    escolha, vista = _graficos_a_mostrar(
        guardada, ampliada, (mostrada, publicada), e_pro
    )
    tela = _para_a_tela(mostrada, ampliada, motivo, escolha, vista)
    return dataclasses.replace(relatorio, analise=tela)
