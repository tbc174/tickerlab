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
