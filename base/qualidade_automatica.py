"""Exigência 7 da prontidão: qualidade automática de cada tabela (ADR 0027; ADR 0108, Emenda 1, D10).

Cada tabela que a API serve tem uma `Regra` escrita à mão: a chave natural da linha, o que pode ficar
vazio nela e por quê, a coluna de data e a de valor. `avaliar` compara as medidas que a porta tira
(`Porta.perfil`) com a regra. O que não bate e não tem explicação escrita deixa a tabela **vermelha**:
sem a prova da 7, sem prontidão. As regras só apontam, nunca corrigem.

- **linhas repetidas** na chave (além do aceito, com o motivo);
- **vazio** numa coluna da chave que não é opcional;
- **ano faltando** entre o primeiro e o último;
- **salto** de linhas entre anos seguidos (mais que o dobro, ou menos que a metade);
- **escala**: a mediana do valor de um ano ≥ 10 vezes a do ano anterior, ou o inverso.

O ano em curso só tem parte dos dados: salto e escala não o comparam (o ano faltando e a chave contam).

Quem mede e grava o resultado do dia é `scripts/conferir_qualidade.py`.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from zoneinfo import ZoneInfo

BRASILIA = ZoneInfo("America/Sao_Paulo")
FATOR_DE_SALTO = 2.0
FATOR_DE_ESCALA = 10.0


@dataclass(frozen=True)
class Regra:
    chave: tuple[str, ...]
    periodo: str | None = None
    valor: str | None = None
    opcionais: Mapping[str, str] = field(
        default_factory=dict
    )  # coluna da chave -> por que pode faltar
    repetidas_aceitas: int = 0
    porque_repetidas: str = ""
    saltos_explicados: Mapping[int, str] = field(
        default_factory=dict
    )  # ano -> o que houve


@dataclass(frozen=True)
class Achado:
    texto: str
    explicacao: str = ""


def _por_ano(perfil: Mapping[str, object]) -> dict[int, tuple[int, float | None]]:
    return dict(perfil["por_ano"])  # type: ignore[arg-type]


def _faltando(anos: list[int]) -> list[int]:
    return sorted(set(range(min(anos), max(anos) + 1)) - set(anos)) if anos else []


def _salto(antes: int, agora: int) -> bool:
    return antes > 0 and (
        agora > antes * FATOR_DE_SALTO or agora < antes / FATOR_DE_SALTO
    )


def _da_chave(regra: Regra, perfil: Mapping[str, object]) -> list[Achado]:
    achados = []
    repetidas = int(perfil["repetidas"])  # type: ignore[call-overload]
    if repetidas > regra.repetidas_aceitas:
        achados.append(
            Achado(
                f"{repetidas} linhas repetidas na chave (aceitas: {regra.repetidas_aceitas})"
            )
        )
    elif repetidas:
        achados.append(
            Achado(f"{repetidas} linhas repetidas na chave", regra.porque_repetidas)
        )
    vazios: Mapping[str, int] = perfil["vazios_na_chave"]  # type: ignore[assignment]
    for coluna, n in vazios.items():
        if n and coluna not in regra.opcionais:
            achados.append(Achado(f"{n} linhas com `{coluna}` vazia na chave"))
        elif n:
            achados.append(
                Achado(
                    f"{n} linhas com `{coluna}` vazia na chave", regra.opcionais[coluna]
                )
            )
    return achados


def _dos_anos(
    regra: Regra, perfil: Mapping[str, object], ano_em_curso: int
) -> list[Achado]:
    por_ano = _por_ano(perfil)
    if not por_ano:
        return []
    achados = [Achado(f"ano faltando: {ano}") for ano in _faltando(list(por_ano))]
    anos = sorted(por_ano)
    for antes, ano in pairwise(anos):
        if ano >= ano_em_curso:
            continue
        (linhas_antes, escala_antes), (linhas, escala) = por_ano[antes], por_ano[ano]
        if _salto(linhas_antes, linhas):
            texto = f"{ano}: {linhas_antes} -> {linhas} linhas em relação a {antes}"
            achados.append(Achado(texto, regra.saltos_explicados.get(ano, "")))
        if (
            escala
            and escala_antes
            and max(escala / escala_antes, escala_antes / escala) >= FATOR_DE_ESCALA
        ):
            achados.append(
                Achado(
                    f"{ano}: a mediana do valor mudou de escala em relação a {antes}",
                    regra.saltos_explicados.get(ano, ""),
                )
            )
    return achados


def avaliar(
    regra: Regra, perfil: Mapping[str, object], ano_em_curso: int | None = None
) -> list[Achado]:
    """Tudo o que a regra aponta na tabela, com a explicação escrita quando há."""
    return [
        *_da_chave(regra, perfil),
        *_dos_anos(regra, perfil, ano_em_curso or datetime.now(BRASILIA).year),
    ]


def sem_explicacao(achados: list[Achado]) -> list[Achado]:
    return [a for a in achados if not a.explicacao]


REGRAS: dict[str, Regra] = {
    "demonstracoes_como_era": Regra(
        chave=(
            "cnpj",
            "documento",
            "referencia",
            "versao",
            "origem",
            "ordem",
            "grupo",
            "demonstracao",
            "conta",
            "inicio",
            "fim",
        ),
        periodo="referencia",
        valor="valor",
        opcionais={
            "inicio": "balanço patrimonial é uma foto do dia: não tem data de início"
        },
        saltos_explicados={
            2011: "2010 só tem a DFP; o ITR entra a partir de 2011",
            2021: "a partir de 2021 a tabela guarda também as versões lidas do ENET (origem `enet`), além dos dados abertos",
        },
    ),
    "cadastro_de_fundos": Regra(
        # o cadastro repete o fundo uma vez por gestor, auditor, custodiante, administrador e controlador
        chave=(
            "TP_FUNDO",
            "CNPJ_FUNDO",
            "CD_CVM",
            "CPF_CNPJ_GESTOR",
            "CNPJ_AUDITOR",
            "CNPJ_CUSTODIANTE",
            "CNPJ_ADMIN",
            "CNPJ_CONTROLADOR",
        ),
        opcionais={
            "CD_CVM": "fundo ainda em análise na CVM, sem código",
            "CPF_CNPJ_GESTOR": "quase todos são fundos cancelados, que a CVM deixa sem gestor",
            "CNPJ_AUDITOR": "fundo sem auditor informado (os cancelados, em geral)",
            "CNPJ_CUSTODIANTE": "fundo sem custodiante informado",
            "CNPJ_ADMIN": "fundo sem administrador informado (os cancelados, em geral)",
            "CNPJ_CONTROLADOR": "fundo sem controlador informado",
        },
        repetidas_aceitas=1,
        porque_repetidas="um par de linhas do mesmo CNPJ que só difere na situação do fundo (`SIT`); a base não corrige",
    ),
    "carteiras_dos_fundos": Regra(
        chave=(
            "competencia",
            "cnpj_fundo",
            "tipo_do_fundo",
            "tipo",
            "codigo",
            "descricao",
            "quantidade",
            "valor",
            "compras",
            "vendas",
        ),
        periodo="competencia",
        valor="valor",
        opcionais={
            c: "posição sem esse campo no arquivo da CVM"
            for c in ("codigo", "quantidade", "valor", "compras", "vendas")
        },
        repetidas_aceitas=100,
        porque_repetidas="linhas idênticas em todas as colunas, duplicadas no arquivo da CVM (cerca de 0,0005% da tabela); a base não corrige",
    ),
    # retrato mensal da Receita: um único mês por vez, sem série por ano para comparar; vale a chave única
    # (um estabelecimento por CNPJ de 14 dígitos) e nenhuma coluna de cadastro vazia
    "cnpj_estabelecimentos_pj": Regra(
        chave=(
            "cnpj",
            "cnpj_basico",
            "matriz",
            "situacao_cadastral",
            "uf",
            "municipio",
            "cnae_principal",
            "data_inicio_atividade",
        ),
    ),
    "cnpj_empresas_pj": Regra(
        chave=("cnpj_basico", "razao_social", "natureza_juridica", "porte"),
    ),
    # ---- tabelas do roteiro de M&A (linha 784, piloto D11): chave = a do dicionário; primeira medida de 12/11/2026
    "rotulos_atraso": Regra(chave=("cnpj", "documento", "referencia"), periodo="prazo"),
    "cnpj_situacao_cadastral": Regra(chave=("cnpj", "mes_do_retrato")),
    "cnpj_situacao_especial": Regra(chave=("cnpj", "mes_do_retrato")),
    "susep_seguros": Regra(
        chave=("competencia", "coenti", "cogrupo", "coramo", "visto_em"),
        periodo="competencia",
        opcionais={
            "coramo": "2 linhas de 1995 (grupo 99999 de uma só entidade) chegam da SUSEP sem o ramo"
        },
    ),
    "eventos": Regra(
        chave=("protocolo", "versao"),
        periodo="publicado_em",
        repetidas_aceitas=3,
        porque_repetidas="3 protocolos repetem protocolo e versão com assunto e link diferentes (documentos distintos na mesma entrega); a base não corrige",
    ),
    # o ano é o de `conhecido_em` (o arquivo começa em maio de 2010); `efetiva_em` vai de 2001 a 2027 e é esparsa
    "trocas_de_auditor": Regra(
        chave=("cnpj", "efetiva_em", "novo_id"),
        periodo="conhecido_em",
        saltos_explicados={
            2011: "2010 só tem as trocas conhecidas de maio a dezembro, quando o arquivo começa",
            2012: "pico compatível com o rodízio obrigatório do auditor independente a cada cinco anos (pico a cada cinco anos: 2012, 2017, 2022)",
            2013: "volta ao patamar normal depois do pico do rodízio de 2012",
            2017: "pico compatível com o rodízio obrigatório do auditor independente a cada cinco anos (pico a cada cinco anos: 2012, 2017, 2022)",
            2018: "volta ao patamar normal depois do pico do rodízio de 2017",
            2022: "pico compatível com o rodízio obrigatório do auditor independente a cada cinco anos (pico a cada cinco anos: 2012, 2017, 2022)",
            2023: "volta ao patamar normal depois do pico do rodízio de 2022",
        },
    ),
    "fca_geral": Regra(chave=("cnpj", "referencia", "versao"), periodo="referencia"),
    "aneel_samp": Regra(
        chave=(
            "competencia",
            "cnpj",
            "tipo_de_mercado",
            "modalidade_tarifaria",
            "subgrupo_tarifario",
            "classe_de_consumo",
            "subclasse_de_consumo",
            "detalhe_do_consumidor",
            "nucleo_ceg",
            "posto_tarifario",
            "opcao_de_energia",
            "detalhe_do_mercado",
            "visto_em",
        ),
        periodo="competencia",
        opcionais={
            "nucleo_ceg": "a fonte deixa em branco o CEG de algumas usinas da opção de energia Geração (2023 a 2026); as demais linhas trazem 0"
        },
    ),
    "anp_concessionarios": Regra(
        chave=("numero_do_contrato", "cnpj", "visto_em"), periodo="disponivel_em"
    ),
    "entidades": Regra(chave=("id_entidade",)),
    "ligacoes": Regra(
        chave=("de", "para", "tipo", "papel", "aconteceu_em", "fonte"),
        opcionais={
            "papel": "os tipos controlada_de, participada_de, coligada_de, audita e emite não têm papel: ele só existe nos tipos detem, do_conglomerado_de e opera_para"
        },
    ),
    "identificadores": Regra(
        chave=("id_entidade", "sistema", "valor", "desde"),
        opcionais={
            "desde": "só o ticker e o emissor trazem o dia em que o código passou a valer; os registros oficiais (CNPJ, ISIN, códigos da CVM e das agências) não dizem"
        },
    ),
    "controladas": Regra(
        chave=("cnpj_companhia", "referencia", "versao", "cnpj"),
        periodo="referencia",
        opcionais={
            "cnpj": "investida sem CNPJ no formulário de referência; só se distingue pelo nome"
        },
        repetidas_aceitas=8373,
        porque_repetidas="a maior parte são investidas sem CNPJ que só se distinguem pelo nome; 866 linhas são idênticas em todas as colunas; o resto repete o CNPJ com participação ou tipo diferente no mesmo documento. Quem junta por CNPJ pode receber mais de uma linha; a base não corrige",
    ),
    "entradas_de_socio_pj": Regra(
        chave=(
            "movimento",
            "cnpj_basico",
            "raiz_socio_pj",
            "data_entrada",
            "mes_do_retrato",
        )
    ),
    # sem série por ano: os registros vão de 1957 a hoje, esparsos nos primeiros anos, e contar registros por ano não mede se falta carga
    "registro_de_fundos": Regra(
        chave=("ID_Registro_Fundo", "CPF_CNPJ_Gestor"),
        opcionais={
            "CPF_CNPJ_Gestor": "fundo cancelado, que a CVM deixa sem gestor (99% dos casos), ou gestor pessoa física, sem CPF na base"
        },
        repetidas_aceitas=17,
        porque_repetidas="linhas idênticas em todas as colunas, nas colunas que a base guarda (o diretor responsável sai na montagem); a base não corrige",
    ),
    # cópia reduzida que vai ao VPS (linha 844): uma linha por fundo e registro; montada no envio, medida na cópia montada
    "fips_registrados": Regra(
        chave=("CNPJ_Fundo", "Data_Registro"),
        repetidas_aceitas=2,
        porque_repetidas="2 pares de fundo e data de registro (4 linhas) vêm da CVM com duas datas de cancelamento diferentes; são registros distintos na origem e a base não escolhe um",
    ),
    "pgfn_divida": Regra(
        chave=(
            "cnpj",
            "tipo_divida",
            "regiao",
            "tipo_devedor",
            "tipo_situacao",
            "situacao_inscricao",
            "ajuizado",
            "data_do_retrato",
        )
    ),
    # ANS (linha 877): uma linha por valor diferente da chave; a revisão de um mês passado vira linha nova com outro `visto_em`.
    # Medida em 12/11/2026 no acervo local: 483.875 linhas de 2017 a 2026, sem repetida e sem vazio na chave;
    # 2026 é o ano em curso (o salto e a escala não o comparam)
    "ans_beneficiarios": Regra(
        chave=(
            "competencia",
            "cd_operadora",
            "modalidade",
            "cobertura",
            "vigencia_do_plano",
            "contratacao",
            "financiamento",
            "visto_em",
        ),
        periodo="competencia",
        valor="beneficiarios",
    ),
    # estrita (Diretoria, 12/11/2026, linha 877): nenhuma linha repetida aceita. A resposta do BC de 2025-09
    # veio com cada linha ~3 vezes e a carga de 14/10 gravou assim; medida em 18/11/2026 (linha 978): verde,
    # 54.571.412 linhas e sem repetida. Sem `visto_em` na chave: os arquivos de 14/10 não têm a coluna que o
    # contrato 2.0.0 pede; quando todos a tiverem, ela entra na chave (a revisão do BC é linha nova da mesma chave).
    "ifdata_valores": Regra(
        chave=(
            "data_base",
            "tipo_instituicao",
            "cod_inst",
            "relatorio",
            "grupo",
            "conta",
            "coluna",
        ),
        periodo="data_base",
        valor="saldo",
        opcionais={
            "grupo": "só alguns relatórios do IF.data dividem as linhas em grupos; nos outros a fonte deixa o grupo vazio"
        },
        saltos_explicados={
            2014: "em 2014 começam o conglomerado prudencial (tipo 1) e os relatórios 7 a 14 (carteira de crédito)"
        },
    ),
    # Anvisa por empresa (linha 860, piloto D11): uma linha por raiz de CNPJ e por retrato (um por dia de arquivo
    # da Anvisa). Sem coluna de ano nem de valor na regra: a tabela tem um retrato só até a Anvisa publicar outro,
    # e a escala da contagem não se compara entre retratos de dias seguidos.
    "anvisa_por_empresa": Regra(chave=("cnpj_basico", "disponivel_em")),
    # Lote 1 da linha 978 (piloto D11), medido em 18/11/2026 no acervo de casa: chave natural de cada registro da fonte.
    # `aneel_inadimplencia` (24.638 linhas sem a sigla do agente e saltos de linhas em 2013 e 2014) e `fii_ativos`
    # (206.765 linhas repetidas e vazios no código e no nome do ativo) ficaram vermelhas sem explicação escrita:
    # não têm regra aqui até alguém medir a causa e escrever a explicação (ficam fora do registro de piloto).
    "aneel_indicadores_comerciais": Regra(
        chave=(
            "cnpj",
            "sigla_do_agente",
            "tipo_de_outorga",
            "referencia",
            "municipio_ibge",
            "visto_em",
        ),
        opcionais={
            "municipio_ibge": "a fonte manda `0` em vez do código IBGE em algumas linhas (15 de 280.019 em 18/11/2026); o construtor deixa vazio e a base não preenche"
        },
        periodo="referencia",
        valor="unidades_ativas",
    ),
    "ans_idss": Regra(
        chave=("registro_operadora", "indice", "ano_avaliacao", "ano_base", "visto_em")
    ),
    "fii_administradores": Regra(chave=("cnpj", "visto_em")),
    "fii_informe_mensal": Regra(
        chave=("cnpj", "referencia", "versao", "visto_em"),
        periodo="referencia",
        valor="patrimonio_liquido",
    ),
    "fip_informe": Regra(
        chave=("cnpj", "competencia", "periodicidade", "visto_em"),
        periodo="competencia",
        valor="patrimonio_liquido",
    ),
    # Lote 2A da linha 978 (piloto D11), medido em 18/11/2026 no acervo de casa: chave natural de cada registro (a do
    # dicionário). As outras 13 tabelas do lote 2 mediram vermelho sem explicação escrita e não têm regra aqui até
    # alguém medir a causa: fre_capital_social, fre_conselho, fre_remuneracao, ratings, valores_mobiliarios,
    # tickers_no_tempo, codigos_invalidos, dmpl_como_era, insolvencia, negociacoes, anm_cfem_arrecadacao,
    # painel_dos_fundos e securitizacao_certificados.
    "fre_comites": Regra(
        chave=("cnpj", "referencia", "versao", "tipo_de_comite"), periodo="referencia"
    ),
    "fre_distribuicao_capital": Regra(
        chave=("cnpj", "referencia", "versao", "id_documento"), periodo="referencia"
    ),
    "fre_diversidade": Regra(
        chave=("cnpj", "referencia", "versao", "orgao"), periodo="referencia"
    ),
    "fre_empregados": Regra(
        chave=("cnpj", "referencia", "versao", "recorte", "grupo"), periodo="referencia"
    ),
    "fre_remuneracao_extremos": Regra(
        chave=("cnpj", "referencia", "versao", "fim_do_exercicio", "orgao"),
        periodo="referencia",
        valor="media",
    ),
    "pareceres_dfp": Regra(
        chave=("cnpj", "referencia", "versao"), periodo="referencia"
    ),
    "pareceres_itr": Regra(
        chave=("cnpj", "referencia", "versao"), periodo="referencia"
    ),
    "emissores": Regra(chave=("emissor", "cnpj")),
    "debentures_assembleias": Regra(chave=("link",), periodo="referencia"),
    "processos_nas_notas": Regra(
        chave=("cnpj", "referencia", "versao", "pagina", "numero_processo"),
        periodo="referencia",
    ),
    # Lote 2B da linha 978 (piloto D11), medido em 18/11/2026 na VM (só contagens). `aneel_inadimplencia` e `fii_ativos`
    # ficaram vermelhas no lote 1 só pela chave do rascunho; medidas de novo, a chave certa não repete:
    # - aneel_inadimplencia (1.144.238 linhas): `sigla_do_agente` vem vazia em 24.638 linhas e não é da chave; com
    #   (cnpj, indicador, referencia, visto_em) há 0 repetidas e 0 vazias.
    # - fii_ativos (245.030 linhas): 243.192 linhas não têm `codigo` e 231.768 não têm `nome_do_ativo`, então não há
    #   chave natural nelas; vale o `id_na_fonte` com o `visto_em` (0 repetidas, 0 linhas iguais). O mesmo
    #   `id_na_fonte` aparece em dois `visto_em` em 32.615 casos: é o histórico (um retrato por data), não duplicata.
    "aneel_inadimplencia": Regra(
        chave=("cnpj", "indicador", "referencia", "visto_em"),
        periodo="referencia",
        valor="valor",
        saltos_explicados={
            2013: "o arquivo da ANEEL tem pouca linha em 2012 (5.120) e em 2013 (11.200); a tabela guarda o que a fonte manda e não completa o que falta (medido em 18/11/2026; o motivo na ANEEL não foi confirmado)",
            2014: "a série cheia da fonte, de cerca de 90 mil linhas por ano, começa em 2014 (11.200 linhas em 2013 e 94.792 em 2014, medido em 18/11/2026; o motivo na ANEEL não foi confirmado)",
        },
    ),
    "fii_ativos": Regra(
        chave=("id_na_fonte", "visto_em"), periodo="referencia", valor="valor"
    ),
    "cvm_fiagro": Regra(
        chave=("cnpj", "referencia", "versao"),
        periodo="referencia",
        valor="patrimonio_liquido",
    ),
    # Lote 3 da linha 978 (piloto D11): séries sem CNPJ (órgãos públicos e mercado) e três tabelas ligadas pelo CNPJ.
    # A chave é a `chaves` do contrato; o período, a coluna de `aconteceu_em` quando é uma data.
    "anac_estatistico": Regra(
        chave=(
            "competencia",
            "empresa_sigla",
            "aeroporto_de_origem_sigla",
            "aeroporto_de_destino_sigla",
            "natureza",
            "grupo_de_voo",
        ),
        periodo="competencia",
        valor="passageiros_pagos",
    ),
    "anm_amb_agua_mineral": Regra(chave=("ano", "uf", "substancia")),
    "anm_amb_producao_beneficiada": Regra(
        chave=("ano", "uf", "substancia", "contido_indicacao")
    ),
    "anm_amb_producao_bruta": Regra(
        chave=("ano", "uf", "substancia", "contido_indicacao")
    ),
    "anp_vendas": Regra(
        chave=(
            "competencia",
            "grupo",
            "agente",
            "codigo_do_produto",
            "uf_origem",
            "uf_destino",
            "mercado_destino",
        ),
        periodo="competencia",
        valor="quantidade",
    ),
    "antt_siade": Regra(
        chave=(
            "competencia",
            "ferrovia",
            "mercadoria",
            "estacao_de_origem",
            "estacao_de_destino",
            "visto_em",
        ),
        periodo="competencia",
        valor="toneladas_uteis",
    ),
    "area_cafe_municipio": Regra(
        chave=("codigo", "ano"), periodo="referencia", valor="area_total_ha"
    ),
    "bcb_selic_focus": Regra(
        chave=("serie", "referencia", "divulgado_em"),
        periodo="referencia",
        valor="valor",
    ),
    "ccee_pld": Regra(
        chave=("granularidade", "submercado", "referencia", "ordem"),
        periodo="referencia",
        valor="pld",
    ),
    "cftc_cot_agro": Regra(
        chave=("relatorio", "contrato"), periodo="relatorio", valor="open_interest"
    ),
    "clima_regiao_cafe": Regra(
        chave=("regiao", "competencia", "fonte"),
        periodo="competencia",
        valor="chuva_mm",
    ),
    "cnes_competencias": Regra(chave=("competencia",), periodo="competencia"),
    "comex_cafe": Regra(
        chave=("competencia", "ncm", "uf_origem", "codigo_do_pais", "divulgado_em"),
        periodo="competencia",
        valor="vl_fob_usd",
    ),
    "comex_urf": Regra(chave=("urf", "visto_em")),
    "comex_via": Regra(chave=("via", "visto_em")),
    "conab_cafe": Regra(
        chave=("safra", "levantamento", "tipo", "uf", "divulgado_em"),
        valor="producao_mil_sacas",
    ),
    "curva_juros": Regra(
        chave=("data_base", "curva", "prazo_anos"), periodo="data_base", valor="taxa"
    ),
    "faostat_cafe": Regra(
        chave=("codigo_do_pais", "ano", "elemento", "divulgado_em"), valor="valor"
    ),
    "ma_datas": Regra(chave=("assessoria", "url"), periodo="fechamento_em"),
    "ons_capacidade": Regra(
        chave=("cod_equipamento", "visto_em"), valor="potencia_efetiva_mw"
    ),
    "ons_restricao": Regra(
        chave=("instante", "tipo", "id_ons", "visto_em"),
        periodo="instante",
        valor="geracao_mwmed",
    ),
    "usda_psd_cafe": Regra(
        chave=("codigo_do_pais", "ano_safra", "atributo", "tipo", "divulgado_em"),
        valor="valor",
    ),
    "contraparte_cafe": Regra(chave=("id", "fato", "data"), periodo="data"),
    "ma_candidatos": Regra(chave=("link",), periodo="referencia"),
    "ma_regua": Regra(chave=("assessoria", "url"), periodo="fechamento_em"),
    # integridade (linha 981): sanções da CGU, embargos do IBAMA e Lista Suja do MTE; a chave é a do contrato (uma linha por
    # valor diferente da fonte, a mudança vira linha nova com outro `visto_em`)
    "sancoes_cgu": Regra(chave=("cadastro", "id_na_fonte", "visto_em")),
    "ibama_embargos": Regra(chave=("id_na_fonte", "visto_em")),
    "mte_lista_suja": Regra(chave=("id_na_fonte", "visto_em")),
    # conjunto `extended_sources` da frente 3 (ADR 0122, Emenda 2): a chave é a do contrato de cada tabela
    "anatel_pados": Regra(chave=("id_na_fonte", "visto_em")),
    "anatel_produtos_homologados": Regra(chave=("id_na_fonte", "visto_em")),
    "anm_tah": Regra(chave=("id_na_fonte", "visto_em")),
    "anp_tancagem": Regra(chave=("id_na_fonte", "visto_em")),
    "mte_pat": Regra(chave=("id_na_fonte", "visto_em")),
    # compras públicas (linha 988): o cadastro do SICAF é um retrato (sem data de fato, uma linha por CNPJ); no BPS
    # cada compra tem o dia e o preço, então o salto de linhas e a escala do preço entre os anos contam
    "comprasgov_sicaf": Regra(chave=("id_na_fonte", "visto_em")),
    "bps_compras": Regra(
        chave=("id_na_fonte", "visto_em"), periodo="data_da_compra", valor="preco_total"
    ),
    # setores (linha 978): a ligação das entidades dos reguladores às companhias e os acessos da Anatel.
    # Medido na base de 19/11/2026 (só contagens): na `empresa_serie`, via e desde só existem na linha ligada a
    # uma companhia (as 19 ligações do comexstat não trazem `desde`); a chave com `via` e `desde` não repete linha.
    "empresa_serie": Regra(
        chave=("fonte", "chave", "cnpj_companhia", "via", "desde"),
        opcionais={
            "cnpj_companhia": "toda entidade aparece, ligada ou não: a que nenhuma companhia aberta controla fica sem companhia",
            "via": "só a linha ligada a uma companhia diz por qual via (própria, controlada, coligada); entidade sem companhia fica sem via",
            "desde": "só a ligação com companhia tem a data em que apareceu; as 19 ligações do comexstat (produto) não a trazem na fonte",
        },
    ),
    # Na `anatel_acessos` cada planilha (arquivo, serviço e recorte) ou traz uma coluna em todas as linhas ou em
    # nenhuma (medido: zero planilhas mistas nas 11 colunas): o vazio é do layout da planilha, não de dado perdido.
    "anatel_acessos": Regra(
        chave=(
            "competencia",
            "servico",
            "recorte",
            "cnpj",
            "uf",
            "regiao_pgo",
            "codigo_nacional",
            "modalidade_de_cobranca",
            "tecnologia",
            "geracao",
            "tipo_de_pessoa",
            "tipo_de_produto",
            "faixa_de_velocidade",
            "meio_de_acesso",
            "tipo_de_acesso_tv",
            "visto_em",
        ),
        periodo="competencia",
        valor="acessos",
        opcionais={
            coluna: "a Anatel publica uma planilha por serviço e recorte, cada uma com as suas colunas: onde a planilha não tem o campo ele fica vazio em todas as linhas dela"
            for coluna in (
                "uf",
                "regiao_pgo",
                "codigo_nacional",
                "modalidade_de_cobranca",
                "tecnologia",
                "geracao",
                "tipo_de_pessoa",
                "tipo_de_produto",
                "faixa_de_velocidade",
                "meio_de_acesso",
                "tipo_de_acesso_tv",
            )
        },
        saltos_explicados={
            2007: "a série de banda larga fixa começa em 2007 (319 prestadoras, mediana de 35 acessos contra 92 mil da telefonia móvel): entrou um serviço de escala bem menor",
            2011: "a banda larga fixa passa de 4 para 12 competências por ano (o recorte mensal), o que quadruplica as linhas sem mudar de fonte; a mediana do conjunto muda porque a banda larga fixa (mediana perto de 45 acessos) passa a pesar mais que a telefonia móvel (perto de 56 mil)",
        },
    ),
}
