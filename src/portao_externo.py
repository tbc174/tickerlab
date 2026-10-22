"""Portão da API externa (N3; ADR 0108, D2, D3 e D5): o que pode sair para quem integra o dado.

O app (telas, PDF, newsletter e a v1 interna) segue a ADR 0102 em `pode_usar`, que este módulo não
muda: nos canais do app o portão só repete a resposta de `pode_usar`. A API externa revende o dado a
quem vai copiá-lo para dentro de outro sistema, e por isso **nega tudo o que não tiver direito
positivo escrito**. Um campo só sai quando, ao mesmo tempo:

1. não é de pessoa natural, nota de risco, inferência individual nem dívida individual tirada de um
   agregado (D2.4), nem pelo nome do campo nem pela categoria da linha;
2. a fonte não está na lista negada desde o primeiro dia (D2.3);
3. há uma linha em `DIREITOS_DA_API_EXTERNA` para aquela fonte, conjunto, campo, canal e finalidade,
   dentro da vigência (D2.2);
4. as marcas da família (`src/banco/coletas.py`, um lugar só) dizem revenda vendável, guarda permitida,
   coleta limpa (ou `robots_fecha` nas condições do D5.3) e leitura dos termos em dia (D3).

Quem nega não explica para fora (D2.2): toda negação tem o mesmo `codigo_publico`, para não revelar se
o dado existe; o motivo (`Motivo`, lista fechada) fica para o log. Ainda sem rota pública: a B-32 (API
externa e MCP) e a N7 (chaves e quotas) chamam `decidir` antes de servir cada campo e
`consulta_permitida` antes de aceitar a chave de busca.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import NamedTuple

from base.arquivo.registro import TERMOS_LIDOS_EM
from src.banco.coletas import (
    COLETA_E_GUARDA,
    MOSTRAR,
    Coleta,
    ColetaEGuarda,
    Guarda,
    Marca,
    marca_da_fonte,
    pode_usar,
)


class Canal(StrEnum):
    """Por onde o dado sai (D2.5). Só `API_EXTERNA` passa pela regra deste portão."""

    TELA = "tela"
    RELATORIO = "relatorio"  # PDF
    NEWSLETTER = "newsletter"
    API_INTERNA = "api_interna"  # a v1 do app
    API_EXTERNA = "api_externa"


CANAIS_DO_APP = frozenset(canal for canal in Canal if canal is not Canal.API_EXTERNA)


class Finalidade(StrEnum):
    """Para que o dado sai (D2.5)."""

    ANALISE = "analise"  # núcleo Data
    CREDITO = "credito"  # dossiê e monitoramento
    TREINO = "treino"  # modelo próprio


class Categoria(StrEnum):
    """O que o campo é. As quatro últimas nunca saem pela API externa, qualquer que seja a marca."""

    FATO_DE_PJ = "fato_de_pj"
    AGREGADO = "agregado"  # setor, município ou território; nunca métrica da empresa (D4, contextual)
    PESSOA_NATURAL = "pessoa_natural"  # nome, CPF, sócio, administrador, MEI (ADR 0106)
    NOTA_DE_RISCO = "nota_de_risco"  # score, rating, PD (Resolução CVM 9; D8)
    INFERENCIA_INDIVIDUAL = (
        "inferencia_individual"  # insolvência, default, patrimônio individual
    )
    DIVIDA_INDIVIDUAL_DE_AGREGADO = (
        "divida_individual_de_agregado"  # SCR, MDCR, crédito rural
    )


NUNCA_SAEM = frozenset(
    {
        Categoria.PESSOA_NATURAL,
        Categoria.NOTA_DE_RISCO,
        Categoria.INFERENCIA_INDIVIDUAL,
        Categoria.DIVIDA_INDIVIDUAL_DE_AGREGADO,
    }
)


class Motivo(StrEnum):
    """Por que o portão liberou ou negou: lista fechada, para o log (nunca para o cliente)."""

    LIBERADO = "liberado"
    REGRA_DO_APP = (
        "regra_do_app"  # canal do app: a resposta é a de `pode_usar` (ADR 0102)
    )
    CANAL_DESCONHECIDO = "canal_desconhecido"
    NUNCA_SAI = "nunca_sai"  # D2.4
    NEGADA_DESDE_O_PRIMEIRO_DIA = "negada_desde_o_primeiro_dia"  # D2.3
    SO_COMO_PUBLICADO = (
        "so_como_publicado"  # derivado de fonte que só sai como publicada (CONAB)
    )
    SEM_LINHA_DE_DIREITO = "sem_linha_de_direito"  # D2.2
    AGREGADO_SO_COMO_AGREGADO = (
        "agregado_so_como_agregado"  # D2.4: nada individual de um agregado
    )
    REVENDA_NAO_VENDAVEL = "revenda_nao_vendavel"  # D3
    SEM_COLETA_E_GUARDA = (
        "sem_coleta_e_guarda"  # família ainda sem as respostas da linha 159
    )
    GUARDA_NAO_PERMITE = "guarda_nao_permite"
    COLETA_NAO_PERMITE = "coleta_nao_permite"  # D5.2 e D5.3
    TERMOS_SEM_DATA = "termos_sem_data"
    LEITURA_VENCIDA = "leitura_vencida"
    CONSULTA_PROIBIDA = "consulta_proibida"  # busca reversa por pessoa ou por nome
    # N7 (D8): a organização não tem linha de contrato vigente para o conjunto e a finalidade
    SEM_CONTRATO_DA_ORGANIZACAO = "sem_contrato_da_organizacao"


# D2.3 (auditoria N0): sair desta lista pede decisão nova. Vale a fonte e o que começa por ela
# ("b3" barra "b3-negocios"; "bcb-sgs-189" barra só a série do IGP-M, não o resto do BC).
NEGADAS_DESDE_O_PRIMEIRO_DIA = frozenset(
    {
        "b3",
        "yahoo",
        "fnc",
        "cecafe",
        "kraken",
        "mb",
        "fmi",
        "wayback",
        "contrapartes",
        "termos",
        "ico",
        "bcb-sgs-189",
    }
)
# CC BY-ND: a CONAB sai como publicada, sem recorte, soma ou derivado (D2.3)
SO_COMO_PUBLICADO = frozenset({"conab"})
# agregados de crédito (SCR, MDCR e crédito rural do SICOR): só saem como agregado, nunca por empresa
FONTES_DE_AGREGADO_DE_CREDITO = frozenset({"bcb-scr", "bcb-mdcr", "bcb-sicor"})
# Segunda trava do D2.4, pelo nome do campo: pega a linha escrita com a categoria errada. Na dúvida,
# nega (um "socio_cnpj" de sócio PJ também fica fora até ter decisão própria).
PALAVRAS_QUE_NUNCA_SAEM = frozenset(
    {
        "cpf",
        "pf",
        "pessoa",
        "socio",
        "socios",
        "administrador",
        "administradores",
        "mei",
        "empresario",
        "score",
        "rating",
        "pd",
        "insolvencia",
        "default",
    }
)
# D2.4: a API externa só busca por chave de empresa; nome, CPF ou lote de nomes nunca
CHAVES_DE_CONSULTA = frozenset(
    {"cnpj", "cnpj_raiz", "codigo_cvm", "ticker", "id_entidade"}
)
GUARDAS_QUE_SAEM = frozenset({Guarda.SEM_PRAZO, Guarda.COM_PRAZO})
COLETAS_QUE_SAEM = frozenset({Coleta.ABERTA, Coleta.COM_CADASTRO})
# D5.3: `robots_fecha` sai só até a resposta da P-49 ao advogado; se ela disser que não, vira False
ROBOTS_FECHA_SAI_PROVISORIO = True
PRAZO_DA_LEITURA = timedelta(days=180)  # D3: padrão do `revisar_em`
CODIGO_PUBLICO_DA_NEGACAO = (
    "not_available"  # o mesmo para todo motivo (D2.2; nomes externos em inglês, D7)
)


class LinhaDeDireito(NamedTuple):
    """Um direito positivo (D2.2): este campo, deste conjunto e desta fonte, sai por este canal para
    esta finalidade, entre `vigente_desde` e `vigente_ate` (sem incluir o dia; vazio = vale)."""

    fonte: str
    conjunto: str
    campo: str
    canal: Canal
    finalidade: Finalidade
    categoria: Categoria
    vigente_desde: date
    prova: str  # a decisão ou o documento que dá o direito
    vigente_ate: date | None = None


# Nenhum campo sai ainda: a B-32 escreve aqui cada campo que a rota externa servir, com a prova.
DIREITOS_DA_API_EXTERNA: tuple[LinhaDeDireito, ...] = ()


class Pedido(NamedTuple):
    """O que se quer servir: um campo de um conjunto, por um canal, para uma finalidade."""

    fonte: str
    conjunto: str
    campo: str
    canal: str
    finalidade: str
    derivado: bool = (
        False  # recorte, soma ou cálculo feito por nós sobre o dado da fonte
    )


class Decisao(NamedTuple):
    """A resposta do portão. `coleta` vai na proveniência da resposta externa (D5.3, condição c)."""

    libera: bool
    motivo: Motivo
    coleta: Coleta | None = None


@dataclass(frozen=True)
class Regras:
    """Tudo o que o portão consulta, num pacote só (para o teste trocar uma regra de cada vez)."""

    linhas: tuple[LinhaDeDireito, ...]
    negadas: frozenset[str]
    so_como_publicado: frozenset[str]
    fontes_de_agregado: frozenset[str]
    palavras_que_nunca_saem: frozenset[str]
    coleta_e_guarda: Mapping[str, ColetaEGuarda]
    termos_lidos_em: Mapping[str, date]
    robots_fecha_sai: bool


def regras_vigentes() -> Regras:
    """As regras de hoje, lidas dos lugares de sempre (as marcas em `src/banco/coletas.py`)."""
    return Regras(
        linhas=DIREITOS_DA_API_EXTERNA,
        negadas=NEGADAS_DESDE_O_PRIMEIRO_DIA,
        so_como_publicado=SO_COMO_PUBLICADO,
        fontes_de_agregado=FONTES_DE_AGREGADO_DE_CREDITO,
        palavras_que_nunca_saem=PALAVRAS_QUE_NUNCA_SAEM,
        coleta_e_guarda=COLETA_E_GUARDA,
        termos_lidos_em=TERMOS_LIDOS_EM,
        robots_fecha_sai=ROBOTS_FECHA_SAI_PROVISORIO,
    )


def _familia(fonte: str) -> str:
    return fonte.split("-", 1)[0]


def _esta_na_lista(fonte: str, lista: frozenset[str]) -> bool:
    """A fonte é da lista ou começa por um item dela ("b3-negocios" está em {"b3"})."""
    return any(fonte == item or fonte.startswith(f"{item}-") for item in lista)


def _nome_proibido(campo: str, palavras: frozenset[str]) -> bool:
    return any(palavra in palavras for palavra in campo.lower().split("_"))


def _negacao_absoluta(pedido: Pedido, regras: Regras) -> Motivo | None:
    """O que nega antes de olhar qualquer linha ou marca (D2.3, D2.4)."""
    if _nome_proibido(pedido.campo, regras.palavras_que_nunca_saem):
        return Motivo.NUNCA_SAI
    if _esta_na_lista(pedido.fonte, regras.negadas):
        return Motivo.NEGADA_DESDE_O_PRIMEIRO_DIA
    if pedido.derivado and _esta_na_lista(pedido.fonte, regras.so_como_publicado):
        return Motivo.SO_COMO_PUBLICADO
    return None


def _vigente(linha: LinhaDeDireito, hoje: date) -> bool:
    return linha.vigente_desde <= hoje and (
        linha.vigente_ate is None or hoje < linha.vigente_ate
    )


def _categorias_do_pedido(pedido: Pedido, hoje: date, regras: Regras) -> set[Categoria]:
    """As categorias de todas as linhas vigentes do pedido: com duas linhas, vale a mais restrita."""
    chave = (
        pedido.fonte,
        pedido.conjunto,
        pedido.campo,
        pedido.canal,
        pedido.finalidade,
    )
    return {
        linha.categoria
        for linha in regras.linhas
        if linha[:5] == chave and _vigente(linha, hoje)
    }


def _negacao_da_linha(pedido: Pedido, hoje: date, regras: Regras) -> Motivo | None:
    categorias = _categorias_do_pedido(pedido, hoje, regras)
    if not categorias:
        return Motivo.SEM_LINHA_DE_DIREITO
    if categorias & NUNCA_SAEM:
        return Motivo.NUNCA_SAI
    agregado = _esta_na_lista(pedido.fonte, regras.fontes_de_agregado)
    if agregado and categorias != {Categoria.AGREGADO}:
        return Motivo.AGREGADO_SO_COMO_AGREGADO
    return None


def _coleta_permite(respostas: ColetaEGuarda, regras: Regras) -> bool:
    if respostas.coleta in COLETAS_QUE_SAEM:
        return True
    return (
        respostas.coleta is Coleta.ROBOTS_FECHA
        and regras.robots_fecha_sai
        and respostas.licenca_permite_reuso_comercial
        and respostas.respeita_ritmo_e_se_identifica
    )


def _negacao_da_leitura(
    fonte: str, respostas: ColetaEGuarda, hoje: date, regras: Regras
) -> Motivo | None:
    lido_em = regras.termos_lidos_em.get(fonte) or regras.termos_lidos_em.get(
        _familia(fonte)
    )
    if lido_em is None:
        return Motivo.TERMOS_SEM_DATA
    revisar_em = respostas.revisar_em or lido_em + PRAZO_DA_LEITURA
    return Motivo.LEITURA_VENCIDA if hoje > revisar_em else None


def _respostas_da_fonte(fonte: str, regras: Regras) -> ColetaEGuarda | None:
    return regras.coleta_e_guarda.get(fonte) or regras.coleta_e_guarda.get(
        _familia(fonte)
    )


def _negacao_das_marcas(fonte: str, hoje: date, regras: Regras) -> Motivo | None:
    """D3: vendável, guarda permitida, coleta limpa e leitura dos termos em dia, tudo junto."""
    if marca_da_fonte(fonte) is not Marca.VENDAVEL:
        return Motivo.REVENDA_NAO_VENDAVEL
    respostas = _respostas_da_fonte(fonte, regras)
    if respostas is None:
        return Motivo.SEM_COLETA_E_GUARDA
    if respostas.guarda not in GUARDAS_QUE_SAEM:
        return Motivo.GUARDA_NAO_PERMITE
    if not _coleta_permite(respostas, regras):
        return Motivo.COLETA_NAO_PERMITE
    return _negacao_da_leitura(fonte, respostas, hoje, regras)


def _decidir_no_app(pedido: Pedido) -> Decisao:
    """Nos canais do app a regra é a da ADR 0102, sem tirar nem pôr."""
    uso = "treinar" if pedido.finalidade == Finalidade.TREINO else MOSTRAR
    return Decisao(pode_usar(uso, pedido.fonte), Motivo.REGRA_DO_APP)


def _decidir_na_api_externa(pedido: Pedido, hoje: date, regras: Regras) -> Decisao:
    motivo = (
        _negacao_absoluta(pedido, regras)
        or _negacao_da_linha(pedido, hoje, regras)
        or _negacao_das_marcas(pedido.fonte, hoje, regras)
    )
    if motivo is not None:
        return Decisao(False, motivo)
    respostas = _respostas_da_fonte(pedido.fonte, regras)
    return Decisao(True, Motivo.LIBERADO, respostas.coleta if respostas else None)


def decidir(pedido: Pedido, hoje: date, regras: Regras | None = None) -> Decisao:
    """Libera ou nega um campo, com o motivo. `hoje` é o dia da consulta (vigência das linhas e
    validade da leitura dos termos); `regras` vazio usa as vigentes. Canal desconhecido nega."""
    if pedido.canal in CANAIS_DO_APP:
        return _decidir_no_app(pedido)
    if pedido.canal != Canal.API_EXTERNA:
        return Decisao(False, Motivo.CANAL_DESCONHECIDO)
    return _decidir_na_api_externa(pedido, hoje, regras or regras_vigentes())


def consulta_permitida(chave: str) -> Decisao:
    """A API externa aceita buscar por esta chave? Só chave de empresa; nome, CPF e lote de nomes
    nunca (busca reversa por pessoa, D2.4)."""
    if chave in CHAVES_DE_CONSULTA:
        return Decisao(True, Motivo.LIBERADO)
    return Decisao(False, Motivo.CONSULTA_PROIBIDA)


def codigo_publico(decisao: Decisao) -> str | None:
    """O que a resposta externa diz de uma negação: o mesmo código para todo motivo (D2.2), para não
    revelar se o dado existe nem por que não sai. Liberado, None."""
    return None if decisao.libera else CODIGO_PUBLICO_DA_NEGACAO
