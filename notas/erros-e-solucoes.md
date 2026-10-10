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
