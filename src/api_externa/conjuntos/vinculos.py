"""Os vínculos de uma empresa na API externa (linha 736, PR 5): `/data/v1/companies/{cnpj}/links`, como era.

`LeitorDeVinculos(porta, permitido, linhas_maximas).vinculos(cnpj, como_era_em, profundidade, tipos)` anda pela
rede de entidades do TickerLab (`Porta.rede`, ADR 0077) a partir da empresa, de 1 a 3 saltos, e lista em tipos
simples (a rota traduz as chaves na saída) cada ligação que valia no dia:

- `subsidiary_of`, `affiliate_of` e `investee_of`: a sociedade controlada, coligada ou só participada da outra,
  com a participação no capital, como o FRE informou (`controladas`, fonte `cvm-hist-fre`);
- `audits`: a firma de auditoria que auditava a companhia, pelo FCA (`auditores`, fonte `cvm-hist-fca`).

As outras ligações da rede (o fundo que detém o papel, quem emite o valor mobiliário, o conglomerado do BC e a
série do regulador) não saem por aqui. Cada ponta sai com o id da rede, a raiz do CNPJ e o nome, quando o nome
veio de uma fonte que pode sair (o cadastro, o FRE ou o FCA da CVM); cada campo sai no envelope, com a fonte e o
dia em que ficou público.

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
from src.api_externa.conjuntos.empresas import e_empresa
from src.api_externa.envelope import campo

CONJUNTO = "links"
CODIGO_DA_PROFUNDIDADE_INVALIDA = "invalid_depth"
CODIGO_DO_TIPO_INVALIDO = "invalid_link_type"
PROFUNDIDADE_MAXIMA = 3
FRE, FCA, CADASTRO = "cvm-hist-fre", "cvm-hist-fca", "cvm-cadastros"
SISTEMA_DA_RAIZ = "cnpj_raiz"


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
# quem deu o nome da entidade (`base/rede/montar.py::PRIORIDADE_DO_NOME`, da mais confiável à menos) e a fonte
# do portão de cada uma; o nome que veio de outra (GLEIF, IF.data, carteira de fundo...) não sai
PRIORIDADE_DO_NOME = (
    "cvm-cadastro",
    "cvm-fundos",
    "bcb-ifdata",
    "gleif",
    "cvm-fre",
    "cvm-fundos-participantes",
    "conferida-emissores",
    "empresa_serie",
    "cvm-fca",
    "cvm-fca-auditores",
    "cvm-cda",
)
FONTE_DO_NOME = {
    "cvm-cadastro": CADASTRO,
    "cvm-fre": FRE,
    "cvm-fca": FCA,
    "cvm-fca-auditores": FCA,
}

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


def fonte_do_nome(fontes: object) -> str | None:
    """A fonte do portão do nome da entidade: a mais confiável entre as dela, se for uma que pode sair."""
    if not isinstance(fontes, str):
        return None
    dela = {f.strip() for f in fontes.split(",")}
    for fonte in PRIORIDADE_DO_NOME:
        if fonte in dela:
            return FONTE_DO_NOME.get(fonte)
    return None


@dataclass(frozen=True)
class _Ponta:
    """Uma entidade da rede que pode sair como ponta (empresa já pública no dia, que não é pessoa)."""

    id_entidade: str
    raiz: str | None
    nome: str | None
    fonte_do_nome: str | None
    publico_em: date


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
            nome = linha.get("nome")
            pontas[str(linha["id_entidade"])] = _Ponta(
                str(linha["id_entidade"]),
                raizes.get(linha["id_entidade"]),
                nome if isinstance(nome, str) and nome.strip() else None,
                fonte_do_nome(linha.get("fontes")),
                publico_em,
            )
        return pontas

    def _ponta(self, ponta: _Ponta, fontes: set[str]) -> dict[str, object]:
        saida: dict[str, object] = {
            "id_na_rede": ponta.id_entidade,
            "raiz_do_cnpj": ponta.raiz,
        }
        fonte = ponta.fonte_do_nome
        if ponta.nome and fonte and self.permitido(fonte, "nome", False):
            saida["nome"] = campo(
                ponta.nome, fonte=fonte, publico_em=ponta.publico_em, visto_em=None
            )
            fontes.add(fonte)
        return saida

    def _vinculo(
        self,
        linha: dict,
        servidos: tuple[str, ...],
        pontas: dict[str, _Ponta],
        fontes: set[str],
    ) -> dict[str, object]:
        tipo = TIPOS[linha["tipo"]]
        publico_em = _dia(linha["publico_em"])
        vinculo: dict[str, object] = {
            "salto": int(linha["salto"]),
            "de": self._ponta(pontas[linha["de"]], fontes),
            "para": self._ponta(pontas[linha["para"]], fontes),
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
        todos = self._da_rede(normal, como_era_em, profundidade, servidos)
        cabem = max(self.linhas_maximas, 1)
        pagina, cortada = todos[:cabem], len(todos) > cabem
        corpo: dict[str, object] = {
            "cnpj": normal,
            "como_era_em": como_era_em.isoformat(),
            "profundidade": profundidade,
            "vinculos": [v for v, _ in pagina],
            "cortada": cortada,
            "limites": list(LIMITES),
        }
        fontes = set().union(*(f for _, f in pagina)) if pagina else set()
        return VinculosServidos(corpo=corpo, fontes=fontes, linhas=len(pagina))

    def _da_rede(
        self,
        cnpj: str,
        como_era_em: date,
        profundidade: int,
        servidos: dict[str, tuple[str, ...]],
    ) -> list[tuple[dict[str, object], set[str]]]:
        """Cada vínculo servido, na ordem (salto, tipo, pontas, início), com as fontes que ele usou."""
        if "ligacoes" not in views(self.porta.con):
            return []
        try:
            rede = self.porta.rede(
                cnpj,
                tipos=list(servidos),
                como_era_em=como_era_em,
                profundidade=profundidade,
            )
        except LookupError:  # a empresa ainda não estava na rede no dia
            return []
        pontas = self._pontas(rede.entidades, rede.identificadores)
        ligacoes = rede.ligacoes
        if ligacoes.empty:
            return []
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
        ligacoes = ligacoes.assign(
            _ordem=ligacoes["tipo"].map(ordem.index)
        ).sort_values(["salto", "_ordem", "de", "para", "aconteceu_em"], kind="stable")
        saida = []
        for linha in ligacoes.to_dict("records"):
            fontes: set[str] = set()
            saida.append(
                (self._vinculo(linha, servidos[linha["tipo"]], pontas, fontes), fontes)
            )
        return saida
