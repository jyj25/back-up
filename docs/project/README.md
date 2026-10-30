# 8조 프로젝트 문서 — 스마트 분리수거 로봇

10/30 수업 「프로젝트 실무 · 팀·표준·개발 산출물」의 **여덟 묶음**에 맞춘 팀 문서다.
로봇(이정민)과 AI(정유정, `yujeong` 브랜치) 문서를 합쳐 지금 구조(로봇이 통을 찾아가는 방식)에 맞게 다시 썼다.
요구(REQ) → 설계(DES)·계약(IF)·결정(ADR) → 작업(TASK) → 시험(TC)이 같은 ID 로 이어진다.

| 묶음 | 문서 | 교재 양식 |
| --- | --- | --- |
| 1. 문제·목표·범위·인수 | [01-brief.md](01-brief.md) | A01 |
| 2. 역할·검토·결정권 | [02-roles.md](02-roles.md) | A02, A22 |
| 3. 요구·우선순위·수용 기준 | [03-requirements.md](03-requirements.md) | A03 |
| 4. 화면·구조·인터페이스·결정 | [04-design.md](04-design.md) | A05~A08 |
| 5. 작업·의존성·위험·변경 | [05-tasks-risks.md](05-tasks-risks.md) | A04, A13, A14 |
| 6. 시험 계획·케이스·결과 | [06-tests.md](06-tests.md) | A09~A11 |
| 7. 연결표 | [07-traceability.md](07-traceability.md) | A12 |
| 8. 실행·인계·다음 작업 | [08-run-handoff.md](08-run-handoff.md) | A17, A18 |
| 부록 | [09-data-ai.md](09-data-ai.md) · [10-bom-power.md](10-bom-power.md) · [11-security.md](11-security.md) | A19, A20, A21 |

## 읽는 규칙

- **사실 / 가정 / 미확인**을 구별한다. 담당자 기록을 옮긴 것은 "(담당자 기록)" 으로 표시한다.
- 시험 상태: `PASS`(실제 실행해서 기대와 일치) · `FAIL` · `BLOCKED`(선행 조건 없음) · `NOT_RUN`(실행 전).
  노트북 가짜 모드·보드 로직 시험의 PASS 를 **실제 시연 동작의 PASS 로 읽지 않는다.**
- `제안` = 합의 전, `결정` = 팀장이 정했거나 팀이 합의, `미결정` = 아직 정할 사람·기한만 있음.
- 기준일 2026-10-30. 문서를 고치면 같은 PR 에서 관련 ID 문서도 함께 고친다.
- 공개 저장소: Wi-Fi 비밀번호, 기기 IP·계정, API 키는 적지 않는다.

## 담당자 세부 문서 (원본)

이 문서는 팀 전체를 묶은 것이다. 담당 파트의 세부 요구·시험은 각자 폴더가 원본이다.

| 담당 | 원본 | 비고 |
| --- | --- | --- |
| 로봇 | [`jeongmin/`](../../jeongmin/README.md) | 로봇 API, 성능 메모 |
| AI | [`yujeong/ai/docs/`](https://github.com/Jeongmin-lee123/-ai2-8-/tree/yujeong/yujeong/ai/docs), [`yujeong/docs/`](https://github.com/Jeongmin-lee123/-ai2-8-/tree/yujeong/yujeong/docs) | 아직 `yujeong` 브랜치에만 있음 (main 에 PR 전) |
| 웹·앱 | `minhyeong/` (예정) | |

**ID 대응** — AI 원본 문서의 ID 를 팀 문서에서는 이렇게 부른다.

| AI 원본 (`yujeong`) | 팀 문서 |
| --- | --- |
| A07 IF-02 판정 JSON | **IF-01** |
| A07 IF-01 보드→PC 영상 (수집용) | **IF-05** |
| A03 I-02·I-03·I-05, S-02·S-03·S-14 | **REQ-01** |
| A03 C-01~08 (수집기), F-01~04 (영상 펌웨어), T-01~07 (학습 스크립트) | **REQ-01** 의 세부 요구 (원본 유지) |
| A08 ADR-01 카메라 경로, ADR-02 Wi-Fi, ADR-06 라즈봇, ADR-07 담당 | **ADR-02** 와 02 역할로 결정됨 |
| A08 ADR-03 서보 연결 | **ADR-04** (통에 넣는 방법, 미결정) |
| A08 ADR-04 분류 종류 | **ADR-05** (미결정) |
| A08 ADR-05 통 가득 참 | **ADR-06** (미결정, 선택 기능) |
| A09-A11 TC-01·TC-06 | **TC-16 · TC-17** |
| A13 RISK-01~08 | **RISK-02 · 10~14** |
