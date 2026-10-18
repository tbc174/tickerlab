# TickerLab em um contêiner: imagem enxuta, sem testes nem cadernos, rodando sem root.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# dependências primeiro: esta camada só é refeita quando o requirements-prod.txt muda
# (o pip que vem na imagem do Python fica velho: o trivy acusou falha corrigida em versão nova)
COPY requirements-prod.txt .
RUN pip install --upgrade pip==26.2.1 \
    && pip install -r requirements-prod.txt

COPY .streamlit ./.streamlit
COPY static ./static
# o Streamlit manda o HTML com o ícone dele (um barco que parece uma coroa) e só troca pelo nosso
# depois que o script roda; com o arquivo trocado, a aba já abre com o ícone do TickerLab
RUN python -c "import shutil, streamlit, pathlib; shutil.copyfile('static/marca/icone.png', pathlib.Path(streamlit.__file__).parent / 'static/favicon.png')"
COPY app.py ./
COPY src ./src
# as regras do selo de qualidade (base/regras.py), usadas pela tarefa diária atualizar_qualidade
COPY base ./base
COPY telas ./telas
COPY alembic.ini ./
COPY migracoes ./migracoes
COPY conteudo ./conteudo
COPY dados_de_exemplo ./dados_de_exemplo

# o commit deste código, para a linhagem dos números (ADR 0055, exigência 13):
#   docker build --build-arg TICKERLAB_VERSAO="$(git rev-parse HEAD)" .
# Fica no fim para não refazer as camadas de cima a cada commit. Vazio = versão desconhecida.
ARG TICKERLAB_VERSAO=""
ENV TICKERLAB_VERSAO=${TICKERLAB_VERSAO}

# o cache de preços (SQLite) grava em dados_locais; no compose, essa pasta vem de fora
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/dados_locais \
    && chown app:app /app/dados_locais
USER app

EXPOSE 8501

# a saúde no caminho em que o Streamlit está servido: /classico no servidor (compose.yaml), a raiz
# sem a variável (src/classico.py)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; from src.classico import url_da_saude; urllib.request.urlopen(url_da_saude(), timeout=4)"

# aplica as migrações do banco e depois sobe o app (se o banco estiver fora, o contêiner cai e
# o Docker tenta de novo)
CMD ["sh", "-c", "python -m alembic upgrade head && exec streamlit run app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false"]
