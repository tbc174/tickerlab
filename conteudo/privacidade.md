# Política de privacidade do TickerLab

Última atualização: 12/10/2026 (versão 4: cópias de segurança).

O TickerLab é um **projeto educacional**. Esta página explica, em linguagem simples, quais dados pessoais ele guarda, para quê, por quanto tempo e quais são os seus direitos, de acordo com a **LGPD** (Lei Geral de Proteção de Dados, Lei 13.709/2018).

## Quem é responsável

O responsável pelo tratamento dos dados é a pessoa que mantém o projeto (contato: **contato@tickerlab.com.br**). O app e o banco de dados rodam em servidores administrados por essa pessoa: um servidor próprio e um servidor virtual alugado no Brasil (Hostinger, em São Paulo). O banco de dados fica no Brasil.

## Quais dados guardamos e por quê

| Dado | De onde vem | Para quê |
|---|---|---|
| Nome, **e-mail** e foto da sua conta Google | Login com o Google | Criar e identificar a sua conta |
| Identificador da conta Google | Login com o Google | Reconhecer você nos próximos acessos |
| Ativo, período e opções que você escolhe (inclusive a configuração salva do estúdio de relatórios e se você já viu o tutorial) | Você, no app | Lembrar as suas preferências |
| Parâmetros de análise do Research (o seu padrão e os de cada ativo), com o histórico de versões | Você, na página Parâmetros | Calcular as análises do jeito que você escolheu e permitir voltar a uma versão anterior |
| Alertas do Research (nome e as condições de cada regra) | Você, na página Alertas | Avaliar as suas regras nos ativos das suas listas |
| Fotografia da carteira no Research (plano Pro): o código de cada ativo e o peso dele em %. **Nunca** a quantidade nem o valor em reais. Só com o seu consentimento próprio, cuja versão e hora ficam registradas | Você, na página Minha carteira (Research), a partir da planilha da B3 (lida só na memória) | Ordenar o Research pelo tamanho das suas posições e montar a Newsletter da carteira. Ao revogar o consentimento, a fotografia é apagada na hora |
| Inscrição na Newsletter por e-mail (a lista, a frequência e a versão e a hora do consentimento) e o registro de cada envio (período e situação) | Você, na página Newsletter | Mandar a edição na frequência escolhida, uma vez por período. Para sair: o link em cada e-mail ou a página Newsletter |
| Listas do Research (nome e códigos dos ativos que você acompanha) | Você, na página Acontecimentos | Mostrar os eventos das empresas da lista. Não são posições nem valores da sua carteira |
| Favoritos e simulações salvas | Você, no app | Guardar o que você pediu para guardar |
| Relatórios em PDF gerados: tipo, hora, título e os parâmetros usados (ativos, período, estratégia, estilo e seções). O PDF não é guardado | O app, quando você gera um relatório | Contar o limite de relatórios do seu plano e mostrar a biblioteca "Meus relatórios", para você gerar de novo com os mesmos parâmetros. Ao excluir um relatório da biblioteca, o título e os parâmetros são apagados; ficam só o tipo e a hora, que contam o limite. Da planilha da B3 enviada para o relatório não guardamos nem os ativos |
| Planilha de posição da B3, se você enviar (a sua carteira). A carteira de exemplo é fictícia | Você, em Gerar relatório | Montar o relatório da sua carteira. É lida **só na memória**, não é guardada e não vai para os registros (logs) |
| Plano e situação da assinatura | O app e o Stripe | Liberar o que o seu plano inclui |
| Versão dos termos aceita e data | Você, no aceite | Comprovar que você concordou |
| Registro de ações importantes (ids, sem nome nem e-mail) | O app | Segurança e prestação de contas |

**Não coletamos** a sua senha do Google, nem dados de cartão. Não vendemos dados e não os usamos para publicidade.

## Com quem os dados são compartilhados

- **Google**: faz o login. Ele informa ao app o seu nome, e-mail e foto. O Google trata os seus dados segundo a política dele.
- **Stripe**: processa pagamentos de assinatura. Os dados do cartão são digitados direto no site do Stripe e **nunca passam pelo TickerLab**. Hoje o Stripe está em modo de teste, sem cobrança real.
- **Cloudflare**: entrega o site e o app nos endereços tickerlab.com.br e app.tickerlab.com.br (rede e proteção contra ataques). Como todo provedor de rede, ela vê o endereço IP e os dados técnicos da conexão.
- **Hostinger**: fornece o servidor virtual alugado; os dados do app ficam no disco desse servidor, em São Paulo. As **cópias de segurança** do banco de dados ficam no servidor próprio do responsável, também no Brasil, **cifradas** (só o responsável tem a chave que as abre).
- **Resend**: envia a Newsletter por e-mail, **só se você se inscrever**. Recebe o seu e-mail e o conteúdo da edição: os códigos dos ativos da lista escolhida (se for a carteira, os ativos dela, sem os pesos) e os documentos públicos de cada um. Não recebe os seus parâmetros nem outros dados da conta.
- **Yahoo Finance e Banco Central**: o app consulta preços e o CDI. Essas consultas não levam os seus dados pessoais.
- **CVM e SEC** (a comissão de valores mobiliários dos EUA): o TickerLab baixa, uma vez por dia, os documentos públicos que as empresas entregam a elas (eventos, demonstrações e negociações de ações por diretores, conselheiros e controladores; dessas, guardamos só o cargo, nunca o nome da pessoa). A SEC exige que cada consulta traga um e-mail de contato: vai o do TickerLab, nunca o seu. Essas consultas não levam os seus dados pessoais.

Fora isso, os dados só são compartilhados se a lei exigir.

## Cookies

O app usa um **cookie** de sessão, necessário para manter você logado depois do login com o Google. A Cloudflare pode usar cookies técnicos de segurança. Não usamos cookies de rastreamento nem de publicidade, e o site público não usa ferramentas de análise de terceiros.

## Por quanto tempo guardamos

Enquanto a sua conta existir. Quando você apaga a conta, **removemos** o seu perfil, preferências, favoritos, simulações, as listas, os parâmetros, os alertas e a fotografia da carteira do Research, a inscrição na Newsletter e o registro dos envios, o registro dos relatórios gerados e a assinatura, e encerramos a cobrança no Stripe. Ficam apenas registros técnicos de segurança, sem nome nem e-mail: que uma conta foi apagada e, se for o caso, quando o consentimento da carteira e o da Newsletter por e-mail foram dados e revogados (para provar que existiram).

**Cópias de segurança:** uma vez por dia o banco de dados é copiado, cifrado, para outro servidor, para que os dados não se percam se o servidor principal falhar. Cada cópia é apagada depois de **14 dias**. Por isso, o que você apagar (ou a conta inteira) ainda fica nessas cópias por até 14 dias, sem uso, e depois some delas também.

## Seus direitos (LGPD, art. 18)

Você pode, a qualquer momento:

- **Confirmar** que tratamos seus dados e **acessá-los**;
- **Exportar** uma cópia dos seus dados (arquivo JSON), na página "Meus dados e privacidade";
- **Corrigir** dados incorretos (o nome e a foto vêm do Google; atualize lá e entre de novo);
- **Apagar** a sua conta e os seus dados, na mesma página;
- **Revogar** o consentimento, o que equivale a apagar a conta;
- Pedir informações sobre o compartilhamento de dados.

Para qualquer pedido que não consiga fazer pelo app, escreva para **contato@tickerlab.com.br**.

## Segurança

O acesso ao servidor é restrito, as senhas e chaves ficam fora do código, a comunicação usa HTTPS, as cópias de segurança são cifradas e cada pessoa só consegue ver os próprios dados. Nenhum sistema é 100% seguro; se houver um incidente que afete você, avisaremos.

## Menores de idade

O TickerLab não é destinado a menores de 18 anos.

## Mudanças

Esta política pode mudar. A versão aceita fica registrada na sua conta e, em mudança relevante, pediremos um novo aceite.
