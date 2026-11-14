"""Conferência de que uma tabela só tem raiz de CNPJ de pessoa jurídica (linha 789, ADR 0075).

Algumas tabelas não têm a marca de pessoa por linha (`linhas_de_pessoa`) e não filtram a pessoa na
montagem, mas só falam de quem tem registro na CVM ou no BCB. A prova de que não carregam pessoa é cruzar
cada raiz (oito primeiros dígitos do CNPJ) com a `cnpj_empresas_pj`, que a montagem já limpa do
empresário individual (natureza 213-5) e do grupo 4 de natureza. Raiz que não está lá é tratada como
possível pessoa: a tabela fica vermelha e não entra na lista `SEM_PESSOA_PELA_RAIZ`.

Alcance: prova que **quem a linha descreve** é pessoa jurídica. Não cobre texto livre (o assunto de um
evento, por exemplo). Um CNPJ fora da forma de 14 caracteres conta como fora (zero à esquerda perdido deslocaria
a raiz). A forma é a de `base/cnpj.py::FORMA`: 12 posições de `0-9A-Z` e 2 dígitos, pois desde julho de 2026 a
Receita dá CNPJ alfanumérico (IN RFB 2.229/2024); tirar tudo o que não é dígito cortaria a raiz errada.

Só conta quantas raízes ficaram de fora; nunca devolve a raiz (pode ser pessoa).
"""

from typing import NamedTuple

from base.porta import Porta

TABELA_PJ = "cnpj_empresas_pj"

# tabela → coluna com o CNPJ (ou a raiz) de quem a linha descreve
SEM_PESSOA_PELA_RAIZ: dict[str, str] = {
    "rotulos_atraso": "cnpj",
    "eventos": "cnpj",
    "fca_geral": "cnpj",
    "demonstracoes_como_era": "cnpj",
    "carteiras_dos_fundos": "cnpj_fundo",
    "aneel_samp": "cnpj",
    "anp_concessionarios": "cnpj",
    "fips_registrados": "CNPJ_Fundo",
    "cnpj_situacao_cadastral": "cnpj",
}

# tabela → coluna com a raiz já separada: a raiz do texto do CNPJ tem de ser igual a ela
RAIZ_SEPARADA: dict[str, str] = {"cnpj_situacao_cadastral": "cnpj_basico"}


class Cruzamento(NamedTuple):
    """Quantas raízes distintas a tabela tem e quantas não estão na `cnpj_empresas_pj`."""

    tabela: str
    raizes: int
    fora_da_pj: int
    raiz_diferente: int = (
        0  # linhas em que a raiz do texto não é a da coluna de raiz (`RAIZ_SEPARADA`)
    )

    @property
    def sem_pessoa(self) -> bool:
        return self.raizes > 0 and self.fora_da_pj == 0 and self.raiz_diferente == 0


def cruzar(porta: Porta, tabela: str, coluna: str) -> Cruzamento:
    """Cruza as raízes de `tabela.coluna` com a `cnpj_empresas_pj` da mesma base."""
    vista = porta._view(tabela, None)
    pj = porta._view(TABELA_PJ, None)
    # só a pontuação sai (o CNPJ alfanumérico tem letras): tirar o que não é dígito cortaria a raiz errada
    limpo = f"""upper(regexp_replace(cast("{coluna}" as varchar), '[^0-9A-Za-z]', '', 'g'))"""
    # CNPJ fora da forma (zeros à esquerda perdidos, lixo) não vale: conta como fora, o lado seguro
    raiz = f"CASE WHEN regexp_matches({limpo}, '^[0-9A-Z]{{12}}[0-9]{{2}}$') THEN left({limpo}, 8) ELSE '?' END"
    total, fora = porta.con.execute(
        f"""
        WITH raizes AS (SELECT DISTINCT {raiz} AS r FROM "{vista}" WHERE "{coluna}" IS NOT NULL),
        pj AS (SELECT DISTINCT cast(cnpj_basico AS varchar) AS r FROM "{pj}")
        SELECT count(*), count(*) FILTER (WHERE pj.r IS NULL)
        FROM raizes LEFT JOIN pj USING (r)
        """
    ).fetchone()
    diferente = _raiz_diferente(porta, vista, tabela, limpo)
    return Cruzamento(tabela, int(total), int(fora), diferente)


def _raiz_diferente(porta: Porta, vista: str, tabela: str, limpo: str) -> int:
    """Linhas em que a raiz do texto do CNPJ não é a da coluna de raiz da mesma tabela (0 sem coluna de raiz)."""
    separada = RAIZ_SEPARADA.get(tabela)
    if separada is None:
        return 0
    (n,) = porta.con.execute(
        f"""SELECT count(*) FROM "{vista}"
        WHERE left({limpo}, 8) IS DISTINCT FROM upper(cast("{separada}" AS varchar))"""
    ).fetchone()
    return int(n)


# cópias montadas só no envio ao VPS: não ficam no acervo de casa, a prova delas é a trava
# `recorte_dos_compradores.conferir_reduzidas` sobre a cópia montada
SO_NA_COPIA_DO_ENVIO = frozenset({"fips_registrados"})


def cruzar_todas(porta: Porta) -> list[Cruzamento]:
    """Uma contagem por tabela de `SEM_PESSOA_PELA_RAIZ` que existe nesta base (as cópias do envio ficam de fora)."""
    return [
        cruzar(porta, nome, coluna)
        for nome, coluna in SEM_PESSOA_PELA_RAIZ.items()
        if nome not in SO_NA_COPIA_DO_ENVIO
    ]
