# Critérios dos agentes analistas (camada A3), versão 0.1

> **Estado: APROVADO pelo Tiago em 03/11/2026 às 22h03 ("Aprovar como está"; nível 1).** Os critérios são do
> Tiago (ADR 0118, Emenda 1, item 8: "critérios escritos pelo Tiago antes"); o Claude escreveu a proposta e ele a
> aprovou sem mudança. O hash deste texto está em `trader/agentes/criterios.py`, e o código recusa preparar ou
> registrar uma rodada se o texto mudar. O texto não muda mais: mudar qualquer coisa vira a versão 0.2, com data e
> motivo, e as rodadas anteriores ficam marcadas com a versão antiga.

## 1. O que é

A camada A3 da carteira própria: agentes de IA analisam empresas no padrão de análise do TickerLab
(`docs/padrao-de-analise.md`) e dão uma nota contra os critérios da seção 4. Os agentes decidem e a regra da seção 5
monta a carteira. Um modelo de linguagem já sabe o que aconteceu com as empresas no passado, então não há backtest
honesto. Por isso a camada **roda em papel por 12 meses**. Cada escolha é registrada no dia (data e hash, sem edição)
e só é comparada com preços posteriores a ela. Depois da revisão dos 12 meses, dinheiro real entra só com decisão
escrita do Tiago.

O Claude não escolhe empresas para o dinheiro do Tiago: o universo é mecânico (seção 2), a nota segue critérios
escritos antes (seção 4) e a carteira sai de uma regra fixa (seção 5).

## 2. Universo (mecânico)

No dia da rodada entram as ações elegíveis pela seção 8 do pré-registro quant v0.1, que são as mesmas dos fatores
na B3:

- volume financeiro médio de pelo menos **R$ 5 milhões por dia** nos 60 pregões anteriores (piso proposto; o Tiago
  confirma junto com este texto);
- pelo menos 12 meses de pregão;
- uma classe por empresa (a mais líquida);
- fora de recuperação judicial;
- com balanço divulgado nos últimos 12 meses.

Das elegíveis, entram **as 30 mais líquidas**: o limite da ADR é de 30 empresas por rodada. Com menos de 60 pregões
na base, a rodada não acontece.

## 3. A rodada

- **Uma por mês**, do 1º ao 5º pregão do mês. O registro leva a data do dia em que é feito, e o código recusa uma
  segunda rodada no mesmo mês.
- **Um agente por empresa** (subagente Sonnet, numa sessão local, pela assinatura). Cada agente é independente: não
  vê as notas das outras empresas nem as rodadas anteriores. A nota é absoluta, contra os critérios, e não um
  ranking.
- **O pedido é fixo:** `trader/agentes/prompts/analista.md`, com a empresa, a data e este texto. O agente escreve o
  dossiê no padrão de análise e termina com o bloco da nota (seção 4.3).
- **Só o que já era público na data.** Fato com fonte e data. O que não foi achado ou conferido fica escrito.

## 4. Critérios (a nota)

### 4.1 Os seis critérios

Cada critério recebe uma nota inteira de 0 a 10. A nota final é a média ponderada (0 a 10, com uma casa).

| Código | Critério | Peso | 10 | 5 | 0 |
|---|---|---|---|---|---|
| C1 | **Negócio:** o que vende, a quem, se o cliente tem para onde ir; retorno sobre o capital (ROIC) dos últimos 5 anos | 20 | ROIC acima do CDI médio do período em 5 de 5 anos, com a vantagem descrita em fonte | ROIC perto do CDI ou instável | ROIC abaixo do CDI na maioria dos anos |
| C2 | **Qualidade do lucro:** caixa operacional ÷ lucro líquido nos últimos 3 anos; margens; parecer do auditor; reapresentações | 15 | caixa ≥ 90% do lucro nos 3 anos, sem ressalva nem reapresentação | caixa entre 50% e 90% do lucro, ou margem muito instável | lucro sem caixa, ou reapresentação relevante |
| C3 | **Dívida:** dívida líquida ÷ EBITDA; vencimentos de 24 meses contra caixa e geração; dívida em moeda estrangeira sem proteção (bancos e seguradoras: Basileia ou solvência, dizendo qual) | 15 | caixa líquido ou dívida líquida abaixo de 1 EBITDA | de 1 a 2,5 EBITDA | acima de 3,5 EBITDA, ou vencimentos maiores que caixa e geração |
| C4 | **Governança:** segmento de listagem, tag along, partes relacionadas, histórico com minoritários, remuneração; bases oficiais (CVM, CEIS, CNEP, IBAMA, Lista Suja) do grupo inteiro | 15 | Novo Mercado, nada nas bases e partes relacionadas pequenas e explicadas | nível 1 ou 2, ou um ponto de atenção explicado | controle com histórico contra o minoritário, ou ocorrência relevante nas bases |
| C5 | **Preço:** P/L, EV/EBIT e dividend yield contra o próprio histórico de 10 anos e os pares | 20 | abaixo do percentil 25 do histórico e dos pares, sem queda estrutural do negócio que explique | perto da mediana | acima do percentil 75 |
| C6 | **Riscos:** regulatório e político, concentração de cliente ou fornecedor, ciclo do setor, contingências ÷ patrimônio, eventos conhecidos | 15 | riscos pequenos e documentados | um risco relevante com mitigação | um risco que pode tirar mais da metade do valor |

### 4.2 Vetos (nota final 0; a empresa não entra)

| Código | Veto |
|---|---|
| V1 | recuperação judicial ou extrajudicial em curso, ou pedida |
| V2 | parecer do auditor com ressalva, abstenção ou adverso no último exercício |
| V3 | empresa do grupo na Lista Suja do trabalho escravo ou com sanção em vigor no CEIS ou no CNEP |
| V4 | administrador ou controlador em exercício condenado em processo sancionador da CVM nos últimos 5 anos |
| V5 | demonstrações reapresentadas por erro nos últimos 12 meses |

Veto é fato: precisa de fonte. Uma base que não pôde ser conferida fica escrita como "não conferida" e não vira veto.

### 4.3 Disciplina da nota

- Critério sem fonte tem nota **no máximo 5**: incerteza não ganha nota alta.
- Número com mais de dois anos é marcado como velho, e o critério que depende dele tem nota no máximo 5.
- O dossiê termina com um bloco `json` só com a nota, no formato do pedido: `vetos` (lista de códigos com a fonte),
  `itens` (C1 a C6, cada um com `nota` e `fontes`) e `resumo` (uma frase). O código confere o bloco: todos os
  critérios, notas inteiras de 0 a 10, fonte em toda nota acima de 5. Um bloco fora do formato não entra no
  registro.

## 5. A regra (os agentes decidem, a regra compra)

1. A nota final é a soma de peso × nota, dividida por 100. Com veto, a nota final é 0.
2. Entram **as até 5 maiores notas finais de 7,0 para cima**. Empate na nota: entra a mais líquida.
3. **Pesos iguais de 20%.** Com menos de 5 empresas, o que sobra fica em CDI. Sem empresa acima do corte, a
   camada fica toda em CDI.
4. A carteira em papel é montada no **fechamento do pregão seguinte ao registro** e fica parada até a rodada
   seguinte. O custo de negociar é o da tabela de custos do Brasil (`trader/custos_br.py`).
5. **Freio da camada:** queda de 40% do pico da carteira em papel → CDI (seção 6 do pré-registro).

## 6. Registro e "sem olhar o futuro"

- O registro fica fora do Git (`pesquisa_quant/agentes/`). Cada rodada é uma linha com data, versão e hash destes
  critérios, modelo, candidatas, notas, escolhidas e pesos, e o hash do dossiê de cada empresa. A linha também traz
  o hash da linha anterior, numa cadeia: editar qualquer linha quebra a conferência.
- Os dossiês ficam guardados com o nome igual ao próprio hash.
- No dia da rodada, o hash da ponta da cadeia vai para a nota privada da conversa e para a Central. Assim existe
  uma prova fora do PC de que o registro existia naquele dia.
- A data do registro vem do relógio. O código recusa data passada ou futura, rodada fora de ordem e segunda rodada
  no mesmo mês.

## 7. Comparação aos 12 meses

Para cada rodada com 12 meses completos, usando só preços posteriores à data dela:

- o retorno das escolhidas contra a **cesta das 30 candidatas com pesos iguais** (a régua principal: diz se a nota
  agrega algo à lista mecânica), o Ibovespa e o CDI;
- a **correlação de Spearman** entre a nota final e o retorno de 12 meses das 30 candidatas;
- a carteira em papel inteira (rodada após rodada, com custo e freio) contra o CDI e o Ibovespa.

O preço é ajustado por proventos. A fonte dos preços ajustados de hoje em diante fica **a confirmar** antes da
primeira comparação, em 12/2027.

## 8. A revisão dos 12 meses e o dinheiro real

Doze rodadas são uma amostra pequena: pela régua de anos ≈ (t ÷ SR)², nenhum resultado de 12 meses prova
habilidade. A revisão é escrita e a decisão é do Tiago. A proposta é que dinheiro real só seja considerado se
as quatro condições abaixo valerem ao mesmo tempo:

- as escolhidas bateram a cesta das 30, líquidas de custo;
- as escolhidas bateram o CDI;
- a correlação média entre nota e retorno foi positiva;
- o freio de 40% não disparou.

Se alguma falhar, a camada continua em papel ou para.

## 9. Limites e cuidados

- Não há backtest: a camada se mede só para frente, em papel.
- O mesmo modelo de linguagem dá todas as notas. Erros dele se repetem entre as empresas, e a correlação mede isso
  mal com 30 empresas.
- As fontes que o agente acha na rede variam de uma rodada para outra; o dossiê guarda o que ele usou.
- O universo é das ações mais líquidas, ou seja, de empresas grandes e muito acompanhadas, onde é mais difícil
  achar o que o mercado não viu.
- Nada aqui é recomendação de investimento. O dossiê e a nota são internos e nunca são publicados.

## 10. O que o Tiago decide ao aprovar

- Os seis critérios, os pesos, as âncoras e os vetos (seção 4).
- O corte de 7,0, o máximo de 5 empresas e os pesos iguais (seção 5).
- O piso de liquidez de R$ 5 milhões por dia e as 30 mais líquidas (seção 2).
- As quatro condições da revisão dos 12 meses (seção 8).
