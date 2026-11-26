"""As vizinhas do mesmo ramo de um CNPJ, como eram num dia (linha 1038): o bloco da análise completa.

`LeitorDeVizinhas(porta, permitido, linhas_maximas).vizinhas(cnpj, como_era_em)` lê a atividade principal (CNAE de
7 dígitos), a UF e o município do estabelecimento pedido e devolve as outras empresas **ativas** com a mesma
atividade principal: as que têm estabelecimento no município e, à parte, as da mesma UF sem estabelecimento nele.
Uma linha por empresa, da maior para a menor pelo capital social, com o total de cada recorte. É a tabela que quem
origina um mandato usa para pensar em quem compraria.

Só lê as duas tabelas sem pessoa do CNPJ (`cnpj_estabelecimentos_pj` e `cnpj_empresas_pj`, as da busca de
empresas) e passa pelas mesmas linhas de direito dela (conjunto `prospecting`): não libera nada que
`GET /data/v1/companies` já não dê. Sobre as listadas vão ainda a trava de pessoa das outras leituras
(`empresas.e_empresas`) e, na leitura mais estreita, fica de fora quem tem CPF ou e-mail na razão social.

**Sem olhar o futuro:** vale o retrato mensal mais novo já público em `como_era_em` (o mesmo da busca).

Não diz quem é o dono (no exterior ou no Brasil: o quadro só de pessoa jurídica não traz o sócio estrangeiro) nem
traz sinal de risco por vizinha.
"""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base import receita_codigos
from base.porta.duckdb import nome_da_view
from src.api_externa.conjuntos import prospeccao
from src.api_externa.conjuntos.empresas import e_empresa, e_empresas
from src.api_externa.envelope import campo
from src.pessoa_no_texto import texto_de_pessoa

__all__ = ["BLOCO", "CONJUNTO", "EXIGE", "LeitorDeVizinhas", "VizinhasServidas"]

BLOCO = "vizinhas"
CONJUNTO = prospeccao.CONJUNTO
FONTE = prospeccao.FONTE
ESTABELECIMENTOS = prospeccao.ESTABELECIMENTOS
EMPRESAS = prospeccao.EMPRESAS
# o que o portão tem de liberar para o bloco sair: o nome e tudo o que serve de filtro (filtro por campo negado
# seria um oráculo do valor que o portão nega). O resto sai campo a campo.
EXIGE = tuple(
    (FONTE, nome)
    for nome in (
        "razao_social",
        "cnae_principal",
        "uf",
        "municipio",
        "situacao_cadastral",
    )
)
ATIVA = prospeccao.SITUACOES["ativa"]
TAMANHO_DA_RAIZ = 8
# a UF com mais empresas que isto no ramo não é ordenada aqui (não caberia no prazo da análise): sai o total
TETO_NA_UF = prospeccao.TETO_DE_RAIZES
# quantas vizinhas cada recorte (município e resto da UF) devolve, no máximo, seja qual for o plano: o bloco não
# conta pedido, então este teto é o que se leva da busca de empresas numa análise (Diretoria, 26/11/2026)
TETO_DE_VIZINHAS = 10
# o que o bloco diz à chave que não tem as linhas da busca de empresas (não depende do CNPJ pedido)
NAO_HABILITADO = (
    "As vizinhas do mesmo ramo não vieram: a busca de empresas (conjunto prospecting) não está habilitada "
    "ou disponível para esta chave hoje. Isso não diz nada sobre a empresa."
)
# quantas candidatas a mais são conferidas, para a lista continuar cheia quando a trava de pessoa tira alguma
FOLGA_DA_TRAVA = 5

LIMITES = (
    (
        "Vizinhas do mesmo ramo: empresas ativas com a mesma atividade principal (CNAE de 7 dígitos) no retrato "
        "da Receita do dia, no município do estabelecimento pedido e, à parte, no resto da UF; atividade "
        "secundária não conta. Uma linha por empresa, da maior para a menor pelo capital social declarado, que "
        "não é faturamento nem valor da empresa. "
        f"São no máximo {TETO_DE_VIZINHAS} em cada recorte (a busca de empresas traz a lista inteira), e as "
        "vizinhas não contam pedido."
    ),
    (
        "A lista só tem pessoa jurídica: MEI e empresário individual não entram, nem nos totais; empresa que a "
        "trava de pessoa segura (número de pessoa na razão social, por exemplo) conta no total e não é listada."
    ),
    (
        "A lista não diz quem é o dono (no exterior ou no Brasil) nem traz sinal de risco de cada vizinha: "
        "consulte o CNPJ dela. Estar na lista não quer dizer que a empresa compra ou está à venda."
    ),
)
LIMITE_DA_UF_GRANDE = (
    "O ramo tem empresas demais na UF para montar aqui a lista do resto dela: sai o total; a busca de empresas "
    "(atividade, UF e ordem pelo capital) traz a lista."
)
LIMITE_SEM_CAPITAL = "Sem o capital social liberado, as vizinhas vêm na ordem do CNPJ."


@dataclass(frozen=True)
class VizinhasServidas:
    """O bloco servido: o corpo, as fontes usadas (para a atribuição) e as linhas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


def sem_vizinhas(corpo: dict) -> bool:
    """O ramo não tem outra empresa na UF: só aí o bloco é "não achado" (lista vazia com total é outra coisa)."""
    return not corpo.get("total_na_uf")


def _view(tabela: str) -> str:
    return '"' + nome_da_view(tabela).replace('"', '""') + '"'


def _dia(valor: object) -> date:
    return pd.Timestamp(valor).date()  # type: ignore[arg-type]


def _vazio(valor: object) -> bool:
    return valor is None or bool(pd.isna(valor)) or valor == ""  # type: ignore[arg-type]


def _texto(valor: object) -> str | None:
    return None if _vazio(valor) else str(valor)


# a coluna da base -> como o valor sai (o mesmo tipo da busca de empresas)
_DA_EMPRESA = {
    "razao_social": _texto,
    "porte": lambda v: (
        None if _vazio(v) else prospeccao.PORTES_DE_FORA.get(str(v), str(v))
    ),
    "capital_social": lambda v: None if _vazio(v) else float(v),  # type: ignore[arg-type]
    "n_estabelecimentos": lambda v: None if _vazio(v) else int(v),  # type: ignore[call-overload]
}
_DO_ESTABELECIMENTO = {
    "data_inicio_atividade": lambda v: None if _vazio(v) else _dia(v).isoformat(),
    "matriz": lambda v: None if _vazio(v) else bool(v),
}


class LeitorDeVizinhas(prospeccao.LeitorDeProspeccao):
    """Lê as vizinhas do mesmo ramo numa porta para um pedido (herda da busca o retrato do dia)."""

    def _do_pedido(self, cnpj: str, mes: str) -> pd.Series | None:
        """A atividade, a UF e o município do estabelecimento pedido no retrato; None se falta algum."""
        achado = self.porta.con.execute(
            "SELECT cnae_principal, uf, municipio, publico_em "
            f"FROM {_view(ESTABELECIMENTOS)} "
            "WHERE cnpj_basico = $raiz AND cnpj = $cnpj AND mes_do_retrato = $mes",
            {"raiz": cnpj[:TAMANHO_DA_RAIZ], "cnpj": cnpj, "mes": mes},
        ).df()
        if achado.empty:
            return None
        linha = achado.iloc[0]
        if any(_vazio(linha[nome]) for nome in ("cnae_principal", "uf", "municipio")):
            return None
        return linha

    def _estabelecimentos_do_ramo(
        self, pedido: pd.Series, raiz: str, mes: str
    ) -> pd.DataFrame:
        """Um estabelecimento por empresa ativa do ramo na UF (menos a pedida): o do município, se houver, e
        entre eles a matriz e o menor CNPJ. `na_cidade` diz se é do município."""
        achados = self.porta.con.execute(
            "SELECT cnpj_basico, cnpj, matriz, municipio, data_inicio_atividade, publico_em "
            f"FROM {_view(ESTABELECIMENTOS)} WHERE mes_do_retrato = $mes AND cnae_principal = $cnae "
            "AND uf = $uf AND situacao_cadastral = $ativa AND cnpj_basico <> $raiz",
            {
                "mes": mes,
                "cnae": str(pedido["cnae_principal"]),
                "uf": str(pedido["uf"]),
                "ativa": ATIVA,
                "raiz": raiz,
            },
        ).df()
        achados["na_cidade"] = achados["municipio"] == str(pedido["municipio"])
        achados["filial"] = ~achados["matriz"].fillna(False).astype(bool)
        achados = achados.sort_values(
            ["na_cidade", "filial", "cnpj"], ascending=[False, True, True]
        )
        return achados.drop_duplicates("cnpj_basico").drop(columns="filial")

    def _empresas_de(self, raizes: list[str], mes: str) -> pd.DataFrame:
        """As linhas de `cnpj_empresas_pj` das raízes no retrato; a coluna que a base não tem fica de fora."""
        existentes = set(self.porta.colunas(EMPRESAS))
        colunas = [nome for nome in _DA_EMPRESA if nome in existentes]
        return self.porta.con.execute(
            f"SELECT cnpj_basico, publico_em AS publico_em_da_empresa, {', '.join(colunas)} "
            f"FROM {_view(EMPRESAS)} WHERE mes_do_retrato = $mes "
            "AND cnpj_basico BETWEEN $de AND $ate AND cnpj_basico IN (SELECT unnest($raizes))",
            {"mes": mes, "de": min(raizes), "ate": max(raizes), "raizes": raizes},
        ).df()

    def _por_capital(self) -> bool:
        return self.permitido(FONTE, "capital_social", False) and (
            "capital_social" in self.porta.colunas(EMPRESAS)
        )

    def _ordenadas(self, juntas: pd.DataFrame) -> pd.DataFrame:
        """Da maior para a menor pelo capital (sem capital vale 0), com o CNPJ no desempate; sem o capital
        liberado, só pelo CNPJ."""
        if not self._por_capital():
            return juntas.sort_values("cnpj")
        ordem = juntas.assign(capital_da_ordem=juntas["capital_social"].fillna(0))
        return ordem.sort_values(["capital_da_ordem", "cnpj"], ascending=[False, True])

    def _listadas(self, ordenadas: pd.DataFrame, quantas: int) -> list[pd.Series]:
        """As primeiras `quantas` que passam pela trava de pessoa e não têm CPF ou e-mail na razão social."""
        primeiras = ordenadas.head(quantas * 2 + FOLGA_DA_TRAVA)
        empresa = e_empresas(self.porta, [str(c) for c in primeiras["cnpj"]])
        passam = [
            linha
            for _, linha in primeiras.iterrows()
            if empresa.get(str(linha["cnpj"]), False)
            and not texto_de_pessoa(str(linha["razao_social"] or ""))
        ]
        return passam[:quantas]

    def _campo(self, valor: object, publico_em: object) -> dict[str, object]:
        return campo(valor, fonte=FONTE, publico_em=_dia(publico_em), visto_em=None)

    def _item(self, linha: pd.Series, com_municipio: bool) -> dict[str, object]:
        item: dict[str, object] = {"cnpj": str(linha["cnpj"])}
        for nome, converter in _DA_EMPRESA.items():
            if nome in linha.index and self.permitido(FONTE, nome, False):
                item[nome] = self._campo(
                    converter(linha[nome]), linha["publico_em_da_empresa"]
                )
        for nome, converter in _DO_ESTABELECIMENTO.items():
            if self.permitido(FONTE, nome, False):
                item[nome] = self._campo(converter(linha[nome]), linha["publico_em"])
        if com_municipio:
            nome_do_municipio = receita_codigos.municipio(str(linha["municipio"]))
            item["municipio_texto"] = self._campo(
                nome_do_municipio, linha["publico_em"]
            )
        return item

    def _cabecalho(self, pedido: pd.Series, mes: str) -> dict[str, object]:
        publico_em = pedido["publico_em"]
        cnae, uf = str(pedido["cnae_principal"]), str(pedido["uf"])
        return {
            "mes_do_retrato": self._campo(mes, publico_em),
            "cnae_principal": self._campo(cnae, publico_em),
            "cnae_principal_texto": self._campo(receita_codigos.cnae(cnae), publico_em),
            "uf": self._campo(uf, publico_em),
            "municipio_texto": self._campo(
                receita_codigos.municipio(str(pedido["municipio"])), publico_em
            ),
        }

    def _listas(
        self, ramo: pd.DataFrame, mes: str
    ) -> tuple[list[dict], list[dict], list[str]]:
        """(as do município, as do resto da UF, os limites a mais)."""
        extras = [] if self._por_capital() else [LIMITE_SEM_CAPITAL]
        if len(ramo) > TETO_NA_UF:
            ramo = ramo[ramo["na_cidade"]]
            extras.append(LIMITE_DA_UF_GRANDE)
        if ramo.empty:
            return [], [], extras
        empresas = self._empresas_de([str(r) for r in ramo["cnpj_basico"]], mes)
        juntas = self._ordenadas(ramo.merge(empresas, on="cnpj_basico"))
        quantas = max(min(self.linhas_maximas, TETO_DE_VIZINHAS), 1)
        cidade = self._listadas(juntas[juntas["na_cidade"]], quantas)
        resto = self._listadas(juntas[~juntas["na_cidade"]], quantas)
        return (
            [self._item(linha, com_municipio=False) for linha in cidade],
            [self._item(linha, com_municipio=True) for linha in resto],
            extras,
        )

    def vizinhas(self, cnpj: str, como_era_em: date) -> VizinhasServidas | None:
        """As vizinhas do CNPJ como eram em `como_era_em`; None se o portão não libera o que o bloco filtra, se o
        CNPJ não é de empresa, se não há retrato público ou se o estabelecimento não está nele com atividade, UF e
        município. `ValueError` se o CNPJ é inválido."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        if not all(self.permitido(fonte, nome, False) for fonte, nome in EXIGE):
            return None
        if not e_empresa(self.porta, normal):
            return None
        mes = self._mes_do_retrato(como_era_em)
        pedido = None if mes is None else self._do_pedido(normal, mes)
        if mes is None or pedido is None:
            return None
        ramo = self._estabelecimentos_do_ramo(pedido, normal[:TAMANHO_DA_RAIZ], mes)
        # o total conta antes de ordenar: é quantas empresas do ramo há, listadas ou não
        total_na_cidade, total_na_uf = int(ramo["na_cidade"].sum()), len(ramo)
        no_municipio, na_uf, extras = self._listas(ramo, mes)
        corpo = {
            "como_era_em": como_era_em.isoformat(),
            **self._cabecalho(pedido, mes),
            "total_no_municipio": total_na_cidade,
            "total_na_uf": total_na_uf,
            "no_municipio": no_municipio,
            "na_uf": na_uf,
            "cortada": total_na_cidade > len(no_municipio)
            or total_na_uf - total_na_cidade > len(na_uf),
            "limites": [*LIMITES, *extras],
        }
        return VizinhasServidas(corpo, {FONTE}, len(no_municipio) + len(na_uf))
