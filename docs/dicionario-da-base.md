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
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `documento`, `referencia`, `versao`, `demonstracao`, `grupo`, `conta`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `divulgado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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
| `divulgado_em` | Dia da entrega à CVM (vale a partir dele, inclusive; a CVM não informa a hora). Entrega com a empresa fora de qualquer registro na CVM (pedido de registro) vale a partir do registro seguinte: o público só viu o documento perto do registro | data (dia) |
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

As posições em ações de todos os fundos registrados na CVM, por mês, desde 2005 (CDA, bloco de ações): comprado, emprestado e vendido, com o ISIN e o emissor. Fundos e posições que saíram continuam (sem viés de sobrevivência). Um Parquet por ano; quando a CVM regrava um ano, a versão anterior fica como `<ano>.v<N>`

- **Fonte:** CVM: composição e diversificação das aplicações dos fundos (CDA), bloco 4
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal; de 2005 a 2022 um arquivo por ano, de 2023 em diante um por mês
- **Atraso de divulgação:** O arquivo sai uns 40 dias depois do mês e o fundo pode deixar uma posição em sigilo por até 90 dias: `disponivel_em` usa competência + 90 dias, ou o fim do sigilo se depois
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `cnpj_fundo`, `tipo`, `codigo`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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

## `carteiras_bloco_8`

As ações e os certificados de depósito que os fundos informam no bloco 8 do CDA ("demais ativos não codificados"), sem o código estruturado, com o CNPJ do emissor que o próprio fundo informa: em 2020, R$ 1,14 tri (soma dos meses) em ações de companhias com ticker, ~26% a mais sobre o bloco 4, quase nada repetido entre os blocos. Emissor pessoa física nunca entra (o CPF é descartado na leitura). Um Parquet por ano, com versões

- **Fonte:** CVM: composição e diversificação das aplicações dos fundos (CDA), bloco 8
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal; de 2005 a 2022 um arquivo por ano, de 2023 em diante um por mês
- **Atraso de divulgação:** O do CDA: `disponivel_em` usa competência + 90 dias, ou o fim do sigilo se depois
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `cnpj_fundo`, `tipo`, `cnpj_emissor`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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
| `disponivel_em` | Desde quando a posição era pública (como era na data) | data (dia) |

## `fidc_informe`

O informe mensal de cada FIDC desde 2013, um Parquet por quadro (`tab_I` a `tab_X_7`) e por ano, no formato da fonte: carteira, prazos, inadimplência por faixa, pré-pagamento, recompras, cedentes. As colunas mudam com os anos (15 quadros em 2013, 18 em 2026) e são as do dicionário da CVM (`meta_inf_mensal_fidc.txt`); a base acrescenta as três abaixo. Sem dado pessoal: dos documentos de cedentes só fica CNPJ válido (CPF vira vazio)

- **Fonte:** CVM: informe mensal de FIDC
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** Mensal; de 2013 a 2024 um arquivo por ano, de 2025 em diante um por mês
- **Atraso de divulgação:** Entregue em até 15 dias; a CVM regrava meses passados (cada regravação vira versão `<ano>.v<N>`). `disponivel_em` usa competência + 45 dias
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `competencia`, `cnpj_fundo`
- **Três datas:** aconteceu_em = `competencia`; publico_em = `disponivel_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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

## `aneel_samp`

Mercado das distribuidoras de energia (SAMP da ANEEL) por distribuidora, mês, classe de consumo, modalidade e posto tarifário: consumidores, energia (kWh) e receita (R$), desde 2003, no formato da fonte. As linhas de cada consumidor livre vêm somadas (sem CPF nem nome). Uma linha por valor diferente de cada chave: a revisão de um mês passado vira linha nova, que só vale desde o dia em que foi vista (`base/setoriais/revisoes.py::como_era_em`). O que mudou antes da primeira coleta (10/2026) não aparece

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
- **Atraso de divulgação:** Jun/2026 estava publicado em 14/10 (106 dias); `disponivel_em` usa data-base + 120 dias. O BC revisa: as 8 datas mais novas são baixadas de novo a cada carga e cada revisão vira versão `<AAAAMM>.v<N>`
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `data_base`, `tipo_instituicao`, `cod_inst`, `relatorio`, `grupo`, `conta`, `coluna`
- **Três datas:** aconteceu_em = `data_base`; publico_em = `disponivel_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `data_base`, `cod_inst`
- **Três datas:** aconteceu_em = `data_base`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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
- **Atraso de divulgação:** Publicado ~30 dias depois do fim do mês (ago/2026 já estava no arquivo em 09/10); `disponivel_em` usa data-base + 60 dias. O BC regrava anos passados: os 2 anos mais novos são baixados de novo a cada carga e cada regravação vira versão `<ano>.v<N>`
- **Módulo:** credito_e_fidc · **Contém dado de pessoa:** não
- **Chaves:** `data_base`, `uf`, `segmento`, `cliente`, `cnae_ocupacao`, `porte`, `modalidade`, `submodalidade`, `origem`, `indexador`
- **Três datas:** aconteceu_em = `data_base`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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

Documentos do IPE da CVM desde 2003 (fatos relevantes, comunicados, assembleias, resultados...), com o tema e a materialidade do tipo de documento. A mesma entrega reapresentada fica só na versão mais nova.

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

Rótulos de recuperação judicial ou extrajudicial, pedido de falência, falência e liquidação lidos do IPE desde 2003, com a evidência de cada um: documento da categoria própria da CVM (`categoria_ipe`) ou fato relevante que anuncia o pedido (`fato_relevante`, costuma ser o primeiro sinal público)

- **Fonte:** CVM: dados abertos do IPE, um arquivo por ano (`base/rotulos.py`)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Frequência:** A cada montagem (`scripts/montar_base_historica.py`), que relê todos os arquivos anuais guardados
- **Atraso de divulgação:** O rótulo vale a partir de `conhecido_em` (entrega à CVM)
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `protocolo`, `versao`, `rotulo`
- **Três datas:** aconteceu_em = `referencia`; publico_em = `conhecido_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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
- **Módulo:** governo_e_sancoes · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `mes_do_retrato`
- **Três datas:** aconteceu_em = `data_situacao_especial`; publico_em = `mes_do_retrato`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2026-10-14 (`publico_em` por mes)
- **Versão do contrato:** 1.0.0
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
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `referencia`, `versao`, `auditor_id`
- **Três datas:** aconteceu_em = `inicio`; publico_em = `conhecido_em`; coletado_em = `origem_coletada_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `cnpj`, `efetiva_em`, `novo_id`
- **Três datas:** aconteceu_em = `efetiva_em`; publico_em = `conhecido_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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

## `controladas`

Controladas e coligadas de cada companhia informadas no FRE desde 2010, com a participação e a data de entrega. O FRE mais novo deixa o tipo da sociedade em branco em muitas linhas, e o FRE guarda ligações antigas.

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

## `rotulos_atraso`

Rótulo do modelo de atraso na entrega (modelo 8, ADR 0030): uma linha por companhia, documento (DFP ou ITR) e data-base, com o prazo da CVM, a primeira entrega e se atrasou. Entram os documentos entregues e os devidos sem entrega (entregou um ano antes, ativa no prazo, data-base no calendário da empresa e no arquivo do ano). Não entra o documento com o prazo antes do primeiro registro da empresa (o que ela manda para pedir o registro, sem prazo a cumprir); o manifesto conta quantos ficaram de fora (`fora_dos_exemplos`). Não é coluna para prever: é a resposta que o modelo tenta acertar (ADR 0027)

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
- **Linhagem:** O manifesto (`rotulos_atraso.json`) lista o endereço e o SHA-256 de cada arquivo anual da DFP e do ITR e do cadastro usados, e o SHA-256 da tabela; `montado_em` diz quando a tabela foi montada. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas).

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

## `empresa_serie`

De que companhia listada é cada entidade que os reguladores enxergam (operadora de saúde, distribuidora, banco no Pix, prestadora de telecomunicações, usina, concessionária de ferrovia, companhia aérea): pelo CNPJ, pelo nome exato ou pela tabela conferida (`base/conferidas/empresa_serie.csv`), e daí pelas `controladas`. Os capítulos do NCM do Comex Stat ligam às companhias expostas ao produto (`via` = `produto`: exposição, não posse). Toda entidade aparece, ligada ou não.

- **Fonte:** ANS, ANEEL (SAMP), Banco Central (Pix), Anatel, ANP, ONS, ANTT, ANAC e Comex Stat, ligados pelo FRE da CVM e pelo FCA (tickers)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Ressalva de revenda:** Os nomes e códigos das entidades seguem a licença de cada regulador: CC BY (ANS, Anatel, ANP, ONS, ANTT, ANAC; citar), ODbL (ANEEL, Banco Central) e Comex Stat a confirmar com o MDIC.
- **Frequência:** Refeita a cada montagem, com a safra mais recente de cada fonte
- **Atraso de divulgação:** A ligação vale a partir de `desde` (entrega do FRE que a mostrou); os tickers são os do FCA mais recente
- **Módulo:** mercado_e_empresas · **Contém dado de pessoa:** não
- **Chaves:** `fonte`, `chave`, `cnpj_companhia`
- **Três datas:** aconteceu_em = `desde`; coletado_em = `montado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
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

## `entidades`

Uma linha por entidade da rede (ADR 0077): empresa (pela raiz do CNPJ; a filial é a mesma empresa), fundo (pelo CNPJ de 14), valor mobiliário (pelo ISIN das carteiras dos fundos) ou firma de auditoria (pelo código da CVM), com id determinístico (`base/rede/ids.py`), nome, natureza jurídica e MEI. Vem das tabelas que a base já tem: cadastro da CVM, FCA, controladas, auditores, empresa ↔ série, cadastro e carteiras de fundos, IF.data e GLEIF. Empresário individual, pessoa física com CNPJ e MEI ficam sem nome e com `trata_como_pessoa`

- **Fonte:** CVM (cadastro, FCA, FRE, fundos), Banco Central (IF.data), GLEIF, os reguladores da empresa ↔ série e a Receita (natureza jurídica e opção pelo MEI)
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Ressalva de revenda:** A natureza jurídica e o MEI com `natureza_fonte` = receita vêm do CNPJ aberto da Receita, que está como só uso interno até a licença ser confirmada; o LEI é do GLEIF (CC0, citar); os códigos dos reguladores seguem a licença de cada um (ver `empresa_serie`).
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

Os identificadores de cada entidade da rede, com de quando a quando valem: CNPJ (com letras), raiz, LEI, ticker, emissor e códigos dos reguladores (`codigo_<fonte>`). Resolvidos por regras de código em ordem fixa (1 CNPJ, 2 raiz, 3 LEI, 4 emissor e ticker, 5 código do regulador, 7 tabela conferida); o mesmo identificador em duas entidades no mesmo período é conflito e não entra em nenhuma

- **Fonte:** CVM (cadastro, FCA, FRE, fundos), Banco Central (IF.data), GLEIF e os reguladores da empresa ↔ série
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Ressalva de revenda:** A natureza jurídica e o MEI com `natureza_fonte` = receita vêm do CNPJ aberto da Receita, que está como só uso interno até a licença ser confirmada; o LEI é do GLEIF (CC0, citar); os códigos dos reguladores seguem a licença de cada um (ver `empresa_serie`).
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

Uma linha por relação entre duas entidades da rede (ADR 0077), com as três datas: sociedade controlada, coligada ou participada da companhia (FRE), entidade do regulador que opera para a companhia (empresa ↔ série), instituição do conglomerado do líder (IF.data), firma que audita a companhia (FCA), empresa que emite o valor mobiliário e fundo que o detém (carteiras do CDA, meses seguidos num período só). Nada é apagado entre cargas: o que some da fonte fica, encerrado pela carga. Esta é a vista interna; a publicada (sem pessoas) sai de `base/rede/vistas.py`

- **Fonte:** CVM (FRE, FCA, carteiras dos fundos), Banco Central (IF.data) e os reguladores da empresa ↔ série
- **Licença:** ODbL (dados abertos da CVM; citar a fonte)
- **Revenda:** vendável com atribuição, sob a ODbL (compartilhar igual: quem compra pode repassar; o valor está na curadoria, nas versões e na qualidade)
- **Ressalva de revenda:** A natureza jurídica e o MEI com `natureza_fonte` = receita vêm do CNPJ aberto da Receita, que está como só uso interno até a licença ser confirmada; o LEI é do GLEIF (CC0, citar); os códigos dos reguladores seguem a licença de cada um (ver `empresa_serie`).
- **Frequência:** Toda noite no servidor de casa; versão nova só quando o conteúdo muda
- **Atraso de divulgação:** O da fonte: o FRE e o FCA pela entrega à CVM, a carteira 90 dias depois do mês, o IF.data 120 dias depois da data-base; a fonte de governo desde que guardada
- **Módulo:** rede · **Contém dado de pessoa:** não
- **Chaves:** `de`, `para`, `tipo`, `papel`, `aconteceu_em`, `fonte`
- **Três datas:** aconteceu_em = `aconteceu_em`; publico_em = `publico_em`; coletado_em = `coletado_em`
- **Histórico desde:** 2010-01-01 (`publico_em` por dia)
- **Versão do contrato:** 1.0.0
- **Onde fica:** Parquet em `<acervo>/base/rede/ligacoes.parquet` (servidor de casa, `scripts/montar_rede.py`)
- **Linhagem:** Derivada: o manifesto aponta as tabelas de entrada (com o SHA-256 do conteúdo), as tabelas conferidas (`emissores_antigos.csv`, `entidades.csv`) e os originais lidos do acervo (cadastro da CVM, páginas do GLEIF, Empresas e Simples da Receita); a linhagem segue até a coleta de cada um. `versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit ou com mudanças não salvas). Cada linha leva o `origem_sha256` do arquivo (ou da tabela da base) de onde veio.

| Coluna | O que é | Unidade |
|---|---|---|
| `de` | A entidade de onde a relação sai (a controlada, o fundo, a firma) | texto |
| `para` | A entidade para onde a relação vai (a companhia, o valor mobiliário) | texto |
| `tipo` | controlada_de, coligada_de, participada_de (FRE sem o tipo), opera_para, do_conglomerado_de, audita, emite ou detem | texto |
| `papel` | Detalhe do tipo: comprado, emprestado ou vendido (detem); a via e se é a principal (opera_para); lider (do_conglomerado_de) | texto |
| `participacao` | Participação informada no FRE (vazia nos outros) | pontos percentuais (66,25 = 66,25%) |
| `aconteceu_em` | Data do fato: referência do FRE, início do mandato, primeiro mês da carteira | data (dia) |
| `infracao_em` | Data da infração, nas sanções (vazia nas fontes de hoje) | data (dia) |
| `publico_em` | Desde quando a relação era pública (como era na data) | data (dia) |
| `coletado_em` | Quando a base guardou o arquivo de onde veio (registro de coletas) | data (dia) |
| `ate` | Até quando valeu, sem incluir o dia (vazio: ainda vale) | data (dia) |
| `situacao` | vigente ou encerrada | texto |
| `encerrada_por` | fonte (a fonte diz o fim) ou carga (sumiu da fonte nesta carga); vazio se vigente | texto |
| `fonte` | cvm-fre, cvm-fca, cvm-cda, bcb-ifdata ou empresa_serie | texto |
| `origem_sha256` | SHA-256 do arquivo ou da tabela da base de onde veio | texto |
| `conferido_por` | regra (código) ou tabela (conferida à mão) | texto |

## `ma_assessorias`

Negócios de M&A do middle market tirados dos posts das assessorias independentes (ADR 0082), uma linha por página de negócio: as empresas, o tipo e o sentido. Só fatos: nenhum texto do post e nenhuma pessoa física (a equipe da assessoria nem é lida). Sem data do negócio (a página não tem; `conhecido_em` vem no passo 4 da série 5) e sem CNPJ das partes (passo 3)

- **Fonte:** Sites das assessorias de M&A (IGC Partners), páginas guardadas pelo arquivista
- **Licença:** Posts públicos de assessorias de M&A: só fatos, sem texto (ADR 0082)
- **Revenda:** a confirmar (sem resposta escrita sobre revenda; não vender até conferir)
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
| `conferencia` | assessoria (fonte única: declarado por quem assessorou) ou confirmado | texto |

## `ma_partes`

As empresas de cada negócio de M&A das assessorias (`ma_assessorias`), uma linha por empresa de cada página, ligadas à rede de entidades (ADR 0077) só por regras exatas: o nome normalizado contra os nomes da rede e a razão social do CNPJ e, se nada casou, contra o nome fantasia. Nome de mais de uma entidade fica na dúvida, nunca escolhido; empresário individual e MEI nunca são ligados (ADR 0075). Série 5 do plano de M&A, passo 3 (ADR 0082)

- **Fonte:** `ma_assessorias`, a rede (`entidades`, `identificadores`) e o CNPJ aberto da Receita (razão social e nome fantasia, lidos e descartados: só a raiz fica)
- **Licença:** Posts públicos de assessorias de M&A: só fatos, sem texto (ADR 0082)
- **Revenda:** a confirmar (sem resposta escrita sobre revenda; não vender até conferir)
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
| `ligacao_por` | nome_exato (rede ou razão social), nome_fantasia, na_duvida (mais de um candidato) ou sem_ligacao | texto |
| `candidatos` | Quantas entidades têm esse nome (0 sem ligação, 1 ligada, 2 ou mais na dúvida) | número inteiro |

## `ma_negocios`

Uma linha por página de negócio de M&A com o `id_negocio`, o mesmo para as páginas do mesmo negócio em sites diferentes (as assessorias dos dois lados postam o mesmo negócio): mesmas partes, assessorias diferentes e tipos que não se contradizem. Série 5 do plano de M&A, passo 3 (ADR 0082)

- **Fonte:** `ma_assessorias` e `ma_partes`
- **Licença:** Posts públicos de assessorias de M&A: só fatos, sem texto (ADR 0082)
- **Revenda:** a confirmar (sem resposta escrita sobre revenda; não vender até conferir)
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
