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
- [ ] Mudou o banco? Migração nova (com `downgrade`) e consultas filtradas pelo usuário.
- [ ] O trecho tocado ficou mais claro do que estava.
- [ ] Pronto para trocar de interface: nenhum cálculo, regra ou texto novo em `telas/`; estado que importa no banco.
- [ ] Casa em ordem: script novo com a linha `Roda:`; nada novo na raiz nem nos `requirements*.txt` sem a lista ou a exceção do teste.

Feito por: <!-- IA e modelo, ou "Tiago" (AGENTS.md, "Várias IAs no mesmo projeto", regra 4) -->
