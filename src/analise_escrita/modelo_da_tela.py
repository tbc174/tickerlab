"""A análise como a tela, o PDF e a API a mostram: frases com o número da nota e a lista de notas.

Só tipos simples, sem importar o relatório (ele guarda uma `AnaliseDaTela` em `Relatorio.analise`):
quem monta fica em `exibicao.py`.
"""

from dataclasses import dataclass

FAIXA_MINIMA = 3  # a partir de quantas notas seguidas elas viram "a–b"


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
class AnaliseDaTela:
    partes: tuple[ParteDaTela, ...]
    notas: tuple[NotaDaTela, ...]
    aviso: str
    # por que saiu o molde no lugar do texto do modelo, se saiu
    motivo: str | None = None

    def notas_da_parte(self, parte: ParteDaTela) -> tuple[NotaDaTela, ...]:
        """As notas citadas pelas frases da parte, na ordem do número (o rodapé do PDF)."""
        usadas = {
            n for p in parte.paragrafos for frase in p.frases for n in frase.notas
        }
        return tuple(n for n in self.notas if n.numero in usadas)
