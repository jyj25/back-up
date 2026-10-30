# 06 · 시험 계획·케이스·결과 (A09~A11)

## 계획

| 항목 | 내용 |
| --- | --- |
| 대상 | 로봇 조종 서버(`jeongmin/robot`), 분류 펌웨어(예정), 대시보드(예정) |
| 근거 종류 구별 | ① 자동 시험(가짜 모드) ② 노트북 가짜 서버 수동 확인 ③ **실제 로봇** ④ 발표장 사용 — 서로 다른 근거로 적는다 |
| 범위 밖 | 장시간 내구, 여러 바닥 재질, 접근성 전체 |
| 판정 | 사전 조건이 없으면 `BLOCKED`, 실행 전은 `NOT_RUN`, 실제 관찰 후에만 `PASS`/`FAIL` |
| 담당 | 각자 자기 파트 시험·기록, 독립 검토는 11/1 서로 교차 |

## 시험 케이스 (TC)

| ID | 요구 | 확인 내용 | 근거 종류 |
| --- | --- | --- | --- |
| TC-01 | REQ-03 | 이동 명령 후 지정 시간이 지나면 자동 정지 | ① |
| TC-02 | REQ-03 | 속도가 상한을 넘지 않음, 잘못된 값은 거절(422) | ① |
| TC-03 | REQ-03 | 앞 8cm 장애물: 앞 이동 거절·뒤 이동 허용 / 가는 중 10cm 되면 정지 | ① |
| TC-04 | REQ-02 | 판단 규칙: 못 찾으면 회전, 벗어나면 맞추기, 가운데면 전진, 크거나 가까우면 도착 | ① |
| TC-05 | REQ-02 | 가짜 세계에서 재활용 통 앞 15~35cm 에 도착 → 출발점 35cm 이내 복귀 | ① |
| TC-06 | REQ-02 | 마커가 없는 통: `failed` + "못 찾았습니다" | ① |
| TC-07 | REQ-03 | 임무 중 수동 이동 → 임무 `cancelled`, 수동 이동은 실행 | ① |
| TC-08 | REQ-01 | 시연 실물로 종류별 10회 → 9회 이상 정답, 빈 트레이는 `empty` | ③ |
| TC-09 | REQ-02 | 실제 로봇·실제 통 3개 × 각 5회: 통 앞 20~30cm 도착·복귀 | ③ |
| TC-10 | REQ-03 | 실제 로봇이 벽 앞 15cm 근처에서 멈추고 밀린 거리 측정 | ③ |
| TC-11 | REQ-04 | 휴대폰으로 조종, 손 떼면 정지, 영상 지연 체감 | ③ |
| TC-12 | REQ-07 | 핫스팟만 켠 상태에서 전원 → 1분 안에 조종 화면 접속 | ③ |
| TC-13 | REQ-01, 02 | ESP32 결과 한 줄 → 로봇이 해당 통으로 출발 | ③ |
| TC-14 | REQ-06 | 처리 1회 후 대시보드 개수 +1 | ③ |
| TC-15 | REQ-02 | 인쇄 마커 이미지를 OpenCV 로 찾고 번호·위치를 맞힘 | ① |

## 실행 결과

**RUN-01** — 2026-10-30 16:26 · 커밋 `a14f0ce` · Windows 10 노트북 · Python 3.14.8 · `ROBOT_MODE=fake` · `pytest -v` (16개)

| TC | 자동 시험 | 판정 | 비고 |
| --- | --- | --- | --- |
| TC-01 | `test_move_then_auto_stop` | PASS | 가짜 모드 |
| TC-02 | `test_speed_is_capped`, `test_validation` | PASS | 가짜 모드 |
| TC-03 | `test_obstacle_blocks_forward_but_not_backward`, `test_obstacle_stops_while_moving` | PASS | 거리값을 시험에서 넣음 |
| TC-04 | `test_decide_search_turns_toward_last_seen_side`, `test_decide_align_approach_arrive` | PASS | |
| TC-05 | `test_full_mission_in_sim` | PASS | 가상 시계·2D 시뮬레이션 |
| TC-06 | `test_mission_fails_when_marker_missing` | PASS | 시뮬레이션 |
| TC-07 | `test_mission_api_and_manual_override` | PASS | 가짜 서버 |
| TC-15 | `test_detect_printed_markers` | PASS | 합성 이미지, 실제 카메라 아님 |
| (기타) | 상태·CORS·카메라 없음 503·서보/LED/부저 API | PASS | `test_server`, `test_cors` |

수동 확인(② 노트북 가짜 서버, 10/30): 재활용·일반·비닐 통 임무가 모두 `done`, 1회 약 20~30초. 파이썬 클라이언트 `go()` 로 같은 결과.

| TC | 판정 | 이유 |
| --- | --- | --- |
| TC-08 | NOT_RUN | 모델 미확인 (정유정) |
| TC-09, TC-10, TC-11 | BLOCKED | 라즈봇 조립 중 |
| TC-12 | BLOCKED | 핫스팟 폰 미정, 조립 중 |
| TC-13 | BLOCKED | IF-01 합의 전, 로봇 쪽 수신 미구현 |
| TC-14 | NOT_RUN | 대시보드·기록 API 미구현 |

**결론**: 로봇 소프트웨어의 판단·안전 규칙은 가짜 모드에서 기대대로 동작한다. **실제 로봇 주행, 분류, 전체 연결은 아직 확인하지 않았다.** 이 결과로 시연 성공을 보장하지 않는다.

## 결함 기록

아직 없음. 실제 시험에서 기대와 다르면 `DEF-번호` 로 재현 조건·실제/기대·관련 REQ 를 적고 수정 후 재시험(RUN-번호 추가).
