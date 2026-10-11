# TickerLab

Serviço web (SaaS) de análise de ações e teste de estratégias, feito para a matéria de Python e
Pandas. Digite o ticker de uma empresa, o app busca os dados no Yahoo Finance, analisa com Pandas
e testa estratégias com um motor de backtest escrito à mão, sem biblioteca pronta de backtest.
Tem contas (login com o Google), planos Gratuito e Pro (pagamento em modo de teste do Stripe),
painel de administração e privacidade de acordo com a LGPD.

> Projeto educacional. Nada aqui é recomendação de investimento. Os dados vêm do Yahoo Finance
> e podem ter atraso ou erros. Rentabilidade passada não garante resultado futuro.

![Preço da PETR4 com médias móveis e volume](docs/imagens/preco.png)

## O que o app faz

**Identidade visual:** tema escuro em degraus de cinza-azulado, azul `#2962FF`, o símbolo "Vela T"
(`static/marca/`) e a fonte Manrope servida pelo próprio site, sem Google Fonts. As cores ficam
num lugar só, `src/marca.py`, de onde saem o tema do Streamlit, o CSS e o tema dos gráficos.

No menu do topo, **Início** e **TickerLab Trade** ficam como links diretos, seguidos de 5 grupos
(e um sexto, só para administradores). Termos de uso e Política de privacidade ficam no rodapé.
Cada página tem uma frase dizendo para que serve, e cada número tem uma explicação em português
ao passar o mouse no **?**.

| Grupo | Páginas | Pergunta que respondem |
|---|---|---|
| (direto no menu) | Início, TickerLab Trade | O que é isto? E a pesquisa de trading quantitativo, em que fase está? |
| Analisar | Visão geral, Risco, Retorno mensal, Comparar ativos, Correlação e beta | Como o ativo se comportou: retorno, volatilidade, quedas, calendário, comparação com Ibovespa e S&P 500, beta |
| Estratégias | Backtest, Ranking, Carteira, Experimentos, Fases do mercado | E se eu tivesse seguido uma regra? Qual estratégia foi melhor, descontando a sorte? E com vários ativos? |
| Avançado (Pro) | Aprendizado de máquina, Pairs trading | Um modelo vence a previsão ingênua? Pares de ativos cointegrados |
| Aprender | Guia e glossário (Termos e Privacidade no rodapé) | Como os números são calculados e o que cada termo quer dizer |
| Minha conta | Minhas simulações, Favoritos e momentum, Meus dados e privacidade, Planos e assinatura | O que é meu: simulações guardadas, favoritos, exportar e apagar os dados, plano |
| Administração | Administração | Usuários, planos, assinaturas e registro de ações (só administradores) |

![Evolução do capital: estratégia contra comprar e segurar](docs/imagens/backtest.png)

No Backtest há 12 estratégias (tendência e reversão), custos, stops, CDI, imposto e validação
(treino e teste, walk-forward, mapa de parâmetros, Monte Carlo, teste contra o acaso, Sharpe
deflacionado e PBO). O Ranking compara todas descontando a sorte de escolher a melhor entre
muitas. A Carteira traz rotação, momentum dual, inverso da volatilidade, baixa volatilidade,
canário e paridade hierárquica de risco (HRP).

| Risco | Retorno mensal |
|---|---|
| ![Drawdown](docs/imagens/drawdown.png) | ![Retorno mensal](docs/imagens/retorno-mensal.png) |

## Como rodar no seu computador

Requer Python 3.12.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py
```

Sem a configuração do login (`.streamlit/secrets.toml`), o app roda em **modo local**: sem
contas, com todos os recursos liberados e um banco SQLite em `dados_locais/`. Sem internet (ou se
o Yahoo Finance falhar), marque "Usar dados de exemplo" em "Opções avançadas": ele usa cópias de
5 anos de 13 tickers guardadas em `dados_de_exemplo/`.

Testes e estilo:

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check app.py src tests
```

## Configuração (produção)

Segredos nunca vão para o Git: ficam em arquivos com permissão 600 no servidor.

| Onde | O que |
|---|---|
| `.env` (modelo em `.env.example`) | `TICKERLAB_DATABASE_URL` (PostgreSQL), `TICKERLAB_ADMINS`, chaves do Stripe de **teste** (`rk_test_`/`sk_test_`: chaves de produção são recusadas), `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET`, `TICKERLAB_URL_PUBLICA` |
| `.streamlit/secrets.toml` (modelo em `secrets.toml.example`) | Cliente OAuth do Google (`[auth]`) |

O esquema do banco é criado pelas migrações do Alembic (`migracoes/`), aplicadas sozinhas quando
o contêiner sobe: `python -m alembic upgrade head`.

## Publicar com Docker

O `compose.yaml` sobe dois serviços com a mesma imagem: `tickerlab` (o app, `127.0.0.1:8501`) e
`tickerlab-api` (FastAPI, `127.0.0.1:8000`: `/saude` e o webhook do Stripe). As portas ficam só em
`127.0.0.1`; o acesso de fora vem de um proxy (aqui, o Tailscale).

```bash
mkdir -p dados_locais && touch .streamlit/secrets.toml   # pasta do cache e arquivo de login
docker compose up -d --build
```

Veja `projeto-acoes/stripe.md` (fora deste repositório, na pasta do projeto) para ligar a
cobrança de teste.

## Operação

- **Deploy automático:** `scripts/deploy-automatico.sh`, no cron do servidor (a cada 5 minutos),
  puxa a `main` **só se os testes do GitHub Actions passaram** nesse commit, reconstrói os
  contêineres, espera o app e a API ficarem saudáveis e, se não ficarem, volta sozinho para a
  versão anterior. Log em `~/deploy-tickerlab.log`.
- **Logs:** uma linha de JSON por registro (`TICKERLAB_LOG_FORMATO=json`), sem e-mail nem nome:
  `docker logs tickerlab-api | jq`.
- **Monitor:** o Uptime Kuma verifica `http://127.0.0.1:8501/_stcore/health` (app) e
  `http://127.0.0.1:8000/saude` (API).
- **Carga leve:** `python scripts/carga_leve.py URL --total 300 --simultaneas 20`.
- **Integração contínua:** o GitHub Actions roda `ruff` e os testes (com PostgreSQL de verdade),
  constrói a imagem e confere que o app, a API e o login do Google abrem dentro dela.

## Segurança e privacidade

- Login só com o Google; e-mail não verificado é recusado. Cada pessoa vê apenas os próprios
  dados (toda consulta filtra pelo usuário, com testes de isolamento).
- Webhook do Stripe com assinatura verificada, idempotente e tolerante a eventos fora de ordem.
- Painel de administração confere o papel **no banco** a cada ação e registra tudo em uma
  auditoria que guarda só ids, nunca e-mail ou nome.
- LGPD: aceite dos termos no primeiro acesso (com versão e data), exportação dos dados em JSON e
  exclusão da conta em cascata, encerrando antes a cobrança no Stripe. Os textos estão em
  `conteudo/termos.md` e `conteudo/privacidade.md` (modelos para um projeto educacional, sem
  revisão de advogado).

## Princípios do projeto

- **Sem olhar o futuro.** Toda decisão tomada no fim do dia só vale a partir do dia seguinte, e
  há testes que conferem que cortar o futuro não muda o passado.
- **Honestidade com os números.** O app mostra o que não funcionou: a maioria das estratégias
  não passa no teste contra o acaso, o Sharpe vem com intervalo e o modelo de aprendizado de
  máquina é comparado com uma previsão ingênua.
- **Limites explícitos.** Só 5 anos de dados, viés de sobrevivência, custos e imposto
  simplificados, perna vendida do pairs trading sem o custo do aluguel.
- **Cada conceito explicado.** O glossário (`conteudo/glossario.md`) e as explicações de cada
  estratégia (`conteudo/estrategias.md`) aparecem na tela e são conferidos por testes.

## Estrutura

```
app.py                interface: menu, páginas e telas (só mostra; as contas ficam em src/)
src/
  paginas.py          o mapa do site: grupos, páginas e a frase de cada uma
  planos.py           limites do Gratuito e do Pro (um lugar só)
  autenticacao.py     regras do login com o Google
  banco/              modelo, conexão, usuários e dados por usuário (SQLAlchemy)
  cobranca.py         Stripe: pagamento, portal e eventos (idempotentes)
  api.py              FastAPI: /saude e webhook do Stripe
  administracao.py    painel de administração (permissão conferida no banco)
  conformidade.py     termos, exportar os meus dados e apagar a conta
  auditoria.py        registro de ações sem dados pessoais
  simulacoes.py       salvar e reabrir simulações
  logs.py             logs em texto ou JSON
  dados.py, armazenamento.py, exemplos.py   dados do Yahoo, cache em SQLite e dados de exemplo
  indicadores.py, metricas.py               números básicos e métricas de desempenho
  backtest.py, estrategias.py, protecoes.py motor vetorizado, 12 estratégias e stops
  validacao.py, acaso.py, ranking.py        validação honesta dos resultados
  carteiras.py, hrp.py, experimentos.py, regimes.py, aprendizado.py, pares.py
  graficos.py         gráficos Plotly
conteudo/             glossário, estratégias, termos de uso e política de privacidade
migracoes/            migrações do banco (Alembic)
scripts/              deploy automático, carga leve, imagens do README
tests/                testes automatizados (pytest)
docs/imagens/         figuras deste README (geradas por scripts/gerar_imagens_do_readme.py)
```

## Referências das técnicas

Sharpe probabilístico e deflacionado (Bailey e López de Prado, 2014), PBO (Bailey, Borwein,
López de Prado e Zhu, 2017), barreira tripla, expurgo e embargo, meta-rotulagem e HRP
(López de Prado), variância gerida (Moreira e Muir, 2017), cointegração (Engle e Granger).
As fórmulas foram implementadas a partir da descrição dos artigos e conferidas por testes e
simulações; vale conferi-las nas fontes originais antes de qualquer uso sério.
