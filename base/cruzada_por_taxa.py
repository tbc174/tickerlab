"""Conferência cruzada por taxa de acordo: a Receita contra outro órgão (exigência 6 da ADR 0027; D10.6 da 0108).

O CNPJ só a Receita publica, mas vários órgãos cadastram o mesmo CNPJ (ANATEL, ANVISA, ANCINE, Banco Central,
CVM). Aqui a conferência não é "número igual ao centavo" (`base/cruzada.py`) e sim **taxa de acordo**: de cada
100 CNPJs que existem nos dois lados, quantos têm a mesma UF, a mesma situação ou a mesma razão social. Cada
`ParPorTaxa` tem um **piso** escrito uma vez e **congelado**: medida abaixo do piso, a tabela não fecha; não se
mexe no piso para fechar.

Honestidade sobre a ordem: os pisos de 11/11/2026 (UF 95%, situação 90%, razão social 80%) foram propostos
**depois** de ver as primeiras medidas (UF 95,8% a 99,3%, situação 93,7%, razão social 82%), a poucos pontos
delas. Valem daqui para a frente sem ajuste.

Limite da prova: o par cobre só quem o outro órgão cadastra (companhias, instituições financeiras, concessões,
registros de produto), não é amostra dos ~21 milhões de CNPJs; MEI, empresário individual e pessoa física não
entram nas tabelas `_pj`.

Divergência vem **explicada, não só contada**: cada uma ganha uma causa pelas regras do par. A causa "não
explicado" acima de `MAXIMO_NAO_EXPLICADO` das divergências avisa a Diretoria antes de gravar a prontidão.

Só regra: as tabelas chegam em DataFrames (`scripts/conferir_receita.py` lê pela porta) e o resultado sai em
tipos simples, sem CNPJ nem nome.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from base.cruzada import OUTRO_ORGAO

PISO_DA_UF = 0.95
PISO_DA_SITUACAO = 0.90
PISO_DA_RAZAO_SOCIAL = 0.80
MAXIMO_NAO_EXPLICADO = (
    0.20  # acima disto das divergências, avisar antes de gravar a prontidão
)
NAO_EXPLICADO = "não explicado"
SEMELHANCA_MINIMA_DO_NOME = (
    0.6  # palavras em comum / palavras no total, sem as de forma jurídica
)
SEMELHANCA_DA_RENOMEACAO = 0.3
ANOS_DE_REGISTRO_ANTIGO = 2

LIMITE_DA_PROVA = (
    "O par cobre só os CNPJs que o outro órgão cadastra; não é amostra dos ~21 milhões de CNPJs. "
    "MEI, empresário individual e pessoa física não entram."
)

_FORMA_JURIDICA = re.compile(
    r"(?<![A-Z0-9])(S ?[./]? ?A|LTDA|CIA|COMPANHIA|DE|DA|DO|DAS|DOS|E|ME|EPP|EIRELI)(?![A-Z0-9])"
)


@dataclass(frozen=True)
class ParPorTaxa:
    nome: str
    descricao: str
    piso: float
    tabelas: tuple[str, ...]
    independencia: str = OUTRO_ORGAO
    limite: str = LIMITE_DA_PROVA
    # Regra: par cujo campo não é o que a tabela guarda (o nome do IF.data é o da instituição no Banco Central,
    # não a razão social) fica visível, com a causa aqui, mas nunca prova nem reprova a tabela.
    informativo: str = ""


@dataclass(frozen=True)
class RelatorioPorTaxa:
    par: str
    independencia: str
    piso: float
    comparadas: int
    concordam: int
    causas: dict[str, int] = field(default_factory=dict)  # das divergências, todas
    tabelas: tuple[str, ...] = ()
    limite: str = ""
    informativo: str = ""

    @property
    def taxa(self) -> float:
        return self.concordam / self.comparadas if self.comparadas else 0.0

    @property
    def aprovado(self) -> bool:
        return self.comparadas > 0 and self.taxa >= self.piso

    @property
    def divergentes(self) -> int:
        return self.comparadas - self.concordam

    @property
    def nao_explicado(self) -> float:
        total = self.divergentes
        return self.causas.get(NAO_EXPLICADO, 0) / total if total else 0.0

    @property
    def avisa_a_diretoria(self) -> bool:
        return self.nao_explicado > MAXIMO_NAO_EXPLICADO

    def como_dict(self) -> dict[str, object]:
        return {
            "nome": self.par,
            "independencia": self.independencia,
            "piso": self.piso,
            "comparadas": self.comparadas,
            "concordam": self.concordam,
            "taxa": round(self.taxa, 4),
            "aprovado": self.aprovado,
            "divergentes": self.divergentes,
            "causas": dict(self.causas),
            "nao_explicado": round(self.nao_explicado, 4),
            "avisa_a_diretoria": self.avisa_a_diretoria,
            "tabelas": list(self.tabelas),
            "limite": self.limite,
            "informativo": self.informativo,
        }


def palavras_do_nome(texto: object) -> set[str]:
    """As palavras que identificam a empresa: sem acento, sem pontuação e sem a forma jurídica."""
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode(
        "ascii", "ignore"
    )
    sem_forma = _FORMA_JURIDICA.sub(" ", sem_acento.decode().upper())
    return set(re.sub(r"[^A-Z0-9 ]", " ", sem_forma).split())


def semelhanca_do_nome(a: object, b: object) -> float:
    pa, pb = palavras_do_nome(a), palavras_do_nome(b)
    return len(pa & pb) / len(pa | pb) if pa | pb else 0.0


def nomes_concordam(a: object, b: object) -> bool:
    return semelhanca_do_nome(a, b) >= SEMELHANCA_MINIMA_DO_NOME


def _primeira_palavra(texto: object) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode(
        "ascii", "ignore"
    )
    sem_forma = _FORMA_JURIDICA.sub(" ", sem_acento.decode().upper())
    palavras = re.sub(r"[^A-Z0-9 ]", " ", sem_forma).split()
    return palavras[0] if palavras else ""


def _abrevia(curto: set[str], longo: set[str]) -> bool:
    """Cada palavra do nome curto é igual a uma do longo ou o começo dela ("ADM" de "ADMINISTRACAO")."""
    return bool(curto) and all(any(q.startswith(w) for q in longo) for w in curto)


def causa_do_nome(a: object, b: object) -> str:
    """Por que dois nomes do mesmo CNPJ não batem. Só classifica: não confirma que a causa é a verdadeira."""
    pa, pb = palavras_do_nome(a), palavras_do_nome(b)
    if "".join(sorted(pa)) == "".join(sorted(pb)) or "".join(sorted(pa)).replace(
        " ", ""
    ) == "".join(sorted(pb)):
        return "grafia"
    if semelhanca_do_nome(a, b) >= SEMELHANCA_DA_RENOMEACAO or pa <= pb or pb <= pa:
        return "renomeação ou abreviação"
    if _abrevia(*sorted((pa, pb), key=len)):
        return "renomeação ou abreviação"
    if _primeira_palavra(a) and _primeira_palavra(a) == _primeira_palavra(b):
        return "mesma marca, outra razão social (renomeação, conversão ou outra empresa do grupo)"
    return NAO_EXPLICADO


def causa_da_uf(
    uf_outro: str, ufs_da_raiz: set[str], idade_em_anos: float | None, situacao: str
) -> str:
    """Por que a UF do outro órgão difere da Receita: é a de outro estabelecimento da mesma raiz, o registro é
    antigo (mudança de sede provável) ou o estabelecimento não opera regularmente na Receita."""
    if uf_outro in ufs_da_raiz:
        return "o outro órgão registrou a UF de outro estabelecimento da mesma raiz"
    if idade_em_anos is not None and idade_em_anos >= ANOS_DE_REGISTRO_ANTIGO:
        return "registro antigo no outro órgão (mudança de sede provável)"
    if situacao and situacao != "02":
        return "estabelecimento sem operação regular na Receita"
    return NAO_EXPLICADO


def causa_da_situacao(situacao_receita: str, idade_em_anos: float | None) -> str:
    """Instituição ativa no Banco Central e não ativa na Receita."""
    if situacao_receita in {"03", "04"}:
        return "CNPJ suspenso ou inapto na Receita por pendência, instituição ainda autorizada"
    if idade_em_anos is not None and idade_em_anos >= 1:
        return "cadastro do Banco Central anterior à baixa na Receita"
    return NAO_EXPLICADO


def avaliar(par: ParPorTaxa, comparacao: pd.DataFrame) -> RelatorioPorTaxa:
    """`comparacao` tem uma linha por CNPJ nos dois lados, com `concorda` (bool) e, nas que não, `causa`."""
    concordam = int(comparacao["concorda"].sum())
    divergentes = comparacao.loc[~comparacao["concorda"].astype(bool), "causa"]
    return RelatorioPorTaxa(
        par=par.nome,
        independencia=par.independencia,
        piso=par.piso,
        comparadas=len(comparacao),
        concordam=concordam,
        causas=dict(Counter(divergentes.fillna(NAO_EXPLICADO))),
        tabelas=par.tabelas,
        limite=par.limite,
        informativo=par.informativo,
    )


_NOME_DO_IFDATA = (
    "o campo `instituicao` do IF.data é o nome da instituição no Banco Central (marca, sufixo como "
    '"- PRUDENCIAL", cooperativa por extenso), não a razão social: 58,9% em 11/11/2026, abaixo do piso. '
    "Não prova nem reprova a tabela"
)

PARES: tuple[ParPorTaxa, ...] = (
    ParPorTaxa(
        "uf_anatel_x_receita",
        "UF da outorga da ANATEL × UF do estabelecimento na Receita, por CNPJ",
        PISO_DA_UF,
        ("anatel_outorgas", "cnpj_estabelecimentos_pj"),
    ),
    ParPorTaxa(
        "uf_anvisa_x_receita",
        "UF do registro da ANVISA × UF do estabelecimento na Receita, por CNPJ",
        PISO_DA_UF,
        ("anvisa_registros", "cnpj_estabelecimentos_pj"),
    ),
    ParPorTaxa(
        "uf_ancine_x_receita",
        "UF do agente da ANCINE × UF do estabelecimento na Receita, por CNPJ",
        PISO_DA_UF,
        ("ancine_agentes", "cnpj_estabelecimentos_pj"),
    ),
    ParPorTaxa(
        "uf_ifdata_x_receita",
        "UF da instituição no IF.data (Banco Central) × UF da matriz na Receita, por raiz de CNPJ",
        PISO_DA_UF,
        ("ifdata_cadastro", "cnpj_estabelecimentos_pj"),
    ),
    ParPorTaxa(
        "situacao_ifdata_x_receita",
        "Instituição ativa no IF.data × matriz com situação ativa na Receita (a instituição inativa no BCB não "
        "entra: perder a autorização não baixa o CNPJ)",
        PISO_DA_SITUACAO,
        ("ifdata_cadastro", "cnpj_estabelecimentos_pj"),
    ),
    ParPorTaxa(
        "razao_social_cvm_x_receita",
        "Nome da companhia no cadastro da CVM (FCA) × razão social na Receita, por raiz de CNPJ",
        PISO_DA_RAZAO_SOCIAL,
        ("fca_geral", "cnpj_empresas_pj"),
    ),
    ParPorTaxa(
        "razao_social_ifdata_x_receita",
        "Nome da instituição no IF.data (Banco Central) × razão social na Receita, por raiz de CNPJ",
        PISO_DA_RAZAO_SOCIAL,
        ("ifdata_cadastro", "cnpj_empresas_pj"),
        informativo=_NOME_DO_IFDATA,
    ),
)
