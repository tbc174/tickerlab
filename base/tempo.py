"""Mapa dos nomes de tempo da base para os nomes canônicos (ADR 0108, D6, item 4; DIR-12).

Coluna publicada é contrato e não se renomeia: cada coluna temporal ganha, no contrato, o nome
canônico a que corresponde. Os canônicos são os de `base/rede/ligacoes.py` (ADR 0077), estendidos
a toda tabela nova. O sentido que não está claro fica `a_conferir` (e entra em `COLUNAS_A_CONFERIR`,
que o teste trava): ninguém chuta.
"""

from base.dicionario import Tabela

A_CONFERIR = "a_conferir"
CANONICOS = frozenset(
    {
        "aconteceu_em",  # (A) quando o fato começou a valer
        "ate",  # (A) quando deixou de valer (sem incluir o dia)
        "referencia",  # competência: o período a que o número se refere
        "publico_em",  # (B) quando ficou público
        "ate_publico_em",  # (B) quando se soube que acabou
        "visto_em",  # (B) quando o TickerLab viu a fonte pela primeira vez
        "coletado_em",  # (B) quando o arquivista guardou o original
    }
)

_POR_CANONICO: dict[str, tuple[str, ...]] = {
    "aconteceu_em": (
        "aconteceu_em", "valido_desde", "efetiva_em", "desde", "anunciada_em", "autorizado_em",
        "data_acao", "data_entrada", "data_entrada_antes", "data_entrada_depois",
        "data_inicio_atividade", "data_inicio_atividade_antes", "data_inicio_atividade_depois",
        "data_opcao_mei", "data_opcao_mei_antes", "data_opcao_mei_depois",
        "data_opcao_simples", "data_opcao_simples_antes", "data_opcao_simples_depois",
        "data_situacao_cadastral", "data_situacao_cadastral_antes", "data_situacao_cadastral_depois",
        "data_situacao_especial", "data_situacao_especial_antes", "data_situacao_especial_depois",
        "data_transacao", "data_abertura_processo", "data_comunicado", "data_deliberacao_aprovou_oferta",
        "data_dispensa_oferta", "data_emissao", "data_inicio_oferta", "data_protocolo",
        "data_registro", "data_registro_oferta", "data_requerimento",
        "DT_CONST", "DT_REG", "DT_INI_ATIV", "DT_INI_CLASSE", "DT_INI_SIT",
        "registro", "registrada_desde", "inicio_listagem", "inicio_negociacao",
        "entrada_em_operacao", "entrada_em_teste", "fechamento_em", "infracao_em",
        "primeira_inscricao", "ultima_inscricao", "ultima_alteracao_em", "instante",
        "transito_em_julgado", "concedido_em", "situacao_desde", "portaria_em", "execucao_desde",
    ),
    "ate": (
        "ate", "valido_ate", "vence_em", "execucao_ate", "cancelado_em", "cancelamento", "DT_CANCEL", "desativada_em", "fim_listagem",
        "fim_negociacao", "data_encerramento", "data_encerramento_oferta",
        "data_exclusao_mei", "data_exclusao_mei_antes", "data_exclusao_mei_depois",
        "data_exclusao_simples", "data_exclusao_simples_antes", "data_exclusao_simples_depois",
    ),
    "referencia": (
        "referencia", "competencia", "data_base", "exercicio", "inicio", "fim",
        "inicio_do_exercicio", "fim_do_exercicio", "DT_INI_EXERC", "DT_FIM_EXERC",
        "DT_PATRIM_LIQ", "acumulado_inicio", "acumulado_fim", "anual_fim", "balanco_fim",
        "receita_exercicio_fim", "composicao_em", "data_do_retrato", "relatorio",
        "ultima_referencia",
    ),
    "publico_em": (
        "publico_em", "disponivel_em", "divulgado_em", "conhecido_em", "publicado_em",
        "recebido_em", "entregue_em", "data_entrega", "documento_entregue_em",
        "origem_divulgado_em", "acumulado_publico_em", "anual_publico_em",
        "balanco_publico_em", "receita_publico_em", "conhecido_em_do_negocio",
        "primeira_entrega", "primeiro_recebido_em", "primeiro_visto",
    ),
    "ate_publico_em": ("ate_publico_em",),
    "visto_em": ("visto_em",),
    "coletado_em": (
        "coletado_em", "origem_coletada_em", "conferido_em", "confirmacao_em", "wayback_em",
    ),
}  # fmt: skip

# Sentido que não está claro (ou que a D6 não nomeia): cada grupo é uma linha da fila.
COLUNAS_A_CONFERIR = frozenset(
    {
        "atualizado_em",
        "base_de",
        "calculado_em",
        "confidencial_ate",
        "data",
        "data_da_previsao",
        "data_de_corte",
        "data_vencimento",
        "fechado_em",
        "gerado_em",
        "informado_em",  # o órgão informou a sanção à CGU (antes de ficar pública?)
        "mes",
        "montado_em",
        "porte_publico_em",
        "prazo",
        "primeira",
        "primeiro_no_cda",
        "ultima",
        "ultimo_no_cda",
        "ultimo_visto",
    }
)

SINONIMO_PARA_CANONICO: dict[str, str] = {
    coluna: canonico
    for canonico, colunas in _POR_CANONICO.items()
    for coluna in colunas
}


def coluna_e_temporal(tabela: Tabela, coluna: str) -> bool:
    """Data (dia ou hora) ou a coluna de uma das três datas da tabela (competência, mês...)."""
    if coluna not in tabela.colunas:
        return False
    unidade = tabela.colunas[coluna][1]
    return unidade.startswith("data") or coluna in tabela.datas.values()


def sinonimos_de_tempo(tabela: Tabela) -> dict[str, str]:
    """Coluna temporal → nome canônico da D6 (ou `a_conferir`)."""
    return {
        coluna: SINONIMO_PARA_CANONICO.get(coluna, A_CONFERIR)
        for coluna in tabela.colunas
        if coluna_e_temporal(tabela, coluna)
    }
