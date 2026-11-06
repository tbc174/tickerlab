# Ficha F-B3 (fatores na B3): conferência da base antes da primeira tentativa

> **Superado:** a base que faltava (COTAHIST anual de 2009 a 2023) foi completada no mesmo dia
> (`docs/conferencia-base-b3-2009-2023.md`) e a ficha rodou em 04/11/2026
> (`docs/resultado-fatores-b3-tentativa-1.md`). Este arquivo fica só como registro da conferência.

Gerado em 03/11/2026 pela conversa "Satélites · carteira própria e trade 24/7", PR 5 do plano v2 da
carteira própria (ADR 0118, Emenda 1). Pré-registro quant v0.1 (hash
`ea45eddf09e89f1cee5af3e7612fac2739cebf05ab1583e5270c6b3c2f403269`), ficha F-B3.

**Veredito: INCONCLUSIVA, sem universo histórico.** A ficha não rodou e **nenhuma das 10 tentativas
foi gasta**: a base local não tem o que a seção 8 do pré-registro exige para montar o universo mês a
mês de 2010 a 2023 com as ações que foram deslistadas. Rodar só com as sobreviventes daria um número
com viés de sobrevivência, e a seção 2 diz que esse resultado não autoriza dinheiro. O plano v2 mandava
"conferir primeiro se a base tem as deslistadas": a resposta é não.

## O que a base tem e o que falta

| Tabela da ficha | O que há na cópia local do acervo | Falta |
|---|---|---|
| Preços e volume diários de toda a B3 (2010–2023) | COTAHIST **diário** só desde 09/2026; lote anual (`b3-cotahist-anual`) de **1986 a 2009**; export do MT5 com 25 ações sobreviventes e índices | COTAHIST anual de 2009 a 2023 (o universo inteiro, deslistadas incluídas) |
| Preços ajustados (momento e volatilidade) | `eventos_de_capital/<ano>` (desdobramentos e grupamentos) e `proventos/<ano>` de 2010 a 2023 | uma base de preços ajustados construída com essas tabelas (fila, linha 59) |
| Quantidade de ações em circulação (valor da firma) | nada: o FCA geral tem categoria, setor e controle, sem quantidade de ações | tabela ponto no tempo (CNPJ, quantidade, data em que ficou pública) |
| Balanços ponto no tempo | `demonstracoes/<ano>` de 2010 a 2026 com `divulgado_em` e `ate` (ITR e DFP, plano de contas industrial) | nada; bancos ficam sem EBIT e sem empréstimos (plano de contas próprio): limitação declarada |
| Cadastro (CNPJ, classe, datas) | `fca/emissores` e `fca/tickers` desde 2018; o ISIN do COTAHIST dá o emissor | nada para quem existiu depois de 2018; antes disso o CNPJ vem pelo emissor do ISIN |
| Recuperação judicial | nada estruturado | lista com início e fim (sem ela o filtro não roda: limitação declarada) |
| CDI e Ibovespa (réguas) | SGS 12 em cache; BOVA11 no export do MT5 desde 2008 | nada |

## O que o PR 5 entregou mesmo sem a base

- **Motor** `trader/estrategias/fatores_b3.py`, com as convenções escritas no topo antes de qualquer
  número: ponto no tempo (balanço divulgado em D entra em D+1; os 12 meses são DFP + acumulado do ano
  − acumulado do ano anterior), universo da seção 8 (liquidez dos 60 pregões anteriores sem o próprio
  dia, 12 meses de pregão, uma classe por empresa, balanço nos 12 meses, sem recuperação judicial,
  deslistadas enquanto existiram), os 4 fatores, a média dos escores z com pelo menos 3 fatores, as
  20% melhores em pesos iguais, decisão no primeiro pregão do mês e execução na abertura do pregão
  seguinte em ações inteiras, banda de 20%, custos de `custos_br` com impacto de raiz quadrada, IR com
  a isenção de R$ 20 mil e DARF no fim do mês seguinte, venda da deslistada no último preço.
- **Conferência de sobrevivência** (`conferir_sobrevivencia`): sem nenhuma deslistada, o relatório sai
  com o aviso escrito e o veredito V fica reprovado (`dados_conforme=False`).
- **Testes do Brasil** prontos no `rodar_f_b3`: (a) com e sem deslistadas, (b) carteiras de R$ 100 mil,
  500 mil e 2 milhões para a isenção, (c) balanço pela data de divulgação contra a data do balanço.
- **Carregador** `trader/estrategias/dados_f_b3.py`: lê o COTAHIST anual (layout de 245 posições),
  monta os painéis, o cadastro pelo ISIN e os fundamentos do acervo; `conferir_base` lista o que falta.
- **Rodada** `python -m trader.estrategias.rodar_f_b3`: com faltas, imprime este veredito e sai sem
  tocar no registro; com a base, registra uma tentativa por execução e escreve o relatório.
- 43 testes com dados sintéticos (12 ações, uma deslistada em 15/06/2018): ponto no tempo, universo,
  fatores, notas, banda, isenção, cortar o futuro, reexecução, estresse, sobrevivência e a rodada.

## Limites e cuidados

- Nenhum número de retorno foi produzido com dados reais; os testes usam preços sorteados.
- O carregador ainda não foi exercitado com arquivos reais do COTAHIST anual: a primeira carga vai ser
  uma conferência de dados (não gasta tentativa) antes da tentativa 1.
- Bancos e seguradoras ficam sem o fator valor (plano de contas diferente) e, com 3 de 4 fatores, ainda
  entram; isso é uma escolha de v0.1 escrita antes dos números e será avaliada no relatório da tentativa 1.
- A régua "Ibovespa total líquido" é o BOVA11 comprado e mantido, sem o IR da venda final.
- Desenvolvimento só (até 08/09/2023); o holdout continua lacrado e só abre com decisão escrita do Tiago.
- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

## Próximo passo (mesa de Dados, fila)

COTAHIST anual de 2009 a 2023 no acervo (a URL pública da B3 é a mesma do lote de 1986–2009), preços
ajustados pelos eventos de capital e proventos já guardados, e a quantidade de ações em circulação
ponto no tempo (do FCA ou do formulário de referência). Com os três arquivos em `pesquisa_quant/f_b3/`,
`conferir_base` devolve vazio e a tentativa 1 da F-B3 pode rodar.
