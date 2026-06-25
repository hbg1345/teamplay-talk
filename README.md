# teamplay-talk

KAKAO PlayMCP 공모전 출품용 — 팀플(팀 프로젝트) 협업 MCP 서버.

팀 생성·익명 투표·진척 관리·카카오 알림을 MCP 도구로 제공한다.
스택: **Python (FastMCP)** · **Postgres (DigitalOcean Managed)** · **DigitalOcean 상시 컨테이너**.

## 개발

```bash
uv venv
uv pip install -e .

# 서버 실행 (기본 0.0.0.0:8000)
teamplay-talk
# 또는
uv run python -m teamplay_talk.server
```

- MCP 엔드포인트: `http://localhost:8000/mcp/`
- 헬스체크: `http://localhost:8000/health`

### 검증 (P0)

서버를 띄운 뒤:

```bash
uv run python scripts/smoke.py
# -> tools/list (1): ['teamplay_ping'] / teamplay_ping -> 'pong'
```

## 로드맵

P0 스캐폴드 → P1 카카오 OAuth 신원 → P2 팀 → P3 알림(카톡 self-push) → P4 익명 투표 → P5 진척 → P6 cron 자동알림 → P8 배포·PlayMCP 등록.
