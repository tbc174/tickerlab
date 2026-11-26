"""De quais fontes de coleta vem cada tabela do conector (linha 1 do foco "base em dia", 25/11/2026).

O frescor de uma tabela é o da última coleta "ok" das fontes que a alimentam (`src/frescor_das_fontes.py`).
Esse mapa não repete o que já está escrito em outro lugar:

- as fontes do arquivista vêm de `base/arquivo/destinos.py` (uma verdade só: o destino de cada fonte
  diz a tabela que ela alimenta);
- aqui ficam só as três exceções, cada uma com teste (`tests/test_fontes_das_tabelas.py`):
  `COLETAS_PROPRIAS` (tabela cujo coletor não é o arquivista), `DERIVADAS` (montada de outra tabela:
  herda as fontes dela) e `SEM_COLETA_PROPRIA` (montada de várias, sem fonte que dê o prazo; o motivo
  é escrito).

Sem Streamlit, só dado simples: serve a um script de frescor, à API ou ao conector.
"""

from collections import defaultdict
from collections.abc import Iterable
from functools import lru_cache

from base.arquivo import destinos

# tabelas cujos coletores gravam no registro de coletas com id próprio, fora do arquivista. Somam-se
# às fontes do arquivista da mesma tabela: os coletores diários da CVM (`cvm-dfp-itr`, `cvm-eventos`,
# `cvm-vlmo`, `cvm-cda`) trazem o dado do dia, e o arquivista (`cvm-hist-*`) guarda o histórico.
COLETAS_PROPRIAS: dict[str, tuple[str, ...]] = {
    "demonstracoes_como_era": ("cvm-dfp-itr",),
    "dmpl_como_era": ("cvm-dfp-itr",),
    "eventos": ("cvm-eventos",),
    "negociacoes": ("cvm-vlmo",),
    "cda_cotas": ("cvm-cda",),
    "codigos_invalidos": ("cvm-fca-versao",),
    "ifdata_valores": ("bcb-ifdata",),
    "ifdata_cadastro": ("bcb-ifdata",),
    "cnes_competencias": ("ms-cnes-estabelecimentos-competencia",),
    "sus_internacoes": ("ms-sih-rd-competencia",),
    "sus_ambulatorial": ("ms-sia-pa-competencia",),
    "anm_cfem_arrecadacao": ("anm-cfem-arrecadacao",),
    "anm_sigbm_barragens": ("anm-sigbm-barragens",),
    "anm_amb_producao_bruta": ("anm-amb-producao-bruta",),
    "anm_amb_producao_beneficiada": ("anm-amb-producao-beneficiada",),
    "anm_amb_agua_mineral": ("anm-amb-agua-mineral",),
    "debentures_assembleias": ("cvm-hist-ipe",),
    "ratings": ("cvm-hist-ipe", "cvm-ipe-rating"),
    "processos_nas_notas": ("cvm-enet-notas",),
    "ma_receitas_cpc15": ("cvm-enet-notas",),  # linha 1129: as notas CPC 15 das DFPs
}

# tabela montada a partir de outra: o frescor dela é o da tabela de origem
DERIVADAS: dict[str, tuple[str, ...]] = {
    "fre_remuneracao_extremos": ("fre_remuneracao",),
    "trocas_de_auditor": ("auditores",),
    "controladas_primeiro_fre": ("controladas",),
}

# tabela montada de várias tabelas, sem fonte própria que marque o prazo (a de origem é que vale)
SEM_COLETA_PROPRIA: dict[str, str] = {
    "rotulos_atraso": "rótulo calculado das demonstrações e das entregas, sem fonte própria",
    "entidades": "cadastro de entidades montado de várias tabelas de cadastro",
    "identificadores": "identificadores ligados de várias tabelas de cadastro",
    "ligacoes": "relações entre entidades montadas de várias tabelas",
}


@lru_cache(maxsize=1)
def _fontes_do_arquivista_por_tabela() -> dict[str, tuple[str, ...]]:
    por_tabela: dict[str, list[str]] = defaultdict(list)
    for fonte, destino in destinos.DESTINOS.items():
        for tabela in destino.tabelas:
            por_tabela[tabela].append(fonte)
    return {tabela: tuple(sorted(fontes)) for tabela, fontes in por_tabela.items()}


def fontes_da_tabela(tabela: str) -> tuple[str, ...]:
    """Os ids das fontes de coleta de uma tabela, em ordem; vazio se não tem (ou não existe)."""
    if tabela in DERIVADAS:
        return _sem_repetir(
            f for origem in DERIVADAS[tabela] for f in fontes_da_tabela(origem)
        )
    return _sem_repetir(
        (
            *_fontes_do_arquivista_por_tabela().get(tabela, ()),
            *COLETAS_PROPRIAS.get(tabela, ()),
        )
    )


def _sem_repetir(fontes: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(fontes))
