# 04 · 화면·구조·인터페이스·결정 (A05~A08)

## 구조 (DES-01)

```
 물건 ─▶ 트레이 ◀── XIAO ESP32S3 Sense 카메라 (분류·확정) ── USB · IF-01 ──▶ 라즈베리파이 5 · 조종 서버
                                                                            ├ 라즈봇 기본 USB 카메라: 통 마커 찾기
                                                                            ├ 초음파: 거리·장애물
                                                                            └ 메카넘 바퀴 4개 (I2C 0x2B)
                                     │ HTTP · IF-02 (휴대폰 핫스팟)
               휴대폰 조종 화면 (DES-03)          웹 대시보드 · 웹앱 (DES-04, 노트북에서 실행)
```

| 요소 | 책임 | 실행 장치 | 원본 |
| --- | --- | --- | --- |
| 추론·판정 펌웨어 | 분류, 확정 규칙, 판정 JSON 출력 | XIAO ESP32S3 | `yujeong/firmware/xiao_sorter/` (판정 로직 구현, 추론 미구현) |
| 영상 펌웨어·수집기 | 학습 사진 수집 (USB/Wi-Fi) | XIAO + 노트북 브라우저 | `yujeong/firmware/xiao_stream/`, `yujeong/ai/collector/` |
| 조종 서버 | 이동·안전·임무·카메라·API, 판정 수신 | 라즈베리파이 5 | `jeongmin/robot/server/` |
| 조종 화면 | 수동 조종·수동 분류(통 버튼) | 휴대폰 브라우저 (로봇 서버가 제공) | `jeongmin/robot/server/static/` |
| 대시보드 | 상태·기록·통계 | 노트북 브라우저 | `minhyeong/` (예정) |

- **보드는 Wi-Fi 없이 USB 로만** 로봇에 연결. 웹으로 가는 기록은 로봇이 대신 제공한다 (AI 원본 ADR-02 ③ 과 같은 방향).
- **저장**: 처리 기록은 로봇 서버가 보관 (IF-04). 원격 DB 는 쓰지 않음.
- **경계**: 인터넷 없이 핫스팟 안에서 동작. 배포된(https) 사이트에서 로봇 접속은 브라우저가 막으므로 대시보드는 노트북 `http://localhost` 로 실행.
- **같은 USB 포트 공유**: 보드를 라즈베리파이에 꽂으면 노트북 수집기(Web Serial)와 동시에 쓸 수 없다 → 사진 수집은 보드를 노트북에 직접 연결해서.

## 임무 상태 흐름 (DES-02)

```
판정 확정(IF-01) 또는 통 버튼 ─▶ search ⇄ align ⇄ approach → arrived → (통에 넣기) → backing → 출발점으로 … → done
                                   │ 40걸음 못 찾음 → failed          수동 조종·정지 → cancelled (즉시 정지)
```

- 한 걸음 = 조금 움직이기(0.25초) → 멈추기 → 화면 보고 다시 판단. 판단 규칙은 `navigator.decide()` 한곳에 있다.
- `(통에 넣기)` 단계는 지금 신호(LED + 소리)만 낸다 (ADR-04).
- 보드의 판정 로직은 확정 뒤 트레이가 빌 때까지(`empty` 3번) 새 확정을 내지 않는다. 로봇이 이동하는 동안 보드가 내는 STUCK(10초 안에 안 빔)은 **로봇이 무시**한다 — 임무가 30초쯤 걸리므로 (IF-01 쟁점).

## 화면 (DES-03 조종 화면 · 구현됨)

- 위: 카메라 영상, 거리·라인·상태(장애물 정지 포함).
- 가운데: 방향 버튼 9개 + 회전 2개, 누르는 동안만 이동. 키보드 W/S/A/D/Q/E, Space 정지.
- 아래: 통 찾아가기 버튼(통마다), "도착 동작·복귀" 선택, 진행 단계·보이는 마커, 임무 취소.
- 색만으로 상태를 전하지 않고 글자로도 표시한다. 접근성 전체 점검은 미확인.

## 화면 (DES-04 대시보드 · 서민형, 미확인)

제안: 로봇 연결 상태 / 지금 하는 일 / 최근 판정·확신도 / 통별 개수 / 오늘 처리량 / 탄소 절감량(출처 표시) / 최근 기록. 값 없음은 "—".

## 인터페이스 계약

**IF-01 보드 → 라즈베리파이 판정 (AI 제안, 로봇 수용 — 합의 마무리 필요)**
원본: `yujeong/docs/A07-interface.md` IF-02
- USB 시리얼 115200 (USB CDC), 한 줄 = 한 메시지, UTF-8, LF 로 끝남.
- 판정: `{"class":"can","conf":0.93,"ms":173}` / 판정 없음: `{"class":null,"conf":0.41,"ms":173}` / 오류: `{"error":"camera"}`
- 받는 쪽은 `{` 로 시작하지 않는 줄(부팅·디버그 로그)과 해석 안 되는 줄을 버린다.
- 값 없음은 `null`, 0 으로 채우지 않는다.
- **확정 신호**: AI 원본(A03 I-03)대로 조건 미달은 `class: null` 이므로 **`class` 가 있으면 확정**으로 본다. 보드가 매 프레임을 보내는 방식으로 바뀌면 확정 줄에 `"event":"decision"` 을 붙인다 — 로봇은 `event` 가 있으면 `decision` 일 때만 출발 (두 방식 모두 수용, 최종 방식은 AI 담당이 정함). STUCK 등 다른 `event` 는 무시.
- 로봇 출발 조건: 자동 출발 켜짐(기본 꺼짐) · 임무 중 아님 · `class` 가 통 이름(`can/pet/paper`) · `conf` ≥ 0.8. 거절 이유는 `GET /api/sort` 의 `last_verdict.result`.
- 라즈베리파이 쪽: 포트 `BOARD_PORT=auto`(`/dev/ttyACM*`), 뽑히면 2초마다 다시 찾음. 권한 오류면 `dialout` 그룹. 수신 구현 완료(TASK-R4, `jeongmin/robot/server/board.py`·`sorter.py`). 확인용 `yujeong/firmware/xiao_sorter/pi_reader.py` 도 있음.

**IF-02 로봇 HTTP API (구현됨, 원본 `jeongmin/README.md`)**
- 이동: `POST /api/move {action, speed, duration_ms}`, `POST /api/stop`
- 상태: `GET /api/status` (mode, moving, blocked, mission …)
- 임무: `POST /api/mission {station, dump, return_home}` → 202, `GET /api/mission`, `POST /api/mission/cancel`
- 마커·통: `GET /api/markers`, `GET /api/stations` / 카메라: `GET /api/camera.jpg`, `GET /api/stream`
- 브라우저에서 부를 때 웹 주소를 `CORS_ORIGINS` 에 등록.

**IF-03 통 목록 `jeongmin/robot/stations.json` (구현됨)**
- `home`=마커 0, `can`=1, `pet`=2, `paper`=3 (10/30 ADR-05 반영). 마커 DICT_4X4_50, 한 변 10cm, 통 앞면 카메라 높이(약 15cm).
- 판정 `class` 가 그대로 통 이름. `empty`·`null` 은 통이 없으므로 로봇이 움직이지 않는다.

**IF-04 처리 기록 API (구현됨 — 서민형 제안 형식, 통 이름만 can/pet/paper)**
- `GET /api/history` → `{"bins": {"can": 3, "pet": 1, "paper": 0}, "items": [{id, time, label, confidence, by, result, seconds, steps, message}]}`
  - `by`: `ai`(판정으로 출발) / `web`(통 버튼·`POST /api/mission`, `confidence: null`). `result`: `done`/`failed`/`cancelled`. `bins` 는 `done` 만 센다.
- `POST /api/history/reset {"station": "can"}` 통 비우기 (빼면 전부) — 개수만 0, 기록은 남음.
- `GET /api/mission` 에 지금 임무의 `label`·`confidence`·`by` 포함.
- 실제 로봇은 `data/history.jsonl` 에 저장해 서버를 다시 켜도 이어짐 (가짜 모드는 저장 안 함).
- 대시보드(`http://localhost:8765`)는 로봇 실행 때 `CORS_ORIGINS` 에 등록 (`robot.env.example`).

**IF-05 보드 → PC 영상 (수집용, 구현됨 — AI 원본 IF-01)**
- PC 가 `C` 1바이트 → `AA 55 AA 55` + 길이(u32 LE) + JPEG(VGA). 2초 안에 없으면 응답 없음. 보조로 보드 Wi-Fi AP 대시보드.

## 결정 기록 (ADR)

**ADR-01 통 찾기는 ArUco 마커 — 결정 (10/30, 팀장)**
- 대안: 시간으로 움직이기(바퀴 회전 센서가 없어 오차가 쌓임) / 바닥 라인 따라가기(테이프 설치, 경로 고정) / 마커.
- 이유: 학습 없이 번호·방향·크기를 알 수 있고, 계속 보며 고치므로 오차가 쌓이지 않음.
- 포기·재검토: 가려지거나 조명이 나쁘면 못 찾음. 실제 인식 거리가 1m 미만이면 마커 크기·배치 변경.

**ADR-02 분류는 로봇 위 보드 카메라 + USB — 결정 (10/30, 팀장)**
- 대안: 노트북 웹캠 → PC → 보드로 사진 전송 / 출발점 고정 카메라 + Wi-Fi / 로봇 위 보드 카메라 + USB.
- 이유: 보드 카메라가 동작함(TC-16), 사진 전송 경로가 필요 없음, Wi-Fi 상태와 무관, 케이블 하나로 전원·데이터. AI 원본 ADR-01 ②·ADR-02 ③ 추천과 같은 방향.
- 포기: 화질·모델 크기가 작음, 카메라가 90° 누워 있음(RISK-13). 대체: 정확도가 낮으면 C270 + 라즈베리파이 분류 (로봇은 결과만 받으므로 구조 유지).

**ADR-03 이동은 '움직이고-멈추고-보기' 반복 — 결정 (10/30, 팀장)**
- 이유: 멈춘 화면으로 판단, 끊겨도 자동 정지와 맞물림. 포기: 이동이 느림(시뮬레이션 1회 약 30초).

**ADR-04 통에 넣는 방법 — 미결정**
- 후보·배선 제안은 AI 원본 A08 ADR-03, A20 참고. 정하기 전 기본: 도착 신호 후 사람이 넣기.
- 정해지면 REQ-05·TASK-R6·시험·[10](10-bom-power.md) 전원을 함께 고친다.

**ADR-05 분류 종류·통 이름 — 결정 (10/30, 팀장 — AI 담당 안 채택)**
- 선택: AI 안 `can / pet / paper / empty` 를 그대로 쓰고, 통도 캔 / 페트 / 종이 3개로 한다.
- 대안: 통은 `recycle / general / vinyl` 로 두고 판정 종류 → 통 대응표를 두기 (로봇 쪽 초안).
- 이유: 분류는 AI 담당 영역(02 RACI), 수집기·판정 로직이 이미 이 이름으로 만들어져 있음, 대응표가 없어 연결 실수가 줄어듦.
- 반영: `stations.json`, 인쇄 마커, 로봇 시험 (TASK-R10 완료). 앞으로 이름을 바꾸면 07 의 변경 영향 목록을 따른다.

**ADR-06 통 가득 참 판단 — 미결정 (선택 기능)**
- 안: 센서 없이 통별 개수 기준 (AI 원본 ADR-05 추천). 기준 개수는 팀이 정한다.
