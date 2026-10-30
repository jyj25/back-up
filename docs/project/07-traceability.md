# 07 · 요구 추적표 (A12)

| 요구 | 설계·계약·결정 | 작업 | 시험 | 현재 근거 (10/30) |
| --- | --- | --- | --- | --- |
| REQ-01 분류·확정 | DES-01 / IF-01 / ADR-02, ADR-05 | TASK-A3~A9, R4, R10 | TC-17 (로직) / TC-08, 13, 18 | 로직 PASS · 모델 BLOCKED |
| REQ-02 통 찾아가기·복귀 | DES-01, 02 / IF-02, 03 / ADR-01, 03 | TASK-R2, R7, R10 | TC-04~06, 15 (가짜) / TC-09 | 가짜 PASS · 실기 BLOCKED |
| REQ-03 안전 | DES-02 / IF-02 | TASK-R1, R7 | TC-01~03, 07 (가짜) / TC-10 | 가짜 PASS · 실기 BLOCKED |
| REQ-04 수동 조종·분류 | DES-03 / IF-02 | TASK-R1 | TC-07 / TC-11 | 가짜 PASS · 실기 BLOCKED |
| REQ-05 통에 넣기 | ADR-04 (미결정) | TASK-R6 | 결정 후 작성 | 미정 |
| REQ-06 기록·대시보드 | DES-04 / IF-02, IF-04 (예정) | TASK-R5, W1~W3 | TC-14 | NOT_RUN |
| REQ-07 발표장 연결 | DES-01 | TASK-R3, R8 | TC-12 | BLOCKED |
| REQ-08 가득 참 알림 (선택) | ADR-06 (미결정) | TASK-W3 | 결정 후 작성 | 미정 |
| REQ-09 사진 수집 | IF-05 | TASK-A1, A2, A6, R9 | TC-16 / TC-19 | 영상 PASS · 수집 흐름 NOT_RUN |

## 변경 영향 예

- **분류 종류·통 이름을 바꾸면 (ADR-05, 10/30 한 번 바꿈 — CR-06)**: IF-01 의 `class` 값, IF-03 `stations.json`, 수집 클래스(TASK-A6), 마커 라벨(TASK-R10), REQ-01·09, TC-08·13, 대시보드 표시.
- **IF-01 확정 신호 방식이 정해지면**: 추론 펌웨어 출력(TASK-A8), 로봇 수신(TASK-R4), `pi_reader.py`, TC-13.
- **도착 거리 기준이 바뀌면**: REQ-02, `stations.json` 의 `arrive_size`·`arrive_cm`, TC-04·05·09 기대값.
- **통에 넣는 방법이 정해지면 (ADR-04)**: REQ-05, DES-02, `RealDriver.dump()`, TASK-R6, [10](10-bom-power.md) 전원, 새 TC, RISK-06.
- **확정 기준(0.8 / 0.2 / 3번)을 바꾸면**: REQ-01, `sorter_logic.h` Config, TC-17 재실행, TC-18.
