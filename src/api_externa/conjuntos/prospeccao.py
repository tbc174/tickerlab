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
matriz. Pelo menos um filtro além da situação: ninguém baixa a base inteira. Ordem por CNPJ, com cursor
opaco (o último CNPJ da página) e `limite` (padrão 50, no máximo 100 e o que o plano deixa por resposta).
Sem total: contar custaria uma varredura a mais por chamada. A consulta lê só as colunas pedidas dos
arquivos Parquet (formato em colunas), com os filtros empurrados para a leitura.

**Fora, por desenho (decisão D2.4 do portão):** a API externa não busca por nome. A busca por trecho da razão
social precisa de decisão própria sobre a regra (nome de empresa que carrega nome de pessoa) e fica para um
PR depois, se a Diretoria autorizar; entra como mais um filtro deste mesmo leitor.
"""

import base64
import binascii
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
PORTES = ("micro", "pequeno", "demais", "nao_informado")
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
CAMPOS_DA_EMPRESA = ("razao_social", "natureza_juridica", "porte")
CAMPOS = (*CAMPOS_DA_EMPRESA, *CAMPOS_DO_ESTABELECIMENTO)
PUBLICADO_EM = "publico_em"
MES = "mes_do_retrato"
TAMANHO_DA_UF = 2
TAMANHO_DO_CNPJ = 14
TAMANHO_DO_MUNICIPIO = 4
CNAE_MINIMO, CNAE_MAXIMO = 2, 7
NATUREZA_MAXIMA = 4


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
    depois_de: str | None = None
    limite: int = LIMITE_PADRAO

    def filtros(self) -> int:
        """Quantos filtros além da situação foram pedidos."""
        return sum(
            bool(v)
            for v in (
                self.cnaes, self.ufs, self.municipios, self.portes, self.naturezas,
                self.aberta_antes, self.aberta_depois,
            )
        ) + (self.matriz is not None)  # fmt: skip


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


def cursor_de(cnpj: str) -> str:
    """O cursor opaco que a próxima página manda de volta."""
    return base64.urlsafe_b64encode(cnpj.encode()).decode().rstrip("=")


def _cnpj_do_cursor(cursor: str) -> str:
    try:
        texto = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError) as erro:
        raise FiltroInvalido("invalid_cursor") from erro
    if len(texto) != TAMANHO_DO_CNPJ or not (texto.isascii() and texto.isalnum()):
        raise FiltroInvalido("invalid_cursor")
    return texto


def busca_dos_pedidos(
    *,
    cnae: list[str], state: list[str], municipality: list[str], size: list[str],
    legal_nature: list[str], registration_status: list[str], opened_before: date | None,
    opened_after: date | None, head_office: bool | None, cursor: str | None, limit: int | None,
) -> Busca:  # fmt: skip
    """Os filtros da rota (nomes de fora, valores como o cliente escreve) viram uma `Busca`; `FiltroInvalido`
    se algo está fora do vocabulário ou da forma, ou se não há filtro nenhum além da situação."""
    if limit is not None and limit < 1:
        raise FiltroInvalido
    busca = Busca(
        cnaes=tuple(sorted({_digitos(c, CNAE_MINIMO, CNAE_MAXIMO) for c in cnae})),
        ufs=_ufs(state),
        municipios=_codigos_de_municipio(municipality),
        portes=_um_de(size, PORTES),
        naturezas=tuple(
            sorted({_digitos(n, 1, NATUREZA_MAXIMA) for n in legal_nature})
        ),
        situacoes=_situacoes(registration_status),
        aberta_antes=opened_before,
        aberta_depois=opened_after,
        matriz=head_office,
        depois_de=None if cursor is None else _cnpj_do_cursor(cursor),
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
    if busca.depois_de:
        condicoes.append("e.cnpj > $cursor")
        parametros["cursor"] = busca.depois_de
    return condicoes, parametros


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

    def buscar(self, busca: Busca, como_era_em: date) -> BuscaServida | None:
        """Uma página da busca no retrato que valia em `como_era_em`; None se não há retrato público ainda."""
        mes = self._mes_do_retrato(como_era_em)
        if mes is None:
            return None
        limite = max(1, min(busca.limite, self.linhas_maximas))
        condicoes, parametros = _onde(busca, mes)
        parametros["limite"] = limite + 1
        consulta = (
            f"SELECT e.cnpj, e.{PUBLICADO_EM}, e.{MES}, "
            + ", ".join(f"p.{c}" for c in CAMPOS_DA_EMPRESA)
            + ", "
            + ", ".join(f"e.{c}" for c in CAMPOS_DO_ESTABELECIMENTO)
            + f" FROM {_aspas(nome_da_view(ESTABELECIMENTOS))} e"
            + f" JOIN {_aspas(nome_da_view(EMPRESAS))} p"
            + f" ON p.cnpj_basico = e.cnpj_basico AND p.{MES} = e.{MES}"
            + f" WHERE {' AND '.join(condicoes)} ORDER BY e.cnpj LIMIT $limite"
        )
        achadas = self.porta.con.execute(consulta, parametros).df()
        cortada = len(achadas) > limite
        achadas = achadas.head(limite)
        empresas = [self._empresa(linha) for _, linha in achadas.iterrows()]
        corpo = {
            "como_era_em": como_era_em.isoformat(),
            "empresas": empresas,
            "cortada": cortada,
            "proximo_cursor": cursor_de(str(achadas["cnpj"].iloc[-1]))
            if cortada
            else None,
        }
        return BuscaServida(corpo, {FONTE} if empresas else set(), len(empresas))

    def _empresa(self, linha: pd.Series) -> dict[str, object]:
        """Uma empresa: o CNPJ e, em envelope, os campos que o portão libera."""
        publico_em = pd.Timestamp(linha[PUBLICADO_EM]).date()
        servidos = {
            nome: campo(_valor(nome, linha[nome]), fonte=FONTE, publico_em=publico_em, visto_em=None)
            for nome in CAMPOS
            if self.permitido(FONTE, nome, False)
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
    return str(valor)
