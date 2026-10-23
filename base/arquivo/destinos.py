"""Destino de cada fonte do arquivista: para onde vai o que ela baixa (ADR 0076, série T).

Toda `Fonte.id` de `base/arquivo/fontes.py` tem uma entrada aqui, e um teste quebra o CI se faltar
(ou sobrar) uma. Assim uma fonte não passa dias sendo baixada sem virar tabela sem que ninguém
veja. Quando uma fonte planejada ganhar a tabela, troque o tipo para `tabela` neste arquivo.

Em `onde` vai só o nome da série e do PR (o repositório é público).
"""

from dataclasses import dataclass

from base.arquivo import (
    lote_atencao,
    lote_brasil2,
    lote_cadastros,
    lote_cvm,
    lote_eua,
    lote_licitacoes,
    lote_setoriais,
)

TABELA = "tabela"  # vira tabela com contrato no catálogo da base
SO_LIGA = "so_liga"  # hoje só liga nomes (rede de relações), sem tabela própria
SO_PESQUISA = (
    "so_pesquisa"  # cópia de pesquisa fora do catálogo: BDI e barras de 1 minuto da B3
)
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


def _ids(prefixo: str, *sufixos: str) -> tuple[str, ...]:
    return tuple(f"{prefixo}-{sufixo}" for sufixo in sufixos)


_LOTE_ORGANISMOS: dict[str, tuple[str, ...]] = {
    "câmbio, juros, inflação e crédito da zona do euro nas séries do BCE": _ids(
        "bce",
        "cambio-dolar",
        "cambio-real",
        "curva-10a",
        "juro-principal",
        "inflacao-ipch",
        "balanco-bancos",
        "juro-credito",
    ),
    "indicador antecedente composto de 12 países na OCDE (Brasil primeiro)": (
        "ocde-cli",
    ),
    "séries da União Europeia no Eurostat (só países da UE)": _ids(
        "eurostat",
        "confianca",
        "desemprego",
        "ipch",
        "juro-longo",
        "pib",
        "producao-industrial",
    ),
    "câmbio, juros, crédito e imóveis nas séries do BIS (marca não comercial)": _ids(
        "bis",
        "cambio",
        "cambio-efetivo-nominal",
        "cambio-efetivo-real",
        "inflacao-longa",
        "juro-dos-bancos-centrais",
        "lacuna-de-credito",
        "preco-de-imoveis",
    ),
    "câmbio, inflação, reservas e perspectivas do FMI (marca não comercial)": _ids(
        "fmi",
        "cambio",
        "inflacao",
        "reservas-do-mundo",
        "weo-bca_ngdpd",
        "weo-ggxwdg_ngdp",
        "weo-ngdp_rpch",
        "weo-pcpipch",
    ),
    "indicadores do Banco Mundial para o Brasil e para o mundo": _ids(
        "worldbank",
        "brasil",
        "mundo-fp-cpi-totl-zg",
        "mundo-ny-gdp-mktp-kd-zg",
        "mundo-sp-pop-totl",
    ),
    "emissores de LEI e autoridades de registro do GLEIF": _ids(
        "gleif", "emissores", "autoridades-de-registro"
    ),
    "clima mensal por ponto de cada região cafeeira na NASA POWER": _ids(
        "nasa-power",
        "alta-paulista",
        "bahia-atlantico",
        "cerrado-mineiro",
        "chapada-de-minas",
        "es-montanhas",
        "es-norte",
        "matas-de-minas",
        "mogiana",
        "norte-do-parana",
        "oeste-da-bahia",
        "planalto-da-bahia",
        "rondonia",
        "sul-de-minas",
    ),
    "índices de teleconexão (NAO, AO, PNA) do NOAA CPC": _ids(
        "noaa", "ao", "nao", "pna", "teleconexoes"
    ),
}

_LOTE_EUA_SO_ARQUIVO = (
    "dado público do governo dos EUA guardado como publicado; a tabela com contrato no catálogo "
    "ainda não existe (sem pessoa física nas tabelas derivadas)"
)

_LOTE_ATENCAO_SO_ARQUIVO = (
    "atenção e texto guardados já filtrados (contagem, tema, tom e índice; nunca pessoa nem texto de "
    "terceiros); a tabela com contrato no catálogo ainda não existe"
)
_LOTE_CADASTROS_SO_ARQUIVO = (
    "cadastro ou lista de sanções guardado como publicado, só pessoa jurídica (a firma individual e a "
    "pessoa física saem antes de guardar); a tabela com contrato no catálogo ainda não existe"
)

_LOTE_SETORIAIS_SO_ARQUIVO = (
    "dado aberto de órgão público brasileiro guardado como publicado; a tabela com contrato no "
    "catálogo ainda não existe (INPI só com os arquivos sem pessoa física)"
)

_LOTE_LICITACOES_SO_ARQUIVO = (
    "licitação e contrato públicos guardados só com pessoa jurídica (LGPD, ADR 0088); a tabela com "
    "contrato no catálogo ainda não existe"
)

_LOTE_BRASIL2_SO_ARQUIVO = (
    "dado aberto de órgão público brasileiro guardado como publicado, só CNPJ e agregados (a pessoa "
    "física sai antes de guardar, ADR 0088); a tabela com contrato no catálogo ainda não existe"
)

_LOTE_CVM_SO_ARQUIVO = (
    "dado aberto da CVM (ODbL) guardado como publicado, só fundo, CNPJ e agregado (sem cadastro de "
    "pessoa, ADR 0088); a tabela com contrato no catálogo ainda não existe"
)

DESTINOS: dict[str, Destino] = {
    # CVM
    "cvm-hist-dfp": _tabela("demonstracoes_como_era", "dmpl_como_era", "pareceres_dfp"),
    "cvm-hist-itr": _tabela("demonstracoes_como_era", "dmpl_como_era", "pareceres_itr"),
    "cvm-hist-fre": _tabela(
        "fre_comites",
        "fre_conselho",
        "fre_diversidade",
        "fre_capital_social",
        "fre_empregados",
        "fre_acionistas",
        "fre_partes_relacionadas",
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
    # lote BCB e SICONFI da rodada 1 (linha 242 da fila): guardados; a carga na base é a linha seguinte
    "bcb-mercado-imobiliario": _planejada(
        "rodada-1/lote-bcb", "crédito imobiliário do Banco Central, por tipo e região"
    ),
    "bcb-str": _planejada(
        "rodada-1/lote-bcb", "giro, TED e portabilidade de crédito no STR, por dia"
    ),
    "bcb-consorcios": _planejada(
        "rodada-1/lote-bcb", "panorama trimestral dos consórcios, com o dicionário"
    ),
    "bcb-leiloes-selic": _planejada(
        "rodada-1/lote-bcb", "leilões de títulos públicos e de swap cambial do BC"
    ),
    "bcb-tarifas-instituicao": _planejada(
        "rodada-1/lote-bcb", "tarifas de cada banco listado"
    ),
    "bcb-cosif": _planejada(
        "rodada-1/lote-bcb", "balancete mensal (4010) de cada banco listado"
    ),
    "tesouro-br-siconfi-entes": _planejada(
        "rodada-1/lote-bcb", "estados e municípios do SICONFI, com o CNPJ do ente"
    ),
    "tesouro-br-siconfi-entregas": _planejada(
        "rodada-1/lote-bcb", "o que cada estado e capital entregou ao SICONFI"
    ),
    "tesouro-br-siconfi-rreo": _planejada(
        "rodada-1/lote-bcb", "RREO de estados e capitais, por bimestre"
    ),
    "tesouro-br-siconfi-rgf": _planejada(
        "rodada-1/lote-bcb", "RGF do Executivo de estados e capitais, por quadrimestre"
    ),
    "tesouro-br-siconfi-dca": _planejada(
        "rodada-1/lote-bcb", "balanço anual (DCA) de estados e capitais"
    ),
    "tesouro-br-divida": _planejada(
        "serie-T/T7", "estoque e emissões da dívida federal, CAPAG e dívida dos estados"
    ),
    "rfb-cnpj": _tabela("cnpj_situacao_especial"),
    "pgfn-divida": _tabela("pgfn_divida"),
    # setoriais
    "anp-vendas-distribuidora": _tabela("anp_vendas"),
    "anp-producao-poco": _planejada("serie-5/PR3", "produção por poço, com o operador"),
    "anp-concessionarios": _tabela("anp_concessionarios"),
    "ons-geracao-usina": _tabela("ons_geracao"),
    "ons-capacidade-geracao": _tabela("ons_capacidade"),
    "ons-restricao-eolica-solar": _tabela("ons_restricao"),
    "ccee-pld": _tabela("ccee_pld"),
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
    "antt-siade": _tabela("antt_siade"),
    "comexstat": _tabela("comex_cafe", "comex_preco_medio"),
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
    "conab-cafe-safra": _tabela("conab_cafe"),
    "conab-cafe-publicacao": _tabela("conab_cafe"),
    # balanço mundial do café (PR 4)
    "usda-psd-cafe": _tabela("usda_psd_cafe"),
    "faostat-cafe": _tabela("faostat_cafe"),
    "ico-relatorio-mensal": _planejada(
        "cafe/PR4",
        "balanço mundial do café a partir do relatório mensal da ICO em PDF; marca 'não comercial' "
        "registrada, coleta e uso citando a ICO e a data (ADR 0102)",
    ),
    # clima por região cafeeira (plano do café, PR 8): `base/commodities/clima_regiao.py`
    "inmet-bdmep": _tabela("clima_regiao_cafe"),
    "chirps-mensal": _tabela("clima_regiao_cafe"),
    "chirps-historico": _tabela("clima_regiao_cafe"),
    "ibge-malha-municipal": _tabela("clima_regiao_cafe"),
    # área de café por município (plano do café, PR 8): `base/commodities/area_municipio.py`
    "mapbiomas-cafe": _tabela("area_cafe_municipio"),
    # lote organismos (dados escondidos, rodada 1): guardado no acervo, tabelas ainda não escritas
    **{
        id_: _planejada("dados-escondidos/rodada-1", porque)
        for porque, ids in _LOTE_ORGANISMOS.items()
        for id_ in ids
    },
    # lote setoriais Brasil (linha 245 da fila, 22/10/2026): guardado no acervo, tabelas ainda não escritas
    **{
        f.id: _planejada("dados-escondidos/rodada-1", _LOTE_SETORIAIS_SO_ARQUIVO)
        for f in lote_setoriais.fontes()
    },
    # lote licitações e contratos (linha 288 da fila, rodada 4): guardado no acervo, tabelas ainda não escritas
    **{
        f.id: _planejada("dados-escondidos/rodada-4", _LOTE_LICITACOES_SO_ARQUIVO)
        for f in lote_licitacoes.fontes()
    },
    # lote Brasil segunda camada (linhas 259, 260 e 262 da fila, 23/10/2026): guardado no acervo, tabelas ainda não escritas
    **{
        f.id: _planejada("dados-escondidos/brasil-camada-2", _LOTE_BRASIL2_SO_ARQUIVO)
        for f in lote_brasil2.fontes()
    },
    # lote cadastros globais (rodada 4, linha 287): guardado no acervo, tabelas ainda não escritas
    **{
        f.id: _planejada("dados-escondidos/rodada-4", _LOTE_CADASTROS_SO_ARQUIVO)
        for f in lote_cadastros.fontes()
    },
    # lote atenção e texto (rodada 4, linha 289): guardado no acervo, tabelas ainda não escritas
    **{
        f.id: _planejada("dados-escondidos/rodada-4", _LOTE_ATENCAO_SO_ARQUIVO)
        for f in lote_atencao.fontes()
    },
    # lote CVM (linha 200 da fila, 23/10/2026): guardado no acervo; as tabelas são o lote 2
    **{
        f.id: _planejada("cvm-lote-2/tabelas", _LOTE_CVM_SO_ARQUIVO)
        for f in lote_cvm.fontes()
    },
    "cvm-fundos-informe-diario": _planejada(
        "cvm-lote-2/cota-por-fundo",
        "cota, patrimônio e captação diária de cada fundo 555",
    ),
    "cvm-fii-mensal": _planejada("cvm-lote-2/tela-de-fii", "informe mensal dos FII"),
    "cvm-fii-trimestral": _planejada(
        "cvm-lote-2/tela-de-fii", "informe trimestral dos FII"
    ),
    "cvm-fii-anual": _planejada("cvm-lote-2/tela-de-fii", "informe anual dos FII"),
    "cvm-fii-demonstracoes": _planejada(
        "cvm-lote-2/tela-de-fii", "demonstrações dos FII"
    ),
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
            "termos-cnpj-licenca",
            "termos-bce",
            "termos-eurostat",
            "termos-bis",
            "termos-nasa-power",
            "termos-noaa",
            "termos-kraken",
            "termos-yahoo",
            "termos-gdelt",
            "termos-gleif",
            "termos-faostat",
            "termos-chirps",
            "termos-mapbiomas",
            "termos-iex",
            "termos-banco-mundial",
            *lote_eua.termos(),
            *lote_cadastros.termos(),
            *lote_atencao.termos(),
        )
    },
    # lote EUA (rodada 1 da pesquisa de dados escondidos, 22/10/2026): guardado como as agências
    # publicam; a carga na base de ML (tabelas, contratos, dicionário) é uma fila própria
    **{
        f.id: _planejada("lote-eua/carga", _LOTE_EUA_SO_ARQUIVO)
        for f in lote_eua.fontes()
    },
    # commodities: posição dos fundos no café e nos outros agro (CFTC, domínio público)
    "cftc-cot-disaggregated": _tabela("cftc_cot_agro"),
    # ficha das contrapartes do café (PR 12): a prova dos fatos de `base/conferidas/contrapartes_cafe.csv`
    "contrapartes-cafe": _tabela("contraparte_cafe"),
}


def placar() -> dict[str, int]:
    """Quantas fontes há em cada tipo de destino (todos os tipos aparecem, mesmo com zero)."""
    contagem = dict.fromkeys(TIPOS, 0)
    for destino in DESTINOS.values():
        contagem[destino.tipo] += 1
    return contagem
