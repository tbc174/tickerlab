# Padrão de análise do TickerLab

Pedido do Tiago em 24/10/2026: **toda análise do TickerLab segue este padrão**. Vale para qualquer IA e para
pessoas, em qualquer análise de empresa ou de grupo: companhia aberta, empresa fechada, grupo familiar, holding,
fornecedor, contraparte. Os exemplos que viraram régua (dois grupos agropecuários fechados, pesquisados em 24/10)
ficam na pasta privada do autor, porque têm nomes de pessoas.

Este padrão **soma** com as regras que já existem, não as troca:

- o relatório de companhia aberta continua sendo a análise completa da ADR 0100, com o gabarito da CPFL como régua
  de tom e profundidade (texto corrido, fonte em cada frase, "Leitura" separada do fato);
- o que é publicado para usuários continua passando pelas regras de pessoas na base (ADR 0075 e 0106), pelas
  portas de conferência (ADR 0093) e por "nada é recomendação de investimento".

## A ordem das seções

1. **Em uma frase.** No topo, o que é o grupo ou a empresa, de quem é, onde atua e o que faz, em uma ou duas frases
   que alguém de fora entende. Na companhia aberta, é o começo do "Em meia página" do gabarito.
2. **Estrutura societária.** O mapa completo, não só a empresa pedida:
   - parta do CNPJ (ou do nome) e leia o quadro de sócios na Receita;
   - siga cada sócio, pessoa ou holding, até achar **todas** as empresas ligadas, nas duas direções (de quem a
     empresa é e o que ela tem). A base aberta de CNPJ da Receita, que o acervo já guarda, permite isso;
   - uma tabela com empresa, abertura, situação, capital, atividade e sócios, com a data de entrada de cada sócio;
   - diga quem é sócio e quem é só administrador: a diferença muda a leitura.
3. **História.** Uma linha do tempo, com o ano e a fonte de cada marco. Quando não há reportagem, a história sai
   do próprio cadastro (aberturas, entradas e saídas de sócios, empresas fechadas).
4. **Atividades e ativos.** O que o grupo faz e onde: fazendas, fábricas, lojas, concessões, marcas. Uma tabela com
   o lugar, a atividade e os números, sempre com **o ano da fonte** ao lado de cada número.
5. **Conferência nas bases oficiais.** Cruze o grupo inteiro (as pessoas com função no grupo e todos os CNPJs, não
   só a empresa pedida) com as bases públicas que se aplicam, e escreva a data de cada base:
   - IBAMA: termos de embargo e autos de infração;
   - Cadastro de Empregadores do MTE (a "Lista Suja" do trabalho escravo);
   - sanções: CEIS, CNEP, CVM, Banco Central;
   - dívida no mercado: CRA, CRI, debênture, FIAGRO; recuperação judicial e falência;
   - terra, quando houver fazenda: CAR, SIGEF e INCRA;
   - o que for próprio do setor (ANEEL, ANP, ANS, ANAC, licenças ambientais do estado).

   Confira pelo nome **e** pelo CNPJ ou CPF mascarado, e descarte o homônimo antes de relatar. "Nada encontrado"
   é um resultado e se escreve, com a base e a data. Busca na web não substitui a base oficial.
6. **Riscos e o que não achei.** O que pesa contra, o que não foi encontrado, o que não foi conferido e por quê, e os
   números velhos ("os dados de produção são de 2013"). O buraco fica à vista, como o "a base não tem" do gabarito.
7. **Comparação.** Quando houver um par natural (outro grupo do mesmo setor e região, outra análise já feita, a
   mediana do setor), uma tabela curta lado a lado.
8. **Fontes.** No fim, a lista de links, agrupada por tipo (cadastro, balanços, bases oficiais, reportagens). Na
   companhia aberta, as notas de rodapé do gabarito fazem esse papel.

## Regras que valem em todas as seções

- **Fato separado de dedução.** O que está escrito em alguma fonte é fato, com a fonte. O que a análise conclui vai
  num bloco à parte, com o título "O que eu concluo disso (é dedução, não está escrito em lugar nenhum)" ou
  "Leitura", e diz em que fatos se apoia.
- **Nomes parecidos que não são do grupo.** Liste os homônimos que apareceram na pesquisa (mesmo nome, outra
  cidade, outro sócio) e diga por que não são do grupo. Evita que o leitor junte coisas que não se juntam.
- **Data em tudo.** Data da base consultada, ano de cada número, data de entrada de cada sócio. Dado com mais de
  dois anos é marcado como velho.
- **Pouca exposição pública também é informação.** Se o grupo quase não aparece na web e a análise sai quase toda
  do cadastro, diga isso no começo.
- **Privacidade.** Nunca o CPF, nem os dígitos que a Receita deixa à mostra. Menor de idade não é nomeado (diga "os
  filhos"). Sem telefone, e-mail ou endereço residencial. Nenhum dado sensível (saúde, religião, política). Pessoa
  aparece pela função que tem no grupo.
- **Honestidade.** Capital social não é patrimônio nem faturamento. Nada de "boa empresa", nota, recomendação ou
  previsão.
- **Linguagem.** Português do Brasil, frases curtas, cada termo técnico explicado na primeira vez (`conteudo/glossario.md`).

## Fim da análise

Antes de entregar, confira:

- [ ] o mapa societário seguiu todos os sócios, não só a empresa pedida;
- [ ] cada número tem fonte e ano;
- [ ] as deduções estão separadas dos fatos;
- [ ] as bases oficiais foram cruzadas pelo grupo inteiro, com a data de cada uma, e os homônimos foram descartados;
- [ ] o que não foi achado ou conferido está escrito;
- [ ] nenhum CPF, menor de idade, contato ou endereço residencial;
- [ ] nenhuma frase de recomendação.
