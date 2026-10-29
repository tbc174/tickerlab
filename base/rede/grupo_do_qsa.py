"""O grupo econômico pelo quadro de sócios da Receita (Ficha Clara, etapa 5; fila 525).

**Ligação.** Uma aresta por sócia pessoa jurídica: a raiz da sócia é sócia da raiz da empresa, no QSA vigente
(`tipo_socio` 1). O QSA não diz quanto cada sócia tem nem quem manda, então a ligação é "sócia de", nunca
"controlada por": a cadeia de controle das companhias abertas é a do FRE (`base/rede/controle.py`).

**Grupo.** O que se alcança da empresa andando pelas ligações nos dois sentidos: as sócias, as sócias delas, as
empresas de que ela é sócia e as irmãs (outra empresa da mesma sócia). A busca anda em largura, um passo por
vez e em ordem de raiz (a mesma resposta a cada leitura), e para em `profundidade` passos ou `limite` empresas.
Uma holding grande alcança milhares, então o recorte vem marcado: `completo` falso e, em `ligacoes_de_fora`,
quantas ligações saem dele.

**Só pessoa jurídica.** O sócio pessoa física e o estrangeiro não entram, nem o pseudônimo da pessoa. Ligar
duas empresas por terem a mesma pessoa como sócia seria montar o patrimônio de uma pessoa (ADR 0106).

**Sem olhar o futuro.** É o retrato vigente da vista do CNPJ, que vale desde o `disponivel_em` do manifesto
(o dia em que a Receita publicou o mês), e o grupo diz de que mês é.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import pandas as pd

from base.porta import vista_do_cnpj

PROFUNDIDADE = 3  # até as sócias das sócias das sócias (as irmãs estão a 2 passos)
LIMITE = (
    100  # empresas no grupo: além disso, a ficha mostra o recorte e diz que há mais
)
SOCIO_PESSOA_JURIDICA = "1"  # `tipo_socio` da Receita
RAIZ = r"[0-9A-Z]{8}"  # o CNPJ alfanumérico (2026) também


@dataclass(frozen=True)
class Ligacao:
    """A `socia` é sócia pessoa jurídica da `empresa` (as duas pela raiz do CNPJ)."""

    socia: str
    empresa: str
    qualificacao: str  # o código da Receita (22 sócio, 49 sócio-administrador...)
    entrada_em: str | None  # ISO; vazio quando a Receita não informa


@dataclass(frozen=True)
class Empresa:
    raiz: str
    passos: int  # quantas ligações a separam da empresa pedida


@dataclass(frozen=True)
class Grupo:
    """O grupo de uma empresa, em tipos simples (vira JSON como está)."""

    raiz: str
    empresas: tuple[Empresa, ...]  # a pedida primeiro, depois por passos e raiz
    ligacoes: tuple[Ligacao, ...]  # só entre empresas do grupo
    completo: bool  # falso se alguma ligação sai do recorte (a profundidade ou o limite cortou)
    ligacoes_de_fora: int  # ligações de uma empresa do grupo a uma que ficou de fora
    retrato: str | None = None  # o mês do QSA (AAAA-MM)
    disponivel_em: str | None = None  # desde quando o retrato é público (ISO)

    def como_dict(self) -> dict:
        return asdict(self)


Leitura = Callable[[str], pd.DataFrame]


def _data(valor: object) -> str | None:
    dia = pd.to_datetime(valor, errors="coerce")  # type: ignore[arg-type]
    return None if pd.isna(dia) else dia.date().isoformat()


def ligacoes(tabela: pd.DataFrame) -> list[Ligacao]:
    """As ligações de linhas do QSA (ou das participações): só sócia pessoa jurídica de raiz bem formada."""
    if tabela.empty:
        return []
    linhas = tabela
    if "tipo_socio" in linhas:
        linhas = linhas[linhas["tipo_socio"].astype(str) == SOCIO_PESSOA_JURIDICA]
    socia = linhas["raiz_socio_pj"].fillna("").astype(str).str.strip().str.upper()
    empresa = linhas["cnpj_basico"].fillna("").astype(str).str.strip().str.upper()
    boas = socia.str.fullmatch(RAIZ) & empresa.str.fullmatch(RAIZ) & (socia != empresa)
    return [
        Ligacao(s, e, str(q or ""), _data(d))
        for s, e, q, d in zip(
            socia[boas],
            empresa[boas],
            linhas.loc[boas, "qualificacao"],
            linhas.loc[boas, "data_entrada"],
            strict=True,
        )
    ]


def _vizinhas(raiz: str, socias_de: Leitura, participadas_de: Leitura) -> list[Ligacao]:
    return ligacoes(socias_de(raiz)) + ligacoes(participadas_de(raiz))


def montar_grupo(
    raiz: str,
    socias_de: Leitura,
    participadas_de: Leitura,
    profundidade: int = PROFUNDIDADE,
    limite: int = LIMITE,
) -> Grupo:
    """O grupo da `raiz`: `socias_de(r)` dá o QSA de r; `participadas_de(r)`, as empresas de que r é sócia."""
    raiz = raiz.strip().upper()
    passos = {raiz: 0}
    vistas: set[Ligacao] = set()
    camada = [raiz]
    for passo in range(1, profundidade + 1):
        proxima = _abrir(camada, passos, vistas, socias_de, participadas_de)
        camada = proxima[: max(limite - len(passos), 0)]
        passos.update(dict.fromkeys(camada, passo))
        if not camada:
            break
    else:
        # a última camada não foi aberta: só para contar as ligações que saem do recorte
        _abrir(camada, passos, vistas, socias_de, participadas_de)
    dentro = [v for v in vistas if v.socia in passos and v.empresa in passos]
    fora = len(vistas) - len(dentro)
    return Grupo(
        raiz=raiz,
        empresas=tuple(
            Empresa(r, p)
            for r, p in sorted(passos.items(), key=lambda par: (par[1], par[0]))
        ),
        ligacoes=tuple(
            sorted(dentro, key=lambda v: (v.socia, v.empresa, v.qualificacao))
        ),
        completo=fora == 0,
        ligacoes_de_fora=fora,
    )


def _abrir(
    camada: list[str],
    passos: dict[str, int],
    vistas: set[Ligacao],
    socias_de: Leitura,
    participadas_de: Leitura,
) -> list[str]:
    """Lê as ligações da `camada` (guarda em `vistas`) e devolve as empresas novas, em ordem de raiz."""
    novas: set[str] = set()
    for atual in camada:
        for ligacao in _vizinhas(atual, socias_de, participadas_de):
            vistas.add(ligacao)
            outra = ligacao.empresa if ligacao.socia == atual else ligacao.socia
            if outra not in passos:
                novas.add(outra)
    return sorted(novas)


def grupo_na_vista(
    vista: Path,
    raiz: str,
    profundidade: int = PROFUNDIDADE,
    limite: int = LIMITE,
) -> Grupo | None:
    """O grupo da `raiz` no retrato vigente da vista do CNPJ; None se a vista ainda não chegou."""
    manifesto = vista_do_cnpj.manifesto(vista)
    if manifesto is None:
        return None
    grupo = montar_grupo(
        raiz,
        lambda r: vista_do_cnpj.da_raiz(vista, "vigente", "qsa", r),
        lambda r: vista_do_cnpj.participacoes_da_raiz(vista, r),
        profundidade,
        limite,
    )
    return replace(
        grupo,
        retrato=manifesto.get("mes"),
        disponivel_em=manifesto.get("disponivel_em"),
    )
