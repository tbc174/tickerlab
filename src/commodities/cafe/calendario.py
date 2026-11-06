"""Calendário do café por região: em que fase a planta está e o que o mercado costuma olhar
(plano do café, PR 9).

**Fonte do calendário.** As seis fases fenológicas do cafeeiro de Camargo & Camargo (2001,
"Definição e esquematização das fases fenológicas do cafeeiro arábica nas condições tropicais do
Brasil", *Bragantia*), em **dois anos** da planta, e as épocas de colheita dos levantamentos da
CONAB e da Embrapa Café. O cafeeiro leva dois anos para fazer uma safra: no primeiro, vegeta e
forma os ramos e as gemas; no segundo, as gemas florescem, os frutos enchem e amadurecem. Por isso,
em qualquer mês há **duas safras andando ao mesmo tempo**:

- *safra em curso* (ano 2 da planta): florada (set–nov), enchimento do grão (dez–mar), maturação
  (abr–mai) e repouso dos ramos (jun–ago);
- *safra seguinte* (ano 1 da planta): vegetação e formação das gemas foliares (set–mar) e indução e
  maturação das gemas florais (abr–ago).

Sobre as fases entram dois recortes que o mercado acompanha: a **colheita** (maio a setembro; no
Espírito Santo começa em abril) e a **janela de geada** (junho a agosto).

O calendário é **contexto datado, não previsão**: diz o que o mercado costuma olhar em cada época,
nunca o que o preço vai fazer. Os textos ficam em `conteudo/commodities/cafe.md`. Tudo aqui é
função pura em tipos simples (dataclass que vira JSON) e não depende do Streamlit.
"""

from dataclasses import dataclass

from src.commodities.cafe.regioes import POR_ID, Regiao
from src.conteudo import carregar_textos_do_cafe

MESES_DO_ANO = range(1, 13)

# safra em curso (ano 2 da planta), por mês
_SAFRA_EM_CURSO = {
    **dict.fromkeys((9, 10, 11), "florada"),
    **dict.fromkeys((12, 1, 2, 3), "enchimento"),
    **dict.fromkeys((4, 5), "maturacao"),
    **dict.fromkeys((6, 7, 8), "repouso"),
}
# safra seguinte (ano 1 da planta), por mês
_SAFRA_SEGUINTE = {
    **dict.fromkeys((9, 10, 11, 12, 1, 2, 3), "vegetacao"),
    **dict.fromkeys((4, 5, 6, 7, 8), "inducao"),
}
MESES_DA_COLHEITA = frozenset(range(5, 10))
MESES_DA_COLHEITA_NO_ES = frozenset(range(4, 10))  # o ES começa em abril
MESES_DA_GEADA = frozenset((6, 7, 8))

# índices do PR 8 (`indices_de_clima.py`) que se aplicam a cada tema; vazio = sem índice
INDICES_POR_TEMA: dict[str, tuple[str, ...]] = {
    "florada": ("indice_de_florada",),
    "enchimento": ("deficit_dez_mar",),
    "maturacao": (),
    "repouso": (),
    "colheita": (),
    "geada": ("dias_de_geada",),
    "vegetacao": (),
    "inducao": (),
}
TEMAS = tuple(INDICES_POR_TEMA)
TITULO_DO_TEXTO = {
    "florada": "O que o mercado olha na florada",
    "enchimento": "O que o mercado olha no enchimento do grão",
    "maturacao": "O que o mercado olha na maturação",
    "repouso": "O que o mercado olha no repouso dos ramos",
    "colheita": "O que o mercado olha na colheita",
    "geada": "O que o mercado olha na janela de geada",
    "vegetacao": "O que o mercado olha na vegetação da safra seguinte",
    "inducao": "O que o mercado olha na indução das gemas da safra seguinte",
}


@dataclass(frozen=True)
class Fase:
    """A fase do café numa região e num mês (cada nome é um tema de `TEMAS`)."""

    mes: int
    regiao_id: str
    safra_em_curso: str
    safra_seguinte: str
    em_colheita: bool
    na_janela_de_geada: bool


@dataclass(frozen=True)
class ItemDoCalendario:
    """Um assunto do mês: o texto explicativo e os índices de clima que se aplicam."""

    tema: str
    texto: str
    indices: tuple[str, ...]


@dataclass(frozen=True)
class OQueOMercadoOlha:
    """Tudo o que o mercado costuma olhar numa região num mês, na ordem: safra em curso,
    colheita, geada, safra seguinte."""

    fase: Fase
    itens: tuple[ItemDoCalendario, ...]


def _conferir(mes: int, regiao: Regiao) -> None:
    if mes not in MESES_DO_ANO:
        raise ValueError(f"mês fora de 1 a 12: {mes}")
    if regiao.id not in POR_ID:
        raise ValueError(f"região de café desconhecida: {regiao.id!r}")


def fase(mes: int, regiao: Regiao) -> Fase:
    """A fase do café no `mes` (1 a 12) na `regiao`: erro claro se o mês ou a região não existem."""
    _conferir(mes, regiao)
    meses_da_colheita = (
        MESES_DA_COLHEITA_NO_ES if "ES" in regiao.ufs else MESES_DA_COLHEITA
    )
    return Fase(
        mes,
        regiao.id,
        _SAFRA_EM_CURSO[mes],
        _SAFRA_SEGUINTE[mes],
        mes in meses_da_colheita,
        mes in MESES_DA_GEADA,
    )


def _temas_do_mes(situacao: Fase) -> list[str]:
    temas = [situacao.safra_em_curso]
    if situacao.em_colheita:
        temas.append("colheita")
    if situacao.na_janela_de_geada:
        temas.append("geada")
    temas.append(situacao.safra_seguinte)
    return temas


def o_que_o_mercado_olha(mes: int, regiao: Regiao) -> OQueOMercadoOlha:
    """O que o mercado costuma olhar na `regiao` no `mes`: texto de cada assunto e os índices de
    clima do PR 8 que se aplicam. Contexto, não previsão."""
    situacao = fase(mes, regiao)
    textos = carregar_textos_do_cafe()
    itens = tuple(
        ItemDoCalendario(tema, textos[TITULO_DO_TEXTO[tema]], INDICES_POR_TEMA[tema])
        for tema in _temas_do_mes(situacao)
    )
    return OQueOMercadoOlha(situacao, itens)
