# Trabalhar pelo Orca

## Em uma frase

O Orca é um orquestrador que abre cada tarefa numa cópia própria do repositório (worktree), com um agente
(Claude, Codex ou Gemini) trabalhando nela; as regras são as mesmas do `AGENTS.md`.

## Abrir uma tarefa

```powershell
orca worktree create --repo "name:<projeto>" --name "Mesa · tarefa" --branch feat/tarefa-tal --agent claude --model <modelo> --prompt "o que fazer"
```

O ramo vai sempre com `--branch`, no formato do repositório (`feat/`, `fix/`, `docs/`, `test/`): o nome que o
Orca sugere sozinho leva um prefixo dele.

## O que o app do Claude faz e o caminho pelo Orca

Regra 7 do `AGENTS.md`: ferramenta diferente, mesmo objetivo.

| No app do Claude | Pelo Orca |
|---|---|
| Acompanhar o CI do PR até o merge (Auto-fix) | `gh pr checks <número> --watch` |
| Ordem ou aviso a outra conversa | `orca orchestration send`, `check` e `reply`, ou a passagem escrita |
| Aviso do início da sessão | o comando de situação que fica na pasta privada |
| Lista de passos e caixa de próximo passo | não há: o bloco "Onde estamos" no fim da resposta basta |

## O que não muda

- Nunca trabalhar na pasta principal do repositório.
- Uma IA por cópia, por ramo e por PR.
- Tarefa fechada = cópia e ramo apagados.
- Assinatura no commit (`Co-Authored-By`) e no corpo do PR (`Feito por`).
- Mesmas alçadas e mesmas duas revisões antes do merge nas áreas sensíveis.

## O que foi testado (24/11/2026)

Primeira tarefa inteira feita por uma conversa aberta pelo Orca (esta, que escreveu este documento).

- **Funcionou:** a conversa abriu na cópia certa, no ramo `docs/trabalhar-pelo-orca`; `git`, `gh` e os testes
  rodaram pela cópia; `orca orchestration check --all` respondeu ("No messages.").
- **Não testado:** `orca orchestration reply` (não havia mensagem para responder) e `orca orchestration send`.
