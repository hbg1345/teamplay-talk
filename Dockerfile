FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .

# KC(카카오클라우드) 배포는 환경변수 입력란이 없어 .env를 이미지에 굽는다.
# (config.py의 load_dotenv()가 /app/.env를 읽음) — .env는 git에 커밋하지 않는다.
# 주의: .env가 없으면 이 COPY에서 빌드가 실패하므로, 로컬 .env를 둔 채 빌드한다.
COPY .env ./

ENV HOST=0.0.0.0 \
    PORT=8000
EXPOSE 8000

CMD ["teamplay-talk"]
