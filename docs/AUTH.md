# 인증(OAuth) 설계 메모

> 카카오 OAuth broker 연동은 **사후(나중) 처리**로 보류한다.
> 현재는 **로그인 링크 방식**으로 정상 동작하며, 헤더에 카카오 토큰이 오면
> 자동으로 무로그인 동작하도록 **forward-compatible** 하게 구현돼 있다.

## 현재 동작 (작동 중)
- **호출자 신원**: `identity.resolve_caller()` 가 `Authorization: Bearer` 헤더의
  카카오 토큰으로 호출자를 식별한다. 토큰이 있으면 무로그인으로 바로 동작.
- **헤더가 없으면(현재 PlayMCP 상태)**: 도구가 **카카오 로그인 링크**를 반환 →
  사용자가 클릭 → `/auth/kakao/callback` 에서 인증 → 방 생성/참여/나가기/현재방 설정.
  (= 링크 방식 fallback, 지금 데모는 이걸로 작동)
- **알림(`notify_room`)**: 멤버별 카카오 토큰으로 '나와의 채팅방' self-push.
  멤버 토큰은 로그인 시 `users` 에 저장된다.

## 사후 처리 계획 (나중에)

### 1) PlayMCP 카카오 OAuth broker 연결 — **현재 PlayMCP 버그로 보류**
- 되면: 매 호출 헤더에 카카오 토큰이 실려와 **로그인 클릭 제거 + active room 무마찰**.
- **블로커 (확인됨)**: 카카오는 정상이다. redirect_uri(`.../authorize/oauth:callback`)로
  직접 인가 요청 시 **카카오가 code+state를 정상 반환**하는 것을 확인했다.
  그러나 **PlayMCP 콜백이 실패**한다:
  - `{"message":"Invalid state format.","code":"ERR-CHAT-90400"}` (state 검증)
  - 실제 플로우에선 `"code가 없습니다"` (ERR-CHAT-90400)
  → 카카오→PlayMCP 콜백 이후 **PlayMCP의 state/code 처리 단계 버그**로 추정.
  → **PlayMCP 디스코드 문의 대상.** (우리 설정/서버/카카오는 모두 정상)

### 2) 개인정보 최소화 방향 (broker 연결되면)
- **카카오 broker + 알림 pull 방식 → 토큰 0 저장** 을 목표로.
  - caller 작업(방 생성·내방목록·내 Drive)은 헤더 토큰을 쓰고 버림(무저장).
  - 알림은 DB에 텍스트로만 저장, 멤버가 다음 호출 시 자기 헤더 토큰으로 본인에게 전송.
- 자동 푸시(미접속 멤버에게도)를 유지하려면 → 그 토큰만 **암호화 저장**.

### 3) 무조건 할 일 (broker 여부와 무관)
- 현재 `users.kakao_access_token` 등이 **평문 저장**이다. → **암호화 저장으로 전환**
  (앱 키로 대칭 암호화 or KMS). 개인정보/보안상 제일 시급.

### 4) 구글 Drive
- 헤더 슬롯은 카카오가 쓰므로 구글은 self-managed(`google_tokens`) — 친구 작업과 통일.
- `drive.file` 스코프(앱이 만든 파일만)라 노출 범위는 작음.

## 참고
- PlayMCP redirect URI 형식: `https://playmcp.kakao.com/api/v1/applied-mcps/{mcpId}/authorize/oauth:callback`
- 현재 mcpId: `63607997749844675` (카카오 콘솔 Redirect URI에 등록 완료)
- 배포: `https://167.71.219.241.sslip.io` (DO Droplet + Caddy 자동 HTTPS)
