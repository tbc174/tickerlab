"""Os sinais de tamanho no perfil (linha 1130 da fila; bot Analista, simulação 8, 26/11/2026).

"Esta fechada fatura quanto?" não tem resposta direta na base. O perfil (`profiles`, e por ele a análise completa)
traz, campo a campo pelo portão, os sinais que a base tem, cada um no envelope com a fonte e o dia em que ficou
público:

- `acessos_na_anatel`: os acessos da prestadora no último mês já público, somados por serviço (cada revisão pela
  mais nova; na móvel de 2005 a 2018, uma visão só), conta nossa sobre a tabela da Anatel;
- `n_estabelecimentos`: os estabelecimentos ativos da raiz, contados na montagem da lista sem pessoa da Receita;
- `capital_social`: o capital declarado, no mesmo retrato, sempre com o aviso de que capital não mede tamanho.

Fica fora, na leitura mais estreita do "pode" da Diretoria (26/11/2026): a conta de receita (não há premissa de
fonte pública para o R$ por acesso), o porte do BNDES (a tabela não tem prontidão) e o PAT (só como publicado, e de
uso interno). Pessoa não sai: o perfil só chega aqui depois do cadastro, que já barrou quem é pessoa.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base.porta import Porta
from base.porta.duckdb import condicao_como_era, dia_de, nome_da_view
from base.porta.rede import views
from src.api_externa.conjuntos import Permitido, empresas
from src.api_externa.envelope import campo

FONTE_DA_ANATEL = "anatel-acessos"
TABELA_DA_ANATEL = "anatel_acessos"
COMPLETO, MODALIDADE = "completo", "modalidade"
# as chaves da `anatel_acessos` sem o `visto_em` (o contrato): a mesma chave com outro `visto_em` é revisão
CHAVES_DA_ANATEL = (
    "competencia", "servico", "recorte", "cnpj", "uf", "regiao_pgo", "codigo_nacional", "modalidade_de_cobranca",
    "tecnologia", "geracao", "tipo_de_pessoa", "tipo_de_produto", "faixa_de_velocidade", "meio_de_acesso",
    "tipo_de_acesso_tv",
)  # fmt: skip
AVISO_DO_CAPITAL = (
    "O capital social não mede tamanho: é o valor declarado no contrato social, não o faturamento (há empresa com "
    "capital de R$ 70 mil e receita de R$ 122 milhões, e o contrário)."
)
AVISO_DA_ANATEL = "Os acessos na Anatel são os do último mês já público, somados por serviço: sinal de porte, não receita."


@dataclass(frozen=True)
class OrigemDoSinal:
    """De que coleta e de que tabelas o sinal sai, e se é conta nossa (derivado)."""

    fonte: str
    tabelas: tuple[str, ...]
    derivado: bool


# os campos do bloco, na ordem de saída; há teste que confere que cada um tem linha de direito em `profiles`
CAMPOS: dict[str, OrigemDoSinal] = {
    "acessos_na_anatel": OrigemDoSinal(FONTE_DA_ANATEL, (TABELA_DA_ANATEL,), True),
    "n_estabelecimentos": OrigemDoSinal(
        empresas.FONTE, (empresas.LISTA_DE_EMPRESAS,), True
    ),
    "capital_social": OrigemDoSinal(
        empresas.FONTE, (empresas.LISTA_DE_EMPRESAS,), False
    ),
}
DA_RECEITA = ("n_estabelecimentos", "capital_social")


def limites(servidos: dict[str, object]) -> list[str]:
    """Os avisos do bloco: o do capital sempre que ele sai, o da Anatel quando os acessos saem."""
    avisos = []
    if "acessos_na_anatel" in servidos:
        avisos.append(AVISO_DA_ANATEL)
    if "capital_social" in servidos:
        avisos.append(AVISO_DO_CAPITAL)
    return avisos


def _sem_revisoes_velhas(linhas: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por chave: a do `visto_em` mais novo (a revisão de um mês passado vira linha nova)."""
    if "visto_em" not in linhas:
        return linhas
    chaves = [coluna for coluna in CHAVES_DA_ANATEL if coluna in linhas]
    return (
        linhas.sort_values("visto_em").groupby(chaves, dropna=False, sort=False).tail(1)
    )


def _uma_visao_por_servico(linhas: pd.DataFrame) -> pd.DataFrame:
    """Na móvel de 2005 a 2018 a Anatel dá duas visões dos mesmos acessos: fica a completa, ou só a modalidade."""
    if "recorte" not in linhas:
        return linhas
    partes = []
    for _, do_servico in linhas.groupby("servico", sort=True):
        recortes = set(do_servico["recorte"].dropna())
        escolhido = next((r for r in (COMPLETO, MODALIDADE) if r in recortes), None)
        partes.append(
            do_servico
            if escolhido is None
            else do_servico[do_servico["recorte"] == escolhido]
        )
    return pd.concat(partes) if partes else linhas


def acessos_por_servico(linhas: pd.DataFrame) -> dict[str, object] | None:
    """O último mês das linhas, somado por serviço; None sem linha."""
    if linhas.empty:
        return None
    ultimo = linhas["competencia"].max()
    do_mes = _uma_visao_por_servico(
        _sem_revisoes_velhas(linhas[linhas["competencia"] == ultimo])
    )
    soma = do_mes.groupby("servico")["acessos"].sum()
    por_servico = [
        {"servico": str(servico), "acessos": round(float(total))}
        for servico, total in soma.items()
    ]
    return {
        "competencia": pd.Timestamp(ultimo).strftime("%Y-%m"),
        "acessos_por_servico": por_servico,
        "acessos_total": sum(int(item["acessos"]) for item in por_servico),
        "publico_em": pd.Timestamp(do_mes["publico_em"].max()).date(),
    }


class LeitorDeTamanho:
    """Lê os sinais de tamanho de uma empresa de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido) -> None:
        self.porta = porta
        self.permitido = permitido

    def _liberado(self, nome: str) -> bool:
        origem = CAMPOS[nome]
        return self.permitido(origem.fonte, nome, origem.derivado)

    def _anatel(self, normal: str, como_era_em: date) -> dict[str, dict]:
        if not self._liberado("acessos_na_anatel") or TABELA_DA_ANATEL not in views(
            self.porta.con
        ):
            return {}
        condicao = condicao_como_era(
            self.porta.colunas(TABELA_DA_ANATEL), TABELA_DA_ANATEL
        )
        # a prestadora pelo CNPJ inteiro (matriz) ou por qualquer estabelecimento da raiz
        linhas = self.porta.con.execute(
            f'SELECT * FROM "{nome_da_view(TABELA_DA_ANATEL)}" WHERE {condicao} AND '
            "(CAST(cnpj AS VARCHAR) LIKE $digitos OR CAST(cnpj AS VARCHAR) LIKE $pontuado)",
            {
                "dia": dia_de(como_era_em),
                "digitos": f"{normal[: empresas.TAMANHO_DA_RAIZ]}%",
                "pontuado": f"{cnpj_.formatar(normal)[:10]}%",
            },
        ).df()
        somado = acessos_por_servico(linhas)
        if somado is None:
            return {}
        publico_em = somado.pop("publico_em")
        return {
            "acessos_na_anatel": campo(
                somado, fonte=FONTE_DA_ANATEL, publico_em=publico_em, visto_em=None
            )
        }

    def _da_receita(self, normal: str, como_era_em: date) -> dict[str, dict]:
        if empresas.LISTA_DE_EMPRESAS not in views(self.porta.con):
            return {}
        # as duas colunas entraram na versão 1.1.0 da lista (10/11/2026): retrato sem elas não derruba o perfil
        existem = set(self.porta.colunas(empresas.LISTA_DE_EMPRESAS))
        liberados = [
            nome for nome in DA_RECEITA if nome in existem and self._liberado(nome)
        ]
        if not liberados:
            return {}
        raiz = normal[: empresas.TAMANHO_DA_RAIZ]
        linha = empresas.retratos_de_empresa(
            self.porta, [raiz], como_era_em, tuple(liberados)
        ).get(raiz)
        if linha is None:
            return {}
        publico_em = pd.Timestamp(linha[empresas.PUBLICADO_EM]).date()
        servidos = {}
        for nome in liberados:
            valor = linha[nome]
            if pd.isna(valor):
                continue
            numero = int(valor) if nome == "n_estabelecimentos" else float(valor)
            servidos[nome] = campo(
                numero, fonte=empresas.FONTE, publico_em=publico_em, visto_em=None
            )
        return servidos

    def bloco(self, cnpj: str, como_era_em: date) -> tuple[dict[str, dict], set[str]]:
        """Os sinais que o portão libera e a base tem, e as fontes usadas; ({}, set()) sem nenhum."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        servidos = self._anatel(normal, como_era_em) | self._da_receita(
            normal, como_era_em
        )
        ordenados = {nome: servidos[nome] for nome in CAMPOS if nome in servidos}
        return ordenados, {envelope["fonte"] for envelope in ordenados.values()}
