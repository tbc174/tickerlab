"""Grupo PJ da análise (Fila 1036): ascendentes e participadas diretas da alvo.

A cadeia usa apenas entradas já públicas e empresas da lista sem pessoa. Abertura
e atividade passam pelo portão do cadastro; os vínculos, pelo de sócios PJ. Limite
e profundidade são explícitos: um recorte nunca se apresenta como grupo completo.
"""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base.cnpj import TAMANHO_DA_RAIZ
from base.porta import Porta
from base.porta.duckdb import dia_de
from base.rede.entidades import EMPRESARIO_INDIVIDUAL, GRUPO_DAS_PESSOAS_FISICAS
from src.api_externa.conjuntos import Permitido, Servido, empresas, ficha, socios_pj
from src.api_externa.envelope import campo

PROFUNDIDADE = 3
LIGACOES_POR_EMPRESA = 3
COLUNAS_DO_QUADRO = ("empresa", "socia", "data_entrada", "publico_em")
CAMPOS_DO_CADASTRO = ("data_inicio_atividade", "cnae_principal")
LIMITE_DO_GRUPO = (
    "A composição do grupo é dedução: alvo, sócias PJ ascendentes até três níveis e participadas diretas da alvo. "
    "Não inclui irmãs nem coinvestidoras. Holding indica o papel neste recorte, não controle comprovado. "
    "O corte prioriza holdings de nível 1, 2 e 3, depois participadas diretas; dentro do nível, entradas mais "
    "recentes primeiro. Há até três ligações por vaga de empresa; grupo incompleto tem conferências parciais."
)


@dataclass
class _Composicao:
    limite: int
    empresas: dict[str, dict]
    ligacoes: dict[tuple[str, str], dict] = field(default_factory=dict)
    completa: bool = True

    def adicionar(
        self, quadro: pd.DataFrame, outra: str, nivel: int, papel: str
    ) -> list[str]:
        teto = self.limite * LIGACOES_POR_EMPRESA
        self.completa &= len(quadro) <= teto
        novas = []
        for linha in quadro.head(teto).to_dict("records"):
            raiz = str(linha[outra])
            chave = (linha["socia"], linha["empresa"])
            if chave in self.ligacoes:
                continue
            if len(self.ligacoes) >= teto or (
                raiz not in self.empresas and len(self.empresas) >= self.limite
            ):
                self.completa = False
                continue
            if raiz not in self.empresas:
                self.empresas[raiz] = {"passos": nivel, "papel": papel}
                novas.append(raiz)
            self.ligacoes[chave] = linha
        return novas


class LeitorDeGrupo(socios_pj.LeitorDeSociosPj):
    """Lê camadas ascendentes e só as participadas da alvo, com memória por pedido."""

    def __init__(self, porta: Porta, permitido: Permitido, linhas_maximas: int) -> None:
        super().__init__(porta, permitido, max(linhas_maximas, 1))
        self._camadas: dict[tuple[str, tuple[str, ...], date], pd.DataFrame] = {}

    def _camada(self, coluna: str, raizes: list[str], dia: date) -> pd.DataFrame:
        if coluna not in ("cnpj_basico", "raiz_socio_pj"):
            raise ValueError("Direção inválida do quadro societário")
        if not all(self.permitido(f, c, False) for f, c in socios_pj.CAMPOS):
            return pd.DataFrame(columns=list(COLUNAS_DO_QUADRO))
        chave = (coluna, tuple(raizes), dia)
        if chave not in self._camadas:
            self._camadas[chave] = self._ler_camada(coluna, raizes, dia)
        return self._camadas[chave]

    def _ler_camada(self, coluna: str, raizes: list[str], dia: date) -> pd.DataFrame:
        mes = empresas.mes_do_retrato_publico(self.porta, dia)
        if mes is None:
            return pd.DataFrame(columns=list(COLUNAS_DO_QUADRO))
        # Filtra as duas pontas antes do LIMIT: pessoa, duplicata ou raiz ausente não ocupa vaga de PJ.
        return self.porta.con.execute(
            "WITH quadro AS ("
            "SELECT cnpj_basico AS empresa, raiz_socio_pj AS socia, data_entrada, publico_em "
            f"FROM {socios_pj._view(socios_pj.ENTRADAS)} WHERE movimento IN ('entrou', 'saiu') "
            f"AND {coluna} IN (SELECT unnest($raizes)) AND raiz_socio_pj <> cnpj_basico "
            "AND publico_em <= CAST($dia AS DATE) "
            "QUALIFY row_number() OVER (PARTITION BY cnpj_basico, raiz_socio_pj "
            "ORDER BY mes_do_retrato DESC, movimento = 'saiu' DESC) = 1 AND movimento = 'entrou'), "
            "elegiveis AS (SELECT cnpj_basico "
            f"FROM {socios_pj._view(empresas.LISTA_DE_EMPRESAS)} "
            "WHERE mes_do_retrato = $mes AND publico_em <= CAST($dia AS DATE) "
            "AND cnpj_basico IN (SELECT empresa FROM quadro UNION SELECT socia FROM quadro) "
            "GROUP BY cnpj_basico HAVING count(*) = 1 AND bool_and("
            "natureza_juridica IS NOT NULL AND trim(CAST(natureza_juridica AS VARCHAR)) <> '' "
            "AND trim(CAST(natureza_juridica AS VARCHAR)) <> $empresario "
            "AND NOT starts_with(trim(CAST(natureza_juridica AS VARCHAR)), $pessoa))) "
            "SELECT q.* FROM quadro q JOIN elegiveis e ON e.cnpj_basico = q.empresa "
            "JOIN elegiveis s ON s.cnpj_basico = q.socia "
            "WHERE regexp_full_match(q.empresa, '[0-9A-Z]{8}') AND regexp_full_match(q.socia, '[0-9A-Z]{8}') "
            "ORDER BY data_entrada DESC NULLS LAST, publico_em DESC, socia DESC, empresa DESC LIMIT $limite",
            {
                "raizes": raizes,
                "dia": dia_de(dia),
                "mes": mes,
                "empresario": EMPRESARIO_INDIVIDUAL,
                "pessoa": GRUPO_DAS_PESSOAS_FISICAS,
                "limite": self.linhas_maximas * LIGACOES_POR_EMPRESA + 1,
            },
        ).df()

    def _rede(self, raiz: str, dia: date) -> _Composicao:
        rede = _Composicao(self.linhas_maximas, {raiz: {"passos": 0, "papel": "alvo"}})
        camada = [raiz]
        for nivel in range(1, PROFUNDIDADE + 1):
            quadro = self._camada("cnpj_basico", camada, dia)
            camada = rede.adicionar(quadro, "socia", nivel, f"holding nível {nivel}")
            if not camada:
                break
        # A camada seguinte só detecta o corte; não acrescenta empresas além da profundidade.
        if camada and not self._camada("cnpj_basico", camada, dia).empty:
            rede.completa = False
        rede.adicionar(
            self._camada("raiz_socio_pj", [raiz], dia),
            "empresa",
            1,
            "participada direta",
        )
        return rede

    def grupo(self, cnpj: str, dia: date, permitido_cadastro: Permitido) -> dict:
        """Empresas, abertura, atividade e ligações datadas; nunca lê pessoa física."""
        rede = self._rede(cnpj[:TAMANHO_DA_RAIZ], dia)
        passos = {r: item["passos"] for r, item in rede.empresas.items()}
        nomes = empresas.retratos_de_empresa(self.porta, passos, dia, ("razao_social",))
        cadastros = _cadastros(self.porta, passos, dia, permitido_cadastro)
        return {
            "empresas": [
                {
                    "raiz_do_cnpj": raiz,
                    **rede.empresas[raiz],
                    "razao_social": campo(
                        str(nome["razao_social"]),
                        fonte=empresas.FONTE,
                        publico_em=pd.Timestamp(nome["publico_em"]).date(),
                        visto_em=None,
                    ),
                    **cadastros.get(raiz, {}),
                }
                for raiz in rede.empresas
                if (nome := nomes.get(raiz)) is not None
            ],
            "ligacoes": [_ligacao(l) for l in rede.ligacoes.values()],
            "completo": rede.completa,
            "profundidade": PROFUNDIDADE,
            "tipo": "inference",
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
    leitor: LeitorDeGrupo,
    permitido_cadastro: Permitido,
    cnpj: str,
    dia: date,
) -> socios_pj.SociosServidos:
    """Mantém as listas diretas e acrescenta o grupo, com fonte, limites e consumo."""
    grupo = leitor.grupo(cnpj, dia, permitido_cadastro)
    return socios_pj.SociosServidos(
        socios.corpo
        | {
            "grupo": grupo,
            "limites": [*socios.corpo.get("limites", []), LIMITE_DO_GRUPO],
        },
        socios.fontes,
        socios.linhas + len(grupo["empresas"]) + len(grupo["ligacoes"]),
    )
