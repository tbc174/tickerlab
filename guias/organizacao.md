# Guia de organização do projeto

Este guia cresce junto com o projeto. Em cada sessão aprendemos uma prática e
anotamos aqui. A regra de ouro: **cada coisa tem um lugar, e o nome diz o que ela é.**

## 1. Estrutura final de pastas (meta)

```
analise-acoes/
├── README.md              o que é, como instalar, como rodar, prints
├── requirements.txt       bibliotecas (versões fixas)
├── .gitignore             o que o Git ignora
├── app.py                 só a interface (Streamlit); chama o resto
├── src/                   a lógica do projeto, sem interface
│   ├── dados.py           baixar e limpar dados (yfinance)
│   ├── indicadores.py     retornos, médias móveis, volatilidade, drawdown
│   ├── backtest.py        estratégias e métricas
│   └── validacao.py       checar o ticker digitado
├── tests/                 testes que provam que as funções funcionam
├── conteudo/              textos do app (glossario.md...), separados do código
├── estudos/               seus exercícios de aprendizado (sessao01.py...)
└── guias/                 guias das sessões e este arquivo
```

Ideia central: **separar o que o app mostra (`app.py`) do que ele calcula
(`src/`)**. Assim cada arquivo faz uma coisa só e dá para testar e reutilizar.

Hoje o projeto está no começo: os exercícios estão soltos na raiz. Vamos
organizando por etapa (na sessão 2 criamos `src/`; na 3, o `app.py`; os
exercícios vão para `estudos/`).

## 2. Nomes

- Arquivos e pastas: minúsculas, sem acento, sem espaço, com `_` (`indicadores.py`).
- Funções e variáveis: minúsculas com `_` e nome que diz o que é
  (`calcular_retorno_diario`, não `f1`; `fechamento`, não `x`).
- Constantes: MAIÚSCULAS (`DIAS_POR_ANO = 252`).
- Português ou inglês? **Português**, em tudo, sem misturar.

## 3. Código

- Uma função faz uma coisa. Se precisar de "e" para descrevê-la, divida.
- Cada função tem uma docstring de uma linha dizendo o que faz.
- Nada de números mágicos soltos: dê nome (`CUSTO_POR_OPERACAO = 0.001`).
- O Ruff formata ao salvar. Não discuta estilo, deixe a ferramenta cuidar.

## 4. Git

- **Um commit = uma ideia.** Pequenos e frequentes.
- Mensagem no formato `tipo: o que mudou`, no presente:
  - `feat: calcula retorno diário`
  - `fix: corrige ticker sem .SA`
  - `docs: atualiza README`
  - `refactor: move funções para src/indicadores.py`
  - `test: testa o cálculo de drawdown`
- Antes de commitar: `git status` e `git diff` (olhe o que vai).
- A partir da semana 3: uma **branch por funcionalidade** (`feat/grafico-preco`),
  que volta para a `main` quando estiver funcionando.
- A `main` sempre funciona.
- Nunca commitar: `.venv/`, `.env`, chaves, dados baixados.

## 5. Documentação

- O `README` responde: o que é, como instalar, como rodar, exemplo de uso.
- Comentário explica o **porquê**, não o óbvio.
- Todo fim de sessão: 3 linhas no diário de aprendizado.

## 6. Checklist de fim de sessão

- [ ] O código roda do começo ao fim?
- [ ] Os nomes estão claros?
- [ ] Rodei `ruff check .`?
- [ ] `git status` mostra só o que eu quero?
- [ ] Commit feito com mensagem no formato certo?
- [ ] Diário atualizado?

## Prática por sessão

| Sessão | O que aprendemos de organização |
|---|---|
| 1 | Nomes, estrutura inicial, `.gitignore`, primeiro commit |
| 2 | Criar `src/`, separar funções em módulos, docstrings |
| 3 | `app.py` separado da lógica, primeiro branch |
| 4 | Testes em `tests/`, constantes nomeadas |
| 5 | README completo, `requirements.txt`, revisão final |
