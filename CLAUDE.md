@AGENTS.md

# Só para o Claude

As regras do repositório estão no `AGENTS.md` (importado acima) e valem para todas as IAs. Aqui fica só o que
depende das ferramentas do Claude Code; **regra nova vai para o `AGENTS.md`**, não para cá.

- **Ao abrir um PR**, ligue o Auto-fix do app (`mcp__ccd_pr__set_monitor` com `auto_fix` e `address_comments`):
  é o jeito do Claude de acompanhar o CI até o merge.
- **Ordens da Diretoria** chegam por mensagem entre sessões (`SendMessage`). Para uma conversa de outra IA, a
  ordem vai escrita na passagem da tarefa.
