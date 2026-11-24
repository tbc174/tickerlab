# TickerLab CLI: instruções para o agente de IA

Este arquivo é para o agente de IA (Claude Code, Codex e outros) de quem analisa empresas e usa a CLI
`tickerlab`. Ponha-o na pasta do seu projeto com `tickerlab instrucoes > AGENTS.md`. (No repositório do
TickerLab, as regras de quem programa estão no `AGENTS.md` da raiz; este aqui é só o do pacote.)

## O que a CLI faz

Busca dados de empresas, fundos e setores do Brasil na API do TickerLab Data. Cada número sai com a **fonte**, o
**dia em que ficou público** e a licença da fonte. A CLI não calcula nada por conta própria: o que ela
devolve é o que a API serviu.

## Comandos

<!-- comandos: montados pela CLI a partir da ajuda de cada comando -->

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
   **Dado de piloto:** campo com `pilot: true` (e `pilot_notice` na resposta) ainda não passou pela conferência cheia. Repasse a frase de `pilot_notice` junto do número, como veio, sem reescrever nem tirar; a CLI a mostra na tela e nas planilhas.
   **Parte não disponível:** se a resposta traz `unavailable_event_types` (ou a tela avisa que parte dos dados não está disponível para a organização), aquele tipo não foi consultado: lista vazia não quer dizer que não existe. Diga qual tipo ficou de fora.
3. **Não invente número que a CLI não devolveu.** Se o dado não veio (código 5, campo ausente, lista
   cortada), diga que não veio. Não complete com estimativa sem dizer que é sua e como chegou nela.
4. **Conta sua é sua.** Se você calcular algo a partir dos números (margem, crescimento, múltiplo), mostre a
   conta e os campos de origem, separado do que a API serviu.
5. **A chave é segredo.** Nunca a escreva num comando, num arquivo do projeto, num log ou no chat. Ela fica
   em `TICKERLAB_API_KEY` ou no arquivo do `tickerlab login`.
6. **Sem dado de pessoa física.** A linha de comando não traz sócio pessoa física, CPF, MEI nem empresário
   individual. A API só serve o nome de sócio pessoa física à organização com a permissão de ver pessoas
   pela API e pelo conector, desligada por padrão, e nunca o CPF; nenhum comando daqui o pede. Não tente chegar a uma pessoa por outros
   caminhos.

## Configuração

- `tickerlab login` pergunta a chave sem mostrá-la e a grava só para o usuário (`tickerlab logout` apaga).
- `TICKERLAB_API_KEY` vale mais que o arquivo. `TICKERLAB_API_URL` troca o endereço (padrão:
  `https://api.tickerlab.com.br`; HTTP só para `localhost`).
