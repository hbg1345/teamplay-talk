FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .

ENV HOST=0.0.0.0 \
    PORT=8000
EXPOSE 8000

CMD ["teamplay-talk"]
