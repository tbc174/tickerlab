"""Destino de cada fonte do arquivista: para onde vai o que ela baixa (ADR 0076, série T).

Toda `Fonte.id` de `base/arquivo/fontes.py` tem uma entrada aqui, e um teste quebra o CI se faltar
(ou sobrar) uma. Assim uma fonte não passa dias sendo baixada sem virar tabela sem que ninguém
veja. Quando uma fonte planejada ganhar a tabela, troque o tipo para `tabela` neste arquivo.

Em `onde` vai só o nome da série e do PR (o repositório é público).
"""

from dataclasses import dataclass

TABELA = "tabela"  # vira tabela com contrato no catálogo da base
SO_LIGA = "so_liga"  # hoje só liga nomes (rede de relações), sem tabela própria
SO_PESQUISA = "so_pesquisa"  # fica no acervo para pesquisa, fora do catálogo (licença)
VIGIA = "vigia"  # só avisa quando o texto (termos, catálogo) muda
PLANEJADA = "planejada"  # guardada, com tabela prevista em um PR já nomeado

TIPOS = (TABELA, SO_LIGA, SO_PESQUISA, VIGIA, PLANEJADA)


@dataclass(frozen=True)
class Destino:
    tipo: str
    tabelas: tuple[str, ...] = ()  # nomes do catálogo (só no tipo `tabela`)
    onde: str = ""  # série e PR (só na `planejada`), ex. "serie-T/T4"
    porque: str = ""  # uma frase (obrigatória fora de `tabela` e `vigia`)


def _tabela(*tabelas: str) -> Destino:
    return Destino(TABELA, tabelas=tabelas)


def _vigia() -> Destino:
    return Destino(VIGIA)


def _planejada(onde: str, porque: str) -> Destino:
    return Destino(PLANEJADA, onde=onde, porque=porque)


def _pesquisa(porque: str) -> Destino:
    return Destino(SO_PESQUISA, porque=porque)


_SO_LIGA_HOJE = "hoje só liga nomes na rede; a tabela própria está prevista"
_B3_FORA_DO_CATALOGO = (
    "barras de 1 minuto em arquivos, fora do catálogo (licença da B3)"
)

_B3_BDI_CONTRA_OS_TERMOS = (
    "só arquivo, só pesquisa: a página da B3 veda a 'coleta automatizada, inclusive por meio de "
    "ferramentas de inteligência artificial, para quaisquer finalidades' "
    "(www.b3.com.br, Boletim diário do mercado, lida em 18/10/2026); decisão do Tiago em "
    "18/10/2026 de guardar a cópia até a B3 autorizar por escrito; nada em tela, API ou tabela"
)

DESTINOS: dict[str, Destino] = {
    # CVM
    "cvm-hist-dfp": _tabela("demonstracoes_como_era"),
    "cvm-hist-itr": _tabela("demonstracoes_como_era"),
    "cvm-hist-fre": _tabela(
        "fre_comites",
        "fre_conselho",
        "fre_diversidade",
        "fre_eventos_de_capital",
        "fre_proventos",
        "fre_remuneracao",
        "controladas",
    ),
    "cvm-hist-fca": _tabela(
        "fca_geral", "valores_mobiliarios", "emissores", "auditores", "tickers_no_tempo"
    ),
    "cvm-hist-ipe": _tabela(
        "eventos",
        "insolvencia",
        "ma_candidatos",
        "noticias_fatos",
        "noticias_numeros",
        "release_x_oficial",
    ),
    "cvm-hist-vlmo": _tabela("negociacoes"),
    "cvm-hist-cda": _tabela(
        "carteiras_dos_fundos", "carteiras_bloco_8", "cda_cotas", "painel_dos_fundos"
    ),
    "cvm-cda-recente": _tabela(
        "carteiras_dos_fundos", "carteiras_bloco_8", "cda_cotas", "painel_dos_fundos"
    ),
    "cvm-fidc": _tabela("fidc_informe"),
    "cvm-fidc-recente": _tabela("fidc_informe"),
    "cvm-ofertas": _tabela("ofertas_antigas", "ofertas_resolucao_160"),
    "cvm-cadastros": _tabela("cadastro_das_companhias", "cadastro_de_fundos"),
    "cvm-cri": _planejada("serie-6/PR1", "certificados de recebíveis imobiliários"),
    "cvm-cra": _planejada("serie-6/PR1", "certificados de recebíveis do agronegócio"),
    "cvm-fiagro": _planejada(
        "serie-T/T4", "informe mensal do FIAGRO; a CVM só guarda os meses recentes"
    ),
    "cvm-sancionador": _planejada(
        "serie-T/T4", "processos sancionadores (só PJ e a função)"
    ),
    "cvm-recompra": _planejada("serie-T/T4", "programas de recompra de ações"),
    "cvm-cgvn": _planejada(
        "serie-T/T4", "informe do código de governança, por item e ano"
    ),
    # Banco Central, Tesouro e Receita
    "bcb-scr": _tabela("scr_credito"),
    "bcb-pix-chaves": _planejada("serie-T/T9", _SO_LIGA_HOJE + " (ISPB ao banco)"),
    "tesouro-br-direto": _tabela("curva_juros"),
    "tesouro-br-leiloes": _tabela("curva_juros"),
    "tesouro-br-divida": _planejada(
        "serie-T/T7", "estoque e emissões da dívida federal, CAPAG e dívida dos estados"
    ),
    "rfb-cnpj": _tabela("cnpj_situacao_especial"),
    "pgfn-divida": _tabela("pgfn_divida"),
    # setoriais
    "anp-vendas-distribuidora": _tabela("anp_vendas"),
    "anp-producao-poco": _planejada("serie-5/PR3", "produção por poço, com o operador"),
    "anp-concessionarios": _planejada(
        "serie-T/T8", "quem opera cada bloco e campo; liga a produção à empresa"
    ),
    "ons-geracao-usina": _tabela("ons_geracao"),
    "ons-capacidade-geracao": _planejada(
        "serie-T/T6", _SO_LIGA_HOJE + " (capacidade por usina)"
    ),
    "ons-restricao-eolica-solar": _planejada(
        "serie-T/T6", "corte de geração (curtailment) por usina"
    ),
    "ccee-pld": _planejada("serie-T/T6", "PLD horário, diário e mensal por submercado"),
    "aneel-samp": _tabela("aneel_samp"),
    "anatel-acessos": _tabela("anatel_acessos"),
    "anac-estatistico": _tabela("anac_estatistico"),
    "ans-beneficiarios": _tabela("ans_beneficiarios"),
    "ans-beneficiarios-operadora": _tabela("ans_beneficiarios"),
    "ans-operadoras": _planejada(
        "serie-T/T9", _SO_LIGA_HOJE + " (cadastro de operadoras)"
    ),
    "susep-ses": _tabela("susep_seguros"),
    "susep-cadastro": _planejada(
        "serie-T/T9", _SO_LIGA_HOJE + " (entidades supervisionadas)"
    ),
    "antt-pedagio": _planejada("serie-5/PR1", "praças de pedágio e tráfego"),
    "antt-siade": _planejada(
        "serie-T/T8", _SO_LIGA_HOJE + " (desempenho por ferrovia)"
    ),
    "comexstat": _tabela("comex_cafe"),
    # governo, sanções e identificadores
    "cgu-ceis": _planejada("sinais/PR4", "sanções administrativas da CGU"),
    "cgu-cnep": _planejada("sinais/PR4", "sanções da Lei Anticorrupção"),
    "cgu-cepim": _planejada(
        "sinais/PR4", "entidades privadas sem fins lucrativos impedidas"
    ),
    "cgu-leniencia": _planejada("sinais/PR4", "acordos de leniência"),
    "tce-pr-pit": _planejada(
        "sinais/PR1-3", "contratos e licitações dos municípios do Paraná"
    ),
    "tce-pr-despesa": _planejada(
        "sinais/PR2-3", "empenhos, liquidações e pagamentos dos municípios do Paraná"
    ),
    "ibama-autos": _planejada("serie-T/T5", "autos de infração ambiental por CNPJ"),
    "ibama-embargos": _planejada("serie-T/T5", "embargos ambientais por CNPJ"),
    "mte-lista-suja": _planejada("serie-T/T5", "cadastro de empregadores (só PJ)"),
    "gleif-br": _planejada("serie-T/T9", _SO_LIGA_HOJE + " (CNPJ e LEI)"),
    # M&A e intradiários
    "assessoria-igc": _tabela(
        "ma_assessorias", "ma_datas", "ma_negocios", "ma_partes", "ma_regua"
    ),
    "wayback-igc": _tabela(
        "ma_assessorias", "ma_datas", "ma_negocios", "ma_partes", "ma_regua"
    ),
    "b3-negocios": _pesquisa(_B3_FORA_DO_CATALOGO),
    "b3-boletim-pr": _pesquisa(_B3_FORA_DO_CATALOGO),
    "b3-cotahist-dia": _pesquisa(_B3_FORA_DO_CATALOGO),
    "b3-emprestimo-posicoes": _pesquisa(_B3_BDI_CONTRA_OS_TERMOS),
    "b3-derivativos-posicoes": _pesquisa(_B3_BDI_CONTRA_OS_TERMOS),
    "b3-emprestimo-resumo": _pesquisa(_B3_BDI_CONTRA_OS_TERMOS),
    "conab-cafe-safra": _tabela("conab_cafe"),
    # balanço mundial do café (PR 4)
    "usda-psd-cafe": _tabela("usda_psd_cafe"),
    "faostat-cafe": _planejada(
        "commodities/PR 14", "produção e área por país e ano, em tabela própria"
    ),
    "ico-relatorio-mensal": _pesquisa(
        "relatório mensal da ICO em PDF, sem termos de uso localizados; só pesquisa até a ICO publicar a licença"
    ),
    "cecafe-relatorio-mensal": _pesquisa(
        "só pesquisa: o robots.txt de www.cecafe.com.br proíbe PDF (lido em 18/10/2026) e a "
        "página de termos não traz texto; a coleta falha, sem baixar, até a Cecafé autorizar por escrito"
    ),
    # clima por região cafeeira (plano do café, PR 8): `base/commodities/clima_regiao.py`
    "inmet-bdmep": _tabela("clima_regiao_cafe"),
    "chirps-mensal": _tabela("clima_regiao_cafe"),
    "ibge-malha-municipal": _tabela("clima_regiao_cafe"),
    # área de café por município (plano do café, PR 8): `base/commodities/area_municipio.py`
    "mapbiomas-cafe": _tabela("area_cafe_municipio"),
    # vigias (avisam quando o texto muda)
    **{
        id_: _vigia()
        for id_ in (
            "termos-b3-politica",
            "termos-b3-distribuidores",
            "termos-b3-coleta-automatizada",
            "termos-finra",
            "termos-fred",
            "termos-datajud",
            "termos-sec",
            "termos-ibge",
            "termos-fnc-colombia",
            "termos-igc-robots",
            "termos-igc-privacidade",
            "catalogo-cvm",
            "catalogo-bc",
            "catalogo-tesouro",
            "catalogo-ibama",
            "termos-cecafe-robots",
            "termos-inmet",
        )
    },
    # commodities: posição dos fundos no café e nos outros agro (CFTC, domínio público)
    "cftc-cot-disaggregated": _tabela("cftc_cot_agro"),
}


def placar() -> dict[str, int]:
    """Quantas fontes há em cada tipo de destino (todos os tipos aparecem, mesmo com zero)."""
    contagem = dict.fromkeys(TIPOS, 0)
    for destino in DESTINOS.values():
        contagem[destino.tipo] += 1
    return contagem
