# Streamlit (interface do app)

## O que é e como roda
- **O que é:** biblioteca que transforma um script Python em página web, sem HTML nem JavaScript.
- **Como rodar:** `python -m streamlit run app.py` (com o `(.venv)` ativo). O navegador abre sozinho.
- **Como funciona:** a cada interação (digitar, escolher), o script roda **de novo, de cima para baixo**.
- **Cuidado:** o comando solto `streamlit` pode apontar para o Conda em vez do `.venv`. Usar `python -m streamlit` garante o ambiente certo.
- **Data:** 10/10/2026

## Componentes que usei no `app.py`
- `st.set_page_config(page_title=..., layout="wide")`: título da aba e largura da página.
- `st.title` e `st.caption`: título e texto pequeno (o aviso de que não é recomendação).
- `st.text_input("Ticker", value="PETR4.SA")`: **campo de digitar**; devolve o texto.
- `st.selectbox("Período", [...], index=2)`: **menu de escolha**; devolve a opção.
- `st.columns(3)`: três colunas lado a lado; `colunas[0].metric(...)` põe um número grande na primeira.
- `st.metric("Retorno total", f"{valor:.2%}")`: cartão com número. O `:.2%` formata a fração como porcentagem com 2 casas.
- `px.line(...)` + `st.plotly_chart(figura, use_container_width=True)`: gráfico de linha do Plotly, ocupando a largura.
- `st.error(...)` e `st.stop()`: mostra uma mensagem de erro e **para o script** ali, em vez de quebrar.
- **Cuidado:** os `st.text_input`, `st.selectbox` etc. são para o que a **pessoa digita ou escolhe**. Resultado de cálculo não vai em campo; é uma variável comum (`retorno = ind.calcular_retorno_diario(fechamento)`).
- **Data:** 10/10/2026

## Tema escuro: `.streamlit/config.toml`
- **O que é:** arquivo que o Streamlit lê sozinho para configurar o tema.
- **Exemplo:** `base = "dark"`, `primaryColor = "#2962ff"` (azul), `backgroundColor = "#000000"`.
- **Data:** 10/10/2026

## Organização: `app.py` só mostra, `src/` calcula
- O `app.py` importa as funções (`from src import indicadores as ind`) e só as chama. Assim as contas podem ser testadas e reaproveitadas sem abrir o navegador.
- **Data:** 10/10/2026

## A ver
- Cache (`st.cache_data`), abas, gráficos com vários tickers, estado da sessão

*(Tiago: reescreva com suas palavras.)*
