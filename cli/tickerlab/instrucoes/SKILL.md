---
name: tickerlab
description: Busca dados oficiais de empresas, fundos e setores do Brasil (Receita Federal, CVM, agências reguladoras) pela CLI `tickerlab`, com fonte e data em cada número. Use quando a pessoa pedir a situação cadastral de um CNPJ, se uma companhia aberta entrega a DFP e o ITR no prazo, as demonstrações financeiras (DFP, ITR) de uma companhia aberta, o cadastro, as taxas ou a carteira de um fundo, o tamanho e a concentração (CR4, HHI) de um setor regulado e a fatia de cada companhia aberta nele, uma lista de empresas por CNAE, UF, porte e idade (prospecção), o que a chave do TickerLab pode pedir ou quanto da quota já foi usado, e para análise de empresa, M&A ou crédito que precise desses números.
---

# TickerLab CLI

Instale a skill copiando este arquivo para `.claude/skills/tickerlab/SKILL.md` no seu projeto (ou em
`~/.claude/skills/tickerlab/`): `tickerlab instrucoes skill`.

## Como usar

1. Rode sempre com `--json` e leia o envelope: cada campo é `{"value", "source", "published_at", ...}` e
   `sources` traz a licença e a frase de atribuição de cada fonte.
2. Comandos:
   - `tickerlab empresa <cnpj> --json`: o perfil: cadastro na Receita (situação, razão social, natureza
     jurídica, Simples) e, de companhia aberta, cada DFP e ITR com prazo da CVM, atraso e situação da entrega;
     leia `limits`. `--so-cadastro` traz só o cadastro.
   - `tickerlab comparaveis <cnpj> [--como-era AAAA-MM-DD] --json`: as companhias abertas do mesmo grupo de
     setores, cada uma com o último DFP (receita, EBITDA, lucro, dívida líquida e razões), e a mediana de cada
     razão em `peer_medians`; leia `limits` antes de comparar múltiplos.
   - `tickerlab demonstracoes <cnpj> [--periodo AAAA-MM-DD] --json`: DFP e ITR (CVM), uma linha por conta e
     período, com documento, versão e data de entrega.
   - `tickerlab fundo <cnpj> [--retorno-suposto 0.12] --json`: cadastro, taxas e carteira do fundo (CVM).
   - `tickerlab prospectar --cnae 3511 --uf SP [--porte demais] [--aberta-antes AAAA-MM-DD] --json`: empresas do
     cadastro da Receita por atividade, lugar, porte e idade (pelo menos um filtro além da situação; os filtros
     repetem, até 50 valores; `--municipio` é o nome ou o código da Receita, não o do IBGE; só empresa, sem sócio
     nem contato). `next_cursor` preenchido: há mais páginas; `--todas` busca todas (um pedido por página).
   - `tickerlab setor --json`: os setores disponíveis (não gasta a quota); `tickerlab setor <chave> --json`:
     mercado, CR4, HHI e faixa do CADE por ano, a fatia de cada companhia aberta e as `notes` de método (leia
     antes de concluir sobre concentração).
   - `tickerlab catalogo --json`: o que a chave pode pedir hoje (não gasta a quota).
   - `tickerlab consumo --json`: pedidos do mês e limites (não gasta a quota).
   - `--como-era AAAA-MM-DD` em qualquer comando de dado: o dado como era público naquele dia.
   - `--planilha ARQUIVO.xlsx` (ou `.csv`) em qualquer comando de dado, quando a pessoa quiser a planilha para
     o Excel: uma aba por tabela, com `fonte` e `publicado_em` em cada linha, e a aba `fontes`.
3. Código de saída: 0 ok; 2 comando errado; 3 sem chave ou chave recusada (peça `tickerlab login` à pessoa,
   nunca a chave no chat); 4 limite ou quota; 5 nada disponível (veja `tickerlab catalogo`, não insista);
   6 pedido recusado; 7 API fora do ar; 1 erro inesperado. A mensagem sai em stderr.
4. `truncated: true`: a lista foi cortada no limite do plano. Diga isso; não trate como completa.

## Travas

- **Nada é recomendação de investimento.** Descreva, compare e calcule; não diga para comprar ou vender.
- **Cite a fonte e a data de cada número** (`source` e `published_at`), e a `attribution` ao repassar.
- **Não invente número que a CLI não devolveu.** Dado ausente é ausente; conta sua sai separada e com a
  origem de cada parcela.
- **A chave é segredo:** nunca num comando, arquivo, log ou no chat.
- **Sem pessoa física:** a API não serve sócio PF, CPF, MEI nem empresário individual; não procure por outros
  caminhos.

Instruções completas: `tickerlab instrucoes` (o AGENTS.md do pacote).
