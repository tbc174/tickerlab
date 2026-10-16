# Mudanças no contrato da base

Gerado por `python -m base.contrato` (não edite à mão). Compara o dicionário com o contrato
congelado de cada tabela (`base/contratos/v<maior>/`). Versão maior: coluna que some ou
muda de unidade ou de chave; menor: coluna nova; correção: dado.

- `valores_mobiliarios`: 1.0.0 → 1.3.0
  - colunas novas: `origem`
- `painel_dos_fundos`: 1.0.0 → 1.1.0
  - colunas novas: `fundos_no_bloco_8`, `quantidade_no_bloco_8`, `valor_no_bloco_8`
- `buracos_dos_fundos`: 1.0.0 → 1.1.0
  - colunas novas: `motivo`
- `amostra_painel`: 1.0.0 → 1.1.0
  - colunas novas: `acessos_anatel`, `acessos_anatel_12m_antes`, `acessos_anatel_competencia`, `acumulado_fim`, `acumulado_grupo`, `acumulado_inicio`, `acumulado_publico_em`, `anual_fim`, `anual_grupo`, `anual_publico_em`, `ativo_total`, `auditor_id`, `auditor_publico_em`, `balanco_fim`, `balanco_grupo`, `balanco_publico_em`, `beneficiarios_ans`, `beneficiarios_ans_12m_antes`, `beneficiarios_ans_competencia`, `caixa`, `compras_administracao_90d`, `compras_controlador_90d`, `conselho_fiscal_membros`, `conselho_independentes`, `conselho_membros`, `consumidores_samp`, `consumidores_samp_12m_antes`, `consumidores_samp_competencia`, `divida_bruta`, `documentos_eventos_90d`, `documentos_proventos_90d`, `documentos_resultados_90d`, `documentos_risco_90d`, `ebit_acumulado`, `ebit_anual`, `fatos_relevantes_90d`, `fre_publico_em`, `fundos_com_a_acao`, `fundos_competencia`, `fundos_no_bloco_8`, `fundos_publico_em`, `fundos_valor`, `fundos_valor_no_bloco_8`, `insolvencia_conhecida`, `insolvencia_desde`, `insolvencia_rotulo`, `juros_data_base`, `juros_nominal_1a`, `juros_nominal_5a`, `juros_real_5a`, `lucro_acumulado`, `lucro_anual`, `meses_desde_a_troca_de_auditor`, `ofertas_12m`, `passageiros_anac`, `passageiros_anac_12m_antes`, `passageiros_anac_competencia`, `patrimonio_liquido`, `premios_susep`, `premios_susep_12m_antes`, `premios_susep_competencia`, `receita_acumulado`, `receita_anual`, `remuneracao_diretoria`, `remuneracao_exercicio`, `vendas_administracao_90d`, `vendas_anp`, `vendas_anp_12m_antes`, `vendas_anp_competencia`, `vendas_controlador_90d`
