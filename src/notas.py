"""Notas por padrões públicos (série 2 da base de ML, PR 4; ADR 0033).

Cada indicador da empresa ganha uma nota contra o padrão do grupo de setores dela
(`src/padroes.py`), sempre com o número, o padrão, o grupo, a data do corte e a fonte ao lado:

- **Qualidade: ótimo, bom, médio, ruim ou péssimo** pelos quintis do grupo (20%, 40%, 60%, 80%), na
  direção do indicador: margem, quanto maior melhor; dívida e ciclo de caixa, quanto menor melhor.
- **Preço: barato, justo ou caro** por duas réguas: o setor (tercis: abaixo de 33% barato, acima de
  67% caro) e o próprio histórico da empresa (os mesmos tercis dos últimos anos). Se as duas
  concordam, vale a nota delas; se discordam, "justo", e as duas aparecem. Sem histórico, vale o
  setor. Múltiplo negativo (prejuízo) não tem nota.
- Número em conferência (selo de qualidade) mostra o aviso ao lado da nota.

As regras são fixas e públicas (página de metodologia). Risco regulatório aceito pelo Tiago na ADR
0033: o `AVISO` acompanha toda nota, na tela e no PDF.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from src import fundamentalista, fundamentos
from src.padroes import INDICADORES, UNIDADES
from src.setores import NOMES, SEM_GRUPO, grupo_para_comparar

QUALIDADES = ("péssimo", "ruim", "médio", "bom", "ótimo")
LIMITES_DOS_QUINTIS = ("20", "40", "60", "80")
TERCIL_BAIXO, TERCIL_ALTO = "33", "67"
FONTE = "dados abertos da CVM"
AVISO = (
    "As notas comparam o número da empresa com o das empresas do mesmo grupo de setores, por "
    "regras fixas e públicas (página de metodologia). Dizem como o número está em relação aos "
    "pares, não o que vai acontecer: não é recomendação de compra ou venda."
)


def _numero(valor: float, unidade: str) -> str:
    if unidade == fundamentos.FRACAO:
        return f"{valor * 100:.1f}%".replace(".", ",")
    if unidade == fundamentalista.DIAS:
        return f"{valor:.0f} dias"
    return f"{valor:.2f}×".replace(".", ",")


def qualidade(valor: float, percentis: dict[str, float], maior_e_melhor: bool) -> str:
    """Ótimo a péssimo pelos quintis do grupo, na direção do indicador."""
    if maior_e_melhor:
        acima = sum(valor >= percentis[p] for p in LIMITES_DOS_QUINTIS)
        return QUALIDADES[acima]
    abaixo = sum(valor <= percentis[p] for p in LIMITES_DOS_QUINTIS)
    return QUALIDADES[abaixo]


@dataclass(frozen=True)
class Nota:
    indicador: str
    nome: str
    valor: float
    nota: str
    grupo: str  # o grupo usado no padrão (pode ser o mercado)
    empresas: int
    percentis: dict[str, float]
    data_de_corte: date
    aviso_do_grupo: str = ""
    em_conferencia: bool = False

    @property
    def texto(self) -> str:
        unidade = UNIDADES[self.indicador]
        faixa = f"{_numero(self.percentis['25'], unidade)} e {_numero(self.percentis['75'], unidade)}"
        partes = [
            f"{self.nome} {_numero(self.valor, unidade)}: {self.nota}.",
            (
                f"Padrão: {NOMES.get(self.grupo, self.grupo)} ({self.empresas} empresas, corte "
                f"de {self.data_de_corte:%d/%m/%Y}, {FONTE}); metade fica entre {faixa}."
            ),
        ]
        if self.aviso_do_grupo:
            partes.append(self.aviso_do_grupo)
        if self.em_conferencia:
            partes.append(
                "Número em conferência: veja o selo de qualidade antes de tirar conclusões."
            )
        return " ".join(partes)


# --- faixa fixa e pública (série 3, PR 2; decisão do Tiago em 14/10/2026) -----------------------
# Indicadores em que o percentil do setor engana: no "caixa operacional / lucro", um número alto
# costuma vir de lucro pequeno, não de caixa bom (a Petrobras, com 1,6×, saía "péssimo"). A nota é
# por faixa fixa, sem comparar com o setor.
@dataclass(frozen=True)
class FaixaFixa:
    nome: str
    unidade: str
    abaixo_de: float  # menor que isto: a 1ª nota
    ate: float  # daqui até isto (inclusive): a 2ª; acima: a 3ª
    notas: tuple[str, str, str]
    porque: str


FAIXAS_FIXAS: dict[str, FaixaFixa] = {
    "conversao_de_caixa": FaixaFixa(
        "Caixa operacional / lucro", fundamentos.VEZES, 0.8, 1.5,
        ("atenção", "saudável", "conferir o lucro"),
        "um número alto costuma vir de lucro pequeno, não de caixa bom",
    ),
}  # fmt: skip


@dataclass(frozen=True)
class NotaPorFaixa:
    indicador: str
    nome: str
    valor: float
    nota: str

    @property
    def texto(self) -> str:
        f = FAIXAS_FIXAS[self.indicador]
        baixo, alto = _numero(f.abaixo_de, f.unidade), _numero(f.ate, f.unidade)
        return (
            f"{self.nome} {_numero(self.valor, f.unidade)}: {self.nota}. Faixa fixa e pública (não "
            f"compara com o setor): abaixo de {baixo} {f.notas[0]}; de {baixo} a {alto} "
            f"{f.notas[1]}; acima de {alto} {f.notas[2]} ({f.porque})."
        )


def nota_por_faixa(indicador: str, valor: float) -> NotaPorFaixa | None:
    """A nota de um indicador de faixa fixa (`FAIXAS_FIXAS`); None para os outros."""
    faixa = FAIXAS_FIXAS.get(indicador)
    if faixa is None:
        return None
    if valor < faixa.abaixo_de:
        nota = faixa.notas[0]
    elif valor <= faixa.ate:
        nota = faixa.notas[1]
    else:
        nota = faixa.notas[2]
    return NotaPorFaixa(indicador, faixa.nome, valor, nota)


def _padrao(padroes: pd.DataFrame, grupo: str, indicador: str) -> pd.Series | None:
    linha = padroes[(padroes["grupo"] == grupo) & (padroes["indicador"] == indicador)]
    return None if linha.empty else linha.iloc[0]


def notas_da_empresa(
    valores: dict[str, float | None],
    grupo: str,
    padroes: pd.DataFrame,
    data_de_corte: date,
    em_conferencia: bool = False,
) -> list[Nota]:
    """Uma nota por indicador com valor e com padrão (do grupo ou, se pequeno, do mercado)."""
    resultado = []
    for indicador, valor in valores.items():
        if valor is None or indicador not in INDICADORES:
            continue
        contagem = {
            g: int(n)
            for g, n in padroes.loc[
                padroes["indicador"] == indicador, ["grupo", "empresas"]
            ].itertuples(index=False)
        }
        usado, aviso = grupo_para_comparar(grupo, contagem)
        padrao = None if usado == SEM_GRUPO else _padrao(padroes, usado, indicador)
        if padrao is None:
            continue
        nome, maior_e_melhor = INDICADORES[indicador]
        resultado.append(
            Nota(
                indicador, nome, float(valor),
                qualidade(float(valor), padrao["percentis"], maior_e_melhor),
                usado, int(padrao["empresas"]), dict(padrao["percentis"]), data_de_corte,
                aviso, em_conferencia,
            )
        )  # fmt: skip
    return resultado


@dataclass(frozen=True)
class NotaDePreco:
    nota: str | None
    pelo_setor: str | None
    pelo_historico: str | None
    motivo: str = ""


def _regua(multiplo: float, percentis: dict[str, float]) -> str:
    if multiplo < percentis[TERCIL_BAIXO]:
        return "barato"
    return "caro" if multiplo > percentis[TERCIL_ALTO] else "justo"


def preco(
    multiplo: float,
    setor: dict[str, float],
    historico: dict[str, float] | None,
) -> NotaDePreco:
    """Barato, justo ou caro pelas duas réguas (setor e próprio histórico)."""
    if multiplo <= 0:
        return NotaDePreco(
            None, None, None,
            "Múltiplo negativo ou zero: a empresa teve prejuízo; não dá para dizer barato ou caro.",
        )  # fmt: skip
    pelo_setor = _regua(multiplo, setor)
    pelo_historico = None if historico is None else _regua(multiplo, historico)
    if pelo_historico is None or pelo_historico == pelo_setor:
        return NotaDePreco(pelo_setor, pelo_setor, pelo_historico)
    return NotaDePreco(
        "justo", pelo_setor, pelo_historico,
        f"As réguas discordam: {pelo_setor} contra o setor, {pelo_historico} contra o próprio histórico.",
    )  # fmt: skip
