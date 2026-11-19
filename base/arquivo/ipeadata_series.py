"""Séries do IPEADATA que o arquivista guarda (linha 388 da fila; amplia as 6 séries do lote acervos, linha 292).

O Ipeadata é um repositório: redistribui séries de órgãos oficiais. A lista abaixo foi escolhida do `Metadados`
do próprio Ipeadata (4.136 séries, lido em 05/11/2026) por relevância para o app (juros e crédito, câmbio,
inflação, atividade, contas públicas, setor externo e bolsa), e cada série leva a **fonte original** como o
Ipeadata a declara (`FNTSIGLA`/`FNTNOME`). Critérios (ADR 0102, ADR 0008 Emenda 4):

- só série **ativa** (`SERSTATUS = 'A'`), do Brasil, de fonte oficial: Banco Central, IBGE, Receita (SRF), MDIC
  (SECEX), B3 (só o Ibovespa) e o próprio Ipea (volatilidade do Ibovespa, calculada por ele);
- **ficam de fora** as séries de terceiros com termos que proíbem uso comercial ou privadas (FGV, Fipe, Funcex,
  Anbima, Anfavea, CNI, CNC, FMI...): o repasse pelo Ipeadata não limpa a licença (`licencas-por-fonte.md`);
- **ficam de fora** os derivativos da B3 (DI e dólar futuros): termos de redistribuição mais duros que o índice;
- sem termos publicados, a marca é `a_confirmar` (vendável citando a fonte, risco assumido): o uso cita a fonte
  original, nunca só "Ipeadata";
- nenhuma série traz pessoa física (ADR 0088).

Para somar uma série: escolha o `SERCODIGO` no `Metadados`, copie nome, periodicidade e a sigla da fonte para
`SERIES` e, se a fonte for nova, o nome por extenso para `FONTES_ORIGINAIS`. O teste confere a regra.
"""

from dataclasses import dataclass

TEMAS = {
    "juros": "juros e crédito",
    "cambio": "câmbio",
    "inflacao": "inflação",
    "atividade": "atividade",
    "fiscal": "contas públicas",
    "externo": "setor externo",
    "bolsa": "bolsa",
}


@dataclass(frozen=True)
class SerieDoIpeadata:
    """Uma série do Ipeadata: o que é, de quem veio e com que periodicidade."""

    tema: str
    nome: str
    periodicidade: str
    fonte: str  # sigla da fonte original, chave de `FONTES_ORIGINAIS`


# Observação que acompanha a série quando o dado pede cuidado.
OBSERVACOES = {
    "GM366_IBVSP366": "1995 com valores implausíveis (guardado como veio, não é série limpa)",
    "GM366_IBVSPV366": "calculada pelo Ipea, não é dado da B3",
}

# Nome por extenso de cada fonte, copiado do `FNTNOME` do `Metadados`.
FONTES_ORIGINAIS = {
    "BM&FBovespa": "Bolsa de Valores, Mercadorias e Futuros (BM&FBovespa)",
    "Bacen Outras/SGS": "Banco Central do Brasil, Sistema Gerenciador de Séries Temporais (Bacen Outras/SGS)",
    "Bacen/BP (BPM6)": "Banco Central do Brasil, Balanço de Pagamentos (BPM6) (BCB / BP (BPM6))",
    "Bacen/Boletim/Ativ. Ec.": "Banco Central do Brasil, Boletim, Seção Atividade Econômica (Bacen / Boletim / Ativ. Ec.)",
    "Bacen/Boletim/BP": "Banco Central do Brasil, Boletim, Seção Balanço de Pagamentos (Bacen / Boletim / BP)",
    "Bacen/Boletim/M. Finan.": "Banco Central do Brasil, Boletim, Seção mercado financeiro e de capitais (Bacen/Boletim/M. Finan.)",
    "Bacen/Notas Imprensa/F. Púb.": "Banco Central do Brasil, Notas Econômico-financeiras para a Imprensa, Finanças Públicas (Bacen/Notas Imprensa/F. Púb)",
    "Bacen/Notas Imprensa/Moeda": "Banco Central do Brasil, Notas Econômico-financeiras para a Imprensa, Política Monetária e Operações de Crédito do SFN (Bacen/Notas Imprensa/Moeda)",
    "Bacen/Notas Imprensa/Set. Ext.": "Banco Central do Brasil, Notas Econômico-financeiras para a Imprensa, Setor Externo (Bacen/Notas Imprensa/Set. Ext)",
    "IBGE/IPP": "Instituto Brasileiro de Geografia e Estatística, Índice de Preços ao Produtor (IBGE/IPP)",
    "IBGE/PIM-PF": "Instituto Brasileiro de Geografia e Estatística, Pesquisa Industrial Mensal - Produção Física (IBGE/PIM-PF)",
    "IBGE/PMC": "Instituto Brasileiro de Geografia e Estatística, Pesquisa Mensal de Comércio (IBGE/PMC)",
    "IBGE/PMS": "Instituto Brasileiro de Geografia e Estatística, Pesquisa Mensal de Serviços (IBGE/PMS)",
    "IBGE/PNAD Contínua": "Instituto Brasileiro de Geografia e Estatística, Pesquisa Nacional por Amostra de Domicílios Contínua (IBGE/PNAD Contínua)",
    "IBGE/SCN Trim.": "Instituto Brasileiro de Geografia e Estatística, Sistema de Contas Nacionais Trimestrais (IBGE/SCN Trimestral)",
    "IBGE/SNIPC": "Instituto Brasileiro de Geografia e Estatística, Sistema Nacional de Índices de Preços ao Consumidor (IBGE/SNIPC)",
    "IPEA": "Instituto de Pesquisa Econômica Aplicada",
    "MDIC/SECEX": "Ministério do Desenvolvimento, Indústria e Comércio Exterior-Secretaria de Comércio Exterior",
    "Min. Economia/SRF": "Ministério da Economia, Secretaria da Receita Federal (Min. Economia/SRF)",
}

SERIES: dict[str, SerieDoIpeadata] = {
    # --- juros e crédito ---
    "BM366_TJOVER366": SerieDoIpeadata(
        "juros",
        "Taxa de juros - Selic - fixada pelo Copom",
        "diária",
        "Bacen/Boletim/M. Finan.",
    ),
    "GM366_TJOVER366": SerieDoIpeadata(
        "juros", "Taxa de juros - Over / Selic", "diária", "Bacen Outras/SGS"
    ),
    "BM12_TJOVER12": SerieDoIpeadata(
        "juros",
        "Taxa de juros - Over / Selic - acumulada no mês",
        "mensal",
        "Bacen/Boletim/M. Finan.",
    ),
    "SGS366_CDI366": SerieDoIpeadata(
        "juros", "Taxa de juros - CDI", "diária", "Bacen Outras/SGS"
    ),
    "BM12_TJCDI12": SerieDoIpeadata(
        "juros",
        "Taxa de juros - CDI / Over - acumulada no mês",
        "mensal",
        "Bacen/Boletim/M. Finan.",
    ),
    "BM12_TJLP12": SerieDoIpeadata(
        "juros", "Taxa de juros - TJLP", "mensal", "Bacen/Boletim/M. Finan."
    ),
    "BM12_TJTR12": SerieDoIpeadata(
        "juros",
        "Taxa de juros - TR - primeiro dia do mês",
        "mensal",
        "Bacen/Boletim/M. Finan.",
    ),
    "GM366_TJTR366": SerieDoIpeadata(
        "juros", "Taxa de juros - TR", "diária", "Bacen Outras/SGS"
    ),
    "BM12_RNDPO12": SerieDoIpeadata(
        "juros",
        "Poupança - rentabilidade - depósitos a partir de 04.05.2012 (1º dia do mês)",
        "mensal",
        "Bacen/Boletim/M. Finan.",
    ),
    "BM12_CTJ12": SerieDoIpeadata(
        "juros",
        "Operações de crédito - taxa média de juros - total",
        "mensal",
        "Bacen/Notas Imprensa/Moeda",
    ),
    "BM12_CTJPF12": SerieDoIpeadata(
        "juros",
        "Operações de crédito - taxa média de juros - pessoa física",
        "mensal",
        "Bacen/Notas Imprensa/Moeda",
    ),
    "BM12_CTJPJ12": SerieDoIpeadata(
        "juros",
        "Operações de crédito - taxa média de juros - pessoa jurídica",
        "mensal",
        "Bacen/Notas Imprensa/Moeda",
    ),
    "BM12_CRLTJ12": SerieDoIpeadata(
        "juros",
        "Operações de crédito - taxa média de juros - recursos livres - total",
        "mensal",
        "Bacen/Notas Imprensa/Moeda",
    ),
    "BM12_CRDTJ12": SerieDoIpeadata(
        "juros",
        "Operações de crédito - taxa média de juros - recursos direcionados - total",
        "mensal",
        "Bacen/Notas Imprensa/Moeda",
    ),
    "BM12_CSD12": SerieDoIpeadata(
        "juros",
        "Operações de crédito - spread médio das operações - total",
        "mensal",
        "Bacen/Notas Imprensa/Moeda",
    ),
    "BM12_CIN12": SerieDoIpeadata(
        "juros",
        "Operações de crédito - inadimplência da carteira de crédito - total",
        "mensal",
        "Bacen/Notas Imprensa/Moeda",
    ),
    "BM12_CINPF12": SerieDoIpeadata(
        "juros",
        "Operações de crédito - inadimplência da carteira de crédito - pessoa física",
        "mensal",
        "Bacen/Notas Imprensa/Moeda",
    ),
    "BM12_CINPJ12": SerieDoIpeadata(
        "juros",
        "Operações de crédito - inadimplência da carteira de crédito - pessoa Jurídica",
        "mensal",
        "Bacen/Notas Imprensa/Moeda",
    ),
    "BM12_CS12": SerieDoIpeadata(
        "juros",
        "Operações de crédito - saldo da carteira de crédito - total",
        "mensal",
        "Bacen/Notas Imprensa/Moeda",
    ),
    "BM12_CCA12": SerieDoIpeadata(
        "juros",
        "Operações de crédito - concessões - total",
        "mensal",
        "Bacen/Notas Imprensa/Moeda",
    ),
    "BM12_M2NCN12": SerieDoIpeadata(
        "juros",
        "Meio de pagamento ampliado - M2 - fim de período",
        "mensal",
        "Bacen/Notas Imprensa/Moeda",
    ),
    "BM12_M4NCN12": SerieDoIpeadata(
        "juros",
        "Meio de pagamento ampliado - M4 - fim de período",
        "mensal",
        "Bacen/Notas Imprensa/Moeda",
    ),
    # --- câmbio ---
    "GM366_ERV366": SerieDoIpeadata(
        "cambio",
        "Taxa de câmbio dólar comercial para venda - média",
        "diária",
        "Bacen Outras/SGS",
    ),
    "GM366_ERC366": SerieDoIpeadata(
        "cambio",
        "Taxa de câmbio dólar comercial para compra - média",
        "diária",
        "Bacen Outras/SGS",
    ),
    "BM12_ERV12": SerieDoIpeadata(
        "cambio",
        "Taxa de câmbio - R$ / US$ - comercial - venda - média",
        "mensal",
        "Bacen/Boletim/BP",
    ),
    "GM366_EUROV366": SerieDoIpeadata(
        "cambio",
        "Zona do Euro - taxa de câmbio - R$ / euro - venda - média",
        "diária",
        "Bacen Outras/SGS",
    ),
    "GM366_EREURO366": SerieDoIpeadata(
        "cambio",
        "Zona do Euro - taxa de câmbio - EUR por US$ - média",
        "diária",
        "Bacen Outras/SGS",
    ),
    "BM12_RES12": SerieDoIpeadata(
        "cambio", "Reservas internacionais", "mensal", "Bacen/Notas Imprensa/Set. Ext."
    ),
    # --- inflação ---
    "PRECOS12_IPCA12": SerieDoIpeadata(
        "inflacao", "IPCA - geral - índice (dez. 1993 = 100)", "mensal", "IBGE/SNIPC"
    ),
    "PRECOS12_INPC12": SerieDoIpeadata(
        "inflacao", "INPC - geral - índice (dez. 1993 = 100)", "mensal", "IBGE/SNIPC"
    ),
    "PRECOS12_IPCAG12": SerieDoIpeadata(
        "inflacao", "IPCA - geral - taxa de variação", "mensal", "IBGE/SNIPC"
    ),
    "PRECOS12_IPCAGA12": SerieDoIpeadata(
        "inflacao", "IPCA - geral - taxa de variação (12 meses)", "mensal", "IBGE/SNIPC"
    ),
    "PRECOS12_IPCA15G12": SerieDoIpeadata(
        "inflacao", "IPCA - 15 - taxa de variação", "mensal", "IBGE/SNIPC"
    ),
    "PRECOS12_INPCBR12": SerieDoIpeadata(
        "inflacao", "INPC - geral - taxa de variação", "mensal", "IBGE/SNIPC"
    ),
    "PRECOS12_IPCAAB12": SerieDoIpeadata(
        "inflacao",
        "IPCA - alimentos e bebidas - taxa de variação",
        "mensal",
        "IBGE/SNIPC",
    ),
    "PRECOS12_IPCAHA12": SerieDoIpeadata(
        "inflacao", "IPCA - habitação - taxa de variação", "mensal", "IBGE/SNIPC"
    ),
    "PRECOS12_IPCATC12": SerieDoIpeadata(
        "inflacao", "IPCA - transportes - taxa de variação", "mensal", "IBGE/SNIPC"
    ),
    "BM12_IPCA2012": SerieDoIpeadata(
        "inflacao",
        "IPCA - núcleo médias aparadas com suavização - taxa de variação",
        "mensal",
        "Bacen/Boletim/Ativ. Ec.",
    ),
    "BM12_IPCA20N12": SerieDoIpeadata(
        "inflacao",
        "IPCA - núcleo médias aparadas sem suavização - taxa de variação",
        "mensal",
        "Bacen/Boletim/Ativ. Ec.",
    ),
    "BM12_NUCLEOPIPCA12": SerieDoIpeadata(
        "inflacao",
        "Núcleo de dupla ponderação - IPCA",
        "mensal",
        "Bacen/Boletim/Ativ. Ec.",
    ),
    "BM12_IPCAPL12": SerieDoIpeadata(
        "inflacao",
        "IPCA - preços livres - taxa de variação",
        "mensal",
        "Bacen/Boletim/Ativ. Ec.",
    ),
    "BM12_IPCAPM12": SerieDoIpeadata(
        "inflacao",
        "IPCA - preços monitorados - taxa de variação",
        "mensal",
        "Bacen/Boletim/Ativ. Ec.",
    ),
    "BM12_IPCAPLSER12": SerieDoIpeadata(
        "inflacao",
        "IPCA - preços livres - serviços - taxa de variação",
        "mensal",
        "Bacen/Boletim/Ativ. Ec.",
    ),
    "BM12_IPCAEXP1212": SerieDoIpeadata(
        "inflacao",
        "Expectativa média de Inflação - IPCA - taxa acumulada para os próximos doze meses",
        "mensal",
        "Bacen/Boletim/Ativ. Ec.",
    ),
    "IPP12_IPPCIG12": SerieDoIpeadata(
        "inflacao",
        "IPP - indústria geral - índice (dez. 2018 = 100)",
        "mensal",
        "IBGE/IPP",
    ),
    "IPP12_IPPCG12": SerieDoIpeadata(
        "inflacao", "IPP - indústrias de transformação", "mensal", "IBGE/IPP"
    ),
    # --- atividade ---
    "SGS12_IBCBR12": SerieDoIpeadata(
        "atividade", "IBC-Br - índice real (2022=100)", "mensal", "Bacen Outras/SGS"
    ),
    "SGS12_IBCBRDESSAZ12": SerieDoIpeadata(
        "atividade",
        "IBC-Br - índice real dessazonalizado (2022=100)",
        "mensal",
        "Bacen Outras/SGS",
    ),
    "SCN104_PIBPMG104": SerieDoIpeadata(
        "atividade",
        "PIB - preços de mercado - variação real trimestral sobre mesmo trimestre do ano anterior",
        "trimestral",
        "IBGE/SCN Trim.",
    ),
    "SCN104_PIBPMAS104": SerieDoIpeadata(
        "atividade",
        "PIB - preços de mercado - índice real encadeado dessazonalizado (média 1995 = 100)",
        "trimestral",
        "IBGE/SCN Trim.",
    ),
    "SCN104_PIBPMV104": SerieDoIpeadata(
        "atividade", "PIB - preços de mercado", "trimestral", "IBGE/SCN Trim."
    ),
    "SCN104_PIBINDG104": SerieDoIpeadata(
        "atividade",
        "PIB - indústria - variação real trimestral sobre mesmo trimestre do ano anterior",
        "trimestral",
        "IBGE/SCN Trim.",
    ),
    "SCN104_PIBAGPG104": SerieDoIpeadata(
        "atividade",
        "PIB - agropecuária - variação real trimestral sobre mesmo trimestre do ano anterior",
        "trimestral",
        "IBGE/SCN Trim.",
    ),
    "SCN104_CFPPG104": SerieDoIpeadata(
        "atividade",
        "PIB - consumo final - famílias - variação real trimestral sobre mesmo trimestre do ano anterior",
        "trimestral",
        "IBGE/SCN Trim.",
    ),
    "SCN104_FBKFG104": SerieDoIpeadata(
        "atividade",
        "PIB - formação bruta de capital fixo - variação real trimestral sobre mesmo trimestre do ano anterior",
        "trimestral",
        "IBGE/SCN Trim.",
    ),
    "BM12_PIB12": SerieDoIpeadata(
        "atividade", "PIB", "mensal", "Bacen/Boletim/Ativ. Ec."
    ),
    "BM12_PIBAC12": SerieDoIpeadata(
        "atividade", "PIB - acumulado em 12 meses", "mensal", "Bacen Outras/SGS"
    ),
    "PIMPFN12_QIIGNN12": SerieDoIpeadata(
        "atividade",
        "Produção industrial - indústria geral - quantum - índice (média 2022 = 100)",
        "mensal",
        "IBGE/PIM-PF",
    ),
    "PIMPFN12_QIIGSNNAS12": SerieDoIpeadata(
        "atividade",
        "Produção industrial - indústria geral - quantum - índice dessazonalizado (média 2022 = 100)",
        "mensal",
        "IBGE/PIM-PF",
    ),
    "PIMPFN12_QIITNN12": SerieDoIpeadata(
        "atividade",
        "Produção industrial - indústrias de transformação - quantum - índice (média 2022 = 100)",
        "mensal",
        "IBGE/PIM-PF",
    ),
    "PIMPFN12_QIEMNN12": SerieDoIpeadata(
        "atividade",
        "Produção industrial - indústrias extrativas - quantum - índice (média 2022 = 100)",
        "mensal",
        "IBGE/PIM-PF",
    ),
    "PIMPFN12_QIBKNN12": SerieDoIpeadata(
        "atividade",
        "Produção industrial - bens de capital - quantum - índice (média 2022 = 100)",
        "mensal",
        "IBGE/PIM-PF",
    ),
    "PIMPFN12_QIBCTNN12": SerieDoIpeadata(
        "atividade",
        "Produção industrial - bens de consumo - quantum - índice (média 2022 = 100)",
        "mensal",
        "IBGE/PIM-PF",
    ),
    "PIMPFN12_QIBINN12": SerieDoIpeadata(
        "atividade",
        "Produção industrial - bens intermediários - quantum - índice (média 2022 = 100)",
        "mensal",
        "IBGE/PIM-PF",
    ),
    "PMC12_IVVRN12": SerieDoIpeadata(
        "atividade",
        "Vendas reais - varejo - índice (média 2022 = 100)",
        "mensal",
        "IBGE/PMC",
    ),
    "PMC12_IVVRNSA12": SerieDoIpeadata(
        "atividade",
        "Vendas reais - varejo - índice dessazonalizado (média 2022 = 100)",
        "mensal",
        "IBGE/PMC",
    ),
    "PMC12_IVVRNSAAMP12": SerieDoIpeadata(
        "atividade",
        "Vendas reais - varejo ampliado - índice dessazonalizado (média 2022 = 100)",
        "mensal",
        "IBGE/PMC",
    ),
    "PMS12_RRSSA12": SerieDoIpeadata(
        "atividade",
        "Receita real - serviços - índice dessazonalizado (média 2022 = 100)",
        "mensal",
        "IBGE/PMS",
    ),
    "PNADC12_TDESOC12": SerieDoIpeadata(
        "atividade", "Taxa de desemprego (desocupação)", "mensal", "IBGE/PNAD Contínua"
    ),
    "SRF12_TOTGER12": SerieDoIpeadata(
        "atividade",
        "Arrecadação das receitas federais - receita bruta",
        "mensal",
        "Min. Economia/SRF",
    ),
    "SRF12_IRPJ12": SerieDoIpeadata(
        "atividade",
        "Imposto sobre a renda (IR) - pessoas jurídicas - total - receita bruta",
        "mensal",
        "Min. Economia/SRF",
    ),
    "SRF12_CSLL12": SerieDoIpeadata(
        "atividade",
        "Contribuição social sobre o lucro líquido (CSLL) - total - receita bruta",
        "mensal",
        "Min. Economia/SRF",
    ),
    "SRF12_COFINS12": SerieDoIpeadata(
        "atividade",
        "Contribuição - Finsocial / Cofins - total - receita bruta",
        "mensal",
        "Min. Economia/SRF",
    ),
    # --- contas públicas ---
    "BM12_DTSPY12": SerieDoIpeadata(
        "fiscal",
        "DSLP - total - setor público não-financeiro",
        "mensal",
        "Bacen/Notas Imprensa/F. Púb.",
    ),
    "BM12_DTSPN12": SerieDoIpeadata(
        "fiscal",
        "DSLP - total - setor público não-financeiro",
        "mensal",
        "Bacen/Notas Imprensa/F. Púb.",
    ),
    "BM12_DTGFY12": SerieDoIpeadata(
        "fiscal",
        "DSLP - total - governo federal e Banco Central",
        "mensal",
        "Bacen/Notas Imprensa/F. Púb.",
    ),
    "BM12_NFSPPYS12": SerieDoIpeadata(
        "fiscal",
        "NFSP - setor público - resultado primário - sem desvalorização cambial - fluxo acumulado em 12 meses",
        "mensal",
        "Bacen/Notas Imprensa/F. Púb.",
    ),
    "BM12_NFSPNYS12": SerieDoIpeadata(
        "fiscal",
        "NFSP - setor público - resultado nominal - sem desvalorização cambial - fluxo acumulado em 12 meses",
        "mensal",
        "Bacen/Notas Imprensa/F. Púb.",
    ),
    "BM12_NFSPJNYS12": SerieDoIpeadata(
        "fiscal",
        "NFSP - setor público - juros nominais - sem desvalorização cambial - fluxo acumulado em 12meses",
        "mensal",
        "Bacen/Notas Imprensa/F. Púb.",
    ),
    "BM12_DIFISPY12": SerieDoIpeadata(
        "fiscal",
        "DLSP - Dívida Fiscal Líquida - fim de período",
        "mensal",
        "Bacen/Notas Imprensa/F. Púb.",
    ),
    # --- setor externo ---
    "BPAG12_TC12": SerieDoIpeadata(
        "externo",
        "Balanço de pagamentos - transações correntes - saldo",
        "mensal",
        "Bacen/BP (BPM6)",
    ),
    "BPAG12_TCPIB12": SerieDoIpeadata(
        "externo",
        "Balanço de pagamentos - transações correntes",
        "mensal",
        "Bacen/BP (BPM6)",
    ),
    "BPAG12_BC12": SerieDoIpeadata(
        "externo",
        "Balanço de pagamentos - balança comercial - saldo",
        "mensal",
        "Bacen/BP (BPM6)",
    ),
    "SECEX12_XVTOT12": SerieDoIpeadata(
        "externo", "Exportações - (FOB) - SECEX", "mensal", "MDIC/SECEX"
    ),
    "SECEX12_MVTOT12": SerieDoIpeadata(
        "externo", "Importações - (FOB) - SECEX", "mensal", "MDIC/SECEX"
    ),
    "SECEX12_XCOBLUBGCE12": SerieDoIpeadata(
        "externo",
        "Exportações - combustíveis e lubrificantes - (FOB) - SECEX",
        "mensal",
        "MDIC/SECEX",
    ),
    "SECEX12_MCOBLUBGCE12": SerieDoIpeadata(
        "externo",
        "Importações - combustíveis e lubrificantes - (FOB) - SECEX",
        "mensal",
        "MDIC/SECEX",
    ),
    # --- bolsa ---
    "GM366_IBVSP366": SerieDoIpeadata(
        "bolsa", "Índice de ações - Ibovespa - fechamento", "diária", "BM&FBovespa"
    ),
    "GM366_IBVSPV366": SerieDoIpeadata(
        "bolsa",
        "Índice de ações - Ibovespa - fechamento - volatilidade",
        "diária",
        "IPEA",
    ),
}


def descricao(codigo: str) -> str:
    """Texto de uma série para o arquivo e para a tela: nome, periodicidade, fonte original e observação."""
    serie = SERIES[codigo]
    texto = f"{serie.nome} ({serie.periodicidade}; fonte original: {serie.fonte})"
    if codigo in OBSERVACOES:
        texto += f"; {OBSERVACOES[codigo]}"
    return texto
