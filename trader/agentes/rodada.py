"""A rodada mensal dos agentes analistas: universo, pedidos, leitura das notas, regra e registro.

O fluxo de um mês (critérios, seção 3), numa sessão local do Claude Code:

1. `preparar` (`python -m trader.agentes.rodada preparar`, com os dados de `trader.agentes.dados`): confere os critérios aprovados, a janela (1º ao 5º pregão do mês) e os dados (até o
   pregão anterior a hoje); escolhe as candidatas pelo universo mecânico e escreve um pedido por
   empresa em `<pasta>/pedidos/`;
2. a sessão roda um subagente Sonnet por pedido, cada um sem ver os outros, e grava a resposta
   inteira em `<pasta>/respostas/<ticker>.md`;
3. `registrar`: no mesmo dia, lê todas as respostas (todas ou nenhuma), guarda os dossiês, aplica a
   regra e grava a rodada no registro em cadeia.

Nada aqui chama API, envia ordem ou lê dado pessoal. A nota é dos agentes; a carteira é da regra.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from string import Template

import pandas as pd

from trader import calendario
from trader.agentes import criterios
from trader.agentes import dados as dados_da_rodada
from trader.agentes.registro import (
    BRASILIA,
    PASTA_PADRAO,
    RegistroDeAgentes,
    RodadaRecusadaError,
)
from trader.estrategias import fatores_b3 as fb
from trader.registro import commit_atual

PROMPT = Path(__file__).resolve().parent / "prompts" / "analista.md"
ARQUIVO_DAS_CANDIDATAS = "candidatas.json"
PASTA_DOS_PEDIDOS = "pedidos"
PASTA_DAS_RESPOSTAS = "respostas"
INICIO_DO_BLOCO = "```json"
FIM_DO_BLOCO = "```"


class PoucosPregoesError(ValueError):
    """A base não tem os pregões que a média da liquidez pede."""


class ForaDaJanelaError(ValueError):
    """Hoje não é um dos primeiros pregões do mês."""


class DadosVelhosError(ValueError):
    """Os dados não chegam ao pregão anterior a hoje."""


class RespostaInvalidaError(ValueError):
    """O bloco da nota não está no formato do pedido."""


@dataclass(frozen=True)
class Candidata:
    ticker: str
    cnpj: str
    liquidez: float  # volume financeiro médio dos 60 pregões anteriores, em reais


@dataclass(frozen=True)
class Avaliacao:
    """A nota de um agente para uma empresa, já conferida."""

    ticker: str
    notas: dict[str, int]
    fontes: dict[str, tuple[str, ...]]
    vetos: tuple[dict[str, str], ...]
    resumo: str

    @property
    def nota_final(self) -> float:
        if self.vetos:
            return 0.0
        soma = sum(
            criterios.PESOS[codigo] * nota for codigo, nota in self.notas.items()
        )
        return round(
            soma / sum(criterios.PESOS.values()) * criterios.NOTA_MAXIMA / 10, 1
        )

    def para_o_registro(self, hash_do_dossie: str) -> dict:
        return {
            "ticker": self.ticker,
            "nota_final": self.nota_final,
            "notas": dict(self.notas),
            "fontes": {codigo: list(f) for codigo, f in self.fontes.items()},
            "vetos": [dict(v) for v in self.vetos],
            "resumo": self.resumo,
            "hash_do_dossie": hash_do_dossie,
        }


# --- universo e pedido ---------------------------------------------------------------------------


def candidatas(
    dia: pd.Timestamp, dados: fb.Dados, maximo: int = criterios.MAXIMO_DE_CANDIDATAS
) -> list[Candidata]:
    """As `maximo` ações mais líquidas do universo dos fatores em D (critérios, seção 2)."""
    dia = pd.Timestamp(dia)
    posicao = pd.DatetimeIndex(dados.fechamento.index).get_loc(dia)
    if not isinstance(posicao, int):
        raise TypeError(f"{dia.date()} não é um pregão único dos dados")
    if posicao < criterios.PREGOES_MINIMOS:
        raise PoucosPregoesError(
            f"a base tem {posicao} pregões antes de {dia.date()}; "
            f"a liquidez pede {criterios.PREGOES_MINIMOS}"
        )
    elegiveis = fb.universo_em(dia, dados, fb.Parametros())
    liquidez = fb.liquidez_media_em(dia, dados)
    ordem = sorted(elegiveis, key=lambda ticker: (-liquidez[ticker], ticker))[:maximo]
    cnpj = dados.cadastro["cnpj"]
    return [Candidata(t, str(cnpj[t]), float(liquidez[t])) for t in ordem]


def pedido(candidata: Candidata, data: date) -> str:
    """O pedido fixo de um agente: o prompt com a empresa, a data e o texto inteiro dos critérios."""
    return Template(PROMPT.read_text(encoding="utf-8")).substitute(
        ticker=candidata.ticker,
        cnpj=candidata.cnpj,
        data=data.isoformat(),
        versao=criterios.VERSAO,
        criterios=criterios.texto(),
    )


# --- a resposta ----------------------------------------------------------------------------------


def _ultimo_bloco(ticker: str, texto: str) -> dict:
    linhas = texto.splitlines()
    inicios = [i for i, linha in enumerate(linhas) if linha.strip() == INICIO_DO_BLOCO]
    for inicio in reversed(inicios):
        fins = [
            i
            for i in range(inicio + 1, len(linhas))
            if linhas[i].strip() == FIM_DO_BLOCO
        ]
        if fins:
            try:
                bloco = json.loads("\n".join(linhas[inicio + 1 : fins[0]]))
            except json.JSONDecodeError as erro:
                raise RespostaInvalidaError(
                    f"{ticker}: bloco json inválido ({erro})"
                ) from erro
            if not isinstance(bloco, dict):
                raise RespostaInvalidaError(f"{ticker}: o bloco json não é um objeto")
            return bloco
    raise RespostaInvalidaError(
        f"{ticker}: a resposta não termina com o bloco json da nota"
    )


def _fontes(ticker: str, codigo: str, valor: object) -> tuple[str, ...]:
    if not isinstance(valor, list) or not all(isinstance(f, str) for f in valor):
        raise RespostaInvalidaError(
            f"{ticker}: as fontes de {codigo} não são uma lista de textos"
        )
    return tuple(f.strip() for f in valor if f.strip())


def _nota(ticker: str, codigo: str, item: object) -> tuple[int, tuple[str, ...]]:
    if not isinstance(item, dict):
        raise RespostaInvalidaError(
            f"{ticker}: {codigo} não é um objeto com nota e fontes"
        )
    nota = item.get("nota")
    if not isinstance(nota, int) or isinstance(nota, bool):
        raise RespostaInvalidaError(f"{ticker}: a nota de {codigo} precisa ser inteira")
    if not criterios.NOTA_MINIMA <= nota <= criterios.NOTA_MAXIMA:
        raise RespostaInvalidaError(f"{ticker}: a nota de {codigo} vai de 0 a 10")
    fontes = _fontes(ticker, codigo, item.get("fontes", []))
    if nota > criterios.NOTA_MAXIMA_SEM_FONTE and not fontes:
        raise RespostaInvalidaError(
            f"{ticker}: nota {nota} em {codigo} sem fonte (sem fonte, no máximo "
            f"{criterios.NOTA_MAXIMA_SEM_FONTE})"
        )
    return nota, fontes


def _vetos(ticker: str, valor: object) -> tuple[dict[str, str], ...]:
    if not isinstance(valor, list):
        raise RespostaInvalidaError(f"{ticker}: vetos precisa ser uma lista")
    vetos = []
    for veto in valor:
        codigo = veto.get("codigo") if isinstance(veto, dict) else None
        if codigo not in criterios.VETOS:
            raise RespostaInvalidaError(f"{ticker}: veto desconhecido: {codigo}")
        fonte = veto.get("fonte")
        if not isinstance(fonte, str) or not fonte.strip():
            raise RespostaInvalidaError(f"{ticker}: veto {codigo} sem fonte")
        vetos.append({"codigo": codigo, "fonte": fonte.strip()})
    return tuple(vetos)


def ler_resposta(ticker: str, texto: str) -> Avaliacao:
    """Lê o último bloco json da resposta e confere o formato da seção 4.3 dos critérios."""
    bloco = _ultimo_bloco(ticker, texto)
    itens = bloco.get("itens")
    if not isinstance(itens, dict):
        raise RespostaInvalidaError(f"{ticker}: falta o objeto itens")
    desconhecidos = sorted(set(itens) - set(criterios.PESOS))
    if desconhecidos:
        raise RespostaInvalidaError(
            f"{ticker}: critério desconhecido: {', '.join(desconhecidos)}"
        )
    notas: dict[str, int] = {}
    fontes: dict[str, tuple[str, ...]] = {}
    for codigo in criterios.PESOS:
        if codigo not in itens:
            raise RespostaInvalidaError(f"{ticker}: falta o critério {codigo}")
        notas[codigo], fontes[codigo] = _nota(ticker, codigo, itens[codigo])
    resumo = bloco.get("resumo", "")
    return Avaliacao(
        ticker=ticker,
        notas=notas,
        fontes=fontes,
        vetos=_vetos(ticker, bloco.get("vetos", [])),
        resumo=resumo.strip() if isinstance(resumo, str) else "",
    )


# --- a regra -------------------------------------------------------------------------------------


def escolher(
    avaliacoes: Iterable[Avaliacao], liquidez: Mapping[str, float]
) -> dict[str, float]:
    """As até 5 maiores notas finais do corte para cima, pesos iguais (critérios, seção 5)."""
    acima = [a for a in avaliacoes if a.nota_final >= criterios.NOTA_DE_CORTE]
    ordem = sorted(
        acima, key=lambda a: (-a.nota_final, -liquidez.get(a.ticker, 0.0), a.ticker)
    )
    return {
        a.ticker: criterios.PESO_POR_EMPRESA
        for a in ordem[: criterios.MAXIMO_NA_CARTEIRA]
    }


def dentro_da_janela(dia: date) -> bool:
    """Se `dia` é um dos 5 primeiros pregões do mês."""
    fim = calendario.ultimo_pregao_do_mes(dia.year, dia.month)
    primeiros = calendario.pregoes(date(dia.year, dia.month, 1), fim)
    return dia in primeiros[: criterios.PREGOES_DA_JANELA]


# --- preparar e registrar ------------------------------------------------------------------------


def _hoje() -> date:
    return datetime.now(BRASILIA).date()


def preparar(dados: fb.Dados, pasta: Path, hoje: date | None = None) -> list[Path]:
    """Escreve os pedidos da rodada de hoje e a lista das candidatas; devolve os pedidos."""
    hash_dos_criterios = criterios.conferir()
    hoje = _hoje() if hoje is None else hoje
    if not dentro_da_janela(hoje):
        raise ForaDaJanelaError(
            f"{hoje} não está entre os {criterios.PREGOES_DA_JANELA} primeiros pregões do mês"
        )
    esperado = calendario.pregao_anterior(hoje)
    datas = pd.DatetimeIndex(dados.fechamento.index)
    antes = datas[datas < pd.Timestamp(hoje)]
    if len(antes) == 0 or antes[-1].date() != esperado:
        ultimo = antes[-1].date() if len(antes) else "nenhum pregão"
        raise DadosVelhosError(
            f"os dados vão até {ultimo}; a rodada de {hoje} usa o pregão de {esperado}"
        )
    lista = candidatas(antes[-1], dados)
    pasta_dos_pedidos = pasta / PASTA_DOS_PEDIDOS
    pasta_dos_pedidos.mkdir(parents=True, exist_ok=True)
    pedidos = []
    for candidata in lista:
        caminho = pasta_dos_pedidos / f"{candidata.ticker}.md"
        caminho.write_text(pedido(candidata, hoje), encoding="utf-8")
        pedidos.append(caminho)
    preparo = {
        "data": hoje.isoformat(),
        "dia_dos_dados": esperado.isoformat(),
        "versao_dos_criterios": criterios.VERSAO,
        "hash_dos_criterios": hash_dos_criterios,
        "candidatas": [asdict(c) for c in lista],
    }
    (pasta / ARQUIVO_DAS_CANDIDATAS).write_text(
        json.dumps(preparo, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return pedidos


def registrar(
    pasta: Path,
    registro: RegistroDeAgentes,
    modelo: str,
    agora: datetime | None = None,
) -> dict:
    """Lê todas as respostas, aplica a regra e grava a rodada; nada é gravado se faltar uma."""
    hash_dos_criterios = criterios.conferir()
    preparo = json.loads((pasta / ARQUIVO_DAS_CANDIDATAS).read_text(encoding="utf-8"))
    agora = datetime.now(BRASILIA) if agora is None else agora
    if agora.tzinfo is None:
        raise ValueError("o relógio do registro precisa de fuso horário")
    hoje = agora.astimezone(BRASILIA).date().isoformat()
    if preparo["data"] != hoje:
        raise RodadaRecusadaError(
            f"a rodada foi preparada em {preparo['data']} e só é registrada no mesmo dia "
            f"(hoje é {hoje})"
        )
    if preparo["hash_dos_criterios"] != hash_dos_criterios:
        raise RodadaRecusadaError("os pedidos foram feitos com outros critérios")
    respostas = pasta / PASTA_DAS_RESPOSTAS
    tickers = [c["ticker"] for c in preparo["candidatas"]]
    faltando = [t for t in tickers if not (respostas / f"{t}.md").exists()]
    if faltando:
        raise FileNotFoundError(
            f"faltam {len(faltando)} respostas em {respostas}: {', '.join(faltando)}"
        )
    textos = {t: (respostas / f"{t}.md").read_text(encoding="utf-8") for t in tickers}
    avaliacoes = {
        t: ler_resposta(t, textos[t]) for t in tickers
    }  # todas antes de gravar
    liquidez = {c["ticker"]: c["liquidez"] for c in preparo["candidatas"]}
    conteudo = {
        "versao_dos_criterios": criterios.VERSAO,
        "hash_dos_criterios": hash_dos_criterios,
        "modelo": modelo,
        "commit_do_codigo": commit_atual(),
        "dia_dos_dados": preparo["dia_dos_dados"],
        "candidatas": preparo["candidatas"],
        "avaliacoes": [
            avaliacoes[t].para_o_registro(registro.guardar_dossie(textos[t]))
            for t in tickers
        ],
        "escolhidas": escolher(avaliacoes.values(), liquidez),
    }
    return registro.acrescentar(conteudo, agora=agora)


# --- linha de comando ----------------------------------------------------------------------------


def conferir_registro(registro: RegistroDeAgentes) -> str:
    """O estado do registro e dos critérios, em texto (para a nota do dia e a Central)."""
    registro.verificar()
    linhas = registro.linhas()
    try:
        criterios.conferir()
        estado = f"critérios {criterios.VERSAO} aprovados"
    except criterios.CriteriosNaoAprovadosError as aviso:
        estado = str(aviso)
    ultima = linhas[-1]["data"] if linhas else "nenhuma"
    return (
        f"{estado}\nrodadas: {len(linhas)} (última: {ultima})\n"
        f"ponta da cadeia: {registro.ponta()}"
    )


def main(argumentos: list[str] | None = None) -> int:
    leitor = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    leitor.add_argument("acao", choices=("conferir", "preparar", "registrar"))
    leitor.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    leitor.add_argument("--modelo", default="")
    opcoes = leitor.parse_args(argumentos)
    registro = RegistroDeAgentes(opcoes.pasta)
    hoje = _hoje()
    pasta_da_rodada = opcoes.pasta / hoje.isoformat()[:7]
    if opcoes.acao == "preparar":
        dados = dados_da_rodada.carregar(calendario.pregao_anterior(hoje))
        pedidos = preparar(dados, pasta_da_rodada, hoje)
        print(f"{len(pedidos)} pedidos em {pasta_da_rodada / PASTA_DOS_PEDIDOS}")
    if opcoes.acao == "registrar":
        if not opcoes.modelo:
            leitor.error("registrar pede --modelo (o id do modelo dos subagentes)")
        linha = registrar(pasta_da_rodada, registro, opcoes.modelo)
        print(
            f"rodada de {linha['data']} gravada; escolhidas: {linha['escolhidas'] or 'nenhuma (CDI)'}"
        )
    print(conferir_registro(registro))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
