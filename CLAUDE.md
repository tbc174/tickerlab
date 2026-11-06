@AGENTS.md

# Só para o Claude

As regras do repositório estão no `AGENTS.md` (importado acima) e valem para todas as IAs. Aqui fica só o que
depende das ferramentas do Claude Code; **regra nova vai para o `AGENTS.md`**, não para cá.

- **Ao abrir um PR**, ligue o Auto-fix do app (`mcp__ccd_pr__set_monitor` com `auto_fix` e `address_comments`):
  é o jeito do Claude de acompanhar o CI até o merge.
- **Ordens da Diretoria** chegam por mensagem entre sessões (`SendMessage`). Para uma conversa de outra IA, a
  ordem vai escrita na passagem da tarefa.
- **Pelo terminal (PowerShell):** o Claude Code de terminal com a cara do TickerLab fica em `scripts/terminal/`
  (`docs/terminal.md`): perfil "TickerLab" do Windows Terminal, linha de status com mesa, PR e fila, estilo de saída,
  atalhos e o lançador `claude-tickerlab.ps1` (instala com `python -m scripts.terminal.perfil_windows_terminal`); o
  painel `tl`, na mesma pasta, abre e acompanha as conversas de fora. Numa conversa aberta assim não existem as
  ferramentas do app (`start_session`, `wrap_up`, `set_monitor`...): cumpra o objetivo pelo caminho equivalente
  (regra 7 do `AGENTS.md`), como `gh pr checks <número> --watch` no lugar do Auto-fix.
