"""Os vínculos de uma empresa na API externa (linha 736, PR 5): `/data/v1/companies/{cnpj}/links`, como era.

`LeitorDeVinculos(porta, permitido, linhas_maximas).vinculos(cnpj, como_era_em, profundidade, tipos)` anda pela
rede de entidades do TickerLab (`Porta.rede`, ADR 0077) a partir da empresa, de 1 a 3 saltos, e lista em tipos
simples (a rota traduz as chaves na saída) cada ligação que valia no dia:

- `subsidiary_of`, `affiliate_of` e `investee_of`: a sociedade controlada, coligada ou só participada da outra,
  com a participação no capital, como o FRE informou (`controladas`, fonte `cvm-hist-fre`);
- `audits`: a firma de auditoria que auditava a companhia, pelo FCA (`auditores`, fonte `cvm-hist-fca`).

As outras ligações da rede (o fundo que detém o papel, quem emite o valor mobiliário, o conglomerado do BC e a
série do regulador) não saem por aqui. Cada ponta sai com o id da rede, a raiz do CNPJ e a razão social do
retrato mensal mais novo da lista sem pessoa da Receita já público no dia (`cnpj_empresas_pj`, a mesma de
`/companies`), com o mês dele (linha 867): é o nome daquele retrato, não o de cada dia, e a raiz que não está nele
sai sem nome, mesmo que esteja num retrato mais velho. O histórico datado (`cnpj_empresas_historico`) não é lido:
tem pessoa e não vai à base da API. O nome guardado na rede é o de hoje e não sai (num dia do passado, ele seria um
dado do futuro). Cada campo sai no envelope, com a fonte e o dia em que ficou público.

Sem olhar o futuro: a porta só devolve a ligação já pública no dia e esconde o fim que só se soube depois (D5:
a ligação que acabou depois do dia ainda aparece no dia). Pessoa não sai (ADR 0108 D2.2): o CNPJ pedido só é
servido se a rede o conhece como empresa que não é pessoa (`empresas.e_empresa`); a porta já tira toda ponta de
pessoa natural (vista publicada, ADR 0075), e aqui sai também a ligação com a ponta que a rede trata como
pessoa (MEI, empresário individual, natureza não informada) ou que ainda não era pública no dia.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base.porta import Porta
from base.porta.rede import views
from src.api_externa import nao_disponivel
from src.api_externa.conjuntos import Permitido
from src.api_externa.conjuntos.empresas import FONTE as RECEITA
from src.api_externa.conjuntos.empresas import (
    MES,
    PUBLICADO_EM,
    RETRATO_DO_CADASTRO,
    e_empresa,
    retratos_de_empresa,
)
from src.api_externa.envelope import campo

CONJUNTO = "links"
CODIGO_DA_PROFUNDIDADE_INVALIDA = "invalid_depth"
CODIGO_DO_TIPO_INVALIDO = "invalid_link_type"
PROFUNDIDADE_MAXIMA = 3
FRE, FCA = "cvm-hist-fre", "cvm-hist-fca"
SISTEMA_DA_RAIZ = "cnpj_raiz"
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
# os limites que valem para a resposta inteira; os de cada fonte (`LIMITES_DA_FONTE`) só entram quando algum
# tipo dela é servido, para a resposta não afirmar o que não consultou (linha 880)
LIMITES_GERAIS = (
    (
        "Cada campo traz a fonte e o dia em que ficou público: nada publicado depois de known_at entra, e a "
        "ligação que só se soube ter acabado depois do dia ainda aparece."
    ),
    "Fundos, sócios e administradores não saem por aqui.",
    (
        "Uma empresa sem vínculos não quer dizer que ela não tenha grupo: quer dizer que nenhuma fonte servida "
        "mostra um no dia. Nada aqui é recomendação de investimento."
    ),
    (
        "O nome de cada ponta é a razão social do retrato mensal mais novo da Receita já público no dia, com o "
        "mês dele (mes_do_retrato_do_cadastro): é o nome daquele retrato, não necessariamente o que valia no dia "
        "exato. Antes do primeiro retrato, numa ponta sem CNPJ ou fora do retrato, a ponta sai sem nome."
    ),
    "Pessoa natural (MEI, empresário individual, sócio pessoa física) não é servida.",
)

LIMITES_DA_FONTE = {
    FRE: (
        "Controle, coligação e participação vêm do FRE (só de companhia aberta, uma vez por ano, e só as "
        "sociedades com CNPJ). O tipo (controlada, coligada) e a participação no capital são os que a "
        "companhia escreveu no FRE, sem correção nossa: um número estranho (uma controlada com 0,12% do "
        "capital) vem da própria entrega."
    ),
    FCA: "A auditoria vem do FCA.",
}

# os tipos pedidos que o portão não libera, com o nome de fora (o padrão de `nao_disponivel`, linha 880)
NAO_DISPONIVEIS = "tipos_de_vinculo_nao_disponiveis"
LIMITE_DO_TIPO_NAO_DISPONIVEL = nao_disponivel.aviso(
    NAO_DISPONIVEIS, "tipos", "a lista de vínculos"
)


def limites(
    tipos_servidos: Iterable[str], nao_disponiveis: Sequence[str] = ()
) -> list[str]:
    """Os limites da resposta: o primeiro geral, os das fontes dos tipos servidos, o aviso dos tipos pedidos
    que o portão não libera (se houver) e o resto dos gerais."""
    fontes = (TIPOS[tipo].fonte for tipo in tipos_servidos)
    return nao_disponivel.limites(
        LIMITES_GERAIS,
        LIMITES_DA_FONTE,
        fontes,
        nao_disponiveis,
        LIMITE_DO_TIPO_NAO_DISPONIVEL,
    )


# os limites com todos os tipos servidos (a tela do analista os usa como texto fixo)
LIMITES = tuple(limites(TIPOS))


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
        """Os campos da ligação que o portão libera; sem o `tipo`, a ligação não sai. Sem a tabela de ligações
        na base nada foi consultado: o tipo vai em `tipos_de_vinculo_nao_disponiveis` (linha 917)."""
        if "ligacoes" not in views(self.porta.con):
            return ()
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

    def _nomes(self, raizes: set[str], como_era_em: date) -> dict[str, dict[str, dict]]:
        """Por raiz, a razão social (e o mês do retrato) do retrato mais novo de `cnpj_empresas_pj` já público no
        dia, cada um no envelope; a raiz fora desse retrato, repetida nele ou sem natureza de empresa fica de
        fora (na dúvida, não), e sem o nome liberado nada sai."""
        if not raizes or not self.permitido(RECEITA, NOME, False):
            return {}
        servem_o_mes = self.permitido(RECEITA, RETRATO_DO_CADASTRO, False)
        nomes = {}
        for raiz, linha in retratos_de_empresa(
            self.porta, raizes, como_era_em, (NOME,)
        ).items():
            nome = linha[NOME]
            if not isinstance(nome, str) or not nome.strip():
                continue
            publico_em = pd.Timestamp(linha[PUBLICADO_EM]).date()
            campos = {
                NOME: campo(nome, fonte=RECEITA, publico_em=publico_em, visto_em=None)
            }
            if servem_o_mes:
                campos[RETRATO_DO_CADASTRO] = campo(
                    str(linha[MES]), fonte=RECEITA, publico_em=publico_em, visto_em=None
                )
            nomes[raiz] = campos
        return nomes

    @staticmethod
    def _ponta(
        ponta: _Ponta, nomes: dict[str, dict[str, dict]], fontes: set[str]
    ) -> dict[str, object]:
        saida: dict[str, object] = {
            "id_na_rede": ponta.id_entidade,
            "raiz_do_cnpj": ponta.raiz,
        }
        if ponta.raiz in nomes:
            saida.update(nomes[ponta.raiz])
            fontes.add(RECEITA)
        return saida

    def _vinculo(
        self,
        linha: dict,
        servidos: tuple[str, ...],
        pontas: dict[str, _Ponta],
        nomes: dict[str, dict[str, dict]],
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
        libera; None se o CNPJ não é de empresa ou se o portão não libera nenhum dos tipos pedidos. O tipo pedido
        que o portão não libera não some em silêncio: vai, com o nome de fora, em
        `tipos_de_vinculo_nao_disponiveis` (linha 880), e os limites não falam da fonte dele. Empresa sem
        vínculo no dia sai com a lista vazia; com essa lista também vazia, todos os tipos pedidos foram
        consultados."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        profundidade_do_pedido(profundidade)
        pedidos = {t: self._servidos(TIPOS[t]) for t in tipos}
        servidos = {t: campos for t, campos in pedidos.items() if campos}
        if not servidos:
            return None
        nao_disponiveis = [
            TIPOS[t].de_fora for t in nao_disponivel.nao_disponiveis(pedidos)
        ]
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
            NAO_DISPONIVEIS: nao_disponiveis,
            "limites": limites(servidos, nao_disponiveis),
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
