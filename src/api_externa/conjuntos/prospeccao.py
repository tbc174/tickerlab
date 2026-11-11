"""A busca de empresas na API externa (linha 794): `GET /data/v1/companies` com filtros, só pessoa jurídica.

`LeitorDeProspeccao(porta, permitido, linhas_maximas).buscar(busca, como_era_em)` devolve, em tipos simples e
com as chaves em português (a rota traduz na saída), uma página de estabelecimentos de empresas (CNPJ,
razão social, natureza jurídica, porte, atividade, abertura, município, UF, situação, matriz), cada campo com
fonte e o dia em que ficou público. Lê só as duas tabelas do acervo montadas sem pessoa (linha 584,
`cnpj_estabelecimentos_pj` e `cnpj_empresas_pj`): empresário individual (213-5), grupo 4 e MEI nem existem
nelas, e a vista não tem endereço fino, contato, sócio nem nome fantasia.

**Como era:** as duas tabelas são retratos mensais inteiros. A busca usa o retrato mais novo que já era
público em `como_era_em` (a porta vale o mês pelo último dia dele) e junta as duas tabelas no mesmo mês. O
CNPJ que saiu do arquivo naquele mês não aparece.

**Busca:** filtros por CNAE (prefixo de 2 a 7 dígitos), UF, município (código da Receita ou nome), porte,
natureza jurídica (prefixo), situação cadastral (padrão ativa), abertura (antes e depois de uma data) e
matriz, capital social (mínimo e máximo) e número mínimo de estabelecimentos ativos. Pelo menos um filtro
além da situação: ninguém baixa a base inteira. Ordem por CNPJ (padrão), por capital social ou por número de
estabelecimentos, crescente ou decrescente (`-` na frente), sempre com o CNPJ como desempate; cursor opaco
(o último CNPJ da página, e o valor da ordenação quando ela não é por CNPJ) e `limite` (padrão 50, no máximo 100 e o que o plano deixa por resposta).
Sem total: contar custaria uma varredura a mais por chamada. A consulta lê só as colunas pedidas dos
arquivos Parquet (formato em colunas), com os filtros empurrados para a leitura.

**Fora, por desenho (decisão D2.4 do portão):** a API externa não busca por nome. A busca por trecho da razão
social precisa de decisão própria sobre a regra (nome de empresa que carrega nome de pessoa) e fica para um
PR depois, se a Diretoria autorizar; entra como mais um filtro deste mesmo leitor.
"""

import base64
import binascii
import json
import math
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base.porta import Porta
from base.porta.duckdb import condicao_como_era, dia_de, nome_da_view
from base.receita_codigos import codigos_do_municipio
from src.api_externa.conjuntos import Permitido
from src.api_externa.envelope import campo

CONJUNTO = "prospecting"
FONTE = "rfb-cnpj"
ESTABELECIMENTOS = "cnpj_estabelecimentos_pj"
EMPRESAS = "cnpj_empresas_pj"
LIMITE_PADRAO = 50
LIMITE_MAXIMO = 100
# o porte como a Receita o grava na base -> como a API o diz (a Receita não diz "grande": 05 é "demais")
PORTES_DE_FORA = {
    "micro": "micro",
    "pequeno": "small",
    "demais": "other",
    "nao_informado": "not_informed",
}
PORTES_DA_BASE = {fora: base for base, fora in PORTES_DE_FORA.items()}
SITUACOES = {
    "ativa": "02",
    "baixada": "08",
    "inapta": "04",
    "suspensa": "03",
    "nula": "01",
}
CAMPOS_DO_ESTABELECIMENTO = (
    "situacao_cadastral", "data_inicio_atividade", "cnae_principal", "uf", "municipio", "matriz",
)  # fmt: skip
CAMPOS_DA_EMPRESA = (
    "razao_social", "natureza_juridica", "porte", "capital_social", "n_estabelecimentos",
)  # fmt: skip
# a ordem pedida (`sort`) -> a coluna da base; o `-` na frente é decrescente
ORDENS = {"capital": "capital_social", "branches": "n_estabelecimentos"}
CAPITAL_MAXIMO = (
    1e15  # acima disso o número não é capital: recusa em vez de comparar lixo
)
CAMPOS = (*CAMPOS_DA_EMPRESA, *CAMPOS_DO_ESTABELECIMENTO)
PUBLICADO_EM = "publico_em"
MES = "mes_do_retrato"
TAMANHO_DA_UF = 2
TAMANHO_DO_CNPJ = 14
TAMANHO_DO_MUNICIPIO = 4
CNAE_MINIMO, CNAE_MAXIMO = 2, 7
NATUREZA_MAXIMA = 4
FILIAIS_MAXIMAS = 1_000_000
VALORES_MAXIMOS = 50  # por filtro: a lista do pedido não monta SQL sem fim


class FiltroInvalido(ValueError):
    """Um filtro fora do vocabulário ou da forma: a rota responde 400 com o `codigo`."""

    def __init__(self, codigo: str = "invalid_filter") -> None:
        super().__init__(codigo)
        self.codigo = codigo


@dataclass(frozen=True)
class Busca:
    """Os filtros de uma busca, já como a base os escreve (veja `busca_dos_pedidos`)."""

    cnaes: tuple[str, ...] = ()
    ufs: tuple[str, ...] = ()
    municipios: tuple[str, ...] = ()
    portes: tuple[str, ...] = ()
    naturezas: tuple[str, ...] = ()
    situacoes: tuple[str, ...] = (SITUACOES["ativa"],)
    aberta_antes: date | None = None
    aberta_depois: date | None = None
    matriz: bool | None = None
    capital_min: float | None = None
    capital_max: float | None = None
    filiais_min: int | None = None
    ordem: str | None = (
        None  # coluna da base (`capital_social` ou `n_estabelecimentos`); None é por CNPJ
    )
    decrescente: bool = False
    depois_de: str | None = None  # CNPJ do último da página anterior
    valor_depois_de: float | None = (
        None  # o valor da ordem desse último (só quando há `ordem`)
    )
    limite: int = LIMITE_PADRAO
    # CNPJs certos (14 dígitos), para a comparação da tela do analista; a API externa não recebe este filtro
    cnpjs: tuple[str, ...] = ()

    def filtros(self) -> int:
        """Quantos filtros além da situação foram pedidos."""
        return sum(
            bool(v)
            for v in (
                self.cnaes, self.ufs, self.municipios, self.portes, self.naturezas, self.cnpjs,
                self.aberta_antes, self.aberta_depois,
            )
        ) + sum(
            v is not None
            for v in (self.matriz, self.capital_min, self.capital_max, self.filiais_min)
        )  # fmt: skip

    def campos_filtrados(self) -> set[str]:
        """Os campos da base que esta busca usa para filtrar (a situação sempre filtra)."""
        usados = {
            "cnae_principal": self.cnaes, "uf": self.ufs, "municipio": self.municipios,
            "porte": self.portes, "natureza_juridica": self.naturezas,
            "data_inicio_atividade": self.aberta_antes or self.aberta_depois,
            "matriz": self.matriz is not None,
            "capital_social": self.capital_min is not None or self.capital_max is not None or self.ordem == "capital_social",
            "n_estabelecimentos": self.filiais_min is not None or self.ordem == "n_estabelecimentos",
        }  # fmt: skip
        return {"situacao_cadastral", *(nome for nome, uso in usados.items() if uso)}


@dataclass(frozen=True)
class BuscaServida:
    """Uma página: o corpo, as fontes usadas (para a atribuição) e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


def _digitos(texto: str, minimo: int, maximo: int) -> str:
    limpo = texto.strip()
    if not (limpo.isascii() and limpo.isdigit()) or not minimo <= len(limpo) <= maximo:
        raise FiltroInvalido
    return limpo


def _codigos_de_municipio(pedidos: list[str]) -> tuple[str, ...]:
    """O código da Receita (4 dígitos) ou o nome (sem acento nem caixa) vira os códigos da Receita."""
    codigos: set[str] = set()
    for pedido in pedidos:
        if pedido.strip().isascii() and pedido.strip().isdigit():
            codigos.add(
                _digitos(pedido, 1, TAMANHO_DO_MUNICIPIO).zfill(TAMANHO_DO_MUNICIPIO)
            )
            continue
        achados = codigos_do_municipio(pedido)
        if not achados:
            raise FiltroInvalido
        codigos.update(achados)
    return tuple(sorted(codigos))


def _ufs(pedidos: list[str]) -> tuple[str, ...]:
    ufs = tuple(sorted({p.strip().upper() for p in pedidos}))
    if any(len(uf) != TAMANHO_DA_UF or not uf.isalpha() for uf in ufs):
        raise FiltroInvalido
    return ufs


def _um_de(pedidos: list[str], vocabulario: tuple[str, ...]) -> tuple[str, ...]:
    valores = tuple(sorted({p.strip().lower() for p in pedidos}))
    if any(valor not in vocabulario for valor in valores):
        raise FiltroInvalido
    return valores


def _situacoes(pedidos: list[str]) -> tuple[str, ...]:
    if not pedidos:
        return (SITUACOES["ativa"],)
    nomes = _um_de(pedidos, tuple(SITUACOES))
    return tuple(sorted(SITUACOES[nome] for nome in nomes))


def cursor_de(cnpj: str, valor: float | None = None) -> str:
    """O cursor opaco que a próxima página manda de volta: o último CNPJ e, se a ordem não é por CNPJ, o
    valor da ordem dele (JSON dentro do base64; o texto do CNPJ sozinho é a ordem por CNPJ)."""
    texto = cnpj if valor is None else json.dumps([valor, cnpj])
    return base64.urlsafe_b64encode(texto.encode()).decode().rstrip("=")


def _cnpj_valido(texto: object) -> str:
    if (
        not isinstance(texto, str)
        or len(texto) != TAMANHO_DO_CNPJ
        or not (texto.isascii() and texto.isalnum())
    ):
        raise FiltroInvalido("invalid_cursor")
    return texto


def _do_cursor(cursor: str) -> tuple[str, float | None]:
    """(CNPJ, valor da ordem ou None) do cursor; `FiltroInvalido("invalid_cursor")` se não é nosso."""
    try:
        texto = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        if texto.startswith("["):
            valor, cnpj = json.loads(texto)
            if isinstance(valor, bool) or not isinstance(valor, int | float):
                raise FiltroInvalido("invalid_cursor")
            if not math.isfinite(valor):
                raise FiltroInvalido("invalid_cursor")
            return _cnpj_valido(cnpj), float(valor)
    except (binascii.Error, UnicodeDecodeError, ValueError, OverflowError) as erro:
        raise FiltroInvalido("invalid_cursor") from erro
    return _cnpj_valido(texto), None


def _ordem(sort: str | None) -> tuple[str | None, bool]:
    """`capital`, `-capital`, `branches` ou `-branches` -> (coluna, decrescente); sem ordem é por CNPJ."""
    if sort is None:
        return None, False
    pedido = sort.strip().lower()
    decrescente = pedido.startswith("-")
    nome = pedido.removeprefix("-")
    if nome not in ORDENS:
        raise FiltroInvalido
    return ORDENS[nome], decrescente


def _numero(valor: float | None, maximo: float) -> float | None:
    if valor is None:
        return None
    if not math.isfinite(valor) or not 0 <= valor <= maximo:
        raise FiltroInvalido
    return float(valor)


def busca_dos_pedidos(
    *,
    cnae: list[str], state: list[str], municipality: list[str], size: list[str],
    legal_nature: list[str], registration_status: list[str], opened_before: date | None,
    opened_after: date | None, head_office: bool | None, cursor: str | None, limit: int | None,
    capital_min: float | None = None, capital_max: float | None = None,
    branches_min: int | None = None, sort: str | None = None,
) -> Busca:  # fmt: skip
    """Os filtros da rota (nomes de fora, valores como o cliente escreve) viram uma `Busca`; `FiltroInvalido`
    se algo está fora do vocabulário ou da forma, ou se não há filtro nenhum além da situação."""
    if limit is not None and limit < 1:
        raise FiltroInvalido
    capital_min = _numero(capital_min, CAPITAL_MAXIMO)
    capital_max = _numero(capital_max, CAPITAL_MAXIMO)
    if (
        capital_min is not None
        and capital_max is not None
        and capital_min > capital_max
    ):
        raise FiltroInvalido
    if branches_min is not None and not 1 <= branches_min <= FILIAIS_MAXIMAS:
        raise FiltroInvalido
    ordem, decrescente = _ordem(sort)
    depois_de, valor_depois_de = (None, None) if cursor is None else _do_cursor(cursor)
    if cursor is not None and (ordem is None) != (valor_depois_de is None):
        raise FiltroInvalido("invalid_cursor")  # cursor de outra ordem
    listas = (cnae, state, municipality, size, legal_nature, registration_status)
    if any(len(valores) > VALORES_MAXIMOS for valores in listas):
        raise FiltroInvalido
    busca = Busca(
        cnaes=tuple(sorted({_digitos(c, CNAE_MINIMO, CNAE_MAXIMO) for c in cnae})),
        ufs=_ufs(state),
        municipios=_codigos_de_municipio(municipality),
        portes=tuple(
            sorted(PORTES_DA_BASE[p] for p in _um_de(size, tuple(PORTES_DA_BASE)))
        ),
        naturezas=tuple(
            sorted({_digitos(n, 1, NATUREZA_MAXIMA) for n in legal_nature})
        ),
        situacoes=_situacoes(registration_status),
        aberta_antes=opened_before,
        aberta_depois=opened_after,
        matriz=head_office,
        capital_min=capital_min,
        capital_max=capital_max,
        filiais_min=branches_min,
        ordem=ordem,
        decrescente=decrescente,
        depois_de=depois_de,
        valor_depois_de=valor_depois_de,
        limite=min(limit or LIMITE_PADRAO, LIMITE_MAXIMO),
    )
    if not busca.filtros():
        raise FiltroInvalido("filter_required")
    return busca


def _em(coluna: str, valores: tuple[str, ...], nome: str, parametros: dict) -> str:
    for i, valor in enumerate(valores):
        parametros[f"{nome}{i}"] = valor
    return f"{coluna} IN ({', '.join(f'${nome}{i}' for i in range(len(valores)))})"


def _prefixos(
    coluna: str, valores: tuple[str, ...], nome: str, parametros: dict
) -> str:
    for i, valor in enumerate(valores):
        parametros[f"{nome}{i}"] = valor
    ou = " OR ".join(f"starts_with({coluna}, ${nome}{i})" for i in range(len(valores)))
    return f"({ou})"


def _onde(busca: Busca, mes: str) -> tuple[list[str], dict[str, object]]:
    """As condições e os parâmetros; o texto vem destes nomes, nunca do pedido (o pedido vai em parâmetro)."""
    parametros: dict[str, object] = {"mes": mes}
    condicoes = [
        "e.mes_do_retrato = $mes",
        _em("e.situacao_cadastral", busca.situacoes, "s", parametros),
    ]
    if busca.cnpjs:
        condicoes.append(_em("e.cnpj", busca.cnpjs, "j", parametros))
    if busca.cnaes:
        condicoes.append(_prefixos("e.cnae_principal", busca.cnaes, "c", parametros))
    if busca.ufs:
        condicoes.append(_em("e.uf", busca.ufs, "u", parametros))
    if busca.municipios:
        condicoes.append(_em("e.municipio", busca.municipios, "m", parametros))
    if busca.portes:
        condicoes.append(_em("p.porte", busca.portes, "p", parametros))
    if busca.naturezas:
        condicoes.append(
            _prefixos("p.natureza_juridica", busca.naturezas, "n", parametros)
        )
    if busca.aberta_antes:
        condicoes.append("e.data_inicio_atividade < CAST($antes AS DATE)")
        parametros["antes"] = busca.aberta_antes.isoformat()
    if busca.aberta_depois:
        condicoes.append("e.data_inicio_atividade > CAST($depois AS DATE)")
        parametros["depois"] = busca.aberta_depois.isoformat()
    if busca.matriz is not None:
        condicoes.append("e.matriz = $matriz")
        parametros["matriz"] = busca.matriz
    if busca.capital_min is not None:
        condicoes.append("p.capital_social >= $capital_min")
        parametros["capital_min"] = busca.capital_min
    if busca.capital_max is not None:
        condicoes.append("p.capital_social <= $capital_max")
        parametros["capital_max"] = busca.capital_max
    if busca.filiais_min is not None:
        condicoes.append("p.n_estabelecimentos >= $filiais_min")
        parametros["filiais_min"] = busca.filiais_min
    if busca.depois_de:
        condicoes.append(_depois_do_cursor(busca, parametros))
    return condicoes, parametros


def _depois_do_cursor(busca: Busca, parametros: dict[str, object]) -> str:
    """Só o que vem depois do último da página anterior, na ordem pedida (CNPJ desempata sempre, crescente)."""
    parametros["cursor"] = busca.depois_de
    if busca.ordem is None:
        return "e.cnpj > $cursor"
    parametros["cursor_valor"] = busca.valor_depois_de
    coluna = f"p.{busca.ordem}"  # a coluna vem de ORDENS, nunca do pedido
    depois = "<" if busca.decrescente else ">"
    return f"({coluna} {depois} $cursor_valor OR ({coluna} = $cursor_valor AND e.cnpj > $cursor))"


def _ordenacao(busca: Busca) -> str:
    if busca.ordem is None:
        return "e.cnpj"
    sentido = "DESC" if busca.decrescente else "ASC"
    return (
        f"p.{busca.ordem} {sentido}, e.cnpj"  # a coluna vem de ORDENS, nunca do pedido
    )


def _aspas(nome: str) -> str:
    return '"' + nome.replace('"', '""') + '"'


class LeitorDeProspeccao:
    """Busca empresas numa porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido, linhas_maximas: int) -> None:
        self.porta = porta
        self.permitido = permitido
        self.linhas_maximas = linhas_maximas

    def _mes_do_retrato(self, como_era_em: date) -> str | None:
        """O retrato mais novo já público em `como_era_em`, nas duas tabelas (o mesmo mês em ambas)."""
        meses = []
        for tabela in (ESTABELECIMENTOS, EMPRESAS):
            condicao = condicao_como_era(self.porta.colunas(tabela), tabela)
            achado = self.porta.con.execute(
                f"SELECT max({MES}) FROM {_aspas(nome_da_view(tabela))} WHERE {condicao}",
                {"dia": dia_de(como_era_em)},
            ).fetchone()
            meses.append(None if achado is None else achado[0])
        return None if None in meses else min(meses)

    def _liberados(self, busca: Busca) -> bool:
        """O portão libera algum campo e todo campo que serve de filtro? Filtro por campo negado seria um
        oráculo do valor que o portão nega, e o CNPJ sozinho não sai."""
        if not any(self.permitido(FONTE, nome, False) for nome in CAMPOS):
            return False
        return all(
            self.permitido(FONTE, campo_, False) for campo_ in busca.campos_filtrados()
        )

    def buscar(self, busca: Busca, como_era_em: date) -> BuscaServida | None:
        """Uma página da busca no retrato que valia em `como_era_em`; None se não há retrato público ainda
        ou se o portão nega a busca (sem contrato do conjunto, ou filtro por campo negado)."""
        if not self._liberados(busca):
            return None
        mes = self._mes_do_retrato(como_era_em)
        if mes is None:
            return None
        existentes = set(self.porta.colunas(EMPRESAS))
        if not busca.campos_filtrados() <= existentes | set(CAMPOS_DO_ESTABELECIMENTO):
            return None  # a tabela montada antes de capital e estabelecimentos não responde a esse filtro
        limite = max(1, min(busca.limite, self.linhas_maximas))
        condicoes, parametros = _onde(busca, mes)
        parametros["limite"] = limite + 1
        consulta = (
            f"SELECT e.cnpj, e.{PUBLICADO_EM}, e.{MES}, "
            + ", ".join(f"p.{c}" for c in CAMPOS_DA_EMPRESA if c in existentes)
            + ", "
            + ", ".join(f"e.{c}" for c in CAMPOS_DO_ESTABELECIMENTO)
            + f" FROM {_aspas(nome_da_view(ESTABELECIMENTOS))} e"
            + f" JOIN {_aspas(nome_da_view(EMPRESAS))} p"
            + f" ON p.cnpj_basico = e.cnpj_basico AND p.{MES} = e.{MES}"
            + f" WHERE {' AND '.join(condicoes)} ORDER BY {_ordenacao(busca)} LIMIT $limite"
        )
        achadas = self.porta.con.execute(consulta, parametros).df()
        cortada = len(achadas) > limite
        achadas = achadas.head(limite)
        empresas = [self._empresa(linha) for _, linha in achadas.iterrows()]
        corpo = {
            "como_era_em": como_era_em.isoformat(),
            "empresas": empresas,
            "cortada": cortada,
            "proximo_cursor": self._proximo_cursor(busca, achadas) if cortada else None,
        }
        return BuscaServida(corpo, {FONTE} if empresas else set(), len(empresas))

    @staticmethod
    def _proximo_cursor(busca: Busca, achadas: pd.DataFrame) -> str:
        ultima = achadas.iloc[-1]
        valor = None if busca.ordem is None else float(ultima[busca.ordem])
        return cursor_de(str(ultima["cnpj"]), valor)

    def _empresa(self, linha: pd.Series) -> dict[str, object]:
        """Uma empresa: o CNPJ e, em envelope, os campos que o portão libera."""
        publico_em = pd.Timestamp(linha[PUBLICADO_EM]).date()
        servidos = {
            nome: campo(_valor(nome, linha[nome]), fonte=FONTE, publico_em=publico_em, visto_em=None)
            for nome in CAMPOS
            if nome in linha.index and self.permitido(FONTE, nome, False)
        }  # fmt: skip
        return {"cnpj": str(linha["cnpj"]), **servidos}


def _valor(nome: str, valor: object) -> object:
    """O valor da base num tipo que vira JSON: data em ISO, booleano do NumPy em booleano, vazio em None."""
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    if nome == "data_inicio_atividade":
        return pd.Timestamp(valor).date().isoformat()  # type: ignore[arg-type]
    if nome == "matriz":
        return bool(valor)
    if nome == "porte":
        return PORTES_DE_FORA.get(str(valor), str(valor))
    if nome == "capital_social":
        return float(valor)  # type: ignore[arg-type]
    if nome == "n_estabelecimentos":
        return int(valor)  # type: ignore[call-overload]
    return str(valor)
