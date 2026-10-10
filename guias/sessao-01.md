# Sessão 1: ambiente, Git e o primeiro DataFrame

**Meta de hoje:** baixar o histórico de uma ação, entender o que é um `DataFrame`
e calcular o primeiro retorno. Ao final, fazer seu primeiro commit.

Tempo estimado: 1h30 a 2h. Faça no seu ritmo.

## Parte 1: conferir o ambiente (10 min)

1. Abra o VS Code na pasta `C:\Users\tiago\projetos\analise-acoes`
   (Arquivo > Abrir Pasta).
2. Abra o terminal (`Ctrl+'`). Deve aparecer `(.venv)` no começo da linha.
   Se não aparecer, me avise.
3. Rode `python --version`. Deve mostrar Python 3.12.10.

## Parte 2: Pandas (60 min)

Abra o notebook `estudos/sessao01.ipynb`. Ele mistura explicações e código em células.
Rode cada célula com `Shift+Enter` (ou o botão de play).
O resultado aparece logo abaixo da célula. Na primeira vez, escolha o kernel `.venv` (Python 3.12.10).

Regra do jogo: **leia o bloco, tente, e só peça ajuda depois de tentar.**
Quando travar, peça nesta ordem: uma dica, uma dica maior, a resposta comentada.

Conceitos desta sessão:

- `Series` (uma coluna) e `DataFrame` (uma tabela).
- Índice de datas.
- `head()`, `tail()`, `info()`, `describe()`.
- Selecionar colunas e filtrar linhas.
- `pct_change()` para calcular retornos.

## Parte 3: Git (20 min)

Eu te guio ao vivo. Resumo do que você vai fazer:

1. `git init`
2. `git status` (ver o que mudou)
3. `git add .`
4. `git commit -m "Primeira sessão: ambiente e primeiro DataFrame"`

O envio ao GitHub (`push`) fica para quando você criar o repositório lá.

## Para anotar no fim

Escreva 3 linhas sobre o que você aprendeu e o que ficou confuso.
Isso vira material para o relatório e me ajuda a ajustar a próxima sessão.
