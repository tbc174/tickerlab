# Scalp no mini índice (WIN), fase 1b: fluxo de ordens (pré-registro)

**Status: VIGENTE, versão 1.0, escrita em 29/10/2026 antes de qualquer medida desta fase.** O commit que traz
este arquivo vem antes do código que mede. Pedido do Tiago em 29/10/2026 ("vamos fazer o 1b"), depois de a
fase 1 reprovar (`docs/resultado-scalp-win-fase1.md`). Pesquisa à parte da M2, só leitura.

> **Aprovar aqui não quer dizer lucro.** Aprovar só justifica conferir a regra em pregões novos (seção 5) e,
> depois, a fase 2 em conta demo com autorização escrita do Tiago. Reprovar é um resultado válido. Nada
> aqui é recomendação de investimento.

## 1. A pergunta

A fase 1 mostrou que olhar só o preço não basta. A pergunta agora é se o **fluxo** dos últimos minutos prevê
o preço dos minutos seguintes o bastante para passar do custo. O fluxo é quem agrediu ou quais corretoras
compraram e venderam.

## 2. Dados

Os mesmos da fase 1, com as mesmas regras: os 23 pregões que entram na tabela do
`docs/pre-registro-scalp-win-fase1.md`, com o mesmo hash por arquivo, o mesmo contrato do dia, a mesma
limpeza e a mesma janela das 09h15 às 17h45. **Desenvolvimento:** os 11 primeiros. **Validação:** os 12 últimos.

Acrescenta duas colunas do mesmo arquivo: `CodigoParticipanteComprador` e `CodigoParticipanteVendedor`. São
os códigos das corretoras na B3. Os nomes delas não são usados nem guardados.

**Cuidado conhecido:** os preços desses 23 pregões já foram vistos na fase 1. Os sinais desta fase são novos,
mas o período é o mesmo. Por isso, aprovar aqui exige confirmar em pregões novos (seção 5).

## 3. Sinais e regras (16 variantes, toda a lista)

A decisão é tomada a cada h minutos, a partir das 09h15 + h, com os negócios da janela [t − h, t). A
operação é de 1 contrato, com saída h minutos depois, sem sobreposição e com a última saída até 17h45. É a
mesma grade de preços da fase 1. Horizontes: h ∈ {1, 2, 5, 10} minutos. Sinal igual a zero: não opera.

- **F. Fluxo do agressor (regra do tick).** Cada negócio leva o sinal da mudança de preço que ele causou:
  +1 se subiu e −1 se caiu. Se o preço não mudou, o negócio herda o sinal do anterior, e o primeiro do dia
  fica com 0. O sinal da regra é o sinal da soma de (sinal × quantidade) na janela.
  - **F-momento:** segue o fluxo (compra quando a compra agrediu mais).
  - **F-reversão:** vai contra o fluxo.
- **C. Fluxo das corretoras de lote pequeno.** O grupo é escolhido só com os pregões do desenvolvimento.
  - **Entram no grupo:** as corretoras com pelo menos 1% do volume do WIN (comprado + vendido, dividido
    por 2 × volume) que estão na metade de baixo, contando a de lote médio igual à mediana.
  - **Lote médio:** quantidade média por negócio, somando os lados de compra e de venda.
  - **Sinal:** o sinal da compra líquida do grupo na janela (quantidade comprada por corretoras do grupo
    menos a vendida por elas; negócio entre duas do grupo se anula).
  - **C-momento:** segue o grupo.
  - **C-reversão:** vai contra o grupo.
  - **Limite:** o grupo é "de lote pequeno", não "varejo". Robôs de alta frequência também negociam lotes
    pequenos.

Momento e reversão do mesmo sinal e horizonte são as mesmas operações com o sinal trocado. São 8 testes
independentes em 16 variantes.

## 4. Critério de aprovação

- **Empate:** E = **10 pontos** por operação, fixo. A fase 1 mediu um spread de 2,6 pontos, e a conta dá
  2,5 + 2,6 + 2,5 = 7,6, abaixo do piso de 10.
- **Passos:**
  1. No desenvolvimento, escolhe-se **uma** das 16 variantes, a de maior ganho bruto médio por operação.
     Em empate, vale a primeira na ordem F e depois C, h crescente e momento antes de reversão.
  2. Na validação, mede-se **só essa**: o ganho bruto médio por operação e o intervalo de 95% por
     bootstrap de dias (10.000 reamostras dos 12 dias, com reposição, semente 20261029, percentis 2,5 e
     97,5).
  3. **APROVA** se o limite inferior for maior que E. **REPROVA** em qualquer outro caso.
- As 16 variantes aparecem no resultado, e só a escolhida decide.

## 5. Se aprovar: confirmação antes da fase 2

A regra aprovada é medida, sem mudar nada, em pelo menos 15 pregões novos, posteriores a 22/10/2026, com
selo `completo`. Ela segue só se o ganho médio passar de E nesses pregões. Essa conferência tem o próprio
registro, escrito antes de rodar.

## 6. Tentativas

A fase 1 foi a tentativa 1 da pesquisa do scalp, com 8 variantes. Esta é a **tentativa 2**, com 16. A medida
roda uma vez. Uma correção de erro de código vira a tentativa 3, com o motivo escrito.

## 7. Limites

- A regra do tick erra parte dos negócios sem mudança de preço. O lado agressor de verdade vem com o
  negócio no MetaTrader 5 de uma corretora da B3. Essa medida, se o Tiago quiser, fica para outra versão.
- Sem livro de ofertas. A operação é a mercado.
- 23 pregões, um só regime de mercado.
