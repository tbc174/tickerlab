# Guia do analista: o TickerLab dentro do Claude e do ChatGPT

Com o conector do TickerLab, você pergunta ao Claude ou ao ChatGPT sobre uma empresa, e a IA consulta a
base do TickerLab na hora, com a fonte e a data de cada informação. Você não precisa sair da conversa
nem copiar dados de um lugar para o outro.

## Antes de começar

- **Sua chave pessoal.** Ela começa com `tld_` e é entregue por quem administra o TickerLab na sua
  empresa. **Cada pessoa tem a própria chave.** Não empreste a sua e não use a de um colega: tudo o que a
  IA consultar conta na chave de quem a ligou.
- **O endereço do conector:** `https://mcp.tickerlab.com.br/mcp`

## Ligar no Claude (claude.ai e o app)

1. Em **Configurações → Conectores**, escolha **Adicionar conector personalizado**. Nos planos Team e
   Enterprise, quem adiciona é quem administra a organização no Claude. Depois, cada pessoa liga o
   conector com a própria chave.
2. Cole o endereço `https://mcp.tickerlab.com.br/mcp` e confirme.
3. Clique em **Conectar**. Abre uma página do TickerLab com o título **"Ligar o Claude ao TickerLab"**.
4. Cole a sua chave e clique em **Ligar**. Você volta ao Claude com o conector ligado.

Os nomes dos menus podem mudar um pouco de uma versão do Claude para outra. O endereço e a página do
TickerLab não mudam.

## Se você usa o ChatGPT

O mesmo conector também funciona no ChatGPT, com a mesma chave.

1. Em **Configurações → Apps e conectores**, crie um conector novo com o endereço
   `https://mcp.tickerlab.com.br/mcp` e a autenticação **OAuth**. Nas contas de empresa, quem administra o
   ChatGPT pode precisar liberar conectores personalizados antes.
2. Ao conectar, abre a página do TickerLab com o título **"Ligar o ChatGPT ao TickerLab"**.
3. Cole a sua chave e clique em **Ligar**.

## Confira a página antes de colar a chave

A página do TickerLab diz qual IA está pedindo o acesso e traz o aviso **"Só continue se foi você que
começou esta ligação agora"**. Leve esse aviso a sério:

- só cole a chave numa página que se abriu porque **você** clicou em Conectar, no seu Claude ou no seu
  ChatGPT, neste momento;
- se alguém mandar um link para essa página (por e-mail, mensagem ou chat), **não cole a chave**: quem
  mandou estaria ligando o assistente dele à sua chave;
- se a página falar de uma IA que você não está usando, feche a página.

A chave não fica guardada no assistente. Ele recebe um acesso que vence sozinho e que para de funcionar
quando a chave é revogada.

## O que dá para perguntar

O conector só lê. Ele não muda nada na base nem na sua conta. A IA escolhe sozinha as consultas certas:

| Consulta | Para quê |
|---|---|
| Buscar empresas | achar empresas por atividade (CNAE), UF, município, porte ou idade |
| Ficha da empresa | a triagem de um CNPJ antes da reunião: cadastro na Receita, situação, atividade e, se for companhia aberta, as entregas à CVM |
| Comparáveis | empresas parecidas com a do CNPJ |
| Demonstrações | os números publicados, quando a empresa publica |
| Fundo | o raio-x de um fundo na CVM: cadastro, taxas e carteira |
| Setores e setor | o panorama de um setor |
| O que posso ver | o que a sua chave libera |

Para várias consultas, dá para pedir a informação **como ela era numa data** ("como era em 31/12/2025").

Exemplos de pedidos:

- "Faça a triagem do CNPJ 00.000.000/0001-00 para uma reunião amanhã, com a fonte de cada ponto."
- "Liste empresas de embalagens plásticas em Santa Catarina com mais de 15 anos."
- "Quem são os comparáveis desta empresa? Monte uma tabela."

## Pesquisas em vários passos

A IA pode encadear as consultas: o resultado de uma vira a entrada da seguinte. Cada busca traz no
máximo 100 empresas. Se a lista vier cortada, peça "continue da próxima página" e a IA
segue de onde parou. Três roteiros prontos para colar e adaptar:

**1. Mapa de alvos num setor e numa UF.**

> "Liste as empresas ativas de fabricação de embalagens plásticas em Santa Catarina, só matrizes, abertas
> antes de 2010. Para as 10 mais antigas, faça a ficha de cada uma e monte uma tabela com a razão social,
> a abertura, a atividade principal, o porte e a situação, com a fonte e a data de cada coluna."

A IA usa **Buscar empresas** e depois a **Ficha da empresa**, uma vez por CNPJ.

**2. Quem compraria: o setor e as companhias abertas dele.**

> "Mostre os setores que o TickerLab acompanha e escolha o mais próximo de embalagens. Nesse setor, quem
> concentra o mercado? Das companhias abertas que aparecem, traga os comparáveis e a receita, o EBITDA e
> a dívida líquida do último ano, numa tabela com a fonte."

A IA usa **Setores e setor**, depois **Comparáveis** e **Demonstrações** das companhias abertas que
aparecerem.

**3. O que mudou desde uma data.**

> "Faça a ficha do CNPJ 00.000.000/0001-00 como era em 31/12/2024 e como é hoje, e diga o que mudou:
> situação, atividade, porte. Se for companhia aberta, compare também as demonstrações dos dois anos."

A IA usa a **Ficha da empresa** duas vezes ("como era em" e hoje) e, se couber, as **Demonstrações**.

Em todo roteiro, peça a fonte e a data de cada informação. Peça à IA que separe o que a base diz do
que ela deduz, e confira antes de levar para um material.

## Limites e cuidados

- **Nada aqui é recomendação de investimento.** O TickerLab organiza dados públicos. A leitura e a
  decisão são suas.
- **Confira a fonte.** Cada informação vem com a fonte e a data. A IA pode resumir errado: antes de usar
  um número num material, confira na fonte indicada.
- **Sem dados de pessoa física.** O conector recusa respostas com dados de pessoa física.
- **O que a sua chave não libera, a IA não vê.** Se faltar alguma coisa, pergunte a quem administra o
  TickerLab na sua empresa.

## Se algo der errado

| Mensagem | O que fazer |
|---|---|
| "A chave não foi aceita" | confira se colou a chave inteira (começa com `tld_`); se ela foi revogada, peça uma nova |
| "O TickerLab não respondeu agora" | espere alguns instantes e tente de novo |
| "Tentativas demais deste endereço" | espere 15 minutos |
| "Este pedido de ligação venceu" ou "A página ficou velha" | volte ao Claude ou ao ChatGPT e comece a ligação de novo |

**Perdeu a chave, ou acha que alguém a viu?** Avise logo quem administra o TickerLab na sua empresa. A
chave é revogada e você recebe outra. Em até um minuto, as IAs ligadas a ela perdem o acesso.
