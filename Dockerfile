FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .

# KakaoCloud MCP 배포는 런타임 환경변수 입력이 없어 설정을 이미지에 굽는다.
# .env는 비공개 저장소에 커밋되어 있어야 하며, 여기서 /app/.env로 복사된다.
COPY .env ./

# KakaoCloud 무설정 컨테이너 플랫폼은 고정 포트 8080으로 라우팅한다.
# 앱은 $PORT를 읽으므로(config.py) KC가 PORT를 주입하면 그 값을, 없으면 8080을 쓴다.
ENV HOST=0.0.0.0 \
    PORT=8080
EXPOSE 8080

CMD ["teamplay-talk"]
