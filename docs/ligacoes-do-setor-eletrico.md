# Ligações da B13 no setor elétrico: vigência, controle e dono do momento

Decisão de 28/10/2026 (mesa Dados, linha 168 da fila). Vale para a tabela `empresa_serie` (B13) e para quem a lê:
a seção `setor_regulado` do dossiê da empresa e a seção `setor` do relatório do setor (`base/dossie.py`).

## O problema

A B13 liga cada entidade do regulador (na ANEEL, a distribuidora) à companhia aberta que a tem como controlada,
coligada ou participação no FRE da CVM. Só havia o dia da primeira entrega que mostrou a ligação (`desde`) e a
referência da mais nova (`ultima_referencia`); nada dizia que a ligação **acabou**. E a ligação "principal" de cada
entidade era a do FRE mais recente, sem olhar se era controle. Nos dossiês de 21/10 isso deu:

| Caso | O que a base mostrava | O que aconteceu |
|---|---|---|
| Eletropaulo | AES ELPA como dona, desde 2011 | a AES ELPA parou de entregar o FRE em 2017; a Enel assumiu o controle em 04/06/2018 (anuência da ANEEL em 26/06/2018) |
| Roraima Energia | Axia (ex-Eletrobras) como dona | vendida no leilão de 30/08/2018, anuência da ANEEL em out/2018 |
| Coelce | Axia, com 6,41% (sem tipo) | controlada pela Enel (74% do capital); a Eletrobras tinha cerca de 7% |
| Bragantina | Axia, com 0,11% (coligada) | o FRE de 2017 da controladora (Rede) mostra 95,85%; o 0,11% mais novo ganhava só por ser mais recente |
| CEB | série da ANEEL só até 2005 | a distribuição passou à CEB-D, que o leilão de dez/2020 levou à Neoenergia (concluído por volta de mar/2021) |
| Energisa e Rede | duas companhias separadas | o mesmo grupo econômico desde 2014, mas o FRE da Energisa mostra a Rede com só 0,147548% diretos |

## O que mudou no código

1. **Vigência na B13** (`base/empresa_serie.py`, contrato 1.1.0). Colunas novas, pela mesma convenção da tabela `rede`:
   - `ate`: 1ª referência do FRE da própria companhia que já não mostra a ligação;
   - `ate_publico_em`: o dia em que essa entrega ficou pública (sem olhar o futuro: antes dele não se sabia do fim);
   - `vigente`: a ligação aparece no FRE mais novo da companhia. Falso quando acabou **ou** quando a companhia parou
     de entregar o FRE há mais de um ano (caso da AES ELPA: não há "entrega sem a ligação", mas a última evidência é de 2016).
     A própria companhia é sempre vigente.
2. **Vínculo principal**: uma ligação que acabou perde para a que ainda vale, e na ANEEL só controle (a própria,
   `controlada`, ou mais de 50%) pode ser a principal: participação minoritária não atribui o mercado a ninguém
   (a ANEEL mede por concessionária; a Eletrobras ter 0,11% da Bragantina não a torna dona dela). As outras fontes
   (Anatel, ANS, Pix, SUSEP, ONS, ANTT, ANAC) continuam como eram: seguem na fila.
3. **Quem a participação conta, ano a ano** (`_ultimo_ano_da_ligacao` em `base/dossie.py`): a entidade soma para a companhia
   até o ano da última entrega do FRE que mostrou a ligação, se ela acabou (**o dono do momento, não o dono de hoje**).
   Depois disso ela deixa de somar na companhia antiga; no relatório do setor passa a ser uma entidade solta, e o aviso
   "contada por entidade" já diz que a concentração real é maior ou igual à mostrada. As `entidades_ligadas` do dossiê
   trazem `ate`, `ate_publico_em` e `vigente`.

O **começo** da ligação não foi limitado: a estrutura que o FRE mostra vale também nos anos anteriores à 1ª entrega, como
antes (a base não tem a data em que a controlada entrou no grupo, só a da 1ª entrega que a citou). Anos antes do FRE
ficam, portanto, com a estrutura de quando ele a mostrou.

## O que fica de fora (e por quê)

- **Energisa × Rede**: somar os dois grupos exige o encadeamento Energisa → Rede (controle desde 2014, segundo os
  documentos da própria Energisa), que o FRE não traz como linha direta. Pôr isso numa tabela conferida à mão pede fonte
  e data por linha; fica como item da fila. Até lá a participação da Energisa não inclui a da Rede, e a da Rede aparece à
  parte (subestima a escala do grupo, nunca a superestima).
- **CEB → CEB-D**: a série da ANEEL muda de CNPJ quando a concessão passa à sucessora; a B13 liga por CNPJ e não segue
  sucessão. Tratar sucessão de concessionária também fica na fila.
- Fontes além da ANEEL: a regra de controle e a vigência valem para todas, mas só a ANEEL exige controle para ser principal.

## Fontes e datas (consultadas em 28/10/2026)

- CVM, FRE `controladas` (participações), entregas até 01/10/2026, na cópia local do acervo.
- ANEEL, SAMP (consumidores por distribuidora), carga mais recente da base.
- Fatos sobre as vendas (datas de controle e leilões): comunicados e notícias de imprensa sobre a Enel/Eletropaulo
  (2018), o leilão da Roraima Energia (2018), a venda da CEB-D à Neoenergia (2020/21), a Coelce (relatórios de resultado
  da Enel, 2010 a 2015, e imprensa) e as apresentações da Energisa sobre a Rede (2014). São o motivo do tratamento acima;
  o que a tabela grava vem só do FRE, e cada linha da B13 mostra a referência e o dia de entrega da CVM.
- Não achado: nenhuma fonte pública consultada confirma a data exata em que a Bragantina saiu da Rede; o tratamento
  dela vem do que o FRE mostra (controle de 95,85% em 2017, sem entrega mais nova da controladora que a cite).

## Como desfazer

Reverter o PR desta decisão: as colunas novas somem da B13 na próxima montagem e o dossiê volta a contar a estrutura
de hoje em todos os anos. Nenhuma migração de banco; só a tabela da B13 é refeita (`scripts/montar_base_historica.py`).
