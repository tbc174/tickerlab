# TickerLab: regras do repositório (para qualquer IA e para quem programa aqui)

**Este é o livro de regras único do repositório.** Vale para todas as IAs que trabalham aqui (hoje o
Claude, da Anthropic, e o ChatGPT/Codex, da OpenAI) e para pessoas. O `CLAUDE.md` só importa este
arquivo e acrescenta o que depende das ferramentas do Claude; regra nova entra **aqui**, nunca só no
arquivo de uma IA (ver "Várias IAs no mesmo projeto").

Este arquivo fica no repositório, que é **público**: nada de senhas, IPs, e-mails ou detalhes do
servidor aqui. O planejamento, as decisões e o histórico ficam numa pasta privada do autor; quando
ela existir no PC, leia o `AGENTS.md` de lá primeiro.

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
.venv\Scripts\python -m pyright                            # tipos (src, scripts, telas e base; ver pyrightconfig.json)
.venv\Scripts\python -m pytest -q -n 4 --dist loadgroup --cov   # suíte + cobertura (mínimo no .coveragerc)
.venv\Scripts\python -m ruff format app.py telas src base tests trader scripts migracoes
.venv\Scripts\python -m scripts.conferir_codigo_morto --gravar   # regrava a lista do vulture (código morto: não piorar)
.venv\Scripts\python -m scripts.gerar_site                # parte do Python do site (fontes, marca, relatório de exemplo, catálogo)
.venv\Scripts\python -m scripts.exportar_conteudo         # conteúdo do Python para o React (web/conteudo/*.json)
cd web; npm run site                                        # páginas, CSS e JS do site em site/ (React; há teste que confere)
.venv\Scripts\python -m alembic upgrade head              # migrações do banco
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-estudos.txt   # cadernos de estudos/ (Jupyter); só no PC
```

- A suíte inteira demora: rode em segundo plano gravando a saída num arquivo e avise o Tiago.
- O CI (`.github/workflows/testes.yml`) roda `ruff`, `pyright`, o `vulture` (código morto: não piorar), os testes com
  **PostgreSQL de verdade** e a **cobertura** (falha abaixo do mínimo do `.coveragerc`), e
  constrói a imagem Docker conferindo que app, API, migrações e login abrem dentro dela.
  Os testes rodam em 5 máquinas ao mesmo tempo (3 partes do app, só com o `requirements.txt`, e 2
  do trader; `scripts/repartir_testes.py`); para rodar uma parte no PC: `pytest --parte=2/3` ou
  `pytest --parte=trader-1/2`. Teste
  novo do trader se chama `test_trader_*` ou `test_c1_*`. Partes desiguais: refaça os tempos com
  `pytest -n 4 --dist loadgroup --gravar-duracoes` e faça o commit do `tests/duracoes.json`.
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

## Casa em ordem (o que o CI tranca desde 05/11/2026)

Pedido do Tiago (05/11/2026): crescer organizado, sem deixar coisa sem uso. Quatro testes cobram:

- **Raiz trancada:** arquivo ou pasta nova na raiz só entra na lista de `tests/test_raiz_do_repositorio.py`
  (diga o porquê no PR). O que não é do repositório fica na pasta privada ou no `.gitignore`; o aviso do
  início da sessão (hook do Claude) lista o que estiver solto na raiz. Nunca `git add -A`.
- **Dependência pinada é dependência usada:** `tests/test_requirements.py` falha se um pin dos
  `requirements*.txt` não é importado pelo código nem puxado, pelos metadados, por um pin usado. O que se usa
  sem `import` (comando, plugin, motor carregado pelo nome) entra em `EXCECOES`, com o motivo. Pin repetido
  falha. `requirements-estudos.txt` (Jupyter dos cadernos de `estudos/`) é só do PC: não vai ao CI nem à
  imagem. Tirou um pacote do código: tire o pin.
- **Todo `scripts/*.py` diz quem o roda:** a docstring termina com uma linha `Roda: ...` (cron do VPS, cron de
  casa pelo X.sh, CI, hook, manual, outro script...), com o horário quando é agendado
  (`tests/test_scripts_dizem_quem_roda.py`). Script sem uso registrado sai, ou ganha "sem uso registrado em
  DD/MM/AAAA" para a próxima faxina decidir.
- **Código morto não piora:** o CI roda o `vulture` (`scripts/conferir_codigo_morto.py`) e compara com
  `tests/arquivos/vulture_esperado.txt`; item novo falha. Tirou código morto, ou apareceu um falso positivo
  com motivo: `python -m scripts.conferir_codigo_morto --gravar` e o arquivo vai no commit (de novo depois
  do `juntar_main`).

## Git e GitHub

- **Nunca** commitar na `main` direto, nem `push --force`, nem reescrever histórico publicado.
  Trabalho em ramos `feat/...`, `fix/...`, `docs/...`, `test/...`; entra na `main` por PR com o
  CI verde. Push e PR são livres. **Merge:** com CI verde e dentro de um pedido do Tiago ou de um plano
  aceito, a sessão mescla e registra a decisão (alçadas da ADR 0101, na pasta privada). **Áreas sensíveis**
  (login, contas e admins, cobrança, limites dos planos, migração, segredos, apagar dado) e **nível 1**
  (texto público, licença de dado, LGPD, nome de pessoa) também mesclam sozinhos (ADR 0101, Emenda 3,
  05/11/2026), mas só depois de: (1) a revisão de segurança (`revisar-seguranca-pr`) sem achado
  bloqueante, com o resumo no corpo do PR; (2) a revisão cruzada por outro modelo sem P0 nem P1 aberto.
  Seguem como na Emenda 2: migração que só acrescenta (tabela, coluna anulável ou com padrão, índice) e tem
  `downgrade` testado precisa só da revisão de segurança; correção de digitação ou de link quebrado em texto
  público já aprovado, sem mudar sentido, número, preço, promessa, nome nem texto legal, não precisa de nenhuma.
  O Tiago fica sabendo pelo registro e pelo relato do dia, não aprovando. **Continua só do Tiago**
  (não é merge de PR): gasto, inclusive o PR que liga um gasto novo; contrato; e-mail ou pedido a
  terceiro; segredo num servidor; e o que leva o nome ou o CNPJ dele. O resto do nível 1 que não é merge
  passa pela Diretoria (abaixo).
- **Ordens da Diretoria:** a conversa da Diretoria que toca a fila única pode mandar ordens às outras sessões
  (mensagem entre sessões ou, para a IA que não recebe mensagens, escrita na passagem da tarefa), citando as
  palavras do Tiago (autorização dele em 20/10/2026). Essa ordem vale como a do Tiago para push, PR, merge
  com auto-merge (nas áreas sensíveis, com as duas revisões acima) e o próximo passo da passagem. **O "pode"
  do nível 1 que não é merge** (rodar algo no servidor de casa ou no VPS fora da rotina, repetir carga, mudar o
  crontab, texto público, licença de dado, apagar dado com cópia conferida) **é dado pela Diretoria** (ADR 0101,
  Emenda 4, 05/11/2026; Tiago: "não quero mais dar pode, você a partir de agora pode tomar essa decisão"): a
  sessão pede à Diretoria por mensagem, com a recomendação; a resposta dela, citando a Emenda 4, vale como o
  "pode" do Tiago na conversa de destino, e a Diretoria registra cada uma em `decisoes-delegadas.md`. Para o que
  continua só do Tiago (gasto, contrato, CNPJ, terceiro, Stripe fora do modo de teste, dado pessoal novo,
  segredo num servidor, a lista do lançamento e o que leva o nome ou o CNPJ dele), só vale o que ele escreve na
  própria conversa.
- **Merge automático:** quando o merge está autorizado (pela alçada ou pelo Tiago), ative o auto-merge do PR (ele
  mescla sozinho quando o CI fica verde), em vez de esperar o CI para voltar e mesclar. CI vermelho
  não mescla: corrija e faça o push de novo.
- **O PR é de quem abriu até o merge:** o auto-merge não acorda ninguém quando o CI fica vermelho. Quem abre o PR
  acompanha o CI até o merge (no Claude, o Auto-fix do app; nas outras IAs, `gh pr checks <número> --watch`) e não
  fecha a conversa nem dá a tarefa por pronta antes do merge.
- **Agente da fila:** os ramos `claude/agente-*` são de um agente na nuvem que resolve pendências
  fáceis. O passo "Portão do agente" do CI (`scripts/portao_do_agente.py`) deixa entrar sozinho só
  PR de teste e doc; outro código espera o rótulo `revisado` posto por uma pessoa (e de novo a cada
  commit novo); área sensível falha sempre. Não ponha `revisado` sem ler o diff.
- A `main` vai para produção sozinha (deploy automático só de commits com CI verde). Trate cada
  merge como uma publicação.
- Mensagens de commit em português, no formato `tipo: o que mudou` (`feat`, `fix`, `docs`,
  `test`, `perf`, `ci`, `chore`).
- **Várias sessões podem estar abertas, de mais de uma IA.** Cada uma trabalha na própria cópia
  (`git worktree add ../analise-acoes-NOME -b ramo origin/main`); não mexa num ramo ou numa pasta
  que outra sessão esteja usando, e não use `git add -A` sem conferir o `git status`.
- **Tarefa fechada = cópia e ramo apagados** (05/11/2026). Depois do merge, quem fechou a tarefa apaga a
  cópia (`git worktree remove ../analise-acoes-NOME`) e o ramo local (`git branch -D ramo`; o GitHub apaga o
  remoto ao mesclar). O `/fechar-tarefa` e o `fechar-e-seguir` fazem isso; o aviso do início da sessão (hook do
  Claude) lista as cópias de PR já mesclado que ficaram.
- **PR parado há mais de 7 dias** (sem commit, comentário nem CI pendente) não fica aberto esperando: vira
  linha da fila (com o que falta e quem continua) ou fecha, com um comentário dizendo por quê. O
  `arrumar-fila` confere e propõe; o PR do Dependabot conta também.
- **Pastas geradas (`site/`, `novo/`, `web/conteudo/`) não se juntam à mão: se refazem.** Ramo atrás da
  `main` ou PR com conflito: `python -m scripts.juntar_main` (merge da `main`, conflito em pasta gerada
  resolvido rodando os geradores; conflito em código para e pede uma pessoa) e `git push` comum. Rode
  também antes de pedir o merge. Mudou `src/paginas.py`, `src/modulos.py` ou `web/`: rode os geradores
  (`exportar_conteudo`, `gerar_site`, `npm run site`, `npm run app`) e faça o commit junto.
- **A página inicial acompanha a base** (pedido do Tiago, 04/11/2026): tabela ou fonte nova no catálogo pede
  os geradores do site; se é de órgão público e tem CNPJ, entra num tema de `base/vitrine.py::TEMAS_DO_CNPJ`
  (há teste que cobra), com o órgão na frase. Frase nova na página é texto público: passa pelas duas revisões.

## Várias IAs no mesmo projeto

O Tiago trabalha com mais de uma IA (decisão na pasta privada, ADR 0110). Para não haver confusão:

1. **Um livro de regras só.** Este `AGENTS.md` (e o `trader/AGENTS.md`). Os `CLAUDE.md` só importam
   estes arquivos (`@AGENTS.md`) e guardam o que é ferramenta do Claude. Arquivo de regras de uma IA nova
   segue o mesmo molde: importa ou aponta para cá, nunca copia.
2. **Uma IA por tarefa.** Cada tarefa tem uma dona: uma conversa de uma IA, com a própria cópia e o próprio
   ramo. Duas IAs nunca trabalham na mesma cópia, no mesmo ramo ou no mesmo PR ao mesmo tempo. Antes de
   começar, confira `git worktree list` e `gh pr list` (e, no PC do Tiago, a fila da pasta privada).
3. **Trocar de IA no meio da tarefa** (por exemplo, quando o limite de uma acaba): a que sai faz o commit e o
   push de tudo, escreve a passagem (ramo, cópia, PR, o que falta, próximo passo) e para; a que entra lê a
   passagem e continua no **mesmo ramo e na mesma cópia**. Nunca as duas ao mesmo tempo.
4. **Assinatura.** Todo commit termina com `Co-Authored-By: <IA e modelo> <noreply@...>` (ex.:
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, `Co-Authored-By: Codex (GPT-6) <noreply@openai.com>`),
   e o corpo do PR termina com `Feito por: <IA e modelo>`. Assim cada linha da `main` diz quem a escreveu.
5. **Mesmas regras, mesmas travas.** Nenhuma IA tem mais permissão que a outra: mesmas alçadas, mesmo CI,
   mesmo portão, mesmas áreas sensíveis e as mesmas duas revisões antes do merge.
6. **Revisão cruzada.** PR em área sensível ou de nível 1 feito por uma IA é revisado por outro modelo (a
   outra IA ou outro modelo do Claude) antes do merge, e o merge espera não haver P0 nem P1 aberto: modelos
   diferentes erram em lugares diferentes (ver "Quando a tarefa é só auditar").
7. **Ferramenta diferente, mesmo objetivo.** Quando uma regra cita uma ferramenta que você não tem (o
   Auto-fix ou as mensagens entre sessões do Claude, por exemplo), cumpra o objetivo dela pelo caminho que
   você tem, e diga qual usou.

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

## Análises de empresa e de grupo

**Toda análise do TickerLab segue `docs/padrao-de-analise.md`** (pedido do Tiago em 24/10/2026): companhia
aberta, empresa fechada ou grupo. Em resumo: uma frase no topo, o mapa societário completo a partir do quadro
de sócios da Receita, linha do tempo, atividades com o ano de cada fonte, conferência nas bases oficiais
(IBAMA, Lista Suja, sanções, dívida, terra) com a data de cada uma, fato separado de dedução, homônimos
descartados à vista, o que não foi achado, comparação e fontes. Sem CPF, menor de idade, contato ou endereço
residencial. O relatório de companhia aberta continua seguindo a análise completa da ADR 0100.

## `trader/` (pesquisa de trading)

Regras próprias em `trader/AGENTS.md`. Resumo: só leitura (há teste que
impede enviar ordens), conta de demonstração, critério de aprovação escrito antes dos resultados,
toda execução conta como tentativa, um modelo por vez.

## Quando a tarefa é só auditar

Se o pedido é **auditar** ou **revisar** (e não programar), você só lê e aponta: sem commit, sem push, sem PR,
sem editar arquivos fora de uma pasta temporária sua. Quem corrige é o autor, por PR com teste e CI verde.
Se encontrar um segredo, uma senha, um IP de servidor ou um e-mail pessoal versionado, isso é achado grave:
descreva onde está, **sem copiar o valor**.

Para auditar: `python -m pip install -r requirements.txt` e os comandos acima. Os testes não precisam de
internet nem de segredos; se um teste precisar de PostgreSQL e não houver, anote e siga com os demais.

### Mapa de risco (onde procurar primeiro)

| Risco | Onde |
|---|---|
| **Alto** | login e admins (`src/autenticacao.py`, `src/administracao.py`; OAuth do Google, `TICKERLAB_ADMINS`, `TICKERLAB_AMBIENTE`); API (`src/api.py`, `src/api_v1/`); cobrança e webhook do Stripe (`src/cobranca.py`: assinatura verificada, idempotência, eventos fora de ordem); limites dos planos (`src/planos.py` e quem os confere); **consulta ao banco sem filtro por `usuario_id`** (vazamento entre contas); SQL montado com texto; migrações (`migracoes/versions/`); compartilhamento por link (`src/compartilhamentos.py`, `src/api_v1/compartilhados.py`); coletas que baixam URL vinda de dado (SSRF); PDF e e-mail com texto do usuário; `Dockerfile`, `compose.yaml`, `.github/workflows/` |
| **Alto (dados)** | **olhar o futuro**: em `base/`, `src/backtest.py`, indicadores e rótulos, um dado só pode ser usado a partir da data em que ficou público (colunas como `disponivel_em`, `visto_em`) |
| **Médio** | regras de negócio (backtest, Research, Radar), estado gravado no banco, telas que mostram dados da conta, exportação e exclusão da conta (LGPD, `src/conformidade.py`) |
| **Baixo** | textos, CSS, documentação, logs (exceto log com e-mail ou nome: isso é médio) |

### Como relatar um achado

Um achado por bloco, do mais grave ao menos grave:

```
### [P0|P1|P2] Título curto
- Arquivo e linha: `src/x.py:123`
- O que está errado (uma frase)
- Cenário concreto: quem (visitante, conta Gratuita, outra conta, webhook falso, dado de entrada),
  o que faz, passo a passo, e o que acontece de errado
- Como reproduzir: um teste ou comando, se possível
- Confiança: alta | média | baixa
```

- **P0:** perda ou vazamento de dados, acesso indevido, cobrança errada, dado do futuro no passado.
- **P1:** resultado errado para o usuário ou na base, sem vazamento.
- **P2:** robustez (erro não tratado, caso de borda) com efeito real.

Não relate estilo, nomes, formatação, "talvez fosse melhor", nem sugestões de refatoração: o projeto
tem `ruff` e `pyright` no CI para isso. Sem cenário concreto, escreva "suspeita" no título e use
confiança baixa. Prefira poucos achados certos a muitos duvidosos.

## Review guidelines

Para revisão de pull request:

- Revise só o que o PR muda e o que essas linhas afetam; aponte apenas P0 e P1.
- Toda consulta nova ao banco filtra pelo `usuario_id` e tem teste com duas contas.
- Webhook do Stripe: assinatura verificada antes de qualquer efeito; nenhuma chave que não seja de teste.
- Nada de segredo, e-mail ou nome de pessoa em código, log ou teste.
- Em `base/` e no backtest: nenhum dado usado antes da data em que ficou público.
- Migração nova tem caminho de volta (`downgrade`) e não apaga dado sem aviso.
