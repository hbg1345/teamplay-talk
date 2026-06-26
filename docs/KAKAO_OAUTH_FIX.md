# 카카오 OAuth (PlayMCP) — 토큰 교환 실패 해결

## 증상
- PlayMCP OAuth broker로 **구글은 정상**, **카카오만 토큰 교환 단계에서 실패**.
- 설정(Client ID/Secret, 엔드포인트, Scope, Redirect URI)은 모두 정확한데도 막힘.

## 원인
`/token`에서 client 자격증명을 보내는 방식 차이:

| | client 자격증명 |
|---|---|
| **PlayMCP가 보내는 방식** | HTTP **Basic** 헤더 (`Authorization: Basic ...`) |
| **구글 `/token`** | Basic·body **둘 다 허용** → 통과 |
| **카카오 `/token`** | **body 방식만 허용** (Basic 거부) → 실패 |

즉 PlayMCP가 Basic으로 보내는데 카카오는 body만 받아서, 같은 경로인데 구글만 됐던 것.

## 해결: 토큰 프록시
우리 서버에 **`/kakao/token` 프록시**를 두고, PlayMCP의 Token Endpoint를 카카오 대신
이 프록시로 지정한다. 프록시가 **Basic으로 온 자격증명을 body로 변환**해 카카오에 중계.

- 코드: [`src/teamplay_talk/kakao_token_proxy.py`](../src/teamplay_talk/kakao_token_proxy.py)
- 동작: 요청의 Basic 헤더에서 `client_id`/`client_secret`을 꺼내 body에 넣고
  `https://kauth.kakao.com/oauth/token` 에 form body로 POST → 응답 그대로 반환.
- 실패 시 카카오 실제 에러(KOE0xx)를 컨테이너 로그에 남김(`[kakao_token_proxy]`).

### PlayMCP OAuth 폼 설정
| 항목 | 값 |
|---|---|
| Authorization Endpoint | `https://kauth.kakao.com/oauth/authorize` |
| **Token Endpoint** | `https://<배포URL>/kakao/token` ← 프록시 |
| Client ID | 카카오 REST API 키 |
| Client Secret | (카카오 [보안]에서 "사용함"일 때만) |
| Scope | `talk_message profile_nickname` |
| Grant Type | `AUTHORIZATION_CODE` |

## 검증
```bash
# 서버 떠있나
curl https://<배포URL>/health            # -> ok
# 프록시 살아있나 (더미 키 -> KOE101 = 카카오까지 정상 도달)
curl -X POST https://<배포URL>/kakao/token \
  -H "Authorization: Basic $(printf 'k:s' | base64)" \
  -d "grant_type=authorization_code&code=DUMMY&redirect_uri=https://x/cb"
```
