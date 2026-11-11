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
        # FRE 15.7: a assembleia a que o free float se refere (pode ser anterior à entrega do FRE)
        "ultima_assembleia_em",
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
        "DT_INI_GESTOR", "DT_INI_ADMIN",
        # o registro de fundos da CVM 175 (`registro_de_fundos`)
        "Data_Registro", "Data_Constituicao", "Data_Inicio_Situacao", "Data_Adaptacao_RCVM175",
        "registro", "registrada_desde", "inicio_listagem", "inicio_negociacao",
        "entrada_em_operacao", "entrada_em_teste", "fechamento_em", "infracao_em",
        "primeira_inscricao", "ultima_inscricao", "inscrito_em", "parcelado_em",  # a dívida ativa do PR e de MG
        "liquidado_em", "pago_em", "ordem_bancaria_em", "ordem_cronologica_em",  # a ordem cronológica de PE e ES
        "ultima_alteracao_em", "instante",
        "transito_em_julgado", "concedido_em", "situacao_desde", "portaria_em", "execucao_desde",
        "contratado_em", "data_assinatura", "data_contrato", "vigencia_inicio",
        "autorizada_em", "incluida_em", "embargada_em", "registrada_em",
        "ajuizado_em", "atualizado_na_fonte_em", "ultimo_movimento_em",  # o DataJud
        # linha 440: carimbo do arquivo na fonte, dia do fato e prazo (o `datas` já os tem assim)
        "gerado_em", "atualizado_em", "data", "prazo",
    ),
    "ate": (
        "ate", "valido_ate", "vence_em", "execucao_ate", "cancelado_em", "cancelada_em", "cancelamento", "DT_CANCEL", "Data_Cancelamento", "DT_FIM_GESTOR", "DT_FIM_ADMIN", "desativada_em", "fim_listagem",
        "confidencial_ate", "data_vencimento",  # linha 440: fim do sigilo; vencimento (como `vence_em`)
        "vigencia_fim", "fim_negociacao", "desembargada_em", "descredenciada_em", "data_encerramento", "data_encerramento_oferta",
        "data_exclusao_mei", "data_exclusao_mei_antes", "data_exclusao_mei_depois",
        "data_exclusao_simples", "data_exclusao_simples_antes", "data_exclusao_simples_depois",
    ),
    "referencia": (
        "referencia", "competencia", "data_base", "exercicio", "inicio", "fim",
        "inicio_do_exercicio", "fim_do_exercicio", "DT_INI_EXERC", "DT_FIM_EXERC",
        "Data_Inicio_Exercicio_Social", "Data_Fim_Exercicio_Social", "Data_Patrimonio_Liquido",
        "DT_PATRIM_LIQ", "acumulado_inicio", "acumulado_fim", "anual_fim", "balanco_fim",
        "receita_exercicio_fim", "composicao_em", "data_do_retrato", "relatorio",
        "ultima_referencia",
        # linha 440: data-base, meses de primeira e última aparição e o mês do dado
        "data_de_corte", "data_da_previsao", "primeira", "ultima", "primeiro_no_cda",
        "ultimo_no_cda", "mes",
    ),
    "publico_em": (
        "publico_em", "disponivel_em", "divulgado_em", "conhecido_em", "publicado_em",
        "recebido_em", "entregue_em", "data_entrega", "documento_entregue_em",
        "origem_divulgado_em", "acumulado_publico_em", "anual_publico_em",
        "balanco_publico_em", "receita_publico_em", "conhecido_em_do_negocio",
        "primeira_entrega", "primeiro_recebido_em", "primeiro_visto",
        "disponibilizada_em", "primeira_comunicacao",
        "lista_publicada_em",  # a CMED: o Last-Modified do arquivo no portal da Anvisa
        "ultimo_visto",  # linha 440: entrega do último FCA com o código, par do `primeiro_visto`
    ),
    "ate_publico_em": ("ate_publico_em", "fechado_em"),  # fechado_em: a rodada soube que acabou
    "visto_em": ("visto_em", "base_de"),  # base_de: o mês da extração em que o valor apareceu
    "coletado_em": (
        "coletado_em", "origem_coletada_em", "conferido_em", "confirmacao_em", "wayback_em",
        "teor_conferido_em",
        # linha 440: hora do sistema (o `datas` de 6 tabelas já as usa como `coletado_em`); o
        # `porte_publico_em` é o `baixado_em` do ZIP, apesar do nome (o corte da régua é conservador)
        "montado_em", "calculado_em", "porte_publico_em",
    ),
}  # fmt: skip

# Onde o mesmo nome de coluna tem outro sentido: (tabela, coluna) → nome canônico.
_POR_TABELA: dict[tuple[str, str], str] = {
    # o dia da foto: "o que se sabia neste dia"
    ("amostra_painel", "data"): "referencia",
    # o mês do retrato em que a mudança foi vista (o `datas` usa o mês como `publico_em`, no
    # mês inteiro: é a data de ver, nunca anterior à de publicar; o corte não muda)
    ("cnpj_estabelecimentos_mudancas", "mes"): "visto_em",
    ("cnpj_qsa_mudancas", "mes"): "visto_em",
    ("cnpj_simples_mudancas", "mes"): "visto_em",
}

# Sentido que não está claro (ou que a D6 não nomeia): cada grupo é uma linha da fila. As 19 da linha 160
# ganharam nome na linha 440; ficam as das linhas que as trouxeram.
COLUNAS_A_CONFERIR = frozenset(
    {
        "classificado_em",  # SIGBM: data da declaração que informou o CRI e o DPA
        "criado_em",  # CFEM: dia em que a ANM criou a linha (vira disponivel_em)
        "data_edital",  # TCE-PE: emissão do edital da licitação
        "data_homologacao",  # TCE-PE: publicação da homologação (o resultado já era público?)
        "informado_em",  # o órgão informou a sanção à CGU (antes de ficar pública?)
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


def sinonimos_de_tempo(tabela: Tabela, nome: str) -> dict[str, str]:
    """Coluna temporal → nome canônico da D6 (ou `a_conferir`); `nome` é o da tabela (há exceções)."""
    return {
        coluna: _POR_TABELA.get((nome, coluna))
        or SINONIMO_PARA_CANONICO.get(coluna, A_CONFERIR)
        for coluna in tabela.colunas
        if coluna_e_temporal(tabela, coluna)
    }
