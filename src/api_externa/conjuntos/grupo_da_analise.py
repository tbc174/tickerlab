"""Grupo PJ da análise (Fila 1036): QSA nos dois sentidos, sem presumir controle.

A cadeia usa apenas entradas já públicas e empresas da lista sem pessoa. Abertura
e atividade passam pelo portão do cadastro; os vínculos, pelo de sócios PJ. Limite
e profundidade são explícitos: um recorte nunca se apresenta como grupo completo.
"""

import re
from datetime import date

import pandas as pd

from base.cnpj import TAMANHO_DA_RAIZ
from base.porta import Porta
from src.api_externa.conjuntos import Permitido, Servido, empresas, ficha, socios_pj
from src.api_externa.envelope import campo

PROFUNDIDADE = 3
CAMPOS_DO_CADASTRO = ("data_inicio_atividade", "cnae_principal")
LIMITE_DO_GRUPO = (
    "O grupo segue sócias e participações PJ da Receita nos dois sentidos, até três ligações e o limite de "
    "empresas da resposta. Participação no QSA não prova controle. Grupo incompleto tem conferências parciais."
)


class LeitorDeGrupo(socios_pj.LeitorDeSociosPj):
    """Amplia o quadro direto com as empresas alcançadas, sem repetir ciclos."""

    def _vizinhas(self, raiz: str, dia: date) -> list[dict]:
        if not all(self.permitido(f, c, False) for f, c in socios_pj.CAMPOS):
            return []
        quadro = pd.concat(
            [
                self._quadro("cnpj_basico", raiz, dia),
                self._quadro("raiz_socio_pj", raiz, dia),
            ]
        ).drop_duplicates()
        outras = {
            str(r)
            for r in (*quadro["empresa"], *quadro["socia"])
            if re.fullmatch(r"[0-9A-Z]{8}", str(r))
        }
        nomes = empresas.retratos_de_empresa(self.porta, outras, dia, ("razao_social",))
        return [
            l
            for l in quadro.to_dict("records")
            if l["empresa"] in nomes and l["socia"] in nomes
        ]

    def _rede(self, raiz: str, dia: date) -> tuple[dict[str, int], list[dict], bool]:
        passos = {raiz: 0}
        camada = [raiz]
        vistas: dict[tuple[str, str], dict] = {}
        for passo in range(PROFUNDIDADE + 1):
            novas: set[str] = set()
            for atual in camada:
                for linha in self._vizinhas(atual, dia):
                    vistas[(linha["socia"], linha["empresa"])] = linha
                    novas.update({linha["empresa"], linha["socia"]} - passos.keys())
            if passo == PROFUNDIDADE:
                break
            camada = sorted(novas)[: max(self.linhas_maximas - len(passos), 0)]
            passos.update(dict.fromkeys(camada, passo + 1))
            if not camada:
                break
        dentro = [
            l for (s, e), l in sorted(vistas.items()) if s in passos and e in passos
        ]
        return passos, dentro, len(dentro) == len(vistas)

    def grupo(self, cnpj: str, dia: date, permitido_cadastro: Permitido) -> dict:
        """Empresas, abertura, atividade e ligações datadas; nunca lê pessoa física."""
        passos, ligacoes, completo = self._rede(cnpj[:TAMANHO_DA_RAIZ], dia)
        nomes = empresas.retratos_de_empresa(self.porta, passos, dia, ("razao_social",))
        cadastros = _cadastros(self.porta, passos, dia, permitido_cadastro)
        return {
            "empresas": [
                {
                    "raiz_do_cnpj": raiz,
                    "passos": passos[raiz],
                    "razao_social": campo(
                        str(nome["razao_social"]),
                        fonte=empresas.FONTE,
                        publico_em=pd.Timestamp(nome["publico_em"]).date(),
                        visto_em=None,
                    ),
                    **cadastros.get(raiz, {}),
                }
                for raiz, nome in sorted(
                    nomes.items(), key=lambda item: (passos[item[0]], item[0])
                )
            ],
            "ligacoes": [_ligacao(l) for l in ligacoes],
            "completo": completo,
            "profundidade": PROFUNDIDADE,
        }


def _ligacao(linha: dict) -> dict:
    entrada = linha["data_entrada"]
    return {
        "socia": linha["socia"],
        "empresa_do_vinculo": linha["empresa"],
        "data_entrada": campo(
            None if pd.isna(entrada) else pd.Timestamp(entrada).date().isoformat(),
            fonte=empresas.FONTE,
            publico_em=pd.Timestamp(linha["publico_em"]).date(),
            visto_em=None,
        ),
    }


def _cadastros(
    porta: Porta, raizes: dict[str, int], dia: date, permitido: Permitido
) -> dict[str, dict]:
    campos = [c for c in CAMPOS_DO_CADASTRO if permitido(empresas.FONTE, c, False)]
    mes = (
        ficha.LeitorDeFicha(porta, permitido)._retrato_do_estabelecimento(dia)
        if campos
        else None
    )
    if mes is None:
        return {}
    tabela = porta.ler(
        ficha.TABELA_DO_ESTABELECIMENTO,
        como_era_em=dia,
        filtros={empresas.RAIZ: list(raizes), empresas.MES: mes, "matriz": True},
        colunas=[empresas.RAIZ, *campos, empresas.PUBLICADO_EM],
    )
    return {
        str(raiz): {
            c: campo(
                _valor_cadastral(c, linhas.iloc[0][c]),
                fonte=empresas.FONTE,
                publico_em=pd.Timestamp(linhas.iloc[0][empresas.PUBLICADO_EM]).date(),
                visto_em=None,
            )
            for c in campos
        }
        for raiz, linhas in tabela.groupby(empresas.RAIZ, sort=True)
        if len(linhas) == 1
    }


def _valor_cadastral(nome: str, valor: object) -> str | None:
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    return (
        pd.Timestamp(valor).date().isoformat()
        if nome == "data_inicio_atividade"
        else str(valor)
    )  # type: ignore[arg-type]


def ampliar(
    socios: Servido,
    porta: Porta,
    permitido: Permitido,
    permitido_cadastro: Permitido,
    linhas: int,
    cnpj: str,
    dia: date,
) -> socios_pj.SociosServidos:
    """Mantém as listas diretas e acrescenta o grupo, com fonte, limites e consumo."""
    grupo = LeitorDeGrupo(porta, permitido, linhas).grupo(cnpj, dia, permitido_cadastro)
    return socios_pj.SociosServidos(
        socios.corpo
        | {
            "grupo": grupo,
            "limites": [*socios.corpo.get("limites", []), LIMITE_DO_GRUPO],
        },
        socios.fontes,
        socios.linhas + len(grupo["empresas"]) + len(grupo["ligacoes"]),
    )
