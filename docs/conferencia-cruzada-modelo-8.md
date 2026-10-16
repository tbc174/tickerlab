# Conferência cruzada das fontes do modelo 8 (ADR 0027, exigência 6)

Critério de pronto do modelo 8 (atraso na entrega da DFP/ITR), PR C do placar. **Esta seção foi escrita e
gravada no Git antes de qualquer comparação** (16/10/2026): as tolerâncias e o que conta como divergência não
podem mudar depois de ver o resultado. Toda divergência precisa de explicação escrita; divergência sem explicação
reprova a fonte e vira correção (ou pendência) antes do pré-registro.

Nenhuma conferência cruza dado com o alvo (ADR 0027, item 2): cada uma compara **a mesma informação em duas
fontes**. O rótulo só é conferido contra o ENET.

## Tolerâncias (escritas antes de olhar)

| # | O que se compara | Amostra | Tolerância | Conta como divergência |
|---|---|---|---|---|
| 1 | Contas da base "como era" (`demonstracoes`, `como_era_em`) × o documento da DFP/ITR no ENET (Empresas.NET) | ~10 empresas × 3 datas de corte, sorteadas com semente; pelo menos uma com reapresentação (antes e depois dela) e uma cancelada | **até 1 unidade da escala do documento** (R$ 1 mil quando o documento está em milhares), por arredondamento; **mesma versão** do documento | valor diferente além disso; a base mostrar, numa data, uma versão que ainda não era pública (ou deixar de mostrar a que já era) |
| | Contas: ativo total (`1`), caixa e equivalentes (`1.01.01`), empréstimos e financiamentos de curto prazo (`2.01.04`), patrimônio líquido (`2.03`), lucro ou prejuízo do período (`3.11`); consolidado quando houver | | | |
| 2 | Auditor vigente na tabela `auditores` na data da entrega da DFP × a firma que assina o parecer (relatório do auditor) da mesma DFP no ENET | ~20 DFPs sorteadas | nome da firma igual depois de normalizar (rede das grandes, sem "Ltda", "S/S", "Auditores Independentes") | outra firma, sem troca de auditor registrada entre o FCA e o parecer |
| 3 | Recuperação judicial, falência e liquidação no IPE (`insolvencia`) × situação especial do CNPJ na Receita (`cnpj_situacao_especial`) | todas as companhias com registro na CVM que aparecem em qualquer uma das duas | **≥ 90% de concordância em cada sentido** (Receita → IPE e IPE → Receita, entre as que a Receita ainda marca); o tipo (RJ, falência, liquidação) igual | companhia num lado e não no outro, ou com tipo diferente |
| 4 | Registro e cancelamento do cadastro (`cad_cia_aberta.csv`) × a página da companhia no sistema da CVM | ~20 companhias sorteadas (metade canceladas) | **0 dia** nas datas de registro e de cancelamento; mesma situação | qualquer data diferente |
| 5 | Prorrogações de prazo de 2022 a 2026 em `src/prazos.py` × as normas da CVM e as próprias entregas | todas as normas encontradas; todas as data-bases de 2022 a 2026 | nenhuma norma de prorrogação fora de `src/prazos.py`; nas entregas, nenhuma data-base com a fração de entregas de 1 a 15 dias depois do prazo **acima de 3 vezes** a mediana das data-bases do mesmo documento | norma achada e não codificada; data-base acima do limite sem explicação |
| 6 | Rótulo (`rotulos_atraso`) × "Data do Envio" no ENET | 30 casos (15 atrasados, 5 da zona cinzenta, 10 no prazo; semente 20261015) e 300 entregas da conferência de 15/10 | **0 dia** na data da primeira entrega; **0** rótulo diferente | data ou rótulo diferente fora do grupo do pedido de registro (que saiu dos exemplos no #288 e no PR B) |

## Resultados

(preenchidos depois, abaixo desta linha, sem mudar a tabela acima)

Medidos em 16/10/2026, só leitura (servidor de casa e páginas públicas da CVM, um pedido por segundo). Cada
conferência é uma tabela em `base/conferidas/modelo_8/` e um teste em `tests/test_conferencia_cruzada_modelo_8.py`.
Das páginas só foram guardados números, datas, códigos e nomes de firmas de auditoria: nenhum nome de pessoa.

| # | Resultado | Passa? |
|---|---|---|
| 1 | **142 de 146** contas iguais (10 empresas, 29 documentos, 5 contas; sementes 20261019). As 3 de `2.01.04` que não batem: o documento deixa a linha **em branco** e os dados abertos da CVM trazem **0** (o dicionário foi corrigido). A versão mostrada é sempre a pública na data; na reapresentação do mesmo dia, a base mostra a versão 2 a partir do próprio dia (regra "vale a partir do dia; quem decide no dia olha a véspera"). O caso vazio (Porto Saúde, ITR de 31/03/2024) é um documento do pedido de registro: vale a partir do registro (#288) | sim (divergências explicadas) |
| 2 | **19 de 20** relatórios assinados pela firma que a tabela dava como vigente (numa auditoria em transição, o FCA tinha EY e KPMG e assinou a EY). O 20º (Magnesita Mineração, DFP 2016) não tem auditor na tabela: o primeiro FCA da companhia só traz o de 2017 em diante. Falta de informação, não auditor errado (sementes 20261021) | sim |
| 3 | Receita → IPE: **45 de 59 (76%)**; IPE → Receita: **24 de 44 (55%)**. A recuperação judicial bate **25 de 25** da Receita para o IPE. As divergências: 12 massas falidas que pararam de entregar à CVM antes da falência; 2 liquidações que o leitor do IPE não marcou; 2 eventos de **outra** empresa marcados na companhia (Vale/Samarco, V.tal/Oi); recuperações extrajudiciais juntadas com a judicial; recuperações encerradas; CNPJ de filial no IPE; e a Receita sem a marca em casos conhecidos (a Americanas só aparece em outro estabelecimento) | **não** (abaixo de 90%): fica pendente |
| 4 | **20 de 20** iguais à consulta pública de companhias da CVM (registro das 10 ativas, cancelamento das 10 canceladas; a Panex, com dois registros, bate nos dois; semente 20261020) | sim |
| 5 | Normas: só a **Resolução CVM 202/2024** em 2022–2026 (duas buscas e a lista de resoluções da CVM, 16/10), já no código. Entregas: 9 de 54 data-bases acima de 3 vezes a mediana, todas explicadas: 5 com menos de 100 empresas (exercício fora de dezembro), as 5 DFPs de dezembro porque a mediana da regra é 0 (contra as data-bases grandes, 0,7 a 1,6 vez; **a regra escrita antes era degenerada para a DFP**, registrado aqui sem trocá-la) e o ITR de 30/06/2023 (3,0 vezes: 21 entregas no dia útil seguinte ao prazo, ao longo do dia; volume normal no dia do prazo) | sim (divergências explicadas) |
| 6 | Rótulo remontado com o PR B: **30 de 30** com o mesmo rótulo e a mesma data; das 301 entregas de 15/10, **298 de 298** iguais fora do grupo do pedido de registro (que já saiu dos exemplos) | sim |

**O que fica para decidir (IPE):** a proposta é o modelo 8 usar do IPE **só a recuperação judicial da própria
companhia**, com três correções no PR 3 do plano: juntar pelo CNPJ raiz (filial), não marcar a companhia por
evento de outra empresa do grupo e separar a recuperação extrajudicial. Quantidade de fatos relevantes fica de
fora até lá, e empresa sem nenhum documento no IPE fica com a coluna vazia, não 0 (achado do PR B).
