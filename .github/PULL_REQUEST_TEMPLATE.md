## O que muda

<!-- Em uma ou duas frases: o que este PR faz e por quê. -->

## O que não muda

<!-- O que continua igual (comportamento, telas, banco). Num PR só de refatoração, diga que o
resultado não muda e qual teste prova isso. -->

## Como foi testado

<!-- Testes rodados, conferências manuais, números antes e depois. -->

## Checklist ([padrões de código](https://github.com/tbc174/tickerlab/blob/main/docs/padroes-de-codigo.md), seção 9)

- [ ] Funções novas curtas, com nome claro, tipo e docstring.
- [ ] Nenhum número mágico novo; nenhum segredo, e-mail ou IP no código.
- [ ] Testes do que mudou passando; `ruff check` e `ruff format --check` limpos.
- [ ] Mudou o banco? Migração nova e consultas filtradas pelo usuário.
- [ ] O trecho tocado ficou mais claro do que estava.
