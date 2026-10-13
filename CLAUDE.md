# TickerLab: regras do repositório (para o Claude e para quem programa aqui)

Este arquivo fica no repositório, que é **público**: nada de senhas, IPs, e-mails ou detalhes do
servidor aqui. O planejamento, as decisões e o histórico ficam numa pasta privada do autor; quando
ela existir no PC, leia o `CLAUDE.md` de lá primeiro.

## O que é

Plataforma de inteligência financeira, por assinatura, de análise de ações (B3 e EUA) e teste de estratégias com dados do passado:
app Streamlit (`app.tickerlab.com.br`), API FastAPI (saúde e webhook do Stripe), site público
estático (`tickerlab.com.br`, gerado em `site/` pelo React de `web/` e por `scripts/gerar_site.py`) e a pesquisa de trading em `trader/` (roda no PC,
fora do app e da imagem Docker). Visão geral e estrutura de pastas: `README.md`.

## Comandos

```powershell
.venv\Scripts\python -m streamlit run app.py              # app em modo local (sem login, SQLite)
.venv\Scripts\python -m pytest -q -n 4 --dist loadgroup  # suíte inteira em 4 processos (~2 min; sem -n, ~12 min)
.venv\Scripts\python -m pytest -q tests/test_planos.py    # um arquivo (prefira durante o trabalho)
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m pyright                            # tipos (src, scripts e telas; ver pyrightconfig.json)
.venv\Scripts\python -m pytest -q -n 4 --dist loadgroup --cov   # suíte + cobertura (mínimo no .coveragerc)
.venv\Scripts\python -m ruff format app.py telas src base tests trader scripts
.venv\Scripts\python -m scripts.gerar_site                # parte do Python do site (fontes, marca, relatório de exemplo, catálogo)
.venv\Scripts\python -m scripts.exportar_conteudo         # conteúdo do Python para o React (web/conteudo/*.json)
cd web; npm run site                                        # páginas, CSS e JS do site em site/ (React; há teste que confere)
.venv\Scripts\python -m alembic upgrade head              # migrações do banco
```

- A suíte inteira demora: rode em segundo plano gravando a saída num arquivo e avise o Tiago.
- O CI (`.github/workflows/testes.yml`) roda `ruff`, `pyright`, os testes com **PostgreSQL de
  verdade** e a **cobertura** (falha abaixo do mínimo do `.coveragerc`), e
  constrói a imagem Docker conferindo que app, API, migrações e login abrem dentro dela.
  Mudança só de texto (lista em `scripts/mudou_so_texto.py`) roda só os testes do README: se um
  teste ou o app passar a ler um texto da lista, tire-o de lá.

## Arquitetura (onde cada coisa deve ficar)

- **`src/` não importa o Streamlit.** As contas, regras e dados ficam em `src/`; a tela (cola com o
  Streamlit) fica em `telas/`, um arquivo ou pasta por grupo de páginas; o `app.py` só configura,
  monta o menu e roda a página. Teste a regra em `src/` e a tela com `AppTest`.
- **Pronto para trocar de interface:** o app fica em Streamlit por enquanto, mas um dia as telas vão
  migrar, uma por vez, para uma interface JavaScript que consome a API. Então tudo o que for construído
  já nasce assim: cálculo, regra, consulta e texto em `src/` (ou `conteudo/`), com entradas e saídas em
  tipos simples (fáceis de virar JSON); gráfico como figura Plotly em `src/graficos.py`; estado que
  importa no banco (preferências da conta), não só no `st.session_state`; endereços de `src/paginas.py`
  estáveis; truque que depende do Streamlit (chave interna, `data-testid`, JS no `st.html`) só quando não
  houver outro jeito, num lugar só e com teste que quebre se o Streamlit mudar. Pense qual rota da API
  exporia a função nova.
- **Nenhum estado mutável num módulo de `telas/`:** o `app.py` roda de novo a cada clique (as
  variáveis dele são de cada sessão), mas um módulo importado roda uma vez por processo (as variáveis
  dele seriam de todos os usuários). Estado de usuário vai no `st.session_state`.
- **Um lugar só para cada verdade:** limites dos planos em `src/planos.py`; mapa de páginas e
  frases em `src/paginas.py`; cores e fontes em `src/marca.py` (identidade visual oficial); textos
  legais em `conteudo/`. O site público lê desses mesmos lugares.
- **Banco:** SQLAlchemy 2 + Alembic. Mudou o modelo → nova migração em `migracoes/versions/`
  (numeração seguida). **Toda consulta filtra pelo `usuario_id`**, com teste de isolamento.
  `hide_parameters=True` (erros do banco não podem levar e-mails para os logs).
- **Cobrança:** Stripe **só em modo de teste** (o código recusa chaves que não sejam
  `sk_test_`/`rk_test_`). O plano só muda pelo webhook (assinatura verificada, idempotente,
  tolerante a eventos fora de ordem).
- **Relatórios em PDF** usam as mesmas funções que a tela; a seção "Limites e cuidados" é
  obrigatória.

## Testes

- Todo comportamento novo vem com teste; todo bug corrigido ganha teste de regressão.
- Testes de tela: `tests/ajudantes_da_conta.py` (`abrir_app`, `ir_para`, `entrar_como`).
  No `AppTest`, `st.switch_page` só vale naquela execução: fixe a página com `ir_para`.
- `monkeypatch` numa função que `telas/` importa pelo nome (`from src.x import f`): troque onde a
  tela usa (`telas.y.f`), não só em `src.x`; o módulo da tela guarda o que recebeu na 1ª importação.
- Sem internet nos testes: use `dados_de_exemplo/` e os dublês já existentes.
- Princípio que tem teste: **sem olhar o futuro** (cortar o futuro não muda o passado).

## Git e GitHub

- **Nunca** commitar na `main` direto, nem `push --force`, nem reescrever histórico publicado.
  Trabalho em ramos `feat/...`, `fix/...`, `docs/...`, `test/...`; entra na `main` por PR com o
  CI verde. Push, PR e merge **só com autorização do Tiago**, uma etapa de cada vez.
- A `main` vai para produção sozinha (deploy automático só de commits com CI verde). Trate cada
  merge como uma publicação.
- Mensagens de commit em português, no formato `tipo: o que mudou` (`feat`, `fix`, `docs`,
  `test`, `perf`, `ci`, `chore`).
- **Várias sessões do Claude podem estar abertas.** Cada uma trabalha na própria cópia
  (`git worktree add ../analise-acoes-NOME -b ramo origin/main`); não mexa num ramo ou numa pasta
  que outra sessão esteja usando, e não use `git add -A` sem conferir o `git status`.

## Segurança e privacidade

- Segredos só em `.env` e `.streamlit/secrets.toml` (fora do Git). Nunca imprimir segredos.
- Logs em JSON sem e-mail nem nome; auditoria só com ids.
- LGPD: exportar e apagar a conta já existem (`src/conformidade.py`); não guardar dado pessoal novo
  sem pensar em exportação e exclusão.
- O repositório não tem licença de código aberto (todos os direitos reservados): não adicionar
  `LICENSE` nem dependência GPL/AGPL.

## Padrões de código

**Leia `docs/padroes-de-codigo.md`** antes de escrever código: funções curtas com uma
responsabilidade, nomes claros em português, sem números mágicos, tipos e docstrings em `src/`,
comentário explica o porquê, refatoração separada de mudança de comportamento. Fique atento ao
código em toda tarefa: deixe o trecho tocado mais limpo do que estava e aponte problemas que
encontrar fora do pedido (sem refatorar a área de outra sessão sem combinar).

## Conteúdo e estilo

- Português do Brasil no código, nos textos e nas mensagens; termos técnicos em inglês quando
  consagrados (Sharpe, backtest, drawdown). Cada conceito explicado na tela.
- **Honestidade com os números:** mostrar o que não funciona; nunca prometer rentabilidade; nada é
  recomendação de investimento.
- Siga o estilo do código ao redor e o guia de padrões.

## `trader/` (pesquisa de trading)

Regras próprias em `trader/CLAUDE.md`. Resumo: só leitura (há teste que
impede enviar ordens), conta de demonstração, critério de aprovação escrito antes dos resultados,
toda execução conta como tentativa, um modelo por vez.
