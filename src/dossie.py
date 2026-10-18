"""As fichas do dossiê da base no app (plano do relatório-modelo, 17/10/2026, PR 1).

A ficha é montada toda noite no servidor de casa (`scripts/gerar_dossies.py`), uma por CNPJ. Aqui ela
é lida e validada, perde o que é ruído (série de agência sem peso) e vira as `Secao` do relatório, já
com cada número escrito: a página do site, o PDF e a tela do app leem a mesma coisa (ADR 0044).

Uma ficha que não abre, fora do esquema ou de uma versão desconhecida não é mostrada (`None`): melhor
nenhuma seção do que uma seção errada.

No VPS (plano do dossiê da empresa no app, PR 3), as fichas chegam de casa toda noite em
`dados_locais/dossies/<dia>/`, e o link `atual` aponta para a última noite completa (`TICKERLAB_DOSSIES`
troca a pasta). `ficha_do` lê a do CNPJ e passa de novo pelas regras da base: seção fora do registro
ou tabela que não pode ser mostrada sai; CPF ou coluna de pessoa barra a ficha inteira.
"""

import json
import logging
import os
import re
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError

from base import dossie as dossie_da_base
from src.configuracao import PASTA_RAIZ
from src.negociacoes import formatar_valor
from src.numero import Comparacao
from src.relatorio_empresa import Dossie, Item, Secao

log = logging.getLogger(__name__)

VERSOES_CONHECIDAS = frozenset({1})
PASTA_PADRAO = PASTA_RAIZ / "dados_locais" / "dossies"
TAMANHO_MAXIMO = 2_000_000  # bytes; a maior ficha tem dezenas de KB
TAMANHO_DO_CNPJ = 14
DIAS_ATE_FICAR_VELHA = 3
FUSO = ZoneInfo("America/Sao_Paulo")
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
TAMANHO_DO_ANO = (
    4  # "2025": a série de agência somada no ano (base/dossie.py, `_item_da_serie`)
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


def pasta_das_fichas() -> Path:
    return Path(os.environ.get("TICKERLAB_DOSSIES") or PASTA_PADRAO)


def ficha_do(cnpj: str, pasta: Path | None = None) -> Ficha | None:
    """A ficha do CNPJ (formatado ou não) já conferida e cortada; None se não há ou não deve aparecer."""
    digitos = re.sub(r"\D", "", cnpj)
    if len(digitos) != TAMANHO_DO_CNPJ:
        return None
    caminho = (pasta or pasta_das_fichas()) / "atual" / f"{digitos}.json"
    try:
        if caminho.stat().st_size > TAMANHO_MAXIMO:
            log.warning("ficha do dossiê grande demais: %s", caminho)
            return None
    except OSError:
        return None  # a empresa não tem ficha (ou a pasta ainda não chegou)
    ficha = ler_ficha(caminho)
    if ficha is None:
        return None
    if ficha.cnpj != digitos:
        log.warning("ficha do dossiê com outro CNPJ dentro: %s", caminho)
        return None
    ficha = _so_o_que_pode_mostrar(ficha)
    try:
        # os nomes das entidades-pessoa ficam no servidor de casa; aqui valem o CPF e as colunas
        dossie_da_base.conferir_sem_pessoas(ficha.model_dump(mode="json"), set())
    except dossie_da_base.PessoaNaFichaError as erro:
        log.warning("ficha do dossiê barrada (%s): %s", erro, caminho)
        return None
    return cortar(ficha)


_REGISTRO = {secao.chave: secao for secao in dossie_da_base.SECOES}
_TABELA_DA_SERIE = {
    serie.nome: serie.tabela for serie in dossie_da_base.SERIES_DAS_AGENCIAS
}


def _tabela_pode_sair(chave: str) -> bool:
    """A tabela da ficha tem colunas declaradas e, se é série de agência, a fonte é vendável."""
    if chave in _TABELA_DA_SERIE:
        return dossie_da_base.pode_mostrar(_TABELA_DA_SERIE[chave])
    return chave in COLUNAS


def _so_o_que_pode_mostrar(ficha: Ficha) -> Ficha:
    """Tira a seção fora do registro ou que lê tabela proibida, e a tabela que não pode sair.

    As séries das agências são vistas uma a uma: uma fonte que deixa de ser vendável tira só a
    série dela, não o setor regulado inteiro.
    """
    series = set(_TABELA_DA_SERIE.values())
    secoes = []
    for secao in ficha.secoes:
        registrada = _REGISTRO.get(secao.chave)
        lidas = set(registrada.tabelas) - series if registrada else set()
        if registrada is None or not all(dossie_da_base.pode_mostrar(t) for t in lidas):
            log.warning("seção do dossiê que não pode ser mostrada: %s", secao.chave)
            continue
        tabelas = {k: v for k, v in secao.tabelas.items() if _tabela_pode_sair(k)}
        if len(tabelas) < len(secao.tabelas):
            log.warning(
                "tabelas do dossiê que não podem ser mostradas: %s",
                sorted(set(secao.tabelas) - set(tabelas)),
            )
        secoes.append(secao.model_copy(update={"tabelas": tabelas}))
    return ficha.model_copy(update={"secoes": secoes})


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
            "fontes": dossie_da_base.fontes_do_setor(series),
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


def _escritor_da_unidade(unidade: str) -> Callable[[object], str]:
    """Como escrever um número da série: em reais ("R$ 8,0 bi") ou inteiro ("9.743.641")."""
    return reais if unidade == "R$" else inteiro


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
    """De quando é o número: dia, mês ("dez/2025"), ano ("2025") ou, se a data é depois da ficha, o
    ano do FRE."""
    if not base:
        return ""
    if len(base) == TAMANHO_DO_ANO:
        return base
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
        (
            "valor",
            _UNIDADE_DA_SERIE[nome].capitalize(),
            _escritor_da_unidade(_UNIDADE_DA_SERIE[nome]),
        ),
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


# --- o contrato do número (relatórios v2, PR 1): de onde veio e contra o quê comparar -------------
_DO_FRE = "FRE entregue à CVM"
_DOS_FUNDOS = "carteiras dos fundos entregues à CVM (CDA, tabela painel_dos_fundos)"
FONTES_DOS_ITENS = {
    "auditor_atual": f"{_DO_FRE} (tabela auditores)",
    "auditor_desde": f"{_DO_FRE} (tabela trocas_de_auditor)",
    "sociedades": f"{_DO_FRE} (tabela controladas)",
    "controladas": f"{_DO_FRE} (tabela controladas)",
    "coligadas_e_outras": f"{_DO_FRE} (tabela controladas)",
    "ofertas": "ofertas registradas na CVM (tabelas ofertas_resolucao_160 e ofertas_antigas)",
    "fundos_com_a_acao": _DOS_FUNDOS,
    "valor_nos_fundos": _DOS_FUNDOS,
    "negocios": "fatos relevantes e comunicados do IPE na CVM (tabela eventos)",
} | {
    serie.nome: f"dados abertos da {_NOME_DA_AGENCIA[serie.fonte_b13]} (tabela {serie.tabela})"
    for serie in dossie_da_base.SERIES_DAS_AGENCIAS
}
SO_O_FRE_MAIS_RECENTE = (
    "A ficha traz só o FRE mais recente: não há o número do ano anterior para comparar."
)
SEM_COM_O_QUE_COMPARAR = "A ficha não traz com o quê comparar este número."
MESES_NO_ANO = 12

Comparado = tuple[Comparacao | None, str]  # a comparação ou o motivo de não haver
Comparar = Callable[[SecaoDaFicha, ItemDaFicha], Comparado]


def _mais_recentes(linhas: list[dict[str, Any]], coluna: str) -> list[dict[str, Any]]:
    return sorted(linhas, key=lambda linha: str(linha.get(coluna)), reverse=True)


def _contra_o_auditor_anterior(secao: SecaoDaFicha, _: ItemDaFicha) -> Comparado:
    trocas = _mais_recentes(secao.tabelas.get("trocas_de_auditor", []), "efetiva_em")
    if not trocas:
        return None, "A ficha não registra troca de auditor para comparar."
    troca = trocas[0]
    return Comparacao(
        "auditor anterior",
        f"{troca['anterior']} por {decimal(troca['anos_com_o_anterior'])} anos, até "
        f"{dia(troca['efetiva_em'])}",
    ), ""


def _contra_as_sociedades(secao: SecaoDaFicha, item: ItemDaFicha) -> Comparado:
    total = next((i.valor for i in secao.itens if i.chave == "sociedades"), None)
    if total is None or item.valor is None:
        return None, SO_O_FRE_MAIS_RECENTE
    return Comparacao(
        "sociedades no FRE", f"{inteiro(item.valor)} de {inteiro(total)}"
    ), ""


def _contra_os_anos(tabela: str, coluna: str) -> Comparar:
    """Compara a contagem com a dos dois últimos anos da tabela por ano."""

    def comparar(secao: SecaoDaFicha, _: ItemDaFicha) -> Comparado:
        anos = _mais_recentes(secao.tabelas.get(tabela, []), "ano")[:2]
        if not anos:
            return None, SEM_COM_O_QUE_COMPARAR
        return Comparacao(
            "contagem por ano",
            " e ".join(f"{inteiro(a[coluna])} em {_ano(a['ano'])}" for a in anos),
        ), ""

    return comparar


def _um_ano_antes(quando: date) -> date:
    return quando.replace(year=quando.year - 1)


def _contra_o_mesmo_mes(
    coluna: str, escrever: Callable[[object], str], sufixo: str = ""
) -> Comparar:
    """Compara a posição dos fundos com a do mesmo mês do ano anterior (ou a mais antiga)."""

    def comparar(secao: SecaoDaFicha, item: ItemDaFicha) -> Comparado:
        meses = sorted(
            secao.tabelas.get("fundos_por_mes", []), key=lambda m: str(m["competencia"])
        )
        if not meses or not item.base:
            return None, SEM_COM_O_QUE_COMPARAR
        alvo = _um_ano_antes(para_data(item.base)).strftime("%Y-%m")
        linha = next(
            (m for m in meses if str(m["competencia"]).startswith(alvo)), meses[0]
        )
        quando = mes(linha["competencia"])
        return Comparacao(
            f"carteiras de {quando}",
            f"{escrever(linha[coluna])}{sufixo} em {quando}",
            float(linha[coluna]),
        ), ""

    return comparar


def _contra_o_total_da_agencia(secao: SecaoDaFicha, item: ItemDaFicha) -> Comparado:
    """A participação no ano do item e o valor do ano anterior; o ano depois do item, se há na
    tabela, é o corrente, que o item deixou de fora por estar incompleto (`base/dossie.py`,
    `_item_da_serie`)."""
    anos = _mais_recentes(secao.tabelas.get(item.chave, []), "ano")
    if not anos:
        return None, SEM_COM_O_QUE_COMPARAR
    ano_do_item = (item.base or "")[:TAMANHO_DO_ANO]
    posicao = next(
        (i for i, linha in enumerate(anos) if _ano(linha["ano"]) == ano_do_item), 0
    )
    do_ano = anos[posicao]
    textos = [
        f"{fracao(do_ano['participacao'])} do total da agência em {_ano(do_ano['ano'])}"
    ]
    anterior = anos[posicao + 1] if posicao + 1 < len(anos) else None
    if anterior is not None:
        escrever = _escritor_da_unidade(item.unidade)
        textos.append(f"{escrever(anterior['valor'])} em {_ano(anterior['ano'])}")
    if posicao > 0:
        textos.append(f"{_ano(anos[0]['ano'])} fica de fora por estar incompleto")
    return Comparacao(
        "total da agência no ano",
        "; ".join(textos),
        _numero(anterior["valor"]) if anterior is not None else None,
    ), ""


_COMPARACOES = {
    "auditor_atual": _contra_o_auditor_anterior,
    "auditor_desde": _contra_o_auditor_anterior,
    "controladas": _contra_as_sociedades,
    "coligadas_e_outras": _contra_as_sociedades,
    "ofertas": _contra_os_anos("ofertas_por_ano", "ofertas"),
    "negocios": _contra_os_anos("negocios_por_ano", "documentos"),
    "fundos_com_a_acao": _contra_o_mesmo_mes("fundos", inteiro, " fundos"),
    "valor_nos_fundos": _contra_o_mesmo_mes("valor", reais),
} | {
    serie.nome: _contra_o_total_da_agencia
    for serie in dossie_da_base.SERIES_DAS_AGENCIAS
}


def _comparar(secao: SecaoDaFicha, item: ItemDaFicha) -> Comparado:
    if item.chave == "sociedades":
        return None, SO_O_FRE_MAIS_RECENTE
    comparar = _COMPARACOES.get(item.chave)
    return comparar(secao, item) if comparar else (None, SEM_COM_O_QUE_COMPARAR)


def _item_da_ficha(ficha: Ficha, secao: SecaoDaFicha, item: ItemDaFicha) -> Item:
    comparacao, sem_comparacao = _comparar(secao, item)
    return Item(
        item.chave,
        item.nome,
        _escrever_valor(item.valor, item.unidade),
        float(item.valor) if isinstance(item.valor, int | float) else None,
        item.unidade,
        _escrever_base(item.base, ficha.gerado_em),
        fonte=FONTES_DOS_ITENS.get(item.chave, ", ".join(secao.fontes)),
        comparacao=comparacao,
        sem_comparacao=sem_comparacao,
    )


def secoes_da_ficha(ficha: Ficha) -> list[Secao]:
    """As seções do relatório, com os números escritos e a fonte (a atribuição que a licença pede)."""
    secoes = []
    for secao in ficha.secoes:
        itens = [_item_da_ficha(ficha, secao, item) for item in secao.itens]
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


def limites_da_ficha(ficha: Ficha) -> list[str]:
    """Os cuidados com os números do dossiê (vão na seção de limites, no app e na amostra)."""
    return [
        (
            f"Os números são da base do TickerLab em {ficha.gerado_em:%d/%m/%Y} e mudam quando a "
            "companhia reapresenta um documento ou um fundo entrega uma carteira atrasada."
        ),
        (
            "As ofertas estão pelo valor registrado na CVM, não pelo colocado. O assunto dos "
            "documentos é escrito pela própria companhia, e os documentos de negócios são "
            "escolhidos pelas palavras do assunto: pode faltar algum ou sobrar algum."
        ),
        (
            "O setor regulado soma as entidades que o FRE liga à companhia hoje, também nos anos "
            "anteriores: um ano antigo pode contar uma distribuidora comprada depois."
        ),
        "Nomes de pessoas (administradores, conselheiros, sócios) não aparecem.",
    ]


def dossie_da_ficha(ficha: Ficha, hoje: date | None = None) -> Dossie:
    """A ficha (já de `ficha_do`) pronta para o relatório; velha com mais de 3 dias."""
    hoje = hoje or datetime.now(FUSO).date()
    dia = dia_da_ficha(ficha)
    return Dossie(
        secoes=secoes_da_ficha(ficha),
        fontes=tuple(dict.fromkeys(f for s in ficha.secoes for f in s.fontes)),
        limites=limites_da_ficha(ficha),
        dia=dia,
        velha=(hoje - dia).days > DIAS_ATE_FICAR_VELHA,
    )
