# TickerLab: virada para empresas fechadas e M&A

Nov 5, 2026 · @Tiago

Documento de passagem para o Claude Code: a decisão tomada em 5/11/2026, o debate que levou a ela, o inventário de dados e o plano de trabalho no repositório.

## Decisão de 5/11/2026

O TickerLab passa a ter como foco principal cruzar dados de empresas fechadas, além das abertas, e a primeira venda é para uma boutique de M&A.

- **Primeiro cliente:** boutique de M&A, para originação de alvos e diligência. Consolidadores, search funds e analistas de crédito vêm depois, com o mesmo produto.
- **Toda a base vai a público**, inclusive as tabelas hoje barradas no app: insolvência, dívida na PGFN, situação especial do CNPJ e rótulos de atraso. Não se espera parecer jurídico para isso; a decisão é do autor.
- **Ficha Clara passa a consumir a API do TickerLab.** A Ficha Clara vira a porta de entrada gratuita (consulta de CNPJ); o TickerLab vira o motor pago.
- **O research de empresas abertas continua.** As listadas são as compradoras, e o FRE (controladas e coligadas) é a ponte entre empresa fechada e aberta.
- **O que se vende é API e alertas**, não telas novas. A boutique compra a consulta por CNPJ, o histórico e o monitoramento de uma lista de alvos.
- **Prioridade imediata do autor:** ter dados importantes de empresas abertas e fechadas para análise e cruzamento. Riscos legais estão fora do escopo deste documento por decisão dele.

**Acréscimo de 5/11/2026 (Tiago, na conversa com o Claude Code):** "e vamos focar também em análise de crédito". A análise de crédito entra como foco ao lado do M&A, e não só "depois": o analista de crédito é cliente da mesma API e dos mesmos alertas. As tabelas que a fase 1 libera (dívida na PGFN, insolvência, situação especial do CNPJ e rótulos de atraso) são justamente os sinais de crédito, então a fase 1 não muda; nas fases 2 a 4, os comparáveis e o monitoramento ganham o olhar de quem empresta (atraso de balanço, dívida com a União, pedido de recuperação), sem nota, score nem opinião de crédito (B-31: o TickerLab mostra o fato e a fonte).

**Acréscimo de 6/11/2026 (Tiago, na conversa com o Claude Code):** "Eu não quero esperar parecer jurídico pra mais nada". A virada de 5/11 já tinha posto a base a público sem esperar o parecer; agora a regra vale para tudo: **nenhuma trava do repositório espera mais parecer jurídico**. No lugar do parecer, a decisão sai da **nossa leitura do texto da norma** (já lida e anotada, com a data, como em `REGULATORY_WATCH.md` do Capital), registrada no PR. O que não muda: as duas revisões antes do merge em área sensível e nível 1 (`AGENTS.md`), as travas de licença de dado (são do dono do dado, não de advogado) e o que é só do Tiago (gasto, contrato, CNPJ, terceiro, Stripe fora do modo de teste). Leituras da casa que passam a valer no lugar do parecer:

- **Score de crédito (B-31) liberado.** Pela leitura da Resolução CVM 9 (art. 1º, lida em 16/10), opinião sobre a qualidade de crédito de **emissor de valor mobiliário** é de agência registrada, "ainda que restrita a clientes". Regra da casa: score só de **empresa que não é emissora** (fechada, cedente, sacado); companhia aberta e emissor de debênture, CRI ou CRA recebem sinais e fatos, não score. Nunca "rating", nunca escala de letras, nunca sobre cota ou fundo.
- **Pessoa física continua fora** por leitura da LGPD (finalidade e minimização), não por espera: nome de sócio só pelo portão dos nomes quando houver finalidade escrita; CPF nunca; CNPJ de MEI tratado como dado pessoal (fora do score ou com revisão, LGPD art. 20).
- **Travas que esperavam parecer e devem ser revistas, uma por PR:** `src/credito/features.py` e `src/credito/dossie.py` (B-31), `src/credito/montar_dossie.py` (sanções), `src/busca_por_cnpj.py` (dívida com a União e sanções da rede), `base/fre_governanca.py` (pessoa física: segue a regra acima), `base/arquivo/wayback.py` e `src/banco/coletas.py` (licenças "só uso interno até o parecer"). Trava que espera a resposta do **dono do dado** (FMI em `src/commodities/painel_de_precos.py`, B3) não é parecer e fica.

## Resumo do debate

A tese que saiu do debate: dado de CNPJ é commodity; o diferencial do TickerLab é ponto no tempo, linhagem e cruzamento entre fontes.

**Por que não prospecção genérica.** Econodata nasce do cadastro de CNPJ; a Speedio diz cobrir mais de 40 milhões de CNPJs com mais de 117 fontes; Neoway, Driva e CNPJ Biz disputam o mesmo espaço. Esse mercado é time de SDR, telefone e e-mail, integração com CRM e preço baixo por assento. Entrar nele é perder por preço e por time de vendas.

**O que esses concorrentes não têm.** Eles mostram a empresa de hoje. O TickerLab mostra a empresa em qualquer data (`como_era_em`) e de onde veio cada número (linhagem até o original no acervo). Usuários da Econodata reclamam da imprecisão dos dados e pedem que a ferramenta mostre as dívidas das empresas: exatamente as tabelas que vão ser liberadas.

**O que "análise de empresa fechada" significa.** LTDA não publica balanço. Então análise aqui é sinal + história + relação, não fundamento: mudança de capital, troca de sócio, FIDC, BNDES, exportação, contrato público, dívida, RJ, ato no CADE. A única exceção são setores regulados com balanço por empresa (ANS, SUSEP, bancos no IF.data) e S.A. fechadas na Central de Balanços.

**Por que M&A antes de prospecção.** Boutique, consolidador, search fund e crédito são poucos clientes, de ticket alto, que compram profundidade e confiança. O relatório TTR LatAm do 2º trimestre de 2026 diz que compradores querem mais clareza sobre riscos, governança, documentação e qualidade das informações. A TTR vende demonstrações financeiras de empresas brasileiras, de fontes oficiais, como adicional da assinatura; o espaço vazio é histórico + relações + sinais por CNPJ. A OverA (ligada à igc Partners) usa uma calculadora pública de valuation como fonte de originação, prova de que comparáveis para empresa fechada vendem.

**O gargalo não é coleta.** A base já tem 86 tabelas (contagem de 19/10) e metade não aparece em tela nenhuma. Mais fontes sem uma pergunta que elas respondam é mais catálogo, não mais produto. As fontes novas desta virada entram por serem insumo das três camadas da seção "O produto".

**Ferramentas de prospecção são clientes, não concorrentes.** Depois do produto para M&A, Econodata e similares podem comprar sinais e histórico pela API.

## Inventário de dados

Três listas: o que a base já tem, o que falta e é aberto por CNPJ, e o que não existe aberto por CNPJ (por mais que uma pesquisa de IA tenha prometido). Conferir cada item contra `base/contratos/catalogo.json` e `base/arquivo/fontes.py` antes de coletar.

**Já na base (58 fontes no arquivista, 86 tabelas no catálogo)**

| Dado | Fonte | Uso na virada |
| --- | --- | --- |
| Cadastro de CNPJ: QSA, capital, CNAE, situação, situação especial | Receita Federal | Espinha dorsal; versões mensais dão o histórico de sócios e capital |
| Dívida ativa da União e FGTS | PGFN (base completa trimestral em dados abertos) | Sinal de risco; hoje barrada no app |
| Insolvência (RJ e falência), rótulos de atraso | Tribunais e derivadas | Sinal de risco; hoje barradas no app |
| Sanções (CEIS/CNEP), autuações | CGU, IBAMA | Diligência |
| Controladas e coligadas das listadas | CVM, FRE | Ponte entre empresa fechada e aberta |
| Fatos relevantes, DFP, ITR, FCA, cadastros, emissores antigos, tickers no tempo | CVM | Linha do tempo das abertas; M&A anunciado |
| Ofertas restritas (debêntures, CRI, CRA) de emissores fechados | CVM | Financiamento e, às vezes, demonstrações do emissor |
| Informes de 6.178 FIDCs | CVM | Quem financia recebíveis via FIDC |
| Carteiras dos fundos, 21 anos | CVM, CDA | Quem detém o quê |
| Balanços de 5.865 instituições e vínculo banco-empresa | BCB, IF.data | Relação banco-empresa |
| Crédito por setor e UF, 43 milhões de linhas | BCB, SCR.data | Contexto setorial (agregado, não por empresa) |
| Base própria de M&A: negócios, partes, assessorias, datas, múltiplos | Própria | Comparáveis |
| Energia, combustíveis, transporte: CCEE, ONS, ANEEL, ANP, ANTT | Agências | Setores regulados com dado por empresa |
| Focus e curva de juros como eram na data | BCB | Taxa de desconto na data do negócio |

**Falta e é aberto por CNPJ (ordem sugerida de coleta)**

| Prioridade | Dado | Fonte | Por que para M&A |
| --- | --- | --- | --- |
| 1 | Atos de concentração | CADE | Negócios anunciados com partes e setor; comparáveis |
| 2 | Operações diretas e indiretas: cliente, valor, finalidade | BNDES | Sinal de investimento e porte |
| 3 | Demonstrações das operadoras de saúde (DIOPS) | ANS | Único balanço por empresa num setor com 97 negócios em 2024 (TTR) |
| 4 | Empresas exportadoras e importadoras por faixa de valor | Comex Stat, MDIC | Proxy de receita |
| 5 | Contratos públicos por fornecedor | PNCP, Compras.gov | Proxy de receita B2G |
| 6 | Demonstrações publicadas por S.A. fechadas | Central de Balanços, SPED | Balanço real quando existe |
| 7 | Seguradoras: balanços | SUSEP | Setor regulado com balanço |
| 8 | Marcas e patentes | INPI | Sinal de produto e marca |
| 9 | Acessos por operadora | ANATEL | Setor regulado com dado operacional |
| 10 | Processos por parte | DataJud (CNJ) e consultas dos tribunais | Diligência; coleta trabalhosa |

**Não existe aberto por CNPJ**

- SCR por empresa: sigilo bancário; só o agregado do SCR.data.
- Faturamento, notas fiscais e DRE de LTDA.
- RAIS identificada (empregados por CNPJ): só por convênio; o CAGED aberto é agregado.
- Contatos de decisores (telefone, e-mail): fora do produto por decisão, não por falta de fonte.

## O produto em três camadas

O produto é o cruzamento, não as tabelas. Cada camada é uma tabela derivada na base, exposta pela API e por alertas, e cada linha dela guarda fonte, data em que ficou pública e linhagem até o original, como já é regra do projeto.

| Camada | O que responde | Entradas | Saída |
| --- | --- | --- | --- |
| 1. Grafo de dono | Quem controla o quê, e desde quando | QSA da Receita (pessoas e empresas como sócias), FRE (controladas e coligadas), CDA (carteiras dos fundos), IF.data (vínculo banco-empresa) | Tabela `vinculos` com origem, destino, tipo, percentual quando houver, vigência (de, até); consulta por CNPJ sobe e desce o grupo |
| 2. Linha do tempo por CNPJ | O que aconteceu com esta empresa, em ordem | Receita (capital, sócios, situação), PGFN, insolvência, FIDC, ofertas CVM, BNDES, Comex, PNCP, CADE, CGU, INPI | Tabela `eventos` com CNPJ, data, tipo, fonte, valor quando houver; é o feed de originação e de alertas |
| 3. Comparáveis | Quanto valeu um negócio parecido | Base própria de M&A (múltiplos), CADE, fatos relevantes da CVM, ANS e SUSEP (balanços de setores regulados) | Consulta por CNAE, porte e período que devolve negócios, múltiplos e as fontes de cada um |

**A pergunta que o cliente faz** e que nenhuma ferramenta atual responde de uma vez: "empresas do CNAE X, no estado Y, com mais de 10 anos, capital acima de Z, que trocaram sócio ou aumentaram capital nos últimos 12 meses, sem dívida na PGFN e fora de RJ". A busca de alvos é essa consulta sobre as camadas 1 e 2; o monitoramento é a mesma consulta rodando sobre uma lista de CNPJs e avisando quando algo entra na linha do tempo.

**Ficha por CNPJ** (para a Ficha Clara e para a API): cadastro atual, o grupo (camada 1), a linha do tempo (camada 2), comparáveis do setor (camada 3) e, para empresa de setor regulado ou S.A. fechada, o balanço publicado. Tudo com parâmetro `como_era_em`, que é o que diferencia o produto.

## Plano de trabalho para o Claude Code

Quatro fases, cada uma fechada em PRs pequenos com testes, no padrão do repositório (`CLAUDE.md`, `docs/padroes-de-codigo.md`, texto em português, nada usa informação do futuro). Os caminhos abaixo vêm do README e de conversas anteriores; confirmar no repositório antes de editar.

1. **Liberar a base inteira (primeira semana).**
   - Remover o bloqueio das tabelas de insolvência, PGFN, situação especial do CNPJ e rótulos de atraso: a regra `pode_mostrar` em `base/dossie.py` e qualquer outro filtro no app e na API.
   - Garantir que toda linha exposta carregue fonte, data em que ficou pública e link para o original no acervo; rótulos derivados mostram a regra que os gerou.
   - Página Dados: as 86 tabelas deixam de ser só catálogo e passam a ter consulta e exportação.
   - Atualizar `docs/dicionario-da-base.md`, `docs/CHANGELOG-da-base.md` e os contratos em `base/contratos/` (versão semântica conferida no CI).
2. **API v2 por CNPJ (segunda e terceira semanas).**
   - Novas rotas em `src/api_v1/` ou um pacote `src/api_v2/`: `GET /v2/cnpj/{cnpj}/ficha`, `/eventos`, `/vinculos`, `/comparaveis`, `/tabelas/{nome}` (bruta, paginada). Todas aceitam `como_era_em=AAAA-MM-DD`.
   - Autenticação por chave de API por cliente, além do token do Google da v1; limite por minuto e cota por plano em `src/planos.py`, cobrada por consulta ou por volume.
   - A v1 continua como está: ela entrega números calculados para o app; a v2 entrega dados.
   - Primeiro cliente da v2: a Ficha Clara. Publicar `docs/api/openapi-v2.json` e um exemplo de uso.
3. **Fontes novas (em paralelo, uma por PR, na ordem do inventário).**
   - Cada fonte entra pelo arquivista (`base/arquivo/fontes.py`): original no acervo com SHA-256, manifesto, ponto no tempo, contrato no catálogo, regras de qualidade que apontam e nunca corrigem.
   - Ordem: CADE, BNDES, ANS, Comex Stat, PNCP, Central de Balanços, SUSEP, INPI, ANATEL, DataJud.
   - Toda fonte precisa de chave de junção por CNPJ. Fontes que trazem só nome (CADE, fatos relevantes, notícias) passam por uma tabela de resolução nome → CNPJ, com a confiança da junção gravada.
4. **As três camadas e o monitoramento (quarta semana em diante).**
   - Tabelas derivadas `vinculos` e `eventos` em `base/`, com linhagem até as tabelas de entrada e testes de ponto no tempo (cortar o futuro não muda o passado).
   - Consulta de comparáveis sobre a base própria de M&A, CADE e fatos relevantes.
   - Busca de alvos e listas monitoradas: uma tela só, que roda a consulta da seção "O produto" e manda alerta (e-mail com opt-in, como a newsletter) quando a linha do tempo de um CNPJ muda.
   - Medir: tempo de resposta da ficha por CNPJ, cobertura das junções por CNPJ, e quantas empresas do CNAE do primeiro cliente têm ao menos um evento nos últimos 12 meses.

## Decisões fechadas e o que não fazer

Estas decisões já foram tomadas pelo autor; o Claude Code não as reabre, só executa.

- Não esperar parecer jurídico para liberar tabelas.
- Não construir prospecção comercial: nada de telefone, e-mail ou contato de decisor. O produto é inteligência sobre a empresa, não lista para SDR.
- Não remover nem despriorizar o research de empresas abertas; as listadas são as compradoras.
- Não inventar dado: fonte que não existe aberta por CNPJ (SCR individual, faturamento, RAIS identificada) não entra por estimativa. Proxy é rotulado como proxy.
- Não corrigir dado em silêncio: as regras de qualidade apontam e nunca consertam, como já é hoje.
- Não criar telas novas antes da API v2 e das tabelas derivadas; a tela de busca de alvos e monitoramento é a única nova nesta fase.
- Manter os princípios do projeto: nada usa informação do futuro, toda linha tem origem, resultado negativo também conta.

## Perguntas em aberto para o autor

Respostas que o Claude Code deve pedir antes de começar a fase correspondente.

- [ ] Qual boutique é o primeiro cliente, e quais são as cinco consultas que o analista dela faz toda semana hoje no braço? (define a busca de alvos e os alertas)
- [ ] Quais fontes a pesquisa no ChatGPT de 4/11 listou? Cruzar com o inventário acima e marcar: já tem / falta / não existe.
- [ ] Preço da API v2: por consulta, por CNPJ monitorado ou por cota mensal? (define `src/planos.py`)
- [ ] A Ficha Clara chama a v2 com chave própria ou com o login do usuário final? (define a autenticação)
- [ ] A base completa da Receita (todas as versões mensais) já está carregada, ou só o cadastro atual? (define se o histórico de sócios e capital já existe)
- [ ] A resolução nome → CNPJ pode usar um modelo (rotulagem por IA já existe em `rotulos_ia.py`) ou só regras? (define a camada 2 para CADE e fatos relevantes)

## Como usar este documento no Claude Code

Exporte este doc em Markdown, salve como `docs/virada-empresas-fechadas.md` na raiz do repositório `tbc174/tickerlab` e abra o Claude Code com o prompt abaixo.

```markdown
Leia docs/virada-empresas-fechadas.md inteiro antes de qualquer coisa. Ele registra uma decisão de produto tomada em 5/11/2026 e um plano em quatro fases.

Tarefa desta sessão: fase 1 (liberar a base inteira).

1. Confirme no código onde as tabelas de insolvência, PGFN, situação especial do CNPJ e rótulos de atraso são barradas (comece por `pode_mostrar` em base/dossie.py) e liste todos os pontos antes de mudar.
2. Proponha os PRs da fase 1, um por mudança, com os testes de cada um. Espere minha aprovação da lista antes de abrir o primeiro.
3. Siga CLAUDE.md e docs/padroes-de-codigo.md. Texto, nomes e commits em português. Nada usa informação do futuro.
4. As decisões da seção "Decisões fechadas e o que não fazer" não se discutem. As da seção "Perguntas em aberto" você me pergunta quando a fase precisar delas.

Ao terminar a fase 1, atualize a seção "Plano de trabalho" do próprio documento com o que foi feito e o que ficou, e me diga em uma linha o próximo passo da fase 2.
```

Para as fases seguintes, troque a linha "Tarefa desta sessão" e mantenha o resto.

## Referências

Fontes consultadas no debate de 5/11/2026, para o Claude Code conferir ou aprofundar.

- [5 Best B2B Databases for Brazil in 2026 (syncgtm.com)](https://syncgtm.com/blog/best-b2b-database-brazil): Econodata e Speedio como plataformas nativas de CNPJ.
- [Speedio no Deepline](https://deepline.com/gtm-stack/providers/speedio): 40 milhões de CNPJs e 117 fontes.
- [Avaliações da Econodata, B2B Stack](https://www.b2bstack.com.br/product/econodata/avaliacoes?page=16): reclamação de imprecisão dos dados.
- [Avaliações da Econodata, pedido de dívidas](https://www.b2bstack.com.br/product/econodata/avaliacoes?page=72): usuário pede que a ferramenta mostre as dívidas das empresas.
- [Comparativo Neoway x Econodata, B2B Stack](https://www.b2bstack.com.br/compare/neoway-vs-econodata): preços e perfis dos concorrentes de prospecção.
- [TTR Data](https://ttrdata.com): cobertura de M&A, PE, VC e mercado de capitais na América Latina.
- [TTR: demonstrações financeiras de empresas brasileiras](https://blog.ttrdata.com/category/what-is-new/): adicional pago com balanços de fontes oficiais.
- [TTR Data, Brazil Healthcare Sector Report](https://www.ttrdata.com/es/publicaciones/informe-por-mercado/informe-mensual-brasil/Brazil-Healthcare-Sector-Report/2307): 97 operações de M&A em saúde em 2024.
- [TTR LatAm, relatório do 2º trimestre de 2026 (Datasite)](https://www.datasite.com/pt/resources%2Finsights%2Fttr-latam-q2-2026-report): compradores pedem clareza sobre riscos e qualidade da informação.
- [InvestNews: OverA e o mid-market de M&A](https://investnews.com.br/?p=825322): calculadora de valuation como fonte de originação.
- [PGFN: Dívida Aberta e dados abertos](https://www.contadores.cnt.br/projetos/59/noticias/empresariais/2020/01/30/pgfn-lanca-aplicativo-para-dispositivos-moveis-com-foco-na-transparencia-publica-e-no-consumo-consciente.html): base completa da dívida ativa publicada a cada trimestre.
- [Consultar Lista de Devedores da PGFN (gov.br)](https://www.gov.br/pt-br/servicos/consultar-lista-de-devedores-da-pgfn): consulta por CNPJ, por setor e exportação.
