FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    FASTEMBED_CACHE_PATH=/app/models

WORKDIR /app

ARG PIP_INDEX_URL=https://mirror-pypi.runflare.com/simple
COPY requirements.txt .
RUN pip install --timeout 120 --retries 10 \
        --index-url "${PIP_INDEX_URL}" \
        --trusted-host mirror-pypi.runflare.com \
        -r requirements.txt

# Bake the embedding model into the image so the container works without HuggingFace access.
ARG EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='${EMBED_MODEL}')"

COPY *.py ./
COPY Dataset.txt krs_chunks.txt ./
COPY web ./web
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh && chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /app/data

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
