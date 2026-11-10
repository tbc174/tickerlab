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
| `tickerlab empresa <cnpj> [--como-era AAAA-MM-DD]` | Situação cadastral na Receita Federal (com data e motivo), matriz ou filial, mês do retrato; da raiz do CNPJ, razão social, natureza jurídica e opção pelo Simples, cada um na versão que valia no dia. |
| `tickerlab demonstracoes <cnpj> [--como-era AAAA-MM-DD] [--periodo AAAA-MM-DD]` | DFP e ITR da companhia aberta (CVM): uma linha por conta e período, com o documento, a data de referência, a versão (reapresentação) e a data de entrega. Do período mais novo para o mais velho. |
| `tickerlab fundo <cnpj> [--como-era AAAA-MM-DD] [--retorno-suposto 0.12]` | Cadastro e taxas do fundo, a carteira declarada (CDA) e, com `--retorno-suposto`, a conta de quanto a taxa de administração leva em alguns prazos, sobre um capital de exemplo. |
| `tickerlab setor [<chave>] [--como-era AAAA-MM-DD]` | Sem chave, a lista dos setores (`eletricas`, `bancos`...) com o dia da ficha; não gasta a quota. Com a chave, o mercado do setor por série da agência (tamanho, CR4, HHI e a faixa de concentração do CADE, por ano), a fatia de cada companhia aberta, quem são elas e as notas de método (`notes`). Sai como a ficha da última noite o deixou: `--como-era` antes dela dá o código 5. |
| `tickerlab catalogo` | O que a chave pode pedir hoje: conjuntos, campos, fontes e licenças. Não gasta a quota. |
| `tickerlab consumo` | Pedidos do mês, limites do plano e o que ainda cabe. Não gasta a quota. |

- O CNPJ entra com ou sem pontuação (`33.000.167/0001-01` ou `33000167000101`). A chave do setor é a da
  lista (`tickerlab setor`), em minúsculas.
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
| 4 | limite do minuto ou quota do mês | espere (o texto diz quanto) ou veja `tickerlab consumo` |
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
