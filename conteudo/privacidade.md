# Política de privacidade do TickerLab

Última atualização: 21/10/2026 (versão 9: transferência internacional provedor por provedor, depois da leitura dos contratos: as cláusulas-padrão da ANPD no Stripe, o Google e a Microsoft como responsáveis próprios no login, e o endereço IP de quem só visita o site, visto pela Cloudflare).

O TickerLab é uma **plataforma de inteligência financeira** para quem analisa empresas: análise de ações, teste de estratégias com dados do passado, relatórios sobre empresas, uma base de dados públicos sobre empresas e a área do café. Esta página explica, em linguagem simples, quais dados pessoais ele guarda, para quê, com que base legal, por quanto tempo, com quem divide e quais são os seus direitos, de acordo com a **LGPD** (Lei Geral de Proteção de Dados, Lei 13.709/2018).

## Quem é responsável e como falar com a gente

- **Controlador:** a pessoa que mantém o projeto. Contato geral: **contato@tickerlab.com.br**.
- **Encarregado pela proteção de dados** (LGPD, art. 41): a mesma pessoa. Para qualquer assunto de dados pessoais, escreva para **privacidade@tickerlab.com.br**. Respondemos em até **15 dias**.
- **Onde os dados ficam:** o app e o banco de dados rodam num servidor virtual alugado no Brasil (Hostinger, em São Paulo). As cópias de segurança e a montagem da base de empresas ficam num servidor próprio do responsável, também no Brasil. O banco de dados da sua conta fica no Brasil.

## Quais dados guardamos, para quê e com que base legal

A base legal é o artigo 7º da LGPD: **contrato** (inciso V: o que é preciso para o serviço funcionar), **consentimento** (inciso I: só se você marcar), **legítimo interesse** (inciso IX) e **obrigação legal** (inciso II). "Segurança" é o legítimo interesse de proteger as contas (arts. 7º, IX, e 46).

| Dado | De onde vem | Para quê | Base legal |
|---|---|---|---|
| Nome, **e-mail** e foto da conta que você usa para entrar (Google ou Microsoft) | Login | Criar e identificar a sua conta | Contrato |
| Formas de entrar: o identificador da sua conta no Google ou na Microsoft, o e-mail de cada forma e se ele foi confirmado, quando cada forma foi ligada à conta e a última vez que foi usada | Login | Reconhecer você nos próximos acessos e mostrar, em Meus dados, por onde você entra | Contrato |
| Código de entrada por e-mail: enquanto o código vale, guardamos só uma impressão (SHA-256) do e-mail, outra do código, a validade e o número de tentativas. Nada disso fica ligado à sua conta, e some quando o código vence ou é usado | Você, ao pedir um código | Entrar sem senha, pelo e-mail | Contrato |
| Sessões de login: uma impressão (SHA-256) do cookie de sessão, a forma de entrar, quando a sessão começou, quando vence (30 dias), a última vez usada (com precisão de 1 hora) e quando foi encerrada. **Nunca** o endereço IP nem o aparelho | O app, quando você entra | Manter você conectado por até 30 dias e permitir que você encerre todas as sessões de uma vez, em Meus dados | Contrato; segurança |
| Origem do cadastro: a campanha pela qual você chegou (`utm_source`, `utm_medium`, `utm_campaign`, `utm_content` e o código `ref` de um parceiro) e a data da primeira visita, lidos do cookie próprio `tl_origem` no seu primeiro login. Só a primeira origem fica. Nada disso vai para o Google, a Meta ou o parceiro: ele recebe só números somados ("12 cadastros") | O site, quando você chega por um link de campanha | Medir a campanha de lançamento e pagar comissão a parceiros sem rastrear você | Legítimo interesse |
| Ativo, período e opções que você escolhe (inclusive a configuração salva do estúdio de relatórios e se você já viu o tutorial) | Você, no app | Lembrar as suas preferências | Contrato |
| Parâmetros de análise do Research (o seu padrão e os de cada ativo), com o histórico de versões | Você, na página Parâmetros | Calcular as análises do jeito que você escolheu e permitir voltar a uma versão anterior | Contrato |
| Alertas do Research (nome e as condições de cada regra) | Você, na página Alertas | Avaliar as suas regras nos ativos das suas listas | Contrato |
| Fotografia da carteira no Research: o código de cada ativo e o peso dele em %. **Nunca** a quantidade nem o valor em reais. Só com o seu consentimento próprio, cuja versão e hora ficam registradas | Você, na página Minha carteira (Research), a partir da planilha da B3 (lida só na memória) | Ordenar o Research pelo tamanho das suas posições e montar a Newsletter da carteira. Ao revogar o consentimento, a fotografia é apagada na hora | Consentimento |
| Inscrição na Newsletter por e-mail (a lista, a frequência e a versão e a hora do consentimento) e o registro de cada envio (período e situação) | Você, na página Newsletter | Mandar a edição na frequência escolhida, uma vez por período. Para sair: o link em cada e-mail ou a página Newsletter | Consentimento |
| Inscrição nas Novidades e ofertas por e-mail (a versão e a hora do consentimento) e o registro de cada envio (a campanha e a situação). **Só se você marcar** a caixa própria, que começa desmarcada e não é condição para usar o app | Você, no primeiro acesso ou em Meus dados | Mandar por e-mail novidades e ofertas **do próprio TickerLab** (lançamentos, recursos novos e promoções dos planos), cada campanha uma vez só. Para sair: o link em cada e-mail ou Meus dados | Consentimento |
| Listas do Research (nome e códigos dos ativos que você acompanha) | Você, na página Acontecimentos | Mostrar os eventos das empresas da lista. Não são posições nem valores da sua carteira | Contrato |
| Favoritos e simulações salvas | Você, no app | Guardar o que você pediu para guardar | Contrato |
| Tentativas do backtest: para cada ativo, uma impressão (SHA-256) de cada configuração diferente que você rodou (estratégia, parâmetros, proteções, custo e período) e a hora da primeira vez. **Nunca** a configuração em si, os resultados ou valores | O app, quando você roda um backtest | Contar quantas variações você testou e descontar isso no teste contra a sorte da ficha "Foi sorte?" | Contrato |
| Pulse: a hora em que você abriu o Pulse pela última vez e, para cada estratégia salva, o veredito da ficha "Foi sorte?" que você já viu ("passou", "não passou" ou "inconclusivo") | O app, quando você abre o Pulse | Mostrar só o que mudou nos seus ativos desde a sua última visita | Contrato |
| Diário de Teses: o texto de cada anotação que você escreve sobre um ativo, o código do ativo, a data e os backtests salvos que você ligou a ela. Não escreva ali dados pessoais (seus ou de outras pessoas) | Você, na página Diário de Teses | Guardar o que você pensava de cada ativo e mostrar no Pulse quando o veredito de um backtest ligado mudar. Cada anotação pode ser apagada a qualquer momento; apagar um backtest tira só a ligação | Contrato |
| Links compartilhados: o que você escolheu compartilhar (a ficha "Foi sorte?" como estava na hora, ou a ligação com um PDF guardado na biblioteca), o título, as datas de criação, de vencimento e de revogação, quantas vezes o link foi aberto e quando foi a última vez. Do link, guardamos só uma impressão (SHA-256), nunca o link; de quem abre, nada (nem o endereço IP, que é usado só na memória, por um minuto, para limitar pedidos em excesso) | Você, no botão "Compartilhar" | Mostrar o que você compartilhou a quem tiver o link, até o prazo que você escolheu ou até você revogar em Meus dados | Contrato |
| Relatórios em PDF gerados: tipo, hora, título e os parâmetros usados (ativos, período, estratégia, estilo e seções) | O app, quando você gera um relatório | Contar o limite de relatórios do seu plano e mostrar a biblioteca "Meus relatórios", para você gerar de novo com os mesmos parâmetros. Ao excluir um relatório da biblioteca, o título e os parâmetros são apagados; ficam só o tipo e a hora, que contam o limite | Contrato |
| O **PDF original** de cada relatório, como foi entregue, com o código de conferência (SHA-256) e as versões das fórmulas e dos dados. **Nunca** o do relatório "Minha carteira": da planilha da B3 enviada para o relatório não guardamos nem os ativos | O app, quando você gera um relatório | Você baixar depois o arquivo exato que recebeu ("Original", na biblioteca). Cada PDF fica guardado por **1 ano**, até o número do seu plano (os mais antigos saem); ao excluir o relatório da biblioteca, o PDF é apagado na hora | Contrato |
| Planilha de posição da B3, se você enviar (a sua carteira). A carteira de exemplo é fictícia | Você, em Gerar relatório | Montar o relatório da sua carteira. É lida **só na memória**, não é guardada e não vai para os registros (logs) | Contrato |
| Plano e situação da assinatura e o identificador do seu cadastro de cliente no Stripe | O app e o Stripe | Liberar o que o seu plano inclui | Contrato |
| Versão dos termos aceita e data | Você, no aceite | Comprovar que você concordou | Obrigação legal e contrato |
| Registro de ações importantes (ids, sem nome nem e-mail) | O app | Segurança e prestação de contas | Segurança |
| Registros técnicos de acesso: cada pedido ao site e ao app passa pela Cloudflare e pelo servidor, que registram o endereço IP, a hora, a página pedida e o navegador, sem o seu nome. Ficam por tempo limitado, e por 6 meses quando a lei exigir (Marco Civil da Internet, art. 15) | A Cloudflare e o servidor | Segurança e investigação de falhas e ataques | Segurança; obrigação legal |

**Não coletamos** a sua senha do Google ou da Microsoft (o login acontece lá), nem dados de cartão. Não montamos perfil de navegação, não usamos pixel de publicidade, não vendemos dados e não os usamos para publicidade de terceiros. O seu e-mail só recebe propaganda do próprio TickerLab se você pedir (Novidades e ofertas, acima).

## Inteligência artificial nos relatórios

Os textos dos relatórios sobre empresas são escritos por um **modelo de linguagem** (da Anthropic, EUA) a partir dos dados da base e de trechos de documentos públicos, e cada afirmação é conferida por código contra a fonte antes de ser publicada. O que vai ao modelo são **dados públicos sobre empresas**, em lote, fora do servidor do app. **Nenhum dado da sua conta** (o que você escolhe, salva, escreve ou compartilha) é enviado a ele. Pelos termos do provedor, lidos em 19/10/2026, ele não treina modelos com o que enviamos e apaga o que recebeu em até 30 dias, salvo o que o provedor retém por segurança quando um filtro sinaliza o conteúdo. Nenhuma decisão sobre você é tomada por esse modelo.

## Com quem os dados são compartilhados

- **Google**: faz o login, se você entrar com o Google. Ele informa ao app o seu nome, e-mail e foto. O Google trata os seus dados segundo a política dele.
- **Microsoft**: faz o login, se você entrar com a Microsoft (quando essa forma aparecer na tela de entrada). Informa ao app o mesmo que o Google e trata os seus dados segundo a política dela.
- **Stripe**: processa pagamentos de assinatura. Ao criar o seu cadastro de cliente, recebe o seu e-mail e o identificador da sua conta. Os dados do cartão são digitados direto no site do Stripe e **nunca passam pelo TickerLab**. Hoje o Stripe está em modo de teste, sem cobrança real.
- **Cloudflare**: entrega o site e o app nos endereços tickerlab.com.br e app.tickerlab.com.br (rede e proteção contra ataques). Como todo provedor de rede, ela vê o endereço IP e os dados técnicos da conexão e mantém registros de acesso.
- **Hostinger**: fornece o servidor virtual alugado; os dados do app ficam no disco desse servidor, em São Paulo. As **cópias de segurança** do banco de dados ficam no servidor próprio do responsável, também no Brasil, **cifradas** (só o responsável tem a chave que as abre).
- **Resend**: envia o **código de entrada** por e-mail, quando você pede para entrar com o e-mail (recebe o seu e-mail e o código de 6 dígitos), e envia a Newsletter e as Novidades e ofertas por e-mail, **só se você se inscrever**. Nas Novidades, recebe o seu e-mail e o texto da campanha, igual para todos. Na Newsletter, recebe o seu e-mail e o conteúdo da edição: os códigos dos ativos da lista escolhida (se for a carteira, os ativos dela, sem os pesos) e os documentos públicos de cada um. Não recebe os seus parâmetros nem outros dados da conta. O Resend guarda os e-mails enviados enquanto a conta do TickerLab nele existir.
- **Anthropic**: recebe só documentos públicos e dados da base de empresas para escrever os relatórios (seção acima); nunca dados da sua conta.
- **Fontes públicas** (CVM, SEC, Banco Central, IBGE, Receita Federal, PGFN, CGU, tribunais de contas, agências reguladoras, INMET, CONAB, USDA, CFTC e outras): o TickerLab baixa delas documentos e tabelas públicos sobre empresas, economia e clima. Essas consultas não levam os seus dados pessoais. A SEC (a comissão de valores mobiliários dos EUA) exige que cada consulta traga um e-mail de contato: vai o do TickerLab, nunca o seu.
- **Quem tiver um link que você criou**: vê só o que você compartilhou por ele (a ficha "Foi sorte?" ou o PDF), **sem o seu nome nem o seu e-mail**, até o prazo de 7, 30 ou 90 dias ou até você revogar em Meus dados. Quem recebe pode repassar o link: compartilhe só com quem você escolher.

Fora isso, os dados só são compartilhados se a lei exigir.

## Transferência internacional

Google, Microsoft, Stripe, Cloudflare, Resend e Anthropic são empresas dos Estados Unidos e podem tratar lá os dados que recebem. Quando é você quem escolhe o serviço (entrar com o Google, com a Microsoft ou com um código por e-mail, pagar pelo Stripe, inscrever-se para receber e-mails, abrir o app), a transferência é **necessária para executar o que você pediu** (LGPD, art. 33, IX). No login, o Google e a Microsoft tratam a sua conta como responsáveis próprios, pela política de cada um. O contrato do Stripe traz também as cláusulas-padrão da ANPD (LGPD, art. 33, II, "b"; Resolução CD/ANPD 19/2024). À Anthropic não vai dado pessoal seu: só documentos públicos e dados da base de empresas. Quem só visita o site, sem conta, tem o endereço IP e os dados técnicos da conexão vistos pela Cloudflare, que entrega o site e o protege (seção acima). Os contratos da Cloudflare, do Resend e da Anthropic trazem só as cláusulas-padrão da União Europeia, que a ANPD ainda não reconheceu como equivalentes às brasileiras (Resolução CD/ANPD 19/2024, art. 18); assim que tiver CNPJ, o TickerLab vai pedir a eles as cláusulas-padrão da ANPD. O banco de dados da sua conta e as cópias de segurança ficam no Brasil. Esta seção segue o modelo de descrição pública da Resolução CD/ANPD 19/2024 (art. 17, § 2º).

## Cookies e armazenamento no navegador

- **`__Host-tl_sessao`**: o cookie de sessão do app, necessário para manter você conectado. Dura **30 dias** desde a entrada, só vai por HTTPS, não é acessível a scripts e é apagado quando você sai. No app clássico (`/classico`), o cookie de sessão do Streamlit faz o mesmo papel.
- **`tl_origem`**: cookie próprio do site, gravado só quando você chega por um link de campanha; é lido no seu primeiro login para registrar a origem do cadastro (tabela acima).
- **Preferências de tela** (tema claro ou escuro, favoritos do menu, animação do fundo, a janela do Pulse que você já viu): ficam no seu navegador (`localStorage` e `sessionStorage`), sem dado pessoal, e não vão ao servidor.
- A Cloudflare pode usar cookies técnicos de segurança.

Não usamos cookies de rastreamento nem de publicidade, e o site e o app não carregam ferramentas de análise de terceiros.

## A base de dados de empresas e as pessoas que aparecem nela

A base do TickerLab é sobre **empresas**: documentos e cadastros públicos (CVM, SEC, Banco Central, Receita Federal, PGFN, CGU, tribunais de contas, agências reguladoras e outros). Pessoas aparecem nela só pela **função que exercem no mercado**, e com limites:

- Nas negociações de ações informadas à CVM e à SEC por diretores, conselheiros e controladores, guardamos **o cargo, nunca o nome** da pessoa.
- Os sócios e administradores do cadastro público do CNPJ **não aparecem no app**. Na montagem da base, cada um vira só um identificador interno, sem nome e com o CPF mascarado como a Receita Federal publica, usado para ligar empresas entre si ("têm sócio em comum").
- O app **não tem busca por nome de pessoa nem por CPF**, não mostra fichas de pessoas e nunca cruza os dados da base com os dados das contas.
- O que mostramos sobre empresas são **fatos com data e fonte**, nunca acusações. Uma empresa que se achar retratada de forma errada pode escrever para contato@tickerlab.com.br; a correção sai com errata visível.

Se você é administrador, conselheiro ou sócio de uma empresa e quer saber o que a base guarda sobre o seu papel nela, ou se opor a isso, escreva para **privacidade@tickerlab.com.br** (LGPD, art. 18).

## Por quanto tempo guardamos

Enquanto a sua conta existir. Os códigos de entrada por e-mail somem quando vencem ou são usados; as sessões de login vencidas ou encerradas são apagadas 90 dias depois, por uma rotina diária (sem endereço IP em nenhum momento); os códigos de entrada vencidos são apagados em até 1 dia; os registros técnicos de acesso ficam por tempo limitado (tabela acima).

Quando você apaga a conta, **removemos** o seu perfil, as formas de entrar e as sessões de login, a origem do cadastro, preferências, favoritos, simulações, as listas, os parâmetros, os alertas e a fotografia da carteira do Research, a inscrição na Newsletter e nas Novidades e o registro dos envios, o registro dos relatórios gerados, os PDFs originais guardados, as tentativas do backtest, o registro do Pulse, as anotações do Diário de Teses, os links compartilhados e a assinatura, e encerramos a cobrança no Stripe. Ficam apenas registros técnicos de segurança, sem nome nem e-mail: que uma conta foi apagada e, se for o caso, quando o consentimento da carteira, o da Newsletter e o das Novidades por e-mail foram dados e revogados (para provar que existiram).

**Cópias de segurança:** uma vez por dia o banco de dados é copiado, cifrado, para outro servidor, para que os dados não se percam se o servidor principal falhar. Cada cópia é apagada depois de **14 dias**. Por isso, o que você apagar (ou a conta inteira) ainda fica nessas cópias por até 14 dias, sem uso, e depois some delas também.

## Seus direitos (LGPD, art. 18)

Você pode, a qualquer momento:

- **Confirmar** que tratamos seus dados e **acessá-los**;
- **Exportar** uma cópia dos seus dados (arquivo JSON) e os PDFs originais guardados (arquivo .zip), na página "Meus dados e privacidade"; isso vale também como portabilidade;
- **Corrigir** dados incorretos (o nome e a foto vêm do Google ou da Microsoft; atualize lá e entre de novo);
- **Apagar** a sua conta e os seus dados, na mesma página;
- **Revogar** o consentimento: o da carteira, o da Newsletter e o das Novidades, a qualquer momento, sem perder a conta; o do uso da conta em si equivale a apagá-la;
- **Encerrar a sessão** neste aparelho ("Sair") e em todos os aparelhos de uma vez, em Meus dados;
- Pedir informações sobre o compartilhamento de dados e sobre a base legal de cada tratamento;
- **Reclamar à ANPD** (Autoridade Nacional de Proteção de Dados) se achar que não cumprimos a lei.

Se você não quiser aceitar uma versão nova dos termos, continua podendo baixar uma cópia dos seus dados e apagar a conta, na mesma tela do aceite.

Para qualquer pedido que não consiga fazer pelo app, escreva para **privacidade@tickerlab.com.br**. Respondemos em até 15 dias.

## Segurança e incidentes

O acesso ao servidor é restrito, as senhas e chaves ficam fora do código, a comunicação usa HTTPS, as cópias de segurança são cifradas e cada pessoa só consegue ver os próprios dados. Nenhum sistema é 100% seguro. Se houver um incidente de segurança que possa causar risco ou dano a você, comunicamos a ANPD e você em até **3 dias úteis** depois de sabermos, dizendo o que aconteceu, quais dados foram afetados e o que fazer (LGPD, art. 48; Resolução CD/ANPD 15/2024).

## Menores de idade

O TickerLab não é destinado a menores de 18 anos.

## Mudanças

Esta política pode mudar. A versão aceita fica registrada na sua conta e, em mudança relevante, pediremos um novo aceite.
