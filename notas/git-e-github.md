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

## Os quatro comandos do dia a dia (a preencher na sessão 1)
- `git init`, `git status`, `git add`, `git commit`: ver a Parte 3 do guia da sessão 1.

## Regras que adotamos
- Um commit = uma ideia, mensagem `tipo: o que mudou` (`feat`, `fix`, `docs`, `refactor`, `test`).
- Antes de commitar: `git status` e `git diff`.
- A `main` sempre funciona.
- Nunca commitar `.venv/`, `.env`, chaves ou dados baixados.
- Não dar `push` sem conferir o que vai subir.
