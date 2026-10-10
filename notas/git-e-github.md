# Git, GitHub e `gh`

## Conceitos
- **Git:** guarda o histórico do projeto. Cada **commit** é uma "foto" do código naquele momento.
- **GitHub:** site onde o histórico fica guardado na internet (backup e vitrine para o professor).
- **`gh`:** programa de linha de comando para falar com o GitHub (criar repositórios, tarefas e quadros).
- **Repositório:** a pasta do projeto com o histórico.

## Configuração inicial (feita uma vez por computador)
```
git config --global user.name "Tiago"
git config --global user.email "seu-email"
git config --global init.defaultBranch main
```
- Nome e e-mail aparecem em todos os commits. Como o repositório é público, **o e-mail fica visível**.
- `main` é o nome do branch (linha do tempo) principal.
- **Data:** 09/10/2026

## Login do VS Code no GitHub
Ícone de Contas (canto inferior esquerdo), Entrar com o GitHub, autorizar no navegador.
- **Data:** 09/10/2026

## Login do `gh`
```
gh auth login -s project
```
- `-s project` pede permissão extra para usar o quadro de tarefas (Projects).
- O login do `gh` é **separado** do login do VS Code.
- Conferir: `gh auth status`.
- **Data:** 09/10/2026

## Os comandos do dia a dia
Fluxo: **mexo nos arquivos, `git status` (o que mudou?), `git add` (separo o que vai entrar), `git commit` (gravo a foto), `git log` (confiro).**

### `git init`
- **O que é:** transforma a pasta num repositório (cria a pasta oculta `.git`, onde mora o histórico).
- **Para que serve:** começar a guardar o histórico do projeto. Roda uma vez só.
- **Exemplo:** `git init`
- **Cuidados:** no começo o branch `main` não tem nenhum commit; o `git log` avisa "does not have any commits yet".
- **Data:** 09/10/2026

### `git status`
- **O que é:** mostra o estado da pasta: o que está preparado, o que mudou e o que ainda não é acompanhado.
- **Para que serve:** olhar antes de qualquer `add` ou `commit`. É seguro rodar sempre.
- **Como ler:** `A` = preparado para o commit; `M` = modificado; `AM` = preparado, mas **mudou de novo depois do `add`** (precisa de outro `git add`). Sem saída no `--short` = nada pendente.
- **Data:** 10/10/2026

### `git add`
- **O que é:** prepara alterações para entrarem no próximo commit (a "área de preparação").
- **Para que serve:** escolher o que entra na foto. `git add .` prepara tudo da pasta atual.
- **Exemplo:** `git add .` ou `git add notas/git-e-github.md` (só um arquivo)
- **Cuidados:** o `add` tira uma foto do arquivo **naquele instante**. Se editar depois, rode `add` de novo. Confira o `.gitignore` antes, para não preparar a `.venv` nem segredos.
- **Data:** 09/10/2026

### `git commit`
- **O que é:** grava no histórico tudo o que está preparado, com uma mensagem.
- **Para que serve:** criar um ponto do projeto ao qual dá para voltar.
- **Exemplo:** `git commit -m "chore: primeiro commit do projeto"`
- **Cuidados:**
  - Sem o `-m`, o Git abre um editor (`COMMIT_EDITMSG`) e o commit só acontece quando a mensagem é **salva e a aba fechada**. Foi isso que deixou o primeiro commit pendente.
  - Mensagem no padrão `tipo: o que mudou` (ver regras abaixo). O meu primeiro commit saiu como "Primeiro Commit do Projeto!!!".
  - `git commit --amend -m "..."` reescreve o **último** commit; só usar **antes** do `push`.
- **Data:** 10/10/2026 (primeiro commit, `8404143`)

### `git log --oneline`
- **O que é:** lista os commits, um por linha (código curto + mensagem).
- **Para que serve:** conferir que o commit existe. Se mostrar "does not have any commits yet", nada foi gravado.
- **Data:** 10/10/2026

*(Tiago: reescreva com suas palavras o que ficou estranho e acrescente o que você entendeu do fluxo.)*

## Regras que adotamos
- Um commit = uma ideia, mensagem `tipo: o que mudou` (`feat`, `fix`, `docs`, `refactor`, `test`).
- Antes de commitar: `git status` e `git diff`.
- A `main` sempre funciona.
- Nunca commitar `.venv/`, `.env`, chaves ou dados baixados.
- Não dar `push` sem conferir o que vai subir.
