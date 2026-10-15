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
- **Linhagem:** `cnpj`, `documento`, `referencia` e `versao` dizem qual entrega à CVM publicou o valor; `origem` diz se veio dos dados abertos ou do XML do ENET. Ao lado de cada Parquet, `<ano>.json` guarda o SHA-256 da base e o endereço e o SHA-256 de cada original, que está no acervo e no registro de coletas (com a data da coleta), e a `versao_do_codigo` (o commit que montou o ano; os anos montados antes da série 3 ficam sem ela até serem remontados). `base/linhagem.py` refaz o caminho de qualquer linha e diz se está completo.

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

Cada código de ação da B3 (bolsa) com a empresa e o período em que existiu, juntando todos os anos do formulário cadastral (FCA): código que sumiu continua aqui. Os códigos que a empresa informa fora do formato (o BTG põe "000000" nas units) entram pela tabela conferida, válidos do 1º ao último mês em que aparecem nas carteiras dos fundos

- **Fonte:** CVM: formulário cadastral (FCA), valores mobiliários
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual (o FCA é entregue até 31/05) e a cada alteração
- **Atraso de divulgação:** Até meses: a empresa atualiza o FCA quando muda algo
- **Onde fica:** Parquet em `<acervo>/base/fca/tickers.parquet` (servidor de casa, `scripts/carga_fca.py`); a função é `base/cadastro.py::tickers_no_tempo`
- **Linhagem:** Montada dos zips do FCA de todos os anos, guardados no acervo e no registro de coletas (com SHA-256 e data da coleta); `primeiro_visto` e `ultimo_visto` dizem de qual FCA veio cada código. O `.json` ao lado do Parquet guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada FCA usado (no acervo e no registro de coletas, fonte `cvm-fca`, com a data da coleta e a versão do código que baixou) e a versão do código que gravou a tabela. As linhas com `origem` = códigos conferidos vêm da tabela conferida, que entra nas origens do `.json` pelo caminho no repositório e o SHA-256 (`base/linhagem.py` confere o arquivo).

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
| `origem` | fca (informado no formulário) ou códigos conferidos (tabela `base/conferidas/codigos_fora_do_fca.csv`: o código veio fora do formato no FCA) | texto |

## `valores_mobiliarios`

Todos os valores mobiliários de cada companhia em cada FCA (ações, units, BDRs, debêntures, notas comerciais...), na versão mais nova de cada documento. Base do código permanente da ação (série 3). Até 2017 o FCA não traz o código de negociação

- **Fonte:** CVM: formulário cadastral (FCA), valores mobiliários
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual (o FCA é entregue até 31/05) e a cada alteração; a carga relê todos os anos
- **Atraso de divulgação:** Até meses: a empresa atualiza o FCA quando muda algo; sem ticker até 2017
- **Onde fica:** Parquet em `<acervo>/base/fca/` (servidor de casa, `scripts/carga_fca.py`)
- **Linhagem:** `cnpj`, `referencia` e `versao` dizem de qual FCA veio a linha. O `.json` ao lado do Parquet guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada FCA usado (no acervo e no registro de coletas, fonte `cvm-fca`, com a data da coleta e a versão do código que baixou) e a versão do código que gravou a tabela.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `referencia` | Data de referência do FCA | data (dia) |
| `versao` | Versão do documento (fica a mais nova) | número inteiro |
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

## `emissores`

Emissor (as 4 letras do ticker e do ISIN: PETR) → CNPJ, com o primeiro e o último ano do FCA em que apareceu. É a ligação do ISIN das carteiras dos fundos (CDA) com a empresa. Um emissor com mais de um CNPJ é conflito e fica sem resposta

- **Fonte:** CVM: formulário cadastral (FCA), derivado de `valores_mobiliarios`
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual (o FCA é entregue até 31/05) e a cada alteração; a carga relê todos os anos
- **Atraso de divulgação:** Até meses: a empresa atualiza o FCA quando muda algo; sem ticker até 2017
- **Onde fica:** Parquet em `<acervo>/base/fca/` (servidor de casa, `scripts/carga_fca.py`)
- **Linhagem:** Derivada de `valores_mobiliarios` na mesma carga. O `.json` ao lado do Parquet guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada FCA usado (no acervo e no registro de coletas, fonte `cvm-fca`, com a data da coleta e a versão do código que baixou) e a versão do código que gravou a tabela. As linhas com `origem` = códigos conferidos vêm da tabela conferida, que entra nas origens do `.json` pelo caminho no repositório e o SHA-256 (`base/linhagem.py` confere o arquivo).

| Coluna | O que é | Unidade |
|---|---|---|
| `emissor` | As 4 letras do emissor | texto |
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `primeiro_ano` | Ano do primeiro FCA com o emissor | número inteiro |
| `ultimo_ano` | Ano do último FCA com o emissor | número inteiro |
| `conflito` | Verdadeiro se o emissor aparece com mais de um CNPJ | verdadeiro ou falso |
| `origem` | fca (informado no formulário) ou códigos conferidos (tabela `base/conferidas/codigos_fora_do_fca.csv`: o código veio fora do formato no FCA) | texto |

## `codigos_invalidos`

Códigos de negociação informados fora do formato de ticker (a CSN informa "4030"): não viram ligação e vão para o relatório de buracos; os da bolsa que aparecem nas carteiras dos fundos são conferidos um a um e entram em `codigos_fora_do_fca`

- **Fonte:** CVM: formulário cadastral (FCA), derivado de `valores_mobiliarios`
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Anual (o FCA é entregue até 31/05) e a cada alteração; a carga relê todos os anos
- **Atraso de divulgação:** Até meses: a empresa atualiza o FCA quando muda algo; sem ticker até 2017
- **Onde fica:** Parquet em `<acervo>/base/fca/` (servidor de casa, `scripts/carga_fca.py`)
- **Linhagem:** Derivada de `valores_mobiliarios` na mesma carga. O `.json` ao lado do Parquet guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada FCA usado (no acervo e no registro de coletas, fonte `cvm-fca`, com a data da coleta e a versão do código que baixou) e a versão do código que gravou a tabela.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `referencia` | Data de referência do FCA | data (dia) |
| `valor_mobiliario` | Tipo do papel, como a empresa informa | texto |
| `codigo_informado` | O código como a empresa escreveu | texto |

## `carteiras_dos_fundos`

As posições em ações de todos os fundos registrados na CVM, por mês, desde 2005 (CDA, bloco de ações): comprado, emprestado e vendido, com o ISIN e o emissor. Fundos e posições que saíram continuam (sem viés de sobrevivência). Um Parquet por ano; quando a CVM regrava um ano, a versão anterior fica como `<ano>.v<N>`

- **Fonte:** CVM: composição e diversificação das aplicações dos fundos (CDA), bloco 4
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal; de 2005 a 2022 um arquivo por ano, de 2023 em diante um por mês
- **Atraso de divulgação:** O arquivo sai uns 40 dias depois do mês e o fundo pode deixar uma posição em sigilo por até 90 dias: `disponivel_em` usa competência + 90 dias, ou o fim do sigilo se depois
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
| `disponivel_em` | Desde quando a posição era pública (como era na data) | data (dia) |

## `fidc_informe`

O informe mensal de cada FIDC desde 2013, um Parquet por quadro (`tab_I` a `tab_X_7`) e por ano, no formato da fonte: carteira, prazos, inadimplência por faixa, pré-pagamento, recompras, cedentes. As colunas mudam com os anos (15 quadros em 2013, 18 em 2026) e são as do dicionário da CVM (`meta_inf_mensal_fidc.txt`); a base acrescenta as três abaixo. Sem dado pessoal: dos documentos de cedentes só fica CNPJ válido (CPF vira vazio)

- **Fonte:** CVM: informe mensal de FIDC
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal; de 2013 a 2024 um arquivo por ano, de 2025 em diante um por mês
- **Atraso de divulgação:** Entregue em até 15 dias; a CVM regrava meses passados (cada regravação vira versão `<ano>.v<N>`). `disponivel_em` usa competência + 45 dias
- **Onde fica:** Parquet em `<acervo>/base/fidc/informe/<quadro>/<ano>.parquet` (servidor de casa, `scripts/carga_fidc.py`)
- **Linhagem:** O `<ano>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada arquivo do informe usado (no acervo e no registro de coletas, com a data da coleta e a versão do código que baixou) e a versão do código que gravou.

| Coluna | O que é | Unidade |
|---|---|---|
| `competencia` | Mês do informe (último dia) | data (dia) |
| `cnpj_fundo` | CNPJ do fundo (ou da classe, depois da CVM 175) | texto |
| `disponivel_em` | Desde quando o informe era público (como era na data) | data (dia) |

## `cadastro_de_fundos`

O cadastro de fundos da CVM (atual, histórico de administrador, auditor, classe... e o registro de fundos e classes da CVM 175), com o gestor de cada FIDC: a lista de clientes possíveis do Capital. Fundos cancelados continuam. Sem dado pessoal: o diretor responsável e o histórico dele ficam fora; o gestor pessoa física fica só com a marca PF

- **Fonte:** CVM: cadastro de fundos (`cad_fi.csv`, `cad_fi_hist.zip`, `registro_fundo_classe.zip`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária na CVM; a base guarda um retrato a cada carga (versões `<nome>.v<N>`)
- **Atraso de divulgação:** Do dia: é um retrato do cadastro na data da coleta; o histórico vem de `cad_fi_hist`
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

## `painel_dos_fundos`

Quem tinha cada empresa em cada mês desde 2005: as posições dos fundos (CDA) somadas por mês e tipo (comprado, emprestado, vendido), em duas versões: por emissor (sempre) e por empresa (CNPJ). O emissor vira CNPJ pelo FCA e, no que falta (empresas que saíram antes de 2018), pela tabela conferida `base/conferidas/emissores_antigos.csv`; cada ano tem pelo menos 95% do valor comprado com CNPJ (`cobertura`), e o resto está em `buracos`. Inclui empresas que saíram da bolsa (sem viés de sobrevivência)

- **Fonte:** Derivado: CVM, CDA (posições) e FCA (emissores), mais a tabela conferida
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal, montado de novo quando o CDA ou o FCA mudam
- **Atraso de divulgação:** O do CDA: `disponivel_em` é a maior data das posições somadas (o total só era público quando a última posição dele ficou pública)
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

## `cobertura_dos_fundos`

Por mês desde 2005, quanto do valor comprado pelos fundos chega a um CNPJ de empresa pela ligação do painel (a meta da tabela conferida é 95% em cada ano)

- **Fonte:** Derivado: CVM, CDA (posições) e FCA (emissores), mais as tabelas conferidas
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal, montada junto com o painel dos fundos
- **Atraso de divulgação:** O do CDA (os meses mais novos ainda crescem enquanto os fundos entregam)
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
- **Onde fica:** Parquet em `<acervo>/base/fundos/buracos.parquet` (`scripts/montar_painel_dos_fundos.py`)
- **Linhagem:** O `.json` lista as tabelas de entrada (cada ano do CDA e os emissores do FCA, com o SHA-256 do conteúdo) e o SHA-256 da tabela conferida; guarda a versão do código. `base/linhagem.py::linhagem_da_tabela` segue cada tabela de entrada pelo manifesto dela até os originais; se uma entrada foi regravada depois, a derivada não confere até ser remontada.

| Coluna | O que é | Unidade |
|---|---|---|
| `emissor` | As 4 posições do emissor sem CNPJ | texto |
| `valor` | Valor comprado somado em todos os meses | reais (R$), já multiplicado pela escala informada |
| `primeira` | Primeiro mês em que aparece | data (dia) |
| `ultima` | Último mês em que aparece | data (dia) |
| `descricao` | Descrição do ativo no CDA (a pista para a conferência) | texto |

## `emissores_antigos`

Tabela conferida à mão: emissores das carteiras dos fundos que saíram da bolsa ou mudaram de código antes de 2018 (e a CSN, que informa "4030"), ligados ao CNPJ pelo cadastro de companhias da CVM, um a um, sem casar nome aproximado

- **Fonte:** CVM: cadastro de companhias (`cad_cia_aberta.csv`) e descrição do ativo no CDA
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Quando a conferência anda (pelos buracos de maior valor)
- **Atraso de divulgação:** Nenhum: a ligação vale para o período em que o emissor aparece nas carteiras
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

## `ifdata_valores`

Balanço, resultado, capital, segmentação e carteira de crédito de cada banco e conglomerado, por trimestre desde 2000, no formato longo da fonte (uma linha por instituição, relatório, conta e coluna). Tipo 1 = conglomerado prudencial (desde mar/2014), 2 = conglomerado financeiro, 3 = instituição individual. Ficam fora o relatório 15 (câmbio) e as linhas de total sem código de instituição

- **Fonte:** Banco Central: IF.data (API Olinda, `IfDataValores`)
- **Licença:** ODbL (dados abertos do Banco Central; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Trimestral (data-base em mar, jun, set e dez)
- **Atraso de divulgação:** Jun/2026 estava publicado em 14/10 (106 dias); `disponivel_em` usa data-base + 120 dias. O BC revisa: as 8 datas mais novas são baixadas de novo a cada carga e cada revisão vira versão `<AAAAMM>.v<N>`
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
| `disponivel_em` | Desde quando o número era público (como era na data) | data (dia) |

## `ifdata_cadastro`

O cadastro de cada data-base do IF.data: nome, tipo de controle, segmento, cidade, conglomerados e CNPJ do líder de cada instituição e conglomerado, com a raiz do CNPJ que liga à bolsa

- **Fonte:** Banco Central: IF.data (API Olinda, `IfDataCadastro`)
- **Licença:** ODbL (dados abertos do Banco Central; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Trimestral, junto com os valores
- **Atraso de divulgação:** O dos valores (o cadastro sai com a data-base)
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

## `ligacao_dos_bancos`

Instituição do IF.data → CNPJ da empresa da bolsa → tickers que valiam no ano, por data-base. A instituição cujo código é o CNPJ de uma empresa do FCA liga por ele (o Banco PAN, do conglomerado do BTG, tem ação própria); as outras, pela raiz do CNPJ do líder do conglomerado. Antes de 2010 (sem FCA) a ligação chega ao CNPJ, mas não à ação. Instituição sem ação (Caixa, BNDES) fica sem CNPJ

- **Fonte:** Derivado: IF.data (cadastro) e CVM, FCA (emissores e tickers)
- **Licença:** ODbL (dados abertos do Banco Central; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Trimestral, montada de novo a cada carga
- **Atraso de divulgação:** O do cadastro do IF.data
- **Onde fica:** Parquet em `<acervo>/base/bcb/ifdata/ligacao_dos_bancos.parquet` (servidor de casa)
- **Linhagem:** O `.json` lista cada cadastro e as tabelas do FCA usados, com o SHA-256 de cada arquivo, e a versão do código. `base/linhagem.py::linhagem_da_tabela` segue cada tabela de entrada pelo manifesto dela até os originais; se uma entrada foi regravada depois, a derivada não confere até ser remontada.

| Coluna | O que é | Unidade |
|---|---|---|
| `data_base` | Data-base do cadastro | data (dia) |
| `cod_inst` | Código da instituição no BC | texto |
| `instituicao` | Nome da instituição | texto |
| `cnpj_raiz` | Raiz do CNPJ (8 dígitos) | texto |
| `cnpj` | CNPJ da empresa da bolsa (vazio se não tem ação) | texto |
| `tickers` | Códigos que valiam no ano, separados por vírgula | texto |
| `ligado_por` | próprio CNPJ (a instituição é a empresa da bolsa, como o Banco PAN) ou líder do conglomerado; vazio sem ligação | texto |

## `scr_credito`

Carteira de crédito do sistema financeiro por mês desde jul/2012 (SCR.data versão 2): por UF, segmento da instituição, PF ou PJ, CNAE (PJ) ou ocupação (PF), porte, modalidade, origem dos recursos e indexador, com prazos a vencer, atraso, inadimplência e ativo problemático. Agregado, sem pessoa nem instituição. A versão 1 (parou em jun/2025) fica fora

- **Fonte:** Banco Central: SCR.data (`scrdata_<ano>.zip`)
- **Licença:** ODbL (dados abertos do Banco Central; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal, um arquivo por ano
- **Atraso de divulgação:** Publicado ~30 dias depois do fim do mês (ago/2026 já estava no arquivo em 09/10); `disponivel_em` usa data-base + 60 dias. O BC regrava anos passados: os 2 anos mais novos são baixados de novo a cada carga e cada regravação vira versão `<ano>.v<N>`
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
| `disponivel_em` | Desde quando o mês era público (como era na data) | data (dia) |

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

## `eventos`

Documentos do IPE da CVM desde 2003 (fatos relevantes, comunicados, assembleias, resultados...), com o tema e a materialidade do tipo de documento. A mesma entrega reapresentada fica só na versão mais nova.

- **Fonte:** CVM: dados abertos do IPE (documentos periódicos e eventuais), um arquivo por ano
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada montagem (`scripts/montar_base_historica.py`), que relê todos os arquivos anuais guardados (o IPE da CVM muda todo dia)
- **Atraso de divulgação:** Nenhum além da entrega: o documento vale a partir de `publicado_em`
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

Rótulos de recuperação judicial ou extrajudicial, pedido de falência, falência e liquidação lidos do IPE desde 2003, com a evidência de cada um: documento da categoria própria da CVM (`categoria_ipe`) ou fato relevante que anuncia o pedido (`fato_relevante`, costuma ser o primeiro sinal público)

- **Fonte:** CVM: dados abertos do IPE, um arquivo por ano (`base/rotulos.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada montagem (`scripts/montar_base_historica.py`), que relê todos os arquivos anuais guardados
- **Atraso de divulgação:** O rótulo vale a partir de `conhecido_em` (entrega à CVM)
- **Onde fica:** Parquet em `<acervo>/base/insolvencia/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `rotulo` | recuperacao_judicial, recuperacao_extrajudicial, pedido_de_falencia, falencia ou liquidacao | texto |
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

Estabelecimentos com "situação especial" no CNPJ da Receita (falido, em recuperação, em liquidação, intervenção...), um retrato por mês guardado: o histórico "como era na data" nasce da sequência dos retratos. Nome, endereço, telefone e e-mail nunca entram (LGPD).

- **Fonte:** Receita Federal: dados abertos do CNPJ, arquivos de estabelecimentos
- **Licença:** Dados abertos do CNPJ (Receita; rodapé CC BY-ND do site: perguntar a licença)
- **Revenda:** só uso interno (nunca vender nem exportar)
- **Frequência:** Mensal (a Receita publica um retrato por mês; cada mês guardado vira um arquivo)
- **Atraso de divulgação:** O retrato sai semanas depois do mês; `data_situacao_especial` é a data que a Receita informa, que pode ser anterior ao retrato em que a linha apareceu pela primeira vez
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
- **Onde fica:** Parquet em `<acervo>/base/auditores/<ano>.parquet` (servidor de casa, `scripts/montar_base_historica.py`)
- **Linhagem:** Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). `ano_do_arquivo` diz de que arquivo anual veio a linha.

| Coluna | O que é | Unidade |
|---|---|---|
| `cnpj` | CNPJ da companhia, no formato 00.000.000/0000-00 | texto |
| `empresa` | Nome da companhia como a fonte informa | texto |
| `referencia` | Data de referência do FCA | data (dia) |
| `versao` | Versão do FCA | número inteiro |
| `id_documento` | Número do documento na CVM | texto |
| `conhecido_em` | Data em que a CVM recebeu essa versão do FCA | data (dia) |
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

## `trocas_de_auditor`

Rótulo "trocou de auditor": cada troca de firma, montada de todos os anos de `auditores` na ordem de entrega dos FCAs (uma troca nunca é reescrita depois)

- **Fonte:** CVM: dados abertos do FCA, pela tabela `auditores`
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Refeita a cada montagem de `auditores`
- **Atraso de divulgação:** A troca vale a partir de `conhecido_em` (entrega do FCA que a mostrou)
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
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |

## `curva_juros`

Curva de juros própria, sem B3 nem ANBIMA: nominal (Tesouro Prefixado), real (Tesouro IPCA+) e inflação implícita, nos vértices de 6 meses a 20 anos, só com os títulos sem cupom, interpolação flat-forward e sem extrapolar (nominal desde 2004, real desde 2005). A taxa do Tesouro Direto tem um spread sobre o mercado secundário.

- **Fonte:** Tesouro Nacional: taxas diárias do Tesouro Direto (Tesouro Transparente)
- **Licença:** ODbL (Tesouro Transparente, Tesouro Nacional; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Diária (dias úteis)
- **Atraso de divulgação:** Um dia útil: o arquivo do Tesouro sai na manhã seguinte (`disponivel_em`)
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

## `controladas`

Controladas e coligadas de cada companhia informadas no FRE desde 2010, com a participação e a data de entrega. O FRE mais novo deixa o tipo da sociedade em branco em muitas linhas, e o FRE guarda ligações antigas.

- **Fonte:** CVM: dados abertos do FRE, tabela de participação em sociedades
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada montagem (`scripts/montar_base_historica.py`), que relê todos os arquivos anuais guardados
- **Atraso de divulgação:** O FRE é entregue até 5 meses depois do fim do exercício e reapresentado a cada mudança; a ligação vale a partir de `conhecido_em`
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

## `empresa_serie`

De que companhia listada é cada entidade que os reguladores enxergam (operadora de saúde, distribuidora, banco no Pix, prestadora de telecomunicações, usina, concessionária de ferrovia, companhia aérea): pelo CNPJ, pelo nome exato ou pela tabela conferida (`base/conferidas/empresa_serie.csv`), e daí pelas `controladas`. Os capítulos do NCM do Comex Stat ligam às companhias expostas ao produto (`via` = `produto`: exposição, não posse). Toda entidade aparece, ligada ou não.

- **Fonte:** ANS, ANEEL (SAMP), Banco Central (Pix), Anatel, ANP, ONS, ANTT, ANAC e Comex Stat, ligados pelo FRE da CVM e pelo FCA (tickers)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Ressalva de revenda:** Os nomes e códigos das entidades seguem a licença de cada regulador: CC BY (ANS, Anatel, ANP, ONS, ANTT, ANAC; citar), ODbL (ANEEL, Banco Central) e Comex Stat a confirmar com o MDIC.
- **Frequência:** Refeita a cada montagem, com a safra mais recente de cada fonte
- **Atraso de divulgação:** A ligação vale a partir de `desde` (entrega do FRE que a mostrou); os tickers são os do FCA mais recente
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
| `principal` | A ligação a usar da entidade (ticker hoje, própria, FRE mais recente; nunca no produto) | verdadeiro ou falso |
| `tickers` | Tickers da companhia no FCA mais recente | texto |
| `origem_sha256` | SHA-256 do arquivo de onde a entidade saiu | texto |
| `montado_em` | Quando a tabela foi montada | data e hora (UTC) |
| `versao_do_codigo` | Commit do código que montou a tabela | texto |
