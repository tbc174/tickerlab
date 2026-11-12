"""Conferência de que uma tabela só tem raiz de CNPJ de pessoa jurídica (linha 789, ADR 0075).

Algumas tabelas não têm a marca de pessoa por linha (`linhas_de_pessoa`) e não filtram a pessoa na
montagem, mas só falam de quem tem registro na CVM ou no BCB. A prova de que não carregam pessoa é cruzar
cada raiz (oito primeiros dígitos do CNPJ) com a `cnpj_empresas_pj`, que a montagem já limpa do
empresário individual (natureza 213-5) e do grupo 4 de natureza. Raiz que não está lá é tratada como
possível pessoa: a tabela fica vermelha e não entra na lista `SEM_PESSOA_PELA_RAIZ`.

Alcance: prova que **quem a linha descreve** é pessoa jurídica. Não cobre texto livre (o assunto de um
evento, por exemplo). Um CNPJ sem os 14 dígitos conta como fora (zero à esquerda perdido deslocaria a raiz).

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
}


class Cruzamento(NamedTuple):
    """Quantas raízes distintas a tabela tem e quantas não estão na `cnpj_empresas_pj`."""

    tabela: str
    raizes: int
    fora_da_pj: int

    @property
    def sem_pessoa(self) -> bool:
        return self.raizes > 0 and self.fora_da_pj == 0


def cruzar(porta: Porta, tabela: str, coluna: str) -> Cruzamento:
    """Cruza as raízes de `tabela.coluna` com a `cnpj_empresas_pj` da mesma base."""
    vista = porta._view(tabela, None)
    pj = porta._view(TABELA_PJ, None)
    digitos = rf"""regexp_replace(cast("{coluna}" as varchar), '\D', '', 'g')"""
    # CNPJ sem os 14 dígitos (zeros à esquerda perdidos, lixo) não vale: conta como fora, o lado seguro
    raiz = f"CASE WHEN length({digitos}) = 14 THEN left({digitos}, 8) ELSE '?' END"
    total, fora = porta.con.execute(
        f"""
        WITH raizes AS (SELECT DISTINCT {raiz} AS r FROM "{vista}" WHERE "{coluna}" IS NOT NULL),
        pj AS (SELECT DISTINCT cast(cnpj_basico AS varchar) AS r FROM "{pj}")
        SELECT count(*), count(*) FILTER (WHERE pj.r IS NULL)
        FROM raizes LEFT JOIN pj USING (r)
        """
    ).fetchone()
    return Cruzamento(tabela, int(total), int(fora))


def cruzar_todas(porta: Porta) -> list[Cruzamento]:
    return [
        cruzar(porta, nome, coluna) for nome, coluna in SEM_PESSOA_PELA_RAIZ.items()
    ]
