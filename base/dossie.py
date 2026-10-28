"""O dossiê da empresa: o que a base de ML diz de cada companhia, para o app (plano de 17/10/2026).

O "Relatório da empresa" do app (ADR 0032) ganha seções que vêm da base. Elas são calculadas toda noite
no servidor de casa (`scripts/gerar_dossies.py`), uma ficha JSON por CNPJ, e só o assinante Pro as vê.
É o primeiro uso da base como produto (ADR 0076: o TickerLab é o primeiro cliente).

**Só entra o que pode ser mostrado a quem paga** (`pode_mostrar`):

- a tabela está no dicionário da base e **não guarda pessoa** (ADR 0075: nomes esperam a LGPD);
- a fonte pode ser **mostrada** pela trava das licenças (`coletas.pode_usar("mostrar", ...)`): toda
  fonte, com a marca registrada e a fonte citada (ADR 0102; a B3 entrou em 22/10/2026, ADR 0008 Emenda 6);
- não é uma tabela de crise ou de risco com o nome da empresa (insolvência, atraso, situação especial,
  dívida com a União: esperam o parecer, P-44), nem das assessorias de M&A (licença a confirmar).

Uma fonte que passar a ser vendável entra sozinha: basta a tabela estar numa seção. Para pôr uma série
nova de agência (as das séries 5 e 6 da base, quando chegarem), é uma linha em `SERIES_DAS_AGENCIAS`.

Por último, `conferir_sem_pessoas` passa pela ficha inteira: nenhum CPF, nenhum nome de entidade tratada
como pessoa e nenhuma coluna de pessoa. Os textos livres (o assunto de um fato relevante) só são
conferidos contra os nomes que a rede conhece: é um limite, escrito na seção.

Cada item leva o seu rastro (`src/rastro.py`, B-02 de 20/10/2026): a fórmula e a tabela de cada chave
ficam em `ORIGEM_DOS_ITENS`, a versão do cálculo em `VERSAO_DO_DOSSIE`, e `publicado_em` é o dia em que
a linha mais nova usada ficou pública (a coluna `publico_em` do dicionário da tabela).

Funções puras: as tabelas chegam já só com a empresa da ficha; ler e gravar fica no script.
"""

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, NamedTuple

import pandas as pd

from base import concentracao
from base import indicadores_de_caixa as t1
from base.bcb_ifdata import DIAS_ATE_FICAR_PUBLICO, MESES_DA_DATA_BASE
from base.cnpj import formatar, raiz
from base.contrapartes.cafe import ENDERECO_DO_CNPJ, VEICULO_DO_CNPJ
from base.dicionario import TABELAS
from base.pessoas.sem_cpf import tirar_cpf_da_coluna
from base.rede.ligacoes_das_fontes import (
    AUDITA,
    COLIGADA_DE,
    CONTROLADA_DE,
    DO_CONGLOMERADO_DE,
    EMITE,
    PARTICIPADA_DE,
)
from base.rede.vistas import vista_publicada
from base.regras import LINHA_DO_LUCRO, RECEITA, TOLERANCIA_EM_REAIS
from src.banco.coletas import MOSTRAR, licenca_da_fonte, pode_usar
from src.negociacoes import CARGOS

VERSAO_DO_ESQUEMA = 1  # muda quando o app precisa ler a ficha de outro jeito
# sobe quando a conta de um item muda (o gabarito de `tests/test_dossie_rastro.py` quebra se não subir)
VERSAO_DO_DOSSIE = "1"
CALCULO_DO_DOSSIE = f"dossiê {VERSAO_DO_DOSSIE}"
# fora do app até o parecer (crise ou risco com o nome da empresa, P-44), mesmo que a licença deixe
# (a Emenda 3 da ADR 0008 liberou a da PGFN; o P-44 ainda a segura). A ADR 0103 (D2) tirou daqui a
# insolvência e a situação especial: só como fato datado e com o direito de resposta (`base/contestacoes.py`)
TABELAS_PROIBIDAS = frozenset({"rotulos_atraso", "pgfn_divida"})
LINHAS_NAS_LISTAS = (
    20  # últimas ofertas, últimos negócios: o resto fica na contagem por ano
)
MESES_DOS_FUNDOS = 24
ANOS_NAS_SERIES = 10
MESES_NO_ANO = 12
PARTICIPACAO_DE_CONTROLE = (
    50.0  # sem o tipo no FRE, mais da metade do capital é controle
)
ANOS_DO_FRE_EM_DIA = 2  # FRE da controladora mais velho que isso: ela parou de entregar
# mês do CDA com menos que isso do valor normal (mediana dos 12 anteriores): carteiras ainda chegando
FRACAO_DO_MES_COMPLETO = 0.6
MESES_PARA_A_MEDIANA = 12
MESES_MINIMOS_NA_MEDIANA = 6
AUDITOR_PESSOA = "Auditor pessoa física (nome não mostrado)"
DIGITOS_DO_CNPJ = 14
SOMA_DO_ANO, ULTIMO_MES = "soma do ano", "último mês do ano"
CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
COLUNAS_DE_PESSOA = frozenset(
    {"cpf", "administrador", "conselheiro", "diretor", "nome_pessoa", "socio"}
)
# palavras do assunto que indicam compra, venda, fusão ou reorganização (escolha editorial, sem acento)
PALAVRAS_DE_NEGOCIO = re.compile(
    r"aquisi|incorpora|fusao|cisao|aliena|desinvestimento|combinacao de negocio"
    r"|\bvenda de (?:participa|ativo|controle)|\bcompra de (?:participa|ativo|controle)"
    r"|oferta publica de aquisi|\bopa\b|reorganizacao societaria|joint venture"
    r"|transferencia de controle|memorando de entendimento"
)
ROTULOS_DE_NEGOCIO = ("Fato relevante", "Comunicado ao mercado")


class TabelaProibidaError(ValueError):
    """Uma seção do dossiê usaria uma tabela que não pode ser mostrada a quem assina."""


class PessoaNaFichaError(ValueError):
    """A ficha montada tem CPF, nome de pessoa ou coluna de pessoa: não sai do servidor de casa."""


# --- a regra de mostrar --------------------------------------------------------------------------


def pode_mostrar(nome_da_tabela: str) -> bool:
    """A tabela pode aparecer no app? (a trava deixa mostrar, sem pessoa e fora da lista proibida)"""
    tabela = TABELAS.get(nome_da_tabela)
    if tabela is None or tabela.pessoa or nome_da_tabela in TABELAS_PROIBIDAS:
        return False
    return pode_usar(MOSTRAR, tabela.familia_da_fonte)


def exigir_que_pode_mostrar(tabelas: Iterable[str]) -> None:
    """Levanta `TabelaProibidaError` com as tabelas que não podem ser mostradas."""
    proibidas = [nome for nome in tabelas if not pode_mostrar(nome)]
    if proibidas:
        raise TabelaProibidaError(f"não podem ser mostradas: {', '.join(proibidas)}")


def fontes_das_tabelas(tabelas: Iterable[str]) -> list[str]:
    """As licenças das fontes das tabelas, sem repetir: vão na seção (a atribuição que a licença pede)."""
    return sorted(
        {licenca_da_fonte(TABELAS[nome].familia_da_fonte) for nome in tabelas}
    )


@dataclass(frozen=True)
class SerieDaAgencia:
    """Uma medida de agência por entidade e mês, ligada à companhia pela tabela empresa ↔ série (B13)."""

    nome: str  # chave da série na ficha
    fonte_b13: str  # a `fonte` em `empresa_serie`
    tabela: str  # no dicionário da base (lida pela porta)
    chave: str  # a coluna que a B13 usa como `chave`
    valor: str
    modo: str  # SOMA_DO_ANO ou ULTIMO_MES
    medida: str  # o que o número é, escrito para a tela
    unidade: str
    # filtros de igualdade da porta: `(coluna, valor)` ou `(coluna, (valores aceitos))`
    filtros: tuple[tuple[str, str | int | tuple[str, ...]], ...] = ()
    chave_em_digitos: bool = False  # CNPJ: casa formatado ou não
    grupo: str | None = (
        None  # a coluna do grupo econômico, quando a agência o informa (molde D)
    )
    data: str = (
        "competencia"  # a coluna da data (o IF.data usa a data-base do trimestre)
    )
    meses_por_periodo: int = (
        1  # quantos meses cada data vale: 4 datas-base trimestrais fazem o ano
    )
    como_era: bool = (
        False  # a tabela diz quando o número ficou público: a noite lê o que era no dia
    )
    ligacao: str = "empresa_serie"  # a tabela que liga a entidade à companhia aberta
    chave_e_o_grupo: bool = (
        False  # a entidade já é o grupo (o conglomerado prudencial do BC)
    )
    abertura: str | None = (
        None  # a coluna que abre o número de cada entidade (a modalidade)
    )


SERIES_DAS_AGENCIAS = (
    SerieDaAgencia(
        "aneel_consumidores",
        "aneel-samp",
        "aneel_samp",
        "cnpj",
        "valor",
        ULTIMO_MES,
        "Consumidores atendidos pelas distribuidoras (ANEEL)",
        "consumidores",
        (
            ("detalhe_do_mercado", "Número de consumidores"),
            ("tipo_de_mercado", "Regular"),
        ),
        chave_em_digitos=True,
    ),
    *(
        SerieDaAgencia(
            f"anatel_{servico}",
            "anatel-acessos",
            "anatel_acessos",
            "cnpj",
            "acessos",
            ULTIMO_MES,
            f"Acessos em serviço, {texto} (Anatel)",
            "acessos",
            # a móvel vem por modalidade e por tecnologia (o mesmo acesso duas vezes): só a 1ª
            (("servico", servico), ("recorte", ("completo", "modalidade"))),
            chave_em_digitos=True,
            grupo="grupo_economico",
            como_era=True,
        )
        for servico, texto in (
            ("telefonia_movel", "telefonia móvel"),
            ("banda_larga_fixa", "banda larga fixa"),
            ("tv_por_assinatura", "TV por assinatura"),
        )
    ),
    SerieDaAgencia(
        "ans_beneficiarios",
        "ans-beneficiarios",
        "ans_beneficiarios",
        "cd_operadora",
        "beneficiarios",
        ULTIMO_MES,
        "Beneficiários de planos de saúde (ANS)",
        "beneficiários",
        como_era=True,
    ),
    SerieDaAgencia(
        "anac_passageiros",
        "anac-estatistico",
        "anac_estatistico",
        "empresa_sigla",
        "passageiros_pagos",
        SOMA_DO_ANO,
        "Passageiros pagos transportados (ANAC)",
        "passageiros",
    ),
    SerieDaAgencia(
        "susep_premio_ganho",
        "susep-ses",
        "susep_seguros",
        "coenti",
        "premio_ganho",
        SOMA_DO_ANO,
        "Prêmio ganho das seguradoras (SUSEP)",
        "R$",
        como_era=True,
    ),
    SerieDaAgencia(
        "anp_vendas",
        "anp-vendas-distribuidora",
        "anp_vendas",
        "agente",
        "quantidade",
        SOMA_DO_ANO,
        "Vendas das distribuidoras de combustíveis líquidos (ANP)",
        "mil m³",
        (("unidade", "mil m³"),),
    ),
)


FONTE_DO_IFDATA = "bcb-ifdata"
CONGLOMERADO_PRUDENCIAL = 1  # o tipo 1 do IF.data: a base do REB do Banco Central
RESUMO, CARTEIRA_PF, CARTEIRA_PJ = (
    1,
    11,
    13,
)  # relatórios do IF.data (os de modalidade, desde 2025)
# os nomes do relatório 1 no acervo (201403 a 202606); a carteira mudou de nome com a contabilidade
# de 2025 (Resolução CMN 4.966): "Classificada" até 2024, sem o adjetivo desde então
CARTEIRA_DE_CREDITO = ("Carteira de Crédito Classificada", "Carteira de Crédito")


def _do_ifdata(
    nome: str,
    medida: str,
    coluna: str | tuple[str, ...],
    unidade: str = "R$",
    relatorio: int = RESUMO,
    abertura: str | None = None,
) -> SerieDaAgencia:
    """Uma série do conglomerado prudencial no IF.data: o estoque da última data-base de cada ano,
    lido como era público no dia (a data-base sai 120 dias depois)."""
    return SerieDaAgencia(
        nome,
        FONTE_DO_IFDATA,
        "ifdata_valores",
        "cod_inst",
        "saldo",
        ULTIMO_MES,
        medida,
        unidade,
        (
            ("tipo_instituicao", CONGLOMERADO_PRUDENCIAL),
            ("relatorio", relatorio),
            ("coluna", (coluna,) if isinstance(coluna, str) else coluna),
        ),
        data="data_base",
        meses_por_periodo=MESES_NO_ANO // len(MESES_DA_DATA_BASE),
        como_era=True,
        ligacao="ligacao_dos_bancos",
        chave_e_o_grupo=True,
        abertura=abertura,
    )


# fora de `SERIES_DAS_AGENCIAS`: só o relatório do setor (molde D) as lê; a ficha da empresa, não
SERIES_DOS_BANCOS = (
    _do_ifdata(
        "bcb_ativo_total",
        "Ativo total dos conglomerados prudenciais (Banco Central)",
        "Ativo Total",
    ),
    _do_ifdata(
        "bcb_carteira_de_credito",
        "Carteira de crédito dos conglomerados prudenciais (Banco Central)",
        CARTEIRA_DE_CREDITO,
    ),
    _do_ifdata(
        "bcb_captacoes",
        "Captações dos conglomerados prudenciais (Banco Central)",
        "Captações",
    ),
    _do_ifdata(
        "bcb_indice_de_basileia",
        "Índice de Basileia do conglomerado prudencial (Banco Central)",
        "Índice de Basileia",
        unidade="fração",
    ),
    _do_ifdata(
        "bcb_carteira_pf_por_modalidade",
        "Carteira de crédito a pessoas físicas, por modalidade (Banco Central)",
        "Total",
        relatorio=CARTEIRA_PF,
        abertura="grupo",
    ),
    _do_ifdata(
        "bcb_carteira_pj_por_modalidade",
        "Carteira de crédito a pessoas jurídicas, por modalidade (Banco Central)",
        "Total",
        relatorio=CARTEIRA_PJ,
        abertura="grupo",
    ),
)
_SERIE_POR_NOME = {
    serie.nome: serie for serie in (*SERIES_DAS_AGENCIAS, *SERIES_DOS_BANCOS)
}


@dataclass(frozen=True)
class SetorDoLancamento:
    """Um setor do relatório do setor (molde D): quem está nele e sobre o que se mede a concentração.

    Entra no setor a companhia com ticker ligada à agência pela tabela empresa ↔ série (B13). As que
    entram pelo setor da CVM (geradoras, transmissoras) são somadas no app, que tem o cadastro.
    """

    chave: str
    nome: str
    agencia: str  # para o motivo de cada membro ("ligada à ANS por 2 entidades")
    series: tuple[str, ...]  # `SerieDaAgencia.nome`: a base da concentração
    mercado_regional: bool = False  # competem por região: o total nacional mede escala
    # números de cada membro mostrados lado a lado, sem concentração (Basileia não se soma)
    lado_a_lado: tuple[str, ...] = ()
    contracao: str = "à"  # "ligada à ANS", "ligada ao Banco Central"

    @property
    def fontes_b13(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(_SERIE_POR_NOME[n].fonte_b13 for n in self.series))

    @property
    def todas_as_series(self) -> tuple[str, ...]:
        return (*self.series, *self.lado_a_lado)


SETORES_DO_LANCAMENTO = (
    SetorDoLancamento("eletricas", "Elétricas", "ANEEL", ("aneel_consumidores",)),
    SetorDoLancamento(
        "bancos",
        "Bancos",
        "Banco Central",
        ("bcb_ativo_total", "bcb_carteira_de_credito", "bcb_captacoes"),
        lado_a_lado=(
            "bcb_indice_de_basileia",
            "bcb_carteira_pf_por_modalidade",
            "bcb_carteira_pj_por_modalidade",
        ),
        contracao="ao",
    ),
    SetorDoLancamento("seguros", "Seguros", "SUSEP", ("susep_premio_ganho",)),
    SetorDoLancamento(
        "saude_suplementar",
        "Saúde suplementar",
        "ANS",
        ("ans_beneficiarios",),
        mercado_regional=True,
    ),
    SetorDoLancamento(
        "telecom",
        "Telecomunicações",
        "Anatel",
        ("anatel_telefonia_movel", "anatel_banda_larga_fixa"),
        mercado_regional=True,
    ),
    SetorDoLancamento("aviacao", "Aviação", "ANAC", ("anac_passageiros",)),
)


def fontes_do_setor(nomes_das_series: Iterable[str]) -> list[str]:
    """As licenças do setor regulado: só as agências das séries dadas e a tabela que liga cada uma à
    companhia (a empresa ↔ série; a `ligacao_dos_bancos` no IF.data)."""
    nomes = set(nomes_das_series)
    series = [serie for serie in _SERIE_POR_NOME.values() if serie.nome in nomes]
    tabelas = dict.fromkeys(t for s in series for t in (s.ligacao, s.tabela))
    return fontes_das_tabelas(tabelas or ("empresa_serie",))


@dataclass(frozen=True)
class SecaoDaBase:
    chave: str
    titulo: str
    tabelas: tuple[str, ...]


# o M&A das assessorias (série 5 da base): as partes, o negócio, a data em que ficou conhecido
TABELAS_DO_MA = ("ma_assessorias", "ma_partes", "ma_negocios", "ma_datas")

SECOES = (
    SecaoDaBase(
        "auditor_e_controladas",
        "Auditor e controladas",
        (
            "auditores",
            "trocas_de_auditor",
            "controladas",
            "ligacoes",
            "entidades",
            "identificadores",
        ),
    ),
    SecaoDaBase(
        "ofertas_e_fundos",
        "Ofertas e fundos",
        ("ofertas_resolucao_160", "ofertas_antigas", "painel_dos_fundos"),
    ),
    SecaoDaBase(
        "qualidade_do_lucro",
        "Qualidade do lucro",
        ("demonstracoes_como_era", "release_x_oficial", "trocas_de_auditor"),
    ),
    SecaoDaBase(
        "geracao_de_caixa",
        "Geração de caixa (EBITDA, capex e FCF)",
        ("demonstracoes_como_era",),
    ),
    SecaoDaBase(
        "capital_e_acionistas",
        "Capital e acionistas",
        ("negociacoes", "eventos_de_capital", "painel_dos_fundos"),
    ),
    SecaoDaBase(
        "governanca",
        "Governança",
        (
            "fre_conselho",
            "fre_comites",
            "fre_remuneracao",
            "fre_remuneracao_extremos",
            "fre_diversidade",
        ),
    ),
    SecaoDaBase("credito", "Crédito", ("ratings", "debentures_assembleias")),
    SecaoDaBase(
        "setor_regulado",
        "Setor regulado",
        ("empresa_serie", *dict.fromkeys(s.tabela for s in SERIES_DAS_AGENCIAS)),
    ),
    SecaoDaBase(
        "setor",
        "Setor",
        (
            "empresa_serie",
            *dict.fromkeys(
                tabela
                for setor in SETORES_DO_LANCAMENTO
                for nome in setor.todas_as_series
                for tabela in (
                    _SERIE_POR_NOME[nome].ligacao,
                    _SERIE_POR_NOME[nome].tabela,
                )
            ),
        ),
    ),
    SecaoDaBase("negocios", "Negócios e eventos", ("eventos", *TABELAS_DO_MA)),
    SecaoDaBase(
        "insolvencia",
        "Registros de insolvência e situação especial",
        ("insolvencia", "cnpj_situacao_especial"),
    ),
    SecaoDaBase(
        "rede", "Ligações na rede", ("ligacoes", "entidades", "identificadores")
    ),
)
_SECAO_POR_CHAVE = {secao.chave: secao for secao in SECOES}

LIMITES = {
    "auditor_e_controladas": (
        "Controladas e coligadas vêm do Formulário de Referência (FRE) mais recente entregue à CVM. "
        "Quando o FRE não informa o tipo, conta como controlada a sociedade com mais da metade do "
        "capital. A controladora aparece só quando ela também entrega o FRE, com o dos últimos 2 anos ainda listando a "
        "companhia. Auditor pessoa física "
        "não tem o nome mostrado."
    ),
    "ofertas_e_fundos": (
        "Ofertas registradas na CVM (Resolução 160 e as anteriores) da companhia e das controladas do "
        "FRE mais recente (o grupo costuma emitir pelas controladas), pelo valor registrado, não o "
        "colocado. Fundos: a posição comprada somada das carteiras entregues à CVM (CDA), que saem "
        "com até 90 dias de atraso: os meses em que as carteiras ainda estão chegando ficam de fora."
    ),
    "geracao_de_caixa": (
        "Contas da DFP de cada exercício, como eram públicas no dia da ficha (uma reapresentação "
        "entra a partir do dia em que saiu). EBITDA = resultado antes do resultado financeiro (DRE "
        "3.05) + depreciação e amortização (DVA 7.04.01; sem DVA, as linhas de depreciação da DFC). "
        "Capex = compras de imobilizado e intangível na DFC de investimento. FCF = caixa operacional "
        "(DFC 6.01) − capex. No consolidado, quando a empresa o publica. Sem a linha, o número fica "
        "vazio: em bancos e seguradoras a DRE 3.05 não é o EBIT, e o EBITDA não sai."
    ),
    "qualidade_do_lucro": (
        "Reapresentação: o lucro do período ou a receita de um dos últimos 10 exercícios que mudou "
        "mais de R$ 1 mil (o arredondamento da CVM) depois de publicado na DFP, pela própria DFP "
        "reapresentada ou pela do ano seguinte; no consolidado, quando a empresa o publica. O "
        "release é o que a empresa disse no press-release de resultado contra o ITR ou a DFP do "
        "mesmo período (receita, lucro dos controladores e resultado operacional): o número do "
        "release foi lido por um modelo de IA e conferido no texto do PDF, e diferença não é erro, "
        "pode ser outro critério da empresa. O atraso de entrega está na ficha técnica (o prazo da "
        "CVM contra a entrega)."
    ),
    "capital_e_acionistas": (
        "Insiders: compras e vendas de ações declaradas à CVM (VLMO) por controladores, diretores, "
        "conselheiros e acionistas com 10% ou mais, somadas por tipo de cargo nos 12 meses até a "
        "data da ficha, só com as declarações já entregues; sem nomes. A recompra é a própria "
        "empresa comprando (tesouraria), à parte. Eventos de capital (desdobramentos, grupamentos, "
        "bonificações e aumentos) vêm do Formulário de Referência (FRE). Compras e vendas dos "
        "fundos: o que as carteiras entregues à CVM (CDA) informam no mês, até o último mês "
        "completo; nem todo fundo preenche, e quantos fundos têm a ação está em Ofertas e fundos."
    ),
    "governanca": (
        "Do Formulário de Referência (FRE) entregue à CVM, na versão mais nova já entregue na data da "
        "ficha; só contagens e somas, sem nomes. O conselho conta quem está só nele e quem é também "
        "diretor; independente e eleito por minoritários seguem o cargo que a empresa informa. A "
        "remuneração é a do último exercício encerrado, como a empresa a informa por órgão (o total e "
        "a maior, a média e a menor individual); a prevista para o ano corrente fica de fora. "
        "Diversidade só existe no FRE de 2023 em diante."
    ),
    "credito": (
        "Ratings: os relatórios das agências e os comunicados da companhia entregues à CVM, lidos "
        "pelo TickerLab (documento que não deu para ler fica de fora); o mesmo rating em dois "
        "documentos conta uma vez, na data do primeiro. Assembleias de debenturistas: editais, atas "
        "e propostas entregues à CVM, na versão mais nova; o tema sai das palavras do assunto, que "
        "a empresa escreve, e pode deixar escapar ou incluir algum. Assembleia não quer dizer "
        "problema: muitas só aprovam mudanças de rotina."
    ),
    "setor_regulado": (
        "Soma das entidades ligadas à companhia pela tabela empresa ↔ série da base (própria ou "
        "controlada, pelo FRE). A participação é sobre o total da agência no ano."
    ),
    "setor": (
        "Concentração pelo HHI (a soma dos quadrados das participações em %, de 0 a 10.000) e pela "
        "CR4 (a participação somada das 4 maiores), sobre o total nacional que a agência publica no "
        "ano (o estoque do último mês ou a soma dos meses). Faixas do Guia para Análise de Atos de "
        "Concentração Horizontal do CADE (2016): abaixo de 1.500 pontos, não concentrado; de 1.500 a "
        "2.500, moderadamente concentrado; acima de 2.500, altamente concentrado. Cada participante é "
        "o grupo econômico quando a agência o informa; senão a companhia aberta a que a entidade está "
        "ligada pela base, com a estrutura de hoje também nos anos passados; senão a própria "
        "entidade. A variação do HHI só compara dois anos seguidos e completos. "
        "Bancos: o IF.data do Banco Central, com todas as instituições do sistema financeiro e cada "
        "conglomerado prudencial como um participante (o BC já junta as instituições do grupo; a "
        "companhia aberta se liga ao conglomerado pela base), a mesma base do Relatório de Economia "
        "Bancária (REB). O estoque é o da última data-base do ano (são 4 por ano), que sai 120 dias "
        "depois dela. A carteira de crédito é a carteira classificada (desde 2025, a carteira de "
        "crédito da contabilidade nova) e o REB usa a carteira ativa: a participação de cada banco "
        "muda um pouco, mas a CR4 de crédito fica perto da publicada (2022: 58,7% contra 58,6%; "
        "2023: 57,8% contra 57,8%; 2024: 57,3% contra 57,9%). O ativo é o total (o REB tira as "
        "aplicações interfinanceiras) e as captações são mais largas que os depósitos do REB. O REB "
        "mede com a régua do BC (o HHI normalizado); aqui, com a do CADE. Quando o BC revisa uma "
        "data-base, vale a revisão, com a data da primeira publicação: a base não guarda o dia da "
        "revisão. Basileia e carteira por modalidade são de cada conglomerado, sem somar; a carteira "
        "por modalidade só existe desde 2025."
    ),
    "negocios": (
        "Fatos relevantes e comunicados cujo assunto fala de compra, venda, fusão, incorporação ou "
        "reorganização. A escolha é pelas palavras do assunto: pode deixar escapar ou incluir algum. "
        "O assunto é escrito pela empresa. M&A das assessorias: negócios de compra, venda e "
        "investimento que as assessorias de M&A independentes publicam nos sites delas, nos quais a "
        "empresa aparece com o papel dito no título (comprou, vendeu ou foi comprada), contados uma "
        "vez por negócio mesmo que as duas pontas o publiquem. A data é a da primeira prova de que o "
        "negócio já era público (a primeira cópia da página no arquivo da web ou a nossa primeira "
        "coleta), não a do fechamento. Só entram empresas ligadas por nome exato ao CNPJ; nome em "
        "dúvida fica de fora. Cobre as assessorias que a base lê (hoje uma), sobretudo o middle "
        "market: não é a lista de todas as operações do mercado, e a ausência de negócios aqui não "
        "quer dizer que a empresa não fez nenhum. Sem valores e sem a outra parte do negócio."
    ),
    "insolvencia": (
        "Só fatos que fontes oficiais registram, copiados com a data do fato, a data em que ficaram "
        "públicos, o veículo e o link; a ficha descreve o que as fontes dizem. CVM: documentos do IPE "
        "que anunciam recuperação, pedido de falência, falência ou liquidação da própria companhia, "
        "contados uma vez por entrega, na data da primeira versão; o documento que fala de outra "
        "empresa fica de fora. Receita Federal: a situação especial do cadastro do CNPJ, publicada "
        "por mês; filiais e meses repetidos contam um fato só. Cada fato vale a partir do dia em que "
        "ficou público. Quando a empresa contesta um fato, a contestação aparece ao lado dele. "
        "Sócios e administradores não aparecem."
    ),
    "rede": (
        "Ligações da rede de entidades do TickerLab, montada com o Formulário de Referência (FRE), o "
        "Formulário Cadastral e as carteiras dos fundos entregues à CVM e com o IF.data do Banco "
        "Central. Uma ligação do FRE só aparece quando o FRE mais recente da companhia que a informa é "
        "dos últimos 2 anos e ainda a lista. A data é a do primeiro documento que mostrou a ligação. "
        "Pessoas (sócios, administradores) e sinais negativos (sanções, dívidas) não aparecem."
    ),
}


# --- peças comuns ---------------------------------------------------------------------------------


def normalizar_nome(texto: str) -> str:
    """Sem acento, em minúsculas e com um espaço só: para comparar nomes."""
    sem_acento = unicodedata.normalize("NFD", str(texto))
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    return " ".join(sem_acento.casefold().split())


def digitos(valores: pd.Series) -> pd.Series:
    """Só os dígitos de cada valor (CNPJ formatado ou não)."""
    return valores.astype(str).str.replace(r"\D", "", regex=True)


def _data(valor: object) -> str | None:
    return None if pd.isna(valor) else pd.Timestamp(valor).strftime("%Y-%m-%d")


def _registros(tabela: pd.DataFrame) -> list[dict[str, Any]]:
    """As linhas em tipos simples (datas ISO, faltando → None), como vão no JSON."""
    copia = tabela.copy()
    for coluna in copia.columns:
        if pd.api.types.is_datetime64_any_dtype(copia[coluna]):
            copia[coluna] = copia[coluna].dt.strftime("%Y-%m-%d")
        elif copia[coluna].map(lambda v: isinstance(v, date)).any():
            # a base guarda algumas datas sem hora (`datetime.date`): o JSON as escreveria em milissegundos
            copia[coluna] = copia[coluna].map(_data)
    return json.loads(copia.to_json(orient="records", force_ascii=False))


def _item(
    chave: str,
    nome: str,
    valor: str | float | None,
    unidade: str,
    base: str | None,
    *,
    publicado_em: str | None,
    fontes: Iterable[str] = (),
    origem: "Origem | None" = None,
) -> dict[str, Any]:
    """Um item da ficha com o rastro; `publicado_em` é obrigatório para ninguém esquecer de pensar nele
    (None só nos `ITENS_SEM_DATA_DE_PUBLICACAO`, ou quando as linhas não trazem a data). `origem`: só
    quando a chave repete a de outra seção (as relações da rede); senão, a de `ORIGEM_DOS_ITENS`."""
    return {
        "chave": chave,
        "nome": nome,
        "valor": valor,
        "unidade": unidade,
        "base": base,
        "rastro": _rastro(origem or ORIGEM_DOS_ITENS[chave], publicado_em, fontes),
    }


def _rastro(
    origem: "Origem", publicado_em: str | None, fontes: Iterable[str]
) -> dict[str, Any]:
    """O rastro do item como vai no JSON. `fontes`: as famílias, quando o item junta mais de uma (a
    rede); sem elas, a da tabela. Chave sem origem é erro de código (a seção quebra no teste)."""
    familias = list(dict.fromkeys(fontes)) or [TABELAS[origem.tabela].familia_da_fonte]
    return {
        "formula": origem.formula,
        "versao_do_calculo": CALCULO_DO_DOSSIE,
        "fonte_id": familias[0],
        "outras_fontes": familias[1:],
        "publicado_em": publicado_em,
    }


def _publicado(linhas: pd.DataFrame, tabela: str) -> str | None:
    """O dia em que a linha mais nova de `linhas` ficou pública, pela coluna `publico_em` que o
    dicionário dá à `tabela` (None: sem linhas ou sem a coluna)."""
    coluna = TABELAS[tabela].datas.get("publico_em")
    if linhas.empty or coluna is None or coluna not in linhas.columns:
        return None
    return _data(pd.to_datetime(linhas[coluna]).max())


def _mais_novo(*dias: str | None) -> str | None:
    """O mais novo dos dias ISO (None: nenhum)."""
    return max((d for d in dias if d), default=None)


def _secao(
    chave: str,
    itens: list[dict[str, Any]],
    tabelas: Mapping[str, pd.DataFrame],
    paragrafos: list[str] | None = None,
    fontes: list[str] | None = None,
) -> dict[str, Any]:
    registro = _SECAO_POR_CHAVE[chave]
    return {
        "chave": chave,
        "titulo": registro.titulo,
        "itens": itens,
        "tabelas": {nome: _registros(t) for nome, t in tabelas.items() if not t.empty},
        "paragrafos": [*(paragrafos or []), LIMITES[chave]],
        "fontes": fontes_das_tabelas(registro.tabelas) if fontes is None else fontes,
    }


def _mais_recente(tabela: pd.DataFrame) -> pd.DataFrame:
    """As linhas do documento mais recente (maior referência e, nela, a maior versão)."""
    if tabela.empty:
        return tabela
    ultima = tabela["referencia"].max()
    do_ultimo = tabela[tabela["referencia"] == ultima]
    return do_ultimo[do_ultimo["versao"] == do_ultimo["versao"].max()]


# --- auditor e controladas -----------------------------------------------------------------------


def _e_pessoa(nome: object, pessoas: set[str]) -> bool:
    return normalizar_nome(nome) in pessoas


def _nome_do_auditor(linha: pd.Series, pessoas: set[str]) -> str:
    """O nome da firma; o de um auditor pessoa física não aparece (sem CNPJ de firma ou nome de pessoa)."""
    cnpj = re.sub(r"\D", "", str(linha.get("auditor_cnpj") or ""))
    firma = len(cnpj) == DIGITOS_DO_CNPJ or str(linha.get("auditor_id", "")).startswith(
        "rede:"
    )
    if not firma or _e_pessoa(linha["auditor"], pessoas):
        return AUDITOR_PESSOA
    return str(linha["auditor"])


def _itens_do_auditor(
    auditores: pd.DataFrame, pessoas: set[str]
) -> list[dict[str, Any]]:
    if auditores.empty:
        return []
    em_curso = _mais_recente(auditores)
    em_curso = em_curso[em_curso["fim"].isna()].sort_values("inicio")
    if em_curso.empty:
        return []
    atual = em_curso.iloc[-1]
    base = _data(atual["referencia"])
    publicado = _publicado(em_curso.iloc[[-1]], "auditores")
    return [
        _item(
            "auditor_atual",
            "Auditor atual",
            _nome_do_auditor(atual, pessoas),
            "texto",
            base,
            publicado_em=publicado,
        ),
        _item(
            "auditor_desde",
            "Auditor desde",
            _data(atual["inicio"]),
            "data",
            base,
            publicado_em=publicado,
        ),
    ]


def _trocas_sem_pessoas(trocas: pd.DataFrame, pessoas: set[str]) -> pd.DataFrame:
    if trocas.empty:
        return trocas
    tabela = trocas[["efetiva_em", "anterior", "novo", "anos_com_o_anterior"]].copy()
    for coluna in ("anterior", "novo"):
        tabela[coluna] = tabela[coluna].map(
            lambda nome: AUDITOR_PESSOA if _e_pessoa(nome, pessoas) else nome
        )
    return tabela.sort_values("efetiva_em", ascending=False)


def _e_controlada(sociedades: pd.DataFrame) -> pd.Series:
    """Controlada pelo tipo do FRE ou, quando o tipo vem vazio (os FREs recentes), por mais da metade."""
    tipo = sociedades["tipo"].fillna("").astype(str).str.strip().str.lower()
    participacao = pd.to_numeric(sociedades["participacao"], errors="coerce")
    return (tipo == "controlada") | (
        (tipo == "") & (participacao > PARTICIPACAO_DE_CONTROLE)
    )


def cnpjs_do_grupo(cnpj: str, controladas: pd.DataFrame) -> set[str]:
    """A companhia e as controladas do FRE mais recente (só dígitos): quem emite pelo grupo."""
    ultimas = _mais_recente(controladas)
    if ultimas.empty:
        return {cnpj}
    das_controladas = digitos(ultimas.loc[_e_controlada(ultimas), "cnpj"].dropna())
    return {cnpj, *(c for c in das_controladas if len(c) == DIGITOS_DO_CNPJ)}


def _controladas_do_ultimo_fre(
    controladas: pd.DataFrame,
) -> tuple[pd.DataFrame, str | None]:
    ultimas = _mais_recente(controladas)
    if ultimas.empty:
        return ultimas, None
    tabela = (
        ultimas[["razao_social", "tipo", "participacao"]]
        .assign(razao_social=lambda t: tirar_cpf_da_coluna(t["razao_social"]))
        .assign(controlada=_e_controlada(ultimas))
        .sort_values("participacao", ascending=False)
    )
    return tabela, _data(ultimas["referencia"].iloc[0])


def secao_auditor_e_controladas(
    auditores: pd.DataFrame,
    trocas: pd.DataFrame,
    controladas: pd.DataFrame,
    controladoras_da_empresa: pd.DataFrame,
    pessoas: set[str],
) -> dict[str, Any] | None:
    """Quem audita, as trocas de auditor, as controladas e coligadas e quem controla (None: nada)."""
    itens = _itens_do_auditor(auditores, pessoas)
    tabela_de_controladas, base = _controladas_do_ultimo_fre(controladas)
    if not tabela_de_controladas.empty:
        sao_controladas = int(tabela_de_controladas["controlada"].sum())
        total = len(tabela_de_controladas)
        publicado = _publicado(_mais_recente(controladas), "controladas")
        itens += [
            _item("sociedades", "Sociedades no FRE", total, "empresas", base, publicado_em=publicado),
            _item("controladas", "Controladas", sao_controladas, "empresas", base, publicado_em=publicado),
            _item(
                "coligadas_e_outras",
                "Coligadas e outras participações",
                total - sao_controladas,
                "empresas",
                base,
                publicado_em=publicado,
            ),
        ]  # fmt: skip
    tabelas = {
        "trocas_de_auditor": _trocas_sem_pessoas(trocas, pessoas),
        "controladas": tabela_de_controladas,
        "controladoras": controladoras_da_empresa.drop(columns="cnpj", errors="ignore"),
    }
    if not itens and all(t.empty for t in tabelas.values()):
        return None
    return _secao("auditor_e_controladas", itens, tabelas)


def controladoras(
    ligacoes: pd.DataFrame, entidades: pd.DataFrame, identificadores: pd.DataFrame
) -> pd.DataFrame:
    """Quem controla cada companhia hoje pela rede (FRE da controladora): cnpj, controladora, participação.

    Só ligações vigentes; nenhuma entidade tratada como pessoa. Sem datas de fim: o `ate` da rede ainda
    pode olhar o futuro (achado na Ultrapar), e aqui só importa a situação de hoje.
    """
    cnpjs = identificadores[
        (identificadores["sistema"] == "cnpj") & identificadores["ate"].isna()
    ][["id_entidade", "valor"]].rename(columns={"id_entidade": "de", "valor": "cnpj"})
    cnpjs_das_controladoras = cnpjs.rename(
        columns={"de": "para", "cnpj": "cnpj_controladora"}
    )
    vigentes = ligacoes[
        (ligacoes["tipo"] == "controlada_de")
        & (ligacoes["situacao"] == "vigente")
        & (ligacoes["fonte"] == "cvm-fre")
    ]
    nomes = entidades[~entidades["trata_como_pessoa"].fillna(True).astype(bool)][
        ["id_entidade", "nome"]
    ].rename(columns={"id_entidade": "para", "nome": "controladora"})
    tabela = (
        vigentes.merge(cnpjs, on="de")
        .merge(nomes, on="para")
        .merge(cnpjs_das_controladoras, on="para", how="left")
    )
    return tabela[
        ["cnpj", "controladora", "participacao", "cnpj_controladora"]
    ].reset_index(drop=True)


def controladoras_em_dia(
    controladoras: pd.DataFrame, controladas: pd.DataFrame, hoje: pd.Timestamp
) -> pd.DataFrame:
    """Só as controladoras cujo FRE mais recente é dos últimos anos e ainda lista a empresa como controlada.

    A rede guarda a ligação como vigente enquanto ninguém a encerra: a controladora que parou de
    entregar o FRE (a VBC Energia, que deixou a CPFL em 2011) continuaria aparecendo como dona hoje.
    """
    if controladoras.empty or controladas.empty:
        return pd.DataFrame(columns=["cnpj", "controladora", "participacao"])
    limite = hoje.tz_localize(None) - pd.DateOffset(years=ANOS_DO_FRE_EM_DIA)
    listadas = set()
    for cnpj_controladora, fres in controladas.groupby(
        digitos(controladas["cnpj_companhia"])
    ):
        ultimo = _mais_recente(fres)
        if ultimo.empty or pd.Timestamp(ultimo["referencia"].iloc[0]) < limite:
            continue
        como_controlada = ultimo[_e_controlada(ultimo)]
        listadas |= {
            (str(cnpj_controladora), c)
            for c in digitos(como_controlada["cnpj"].dropna())
        }
    pares = zip(
        controladoras["cnpj_controladora"], digitos(controladoras["cnpj"]), strict=True
    )
    em_dia = [
        isinstance(dona, str) and (re.sub(r"\D", "", dona), empresa) in listadas
        for dona, empresa in pares
    ]
    return controladoras.loc[
        em_dia, ["cnpj", "controladora", "participacao"]
    ].reset_index(drop=True)


# --- ofertas e fundos ----------------------------------------------------------------------------


def _numero(valores: pd.Series) -> pd.Series:
    return pd.to_numeric(valores, errors="coerce")


def _ofertas(ofertas_160: pd.DataFrame, ofertas_antigas: pd.DataFrame) -> pd.DataFrame:
    """As ofertas das duas tabelas da CVM numa só, da mais nova para a mais velha."""
    partes = []
    if not ofertas_160.empty:
        partes.append(
            pd.DataFrame(
                {
                    "data": ofertas_160["data_registro"].fillna(
                        ofertas_160["data_requerimento"]
                    ),
                    "regime": "Res. 160",
                    "emissor": ofertas_160.get("nome_emissor"),
                    "valor_mobiliario": ofertas_160["valor_mobiliario"],
                    "tipo_oferta": ofertas_160["tipo_oferta"],
                    "valor_total": _numero(ofertas_160["valor_total_registrado"]),
                    "situacao": ofertas_160["status_requerimento"],
                }
            )
        )
    if not ofertas_antigas.empty:
        partes.append(
            pd.DataFrame(
                {
                    "data": ofertas_antigas["data_registro_oferta"].fillna(
                        ofertas_antigas["data_protocolo"]
                    ),
                    "regime": "anterior à Res. 160",
                    "emissor": ofertas_antigas.get("nome_emissor"),
                    "valor_mobiliario": ofertas_antigas["tipo_ativo"],
                    "tipo_oferta": ofertas_antigas["tipo_oferta"],
                    "valor_total": _numero(ofertas_antigas["valor_total"]),
                    "situacao": None,
                }
            )
        )
    if not partes:
        return pd.DataFrame()
    juntas = pd.concat(partes, ignore_index=True)
    juntas["data"] = pd.to_datetime(juntas["data"])
    return juntas.sort_values("data", ascending=False, ignore_index=True)


def _ofertas_por_ano(ofertas: pd.DataFrame) -> pd.DataFrame:
    if ofertas.empty:
        return ofertas
    por_ano = ofertas.groupby(ofertas["data"].dt.year.rename("ano")).agg(
        ofertas=("regime", "size"), valor_total=("valor_total", "sum")
    )
    return (
        por_ano.reset_index().sort_values("ano", ascending=False).head(ANOS_NAS_SERIES)
    )


def ultimo_mes_completo(cobertura: pd.DataFrame) -> pd.Timestamp | None:
    """O último mês do CDA com as carteiras já entregues (None: sem a tabela de cobertura).

    Os fundos entregam a carteira com até 90 dias de atraso, então os meses mais novos ainda crescem.
    Só o rabo da série é cortado: do fim para trás, sai cada mês com menos de 60% da mediana dos 12
    anteriores. Uma queda no meio da série (crise de mercado) não é carteira faltando.
    """
    if cobertura.empty:
        return None
    serie = cobertura.sort_values("competencia").reset_index(drop=True)
    valores = pd.to_numeric(serie["valor_comprado"], errors="coerce")
    for posicao in range(len(serie) - 1, -1, -1):
        anteriores = valores.iloc[
            max(0, posicao - MESES_PARA_A_MEDIANA) : posicao
        ].dropna()
        if len(anteriores) < MESES_MINIMOS_NA_MEDIANA:
            return pd.Timestamp(serie["competencia"].iloc[posicao])
        if valores.iloc[posicao] >= FRACAO_DO_MES_COMPLETO * anteriores.median():
            return pd.Timestamp(serie["competencia"].iloc[posicao])
    return None


def _fundos(
    painel: pd.DataFrame, ultimo_mes: pd.Timestamp | None = None
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Quantos fundos têm a ação e quanto, no último mês completo, e a série dos últimos meses."""
    if painel.empty:
        return [], painel
    if ultimo_mes is not None:
        painel = painel[pd.to_datetime(painel["competencia"]) <= ultimo_mes]
    comprado = painel[painel["tipo"] == "comprado"].sort_values("competencia")
    if comprado.empty:
        return [], comprado
    ultimo = comprado.iloc[-1]
    base = _data(ultimo["competencia"])
    publicado = _publicado(comprado.iloc[[-1]], "painel_dos_fundos")
    itens = [
        _item(
            "fundos_com_a_acao",
            "Fundos com a empresa na carteira",
            int(ultimo["fundos"]),
            "fundos",
            base,
            publicado_em=publicado,
        ),
        _item(
            "valor_nos_fundos",
            "Valor nas carteiras dos fundos",
            float(ultimo["valor"]),
            "R$",
            base,
            publicado_em=publicado,
        ),
    ]
    serie = comprado[["competencia", "fundos", "valor"]].tail(MESES_DOS_FUNDOS)
    return itens, serie


def secao_ofertas_e_fundos(
    ofertas_160: pd.DataFrame,
    ofertas_antigas: pd.DataFrame,
    painel: pd.DataFrame,
    ultimo_mes_completo: pd.Timestamp | None = None,
) -> dict[str, Any] | None:
    """As ofertas registradas na CVM e os fundos que têm a empresa na carteira (None: nada)."""
    ofertas = _ofertas(ofertas_160, ofertas_antigas)
    itens, fundos_por_mes = _fundos(painel, ultimo_mes_completo)
    if ofertas.empty and not itens:
        return None
    if not ofertas.empty:
        publicado = _mais_novo(
            _publicado(ofertas_160, "ofertas_resolucao_160"),
            _publicado(ofertas_antigas, "ofertas_antigas"),
        )
        itens.insert(
            0,
            _item(
                "ofertas",
                "Ofertas registradas na CVM",
                len(ofertas),
                "ofertas",
                _data(ofertas["data"].max()),
                publicado_em=publicado,
            ),
        )
    tabelas = {
        "ofertas": ofertas.head(LINHAS_NAS_LISTAS),
        "ofertas_por_ano": _ofertas_por_ano(ofertas),
        "fundos_por_mes": fundos_por_mes,
    }
    return _secao("ofertas_e_fundos", itens, tabelas)


# --- geração de caixa (série T1) -----------------------------------------------------------------

DOCUMENTO_ANUAL = "DFP"
NUMEROS_DO_CAIXA = {  # coluna da T1 → nome do item (só os que existem no último exercício)
    "ebitda": "EBITDA do último exercício",
    "capex": "Capex do último exercício",
    "fcf": "Fluxo de caixa livre (FCF) do último exercício",
}
COLUNAS_DO_CAIXA = [
    "exercicio",
    "fim",
    "receita",
    "ebitda",
    "margem_ebitda",
    "depreciacao_amortizacao",
    "caixa_operacional",
    "capex",
    "fcf",
    "divulgado_em",
]


def _publicas_no_dia(como_era: pd.DataFrame, hoje: pd.Timestamp) -> pd.DataFrame:
    """As linhas da DFP já divulgadas no dia, do consolidado (ou do individual, se não há)."""
    anuais = como_era[
        (como_era["documento"] == DOCUMENTO_ANUAL)
        & (pd.to_datetime(como_era["divulgado_em"]) <= hoje)
    ]
    grupo = "con" if (anuais["grupo"] == "con").any() else "ind"
    return anuais[anuais["grupo"] == grupo].assign(
        divulgado_em=lambda t: pd.to_datetime(t["divulgado_em"])
    )


def _receitas(linhas: pd.DataFrame) -> pd.DataFrame:
    """A receita (DRE 3.01) de cada período, na versão mais nova já divulgada."""
    receitas = linhas[(linhas["demonstracao"] == "DRE") & (linhas["conta"] == RECEITA)]
    receitas = receitas.sort_values("divulgado_em").drop_duplicates(
        t1.PERIODO, keep="last"
    )
    return receitas.set_index(t1.PERIODO)[["valor"]].rename(
        columns={"valor": "receita"}
    )


def _caixa_por_exercicio(linhas: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por exercício (o mais novo primeiro), com a margem sobre a receita da mesma DRE."""
    numeros = t1.indicadores_de_caixa(linhas)
    if numeros.empty:
        return numeros
    tabela = numeros.join(_receitas(linhas), on=t1.PERIODO)
    receita = tabela["receita"].where(tabela["receita"] > 0)
    tabela = tabela.assign(
        exercicio=pd.to_datetime(tabela["fim"]).dt.year,
        margem_ebitda=tabela["ebitda"] / receita,
    )
    tabela = tabela.sort_values("exercicio", ascending=False)
    return tabela[COLUNAS_DO_CAIXA].head(ANOS_NAS_SERIES).reset_index(drop=True)


def secao_geracao_de_caixa(
    como_era: pd.DataFrame, hoje: pd.Timestamp
) -> dict[str, Any] | None:
    """EBITDA, capex e FCF de cada DFP, como eram públicos no dia (None: a base não tem a DFC).

    `como_era`: as linhas da DFP (DRE, DFC e DVA) de `demonstracoes_como_era`, de todas as versões; a
    seção fica com a mais nova já divulgada em `hoje`. Número sem a linha fica vazio e não vira item.
    """
    if como_era.empty:
        return None
    tabela = _caixa_por_exercicio(_publicas_no_dia(como_era, hoje))
    if tabela.empty:
        return None
    ultimo = tabela.iloc[0]
    base = _data(ultimo["fim"])
    publicado = _publicado(tabela.iloc[[0]], "demonstracoes_como_era")
    itens = [
        _item(chave, nome, float(ultimo[chave]), "R$", base, publicado_em=publicado)
        for chave, nome in NUMEROS_DO_CAIXA.items()
        if pd.notna(ultimo[chave])
    ]
    tabelas = {"caixa_por_exercicio": tabela.astype(object).where(tabela.notna(), None)}
    return _secao("geracao_de_caixa", itens, tabelas)


# --- qualidade do lucro --------------------------------------------------------------------------

LINHAS_DO_RELEASE = {
    "receita_liquida": "Receita líquida",
    "lucro_liquido_controladores": "Lucro dos controladores",
    "resultado_operacional": "Resultado operacional",
}
CLASSES_COMPARADAS = ("igual", "igual (arredondamento)", "diferente")
CLASSES_DO_RELEASE = (*CLASSES_COMPARADAS, "release não mostra", "sem ITR")
LUCRO_DO_PERIODO, RECEITA_DA_DRE = "Lucro do período", "Receita"
# a receita e as contas onde o lucro costuma ficar (ele é achado pela descrição, `regras.LINHA_DO_LUCRO`)
CONTAS_DA_DRE = (RECEITA, "3.09", "3.11", "3.13")
PORCENTO = 100.0


def _linhas_da_dre(como_era: pd.DataFrame) -> pd.DataFrame:
    """O lucro do período e a receita da DFP, no consolidado (ou no individual, se não há)."""
    dfp = como_era[
        (como_era["demonstracao"] == "DRE") & (como_era["documento"] == "DFP")
    ]
    grupo = "con" if (dfp["grupo"] == "con").any() else "ind"
    dfp = dfp[dfp["grupo"] == grupo]
    descricao = dfp["descricao"].fillna("").astype(str).str.strip()
    lucro = descricao.str.match(LINHA_DO_LUCRO)
    receita = dfp["conta"] == RECEITA
    escolhidas = dfp[lucro | receita]
    return escolhidas.assign(
        linha=lucro[lucro | receita].map(
            {True: LUCRO_DO_PERIODO, False: RECEITA_DA_DRE}
        ),
        exercicio=pd.to_datetime(escolhidas["fim"]).dt.year,
        divulgado_em=pd.to_datetime(escolhidas["divulgado_em"]),
    )


def _refeita(
    exercicio: int, linha: str, versoes: pd.DataFrame
) -> dict[str, Any] | None:
    """A primeira e a última versão de uma linha de um exercício, se mudou mais que o arredondamento."""
    versoes = versoes.sort_values("divulgado_em")
    primeira, atual = versoes.iloc[0], versoes.iloc[-1]
    primeiro_valor, valor_atual = float(primeira["valor"]), float(atual["valor"])
    diferenca = valor_atual - primeiro_valor
    if abs(diferenca) <= TOLERANCIA_EM_REAIS:
        return None
    return {
        "exercicio": exercicio,
        "linha": linha,
        "primeiro_valor": primeiro_valor,
        "primeiro_em": primeira["divulgado_em"],
        "valor_atual": valor_atual,
        "trocado_em": atual["divulgado_em"],
        "diferenca": diferenca,
        "diferenca_pct": (
            PORCENTO * diferenca / abs(primeiro_valor) if primeiro_valor else None
        ),
    }


def _reapresentacoes(
    como_era: pd.DataFrame, hoje: pd.Timestamp
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Quantos exercícios a ficha olhou e quais tiveram o lucro ou a receita refeitos depois.

    Sem olhar o futuro: só o que já tinha sido divulgado até `hoje`; o valor "de hoje" é o último
    divulgado até lá, não o que a base sabe agora.
    """
    if como_era.empty:
        return [], pd.DataFrame()
    linhas = _linhas_da_dre(como_era)
    linhas = linhas[linhas["divulgado_em"] <= hoje]
    if linhas.empty:
        return [], pd.DataFrame()
    linhas = linhas[linhas["exercicio"] > linhas["exercicio"].max() - ANOS_NAS_SERIES]
    refeitas = [
        _refeita(int(exercicio), str(linha), versoes)
        for (exercicio, linha, _), versoes in linhas.groupby(
            ["exercicio", "linha", "conta"], sort=False
        )
    ]
    tabela = pd.DataFrame([r for r in refeitas if r is not None])
    if not tabela.empty:
        tabela = tabela.sort_values(
            ["trocado_em", "exercicio"], ascending=False, ignore_index=True
        )
    base = (
        tabela["trocado_em"].max() if not tabela.empty else linhas["divulgado_em"].max()
    )
    publicado = _publicado(linhas, "demonstracoes_como_era")
    itens = [
        _item(
            "exercicios_reapresentados",
            "Exercícios com o lucro ou a receita refeitos depois de publicados",
            int(tabela["exercicio"].nunique()) if not tabela.empty else 0,
            "exercícios",
            _data(base),
            publicado_em=publicado,
        ),
        _item(
            "exercicios_olhados",
            "Exercícios olhados (DFP)",
            int(linhas["exercicio"].nunique()),
            "exercícios",
            _data(linhas["divulgado_em"].max()),
            publicado_em=publicado,
        ),
    ]
    return itens, tabela


def _releases(
    releases: pd.DataFrame, hoje: pd.Timestamp
) -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame]]:
    """O release de resultado contra o ITR ou a DFP: quantos valores deu para comparar e os diferentes."""
    if releases.empty:
        return [], {}
    releases = releases[pd.to_datetime(releases["publico_em"]) <= hoje]
    if releases.empty:
        return [], {}
    # o release reentregue (versão nova) substitui o anterior do mesmo período
    releases = releases.sort_values(["data_entrega", "versao"]).drop_duplicates(
        ["periodo", "linha", "periodo_lido", "leitura"], keep="last"
    )
    comparados = releases[releases["classe"].isin(CLASSES_COMPARADAS)]
    diferentes = comparados[comparados["classe"] == "diferente"]
    base = _data(pd.to_datetime(releases["publico_em"]).max())
    publicado = _publicado(releases, "release_x_oficial")
    itens = [
        _item(
            "releases_comparados",
            "Valores do release comparados com o ITR ou a DFP",
            len(comparados),
            "valores",
            base,
            publicado_em=publicado,
        ),
        _item(
            "releases_diferentes",
            "Valores do release diferentes do oficial",
            len(diferentes),
            "valores",
            base,
            publicado_em=publicado,
        ),
    ]
    por_classe = releases["classe"].value_counts().reindex(CLASSES_DO_RELEASE).dropna()
    colunas = [
        "periodo",
        "referencia",
        "linha",
        "valor_release_reais",
        "valor_oficial_reais",
        "diferenca_pct",
        "link",
    ]
    tabelas = {
        "releases_diferentes": diferentes.assign(
            linha=diferentes["linha"].map(LINHAS_DO_RELEASE)
        )
        .sort_values("referencia", ascending=False)[colunas]
        .head(LINHAS_NAS_LISTAS),
        "releases_por_classe": pd.DataFrame(
            {"classe": por_classe.index, "valores": por_classe.astype(int).to_numpy()}
        ),
    }
    return itens, tabelas


def _trocas_recentes(trocas: pd.DataFrame, hoje: pd.Timestamp) -> list[dict[str, Any]]:
    """Quantas vezes a empresa trocou de auditor nos últimos 10 anos (a lista está no auditor)."""
    if trocas.empty:
        return []
    conhecidas = trocas[pd.to_datetime(trocas["conhecido_em"]) <= hoje]
    efetiva = pd.to_datetime(conhecidas["efetiva_em"])
    recentes = efetiva[efetiva > hoje - pd.DateOffset(years=ANOS_NAS_SERIES)]
    if recentes.empty:
        return []
    return [
        _item(
            "trocas_de_auditor_10_anos",
            "Trocas de auditor nos últimos 10 anos",
            len(recentes),
            "trocas",
            _data(recentes.max()),
            publicado_em=_publicado(
                conhecidas.loc[recentes.index], "trocas_de_auditor"
            ),
        )
    ]


def secao_qualidade_do_lucro(
    como_era: pd.DataFrame,
    releases: pd.DataFrame,
    trocas: pd.DataFrame,
    hoje: pd.Timestamp,
) -> dict[str, Any] | None:
    """Reapresentações, o release contra o oficial e as trocas de auditor (None: nada disso)."""
    itens_da_dre, reapresentacoes = _reapresentacoes(como_era, hoje)
    itens_do_release, tabelas_do_release = _releases(releases, hoje)
    itens = [*itens_da_dre, *itens_do_release, *_trocas_recentes(trocas, hoje)]
    if not itens:
        return None
    tabelas = {"reapresentacoes": reapresentacoes, **tabelas_do_release}
    return _secao("qualidade_do_lucro", itens, tabelas)


# --- capital e acionistas ------------------------------------------------------------------------

TESOURARIA = "companhia"  # o cargo da própria empresa no VLMO: recompra, não insider
JANELAS = ("últimos 12 meses", "12 meses anteriores")


def _janela(datas: pd.Series, ate: pd.Timestamp, anos_antes: int = 0) -> pd.Series:
    """As datas dentro dos 12 meses que terminam em `ate` (ou `anos_antes` anos antes)."""
    fim = ate - pd.DateOffset(years=anos_antes)
    return (datas > fim - pd.DateOffset(years=1)) & (datas <= fim)


def _soma(negociacoes: pd.DataFrame, operacao: str) -> float:
    return float(negociacoes.loc[negociacoes["operacao"] == operacao, "valor"].sum())


def _somas_dos_insiders(negociacoes: pd.DataFrame) -> dict[str, float | int]:
    insiders = negociacoes[negociacoes["cargo"] != TESOURARIA]
    tesouraria = negociacoes[negociacoes["cargo"] == TESOURARIA]
    return {
        "compras": _soma(insiders, "compra"),
        "vendas": _soma(insiders, "venda"),
        "recompras": _soma(tesouraria, "compra"),
        "negociacoes": len(insiders),
    }


def _por_cargo(negociacoes: pd.DataFrame) -> pd.DataFrame:
    """Compras e vendas somadas por tipo de cargo: nunca por pessoa (ADRs 0018 e 0075)."""
    if negociacoes.empty:
        return pd.DataFrame()
    linhas = [
        {
            "cargo": CARGOS.get(str(cargo), str(cargo)),
            "compras": _soma(do_cargo, "compra"),
            "vendas": _soma(do_cargo, "venda"),
            "negociacoes": len(do_cargo),
        }
        for cargo, do_cargo in negociacoes.groupby("cargo", sort=False)
    ]
    return pd.DataFrame(linhas).sort_values(
        ["compras", "vendas"], ascending=False, ignore_index=True
    )


def _insiders(
    negociacoes: pd.DataFrame, hoje: pd.Timestamp
) -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame]]:
    """Compras e vendas declaradas nos 12 meses até hoje, por cargo, e as dos 12 meses anteriores.

    Só as declarações já entregues até hoje: a negociação do mês ainda sem formulário fica de fora.
    """
    if negociacoes.empty:
        return [], {}
    entregues = negociacoes[pd.to_datetime(negociacoes["entregue_em"]) <= hoje]
    datas = pd.to_datetime(entregues["data"])
    do_ano = entregues[_janela(datas, hoje)]
    somas = _somas_dos_insiders(do_ano)
    base = _data(hoje)
    # a declaração mais nova já entregue: também a que diz "nada nos 12 meses"
    publicado = _publicado(entregues, "negociacoes")
    itens = [
        _item("insiders_compras_12m", "Compras de insiders em 12 meses", somas["compras"], "R$", base, publicado_em=publicado),
        _item("insiders_vendas_12m", "Vendas de insiders em 12 meses", somas["vendas"], "R$", base, publicado_em=publicado),
        _item("recompras_12m", "Recompras da própria empresa em 12 meses", somas["recompras"], "R$", base, publicado_em=publicado),
    ]  # fmt: skip
    janelas = pd.DataFrame(
        [
            {
                "janela": JANELAS[anos_antes],
                "ate": hoje - pd.DateOffset(years=anos_antes),
            }
            | _somas_dos_insiders(entregues[_janela(datas, hoje, anos_antes)])
            for anos_antes in range(len(JANELAS))
        ]
    )
    tabelas = {"insiders_por_cargo": _por_cargo(do_ano), "insiders_janelas": janelas}
    return itens, tabelas


def _eventos_de_capital(
    eventos: pd.DataFrame, hoje: pd.Timestamp
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Os eventos de capital dos últimos 10 anos, cada um uma vez (o FRE de cada ano os repete)."""
    if eventos.empty:
        return [], pd.DataFrame()
    eventos = eventos.assign(data=pd.to_datetime(eventos["data"]))
    eventos = eventos[
        (eventos["data"] <= hoje)
        & (eventos["data"] > hoje - pd.DateOffset(years=ANOS_NAS_SERIES))
    ]
    if eventos.empty:
        return [], pd.DataFrame()
    unicos = eventos.sort_values(["referencia", "versao"]).drop_duplicates(
        ["tipo", "data"], keep="last"
    )
    tabela = unicos.sort_values("data", ascending=False, ignore_index=True)[
        ["data", "tipo", "fator", "acoes_novas", "valor"]
    ]
    item = _item(
        "eventos_de_capital",
        "Eventos de capital nos últimos 10 anos",
        len(tabela),
        "eventos",
        _data(tabela["data"].max()),
        publicado_em=None,  # a tabela não guarda a entrega do FRE (`ITENS_SEM_DATA_DE_PUBLICACAO`)
    )
    return [item], tabela.head(LINHAS_NAS_LISTAS)


def _movimento_dos_fundos(
    painel: pd.DataFrame, ultimo_mes: pd.Timestamp | None
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """O que os fundos compraram e venderam nos 12 últimos meses completos e nos 12 anteriores."""
    if painel.empty or not {"compras", "vendas"} <= set(painel.columns):
        return [], pd.DataFrame()
    comprado = painel[painel["tipo"] == "comprado"]
    comprado = comprado.assign(competencia=pd.to_datetime(comprado["competencia"]))
    if ultimo_mes is not None:
        comprado = comprado[comprado["competencia"] <= ultimo_mes]
    if comprado.empty:
        return [], pd.DataFrame()
    ate = comprado["competencia"].max()
    linhas = []
    for anos_antes in range(len(JANELAS)):
        no_ano = comprado[_janela(comprado["competencia"], ate, anos_antes)]
        linhas.append(
            {
                "janela": JANELAS[anos_antes],
                "ate": ate - pd.DateOffset(years=anos_antes),
                "compras": float(no_ano["compras"].sum()),
                "vendas": float(no_ano["vendas"].sum()),
            }
        )
    base = _data(ate)
    publicado = _publicado(comprado, "painel_dos_fundos")
    itens = [
        _item("compras_dos_fundos_12m", "Compras dos fundos em 12 meses", linhas[0]["compras"], "R$", base, publicado_em=publicado),
        _item("vendas_dos_fundos_12m", "Vendas dos fundos em 12 meses", linhas[0]["vendas"], "R$", base, publicado_em=publicado),
    ]  # fmt: skip
    return itens, pd.DataFrame(linhas)


def secao_capital_e_acionistas(
    negociacoes: pd.DataFrame,
    eventos: pd.DataFrame,
    painel: pd.DataFrame,
    hoje: pd.Timestamp,
    ultimo_mes_completo: pd.Timestamp | None = None,
) -> dict[str, Any] | None:
    """Insiders, eventos de capital e o movimento dos fundos (None: nada disso)."""
    itens_dos_insiders, tabelas_dos_insiders = _insiders(negociacoes, hoje)
    itens_dos_eventos, eventos_de_capital = _eventos_de_capital(eventos, hoje)
    itens_dos_fundos, fundos_janelas = _movimento_dos_fundos(
        painel, ultimo_mes_completo
    )
    itens = [*itens_dos_insiders, *itens_dos_eventos, *itens_dos_fundos]
    if not itens:
        return None
    tabelas = {
        **tabelas_dos_insiders,
        "eventos_de_capital": eventos_de_capital,
        "fundos_janelas": fundos_janelas,
    }
    return _secao("capital_e_acionistas", itens, tabelas)


# --- governança ----------------------------------------------------------------------------------

# no FRE o conselheiro que também é diretor vem como "Pertence à Diretoria e ao Conselho de Administração"
DO_CONSELHO = re.compile(r"conselho de administra", re.IGNORECASE)
ANOS_DA_GOVERNANCA = 5  # quantos FREs (e exercícios da remuneração) as tabelas mostram
ITENS_DA_GOVERNANCA = (  # chave do item, coluna de `governanca_por_ano`, nome, unidade
    ("conselho_membros", "conselho", "Membros do conselho de administração", "pessoas"),
    ("conselho_independentes", "independentes", "Conselheiros independentes", "pessoas"),
    ("conselho_eleitos_por_minoritarios", "eleitos_por_minoritarios",
     "Conselheiros eleitos por minoritários", "pessoas"),
    ("comites", "comites", "Comitês informados no FRE", "comitês"),
    ("mulheres_no_conselho", "mulheres_no_conselho", "Mulheres no conselho de administração",
     "pessoas"),
)  # fmt: skip


def _entregues(tabela: pd.DataFrame, hoje: pd.Timestamp) -> pd.DataFrame:
    """As linhas dos FREs já entregues até hoje, na versão mais nova de cada referência."""
    if tabela.empty:
        return tabela
    entregues = tabela[pd.to_datetime(tabela["conhecido_em"]) <= hoje]
    ultima = entregues.groupby("referencia")["versao"].transform("max")
    return entregues[entregues["versao"] == ultima]


def _do_conselho(tabela: pd.DataFrame) -> pd.DataFrame:
    return tabela[tabela["orgao"].fillna("").astype(str).str.contains(DO_CONSELHO)]


def _governanca_por_ano(
    conselho: pd.DataFrame, comites: pd.DataFrame, diversidade: pd.DataFrame
) -> pd.DataFrame:
    """Um FRE por linha (o mais novo primeiro): o tamanho do conselho, os comitês e as mulheres."""
    if conselho.empty:
        return pd.DataFrame()
    por_ano = (
        _do_conselho(conselho)
        .groupby("referencia")
        .agg(
            entregue_em=("conhecido_em", "max"),
            conselho=("membros", "sum"),
            independentes=("independentes", "sum"),
            eleitos_por_minoritarios=("eleitos_por_minoritarios", "sum"),
        )
    )
    if not comites.empty:
        por_ano["comites"] = comites.groupby("referencia")["tipo_de_comite"].nunique()
    if not diversidade.empty:
        mulheres = (
            _do_conselho(diversidade).groupby("referencia")["genero_feminino"].sum()
        )
        por_ano["mulheres_no_conselho"] = mulheres
    por_ano = por_ano.sort_index(ascending=False).head(ANOS_DA_GOVERNANCA).reset_index()
    por_ano.insert(0, "ano", pd.to_datetime(por_ano.pop("referencia")).dt.year)
    por_ano["entregue_em"] = pd.to_datetime(por_ano["entregue_em"])
    return por_ano


def _itens_da_governanca(por_ano: pd.DataFrame) -> list[dict[str, Any]]:
    if por_ano.empty:
        return []
    mais_novo = por_ano.iloc[0]
    base = _data(mais_novo["entregue_em"])
    return [  # a data-base já é a entrega do FRE: o dia em que ficou público
        _item(chave, nome, int(mais_novo[coluna]), unidade, base, publicado_em=base)
        for chave, coluna, nome, unidade in ITENS_DA_GOVERNANCA
        if coluna in por_ano.columns and pd.notna(mais_novo[coluna])
    ]


def _comites_do_fre(comites: pd.DataFrame) -> pd.DataFrame:
    """Os comitês do FRE mais novo, só o tipo e quantos membros."""
    if comites.empty:
        return pd.DataFrame()
    do_fre = comites[comites["referencia"] == comites["referencia"].max()]
    tabela = do_fre.rename(columns={"tipo_de_comite": "comite"})[["comite", "membros"]]
    return tabela.sort_values("comite", ignore_index=True)


def _por_exercicio(tabela: pd.DataFrame, hoje: pd.Timestamp) -> pd.DataFrame:
    """Cada exercício já encerrado como o FRE mais novo entregue até hoje o informa (sem a prevista)."""
    entregues = _entregues(tabela, hoje)
    if entregues.empty:
        return entregues
    encerrados = entregues[pd.to_datetime(entregues["fim_do_exercicio"]) <= hoje]
    mais_novo = encerrados.groupby("fim_do_exercicio")["referencia"].transform("max")
    return encerrados[encerrados["referencia"] == mais_novo]


def _remuneracao(
    remuneracao: pd.DataFrame, extremos: pd.DataFrame, hoje: pd.Timestamp
) -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame]]:
    """O total pago à administração em cada exercício e, no último, por órgão com os extremos."""
    exercicios = _por_exercicio(remuneracao, hoje)
    if exercicios.empty:
        return [], {}
    totais = (
        exercicios.groupby("fim_do_exercicio")["total_remuneracao"]
        .sum()
        .sort_index(ascending=False)
    )
    ultimo = totais.index[0]
    do_ultimo = exercicios[exercicios["fim_do_exercicio"] == ultimo]
    itens = [
        _item(
            "remuneracao_da_administracao",
            "Remuneração da administração no último exercício",
            float(totais.iloc[0]),
            "R$",
            _data(ultimo),
            publicado_em=_publicado(do_ultimo, "fre_remuneracao"),
        )
    ]
    por_exercicio = pd.DataFrame(
        {"exercicio": pd.to_datetime(totais.index).year, "total": totais.to_numpy()}
    ).head(ANOS_DA_GOVERNANCA)
    por_orgao = do_ultimo[["orgao", "membros_remunerados", "total_remuneracao"]].rename(
        columns={"total_remuneracao": "total"}
    )
    extremos = _por_exercicio(extremos, hoje)
    if not extremos.empty:
        do_ano = extremos[extremos["fim_do_exercicio"] == ultimo]
        por_orgao = por_orgao.merge(
            do_ano[["orgao", "maior", "media", "menor"]], on="orgao", how="left"
        )
    tabelas = {
        "remuneracao_por_exercicio": por_exercicio,
        "remuneracao_por_orgao": por_orgao.reset_index(drop=True),
    }
    return itens, tabelas


def secao_governanca(
    conselho: pd.DataFrame,
    comites: pd.DataFrame,
    remuneracao: pd.DataFrame,
    extremos: pd.DataFrame,
    diversidade: pd.DataFrame,
    hoje: pd.Timestamp,
) -> dict[str, Any] | None:
    """Conselho, comitês, remuneração e diversidade pelo FRE, só contagens e somas (None: nada)."""
    conselho, comites, diversidade = (
        _entregues(tabela, hoje) for tabela in (conselho, comites, diversidade)
    )
    por_ano = _governanca_por_ano(conselho, comites, diversidade)
    itens_da_remuneracao, tabelas_da_remuneracao = _remuneracao(
        remuneracao, extremos, hoje
    )
    itens = [*_itens_da_governanca(por_ano), *itens_da_remuneracao]
    if not itens:
        return None
    tabelas = {
        "governanca_por_ano": por_ano,
        "comites": _comites_do_fre(comites),
        **tabelas_da_remuneracao,
    }
    return _secao("governanca", itens, tabelas)


# --- crédito -------------------------------------------------------------------------------------

EXTRAIDO = (
    "extraido"  # rating lido do documento (`base.ratings`): os outros não têm nota
)
MESMO_RATING = [
    "agencia",
    "escala",
    "nota",
    "data_acao",
]  # o relatório e o fato relevante
ASSEMBLEIA = (
    "assembleia"  # o aviso de pagamento e a notificação do agente não são assembleia
)
TEMAS_DAS_ASSEMBLEIAS = {  # coluna `tema_*` de `debentures_assembleias` → nome na ficha
    "vencimento_antecipado": "Vencimento antecipado",
    "waiver": "Waiver",
    "covenant": "Covenant",
    "repactuacao": "Repactuação",
    "inadimplemento": "Inadimplemento",
    "garantia": "Garantia",
    "resgate": "Resgate antecipado",
    "reorganizacao": "Reorganização",
}


def _ratings_publicos(ratings: pd.DataFrame, hoje: pd.Timestamp) -> pd.DataFrame:
    """Cada ação de agência já pública até hoje, uma vez (o mesmo evento em dois documentos)."""
    if ratings.empty:
        return ratings
    publicos = ratings[
        (pd.to_datetime(ratings["publico_em"]) <= hoje)
        & (ratings["situacao_extracao"] == EXTRAIDO)
    ]
    publicos = publicos.sort_values("publico_em", kind="stable")
    com_data = publicos[publicos["data_acao"].notna()]
    sem_data = publicos[publicos["data_acao"].isna()]
    unicos = pd.concat([com_data.drop_duplicates(MESMO_RATING), sem_data])
    return unicos.assign(publico_em=pd.to_datetime(unicos["publico_em"]))


def _acoes_de_rating(ratings: pd.DataFrame) -> dict[str, int]:
    return {
        "acoes": len(ratings),
        "rebaixamentos": int((ratings["acao"] == "rebaixamento").sum()),
        "elevacoes": int((ratings["acao"] == "elevacao").sum()),
    }


def _ratings(
    ratings: pd.DataFrame, hoje: pd.Timestamp
) -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame]]:
    """A última ação de cada agência e as ações dos 12 meses até hoje contra as dos 12 anteriores."""
    publicos = _ratings_publicos(ratings, hoje)
    if publicos.empty:
        return [], {}
    ultimas = (
        publicos.sort_values("publico_em", kind="stable")
        .drop_duplicates(["agencia", "escala"], keep="last")
        .sort_values("publico_em", ascending=False, ignore_index=True)
    )
    por_agencia = ultimas.drop(columns="nota").rename(
        columns={"nota_original": "nota"}
    )[["agencia", "escala", "nota", "perspectiva", "acao", "publico_em", "link"]]
    janelas = pd.DataFrame(
        [
            {
                "janela": JANELAS[anos_antes],
                "ate": hoje - pd.DateOffset(years=anos_antes),
            }
            | _acoes_de_rating(
                publicos[_janela(publicos["publico_em"], hoje, anos_antes)]
            )
            for anos_antes in range(len(JANELAS))
        ]
    )
    do_ano = janelas.iloc[0]
    base = _data(hoje)
    publicado = _publicado(publicos, "ratings")
    itens = [
        _item("ratings_rebaixamentos_12m", "Rebaixamentos de rating em 12 meses", int(do_ano["rebaixamentos"]), "ações", base, publicado_em=publicado),
        _item("ratings_elevacoes_12m", "Elevações de rating em 12 meses", int(do_ano["elevacoes"]), "ações", base, publicado_em=publicado),
    ]  # fmt: skip
    return itens, {"ratings": por_agencia, "ratings_janelas": janelas}


def _assembleias_publicas(
    assembleias: pd.DataFrame, hoje: pd.Timestamp
) -> pd.DataFrame:
    """As assembleias de debenturistas já públicas até hoje, na versão mais nova de cada documento."""
    if assembleias.empty:
        return assembleias
    publicas = assembleias[
        (pd.to_datetime(assembleias["publico_em"]) <= hoje)
        & (assembleias["documento"] == ASSEMBLEIA)
    ]
    ultimas = publicas.sort_values(["protocolo", "versao"]).drop_duplicates(
        "protocolo", keep="last"
    )
    return ultimas.assign(publico_em=pd.to_datetime(ultimas["publico_em"]))


def _com_o_tema(documentos: pd.DataFrame, tema: str) -> int:
    return int(documentos[f"tema_{tema}"].fillna(False).astype(bool).sum())


def _por_tema(do_ano: pd.DataFrame, do_ano_anterior: pd.DataFrame) -> pd.DataFrame:
    """Quantos documentos falam de cada tema (pelo assunto que a empresa escreveu), nas 2 janelas."""
    colunas = ["tema", "ultimos_12_meses", "12_meses_anteriores"]
    linhas = [
        (nome, _com_o_tema(do_ano, tema), _com_o_tema(do_ano_anterior, tema))
        for tema, nome in TEMAS_DAS_ASSEMBLEIAS.items()
        if f"tema_{tema}" in do_ano.columns
    ]
    tabela = pd.DataFrame(linhas, columns=colunas)
    tabela = tabela[
        (tabela["ultimos_12_meses"] > 0) | (tabela["12_meses_anteriores"] > 0)
    ]
    return tabela.sort_values(
        colunas[1:], ascending=False, kind="stable", ignore_index=True
    )


def _assembleias(
    assembleias: pd.DataFrame, hoje: pd.Timestamp
) -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame]]:
    """Assembleias de debenturistas nos 12 meses até hoje e nos 12 anteriores, por tema."""
    publicas = _assembleias_publicas(assembleias, hoje)
    if publicas.empty:
        return [], {}
    do_ano, do_ano_anterior = (
        publicas[_janela(publicas["publico_em"], hoje, anos_antes)]
        for anos_antes in range(len(JANELAS))
    )
    janelas = pd.DataFrame(
        [
            {
                "janela": JANELAS[anos_antes],
                "ate": hoje - pd.DateOffset(years=anos_antes),
                "documentos": len(janela),
            }
            for anos_antes, janela in enumerate((do_ano, do_ano_anterior))
        ]
    )
    recentes = publicas.sort_values("publico_em", ascending=False, ignore_index=True)
    item = _item(
        "assembleias_de_debenturistas_12m",
        "Documentos de assembleias de debenturistas em 12 meses",
        len(do_ano),
        "documentos",
        _data(hoje),
        publicado_em=_publicado(publicas, "debentures_assembleias"),
    )
    tabelas = {
        "assembleias_janelas": janelas,
        "assembleias_por_tema": _por_tema(do_ano, do_ano_anterior),
        "assembleias_recentes": recentes[
            ["publico_em", "especie", "assunto", "link"]
        ].head(LINHAS_NAS_LISTAS),
    }
    return [item], tabelas


def secao_credito(
    ratings: pd.DataFrame, assembleias: pd.DataFrame, hoje: pd.Timestamp
) -> dict[str, Any] | None:
    """Ratings e assembleias de debenturistas, só fatos com data e fonte (None: nada disso)."""
    itens_dos_ratings, tabelas_dos_ratings = _ratings(ratings, hoje)
    itens_das_assembleias, tabelas_das_assembleias = _assembleias(assembleias, hoje)
    itens = [*itens_dos_ratings, *itens_das_assembleias]
    if not itens:
        return None
    return _secao("credito", itens, {**tabelas_dos_ratings, **tabelas_das_assembleias})


# --- setor regulado ------------------------------------------------------------------------------


def serie_anual(
    tabela: pd.DataFrame, modo: str, meses_por_periodo: int = 1
) -> pd.DataFrame:
    """De (competencia, chave, valor) por mês para (ano, chave, valor) por ano; a coluna `abertura`
    (a modalidade), quando vem, continua separada.

    `SOMA_DO_ANO` soma os meses (passageiros, prêmios); `ULTIMO_MES` fica com o último mês que a fonte
    tem em cada ano (consumidores, acessos: um estoque, que não se soma). `meses_por_periodo`: quanto
    cada data vale (a data-base trimestral do IF.data vale 3, e as 4 do ano fazem o ano completo).
    Com a coluna `publicado_em` (quando cada mês ficou público), cada ano leva a mais nova.
    """
    ano = tabela["competencia"].dt.year
    # quantos meses a fonte tem em cada ano e qual o último: o ano corrente ainda está pela metade
    meses = tabela.groupby(ano)["competencia"].agg(meses="nunique", ultimo_mes="max")
    meses["meses"] *= meses_por_periodo
    if "publicado_em" in tabela.columns:  # o mês mais novo do ano que já ficou público
        meses["publicado_em"] = tabela.groupby(ano)["publicado_em"].max()
    if modo == ULTIMO_MES:
        ultimo = tabela.groupby(ano)["competencia"].transform("max")
        tabela, ano = (
            tabela[tabela["competencia"] == ultimo],
            ano[tabela["competencia"] == ultimo],
        )
    abertura = ["abertura"] if "abertura" in tabela.columns else []
    por = [ano.rename("ano"), "chave", *abertura]
    somada = tabela.groupby(por)["valor"].sum().reset_index()
    return somada.merge(meses.rename_axis("ano").reset_index(), on="ano")


SEM_FIM = float("inf")


def _ultimo_ano_da_ligacao(ligacoes: pd.DataFrame) -> pd.Series:
    """Até que ano a ligação conta a entidade para a companhia.

    A B13 diz se a ligação ainda aparece nas entregas do FRE (`vigente`). Quando acabou, ou a
    companhia parou de entregar, vale até o ano da última entrega que a mostrou
    (`ultima_referencia`): o dono do momento, não o de hoje (decisão de 28/10/2026). Sem as colunas
    (a ligação dos bancos, por exemplo) ou vigente, não há fim. Quando a ligação começou não entra:
    a estrutura que o FRE mostra vale também para os anos anteriores à primeira entrega.
    """
    sem_fim = pd.Series(SEM_FIM, index=ligacoes.index)
    if "vigente" not in ligacoes or "ultima_referencia" not in ligacoes:
        return sem_fim
    ano = pd.to_datetime(ligacoes["ultima_referencia"], errors="coerce").dt.year
    acabou = ~ligacoes["vigente"].fillna(True).astype(bool)
    return sem_fim.mask(acabou & ano.notna(), ano)


def _vigentes_no_ano(ligacoes: pd.DataFrame, ano: int) -> pd.DataFrame:
    return ligacoes[_ultimo_ano_da_ligacao(ligacoes) >= ano]


def _chaves(
    ligacoes: pd.DataFrame, serie: SerieDaAgencia, ano: int | None = None
) -> set[str]:
    principais = ligacoes[
        (ligacoes["fonte"] == serie.fonte_b13) & ligacoes["principal"]
    ]
    if ano is not None:
        principais = _vigentes_no_ano(principais, ano)
    valores = principais["chave"].astype(str).str.strip()
    return set(digitos(valores) if serie.chave_em_digitos else valores)


def _chaves_por_ano(
    ligacoes: pd.DataFrame, serie: SerieDaAgencia, anos: Iterable[int]
) -> dict[int, set[str]]:
    """As entidades que contam para a companhia em cada ano (só os anos que têm alguma)."""
    por_ano = {int(ano): _chaves(ligacoes, serie, int(ano)) for ano in anos}
    return {ano: chaves for ano, chaves in por_ano.items() if chaves}


def _participacao_por_ano(
    dados: pd.DataFrame, chaves: set[str] | Mapping[int, set[str]]
) -> pd.DataFrame:
    dados = dados.assign(chave=dados["chave"].astype(str).str.strip())
    total = dados.groupby("ano")["valor"].sum()
    if isinstance(chaves, Mapping):
        da_empresa_no_ano = [
            c in chaves.get(a, ())
            for a, c in zip(dados["ano"], dados["chave"], strict=True)
        ]
        da_empresa = dados[da_empresa_no_ano].groupby("ano")["valor"].sum()
    else:
        da_empresa = dados[dados["chave"].isin(chaves)].groupby("ano")["valor"].sum()
    # só os anos em que a empresa tem número: a divisão alinharia com todos os anos do mercado
    tabela = pd.DataFrame(
        {"valor": da_empresa, "participacao": da_empresa / total}
    ).dropna(subset=["valor"])
    periodo = dados.groupby("ano")[["meses", "ultimo_mes"]].first()
    tabela = tabela.join(periodo)
    return (
        tabela.reset_index().sort_values("ano", ascending=False).head(ANOS_NAS_SERIES)
    )


COLUNAS_DAS_ENTIDADES_LIGADAS = [
    "fonte",
    "nome",
    "via",
    "desde",
    "ate",
    "ate_publico_em",
    "vigente",
]


def _entidades_ligadas(ligacoes: pd.DataFrame) -> pd.DataFrame:
    principais = ligacoes[ligacoes["principal"]]
    colunas = [c for c in COLUNAS_DAS_ENTIDADES_LIGADAS if c in principais]
    return principais[colunas].sort_values(["fonte", "nome"])


def _linha_do_item(
    serie: SerieDaAgencia, tabela: pd.DataFrame
) -> tuple[pd.Series, str]:
    """A linha do item e a base: o último mês (estoque) ou o último ano completo (soma; o corrente
    engana). `tabela` vem do ano mais novo para o mais velho."""
    if serie.modo == ULTIMO_MES:
        linha = tabela.iloc[0]
        return linha, pd.Timestamp(linha["ultimo_mes"]).strftime("%Y-%m")
    completos = tabela[tabela["meses"] == MESES_NO_ANO]
    linha = completos.iloc[0] if not completos.empty else tabela.iloc[0]
    return linha, str(int(linha["ano"]))


def _publicado_no_ano(dados: pd.DataFrame, ano: object) -> str | None:
    """Quando o mês mais novo do `ano` ficou público, de todo o mercado (`serie_anual`)."""
    if "publicado_em" not in dados.columns:
        return None
    return _data(pd.to_datetime(dados.loc[dados["ano"] == ano, "publicado_em"]).max())


def _item_da_serie(
    serie: SerieDaAgencia, tabela: pd.DataFrame, dados: pd.DataFrame
) -> dict[str, Any]:
    linha, base = _linha_do_item(serie, tabela)
    return _item(
        serie.nome,
        serie.medida,
        float(linha["valor"]),
        serie.unidade,
        base,
        publicado_em=_publicado_no_ano(dados, linha["ano"]),
    )


def secao_setor_regulado(
    ligacoes_b13: pd.DataFrame, series: Mapping[str, pd.DataFrame]
) -> dict[str, Any] | None:
    """Os números da agência que regula a empresa, somadas as entidades dela (None: sem agência).

    `ligacoes_b13` são as linhas de `empresa_serie` da companhia; `series`, por `SerieDaAgencia.nome`,
    (ano, chave, valor) de todo o mercado, para a participação.
    """
    if ligacoes_b13.empty:
        return None
    itens, tabelas = [], {}
    for serie in SERIES_DAS_AGENCIAS:
        dados = series.get(serie.nome)
        if dados is None or dados.empty:
            continue
        chaves = _chaves_por_ano(ligacoes_b13, serie, dados["ano"].unique())
        if not chaves:
            continue
        tabela = _participacao_por_ano(dados, chaves)
        if tabela.empty:
            continue
        tabelas[serie.nome] = tabela
        itens.append(_item_da_serie(serie, tabela, dados))
    if not tabelas:
        return None
    tabelas["entidades_ligadas"] = _entidades_ligadas(ligacoes_b13)
    return _secao(
        "setor_regulado", itens, tabelas, fontes=fontes_do_setor(tabelas.keys())
    )


# --- setor (molde D) ------------------------------------------------------------------------------

POR_GRUPO, POR_COMPANHIA, POR_ENTIDADE = "grupo", "companhia", "entidade"
AVISO_POR_ENTIDADE = (
    "Parte do mercado está contada por entidade: as que a base não liga a uma companhia aberta e de "
    "que a agência não informa o grupo. Um grupo fechado com várias entidades aparece partido, e elas "
    "parecem menores do que o grupo é: a concentração real é maior ou igual à mostrada."
)
AVISO_DE_MERCADO_REGIONAL = (
    "As empresas deste setor competem por região (estado, cidade, tipo de contratação): o total "
    "nacional mede a escala de cada uma, não a competição no mercado relevante, que pode ser bem "
    "mais concentrado."
)
_SEM_MEMBROS = pd.DataFrame(columns=["cnpj", "empresa", "motivo"])


def _ligacoes_principais(
    empresa_serie: pd.DataFrame, fontes: Iterable[str]
) -> pd.DataFrame:
    """As ligações principais das fontes, com a chave limpa e o CNPJ da companhia só em dígitos."""
    if empresa_serie.empty:
        return pd.DataFrame(columns=["fonte", "chave", "cnpj"])
    ligacoes = empresa_serie[
        empresa_serie["fonte"].isin(list(fontes))
        & empresa_serie["principal"].fillna(False).astype(bool)
    ]
    return ligacoes.assign(
        chave=ligacoes["chave"].astype(str).str.strip(),
        cnpj=digitos(ligacoes["cnpj_companhia"]),
    )


COLUNAS_DA_B13 = (
    "fonte",
    "chave",
    "nome",
    "cnpj_companhia",
    "via",
    "principal",
    "desde",
)


def ligacoes_dos_bancos(
    ligacao: pd.DataFrame, chaves: set[str], hoje: pd.Timestamp
) -> pd.DataFrame:
    """A `ligacao_dos_bancos` no formato da tabela empresa ↔ série (B13), para o setor dos bancos.

    Só os conglomerados das séries (`chaves`: o mesmo banco no tipo 2 não conta duas vezes), ligados
    à companhia aberta pela data-base mais nova já pública no dia; `desde` é a 1ª data-base da ligação.
    Como na B13, a estrutura de hoje vale também nos anos passados.
    """
    if ligacao.empty:
        return pd.DataFrame(columns=list(COLUNAS_DA_B13))
    ligacao = ligacao.assign(
        cod_inst=ligacao["cod_inst"].astype(str).str.strip(),
        cnpj=ligacao["cnpj"].fillna("").astype(str).str.strip(),
    )
    publica = pd.to_datetime(ligacao["data_base"]) + pd.Timedelta(
        days=DIAS_ATE_FICAR_PUBLICO
    )
    ligacao = ligacao[(publica <= hoje) & ligacao["cod_inst"].isin(chaves)]
    ultima = ligacao.sort_values("data_base").drop_duplicates("cod_inst", keep="last")
    ligadas = ultima[ultima["cnpj"] != ""]
    desde = ligacao.groupby(["cod_inst", "cnpj"])["data_base"].min().rename("desde")
    ligadas = ligadas.join(desde, on=["cod_inst", "cnpj"])
    return pd.DataFrame(
        {
            "fonte": FONTE_DO_IFDATA,
            "chave": ligadas["cod_inst"],
            "nome": ligadas["instituicao"],
            "cnpj_companhia": digitos(ligadas["cnpj"]),
            "via": ligadas["ligado_por"],
            "principal": True,
            "desde": pd.to_datetime(ligadas["desde"]),
        },
        columns=list(COLUNAS_DA_B13),
    ).reset_index(drop=True)


def membros_do_setor(
    setor: SetorDoLancamento, empresas: pd.DataFrame, empresa_serie: pd.DataFrame
) -> pd.DataFrame:
    """As companhias com ticker (`empresas`: cnpj em dígitos, empresa) ligadas à agência do setor,
    com o motivo; vazia se nenhuma."""
    ligacoes = _ligacoes_principais(empresa_serie, setor.fontes_b13)
    if ligacoes.empty or empresas.empty:
        return _SEM_MEMBROS
    entidades = ligacoes.groupby("cnpj")["chave"].nunique()
    membros = empresas[empresas["cnpj"].isin(entidades.index)]
    motivo = [
        f"ligada {setor.contracao} {setor.agencia} por {n} "
        f"{'entidade' if n == 1 else 'entidades'}"
        for n in membros["cnpj"].map(entidades)
    ]
    return (
        membros.assign(motivo=motivo)[["cnpj", "empresa", "motivo"]]
        .sort_values("empresa")
        .reset_index(drop=True)
    )


def _companhia_de_cada_entidade(
    serie: SerieDaAgencia, empresa_serie: pd.DataFrame
) -> dict[str, str]:
    """Entidade → companhia aberta. Ligada a duas (a holding e a controlada, ambas abertas), fica com
    a que junta mais entidades da fonte: a entidade conta uma vez só."""
    ligacoes = _ligacoes_principais(empresa_serie, (serie.fonte_b13,))
    if ligacoes.empty:
        return {}
    if serie.chave_em_digitos:
        ligacoes = ligacoes.assign(chave=digitos(ligacoes["chave"]))
    tamanho = ligacoes.groupby("cnpj")["chave"].transform("nunique")
    escolhidas = (
        ligacoes.assign(tamanho=tamanho)
        .sort_values(["tamanho", "cnpj"], ascending=[False, True])
        .drop_duplicates("chave")
    )
    return dict(zip(escolhidas["chave"], escolhidas["cnpj"], strict=True))


def grupos_por_ano(mensais: pd.DataFrame) -> pd.DataFrame:
    """De (competencia, chave, grupo, valor) por mês para (ano, chave, grupo): o grupo que a agência
    informa no último mês de cada entidade no ano (com dois, o de mais valor); sem grupo, fica de fora."""
    if mensais.empty:
        return pd.DataFrame(columns=["ano", "chave", "grupo"])
    mensais = mensais.assign(
        ano=mensais["competencia"].dt.year,
        grupo=mensais["grupo"].fillna("").astype(str).str.strip(),
    )
    ultimo = mensais.groupby(["ano", "chave"])["competencia"].transform("max")
    do_ultimo = mensais[(mensais["competencia"] == ultimo) & (mensais["grupo"] != "")]
    escolhidos = do_ultimo.sort_values(
        ["ano", "chave", "valor"], ascending=[True, True, False]
    ).drop_duplicates(["ano", "chave"])
    return escolhidos[["ano", "chave", "grupo"]].reset_index(drop=True)


def _grupo_da_agencia(dados: pd.DataFrame, grupos: pd.DataFrame | None) -> pd.Series:
    """O grupo econômico que a agência informa para cada linha (vazio quando não informa)."""
    if grupos is None or grupos.empty:
        return pd.Series(pd.NA, index=dados.index, dtype="object")
    grupo = dados[["ano", "chave"]].merge(
        grupos.assign(chave=grupos["chave"].astype(str).str.strip()),
        on=["ano", "chave"],
        how="left",
    )["grupo"]
    grupo.index = dados.index
    return grupo.where(grupo.astype(str).str.strip() != "")


def _companhia_em_cada_ano(
    serie: SerieDaAgencia, dados: pd.DataFrame, empresa_serie: pd.DataFrame
) -> pd.Series:
    """A companhia a que cada linha (ano, entidade) pertence: a do dono do momento, e sem companhia
    (entidade solta) quando a ligação já tinha acabado naquele ano."""
    por_ano = {
        int(ano): _companhia_de_cada_entidade(
            serie, _vigentes_no_ano(empresa_serie, int(ano))
        )
        for ano in dados["ano"].unique()
    }
    companhias = [
        por_ano[int(a)].get(c)
        for a, c in zip(dados["ano"], dados["chave"], strict=True)
    ]
    return pd.Series(companhias, index=dados.index, dtype=object)


def participantes(
    serie: SerieDaAgencia,
    dados: pd.DataFrame,
    empresa_serie: pd.DataFrame,
    grupos: pd.DataFrame | None,
) -> pd.DataFrame:
    """De (ano, chave, valor, meses, ultimo_mes) por entidade para (ano, participante, por, valor,
    meses, ultimo_mes): o grupo da agência, senão a companhia aberta, senão a própria entidade. No
    IF.data a entidade já é o grupo (o conglomerado prudencial): cada uma é um participante."""
    dados = dados.assign(chave=dados["chave"].astype(str).str.strip())
    companhia = _companhia_em_cada_ano(serie, dados, empresa_serie)
    grupo = (
        dados["chave"] if serie.chave_e_o_grupo else _grupo_da_agencia(dados, grupos)
    )
    participante = ("entidade:" + dados["chave"]).mask(
        companhia.notna(), "companhia:" + companhia.astype(str)
    )
    participante = participante.mask(grupo.notna(), "grupo:" + grupo.astype(str))
    por = pd.Series(POR_ENTIDADE, index=dados.index)
    por = por.mask(companhia.notna(), POR_COMPANHIA).mask(grupo.notna(), POR_GRUPO)
    periodo = dados.groupby("ano")[["meses", "ultimo_mes"]].first()
    somados = (
        dados.assign(participante=participante, por=por)
        .groupby(["ano", "participante", "por"], as_index=False)["valor"]
        .sum()
    )
    return somados.join(periodo, on="ano")


def _concentracao_da_serie(quem: pd.DataFrame) -> pd.DataFrame:
    """A concentração por ano, com a fração do mercado contada por entidade solta."""
    tabela = concentracao.concentracao_por_ano(quem)
    soltas = quem[quem["por"] == POR_ENTIDADE].groupby("ano")["valor"].sum()
    tabela["por_entidade"] = tabela["ano"].map(soltas).fillna(0.0) / tabela["total"]
    return tabela.head(ANOS_NAS_SERIES)


def _itens_da_concentracao(
    serie: SerieDaAgencia, tabela: pd.DataFrame, dados: pd.DataFrame
) -> list[dict[str, Any]]:
    linha, base = _linha_do_item(serie, tabela)
    nome, publicado = serie.nome, _publicado_no_ano(dados, linha["ano"])
    return [
        _item(f"mercado_{nome}", f"Mercado: {serie.medida}", float(linha["total"]), serie.unidade, base, publicado_em=publicado),
        _item(f"hhi_{nome}", f"HHI: {serie.medida}", float(linha["hhi"]), "pontos", base, publicado_em=publicado),
        _item(
            f"cr4_{nome}",
            f"Participação das 4 maiores (CR4): {serie.medida}",
            float(linha["cr4"]),
            "fração",
            base,
            publicado_em=publicado,
        ),
    ]  # fmt: skip


def _participacao_dos_membros(
    serie: SerieDaAgencia,
    dados: pd.DataFrame,
    membros: pd.DataFrame,
    empresa_serie: pd.DataFrame,
) -> pd.DataFrame:
    """A participação de cada membro por ano, com a mesma conta do setor regulado da ficha dele."""
    ligacoes = empresa_serie.assign(cnpj=digitos(empresa_serie["cnpj_companhia"]))
    partes = []
    for membro in membros.itertuples(index=False):
        chaves = _chaves_por_ano(
            ligacoes[ligacoes["cnpj"] == membro.cnpj], serie, dados["ano"].unique()
        )
        tabela = _participacao_por_ano(dados, chaves) if chaves else pd.DataFrame()
        if not tabela.empty:
            partes.append(
                tabela.assign(
                    serie=serie.nome, cnpj=membro.cnpj, empresa=membro.empresa
                )
            )
    if not partes:
        return pd.DataFrame()
    colunas = [
        "serie",
        "cnpj",
        "empresa",
        "ano",
        "valor",
        "participacao",
        "meses",
        "ultimo_mes",
    ]
    return pd.concat(partes, ignore_index=True)[colunas]


def _lado_a_lado(
    serie: SerieDaAgencia,
    dados: pd.DataFrame,
    membros: pd.DataFrame,
    empresa_serie: pd.DataFrame,
) -> pd.DataFrame:
    """O número de cada membro por entidade e ano, sem somar as entidades (um índice não se soma) nem
    dividir pelo mercado, nos últimos anos; a modalidade (`abertura`) continua separada."""
    ligacoes = _ligacoes_principais(empresa_serie, (serie.fonte_b13,))
    entidades = (
        ligacoes.assign(_ate=_ultimo_ano_da_ligacao(ligacoes))
        .merge(membros[["cnpj", "empresa"]], on="cnpj")[
            ["cnpj", "empresa", "chave", "nome", "_ate"]
        ]
        .rename(columns={"nome": "entidade"})
    )
    tabela = dados.assign(chave=dados["chave"].astype(str).str.strip()).merge(
        entidades, on="chave"
    )
    tabela = tabela[tabela["ano"] <= tabela["_ate"]].drop(columns="_ate")
    if tabela.empty:
        return pd.DataFrame()
    anos = sorted(tabela["ano"].unique(), reverse=True)[:ANOS_NAS_SERIES]
    abertura = ["abertura"] if "abertura" in tabela.columns else []
    colunas = ["cnpj", "empresa", "chave", "entidade", "ano", *abertura, "valor"]
    return (
        tabela[tabela["ano"].isin(anos)]
        .assign(serie=serie.nome)[["serie", *colunas, "ultimo_mes"]]
        .sort_values(
            ["empresa", "ano", *abertura],
            ascending=[True, False] + [True] * len(abertura),
        )
        .reset_index(drop=True)
    )


def _tabelas_lado_a_lado(
    setor: SetorDoLancamento,
    series: Mapping[str, pd.DataFrame],
    membros: pd.DataFrame,
    empresa_serie: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """`lado_a_lado_<serie>` de cada série do lado a lado que tem número de algum membro."""
    tabelas = {}
    for nome in setor.lado_a_lado:
        dados = series.get(nome)
        if dados is None or dados.empty:
            continue
        tabela = _lado_a_lado(_SERIE_POR_NOME[nome], dados, membros, empresa_serie)
        if not tabela.empty:
            tabelas[f"lado_a_lado_{nome}"] = tabela
    return tabelas


def secao_setor(
    setor: SetorDoLancamento,
    membros: pd.DataFrame,
    series: Mapping[str, pd.DataFrame],
    empresa_serie: pd.DataFrame,
    grupos: Mapping[str, pd.DataFrame],
) -> dict[str, Any] | None:
    """O mercado do setor: tamanho, CR4 e HHI por ano, a participação dos membros e quem são
    (None: setor sem membros ou sem série).

    `series` e `grupos` são de todo o mercado, por `SerieDaAgencia.nome`; `grupos` (ano, chave,
    grupo) só das agências que informam o grupo econômico.
    """
    if membros.empty:
        return None
    itens = [  # a ligação à agência não guarda quando ficou pública (`ITENS_SEM_DATA_DE_PUBLICACAO`)
        _item("setor", "Setor", setor.nome, "", None, publicado_em=None),
        _item(
            "membros",
            "Companhias abertas da base ligadas à agência",
            len(membros),
            "companhias",
            None,
            publicado_em=None,
        ),
    ]
    tabelas: dict[str, pd.DataFrame] = {}
    participacoes, usadas, tem_entidade_solta = [], [], False
    for nome in setor.series:
        dados = series.get(nome)
        if dados is None or dados.empty:
            continue
        serie = _SERIE_POR_NOME[nome]
        quem = participantes(serie, dados, empresa_serie, grupos.get(nome))
        tabela = _concentracao_da_serie(quem)
        tabelas[f"concentracao_{nome}"] = tabela
        tem_entidade_solta |= bool(tabela["por_entidade"].iloc[0] > 0)
        itens += _itens_da_concentracao(serie, tabela, dados)
        participacoes.append(
            _participacao_dos_membros(serie, dados, membros, empresa_serie)
        )
        usadas.append(nome)
    if not usadas:
        return None
    tabelas["participacao_dos_membros"] = pd.concat(participacoes, ignore_index=True)
    tabelas["membros"] = membros
    lado_a_lado = _tabelas_lado_a_lado(setor, series, membros, empresa_serie)
    tabelas |= lado_a_lado
    usadas += [nome.removeprefix("lado_a_lado_") for nome in lado_a_lado]
    paragrafos = [
        *([AVISO_POR_ENTIDADE] if tem_entidade_solta else []),
        *([AVISO_DE_MERCADO_REGIONAL] if setor.mercado_regional else []),
    ]
    return _secao("setor", itens, tabelas, paragrafos, fontes=fontes_do_setor(usadas))


# --- negócios ------------------------------------------------------------------------------------


LIGACOES_CERTAS_DO_MA = frozenset({"nome_exato", "nome_fantasia"})
TIPOS_DE_COMPRA = frozenset({"AQ_CONTROLE", "AQ_MINORITARIA", "VENDA_ATIVO", "PE_VC"})
# o papel da empresa no negócio; vale o primeiro de `ORDEM_DOS_PAPEIS` quando ela aparece em mais de um
PAPEIS_DO_MA = {"comprador": "comprou", "vendedor": "vendeu", "alvo": "foi_comprada"}
OUTRO_PAPEL_DO_MA = "outro"
ORDEM_DOS_PAPEIS = ("comprou", "vendeu", "foi_comprada", OUTRO_PAPEL_DO_MA)
FONTES_DO_MA = ("assessoria", "wayback")  # as páginas das assessorias e a prova da data
ITENS_DO_MA = (
    ("comprou", "ma_comprou", "Negócios de M&A em que comprou ou investiu"),
    ("vendeu", "ma_vendeu", "Negócios de M&A em que vendeu"),
    ("foi_comprada", "ma_foi_comprada", "Negócios de M&A em que foi comprada ou recebeu investimento"),
)  # fmt: skip
COLUNAS_DO_MA = ["id_negocio", "papel", "tipo", "conhecido_em", "confirmado"]


def negocios_de_ma_por_empresa(
    partes: pd.DataFrame,
    negocios: pd.DataFrame,
    datas: pd.DataFrame,
    assessorias: pd.DataFrame,
    hoje: str,
) -> dict[str, pd.DataFrame]:
    """Os negócios de M&A das assessorias de cada empresa (raiz do CNPJ), como eram conhecidos em `hoje`.

    Só entra a parte ligada à empresa por nome exato e o negócio cuja prova de data é de `hoje` para
    trás (sem olhar o futuro). Um negócio publicado por duas assessorias conta uma vez, com o papel
    mais forte da empresa nele. Sem nomes, valores nem a outra parte: só o que se agrega.
    """
    if any(t.empty for t in (partes, negocios, datas, assessorias)):
        return {}
    ligadas = partes[
        partes["ligacao_por"].isin(LIGACOES_CERTAS_DO_MA)
        & partes["cnpj_raiz"].fillna("").astype(str).ne("")
    ]
    if ligadas.empty:
        return {}
    chave = ["assessoria", "url"]
    juntas = (
        ligadas[[*chave, "papel", "cnpj_raiz"]]
        .merge(negocios[[*chave, "id_negocio"]], on=chave)
        .merge(datas[[*chave, "conhecido_em_do_negocio", "confirmado_por"]], on=chave)
        .merge(assessorias[[*chave, "tipo"]], on=chave)
    )
    # a base traz o momento em UTC (com fuso); `hoje` é um dia sem fuso: compara-se pelo dia de UTC
    juntas["conhecido_em"] = pd.to_datetime(
        juntas["conhecido_em_do_negocio"], utc=True
    ).dt.tz_localize(None)
    juntas = juntas[
        juntas["conhecido_em"].notna() & (juntas["conhecido_em"] <= pd.Timestamp(hoje))
    ].copy()
    papel = juntas["papel"].map(PAPEIS_DO_MA)
    juntas["papel"] = papel.where(juntas["tipo"].isin(TIPOS_DE_COMPRA)).fillna(
        OUTRO_PAPEL_DO_MA
    )
    juntas["confirmado"] = juntas["confirmado_por"].notna()
    juntas["_forca"] = juntas["papel"].map(ORDEM_DOS_PAPEIS.index)
    unicas = juntas.sort_values(["_forca", "conhecido_em"]).drop_duplicates(
        ["cnpj_raiz", "id_negocio"]
    )
    return {
        str(raiz): linhas[COLUNAS_DO_MA] for raiz, linhas in unicas.groupby("cnpj_raiz")
    }


def _tabelas_do_ma(ma: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Os negócios de M&A por ano em que ficaram conhecidos, e os mais recentes (sem a outra parte)."""
    ano = ma["conhecido_em"].dt.year.rename("ano")
    por_ano = (
        ma.groupby([ano, "papel"]).size().unstack(fill_value=0)
        .reindex(columns=list(ORDEM_DOS_PAPEIS), fill_value=0)
        .reset_index()
        .sort_values("ano", ascending=False)
        .head(ANOS_NAS_SERIES)
    )  # fmt: skip
    recentes = ma.sort_values("conhecido_em", ascending=False).head(LINHAS_NAS_LISTAS)
    return {
        "ma_por_ano": por_ano,
        "ma_recentes": recentes[["conhecido_em", "papel", "tipo", "confirmado"]],
    }


def _itens_do_ma(ma: pd.DataFrame) -> list[dict[str, Any]]:
    base = _data(ma["conhecido_em"].max())
    contagem = ma["papel"].value_counts()
    return [
        _item(chave, nome, int(contagem.get(papel, 0)), "negócios", base, publicado_em=base, fontes=FONTES_DO_MA)
        for papel, chave, nome in ITENS_DO_MA
    ]  # fmt: skip


def _itens_e_tabelas_da_cvm(
    eventos: pd.DataFrame,
) -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame]]:
    """Fatos relevantes e comunicados de compra, venda, fusão ou reorganização (vazio: nenhum)."""
    if eventos.empty:
        return [], {}
    # a base guarda a data sem hora (`datetime.date`): vira data do pandas para ordenar e agrupar
    eventos = eventos.assign(publicado_em=pd.to_datetime(eventos["publicado_em"]))
    assunto = eventos["assunto"].fillna("").map(normalizar_nome)
    negocios = eventos[
        eventos["rotulo"].isin(ROTULOS_DE_NEGOCIO)
        & assunto.str.contains(PALAVRAS_DE_NEGOCIO)
    ].sort_values("publicado_em", ascending=False)
    if negocios.empty:
        return [], {}
    por_ano = (
        negocios.groupby(negocios["publicado_em"].dt.year.rename("ano"))
        .size()
        .rename("documentos")
        .reset_index()
        .sort_values("ano", ascending=False)
        .head(ANOS_NAS_SERIES)
    )
    base = _data(negocios["publicado_em"].iloc[0])
    itens = [
        _item(
            "negocios",
            "Documentos de negócios na CVM",
            len(negocios),
            "documentos",
            base,
            publicado_em=base,  # a data-base já é a publicação do documento mais novo
        )
    ]
    tabelas = {
        "negocios": negocios[["publicado_em", "rotulo", "assunto", "link"]].head(
            LINHAS_NAS_LISTAS
        ),
        "negocios_por_ano": por_ano,
    }
    return itens, tabelas


def secao_negocios(
    eventos: pd.DataFrame, ma: pd.DataFrame | None = None
) -> dict[str, Any] | None:
    """Negócios e eventos: os documentos da CVM sobre compra, venda, fusão ou reorganização e o M&A das
    assessorias (`negocios_de_ma_por_empresa`, já só da empresa da ficha). None: nenhum dos dois."""
    itens, tabelas = _itens_e_tabelas_da_cvm(eventos)
    if ma is not None and not ma.empty:
        itens += _itens_do_ma(ma)
        tabelas |= _tabelas_do_ma(ma)
        fontes = fontes_das_tabelas(_SECAO_POR_CHAVE["negocios"].tabelas)
    else:
        fontes = fontes_das_tabelas(["eventos"])
    if not itens:
        return None
    return _secao("negocios", itens, tabelas, fontes=fontes)


# --- insolvência e situação especial (ADR 0103, D2: só fatos, com o direito de resposta) --------------

# o rótulo da base → como a ficha escreve; rótulo fora daqui (exposição a terceiro, espólio) não sai
NOMES_DOS_REGISTROS = {
    "recuperacao_judicial": "Recuperação judicial",
    "recuperacao_extrajudicial": "Recuperação extrajudicial",
    "recuperacao_judicial_ou_extrajudicial": "Recuperação judicial ou extrajudicial (a CVM não diz qual)",
    "pedido_de_falencia": "Pedido de falência",
    "falencia": "Falência",
    "liquidacao": "Liquidação",
    "liquidacao_judicial": "Liquidação judicial",
    "liquidacao_extrajudicial": "Liquidação extrajudicial",
    "intervencao": "Intervenção",
}  # fmt: skip
# o que cada fonte precisa ter: a empresa sem linha chega como quadro vazio, e as colunas vêm do reindex
COLUNAS_DA_INSOLVENCIA = ("rotulo", "protocolo", "referencia", "conhecido_em", "link")
COLUNAS_DA_SITUACAO_ESPECIAL = (
    "rotulo", "data_situacao_especial", "disponivel_em",
)  # fmt: skip
VEICULO_DA_CVM = "CVM (IPE)"
SITUACAO_CONTESTADA = "contestada"
COLUNAS_DOS_FATOS = ["rotulo", "aconteceu_em", "publico_em", "veiculo", "link"]
SEM_REGISTRO_NA_CVM = (
    "Sem registro de recuperação, falência ou liquidação nos documentos da CVM (IPE), consultados "
    "em {dia}."
)
SEM_REGISTRO_NA_RECEITA = "Sem registro de situação especial no cadastro do CNPJ da Receita Federal, consultado em {dia}."
NAO_CONSULTADO_NA_CVM = (
    "Não consultamos os documentos da CVM (IPE) sobre recuperação, falência e liquidação: a base "
    "não tinha essa fonte no dia da ficha."
)
NAO_CONSULTADO_NA_RECEITA = (
    "Não consultamos a situação especial do cadastro do CNPJ da Receita Federal: a base não tinha "
    "essa fonte no dia da ficha."
)
O_QUE_NAO_SABEMOS_DA_INSOLVENCIA = (
    "O que não sabemos: não lemos processos nos tribunais, diários oficiais, notícias nem a dívida "
    "ativa da União; a falta de registro nas fontes lidas não prova que não exista."
)


def _fatos_da_cvm(insolvencia: pd.DataFrame, hoje: pd.Timestamp) -> pd.DataFrame:
    """Os documentos do IPE sobre a própria companhia, já públicos em `hoje`, uma vez por entrega
    (a reapresentação não apaga a data da primeira versão)."""
    insolvencia = insolvencia.reindex(columns=COLUNAS_DA_INSOLVENCIA)
    publico = pd.to_datetime(insolvencia["conhecido_em"])
    vale = insolvencia.assign(conhecido_em=publico)[
        insolvencia["rotulo"].isin(NOMES_DOS_REGISTROS) & (publico <= hoje)
    ]
    primeiras = vale.sort_values("conhecido_em").drop_duplicates(
        ["protocolo", "rotulo"]
    )
    return pd.DataFrame(
        {
            "rotulo": primeiras["rotulo"],
            "aconteceu_em": pd.to_datetime(primeiras["referencia"]),
            "publico_em": primeiras["conhecido_em"],
            "veiculo": VEICULO_DA_CVM,
            "link": primeiras["link"],
        },
        columns=COLUNAS_DOS_FATOS,
    )


def _fatos_da_receita(
    situacao_especial: pd.DataFrame, hoje: pd.Timestamp
) -> pd.DataFrame:
    """As situações especiais do cadastro do CNPJ já públicas em `hoje`: um fato por rótulo e data,
    na primeira vez que o retrato mensal o trouxe (a filial e os meses seguintes não o repetem)."""
    situacao_especial = situacao_especial.reindex(columns=COLUNAS_DA_SITUACAO_ESPECIAL)
    publico = pd.to_datetime(situacao_especial["disponivel_em"])
    vale = situacao_especial.assign(disponivel_em=publico)[
        situacao_especial["rotulo"].isin(NOMES_DOS_REGISTROS) & (publico <= hoje)
    ]
    primeiras = vale.sort_values("disponivel_em").drop_duplicates(
        ["rotulo", "data_situacao_especial"]
    )
    return pd.DataFrame(
        {
            "rotulo": primeiras["rotulo"],
            "aconteceu_em": pd.to_datetime(primeiras["data_situacao_especial"]),
            "publico_em": primeiras["disponivel_em"],
            "veiculo": VEICULO_DO_CNPJ,
            "link": ENDERECO_DO_CNPJ,
        },
        columns=COLUNAS_DOS_FATOS,
    )


def _contestacao_do_fato(
    fato: pd.Series, contestadas: pd.DataFrame
) -> pd.Series | None:
    """A contestação mais nova do fato: a do registro dele e, se disser o dia, a do mesmo dia."""
    do_registro = contestadas[contestadas["registro"] == fato["rotulo"]]
    do_dia = do_registro["aconteceu_em"].isna() | (
        do_registro["aconteceu_em"] == fato["aconteceu_em"]
    )
    achadas = do_registro[do_dia].sort_values("recebida_em")
    return None if achadas.empty else achadas.iloc[-1]


def _linha_do_fato(fato: pd.Series, contestadas: pd.DataFrame) -> dict[str, Any]:
    contestacao = _contestacao_do_fato(fato, contestadas)
    return {
        "aconteceu_em": _data(fato["aconteceu_em"]),
        "publico_em": _data(fato["publico_em"]),
        "registro": NOMES_DOS_REGISTROS[fato["rotulo"]],
        "veiculo": fato["veiculo"],
        "link": None if pd.isna(fato["link"]) else fato["link"],
        "situacao": None if contestacao is None else SITUACAO_CONTESTADA,
        "contestacao": None if contestacao is None else contestacao["texto"],
        "contestada_em": (
            None if contestacao is None else _data(contestacao["recebida_em"])
        ),
    }


def _avisos_da_fonte(
    fatos: pd.DataFrame | None, sem_registro: str, nao_consultado: str, dia: str
) -> list[str]:
    """A frase da fonte que não trouxe fato: "sem registro" com o dia, ou que não foi lida."""
    if fatos is None:
        return [nao_consultado]
    return [] if len(fatos) else [sem_registro.format(dia=dia)]


def secao_insolvencia(
    insolvencia: pd.DataFrame | None,
    situacao_especial: pd.DataFrame | None,
    contestacoes: pd.DataFrame,
    hoje: pd.Timestamp,
) -> dict[str, Any] | None:
    """Registros de insolvência e situação especial: só fatos, cada um com a data do fato, a data em
    que ficou público, o veículo e o link (ADR 0103, D2). Sem fato, diz "sem registro" com o dia da
    consulta; fonte que a base não leu (`None`) diz que não foi consultada. None: nenhuma das duas foi lida.

    Os dois quadros já são só da empresa da ficha; `contestacoes` também (`base.contestacoes`). Um fato
    contestado ganha `situacao: contestada` e o texto da empresa ao lado.
    """
    if insolvencia is None and situacao_especial is None:
        return None
    da_cvm = None if insolvencia is None else _fatos_da_cvm(insolvencia, hoje)
    da_receita = (
        None
        if situacao_especial is None
        else _fatos_da_receita(situacao_especial, hoje)
    )
    contestadas = contestacoes[contestacoes["recebida_em"] <= hoje]
    fatos = pd.concat(
        [f for f in (da_cvm, da_receita) if f is not None], ignore_index=True
    )
    fatos = fatos.sort_values(["publico_em", "rotulo"], ascending=[False, True])
    linhas = pd.DataFrame([_linha_do_fato(f, contestadas) for _, f in fatos.iterrows()])
    dia = f"{hoje:%d/%m/%Y}"
    paragrafos = [
        *_avisos_da_fonte(da_cvm, SEM_REGISTRO_NA_CVM, NAO_CONSULTADO_NA_CVM, dia),
        *_avisos_da_fonte(
            da_receita, SEM_REGISTRO_NA_RECEITA, NAO_CONSULTADO_NA_RECEITA, dia
        ),
        O_QUE_NAO_SABEMOS_DA_INSOLVENCIA,
    ]
    lidas = {"insolvencia": insolvencia, "cnpj_situacao_especial": situacao_especial}
    fontes = fontes_das_tabelas(t for t, lida in lidas.items() if lida is not None)
    return _secao(
        "insolvencia", [], {"registros_de_insolvencia": linhas}, paragrafos, fontes
    )


# --- ligações na rede (molde B: a busca por CNPJ, plano de 19/10/2026) ---------------------------


class Relacao(NamedTuple):
    """O que a outra ponta de uma ligação é para a empresa da ficha."""

    chave: str  # do item com a contagem
    tipo: str
    empresa_em_de: bool  # a empresa da ficha é a ponta `de` da ligação
    nome: str


RELACOES = (
    Relacao("controladas", CONTROLADA_DE, False, "Controlada"),
    Relacao("controladoras", CONTROLADA_DE, True, "Controladora"),
    Relacao("coligadas", COLIGADA_DE, False, "Coligada"),
    Relacao("coligada_de", COLIGADA_DE, True, "Tem a companhia como coligada"),
    Relacao("participacoes", PARTICIPADA_DE, False, "Participação da companhia"),
    Relacao("participam", PARTICIPADA_DE, True, "Tem participação na companhia"),
    Relacao("auditor", AUDITA, False, "Auditor"),
    Relacao(
        "instituicoes_do_conglomerado",
        DO_CONGLOMERADO_DE,
        False,
        "Instituição do conglomerado",
    ),
    Relacao("lider_do_conglomerado", DO_CONGLOMERADO_DE, True, "Líder do conglomerado"),
)
_RELACAO = {(r.tipo, r.empresa_em_de): r for r in RELACOES}
TIPOS_DO_FRE = frozenset({CONTROLADA_DE, COLIGADA_DE, PARTICIPADA_DE})
# só estes tipos saem (nenhum de pessoa nem negativo); `emite` entra só como contagem
TIPOS_DA_REDE = frozenset({*(r.tipo for r in RELACOES), EMITE})
# a família da licença e o documento de cada fonte de ligação; fonte fora daqui não sai (`opera_para`
# já está no setor regulado; uma fonte nova só entra quando alguém a põe aqui)
FONTES_DA_REDE = {
    "cvm-fre": ("cvm", "Formulário de Referência (CVM)"),
    "cvm-fca": ("cvm", "Formulário Cadastral (CVM)"),
    "cvm-cda": ("cvm", "Carteiras dos fundos (CVM)"),
    "bcb-ifdata": ("bcb", "IF.data (Banco Central)"),
}
# os identificadores públicos da empresa que saem: a família da licença e o nome na tela
IDENTIFICADORES_DA_EMPRESA = {
    "cnpj": ("cvm", "CNPJ"),
    "ticker": ("cvm", "Ticker"),
    "emissor": ("cvm", "Código do emissor"),
    "lei": ("gleif", "LEI (GLEIF)"),
    "codigo_bcb_ifdata": ("bcb", "Código no IF.data (Banco Central)"),
}
SISTEMAS_DA_REDE = (*IDENTIFICADORES_DA_EMPRESA, "cnpj_raiz")  # o que a noite lê
SECOES_DO_MOLDE_B = frozenset(
    {"rede"}
)  # o relatório da empresa (molde A) não as mostra
SECOES_DO_MOLDE_D = frozenset({"setor"})  # idem: quem as lê é o relatório do setor
SECOES_FORA_DO_MOLDE_A = SECOES_DO_MOLDE_B | SECOES_DO_MOLDE_D


@dataclass(frozen=True)
class RedeDaNoite:
    """A rede pronta para as fichas: só o que pode sair, já separado por entidade."""

    centros: dict[str, str]  # raiz do CNPJ → id_entidade
    ligacoes: dict[str, pd.DataFrame]  # id_entidade → as ligações dele que podem sair
    identificadores: dict[
        str, pd.DataFrame
    ]  # id_entidade → os identificadores que saem
    nomes: dict[str, str]
    cnpjs: dict[str, str]


def _sem_fuso(quando: pd.Timestamp) -> pd.Timestamp:
    return quando.tz_localize(None) if quando.tzinfo else quando


def _pode_mostrar_a_familia(familia: object) -> bool:
    return isinstance(familia, str) and pode_usar(MOSTRAR, familia)  # sem família: NaN


def raizes_do_fre_em_dia(
    controladas: pd.DataFrame, hoje: pd.Timestamp
) -> set[tuple[str, str]]:
    """(raiz da companhia, raiz da sociedade) de cada FRE mais recente dos últimos anos, público hoje.

    A rede guarda a ligação do FRE como vigente enquanto ninguém a encerra: a companhia que parou de
    entregar (a VBC Energia, que deixou a CPFL em 2011) continuaria dona hoje.
    """
    if controladas.empty or "conhecido_em" not in controladas.columns:
        return set()  # sem a data de entrega não dá para saber o que já era público
    hoje = _sem_fuso(hoje)
    publicos = controladas[pd.to_datetime(controladas["conhecido_em"]) <= hoje]
    limite = hoje - pd.DateOffset(years=ANOS_DO_FRE_EM_DIA)
    pares: set[tuple[str, str]] = set()
    for companhia, fres in publicos.groupby(publicos["cnpj_companhia"].map(raiz)):
        ultimo = _mais_recente(fres)
        if ultimo.empty or pd.Timestamp(ultimo["referencia"].iloc[0]) < limite:
            continue
        pares |= {(str(companhia), r) for r in ultimo["cnpj"].dropna().map(raiz) if r}
    return pares


def _raizes(identificadores: pd.DataFrame) -> pd.Series:
    """A raiz do CNPJ de cada entidade (pela raiz da rede ou pelo CNPJ inteiro)."""
    pela_raiz = identificadores[identificadores["sistema"] == "cnpj_raiz"]
    pelo_cnpj = identificadores[identificadores["sistema"] == "cnpj"]
    juntas = pd.concat(
        [
            pela_raiz.assign(raiz=pela_raiz["valor"]),
            pelo_cnpj.assign(raiz=pelo_cnpj["valor"].map(raiz)),
        ]
    ).dropna(subset=["raiz"])
    return juntas.drop_duplicates("id_entidade").set_index("id_entidade")["raiz"]


def _centros(identificadores: pd.DataFrame) -> dict[str, str]:
    """Raiz → entidade, só quando a raiz aponta para uma entidade só."""
    raizes = identificadores[identificadores["sistema"] == "cnpj_raiz"]
    unicas = raizes.drop_duplicates(["valor", "id_entidade"])
    unicas = unicas[~unicas["valor"].duplicated(keep=False)]
    return dict(zip(unicas["valor"], unicas["id_entidade"], strict=True))


def _ligacoes_que_podem_sair(
    ligacoes: pd.DataFrame, empresas: set[str]
) -> pd.DataFrame:
    """Os tipos da rede, de fonte conhecida que pode ser mostrada, entre empresas (nunca pessoas)."""
    familias = ligacoes["fonte"].map(lambda f: FONTES_DA_REDE.get(f, (None, ""))[0])
    entre_empresas = ligacoes["de"].isin(empresas) & (
        ligacoes["para"].isin(empresas) | (ligacoes["tipo"] == EMITE)
    )
    return ligacoes[
        ligacoes["tipo"].isin(TIPOS_DA_REDE)
        & familias.map(_pode_mostrar_a_familia).astype(bool)
        & entre_empresas
    ]


def _do_fre_em_dia(
    ligacoes: pd.DataFrame, raizes: pd.Series, pares: set[tuple[str, str]]
) -> pd.Series:
    """A ligação não é do FRE, ou o FRE em dia da companhia (`para`) ainda lista a sociedade (`de`)."""
    par = zip(ligacoes["para"].map(raizes), ligacoes["de"].map(raizes), strict=True)
    listada = pd.Series([p in pares for p in par], index=ligacoes.index, dtype=bool)
    return ~ligacoes["tipo"].isin(TIPOS_DO_FRE) | listada


def _por_entidade(ligacoes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """As ligações de cada entidade, como `de` ou como `para`."""
    por_de = {str(e): g for e, g in ligacoes.groupby("de")}
    por_para = {str(e): g for e, g in ligacoes.groupby("para")}
    vazia = ligacoes.iloc[0:0]
    return {
        e: pd.concat([por_de.get(e, vazia), por_para.get(e, vazia)])
        for e in por_de.keys() | por_para.keys()
    }


def _identificadores_que_saem(
    identificadores: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    familias = identificadores["sistema"].map(
        lambda s: IDENTIFICADORES_DA_EMPRESA.get(s, (None, ""))[0]
    )
    saem = identificadores[familias.map(_pode_mostrar_a_familia).astype(bool)]
    return {str(e): g for e, g in saem.groupby("id_entidade")}


def preparar_rede(
    ligacoes: pd.DataFrame,
    entidades: pd.DataFrame,
    identificadores: pd.DataFrame,
    controladas: pd.DataFrame,
    hoje: pd.Timestamp,
) -> RedeDaNoite:
    """A rede como era em `hoje` (a porta já cortou o futuro), sem pessoa nem tipo negativo.

    Montada uma vez por noite. Entidade fora da rede conta como pessoa (o conservador); a ligação do
    FRE só fica se o FRE em dia ainda a mostra (`raizes_do_fre_em_dia`).
    """
    if ligacoes.empty or entidades.empty or identificadores.empty:
        return RedeDaNoite(
            {}, {}, {}, {}, {}
        )  # a rede ainda não foi montada nesta base
    publicadas, _ = vista_publicada(ligacoes, entidades)
    empresas = entidades[~entidades["trata_como_pessoa"].fillna(True).astype(bool)]
    nomes = {
        str(e): str(n)
        for e, n in zip(empresas["id_entidade"], empresas["nome"], strict=True)
    }
    podem = _ligacoes_que_podem_sair(publicadas, set(nomes))
    pares = raizes_do_fre_em_dia(controladas, hoje)
    podem = podem[_do_fre_em_dia(podem, _raizes(identificadores), pares)]
    cnpjs = identificadores[identificadores["sistema"] == "cnpj"].drop_duplicates(
        "id_entidade"
    )
    return RedeDaNoite(
        centros=_centros(identificadores),
        ligacoes=_por_entidade(podem),
        identificadores=_identificadores_que_saem(identificadores),
        nomes=nomes,
        cnpjs=dict(zip(cnpjs["id_entidade"], cnpjs["valor"], strict=True)),
    )


def _cnpj_formatado(cnpj: str | None) -> str | None:
    return formatar(cnpj) if cnpj and len(cnpj) == DIGITOS_DO_CNPJ else None


_COLUNAS_DAS_LIGACOES = (
    "ordem",
    "chave",
    "relacao",
    "entidade",
    "cnpj",
    "participacao",
    "desde",
    "documento",
    "familia",
    "publicado_em",
)
_PUBLICO_EM_DAS_LIGACOES = TABELAS["ligacoes"].datas["publico_em"]
_COLUNAS_DOS_IDENTIFICADORES = ("identificador", "valor", "desde", "familia")


def _linhas_da_rede(
    centro: str, ligacoes: pd.DataFrame, rede: RedeDaNoite
) -> pd.DataFrame:
    """Uma linha por ligação: o que a outra ponta é para a empresa, com o documento que a mostra."""
    linhas = []
    for ligacao in ligacoes.itertuples(index=False):
        em_de = ligacao.de == centro
        relacao = _RELACAO.get((str(ligacao.tipo), em_de))
        outra = str(ligacao.para if em_de else ligacao.de)
        if relacao is None or outra == centro:
            continue
        familia, documento = FONTES_DA_REDE[str(ligacao.fonte)]
        publicado_em = getattr(ligacao, _PUBLICO_EM_DAS_LIGACOES, None)
        linhas.append(
            {
                "ordem": RELACOES.index(relacao),
                "chave": relacao.chave,
                "relacao": relacao.nome,
                "entidade": rede.nomes[outra],
                "cnpj": _cnpj_formatado(rede.cnpjs.get(outra)),
                "participacao": ligacao.participacao,
                "desde": _desde_quando(ligacao.aconteceu_em, publicado_em),
                "documento": documento,
                "familia": familia,
                "publicado_em": publicado_em,
            }
        )
    return pd.DataFrame(linhas, columns=list(_COLUNAS_DAS_LIGACOES))


def _desde_quando(aconteceu_em: object, publicado_em: object) -> object:
    """O dia em que a ligação ficou pública, não o dia nominal em que "aconteceu": a CVM dá ao FRE
    a referência de 31/12 do ano (o FRE de 2026, entregue em agosto, diz 31/12/2026), e a ficha
    não mostra o futuro. Sem a data de publicação (fonte sem ela), fica a do acontecimento."""
    return aconteceu_em if pd.isna(publicado_em) else publicado_em


def _mostradas(linhas: pd.DataFrame) -> pd.DataFrame:
    """Até `LINHAS_NAS_LISTAS` por relação, as de maior participação primeiro."""
    if linhas.empty:
        return linhas
    ordenadas = linhas.sort_values(
        ["ordem", "participacao", "entidade"],
        ascending=[True, False, True],
        na_position="last",
    )
    return (
        ordenadas.groupby("chave", sort=False)
        .head(LINHAS_NAS_LISTAS)
        .drop(columns=["ordem", "chave", "familia", "publicado_em"])
    )


def _tabela_dos_identificadores(identificadores: pd.DataFrame | None) -> pd.DataFrame:
    if identificadores is None:
        return pd.DataFrame(columns=list(_COLUNAS_DOS_IDENTIFICADORES))
    ordem = list(IDENTIFICADORES_DA_EMPRESA)
    tabela = identificadores.assign(
        ordem=identificadores["sistema"].map(ordem.index)
    ).sort_values(["ordem", "valor"])
    return pd.DataFrame(
        {
            "identificador": tabela["sistema"].map(
                lambda s: IDENTIFICADORES_DA_EMPRESA[s][1]
            ),
            "valor": [
                _cnpj_formatado(v) if s == "cnpj" else v
                for s, v in zip(tabela["sistema"], tabela["valor"], strict=True)
            ],
            "desde": tabela["desde"],
            "familia": tabela["sistema"].map(
                lambda s: IDENTIFICADORES_DA_EMPRESA[s][0]
            ),
        }
    )


def _publicada(linhas: pd.DataFrame) -> str | None:
    """A ligação mais nova das `linhas` (de `_linhas_da_rede`): quando ficou pública."""
    return _data(pd.to_datetime(linhas["publicado_em"]).max()) if len(linhas) else None


def _item_da_relacao(relacao: Relacao, linhas: pd.DataFrame) -> dict[str, Any]:
    da_relacao = linhas[linhas["chave"] == relacao.chave]
    return _item(
        relacao.chave,
        relacao.nome,
        len(da_relacao),
        "empresas",
        None,
        publicado_em=_publicada(da_relacao),
        fontes=sorted(da_relacao["familia"].unique()),
        origem=ORIGEM_DAS_RELACOES[relacao.chave],
    )


def _itens_da_rede(
    linhas: pd.DataFrame, emitidos: pd.DataFrame
) -> list[dict[str, Any]]:
    """A contagem de ligações, a de cada relação e a dos valores mobiliários (`emitidos`: as ligações
    `emite` da companhia), cada uma com a fonte das linhas que conta."""
    itens = [
        _item(
            "ligacoes",
            "Ligações na rede",
            len(linhas),
            "empresas",
            None,
            publicado_em=_publicada(linhas),
            fontes=sorted(linhas["familia"].unique()),
        )
    ]
    itens += [
        _item_da_relacao(r, linhas)
        for r in RELACOES
        if (linhas["chave"] == r.chave).any()
    ]
    if not emitidos.empty:
        itens.append(
            _item(
                "valores_mobiliarios",
                "Valores mobiliários nas carteiras dos fundos",
                int(emitidos["para"].nunique()),
                "valores mobiliários",
                None,
                publicado_em=_publicado(emitidos, "ligacoes"),
                fontes=[FONTES_DA_REDE["cvm-cda"][0]],
            )
        )
    return itens


def secao_rede(cnpj: str, rede: RedeDaNoite) -> dict[str, Any] | None:
    """O que a companhia é na rede: controladas, donas, coligadas, auditor e conglomerado (None: nada).

    Cada relação mostra até `LINHAS_NAS_LISTAS` entidades; a contagem é toda. Os valores mobiliários
    entram só como contagem.
    """
    centro = rede.centros.get(raiz(cnpj) or "")
    if centro is None or centro not in rede.ligacoes:
        return None
    ligacoes = rede.ligacoes[centro]
    emitidos = ligacoes[(ligacoes["tipo"] == EMITE) & (ligacoes["de"] == centro)]
    linhas = _linhas_da_rede(centro, ligacoes[ligacoes["tipo"] != EMITE], rede)
    if linhas.empty and emitidos.empty:
        return None
    identificadores = _tabela_dos_identificadores(rede.identificadores.get(centro))
    familias = {*linhas["familia"], *identificadores["familia"]}
    if not emitidos.empty:
        familias.add(FONTES_DA_REDE["cvm-cda"][0])
    tabelas = {
        "ligacoes_da_rede": _mostradas(linhas),
        "identificadores_da_empresa": identificadores.drop(
            columns="familia", errors="ignore"
        ),
    }
    fontes = sorted({licenca_da_fonte(f) for f in familias})
    return _secao("rede", _itens_da_rede(linhas, emitidos), tabelas, fontes=fontes)


# --- o rastro de cada item (B-02, 20/10/2026) ----------------------------------------------------


class Origem(NamedTuple):
    """De onde sai um item: a tabela da porta (a fonte é a família dela) e a conta, em português."""

    tabela: str
    formula: str


_DO_FRE_MAIS_RECENTE = "no FRE mais recente"
_ORIGENS_FIXAS = {
    "auditor_atual": Origem("auditores", f"a firma do mandato sem fim {_DO_FRE_MAIS_RECENTE}"),
    "auditor_desde": Origem("auditores", f"o início do mandato sem fim {_DO_FRE_MAIS_RECENTE}"),
    "sociedades": Origem("controladas", f"número de sociedades listadas {_DO_FRE_MAIS_RECENTE}"),
    "controladas": Origem(
        "controladas",
        f"sociedades {_DO_FRE_MAIS_RECENTE} do tipo controlada (sem tipo: participação acima de "
        f"{PARTICIPACAO_DE_CONTROLE:.0f}%)",
    ),
    "coligadas_e_outras": Origem(
        "controladas", f"sociedades {_DO_FRE_MAIS_RECENTE} menos as controladas"
    ),
    "ofertas": Origem(
        "ofertas_resolucao_160",
        "número de ofertas registradas na CVM pela companhia e pelas controladas do FRE mais "
        "recente (Resolução 160 e as anteriores)",
    ),
    "fundos_com_a_acao": Origem(
        "painel_dos_fundos", "número de fundos com a ação comprada no último mês completo do CDA"
    ),
    "valor_nos_fundos": Origem(
        "painel_dos_fundos", "soma do valor da ação nas carteiras no último mês completo do CDA"
    ),
    "ebitda": Origem(
        "demonstracoes_como_era",
        "EBIT (DRE 3.05) + depreciação e amortização (DVA 7.04.01; sem DVA, os ajustes da DFC), "
        "na DFP mais nova já divulgada",
    ),
    "capex": Origem(
        "demonstracoes_como_era",
        "saídas para comprar imobilizado e intangível (DFC 6.02), na DFP mais nova já divulgada",
    ),
    "fcf": Origem(
        "demonstracoes_como_era",
        "caixa operacional (DFC 6.01) − capex, na DFP mais nova já divulgada",
    ),
    "exercicios_reapresentados": Origem(
        "demonstracoes_como_era",
        f"exercícios dos últimos {ANOS_NAS_SERIES} em que o lucro ou a receita da DFP mudaram mais "
        "que o arredondamento entre a primeira e a última versão divulgada",
    ),
    "exercicios_olhados": Origem(
        "demonstracoes_como_era", f"exercícios dos últimos {ANOS_NAS_SERIES} com DFP divulgada"
    ),
    "releases_comparados": Origem(
        "release_x_oficial",
        "valores do release que deu para comparar com o ITR ou a DFP (versão mais nova de cada release)",
    ),
    "releases_diferentes": Origem(
        "release_x_oficial",
        "valores do release diferentes do ITR ou da DFP além do arredondamento",
    ),
    "trocas_de_auditor_10_anos": Origem(
        "trocas_de_auditor",
        f"trocas de auditor com efeito nos últimos {ANOS_NAS_SERIES} anos, já conhecidas",
    ),
    "insiders_compras_12m": Origem(
        "negociacoes",
        "soma das compras declaradas (todo cargo fora a tesouraria) nos 12 meses até o dia, das "
        "declarações já entregues",
    ),
    "insiders_vendas_12m": Origem(
        "negociacoes",
        "soma das vendas declaradas (todo cargo fora a tesouraria) nos 12 meses até o dia, das "
        "declarações já entregues",
    ),
    "recompras_12m": Origem(
        "negociacoes",
        "soma das compras da própria companhia (tesouraria) nos 12 meses até o dia",
    ),
    "eventos_de_capital": Origem(
        "eventos_de_capital",
        f"eventos de capital dos últimos {ANOS_NAS_SERIES} anos, cada um uma vez",
    ),
    "compras_dos_fundos_12m": Origem(
        "painel_dos_fundos", "soma das compras dos fundos nos 12 meses até o último mês completo"
    ),
    "vendas_dos_fundos_12m": Origem(
        "painel_dos_fundos", "soma das vendas dos fundos nos 12 meses até o último mês completo"
    ),
    "conselho_membros": Origem(
        "fre_conselho", "membros dos órgãos do conselho de administração no FRE mais novo entregue"
    ),
    "conselho_independentes": Origem(
        "fre_conselho", "conselheiros independentes no FRE mais novo entregue"
    ),
    "conselho_eleitos_por_minoritarios": Origem(
        "fre_conselho", "conselheiros eleitos por minoritários no FRE mais novo entregue"
    ),
    "comites": Origem("fre_comites", "tipos de comitê distintos no FRE mais novo entregue"),
    "mulheres_no_conselho": Origem(
        "fre_diversidade", "mulheres no conselho de administração no FRE mais novo entregue"
    ),
    "remuneracao_da_administracao": Origem(
        "fre_remuneracao",
        "soma da remuneração total dos órgãos no último exercício encerrado, no FRE mais novo que "
        "o informa",
    ),
    "ratings_rebaixamentos_12m": Origem(
        "ratings", "rebaixamentos de rating públicos nos 12 meses até o dia, cada ação uma vez"
    ),
    "ratings_elevacoes_12m": Origem(
        "ratings", "elevações de rating públicas nos 12 meses até o dia, cada ação uma vez"
    ),
    "assembleias_de_debenturistas_12m": Origem(
        "debentures_assembleias",
        "documentos de assembleia de debenturistas públicos nos 12 meses até o dia (versão mais nova)",
    ),
    "setor": Origem("empresa_serie", "o setor da agência que regula as entidades da companhia"),
    "membros": Origem(
        "empresa_serie", "companhias abertas da base com entidade ligada à agência do setor"
    ),
    "negocios": Origem(
        "eventos",
        "fatos relevantes e comunicados cujo assunto fala de compra, venda, fusão ou reorganização",
    ),
    "ma_comprou": Origem(
        "ma_datas",
        "negócios de M&A das assessorias em que a empresa é a compradora ou a investidora, já "
        "conhecidos no dia, cada negócio uma vez",
    ),
    "ma_vendeu": Origem(
        "ma_datas",
        "negócios de M&A das assessorias em que a empresa é a vendedora, já conhecidos no dia, "
        "cada negócio uma vez",
    ),
    "ma_foi_comprada": Origem(
        "ma_datas",
        "negócios de M&A das assessorias em que a empresa é a alvo de compra ou investimento, "
        "já conhecidos no dia, cada negócio uma vez",
    ),
    "ligacoes": Origem("ligacoes", "empresas ligadas à companhia na rede, como era no dia"),
    "valores_mobiliarios": Origem(
        "ligacoes", "valores mobiliários da companhia nas carteiras dos fundos (CDA), como era no dia"
    ),
}  # fmt: skip


_PARTICIPANTE = "participante: o grupo econômico quando se sabe, senão a entidade"


def _origens_das_series() -> dict[str, Origem]:
    """A série da companhia (setor regulado) e o mercado, o HHI e o CR4 de cada série (setor)."""
    origens = {}
    for s in (*SERIES_DAS_AGENCIAS, *SERIES_DOS_BANCOS):
        medida = f"{s.medida} ({s.modo})"
        origens |= {
            s.nome: Origem(
                s.tabela, f"{medida}: soma das entidades ligadas à companhia"
            ),
            f"mercado_{s.nome}": Origem(s.tabela, f"{medida}: soma de todo o mercado"),
            f"hhi_{s.nome}": Origem(
                s.tabela,
                f"{medida}: soma dos quadrados das participações (em %) de cada {_PARTICIPANTE}",
            ),
            f"cr4_{s.nome}": Origem(
                s.tabela,
                f"{medida}: fração do mercado somada pelos 4 maiores ({_PARTICIPANTE})",
            ),
        }
    return origens


ORIGEM_DOS_ITENS: dict[str, Origem] = _ORIGENS_FIXAS | _origens_das_series()
# a contagem de cada relação da rede; à parte porque "controladas" também é chave da seção do FRE
ORIGEM_DAS_RELACOES = {
    r.chave: Origem("ligacoes", f"empresas que são '{r.nome}' da companhia na rede, como era no dia")
    for r in RELACOES
}  # fmt: skip
# itens cuja tabela não guarda quando o dado ficou público: o rastro sai sem `publicado_em`, com o motivo
ITENS_SEM_DATA_DE_PUBLICACAO = {
    "eventos_de_capital": "a tabela de eventos de capital não guarda a entrega do FRE que os informa",
    "setor": "a ligação das entidades da agência às companhias não guarda quando ficou pública",
    "membros": "a ligação das entidades da agência às companhias não guarda quando ficou pública",
}


# --- a ficha e o filtro de pessoas ---------------------------------------------------------------


def montar_ficha(
    cnpj: str, empresa: str, secoes: Iterable[dict[str, Any] | None], gerado_em: str
) -> dict[str, Any]:
    """A ficha de uma companhia: o esquema, quem é e as seções que existem, na ordem de `SECOES`."""
    return {
        "versao_do_esquema": VERSAO_DO_ESQUEMA,
        "cnpj": cnpj,
        "empresa": empresa,
        "gerado_em": gerado_em,
        "secoes": [secao for secao in secoes if secao is not None],
    }


def _textos_e_chaves(valor: object) -> Iterable[tuple[str, str]]:
    """Cada texto da ficha, com o tipo ("texto" ou "coluna"), percorrendo listas e dicionários."""
    if isinstance(valor, dict):
        for chave, dentro in valor.items():
            yield "coluna", str(chave)
            yield from _textos_e_chaves(dentro)
    elif isinstance(valor, list):
        for dentro in valor:
            yield from _textos_e_chaves(dentro)
    elif isinstance(valor, str):
        yield "texto", valor


def conferir_sem_pessoas(ficha: Mapping[str, Any], pessoas: set[str]) -> None:
    """Levanta `PessoaNaFichaError` se a ficha tem CPF, nome de pessoa (já normalizado) ou coluna de pessoa."""
    for tipo, texto in _textos_e_chaves(ficha):
        if tipo == "coluna":
            if texto in COLUNAS_DE_PESSOA:
                raise PessoaNaFichaError(f"coluna de pessoa na ficha: {texto}")
        elif CPF.search(texto):
            raise PessoaNaFichaError("CPF na ficha")
        elif normalizar_nome(texto) in pessoas:
            raise PessoaNaFichaError("nome de pessoa na ficha")
