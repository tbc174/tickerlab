# TickerLab CLI: instruções para o agente de IA

Este arquivo é para o agente de IA (Claude Code, Codex e outros) de quem analisa empresas e usa a CLI
`tickerlab`. Ponha-o na pasta do seu projeto com `tickerlab instrucoes > AGENTS.md`. (No repositório do
TickerLab, as regras de quem programa estão no `AGENTS.md` da raiz; este aqui é só o do pacote.)

## O que a CLI faz

Busca dados de empresas, fundos e setores do Brasil na API do TickerLab Data. Cada número sai com a **fonte**, o
**dia em que ficou público** e a licença da fonte. A CLI não calcula nada por conta própria: o que ela
devolve é o que a API serviu.

## Comandos

| Comando | O que devolve |
|---|---|
| `tickerlab empresa <cnpj> [--como-era AAAA-MM-DD] [--so-cadastro]` | O perfil: em `registration`, a situação cadastral na Receita Federal (com data e motivo), matriz ou filial, mês do retrato, razão social, natureza jurídica e opção pelo Simples, cada um na versão que valia no dia; em `periodic_filings`, de companhia aberta, cada DFP e ITR devida até o dia, com prazo da CVM, primeira entrega, dias úteis de atraso e situação (`on_time`, `gray_zone`, `late`, `severely_late`, `not_filed`); em `limits`, o que a leitura não cobre. `--so-cadastro` traz só o cadastro (para a chave sem o conjunto `profiles`). |
| `tickerlab comparaveis <cnpj> [--como-era AAAA-MM-DD]` | Os comparáveis da companhia aberta: o grupo de setores (`sector_group`, pelo FCA), a empresa pedida e cada par do mesmo grupo com o último DFP entregue até o dia (receita, EBITDA, lucro, patrimônio, dívida líquida, margens, retorno sobre o patrimônio, dívida líquida/EBITDA), a mediana de cada razão entre os pares (`peer_medians`) e os `limits`. Pede o conjunto `comparables` no contrato; empresa sem FCA no dia sai com o código 5. |
| `tickerlab compradores --cnae <5 ou 7 dígitos> [--uf SP] [--anos 3] [--limite 20] [--como-era AAAA-MM-DD]` | Candidatos a comprador do setor: quem entrou como sócio, fundo sócio ou controla empresa do setor nos últimos anos. Só pessoa jurídica; traz sinais e evidências (empresa do setor, UF, data). Movimento passado não é intenção de compra: leia os `limits`. |
| `tickerlab dossie <cnpj> [--como-era AAAA-MM-DD]` | O dossiê do CNPJ numa saída só: perfil, eventos, vínculos e comparáveis, com fonte e data. Gasta 4 pedidos. Seção que a chave não cobre ou sem dado vem em `gaps` com o motivo (não achado não quer dizer que não existe). Só pessoa jurídica. |
| `tickerlab eventos <cnpj> [--tipo documento\|auditor] [--como-era AAAA-MM-DD] [--todas]` | Os eventos da empresa, do mais novo ao mais velho: documentos entregues à CVM pelo IPE (`ipe_filing`: protocolo, categoria, tipo, data de referência e `document_url`; o assunto escrito pela companhia não sai) e trocas de auditor pelo FCA (`auditor_change`: `effective_on`, `previous`, `new`, `years_with_previous`). `--tipo` repete. `next_cursor` preenchido: há mais páginas; `--todas` junta todas (um pedido por página). Pede o conjunto `events` no contrato. Sem evento não quer dizer que nada aconteceu: leia os `limits`. |
| `tickerlab vinculos <cnpj> [--profundidade 1-3] [--tipo controlada\|coligada\|participada\|auditor] [--como-era AAAA-MM-DD]` | Os vínculos da empresa como eram no dia, de 1 a 3 saltos: de quem era controlada (`subsidiary_of`), coligada (`affiliate_of`) ou participada (`investee_of`) e quem ela controlava, com a participação no capital (`ownership_pct`, pelo FRE), e a firma que a auditava (`audits`, pelo FCA). Cada ponta (`from`, `to`) traz `entity_id`, `cnpj_root` e a razão social do dia. Pessoa física não sai. Pede o conjunto `links` no contrato; `truncated: true` é lista cortada. Leia os `limits`: só companhia aberta informa controle e coligação, uma vez por ano. |
| `tickerlab demonstracoes <cnpj> [--como-era AAAA-MM-DD] [--periodo AAAA-MM-DD]` | DFP e ITR da companhia aberta (CVM): uma linha por conta e período, com o documento, a data de referência, a versão (reapresentação) e a data de entrega. Do período mais novo para o mais velho. |
| `tickerlab fundo <cnpj> [--como-era AAAA-MM-DD] [--retorno-suposto 0.12]` | Cadastro e taxas do fundo, a carteira declarada (CDA) e, com `--retorno-suposto`, a conta de quanto a taxa de administração leva em alguns prazos, sobre um capital de exemplo. |
| `tickerlab prospectar --cnae <2 a 7 dígitos> [--uf SP] [--municipio <nome ou código da Receita>] [--porte micro\|pequena\|demais\|nao_informado] [--natureza <até 4 dígitos>] [--situacao ativa\|baixada\|inapta\|suspensa\|nula] [--aberta-antes AAAA-MM-DD] [--aberta-depois AAAA-MM-DD] [--so-matriz] [--todas]` | Empresas do cadastro da Receita que atendem os filtros (pelo menos um além da situação; os de lista podem repetir), por ordem de CNPJ: o CNPJ e, cada um com fonte e data, razão social, natureza, porte, situação, abertura, CNAE, UF, município e matriz. O município é o nome ou o código da Receita (não o do IBGE). Pede o conjunto `prospecting` no contrato. Só empresa: sem sócio, contato nem endereço. Vem em páginas: sem `--todas`, só a primeira, e `next_cursor` preenchido quer dizer que há mais; `--todas` busca todas (cada página é um pedido da quota). |
| `tickerlab setor [<chave>] [--como-era AAAA-MM-DD]` | Sem chave, a lista dos setores (`eletricas`, `bancos`...) com o dia da ficha; não gasta a quota. Com a chave, o mercado do setor por série da agência (tamanho, CR4, HHI e a faixa de concentração do CADE, por ano), a fatia de cada companhia aberta, quem são elas e as notas de método (`notes`). Sai como a ficha da última noite o deixou: `--como-era` antes dela dá o código 5. |
| `tickerlab novidades [--dias 1-30]` | As fontes que a pesquisa do TickerLab provou na semana (padrão 7 dias): de cada uma, `agency` (o órgão público), `date`, `excerpt` (o trecho literal), `source_url` e `original_sha256` (o hash do original, que prova que o trecho está lá). Só fonte pública de órgão e só o que tem prova gravada; sem nada novo a lista vem vazia e a resposta é "nenhuma fonte nova provada na semana". Não é opinião nem recomendação: é citação conferida. |
| `tickerlab catalogo` | O que a chave pode pedir hoje: conjuntos, campos, fontes e licenças. Não gasta a quota. |
| `tickerlab consumo` | Pedidos do mês, limites do plano e o que ainda cabe. Não gasta a quota. |

- O CNPJ entra com ou sem pontuação (`33.000.167/0001-01` ou `33000167000101`). A chave do setor é a da
  lista (`tickerlab setor`), em minúsculas.
- Nas entregas, `not_filed` quer dizer não entregue **até o dia pedido**; empresa sem `periodic_filings` não é
  companhia aberta no cadastro da CVM (não quer dizer que nada era devido). A situação é uma regra sobre o
  prazo, não opinião sobre a empresa: leia `limits` e diga isso junto.
- Na prospecção, a lista é **o que o cadastro diz** (CNAE e porte declarados pela própria empresa à Receita), não
  uma triagem: diga isso. Se `next_cursor` vier preenchido, a lista não está completa; antes de `--todas` numa
  busca larga, confira a quota com `tickerlab consumo`. Para a ficha de cada uma, `tickerlab empresa <cnpj>`.
- No setor, leia as `notes` antes de concluir: parte do mercado pode estar contada por entidade, e aí a
  concentração real é maior ou igual à mostrada. Diga isso junto do número.
- `--como-era` mostra o dado **como era público naquele dia**: nada publicado depois entra. Use para
  reconstruir o que se sabia numa data (um precedente de M&A, um comitê de crédito).
- **Use `--json` sempre que for ler a resposta por programa.** O JSON é o envelope inteiro da API: cada
  campo vem como `{"value", "source", "published_at", "observed_at"}`, e a resposta termina com `sources`
  (licença e frase de atribuição de cada fonte). A tabela, sem `--json`, é para a pessoa ler.
- `--planilha ARQUIVO.xlsx` (ou `.csv`) nos comandos de dado grava a resposta para o Excel, quando a pessoa
  pedir uma planilha: uma aba por tabela, mais `campos` e `fontes`; cada linha com `fonte` e `publicado_em`.
  Para ler você mesmo, continue com `--json`; os dois juntos gravam o arquivo e imprimem o JSON.
- `truncated: true` quer dizer que a resposta foi cortada no limite de linhas do plano: diga isso no texto,
  não trate a lista como completa. Para menos linhas, use `--periodo` nas demonstrações.

## Códigos de saída

| Código | Quer dizer | O que fazer |
|---|---|---|
| 0 | ok | |
| 2 | comando, CNPJ ou chave do setor mal escritos, ou endereço da API inseguro | corrija o comando |
| 3 | sem chave, ou a chave foi recusada | peça à pessoa para rodar `tickerlab login`; **nunca** peça a chave no chat |
| 4 | limite do minuto ou quota do mês | a CLI já esperou e repetiu uma vez no limite do minuto; espere (o texto diz quanto) ou veja `tickerlab consumo` |
| 5 | nada disponível para este pedido | o CNPJ (ou o setor) não tem o dado na data, ou o conjunto não está no contrato: veja `tickerlab catalogo`. Não insista com variações do mesmo pedido |
| 6 | a API recusou o pedido (dígito do CNPJ, data no futuro...) | corrija o pedido |
| 7 | API fora do ar ou sem internet | tente de novo mais tarde |
| 1 | erro inesperado | conte à pessoa |

As mensagens de erro saem na saída de erro (stderr), em português.

## Travas (siga sempre)

1. **Nada é recomendação de investimento.** Não diga "compre", "venda", "vale a pena investir". Você pode
   descrever os dados, comparar e calcular; a decisão é da pessoa.
2. **Cite a fonte e a data de cada número** que usar: a `source` e o `published_at` do campo (por exemplo,
   "conta 3.01 de 2025: 200,0, da DFP entregue à CVM em 15/03/2026, fonte cvm-hist-dfp"). Ao publicar ou
   repassar, inclua a frase de `attribution` de cada fonte, como a licença pede.
3. **Não invente número que a CLI não devolveu.** Se o dado não veio (código 5, campo ausente, lista
   cortada), diga que não veio. Não complete com estimativa sem dizer que é sua e como chegou nela.
4. **Conta sua é sua.** Se você calcular algo a partir dos números (margem, crescimento, múltiplo), mostre a
   conta e os campos de origem, separado do que a API serviu.
5. **A chave é segredo.** Nunca a escreva num comando, num arquivo do projeto, num log ou no chat. Ela fica
   em `TICKERLAB_API_KEY` ou no arquivo do `tickerlab login`.
6. **Sem dado de pessoa física.** A API não serve sócio pessoa física, CPF, MEI nem empresário individual;
   não tente chegar a uma pessoa por outros caminhos.

## Configuração

- `tickerlab login` pergunta a chave sem mostrá-la e a grava só para o usuário (`tickerlab logout` apaga).
- `TICKERLAB_API_KEY` vale mais que o arquivo. `TICKERLAB_API_URL` troca o endereço (padrão:
  `https://api.tickerlab.com.br`; HTTP só para `localhost`).
