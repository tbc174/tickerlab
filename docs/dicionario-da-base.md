# Dicionário de dados da base de ML

Gerado por `python -m base.dicionario` a partir de `base/dicionario.py` (não edite à mão).
Exigência 8 do critério de pronto da base (ADR 0027 do autor): para cada tabela, unidade,
frequência, atraso de divulgação, fonte e licença. Exigências 11 e 13 (ADR 0055): se pode
ser revendida (não é parecer jurídico) e a linhagem até o arquivo original.

## `demonstracoes_como_era`

Uma linha por valor diferente que cada conta de cada período já teve (versão 1, reapresentações e o balanço seguinte refazendo o ano anterior), com o dia em que ficou público e o dia em que foi trocado. `como_era_em(base, data)` dá a foto. **Sem pessoa pela raiz:** toda raiz de CNPJ desta tabela existe na `cnpj_empresas_pj`, que só tem pessoa jurídica; CNPJ que não tem 14 dígitos conta como fora. A prova cobre quem a linha descreve, não o texto livre que ela carrega (o assunto de um evento, por exemplo). A conferência é `scripts/conferir_sem_pessoa.py`, rodada antes de cada concessão do piloto

- **Fonte:** CVM: dados abertos de DFP e ITR (versão mais nova) e ENET (versões anteriores, XML de cada entrega)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária no servidor de casa (carga do ENET às 0h30); a base é remontada por ano
- **Atraso de divulgação:** DFP: até 3 meses depois do fim do exercício; ITR: até 45 dias depois do trimestre (prazos da CVM, `src/prazos.py`); reapresentações a qualquer momento
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `documento`, `referencia`, `versao`, `demonstracao`, `grupo`, `conta`, `ordem`, `inicio`, `fim`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `divulgado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 3.0.0
- **Onde fica:** Parquet por ano em `<acervo>/base/demonstracoes/<ano>.parquet` (servidor de casa)
- **Linhagem:** `cnpj`, `documento`, `referencia` e `versao` dizem qual entrega à CVM publicou o valor; `origem` diz se veio dos dados abertos ou do XML do ENET. Ao lado de cada Parquet, `<ano>.json` guarda o SHA-256 da base e o endereço e o SHA-256 de cada original, que está no acervo e no registro de coletas (com a data da coleta), e a `versao_do_codigo` (o commit que montou o ano; os anos montados antes da série 3 ficam sem ela até serem remontados). `base/linhagem.py` refaz o caminho de qualquer linha e diz se está completo.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `grupo` | con (consolidado) ou ind (individual) | texto |
| `demonstracao` | BPA (ativo), BPP (passivo e patrimônio), DRE (resultado, só o primeiro nível), DRA (resultado abrangente), DFC_MI ou DFC_MD (fluxo de caixa pelo método indireto ou direto) ou DVA (valor adicionado); as quatro últimas inteiras, desde a série T1 (contrato 2.0.0). A DMPL fica em `dmpl_como_era` | texto |
| `conta` | Código da conta no plano da CVM (1, 1.01, 3.01, 6.01, 7.04.01...) | texto |
| `descricao` | Nome da conta como a empresa informou | texto |
| `inicio` | Começo do período (vazio no balanço, que é um saldo numa data) | data (dia) |
| `fim` | Fim do período ou data do saldo | data (dia) |
| `valor` | Valor da conta; vazio quando a empresa deixou em branco na versão lida do ENET (nos dados abertos da CVM, a linha em branco vem como 0) | reais (R$), já multiplicado pela escala informada |
| `documento` | DFP (demonstrações anuais) ou ITR (informações trimestrais) | texto |
| `referencia` | Data a que o documento se refere (fim do exercício ou do trimestre) | data (dia) |
| `versao` | Versão do documento que publicou este valor (1, 2, 3...) | número |
| `ordem` | ultimo (período do próprio documento) ou penultimo (o ano anterior, refeito) | texto |
| `origem` | dados_abertos ou enet | texto |
| `divulgado_em` | Dia da entrega à CVM (vale a partir dele, inclusive; a CVM não informa a hora). Entrega com a empresa fora de qualquer registro na CVM (pedido de registro) vale a partir do registro seguinte: o público só viu o documento perto do registro | data (dia) |
| `ate` | Dia em que outro valor tomou o lugar (vazio: vale até hoje) | data (dia) |

## `dmpl_como_era`

A demonstração das mutações do patrimônio líquido (DMPL) como era em cada data: uma linha por valor diferente que cada célula (conta × coluna do patrimônio) de cada período já teve, com o dia em que ficou público e o dia em que foi trocado. É a `demonstracoes_como_era` com uma coluna a mais no fato (`coluna`); `como_era_em(base, data, formato=FORMATO_DMPL)` dá a foto (série T1).

- **Fonte:** CVM: dados abertos de DFP e ITR (arquivos `_DMPL_con` e `_DMPL_ind`, versão mais nova) e ENET (versões anteriores, XML de cada entrega)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Montada junto com `demonstracoes_como_era`, por ano (opção `--serie-t1`)
- **Atraso de divulgação:** DFP: até 3 meses depois do fim do exercício; ITR: até 45 dias depois do trimestre (prazos da CVM, `src/prazos.py`); reapresentações a qualquer momento
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `documento`, `referencia`, `versao`, `grupo`, `conta`, `coluna`, `ordem`, `inicio`, `fim`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `divulgado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 2.0.0
- **Onde fica:** Parquet por ano em `<acervo>/base/dmpl/<ano>.parquet` (servidor de casa)
- **Linhagem:** A mesma de `demonstracoes_como_era`: `cnpj`, `documento`, `referencia` e `versao` dizem qual entrega publicou o valor e `origem` se veio dos dados abertos ou do ENET; ao lado de cada Parquet, `<ano>.json` guarda o SHA-256 da base, cada original e a `versao_do_codigo`.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `grupo` | con (consolidado) ou ind (individual) | texto |
| `demonstracao` | Sempre DMPL | texto |
| `conta` | Código da linha da DMPL no plano da CVM (5.01, 5.04.06...) | texto |
| `coluna` | Coluna do patrimônio, com nome único entre empresas (`base/dmpl.py`): capital_social, reservas_de_capital, reservas_de_lucro, lucros_acumulados, outros_resultados_abrangentes, ajustes_de_avaliacao_patrimonial, reservas_de_reavaliacao, patrimonio_liquido, patrimonio_liquido_consolidado e nao_controladores; outra coluna fica com o nome da empresa sem acento; sem_coluna quando veio sem nome | texto |
| `descricao` | Nome da linha como a empresa informou | texto |
| `inicio` | Começo do período | data (dia) |
| `fim` | Fim do período | data (dia) |
| `valor` | Valor da célula; vazio quando a empresa deixou em branco na versão lida do ENET (nos dados abertos da CVM, a linha em branco vem como 0) | reais (R$), já multiplicado pela escala informada |
| `documento` | DFP (demonstrações anuais) ou ITR (informações trimestrais) | texto |
| `referencia` | Data a que o documento se refere (fim do exercício ou do trimestre) | data (dia) |
| `versao` | Versão do documento que publicou este valor (1, 2, 3...) | número |
| `ordem` | ultimo (período do próprio documento) ou penultimo (o ano anterior, refeito) | texto |
| `origem` | dados_abertos ou enet | texto |
| `divulgado_em` | Dia da entrega à CVM (vale a partir dele, inclusive); as mesmas regras de `demonstracoes_como_era` | data (dia) |
| `ate` | Dia em que outro valor tomou o lugar (vazio: vale até hoje) | data (dia) |

## `achados_de_qualidade`

Os achados das regras fixas do selo "dado em conferência" (R1 a R11, `base/regras.py`): o número que chamou a atenção, o esperado e o porquê. Achado que some é fechado, nunca apagado.

- **Fonte:** CVM: dados abertos de DFP e ITR, cadastro e eventos do IPE
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária no VPS (tarefa `qualidade-cvm` às 8h15)
- **Atraso de divulgação:** O do documento conferido; `valido_desde` diz desde quando o achado existe
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `id`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `valido_desde`; coletado_em = `calculado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`
- **Três datas:** aconteceu_em = `registro`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Lido do acervo quando preciso (`base/cadastro.py::ler_cadastro`)
- **Linhagem:** O `cad_cia_aberta.csv` de cada dia fica no acervo e no registro de coletas (com SHA-256 e data da coleta); a tabela é refeita dele. Não é gravada sozinha: o arquivo lido entra nas origens do manifesto de quem o usa (`rotulos_atraso`, `demonstracoes_como_era`), ao lado da versão do código que montou a tabela.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `registro` | Data do registro na CVM | data (dia) |
| `cancelamento` | Data do cancelamento (vazio: ativa) | data (dia) |
| `motivo_cancelamento` | Motivo informado pela CVM (voluntário, de ofício...) | texto |
| `situacao` | Situação do registro (ATIVO, CANCELADA...) | texto |
| `setor` | Setor de atividade informado à CVM | texto |
| `uf` | Estado da sede, no cadastro de hoje (muda o prazo do ITR de 2024 no RS) | texto |

## `tickers_no_tempo`

Cada código de ação da B3 (bolsa) com a empresa e de quando a quando valeu, juntando todos os anos do formulário cadastral (FCA): código que sumiu continua aqui. Vale da entrega do FCA que trouxe o código até a do que veio sem ele (série 4, PR 1); numa data, vale o FCA de referência mais nova já entregue. Os códigos que a empresa informa fora do formato (o BTG põe "000000" nas units) entram pela tabela conferida, válidos do 1º mês em que aparecem nas carteiras dos fundos até o fim do ano do último

- **Fonte:** CVM: formulário cadastral (FCA), valores mobiliários
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual (o FCA é entregue até 31/05) e a cada alteração
- **Atraso de divulgação:** Até meses: a empresa atualiza o FCA quando muda algo
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `codigo`, `cnpj`
- **Três datas:** aconteceu_em = `inicio_negociacao`; publico_em = `primeiro_visto`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fca/tickers.parquet` (servidor de casa, `scripts/carga_fca.py`); a função é `base/cadastro.py::tickers_no_tempo`
- **Linhagem:** Montada dos zips do FCA de todos os anos, guardados no acervo e no registro de coletas (com SHA-256 e data da coleta); `primeiro_visto` e `ultimo_visto` são as entregas dos FCA de onde veio cada código. O `.json` ao lado do Parquet guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada FCA usado (no acervo e no registro de coletas, fonte `cvm-fca`, com a data da coleta e a versão do código que baixou) e a versão do código que gravou a tabela. As linhas com `origem` = códigos conferidos vêm da tabela conferida, que entra nas origens do `.json` pelo caminho no repositório e o SHA-256 (`base/linhagem.py` confere o arquivo).

| Coluna | O que é | Unidade |
|---|---|---|
| `codigo` | Código de negociação na B3 (PETR4, TAEE11) | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `valor_mobiliario` | Tipo do papel (ações ordinárias, preferenciais, units) | texto |
| `primeiro_visto` | Entrega (DT_RECEB) do primeiro FCA vigente com o código: vale desde esse dia | data (dia) |
| `ultimo_visto` | Entrega do último FCA vigente com o código | data (dia) |
| `valido_ate` | Entrega do FCA que passou a valer sem o código (deixa de valer nesse dia); vazio: ainda no FCA mais recente da empresa | data (dia) |
| `inicio_negociacao` | Início da negociação informado pela empresa | data (dia) |
| `fim_negociacao` | Fim da negociação informado (vazio: ainda negociado) | data (dia) |
| `origem` | fca (informado no formulário) ou códigos conferidos (tabela `base/conferidas/codigos_fora_do_fca.csv`: o código veio fora do formato no FCA) | texto |

## `valores_mobiliarios`

Todos os valores mobiliários de cada companhia em cada FCA (ações, units, BDRs, debêntures, notas comerciais...), com a data de entrega de cada versão: a mais nova de cada documento (a única que a CVM publica nos dados abertos), as das baixadas antigas guardadas no acervo e as versões substituídas buscadas no sistema de documentos da CVM (RAD) nos anos em que o código mudou. Base do código permanente da ação (série 3). Até 2017 o FCA não traz o código de negociação

- **Fonte:** CVM: formulário cadastral (FCA), valores mobiliários
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual (o FCA é entregue até 31/05) e a cada alteração; a carga relê todos os anos
- **Atraso de divulgação:** Até meses: a empresa atualiza o FCA quando muda algo; sem ticker até 2017
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`, `valor_mobiliario`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `recebido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.1.0
- **Onde fica:** Parquet em `<acervo>/base/fca/` (servidor de casa, `scripts/carga_fca.py`)
- **Linhagem:** `id_documento` (ou `cnpj`, `referencia` e `versao`) diz de qual FCA veio a linha. O `.json` ao lado do Parquet guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada FCA usado (no acervo e no registro de coletas, fonte `cvm-fca`, com a data da coleta e a versão do código que baixou) e a versão do código que gravou a tabela.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `referencia` | Data de referência do FCA | data (dia) |
| `versao` | Versão do documento (fica a mais nova) | número inteiro |
| `id_documento` | Número do documento na CVM (ID_DOC) | texto |
| `recebido_em` | Data de entrega desta versão à CVM (DT_RECEB): como era na data | data (dia) |
| `valor_mobiliario` | Tipo do papel, como a empresa informa | texto |
| `classe` | Classe da ação preferencial (Preferencial Classe A...) | texto |
| `codigo_informado` | Código de negociação como a empresa escreveu | texto |
| `ticker` | O código, se está no formato de ticker da B3 (PETR4); senão vazio | texto |
| `emissor` | As 4 letras do emissor (PETR), tiradas do ticker | texto |
| `mercado` | Bolsa, balcão organizado ou balcão não organizado | texto |
| `administradora` | Sigla da entidade administradora do mercado (B3) | texto |
| `inicio_negociacao` | Início da negociação informado (a troca de ticker não muda) | data (dia) |
| `fim_negociacao` | Fim da negociação informado (vazio: ainda negociado) | data (dia) |
| `segmento` | Segmento de listagem (Novo Mercado, Nível 1...) | texto |
| `inicio_listagem` | Início da listagem no segmento | data (dia) |
| `fim_listagem` | Fim da listagem no segmento | data (dia) |
| `origem` | dados abertos (arquivo anual da CVM) ou documento da versão (RAD da CVM) | texto |

## `emissores`

Emissor (as 4 letras do ticker e do ISIN: PETR) → CNPJ, com o primeiro e o último ano do FCA em que apareceu. É a ligação do ISIN das carteiras dos fundos (CDA) com a empresa. Um emissor com mais de um CNPJ é conflito e fica sem resposta

- **Fonte:** CVM: formulário cadastral (FCA), derivado de `valores_mobiliarios`
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual (o FCA é entregue até 31/05) e a cada alteração; a carga relê todos os anos
- **Atraso de divulgação:** Até meses: a empresa atualiza o FCA quando muda algo; sem ticker até 2017
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `emissor`, `cnpj`
- **Três datas:** publico_em = `primeiro_recebido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fca/` (servidor de casa, `scripts/carga_fca.py`)
- **Linhagem:** Derivada de `valores_mobiliarios` na mesma carga. O `.json` ao lado do Parquet guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada FCA usado (no acervo e no registro de coletas, fonte `cvm-fca`, com a data da coleta e a versão do código que baixou) e a versão do código que gravou a tabela. As linhas com `origem` = códigos conferidos vêm da tabela conferida, que entra nas origens do `.json` pelo caminho no repositório e o SHA-256 (`base/linhagem.py` confere o arquivo).

| Coluna | O que é | Unidade |
|---|---|---|
| `emissor` | As 4 letras do emissor | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `primeiro_ano` | Ano do primeiro FCA com o emissor | número inteiro |
| `ultimo_ano` | Ano do último FCA com o emissor | número inteiro |
| `primeiro_recebido_em` | Entrega do primeiro FCA com o emissor (nos códigos conferidos, o 1º mês nas carteiras dos fundos): desde quando a ligação é conhecida | data (dia) |
| `conflito` | Verdadeiro se o emissor aparece com mais de um CNPJ | verdadeiro ou falso |
| `origem` | fca (informado no formulário) ou códigos conferidos (tabela `base/conferidas/codigos_fora_do_fca.csv`: o código veio fora do formato no FCA) | texto |

## `codigos_invalidos`

Códigos de negociação informados fora do formato de ticker (a CSN informa "4030"): não viram ligação e vão para o relatório de buracos; os da bolsa que aparecem nas carteiras dos fundos são conferidos um a um e entram em `codigos_fora_do_fca`

- **Fonte:** CVM: formulário cadastral (FCA), derivado de `valores_mobiliarios`
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual (o FCA é entregue até 31/05) e a cada alteração; a carga relê todos os anos
- **Atraso de divulgação:** Até meses: a empresa atualiza o FCA quando muda algo; sem ticker até 2017
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `codigo_informado`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `recebido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fca/` (servidor de casa, `scripts/carga_fca.py`)
- **Linhagem:** Derivada de `valores_mobiliarios` na mesma carga. O `.json` ao lado do Parquet guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada FCA usado (no acervo e no registro de coletas, fonte `cvm-fca`, com a data da coleta e a versão do código que baixou) e a versão do código que gravou a tabela.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `referencia` | Data de referência do FCA | data (dia) |
| `recebido_em` | Data de entrega do FCA à CVM (DT_RECEB) | data (dia) |
| `valor_mobiliario` | Tipo do papel, como a empresa informa | texto |
| `codigo_informado` | O código como a empresa escreveu | texto |

## `carteiras_dos_fundos`

As posições em ações de todos os fundos registrados na CVM, por mês, desde 2005 (CDA, bloco de ações): comprado, emprestado e vendido, com o ISIN e o emissor. Fundos e posições que saíram continuam (sem viés de sobrevivência). Um Parquet por ano; quando a CVM regrava um ano, a versão anterior fica como `<ano>.v<N>` **Sem pessoa pela raiz:** toda raiz de CNPJ desta tabela existe na `cnpj_empresas_pj`, que só tem pessoa jurídica; CNPJ que não tem 14 dígitos conta como fora. A prova cobre quem a linha descreve, não o texto livre que ela carrega (o assunto de um evento, por exemplo). A conferência é `scripts/conferir_sem_pessoa.py`, rodada antes de cada concessão do piloto

- **Fonte:** CVM: composição e diversificação das aplicações dos fundos (CDA), bloco 4
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal; de 2005 a 2022 um arquivo por ano, de 2023 em diante um por mês
- **Atraso de divulgação:** O arquivo sai uns 40 dias depois do mês e o fundo pode deixar uma posição em sigilo por até 90 dias: `disponivel_em` usa competência + 90 dias, ou o fim do sigilo se depois (o prazo, não a data vista). Desde 10/2026 o arquivista olha os 5 meses mais novos todo dia: a carteira entregue depois do prazo só vale do dia em que apareceu (`visto_em`). Antes disso, a data é só o prazo
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `cnpj_fundo`, `tipo`, `codigo`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.1.0
- **Onde fica:** Parquet por ano em `<acervo>/base/cda/<ano>.parquet` (servidor de casa, `scripts/carga_cda.py`)
- **Linhagem:** O `<ano>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada arquivo do CDA usado (no acervo e no registro de coletas, com a data da coleta e a versão do código que baixou) e a versão do código que gravou.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês da carteira (último dia) | data (dia) |
| `cnpj_fundo` | CNPJ do fundo (ou da classe, depois da CVM 175) | texto |
| `tipo_do_fundo` | Tipo do fundo como a CVM informa | texto |
| `fundo` | Nome do fundo (pessoa jurídica) | texto |
| `tipo` | comprado, emprestado ou vendido | texto |
| `codigo` | Código do ativo informado (ticker) | texto |
| `isin` | ISIN do ativo: o código permanente | texto |
| `emissor` | As 4 letras do emissor, tiradas do ISIN | texto |
| `descricao` | Descrição do ativo informada | texto |
| `quantidade` | Quantidade no fim do mês | ações |
| `valor` | Valor de mercado no fim do mês | reais (R$), já multiplicado pela escala informada |
| `compras` | Valor comprado no mês | reais (R$), já multiplicado pela escala informada |
| `vendas` | Valor vendido no mês | reais (R$), já multiplicado pela escala informada |
| `confidencial_ate` | Até quando a posição ficou em sigilo (vazio: sem sigilo) | data (dia) |
| `visto_em` | O dia em que a carteira do fundo apareceu na CVM pela primeira vez, pelas baixadas diárias do arquivista (vazio: já estava no arquivo quando a base começou a olhar, em 10/2026; vale o prazo) | data (dia) |
| `disponivel_em` | Desde quando a posição era pública (como era na data): o prazo, ou `visto_em` se for depois | data (dia) |

## `carteiras_bloco_8`

As ações e os certificados de depósito que os fundos informam no bloco 8 do CDA ("demais ativos não codificados"), sem o código estruturado, com o CNPJ do emissor que o próprio fundo informa: em 2020, R$ 1,14 tri (soma dos meses) em ações de companhias com ticker, ~26% a mais sobre o bloco 4, quase nada repetido entre os blocos. Emissor pessoa física nunca entra (o CPF é descartado na leitura). Um Parquet por ano, com versões

- **Fonte:** CVM: composição e diversificação das aplicações dos fundos (CDA), bloco 8
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal; de 2005 a 2022 um arquivo por ano, de 2023 em diante um por mês
- **Atraso de divulgação:** O do CDA: `disponivel_em` usa competência + 90 dias, ou o fim do sigilo se depois, ou o dia em que a carteira apareceu (`visto_em`, desde 10/2026) se for depois
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `cnpj_fundo`, `tipo`, `cnpj_emissor`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.1.0
- **Onde fica:** Parquet por ano em `<acervo>/base/cda_bloco_8/<ano>.parquet` (servidor de casa, `scripts/carga_cda.py`, na mesma carga do CDA)
- **Linhagem:** O `<ano>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada arquivo do CDA usado (os mesmos do bloco 4) e a versão do código que gravou.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês da carteira (último dia) | data (dia) |
| `cnpj_fundo` | CNPJ do fundo (ou da classe, depois da CVM 175) | texto |
| `tipo_do_fundo` | Tipo do fundo como a CVM informa | texto |
| `fundo` | Nome do fundo (pessoa jurídica) | texto |
| `tipo` | comprado, emprestado ou vendido | texto |
| `tipo_do_ativo` | Ação ordinária, ação preferencial... como o fundo informa | texto |
| `cnpj_emissor` | CNPJ do emissor que o fundo informa (só pessoa jurídica) | texto |
| `nome_do_emissor` | Nome do emissor como o fundo escreve | texto |
| `descricao` | Descrição do ativo ("PETR3 - PETROBRAS") | texto |
| `quantidade` | Quantidade no fim do mês | ações |
| `valor` | Valor de mercado no fim do mês | reais (R$), já multiplicado pela escala informada |
| `compras` | Valor comprado no mês | reais (R$), já multiplicado pela escala informada |
| `vendas` | Valor vendido no mês | reais (R$), já multiplicado pela escala informada |
| `confidencial_ate` | Até quando a posição ficou em sigilo (vazio: sem sigilo) | data (dia) |
| `visto_em` | O dia em que a carteira do fundo apareceu na CVM pela primeira vez, pelas baixadas diárias do arquivista (vazio: já estava no arquivo quando a base começou a olhar, em 10/2026; vale o prazo) | data (dia) |
| `disponivel_em` | Desde quando a posição era pública (como era na data): o prazo, ou `visto_em` se for depois | data (dia) |

## `cda_cotas`

As cotas de fundos que cada fundo tem, do bloco 2 do CDA ("cotas de fundos"): quem compra cotas de FIDC, de FIP, de FII e de outros fundos, com o CNPJ do fundo investido e o tipo dele (`tipo_do_ativo` = "FIDC" desde ~2009; em 2005 tudo é "Cotas de fundos"). Em jun/2026, 4.531 fundos com R$ 291,8 bi em cotas de 2.403 FIDCs (relatório da base de crédito). Só fundos (pessoas jurídicas); os nomes ficam no cadastro de fundos. Um Parquet por ano, com versões

- **Fonte:** CVM: composição e diversificação das aplicações dos fundos (CDA), bloco 2
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal; de 2005 a 2022 um arquivo por ano, de 2023 em diante um por mês
- **Atraso de divulgação:** O do CDA: `disponivel_em` usa competência + 90 dias, ou o fim do sigilo se depois, ou o dia em que a carteira apareceu (`visto_em`, desde 10/2026) se for depois
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `tipo_do_fundo`, `cnpj_fundo`, `cnpj_fundo_investido`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2005-01-31 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por ano em `<acervo>/base/cda_cotas/<ano>.parquet` (servidor de casa, `scripts/carga_cda.py`, na mesma carga do CDA)
- **Linhagem:** O `<ano>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada arquivo do CDA usado (os mesmos do bloco 4) e a versão do código que gravou.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês da carteira (último dia) | data (dia) |
| `cnpj_fundo` | CNPJ do fundo que tem as cotas (ou da classe, depois da CVM 175) | texto |
| `tipo_do_fundo` | Tipo do fundo que tem as cotas como a CVM informa; com o CNPJ, identifica o fundo (em 11/2022 um fundo aparece como FI e como FIP) | texto |
| `tipo_do_ativo` | Tipo do fundo investido como o fundo informa ("FIDC", "FI Participações", "FI Imobiliário", "Fundos de Índice", "Fundo de Investimento e de Cotas", "Cotas de fundos") | texto |
| `emissor_ligado` | O fundo investido é ligado ao administrador ou ao gestor de quem compra (vazio: não informado, como em 2005) | verdadeiro ou falso |
| `cnpj_fundo_investido` | CNPJ do fundo (ou da classe) cujas cotas o fundo tem | texto |
| `id_subclasse` | Código da subclasse investida, depois da CVM 175 (vazio: sem subclasse) | texto |
| `quantidade` | Quantidade de cotas no fim do mês | número com decimais, na unidade da fonte |
| `valor` | Valor de mercado no fim do mês | reais (R$), já multiplicado pela escala informada |
| `compras` | Valor comprado no mês | reais (R$), já multiplicado pela escala informada |
| `vendas` | Valor vendido no mês | reais (R$), já multiplicado pela escala informada |
| `confidencial_ate` | Até quando a posição ficou em sigilo (vazio: sem sigilo) | data (dia) |
| `visto_em` | O dia em que a carteira do fundo apareceu na CVM pela primeira vez, pelas baixadas diárias do arquivista (vazio: já estava no arquivo quando a base começou a olhar, em 10/2026; vale o prazo) | data (dia) |
| `disponivel_em` | Desde quando a posição era pública (como era na data): o prazo, ou `visto_em` se for depois | data (dia) |

## `fidc_informe`

O informe mensal de cada FIDC desde 2013, um Parquet por quadro (`tab_I` a `tab_X_7`) e por ano, no formato da fonte: carteira, prazos, inadimplência por faixa, pré-pagamento, recompras, cedentes. As colunas mudam com os anos (15 quadros em 2013, 18 em 2026) e são as do dicionário da CVM (`meta_inf_mensal_fidc.txt`); a base acrescenta as quatro abaixo. Sem dado pessoal: dos documentos de cedentes só fica CNPJ válido (CPF vira vazio)

- **Fonte:** CVM: informe mensal de FIDC
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal; de 2013 a 2024 um arquivo por ano, de 2025 em diante um por mês
- **Atraso de divulgação:** Entregue em até 15 dias; a CVM regrava meses passados (cada regravação vira versão `<ano>.v<N>`). `disponivel_em` usa competência + 45 dias (o prazo, não a data vista). Desde 10/2026 o arquivista olha os 4 meses mais novos todo dia: o informe entregue depois só vale do dia em que apareceu (`visto_em`). Antes disso, a data é só o prazo
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `cnpj_fundo`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.1.0
- **Onde fica:** Parquet em `<acervo>/base/fidc/informe/<quadro>/<ano>.parquet` (servidor de casa, `scripts/carga_fidc.py`)
- **Linhagem:** O `<ano>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada arquivo do informe usado, com todas as versões guardadas de onde sai o `visto_em` (no acervo e no registro de coletas, com a data da coleta e a versão do código que baixou) e a versão do código que gravou.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês do informe (último dia) | data (dia) |
| `cnpj_fundo` | CNPJ do fundo (ou da classe, depois da CVM 175) | texto |
| `visto_em` | O dia em que o informe do fundo apareceu na CVM pela primeira vez, pelas baixadas diárias do arquivista (vazio: já estava no arquivo quando a base começou a olhar, em 10/2026; vale o prazo) | data (dia) |
| `disponivel_em` | Desde quando o informe era público (como era na data): competência + 45 dias, ou `visto_em` se for depois | data (dia) |

## `cadastro_de_fundos`

O cadastro de fundos da CVM (atual, histórico de administrador, auditor, classe... e o registro de fundos e classes da CVM 175), com o gestor de cada FIDC: a lista de clientes possíveis do Capital. Fundos cancelados continuam. Sem dado pessoal: o diretor responsável e o histórico dele ficam fora; o gestor pessoa física fica só com a marca PF. **Um CNPJ pode ter várias linhas:** em 12/11/2026, de 41103 CNPJs, 5244 aparecem em mais de uma linha, e em 4805 deles com mais de um `TP_FUNDO` (o mesmo CNPJ registrado em mais de um tipo); a repetição também pode vir de o fundo trocar de gestor, auditor, custodiante, administrador ou controlador (a base não corrige); para contar fundos, conte CNPJ_FUNDO distintos

- **Fonte:** CVM: cadastro de fundos (`cad_fi.csv`, `cad_fi_hist.zip`, `registro_fundo_classe.zip`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária na CVM; a base guarda um retrato a cada carga (versões `<nome>.v<N>`)
- **Atraso de divulgação:** Do dia: é um retrato do cadastro na data da coleta; o histórico vem de `cad_fi_hist`
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `CNPJ_FUNDO`
- **Três datas:** aconteceu_em = `DT_REG`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fidc/cadastro/` (servidor de casa, `scripts/carga_fidc.py`)
- **Linhagem:** O `.json` de cada tabela guarda o SHA-256, o endereço e o SHA-256 do arquivo da CVM (no acervo e no registro de coletas, com a data e a versão do código) e a versão que gravou.

| Coluna | O que é | Unidade |
|---|---|---|
| `TP_FUNDO` | Tipo do fundo (FIDC, FI, FII...) | texto |
| `CNPJ_FUNDO` | CNPJ do fundo | texto |
| `DENOM_SOCIAL` | Nome do fundo | texto |
| `DT_REG` | Data do registro na CVM | data (dia) |
| `DT_CONST` | Data de constituição | data (dia) |
| `CD_CVM` | Código do fundo na CVM | texto |
| `DT_CANCEL` | Data do cancelamento (vazio: ativo) | data (dia) |
| `SIT` | Situação (em funcionamento normal, cancelado...) | texto |
| `DT_INI_SIT` | Início da situação | data (dia) |
| `DT_INI_ATIV` | Início das atividades | data (dia) |
| `DT_INI_EXERC` | Início do exercício social | data (dia) |
| `DT_FIM_EXERC` | Fim do exercício social | data (dia) |
| `CLASSE` | Classe do fundo (Ações, Renda Fixa, FIDC...) | texto |
| `DT_INI_CLASSE` | Início da classe | data (dia) |
| `RENTAB_FUNDO` | Indicador de desempenho informado (CDI, Ibovespa...) | texto |
| `CONDOM` | Condomínio aberto ou fechado | texto |
| `FUNDO_COTAS` | S se é fundo de cotas | texto |
| `FUNDO_EXCLUSIVO` | S se é fundo exclusivo | texto |
| `TRIB_LPRAZO` | S se tem tributação de longo prazo | texto |
| `PUBLICO_ALVO` | Público-alvo (geral, qualificado, profissional) | texto |
| `ENTID_INVEST` | S se é entidade de investimento | texto |
| `TAXA_PERFM` | Taxa de performance | percentual, como a CVM informa |
| `INF_TAXA_PERFM` | Texto sobre a taxa de performance | texto |
| `TAXA_ADM` | Taxa de administração | percentual ao ano, como a CVM informa |
| `INF_TAXA_ADM` | Texto sobre a taxa de administração | texto |
| `VL_PATRIM_LIQ` | Patrimônio líquido | reais (R$) |
| `DT_PATRIM_LIQ` | Data do patrimônio líquido | data (dia) |
| `CNPJ_ADMIN` | CNPJ do administrador | texto |
| `ADMIN` | Nome do administrador (empresa) | texto |
| `PF_PJ_GESTOR` | PF ou PJ: o gestor é pessoa física ou jurídica | texto |
| `CPF_CNPJ_GESTOR` | CNPJ do gestor; vazio quando o gestor é pessoa física | texto |
| `GESTOR` | Nome do gestor; vazio quando é pessoa física | texto |
| `CNPJ_AUDITOR` | CNPJ do auditor | texto |
| `AUDITOR` | Nome do auditor | texto |
| `CNPJ_CUSTODIANTE` | CNPJ do custodiante | texto |
| `CUSTODIANTE` | Nome do custodiante | texto |
| `CNPJ_CONTROLADOR` | CNPJ do controlador | texto |
| `CONTROLADOR` | Nome do controlador | texto |
| `INVEST_CEMPR_EXTER` | S se pode aplicar 100% no exterior | texto |
| `CLASSE_ANBIMA` | Classificação da Anbima | texto |

## `cadastro_gestor_hist`

O gestor de cada fundo da CVM ao longo do tempo (`cad_fi_hist`): uma linha por período, com o início e o fim que a CVM declara. Serve para dizer quem era o gestor do fundo numa data passada. A CVM não dá o dia em que cada linha ficou pública. Sem dado pessoal: o gestor pessoa física fica sem CNPJ e sem nome

- **Fonte:** CVM: histórico do cadastro de fundos (`cad_fi_hist.zip`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária na CVM; a base guarda um retrato a cada carga (versões `<nome>.v<N>`)
- **Atraso de divulgação:** Sem data pública por linha: vale o início e o fim que a CVM declara
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `CNPJ_FUNDO`, `DT_INI_GESTOR`
- **Três datas:** aconteceu_em = `DT_INI_GESTOR`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fidc/cadastro/` (servidor de casa, `scripts/carga_fidc.py`)
- **Linhagem:** O `.json` da tabela guarda o SHA-256, o endereço e o SHA-256 do arquivo da CVM (no acervo e no registro de coletas, com a data e a versão do código) e a versão que gravou.

| Coluna | O que é | Unidade |
|---|---|---|
| `CNPJ_FUNDO` | CNPJ do fundo | texto |
| `DT_REG` | Data do registro do fundo na CVM | data (dia) |
| `PF_PJ_GESTOR` | PF ou PJ: o gestor é pessoa física ou jurídica | texto |
| `CPF_CNPJ_GESTOR` | CNPJ do gestor; vazio quando é pessoa física | texto |
| `GESTOR` | Nome do gestor; vazio quando é pessoa física | texto |
| `DT_INI_GESTOR` | Início do gestor no fundo | data (dia) |
| `DT_FIM_GESTOR` | Fim do gestor no fundo (vazio: sem fim declarado) | data (dia) |

## `cadastro_admin_hist`

O administrador de cada fundo da CVM ao longo do tempo (`cad_fi_hist`): uma linha por período, com o início e o fim que a CVM declara. Serve para dizer quem era o administrador do fundo numa data passada. A CVM não dá o dia em que cada linha ficou pública. Sem dado pessoal: só pessoa jurídica

- **Fonte:** CVM: histórico do cadastro de fundos (`cad_fi_hist.zip`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária na CVM; a base guarda um retrato a cada carga (versões `<nome>.v<N>`)
- **Atraso de divulgação:** Sem data pública por linha: vale o início e o fim que a CVM declara
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `CNPJ_FUNDO`, `DT_INI_ADMIN`
- **Três datas:** aconteceu_em = `DT_INI_ADMIN`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fidc/cadastro/` (servidor de casa, `scripts/carga_fidc.py`)
- **Linhagem:** O `.json` da tabela guarda o SHA-256, o endereço e o SHA-256 do arquivo da CVM (no acervo e no registro de coletas, com a data e a versão do código) e a versão que gravou.

| Coluna | O que é | Unidade |
|---|---|---|
| `CNPJ_FUNDO` | CNPJ do fundo | texto |
| `DT_REG` | Data do registro do fundo na CVM | data (dia) |
| `CNPJ_ADMIN` | CNPJ do administrador | texto |
| `ADMIN` | Nome do administrador (empresa) | texto |
| `DT_INI_ADMIN` | Início do administrador no fundo | data (dia) |
| `DT_FIM_ADMIN` | Fim do administrador no fundo (vazio: sem fim declarado) | data (dia) |

## `registro_de_fundos`

O registro de fundos da CVM 175 (`registro_fundo`): todo fundo registrado, com o tipo (FIP, FII, FIDC, FIAGRO, FI...), a situação, o administrador e o gestor. É o cadastro em dia dos fundos de participação (FIP), que o `cadastro_de_fundos` antigo quase não traz mais: serve para reconhecer um fundo no quadro de sócios da Receita. Uma linha por fundo e gestor (o fundo com mais de um gestor repete). Fundos cancelados continuam. Sem dado pessoal: o gestor pessoa física fica só com a marca PF, sem CPF e sem nome, e o diretor responsável fica fora. **Limites medidos em 12/11/2026:** 17 linhas são idênticas em todas as colunas que a base guarda (o diretor responsável sai na montagem); o gestor fica vazio em 26679 linhas, quase todas de fundos cancelados (a CVM os deixa sem gestor) ou de gestor pessoa física. Os registros vão de 1957 a hoje, esparsos nos primeiros anos.

- **Fonte:** CVM: registro de fundos e classes da CVM 175 (`registro_fundo_classe.zip`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária na CVM; a base guarda um retrato a cada carga (versões `<nome>.v<N>`)
- **Atraso de divulgação:** Do dia: é um retrato do registro na data da coleta
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `ID_Registro_Fundo`, `CPF_CNPJ_Gestor`
- **Três datas:** aconteceu_em = `Data_Registro`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fidc/cadastro/` (servidor de casa, `scripts/carga_fidc.py`)
- **Linhagem:** O `.json` da tabela guarda o SHA-256, o endereço e o SHA-256 do arquivo da CVM (no acervo e no registro de coletas, com a data e a versão do código) e a versão que gravou.

| Coluna | O que é | Unidade |
|---|---|---|
| `ID_Registro_Fundo` | Identificador do registro do fundo na CVM | texto |
| `CNPJ_Fundo` | CNPJ do fundo (14 dígitos) | texto |
| `Codigo_CVM` | Código do fundo na CVM | texto |
| `Data_Registro` | Data do registro na CVM | data (dia) |
| `Data_Constituicao` | Data de constituição | data (dia) |
| `Tipo_Fundo` | Tipo do fundo (FIP, FII, FIDC, FIAGRO, FI...) | texto |
| `Denominacao_Social` | Nome do fundo | texto |
| `Data_Cancelamento` | Data do cancelamento (vazio: ativo) | data (dia) |
| `Situacao` | Situação (em funcionamento normal, cancelado...) | texto |
| `Data_Inicio_Situacao` | Início da situação | data (dia) |
| `Data_Adaptacao_RCVM175` | Data da adaptação à Resolução CVM 175 | data (dia) |
| `Data_Inicio_Exercicio_Social` | Início do exercício social | data (dia) |
| `Data_Fim_Exercicio_Social` | Fim do exercício social | data (dia) |
| `Patrimonio_Liquido` | Patrimônio líquido | reais (R$) |
| `Data_Patrimonio_Liquido` | Data do patrimônio líquido | data (dia) |
| `CNPJ_Administrador` | CNPJ do administrador | texto |
| `Administrador` | Nome do administrador (empresa) | texto |
| `Tipo_Pessoa_Gestor` | PF ou PJ: o gestor é pessoa física ou jurídica | texto |
| `CPF_CNPJ_Gestor` | CNPJ do gestor; vazio quando o gestor é pessoa física | texto |
| `Gestor` | Nome do gestor; vazio quando é pessoa física | texto |

## `fips_registrados`

Cópia reduzida de `registro_de_fundos` que vai ao VPS só para a lista de compradores por setor da API externa (linha 844): só FIP, só o fundo cuja raiz está em `cnpj_empresas_pj` (sem pessoa), uma linha por fundo e registro (sem repetir por gestor). Sem gestor, administrador, nome nem CPF. A CVM não dá o dia em que cada linha ficou pública: vale a data do registro, como na tabela inteira. Montada no envio, não fica no acervo de casa. **Sem pessoa pela raiz:** toda raiz de CNPJ desta tabela existe na `cnpj_empresas_pj`, que só tem pessoa jurídica; CNPJ que não tem 14 dígitos conta como fora. A prova cobre quem a linha descreve, não o texto livre que ela carrega (o assunto de um evento, por exemplo). A conferência é `scripts/conferir_sem_pessoa.py`, rodada antes de cada concessão do piloto. **Alcance da marca:** vale para esta cópia, medida montada em 12/11/2026 (4.419 linhas, 4.384 raízes, 0 fora da `cnpj_empresas_pj`, 0 CNPJ que não confere, 0 fundo que não é FIP); a tabela inteira `registro_de_fundos` segue sem a marca

- **Fonte:** CVM: registro de fundos e classes da CVM 175 (cópia reduzida de `registro_de_fundos`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada envio do recorte ao VPS (`scripts/montar_recorte_da_api.py --degrau 4`)
- **Atraso de divulgação:** O de `registro_de_fundos`: um retrato do registro na data da coleta
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `CNPJ_Fundo`, `Data_Registro`
- **Três datas:** aconteceu_em = `Data_Registro`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fips_registrados/fips_registrados.parquet`, só no VPS (montado pelo recorte, `base/recorte_dos_compradores.py`)
- **Linhagem:** Derivada de `registro_de_fundos` no envio; a trava `base/recorte_dos_compradores.py::conferir_reduzidas` lê a saída e derruba o envio em coluna fora da lista, raiz fora de `cnpj_empresas_pj`, CNPJ que não confere (dígito errado ou CPF completado com zeros), fundo que não é FIP ou cópia vazia.

| Coluna | O que é | Unidade |
|---|---|---|
| `CNPJ_Fundo` | CNPJ do fundo (14 dígitos) | texto |
| `Tipo_Fundo` | Tipo do fundo: sempre FIP | texto |
| `Data_Registro` | Data do registro na CVM | data (dia) |
| `Data_Cancelamento` | Data do cancelamento (vazio: ativo) | data (dia) |

## `painel_dos_fundos`

Quem tinha cada empresa em cada mês desde 2005: as posições dos fundos (CDA) somadas por mês e tipo (comprado, emprestado, vendido), em duas versões: por emissor (sempre) e por empresa (CNPJ). O emissor vira CNPJ pelo FCA e, no que falta (empresas que saíram antes de 2018), pela tabela conferida `base/conferidas/emissores_antigos.csv`; cada ano tem pelo menos 95% do valor comprado com CNPJ (`cobertura`), e o resto está em `buracos`. Inclui empresas que saíram da bolsa (sem viés de sobrevivência)

- **Fonte:** Derivado: CVM, CDA (posições) e FCA (emissores), mais a tabela conferida
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal, montado de novo quando o CDA ou o FCA mudam
- **Atraso de divulgação:** O do CDA: `disponivel_em` é a maior data das posições somadas (o total só era público quando a última posição dele ficou pública)
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `emissor`, `tipo`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.1.0
- **Onde fica:** Parquet em `<acervo>/base/fundos/`: `painel_emissor/<ano>`, `painel_empresa/<ano>`, `cobertura` e `buracos` (servidor de casa, `scripts/montar_painel_dos_fundos.py`)
- **Linhagem:** O `.json` de cada tabela lista as tabelas de entrada (o CDA do ano e os emissores do FCA, com o SHA-256 do conteúdo anotado no manifesto delas) e o SHA-256 da tabela conferida; cada entrada tem a própria linhagem até os arquivos da CVM. Guarda a versão do código. `base/linhagem.py::linhagem_da_tabela` segue cada tabela de entrada pelo manifesto dela até os originais; se uma entrada foi regravada depois, a derivada não confere até ser remontada.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês da carteira | data (dia) |
| `emissor` | As 4 posições do emissor (só no painel por emissor) | texto |
| `cnpj` | CNPJ da empresa (só no painel por empresa) | texto |
| `tipo` | comprado, emprestado ou vendido | texto |
| `fundos` | Quantos fundos tinham a posição (cada fundo uma vez por empresa) | número inteiro |
| `valor` | Valor de mercado somado | reais (R$), já multiplicado pela escala informada |
| `quantidade` | Quantidade somada | ações |
| `compras` | Valor comprado no mês, somado | reais (R$), já multiplicado pela escala informada |
| `vendas` | Valor vendido no mês, somado | reais (R$), já multiplicado pela escala informada |
| `disponivel_em` | Desde quando o total era público (como era na data) | data (dia) |
| `fundos_no_bloco_8` | Só no painel por empresa: quantos fundos informaram a ação no bloco 8 (demais ativos, pelo CNPJ do emissor) | número inteiro |
| `valor_no_bloco_8` | Só no painel por empresa: valor de mercado no bloco 8; as colunas sem o sufixo são só o bloco 4 | reais (R$), já multiplicado pela escala informada |
| `quantidade_no_bloco_8` | Só no painel por empresa: quantidade no bloco 8 | ações |

## `cobertura_dos_fundos`

Por mês desde 2005, quanto do valor comprado pelos fundos chega a um CNPJ de empresa pela ligação do painel (a meta da tabela conferida é 95% em cada ano)

- **Fonte:** Derivado: CVM, CDA (posições) e FCA (emissores), mais as tabelas conferidas
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal, montada junto com o painel dos fundos
- **Atraso de divulgação:** O do CDA (os meses mais novos ainda crescem enquanto os fundos entregam)
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `competencia`
- **Três datas:** aconteceu_em = `competencia`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fundos/cobertura.parquet` (`scripts/montar_painel_dos_fundos.py`)
- **Linhagem:** O `.json` lista as tabelas de entrada (cada ano do CDA e os emissores do FCA, com o SHA-256 do conteúdo) e o SHA-256 da tabela conferida; guarda a versão do código. `base/linhagem.py::linhagem_da_tabela` segue cada tabela de entrada pelo manifesto dela até os originais; se uma entrada foi regravada depois, a derivada não confere até ser remontada.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês da carteira | data (dia) |
| `valor_comprado` | Valor comprado por todos os fundos | reais (R$), já multiplicado pela escala informada |
| `valor_com_cnpj` | A parte desse valor cujo emissor tem CNPJ | reais (R$), já multiplicado pela escala informada |
| `fracao_com_cnpj` | valor_com_cnpj ÷ valor_comprado | fração (0,25 = 25%) |

## `buracos_dos_fundos`

Os emissores das carteiras dos fundos que ficaram sem CNPJ, do maior valor comprado para o menor: a lista de trabalho para a próxima conferência (nada some calado)

- **Fonte:** Derivado: CVM, CDA (posições) e FCA (emissores), mais as tabelas conferidas
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal, montada junto com o painel dos fundos
- **Atraso de divulgação:** O do CDA
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `emissor`
- **Três datas:** nenhuma coluna da tabela traz estas datas
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.1.0
- **Onde fica:** Parquet em `<acervo>/base/fundos/buracos.parquet` (`scripts/montar_painel_dos_fundos.py`)
- **Linhagem:** O `.json` lista as tabelas de entrada (cada ano do CDA e os emissores do FCA, com o SHA-256 do conteúdo) e o SHA-256 da tabela conferida; guarda a versão do código. `base/linhagem.py::linhagem_da_tabela` segue cada tabela de entrada pelo manifesto dela até os originais; se uma entrada foi regravada depois, a derivada não confere até ser remontada.

| Coluna | O que é | Unidade |
|---|---|---|
| `emissor` | As 4 posições do emissor sem CNPJ | texto |
| `valor` | Valor comprado somado em todos os meses | reais (R$), já multiplicado pela escala informada |
| `primeira` | Primeiro mês em que aparece | data (dia) |
| `ultima` | Último mês em que aparece | data (dia) |
| `descricao` | Descrição do ativo no CDA (a pista para a conferência) | texto |
| `motivo` | Por que fica sem empresa, se foi conferido (`emissores_sem_ligacao`); vazio: ainda não conferido | texto |

## `emissores_sem_ligacao`

Tabela conferida à mão: emissores das carteiras dos fundos que ficam sem empresa de propósito, cada um com o motivo (companhia sem ação na bolsa, como a Comerc e a Granja Faria; dois CNPJs no período; BDR de empresa de fora; falta de prova). Ficam só no painel por emissor, e o motivo vai para o relatório de buracos (série 4, PR 3)

- **Fonte:** CVM: formulário cadastral (FCA), cadastro de companhias, IPE e descrição no CDA
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Quando a conferência anda (pelos buracos de maior valor)
- **Atraso de divulgação:** Nenhum
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `emissor`
- **Três datas:** coletado_em = `conferido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** `base/conferidas/emissores_sem_ligacao.csv` no repositório (Git)
- **Linhagem:** Cada linha diz a fonte e quando foi conferida; o histórico fica no Git e o painel dos fundos anota o SHA-256 da tabela no `.json` de cada tabela que monta.

| Coluna | O que é | Unidade |
|---|---|---|
| `emissor` | As 4 posições do emissor | texto |
| `cnpj` | CNPJ, quando é um só e conhecido; vazio nos outros casos | texto |
| `empresa` | Nome no FCA ou no cadastro; sem CNPJ, como o CDA descreve | texto |
| `motivo` | Por que o emissor fica sem empresa | texto |
| `fonte` | De onde veio a conferência | texto |
| `conferido_em` | Dia da conferência | data (dia) |

## `emissores_antigos`

Tabela conferida à mão: emissores das carteiras dos fundos que saíram da bolsa ou mudaram de código antes de 2018 (e a CSN, que informa "4030"), ligados ao CNPJ pelo cadastro de companhias da CVM, um a um, sem casar nome aproximado

- **Fonte:** CVM: cadastro de companhias (`cad_cia_aberta.csv`) e descrição do ativo no CDA
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Quando a conferência anda (pelos buracos de maior valor)
- **Atraso de divulgação:** Nenhum: a ligação vale para o período em que o emissor aparece nas carteiras
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `emissor`
- **Três datas:** coletado_em = `conferido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** `base/conferidas/emissores_antigos.csv` no repositório (Git)
- **Linhagem:** Cada linha diz a fonte e quando foi conferida (`fonte`, `conferido_em`); o histórico de cada mudança fica no Git, e quem usa a tabela anota o SHA-256 dela no próprio `.json`.

| Coluna | O que é | Unidade |
|---|---|---|
| `emissor` | As 4 posições do emissor | texto |
| `cnpj` | CNPJ da companhia no cadastro da CVM | texto |
| `empresa_no_cadastro` | Nome no cadastro de companhias da CVM | texto |
| `cd_cvm` | Código da companhia na CVM | texto |
| `registro` | Data do registro na CVM | data (dia) |
| `cancelamento` | Data do cancelamento do registro (vazio: ativa) | data (dia) |
| `descricao_no_cda` | Descrição do ativo nas carteiras dos fundos | texto |
| `no_cda` | Primeiro e último mês nas carteiras (AAAA-MM–AAAA-MM) | texto |
| `observacao` | O que aconteceu com a empresa (incorporação, troca de nome) | texto |
| `fonte` | De onde veio a ligação | texto |
| `conferido_em` | Dia da conferência | data (dia) |

## `codigos_fora_do_fca`

Tabela conferida à mão: códigos de empresas da bolsa que o FCA traz fora do formato (o BTG informa "000000" nas units, a Marisa "022055"). O CNPJ vem do próprio FCA e o código e o ISIN, das carteiras dos fundos; a `carga_fca` junta a tabela aos tickers e aos emissores

- **Fonte:** CVM: formulário cadastral (FCA) e carteiras dos fundos (CDA)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Quando a conferência anda (pelos buracos de maior valor)
- **Atraso de divulgação:** Nenhum: o código vale do 1º ao último mês em que aparece nas carteiras
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `codigo`
- **Três datas:** coletado_em = `conferido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** `base/conferidas/codigos_fora_do_fca.csv` no repositório (Git)
- **Linhagem:** Cada linha diz a fonte e quando foi conferida; o histórico fica no Git e a `carga_fca` anota o SHA-256 da tabela no `.json` dos tickers e dos emissores.

| Coluna | O que é | Unidade |
|---|---|---|
| `codigo` | Código de negociação na B3 (BPAC11) | texto |
| `cnpj` | CNPJ da companhia, como no FCA | texto |
| `empresa` | Nome da companhia no FCA | texto |
| `valor_mobiliario` | Tipo do papel (units, ações ordinárias...) | texto |
| `isin` | ISIN do papel nas carteiras dos fundos (a prova do emissor) | texto |
| `primeiro_no_cda` | Primeiro mês em que o código aparece nas carteiras | data (dia) |
| `ultimo_no_cda` | Último mês em que o código aparece nas carteiras | data (dia) |
| `codigo_no_fca` | O que a empresa escreveu no lugar do código | texto |
| `observacao` | Nota da conferência | texto |
| `fonte` | De onde veio cada parte da ligação | texto |
| `conferido_em` | Dia da conferência | data (dia) |

## `anac_estatistico`

Estatístico do transporte aéreo da ANAC por empresa, mês e par de aeroportos (passageiros, carga, assentos, ASK, RPK, combustível...), desde 2000, no formato da fonte. A chave da empresa é a sigla, a mesma da B13 (empresa ↔ série)

- **Fonte:** ANAC: dados estatísticos do transporte aéreo (Dados_Estatisticos.csv)
- **Licença:** CC BY (dados abertos da ANAC no dados.gov.br; citar a ANAC)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (o arquivo inteiro é republicado; a 1ª linha diz "Atualizado em")
- **Atraso de divulgação:** Mensal; a regra de "como era na data" usa o fim do mês + 60 dias (agosto/2026 estava publicado 44 dias depois, medido em 14/10/2026)
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `empresa_sigla`, `aeroporto_de_origem_sigla`, `aeroporto_de_destino_sigla`, `natureza`, `grupo_de_voo`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por ano em `<acervo>/base/setoriais/anac/<ano>.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 do arquivo da ANAC usado (no acervo e no registro de coletas) e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês (último dia) | data (dia) |
| `empresa_sigla` | Empresa sigla, como a ANAC publica | texto |
| `empresa_nome` | Empresa nome, como a ANAC publica | texto |
| `empresa_nacionalidade` | Empresa nacionalidade, como a ANAC publica | texto |
| `aeroporto_de_origem_sigla` | Aeroporto de origem sigla, como a ANAC publica | texto |
| `aeroporto_de_origem_nome` | Aeroporto de origem nome, como a ANAC publica | texto |
| `aeroporto_de_origem_uf` | Aeroporto de origem uf, como a ANAC publica | texto |
| `aeroporto_de_origem_regiao` | Aeroporto de origem regiao, como a ANAC publica | texto |
| `aeroporto_de_origem_pais` | Aeroporto de origem pais, como a ANAC publica | texto |
| `aeroporto_de_origem_continente` | Aeroporto de origem continente, como a ANAC publica | texto |
| `aeroporto_de_destino_sigla` | Aeroporto de destino sigla, como a ANAC publica | texto |
| `aeroporto_de_destino_nome` | Aeroporto de destino nome, como a ANAC publica | texto |
| `aeroporto_de_destino_uf` | Aeroporto de destino uf, como a ANAC publica | texto |
| `aeroporto_de_destino_regiao` | Aeroporto de destino regiao, como a ANAC publica | texto |
| `aeroporto_de_destino_pais` | Aeroporto de destino pais, como a ANAC publica | texto |
| `aeroporto_de_destino_continente` | Aeroporto de destino continente, como a ANAC publica | texto |
| `natureza` | Natureza, como a ANAC publica | texto |
| `grupo_de_voo` | Grupo de voo, como a ANAC publica | texto |
| `passageiros_pagos` | Passageiros pagos no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `passageiros_gratis` | Passageiros gratis no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `carga_paga_kg` | Carga paga kg no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `carga_gratis_kg` | Carga gratis kg no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `correio_kg` | Correio kg no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `ask` | Ask no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `rpk` | Rpk no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `atk` | Atk no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `rtk` | Rtk no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `combustivel_litros` | Combustivel litros no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `distancia_voada_km` | Distancia voada km no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `decolagens` | Decolagens no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `carga_paga_km` | Carga paga km no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `carga_gratis_km` | Carga gratis km no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `correio_km` | Correio km no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `assentos` | Assentos no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `payload` | Payload no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `horas_voadas` | Horas voadas no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `bagagem_kg` | Bagagem kg no mês, como a ANAC publica | número com decimais, na unidade da fonte |
| `atualizado_em` | A data da linha "Atualizado em" do arquivo usado | data (dia) |
| `disponivel_em` | Desde quando o número era público (fim do mês + 60 dias) | data (dia) |

## `anp_vendas`

Vendas de combustíveis pelas distribuidoras (líquidos, GLP e aviação) por mês, agente, produto, origem, destino e mercado, desde 2007, no formato da fonte. A ANP escreve o nome atual da distribuidora também no passado; a ligação à empresa é pela B13

- **Fonte:** ANP: vendas de derivados de petróleo e biocombustíveis por distribuidor (liquidos, glp, aviacao)
- **Licença:** CC BY (dados abertos da ANP no dados.gov.br; citar a ANP)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal
- **Atraso de divulgação:** Mensal; a regra de "como era na data" usa o fim do mês + 60 dias (agosto/2026 estava publicado 44 dias depois, medido em 14/10/2026)
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `grupo`, `agente`, `codigo_do_produto`, `uf_origem`, `uf_destino`, `mercado_destino`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por ano em `<acervo>/base/setoriais/anp/<ano>.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 dos três zips da ANP usados e a versão do código; `arquivo` diz de qual CSV do zip veio a linha (atual ou histórico).

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês (último dia) | data (dia) |
| `grupo` | liquidos, glp ou aviacao (o zip) | texto |
| `agente` | Agente regulado (a distribuidora), como a ANP escreve | texto |
| `codigo_do_produto` | Código do produto na ANP | texto |
| `nome_do_produto` | Nome do produto | texto |
| `descricao_do_produto` | Descrição do produto (vazio no histórico dos líquidos) | texto |
| `codigo_da_embalagem` | Código da embalagem (só GLP) | texto |
| `regiao_origem` | Região de origem | texto |
| `uf_origem` | UF de origem | texto |
| `regiao_destino` | Região de destino | texto |
| `uf_destino` | UF de destino | texto |
| `mercado_destino` | Mercado destinatário (posto, consumidor final...) | texto |
| `quantidade` | Quantidade vendida, na unidade da coluna `unidade` | número com decimais, na unidade da fonte |
| `unidade` | mil m³ ou mil ton, como no cabeçalho da ANP | texto |
| `arquivo` | O CSV do zip de onde veio a linha | texto |
| `disponivel_em` | Desde quando o número era público (fim do mês + 60 dias) | data (dia) |

## `comex_cafe`

Exportações de café por mês, NCM, UF de origem e país de destino, recortadas do Comex Stat (NCMs 09011110, 09011190, 09012100 e 21011110). A NCM não separa arábica de conilon: o `tipo` é sempre `total` e o Espírito Santo (quase só conilon) vai marcado em `proxy_conilon`, sem dividir o volume. Cada coleta do arquivista vira linhas novas (`divulgado_em`), porque o MDIC revisa meses antigos

- **Fonte:** MDIC: Comex Stat, exportação por NCM (EXP_AAAA.csv) e tabela de países
- **Licença:** Dados abertos, uso livre e comercial (MDIC, LAI de 21/10/2026; citar Secex/MDIC)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal
- **Atraso de divulgação:** O mês fecha cerca de 60 dias depois; o `divulgado_em` é a data da coleta do arquivista, não a do MDIC
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `ncm`, `uf_origem`, `codigo_do_pais`, `divulgado_em`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `divulgado_em`
- **Histórico desde:** 2026-10-18 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/commodities/comex_cafe/` (`scripts/carga_cafe.py`; leitor `base/commodities/comex_cafe.py`)
- **Linhagem:** Recorte do `EXP_AAAA.csv` guardado pelo arquivista (fonte `comexstat`); as vias e unidades da aduana são somadas por mês, NCM, UF e país.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês (último dia) | data (dia) |
| `ncm` | NCM do café (8 dígitos) | texto |
| `uf_origem` | UF do produtor/exportador | texto |
| `codigo_do_pais` | Código do país de destino no Comex | texto |
| `pais_destino` | Nome do país de destino | texto |
| `vl_fob_usd` | Valor FOB em dólares | número com decimais, na unidade da fonte |
| `kg_liquido` | Peso líquido em quilos | número com decimais, na unidade da fonte |
| `sacas` | Sacas de 60 kg (quilos líquidos ÷ 60) | número com decimais, na unidade da fonte |
| `tipo` | Sempre `total`: a NCM não separa arábica de conilon | texto |
| `proxy_conilon` | Verdadeiro para o Espírito Santo, pista de conilon (não divide o volume) | verdadeiro ou falso |
| `divulgado_em` | Data da coleta do arquivista em que a linha apareceu (sem olhar o futuro) | data (dia) |

## `ons_geracao`

Geração por usina do ONS, em MWmed por hora, desde 2000, no formato da fonte. A chave da usina é o `id_ons` (o CEG falta em 41% da geração de 09/2026). Sem ligação à empresa: o dono da usina só existe no cadastro de hoje, e aplicá-lo ao passado olharia o futuro

- **Fonte:** ONS: geração por usina em base horária (dados abertos)
- **Licença:** CC BY 4.0 (dados abertos do ONS; citar o ONS)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Diária (um arquivo por ano até 2021, por mês depois)
- **Atraso de divulgação:** O dia seguinte; a regra usa o instante + 2 dias
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `instante`, `id_ons`
- **Três datas:** aconteceu_em = `instante`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por ano em `<acervo>/base/setoriais/ons/<ano>.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada arquivo do ONS do ano e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `instante` | Hora (início) | data (dia) |
| `id_subsistema` | Subsistema (N, NE, S, SE) | texto |
| `subsistema` | Nome do subsistema | texto |
| `uf` | UF da usina | texto |
| `modalidade_de_operacao` | Modalidade de operação (tipo I, II...) | texto |
| `tipo_de_usina` | Hidrelétrica, térmica, eólica, fotovoltaica... | texto |
| `combustivel` | Combustível ou fonte | texto |
| `usina` | Nome da usina, como o ONS escreve | texto |
| `id_ons` | Código da usina no ONS (a chave) | texto |
| `ceg` | Código da usina na ANEEL (vazio quando o ONS não informa) | texto |
| `geracao_mwmed` | Geração na hora, em MWmed | número com decimais, na unidade da fonte |
| `disponivel_em` | Desde quando o número era público (instante + 2 dias) | data (dia) |

## `ccee_pld`

PLD (preço de liquidação das diferenças) da CCEE, em R$/MWh, por submercado: por hora e por dia desde 01/2021, por mês desde 2001 e, de 06/2001 a 12/2020, por semana e patamar de carga (`semana_por_patamar`: o arquivo horário da CCEE desses anos não é horário, e a fonte não rotula o patamar; a posição entre as linhas repetidas vai em `ordem`). A média do dia e a do mês são as que a CCEE publica, não recalculadas aqui. Sem ligação à empresa: é o preço de um mercado, não de um agente

- **Fonte:** CCEE: PLD horário, média diária e média mensal (dados abertos)
- **Licença:** CC BY 4.0 (dados abertos da CCEE; citar a CCEE)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Diária (a CCEE republica o arquivo do ano a cada dia útil)
- **Atraso de divulgação:** O preço do dia sai no dia anterior e a regra usa o dia + 1; a média do mês vale a partir de 2 dias depois do fim do mês; a semana, 7 dias depois do dia que a fonte marca
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `granularidade`, `submercado`, `referencia`, `ordem`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por ano em `<acervo>/base/setoriais/ccee/<ano>.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada arquivo da CCEE lido e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `granularidade` | `hora`, `dia`, `mes` ou `semana_por_patamar` | texto |
| `submercado` | Sudeste, Sul, Nordeste ou Norte, como a CCEE escreve | texto |
| `referencia` | Início do período a que o preço se refere (hora, dia, mês ou semana) | data e hora (UTC) |
| `competencia` | Mês (último dia) | data (dia) |
| `ordem` | Posição entre as linhas da fonte que repetem a mesma referência (1 se única) | número inteiro |
| `periodo_de_comercializacao` | Hora do mês (1 a 744) na fonte; vazio nas outras granularidades | número inteiro |
| `pld` | Preço em R$/MWh | número com decimais, na unidade da fonte |
| `disponivel_em` | Desde quando o número era público (ver o atraso) | data (dia) |

## `ons_restricao`

Restrição de geração eólica e solar do ONS (curtailment): quanto cada usina ou conjunto deixou de gerar por ordem do operador, uma linha por usina e hora (a fonte traz uma leitura a cada 30 minutos; aqui, a média das duas). Eólica desde 10/2021, fotovoltaica desde 04/2024. Hora sem restrição fica com a energia não realizada vazia (vazio não é zero). O ONS fecha a apuração depois: a revisão de uma hora passada vira linha nova, que só vale desde o dia em que foi vista (`base/setoriais/revisoes.py::como_era_em`). O dono da usina não vem no arquivo: a ligação à empresa é pelo agente operador, pelo nome exato do agente na B13

- **Fonte:** ONS: restrição de operação por constrained-off de usinas eólicas e fotovoltaicas (dados abertos)
- **Licença:** CC BY 4.0 (dados abertos do ONS; citar o ONS)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (o ONS acrescenta e revisa os arquivos de meses passados)
- **Atraso de divulgação:** O instante + 2 dias (o mesmo da geração por usina)
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `instante`, `tipo`, `id_ons`, `visto_em`
- **Três datas:** aconteceu_em = `instante`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por tipo e mês em `<acervo>/base/setoriais/ons_restricao/<tipo>_<ano>_<mês>.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `.json` de cada arquivo guarda o endereço e o SHA-256 de cada baixada (uma por revisão) e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `instante` | Hora (início) | data e hora (UTC) |
| `tipo` | `eolica` ou `fotovoltaica` | texto |
| `id_subsistema` | Subsistema (N, NE, S, SE) | texto |
| `uf` | UF da usina | texto |
| `usina` | Nome da usina ou do conjunto, como o ONS escreve | texto |
| `id_ons` | Código da usina ou conjunto no ONS (a chave) | texto |
| `ceg` | Código na ANEEL (vazio nos conjuntos) | texto |
| `agente_operador` | Agente operador (liga à empresa pela B13) | texto |
| `geracao_mwmed` | Geração verificada, em MWmed (numa hora, igual a MWh) | número com decimais, na unidade da fonte |
| `referencia_mwmed` | Geração de referência (o que a usina geraria sem a restrição), MWmed | número com decimais, na unidade da fonte |
| `referencia_final_mwmed` | Referência final, depois do fechamento da apuração, MWmed | número com decimais, na unidade da fonte |
| `disponibilidade_mwmed` | Potência disponível, MWmed | número com decimais, na unidade da fonte |
| `nao_realizada_mwmed` | Energia que deixou de ser gerada por ordem do operador, MWmed (vazio sem restrição) | número com decimais, na unidade da fonte |
| `minutos_restricao` | Minutos de restrição na hora (soma das leituras; vazio sem restrição) | número inteiro |
| `razao_da_restricao` | Código da razão da restrição (a primeira da hora) | texto |
| `origem_da_restricao` | Código da origem da restrição (a primeira da hora) | texto |
| `leituras` | Quantas leituras da fonte entraram na linha | número inteiro |
| `disponivel_em` | Desde quando o número era público (instante + 2 dias) | data (dia) |
| `visto_em` | Dia da coleta em que este valor apareceu (a revisão vale desde aí) | data (dia) |

## `ons_capacidade`

Capacidade instalada do ONS, uma linha por unidade geradora: potência efetiva (MW), proprietário, operador, entrada em teste, entrada em operação e desativação. É a foto do cadastro de hoje (captura de 14/10/2026), não uma série: a unidade vale desde a entrada em operação, e a potência de hoje vale desde a entrada (mudanças de potência anteriores à primeira coleta não aparecem; cada coleta que traz outro valor entra como revisão). A desativação é só uma data na linha: a unidade não some do passado. O proprietário liga à empresa pelo nome exato do agente na B13

- **Fonte:** ONS: capacidade instalada de geração (dados abertos)
- **Licença:** CC BY 4.0 (dados abertos do ONS; citar o ONS)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (o ONS regera o cadastro inteiro)
- **Atraso de divulgação:** A regra usa a data de entrada em operação (ou em teste, quando falta)
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cod_equipamento`, `visto_em`
- **Três datas:** aconteceu_em = `entrada_em_operacao`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/setoriais/ons_capacidade/capacidade.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `capacidade.json` guarda o endereço e o SHA-256 de cada baixada do cadastro e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `id_subsistema` | Subsistema (N, NE, S, SE) | texto |
| `uf` | UF da usina | texto |
| `modalidade_de_operacao` | Modalidade de operação (tipo I, II...) | texto |
| `proprietario` | Agente proprietário, como o ONS escreve (liga à empresa pela B13) | texto |
| `operador` | Agente operador | texto |
| `tipo_de_usina` | Hidrelétrica, térmica, eólica, fotovoltaica... | texto |
| `usina` | Nome da usina | texto |
| `ceg` | Código na ANEEL | texto |
| `unidade_geradora` | Nome da unidade geradora | texto |
| `cod_equipamento` | Código do equipamento no ONS (a chave) | texto |
| `numero_da_unidade` | Número da unidade na usina | texto |
| `combustivel` | Combustível ou fonte | texto |
| `entrada_em_teste` | Data da entrada em teste | data (dia) |
| `entrada_em_operacao` | Data da entrada em operação | data (dia) |
| `desativada_em` | Data da desativação (vazio: em operação) | data (dia) |
| `potencia_efetiva_mw` | Potência efetiva da unidade, em MW | número com decimais, na unidade da fonte |
| `disponivel_em` | Desde quando a unidade existe para quem pergunta (entrada em operação) | data (dia) |
| `visto_em` | Dia da coleta em que este valor apareceu (a revisão vale desde aí) | data (dia) |

## `anp_concessionarios`

Concessionários da ANP: uma linha por contrato de exploração e produção de petróleo e gás e por sócio do consórcio, com a fase (exploração, avaliação ou produção), a bacia, o ambiente (terra ou mar), o CNPJ do sócio, a participação em pontos percentuais e a marca de quem opera. É a foto do dia da coleta, sem data própria: o primeiro valor vale desde a coleta que o trouxe e uma mudança de sócio, de fase ou de participação entra como linha nova, desde o dia em que foi vista (o que mudou antes da primeira coleta não aparece). O CNPJ vem na fonte (o leitor recoloca o zero à esquerda): a ligação à empresa é por ele, sem comparar nomes **Sem pessoa pela raiz:** toda raiz de CNPJ desta tabela existe na `cnpj_empresas_pj`, que só tem pessoa jurídica; CNPJ que não tem 14 dígitos conta como fora. A prova cobre quem a linha descreve, não o texto livre que ela carrega (o assunto de um evento, por exemplo). A conferência é `scripts/conferir_sem_pessoa.py`, rodada antes de cada concessão do piloto

- **Fonte:** ANP: relação de concessionários (dados abertos)
- **Licença:** CC BY (dados abertos da ANP no dados.gov.br; citar a ANP)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a ANP regera o arquivo inteiro)
- **Atraso de divulgação:** Sem data própria: vale desde o dia da coleta do arquivista
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `numero_do_contrato`, `cnpj`, `visto_em`
- **Três datas:** aconteceu_em = `disponivel_em`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/setoriais/anp_concessionarios/concessionarios.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `concessionarios.json` guarda o endereço e o SHA-256 de cada baixada do arquivo e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `bid` | Código da rodada de licitação (BID) do contrato | texto |
| `numero_do_contrato` | Número do contrato na ANP (a chave, com o CNPJ) | texto |
| `fase` | Exploração, Avaliação ou Produção | texto |
| `nome_fantasia` | Nome do campo ou bloco | texto |
| `bacia` | Bacia sedimentar | texto |
| `cnpj` | CNPJ do sócio, com 14 dígitos (liga à empresa) | texto |
| `empresa` | Nome do sócio, sem o prefixo de operador | texto |
| `operador` | Verdadeiro na linha de quem opera o contrato | verdadeiro ou falso |
| `participacao_pct` | Participação do sócio no contrato, em pontos percentuais (0 a 100) | número com decimais, na unidade da fonte |
| `ambiente` | Terra ou Mar | texto |
| `disponivel_em` | Desde quando o número era público (o dia da coleta que o trouxe) | data (dia) |
| `visto_em` | Dia da coleta em que este valor apareceu (a mudança vale desde aí) | data (dia) |

## `antt_siade`

Produção ferroviária da ANTT (SIADE): toneladas úteis (TU) e tonelada-quilômetro útil (TKU) por mês, ferrovia, mercadoria e par de estações (origem e destino), de 2006 em diante. A ferrovia vem como sigla (EFC, MRS, RMS...) e liga à empresa pela B13, na chave exata. A ANTT pode revisar um mês passado: a revisão vira linha nova, desde o dia em que foi vista

- **Fonte:** ANTT: SIADE, produção por origem e destino (dados abertos)
- **Licença:** CC BY (dados abertos da ANTT; citar a ANTT)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (um CSV por ano)
- **Atraso de divulgação:** Fim do mês + 60 dias, com folga: a ANTT não diz quando publica e ainda não foi medido (só uma captura, 14/10/2026); pode atrasar um número, nunca adiantar
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `ferrovia`, `mercadoria`, `estacao_de_origem`, `estacao_de_destino`, `visto_em`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por ano em `<acervo>/base/setoriais/antt_siade/<ano>.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do CSV do ano e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês (último dia) | data (dia) |
| `ferrovia` | Sigla da ferrovia na ANTT (liga à empresa pela B13) | texto |
| `mercadoria` | Mercadoria, como a ANTT escreve | texto |
| `estacao_de_origem` | Estação de origem | texto |
| `uf_de_origem` | UF da estação de origem | texto |
| `estacao_de_destino` | Estação de destino | texto |
| `uf_de_destino` | UF da estação de destino | texto |
| `toneladas_uteis` | Toneladas úteis transportadas (TU) | número com decimais, na unidade da fonte |
| `tku` | Tonelada-quilômetro útil (TKU) | número com decimais, na unidade da fonte |
| `disponivel_em` | Desde quando o número era público (fim do mês + 60 dias) | data (dia) |
| `visto_em` | Dia da coleta em que este valor apareceu (a revisão vale desde aí) | data (dia) |

## `comex_preco_medio`

Preço médio de comércio exterior do Comex Stat, em US$ por quilo (valor FOB ÷ quilo líquido), por fluxo (exportação ou importação), mês, NCM e URF (porto, aeroporto ou posto de fronteira). A fonte não publica preço: é conta nossa sobre os CSVs de NCM, somando vias, países e UFs de cada linha. Quilo zero deixa o preço vazio. Dados abertos de uso livre, inclusive comercial (resposta do MDIC em 21/10/2026): citar Secex/MDIC e dizer que o preço é elaboração própria. O MDIC revisa meses passados: a revisão vira linha nova, desde o dia em que foi vista. O nome da URF está em `URF.csv`, outra tabela da fonte

- **Fonte:** MDIC: Comex Stat, exportação e importação por NCM (EXP_AAAA.csv e IMP_AAAA.csv)
- **Licença:** Dados abertos, uso livre e comercial (MDIC, LAI de 21/10/2026; citar Secex/MDIC)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (um CSV por ano e por fluxo)
- **Atraso de divulgação:** Fim do mês + 60 dias, com folga sobre a divulgação do MDIC (nos primeiros dias úteis do mês seguinte); pode atrasar um número, nunca adiantar
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `fluxo`, `competencia`, `ncm`, `urf`, `visto_em`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por fluxo e ano em `<acervo>/base/setoriais/comex_preco_medio/<fluxo>_<ano>.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `.json` de cada arquivo guarda o endereço e o SHA-256 de cada baixada do CSV e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `fluxo` | `exportacao` ou `importacao` | texto |
| `competencia` | Mês (último dia) | data (dia) |
| `ncm` | NCM (8 dígitos) | texto |
| `urf` | Código da URF (unidade da Receita: porto, aeroporto ou posto) | texto |
| `vl_fob_usd` | Valor FOB somado, em US$ | número com decimais, na unidade da fonte |
| `kg_liquido` | Quilo líquido somado | número com decimais, na unidade da fonte |
| `preco_usd_por_kg` | Valor FOB ÷ quilo líquido, em US$ por quilo (vazio com quilo zero) | número com decimais, na unidade da fonte |
| `disponivel_em` | Desde quando o número era público (fim do mês + 60 dias) | data (dia) |
| `visto_em` | Dia da coleta em que este valor apareceu (a revisão vale desde aí) | data (dia) |

## `comex_urf`

Nome de cada URF (unidade da Receita: porto, aeroporto ou posto) do Comex Stat, para ler o código que `comex_preco_medio` guarda (coluna `urf`). Tabela de apoio da fonte (`URF.csv`), sem data própria: o primeiro valor vale desde o dia da coleta, e um nome que o MDIC mude depois vira linha nova, desde o dia em que foi visto. Dados abertos de uso livre, inclusive comercial (resposta do MDIC em 21/10/2026): citar Secex/MDIC

- **Fonte:** MDIC: Comex Stat, tabela auxiliar `URF.csv`
- **Licença:** Dados abertos, uso livre e comercial (MDIC, LAI de 21/10/2026; citar Secex/MDIC)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Quando o MDIC muda a tabela (coletada junto com os CSVs de NCM, semanal)
- **Atraso de divulgação:** Sem data própria: vale desde o dia da coleta do arquivista
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `urf`, `visto_em`
- **Três datas:** aconteceu_em = `disponivel_em`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/setoriais/comex_urf/urf.parquet` (`scripts/carga_setoriais.py`; leitor `base/setoriais/comex_tabelas.py`)
- **Linhagem:** O `.json` do arquivo guarda o endereço e o SHA-256 de cada baixada do CSV e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `urf` | Código da URF, o mesmo de `comex_preco_medio.urf` | texto |
| `nome` | Nome da unidade, sem o código repetido na frente (`IRF ILHEUS`) | texto |
| `disponivel_em` | Desde quando o nome era público (o dia da coleta que o trouxe) | data (dia) |
| `visto_em` | Dia da coleta em que este valor apareceu (a revisão vale desde aí) | data (dia) |

## `comex_via`

Nome de cada via de transporte do Comex Stat, para ler o código que `comex_preco_medio` guarda (a via de transporte dos CSVs do MDIC). Tabela de apoio da fonte (`VIA.csv`), sem data própria: o primeiro valor vale desde o dia da coleta, e um nome que o MDIC mude depois vira linha nova, desde o dia em que foi visto. Dados abertos de uso livre, inclusive comercial (resposta do MDIC em 21/10/2026): citar Secex/MDIC

- **Fonte:** MDIC: Comex Stat, tabela auxiliar `VIA.csv`
- **Licença:** Dados abertos, uso livre e comercial (MDIC, LAI de 21/10/2026; citar Secex/MDIC)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Quando o MDIC muda a tabela (coletada junto com os CSVs de NCM, semanal)
- **Atraso de divulgação:** Sem data própria: vale desde o dia da coleta do arquivista
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `via`, `visto_em`
- **Três datas:** aconteceu_em = `disponivel_em`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/setoriais/comex_via/via.parquet` (`scripts/carga_setoriais.py`; leitor `base/setoriais/comex_tabelas.py`)
- **Linhagem:** O `.json` do arquivo guarda o endereço e o SHA-256 de cada baixada do CSV e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `via` | Código da via (`01` marítima, `04` aérea...) | texto |
| `nome` | Nome da via, como o MDIC escreve (`MARITIMA`) | texto |
| `disponivel_em` | Desde quando o nome era público (o dia da coleta que o trouxe) | data (dia) |
| `visto_em` | Dia da coleta em que este valor apareceu (a revisão vale desde aí) | data (dia) |

## `aneel_samp`

Mercado das distribuidoras de energia (SAMP da ANEEL) por distribuidora, mês, classe de consumo, modalidade e posto tarifário: consumidores, energia (kWh) e receita (R$), desde 2003, no formato da fonte. As linhas de cada consumidor livre vêm somadas (sem CPF nem nome). Uma linha por valor diferente de cada chave: a revisão de um mês passado vira linha nova, que só vale desde o dia em que foi vista (`base/setoriais/revisoes.py::como_era_em`). O que mudou antes da primeira coleta (10/2026) não aparece **Sem pessoa pela raiz:** toda raiz de CNPJ desta tabela existe na `cnpj_empresas_pj`, que só tem pessoa jurídica; CNPJ que não tem 14 dígitos conta como fora. A prova cobre quem a linha descreve, não o texto livre que ela carrega (o assunto de um evento, por exemplo). A conferência é `scripts/conferir_sem_pessoa.py`, rodada antes de cada concessão do piloto

- **Fonte:** ANEEL: SAMP, mercado de distribuição (dados abertos, um Parquet por ano)
- **Licença:** ODbL (dados abertos da ANEEL; citar). SAMP sem CPF e nome do consumidor
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal (a ANEEL regera todos os anos a cada mês, perto do dia 15)
- **Atraso de divulgação:** Medido: o SAMP de 15/09/2026 tinha julho completo (46 dias) e agosto pela metade; a regra usa o fim do mês + 60 dias
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `cnpj`, `tipo_de_mercado`, `modalidade_tarifaria`, `subgrupo_tarifario`, `classe_de_consumo`, `subclasse_de_consumo`, `detalhe_do_consumidor`, `nucleo_ceg`, `posto_tarifario`, `opcao_de_energia`, `detalhe_do_mercado`, `visto_em`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por ano em `<acervo>/base/setoriais/aneel/<ano>.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do ano usada (uma por revisão) e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês (último dia) | data (dia) |
| `cnpj` | CNPJ da distribuidora (14 dígitos; a chave da B13) | texto |
| `sigla` | Sigla da distribuidora, como a ANEEL escreve | texto |
| `distribuidora` | Nome da distribuidora, como a ANEEL escreve | texto |
| `tipo_de_mercado` | Regular, refaturamento, compensação de geração distribuída... | texto |
| `modalidade_tarifaria` | Convencional, azul, verde, branca... | texto |
| `subgrupo_tarifario` | A1 a A4, AS, B1 a B4 | texto |
| `classe_de_consumo` | Residencial, industrial, comercial, rural... | texto |
| `subclasse_de_consumo` | Subclasse (baixa renda, cooperativa...) | texto |
| `detalhe_do_consumidor` | Detalhe do consumidor (fonte incentivada...) | texto |
| `nucleo_ceg` | Núcleo do CEG da usina, quando há (texto inteiro) | texto |
| `posto_tarifario` | Ponta, fora ponta, intermediário | texto |
| `opcao_de_energia` | Cativo, livre, suprimento, distribuição | texto |
| `detalhe_do_mercado` | O que o valor mede: número de consumidores, energia (kWh), receita (R$), desconto (%)... | texto |
| `valor` | O valor, na unidade do `detalhe_do_mercado` (soma das linhas; média nos percentuais) | número com decimais, na unidade da fonte |
| `linhas_somadas` | Quantas linhas da fonte (uma por acessante) foram somadas | número com decimais, na unidade da fonte |
| `gerado_em` | A data de geração do arquivo pela ANEEL, na primeira vez que o valor foi visto | data (dia) |
| `disponivel_em` | Desde quando o número era público (fim do mês + 60 dias; a revisão, desde o dia em que foi vista) | data (dia) |
| `visto_em` | O dia da baixada do arquivista que trouxe este valor pela primeira vez | data (dia) |

## `anatel_acessos`

Acessos de banda larga fixa, telefonia móvel e TV por assinatura da Anatel por prestadora (CNPJ), mês e UF, desde 2005 (móvel), 2007 (banda larga) e 2012 (TV), somados os municípios. Na móvel de 2005 a 2018 a Anatel publica duas visões dos mesmos acessos (`recorte` modalidade ou tecnologia): somar as duas conta tudo duas vezes. Uma linha por valor diferente de cada chave: a revisão de um mês passado vira linha nova, que só vale desde o dia em que foi vista (`base/setoriais/revisoes.py::como_era_em`). O que mudou antes da primeira coleta (10/2026) não aparece

- **Fonte:** Anatel: painéis de dados, acessos (CSVs "_Colunas" de dentro dos ZIPs)
- **Licença:** CC BY (dados abertos da Anatel no dados.gov.br; citar a Anatel)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal
- **Atraso de divulgação:** Agosto/2026 estava publicado em 14/10/2026; a regra usa o fim do mês + 60 dias
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `servico`, `recorte`, `cnpj`, `uf`, `regiao_pgo`, `codigo_nacional`, `modalidade_de_cobranca`, `tecnologia`, `geracao`, `tipo_de_pessoa`, `tipo_de_produto`, `faixa_de_velocidade`, `meio_de_acesso`, `tipo_de_acesso_tv`, `visto_em`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por CSV da Anatel em `<acervo>/base/setoriais/anatel/<nome do CSV>.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `.json` de cada CSV guarda o endereço (`zip#csv`) e o SHA-256 de cada baixada usada e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês (último dia) | data (dia) |
| `servico` | banda_larga_fixa, telefonia_movel ou tv_por_assinatura | texto |
| `recorte` | completo; na móvel de 2005 a 2018, modalidade ou tecnologia | texto |
| `cnpj` | CNPJ da prestadora (14 dígitos; a chave da B13) | texto |
| `empresa` | Nome da prestadora, como a Anatel escreve | texto |
| `grupo_economico` | Grupo econômico, como a Anatel escreve | texto |
| `porte_da_prestadora` | Grande ou pequeno porte | texto |
| `uf` | UF | texto |
| `regiao_pgo` | Região do plano geral de outorgas (móvel até 2009) | texto |
| `codigo_nacional` | DDD (móvel) | texto |
| `modalidade_de_cobranca` | Pré-pago ou pós-pago (móvel) | texto |
| `tecnologia` | Tecnologia (FTTH, cabo, GSM, LTE, DTH...) | texto |
| `geracao` | Geração da tecnologia móvel (2G a 5G) | texto |
| `tipo_de_pessoa` | Assinante pessoa física ou jurídica | texto |
| `tipo_de_produto` | Tipo de produto (internet, voz, M2M...) | texto |
| `faixa_de_velocidade` | Faixa de velocidade contratada (banda larga) | texto |
| `meio_de_acesso` | Fibra, cabo coaxial, rádio, satélite... | texto |
| `tipo_de_acesso_tv` | Tipo de acesso de TV por assinatura | texto |
| `acessos` | Acessos em serviço no fim do mês, somados os municípios da UF | número com decimais, na unidade da fonte |
| `arquivo` | O CSV da Anatel de onde veio a linha | texto |
| `disponivel_em` | Desde quando o número era público (fim do mês + 60 dias; a revisão, desde o dia em que foi vista) | data (dia) |
| `visto_em` | O dia da baixada do arquivista que trouxe este valor pela primeira vez | data (dia) |

## `ans_beneficiarios`

Beneficiários de planos de saúde por operadora (registro ANS), mês, modalidade, cobertura, vigência do plano, contratação e financiamento, desde 2017, no formato da fonte. Uma linha por valor diferente de cada chave: a revisão de um mês passado vira linha nova, que só vale desde o dia em que foi vista (`base/setoriais/revisoes.py::como_era_em`). O que mudou antes da primeira coleta (10/2026) não aparece

- **Fonte:** ANS: beneficiários por operadora e carteira (Beneficiarios_operadora_e_carteira.csv)
- **Licença:** CC BY (dados abertos da ANS no dados.gov.br; citar a ANS)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Sem data fixa: o arquivo de 08/08/2026 ainda era o mesmo em 14/10/2026
- **Atraso de divulgação:** Medido: o arquivo de 08/08/2026 trazia até junho/2026 (39 dias); a regra usa o fim do mês + 90 dias
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `cd_operadora`, `modalidade`, `cobertura`, `vigencia_do_plano`, `contratacao`, `financiamento`, `visto_em`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por ano em `<acervo>/base/setoriais/ans/<ano>.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do arquivo usada (uma por revisão) e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês (último dia) | data (dia) |
| `cd_operadora` | Registro da operadora na ANS (a chave da B13, fonte `ans-beneficiarios`) | texto |
| `modalidade` | Medicina de grupo, cooperativa médica, seguradora... | texto |
| `cobertura` | Médico-hospitalar ou odontológico | texto |
| `vigencia_do_plano` | P (plano posterior à Lei 9.656) ou A (anterior) | texto |
| `contratacao` | Individual ou familiar, coletivo empresarial, por adesão... | texto |
| `financiamento` | Pré-estabelecido, pós-estabelecido... | texto |
| `beneficiarios` | Beneficiários no mês | número com decimais, na unidade da fonte |
| `base_de` | O mês da extração da ANS (`ID_CMPT`) na primeira vez que o valor foi visto | data (dia) |
| `disponivel_em` | Desde quando o número era público (fim do mês + 90 dias; a revisão, desde o dia em que foi vista) | data (dia) |
| `visto_em` | O dia da baixada do arquivista que trouxe este valor pela primeira vez | data (dia) |

## `fre_conselho`

Conselho de administração, diretoria e conselho fiscal por companhia e versão do FRE: quantos membros, suplentes, independentes, eleitos pelo controlador e pelos minoritários, desde 2010. Só contagens: nome, CPF, nascimento e currículo dos administradores nem são lidos

- **Fonte:** CVM: formulário de referência (FRE), dados abertos
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual, com reapresentações (a CVM reescreve os anos antigos)
- **Atraso de divulgação:** A entrega do FRE: `conhecido_em` é o DT_RECEB da versão
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`, `orgao`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fre_conselho/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia (como a CVM escreve) | texto |
| `referencia` | Data de referência do FRE | data (dia) |
| `versao` | Versão do FRE | número com decimais, na unidade da fonte |
| `id_documento` | Identificador do documento na CVM | texto |
| `orgao` | Órgão da administração, como a CVM escreve | texto |
| `membros` | Quantas pessoas no órgão (ou no comitê) | número com decimais, na unidade da fonte |
| `suplentes` | Quantos suplentes | número com decimais, na unidade da fonte |
| `independentes` | Quantos conselheiros independentes (pelo cargo informado) | número com decimais, na unidade da fonte |
| `eleitos_pelo_controlador` | Quantos eleitos pelo controlador (`Eleito_Controlador` = S) | número com decimais, na unidade da fonte |
| `eleitos_por_minoritarios` | Quantos eleitos pelos minoritários ordinaristas (pelo cargo) | número com decimais, na unidade da fonte |
| `eleitos_por_preferencialistas` | Quantos eleitos pelos preferencialistas (pelo cargo) | número com decimais, na unidade da fonte |
| `mandatos_consecutivos_medio` | Média de mandatos consecutivos (vazio quando a CVM não informa) | número com decimais, na unidade da fonte |
| `participacao_em_reunioes_media` | Média do % de participação em reuniões (vazio quando não informado) | número com decimais, na unidade da fonte |
| `conhecido_em` | Entrega desta versão do FRE à CVM (DT_RECEB): como era na data | data (dia) |

## `fre_comites`

Comitês (auditoria, risco, remuneração...) por companhia e versão do FRE: quantos membros e suplentes, desde 2010. Só contagens, sem pessoas

- **Fonte:** CVM: formulário de referência (FRE), dados abertos
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual, com reapresentações (a CVM reescreve os anos antigos)
- **Atraso de divulgação:** A entrega do FRE: `conhecido_em` é o DT_RECEB da versão
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`, `tipo_de_comite`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fre_comites/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia (como a CVM escreve) | texto |
| `referencia` | Data de referência do FRE | data (dia) |
| `versao` | Versão do FRE | número com decimais, na unidade da fonte |
| `id_documento` | Identificador do documento na CVM | texto |
| `tipo_de_comite` | Tipo de comitê (auditoria, risco, remuneração...) | texto |
| `membros` | Quantas pessoas no órgão (ou no comitê) | número com decimais, na unidade da fonte |
| `suplentes` | Quantos suplentes | número com decimais, na unidade da fonte |
| `conhecido_em` | Entrega desta versão do FRE à CVM (DT_RECEB): como era na data | data (dia) |

## `fre_remuneracao`

Remuneração total da administração por órgão e exercício (salário, benefícios, bônus, participação nos resultados, ações...), como a CVM publica no FRE, desde 2010, sem os textos livres

- **Fonte:** CVM: formulário de referência (FRE), dados abertos
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual, com reapresentações (a CVM reescreve os anos antigos)
- **Atraso de divulgação:** A entrega do FRE: `conhecido_em` é o DT_RECEB da versão
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`, `fim_do_exercicio`, `orgao`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fre_remuneracao/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia (como a CVM escreve) | texto |
| `referencia` | Data de referência do FRE | data (dia) |
| `versao` | Versão do FRE | número com decimais, na unidade da fonte |
| `id_documento` | Identificador do documento na CVM | texto |
| `inicio_do_exercicio` | Início do exercício social | data (dia) |
| `fim_do_exercicio` | Fim do exercício social | data (dia) |
| `orgao` | Órgão da administração, como a CVM escreve | texto |
| `total_remuneracao` | Como a CVM publica (`Total_Remuneracao`) | número com decimais, na unidade da fonte |
| `membros` | Quantas pessoas no órgão (ou no comitê) | número com decimais, na unidade da fonte |
| `total_do_orgao` | Como a CVM publica (`Total_Remuneracao_Orgao`) | número com decimais, na unidade da fonte |
| `membros_remunerados` | Como a CVM publica (`Numero_Membros_Remunerados`) | número com decimais, na unidade da fonte |
| `salario` | Como a CVM publica (`Salario`) | número com decimais, na unidade da fonte |
| `beneficios` | Como a CVM publica (`Beneficios_Diretos_Indiretos`) | número com decimais, na unidade da fonte |
| `participacao_em_comites` | Como a CVM publica (`Participacoes_Comites`) | número com decimais, na unidade da fonte |
| `outros_fixos` | Como a CVM publica (`Outros_Valores_Fixos`) | número com decimais, na unidade da fonte |
| `bonus` | Como a CVM publica (`Bonus`) | número com decimais, na unidade da fonte |
| `participacao_nos_resultados` | Como a CVM publica (`Participacao_Resultados`) | número com decimais, na unidade da fonte |
| `participacao_em_reunioes` | Como a CVM publica (`Participacao_Reunioes`) | número com decimais, na unidade da fonte |
| `outros_variaveis` | Como a CVM publica (`Outros_Valores_Variaveis`) | número com decimais, na unidade da fonte |
| `comissoes` | Como a CVM publica (`Comissoes`) | número com decimais, na unidade da fonte |
| `pos_emprego` | Como a CVM publica (`Pos_emprego`) | número com decimais, na unidade da fonte |
| `cessacao_do_cargo` | Como a CVM publica (`Cessacao_Cargo`) | número com decimais, na unidade da fonte |
| `baseada_em_acoes` | Como a CVM publica (`Baseada_Acoes`) | número com decimais, na unidade da fonte |
| `conhecido_em` | Entrega desta versão do FRE à CVM (DT_RECEB): como era na data | data (dia) |

## `fre_remuneracao_extremos`

A maior, a menor e a média da remuneração individual por órgão e exercício, como a CVM publica no FRE, desde 2010 (sem a observação em texto livre)

- **Fonte:** CVM: formulário de referência (FRE), dados abertos
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual, com reapresentações (a CVM reescreve os anos antigos)
- **Atraso de divulgação:** A entrega do FRE: `conhecido_em` é o DT_RECEB da versão
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`, `fim_do_exercicio`, `orgao`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fre_remuneracao_extremos/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia (como a CVM escreve) | texto |
| `referencia` | Data de referência do FRE | data (dia) |
| `versao` | Versão do FRE | número com decimais, na unidade da fonte |
| `id_documento` | Identificador do documento na CVM | texto |
| `inicio_do_exercicio` | Início do exercício social | data (dia) |
| `fim_do_exercicio` | Fim do exercício social | data (dia) |
| `orgao` | Órgão da administração, como a CVM escreve | texto |
| `membros` | Quantas pessoas no órgão (ou no comitê) | número com decimais, na unidade da fonte |
| `membros_remunerados` | Como a CVM publica (`Numero_Membros_Remunerados`) | número com decimais, na unidade da fonte |
| `maior` | Como a CVM publica (`Valor_Maior_Remuneracao`) | número com decimais, na unidade da fonte |
| `menor` | Como a CVM publica (`Valor_Menor_Remuneracao`) | número com decimais, na unidade da fonte |
| `media` | Como a CVM publica (`Valor_Medio_Remuneracao`) | número com decimais, na unidade da fonte |
| `conhecido_em` | Entrega desta versão do FRE à CVM (DT_RECEB): como era na data | data (dia) |

## `fre_diversidade`

Gênero, raça e pessoas com deficiência na administração por órgão, como a CVM publica no FRE de 2023 em diante (contagens; vazio nos anos anteriores)

- **Fonte:** CVM: formulário de referência (FRE), dados abertos
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual, com reapresentações (a CVM reescreve os anos antigos)
- **Atraso de divulgação:** A entrega do FRE: `conhecido_em` é o DT_RECEB da versão
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`, `orgao`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fre_diversidade/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia (como a CVM escreve) | texto |
| `referencia` | Data de referência do FRE | data (dia) |
| `versao` | Versão do FRE | número com decimais, na unidade da fonte |
| `id_documento` | Identificador do documento na CVM | texto |
| `orgao` | Órgão da administração, como a CVM escreve | texto |
| `genero_feminino` | Como a CVM publica (`genero_feminino`) | número com decimais, na unidade da fonte |
| `genero_masculino` | Como a CVM publica (`genero_masculino`) | número com decimais, na unidade da fonte |
| `genero_nao_binario` | Como a CVM publica (`genero_nao_binario`) | número com decimais, na unidade da fonte |
| `genero_outros` | Como a CVM publica (`genero_outros`) | número com decimais, na unidade da fonte |
| `genero_sem_resposta` | Como a CVM publica (`genero_sem_resposta`) | número com decimais, na unidade da fonte |
| `genero_nao_aplicavel` | Como a CVM publica (`genero_nao_aplicavel`) | texto |
| `raca_amarelo` | Como a CVM publica (`raca_amarelo`) | número com decimais, na unidade da fonte |
| `raca_branco` | Como a CVM publica (`raca_branco`) | número com decimais, na unidade da fonte |
| `raca_preto` | Como a CVM publica (`raca_preto`) | número com decimais, na unidade da fonte |
| `raca_pardo` | Como a CVM publica (`raca_pardo`) | número com decimais, na unidade da fonte |
| `raca_indigena` | Como a CVM publica (`raca_indigena`) | número com decimais, na unidade da fonte |
| `raca_outros` | Como a CVM publica (`raca_outros`) | número com decimais, na unidade da fonte |
| `raca_sem_resposta` | Como a CVM publica (`raca_sem_resposta`) | número com decimais, na unidade da fonte |
| `raca_nao_aplicavel` | Como a CVM publica (`raca_nao_aplicavel`) | texto |
| `pcd_pcd` | Como a CVM publica (`pcd_pcd`) | número com decimais, na unidade da fonte |
| `pcd_nao_pcd` | Como a CVM publica (`pcd_nao_pcd`) | número com decimais, na unidade da fonte |
| `pcd_sem_resposta` | Como a CVM publica (`pcd_sem_resposta`) | número com decimais, na unidade da fonte |
| `pcd_nao_aplicavel` | Como a CVM publica (`pcd_nao_aplicavel`) | texto |
| `conhecido_em` | Entrega desta versão do FRE à CVM (DT_RECEB): como era na data | data (dia) |

## `fre_capital_social`

Capital social de cada FRE (integralizado, subscrito, emitido e autorizado), com as ações ordinárias e preferenciais, as classes e os títulos conversíveis em ação

- **Fonte:** CVM: formulário de referência (FRE), dados abertos
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual, com reapresentações (a CVM reescreve os anos antigos)
- **Atraso de divulgação:** A entrega do FRE: `conhecido_em` é o DT_RECEB da versão
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`, `id_capital_social`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fre_capital_social/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia (como a CVM escreve) | texto |
| `referencia` | Data de referência do FRE | data (dia) |
| `versao` | Versão do FRE | número com decimais, na unidade da fonte |
| `id_documento` | Identificador do documento na CVM | texto |
| `id_capital_social` | Identificador da linha de capital na CVM | texto |
| `tipo_capital` | integralizado, subscrito, emitido ou autorizado (o "Capital ..." da CVM, sem acento) | texto |
| `autorizado_em` | Data da autorização ou aprovação do capital | data (dia) |
| `valor_capital` | Valor do capital | reais (R$), já multiplicado pela escala informada |
| `acoes_ordinarias` | Quantidade de ações ordinárias | ações |
| `acoes_preferenciais` | Quantidade de ações preferenciais | ações |
| `acoes_total` | Quantidade total de ações | ações |
| `acoes_por_classe` | Quantidade por classe, como "Preferencial Classe A=1000; Ordinária Classe A=500" (vazio sem classe declarada) | texto |
| `titulos_conversiveis` | Títulos conversíveis em ação, separados por "; " (sem as condições de conversão, texto livre; vazio quando a companhia diz que não há) | texto |
| `conhecido_em` | Entrega desta versão do FRE à CVM (DT_RECEB): como era na data | data (dia) |

## `fre_empregados`

Empregados por região (recorte `local`) e por posição, liderança ou não (recorte `posicao`), com gênero, raça, faixa etária, PCD e região, como a CVM publica no FRE de 2023 em diante (contagens; vazio nos anos anteriores)

- **Fonte:** CVM: formulário de referência (FRE), dados abertos
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual, com reapresentações (a CVM reescreve os anos antigos)
- **Atraso de divulgação:** A entrega do FRE: `conhecido_em` é o DT_RECEB da versão
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`, `recorte`, `grupo`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`
- **Histórico desde:** 2023-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fre_empregados/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia (como a CVM escreve) | texto |
| `referencia` | Data de referência do FRE | data (dia) |
| `versao` | Versão do FRE | número com decimais, na unidade da fonte |
| `id_documento` | Identificador do documento na CVM | texto |
| `recorte` | `local` (por região) ou `posicao` (liderança ou não) | texto |
| `grupo` | A região (Norte, Nordeste, Centro-Oeste, Sudeste, Sul, Exterior) ou a posição (Liderança, Não-liderança), como a CVM escreve | texto |
| `genero_feminino` | Como a CVM publica (`genero_feminino`) | número com decimais, na unidade da fonte |
| `genero_masculino` | Como a CVM publica (`genero_masculino`) | número com decimais, na unidade da fonte |
| `genero_nao_binario` | Como a CVM publica (`genero_nao_binario`) | número com decimais, na unidade da fonte |
| `genero_outros` | Como a CVM publica (`genero_outros`) | número com decimais, na unidade da fonte |
| `genero_sem_resposta` | Como a CVM publica (`genero_sem_resposta`) | número com decimais, na unidade da fonte |
| `raca_amarelo` | Como a CVM publica (`raca_amarelo`) | número com decimais, na unidade da fonte |
| `raca_branco` | Como a CVM publica (`raca_branco`) | número com decimais, na unidade da fonte |
| `raca_preto` | Como a CVM publica (`raca_preto`) | número com decimais, na unidade da fonte |
| `raca_pardo` | Como a CVM publica (`raca_pardo`) | número com decimais, na unidade da fonte |
| `raca_indigena` | Como a CVM publica (`raca_indigena`) | número com decimais, na unidade da fonte |
| `raca_outros` | Como a CVM publica (`raca_outros`) | número com decimais, na unidade da fonte |
| `raca_sem_resposta` | Como a CVM publica (`raca_sem_resposta`) | número com decimais, na unidade da fonte |
| `idade_ate_30` | Como a CVM publica (`idade_ate_30`) | número com decimais, na unidade da fonte |
| `idade_30_a_50` | Como a CVM publica (`idade_30_a_50`) | número com decimais, na unidade da fonte |
| `idade_acima_50` | Como a CVM publica (`idade_acima_50`) | número com decimais, na unidade da fonte |
| `pcd_sim` | Só no recorte `posicao`: como a CVM publica (`pcd_sim`) | número com decimais, na unidade da fonte |
| `pcd_nao` | Só no recorte `posicao`: como a CVM publica (`pcd_nao`) | número com decimais, na unidade da fonte |
| `pcd_sem_resposta` | Só no recorte `posicao`: como a CVM publica (`pcd_sem_resposta`) | número com decimais, na unidade da fonte |
| `regiao_norte` | Só no recorte `posicao`: como a CVM publica (`regiao_norte`) | número com decimais, na unidade da fonte |
| `regiao_nordeste` | Só no recorte `posicao`: como a CVM publica (`regiao_nordeste`) | número com decimais, na unidade da fonte |
| `regiao_centro_oeste` | Só no recorte `posicao`: como a CVM publica (`regiao_centro_oeste`) | número com decimais, na unidade da fonte |
| `regiao_sudeste` | Só no recorte `posicao`: como a CVM publica (`regiao_sudeste`) | número com decimais, na unidade da fonte |
| `regiao_sul` | Só no recorte `posicao`: como a CVM publica (`regiao_sul`) | número com decimais, na unidade da fonte |
| `regiao_exterior` | Só no recorte `posicao`: como a CVM publica (`regiao_exterior`) | número com decimais, na unidade da fonte |
| `conhecido_em` | Entrega desta versão do FRE à CVM (DT_RECEB): como era na data | data (dia) |

## `fre_distribuicao_capital`

Distribuição do capital de cada FRE (item 15.7): as ações em circulação, o free float (fora o controlador, os administradores e a tesouraria), com a quantidade e o percentual por espécie, e quantos acionistas pessoa física, pessoa jurídica e investidor institucional a companhia declara. Só contagens e percentuais, sem nome nem documento

- **Fonte:** CVM: formulário de referência (FRE), dados abertos
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual, com reapresentações (a CVM reescreve os anos antigos)
- **Atraso de divulgação:** A entrega do FRE: `conhecido_em` é o DT_RECEB da versão
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`, `id_documento`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fre_distribuicao_capital/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia (como a CVM escreve) | texto |
| `referencia` | Data de referência do FRE | data (dia) |
| `versao` | Versão do FRE | número com decimais, na unidade da fonte |
| `id_documento` | Identificador do documento na CVM | texto |
| `acionistas_pf` | Número de acionistas pessoa física | número inteiro |
| `acionistas_pj` | Número de acionistas pessoa jurídica | número inteiro |
| `acionistas_institucionais` | Número de investidores institucionais | número inteiro |
| `circulacao_ordinarias` | Ações ordinárias em circulação | ações |
| `percentual_ordinarias` | Percentual das ordinárias em circulação, de 0 a 100 como a CVM escreve | número com decimais, na unidade da fonte |
| `circulacao_preferenciais` | Ações preferenciais em circulação | ações |
| `percentual_preferenciais` | Percentual das preferenciais em circulação, de 0 a 100 como a CVM escreve | número com decimais, na unidade da fonte |
| `circulacao_total` | Total de ações em circulação | ações |
| `percentual_total` | Percentual do total de ações em circulação (o free float declarado), de 0 a 100 como a CVM escreve; a CVM tem linhas fora dessa faixa | número com decimais, na unidade da fonte |
| `ultima_assembleia_em` | Data da última assembleia geral a que a distribuição se refere | data (dia) |
| `conhecido_em` | Entrega desta versão do FRE à CVM (DT_RECEB): como era na data | data (dia) |

## `fre_acionistas`

Posição acionária de cada FRE: os acionistas que a companhia declara (controladores e quem tem 5% ou mais de uma espécie) e os acionistas deles, até a pessoa física, com as ações e o percentual de cada espécie, desde 2010. Empresa e fundo entram com nome e CNPJ; pessoa física (ou CPF, ou nome sem cara de empresa) só somada por grupo, sem nome, CPF, UF nem nacionalidade (ADR 0075, item 5); o representante legal nem é lido

- **Fonte:** CVM: formulário de referência (FRE), dados abertos
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual, com reapresentações (a CVM reescreve os anos antigos)
- **Atraso de divulgação:** A entrega do FRE: `conhecido_em` é o DT_RECEB da versão
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** sim
- **Chaves:** `cnpj`, `referencia`, `versao`, `id_acionista`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fre_acionistas/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia (como a CVM escreve) | texto |
| `referencia` | Data de referência do FRE | data (dia) |
| `versao` | Versão do FRE | número com decimais, na unidade da fonte |
| `id_documento` | Identificador do documento na CVM | texto |
| `id_acionista` | Identificador do acionista na CVM; nas pessoas somadas, "pf:<grupo>:<controlador S/N>:<acordo S/N>" (o grupo é o `id_acionista_relacionado` ou "raiz") | texto |
| `tipo_acionista` | `pj` (empresa ou fundo), `pf_somada` (pessoas físicas do grupo, somadas), `outros` ou `tesouraria` (as linhas fixas da CVM) | texto |
| `acionista` | Nome do acionista; só em `pj` | texto |
| `cnpj_acionista` | CNPJ do acionista; só em `pj` (vazio quando a CVM traz só zeros) | texto |
| `id_acionista_relacionado` | De quem a linha é acionista (o `id_acionista` do grupo); vazio na companhia e quando o grupo é pessoa física | texto |
| `tipo_relacionado` | PJ ou PF: o tipo de quem a linha é acionista | texto |
| `cnpj_acionista_relacionado` | CNPJ de quem a linha é acionista; vazio quando é pessoa física | texto |
| `acoes_ordinarias` | Ações ordinárias | ações |
| `percentual_ordinarias` | Percentual das ações ordinárias (0 a 100) | número com decimais, na unidade da fonte |
| `acoes_preferenciais` | Ações preferenciais | ações |
| `percentual_preferenciais` | Percentual das ações preferenciais (0 a 100) | número com decimais, na unidade da fonte |
| `acoes_total` | Total de ações | ações |
| `percentual_total` | Percentual do total de ações (0 a 100) | número com decimais, na unidade da fonte |
| `controlador` | O acionista é controlador? | verdadeiro ou falso |
| `acordo_de_acionistas` | Participa de acordo de acionistas? | verdadeiro ou falso |
| `residente_exterior` | Reside no exterior? Só em `pj` | verdadeiro ou falso |
| `nacionalidade` | Nacionalidade; só em `pj` | texto |
| `uf` | UF; só em `pj` | texto |
| `composicao_em` | Data da composição do capital informada | data (dia) |
| `ultima_alteracao_em` | Data da última alteração da participação | data (dia) |
| `acionistas_no_grupo` | Quantos acionistas a linha soma (1 fora das pessoas somadas) | número inteiro |
| `conhecido_em` | Entrega desta versão do FRE à CVM (DT_RECEB): como era na data | data (dia) |

## `fre_partes_relacionadas`

Transações com partes relacionadas de cada FRE, desde 2010: a contraparte, a categoria da relação, os montantes, a taxa e a posição da companhia. Empresa entra com nome e CNPJ; pessoa física (ou CPF, ou sem tipo e nome sem cara de empresa) só somada por tipo e relação, sem nome nem documento (ADR 0075, item 5); o objeto e as garantias (texto livre) nem são lidos

- **Fonte:** CVM: formulário de referência (FRE), dados abertos
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual, com reapresentações (a CVM reescreve os anos antigos)
- **Atraso de divulgação:** A entrega do FRE: `conhecido_em` é o DT_RECEB da versão
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** sim
- **Chaves:** `cnpj`, `referencia`, `versao`, `linha`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fre_partes_relacionadas/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia (como a CVM escreve) | texto |
| `referencia` | Data de referência do FRE | data (dia) |
| `versao` | Versão do FRE | número com decimais, na unidade da fonte |
| `id_documento` | Identificador do documento na CVM | texto |
| `linha` | Posição da transação no documento ("1", "2"...); nas pessoas somadas, "pf:<tipo>:<relacao>" | texto |
| `tipo_pessoa` | PJ, PF ou `nao_informado`, como a companhia declara | texto |
| `contraparte` | Nome da parte relacionada; vazio nas pessoas somadas | texto |
| `cnpj_contraparte` | CNPJ da parte relacionada; vazio nas pessoas somadas | texto |
| `relacao` | Categoria da relação com a companhia (controle_comum, controle_conjunto, controladora, controlada, coligada, administracao, familiar, acionista, outra, nao_informada), tirada do texto livre | texto |
| `data_transacao` | Data da transação; vazio nas pessoas somadas | data (dia) |
| `montante_envolvido` | Montante envolvido (soma nas pessoas somadas) | reais (R$), já multiplicado pela escala informada |
| `saldo_existente` | Saldo existente (soma nas pessoas somadas) | reais (R$), já multiplicado pela escala informada |
| `montante_de_interesse` | Montante de interesse da parte relacionada (soma nas pessoas somadas) | reais (R$), já multiplicado pela escala informada |
| `emprestimo` | É empréstimo ou dívida? (alguma, nas pessoas somadas) | verdadeiro ou falso |
| `taxa_de_juros` | Taxa de juros em % quando é um número ("3,5%"); "CDI + 1%" e "N/A" ficam vazios | número com decimais, na unidade da fonte |
| `posicao_contratual` | `credor`, `devedor` ou `outra`: a posição da companhia | texto |
| `transacoes` | Quantas transações a linha soma (1 fora das pessoas somadas) | número inteiro |
| `conhecido_em` | Entrega desta versão do FRE à CVM (DT_RECEB): como era na data | data (dia) |

## `ofertas_antigas`

Ofertas públicas registradas na CVM até a Resolução 160 (ICVM 400, 476 e 555), desde 1989, por CNPJ do emissor, no formato da CVM, uma linha por série ou ativo (sem chave única: a ICVM 476 não tem número de processo). O nome do vendedor e o nome e o documento do ofertante sem CNPJ nunca entram

- **Fonte:** CVM: ofertas públicas de distribuição (OFERTA/DISTRIB, ODbL)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária (o ZIP é regerado todo dia)
- **Atraso de divulgação:** Nenhum além das datas da própria oferta (`anunciada_em`, `disponivel_em`)
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `numero_processo`, `numero_registro_oferta`, `cnpj_emissor`, `tipo_ativo`, `classe_ativo`, `serie`, `emissao`
- **Três datas:** aconteceu_em = `anunciada_em`; publico_em = `disponivel_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ofertas/antigas.parquet` (`scripts/carga_ofertas_e_conselhos.py`)
- **Linhagem:** O `.json` guarda o endereço e o SHA-256 do ZIP de ofertas usado e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `numero_processo` | Como a CVM publica (`Numero_Processo`) | texto |
| `numero_registro_oferta` | Como a CVM publica (`Numero_Registro_Oferta`) | texto |
| `tipo_oferta` | Como a CVM publica (`Tipo_Oferta`) | texto |
| `tipo_componente_oferta_mista` | Como a CVM publica (`Tipo_Componente_Oferta_Mista`) | texto |
| `tipo_ativo` | Como a CVM publica (`Tipo_Ativo`) | texto |
| `cnpj_emissor` | Como a CVM publica (`CNPJ_Emissor`) | texto |
| `nome_emissor` | Como a CVM publica (`Nome_Emissor`) | texto |
| `cnpj_lider` | Como a CVM publica (`CNPJ_Lider`) | texto |
| `nome_lider` | Como a CVM publica (`Nome_Lider`) | texto |
| `cnpj_ofertante` | Como a CVM publica (`CNPJ_Ofertante`) | texto |
| `nome_ofertante` | Como a CVM publica (`Nome_Ofertante`) | texto |
| `rito_oferta` | Como a CVM publica (`Rito_Oferta`) | texto |
| `modalidade_oferta` | Como a CVM publica (`Modalidade_Oferta`) | texto |
| `modalidade_registro` | Como a CVM publica (`Modalidade_Registro`) | texto |
| `modalidade_dispensa_registro` | Como a CVM publica (`Modalidade_Dispensa_Registro`) | texto |
| `data_abertura_processo` | Como a CVM publica (`Data_Abertura_Processo`) | data (dia) |
| `data_protocolo` | Como a CVM publica (`Data_Protocolo`) | data (dia) |
| `data_dispensa_oferta` | Como a CVM publica (`Data_Dispensa_Oferta`) | data (dia) |
| `data_registro_oferta` | Como a CVM publica (`Data_Registro_Oferta`) | data (dia) |
| `data_inicio_oferta` | Como a CVM publica (`Data_Inicio_Oferta`) | data (dia) |
| `data_encerramento_oferta` | Como a CVM publica (`Data_Encerramento_Oferta`) | data (dia) |
| `emissao` | Como a CVM publica (`Emissao`) | texto |
| `classe_ativo` | Como a CVM publica (`Classe_Ativo`) | texto |
| `serie` | Como a CVM publica (`Serie`) | texto |
| `especie_ativo` | Como a CVM publica (`Especie_Ativo`) | texto |
| `forma_ativo` | Como a CVM publica (`Forma_Ativo`) | texto |
| `data_emissao` | Como a CVM publica (`Data_Emissao`) | data (dia) |
| `data_vencimento` | Como a CVM publica (`Data_Vencimento`) | data (dia) |
| `quantidade_sem_lote_suplementar` | Como a CVM publica (`Quantidade_Sem_Lote_Suplementar`) | número com decimais, na unidade da fonte |
| `quantidade_no_lote_suplementar` | Como a CVM publica (`Quantidade_No_Lote_Suplementar`) | número com decimais, na unidade da fonte |
| `quantidade_total` | Como a CVM publica (`Quantidade_Total`) | número com decimais, na unidade da fonte |
| `preco_unitario` | Como a CVM publica (`Preco_Unitario`) | número com decimais, na unidade da fonte |
| `valor_total` | Como a CVM publica (`Valor_Total`) | número com decimais, na unidade da fonte |
| `oferta_inicial` | Como a CVM publica (`Oferta_Inicial`) | texto |
| `oferta_incentivo_fiscal` | Como a CVM publica (`Oferta_Incentivo_Fiscal`) | texto |
| `oferta_regime_fiduciario` | Como a CVM publica (`Oferta_Regime_Fiduciario`) | texto |
| `atualizacao_monetaria` | Como a CVM publica (`Atualizacao_Monetaria`) | texto |
| `juros` | Como a CVM publica (`Juros`) | texto |
| `projeto_audiovisual` | Como a CVM publica (`Projeto_Audiovisual`) | texto |
| `tipo_societario_emissor` | Como a CVM publica (`Tipo_Societario_Emissor`) | texto |
| `tipo_fundo_investimento` | Como a CVM publica (`Tipo_Fundo_Investimento`) | texto |
| `ultimo_comunicado` | Como a CVM publica (`Ultimo_Comunicado`) | texto |
| `data_comunicado` | Como a CVM publica (`Data_Comunicado`) | data (dia) |
| `nr_pessoa_fisica` | Como a CVM publica (`Nr_Pessoa_Fisica`) | número com decimais, na unidade da fonte |
| `qtd_pessoa_fisica` | Como a CVM publica (`Qtd_Pessoa_Fisica`) | número com decimais, na unidade da fonte |
| `nr_clube_investimento` | Como a CVM publica (`Nr_Clube_Investimento`) | número com decimais, na unidade da fonte |
| `qtd_clube_investimento` | Como a CVM publica (`Qtd_Clube_Investimento`) | número com decimais, na unidade da fonte |
| `nr_fundos_investimento` | Como a CVM publica (`Nr_Fundos_Investimento`) | número com decimais, na unidade da fonte |
| `qtd_fundos_investimento` | Como a CVM publica (`Qtd_Fundos_Investimento`) | número com decimais, na unidade da fonte |
| `nr_entidade_previdencia_privada` | Como a CVM publica (`Nr_Entidade_Previdencia_Privada`) | número com decimais, na unidade da fonte |
| `qtd_entidade_previdencia_privada` | Como a CVM publica (`Qtd_Entidade_Previdencia_Privada`) | número com decimais, na unidade da fonte |
| `nr_companhia_seguradora` | Como a CVM publica (`Nr_Companhia_Seguradora`) | número com decimais, na unidade da fonte |
| `qtd_companhia_seguradora` | Como a CVM publica (`Qtd_Companhia_Seguradora`) | número com decimais, na unidade da fonte |
| `nr_investidor_estrangeiro` | Como a CVM publica (`Nr_Investidor_Estrangeiro`) | número com decimais, na unidade da fonte |
| `qtd_investidor_estrangeiro` | Como a CVM publica (`Qtd_Investidor_Estrangeiro`) | número com decimais, na unidade da fonte |
| `nr_instit_intermed_partic_consorcio_distrib` | Como a CVM publica (`Nr_Instit_Intermed_Partic_Consorcio_Distrib`) | número com decimais, na unidade da fonte |
| `qtd_instit_intermed_partic_consorcio_distrib` | Como a CVM publica (`Qtd_Instit_Intermed_Partic_Consorcio_Distrib`) | número com decimais, na unidade da fonte |
| `nr_instit_financ_emissora_partic_consorcio` | Como a CVM publica (`Nr_Instit_Financ_Emissora_Partic_Consorcio`) | número com decimais, na unidade da fonte |
| `qtd_instit_financ_emissora_partic_consorcio` | Como a CVM publica (`Qtd_Instit_Financ_Emissora_Partic_Consorcio`) | número com decimais, na unidade da fonte |
| `nr_demais_instit_financ` | Como a CVM publica (`Nr_Demais_Instit_Financ`) | número com decimais, na unidade da fonte |
| `qtd_demais_instit_financ` | Como a CVM publica (`Qtd_Demais_Instit_Financ`) | número com decimais, na unidade da fonte |
| `nr_demais_pessoa_juridica_emissora_partic_consorcio` | Como a CVM publica (`Nr_Demais_Pessoa_Juridica_Emissora_Partic_Consorcio`) | número com decimais, na unidade da fonte |
| `qtd_demais_pessoa_juridica_emissora_partic_consorcio` | Como a CVM publica (`Qtd_Demais_Pessoa_Juridica_Emissora_Partic_Consorcio`) | número com decimais, na unidade da fonte |
| `nr_demais_pessoa_juridica` | Como a CVM publica (`Nr_Demais_Pessoa_Juridica`) | número com decimais, na unidade da fonte |
| `qtd_demais_pessoa_juridica` | Como a CVM publica (`Qtd_Demais_Pessoa_Juridica`) | número com decimais, na unidade da fonte |
| `nr_soc_adm_emp_prop_demais_pess_jurid_emiss_partic_consorcio` | Como a CVM publica (`Nr_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio`) | número com decimais, na unidade da fonte |
| `qdt_soc_adm_emp_prop_demais_pess_jurid_emiss_partic_consorcio` | Como a CVM publica (`Qdt_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio`) | número com decimais, na unidade da fonte |
| `nr_outros` | Como a CVM publica (`Nr_Outros`) | número com decimais, na unidade da fonte |
| `qtd_outros` | Como a CVM publica (`Qtd_Outros`) | número com decimais, na unidade da fonte |
| `qtd_cli_pessoa_fisica` | Como a CVM publica (`Qtd_Cli_Pessoa_Fisica`) | número com decimais, na unidade da fonte |
| `qtd_cli_pessoa_juridica` | Como a CVM publica (`Qtd_Cli_Pessoa_Juridica`) | número com decimais, na unidade da fonte |
| `qtd_cli_pessoa_juridica_ligada_adm` | Como a CVM publica (`Qtd_Cli_Pessoa_Juridica_Ligada_Adm`) | número com decimais, na unidade da fonte |
| `qtd_cli_demais_pessoa_juridica` | Como a CVM publica (`QtD_Cli_Demais_Pessoa_Juridica`) | número com decimais, na unidade da fonte |
| `qtd_cli_investidor_estrangeiro` | Como a CVM publica (`Qtd_Cli_Investidor_Estrangeiro`) | número com decimais, na unidade da fonte |
| `qtd_cli_soc_adm_emp_prop_demais_pess_jurid_emiss_partic_consorcio` | Como a CVM publica (`Qtd_Cli_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio`) | número com decimais, na unidade da fonte |
| `anunciada_em` | Quando a oferta ficou pública na CVM (registro, dispensa ou comunicado da 476) | data (dia) |
| `disponivel_em` | Quando a linha inteira era pública (o mais tarde entre o anúncio e o encerramento) | data (dia) |

## `ofertas_resolucao_160`

Requerimentos de oferta pública pela Resolução CVM 160 (2023 em diante), por CNPJ do emissor, no formato da CVM, sem os textos livres (devedores, garantias, lastro, destinação dos recursos)

- **Fonte:** CVM: ofertas públicas de distribuição (OFERTA/DISTRIB, ODbL)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária (o ZIP é regerado todo dia)
- **Atraso de divulgação:** Nenhum além das datas da própria oferta (`anunciada_em`, `disponivel_em`)
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `numero_requerimento`, `cnpj_emissor`
- **Três datas:** aconteceu_em = `anunciada_em`; publico_em = `disponivel_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ofertas/resolucao_160.parquet` (`scripts/carga_ofertas_e_conselhos.py`)
- **Linhagem:** O `.json` guarda o endereço e o SHA-256 do ZIP de ofertas usado e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `numero_requerimento` | Como a CVM publica (`Numero_Requerimento`) | texto |
| `rito_requerimento` | Como a CVM publica (`Rito_Requerimento`) | texto |
| `numero_processo` | Como a CVM publica (`Numero_Processo`) | texto |
| `data_requerimento` | Como a CVM publica (`Data_requerimento`) | data (dia) |
| `data_registro` | Como a CVM publica (`Data_Registro`) | data (dia) |
| `data_encerramento` | Como a CVM publica (`Data_Encerramento`) | data (dia) |
| `status_requerimento` | Como a CVM publica (`Status_Requerimento`) | texto |
| `valor_mobiliario` | Como a CVM publica (`Valor_Mobiliario`) | texto |
| `tipo_requerimento` | Como a CVM publica (`Tipo_requerimento`) | texto |
| `bookbuilding` | Como a CVM publica (`Bookbuilding`) | texto |
| `cnpj_emissor` | Como a CVM publica (`CNPJ_Emissor`) | texto |
| `nome_emissor` | Como a CVM publica (`Nome_Emissor`) | texto |
| `cnpj_lider` | Como a CVM publica (`CNPJ_Lider`) | texto |
| `nome_lider` | Como a CVM publica (`Nome_Lider`) | texto |
| `grupo_coordenador` | Como a CVM publica (`Grupo_Coordenador`) | texto |
| `tipo_oferta` | Como a CVM publica (`Tipo_Oferta`) | texto |
| `emissao` | Como a CVM publica (`Emissao`) | texto |
| `qtde_total_registrada` | Como a CVM publica (`Qtde_Total_Registrada`) | número com decimais, na unidade da fonte |
| `valor_total_registrado` | Como a CVM publica (`Valor_Total_Registrado`) | número com decimais, na unidade da fonte |
| `oferta_inicial` | Como a CVM publica (`Oferta_inicial`) | texto |
| `oferta_vasos_comunicantes` | Como a CVM publica (`Oferta_vasos_comunicantes`) | texto |
| `publico_alvo` | Como a CVM publica (`Publico_alvo`) | texto |
| `reabertura_serie` | Como a CVM publica (`Reabertura_serie`) | texto |
| `titulo_classificado_como_sustentavel` | Como a CVM publica (`Titulo_classificado_como_sustentavel`) | texto |
| `titulo_padronizado` | Como a CVM publica (`Titulo_padronizado`) | texto |
| `data_deliberacao_aprovou_oferta` | Como a CVM publica (`Data_deliberacao_aprovou_oferta`) | data (dia) |
| `mercado_negociacao` | Como a CVM publica (`Mercado_negociacao`) | texto |
| `tipo_lastro` | Como a CVM publica (`Tipo_lastro`) | texto |
| `regime_fiduciario` | Como a CVM publica (`Regime_fiduciario`) | texto |
| `ativos_alvo` | Como a CVM publica (`Ativos_alvo`) | texto |
| `possibilidade_revolvencia` | Como a CVM publica (`Possibilidade_revolvencia`) | texto |
| `fidc_nao_padronizado` | Como a CVM publica (`FIDC_nao_padronizado`) | texto |
| `titulo_incentivado` | Como a CVM publica (`Titulo_incentivado`) | texto |
| `regime_distribuicao` | Como a CVM publica (`Regime_distribuicao`) | texto |
| `tipo_societario` | Como a CVM publica (`Tipo_societario`) | texto |
| `administrador` | Como a CVM publica (`Administrador`) | texto |
| `gestor` | Como a CVM publica (`Gestor`) | texto |
| `agente_fiduciario` | Como a CVM publica (`Agente_fiduciario`) | texto |
| `escriturador` | Como a CVM publica (`Escriturador`) | texto |
| `custodiante` | Como a CVM publica (`Custodiante`) | texto |
| `avaliador_risco` | Como a CVM publica (`Avaliador_Risco`) | texto |
| `processo_sei` | Como a CVM publica (`Processo_SEI`) | texto |
| `endereco_emissor_rede_mundial_computadores` | Como a CVM publica (`Endereco_emissor_rede_mundial_computadores`) | texto |
| `num_invest_pessoa_natural` | Como a CVM publica (`Num_Invest_Pessoa_Natural`) | número com decimais, na unidade da fonte |
| `qtde_vm_pessoa_natural` | Como a CVM publica (`Qtde_VM_Pessoa_Natural`) | número com decimais, na unidade da fonte |
| `num_invest_clube_investimento` | Como a CVM publica (`Num_Invest_Clube_Investimento`) | número com decimais, na unidade da fonte |
| `qtde_vm_clube_investimento` | Como a CVM publica (`Qtde_VM_Clube_Investimento`) | número com decimais, na unidade da fonte |
| `num_invest_fundos_investimento` | Como a CVM publica (`Num_Invest_Fundos_Investimento`) | número com decimais, na unidade da fonte |
| `qtde_vm_fundos_investimento` | Como a CVM publica (`Qtde_VM_Fundos_Investimento`) | número com decimais, na unidade da fonte |
| `num_invest_entidade_previdencia_privada` | Como a CVM publica (`Num_Invest_Entidade_Previdencia_Privada`) | número com decimais, na unidade da fonte |
| `qtde_vm_entidade_previdencia_privada` | Como a CVM publica (`Qtde_VM_Entidade_Previdencia_Privada`) | número com decimais, na unidade da fonte |
| `num_invest_companhia_seguradora` | Como a CVM publica (`Num_Invest_Companhia_Seguradora`) | número com decimais, na unidade da fonte |
| `qtde_vm_companhia_seguradora` | Como a CVM publica (`Qtde_VM_Companhia_Seguradora`) | número com decimais, na unidade da fonte |
| `num_invest_investidor_estrangeiro` | Como a CVM publica (`Num_Invest_Investidor_Estrangeiro`) | número com decimais, na unidade da fonte |
| `qtde_vm_investidor_estrangeiro` | Como a CVM publica (`Qtde_VM_Investidor_Estrangeiro`) | número com decimais, na unidade da fonte |
| `num_invest_instit_intermed_partic_consorcio_distrib` | Como a CVM publica (`Num_Invest_Instit_Intermed_Partic_Consorcio_Distrib`) | número com decimais, na unidade da fonte |
| `qtde_vm_instit_intermed_partic_consorcio_distrib` | Como a CVM publica (`Qtde_VM_Instit_Intermed_Partic_Consorcio_Distrib`) | número com decimais, na unidade da fonte |
| `num_invest_instit_financ_emissora_partic_consorcio` | Como a CVM publica (`Num_Invest_Instit_Financ_Emissora_Partic_Consorcio`) | número com decimais, na unidade da fonte |
| `qtde_vm_instit_financ_emissora_partic_consorcio` | Como a CVM publica (`Qtde_VM_Instit_Financ_Emissora_Partic_Consorcio`) | número com decimais, na unidade da fonte |
| `num_invest_demais_instit_financ` | Como a CVM publica (`Num_Invest_Demais_Instit_Financ`) | número com decimais, na unidade da fonte |
| `qtde_vm_demais_instit_financ` | Como a CVM publica (`Qtde_VM_Demais_Instit_Financ`) | número com decimais, na unidade da fonte |
| `num_invest_demais_pessoa_juridica_emissora_partic_consorcio` | Como a CVM publica (`Num_Invest_Demais_Pessoa_Juridica_Emissora_Partic_Consorcio`) | número com decimais, na unidade da fonte |
| `qtde_vm_demais_pessoa_juridica_emissora_partic_consorcio` | Como a CVM publica (`Qtde_VM_Demais_Pessoa_Juridica_Emissora_Partic_Consorcio`) | número com decimais, na unidade da fonte |
| `num_invest_demais_pessoa_juridica` | Como a CVM publica (`Num_Invest_Demais_Pessoa_Juridica`) | número com decimais, na unidade da fonte |
| `qtde_vm_demais_pessoa_juridica` | Como a CVM publica (`Qtde_VM_Demais_Pessoa_Juridica`) | número com decimais, na unidade da fonte |
| `num_invest_soc_adm_emp_prop_demais_pess_jurid_emiss_partic_consorcio` | Como a CVM publica (`Num_Invest_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio`) | número com decimais, na unidade da fonte |
| `qdte_vm_soc_adm_emp_prop_demais_pess_jurid_emiss_partic_consorcio` | Como a CVM publica (`Qdte_VM_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio`) | número com decimais, na unidade da fonte |
| `anunciada_em` | Quando a oferta ficou pública na CVM (registro, dispensa ou comunicado da 476) | data (dia) |
| `disponivel_em` | Quando a linha inteira era pública (o mais tarde entre o anúncio e o encerramento) | data (dia) |

## `susep_seguros`

Prêmios, sinistros e despesas de seguros por seguradora (código da SUSEP), grupo de ramos, ramo e mês desde 1995 (SES), no formato da fonte. O cadastro da SUSEP não traz CNPJ e a B13 ainda não liga o código a uma empresa: todos os códigos estão nos buracos. Uma linha por valor diferente de cada chave: a revisão de um mês passado vira linha nova, que só vale desde o dia em que foi vista (`base/setoriais/revisoes.py::como_era_em`)

- **Fonte:** SUSEP: SES, base de dados completa (`Ses_seguros.csv` de dentro do ZIP)
- **Licença:** CC BY (SES da SUSEP no dados.gov.br; citar a SUSEP). Só os CSVs sem pessoas
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (o ZIP é regerado todo dia)
- **Atraso de divulgação:** Agosto/2026 estava publicado em 16/10/2026 (47 dias); a regra usa o fim do mês + 60 dias
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `coenti`, `cogrupo`, `coramo`, `visto_em`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por ano em `<acervo>/base/setoriais/susep/<ano>.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço (`zip#Ses_seguros.csv`) e o SHA-256 de cada baixada usada e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês (último dia) | data (dia) |
| `coenti` | Código da seguradora na SUSEP (a chave; 5 dígitos) | texto |
| `cogrupo` | Código do grupo de ramos | texto |
| `coramo` | Código do ramo (nomes em `Ses_ramos.csv`, guardado no acervo) | texto |
| `premio_direto` | Prêmio direto no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `premio_de_seguros` | Prêmio de seguros no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `premio_retido` | Prêmio retido no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `premio_ganho` | Prêmio ganho no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `sinistro_direto` | Sinistro direto no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `sinistro_retido` | Sinistro retido no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `desp_com` | Despesa de comercialização no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `premio_emitido2` | Prêmio emitido no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `premio_emitido_cap` | Prêmio emitido (capitalização) no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `despesa_resseguros` | Despesa com resseguros no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `sinistro_ocorrido` | Sinistro ocorrido no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `receita_resseguro` | Receita com resseguro no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `sinistros_ocorridos_cap` | Sinistros ocorridos (capitalização) no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `recuperacao_sinistros_ocorridos_cap` | Recuperação de sinistros ocorridos (capitalização) no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `rvne` | Riscos vigentes não emitidos (RVNE) no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `conveniodpvat` | Convênio DPVAT no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `consorciosefundos` | Consórcios e fundos no mês, em R$, como a SUSEP publica | reais (R$), já multiplicado pela escala informada |
| `disponivel_em` | Desde quando o número era público (fim do mês + 60 dias; a revisão, desde o dia em que foi vista) | data (dia) |
| `visto_em` | O dia da baixada do arquivista que trouxe este valor pela primeira vez | data (dia) |

## `amostra_painel`

A amostra integrada (ADR 0058): uma linha por companhia e fim de mês, desde jan/2010, com só o que se sabia dela naquele dia, de todas as fontes da base. Cada bloco usa a linha mais nova já pública na data (`base/amostra/como_era.py`), e o teste corta a base em cada data para provar que nada do futuro entra. As canceladas ficam nos meses em que existiam. Por enquanto, só o bloco universo (quem está e os tickers) e demonstrações (balanço, acumulado no ano e anual, como eram); os outros entram um por PR

- **Fonte:** Derivado: cadastro da CVM, `rotulos_atraso` (entregas de DFP e ITR), `tickers_no_tempo` e `demonstracoes_como_era`
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal (até o último mês fechado)
- **Atraso de divulgação:** Nenhum além do de cada fonte: cada coluna vale desde que ficou pública
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `data`
- **Três datas:** aconteceu_em = `data`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.1.0
- **Onde fica:** Parquet por ano em `<acervo>/base/amostra/v1/painel/<ano>.parquet` (`scripts/montar_amostra.py`)
- **Linhagem:** O `<ano>.json` aponta as tabelas de entrada (com o hash do manifesto de cada uma) e o original do cadastro; a linhagem segue das tabelas até os originais (`base/linhagem.py`).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `data` | Fim do mês: a linha diz o que se sabia neste dia | data (dia) |
| `registrada_desde` | Início do registro de companhia aberta vigente na data | data (dia) |
| `primeira_entrega` | A primeira DFP ou ITR entregue (a companhia só entra depois dela) | data (dia) |
| `tickers_na_data` | Os códigos de negociação válidos na data, pelo FCA (vazio: nenhum) | texto |
| `com_ticker_na_data` | Tinha ao menos um código válido na data; vazio antes de o FCA trazer códigos (2018): não se sabe | verdadeiro ou falso |
| `balanco_fim` | Data do balanço mais novo já público na data | data (dia) |
| `balanco_publico_em` | Quando os valores do balanço usados ficaram públicos (entrega à CVM) | data (dia) |
| `balanco_grupo` | con (consolidado) ou ind (individual, sem consolidado no período) | texto |
| `ativo_total` | Ativo total (conta 1) | reais (R$), já multiplicado pela escala informada |
| `caixa` | Caixa e equivalentes de caixa | reais (R$), já multiplicado pela escala informada |
| `patrimonio_liquido` | Patrimônio líquido (consolidado: com os minoritários) | reais (R$), já multiplicado pela escala informada |
| `divida_bruta` | Empréstimos e financiamentos de curto e de longo prazo, somados | reais (R$), já multiplicado pela escala informada |
| `acumulado_inicio` | Início do período acumulado do documento mais novo (o início do exercício) | data (dia) |
| `acumulado_fim` | Fim do período acumulado (o fim do trimestre ou do exercício) | data (dia) |
| `acumulado_publico_em` | Quando os valores acumulados usados ficaram públicos | data (dia) |
| `acumulado_grupo` | con ou ind, no acumulado | texto |
| `receita_acumulado` | Receita do início do exercício ao fim do trimestre (bancos: da intermediação) | reais (R$), já multiplicado pela escala informada |
| `ebit_acumulado` | Resultado antes do financeiro e dos tributos, acumulado (vazio nos bancos) | reais (R$), já multiplicado pela escala informada |
| `lucro_acumulado` | Lucro ou prejuízo do período, acumulado | reais (R$), já multiplicado pela escala informada |
| `anual_fim` | Fim do exercício da DFP mais nova já pública | data (dia) |
| `anual_publico_em` | Quando os valores anuais usados ficaram públicos | data (dia) |
| `anual_grupo` | con ou ind, no anual | texto |
| `receita_anual` | Receita do exercício (bancos: da intermediação) | reais (R$), já multiplicado pela escala informada |
| `ebit_anual` | Resultado antes do financeiro e dos tributos, no exercício (vazio nos bancos) | reais (R$), já multiplicado pela escala informada |
| `lucro_anual` | Lucro ou prejuízo do exercício | reais (R$), já multiplicado pela escala informada |

## `setoriais_buracos`

Os códigos das fontes setoriais (sigla da ANAC, agente da ANP) que a B13 não liga a uma empresa, do maior volume para o menor: a lista de trabalho da próxima conferência

- **Fonte:** Derivado: fontes setoriais e a B13 (empresa_serie)
- **Licença:** CC BY (dados abertos da ANP no dados.gov.br; citar a ANP)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** A cada carga das fontes setoriais
- **Atraso de divulgação:** Nenhum
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `fonte`, `chave`
- **Três datas:** nenhuma coluna da tabela traz estas datas
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/setoriais/buracos.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `.json` anota a tabela da B13 usada (SHA-256 do conteúdo) e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `chave` | Código na fonte sem ligação | texto |
| `valor` | Volume somado (passageiros pagos na ANAC, quantidade na ANP) | número com decimais, na unidade da fonte |
| `primeira` | Primeiro mês em que aparece | data (dia) |
| `ultima` | Último mês em que aparece | data (dia) |
| `fonte` | Fonte no registro de coletas | texto |

## `ifdata_valores`

Balanço, resultado, capital, segmentação e carteira de crédito de cada banco e conglomerado, por trimestre desde 2000, no formato longo da fonte (uma linha por instituição, relatório, conta e coluna). Tipo 1 = conglomerado prudencial (desde mar/2014), 2 = conglomerado financeiro, 3 = instituição individual. Ficam fora o relatório 15 (câmbio) e as linhas de total sem código de instituição

- **Fonte:** Banco Central: IF.data (API Olinda, `IfDataValores`)
- **Licença:** ODbL (dados abertos do Banco Central; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Trimestral (data-base em mar, jun, set e dez)
- **Atraso de divulgação:** Jun/2026 estava publicado em 14/10 (106 dias); `disponivel_em` usa data-base + 120 dias. O BC revisa: as 8 datas mais novas são baixadas de novo a cada carga e cada revisão vira linha nova da mesma chave, que só vale desde o dia em que foi vista (`visto_em`; `base/setoriais/revisoes.py::como_era_em`), e a tabela anterior fica guardada como `<AAAAMM>.v<N>`. O que o BC revisou antes da 1ª coleta guardada (10/2026) não aparece
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `data_base`, `tipo_instituicao`, `cod_inst`, `relatorio`, `grupo`, `conta`, `coluna`, `visto_em`
- **Três datas:** aconteceu_em = `data_base`; publico_em = `disponivel_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 2.0.0
- **Onde fica:** Parquet em `<acervo>/base/bcb/ifdata/valores/tipo_<t>/<AAAAMM>.parquet` (servidor de casa, `scripts/carga_bcb_credito.py`)
- **Linhagem:** O `<AAAAMM>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada resposta da API (no acervo e no registro de coletas, fonte `bcb-ifdata`, com a data da coleta) e a versão do código que gravou.

| Coluna | O que é | Unidade |
|---|---|---|
| `data_base` | Fim do trimestre a que o número se refere | data (dia) |
| `tipo_instituicao` | 1 prudencial, 2 financeiro, 3 individual | número inteiro |
| `cod_inst` | Código da instituição no BC (raiz do CNPJ ou C00... do conglomerado) | texto |
| `relatorio` | Número do relatório (1 Resumo, 2 Ativo, 3 Passivo...) | número inteiro |
| `nome_relatorio` | Nome do relatório | texto |
| `grupo` | Grupo da linha, quando o relatório tem | texto |
| `conta` | Código da conta no relatório | texto |
| `coluna` | Nome da coluna, com a letra da nota ("Disponibilidades (a)") | texto |
| `descricao` | Fórmula da coluna nas contas do Cosif | texto |
| `saldo` | Valor da linha | reais (R$), já multiplicado pela escala informada |
| `disponivel_em` | Desde quando o número era público (como era na data): o prazo, ou o dia em que a revisão do BC foi vista, se for depois | data (dia) |
| `visto_em` | Dia (São Paulo) em que o arquivista baixou a resposta que trouxe este valor; vazio se não havia o dia (acervo desligado) | data (dia) |

## `ifdata_cadastro`

O cadastro de cada data-base do IF.data: nome, tipo de controle, segmento, cidade, conglomerados e CNPJ do líder de cada instituição e conglomerado, com a raiz do CNPJ que liga à bolsa

- **Fonte:** Banco Central: IF.data (API Olinda, `IfDataCadastro`)
- **Licença:** ODbL (dados abertos do Banco Central; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Trimestral, junto com os valores
- **Atraso de divulgação:** O dos valores (o cadastro sai com a data-base): `disponivel_em` usa data-base + 120 dias. O BC revisa: as 8 datas mais novas são baixadas de novo a cada carga e cada revisão vira linha nova da mesma chave, que só vale desde o dia em que foi vista (`visto_em`; `base/setoriais/revisoes.py::como_era_em`), e a tabela anterior fica guardada como `<AAAAMM>.v<N>`. O que o BC revisou antes da 1ª coleta guardada (10/2026) não aparece
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `data_base`, `cod_inst`, `visto_em`
- **Três datas:** aconteceu_em = `data_base`; publico_em = `disponivel_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 2.0.0
- **Onde fica:** Parquet em `<acervo>/base/bcb/ifdata/cadastro/<AAAAMM>.parquet` (servidor de casa)
- **Linhagem:** Como `ifdata_valores`: o manifesto guarda o endereço e o SHA-256 da resposta.

| Coluna | O que é | Unidade |
|---|---|---|
| `data_base` | Data-base do cadastro | data (dia) |
| `cod_inst` | Código da instituição no BC | texto |
| `instituicao` | Nome da instituição | texto |
| `tipo_controle` | Tc: 1 público, 2 privado nacional, 3 estrangeiro | texto |
| `tipo_consolidado` | Tcb: tipo de consolidado bancário (b1, b2...) | texto |
| `tipo_documento` | Td: tipo de documento contábil | texto |
| `segmento_prudencial` | Sr: segmento da regulação prudencial (S1 a S5) | texto |
| `segmento` | Segmento da instituição, quando informado | texto |
| `atividade` | Atividade principal, quando informada | texto |
| `uf` | UF da sede | texto |
| `municipio` | Município da sede | texto |
| `conglomerado_financeiro` | Código do conglomerado financeiro | texto |
| `conglomerado_prudencial` | Código do conglomerado prudencial | texto |
| `cnpj_lider` | Raiz do CNPJ da instituição líder (8 dígitos) | texto |
| `inicio_atividade` | Mês de início da atividade (AAAAMM) | número inteiro |
| `situacao` | A = ativa | texto |
| `cnpj_raiz` | Raiz do CNPJ usada na ligação: a do líder ou o próprio código, se for CNPJ | texto |
| `disponivel_em` | Desde quando o cadastro era público (como era na data): o prazo, ou o dia em que a revisão do BC foi vista, se for depois | data (dia) |
| `visto_em` | Dia (São Paulo) em que o arquivista baixou a resposta que trouxe esta linha; vazio se não havia o dia (acervo desligado) | data (dia) |

## `ligacao_dos_bancos`

Instituição do IF.data → CNPJ da empresa da bolsa → tickers que valiam no ano, por data-base. A instituição cujo código é o CNPJ de uma empresa do FCA liga por ele (o Banco PAN, do conglomerado do BTG, tem ação própria); as outras, pela raiz do CNPJ do líder do conglomerado. Antes de 2010 (sem FCA) a ligação chega ao CNPJ, mas não à ação. Instituição sem ação (Caixa, BNDES) fica sem CNPJ

- **Fonte:** Derivado: IF.data (cadastro) e CVM, FCA (emissores e tickers)
- **Licença:** ODbL (dados abertos do Banco Central; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Trimestral, montada de novo a cada carga
- **Atraso de divulgação:** O do cadastro do IF.data
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `data_base`, `cod_inst`
- **Três datas:** aconteceu_em = `data_base`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/bcb/ifdata/ligacao_dos_bancos.parquet` (servidor de casa)
- **Linhagem:** O `.json` lista cada cadastro e as tabelas do FCA usados, com o SHA-256 de cada arquivo, e a versão do código. `base/linhagem.py::linhagem_da_tabela` segue cada tabela de entrada pelo manifesto dela até os originais; se uma entrada foi regravada depois, a derivada não confere até ser remontada.

| Coluna | O que é | Unidade |
|---|---|---|
| `data_base` | Data-base do cadastro | data (dia) |
| `cod_inst` | Código da instituição no BC | texto |
| `instituicao` | Nome da instituição | texto |
| `cnpj_raiz` | Raiz do CNPJ (8 dígitos) | texto |
| `cnpj` | CNPJ da empresa da bolsa (vazio se não tem ação) | texto |
| `tickers` | Códigos que valiam na data-base (FCA já entregue), separados por vírgula | texto |
| `ligado_por` | próprio CNPJ (a instituição é a empresa da bolsa, como o Banco PAN) ou líder do conglomerado; vazio sem ligação | texto |

## `scr_credito`

Carteira de crédito do sistema financeiro por mês desde jul/2012 (SCR.data versão 2): por UF, segmento da instituição, PF ou PJ, CNAE (PJ) ou ocupação (PF), porte, modalidade, origem dos recursos e indexador, com prazos a vencer, atraso, inadimplência e ativo problemático. Agregado, sem pessoa nem instituição. A versão 1 (parou em jun/2025) fica fora

- **Fonte:** Banco Central: SCR.data (`scrdata_<ano>.zip`)
- **Licença:** ODbL (dados abertos do Banco Central; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal, um arquivo por ano
- **Atraso de divulgação:** Publicado ~30 dias depois do fim do mês (ago/2026 já estava no arquivo em 09/10); `disponivel_em` usa data-base + 60 dias. O BC regrava anos passados: os 2 anos mais novos são baixados de novo a cada carga e cada regravação que muda um número vira linha nova da mesma chave, que só vale desde o dia em que foi vista (`visto_em`; `base/setoriais/revisoes.py::como_era_em`), e a tabela anterior fica guardada como `<ano>.v<N>`. O que o BC revisou antes da 1ª coleta guardada (10/2026) não aparece
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `data_base`, `uf`, `segmento`, `cliente`, `cnae_ocupacao`, `porte`, `modalidade`, `submodalidade`, `origem`, `indexador`, `ocorrencia`, `visto_em`
- **Três datas:** aconteceu_em = `data_base`; publico_em = `disponivel_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 2.0.0
- **Onde fica:** Parquet em `<acervo>/base/bcb/scr/<ano>.parquet` (servidor de casa, `scripts/carga_bcb_credito.py`)
- **Linhagem:** O `<ano>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 do arquivo do BC (no acervo e no registro de coletas, fonte `bcb-scr-base`) e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `data_base` | Fim do mês | data (dia) |
| `uf` | UF do cliente | texto |
| `segmento` | Segmento da instituição (Banco, Cooperativa, Financeira...) | texto |
| `cliente` | PF ou PJ | texto |
| `cnae_ocupacao` | Seção do CNAE (PJ) ou natureza da ocupação (PF) | texto |
| `porte` | Porte da empresa (PJ) ou faixa de renda (PF) | texto |
| `modalidade` | Modalidade do crédito | texto |
| `submodalidade` | Submodalidade do crédito | texto |
| `origem` | Origem dos recursos (livres ou direcionados) | texto |
| `indexador` | Indexador (prefixado, pós-fixado...) | texto |
| `numero_de_operacoes` | Número de operações (vazio quando o BC não informa) | número inteiro |
| `a_vencer_ate_90_dias` | Carteira a vencer em até 90 dias | reais (R$), já multiplicado pela escala informada |
| `a_vencer_de_91_ate_360_dias` | A vencer de 91 a 360 dias | reais (R$), já multiplicado pela escala informada |
| `a_vencer_de_361_ate_1080_dias` | A vencer de 361 a 1080 dias | reais (R$), já multiplicado pela escala informada |
| `a_vencer_de_1081_ate_1800_dias` | A vencer de 1081 a 1800 dias | reais (R$), já multiplicado pela escala informada |
| `a_vencer_de_1801_ate_5400_dias` | A vencer de 1801 a 5400 dias | reais (R$), já multiplicado pela escala informada |
| `a_vencer_acima_de_5400_dias` | A vencer acima de 5400 dias | reais (R$), já multiplicado pela escala informada |
| `carteira_a_vencer` | Total a vencer | reais (R$), já multiplicado pela escala informada |
| `vencido_de_15_ate_90_dias` | Vencido de 15 a 90 dias | reais (R$), já multiplicado pela escala informada |
| `vencido_acima_de_90_dias` | Vencido há mais de 90 dias | reais (R$), já multiplicado pela escala informada |
| `carteira_vencida` | Total vencido (a partir de 15 dias) | reais (R$), já multiplicado pela escala informada |
| `carteira_ativa` | Carteira ativa, como o BC informa | reais (R$), já multiplicado pela escala informada |
| `carteira_inadimplencia` | Carteira em inadimplência (atraso acima de 90 dias) | reais (R$), já multiplicado pela escala informada |
| `ativo_problematico` | Ativo problemático (atraso ou reestruturação) | reais (R$), já multiplicado pela escala informada |
| `disponivel_em` | Desde quando o mês era público (como era na data): o prazo, ou o dia em que a revisão do BC foi vista, se for depois | data (dia) |
| `ocorrencia` | Ordem da linha entre as de mesma chave no arquivo do BC (0, 1...): o BC publica mais de uma linha por chave e a base soma todas | número inteiro |
| `visto_em` | Dia (São Paulo) em que o arquivista baixou a resposta que trouxe esta linha; vazio se não havia o dia (acervo desligado) | data (dia) |

## `padroes_setoriais`

Os padrões por setor das notas (ADR 0033): os percentis de cada indicador entre as empresas de cada grupo de setores (`src/setores.py`), calculados só com os balanços que eram públicos na data de corte. Dado derivado: recalcular o mesmo corte substitui as linhas dele.

- **Fonte:** Calculado pelo TickerLab das demonstrações da CVM (DFP e ITR, versões do Radar); nos múltiplos, também o preço da ação (Yahoo Finance)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Ressalva de revenda:** As linhas dos múltiplos (`p_l`, `p_vp`) usam o preço do Yahoo Finance: não comercial (uso pessoal, só pesquisa ou conta de estudante: só gabarito e pesquisa no PC; nunca em modelo, rótulo ou exportação).
- **Frequência:** Um corte por fim de mês; o cron do VPS roda todo dia às 8h30 e só grava o corte que falta (`scripts/atualizar_padroes.py --so-o-que-falta`)
- **Atraso de divulgação:** O do balanço mais novo de cada empresa até o corte (DFP até 3 meses, ITR até 45 dias)
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `data_de_corte`, `grupo`, `indicador`, `versao`
- **Três datas:** aconteceu_em = `data_de_corte`; coletado_em = `calculado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `exercicio`, `referencia`, `versao`
- **Três datas:** aconteceu_em = `referencia`; coletado_em = `coletado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `tipo`, `data`, `referencia`, `versao`
- **Três datas:** aconteceu_em = `data`; coletado_em = `coletado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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

## `eventos`

Documentos do IPE da CVM desde 2003 (fatos relevantes, comunicados, assembleias, resultados...), com o tema e a materialidade do tipo de documento. A mesma entrega reapresentada fica só na versão mais nova. A rota da API acrescenta `fatos_relevantes_12_meses`: contagem calculada por ela, não coluna desta tabela. **Limite medido em 12/11/2026:** 3 protocolos repetem protocolo e versão com assunto e link diferentes (documentos distintos na mesma entrega). **Sem pessoa pela raiz:** toda raiz de CNPJ desta tabela existe na `cnpj_empresas_pj`, que só tem pessoa jurídica; CNPJ que não tem 14 dígitos conta como fora. A prova cobre quem a linha descreve, não o texto livre que ela carrega (o assunto de um evento, por exemplo). A conferência é `scripts/conferir_sem_pessoa.py`, rodada antes de cada concessão do piloto. **CPF no assunto:** o CPF que a empresa escreve no texto do assunto é trocado por `[CPF omitido]` na montagem (contagem só no `assunto`, em 12/11/2026: 5 linhas no acervo antes, 0 depois, 0 na cópia servida); o texto livre fora disso não é coberto pela marca.

- **Fonte:** CVM: dados abertos do IPE (documentos periódicos e eventuais), um arquivo por ano
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada montagem (`scripts/montar_base_historica.py`), que relê todos os arquivos anuais guardados (o IPE da CVM muda todo dia)
- **Atraso de divulgação:** Nenhum além da entrega: o documento vale a partir de `publicado_em`
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `protocolo`, `versao`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `publicado_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/eventos/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `protocolo` | Protocolo de entrega na CVM | texto |
| `versao` | Versão da entrega (fica a mais nova) | número inteiro |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `categoria` | Categoria do documento, como a CVM publica | texto |
| `tipo` | Tipo do documento, como a CVM publica (pode vir vazio) | texto |
| `assunto` | Assunto escrito pela empresa | texto |
| `rotulo` | Nome curto do tipo de documento (`src/eventos.py`) | texto |
| `tema` | resultados, proventos, eventos ou risco | texto |
| `materialidade` | Quanto o tipo de documento costuma importar (escolha editorial) | 0 a 100 |
| `referencia` | Data a que o documento se refere | data (dia) |
| `publicado_em` | Data de entrega à CVM | data (dia) |
| `link` | Endereço do documento original no sistema da CVM | texto |
| `ano_do_arquivo` | Ano do arquivo da CVM de onde a linha veio | ano |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `negociacoes`

Compras e vendas de ações e units por controladores, diretores, conselheiros e pela própria companhia (tesouraria), declaradas à CVM no VLMO desde 2018

- **Fonte:** CVM: dados abertos do VLMO (valores mobiliários negociados e detidos)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada montagem (`scripts/montar_base_historica.py`), que relê todos os arquivos anuais guardados (o VLMO é mensal)
- **Atraso de divulgação:** Até 10 dias depois do fim do mês da negociação (Resolução CVM 44); a linha vale a partir de `entregue_em`
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `fonte`, `documento`, `versao`, `cnpj`, `cargo`, `operacao`, `ativo`, `data`
- **Três datas:** aconteceu_em = `data`; publico_em = `entregue_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/negociacoes/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `fonte` | De onde veio a declaração (`cvm-vlmo`) | texto |
| `documento` | CNPJ e mês de referência do formulário (`cnpj|AAAA-MM`) | texto |
| `versao` | Versão do formulário (fica a mais nova) | número inteiro |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `cargo` | controlador, diretoria, conselho, conselho_fiscal, outros_orgaos ou companhia (tesouraria) | texto |
| `cargo_descricao` | Cargo por extenso (vazio no VLMO) | texto |
| `operacao` | compra ou venda | texto |
| `ativo` | Tipo e característica do valor mobiliário (até 80 letras) | texto |
| `data` | Data da negociação | data (dia) |
| `referencia` | Mês de referência do formulário (1º dia) | data (dia) |
| `entregue_em` | Data de entrega do formulário à CVM | data (dia) |
| `quantidade` | Quantidade negociada | ações |
| `preco` | Preço unitário informado | reais (R$) por ação |
| `valor` | Volume informado ou, sem ele, quantidade × preço | reais (R$) |
| `moeda` | Moeda (sempre BRL) | texto |
| `plano_10b5_1` | Plano de negociação da SEC (vazio na CVM) | verdadeiro ou falso |
| `link` | Endereço do formulário original no sistema da CVM | texto |
| `ano_do_arquivo` | Ano do arquivo da CVM de onde a linha veio | ano |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `proventos`

Dividendos e JCP de cada exercício pelo FRE de todos os anos guardados (a versão de longo prazo de `fre_proventos`, do app)

- **Fonte:** CVM: dados abertos do Formulário de Referência (FRE), tabela de distribuição
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada montagem (`scripts/montar_base_historica.py`), que relê todos os arquivos anuais guardados; a CVM tirou estas tabelas do FRE aberto depois de 2022 (Resolução CVM 59): os anos novos vêm vazios ou quase
- **Atraso de divulgação:** O FRE é entregue até 5 meses depois do fim do exercício e reapresentado a cada mudança
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`
- **Três datas:** aconteceu_em = `referencia`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/proventos/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `referencia` | Data de referência do FRE de onde a linha veio | data (dia) |
| `versao` | Versão desse FRE (1, 2, 3...) | número inteiro |
| `exercicio` | Fim do exercício social | data (dia) |
| `lucro_ajustado` | Lucro líquido ajustado, base da distribuição | reais (R$), já multiplicado pela escala informada |
| `dividendo_total` | Total distribuído (dividendos e JCP) | reais (R$), já multiplicado pela escala informada |
| `payout` | Parte do lucro ajustado distribuída | fração (0,25 = 25%) |
| `dividendos` | Dividendos declarados | reais (R$), já multiplicado pela escala informada |
| `jcp` | Juros sobre capital próprio declarados | reais (R$), já multiplicado pela escala informada |
| `ano_do_arquivo` | Ano do arquivo da CVM de onde a linha veio | ano |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `eventos_de_capital`

Desdobramentos, grupamentos, bonificações e aumentos de capital pelo FRE de todos os anos guardados (a versão de longo prazo de `fre_eventos_de_capital`, do app)

- **Fonte:** CVM: dados abertos do Formulário de Referência (FRE), tabelas de desdobramentos, grupamentos, bonificações e aumentos de capital
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada montagem (`scripts/montar_base_historica.py`), que relê todos os arquivos anuais guardados; a CVM tirou estas tabelas do FRE aberto depois de 2022 (Resolução CVM 59): os anos novos vêm vazios ou quase
- **Atraso de divulgação:** O FRE é entregue até 5 meses depois do fim do exercício e reapresentado a cada mudança
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`, `tipo`, `data`
- **Três datas:** aconteceu_em = `data`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/eventos_de_capital/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `referencia` | Data de referência do FRE de onde a linha veio | data (dia) |
| `versao` | Versão desse FRE (1, 2, 3...) | número inteiro |
| `tipo` | desdobramento, grupamento, bonificação ou aumento | texto |
| `data` | Data da aprovação ou da deliberação | data (dia) |
| `acoes_antes` | Ações antes do evento | ações |
| `acoes_depois` | Ações depois do evento | ações |
| `fator` | Depois ÷ antes (desdobramento de 1 para 10 = 10) | vezes |
| `acoes_novas` | Ações emitidas no aumento de capital | ações |
| `valor` | Valor do aumento de capital | reais (R$), já multiplicado pela escala informada |
| `ano_do_arquivo` | Ano do arquivo da CVM de onde a linha veio | ano |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `insolvencia`

Rótulos de recuperação judicial ou extrajudicial, pedido de falência, falência e liquidação lidos do IPE desde 2003, com a evidência de cada um: documento da categoria própria da CVM (`categoria_ipe`) ou fato relevante que anuncia o pedido (`fato_relevante`, costuma ser o primeiro sinal público). Desde a versão 2.0.0 o `rotulo` é da companhia que entregou o documento: quando ele fala de outra empresa (controlada, investida, devedora do CRI), vira `exposicao_a_terceiro` e o `evento` guarda o que aconteceu com a outra. Desde a 3.0.0 cada versão de uma entrega é uma linha, com a própria `conhecido_em`: a reapresentação não apaga a data da 1ª versão

- **Fonte:** CVM: dados abertos do IPE, um arquivo por ano (`base/rotulos.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada montagem (`scripts/montar_base_historica.py`), que relê todos os arquivos anuais guardados
- **Atraso de divulgação:** O rótulo vale a partir de `conhecido_em` (entrega à CVM)
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `protocolo`, `versao`, `rotulo`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 3.0.0
- **Onde fica:** Parquet em `<acervo>/base/insolvencia/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `rotulo` | O que aconteceu com a própria companhia: recuperacao_judicial, recuperacao_extrajudicial, recuperacao_judicial_ou_extrajudicial (a categoria da CVM não diz qual e nada antes disse), pedido_de_falencia, falencia ou liquidacao; ou exposicao_a_terceiro (o documento fala de outra empresa) | texto |
| `evento` | O que aconteceu, com quem for: os mesmos valores do rótulo, sem exposicao_a_terceiro | texto |
| `regra` | O que decidiu de quem é o evento: categoria_ipe ou fato_relevante (da própria, sem sinal contrário), texto_proprio, texto_de_terceiro, securitizadora, outra_empresa (palavras achadas) ou contexto_de_terceiro | texto |
| `evidencia` | categoria_ipe ou fato_relevante | texto |
| `categoria` | Categoria do documento, como a CVM publica | texto |
| `tipo` | Tipo do documento, como a CVM publica (pode vir vazio) | texto |
| `assunto` | Assunto escrito pela empresa | texto |
| `conhecido_em` | Data de entrega à CVM (quando ficou público) | data (dia) |
| `referencia` | Data a que o documento se refere | data (dia) |
| `protocolo` | Protocolo de entrega na CVM | texto |
| `versao` | Versão da entrega | número inteiro |
| `link` | Endereço do documento original no sistema da CVM | texto |
| `ano_do_arquivo` | Ano do arquivo da CVM de onde a linha veio | ano |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `cnpj_situacao_especial`

Estabelecimentos com "situação especial" no CNPJ da Receita (falido, em recuperação, em liquidação, intervenção...), um retrato por mês guardado: o histórico "como era na data" nasce da sequência dos retratos. Nome, endereço, telefone e e-mail nunca entram (LGPD). A linha do empresário individual, do MEI e da pessoa física (`trata_como_pessoa`, ADR 0075) não sai da porta.

- **Fonte:** Receita Federal: dados abertos do CNPJ, arquivos de estabelecimentos
- **Licença:** CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a Receita publica um retrato por mês; cada mês guardado vira um arquivo)
- **Atraso de divulgação:** A Receita publica o retrato do mês por volta do dia 10 a 15; ele vale desde `disponivel_em` (o fim do mês ou, se depois, o dia em que foi baixado). `data_situacao_especial` é a data que a Receita informa, que pode ser anterior ao retrato em que a linha apareceu pela primeira vez
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `cnpj`, `mes_do_retrato`
- **Três datas:** aconteceu_em = `data_situacao_especial`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 2.1.0
- **Onde fica:** Parquet em `<acervo>/base/cnpj_situacao_especial/<AAAA-MM>.parquet` (servidor de casa)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 dígitos): a empresa | texto |
| `matriz` | Verdadeiro na matriz, falso na filial | verdadeiro ou falso |
| `situacao_especial` | Situação especial, como a Receita escreve | texto |
| `rotulo` | falencia, recuperacao_judicial, recuperacao_extrajudicial, liquidacao, liquidacao_judicial, liquidacao_extrajudicial ou intervencao (vazio nas outras situações, como espólio) | texto |
| `data_situacao_especial` | Data da situação especial informada | data (dia) |
| `mes_do_retrato` | Mês do arquivo da Receita de onde a linha veio | AAAA-MM |
| `disponivel_em` | Desde quando o retrato era público: o fim do mês dele ou, se depois, o dia em que o arquivo foi baixado pela primeira vez (atraso, correção ou mês antigo baixado depois) | data (dia) |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada no dia da montagem não tem (ADR 0075): a linha não sai da porta | verdadeiro ou falso |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `cnpj_estabelecimentos`

Estabelecimentos (matriz e filiais) do CNPJ aberto da Receita, o retrato mais recente: situação cadastral, datas, atividade (CNAE), endereço e situação especial. Telefone, e-mail e nome fantasia nunca são lidos (LGPD, ADR 0106, item 3.5). O endereço de empresário individual e de MEI deve ficar só até o município e a UF, mas o leitor da tabela de empresas, que diz quem é quem, ainda não existe: por ora a carga grava o endereço inteiro de todos, e por isso a tabela conta como dado de pessoa. Finalidade: conhecer a empresa com quem se faz negócio (contraparte, crédito, compliance, fornecedor, M&A), a mesma da publicação pela Receita; base legal: legítimo interesse (LGPD, art. 7º, IX), com o RIPD da base e a ADR 0106

- **Fonte:** Receita Federal: dados abertos do CNPJ (`base/receita_retrato.py`, `scripts/carga_receita_mes.py`)
- **Licença:** CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)
- **Revenda:** vendável com atribuição à fonte
- **Ressalva de revenda:** CC BY: citar "Receita Federal, dados abertos do CNPJ" e o mês da extração em tudo o que sair
- **Frequência:** Mensal (a Receita publica uma pasta AAAA-MM por mês; a carga anda um mês por vez)
- **Atraso de divulgação:** A Receita põe a pasta do mês no ar durante o mês; a base conta como público o dia 27 (`base/receita_diff.py`, valor prudente até a medida no servidor)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `cnpj`
- **Três datas:** aconteceu_em = `data_situacao_cadastral`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<pasta da carga>/vigente/estabelecimentos/<2 primeiros caracteres da raiz>.parquet` (servidor de casa, `scripts/carga_receita_retrato.py`; o `manifesto.json` da pasta guarda o SHA-256 de cada ZIP lido)
- **Linhagem:** O `manifesto.json` da carga diz, por mês, o SHA-256 de cada ZIP da Receita lido; o ZIP dos meses âncora (05/2023, 01/2024, 01/2025 e 01/2026) fica no acervo (`rfb-cnpj`, `cnpj/<AAAA-MM>/`) e leva ao registro de coletas. A linha não leva a versão do código que a montou.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ com os 14 caracteres (com letras no CNPJ novo) | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `matriz` | Verdadeiro na matriz, falso na filial | verdadeiro ou falso |
| `situacao_cadastral` | Código da situação cadastral da Receita (2 ativa, 3 suspensa, 4 inapta, 8 baixada) | texto |
| `data_situacao_cadastral` | Data da situação cadastral; vazio quando a Receita põe zero | data (dia) |
| `motivo_situacao` | Código do motivo da situação cadastral, como a Receita publica | texto |
| `pais` | Código do país, só para quem tem sede fora do Brasil; vazio no resto | texto |
| `data_inicio_atividade` | Data de início da atividade; vazio quando a Receita põe zero | data (dia) |
| `cnae_principal` | Código da atividade principal (CNAE fiscal, 7 dígitos) | texto |
| `cnae_secundaria` | Códigos das atividades secundárias, separados por vírgula | texto |
| `tipo_logradouro` | Tipo do logradouro (rua, avenida...); vazio nas raízes só com município | texto |
| `logradouro` | Logradouro; vazio nas raízes só com município | texto |
| `numero` | Número do endereço; vazio nas raízes só com município | texto |
| `complemento` | Complemento do endereço; vazio nas raízes só com município | texto |
| `bairro` | Bairro; vazio nas raízes só com município | texto |
| `cep` | CEP; vazio nas raízes só com município | texto |
| `uf` | Sigla do estado | texto |
| `municipio` | Código do município na Receita (não é o código do IBGE) | texto |
| `situacao_especial` | Situação especial, como a Receita escreve; vazio quando não há | texto |
| `data_situacao_especial` | Data da situação especial informada | data (dia) |
| `dv_confere` | Falso quando o dígito verificador do CNPJ não confere; a linha fica, não é descartada | verdadeiro ou falso |

## `cnpj_estabelecimentos_mudancas`

O que mudou de um mês para o outro em `cnpj_estabelecimentos`: uma linha por entrada, saída ou mudança, com o valor de antes e o de depois; aplicadas em ordem sobre o retrato inicial, devolvem o retrato de qualquer mês (é o histórico "como era na data" do CNPJ). Finalidade: conhecer a empresa com quem se faz negócio (contraparte, crédito, compliance, fornecedor, M&A), a mesma da publicação pela Receita; base legal: legítimo interesse (LGPD, art. 7º, IX), com o RIPD da base e a ADR 0106

- **Fonte:** Receita Federal: dados abertos do CNPJ (`base/receita_retrato.py`, `scripts/carga_receita_mes.py`)
- **Licença:** CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)
- **Revenda:** vendável com atribuição à fonte
- **Ressalva de revenda:** CC BY: citar "Receita Federal, dados abertos do CNPJ" e o mês da extração em tudo o que sair
- **Frequência:** Mensal (a Receita publica uma pasta AAAA-MM por mês; a carga anda um mês por vez)
- **Atraso de divulgação:** A Receita põe a pasta do mês no ar durante o mês; a base conta como público o dia 27 (`base/receita_diff.py`, valor prudente até a medida no servidor)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `mes`, `cnpj`, `ordem`
- **Três datas:** publico_em = `mes`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<pasta da carga>/mudancas/estabelecimentos/<AAAA-MM>.parquet` (servidor de casa, `scripts/carga_receita_retrato.py`; o `manifesto.json` da pasta guarda o SHA-256 de cada ZIP lido)
- **Linhagem:** O `manifesto.json` da carga diz, por mês, o SHA-256 de cada ZIP da Receita lido; o ZIP dos meses âncora (05/2023, 01/2024, 01/2025 e 01/2026) fica no acervo (`rfb-cnpj`, `cnpj/<AAAA-MM>/`) e leva ao registro de coletas. A linha não leva a versão do código que a montou.

| Coluna | O que é | Unidade |
|---|---|---|
| `mes` | Mês do retrato em que a mudança apareceu | AAAA-MM |
| `tipo` | entrou, saiu ou mudou, de um mês para o seguinte | texto |
| `cnpj` | CNPJ com os 14 caracteres (com letras no CNPJ novo) | texto |
| `ordem` | Número da linha dentro da chave quando ela se repete (ordenada pelo conteúdo) | número inteiro |
| `cnpj_basico_antes` | Antes da mudança. Raiz do CNPJ (8 caracteres): a empresa | texto |
| `cnpj_basico_depois` | Depois da mudança. Raiz do CNPJ (8 caracteres): a empresa | texto |
| `matriz_antes` | Antes da mudança. Verdadeiro na matriz, falso na filial | verdadeiro ou falso |
| `matriz_depois` | Depois da mudança. Verdadeiro na matriz, falso na filial | verdadeiro ou falso |
| `situacao_cadastral_antes` | Antes da mudança. Código da situação cadastral da Receita (2 ativa, 3 suspensa, 4 inapta, 8 baixada) | texto |
| `situacao_cadastral_depois` | Depois da mudança. Código da situação cadastral da Receita (2 ativa, 3 suspensa, 4 inapta, 8 baixada) | texto |
| `data_situacao_cadastral_antes` | Antes da mudança. Data da situação cadastral; vazio quando a Receita põe zero | data (dia) |
| `data_situacao_cadastral_depois` | Depois da mudança. Data da situação cadastral; vazio quando a Receita põe zero | data (dia) |
| `motivo_situacao_antes` | Antes da mudança. Código do motivo da situação cadastral, como a Receita publica | texto |
| `motivo_situacao_depois` | Depois da mudança. Código do motivo da situação cadastral, como a Receita publica | texto |
| `pais_antes` | Antes da mudança. Código do país, só para quem tem sede fora do Brasil; vazio no resto | texto |
| `pais_depois` | Depois da mudança. Código do país, só para quem tem sede fora do Brasil; vazio no resto | texto |
| `data_inicio_atividade_antes` | Antes da mudança. Data de início da atividade; vazio quando a Receita põe zero | data (dia) |
| `data_inicio_atividade_depois` | Depois da mudança. Data de início da atividade; vazio quando a Receita põe zero | data (dia) |
| `cnae_principal_antes` | Antes da mudança. Código da atividade principal (CNAE fiscal, 7 dígitos) | texto |
| `cnae_principal_depois` | Depois da mudança. Código da atividade principal (CNAE fiscal, 7 dígitos) | texto |
| `cnae_secundaria_antes` | Antes da mudança. Códigos das atividades secundárias, separados por vírgula | texto |
| `cnae_secundaria_depois` | Depois da mudança. Códigos das atividades secundárias, separados por vírgula | texto |
| `tipo_logradouro_antes` | Antes da mudança. Tipo do logradouro (rua, avenida...); vazio nas raízes só com município | texto |
| `tipo_logradouro_depois` | Depois da mudança. Tipo do logradouro (rua, avenida...); vazio nas raízes só com município | texto |
| `logradouro_antes` | Antes da mudança. Logradouro; vazio nas raízes só com município | texto |
| `logradouro_depois` | Depois da mudança. Logradouro; vazio nas raízes só com município | texto |
| `numero_antes` | Antes da mudança. Número do endereço; vazio nas raízes só com município | texto |
| `numero_depois` | Depois da mudança. Número do endereço; vazio nas raízes só com município | texto |
| `complemento_antes` | Antes da mudança. Complemento do endereço; vazio nas raízes só com município | texto |
| `complemento_depois` | Depois da mudança. Complemento do endereço; vazio nas raízes só com município | texto |
| `bairro_antes` | Antes da mudança. Bairro; vazio nas raízes só com município | texto |
| `bairro_depois` | Depois da mudança. Bairro; vazio nas raízes só com município | texto |
| `cep_antes` | Antes da mudança. CEP; vazio nas raízes só com município | texto |
| `cep_depois` | Depois da mudança. CEP; vazio nas raízes só com município | texto |
| `uf_antes` | Antes da mudança. Sigla do estado | texto |
| `uf_depois` | Depois da mudança. Sigla do estado | texto |
| `municipio_antes` | Antes da mudança. Código do município na Receita (não é o código do IBGE) | texto |
| `municipio_depois` | Depois da mudança. Código do município na Receita (não é o código do IBGE) | texto |
| `situacao_especial_antes` | Antes da mudança. Situação especial, como a Receita escreve; vazio quando não há | texto |
| `situacao_especial_depois` | Depois da mudança. Situação especial, como a Receita escreve; vazio quando não há | texto |
| `data_situacao_especial_antes` | Antes da mudança. Data da situação especial informada | data (dia) |
| `data_situacao_especial_depois` | Depois da mudança. Data da situação especial informada | data (dia) |
| `dv_confere_antes` | Antes da mudança. Falso quando o dígito verificador do CNPJ não confere; a linha fica, não é descartada | verdadeiro ou falso |
| `dv_confere_depois` | Depois da mudança. Falso quando o dígito verificador do CNPJ não confere; a linha fica, não é descartada | verdadeiro ou falso |

## `cnpj_simples`

Opção pelo Simples Nacional e pelo MEI de cada empresa do CNPJ aberto da Receita, o retrato mais recente, com as datas de opção e de exclusão. Sem dado de pessoa além do próprio CNPJ. Finalidade: conhecer a empresa com quem se faz negócio (contraparte, crédito, compliance, fornecedor, M&A), a mesma da publicação pela Receita; base legal: legítimo interesse (LGPD, art. 7º, IX), com o RIPD da base e a ADR 0106

- **Fonte:** Receita Federal: dados abertos do CNPJ (`base/receita_retrato.py`, `scripts/carga_receita_mes.py`)
- **Licença:** CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)
- **Revenda:** vendável com atribuição à fonte
- **Ressalva de revenda:** CC BY: citar "Receita Federal, dados abertos do CNPJ" e o mês da extração em tudo o que sair
- **Frequência:** Mensal (a Receita publica uma pasta AAAA-MM por mês; a carga anda um mês por vez)
- **Atraso de divulgação:** A Receita põe a pasta do mês no ar durante o mês; a base conta como público o dia 27 (`base/receita_diff.py`, valor prudente até a medida no servidor)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `cnpj_basico`
- **Três datas:** nenhuma coluna da tabela traz estas datas
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<pasta da carga>/vigente/simples/<2 primeiros caracteres da raiz>.parquet` (servidor de casa, `scripts/carga_receita_retrato.py`; o `manifesto.json` da pasta guarda o SHA-256 de cada ZIP lido)
- **Linhagem:** O `manifesto.json` da carga diz, por mês, o SHA-256 de cada ZIP da Receita lido; o ZIP dos meses âncora (05/2023, 01/2024, 01/2025 e 01/2026) fica no acervo (`rfb-cnpj`, `cnpj/<AAAA-MM>/`) e leva ao registro de coletas. A linha não leva a versão do código que a montou.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `optante_simples` | Verdadeiro se a empresa é optante do Simples Nacional | verdadeiro ou falso |
| `data_opcao_simples` | Data da opção pelo Simples; vazio quando a Receita põe zero | data (dia) |
| `data_exclusao_simples` | Data da exclusão do Simples; vazio quando a Receita põe zero | data (dia) |
| `optante_mei` | Verdadeiro se a empresa é MEI | verdadeiro ou falso |
| `data_opcao_mei` | Data do enquadramento como MEI; vazio quando a Receita põe zero | data (dia) |
| `data_exclusao_mei` | Data do desenquadramento do MEI; vazio quando a Receita põe zero | data (dia) |

## `cnpj_simples_mudancas`

O que mudou de um mês para o outro em `cnpj_simples`: uma linha por entrada, saída ou mudança, com o valor de antes e o de depois; aplicadas em ordem sobre o retrato inicial, devolvem o retrato de qualquer mês (é o histórico "como era na data" do CNPJ). Finalidade: conhecer a empresa com quem se faz negócio (contraparte, crédito, compliance, fornecedor, M&A), a mesma da publicação pela Receita; base legal: legítimo interesse (LGPD, art. 7º, IX), com o RIPD da base e a ADR 0106

- **Fonte:** Receita Federal: dados abertos do CNPJ (`base/receita_retrato.py`, `scripts/carga_receita_mes.py`)
- **Licença:** CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)
- **Revenda:** vendável com atribuição à fonte
- **Ressalva de revenda:** CC BY: citar "Receita Federal, dados abertos do CNPJ" e o mês da extração em tudo o que sair
- **Frequência:** Mensal (a Receita publica uma pasta AAAA-MM por mês; a carga anda um mês por vez)
- **Atraso de divulgação:** A Receita põe a pasta do mês no ar durante o mês; a base conta como público o dia 27 (`base/receita_diff.py`, valor prudente até a medida no servidor)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `mes`, `cnpj_basico`, `ordem`
- **Três datas:** publico_em = `mes`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<pasta da carga>/mudancas/simples/<AAAA-MM>.parquet` (servidor de casa, `scripts/carga_receita_retrato.py`; o `manifesto.json` da pasta guarda o SHA-256 de cada ZIP lido)
- **Linhagem:** O `manifesto.json` da carga diz, por mês, o SHA-256 de cada ZIP da Receita lido; o ZIP dos meses âncora (05/2023, 01/2024, 01/2025 e 01/2026) fica no acervo (`rfb-cnpj`, `cnpj/<AAAA-MM>/`) e leva ao registro de coletas. A linha não leva a versão do código que a montou.

| Coluna | O que é | Unidade |
|---|---|---|
| `mes` | Mês do retrato em que a mudança apareceu | AAAA-MM |
| `tipo` | entrou, saiu ou mudou, de um mês para o seguinte | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `ordem` | Número da linha dentro da chave quando ela se repete (ordenada pelo conteúdo) | número inteiro |
| `optante_simples_antes` | Antes da mudança. Verdadeiro se a empresa é optante do Simples Nacional | verdadeiro ou falso |
| `optante_simples_depois` | Depois da mudança. Verdadeiro se a empresa é optante do Simples Nacional | verdadeiro ou falso |
| `data_opcao_simples_antes` | Antes da mudança. Data da opção pelo Simples; vazio quando a Receita põe zero | data (dia) |
| `data_opcao_simples_depois` | Depois da mudança. Data da opção pelo Simples; vazio quando a Receita põe zero | data (dia) |
| `data_exclusao_simples_antes` | Antes da mudança. Data da exclusão do Simples; vazio quando a Receita põe zero | data (dia) |
| `data_exclusao_simples_depois` | Depois da mudança. Data da exclusão do Simples; vazio quando a Receita põe zero | data (dia) |
| `optante_mei_antes` | Antes da mudança. Verdadeiro se a empresa é MEI | verdadeiro ou falso |
| `optante_mei_depois` | Depois da mudança. Verdadeiro se a empresa é MEI | verdadeiro ou falso |
| `data_opcao_mei_antes` | Antes da mudança. Data do enquadramento como MEI; vazio quando a Receita põe zero | data (dia) |
| `data_opcao_mei_depois` | Depois da mudança. Data do enquadramento como MEI; vazio quando a Receita põe zero | data (dia) |
| `data_exclusao_mei_antes` | Antes da mudança. Data do desenquadramento do MEI; vazio quando a Receita põe zero | data (dia) |
| `data_exclusao_mei_depois` | Depois da mudança. Data do desenquadramento do MEI; vazio quando a Receita põe zero | data (dia) |

## `cnpj_qsa`

Quadro de sócios e administradores das empresas do CNPJ aberto da Receita, o retrato mais recente. Traz tipo, qualificação, data de entrada, país e, para sócio pessoa física, só o pseudônimo `id_pessoa`. Nome, CPF mascarado e representante legal não entram: o nome fica no esquema `pessoas` (acervo restrito) e só sai de casa quando o portão dos nomes abrir (`base/pessoas/portao.py`, fechado, ADR 0106 item 4); CPF inteiro quebra a carga; faixa etária e representante legal nem são lidos. A porta é o CNPJ: não há busca por pessoa. Quem se opôs (art. 18) tem o id apagado. Finalidade: conhecer a empresa com quem se faz negócio (contraparte, crédito, compliance, fornecedor, M&A), a mesma da publicação pela Receita; base legal: legítimo interesse (LGPD, art. 7º, IX), com o RIPD da base e a ADR 0106

- **Fonte:** Receita Federal: dados abertos do CNPJ (`base/receita_retrato.py`, `scripts/carga_receita_mes.py`)
- **Licença:** CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)
- **Revenda:** vendável com atribuição à fonte
- **Ressalva de revenda:** CC BY: citar "Receita Federal, dados abertos do CNPJ" e o mês da extração em tudo o que sair
- **Frequência:** Mensal (a Receita publica uma pasta AAAA-MM por mês; a carga anda um mês por vez)
- **Atraso de divulgação:** A Receita põe a pasta do mês no ar durante o mês; a base conta como público o dia 27 (`base/receita_diff.py`, valor prudente até a medida no servidor)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `cnpj_basico`, `tipo_socio`, `raiz_socio_pj`, `id_pessoa`
- **Três datas:** aconteceu_em = `data_entrada`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<pasta da carga>/vigente/qsa/<2 primeiros caracteres da raiz>.parquet` (servidor de casa, `scripts/carga_receita_retrato.py`; o `manifesto.json` da pasta guarda o SHA-256 de cada ZIP lido)
- **Linhagem:** O `manifesto.json` da carga diz, por mês, o SHA-256 de cada ZIP da Receita lido; o ZIP dos meses âncora (05/2023, 01/2024, 01/2025 e 01/2026) fica no acervo (`rfb-cnpj`, `cnpj/<AAAA-MM>/`) e leva ao registro de coletas. A linha não leva a versão do código que a montou.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `tipo_socio` | 1 pessoa jurídica, 2 pessoa física ou 3 estrangeiro, como a Receita publica | texto |
| `raiz_socio_pj` | Raiz do CNPJ do sócio, só quando ele é pessoa jurídica; vazio nos outros | texto |
| `id_pessoa` | Pseudônimo (HMAC com chave fora do Git) do sócio pessoa física; vazio para sócio pessoa jurídica e para quem se opôs. O nome, que a Receita publica, fica só no esquema `pessoas` (acervo restrito, fora desta tabela) e atrás do portão dos nomes | texto |
| `qualificacao` | Código da qualificação do sócio (sócio-administrador, diretor...) | texto |
| `data_entrada` | Data de entrada na sociedade | data (dia) |
| `pais` | Código do país do sócio estrangeiro; vazio no resto | texto |

## `cnpj_qsa_mudancas`

O que mudou de um mês para o outro em `cnpj_qsa`: uma linha por entrada, saída ou mudança, com o valor de antes e o de depois; aplicadas em ordem sobre o retrato inicial, devolvem o retrato de qualquer mês (é o histórico "como era na data" do CNPJ). O sócio pessoa física é só o `id_pessoa`; o histórico de quem saiu nunca leva nome. Finalidade: conhecer a empresa com quem se faz negócio (contraparte, crédito, compliance, fornecedor, M&A), a mesma da publicação pela Receita; base legal: legítimo interesse (LGPD, art. 7º, IX), com o RIPD da base e a ADR 0106

- **Fonte:** Receita Federal: dados abertos do CNPJ (`base/receita_retrato.py`, `scripts/carga_receita_mes.py`)
- **Licença:** CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)
- **Revenda:** vendável com atribuição à fonte
- **Ressalva de revenda:** CC BY: citar "Receita Federal, dados abertos do CNPJ" e o mês da extração em tudo o que sair
- **Frequência:** Mensal (a Receita publica uma pasta AAAA-MM por mês; a carga anda um mês por vez)
- **Atraso de divulgação:** A Receita põe a pasta do mês no ar durante o mês; a base conta como público o dia 27 (`base/receita_diff.py`, valor prudente até a medida no servidor)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `mes`, `cnpj_basico`, `tipo_socio`, `raiz_socio_pj`, `id_pessoa`, `ordem`
- **Três datas:** publico_em = `mes`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<pasta da carga>/mudancas/qsa/<AAAA-MM>.parquet` (servidor de casa, `scripts/carga_receita_retrato.py`; o `manifesto.json` da pasta guarda o SHA-256 de cada ZIP lido)
- **Linhagem:** O `manifesto.json` da carga diz, por mês, o SHA-256 de cada ZIP da Receita lido; o ZIP dos meses âncora (05/2023, 01/2024, 01/2025 e 01/2026) fica no acervo (`rfb-cnpj`, `cnpj/<AAAA-MM>/`) e leva ao registro de coletas. A linha não leva a versão do código que a montou.

| Coluna | O que é | Unidade |
|---|---|---|
| `mes` | Mês do retrato em que a mudança apareceu | AAAA-MM |
| `tipo` | entrou, saiu ou mudou, de um mês para o seguinte | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `tipo_socio` | 1 pessoa jurídica, 2 pessoa física ou 3 estrangeiro, como a Receita publica | texto |
| `raiz_socio_pj` | Raiz do CNPJ do sócio, só quando ele é pessoa jurídica; vazio nos outros | texto |
| `id_pessoa` | Pseudônimo (HMAC com chave fora do Git) do sócio pessoa física; vazio para sócio pessoa jurídica e para quem se opôs. O nome, que a Receita publica, fica só no esquema `pessoas` (acervo restrito, fora desta tabela) e atrás do portão dos nomes | texto |
| `ordem` | Número da linha dentro da chave quando ela se repete (ordenada pelo conteúdo) | número inteiro |
| `qualificacao_antes` | Antes da mudança. Código da qualificação do sócio (sócio-administrador, diretor...) | texto |
| `qualificacao_depois` | Depois da mudança. Código da qualificação do sócio (sócio-administrador, diretor...) | texto |
| `data_entrada_antes` | Antes da mudança. Data de entrada na sociedade | data (dia) |
| `data_entrada_depois` | Depois da mudança. Data de entrada na sociedade | data (dia) |
| `pais_antes` | Antes da mudança. Código do país do sócio estrangeiro; vazio no resto | texto |
| `pais_depois` | Depois da mudança. Código do país do sócio estrangeiro; vazio no resto | texto |

## `cnpj_simples_historico`

Opção pelo Simples Nacional e pelo MEI de cada empresa, versão por versão desde 05/2023, com desde quando cada uma era pública: a versão que vale na data D é a última com `disponivel_em` até D. Montada do retrato vigente e das mudanças mensais da base do CNPJ; a última versão de cada raiz é conferida com o vigente. A tabela tem as raízes de empresário individual e MEI (CNPJ de pessoa natural, `optante_mei`): a rota da API tira essas linhas, e a tabela em si não as separa. Finalidade: conhecer a empresa com quem se faz negócio (contraparte, crédito, compliance, fornecedor, M&A), a mesma da publicação pela Receita; base legal: legítimo interesse (LGPD, art. 7º, IX), com o RIPD da base e a ADR 0106

- **Fonte:** Receita Federal: dados abertos do CNPJ, `Simples.zip` (`scripts/montar_historico_do_cnpj.py simples`)
- **Licença:** CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)
- **Revenda:** vendável com atribuição à fonte
- **Ressalva de revenda:** CC BY: citar "Receita Federal, dados abertos do CNPJ" e o mês da extração em tudo o que sair
- **Frequência:** Mensal: cada retrato novo da Receita só acrescenta versões; as antigas não mudam
- **Atraso de divulgação:** A Receita põe a pasta do mês no ar por volta do dia 14; a versão vale desde o dia 21 do mês (`disponivel_em`). As datas de opção e de exclusão do Simples são as que a Receita informa e podem ser anteriores ao retrato em que apareceram
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim em casa (raízes de empresário individual e MEI); a rota da API tira essas linhas
- **Chaves:** `cnpj_basico`, `mes_do_retrato`
- **Três datas:** publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/cnpj_simples_historico/<2 primeiros caracteres da raiz>.parquet` (servidor de casa)
- **Linhagem:** Cada linha guarda o SHA-256 do ZIP da Receita do mês dela (`origem_sha256`, vazio na versão "saiu do arquivo"); o manifesto de cada Parquet lista os ZIPs de todos os meses. `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `mes_do_retrato` | Mês do arquivo da Receita em que a versão apareceu; o primeiro mês da base (2023-05) traz o que já estava lá | AAAA-MM |
| `disponivel_em` | Desde quando a versão era pública: o dia 21 do mês do retrato, o piso de publicação (`base/receita_diff.disponivel_em`, dia 14 mais 7 de folga). Vale até a versão seguinte. A porta, como nas outras fontes de governo, só a mostra a partir do último dia do mês | data (dia) |
| `consta` | Falso quando a raiz saiu do arquivo naquele mês (os campos vêm vazios) | verdadeiro ou falso |
| `optante_simples` | Verdadeiro se a empresa é optante do Simples Nacional | verdadeiro ou falso |
| `data_opcao_simples` | Data da opção pelo Simples; vazio quando a Receita põe zero | data (dia) |
| `data_exclusao_simples` | Data da exclusão do Simples; vazio quando a Receita põe zero | data (dia) |
| `optante_mei` | Verdadeiro se a empresa é MEI | verdadeiro ou falso |
| `data_opcao_mei` | Data do enquadramento como MEI; vazio quando a Receita põe zero | data (dia) |
| `data_exclusao_mei` | Data do desenquadramento do MEI; vazio quando a Receita põe zero | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `cnpj_situacao_cadastral`

Situação cadastral de cada estabelecimento (01 nula, 02 ativa, 03 suspensa, 04 inapta, 08 baixada), com a data e o motivo, versão por versão desde 05/2023 e com desde quando cada uma era pública: a versão que vale na data D é a última com `disponivel_em` até D. Montada do retrato vigente e das mudanças mensais dos estabelecimentos da base do CNPJ (linha 841); só nasce versão quando a situação, a data, o motivo ou a matriz mudam, e a última versão de cada estabelecimento é conferida com o vigente. **Só pessoa jurídica:** entram só os estabelecimentos das raízes de `cnpj_estabelecimentos_pj` do mesmo mês do vigente (fora MEI, empresário individual e grupo 4); quem hoje não é só empresa some da história inteira. Nome fantasia, razão social, endereço e contatos nem são lidos (ADR 0106). Finalidade: conhecer a empresa com quem se faz negócio (contraparte, crédito, compliance, fornecedor, M&A), a mesma da publicação pela Receita; base legal: legítimo interesse (LGPD, art. 7º, IX), com o RIPD da base e a ADR 0106

- **Fonte:** Receita Federal: dados abertos do CNPJ, arquivos de estabelecimentos (`scripts/montar_historico_do_cnpj.py situacao`)
- **Licença:** CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)
- **Revenda:** vendável com atribuição à fonte
- **Ressalva de revenda:** CC BY: citar "Receita Federal, dados abertos do CNPJ" e o mês da extração em tudo o que sair
- **Frequência:** Mensal: cada retrato novo da Receita só acrescenta versões; as antigas não mudam
- **Atraso de divulgação:** A Receita põe a pasta do mês no ar por volta do dia 14; a versão vale desde o dia 21 do mês (`disponivel_em`)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `mes_do_retrato`
- **Três datas:** aconteceu_em = `data_situacao_cadastral`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 2.0.0
- **Onde fica:** Parquet em `<acervo>/base/cnpj_situacao_cadastral/<2 primeiros caracteres do CNPJ>.parquet` (servidor de casa)
- **Linhagem:** Cada linha guarda o SHA-256 do ZIP da Receita do mês dela (`origem_sha256`, vazio na versão "saiu do arquivo"); o manifesto de cada Parquet lista os ZIPs de todos os meses. `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ do estabelecimento (14 dígitos, com a pontuação) | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `mes_do_retrato` | Mês do arquivo da Receita em que a versão apareceu; o primeiro mês da base (2023-05) traz o que já estava lá | AAAA-MM |
| `disponivel_em` | Desde quando a versão era pública: o dia 21 do mês do retrato, o piso de publicação (`base/receita_diff.disponivel_em`, dia 14 mais 7 de folga). Vale até a versão seguinte. A porta, como nas outras fontes de governo, só a mostra a partir do último dia do mês | data (dia) |
| `consta` | Falso quando o estabelecimento saiu do arquivo naquele mês (os campos vêm vazios) | verdadeiro ou falso |
| `matriz` | Verdadeiro na matriz, falso na filial | verdadeiro ou falso |
| `situacao_cadastral` | Código da situação cadastral: 01 nula, 02 ativa, 03 suspensa, 04 inapta, 08 baixada | texto |
| `data_situacao_cadastral` | Data da situação cadastral que a Receita informa; pode ser anterior ao retrato em que a versão apareceu | data (dia) |
| `motivo_situacao` | Código do motivo da situação cadastral, como a Receita publica (tabela de motivos) | texto |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `cnpj_empresas_historico`

Natureza jurídica e razão social de cada empresa, versão por versão desde 05/2023, com desde quando cada uma era pública. Montada mês a mês dos `Empresas*.zip`. **A razão social de pessoa nunca entra:** a do empresário individual e do MEI (213-5) e a do grupo 4 (pessoas físicas) trazem o nome e o CPF da pessoa e saem vazias no leitor (ADR 0106); nas outras, um CPF escrito no texto sai. Capital, porte, qualificação do responsável e ente federativo não são lidos. A tabela tem as raízes de empresário individual (2135) e MEI, com a razão social vazia; a rota da API tira essas linhas. Finalidade: conhecer a empresa com quem se faz negócio (contraparte, crédito, compliance, fornecedor, M&A), a mesma da publicação pela Receita; base legal: legítimo interesse (LGPD, art. 7º, IX), com o RIPD da base e a ADR 0106

- **Fonte:** Receita Federal: dados abertos do CNPJ, `Empresas*.zip` (`scripts/montar_historico_do_cnpj.py empresas`)
- **Licença:** CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)
- **Revenda:** vendável com atribuição à fonte
- **Ressalva de revenda:** CC BY: citar "Receita Federal, dados abertos do CNPJ" e o mês da extração em tudo o que sair
- **Frequência:** Mensal: cada retrato novo da Receita só acrescenta versões; as antigas não mudam
- **Atraso de divulgação:** A Receita põe a pasta do mês no ar por volta do dia 14; a versão vale desde o dia 21 do mês (`disponivel_em`). As datas de opção e de exclusão do Simples são as que a Receita informa e podem ser anteriores ao retrato em que apareceram
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim em casa (raízes de empresário individual e MEI); a rota da API tira essas linhas
- **Chaves:** `cnpj_basico`, `mes_do_retrato`
- **Três datas:** publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/cnpj_empresas_historico/<2 primeiros caracteres da raiz>.parquet` (servidor de casa; `meses.json` diz os meses já acrescentados e o SHA-256 de cada ZIP)
- **Linhagem:** Cada linha guarda o SHA-256 do ZIP da Receita do mês dela (`origem_sha256`, vazio na versão "saiu do arquivo"); o manifesto de cada Parquet lista os ZIPs de todos os meses. `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `mes_do_retrato` | Mês do arquivo da Receita em que a versão apareceu; o primeiro mês da base (2023-05) traz o que já estava lá | AAAA-MM |
| `disponivel_em` | Desde quando a versão era pública: o dia 21 do mês do retrato, o piso de publicação (`base/receita_diff.disponivel_em`, dia 14 mais 7 de folga). Vale até a versão seguinte. A porta, como nas outras fontes de governo, só a mostra a partir do último dia do mês | data (dia) |
| `consta` | Falso quando a raiz saiu do arquivo naquele mês (os campos vêm vazios) | verdadeiro ou falso |
| `natureza_juridica` | Código da natureza jurídica (tabela da Receita, 4 dígitos: 2062 limitada, 2054 S.A. fechada, 2046 S.A. aberta, 2135 empresário individual) | texto |
| `razao_social` | Razão social como a Receita publica; vazia para empresário individual, MEI e grupo 4 (é o nome da pessoa) | texto |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `cnpj_empresas_pj`

Razão social, natureza jurídica e porte de toda pessoa jurídica do CNPJ aberto da Receita, o retrato do mês. **Sem pessoa:** o empresário individual (213-5) e o grupo 4 (pessoas físicas) nem entram, porque a razão social deles é o nome da pessoa; CPF escrito no texto sai. Sem sócios. **Limite da conferência:** a Receita é a única que publica o CNPJ, então ele é conferido contra o que outro órgão cadastra do mesmo CNPJ, e só nisso: a conferência cobre os CNPJs que esse outro órgão registra, não é amostra dos ~21 milhões; MEI e pessoa física não entram. As taxas de acordo e os pisos estão em `base/cruzada_por_taxa.py`. Nesta tabela: a razão social contra a CVM; o nome no IF.data, do Banco Central, só informa (abaixo do piso). Finalidade: conhecer a empresa com quem se faz negócio (contraparte, crédito, compliance, fornecedor, M&A), a mesma da publicação pela Receita; base legal: legítimo interesse (LGPD, art. 7º, IX), com o RIPD da base e a ADR 0106

- **Fonte:** Receita Federal: dados abertos do CNPJ (`scripts/montar_empresas_pj.py`)
- **Licença:** CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)
- **Revenda:** vendável com atribuição à fonte
- **Ressalva de revenda:** CC BY: citar "Receita Federal, dados abertos do CNPJ" e o mês da extração em tudo o que sair
- **Frequência:** Mensal (a Receita publica uma pasta AAAA-MM por mês; a carga anda um mês por vez)
- **Atraso de divulgação:** A Receita põe a pasta do mês no ar durante o mês; a base conta como público o dia 27 (`base/receita_diff.py`, valor prudente até a medida no servidor)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `cnpj_basico`
- **Três datas:** publico_em = `disponivel_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.1.0
- **Onde fica:** Parquet em `<acervo>/base/cnpj_empresas_pj/<2 primeiros caracteres da raiz>.parquet` (servidor de casa)
- **Linhagem:** Cada linha guarda o SHA-256 do ZIP da Receita do mês dela (`origem_sha256`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `razao_social` | Razão social como a Receita publica | texto |
| `natureza_juridica` | Código da natureza jurídica (tabela da Receita, 4 dígitos) | texto |
| `porte` | nao_informado, micro, pequeno ou demais (códigos 00, 01, 03 e 05 da Receita) | texto |
| `capital_social` | Capital social declarado à Receita (aproximação do porte, não é faturamento; 0 se ilegível) | reais (R$) |
| `n_estabelecimentos` | Estabelecimentos ativos da raiz (matriz e filiais) no retrato, contados na montagem | número inteiro |
| `mes_do_retrato` | Mês do arquivo da Receita de onde a linha veio | AAAA-MM |
| `disponivel_em` | Desde quando o retrato era público: o dia 21 do mês dele (`base/receita_diff.disponivel_em`). A porta, como nas outras fontes de governo, só o mostra a partir do último dia do mês | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `cnpj_estabelecimentos_pj`

Estabelecimentos (matriz e filiais) das pessoas jurídicas de `cnpj_empresas_pj`, o retrato do mês: situação cadastral, abertura, atividade (CNAE), UF e município. **Sem pessoa:** fica de fora o MEI, a raiz que `cnpj_empresas_pj` não tem e todo endereço fino (logradouro, CEP...). Telefone, e-mail e nome fantasia nunca são lidos (LGPD, ADR 0106, item 3.5). **Limite da conferência:** a Receita é a única que publica o CNPJ, então ele é conferido contra o que outro órgão cadastra do mesmo CNPJ, e só nisso: a conferência cobre os CNPJs que esse outro órgão registra, não é amostra dos ~21 milhões; MEI e pessoa física não entram. As taxas de acordo e os pisos estão em `base/cruzada_por_taxa.py`. Nesta tabela: a UF contra ANATEL, ANVISA e ANCINE, e contra o IF.data, do Banco Central. A UF se confere contra ANATEL, ANVISA e ANCINE; divergência de UF costuma ser mudança de sede ou outra filial da mesma raiz. Finalidade: conhecer a empresa com quem se faz negócio (contraparte, crédito, compliance, fornecedor, M&A), a mesma da publicação pela Receita; base legal: legítimo interesse (LGPD, art. 7º, IX), com o RIPD da base e a ADR 0106

- **Fonte:** Receita Federal: dados abertos do CNPJ (`scripts/montar_empresas_pj.py`)
- **Licença:** CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)
- **Revenda:** vendável com atribuição à fonte
- **Ressalva de revenda:** CC BY: citar "Receita Federal, dados abertos do CNPJ" e o mês da extração em tudo o que sair
- **Frequência:** Mensal (a Receita publica uma pasta AAAA-MM por mês; a carga anda um mês por vez)
- **Atraso de divulgação:** A Receita põe a pasta do mês no ar durante o mês; a base conta como público o dia 27 (`base/receita_diff.py`, valor prudente até a medida no servidor)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`
- **Três datas:** publico_em = `disponivel_em`; aconteceu_em = `data_inicio_atividade`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/cnpj_estabelecimentos_pj/<2 primeiros caracteres da raiz>.parquet` (servidor de casa)
- **Linhagem:** Cada linha guarda o SHA-256 do ZIP da Receita do mês dela (`origem_sha256`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ com os 14 caracteres (com letras no CNPJ novo) | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `matriz` | Verdadeiro na matriz, falso na filial | verdadeiro ou falso |
| `situacao_cadastral` | Código da situação cadastral da Receita (2 ativa, 3 suspensa, 4 inapta, 8 baixada) | texto |
| `data_inicio_atividade` | Data de início da atividade; vazio quando a Receita põe zero | data (dia) |
| `cnae_principal` | Código da atividade principal (CNAE fiscal, 7 dígitos) | texto |
| `uf` | Sigla do estado | texto |
| `municipio` | Código do município na Receita (não é o código do IBGE) | texto |
| `mes_do_retrato` | Mês do arquivo da Receita de onde a linha veio | AAAA-MM |
| `disponivel_em` | Desde quando o retrato era público: o dia 21 do mês dele (`base/receita_diff.disponivel_em`). A porta, como nas outras fontes de governo, só o mostra a partir do último dia do mês | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `entradas_de_socio_pj`

Entradas e saídas de sócio pessoa jurídica no quadro de sócios da Receita: que empresa entrou como sócia de que empresa, com a data de entrada que a Receita dá, e o mês em que a base viu a entrada (ou a saída). Diz quem já fez movimentos parecidos, não quem quer comprar: holding de família, reorganização e aumento de capital também entram, e entrar como sócio não é aquisição. **Sem pessoa:** só sócio do tipo 1 e só raízes de `cnpj_estabelecimentos_pj`, dos dois lados (fora MEI, empresário individual e grupo 4, mesmo com CNPJ); a lista é a do mês mais recente, e quem deixou de ser só empresa some da história inteira. Sair e entrar com os mesmos dados no mesmo mês não conta. **As mudanças de setembro de 2024 aparecem em outubro de 2024:** o arquivo de sócios da Receita de 2024-09 tirou uns 115 mil sócios PJ que voltaram em outubro e pôs uns 113 mil que só existem nele, então a base compara outubro direto com agosto. Sair e voltar depois conta como entrada nova; a Receita trocar a data de entrada de quem continuou é `data_corrigida`, não entrada. Antes de 2023-06 só há quem ainda estava no primeiro retrato: quem entrou e saiu antes disso não aparece. Finalidade: conhecer a empresa com quem se faz negócio (contraparte, crédito, compliance, fornecedor, M&A), a mesma da publicação pela Receita; base legal: legítimo interesse (LGPD, art. 7º, IX), com o RIPD da base e a ADR 0106

- **Fonte:** Receita Federal: dados abertos do CNPJ, quadro de sócios vigente e mudanças de cada mês (`scripts/montar_entradas_de_socio_pj.py`)
- **Licença:** CC BY, ficha do CNPJ no dados.gov.br lida em 20/10/2026 (citar a Receita)
- **Revenda:** vendável com atribuição à fonte
- **Ressalva de revenda:** CC BY: citar "Receita Federal, dados abertos do CNPJ" e o mês da extração em tudo o que sair
- **Frequência:** Mensal (a Receita publica uma pasta AAAA-MM por mês; a carga anda um mês por vez)
- **Atraso de divulgação:** A Receita põe a pasta do mês no ar durante o mês; a base conta como público o dia 27 (`base/receita_diff.py`, valor prudente até a medida no servidor)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `movimento`, `cnpj_basico`, `raiz_socio_pj`, `data_entrada`, `mes_do_retrato`
- **Três datas:** publico_em = `disponivel_em`; aconteceu_em = `data_entrada`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/entradas_de_socio_pj/<2 primeiros caracteres da raiz da empresa>.parquet` (servidor de casa)
- **Linhagem:** Derivada de `cnpj_qsa`, `cnpj_qsa_mudancas` e `cnpj_estabelecimentos_pj`; o manifesto de cada Parquet lista o SHA-256 dos ZIPs de sócios da Receita de todos os meses lidos. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `movimento` | entrou, saiu ou data_corrigida (a Receita trocou a data de entrada de quem continuou) | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres) da empresa em que o sócio entrou ou de que saiu | texto |
| `raiz_socio_pj` | Raiz do CNPJ (8 caracteres) da pessoa jurídica que entrou como sócia ou saiu | texto |
| `data_entrada` | Data de entrada na sociedade, como a Receita publica (na saída, a da entrada que acabou) | data (dia) |
| `qualificacao` | Código da qualificação do sócio no mês em que a base viu o movimento | texto |
| `mes_do_retrato` | Mês do arquivo da Receita em que a base viu o movimento; para quem já estava no primeiro retrato (2023-05), esse mês | AAAA-MM |
| `disponivel_em` | Desde quando o movimento era público: o dia 21 do mês do retrato (`base/receita_diff.disponivel_em`). A porta, como nas outras fontes de governo, só o mostra a partir do último dia do mês | data (dia) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `anvisa_por_empresa`

Quantos registros a empresa tem na Anvisa, por tipo (cosméticos, produtos para saúde, saneantes, alimentos, medicamentos, autorização de funcionamento e certificado de boas práticas): o total e os que estão em vigor, uma linha por raiz de CNPJ e por retrato do arquivo da Anvisa. **É um sinal de porte, uma aproximação, não faturamento:** um registro não diz quanto a empresa vende, e empresa pequena pode ter muitos produtos. **Sem pessoa:** só pessoa jurídica; a raiz que tem qualquer linha de empresário individual, MEI, natureza do grupo 4 ou CNPJ que a Receita guardada não tem sai inteira, nos totais e nos ativos. Cada registro conta uma vez (a versão mais nova vista até o retrato), o que saiu do arquivo não conta, e situação vazia ou fora do vocabulário nunca conta como ativa. Medicamento com apresentações de situações diferentes ('Ativo / Inativo') conta como ativo. O retrato mais antigo é de 2026-10-29 (o arquivista começou ali): antes disso a base não viu a Anvisa.

- **Fonte:** Anvisa: dados abertos, consultas de empresas e de produtos, contados de `anvisa_registros` (`scripts/montar_anvisa_por_empresa.py`)
- **Licença:** CC BY (dados abertos da Anvisa no dados.gov.br; citar a Anvisa)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (um retrato por dia de arquivo da Anvisa que o arquivista guardou)
- **Atraso de divulgação:** A fonte publica o estado de hoje sem dizer desde quando. **Por dia, não por mês** (decisão da Diretoria, 12/11/2026, só para esta tabela): o retrato vale desde o dia em que o arquivista viu o arquivo (`visto_em`), nunca desde a data de referência da Anvisa nem um dia antes. A `anvisa_registros`, de que ela deriva, continua por mês (contrato publicado; mudar pede versão maior). Motivo: a contagem é nossa, feita sobre o que o arquivista já guardou, e esperar o fim do mês esconderia um dado que a base já tinha na véspera
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `cnpj_basico`, `disponivel_em`
- **Três datas:** publico_em = `disponivel_em`; coletado_em = `montado_em`
- **Histórico desde:** 2026-10-29 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/anvisa_por_empresa/anvisa_por_empresa.parquet` (servidor de casa, `scripts/montar_anvisa_por_empresa.py`)
- **Linhagem:** Derivada de `anvisa_registros`; o manifesto lista o SHA-256 de cada cadastro lido. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `disponivel_em` | Dia do arquivo da Anvisa que este retrato conta (só o que a base tinha visto até ele), que é o dia em que o arquivista o viu. A porta o mostra desde esse dia | data (dia) |
| `trata_como_pessoa` | Sempre falso: a raiz com alguma linha de pessoa já saiu na montagem. Fica para a porta recusar uma linha que um dia vier diferente (ADR 0075) | verdadeiro ou falso |
| `cosmeticos_total` | Registros de cosméticos da empresa, em vigor ou não | número inteiro |
| `cosmeticos_ativos` | Registros de cosméticos da empresa que estão em vigor (a situação 'ativa' muda de nome por tipo) | número inteiro |
| `produtos_saude_total` | Registros de produtos para saúde da empresa, em vigor ou não | número inteiro |
| `produtos_saude_ativos` | Registros de produtos para saúde da empresa que estão em vigor (a situação 'ativa' muda de nome por tipo) | número inteiro |
| `saneantes_total` | Registros de saneantes da empresa, em vigor ou não | número inteiro |
| `saneantes_ativos` | Registros de saneantes da empresa que estão em vigor (a situação 'ativa' muda de nome por tipo) | número inteiro |
| `alimentos_total` | Registros de alimentos da empresa, em vigor ou não | número inteiro |
| `alimentos_ativos` | Registros de alimentos da empresa que estão em vigor (a situação 'ativa' muda de nome por tipo) | número inteiro |
| `medicamentos_total` | Registros de medicamentos da empresa, em vigor ou não | número inteiro |
| `medicamentos_ativos` | Registros de medicamentos da empresa que estão em vigor (a situação 'ativa' muda de nome por tipo) | número inteiro |
| `produtos_total` | Registros de produtos (a soma dos cinco tipos de produto) da empresa, em vigor ou não | número inteiro |
| `produtos_ativos` | Registros de produtos (a soma dos cinco tipos de produto) da empresa que estão em vigor (a situação 'ativa' muda de nome por tipo) | número inteiro |
| `afe_total` | Registros de autorizações de funcionamento (AFE) da empresa, em vigor ou não | número inteiro |
| `afe_ativos` | Registros de autorizações de funcionamento (AFE) da empresa que estão em vigor (a situação 'ativa' muda de nome por tipo) | número inteiro |
| `cbpf_total` | Registros de certificados de boas práticas de fabricação (CBPF) da empresa, em vigor ou não | número inteiro |
| `cbpf_ativos` | Registros de certificados de boas práticas de fabricação (CBPF) da empresa que estão em vigor (a situação 'ativa' muda de nome por tipo) | número inteiro |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `pgfn_divida`

Dívida ativa da União (PGFN) por CNPJ de empresa, um retrato por trimestre guardado: uma linha por CNPJ, tipo de dívida (não previdenciária, previdenciária, FGTS), região da PGFN, tipo de devedor, situação e ajuizamento, com quantas inscrições e o valor somado. Só pessoa jurídica com CNPJ de dígito certo (ADR 0075): pessoa física, CPF e nome nunca entram; empresário individual e MEI ficam com `trata_como_pessoa` e a porta não os serve.

- **Fonte:** PGFN: dados abertos da dívida ativa (SIDA, Previdência e FGTS; `base/pgfn.py`)
- **Licença:** Dados abertos da PGFN (rodapé CC BY-ND do site: perguntar a licença)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Trimestral (a PGFN publica um retrato por trimestre; cada CSV guardado vira um arquivo)
- **Atraso de divulgação:** O retrato do fim do trimestre sai semanas depois (o de 2026-06 foi gerado em 23/07); a PGFN não diz quando publicou, então `disponivel_em` é o dia em que o arquivista viu o arquivo pela primeira vez, e a porta o lê pelo último dia do mês, como as outras fontes de governo (o conservador; a história começa em 14/10/2026)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `cnpj`, `tipo_divida`, `regiao`, `tipo_devedor`, `tipo_situacao`, `situacao_inscricao`, `ajuizado`, `data_do_retrato`
- **Três datas:** aconteceu_em = `data_do_retrato`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.1
- **Onde fica:** Parquet em `<acervo>/base/pgfn_divida/<AAAA-MM>/<sistema>-<região>-<1º caractere do CNPJ>.parquet`, 11 por CSV da PGFN (servidor de casa, `scripts/carga_pgfn.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `tipo_divida` | nao_previdenciaria (SIDA), previdenciaria ou fgts: o arquivo da PGFN de onde veio | texto |
| `regiao` | Região da PGFN no nome do arquivo (1 a 6, ou NA) | texto |
| `tipo_devedor` | principal, corresponsavel ou solidario | texto |
| `tipo_situacao` | Grupo da situação, como a PGFN escreve (Em cobrança, Suspenso por decisão judicial, Benefício Fiscal, Garantia) | texto |
| `situacao_inscricao` | Situação da inscrição, como a PGFN escreve (ATIVA AJUIZADA, ATIVA EM COBRANCA...) | texto |
| `ajuizado` | Verdadeiro se a cobrança já está na Justiça | verdadeiro ou falso |
| `inscricoes` | Quantas inscrições somadas nesta linha | número inteiro |
| `valor_consolidado` | Valor consolidado somado das inscrições | reais (R$), já multiplicado pela escala informada |
| `primeira_inscricao` | Data da inscrição mais antiga (vazia se a PGFN não informa) | data (dia) |
| `ultima_inscricao` | Data da inscrição mais recente | data (dia) |
| `data_do_retrato` | Último dia do mês do retrato da PGFN | data (dia) |
| `gerado_em` | Data dos CSVs dentro do ZIP (informativa: não é a de publicação) | data (dia) |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075): nada negativo sobre ele sai da base | verdadeiro ou falso |
| `disponivel_em` | Dia em que o arquivista viu o arquivo pela primeira vez (quando ficou público para a base) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `sancoes_cgu`

Sanções da CGU por CNPJ de empresa: CEIS (inidôneas e suspensas), CNEP (punidas pela Lei Anticorrupção, com o valor da multa), CEPIM (entidades sem fins lucrativos impedidas de receber convênio) e acordos de leniência. Uma linha por valor diferente de cada sanção: a mudança (situação, fim, valor) vira linha nova que só vale desde o dia em que foi vista, e a sanção que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só pessoa jurídica com CNPJ de dígito certo (ADR 0075): pessoa física, CPF e nome nunca entram, nem a razão social; empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade das sanções do anterior é pulado: é arquivo quebrado da fonte, não sanção que acabou. Os efeitos de cada acordo de leniência (o 2º arquivo do ZIP) ainda não entram.

- **Fonte:** CGU: Portal da Transparência, download de dados do CEIS, CNEP, CEPIM e acordos de leniência (`base/sancoes.py`)
- **Licença:** Dados abertos da CGU (Decreto 8.777/2016; citar a CGU)
- **Revenda:** só uso interno (entra em modelo; nunca vender nem exportar o dado)
- **Frequência:** Diária (o portal gera um arquivo por dia; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** A fonte não diz quando cada linha entrou no arquivo: no 1º arquivo guardado vale a data de publicação ou de informação (o que a fonte diz), e depois o dia em que o arquivista viu a mudança (o conservador; a história guardada começa em 14/10/2026)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `cadastro`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `inicio`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/sancoes_cgu/<cadastro>.parquet` (servidor de casa, `scripts/carga_sancoes.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cadastro` | De que cadastro veio: ceis, cnep, cepim, leniencia ou penalidades (ANS) | texto |
| `id_na_fonte` | O código da sanção na fonte (no CEPIM, que não tem código: o CNPJ e o convênio) | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `categoria` | O tipo da sanção como a fonte escreve (Suspensão, Inidoneidade, Multa Pecuniária, o motivo do impedimento no CEPIM, Acordo de leniência) | texto |
| `situacao` | Situação do acordo (leniência) ou da demanda (ANS), como a fonte escreve | texto |
| `assunto` | Tipo do processo na ANS (Consumidor, Econômico-financeiro...) | texto |
| `orgao` | Órgão que aplicou a sanção (no CEPIM, o concedente do convênio) | texto |
| `uf_do_orgao` | UF do órgão sancionador | texto |
| `esfera_do_orgao` | Esfera do órgão (FEDERAL, ESTADUAL, MUNICIPAL) | texto |
| `origem_da_informacao` | Quem informou a sanção à CGU | texto |
| `fundamentacao_legal` | A lei em que a sanção se baseia | texto |
| `abrangencia` | Abrangência da sanção, como a CGU escreve | texto |
| `processo` | Número do processo (no CEPIM, o do convênio) | texto |
| `inicio` | Início da sanção ou do acordo; na ANS, a data da decisão de 1ª instância. Pode ser depois da publicação (a sanção publicada que só vale adiante) | data (dia) |
| `fim` | Fim da sanção ou do acordo (vazio: sem prazo ou não informado) | data (dia) |
| `publicado_em` | Publicação oficial (Diário Oficial; na ANS, a da 1ª instância) | data (dia) |
| `transito_em_julgado` | Trânsito em julgado, quando a fonte informa | data (dia) |
| `informado_em` | Quando o órgão informou a sanção à CGU (data de origem da informação) | data (dia) |
| `valor_multa` | Valor da multa (CNEP; na ANS, a multa final aplicada) | reais (R$), já multiplicado pela escala informada |
| `consta` | Verdadeiro enquanto a sanção está no arquivo; falso na linha do dia em que saiu dele (acabou, foi excluída ou anulada) | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075): nada negativo sobre ele sai da base | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a publicação ou a informação ao órgão (a que for depois), nunca depois do dia do arquivo; depois dele, o dia do arquivo em que a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `ans_penalidades`

Penalidades aplicadas pela ANS a operadoras de planos de saúde, por CNPJ: o tipo do processo, a situação da demanda, as datas da 1ª instância e a multa final. Uma linha por valor diferente de cada sanção: a mudança (situação, fim, valor) vira linha nova que só vale desde o dia em que foi vista, e a sanção que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só pessoa jurídica com CNPJ de dígito certo (ADR 0075): pessoa física, CPF e nome nunca entram, nem a razão social; empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade das sanções do anterior é pulado: é arquivo quebrado da fonte, não sanção que acabou.

- **Fonte:** ANS: dados abertos, penalidades aplicadas a operadoras (`base/sancoes.py`)
- **Licença:** CC BY (dados abertos da ANS no dados.gov.br; citar a ANS)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a ANS recarrega o arquivo inteiro; `NR_COMPETENCIA_CARGA` diz o mês)
- **Atraso de divulgação:** A fonte não diz quando cada linha entrou no arquivo: no 1º arquivo guardado vale a data de publicação ou de informação (o que a fonte diz), e depois o dia em que o arquivista viu a mudança (o conservador; a história guardada começa em 14/10/2026)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `cadastro`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `inicio`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ans_penalidades/penalidades.parquet` (servidor de casa, `scripts/carga_sancoes.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cadastro` | De que cadastro veio: ceis, cnep, cepim, leniencia ou penalidades (ANS) | texto |
| `id_na_fonte` | O código da sanção na fonte (no CEPIM, que não tem código: o CNPJ e o convênio) | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `categoria` | O tipo da sanção como a fonte escreve (Suspensão, Inidoneidade, Multa Pecuniária, o motivo do impedimento no CEPIM, Acordo de leniência) | texto |
| `situacao` | Situação do acordo (leniência) ou da demanda (ANS), como a fonte escreve | texto |
| `assunto` | Tipo do processo na ANS (Consumidor, Econômico-financeiro...) | texto |
| `orgao` | Órgão que aplicou a sanção (no CEPIM, o concedente do convênio) | texto |
| `uf_do_orgao` | UF do órgão sancionador | texto |
| `esfera_do_orgao` | Esfera do órgão (FEDERAL, ESTADUAL, MUNICIPAL) | texto |
| `origem_da_informacao` | Quem informou a sanção à CGU | texto |
| `fundamentacao_legal` | A lei em que a sanção se baseia | texto |
| `abrangencia` | Abrangência da sanção, como a CGU escreve | texto |
| `processo` | Número do processo (no CEPIM, o do convênio) | texto |
| `inicio` | Início da sanção ou do acordo; na ANS, a data da decisão de 1ª instância. Pode ser depois da publicação (a sanção publicada que só vale adiante) | data (dia) |
| `fim` | Fim da sanção ou do acordo (vazio: sem prazo ou não informado) | data (dia) |
| `publicado_em` | Publicação oficial (Diário Oficial; na ANS, a da 1ª instância) | data (dia) |
| `transito_em_julgado` | Trânsito em julgado, quando a fonte informa | data (dia) |
| `informado_em` | Quando o órgão informou a sanção à CGU (data de origem da informação) | data (dia) |
| `valor_multa` | Valor da multa (CNEP; na ANS, a multa final aplicada) | reais (R$), já multiplicado pela escala informada |
| `consta` | Verdadeiro enquanto a sanção está no arquivo; falso na linha do dia em que saiu dele (acabou, foi excluída ou anulada) | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075): nada negativo sobre ele sai da base | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a publicação ou a informação ao órgão (a que for depois), nunca depois do dia do arquivo; depois dele, o dia do arquivo em que a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `processos_comunicacoes`

Processos judiciais por companhia aberta: as comunicações. Uma linha por comunicação publicada no DJEN (intimação, citação, edital) de um processo em que uma companhia aberta é parte, achada pela razão social do cadastro da CVM ou, depois, pelo número do processo (a que intima só a outra parte). Sem a Justiça do Trabalho (Resolução CNJ 121/2010 proíbe a consulta pública dela pelo nome da parte) e sem nome de pessoa física: as partes que não são companhia nem órgão público entram só na contagem. Só as companhias com registro ativo hoje, pela razão social de hoje: a que saiu da CVM fica sem histórico, e a comunicação com o nome antigo de quem mudou de razão social não entra (viés de sobrevivência).

- **Fonte:** CNJ: Diário de Justiça Eletrônico Nacional, API pública de comunicações processuais, e as Tabelas Processuais Unificadas (`base/arquivo/djen.py`, `base/arquivo/cnj_tpu.py`, `base/processos.py`)
- **Licença:** DJEN do CNJ, público; citar CNJ e tribunal; sem a Justiça do Trabalho
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Semanal (a semana fechada de cada companhia; o histórico desde 2025 aos poucos)
- **Atraso de divulgação:** A comunicação vale desde o dia em que foi disponibilizada no DJEN (`disponivel_em`); a consulta da semana roda depois do domingo, e o histórico desde 2025 entra aos poucos
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `id_na_fonte`
- **Três datas:** aconteceu_em = `disponivel_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2025-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.2.0
- **Onde fica:** Parquet em `<acervo>/base/processos_comunicacoes/djen.parquet` (servidor de casa, `scripts/carga_processos.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O `hash` da comunicação no DJEN (único) | texto |
| `id_djen` | O número da comunicação na API do DJEN | número inteiro |
| `numero_processo` | Número único do processo (CNJ, NNNNNNN-DD.AAAA.J.TR.OOOO), com o dígito conferido | texto |
| `ano_do_processo` | Ano em que o processo foi ajuizado (o AAAA do número) | ano |
| `justica` | Segmento da Justiça pelo número (Estadual, Federal, STJ...) | texto |
| `tribunal` | Sigla do tribunal (TJSP, TRF3, STJ...) | texto |
| `orgao` | Vara, câmara ou turma que publicou, em maiúsculas | texto |
| `classe_codigo` | Código da classe processual nas tabelas do CNJ | texto |
| `classe` | Classe processual (procedimento comum, execução fiscal...) | texto |
| `tipo_comunicacao` | Intimação, citação, edital... | texto |
| `tipo_documento` | Despacho, decisão, sentença, acórdão... | texto |
| `meio` | Meio da comunicação, como o DJEN escreve | texto |
| `link` | Endereço do documento no sistema do tribunal | texto |
| `cancelada_em` | Dia em que o tribunal cancelou a comunicação (vazio: não cancelada); antes dele, valia | data (dia) |
| `companhias` | Quantas partes são companhias abertas ligadas ao CNPJ | número inteiro |
| `orgaos_publicos` | Quantas partes são órgãos públicos | número inteiro |
| `pessoas_juridicas` | Quantas partes são outras empresas (ou nome de mais de uma companhia do cadastro) | número inteiro |
| `pessoas_ou_desconhecidas` | Quantas partes são pessoas ou não têm tipo claro | número inteiro |
| `advogados` | Quantos advogados a comunicação cita (os nomes não entram) | número inteiro |
| `tipo_de_ato` | O ato publicado (`sentenca`, `acordao`, `decisao`, `despacho`, `despacho_ou_decisao`, `ato_ordinatorio`, `ata_de_julgamento`, `pauta`, `distribuicao`, `edital`, `certidao`), pelo tipo do documento; no tipo genérico, `sentenca` só com o dispositivo de uma. Vazio: não identificado ou não conferido | texto |
| `resultado` | O que a comunicação decide, pela fórmula do dispositivo (`procedente`, `parcialmente_procedente`, `improcedente`, `acordo_homologado`, `extinto`, `recurso_provido`, `recurso_parcialmente_provido`, `recurso_nao_provido`). É o resultado do pedido, não o da companhia: quem ganhou depende do polo (`processos_partes`). Vazio: sem dispositivo claro, dois que se contradizem, lista de muitos processos ou não conferido | texto |
| `resultado_trecho` | A fórmula que provou o resultado ("JULGO PROCEDENTE", "NEGO PROVIMENTO"); o que fica entre o verbo e a palavra-chave vira "..." (nenhum texto livre) | texto |
| `valor_citado` | O maior valor em reais escrito no teor (condenação, causa ou honorários: o que o texto cita, não o valor da causa) | reais (R$), já multiplicado pela escala informada |
| `teor_conferido_em` | Dia da conferência automática que cobre a linha (amostra com semente, gabarito de um segundo modelo, precisão mínima de 95% por campo; regra e modelo que discordam deixam o campo vazio). Vazio: nenhuma conferência ainda cobre a comunicação, e o teor fica vazio | data (dia) |
| `achada_por` | `nome` (a busca pela razão social achou: a companhia está entre as partes) ou `numero` (só a busca pelo número do processo achou) | texto |
| `disponibilizada_em` | Dia em que a comunicação saiu no DJEN, como o tribunal informou (a achada pelo número pode ter saído antes de `disponivel_em`) | data (dia) |
| `disponivel_em` | Dia em que a comunicação foi disponibilizada no DJEN (nunca depois de `visto_em`): desde quando a linha vale para a base. A achada pelo número vale a partir da primeira comunicação do processo com uma companhia entre as partes | data (dia) |
| `visto_em` | Dia da consulta guardada que trouxe esta versão da linha | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `processos_partes`

Processos judiciais por companhia aberta: as companhias (com o CNPJ) e os órgãos públicos de cada comunicação, com o polo. Uma linha por comunicação publicada no DJEN (intimação, citação, edital) de um processo em que uma companhia aberta é parte, achada pela razão social do cadastro da CVM ou, depois, pelo número do processo (a que intima só a outra parte). Sem a Justiça do Trabalho (Resolução CNJ 121/2010 proíbe a consulta pública dela pelo nome da parte) e sem nome de pessoa física: as partes que não são companhia nem órgão público entram só na contagem. Só as companhias com registro ativo hoje, pela razão social de hoje: a que saiu da CVM fica sem histórico, e a comunicação com o nome antigo de quem mudou de razão social não entra (viés de sobrevivência).

- **Fonte:** CNJ: Diário de Justiça Eletrônico Nacional, API pública de comunicações processuais, e as Tabelas Processuais Unificadas (`base/arquivo/djen.py`, `base/arquivo/cnj_tpu.py`, `base/processos.py`)
- **Licença:** DJEN do CNJ, público; citar CNJ e tribunal; sem a Justiça do Trabalho
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Semanal (a semana fechada de cada companhia; o histórico desde 2025 aos poucos)
- **Atraso de divulgação:** A comunicação vale desde o dia em que foi disponibilizada no DJEN (`disponivel_em`); a consulta da semana roda depois do domingo, e o histórico desde 2025 entra aos poucos
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `id_na_fonte`, `polo`, `parte`
- **Três datas:** aconteceu_em = `disponivel_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2025-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/processos_partes/djen.parquet` (servidor de casa, `scripts/carga_processos.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O `hash` da comunicação (liga a `processos_comunicacoes`) | texto |
| `numero_processo` | Número único do processo (CNJ) | texto |
| `polo` | `ativo` (autor), `passivo` (réu) ou `outro` | texto |
| `tipo_parte` | `companhia` ou `orgao_publico` | texto |
| `parte` | Quem é a parte: o `cnpj` da companhia ou o `orgao_publico` | texto |
| `cnpj` | CNPJ da companhia (14 caracteres, sem pontuação); vazio no órgão público | texto |
| `empresa` | Razão social da companhia no cadastro da CVM | texto |
| `orgao_publico` | Nome do órgão público, normalizado (maiúsculas, sem acento) | texto |
| `disponivel_em` | Dia em que a comunicação foi disponibilizada no DJEN (nunca depois de `visto_em`): desde quando a linha vale para a base. A achada pelo número vale a partir da primeira comunicação do processo com uma companhia entre as partes | data (dia) |
| `visto_em` | Dia da consulta guardada que trouxe esta versão da linha | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `processos`

Processos judiciais por companhia aberta: uma linha por processo, com o que a primeira comunicação diz e a classe pela TPU do CNJ. A classe é a do começo: a mudança (o cumprimento de sentença, o recurso) está nas comunicações. Uma linha por comunicação publicada no DJEN (intimação, citação, edital) de um processo em que uma companhia aberta é parte, achada pela razão social do cadastro da CVM ou, depois, pelo número do processo (a que intima só a outra parte). Sem a Justiça do Trabalho (Resolução CNJ 121/2010 proíbe a consulta pública dela pelo nome da parte) e sem nome de pessoa física: as partes que não são companhia nem órgão público entram só na contagem. Só as companhias com registro ativo hoje, pela razão social de hoje: a que saiu da CVM fica sem histórico, e a comunicação com o nome antigo de quem mudou de razão social não entra (viés de sobrevivência).

- **Fonte:** CNJ: Diário de Justiça Eletrônico Nacional, API pública de comunicações processuais, e as Tabelas Processuais Unificadas (`base/arquivo/djen.py`, `base/arquivo/cnj_tpu.py`, `base/processos.py`)
- **Licença:** DJEN do CNJ, público; citar CNJ e tribunal; sem a Justiça do Trabalho
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Semanal (a semana fechada de cada companhia; o histórico desde 2025 aos poucos)
- **Atraso de divulgação:** A comunicação vale desde o dia em que foi disponibilizada no DJEN (`disponivel_em`); a consulta da semana roda depois do domingo, e o histórico desde 2025 entra aos poucos
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `numero_processo`
- **Três datas:** aconteceu_em = `primeira_comunicacao`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2025-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/processos/djen.parquet` (servidor de casa, `scripts/carga_processos.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `numero_processo` | Número único do processo (CNJ, NNNNNNN-DD.AAAA.J.TR.OOOO), com o dígito conferido | texto |
| `ano_do_processo` | Ano em que o processo foi ajuizado (o AAAA do número) | ano |
| `justica` | Segmento da Justiça pelo número (Estadual, Federal, STJ...) | texto |
| `tribunal` | Sigla do tribunal (TJSP, TRF3, STJ...) | texto |
| `orgao` | Vara, câmara ou turma da primeira comunicação, em maiúsculas | texto |
| `classe_codigo` | Código da classe na primeira comunicação (Tabelas Processuais Unificadas do CNJ) | texto |
| `classe` | Classe da primeira comunicação, como o DJEN escreve | texto |
| `classe_tpu` | Nome da classe na TPU do CNJ (vazio se a TPU não tem o código) | texto |
| `classe_caminho` | As classes da TPU da raiz até a desta, separadas por ` > ` | texto |
| `ramo` | Agrupamento nosso pela classe mais próxima na TPU: execucao_fiscal, insolvencia, coletivo, juizado_especial, criminal, recurso, cumprimento_de_sentenca, execucao, conhecimento (vazio: sem ramo conhecido) | texto |
| `primeira_comunicacao` | Dia da primeira comunicação do processo no DJEN que a base tem | data (dia) |
| `disponivel_em` | Dia da primeira comunicação do processo com uma companhia entre as partes: desde quando se sabe que o processo é de uma companhia | data (dia) |
| `visto_em` | Dia da consulta guardada que trouxe essa comunicação | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `processos_datajud`

Processos judiciais por companhia aberta, pelo DataJud: um retrato de cada processo, por grau, a cada consulta (classe, assuntos, órgão julgador, ajuizamento). **Só uso interno:** o termo de uso da API Pública do DataJud (itens 3.3 e 3.8) veda o uso comercial e a consultoria, então a tabela só treina e rotula (`coletas.FONTES_SO_INTERNAS`) e não sai em tela, relatório, API nem exportação. Só os processos que o DJEN ligou a uma companhia aberta pelo nome (`processos_comunicacoes`), sem a Justiça do Trabalho. O DataJud não traz as partes: nenhum nome de pessoa.

- **Fonte:** CNJ: DataJud, API Pública, um índice por tribunal (`base/arquivo/datajud.py`, `base/processos_datajud.py`)
- **Licença:** DataJud do CNJ: só uso interno (termo de uso, itens 3.3 e 3.8)
- **Revenda:** só uso interno (entra em modelo; nunca vender nem exportar o dado)
- **Frequência:** Semanal (o processo volta a ser consultado quando o DJEN mostra comunicação nova)
- **Atraso de divulgação:** O processo é consultado na semana seguinte à comunicação mais recente do DJEN; a linha vale desde o dia da consulta (`disponivel_em`), porque o DataJud não diz quando cada dado ficou público
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `numero_processo`, `grau`, `visto_em`
- **Três datas:** aconteceu_em = `ajuizado_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-05 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/processos_datajud/datajud.parquet` (servidor de casa, `scripts/carga_processos.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `numero_processo` | Número único do processo (CNJ, NNNNNNN-DD.AAAA.J.TR.OOOO), com o dígito conferido | texto |
| `ano_do_processo` | Ano em que o processo foi ajuizado (o AAAA do número) | ano |
| `justica` | A justiça pelo J do número (Justiça Estadual, Justiça Federal...) | texto |
| `tribunal` | Sigla do tribunal no DataJud (TJSP, TRF3...) | texto |
| `grau` | Grau no DataJud: G1, G2, JE (juizado), TR (turma recursal), SUP... | texto |
| `classe_codigo` | Código da classe (Tabelas Processuais Unificadas do CNJ) | texto |
| `classe` | Nome da classe, como o DataJud escreve | texto |
| `assuntos_codigos` | Códigos dos assuntos na TPU, separados por `;` | texto |
| `assuntos` | Nomes dos assuntos, separados por `; ` | texto |
| `orgao_julgador_codigo` | Código do órgão julgador no CNJ | texto |
| `orgao_julgador` | Vara, câmara ou turma, como o DataJud escreve | texto |
| `ajuizado_em` | Dia do ajuizamento (`dataAjuizamento`) | data (dia) |
| `atualizado_na_fonte_em` | Última atualização do processo no DataJud | data e hora (UTC) |
| `nivel_sigilo` | Nível de sigilo no DataJud (0: público) | número inteiro |
| `sistema` | Sistema processual do tribunal (PJe, eproc, SAJ...) | texto |
| `formato` | Eletrônico ou físico | texto |
| `movimentos` | Quantos movimentos a consulta trouxe | número inteiro |
| `ultimo_movimento_codigo` | Código TPU do movimento mais recente da consulta | texto |
| `ultimo_movimento_em` | Quando aconteceu o movimento mais recente da consulta | data e hora (UTC) |
| `disponivel_em` | Dia da consulta: desde quando a linha vale para a base | data (dia) |
| `visto_em` | Dia da consulta guardada que trouxe esta versão da linha | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `processos_datajud_movimentos`

Processos judiciais por companhia aberta, pelo DataJud: os movimentos de cada processo (distribuição, sentença, recurso, trânsito em julgado), uma linha por movimento. **Só uso interno:** o termo de uso da API Pública do DataJud (itens 3.3 e 3.8) veda o uso comercial e a consultoria, então a tabela só treina e rotula (`coletas.FONTES_SO_INTERNAS`) e não sai em tela, relatório, API nem exportação. Só os processos que o DJEN ligou a uma companhia aberta pelo nome (`processos_comunicacoes`), sem a Justiça do Trabalho. O DataJud não traz as partes: nenhum nome de pessoa.

- **Fonte:** CNJ: DataJud, API Pública, um índice por tribunal (`base/arquivo/datajud.py`, `base/processos_datajud.py`)
- **Licença:** DataJud do CNJ: só uso interno (termo de uso, itens 3.3 e 3.8)
- **Revenda:** só uso interno (entra em modelo; nunca vender nem exportar o dado)
- **Frequência:** Semanal (o processo volta a ser consultado quando o DJEN mostra comunicação nova)
- **Atraso de divulgação:** O processo é consultado na semana seguinte à comunicação mais recente do DJEN; a linha vale desde o dia da consulta (`disponivel_em`), porque o DataJud não diz quando cada dado ficou público
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `numero_processo`, `grau`, `aconteceu_em`, `movimento_codigo`, `complementos`
- **Três datas:** aconteceu_em = `aconteceu_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-05 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/processos_datajud_movimentos/datajud.parquet` (servidor de casa, `scripts/carga_processos.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `numero_processo` | Número único do processo (CNJ, NNNNNNN-DD.AAAA.J.TR.OOOO), com o dígito conferido | texto |
| `grau` | Grau no DataJud: G1, G2, JE (juizado), TR (turma recursal), SUP... | texto |
| `movimento_codigo` | Código do movimento (Tabelas Processuais Unificadas do CNJ) | texto |
| `movimento` | Nome do movimento, como o DataJud escreve | texto |
| `complementos` | Complementos tabelados do CNJ, `nome: descrição`, separados por `; ` (texto vazio: sem complemento) | texto |
| `aconteceu_em` | Quando o movimento aconteceu, como o tribunal informou | data e hora (UTC) |
| `disponivel_em` | Primeiro dia em que uma consulta mostrou o movimento: desde quando a linha vale (o movimento pode ter acontecido muito antes) | data (dia) |
| `visto_em` | Dia da primeira consulta que trouxe o movimento | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `anvisa_registros`

Licenças da Anvisa por CNPJ: autorização de funcionamento (AFE), certificados de boas práticas de fabricação (CBPF) e os produtos registrados (medicamentos, saneantes, cosméticos, produtos para saúde e alimentos). Uma linha por valor diferente de cada registro: a mudança (situação, vencimento, cancelamento) vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo, com letras ou não: CPF e CNPJ mascarado saem na coleta; razão social, nome de fantasia, endereço, contato e responsável técnico nunca chegam ao acervo. Empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado.

- **Fonte:** Anvisa: dados abertos, consultas de empresas e de produtos (`base/licencas.py`)
- **Licença:** CC BY (dados abertos da Anvisa no dados.gov.br; citar a Anvisa)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a fonte recarrega o arquivo inteiro; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** A fonte publica o estado de hoje sem dizer desde quando: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 29/10/2026); as datas da fonte ficam nas colunas delas
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `cadastro`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `concedido_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-29 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/anvisa_registros/<cadastro>.parquet` (servidor de casa, `scripts/carga_licencas.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cadastro` | De que arquivo veio: afe, cbpf, cbpf_medicamento, medicamentos, saneantes, cosmeticos, produtos_saude, alimentos (Anvisa); rntrc (ANTT); produto_veterinario, aviacao_agricola (MAPA); outorgas (Anatel); o tipo de título (ANM); agentes (Ancine) | texto |
| `id_na_fonte` | O que identifica o registro no arquivo (o código da fonte, ou as colunas que o identificam juntas por `|`); nos medicamentos, o tipo de autorização + o código (`REGISTRADO|937`: o mesmo código é um registrado de uma empresa e um notificado de outra), e o CNPJ, o registro e o processo no fim se a chave aparecer com dois deles | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `registro` | Número da licença na fonte: autorização (AFE), certificado (CBPF), registro do produto, RNTRC, registro do estabelecimento (MAPA), Fistel da outorga, registro na Ancine | texto |
| `processo` | Número do processo no órgão | texto |
| `categoria` | O tipo, como a fonte escreve: tipo de produto (AFE), tipo de certificado, categoria regulatória, categoria do transportador, atividade (MAPA), tipo de outorga, tipo de requerimento (ANM), classificação do agente (Ancine) | texto |
| `descricao` | O que a licença cobre: atividades (AFE), assunto (CBPF), nome do produto, classificação (MAPA), serviço notificado (Anatel), substâncias (ANM), natureza jurídica (Ancine) | texto |
| `complemento` | Um dado a mais de cada fonte: número novo da AFE, país da fábrica inspecionada (CBPF), transportador equiparado (RNTRC), característica ou aeronave (MAPA), Fistel da notificação (Anatel), tipo de uso (ANM), brasileiro independente (Ancine) | texto |
| `situacao` | A situação como a fonte escreve hoje (ativo, vencido, cancelado, fase atual do título...): vale desde o dia do arquivo, nunca antes. Nos medicamentos, todas as situações das apresentações do produto, em ordem alfabética (`Ativo / Inativo`): nenhuma vence, e a de cada apresentação não está no arquivo | texto |
| `uf` | UF da empresa ou do estabelecimento, quando a fonte informa | texto |
| `municipio` | Município, quando a fonte informa | texto |
| `concedido_em` | Data da concessão, autorização, inclusão ou registro, quando a fonte informa | data (dia) |
| `publicado_em` | Publicação da licença (Diário Oficial), quando a fonte informa | data (dia) |
| `vence_em` | Vencimento da licença ou do registro (nos alimentos da Anvisa, que só dão o mês, o 1º dia do mês) | data (dia) |
| `cancelado_em` | Cancelamento, quando a fonte informa | data (dia) |
| `situacao_desde` | Desde quando vale a situação (só o RNTRC informa) | data (dia) |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte publica o estado de hoje sem dizer desde quando) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `antt_rntrc`

Transportadores rodoviários de carga com registro na ANTT (RNTRC), por CNPJ. Uma linha por valor diferente de cada registro: a mudança (situação, vencimento, cancelamento) vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo, com letras ou não: CPF e CNPJ mascarado saem na coleta; razão social, nome de fantasia, endereço, contato e responsável técnico nunca chegam ao acervo. Empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado.

- **Fonte:** ANTT: dados abertos, RNTRC (um arquivo por mês, cada um com o cadastro inteiro) (`base/licencas.py`)
- **Licença:** CC BY (dados abertos da ANTT; citar a ANTT)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a fonte recarrega o arquivo inteiro; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** A fonte publica o estado de hoje sem dizer desde quando: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 29/10/2026); as datas da fonte ficam nas colunas delas
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `cadastro`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `concedido_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-29 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/antt_rntrc/<cadastro>.parquet` (servidor de casa, `scripts/carga_licencas.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cadastro` | De que arquivo veio: afe, cbpf, cbpf_medicamento, medicamentos, saneantes, cosmeticos, produtos_saude, alimentos (Anvisa); rntrc (ANTT); produto_veterinario, aviacao_agricola (MAPA); outorgas (Anatel); o tipo de título (ANM); agentes (Ancine) | texto |
| `id_na_fonte` | O que identifica o registro no arquivo (o código da fonte, ou as colunas que o identificam juntas por `|`); nos medicamentos, o tipo de autorização + o código (`REGISTRADO|937`: o mesmo código é um registrado de uma empresa e um notificado de outra), e o CNPJ, o registro e o processo no fim se a chave aparecer com dois deles | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `registro` | Número da licença na fonte: autorização (AFE), certificado (CBPF), registro do produto, RNTRC, registro do estabelecimento (MAPA), Fistel da outorga, registro na Ancine | texto |
| `processo` | Número do processo no órgão | texto |
| `categoria` | O tipo, como a fonte escreve: tipo de produto (AFE), tipo de certificado, categoria regulatória, categoria do transportador, atividade (MAPA), tipo de outorga, tipo de requerimento (ANM), classificação do agente (Ancine) | texto |
| `descricao` | O que a licença cobre: atividades (AFE), assunto (CBPF), nome do produto, classificação (MAPA), serviço notificado (Anatel), substâncias (ANM), natureza jurídica (Ancine) | texto |
| `complemento` | Um dado a mais de cada fonte: número novo da AFE, país da fábrica inspecionada (CBPF), transportador equiparado (RNTRC), característica ou aeronave (MAPA), Fistel da notificação (Anatel), tipo de uso (ANM), brasileiro independente (Ancine) | texto |
| `situacao` | A situação como a fonte escreve hoje (ativo, vencido, cancelado, fase atual do título...): vale desde o dia do arquivo, nunca antes. Nos medicamentos, todas as situações das apresentações do produto, em ordem alfabética (`Ativo / Inativo`): nenhuma vence, e a de cada apresentação não está no arquivo | texto |
| `uf` | UF da empresa ou do estabelecimento, quando a fonte informa | texto |
| `municipio` | Município, quando a fonte informa | texto |
| `concedido_em` | Data da concessão, autorização, inclusão ou registro, quando a fonte informa | data (dia) |
| `publicado_em` | Publicação da licença (Diário Oficial), quando a fonte informa | data (dia) |
| `vence_em` | Vencimento da licença ou do registro (nos alimentos da Anvisa, que só dão o mês, o 1º dia do mês) | data (dia) |
| `cancelado_em` | Cancelamento, quando a fonte informa | data (dia) |
| `situacao_desde` | Desde quando vale a situação (só o RNTRC informa) | data (dia) |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte publica o estado de hoje sem dizer desde quando) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `mapa_sipeagro`

Estabelecimentos registrados no MAPA (SIPEAGRO) por CNPJ: produto veterinário e aviação agrícola. Os outros arquivos do SIPEAGRO mascaram o CNPJ e ficam de fora (nunca se cruza pelo nome). Uma linha por valor diferente de cada registro: a mudança (situação, vencimento, cancelamento) vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo, com letras ou não: CPF e CNPJ mascarado saem na coleta; razão social, nome de fantasia, endereço, contato e responsável técnico nunca chegam ao acervo. Empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado.

- **Fonte:** MAPA: dados abertos do SIPEAGRO (`base/licencas.py`)
- **Licença:** CC BY (dados abertos do MAPA, SIPEAGRO, no dados.gov.br; citar o MAPA)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a fonte recarrega o arquivo inteiro; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** A fonte publica o estado de hoje sem dizer desde quando: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 29/10/2026); as datas da fonte ficam nas colunas delas
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `cadastro`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `concedido_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-29 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/mapa_sipeagro/<cadastro>.parquet` (servidor de casa, `scripts/carga_licencas.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cadastro` | De que arquivo veio: afe, cbpf, cbpf_medicamento, medicamentos, saneantes, cosmeticos, produtos_saude, alimentos (Anvisa); rntrc (ANTT); produto_veterinario, aviacao_agricola (MAPA); outorgas (Anatel); o tipo de título (ANM); agentes (Ancine) | texto |
| `id_na_fonte` | O que identifica o registro no arquivo (o código da fonte, ou as colunas que o identificam juntas por `|`); nos medicamentos, o tipo de autorização + o código (`REGISTRADO|937`: o mesmo código é um registrado de uma empresa e um notificado de outra), e o CNPJ, o registro e o processo no fim se a chave aparecer com dois deles | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `registro` | Número da licença na fonte: autorização (AFE), certificado (CBPF), registro do produto, RNTRC, registro do estabelecimento (MAPA), Fistel da outorga, registro na Ancine | texto |
| `processo` | Número do processo no órgão | texto |
| `categoria` | O tipo, como a fonte escreve: tipo de produto (AFE), tipo de certificado, categoria regulatória, categoria do transportador, atividade (MAPA), tipo de outorga, tipo de requerimento (ANM), classificação do agente (Ancine) | texto |
| `descricao` | O que a licença cobre: atividades (AFE), assunto (CBPF), nome do produto, classificação (MAPA), serviço notificado (Anatel), substâncias (ANM), natureza jurídica (Ancine) | texto |
| `complemento` | Um dado a mais de cada fonte: número novo da AFE, país da fábrica inspecionada (CBPF), transportador equiparado (RNTRC), característica ou aeronave (MAPA), Fistel da notificação (Anatel), tipo de uso (ANM), brasileiro independente (Ancine) | texto |
| `situacao` | A situação como a fonte escreve hoje (ativo, vencido, cancelado, fase atual do título...): vale desde o dia do arquivo, nunca antes. Nos medicamentos, todas as situações das apresentações do produto, em ordem alfabética (`Ativo / Inativo`): nenhuma vence, e a de cada apresentação não está no arquivo | texto |
| `uf` | UF da empresa ou do estabelecimento, quando a fonte informa | texto |
| `municipio` | Município, quando a fonte informa | texto |
| `concedido_em` | Data da concessão, autorização, inclusão ou registro, quando a fonte informa | data (dia) |
| `publicado_em` | Publicação da licença (Diário Oficial), quando a fonte informa | data (dia) |
| `vence_em` | Vencimento da licença ou do registro (nos alimentos da Anvisa, que só dão o mês, o 1º dia do mês) | data (dia) |
| `cancelado_em` | Cancelamento, quando a fonte informa | data (dia) |
| `situacao_desde` | Desde quando vale a situação (só o RNTRC informa) | data (dia) |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte publica o estado de hoje sem dizer desde quando) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `anatel_outorgas`

Prestadoras de telecomunicações com outorga da Anatel, por CNPJ e serviço notificado. Uma linha por valor diferente de cada registro: a mudança (situação, vencimento, cancelamento) vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo, com letras ou não: CPF e CNPJ mascarado saem na coleta; razão social, nome de fantasia, endereço, contato e responsável técnico nunca chegam ao acervo. Empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado.

- **Fonte:** Anatel: dados abertos, prestadoras de serviços de telecomunicações (`base/licencas.py`)
- **Licença:** CC BY (dados abertos da Anatel no dados.gov.br; citar a Anatel)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a fonte recarrega o arquivo inteiro; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** A fonte publica o estado de hoje sem dizer desde quando: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 29/10/2026); as datas da fonte ficam nas colunas delas
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `cadastro`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `concedido_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-29 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/anatel_outorgas/<cadastro>.parquet` (servidor de casa, `scripts/carga_licencas.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cadastro` | De que arquivo veio: afe, cbpf, cbpf_medicamento, medicamentos, saneantes, cosmeticos, produtos_saude, alimentos (Anvisa); rntrc (ANTT); produto_veterinario, aviacao_agricola (MAPA); outorgas (Anatel); o tipo de título (ANM); agentes (Ancine) | texto |
| `id_na_fonte` | O que identifica o registro no arquivo (o código da fonte, ou as colunas que o identificam juntas por `|`); nos medicamentos, o tipo de autorização + o código (`REGISTRADO|937`: o mesmo código é um registrado de uma empresa e um notificado de outra), e o CNPJ, o registro e o processo no fim se a chave aparecer com dois deles | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `registro` | Número da licença na fonte: autorização (AFE), certificado (CBPF), registro do produto, RNTRC, registro do estabelecimento (MAPA), Fistel da outorga, registro na Ancine | texto |
| `processo` | Número do processo no órgão | texto |
| `categoria` | O tipo, como a fonte escreve: tipo de produto (AFE), tipo de certificado, categoria regulatória, categoria do transportador, atividade (MAPA), tipo de outorga, tipo de requerimento (ANM), classificação do agente (Ancine) | texto |
| `descricao` | O que a licença cobre: atividades (AFE), assunto (CBPF), nome do produto, classificação (MAPA), serviço notificado (Anatel), substâncias (ANM), natureza jurídica (Ancine) | texto |
| `complemento` | Um dado a mais de cada fonte: número novo da AFE, país da fábrica inspecionada (CBPF), transportador equiparado (RNTRC), característica ou aeronave (MAPA), Fistel da notificação (Anatel), tipo de uso (ANM), brasileiro independente (Ancine) | texto |
| `situacao` | A situação como a fonte escreve hoje (ativo, vencido, cancelado, fase atual do título...): vale desde o dia do arquivo, nunca antes. Nos medicamentos, todas as situações das apresentações do produto, em ordem alfabética (`Ativo / Inativo`): nenhuma vence, e a de cada apresentação não está no arquivo | texto |
| `uf` | UF da empresa ou do estabelecimento, quando a fonte informa | texto |
| `municipio` | Município, quando a fonte informa | texto |
| `concedido_em` | Data da concessão, autorização, inclusão ou registro, quando a fonte informa | data (dia) |
| `publicado_em` | Publicação da licença (Diário Oficial), quando a fonte informa | data (dia) |
| `vence_em` | Vencimento da licença ou do registro (nos alimentos da Anvisa, que só dão o mês, o 1º dia do mês) | data (dia) |
| `cancelado_em` | Cancelamento, quando a fonte informa | data (dia) |
| `situacao_desde` | Desde quando vale a situação (só o RNTRC informa) | data (dia) |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte publica o estado de hoje sem dizer desde quando) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `anm_titulos`

Títulos e requerimentos minerários da ANM por CNPJ do titular (Cadastro Mineiro, um arquivo por tipo de título). A coluna "Situação" (Sim/Não) da ANM fica de fora: o sentido não está no dicionário dela. Uma linha por valor diferente de cada registro: a mudança (situação, vencimento, cancelamento) vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo, com letras ou não: CPF e CNPJ mascarado saem na coleta; razão social, nome de fantasia, endereço, contato e responsável técnico nunca chegam ao acervo. Empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado.

- **Fonte:** ANM: dados abertos do Cadastro Mineiro (`base/licencas.py`)
- **Licença:** CC BY (dados abertos da ANM, Cadastro Mineiro, no dados.gov.br; citar a ANM)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a fonte recarrega o arquivo inteiro; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** A fonte publica o estado de hoje sem dizer desde quando: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 29/10/2026); as datas da fonte ficam nas colunas delas
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `cadastro`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `concedido_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-29 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/anm_titulos/<cadastro>.parquet` (servidor de casa, `scripts/carga_licencas.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cadastro` | De que arquivo veio: afe, cbpf, cbpf_medicamento, medicamentos, saneantes, cosmeticos, produtos_saude, alimentos (Anvisa); rntrc (ANTT); produto_veterinario, aviacao_agricola (MAPA); outorgas (Anatel); o tipo de título (ANM); agentes (Ancine) | texto |
| `id_na_fonte` | O que identifica o registro no arquivo (o código da fonte, ou as colunas que o identificam juntas por `|`); nos medicamentos, o tipo de autorização + o código (`REGISTRADO|937`: o mesmo código é um registrado de uma empresa e um notificado de outra), e o CNPJ, o registro e o processo no fim se a chave aparecer com dois deles | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `registro` | Número da licença na fonte: autorização (AFE), certificado (CBPF), registro do produto, RNTRC, registro do estabelecimento (MAPA), Fistel da outorga, registro na Ancine | texto |
| `processo` | Número do processo no órgão | texto |
| `categoria` | O tipo, como a fonte escreve: tipo de produto (AFE), tipo de certificado, categoria regulatória, categoria do transportador, atividade (MAPA), tipo de outorga, tipo de requerimento (ANM), classificação do agente (Ancine) | texto |
| `descricao` | O que a licença cobre: atividades (AFE), assunto (CBPF), nome do produto, classificação (MAPA), serviço notificado (Anatel), substâncias (ANM), natureza jurídica (Ancine) | texto |
| `complemento` | Um dado a mais de cada fonte: número novo da AFE, país da fábrica inspecionada (CBPF), transportador equiparado (RNTRC), característica ou aeronave (MAPA), Fistel da notificação (Anatel), tipo de uso (ANM), brasileiro independente (Ancine) | texto |
| `situacao` | A situação como a fonte escreve hoje (ativo, vencido, cancelado, fase atual do título...): vale desde o dia do arquivo, nunca antes. Nos medicamentos, todas as situações das apresentações do produto, em ordem alfabética (`Ativo / Inativo`): nenhuma vence, e a de cada apresentação não está no arquivo | texto |
| `uf` | UF da empresa ou do estabelecimento, quando a fonte informa | texto |
| `municipio` | Município, quando a fonte informa | texto |
| `concedido_em` | Data da concessão, autorização, inclusão ou registro, quando a fonte informa | data (dia) |
| `publicado_em` | Publicação da licença (Diário Oficial), quando a fonte informa | data (dia) |
| `vence_em` | Vencimento da licença ou do registro (nos alimentos da Anvisa, que só dão o mês, o 1º dia do mês) | data (dia) |
| `cancelado_em` | Cancelamento, quando a fonte informa | data (dia) |
| `situacao_desde` | Desde quando vale a situação (só o RNTRC informa) | data (dia) |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte publica o estado de hoje sem dizer desde quando) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `ancine_agentes`

Agentes econômicos registrados na Ancine, por CNPJ. Uma linha por valor diferente de cada registro: a mudança (situação, vencimento, cancelamento) vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo, com letras ou não: CPF e CNPJ mascarado saem na coleta; razão social, nome de fantasia, endereço, contato e responsável técnico nunca chegam ao acervo. Empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado.

- **Fonte:** Ancine: dados abertos, agentes econômicos regulares (`base/licencas.py`)
- **Licença:** CC BY (dados abertos da Ancine no dados.gov.br; citar a Ancine)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a fonte recarrega o arquivo inteiro; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** A fonte publica o estado de hoje sem dizer desde quando: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 29/10/2026); as datas da fonte ficam nas colunas delas
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `cadastro`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `concedido_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-29 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ancine_agentes/<cadastro>.parquet` (servidor de casa, `scripts/carga_licencas.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cadastro` | De que arquivo veio: afe, cbpf, cbpf_medicamento, medicamentos, saneantes, cosmeticos, produtos_saude, alimentos (Anvisa); rntrc (ANTT); produto_veterinario, aviacao_agricola (MAPA); outorgas (Anatel); o tipo de título (ANM); agentes (Ancine) | texto |
| `id_na_fonte` | O que identifica o registro no arquivo (o código da fonte, ou as colunas que o identificam juntas por `|`); nos medicamentos, o tipo de autorização + o código (`REGISTRADO|937`: o mesmo código é um registrado de uma empresa e um notificado de outra), e o CNPJ, o registro e o processo no fim se a chave aparecer com dois deles | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `registro` | Número da licença na fonte: autorização (AFE), certificado (CBPF), registro do produto, RNTRC, registro do estabelecimento (MAPA), Fistel da outorga, registro na Ancine | texto |
| `processo` | Número do processo no órgão | texto |
| `categoria` | O tipo, como a fonte escreve: tipo de produto (AFE), tipo de certificado, categoria regulatória, categoria do transportador, atividade (MAPA), tipo de outorga, tipo de requerimento (ANM), classificação do agente (Ancine) | texto |
| `descricao` | O que a licença cobre: atividades (AFE), assunto (CBPF), nome do produto, classificação (MAPA), serviço notificado (Anatel), substâncias (ANM), natureza jurídica (Ancine) | texto |
| `complemento` | Um dado a mais de cada fonte: número novo da AFE, país da fábrica inspecionada (CBPF), transportador equiparado (RNTRC), característica ou aeronave (MAPA), Fistel da notificação (Anatel), tipo de uso (ANM), brasileiro independente (Ancine) | texto |
| `situacao` | A situação como a fonte escreve hoje (ativo, vencido, cancelado, fase atual do título...): vale desde o dia do arquivo, nunca antes. Nos medicamentos, todas as situações das apresentações do produto, em ordem alfabética (`Ativo / Inativo`): nenhuma vence, e a de cada apresentação não está no arquivo | texto |
| `uf` | UF da empresa ou do estabelecimento, quando a fonte informa | texto |
| `municipio` | Município, quando a fonte informa | texto |
| `concedido_em` | Data da concessão, autorização, inclusão ou registro, quando a fonte informa | data (dia) |
| `publicado_em` | Publicação da licença (Diário Oficial), quando a fonte informa | data (dia) |
| `vence_em` | Vencimento da licença ou do registro (nos alimentos da Anvisa, que só dão o mês, o 1º dia do mês) | data (dia) |
| `cancelado_em` | Cancelamento, quando a fonte informa | data (dia) |
| `situacao_desde` | Desde quando vale a situação (só o RNTRC informa) | data (dia) |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte publica o estado de hoje sem dizer desde quando) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `mme_reidi`

Projetos de geração e transmissão de energia enquadrados no REIDI (MME), por CNPJ, com a portaria, a execução e o benefício fiscal. Uma linha por valor diferente de cada projeto: a mudança vira linha nova desde o dia em que foi vista, e o projeto que some do arquivo ganha `consta` falso (`como_era_em` dá o retrato de um dia). Só pessoa jurídica: CPF e nome (do cliente, do agente, do investidor, da empresa) saem na coleta; empresário individual e MEI ficam com `trata_como_pessoa`.

- **Fonte:** MME: dados abertos, REIDI (processos deferidos) (`base/incentivos.py`)
- **Licença:** Outra (Aberta), sem nome, no portal do MME (a confirmar; citar o MME)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Mensal (a fonte recarrega o arquivo inteiro; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** A fonte não diz quando publicou cada linha: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 29/10/2026); as datas da fonte ficam nas colunas delas
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `portaria_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-29 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/mme_reidi/<arquivo>.parquet` (servidor de casa, `scripts/carga_incentivos.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O processo e o projeto juntos por `|` | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `processo` | Número do processo no MME | texto |
| `projeto` | Código do projeto no MME | texto |
| `nome_do_projeto` | Nome do projeto (a usina ou a linha de transmissão) | texto |
| `portaria` | Portaria de enquadramento, como a fonte escreve | texto |
| `uf` | UF do projeto (NI quando a fonte não identifica) | texto |
| `municipio` | Município do projeto, como a fonte escreve | texto |
| `portaria_em` | Início da portaria de enquadramento | data (dia) |
| `execucao_desde` | Início da execução do projeto | data (dia) |
| `execucao_ate` | Fim previsto da execução do projeto | data (dia) |
| `valor_com_incidencia` | Total do projeto com PIS/Pasep e Cofins | reais (R$), já multiplicado pela escala informada |
| `valor_sem_incidencia` | Total do projeto sem PIS/Pasep e Cofins | reais (R$), já multiplicado pela escala informada |
| `valor_do_beneficio` | Benefício fiscal estimado (a diferença) | reais (R$), já multiplicado pela escala informada |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que o arquivista viu a linha | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte não diz quando publicou cada linha) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `aneel_cde`

Descontos tarifários pagos pela Conta de Desenvolvimento Energético (CDE, ANEEL), somados por CNPJ, mês, distribuidora, classe, grupo tarifário e tipo de subsídio (a fonte tem uma linha por unidade consumidora). Cada arquivo da ANEEL (um por mês; um por ano na rede básica) é um Parquet; a republicação corrigida vira linha nova. Só pessoa jurídica: CPF e nome (do cliente, do agente, do investidor, da empresa) saem na coleta; empresário individual e MEI ficam com `trata_como_pessoa`.

- **Fonte:** ANEEL: dados abertos, beneficiários da CDE (`base/incentivos.py`)
- **Licença:** ODbL (dados abertos da ANEEL; citar). SAMP sem CPF e nome do consumidor
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal (um arquivo novo por mês; a ANEEL pode republicar o mês corrigido)
- **Atraso de divulgação:** A fonte não diz quando publicou cada linha: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 29/10/2026); as datas da fonte ficam nas colunas delas
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `arquivo`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `mes`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-29 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/aneel_cde/<arquivo>.parquet` (servidor de casa, `scripts/carga_incentivos.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `arquivo` | `mensal` (beneficiários) ou `rede_basica` (descontos na transmissão) | texto |
| `id_na_fonte` | As colunas da soma juntas por `|` | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `mes` | Mês de referência (o 1º dia do mês) | data (dia) |
| `distribuidora` | Sigla da distribuidora (vazio na rede básica) | texto |
| `cnpj_da_distribuidora` | CNPJ da distribuidora, só os números (vazio na rede básica) | texto |
| `classe` | Código da classe do consumidor, como a ANEEL escreve | texto |
| `grupo_tarifario` | Subgrupo tarifário (código) ou grupo (rede básica) | texto |
| `tipo_de_desconto` | Tipo de subsídio (`SubsCARFI`, `SubsRural`...) ou o código do tipo (rede básica) | texto |
| `valor_do_desconto` | Soma dos subsídios ou descontos pagos pela CDE no mês | reais (R$), já multiplicado pela escala informada |
| `valor_cobrado` | Soma da cobrança (só a rede básica informa) | reais (R$), já multiplicado pela escala informada |
| `linhas` | Quantas linhas da fonte (unidades consumidoras ou agentes) foram somadas | número inteiro |
| `gerado_em` | Dia em que a ANEEL gerou o arquivo | data (dia) |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que o arquivista viu a linha | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte não diz quando publicou cada linha) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `bcb_rde_ied`

Registros de investimento estrangeiro direto no Banco Central (RDE-IED) pela raiz do CNPJ da empresa que recebeu, de nov/2011 a dez/2022 (a série parou aí). A moeda e o valor, sempre vazios na fonte, ficam de fora. Só pessoa jurídica: CPF e nome (do cliente, do agente, do investidor, da empresa) saem na coleta; empresário individual e MEI ficam com `trata_como_pessoa`.

- **Fonte:** Banco Central: API Olinda, RDE-IED (registros) (`base/incentivos.py`)
- **Licença:** ODbL (dados abertos do Banco Central; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Parada desde dez/2022 (o arquivista confere todo mês)
- **Atraso de divulgação:** A fonte não diz quando publicou cada linha: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 29/10/2026); as datas da fonte ficam nas colunas delas
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `mes`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-29 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/bcb_rde_ied/<arquivo>.parquet` (servidor de casa, `scripts/carga_incentivos.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O código, a ocorrência, o mês e o país juntos por `|` | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres) da empresa que recebeu o investimento | texto |
| `codigo_rde` | Código do registro no RDE-IED | texto |
| `uf` | UF da empresa que recebeu | texto |
| `pais` | País do investidor estrangeiro | texto |
| `ocorrencia` | `REGISTRO EFETUADO` ou `REGISTRO ENCERRADO` | texto |
| `mes` | Mês da ocorrência (o 1º dia do mês) | data (dia) |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que o arquivista viu a linha | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte não diz quando publicou cada linha) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `sefaz_pe_beneficios`

Benefícios fiscais estaduais de Pernambuco (SEFAZ-PE: PRODEPE, PEAP, máquinas pesadas...) por CNPJ, com o CACEPE e o prazo de cada um. Um Parquet por ano da fonte (`arquivo`); a razão social não é guardada. O prazo prorrogado vira linha nova, e o prazo (`vigencia_inicio`, `vigencia_fim`) não é a data em que a base soube do benefício (`disponivel_em`). Só pessoa jurídica: CPF e nome (do cliente, do agente, do investidor, da empresa) saem na coleta; empresário individual e MEI ficam com `trata_como_pessoa`.

- **Fonte:** SEFAZ-PE: dados abertos (dados.pe.gov.br), benefícios fiscais, CC BY (`base/incentivos.py`)
- **Licença:** CC BY, SEFAZ-PE (citar a fonte). Só CNPJ, sem a razão social
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (um arquivo por ano; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** A fonte não diz quando publicou cada linha: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 29/10/2026); as datas da fonte ficam nas colunas delas
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `arquivo`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `vigencia_inicio`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-05 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/sefaz_pe_beneficios/<arquivo>.parquet` (servidor de casa, `scripts/carga_incentivos.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `arquivo` | O ano do arquivo da SEFAZ-PE de onde a linha veio | texto |
| `id_na_fonte` | O programa, o CNPJ, o CACEPE e o início do prazo juntos por `|` | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `programa` | Programa estadual do benefício (PRODEPE, PEAP, máquinas pesadas...), como a fonte escreve | texto |
| `cacepe` | Cadastro da empresa na SEFAZ-PE (CACEPE) | texto |
| `vigencia_inicio` | Início do prazo do benefício (não é quando a base soube) | data (dia) |
| `vigencia_fim` | Fim do prazo do benefício; a prorrogação vira linha nova (vazio quando a fonte não diz) | data (dia) |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que o arquivista viu a linha | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte não diz quando publicou cada linha) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `sefa_pr_divida_ativa`

Débitos inscritos em dívida ativa no Paraná (Sefa-PR: ICMS, IPVA, taxas...) por CNPJ, com o valor, a data da inscrição, a suspensão, a garantia e o parcelamento. Um arquivo por dia forma uma série só: débito novo ou com valor ou situação diferente vira linha nova desde o dia em que foi visto, e o débito que some do arquivo (pago, cancelado, prescrito: a fonte não diz o motivo) ganha `consta` falso. Só pessoa jurídica: a coleta tira o CPF, o nome e a razão social (firma individual e MEI têm o nome da pessoa), e quem a Receita guardada trata como pessoa fica com `trata_como_pessoa`.

- **Fonte:** Sefa-PR: Portal do Devedor, lista de devedores em arquivo (licença a confirmar; citar a fonte) (`base/divida_estadual.py`)
- **Licença:** Sefa-PR, dívida ativa: sem licença escrita (a confirmar; citar a Sefa-PR)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Semanal (a Sefa-PR gera o arquivo todo dia; o arquivista guarda o do dia)
- **Atraso de divulgação:** A fonte não diz quando publicou cada débito: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 06/11/2026); a data da inscrição fica na coluna `inscrito_em`
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `inscrito_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-06 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/sefa_pr_divida_ativa/divida_ativa.parquet` (servidor de casa, `scripts/carga_divida_estadual.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O número da dívida ativa, o CNPJ e o tipo do crédito juntos por `|` | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `divida_ativa` | Número da inscrição em dívida ativa, como a fonte escreve | texto |
| `tipo_do_credito` | Tipo do crédito (ICMS, IPVA, PROCON, taxas...), como a fonte escreve | texto |
| `inscrito_em` | Data da inscrição do débito em dívida ativa (não é quando a base soube) | data (dia) |
| `atualizado_em` | Data da última atualização do valor, segundo a fonte | data (dia) |
| `valor_do_imposto` | Valor do imposto (principal), em reais | reais (R$), já multiplicado pela escala informada |
| `valor_da_multa` | Valor da multa, em reais | reais (R$), já multiplicado pela escala informada |
| `valor_dos_juros` | Valor dos juros, em reais | reais (R$), já multiplicado pela escala informada |
| `valor_total` | Valor total do débito na atualização, em reais | reais (R$), já multiplicado pela escala informada |
| `suspensao` | Motivo da suspensão da exigibilidade (depósito judicial, suspensão da PGE...); vazio quando não há | texto |
| `com_garantia` | Verdadeiro quando o débito tem garantia | verdadeiro ou falso |
| `com_parcelamento_ativo` | Verdadeiro quando há parcelamento ativo do débito | verdadeiro ou falso |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que o arquivista viu a linha | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte não diz quando publicou cada linha) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `sef_mg_divida_ativa`

Certidões de dívida ativa de pessoas jurídicas de Minas Gerais (SEF-MG, Resolução Conjunta SEF/AGE 5.625/2022) por CNPJ, com a espécie, a data da inscrição e o saldo. Uma planilha por semana forma uma série só: CDA nova ou com saldo diferente vira linha nova desde o dia em que foi vista, e a que some da planilha (paga, cancelada, prescrita: a fonte não diz o motivo) ganha `consta` falso. Só pessoa jurídica: a coleta tira o nome do devedor (firma individual leva o nome da pessoa) e as linhas com CPF no nome; quem a Receita guardada trata como pessoa fica com `trata_como_pessoa`. Linha sem CNPJ completo e de dígito certo não entra.

- **Fonte:** SEF-MG: dívida ativa, planilhas de pessoa jurídica (Res. Conj. SEF/AGE 5.625/2022; licença a confirmar; citar a fonte) (`base/divida_estadual.py`)
- **Licença:** SEF-MG, dívida ativa: sem licença escrita (a confirmar; citar a SEF-MG)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Semanal (a SEF-MG atualiza a planilha; o arquivista guarda uma por semana)
- **Atraso de divulgação:** A fonte não diz quando publicou cada CDA: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 06/11/2026); a data da inscrição fica na coluna `inscrito_em`
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `inscrito_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-06 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/sef_mg_divida_ativa/divida_ativa.parquet` (servidor de casa, `scripts/carga_divida_estadual.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O número da certidão ou do parcelamento e o CNPJ, juntos por `|` | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `cda` | Número da certidão de dívida ativa (CDA), como a fonte escreve | texto |
| `inscrito_em` | Data da inscrição da CDA (não é quando a base soube) | data (dia) |
| `especie` | Espécie da dívida (ICMS, IPVA, multa...), como a fonte escreve | texto |
| `saldo_da_cda` | Saldo da CDA na data do arquivo, em reais | reais (R$), já multiplicado pela escala informada |
| `saldo_do_nucleo` | Saldo do núcleo (o principal da dívida, sem acessórios), em reais, como a fonte informa | reais (R$), já multiplicado pela escala informada |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que o arquivista viu a linha | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte não diz quando publicou cada linha) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `sef_mg_parcelamentos`

Parcelamentos de dívida ativa de pessoas jurídicas de Minas Gerais (SEF-MG) por CNPJ, com a espécie, a data, a quantidade de parcelas e o débito. Mesma série semanal das CDAs: parcelamento novo ou com valor diferente vira linha nova, e o que some da planilha ganha `consta` falso. Só pessoa jurídica: a coleta tira o nome do devedor (firma individual leva o nome da pessoa) e as linhas com CPF no nome; quem a Receita guardada trata como pessoa fica com `trata_como_pessoa`. Linha sem CNPJ completo e de dígito certo não entra.

- **Fonte:** SEF-MG: dívida ativa, planilhas de pessoa jurídica (Res. Conj. SEF/AGE 5.625/2022; licença a confirmar; citar a fonte) (`base/divida_estadual.py`)
- **Licença:** SEF-MG, dívida ativa: sem licença escrita (a confirmar; citar a SEF-MG)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Semanal (a SEF-MG atualiza a planilha; o arquivista guarda uma por semana)
- **Atraso de divulgação:** A fonte não diz quando publicou cada parcelamento: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 06/11/2026); a data do parcelamento fica na coluna `parcelado_em`
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `parcelado_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-06 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/sef_mg_parcelamentos/parcelamentos.parquet` (servidor de casa, `scripts/carga_divida_estadual.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O número da certidão ou do parcelamento e o CNPJ, juntos por `|` | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `parcelamento` | Número do parcelamento, como a fonte escreve | texto |
| `parcelado_em` | Data em que o parcelamento foi feito | data (dia) |
| `especie` | Espécie da dívida parcelada, como a fonte escreve | texto |
| `parcelas` | Quantidade de parcelas | número inteiro |
| `debito` | Débito parcelado, em reais, como a fonte informa | reais (R$), já multiplicado pela escala informada |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que o arquivista viu a linha | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte não diz quando publicou cada linha) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `sefaz_pe_ordem_cronologica`

Pagamentos do governo de Pernambuco a fornecedores, por CNPJ, com a unidade gestora, o empenho, o dia da liquidação, o dia do pagamento e o valor pago. `dias_ate_pagar` é o prazo real de pagamento do estado. Um Parquet por ano da fonte (`arquivo`): pagamento novo ou com data ou valor diferente vira linha nova desde o dia em que foi visto, e o que some do arquivo (o estado corrigiu) ganha `consta` falso. Só pessoa jurídica: a coleta tira o nome do credor (firma individual leva o nome da pessoa), o texto livre e as linhas com CPF; quem a Receita guardada trata como pessoa fica com `trata_como_pessoa`. Linha sem CNPJ completo e de dígito certo não entra.

- **Fonte:** SEFAZ-PE: dados abertos (dados.pe.gov.br), ordem cronológica de pagamentos, CC BY (`base/ordem_cronologica.py`)
- **Licença:** CC BY, SEFAZ-PE (citar a fonte). Só CNPJ, sem a razão social
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (o arquivista guarda o arquivo do ano a cada coleta, só o que mudou)
- **Atraso de divulgação:** A fonte não diz quando publicou cada pagamento: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 06/11/2026); as datas do pagamento ficam nas colunas `liquidado_em` e `pago_em`
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `arquivo`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `pago_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-06 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/sefaz_pe_ordem_cronologica/ordem-cronologica-<ano>.parquet` (servidor de casa, `scripts/carga_ordem_cronologica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | Empenho, documento, ordem bancária, CNPJ e valor pago juntos por `|` | texto |
| `arquivo` | O ano do arquivo de onde a linha veio | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `codigo_ug` | Código da unidade gestora que pagou | texto |
| `unidade_gestora` | Nome da unidade gestora (o órgão) que pagou, como a fonte escreve | texto |
| `empenho` | Número do empenho (a reserva da despesa), como a fonte escreve | texto |
| `documento` | Número do documento de liquidação, como a fonte escreve | texto |
| `ordem_bancaria` | Número da ordem bancária do pagamento, como a fonte escreve | texto |
| `categoria_contrato` | Categoria do contrato, como a fonte escreve | texto |
| `liquidado_em` | Dia em que a despesa foi liquidada (o estado reconheceu a dívida) | data (dia) |
| `ordem_bancaria_em` | Dia da ordem bancária | data (dia) |
| `pago_em` | Dia do pagamento (não é quando a base soube) | data (dia) |
| `valor_documento` | Valor do documento de liquidação, em reais | reais (R$), já multiplicado pela escala informada |
| `valor_pago` | Valor pago, em reais | reais (R$), já multiplicado pela escala informada |
| `dias_ate_pagar` | Dias entre a liquidação e o pagamento (`pago_em` menos `liquidado_em`): o prazo real do governo; vazio quando falta uma das datas | número inteiro |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que o arquivista viu a linha | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte não diz quando publicou cada linha) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `es_ordem_cronologica`

Pagamentos do governo do Espírito Santo a fornecedores, por CNPJ, com a unidade gestora, o empenho, a nota de liquidação, o dia da liquidação, o dia da ordem bancária e o valor pago. `dias_ate_pagar` é o prazo real de pagamento do estado. Um Parquet por ano da fonte (`arquivo`): pagamento novo ou com data ou valor diferente vira linha nova desde o dia em que foi visto, e o que some do arquivo (o estado corrigiu) ganha `consta` falso. Só pessoa jurídica: a coleta tira o nome do credor (firma individual leva o nome da pessoa), o texto livre e as linhas com CPF; quem a Receita guardada trata como pessoa fica com `trata_como_pessoa`. Linha sem CNPJ completo e de dígito certo não entra.

- **Fonte:** Governo do ES: dados abertos (dados.es.gov.br), ordem cronológica de pagamentos, CC BY (`base/ordem_cronologica.py`)
- **Licença:** CC BY, Governo do ES (citar a fonte). Só CNPJ, sem o nome do credor
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (o arquivista guarda o arquivo do ano a cada coleta, só o que mudou)
- **Atraso de divulgação:** A fonte não diz quando publicou cada pagamento: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa em 06/11/2026); as datas do pagamento ficam nas colunas `liquidado_em` e `pago_em`
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `arquivo`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `pago_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-06 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/es_ordem_cronologica/ordem-cronologica-<ano>.parquet` (servidor de casa, `scripts/carga_ordem_cronologica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | Empenho, documento, ordem bancária, CNPJ e valor pago juntos por `|` | texto |
| `arquivo` | O ano do arquivo de onde a linha veio | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `codigo_ug` | Código da unidade gestora que pagou | texto |
| `unidade_gestora` | Nome da unidade gestora (o órgão) que pagou, como a fonte escreve | texto |
| `empenho` | Número do empenho (a reserva da despesa), como a fonte escreve | texto |
| `nota_de_liquidacao` | Número da nota de liquidação, como a fonte escreve | texto |
| `ordem_bancaria` | Número da ordem bancária do pagamento, como a fonte escreve | texto |
| `categoria_contrato` | Categoria do contrato, como a fonte escreve | texto |
| `ordem_cronologica_em` | Dia da ordem cronológica de pagamento na fonte | data (dia) |
| `liquidado_em` | Dia em que a despesa foi liquidada (o estado reconheceu a dívida) | data (dia) |
| `pago_em` | Dia da emissão da ordem bancária (a fonte não dá o dia em que o dinheiro caiu na conta) | data (dia) |
| `valor_pago` | Valor pago, em reais | reais (R$), já multiplicado pela escala informada |
| `dias_ate_pagar` | Dias entre a liquidação e o pagamento (`pago_em` menos `liquidado_em`): o prazo real do governo; vazio quando falta uma das datas | número inteiro |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que o arquivista viu a linha | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a fonte não diz quando publicou cada linha) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `financiamentos_bndes`

Histórico de contratações de crédito reembolsável do BNDES por CNPJ (operações não automáticas, diretas e pelas instituições credenciadas). **Não é saldo nem dívida atual:** é o fluxo que o banco divulga (contratado e desembolsado); nada se soma (subcréditos ficam separados, e a outra fonte fica na outra tabela) e o vazio fica vazio. Uma linha por valor diferente de cada operação: a mudança vira linha nova desde o dia em que foi vista, e a que some do arquivo ganha `consta` falso. Só pessoa jurídica: nome do cliente e texto do projeto nunca entram; empresário individual e MEI ficam com `trata_como_pessoa`.

- **Fonte:** BNDES, dados abertos: operações não automáticas (ODbL; citar o BNDES) (`base/financiamentos.py`)
- **Licença:** ODbL (dados abertos do BNDES; citar o BNDES, compartilhar igual). Só CNPJ
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal (a fonte reescreve o arquivo inteiro)
- **Atraso de divulgação:** A fonte não diz quando publicou cada linha: toda linha vale desde o dia em que o arquivista a viu
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `contratado_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/financiamentos_bndes/bndes.parquet` (servidor de casa, `scripts/carga_financiamentos.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | Identidade estável da operação (nunca o número da linha). BNDES: `bndes|contrato|resumo|n`, com um hash curto dos campos que não mudam (CNPJ, data, produto, instrumento, fonte de recurso, custo, juros, prazos, subsetor, forma e repassador) e a ordem pelo valor contratado dentro do grupo (um contrato tem vários subcréditos, alguns iguais em tudo). Finep direta: `finep|direto|contrato|n`; descentralizada: `finep|descentralizado|convênio|CNPJ|data|n`. Limite: um subcrédito novo de valor menor no mesmo grupo empurra a ordem dos outros | texto |
| `fonte` | `bndes` ou `finep`: nunca somar as duas | texto |
| `modalidade` | `bndes_nao_automatica` (operações não automáticas do BNDES), `finep_credito_direto` ou `finep_credito_descentralizado` | texto |
| `cnpj` | CNPJ de quem tomou o crédito, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `uf` | UF de quem tomou, como a fonte escreve | texto |
| `contrato` | Número do contrato (BNDES e Finep direta; vazio na descentralizada) | texto |
| `convenio_do_agente` | Finep descentralizada: o convênio entre a Finep e o agente financeiro ("Contrato Finep Agente"), não o empréstimo da empresa: muitas empresas cabem nele | texto |
| `contratado_em` | Dia da contratação (BNDES) ou da assinatura (Finep) | data (dia) |
| `valor_contratado` | Valor contratado (Finep: "Valor Finep" ou "Valor Financiado"); vazio fica vazio | reais (R$), já multiplicado pela escala informada |
| `valor_desembolsado` | Valor desembolsado até a data do arquivo (Finep: "Valor Pago" ou "Valor Liberado"). É desembolso, não pagamento da dívida; vazio fica vazio, nunca zero | reais (R$), já multiplicado pela escala informada |
| `contrapartida` | Contrapartida da empresa (só a Finep informa) | reais (R$), já multiplicado pela escala informada |
| `outros_recursos` | Outros recursos (só a Finep descentralizada) | reais (R$), já multiplicado pela escala informada |
| `financiador` | Quem emprestou: `BNDES` na DIRETA, a instituição credenciada na INDIRETA, `FINEP` no crédito direto, o agente financeiro no descentralizado | texto |
| `agente_papel` | `financiador_direto`, `instituicao_credenciada` ou `agente_descentralizado` | texto |
| `cnpj_do_financiador` | CNPJ de quem emprestou, quando a fonte o dá inteiro e de dígito certo (vazio no agente da Finep descentralizada) | texto |
| `forma_de_apoio` | BNDES: `DIRETA` (sem repassador, é normal) ou `INDIRETA` | texto |
| `cnpj_do_executor` | Finep direta: CNPJ do executor do projeto (não é quem tomou o crédito) | texto |
| `uf_do_projeto` | Finep direta: UF do projeto | texto |
| `produto` | BNDES: produto (`BNDES FINEM`...) | texto |
| `instrumento` | BNDES: instrumento financeiro | texto |
| `fonte_de_recurso` | BNDES: fonte de recurso dos desembolsos | texto |
| `custo_financeiro` | BNDES: custo financeiro (`TJLP`, `TLP`, `SELIC`, `US$ / CESTA`...) | texto |
| `juros` | BNDES: juros (spread) em % ao ano, como a fonte escreve; não é o custo efetivo | número com decimais, na unidade da fonte |
| `carencia_meses` | BNDES: prazo de carência, em meses | número inteiro |
| `amortizacao_meses` | BNDES: prazo de amortização, em meses | número inteiro |
| `inovacao` | BNDES: se a operação é de inovação, como a fonte escreve | texto |
| `porte` | BNDES: porte do cliente | texto |
| `natureza` | BNDES: natureza do cliente (privada ou pública) | texto |
| `subsetor_cnae` | BNDES: código do subsetor CNAE | texto |
| `tipo_de_garantia` | BNDES: tipo de garantia | texto |
| `situacao` | Situação como a fonte escreve (vazio quando a fonte põe `-`; a descentralizada não tem) | texto |
| `situacao_classe` | `liquidado`, `ativo`, `cancelado`, `rescindido`, `pendente`, `encerrado_tecnico` (o ENCERRADO da Finep fecha o projeto, não quita), `nao_informado` ou `nao_classificado` (situação que a tabela não conhece) | texto |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que o arquivista viu a linha | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (nenhuma das duas fontes diz quando publicou cada linha) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `financiamentos_finep`

Histórico de contratações de crédito reembolsável da Finep por CNPJ (crédito direto e descentralizado, pelos agentes financeiros). A "Posição" da planilha fica no CSV guardado e não vira coluna: a data que vale é a do arquivo. **Não é saldo nem dívida atual:** é o fluxo que o banco divulga (contratado e desembolsado); nada se soma (subcréditos ficam separados, e a outra fonte fica na outra tabela) e o vazio fica vazio. Uma linha por valor diferente de cada operação: a mudança vira linha nova desde o dia em que foi vista, e a que some do arquivo ganha `consta` falso. Só pessoa jurídica: nome do cliente e texto do projeto nunca entram; empresário individual e MEI ficam com `trata_como_pessoa`.

- **Fonte:** Finep, planilha de contratações (licença a confirmar: uso interno) (`base/financiamentos.py`)
- **Licença:** Sem licença escrita na planilha da Finep (a confirmar; citar a Finep)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Mensal (a fonte reescreve o arquivo inteiro)
- **Atraso de divulgação:** A fonte não diz quando publicou cada linha: toda linha vale desde o dia em que o arquivista a viu
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `contratado_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/financiamentos_finep/finep.parquet` (servidor de casa, `scripts/carga_financiamentos.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | Identidade estável da operação (nunca o número da linha). BNDES: `bndes|contrato|resumo|n`, com um hash curto dos campos que não mudam (CNPJ, data, produto, instrumento, fonte de recurso, custo, juros, prazos, subsetor, forma e repassador) e a ordem pelo valor contratado dentro do grupo (um contrato tem vários subcréditos, alguns iguais em tudo). Finep direta: `finep|direto|contrato|n`; descentralizada: `finep|descentralizado|convênio|CNPJ|data|n`. Limite: um subcrédito novo de valor menor no mesmo grupo empurra a ordem dos outros | texto |
| `fonte` | `bndes` ou `finep`: nunca somar as duas | texto |
| `modalidade` | `bndes_nao_automatica` (operações não automáticas do BNDES), `finep_credito_direto` ou `finep_credito_descentralizado` | texto |
| `cnpj` | CNPJ de quem tomou o crédito, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `uf` | UF de quem tomou, como a fonte escreve | texto |
| `contrato` | Número do contrato (BNDES e Finep direta; vazio na descentralizada) | texto |
| `convenio_do_agente` | Finep descentralizada: o convênio entre a Finep e o agente financeiro ("Contrato Finep Agente"), não o empréstimo da empresa: muitas empresas cabem nele | texto |
| `contratado_em` | Dia da contratação (BNDES) ou da assinatura (Finep) | data (dia) |
| `valor_contratado` | Valor contratado (Finep: "Valor Finep" ou "Valor Financiado"); vazio fica vazio | reais (R$), já multiplicado pela escala informada |
| `valor_desembolsado` | Valor desembolsado até a data do arquivo (Finep: "Valor Pago" ou "Valor Liberado"). É desembolso, não pagamento da dívida; vazio fica vazio, nunca zero | reais (R$), já multiplicado pela escala informada |
| `contrapartida` | Contrapartida da empresa (só a Finep informa) | reais (R$), já multiplicado pela escala informada |
| `outros_recursos` | Outros recursos (só a Finep descentralizada) | reais (R$), já multiplicado pela escala informada |
| `financiador` | Quem emprestou: `BNDES` na DIRETA, a instituição credenciada na INDIRETA, `FINEP` no crédito direto, o agente financeiro no descentralizado | texto |
| `agente_papel` | `financiador_direto`, `instituicao_credenciada` ou `agente_descentralizado` | texto |
| `cnpj_do_financiador` | CNPJ de quem emprestou, quando a fonte o dá inteiro e de dígito certo (vazio no agente da Finep descentralizada) | texto |
| `forma_de_apoio` | BNDES: `DIRETA` (sem repassador, é normal) ou `INDIRETA` | texto |
| `cnpj_do_executor` | Finep direta: CNPJ do executor do projeto (não é quem tomou o crédito) | texto |
| `uf_do_projeto` | Finep direta: UF do projeto | texto |
| `produto` | BNDES: produto (`BNDES FINEM`...) | texto |
| `instrumento` | BNDES: instrumento financeiro | texto |
| `fonte_de_recurso` | BNDES: fonte de recurso dos desembolsos | texto |
| `custo_financeiro` | BNDES: custo financeiro (`TJLP`, `TLP`, `SELIC`, `US$ / CESTA`...) | texto |
| `juros` | BNDES: juros (spread) em % ao ano, como a fonte escreve; não é o custo efetivo | número com decimais, na unidade da fonte |
| `carencia_meses` | BNDES: prazo de carência, em meses | número inteiro |
| `amortizacao_meses` | BNDES: prazo de amortização, em meses | número inteiro |
| `inovacao` | BNDES: se a operação é de inovação, como a fonte escreve | texto |
| `porte` | BNDES: porte do cliente | texto |
| `natureza` | BNDES: natureza do cliente (privada ou pública) | texto |
| `subsetor_cnae` | BNDES: código do subsetor CNAE | texto |
| `tipo_de_garantia` | BNDES: tipo de garantia | texto |
| `situacao` | Situação como a fonte escreve (vazio quando a fonte põe `-`; a descentralizada não tem) | texto |
| `situacao_classe` | `liquidado`, `ativo`, `cancelado`, `rescindido`, `pendente`, `encerrado_tecnico` (o ENCERRADO da Finep fecha o projeto, não quita), `nao_informado` ou `nao_classificado` (situação que a tabela não conhece) | texto |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que o arquivista viu a linha | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (nenhuma das duas fontes diz quando publicou cada linha) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `cmed_precos`

Preços máximos de medicamentos da CMED por apresentação (CNPJ + código GGREM), nas duas listas que a Anvisa publica. São tetos regulatórios, não preço praticado nem receita: nada se multiplica por quantidade. Uma linha por valor diferente de cada apresentação: a mudança vira linha nova que só vale desde o dia em que foi vista, e a que some da lista ganha `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Preço exato em 2 casas: vazio fica vazio e zero fica zero. O nome do laboratório não chega ao acervo (a ligação é pelo CNPJ); empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com layout novo, ou com menos da metade das apresentações do anterior, é pulado. A ligação a `anvisa_registros` usa só CNPJ + registro do produto entre os medicamentos REGISTRADOS e não diz a situação do registro: vigente na lista de preços não quer dizer registro ativo.

- **Fonte:** Anvisa: listas de preços da CMED, dados abertos (`base/cmed.py`)
- **Licença:** Listas da CMED sem licença própria escrita (a confirmar; citar a CMED)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Mensal (a CMED republica as listas inteiras)
- **Atraso de divulgação:** A lista não diz desde quando vale cada preço: toda linha vale desde o dia em que o arquivista a viu (a história guardada começa no dia em que a coleta entrou); o dia da publicação do arquivo fica em `lista_publicada_em`
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `lista`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `lista_publicada_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/cmed_precos/<lista>.parquet` (servidor de casa, `scripts/carga_cmed.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `lista` | `consumidor` (TA_PRECO_MEDICAMENTO: PF e PMC) ou `governo` (TA_PRECO_MEDICAMENTO_GOV: PF e PMVG); nunca somar as duas | texto |
| `id_na_fonte` | A apresentação: CNPJ (só os dígitos) e código GGREM juntos por `|` | texto |
| `cnpj` | CNPJ do detentor do registro, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `ggrem` | Código GGREM da apresentação, como a CMED escreve | texto |
| `registro` | Registro da apresentação na Anvisa (13 dígitos), como a lista escreve | texto |
| `registro_produto` | Os 9 primeiros dígitos do registro: o produto (vazio quando o registro não tem 13 dígitos). Liga à tabela `anvisa_registros` pelo CNPJ inteiro, nunca pelo nome | texto |
| `eans` | Códigos de barras (EAN 1 a 3) da apresentação, separados por ` / ` | texto |
| `produto` | Nome do produto, como a lista escreve | texto |
| `apresentacao` | Apresentação (concentração, forma e embalagem), como a lista escreve | texto |
| `substancia` | Substância (princípio ativo), como a lista escreve | texto |
| `classe_terapeutica` | Classe terapêutica, como a lista escreve | texto |
| `tipo_de_produto` | Tipo de produto (novo, genérico, similar...), como a lista escreve; vazio onde ela põe `-` | texto |
| `regime_de_preco` | Regime de preço (regulado ou liberado), como a lista escreve | texto |
| `pf_sem_impostos` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), sem impostos | reais (R$) |
| `pf_0` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 0% | reais (R$) |
| `pf_12` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 12% | reais (R$) |
| `pf_12_alc` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 12%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pf_17` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 17% | reais (R$) |
| `pf_17_alc` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 17%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pf_17_5` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 17,5% | reais (R$) |
| `pf_17_5_alc` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 17,5%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pf_18` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 18% | reais (R$) |
| `pf_18_alc` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 18%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pf_19` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 19% | reais (R$) |
| `pf_19_alc` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 19%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pf_19_5` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 19,5% | reais (R$) |
| `pf_19_5_alc` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 19,5%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pf_20` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 20% | reais (R$) |
| `pf_20_alc` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 20%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pf_20_5` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 20,5% | reais (R$) |
| `pf_20_5_alc` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 20,5%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pf_21` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 21% | reais (R$) |
| `pf_21_alc` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 21%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pf_22` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 22% | reais (R$) |
| `pf_22_alc` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 22%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pf_22_5` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 22,5% | reais (R$) |
| `pf_22_5_alc` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 22,5%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pf_23` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 23% | reais (R$) |
| `pf_23_alc` | Preço Fábrica (PF: o teto de venda do fabricante e do distribuidor), com ICMS de 23%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmc_sem_impostos` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), sem impostos | reais (R$) |
| `pmc_0` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 0% | reais (R$) |
| `pmc_12` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 12% | reais (R$) |
| `pmc_12_alc` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 12%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmc_17` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 17% | reais (R$) |
| `pmc_17_alc` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 17%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmc_17_5` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 17,5% | reais (R$) |
| `pmc_17_5_alc` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 17,5%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmc_18` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 18% | reais (R$) |
| `pmc_18_alc` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 18%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmc_19` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 19% | reais (R$) |
| `pmc_19_alc` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 19%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmc_19_5` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 19,5% | reais (R$) |
| `pmc_19_5_alc` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 19,5%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmc_20` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 20% | reais (R$) |
| `pmc_20_alc` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 20%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmc_20_5` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 20,5% | reais (R$) |
| `pmc_20_5_alc` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 20,5%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmc_21` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 21% | reais (R$) |
| `pmc_21_alc` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 21%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmc_22` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 22% | reais (R$) |
| `pmc_22_alc` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 22%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmc_22_5` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 22,5% | reais (R$) |
| `pmc_22_5_alc` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 22,5%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmc_23` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 23% | reais (R$) |
| `pmc_23_alc` | Preço Máximo ao Consumidor (PMC: o teto da farmácia; só na lista `consumidor`, vazio quando a CMED não o publica, nunca zero), com ICMS de 23%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmvg_sem_impostos` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), sem impostos | reais (R$) |
| `pmvg_0` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 0% | reais (R$) |
| `pmvg_12` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 12% | reais (R$) |
| `pmvg_12_alc` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 12%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmvg_17` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 17% | reais (R$) |
| `pmvg_17_alc` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 17%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmvg_17_5` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 17,5% | reais (R$) |
| `pmvg_17_5_alc` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 17,5%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmvg_18` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 18% | reais (R$) |
| `pmvg_18_alc` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 18%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmvg_19` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 19% | reais (R$) |
| `pmvg_19_alc` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 19%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmvg_19_5` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 19,5% | reais (R$) |
| `pmvg_19_5_alc` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 19,5%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmvg_20` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 20% | reais (R$) |
| `pmvg_20_alc` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 20%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmvg_20_5` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 20,5% | reais (R$) |
| `pmvg_20_5_alc` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 20,5%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmvg_21` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 21% | reais (R$) |
| `pmvg_21_alc` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 21%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmvg_22` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 22% | reais (R$) |
| `pmvg_22_alc` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 22%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmvg_22_5` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 22,5% | reais (R$) |
| `pmvg_22_5_alc` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 22,5%, na Área de Livre Comércio (ALC) | reais (R$) |
| `pmvg_23` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 23% | reais (R$) |
| `pmvg_23_alc` | Preço Máximo de Venda ao Governo (PMVG: o PF com o desconto do CAP; só na lista `governo`), com ICMS de 23%, na Área de Livre Comércio (ALC) | reais (R$) |
| `precos_com_asterisco` | Colunas de preço que a lista marca com `*`, separadas por ` / ` (o valor fica, sem a marca; o sentido da marca está na nota da lista) | texto |
| `precos_ilegiveis` | Colunas de preço que não são um número de até 2 casas, com o texto da fonte (`pf_0=1.234,56`): o preço fica vazio | texto |
| `restricao_hospitalar` | Se a venda é restrita a hospitais (Sim/Não da lista) | verdadeiro ou falso |
| `cap` | Se a apresentação está sujeita ao CAP (Sim/Não da lista) | verdadeiro ou falso |
| `confaz_87` | Se está no Convênio ICMS 87/02 do Confaz (Sim/Não da lista) | verdadeiro ou falso |
| `icms_0` | Se a lista marca ICMS 0% (Sim/Não da lista) | verdadeiro ou falso |
| `analise_recursal` | Análise recursal, como a lista escreve | texto |
| `lista_pis_cofins` | Lista de concessão de crédito tributário (PIS/Cofins), como a lista escreve | texto |
| `tarja` | Tarja, como a lista escreve | texto |
| `lista_publicada_em` | Dia em que a fonte diz ter publicado o arquivo (o Last-Modified da coleta; vazio quando o servidor não informou) | data (dia) |
| `consta` | Verdadeiro enquanto a apresentação está na lista; falso na linha do dia em que saiu dela | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que o arquivista viu a linha | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também no 1º (a lista não diz desde quando vale cada preço) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `ans_operadoras`

Cadastro de operadoras de planos de saúde da ANS por CNPJ, em dois arquivos: `ativas` e `canceladas` (com a data e o motivo do descredenciamento). O contato e o representante legal não chegam ao acervo. Uma linha por valor diferente de cada registro: a mudança vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo (ADR 0075): CPF e documento que não fecha o dígito nunca entram, nem o nome de pessoa física; empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado: é arquivo cortado da fonte, não registro que acabou.

- **Fonte:** ANS: dados abertos, cadastro de operadoras (`base/ans_operadoras.py`)
- **Licença:** CC BY (dados abertos da ANS no dados.gov.br; citar a ANS)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a ANS recarrega o arquivo inteiro; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** A fonte publica o estado de hoje: no 1º arquivo guardado a linha vale desde a data do ato público que ela informa, e depois o dia em que o arquivista viu a mudança (o conservador; a história guardada começa no dia em que o arquivista passou a guardar a fonte: ver o histórico da tabela)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `situacao`, `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `registrada_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-16 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ans_operadoras/<situacao>.parquet` (servidor de casa, `base/cadastros_em_retrato.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O que identifica o registro na fonte | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `razao_social` | Razão social da operadora, como a ANS escreve | texto |
| `nome_fantasia` | Nome fantasia, quando a ANS informa | texto |
| `modalidade` | Modalidade (Medicina de Grupo, Cooperativa Médica...) | texto |
| `uf` | UF da sede | texto |
| `registrada_em` | Data do registro na ANS | data (dia) |
| `descredenciada_em` | Data do descredenciamento (só nas canceladas) | data (dia) |
| `motivo_do_descredenciamento` | Motivo, como a ANS escreve (só nas canceladas) | texto |
| `situacao` | `ativas` ou `canceladas`: o arquivo de onde a linha veio | texto |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075); sem CNPJ, falso | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a data do ato público que a fonte informa (nunca depois do dia do arquivo); depois dele, o dia do arquivo em que a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `susep_cadastro`

Entidades supervisionadas pela SUSEP (seguradoras, resseguradores, previdência, capitalização). Entidade estrangeira (ressegurador admitido) não tem CNPJ: a linha fica, com `cnpj` vazio. Endereço e telefone não chegam ao acervo. Uma linha por valor diferente de cada registro: a mudança vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo (ADR 0075): CPF e documento que não fecha o dígito nunca entram, nem o nome de pessoa física; empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado: é arquivo cortado da fonte, não registro que acabou.

- **Fonte:** SUSEP: serviço DadosCadastrais (dados abertos) (`base/susep_cadastro.py`)
- **Licença:** CC BY (SES da SUSEP no dados.gov.br; citar a SUSEP). Só os CSVs sem pessoas
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a SUSEP devolve a lista inteira; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** A fonte publica o estado de hoje: no 1º arquivo guardado a linha vale desde a data do ato público que ela informa, e depois o dia em que o arquivista viu a mudança (o conservador; a história guardada começa no dia em que o arquivista passou a guardar a fonte: ver o histórico da tabela)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `autorizada_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-16 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/susep_cadastro/entidades.parquet` (servidor de casa, `base/cadastros_em_retrato.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O que identifica o registro na fonte | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `codigo_do_mercado` | Código do mercado da SUSEP (1 a 8 e 99), como vem | número inteiro |
| `nome` | Nome da entidade, como a SUSEP escreve | texto |
| `autorizada_em` | Data da autorização para funcionar | data (dia) |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075); sem CNPJ, falso | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a data do ato público que a fonte informa (nunca depois do dia do arquivo); depois dele, o dia do arquivo em que a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `mte_lista_suja`

Cadastro de Empregadores do MTE (a "lista suja" do trabalho análogo ao escravo), só pessoa jurídica. Quando a página do MTE linka CSVs de layouts diferentes, vale o do arquivo baixado mais recentemente. A chave é CNPJ + ano da ação fiscal + estabelecimento: o `ID` do arquivo é só a posição na lista. Ser citado no cadastro não é condenação criminal. Uma linha por valor diferente de cada registro: a mudança vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo (ADR 0075): CPF e documento que não fecha o dígito nunca entram, nem o nome de pessoa física; empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado: é arquivo cortado da fonte, não registro que acabou.

- **Fonte:** MTE: Cadastro de Empregadores (dados abertos) (`base/mte_lista_suja.py`)
- **Licença:** Cadastro de empregadores do MTE (dado público; citar o MTE)
- **Revenda:** só uso interno (entra em modelo; nunca vender nem exportar o dado)
- **Frequência:** Semanal (o MTE atualiza o cadastro; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** A fonte publica o estado de hoje: no 1º arquivo guardado a linha vale desde a data do ato público que ela informa, e depois o dia em que o arquivista viu a mudança (o conservador; a história guardada começa no dia em que o arquivista passou a guardar a fonte: ver o histórico da tabela)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `incluida_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/mte_lista_suja/empregadores.parquet` (servidor de casa, `base/cadastros_em_retrato.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O que identifica o registro na fonte | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `ano_da_acao` | Ano da ação fiscal | número inteiro |
| `uf` | UF do estabelecimento | texto |
| `empregador` | Razão social do empregador pessoa jurídica | texto |
| `estabelecimento` | Endereço do estabelecimento, como a fonte escreve | texto |
| `cnae` | CNAE do estabelecimento, como a fonte escreve | texto |
| `trabalhadores` | Trabalhadores envolvidos na ação | número inteiro |
| `incluida_em` | Data da inclusão no cadastro (a 1ª, se a fonte traz um período) | data (dia) |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075); sem CNPJ, falso | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a data do ato público que a fonte informa (nunca depois do dia do arquivo); depois dele, o dia do arquivo em que a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `ibama_embargos`

Termos de embargo do IBAMA por CNPJ do embargado, um por linha. Só quem, onde, quando e em que situação: a geometria da área e o texto livre não chegam ao acervo. Data de embargo fora de 1980 até o dia do arquivo (a fonte traz anos impossíveis) fica vazia, nunca corrigida. Embargo não é condenação. Uma linha por valor diferente de cada registro: a mudança vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo (ADR 0075): CPF e documento que não fecha o dígito nunca entram, nem o nome de pessoa física; empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado: é arquivo cortado da fonte, não registro que acabou.

- **Fonte:** IBAMA: dados abertos, termos de embargo (`base/ibama_embargos.py`)
- **Licença:** Dados abertos do IBAMA ('Outra (Aberta)'; citar o IBAMA)
- **Revenda:** só uso interno (entra em modelo; nunca vender nem exportar o dado)
- **Frequência:** Semanal (o IBAMA republica o arquivo; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** A fonte publica o estado de hoje: no 1º arquivo guardado a linha vale desde a data do ato público que ela informa, e depois o dia em que o arquivista viu a mudança (o conservador; a história guardada começa no dia em que o arquivista passou a guardar a fonte: ver o histórico da tabela)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `embargada_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ibama_embargos/termos.parquet` (servidor de casa, `base/cadastros_em_retrato.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O que identifica o registro na fonte | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `numero_do_termo` | Número do termo de embargo | texto |
| `nome` | Nome do embargado pessoa jurídica | texto |
| `situacao_do_termo` | Situação do termo, como o IBAMA escreve | texto |
| `cancelado` | Marca de cancelamento do termo, como o IBAMA escreve | texto |
| `codigo_do_municipio` | Código do município (IBGE) do embargo | texto |
| `uf` | UF do embargo | texto |
| `desembargado` | Marca de desembargo, como o IBAMA escreve | texto |
| `numero_do_auto` | Número do auto de infração que gerou o embargo | texto |
| `area_embargada_ha` | Área embargada, em hectares | número com decimais, na unidade da fonte |
| `embargada_em` | Data do embargo | data (dia) |
| `desembargada_em` | Data do desembargo | data (dia) |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075); sem CNPJ, falso | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a data do ato público que a fonte informa (nunca depois do dia do arquivo); depois dele, o dia do arquivo em que a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `inpi_marcas_titulares`

Titulares de marcas depositadas no INPI. Uma linha por pedido e empresa: o número do pedido no INPI e o CNPJ de cada titular que é empresa. Só pessoa jurídica (CNPJ de dígito certo e tipo de pessoa que não é física): o nome, o CPF, o país, o estado, os inventores, autores e procuradores nunca chegam ao acervo. O arquivo de titulares não traz data: a linha vale desde o dia em que o arquivista a viu pela primeira vez, não desde o depósito. Dado do INPI sob licença Creative Commons Atribuição-SemDerivações 3.0 (a confirmar para tabela derivada). Uma linha por valor diferente de cada registro: a mudança vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo (ADR 0075): CPF e documento que não fecha o dígito nunca entram, nem o nome de pessoa física; empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado: é arquivo cortado da fonte, não registro que acabou.

- **Fonte:** INPI: dados abertos, marcas (`MARCAS_DEPOSITANTES.csv`) (`base/inpi_titulares.py`)
- **Licença:** Sem licença do conjunto (rodapé CC BY-ND 3.0); como publicado, citando o INPI
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Mensal (o INPI republica o arquivo inteiro; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** O arquivo de titulares do INPI não traz data de publicação: a linha vale desde o dia em que o arquivista a viu pela primeira vez (o conservador; a história guardada começa no dia em que o arquivista passou a guardar a fonte: ver o histórico da tabela)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/inpi_marcas_titulares/titulares.parquet` (servidor de casa, `base/cadastros_em_retrato.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O que identifica o registro na fonte | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `numero_inpi` | Número do pedido no INPI (a chave para a ficha pública dele no portal) | texto |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075); sem CNPJ, falso | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a data do ato público que a fonte informa (nunca depois do dia do arquivo); depois dele, o dia do arquivo em que a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `inpi_patentes_depositantes`

Depositantes de patentes no INPI. Uma linha por pedido e empresa: o número do pedido no INPI e o CNPJ de cada depositante que é empresa. Só pessoa jurídica (CNPJ de dígito certo e tipo de pessoa que não é física): o nome, o CPF, o país, o estado, os inventores, autores e procuradores nunca chegam ao acervo. Só o titular vigente: a linha com data de fim da titularidade (pedido transferido) não entra, e o titular que a ganha depois passa a `consta` falso. O arquivo não traz data de publicação: a linha vale desde o dia em que o arquivista a viu pela primeira vez, não desde o depósito. Dado do INPI sob licença Creative Commons Atribuição-SemDerivações 3.0 (a confirmar para tabela derivada). Uma linha por valor diferente de cada registro: a mudança vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo (ADR 0075): CPF e documento que não fecha o dígito nunca entram, nem o nome de pessoa física; empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado: é arquivo cortado da fonte, não registro que acabou.

- **Fonte:** INPI: dados abertos, patentes (`PATENTES_DEPOSITANTES.csv`) (`base/inpi_titulares.py`)
- **Licença:** Sem licença do conjunto (rodapé CC BY-ND 3.0); como publicado, citando o INPI
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Mensal (o INPI republica o arquivo inteiro; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** O arquivo de titulares do INPI não traz data de publicação: a linha vale desde o dia em que o arquivista a viu pela primeira vez (o conservador; a história guardada começa no dia em que o arquivista passou a guardar a fonte: ver o histórico da tabela)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/inpi_patentes_depositantes/titulares.parquet` (servidor de casa, `base/cadastros_em_retrato.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O que identifica o registro na fonte | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `numero_inpi` | Número do pedido no INPI (a chave para a ficha pública dele no portal) | texto |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075); sem CNPJ, falso | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a data do ato público que a fonte informa (nunca depois do dia do arquivo); depois dele, o dia do arquivo em que a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `inpi_desenhos_depositantes`

Depositantes de desenhos industriais no INPI. Uma linha por pedido e empresa: o número do pedido no INPI e o CNPJ de cada depositante que é empresa. Só pessoa jurídica (CNPJ de dígito certo e tipo de pessoa que não é física): o nome, o CPF, o país, o estado, os inventores, autores e procuradores nunca chegam ao acervo. O arquivo de titulares não traz data: a linha vale desde o dia em que o arquivista a viu pela primeira vez, não desde o depósito. Dado do INPI sob licença Creative Commons Atribuição-SemDerivações 3.0 (a confirmar para tabela derivada). Uma linha por valor diferente de cada registro: a mudança vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo (ADR 0075): CPF e documento que não fecha o dígito nunca entram, nem o nome de pessoa física; empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado: é arquivo cortado da fonte, não registro que acabou.

- **Fonte:** INPI: dados abertos, desenhos industriais (`DI_DEPOSITANTES.csv`) (`base/inpi_titulares.py`)
- **Licença:** Sem licença do conjunto (rodapé CC BY-ND 3.0); como publicado, citando o INPI
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Mensal (o INPI republica o arquivo inteiro; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** O arquivo de titulares do INPI não traz data de publicação: a linha vale desde o dia em que o arquivista a viu pela primeira vez (o conservador; a história guardada começa no dia em que o arquivista passou a guardar a fonte: ver o histórico da tabela)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/inpi_desenhos_depositantes/titulares.parquet` (servidor de casa, `base/cadastros_em_retrato.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O que identifica o registro na fonte | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `numero_inpi` | Número do pedido no INPI (a chave para a ficha pública dele no portal) | texto |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075); sem CNPJ, falso | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a data do ato público que a fonte informa (nunca depois do dia do arquivo); depois dele, o dia do arquivo em que a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `inpi_programas_titulares`

Titulares de registros de programas de computador no INPI. Uma linha por pedido e empresa: o número do pedido no INPI e o CNPJ de cada titular que é empresa. Só pessoa jurídica (CNPJ de dígito certo e tipo de pessoa que não é física): o nome, o CPF, o país, o estado, os inventores, autores e procuradores nunca chegam ao acervo. Só o titular vigente: a linha com data de fim da titularidade (pedido transferido) não entra, e o titular que a ganha depois passa a `consta` falso. O arquivo não traz data de publicação: a linha vale desde o dia em que o arquivista a viu pela primeira vez, não desde o depósito. Dado do INPI sob licença Creative Commons Atribuição-SemDerivações 3.0 (a confirmar para tabela derivada). Uma linha por valor diferente de cada registro: a mudança vira linha nova que só vale desde o dia em que foi vista, e o registro que some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo (ADR 0075): CPF e documento que não fecha o dígito nunca entram, nem o nome de pessoa física; empresário individual e MEI ficam com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado: é arquivo cortado da fonte, não registro que acabou.

- **Fonte:** INPI: dados abertos, programas de computador (`PROG_COMP_TITULAR.csv`) (`base/inpi_titulares.py`)
- **Licença:** Sem licença do conjunto (rodapé CC BY-ND 3.0); como publicado, citando o INPI
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Mensal (o INPI republica o arquivo inteiro; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** O arquivo de titulares do INPI não traz data de publicação: a linha vale desde o dia em que o arquivista a viu pela primeira vez (o conservador; a história guardada começa no dia em que o arquivista passou a guardar a fonte: ver o histórico da tabela)
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/inpi_programas_titulares/titulares.parquet` (servidor de casa, `base/cadastros_em_retrato.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O que identifica o registro na fonte | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `numero_inpi` | Número do pedido no INPI (a chave para a ficha pública dele no portal) | texto |
| `consta` | Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075); sem CNPJ, falso | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a data do ato público que a fonte informa (nunca depois do dia do arquivo); depois dele, o dia do arquivo em que a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `cvm_fiagro`

O informe mensal de cada classe de Fiagro (Fundo de Investimento nas Cadeias Produtivas Agroindustriais) por CNPJ: cotistas, balanço resumido, rentabilidade e dividend yield do mês, taxas e a carteira por tipo de ativo (imóveis rurais, CRA, CRI, LCA, LCI). Uma linha por classe, mês e versão do informe: o reenvio traz `versao` maior e não apaga a anterior (quem quer o vigente fica com a maior). Contato, nome do administrador e do gestor e as subclasses ficam de fora; administrador e gestor entram só pelo CNPJ. Só classe com CNPJ de dígito certo. A CVM só mantém os meses recentes: a história daqui em diante é a do acervo

- **Fonte:** CVM: informe mensal de Fiagro (`base/cvm_fiagro.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal (um ZIP por mês; o arquivista olha toda semana)
- **Atraso de divulgação:** `disponivel_em` é a `Data_Entrega` do informe (o dia em que chegou à CVM), nunca a referência; sem ela, vale o dia em que o ZIP foi guardado
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2025-10-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/cvm_fiagro/informe.parquet` (servidor de casa, `base/cvm_fiagro.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a classe | texto |
| `referencia` | Mês a que o informe se refere (a `Data_Referencia`) | data (dia) |
| `versao` | Versão do informe; o reenvio traz número maior | número inteiro |
| `nome_da_classe` | Nome da classe, como a CVM escreve | texto |
| `publico_alvo` | Público-alvo da classe, como a CVM escreve | texto |
| `codigo_isin` | Código ISIN da cota, quando informado | texto |
| `mercado_de_negociacao` | Mercado em que a cota negocia, como a CVM escreve | texto |
| `cnpj_administrador` | CNPJ do administrador (só o CNPJ, sem o nome) | texto |
| `cnpj_gestor` | CNPJ do gestor (só o CNPJ, sem o nome) | texto |
| `cotistas` | Número de cotistas | número inteiro |
| `valor_do_ativo` | Valor do ativo, em reais | número com decimais, na unidade da fonte |
| `patrimonio_liquido` | Patrimônio líquido, em reais | número com decimais, na unidade da fonte |
| `cotas_emitidas` | Cotas emitidas | número com decimais, na unidade da fonte |
| `valor_patrimonial_da_cota` | Valor patrimonial da cota, em reais | número com decimais, na unidade da fonte |
| `taxa_de_administracao_pct` | Despesa com taxa de administração, em % do patrimônio | número com decimais, na unidade da fonte |
| `taxa_de_gestao_pct` | Despesa com taxa de gestão, em % do patrimônio | número com decimais, na unidade da fonte |
| `rentabilidade_efetiva_no_mes` | Rentabilidade efetiva do mês, como a CVM informa | número com decimais, na unidade da fonte |
| `rentabilidade_patrimonial_no_mes` | Rentabilidade patrimonial do mês, como a CVM informa | número com decimais, na unidade da fonte |
| `dividend_yield_no_mes` | Dividend yield do mês, como a CVM informa | número com decimais, na unidade da fonte |
| `total_investido` | Total investido, em reais | número com decimais, na unidade da fonte |
| `imoveis_rurais` | Investido em imóveis rurais, em reais | número com decimais, na unidade da fonte |
| `cra` | Investido em CRA, em reais | número com decimais, na unidade da fonte |
| `cri` | Investido em CRI, em reais | número com decimais, na unidade da fonte |
| `lca` | Investido em LCA, em reais | número com decimais, na unidade da fonte |
| `lci` | Investido em LCI, em reais | número com decimais, na unidade da fonte |
| `total_do_passivo` | Total do passivo, em reais | número com decimais, na unidade da fonte |
| `disponivel_em` | Desde quando o informe era público: a `Data_Entrega` (nunca depois do dia em que o ZIP foi guardado) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `gleif_ponte`

A ponte entre o LEI (código global de entidade jurídica, do GLEIF) e o CNPJ das entidades do Brasil: uma linha por valor diferente de cada par LEI e CNPJ, a cada cópia semanal do GLEIF (`consta` falso quando o par some da cópia). Só CNPJ inteiro de dígito certo: CPF, NIRE e vazio ficam fora (o LEI fica sem ponte). Empresário individual (`SOLE_PROPRIETOR`) e LEI marcado `DUPLICATE` pelo GLEIF não entram. `conflito` marca o CNPJ com dois LEIs na mesma cópia: a resolução não liga por ele. Cópia com menos da metade dos pares da anterior é pulada (cópia cortada)

- **Fonte:** GLEIF: base global de LEI, registros do Brasil (`base/gleif.py`)
- **Licença:** CC0 (GLEIF, Global LEI Index)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Semanal (uma cópia por semana; o arquivista guarda só o que mudou)
- **Atraso de divulgação:** No 1º arquivo guardado, `disponivel_em` é a data da cópia do GLEIF (`goldenCopy.publishDate`), nunca depois do dia em que foi guardada; depois, o dia da cópia em que a mudança apareceu
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** sim
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/gleif_ponte/ponte.parquet` (servidor de casa, `base/cadastros_em_retrato.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_na_fonte` | O par: LEI e CNPJ (só os dígitos) juntos por `|` | texto |
| `lei` | LEI (20 caracteres) | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): a empresa | texto |
| `nome` | Nome legal da entidade, como o GLEIF escreve | texto |
| `autoridade` | Autoridade de registro que informou o CNPJ (`RA000681` é a Receita) | texto |
| `categoria` | Categoria da entidade no GLEIF (`GENERAL`, `FUND`, `BRANCH`...) | texto |
| `situacao_do_lei` | Situação do LEI (`ISSUED`, `LAPSED`...) | texto |
| `conflito` | Verdadeiro quando o CNPJ aparece em mais de um LEI na cópia | verdadeiro ou falso |
| `consta` | Verdadeiro enquanto o par está na cópia; falso na linha do dia em que saiu | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075) | verdadeiro ou falso |
| `visto_em` | Dia da cópia em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base (ver o atraso) | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `fip_informe`

O informe dos Fundos de Investimento em Participações (FIP) por CNPJ do fundo ou da classe: patrimônio, cotas, cotistas por tipo, capital comprometido, subscrito e integralizado. Trimestral até 2023 e quadrimestral desde 2024 (Resolução CVM 175), numa tabela só (`periodicidade`). Uma linha por fundo e competência. Só fundo com CNPJ de dígito certo; o nome é o do fundo

- **Fonte:** CVM: informe trimestral e quadrimestral de FIP (`base/cvm_fip_fii.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Um arquivo por ano, republicado inteiro (o arquivista olha toda semana)
- **Atraso de divulgação:** O arquivo não traz a data de entrega: vale o dia em que o arquivista o viu
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-25 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fip_informe/<arquivo do ano>.parquet` (servidor de casa, `base/cvm_fip_fii.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): o fundo ou a classe | texto |
| `competencia` | Data de competência do informe | data (dia) |
| `periodicidade` | `trimestral` (até 2023) ou `quadrimestral` (desde 2024) | texto |
| `tipo_fundo_classe` | Fundo ou classe (só no quadrimestral) | texto |
| `nome_do_fundo` | Nome do fundo, como a CVM escreve | texto |
| `entidade_de_investimento` | Se é entidade de investimento (S/N) | texto |
| `publico_alvo` | Público-alvo, como a CVM escreve | texto |
| `patrimonio_liquido` | Patrimônio líquido, em reais | número com decimais, na unidade da fonte |
| `cotas` | Quantidade de cotas | número com decimais, na unidade da fonte |
| `valor_patrimonial_da_cota` | Valor patrimonial da cota, em reais | número com decimais, na unidade da fonte |
| `cotistas` | Número de cotistas | número inteiro |
| `capital_comprometido` | Capital comprometido, em reais | número com decimais, na unidade da fonte |
| `capital_subscrito` | Capital subscrito, em reais | número com decimais, na unidade da fonte |
| `capital_integralizado` | Capital integralizado, em reais | número com decimais, na unidade da fonte |
| `investido_em_cotas_de_fip` | Investido em cotas de outros FIP, em reais | número com decimais, na unidade da fonte |
| `cotistas_pessoa_fisica` | Quantos cotistas subscritores são pessoa física (só a contagem) | número inteiro |
| `cotistas_empresa_nao_financeira` | Quantos cotistas subscritores são empresa não financeira | número inteiro |
| `cotistas_nao_residentes` | Quantos cotistas subscritores são investidores não residentes | número inteiro |
| `cotistas_previdencia_fechada` | Quantos cotistas subscritores são entidade fechada de previdência | número inteiro |
| `cotistas_regime_proprio` | Quantos cotistas subscritores são regime próprio de previdência | número inteiro |
| `id_na_fonte` | Identificador da linha no arquivo da fonte | texto |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075): a porta não serve a linha | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que ela (ou a mudança) apareceu; o arquivo não diz quando cada linha saiu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `fii_informe_mensal`

O informe mensal dos Fundos de Investimento Imobiliário (FII) por CNPJ do fundo ou da classe: segmento, mandato, gestão, ISIN, administrador (só o CNPJ), cotistas, ativo, patrimônio, cota, taxa de administração, rentabilidade e dividend yield do mês. Uma linha por fundo, mês e versão do informe: o reenvio traz `versao` maior e não apaga a anterior. Contato, endereço, nome do administrador e o vínculo familiar dos cotistas ficam de fora. Só fundo com CNPJ de dígito certo

- **Fonte:** CVM: informe mensal de FII, partes geral e complemento (`base/cvm_fip_fii.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Um ZIP por ano, republicado inteiro (o arquivista olha toda semana)
- **Atraso de divulgação:** `disponivel_em` é a `Data_Entrega` do informe, nunca depois do dia em que o ZIP foi guardado; informe que só aparece num arquivo seguinte vale do dia desse arquivo
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-25 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fii_informe_mensal/<arquivo do ano>.parquet` (servidor de casa, `base/cvm_fip_fii.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): o fundo ou a classe | texto |
| `referencia` | Mês a que o informe se refere (a `Data_Referencia`) | data (dia) |
| `versao` | Versão do informe; o reenvio traz número maior | número inteiro |
| `entregue_em` | Dia em que o informe chegou à CVM (`Data_Entrega`) | data (dia) |
| `tipo_fundo_classe` | Fundo ou classe, como a CVM escreve | texto |
| `nome_do_fundo` | Nome do fundo ou da classe, como a CVM escreve | texto |
| `publico_alvo` | Público-alvo, como a CVM escreve | texto |
| `codigo_isin` | Código ISIN da cota, quando informado | texto |
| `fundo_exclusivo` | Se é fundo exclusivo (S/N) | texto |
| `mandato` | Mandato do fundo (renda, desenvolvimento, títulos...), como a CVM escreve | texto |
| `segmento_de_atuacao` | Segmento de atuação (logística, lajes, shoppings...), como a CVM escreve | texto |
| `tipo_de_gestao` | Gestão ativa ou passiva | texto |
| `prazo_de_duracao` | Prazo de duração, como a CVM escreve | texto |
| `negocia_em_bolsa` | Se a cota negocia em bolsa (S/N) | texto |
| `funciona_desde` | Data de início de funcionamento | data (dia) |
| `cnpj_administrador` | CNPJ do administrador (só o CNPJ, sem o nome) | texto |
| `cotistas` | Número de cotistas | número inteiro |
| `cotistas_pessoa_fisica` | Quantos cotistas são pessoa física (só a contagem) | número inteiro |
| `valor_do_ativo` | Valor do ativo, em reais | número com decimais, na unidade da fonte |
| `patrimonio_liquido` | Patrimônio líquido, em reais | número com decimais, na unidade da fonte |
| `cotas_emitidas` | Cotas emitidas | número com decimais, na unidade da fonte |
| `valor_patrimonial_da_cota` | Valor patrimonial da cota, em reais | número com decimais, na unidade da fonte |
| `taxa_de_administracao_pct` | Despesa com taxa de administração, em % do patrimônio | número com decimais, na unidade da fonte |
| `rentabilidade_efetiva_no_mes` | Rentabilidade efetiva do mês, como a CVM informa | número com decimais, na unidade da fonte |
| `rentabilidade_patrimonial_no_mes` | Rentabilidade patrimonial do mês, como a CVM informa | número com decimais, na unidade da fonte |
| `dividend_yield_no_mes` | Dividend yield do mês, como a CVM informa | número com decimais, na unidade da fonte |
| `id_na_fonte` | Identificador da linha no arquivo da fonte | texto |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075): a porta não serve a linha | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a `Data_Entrega` do informe (o dia em que chegou à CVM), nunca depois do dia do arquivo; depois dele, o dia do arquivo em que a linha nova ou a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `fii_ativos`

Os títulos e valores mobiliários que cada FII declara no informe trimestral (CRI, ações, debêntures, cotas de outros fundos...), com o CNPJ do emissor: liga uma empresa aos FII que carregam os papéis dela. Uma linha por fundo, trimestre, versão do informe e ativo. O nome do emissor só entra quando o CNPJ dele fecha o dígito; a linha é marcada como de pessoa se o fundo ou o emissor for empresário individual ou MEI. Imóveis e terrenos (que trazem endereço) ficam de fora

- **Fonte:** CVM: informe trimestral de FII, parte de ativos (`base/cvm_fip_fii.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Um ZIP por ano, republicado inteiro (o arquivista olha toda semana)
- **Atraso de divulgação:** `disponivel_em` é a `Data_Entrega` do informe trimestral (parte geral), nunca depois do dia em que o ZIP foi guardado; ativo que só aparece num arquivo seguinte vale do dia desse arquivo
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-25 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fii_ativos/<arquivo do ano>.parquet` (servidor de casa, `base/cvm_fip_fii.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): o fundo ou a classe | texto |
| `referencia` | Trimestre a que o informe se refere (a `Data_Referencia`) | data (dia) |
| `versao` | Versão do informe; o reenvio traz número maior | número inteiro |
| `entregue_em` | Dia em que o informe chegou à CVM (`Data_Entrega` da parte geral) | data (dia) |
| `cnpj_emissor` | CNPJ do emissor do ativo, quando fecha o dígito | texto |
| `cnpj_basico_emissor` | Raiz do CNPJ do emissor (8 caracteres) | texto |
| `emissor` | Nome do emissor, como a CVM escreve (só com CNPJ de dígito certo) | texto |
| `tipo_do_ativo` | Tipo do ativo (CRI, ações, debêntures...), como a CVM escreve | texto |
| `emissao` | Número da emissão, como a CVM escreve | texto |
| `serie` | Série, como a CVM escreve | texto |
| `codigo` | Código de negociação, quando informado | texto |
| `nome_do_ativo` | Nome do ativo, como a CVM escreve | texto |
| `vencimento` | Vencimento do ativo, quando há | data (dia) |
| `quantidade` | Quantidade do ativo na carteira | número com decimais, na unidade da fonte |
| `valor` | Valor do ativo na carteira, em reais | número com decimais, na unidade da fonte |
| `id_na_fonte` | Identificador da linha no arquivo da fonte | texto |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075): a porta não serve a linha | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a `Data_Entrega` do informe (o dia em que chegou à CVM), nunca depois do dia do arquivo; depois dele, o dia do arquivo em que a linha nova ou a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `fii_administradores`

Quem a CVM registrou para administrar FII, pelo CNPJ: razão social, nome comercial, situação e as datas do registro, da situação e do cancelamento. Endereço, telefone e e-mail ficam de fora (só a UF entra). Só CNPJ de dígito certo

- **Fonte:** CVM: cadastro de administradores de FII (`base/cvm_fip_fii.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Um arquivo, republicado inteiro (o arquivista olha toda semana)
- **Atraso de divulgação:** O cadastro não diz quando cada linha mudou: vale o dia em que o arquivista a viu
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `registrado_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-25 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fii_administradores/administradores.parquet` (servidor de casa, `base/cvm_fip_fii.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres): o administrador | texto |
| `razao_social` | Razão social, como a CVM escreve | texto |
| `nome_comercial` | Nome comercial, como a CVM escreve | texto |
| `motivo_do_cancelamento` | Motivo do cancelamento do registro, quando há | texto |
| `situacao` | Situação do registro na CVM, como a CVM escreve | texto |
| `uf` | UF da sede | texto |
| `registrado_em` | Data do registro na CVM | data (dia) |
| `cancelado_em` | Data do cancelamento do registro, quando há | data (dia) |
| `situacao_desde` | Desde quando vale a situação | data (dia) |
| `id_na_fonte` | Identificador da linha no arquivo da fonte | texto |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075): a porta não serve a linha | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que ela (ou a mudança) apareceu; o arquivo não diz quando cada linha saiu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `aneel_inadimplencia`

Os indicadores de inadimplência que cada distribuidora de energia manda à ANEEL, por CNPJ, indicador e mês: quanto deixa de receber dos consumidores, em cada recorte que a ANEEL pede. A descrição do indicador vem do domínio da própria ANEEL guardado até o dia do arquivo. Só distribuidora com CNPJ de dígito certo; o nome por extenso fica de fora

- **Fonte:** ANEEL: dados abertos, inadimplência das distribuidoras (`base/aneel_indicadores.py`)
- **Licença:** ODbL (dados abertos da ANEEL; citar). SAMP sem CPF e nome do consumidor
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Um arquivo, republicado inteiro (o arquivista olha toda semana)
- **Atraso de divulgação:** A ANEEL escreve a data de geração do conjunto; o mês mais novo costuma ter de 1 a 3 meses
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-25 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/aneel_inadimplencia/inadimplencia.parquet` (servidor de casa, `base/aneel_indicadores.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da distribuidora (14 dígitos com máscara) | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres) | texto |
| `sigla_do_agente` | Sigla da distribuidora na ANEEL | texto |
| `indicador` | Sigla do indicador, como a ANEEL escreve | texto |
| `descricao_do_indicador` | Descrição do indicador no domínio da ANEEL; vazia quando a sigla não está no domínio | texto |
| `referencia` | Mês do indicador (dia 1) | data (dia) |
| `valor` | Valor do indicador, na unidade que a ANEEL define para ele | número com decimais, na unidade da fonte |
| `id_na_fonte` | Identificador da linha no arquivo da fonte | texto |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075): a porta não serve a linha | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a data de geração do conjunto que a ANEEL escreve no arquivo, nunca depois do dia do arquivo; depois dele, o dia do arquivo em que a linha nova ou a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `aneel_indicadores_comerciais`

Os indicadores comerciais de cada distribuidora de energia por CNPJ, município e mês (INDGER): unidades consumidoras ativas e faturadas, faturas sem leitura, refaturamentos, pedidos e pagamentos de ressarcimento de dano, postos de atendimento e suspensões por inadimplência (inclusive as indevidas e a compensação paga). Só distribuidora com CNPJ de dígito certo; o nome por extenso fica de fora

- **Fonte:** ANEEL: dados abertos, INDGER dados comerciais (`base/aneel_indicadores.py`)
- **Licença:** ODbL (dados abertos da ANEEL; citar). SAMP sem CPF e nome do consumidor
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Um arquivo, republicado inteiro (o arquivista olha toda semana)
- **Atraso de divulgação:** A ANEEL escreve a data de geração do conjunto; o mês mais novo costuma ter de 1 a 3 meses
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-25 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/aneel_indicadores_comerciais/comerciais.parquet` (servidor de casa, `base/aneel_indicadores.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da distribuidora (14 dígitos com máscara) | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres) | texto |
| `sigla_do_agente` | Sigla da distribuidora na ANEEL | texto |
| `tipo_de_outorga` | Concessão ou permissão, como a ANEEL escreve | texto |
| `referencia` | Mês informado (dia 1) | data (dia) |
| `municipio_ibge` | Código IBGE do município (7 dígitos); vazio quando a fonte manda `0` | texto |
| `unidades_ativas` | Unidades consumidoras ativas | número com decimais, na unidade da fonte |
| `unidades_faturadas` | Unidades consumidoras ativas faturadas | número com decimais, na unidade da fonte |
| `faturas` | Faturas emitidas | número com decimais, na unidade da fonte |
| `faturas_sem_leitura` | Faturas emitidas sem leitura do medidor | número com decimais, na unidade da fonte |
| `refaturamentos` | Refaturamentos | número com decimais, na unidade da fonte |
| `pedidos_de_ressarcimento_de_dano` | Pedidos de ressarcimento de dano elétrico | número com decimais, na unidade da fonte |
| `ressarcimentos_indeferidos` | Pedidos de ressarcimento indeferidos | número com decimais, na unidade da fonte |
| `valor_pago_de_ressarcimento` | Valor pago de ressarcimento de dano, em reais | número com decimais, na unidade da fonte |
| `postos_de_atendimento` | Postos de atendimento presencial | número com decimais, na unidade da fonte |
| `unidades_suspensas_por_inadimplencia` | Unidades com fornecimento suspenso por inadimplência | número com decimais, na unidade da fonte |
| `suspensoes_indevidas` | Suspensões indevidas de fornecimento | número com decimais, na unidade da fonte |
| `valor_de_compensacao_por_suspensao_indevida` | Compensação paga por suspensão indevida, em reais | número com decimais, na unidade da fonte |
| `id_na_fonte` | Identificador da linha no arquivo da fonte | texto |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075): a porta não serve a linha | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: no 1º arquivo, a data de geração do conjunto que a ANEEL escreve no arquivo, nunca depois do dia do arquivo; depois dele, o dia do arquivo em que a linha nova ou a mudança apareceu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `ans_idss`

O Índice de Desempenho da Saúde Suplementar (IDSS) de cada operadora de plano de saúde, por CNPJ, índice (o IDSS e as dimensões dele) e ano de avaliação, desde 2009. De 2009 a 2011 a ANS publica só a faixa (`0,40 a 0,59`); depois, a nota. Nota `ND` (não disponível) não vira linha. Só operadora com CNPJ de dígito certo; a razão social fica de fora (o nome está em `ans_operadoras`)

- **Fonte:** ANS: dados abertos, histórico do IDSS (`base/ans_idss.py`)
- **Licença:** CC BY (dados abertos da ANS no dados.gov.br; citar a ANS)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Três arquivos, republicados inteiros; o mais novo ganha um ano por ano (o arquivista olha toda semana)
- **Atraso de divulgação:** A ANS publica a avaliação de um ano (ano base) no ano seguinte; o arquivo não diz o dia
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `id_na_fonte`, `visto_em`
- **Três datas:** aconteceu_em = `disponivel_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-25 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ans_idss/{de_2009,de_2012,de_2016}.parquet` (servidor de casa, `base/ans_idss.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da operadora (14 dígitos com máscara) | texto |
| `cnpj_basico` | Raiz do CNPJ (8 caracteres) | texto |
| `registro_operadora` | Registro da operadora na ANS | texto |
| `modalidade` | Modalidade (Medicina de Grupo, Cooperativa Médica...), como a ANS escreve | texto |
| `indice` | O índice: `IDSS` ou uma dimensão dele (`IDQS`, `IDGA`, `IDSM`, `IDGR`...) | texto |
| `ano_avaliacao` | Ano da avaliação, como está no nome da coluna da ANS | número inteiro |
| `ano_base` | Ano base (o ano avaliado) | número inteiro |
| `valor` | Nota de 0 a 1; vazia quando a ANS publica a faixa | número com decimais, na unidade da fonte |
| `faixa` | Faixa da nota (`0,40 a 0,59`), só de 2009 a 2011 | texto |
| `id_na_fonte` | Identificador da linha no arquivo da fonte | texto |
| `consta` | Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a Receita guardada não tem (ADR 0075): a porta não serve a linha | verdadeiro ou falso |
| `visto_em` | Dia do arquivo em que esta versão da linha foi vista | data (dia) |
| `disponivel_em` | Desde quando a linha vale para a base: o dia do arquivo em que ela (ou a mudança) apareceu; o arquivo não diz quando cada nota saiu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `cnes_estabelecimentos`

Estabelecimentos de saúde do CNES por competência, com o CNPJ do estabelecimento e o da mantenedora em colunas separadas. Estabelecimento sem nenhum CNPJ (pessoa física) fica sem nome; endereço, CEP, telefone e e-mail da fonte nunca entram. Razão social de empresário individual pode ser nome de pessoa: a tabela é marcada como de pessoa. Competência vazia não grava linha: veja `cnes_competencias`.

- **Fonte:** Ministério da Saúde, DATASUS, API de dados abertos do CNES (`base/cnes.py`)
- **Licença:** CNES do Ministério da Saúde: uso comercial liberado (LAI, 05/11/2026); citar
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a coleta olha as competências mais recentes; as já gravadas não mudam sem dado novo)
- **Atraso de divulgação:** A API não diz quando publicou cada competência (o FTP publica por volta do dia 15 do mês seguinte): a competência vale desde o dia em que a coleta a viu, e a última com dado fica 1 a 3 meses atrás
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `competencia`, `codigo_cnes`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/cnes_estabelecimentos/<AAAAMM>.parquet` (servidor de casa, `scripts/carga_cnes.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Competência do cadastro, no formato AAAAMM | número inteiro |
| `codigo_cnes` | Código do estabelecimento no CNES (7 dígitos) | texto |
| `cnpj` | CNPJ do estabelecimento, só os 14 dígitos; vazio na unidade pública que não tem CNPJ próprio e no CPF (CPF nunca vira CNPJ) | texto |
| `cnpj_mantenedora` | CNPJ de quem mantém o estabelecimento (a prefeitura, a rede), só os 14 dígitos. Não substitui o `cnpj`, e a mantenedora não é dona de tudo o que mantém | texto |
| `razao_social` | Nome empresarial; vazio quando não há nenhum CNPJ (pessoa física) | texto |
| `nome_fantasia` | Nome fantasia; vazio quando não há nenhum CNPJ (pessoa física) | texto |
| `codigo_ibge_municipio` | Código IBGE do município do estabelecimento | texto |
| `gestao` | Tipo de gestão (municipal, estadual, dupla...), como a fonte escreve | texto |
| `tipo_unidade` | Tipo de unidade (hospital geral, posto de saúde...), como a fonte escreve | texto |
| `classificacao` | Classificação do estabelecimento, como a fonte escreve | texto |
| `natureza_juridica` | Natureza jurídica, como a fonte escreve | texto |
| `grupo_natureza_juridica` | Grupo da natureza jurídica, como a fonte escreve | texto |
| `latitude` | Latitude do estabelecimento (graus); vazio quando a fonte não informa | número com decimais, na unidade da fonte |
| `longitude` | Longitude do estabelecimento (graus); vazio quando a fonte não informa | número com decimais, na unidade da fonte |
| `situacao_cnes` | Situação do estabelecimento (ativo ou não), como a fonte escreve | texto |
| `disponivel_em` | Dia em que a coleta viu a competência pela primeira vez (a API não dá a data de publicação); `competencia` nunca serve de disponibilidade | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `cnes_competencias`

Uma linha por competência do CNES olhada pela coleta, dizendo se veio com dados ou vazia. Serve para não confundir competência ainda não publicada com ausência de estabelecimentos.

- **Fonte:** Ministério da Saúde, DATASUS, API de dados abertos do CNES (`base/cnes.py`)
- **Licença:** CNES do Ministério da Saúde: uso comercial liberado (LAI, 05/11/2026); citar
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a coleta olha as competências mais recentes; as já gravadas não mudam sem dado novo)
- **Atraso de divulgação:** A API não diz quando publicou cada competência (o FTP publica por volta do dia 15 do mês seguinte): a competência vale desde o dia em que a coleta a viu, e a última com dado fica 1 a 3 meses atrás
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `competencia`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `coletado_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/cnes_competencias/<AAAAMM>.parquet` (servidor de casa, `scripts/carga_cnes.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Competência olhada, no formato AAAAMM | número inteiro |
| `linhas` | Quantos estabelecimentos a fonte devolveu na competência | número inteiro |
| `situacao` | `com_dados` ou `vazia`. `vazia` é a fonte ainda não ter publicado a competência: nunca significa que não há estabelecimentos | texto |
| `coletado_em` | Dia em que a competência foi vista pela primeira vez com essa situação | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `sus_internacoes`

Internações do SUS por estabelecimento e mês (SIH, AIH reduzida), com o CNPJ do estabelecimento e o da mantenedora. Só o total do mês: nada do paciente. Mês com menos de 10 internações sai suprimido; estabelecimento de pessoa física fica fora. Não treina modelo (`coletas.FONTES_SEM_TREINO`, ADR 0122).

- **Fonte:** Ministério da Saúde, DATASUS, FTP do SIH/SUS, arquivos RD (`base/sus.py`)
- **Licença:** CNES do Ministério da Saúde: uso comercial liberado (LAI, 05/11/2026); citar
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a coleta olha as competências recentes; as gravadas não mudam sem dado novo)
- **Atraso de divulgação:** O DATASUS publica a competência por volta de dois meses depois e reprocessa as anteriores: a competência vale desde o dia em que a coleta a viu (`disponivel_em`), e o reprocesso que muda um número vira versão nova com a data nova
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `codigo_cnes`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-11-06 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/sus_internacoes/<AAAAMM>.parquet` (servidor de casa, `scripts/carga_sus.py`)
- **Linhagem:** O `.json` ao lado do Parquet guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada DBC do FTP somado e a versão do código que gravou. O DBC não fica no acervo: é lido na memória, somado e descartado, e a linha do paciente nunca chega ao disco (ADR 0088, Emenda 1).

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Competência do arquivo (mês de processamento do DATASUS), no formato AAAAMM; não é o mês da alta nem do atendimento | número inteiro |
| `codigo_cnes` | Código do estabelecimento no CNES (7 dígitos); liga a `cnes_estabelecimentos` | texto |
| `cnpj` | CNPJ do próprio estabelecimento, só os 14 dígitos com DV conferido; vazio na unidade pública sem CNPJ próprio. CPF nunca entra: o estabelecimento de pessoa física fica fora | texto |
| `cnpj_mantenedora` | CNPJ de quem mantém o estabelecimento (a prefeitura, a rede), só os 14 dígitos com DV conferido. Não substitui o `cnpj` | texto |
| `codigo_ibge_municipio` | Código IBGE do município do estabelecimento (6 dígitos) | texto |
| `uf` | UF do arquivo do DATASUS | texto |
| `internacoes` | AIH pagas no mês, sem as de longa permanência (como o TabNet); vazio se suprimida | número inteiro |
| `valor_total` | Valor total das AIH do mês, todas as AIH; vazio se suprimida | reais (R$) |
| `valor_uti` | Parte do valor que é de UTI; vazio se suprimida | reais (R$) |
| `dias_permanencia` | Dias de permanência somados de todas as AIH; vazio se suprimida | número inteiro |
| `obitos` | Óbitos nas internações do mês; vazio se suprimida ou com menos de 20 | número inteiro |
| `suprimida` | Verdadeiro quando o mês teve menos de 10 e os números saíram vazios (ADR 0081, item 4): a célula pequena nunca chega ao acervo | verdadeiro ou falso |
| `obitos_suprimidos` | Verdadeiro quando os óbitos saíram vazios por serem menos de 20 no mês | verdadeiro ou falso |
| `disponivel_em` | Dia em que a coleta viu a competência pela primeira vez com esses números (o DATASUS não diz quando publicou); `competencia` nunca serve de disponibilidade | data (dia) |

## `sus_ambulatorial`

Produção ambulatorial do SUS por estabelecimento e mês (SIA, arquivos PA), com o CNPJ do estabelecimento e o da mantenedora. Só o total do mês: nada do paciente. Mês com menos de 10 procedimentos aprovados sai suprimido; estabelecimento de pessoa física fica fora. Não treina modelo (`coletas.FONTES_SEM_TREINO`, ADR 0122).

- **Fonte:** Ministério da Saúde, DATASUS, FTP do SIA/SUS, arquivos PA (`base/sus.py`)
- **Licença:** CNES do Ministério da Saúde: uso comercial liberado (LAI, 05/11/2026); citar
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a coleta olha as competências recentes; as gravadas não mudam sem dado novo)
- **Atraso de divulgação:** O DATASUS publica a competência por volta de dois meses depois e reprocessa as anteriores: a competência vale desde o dia em que a coleta a viu (`disponivel_em`), e o reprocesso que muda um número vira versão nova com a data nova
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `codigo_cnes`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2026-11-06 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/sus_ambulatorial/<AAAAMM>.parquet` (servidor de casa, `scripts/carga_sus.py`)
- **Linhagem:** O `.json` ao lado do Parquet guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada DBC do FTP somado e a versão do código que gravou. O DBC não fica no acervo: é lido na memória, somado e descartado, e a linha do paciente nunca chega ao disco (ADR 0088, Emenda 1).

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Competência do arquivo (mês de processamento do DATASUS), no formato AAAAMM; não é o mês da alta nem do atendimento | número inteiro |
| `codigo_cnes` | Código do estabelecimento no CNES (7 dígitos); liga a `cnes_estabelecimentos` | texto |
| `cnpj` | CNPJ do próprio estabelecimento, só os 14 dígitos com DV conferido; vazio na unidade pública sem CNPJ próprio. CPF nunca entra: o estabelecimento de pessoa física fica fora | texto |
| `cnpj_mantenedora` | CNPJ de quem mantém o estabelecimento (a prefeitura, a rede), só os 14 dígitos com DV conferido. Não substitui o `cnpj` | texto |
| `codigo_ibge_municipio` | Código IBGE do município do estabelecimento (6 dígitos) | texto |
| `uf` | UF do arquivo do DATASUS | texto |
| `quantidade_apresentada` | Procedimentos apresentados no mês; vazio se suprimida | número inteiro |
| `quantidade_aprovada` | Procedimentos aprovados no mês (a supressão olha esta); vazio se suprimida | número inteiro |
| `valor_apresentado` | Valor apresentado dos procedimentos; vazio se suprimida | reais (R$) |
| `valor_aprovado` | Valor aprovado dos procedimentos; vazio se suprimida | reais (R$) |
| `suprimida` | Verdadeiro quando o mês teve menos de 10 e os números saíram vazios (ADR 0081, item 4): a célula pequena nunca chega ao acervo | verdadeiro ou falso |
| `disponivel_em` | Dia em que a coleta viu a competência pela primeira vez com esses números (o DATASUS não diz quando publicou); `competencia` nunca serve de disponibilidade | data (dia) |

## `sus_competencias`

Uma linha por sistema, competência e UF olhados pela coleta do SUS: os arquivos lidos, quantos registros se somaram e quantos estabelecimentos saíram suprimidos ou fora. **Só interna:** `registros` menos a soma publicada revelaria a célula suprimida, então a tabela não sai no site, na API nem na ficha (`vitrine.TABELAS_SO_INTERNAS`).

- **Fonte:** Ministério da Saúde, DATASUS, FTP do SIH/SUS e do SIA/SUS (`base/sus.py`)
- **Licença:** CNES do Ministério da Saúde: uso comercial liberado (LAI, 05/11/2026); citar
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a coleta olha as competências recentes; as gravadas não mudam sem dado novo)
- **Atraso de divulgação:** O DATASUS publica a competência por volta de dois meses depois e reprocessa as anteriores: a competência vale desde o dia em que a coleta a viu (`disponivel_em`), e o reprocesso que muda um número vira versão nova com a data nova
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `sistema`, `competencia`, `uf`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `coletado_em`
- **Histórico desde:** 2026-11-06 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/sus_competencias/<sistema>-<AAAAMM>.parquet` (servidor de casa, `scripts/carga_sus.py`)
- **Linhagem:** O `.json` ao lado do Parquet guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada DBC do FTP somado e a versão do código que gravou. O DBC não fica no acervo: é lido na memória, somado e descartado, e a linha do paciente nunca chega ao disco (ADR 0088, Emenda 1).

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Competência olhada, no formato AAAAMM | número inteiro |
| `uf` | UF olhada | texto |
| `sistema` | `sih` ou `sia` | texto |
| `arquivos` | Nomes dos DBC lidos no FTP, separados por vírgula | texto |
| `sha256` | SHA-256 de cada DBC, na ordem de `arquivos` | texto |
| `registros` | Quantas linhas dos DBC foram somadas | número inteiro |
| `estabelecimentos` | Quantos estabelecimentos saíram na tabela | número inteiro |
| `suprimidos` | Quantos saíram com os números vazios | número inteiro |
| `fora_pessoa_fisica` | Quantos ficaram fora por serem de pessoa física (CPF) | número inteiro |
| `fora_sem_cnpj` | Quantos ficaram fora por não terem CNPJ nenhum | número inteiro |
| `fora_sem_cnes` | Linhas do DBC sem código do estabelecimento, que não se somam | número inteiro |
| `situacao` | `com_dados` ou `vazia`. `vazia` é o DATASUS ainda não ter publicado a competência | texto |
| `coletado_em` | Dia em que a competência foi vista com essa situação | data (dia) |

## `tce_pe_contratos`

Contratos do TCE-PE (estaduais e municipais) por contratado. Só pessoa jurídica (CNPJ válido); nenhum nome, CPF, endereço ou texto livre. Uso interno, licença a confirmar.

- **Fonte:** TCE-PE, API Dados Abertos (`Contratos`)
- **Licença:** TCE-PE: licença não localizada; risco assumido (ADR 0122)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Anual (um pedido por ano; refazer o ano corrente a cada trimestre)
- **Atraso de divulgação:** Sem data de publicação na fonte: a linha vale desde o download
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `codigo_contrato`, `cnpj`
- **Três datas:** aconteceu_em = `vigencia_inicio`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/tce_pe_contratos/<ano>.parquet` (`scripts/carga_tces.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `codigo_contrato` | Código do contrato no TCE-PE | texto |
| `numero_contrato` | Número do contrato, como a fonte escreve | texto |
| `ano_contrato` | Ano do contrato | texto |
| `codigo_ug` | Código da unidade gestora | texto |
| `codigo_efisco_ug` | Código e-Fisco da unidade gestora | texto |
| `municipio` | Município da unidade gestora, como a fonte escreve | texto |
| `situacao` | Situação, como a fonte escreve | texto |
| `estagio` | Estágio, como a fonte escreve | texto |
| `link` | Endereço do documento na fonte | texto |
| `vigencia_inicio` | Início da vigência (a fonte traz o período numa frase) | data (dia) |
| `vigencia_fim` | Fim da vigência | data (dia) |
| `esfera` | Esfera (estadual ou municipal), como a fonte escreve | texto |
| `tipo_processo` | Tipo do processo de contratação, como a fonte escreve | texto |
| `numero_processo` | Número do processo de contratação | texto |
| `valor` | Valor do contrato, em reais | número com decimais, na unidade da fonte |
| `tribunal` | Tribunal de contas de origem: `pe`, `sp`, `ce` ou `rs` | texto |
| `tabela` | Assunto da linha dentro do tribunal (contratos, aditivos, despesas) | texto |
| `cnpj` | CNPJ do contratado ou fornecedor, só os 14 dígitos com o dígito verificador certo. Linha de pessoa física, de CPF ou de CNPJ inválido não entra; nome, endereço e texto livre nunca são gravados | texto |
| `disponivel_em` | Dia do download. Nenhuma das fontes diz quando a linha ficou pública, então o dado só vale a partir do dia em que a coleta o viu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `tce_pe_aditivos`

Termos aditivos dos contratos do TCE-PE por contratado. Só pessoa jurídica (CNPJ válido); nenhum nome, CPF, endereço ou texto livre. Uso interno, licença a confirmar.

- **Fonte:** TCE-PE, API Dados Abertos (`TermoAditivo`)
- **Licença:** TCE-PE: licença não localizada; risco assumido (ADR 0122)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Anual (um pedido por ano; refazer o ano corrente a cada trimestre)
- **Atraso de divulgação:** Sem data de publicação na fonte: a linha vale desde o download
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `codigo_contrato`, `numero_aditivo`, `ano_aditivo`, `cnpj`
- **Três datas:** aconteceu_em = `vigencia_inicio`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/tce_pe_aditivos/<ano>.parquet` (`scripts/carga_tces.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `codigo_contrato` | Código do contrato no TCE-PE | texto |
| `numero_contrato` | Número do contrato, como a fonte escreve | texto |
| `ano_contrato` | Ano do contrato | texto |
| `codigo_ug` | Código da unidade gestora | texto |
| `codigo_efisco_ug` | Código e-Fisco da unidade gestora | texto |
| `municipio` | Município da unidade gestora, como a fonte escreve | texto |
| `situacao` | Situação, como a fonte escreve | texto |
| `estagio` | Estágio, como a fonte escreve | texto |
| `link` | Endereço do documento na fonte | texto |
| `vigencia_inicio` | Início da vigência (a fonte traz o período numa frase) | data (dia) |
| `vigencia_fim` | Fim da vigência | data (dia) |
| `numero_aditivo` | Número do termo aditivo | texto |
| `ano_aditivo` | Ano do termo aditivo | texto |
| `tribunal` | Tribunal de contas de origem: `pe`, `sp`, `ce` ou `rs` | texto |
| `tabela` | Assunto da linha dentro do tribunal (contratos, aditivos, despesas) | texto |
| `cnpj` | CNPJ do contratado ou fornecedor, só os 14 dígitos com o dígito verificador certo. Linha de pessoa física, de CPF ou de CNPJ inválido não entra; nome, endereço e texto livre nunca são gravados | texto |
| `disponivel_em` | Dia do download. Nenhuma das fontes diz quando a linha ficou pública, então o dado só vale a partir do dia em que a coleta o viu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `tce_pe_licitacoes`

Licitações do TCE-PE por licitante vencedor (`LicitacoesDetalhes`; só a linha do vencedor pessoa jurídica). Só pessoa jurídica (CNPJ válido); nenhum nome, CPF, endereço ou texto livre. Uso interno, licença a confirmar.

- **Fonte:** TCE-PE, API Dados Abertos (`LicitacoesDetalhes`)
- **Licença:** TCE-PE: licença não localizada; risco assumido (ADR 0122)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Anual, fatiado por ano e modalidade (um pedido por fatia, com pausa); refazer o ano corrente a cada trimestre
- **Atraso de divulgação:** Sem data de publicação na fonte: a linha vale desde o download
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `codigo_licitacao`, `cnpj`
- **Três datas:** aconteceu_em = `data_homologacao`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/tce_pe_licitacoes/<ano>.parquet` (`scripts/carga_tces.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `codigo_licitacao` | Código do processo licitatório no TCE-PE | texto |
| `numero_processo` | Número do processo | texto |
| `ano_processo` | Ano do processo | texto |
| `numero_modalidade` | Número da licitação na modalidade | texto |
| `ano_modalidade` | Ano da licitação na modalidade | texto |
| `codigo_modalidade` | Código da modalidade, como a fonte codifica | texto |
| `modalidade` | Nome da modalidade, como a fonte escreve | texto |
| `codigo_ug` | Código da unidade gestora | texto |
| `unidade_gestora` | Nome da unidade gestora (órgão público) | texto |
| `codigo_municipio` | Código do município no TCE-PE | texto |
| `natureza` | Natureza do objeto, como a fonte escreve | texto |
| `fundamento_legal` | Código do fundamento legal, como a fonte codifica | texto |
| `situacao` | Situação da licitação, como a fonte escreve | texto |
| `estagio` | Estágio da licitação, como a fonte escreve | texto |
| `quantidade_licitantes` | Quantidade de licitantes | texto |
| `link` | Endereço do documento na fonte | texto |
| `data_edital` | Dia da emissão do edital | data (dia) |
| `data_homologacao` | Dia da publicação da homologação | data (dia) |
| `valor_estimado` | Valor estimado do orçamento, em reais | número com decimais, na unidade da fonte |
| `valor_adjudicado` | Total adjudicado ao vencedor (a linha é a do licitante vencedor), em reais | número com decimais, na unidade da fonte |
| `tribunal` | Tribunal de contas de origem: `pe`, `sp`, `ce` ou `rs` | texto |
| `tabela` | Assunto da linha dentro do tribunal (contratos, aditivos, despesas) | texto |
| `cnpj` | CNPJ do contratado ou fornecedor, só os 14 dígitos com o dígito verificador certo. Linha de pessoa física, de CPF ou de CNPJ inválido não entra; nome, endereço e texto livre nunca são gravados | texto |
| `disponivel_em` | Dia do download. Nenhuma das fontes diz quando a linha ficou pública, então o dado só vale a partir do dia em que a coleta o viu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `tce_sp_despesas`

Despesas dos municípios paulistas por fornecedor pessoa jurídica, um evento por linha. Só pessoa jurídica (CNPJ válido); nenhum nome, CPF, endereço ou texto livre. Uso interno, licença a confirmar.

- **Fonte:** TCE-SP, Portal da Transparência Municipal
- **Licença:** TCE-SP: licença não localizada; risco assumido (ADR 0122)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Mensal por município (645 x 12 pedidos por ano, com pausa)
- **Atraso de divulgação:** Sem data de publicação na fonte: a linha vale desde o download
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `municipio`, `mes`, `evento`, `numero_empenho`, `cnpj`, `data_emissao`, `valor`
- **Três datas:** aconteceu_em = `data_emissao`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/tce_sp_despesas/<ano>.parquet` (`scripts/carga_tces.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `municipio` | Município da consulta, como no endereço da fonte (sem acento, com hífen) | texto |
| `ano` | Ano da consulta | texto |
| `mes` | Mês por extenso, como a fonte escreve | texto |
| `evento` | Evento da despesa (empenhado, liquidado, pago): cada um é uma linha e eles não se somam | texto |
| `numero_empenho` | Número do empenho, como a fonte escreve | texto |
| `data_emissao` | Dia da emissão da despesa | data (dia) |
| `valor` | Valor do evento, em reais | número com decimais, na unidade da fonte |
| `tribunal` | Tribunal de contas de origem: `pe`, `sp`, `ce` ou `rs` | texto |
| `tabela` | Assunto da linha dentro do tribunal (contratos, aditivos, despesas) | texto |
| `cnpj` | CNPJ do contratado ou fornecedor, só os 14 dígitos com o dígito verificador certo. Linha de pessoa física, de CPF ou de CNPJ inválido não entra; nome, endereço e texto livre nunca são gravados | texto |
| `disponivel_em` | Dia do download. Nenhuma das fontes diz quando a linha ficou pública, então o dado só vale a partir do dia em que a coleta o viu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `tce_ce_contratos`

Contratados e contratos do SIM do TCE-CE, ligados pela chave município, número e data. Só pessoa jurídica (CNPJ válido); nenhum nome, CPF, endereço ou texto livre. Uso interno, licença a confirmar.

- **Fonte:** TCE-CE, SIM (arquivos postos à mão; sem coleta automática ainda)
- **Licença:** TCE-CE: licença não localizada; risco assumido (ADR 0122)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Sem rotina: carga manual de arquivos baixados
- **Atraso de divulgação:** Sem data de publicação na fonte: a linha vale desde o download
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `codigo_municipio`, `numero_contrato`, `data_contrato`, `cnpj`
- **Três datas:** aconteceu_em = `data_contrato`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/tce_ce_contratos/<ano>.parquet` (`scripts/carga_tces.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `codigo_municipio` | Código do município no SIM do TCE-CE | texto |
| `numero_contrato` | Número do contrato, como a fonte escreve | texto |
| `data_contrato` | Dia do contrato | data (dia) |
| `data_referencia` | Data de referência do documento do contratado | texto |
| `codigo_tipo_negociante` | Tipo do negociante, como a fonte codifica | texto |
| `tipo_contrato` | Tipo do contrato, como a fonte escreve | texto |
| `modalidade` | Modalidade, como a fonte escreve | texto |
| `numero_processo` | Número do processo administrativo | texto |
| `vigencia_inicio` | Início da vigência | data (dia) |
| `vigencia_fim` | Fim da vigência | data (dia) |
| `valor` | Valor total do contrato, em reais | número com decimais, na unidade da fonte |
| `id_pncp` | Id do contrato no PNCP, para casar com a carga do PNCP; vazio quando não há | texto |
| `com_contrato` | `True` quando o contratado achou o contrato pela chave (município, número, data) | texto |
| `tribunal` | Tribunal de contas de origem: `pe`, `sp`, `ce` ou `rs` | texto |
| `tabela` | Assunto da linha dentro do tribunal (contratos, aditivos, despesas) | texto |
| `cnpj` | CNPJ do contratado ou fornecedor, só os 14 dígitos com o dígito verificador certo. Linha de pessoa física, de CPF ou de CNPJ inválido não entra; nome, endereço e texto livre nunca são gravados | texto |
| `disponivel_em` | Dia do download. Nenhuma das fontes diz quando a linha ficou pública, então o dado só vale a partir do dia em que a coleta o viu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `tce_rs_contratos`

Contratos do LicitaCon do TCE-RS por contratado (só `contrato.csv`; `pessoas.csv` nunca é aberto). Só pessoa jurídica (CNPJ válido); nenhum nome, CPF, endereço ou texto livre. Uso interno, licença a confirmar.

- **Fonte:** TCE-RS, dados abertos (LicitaCon, um ZIP por órgão)
- **Licença:** LicitaCon do TCE-RS: licença a confirmar com a Ouvidoria (ADR 0085)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Mensal (índice do CKAN e um ZIP por órgão, com retomada)
- **Atraso de divulgação:** Sem data de publicação na fonte: a linha vale desde o download
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** sim
- **Chaves:** `codigo_orgao`, `numero_licitacao`, `ano_licitacao`, `numero_contrato`, `ano_contrato`, `cnpj`
- **Três datas:** aconteceu_em = `data_assinatura`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/tce_rs_contratos/<ano>.parquet` (`scripts/carga_tces.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `codigo_orgao` | Código do órgão no LicitaCon | texto |
| `numero_licitacao` | Número da licitação | texto |
| `ano_licitacao` | Ano da licitação | texto |
| `codigo_modalidade` | Código da modalidade da licitação | texto |
| `numero_contrato` | Número do contrato | texto |
| `ano_contrato` | Ano do contrato | texto |
| `tipo_instrumento` | Tipo do instrumento, como a fonte codifica | texto |
| `numero_processo` | Número do processo | texto |
| `ano_processo` | Ano do processo | texto |
| `link` | Endereço da licitação no LicitaCon Cidadão | texto |
| `vigencia_inicio` | Início da vigência | data (dia) |
| `vigencia_fim` | Fim da vigência | data (dia) |
| `data_assinatura` | Dia da assinatura | data (dia) |
| `valor` | Valor do contrato, em reais | número com decimais, na unidade da fonte |
| `tribunal` | Tribunal de contas de origem: `pe`, `sp`, `ce` ou `rs` | texto |
| `tabela` | Assunto da linha dentro do tribunal (contratos, aditivos, despesas) | texto |
| `cnpj` | CNPJ do contratado ou fornecedor, só os 14 dígitos com o dígito verificador certo. Linha de pessoa física, de CPF ou de CNPJ inválido não entra; nome, endereço e texto livre nunca são gravados | texto |
| `disponivel_em` | Dia do download. Nenhuma das fontes diz quando a linha ficou pública, então o dado só vale a partir do dia em que a coleta o viu | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `anm_cfem_arrecadacao`

CFEM (royalty da mineração) recolhida por titular do processo, substância e município. Só pessoa jurídica com CNPJ completo: pessoa física, CPF e documento mascarado são descartados na carga. Um arquivo por faixa de anos da ANM. O CNPJ liga a tabela ao quadro de sócios pela raiz.

- **Fonte:** ANM, Dados Abertos, arrecadação da CFEM (`base/anm.py`)
- **Licença:** CC BY (dados abertos da ANM, Cadastro Mineiro, no dados.gov.br; citar a ANM)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a coleta olha a faixa de anos do ano corrente e a anterior)
- **Atraso de divulgação:** A linha vale desde a data em que a ANM a criou (`criado_em`). A licença da ANM não é declarada no portal: a confirmar, só uso interno; nada foi perguntado à fonte
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `ano`, `mes`, `processo`, `ano_processo`, `cnpj`, `substancia`, `municipio`, `criado_em`
- **Três datas:** aconteceu_em = `criado_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2002-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/anm_cfem_arrecadacao/<faixa de anos>.parquet` (servidor de casa, `scripts/carga_anm.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `ano` | Ano de competência do recolhimento | texto |
| `mes` | Mês de competência do recolhimento (1 a 12) | texto |
| `processo` | Número do processo minerário na ANM | texto |
| `ano_processo` | Ano do processo minerário | texto |
| `cnpj` | CNPJ do titular, só os 14 dígitos. Pessoa física, CPF e documento mascarado são descartados na carga | texto |
| `cnpj_raiz` | Os 8 primeiros dígitos do CNPJ: a ponte com o quadro de sócios da Receita | texto |
| `substancia` | Substância mineral, como a ANM escreve | texto |
| `uf` | Sigla do estado | texto |
| `codigo_municipio` | Código IBGE do município | texto |
| `municipio` | Nome do município, como a ANM escreve | texto |
| `quantidade` | Quantidade comercializada, na unidade da coluna `unidade` | número com decimais, na unidade da fonte |
| `unidade` | Unidade da quantidade (t, l, m3, g, kg, ct...), como a ANM escreve | texto |
| `valor_recolhido` | CFEM recolhida, em reais (R$) | número com decimais, na unidade da fonte |
| `criado_em` | Data e hora em que a ANM criou a linha | data (dia) |
| `disponivel_em` | Dia em que a linha passou a existir na ANM (`criado_em`); sem data na linha, o dia da coleta. `ano` e `mes` nunca servem de disponibilidade | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `anm_sigbm_barragens`

Barragens de mineração do SIGBM da ANM, com a categoria de risco (CRI) e o dano potencial (DPA) como o empreendedor declarou. O CNPJ é o do empreendedor, que não é necessariamente quem opera a mina; sem CNPJ completo, o nome do empreendedor também fica de fora.

- **Fonte:** ANM, Dados Abertos, SIGBM (`base/anm.py`)
- **Licença:** CC BY (dados abertos da ANM, Cadastro Mineiro, no dados.gov.br; citar a ANM)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (a ANM sobrescreve o arquivo)
- **Atraso de divulgação:** O SIGBM não guarda histórico: a linha vale desde o dia em que a coleta a viu. A licença da ANM não é declarada no portal: a confirmar, só uso interno; nada foi perguntado à fonte
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `id`
- **Três datas:** aconteceu_em = `classificado_em`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/anm_sigbm_barragens/barragens.parquet` (servidor de casa, `scripts/carga_anm.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id` | Identificador da barragem no SIGBM | texto |
| `nome` | Nome da barragem | texto |
| `empreendedor` | Nome do empreendedor; vazio quando o documento não é um CNPJ completo (pode ser pessoa física) | texto |
| `cnpj` | CNPJ do empreendedor, só os 14 dígitos. Não é necessariamente quem opera a mina | texto |
| `cnpj_raiz` | Os 8 primeiros dígitos do CNPJ do empreendedor | texto |
| `nome_mina` | Nome da mina | texto |
| `uf` | Sigla do estado | texto |
| `municipio` | Município, como a ANM escreve | texto |
| `latitude` | Latitude em graus decimais (a ANM entrega em graus, minutos e segundos) | número com decimais, na unidade da fonte |
| `longitude` | Longitude em graus decimais (a ANM entrega em graus, minutos e segundos) | número com decimais, na unidade da fonte |
| `categoria_risco` | Categoria de risco (CRI) declarada pelo empreendedor: Alta, Média ou Baixa | texto |
| `dano_potencial` | Dano potencial associado (DPA) declarado pelo empreendedor: Alto, Médio ou Baixo | texto |
| `classificado_em` | Data da finalização da declaração (DCE) em que o CRI e o DPA foram informados; vazio quando a ANM diz que não se aplica ou que não foi entregue | data (dia) |
| `nivel_emergencia` | Nível de emergência declarado | texto |
| `situacao_operacional` | Situação operacional (em operação, em descaracterização...) | texto |
| `motivo_envio` | Motivo do envio da declaração | texto |
| `altura_atual_m` | Altura máxima atual da barragem, em metros | número com decimais, na unidade da fonte |
| `volume_atual_m3` | Volume atual do reservatório, em metros cúbicos | número com decimais, na unidade da fonte |
| `unidade_gestora` | Unidade gestora da ANM responsável | texto |
| `disponivel_em` | Dia em que a coleta viu essa versão da linha pela primeira vez: a ANM sobrescreve o arquivo, sem histórico, e `classificado_em` nunca serve de disponibilidade | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `anm_amb_producao_bruta`

Produção mineral bruta do Anuário Mineral (minério ROM, venda, consumo e transferência) por ano, UF e substância. Série setorial, sem CNPJ. Unidades por linha, sem converter; chave repetida não é somada.

- **Fonte:** ANM, Dados Abertos, Anuário Mineral Brasileiro (`base/anm.py`)
- **Licença:** CC BY (dados abertos da ANM, Cadastro Mineiro, no dados.gov.br; citar a ANM)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (o Anuário é anual e a ANM sobrescreve o arquivo)
- **Atraso de divulgação:** O Anuário não guarda histórico: a linha vale desde o dia em que a coleta a viu. A licença da ANM não é declarada no portal: a confirmar, só uso interno; nada foi perguntado à fonte
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `ano`, `uf`, `substancia`, `contido_indicacao`
- **Três datas:** publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/anm_amb_producao_bruta/atual.parquet` (servidor de casa, `scripts/carga_anm.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `ano` | Ano-base do Anuário Mineral | texto |
| `uf` | Sigla do estado | texto |
| `classe` | Classe da substância (metálicos, não metálicos...) | texto |
| `substancia` | Substância mineral, como a ANM escreve | texto |
| `producao_rom_t` | Produção de minério ROM, em toneladas | número com decimais, na unidade da fonte |
| `contido` | Quantidade contida, na unidade da linha (`contido_unidade`) | número com decimais, na unidade da fonte |
| `contido_unidade` | Unidade do contido, por linha, sem converter | texto |
| `contido_indicacao` | Indicação do contido (de que mineral ou fase), como a ANM escreve | texto |
| `venda_t` | Quantidade vendida, em toneladas | número com decimais, na unidade da fonte |
| `venda_valor` | Valor da venda, em reais (R$) | número com decimais, na unidade da fonte |
| `consumo_t` | Quantidade para transformação, consumo ou utilização, em toneladas | número com decimais, na unidade da fonte |
| `consumo_valor` | Valor da transformação, consumo ou utilização nesta mina, em reais (R$) | número com decimais, na unidade da fonte |
| `transferencia_t` | Quantidade transferida para transformação, utilização ou consumo, em toneladas | número com decimais, na unidade da fonte |
| `transferencia_valor` | Valor da transferência, em reais (R$) | número com decimais, na unidade da fonte |
| `disponivel_em` | Dia em que a coleta viu essa versão da linha pela primeira vez: o Anuário é sobrescrito pela ANM, e `ano` (o ano-base) nunca serve de disponibilidade | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `anm_amb_producao_beneficiada`

Produção mineral beneficiada do Anuário Mineral por ano, UF e substância. Série setorial, sem CNPJ. Unidades por linha, sem converter.

- **Fonte:** ANM, Dados Abertos, Anuário Mineral Brasileiro (`base/anm.py`)
- **Licença:** CC BY (dados abertos da ANM, Cadastro Mineiro, no dados.gov.br; citar a ANM)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (o Anuário é anual e a ANM sobrescreve o arquivo)
- **Atraso de divulgação:** O Anuário não guarda histórico: a linha vale desde o dia em que a coleta a viu. A licença da ANM não é declarada no portal: a confirmar, só uso interno; nada foi perguntado à fonte
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `ano`, `uf`, `substancia`, `contido_indicacao`
- **Três datas:** publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/anm_amb_producao_beneficiada/atual.parquet` (servidor de casa, `scripts/carga_anm.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `ano` | Ano-base do Anuário Mineral | texto |
| `uf` | Sigla do estado | texto |
| `classe` | Classe da substância (metálicos, não metálicos...) | texto |
| `substancia` | Substância mineral, como a ANM escreve | texto |
| `producao` | Quantidade produzida, na unidade `producao_unidade` | número com decimais, na unidade da fonte |
| `producao_unidade` | Unidade da produção, por linha, sem converter | texto |
| `contido` | Quantidade contida, na unidade da linha (`contido_unidade`) | número com decimais, na unidade da fonte |
| `contido_unidade` | Unidade do contido, por linha, sem converter | texto |
| `contido_indicacao` | Indicação do contido, como a ANM escreve | texto |
| `venda` | Quantidade vendida, na unidade `venda_unidade` | número com decimais, na unidade da fonte |
| `venda_unidade` | Unidade da venda, por linha, sem converter | texto |
| `venda_valor` | Valor da venda, em reais (R$) | número com decimais, na unidade da fonte |
| `consumo` | Quantidade consumida ou utilizada na usina, na unidade `consumo_unidade` | número com decimais, na unidade da fonte |
| `consumo_unidade` | Unidade do consumo, por linha, sem converter | texto |
| `consumo_valor` | Valor do consumo ou utilização na usina, em reais (R$) | número com decimais, na unidade da fonte |
| `transferencia` | Quantidade transferida, na unidade `transferencia_unidade` | número com decimais, na unidade da fonte |
| `transferencia_unidade` | Unidade da transferência, por linha, sem converter | texto |
| `transferencia_valor` | Valor da transferência, em reais (R$) | número com decimais, na unidade da fonte |
| `disponivel_em` | Dia em que a coleta viu essa versão da linha pela primeira vez: o Anuário é sobrescrito pela ANM, e `ano` (o ano-base) nunca serve de disponibilidade | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `anm_amb_agua_mineral`

Água mineral do Anuário Mineral: litros e valor por tipo de embalagem, por ano, UF e substância. Série setorial, sem CNPJ.

- **Fonte:** ANM, Dados Abertos, Anuário Mineral Brasileiro (`base/anm.py`)
- **Licença:** CC BY (dados abertos da ANM, Cadastro Mineiro, no dados.gov.br; citar a ANM)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Mensal (o Anuário é anual e a ANM sobrescreve o arquivo)
- **Atraso de divulgação:** O Anuário não guarda histórico: a linha vale desde o dia em que a coleta a viu. A licença da ANM não é declarada no portal: a confirmar, só uso interno; nada foi perguntado à fonte
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `ano`, `uf`, `substancia`
- **Três datas:** publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-11-04 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/anm_amb_agua_mineral/atual.parquet` (servidor de casa, `scripts/carga_anm.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `ano` | Ano-base do Anuário Mineral | texto |
| `uf` | Sigla do estado | texto |
| `classe` | Classe da substância (metálicos, não metálicos...) | texto |
| `substancia` | Substância mineral, como a ANM escreve | texto |
| `litros_garrafao` | Litros vendidos em garrafão | número com decimais, na unidade da fonte |
| `litros_garrafa_plastica` | Litros vendidos em garrafa plástica | número com decimais, na unidade da fonte |
| `litros_garrafa_vidro` | Litros vendidos em garrafa de vidro | número com decimais, na unidade da fonte |
| `litros_copo` | Litros vendidos em copo | número com decimais, na unidade da fonte |
| `litros_outras` | Litros vendidos em outras embalagens | número com decimais, na unidade da fonte |
| `litros_industrializados` | Litros vendidos em composição de produtos industrializados | número com decimais, na unidade da fonte |
| `valor_garrafao` | Valor das vendas em garrafão, em reais (R$) | número com decimais, na unidade da fonte |
| `valor_garrafa_plastica` | Valor das vendas em garrafa plástica, em reais (R$) | número com decimais, na unidade da fonte |
| `valor_garrafa_vidro` | Valor das vendas em garrafa de vidro, em reais (R$) | número com decimais, na unidade da fonte |
| `valor_copo` | Valor das vendas em copo, em reais (R$) | número com decimais, na unidade da fonte |
| `valor_outras` | Valor das vendas em outras embalagens, em reais (R$) | número com decimais, na unidade da fonte |
| `valor_industrializados` | Valor das vendas em composição de produtos industrializados, em reais (R$) | número com decimais, na unidade da fonte |
| `unidade` | Unidade de medida declarada pela ANM | texto |
| `disponivel_em` | Dia em que a coleta viu essa versão da linha pela primeira vez: o Anuário é sobrescrito pela ANM, e `ano` (o ano-base) nunca serve de disponibilidade | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `debentures_assembleias`

Assembleias de debenturistas (`AGDEB`: ata, edital, proposta, instrução de voto), avisos aos debenturistas e notificações do agente fiduciário que as companhias abertas entregam à CVM no IPE desde 2003, uma linha por versão entregue. O tema de cada documento sai só do assunto preenchido pela companhia, sem abrir o PDF (modelo 18, PR 1): cerca de metade dos assuntos é genérica (`generico`) e só o PDF dirá o tema. `estresse` marca o aperto de crédito (vencimento antecipado, covenant, repactuação, inadimplemento ou waiver que não é para reorganizar a empresa nem prêmio de resgate; no aviso, só vencimento antecipado e inadimplemento). Cobre só quem entrega ao IPE: as emissões ICVM 476 de companhias fechadas ficam de fora (`relatorio-modelo-18-agente-fiduciario.md`). Conferência à mão de 50 PDFs (17/10/2026): `estresse` certo em 23 de 26; 3 de 10 genéricos tinham estresse no PDF

- **Fonte:** CVM: arquivos anuais do IPE (`cvm-hist-ipe`), lidos por `base/debentures.py`
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária no servidor de casa (`scripts/montar_debentures_assembleias.py`), depois do arquivista baixar o IPE do ano
- **Atraso de divulgação:** O documento vale a partir de `publico_em` (entrega da versão à CVM); `referencia` é a data informada pela companhia e, no edital, é o dia da assembleia, que pode vir depois
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `link`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `publico_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2003-01-01 (`publico_em` por dia)
- **Versão do contrato:** 2.0.0
- **Onde fica:** Parquet em `<acervo>/base/debentures_assembleias/debentures_assembleias.parquet` (servidor de casa, `scripts/montar_debentures_assembleias.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do arquivo anual do IPE de onde veio (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); o manifesto lista os arquivos anuais lidos. `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `codigo_cvm` | Código da companhia na CVM | texto |
| `documento` | assembleia, aviso ou notificacao_do_agente | texto |
| `especie` | Espécie do documento da assembleia (Ata, Edital de Convocação, Proposta da Administração...); vazia no aviso e na notificação | texto |
| `assunto` | Assunto como a companhia preencheu no IPE | texto |
| `emissao` | Número da emissão citada no assunto (vazio se não há nenhuma ou se há mais de uma) | número inteiro |
| `tema_vencimento_antecipado` | O assunto fala de vencimento antecipado (inclui o pedido para não declarar) | verdadeiro ou falso |
| `tema_waiver` | O assunto fala de waiver, renúncia, perdão, anuência ou consentimento prévio | verdadeiro ou falso |
| `tema_covenant` | O assunto fala de covenant, índices ou limites financeiros, alavancagem, dívida líquida ou EBITDA | verdadeiro ou falso |
| `tema_repactuacao` | O assunto fala de repactuação, prorrogação, postergação, carência, suspensão de pagamento ou mudança de taxa, prazo ou cronograma | verdadeiro ou falso |
| `tema_inadimplemento` | O assunto fala de inadimplemento, não pagamento, recuperação judicial ou extrajudicial ou falência | verdadeiro ou falso |
| `tema_garantia` | O assunto fala de garantia, alienação ou cessão fiduciária, fiança, aval ou conta vinculada | verdadeiro ou falso |
| `tema_resgate` | O assunto fala de resgate antecipado, amortização extraordinária ou aquisição facultativa | verdadeiro ou falso |
| `tema_reorganizacao` | O assunto fala de incorporação, cisão, fusão, reorganização, troca de controle ou oferta de ações | verdadeiro ou falso |
| `tema_pagamento` | O assunto avisa pagamento de juros, remuneração, amortização, prêmio ou principal | verdadeiro ou falso |
| `estresse` | O tema é de aperto de crédito (regra na descrição) | verdadeiro ou falso |
| `generico` | O assunto não casa com nenhum tema: só o PDF dirá | verdadeiro ou falso |
| `referencia` | Data informada pela companhia (no edital, o dia da assembleia) | data (dia) |
| `publico_em` | Entrega da versão do documento à CVM: quando ficou público para a base | data (dia) |
| `protocolo` | Protocolo de entrega na CVM (de 2003 a 2014, o link, que a CVM não dá protocolo) | texto |
| `versao` | Versão do documento (reapresentação); vazia de 2003 a 2015, quando o IPE não a traz | número inteiro |
| `link` | Link do arquivo no sistema da CVM: identifica a linha (uma entrega pode ter vários arquivos) | texto |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `ratings`

Ratings de crédito das companhias abertas lidos dos documentos que elas entregam à CVM no IPE desde 2003: o relatório da agência (tipo próprio do IPE) e os comunicados, fatos relevantes e editais que falam do rating. Uma linha por documento baixado e lido, com a situação da extração (`extraido`; `nao_extraido`: PDF escaneado ou sem nota; `nao_e_pdf`: Word, ZIP ou PDF quebrado). O mesmo evento (companhia, agência, escala, nota e data da ação) contado pelo relatório e pelo comunicado vira uma linha só, com a primeira entrega. v1: o rating principal de cada documento; notas por emissão, uma a uma, ficam para depois. Conferência à mão: 35 de 36 certas (16/10/2026)

- **Fonte:** CVM: documentos do IPE no sistema de documentos (RAD), fonte `cvm-ipe-rating`, e a lista dos arquivos anuais do IPE (`base/ratings.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária no servidor de casa (`scripts/montar_ratings.py`), depois das rodadas do coletor, que baixa os documentos de hora em hora, do mais novo ao mais velho
- **Atraso de divulgação:** O rating vale a partir de `publico_em` (entrega da versão do documento à CVM), nunca da data do relatório da agência; `data_acao` depois da entrega fica vazia
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `protocolo`, `versao`
- **Três datas:** aconteceu_em = `data_acao`; publico_em = `publico_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2003-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ratings/ratings.parquet` (servidor de casa, `scripts/montar_ratings.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do documento no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); o manifesto lista os arquivos anuais do IPE e todos os documentos lidos. `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `codigo_cvm` | Código da companhia na CVM | texto |
| `agencia` | fitch, sp, moodys, austin, liberum, sr_rating, lf_rating ou am_best (vazia se não extraído) | texto |
| `escala` | nacional ou global | texto |
| `nota` | Nota sem sufixos (AA, RD, Aa1): compara documentos da mesma agência | texto |
| `nivel` | Posição da nota na escala (1 = AAA ou Aaa): compara agências | número inteiro |
| `nota_original` | A nota como está no texto (AA(bra), brAAA, Aa1.br) | texto |
| `perspectiva` | estavel, positiva, negativa, em_desenvolvimento, em_observacao_positiva ou em_observacao_negativa | texto |
| `acao` | afirmacao, elevacao, rebaixamento, atribuicao, retirada... | texto |
| `data_acao` | Data da ação da agência lida do texto (vazia se não está ou se vem depois da entrega) | data (dia) |
| `outras_notas` | As outras notas citadas no documento, separadas por `; ` | texto |
| `publico_em` | Entrega da versão do documento à CVM: quando o rating ficou público para a base | data (dia) |
| `protocolo` | Protocolo de entrega na CVM (de 2003 a 2014, o link, que a CVM não dá protocolo) | texto |
| `versao` | Versão do documento (reapresentação) | número inteiro |
| `link` | Link do documento no sistema da CVM | texto |
| `evidencia` | Por que o documento entrou: relatorio_de_agencia (tipo do IPE) ou assunto | texto |
| `situacao_extracao` | extraido, nao_extraido ou nao_e_pdf | texto |
| `documentos` | Protocolos de todos os documentos do mesmo evento, pela data de entrega, separados por `; ` (pode citar entregas posteriores a `publico_em`) | texto |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `auditores`

Mandatos de auditor independente de cada companhia pelo FCA desde 2010 (firma, início e fim). A firma é identificada pela rede, lida do nome (KPMG, EY, PwC, Deloitte...), porque CNPJ e código da CVM vêm errados em parte das linhas. O sócio responsável (nome e CPF) nunca entra (LGPD).

- **Fonte:** CVM: dados abertos do FCA, tabela de auditores (`base/auditores.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual (o FCA é entregue até 31/05) e a cada alteração; a carga relê todos os anos
- **Atraso de divulgação:** Até meses: o acervo só tem a última versão de cada FCA, então `conhecido_em` pode ser mais tarde que a primeira notícia, nunca mais cedo
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`, `auditor_id`, `inicio`
- **Três datas:** aconteceu_em = `inicio`; publico_em = `conhecido_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 2.0.0
- **Onde fica:** Parquet em `<acervo>/base/auditores/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `referencia` | Data de referência do FCA | data (dia) |
| `versao` | Versão do FCA | número inteiro |
| `id_documento` | Número do documento na CVM | texto |
| `conhecido_em` | Data em que a CVM recebeu essa versão do FCA; mandada com a empresa fora do registro (pedido de registro), vale a partir do registro seguinte | data (dia) |
| `auditor_id` | Identificador da firma: `rede:<nome>` nas redes; senão código da CVM, raiz do CNPJ ou nome | texto |
| `auditor` | Nome da firma, como a empresa escreveu | texto |
| `auditor_cnpj` | CNPJ da firma informado (14 dígitos; pode estar errado) | texto |
| `codigo_cvm_auditor` | Código da firma na CVM informado | texto |
| `origem` | Nacional ou estrangeiro, como a CVM publica | texto |
| `inicio` | Início do mandato | data (dia) |
| `fim` | Fim do mandato (vazio: em curso) | data (dia) |
| `ano_do_arquivo` | Ano do arquivo da CVM de onde a linha veio | ano |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `pareceres_dfp`

Parecer do auditor de cada DFP desde 2010, lido do CSV de pareceres da CVM (relatório do auditor independente): tipo de opinião (campo da CVM), ênfase e continuidade operacional (pelos títulos do texto livre, sem palavra solta). Só a classificação é guardada, não o texto; a declaração dos diretores e o parecer do conselho fiscal ficam de fora. A firma não está neste CSV: liga-se a `auditores` por CNPJ e data. Documento sem relatório do auditor não tem linha

- **Fonte:** CVM: dados abertos do DFP, CSV de pareceres (`base/pareceres.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal: a carga relê todos os anos (a CVM reescreve os antigos com reapresentações)
- **Atraso de divulgação:** A entrega à CVM (`DT_RECEB` do arquivo principal); documento enviado com a empresa fora do registro vale a partir do registro seguinte
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/pareceres_dfp/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `referencia` | Data a que o documento se refere | data (dia) |
| `versao` | Versão do DFP | número inteiro |
| `id_documento` | Número do documento na CVM | texto |
| `disponivel_em` | Data em que o documento ficou público (a entrega à CVM, ou o registro da empresa) | data (dia) |
| `opiniao` | `sem_ressalva`, `com_ressalva`, `adversa`, `abstencao` (a CVM escreve "Negativa de Opinião") ou `nao_classificado` (campo vazio, como em parte de 2010) | texto |
| `enfase` | Parágrafo de ênfase no relatório: `sim`, `nao` ou `nao_classificado` (relatório curto demais ou texto ambíguo: nunca no chute) | texto |
| `continuidade_operacional` | Incerteza relevante sobre a continuidade operacional apontada pelo auditor: `sim`, `nao` ou `nao_classificado` (relatório curto demais ou texto ambíguo: nunca no chute) | texto |
| `caracteres_do_relatorio` | Tamanho do texto do relatório lido (quanto menor, menos confiável a classificação) | número inteiro |
| `ano_do_arquivo` | Ano do arquivo da CVM de onde a linha veio | ano |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `pareceres_itr`

Parecer do auditor de cada ITR desde 2011, lido do CSV de pareceres da CVM (relatório da revisão especial): tipo de opinião (campo da CVM), ênfase e continuidade operacional (pelos títulos do texto livre, sem palavra solta). Só a classificação é guardada, não o texto; a declaração dos diretores e o parecer do conselho fiscal ficam de fora. A firma não está neste CSV: liga-se a `auditores` por CNPJ e data. Documento sem relatório do auditor não tem linha

- **Fonte:** CVM: dados abertos do ITR, CSV de pareceres (`base/pareceres.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal: a carga relê todos os anos (a CVM reescreve os antigos com reapresentações)
- **Atraso de divulgação:** A entrega à CVM (`DT_RECEB` do arquivo principal); documento enviado com a empresa fora do registro vale a partir do registro seguinte
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2011-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/pareceres_itr/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `referencia` | Data a que o documento se refere | data (dia) |
| `versao` | Versão do ITR | número inteiro |
| `id_documento` | Número do documento na CVM | texto |
| `disponivel_em` | Data em que o documento ficou público (a entrega à CVM, ou o registro da empresa) | data (dia) |
| `opiniao` | `sem_ressalva`, `com_ressalva`, `adversa`, `abstencao` (a CVM escreve "Negativa de Opinião") ou `nao_classificado` (campo vazio, como em parte de 2010) | texto |
| `enfase` | Parágrafo de ênfase no relatório: `sim`, `nao` ou `nao_classificado` (relatório curto demais ou texto ambíguo: nunca no chute) | texto |
| `continuidade_operacional` | Incerteza relevante sobre a continuidade operacional apontada pelo auditor: `sim`, `nao` ou `nao_classificado` (relatório curto demais ou texto ambíguo: nunca no chute) | texto |
| `caracteres_do_relatorio` | Tamanho do texto do relatório lido (quanto menor, menos confiável a classificação) | número inteiro |
| `ano_do_arquivo` | Ano do arquivo da CVM de onde a linha veio | ano |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `securitizacao_certificados`

Um certificado de recebíveis (CRI, CRA ou outro título de securitização, OTS) por mês, lido do informe mensal da CVM (quadro `geral`): a securitizadora, o código do certificado, a emissão, o tipo de lastro e a data em que o informe foi entregue. Só o que o informe traz de identificação: garantias, contingências e outros textos livres ficam de fora. A chave é (`competencia`, `cnpj_securitizadora`, `codigo_certificado`)

- **Fonte:** CVM: dados abertos do informe mensal de CRI, CRA e OTS (`base/securitizacao.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Semanal: a carga relê os arquivos anuais (a CVM reescreve os meses com reapresentações)
- **Atraso de divulgação:** A entrega do informe à CVM (`Data_Entrega`); sem ela, a competência mais 120 dias, e nunca antes de o mês informado acabar. A mediana da entrega é de 58 dias no CRI e no CRA e de 29 no OTS, mas há entrega com anos de atraso: o prazo fixo olharia o futuro
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `cnpj_securitizadora`, `codigo_certificado`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2019-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/securitizacao_certificados/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Primeiro dia do mês a que o informe se refere | data (dia) |
| `cnpj_securitizadora` | CNPJ da securitizadora (emissora), no formato 00.000.000/0000-00 | texto |
| `codigo_certificado` | Código de identificação do certificado na CVM | texto |
| `produto` | `CRI`, `CRA` ou `OTS` (outros títulos de securitização) | texto |
| `versao` | Versão do informe; fica a maior de cada certificado e mês | número inteiro |
| `data_entrega` | Dia em que o informe foi entregue à CVM | data (dia) |
| `disponivel_em` | Dia em que o informe ficou público: a entrega, ou o piso quando ela falta | data (dia) |
| `nome_securitizadora` | Nome da securitizadora como o informe traz | texto |
| `numero_emissao` | Número da emissão | número inteiro |
| `nome_emissao` | Nome da emissão (séries) como o informe traz | texto |
| `data_emissao` | Dia da emissão | data (dia) |
| `quantidade_series` | Quantidade de séries da emissão | número inteiro |
| `tipo_lastro` | Tipo de lastro como a CVM classifica | texto |
| `ano_do_arquivo` | Ano do arquivo da CVM de onde a linha veio | ano |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `securitizacao_cedente_devedor`

Cedente e devedor de cada certificado (CRI, CRA e OTS) por mês, do quadro `cedente_devedor` do informe mensal da CVM. **Cedente e devedor só entram quando são pessoa jurídica com CNPJ válido**: a linha com CPF, com documento que não fecha ou em branco fica de fora inteira (nunca nome nem CPF de pessoa física). A CVM não dá o nome: só o CNPJ; o nome vem do cadastro. Onde o informe não preenche, cedente e devedor continuam não observáveis. Sem juízo de qualidade sobre o cedente

- **Fonte:** CVM: dados abertos do informe mensal de CRI, CRA e OTS (`base/securitizacao.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Semanal: a carga relê os arquivos anuais (a CVM reescreve os meses com reapresentações)
- **Atraso de divulgação:** A entrega do informe à CVM (`Data_Entrega`); sem ela, a competência mais 120 dias, e nunca antes de o mês informado acabar
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `cnpj_securitizadora`, `codigo_certificado`, `papel`, `cnpj`, `versao`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2019-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/securitizacao_cedente_devedor/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Primeiro dia do mês a que o informe se refere | data (dia) |
| `cnpj_securitizadora` | CNPJ da securitizadora (emissora), no formato 00.000.000/0000-00 | texto |
| `codigo_certificado` | Código de identificação do certificado na CVM | texto |
| `produto` | `CRI`, `CRA` ou `OTS` (outros títulos de securitização) | texto |
| `versao` | Versão do informe; fica a maior de cada certificado e mês | número inteiro |
| `data_entrega` | Dia em que o informe foi entregue à CVM | data (dia) |
| `disponivel_em` | Dia em que o informe ficou público: a entrega, ou o piso quando ela falta | data (dia) |
| `papel` | `cedente` ou `devedor` | texto |
| `cnpj` | CNPJ do cedente ou do devedor, no formato 00.000.000/0000-00 | texto |
| `percentual` | Percentual informado pela CVM (nos informes lidos, de 0 a 1; a CVM não define a base) | número com decimais, na unidade da fonte |
| `ano_do_arquivo` | Ano do arquivo da CVM de onde a linha veio | ano |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `notas_dfp`

Texto das notas explicativas (e do resto do PDF) de cada versão de DFP, uma linha por página com texto, lido do PDF do pacote do ENET da CVM (linha 135 da fila). Serve para ler a dívida, as contingências e as partes relacionadas por documento (`src/divida/nota_dfp.py`). Página só de imagem não tem linha (nada é inventado); cada versão tem as próprias linhas e vale a partir da própria entrega. O texto traz nomes de administradores e do auditor: a tabela e o original ficam em área restrita

- **Fonte:** CVM: ENET, PDF do pacote da DFP (`base/enet_notas.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Sob demanda: a carga baixa um pacote por vez, de madrugada, e a montagem relê o acervo
- **Atraso de divulgação:** A entrega à CVM (`DT_RECEB` do índice do DFP); documento enviado com a empresa fora do registro vale a partir do registro seguinte
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** sim
- **Chaves:** `cnpj`, `referencia`, `versao`, `pagina`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/notas_dfp/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `referencia` | Data a que a DFP se refere (fim do exercício) | data (dia) |
| `versao` | Versão da DFP (cada reapresentação é um documento) | número inteiro |
| `pagina` | Página do PDF, a partir de 1 | número inteiro |
| `texto` | Texto da página como o PDF o entrega, sem conta nem correção | texto |
| `disponivel_em` | Data em que a versão ficou pública (a entrega à CVM, ou o registro da empresa) | data (dia) |
| `link` | Endereço do pacote no ENET de onde o texto saiu | texto |
| `ano_do_arquivo` | Ano do arquivo da CVM de onde a linha veio | ano |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `processos_nas_notas`

Processos judiciais que a própria companhia cita nas notas explicativas da DFP: uma linha por número de processo e página de cada versão, achado no texto de `notas_dfp` e conferido pelo dígito verificador (número com o dígito errado fica de fora). Sem a Justiça do Trabalho, como no resto da base de processos (Resolução CNJ 121/2010). Sem o texto da página: ele fica em `notas_dfp`, em área restrita

- **Fonte:** CVM: ENET, PDF do pacote da DFP, pela tabela `notas_dfp` (`base/processos.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada montagem de `notas_dfp`: relê as notas quando elas mudam
- **Atraso de divulgação:** O da DFP: cada versão vale a partir da própria entrega à CVM
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`, `pagina`, `numero_processo`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/processos_nas_notas/dfp.parquet` (servidor de casa, `scripts/carga_processos.py`)
- **Linhagem:** Cada linha leva o `origem_sha256` e o `origem_coletada_em` da página de `notas_dfp` de onde saiu; o manifesto guarda os arquivos de `notas_dfp` lidos. Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `numero_processo` | Número do processo no formato do CNJ (NNNNNNN-DD.AAAA.J.TR.OOOO), com o dígito conferido | texto |
| `ano_do_processo` | Ano de ajuizamento, como o número diz | ano |
| `justica` | Ramo da Justiça, pelo número (Estadual, Federal, Eleitoral...) | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `referencia` | Data a que a DFP se refere (fim do exercício) | data (dia) |
| `versao` | Versão da DFP (cada reapresentação é um documento) | número inteiro |
| `pagina` | Página do PDF em que o número aparece, a partir de 1 | número inteiro |
| `link` | Endereço do pacote no ENET de onde o texto saiu | texto |
| `disponivel_em` | Data em que a versão da DFP ficou pública: desde quando se sabe que a companhia cita o processo | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `fca_geral`

Cadastro de cada companhia como era em cada FCA desde 2010: categoria do registro (A ou B), setor de atividade, espécie do controle acionário e mês de fim do exercício, como a companhia informou naquele formulário. É o cadastro "como era na data" do modelo 8 (nota i do critério de pronto): o `cad_cia_aberta.csv` só tem o de hoje **Sem pessoa pela raiz:** toda raiz de CNPJ desta tabela existe na `cnpj_empresas_pj`, que só tem pessoa jurídica; CNPJ que não tem 14 dígitos conta como fora. A prova cobre quem a linha descreve, não o texto livre que ela carrega (o assunto de um evento, por exemplo). A conferência é `scripts/conferir_sem_pessoa.py`, rodada antes de cada concessão do piloto

- **Fonte:** CVM: dados abertos do FCA, tabela de dados gerais (`base/fca_geral.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual (o FCA é entregue até 31/05) e a cada alteração; a carga relê todos os anos
- **Atraso de divulgação:** Até meses: o acervo só tem a última versão de cada FCA, então `conhecido_em` pode ser mais tarde que a primeira notícia, nunca mais cedo
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/fca_geral/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `referencia` | Data de referência do FCA | data (dia) |
| `versao` | Versão do FCA | número inteiro |
| `id_documento` | Número do documento na CVM | texto |
| `conhecido_em` | Data em que a CVM recebeu essa versão do FCA; mandada com a empresa fora do registro (pedido de registro), vale a partir do registro seguinte | data (dia) |
| `categoria` | Categoria do registro na CVM: A (pode emitir ações) ou B | texto |
| `setor` | Setor de atividade, como a companhia informou | texto |
| `controle_acionario` | Espécie do controle (Privado, Privado Holding, Estatal, Estrangeiro...) | texto |
| `mes_fim_do_exercicio` | Mês de fim do exercício social | mês (1 a 12) |
| `ano_do_arquivo` | Ano do arquivo da CVM de onde a linha veio | ano |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `trocas_de_auditor`

Rótulo "trocou de auditor": cada troca de firma, montada de todos os anos de `auditores` na ordem de entrega dos FCAs (uma troca nunca é reescrita depois). A troca com auditor que pode ser pessoa física (`trata_como_pessoa`, ADR 0075) não sai da porta. **Limite medido em 12/11/2026:** o arquivo começa em maio de 2010 (`conhecido_em`); `efetiva_em` vai de 2001 a 2027. As trocas se concentram em 2012, 2017 e 2022, o que é compatível com o rodízio obrigatório de cinco anos; isso é leitura, não campo da fonte.

- **Fonte:** CVM: dados abertos do FCA, pela tabela `auditores`
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Refeita a cada montagem de `auditores`
- **Atraso de divulgação:** A troca vale a partir de `conhecido_em` (entrega do FCA que a mostrou)
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** sim em casa (linhas com `trata_como_pessoa`); o recorte da API e a porta as tiram
- **Linhas de pessoa:** a porta esconde as marcadas em `trata_como_pessoa` (ADR 0075)
- **Chaves:** `cnpj`, `efetiva_em`, `novo_id`
- **Três datas:** aconteceu_em = `efetiva_em`; publico_em = `conhecido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.1.0
- **Onde fica:** Parquet em `<acervo>/base/trocas_de_auditor/trocas.parquet` (servidor de casa)
- **Linhagem:** `id_documento` leva ao FCA (e dali à linha de `auditores`, que guarda o SHA-256 do original); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `conhecido_em` | Data de entrega do FCA que mostrou a troca | data (dia) |
| `efetiva_em` | Início do mandato da firma nova | data (dia) |
| `anterior_id` | Identificador da firma anterior (ver `auditores`) | texto |
| `anterior` | Nome da firma anterior | texto |
| `novo_id` | Identificador da firma nova | texto |
| `novo` | Nome da firma nova | texto |
| `anos_com_o_anterior` | Tempo com a firma anterior | anos |
| `id_documento` | Número na CVM do FCA que mostrou a troca | texto |
| `trata_como_pessoa` | Verdadeiro quando o auditor anterior ou o novo vem sem CNPJ de firma (pode ser pessoa física) ou tem a raiz de empresário individual, natureza do grupo 4 ou MEI, ou quando a Receita guardada no dia da montagem não tem a raiz da empresa ou da firma (ADR 0075): a linha não sai da porta | verdadeiro ou falso |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `curva_juros`

Curva de juros própria, sem B3 nem ANBIMA: nominal (Tesouro Prefixado), real (Tesouro IPCA+) e inflação implícita, nos vértices de 6 meses a 20 anos, só com os títulos sem cupom, interpolação flat-forward e sem extrapolar (nominal desde 2004, real desde 2005). A taxa do Tesouro Direto tem um spread sobre o mercado secundário.

- **Fonte:** Tesouro Nacional: taxas diárias do Tesouro Direto (Tesouro Transparente)
- **Licença:** ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária (dias úteis)
- **Atraso de divulgação:** Um dia útil: o arquivo do Tesouro sai na manhã seguinte (`disponivel_em`)
- **Módulo:** macro · **Contém dado de pessoa:** não
- **Chaves:** `data_base`, `curva`, `prazo_anos`
- **Três datas:** aconteceu_em = `data_base`; publico_em = `disponivel_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/curva_juros/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `data_base` | Dia das taxas | data (dia) |
| `curva` | nominal, real ou implicita | texto |
| `prazo_anos` | Vértice da curva (0,5 a 20) | anos (base 252) |
| `taxa` | Taxa ao ano no vértice | fração (0,25 = 25%) |
| `titulos` | Títulos usados na curva do dia | número inteiro |
| `maior_prazo_anos` | Prazo do título mais longo do dia | anos (base 252) |
| `disponivel_em` | Dia útil seguinte: quando a taxa ficou pública | data (dia) |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `bcb_selic_focus`

Meta da Selic (SGS 432) e mediana do Focus para a Selic no fim de cada ano, com a safra: cada revisão é uma linha a mais, que passa a valer em `divulgado_em`. Tabela derivada da exportação do acervo, sem coleta nova. O Focus é o anual ("Selic no fim do ano"), não o por reunião. A meta só muda quando o Copom muda; a manutenção não aparece na série

- **Fonte:** Banco Central: SGS (série 432) e Focus (API Olinda, expectativas anuais)
- **Licença:** ODbL (dados abertos do Banco Central; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada montagem, a partir da exportação do acervo (`base/bcb_selic_focus.py`)
- **Atraso de divulgação:** O valor vale a partir de `divulgado_em` (a safra): a data da pesquisa, no Focus; o dia da coleta, na meta
- **Módulo:** macro · **Contém dado de pessoa:** não
- **Chaves:** `serie`, `referencia`, `divulgado_em`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `publico_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/bcb_selic_focus/bcb_selic_focus.parquet` (servidor de casa)
- **Linhagem:** Cada linha guarda quando o acervo registrou a observação (`origem_coletada_em`) e o SHA-256 da exportação de onde saiu (`origem_sha256`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `serie` | `bcb-sgs-432` (meta da Selic) ou `focus-selic-anual` (mediana do Focus) | texto |
| `referencia` | Dia a que o valor se refere (no Focus, 31/12 do ano esperado) | data (dia) |
| `valor` | Taxa ao ano, em % (14,25 = 14,25% ao ano) | 0 a 100 |
| `divulgado_em` | A safra: quando este valor passou a valer | data (dia) |
| `publico_em` | Igual a `divulgado_em`: quando o valor ficou público | data (dia) |
| `origem_coletada_em` | Quando o acervo registrou a observação | data e hora (UTC) |
| `origem_sha256` | SHA-256 da exportação do acervo de onde a tabela saiu | texto |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `release_x_oficial`

O que a empresa disse no press-release de resultado contra o que entregou à CVM no ITR ou na DFP do mesmo período: receita líquida, lucro líquido dos controladores e resultado operacional. Uma linha por valor lido do release, com o valor oficial, a diferença em R$ e em % e a classe (igual, igual por arredondamento, diferente, release não mostra, sem ITR). O modelo só copiou o número e o trecho; o código conferiu o trecho no texto do PDF e fez a comparação. A tabela guarda só números, nenhum texto do modelo. Diferença não é erro: pode ser ajuste ou outro critério da empresa

- **Fonte:** CVM: índice do IPE (press-releases de resultado) e dados abertos de DFP e ITR (`demonstracoes_como_era`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Semanal no servidor de casa: baixa os releases novos, lê em lote e remonta a tabela
- **Atraso de divulgação:** Vale a partir de `disponivel_em`, a data mais nova entre o release e o documento oficial: sem as duas pontas, não existe
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `protocolo`, `linha`, `periodo_lido`, `leitura`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `publico_em`; coletado_em = `montado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/release_x_oficial/release_x_oficial.parquet` (servidor de casa)
- **Linhagem:** `protocolo` e `link` levam ao PDF do release no IPE da CVM; `sha256_do_documento` é o SHA-256 dele, igual ao do manifesto. `modelo` e `versao_do_guia` dizem quem leu e com que instrução; a resposta bruta, o trecho, os tokens e os descartes ficam no arquivo de leituras ao lado do PDF (`scripts/ler_releases.py`). O valor oficial vem de `demonstracoes_como_era`, na versão que valia no dia do release. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `protocolo` | Protocolo da entrega do release no IPE da CVM | texto |
| `versao` | Versão da entrega do release (1, 2, 3...) | número inteiro |
| `periodo` | Trimestre do release (3T25) | texto |
| `referencia` | Data de referência do release: o fim do trimestre | data (dia) |
| `data_entrega` | Dia em que o release foi entregue à CVM | data (dia) |
| `link` | Endereço do PDF do release na CVM | texto |
| `linha` | receita_liquida, lucro_liquido_controladores ou resultado_operacional | texto |
| `periodo_lido` | O período a que o valor do release se refere: trimestre, acumulado_no_ano ou ano | texto |
| `leitura` | Ordem do valor quando o release repete a linha no mesmo período (0, 1...) | número inteiro |
| `valor_release_reais` | Valor que o release mostra, já em reais (vazio: o release não mostra a linha) | reais (R$), já multiplicado pela escala informada |
| `unidade_release` | Escala em que o release mostra o valor: unidade, mil, milhoes ou bilhoes | texto |
| `grupo` | con (consolidado) ou ind (individual) do valor oficial | texto |
| `documento` | ITR ou DFP de onde veio o valor oficial; DFP-ITR no 4º trimestre (o ano da DFP menos os nove meses do ITR) | texto |
| `documento_versao` | Versão do ITR ou da DFP usada | número inteiro |
| `documento_entregue_em` | Dia da entrega dessa versão à CVM | data (dia) |
| `valor_oficial_reais` | Valor do ITR ou da DFP, em reais | reais (R$), já multiplicado pela escala informada |
| `tolerancia_reais` | Uma unidade do que o release mostra, em reais: até aqui é arredondamento (o release soma parcelas arredondadas) | reais (R$), já multiplicado pela escala informada |
| `diferenca_reais` | Valor do release menos o oficial, em reais | reais (R$), já multiplicado pela escala informada |
| `diferenca_pct` | Diferença em % do valor oficial | pontos percentuais (66,25 = 66,25%) |
| `classe` | igual, igual (arredondamento), diferente, release não mostra ou sem ITR | texto |
| `disponivel_em` | A data mais nova entre o release e o documento oficial: quando a linha passou a existir | data (dia) |
| `publico_em` | Igual a `disponivel_em` | data (dia) |
| `modelo` | Modelo que leu o release | texto |
| `versao_do_guia` | Versão do guia de leitura dado ao modelo | texto |
| `sha256_do_documento` | SHA-256 do PDF do release | texto |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `noticias_fatos`

Um fato por linha para as notas de dado (ADR 0093): resultado trimestral (ITR e DFP), fato relevante (IPE) e reunião do Copom. Tabela derivada: cada linha diz de qual linha de qual tabela da base saiu (`chave_de_origem`) e quando ficou pública. Sem nenhum dado de pessoa: o trecho do fato relevante é cortado se citar nome

- **Fonte:** Derivado: `demonstracoes_como_era`, `eventos` (CVM) e `bcb_selic_focus` (Banco Central)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Ressalva de revenda:** A pauta `copom` vem do Banco Central (`bcb_selic_focus` e a tabela conferida do Copom)
- **Frequência:** Diária, no lote da manhã (`base/noticias_fatos.py`)
- **Atraso de divulgação:** Nenhum além do de cada origem: o fato vale a partir de `publico_em`
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `id_fato`
- **Três datas:** aconteceu_em = `aconteceu_em`; publico_em = `publico_em`; coletado_em = `coletado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/noticias_fatos/<ano>.parquet` (servidor de casa)
- **Linhagem:** `chave_de_origem` aponta a linha da tabela de entrada; `hash_da_linha` cobre a linha e os números dela (`noticias_numeros`). `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_fato` | SHA-256 de `pauta` + `chave_de_origem`: remontar dá o mesmo id | texto |
| `pauta` | `resultado_trimestral`, `fato_relevante` ou `copom` | texto |
| `versao_do_gatilho` | Versão da regra que criou a linha (`resultado-1.0`) | texto |
| `cnpj` | CNPJ da companhia (vazio no Copom) | texto |
| `empresa` | Nome da companhia, como a CVM publica (vazio no Copom) | texto |
| `tabela_de_origem` | Tabela da base de onde o fato saiu | texto |
| `chave_de_origem` | JSON canônico da chave da linha de origem | texto |
| `aconteceu_em` | Fim do trimestre, data de referência do IPE ou data da reunião | data (dia) |
| `publico_em` | Quando o documento ficou público (o comunicado do Copom, no dia da reunião) | data (dia) |
| `coletado_em` | Quando a origem foi baixada | data e hora (UTC) |
| `link` | Endereço do documento original (CVM) ou do comunicado (Banco Central) | texto |
| `topico` | Fato relevante: tópico da lista fechada (`src/topicos.py`); vazio nas outras pautas | texto |
| `metodo_do_topico` | Fato relevante: `regra_titulo` | texto |
| `versao_do_topico` | Fato relevante: versão das regras do tópico | texto |
| `trecho` | Fato relevante: o assunto escrito pela empresa, literal, até 200 caracteres | texto |
| `reapresentacao` | Resultado: o documento é uma versão 2 em diante (verdadeiro/falso) | verdadeiro ou falso |
| `fato_anterior` | Resultado reapresentado: `id_fato` da versão anterior | texto |
| `marcas` | Lista: `dado_em_conferencia`, `fontes_divergem`, `trecho_cortado` | texto |
| `licenca` | Família da fonte (`cvm` ou `bcb`), para a marca de licença | texto |
| `hash_da_linha` | SHA-256 da linha e dos números dela | texto |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `noticias_numeros`

Um número por linha de cada fato de `noticias_fatos`, com a conta, o período, a versão e a data pública de onde saiu, e o cálculo quando o valor não é o publicado (trimestre isolado)

- **Fonte:** Derivado: `demonstracoes_como_era` (CVM) e `bcb_selic_focus` (Banco Central)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Ressalva de revenda:** Os números do Copom vêm do Banco Central
- **Frequência:** Diária, junto com `noticias_fatos`
- **Atraso de divulgação:** Nenhum além do de cada origem: cada número vale a partir de `origem_divulgado_em`
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `id_fato`, `campo`
- **Três datas:** publico_em = `origem_divulgado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/noticias_numeros/<ano>.parquet` (servidor de casa)
- **Linhagem:** Cada linha diz a conta, o período, a versão e a data pública da origem; `calculo` mostra a conta feita quando o valor não é o publicado. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_fato` | Fato a que o número pertence (`noticias_fatos`) | texto |
| `campo` | Nome do número (`receita_trimestre`, `meta_selic`...) | texto |
| `valor` | O número, na unidade da coluna `unidade` | número com decimais, na unidade da fonte |
| `unidade` | `reais` ou `pct_ao_ano` | texto |
| `periodo` | Período em texto (`3T26`, `30/09/2026`, `fim de 2026`) | texto |
| `origem_conta` | Conta do plano da CVM ou código da série do Banco Central | texto |
| `origem_periodo` | `acumulado`, `exercicio` ou `posicao` (ou vazio na série do Banco Central) | texto |
| `origem_versao` | Versão do documento de origem | número inteiro |
| `origem_divulgado_em` | Quando o valor de origem ficou público | data (dia) |
| `calculo` | Vazio se é o valor publicado; senão a conta (`acumulado 9M26 - acumulado 6M26`) | texto |

## `controladas`

Controladas e coligadas de cada companhia informadas no FRE desde 2010, com a participação e a data de entrega. O FRE mais novo deixa o tipo da sociedade em branco em muitas linhas, e o FRE guarda ligações antigas. **Limites medidos em 12/11/2026:** 8643 linhas não têm CNPJ (o formulário não traz CNPJ para essas investidas; só o nome as distingue); a chave se repete em 8373 linhas (866 idênticas em todas as colunas; as demais são investidas sem CNPJ com nomes diferentes ou o mesmo CNPJ com participação ou tipo diferente no mesmo documento). Quem junta por CNPJ pode receber mais de uma linha por investida.

- **Fonte:** CVM: dados abertos do FRE, tabela de participação em sociedades
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada montagem (`scripts/montar_base_historica.py`), que relê todos os arquivos anuais guardados
- **Atraso de divulgação:** O FRE é entregue até 5 meses depois do fim do exercício e reapresentado a cada mudança; a ligação vale a partir de `conhecido_em`
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj_companhia`, `referencia`, `versao`, `cnpj`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/controladas/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj_companhia` | CNPJ da companhia que informou (14 dígitos) | texto |
| `companhia` | Nome da companhia | texto |
| `referencia` | Data de referência do FRE | data (dia) |
| `versao` | Versão do FRE (fica a mais nova) | número inteiro |
| `id_documento` | Número do documento na CVM | texto |
| `conhecido_em` | Data em que a CVM recebeu essa versão do FRE | data (dia) |
| `cnpj` | CNPJ da sociedade (14 dígitos; vazio nas estrangeiras) | texto |
| `razao_social` | Razão social da sociedade | texto |
| `tipo` | controlada, coligada ou vazio (não informado) | texto |
| `participacao` | Participação da companhia na sociedade | pontos percentuais (66,25 = 66,25%) |
| `ano_do_arquivo` | Ano do arquivo da CVM de onde a linha veio | ano |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `controladas_pj`

Cópia reduzida de `controladas` que vai ao VPS só para a lista de compradores por setor da API externa (linha 844): só a companhia e a controlada cujas raízes estão em `cnpj_empresas_pj` (sem pessoa), sem a razão social da sociedade nem o nome da companhia. Cada documento do FRE (companhia, referência e versão) tem ainda uma linha de marca, com `cnpj`, `tipo` e `participacao` vazios: assim o FRE mais recente da companhia continua o mesmo da tabela inteira, mesmo quando ele só tinha controladas fora da lista. Montada no envio, não fica no acervo de casa

- **Fonte:** CVM: dados abertos do FRE, tabela de participação em sociedades (cópia reduzida de `controladas`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada envio do recorte ao VPS (`scripts/montar_recorte_da_api.py --degrau 4`)
- **Atraso de divulgação:** O FRE é entregue até 5 meses depois do fim do exercício e reapresentado a cada mudança; a ligação vale a partir de `publico_em`
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj_companhia`, `referencia`, `versao`, `cnpj`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `publico_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/controladas_pj/controladas_pj.parquet`, só no VPS (montado pelo recorte, `base/recorte_dos_compradores.py`)
- **Linhagem:** Derivada de `controladas` no envio; a trava `base/recorte_dos_compradores.py::conferir_reduzidas` lê a saída e derruba o envio em coluna fora da lista, raiz fora de `cnpj_empresas_pj`, CNPJ que não confere (dígito errado; na controlada, também CPF completado com zeros), linha sem CNPJ com tipo ou participação ou cópia vazia.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj_companhia` | CNPJ da companhia que informou (14 dígitos) | texto |
| `cnpj` | CNPJ da sociedade (14 dígitos); vazio só na linha de marca do documento | texto |
| `tipo` | controlada, coligada ou vazio (não informado, ou a linha de marca) | texto |
| `participacao` | Participação da companhia na sociedade | pontos percentuais (66,25 = 66,25%) |
| `referencia` | Data de referência do FRE | data (dia) |
| `versao` | Versão do FRE | número inteiro |
| `publico_em` | Data em que a CVM recebeu essa versão do FRE (`conhecido_em`) | data (dia) |

## `rotulos_atraso`

Rótulo do modelo de atraso na entrega (modelo 8, ADR 0030; a rota da API acrescenta `situacao_da_entrega`, campo calculado por ela, não coluna desta tabela): uma linha por companhia, documento (DFP ou ITR) e data-base, com o prazo da CVM, a primeira entrega e se atrasou. Entram os documentos entregues e os devidos sem entrega (entregou um ano antes, ativa no prazo, data-base no calendário da empresa e no arquivo do ano). Só entra o documento que a empresa devia: registrada e ativa no cadastro da CVM na data do prazo. Ficam de fora o que ela manda para pedir o registro (prazo antes do primeiro registro ou entre dois registros), o que manda depois do cancelamento e o das empresas fora do cadastro (quase todas emissores estrangeiros); o manifesto conta quantos ficaram de fora, por motivo (`fora_dos_exemplos`). Não é coluna para prever: é a resposta que o modelo tenta acertar (ADR 0027) **Sem pessoa pela raiz:** toda raiz de CNPJ desta tabela existe na `cnpj_empresas_pj`, que só tem pessoa jurídica; CNPJ que não tem 14 dígitos conta como fora. A prova cobre quem a linha descreve, não o texto livre que ela carrega (o assunto de um evento, por exemplo). A conferência é `scripts/conferir_sem_pessoa.py`, rodada antes de cada concessão do piloto

- **Fonte:** CVM: dados abertos da DFP e do ITR (índice das entregas) e cadastro das companhias
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Refeita a cada montagem, com os arquivos anuais e o cadastro mais recentes
- **Atraso de divulgação:** O rótulo de um documento existe a partir do prazo (ou da entrega, se veio antes); uma falta só conta se o prazo venceu antes da coleta do arquivo do ano
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `documento`, `referencia`
- **Três datas:** aconteceu_em = `prazo`; publico_em = `primeira_entrega`; coletado_em = `montado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/rotulos_atraso/rotulos_atraso.parquet`, com o manifesto ao lado (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** O manifesto (`rotulos_atraso.json`) lista o endereço e o SHA-256 de cada arquivo anual da DFP e do ITR e do cadastro usados, e o SHA-256 da tabela; `montado_em` é o início do dia (em Brasília) da montagem: os mesmos originais no mesmo dia dão a mesma tabela. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `documento` | DFP (demonstrações anuais) ou ITR (informações trimestrais) | texto |
| `referencia` | Data a que o documento se refere (fim do exercício ou do trimestre) | data (dia) |
| `data_da_previsao` | Dia em que o modelo faz a pergunta (a própria data-base) | data (dia) |
| `prazo` | Último dia para entregar, com feriados e prorrogações (`src/prazos.py`) | data (dia) |
| `primeira_entrega` | Dia da primeira entrega (vazio: não entregou) | data (dia) |
| `dias_uteis_de_atraso` | Dias úteis entre o prazo e a entrega (ou a montagem, sem entrega); 0 no prazo | número inteiro |
| `atrasou` | Entregou 1 dia útil ou mais depois do prazo, ou não entregou | verdadeiro ou falso |
| `atraso_grave` | Mais de 30 dias corridos de atraso, ou não entregou | verdadeiro ou falso |
| `zona_cinzenta` | Atraso de 1 ou 2 dias úteis: pode ser um feriado estadual ou municipal | verdadeiro ou falso |
| `uf` | Estado da sede, no cadastro de hoje | texto |
| `mes_fim_do_exercicio` | Mês de fim do exercício (o mais comum nas DFPs da companhia) | mês (1 a 12) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `colunas_atraso`

Colunas do modelo de atraso na entrega (modelo 8) como eram na data da previsão: uma linha por exemplo de `rotulos_atraso` (mesma chave), só com fatos públicos antes de `data_da_previsao` (o que chegou no próprio dia fica de fora). Grupos: histórico de entregas, auditor, dificuldade (só a recuperação judicial da própria companhia, pela raiz do CNPJ), cadastro (do FCA vigente na data, nunca do cadastro de hoje), balanço e calendário. O selo de qualidade e os fatos relevantes ficam fora da v1. Vazio = não se sabia na data. O rótulo não está aqui: junta-se pela chave na hora de treinar

- **Fonte:** CVM: índice da DFP/ITR, FCA (dados gerais, valores mobiliários e auditores), IPE (insolvência e eventos), demonstrações "como era" e cadastro das companhias
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Refeita a cada montagem do modelo 8 (`scripts/montar_modelo_8.py`)
- **Atraso de divulgação:** Cada coluna usa só o que era público na véspera da previsão
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `documento`, `referencia`
- **Três datas:** aconteceu_em = `data_da_previsao`; coletado_em = `montado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/colunas_atraso/colunas_atraso.parquet`, com o manifesto ao lado (servidor de casa, `scripts/montar_modelo_8.py`)
- **Linhagem:** O manifesto (`colunas_atraso.json`) lista cada tabela da base lida (caminho e SHA-256) e cada arquivo anual do índice e o cadastro; `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `documento` | DFP (demonstrações anuais) ou ITR (informações trimestrais) | texto |
| `referencia` | Data a que o documento se refere (fim do exercício ou do trimestre) | data (dia) |
| `data_da_previsao` | Dia da previsão (a própria data-base) | data (dia) |
| `documentos_anteriores` | DFPs e ITRs anteriores com o resultado já conhecido na véspera | número inteiro |
| `atrasou_o_anterior` | O último documento anterior conhecido atrasou (ou venceu sem entrega) | verdadeiro ou falso |
| `atrasos_nos_ultimos_4` | Atrasos entre os 4 documentos anteriores | número inteiro |
| `atrasos_nos_ultimos_8` | Atrasos entre os 8 documentos anteriores | número inteiro |
| `media_dias_de_atraso_ultimos_4` | Média de dias úteis de atraso nos 4 anteriores (sem entrega: até a previsão) | número com decimais, na unidade da fonte |
| `folga_media_ultimos_4` | Média de dias úteis entre a entrega e o prazo nos 4 anteriores (negativa: atrasou) | número com decimais, na unidade da fonte |
| `entregou_o_anterior_no_ultimo_dia` | O último documento anterior foi entregue no dia do prazo | verdadeiro ou falso |
| `reapresentacoes_12_meses` | Versões 2 em diante de DFP/ITR públicas nos 12 meses antes da previsão | número inteiro |
| `auditor_rede_grande` | O auditor do FCA vigente é EY, PwC, KPMG ou Deloitte | verdadeiro ou falso |
| `trocou_de_auditor_12_meses` | Uma troca de auditor ficou pública nos 12 meses antes da previsão | verdadeiro ou falso |
| `anos_com_o_auditor` | Anos desde o início do mandato mais antigo da firma atual no FCA vigente | anos |
| `ja_entrou_em_recuperacao_judicial` | Recuperação judicial da própria companhia (raiz do CNPJ) pública no IPE antes da previsão; vazio se a companhia não tinha nenhum documento no IPE | verdadeiro ou falso |
| `setor` | Setor de atividade no FCA vigente na data | texto |
| `categoria` | Categoria do registro (A ou B) no FCA vigente | texto |
| `controle_acionario` | Espécie do controle no FCA vigente | texto |
| `exercicio_fora_de_dezembro` | O exercício social não fecha em dezembro (FCA vigente) | verdadeiro ou falso |
| `anos_de_registro` | Anos desde o último registro na CVM antes da previsão | anos |
| `tem_acao_na_bolsa` | Ações ou units negociadas em bolsa no FCA vigente | verdadeiro ou falso |
| `segmento_de_listagem` | Segmento de listagem dessas ações (Novo Mercado, Nível 1...) | texto |
| `ativo_total` | Ativo total do último balanço público (consolidado se houver) | reais (R$), já multiplicado pela escala informada |
| `patrimonio_liquido_negativo` | Patrimônio líquido negativo no último balanço público | verdadeiro ou falso |
| `prejuizo_no_ultimo_exercicio` | Prejuízo na DRE do último exercício (12 meses) público | verdadeiro ou falso |
| `divida_curto_prazo_sobre_caixa` | Empréstimos de curto prazo (2.01.04) sobre caixa (1.01.01); vazio sem caixa | número com decimais, na unidade da fonte |
| `trimestre` | Trimestre da data-base (1 a 4) | número inteiro |
| `prazo_perto_de_feriado` | Há feriado nacional nos 7 dias antes do prazo (ou no próprio dia) | verdadeiro ou falso |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `empresa_serie`

De que companhia listada é cada entidade que os reguladores enxergam (operadora de saúde, distribuidora, banco no Pix, prestadora de telecomunicações, usina, concessionária de ferrovia, companhia aérea): pelo CNPJ, pelo nome exato ou pela tabela conferida (`base/conferidas/empresa_serie.csv`), e daí pelas `controladas`. Os capítulos do NCM do Comex Stat ligam às companhias expostas ao produto (`via` = `produto`: exposição, não posse). Toda entidade aparece, ligada ou não.

- **Fonte:** ANS, ANEEL (SAMP), Banco Central (Pix), Anatel, ANP, ONS, ANTT, ANAC e Comex Stat, ligados pelo FRE da CVM e pelo FCA (tickers)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Ressalva de revenda:** Os nomes e códigos das entidades seguem a licença de cada regulador: CC BY (ANS, Anatel, ANP, ONS, ANTT, ANAC; citar), ODbL (ANEEL, Banco Central) e dados abertos de uso livre (Comex Stat; citar Secex/MDIC).
- **Frequência:** Refeita a cada montagem, com a safra mais recente de cada fonte
- **Atraso de divulgação:** A ligação vale a partir de `desde` (entrega do FRE que a mostrou); os tickers são os do FCA mais recente
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `fonte`, `chave`, `cnpj_companhia`
- **Três datas:** aconteceu_em = `desde`; coletado_em = `montado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.1.0
- **Onde fica:** Parquet em `<acervo>/base/empresa_serie/empresa_serie.parquet` (servidor de casa)
- **Linhagem:** `origem_sha256` leva ao arquivo do regulador no acervo de onde a entidade saiu (no Comex, à versão da tabela conferida); as ligações saem de `controladas`, que guarda o SHA-256 de cada FRE; `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `fonte` | Fonte do arquivista de onde veio a entidade | texto |
| `chave` | Como a fonte identifica a entidade: registro ANS, CNPJ, ISPB, nome, sigla ou capítulo do NCM | texto |
| `nome` | Nome da entidade na fonte (ou na tabela conferida) | texto |
| `raiz` | Raiz do CNPJ da entidade (8 dígitos), quando há | texto |
| `cnpj_companhia` | CNPJ da companhia ligada (14 dígitos) | texto |
| `companhia` | Nome da companhia ligada | texto |
| `via` | propria, controlada, coligada, sem_tipo ou produto | texto |
| `por` | cnpj, nome ou tabela (conferida à mão) | texto |
| `participacao` | Participação informada no FRE (vazia no produto) | pontos percentuais (66,25 = 66,25%) |
| `desde` | 1ª entrega à CVM de um FRE que mostrava a ligação | data (dia) |
| `ultima_referencia` | Referência do FRE mais novo que mostra a ligação | data (dia) |
| `ate` | 1ª referência do FRE da companhia que já não mostra a ligação (vazia: ainda aparece, ou a companhia parou de entregar o FRE) | data (dia) |
| `ate_publico_em` | Dia em que essa entrega ficou pública: antes dele não se sabia que a ligação acabou | data (dia) |
| `vigente` | A ligação aparece no FRE mais novo da companhia; falso quando acabou ou a companhia parou de entregar (a última evidência é a `ultima_referencia`) | verdadeiro ou falso |
| `principal` | A ligação a usar da entidade (ticker hoje, própria, a que ainda vale, FRE mais recente; nunca no produto; na ANEEL, nunca participação minoritária) | verdadeiro ou falso |
| `tickers` | Tickers da companhia no FCA mais recente | texto |
| `origem_sha256` | SHA-256 do arquivo de onde a entidade saiu | texto |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `entidades`

Uma linha por entidade da rede (ADR 0077): empresa (pela raiz do CNPJ; a filial é a mesma empresa), fundo (pelo CNPJ de 14), valor mobiliário (pelo ISIN das carteiras dos fundos) ou firma de auditoria (pelo código da CVM), com id determinístico (`base/rede/ids.py`), nome, natureza jurídica e MEI. Vem das tabelas que a base já tem: cadastro da CVM, FCA, controladas, auditores, empresa ↔ série, cadastro e carteiras de fundos, IF.data e GLEIF. Empresário individual, pessoa física com CNPJ e MEI ficam sem nome e com `trata_como_pessoa`

- **Fonte:** CVM (cadastro, FCA, FRE, fundos), Banco Central (IF.data), GLEIF, os reguladores da empresa ↔ série e a Receita (natureza jurídica e opção pelo MEI)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Ressalva de revenda:** A natureza jurídica e o MEI com `natureza_fonte` = receita vêm do CNPJ aberto da Receita (CC BY, citar a Receita); o LEI é do GLEIF (CC0, citar); os códigos dos reguladores seguem a licença de cada um (ver `empresa_serie`).
- **Frequência:** Refeita a cada montagem; versão nova só quando o conteúdo muda
- **Atraso de divulgação:** O da fonte mais lenta de cada entidade; `publico_em` diz desde quando se sabe dela
- **Módulo:** rede · **Contém dado de pessoa:** não
- **Chaves:** `id_entidade`
- **Três datas:** publico_em = `publico_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/rede/entidades.parquet` (servidor de casa, `scripts/montar_rede.py`)
- **Linhagem:** Derivada: o manifesto aponta as tabelas de entrada (com o SHA-256 do conteúdo), as tabelas conferidas (`emissores_antigos.csv`, `entidades.csv`) e os originais lidos do acervo (cadastro da CVM, páginas do GLEIF, Empresas e Simples da Receita); a linhagem segue até a coleta de cada um. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_entidade` | 'E' + 20 hexadecimais do SHA-256 do identificador primário | texto |
| `tipo` | empresa, fundo, valor_mobiliario ou auditor | texto |
| `nome` | Nome pela fonte mais confiável (vazio na pessoa com CNPJ) | texto |
| `natureza_juridica` | Código da natureza jurídica da Receita (2046 = S.A. aberta), nao_informada ou nao_se_aplica (valor mobiliário) | texto |
| `natureza_fonte` | receita, fonte (CVM ou cadastro de fundos) ou nao_informada | texto |
| `mei` | Verdadeiro se é MEI hoje (Simples da Receita) | verdadeiro ou falso |
| `trata_como_pessoa` | Verdadeiro para empresário individual (213-5), grupo 4, MEI e natureza não informada: nunca recebe sinal negativo publicado | verdadeiro ou falso |
| `fontes` | As fontes de onde a entidade saiu, separadas por vírgula | texto |
| `publico_em` | O dia mais antigo em que alguma fonte a tornou pública | data (dia) |

## `identificadores`

Os identificadores de cada entidade da rede, com de quando a quando valem: CNPJ (com letras), raiz, LEI, ticker, emissor e códigos dos reguladores (`codigo_<fonte>`). Resolvidos por regras de código em ordem fixa (1 CNPJ, 2 raiz, 3 LEI, 4 emissor e ticker, 5 código do regulador, 7 tabela conferida); o mesmo identificador em duas entidades no mesmo período é conflito e não entra em nenhuma. **Limite medido em 12/11/2026:** `desde` só existe para ticker e emissor; nos registros oficiais (CNPJ, ISIN, códigos da CVM e das agências) a fonte não diz desde quando o código vale, e a coluna fica vazia (193197 de 194489 linhas).

- **Fonte:** CVM (cadastro, FCA, FRE, fundos), Banco Central (IF.data), GLEIF e os reguladores da empresa ↔ série
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Ressalva de revenda:** A natureza jurídica e o MEI com `natureza_fonte` = receita vêm do CNPJ aberto da Receita (CC BY, citar a Receita); o LEI é do GLEIF (CC0, citar); os códigos dos reguladores seguem a licença de cada um (ver `empresa_serie`).
- **Frequência:** Refeita a cada montagem; versão nova só quando o conteúdo muda
- **Atraso de divulgação:** O ticker vale da entrega do FCA que o trouxe; o código do IF.data, 120 dias depois
- **Módulo:** rede · **Contém dado de pessoa:** não
- **Chaves:** `id_entidade`, `sistema`, `valor`, `desde`
- **Três datas:** aconteceu_em = `desde`; publico_em = `publico_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/rede/identificadores.parquet` (servidor de casa, `scripts/montar_rede.py`)
- **Linhagem:** Derivada: o manifesto aponta as tabelas de entrada (com o SHA-256 do conteúdo), as tabelas conferidas (`emissores_antigos.csv`, `entidades.csv`) e os originais lidos do acervo (cadastro da CVM, páginas do GLEIF, Empresas e Simples da Receita); a linhagem segue até a coleta de cada um. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `id_entidade` | A entidade (tabela `entidades`) | texto |
| `sistema` | cnpj, cnpj_raiz, lei, isin, ticker, emissor, codigo_cvm_auditor ou codigo_<fonte> (codigo_bcb_ifdata...) | texto |
| `valor` | O identificador (CNPJ sem pontuação, com letras se tiver) | texto |
| `desde` | Desde quando vale (vazio: sempre) | data (dia) |
| `ate` | Até quando valeu, sem incluir o dia (vazio: ainda vale) | data (dia) |
| `publico_em` | Desde quando a ligação era pública (como era na data) | data (dia) |
| `regra` | A regra que ligou (1, 2, 3, 4, 5 ou 7; a menor, se várias) | número inteiro |
| `conferido_por` | regra (código) ou tabela (conferida à mão) | texto |
| `fontes` | As fontes que trouxeram o identificador, separadas por vírgula | texto |

## `ligacoes`

Uma linha por relação entre duas entidades da rede (ADR 0077), com as três datas: sociedade controlada, coligada ou participada da companhia (FRE), entidade do regulador que opera para a companhia (empresa ↔ série), instituição do conglomerado do líder (IF.data), firma que audita a companhia (FCA), empresa que emite o valor mobiliário e fundo que o detém (carteiras do CDA, meses seguidos num período só). Nada é apagado entre cargas: o que some da fonte fica, encerrado pela carga. Esta é a vista interna; a publicada (sem pessoas) sai de `base/rede/vistas.py`. **Limite medido em 12/11/2026:** `papel` fica vazio em 25182 linhas, todas dos tipos controlada_de, participada_de, coligada_de, audita e emite, que não têm papel; ele só existe nos tipos detem, do_conglomerado_de e opera_para.

- **Fonte:** CVM (FRE, FCA, carteiras dos fundos), Banco Central (IF.data) e os reguladores da empresa ↔ série
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Ressalva de revenda:** A natureza jurídica e o MEI com `natureza_fonte` = receita vêm do CNPJ aberto da Receita (CC BY, citar a Receita); o LEI é do GLEIF (CC0, citar); os códigos dos reguladores seguem a licença de cada um (ver `empresa_serie`).
- **Frequência:** Toda noite no servidor de casa; versão nova só quando o conteúdo muda
- **Atraso de divulgação:** O da fonte: o FRE e o FCA pela entrega à CVM, a carteira 90 dias depois do mês, o IF.data 120 dias depois da data-base; a fonte de governo desde que guardada
- **Módulo:** rede · **Contém dado de pessoa:** não
- **Chaves:** `de`, `para`, `tipo`, `papel`, `aconteceu_em`, `fonte`
- **Três datas:** aconteceu_em = `aconteceu_em`; publico_em = `publico_em`; coletado_em = `coletado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.1.0
- **Onde fica:** Parquet em `<acervo>/base/rede/ligacoes.parquet` (servidor de casa, `scripts/montar_rede.py`)
- **Linhagem:** Derivada: o manifesto aponta as tabelas de entrada (com o SHA-256 do conteúdo), as tabelas conferidas (`emissores_antigos.csv`, `entidades.csv`) e os originais lidos do acervo (cadastro da CVM, páginas do GLEIF, Empresas e Simples da Receita); a linhagem segue até a coleta de cada um. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). Cada linha leva o `origem_sha256` do arquivo (ou da tabela da base) de onde veio.

| Coluna | O que é | Unidade |
|---|---|---|
| `de` | A entidade de onde a relação sai (a controlada, o fundo, a firma) | texto |
| `para` | A entidade para onde a relação vai (a companhia, o valor mobiliário) | texto |
| `tipo` | controlada_de, coligada_de, participada_de (FRE sem o tipo), opera_para, do_conglomerado_de, audita, emite ou detem | texto |
| `papel` | Detalhe do tipo: comprado, emprestado ou vendido (detem); a via e se é a principal (opera_para); lider (do_conglomerado_de) | texto |
| `participacao` | Participação informada no FRE (vazia nos outros) | pontos percentuais (66,25 = 66,25%) |
| `aconteceu_em` | Data do fato: referência do FRE, início do mandato, primeiro mês da carteira. É o início da validade (valido_de): a ligação vale de `aconteceu_em` até `ate` | data (dia) |
| `infracao_em` | Data da infração, nas sanções (vazia nas fontes de hoje) | data (dia) |
| `publico_em` | Desde quando a relação era pública (como era na data) | data (dia) |
| `coletado_em` | Quando a base guardou o arquivo de onde veio (registro de coletas) | data (dia) |
| `ate` | Até quando valeu, sem incluir o dia (vazio: ainda vale): o fim da validade (valido_ate). O que valia em D sabendo o que se sabia em K: `base/rede/controle.py::valiam_em` | data (dia) |
| `ate_publico_em` | Desde quando se sabia que tinha acabado: o FRE, o FCA ou a carteira que já não a mostra (vazio: ainda vale). Como era em D usa este, não o `ate` | data (dia) |
| `situacao` | vigente ou encerrada | texto |
| `encerrada_por` | fonte (a fonte diz o fim) ou carga (sumiu da fonte nesta carga); vazio se vigente | texto |
| `fonte` | cvm-fre, cvm-fca, cvm-cda, bcb-ifdata ou empresa_serie | texto |
| `origem_sha256` | SHA-256 do arquivo ou da tabela da base de onde veio | texto |
| `conferido_por` | regra (código) ou tabela (conferida à mão) | texto |

## `ma_assessorias`

Negócios de M&A do middle market tirados dos posts das assessorias independentes (ADR 0082), uma linha por página de negócio: as empresas, o tipo e o sentido. Só fatos: nenhum texto do post e nenhuma pessoa física (a equipe da assessoria nem é lida). Sem data do negócio (a página não tem; `conhecido_em` está em `ma_datas`) e sem CNPJ das partes (passo 3)

- **Fonte:** Sites das assessorias de M&A (IGC Partners), páginas guardadas pelo arquivista
- **Licença:** Posts públicos de assessorias de M&A: só fatos, sem texto (ADR 0082)
- **Revenda:** a confirmar (sem resposta escrita sobre uso comercial ou treino de ML: vale como não comercial até a resposta)
- **Frequência:** Semanal (a coleta é aos domingos); versão nova só quando uma página muda
- **Atraso de divulgação:** Desconhecido: a assessoria posta depois de fechar o negócio, sem dizer quando; a base só sabe a data da nossa coleta
- **Módulo:** ma · **Contém dado de pessoa:** não
- **Chaves:** `assessoria`, `url`
- **Três datas:** coletado_em = `coletado_em`
- **Histórico desde:** 2026-10-16 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ma/assessorias/<assessoria>.parquet` (servidor de casa, `scripts/carga_ma_assessorias.py`)
- **Linhagem:** Cada linha guarda o endereço e o SHA-256 da página no acervo (`url`, `sha256`, que levam ao registro de coletas) e quando ela foi coletada; o `.json` guarda as páginas usadas. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `assessoria` | Quem postou (`igc`) | texto |
| `url` | Endereço da página do negócio | texto |
| `sha256` | SHA-256 da página guardada no acervo | texto |
| `coletado_em` | Quando o arquivista baixou a página | data e hora (UTC) |
| `tipo` | Código da taxonomia de M&A (AQ_CONTROLE, AQ_MINORITARIA, FUSAO, JV, VENDA_ATIVO, PE_VC, DCM) ou desconhecido | texto |
| `regra` | Qual regra do título deu o tipo (divida, fusao, jv, venda_de_ativo, minoritaria, majoritaria, participacao, financiamento, rodada, aquisicao); vazio se nenhuma | texto |
| `alvo` | Empresa(s) comprada(s) ou que recebeu o investimento, separadas por `; ` | texto |
| `comprador` | Quem comprou ou investiu | texto |
| `vendedor` | Quem vendeu, quando não é a própria alvo (controladora, dono do ativo) | texto |
| `outras_partes` | Empresas da página sem papel dito no título (controladora de quem compra) | texto |
| `cliente` | Empresa(s) que a assessoria diz ter assessorado (campo da página) | texto |
| `contraparte` | A(s) outra(s) empresa(s) do negócio, como a página lista | texto |
| `papeis_por` | titulo (os papéis vieram do título) ou pagina (algum nome não aparece no título e o lado veio do campo da página); vazio sem empresas | texto |
| `lado_da_assessoria` | venda, compra, captacao (dívida ou empréstimo) ou parte (fusão, JV) | texto |
| `setor` | Setor da alvo; vazio enquanto a página não diz (vem do CNPJ no passo 3) | texto |
| `paises` | Países das partes (ISO 3166-1, separados por `;`), sem dizer de quem | texto |
| `valor` | Valor que o título escreve (quase sempre vazio; nas emissões de dívida, o volume) | número com decimais, na unidade da fonte |
| `moeda` | BRL ou USD, a do valor | texto |
| `conferencia` | assessoria (fonte única: declarado por quem assessorou); a confirmação por fonte oficial, com a prova, fica em `ma_datas` | texto |

## `ma_candidatos`

Documentos que as companhias abertas entregam à CVM no IPE desde 2003 e que podem anunciar uma operação de M&A (série 1 da base de M&A, ADR 0063), uma linha por versão entregue: fatos relevantes escolhidos pelo assunto, comunicados ao mercado com o tipo no assunto e todo edital de OPA. É a lista do que ler, não a lista de operações: favorece a cobertura, e o assunto genérico (o padrão do sistema da CVM, o vazio, o esclarecimento sobre notícia) entra sem tipo, para a leitura do texto decidir. Recompra, proventos, dívida e oferta de ações ficam fora. Cobertura contra as reestruturações declaradas no FRE (2010 a 2015): 80% das operações com algum fato relevante da companhia no ano anterior têm fato relevante candidato na janela (92% com os comunicados); lidas à mão 40 perdidas, 36 não tinham fato relevante sobre a operação (~97% dos que existem). Amostra de ouro: 84 de 85 operações candidatas

- **Fonte:** CVM: arquivos anuais do IPE (`cvm-hist-ipe`), lidos por `base/ma_ipe.py`
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária no servidor de casa (`scripts/montar_ma_candidatos.py`), depois do arquivista baixar o IPE do ano
- **Atraso de divulgação:** O documento vale a partir de `publico_em` (entrega da versão à CVM), nunca da `referencia` informada pela companhia
- **Módulo:** ma · **Contém dado de pessoa:** não
- **Chaves:** `link`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `publico_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2003-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ma/candidatos/candidatos.parquet` (servidor de casa, `scripts/montar_ma_candidatos.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do arquivo anual do IPE de onde veio (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); o manifesto lista os arquivos anuais lidos. `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `codigo_cvm` | Código da companhia na CVM | texto |
| `categoria` | Categoria do IPE: Fato Relevante, Comunicado ao Mercado ou o edital de OPA | texto |
| `tipo` | Tipo do IPE (vazio no fato relevante) | texto |
| `assunto` | Assunto como a companhia preencheu | texto |
| `tipo_provavel` | Pista do assunto: OPA, INC_ACOES, FUSAO, CISAO, INC_EMPRESA, JV, UPI, PRIVATIZACAO, ALIEN_CONTROLE, VENDA_ATIVO, AQUISICAO (controle ou minoritária) ou NEGOCIACAO (memorando, exclusividade); vazia no assunto genérico. Não é o tipo da operação: quem diz é o texto | texto |
| `evidencia` | Por que entrou: assunto (o assunto dá o tipo provável), assunto_generico (fato relevante de assunto padrão ou vazio) ou categoria (edital de OPA) | texto |
| `referencia` | Data de referência informada pela companhia | data (dia) |
| `publico_em` | Entrega da versão do documento à CVM: quando ficou público para a base | data (dia) |
| `protocolo` | Protocolo de entrega na CVM (de 2003 a 2014, o link, que a CVM não dá protocolo) | texto |
| `versao` | Versão do documento (reapresentação) | número inteiro |
| `link` | Link do documento no sistema da CVM | texto |
| `origem_sha256` | SHA-256 do arquivo original no acervo | texto |
| `origem_coletada_em` | Quando o arquivista baixou esse original | data e hora (UTC) |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `ma_partes`

As empresas de cada negócio de M&A das assessorias (`ma_assessorias`), uma linha por empresa de cada página, ligadas à rede de entidades (ADR 0077) só por regras exatas: o nome normalizado contra os nomes da rede e a razão social do CNPJ e, se nada casou, contra o nome fantasia. Nome de mais de uma entidade fica na dúvida, nunca escolhido; empresário individual e MEI nunca são ligados (ADR 0075). Série 5 do plano de M&A, passo 3 (ADR 0082)

- **Fonte:** `ma_assessorias`, a rede (`entidades`, `identificadores`) e o CNPJ aberto da Receita (razão social e nome fantasia, lidos e descartados: só a raiz fica)
- **Licença:** Posts públicos de assessorias de M&A: só fatos, sem texto (ADR 0082)
- **Revenda:** a confirmar (sem resposta escrita sobre uso comercial ou treino de ML: vale como não comercial até a resposta)
- **Frequência:** Semanal, junto da extração; versão nova só quando uma entrada muda
- **Atraso de divulgação:** O da tabela `ma_assessorias` e o do mês do CNPJ guardado
- **Módulo:** ma · **Contém dado de pessoa:** não
- **Chaves:** `assessoria`, `url`, `nome`
- **Três datas:** nenhuma coluna da tabela traz estas datas
- **Histórico desde:** 2026-10-16 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ma/ligacao/partes.parquet` (servidor de casa, `scripts/carga_ma_assessorias.py`)
- **Linhagem:** O `.json` guarda as tabelas de entrada (com o hash de cada uma) e os arquivos da Receita usados; a página de cada parte está em `url`. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `assessoria` | Quem postou (`igc`) | texto |
| `url` | Endereço da página do negócio (liga com `ma_assessorias`) | texto |
| `nome` | O nome da empresa como a página escreve | texto |
| `papel` | alvo, comprador, vendedor ou outras_partes; vazio quando o negócio não tem papéis (dívida, fusão, joint venture, título sem verbo) | texto |
| `na_pagina` | cliente (a assessorada) ou contraparte: o campo da página em que o nome está | texto |
| `nome_normalizado` | O nome sem acento, caixa, forma jurídica no fim (S.A., Ltda...) e "Grupo": o que se compara | texto |
| `id_entidade` | A entidade da rede; para uma fechada que ainda não está na rede, o id que a rede dará à raiz dela. Vazio sem ligação ou na dúvida | texto |
| `cnpj_raiz` | Os 8 primeiros dígitos do CNPJ da empresa ligada | texto |
| `lei` | O LEI da entidade ligada, quando a rede tem | texto |
| `ligacao_por` | nome_exato (rede ou razão social), nome_fantasia, na_duvida (mais de um candidato, nome de uma palavra só fora da rede, ou nome fantasia que a razão social não tem), holding_estrangeira (CNPJ da dona de fora), aberto_depois_do_negocio (a matriz abriu depois do post) ou sem_ligacao | texto |
| `candidatos` | Quantas entidades têm esse nome (0 sem ligação, 1 ligada, 2 ou mais na dúvida) | número inteiro |

## `ma_negocios`

Uma linha por página de negócio de M&A com o `id_negocio`, o mesmo para as páginas do mesmo negócio em sites diferentes (as assessorias dos dois lados postam o mesmo negócio): mesmas partes, assessorias diferentes e tipos que não se contradizem. Série 5 do plano de M&A, passo 3 (ADR 0082)

- **Fonte:** `ma_assessorias` e `ma_partes`
- **Licença:** Posts públicos de assessorias de M&A: só fatos, sem texto (ADR 0082)
- **Revenda:** a confirmar (sem resposta escrita sobre uso comercial ou treino de ML: vale como não comercial até a resposta)
- **Frequência:** Semanal, junto da extração; versão nova só quando uma entrada muda
- **Atraso de divulgação:** O da tabela `ma_assessorias`
- **Módulo:** ma · **Contém dado de pessoa:** não
- **Chaves:** `assessoria`, `url`
- **Três datas:** nenhuma coluna da tabela traz estas datas
- **Histórico desde:** 2026-10-16 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ma/ligacao/negocios.parquet` (servidor de casa, `scripts/carga_ma_assessorias.py`)
- **Linhagem:** O `.json` guarda as tabelas de entrada com o hash de cada uma. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `assessoria` | Quem postou (`igc`) | texto |
| `url` | Endereço da página do negócio (liga com `ma_assessorias`) | texto |
| `id_negocio` | "N" + 20 hexadecimais do SHA-256 das partes (entidade ou nome normalizado); o de uma página quando as mesmas partes não podem ser juntadas | texto |
| `paginas_do_negocio` | Quantas páginas têm este `id_negocio` | número inteiro |
| `paginas_com_as_mesmas_partes` | Quantas páginas têm as mesmas partes, juntadas ou não (mais de uma do mesmo site são posts diferentes) | número inteiro |
| `duplicata_por` | partes_iguais quando o negócio está em mais de uma página; vazio se só em uma | texto |

## `ma_datas`

Quando cada negócio de M&A das assessorias ficou público, provado, e a confirmação por fonte oficial; uma linha por página (ADR 0082, série 5 do plano de M&A, passo 4). `conhecido_em` é a prova mais antiga guardada: a primeira cópia da página no Internet Archive, o arquivo de sócios do CNPJ em que a compradora aparece como sócia pessoa jurídica da alvo, ou a nossa primeira coleta. Nunca uma data contada: a entrada na sociedade é a do fechamento (`fechamento_em`) e não entra na conta

- **Fonte:** `ma_assessorias`, `ma_partes` e `ma_negocios`; a API CDX do Wayback Machine (só as datas das cópias) e os sócios pessoa jurídica do CNPJ aberto da Receita (raiz, raiz da sócia e data de entrada; nome, CPF e representante nunca são lidos)
- **Licença:** Internet Archive: 'for scholarship and research purposes only'; só datas
- **Revenda:** não comercial (uso pessoal, só pesquisa ou conta de estudante: só gabarito e pesquisa no PC; nunca em modelo, rótulo ou exportação)
- **Frequência:** Semanal, junto da extração; versão nova só quando uma entrada muda
- **Atraso de divulgação:** O da tabela `ma_assessorias`; a consulta ao Wayback roda na coleta de domingo, depois da página, e o CNPJ é o do mês mais recente guardado
- **Módulo:** ma · **Contém dado de pessoa:** não
- **Chaves:** `assessoria`, `url`
- **Três datas:** aconteceu_em = `fechamento_em`; publico_em = `conhecido_em`; coletado_em = `coletado_em`
- **Histórico desde:** 2026-10-16 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ma/datas/negocios.parquet` (servidor de casa, `scripts/carga_ma_assessorias.py`)
- **Linhagem:** Cada data aponta a prova: o endereço e o SHA-256 do original no acervo (a consulta do Wayback, o ZIP de sócios da Receita ou a página da assessoria). O `.json` guarda as tabelas e os originais de entrada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `assessoria` | Quem postou (`igc`) | texto |
| `url` | Endereço da página do negócio (liga com `ma_assessorias`) | texto |
| `id_negocio` | O negócio (liga com `ma_negocios`) | texto |
| `coletado_em` | Quando o arquivista baixou a página pela primeira vez | data e hora (UTC) |
| `wayback_em` | A cópia mais antiga da página no Wayback que respondeu 200; vazio se nenhuma | data e hora (UTC) |
| `wayback_copia` | Link da cópia no Wayback, para conferir à mão | texto |
| `wayback_consulta` | Endereço da consulta à API CDX guardada no acervo | texto |
| `wayback_sha256` | SHA-256 da resposta da consulta guardada | texto |
| `confirmado_por` | rfb-cnpj quando a compradora é sócia PJ da alvo no CNPJ; vazio sem confirmação | texto |
| `confirmacao_url` | Endereço do ZIP de sócios da Receita que confirma | texto |
| `confirmacao_sha256` | SHA-256 do ZIP guardado no acervo | texto |
| `confirmacao_em` | Quando o arquivista baixou esse ZIP | data e hora (UTC) |
| `fechamento_em` | Data de entrada da compradora na sociedade da alvo, como a Receita publica (a etapa de fechamento); se ela já era sócia antes, a da primeira entrada | data (dia) |
| `conhecido_em` | A prova mais antiga de que o negócio era público (nunca antes dela) | data e hora (UTC) |
| `conhecido_por` | wayback, rfb-cnpj ou coleta: de onde veio o `conhecido_em` | texto |
| `prova_url` | Endereço do original que prova o `conhecido_em` | texto |
| `prova_sha256` | SHA-256 desse original | texto |
| `conhecido_em_do_negocio` | O `conhecido_em` mais antigo entre as páginas do mesmo negócio | data e hora (UTC) |
| `conferencia` | confirmado (fonte oficial com a prova apontada) ou assessoria (só o post) | texto |

## `ma_regua`

Régua do middle market de cada negócio de M&A das assessorias: a receita anual da alvo no último exercício antes do negócio, entre R$ 30 e 500 milhões; uma linha por página (ADR 0082, item 2; série 5 do plano de M&A, passo 5). Só vale o que era público antes do `conhecido_em` do negócio (documento entregue no mesmo dia ou depois não entra). Sem receita conhecida, `desconhecido`: o valor nunca é estimado

- **Fonte:** `ma_datas` e `ma_partes`; a DRE anual da alvo na CVM (`demonstracoes_como_era`), as receitas lidas à mão em `base/conferidas/ma_receitas.csv` (nota de combinação de negócios da compradora, balanço publicado da alvo, faixa do CADE) e o porte do CNPJ aberto da Receita (só raiz e porte são lidos)
- **Licença:** Posts públicos de assessorias de M&A: só fatos, sem texto (ADR 0082)
- **Revenda:** a confirmar (sem resposta escrita sobre uso comercial ou treino de ML: vale como não comercial até a resposta)
- **Frequência:** Semanal, junto da extração; versão nova só quando uma entrada muda
- **Atraso de divulgação:** O da tabela `ma_datas`; a DRE é a já montada na base e o CNPJ é o do mês mais recente guardado
- **Módulo:** ma · **Contém dado de pessoa:** não
- **Chaves:** `assessoria`, `url`
- **Três datas:** aconteceu_em = `fechamento_em`; publico_em = `conhecido_em_do_negocio`
- **Histórico desde:** 2026-10-16 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/ma/regua/negocios.parquet` (servidor de casa, `scripts/carga_ma_assessorias.py`)
- **Linhagem:** Cada receita diz a fonte e o documento (a entrega à CVM, ou o endereço do documento lido à mão) e o dia em que ficou público; o porte aponta o ZIP da Receita no acervo (endereço e SHA-256). O `.json` guarda as tabelas e os originais de entrada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `assessoria` | Quem postou (`igc`) | texto |
| `url` | Endereço da página do negócio (liga com `ma_datas`) | texto |
| `id_negocio` | O negócio (liga com `ma_negocios`) | texto |
| `alvo_cnpj_raiz` | Raiz do CNPJ da alvo (vazio sem ligação ou com mais de uma alvo ligada) | texto |
| `conhecido_em_do_negocio` | O `conhecido_em` do negócio (`ma_datas`): o corte do que a régua pode usar | data e hora (UTC) |
| `fechamento_em` | Data do fechamento pelo CNPJ (`ma_datas`), quando há: o exercício é o de antes dela | data (dia) |
| `middle_market` | sim (receita de 30 a 500 milhões, limites inclusos), nao ou desconhecido | texto |
| `motivo` | receita, porte_me_epp, sem_receita (alvo com CNPJ sem receita pública antes), alvo_sem_cnpj ou varias_alvos | texto |
| `receita` | Receita anual da alvo; vazio quando não há documento | reais (R$), já multiplicado pela escala informada |
| `receita_exercicio_fim` | Fim do exercício dessa receita | data (dia) |
| `receita_fonte` | cpc15-compradora, dfp-alvo, balanco-alvo ou cade (no mesmo exercício, nessa ordem) | texto |
| `receita_documento` | O documento: a entrega à CVM (tipo, CNPJ, referência, versão e grupo) ou o endereço | texto |
| `receita_documento_sha256` | SHA-256 do documento no acervo, quando guardado | texto |
| `receita_publico_em` | Dia em que o documento ficou público | data (dia) |
| `porte` | Porte da alvo no CNPJ baixado antes do negócio (01 ME, 03 EPP, 05 demais, 00 não informado); vazio se o arquivo é de depois | texto |
| `porte_publico_em` | Quando o arquivista baixou esse ZIP | data e hora (UTC) |
| `porte_prova_url` | Endereço do ZIP `Empresas` da Receita | texto |
| `porte_prova_sha256` | SHA-256 do ZIP guardado no acervo | texto |

## `cftc_cot_agro`

Posição dos fundos e dos produtores nos futuros de café (Coffee C), açúcar, soja, milho, boi gordo e algodão, por semana, desde 2006, no formato do relatório Disaggregated da CFTC

- **Fonte:** CFTC: Commitments of Traders, Disaggregated Futures Only (fut_disagg_txt)
- **Licença:** Obra do governo dos EUA (17 U.S.C. §105; citar a CFTC)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Semanal (posição de terça-feira)
- **Atraso de divulgação:** Divulgado na sexta-feira; a base conta a segunda-feira seguinte, 15h30 de Nova York (regra conservadora do `base/commodities/cftc_cot.py`, com as exceções das paralisações do governo dos EUA em 2018-19 e 2025). `disponivel_em` é o dia seguinte à divulgação
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `relatorio`, `contrato`
- **Três datas:** aconteceu_em = `relatorio`; publico_em = `disponivel_em`
- **Histórico desde:** 2006-06-13 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por ano em `<acervo>/base/setoriais/cftc/<ano>.parquet` (`scripts/carga_setoriais.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 dos zips da CFTC usados (o histórico de 2006 a 2016 e um zip por ano desde 2017) e a versão do código.

| Coluna | O que é | Unidade |
|---|---|---|
| `relatorio` | Terça-feira a que a posição se refere | data (dia) |
| `contrato` | cafe-arabica, acucar, soja, milho, boi-gordo ou algodao | texto |
| `open_interest` | Contratos em aberto no mercado, total | número com decimais, na unidade da fonte |
| `producer_merchant_long` | Produtores e comerciantes: contratos comprados | número com decimais, na unidade da fonte |
| `producer_merchant_short` | Produtores e comerciantes: contratos vendidos | número com decimais, na unidade da fonte |
| `swap_long` | Operadores de swap: contratos comprados | número com decimais, na unidade da fonte |
| `swap_short` | Operadores de swap: contratos vendidos | número com decimais, na unidade da fonte |
| `swap_spread` | Operadores de swap: posições em spread | número com decimais, na unidade da fonte |
| `managed_money_long` | Fundos (managed money): contratos comprados | número com decimais, na unidade da fonte |
| `managed_money_short` | Fundos (managed money): contratos vendidos | número com decimais, na unidade da fonte |
| `managed_money_spread` | Fundos (managed money): posições em spread | número com decimais, na unidade da fonte |
| `disponivel_em` | Desde quando o número era público (dia seguinte à divulgação) | data (dia) |

## `conab_cafe`

Os levantamentos de safra de café da CONAB, como publicados: por safra, levantamento (1 a 4), tipo (arábica, conilon, total) e UF, a área em formação e em produção, a produtividade e a produção em mil sacas. Cada levantamento é uma linha a mais, nunca sobrescreve o anterior. Em tela e API citando a CONAB e a data do levantamento (ADR 0102; licença CC BY-ND 3.0 registrada na marca)

- **Fonte:** CONAB: Acompanhamento da Safra Brasileira de Café (planilha de cada levantamento)
- **Licença:** CC BY-ND 3.0 (CONAB): uso citando a CONAB e a data do levantamento (ADR 0102)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Frequência:** Quatro levantamentos por safra (jan/fev, mai, set e dez), coletados pelo arquivista
- **Atraso de divulgação:** O número vale a partir de `divulgado_em`, o dia em que a CONAB publicou o levantamento
- **Módulo:** macro · **Contém dado de pessoa:** não
- **Chaves:** `safra`, `levantamento`, `tipo`, `uf`, `divulgado_em`
- **Três datas:** publico_em = `divulgado_em`
- **Histórico desde:** 2026-02-05 (`publico_em` por dia)
- **Versão do contrato:** 1.1.0
- **Onde fica:** Parquet em `<acervo>/base/commodities/conab_cafe/` (`scripts/carga_cafe.py`; leitor `base/commodities/conab_cafe.py`)
- **Linhagem:** A planilha original fica no acervo do arquivista (fonte `conab-cafe-safra`), com data da coleta e SHA-256; o dia da divulgação vem do 'Publicado em' da página do levantamento (fonte `conab-cafe-publicacao`). `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

| Coluna | O que é | Unidade |
|---|---|---|
| `safra` | Ano em que a safra começa (2026 é a safra 2026/27) | número inteiro |
| `levantamento` | Número do levantamento da safra, de 1 a 4 | número inteiro |
| `tipo` | `arabica`, `conilon` ou `total` | texto |
| `uf` | Sigla da UF, `OUTROS` (agrupamento da CONAB) ou `BRASIL` | texto |
| `area_formacao_ha` | Área em formação, em hectares | número com decimais, na unidade da fonte |
| `area_producao_ha` | Área em produção, em hectares | número com decimais, na unidade da fonte |
| `produtividade_sc_ha` | Produtividade, em sacas de 60 kg por hectare | número com decimais, na unidade da fonte |
| `producao_mil_sacas` | Produção, em mil sacas de 60 kg | número com decimais, na unidade da fonte |
| `divulgado_em` | Dia em que a CONAB divulgou o levantamento | data (dia) |
| `divulgado_aproximado` | Verdadeiro quando a data da CONAB não foi achada e `divulgado_em` é o dia da coleta | verdadeiro ou falso |

## `usda_psd_cafe`

Balanço mundial do café por país e ano-safra (produção, consumo, estoques, exportação, importação), em mil sacas de 60 kg, do USDA PSD. Só a produção se separa por tipo (arabica, conilon = a Robusta do USDA); os demais atributos são do `total`. Cada baixada semanal guarda as revisões do USDA com a data em que apareceram, para o 'como era na data'

- **Fonte:** USDA FAS, PSD Online: Coffee (psd_coffee_csv.zip)
- **Licença:** Domínio público do USDA (citar o USDA FAS, PSD Online); no data.gov consta CC BY
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Semanal (o USDA revisa o café em junho e dezembro, com ajustes no meio)
- **Atraso de divulgação:** `divulgado_em` é o fim do mês da revisão que o USDA informa na linha (no máximo o dia da baixada); o CSV só traz a versão mais recente de cada número, então o passado vem das baixadas guardadas pelo arquivista
- **Módulo:** macro · **Contém dado de pessoa:** não
- **Chaves:** `codigo_do_pais`, `ano_safra`, `atributo`, `tipo`, `divulgado_em`
- **Três datas:** aconteceu_em = `divulgado_em`; publico_em = `divulgado_em`
- **Histórico desde:** 2026-10-18 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/commodities/usda_psd/<dia da baixada>.parquet`
- **Linhagem:** Cada parquet nasce de um `psd_coffee_csv.zip` guardado pelo arquivista (SHA-256 no registro de coletas); a unidade da fonte é conferida (mil sacas de 60 kg) e uma unidade diferente interrompe a leitura.

| Coluna | O que é | Unidade |
|---|---|---|
| `codigo_do_pais` | Código do país no USDA (ex.: BR) | texto |
| `pais` | Nome do país, como o USDA escreve | texto |
| `ano_safra` | Ano de início da safra comercial (2024 = 2024/25) | número inteiro |
| `atributo` | Produção, consumo, estoque final, exportação... | texto |
| `tipo` | arabica, conilon ou total | texto |
| `valor` | Valor em mil sacas de 60 kg | número com decimais, na unidade da fonte |
| `unidade` | Unidade da fonte, conferida na leitura | texto |
| `divulgado_em` | Quando a revisão ficou pública (fim do mês da revisão) | data (dia) |

## `faostat_cafe`

Café verde por país e ano da FAO (FAOSTAT): produção em toneladas, área colhida em hectares e rendimento em kg por hectare, desde 1961. O FAOSTAT não separa arábica de robusta (`tipo` é sempre `total`; a separação por tipo está no `usda_psd_cafe`). Cada baixada semanal guarda a fotografia do dia, para o 'como era na data'

- **Fonte:** FAO, FAOSTAT: Crops and livestock products (Production_Crops_Livestock_E_All_Data_(Normalized).zip)
- **Licença:** CC BY 4.0 (FAO; crédito no formato da FAO e sem sugerir aval da FAO)
- **Revenda:** vendável com atribuição à fonte
- **Frequência:** Semanal (a FAO atualiza a base algumas vezes por ano)
- **Atraso de divulgação:** A FAO não informa a data de cada revisão: `divulgado_em` é o dia da baixada que o arquivista guardou, então um número nunca aparece antes de ter sido visto
- **Módulo:** macro · **Contém dado de pessoa:** não
- **Chaves:** `codigo_do_pais`, `ano`, `elemento`, `divulgado_em`
- **Três datas:** aconteceu_em = `divulgado_em`; publico_em = `divulgado_em`
- **Histórico desde:** 2026-10-19 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/commodities/faostat_cafe/<dia da baixada>.parquet`
- **Linhagem:** Cada parquet nasce de um zip guardado pelo arquivista (SHA-256 no registro de coletas); só entram o café verde dos países (os agregados da FAO saem), a unidade da fonte é conferida (hg/ha vira kg/ha) e uma unidade desconhecida interrompe a leitura. Crédito: FAO, FAOSTAT, CC BY 4.0.

| Coluna | O que é | Unidade |
|---|---|---|
| `codigo_do_pais` | Código M49 do país (ex.: 076 para o Brasil) | texto |
| `pais` | Nome do país, como a FAO escreve | texto |
| `ano` | Ano civil da produção | número inteiro |
| `elemento` | producao, area_colhida ou rendimento | texto |
| `tipo` | Sempre total: o FAOSTAT não separa arábica de robusta | texto |
| `valor` | Valor na unidade da coluna `unidade` | número com decimais, na unidade da fonte |
| `unidade` | t, ha ou kg/ha | texto |
| `sinalizador` | Sinalizador da FAO (A oficial, E estimado, I imputado...) | texto |
| `divulgado_em` | Dia da baixada que trouxe este número | data (dia) |

## `clima_regiao_cafe`

Clima do mês por região produtora de café (13 regiões de `src/commodities/cafe/regioes.py`): chuva acumulada, Tmín média, dias com Tmín abaixo de 2 °C e Tmáx média, com a normal de 1991–2020 e a anomalia. Duas fontes, uma por linha: as estações automáticas do INMET (`inmet`; `n_estacoes` diz quantas valeram) e a chuva por satélite do CHIRPS (`chirps`; só chuva, média dos municípios ponderada pela área de café da PAM) e, depois de dez/2026, a ponte `chirps-v3-rnl` (CHIRPS v3 `rnl`, outra série: nunca somada à v2 e com normal própria). Região com menos de 3 estações válidas no mês fica com os valores vazios, nunca zero

- **Fonte:** INMET: dados históricos das estações automáticas (BDMEP), um zip por ano; CHIRPS v2.0 (UCSB): GeoTIFF mensal global; CHIRPS v3 `rnl` diário (cópia de terceiro no Hugging Face, CC BY 4.0; soma do mês feita por nós); IBGE: malha municipal (API de malhas)
- **Licença:** Dados históricos do INMET: públicos e gratuitos, sem licença escrita (citar)
- **Revenda:** vendável com atribuição à fonte
- **Ressalva de revenda:** As linhas `chirps` são do CHIRPS v2.0 (domínio público; citar Funk et al. 2015); as linhas `chirps-v3-rnl` são do CHIRPS v3 `rnl` (sabor ERA5, não o `sat`), cópia de terceiro no Hugging Face sob CC BY 4.0 (citar Funk et al. e o autor da cópia); a malha é do IBGE
- **Frequência:** Mensal
- **Atraso de divulgação:** Mensal; a regra de "como era na data" usa o fim do mês + 45 dias para o INMET e + 60 dias para o CHIRPS (folga conservadora, não medida: conferir com as baixadas do arquivista)
- **Módulo:** macro · **Contém dado de pessoa:** não
- **Chaves:** `regiao`, `competencia`, `fonte`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 1981-01-31 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet por ano em `<acervo>/base/commodities/clima_regiao_cafe/<ano>.parquet` (a carga segue o molde de `scripts/carga_setoriais.py`)
- **Linhagem:** O `<ano>.json` guarda o endereço e o SHA-256 dos zips do INMET, dos GeoTIFFs do CHIRPS e da malha usados e a versão do código; `fonte` diz de qual fonte veio a linha. A normal do CHIRPS (v2.0, média de 1991–2020 por região e mês do ano, 30 anos) é calculada na carga e fica no Parquet; a data da conta é a da versão gravada. **Sem olhar o futuro:** vale para os meses (cada `chuva_mm` só usa o que a fonte tinha na `disponivel_em`), não para a normal: ela é fixa, só muda se o período de referência mudar (e o que chega depois de 2020 não a altera). Para os meses de 1991–2020 a anomalia é contra uma normal que inclui anos posteriores a eles: serve para descrever, não para simular uma decisão da época

| Coluna | O que é | Unidade |
|---|---|---|
| `regiao` | Id da região produtora (`src/commodities/cafe/regioes.py`) | texto |
| `competencia` | Mês (último dia) | data (dia) |
| `fonte` | inmet, chirps (v2) ou chirps-v3-rnl | texto |
| `chuva_mm` | Chuva acumulada no mês (média das estações, ou do satélite) | mm |
| `tmin_media_c` | Média das temperaturas mínimas diárias (vazio no chirps) | °C |
| `dias_tmin_abaixo_de_2c` | Dias do mês com Tmín abaixo de 2 °C (média das estações; vazio no chirps) | dias |
| `tmax_media_c` | Média das temperaturas máximas diárias (vazio no chirps) | °C |
| `n_estacoes` | Estações válidas no mês (80% dos dias com 20 horas de leitura); vazio no chirps | número inteiro |
| `chuva_normal_mm` | Normal 1991–2020 da chuva do mês do ano (10 anos no mínimo) | mm |
| `chuva_anomalia_mm` | chuva_mm menos a normal | mm |
| `tmin_normal_c` | Normal 1991–2020 da Tmín média | °C |
| `tmin_anomalia_c` | tmin_media_c menos a normal | °C |
| `tmax_normal_c` | Normal 1991–2020 da Tmáx média | °C |
| `tmax_anomalia_c` | tmax_media_c menos a normal | °C |
| `anos_na_normal` | Anos que entraram na normal (vazio quando menos de 10) | número inteiro |
| `disponivel_em` | Desde quando o número era público (fim do mês + a folga da fonte) | data (dia) |

## `area_cafe_municipio`

Área e produção de café por município e ano, pela PAM do IBGE e pela cobertura de café do MapBiomas, lado a lado. A PAM traz a área colhida (hectares) e a quantidade produzida (toneladas) por tipo: arábica, conilon e o total quando os dois têm número. O MapBiomas traz os hectares de lavoura de café vistos por satélite (classe 46, soma dos biomas do município). Medem coisas diferentes (colhida contra plantada visível) e nunca se somam; coluna sem número fica vazia, nunca zero

- **Fonte:** IBGE: PAM, tabela 1613 do SIDRA (variáveis 216 e 214, café arábica e canephora, por município); MapBiomas: Coleção 11, planilha de cobertura por bioma, estado e município
- **Licença:** MapBiomas Coleção 11: CC BY-SA (citar Souza et al. 2020)
- **Revenda:** vendável com atribuição à fonte, risco assumido pelo Tiago (ADR 0122, 05/11/2026): sem resposta escrita sobre uso comercial
- **Ressalva de revenda:** As colunas da PAM são do IBGE (domínio público; citar o IBGE); a coluna do MapBiomas é CC BY-SA (citar o projeto MapBiomas, Souza et al. 2020; revenda a confirmar)
- **Frequência:** Anual
- **Atraso de divulgação:** Anual; a regra de "como era na data" usa 31/10 do ano seguinte, quando a PAM já saiu (setembro ou outubro); a coleção do MapBiomas sai uma vez por ano com todos os anos refeitos
- **Módulo:** macro · **Contém dado de pessoa:** não
- **Chaves:** `codigo`, `ano`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `disponivel_em`
- **Histórico desde:** 1985-12-31 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet único em `<acervo>/base/commodities/area_cafe_municipio/municipios.parquet` (a carga segue o molde de `scripts/carga_setoriais.py`)
- **Linhagem:** O `municipios.json` guarda o endereço e o SHA-256 da resposta do SIDRA e do zip do MapBiomas (com a coleção), e a versão do código

| Coluna | O que é | Unidade |
|---|---|---|
| `codigo` | Código do município no IBGE (7 dígitos) | texto |
| `nome` | Nome do município (PAM); vazio quando só o MapBiomas tem o município | texto |
| `uf` | Sigla da UF | texto |
| `ano` | Ano da safra (PAM) ou do mapa (MapBiomas) | ano |
| `referencia` | Último dia do ano | data (dia) |
| `area_arabica_ha` | Área colhida de café arábica (PAM) | hectares |
| `area_conilon_ha` | Área colhida de café canephora/conilon (PAM) | hectares |
| `area_total_ha` | Arábica + conilon, só quando os dois têm número | hectares |
| `producao_arabica_t` | Quantidade produzida de arábica (PAM) | toneladas |
| `producao_conilon_t` | Quantidade produzida de canephora/conilon (PAM) | toneladas |
| `producao_total_t` | Arábica + conilon, só quando os dois têm número | toneladas |
| `area_mapbiomas_ha` | Cobertura da classe Café do MapBiomas no município (soma dos biomas) | hectares |
| `disponivel_em` | Desde quando o número era público (31/10 do ano seguinte, pela PAM) | data (dia) |

## `contraparte_cafe`

Tabela conferida à mão: fatos públicos e datados das cooperativas e tradings de café (faturamento, sobras, sacas recebidas, pedido de recuperação judicial, apuração pública), cada um com fonte, veículo e data, ditos com as nossas palavras. Sem nota, cor nem conselho e sem pessoa física: a ficha (`base/contrapartes/cafe.py`) junta a situação especial da Receita e os informes de CRA da CVM e diz o que não sabemos

- **Fonte:** Notícias e documentos públicos (ALMG, Bloomberg Línea, Revista Cultivar, Notícias Agrícolas, Compre Rural, AgFeed, Brazil Journal)
- **Licença:** Página guardada só como prova; na ficha, fato e link (ADR 0102)
- **Revenda:** a confirmar (sem resposta escrita sobre uso comercial ou treino de ML: vale como não comercial até a resposta)
- **Frequência:** Quando a conferência anda (assembleias de março, notícias de recuperação judicial)
- **Atraso de divulgação:** O `divulgado_em` é o dia da publicação da notícia ou do documento
- **Módulo:** macro · **Contém dado de pessoa:** não
- **Chaves:** `id`, `fato`, `data`
- **Três datas:** aconteceu_em = `data`; publico_em = `divulgado_em`; coletado_em = `conferido_em`
- **Histórico desde:** 2004-07-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** `base/conferidas/contrapartes_cafe.csv` no repositório (Git)
- **Linhagem:** Cada linha diz a fonte, o veículo e quando foi conferida (`fonte`, `conferido_em`); as páginas de todas as fontes ficam guardadas pelo arquivista (`contrapartes-cafe`) só como prova, nunca mostradas (ADR 0102); a notícia de recuperação judicial ou fechamento só vira fato da ficha depois de guardada (antes, fica em 'o que não sabemos'); o histórico de cada mudança fica no Git.

| Coluna | O que é | Unidade |
|---|---|---|
| `id` | Apelido da contraparte (chave quando não há CNPJ conferido) | texto |
| `cnpj` | CNPJ da entidade no cadastro aberto da Receita (vazio: não confirmado) | texto |
| `nome` | Nome da cooperativa ou empresa | texto |
| `tipo` | `cooperativa`, `trading` ou `exportadora` | texto |
| `uf` | UF da sede | texto |
| `fato` | Tipo do fato (`faturamento`, `pedido_de_recuperacao_judicial`...) | texto |
| `descricao` | O fato com as nossas palavras, "segundo <veículo>" | texto |
| `valor` | O número do fato, na unidade ao lado (vazio se não há) | número com decimais, na unidade da fonte |
| `unidade` | `R$`, `sacas` ou outra | texto |
| `data` | Quando o fato aconteceu (fim do exercício, dia do pedido) | data (dia) |
| `divulgado_em` | Quando ficou público (sem olhar o futuro) | data (dia) |
| `fonte` | Endereço público da notícia ou do documento | texto |
| `veiculo` | Quem publicou | texto |
| `tipo_de_fonte` | `documento_oficial`, `demonstracao_financeira`, `relatorio_da_entidade` ou `noticia` | texto |
| `conferido_em` | Dia da conferência | data (dia) |
