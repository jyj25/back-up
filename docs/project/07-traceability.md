# 07 · 요구 추적표 (A12)

| 요구 | 설계·계약 | 작업 | 시험 | 현재 근거 (10/30, `a14f0ce`) |
| --- | --- | --- | --- | --- |
| REQ-01 분류 | DES-01 / IF-01 (제안) / ADR-02 | TASK-A1~A4, R4 | TC-08, TC-13 | NOT_RUN · BLOCKED |
| REQ-02 통 찾아가기·복귀 | DES-01, DES-02 / IF-02, IF-03 / ADR-01, 03 | TASK-R2, R7 | TC-04~06, TC-15 (가짜) / TC-09 (실기) | 가짜 PASS · 실기 BLOCKED |
| REQ-03 안전 | DES-02 / IF-02 | TASK-R1, R7 | TC-01~03, TC-07 (가짜) / TC-10 (실기) | 가짜 PASS · 실기 BLOCKED |
| REQ-04 수동 조종 | DES-03 / IF-02 | TASK-R1 | TC-11 | 실기 BLOCKED |
| REQ-05 통에 넣기 | ADR-04 (미정) | TASK-R6 | 결정 후 작성 | 미정 |
| REQ-06 기록·대시보드 | DES-04 / IF-02, IF-04 (예정) | TASK-R5, W1~W3 | TC-14 | NOT_RUN |
| REQ-07 발표장 연결 | DES-01 | TASK-R3, R8 | TC-12 | BLOCKED |

## 변경 영향 예

- **라벨 이름이 바뀌면**: REQ-01, IF-01, IF-03(`stations.json`), TASK-A1·A4·R4, TC-08·TC-13, 대시보드 표시(DES-04) 를 함께 고친다.
- **도착 거리 기준이 바뀌면**: REQ-02, `stations.json` 의 `arrive_size`·`arrive_cm`, TC-04·TC-05·TC-09 기대값.
- **통에 넣는 방법이 정해지면 (ADR-04)**: REQ-05, DES-02 의 `dumping`, `RealDriver.dump()`, TASK-R6, 새 TC, RISK-06 상태.
