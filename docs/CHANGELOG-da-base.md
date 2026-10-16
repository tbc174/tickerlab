# Mudanças no contrato da base

Gerado por `python -m base.contrato` (não edite à mão). Compara o dicionário com o contrato
congelado de cada tabela (`base/contratos/v<maior>/`). Versão maior: coluna que some ou
muda de unidade ou de chave; menor: coluna nova; correção: dado.

- `valores_mobiliarios`: 1.0.0 → 1.2.0
  - colunas novas: `origem`
- `painel_dos_fundos`: 1.0.0 → 1.1.0
  - colunas novas: `fundos_no_bloco_8`, `quantidade_no_bloco_8`, `valor_no_bloco_8`
- `buracos_dos_fundos`: 1.0.0 → 1.1.0
  - colunas novas: `motivo`
- `amostra_painel`: 1.0.0 → 1.1.0
  - colunas novas: `acumulado_fim`, `acumulado_grupo`, `acumulado_inicio`, `acumulado_publico_em`, `anual_fim`, `anual_grupo`, `anual_publico_em`, `ativo_total`, `auditor_id`, `auditor_publico_em`, `balanco_fim`, `balanco_grupo`, `balanco_publico_em`, `caixa`, `compras_administracao_90d`, `compras_controlador_90d`, `conselho_fiscal_membros`, `conselho_independentes`, `conselho_membros`, `divida_bruta`, `documentos_eventos_90d`, `documentos_proventos_90d`, `documentos_resultados_90d`, `documentos_risco_90d`, `ebit_acumulado`, `ebit_anual`, `fatos_relevantes_90d`, `fre_publico_em`, `insolvencia_conhecida`, `insolvencia_desde`, `insolvencia_rotulo`, `lucro_acumulado`, `lucro_anual`, `meses_desde_a_troca_de_auditor`, `ofertas_12m`, `patrimonio_liquido`, `receita_acumulado`, `receita_anual`, `remuneracao_diretoria`, `remuneracao_exercicio`, `vendas_administracao_90d`, `vendas_controlador_90d`
