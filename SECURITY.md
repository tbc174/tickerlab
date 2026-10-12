# Segurança

Obrigado por ajudar a manter o TickerLab seguro.

## Como reportar uma falha

**Não abra uma issue pública.** Escreva para **contato@tickerlab.com.br** com:

- o que você encontrou e onde (página, endereço ou arquivo do repositório);
- os passos para reproduzir;
- o impacto que você imagina (por exemplo: ver dados de outra conta, mudar de plano sem pagar).

Você recebe uma resposta em até 5 dias úteis. Corrigida a falha, conto o que foi feito e, se
quiser, agradeço publicamente pelo nome que você indicar.

## O que está no escopo

- O app (`app.tickerlab.com.br`), a API (`api.tickerlab.com.br`) e o site (`tickerlab.com.br`).
- O código deste repositório.

Fora do escopo: ataques de negação de serviço, testes automatizados em massa contra a produção e
engenharia social. Por favor, teste só com a sua própria conta e não acesse dados de outras
pessoas.

## Como o projeto se protege

- Login só pelo Google; toda consulta ao banco filtra pelo usuário, com teste de isolamento.
- Cobrança pelo Stripe **só em modo de teste**: o código recusa chaves de produção.
- O plano só muda pelo webhook do Stripe, com assinatura verificada.
- Segredos fora do Git; logs sem e-mail nem nome.
- Exportar e apagar a conta (LGPD) disponíveis no próprio app.
