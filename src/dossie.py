"""As fichas do dossiê da base no app (plano do relatório-modelo, 17/10/2026, PR 1).

A ficha é montada toda noite no servidor de casa (`scripts/gerar_dossies.py`), uma por CNPJ. Aqui ela
é lida e validada, perde o que é ruído (série de agência sem peso) e vira as `Secao` do relatório, já
com cada número escrito: a página do site, o PDF e a tela do app leem a mesma coisa (ADR 0044).

Uma ficha que não abre, fora do esquema ou de uma versão desconhecida não é mostrada (`None`): melhor
nenhuma seção do que uma seção errada.
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from base import dossie as dossie_da_base
from src.negociacoes import formatar_valor
from src.relatorio_empresa import Item, Secao

log = logging.getLogger(__name__)

VERSOES_CONHECIDAS = frozenset({1})
FICHA_DE_EXEMPLO = (
    Path(__file__).resolve().parent.parent
    / "dados_de_exemplo"
    / "dossie"
    / "02429144000193.json"
)
# série de agência com menos que isso do total no último ano: ruído (113 acessos de banda larga)
PARTICIPACAO_MINIMA = 0.001
MESES = (
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
)
TAMANHO_DO_MES = 7  # "2025-12"

TITULOS_DAS_TABELAS = {
    "trocas_de_auditor": "Trocas de auditor",
    "controladas": "Controladas e coligadas no FRE mais recente",
    "controladoras": "Quem controla a companhia",
    "ofertas": "Últimas ofertas do grupo registradas na CVM",
    "ofertas_por_ano": "Ofertas do grupo por ano",
    "fundos_por_mes": "Fundos com a empresa, mês a mês",
    "entidades_ligadas": "Entidades da agência ligadas à companhia",
    "negocios": "Últimos documentos de negócios",
    "negocios_por_ano": "Documentos de negócios por ano",
} | {serie.nome: serie.medida for serie in dossie_da_base.SERIES_DAS_AGENCIAS}
_UNIDADE_DA_SERIE = {
    serie.nome: serie.unidade for serie in dossie_da_base.SERIES_DAS_AGENCIAS
}
_NOME_DA_AGENCIA = {
    serie.fonte_b13: serie.medida.rsplit("(", 1)[-1].rstrip(")")
    for serie in dossie_da_base.SERIES_DAS_AGENCIAS
}


class ItemDaFicha(BaseModel):
    chave: str
    nome: str
    valor: str | int | float | None
    unidade: str
    base: str | None = None


class SecaoDaFicha(BaseModel):
    chave: str
    titulo: str
    itens: list[ItemDaFicha] = []
    tabelas: dict[str, list[dict[str, Any]]] = {}
    paragrafos: list[str] = []
    fontes: list[str] = []


class Ficha(BaseModel):
    versao_do_esquema: int
    cnpj: str
    empresa: str
    gerado_em: datetime
    secoes: list[SecaoDaFicha]


def ler_ficha(caminho: Path) -> Ficha | None:
    """A ficha validada (None: não existe, não abre, fora do esquema ou de versão desconhecida)."""
    try:
        bruta = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("ficha do dossiê não abre: %s", caminho)
        return None
    if (
        not isinstance(bruta, dict)
        or bruta.get("versao_do_esquema") not in VERSOES_CONHECIDAS
    ):
        log.warning("ficha do dossiê de versão desconhecida: %s", caminho)
        return None
    try:
        return Ficha.model_validate(bruta)
    except ValidationError:
        log.warning("ficha do dossiê fora do esquema: %s", caminho)
        return None


# --- cortes ----------------------------------------------------------------------------------------


def _serie_com_peso(linhas: list[dict[str, Any]]) -> bool:
    """A série tem peso se, no ano mais recente, passa de 0,1% do total da agência."""
    if not linhas:
        return False
    recente = max(linhas, key=lambda linha: linha.get("ano") or 0)
    return float(recente.get("participacao") or 0) >= PARTICIPACAO_MINIMA


def _cortar_setor(secao: SecaoDaFicha) -> SecaoDaFicha | None:
    series = {
        nome: linhas
        for nome, linhas in secao.tabelas.items()
        if nome in _UNIDADE_DA_SERIE and _serie_com_peso(linhas)
    }
    if not series:
        return None
    fontes_que_ficam = {
        serie.fonte_b13
        for serie in dossie_da_base.SERIES_DAS_AGENCIAS
        if serie.nome in series
    }
    ligadas = [
        linha
        for linha in secao.tabelas.get("entidades_ligadas", [])
        if linha.get("fonte") in fontes_que_ficam
    ]
    return secao.model_copy(
        update={
            "itens": [i for i in secao.itens if i.chave in series],
            "tabelas": series | ({"entidades_ligadas": ligadas} if ligadas else {}),
        }
    )


def cortar(ficha: Ficha) -> Ficha:
    """A ficha sem o ruído: série de agência com menos de 0,1% do total some (e a seção, se esvaziar)."""
    secoes = []
    for secao in ficha.secoes:
        cortada = _cortar_setor(secao) if secao.chave == "setor_regulado" else secao
        if cortada is not None:
            secoes.append(cortada)
    return ficha.model_copy(update={"secoes": secoes})


# --- números escritos ------------------------------------------------------------------------------


def _numero(valor: object) -> float:
    return float(valor) if isinstance(valor, int | float) else float(str(valor))


def para_data(valor: object) -> date:
    return date.fromisoformat(str(valor)[:10])  # "2026-03-31" ou "2026-03-31T00:00:00"


def inteiro(valor: object) -> str:
    return f"{_numero(valor):,.0f}".replace(",", ".")


def decimal(valor: object, casas: int = 1) -> str:
    return f"{_numero(valor):.{casas}f}".replace(".", ",")


def _porcentagem(valor: object) -> str:
    """30.0 → "30%"; 89.01 → "89,01%" (a participação no capital, como o FRE informa)."""
    numero = _numero(valor)
    return f"{numero:.0f}%" if numero.is_integer() else f"{decimal(numero, 2)}%"


def fracao(valor: object) -> str:
    return f"{decimal(_numero(valor) * 100)}%"


def reais(valor: object) -> str:
    return formatar_valor(_numero(valor), "BRL")


def dia(valor: object) -> str:
    return para_data(valor).strftime("%d/%m/%Y")


def mes(valor: object) -> str:
    quando = para_data(valor)
    return f"{MESES[quando.month - 1]}/{quando.year}"


def _ano(valor: object) -> str:
    return str(int(_numero(valor)))


def _texto(valor: object) -> str:
    return str(valor)


def _sim_ou_nao(valor: object) -> str:
    return "sim" if valor else "não"


def _agencia(valor: object) -> str:
    return _NOME_DA_AGENCIA.get(str(valor), str(valor))


def _escrever_valor(valor: str | float | None, unidade: str) -> str:
    if valor is None:
        return "—"
    if unidade == "R$":
        return reais(valor)
    if unidade == "data":
        return dia(valor)
    if isinstance(valor, int | float):
        return inteiro(valor)
    return str(valor)


def _escrever_base(base: str | None, gerado_em: datetime) -> str:
    """De quando é o número: dia, mês ("dez/2025") ou, se a data é depois da ficha, o ano do FRE."""
    if not base:
        return ""
    if len(base) == TAMANHO_DO_MES:
        return mes(f"{base}-01")
    quando = para_data(base)
    if quando > gerado_em.date():
        return f"FRE de {quando.year}"
    return dia(quando)


# cada coluna de cada tabela da ficha: (coluna, rótulo, como escrever); o que não está aqui não sai
Coluna = tuple[str, str, Any]
COLUNAS: dict[str, list[Coluna]] = {
    "trocas_de_auditor": [
        ("efetiva_em", "Desde", dia),
        ("anterior", "Auditor anterior", _texto),
        ("novo", "Auditor novo", _texto),
        ("anos_com_o_anterior", "Anos com o anterior", decimal),
    ],
    "controladas": [
        ("razao_social", "Sociedade", _texto),
        ("participacao", "Participação", _porcentagem),
        ("controlada", "Controlada", _sim_ou_nao),
    ],
    "controladoras": [
        ("controladora", "Controladora", _texto),
        ("participacao", "Participação", _porcentagem),
    ],
    "ofertas": [
        ("data", "Data", dia),
        ("emissor", "Emissor", _texto),
        ("valor_mobiliario", "Papel", _texto),
        ("tipo_oferta", "Tipo", lambda v: str(v).capitalize()),
        ("valor_total", "Valor registrado", reais),
        ("regime", "Regra", _texto),
    ],
    "ofertas_por_ano": [
        ("ano", "Ano", _ano),
        ("ofertas", "Ofertas", inteiro),
        ("valor_total", "Valor registrado", reais),
    ],
    "fundos_por_mes": [
        ("competencia", "Mês", mes),
        ("fundos", "Fundos", inteiro),
        ("valor", "Valor nas carteiras", reais),
    ],
    "entidades_ligadas": [
        ("nome", "Entidade na agência", _texto),
        ("fonte", "Agência", _agencia),
        ("desde", "Ligada desde", dia),
    ],
    "negocios": [
        ("publicado_em", "Data", dia),
        ("rotulo", "Documento", _texto),
        ("assunto", "Assunto, como a empresa escreveu", _texto),
    ],
    "negocios_por_ano": [
        ("ano", "Ano", _ano),
        ("documentos", "Documentos", inteiro),
    ],
}


def _colunas_da_serie(nome: str) -> list[Coluna]:
    return [
        ("ano", "Ano", _ano),
        ("valor", _UNIDADE_DA_SERIE[nome].capitalize(), inteiro),
        ("participacao", "Parte do total", fracao),
        ("meses", "Meses no ano", inteiro),
    ]


def titulo_da_tabela(chave: str) -> str:
    return TITULOS_DAS_TABELAS.get(chave, chave.replace("_", " ").capitalize())


def _escrever_tabela(chave: str, linhas: list[dict[str, Any]]) -> list[dict[str, str]]:
    colunas = (
        _colunas_da_serie(chave) if chave in _UNIDADE_DA_SERIE else COLUNAS.get(chave)
    )
    if colunas is None:
        raise KeyError(f"tabela do dossiê sem colunas declaradas: {chave}")
    return [
        {
            rotulo: "—" if linha.get(coluna) is None else escrever(linha[coluna])
            for coluna, rotulo, escrever in colunas
        }
        for linha in linhas
    ]


def links_da_tabela(ficha: Ficha, secao: str, tabela: str) -> list[str]:
    """Os links de cada linha (o documento na CVM), na ordem das linhas escritas."""
    da_secao = next((s for s in ficha.secoes if s.chave == secao), None)
    if da_secao is None:
        return []
    return [str(linha.get("link") or "") for linha in da_secao.tabelas.get(tabela, [])]


def secoes_da_ficha(ficha: Ficha) -> list[Secao]:
    """As seções do relatório, com os números escritos e a fonte (a atribuição que a licença pede)."""
    secoes = []
    for secao in ficha.secoes:
        itens = [
            Item(
                item.chave,
                item.nome,
                _escrever_valor(item.valor, item.unidade),
                float(item.valor) if isinstance(item.valor, int | float) else None,
                item.unidade,
                _escrever_base(item.base, ficha.gerado_em),
            )
            for item in secao.itens
        ]
        fontes = [f"Fonte: {fonte}." for fonte in secao.fontes]
        tabelas = {
            chave: _escrever_tabela(chave, linhas)
            for chave, linhas in secao.tabelas.items()
            if linhas
        }
        secoes.append(
            Secao(
                secao.chave, secao.titulo, itens, [*secao.paragrafos, *fontes], tabelas
            )
        )
    return secoes


def dia_da_ficha(ficha: Ficha) -> date:
    return ficha.gerado_em.date()
