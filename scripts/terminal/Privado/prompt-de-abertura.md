Mesa {{MESA}}: {{TAREFA}}.

Esta conversa roda no terminal (PowerShell), não no app do Claude: não existem `start_session`, `wrap_up`,
`update_plan`, `set_monitor` nem a barra lateral. Cumpra o objetivo de cada regra pelo caminho que você tem
(AGENTS.md, "Ferramenta diferente, mesmo objetivo"): o PR que você abrir se acompanha com
`gh pr checks <número> --watch` até o merge (CI vermelho: corrija e faça o push de novo); conversa nova não
se abre daqui: trabalho novo vira linha no fim de `projeto-acoes/fila.md`.

Sua cópia do repositório é `{{COPIA}}`{{RAMO}}. Trabalhe só nela; não toque na cópia, no ramo ou no PR de
outra conversa.

{{PASSAGEM}}

Primeiro: leia o `CLAUDE.md`; ponha esta conversa na linha da mesa no quadro de sessões (`sessoes.md`), crie
a nota dela em `projeto-acoes/conversas/` (copie as propriedades de uma nota vizinha) e, em `fila.md`, mova a
sua linha para "Trabalhando agora". Respeite o que pede o "pode" do Tiago (nível 1 da ADR 0101). Ao terminar,
`/fechar-tarefa`, pulando os passos que só existem no app, e tire a sua linha de "Trabalhando agora".
