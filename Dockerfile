FROM python:3.12.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    CORPUS_DB_PATH=/corpus/takhrij.db

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY templates ./templates
COPY static ./static

RUN useradd --create-home --uid 10001 takhrij \
    && mkdir /corpus \
    && chown -R takhrij:takhrij /app /corpus
USER takhrij

VOLUME ["/corpus"]

CMD ["sh", "-c", "exec gunicorn --bind :${PORT} --workers 1 --threads 8 --timeout 3700 'takhrij.web:create_app()'"]
