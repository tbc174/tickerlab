# Dicionário de dados da base de ML

Gerado por `python -m base.dicionario` a partir de `base/dicionario.py` (não edite à mão).
Exigência 8 do critério de pronto da base (ADR 0027 do autor): para cada tabela, unidade,
frequência, atraso de divulgação, fonte e licença. Exigências 11 e 13 (ADR 0055): se pode
ser revendida (não é parecer jurídico) e a linhagem até o arquivo original.

## `demonstracoes_como_era`

Uma linha por valor diferente que cada conta de cada período já teve (versão 1, reapresentações e o balanço seguinte refazendo o ano anterior), com o dia em que ficou público e o dia em que foi trocado. `como_era_em(base, data)` dá a foto.

- **Fonte:** CVM: dados abertos de DFP e ITR (versão mais nova) e ENET (versões anteriores, XML de cada entrega)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária no servidor de casa (carga do ENET às 0h30); a base é remontada por ano
- **Atraso de divulgação:** DFP: até 3 meses depois do fim do exercício; ITR: até 45 dias depois do trimestre (prazos da CVM, `src/prazos.py`); reapresentações a qualquer momento
- **Onde fica:** Parquet por ano em `<acervo>/base/demonstracoes/<ano>.parquet` (servidor de casa)
- **Linhagem:** `cnpj`, `documento`, `referencia` e `versao` dizem qual entrega à CVM publicou o valor; `origem` diz se veio dos dados abertos ou do XML do ENET. Ao lado de cada Parquet, `<ano>.json` guarda o SHA-256 da base e o endereço e o SHA-256 de cada original, que está no acervo e no registro de coletas (com a data da coleta). A versão do código que processou a linha ainda não é guardada.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `grupo` | con (consolidado) ou ind (individual) | texto |
| `demonstracao` | BPA (ativo), BPP (passivo e patrimônio) ou DRE (resultado) | texto |
| `conta` | Código da conta no plano da CVM (1, 1.01, 3.01...) | texto |
| `descricao` | Nome da conta como a empresa informou | texto |
| `inicio` | Começo do período (vazio no balanço, que é um saldo numa data) | data (dia) |
| `fim` | Fim do período ou data do saldo | data (dia) |
| `valor` | Valor da conta; vazio quando a empresa deixou em branco | reais (R$), já multiplicado pela escala informada |
| `documento` | DFP (demonstrações anuais) ou ITR (informações trimestrais) | texto |
| `referencia` | Data a que o documento se refere (fim do exercício ou do trimestre) | data (dia) |
| `versao` | Versão do documento que publicou este valor (1, 2, 3...) | número |
| `ordem` | ultimo (período do próprio documento) ou penultimo (o ano anterior, refeito) | texto |
| `origem` | dados_abertos ou enet | texto |
| `divulgado_em` | Dia da entrega à CVM (vale a partir dele, inclusive; a CVM não informa a hora) | data (dia) |
| `ate` | Dia em que outro valor tomou o lugar (vazio: vale até hoje) | data (dia) |

## `achados_de_qualidade`

Os achados das regras fixas do selo "dado em conferência" (R1 a R11, `base/regras.py`): o número que chamou a atenção, o esperado e o porquê. Achado que some é fechado, nunca apagado.

- **Fonte:** CVM: dados abertos de DFP e ITR, cadastro e eventos do IPE
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária no VPS (tarefa `qualidade-cvm` às 8h15)
- **Atraso de divulgação:** O do documento conferido; `valido_desde` diz desde quando o achado existe
- **Onde fica:** Tabela `achados_de_qualidade` do banco do app (VPS), migração 0026
- **Linhagem:** `cnpj`, `documento` e `referencia` levam ao arquivo de DFP ou ITR da CVM, guardado no acervo e no registro de coletas (fonte `cvm-dfp-itr`, com SHA-256 e data da coleta); `versao_das_regras` e `calculado_em` dizem com que regras e quando o achado foi calculado.

| Coluna | O que é | Unidade |
|---|---|---|
| `id` | Identificador da linha | UUID |
| `regra` | Regra que apontou (R1 a R11) | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `documento` | DFP (demonstrações anuais) ou ITR (informações trimestrais) | texto |
| `referencia` | Data a que o documento se refere (fim do exercício ou do trimestre) | data (dia) |
| `grupo` | con, ind ou vazio (regras que olham o documento inteiro) | texto |
| `conta` | Conta apontada, ou vazio | texto |
| `valor` | O número publicado (na R8, os dias de atraso) | reais ou dias |
| `valor_esperado` | O que a regra esperava encontrar | reais ou dias |
| `porque` | Frase em português que o selo mostra | texto |
| `versao_das_regras` | Versão das regras que calculou | texto |
| `valido_desde` | Desde quando a informação existia (a entrega do documento) | data e hora (UTC) |
| `calculado_em` | Quando a tarefa gravou ou atualizou o achado | data e hora (UTC) |
| `fechado_em` | Quando o achado sumiu numa rodada nova (vazio: aberto) | data e hora (UTC) |

## `cadastro_das_companhias`

Cada registro de companhia aberta na CVM, inclusive as que saíram, com a data e o motivo (sem viés de sobrevivência, ADR 0027, exigência 4)

- **Fonte:** CVM: cadastro de companhias abertas (`cad_cia_aberta.csv`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária (a CVM atualiza o arquivo todo dia útil)
- **Atraso de divulgação:** Dias, entre o ato (registro ou cancelamento) e a publicação
- **Onde fica:** Lido do acervo quando preciso (`base/cadastro.py::ler_cadastro`)
- **Linhagem:** O `cad_cia_aberta.csv` de cada dia fica no acervo e no registro de coletas (com SHA-256 e data da coleta); a tabela é refeita dele. A versão do código que processou a linha ainda não é guardada.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `registro` | Data do registro na CVM | data (dia) |
| `cancelamento` | Data do cancelamento (vazio: ativa) | data (dia) |
| `motivo_cancelamento` | Motivo informado pela CVM (voluntário, de ofício...) | texto |
| `situacao` | Situação do registro (ATIVO, CANCELADA...) | texto |
| `setor` | Setor de atividade informado à CVM | texto |

## `tickers_no_tempo`

Cada código de ação da B3 (bolsa) com a empresa e o período em que existiu, juntando todos os anos do formulário cadastral (FCA): código que sumiu continua aqui

- **Fonte:** CVM: formulário cadastral (FCA), valores mobiliários
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual (o FCA é entregue até 31/05) e a cada alteração
- **Atraso de divulgação:** Até meses: a empresa atualiza o FCA quando muda algo
- **Onde fica:** Lido do acervo quando preciso (`base/cadastro.py::tickers_no_tempo`)
- **Linhagem:** Montada dos zips do FCA de todos os anos, guardados no acervo e no registro de coletas (com SHA-256 e data da coleta); `primeiro_visto` e `ultimo_visto` dizem de qual FCA veio cada código. A versão do código que processou a linha ainda não é guardada.

| Coluna | O que é | Unidade |
|---|---|---|
| `codigo` | Código de negociação na B3 (PETR4, TAEE11) | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `valor_mobiliario` | Tipo do papel (ações ordinárias, preferenciais, units) | texto |
| `primeiro_visto` | Data do primeiro FCA em que o código apareceu | data (dia) |
| `ultimo_visto` | Data do último FCA em que o código apareceu | data (dia) |
| `inicio_negociacao` | Início da negociação informado pela empresa | data (dia) |
| `fim_negociacao` | Fim da negociação informado (vazio: ainda negociado) | data (dia) |

## `padroes_setoriais`

Os padrões por setor das notas (ADR 0033): os percentis de cada indicador entre as empresas de cada grupo de setores (`src/setores.py`), calculados só com os balanços que eram públicos na data de corte. Dado derivado: recalcular o mesmo corte substitui as linhas dele.

- **Fonte:** Calculado pelo TickerLab das demonstrações da CVM (DFP e ITR, versões do Radar); nos múltiplos, também o preço da ação (Yahoo Finance)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Ressalva de revenda:** As linhas dos múltiplos (`p_l`, `p_vp`) usam o preço do Yahoo Finance: só uso interno (nunca vender nem exportar).
- **Frequência:** Um corte por fim de mês; o cron do VPS roda todo dia às 8h30 e só grava o corte que falta (`scripts/atualizar_padroes.py --so-o-que-falta`)
- **Atraso de divulgação:** O do balanço mais novo de cada empresa até o corte (DFP até 3 meses, ITR até 45 dias)
- **Onde fica:** Tabela `padroes_setoriais` do banco do app (VPS), migração 0028
- **Linhagem:** `data_de_corte` e `versao` (o método, `src/padroes.py::VERSAO_DOS_PADROES`) bastam para refazer a linha: `python -m scripts.atualizar_padroes --datas <corte>` lê as versões dos documentos entregues até o corte (`demonstracoes_versoes`), que levam aos originais do acervo; `calculado_em` diz quando foi gravada. As empresas de cada percentil não ficam guardadas, só a quantidade.

| Coluna | O que é | Unidade |
|---|---|---|
| `data_de_corte` | Data de corte: entra só o que era público até ela (fim de cada mês) | data (dia) |
| `grupo` | Grupo de setores (`src/setores.py`) ou `mercado` (todas as não financeiras) | texto |
| `indicador` | Indicador (`src/padroes.py::INDICADORES`) ou múltiplo de preço | texto |
| `versao` | Versão do método (`VERSAO_DOS_PADROES`) | texto |
| `empresas` | Quantas empresas do grupo tinham o indicador no corte | número |
| `percentis` | Os percentis 10 a 90 do indicador no grupo ({"50": 0.08, ...}) | a do indicador (fração, vezes ou dias) |
| `calculado_em` | Quando a tarefa gravou a linha | data e hora (UTC) |

## `fre_proventos`

Dividendos e juros sobre capital próprio de cada exercício, como a empresa informou no Formulário de Referência (FRE). O mesmo exercício aparece no FRE de vários anos: fica o documento mais novo.

- **Fonte:** CVM: dados abertos do Formulário de Referência (FRE), tabela de distribuição
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Carga de uma vez (FRE de 2010 a 2022): a CVM tirou estas tabelas do FRE aberto depois de 2022 (Resolução CVM 59)
- **Atraso de divulgação:** O FRE é entregue até 5 meses depois do fim do exercício e reapresentado a cada mudança
- **Onde fica:** Tabela `fre_proventos` do banco do app (VPS), migração 0029
- **Linhagem:** `referencia` e `versao` dizem de qual FRE veio a linha; o zip do ano fica no acervo e no registro de coletas (fonte `cvm-fre`, com SHA-256 e data da coleta); `coletado_em` diz quando a linha foi gravada. A versão do código que processou a linha ainda não é guardada.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `exercicio` | Fim do exercício social | data (dia) |
| `referencia` | Data de referência do FRE de onde a linha veio | data (dia) |
| `versao` | Versão desse FRE (1, 2, 3...) | número |
| `lucro_ajustado` | Lucro líquido ajustado, base da distribuição | reais (R$), já multiplicado pela escala informada |
| `dividendo_total` | Total distribuído (dividendos e JCP) | reais (R$), já multiplicado pela escala informada |
| `payout` | Parte do lucro ajustado distribuída | fração (0,25 = 25%) |
| `dividendos` | Dividendos declarados | reais (R$), já multiplicado pela escala informada |
| `jcp` | Juros sobre capital próprio declarados | reais (R$), já multiplicado pela escala informada |
| `coletado_em` | Quando a carga gravou a linha | data e hora (UTC) |

## `fre_eventos_de_capital`

Desdobramentos, grupamentos, bonificações e aumentos de capital informados no FRE, para ajustar a quantidade de ações (sem confundir desdobramento com diluição)

- **Fonte:** CVM: dados abertos do Formulário de Referência (FRE), tabelas de desdobramentos, grupamentos, bonificações e aumentos de capital
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Carga de uma vez (FRE de 2010 a 2022): a CVM tirou estas tabelas do FRE aberto depois de 2022 (Resolução CVM 59)
- **Atraso de divulgação:** O FRE é entregue até 5 meses depois do fim do exercício e reapresentado a cada mudança
- **Onde fica:** Tabela `fre_eventos_de_capital` do banco do app (VPS), migração 0029
- **Linhagem:** `referencia` e `versao` dizem de qual FRE veio a linha; o zip do ano fica no acervo e no registro de coletas (fonte `cvm-fre`, com SHA-256 e data da coleta); `coletado_em` diz quando a linha foi gravada. A versão do código que processou a linha ainda não é guardada.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `tipo` | desdobramento, grupamento, bonificação ou aumento | texto |
| `data` | Data da aprovação ou da deliberação | data (dia) |
| `quantidade` | Ações depois do evento (no aumento, as ações novas) | ações |
| `referencia` | Data de referência do FRE de onde a linha veio | data (dia) |
| `versao` | Versão desse FRE (1, 2, 3...) | número |
| `acoes_antes` | Ações antes do evento | ações |
| `acoes_depois` | Ações depois do evento | ações |
| `fator` | Depois ÷ antes (desdobramento de 1 para 10 = 10) | vezes |
| `acoes_novas` | Ações emitidas no aumento de capital | ações |
| `valor` | Valor do aumento de capital | reais (R$), já multiplicado pela escala informada |
| `coletado_em` | Quando a carga gravou a linha | data e hora (UTC) |
