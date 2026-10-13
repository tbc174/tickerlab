# Padrões de código do TickerLab

Como escrevemos código aqui, e por quê. Vale para quem programa à mão e para o Claude. O objetivo
é um só: **qualquer pessoa (inclusive o Tiago daqui a seis meses) entender o código lendo uma vez.**
Regras que uma ferramenta confere estão marcadas com 🤖 (ruff ou testes, no CI).

## 1. Funções

- **Uma função faz uma coisa.** Se para descrevê-la você precisa de "e" ("calcula o retorno *e*
  desenha o gráfico"), são duas funções.
- **Curtas:** mire em até ~40 linhas; acima de ~60, divida em partes com nome. Telas longas viram
  uma sequência de chamadas que se lê como um índice:

  ```python
  def secao_backtest(dados):
      parametros = escolher_parametros()
      resultado = rodar_backtest(dados, parametros)
      mostrar_resumo(resultado)
      mostrar_graficos(resultado)
  ```
- 🤖 **Complexidade máxima 15** (C901): muitos `if`/`for` aninhados escondem erros. Saída antecipada
  (`if not dados: return`) ajuda a não aninhar.
- **Poucos parâmetros:** mais de ~5 é sinal de que falta agrupar (um `@dataclass` de configuração).
- Sem efeitos escondidos: uma função que calcula não grava arquivo nem muda variável global.

## 2. Nomes

- **Português**, descritivo e sem abreviação obscura: `retorno_anualizado`, não `ret_a`.
  Termos consagrados ficam em inglês (`sharpe`, `drawdown`, `backtest`).
- Funções com verbo (`calcular_drawdown`, `mostrar_tabela`); valores com substantivo
  (`maior_queda`); booleanos que leem como pergunta (`tem_dados`, `esta_logado`).
- Constantes em MAIÚSCULAS no topo do módulo: `DIAS_POR_ANO = 252`.

## 3. Números e textos soltos

- **Nada de número mágico.** `if vol > 0.4` não diz nada; `if vol > VOLATILIDADE_ALTA` diz.
  Exceções óbvias: 0, 1, 100 em porcentagem, índices.
- Limites de negócio têm **um lugar só**: planos em `src/planos.py`, páginas em `src/paginas.py`,
  cores e fontes em `src/marca.py`, textos legais em `conteudo/`.

## 4. Tipos e documentação

- 🤖 **Anotações de tipo em `src/`** (ANN): `def retorno(precos: pd.Series) -> float:`.
- **Docstring** em toda função pública: uma frase dizendo o que devolve e, se não for óbvio, o
  que cada parâmetro significa e as unidades (fração ou porcentagem? dias úteis ou corridos?).
- **Comentário explica o porquê, não o quê.** O código já diz o que faz; o comentário conta a
  razão ("o Yahoo devolve o último dia duas vezes no fim de semana").
- Código morto e comentado é apagado: o Git guarda a história.

## 5. Arquitetura

- **`src/` não importa o Streamlit.** Regra de negócio em `src/`; a tela em `telas/` (o `app.py`
  só monta o menu) só lê, chama e mostra. Assim a regra é testável sem abrir o navegador.
- Dados entram validados na borda (o que vem do usuário ou da URL é texto não confiável) e o
  resto do código confia neles.
- **Erros:** capture só a exceção que você sabe tratar (`except ValueError`), nunca `except:`
  vazio; mensagem para o usuário em português, detalhe técnico no log (sem dados pessoais).

## 6. Testes

- Todo comportamento novo vem com teste; todo bug corrigido ganha **teste de regressão** que
  falhava antes da correção.
- Nome do teste é uma frase: `test_carteira_sem_ativos_mostra_aviso`.
- Um teste confere uma ideia; use dados pequenos e determinísticos (semente fixa), sem internet.
- Princípios que têm teste: **sem olhar o futuro**; consultas filtradas pelo usuário; Stripe só
  em modo de teste.

## 7. Estilo automático 🤖

- `ruff format` define a formatação (não discutimos espaço e quebra de linha).
- `ruff check` com as regras de `ruff.toml`: erros comuns (B), simplificações (SIM), Python
  moderno (UP), imports em ordem (I), complexidade (C90), desempenho (PERF), tipos (ANN).
- Uma exceção pontual leva `# noqa: CODIGO` **com o motivo** na mesma linha.

## 8. Git

- Commits pequenos, cada um com uma ideia, mensagem `tipo: o que mudou` em português
  (`feat`, `fix`, `refactor`, `docs`, `test`, `perf`, `ci`, `chore`).
- Ramos `feat/...`, `fix/...`, `refactor/...`, `docs/...`; a `main` só recebe PR com o CI verde.
- **Refatoração separada de mudança de comportamento:** um PR que só reorganiza não muda
  resultado (os testes provam), e fica fácil de revisar.

## 9. Antes de abrir um PR (checklist)

- [ ] Funções novas curtas, com nome claro, tipo e docstring.
- [ ] Nenhum número mágico novo; nenhum segredo, e-mail ou IP no código.
- [ ] Testes do que mudou passando; `ruff check` e `ruff format --check` limpos.
- [ ] O trecho que você tocou ficou mais claro do que estava ("regra do escoteiro").
- [ ] Pronto para trocar de interface: nenhum cálculo, regra ou texto novo em `telas/` (só ler, chamar
      `src/` e mostrar); estado que importa no banco; truque do Streamlit isolado e testado.
- [ ] O PR explica o que muda, o que não muda e como foi testado.

## Dívida conhecida (a pagar em etapas)

- Cálculos do pandas que ainda moram em telas (`telas/estrategias/backtest.py`, `carteira.py` e
  `experimentos.py`): levar para `src/`, com teste, antes de essas telas migrarem para outra interface.
- A API só tem saúde, webhook e Newsletter: as análises principais ainda não têm rota de leitura.

- ~~`app.py` gigante~~: dividido em `telas/` em 12/10/2026 (229 linhas: entrada e menu); as funções
  acima da complexidade 15 foram divididas e o C901 e o B905 valem em todo o código.
- `src/relatorios.py` com funções de 125 a 200 linhas: quebrar por seção do relatório.
- Funções de tela ainda longas (mais de ~100 linhas, mas abaixo da complexidade 15): dividir quando
  forem tocadas.
- ~~Checagem de tipos e cobertura no CI~~: no CI desde 12/10/2026 (`pyright` em `src/`, `scripts/` e
  `telas/`; cobertura mínima no `.coveragerc`).
