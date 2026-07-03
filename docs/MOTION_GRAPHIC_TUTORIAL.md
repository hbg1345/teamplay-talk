# Teamplay Talk MCP Motion Graphic Tutorial

## Core Message

Teamplay Talk is an AI PM for team projects.

The room owner gives direction.
Team members respond through KakaoTalk.
The AI PM turns scattered replies into roadmap, roles, todos, meetings, daily reports, and decisions.

## Scenario

Project: Kakao MCP Competition

Goal: Build and submit a working MCP service demo by July 10, 2026.

Team:

- Park Sewon: room owner, PM
- Kim Juho: MCP server and OAuth
- Lee Minji: UX and dashboard
- Choi Doyun: testing and presentation

## Main Actors

### Room Owner

The room owner starts the project, confirms decisions, and asks the AI PM to move the project forward.

Typical owner actions:

- Create a room
- Build a roadmap
- Ask for team feedback
- Confirm roles
- Generate todos
- Check daily reports
- Send final notices

### Team Members

Team members do not need to manage the project system directly.
They receive KakaoTalk messages, answer forms, check their roles, and complete daily check-ins.

Typical member actions:

- Join with an invite code
- Submit roadmap feedback
- Rank preferred roles
- Submit available meeting times
- Check completed todos
- Report blockers

### AI PM / MCP

The AI PM handles project coordination as real actions through MCP tools.

Typical AI PM actions:

- Create rooms and invite codes
- Generate roadmaps
- Create and send forms
- Summarize responses
- Assign roles
- Decompose todos
- Schedule meetings
- Send KakaoTalk notices
- Generate daily reports
- Update project state

## Ideal Workflow

```text
Create Room
→ Build Roadmap
→ Collect Roadmap Feedback
→ Confirm Roadmap
→ Create Role Survey
→ Confirm Roles
→ Generate Role-based Todos
→ Schedule Meetings and Deadlines
→ Run Daily Reports and Check-ins
→ Review Dashboard
→ Send Final Notice
→ Run Retrospective
→ Close Room
```

## 1. Create Room

### Owner Input

```text
카카오 MCP 대회방 만들어줘
```

### AI PM Output

```text
'카카오 MCP 대회방'이 생성되었습니다.

팀원에게 아래 초대 코드를 공유하세요.
초대 코드: AbC123xY

PlayMCP에서 teamplay-talk를 열고
"초대 코드 AbC123xY로 방에 참여할래"라고 요청하면 됩니다.

다음으로 프로젝트 로드맵을 만들어볼까요?
```

### Team Member Input

```text
초대 코드 AbC123xY로 방에 참여할래
```

### AI PM Output

```text
카카오 MCP 대회방에 참여했습니다.
현재는 프로젝트 로드맵을 준비하는 단계입니다.
방장이 의견 요청을 보내면 카카오톡으로 안내드릴게요.
```

### Why This Step Exists

팀플은 시작부터 참여자와 작업 공간이 정리되어야 한다.
방이 만들어져야 이후의 로드맵, 역할, todo, 투표, 리포트가 모두 같은 프로젝트 맥락에 저장된다.

### MCP Logic

- Create room
- Generate invite code
- Set current room context
- Suggest next step: roadmap creation

## 2. Build Roadmap

### Owner Input

```text
카카오 MCP 대회 출품작 로드맵 만들어줘.
최종 제출은 7월 10일이야.
```

### AI PM Output

```text
카카오 MCP 대회 로드맵 초안을 만들었습니다.

1. 주제 확정
2. 핵심 기능 설계
3. MCP 서버 구현
4. 카카오 API/OAuth 연동
5. 데모 UX와 대시보드 정리
6. 테스트 및 최종 제출

다음 단계로 팀원들에게 이 로드맵이 적절한지 의견을 받아볼 수 있습니다.
진행할까요?
```

### Why This Step Exists

역할이나 할 일을 나누기 전에 팀이 무엇을 완성해야 하는지 먼저 정해야 한다.
로드맵은 이후 역할 분배와 todo 생성의 기준점이 된다.

### MCP Logic

- Analyze project topic
- Generate milestone candidates
- Save roadmap
- Suggest roadmap review before role assignment

## 3. Collect Roadmap Feedback

### Owner Input

```text
로드맵 괜찮은지 팀원 의견 받아봐
```

### AI PM Output

```text
로드맵 검토 의견 폼을 만들었습니다.

팀원들은 현재 로드맵을 보고
추가할 단계, 수정할 단계, 위험 요소를 남길 수 있습니다.

팀원들에게 보내드릴까요?
```

### Owner Input

```text
보내줘
```

### KakaoTalk Message to Members

```text
[팀플톡] 카카오 MCP 대회 로드맵 검토 요청

현재 로드맵
1. 주제 확정
2. 핵심 기능 설계
3. MCP 서버 구현
4. 카카오 API/OAuth 연동
5. 데모 UX와 대시보드 정리
6. 테스트 및 최종 제출

빠진 단계나 수정할 부분이 있으면 의견을 남겨주세요.

응답하기:
https://teamplay-talk.tech/forms/...
```

### Team Member Responses

```text
김주호:
OAuth 인증 검증 단계를 따로 빼면 좋겠습니다.

이민지:
대시보드 디자인 시간이 부족할 수 있습니다.

최도윤:
발표 시나리오와 시연 동선 준비가 필요합니다.
```

### Why This Step Exists

로드맵을 방장이 혼자 확정하면 빠진 작업이 생기기 쉽다.
팀원 의견을 먼저 받으면 이후 실행 단계에서 변경 비용이 줄어든다.

### MCP Logic

- Create opinion form
- Attach roadmap context to the form
- Send KakaoTalk message
- Collect text responses
- Summarize suggestions and risks

## 4. Summarize Feedback and Confirm Roadmap

### Owner Input

```text
로드맵 의견 결과 정리해줘
```

### AI PM Output

```text
로드맵 의견 결과입니다.

김주호
- OAuth 인증 검증 단계를 따로 빼는 것이 좋음

이민지
- 데모 화면과 대시보드 디자인 시간이 부족할 수 있음

최도윤
- 제출 전 발표 스크립트와 시연 동선 준비 필요

추천 수정안:
1. 주제 확정
2. 핵심 기능 설계
3. MCP 서버 구현
4. 카카오 API/OAuth 연동
5. 데모 UX와 대시보드 정리
6. 테스트, 발표 준비, 최종 제출

이 수정안으로 로드맵을 확정할까요?
```

### Owner Input

```text
그 수정안으로 확정해줘
```

### AI PM Output

```text
로드맵을 확정했습니다.

다음 단계로 로드맵에 맞는 역할을 나누는 것이 좋습니다.
역할 선호도 조사를 만들어볼까요?
```

### KakaoTalk Message to Members

```text
[팀플톡] 카카오 MCP 대회 로드맵이 확정되었습니다.

1. 주제 확정
2. 핵심 기능 설계
3. MCP 서버 구현
4. 카카오 API/OAuth 연동
5. 데모 UX와 대시보드 정리
6. 테스트, 발표 준비, 최종 제출

다음 단계는 역할 분배입니다.
```

### Why This Step Exists

확정된 로드맵이 있어야 역할과 todo가 흔들리지 않는다.
이 시점부터 프로젝트는 "의견 수렴"에서 "실행 계획"으로 넘어간다.

### MCP Logic

- Read collected responses
- Summarize by member
- Identify common changes and risks
- Update roadmap if approved
- Mark roadmap as confirmed
- Suggest role planning

## 5. Role Planning

### Owner Input

```text
로드맵 기준으로 역할분배 시작해줘
```

### AI PM Output

```text
로드맵을 기준으로 필요한 역할을 제안했습니다.

1. 기획·PM
2. MCP 서버 구현
3. 카카오 API/OAuth 연동
4. 데모 UX·대시보드
5. 테스트·발표·제출

팀원들에게 역할 선호도 조사를 보낼까요?
```

### KakaoTalk Message to Members

```text
[팀플톡] 역할 선호도 조사

카카오 MCP 대회에서 맡고 싶은 역할을 순서대로 선택해주세요.

역할 후보
- 기획·PM
- MCP 서버 구현
- 카카오 API/OAuth 연동
- 데모 UX·대시보드
- 테스트·발표·제출

응답하기:
https://teamplay-talk.tech/forms/...
```

### Why This Step Exists

역할은 단순히 사람이 좋아하는 일을 고르는 단계가 아니다.
로드맵을 실제로 실행하기 위한 워크스트림을 나누는 단계다.

### MCP Logic

- Read confirmed roadmap
- Generate role candidates
- Create ranking form
- Send KakaoTalk message
- Aggregate preferences
- Detect overlap or missing ownership

## 6. Confirm Roles

### Owner Input

```text
역할 결과 보고 배정해줘
```

### AI PM Output

```text
역할 선호도와 팀 구성을 기준으로 역할을 배정했습니다.

박세원: 기획·PM
김주호: MCP 서버 구현, 카카오 API/OAuth 연동
이민지: 데모 UX·대시보드
최도윤: 테스트·발표·제출

이대로 확정할까요?
```

### Owner Input

```text
확정해
```

### AI PM Output

```text
역할을 확정했습니다.

이제 로드맵과 역할을 기준으로 팀원별 todo를 만들 수 있습니다.
```

### KakaoTalk Message to Members

```text
[팀플톡] 역할 분배가 확정되었습니다.

박세원: 기획·PM
김주호: MCP 서버 구현, 카카오 API/OAuth 연동
이민지: 데모 UX·대시보드
최도윤: 테스트·발표·제출

다음 단계에서는 역할별 실행 todo가 정리됩니다.
```

### Why This Step Exists

역할 확정은 책임의 기준을 만든다.
이 기준이 있어야 todo가 개인별로 배정될 수 있다.

### MCP Logic

- Read role preference responses
- Score role fit
- Generate assignment draft
- Confirm with room owner
- Save final roles
- Notify members

## 7. Generate Role-Based Todos

### Owner Input

```text
로드맵과 역할 기준으로 팀원별 todo 만들어줘
```

### AI PM Output

```text
팀원별 todo를 생성했습니다.

박세원
- 대회 주제와 핵심 문제 정의
- 기능 우선순위 정리
- 팀 진행 상황 확인

김주호
- MCP 서버 기본 구조 구현
- OAuth 인증 흐름 검증
- 카카오 API 연동 테스트

이민지
- 폼 화면 UX 정리
- 대시보드 정보 구조 정리
- 데모 화면 디자인 다듬기

최도윤
- 테스트 시나리오 작성
- 발표 흐름 정리
- 최종 제출 체크리스트 관리

다음으로 마감일 기준 일정을 배정하거나, 회의 가능 시간을 잡을 수 있습니다.
```

### Why This Step Exists

역할만 있으면 실행이 모호하다.
todo까지 쪼개져야 팀원이 오늘 무엇을 해야 하는지 알 수 있다.

### MCP Logic

- Read confirmed roadmap
- Read confirmed roles
- Match roles to milestones
- Generate executable todos
- Assign todos to members
- Save todo status as open

## 8. Schedule Meeting

### Owner Input

```text
이번 주 안에 전체 회의 시간 잡아줘
```

### AI PM Output

```text
회의 가능 시간 조사를 만들었습니다.

팀원들이 가능한 시간을 선택하면
가장 많이 겹치는 시간을 추천해드릴게요.

보내드릴까요?
```

### KakaoTalk Message to Members

```text
[팀플톡] 카카오 MCP 대회 회의 시간 조사

이번 주 전체 회의 가능한 시간을 선택해주세요.

응답하기:
https://teamplay-talk.tech/forms/...
```

### Result Output

```text
회의 가능 시간 결과입니다.

가장 많이 가능한 시간:
1. 2026년 7월 6일 월요일 21:00 - 4명 가능
2. 2026년 7월 7일 화요일 20:00 - 3명 가능

추천 회의 시간은 2026년 7월 6일 월요일 21:00입니다.
이 시간으로 확정할까요?
```

### Why This Step Exists

회의 시간 조율은 팀장이 직접 카톡에서 하나씩 물으면 가장 많이 시간이 드는 작업이다.
MCP는 후보 생성, 응답 수집, 최적 시간 계산을 자동화한다.

### MCP Logic

- Create availability matrix
- Send form
- Collect member responses
- Count overlapping slots
- Recommend best time
- Confirm and notify

## 9. Collect Meeting Location Candidates

### Owner Input

```text
회의 장소 후보 받아봐
```

### AI PM Output

```text
약속 장소 후보를 받는 폼을 만들었습니다.

팀원들은 선호하는 장소를 최대 5개까지 입력할 수 있습니다.
응답이 모이면 중복 장소를 정리하고 후보별 선호도를 보여드릴게요.

카카오맵 MCP가 함께 사용 가능하면 장소명 확인이나 주소 정리에 활용할 수 있습니다.
```

### KakaoTalk Message to Members

```text
[팀플톡] 회의 장소 후보 조사

회의하기 좋은 장소 후보를 적어주세요.
예: 강남역, 신논현역 근처 카페, 홍대입구역

응답하기:
https://teamplay-talk.tech/forms/...
```

### Why This Step Exists

장소 후보는 자유롭게 받되, 결과는 정리된 후보 목록으로 바뀌어야 한다.
카카오맵 MCP가 있으면 장소명 확인과 주소 정리에 도움을 줄 수 있다.

### MCP Logic

- Create location candidate form
- Receive short text answers
- Normalize duplicate place names
- Count preferred places
- Suggest using Kakao Map MCP when available

## 10. Morning Daily Report

### Time

```text
Every day at 09:00
```

### KakaoTalk Message to Members

```text
[팀플톡] 오늘의 팀 진행 리포트

전체 상태
- 진행 중인 마일스톤: MCP 서버 구현
- 오늘 예정된 todo: 4개
- 밀린 todo: 1개

내가 오늘 볼 일
- OAuth 콜백 테스트
- 데모 화면 오류 확인

막힌 이슈
- 카카오 로그인 테스트 계정 확인 필요
```

### Owner Input

```text
오늘 데일리 리포트 보여줘
```

### AI PM Output

```text
오늘의 팀 진행 리포트입니다.

전체 상태
- 로드맵 6단계 중 2단계 진행 중
- 지연된 todo 1개
- 오늘 예정 todo 4개

오늘 완료된 일
- MCP 서버 기본 구조 구현
- 대시보드 초안 정리

밀린 일
- OAuth 콜백 예외 케이스 정리

막힌 점
- 카카오 OAuth 테스트 계정 권한 확인 필요

추천 다음 액션
1. OAuth 이슈를 김주호에게 우선 배정
2. 내일 회의에서 데모 시나리오 확정
3. 발표 준비 todo를 최도윤에게 추가
```

### Why This Step Exists

아침에는 팀원이 오늘 무엇을 해야 하는지 바로 알아야 한다.
방장은 전체 진행 상태와 병목을 빠르게 확인해야 한다.

### MCP Logic

- Find overdue todos
- Find today’s todos
- Find upcoming todos
- Read previous check-ins
- Generate team summary
- Generate member-specific summary
- Highlight blockers

## 11. Evening Daily Check-in

### Time

```text
Every day at 21:00
```

### KakaoTalk Message to Members

```text
[팀플톡] 오늘의 진행 체크

1. 밀린 일 중 완료한 것을 체크해주세요.
2. 오늘 예정된 일 중 완료한 것을 체크해주세요.
3. 미리 끝낸 일이 있다면 체크해주세요.
4. 막힌 점이나 공유할 내용을 적어주세요.

응답하기:
https://teamplay-talk.tech/forms/...
```

### Team Member Response

```text
완료:
- OAuth 콜백 테스트
- 데모 화면 오류 확인

막힌 점:
- PlayMCP 인증 테스트가 한 번 실패했습니다.
```

### Why This Step Exists

밤에는 팀원이 긴 보고서를 쓰지 않아도 된다.
체크박스와 짧은 메모만으로 진행 상태가 업데이트된다.

### MCP Logic

- Send checklist form
- Include overdue todos
- Include today’s todos
- Include upcoming todos that may have been finished early
- Save completed items
- Keep incomplete items open
- Convert blockers into report items

## 12. Next Morning Report Uses Check-in Data

### AI PM Output

```text
어제 체크인 기준 진행 상태입니다.

완료:
- OAuth 콜백 테스트
- 데모 화면 오류 확인

남은 일:
- 발표 시나리오 초안 작성

새로운 리스크:
- PlayMCP 인증 테스트 실패 이슈 확인 필요

추천 액션:
김주호님은 인증 테스트 로그를 먼저 확인해주세요.
박세원님은 발표 시나리오 초안을 오늘 중 작성하는 것이 좋습니다.
```

### Why This Step Exists

체크인은 끝이 아니라 다음 날 리포트의 입력값이다.
어제의 응답이 오늘의 todo, 지연 항목, 리스크로 이어진다.

### MCP Logic

- Yesterday’s check-in becomes today’s context
- Completed todos are closed
- Unfinished todos become overdue
- Blockers become highlighted risks
- AI PM suggests next actions

## 13. Dashboard Review

### Owner Input

```text
지금 방 상황 보여줘
```

### AI PM Output

```text
현재 카카오 MCP 대회방 상태입니다.

로드맵
- 6개 마일스톤 중 2개 진행 중

역할
- 4명 역할 확정 완료

Todo
- 전체 18개
- 완료 6개
- 진행 중 7개
- 지연 1개

진행 중인 폼
- 회의 장소 후보 조사
- 데일리 체크인

자세한 타임라인은 대시보드에서 확인할 수 있습니다.
https://teamplay-talk.tech/dashboard/rooms/...
```

### Why This Step Exists

대시보드는 MCP의 중심이 아니라 프로젝트 상태를 확인하는 보조 화면이다.
핵심 작업은 카카오톡과 MCP 대화 안에서 진행되고, 대시보드는 누적된 흐름을 보여준다.

### MCP Logic

- Read room state
- Read roadmap
- Read forms
- Read todos
- Read daily reports
- Generate dashboard token
- Return temporary dashboard link

## 14. Final Notice

### Owner Input

```text
지금까지 결정된 내용 팀에 공지해줘
```

### KakaoTalk Message to Members

```text
[팀플톡] 카카오 MCP 대회 진행 정리

확정된 내용
- 로드맵 확정 완료
- 역할 분배 완료
- 전체 회의: 2026년 7월 6일 월요일 21:00
- 최종 제출 목표: 2026년 7월 10일

오늘 집중할 일
- MCP 서버 안정화
- OAuth 플로우 검증
- 데모 화면 정리
- 발표 시나리오 초안 작성

각자 맡은 todo를 확인하고 진행 상황을 체크해주세요.
```

### Why This Step Exists

결정사항은 카톡 대화 속에서 흩어지면 안 된다.
AI PM이 확정된 내용을 정리해 팀원에게 다시 공지한다.

### MCP Logic

- Read confirmed decisions
- Read current todos
- Read upcoming deadlines
- Compose concise KakaoTalk notice
- Send to room members

## Motion Graphic Scene Structure

### Scene 1. Before Teamplay Talk

```text
Problem:
- 의견이 카톡방에 흩어짐
- 누가 뭘 하는지 모름
- 방장이 계속 물어봐야 함
- 진행 상황이 매일 새로 헷갈림
```

Visual idea:

- KakaoTalk messages floating around
- Same question repeated
- Owner manually collecting answers

### Scene 2. Create Room

```text
Owner creates room.
Members join with invite code.
```

Visual idea:

- One room appears
- Invite code connects members into the same workspace

### Scene 3. Roadmap

```text
AI PM turns a vague project topic into milestones.
```

Visual idea:

- "카카오 MCP 대회" becomes a structured timeline
- Milestone cards appear in order

### Scene 4. Team Input

```text
Members receive KakaoTalk forms.
They only answer.
AI PM collects and summarizes.
```

Visual idea:

- KakaoTalk messages go out
- Responses come back
- AI PM groups them into clean bullets

### Scene 5. Roles and Todos

```text
Roadmap becomes roles.
Roles become todos.
Todos become daily work.
```

Visual idea:

- Milestones split into role lanes
- Role lanes split into personal todo cards

### Scene 6. Daily Loop

```text
09:00 Daily Report
21:00 Daily Check-in
Next day Updated Report
```

Visual idea:

- Morning sun: report arrives
- Night moon: check-in arrives
- Next morning: project state updates

### Scene 7. Dashboard

```text
All decisions, votes, todos, reports, and milestones appear as a project timeline.
```

Visual idea:

- Timeline shows room activity
- Polls, roles, todos, reports appear in one flow

### Scene 8. Final Message

```text
Team members focus on work.
The AI PM handles coordination.
```

Visual idea:

- Team members working
- AI PM quietly connecting roadmap, forms, KakaoTalk, and reports

## Product Positioning

### One-Line Message

```text
Teamplay Talk turns KakaoTalk conversations into structured project management.
```

### Short Pitch

```text
방장은 방향만 말합니다.
팀원은 카카오톡으로 응답합니다.
AI PM은 로드맵, 역할, todo, 일정, 리포트를 자동으로 연결합니다.
```

### MCP Differentiation

```text
This is not just a chatbot giving advice.

The MCP actually creates rooms, sends forms, gathers responses,
updates todos, sends reports, and keeps project state alive.
```

