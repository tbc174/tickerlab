# Censo Escolar do INEP: escolas privadas (2022–2025)

Coleta manual na máquina de casa. Não há tarefa agendada nova, download no CI ou
carga feita como parte da implementação. O teste usa ZIPs pequenos inventados.

```powershell
.venv\Scripts\python -m scripts.carga_censo_escolar --ano 2022 --ano 2023 --ano 2024 --ano 2025
# Para outro diretório de base:
.venv\Scripts\python -m scripts.carga_censo_escolar --ano 2025 --pasta D:/acervo/base
```

O comando exige um commit conhecido, confere o freio de disco do arquivista e
baixa uma edição por vez, com o cliente HTTP do acervo. O destino padrão é
`<TICKERLAB_ACERVO>/base/inep_censo_escolar/<ano>.parquet`. O manifesto `.json`
registra URL, SHA-256 real do ZIP, hash da tabela, versão do código e marca de
licença. Recoleta idêntica preserva datas; mudança preserva o Parquet anterior
em `.vN`. O ZIP fica em pasta temporária e é removido mesmo em falha: contém
colunas fora do recorte permitido. O acervo guarda somente o resultado filtrado;
a reprodução dos bytes originais depende de o INEP ainda oferecer a mesma versão.

## Fonte e integridade

- [Microdados oficiais do Censo Escolar](https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar).
- ZIPs: `https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_2022.zip`,
  com o ano trocado para 2023 e 2024; em 2025 o nome é
  `microdados_censo_escolar_2025_.zip` (sublinhado final, edição v2).
- 2022 e 2023 têm cerca de 25 e 31 MB; 2024, 32 MB; 2025 v2, 512 MB.
- O arquivo `md5_microdados_ed_basica_<ano>.txt` **dentro do ZIP** publica o MD5
  de cada CSV, não do ZIP inteiro. A carga confere os bytes dos CSVs utilizados
  antes de interpretá-los. Manifesto ausente, ambíguo ou divergente impede a carga.
  O MD5 é uma conferência de integridade; não é uma assinatura independente.
- Até 2024, lê `microdados_ed_basica_<ano>.csv`. Em 2025 v2, lê somente
  `Tabela_Escola_2025_V2.csv` e `Tabela_Matricula_2025_V2.csv`, ligados por
  `(NU_ANO_CENSO, CO_ENTIDADE)`. Turma, Docente, Gestor e Curso Técnico ficam fechadas.
  Diferenças de maiúsculas no nome dos membros/manifesto são aceitas.

## Lista completa de colunas lidas

A lista fechada está em `base/inep_censo_escolar.py::CADASTRO` e `MATRICULAS`;
o leitor passa `usecols` ao pandas, em blocos de 20 mil linhas.

| Grupo | Colunas originais |
|---|---|
| Chaves | `CO_ENTIDADE`, `NU_ANO_CENSO` |
| Cadastro | `TP_DEPENDENCIA`, `TP_SITUACAO_FUNCIONAMENTO`, `NU_CNPJ_ESCOLA_PRIVADA`, `NU_CNPJ_MANTENEDORA`, `SG_UF`, `CO_MUNICIPIO`, `NO_MUNICIPIO` |
| Matrículas | `QT_MAT_BAS`, `QT_MAT_INF`, `QT_MAT_INF_CRE`, `QT_MAT_INF_PRE`, `QT_MAT_FUND`, `QT_MAT_FUND_AI`, `QT_MAT_FUND_AF`, `QT_MAT_MED`, `QT_MAT_PROF`, `QT_MAT_PROF_TEC`, `QT_MAT_EJA`, `QT_MAT_ESP` |
| Tempo integral | `QT_MAT_BAS_INT`, `QT_MAT_INF_INT`, `QT_MAT_INF_CRE_INT`, `QT_MAT_INF_PRE_INT`, `QT_MAT_FUND_INT`, `QT_MAT_FUND_AI_INT`, `QT_MAT_FUND_AF_INT`, `QT_MAT_MED_INT` |

Só dependência 4 (privada), com pelo menos um dos dois CNPJs válido. Cada CNPJ é
validado separadamente: exatamente 14 dígitos ASCII e DV correto, sem completar
zeros, limpar pontuação nem aceitar decimal. Vazio, zeros, sentinela de não
declaração, DV inválido e documento pessoal completado com zeros viram nulo;
sem nenhum CNPJ válido a linha sai. Não há
nome de escola, gestor, telefone, e-mail, endereço, coordenada ou dado individual.
A situação de funcionamento é preservada, inclusive paralisada/extinta.

As contagens são as publicadas: educação especial e profissional podem estar
incluídas em outros totais; não somar os recortes. Coluna de tempo integral não
publicada naquela edição fica nula, nunca zero nem estimativa (o total integral
`QT_MAT_BAS_INT` foi acrescentado em 2025). Chave duplicada, ano incompatível,
contagem inválida ou escola privada sem linha de matrículas em 2025 impedem a carga.

## Datas e atribuição

Cada linha leva `fonte = "INEP / Censo Escolar da Educação Básica"`, `ano_censo`
e `data_edicao` (última quarta-feira de maio). Essa é a data de referência, não a
data de publicação. `disponivel_em` é o dia em que este conteúdo foi coletado;
não se usa o ano histórico como disponibilidade. `origem_coletada_em`,
`origem_sha256`, `montado_em` e `versao_do_codigo` permitem identificar a carga.
Os Parquets vigentes e as versões `.vN` ficam no acervo interno.
O contrato deixa `historico_desde` não informado (`""`, valor padrão do
dicionário) até a primeira carga real; nessa ocasião, deve receber o dia da
primeira coleta, nunca a referência de 2022.

**Recorte interno até classificar EI/MEI:** CNPJ com DV válido não prova que o
titular é uma sociedade. A escola ou a mantenedora pode ser empresário individual
ou MEI. Como esta carga não cruza os dois documentos com a Receita, o contrato
marca a tabela inteira como `pessoa: true`, e ela fica em `FORA_DA_PORTA` e no
inventário `FORA_DA_CONSULTA_SEM_A_MARCA`. Não existe view consultável, nem saída
pela consulta aberta ou pela API de organizações. `TABELAS_SO_INTERNAS` também
impede o anúncio no catálogo do site, mesmo depois de montada. Uma carga futura deve marcar
as linhas dos dois lados, incluindo desconhecidos, antes de habilitar a porta.

O [conjunto oficial do INEP no dados.gov.br](https://dados.gov.br/dados/conjuntos-dados/microdados-publicos-do-censo-escolar-da-educacao-basica)
tem CC BY segundo o levantamento da fonte de 27/11/2026, baseado na leitura
registrada em 28/10/2026 em `licencas-por-fonte.md`. O rodapé genérico do portal
INEP é CC BY-ND. Esta coleta preserva a classificação vigente da família `inep`
da ADR 0122; não altera licença, marca nem permissões de saída. O Catálogo de
Escolas e cruzamentos por nome/endereço estão fora desta coleta.
