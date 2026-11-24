---
name: tickerlab
description: Busca dados oficiais de empresas, fundos e setores do Brasil (Receita Federal, CVM, agências reguladoras) pela CLI `tickerlab`, com fonte e data em cada número. Use quando a pessoa pedir a situação cadastral de um CNPJ, se uma companhia aberta entrega a DFP e o ITR no prazo, as demonstrações financeiras (DFP, ITR) de uma companhia aberta, o cadastro, as taxas ou a carteira de um fundo, o tamanho e a concentração (CR4, HHI) de um setor regulado e a fatia de cada companhia aberta nele, as controladas, coligadas e participadas e o auditor de uma companhia aberta, os fatos relevantes, comunicados e trocas de auditor de uma companhia aberta, uma lista de empresas por CNAE, UF, porte e idade (prospecção), o que a chave do TickerLab pode pedir ou quanto da quota já foi usado, e para análise de empresa, M&A ou crédito que precise desses números.
---

# TickerLab CLI

Instale a skill copiando este arquivo para `.claude/skills/tickerlab/SKILL.md` no seu projeto (ou em
`~/.claude/skills/tickerlab/`): `tickerlab instrucoes skill`.

## Como usar

1. Rode sempre com `--json` e leia o envelope: cada campo é `{"value", "source", "published_at", ...}` e
   `sources` traz a licença e a frase de atribuição de cada fonte.
2. Escolha o comando na lista de "Comandos" abaixo (`tickerlab <comando> --help` dá o detalhe). Nos comandos
   que leem a base por CNPJ, setor ou filtro:
   - `--como-era AAAA-MM-DD`: o dado como era público naquele dia.
   - `--planilha ARQUIVO.xlsx` (ou `.csv`), quando a pessoa quiser a planilha para o Excel: uma aba por
     tabela, com `fonte` e `publicado_em` em cada linha, e a aba `fontes`.
3. Código de saída: 0 ok; 2 comando errado; 3 sem chave ou chave recusada (peça `tickerlab login` à pessoa,
   nunca a chave no chat); 4 limite ou quota; 5 nada disponível (veja `tickerlab catalogo`, não insista);
   6 pedido recusado; 7 API fora do ar; 1 erro inesperado. A mensagem sai em stderr.
4. `truncated: true`: a lista foi cortada no limite do plano. Diga isso; não trate como completa.
5. Antes de concluir, leia `limits` (o que a leitura não cobre) e, no dossiê, `gaps`: não achado não quer dizer
   que não existe. `next_cursor` preenchido: há mais páginas (`--todas` busca todas, um pedido da quota por
   página). Código 5 nas demonstrações: empresa fechada não tem DFP nem ITR, e a base não estima faturamento;
   diga isso, não invente o número. O dossiê gasta 4 pedidos; `setor` sem chave, `catalogo` e `consumo` não
   gastam a quota.

## Comandos

<!-- comandos: montados pela CLI a partir da ajuda de cada comando -->

## Travas

- **Nada é recomendação de investimento.** Descreva, compare e calcule; não diga para comprar ou vender.
- **Cite a fonte e a data de cada número** (`source` e `published_at`), e a `attribution` ao repassar.
- **Não invente número que a CLI não devolveu.** Dado ausente é ausente; conta sua sai separada e com a
  origem de cada parcela.
- **A chave é segredo:** nunca num comando, arquivo, log ou no chat.
- **Sem pessoa física:** a linha de comando não traz sócio PF, CPF, MEI nem empresário individual (a API só
  serve o nome de sócio PF à organização com a permissão de ver pessoas pela API, e nunca o CPF); não procure por
  outros caminhos.

Instruções completas: `tickerlab instrucoes` (o AGENTS.md do pacote).
