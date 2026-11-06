# Lote de medição do leitor de fatos relevantes (v1)

`lote_medicao_v1.csv`: 200 fatos relevantes de companhias abertas, entregues à CVM de 2003 a
31/03/2026, sorteados com semente fixa (8 por ano, 4 do 1º trimestre de 2026 e o resto para que cada
assunto provável tenha pelo menos 6). Serve para medir o leitor v2 (`src/topicos.py`): a leitura diária
baixa o texto deles aos poucos (`python -m scripts.atualizar_leituras_cvm --lote
base/leitor/lote_medicao_v1.csv`) e os rótulos humanos, feitos às cegas, dizem quanto o leitor acerta.

O que vem depois de 31/03/2026 fica de fora: é o período lacrado para a prova final dos modelos.

**Fonte:** índices anuais do IPE (Informações Periódicas e Eventuais) da CVM, dados abertos
(`dados.cvm.gov.br`), licença ODbL. Colunas e textos como a CVM publica; o link de cada linha é o
documento original no sistema da CVM.
