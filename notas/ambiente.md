# Ambiente: Python, ambiente virtual e VS Code

## Ambiente virtual (`.venv`)
- **O que é:** uma "caixinha" com o Python e as bibliotecas só deste projeto.
- **Para que serve:** projetos diferentes podem usar versões diferentes de uma biblioteca sem brigar. Também deixa claro o que o projeto precisa para rodar.
- **Como usar:** o ambiente já foi criado na pasta `.venv`. No terminal do VS Code ele aparece com `(.venv)` no começo da linha. Confira com `python --version` (deve mostrar 3.12.10).
- **Cuidados:**
  - A pasta `.venv` **não vai para o Git** (está no `.gitignore`). Quem baixar o projeto cria a sua com `python -m venv .venv` e instala as bibliotecas com `pip install -r requirements.txt`.
  - Sem o `(.venv)` ativo, o Python usado pode ser outro e as bibliotecas não são encontradas.
- **Data:** 09/10/2026

## Escolher o interpretador no VS Code
- **O que é:** dizer ao VS Code qual Python usar neste projeto.
- **Como usar:** `Ctrl+Shift+P`, digitar `Python: Select Interpreter`, escolher `Python 3.12.10 (.venv)`. Depois abrir um terminal novo.
- **Por que precisei:** o terminal abriu com `(base)` e Python 3.14.
- **Data:** 09/10/2026

## Conda e o ambiente `base`
- **O que é:** o Conda é outro gerenciador de ambientes (Anaconda/Miniconda). O `base` é o ambiente padrão dele.
- **O que aconteceu:** o Conda ativava o `base` sozinho em todo terminal, na frente do `.venv`.
- **Como resolver:** escolher o interpretador certo no VS Code (acima). Se o `(base)` insistir: `conda deactivate` e depois `.\.venv\Scripts\Activate.ps1`.
- **Data:** 09/10/2026

## `requirements.txt`
- **O que é:** lista das bibliotecas do projeto com as versões exatas.
- **Para que serve:** recriar o ambiente em outro computador (ou no servidor, dentro do Docker).
- **Como gerar:** `python -m pip freeze > requirements.txt`.
