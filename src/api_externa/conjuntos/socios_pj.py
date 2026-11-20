"""Os sócios pessoa jurídica de um CNPJ e as empresas de que ele é sócio, como eram num dia (frente 3, 18/11/2026).

`LeitorDeSociosPj(porta, permitido, linhas_maximas).socios(cnpj, como_era_em)` refaz o quadro de sócios PJ do dia
pela tabela `entradas_de_socio_pj` (fonte `rfb-cnpj`): de cada par empresa e sócia, o último movimento já público
no dia, e só os pares cujo último movimento é a entrada. É a mesma conta do quadro do dia de `compradores` e passa
pelo portão do mesmo conjunto (`buyers`), com os mesmos campos: a data de entrada e a razão social. Não tem rota
própria: só a análise completa do CNPJ (`conjuntos/analise.py`) o lê.

**Sem pessoa:** a tabela só tem sócio do tipo 1 (pessoa jurídica) e o quadro com pessoa não é lido. A empresa
pedida passa por `e_empresa`, e cada sócia ou participada só sai se estiver na lista sem pessoa da Receita
(`cnpj_empresas_pj`) do retrato do dia, com natureza de empresa (`empresas.retratos_de_empresa`); a que não
está não sai, nem pela raiz.

**Sem olhar o futuro:** só entra o movimento com `publico_em` até o dia, e a razão social é a do retrato mais
novo já público no dia.
"""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base.porta import Porta
from base.porta.duckdb import dia_de, nome_da_view
from base.porta.rede import views
from src.api_externa.conjuntos import Permitido
from src.api_externa.conjuntos.compradores import CONJUNTO, ENTRADAS, RECEITA
from src.api_externa.conjuntos.empresas import e_empresa, retratos_de_empresa
from src.api_externa.envelope import campo

__all__ = ["CONJUNTO", "LeitorDeSociosPj", "SociosServidos"]

# o que o portão tem de liberar para o bloco sair: a data de entrada e o nome de cada empresa
CAMPOS = ((RECEITA, "data_entrada"), (RECEITA, "razao_social"))
SOCIAS, PARTICIPACOES = "socias_pj", "participacoes_pj"
LIMITES = (
    (
        "Sócios pessoa jurídica: do quadro de sócios da Receita, que a base acompanha desde 05/2023 (antes disso, "
        "só quem ainda era sócio naquele mês). O quadro do dia é refeito das entradas e saídas já públicas."
    ),
    (
        "Só pessoa jurídica: sócio pessoa física, MEI e empresário individual não saem, e a empresa que não está "
        "na lista da Receita sem pessoa no retrato do dia também não."
    ),
)


@dataclass(frozen=True)
class SociosServidos:
    """O que sai do quadro de sócios PJ: o corpo, as fontes usadas (para a atribuição) e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


def _view(tabela: str) -> str:
    return '"' + nome_da_view(tabela).replace('"', '""') + '"'


def _dia(valor: object) -> date | None:
    if valor is None or bool(pd.isna(valor)):  # type: ignore[arg-type]
        return None
    return pd.Timestamp(valor).date()  # type: ignore[arg-type]


class LeitorDeSociosPj:
    """Lê o quadro de sócios PJ do dia de um CNPJ, só se o portão libera a data de entrada e o nome."""

    def __init__(self, porta: Porta, permitido: Permitido, linhas_maximas: int) -> None:
        self.porta = porta
        self.permitido = permitido
        self.linhas_maximas = linhas_maximas

    def _quadro(self, coluna: str, raiz: str, dia: date) -> pd.DataFrame:
        """Os pares do quadro do dia em que `coluna` (a empresa ou a sócia) é a raiz pedida: o último movimento
        já público de cada par, só quando é a entrada; a empresa sócia de si mesma não conta."""
        return self.porta.con.execute(
            "SELECT cnpj_basico AS empresa, raiz_socio_pj AS socia, data_entrada, publico_em "
            f"FROM {_view(ENTRADAS)} WHERE movimento IN ('entrou', 'saiu') AND {coluna} = $raiz "
            "AND raiz_socio_pj <> cnpj_basico AND publico_em <= CAST($dia AS DATE) "
            "QUALIFY row_number() OVER (PARTITION BY cnpj_basico, raiz_socio_pj "
            "ORDER BY mes_do_retrato DESC, movimento = 'saiu' DESC) = 1 AND movimento = 'entrou'",
            {"raiz": raiz, "dia": dia_de(dia)},
        ).df()

    def _itens(
        self, quadro: pd.DataFrame, outra: str, nomes: dict[str, pd.Series]
    ) -> list[dict]:
        """Uma linha por empresa do outro lado do par (a sócia ou a participada), só a que está na lista sem
        pessoa; da entrada mais nova à mais velha e, no empate, pela raiz."""
        itens = []
        for linha in quadro.to_dict("records"):
            raiz = str(linha[outra])
            nome = nomes.get(raiz)
            if nome is None:
                continue
            entrada = _dia(linha["data_entrada"])
            itens.append(
                {
                    "raiz_do_cnpj": raiz,
                    "razao_social": campo(
                        str(nome["razao_social"] or ""),
                        fonte=RECEITA,
                        publico_em=_dia(nome["publico_em"]),
                        visto_em=None,
                    ),
                    "data_entrada": campo(
                        entrada and entrada.isoformat(),
                        fonte=RECEITA,
                        publico_em=_dia(linha["publico_em"]),
                        visto_em=None,
                    ),
                }
            )
        return sorted(
            itens,
            key=lambda i: (i["data_entrada"]["valor"] or "", i["raiz_do_cnpj"]),
            reverse=True,
        )

    def socios(self, cnpj: str, como_era_em: date) -> SociosServidos | None:
        """As sócias PJ do CNPJ e as empresas de que ele é sócio, como eram em `como_era_em`; None se o portão
        não libera os campos, se a base não tem a tabela ou se o CNPJ não é de empresa."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        if not all(self.permitido(fonte, nome, False) for fonte, nome in CAMPOS):
            return None
        if ENTRADAS not in views(self.porta.con) or not e_empresa(self.porta, normal):
            return None
        raiz = normal[: cnpj_.TAMANHO_DA_RAIZ]
        socias = self._quadro("cnpj_basico", raiz, como_era_em)
        participacoes = self._quadro("raiz_socio_pj", raiz, como_era_em)
        outras = {*socias["socia"].astype(str), *participacoes["empresa"].astype(str)}
        nomes = retratos_de_empresa(self.porta, outras, como_era_em, ("razao_social",))
        cabem = max(self.linhas_maximas, 1)
        listas = {
            SOCIAS: self._itens(socias, "socia", nomes),
            PARTICIPACOES: self._itens(participacoes, "empresa", nomes),
        }
        cortada = any(len(lista) > cabem for lista in listas.values())
        corpo: dict[str, object] = {
            "cnpj": normal,
            "como_era_em": como_era_em.isoformat(),
            **{nome: lista[:cabem] for nome, lista in listas.items()},
            "cortada": cortada,
            "limites": list(LIMITES),
        }
        linhas = sum(min(len(lista), cabem) for lista in listas.values())
        return SociosServidos(corpo, {RECEITA}, linhas)
