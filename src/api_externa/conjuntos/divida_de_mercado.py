"""A dívida de mercado na ficha de crédito (linha 1126 da fila; bot Analista, simulação 7, 25/11/2026).

`LeitorDaDivida(porta, permitido).bloco(cnpj, como_era_em)` lista, cada lista no envelope com a fonte e o dia em que
ficou público, o que os informes mensais da CVM diziam da empresa no dia:

- `certificados_cra`, `certificados_cri` e `certificados_ots`: um certificado por item, com a securitizadora, os
  papéis da empresa (cedente, devedora) e o percentual do informe mais novo, o primeiro e o último mês em que ela
  aparece e se o certificado ainda estava no último informe que a securitizadora entregou;
- `lista_dos_fundos_em_que_cede`: cada FIDC que a lista entre os maiores cedentes nos 12 meses, pelo informe mais
  novo, com a instituição administradora (pessoa jurídica), a participação, a carteira e o crédito inadimplente.

São fatos dos informes, não saldo devedor nem opinião de crédito. Cada lista sai só se o portão a libera (conta
nossa sobre a fonte: derivado) e a base tem a tabela; o portão hoje a nega, porque as tabelas de securitização e do
FIDC não têm a prontidão do D10 (linhas 1132 e 1133 da fila), e o texto que a anuncia (`LIMITE`) sai só com ela.
O informe do FIDC traz o documento de outras cedentes, até de pessoa: daqui só sai o fundo e a instituição que o
administra, e só quando o documento dela tem 14 dígitos.
"""

import re
from dataclasses import dataclass
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base.porta import Porta
from base.porta.duckdb import condicao_como_era, dia_de, nome_da_view
from base.porta.rede import views
from src.api_externa.conjuntos import Permitido
from src.credito.sinais import informes_por_fundo

CEDENTE_DEVEDOR = "securitizacao_cedente_devedor"
CERTIFICADOS = "securitizacao_certificados"
FIDC = "fidc_informe"
FONTES_DOS_PRODUTOS = {
    "CRA": "cvm-cra",
    "CRI": "cvm-cri",
    "OTS": "cvm-securitizadoras-ots",
}
LIMITE = (
    "A dívida de mercado lista os CRA, CRI e outros títulos de securitização em que a empresa aparece como cedente "
    "ou devedora nos informes mensais da CVM, e os FIDC que a listam entre os maiores cedentes nos 12 meses: é "
    "fato dos informes, não saldo devedor; um título que não aparece não quer dizer que não exista."
)
CARTEIRA = "TAB_I2_VL_CARTEIRA"
# crédito inadimplente com aquisição substancial dos riscos (I2A) e sem (I2B): a carteira (I2) tem os dois
INADIMPLENTES = ("TAB_I2A3_VL_CRED_INAD", "TAB_I2B3_VL_CRED_INAD")
NOME_DO_FUNDO, ADMINISTRADORA, CNPJ_DA_ADMINISTRADORA = (
    "DENOM_SOCIAL",
    "ADMIN",
    "CNPJ_ADMIN",
)
DIGITOS_DE_EMPRESA = 14
CASAS_DA_RAZAO = 4


@dataclass(frozen=True)
class OrigemDaLista:
    """De que coleta e de que tabelas a lista sai (a mesma linha de direito que o portão julga)."""

    fonte: str
    tabelas: tuple[str, ...]


CAMPOS: dict[str, OrigemDaLista] = {
    **{
        f"certificados_{produto.lower()}": OrigemDaLista(
            fonte, (CEDENTE_DEVEDOR, CERTIFICADOS)
        )
        for produto, fonte in FONTES_DOS_PRODUTOS.items()
    },
    "lista_dos_fundos_em_que_cede": OrigemDaLista("cvm-fidc", (FIDC,)),
}


def _mes(valor: object) -> str | None:
    dia = pd.to_datetime(valor, errors="coerce")
    return None if pd.isna(dia) else dia.strftime("%Y-%m")


def _dia(valor: object) -> str | None:
    dia = pd.to_datetime(valor, errors="coerce")
    return None if pd.isna(dia) else dia.strftime("%Y-%m-%d")


def _numero(valor: object) -> float | None:
    numero = pd.to_numeric(valor, errors="coerce")
    return None if pd.isna(numero) else float(numero)


def _texto(valor: object) -> str | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    return str(valor).strip() or None


def _sem_vazios(item: dict[str, object]) -> dict[str, object]:
    return {chave: valor for chave, valor in item.items() if valor is not None}


class LeitorDaDivida:
    """Lê a dívida de mercado de uma empresa de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido) -> None:
        self.porta = porta
        self.permitido = permitido

    def _liberados(self) -> set[str]:
        existem = views(self.porta.con)
        return {
            nome
            for nome, origem in CAMPOS.items()
            if origem.tabelas[0] in existem and self.permitido(origem.fonte, nome, True)
        }

    def _consulta(
        self, tabela: str, onde: str, parametros: dict, resto: str = ""
    ) -> pd.DataFrame:
        condicao = condicao_como_era(self.porta.colunas(tabela), tabela)
        return self.porta.con.execute(
            f'SELECT * FROM "{nome_da_view(tabela)}" WHERE {condicao} AND ({onde}) {resto}',
            parametros,
        ).df()

    # --- certificados -----------------------------------------------------------------------------------

    def _linhas_da_empresa(
        self, formatado: str, dia: str, produtos: list[str]
    ) -> pd.DataFrame:
        """As linhas da empresa no quadro cedente e devedor, só a versão mais nova de cada mês."""
        return self._consulta(
            CEDENTE_DEVEDOR,
            "cnpj = $cnpj AND list_contains($produtos, produto)",
            {"dia": dia, "cnpj": formatado, "produtos": produtos},
            "QUALIFY row_number() OVER (PARTITION BY competencia, cnpj_securitizadora, codigo_certificado, papel "
            "ORDER BY versao DESC, publico_em DESC) = 1",
        )

    def _dos_certificados(
        self, codigos: list[str], securitizadoras: list[str], dia: str
    ) -> tuple[dict[tuple[str, str], dict], dict[str, str | None]]:
        """O informe mais novo de cada certificado (nome da securitizadora, emissão) e o último mês que cada
        securitizadora informou no dia."""
        if CERTIFICADOS not in views(self.porta.con):
            return {}, {}
        dados = self._consulta(
            CERTIFICADOS,
            "list_contains($codigos, codigo_certificado)",
            {"dia": dia, "codigos": codigos},
            "QUALIFY row_number() OVER (PARTITION BY cnpj_securitizadora, codigo_certificado "
            "ORDER BY competencia DESC, versao DESC) = 1",
        )
        ultimos = self._consulta(
            CERTIFICADOS, "list_contains($securitizadoras, cnpj_securitizadora)",
            {"dia": dia, "securitizadoras": securitizadoras},
        ).groupby("cnpj_securitizadora")["competencia"].max()  # fmt: skip
        por_certificado = {
            (str(linha["cnpj_securitizadora"]), str(linha["codigo_certificado"])): linha
            for linha in dados.to_dict(orient="records")
        }
        return por_certificado, {str(s): _mes(m) for s, m in ultimos.items()}

    @staticmethod
    def _um_certificado(
        linhas: pd.DataFrame, dados: dict, ultimo: str | None
    ) -> dict[str, object]:
        ultima = linhas["competencia"].max()
        do_ultimo_mes = linhas[linhas["competencia"] == ultima].sort_values("papel")
        primeira = linhas.iloc[0]
        ultimo_mes = _mes(ultima)
        return _sem_vazios({
            "codigo_certificado": _texto(primeira["codigo_certificado"]),
            "cnpj_securitizadora": _texto(primeira["cnpj_securitizadora"]),
            "securitizadora": _texto(dados.get("nome_securitizadora")),
            "data_emissao": _dia(dados.get("data_emissao")),
            "papeis": [
                {"papel": str(papel), "percentual": _numero(percentual)}
                for papel, percentual in zip(do_ultimo_mes["papel"], do_ultimo_mes["percentual"], strict=True)
            ],
            "primeiro_mes_com_a_empresa": _mes(linhas["competencia"].min()),
            "ultimo_mes_com_a_empresa": ultimo_mes,
            "meses": int(linhas["competencia"].nunique()),
            "no_ultimo_informe": None if ultimo is None else ultimo_mes == ultimo,
            "publico_em": _dia(linhas["publico_em"].max()),
        })  # fmt: skip

    def _certificados(
        self, formatado: str, dia: str, liberados: set[str]
    ) -> dict[str, dict]:
        produtos = [
            p for p in FONTES_DOS_PRODUTOS if f"certificados_{p.lower()}" in liberados
        ]
        if not produtos:
            return {}
        linhas = self._linhas_da_empresa(formatado, dia, produtos)
        if linhas.empty:
            return {}
        dados, ultimos = self._dos_certificados(
            sorted({str(c) for c in linhas["codigo_certificado"]}),
            sorted({str(s) for s in linhas["cnpj_securitizadora"]}),
            dia,
        )
        listas: dict[str, list[dict]] = {}
        for (securitizadora, codigo, produto), grupo in linhas.groupby(
            ["cnpj_securitizadora", "codigo_certificado", "produto"], sort=False
        ):
            chave = (str(securitizadora), str(codigo))
            listas.setdefault(str(produto), []).append(
                self._um_certificado(grupo, dados.get(chave, {}), ultimos.get(chave[0]))
            )
        return {
            f"certificados_{produto.lower()}": _envelope(
                sorted(lista, key=lambda c: (str(c.get("ultimo_mes_com_a_empresa")), str(c.get("codigo_certificado"))),
                       reverse=True),
                FONTES_DOS_PRODUTOS[produto],
            )
            for produto, lista in listas.items()
        }  # fmt: skip

    # --- FIDC ----------------------------------------------------------------------------------------------

    @staticmethod
    def _um_fundo(linha: dict) -> dict[str, object]:
        carteira = _numero(linha.get(CARTEIRA))
        partes = [_numero(linha.get(coluna)) for coluna in INADIMPLENTES]
        presentes = [parte for parte in partes if parte is not None]
        inadimplente = sum(presentes) if presentes else None
        cnpj_da_administradora = re.sub(
            r"\D", "", str(linha.get(CNPJ_DA_ADMINISTRADORA) or "")
        )
        e_empresa = len(cnpj_da_administradora) == DIGITOS_DE_EMPRESA
        participacao = _numero(linha.get("participacao"))
        return _sem_vazios({
            "cnpj_fundo": _texto(linha.get("cnpj_fundo")),
            "nome_do_fundo": _texto(linha.get(NOME_DO_FUNDO)),
            # a instituição só quando o documento dela é de empresa: nunca o nome de uma pessoa
            "instituicao_administradora": _texto(linha.get(ADMINISTRADORA)) if e_empresa else None,
            "cnpj_da_instituicao_administradora": (
                cnpj_.formatar(cnpj_da_administradora) if e_empresa else None
            ),
            "competencia": _mes(linha.get("competencia")),
            "participacao_como_cedente": None if participacao is None else round(participacao, CASAS_DA_RAZAO),
            "carteira_do_fundo": carteira,
            "credito_inadimplente": inadimplente,
            "inadimplente_sobre_carteira": (
                round(inadimplente / carteira, CASAS_DA_RAZAO) if carteira and inadimplente is not None else None
            ),
            "publico_em": _dia(linha.get("publico_em")),
        })  # fmt: skip

    def _fundos(
        self, formatado: str, como_era_em: date, liberados: set[str]
    ) -> dict[str, dict]:
        if "lista_dos_fundos_em_que_cede" not in liberados:
            return {}
        fundos = informes_por_fundo(self.porta, formatado, como_era_em)
        if fundos is None or fundos.empty:
            return {}
        lista = [self._um_fundo(linha) for linha in fundos.to_dict(orient="records")]
        lista.sort(
            key=lambda f: (
                -(f.get("inadimplente_sobre_carteira") or 0),
                str(f.get("cnpj_fundo")),
            )
        )
        return {
            "lista_dos_fundos_em_que_cede": _envelope(
                lista, CAMPOS["lista_dos_fundos_em_que_cede"].fonte
            )
        }

    def bloco(self, cnpj: str, como_era_em: date) -> tuple[dict[str, dict], set[str]]:
        """As listas que o portão libera e que têm algum item, e as fontes usadas; ({}, set()) sem nenhuma. Quem
        chama já barrou pessoa (a ficha de crédito só chega aqui com o CNPJ de empresa)."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        liberados = self._liberados()
        if not liberados:
            return {}, set()
        formatado = cnpj_.formatar(normal)
        servidas = self._certificados(
            formatado, dia_de(como_era_em), liberados
        ) | self._fundos(formatado, como_era_em, liberados)
        ordenadas = {nome: servidas[nome] for nome in CAMPOS if nome in servidas}
        return ordenadas, {envelope["fonte"] for envelope in ordenadas.values()}


def _envelope(lista: list[dict], fonte: str) -> dict:
    """A lista no envelope, com o dia em que o item mais novo ficou público."""
    return {
        "valor": lista,
        "fonte": fonte,
        "publico_em": max(str(item["publico_em"]) for item in lista),
        "visto_em": None,
    }
