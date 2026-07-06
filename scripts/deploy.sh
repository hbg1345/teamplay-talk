#!/usr/bin/env bash
# 한 방 배포: 이미지 빌드 → ghcr 푸시.
# 이후 KC 콘솔에서 MCP "재배포"(새 이미지 pull)만 누르면 끝.
#
# 사용: bash scripts/deploy.sh
#
# ── KC 재배포(Docker 이미지) 폼에 입력할 값 ───────────────────────────────
#   Registry 호스트   : ghcr.io
#   Registry 사용자   : hbg1345
#   Registry 비밀번호 : GitHub PAT (read:packages 권한)
#   image_name        : hbg1345/teamplay-talk
#   image_tag         : latest
#
# ── PlayMCP OAuth 폼(카카오) ─────────────────────────────────────────────
#   Authorization Endpoint : https://kauth.kakao.com/oauth/authorize
#   Token Endpoint         : https://teamplay-talk.playmcp-endpoint.kakaocloud.io/kakao/token
#   Client ID              : 카카오 REST API 키 / Grant Type: AUTHORIZATION_CODE
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

IMAGE="ghcr.io/hbg1345/teamplay-talk:latest"

cd "$(dirname "$0")/.."

echo "==> 1/3 빌드"
docker build -t teamplay-talk:latest .

echo "==> 2/3 태그"
docker tag teamplay-talk:latest "$IMAGE"

echo "==> 3/3 푸시: $IMAGE"
docker push "$IMAGE"

cat <<'EOF'

✅ 푸시 완료. 이제 KC 콘솔에서 MCP "재배포"(새 이미지 pull) 하세요.

─ KC 재배포(Docker 이미지) 폼 입력값 ───────────────────────
  Registry 호스트   : ghcr.io
  Registry 사용자   : hbg1345
  Registry 비밀번호 : GitHub PAT (read:packages)
  image_name        : hbg1345/teamplay-talk
  image_tag         : latest
────────────────────────────────────────────────────────────
EOF
