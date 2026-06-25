FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .

# PlayMCP in KC는 환경변수 입력란을 제공하지 않으므로 .env를 이미지에 굽는다.
# (config.py의 load_dotenv()가 /app/.env를 읽음) — .env는 git에 커밋하지 않고
# (private repo의 .gitignore 유지), 이미지에만 포함되도록 Docker 이미지 등록 방식으로 배포한다.
# 주의: .env가 없으면 빌드가 실패하므로, 로컬에서 .env를 둔 채로 빌드해야 한다.
COPY .env ./

ENV HOST=0.0.0.0 \
    PORT=8000
EXPOSE 8000

CMD ["teamplay-talk"]
