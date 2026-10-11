# TickerLab em um contêiner: imagem enxuta, sem testes nem cadernos, rodando sem root.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# dependências primeiro: esta camada só é refeita quando o requirements-prod.txt muda
COPY requirements-prod.txt .
RUN pip install -r requirements-prod.txt

COPY .streamlit ./.streamlit
COPY static ./static
COPY app.py ./
COPY src ./src
COPY alembic.ini ./
COPY migracoes ./migracoes
COPY conteudo ./conteudo
COPY dados_de_exemplo ./dados_de_exemplo

# o cache de preços (SQLite) grava em dados_locais; no compose, essa pasta vem de fora
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/dados_locais \
    && chown app:app /app/dados_locais
USER app

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)"

# aplica as migrações do banco e depois sobe o app (se o banco estiver fora, o contêiner cai e
# o Docker tenta de novo)
CMD ["sh", "-c", "python -m alembic upgrade head && exec streamlit run app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false"]
