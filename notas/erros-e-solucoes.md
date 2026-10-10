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
