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

Tabela que guarda só a raiz (`SO_A_RAIZ`): a forma é a de 8 posições de `0-9A-Z`, e uma segunda coluna de CNPJ
de quem a linha descreve (`OUTRA_COLUNA`) entra no mesmo cruzamento. A linha sem nenhuma das duas (entidade só
pelo nome, sem ligação) não tem prova de ser pessoa jurídica: conta em `sem_documento` e reprova a tabela, a
leitura mais estreita. A `empresa_serie` tem esse formato; medida em 16/11/2026, reprovou e não está na lista
de cima (o conserto é a linha 960): `cruzar(porta, "empresa_serie", "raiz")` a mede de novo.

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
    "fre_comites": "cnpj",
    "fre_distribuicao_capital": "cnpj",
    "fre_diversidade": "cnpj",
    "fre_empregados": "cnpj",
    "fre_remuneracao_extremos": "cnpj",
    "pareceres_dfp": "cnpj",
    "pareceres_itr": "cnpj",
    "emissores": "cnpj",
    "debentures_assembleias": "cnpj",
    "processos_nas_notas": "cnpj",
}

# tabela → coluna que já é a raiz (8 posições): não há o CNPJ inteiro para conferir a forma
SO_A_RAIZ: dict[str, str] = {"empresa_serie": "raiz"}

# tabela → outra coluna com o CNPJ (14) de quem a linha descreve, cruzada junto com a de cima
OUTRA_COLUNA: dict[str, str] = {"empresa_serie": "cnpj_companhia"}

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
    sem_documento: int = (
        0  # linhas de `SO_A_RAIZ` sem raiz nem a outra coluna: nada prova que é PJ
    )

    @property
    def sem_pessoa(self) -> bool:
        return (
            self.raizes > 0
            and self.fora_da_pj == 0
            and self.raiz_diferente == 0
            and self.sem_documento == 0
        )


def _limpo(coluna: str) -> str:
    """O texto da coluna sem pontuação, em maiúsculas (o CNPJ alfanumérico tem letras)."""
    # só a pontuação sai: tirar o que não é dígito cortaria a raiz errada
    return f"""upper(regexp_replace(cast("{coluna}" as varchar), '[^0-9A-Za-z]', '', 'g'))"""


def _raiz(coluna: str, *, so_a_raiz: bool) -> str:
    """A raiz de 8 posições da coluna; '?' quando o texto está fora da forma (conta como fora, o lado seguro)."""
    limpo = _limpo(coluna)
    if so_a_raiz:
        return f"CASE WHEN regexp_matches({limpo}, '^[0-9A-Z]{{8}}$') THEN {limpo} ELSE '?' END"
    # CNPJ fora da forma (zeros à esquerda perdidos, lixo) não vale
    return f"CASE WHEN regexp_matches({limpo}, '^[0-9A-Z]{{12}}[0-9]{{2}}$') THEN left({limpo}, 8) ELSE '?' END"


def _preenchida(coluna: str) -> str:
    return f"""nullif(trim(cast("{coluna}" as varchar)), '') IS NOT NULL"""


def cruzar(porta: Porta, tabela: str, coluna: str) -> Cruzamento:
    """Cruza as raízes de `tabela.coluna` com a `cnpj_empresas_pj` da mesma base."""
    vista = porta._view(tabela, None)
    pj = porta._view(TABELA_PJ, None)
    so_a_raiz = tabela in SO_A_RAIZ
    outra = OUTRA_COLUNA.get(tabela)
    # na tabela de `SO_A_RAIZ`, a raiz em branco é falta de documento (`sem_documento`), não raiz de fora
    filtro = _preenchida(coluna) if so_a_raiz else f'"{coluna}" IS NOT NULL'
    selecoes = [
        f'SELECT {_raiz(coluna, so_a_raiz=so_a_raiz)} AS r FROM "{vista}" WHERE {filtro}'
    ]
    if outra:
        selecoes.append(
            f'SELECT {_raiz(outra, so_a_raiz=False)} AS r FROM "{vista}" WHERE {_preenchida(outra)}'
        )
    total, fora = porta.con.execute(
        f"""
        WITH raizes AS (SELECT DISTINCT r FROM ({" UNION ALL ".join(selecoes)})),
        pj AS (SELECT DISTINCT cast(cnpj_basico AS varchar) AS r FROM "{pj}")
        SELECT count(*), count(*) FILTER (WHERE pj.r IS NULL)
        FROM raizes LEFT JOIN pj USING (r)
        """
    ).fetchone()
    diferente = _raiz_diferente(porta, vista, tabela, _limpo(coluna))
    return Cruzamento(
        tabela,
        int(total),
        int(fora),
        diferente,
        _sem_documento(porta, vista, coluna, outra) if so_a_raiz else 0,
    )


def _sem_documento(porta: Porta, vista: str, coluna: str, outra: str | None) -> int:
    """Linhas sem a raiz e sem a outra coluna de CNPJ: quem elas descrevem não tem prova de ser PJ."""
    condicao = f"NOT {_preenchida(coluna)}"
    if outra:
        condicao += f" AND NOT {_preenchida(outra)}"
    (n,) = porta.con.execute(
        f'SELECT count(*) FROM "{vista}" WHERE {condicao}'
    ).fetchone()
    return int(n)


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
