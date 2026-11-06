"""Concessionários da ANP (série T, PR T8): quem tem cada contrato de exploração e produção de petróleo
e gás, com a participação de cada sócio do consórcio e a marca de quem opera.

O arquivo (`relacao-concessionarios.csv`) é a foto de hoje, sem data própria (captura de 14/10/2026):
cada coleta é uma foto, e a linha vale desde o dia da coleta que a trouxe (`disponivel_em`, posta pela
carga; o leitor deixa vazio). Mudança de sócio ou de operador entra como linha nova, com o dia em que foi
vista (`base/setoriais/revisoes.py`); o que mudou antes da primeira coleta não aparece.

A fonte traz o CNPJ do sócio (sem o zero à esquerda, que o leitor recoloca) e o nome com o prefixo
"(Operador) - " na linha de quem opera. A ligação à empresa é pelo CNPJ (`cnpj`), sem comparar nomes.
"""

import io

import pandas as pd

from base.controladas import cnpj14
from base.setoriais.comum import sem_espacos

FONTE = "anp-concessionarios"
CODIFICACAO = "latin-1"
PREFIXO_DO_OPERADOR = "(Operador) - "
COLUNAS = (
    "bid", "numero_do_contrato", "fase", "nome_fantasia", "bacia", "cnpj", "empresa", "operador",
    "participacao_pct", "ambiente", "disponivel_em",
)  # fmt: skip
CHAVE = ("numero_do_contrato", "cnpj")
CARIMBOS: tuple[str, ...] = ()
TEXTOS = {
    "BID": "bid", "Número Contrato": "numero_do_contrato", "Fase": "fase",
    "Nome Fantasia": "nome_fantasia", "Bacia": "bacia", "Ambiente": "ambiente",
}  # fmt: skip
CASAS_DO_CNPJ = 14


def destino(url: str) -> str | None:
    return "concessionarios" if url.endswith("/relacao-concessionarios.csv") else None


def _cnpj(coluna: pd.Series) -> pd.Series:
    """O CNPJ com 14 dígitos: a fonte perde o zero à esquerda (`4054366000102`)."""
    return coluna.str.strip().str.zfill(CASAS_DO_CNPJ).map(cnpj14)


def ler(conteudo: bytes) -> pd.DataFrame:
    """O CSV da ANP; `disponivel_em` fica vazio (a carga põe o dia da coleta)."""
    bruto = pd.read_csv(
        io.BytesIO(conteudo),
        sep=";",
        dtype=str,
        encoding=CODIFICACAO,
        keep_default_na=False,
    )
    bruto.columns = [c.strip() for c in bruto.columns]
    tabela = pd.DataFrame(
        {
            novo: sem_espacos(bruto[velho], vazio_vira_none=True)
            for velho, novo in TEXTOS.items()
        }
    )
    nome = bruto["Nome"].str.strip()
    tabela["cnpj"] = _cnpj(bruto["CNPJ"])
    tabela["operador"] = nome.str.startswith(PREFIXO_DO_OPERADOR)
    tabela["empresa"] = nome.str.removeprefix(PREFIXO_DO_OPERADOR)
    tabela["participacao_pct"] = pd.to_numeric(
        bruto["% Participação"].str.replace(",", ".", regex=False), errors="coerce"
    ).astype(float)
    tabela["disponivel_em"] = pd.NaT
    tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"])
    return tabela.reindex(columns=list(COLUNAS))
