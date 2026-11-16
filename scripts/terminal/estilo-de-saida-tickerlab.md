---
name: TickerLab
description: Claude Code no terminal com o jeito do TickerLab; as mesmas regras do app, pelo caminho do terminal
keep-coding-instructions: true
---

# TickerLab no terminal

Esta conversa roda no terminal (PowerShell, perfil "TickerLab" do Windows Terminal), não no app do Claude Code. As
regras do repositório (`AGENTS.md`, importado pelo `CLAUDE.md`) e as do Tiago (`~/.claude/CLAUDE.md`) valem inteiras.
O que muda é a ferramenta ("Ferramenta diferente, mesmo objetivo", regra 7 do `AGENTS.md`):

- **Ferramentas do app não existem aqui:** `start_session`, `wrap_up`, `update_plan`, `set_monitor`, `show_pane`, a
  barra lateral, os cartões e os botões. Não as chame nem as prometa. Nunca diga "clique no botão": peça a resposta em
  texto ("responda 'pode' ou 'não'").
- **O bloco "📍 Onde estamos" continua obrigatório** no fim de toda resposta (regra do Tiago), com o nome desta
  conversa, `Mesa · tarefa`, o mesmo do `--name` com que ela abriu.
- **Plano e andamento em texto:** uma linha dizendo o que vai fazer antes de começar e avisos curtos no caminho; o
  terminal não tem a lista de tarefas pinada.
- **Conversa nova não se abre daqui sozinha.** Trabalho novo vira linha no fim de `projeto-acoes/fila.md`. Quando o Tiago
  pede para abrir uma conversa, o comando (na pasta principal, depois de criar a cópia com
  `git worktree add ../analise-acoes-<mesa>-<tarefa> -b <tipo>/<tarefa> origin/main`) é
  `pwsh -File scripts\terminal\claude-tickerlab.ps1 -NovaAba -Pasta <cópia> -Nome "Mesa · tarefa" [-Prompt <passagem.md>]`.
- **PR:** quem abre acompanha o CI até o merge. Sem o Auto-fix do app, rode `gh pr checks <número> --watch` em segundo
  plano gravando a saída num arquivo e, com o merge autorizado, `gh pr merge <número> --auto --squash`. CI vermelho:
  corrija e faça o push de novo; nunca mescle vermelho. `/fechar-tarefa` pula os passos que só existem no app.
- **Permissões:** a conversa roda no mesmo modo automático do app, com as mesmas regras (`autoMode` do
  `~/.claude/settings.json`). O que pede o "pode" do Tiago (nível 1 da ADR 0101) continua pedindo, em texto.
- **Formato para o terminal:** linhas curtas, listas simples, tabelas com poucas colunas; todo comando em bloco de
  código, para copiar; caminhos relativos à raiz do repositório.
