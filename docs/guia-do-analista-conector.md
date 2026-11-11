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
| Ficha da empresa | a triagem de um CNPJ antes da reunião: cadastro, atividade, onde opera, eventos |
| Comparáveis | empresas parecidas com a do CNPJ |
| Demonstrações | os números publicados, quando a empresa publica |
| Setores e setor | o panorama de um setor |
| O que posso ver | o que a sua chave libera |

Para várias consultas, dá para pedir a informação **como ela era numa data** ("como era em 31/12/2025").

Exemplos de pedidos:

- "Faça a triagem do CNPJ 00.000.000/0001-00 para uma reunião amanhã, com a fonte de cada ponto."
- "Liste empresas de embalagens plásticas em Santa Catarina com mais de 15 anos."
- "Quem são os comparáveis desta empresa? Monte uma tabela."

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
