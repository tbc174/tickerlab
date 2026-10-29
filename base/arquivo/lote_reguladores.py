"""Lote reguladores do arquivista: mais pacotes de energia (ANEEL, ONS e CCEE) que o lote setoriais de 22/10
ainda não guarda (23/10/2026, linha 203 da fila, item 13 do lançamento; levantamento de 22/10 na pasta
privada) e, no PR 2 (24/10), saúde suplementar (ANS), seguros (SUSEP) e comércio exterior (Comex Stat).

Cada fonte guarda os arquivos do pacote como o portal os publica (dados abertos, citar a fonte; as
famílias `aneel`, `ons` e `ccee` já têm licença e marca em `src/banco/coletas.py`: o id novo começa por elas).
Nada aqui é lido nem tratado: o que sai de cada arquivo é tarefa da extração.

Escolhas (testes em `tests/test_base_arquivo_lote_reguladores.py`):
- **só o que o lote setoriais não leva:** `PACOTES_DA_ANEEL`, `PACOTES_DO_ONS` e `PACOTES_DA_CCEE` de
  `lote_setoriais.py` e a `ccee-pld` ficam como estão; aqui entra o resto, sem repetir pacote;
- **LGPD (ADR 0088): nada de dado por pessoa.** Ficaram de fora, por trazer titular, beneficiário ou
  agente: `relacao-de-empreendimentos-de-geracao-distribuida` (titular da unidade),
  `agentes-de-geracao-de-energia-eletrica` (coluna de CPF ou CNPJ; hoje só CNPJ, mas nada garante amanhã, e o SIGA já traz as usinas),
  `tarifa-social-de-energia-eletrica-beneficiarios`, `beneficiarios-da-cde` e as listas de agentes e de
  perfil da CCEE (`lista_*`, `varejista_consumidor`, `mve_contrapartes`);
- **fora também, de propósito:** a BDGD da ANEEL (GBs por distribuidora, base geográfica); o
  `programacao_diaria` do ONS (um arquivo por dia desde 2024, mais de 2.000 arquivos); os `*_horaria_*`
  e `*_horario` da CCEE por usina ou agente (volume), e o EAR/ENA por REE (o ONS não tem o pacote com
  esse nome);
- **CCEE:** o portal recusa o `curl` simples (HTTP 403) e responde ao cliente do arquivista; o robots.txt
  dela proíbe a `/api/`, então as fontes leem a página de cada pacote (`_ckan_pela_pagina`, 28/10/2026),
  como o `ccee-pld`;
- **ritmo pelo calendário do pacote:** o que o portal regrava todo dia (demanda máxima e CMO
  semi-horário do ONS) roda `diaria`; carga e hidrologia, `semanal`; tarifa, qualidade, encargos,
  liquidação e risco hidrológico, `mensal`. Os arquivos grandes do ONS (um por ano ou mês) são `pesada`: o
  Arquivista só baixa o que mudou (ETag);
- **o pacote que o portal trocar de nome ou esvaziar** falha na descoberta com o nome dele (um pacote sem
  arquivo é erro, nunca "ok").

PR 2, o que muda:
- **ANS:** pastas do `FTP/PDA` guardadas inteiras (CSV, ZIP e o dicionário), uma fonte por assunto. Fora, por
  trazer reclamação de beneficiário (pessoa, LGPD): `demandas_dos_consumidores_nip` e
  `demandas_dos_consumidores_reclamacao_beneficiarios`; fora por ser só apresentação:
  `dados_consolidados_da_saude_suplementar`. As demonstrações contábeis (DIOPS) já estão em
  `ans-demonstracoes`;
- **SUSEP:** os membros grandes do `BaseCompleta.zip` (até 749 MB) numa fonte `pesada`; os pequenos já
  estão em `susep-ses` e `susep-ses-complementos`. Continuam de fora administradores, contatos,
  dependências, acionistas e grupos econômicos (pessoas e endereços);
- **Anatel:** a telefonia fixa já está em `anatel-acessos-telefonia-fixa`; o resto do catálogo da Anatel não
  respondeu em 22/10 e segue na fila;
- **Comex Stat:** as tabelas de correspondência têm o nome `NCM_SH`, `NCM_CUCI`, `NCM_ISIC`, `NCM_CGCE`...
  (os nomes `SH`, `CUCI`... devolvem uma página HTML com 200, não o CSV).
"""

import re
from datetime import datetime
from urllib.parse import urljoin

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte
from base.arquivo.lote_brasil2 import SES_DA_SUSEP
from base.arquivo.lote_setoriais import (
    FORMATOS_DA_ANEEL,
    FORMATOS_DO_ONS,
    PORTAL_DA_ANEEL,
    PORTAL_DA_CCEE,
    PORTAL_DO_ONS,
    _ckan,
    _ckan_pela_pagina,
)
from base.arquivo.obter import extrair_do_zip_remoto, membros_do_zip_remoto

DIARIA = "diaria"
SEMANAL = "semanal"
MENSAL = "mensal"

# id da fonte -> pacotes do portal da ANEEL (CSV e o dicionário em PDF)
PACOTES_DA_ANEEL: dict[str, tuple[str, ...]] = {
    "aneel-inadimplencia": ("indqual-inadimplencia",),
    "aneel-empreendimentos": (
        "empreendimentos-em-operacao",
        "ralie-relatorio-de-acompanhamento-da-expansao-da-oferta-de-geracao-de-energia-eletrica",
        "liberacao-para-operacao-comercial-de-empreendimentos-de-geracao",
    ),
    "aneel-encargos": (
        "subsidios-tarifarios",
        "conta-desenvolvimento-energetico-cde-custeio-dos-beneficios-tarifarios",
        "compensacao-financeira-royalties",
        "cfurh",
        "tfsee",
    ),
    "aneel-fiscalizacao": (
        "fiscalizacao-economica-e-financeira",
        "auto-de-infracao",
        "indger-indicadores-gerenciais-da-distribuicao",
        "samp-balanco",
    ),
}

# id da fonte -> (ritmo, pacotes do portal do ONS, pesada)
PACOTES_DO_ONS: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "ons-demanda-maxima": (DIARIA, ("demanda_maxima_di",), False),
    "ons-hidrologia-detalhe": (
        SEMANAL,
        (
            "ear-diario-por-bacia",
            "ena-diario-por-bacia",
            "ear-diario-por-reservatorio",
            "ena-diario-por-reservatorio",
            "reservatorio",
            "dados-hidrologicos-res",
            "energia-vertida-turbinavel",
        ),
        True,
    ),
    "ons-cmo-semi-horario": (DIARIA, ("cmo-semi-horario",), True),
    "ons-disponibilidade": (
        SEMANAL,
        (
            "disponibilidade_usina",
            "ind-disponibilidade-geracao-sin",
            "taxa_teif_teip",
        ),
        True,
    ),
    "ons-itaipu": (SEMANAL, ("geracao_itaipu",), False),
    "ons-chuva-estacao": (SEMANAL, ("precipitacao-estacao",), False),
}

# id da fonte -> (ritmo, pacotes do portal da CCEE, pesada)
PACOTES_DA_CCEE: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "ccee-consumo-horario": (SEMANAL, ("consumo_horario_submercado",), True),
    "ccee-geracao-detalhe": (
        SEMANAL,
        (
            "geracao_fonte_sub_estado_mensal",
            "geracao_uhe",
            "geracao_uhe_v2",
            "eolica_geracao_acr_acl",
            "fotovoltaica_geracao_acr_acl",
            "biomassa_geracao_acr_acl_modalidade",
            "saldo_geracao_renovavel",
        ),
        False,
    ),
    "ccee-garantia-fisica": (
        MENSAL,
        (
            "garantia_fisica_lastro",
            "garantia_fisica_sazo_lastro",
            "garantia_fisica_sazo_mre_submercado",
            "garantia_fisica_sazo_submercado",
        ),
        False,
    ),
    "ccee-contratos-leilao": (
        MENSAL,
        ("contrato_montante_mensal_leilao", "energia_reserva_mensal_leilao"),
        False,
    ),
    "ccee-preco-futuro": (SEMANAL, ("pldx_valor_anual", "pld_sombra"), False),
    "ccee-risco-hidrologico": (
        MENSAL,
        (
            "fator_ajuste_gf",
            "premio_risco_hidrologico",
            "repasse_risco_hidrologico",
            "rrh_repasse",
        ),
        False,
    ),
    "ccee-liquidacao": (
        MENSAL,
        (
            "sumario_mensal_compra_venda_submercado",
            "fator_alavancagem",
            "encargo_pgto_mensal",
            "penalidade_classe_mensal",
            "penalidade_preco_mensal",
        ),
        False,
    ),
    "ccee-itaipu": (
        MENSAL,
        ("itaipu_balanco_energetico_mensal", "itaipu_resultado_mensal"),
        False,
    ),
    "ccee-mecanismos": (
        MENSAL,
        (
            "mve_resultado_geral",
            "mve_resultado_compra_venda",
            "mve_resumo_produto",
            "mcsd_resultado_mensal",
            "mcsd_montante_compensado_devolvido",
            "mcsd_montante_recebido_leilao",
            "mcsd_montante_reduzido",
            "varejista_subclasse",
            "desligamento_compulsorio",
            "desligamento_descumprimento",
            "desligamento_voluntario",
        ),
        False,
    ),
}

RAIZ_DA_ANS = "https://dadosabertos.ans.gov.br/FTP/PDA/"
ARQUIVO_NA_PASTA = re.compile(
    rb'href="([^"/?#][^"]*\.(?:csv|zip|ods|odt|pdf))"', re.IGNORECASE
)

# id da fonte -> (ritmo, pastas do FTP da ANS, pesada)
PASTAS_DA_ANS: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "ans-qualidade": (
        MENSAL,
        (
            "historico_idss-020",
            "classificacao_prudencial-056",
            "monitoramento_garantia_atendimento",
            "penalidades_aplicadas_a_operadoras",
            "regimes_especiais_direcao_tecnica",
        ),
        False,
    ),
    "ans-precos": (
        MENSAL,
        (
            "percentuais_de_reajuste_de_agrupamento-055",
            "faixa_de_preco",
            "painel_precificacao-031",
            "valor_comercial_medio_por_municipio_NTRP-054",
        ),
        True,
    ),
    "ans-glosas": (MENSAL, ("painel_de_glosas-057/dados",), False),
    "ans-ressarcimento-sus": (
        MENSAL,
        (
            "dados_ressarcimento_SUS_operadora_planos_saude",
            "ressarcimento_ao_SUS_cobranca_arrecadacao",
            "ressarcimento_ao_SUS_indice_efetivo_pagamento",
            "peona_sus",
        ),
        False,
    ),
    "ans-cobertura-e-produtos": (
        MENSAL,
        (
            "taxa_de_cobertura_de_planos_de_saude-047",
            "caracteristicas_produtos_saude_suplementar-008",
            "produtos_e_prestadores_hospitalares",
        ),
        True,
    ),
}

# membros do `BaseCompleta.zip` da SUSEP com mais de 250 MB, que as outras duas fontes da SUSEP não levam
# (só valores por seguradora, ramo e UF, sem pessoa)
MEMBROS_GRANDES_DA_SUSEP = (
    "SES_UF2.csv",
    "SES_ValoresMovRamos.csv",
    "Ses_rmovram.csv",
    "ses_valoresresmovgrupos.csv",
    "SES_Balanco.csv",
)

COMEX_TABELAS = "https://balanca.mdic.gov.br/balanca/bd/tabelas/"
TABELAS_DO_COMEX = (
    "NCM_SH",
    "NCM_CUCI",
    "NCM_ISIC",
    "NCM_CGCE",
    "NCM_UNIDADE",
    "NCM_FAT_AGREG",
    "PAIS_BLOCO",
    "UF_MUN",
    "NBM",
    "NBM_NCM",
)


def _da_pasta_da_ans(pastas: tuple[str, ...]) -> Descobrir:
    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        alvos: list[Alvo] = []
        for pasta in pastas:
            endereco = f"{RAIZ_DA_ANS}{pasta}/"
            nomes = dict.fromkeys(
                m.decode()
                for m in ARQUIVO_NA_PASTA.findall(cliente.ler(endereco).conteudo)
            )
            if not nomes:
                raise ErroDeDescoberta(f"ANS: nenhum arquivo na pasta {pasta}")
            alvos += [Alvo(urljoin(endereco, nome)) for nome in nomes]
        return alvos

    return descobrir


def descobrir_susep_grandes(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os membros grandes do ZIP do SES (o endereço guarda `zip#arquivo`)."""
    membros = set(membros_do_zip_remoto(cliente, SES_DA_SUSEP))
    if faltam := [m for m in MEMBROS_GRANDES_DA_SUSEP if m not in membros]:
        raise ErroDeDescoberta(f"SUSEP: o ZIP do SES não tem {', '.join(faltam)}")
    return [
        Alvo(
            f"{SES_DA_SUSEP}#{membro}",
            ".csv",
            extrair_do_zip_remoto(SES_DA_SUSEP, membro),
        )
        for membro in MEMBROS_GRANDES_DA_SUSEP
    ]


def descobrir_tabelas_do_comex(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [Alvo(f"{COMEX_TABELAS}{nome}.csv") for nome in TABELAS_DO_COMEX]


def fontes() -> list[Fonte]:
    """Todas as fontes do lote, para o `FONTES` do arquivista."""
    return [
        *(
            Fonte(
                id_,
                MENSAL,
                _ckan(PORTAL_DA_ANEEL, *pacotes, formatos=FORMATOS_DA_ANEEL),
            )
            for id_, pacotes in PACOTES_DA_ANEEL.items()
        ),
        *(
            Fonte(
                id_,
                ritmo,
                _ckan(PORTAL_DO_ONS, *pacotes, formatos=FORMATOS_DO_ONS),
                pesada=pesada,
            )
            for id_, (ritmo, pacotes, pesada) in PACOTES_DO_ONS.items()
        ),
        *(
            Fonte(
                id_, ritmo, _ckan_pela_pagina(PORTAL_DA_CCEE, *pacotes), pesada=pesada
            )
            for id_, (ritmo, pacotes, pesada) in PACOTES_DA_CCEE.items()
        ),
        *(
            Fonte(id_, ritmo, _da_pasta_da_ans(pastas), pesada=pesada)
            for id_, (ritmo, pastas, pesada) in PASTAS_DA_ANS.items()
        ),
        Fonte("susep-ses-grandes", MENSAL, descobrir_susep_grandes, pesada=True),
        Fonte("comexstat-tabelas", MENSAL, descobrir_tabelas_do_comex),
    ]
