# Notas da dívida: trechos reais para o gabarito da B-21

Trechos das notas explicativas das DFPs de 31/12/2025, entregues no ENET da CVM. Baixados em 21/10/2026
com o "pode" do Tiago. São o texto como saiu do PDF, sem correção: a quebra de linha, o "−" e o erro da
própria nota ficam como estão. Cada arquivo traz só a frase da escala (o cabeçalho da página) e a tabela
de vencimentos. Os números esperados estão digitados à mão em `tests/test_divida_nota_dfp_gabarito.py`.

| Arquivo | Empresa | Documento no ENET (NumeroSequencialDocumento) | Recebido pela CVM | Arquivo da nota no pacote | Como saiu o texto |
|---|---|---|---|---|---|
| `cpfl-2025-ocr.txt` | CPFL Energia | 155108 | 05/03/2026 | DF25 CPFL Energia 03.03 (p. 49 e 52) | OCR (rapidocr, `src.leitura`): a tabela é imagem no PDF. A linha da escala veio da camada de texto da mesma nota |
| `localiza-2025.txt` | Localiza | 154953 | 26/02/2026 | 5. Notas explicativas Localiza 4T25 | camada de texto do PDF |
| `petrobras-2025.txt` | Petrobras | 155122 | 05/03/2026 | Notas explicativas (nota 30.4) | camada de texto do PDF |
| `sabesp-2025.txt` | Sabesp | 155830 (versão 2, rearquivamento) | 30/03/2026 | NOTA EXPLICATIVA (v4) | camada de texto do PDF |
| `vale-2025.txt` | Vale | 155313 (versão 2) | 12/03/2026 | Notas explicativas_BRGAAP | camada de texto do PDF |

O pacote está em `http://www.rad.cvm.gov.br/ENETCONSULTA/frmDownloadDocumento.aspx?CodigoInstituicao=1&NumeroSequencialDocumento=<número>`.

## Qual tabela e qual série cada gabarito confere

- **CPFL**: as duas tabelas do principal no não circulante, consolidado: empréstimos (Subtotal 6.488.287)
  e debêntures (Subtotal 17.952.086), em milhares de reais. A "Marcação a mercado" fica fora: ela vem
  depois do Subtotal.
- **Localiza**: a composição por ano de vencimento, coluna consolidado em 31/12/25 (Total 43.595.338),
  em milhares de reais.
- **Petrobras**: a nota 30.4, linha "Total em 31 de dezembro de 2025" (145.489), em milhões de reais. A
  coluna do valor justo, depois do total, fica fora.
- **Sabesp**: o cronograma de liquidação da nota repete o ano 2031 no cabeçalho ("2031" e "2031 até
  2048"), então ele fica **não observado** (é o teste de que o leitor não adivinha). Vale a tabela de
  liquidez da mesma DFP, consolidado, linha "Empréstimos e financiamentos" (40.142.347, o mesmo Total
  Geral do cronograma), em milhares de reais.
- **Vale**: os fluxos de principal, coluna consolidado (Total 98.706), em milhões de reais.
