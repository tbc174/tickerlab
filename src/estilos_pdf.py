"""Os três estilos dos relatórios em PDF (blueprint, PDF-04), todos com a identidade TickerLab.

- **Research / Claro:** o papel timbrado padrão, fundo branco com superfícies cinza-azuladas.
  Gasta pouca tinta e é o melhor para imprimir.
- **Terminal / Escuro:** o mesmo visual do app, em marinho (`marca.FUNDO`, `marca.SERIES`), para
  ler na tela.
- **Institucional / Branco e marinho:** faixa marinha da marca no topo de cada página e na capa,
  para mandar para alguém (professor, banca, cliente).

O estilo muda só as cores, nunca os números nem a ordem das seções. Para os gráficos lerem bem
impressos em preto e branco, cada série também tem um traço diferente (`TRACOS`), não só a cor.
"""

from dataclasses import dataclass

from src import marca

# do 2º em diante, cada série tem um traço próprio: dá para distinguir sem cor
TRACOS = ("-", "--", ":", "-.", (0, (5, 1, 1, 1)), (0, (1, 2)))


@dataclass(frozen=True)
class Estilo:
    chave: str
    nome: str
    descricao: str
    fundo: str
    superficie: str
    destaque: str  # fundo do número principal
    linha: str
    texto: str
    apagado: str
    alta: str
    queda: str
    aviso: str  # fundo dos avisos importantes
    series: tuple[str, ...]
    faixa: str | None = None  # faixa marinha do Institucional
    texto_da_faixa: str = "#ffffff"

    @property
    def escuro(self) -> bool:
        return self.fundo.lower() not in ("#ffffff", "#fff")


RESEARCH = Estilo(
    chave="research",
    nome="Research · Claro",
    descricao="Fundo branco, ótimo para imprimir e ler com calma.",
    fundo=marca.PAPEL_FUNDO,
    superficie=marca.PAPEL_SUPERFICIE,
    destaque="#d9e5ff",
    linha=marca.PAPEL_LINHA,
    texto=marca.PAPEL_TEXTO,
    apagado=marca.PAPEL_APAGADO,
    alta=marca.PAPEL_ALTA,
    queda=marca.PAPEL_QUEDA,
    aviso="#fdf6e4",
    series=marca.PAPEL_SERIES,
)
TERMINAL = Estilo(
    chave="terminal",
    nome="Terminal · Escuro",
    descricao="O visual do site, para ler na tela. Gasta muita tinta se imprimir.",
    fundo=marca.FUNDO,
    superficie=marca.SUPERFICIE,
    destaque="#163160",
    linha="#1f3766",
    texto=marca.TEXTO,
    apagado=marca.TEXTO_APAGADO,
    alta=marca.ALTA,
    queda=marca.QUEDA,
    aviso="#2a2414",
    series=marca.SERIES,
)
INSTITUCIONAL = Estilo(
    chave="institucional",
    nome="Institucional · Branco e marinho",
    descricao="Faixa marinha da marca em cada página, para apresentar ou enviar.",
    fundo="#ffffff",
    superficie=marca.AZUL_CLARO,
    destaque="#d9e5ff",
    linha=marca.PAPEL_LINHA,
    texto=marca.MARINHO,
    apagado=marca.PAPEL_APAGADO,
    alta=marca.PAPEL_ALTA,
    queda=marca.PAPEL_QUEDA,
    aviso="#fdf6e4",
    series=(marca.AZUL, marca.MARINHO, "#11897a", "#c77700", "#b8417f", "#6b4fe0"),
    faixa=marca.MARINHO,
    texto_da_faixa=marca.CLARO,
)
ESTILOS = {e.chave: e for e in (RESEARCH, TERMINAL, INSTITUCIONAL)}
PADRAO = RESEARCH


def estilo(chave: str | None) -> Estilo:
    """O estilo pela chave; uma chave desconhecida (ou vazia) volta ao padrão."""
    return ESTILOS.get(chave or "", PADRAO)
