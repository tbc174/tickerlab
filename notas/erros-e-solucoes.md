# Erros e soluções

Todo erro resolvido vira uma entrada aqui. Formato: **sintoma, causa, solução**.

## Terminal abre com `(base)` e Python 3.14 em vez de `(.venv)` e 3.12.10
- **Causa:** o Conda ativa o ambiente `base` automaticamente, antes do `.venv`.
- **Solução:** `Ctrl+Shift+P`, `Python: Select Interpreter`, `.venv`; abrir um terminal novo. Se persistir, `conda deactivate` e `.\.venv\Scripts\Activate.ps1`.
- **Data:** 09/10/2026

## Pylance sublinha `dados.describe` / `dados.columns`: `"describe" is not a known attribute of "None"`
- **Sintoma:** o notebook roda normalmente (`dados.head()` mostra a tabela), mas o VS Code sublinha o uso de `dados` logo depois de `dados = yf.download(...)`.
- **Causa:** é aviso do Pylance (análise estática), não erro de execução. O `yf.download` é declarado como devolvendo `DataFrame | None`; como `dados` *poderia* ser `None`, o editor reclama de acessar atributos nele.
- **Solução:** validar o download logo depois da chamada. Além de calar o aviso, dá uma mensagem clara se o Yahoo falhar:
  ```python
  if dados is None or dados.empty:
      raise ValueError(f"Não consegui baixar dados de {ticker}")
  ```
- **Data:** 10/10/2026

## `streamlit run app.py` não roda: dois comandos na mesma linha
- **Sintoma:** o app não abre; o terminal mostra `SyntaxError: invalid syntax` apontando para a linha do `st.text_input`.
- **Causa:** o código do comentário `# TODO` foi colado **depois** do que eu já tinha escrito, na mesma linha: `ticker = st.text_input(...) st.text_input(...)`. Em Python, cada comando precisa da própria linha (ou de `;`).
- **Solução:** deixar só um `st.text_input` por linha, apagando o duplicado. Ler a mensagem do terminal inteira mostra o número da linha com problema.
- **Data:** 10/10/2026

## Resultado de cálculo dentro de `st.text_input`
- **Sintoma:** campos de texto estranhos aparecendo na tela e `retorno` virando texto, não série.
- **Causa:** usei `st.text_input("Retorno", value=ind.calcular_retorno_diario(fechamento))`. O `st.text_input` cria um **campo de digitação**; não é para guardar contas.
- **Solução:** chamar a função e guardar numa variável: `retorno = ind.calcular_retorno_diario(fechamento)`. Cada função recebe o argumento certo (`retorno` ou `fechamento`).
- **Data:** 10/10/2026

## `streamlit` solto no terminal usa o Conda, não o `.venv`
- **Sintoma:** `which streamlit` aponta para `anaconda3\Scripts`; pode faltar biblioteca ou ser outra versão.
- **Causa:** o Conda `base` vem antes do `.venv` no `PATH` (mesma origem do erro do `(base)`).
- **Solução:** rodar com o Python do ambiente: `python -m streamlit run app.py`, com `(.venv)` no começo do terminal.
- **Data:** 10/10/2026

## `fillna(0)` no retorno diário distorce a volatilidade
- **Sintoma:** a volatilidade das minhas funções ficava um pouco menor do que a da conferência.
- **Causa:** `pct_change().fillna(0)` troca o `NaN` do primeiro dia por 0, e esse 0 entra no desvio padrão.
- **Solução:** deixar o `NaN` (o `std()` já o ignora): `return fechamento.pct_change()`.
- **Data:** 10/10/2026

## Relatórios de proventos da CVM sumiam da coleta de eventos
- **Sintoma:** nenhum evento do tipo "Relatório Proventos" entrava no banco, mesmo existindo no arquivo da CVM.
- **Causa:** no arquivo IPE da CVM, essas linhas vêm com a coluna `Protocolo_Entrega` **vazia**; o coletor descartava toda linha sem protocolo.
- **Solução:** quando o protocolo vier vazio, usar o número que está no próprio link do documento (`numProtocolo=...&numVersao=...`), como `rad-1477025`. Entraram ~1.400 relatórios de proventos que se perdiam. Lição: conferir os dados reais antes de supor que uma coluna sempre vem preenchida.
- **Data:** 11/10/2026

## `StreamlitAPIException` ao mudar o valor de um campo depois de desenhá-lo
- **Sintoma:** ao criar uma lista no Research, o código tentava abrir a lista nova trocando `st.session_state["research_lista"]`, e o Streamlit recusa.
- **Causa:** o valor de um campo com `key` só pode ser mudado **antes** de o campo aparecer na tela naquela execução (ou dentro de um `on_click`).
- **Solução:** guardar um "pedido pendente" (`research_lista_pendente`) e aplicá-lo no começo da próxima execução, antes do `st.selectbox`.
- **Data:** 11/10/2026

## Testes de migração quebravam a cada migração nova
- **Sintoma:** `test_migracao_0006_vai_e_volta` falhou depois de criar a 0007 (e de novo com a 0008).
- **Causa:** o teste descia "uma versão" (`migrar_para("-1")`) a partir da última; com uma migração nova, "-1" passou a desfazer outra.
- **Solução:** função `desfazer_ate("0005")` em `src/banco/conexao.py`, que desce até uma versão exata; os testes usam o número da versão, não uma contagem.
- **Data:** 11/10/2026

## Página nova acusava "não consegui ler os eventos" no modo local
- **Sintoma:** a página Acontecimentos mostrava erro ao rodar sem conta, num banco SQLite antigo.
- **Causa:** o app abre o banco sem aplicar as migrações (no servidor, quem aplica é o contêiner ao subir); no banco local antigo, a tabela `eventos` não existia.
- **Solução:** tratar "tabela não existe" (`OperationalError`/`ProgrammingError`) como "eventos ainda não coletados", com a dica de rodar `python -m scripts.atualizar_eventos` (que também prepara o banco).
- **Data:** 11/10/2026

## Coleta da SEC ficava mais lenta a cada empresa (7,5 min para 500)
- **Sintoma:** a primeira coleta dos eventos dos EUA começava rápida e ia ficando lenta; cada empresa demorava mais que a anterior.
- **Causa:** `gravar_eventos` lia **todos** os protocolos já guardados da fonte para saber o que era novo. Gravando empresa por empresa, a leitura crescia a cada uma (500 empresas × milhares de linhas).
- **Solução:** ler só os protocolos do lote que está sendo gravado (`protocolo IN (...)`, em pedaços de 5.000, porque o SQLite limita o número de parâmetros de uma consulta).
- **Data:** 11/10/2026

## A coleta de um mercado apagaria o mapa de tickers do outro
- **Sintoma (evitado antes de acontecer):** `gravar_tickers` apagava a tabela inteira antes de gravar o mapa novo; com a SEC, a coleta da CVM das 7h apagaria as empresas dos EUA (e vice-versa).
- **Solução:** cada origem apaga só as suas linhas (`origem="sec"` mexe nas que começam com `CIK`; a CVM, nas outras). Teste: `test_mapa_da_sec_e_o_da_cvm_nao_se_apagam`.
- **Data:** 11/10/2026
