# O TickerLab no terminal: o Claude Code com a cara do TickerLab

O Claude Code de terminal (`claude`, o mesmo programa que o app do Claude Code usa por dentro) personalizado para o
projeto: um perfil "TickerLab" do Windows Terminal que abre o PowerShell 7 já dentro do Claude Code, na pasta do
projeto, com as cores da marca, a fonte mono oficial e o símbolo do TickerLab; uma linha de status que mostra a
conversa (`Mesa · tarefa`), o PR com o CI e a fila única; um estilo de saída com as regras do app pelo caminho do
terminal; atalhos de teclado para as skills do dia a dia; e um lançador que abre uma conversa nova numa aba, como o
`start_session` do app.

Nada aqui substitui o `claude`: tudo é configuração do próprio Claude Code e do Windows Terminal, lida pelos caminhos
oficiais (fragment de perfil, `statusLine`, estilo de saída, `keybindings.json`, `--settings`). O app continua
valendo; o terminal é o mesmo trabalho em outra janela. Tudo fica em `scripts/terminal/`.

## Instalar

Precisa de PowerShell 7 (`pwsh`), Windows Terminal, Node.js (para a linha de status), Git, GitHub CLI
(`gh auth login`) e o Claude Code (`claude`).

```powershell
.venv\Scripts\python -m scripts.terminal.perfil_windows_terminal --so-mostrar   # só imprime o que gravaria
.venv\Scripts\python -m scripts.terminal.perfil_windows_terminal                # perfil, estilo e atalhos
.venv\Scripts\python -m scripts.terminal.perfil_windows_terminal --fonte        # idem, mais a JetBrains Mono
```

O comando grava três coisas, nenhuma dentro do repositório:

| O quê | Onde | Como |
|---|---|---|
| perfil "TickerLab" e esquema de cores do Windows Terminal | `%LOCALAPPDATA%\Microsoft\Windows Terminal\Fragments\TickerLab\tickerlab.json` | *fragment*: o jeito oficial de um programa acrescentar perfil e esquema sem mexer no `settings.json` da pessoa |
| estilo de saída "TickerLab" | `~\.claude\output-styles\TickerLab.md` | cópia de `estilo-de-saida-tickerlab.md` (sobrescreve: o arquivo é do projeto) |
| atalhos de teclado | `~\.claude\keybindings.json` | cópia de `keybindings.json`, só se a pessoa ainda não tem os seus (senão avisa para juntar à mão) |

Com `--fonte`, instala também a JetBrains Mono do repositório (`static/fontes/`) só para o usuário, sem administrador
(cópia em `%LOCALAPPDATA%\Microsoft\Windows\Fonts\` e registro em HKCU); sem a fonte, o perfil usa a Cascadia Mono,
que vem com o Windows Terminal. A pasta do Claude Code é `~\.claude` ou a de `CLAUDE_CONFIG_DIR`.

A **linha de status** é a única parte que a pessoa liga à mão, porque `~\.claude\settings.json` é dela (tem hooks,
permissões e modelo): o comando imprime a chave a acrescentar,
`"statusLine": {"type": "command", "command": "node <repositório>/scripts/terminal/statusline.js", "padding": 0}`.
Ela vale para o app e para o terminal. A fila só aparece com a variável de ambiente `TICKERLAB_PASTA_PRIVADA` (a
pasta que tem `projeto-acoes/fila.md`): o repositório é público, e nenhum caminho do PC entra nele.

Desfazer: `--desfazer` (e `--desfazer --fonte`) apaga o fragment, o estilo e os atalhos (estes só se ainda forem os
nossos); a chave `statusLine` sai do `settings.json` à mão.

## Como fica

- **Perfil "TickerLab"** no menu de abas do Windows Terminal: abre o `pwsh` na raiz do repositório já dentro do
  `claude`, com fundo marinho e as cores de `src/marca.py` (verde é alta, vermelho é queda, amarelo é atenção), a
  fonte mono da marca, o símbolo do TickerLab como ícone da aba e marca-d'água no canto. Quando o `claude` fecha, o
  terminal fica aberto na pasta.
- **Linha de status** (embaixo da caixa de digitação), em duas linhas:
  `Mesa · tarefa · modelo e esforço · pasta da cópia · ⎇ ramo (* = mudança sem commit) · PR #n ✓/✗/… · agente` e
  `contexto ▓▓▓▓░░░░░░ 42% · 5h 30% ↻hora · semana 70% ↻dia hora · cache 90% · ≈US$ custo · fila 13/15`. O nome
  vem de `claude --name` ou `/rename` (no app, do título da conversa); sem nome, da pasta da cópia
  (`analise-acoes-dados-sidra-392` vira `Dados · sidra 392`). O CI do PR vem do `gh` por um cache de 60 s que um
  processo filho atualiza: a linha nunca espera a rede. A fila fica amarela com 2 vagas e vermelha quando cheia.
- **Estilo de saída "TickerLab"** (`estilo-de-saida-tickerlab.md`, com as instruções de código do Claude mantidas):
  a conversa sabe que está no terminal, sem `start_session`, `wrap_up`, `set_monitor` nem botões, e segue as mesmas
  regras pelo caminho equivalente (regra 7 do `AGENTS.md`): bloco "📍 Onde estamos" no fim de cada resposta, plano em
  texto, conversa nova é linha na fila, PR acompanhado com `gh pr checks --watch`. Os verbos do giro ("Conferindo…",
  "Separando fato de dedução…") vêm de `claude-terminal.json`.
- **Atalhos** (`keybindings.json`, acorde `ctrl+k` e uma letra): `f` fecha a tarefa (`/fechar-tarefa`), `p` publica
  (`/publicar`), `o` relato do dia (`/o-que-aconteceu`), `a` arruma a fila (`/arrumar-fila`), `n` conversa nova
  (`/abrir-conversa`).
- **Permissões:** o mesmo modo automático do app (`--permission-mode auto`, com as regras `autoMode` do
  `settings.json` da pessoa). O modo que pula as permissões não existe aqui.

## Abrir uma conversa

`scripts/terminal/claude-tickerlab.ps1` é a única fonte da linha de comando do `claude` no terminal (o perfil do
Windows Terminal roda ele):

```powershell
.\scripts\terminal\claude-tickerlab.ps1                               # nesta pasta, como o perfil faz
.\scripts\terminal\claude-tickerlab.ps1 -Nome 'Dados · coleta nova'   # com o nome da conversa
.\scripts\terminal\claude-tickerlab.ps1 -NovaAba -Pasta ..\analise-acoes-dados-coleta -Nome 'Dados · coleta nova' -Prompt ..\passagem.md
.\scripts\terminal\claude-tickerlab.ps1 -SoMostrar                    # só imprime o comando
.\scripts\terminal\claude-tickerlab.ps1 --resume                      # o resto vai direto ao claude
```

`-NovaAba` é o `start_session` de quem está no terminal: abre outra aba da janela `tickerlab` do Windows Terminal, no
perfil TickerLab, na cópia pedida, com o título `Mesa · tarefa` fixo e, se houver, a passagem como primeira mensagem.
A cópia se cria antes, como sempre: `git worktree add ../analise-acoes-<mesa>-<tarefa> -b <tipo>/<tarefa> origin/main`
(ou `tl nova`, abaixo, que faz as duas coisas). Voltar a uma conversa: na pasta da cópia,
`claude --resume "Mesa · tarefa"`.

## Do app para o terminal

| No app | No terminal |
|---|---|
| Sessão nova com nome `Mesa · tarefa` e worktree | `claude-tickerlab.ps1 -NovaAba -Pasta <cópia> -Nome "Mesa · tarefa"` (ou `tl nova Mesa "tarefa"`, que também cria a cópia) |
| Barra lateral com as sessões | `tl ver` (lê `claude agents --json`, que vê as do app também) |
| Auto-fix do PR (`set_monitor`) | `gh pr checks <número> --watch` em segundo plano (ou `tl pr <número> -Acompanhar`); CI vermelho, corrija e faça o push de novo |
| `start_session` para abrir outra conversa | trabalho novo vira linha no fim de `fila.md`; quem tem vaga abre com `-NovaAba` ou `tl nova` |
| `wrap_up`, `update_plan` | não existem; a conversa resume em texto e termina com o bloco "📍 Onde estamos" |
| Linha de status do app | a mesma (`statusline.js` vale para os dois) |
| Voltar a uma conversa fechada | na pasta da cópia: `claude --resume "Mesa · tarefa"` |
| Pelo celular | `tl celular` (Remote Control; o PC fica ligado) |

## Arquivos

| Em `scripts/terminal/` | O que é |
|---|---|
| `claude-tickerlab.ps1` | lançador: a linha de comando do `claude` (modo `auto`, `--settings claude-terminal.json`, `--name`) e a aba nova |
| `claude-terminal.json` | settings só do terminal (`--settings`): estilo de saída "TickerLab" e os verbos do giro |
| `statusline.js` | a linha de status (Node; vale para o app e para o terminal) |
| `estilo-de-saida-tickerlab.md` | o estilo de saída, instalado em `~\.claude\output-styles\TickerLab.md` |
| `keybindings.json` | os atalhos, instalados em `~\.claude\keybindings.json` |
| `perfil_windows_terminal.py` | gera e instala o fragment do Windows Terminal, o estilo e os atalhos (`--fonte`, `--desfazer`, `--so-mostrar`) |
| `TickerLab.psd1`, `Publico/`, `Privado/`, `instalar.ps1`, `ponte-*.ps1`, `testes/` | o painel `tl` (abaixo) |

## Testes

```powershell
.venv\Scripts\python -m pytest -q tests/test_terminal_perfil_windows_terminal.py   # cores, fragment, instalar e desfazer
.venv\Scripts\python -m pytest -q tests/test_terminal_linha_de_status.py           # a linha de status, pelo Node (pula sem node)
.venv\Scripts\python -m pytest -q tests/test_terminal_lancador.py                  # o lançador, com -SoMostrar (pula sem pwsh)
.venv\Scripts\python -m pytest -q tests/test_terminal_powershell.py                # os testes do painel tl (pula sem pwsh)
```

A instalação nos testes usa `LOCALAPPDATA` e `CLAUDE_CONFIG_DIR` apontando para pastas temporárias e nunca mexe na
fonte; a linha de status é testada função a função (CI, PR, nome, fila) e de ponta a ponta com um JSON de amostra,
numa pasta sem Git (sem ramo, sem PR, sem processo filho).

## Decisões

- **Personalizar o `claude` de verdade, não embrulhá-lo** (pedido do Tiago, 05/11/2026: "o Claude Code do
  PowerShell, só que personalizado para o TickerLab"). Tudo é configuração que o Claude Code e o Windows Terminal já
  leem; nenhum programa no meio.
- **Fragment, não `settings.json`.** O perfil entra pela pasta de fragments do Windows Terminal; o `settings.json` da
  pessoa (e o do Claude Code) ficam intactos. Por isso a linha de status é a única coisa ligada à mão.
- **Nenhum caminho do PC no repositório.** O fragment gerado aponta para a cópia em que o comando rodou; a fila chega
  por `TICKERLAB_PASTA_PRIVADA`.
- **Sem pular permissões.** O terminal abre no mesmo `auto` do app.
- **A linha de status nunca espera.** O `gh` demora cerca de 1 s; um processo filho grava o PR num cache em disco
  (60 s) e a linha lê o cache.
- **Um lugar só para a linha de comando do `claude`:** `claude-tickerlab.ps1`, usado pelo perfil, pela aba nova e
  pelos testes.
- **Os atalhos são da pessoa.** O instalador só copia `keybindings.json` quando ela ainda não tem o seu.

## O painel `tl` (opcional)

O painel `tl` é um módulo do PowerShell em `scripts/terminal/` para quem quer ver tudo numa tela só: abre uma conversa
já na cópia certa do repositório, com o nome `Mesa · tarefa` e o prompt de abertura escrito; mostra as conversas
abertas (do app e do terminal), as cópias, os PRs com o CI e a fila única; e aponta as cópias de PR mesclado que podem
ser apagadas. Feito só com o que já se usa aqui: `git`, `gh`, `claude` e o Windows Terminal (`wt`). Não é preciso
para o perfil acima; é um complemento.

### Instalar o `tl`

```powershell
.\scripts\terminal\instalar.ps1 -SoMostrar                                    # só diz o que faria
.\scripts\terminal\instalar.ps1 -PastaPrivada 'C:\caminho\da\pasta-privada'   # instala e aponta a fila
```

O instalador acrescenta uma linha `Import-Module` ao perfil do PowerShell 7 (o do usuário, para todas as janelas),
importa o módulo já na janela em que rodou e, com `-PastaPrivada`, grava a variável de ambiente
`TICKERLAB_PASTA_PRIVADA` (a pasta que tem `projeto-acoes/fila.md`; a linha de status usa a mesma). No Windows, ele
também deixa o `tl` no Windows PowerShell 5.1 (`powershell.exe`, o azul que o Windows abre por padrão e que no menu
Iniciar se chama "Windows PowerShell"; o 7 é só "PowerShell"): o perfil do 5.1 passa a carregar
`scripts/terminal/ponte-windows-powershell.ps1`, um `tl` que roda cada comando num `pwsh` sem perfil, com os mesmos
argumentos, porque o módulo exige o PowerShell 7. As janelas que já estavam abertas (dos dois PowerShells e o painel
Terminal do app do Claude Code também) carregaram o perfil antes da linha e respondem "tl não é reconhecido": abra uma
janela nova ou rode nelas `. $PROFILE.CurrentUserAllHosts`. Para experimentar sem instalar:
`Import-Module .\scripts\terminal\TickerLab.psd1`.

### Comandos

| Comando | O que faz |
|---|---|
| `tl` ou `tl ver` | painel: conversas abertas (● trabalhando, ? com pergunta para você, ○ parada), cópias, PRs com CI, fila |
| `tl nova <Mesa> "<tarefa>"` | cria a cópia `../analise-acoes-<mesa>-<tarefa>` e o ramo `feat/<tarefa>` a partir de `origin/main`, grava o prompt de abertura e abre a conversa numa aba da janela `tickerlab`, com o título `Mesa · tarefa` e a cor da mesa |
| `tl nova ... -Modelo opus` | `sonnet` (padrão), `opus` ou `fable` |
| `tl nova ... -Ramo fix` | tipo do ramo: `feat`, `fix`, `docs`, `test`, `perf`, `ci`, `chore` |
| `tl nova ... -Passagem arquivo.md` | a passagem que a conversa deve executar (caminho completo ou relativo à pasta privada) |
| `tl nova ... -Permissao plan` | modo de permissão do Claude: `default`, `plan`, `acceptEdits`, `auto`; o modo que pula as permissões não existe aqui |
| `tl nova ... -SemCopia` | abre na pasta principal, sem cópia nem ramo (para conversas que só leem) |
| `tl nova ... -SoMostrar` | mostra o plano (cópia, ramo, comando, aba) sem criar nem abrir nada |
| `tl fila [-Quantas 8] [-Tudo]` | quem trabalha agora e as próximas da fila única |
| `tl pr` | PRs abertos com o CI (✓ passou, ✗ falhou, … rodando) |
| `tl pr <número> [-Acompanhar]` | um PR e as suas verificações; `-Acompanhar` segue o CI até acabar (`gh pr checks --watch`) |
| `tl limpar` | cópias de PR já mesclado: "segura" ou "espere: motivo" |
| `tl limpar -Apagar [-SoMostrar]` | apaga as seguras (`git worktree remove` e `git branch -D`); o PR e a `main` ficam |
| `tl celular` | Remote Control: comanda este PC pelo app do celular ou pelo claude.ai/code |
| `tl ajuda` | a lista de comandos e as mesas |

Mesas: Diretoria, Dados, Plataforma, Produto, Marketing, Financeiro e Satélites, em qualquer grafia (`dados`,
`Satelites`). O prompt de abertura (`scripts/terminal/Privado/prompt-de-abertura.md`) avisa a conversa de que ela
está no terminal e dá o caminho equivalente de cada regra.

### Onde ficam os arquivos gerados pelo `tl`

O prompt e o script da aba vão para `%LOCALAPPDATA%\TickerLab\terminal\<nome-da-cópia>\` (`prompt.md` e
`abrir.ps1`), fora do repositório, para não aparecerem no `git status`. A aba roda `pwsh -NoExit -File abrir.ps1`:
quando o Claude fecha, o terminal fica aberto na pasta da cópia.

### Limpeza das cópias (ADR 0101)

Acima de 10 cópias, as de PR mesclado devem ser apagadas. `tl limpar -Apagar` só apaga quando: o merge tem mais
de 2 h, nenhuma conversa aberta tem nome parecido com a cópia (mesma mesa e uma palavra da tarefa em comum), não há
PR aberto no mesmo ramo, e o git da cópia não tem mudança não salva, arquivo não versionado, commit não enviado nem
commit depois do merge. O resto fica listado com o motivo. Dentro de uma conversa do Claude, apagar cópias é barrado
pelo modo automático: é um comando da pessoa, pelo `tl`.

### Testes e decisões do `tl`

`pwsh -NoProfile -File scripts/terminal/testes/rodar.ps1` roda os testes do módulo sem Pester (o pytest acima só os
chama). As regras (nomes, leitores da fila, das sessões, das cópias e dos PRs, argumentos do `claude` e do `wt`, o
prompt de abertura, as candidatas à limpeza) são funções puras com teste, com exemplos em `testes/exemplos/`. As
funções que chamam programas (`git`, `gh`, `claude`, `wt`) só buscam texto. O instalador e a ponte do Windows
PowerShell são testados num `pwsh` filho, com perfis temporários (e, num PC com Windows, também a partir do
`powershell.exe` de verdade).

- **O nome da conversa é o elo.** O `claude agents --json` dá o nome de cada conversa, mas não a cópia (todas as do
  app apontam para a pasta principal). Por isso `tl limpar` compara o nome da conversa com o nome da cópia.
- **Ponte para o Windows PowerShell 5.1, não uma segunda versão.** O módulo é do PowerShell 7; o 5.1, que o Windows
  ainda abre por padrão, ganha só uma função `tl` que repassa cada comando ao `pwsh` (`ponte-windows-powershell.ps1` e
  `ponte-pwsh.ps1`). Um código só, e o painel funciona em qualquer janela.
