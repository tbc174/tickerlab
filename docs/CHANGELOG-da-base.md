# Mudanças no contrato da base

Gerado por `python -m base.contrato` (não edite à mão). Compara o dicionário com o contrato
congelado de cada tabela (`base/contratos/v<maior>/`). Versão maior: coluna que some ou
muda de unidade ou de chave; menor: coluna nova; correção: dado.

- `valores_mobiliarios`: 1.0.0 → 1.1.0
  - colunas novas: `origem`
- `carteiras_dos_fundos`: 1.0.0 → 1.1.0
  - colunas novas: `visto_em`
- `carteiras_bloco_8`: 1.0.0 → 1.1.0
  - colunas novas: `visto_em`
- `fidc_informe`: 1.0.0 → 1.1.0
  - colunas novas: `visto_em`
- `painel_dos_fundos`: 1.0.0 → 1.1.0
  - colunas novas: `fundos_no_bloco_8`, `quantidade_no_bloco_8`, `valor_no_bloco_8`
- `buracos_dos_fundos`: 1.0.0 → 1.1.0
  - colunas novas: `motivo`
- `amostra_painel`: 1.0.0 → 1.1.0
  - colunas novas: `acumulado_fim`, `acumulado_grupo`, `acumulado_inicio`, `acumulado_publico_em`, `anual_fim`, `anual_grupo`, `anual_publico_em`, `ativo_total`, `balanco_fim`, `balanco_grupo`, `balanco_publico_em`, `caixa`, `divida_bruta`, `ebit_acumulado`, `ebit_anual`, `lucro_acumulado`, `lucro_anual`, `patrimonio_liquido`, `receita_acumulado`, `receita_anual`
- `scr_credito`: 1.0.0 → 1.1.0
- `ligacoes`: 1.0.0 → 1.1.0
  - colunas novas: `ate_publico_em`
