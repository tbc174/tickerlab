"""A análise como a tela, o PDF e a API a mostram: frases com o número da nota e a lista de notas,
mais os gráficos e os destaques presos às partes do texto.

Só tipos simples, sem importar o relatório nem o Plotly (o relatório guarda uma `AnaliseDaTela` em
`Relatorio.analise`): quem monta fica em `exibicao.py`, quem desenha em `graficos_do_relatorio.py`.
"""

from dataclasses import dataclass

FAIXA_MINIMA = 3  # a partir de quantas notas seguidas elas viram "a–b"
ROTULO_DO_DESTAQUE = "Veja na ficha a seção"  # + o título da seção e o porquê


def _faixas(numeros: tuple[int, ...]) -> str:
    """Os números das notas, com a sequência de 3 ou mais em faixa: (1, 2, 3, 4, 7) vira "1–4, 7"."""
    faixas: list[list[int]] = []
    for n in numeros:
        if faixas and n == faixas[-1][-1] + 1:
            faixas[-1].append(n)
        else:
            faixas.append([n])
    return ", ".join(
        f"{f[0]}–{f[-1]}" if len(f) >= FAIXA_MINIMA else ", ".join(map(str, f))
        for f in faixas
    )


@dataclass(frozen=True)
class NotaDaTela:
    """Uma nota numerada: o que o número é, de quando é, de onde veio e contra o que se compara."""

    numero: int
    id: str  # o id da linha da entrada (estável: é o que liga a nota à ficha)
    nome: str
    texto: str  # o valor já escrito ("26,4%", ou a linha da tabela)
    medido_em: str
    fonte: str
    comparacao: str  # "Contra X: texto"; vazio quando a linha não compara

    def legenda(self) -> str:
        """A nota em uma linha, como a página e o PDF a escrevem: o número com as suas origens."""
        partes = [
            f"{self.nome}: {self.texto}",
            f"Medido em {self.medido_em}" if self.medido_em else "",
            f"Fonte: {self.fonte}" if self.fonte else "",
            self.comparacao,
        ]
        return ". ".join(p.rstrip(".") for p in partes if p) + "."


@dataclass(frozen=True)
class FraseDaTela:
    texto: str
    notas: tuple[int, ...]  # os números das notas, na ordem em que a frase as cita

    def com_marcas(self) -> str:
        """A frase com as notas no fim ("... 26,4%. [1, 2]"), para a página e o PDF."""
        if not self.notas:
            return self.texto
        return f"{self.texto} [{_faixas(self.notas)}]"


@dataclass(frozen=True)
class ParagrafoDaTela:
    tipo: str  # "fato" ou "leitura"
    rotulo: str  # "Leitura" no parágrafo de leitura; vazio no de fato
    frases: tuple[FraseDaTela, ...]


@dataclass(frozen=True)
class ParteDaTela:
    chave: str
    titulo: str
    origem: str  # "modelo" ou "molde" (a parte que não passou nas portas)
    paragrafos: tuple[ParagrafoDaTela, ...]


@dataclass(frozen=True)
class PontosDoGrafico:
    """Tudo o que o desenho precisa, lido da ficha: uma tupla de valores por coluna."""

    tipo: str
    titulo: str
    nome_do_eixo: str
    rotulos: tuple[str, ...]
    colunas: tuple[str, ...]
    valores: tuple[tuple[float | None, ...], ...]
    # as linhas da ficha de onde cada ponto saiu, na ordem dos rótulos
    ids: tuple[str, ...]
    unidade: str  # "R$", "US$", "%" ou "" (contagem e número cru)


@dataclass(frozen=True)
class Escala:
    divisor: float
    medida: str  # "R$ bilhões", "%", "" ...
    casas: int


@dataclass(frozen=True)
class GraficoDaTela:
    """Um gráfico depois do parágrafo `paragrafo` da parte, com o achado que diz por que está ali."""

    parte: str
    paragrafo: int
    tipo: str
    titulo: str
    por_que: FraseDaTela
    origem: str  # "modelo" ou "regras" (a reserva)
    pontos: PontosDoGrafico
    escala: Escala


@dataclass(frozen=True)
class DestaqueDaTela:
    """Uma seção da ficha puxada para perto de uma parte do texto."""

    parte: str
    secao: str
    titulo: str  # o título da seção na ficha
    por_que: FraseDaTela
    origem: str


@dataclass(frozen=True)
class AnaliseDaTela:
    partes: tuple[ParteDaTela, ...]
    notas: tuple[NotaDaTela, ...]
    aviso: str
    # por que saiu o molde no lugar do texto do modelo, se saiu
    motivo: str | None = None
    graficos: tuple[GraficoDaTela, ...] = ()
    destaques: tuple[DestaqueDaTela, ...] = ()

    def graficos_do_paragrafo(
        self, parte: str, paragrafo: int
    ) -> tuple[GraficoDaTela, ...]:
        """Os gráficos que entram logo depois do parágrafo, na ordem da escolha."""
        return tuple(
            g for g in self.graficos if (g.parte, g.paragrafo) == (parte, paragrafo)
        )

    def destaques_da_parte(self, parte: str) -> tuple[DestaqueDaTela, ...]:
        return tuple(d for d in self.destaques if d.parte == parte)

    def notas_da_parte(self, parte: ParteDaTela) -> tuple[NotaDaTela, ...]:
        """As notas citadas pelas frases, gráficos e destaques da parte, na ordem do número (o
        rodapé do PDF)."""
        frases = [f for p in parte.paragrafos for f in p.frases]
        frases += [g.por_que for g in self.graficos if g.parte == parte.chave]
        frases += [d.por_que for d in self.destaques_da_parte(parte.chave)]
        usadas = {n for frase in frases for n in frase.notas}
        return tuple(n for n in self.notas if n.numero in usadas)
