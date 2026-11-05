# O TickerLab no terminal: o painel `tl`

O app do Claude Code (barra lateral, botões, Auto-fix) continua valendo. O painel `tl` é o mesmo trabalho pelo
PowerShell, para quem prefere o terminal ou quer ver tudo numa tela só: abre uma conversa já na cópia certa do
repositório, com o nome `Mesa · tarefa` e o prompt de abertura escrito; mostra as conversas abertas (do app e do
terminal), as cópias, os PRs com o CI e a fila única; e aponta as cópias de PR mesclado que podem ser apagadas.

É um módulo do PowerShell em `scripts/terminal/` (comando `tl`), feito só com o que já se usa aqui: `git`, `gh`,
`claude` e o Windows Terminal (`wt`).

## Instalar

Precisa de PowerShell 7 (`pwsh`), Windows Terminal, Git, GitHub CLI (`gh auth login`) e o Claude Code (`claude`).

```powershell
.\scripts\terminal\instalar.ps1 -SoMostrar                                    # só diz o que faria
.\scripts\terminal\instalar.ps1 -PastaPrivada 'C:\caminho\da\pasta-privada'   # instala e aponta a fila
```

O instalador acrescenta uma linha `Import-Module` ao perfil do PowerShell e, com `-PastaPrivada`, grava a variável
de ambiente `TICKERLAB_PASTA_PRIVADA` (a pasta que tem `projeto-acoes/fila.md`). O repositório é público, por isso
nenhum caminho do PC entra nele: a pasta privada chega só por essa variável. Depois, abra um PowerShell novo e
digite `tl`. Para experimentar sem instalar: `Import-Module .\scripts\terminal\TickerLab.psd1`.

## Comandos

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
`Satelites`).

## Do app para o terminal

| No app | No terminal |
|---|---|
| Sessão nova com nome `Mesa · tarefa` e worktree | `tl nova Mesa "tarefa"` (ou, na pasta da cópia, `claude --name "Mesa · tarefa"`) |
| Barra lateral com as sessões | `tl ver` (lê `claude agents --json`, que vê as do app também) |
| Auto-fix do PR (`set_monitor`) | `tl pr <número> -Acompanhar` (`gh pr checks --watch`); CI vermelho, corrija e faça o push de novo |
| `start_session` para abrir outra conversa | não existe daqui: trabalho novo vira linha no fim de `fila.md`, e alguém abre com `tl nova` |
| `wrap_up`, `update_plan` | não existem; a conversa resume em texto |
| Voltar a uma conversa fechada | na pasta da cópia: `claude --resume "Mesa · tarefa"` |
| Pelo celular | `tl celular` (o PC fica ligado) |

O prompt de abertura (`scripts/terminal/Privado/prompt-de-abertura.md`) avisa a conversa de que ela está no
terminal e dá o caminho equivalente de cada regra (AGENTS.md, "Ferramenta diferente, mesmo objetivo").

## Onde ficam os arquivos gerados

O prompt e o script da aba vão para `%LOCALAPPDATA%\TickerLab\terminal\<nome-da-cópia>\` (`prompt.md` e
`abrir.ps1`), fora do repositório, para não aparecerem no `git status`. A aba roda `pwsh -NoExit -File abrir.ps1`:
quando o Claude fecha, o terminal fica aberto na pasta da cópia.

## Limpeza das cópias (ADR 0101)

Acima de 10 cópias, as de PR mesclado devem ser apagadas. `tl limpar -Apagar` só apaga quando: o merge tem mais
de 2 h, nenhuma conversa aberta tem nome parecido com a cópia (mesma mesa e uma palavra da tarefa em comum), não há
PR aberto no mesmo ramo, e o git da cópia não tem mudança não salva, arquivo não versionado, commit não enviado nem
commit depois do merge. O resto fica listado com o motivo. Dentro de uma conversa do Claude, apagar cópias é barrado
pelo modo automático: é um comando da pessoa, pelo `tl`.

## Testes

```powershell
pwsh -NoProfile -File scripts/terminal/testes/rodar.ps1                 # os testes do módulo, sem Pester
.venv\Scripts\python -m pytest -q tests/test_terminal_powershell.py     # o mesmo, pelo pytest (pula sem pwsh)
```

As regras (nomes, leitores da fila, das sessões, das cópias e dos PRs, argumentos do `claude` e do `wt`, o prompt
de abertura, as candidatas à limpeza) são funções puras com teste em `scripts/terminal/testes/rodar.ps1`, com
exemplos em `testes/exemplos/`. As funções que chamam programas (`git`, `gh`, `claude`, `wt`) só buscam texto.

## Decisões

- **Sem pular permissões.** `-Permissao` aceita `default`, `plan`, `acceptEdits` e `auto`; nunca o modo que pula tudo.
- **Pasta privada por variável de ambiente**, nunca no código: o repositório é público.
- **Módulo em `scripts/terminal/`**, não num repositório à parte: mesma regra, mesmo CI, mesma revisão.
- **O nome da conversa é o elo.** O `claude agents --json` dá o nome de cada conversa, mas não a cópia (todas as do
  app apontam para a pasta principal). Por isso `tl limpar` compara o nome da conversa com o nome da cópia.
