# 06 · 시험 계획·케이스·결과 (A09~A11)

## 계획

| 항목 | 내용 |
| --- | --- |
| 대상 | 로봇 조종 서버(`jeongmin/robot`), AI 도구·펌웨어(`yujeong/`), 대시보드(예정) |
| 근거 종류 구별 | ① 자동 시험(가짜 모드) ② 보드에서 로직만 시험 ③ 노트북 가짜 서버 수동 확인 ④ **실제 로봇·실제 모델** ⑤ 발표장 사용 — 서로 다른 근거로 적는다 |
| 범위 밖 | 장시간 내구, 여러 바닥 재질, 접근성 전체 |
| 판정 | 사전 조건이 없으면 `BLOCKED`, 실행 전은 `NOT_RUN`, 실제 관찰 후에만 `PASS`/`FAIL` |
| 담당 | 각자 자기 파트 시험·기록, 독립 검토는 11/1 서로 교차 |

## 시험 케이스 (TC)

| ID | 요구 | 확인 내용 | 근거 |
| --- | --- | --- | --- |
| TC-01 | REQ-03 | 이동 명령 후 지정 시간이 지나면 자동 정지 | ① |
| TC-02 | REQ-03 | 속도가 상한을 넘지 않음, 잘못된 값은 거절(422) | ① |
| TC-03 | REQ-03 | 앞 8cm 장애물: 앞 이동 거절·뒤 이동 허용 / 가는 중 10cm 되면 정지 | ① |
| TC-04 | REQ-02 | 판단 규칙: 못 찾으면 회전, 벗어나면 맞추기, 가운데면 전진, 크거나 가까우면 도착 | ① |
| TC-05 | REQ-02 | 가짜 세계에서 통 앞 15~35cm 에 도착 → 출발점 35cm 이내 복귀 | ① |
| TC-06 | REQ-02 | 마커가 없는 통: `failed` + "못 찾았습니다" | ① |
| TC-07 | REQ-03, 04 | 임무 중 수동 이동 → 임무 `cancelled`, 수동 이동은 실행 | ① |
| TC-08 | REQ-01 | 테스트 셋 정확도 90% 이상, 혼동 행렬 기록 (AI 원본 TC-04) | ④ |
| TC-09 | REQ-02 | 실제 로봇·실제 통 3개 × 각 5회: 통 앞 20~30cm 도착·복귀 | ④ |
| TC-10 | REQ-03 | 실제 로봇이 벽 앞 15cm 근처에서 멈추고 밀린 거리 측정 | ④ |
| TC-11 | REQ-04 | 휴대폰으로 조종, 손 떼면 정지, 영상 지연 체감 | ④ |
| TC-12 | REQ-07 | 핫스팟만 켠 상태에서 전원 → 1분 안에 조종 화면 접속 | ④ |
| TC-13 | REQ-01, 02 | 보드 판정 JSON 한 줄 → 로봇이 해당 통으로 출발, 로그 줄·판정 없음·낮은 확신도·임무 중은 무시 | ① 가짜 입력 / ④ 실제 보드 |
| TC-14 | REQ-06 | 처리 1회 후 기록 +1, 완료면 통 개수 +1, 서버 재시작 후 유지 / 대시보드 표시 | ① API / ④ 대시보드 |
| TC-15 | REQ-02 | 인쇄 마커 이미지를 OpenCV 로 찾고 번호·위치를 맞힘 | ① |
| TC-16 | REQ-09 | 보드에 `C` 전송 → 헤더 + JPEG(FFD8…FFD9) 수신 (AI 원본 TC-01) | ④ |
| TC-17 | REQ-01 | 판정 로직에 가짜 점수열: 연속·확신도·격차·중복 방지·STUCK (AI 원본 TC-06) | ② |
| TC-18 | REQ-01 | 보드 실측 정확도 90% 이상, 추론 1초 이내 (AI 원본 TC-05) | ④ |
| TC-19 | REQ-09 | 수집기: 연결 → 찍기 → ZIP 받기, 클래스별 50장·손 비율 기록 (AI 원본 TC-02·03) | ④ |

## 실행 결과

### 로봇 — RUN-R1 · 2026-10-30 16:26 · 커밋 `a14f0ce` · Windows 10 노트북 · Python 3.14.8 · `ROBOT_MODE=fake` · `pytest -v` 16개

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

수동 확인(③, 10/30): 통 3곳 임무 모두 `done`, 1회 약 20~30초. 파이썬 클라이언트 `go()` 로 같은 결과.

### 로봇 — RUN-R2 · 2026-10-30 17:07 · 판정 수신·기록 추가 후 · 같은 환경 · `pytest` 21개 전부 PASS

| TC | 자동 시험 | 판정 | 비고 |
| --- | --- | --- | --- |
| TC-13 | `test_parse_line_keeps_only_json_objects`, `test_verdict_rules_and_manual_override_is_recorded`, `test_board_line_from_reader_thread_starts_mission`, `test_board_reader_reads_lines_and_reconnects` | PASS (가짜 입력) | 시리얼은 가짜 모듈, **실제 보드 아님** |
| TC-14 | `test_done_mission_counts_and_history_survives_restart` | PASS (API) | 대시보드 표시는 미확인 |
| (전부) | RUN-R1 의 16개 + 위 5개 | PASS | |

수동 확인(③, 17:07): 가짜 서버에 `CORS_ORIGINS=http://localhost:8765` → 사전 요청 200·허용 헤더 확인. 자동 출발 꺼짐이면 거절, 켜면 `paper` 판정 → 33초 뒤 `done`, 기록 1건·`paper` 통 1개.

### AI — 담당자 기록 옮김 (원본 `yujeong/ai/docs/A09-A11-test.md`, 팀장 재실행 안 함)

| 실행 | TC | 실제 | 판정 |
| --- | --- | --- | --- |
| 10/28 이 PC, `xiao_stream` USB 모드 | TC-16 | 3회 연속 프레임 수신, JPEG 시작·끝 정상, 31~54 ms | PASS |
| 10/28 | TC-19 | 브라우저 실제 클릭 흐름·ZIP 저장은 실행 안 함 | NOT_RUN |
| 10/30 보드, `sorter_logic.h` | TC-17 | 시나리오 11개 모두 통과, 두 번 실행해 같은 결과 | PASS (로직 한정) |

### 아직 안 한 것

| TC | 판정 | 이유 |
| --- | --- | --- |
| TC-08, TC-18 | BLOCKED | 분리수거 학습 사진 없음 (10/30 담당자 기록) |
| TC-09, TC-10, TC-11 | BLOCKED | 라즈봇 조립 중 |
| TC-12 | BLOCKED | 핫스팟 폰 미정, 조립 중 |
| TC-13 (④ 실제 보드) | BLOCKED | 추론 펌웨어 미구현, 로봇 조립 중 |
| TC-14 (④ 대시보드) | NOT_RUN | 대시보드 이름 수정 반영 대기 |

**결론**: 로봇의 판단·안전 규칙(가짜 모드), 보드 영상 전송, 판정 확정 로직(가짜 점수)은 기대대로 동작했다. **실제 로봇 주행, 학습된 모델의 분류, 보드→로봇→웹 전체 연결은 아직 확인하지 않았다.** 이 결과로 시연 성공을 보장하지 않는다.

## 결함 기록

아직 없음. 실제 시험에서 기대와 다르면 `DEF-번호` 로 재현 조건·실제/기대·관련 REQ 를 적고, 수정 후 재시험(RUN 번호 추가).
