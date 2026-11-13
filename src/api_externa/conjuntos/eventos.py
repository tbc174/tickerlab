"""Os eventos de uma empresa na API externa (linha 736, PR 4): `/data/v1/companies/{cnpj}/events`, como era.

`LeitorDeEventos(porta, permitido, linhas_maximas).eventos(cnpj, como_era_em, tipos, cursor)` lista, do mais
novo ao mais velho e em tipos simples (a rota traduz as chaves na saída), o que a base sabia da empresa no dia:

- `ipe_filing`: cada documento que a companhia entregou à CVM pelo IPE (`eventos`: fato relevante,
  comunicado, assembleia, demonstração...), com o protocolo, a categoria e o tipo da CVM, o período de
  referência e o endereço do documento no sistema da CVM. O assunto não sai: é texto livre da companhia
  e pode trazer nome de pessoa (administrador eleito, diretor que renunciou);
- `auditor_change`: cada troca da firma de auditoria (`trocas_de_auditor`, montada dos FCAs), com a firma
  que saiu, a que entrou, o dia em que a troca valeu e quantos anos a anterior ficou (conta nossa).

A empresa é a pessoa jurídica: os documentos entregues com o CNPJ de qualquer estabelecimento da mesma raiz
entram. Cada campo sai no envelope, com a fonte e o dia em que ficou público; o evento publicado depois do dia
não entra (`como_era_em` na porta). A rotulagem de insolvência (`insolvencia`) nunca sai pela API externa
(inferência individual, D2.4): o documento da CVM que a anuncia sai como qualquer outro do IPE.

Pessoa não sai (ADR 0108 D2.2): o CNPJ só é servido se a rede o conhece como empresa que não é pessoa
(`empresas.e_empresa`); a troca com auditor que pode ser pessoa física a porta já esconde (`trata_como_pessoa`,
ADR 0075). A página vai até o limite de linhas do plano, ou até o `limit` do pedido quando for menor (o plano é o teto); `proximo_cursor` (opaco) traz a seguinte, sem perder
nem repetir evento quando dois têm o mesmo dia.
"""

import base64
import binascii
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base.porta import Porta
from base.porta.rede import views
from src.api_externa import nao_disponivel
from src.api_externa.conjuntos import Permitido
from src.api_externa.conjuntos.empresas import e_empresa
from src.api_externa.envelope import campo

CONJUNTO = "events"
DOCUMENTO_DO_IPE = "ipe_filing"
TROCA_DE_AUDITOR = "auditor_change"
CODIGO_DO_TIPO_INVALIDO = "invalid_event_type"
CODIGO_DO_CURSOR_INVALIDO = "invalid_cursor"


@dataclass(frozen=True)
class OrigemDoEvento:
    """De onde sai um tipo de evento: a tabela, a fonte, os campos servidos (na ordem), os que são conta
    nossa, a coluna do dia em que ficou público e as colunas que identificam o evento (o desempate)."""

    tabela: str
    fonte: str
    campos: tuple[str, ...]
    derivados: frozenset[str]
    publico_em: str
    identidade: tuple[str, ...]


ORIGENS: dict[str, OrigemDoEvento] = {
    DOCUMENTO_DO_IPE: OrigemDoEvento(
        tabela="eventos",
        fonte="cvm-hist-ipe",
        campos=("protocolo", "categoria", "tipo", "referencia", "link"),
        derivados=frozenset(),
        publico_em="publicado_em",
        identidade=("protocolo",),
    ),
    TROCA_DE_AUDITOR: OrigemDoEvento(
        tabela="trocas_de_auditor",
        fonte="cvm-hist-fca",
        campos=("efetiva_em", "anterior", "novo", "anos_com_o_anterior"),
        derivados=frozenset({"anos_com_o_anterior"}),
        publico_em="conhecido_em",
        identidade=("cnpj", "efetiva_em", "novo"),
    ),
}

# os limites que valem para a resposta inteira; os de cada tipo (`LIMITES_DO_TIPO`) só entram quando o tipo é
# servido, para a resposta não afirmar o que não consultou (linha 878)
LIMITES_GERAIS = (
    "Cada campo traz a fonte e o dia em que ficou público: nada publicado depois de known_at entra.",
    (
        "Uma empresa sem eventos não quer dizer que nada aconteceu, e nada aqui é recomendação de "
        "investimento."
    ),
    "Pessoa natural (MEI, empresário individual) não é servida.",
)

LIMITES_DO_TIPO = {
    DOCUMENTO_DO_IPE: (
        "Os documentos são os do IPE da CVM (só companhia aberta e quem entrega à CVM), de todos os "
        "estabelecimentos da mesma raiz do CNPJ; o assunto escrito pela companhia não sai, só a categoria e o "
        "tipo da CVM e o endereço do documento."
    ),
    TROCA_DE_AUDITOR: (
        "As trocas de auditor vêm dos FCAs; os anos com o auditor anterior são conta do TickerLab."
    ),
}

# os tipos pedidos que o portão não libera (o padrão de `nao_disponivel`, linhas 878 e 880)
NAO_DISPONIVEIS = "tipos_nao_disponiveis"
LIMITE_DO_TIPO_NAO_DISPONIVEL = nao_disponivel.aviso(
    NAO_DISPONIVEIS, "tipos", "a lista de eventos"
)


def limites(servidos: Iterable[str], nao_disponiveis: Sequence[str] = ()) -> list[str]:
    """Os limites da resposta: o primeiro geral, os dos tipos servidos, o aviso dos tipos pedidos que o portão
    não libera (se houver) e o resto dos gerais."""
    return nao_disponivel.limites(
        LIMITES_GERAIS,
        LIMITES_DO_TIPO,
        servidos,
        nao_disponiveis,
        LIMITE_DO_TIPO_NAO_DISPONIVEL,
    )


# os limites com todos os tipos servidos (a tela do analista os usa como texto fixo)
LIMITES = tuple(limites(ORIGENS))


class PedidoInvalido(ValueError):
    """Pedido que não dá para atender (`codigo` vai no 400): tipo de evento ou cursor que não são nossos."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


@dataclass(frozen=True)
class EventosServidos:
    """O que sai de um pedido de eventos: o corpo, as fontes usadas e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


# a ordem da lista: o dia em que ficou público (do mais novo), o tipo e a identidade do evento
Chave = tuple[int, str, str]
TAMANHO_DA_CHAVE = 3


@dataclass(frozen=True)
class _Evento:
    tipo: str
    chave: Chave
    publico_em: date
    linha: dict


def tipos_do_pedido(pedidos: list[str]) -> tuple[str, ...]:
    """Os tipos pedidos (sem nenhum, todos), na ordem de `ORIGENS`; `PedidoInvalido` se um não existe."""
    desconhecidos = set(pedidos) - set(ORIGENS)
    if desconhecidos:
        raise PedidoInvalido(CODIGO_DO_TIPO_INVALIDO)
    return tuple(t for t in ORIGENS if not pedidos or t in pedidos)


def cursor_de(chave: Chave) -> str:
    """O cursor opaco do último evento da página (a chave dele, em JSON dentro do base64)."""
    return (
        base64.urlsafe_b64encode(json.dumps(list(chave)).encode()).decode().rstrip("=")
    )


def chave_do_cursor(cursor: str) -> Chave:
    """A chave do último evento servido; `PedidoInvalido("invalid_cursor")` se o cursor não é nosso."""
    try:
        lida = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (binascii.Error, UnicodeDecodeError, ValueError, RecursionError) as erro:
        # RecursionError: o JSON forjado com milhares de colchetes aninhados
        raise PedidoInvalido(CODIGO_DO_CURSOR_INVALIDO) from erro
    if (
        not isinstance(lida, list)
        or len(lida) != TAMANHO_DA_CHAVE
        or isinstance(lida[0], bool)
        or not isinstance(lida[0], int)
        or not all(isinstance(parte, str) for parte in lida[1:])
    ):
        raise PedidoInvalido(CODIGO_DO_CURSOR_INVALIDO)
    return int(lida[0]), str(lida[1]), str(lida[2])


def _texto(valor: object) -> str | None:
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):  # type: ignore[arg-type]
        return None
    if isinstance(valor, pd.Timestamp | date):
        return pd.Timestamp(valor).date().isoformat()
    texto = str(valor).strip()
    return texto or None


def _valor(nome: str, valor: object) -> object:
    """O valor da coluna em tipo simples: dia em ISO, número como número, texto vazio como ausente."""
    if nome == "anos_com_o_anterior":
        return None if pd.isna(valor) else round(float(valor), 1)  # type: ignore[arg-type]
    return _texto(valor)


class LeitorDeEventos:
    """Lê os eventos de uma empresa de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido, linhas_maximas: int) -> None:
        self.porta = porta
        self.permitido = permitido
        self.linhas_maximas = linhas_maximas

    def _servidos(self, origem: OrigemDoEvento) -> tuple[str, ...]:
        """Os campos que o portão libera. Tabela fora da porta (sem arquivo na base) não foi consultada:
        o tipo vai em `tipos_nao_disponiveis`, e a lista vazia não quer dizer "a empresa não tem" (linha 917)."""
        if origem.tabela not in views(self.porta.con):
            return ()
        return tuple(
            nome
            for nome in origem.campos
            if self.permitido(origem.fonte, nome, nome in origem.derivados)
        )

    def _cnpjs_da_raiz(self, tabela: str, raiz: str) -> list[str]:
        """Os CNPJs, como a tabela os grava, dos estabelecimentos da raiz (a empresa é a pessoa jurídica). O
        prefixo (formatado ou só com os caracteres) corta a tabela antes da conta da raiz, que confere."""
        formatada = f"{raiz[:2]}.{raiz[2:5]}.{raiz[5:8]}"
        linhas = self.porta.con.execute(
            f'SELECT DISTINCT cnpj FROM "{tabela}" '
            "WHERE (upper(CAST(cnpj AS VARCHAR)) LIKE $formatada OR upper(CAST(cnpj AS VARCHAR)) LIKE $crua) "
            "AND left(upper(regexp_replace(CAST(cnpj AS VARCHAR), '[^0-9A-Za-z]', '', 'g')), 8) = $raiz",
            {"raiz": raiz, "formatada": f"{formatada}%", "crua": f"{raiz}%"},
        ).fetchall()
        return sorted(str(linha[0]) for linha in linhas)

    def _da_origem(
        self, tipo: str, raiz: str, como_era_em: date, servidos: tuple[str, ...]
    ) -> list[_Evento]:
        origem = ORIGENS[tipo]
        if origem.tabela not in views(self.porta.con):
            return []
        cnpjs = self._cnpjs_da_raiz(origem.tabela, raiz)
        if not cnpjs:
            return []
        colunas = list(
            dict.fromkeys([*origem.campos, origem.publico_em, *origem.identidade])
        )
        tabela = self.porta.ler(
            origem.tabela,
            como_era_em=como_era_em,
            filtros={"cnpj": cnpjs},
            colunas=colunas,
        )
        eventos = []
        for linha in tabela.to_dict("records"):
            publico_em = pd.Timestamp(linha[origem.publico_em]).date()
            identidade = "|".join(_texto(linha[c]) or "" for c in origem.identidade)
            valores = {nome: _valor(nome, linha[nome]) for nome in servidos}
            servida = {
                nome: campo(
                    valor, fonte=origem.fonte, publico_em=publico_em, visto_em=None
                )
                for nome, valor in valores.items()
                if valor is not None
            }
            if servida:
                chave = (-publico_em.toordinal(), tipo, identidade)
                eventos.append(
                    _Evento(
                        tipo, chave, publico_em, {"tipo_de_evento": tipo, **servida}
                    )
                )
        return eventos

    def eventos(
        self,
        cnpj: str,
        como_era_em: date,
        tipos: tuple[str, ...] = tuple(ORIGENS),
        cursor: str | None = None,
    ) -> EventosServidos | None:
        """Os eventos do CNPJ como eram em `como_era_em`, do mais novo ao mais velho, depois do `cursor`, só
        com o que o portão libera; None se o CNPJ não é de empresa ou se o portão não libera nenhum campo
        dos tipos pedidos. O tipo pedido que o portão não libera não some em silêncio: vai em
        `tipos_nao_disponiveis` (linha 878). A lista vazia com essa lista vazia quer dizer que todos os tipos
        pedidos foram consultados e a base não tem evento da empresa."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        depois_de = None if cursor is None else chave_do_cursor(cursor)
        servidos = {tipo: self._servidos(ORIGENS[tipo]) for tipo in tipos}
        if not any(servidos.values()):
            return None
        nao_disponiveis = nao_disponivel.nao_disponiveis(servidos)
        if not e_empresa(self.porta, normal):
            return None
        raiz = normal[: cnpj_.TAMANHO_DA_RAIZ]
        todos = sorted(
            (
                evento
                for tipo, campos in servidos.items()
                if campos
                for evento in self._da_origem(tipo, raiz, como_era_em, campos)
            ),
            key=lambda e: e.chave,
        )
        if depois_de is not None:
            todos = [e for e in todos if e.chave > depois_de]
        cabem = max(self.linhas_maximas, 1)
        pagina, cortada = todos[:cabem], len(todos) > cabem
        corpo: dict[str, object] = {
            "cnpj": normal,
            "como_era_em": como_era_em.isoformat(),
            "eventos": [e.linha for e in pagina],
            "cortada": cortada,
            "proximo_cursor": cursor_de(pagina[-1].chave) if cortada else None,
            NAO_DISPONIVEIS: nao_disponiveis,
            "limites": limites(
                (tipo for tipo, campos in servidos.items() if campos), nao_disponiveis
            ),
        }
        fontes = {ORIGENS[e.tipo].fonte for e in pagina}
        return EventosServidos(corpo=corpo, fontes=fontes, linhas=len(pagina))
