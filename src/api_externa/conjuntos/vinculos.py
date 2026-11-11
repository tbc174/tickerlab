"""Os vínculos de uma empresa na API externa (linha 736, PR 5): `/data/v1/companies/{cnpj}/links`, como era.

`LeitorDeVinculos(porta, permitido, linhas_maximas).vinculos(cnpj, como_era_em, profundidade, tipos)` anda pela
rede de entidades do TickerLab (`Porta.rede`, ADR 0077) a partir da empresa, de 1 a 3 saltos, e lista em tipos
simples (a rota traduz as chaves na saída) cada ligação que valia no dia:

- `subsidiary_of`, `affiliate_of` e `investee_of`: a sociedade controlada, coligada ou só participada da outra,
  com a participação no capital, como o FRE informou (`controladas`, fonte `cvm-hist-fre`);
- `audits`: a firma de auditoria que auditava a companhia, pelo FCA (`auditores`, fonte `cvm-hist-fca`).

As outras ligações da rede (o fundo que detém o papel, quem emite o valor mobiliário, o conglomerado do BC e a
série do regulador) não saem por aqui. Cada ponta sai com o id da rede, a raiz do CNPJ e a razão social que valia
no dia, do histórico datado da Receita (`cnpj_empresas_historico`, o mesmo de `/companies`); o nome guardado na
rede é o de hoje e não sai (num dia do passado, ele seria um dado do futuro). Cada campo sai no envelope, com a
fonte e o dia em que ficou público.

Sem olhar o futuro: a porta só devolve a ligação já pública no dia e esconde o fim que só se soube depois (D5:
a ligação que acabou depois do dia ainda aparece no dia). Pessoa não sai (ADR 0108 D2.2): o CNPJ pedido só é
servido se a rede o conhece como empresa que não é pessoa (`empresas.e_empresa`); a porta já tira toda ponta de
pessoa natural (vista publicada, ADR 0075), e aqui sai também a ligação com a ponta que a rede trata como
pessoa (MEI, empresário individual, natureza não informada) ou que ainda não era pública no dia.
"""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base.porta import Porta
from base.porta.rede import views
from src.api_externa.conjuntos import Permitido
from src.api_externa.conjuntos.empresas import (
    CONSTA,
    MES,
    PUBLICADO_EM,
    RAIZ,
    e_empresa,
)
from src.api_externa.conjuntos.empresas import FONTE as RECEITA
from src.api_externa.envelope import campo

CONJUNTO = "links"
CODIGO_DA_PROFUNDIDADE_INVALIDA = "invalid_depth"
CODIGO_DO_TIPO_INVALIDO = "invalid_link_type"
PROFUNDIDADE_MAXIMA = 3
FRE, FCA = "cvm-hist-fre", "cvm-hist-fca"
SISTEMA_DA_RAIZ = "cnpj_raiz"
HISTORICO_DOS_NOMES = "cnpj_empresas_historico"
NOME = "razao_social"


@dataclass(frozen=True)
class TipoDeVinculo:
    """Um tipo de ligação da rede que sai: o nome de fora, a fonte do portão, o nome da fonte gravado na
    `ligacoes` e os campos da ligação servidos (na ordem)."""

    de_fora: str
    fonte: str
    fonte_na_rede: str
    campos: tuple[str, ...]


_DO_FRE = ("tipo", "participacao", "aconteceu_em", "ate")
TIPOS: dict[str, TipoDeVinculo] = {
    "controlada_de": TipoDeVinculo("subsidiary_of", FRE, "cvm-fre", _DO_FRE),
    "coligada_de": TipoDeVinculo("affiliate_of", FRE, "cvm-fre", _DO_FRE),
    "participada_de": TipoDeVinculo("investee_of", FRE, "cvm-fre", _DO_FRE),
    "audita": TipoDeVinculo("audits", FCA, "cvm-fca", ("tipo", "aconteceu_em", "ate")),
}
TIPO_PELO_NOME_DE_FORA = {tipo.de_fora: nome for nome, tipo in TIPOS.items()}
# a chave da resposta quando a coluna tem outro sentido em outro conjunto ("participacao" é a do mercado)
CHAVE_NA_RESPOSTA = {"participacao": "participacao_no_capital"}
LIMITES = (
    (
        "Cada campo traz a fonte e o dia em que ficou público: nada publicado depois de known_at entra, e a "
        "ligação que só se soube ter acabado depois do dia ainda aparece."
    ),
    (
        "Controle, coligação e participação vêm do FRE (só de companhia aberta, uma vez por ano, e só as "
        "sociedades com CNPJ); a auditoria vem do FCA. Fundos, sócios e administradores não saem por aqui."
    ),
    (
        "O tipo (controlada, coligada) e a participação no capital são os que a companhia escreveu no FRE, sem "
        "correção nossa: um número estranho (uma controlada com 0,12% do capital) vem da própria entrega."
    ),
    (
        "Uma empresa sem vínculos não quer dizer que ela não tenha grupo: quer dizer que nenhuma fonte servida "
        "mostra um no dia. Nada aqui é recomendação de investimento."
    ),
    (
        "O nome de cada ponta é a razão social que valia no dia, do histórico da Receita (que começa em 05/2023): "
        "antes dele, ou numa ponta sem CNPJ, a ponta sai sem nome."
    ),
    "Pessoa natural (MEI, empresário individual, sócio pessoa física) não é servida.",
)


class PedidoInvalido(ValueError):
    """Pedido que não dá para atender (`codigo` vai no 400): profundidade ou tipo de vínculo que não são nossos."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


@dataclass(frozen=True)
class VinculosServidos:
    """O que sai de um pedido de vínculos: o corpo, as fontes usadas e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


def profundidade_do_pedido(profundidade: int) -> int:
    """A profundidade pedida, de 1 a `PROFUNDIDADE_MAXIMA`; `PedidoInvalido` fora disso."""
    if not 1 <= profundidade <= PROFUNDIDADE_MAXIMA:
        raise PedidoInvalido(CODIGO_DA_PROFUNDIDADE_INVALIDA)
    return profundidade


def tipos_do_pedido(pedidos: list[str]) -> tuple[str, ...]:
    """Os tipos da rede pedidos pelo nome de fora (sem nenhum, todos), na ordem de `TIPOS`."""
    desconhecidos = set(pedidos) - set(TIPO_PELO_NOME_DE_FORA)
    if desconhecidos:
        raise PedidoInvalido(CODIGO_DO_TIPO_INVALIDO)
    pedidos_na_rede = {TIPO_PELO_NOME_DE_FORA[p] for p in pedidos}
    return tuple(t for t in TIPOS if not pedidos or t in pedidos_na_rede)


def _sim(valor: object) -> bool:
    return bool(valor) and not pd.isna(valor)  # type: ignore[arg-type]


def _dia(valor: object) -> date | None:
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    return pd.Timestamp(valor).date()  # type: ignore[arg-type]


def _numero(valor: object) -> float | None:
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    return float(valor)  # type: ignore[arg-type]


@dataclass(frozen=True)
class _Ponta:
    """Uma entidade da rede que pode sair como ponta (empresa já pública no dia, que não é pessoa)."""

    id_entidade: str
    raiz: str | None


class LeitorDeVinculos:
    """Lê os vínculos de uma empresa de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido, linhas_maximas: int) -> None:
        self.porta = porta
        self.permitido = permitido
        self.linhas_maximas = linhas_maximas

    def _servidos(self, tipo: TipoDeVinculo) -> tuple[str, ...]:
        """Os campos da ligação que o portão libera; sem o `tipo`, a ligação não sai."""
        servidos = tuple(c for c in tipo.campos if self.permitido(tipo.fonte, c, False))
        return servidos if "tipo" in servidos else ()

    @staticmethod
    def _pontas(
        entidades: pd.DataFrame, identificadores: pd.DataFrame
    ) -> dict[str, _Ponta]:
        raizes = (
            identificadores[identificadores["sistema"] == SISTEMA_DA_RAIZ]
            .drop_duplicates("id_entidade")
            .set_index("id_entidade")["valor"]
            if not identificadores.empty
            else pd.Series(dtype=object)
        )
        pontas = {}
        for linha in entidades.to_dict("records"):
            publico_em = _dia(linha.get("publico_em"))
            # sem os dados no dia (só ficou pública depois por outra fonte), tratada como pessoa ou sem saber se
            # é pessoa (falha fechada): não sai
            pessoa = linha.get("trata_como_pessoa")
            if (
                publico_em is None
                or _sim(linha.get("mei"))
                or pd.isna(pessoa)
                or _sim(pessoa)
            ):  # type: ignore[arg-type]
                continue
            pontas[str(linha["id_entidade"])] = _Ponta(
                str(linha["id_entidade"]), raizes.get(linha["id_entidade"])
            )
        return pontas

    def _nomes(
        self, raizes: set[str], como_era_em: date
    ) -> dict[str, tuple[str, date]]:
        """A razão social de cada raiz no retrato mais novo já público no dia, com o dia em que ele ficou
        público; a raiz sem retrato público no dia, ou que tinha saído do arquivo, fica de fora."""
        if (
            not raizes
            or not self.permitido(RECEITA, NOME, False)
            or HISTORICO_DOS_NOMES not in views(self.porta.con)
        ):
            return {}
        versoes = self.porta.ler(
            HISTORICO_DOS_NOMES,
            como_era_em=como_era_em,
            filtros={RAIZ: sorted(raizes)},
            colunas=[RAIZ, NOME, MES, CONSTA, PUBLICADO_EM],
        )
        if versoes.empty:
            return {}
        ultimas = versoes.sort_values([RAIZ, MES, PUBLICADO_EM]).groupby(RAIZ).tail(1)
        nomes = {}
        for linha in ultimas.to_dict("records"):
            nome = linha[NOME]
            if _sim(linha[CONSTA]) and isinstance(nome, str) and nome.strip():
                nomes[str(linha[RAIZ])] = (
                    nome,
                    pd.Timestamp(linha[PUBLICADO_EM]).date(),
                )
        return nomes

    @staticmethod
    def _ponta(
        ponta: _Ponta, nomes: dict[str, tuple[str, date]], fontes: set[str]
    ) -> dict[str, object]:
        saida: dict[str, object] = {
            "id_na_rede": ponta.id_entidade,
            "raiz_do_cnpj": ponta.raiz,
        }
        if ponta.raiz in nomes:
            nome, publico_em = nomes[ponta.raiz]
            saida[NOME] = campo(
                nome, fonte=RECEITA, publico_em=publico_em, visto_em=None
            )
            fontes.add(RECEITA)
        return saida

    def _vinculo(
        self,
        linha: dict,
        servidos: tuple[str, ...],
        pontas: dict[str, _Ponta],
        nomes: dict[str, tuple[str, date]],
        fontes: set[str],
    ) -> dict[str, object]:
        tipo = TIPOS[linha["tipo"]]
        publico_em = _dia(linha["publico_em"])
        vinculo: dict[str, object] = {
            "salto": int(linha["salto"]),
            "de": self._ponta(pontas[linha["de"]], nomes, fontes),
            "para": self._ponta(pontas[linha["para"]], nomes, fontes),
        }
        # o tipo sai no envelope com o nome de fora (`subsidiary_of`...): é ele que leva a fonte e o dia público
        valores = {
            "tipo": tipo.de_fora,
            "participacao": _numero(linha.get("participacao")),
            "aconteceu_em": _dia(linha.get("aconteceu_em")),
            "ate": _dia(linha.get("ate")),
        }
        for nome in servidos:
            valor = valores.get(nome)
            if valor is not None:
                chave = CHAVE_NA_RESPOSTA.get(nome, nome)
                saida = valor.isoformat() if isinstance(valor, date) else valor
                vinculo[chave] = campo(
                    saida, fonte=tipo.fonte, publico_em=publico_em, visto_em=None
                )
        fontes.add(tipo.fonte)
        return vinculo

    def vinculos(
        self,
        cnpj: str,
        como_era_em: date,
        profundidade: int = 1,
        tipos: tuple[str, ...] = tuple(TIPOS),
    ) -> VinculosServidos | None:
        """Os vínculos do CNPJ como eram em `como_era_em`, até `profundidade` saltos, só com o que o portão
        libera; None se o CNPJ não é de empresa ou se o portão não libera nenhum dos tipos pedidos. Empresa
        sem vínculo no dia sai com a lista vazia."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        profundidade_do_pedido(profundidade)
        servidos = {t: self._servidos(TIPOS[t]) for t in tipos}
        servidos = {t: campos for t, campos in servidos.items() if campos}
        if not servidos:
            return None
        if not e_empresa(self.porta, normal):
            return None
        ligacoes, pontas = self._da_rede(normal, como_era_em, profundidade, servidos)
        # corta antes de montar: com depth=3 e uma firma de auditoria no meio, a rede tem milhares de ligações
        cabem = max(self.linhas_maximas, 1)
        cortada = len(ligacoes) > cabem
        pagina = ligacoes.head(cabem).to_dict("records")
        raizes = {pontas[linha[p]].raiz for linha in pagina for p in ("de", "para")}
        nomes = self._nomes({r for r in raizes if r}, como_era_em)
        fontes: set[str] = set()
        lista = [
            self._vinculo(linha, servidos[linha["tipo"]], pontas, nomes, fontes)
            for linha in pagina
        ]
        corpo: dict[str, object] = {
            "cnpj": normal,
            "como_era_em": como_era_em.isoformat(),
            "profundidade": profundidade,
            "vinculos": lista,
            "cortada": cortada,
            "limites": list(LIMITES),
        }
        return VinculosServidos(corpo=corpo, fontes=fontes, linhas=len(lista))

    def _da_rede(
        self,
        cnpj: str,
        como_era_em: date,
        profundidade: int,
        servidos: dict[str, tuple[str, ...]],
    ) -> tuple[pd.DataFrame, dict[str, _Ponta]]:
        """As ligações que podem sair, na ordem (salto, tipo, pontas, início), e as pontas que podem sair."""
        if "ligacoes" not in views(self.porta.con):
            return pd.DataFrame(), {}
        try:
            rede = self.porta.rede(
                cnpj,
                tipos=list(servidos),
                como_era_em=como_era_em,
                profundidade=profundidade,
            )
        except LookupError:  # a empresa ainda não estava na rede no dia
            return pd.DataFrame(), {}
        pontas = self._pontas(rede.entidades, rede.identificadores)
        ligacoes = rede.ligacoes
        if ligacoes.empty:
            return pd.DataFrame(), {}
        esperada = ligacoes["tipo"].map(
            lambda t: TIPOS[t].fonte_na_rede if t in TIPOS else None
        )
        ligacoes = ligacoes[
            ligacoes["tipo"].isin(list(servidos))
            & (ligacoes["fonte"] == esperada)
            & ligacoes["de"].isin(list(pontas))
            & ligacoes["para"].isin(list(pontas))
        ]
        ordem = list(TIPOS)
        ligacoes = ligacoes.assign(_ordem=ligacoes["tipo"].map(ordem.index))
        # o desempate vai até as colunas servidas: a página cortada sai igual em toda execução
        chave = [
            "salto",
            "_ordem",
            "de",
            "para",
            "aconteceu_em",
            "ate",
            "participacao",
            "publico_em",
        ]
        ligacoes = ligacoes.sort_values(
            [c for c in chave if c in ligacoes.columns], kind="stable"
        )
        return ligacoes, pontas
