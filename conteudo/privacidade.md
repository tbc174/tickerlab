# Política de privacidade do TickerLab

Última atualização: 11/10/2026.

O TickerLab é um **projeto educacional**. Esta página explica, em linguagem simples, quais dados pessoais ele guarda, para quê, por quanto tempo e quais são os seus direitos, de acordo com a **LGPD** (Lei Geral de Proteção de Dados, Lei 13.709/2018).

## Quem é responsável

O responsável pelo tratamento dos dados é a pessoa que mantém o projeto (veja o contato no repositório do projeto no GitHub, tbc174/tickerlab). O serviço roda em um servidor próprio, não em uma empresa de nuvem.

## Quais dados guardamos e por quê

| Dado | De onde vem | Para quê |
|---|---|---|
| Nome, **e-mail** e foto da sua conta Google | Login com o Google | Criar e identificar a sua conta |
| Identificador da conta Google | Login com o Google | Reconhecer você nos próximos acessos |
| Ativo, período e opções que você escolhe | Você, no app | Lembrar as suas preferências |
| Favoritos e simulações salvas | Você, no app | Guardar o que você pediu para guardar |
| Relatórios em PDF gerados: tipo, hora, título e os parâmetros usados (ativos, período, estratégia, estilo e seções). O PDF não é guardado | O app, quando você gera um relatório | Contar o limite de relatórios do seu plano e mostrar a biblioteca "Meus relatórios", para você gerar de novo com os mesmos parâmetros. Ao excluir um relatório da biblioteca, o título e os parâmetros são apagados; ficam só o tipo e a hora, que contam o limite. Da sua carteira da B3 não guardamos nem os ativos |
| Planilha de posição da B3, se você enviar (a sua carteira) | Você, em Gerar relatório | Montar o relatório da sua carteira. É lida **só na memória**, não é guardada e não vai para os registros (logs) |
| Plano e situação da assinatura | O app e o Stripe | Liberar o que o seu plano inclui |
| Versão dos termos aceita e data | Você, no aceite | Comprovar que você concordou |
| Registro de ações importantes (ids, sem nome nem e-mail) | O app | Segurança e prestação de contas |

**Não coletamos** a sua senha do Google, nem dados de cartão. Não vendemos dados e não os usamos para publicidade.

## Com quem os dados são compartilhados

- **Google**: faz o login. Ele informa ao app o seu nome, e-mail e foto. O Google trata os seus dados segundo a política dele.
- **Stripe**: processa pagamentos de assinatura. Os dados do cartão são digitados direto no site do Stripe e **nunca passam pelo TickerLab**. Hoje o Stripe está em modo de teste, sem cobrança real.
- **Yahoo Finance e Banco Central**: o app consulta preços e o CDI. Essas consultas não levam os seus dados pessoais.

Fora isso, os dados só são compartilhados se a lei exigir.

## Cookies

O app usa um **cookie** de sessão, necessário para manter você logado depois do login com o Google. Não usamos cookies de rastreamento nem de publicidade.

## Por quanto tempo guardamos

Enquanto a sua conta existir. Quando você apaga a conta, **removemos** o seu perfil, preferências, favoritos, simulações, o registro dos relatórios gerados e assinatura, e encerramos a cobrança no Stripe. Fica apenas um registro técnico de segurança, sem nome nem e-mail, que mostra que uma conta foi apagada.

## Seus direitos (LGPD, art. 18)

Você pode, a qualquer momento:

- **Confirmar** que tratamos seus dados e **acessá-los**;
- **Exportar** uma cópia dos seus dados (arquivo JSON), na página "Meus dados e privacidade";
- **Corrigir** dados incorretos (o nome e a foto vêm do Google; atualize lá e entre de novo);
- **Apagar** a sua conta e os seus dados, na mesma página;
- **Revogar** o consentimento, o que equivale a apagar a conta;
- Pedir informações sobre o compartilhamento de dados.

Para qualquer pedido que não consiga fazer pelo app, use o contato do repositório do projeto.

## Segurança

O acesso ao servidor é restrito, as senhas e chaves ficam fora do código, a comunicação usa HTTPS e cada pessoa só consegue ver os próprios dados. Nenhum sistema é 100% seguro; se houver um incidente que afete você, avisaremos.

## Menores de idade

O TickerLab não é destinado a menores de 18 anos.

## Mudanças

Esta política pode mudar. A versão aceita fica registrada na sua conta e, em mudança relevante, pediremos um novo aceite.
